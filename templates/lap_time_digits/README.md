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
| `ac_720p_capture/` | Real AC glyphs from VLC/PS5 HUD — **complete** (0–9 + `:` / `.`) but sharper than live Pi MJPEG |
| `ac_720p_pi/` | **Live Pi HDMI** crops from detect dump `1:35.113` — **incomplete** (`1`,`3`,`5` only); preferred default for Pi |

`colon.png` / `period.png` in the bundled ACC dirs are synthetic separators (not in
the upstream speed set). Separators under `ac_720p_capture/` are real HUD crops.
`ac_720p_pi/` intentionally omits separators and missing digits until more live
Pi Save-glyph crops land (do not hybridize with VLC without documenting the risk).

### Using the live Pi set (default)

```yaml
detect.lap_time.reader: template
detect.lap_time.templates_dir: templates/lap_time_digits/ac_720p_pi
glyphs_dir: templates/lap_time_digits/ac_720p_pi
```

Live-sourced today: **`1`**, **`3`**, **`5`**. Missing: `0`,`2`,`4`,`6`,`7`,`8`,`9`,
`:`, `.`. See [`ac_720p_pi/README.md`](ac_720p_pi/README.md).

VLC `ac_720p_capture/` remains available when you need a complete set offline, but
on soft Pi MJPEG it mis-ranked lookalikes (`796719` vs truth `1:35.113`).

### Capture more glyphs on the Pi

1. Calibrate `rois.lap_time` so `/debug` shows only the last-lap digits.
2. Open `http://<pi-ip>:8741/debug` while AC shows a known time.
3. Optionally drag a single digit on the ROI crop preview.
4. Pick the symbol and tap **Save glyph**.
5. Files land under `glyphs_dir` (default `templates/lap_time_digits/ac_720p_pi/`).

API: `POST /api/debug/glyphs/save` with JSON `{ "symbol": "5" }` and optional
`x,y,width,height` subcrop in ROI-local pixels.

**Default reader stays `tesseract` (or `mock`).** Point
`detect.lap_time.reader` at `template` only when you intend to use PNG matching —
templates do not help Tesseract.
