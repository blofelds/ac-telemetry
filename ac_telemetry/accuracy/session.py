"""Accuracy session coordinator — only constructed when ``accuracy.enabled``."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from ac_telemetry.accuracy.ocr_log import OcrSampleLog
from ac_telemetry.accuracy.paths import ocr_samples_path, session_dir
from ac_telemetry.accuracy.roi_tee import RoiTeeWriter
from ac_telemetry.settings import AccuracySettings

logger = logging.getLogger(__name__)


class AccuracySession:
    """Owns ROI tee + OCR sample log for the open phone session.

    Safe to call from the detect thread via :meth:`on_sample` (never blocks
    on disk encode — tee queue drops under pressure).
    """

    def __init__(self, settings: AccuracySettings, data_dir: Any) -> None:
        self.settings = settings
        self.data_dir = data_dir
        self._lock = threading.Lock()
        self._session_id: str | None = None
        self._tee: RoiTeeWriter | None = None
        self._ocr: OcrSampleLog | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.enabled)

    def status(self) -> dict[str, Any]:
        with self._lock:
            tee_status = self._tee.status() if self._tee is not None else None
            return {
                "enabled": self.enabled,
                "with_session": self.settings.with_session,
                "roi_tee": self.settings.roi_tee,
                "ocr_log": self.settings.ocr_log,
                "roi_tee_format": self.settings.roi_tee_format,
                "roi_tee_max_per_hold": self.settings.roi_tee_max_per_hold,
                "session_id": self._session_id,
                "ocr_samples": None if self._ocr is None else self._ocr.count,
                "tee": tee_status,
                "subdir": self.settings.subdir,
            }

    def on_session_start(self, session_id: str) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "accuracy disabled"}
        if not self.settings.with_session:
            return {"ok": False, "reason": "with_session false — start manually"}
        return self.start(session_id)

    def on_session_end(self, session_id: str | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "accuracy disabled"}
        return self.stop(session_id=session_id)

    def start(self, session_id: str) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "accuracy disabled"}
        sid = (session_id or "").strip()
        if not sid:
            return {"ok": False, "reason": "missing session_id"}

        sdir = session_dir(self.data_dir, sid, subdir=self.settings.subdir)
        sdir.mkdir(parents=True, exist_ok=True)

        with self._lock:
            if self._session_id and self._session_id != sid:
                self._stop_unlocked()
            self._session_id = sid
            if self.settings.ocr_log:
                self._ocr = OcrSampleLog(ocr_samples_path(sdir))
                self._ocr.open()
            else:
                self._ocr = None
            if self.settings.roi_tee:
                self._tee = RoiTeeWriter(
                    session_dir=sdir,
                    fmt=self.settings.roi_tee_format,
                    jpeg_quality=self.settings.jpeg_quality,
                    queue_size=self.settings.queue_size,
                    max_per_hold=self.settings.roi_tee_max_per_hold,
                )
                try:
                    tee_status = self._tee.start(sid)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Accuracy ROI tee start failed: %s", exc)
                    self._tee = None
                    tee_status = {"error": str(exc)}
            else:
                self._tee = None
                tee_status = None

        logger.info(
            "Accuracy capture started session=%s ocr_log=%s roi_tee=%s",
            sid,
            self.settings.ocr_log,
            self.settings.roi_tee,
        )
        return {
            "ok": True,
            "session_id": sid,
            "dir": str(sdir),
            "tee": tee_status,
            "ocr_log": self.settings.ocr_log,
        }

    def stop(self, session_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if session_id and self._session_id and session_id != self._session_id:
                return {
                    "ok": False,
                    "reason": f"active session is {self._session_id}",
                }
            return self._stop_unlocked()

    def _stop_unlocked(self) -> dict[str, Any]:
        sid = self._session_id
        tee_status = None
        if self._tee is not None:
            try:
                tee_status = self._tee.stop()
            except Exception:  # noqa: BLE001
                logger.debug("Accuracy tee stop failed", exc_info=True)
            self._tee = None
        ocr_count = None if self._ocr is None else self._ocr.count
        self._ocr = None
        self._session_id = None
        if sid:
            logger.info(
                "Accuracy capture stopped session=%s ocr_samples=%s",
                sid,
                ocr_count,
            )
        return {
            "ok": True,
            "session_id": sid,
            "tee": tee_status,
            "ocr_samples": ocr_count,
        }

    def on_sample(
        self,
        *,
        session_id: str | None,
        mono_s: float,
        wall_s: float,
        ok: bool,
        text: str,
        lap_time_ms: int | None,
        error: str,
        roi_img: Any | None,
    ) -> None:
        """Detect-thread observer. No-op unless this session is capturing."""
        if not self.enabled:
            return
        with self._lock:
            active_id = self._session_id
            ocr = self._ocr
            tee = self._tee
        if not active_id:
            return
        if session_id and session_id != active_id:
            return

        if ocr is not None:
            try:
                ocr.append(
                    {
                        "session_id": active_id,
                        "mono_s": round(mono_s, 6),
                        "wall_s": round(wall_s, 6),
                        "ok": bool(ok),
                        "text": text or "",
                        "lap_time_ms": lap_time_ms,
                        "error": error or "",
                    }
                )
            except Exception:  # noqa: BLE001
                logger.debug("OCR sample log append failed", exc_info=True)

        if tee is not None and roi_img is not None:
            tee.offer(
                mono_s=mono_s,
                wall_s=wall_s,
                roi_bgr=roi_img,
                text=text or "",
                lap_time_ms=lap_time_ms,
                ok=bool(ok),
            )


def maybe_accuracy_session(
    settings: AccuracySettings, data_dir: Any
) -> AccuracySession | None:
    """Return an AccuracySession only when the master switch is on.

    When ``enabled`` is false, returns ``None`` so ``main`` wires no detect
    hook and incurs no accuracy cost.
    """
    if not settings.enabled:
        return None
    return AccuracySession(settings, data_dir)


def sample_now() -> tuple[float, float]:
    """(mono_s, wall_s) pair for detect alignment."""
    return time.monotonic(), time.time()
