"""Process entrypoint: wire settings, CSV store, capture, detect, HTTP server."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from typing import Any

import uvicorn

from ac_telemetry import metrics
from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.detect import DetectService
from ac_telemetry.settings import get_settings, load_settings
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


def build(settings=None):
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

    app = create_app(settings, capture, store, lap_store=lap_store, detect=detect)
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
        from ac_telemetry.settings import normalize_backend

        settings.backend = normalize_backend(args.backend)
    if args.file_path:
        settings.file_path = args.file_path
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port

    settings, capture, detect, app = build(settings)

    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    def _handle_signal(signum: int, _frame: Any) -> None:
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = str(signum)
        if _shutdown.is_set():
            # Second Ctrl-C: do not wait on joins again.
            logger.warning("Second %s — forcing exit", name)
            raise SystemExit(1)
        logger.info("Shutting down… (%s)", name)
        _shutdown.set()
        server.should_exit = True
        _stop_workers(detect, capture)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if _shutdown.is_set():
        logger.info("Shutdown requested during startup; not binding HTTP")
        _stop_workers(detect, capture)
        return

    if not args.no_capture:
        capture.start()
    detect.start()

    if _shutdown.is_set():
        logger.info("Shutdown requested before listen; exiting")
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
