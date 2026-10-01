# AC Telemetry — Documentation Index

Documentation follows the same **layout philosophy** as [blofelds/acc-telemetry](https://github.com/blofelds/acc-telemetry): explain why, preserve the journey, progressive disclosure.

## Start Here

1. **[../README.md](../README.md)** — Product overview, Pi 2B install, lap times + metrics
2. **[USER_GUIDE.md](USER_GUIDE.md)** — Running the service, sessions, lap CSV
3. **[FEATURES.md](FEATURES.md)** — What exists vs what is planned

## Core documentation

### For users

- **[USER_GUIDE.md](USER_GUIDE.md)** — Install (incl. Pi 2B apt OpenCV), mock/V4L2, laps
- **[FEATURES.md](FEATURES.md)** — Delivered capabilities and roadmap boundaries
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — uvloop, SIGILL, ROI/OCR, black frames
- **[ROI.md](ROI.md)** — `rois.lap_time` / last-lap mapping + future HUD keys

### For developers

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Capture + detect threads, CSV model
- **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** — Orientation for new contributors

## Specialized topics

- **[ROI.md](ROI.md)** — Last-lap ROI, `/debug` calibration, acc-telemetry HUD keys

Candidates as work lands:

- Capture device notes / known-good SKUs (after hardware validation)
- Per-track ROI packs
- Prometheus / Grafana consumers
- CSV → SQLite migration notes

## Quick reference (“I want to…”)

| Goal | Where |
| --- | --- |
| Run without hardware | [USER_GUIDE.md](USER_GUIDE.md) · mock backend |
| Pi 2B OpenCV without SIGILL | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) · apt + system-site-packages |
| Start a session + see laps | `http://<host>:8741/` · [USER_GUIDE.md](USER_GUIDE.md) |
| List laps via API | `GET /api/laps` · [FEATURES.md](FEATURES.md) |
| Scrape Prometheus | `GET /metrics` · [FEATURES.md](FEATURES.md) |
| Calibrate lap ROI | `http://<host>:8741/debug` · [ROI.md](ROI.md) |
| Pull last detect dump (failure ROI/mask/scores) | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) · `/api/debug/detect/last.*` |
| Understand detect thread | [ARCHITECTURE.md](ARCHITECTURE.md) |

## Changelog (docs)

| Date | Change |
| --- | --- |
| 2026-10-01 | Detect dump endpoints: last.json / last_roi.png / last_mask.png checklist |
| 2026-09-28 | ROI debug helper; `rois.lap_time` / last-lap docs; v4l2 default backend |
| 2026-09-27 | Lap times: ROI, readers, CSV, metrics; Pi 2B apt OpenCV notes |
| 2026-09-26 | Pi 2B install: plain uvicorn / no uvloop hang note |
| 2026-09-24 | Foundation stubs: index + core user/dev docs |
