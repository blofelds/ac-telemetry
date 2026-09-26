# Features (Slice 1)

Honest inventory of what ships now versus what is planned. Product goals (live laps, later driving signals) remain; this page tracks **delivered** surface area.

## Delivered in Slice 0 (still present)

### Capture profiles

- Named profiles: **`pi2b`** (default) and **`pi5`** (placeholder).
- `pi2b` hard caps: ≤1280×720, ≤15 fps (default request 10 fps).

### Capture backends

- **`mock`** — synthetic frames at the profile FPS (default; no hardware).
- **`v4l2`** — OpenCV `VideoCapture` on a UVC device (optional `[capture]` extra).

### Health and capture metrics

- `GET /health`, `GET /metrics`, `GET /api/status`.

### Ops sketch

- `deploy/ac-telemetry.service` — systemd unit outline for headless Pi.

## Delivered in Slice 1

### Manual sessions (CSV)

- Create/end a session from the LAN UI or REST API with **track**, **car**, **notes**.
- Persist to `sessions.csv` (append-only; last write per id wins).
- One open session at a time (409 on double-start).
- Ending a session snapshots current capture stats when available.
- Capture **no longer** auto-creates sessions (API owns lifecycle).

### Session API

- `POST /api/sessions` — start
- `POST /api/sessions/{id}/end` / `POST /api/sessions/current/end` — end
- `GET /api/sessions` — history + current
- `GET /api/sessions/current` / `GET /api/sessions/{id}` — lookup

### Session Prometheus counters

- `ac_telemetry_sessions_started_total`
- `ac_telemetry_sessions_ended_total`
- `ac_telemetry_sessions_open`

### Phone-friendly UI

- Large tap targets for Start / End; track/car/notes fields; recent history list.
- Capture status strip retained so Slice 0 health proof stays visible.

## Explicitly not in Slice 1

| Area | Status |
| --- | --- |
| Lap / sector OCR | Slice 2 |
| Throttle, brake, speed, gear | Slice 4 (Pi 5) |
| Grafana | Slice 3+ |
| SQLite | Slice 5 |
| Tailscale / auth | Later |
| Continuous video recording | Non-goal |

## Why this order

Sessions with human metadata come **before** OCR so every later lap row has a parent session, and so the phone UX is usable while the capture kit / OCR work continues. CSV stays first so a 1 GB Pi does not need a database daemon.

## Development journey

- **Slice 0:** Capture proof + health/metrics; sessions were capture-tied stubs.
- **Slice 1:** Decoupled sessions from capture hooks; phone owns start/end; added track/car/notes columns and session counters.
- Chose **one open session** to keep the Pi mental model simple (single driver).
- Kept **append-only CSV** rather than in-place rewrite so crashes do not corrupt the file mid-write.

Further journey notes land here as slices ship (and in Historical when approaches are abandoned).
