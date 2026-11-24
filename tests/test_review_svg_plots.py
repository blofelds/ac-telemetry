"""Tests for the reusable inline-SVG line and bar chart primitives."""

from __future__ import annotations

from ac_telemetry.web.review import REVIEW_HTML
from ac_telemetry.web.review.svg_bar_js import REVIEW_SVG_BAR_JS
from ac_telemetry.web.review.svg_line_js import REVIEW_SVG_LINE_JS


def test_inline_svg_primitives_embedded_without_external_chart_libs() -> None:
    assert "http://www.w3.org/2000/svg" in REVIEW_SVG_LINE_JS
    assert "mountInteractiveLinePlot" in REVIEW_HTML
    assert "mountInteractiveBarPlot" in REVIEW_HTML
    assert "chart-legend" in REVIEW_SVG_LINE_JS
    assert "chart-caption" in REVIEW_SVG_LINE_JS
    assert "chart-caption" in REVIEW_SVG_BAR_JS
    for forbidden in ("chart.js", "plotly", "echarts", "highcharts", "d3.min.js", "unpkg.com", "cdn.jsdelivr"):
        assert forbidden not in REVIEW_HTML.lower()
