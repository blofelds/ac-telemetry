"""UI-only session title formats: History A, dossier/current B, Accuracy A."""

from __future__ import annotations

from pathlib import Path

from ac_telemetry.web.session_title import (
    DISPLAY_TIMEZONE,
    SESSION_TITLE_JS,
    format_accuracy_session_title,
    format_session_hash4,
    format_session_identity,
    format_session_stamp,
    format_session_stamp_short,
    format_session_title,
)


def test_display_timezone_is_europe_london() -> None:
    # No app-wide session-display TZ convention; London is the UI default.
    assert DISPLAY_TIMEZONE == "Europe/London"
    assert "Europe/London" in SESSION_TITLE_JS
    assert "function formatSessionTitle" in SESSION_TITLE_JS
    assert "function formatAccuracySessionTitle" in SESSION_TITLE_JS
    assert "function formatSessionIdentity" in SESSION_TITLE_JS
    assert "function formatSessionStampShort" in SESSION_TITLE_JS
    assert "function formatSessionHash4" in SESSION_TITLE_JS
    assert "function sessionStamp" in SESSION_TITLE_JS
    assert "function sessionHash4" in SESSION_TITLE_JS


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


def test_format_session_identity_track_car() -> None:
    assert (
        format_session_identity(
            {"track": "Vallelunga Club", "car": "Abarth", "session_id": "a3f9"}
        )
        == "Vallelunga Club · Abarth"
    )
    assert format_session_hash4({"session_id": "a3f9c812dead"}) == "a3f9"


def test_format_session_identity_missing_parts() -> None:
    assert format_session_identity({}) == "— · —"
    assert format_session_identity({"track": "Monza"}) == "Monza · —"


def test_format_session_stamp_short_and_hash4() -> None:
    session = {
        "session_id": "a3f9c2e1b8d04f11",
        "started_at": "2026-11-22T14:05:00+00:00",
    }
    assert format_session_stamp_short(session["started_at"]) == "22/11 14:05"
    assert format_session_hash4(session) == "a3f9"
    assert format_session_stamp_short(None) == "--/-- --:--"
    assert format_session_hash4({}) == "----"


def test_format_session_stamp_naive_iso_treated_as_utc() -> None:
    assert format_session_stamp("2026-03-01T12:00:00") == "01/03/26 12:00"
    assert format_session_stamp_short("2026-03-01T12:00:00") == "01/03 12:00"


def test_format_accuracy_session_title_a_with_hash() -> None:
    # Accuracy A: track · car · DD/MM HH:MM · hash4 (hash before GT suffix).
    # 14:05 UTC on 22 Nov → 14:05 Europe/London (GMT).
    title = format_accuracy_session_title(
        {
            "session_id": "a3f9c2e1b8d04f11",
            "started_at": "2026-11-22T14:05:00+00:00",
            "car": "Abarth",
            "track": "Vallelunga Club",
        }
    )
    assert title == "Vallelunga Club · Abarth · 22/11 14:05 · a3f9"
    # Confirmed picker option appends the suffix after the hash.
    assert title + " · GT confirmed" == (
        "Vallelunga Club · Abarth · 22/11 14:05 · a3f9 · GT confirmed"
    )
    assert title + " · GT" == "Vallelunga Club · Abarth · 22/11 14:05 · a3f9 · GT"


def test_format_accuracy_session_title_bst_and_missing() -> None:
    # 13:05 UTC in July → 14:05 BST; short stamp drops the year.
    title = format_accuracy_session_title(
        {
            "session_id": "a3f9c812dead",
            "started_at": "2026-07-01T13:05:00+00:00",
            "car": "Audi R8 LMS",
            "track": "Brands Hatch",
        }
    )
    assert title == "Brands Hatch · Audi R8 LMS · 01/07 14:05 · a3f9"
    missing = format_accuracy_session_title({"session_id": "xy"})
    assert missing == "— · — · --/-- --:-- · xy"


def test_shared_js_helper_embedded_in_phone_and_accuracy_ui() -> None:
    from ac_telemetry.web import STATUS_HTML
    from ac_telemetry.web.accuracy import ACCURACY_HELPER_HTML

    for html in (STATUS_HTML, ACCURACY_HELPER_HTML):
        assert "formatSessionTitle" in html
        assert "formatAccuracySessionTitle" in html
        assert "formatSessionIdentity" in html
        assert "Europe/London" in html
        # Placeholder must be expanded; raw marker must not leak into pages.
        assert "/*__SESSION_TITLE_JS__*/" not in html


def test_phone_history_uses_layout_a_helpers() -> None:
    from ac_telemetry.web import STATUS_HTML

    history_fn = STATUS_HTML.split("function renderHistory(sessions)", 1)[1].split(
        "function escapeHtml", 1
    )[0]
    # History A: track · car title, demoted stamp/hash, live-only status cue.
    assert "formatSessionIdentity(s)" in history_fn
    assert "formatSessionStampShort(s.started_at)" in history_fn
    assert "formatSessionHash4(s)" in history_fn
    assert 'badge run\\">live' in history_fn
    assert 'badge stop\\">stopped' not in history_fn
    assert 'badge gt\\">GT</span>' in history_fn
    assert "formatSessionTitle(s)" not in history_fn


def test_accuracy_picker_uses_accuracy_a_formatter() -> None:
    from ac_telemetry.web import STATUS_HTML
    from ac_telemetry.web.accuracy import ACCURACY_HELPER_HTML

    assert "let label = formatAccuracySessionTitle(s);" in ACCURACY_HELPER_HTML
    # Accuracy picker A owns option text; do not fall back to phone History title.
    assert "let label = formatSessionTitle(s);" not in ACCURACY_HELPER_HTML
    assert "[track, car].filter(Boolean).join" not in ACCURACY_HELPER_HTML
    # Dossier B + Current B use brief track · car identity + LIVE badge.
    assert "formatSessionIdentity(session)" in STATUS_HTML
    assert 'class=\\"badge run\\">LIVE</span>' in STATUS_HTML
    assert "No session running." in STATUS_HTML


def test_current_strip_uses_brief_identity() -> None:
    from ac_telemetry.web import STATUS_HTML

    current_fn = STATUS_HTML.split("function renderCurrent(session)", 1)[1].split(
        "function prefillFromLastSession", 1
    )[0]
    assert "formatSessionIdentity(session)" in current_fn
    assert "sessionStamp(session)" in current_fn
    assert "sessionHash4(session)" in current_fn
    assert "LIVE" in current_fn
    assert "session.session_id +" not in current_fn
    assert "<strong>Running</strong>" not in current_fn


def test_dossier_header_uses_brief_identity() -> None:
    from ac_telemetry.web import STATUS_HTML

    dossier_fn = STATUS_HTML.split("function renderDossier(payload)", 1)[1].split(
        "async function loadDossier", 1
    )[0]
    assert "formatSessionIdentity(session)" in dossier_fn
    assert "sessionStamp(session)" in dossier_fn
    assert "sessionHash4(session)" in dossier_fn
    assert "GT confirmed" in dossier_fn
    assert "formatSessionTitle(session)" not in dossier_fn
    assert 'id="dossier-gt"' not in STATUS_HTML
    assert "session.started_at" not in dossier_fn
    assert "session.ended_at" not in dossier_fn
    assert '"id " +' not in dossier_fn


def test_api_session_list_fields_unchanged(tmp_path: Path) -> None:
    """Title layout is display-only — JSON still exposes raw session fields."""
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
