# Features (Slice 0)

Honest inventory of what ships now versus what is planned. Product goals (live laps, later driving signals) remain; this page tracks **delivered** surface area.

## Delivered in Slice 0

### Capture profiles

- Named profiles: **`pi2b`** (default) and **`pi5`** (placeholder).
- `pi2b` hard caps: ≤1280×720, ≤15 fps (default request 10 fps).
- Caps live in config so business logic does not hard-code board limits.

### Capture backends

- **`mock`** — synthetic frames at the profile FPS (default; no hardware).
- **`v4l2`** — OpenCV `VideoCapture` on a UVC device (optional `[capture]` extra).

### Health and metrics

- `GET /health` — process + capture summary JSON.
- `GET /metrics` — Prometheus: up, capture running, FPS, last frame age, errors, frames.
- `GET /api/status` — UI-friendly status payload.

### LAN status UI

- `GET /` — minimal page: running state, backend, profile, resolution, FPS, frame age, errors.
- Auto-refresh every 2s. No session create/edit controls (those are Slice 1).

### CSV session stub

- On capture start/stop, append rows to `data/sessions/sessions.csv`.
- Stable columns intended to map cleanly when SQLite arrives (Slice 5).

### Ops sketch

- `deploy/ac-telemetry.service` — systemd unit outline for headless Pi.

## Explicitly not in Slice 0

| Area | Status |
| --- | --- |
| Lap / sector OCR | Slice 2 |
| Phone session metadata UX | Slice 1 |
| Throttle, brake, speed, gear | Slice 4 (Pi 5) |
| Grafana | Slice 3+ |
| SQLite | Slice 5 |
| Tailscale / auth | Later |
| Continuous video recording | Non-goal |

## Why this order

Pi 2B CPU and USB 2.0 leave little room for OCR + decode mistakes. Slice 0 exists to **prove HDMI visibility and service shape** before investing in detection. Mock capture lets development continue while the dongle is in transit.

## Development journey (start)

- Chose **CSV before SQLite** so persistence stays trivial on a 1 GB board and export to Obsidian stays a file copy.
- Chose **named profiles** (`pi2b` / `pi5`) so raising resolution/FPS later is configuration.
- Kept **one process** (capture + HTTP + metrics) to avoid multi-service overhead on the 2B.

Further journey notes will land here as slices ship (and in Historical when approaches are abandoned).
