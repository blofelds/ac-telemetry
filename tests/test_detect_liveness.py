"""Detect-loop liveness on /api/status: ok / degraded / stopped (disabled)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.detect import DetectService
from ac_telemetry.detect.service import STALE_TICK_MULTIPLIER
from ac_telemetry.settings import load_settings
from ac_telemetry.store import LapStore, SessionStore


class _FakeThread:
    def __init__(self, *, alive: bool) -> None:
        self._alive = alive

    def is_alive(self) -> bool:
        return self._alive


def _detect_service(tmp_path: Path, *, enabled: bool = True) -> DetectService:
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    settings.detect.enabled = enabled
    settings.detect.fps = 2.0
    settings.detect.lap_time.reader = "mock"
    lap_store = LapStore(settings.data_dir)
    lap_store.ensure()
    return DetectService(
        settings=settings,
        get_frame=lambda: None,
        get_session_id=lambda: None,
        record_lap=lap_store.append_lap,
    )


def _status_client(
    tmp_path: Path, detect: DetectService
) -> TestClient:
    settings = detect.settings
    store = SessionStore(settings.data_dir)
    store.ensure()
    capture = CaptureService(settings=settings)
    # Simulate capture still running while detect may be dead.
    capture.stats.running = True
    app = create_app(
        settings, capture, store, lap_store=LapStore(settings.data_dir), detect=detect
    )
    return TestClient(app)


def test_liveness_alive_fresh_tick_is_ok(tmp_path: Path) -> None:
    service = _detect_service(tmp_path)
    service._thread = _FakeThread(alive=True)  # type: ignore[assignment]
    service._last_tick_mono = time.monotonic()

    live = service.liveness()
    assert live["enabled"] is True
    assert live["alive"] is True
    assert live["running"] is True
    assert live["health"] == "ok"
    assert live["last_tick_age_s"] is not None
    assert live["last_tick_age_s"] < 1.0
    assert live["stale_after_s"] == round(
        (1.0 / 2.0) * STALE_TICK_MULTIPLIER, 3
    )


def test_liveness_thread_dead_is_degraded(tmp_path: Path) -> None:
    service = _detect_service(tmp_path)
    service._thread = _FakeThread(alive=False)  # type: ignore[assignment]
    service._last_tick_mono = time.monotonic()

    live = service.liveness()
    assert live["enabled"] is True
    assert live["alive"] is False
    assert live["running"] is False
    assert live["health"] == "degraded"


def test_liveness_stale_tick_is_degraded(tmp_path: Path) -> None:
    service = _detect_service(tmp_path)
    service._thread = _FakeThread(alive=True)  # type: ignore[assignment]
    # fps=2 → interval 0.5s → stale after 2.0s; age well past that.
    service._last_tick_mono = time.monotonic() - 10.0

    live = service.liveness()
    assert live["alive"] is True
    assert live["running"] is True
    assert live["health"] == "degraded"
    assert live["last_tick_age_s"] is not None
    assert live["last_tick_age_s"] > live["stale_after_s"]


def test_liveness_disabled_is_stopped_not_alarm(tmp_path: Path) -> None:
    service = _detect_service(tmp_path, enabled=False)
    # Even a stale/dead-looking internal state must not look like a crash.
    service._thread = _FakeThread(alive=False)  # type: ignore[assignment]
    service._last_tick_mono = time.monotonic() - 60.0

    live = service.liveness()
    assert live["enabled"] is False
    assert live["running"] is False
    assert live["alive"] is False
    assert live["health"] == "stopped"
    assert live["stale_after_s"] is None


def test_api_status_exposes_detect_liveness(tmp_path: Path) -> None:
    service = _detect_service(tmp_path)
    service._thread = _FakeThread(alive=False)  # type: ignore[assignment]
    service._last_tick_mono = time.monotonic()

    client = _status_client(tmp_path, service)
    payload: dict[str, Any] = client.get("/api/status").json()

    assert payload["running"] is True  # capture still green
    detect = payload["detect"]
    assert detect["enabled"] is True
    assert detect["alive"] is False
    assert detect["running"] is False
    assert detect["health"] == "degraded"
    assert "last_tick_age_s" in detect


def test_api_status_disabled_detect_not_degraded(tmp_path: Path) -> None:
    service = _detect_service(tmp_path, enabled=False)
    client = _status_client(tmp_path, service)
    payload = client.get("/api/status").json()
    detect = payload["detect"]
    assert detect["enabled"] is False
    assert detect["health"] == "stopped"
    assert detect["health"] != "degraded"


def test_status_html_renders_detect_tile() -> None:
    """Phone UI must surface Detect separately from Capture."""
    from ac_telemetry.web import STATUS_HTML

    assert 'id="detect-health"' in STATUS_HTML
    assert "renderDetectHealth" in STATUS_HTML
    assert "dot warn" in STATUS_HTML or "dot.warn" in STATUS_HTML
    assert "degraded" in STATUS_HTML
