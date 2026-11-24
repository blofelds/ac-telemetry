"""Tests for the Weekly Activity SVG view and complete 5-view registration."""

from __future__ import annotations

from ac_telemetry.web.review import REVIEW_HTML
from ac_telemetry.web.review.view_activity_js import REVIEW_ACTIVITY_JS


def test_activity_view_registered_with_track_car_toggle_and_type_split() -> None:
    assert "activity: renderActivityView" in REVIEW_ACTIVITY_JS
    assert "renderActivityView" in REVIEW_HTML
    for marker in (
        "Weekly Laps by ",
        "By Track",
        "By Car",
        "Laps (count)",
        "Week Starting (Europe/London)",
        "Weekly Seat-Time: Practice (p) vs Race (r) Laps",
        "setActivityGroupBy",
    ):
        assert marker in REVIEW_ACTIVITY_JS
    assert "tire" not in REVIEW_ACTIVITY_JS.lower()


def test_all_five_review_views_registered_in_final_html() -> None:
    for fn in (
        "renderOverviewView",
        "renderProgressionView",
        "renderStintComparisonView",
        "renderPracticeVsRaceView",
        "renderActivityView",
    ):
        assert fn in REVIEW_HTML
