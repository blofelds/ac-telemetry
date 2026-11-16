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


def _append(store: LapStore, sid: str, n: int, ms: int | None) -> None:
    if ms is None:
        store.append_lap(
            {
                "session_id": sid,
                "lap_number": n,
                "lap_time": "",
                "lap_time_ms": "",
                "source": "mock",
                "raw_text": "",
            }
        )
        return
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


def test_format_delta_ms() -> None:
    assert LapStore.format_delta_ms(0) == "BEST"
    assert LapStore.format_delta_ms(320) == "+0.320"
    assert LapStore.format_delta_ms(1430) == "+1.430"
    assert LapStore.format_delta_ms(62_100) == "+1:02.100"
    assert LapStore.format_delta_ms(-50) == "-0.050"


def test_min_contiguous_avg_ms_basic() -> None:
    # Chronological times: pick the faster of two 5-lap windows.
    rows = [{"lap_time_ms": str(ms)} for ms in (100, 110, 120, 130, 140, 90, 91, 92, 93, 94)]
    # Window 0..4 avg = 120; window 5..9 avg = 92
    assert LapStore.min_contiguous_avg_ms(rows, 5) == 92
    assert LapStore.min_contiguous_avg_ms(rows, 10) == (
        sum(int(r["lap_time_ms"]) for r in rows) // 10
    )
    assert LapStore.min_contiguous_avg_ms(rows, 11) is None


def test_min_contiguous_avg_ms_invalid_breaks_window() -> None:
    rows = [
        {"lap_time_ms": "100"},
        {"lap_time_ms": "100"},
        {"lap_time_ms": ""},  # breaks contiguity
        {"lap_time_ms": "100"},
        {"lap_time_ms": "100"},
        {"lap_time_ms": "100"},
        {"lap_time_ms": "100"},
        {"lap_time_ms": "100"},
    ]
    # No fully-valid 5-lap window spanning the gap; only indices 3..7.
    assert LapStore.min_contiguous_avg_ms(rows, 5) == 100
    assert LapStore.min_contiguous_avg_ms(rows[:5], 5) is None


def test_summarize_session_best_and_pace(tmp_path: Path) -> None:
    store = LapStore(tmp_path / "sessions")
    store.ensure()
    sid = "sessdossier01"
    # 3 laps: pace fields stay null (need 5 / 10).
    for n, ms in ((1, 102_100), (2, 101_780), (3, 103_210)):
        _append(store, sid, n, ms)

    summary = store.summarize_session(sid)
    assert summary["lap_count"] == 3
    assert summary["timed_lap_count"] == 3
    assert summary["best_ms"] == 101_780
    assert summary["best_lap_number"] == "2"
    assert summary["best_lap_time"] == "1:41.780"
    assert summary["pace_5_ms"] is None
    assert summary["pace_5_lap_time"] is None
    assert summary["pace_10_ms"] is None
    assert summary["pace_10_lap_time"] is None
    assert "avg_ms" not in summary
    assert "spread_ms" not in summary
    # Newest-first
    assert [row["lap_number"] for row in summary["laps"]] == ["3", "2", "1"]
    by_n = {str(row["lap_number"]): row for row in summary["laps"]}
    assert by_n["2"]["is_best"] is True
    assert by_n["2"]["delta_text"] == "BEST"
    assert by_n["3"]["delta_ms"] == 103_210 - 101_780
    assert by_n["3"]["delta_text"] == "+1.430"


def test_summarize_session_contiguous_pace(tmp_path: Path) -> None:
    store = LapStore(tmp_path / "sessions")
    store.ensure()
    sid = "sesspace"
    # Slow first five, then a faster contiguous five, then one more.
    times = [
        110_000,
        111_000,
        112_000,
        113_000,
        114_000,  # window avg 112_000
        100_000,
        101_000,
        102_000,
        103_000,
        104_000,  # window avg 102_000 ← best 5
        105_000,
    ]
    for n, ms in enumerate(times, start=1):
        _append(store, sid, n, ms)

    summary = store.summarize_session(sid)
    assert summary["pace_5_ms"] == 102_000
    assert summary["pace_5_lap_time"] == "1:42.000"
    # Two 10-lap windows; laps 2..11 is faster than 1..10.
    assert summary["pace_10_ms"] == sum(times[1:11]) // 10
    assert summary["pace_10_ms"] == 106_500
    assert summary["pace_10_lap_time"] == "1:46.500"


def test_summarize_session_skips_invalid_times(tmp_path: Path) -> None:
    store = LapStore(tmp_path / "sessions")
    store.ensure()
    sid = "sessbad"
    _append(store, sid, 1, None)
    _append(store, sid, 2, 100_000)
    summary = store.summarize_session(sid)
    assert summary["lap_count"] == 2
    assert summary["timed_lap_count"] == 1
    assert summary["best_ms"] == 100_000
    assert summary["pace_5_ms"] is None
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
    for n, ms in ((1, 102_100), (2, 101_780)):
        _append(lap_store, sid, n, ms)

    resp = client.get(f"/api/sessions/{sid}/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session"]["track"] == "Monza"
    assert body["session"]["car"] == "488"
    assert body["session"]["notes"] == "set 1"
    assert body["summary"]["lap_count"] == 2
    assert body["summary"]["best_ms"] == 101_780
    assert body["summary"]["best_lap_time"] == "1:41.780"
    assert body["summary"]["pace_5_ms"] is None
    assert body["summary"]["pace_10_ms"] is None
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
    assert 'id="dossier-pace-5"' in STATUS_HTML
    assert 'id="dossier-pace-10"' in STATUS_HTML
    assert "5-lap pace" in STATUS_HTML
    assert "10-lap pace" in STATUS_HTML
    assert 'id="dossier-avg"' not in STATUS_HTML
    assert 'id="dossier-spread"' not in STATUS_HTML
    # Concept 1 stint scroll (#51) stays on the home view; dossier is history-only.
    assert 'id="stint"' in STATUS_HTML
    assert "refreshStint" in STATUS_HTML
    assert 'id="live-lap-list"' not in STATUS_HTML
