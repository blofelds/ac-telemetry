# Architecture (Slice 1)

## System overview

One Python process owns capture, CSV session store, HTTP API, Prometheus metrics, and a phone-friendly UI.

```
                 ┌─────────────────────────────────────┐
  HDMI/UVC ───►  │  CaptureService (thread)            │
  or mock        │    mock | v4l2 FrameSource          │
                 └──────────────┬──────────────────────┘
                                │ stats (optional snapshot on end)
                 ┌──────────────▼──────────────────────┐
                 │  SessionStore (CSV append)          │
                 │  Prometheus gauges/counters         │
                 │  FastAPI: / /health /metrics /api/* │
                 │  Phone UI → POST /api/sessions      │
                 └─────────────────────────────────────┘
```

No separate worker queue. Pi 2B cannot afford accidental multi-process weight this early.

## Modules

| Package | Role |
| --- | --- |
| `ac_telemetry.settings` | YAML + env; `CaptureProfile` with hard caps |
| `ac_telemetry.capture` | Background loop; mock / V4L2 sources |
| `ac_telemetry.store` | `sessions.csv` with track/car/notes; API-owned lifecycle |
| `ac_telemetry.metrics` | Dedicated Prometheus registry (capture + sessions) |
| `ac_telemetry.api` | FastAPI routes |
| `ac_telemetry.web` | Inline phone UI HTML |
| `ac_telemetry.main` | Wiring, signals, uvicorn |

## Session model (Slice 1)

- Sessions are started/ended via HTTP (or the UI that calls it), **not** via capture hooks.
- Columns include metadata (`track`, `car`, `notes`) plus optional capture snapshot fields.
- At most one `running` session in process memory; CSV remains the durable history.
- On process restart, an unfinished CSV `running` row can still be ended by id (recovered from disk).

## Capture profiles

Profiles are **named** (`pi2b`, `pi5`) so board limits are not sprinkled through detection code later.

- Requested width/height/fps are **clamped** to `max_*` on load.
- `pi2b` defaults target sustainable decode headroom for later OCR, not max device capability.
- `pi5` is a placeholder with higher ceilings; untuned until hardware exists.

## Backends

- **Mock** — `read()` always succeeds; the loop paces to target FPS.
- **V4L2** — OpenCV with `CAP_V4L2` when available; frames discarded after read.

## Persistence choice (CSV first)

- Zero daemon dependencies beyond the filesystem
- Easy to inspect on the Pi and copy into Obsidian later
- Column set designed to survive a future SQLite migration (Slice 5)

We intentionally do **not** introduce SQLite in Slice 1.

## Metrics design

- Capture health: up, running, FPS, last frame age, error/frame counters
- Sessions: started/ended counters + open gauge

Later slices should add signal gauges keyed by name (`signal_*`) rather than one-off metric names that cannot grow.

## Networking

- Default bind `0.0.0.0` for LAN phone access
- No TLS, no auth — trusted home LAN assumption
- Tailscale deferred

## Design principles

1. Prove capture before OCR (Slice 0); attach human session metadata before laps (Slice 1).
2. Prefer simple code over frameworks-on-frameworks.
3. Pi 2B resource limits win every tradeoff.
4. Leave config/API shapes that do not force a rewrite on Pi 5.

## Future extension points (not built)

- Lap/sector ROI readers appending lap CSV rows under a session id (Slice 2)
- Grafana starter dashboards (Slice 3)
- Driving-signal sample streams (Slice 4)
- SQLite WAL store (Slice 5)
