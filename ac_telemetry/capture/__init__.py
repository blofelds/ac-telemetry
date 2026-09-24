"""Frame capture backends: mock (dev) and V4L2/OpenCV (Pi hardware)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from ac_telemetry.settings import CaptureProfile, Settings

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

    def read(self) -> bool:
        """Grab one frame. Return False on failure."""

    def close(self) -> None:
        ...


class MockFrameSource:
    """Synthetic frames at the profile FPS — no camera required."""

    def __init__(self, profile: CaptureProfile) -> None:
        self._profile = profile
        self._opened = False

    def open(self) -> tuple[int, int]:
        self._opened = True
        return self._profile.width, self._profile.height

    def read(self) -> bool:
        if not self._opened:
            return False
        # Cheap stand-in for a frame; sleep is owned by the capture loop.
        return True

    def close(self) -> None:
        self._opened = False


class V4L2FrameSource:
    """OpenCV VideoCapture on a V4L2 UVC device."""

    def __init__(self, device: str, profile: CaptureProfile) -> None:
        self._device = device
        self._profile = profile
        self._cap = None

    def open(self) -> tuple[int, int]:
        try:
            import cv2  # lazy: optional until hardware path is used
        except ImportError as exc:
            raise RuntimeError(
                "opencv-python-headless is required for the v4l2 backend "
                "(pip install 'ac-telemetry[capture]')"
            ) from exc

        # Prefer device path; fall back to numeric index if given as digit.
        src: str | int = int(self._device) if self._device.isdigit() else self._device
        cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
        if not cap.isOpened():
            # Some stacks ignore CAP_V4L2; retry default backend.
            cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open capture device: {self._device}")

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

    def read(self) -> bool:
        if self._cap is None:
            return False
        ok, _frame = self._cap.read()
        return bool(ok)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


def build_source(settings: Settings, profile: CaptureProfile) -> FrameSource:
    if settings.backend == "mock":
        return MockFrameSource(profile)
    if settings.backend == "v4l2":
        return V4L2FrameSource(settings.device, profile)
    raise ValueError(f"Unknown capture backend: {settings.backend!r}")


@dataclass
class CaptureService:
    """Background frame loop owned by the process."""

    settings: Settings
    stats: CaptureStats = field(default_factory=CaptureStats)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _on_start: Callable[[CaptureStats], str] | None = field(
        default=None, init=False, repr=False
    )
    _on_stop: Callable[[str, CaptureStats], None] | None = field(
        default=None, init=False, repr=False
    )
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def set_session_hooks(self, on_start, on_stop) -> None:
        """CSV (or later store) callbacks for session start/stop."""
        self._on_start = on_start
        self._on_stop = on_stop

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

    def _run(self) -> None:
        profile = self.settings.active_profile()
        source = build_source(self.settings, profile)
        self.stats.backend = self.settings.backend
        self.stats.device = (
            "mock" if self.settings.backend == "mock" else self.settings.device
        )
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
                self.settings.backend,
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
            try:
                ok = source.read()
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
                while not self._stop.is_set() and time.monotonic() < deadline:
                    time.sleep(min(0.05, deadline - time.monotonic()))
