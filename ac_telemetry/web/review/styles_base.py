"""Base theme tokens, topbar, filter bar, view tabs, and responsive CSS for /review."""

from __future__ import annotations

REVIEW_BASE_CSS = """
    :root {
      --bg: #0b0e14;
      --surface: #141923;
      --surface-muted: #0f141e;
      --border: #232c3d;
      --text: #e5e9f0;
      --text-muted: #8892a6;
      --accent: #3b82f6;
      --accent-soft: #16253f;
      --green: #10b981;
      --green-soft: #0e2922;
      --amber: #f59e0b;
      --amber-soft: #2b2110;
      --red: #ef4444;
      --purple: #a78bfa;
      --grid: #1f2736;
    }
    :root[data-theme="light"] {
      --bg: #f6f7f9;
      --surface: #ffffff;
      --surface-muted: #f1f3f7;
      --border: #dde2eb;
      --text: #111827;
      --text-muted: #5b6578;
      --accent: #2563eb;
      --accent-soft: #e8f0fe;
      --green: #059669;
      --green-soft: #e6f6f0;
      --amber: #d97706;
      --amber-soft: #fef3e2;
      --red: #dc2626;
      --purple: #7c3aed;
      --grid: #e6eaf0;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "IBM Plex Sans", "Segoe UI", system-ui, -apple-system, sans-serif;
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    code { font-family: "IBM Plex Mono", "Consolas", monospace; font-size: 0.9em; }

    .topbar {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 20;
    }
    .topbar-inner {
      max-width: 1240px;
      margin: 0 auto;
      padding: 12px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }
    .brand { display: flex; align-items: center; gap: 10px; }
    .brand-title { font-weight: 700; font-size: 16px; letter-spacing: -0.01em; color: var(--text); }
    .route-badge {
      font-size: 11px;
      font-family: "IBM Plex Mono", "Consolas", monospace;
      padding: 2px 7px;
      border-radius: 5px;
      background: var(--accent-soft);
      color: var(--accent);
      border: 1px solid var(--accent);
    }
    .nav-group { display: flex; align-items: center; flex-wrap: wrap; gap: 14px; font-size: 13px; }
    .nav-link { color: var(--text-muted); font-weight: 500; padding-bottom: 2px; }
    .nav-link:hover { color: var(--text); text-decoration: none; }
    .nav-link.active { color: var(--accent); font-weight: 600; border-bottom: 2px solid var(--accent); }
    .theme-btn {
      border: 1px solid var(--border);
      background: var(--surface-muted);
      color: var(--text);
      border-radius: 7px;
      padding: 5px 10px;
      font: inherit;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
    }
    .theme-btn:hover { border-color: var(--accent); }

    .container { max-width: 1240px; margin: 0 auto; padding: 18px 18px 32px; }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
    .stack { display: flex; flex-direction: column; gap: 14px; }

    .filter-bar {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 14px;
      margin-bottom: 14px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .filter-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .ctrl {
      background: var(--surface-muted);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 7px 10px;
      font: inherit;
      font-size: 12.5px;
      outline: none;
      min-width: 145px;
    }
    .ctrl:focus { border-color: var(--accent); }
    .ctrl-search { flex: 1 1 200px; min-width: 165px; }
    .seg-group {
      display: inline-flex;
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow: hidden;
      background: var(--surface-muted);
    }
    .seg-btn {
      border: 0;
      padding: 7px 11px;
      font: inherit;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      background: transparent;
      color: var(--text-muted);
      white-space: nowrap;
    }
    .seg-btn.active { background: var(--accent); color: #ffffff; font-weight: 600; }
    .btn-reset {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-muted);
      border-radius: 6px;
      padding: 7px 11px;
      font: inherit;
      font-size: 12px;
      cursor: pointer;
    }
    .btn-reset:hover { border-color: var(--accent); color: var(--text); }
    .btn-reset.is-hidden { display: none; }

    .toggle-row {
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      align-items: center;
      justify-content: space-between;
      font-size: 12px;
      color: var(--text-muted);
      border-top: 1px solid var(--border);
      padding-top: 9px;
    }
    .toggle-group { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; }
    .chk-label { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; color: var(--text); user-select: none; }
    .chk-label input { accent-color: var(--accent); margin: 0; }
    .muted { color: var(--text-muted); }
    .status-meta { font-size: 11.5px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
    .notice {
      font-size: 12.5px;
      padding: 8px 11px;
      border-radius: 6px;
      background: var(--amber-soft);
      border: 1px solid var(--amber);
      color: var(--amber);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .notice.is-hidden { display: none; }
    .notice-err { background: var(--surface-muted); border-color: var(--red); color: var(--red); }

    .view-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
    .view-tab {
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text-muted);
      font: inherit;
      font-weight: 500;
      font-size: 12.5px;
      padding: 7px 12px;
      border-radius: 8px;
      cursor: pointer;
    }
    .view-tab:hover { border-color: var(--accent); color: var(--text); }
    .view-tab.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); font-weight: 600; }

    .empty-state { text-align: center; padding: 36px 18px; color: var(--text-muted); font-size: 13.5px; }
    .empty-state strong { display: block; color: var(--text); font-size: 15px; margin-bottom: 6px; }
    .page-footer {
      max-width: 1240px;
      margin: 0 auto;
      padding: 10px 18px 24px;
      border-top: 1px solid var(--border);
      font-size: 11.5px;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
    }

    @media (max-width: 520px) {
      .topbar-inner { padding: 10px 12px; }
      .container { padding: 12px 12px 24px; }
      .filter-bar { padding: 10px; }
      .ctrl { width: 100%; min-width: 0; }
      .seg-group { width: 100%; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .seg-btn { text-align: center; padding: 7px 6px; }
      .hide-phone { display: none; }
    }
""".strip()
