"""Session-scoped lap_time ROI tee (detect-aligned, non-blocking).

Writes tiny ROI crops only — never full frames. OpenCV encode path; no
H.264. Detect thread offers frames via a bounded queue (drop under pressure).
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

RoiTeeFormat = Literal["jpeg_seq", "mjpeg", "avi"]


@dataclass
class RoiTeeStatus:
    active: bool = False
    session_id: str | None = None
    path: str | None = None
    frames_written: int = 0
    frames_dropped: int = 0
    format: str = "jpeg_seq"
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "session_id": self.session_id,
            "path": self.path,
            "frames_written": self.frames_written,
            "frames_dropped": self.frames_dropped,
            "format": self.format,
            "error": self.error,
        }


@dataclass
class _RoiItem:
    seq: int
    mono_s: float
    wall_s: float
    roi_bgr: Any
    text: str
    lap_time_ms: int | None
    ok: bool


@dataclass
class RoiTeeWriter:
    """Background writer for detect-aligned ROI crops under a session dir."""

    session_dir: Path
    fmt: RoiTeeFormat = "jpeg_seq"
    jpeg_quality: int = 70
    queue_size: int = 2
    _queue: queue.Queue[_RoiItem | None] = field(init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _status: RoiTeeStatus = field(default_factory=RoiTeeStatus, init=False)
    _seq: int = field(default=0, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    _cv2: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._queue = queue.Queue(maxsize=max(1, int(self.queue_size)))

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status.as_dict()

    def start(self, session_id: str) -> dict[str, Any]:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV (cv2) is required for accuracy ROI tee. "
                "On Pi 2B use apt python3-opencv + system-site-packages venv."
            ) from exc

        roi_dir = self.session_dir / "roi"
        roi_dir.mkdir(parents=True, exist_ok=True)
        manifest = self.session_dir / "roi_manifest.jsonl"

        with self._lock:
            if self._status.active or (
                self._thread is not None and self._thread.is_alive()
            ):
                raise RuntimeError("ROI tee already active")
            self._cv2 = cv2
            self._stop.clear()
            self._seq = 0
            self._status = RoiTeeStatus(
                active=True,
                session_id=session_id,
                path=str(roi_dir if self.fmt == "jpeg_seq" else self.session_dir),
                format=self.fmt,
            )
            self._thread = threading.Thread(
                target=self._writer_loop,
                name="accuracy-roi-tee",
                daemon=True,
                args=(roi_dir, manifest, session_id),
            )
            self._thread.start()
            return self._status.as_dict()

    def stop(self, *, join_timeout: float = 3.0) -> dict[str, Any]:
        with self._lock:
            thread = self._thread
            alive = thread is not None and thread.is_alive()
            if not self._status.active and not alive:
                return self._status.as_dict()
            self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
        if thread is not None:
            thread.join(timeout=max(0.1, float(join_timeout)))
        with self._lock:
            self._status.active = False
            self._thread = None
            return self._status.as_dict()

    def offer(
        self,
        *,
        mono_s: float,
        wall_s: float,
        roi_bgr: Any | None,
        text: str,
        lap_time_ms: int | None,
        ok: bool,
    ) -> None:
        """Non-blocking offer from the detect thread. Drops when busy."""
        if roi_bgr is None:
            return
        with self._lock:
            if not self._status.active:
                return
            self._seq += 1
            seq = self._seq
            if self._queue.full():
                self._status.frames_dropped += 1
                return
        try:
            payload = roi_bgr.copy()
        except AttributeError:
            return
        item = _RoiItem(
            seq=seq,
            mono_s=mono_s,
            wall_s=wall_s,
            roi_bgr=payload,
            text=text,
            lap_time_ms=lap_time_ms,
            ok=ok,
        )
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            with self._lock:
                self._status.frames_dropped += 1

    def _writer_loop(
        self, roi_dir: Path, manifest: Path, session_id: str
    ) -> None:
        assert self._cv2 is not None
        cv2 = self._cv2
        writer = None
        video_path: Path | None = None
        written = 0
        try:
            if self.fmt in ("mjpeg", "avi"):
                # Container chosen at first frame once size is known.
                pass
            while not self._stop.is_set():
                try:
                    item = self._queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if item is None:
                    break
                h, w = int(item.roi_bgr.shape[0]), int(item.roi_bgr.shape[1])
                rel_path: str
                if self.fmt == "jpeg_seq":
                    # Monotonic ms in filename for easy window slicing.
                    mono_ms = int(item.mono_s * 1000.0)
                    name = f"{item.seq:06d}_{mono_ms}.jpg"
                    out = roi_dir / name
                    ok = cv2.imwrite(
                        str(out),
                        item.roi_bgr,
                        [int(cv2.IMWRITE_JPEG_QUALITY), int(self.jpeg_quality)],
                    )
                    if not ok:
                        continue
                    rel_path = f"roi/{name}"
                else:
                    if writer is None:
                        ext = ".avi" if self.fmt == "avi" else ".avi"
                        # OpenCV MJPG in AVI is the Pi-safe strip path.
                        video_path = self.session_dir / f"roi_tee{ext}"
                        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                        # Detect FPS is typically ~2; writer fps is metadata only.
                        writer = cv2.VideoWriter(
                            str(video_path), fourcc, 2.0, (w, h)
                        )
                        if not writer.isOpened():
                            raise RuntimeError(
                                f"Failed to open ROI VideoWriter at {video_path}"
                            )
                        with self._lock:
                            self._status.path = str(video_path)
                    writer.write(item.roi_bgr)
                    rel_path = video_path.name if video_path else "roi_tee.avi"

                row = {
                    "seq": item.seq,
                    "session_id": session_id,
                    "mono_s": round(item.mono_s, 6),
                    "wall_s": round(item.wall_s, 6),
                    "ok": item.ok,
                    "text": item.text,
                    "lap_time_ms": item.lap_time_ms,
                    "path": rel_path,
                }
                with manifest.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=True))
                    fh.write("\n")
                written += 1
                with self._lock:
                    self._status.frames_written = written
        except Exception as exc:  # noqa: BLE001
            logger.exception("Accuracy ROI tee failed: %s", exc)
            with self._lock:
                self._status.error = str(exc)
        finally:
            if writer is not None:
                try:
                    writer.release()
                except Exception:  # noqa: BLE001
                    logger.debug("ROI VideoWriter release failed", exc_info=True)
            with self._lock:
                self._status.active = False
                self._status.frames_written = written
            logger.info(
                "Accuracy ROI tee stopped session=%s frames=%s dropped=%s",
                session_id,
                written,
                self._status.frames_dropped,
            )
