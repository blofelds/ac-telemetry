# User guide

How to run **ac-telemetry**: capture (mock or V4L2), sessions, and lap-time logging.

## Requirements

- Python 3.11+
- For **mock** (laptop/CI): `ac-telemetry --backend mock` — no camera, no OpenCV
- For **V4L2 on Pi 2B** (YAML default): `apt` OpenCV + venv `--system-site-packages` (see below)
- Optional OCR: `tesseract-ocr` + `pip install -e ".[ocr]"`

## Install (laptop / mock)

```bash
git clone https://github.com/blofelds/ac-telemetry.git
cd ac-telemetry
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Install (Raspberry Pi 2B + real capture)

```bash
sudo apt update
sudo apt install -y python3-opencv python3-venv v4l-utils
# Optional later: tesseract-ocr

cd ~/git/ac-telemetry   # or your clone path
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .
```

**Do not** `pip install -e ".[capture]"` on the 2B — OpenCV/numpy wheels frequently die with **SIGILL**. Use distro OpenCV via `--system-site-packages` instead.

Prefer MJPEG (`prefer_mjpeg: true` in `config/default.yaml`) so USB2 is not flooded with raw YUYV.

## Run with mock capture

```bash
ac-telemetry --backend mock
# or: AC_TELEMETRY_BACKEND=mock ac-telemetry --host 127.0.0.1
```

1. Open `http://127.0.0.1:8741/` — lap strip + session form + capture status.
2. **Start session** (track / car / notes).
3. With `detect.lap_time.reader: mock`, a synthetic lap appears every ~45s.
4. Check `data/sessions/laps.csv` and `GET /api/laps`.
5. **End session** when done.

For faster mock laps while testing, set `detect.lap_time.mock_interval_seconds: 5` in YAML.

## Run with V4L2 on the Pi

```bash
v4l2-ctl --list-devices
# backend defaults to v4l2 in config/default.yaml
ac-telemetry
```

1. Open `http://<pi-ip>:8741/debug` and confirm the green box covers the **last-lap** digits (see [`ROI.md`](ROI.md)). Use **Download full-res ROI screenshot** to save a capture-resolution JPEG for measuring pixels (the page preview is scaled).
2. Adjust `rois.lap_time` in `config/default.yaml` if the scaled ROI is wrong, then restart.
3. Keep `reader: mock` until capture is stable; then try `tesseract`. If OCR fails on AC’s block font, switch to `template` — but **bundled `ac_*` PNGs may be ACC (wrong game)**. Prefer live Pi set `templates/lap_time_digits/ac_720p_pi` (complete 0–9 + `:` / `.`; digit span + separator recovery ship); VLC `ac_720p_capture` can mis-rank lookalikes on soft MJPEG (see [`ROI.md`](ROI.md)).
4. Start a session from the phone UI before you drive.

### systemd

See [`../deploy/ac-telemetry.service`](../deploy/ac-telemetry.service). Pi user needs the `video` group.

## Lap times

| Piece | Detail |
| --- | --- |
| ROI | `rois.lap_time` — completed last-lap HUD (see [`ROI.md`](ROI.md)) |
| Detect FPS | `detect.fps` (default 2) — separate from capture FPS |
| Readers | `mock` · `tesseract` (default) · `template` / `assetto_corsa` (OpenCV backup) |
| Modes | `last_lap` (record when last-lap text changes) or `current_timer` (record on reset) |
| CSV | `data/sessions/laps.csv` |
| Live | UI lap strip + `GET /api/laps/current` |
| Calibrate | `/debug` (download full-res + **Save glyph**) · `/api/debug/rois.jpg` · `POST /api/debug/glyphs/save` · `/api/debug/frame.jpg` |
| Detect dump | `/api/debug/detect/last.json` + `last_roi.png` + `last_mask.png` — exact failed crop (see [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)) |

**Reader choice:** prove the path with `mock`, calibrate ROI, try `tesseract`.
Use `template` only as a backup when OCR misreads the AC block font. Bundled
templates under `templates/lap_time_digits/ac_*` may be ACC — capture real AC
glyphs with **/debug → Save glyph** (see [`ROI.md`](ROI.md)). PNGs do not help
Tesseract.

Laps are written only while a session is open. If the UI shows `—`, check
`last_error` on `/debug` (OCR/template miss, wrong ROI, no session, or reader error).
If the error is `no glyphs matched in ROI`, pull the **detect dump** checklist in
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) before changing matcher settings.

## Sessions API

```bash
curl -s -X POST http://127.0.0.1:8741/api/sessions \
  -H 'Content-Type: application/json' \
  -d '{"track":"Monza","car":"Ferrari 488 GT3","notes":""}'

curl -s http://127.0.0.1:8741/api/laps/current
curl -s http://127.0.0.1:8741/api/laps
curl -s -X POST http://127.0.0.1:8741/api/sessions/current/end
```

## Metrics

Scrape `GET /metrics`. Lap-related names:

- `ac_telemetry_detect_latency_seconds`
- `ac_telemetry_detect_failures_total`
- `ac_telemetry_detect_drops_total`
- `ac_telemetry_laps_recorded_total`
- `ac_telemetry_signal_lap_time_ms`

## Next reading

- [FEATURES.md](FEATURES.md) — delivered vs planned
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — Pi install, black frames, OCR misses
- [ARCHITECTURE.md](ARCHITECTURE.md) — detect thread + CSV shape
