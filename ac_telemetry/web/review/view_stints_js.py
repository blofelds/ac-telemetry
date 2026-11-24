"""Stint Comparison inline-SVG lap overlay and consistency band view."""

from __future__ import annotations

REVIEW_STINTS_JS = r"""
(function () {
  function renderStintComparisonView(root, state, helpers) {
    const esc = helpers.escapeHtml;
    const palette = helpers.getThemePalette();
    const colors = window.REVIEW_SVG.seriesPalette(palette);
    const combo = helpers.getActiveCombo();
    const comboSessions = helpers.getActiveComboSessions();

    if (!combo || !comboSessions.length) {
      root.innerHTML =
        '<div class="card empty-state">' +
        "<strong>No timed stints to compare</strong>" +
        "Select a Track and Car with timed sessions or reset filters above." +
        "</div>";
      return;
    }

    const selected = comboSessions.filter((s) => state.compareIds.includes(s.session_id));
    const activeStints =
      selected.length >= 2
        ? selected.slice(0, 4)
        : comboSessions.slice(-Math.min(3, comboSessions.length));

    const chipsHtml = comboSessions
      .map((s) => {
        const idx = activeStints.findIndex((c) => c.session_id === s.session_id);
        const isSel = idx !== -1;
        const color = isSel ? colors[idx % colors.length] : palette.border;
        return (
          '<button type="button" class="chip-btn" data-compare-sid="' + esc(s.session_id) + '"' +
          ' style="border-color:' + (isSel ? color : "var(--border)") + ';color:' +
          (isSel ? "var(--text)" : "var(--text-muted)") + '">' +
            '<span class="chip-dot" style="background:' + color + '"></span>' +
            '<span style="font-weight:' + (isSel ? "600" : "500") + '">' +
              esc(s.date_label + " (" + s.effective_type.toUpperCase() + ")") +
            "</span>" +
            '<span class="muted">' + esc(s.best_time) + "</span>" +
            (s.gt_confirmed ? helpers.renderGtBadge() : "") +
          "</button>"
        );
      })
      .join("");

    const allSpreadTimes = activeStints.flatMap((s) =>
      (s.visible_laps || []).map((l) => l.lap_time_ms)
    );
    const minStripMs = allSpreadTimes.length ? Math.min(...allSpreadTimes) : 90000;
    const maxStripMs = allSpreadTimes.length ? Math.max(...allSpreadTimes) : 100000;
    const stripSpan = Math.max(500, maxStripMs - minStripMs);
    const xPct = (ms) => Math.max(0, Math.min(100, ((ms - minStripMs) / stripSpan) * 100));

    const bandsHtml = activeStints
      .map((s, idx) => {
        const color = colors[idx % colors.length];
        const minP = s.best_ms != null ? xPct(s.best_ms) : 0;
        const q1P = s.q1_ms != null ? xPct(s.q1_ms) : minP;
        const medP = s.median_ms != null ? xPct(s.median_ms) : minP;
        const q3P = s.q3_ms != null ? xPct(s.q3_ms) : minP;
        const maxP = s.worst_ms != null ? xPct(s.worst_ms) : minP;
        const iqrStr = s.iqr_ms != null ? (s.iqr_ms / 1000).toFixed(3) + "s" : "--";

        const bandW = 600;
        const px = (p) => (10 + (p / 100) * (bandW - 20)).toFixed(1);
        const dotsSvg = (s.visible_laps || [])
          .map((l) => {
            const cx = px(xPct(l.lap_time_ms));
            const tip =
              "Lap " + l.lap_number + ": " + helpers.formatLapMs(l.lap_time_ms) +
              (l.note ? " (" + l.note + ")" : "");
            return '<circle cx="' + cx + '" cy="13" r="3.4" fill="' + color + '"><title>' + esc(tip) + "</title></circle>";
          })
          .join("");

        return (
          '<div class="band-row">' +
            '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px">' +
              '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px">' +
                '<span class="chip-dot" style="background:' + color + '"></span>' +
                '<span style="font-size:12.5px;font-weight:600">' + esc(s.date_label) + "</span>" +
                helpers.renderTypePill(s.effective_type, s.is_legacy_blank_type) +
                (s.gt_confirmed ? helpers.renderGtBadge() : "") +
                '<span class="muted" style="font-size:11.5px">' + esc(s.notes || "") + "</span>" +
              "</div>" +
              '<div class="muted" style="font-size:11.5px;font-variant-numeric:tabular-nums">' +
                'Min <strong style="color:var(--text)">' + esc(s.best_time) + "</strong>" +
                ' · Median <strong style="color:var(--text)">' + esc(s.median_time) + "</strong>" +
                ' · IQR <strong style="color:' + color + '">' + esc(iqrStr) + "</strong>" +
                ' · Max <strong style="color:var(--text)">' + esc(helpers.formatLapMs(s.worst_ms)) + "</strong>" +
              "</div>" +
            "</div>" +
            '<div class="band-track">' +
              '<svg viewBox="0 0 ' + bandW + ' 26" style="width:100%;height:24px;display:block" role="img" aria-label="Stint consistency band for ' + esc(s.date_label) + '">' +
                '<line x1="' + px(minP) + '" y1="13" x2="' + px(maxP) + '" y2="13" stroke="' + palette.border + '" stroke-width="2" />' +
                '<rect x="' + px(q1P) + '" y="4" width="' + Math.max(4, Number(px(q3P)) - Number(px(q1P))).toFixed(1) + '" height="18" rx="3" fill="' + color + '" fill-opacity="0.26" stroke="' + color + '" stroke-width="1" />' +
                '<line x1="' + px(medP) + '" y1="2" x2="' + px(medP) + '" y2="24" stroke="' + color + '" stroke-width="2.5" />' +
                dotsSvg +
              "</svg>" +
            "</div>" +
          "</div>"
        );
      })
      .join("");

    root.innerHTML =
      '<div class="stack">' +
        '<div class="card">' +
          '<div class="sec-head" style="margin-bottom:8px">' +
            '<div class="sec-title" style="font-size:14px">' +
              "Select 2 to 4 Stints to Overlay (" + esc(combo.track + " · " + combo.car) + ")" +
            "</div>" +
            '<div class="sec-caption">' +
              activeStints.length + " selected · toggle Auto-trim above to inspect out-lap / spin spikes" +
            "</div>" +
          "</div>" +
          '<div class="combo-chips" id="stint-picker">' + chipsHtml + "</div>" +
        "</div>" +

        '<div class="card">' +
          '<div class="sec-head">' +
            "<div>" +
              '<div class="sec-title">Lap-by-Lap Pace Overlay (Lap 1 to Lap N)</div>' +
              '<div class="sec-sub">' +
                esc(combo.track + " · " + combo.car) + " · " +
                (state.trimOutliers
                  ? "Trimmed view (<=107% of each session's best) highlights tyre degradation"
                  : "Raw view includes out-laps, spins, and pit-in spikes") +
              "</div>" +
            "</div>" +
          "</div>" +
          '<div id="stint-overlay-chart"></div>' +
        "</div>" +

        '<div class="card">' +
          '<div class="sec-head">' +
            "<div>" +
              '<div class="sec-title">Stint Consistency Band (Min · Q1 · Median · Q3 · Max)</div>' +
              '<div class="sec-sub">' +
                "Scale: " + esc(helpers.formatLapMs(minStripMs)) + " (faster, left) to " +
                esc(helpers.formatLapMs(maxStripMs)) + " (slower, right)" +
              "</div>" +
            "</div>" +
            '<div class="chart-legend" style="margin:0">' +
              '<span class="legend-item"><span class="legend-swatch" style="background:var(--accent);opacity:0.35;border:1px solid var(--accent)"></span>IQR (Q1-Q3)</span>' +
              '<span class="legend-item"><span class="legend-line" style="background:var(--accent)"></span>Median</span>' +
              '<span class="legend-item"><span class="chip-dot" style="background:var(--accent)"></span>Lap</span>' +
            "</div>" +
          "</div>" +
          '<div class="stack" style="gap:10px">' + bandsHtml + "</div>" +
          '<div class="chart-caption">' +
            "Narrower shaded IQR box indicates tighter lap-to-lap consistency. Hover any dot for exact lap time (m:ss.sss) and lap note." +
          "</div>" +
        "</div>" +
      "</div>";

    const maxLap = Math.max(
      1,
      ...activeStints.map((s) =>
        Math.max(0, ...(s.visible_laps || []).map((l) => Number(l.lap_number || 0)))
      )
    );
    const categories = Array.from({ length: maxLap }, (_, i) => "L" + (i + 1));
    const nums = [];
    const lapNotesMeta = Array.from({ length: maxLap }, () => []);

    const series = activeStints.map((s, idx) => {
      const byNum = new Map();
      (s.visible_laps || []).forEach((l) => byNum.set(Number(l.lap_number), l));
      const values = categories.map((_, i) => {
        const lap = byNum.get(i + 1);
        if (!lap) return null;
        const sec = lap.lap_time_ms / 1000;
        nums.push(sec);
        if (lap.note) lapNotesMeta[i].push(s.date_label + ": " + lap.note);
        return sec;
      });
      return {
        id: s.session_id,
        name: s.date_label + " (" + s.effective_type.toUpperCase() + ")",
        color: colors[idx % colors.length],
        values,
      };
    });

    const yMin = nums.length ? Math.floor(Math.min(...nums) - 0.5) : 90;
    const yMax = nums.length ? Math.ceil(Math.max(...nums) + 0.7) : 105;

    window.REVIEW_SVG.mountInteractiveLinePlot(
      root.querySelector("#stint-overlay-chart"),
      {
        categories,
        series,
        yDomain: [yMin, yMax],
        yAxisLabel: "Lap Time (m:ss)",
        xAxisLabel: "Lap Number in Stint (lap)",
        formatY: helpers.formatSecShort,
        formatTooltipVal: (v) => helpers.formatLapMs(v * 1000),
        categoryMeta: lapNotesMeta.map((arr) => arr.join(" · ")),
        caption:
          "Source: laps.csv · Comparing " + activeStints.length + " stint" +
          (activeStints.length === 1 ? "" : "s") + " for " + combo.track + " (" + combo.car +
          ") to highlight pace evolution and tyre drop-off.",
      },
      helpers
    );

    root.querySelectorAll("#stint-picker button[data-compare-sid]").forEach((btn) => {
      btn.addEventListener("click", () => {
        helpers.toggleCompareSession(btn.getAttribute("data-compare-sid"));
      });
    });
  }

  window.REVIEW_VIEW_RENDERERS = Object.assign(window.REVIEW_VIEW_RENDERERS || {}, {
    stints: renderStintComparisonView,
  });
})();
""".strip()
