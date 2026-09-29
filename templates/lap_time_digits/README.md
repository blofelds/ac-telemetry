# Lap-time digit templates

**Bundled `ac_1080p` / `ac_720p` are ACC (Competizione), not Assetto Corsa.**
They were copied from [blofelds/acc-telemetry](https://github.com/blofelds/acc-telemetry)
`templates/speed_digits/ac_1080p/`. Despite the `ac_` names, live Pi testing
against Assetto Corsa (original) confirmed the wrong game. There is **no
separate true-AC digit set** in acc-telemetry today — only this mislabeled
bundle (plus gear glyphs under `templates/gear_digits/ac_1080p/`). Expect
`no lap-time pattern in template symbols` until you replace them with real AC
crops.

| Directory | Purpose |
| --- | --- |
| `ac_1080p/` | Upstream 24×28 PNGs (mislabeled; ACC face) |
| `ac_720p/` | Same set scaled ×2/3 for pi2b 720p (still ACC) |
| `ac_720p_capture/` | **Empty by default** — write real AC PNGs here via `/debug` → **Save glyph** |

`colon.png` / `period.png` in the bundled dirs are synthetic separators (not in
the upstream speed set).

### Capture real AC glyphs on the Pi

1. Calibrate `rois.lap_time` so `/debug` shows only the last-lap digits.
2. Open `http://<pi-ip>:8741/debug` while AC shows a known time (e.g. `0:00.000`, `1:23.456`).
3. Optionally drag a single digit on the ROI crop preview.
4. Pick symbol `0`–`9`, `:`, or `.` and tap **Save glyph** (or leave empty for `pending/<timestamp>.png`).
5. Files land under `glyphs_dir` (default `templates/lap_time_digits/ac_720p_capture/`).
6. Point `detect.lap_time.templates_dir` at that folder and set `reader: template`.

API: `POST /api/debug/glyphs/save` with JSON `{ "symbol": "5" }` and optional
`x,y,width,height` subcrop in ROI-local pixels.

**Default reader stays `tesseract` (or `mock`).** Point
`detect.lap_time.reader` at `template` only after AC glyphs are in place —
PNG templates do not help Tesseract.
