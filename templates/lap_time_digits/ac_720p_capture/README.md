# AC 720p capture templates (real Assetto Corsa)

Native-resolution PNGs cropped from a PS5 Assetto Corsa HUD LAST/BEST panel
(VLC capture at ~1280×721). White time digits only — not the LAST/BEST labels.

| File | Symbol | Present |
| --- | --- | --- |
| `0.png` … `9.png` | Digits | Yes — complete set |
| `colon.png` | `:` | Yes |
| `period.png` | `.` | Yes |

`7.png` is from LAST `1:46.177`; `9.png` is from BEST `1:19.329`. `4.png` is
the original crop (kept as extracted). Additional captures can still land under
`pending/` via `/debug` → **Save glyph** (gitignored).

Point config here when using the template reader:

```yaml
detect.lap_time.reader: template
detect.lap_time.templates_dir: templates/lap_time_digits/ac_720p_capture
```

Complete real-AC set: digits **0–9** plus colon and period. Bundled `ac_720p` /
`ac_1080p` remain ACC (wrong game) — prefer this folder for real AC.

See [`docs/ROI.md`](../../docs/ROI.md).
