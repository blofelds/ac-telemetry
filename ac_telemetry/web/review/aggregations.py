"""Combo leaderboard, pace progression, and stint comparison aggregations."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from ac_telemetry.store import SESSION_TYPE_PRACTICE, SESSION_TYPE_RACE
from ac_telemetry.web.review.stats import (
    MISSING_TEXT,
    compute_lap_stats,
    format_delta_ms,
    format_lap_ms,
)


def build_combo_leaderboard(
    sessions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate Track & Car PB leaderboard rows."""
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for s in sessions:
        grouped[
            (str(s.get("track") or MISSING_TEXT), str(s.get("car") or MISSING_TEXT))
        ].append(s)

    rows: list[dict[str, Any]] = []
    for (track, car), group in grouped.items():
        ordered = sorted(
            group,
            key=lambda r: (str(r.get("started_at") or ""), str(r.get("session_id") or "")),
        )
        with_laps = [s for s in ordered if s.get("best_ms") is not None]
        pb_session = min(with_laps, key=lambda s: int(s["best_ms"]), default=None)
        practice_bests = [
            int(s["best_ms"])
            for s in with_laps
            if s.get("effective_type") == SESSION_TYPE_PRACTICE
        ]
        race_bests = [
            int(s["best_ms"])
            for s in with_laps
            if s.get("effective_type") == SESSION_TYPE_RACE
        ]
        practice_pb_ms = min(practice_bests) if practice_bests else None
        race_pb_ms = min(race_bests) if race_bests else None
        pvr_delta_ms = (
            (race_pb_ms - practice_pb_ms)
            if (practice_pb_ms is not None and race_pb_ms is not None)
            else None
        )
        latest_with_laps = with_laps[-1] if with_laps else None
        recent_median_ms = (
            latest_with_laps.get("median_ms") if latest_with_laps else None
        )
        pb_ms = int(pb_session["best_ms"]) if pb_session is not None else None
        rows.append(
            {
                "key": f"{track}__{car}",
                "track": track,
                "car": car,
                "pb_ms": pb_ms,
                "pb_time": format_lap_ms(pb_ms),
                "pb_session_id": pb_session.get("session_id") if pb_session else None,
                "recent_median_ms": recent_median_ms,
                "recent_median_time": format_lap_ms(recent_median_ms),
                "practice_pb_ms": practice_pb_ms,
                "race_pb_ms": race_pb_ms,
                "pvr_delta_ms": pvr_delta_ms,
                "pvr_delta_text": format_delta_ms(pvr_delta_ms),
                "session_count": len(ordered),
                "timed_session_count": len(with_laps),
                "lap_count": sum(int(s.get("visible_lap_count") or 0) for s in ordered),
                "raw_lap_count": sum(int(s.get("lap_count") or 0) for s in ordered),
                "gt_count": sum(1 for s in ordered if s.get("gt_confirmed")),
                "legacy_count": sum(
                    1 for s in ordered if s.get("is_legacy_blank_type")
                ),
                "last_date": str(ordered[-1].get("date_label") or MISSING_TEXT),
                "last_started_at": str(ordered[-1].get("started_at") or ""),
                "session_ids": [str(s.get("session_id") or "") for s in ordered],
            }
        )

    rows.sort(
        key=lambda r: (
            -int(r["session_count"]),
            -int(r["lap_count"]),
            str(r["track"]).lower(),
            str(r["car"]).lower(),
        )
    )
    return rows


def build_pace_progression(
    sessions: Sequence[Mapping[str, Any]],
    *,
    track: str,
    car: str,
) -> dict[str, Any]:
    """Chronological session best, median, and running PB for one Track + Car."""
    matching = [
        s
        for s in sessions
        if s.get("track") == track
        and s.get("car") == car
        and s.get("best_ms") is not None
    ]
    matching.sort(
        key=lambda r: (str(r.get("started_at") or ""), str(r.get("session_id") or ""))
    )

    running_pb: int | None = None
    points: list[dict[str, Any]] = []
    for s in matching:
        best_ms = int(s["best_ms"])
        if running_pb is None or best_ms < running_pb:
            running_pb = best_ms
        points.append(
            {
                "session_id": s.get("session_id"),
                "started_at": s.get("started_at"),
                "date_label": s.get("date_label"),
                "effective_type": s.get("effective_type"),
                "is_legacy_blank_type": bool(s.get("is_legacy_blank_type")),
                "gt_confirmed": bool(s.get("gt_confirmed")),
                "notes": s.get("notes") or "",
                "best_ms": best_ms,
                "best_time": format_lap_ms(best_ms),
                "median_ms": s.get("median_ms"),
                "median_time": format_lap_ms(s.get("median_ms")),
                "running_pb_ms": running_pb,
                "running_pb_time": format_lap_ms(running_pb),
                "iqr_ms": s.get("iqr_ms"),
                "visible_lap_count": s.get("visible_lap_count", 0),
                "lap_count": s.get("lap_count", 0),
                "outlier_count": s.get("outlier_count", 0),
            }
        )

    first_best = points[0]["best_ms"] if points else None
    latest_best = points[-1]["best_ms"] if points else None
    gain_ms = (
        (latest_best - first_best)
        if (first_best is not None and latest_best is not None)
        else None
    )
    return {
        "track": track,
        "car": car,
        "pb_ms": running_pb,
        "pb_time": format_lap_ms(running_pb),
        "first_best_ms": first_best,
        "latest_best_ms": latest_best,
        "gain_ms": gain_ms,
        "gain_text": format_delta_ms(gain_ms),
        "points": points,
    }


def build_stint_comparison(
    sessions: Sequence[Mapping[str, Any]],
    *,
    session_ids: Sequence[str] | None = None,
    max_stints: int = 4,
) -> dict[str, Any]:
    """Build lap-by-lap overlay + consistency bands (min/Q1/median/Q3/IQR/max)."""
    with_laps = [s for s in sessions if s.get("best_ms") is not None]
    with_laps.sort(
        key=lambda r: (str(r.get("started_at") or ""), str(r.get("session_id") or ""))
    )

    if session_ids:
        wanted = set(session_ids)
        selected = [s for s in with_laps if s.get("session_id") in wanted][:max_stints]
    else:
        selected = with_laps[-min(3, len(with_laps)) :] if with_laps else []

    stints: list[dict[str, Any]] = []
    max_lap_number = 0
    all_visible_ms: list[int] = []
    for s in selected:
        vis = list(s.get("visible_laps") or ())
        times = [int(lap["lap_time_ms"]) for lap in vis if lap.get("lap_time_ms")]
        stats = compute_lap_stats(times)
        all_visible_ms.extend(times)
        for lap in vis:
            max_lap_number = max(max_lap_number, int(lap.get("lap_number") or 0))
        stints.append(
            {
                "session_id": s.get("session_id"),
                "date_label": s.get("date_label"),
                "started_at": s.get("started_at"),
                "track": s.get("track"),
                "car": s.get("car"),
                "effective_type": s.get("effective_type"),
                "is_legacy_blank_type": bool(s.get("is_legacy_blank_type")),
                "gt_confirmed": bool(s.get("gt_confirmed")),
                "notes": s.get("notes") or "",
                "min_ms": stats["best_ms"],
                "q1_ms": stats["q1_ms"],
                "median_ms": stats["median_ms"],
                "q3_ms": stats["q3_ms"],
                "iqr_ms": stats["iqr_ms"],
                "max_ms": stats["worst_ms"],
                "laps": vis,
                "outlier_count": int(s.get("outlier_count") or 0),
            }
        )

    return {
        "max_lap_number": max_lap_number,
        "min_ms": min(all_visible_ms) if all_visible_ms else None,
        "max_ms": max(all_visible_ms) if all_visible_ms else None,
        "stints": stints,
    }
