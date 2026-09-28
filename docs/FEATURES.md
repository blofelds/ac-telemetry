# Features

Honest inventory of what ships now versus what is planned.

## Delivered

### Capture profiles

- Named profiles: **`pi2b`** (default) and **`pi5`** (placeholder).
- `pi2b` hard caps: ≤1280×720, ≤15 fps (default request 10 fps).
- Optional **MJPEG** preference for UVC devices (`prefer_mjpeg`).

### Capture backends

- **`v4l2`** — OpenCV `VideoCapture` on a UVC device (default; system OpenCV on Pi 2B).
- **`mock`** — synthetic frames at the profile FPS (`--backend mock` / `AC_TELEMETRY_BACKEND=mock`).

### Health and capture metrics

- `GET /health`, `GET /metrics`, `GET /api/status`.

### Manual sessions (CSV)

- Create/end a session from the LAN UI or REST API with **track**, **car**, **notes**.
- Persist to `sessions.csv` (append-only; last write per id wins).
- One open session at a time (409 on double-start).

### Lap times (CSV)

- Configurable `rois.lap_time` rectangle in YAML.
- Low-FPS detect worker (default 2 fps) with debounce and drop-under-pressure.
- Pluggable readers: **`mock`** (default, no OCR) and optional **`tesseract`**.
- Modes: `last_lap` (default) or `current_timer` (record on timer reset).
- Persist rows to `laps.csv`; live state on UI + `GET /api/laps/current`.
- Metrics: detect latency, failures, drops, laps recorded, signal gauge.

### Phone-friendly UI

- Lap strip (displayed / last recorded / lap # / reader).
- Session start/end + history + capture status.
- **ROI debug** at `/debug` — overlay + crop JPEGs from the capture handoff; **Download full-res ROI screenshot** (`/api/debug/rois.jpg`) for measuring pixels locally; shows `last_error`.

### Ops sketch

- `deploy/ac-telemetry.service` — systemd unit outline for headless Pi.

## Not yet

| Area | Status |
| --- | --- |
| Sector times | Deferred unless cheap |
| Throttle, brake, speed, gear | Later (Pi 5 path) |
| Grafana starter | Later |
| SQLite | Later |
| Tailscale / auth | Later |
| Continuous video recording | Non-goal |

## Why this order

Sessions with human metadata come **before** lap rows so every lap has a parent session. CSV stays first so a 1 GB Pi does not need a database daemon. Mock lap reader proves the store/API/metrics path before spending Pi CPU on OCR.

## Development journey

- Capture proof + health/metrics first; sessions were briefly capture-tied stubs.
- Decoupled sessions from capture hooks; phone owns start/end.
- Lap detect runs on a **separate thread**, samples the latest frame, crops a tiny ROI, and never queues frames (drop old under pressure).
- Chose **mock reader default** so Pi 2B can validate CSV/UI without tesseract.
- Prefer **apt OpenCV + system-site-packages** on 2B after pip wheels SIGILL'd.
