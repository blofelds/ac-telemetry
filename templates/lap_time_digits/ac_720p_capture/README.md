# AC 720p capture templates (real Assetto Corsa)

PNG digits / separators cut from the live Pi HDMI ROI via `/debug` →
**Save glyph**. Empty until you capture on the Pi.

| File | Symbol |
| --- | --- |
| `0.png` … `9.png` | Digits |
| `colon.png` | `:` |
| `period.png` | `.` |
| `pending/*.png` | Unlabeled full-ROI (or subcrop) dumps |

Bundled sibling dirs `ac_720p` / `ac_1080p` may be **ACC** glyphs (wrong game).
Do not expect them to match PS5 Assetto Corsa until replaced. After you have
a full labeled set here, set:

```yaml
detect.lap_time.reader: template
detect.lap_time.templates_dir: templates/lap_time_digits/ac_720p_capture
```

See [`docs/ROI.md`](../../docs/ROI.md).
