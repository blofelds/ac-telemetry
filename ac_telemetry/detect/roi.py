"""Crop a named ROI from a BGR frame without copying the full frame twice."""

from __future__ import annotations

from typing import Any

from ac_telemetry.settings import RoiRect


def crop_roi(frame: Any, roi: RoiRect) -> Any | None:
    """Return a view/copy of ``frame[y:y+h, x:x+w]``, or None if invalid.

    Accepts any array-like with shape ``(H, W, …)``. Returns None when the
    ROI is empty or falls completely outside the frame — callers treat that
    as a soft miss rather than a crash.
    """
    if frame is None:
        return None
    try:
        height, width = int(frame.shape[0]), int(frame.shape[1])
    except (AttributeError, IndexError, TypeError, ValueError):
        return None
    if height <= 0 or width <= 0:
        return None

    x0 = max(0, roi.x)
    y0 = max(0, roi.y)
    x1 = min(width, roi.x + roi.width)
    y1 = min(height, roi.y + roi.height)
    if x1 <= x0 or y1 <= y0:
        return None

    # Copy so the capture thread can overwrite the shared latest-frame buffer.
    return frame[y0:y1, x0:x1].copy()
