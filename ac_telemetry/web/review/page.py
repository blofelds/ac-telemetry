"""HTML document assembler for the /review session visualisations page."""

from __future__ import annotations

from collections.abc import Sequence

from ac_telemetry.runtime_info import short_git_sha
from ac_telemetry.web.review.helpers_js import REVIEW_HELPERS_JS
from ac_telemetry.web.review.shell_js import REVIEW_SHELL_JS
from ac_telemetry.web.review.styles_base import REVIEW_BASE_CSS
from ac_telemetry.web.review.styles_views import REVIEW_VIEWS_CSS

_REVIEW_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <link rel="icon" href="data:," />
  <title>Session Visualisations — AC Telemetry</title>
  <script>
    (function () {
      try {
        var saved = localStorage.getItem("ac_telemetry_review_theme");
        if (saved === "light") {
          document.documentElement.setAttribute("data-theme", "light");
        }
      } catch (e) { /* storage unavailable */ }
    })();
  </script>
  <style>
__REVIEW_CSS__
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <span class="brand-title">AC Telemetry</span>
        <span class="route-badge">/review</span>
      </div>
      <nav class="nav-group" aria-label="Main navigation">
        <a class="nav-link" href="/">Sessions (/)</a>
        <a class="nav-link" href="/accuracy">Accuracy (/accuracy)</a>
        <a class="nav-link active" href="/review" aria-current="page">Review (/review)</a>
        <button type="button" class="theme-btn" id="theme-toggle" aria-label="Toggle colour theme">
          Clean Light
        </button>
      </nav>
    </div>
  </header>

  <main class="container">
    <section class="filter-bar" aria-label="Session filters">
      <div class="filter-row">
        <select class="ctrl" id="filter-track" aria-label="Filter by track">
          <option value="All">All tracks</option>
        </select>

        <select class="ctrl" id="filter-car" aria-label="Filter by car">
          <option value="All">All cars</option>
        </select>

        <div class="seg-group" role="group" aria-label="Session type filter">
          <button type="button" class="seg-btn active" data-type="all">All</button>
          <button type="button" class="seg-btn" data-type="p">Practice (p)</button>
          <button type="button" class="seg-btn" data-type="r">Race (r)</button>
        </div>

        <input
          type="text"
          class="ctrl ctrl-search"
          id="filter-notes"
          aria-label="Search session and lap notes"
          placeholder='Search notes (e.g. "soft", "tyre", "traffic")'
          autocomplete="off"
        />

        <button type="button" class="btn-reset is-hidden" id="btn-reset">Reset</button>
      </div>

      <div class="toggle-row">
        <div class="toggle-group">
          <label class="chk-label" for="toggle-trim">
            <input type="checkbox" id="toggle-trim" checked />
            <span>Auto-trim outliers (&gt;107% of session best)</span>
            <span class="muted" id="trim-meta"></span>
          </label>

          <label class="chk-label" for="toggle-empty">
            <input type="checkbox" id="toggle-empty" checked />
            <span>Hide 0-lap sessions</span>
            <span class="muted" id="empty-meta"></span>
          </label>
        </div>

        <div class="status-meta" id="status-meta">Loading sessions…</div>
      </div>

      <div class="notice is-hidden" id="filter-notice" role="status" aria-live="polite"></div>
    </section>

    <div class="view-tabs" role="tablist" aria-label="Review visualisations">
      <button type="button" class="view-tab active" role="tab" aria-selected="true" data-view="overview">
        Overview &amp; PB Matrix
      </button>
      <button type="button" class="view-tab" role="tab" aria-selected="false" data-view="progression">
        Pace Progression
      </button>
      <button type="button" class="view-tab" role="tab" aria-selected="false" data-view="stints">
        Stint Comparison
      </button>
      <button type="button" class="view-tab" role="tab" aria-selected="false" data-view="pvr">
        Practice vs Race
      </button>
      <button type="button" class="view-tab" role="tab" aria-selected="false" data-view="activity">
        Activity
      </button>
    </div>

    <section id="review-root" aria-live="polite">
      <div class="card empty-state">Loading session visualisations…</div>
    </section>
  </main>

  <footer class="page-footer">
    <span>Session visualisations · reads existing sessions.csv &amp; laps.csv · no live capture polling</span>
    <code>ac-telemetry · /review · __GIT_SHA__</code>
  </footer>

  <script>
__REVIEW_JS__
    window.REVIEW_BOOT();
  </script>
</body>
</html>
"""

_VIEW_SCRIPTS: tuple[str, ...] = ()


def build_review_html(extra_scripts: Sequence[str] = ()) -> str:
    """Assemble the complete ``/review`` HTML document with registered view scripts."""
    css = REVIEW_BASE_CSS + "\n" + REVIEW_VIEWS_CSS
    scripts = "\n\n".join(
        s for s in (REVIEW_HELPERS_JS, REVIEW_SHELL_JS, *extra_scripts) if s
    )
    return (
        _REVIEW_TEMPLATE.replace("__REVIEW_CSS__", css)
        .replace("__REVIEW_JS__", scripts)
        .replace("__GIT_SHA__", short_git_sha())
    )


REVIEW_HTML = build_review_html(_VIEW_SCRIPTS)
