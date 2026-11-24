"""Weekly Activity inline-SVG stacked bar charts (by track/car and Practice vs Race)."""

from __future__ import annotations

REVIEW_ACTIVITY_JS = r"""
(function () {
  function renderActivityView(root, state, helpers) {
    const esc = helpers.escapeHtml;
    const palette = helpers.getThemePalette();
    const colors = window.REVIEW_SVG.seriesPalette(palette);
    const activity = (state.payload && state.payload.activity) || { weeks: [] };
    const summary = (state.payload && state.payload.summary) || {};
    const weeks = activity.weeks || [];

    if (!weeks.length) {
      root.innerHTML =
        '<div class="card empty-state">' +
        "<strong>No weekly activity in current filter view</strong>" +
        "Reset filters or record timed laps to inspect weekly seat-time." +
        "</div>";
      return;
    }

    const groupBy = state.activityGroupBy === "car" ? "car" : "track";
    const groupCats = groupBy === "car" ? activity.cars || [] : activity.tracks || [];
    const weekLabels = weeks.map((w) => w.week_label);
    const spanCaption =
      weekLabels.length > 1
        ? weekLabels[0] + " to " + weekLabels[weekLabels.length - 1]
        : weekLabels[0];

    root.innerHTML =
      '<div class="stack">' +
        '<div class="card">' +
          '<div class="sec-head">' +
            "<div>" +
              '<div class="sec-title">Weekly Laps by ' + (groupBy === "car" ? "Car" : "Track") + " (laps)</div>" +
              '<div class="sec-sub">' +
                "Source: laps.csv · Weeks starting " + esc(spanCaption) + " · " +
                (state.trimOutliers ? "Trimmed clean laps (<=107%)" : "All raw laps") +
              "</div>" +
            "</div>" +
            '<div class="seg-group" role="group" aria-label="Group weekly laps">' +
              '<button type="button" class="seg-btn' + (groupBy === "track" ? " active" : "") + '" data-act-group="track">By Track</button>' +
              '<button type="button" class="seg-btn' + (groupBy === "car" ? " active" : "") + '" data-act-group="car">By Car</button>' +
            "</div>" +
          "</div>" +
          '<div id="activity-group-chart"></div>' +
        "</div>" +

        '<div class="card">' +
          '<div class="sec-head">' +
            "<div>" +
              '<div class="sec-title">Weekly Seat-Time: Practice (p) vs Race (r) Laps</div>' +
              '<div class="sec-sub">' +
                "Total: " + esc(activity.practice_total_laps || 0) + " practice laps · " +
                esc(activity.race_total_laps || 0) + " race laps across " +
                esc(summary.session_count || 0) + " sessions" +
              "</div>" +
            "</div>" +
          "</div>" +
          '<div id="activity-type-chart"></div>' +
        "</div>" +
      "</div>";

    window.REVIEW_SVG.mountInteractiveBarPlot(
      root.querySelector("#activity-group-chart"),
      {
        categories: weekLabels,
        series: groupCats.map((cat, idx) => ({
          id: cat,
          name: cat,
          color: colors[idx % colors.length],
          values: weeks.map((w) => {
            const map = groupBy === "car" ? w.by_car : w.by_track;
            return Number((map && map[cat]) || 0);
          }),
        })),
        stacked: true,
        signed: false,
        yAxisLabel: "Laps (count)",
        xAxisLabel: "Week Starting (Europe/London)",
        formatY: (v) => String(Math.round(v)),
        formatVal: (v) => v + " laps",
        caption:
          "Source: laps.csv · Stacked weekly lap count grouped by " +
          (groupBy === "car" ? "car" : "track") + " across " + weeks.length +
          " week" + (weeks.length === 1 ? "" : "s") + ".",
      },
      helpers
    );

    window.REVIEW_SVG.mountInteractiveBarPlot(
      root.querySelector("#activity-type-chart"),
      {
        categories: weekLabels,
        series: [
          {
            id: "practice",
            name: "Practice (p)",
            color: palette.accent,
            values: weeks.map((w) => Number(w.practice_laps || 0)),
          },
          {
            id: "race",
            name: "Race (r)",
            color: palette.amber,
            values: weeks.map((w) => Number(w.race_laps || 0)),
          },
        ],
        stacked: true,
        signed: false,
        yAxisLabel: "Laps (count)",
        xAxisLabel: "Week Starting (Europe/London)",
        formatY: (v) => String(Math.round(v)),
        formatVal: (v) => v + " laps",
        caption:
          "Source: sessions.csv + laps.csv · Weekly Practice (including legacy blank session_type) versus Race lap split.",
      },
      helpers
    );

    root.querySelectorAll("button[data-act-group]").forEach((btn) => {
      btn.addEventListener("click", () => {
        helpers.setActivityGroupBy(btn.getAttribute("data-act-group"));
      });
    });
  }

  window.REVIEW_VIEW_RENDERERS = Object.assign(window.REVIEW_VIEW_RENDERERS || {}, {
    activity: renderActivityView,
  });
})();
""".strip()
