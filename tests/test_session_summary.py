"""Session dossier summary: LapStore aggregates + GET /api/sessions/{id}/summary."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.settings import load_settings
from ac_telemetry.store import LapStore, SessionStore
from ac_telemetry.web import STATUS_HTML


def _client(tmp_path: Path) -> tuple[TestClient, LapStore]:
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    store = SessionStore(settings.data_dir)
    store.ensure()
    lap_store = LapStore(settings.data_dir)
    lap_store.ensure()
    capture = CaptureService(settings=settings)
    app = create_app(settings, capture, store, lap_store=lap_store)
    return TestClient(app), lap_store


def test_format_delta_ms() -> None:
    assert LapStore.format_delta_ms(0) == "BEST"
    assert LapStore.format_delta_ms(320) == "+0.320"
    assert LapStore.format_delta_ms(1430) == "+1.430"
    assert LapStore.format_delta_ms(62_100) == "+1:02.100"
    assert LapStore.format_delta_ms(-50) == "-0.050"


def test_summarize_session_best_avg_deltas(tmp_path: Path) -> None:
    store = LapStore(tmp_path / "sessions")
    store.ensure()
    sid = "sessdossier01"
    for n, ms in ((1, 102_100), (2, 101_780), (3, 103_210)):
        store.append_lap(
            {
                "session_id": sid,
                "lap_number": n,
                "lap_time": f"{ms // 60000}:{(ms % 60000) // 1000:02d}.{ms % 1000:03d}",
                "lap_time_ms": ms,
                "source": "mock",
                "raw_text": "",
            }
        )

    summary = store.summarize_session(sid)
    assert summary["lap_count"] == 3
    assert summary["timed_lap_count"] == 3
    assert summary["best_ms"] == 101_780
    assert summary["best_lap_number"] == "2"
    assert summary["best_lap_time"] == "1:41.780"
    assert summary["avg_ms"] == (102_100 + 101_780 + 103_210) // 3
    assert summary["spread_ms"] == 103_210 - 101_780
    # Newest-first
    assert [row["lap_number"] for row in summary["laps"]] == ["3", "2", "1"]
    by_n = {str(row["lap_number"]): row for row in summary["laps"]}
    assert by_n["2"]["is_best"] is True
    assert by_n["2"]["delta_text"] == "BEST"
    assert by_n["3"]["delta_ms"] == 103_210 - 101_780
    assert by_n["3"]["delta_text"] == "+1.430"


def test_summarize_session_skips_invalid_times(tmp_path: Path) -> None:
    store = LapStore(tmp_path / "sessions")
    store.ensure()
    sid = "sessbad"
    store.append_lap(
        {
            "session_id": sid,
            "lap_number": 1,
            "lap_time": "",
            "lap_time_ms": "",
            "source": "mock",
            "raw_text": "",
        }
    )
    store.append_lap(
        {
            "session_id": sid,
            "lap_number": 2,
            "lap_time": "1:40.000",
            "lap_time_ms": 100_000,
            "source": "mock",
            "raw_text": "1:40.000",
        }
    )
    summary = store.summarize_session(sid)
    assert summary["lap_count"] == 2
    assert summary["timed_lap_count"] == 1
    assert summary["best_ms"] == 100_000
    invalid = next(r for r in summary["laps"] if str(r["lap_number"]) == "1")
    assert invalid["delta_ms"] is None
    assert invalid["is_best"] is False


def test_api_session_summary_endpoint(tmp_path: Path) -> None:
    client, lap_store = _client(tmp_path)
    created = client.post(
        "/api/sessions",
        json={"track": "Monza", "car": "488", "notes": "set 1"},
    )
    assert created.status_code == 201
    sid = created.json()["session"]["session_id"]
    lap_store.append_lap(
        {
            "session_id": sid,
            "lap_number": 1,
            "lap_time": "1:42.100",
            "lap_time_ms": 102_100,
            "source": "mock",
            "raw_text": "1:42.100",
        }
    )
    lap_store.append_lap(
        {
            "session_id": sid,
            "lap_number": 2,
            "lap_time": "1:41.780",
            "lap_time_ms": 101_780,
            "source": "mock",
            "raw_text": "1:41.780",
        }
    )

    resp = client.get(f"/api/sessions/{sid}/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session"]["track"] == "Monza"
    assert body["session"]["car"] == "488"
    assert body["session"]["notes"] == "set 1"
    assert body["summary"]["lap_count"] == 2
    assert body["summary"]["best_ms"] == 101_780
    assert body["summary"]["best_lap_time"] == "1:41.780"
    assert body["summary"]["avg_lap_time"]
    assert len(body["summary"]["laps"]) == 2

    missing = client.get("/api/sessions/does-not-exist/summary")
    assert missing.status_code == 404


def test_status_html_dossier_markers() -> None:
    """Phone UI: history tap → dossier; List default; lives beside stint scroll."""
    assert 'id="dossier-view"' in STATUS_HTML
    assert 'id="home-view"' in STATUS_HTML
    assert "data-session-id" in STATUS_HTML
    assert "/api/sessions/" in STATUS_HTML and "/summary" in STATUS_HTML
    assert 'data-view="list"' in STATUS_HTML
    assert 'data-view="board"' in STATUS_HTML
    assert "openDossier" in STATUS_HTML
    assert "syncHashRoute" in STATUS_HTML
    assert "setDossierViewMode" in STATUS_HTML
    assert "is-hidden" in STATUS_HTML
    # Concept 1 stint scroll (#51) stays on the home view; dossier is history-only.
    assert 'id="stint"' in STATUS_HTML
    assert "refreshStint" in STATUS_HTML
    assert 'id="live-lap-list"' not in STATUS_HTML
