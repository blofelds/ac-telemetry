"""Save lap-time ROI crops as digit/separator PNG templates.

Bundled ``templates/lap_time_digits/ac_*`` may be ACC (wrong game). This
helper writes real AC crops from the live capture handoff so Gary can build
a matching template set on the Pi without an offline editor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ac_telemetry.detect.roi import crop_roi
from ac_telemetry.settings import RoiRect

# Filenames expected by DigitTemplateMatcher._load_templates.
_SYMBOL_FILES: dict[str, str] = {
    **{d: f"{d}.png" for d in "0123456789"},
    ":": "colon.png",
    "colon": "colon.png",
    ".": "period.png",
    "period": "period.png",
}


def resolve_symbol_filename(symbol: str | None) -> str | None:
    """Map a UI/API symbol to a template filename, or None for pending dumps."""
    if symbol is None:
        return None
    key = str(symbol).strip().lower()
    if not key:
        return None
    if key not in _SYMBOL_FILES:
        raise ValueError(
            f"Unknown symbol {symbol!r}. Use 0-9, ':'/colon, or '.'/period."
        )
    return _SYMBOL_FILES[key]


def subcrop_bgr(
    image: Any,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> Any | None:
    """Crop a sub-rectangle in image-local coords (same rules as ``crop_roi``)."""
    return crop_roi(image, RoiRect(x=x, y=y, width=width, height=height))


def encode_png(image: Any) -> bytes:
    """Lossless PNG bytes (templates must not be JPEG-compressed)."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV (cv2) is required to save glyph PNGs. "
            "On Pi 2B: sudo apt install python3-opencv with a "
            "--system-site-packages venv."
        ) from exc
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("cv2.imencode(.png) failed")
    return buf.tobytes()


def save_glyph_png(
    frame: Any,
    roi: RoiRect,
    dest_dir: Path,
    *,
    symbol: str | None = None,
    sub_x: int | None = None,
    sub_y: int | None = None,
    sub_width: int | None = None,
    sub_height: int | None = None,
) -> dict[str, Any]:
    """Crop ``rois.lap_time`` (optional sub-rect) and write a PNG under ``dest_dir``.

    * With ``symbol`` → ``0.png``…``9.png`` / ``colon.png`` / ``period.png``
      (overwrites existing).
    * Without ``symbol`` → ``pending/<utc-timestamp>.png`` so full-strip dumps
      stay out of the way of labeled templates.
    """
    if frame is None:
        raise ValueError("No frame available")
    crop = crop_roi(frame, roi)
    if crop is None:
        raise ValueError("Empty or out-of-bounds ROI crop")

    subs = (sub_x, sub_y, sub_width, sub_height)
    if any(v is not None for v in subs):
        if any(v is None for v in subs):
            raise ValueError(
                "Sub-crop requires x, y, width, and height together"
            )
        assert sub_x is not None and sub_y is not None
        assert sub_width is not None and sub_height is not None
        if sub_width < 1 or sub_height < 1:
            raise ValueError("Sub-crop width/height must be >= 1")
        patch = subcrop_bgr(
            crop, x=sub_x, y=sub_y, width=sub_width, height=sub_height
        )
        if patch is None:
            raise ValueError("Sub-crop is empty or outside the ROI")
        crop = patch

    filename = resolve_symbol_filename(symbol)
    dest_dir = Path(dest_dir)
    if filename is None:
        pending = dest_dir / "pending"
        pending.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = pending / f"{stamp}.png"
    else:
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / filename

    payload = encode_png(crop)
    path.write_bytes(payload)
    h, w = int(crop.shape[0]), int(crop.shape[1])
    return {
        "path": str(path),
        "filename": path.name,
        "symbol": None if filename is None else symbol,
        "width": w,
        "height": h,
        "bytes": len(payload),
    }
