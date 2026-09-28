# Lap-time digit templates (Assetto Corsa block font)

Source: [blofelds/acc-telemetry](https://github.com/blofelds/acc-telemetry)
`templates/speed_digits/ac_1080p/` (same HUD block font as AC speed / lap count).

| Directory | Purpose |
| --- | --- |
| `ac_1080p/` | Original 28×24 glyphs from acc-telemetry |
| `ac_720p/` | Same glyphs scaled ×2/3 for pi2b 720p capture |

`colon.png` / `period.png` are synthetic separators (not in the upstream speed set)
so lap times like `1:44.321` can be matched without OCR.

**Default reader stays `tesseract` (or `mock`).** Point
`detect.lap_time.reader` at `template` only as a backup when OCR fails on this
block font — PNG templates do not help Tesseract.
