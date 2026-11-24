"""View-level component styles (KPI tiles, tables, badges, charts) for /review."""

from __future__ import annotations

REVIEW_VIEWS_CSS = """
    .kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .kpi-tile {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 14px;
      min-width: 0;
    }
    .kpi-label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-muted);
      margin-bottom: 4px;
    }
    .kpi-value {
      font-size: 21px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      color: var(--text);
      line-height: 1.2;
    }
    .kpi-value.accent-green { color: var(--green); }
    .kpi-sub {
      font-size: 11.5px;
      color: var(--text-muted);
      margin-top: 4px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .sec-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 10px;
    }
    .sec-title { font-size: 15px; font-weight: 600; color: var(--text); }
    .sec-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
    .sec-caption { font-size: 11.5px; color: var(--text-muted); }

    .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
    table.review-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
      font-variant-numeric: tabular-nums;
    }
    table.review-table th {
      text-align: left;
      padding: 8px 8px;
      font-weight: 600;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }
    table.review-table td {
      padding: 9px 8px;
      border-bottom: 1px solid var(--border);
      color: var(--text);
      vertical-align: middle;
    }
    table.review-table tbody tr.clickable { cursor: pointer; }
    table.review-table tbody tr.clickable:hover { background: var(--surface-muted); }
    table.review-table tbody tr.active-row { background: var(--accent-soft); }
    .pb-cell { font-weight: 700; color: var(--green); }
    .delta-fast { color: var(--green); font-weight: 600; }
    .delta-slow { color: var(--amber); font-weight: 600; }

    .pill-type {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 999px;
      white-space: nowrap;
    }
    .pill-type.practice { border: 1px solid var(--accent); background: var(--accent-soft); color: var(--accent); }
    .pill-type.race { border: 1px solid var(--amber); background: var(--amber-soft); color: var(--amber); }
    .badge-gt {
      display: inline-flex;
      align-items: center;
      font-size: 10px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 4px;
      border: 1px solid var(--green);
      background: var(--green-soft);
      color: var(--green);
      letter-spacing: 0.03em;
      white-space: nowrap;
    }
    .badge-empty {
      display: inline-flex;
      align-items: center;
      font-size: 10px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 4px;
      border: 1px solid var(--border);
      color: var(--text-muted);
      white-space: nowrap;
    }

    .session-list { display: flex; flex-direction: column; gap: 8px; }
    .session-item {
      border: 1px solid var(--border);
      background: var(--surface-muted);
      border-radius: 8px;
      padding: 10px 12px;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      text-align: left;
      width: 100%;
      font: inherit;
      color: var(--text);
    }
    .session-item:hover { border-color: var(--accent); }
    .session-item-main { min-width: 0; flex: 1; }
    .session-item-head { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 3px; }
    .session-item-title { font-size: 13px; font-weight: 600; color: var(--text); }
    .session-item-notes {
      font-size: 12px;
      color: var(--text-muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .session-item-metrics { display: flex; align-items: center; gap: 14px; flex-shrink: 0; font-variant-numeric: tabular-nums; }
    .metric-col .m-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; }
    .metric-col .m-val { font-size: 13px; color: var(--text); font-weight: 600; }
    .metric-col .m-val.best { color: var(--green); font-weight: 700; }

    .chart-legend { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; font-size: 11.5px; color: var(--text-muted); }
    .legend-item { display: inline-flex; align-items: center; gap: 6px; color: var(--text); }
    .legend-line { width: 14px; height: 2px; display: inline-block; }
    .legend-swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
    .chart-svg { width: 100%; height: auto; display: block; }
    .hover-strip {
      margin-top: 6px;
      min-height: 30px;
      padding: 6px 10px;
      border-radius: 6px;
      background: var(--surface-muted);
      border: 1px solid var(--border);
      font-size: 12px;
      color: var(--text-muted);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      font-variant-numeric: tabular-nums;
    }
    .chart-caption { margin-top: 6px; font-size: 11.5px; color: var(--text-muted); }
    .two-col { display: grid; grid-template-columns: 1.15fr 1fr; gap: 12px; }
    .combo-chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid var(--border);
      background: var(--surface-muted);
      color: var(--text-muted);
      border-radius: 7px;
      padding: 5px 9px;
      font: inherit;
      font-size: 11.5px;
      cursor: pointer;
    }
    .chip-btn.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); font-weight: 600; }
    .chip-dot { width: 8px; height: 8px; border-radius: 999px; display: inline-block; }
    .detail-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; margin-bottom: 10px; font-variant-numeric: tabular-nums; }
    .detail-stat { background: var(--surface-muted); border-radius: 6px; padding: 6px 8px; }
    .detail-stat .k { font-size: 10px; color: var(--text-muted); text-transform: uppercase; }
    .detail-stat .v { font-size: 13px; font-weight: 600; color: var(--text); margin-top: 2px; }
    .detail-stat .v.best { color: var(--green); font-weight: 700; }
    .lap-scroll { max-height: 220px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; font-variant-numeric: tabular-nums; }
    .lap-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      padding: 5px 8px;
      border-radius: 5px;
      background: var(--surface-muted);
    }
    .lap-row.best { background: var(--green-soft); }
    .lap-row.trimmed { opacity: 0.48; text-decoration: line-through; }
    .band-row { border: 1px solid var(--border); background: var(--surface-muted); border-radius: 8px; padding: 10px 12px; }
    .band-track {
      position: relative;
      height: 24px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      margin-top: 8px;
    }

    @media (max-width: 820px) {
      .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .two-col { grid-template-columns: minmax(0, 1fr); }
    }
    @media (max-width: 520px) {
      .session-item { flex-direction: column; align-items: flex-start; }
      .session-item-notes { white-space: normal; }
      .kpi-value { font-size: 18px; }
    }
""".strip()
