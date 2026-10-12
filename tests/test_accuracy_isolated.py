"""Accuracy feature must stay default-off and removable from the core path."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.detect import DetectService
from ac_telemetry.settings import AccuracySettings, load_settings
from ac_telemetry.store import LapStore, SessionStore


def test_accuracy_defaults_disabled() -> None:
    settings = load_settings()
    assert settings.accuracy.enabled is False
    assert AccuracySettings().enabled is False


def test_env_enables_accuracy(monkeypatch) -> None:
    monkeypatch.setenv("AC_TELEMETRY_ACCURACY_ENABLED", "1")
    # load_settings reads env inside _parse_accuracy; bypass cache.
    from ac_telemetry import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    settings = load_settings()
    assert settings.accuracy.enabled is True
    monkeypatch.delenv("AC_TELEMETRY_ACCURACY_ENABLED", raising=False)
    settings_mod.get_settings.cache_clear()


def test_api_has_no_accuracy_routes_when_disabled(tmp_path: Path) -> None:
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    settings.accuracy.enabled = False
    store = SessionStore(settings.data_dir)
    store.ensure()
    capture = CaptureService(settings=settings)
    app = create_app(settings, capture, store, accuracy=None)
    client = TestClient(app)
    assert client.get("/api/accuracy/status").status_code == 404


def test_api_accuracy_routes_when_enabled(tmp_path: Path) -> None:
    from ac_telemetry.accuracy import maybe_accuracy_session

    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    settings.accuracy.enabled = True
    settings.accuracy.roi_tee = False  # no OpenCV needed for this smoke
    settings.accuracy.ocr_log = True
    settings.accuracy.with_session = True

    store = SessionStore(settings.data_dir)
    store.ensure()
    lap_store = LapStore(settings.data_dir)
    lap_store.ensure()
    capture = CaptureService(settings=settings)
    accuracy = maybe_accuracy_session(settings.accuracy, settings.data_dir)
    assert accuracy is not None
    detect = DetectService(
        settings=settings,
        get_frame=capture.get_latest_frame,
        get_session_id=lambda: (store.current_session() or {}).get("session_id"),
        record_lap=lap_store.append_lap,
        on_sample=accuracy.on_sample,
    )
    app = create_app(
        settings,
        capture,
        store,
        lap_store=lap_store,
        detect=detect,
        accuracy=accuracy,
    )
    client = TestClient(app)

    status = client.get("/api/accuracy/status")
    assert status.status_code == 200
    assert status.json()["enabled"] is True

    created = client.post(
        "/api/sessions", json={"track": "Monza", "car": "Test", "notes": ""}
    )
    assert created.status_code == 201
    sid = created.json()["session"]["session_id"]
    assert accuracy.status()["session_id"] == sid

    # Emit a sample through the detect hook path.
    accuracy.on_sample(
        session_id=sid,
        mono_s=1.0,
        wall_s=1000.0,
        ok=True,
        text="1:07.717",
        lap_time_ms=67_717,
        error="",
        roi_img=None,
    )
    assert accuracy.status()["ocr_samples"] == 1

    lap_store.append_lap(
        {
            "session_id": sid,
            "lap_number": 1,
            "lap_time": "1:07.717",
            "lap_time_ms": 67_717,
            "source": "mock",
            "raw_text": "1:07.717",
        }
    )
    prefill = client.get(f"/api/accuracy/sessions/{sid}/gt/prefill")
    assert prefill.status_code == 200
    assert prefill.json()["laps"][0]["lap_time"] == "1:07.717"

    scored = client.post(
        f"/api/accuracy/sessions/{sid}/gt",
        json={"laps": ["1:07.717"], "score": True},
    )
    assert scored.status_code == 200, scored.text
    body = scored.json()
    assert body["score"]["write_pct"] == 100.0

    ended = client.post("/api/sessions/current/end")
    assert ended.status_code == 200
    assert accuracy.status()["session_id"] is None


def test_detect_on_sample_none_is_noop(tmp_path: Path) -> None:
    """Core path: on_sample=None must not change lap recording."""
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    settings.detect.enabled = True
    settings.detect.fps = 20.0
    settings.detect.debounce_reads = 1
    settings.detect.lap_time.reader = "mock"
    settings.detect.lap_time.mode = "last_lap"
    settings.detect.lap_time.mock_interval_seconds = 0.2
    settings.detect.lap_time.last_lap_stable_ms = 0
    settings.detect.lap_time.min_lap_ms = 0

    store = SessionStore(settings.data_dir)
    store.ensure()
    lap_store = LapStore(settings.data_dir)
    lap_store.ensure()
    capture = CaptureService(settings=settings)
    detect = DetectService(
        settings=settings,
        get_frame=capture.get_latest_frame,
        get_session_id=lambda: (store.current_session() or {}).get("session_id"),
        record_lap=lap_store.append_lap,
        on_sample=None,
    )
    app = create_app(
        settings, capture, store, lap_store=lap_store, detect=detect, accuracy=None
    )
    client = TestClient(app)
    detect.start()
    try:
        created = client.post(
            "/api/sessions", json={"track": "T", "car": "C", "notes": ""}
        )
        assert created.status_code == 201
        import time

        deadline = time.time() + 3.0
        laps = []
        while time.time() < deadline:
            laps = lap_store.list_laps(
                session_id=created.json()["session"]["session_id"], limit=10
            )
            if laps:
                break
            time.sleep(0.05)
        assert laps, "expected mock lap with on_sample=None"
    finally:
        detect.stop(timeout=1.0)
