"""Practice vs Race signed pace-delta inline-SVG bar chart and breakdown view."""

from __future__ import annotations

REVIEW_PVR_JS = r"""
(function () {
  function renderPracticeVsRaceView(root, state, helpers) {
    const esc = helpers.escapeHtml;
    const palette = helpers.getThemePalette();
    const pvr = (state.payload && state.payload.practice_vs_race) || [];
    const summary = (state.payload && state.payload.summary) || {};

    if (!pvr.length) {
      root.innerHTML =
        '<div class="card empty-state">' +
        "<strong>No combos with both Practice (p) and Race (r) sessions</strong>" +
        "Record both Practice and Race stints for the same Track and Car, or set the type filter to All." +
        "</div>";
      return;
    }

    const rowsHtml = pvr
      .map((c) => {
        const pIqr = c.practice_iqr_ms != null ? (c.practice_iqr_ms / 1000).toFixed(2) + "s" : "--";
        const rIqr = c.race_iqr_ms != null ? (c.race_iqr_ms / 1000).toFixed(2) + "s" : "--";
        const deltaCls = c.best_delta_ms <= 600 ? "delta-fast" : "delta-slow";
        return (
          '<tr class="clickable" data-track="' + esc(c.track) + '" data-car="' + esc(c.car) + '">' +
            "<td>" +
              '<div style="font-weight:600">' + esc(c.track) + "</div>" +
              '<div class="muted" style="font-size:11px">' +
                esc(c.car) +
                (c.legacy_count > 0 ? " · " + c.legacy_count + " legacy as p" : "") +
              "</div>" +
            "</td>" +
            "<td>" +
              '<div style="font-weight:600;color:var(--accent)">' + esc(c.practice_best_time) + "</div>" +
              '<div class="muted" style="font-size:11px">med ' + esc(c.practice_median_time) + "</div>" +
            "</td>" +
            "<td>" +
              '<div style="font-weight:600;color:var(--amber)">' + esc(c.race_best_time) + "</div>" +
              '<div class="muted" style="font-size:11px">med ' + esc(c.race_median_time) + "</div>" +
            "</td>" +
            '<td class="' + deltaCls + '">' + esc(c.best_delta_text) + "</td>" +
            '<td class="hide-phone muted">' + esc(pIqr + " / " + rIqr) + "</td>" +
            "<td>" + esc(c.practice_laps + " / " + c.race_laps) + "</td>" +
          "</tr>"
        );
      })
      .join("");

    root.innerHTML =
      '<div class="stack">' +
        '<div class="card">' +
          '<div class="sec-head">' +
            "<div>" +
              '<div class="sec-title">Race Minus Practice Pace Delta by Track &amp; Car (seconds)</div>' +
              '<div class="sec-sub">' +
                "Positive values = Race slower than Practice (traffic, fuel, tyre management) · " +
                esc(summary.legacy_blank_count || 0) +
                " legacy rows with blank <code>session_type</code> grouped under Practice (p)" +
              "</div>" +
            "</div>" +
          "</div>" +
          '<div id="pvr-chart"></div>' +
        "</div>" +

        '<div class="card">' +
          '<div class="sec-head">' +
            '<div class="sec-title">Practice (p) vs Race (r) Pace &amp; Consistency Breakdown</div>' +
            '<div class="sec-caption">Click any row to open its Pace Progression · lap times in m:ss.sss</div>' +
          "</div>" +
          '<div class="table-wrap">' +
            '<table class="review-table" id="pvr-table">' +
              "<thead><tr>" +
                "<th>Track &amp; Car</th>" +
                "<th>Practice PB / Med</th>" +
                "<th>Race PB / Med</th>" +
                "<th>PB Delta</th>" +
                '<th class="hide-phone">IQR (P vs R)</th>' +
                "<th>Laps (P / R)</th>" +
              "</tr></thead>" +
              "<tbody>" + rowsHtml + "</tbody>" +
            "</table>" +
          "</div>" +
        "</div>" +
      "</div>";

    const fmtSignedAxis = (v) => (v >= 0 ? "+" : "-") + Math.abs(v).toFixed(2) + "s";
    const fmtSignedVal = (v) => (v >= 0 ? "+" : "-") + Math.abs(v).toFixed(3) + "s";

    window.REVIEW_SVG.mountInteractiveBarPlot(
      root.querySelector("#pvr-chart"),
      {
        categories: pvr.map((c) => c.short_label),
        series: [
          {
            id: "bestDelta",
            name: "Best Lap Delta (Race - Practice)",
            color: palette.accent,
            values: pvr.map((c) => Number((c.best_delta_ms / 1000).toFixed(3))),
          },
          {
            id: "medDelta",
            name: "Median Pace Delta (Race - Practice)",
            color: palette.amber,
            values: pvr.map((c) =>
              c.median_delta_ms != null ? Number((c.median_delta_ms / 1000).toFixed(3)) : 0
            ),
          },
        ],
        stacked: false,
        signed: true,
        yAxisLabel: "Race - Practice Delta (s)",
        xAxisLabel: "Track & Car Combo",
        formatY: fmtSignedAxis,
        formatVal: fmtSignedVal,
        caption:
          "Source: sessions.csv + laps.csv · Delta = Race minus Practice in seconds across " +
          pvr.length + " combo" + (pvr.length === 1 ? "" : "s") + " with both session types.",
      },
      helpers
    );

    root.querySelectorAll("#pvr-table tbody tr[data-track]").forEach((tr) => {
      tr.addEventListener("click", () => {
        helpers.drillIntoCombo(tr.getAttribute("data-track"), tr.getAttribute("data-car"), null);
      });
    });
  }

  window.REVIEW_VIEW_RENDERERS = Object.assign(window.REVIEW_VIEW_RENDERERS || {}, {
    pvr: renderPracticeVsRaceView,
  });
})();
""".strip()
