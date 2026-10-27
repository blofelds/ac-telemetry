"""UI-only session title format: DD/MM/YY HH:MM hash4 car - track."""

from __future__ import annotations

from pathlib import Path

from ac_telemetry.web.session_title import (
    DISPLAY_TIMEZONE,
    SESSION_TITLE_JS,
    format_session_stamp,
    format_session_title,
)


def test_display_timezone_is_europe_london() -> None:
    # No app-wide session-display TZ convention; London is the UI default.
    assert DISPLAY_TIMEZONE == "Europe/London"
    assert "Europe/London" in SESSION_TITLE_JS
    assert "function formatSessionTitle" in SESSION_TITLE_JS


def test_format_session_title_example_bst() -> None:
    # 13:05 UTC in July → 14:05 Europe/London (BST).
    title = format_session_title(
        {
            "session_id": "a3f9c812dead",
            "started_at": "2026-07-01T13:05:00+00:00",
            "car": "Audi R8 LMS",
            "track": "Brands Hatch",
        }
    )
    assert title == "01/07/26 14:05 a3f9 Audi R8 LMS - Brands Hatch"


def test_format_session_title_winter_gmt() -> None:
    # Late October after BST ends: UTC and London match.
    title = format_session_title(
        {
            "session_id": "deadbeef0001",
            "started_at": "2026-10-27T14:05:00+00:00",
            "car": "Ferrari 488 GT3",
            "track": "Monza",
        }
    )
    assert title == "27/10/26 14:05 dead Ferrari 488 GT3 - Monza"


def test_format_session_title_accepts_zulu_and_id_alias() -> None:
    title = format_session_title(
        {
            "id": "abcd1234",
            "started_at": "2026-01-15T09:30:00Z",
            "car": "Porsche",
            "track": "Spa",
        }
    )
    assert title == "15/01/26 09:30 abcd Porsche - Spa"


def test_format_session_title_missing_fields_keep_shape() -> None:
    title = format_session_title({"session_id": "xy"})
    assert title == f"--/--/-- --:-- xy — - —"


def test_format_session_stamp_naive_iso_treated_as_utc() -> None:
    assert format_session_stamp("2026-03-01T12:00:00") == "01/03/26 12:00"


def test_shared_js_helper_embedded_in_phone_and_accuracy_ui() -> None:
    from ac_telemetry.web import STATUS_HTML
    from ac_telemetry.web.accuracy import ACCURACY_HELPER_HTML

    for html in (STATUS_HTML, ACCURACY_HELPER_HTML):
        assert "formatSessionTitle" in html
        assert "Europe/London" in html
        # Placeholder must be expanded; raw marker must not leak into pages.
        assert "/*__SESSION_TITLE_JS__*/" not in html


def test_phone_history_and_accuracy_picker_call_formatter() -> None:
    from ac_telemetry.web import STATUS_HTML
    from ac_telemetry.web.accuracy import ACCURACY_HELPER_HTML

    assert "formatSessionTitle(s)" in STATUS_HTML
    assert "formatSessionTitle(s)" in ACCURACY_HELPER_HTML
    # Old label shapes should no longer drive the title/option text.
    assert '(s.track || "—") + " · " + (s.car || "—")' not in STATUS_HTML
    assert "[track, car].filter(Boolean).join" not in ACCURACY_HELPER_HTML


def test_api_session_list_fields_unchanged(tmp_path: Path) -> None:
    """Prefix is display-only — JSON still exposes raw session fields."""
    from fastapi.testclient import TestClient

    from ac_telemetry.api import create_app
    from ac_telemetry.capture import CaptureService
    from ac_telemetry.settings import load_settings
    from ac_telemetry.store import SessionStore

    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    store = SessionStore(settings.data_dir)
    store.ensure()
    capture = CaptureService(settings=settings)
    app = create_app(settings, capture, store)
    client = TestClient(app)
    created = client.post(
        "/api/sessions",
        json={"track": "Brands Hatch", "car": "Audi R8 LMS", "notes": ""},
    )
    assert created.status_code == 201
    session = created.json()["session"]
    listed = client.get("/api/sessions?limit=5").json()["sessions"][0]
    assert listed["session_id"] == session["session_id"]
    assert listed["car"] == "Audi R8 LMS"
    assert listed["track"] == "Brands Hatch"
    assert "display_title" not in listed
    assert "title" not in listed
    csv_text = (settings.data_dir / "sessions.csv").read_text(encoding="utf-8")
    assert "Audi R8 LMS" in csv_text
    assert "01/07/26" not in csv_text
