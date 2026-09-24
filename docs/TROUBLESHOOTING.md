# Troubleshooting (Slice 0)

## Service will not start

- Confirm the venv is activated and `pip install -e .` succeeded.
- Check Python version: `python3 --version` (need 3.11+).
- Port in use: change `--port` / `AC_TELEMETRY_PORT` (default `8741`).

## Status UI shows stopped / no frames

- If you passed `--no-capture`, start without that flag.
- Check logs for capture start errors.
- Mock backend should always produce frames; if it does not, file a bug.

## V4L2: failed to open device

- Is the dongle plugged in? `ls -l /dev/video*`
- Permissions: user must be in the `video` group (`groups`; re-login after `usermod -aG video $USER`).
- Wrong index: try `/dev/video0`, `/dev/video1`, or `v4l2-ctl --list-devices`.
- OpenCV missing: `pip install -e ".[capture]"`.

## Black frames / zero FPS on real HDMI

Common console capture issues (validate before OCR work):

- **HDCP** — some splitters/dongles black-screen PS5; try another splitter or return the pair.
- **No live display path** — PS5 often blanks if nothing is “watching” the primary HDMI; use a 1×2 splitter to the TV.
- **Resolution too high for Pi 2B** — stick to `pi2b` profile; do not jump to 1080p on 2B.

## Metrics scrape empty / wrong

- Hit `GET /metrics` directly; content type should be Prometheus text.
- `ac_telemetry_up` should be `1` whenever the process is alive.
- `last_frame_age_seconds` may be `NaN` until the first frame.

## CSV missing or only “running” rows

- Default path: `data/sessions/sessions.csv` under the working directory.
- Stop the process cleanly (SIGINT/SIGTERM) so the stop hook runs.
- Ensure the process can create `data/sessions/` (permissions).

## Phone cannot open the UI

- Bind is `0.0.0.0` by default — confirm you are not forcing `127.0.0.1` on the Pi.
- Same LAN / subnet; no guest-WiFi client isolation.
- Firewall: allow TCP `8741` if enabled (`ufw` etc.).
- Auth is not implemented — trusted home LAN only.

## Historical fixes

None yet. When bugs are fixed, keep a short writeup and link it here (acc-telemetry style).
