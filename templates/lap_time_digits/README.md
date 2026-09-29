# Lap-time digit templates

**Bundled `ac_1080p` / `ac_720p` may be ACC (Competizione), not Assetto Corsa.**
They were copied from acc-telemetry `speed_digits/ac_1080p` and do not match the
PS5 AC last-lap HUD font. Expect `no lap-time pattern in template symbols`
until you replace them with real AC crops.

| Directory | Purpose |
| --- | --- |
| `ac_1080p/` | Legacy bundled glyphs (likely ACC — do not trust for AC) |
| `ac_720p/` | Same set scaled ×2/3 for pi2b 720p |
| `ac_720p_capture/` | **Empty by default** — write real AC PNGs here via `/debug` → **Save glyph** |

`colon.png` / `period.png` in the bundled dirs are synthetic separators.

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
`detect.lap_time.reader` at `template` only as a backup when OCR fails on this
block font — PNG templates do not help Tesseract.
