"""Practice vs Race pace deltas and weekly activity bucket aggregations."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Mapping, Sequence

from ac_telemetry.store import SESSION_TYPE_PRACTICE, SESSION_TYPE_RACE
from ac_telemetry.web.review.stats import (
    MISSING_TEXT,
    compute_lap_stats,
    format_delta_ms,
    format_lap_ms,
)


def build_practice_vs_race(
    sessions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Compute Race minus Practice pace and consistency deltas per Track + Car."""
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for s in sessions:
        if s.get("best_ms") is None:
            continue
        grouped[
            (str(s.get("track") or MISSING_TEXT), str(s.get("car") or MISSING_TEXT))
        ].append(s)

    rows: list[dict[str, Any]] = []
    for (track, car), group in grouped.items():
        p_sessions = [
            s for s in group if s.get("effective_type") == SESSION_TYPE_PRACTICE
        ]
        r_sessions = [
            s for s in group if s.get("effective_type") == SESSION_TYPE_RACE
        ]
        if not p_sessions or not r_sessions:
            continue

        p_times = [
            int(lap["lap_time_ms"])
            for s in p_sessions
            for lap in (s.get("visible_laps") or ())
            if lap.get("lap_time_ms")
        ]
        r_times = [
            int(lap["lap_time_ms"])
            for s in r_sessions
            for lap in (s.get("visible_laps") or ())
            if lap.get("lap_time_ms")
        ]
        p_stats = compute_lap_stats(p_times)
        r_stats = compute_lap_stats(r_times)
        if p_stats["best_ms"] is None or r_stats["best_ms"] is None:
            continue

        best_delta_ms = int(r_stats["best_ms"]) - int(p_stats["best_ms"])
        med_delta_ms = (
            float(r_stats["median_ms"]) - float(p_stats["median_ms"])
            if (p_stats["median_ms"] is not None and r_stats["median_ms"] is not None)
            else None
        )
        rows.append(
            {
                "key": f"{track}__{car}",
                "track": track,
                "car": car,
                "short_label": f"{track.split()[0]} ({car.split()[0]})",
                "practice_best_ms": p_stats["best_ms"],
                "practice_best_time": format_lap_ms(p_stats["best_ms"]),
                "race_best_ms": r_stats["best_ms"],
                "race_best_time": format_lap_ms(r_stats["best_ms"]),
                "practice_median_ms": p_stats["median_ms"],
                "practice_median_time": format_lap_ms(p_stats["median_ms"]),
                "race_median_ms": r_stats["median_ms"],
                "race_median_time": format_lap_ms(r_stats["median_ms"]),
                "practice_iqr_ms": p_stats["iqr_ms"],
                "race_iqr_ms": r_stats["iqr_ms"],
                "best_delta_ms": best_delta_ms,
                "best_delta_text": format_delta_ms(best_delta_ms),
                "median_delta_ms": med_delta_ms,
                "median_delta_text": format_delta_ms(med_delta_ms),
                "practice_laps": len(p_times),
                "race_laps": len(r_times),
                "practice_sessions": len(p_sessions),
                "race_sessions": len(r_sessions),
                "legacy_count": sum(
                    1 for s in p_sessions if s.get("is_legacy_blank_type")
                ),
            }
        )

    rows.sort(
        key=lambda r: (
            -(int(r["practice_sessions"]) + int(r["race_sessions"])),
            str(r["track"]).lower(),
            str(r["car"]).lower(),
        )
    )
    return rows


def build_activity_buckets(
    sessions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Weekly visible-lap buckets grouped by track, car, and Practice vs Race."""
    weeks_map: dict[str, dict[str, Any]] = {}
    tracks_seen: set[str] = set()
    cars_seen: set[str] = set()
    practice_total = 0
    race_total = 0

    for s in sessions:
        wk_key = str(s.get("week_key") or "0000-00-00")
        wk_label = str(s.get("week_label") or "Unknown")
        track = str(s.get("track") or MISSING_TEXT)
        car = str(s.get("car") or MISSING_TEXT)
        laps_n = int(s.get("visible_lap_count") or 0)
        eff_type = str(s.get("effective_type") or SESSION_TYPE_PRACTICE)

        tracks_seen.add(track)
        cars_seen.add(car)
        bucket = weeks_map.get(wk_key)
        if bucket is None:
            bucket = {
                "week_key": wk_key,
                "week_label": wk_label,
                "session_count": 0,
                "total_laps": 0,
                "practice_laps": 0,
                "race_laps": 0,
                "by_track": defaultdict(int),
                "by_car": defaultdict(int),
            }
            weeks_map[wk_key] = bucket

        bucket["session_count"] += 1
        bucket["total_laps"] += laps_n
        bucket["by_track"][track] += laps_n
        bucket["by_car"][car] += laps_n
        if eff_type == SESSION_TYPE_RACE:
            bucket["race_laps"] += laps_n
            race_total += laps_n
        else:
            bucket["practice_laps"] += laps_n
            practice_total += laps_n

    ordered_keys = sorted(weeks_map.keys())
    years = {k[:4] for k in ordered_keys if k != "0000-00-00" and len(k) >= 4}
    multi_year = len(years) > 1

    weeks_out: list[dict[str, Any]] = []
    for k in ordered_keys:
        b = weeks_map[k]
        label = b["week_label"]
        if multi_year and k != "0000-00-00":
            try:
                label = datetime.fromisoformat(k).strftime("%d %b '%y")
            except ValueError:
                pass
        weeks_out.append(
            {
                "week_key": k,
                "week_label": label,
                "session_count": b["session_count"],
                "total_laps": b["total_laps"],
                "practice_laps": b["practice_laps"],
                "race_laps": b["race_laps"],
                "by_track": dict(b["by_track"]),
                "by_car": dict(b["by_car"]),
            }
        )

    return {
        "weeks": weeks_out,
        "tracks": sorted(tracks_seen),
        "cars": sorted(cars_seen),
        "practice_total_laps": practice_total,
        "race_total_laps": race_total,
    }
