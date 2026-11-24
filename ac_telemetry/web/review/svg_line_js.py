"""Reusable inline-SVG DOM helpers and interactive line/step plot primitive."""

from __future__ import annotations

REVIEW_SVG_LINE_JS = r"""
(function () {
  const SVG_NS = "http://www.w3.org/2000/svg";

  function svgEl(tag, attrs, text) {
    const el = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v !== undefined && v !== null) el.setAttribute(k, String(v));
      }
    }
    if (text != null) el.textContent = String(text);
    return el;
  }

  function seriesPalette(palette) {
    return [palette.accent, palette.green, palette.amber, palette.purple, palette.red];
  }

  function buildLegend(items, kind, esc) {
    return (
      '<div class="chart-legend">' +
      items
        .map((s) => {
          const mark =
            kind === "line"
              ? '<span class="legend-line" style="background:' +
                (s.dashed ? "transparent;border-top:2px dashed " + s.color : s.color) +
                '"></span>'
              : '<span class="legend-swatch" style="background:' + s.color + '"></span>';
          return '<span class="legend-item">' + mark + "<span>" + esc(s.name) + "</span></span>";
        })
        .join("") +
      "</div>"
    );
  }

  function mountInteractiveLinePlot(host, opts, helpers) {
    const {
      categories, series, yDomain, yAxisLabel, xAxisLabel,
      formatY, formatTooltipVal, categoryMeta, caption, emptyHint, onSelectCategory,
    } = opts;
    const palette = helpers.getThemePalette();
    const esc = helpers.escapeHtml;
    const isPhone = window.innerWidth <= 520;
    const width = 760;
    const height = isPhone ? 245 : 275;
    const padL = 68, padR = 18, padT = 14, padB = 46;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;
    const yMin = yDomain[0], yMax = yDomain[1];
    const ySpan = Math.max(0.1, yMax - yMin);

    const xFor = (i) =>
      categories.length <= 1 ? padL + plotW / 2 : padL + (i / (categories.length - 1)) * plotW;
    const yFor = (v) => padT + ((yMax - v) / ySpan) * plotH;

    host.innerHTML =
      buildLegend(series, "line", esc) +
      '<div class="svg-slot"></div>' +
      '<div class="hover-strip" role="status" aria-live="polite"></div>' +
      (caption ? '<div class="chart-caption">' + esc(caption) + "</div>" : "");

    const slot = host.querySelector(".svg-slot");
    const strip = host.querySelector(".hover-strip");
    const defaultHint = emptyHint || "Hover any point on the chart to inspect exact times and notes.";
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

    const yMid = padT + plotH / 2;
    svg.appendChild(svgEl("text", {
      x: 14, y: yMid.toFixed(1), transform: "rotate(-90 14 " + yMid.toFixed(1) + ")",
      "text-anchor": "middle", "font-size": 10.5, fill: palette.textMuted,
    }, yAxisLabel));
    svg.appendChild(svgEl("text", {
      x: (padL + plotW / 2).toFixed(1), y: height - 6,
      "text-anchor": "middle", "font-size": 10.5, fill: palette.textMuted,
    }, xAxisLabel));

    const xStep = Math.max(1, Math.ceil(categories.length / 8));
    categories.forEach((cat, i) => {
      if (i % xStep !== 0 && i !== categories.length - 1) return;
      svg.appendChild(svgEl("text", {
        x: xFor(i).toFixed(1), y: padT + plotH + 16,
        "text-anchor": "middle", "font-size": 10.5, fill: palette.textMuted,
      }, cat));
    });

    const guide = svgEl("line", {
      x1: padL, y1: padT, x2: padL, y2: padT + plotH,
      stroke: palette.border, "stroke-width": 1.5, visibility: "hidden",
    });
    svg.appendChild(guide);

    const circlesByIdx = Array.from({ length: categories.length }, () => []);
    series.forEach((s) => {
      let d = "", prevX = null, prevY = null;
      for (let i = 0; i < categories.length; i++) {
        const v = s.values[i];
        if (v == null) continue;
        const x = xFor(i), y = yFor(v);
        if (prevX === null) d += "M " + x.toFixed(1) + " " + y.toFixed(1);
        else if (s.step) d += " L " + x.toFixed(1) + " " + prevY.toFixed(1) + " L " + x.toFixed(1) + " " + y.toFixed(1);
        else d += " L " + x.toFixed(1) + " " + y.toFixed(1);
        prevX = x; prevY = y;
      }
      if (d) {
        svg.appendChild(svgEl("path", {
          d, fill: "none", stroke: s.color,
          "stroke-width": s.dashed ? 1.8 : 2.3,
          "stroke-dasharray": s.dashed ? "5 4" : null,
        }));
      }
      if (!s.step) {
        s.values.forEach((v, i) => {
          if (v == null) return;
          const c = svgEl("circle", {
            cx: xFor(i).toFixed(1), cy: yFor(v).toFixed(1), r: 3.3,
            fill: s.color, stroke: palette.surface, "stroke-width": 1.2,
          });
          svg.appendChild(c);
          circlesByIdx[i].push(c);
        });
      }
    });

    let activeIdx = null;
    function setHover(idx) {
      if (activeIdx !== null && circlesByIdx[activeIdx]) {
        circlesByIdx[activeIdx].forEach((c) => c.setAttribute("r", "3.3"));
      }
      activeIdx = idx;
      if (idx === null) {
        guide.setAttribute("visibility", "hidden");
        strip.innerHTML = "<span>" + esc(defaultHint) + "</span>";
        return;
      }
      const gx = xFor(idx).toFixed(1);
      guide.setAttribute("x1", gx);
      guide.setAttribute("x2", gx);
      guide.setAttribute("visibility", "visible");
      if (circlesByIdx[idx]) circlesByIdx[idx].forEach((c) => c.setAttribute("r", "5.2"));
      const parts = ['<strong style="color:var(--text)">' + esc(categories[idx]) + "</strong>"];
      series.forEach((s) => {
        const v = s.values[idx];
        if (v == null) return;
        parts.push(
          '<span style="color:var(--text)"><span style="color:' + s.color + ';font-weight:600">' +
          esc(s.name) + ":</span> " + esc(formatTooltipVal(v)) + "</span>"
        );
      });
      if (categoryMeta && categoryMeta[idx]) {
        parts.push('<span class="muted">' + esc(categoryMeta[idx]) + "</span>");
      }
      strip.innerHTML = parts.join("");
    }

    const colW = categories.length > 1 ? plotW / (categories.length - 1) : plotW;
    categories.forEach((_, i) => {
      const x = xFor(i);
      const hit = svgEl("rect", {
        x: Math.max(padL, x - colW / 2).toFixed(1), y: padT,
        width: colW.toFixed(1), height: plotH, fill: "transparent",
        style: onSelectCategory ? "cursor:pointer" : "cursor:default",
      });
      hit.addEventListener("mouseenter", () => setHover(i));
      hit.addEventListener("focus", () => setHover(i));
      if (onSelectCategory) hit.addEventListener("click", () => onSelectCategory(i));
      svg.appendChild(hit);
    });

    svg.addEventListener("mouseleave", () => setHover(null));
    slot.appendChild(svg);
  }

  window.REVIEW_SVG = Object.assign(window.REVIEW_SVG || {}, {
    svgEl,
    seriesPalette,
    buildLegend,
    mountInteractiveLinePlot,
  });
})();
""".strip()
