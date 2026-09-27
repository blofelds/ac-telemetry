"""Encode debug JPEGs from a frame copy (Pi 2B-friendly).

Callers should pass a frame already copied off the capture handoff so JPEG
work never holds the capture lock. No ffmpeg — OpenCV ``imencode`` only.
"""

from __future__ import annotations

from typing import Any

from ac_telemetry.detect.roi import crop_roi
from ac_telemetry.settings import RoiRect

# Modest quality keeps CPU-friendly payloads small on Pi 2B.
_JPEG_QUALITY = 70


def _require_cv2():
    try:
        import cv2  # lazy: only needed when serving debug images
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV (cv2) is required to encode debug JPEGs. "
            "On Pi 2B: sudo apt install python3-opencv with a "
            "--system-site-packages venv."
        ) from exc
    return cv2


def encode_jpeg(image: Any, *, quality: int = _JPEG_QUALITY) -> bytes:
    """Encode a BGR (or gray) array as JPEG bytes."""
    cv2 = _require_cv2()
    ok, buf = cv2.imencode(
        ".jpg",
        image,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
    )
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    return buf.tobytes()


def encode_full_frame_jpeg(frame: Any) -> bytes | None:
    """JPEG of a full frame copy, or None if ``frame`` is missing."""
    if frame is None:
        return None
    return encode_jpeg(frame)


def encode_roi_jpeg(frame: Any, roi: RoiRect) -> bytes | None:
    """JPEG of a ROI crop, or None if the crop is empty/invalid."""
    if frame is None:
        return None
    crop = crop_roi(frame, roi)
    if crop is None:
        return None
    return encode_jpeg(crop)


def encode_overlay_jpeg(
    frame: Any,
    roi: RoiRect | None,
    *,
    color: tuple[int, int, int] = (0, 255, 0),
    thickness: int = 2,
) -> bytes | None:
    """Full-frame JPEG with the ROI rectangle drawn (BGR green by default)."""
    if frame is None:
        return None
    cv2 = _require_cv2()
    # Draw on a copy so callers can reuse the snapshot for other crops.
    try:
        snap = frame.copy()
    except AttributeError:
        return None
    if roi is not None:
        x1 = int(roi.x)
        y1 = int(roi.y)
        x2 = int(roi.x + roi.width)
        y2 = int(roi.y + roi.height)
        cv2.rectangle(snap, (x1, y1), (x2, y2), color, thickness)
        label = f"lap_time {roi.width}x{roi.height}@({roi.x},{roi.y})"
        cv2.putText(
            snap,
            label,
            (max(0, x1), max(16, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )
    return encode_jpeg(snap)
