"""Phone-friendly LAN UI: session create/end + capture status (Slice 1)."""

STATUS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>AC Telemetry</title>
  <style>
    :root {
      --bg: #10151b;
      --panel: #1a222c;
      --text: #e8eef4;
      --muted: #8b9aab;
      --ok: #3dba7a;
      --bad: #d35a5a;
      --accent: #4a8fd4;
      --line: #2a3542;
      --input: #0f1419;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(900px 480px at 80% -20%, #1c2f42 0%, transparent 55%),
        radial-gradient(700px 400px at 0% 100%, #162018 0%, transparent 50%),
        var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 1rem 1rem 2.5rem;
    }
    h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 0.2rem; }
    h2 { font-size: 0.85rem; font-weight: 600; text-transform: uppercase;
         letter-spacing: 0.05em; color: var(--muted); margin: 1.5rem 0 0.75rem; }
    .sub { color: var(--muted); margin: 0 0 1.25rem; font-size: 0.92rem; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 1rem;
      max-width: 420px;
    }
    label {
      display: block;
      font-size: 0.78rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin: 0.65rem 0 0.3rem;
    }
    label:first-child { margin-top: 0; }
    input, textarea {
      width: 100%;
      background: var(--input);
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0.7rem 0.75rem;
      font: inherit;
      font-size: 1rem;
    }
    textarea { min-height: 4.5rem; resize: vertical; }
    .actions { display: flex; gap: 0.6rem; margin-top: 1rem; flex-wrap: wrap; }
    button {
      flex: 1;
      min-height: 2.75rem;
      border: 0;
      border-radius: 6px;
      font: inherit;
      font-weight: 600;
      font-size: 1rem;
      cursor: pointer;
      padding: 0.65rem 1rem;
    }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .btn-start { background: var(--ok); color: #062016; }
    .btn-end { background: var(--bad); color: #fff; }
    .msg { margin-top: 0.75rem; font-size: 0.9rem; color: var(--muted); min-height: 1.2em; }
    .msg.err { color: var(--bad); }
    .current {
      margin-top: 0.85rem;
      padding-top: 0.85rem;
      border-top: 1px solid var(--line);
      font-size: 0.92rem;
    }
    .current strong { color: var(--ok); }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 0.55rem;
      max-width: 420px;
    }
    .stat {
      background: var(--panel);
      border: 1px solid var(--line);
      padding: 0.75rem 0.85rem;
      border-radius: 6px;
    }
    .stat .label { color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; }
    .stat .value { font-size: 1.05rem; margin-top: 0.2rem; font-variant-numeric: tabular-nums; }
    .dot { display: inline-block; width: 0.5rem; height: 0.5rem; border-radius: 50%; margin-right: 0.35rem; }
    .dot.on { background: var(--ok); }
    .dot.off { background: var(--bad); }
    .history {
      list-style: none;
      margin: 0;
      padding: 0;
      max-width: 420px;
    }
    .history li {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0.75rem 0.85rem;
      margin-bottom: 0.5rem;
      font-size: 0.9rem;
    }
    .history .meta { color: var(--muted); font-size: 0.78rem; margin-top: 0.25rem; }
    .badge {
      display: inline-block;
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 0.15rem 0.4rem;
      border-radius: 3px;
      margin-left: 0.35rem;
      vertical-align: middle;
    }
    .badge.run { background: #1e3d2e; color: var(--ok); }
    .badge.stop { background: #2a3038; color: var(--muted); }
    a { color: var(--accent); }
    footer { margin-top: 1.75rem; color: var(--muted); font-size: 0.78rem; max-width: 420px; }
  </style>
</head>
<body>
  <h1>AC Telemetry</h1>
  <p class="sub">Session logger · phone-friendly · LAN only</p>

  <h2>Session</h2>
  <div class="panel" id="session-panel">
    <label for="track">Track</label>
    <input id="track" type="text" autocomplete="off" placeholder="e.g. Monza" />
    <label for="car">Car</label>
    <input id="car" type="text" autocomplete="off" placeholder="e.g. Ferrari 488 GT3" />
    <label for="notes">Notes</label>
    <textarea id="notes" placeholder="Optional — tire set, weather, setup…"></textarea>
    <div class="actions">
      <button type="button" class="btn-start" id="btn-start">Start session</button>
      <button type="button" class="btn-end" id="btn-end" disabled>End session</button>
    </div>
    <p class="msg" id="msg"></p>
    <div class="current" id="current">No session running.</div>
  </div>

  <h2>Capture</h2>
  <div class="grid">
    <div class="stat"><div class="label">Capture</div><div class="value" id="running">…</div></div>
    <div class="stat"><div class="label">FPS</div><div class="value" id="fps">…</div></div>
    <div class="stat"><div class="label">Backend</div><div class="value" id="backend">…</div></div>
    <div class="stat"><div class="label">Profile</div><div class="value" id="profile">…</div></div>
  </div>

  <h2>History</h2>
  <ul class="history" id="history"><li class="meta">Loading…</li></ul>

  <footer>
    <a href="/health">/health</a> · <a href="/metrics">/metrics</a> ·
    <a href="/api/sessions">/api/sessions</a> · Slice 1
  </footer>

  <script>
    const $ = (id) => document.getElementById(id);
    let currentId = null;

    function setMsg(text, isErr) {
      const el = $("msg");
      el.textContent = text || "";
      el.className = "msg" + (isErr ? " err" : "");
    }

    function renderCurrent(session) {
      if (!session) {
        currentId = null;
        $("current").textContent = "No session running.";
        $("btn-start").disabled = false;
        $("btn-end").disabled = true;
        return;
      }
      currentId = session.session_id;
      $("current").innerHTML =
        "<strong>Running</strong> · " +
        (session.track || "(no track)") + " · " +
        (session.car || "(no car)") +
        "<br><span style=\\"color:var(--muted)\\">id " + session.session_id +
        " · started " + (session.started_at || "—") + "</span>";
      $("btn-start").disabled = true;
      $("btn-end").disabled = false;
      if (!$("track").value) $("track").value = session.track || "";
      if (!$("car").value) $("car").value = session.car || "";
      if (!$("notes").value) $("notes").value = session.notes || "";
    }

    function renderHistory(sessions) {
      const ul = $("history");
      if (!sessions || !sessions.length) {
        ul.innerHTML = "<li class=\\"meta\\">No sessions yet.</li>";
        return;
      }
      ul.innerHTML = sessions.map((s) => {
        const badge = s.status === "running"
          ? "<span class=\\"badge run\\">running</span>"
          : "<span class=\\"badge stop\\">stopped</span>";
        const title = (s.track || "—") + " · " + (s.car || "—");
        const meta = (s.started_at || "") +
          (s.ended_at ? " → " + s.ended_at : "") +
          " · " + (s.session_id || "");
        const notes = s.notes
          ? "<div class=\\"meta\\">" + escapeHtml(s.notes) + "</div>"
          : "";
        return "<li><div>" + escapeHtml(title) + badge + "</div>" +
          "<div class=\\"meta\\">" + escapeHtml(meta) + "</div>" + notes + "</li>";
      }).join("");
    }

    function escapeHtml(s) {
      return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    async function refreshStatus() {
      try {
        const r = await fetch("/api/status");
        const d = await r.json();
        const on = d.running;
        $("running").innerHTML =
          '<span class="dot ' + (on ? "on" : "off") + '"></span>' +
          (on ? "running" : "stopped");
        $("backend").textContent = d.backend;
        $("profile").textContent = d.profile;
        $("fps").textContent =
          (d.measured_fps ?? "—") + " / " + (d.target_fps ?? "—");
        renderCurrent(d.session || null);
      } catch (e) {
        $("running").textContent = "unreachable";
      }
    }

    async function refreshHistory() {
      try {
        const r = await fetch("/api/sessions?limit=20");
        const d = await r.json();
        renderHistory(d.sessions || []);
        if (d.current) renderCurrent(d.current);
      } catch (e) {
        $("history").innerHTML = "<li class=\\"meta\\">Could not load history.</li>";
      }
    }

    $("btn-start").addEventListener("click", async () => {
      setMsg("Starting…");
      try {
        const r = await fetch("/api/sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            track: $("track").value.trim(),
            car: $("car").value.trim(),
            notes: $("notes").value.trim(),
          }),
        });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) {
          setMsg(d.detail || ("HTTP " + r.status), true);
          return;
        }
        setMsg("Session started.");
        renderCurrent(d.session);
        refreshHistory();
      } catch (e) {
        setMsg(String(e), true);
      }
    });

    $("btn-end").addEventListener("click", async () => {
      if (!currentId) return;
      setMsg("Ending…");
      try {
        const r = await fetch("/api/sessions/" + encodeURIComponent(currentId) + "/end", {
          method: "POST",
        });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) {
          setMsg(d.detail || ("HTTP " + r.status), true);
          return;
        }
        setMsg("Session ended.");
        $("track").value = "";
        $("car").value = "";
        $("notes").value = "";
        renderCurrent(null);
        refreshHistory();
      } catch (e) {
        setMsg(String(e), true);
      }
    });

    refreshStatus();
    refreshHistory();
    setInterval(refreshStatus, 2000);
    setInterval(refreshHistory, 10000);
  </script>
</body>
</html>
"""
