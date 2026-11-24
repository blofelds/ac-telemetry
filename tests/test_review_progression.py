"""Tests for the Pace Progression SVG view on /review."""

from __future__ import annotations

from ac_telemetry.web.review import REVIEW_HTML
from ac_telemetry.web.review.view_progression_js import REVIEW_PROGRESSION_JS


def test_pace_progression_view_registered_with_axes_legend_and_detail() -> None:
    assert "progression: renderProgressionView" in REVIEW_PROGRESSION_JS
    assert "renderProgressionView" in REVIEW_HTML
    for marker in (
        "Session Best, Median &amp; Running PB Lap Time (m:ss.sss)",
        "Running PB",
        "Session Best",
        "Lap Time (m:ss)",
        "Session Date & Type (P / R)",
        "Sessions in Progression",
        "Session Detail",
        "IQR Spread",
        "selectInspectedSession",
    ):
        assert marker in REVIEW_PROGRESSION_JS
    assert "tire" not in REVIEW_PROGRESSION_JS.lower()
