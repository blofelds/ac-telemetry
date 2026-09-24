# Architecture (Slice 0)

## System overview

One Python process owns capture, a tiny CSV session stub, HTTP API, Prometheus metrics, and a status page.

```
                 ┌─────────────────────────────────────┐
  HDMI/UVC ───►  │  CaptureService (thread)            │
  or mock        │    mock | v4l2 FrameSource          │
                 └──────────────┬──────────────────────┘
                                │ stats + session hooks
                 ┌──────────────▼──────────────────────┐
                 │  SessionStore (CSV append)          │
                 │  Prometheus gauges/counters         │
                 │  FastAPI: / /health /metrics /api/* │
                 └─────────────────────────────────────┘
```

No separate worker queue. Pi 2B cannot afford accidental multi-process weight this early.

## Modules

| Package | Role |
| --- | --- |
| `ac_telemetry.settings` | YAML + env; `CaptureProfile` with hard caps |
| `ac_telemetry.capture` | Background loop; mock / V4L2 sources |
| `ac_telemetry.store` | `sessions.csv` start/stop stub |
| `ac_telemetry.metrics` | Dedicated Prometheus registry |
| `ac_telemetry.api` | FastAPI routes |
| `ac_telemetry.web` | Inline status HTML |
| `ac_telemetry.main` | Wiring, signals, uvicorn |

## Capture profiles

Profiles are **named** (`pi2b`, `pi5`) so board limits are not sprinkled through detection code later.

- Requested width/height/fps are **clamped** to `max_*` on load.
- `pi2b` defaults target sustainable decode headroom for later OCR, not max device capability.
- `pi5` is a placeholder with higher ceilings; untuned until hardware exists.

## Backends

- **Mock** — `read()` always succeeds; the loop paces to target FPS. Lets CI/dev proceed without a dongle.
- **V4L2** — OpenCV with `CAP_V4L2` when available; sets FRAME_WIDTH/HEIGHT/FPS; does not yet re-encode or save frames.

Frames are **discarded** after read in Slice 0. Continuous video to disk is a non-goal.

## Persistence choice (CSV first)

CSV session stubs:

- Zero daemon dependencies beyond the filesystem
- Easy to inspect on the Pi and copy into Obsidian later
- Column set designed to survive a future SQLite migration (Slice 5)

We intentionally do **not** introduce SQLite in Slice 0.

## Metrics design

Generic health metrics only:

- Process up, capture running, measured FPS, last frame age, error/frame counters

Later slices should add signal gauges keyed by name (`signal_*`) rather than one-off metric names that cannot grow.

## Networking

- Default bind `0.0.0.0` for LAN phone access
- No TLS, no auth — trusted home LAN assumption
- Tailscale deferred

## Design principles (Slice 0)

1. Prove capture before OCR.
2. Prefer simple code over frameworks-on-frameworks.
3. Pi 2B resource limits win every tradeoff.
4. Leave config/API shapes that do not force a rewrite on Pi 5.

## Future extension points (not built)

- Pluggable ROI readers per signal
- Session metadata API (Slice 1)
- Detect pipeline thread with frame handoff (must never block capture under pressure)
