# AC 720p capture templates (real Assetto Corsa)

Native-resolution PNGs cropped from a PS5 Assetto Corsa HUD LAST/BEST panel
(VLC capture at ~1280×721). White time digits only — not the LAST/BEST labels.

| File | Symbol | Present |
| --- | --- | --- |
| `0.png` … `6.png`, `8.png` | Digits | Yes |
| `7.png`, `9.png` | Digits | **Missing** — not in the source frame |
| `colon.png` | `:` | Yes |
| `period.png` | `.` | Yes |

`4.png` is the original crop (kept as extracted). Additional captures can still
land under `pending/` via `/debug` → **Save glyph** (gitignored).

Point config here when using the template reader:

```yaml
detect.lap_time.reader: template
detect.lap_time.templates_dir: templates/lap_time_digits/ac_720p_capture
```

Expect match failures on times that need **7** or **9** until those glyphs are
added. Bundled `ac_720p` / `ac_1080p` remain ACC (wrong game) — prefer this
folder for real AC.

See [`docs/ROI.md`](../../docs/ROI.md).
