"""HTTP routes for accuracy GT + scores (mounted only when enabled)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ac_telemetry.accuracy.score import (
    load_gt_list,
    prefills_from_csv,
    save_gt,
    score_session,
)
from ac_telemetry.accuracy.session import AccuracySession
from ac_telemetry.settings import Settings
from ac_telemetry.store import LapStore, SessionStore


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


def mount_accuracy_routes(
    app: FastAPI,
    *,
    settings: Settings,
    store: SessionStore,
    lap_store: LapStore | None,
    accuracy: AccuracySession,
) -> None:
    """Register /api/accuracy/* routes. Caller must only mount when enabled."""

    def _sid_or_404(session_id: str) -> str:
        row = store.get_session(session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return session_id

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
