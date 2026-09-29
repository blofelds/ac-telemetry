"""HTTP API: health, metrics, sessions, laps, phone UI, ROI debug."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ac_telemetry import metrics
from ac_telemetry.capture import CaptureService
from ac_telemetry import debug_frames
from ac_telemetry import glyph_save
from ac_telemetry.detect import DetectService
from ac_telemetry.settings import Settings
from ac_telemetry.store import LapStore, SessionConflict, SessionNotFound, SessionStore
from ac_telemetry.web import DEBUG_HTML, STATUS_HTML


class SessionCreate(BaseModel):
    track: str = Field(default="", max_length=120)
    car: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=2000)


class GlyphSaveRequest(BaseModel):
    """Save the current lap_time ROI (or a sub-rect) as a template PNG."""

    symbol: str | None = Field(
        default=None,
        max_length=16,
        description="0-9, ':'/colon, '.'/period; omit to write pending/<timestamp>.png",
    )
    roi_name: str = Field(default="lap_time", max_length=64)
    # Optional sub-rectangle in ROI-local pixels (from /debug drag selection).
    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)


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

    @app.get("/debug", response_class=HTMLResponse)
    def debug_page() -> str:
        """ROI calibration page: overlay + crop + last_error."""
        return DEBUG_HTML

    def _jpeg_or_error(
        payload: bytes | None,
        *,
        missing: str,
        filename: str | None = None,
    ) -> Response:
        if payload is None:
            raise HTTPException(status_code=503, detail=missing)
        headers: dict[str, str] = {"Cache-Control": "no-store"}
        if filename:
            # Attachment so browsers save the full-resolution JPEG instead of
            # showing a CSS-scaled preview (needed for measuring ROI pixels).
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return Response(
            content=payload,
            media_type="image/jpeg",
            headers=headers,
        )

    @app.get("/api/debug/info")
    def api_debug_info() -> dict[str, Any]:
        """ROI coords + detect/capture errors for the debug page."""
        roi = settings.rois.get("lap_time")
        lap = _lap_payload() or {}
        stats = capture.stats.as_dict()
        return {
            "roi": None
            if roi is None
            else {
                "name": "lap_time",
                "x": roi.x,
                "y": roi.y,
                "width": roi.width,
                "height": roi.height,
            },
            "frame": {
                "width": stats.get("width"),
                "height": stats.get("height"),
                "age_seconds": stats.get("last_frame_age_seconds"),
                "available": capture.get_latest_frame() is not None,
            },
            "capture_last_error": stats.get("last_error"),
            "detect_last_error": lap.get("last_error"),
            "lap": lap,
            "session_id": (store.current_session() or {}).get("session_id"),
            "glyphs_dir": str(settings.glyphs_dir),
        }

    @app.get("/api/debug/frame.jpg")
    def api_debug_frame() -> Response:
        """Full latest capture frame as JPEG (from handoff copy; no ffmpeg)."""
        try:
            frame = capture.get_latest_frame_copy()
            payload = debug_frames.encode_full_frame_jpeg(frame)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return _jpeg_or_error(
            payload,
            missing="No frame yet (is capture running? mock has no pixels)",
        )

    @app.get("/api/debug/roi/{name}.jpg")
    def api_debug_roi(name: str) -> Response:
        """Crop of a named ROI from the latest frame."""
        roi = settings.rois.get(name)
        if roi is None:
            raise HTTPException(
                status_code=404,
                detail=f"ROI {name!r} not configured in settings.rois",
            )
        try:
            frame = capture.get_latest_frame_copy()
            payload = debug_frames.encode_roi_jpeg(frame, roi)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return _jpeg_or_error(
            payload,
            missing=f"No frame or empty crop for ROI {name!r}",
        )

    @app.get("/api/debug/overlay/{name}.jpg")
    def api_debug_overlay(name: str) -> Response:
        """Full frame with the named ROI rectangle drawn."""
        roi = settings.rois.get(name)
        if roi is None and name != "lap_time":
            raise HTTPException(
                status_code=404,
                detail=f"ROI {name!r} not configured in settings.rois",
            )
        try:
            frame = capture.get_latest_frame_copy()
            payload = debug_frames.encode_overlay_jpeg(frame, roi, name=name)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return _jpeg_or_error(
            payload,
            missing="No frame yet (is capture running? mock has no pixels)",
        )

    @app.get("/api/debug/rois.jpg")
    def api_debug_rois_download() -> Response:
        """Full-resolution JPEG with every configured ROI overlaid (download).

        Pi 2B-friendly: encodes a copy of the latest capture handoff via
        ``cv2.imencode`` (no ffmpeg). ``Content-Disposition: attachment`` so
        phones/desktops save the capture-resolution file for measuring ROIs.
        """
        try:
            frame = capture.get_latest_frame_copy()
            payload = debug_frames.encode_rois_overlay_jpeg(frame, settings.rois)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return _jpeg_or_error(
            payload,
            missing="No frame yet (is capture running? mock has no pixels)",
            filename="ac-telemetry-rois.jpg",
        )

    @app.post("/api/debug/glyphs/save")
    def api_debug_glyphs_save(body: GlyphSaveRequest) -> dict[str, Any]:
        """Write the current ROI crop (optional sub-rect) as a template PNG.

        Used from ``/debug`` to cut real Assetto Corsa digit/colon/period
        glyphs after the bundled set was found to be ACC (wrong game).
        """
        roi = settings.rois.get(body.roi_name)
        if roi is None:
            raise HTTPException(
                status_code=404,
                detail=f"ROI {body.roi_name!r} not configured in settings.rois",
            )
        try:
            frame = capture.get_latest_frame_copy()
            result = glyph_save.save_glyph_png(
                frame,
                roi,
                settings.glyphs_dir,
                symbol=body.symbol,
                sub_x=body.x,
                sub_y=body.y,
                sub_width=body.width,
                sub_height=body.height,
            )
        except ValueError as exc:
            # No frame / empty crop / bad symbol / bad sub-rect.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "ok": True,
            "glyphs_dir": str(settings.glyphs_dir),
            **result,
        }

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
