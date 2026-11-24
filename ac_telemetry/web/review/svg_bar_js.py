"""Reusable inline-SVG stacked and signed grouped bar plot primitive."""

from __future__ import annotations

REVIEW_SVG_BAR_JS = r"""
(function () {
  function mountInteractiveBarPlot(host, opts, helpers) {
    const { svgEl, buildLegend } = window.REVIEW_SVG;
    const {
      categories, series, stacked, signed, yAxisLabel, xAxisLabel,
      formatY, formatVal, caption, emptyHint,
    } = opts;
    const palette = helpers.getThemePalette();
    const esc = helpers.escapeHtml;
    const isPhone = window.innerWidth <= 520;
    const width = 760;
    const height = isPhone ? 230 : 260;
    const padL = 64, padR = 16, padT = 14, padB = 46;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;

    let minVal = 0, maxVal = 0;
    for (let i = 0; i < categories.length; i++) {
      if (stacked) {
        const sum = series.reduce((acc, s) => acc + Math.max(0, s.values[i] || 0), 0);
        if (sum > maxVal) maxVal = sum;
      } else {
        for (const s of series) {
          const v = Number(s.values[i] || 0);
          if (v > maxVal) maxVal = v;
          if (signed && v < minVal) minVal = v;
        }
      }
    }
    if (maxVal === 0 && minVal === 0) maxVal = 1;
    const yMax = maxVal > 0 ? maxVal * 1.14 : 0.1;
    const yMin = signed && minVal < 0 ? minVal * 1.14 : 0;
    const ySpan = Math.max(0.1, yMax - yMin);
    const yFor = (v) => padT + ((yMax - v) / ySpan) * plotH;
    const zeroY = yFor(0);

    host.innerHTML =
      buildLegend(series, "bar", esc) +
      '<div class="svg-slot"></div>' +
      '<div class="hover-strip" role="status" aria-live="polite"></div>' +
      (caption ? '<div class="chart-caption">' + esc(caption) + "</div>" : "");

    const slot = host.querySelector(".svg-slot");
    const strip = host.querySelector(".hover-strip");
    const defaultHint = emptyHint || "Hover any column to inspect breakdown values.";
    strip.innerHTML = "<span>" + esc(defaultHint) + "</span>";

    const svg = svgEl("svg", {
      viewBox: "0 0 " + width + " " + height,
      class: "chart-svg",
      role: "img",
      "aria-label": yAxisLabel + " by " + xAxisLabel,
    });

    [0, 0.25, 0.5, 0.75, 1].forEach((t) => {
      const val = yMin + t * ySpan;
      const y = yFor(val);
      svg.appendChild(svgEl("line", {
        x1: padL, y1: y.toFixed(1), x2: width - padR, y2: y.toFixed(1),
        stroke: palette.grid, "stroke-dasharray": "3 3",
      }));
      svg.appendChild(svgEl("text", {
        x: padL - 8, y: (y + 4).toFixed(1), "text-anchor": "end",
        "font-size": 10.5, fill: palette.textMuted,
      }, formatY(val)));
    });

    svg.appendChild(svgEl("line", { x1: padL, y1: padT, x2: padL, y2: padT + plotH, stroke: palette.border }));
    svg.appendChild(svgEl("line", { x1: padL, y1: padT + plotH, x2: width - padR, y2: padT + plotH, stroke: palette.border }));
    if (signed && yMin < 0) {
      svg.appendChild(svgEl("line", {
        x1: padL, y1: zeroY.toFixed(1), x2: width - padR, y2: zeroY.toFixed(1),
        stroke: palette.textMuted, "stroke-width": 1.2,
      }));
    }

    const yMid = padT + plotH / 2;
    svg.appendChild(svgEl("text", {
      x: 14, y: yMid.toFixed(1), transform: "rotate(-90 14 " + yMid.toFixed(1) + ")",
      "text-anchor": "middle", "font-size": 10.5, fill: palette.textMuted,
    }, yAxisLabel));
    svg.appendChild(svgEl("text", {
      x: (padL + plotW / 2).toFixed(1), y: height - 6,
      "text-anchor": "middle", "font-size": 10.5, fill: palette.textMuted,
    }, xAxisLabel));

    const groupW = plotW / Math.max(1, categories.length);
    const highlights = [];

    function setHover(idx) {
      highlights.forEach((h, i) => h.setAttribute("visibility", i === idx ? "visible" : "hidden"));
      if (idx === null) {
        strip.innerHTML = "<span>" + esc(defaultHint) + "</span>";
        return;
      }
      const parts = ['<strong style="color:var(--text)">' + esc(categories[idx]) + "</strong>"];
      let total = 0;
      series.forEach((s) => {
        const v = Number(s.values[idx] || 0);
        total += v;
        if (stacked && v === 0) return;
        parts.push(
          '<span style="color:var(--text)"><span style="color:' + s.color + ';font-weight:600">' +
          esc(s.name) + ":</span> " + esc(formatVal(v)) + "</span>"
        );
      });
      if (stacked) parts.push('<span class="muted">Total: ' + esc(formatVal(total)) + "</span>");
      strip.innerHTML = parts.join("");
    }

    categories.forEach((cat, i) => {
      const gx = padL + i * groupW;
      const g = svgEl("g");
      const hl = svgEl("rect", {
        x: (gx + 2).toFixed(1), y: padT, width: Math.max(4, groupW - 4).toFixed(1),
        height: plotH, fill: palette.surfaceMuted, opacity: 0.7, visibility: "hidden",
      });
      highlights.push(hl);
      g.appendChild(hl);

      if (stacked) {
        const barW = Math.min(54, groupW * 0.56);
        const bx = gx + (groupW - barW) / 2;
        let running = 0;
        series.forEach((s) => {
          const v = Math.max(0, Number(s.values[i] || 0));
          const yTop = yFor(running + v), yBot = yFor(running);
          running += v;
          const h = Math.max(0, yBot - yTop);
          if (h > 0) {
            g.appendChild(svgEl("rect", {
              x: bx.toFixed(1), y: yTop.toFixed(1),
              width: barW.toFixed(1), height: h.toFixed(1), fill: s.color,
            }));
          }
        });
      } else {
        const innerGap = 4;
        const totalInner = Math.min(76, groupW * 0.68);
        const barW = (totalInner - innerGap * (series.length - 1)) / Math.max(1, series.length);
        const startX = gx + (groupW - totalInner) / 2;
        series.forEach((s, sIdx) => {
          const v = Number(s.values[i] || 0);
          const yVal = yFor(v);
          const yTop = Math.min(zeroY, yVal);
          const h = Math.max(1.5, Math.abs(yVal - zeroY));
          g.appendChild(svgEl("rect", {
            x: (startX + sIdx * (barW + innerGap)).toFixed(1), y: yTop.toFixed(1),
            width: barW.toFixed(1), height: h.toFixed(1), rx: 2, fill: s.color,
          }));
        });
      }

      g.appendChild(svgEl("text", {
        x: (gx + groupW / 2).toFixed(1), y: padT + plotH + 16,
        "text-anchor": "middle", "font-size": 10.5, fill: palette.textMuted,
      }, cat));

      const hit = svgEl("rect", {
        x: gx.toFixed(1), y: padT, width: groupW.toFixed(1), height: plotH, fill: "transparent",
      });
      hit.addEventListener("mouseenter", () => setHover(i));
      g.appendChild(hit);
      svg.appendChild(g);
    });

    svg.addEventListener("mouseleave", () => setHover(null));
    slot.appendChild(svg);
  }

  window.REVIEW_SVG = Object.assign(window.REVIEW_SVG || {}, {
    mountInteractiveBarPlot,
  });
})();
""".strip()
