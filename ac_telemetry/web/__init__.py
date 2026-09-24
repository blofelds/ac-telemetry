"""Minimal LAN status page (Slice 0 — no session UX beyond status)."""

STATUS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AC Telemetry — status</title>
  <style>
    :root {
      --bg: #0f1419;
      --panel: #1a222c;
      --text: #e8eef4;
      --muted: #8b9aab;
      --ok: #3dba7a;
      --bad: #d35a5a;
      --accent: #4a8fd4;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, #1c2a3a 0%, var(--bg) 55%);
      color: var(--text);
      min-height: 100vh;
      padding: 1.5rem;
    }
    h1 { font-size: 1.35rem; font-weight: 600; margin: 0 0 0.25rem; }
    .sub { color: var(--muted); margin-bottom: 1.5rem; font-size: 0.95rem; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 0.75rem;
      max-width: 720px;
    }
    .stat {
      background: var(--panel);
      padding: 0.9rem 1rem;
      border-radius: 6px;
    }
    .stat .label { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; }
    .stat .value { font-size: 1.35rem; margin-top: 0.25rem; font-variant-numeric: tabular-nums; }
    .dot { display: inline-block; width: 0.55rem; height: 0.55rem; border-radius: 50%; margin-right: 0.4rem; }
    .dot.on { background: var(--ok); }
    .dot.off { background: var(--bad); }
    .err { color: var(--bad); max-width: 720px; margin-top: 1rem; font-size: 0.9rem; }
    a { color: var(--accent); }
    footer { margin-top: 2rem; color: var(--muted); font-size: 0.8rem; }
  </style>
</head>
<body>
  <h1>AC Telemetry</h1>
  <p class="sub">Capture status · Slice 0 · refreshes every 2s</p>
  <div class="grid">
    <div class="stat"><div class="label">Capture</div><div class="value" id="running">…</div></div>
    <div class="stat"><div class="label">Backend</div><div class="value" id="backend">…</div></div>
    <div class="stat"><div class="label">Profile</div><div class="value" id="profile">…</div></div>
    <div class="stat"><div class="label">Resolution</div><div class="value" id="res">…</div></div>
    <div class="stat"><div class="label">FPS (measured)</div><div class="value" id="fps">…</div></div>
    <div class="stat"><div class="label">Last frame age</div><div class="value" id="age">…</div></div>
    <div class="stat"><div class="label">Frames</div><div class="value" id="frames">…</div></div>
    <div class="stat"><div class="label">Errors</div><div class="value" id="errors">…</div></div>
  </div>
  <p class="err" id="last_error"></p>
  <footer>
    <a href="/health">/health</a> · <a href="/metrics">/metrics</a> · device <span id="device"></span>
    · session <span id="session"></span>
  </footer>
  <script>
    async function refresh() {
      try {
        const r = await fetch("/api/status");
        const d = await r.json();
        const on = d.running;
        document.getElementById("running").innerHTML =
          '<span class="dot ' + (on ? "on" : "off") + '"></span>' + (on ? "running" : "stopped");
        document.getElementById("backend").textContent = d.backend;
        document.getElementById("profile").textContent = d.profile;
        document.getElementById("res").textContent = d.width + "×" + d.height;
        document.getElementById("fps").textContent =
          d.measured_fps + " / " + d.target_fps + " target";
        document.getElementById("age").textContent =
          d.last_frame_age_seconds == null ? "—" : d.last_frame_age_seconds + "s";
        document.getElementById("frames").textContent = d.frames;
        document.getElementById("errors").textContent = d.errors;
        document.getElementById("last_error").textContent = d.last_error || "";
        document.getElementById("device").textContent = d.device || "—";
        document.getElementById("session").textContent = d.session_id || "—";
      } catch (e) {
        document.getElementById("running").textContent = "unreachable";
      }
    }
    refresh();
    setInterval(refresh, 2000);
  </script>
</body>
</html>
"""
