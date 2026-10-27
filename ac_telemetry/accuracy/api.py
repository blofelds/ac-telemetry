"""HTTP routes for accuracy GT + scores (mounted only when enabled)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from ac_telemetry.accuracy.helper import (
    GT_CONFIRMED_NOTE,
    build_helper_page_data,
    confirm_helper_gt,
    detect_gt_confirmed,
    list_gt_confirmed_status,
    resolve_roi_file,
)
from ac_telemetry.accuracy.score import (
    load_gt_list,
    prefills_from_csv,
    save_gt,
    score_session,
)
from ac_telemetry.accuracy.session import AccuracySession
from ac_telemetry.settings import Settings
from ac_telemetry.store import LapStore, SessionStore
from ac_telemetry.web.accuracy import ACCURACY_HELPER_HTML


class GtSubmitBody(BaseModel):
    """Confirmed GT lap list (or edits of the CSV prefill)."""

    laps: list[Any] = Field(
        ...,
        description="List of lap times: '1:07.717', ms ints, or {lap_time, note}.",
    )
    score: bool = Field(
        default=True,
        description="If true, compute write%/ocr-sample% immediately.",
    )


class GtConfirmBody(BaseModel):
    """Helper Confirm — GT draft + gt.json + stint CSV note/times."""

    laps: list[Any] = Field(
        ...,
        description="Edited lap times (same shapes as GT submit).",
    )
    score: bool = Field(
        default=True,
        description="If true, compute write%/ocr-sample% after confirm.",
    )
    note: str = Field(
        default=GT_CONFIRMED_NOTE,
        max_length=200,
        description="Note written onto every laps.csv row for this session.",
    )


def mount_accuracy_routes(
    app: FastAPI,
    *,
    settings: Settings,
    store: SessionStore,
    lap_store: LapStore | None,
    accuracy: AccuracySession,
) -> None:
    """Register /api/accuracy/* and /accuracy helper. Caller mounts when enabled."""

    def _sid_or_404(session_id: str) -> str:
        row = store.get_session(session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return session_id

    @app.get("/accuracy", response_class=HTMLResponse)
    def accuracy_helper_page() -> HTMLResponse:
        return HTMLResponse(ACCURACY_HELPER_HTML)

    @app.get("/accuracy/{session_id}", response_class=HTMLResponse)
    def accuracy_helper_page_session(session_id: str) -> HTMLResponse:
        # Page loads even if session_id is unknown; API calls 404 later.
        return HTMLResponse(ACCURACY_HELPER_HTML)

    @app.get("/api/accuracy/status")
    def api_accuracy_status() -> dict[str, Any]:
        return {"ok": True, **accuracy.status()}

    @app.post("/api/accuracy/start/{session_id}")
    def api_accuracy_start(session_id: str) -> dict[str, Any]:
        _sid_or_404(session_id)
        result = accuracy.start(session_id)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("reason"))
        return result

    @app.post("/api/accuracy/stop")
    def api_accuracy_stop() -> dict[str, Any]:
        return accuracy.stop()

    @app.get("/api/accuracy/sessions/{session_id}/gt/prefill")
    def api_accuracy_gt_prefill(session_id: str) -> dict[str, Any]:
        _sid_or_404(session_id)
        if lap_store is None:
            return {"session_id": session_id, "laps": []}
        laps = lap_store.list_laps(session_id=session_id, limit=500)
        return {
            "session_id": session_id,
            "laps": prefills_from_csv(laps),
            "note": "Confirm/edit then POST /api/accuracy/sessions/{id}/gt",
        }

    @app.get("/api/accuracy/sessions/gt-status")
    def api_accuracy_gt_status(session_id: str | None = None) -> dict[str, Any]:
        """Confirmed-GT flags for the helper session list (or one session).

        Query ``?session_id=`` for a single session; omit to scan recent
        sessions from the store (same limit as the helper picker).
        """
        if session_id:
            _sid_or_404(session_id)
            one = detect_gt_confirmed(
                data_dir=settings.data_dir,
                session_id=session_id,
                lap_store=lap_store,
                subdir=accuracy.settings.subdir,
            )
            return {"ok": True, "sessions": {session_id: one}}
        rows = store.list_sessions(limit=100)
        ids = [
            str(r.get("session_id") or r.get("id") or "").strip()
            for r in rows
        ]
        return {
            "ok": True,
            "sessions": list_gt_confirmed_status(
                data_dir=settings.data_dir,
                session_ids=ids,
                lap_store=lap_store,
                subdir=accuracy.settings.subdir,
            ),
        }

    @app.get("/api/accuracy/sessions/{session_id}/helper")
    def api_accuracy_helper(session_id: str) -> dict[str, Any]:
        """Page data: prefill laps + up to two tee crop URLs per hold."""
        _sid_or_404(session_id)
        return build_helper_page_data(
            data_dir=settings.data_dir,
            session_id=session_id,
            lap_store=lap_store,
            subdir=accuracy.settings.subdir,
        )

    @app.get("/api/accuracy/sessions/{session_id}/roi/{filename}")
    def api_accuracy_roi_file(session_id: str, filename: str) -> FileResponse:
        _sid_or_404(session_id)
        try:
            path = resolve_roi_file(
                data_dir=settings.data_dir,
                session_id=session_id,
                filename=filename,
                subdir=accuracy.settings.subdir,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="ROI crop not found")
        return FileResponse(path, media_type="image/jpeg")

    @app.post("/api/accuracy/sessions/{session_id}/gt/confirm")
    def api_accuracy_gt_confirm(
        session_id: str, body: GtConfirmBody
    ) -> dict[str, Any]:
        """Confirm helper edits: gt_draft.json + gt.json + laps.csv note/times."""
        _sid_or_404(session_id)
        try:
            return confirm_helper_gt(
                data_dir=settings.data_dir,
                session_id=session_id,
                raw_laps=body.laps,
                lap_store=lap_store,
                subdir=accuracy.settings.subdir,
                score=body.score,
                note=body.note or GT_CONFIRMED_NOTE,
            )
        except ValueError as exc:
            detail = str(exc)
            if "Lap store not configured" in detail:
                raise HTTPException(status_code=503, detail=detail) from exc
            raise HTTPException(status_code=400, detail=detail) from exc

    @app.post("/api/accuracy/sessions/{session_id}/gt")
    def api_accuracy_gt_submit(
        session_id: str, body: GtSubmitBody
    ) -> dict[str, Any]:
        _sid_or_404(session_id)
        try:
            gt_laps = load_gt_list(body.laps)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        subdir = accuracy.settings.subdir
        path = save_gt(
            data_dir=settings.data_dir,
            session_id=session_id,
            gt_laps=gt_laps,
            subdir=subdir,
        )
        payload: dict[str, Any] = {
            "ok": True,
            "session_id": session_id,
            "gt_path": str(path),
            "gt_laps": len(gt_laps),
        }
        if body.score:
            if lap_store is None:
                raise HTTPException(status_code=503, detail="Lap store not configured")
            report = score_session(
                data_dir=settings.data_dir,
                session_id=session_id,
                gt_laps=gt_laps,
                subdir=subdir,
                lap_store=lap_store,
            )
            payload["score"] = {
                "write_pct": report["write_pct"],
                "ocr_sample_pct": report["ocr_sample_pct"],
                "write_matches": report["write_matches"],
                "write_misses": report["write_misses"],
                "write_extras": report["write_extras"],
                "write_doubles": report.get("write_doubles", 0),
                "gt_skips": report.get("gt_skips", 0),
                "artefact_dir": report["artefact_dir"],
                "score_json": f"{report['artefact_dir']}/score.json",
                "score_md": f"{report['artefact_dir']}/score.md",
                "review_md": f"{report['artefact_dir']}/review.md",
            }
        return payload

    @app.get("/api/accuracy/sessions/{session_id}/score")
    def api_accuracy_score(session_id: str) -> dict[str, Any]:
        _sid_or_404(session_id)
        from ac_telemetry.accuracy.paths import gt_path, session_dir
        import json

        sdir = session_dir(
            settings.data_dir, session_id, subdir=accuracy.settings.subdir
        )
        path = gt_path(sdir)
        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail="No gt.json yet — POST /api/accuracy/sessions/{id}/gt",
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        try:
            gt_laps = load_gt_list(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if lap_store is None:
            raise HTTPException(status_code=503, detail="Lap store not configured")
        return score_session(
            data_dir=settings.data_dir,
            session_id=session_id,
            gt_laps=gt_laps,
            subdir=accuracy.settings.subdir,
            lap_store=lap_store,
        )
