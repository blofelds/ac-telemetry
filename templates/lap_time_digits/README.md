# Lap-time digit templates

**Bundled `ac_1080p` / `ac_720p` are ACC (Competizione), not Assetto Corsa.**
They were copied from [blofelds/acc-telemetry](https://github.com/blofelds/acc-telemetry)
`templates/speed_digits/ac_1080p/`. Despite the `ac_` names, live Pi testing
against Assetto Corsa (original) confirmed the wrong game. Expect
`no lap-time pattern in template symbols` if you point the template reader at
those dirs.

| Directory | Purpose |
| --- | --- |
| `ac_1080p/` | Upstream 24×28 PNGs (mislabeled; ACC face) |
| `ac_720p/` | Same set scaled ×2/3 for pi2b 720p (still ACC) |
| `ac_720p_capture/` | **Real AC** glyphs from PS5 HUD LAST/BEST — **partial** (has 0–6, 8, `:`, `.`; missing **7** and **9**) |

`colon.png` / `period.png` in the bundled ACC dirs are synthetic separators (not in
the upstream speed set). Separators under `ac_720p_capture/` are real HUD crops.

### Using the real-AC set

```yaml
detect.lap_time.reader: template
detect.lap_time.templates_dir: templates/lap_time_digits/ac_720p_capture
```

Add `7.png` / `9.png` (via `/debug` → **Save glyph** or another crop) before
expecting full coverage of all lap times.

### Capture more glyphs on the Pi

1. Calibrate `rois.lap_time` so `/debug` shows only the last-lap digits.
2. Open `http://<pi-ip>:8741/debug` while AC shows a known time that includes missing symbols.
3. Optionally drag a single digit on the ROI crop preview.
4. Pick symbol `7` or `9` (etc.) and tap **Save glyph**.
5. Files land under `glyphs_dir` (default `templates/lap_time_digits/ac_720p_capture/`).

API: `POST /api/debug/glyphs/save` with JSON `{ "symbol": "5" }` and optional
`x,y,width,height` subcrop in ROI-local pixels.

**Default reader stays `tesseract` (or `mock`).** Point
`detect.lap_time.reader` at `template` only when you intend to use PNG matching —
templates do not help Tesseract.
