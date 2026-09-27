"""Process entrypoint: wire settings, CSV store, capture, detect, HTTP server."""

from __future__ import annotations

import argparse
import logging
import signal
import sys

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
    )

    app = create_app(settings, capture, store, lap_store=lap_store, detect=detect)
    return settings, capture, detect, app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AC Telemetry service")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config (default: config/default.yaml)",
    )
    parser.add_argument(
        "--backend",
        choices=("mock", "v4l2"),
        default=None,
        help="Override capture backend",
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
        settings.backend = args.backend
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port

    settings, capture, detect, app = build(settings)

    def _shutdown(*_args) -> None:
        logger.info("Shutting down…")
        detect.stop()
        capture.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if not args.no_capture:
        capture.start()
    detect.start()

    logger.info(
        "Listening on http://%s:%s (backend=%s profile=%s detect=%s)",
        settings.host,
        settings.port,
        settings.backend,
        settings.profile,
        settings.detect.lap_time.reader if settings.detect.enabled else "off",
    )
    try:
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    finally:
        detect.stop()
        capture.stop()


if __name__ == "__main__":
    main(sys.argv[1:])
