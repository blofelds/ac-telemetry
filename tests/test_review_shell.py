"""Tests for the /review HTML shell, Dark/Clean Light themes, and global filters."""

from __future__ import annotations

from ac_telemetry.web.review import REVIEW_HTML


def test_review_shell_theme_palette_and_persistence() -> None:
    assert "Session Visualisations" in REVIEW_HTML
    for hex_val in ("#0b0e14", "#141923", "#232c3d", "#3b82f6", "#10b981", "#f59e0b"):
        assert hex_val in REVIEW_HTML
    assert 'data-theme="light"' in REVIEW_HTML
    assert "ac_telemetry_review_theme" in REVIEW_HTML
    assert "localStorage" in REVIEW_HTML
    assert 'id="theme-toggle"' in REVIEW_HTML
    assert 'rel="icon"' in REVIEW_HTML


def test_review_shell_filters_tabs_navigation_and_british_spelling() -> None:
    for marker in (
        'id="filter-track"',
        'id="filter-car"',
        'id="filter-notes"',
        'id="btn-reset"',
        'id="toggle-trim"',
        'id="toggle-empty"',
        'data-view="overview"',
        'data-view="progression"',
        'data-view="stints"',
        'data-view="pvr"',
        'data-view="activity"',
        'href="/"',
        'href="/accuracy"',
        'href="/review"',
        "/api/review",
        "window.REVIEW_BOOT()",
    ):
        assert marker in REVIEW_HTML
    assert "__REVIEW_CSS__" not in REVIEW_HTML
    assert "__REVIEW_JS__" not in REVIEW_HTML
    assert "__GIT_SHA__" not in REVIEW_HTML
    assert "tyre" in REVIEW_HTML
    assert "tire" not in REVIEW_HTML.lower()
