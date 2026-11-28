"""Lap statistics, outlier trimming, session enrichment, and filtering."""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any, Mapping, Sequence

from ac_telemetry.detect.readers import format_lap_time_ms
from ac_telemetry.store import SESSION_TYPE_PRACTICE, SESSION_TYPE_RACE
from ac_telemetry.web.session_title import _TZ as DISPLAY_TZ, _parse_started_at

OUTLIER_THRESHOLD_RATIO = 1.07
MISSING_TEXT = "—"


def format_lap_ms(ms: float | int | None) -> str:
    """Format milliseconds as ``m:ss.sss``, or ``--:--.---`` when missing."""
    if ms is None or not math.isfinite(float(ms)):
        return "--:--.---"
    total_ms = int(round(float(ms)))
    if total_ms < 0:
        return "--:--.---"
    return format_lap_time_ms(total_ms)


def format_delta_ms(delta_ms: float | int | None) -> str:
    """Format signed millisecond delta as ``+0.420s`` / ``-0.120s``, or ``--``."""
    if delta_ms is None or not math.isfinite(float(delta_ms)):
        return "--"
    val = float(delta_ms)
    sign = "+" if val >= 0 else "-"
    return f"{sign}{abs(val) / 1000.0:.3f}s"


def quantile(sorted_vals: Sequence[float | int], q: float) -> float | None:
    """Linear-interpolated quantile in [0, 1] over pre-sorted values."""
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_vals[0])
    q_clamped = max(0.0, min(1.0, float(q)))
    pos = (n - 1) * q_clamped
    base = math.floor(pos)
    rest = pos - base
    if base + 1 < n:
        return float(sorted_vals[base]) + rest * (
            float(sorted_vals[base + 1]) - float(sorted_vals[base])
        )
    return float(sorted_vals[base])


def compute_lap_stats(times_ms: Sequence[int]) -> dict[str, float | int | None]:
    """Return best, Q1, median, Q3, IQR, mean, and worst over positive times."""
    vals = sorted(int(v) for v in times_ms if v is not None and int(v) > 0)
    if not vals:
        return {
            "best_ms": None,
            "q1_ms": None,
            "median_ms": None,
            "q3_ms": None,
            "iqr_ms": None,
            "mean_ms": None,
            "worst_ms": None,
        }
    q1 = quantile(vals, 0.25)
    med = quantile(vals, 0.5)
    q3 = quantile(vals, 0.75)
    iqr = (q3 - q1) if (q1 is not None and q3 is not None) else None
    mean = sum(vals) / len(vals)
    return {
        "best_ms": vals[0],
        "q1_ms": q1,
        "median_ms": med,
        "q3_ms": q3,
        "iqr_ms": iqr,
        "mean_ms": mean,
        "worst_ms": vals[-1],
    }


def resolve_session_type(
    session_row: Mapping[str, Any],
) -> tuple[str, bool]:
    """Return ``(effective_type, is_legacy_blank_type)`` from ``sessions.csv``.

    Blank or unrecognized values count as Practice (``p``) and are flagged as legacy.
    """
    raw = str(session_row.get("session_type") or "").strip().lower()
    if not raw:
        return SESSION_TYPE_PRACTICE, True
    if raw in (SESSION_TYPE_RACE, "race"):
        return SESSION_TYPE_RACE, False
    if raw in (SESSION_TYPE_PRACTICE, "practice", "not-race", "not_race"):
        return SESSION_TYPE_PRACTICE, False
    return SESSION_TYPE_PRACTICE, True


def _format_date_label(started_at: Any) -> str:
    dt = _parse_started_at(started_at)
    if dt is None:
        return MISSING_TEXT
    return dt.astimezone(DISPLAY_TZ).strftime("%d %b")


def _week_bucket(started_at: Any) -> tuple[str, str]:
    """Return ``(sort_key, human_label)`` for the ISO week (Europe/London)."""
    dt = _parse_started_at(started_at)
    if dt is None:
        return "0000-00-00", "Unknown"
    local_date = dt.astimezone(DISPLAY_TZ).date()
    monday = local_date - timedelta(days=local_date.weekday())
    return monday.isoformat(), monday.strftime("%d %b")


def _parse_lap_number(raw: Any, fallback: int) -> int:
    if raw is None or str(raw).strip() == "":
        return fallback
    try:
        val = int(raw)
        return val if val > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _parse_positive_ms(raw: Any) -> int | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        try:
            ms = int(round(float(str(raw))))
        except (TypeError, ValueError):
            return None
    return ms if ms > 0 else None


def enrich_session(
    session_row: Mapping[str, Any],
    lap_rows: Sequence[Mapping[str, Any]],
    *,
    gt_confirmed: bool = False,
    trim_outliers: bool = True,
    outlier_ratio: float = OUTLIER_THRESHOLD_RATIO,
) -> dict[str, Any]:
    """Enrich a single session and its chronological laps with review stats."""
    sid = str(session_row.get("session_id") or "").strip()
    started_at = str(session_row.get("started_at") or "").strip()
    track = str(session_row.get("track") or "").strip() or MISSING_TEXT
    car = str(session_row.get("car") or "").strip() or MISSING_TEXT
    notes = str(session_row.get("notes") or "").strip()
    status = str(session_row.get("status") or "").strip()
    effective_type, is_legacy_blank = resolve_session_type(session_row)
    week_key, week_label = _week_bucket(started_at)

    parsed_laps: list[dict[str, Any]] = []
    for idx, row in enumerate(lap_rows, start=1):
        ms = _parse_positive_ms(row.get("lap_time_ms"))
        if ms is None:
            continue
        lap_num = _parse_lap_number(row.get("lap_number"), idx)
        lap_note = str(row.get("note") or "").strip()
        lap_time = str(row.get("lap_time") or "").strip() or format_lap_ms(ms)
        parsed_laps.append(
            {
                "lap_number": lap_num,
                "lap_time_ms": ms,
                "lap_time": lap_time,
                "note": lap_note,
                "recorded_at": str(row.get("recorded_at") or "").strip(),
                "source": str(row.get("source") or "").strip(),
            }
        )

    best_ms = min((lap["lap_time_ms"] for lap in parsed_laps), default=None)
    outlier_cutoff_ms = (
        best_ms * float(outlier_ratio) if best_ms is not None else None
    )

    laps_out: list[dict[str, Any]] = []
    trimmed_laps: list[dict[str, Any]] = []
    for lap in parsed_laps:
        ms = lap["lap_time_ms"]
        is_outlier = outlier_cutoff_ms is not None and ms > outlier_cutoff_ms
        is_best = best_ms is not None and ms == best_ms
        item = {
            **lap,
            "is_outlier": is_outlier,
            "is_best": is_best,
            "delta_ms": (ms - best_ms) if best_ms is not None else None,
        }
        laps_out.append(item)
        if not is_outlier:
            trimmed_laps.append(item)

    outlier_count = len(laps_out) - len(trimmed_laps)
    visible_laps = trimmed_laps if trim_outliers else laps_out
    stats = compute_lap_stats([lap["lap_time_ms"] for lap in visible_laps])

    return {
        "session_id": sid,
        "started_at": started_at,
        "ended_at": str(session_row.get("ended_at") or "").strip(),
        "date_label": _format_date_label(started_at),
        "week_key": week_key,
        "week_label": week_label,
        "track": track,
        "car": car,
        "notes": notes,
        "status": status,
        "raw_session_type": str(session_row.get("session_type") or "").strip(),
        "effective_type": effective_type,
        "is_legacy_blank_type": is_legacy_blank,
        "gt_confirmed": bool(gt_confirmed),
        "laps": laps_out,
        "visible_laps": visible_laps,
        "lap_count": len(laps_out),
        "visible_lap_count": len(visible_laps),
        "outlier_count": outlier_count,
        "outlier_cutoff_ms": outlier_cutoff_ms,
        "best_ms": best_ms,
        "best_time": format_lap_ms(best_ms),
        "q1_ms": stats["q1_ms"],
        "median_ms": stats["median_ms"],
        "median_time": format_lap_ms(stats["median_ms"]),
        "q3_ms": stats["q3_ms"],
        "iqr_ms": stats["iqr_ms"],
        "mean_ms": stats["mean_ms"],
        "worst_ms": stats["worst_ms"],
    }


def filter_sessions(
    sessions: Sequence[Mapping[str, Any]],
    *,
    track: str = "All",
    car: str = "All",
    session_type: str = "all",
    notes_query: str = "",
    hide_empty: bool = True,
) -> list[dict[str, Any]]:
    """Filter enriched sessions by track, car, type, notes, and 0-lap toggle."""
    track_f = (track or "All").strip()
    car_f = (car or "All").strip()
    type_f = (session_type or "all").strip().lower()
    if type_f not in ("all", SESSION_TYPE_PRACTICE, SESSION_TYPE_RACE):
        type_f = "all"
    query = (notes_query or "").strip().lower()

    matched: list[dict[str, Any]] = []
    for raw in sessions:
        s = dict(raw)
        if hide_empty and int(s.get("lap_count") or 0) == 0:
            continue
        if track_f != "All" and s.get("track") != track_f:
            continue
        if car_f != "All" and s.get("car") != car_f:
            continue
        if type_f != "all" and s.get("effective_type") != type_f:
            continue
        if query:
            in_notes = query in str(s.get("notes") or "").lower()
            in_laps = any(
                query in str(lap.get("note") or "").lower()
                for lap in (s.get("laps") or ())
            )
            in_title = (
                query in str(s.get("track") or "").lower()
                or query in str(s.get("car") or "").lower()
            )
            if not (in_notes or in_laps or in_title):
                continue
        matched.append(s)

    matched.sort(
        key=lambda r: (str(r.get("started_at") or ""), str(r.get("session_id") or ""))
    )
    return matched
