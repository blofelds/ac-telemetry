"""Bare GT eyeballing helper page (accuracy feature only)."""

# Served under /accuracy when accuracy is enabled. Not the phone home UI.

ACCURACY_HELPER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>GT eyeball — AC Telemetry</title>
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
      --lap: #e6c07b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(900px 480px at 80% -20%, #1c2f42 0%, transparent 55%),
        var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 1rem 1rem 2.5rem;
    }
    h1 { font-size: 1.25rem; font-weight: 600; margin: 0 0 0.25rem; }
    .sub { color: var(--muted); margin: 0 0 1rem; font-size: 0.9rem; }
    .bar {
      display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: flex-end;
      margin-bottom: 1rem; max-width: 920px;
    }
    label {
      display: block; font-size: 0.72rem; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.25rem;
    }
    select, input[type="text"] {
      background: var(--input); color: var(--text);
      border: 1px solid var(--line); border-radius: 6px;
      padding: 0.65rem 0.75rem; font: inherit; font-size: 1rem;
      min-width: 12rem;
    }
    button {
      min-height: 2.6rem; border: 0; border-radius: 6px;
      font: inherit; font-weight: 600; font-size: 1rem;
      cursor: pointer; padding: 0.6rem 1.1rem;
    }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .btn-load { background: var(--accent); color: #fff; }
    .btn-confirm { background: var(--ok); color: #062016; }
    .msg { margin: 0.5rem 0 1rem; font-size: 0.9rem; color: var(--muted); min-height: 1.2em; }
    .msg.err { color: var(--bad); }
    .msg.ok { color: var(--ok); }
    .laps { display: flex; flex-direction: column; gap: 0.75rem; max-width: 920px; }
    .lap {
      display: grid;
      grid-template-columns: minmax(0, 1.4fr) minmax(10rem, 0.8fr);
      gap: 0.75rem;
      align-items: center;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0.75rem;
    }
    @media (max-width: 640px) {
      .lap { grid-template-columns: 1fr; }
    }
    .crops {
      display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center;
      min-height: 2.5rem;
    }
    .crops img {
      max-height: 56px; width: auto; image-rendering: pixelated;
      border: 1px solid var(--line); background: #000; border-radius: 4px;
    }
    .crops .empty { color: var(--muted); font-size: 0.85rem; }
    .time-col label { margin-bottom: 0.3rem; }
    .time-col input {
      width: 100%; font-variant-numeric: tabular-nums;
      color: var(--lap); font-size: 1.15rem; font-weight: 600;
    }
    .meta { color: var(--muted); font-size: 0.75rem; margin-top: 0.35rem; }
    .footer-actions { margin-top: 1rem; display: flex; gap: 0.6rem; flex-wrap: wrap; }
    a.home { color: var(--accent); font-size: 0.85rem; }
  </style>
</head>
<body>
  <h1>GT eyeball</h1>
  <p class="sub">Two tee crops per hold · edit times · Confirm writes GT + stint notes</p>
  <p><a class="home" href="/">← Phone home</a></p>

  <div class="bar">
    <div>
      <label for="session">Session</label>
      <select id="session"></select>
    </div>
    <button type="button" class="btn-load" id="load">Load</button>
  </div>
  <div class="msg" id="msg"></div>
  <div class="laps" id="laps"></div>
  <div class="footer-actions">
    <button type="button" class="btn-confirm" id="confirm" disabled>Confirm</button>
  </div>

  <script>
    const $ = (id) => document.getElementById(id);
    const params = new URLSearchParams(location.search);
    const pathSid = (location.pathname.match(/^\\/accuracy\\/([^/]+)/) || [])[1];
    let currentSid = pathSid || params.get("session") || "";
    let pageLaps = [];

    function setMsg(text, cls) {
      const el = $("msg");
      el.textContent = text || "";
      el.className = "msg" + (cls ? " " + cls : "");
    }

    async function loadSessions() {
      const res = await fetch("/api/sessions?limit=100");
      if (!res.ok) throw new Error("Failed to list sessions");
      const data = await res.json();
      const sessions = data.sessions || data || [];
      const sel = $("session");
      sel.innerHTML = "";
      const opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = "Select session…";
      sel.appendChild(opt0);
      for (const s of sessions) {
        const id = s.session_id || s.id;
        if (!id) continue;
        const opt = document.createElement("option");
        opt.value = id;
        const track = s.track || "";
        const car = s.car || "";
        opt.textContent = id + (track || car ? " — " + [track, car].filter(Boolean).join(" / ") : "");
        sel.appendChild(opt);
      }
      if (currentSid) sel.value = currentSid;
    }

    function renderLaps(laps) {
      pageLaps = laps || [];
      const root = $("laps");
      root.innerHTML = "";
      if (!pageLaps.length) {
        root.innerHTML = "<p class='sub'>No CSV laps to prefill for this session.</p>";
        $("confirm").disabled = true;
        return;
      }
      pageLaps.forEach((lap, idx) => {
        const row = document.createElement("div");
        row.className = "lap";
        const crops = document.createElement("div");
        crops.className = "crops";
        if (lap.crops && lap.crops.length) {
          for (const c of lap.crops) {
            const img = document.createElement("img");
            img.src = c.url;
            img.alt = c.text || "ROI crop";
            img.title = (c.text || "") + " seq=" + (c.seq || "");
            crops.appendChild(img);
          }
        } else {
          const empty = document.createElement("span");
          empty.className = "empty";
          empty.textContent = "No tee crops";
          crops.appendChild(empty);
        }
        const timeCol = document.createElement("div");
        timeCol.className = "time-col";
        const lab = document.createElement("label");
        lab.textContent = "Lap " + (lap.gt_index || idx + 1);
        lab.setAttribute("for", "t" + idx);
        const inp = document.createElement("input");
        inp.type = "text";
        inp.id = "t" + idx;
        inp.value = lap.lap_time || "";
        inp.autocomplete = "off";
        inp.spellcheck = false;
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.textContent = lap.csv_lap_number != null
          ? ("CSV #" + lap.csv_lap_number)
          : "";
        timeCol.appendChild(lab);
        timeCol.appendChild(inp);
        timeCol.appendChild(meta);
        row.appendChild(crops);
        row.appendChild(timeCol);
        root.appendChild(row);
      });
      $("confirm").disabled = false;
    }

    async function loadHelper() {
      const sid = $("session").value;
      if (!sid) {
        setMsg("Pick a session first.", "err");
        return;
      }
      currentSid = sid;
      history.replaceState(null, "", "/accuracy/" + encodeURIComponent(sid));
      setMsg("Loading…");
      const res = await fetch("/api/accuracy/sessions/" + encodeURIComponent(sid) + "/helper");
      if (!res.ok) {
        const detail = await res.text();
        setMsg("Load failed: " + detail, "err");
        $("confirm").disabled = true;
        return;
      }
      const data = await res.json();
      renderLaps(data.laps || []);
      setMsg(
        (data.laps || []).length + " laps · " +
        (data.roi_frame_count || 0) + " tee frames · " +
        (data.hold_count || 0) + " holds"
      );
    }

    async function confirmGt() {
      const sid = currentSid || $("session").value;
      if (!sid) return;
      const laps = pageLaps.map((lap, idx) => {
        const inp = $("t" + idx);
        return {
          lap_time: (inp && inp.value || "").trim(),
          csv_lap_number: lap.csv_lap_number,
          note: "gt_confirmed",
        };
      });
      $("confirm").disabled = true;
      setMsg("Confirming…");
      const res = await fetch(
        "/api/accuracy/sessions/" + encodeURIComponent(sid) + "/gt/confirm",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ laps, score: true }),
        }
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg("Confirm failed: " + (body.detail || res.status), "err");
        $("confirm").disabled = false;
        return;
      }
      const wp = body.score ? body.score.write_pct : "n/a";
      setMsg(
        "Confirmed · write% " + wp +
        " · note on " + (body.csv_laps_updated || 0) + " CSV laps",
        "ok"
      );
      $("confirm").disabled = false;
    }

    $("load").addEventListener("click", () => loadHelper().catch((e) => setMsg(String(e), "err")));
    $("confirm").addEventListener("click", () => confirmGt().catch((e) => setMsg(String(e), "err")));
    $("session").addEventListener("change", () => {
      currentSid = $("session").value;
    });

    loadSessions()
      .then(() => {
        if (currentSid) {
          $("session").value = currentSid;
          return loadHelper();
        }
      })
      .catch((e) => setMsg(String(e), "err"));
  </script>
</body>
</html>
"""
