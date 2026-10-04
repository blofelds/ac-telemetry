"""Process entrypoint: wire settings, CSV store, capture, detect, HTTP server."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from typing import Any, BinaryIO

import uvicorn

from ac_telemetry import metrics
from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.detect import DetectService
from ac_telemetry.settings import get_settings, load_settings, normalize_backend
from ac_telemetry.store import LapStore, SessionStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("ac_telemetry")

# Process-wide shutdown: SIGINT during slow startup must abort before uvicorn
# binds, and after bind must set Server.should_exit (custom handlers replace
# uvicorn's default KeyboardInterrupt path).
_shutdown = threading.Event()

# After first SIGINT/SIGTERM, a *subprocess* watchdog SIGKILLs this process if
# graceful shutdown stalls. A same-process Python thread is not enough on the
# Pi: OpenCV can hold the GIL through the whole countdown.
DEFAULT_SHUTDOWN_WATCHDOG_SECONDS = 8.0
_watchdog_stdin: BinaryIO | None = None


def build(
    settings=None,
    *,
    on_startup=None,
    on_shutdown=None,
):
    settings = settings or get_settings()
    store = SessionStore(settings.data_dir)
    store.ensure()
    lap_store = LapStore(settings.data_dir)
    lap_store.ensure()
    capture = CaptureService(settings=settings)

    detect = DetectService(
        settings=settings,
        get_frame=capture.get_latest_frame,
        get_session_id=lambda: (
            (store.current_session() or {}).get("session_id")
        ),
        record_lap=lap_store.append_lap,
        on_metrics=metrics.observe_detect,
        get_capture_info=lambda: capture.stats.as_dict(),
    )

    app = create_app(
        settings,
        capture,
        store,
        lap_store=lap_store,
        detect=detect,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
    )
    return settings, capture, detect, app


def _stop_workers(detect: DetectService, capture: CaptureService) -> None:
    """Bounded joins so SIGINT never blocks for minutes on VideoCapture/ffmpeg."""
    try:
        detect.stop(timeout=2.0)
    except Exception:  # noqa: BLE001
        logger.debug("detect.stop during shutdown failed", exc_info=True)
    try:
        capture.stop(timeout=2.0, recorder_join_timeout=3.0)
    except Exception:  # noqa: BLE001
        logger.debug("capture.stop during shutdown failed", exc_info=True)


def needs_opencv(settings: Any) -> bool:
    """True when capture or detect will import OpenCV during worker start."""
    backend = normalize_backend(getattr(settings, "backend", "mock"))
    if backend in ("file", "v4l2"):
        return True
    detect = getattr(settings, "detect", None)
    if detect is None or not getattr(detect, "enabled", False):
        return False
    lap = getattr(detect, "lap_time", None)
    reader = getattr(lap, "reader", "mock") if lap is not None else "mock"
    return reader in ("template", "tesseract", "assetto_corsa")


def preload_opencv_if_needed(settings: Any) -> float:
    """Import cv2 on the main thread before binding HTTP.

    On a low-RAM Pi, lazy ``import cv2`` inside the capture/detect worker after
    bind can hold/starve the GIL for minutes (zram thrash). The OS port may
    show LISTEN while ``/api/status`` and SIGINT cannot run. Paying the import
    cost before ``server.run()`` keeps post-listen HTTP and Ctrl-C responsive;
    ``VideoCapture.open`` stays deferred until after bind (still time-bounded).
    """
    if not needs_opencv(settings):
        return 0.0
    if _shutdown.is_set():
        return 0.0
    logger.info(
        "Preloading OpenCV (backend=%s detect=%s)…",
        normalize_backend(settings.backend),
        settings.detect.lap_time.reader if settings.detect.enabled else "off",
    )
    t0 = time.monotonic()
    try:
        import cv2  # noqa: F401
    except ImportError as exc:
        # Worker start will surface the same failure with a richer message.
        logger.warning("OpenCV preload failed: %s", exc)
        return time.monotonic() - t0
    elapsed = time.monotonic() - t0
    logger.info("OpenCV preload finished in %.1fs", elapsed)
    return elapsed


def trip_shutdown_watchdog() -> None:
    """Wake the subprocess watchdog (safe-ish from a SIGINT handler)."""
    global _watchdog_stdin
    stdin = _watchdog_stdin
    _watchdog_stdin = None
    if stdin is None:
        return
    try:
        fd = stdin.fileno()
    except Exception:  # noqa: BLE001
        return
    try:
        os.write(fd, b"x")
    except OSError:
        pass
    try:
        stdin.close()
    except OSError:
        pass


def start_shutdown_watchdog(
    seconds: float = DEFAULT_SHUTDOWN_WATCHDOG_SECONDS,
) -> None:
    """Start an out-of-process SIGKILL watchdog for stalled shutdown.

    The child does not share this interpreter's GIL, so it can still fire while
    OpenCV is stuck in a native call. ``trip_shutdown_watchdog()`` (from the
    SIGINT handler) writes one byte to start the countdown; EOF without a byte
    means the parent exited cleanly and the child exits without killing.
    """
    global _watchdog_stdin
    budget = max(1.0, float(seconds))
    parent = os.getpid()
    # Tiny inline script keeps deploy surface small (no helper module).
    child = (
        "import os,sys,time,signal\n"
        "parent=int(sys.argv[1]); delay=float(sys.argv[2])\n"
        "data=sys.stdin.read(1)\n"
        "if not data:\n"
        "    raise SystemExit(0)\n"
        "time.sleep(delay)\n"
        "try:\n"
        "    os.kill(parent, signal.SIGKILL)\n"
        "except ProcessLookupError:\n"
        "    pass\n"
    )
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", child, str(parent), f"{budget:.3f}"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError as exc:
        logger.warning("Shutdown watchdog not started: %s", exc)
        return
    _watchdog_stdin = proc.stdin
    # Backup trip path if the signal handler could not write (still needs GIL).
    threading.Thread(
        target=lambda: (_shutdown.wait(), trip_shutdown_watchdog()),
        name="shutdown-watchdog-trip",
        daemon=True,
    ).start()


def main(argv: list[str] | None = None) -> None:
    _shutdown.clear()
    parser = argparse.ArgumentParser(description="AC Telemetry service")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config (default: config/default.yaml)",
    )
    parser.add_argument(
        "--backend",
        choices=("mock", "v4l2", "file", "video"),
        default=None,
        help="Override capture backend (video is an alias for file)",
    )
    parser.add_argument(
        "--file-path",
        default=None,
        help="Video/image path for file|video backend",
    )
    parser.add_argument("--host", default=None, help="Bind host (default from config)")
    parser.add_argument("--port", type=int, default=None, help="Bind port")
    parser.add_argument(
        "--no-capture",
        action="store_true",
        help="Start HTTP only (do not auto-start capture)",
    )
    args = parser.parse_args(argv)

    # Clear cached settings if a path override is used.
    from ac_telemetry import settings as settings_mod
    from pathlib import Path

    settings_mod.get_settings.cache_clear()
    settings = load_settings(Path(args.config) if args.config else None)
    if args.backend:
        settings.backend = normalize_backend(args.backend)
    if args.file_path:
        settings.file_path = args.file_path
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port

    # Late-bound so lifespan closures see the real instances.
    holders: dict[str, Any] = {"capture": None, "detect": None}

    # uvicorn runs lifespan startup *before* binding the listen socket. Start
    # capture only after bind so VideoCapture.open cannot delay the listen
    # socket. OpenCV itself is preloaded below (before run) so post-bind worker
    # start does not starve the GIL on low-RAM boards.
    server_holder: dict[str, uvicorn.Server | None] = {"server": None}

    def _on_startup() -> None:
        def _start_after_bind() -> None:
            deadline = time.monotonic() + 120.0
            while time.monotonic() < deadline and not _shutdown.is_set():
                srv = server_holder["server"]
                if srv is not None and srv.started:
                    break
                time.sleep(0.05)
            if _shutdown.is_set():
                return
            capture = holders["capture"]
            detect = holders["detect"]
            if capture is None or detect is None:
                return
            if not args.no_capture:
                capture.start()
            detect.start()

        threading.Thread(
            target=_start_after_bind, name="worker-start", daemon=True
        ).start()

    def _on_shutdown() -> None:
        capture = holders["capture"]
        detect = holders["detect"]
        if capture is None or detect is None:
            return
        _stop_workers(detect, capture)

    settings, capture, detect, app = build(
        settings,
        on_startup=_on_startup,
        on_shutdown=_on_shutdown,
    )
    holders["capture"] = capture
    holders["detect"] = detect

    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    server_holder["server"] = server

    def _handle_signal(signum: int, _frame: Any) -> None:
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = str(signum)
        if _shutdown.is_set():
            # Second Ctrl-C: hard-exit (SystemExit can still stall under GIL).
            logger.warning("Second %s — forcing exit", name)
            os._exit(1)
        logger.info("Shutting down… (%s)", name)
        _shutdown.set()
        server.should_exit = True
        trip_shutdown_watchdog()
        # Never join from a signal handler: capture may be inside a long OpenCV
        # import/open holding the GIL; blocking joins freeze Ctrl-C for minutes.
        try:
            detect.request_stop()
            capture.request_stop()
        except Exception:  # noqa: BLE001
            logger.debug("request_stop from signal handler failed", exc_info=True)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    # Pre-start watchdog before preload/bind — it only counts down after
    # `_shutdown` is set by the signal handler.
    start_shutdown_watchdog(DEFAULT_SHUTDOWN_WATCHDOG_SECONDS)

    # Install handlers before preload so a stuck import still gets should_exit
    # queued once the main thread can run again.
    preload_opencv_if_needed(settings)

    if _shutdown.is_set():
        logger.info("Shutdown requested during startup; not binding HTTP")
        _stop_workers(detect, capture)
        return

    logger.info(
        "Listening on http://%s:%s (backend=%s profile=%s detect=%s)",
        settings.host,
        settings.port,
        settings.backend,
        settings.profile,
        settings.detect.lap_time.reader if settings.detect.enabled else "off",
    )
    try:
        server.run()
    finally:
        _shutdown.set()
        _stop_workers(detect, capture)


if __name__ == "__main__":
    main(sys.argv[1:])
