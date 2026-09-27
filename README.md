# AC Telemetry

Live **HDMI capture** telemetry for **Assetto Corsa on PS5**, running headless on a **Raspberry Pi**.

This is **not** a video-file extractor. Sister project [blofelds/acc-telemetry](https://github.com/blofelds/acc-telemetry) analyzes recorded gameplay offline. **ac-telemetry** sits on the Pi, opens a USB UVC capture device, logs **lap times** to CSV, and exposes health, Prometheus metrics, and a LAN phone UI.

**Current:** capture + sessions + **lap-time detection** (mock reader by default; optional tesseract OCR). No sectors / throttle / brake / SQLite yet.

---

## Why this exists

Console Assetto Corsa has no Shared Memory / native telemetry API. The practical path is:

```
PS5 ──HDMI──► splitter ──► TV
                    └──► USB UVC capture ──► Raspberry Pi (this service)
```

### First board: Raspberry Pi 2 Model B

| Constraint | `pi2b` profile |
| --- | --- |
| USB 2.0 / CPU / 1 GB RAM | ≤720p, ≤15 fps (default 1280×720 @ 10 fps) |
| Early product | **Lap times**; no throttle/brake/speed/gear on 2B |
| Persistence | **CSV first**; SQLite deferred |
| Detect | Tiny `lap_time` ROI @ ~2 fps; debounce; drop under pressure |

A `pi5` profile exists as a placeholder so the upgrade path is config, not a rewrite.

---

## Quick start (mock capture — no hardware)

Default config uses **v4l2** (Pi + dongle). On a laptop / CI, force mock:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# No capture device — override the v4l2 default
ac-telemetry --backend mock
# or: AC_TELEMETRY_BACKEND=mock ac-telemetry
```

Then open:

- Phone UI: [http://127.0.0.1:8741/](http://127.0.0.1:8741/)
- Health: [http://127.0.0.1:8741/health](http://127.0.0.1:8741/health)
- Laps API: [http://127.0.0.1:8741/api/laps](http://127.0.0.1:8741/api/laps)
- Prometheus: [http://127.0.0.1:8741/metrics](http://127.0.0.1:8741/metrics)

Start a session from the UI. With the default **mock** lap reader, a synthetic completed lap appears every ~45s (`detect.lap_time.mock_interval_seconds`) and appends to `data/sessions/laps.csv`.

### Raspberry Pi 2B install (capture reality)

| Do | Do not |
| --- | --- |
| `sudo apt install python3-opencv` | `pip install -e ".[capture]"` on the 2B (wheels often **SIGILL**) |
| `python3 -m venv --system-site-packages .venv` | Expect pip OpenCV/numpy wheels to be safe on ARMv7 |
| Prefer **MJPEG** (`prefer_mjpeg: true`, default) | Push 1080p / high FPS on USB2 |
| Base: `pip install -e .` (plain uvicorn) | `.[standard]` (uvloop compile hang) |

OpenBLAS note still applies if you use pip numpy on Pi OS: `sudo apt install libopenblas0`. See [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

Optional OCR (heavy; not the Pi 2B default):

```bash
sudo apt install tesseract-ocr
pip install -e ".[ocr]"
# then set detect.lap_time.reader: tesseract and calibrate rois.lap_time
```

---

## Quick start (V4L2 on the Pi)

```bash
# Pi 2B — system OpenCV into a venv that can see it
sudo apt install python3-opencv
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .

v4l2-ctl --list-devices
# backend defaults to v4l2 in config/default.yaml
ac-telemetry
```

Default listen address is `0.0.0.0:8741`. Systemd sketch: [`deploy/ac-telemetry.service`](deploy/ac-telemetry.service).

Calibrate `rois.lap_time` on the Pi: open
[`http://<pi-ip>:8741/debug`](http://127.0.0.1:8741/debug)
(or `GET /api/debug/frame.jpg` and `GET /api/debug/roi/lap_time.jpg`).

---

## Project structure

```
ac_telemetry/
  capture/     # Mock + V4L2 frame loop (latest-frame handoff)
  detect/      # Low-FPS lap_time ROI + pluggable readers
  api/         # /health, /metrics, sessions, laps
  store/       # CSV sessions + laps
  web/         # Phone UI
config/
  default.yaml # profiles, rois.lap_time, detect.*
```

---

## Configuration (lap times)

| Setting | Where | Default |
| --- | --- | --- |
| `rois.lap_time` | YAML | `{x,y,width,height}` for 720p last-lap HUD |
| `detect.enabled` | YAML | `true` |
| `detect.fps` | YAML | `2.0` |
| `detect.debounce_reads` | YAML | `2` |
| `detect.lap_time.reader` | YAML | `mock` (`tesseract` optional) |
| `detect.lap_time.mode` | YAML | `last_lap` (or `current_timer`) |
| `prefer_mjpeg` | YAML / env | `true` |

Point `rois.lap_time` at the **last completed lap** display when using `mode: last_lap`. Recalibrate for your capture crop/resolution.

---

## Metrics (Prometheus)

Capture + session metrics, plus:

| Metric | Meaning |
| --- | --- |
| `ac_telemetry_detect_latency_seconds` | Last detect tick duration |
| `ac_telemetry_detect_failures_total` | OCR/read failures |
| `ac_telemetry_detect_drops_total` | Ticks dropped under pressure |
| `ac_telemetry_laps_recorded_total` | Laps written to CSV |
| `ac_telemetry_signal_lap_time_ms` | Last displayed lap time (ms) |

---

## API (laps)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/laps/current` | Live displayed / last recorded lap |
| `GET` | `/api/laps` | Recent lap rows (optional `session_id`) |
| `GET` | `/debug` | ROI calibration page (overlay + crop + `last_error`) |
| `GET` | `/api/debug/frame.jpg` | Full latest frame JPEG |
| `GET` | `/api/debug/roi/lap_time.jpg` | `rois.lap_time` crop JPEG |
| `GET` | `/api/debug/overlay/lap_time.jpg` | Frame with ROI rectangle |

Sessions API unchanged (`POST /api/sessions`, etc.).

---

## What works now vs later

| Now | Later |
| --- | --- |
| Mock + V4L2 capture | Sectors (iff cheap) |
| Sessions (track/car/notes) | SQLite |
| Lap times → CSV + live UI | Driving signals on Pi 5 |
| Mock reader + optional tesseract | Grafana starter |
| Detect latency / failure / lap metrics | Tailscale / auth |

---

## Documentation

See [`docs/README.md`](docs/README.md).

---

## Limitations

- Default lap path is **mock** until you calibrate ROI + enable tesseract (or another reader).
- Tesseract on Pi 2B is best-effort; keep ROI tiny or stay on mock while validating capture.
- HDCP / splitter quirks can black-screen the capture path.
- Trusted home LAN assumed (no auth).

---

## License

Not decided yet — treat as private until Gary sets one.
