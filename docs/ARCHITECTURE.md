# Architecture

## System overview

One Python process owns capture, detection, CSV stores, HTTP API, Prometheus metrics, and a phone-friendly UI.

```
                 ┌─────────────────────────────────────┐
  HDMI/UVC ───►  │  CaptureService (thread)            │
  or mock        │    latest-frame slot (replace)      │
                 └──────────────┬──────────────────────┘
                                │ get_latest_frame()
                 ┌──────────────▼──────────────────────┐
                 │  DetectService (thread, low FPS)    │
                 │    crop rois.lap_time → reader      │
                 │    debounce → LapStore CSV          │
                 └──────────────┬──────────────────────┘
                                │
                 ┌──────────────▼──────────────────────┐
                 │  SessionStore + LapStore (CSV)      │
                 │  Prometheus gauges/counters         │
                 │  FastAPI + phone UI                 │
                 └─────────────────────────────────────┘
```

No separate worker process. Pi 2B cannot afford accidental multi-process weight this early.

## Modules

| Package | Role |
| --- | --- |
| `ac_telemetry.settings` | YAML + env; profiles, `rois`, `detect` |
| `ac_telemetry.capture` | Background loop; mock / V4L2; latest-frame handoff |
| `ac_telemetry.detect` | Low-FPS lap_time crop + pluggable readers |
| `ac_telemetry.store` | `sessions.csv` + `laps.csv` |
| `ac_telemetry.metrics` | Dedicated Prometheus registry |
| `ac_telemetry.api` | FastAPI routes |
| `ac_telemetry.web` | Inline phone UI HTML |
| `ac_telemetry.main` | Wiring, signals, uvicorn |

## Capture profiles

Profiles are **named** (`pi2b`, `pi5`) so board limits are not sprinkled through detection code.

- Requested width/height/fps are **clamped** to `max_*` on load.
- `prefer_mjpeg` asks UVC devices for MJPEG FourCC (USB2-friendly).

## Detection design (Pi 2B)

1. Capture publishes the newest frame under a lock (replace, never queue).
2. Detect wakes at `detect.fps` (default 2). If a prior tick is still busy and `drop_under_pressure` is on, the tick is dropped and counted.
3. Crop only `rois.lap_time` (copy the tiny rectangle, not the full frame twice beyond that).
4. Reader is pluggable (`mock` | `tesseract` | `template`). Missing ROI keys fail soft for pixel readers; mock ignores pixels.
5. Debounce requires N identical reads before recording.
6. Persist only when a session is open.

### Readers

| Reader | Needs frame | Notes |
| --- | --- | --- |
| `mock` | No | Synthetic last-lap times for store/API proof |
| `tesseract` | Yes | Optional `[ocr]` extra + system tesseract; heavy on 2B; may fail on AC block font |
| `template` (alias `assetto_corsa`) | Yes | OpenCV `matchTemplate` backup using `templates/lap_time_digits/`; no OCR deps beyond OpenCV |

### Modes

| Mode | When a lap row is written |
| --- | --- |
| `last_lap` | Debounced last-lap text changes to a new non-zero time |
| `current_timer` | Timer resets downward past `reset_slack_ms` after `min_lap_ms` |

## Persistence (CSV first)

- `sessions.csv` — session metadata + optional capture snapshot
- `laps.csv` — `session_id`, `lap_number`, `lap_time`, `lap_time_ms`, …
- Column sets designed to survive a future SQLite migration

## Metrics

- Capture health: up, running, FPS, last frame age, error/frame counters
- Sessions: started/ended/open
- Detect: latency gauge, failure/drop/lap counters, `signal_lap_time_ms`

## Networking

- Default bind `0.0.0.0` for LAN phone access
- No TLS, no auth — trusted home LAN assumption
- Tailscale deferred

## Design principles

1. Prove capture before OCR; attach human session metadata before laps.
2. Prefer simple code over frameworks-on-frameworks.
3. Pi 2B resource limits win every tradeoff.
4. Missing ROI / optional deps fail soft into metrics, not process death.
5. Keep API shapes stable so UI and Prometheus consumers barely change later.
