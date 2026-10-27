"""UI-only session title format: DD/MM/YY HH:MM hash4 car - track."""

from __future__ import annotations

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
