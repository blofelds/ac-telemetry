# AC 720p Pi templates (live HDMI detect path)

Native-resolution PNGs cropped from **live Pi detect dumps**. Mask-aware tight
crops (non-ink zeroed, ink bbox trimmed) — soft MJPEG / HDMI capture domain,
not the sharper VLC `ac_720p_capture` set. Do **not** hybridize missing glyphs
from VLC without documenting the risk (`1↔7` / `3↔9` / `5↔6` lookalikes).

## Inventory (complete 0–9 + separators)

| File | Symbol | Source dump | Notes |
| --- | --- | --- | --- |
| `0.png` | `0` | `ac-detect-dump-20261001-234819` | Span `[18,28]`, GT `1:10.375`; y clipped `<14` |
| `1.png` | `1` | `ac-detect-dump-20261001-221758` | Span `[3,7]`, GT `1:35.113` |
| `2.png` | `2` | `ac-detect-dump-20261002-000013` | Minutes span `[3,13]`, GT `2:34.492` |
| `3.png` | `3` | `ac-detect-dump-20261001-221758` | Span `[13,24]`, GT `1:35.113` |
| `4.png` | `4` | `ac-detect-dump-20261002-000013` | Isolated post-period `[45,55]`, GT `2:34.492` |
| `5.png` | `5` | `ac-detect-dump-20261001-221758` | Span `[25,36]`, GT `1:35.113` |
| `6.png` | `6` | `ac-detect-dump-20261001-235208` | Split glued `[39,61]` at x=50; y clipped `<14` |
| `7.png` | `7` | `ac-detect-dump-20261001-234819` | Span `[46,54]`, GT `1:10.375` |
| `8.png` | `8` | `ac-detect-dump-20261001-231449` | Thousandths span `[53,64]` |
| `9.png` | `9` | `ac-detect-dump-20261001-231449` | Tenths span `[34,45]` |
| `colon.png` | `:` | `ac-detect-dump-20261001-232108` | Tight color-ROI (2×10); midtone |
| `period.png` | `.` | `ac-detect-dump-20261001-232108` | Tight color-ROI (3×2); midtone |

## Domain + matcher honesty

- **Digits** rematch soft-Pi ROIs that the VLC set mislabeled (`796719` →
  `135113` on dump `221758`; `234492` on dump `000013`; `107960` on dump
  `20261002-002656` after span recovery).
- **Digit span recovery** absorbs multi-column 1-ink bridges (severed `7` top
  bar) and splits oversized glued runs at digit-pitch valleys (`9`+`6`).
- **Separators are included** as live-domain PNGs, but current
  `white_mask` (`V≥150`) zeros their midtone ink on load, so colon/period still
  do not enter the symbol string. Parse to `1:07.960` / `1:35.113` needs a
  **follow-on** separator fix — not soft-MJPEG matcher v2.
- Point config here for Pi 720p template matching:

```yaml
detect.lap_time.reader: template
detect.lap_time.templates_dir: templates/lap_time_digits/ac_720p_pi
glyphs_dir: templates/lap_time_digits/ac_720p_pi
```

See [`../README.md`](../README.md) and [`docs/ROI.md`](../../../docs/ROI.md).
