"""Phone-friendly LAN UI: sessions, live lap time, capture status, ROI debug."""

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
      --warn: #d4a017;
      --bad: #d35a5a;
      --accent: #4a8fd4;
      --line: #2a3542;
      --input: #0f1419;
      --lap: #e6c07b;
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
    .dot.warn { background: var(--warn); }
    .dot.off { background: var(--bad); }
    .dot.muted { background: var(--muted); }
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
  <p class="sub">Lap times · sessions · LAN only</p>

  <h2>Lap time</h2>
  <div class="grid">
    <div class="stat"><div class="label">Displayed</div><div class="value" id="lap-display" style="color:var(--lap)">…</div></div>
    <div class="stat"><div class="label">Last recorded</div><div class="value" id="lap-recorded">…</div></div>
    <div class="stat"><div class="label">Lap #</div><div class="value" id="lap-number">…</div></div>
    <div class="stat"><div class="label">Reader</div><div class="value" id="lap-reader">…</div></div>
  </div>

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
    <div class="stat"><div class="label">Detect</div><div class="value" id="detect-health">…</div></div>
    <div class="stat"><div class="label">FPS</div><div class="value" id="fps">…</div></div>
    <div class="stat"><div class="label">Backend</div><div class="value" id="backend">…</div></div>
    <div class="stat"><div class="label">Profile</div><div class="value" id="profile">…</div></div>
  </div>

  <h2>History</h2>
  <ul class="history" id="history"><li class="meta">Loading…</li></ul>

  <footer>
    <a href="/health">/health</a> · <a href="/metrics">/metrics</a> ·
    <a href="/api/sessions">/api/sessions</a> · <a href="/api/laps">/api/laps</a> ·
    <a href="/debug">ROI debug</a>
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

    function renderDetectHealth(det) {
      // Distinct from Capture: capture.running can stay true while detect dies.
      if (!det || det.enabled === false) {
        return '<span class="dot muted"></span>off';
      }
      if (det.health === "ok") {
        return '<span class="dot on"></span>ok';
      }
      if (det.health === "degraded") {
        return '<span class="dot warn"></span>degraded';
      }
      return '<span class="dot off"></span>stopped';
    }

    async function refreshStatus() {
      try {
        const r = await fetch("/api/status");
        const d = await r.json();
        const on = d.running;
        $("running").innerHTML =
          '<span class="dot ' + (on ? "on" : "off") + '"></span>' +
          (on ? "running" : "stopped");
        $("detect-health").innerHTML = renderDetectHealth(d.detect);
        $("backend").textContent = d.backend;
        $("profile").textContent = d.profile;
        $("fps").textContent =
          (d.measured_fps ?? "—") + " / " + (d.target_fps ?? "—");
        renderCurrent(d.session || null);
        const lap = d.lap || {};
        $("lap-display").textContent = lap.displayed_time || "—";
        $("lap-recorded").textContent = lap.last_recorded_time || "—";
        $("lap-number").textContent =
          (lap.lap_number != null ? lap.lap_number : "—");
        $("lap-reader").textContent =
          (lap.enabled === false ? "off" : (lap.reader || "—"));
      } catch (e) {
        $("running").textContent = "unreachable";
        $("detect-health").textContent = "unreachable";
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

DEBUG_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>AC Telemetry — ROI debug</title>
  <style>
    :root {
      --bg: #10151b; --panel: #1a222c; --text: #e8eef4; --muted: #8b9aab;
      --bad: #d35a5a; --accent: #4a8fd4; --line: #2a3542; --lap: #e6c07b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; padding: 1rem 1rem 2.5rem;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background: var(--bg); color: var(--text); min-height: 100vh;
    }
    h1 { font-size: 1.25rem; font-weight: 600; margin: 0 0 0.25rem; }
    .sub { color: var(--muted); margin: 0 0 1rem; font-size: 0.9rem; }
    .err {
      background: #2a1818; border: 1px solid #5a2a2a; color: var(--bad);
      border-radius: 6px; padding: 0.75rem 0.85rem; margin: 0 0 1rem;
      font-size: 0.9rem; white-space: pre-wrap; max-width: 960px;
    }
    .err.empty { display: none; }
    .meta {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 0.5rem; max-width: 960px; margin-bottom: 1rem;
    }
    .stat {
      background: var(--panel); border: 1px solid var(--line);
      border-radius: 6px; padding: 0.65rem 0.75rem;
    }
    .stat .label { color: var(--muted); font-size: 0.7rem; text-transform: uppercase; }
    .stat .value { margin-top: 0.15rem; font-variant-numeric: tabular-nums; font-size: 0.95rem; }
    figure { margin: 0 0 1.25rem; max-width: 960px; }
    figcaption { color: var(--muted); font-size: 0.8rem; margin: 0.4rem 0 0.5rem; }
    img {
      display: block; max-width: 100%; height: auto;
      background: #000; border: 1px solid var(--line); border-radius: 4px;
    }
    .crop img { max-width: 320px; image-rendering: pixelated; }
    a { color: var(--accent); }
    .actions { display: flex; gap: 0.6rem; flex-wrap: wrap; margin: 0 0 1.25rem; max-width: 960px; }
    .btn-download {
      display: inline-block; text-decoration: none;
      background: var(--accent); color: #061018; font-weight: 600;
      border-radius: 6px; padding: 0.7rem 1rem; font-size: 0.95rem;
    }
    .btn-download:hover { filter: brightness(1.08); }
    .glyph-panel {
      background: var(--panel); border: 1px solid var(--line);
      border-radius: 6px; padding: 0.85rem 1rem; margin: 0 0 1.25rem; max-width: 960px;
    }
    .glyph-panel label {
      display: block; color: var(--muted); font-size: 0.72rem;
      text-transform: uppercase; letter-spacing: 0.04em; margin: 0 0 0.35rem;
    }
    .glyph-row { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
    .glyph-row input, .glyph-row select {
      background: #0f1419; color: var(--text); border: 1px solid var(--line);
      border-radius: 6px; padding: 0.55rem 0.65rem; font: inherit; font-size: 1rem;
    }
    .glyph-row button {
      border: 0; border-radius: 6px; font: inherit; font-weight: 600;
      font-size: 0.95rem; cursor: pointer; padding: 0.65rem 1rem;
      background: #3dba7a; color: #062016;
    }
    .glyph-row button.secondary { background: #2a3542; color: var(--text); }
    .glyph-row button:disabled { opacity: 0.45; cursor: not-allowed; }
    .glyph-msg { margin: 0.55rem 0 0; font-size: 0.85rem; color: var(--muted); min-height: 1.2em; }
    .glyph-msg.err { color: var(--bad); }
    .glyph-msg.ok { color: #3dba7a; }
    .crop-wrap {
      position: relative; display: inline-block; max-width: 100%;
      cursor: crosshair; user-select: none; touch-action: none;
    }
    .crop-wrap img { max-width: 320px; image-rendering: pixelated; }
    .sel {
      position: absolute; border: 1px solid #e6c07b; background: rgba(230, 192, 123, 0.2);
      pointer-events: none; display: none;
    }
    footer { margin-top: 1.5rem; color: var(--muted); font-size: 0.78rem; }
    code { font-size: 0.85em; }
  </style>
</head>
<body>
  <h1>ROI debug</h1>
  <p class="sub">
    Latest capture frame + <code>rois.lap_time</code> overlay.
    Auto-refreshes. No ffmpeg — JPEG from the in-memory handoff.
  </p>

  <div class="err empty" id="last-error"></div>

  <div class="meta">
    <div class="stat"><div class="label">Backend</div><div class="value" id="backend">…</div></div>
    <div class="stat"><div class="label">Frame size</div><div class="value" id="size">…</div></div>
    <div class="stat"><div class="label">ROI lap_time</div><div class="value" id="roi">…</div></div>
    <div class="stat"><div class="label">Displayed</div><div class="value" id="displayed" style="color:var(--lap)">…</div></div>
    <div class="stat"><div class="label">Reader</div><div class="value" id="reader">…</div></div>
    <div class="stat"><div class="label">Session</div><div class="value" id="session">…</div></div>
  </div>

  <div class="actions">
    <a class="btn-download" id="btn-download"
       href="/api/debug/rois.jpg"
       download="ac-telemetry-rois.jpg">
      Download full-res ROI screenshot
    </a>
  </div>
  <p class="sub" style="margin-top:-0.5rem; max-width:960px">
    Saves the capture-resolution JPEG (all configured ROI boxes drawn) so you
    can measure pixels locally — the preview below is scaled to the page.
    Direct URL: <code>/api/debug/rois.jpg</code>
  </p>

  <div class="glyph-panel">
    <label for="glyph-symbol">Save glyph from lap_time ROI</label>
    <p class="sub" style="margin:0 0 0.65rem">
      Writes a PNG under <code id="glyphs-dir">glyphs_dir</code>
      (bundled <code>ac_*</code> templates may be ACC — capture real AC digits here).
      Optional: click-drag on the ROI crop below to save a sub-rect; clear selection
      to save the full strip. Leave symbol empty for <code>pending/&lt;timestamp&gt;.png</code>.
    </p>
    <div class="glyph-row">
      <select id="glyph-symbol" aria-label="Symbol">
        <option value="">(pending dump)</option>
        <option>0</option><option>1</option><option>2</option><option>3</option>
        <option>4</option><option>5</option><option>6</option><option>7</option>
        <option>8</option><option>9</option>
        <option value=":">:</option>
        <option value=".">.</option>
      </select>
      <button type="button" id="btn-save-glyph">Save glyph</button>
      <button type="button" class="secondary" id="btn-clear-sel">Clear selection</button>
    </div>
    <p class="glyph-msg" id="glyph-msg"></p>
  </div>

  <figure>
    <figcaption>Overlay preview — green box is <code>rois.lap_time</code>
      (<a href="/api/debug/overlay/lap_time.jpg" target="_blank">inline JPEG</a>)</figcaption>
    <img id="overlay" alt="Frame with lap_time ROI" src="/api/debug/overlay/lap_time.jpg" />
  </figure>

  <figure class="crop">
    <figcaption>ROI crop
      (<a href="/api/debug/roi/lap_time.jpg" target="_blank">/api/debug/roi/lap_time.jpg</a>)
      · full frame
      (<a href="/api/debug/frame.jpg" target="_blank">/api/debug/frame.jpg</a>)
      · drag to select a single glyph</figcaption>
    <div class="crop-wrap" id="crop-wrap">
      <img id="crop" alt="lap_time ROI crop" src="/api/debug/roi/lap_time.jpg" draggable="false" />
      <div class="sel" id="sel"></div>
    </div>
  </figure>

  <p class="sub" style="max-width:960px">
    Empty lap UI usually means: OCR miss, wrong ROI, no open session
    (laps not persisted), or reader/import error — see <code>last_error</code> above.
  </p>

  <footer><a href="/">← Status UI</a></footer>

  <script>
    const $ = (id) => document.getElementById(id);
    let selection = null; // {x,y,width,height} in natural image pixels
    let drag = null;

    function bust(img) {
      const base = img.getAttribute("src").split("?")[0];
      img.src = base + "?t=" + Date.now();
    }

    function setGlyphMsg(text, kind) {
      const el = $("glyph-msg");
      el.textContent = text || "";
      el.className = "glyph-msg" + (kind ? " " + kind : "");
    }

    function clearSelection() {
      selection = null;
      $("sel").style.display = "none";
      setGlyphMsg("Selection cleared — Save glyph writes the full ROI strip.");
    }

    function clientToNatural(ev) {
      const img = $("crop");
      const rect = img.getBoundingClientRect();
      const sx = img.naturalWidth / rect.width;
      const sy = img.naturalHeight / rect.height;
      const x = Math.max(0, Math.min(rect.width, ev.clientX - rect.left)) * sx;
      const y = Math.max(0, Math.min(rect.height, ev.clientY - rect.top)) * sy;
      return { x: x, y: y };
    }

    function paintSelection() {
      const img = $("crop");
      const box = $("sel");
      if (!selection || !img.naturalWidth) {
        box.style.display = "none";
        return;
      }
      const rect = img.getBoundingClientRect();
      const sx = rect.width / img.naturalWidth;
      const sy = rect.height / img.naturalHeight;
      box.style.display = "block";
      box.style.left = (selection.x * sx) + "px";
      box.style.top = (selection.y * sy) + "px";
      box.style.width = (selection.width * sx) + "px";
      box.style.height = (selection.height * sy) + "px";
    }

    function onPointerDown(ev) {
      if (!$("crop").naturalWidth) return;
      ev.preventDefault();
      const p = clientToNatural(ev);
      drag = { x0: p.x, y0: p.y };
      selection = { x: Math.floor(p.x), y: Math.floor(p.y), width: 1, height: 1 };
      paintSelection();
    }
    function onPointerMove(ev) {
      if (!drag) return;
      ev.preventDefault();
      const p = clientToNatural(ev);
      const x0 = Math.min(drag.x0, p.x);
      const y0 = Math.min(drag.y0, p.y);
      const x1 = Math.max(drag.x0, p.x);
      const y1 = Math.max(drag.y0, p.y);
      selection = {
        x: Math.floor(x0),
        y: Math.floor(y0),
        width: Math.max(1, Math.ceil(x1 - x0)),
        height: Math.max(1, Math.ceil(y1 - y0)),
      };
      paintSelection();
    }
    function onPointerUp(ev) {
      if (!drag) return;
      onPointerMove(ev);
      drag = null;
      if (selection) {
        setGlyphMsg(
          "Selection " + selection.width + "×" + selection.height +
          " @(" + selection.x + "," + selection.y + ") — pick a symbol and Save glyph."
        );
      }
    }

    const wrap = $("crop-wrap");
    wrap.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    $("btn-clear-sel").addEventListener("click", clearSelection);

    $("btn-save-glyph").addEventListener("click", async () => {
      const symbol = $("glyph-symbol").value;
      const body = {};
      if (symbol) body.symbol = symbol;
      if (selection) {
        body.x = selection.x;
        body.y = selection.y;
        body.width = selection.width;
        body.height = selection.height;
      }
      setGlyphMsg("Saving…");
      try {
        const r = await fetch("/api/debug/glyphs/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) {
          const detail = d.detail || ("HTTP " + r.status);
          setGlyphMsg(typeof detail === "string" ? detail : JSON.stringify(detail), "err");
          return;
        }
        setGlyphMsg(
          "Saved " + d.filename + " (" + d.width + "×" + d.height + ") → " + d.path,
          "ok"
        );
      } catch (e) {
        setGlyphMsg(String(e), "err");
      }
    });

    async function refreshMeta() {
      try {
        const r = await fetch("/api/status");
        const d = await r.json();
        const lap = d.lap || {};
        const errEl = $("last-error");
        const err = lap.last_error || d.last_error || "";
        if (err) {
          errEl.textContent = "last_error: " + err;
          errEl.classList.remove("empty");
        } else {
          errEl.textContent = "";
          errEl.classList.add("empty");
        }
        $("backend").textContent = d.backend || "—";
        $("size").textContent =
          (d.width && d.height) ? (d.width + "×" + d.height) : "—";
        $("displayed").textContent = lap.displayed_time || "—";
        $("reader").textContent =
          lap.enabled === false ? "off" : (lap.reader || "—");
        $("session").textContent =
          d.session_id || (d.session && d.session.session_id) || "(none)";
      } catch (e) {
        const errEl = $("last-error");
        errEl.textContent = "status unreachable: " + e;
        errEl.classList.remove("empty");
      }
      try {
        const r = await fetch("/api/debug/info");
        const d = await r.json();
        const roi = d.roi || {};
        if (roi.x != null) {
          $("roi").textContent =
            roi.x + "," + roi.y + " " + roi.width + "×" + roi.height;
        } else {
          $("roi").textContent = "(missing)";
        }
        if (d.glyphs_dir) $("glyphs-dir").textContent = d.glyphs_dir;
      } catch (e) { /* ignore */ }
    }

    function refreshImages() {
      // Skip bust while dragging so selection coords stay aligned.
      if (drag) return;
      bust($("overlay"));
      bust($("crop"));
    }

    $("crop").addEventListener("load", paintSelection);

    refreshMeta();
    setInterval(refreshMeta, 2000);
    setInterval(refreshImages, 1500);
  </script>
</body>
</html>
"""
