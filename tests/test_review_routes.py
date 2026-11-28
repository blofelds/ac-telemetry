"""Route, API query filtering, and navigation link tests for /review."""

from __future__ import annotations

import csv
from pathlib import Path

from fastapi.testclient import TestClient

from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.settings import load_settings
from ac_telemetry.store import LAP_FIELDS, SESSION_FIELDS, LapStore, SessionStore
from ac_telemetry.web import STATUS_HTML
from ac_telemetry.web.accuracy import ACCURACY_HELPER_HTML
from ac_telemetry.web.review import REVIEW_HTML


def _client(tmp_path: Path) -> tuple[TestClient, SessionStore, LapStore]:
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    store = SessionStore(settings.data_dir)
    store.ensure()
    lap_store = LapStore(settings.data_dir)
    lap_store.ensure()
    capture = CaptureService(settings=settings)
    app = create_app(settings, capture, store, lap_store=lap_store)
    return TestClient(app), store, lap_store


def _seed_sample_csv(data_dir: Path) -> None:
    with (data_dir / "sessions.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SESSION_FIELDS)
        w.writeheader()
        w.writerow(
            {
                **{k: "" for k in SESSION_FIELDS},
                "session_id": "s_legacy",
                "started_at": "2026-10-14T19:15:00+00:00",
                "track": "Vallelunga",
                "car": "Porsche 911 GT3 R",
                "notes": "baseline, medium tyres",
                "session_type": "",
                "status": "stopped",
            }
        )
        w.writerow(
            {
                **{k: "" for k in SESSION_FIELDS},
                "session_id": "s_race",
                "started_at": "2026-10-24T18:40:00+00:00",
                "track": "Vallelunga",
                "car": "Porsche 911 GT3 R",
                "notes": "12-lap sprint race",
                "session_type": "r",
                "status": "stopped",
            }
        )
        w.writerow(
            {
                **{k: "" for k in SESSION_FIELDS},
                "session_id": "s_zero",
                "started_at": "2026-10-25T18:00:00+00:00",
                "track": "Monza",
                "car": "Ferrari 488 GT3",
                "notes": "aborted capture",
                "session_type": "p",
                "status": "stopped",
            }
        )
    with (data_dir / "laps.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LAP_FIELDS)
        w.writeheader()
        for sid, n, ms, note in (
            ("s_legacy", 1, 105_000, "out-lap, cold tyres"),
            ("s_legacy", 2, 95_000, "gt_confirmed"),
            ("s_legacy", 3, 95_400, "gt_confirmed"),
            ("s_race", 1, 95_800, "race start traffic"),
            ("s_race", 2, 95_500, ""),
        ):
            w.writerow(
                {
                    "session_id": sid,
                    "lap_number": str(n),
                    "lap_time": f"{ms // 60000}:{(ms % 60000) // 1000:02d}.{ms % 1000:03d}",
                    "lap_time_ms": str(ms),
                    "recorded_at": "2026-10-14T19:20:00+00:00",
                    "source": "mock",
                    "raw_text": "",
                    "note": note,
                }
            )


def test_nav_links_on_home_and_accuracy_pages() -> None:
    assert 'href="/review"' in STATUS_HTML
    assert 'href="/review"' in ACCURACY_HELPER_HTML
    assert 'href="/"' in REVIEW_HTML
    assert 'href="/accuracy"' in REVIEW_HTML


def test_review_route_and_api_filtering(tmp_path: Path) -> None:
    client, store, _lap_store = _client(tmp_path)

    page = client.get("/review")
    assert page.status_code == 200
    assert "Session Visualisations" in page.text

    empty_resp = client.get("/api/review")
    assert empty_resp.status_code == 200
    assert empty_resp.json()["summary"]["total_sessions"] == 0
    assert empty_resp.json()["combos"] == []

    _seed_sample_csv(store.data_dir)

    default_resp = client.get("/api/review").json()
    assert default_resp["summary"]["total_sessions"] == 3
    assert default_resp["summary"]["session_count"] == 2
    assert default_resp["summary"]["empty_session_count"] == 1
    assert default_resp["summary"]["outlier_count"] == 1
    assert default_resp["summary"]["visible_laps"] == 4
    assert default_resp["summary"]["raw_laps"] == 5
    assert default_resp["summary"]["gt_confirmed_count"] == 1
    assert default_resp["summary"]["legacy_blank_count"] == 1
    assert len(default_resp["combos"]) == 1
    assert default_resp["combos"][0]["pb_time"] == "1:35.000"
    assert default_resp["combos"][0]["pvr_delta_ms"] == 500

    raw_resp = client.get("/api/review?trim_outliers=false&hide_empty=false").json()
    assert raw_resp["summary"]["session_count"] == 3
    assert raw_resp["summary"]["visible_laps"] == 5

    p_resp = client.get("/api/review?session_type=p").json()
    assert [s["session_id"] for s in p_resp["sessions"]] == ["s_legacy"]
    r_resp = client.get("/api/review?session_type=r").json()
    assert [s["session_id"] for s in r_resp["sessions"]] == ["s_race"]

    q_lap = client.get("/api/review?q=traffic").json()
    assert [s["session_id"] for s in q_lap["sessions"]] == ["s_race"]
    q_sess = client.get("/api/review?q=tyres").json()
    assert [s["session_id"] for s in q_sess["sessions"]] == ["s_legacy"]
