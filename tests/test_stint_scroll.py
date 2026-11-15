"""Concept 1 stint scroll — Δ-to-best helpers + phone UI wiring."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.settings import load_settings
from ac_telemetry.store import LapStore, SessionStore
from ac_telemetry.web.stint_scroll import (
    format_delta_ms,
    parse_lap_ms,
    session_best_ms,
    stint_row_class,
)


def test_parse_and_best_and_delta() -> None:
    laps = [
        {"lap_number": "7", "lap_time": "1:42.100", "lap_time_ms": "102100"},
        {"lap_number": "6", "lap_time": "1:41.780", "lap_time_ms": "101780"},
        {"lap_number": "5", "lap_time": "1:43.210", "lap_time_ms": "103210"},
        {"lap_number": "4", "lap_time": "bad", "lap_time_ms": ""},
    ]
    assert parse_lap_ms(laps[0]) == 102100
    assert parse_lap_ms(laps[3]) is None
    assert session_best_ms(laps) == 101780
    assert format_delta_ms(0) == "BEST"
    assert format_delta_ms(320) == "+0.32"
    assert format_delta_ms(1430) == "+1.43"
    assert format_delta_ms(-100) == "\u22120.10"


def test_stint_row_class_best_and_outlier() -> None:
    best = 101780
    assert stint_row_class(best, best) == "best"
    assert stint_row_class(102100, best) == ""
    # ≥1.5× best → grey (pit / traffic)
    assert stint_row_class(int(best * 1.5), best) == "outlier"
    assert stint_row_class(None, best) == "outlier"


def test_status_html_stint_scroll_wired() -> None:
    from ac_telemetry.web import STATUS_HTML

    assert 'id="stint"' in STATUS_HTML
    assert "renderStint" in STATUS_HTML
    assert "refreshStint" in STATUS_HTML
    assert "/api/laps?session_id=" in STATUS_HTML
    assert "formatDeltaMs" in STATUS_HTML
    assert "sessionBestMs" in STATUS_HTML
    assert "stintRowClass" in STATUS_HTML
    assert "li.best" in STATUS_HTML
    assert "li.outlier" in STATUS_HTML


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


def test_api_laps_filtered_for_stint_scroll(tmp_path: Path) -> None:
    """Phone stint list relies on session-scoped /api/laps (newest-first)."""
    client, lap_store = _client(tmp_path)
    created = client.post(
        "/api/sessions",
        json={"track": "Monza", "car": "Ferrari"},
    )
    assert created.status_code == 201
    sid = created.json()["session"]["session_id"]

    lap_store.append_lap(
        {
            "session_id": sid,
            "lap_number": 1,
            "lap_time": "1:42.100",
            "lap_time_ms": 102100,
            "source": "test",
        }
    )
    lap_store.append_lap(
        {
            "session_id": sid,
            "lap_number": 2,
            "lap_time": "1:41.780",
            "lap_time_ms": 101780,
            "source": "test",
        }
    )
    lap_store.append_lap(
        {
            "session_id": "other",
            "lap_number": 9,
            "lap_time": "1:40.000",
            "lap_time_ms": 100000,
            "source": "test",
        }
    )

    payload = client.get(f"/api/laps?session_id={sid}&limit=100").json()
    laps = payload["laps"]
    assert len(laps) == 2
    assert laps[0]["lap_number"] == "2" or int(laps[0]["lap_number"]) == 2
    assert session_best_ms(laps) == 101780
    assert format_delta_ms(int(laps[1]["lap_time_ms"]) - 101780) == "+0.32"
