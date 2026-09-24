"""HTTP API: health, Prometheus metrics, status UI (Slice 0)."""

from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse

from ac_telemetry import metrics
from ac_telemetry.capture import CaptureService
from ac_telemetry.settings import Settings
from ac_telemetry.store import SessionStore
from ac_telemetry.web import STATUS_HTML


def create_app(
    settings: Settings,
    capture: CaptureService,
    store: SessionStore,
) -> FastAPI:
    app = FastAPI(
        title="AC Telemetry",
        version="0.1.0",
        description="Slice 0: capture proof + health/metrics (no OCR yet).",
    )
    app.state.settings = settings
    app.state.capture = capture
    app.state.store = store

    @app.get("/", response_class=HTMLResponse)
    def status_page() -> str:
        return STATUS_HTML

    @app.get("/health")
    def health() -> dict:
        stats = capture.stats
        metrics.sync_from_stats(stats)
        healthy = stats.running and (
            stats.last_frame_age_seconds() is None
            or stats.last_frame_age_seconds() < 5.0
        )
        # Startup window: running but no frame yet is still OK briefly.
        if stats.running and stats.frames == 0:
            healthy = True
        return {
            "status": "ok" if healthy or not stats.running else "degraded",
            "capture": stats.as_dict(),
            "profile": settings.profile,
            "backend": settings.backend,
        }

    @app.get("/metrics")
    def prometheus_metrics() -> Response:
        metrics.sync_from_stats(capture.stats)
        body, content_type = metrics.render_metrics()
        return Response(content=body, media_type=content_type)

    @app.get("/api/status")
    def api_status() -> dict:
        metrics.sync_from_stats(capture.stats)
        return capture.stats.as_dict()

    @app.get("/api/sessions")
    def api_sessions() -> dict:
        return {"sessions": store.recent_sessions(10)}

    return app
