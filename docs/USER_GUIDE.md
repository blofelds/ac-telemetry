# User guide (Slice 1)

How to run **ac-telemetry** today: prove capture (mock or V4L2), create/end driving sessions from a phone, scrape metrics. Lap OCR is **not** in this slice.

## Requirements

- Python 3.11+
- For **mock** (default): no camera, no OpenCV
- For **V4L2**: USB UVC capture device + `pip install -e ".[capture]"` (OpenCV headless)

## Install

```bash
git clone https://github.com/blofelds/ac-telemetry.git
cd ac-telemetry
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run with mock capture (laptop or Pi, no dongle)

```bash
ac-telemetry
```

Defaults (`config/default.yaml`):

- Backend: `mock`
- Profile: `pi2b` (1280×720 @ 10 fps, hard caps ≤720p / ≤15 fps)
- Bind: `0.0.0.0:8741`

Localhost-only:

```bash
ac-telemetry --host 127.0.0.1
```

### What you should see

1. Open `http://127.0.0.1:8741/` — phone-friendly session form + capture status.
2. Enter **track**, **car**, optional **notes** → **Start session**.
3. **End session** when done; history lists prior runs.
4. `GET /api/sessions` — JSON history; `GET /health` — capture + current session.
5. `GET /metrics` — Prometheus text (capture + session counters).
6. `data/sessions/sessions.csv` — append-only rows (start then stop per id).

Capture still runs for FPS/health proof. Sessions are **not** created by capture start/stop anymore — you start them from the UI or API.

## Run with a real capture device (Pi)

1. Plug in the HDMI capture dongle; confirm the PS5 path has a live display (splitter → TV).
2. Install capture extras: `pip install -e ".[capture]"`.
3. Find the device: `v4l2-ctl --list-devices` (often `/dev/video0`).
4. Start:

```bash
ac-telemetry --backend v4l2
# or
AC_TELEMETRY_BACKEND=v4l2 AC_TELEMETRY_DEVICE=/dev/video0 ac-telemetry
```

5. On a phone on the same LAN: `http://<pi-ip>:8741/` → start a session before you drive.

### systemd (sketch)

See [`../deploy/ac-telemetry.service`](../deploy/ac-telemetry.service). Copy to `/etc/systemd/system/`, adjust paths/user, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ac-telemetry
```

The Pi user needs membership in the `video` group for `/dev/video*`.

## Sessions API

```bash
# Start
curl -s -X POST http://127.0.0.1:8741/api/sessions \
  -H 'Content-Type: application/json' \
  -d '{"track":"Monza","car":"Ferrari 488 GT3","notes":"wet practice"}'

# List
curl -s 'http://127.0.0.1:8741/api/sessions?limit=20'

# End current
curl -s -X POST http://127.0.0.1:8741/api/sessions/current/end
```

Only one session may be open at a time. A second `POST /api/sessions` returns **409** until you end the current one.

## CSV sessions

| Column | Meaning |
| --- | --- |
| `session_id` | Short id |
| `started_at` / `ended_at` | UTC ISO timestamps |
| `track` / `car` / `notes` | Manual metadata from phone/API |
| `backend` / `profile` / `device` | Capture snapshot (filled when available) |
| `width` / `height` / `target_fps` | Capture geometry |
| `frames` / `errors` / `avg_fps` | Snapshot at end (if capture was running) |
| `status` | `running` or `stopped` |

File: `data/sessions/sessions.csv` (or `AC_TELEMETRY_DATA_DIR`). Append-only; last row per `session_id` wins. Slice 0 CSVs without `track`/`car`/`notes` are migrated on next open.

## Configuration quick reference

| Setting | Env / flag | Default |
| --- | --- | --- |
| Profile | `AC_TELEMETRY_PROFILE` | `pi2b` |
| Backend | `AC_TELEMETRY_BACKEND` / `--backend` | `mock` |
| Device | `AC_TELEMETRY_DEVICE` | `/dev/video0` |
| Host / port | `AC_TELEMETRY_HOST` / `--port` | `0.0.0.0` / `8741` |
| Data dir | `AC_TELEMETRY_DATA_DIR` | `data/sessions` |

## What this guide does not cover yet

- Lap / sector detection (Slice 2)
- Grafana dashboards (Slice 3)
- Driving signals (Slice 4)
- SQLite (Slice 5)

See [FEATURES.md](FEATURES.md) and [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
