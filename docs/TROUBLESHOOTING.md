# Troubleshooting

## `pip install` stuck on “Building wheel for uvloop”

- **Cause:** Older installs used `uvicorn[standard]`, which depends on uvloop. On ARM (Pi 2B) uvloop often builds from source and can hang for a very long time.
- **Fix:** Ctrl+C the hung build. Pull a revision that depends on plain `uvicorn` (no `[standard]` in default deps), then `pip install -e .`.
- Do **not** run `pip install -e ".[standard]"` on the 2B.

## Pi 2B: `.[capture]` / pip OpenCV dies with SIGILL

- **Cause:** Many `opencv-python-headless` / numpy wheels use CPU instructions the Pi 2B (ARMv7) does not have.
- **Fix:** Do **not** pip-install `.[capture]` on the 2B. Instead:
  ```bash
  sudo apt install python3-opencv
  python3 -m venv --system-site-packages .venv
  source .venv/bin/activate
  pip install -e .
  python -c "import cv2; print(cv2.__version__)"
  ```
- Prefer `prefer_mjpeg: true` (default) so the UVC device uses MJPEG over raw YUYV.

## Service will not start

- Confirm the venv is activated and `pip install -e .` succeeded.
- Check Python version: `python3 --version` (need 3.11+).
- Port in use: change `--port` / `AC_TELEMETRY_PORT` (default `8741`).

## Status UI shows stopped / no frames

- If you passed `--no-capture`, start without that flag.
- Check logs for capture start errors.
- Mock backend should always produce frames; if it does not, file a bug.

## Cannot start a session (409)

- Only one session may be open. End the current one from the UI or:
  `curl -X POST http://127.0.0.1:8741/api/sessions/current/end`
- After a crash, check `GET /api/sessions` for a leftover `running` row and end by id.

## V4L2: `ImportError` / missing `libopenblas.so.0`

pip's numpy and opencv-python-headless wheels on Raspberry Pi OS need **system OpenBLAS**. Without it, `import cv2` (or `import numpy`) fails with something like `libopenblas.so.0: cannot open shared object file`, while HTTP still starts (capture fails soft).

- Install OpenBLAS: `sudo apt install libopenblas0`
- Alternatives if that package name differs: `libopenblas0-pthread`, or `libopenblas-dev`
- Confirm: `python -c 'import numpy; import cv2'`
- **Do not** treat this as a missing pip package — reinstalling `.[capture]` will not fix a missing `.so`
- `apt install python3-opencv` is **optional** if pip opencv is already installed; prefer fixing OpenBLAS for the venv wheels

## V4L2: failed to open device

- Is the dongle plugged in? `ls -l /dev/video*`
- Permissions: user must be in the `video` group (`groups`; re-login after `usermod -aG video $USER`).
- Wrong index: try `/dev/video0`, `/dev/video1`, or `v4l2-ctl --list-devices`.
- OpenCV **module** missing on Pi 2B: install `python3-opencv` and recreate the venv with `--system-site-packages` (see SIGILL section). On x86 you may use `pip install -e ".[capture]"`.
- OpenCV installed but import still fails: see **missing libopenblas.so.0** above.

## Black frames / zero FPS on real HDMI

Common console capture issues (validate before OCR work):

- **HDCP** — some splitters/dongles black-screen PS5; try another splitter or return the pair.
- **No live display path** — PS5 often blanks if nothing is “watching” the primary HDMI; use a 1×2 splitter to the TV.
- **Resolution too high for Pi 2B** — stick to `pi2b` profile; do not jump to 1080p on 2B.

## Metrics scrape empty / wrong

- Hit `GET /metrics` directly; content type should be Prometheus text.
- `ac_telemetry_up` should be `1` whenever the process is alive.
- `ac_telemetry_sessions_started_total` increments on each successful `POST /api/sessions`.
- `last_frame_age_seconds` may be `NaN` until the first frame.

## CSV missing or only “running” rows

- Default path: `data/sessions/sessions.csv` under the working directory.
- Sessions are created by the API/UI, not by capture start. Start a session from the phone page.
- End the session from the UI (or API) so a `stopped` row is appended.
- Ensure the process can create `data/sessions/` (permissions).

## Phone cannot reach the Pi

- Confirm bind is `0.0.0.0` (default), not `127.0.0.1`.
- Same Wi-Fi / LAN as the Pi; try `http://<pi-ip>:8741/`.
- Firewall on the Pi may block the port.

## No lap rows / lap UI stuck at —

Empty displayed/recorded time usually means one of:

| Cause | Check |
| --- | --- |
| OCR / template miss | Digits present but unreadable → tune ROI; try `reader: template` if Tesseract fails on AC block font. If `last_error` is `no lap-time pattern in template symbols`, bundled `ac_*` PNGs are **ACC (wrong game; confirmed on Pi)** — capture real AC glyphs with **/debug → Save glyph** (see [`ROI.md`](ROI.md)). |
| Wrong ROI | Scaled coords miss your capture crop |
| No session | Open a session before expecting CSV rows |
| Reader error | Missing tesseract/OpenCV/templates |

- Open **`http://<pi-ip>:8741/debug`** — overlay + ROI crop + `last_error`.
- **Download full-res ROI screenshot** (or `/api/debug/rois.jpg`) for a capture-resolution JPEG with all ROI boxes — use that file to measure pixels; the on-page preview is scaled.
- **Save glyph** on `/debug` (or `POST /api/debug/glyphs/save`) writes PNG crops into `glyphs_dir` for real AC digit templates.
- Inline JPEGs: `/api/debug/frame.jpg`, `/api/debug/roi/lap_time.jpg`.
- Is a **session** open? Laps are not written without one (displayed OCR can still update).
- Mock reader: wait for `mock_interval_seconds` (45s) or lower it for tests (`--backend mock` if not using V4L2).
- For tesseract: confirm the green box covers the **last-lap** digits; see [`ROI.md`](ROI.md).
- For template backup: set `detect.lap_time.reader: template` and point `templates_dir` at **capture-built** (real AC) PNGs via Save glyph (needs apt OpenCV). Bundled `ac_720p` / `ac_1080p` are ACC (mislabeled) — expect `no lap-time pattern in template symbols` on AC until replaced; see [`templates/lap_time_digits/README.md`](../templates/lap_time_digits/README.md).
- Also: `lap.last_error` on `/api/laps/current` or `/api/debug/info`.
- Watch `ac_telemetry_detect_failures_total` and `ac_telemetry_detect_drops_total` on `/metrics`.
- If drops climb, lower `detect.fps` or keep using `mock` until the Pi has headroom.

### Collect a detect dump (preferred for `no glyphs matched in ROI`)

When `lap.last_error` stays `no glyphs matched in ROI` (or template parse fails),
do **not** guess from `/api/debug/roi/*.jpg` — that JPEG is a fresh re-encode of a
new crop. Pull the **last detect dump** (exact BGR crop + white_mask + per-glyph
scores) instead:

```bash
PI="${PI:-http://127.0.0.1:8741}"
BUNDLE="$HOME/ac-detect-dump-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BUNDLE" && cd "$BUNDLE"

# LAST lap digits must be visible on the PS5 HUD while this runs
sleep 2
curl -sS "$PI/api/debug/detect/last.json" -o last.json
curl -sS "$PI/api/debug/detect/last_roi.png" -o last_roi.png
curl -sS "$PI/api/debug/detect/last_mask.png" -o last_mask.png
curl -sS "$PI/api/debug/detect/last_annotated.png" -o last_annotated.png
curl -sS "$PI/api/status" -o status.json

zip -r "../$(basename "$BUNDLE").zip" .
echo "Bundle: $BUNDLE.zip"
```

- Dump is **failure-only** by default (`detect.debug_dump.enabled: true`,
  `on_success: false`). Force on with `AC_TELEMETRY_DETECT_DEBUG_DUMP=1`.
- Attach the zip in chat, or drop it where the Latitude worker can read it.
- Decision tree (mask empty vs low scores vs separators): see the lap-detect
  debug plan in project Context / ask the coordinating agent.

### Duplicate / skipped laps (same LAST re-read as new)

Symptom examples: ~12 laps logged for 7 driven; one lap skipped; the same LAST
string (e.g. `2:21.900` / `2:21.500`) repeating while you are still on one lap.

1. **Start in-app card-native video** before the suspect stint (does not steal video0):
   ```bash
   PI="${PI:-http://127.0.0.1:8741}"
   curl -sS -X POST "$PI/api/debug/record/start" \
     -H 'Content-Type: application/json' \
     -d '{"duration_seconds":90,"output_dir":"'"$HOME"'/ac-telemetry-testdata/card"}'
   ```
2. When the glitch happens, **curl detect dumps + status** (same commands as above).
3. `POST $PI/api/debug/record/stop` (or wait for auto-stop). Confirm with
   `GET $PI/api/debug/record/status` — file should be 1280×720.
4. Do **not** open `/dev/video0` with ffmpeg while runtime is capturing. If you
   must use ffmpeg, stop the service first and run `scripts/record-card-native.sh`.

PS5 share → downscale clips are **not** ROI-accurate for this class of bug.

- Collect: `GET /health` JSON, `GET /api/laps/current`, last 50 log lines, `v4l2-ctl --list-devices` output (if hardware), and whether mock works on the same host.
