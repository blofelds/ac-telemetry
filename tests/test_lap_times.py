"""Smoke tests for lap-time parse, CSV store, API, and metrics."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.detect import DetectService
from ac_telemetry.detect.readers import (
    LapTimeReading,
    MockLapTimeReader,
    format_lap_time_ms,
    parse_lap_time_text,
)
from ac_telemetry.metrics import REGISTRY
from ac_telemetry.settings import load_settings
from ac_telemetry.store import LapStore, SessionStore


def test_parse_lap_time_text_variants() -> None:
    assert parse_lap_time_text("1:44.321") == ("1:44.321", 104_321)
    assert parse_lap_time_text("01:44.321") == ("1:44.321", 104_321)
    assert parse_lap_time_text("noise 1:40.005 more") == ("1:40.005", 100_005)
    assert parse_lap_time_text("garbage") is None
    assert parse_lap_time_text("1:99.000") is None


def test_mock_reader_emits_stable_then_new_lap() -> None:
    reader = MockLapTimeReader(interval_seconds=1.0)
    first = reader.read(None)
    assert first.ok
    assert first.lap_time_ms == 0
    time.sleep(1.1)
    second = reader.read(None)
    assert second.ok
    assert second.lap_time_ms and second.lap_time_ms > 0


def test_lap_store_append_and_list(tmp_path: Path) -> None:
    store = LapStore(tmp_path / "sessions")
    store.ensure()
    row = store.append_lap(
        {
            "session_id": "abc123",
            "lap_number": 1,
            "lap_time": "1:42.100",
            "lap_time_ms": 102_100,
            "source": "mock",
            "raw_text": "1:42.100",
        }
    )
    assert row["recorded_at"]
    laps = store.list_laps(session_id="abc123")
    assert len(laps) == 1
    assert laps[0]["lap_time"] == "1:42.100"


def _client(tmp_path: Path) -> tuple[TestClient, DetectService]:
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    settings.detect.enabled = True
    settings.detect.fps = 10.0
    settings.detect.debounce_reads = 1
    settings.detect.lap_time.reader = "mock"
    settings.detect.lap_time.mode = "last_lap"
    settings.detect.lap_time.mock_interval_seconds = 1.0

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
    )
    app = create_app(
        settings, capture, store, lap_store=lap_store, detect=detect
    )
    return TestClient(app), detect


def test_api_current_lap_and_metrics(tmp_path: Path) -> None:
    client, detect = _client(tmp_path)
    detect.start()
    try:
        created = client.post(
            "/api/sessions",
            json={"track": "Monza", "car": "Ferrari"},
        )
        assert created.status_code == 201

        # Wait for mock reader to emit at least one completed lap.
        deadline = time.time() + 4.0
        recorded = None
        while time.time() < deadline:
            cur = client.get("/api/laps/current").json()
            recorded = (cur.get("lap") or {}).get("last_recorded_time")
            if recorded and recorded != "0:00.000":
                break
            time.sleep(0.2)

        assert recorded and recorded != "0:00.000"

        laps = client.get("/api/laps").json()
        assert laps["laps"]
        assert laps["laps"][0]["session_id"] == created.json()["session"]["session_id"]

        status = client.get("/api/status").json()
        assert status["lap"]["displayed_time"]

        body = client.get("/metrics").text
        assert "ac_telemetry_detect_latency_seconds" in body
        assert "ac_telemetry_detect_failures_total" in body
        assert "ac_telemetry_laps_recorded_total" in body
        assert REGISTRY is not None
    finally:
        detect.stop()


def _last_lap_service(
    *,
    min_lap_ms: int = 30_000,
    debounce_reads: int = 2,
) -> tuple[DetectService, list[dict[str, Any]]]:
    """DetectService wired for direct ``_handle_reading`` tests (no thread)."""
    settings = load_settings()
    settings.detect.enabled = True
    settings.detect.debounce_reads = debounce_reads
    settings.detect.lap_time.reader = "mock"
    settings.detect.lap_time.mode = "last_lap"
    settings.detect.lap_time.min_lap_ms = min_lap_ms
    settings.detect.debug_dump.enabled = False

    recorded: list[dict[str, Any]] = []

    def _append(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        out["recorded_at"] = "test"
        recorded.append(out)
        return out

    detect = DetectService(
        settings=settings,
        get_frame=lambda: None,
        get_session_id=lambda: "sess-test",
        record_lap=_append,
    )
    detect.state.enabled = True
    detect.state.reader = "mock"
    detect.state.mode = "last_lap"
    detect._reader = MockLapTimeReader(interval_seconds=999)
    return detect, recorded


def _feed_stable(
    detect: DetectService,
    lap_time_ms: int,
    *,
    times: int = 2,
) -> None:
    text = format_lap_time_ms(lap_time_ms)
    reading = LapTimeReading(ok=True, text=text, lap_time_ms=lap_time_ms)
    for _ in range(times):
        detect._handle_reading(detect.settings.detect, reading, 0.01)


def test_last_lap_wall_clock_gate_blocks_rapid_distinct_values(
    monkeypatch: Any,
) -> None:
    """OCR flicker (many distinct values in < min_lap_ms) → one CSV write."""
    detect, recorded = _last_lap_service(min_lap_ms=30_000, debounce_reads=2)
    mono = {"t": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: mono["t"])

    _feed_stable(detect, 181_233)  # 3:01.233
    assert len(recorded) == 1

    # Thousandths / lookalike flicker well inside min_lap_ms wall clock.
    for ms in (181_239, 181_293, 181_299, 541_233):
        mono["t"] += 0.5
        _feed_stable(detect, ms)
    assert len(recorded) == 1
    assert recorded[0]["lap_time_ms"] == 181_233


def test_last_lap_records_after_min_lap_wall_clock(
    monkeypatch: Any,
) -> None:
    """A real LAST change after ≥ min_lap_ms wall time still records."""
    detect, recorded = _last_lap_service(min_lap_ms=30_000, debounce_reads=2)
    mono = {"t": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: mono["t"])

    _feed_stable(detect, 150_745)  # 2:30.745
    assert len(recorded) == 1

    mono["t"] = 29.9
    _feed_stable(detect, 66_790)
    assert len(recorded) == 1  # still gated

    mono["t"] = 30.0
    _feed_stable(detect, 66_790)
    assert len(recorded) == 2
    assert recorded[1]["lap_time_ms"] == 66_790


def test_last_lap_close_values_both_record_when_wall_gap_ok(
    monkeypatch: Any,
) -> None:
    """Consecutive real laps may differ by only ~50ms; do not reject on Δvalue."""
    detect, recorded = _last_lap_service(min_lap_ms=30_000, debounce_reads=2)
    mono = {"t": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: mono["t"])

    _feed_stable(detect, 100_000)  # 1:40.000
    assert len(recorded) == 1

    mono["t"] = 60.0  # well past min_lap_ms
    _feed_stable(detect, 100_050)  # only 50ms faster — still a real new LAST
    assert len(recorded) == 2
    assert recorded[1]["lap_time_ms"] == 100_050
    assert abs(recorded[1]["lap_time_ms"] - recorded[0]["lap_time_ms"]) == 50


def test_last_lap_retries_gated_value_until_wall_clock_opens(
    monkeypatch: Any,
) -> None:
    """Value that arrived early is recorded once the gate opens (no re-flicker)."""
    detect, recorded = _last_lap_service(min_lap_ms=30_000, debounce_reads=2)
    mono = {"t": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: mono["t"])

    _feed_stable(detect, 63_532)
    assert len(recorded) == 1

    mono["t"] = 5.0
    _feed_stable(detect, 68_992)
    assert len(recorded) == 1

    # Same stable value still showing when the gate opens → one write.
    mono["t"] = 30.0
    reading = LapTimeReading(ok=True, text="1:08.992", lap_time_ms=68_992)
    detect._handle_reading(detect.settings.detect, reading, 0.01)
    assert len(recorded) == 2
    assert recorded[1]["lap_time_ms"] == 68_992


def test_last_lap_same_value_does_not_rerecord(
    monkeypatch: Any,
) -> None:
    detect, recorded = _last_lap_service(min_lap_ms=1_000, debounce_reads=2)
    mono = {"t": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: mono["t"])

    _feed_stable(detect, 70_000)
    mono["t"] = 5.0
    _feed_stable(detect, 70_000)
    assert len(recorded) == 1
