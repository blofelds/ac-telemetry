"""Tests for the /review HTML shell, Dark/Clean Light themes, and global filters."""

from __future__ import annotations

from ac_telemetry.web.review import REVIEW_HTML
from ac_telemetry.web.review.shell_js import REVIEW_SHELL_JS
from ac_telemetry.web.review.styles_base import REVIEW_BASE_CSS


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


def test_review_filter_bar_loading_notification_markup_and_styles() -> None:
    filter_start = REVIEW_HTML.index('<section class="filter-bar"')
    filter_end = REVIEW_HTML.index("</section>", filter_start)
    filter_section = REVIEW_HTML[filter_start:filter_end]

    notice_idx = filter_section.index('id="filter-notice"')
    load_marker = '<div class="load-status" id="load-status" role="status" aria-live="polite"></div>'
    load_idx = filter_section.index(load_marker)
    assert load_idx > notice_idx

    for css_marker in (
        ".filter-bar {\n      position: relative;",
        ".load-status {",
        "top: 100%;",
        "color: var(--text-muted);",
        "min-height: 1.2em;",
        "white-space: nowrap;",
        ".load-status { left: 10px; }",
    ):
        assert css_marker in REVIEW_BASE_CSS


def test_review_shell_loading_state_js_wiring() -> None:
    assert "function setLoadStatus(text)" in REVIEW_SHELL_JS
    assert '$("load-status")' in REVIEW_SHELL_JS
    start_idx = REVIEW_SHELL_JS.index('setLoadStatus("Loading…");')
    fetch_idx = REVIEW_SHELL_JS.index('await fetch("/api/review?"')
    clear_idx = REVIEW_SHELL_JS.index('if (seq === fetchSeq) setLoadStatus("");')
    finally_idx = REVIEW_SHELL_JS.index("} finally {")
    assert start_idx < fetch_idx < finally_idx < clear_idx
