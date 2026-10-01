"""Build / encode last-detect dump artifacts (Pi 2B–friendly).

One slot in RAM: metadata dict + optional ROI/mask ndarrays. PNG encode
happens on HTTP GET only — never in the detect loop.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from ac_telemetry.runtime_info import runtime_snapshot
from ac_telemetry.settings import RoiRect, Settings


def _array_sha256(image: Any) -> str | None:
    """Hash contiguous ndarray bytes (cheap; no PNG encode in detect loop)."""
    if image is None:
        return None
    try:
        import numpy as np

        arr = np.ascontiguousarray(image)
        return hashlib.sha256(arr.tobytes()).hexdigest()
    except Exception:  # noqa: BLE001
        return None


def _encode_png(image: Any) -> bytes | None:
    if image is None:
        return None
    try:
        import cv2
    except ImportError:
        return None
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        return None
    return buf.tobytes()


@dataclass
class LastDetectDump:
    """In-memory last detect attempt (typically a failure)."""

    meta: dict[str, Any] = field(default_factory=dict)
    roi_bgr: Any | None = None
    mask: Any | None = None
    captured_at: float | None = None

    def clear(self) -> None:
        self.meta = {}
        self.roi_bgr = None
        self.mask = None
        self.captured_at = None

    def as_json(self) -> dict[str, Any] | None:
        if not self.meta:
            return None
        return dict(self.meta)

    def roi_png(self) -> bytes | None:
        return _encode_png(self.roi_bgr)

    def mask_png(self) -> bytes | None:
        return _encode_png(self.mask)

    def annotated_png(self) -> bytes | None:
        """ROI with span boxes + chosen labels (encode on request only)."""
        if self.roi_bgr is None:
            return None
        try:
            import cv2
        except ImportError:
            return None
        try:
            snap = self.roi_bgr.copy()
        except AttributeError:
            return None
        glyphs = (self.meta.get("glyphs") or []) if self.meta else []
        for row in glyphs:
            span = row.get("span") or [0, 0]
            x0, x1 = int(span[0]), int(span[1])
            color = (0, 255, 0) if row.get("chosen") else (0, 0, 255)
            h = int(snap.shape[0])
            cv2.rectangle(snap, (x0, 0), (max(x0 + 1, x1), max(1, h - 1)), color, 1)
            label = row.get("chosen") or "?"
            cv2.putText(
                snap,
                str(label),
                (x0, max(10, h - 2)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                color,
                1,
                cv2.LINE_AA,
            )
        return _encode_png(snap)


def build_dump_meta(
    *,
    settings: Settings,
    ok: bool,
    error: str | None,
    latency_seconds: float,
    reading_text: str,
    reading_ms: int | None,
    diagnostics: dict[str, Any] | None,
    roi: RoiRect | None,
    roi_bgr: Any | None,
    mask: Any | None,
    capture_info: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble JSON-serializable dump metadata (no ndarrays)."""
    diag = dict(diagnostics or {})
    # Never put the mask ndarray into JSON.
    diag.pop("mask", None)

    frame_info = {
        "capture_frames": (capture_info or {}).get("frames"),
        "age_seconds_at_detect": (capture_info or {}).get("last_frame_age_seconds"),
        "roi_sha256": _array_sha256(roi_bgr),
        "mask_sha256": _array_sha256(mask),
    }

    templates_dir = diag.get("templates_dir")
    if not templates_dir:
        templates_dir = settings.detect.lap_time.templates_dir

    profile = settings.active_profile()
    config = {
        "reader": settings.detect.lap_time.reader,
        "templates_dir": templates_dir,
        "match_threshold": settings.detect.lap_time.match_threshold,
        "prefer_mjpeg": settings.prefer_mjpeg,
        "backend": settings.backend,
        "device": settings.device,
        "profile": settings.profile,
        "width": profile.width,
        "height": profile.height,
        "detect_fps": settings.detect.fps,
        "debug_dump": settings.detect.debug_dump.model_dump(),
    }

    raw_symbols = None
    parsed = None
    if ok and reading_ms is not None:
        raw_symbols = reading_text
        parsed = {"text": reading_text, "lap_time_ms": reading_ms}
    elif reading_text:
        raw_symbols = reading_text

    # Prefer matcher-provided raw when present in diag path failures without text.
    glyphs = diag.get("glyphs") or []
    if raw_symbols is None and glyphs:
        chosen = [g.get("chosen") for g in glyphs]
        if all(chosen):
            raw_symbols = "".join(str(c) for c in chosen)

    return {
        "ok": ok,
        "error": error,
        "detect_at": time.time(),
        "latency_seconds": round(float(latency_seconds), 4),
        "frame": frame_info,
        "roi": None
        if roi is None
        else {
            "x": roi.x,
            "y": roi.y,
            "width": roi.width,
            "height": roi.height,
        },
        "white_mask": diag.get("white_mask"),
        "spans": diag.get("spans") or [],
        "glyphs": glyphs,
        "raw_symbols": raw_symbols,
        "parsed": parsed,
        "config": config,
        "runtime": runtime_snapshot(),
        "template_labels": diag.get("template_labels"),
        "canvas": diag.get("canvas"),
    }
