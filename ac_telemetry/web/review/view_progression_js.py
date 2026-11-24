"""Pace Progression inline-SVG view with notes hover readouts and session detail."""

from __future__ import annotations

REVIEW_PROGRESSION_JS = r"""
(function () {
  function renderProgressionView(root, state, helpers) {
    const esc = helpers.escapeHtml;
    const palette = helpers.getThemePalette();
    const combo = helpers.getActiveCombo();
    const comboSessions = helpers.getActiveComboSessions();
    const combos = (state.payload && state.payload.combos) || [];

    if (!combo || !comboSessions.length) {
      root.innerHTML =
        '<div class="card empty-state">' +
        "<strong>No timed sessions for Pace Progression</strong>" +
        "Select a Track and Car with timed laps or reset filters above." +
        "</div>";
      return;
    }

    const firstBest = comboSessions[0].best_ms;
    const latestBest = comboSessions[comboSessions.length - 1].best_ms;
    const gainMs = firstBest != null && latestBest != null ? latestBest - firstBest : null;

    const quickChips = combos
      .slice(0, 4)
      .map((c) => {
        const active = c.key === combo.key;
        return (
          '<button type="button" class="chip-btn' + (active ? " active" : "") + '"' +
          ' data-track="' + esc(c.track) + '" data-car="' + esc(c.car) + '">' +
          esc(c.track.split(" ")[0] + " · " + c.car.split(" ")[0]) +
          "</button>"
        );
      })
      .join("");

    const inspected =
      comboSessions.find((s) => s.session_id === state.inspectedSessionId) ||
      comboSessions[comboSessions.length - 1];

    const sessionListHtml = comboSessions
      .map((s) => {
        const selected = inspected && inspected.session_id === s.session_id;
        return (
          '<button type="button" class="session-item" data-inspect-sid="' + esc(s.session_id) + '"' +
          ' style="' + (selected ? "border-color:var(--accent);background:var(--accent-soft)" : "") + '">' +
          '<div class="session-item-main">' +
            '<div class="session-item-head">' +
              '<span class="session-item-title">' + esc(s.date_label) + "</span>" +
              helpers.renderTypePill(s.effective_type, s.is_legacy_blank_type) +
              (s.gt_confirmed ? helpers.renderGtBadge() : "") +
            "</div>" +
            '<div class="session-item-notes">' + esc(s.notes || "No session notes") + "</div>" +
          "</div>" +
          '<div class="pb-cell" style="font-size:12.5px">' + esc(s.best_time) + "</div>" +
          "</button>"
        );
      })
      .join("");

    const lapsHtml = (inspected.laps || [])
      .map((lap) => {
        const hiddenByTrim = state.trimOutliers && lap.is_outlier;
        const cls = "lap-row" + (lap.is_best ? " best" : "") + (hiddenByTrim ? " trimmed" : "");
        const timeColor = lap.is_best
          ? "color:var(--green);font-weight:700"
          : lap.is_outlier
            ? "color:var(--amber);font-weight:600"
            : "color:var(--text);font-weight:500";
        return (
          '<div class="' + cls + '">' +
            '<span class="muted">Lap ' + esc(lap.lap_number) + (lap.note ? " · " + esc(lap.note) : "") + "</span>" +
            '<span style="' + timeColor + '">' + esc(helpers.formatLapMs(lap.lap_time_ms)) + "</span>" +
          "</div>"
        );
      })
      .join("");

    const iqrText = inspected.iqr_ms != null ? (inspected.iqr_ms / 1000).toFixed(3) + "s" : "--";

    root.innerHTML =
      '<div class="stack">' +
        '<div class="card" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">' +
          "<div>" +
            '<div style="font-size:15px;font-weight:700">' + esc(combo.track + " · " + combo.car) + "</div>" +
            '<div class="sec-sub">' +
              (state.track === "All" || state.car === "All"
                ? "Auto-selected top combo (pick any Track + Car above or in PB Matrix)"
                : "Filtered combo") +
              " · PB " + esc(combo.pb_time) +
              (gainMs != null ? " · First-to-latest delta " + esc(helpers.formatDeltaMs(gainMs)) : "") +
            "</div>" +
          "</div>" +
          '<div class="combo-chips" id="prog-combo-chips">' + quickChips + "</div>" +
        "</div>" +

        '<div class="card">' +
          '<div class="sec-head">' +
            "<div>" +
              '<div class="sec-title">Session Best, Median &amp; Running PB Lap Time (m:ss.sss)</div>' +
              '<div class="sec-sub">' +
                esc(combo.track + " · " + combo.car) + " · " +
                (state.trimOutliers
                  ? "Median computed on <=107% trimmed laps"
                  : "Median computed on all raw laps") +
                " · Click any point or session below to inspect laps &amp; notes" +
              "</div>" +
            "</div>" +
          "</div>" +
          '<div id="prog-chart"></div>' +
        "</div>" +

        '<div class="two-col">' +
          '<div class="card">' +
            '<div class="sec-title" style="font-size:13.5px;margin-bottom:8px">' +
              "Sessions in Progression (" + comboSessions.length + ")" +
            "</div>" +
            '<div class="session-list" id="prog-sessions">' + sessionListHtml + "</div>" +
          "</div>" +

          '<div class="card">' +
            '<div class="sec-head" style="margin-bottom:6px">' +
              '<div class="sec-title" style="font-size:13.5px">Session Detail · ' + esc(inspected.date_label) + "</div>" +
              '<div style="display:flex;gap:5px;align-items:center">' +
                helpers.renderTypePill(inspected.effective_type, inspected.is_legacy_blank_type) +
                (inspected.gt_confirmed ? helpers.renderGtBadge() : "") +
              "</div>" +
            "</div>" +
            '<div style="font-size:12px;background:var(--surface-muted);border:1px solid var(--border);border-radius:6px;padding:7px 9px;margin-bottom:10px">' +
              '<span class="muted">Notes: </span>' + esc(inspected.notes || "No session notes.") +
            "</div>" +
            '<div class="detail-stats">' +
              '<div class="detail-stat"><div class="k">Best</div><div class="v best">' + esc(inspected.best_time) + "</div></div>" +
              '<div class="detail-stat"><div class="k">Median</div><div class="v">' + esc(inspected.median_time) + "</div></div>" +
              '<div class="detail-stat"><div class="k">IQR Spread</div><div class="v">' + esc(iqrText) + "</div></div>" +
            "</div>" +
            '<div class="muted" style="font-size:11.5px;margin-bottom:5px">' +
              "Laps (" + inspected.visible_lap_count + " shown" +
              (state.trimOutliers && inspected.outlier_count > 0 ? ", " + inspected.outlier_count + " >107% trimmed" : "") +
              ")" +
            "</div>" +
            '<div class="lap-scroll">' + lapsHtml + "</div>" +
          "</div>" +
        "</div>" +
      "</div>";

    let runningPbSec = Infinity;
    const categories = [], bestVals = [], medVals = [], pbVals = [], meta = [], nums = [];
    comboSessions.forEach((s) => {
      const bSec = s.best_ms != null ? s.best_ms / 1000 : null;
      const mSec = s.median_ms != null ? s.median_ms / 1000 : null;
      if (bSec != null) { nums.push(bSec); if (bSec < runningPbSec) runningPbSec = bSec; }
      if (mSec != null) nums.push(mSec);
      categories.push(s.date_label + " (" + s.effective_type.toUpperCase() + ")");
      bestVals.push(bSec);
      medVals.push(mSec);
      pbVals.push(Number.isFinite(runningPbSec) ? runningPbSec : null);
      const flags = [s.gt_confirmed ? "GT" : null, s.is_legacy_blank_type ? "legacy blank as p" : null]
        .filter(Boolean).join(", ");
      meta.push((flags ? "[" + flags + "] " : "") + (s.notes || "No session notes"));
    });

    const yMin = nums.length ? Math.floor(Math.min(...nums) - 0.6) : 90;
    const yMax = nums.length ? Math.ceil(Math.max(...nums) + 0.6) : 100;

    window.REVIEW_SVG.mountInteractiveLinePlot(
      root.querySelector("#prog-chart"),
      {
        categories,
        series: [
          { id: "pb", name: "Running PB", color: palette.green, values: pbVals, step: true, dashed: true },
          { id: "best", name: "Session Best", color: palette.accent, values: bestVals },
          { id: "median", name: state.trimOutliers ? "Median (trimmed)" : "Median (raw)", color: palette.amber, values: medVals },
        ],
        yDomain: [yMin, yMax],
        yAxisLabel: "Lap Time (m:ss)",
        xAxisLabel: "Session Date & Type (P / R)",
        formatY: helpers.formatSecShort,
        formatTooltipVal: (v) => helpers.formatLapMs(v * 1000),
        categoryMeta: meta,
        caption:
          "Source: sessions.csv + laps.csv · Running PB tracks the all-time best lap for " +
          combo.track + " (" + combo.car + "); hover any point to read session notes.",
        onSelectCategory: (idx) => {
          const target = comboSessions[idx];
          if (target) helpers.selectInspectedSession(target.session_id);
        },
      },
      helpers
    );

    root.querySelectorAll("#prog-combo-chips button[data-track]").forEach((btn) => {
      btn.addEventListener("click", () => {
        helpers.drillIntoCombo(btn.getAttribute("data-track"), btn.getAttribute("data-car"), null);
      });
    });
    root.querySelectorAll("#prog-sessions button[data-inspect-sid]").forEach((btn) => {
      btn.addEventListener("click", () => {
        helpers.selectInspectedSession(btn.getAttribute("data-inspect-sid"));
      });
    });
  }

  window.REVIEW_VIEW_RENDERERS = Object.assign(window.REVIEW_VIEW_RENDERERS || {}, {
    progression: renderProgressionView,
  });
})();
""".strip()
