"""HTTP API: health, metrics, sessions, laps, phone UI."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ac_telemetry import metrics
from ac_telemetry.capture import CaptureService
from ac_telemetry.detect import DetectService
from ac_telemetry.settings import Settings
from ac_telemetry.store import LapStore, SessionConflict, SessionNotFound, SessionStore
from ac_telemetry.web import STATUS_HTML


class SessionCreate(BaseModel):
    track: str = Field(default="", max_length=120)
    car: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=2000)


def create_app(
    settings: Settings,
    capture: CaptureService,
    store: SessionStore,
    *,
    lap_store: LapStore | None = None,
    detect: DetectService | None = None,
) -> FastAPI:
    app = FastAPI(
        title="AC Telemetry",
        version="0.3.0",
        description="Live HDMI capture with session metadata and lap-time logging.",
    )
    app.state.settings = settings
    app.state.capture = capture
    app.state.store = store
    app.state.lap_store = lap_store
    app.state.detect = detect

    def _lap_payload() -> dict[str, Any] | None:
        if detect is None:
            return None
        return detect.state.as_dict()

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
        current = store.current_session()
        return {
            "status": "ok" if healthy or not stats.running else "degraded",
            "capture": stats.as_dict(),
            "session": current,
            "lap": _lap_payload(),
            "profile": settings.profile,
            "backend": settings.backend,
        }

    @app.get("/metrics")
    def prometheus_metrics() -> Response:
        metrics.sync_from_stats(capture.stats)
        metrics.SESSIONS_OPEN.set(1 if store.current_session() else 0)
        if detect is not None and detect.state.displayed_time_ms is not None:
            metrics.SIGNAL_LAP_TIME_MS.set(detect.state.displayed_time_ms)
        body, content_type = metrics.render_metrics()
        return Response(content=body, media_type=content_type)

    @app.get("/api/status")
    def api_status() -> dict:
        metrics.sync_from_stats(capture.stats)
        payload = capture.stats.as_dict()
        current = store.current_session()
        payload["session"] = current
        payload["session_id"] = current["session_id"] if current else None
        payload["lap"] = _lap_payload()
        return payload

    @app.get("/api/laps/current")
    def api_laps_current() -> dict[str, Any]:
        current = store.current_session()
        return {
            "session_id": current["session_id"] if current else None,
            "lap": _lap_payload(),
        }

    @app.get("/api/laps")
    def api_laps(
        session_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        if lap_store is None:
            return {"laps": [], "current": _lap_payload()}
        sid = session_id
        if sid is None:
            cur = store.current_session()
            sid = cur["session_id"] if cur else None
        return {
            "laps": lap_store.list_laps(session_id=sid, limit=limit),
            "current": _lap_payload(),
            "session_id": sid,
        }

    @app.get("/api/sessions")
    def api_sessions(
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        return {
            "sessions": store.list_sessions(limit=limit),
            "current": store.current_session(),
        }

    @app.get("/api/sessions/current")
    def api_session_current() -> dict[str, Any]:
        current = store.current_session()
        return {"session": current}

    @app.get("/api/sessions/{session_id}")
    def api_session_get(session_id: str) -> dict[str, Any]:
        row = store.get_session(session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session": row}

    @app.post("/api/sessions", status_code=201)
    def api_session_create(body: SessionCreate) -> dict[str, Any]:
        try:
            row = store.start_session(
                track=body.track,
                car=body.car,
                notes=body.notes,
                stats=capture.stats,
            )
        except SessionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if detect is not None:
            detect.reset_for_session()
        metrics.SESSIONS_STARTED.inc()
        metrics.SESSIONS_OPEN.set(1)
        return {"session": row}

    # Static path before {session_id} so "current" is not treated as an id.
    @app.post("/api/sessions/current/end")
    def api_session_end_current() -> dict[str, Any]:
        try:
            row = store.end_current(stats=capture.stats)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        metrics.SESSIONS_ENDED.inc()
        metrics.SESSIONS_OPEN.set(0)
        return {"session": row}

    @app.post("/api/sessions/{session_id}/end")
    def api_session_end(session_id: str) -> dict[str, Any]:
        try:
            row = store.end_session(session_id, stats=capture.stats)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SessionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        metrics.SESSIONS_ENDED.inc()
        metrics.SESSIONS_OPEN.set(0)
        return {"session": row}

    return app
