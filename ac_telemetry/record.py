"""Bounded card-native frame recorder (tee from the capture thread).

Writes full-resolution frames the capture loop already owns — never opens
``/dev/video0`` itself.

Pi 2B path: JPEG sequence while recording (cheap), then a short ffmpeg mux on
stop. Fallback: OpenCV MJPEG VideoWriter when ffmpeg is missing.
"""

from __future__ import annotations

import logging
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DURATION_SECONDS = 60
MAX_DURATION_SECONDS = 120
MIN_DURATION_SECONDS = 1
DEFAULT_WRITE_FPS = 2.0
_QUEUE_MAXSIZE = 2
_JPEG_QUALITY = 75


@dataclass
class RecordStatus:
    """Snapshot of recorder state for the HTTP API."""

    recording: bool = False
    path: str | None = None
    started_at: float | None = None
    duration_seconds: float = 0.0
    max_seconds: float = 0.0
    frames_written: int = 0
    frames_dropped: int = 0
    frames_skipped: int = 0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    codec: str = ""
    error: str | None = None
    finished: bool = False

    def as_dict(self) -> dict[str, Any]:
        elapsed = 0.0
        if self.started_at is not None:
            if self.recording:
                elapsed = max(0.0, time.time() - self.started_at)
            else:
                elapsed = self.duration_seconds
        return {
            "recording": self.recording,
            "path": self.path,
            "started_at": self.started_at,
            "elapsed_seconds": round(elapsed, 3),
            "duration_seconds": round(self.duration_seconds, 3),
            "max_seconds": self.max_seconds,
            "frames_written": self.frames_written,
            "frames_dropped": self.frames_dropped,
            "frames_skipped": self.frames_skipped,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "codec": self.codec,
            "error": self.error,
            "finished": self.finished,
        }


class FrameRecorder:
    """Tee full frames from the capture loop into a bounded video file."""

    def __init__(
        self,
        *,
        output_dir: Path,
        default_seconds: float = DEFAULT_DURATION_SECONDS,
        max_seconds: float = MAX_DURATION_SECONDS,
        fps: float = DEFAULT_WRITE_FPS,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._default_seconds = float(default_seconds)
        self._max_seconds = float(max_seconds)
        self._fps = float(fps)
        self._lock = threading.Lock()
        self._status = RecordStatus()
        self._queue: queue.Queue[object | None] | None = None
        self._thread: threading.Thread | None = None
        self._timer: threading.Timer | None = None
        self._stop = threading.Event()
        self._cv2 = None
        self._next_due = 0.0

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._reap_writer_unlocked()
            return self._status.as_dict()

    def start(
        self,
        *,
        duration_seconds: float | None = None,
        output_dir: Path | str | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: float | None = None,
    ) -> dict[str, Any]:
        """Begin recording. Raises ValueError / RuntimeError on bad args / busy."""
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV (cv2) is required to record frames. "
                "On Pi 2B use apt python3-opencv + system-site-packages venv."
            ) from exc

        secs = self._default_seconds if duration_seconds is None else float(duration_seconds)
        if secs < MIN_DURATION_SECONDS:
            raise ValueError(f"duration_seconds must be >= {MIN_DURATION_SECONDS}")
        if secs > self._max_seconds:
            raise ValueError(
                f"duration_seconds {secs} exceeds max_seconds {self._max_seconds}"
            )

        out_dir = Path(output_dir) if output_dir is not None else self._output_dir
        out_dir = out_dir.expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        use_ffmpeg = shutil.which("ffmpeg") is not None
        # Final container after mux (or AVI if ffmpeg missing).
        path = out_dir / (
            f"{stamp}_card_1280x720.mjpeg" if use_ffmpeg else f"{stamp}_card_1280x720.avi"
        )
        frames_dir = out_dir / f".{stamp}_frames"
        use_fps = float(fps) if fps is not None else self._fps
        use_fps = max(1.0, min(use_fps, DEFAULT_WRITE_FPS))
        codec = "jpeg-seq+ffmpeg" if use_ffmpeg else "MJPG"

        with self._lock:
            self._reap_writer_unlocked()
            if self._status.recording or (
                self._thread is not None and self._thread.is_alive()
            ):
                raise RuntimeError("Recording already in progress")
            self._cv2 = cv2
            self._stop.clear()
            self._next_due = 0.0
            self._queue = queue.Queue(maxsize=_QUEUE_MAXSIZE)
            self._status = RecordStatus(
                recording=True,
                path=str(path),
                started_at=time.time(),
                duration_seconds=0.0,
                max_seconds=secs,
                frames_written=0,
                frames_dropped=0,
                frames_skipped=0,
                width=int(width or 0),
                height=int(height or 0),
                fps=use_fps,
                codec=codec,
                error=None,
                finished=False,
            )
            self._thread = threading.Thread(
                target=self._writer_loop,
                name="frame-recorder",
                daemon=True,
                args=(
                    path,
                    frames_dir,
                    secs,
                    use_fps,
                    int(width or 0),
                    int(height or 0),
                    use_ffmpeg,
                ),
            )
            self._thread.start()
            self._timer = threading.Timer(secs, self._auto_stop)
            self._timer.daemon = True
            self._timer.start()
            return self._status.as_dict()

    def request_stop(self) -> None:
        """Non-blocking stop signal (safe from a SIGINT handler)."""
        with self._lock:
            timer = self._timer
            self._timer = None
            q = self._queue
            if not self._status.recording and (
                self._thread is None or not self._thread.is_alive()
            ):
                return
            self._stop.set()
        if timer is not None:
            timer.cancel()
        if q is not None:
            self._signal_writer_stop(q)

    def stop(self, *, join_timeout: float = 30.0) -> dict[str, Any]:
        """Stop recording and finalize the file (idempotent).

        ``join_timeout`` bounds how long process shutdown waits on the writer /
        ffmpeg mux thread — keep this short for Ctrl-C on a memory-tight Pi.
        """
        with self._lock:
            timer = self._timer
            self._timer = None
            thread = self._thread
            q = self._queue
            alive = thread is not None and thread.is_alive()
            if not self._status.recording and not alive:
                self._reap_writer_unlocked()
                return self._status.as_dict()
            self._stop.set()
        if timer is not None:
            timer.cancel()
        if q is not None:
            self._signal_writer_stop(q)
        if thread is not None:
            thread.join(timeout=max(0.1, float(join_timeout)))
        with self._lock:
            self._reap_writer_unlocked()
            self._status.recording = False
            self._status.finished = True
            if self._status.started_at is not None and self._status.duration_seconds <= 0:
                self._status.duration_seconds = max(
                    0.0, time.time() - self._status.started_at
                )
            return self._status.as_dict()

    def _auto_stop(self) -> None:
        try:
            self.stop()
        except Exception:  # noqa: BLE001
            logger.debug("Recorder auto-stop failed", exc_info=True)

    def offer_frame(self, frame: object | None) -> None:
        """Non-blocking tee from the capture loop. No-op when idle / mock None."""
        if frame is None:
            return
        now = time.monotonic()
        with self._lock:
            if not self._status.recording or self._queue is None:
                return
            q = self._queue
            interval = 1.0 / max(self._status.fps, 1.0)
            if now < self._next_due:
                self._status.frames_skipped += 1
                return
            self._next_due = now + interval
            if q.full():
                self._status.frames_dropped += 1
                return
        try:
            payload = frame.copy()  # type: ignore[attr-defined]
        except AttributeError:
            return
        try:
            q.put_nowait(payload)
        except queue.Full:
            with self._lock:
                self._status.frames_dropped += 1

    @staticmethod
    def _signal_writer_stop(q: queue.Queue[object | None]) -> None:
        try:
            q.put_nowait(None)
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(None)
            except queue.Full:
                pass

    def _reap_writer_unlocked(self) -> None:
        thread = self._thread
        if thread is not None and not thread.is_alive():
            self._thread = None
            self._queue = None
            self._status.recording = False
            self._status.finished = True

    def _writer_loop(
        self,
        path: Path,
        frames_dir: Path,
        max_seconds: float,
        fps: float,
        width_hint: int,
        height_hint: int,
        use_ffmpeg: bool,
    ) -> None:
        assert self._cv2 is not None
        cv2 = self._cv2
        frames = 0
        started = time.time()
        writer = None
        width = width_hint
        height = height_hint
        try:
            if use_ffmpeg:
                frames_dir.mkdir(parents=True, exist_ok=True)
            while not self._stop.is_set():
                if time.time() - started >= max_seconds:
                    break
                assert self._queue is not None
                try:
                    item = self._queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if item is None:
                    break
                h, w = int(item.shape[0]), int(item.shape[1])  # type: ignore[attr-defined]
                width, height = w, h
                if frames == 0:
                    with self._lock:
                        self._status.width = w
                        self._status.height = h
                    logger.info(
                        "Recording started path=%s %sx%s @ %.1f fps max=%.0fs mode=%s",
                        path,
                        w,
                        h,
                        fps,
                        max_seconds,
                        "jpeg-seq" if use_ffmpeg else "cv2",
                    )

                if use_ffmpeg:
                    jpg_path = frames_dir / f"{frames + 1:06d}.jpg"
                    ok = cv2.imwrite(
                        str(jpg_path),
                        item,
                        [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY],
                    )
                    if not ok:
                        continue
                else:
                    if writer is None:
                        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                        writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
                        if not writer.isOpened():
                            raise RuntimeError(f"Failed to open VideoWriter at {path}")
                    writer.write(item)

                frames += 1
                with self._lock:
                    self._status.frames_written = frames
                    self._status.width = width
                    self._status.height = height
        except Exception as exc:  # noqa: BLE001
            logger.exception("Recorder writer failed: %s", exc)
            with self._lock:
                self._status.error = str(exc)
        finally:
            if writer is not None:
                try:
                    writer.release()
                except Exception:  # noqa: BLE001
                    logger.debug("VideoWriter release failed", exc_info=True)
            mux_error: str | None = None
            if use_ffmpeg and frames > 0:
                mux_error = self._mux_jpeg_sequence(frames_dir, path, fps)
            elif use_ffmpeg and frames == 0:
                mux_error = "no frames captured"
            self._cleanup_frames_dir(frames_dir)
            with self._lock:
                self._status.recording = False
                self._status.finished = True
                self._status.frames_written = frames
                self._status.duration_seconds = max(0.0, time.time() - started)
                if width and not self._status.width:
                    self._status.width = width
                if height and not self._status.height:
                    self._status.height = height
                if mux_error and not self._status.error:
                    self._status.error = mux_error
            logger.info(
                "Recording finished path=%s frames=%s dropped=%s skipped=%s error=%s",
                path,
                frames,
                self._status.frames_dropped,
                self._status.frames_skipped,
                self._status.error,
            )

    @staticmethod
    def _mux_jpeg_sequence(frames_dir: Path, path: Path, fps: float) -> str | None:
        pattern = str(frames_dir / "%06d.jpg")
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            pattern,
            "-c:v",
            "copy",
            str(path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception as exc:  # noqa: BLE001
            return f"ffmpeg mux failed: {exc}"
        if proc.returncode != 0 or not path.is_file():
            detail = (proc.stderr or proc.stdout or "").strip()
            return f"ffmpeg mux failed rc={proc.returncode}: {detail[:300]}"
        return None

    @staticmethod
    def _cleanup_frames_dir(frames_dir: Path) -> None:
        if not frames_dir.exists():
            return
        try:
            for child in frames_dir.iterdir():
                try:
                    child.unlink()
                except OSError:
                    pass
            frames_dir.rmdir()
        except OSError:
            logger.debug("Could not remove frames dir %s", frames_dir, exc_info=True)
