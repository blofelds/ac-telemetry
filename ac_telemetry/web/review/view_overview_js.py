"""Overview KPI tiles, Track & Car PB leaderboard matrix, and recent sessions view."""

from __future__ import annotations

REVIEW_OVERVIEW_JS = r"""
(function () {
  function renderOverviewView(root, state, helpers) {
    const esc = helpers.escapeHtml;
    const data = state.payload;
    if (!data) return;
    const summary = data.summary || {};
    const combos = data.combos || [];
    const sessions = data.sessions || [];

    if ((summary.total_sessions || 0) === 0) {
      root.innerHTML =
        '<div class="card empty-state">' +
        "<strong>No sessions recorded yet</strong>" +
        'Start a session on <a href="/">the rig page (/)</a> to populate <code>sessions.csv</code> and <code>laps.csv</code>.' +
        "</div>";
      return;
    }

    const topCombo = combos[0] || null;
    const recent = sessions.slice().reverse().slice(0, 8);

    const kpiHtml =
      '<div class="kpi-grid">' +
        '<div class="kpi-tile">' +
          '<div class="kpi-label">Sessions in view</div>' +
          '<div class="kpi-value">' + esc(summary.session_count || 0) + "</div>" +
          '<div class="kpi-sub">' + esc(summary.gt_confirmed_count || 0) + " GT-confirmed stints</div>" +
        "</div>" +
        '<div class="kpi-tile">' +
          '<div class="kpi-label">' + (state.trimOutliers ? "Clean laps (&lt;=107%)" : "Recorded laps (raw)") + "</div>" +
          '<div class="kpi-value">' + esc(summary.visible_laps || 0) + "</div>" +
          '<div class="kpi-sub">' +
            esc(summary.outlier_count || 0) +
            (state.trimOutliers ? " out/spin/traffic laps trimmed" : " outlier laps included") +
          "</div>" +
        "</div>" +
        '<div class="kpi-tile">' +
          '<div class="kpi-label">Most driven combo</div>' +
          '<div class="kpi-value accent-green">' + esc(topCombo ? topCombo.pb_time : "--:--.---") + "</div>" +
          '<div class="kpi-sub">' +
            (topCombo ? esc(topCombo.track + " · " + topCombo.car) : "No timed laps in view") +
          "</div>" +
        "</div>" +
        '<div class="kpi-tile">' +
          '<div class="kpi-label">Track / Car combos</div>' +
          '<div class="kpi-value">' + esc(combos.length) + "</div>" +
          '<div class="kpi-sub">' + esc(summary.pvr_combo_count || 0) + " with both Practice &amp; Race</div>" +
        "</div>" +
      "</div>";

    let matrixRowsHtml = "";
    if (!combos.length) {
      matrixRowsHtml = '<tr><td colspan="7" class="muted">No combos in current filter view.</td></tr>';
    } else {
      matrixRowsHtml = combos.map((row) => {
        const active = state.track === row.track && state.car === row.car;
        const deltaHtml =
          row.pvr_delta_ms == null
            ? '<span class="muted">Practice only</span>'
            : '<span class="' + (row.pvr_delta_ms <= 600 ? "delta-fast" : "delta-slow") + '">' +
                esc(row.pvr_delta_text) +
              "</span>";
        const gtHtml =
          row.gt_count > 0
            ? '<span class="delta-fast">' + esc(row.gt_count + "/" + row.session_count) + "</span>"
            : '<span class="muted">0</span>';
        return (
          '<tr class="clickable' + (active ? " active-row" : "") + '"' +
            ' data-track="' + esc(row.track) + '"' +
            ' data-car="' + esc(row.car) + '">' +
            "<td>" +
              '<div style="font-weight:600">' + esc(row.track) + "</div>" +
              '<div class="muted" style="font-size:11px">' +
                esc(row.car + " · last " + row.last_date) +
              "</div>" +
            "</td>" +
            '<td class="pb-cell">' + esc(row.pb_time) + "</td>" +
            '<td class="hide-phone">' + esc(row.recent_median_time) + "</td>" +
            "<td>" + deltaHtml + "</td>" +
            "<td>" + esc(row.session_count) + "</td>" +
            "<td>" + esc(row.lap_count) + "</td>" +
            '<td class="hide-phone">' + gtHtml + "</td>" +
          "</tr>"
        );
      }).join("");
    }

    const matrixCardHtml =
      '<div class="card">' +
        '<div class="sec-head">' +
          "<div>" +
            '<div class="sec-title">Track &amp; Car PB Leaderboard</div>' +
            '<div class="sec-sub">Click any combo row to drill into Pace Progression for that track and car.</div>' +
          "</div>" +
          '<div class="sec-caption">Source: sessions.csv + laps.csv · lap times in m:ss.sss</div>' +
        "</div>" +
        '<div class="table-wrap">' +
          '<table class="review-table" id="pb-leaderboard">' +
            "<thead><tr>" +
              "<th>Track &amp; Car</th>" +
              "<th>All-time PB</th>" +
              '<th class="hide-phone">Recent median</th>' +
              "<th>Race vs Practice PB</th>" +
              "<th>Sessions</th>" +
              "<th>Laps</th>" +
              '<th class="hide-phone">GT</th>' +
            "</tr></thead>" +
            "<tbody>" + matrixRowsHtml + "</tbody>" +
          "</table>" +
        "</div>" +
      "</div>";

    const recentItemsHtml = !recent.length
      ? '<div class="muted" style="font-size:12.5px">No sessions in current filter view.</div>'
      : recent.map((s) => {
          const lapStr =
            state.trimOutliers && s.outlier_count > 0
              ? s.visible_lap_count + "/" + s.lap_count
              : String(s.visible_lap_count);
          const emptyTag = s.lap_count === 0 ? '<span class="badge-empty">0 laps</span>' : "";
          const gtTag = s.gt_confirmed ? helpers.renderGtBadge() : "";
          return (
            '<button type="button" class="session-item"' +
              ' data-sid="' + esc(s.session_id) + '"' +
              ' data-track="' + esc(s.track) + '"' +
              ' data-car="' + esc(s.car) + '">' +
              '<div class="session-item-main">' +
                '<div class="session-item-head">' +
                  '<span class="session-item-title">' +
                    esc(s.date_label + " · " + s.track + " · " + s.car) +
                  "</span>" +
                  helpers.renderTypePill(s.effective_type, s.is_legacy_blank_type) +
                  gtTag +
                  emptyTag +
                "</div>" +
                '<div class="session-item-notes">' +
                  esc(s.notes || "No session notes") +
                "</div>" +
              "</div>" +
              '<div class="session-item-metrics">' +
                '<div class="metric-col">' +
                  '<div class="m-label">Best</div>' +
                  '<div class="m-val' + (s.best_ms != null ? " best" : "") + '">' +
                    esc(s.best_time) +
                  "</div>" +
                "</div>" +
                '<div class="metric-col">' +
                  '<div class="m-label">Median</div>' +
                  '<div class="m-val">' + esc(s.median_time) + "</div>" +
                "</div>" +
                '<div class="metric-col">' +
                  '<div class="m-label">Laps</div>' +
                  '<div class="m-val">' + esc(lapStr) + "</div>" +
                "</div>" +
              "</div>" +
            "</button>"
          );
        }).join("");

    const recentCardHtml =
      '<div class="card">' +
        '<div class="sec-head">' +
          '<div class="sec-title">Recent Sessions &amp; Notes</div>' +
          '<div class="sec-caption">Click a session to inspect its progression and laps</div>' +
        "</div>" +
        '<div class="session-list" id="recent-sessions">' + recentItemsHtml + "</div>" +
      "</div>";

    root.innerHTML = '<div class="stack">' + kpiHtml + matrixCardHtml + recentCardHtml + "</div>";

    root.querySelectorAll("#pb-leaderboard tbody tr[data-track]").forEach((tr) => {
      tr.addEventListener("click", () => {
        helpers.drillIntoCombo(tr.getAttribute("data-track"), tr.getAttribute("data-car"), null);
      });
    });

    root.querySelectorAll("#recent-sessions .session-item[data-sid]").forEach((btn) => {
      btn.addEventListener("click", () => {
        helpers.drillIntoCombo(
          btn.getAttribute("data-track"),
          btn.getAttribute("data-car"),
          btn.getAttribute("data-sid")
        );
      });
    });
  }

  window.REVIEW_VIEW_RENDERERS = Object.assign(window.REVIEW_VIEW_RENDERERS || {}, {
    overview: renderOverviewView,
  });
})();
""".strip()
