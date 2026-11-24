"""Tests for the Practice vs Race SVG bar chart and breakdown view."""

from __future__ import annotations

from ac_telemetry.web.review import REVIEW_HTML
from ac_telemetry.web.review.view_pvr_js import REVIEW_PVR_JS


def test_practice_vs_race_view_registered_with_signed_chart_and_table() -> None:
    assert "pvr: renderPracticeVsRaceView" in REVIEW_PVR_JS
    assert "renderPracticeVsRaceView" in REVIEW_HTML
    for marker in (
        "Race Minus Practice Pace Delta by Track &amp; Car (seconds)",
        "Race - Practice Delta (s)",
        "Track & Car Combo",
        "Practice (p) vs Race (r) Pace &amp; Consistency Breakdown",
        'id="pvr-table"',
        "signed: true",
        "tyre",
    ):
        assert marker in REVIEW_PVR_JS
    assert "tire" not in REVIEW_PVR_JS.lower()
