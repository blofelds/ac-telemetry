# AC Telemetry

Live **HDMI capture** telemetry for **Assetto Corsa on PS5**, running headless on a **Raspberry Pi**.

This is **not** a video-file extractor. Sister project [blofelds/acc-telemetry](https://github.com/blofelds/acc-telemetry) analyzes recorded gameplay offline. **ac-telemetry** sits on the Pi, opens a USB UVC capture device, and exposes health, Prometheus metrics, and a LAN status page — building toward live lap logging.

**Current slice: Slice 0 — foundation + capture proof.** No OCR, no lap times, no Grafana yet. CSV session stubs only (SQLite later).

---

## Why this exists

Console Assetto Corsa has no Shared Memory / native telemetry API. The practical path is:

```
PS5 ──HDMI──► splitter ──► TV
                    └──► USB UVC capture ──► Raspberry Pi (this service)
```

Slice 0 proves the Pi can **see** HDMI at a sustainable FPS before any detection work.

### First board: Raspberry Pi 2 Model B

A Pi 2B is available now; the capture kit is in delivery. Design is capped for 2B:

| Constraint | Slice 0 default (`pi2b` profile) |
| --- | --- |
| USB 2.0 / CPU / 1 GB RAM | ≤720p, ≤15 fps (default 1280×720 @ 10 fps) |
| Early product | Lap times later; **no** throttle/brake/speed/gear on 2B |
| Persistence | **CSV first**; SQLite deferred |

A `pi5` profile exists as a placeholder so the upgrade path is config, not a rewrite.

---

## Quick start (mock capture — no hardware)

Use this on a laptop or the Pi before the dongle arrives.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Mock backend is the default in config/default.yaml
ac-telemetry
# or: python -m ac_telemetry.main
```

Then open:

- Status UI: [http://127.0.0.1:8741/](http://127.0.0.1:8741/)
- Health JSON: [http://127.0.0.1:8741/health](http://127.0.0.1:8741/health)
- Prometheus: [http://127.0.0.1:8741/metrics](http://127.0.0.1:8741/metrics)

Override bind for localhost-only:

```bash
ac-telemetry --host 127.0.0.1 --port 8741
```

Session rows append to `data/sessions/sessions.csv` on capture start/stop.

---

## Quick start (V4L2 on the Pi)

When the HDMI capture dongle is plugged in:

```bash
# Optional OpenCV stack for real devices
pip install -e ".[capture]"

# List devices (on the Pi)
v4l2-ctl --list-devices

ac-telemetry --backend v4l2
# or: AC_TELEMETRY_BACKEND=v4l2 AC_TELEMETRY_DEVICE=/dev/video0 ac-telemetry
```

Default listen address is `0.0.0.0:8741` so a phone on the LAN can open `http://<pi-ip>:8741/`.

A systemd unit sketch lives at [`deploy/ac-telemetry.service`](deploy/ac-telemetry.service).

---

## Project structure

```
ac_telemetry/
  capture/     # Mock + V4L2/OpenCV frame loop (profile-aware)
  api/         # /health, /metrics, /api/status
  store/       # CSV session stub writers
  web/         # Minimal LAN status page
  settings.py  # YAML + env config (pi2b / pi5 profiles)
config/
  default.yaml
deploy/
  ac-telemetry.service
docs/          # Index + core stubs (grow with later slices)
```

---

## Configuration

| Setting | Env / flag | Default |
| --- | --- | --- |
| Capture profile | `AC_TELEMETRY_PROFILE` | `pi2b` |
| Backend | `AC_TELEMETRY_BACKEND` / `--backend` | `mock` |
| Device | `AC_TELEMETRY_DEVICE` | `/dev/video0` |
| Bind host | `AC_TELEMETRY_HOST` / `--host` | `0.0.0.0` |
| Port | `AC_TELEMETRY_PORT` / `--port` | `8741` |
| Session CSV dir | `AC_TELEMETRY_DATA_DIR` | `data/sessions` |
| Config file | `AC_TELEMETRY_CONFIG` / `--config` | `config/default.yaml` |

`pi2b` hard caps: max 1280×720, max 15 fps. Requested values are clamped.

---

## Metrics (Prometheus)

| Metric | Meaning |
| --- | --- |
| `ac_telemetry_up` | Process is up |
| `ac_telemetry_capture_running` | Capture loop running |
| `ac_telemetry_capture_fps` | Measured FPS |
| `ac_telemetry_last_frame_age_seconds` | Age of last good frame |
| `ac_telemetry_capture_errors_total` | Error counter |
| `ac_telemetry_frames_total` | Frames since process start |

---

## Stack

- Python 3.11+
- FastAPI + uvicorn
- `prometheus_client`
- OpenCV (optional extra `[capture]`) for V4L2
- CSV files for early persistence

---

## What works now vs later

| Now (Slice 0) | Later |
| --- | --- |
| Mock + V4L2 capture loop | Lap OCR (Slice 2) |
| `/health`, `/metrics`, status UI | Phone session metadata (Slice 1) |
| CSV session start/stop stub | SQLite (Slice 5) |
| `pi2b` / `pi5` profiles | Driving signals on Pi 5 (Slice 4) |
| systemd sketch | Grafana starter (Slice 3) |

**Out of scope for this slice:** OCR, laps, sectors, throttle/brake/speed/gear, Grafana, Tailscale, SQLite.

---

## Documentation

See [`docs/README.md`](docs/README.md) for the documentation index (acc-telemetry layout philosophy; honest Slice 0 stubs).

---

## Limitations

- No hardware validation until the capture kit arrives; mock is the default.
- HDCP / splitter quirks can black-screen the capture path — validate before OCR work.
- Status UI is read-only; no session create/edit yet.
- Trusted home LAN assumed (no auth).

---

## License

Not decided yet — treat as private until Gary sets one.
