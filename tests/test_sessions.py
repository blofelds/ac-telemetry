"""Smoke tests for Slice 1 session API (CSV + counters)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.metrics import REGISTRY
from ac_telemetry.settings import load_settings
from ac_telemetry.store import SessionStore


def _client(tmp_path: Path) -> TestClient:
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    store = SessionStore(settings.data_dir)
    store.ensure()
    capture = CaptureService(settings=settings)
    app = create_app(settings, capture, store)
    return TestClient(app)


def test_session_lifecycle_and_history(tmp_path: Path) -> None:
    client = _client(tmp_path)

    empty = client.get("/api/sessions")
    assert empty.status_code == 200
    assert empty.json()["sessions"] == []
    assert empty.json()["current"] is None

    created = client.post(
        "/api/sessions",
        json={"track": "Monza", "car": "Ferrari 488 GT3", "notes": "wet"},
    )
    assert created.status_code == 201
    session = created.json()["session"]
    assert session["track"] == "Monza"
    assert session["car"] == "Ferrari 488 GT3"
    assert session["notes"] == "wet"
    assert session["status"] == "running"
    sid = session["session_id"]

    conflict = client.post("/api/sessions", json={"track": "Spa"})
    assert conflict.status_code == 409

    current = client.get("/api/sessions/current")
    assert current.json()["session"]["session_id"] == sid

    listed = client.get("/api/sessions")
    assert len(listed.json()["sessions"]) == 1

    ended = client.post(f"/api/sessions/{sid}/end")
    assert ended.status_code == 200
    assert ended.json()["session"]["status"] == "stopped"
    assert ended.json()["session"]["ended_at"]

    after = client.get("/api/sessions/current")
    assert after.json()["session"] is None

    # CSV on disk has track/car/notes columns
    csv_path = tmp_path / "sessions" / "sessions.csv"
    text = csv_path.read_text(encoding="utf-8")
    assert "track,car,notes" in text.splitlines()[0]
    assert "Monza" in text


def test_metrics_include_session_counters(tmp_path: Path) -> None:
    # Fresh registry counters are process-global; just assert names exist after a start.
    client = _client(tmp_path)
    client.post("/api/sessions", json={"track": "Imola", "car": "Porsche"})
    body = client.get("/metrics").text
    assert "ac_telemetry_sessions_started_total" in body
    assert "ac_telemetry_sessions_ended_total" in body
    assert "ac_telemetry_sessions_open" in body
    # Silence unused import lint if any tooling complains
    assert REGISTRY is not None
