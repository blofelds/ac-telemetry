"""CSV store loader and full payload assembler for the /review endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ac_telemetry.accuracy.paths import gt_draft_path, gt_path, session_dir
from ac_telemetry.store import LapStore, SessionStore
from ac_telemetry.web.review.aggregations import (
    build_combo_leaderboard,
    build_pace_progression,
    build_stint_comparison,
)
from ac_telemetry.web.review.comparisons import (
    build_activity_buckets,
    build_practice_vs_race,
)
from ac_telemetry.web.review.stats import (
    enrich_session,
    filter_sessions,
    format_lap_ms,
)

MAX_STORE_LIMIT = 500


def _has_gt_artefact(
    data_dir: Path | None, session_id: str, accuracy_subdir: str
) -> bool:
    if data_dir is None or not session_id:
        return False
    sdir = session_dir(data_dir, session_id, subdir=accuracy_subdir)
    return gt_path(sdir).is_file() or gt_draft_path(sdir).is_file()


def load_enriched_sessions(
    store: SessionStore,
    lap_store: LapStore | None,
    *,
    data_dir: Path | None = None,
    accuracy_subdir: str = "accuracy",
    trim_outliers: bool = True,
    limit: int = MAX_STORE_LIMIT,
) -> list[dict[str, Any]]:
    """Load sessions and laps through existing CSV stores and enrich them."""
    raw_sessions = store.list_sessions(limit=limit)
    gt_csv_ids: set[str] = (
        lap_store.session_ids_with_gt_confirmed()
        if lap_store is not None
        else set()
    )
    resolved_dir = data_dir if data_dir is not None else store.data_dir

    enriched: list[dict[str, Any]] = []
    for srow in raw_sessions:
        sid = str(srow.get("session_id") or "").strip()
        if not sid:
            continue
        if lap_store is not None:
            laps_chrono = list(
                reversed(lap_store.list_laps(session_id=sid, limit=MAX_STORE_LIMIT))
            )
        else:
            laps_chrono = []
        gt_confirmed = sid in gt_csv_ids or _has_gt_artefact(
            resolved_dir, sid, accuracy_subdir
        )
        enriched.append(
            enrich_session(
                srow,
                laps_chrono,
                gt_confirmed=gt_confirmed,
                trim_outliers=trim_outliers,
            )
        )

    enriched.sort(
        key=lambda r: (str(r.get("started_at") or ""), str(r.get("session_id") or ""))
    )
    return enriched


def build_review_payload(
    store: SessionStore,
    lap_store: LapStore | None,
    *,
    data_dir: Path | None = None,
    accuracy_subdir: str = "accuracy",
    track: str = "All",
    car: str = "All",
    session_type: str = "all",
    notes_query: str = "",
    trim_outliers: bool = True,
    hide_empty: bool = True,
) -> dict[str, Any]:
    """Build the full ``/api/review`` payload for all five review views."""
    all_sessions = load_enriched_sessions(
        store,
        lap_store,
        data_dir=data_dir,
        accuracy_subdir=accuracy_subdir,
        trim_outliers=trim_outliers,
    )
    all_tracks = sorted({s["track"] for s in all_sessions})
    all_cars = sorted({s["car"] for s in all_sessions})
    empty_session_count = sum(1 for s in all_sessions if s["lap_count"] == 0)

    filtered = filter_sessions(
        all_sessions,
        track=track,
        car=car,
        session_type=session_type,
        notes_query=notes_query,
        hide_empty=hide_empty,
    )

    combos = build_combo_leaderboard(filtered)
    pvr = build_practice_vs_race(filtered)
    activity = build_activity_buckets(filtered)

    active_combo = None
    if track != "All" and car != "All":
        active_combo = next(
            (c for c in combos if c["track"] == track and c["car"] == car),
            None,
        )
    if active_combo is None and combos:
        active_combo = combos[0]

    progression = (
        build_pace_progression(
            filtered,
            track=active_combo["track"],
            car=active_combo["car"],
        )
        if active_combo is not None
        else {
            "track": None,
            "car": None,
            "pb_ms": None,
            "pb_time": format_lap_ms(None),
            "first_best_ms": None,
            "latest_best_ms": None,
            "gain_ms": None,
            "gain_text": "--",
            "points": [],
        }
    )

    combo_sessions = (
        [
            s
            for s in filtered
            if s["track"] == active_combo["track"]
            and s["car"] == active_combo["car"]
        ]
        if active_combo is not None
        else []
    )
    stints = build_stint_comparison(combo_sessions)

    return {
        "filters": {
            "track": track,
            "car": car,
            "session_type": session_type,
            "notes_query": notes_query,
            "trim_outliers": bool(trim_outliers),
            "hide_empty": bool(hide_empty),
        },
        "options": {
            "tracks": all_tracks,
            "cars": all_cars,
        },
        "summary": {
            "total_sessions": len(all_sessions),
            "session_count": len(filtered),
            "empty_session_count": empty_session_count,
            "visible_laps": sum(s["visible_lap_count"] for s in filtered),
            "raw_laps": sum(s["lap_count"] for s in filtered),
            "outlier_count": sum(s["outlier_count"] for s in filtered),
            "gt_confirmed_count": sum(1 for s in filtered if s["gt_confirmed"]),
            "legacy_blank_count": sum(
                1 for s in filtered if s["is_legacy_blank_type"]
            ),
            "combo_count": len(combos),
            "pvr_combo_count": len(pvr),
        },
        "sessions": filtered,
        "combos": combos,
        "progression": progression,
        "stints": stints,
        "practice_vs_race": pvr,
        "activity": activity,
    }
