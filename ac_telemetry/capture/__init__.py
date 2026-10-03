"""Frame capture backends: mock, V4L2/OpenCV, and file/video path."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from ac_telemetry.record import FrameRecorder
from ac_telemetry.settings import CaptureProfile, Settings, normalize_backend

logger = logging.getLogger(__name__)


@dataclass
class CaptureStats:
    """Live capture counters shared with HTTP/metrics."""

    running: bool = False
    backend: str = "mock"
    device: str = ""
    profile: str = "pi2b"
    width: int = 0
    height: int = 0
    target_fps: float = 0.0
    measured_fps: float = 0.0
    frames: int = 0
    errors: int = 0
    last_error: str = ""
    last_frame_at: float | None = None
    started_at: float | None = None
    session_id: str | None = None

    def last_frame_age_seconds(self) -> float | None:
        if self.last_frame_at is None:
            return None
        return max(0.0, time.time() - self.last_frame_at)

    def as_dict(self) -> dict:
        age = self.last_frame_age_seconds()
        return {
            "running": self.running,
            "backend": self.backend,
            "device": self.device,
            "profile": self.profile,
            "width": self.width,
            "height": self.height,
            "target_fps": self.target_fps,
            "measured_fps": round(self.measured_fps, 2),
            "frames": self.frames,
            "errors": self.errors,
            "last_error": self.last_error or None,
            "last_frame_age_seconds": None if age is None else round(age, 3),
            "session_id": self.session_id,
        }


class FrameSource(Protocol):
    def open(self) -> tuple[int, int]:
        """Open device; return actual (width, height)."""

    def read(self) -> tuple[bool, object | None]:
        """Grab one frame. Return (ok, frame_or_None)."""

    def close(self) -> None:
        ...


class MockFrameSource:
    """Synthetic frames at the profile FPS — no camera required.

    Returns ``(True, None)`` so detection can use the mock lap-time reader
    without pulling in OpenCV/numpy on a laptop or a lean Pi venv.
    """

    def __init__(self, profile: CaptureProfile) -> None:
        self._profile = profile
        self._opened = False

    def open(self) -> tuple[int, int]:
        self._opened = True
        return self._profile.width, self._profile.height

    def read(self) -> tuple[bool, object | None]:
        if not self._opened:
            return False, None
        # Cheap stand-in for a frame; sleep is owned by the capture loop.
        return True, None

    def close(self) -> None:
        self._opened = False


def _cv2_import_failure(exc: ImportError, *, backend: str = "v4l2") -> RuntimeError:
    """Map a cv2 ImportError to a RuntimeError that keeps the real cause visible.

    On Raspberry Pi OS, pip numpy/opencv often fail with missing libopenblas.so.0.
    That is still an ImportError, so wrapping every failure as "install .[capture]"
    hides the apt fix. Only suggest the capture extra when the cv2 module itself
    is absent.
    """
    detail = str(exc)
    detail_l = detail.lower()
    missing_cv2 = isinstance(exc, ModuleNotFoundError) and (
        getattr(exc, "name", None) == "cv2"
        or "no module named 'cv2'" in detail_l
        or 'no module named "cv2"' in detail_l
    )
    if missing_cv2:
        return RuntimeError(
            f"OpenCV (cv2) is required for the {backend} backend. On Raspberry Pi 2B "
            "prefer: sudo apt install python3-opencv && python3 -m venv "
            "--system-site-packages .venv — do not pip install '.[capture]' "
            "(wheels often SIGILL on the 2B). On x86: pip install -e '.[capture]'. "
            f"Original error: {detail}"
        )
    if "openblas" in detail_l or "libopenblas" in detail_l:
        return RuntimeError(
            "OpenCV/numpy failed to import because OpenBLAS is missing "
            f"({detail}). On Raspberry Pi OS / Debian: "
            "sudo apt install libopenblas0 "
            "(alternatives: libopenblas0-pthread, libopenblas-dev). "
            "apt python3-opencv is optional if pip opencv is already installed."
        )
    if "numpy" in detail_l:
        return RuntimeError(
            "OpenCV failed to import due to a numpy load error "
            f"({detail}). On Raspberry Pi OS, pip numpy/opencv often need "
            "system OpenBLAS: sudo apt install libopenblas0. "
            "Re-check with: python -c 'import numpy; import cv2'."
        )
    return RuntimeError(
        f"OpenCV failed to import for the {backend} backend: {detail}"
    )


def _v4l2_cv2_import_failure(exc: ImportError) -> RuntimeError:
    """Backward-compatible wrapper used by v4l2 import-error tests."""
    return _cv2_import_failure(exc, backend="v4l2")


class V4L2FrameSource:
    """OpenCV VideoCapture on a V4L2 UVC device."""

    def __init__(
        self,
        device: str,
        profile: CaptureProfile,
        *,
        prefer_mjpeg: bool = True,
    ) -> None:
        self._device = device
        self._profile = profile
        self._prefer_mjpeg = prefer_mjpeg
        self._cap = None

    def open(self) -> tuple[int, int]:
        try:
            import cv2  # lazy: optional until hardware path is used
        except ImportError as exc:
            raise _v4l2_cv2_import_failure(exc) from exc

        # Prefer device path; fall back to numeric index if given as digit.
        src: str | int = int(self._device) if self._device.isdigit() else self._device
        cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
        if not cap.isOpened():
            # Some stacks ignore CAP_V4L2; retry default backend.
            cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open capture device: {self._device}")

        if self._prefer_mjpeg:
            # MJPEG usually beats uncompressed YUYV on USB 2.0 / Pi 2B.
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            if not cap.set(cv2.CAP_PROP_FOURCC, fourcc):
                logger.warning("Device rejected MJPEG FourCC; continuing with default")

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._profile.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._profile.height)
        cap.set(cv2.CAP_PROP_FPS, self._profile.fps)

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or self._profile.width)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or self._profile.height)
        # Soft-enforce caps: if the driver overshoots, still report requested
        # profile — decoding at 1080p on a 2B is a thermal trap.
        if width > self._profile.max_width or height > self._profile.max_height:
            logger.warning(
                "Device opened at %sx%s which exceeds profile caps %sx%s; "
                "continuing but expect CPU pressure",
                width,
                height,
                self._profile.max_width,
                self._profile.max_height,
            )
        self._cap = cap
        return width, height

    def read(self) -> tuple[bool, object | None]:
        if self._cap is None:
            return False, None
        ok, frame = self._cap.read()
        if not ok:
            return False, None
        return True, frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class FileFrameSource:
    """OpenCV ``VideoCapture`` on a video file, image, or image-sequence path.

    Sandbox / HITL use: feed recorded clips without opening ``/dev/video0``.
    ``loop=True`` rewinds (or re-opens) at EOF so the server can run indefinitely.
    """

    def __init__(
        self,
        path: str,
        profile: CaptureProfile,
        *,
        loop: bool = True,
    ) -> None:
        self._path = path
        self._profile = profile
        self._loop = loop
        self._cap = None
        self._cv2 = None

    def _resolved_path(self) -> str:
        raw = (self._path or "").strip()
        if not raw:
            raise RuntimeError(
                "file backend requires file_path (YAML file_path / "
                "capture.file_path, or AC_TELEMETRY_FILE_PATH)"
            )
        # printf image sequences keep "%" literals; expanduser only.
        expanded = str(Path(raw).expanduser())
        if "%" not in expanded and not Path(expanded).exists():
            raise RuntimeError(f"Capture file not found: {expanded}")
        return expanded

    def _open_capture(self, path: str):
        assert self._cv2 is not None
        cap = self._cv2.VideoCapture(path)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open capture file: {path}")
        return cap

    def open(self) -> tuple[int, int]:
        try:
            import cv2  # lazy: optional until file path is used
        except ImportError as exc:
            raise _cv2_import_failure(exc, backend="file") from exc

        self._cv2 = cv2
        path = self._resolved_path()
        cap = self._open_capture(path)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or self._profile.width)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or self._profile.height)
        if width <= 0:
            width = self._profile.width
        if height <= 0:
            height = self._profile.height
        self._cap = cap
        return width, height

    def read(self) -> tuple[bool, object | None]:
        if self._cap is None or self._cv2 is None:
            return False, None
        ok, frame = self._cap.read()
        if ok:
            return True, frame
        if not self._loop:
            return False, None
        # Seek first (cheap for most containers); re-open if seek fails
        # (common for single-image / some image-sequence backends).
        if self._cap.set(self._cv2.CAP_PROP_POS_FRAMES, 0):
            ok, frame = self._cap.read()
            if ok:
                return True, frame
        try:
            self._cap.release()
        except Exception:  # noqa: BLE001
            logger.debug("Error releasing capture before loop re-open", exc_info=True)
        path = self._resolved_path()
        self._cap = self._open_capture(path)
        ok, frame = self._cap.read()
        if not ok:
            return False, None
        return True, frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


def build_source(settings: Settings, profile: CaptureProfile) -> FrameSource:
    backend = normalize_backend(settings.backend)
    if backend == "mock":
        return MockFrameSource(profile)
    if backend == "v4l2":
        return V4L2FrameSource(
            settings.device,
            profile,
            prefer_mjpeg=settings.prefer_mjpeg,
        )
    if backend == "file":
        return FileFrameSource(
            settings.file_path,
            profile,
            loop=settings.loop,
        )
    raise ValueError(f"Unknown capture backend: {settings.backend!r}")


@dataclass
class CaptureService:
    """Background frame loop owned by the process."""

    settings: Settings
    stats: CaptureStats = field(default_factory=CaptureStats)
    recorder: FrameRecorder | None = field(default=None, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _on_start: Callable[[CaptureStats], str] | None = field(
        default=None, init=False, repr=False
    )
    _on_stop: Callable[[str, CaptureStats], None] | None = field(
        default=None, init=False, repr=False
    )
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _frame_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _latest_frame: object | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        profile = None
        try:
            profile = self.settings.active_profile()
        except Exception:  # noqa: BLE001 — settings may be incomplete in unit tests
            profile = None
        fps = float(profile.fps) if profile is not None else 10.0
        # Write slower than capture on Pi 2B — full-frame MJPEG is expensive.
        write_fps = min(5.0, max(1.0, fps))
        self.recorder = FrameRecorder(
            output_dir=self.settings.record_dir,
            default_seconds=self.settings.record_default_seconds,
            max_seconds=self.settings.record_max_seconds,
            fps=write_fps,
        )

    def set_session_hooks(self, on_start, on_stop) -> None:
        """CSV (or later store) callbacks for session start/stop."""
        self._on_start = on_start
        self._on_stop = on_stop

    def get_latest_frame(self) -> object | None:
        """Return the most recent frame reference (detect must crop/copy fast)."""
        with self._frame_lock:
            return self._latest_frame

    def get_latest_frame_copy(self) -> object | None:
        """Copy the latest frame under the lock, then release (for debug JPEG).

        Prefer this over holding a shared reference across ``cv2.imencode`` —
        encode work must happen *outside* the capture critical path.
        """
        with self._frame_lock:
            frame = self._latest_frame
            if frame is None:
                return None
            try:
                return frame.copy()
            except AttributeError:
                return None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="capture-loop", daemon=True
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        if self.recorder is not None:
            try:
                self.recorder.stop()
            except Exception:  # noqa: BLE001
                logger.debug("Recorder stop during capture shutdown failed", exc_info=True)

    def _run(self) -> None:
        profile = self.settings.active_profile()
        backend = normalize_backend(self.settings.backend)
        source = build_source(self.settings, profile)
        self.stats.backend = backend
        if backend == "mock":
            self.stats.device = "mock"
        elif backend == "file":
            self.stats.device = self.settings.file_path or "file"
        else:
            self.stats.device = self.settings.device
        self.stats.profile = profile.name
        self.stats.target_fps = profile.fps
        self.stats.width = profile.width
        self.stats.height = profile.height
        self.stats.errors = 0
        self.stats.last_error = ""
        self.stats.frames = 0
        self.stats.measured_fps = 0.0
        self.stats.last_frame_at = None

        session_id: str | None = None
        try:
            width, height = source.open()
            self.stats.width = width
            self.stats.height = height
            self.stats.running = True
            self.stats.started_at = time.time()
            if self._on_start is not None:
                session_id = self._on_start(self.stats)
                self.stats.session_id = session_id
            logger.info(
                "Capture started backend=%s profile=%s %sx%s @ %.1f fps",
                backend,
                profile.name,
                width,
                height,
                profile.fps,
            )
            self._loop(source, profile.fps)
        except Exception as exc:  # noqa: BLE001 — surface to metrics/UI
            self.stats.errors += 1
            self.stats.last_error = str(exc)
            logger.exception("Capture failed to start: %s", exc)
        finally:
            try:
                source.close()
            except Exception:  # noqa: BLE001
                logger.exception("Error closing capture source")
            self.stats.running = False
            if self._on_stop is not None and session_id is not None:
                try:
                    self._on_stop(session_id, self.stats)
                except Exception:  # noqa: BLE001
                    logger.exception("Session stop hook failed")
            self.stats.session_id = None
            logger.info("Capture stopped")

    def _loop(self, source: FrameSource, target_fps: float) -> None:
        interval = 1.0 / max(target_fps, 0.1)
        window_start = time.monotonic()
        window_frames = 0
        while not self._stop.is_set():
            tick = time.monotonic()
            ok = False
            frame = None
            try:
                ok, frame = source.read()
            except Exception as exc:  # noqa: BLE001
                self.stats.errors += 1
                self.stats.last_error = str(exc)
                logger.warning("Frame read error: %s", exc)
                time.sleep(min(1.0, interval))
                continue

            if not ok:
                self.stats.errors += 1
                self.stats.last_error = "frame read returned False"
                time.sleep(min(1.0, interval))
                continue

            # Publish latest frame for detect (replace; never queue — drop old).
            with self._frame_lock:
                self._latest_frame = frame

            # Optional card-native tee (same pixels detect sees; no second video0).
            if self.recorder is not None:
                self.recorder.offer_frame(frame)

            now = time.time()
            self.stats.frames += 1
            self.stats.last_frame_at = now
            window_frames += 1
            elapsed = time.monotonic() - window_start
            if elapsed >= 1.0:
                self.stats.measured_fps = window_frames / elapsed
                window_start = time.monotonic()
                window_frames = 0

            # Pace to target FPS so mock and V4L2 share the same CPU budget shape.
            sleep_for = interval - (time.monotonic() - tick)
            if sleep_for > 0:
                # Wait in small slices so stop() is responsive on a slow Pi.
                deadline = time.monotonic() + sleep_for
                while not self._stop.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(0.05, remaining))
