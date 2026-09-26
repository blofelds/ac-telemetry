# User guide (Slice 0)

How to run **ac-telemetry** today: prove capture (mock or V4L2), read status, scrape metrics. Lap logging and phone session UX are **not** in this slice.

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

Default install uses plain uvicorn (no uvloop). On Pi 2B, if an older checkout hung on `Building wheel for uvloop`, Ctrl+C, update the tree, and re-run `pip install -e .`. Skip `.[standard]` on the 2B. `.[capture]` (OpenCV) is separate and heavy — only for real V4L2.

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

1. Open `http://127.0.0.1:8741/` — status shows **running**, backend **mock**, FPS near the target.
2. `GET /health` — JSON with capture fields.
3. `GET /metrics` — Prometheus text (fps, last frame age, errors).
4. `data/sessions/sessions.csv` — a **running** row on start; a **stopped** row when the process exits.

Stop with Ctrl+C; the capture thread flushes the session stop row.

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

5. On a phone on the same LAN: `http://<pi-ip>:8741/`.

### systemd (sketch)

See [`../deploy/ac-telemetry.service`](../deploy/ac-telemetry.service). Copy to `/etc/systemd/system/`, adjust paths/user, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ac-telemetry
```

The Pi user needs membership in the `video` group for `/dev/video*`.

## CSV sessions (stub)

| Column | Meaning |
| --- | --- |
| `session_id` | Short id for the capture run |
| `started_at` / `ended_at` | UTC ISO timestamps |
| `backend` / `profile` / `device` | How capture was configured |
| `width` / `height` / `target_fps` | Negotiated / requested geometry |
| `frames` / `errors` / `avg_fps` | Filled on stop |
| `status` | `running` then `stopped` |

This is a **stub** for Slice 0 — not lap data. SQLite arrives much later.

## Configuration knobs

Prefer env vars on the Pi so the unit file stays simple:

```bash
export AC_TELEMETRY_PROFILE=pi2b
export AC_TELEMETRY_BACKEND=v4l2
export AC_TELEMETRY_DEVICE=/dev/video0
export AC_TELEMETRY_HOST=0.0.0.0
export AC_TELEMETRY_PORT=8741
```

Or edit `config/default.yaml`. Profile `pi5` is a placeholder; do not assume it is tuned.

## What this guide does **not** cover yet

- Creating sessions from the phone (track, car, notes) — Slice 1
- Lap / sector detection — Slice 2
- Grafana dashboards — Slice 3+
- Throttle / brake / speed / gear — Pi 5 path (Slice 4)

See [FEATURES.md](FEATURES.md) and [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
