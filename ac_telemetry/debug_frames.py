"""Encode debug JPEGs from a frame copy (Pi 2B-friendly).

Callers should pass a frame already copied off the capture handoff so JPEG
work never holds the capture lock. No ffmpeg — OpenCV ``imencode`` only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ac_telemetry.detect.roi import crop_roi
from ac_telemetry.settings import RoiRect

# Modest quality keeps CPU-friendly payloads small on Pi 2B.
_JPEG_QUALITY = 70

# Distinct BGR colors so multiple ROI boxes stay readable on one frame.
_ROI_COLORS: tuple[tuple[int, int, int], ...] = (
    (0, 255, 0),  # green
    (0, 200, 255),  # amber
    (255, 180, 0),  # sky
    (255, 80, 255),  # magenta
    (80, 255, 255),  # yellow
)


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


def _draw_roi(
    snap: Any,
    name: str,
    roi: RoiRect,
    *,
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    """Draw one labeled ROI rectangle onto ``snap`` (mutates in place)."""
    cv2 = _require_cv2()
    x1 = int(roi.x)
    y1 = int(roi.y)
    x2 = int(roi.x + roi.width)
    y2 = int(roi.y + roi.height)
    cv2.rectangle(snap, (x1, y1), (x2, y2), color, thickness)
    label = f"{name} {roi.width}x{roi.height}@({roi.x},{roi.y})"
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


def encode_overlay_jpeg(
    frame: Any,
    roi: RoiRect | None,
    *,
    name: str = "lap_time",
    color: tuple[int, int, int] = (0, 255, 0),
    thickness: int = 2,
) -> bytes | None:
    """Full-frame JPEG with one ROI rectangle drawn (BGR green by default)."""
    if frame is None:
        return None
    # Draw on a copy so callers can reuse the snapshot for other crops.
    try:
        snap = frame.copy()
    except AttributeError:
        return None
    if roi is not None:
        _draw_roi(snap, name, roi, color=color, thickness=thickness)
    return encode_jpeg(snap)


def encode_rois_overlay_jpeg(
    frame: Any,
    rois: Mapping[str, RoiRect],
    *,
    thickness: int = 2,
) -> bytes | None:
    """Full-frame JPEG with every configured ROI drawn (capture resolution).

    Used for the downloadable calibration screenshot — same pixel size as the
    latest capture handoff, not a CSS-scaled preview.
    """
    if frame is None:
        return None
    try:
        snap = frame.copy()
    except AttributeError:
        return None
    # Stable order so colors stay consistent across refreshes.
    for i, name in enumerate(sorted(rois)):
        color = _ROI_COLORS[i % len(_ROI_COLORS)]
        _draw_roi(snap, name, rois[name], color=color, thickness=thickness)
    return encode_jpeg(snap)
