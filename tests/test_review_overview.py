"""Tests for the Overview KPI tiles, PB leaderboard, and recent sessions view."""

from __future__ import annotations

from ac_telemetry.web.review import REVIEW_HTML
from ac_telemetry.web.review.view_overview_js import REVIEW_OVERVIEW_JS


def test_overview_view_registered_with_kpis_leaderboard_and_recent_sessions() -> None:
    assert "overview: renderOverviewView" in REVIEW_OVERVIEW_JS
    assert "renderOverviewView" in REVIEW_HTML
    for marker in (
        "Sessions in view",
        "Most driven combo",
        "Track &amp; Car PB Leaderboard",
        'id="pb-leaderboard"',
        "All-time PB",
        "Recent median",
        "Race vs Practice PB",
        "Recent Sessions &amp; Notes",
        'id="recent-sessions"',
        "drillIntoCombo",
    ):
        assert marker in REVIEW_OVERVIEW_JS
    assert "tire" not in REVIEW_OVERVIEW_JS.lower()
