"""Smoke tests for lap-time parse, CSV store, API, and metrics."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.detect import DetectService
from ac_telemetry.detect.readers import MockLapTimeReader, parse_lap_time_text
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
