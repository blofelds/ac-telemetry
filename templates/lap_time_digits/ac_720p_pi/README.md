# AC 720p Pi templates (live HDMI detect path)

Native-resolution PNGs cropped from a **live Pi detect dump** ROI
(`ac-detect-dump-20261001-221758`, ground truth `1:35.113`). Mask-aware tight
crops (non-ink zeroed, ink bbox trimmed) — soft MJPEG / HDMI capture domain,
not the sharper VLC `ac_720p_capture` set.

| File | Symbol | Source |
| --- | --- | --- |
| `1.png` | `1` | Live dump span `[3,7]` |
| `3.png` | `3` | Live dump span `[13,24]` |
| `5.png` | `5` | Live dump span `[25,36]` |
| `0.png`, `2.png`, `4.png`, `6.png`, `7.png`, `8.png`, `9.png` | — | **Missing** (not in this ROI) |
| `colon.png`, `period.png` | — | **Missing** (separator recovery is follow-on) |

Do **not** silently copy missing digits from `ac_720p_capture` — that mixes VLC
sharpness with soft Pi MJPEG and reintroduces the `1↔7` / `3↔9` / `5↔6`
lookalike failures diagnosed on this dump. Fill gaps with more live Pi Save
glyph crops when those digits appear on the HUD.

Point config here for Pi 720p template matching:

```yaml
detect.lap_time.reader: template
detect.lap_time.templates_dir: templates/lap_time_digits/ac_720p_pi
glyphs_dir: templates/lap_time_digits/ac_720p_pi
```

Offline rematch of the dump ROI with this incomplete set yields digit labels
`135113` (beats capture-domain `796719`). Separators are still absent — parse
to `1:35.113` needs a later scoped separator fix.

See [`../README.md`](../README.md) and [`docs/ROI.md`](../../../docs/ROI.md).
