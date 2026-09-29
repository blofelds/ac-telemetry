# ROI and HUD signals

How `rois.lap_time` maps to Assetto Corsa’s on-screen HUD, and which other HUD
regions exist in the sister project for later signals.

## `rois.lap_time` (live service)

| Field | Meaning |
| --- | --- |
| Config key | `rois.lap_time` in [`config/default.yaml`](../config/default.yaml) |
| Detect mode | `detect.lap_time.mode: last_lap` (default) |
| HUD meaning | **Completed** lap time (“last lap”), not the running current-lap timer |
| Source mapping | Scaled from [acc-telemetry](https://github.com/blofelds/acc-telemetry) profile `assetto_corsa_1080p` → `last_lap_time` |
| Scale used | 1080p → pi2b 720p (×2/3) |

With `mode: last_lap`, a new CSV row is written when the debounced reader text
changes to a new non-zero time. That matches AC’s left-side **last lap**
readout after you cross the line.

Coordinates are resolution- and crop-dependent. HDMI capture often differs
from a recorded 1080p YouTube/file crop — verify with the debug helper before
trusting any reader.

### Which lap-time reader?

| Reader | When to use |
| --- | --- |
| `mock` | Laptop / plumbing tests; no pixels needed |
| `tesseract` | Default OCR path once `rois.lap_time` is calibrated |
| `template` (alias `assetto_corsa`) | **Backup** when Tesseract misreads AC’s block font. Uses OpenCV `matchTemplate` on digit PNGs under `templates/lap_time_digits/` (from acc-telemetry AC 1080p speed digits; `ac_720p` is scaled ×2/3 for pi2b). PNG templates do **not** help Tesseract. |

Keep `reader: tesseract` (or `mock`) until OCR is ruled out. Switch only the
YAML `detect.lap_time.reader` value — mock and tesseract stay available.

### Calibrate on the Pi

1. Run with real capture (`backend: v4l2`, default).
2. Open `http://<pi-ip>:8741/debug`.
3. Confirm the green box covers the last-lap digits.
4. **Download full-res ROI screenshot** (button on `/debug`, or
   `GET /api/debug/rois.jpg`) — attachment JPEG at **capture resolution** with
   every configured ROI drawn. Open it locally to measure pixel coords; the
   on-page preview is CSS-scaled and is not for measuring.
5. Adjust `rois.lap_time` `{x,y,width,height}` and restart (or reload config by restarting the service).
6. Optional inline JPEGs: `/api/debug/frame.jpg`, `/api/debug/roi/lap_time.jpg`,
   `/api/debug/overlay/lap_time.jpg`.

JPEG comes from the in-memory latest-frame handoff (`cv2.imencode`). No ffmpeg;
encode runs outside the capture lock.

### Why the UI may show empty (`—`)

| Cause | What to check |
| --- | --- |
| OCR / template miss | Crop looks right but digits unreadable → tune ROI / lighting; watch `lap.last_error`; try `reader: template` if Tesseract fails on AC block font |
| Wrong ROI | Debug overlay misses the HUD → edit `rois.lap_time` |
| No session | Displayed time may update, but laps are **not** persisted without an open session |
| Reader error | Missing tesseract/OpenCV/templates → `last_error` on `/debug` and `/api/laps/current` |

## Known HUD keys (`assetto_corsa_1080p`)

From acc-telemetry’s `assetto_corsa_1080p` profile — candidates for future
`rois.*` keys on Pi 5 / richer detect. **Only `lap_time` is wired today.**

| acc-telemetry key | Role | ac-telemetry today |
| --- | --- | --- |
| `last_lap_time` | Completed lap time (left timing panel) | Mapped → `rois.lap_time` |
| `lap_number` | Lap count in timing panel | Not yet |
| `throttle` | Vertical green pedal bar | Deferred (Pi 5) |
| `brake` | Vertical red pedal bar | Deferred (Pi 5) |
| `speed` | km/h digits by pedals | Deferred (Pi 5) |
| `gear` | Large gear digit (N→0) | Deferred (Pi 5) |

Not present on that AC original profile (unlike ACC Competizione): steering
indicator, circular minimap / track map.
