"""Tests for the Stint Comparison SVG view on /review."""

from __future__ import annotations

from ac_telemetry.web.review import REVIEW_HTML
from ac_telemetry.web.review.view_stints_js import REVIEW_STINTS_JS


def test_stint_comparison_view_registered_with_overlay_bands_and_british_spelling() -> None:
    assert "stints: renderStintComparisonView" in REVIEW_STINTS_JS
    assert "renderStintComparisonView" in REVIEW_HTML
    for marker in (
        "Select 2 to 4 Stints to Overlay",
        "Lap-by-Lap Pace Overlay (Lap 1 to Lap N)",
        "Lap Time (m:ss)",
        "Lap Number in Stint (lap)",
        "Stint Consistency Band (Min · Q1 · Median · Q3 · Max)",
        "toggleCompareSession",
        "tyre",
    ):
        assert marker in REVIEW_STINTS_JS
    assert "tire" not in REVIEW_STINTS_JS.lower()
