# Troubleshooting (Slice 1)

## `pip install` stuck on “Building wheel for uvloop”

- **Cause:** Older installs used `uvicorn[standard]`, which depends on uvloop. On ARM (Pi 2B) uvloop often builds from source and can hang for a very long time.
- **Fix:** Ctrl+C the hung build. Pull a revision that depends on plain `uvicorn` (no `[standard]` in default deps), then `pip install -e .`.
- Do **not** run `pip install -e ".[standard]"` on the 2B.
- OpenCV / `.[capture]` is unrelated and also heavy on a 2B — install it only when you need V4L2.

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
- OpenCV **module** missing (`No module named 'cv2'`): `pip install -e ".[capture]"`.
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

## Still stuck

- Collect: `GET /health` JSON, last 50 log lines, `v4l2-ctl --list-devices` output (if hardware), and whether mock works on the same host.
