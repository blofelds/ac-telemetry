"""Unit tests for review lap statistics, outlier trimming, and session filtering."""

from __future__ import annotations

from ac_telemetry.store import SESSION_TYPE_PRACTICE, SESSION_TYPE_RACE
from ac_telemetry.web.review.stats import (
    OUTLIER_THRESHOLD_RATIO,
    compute_lap_stats,
    enrich_session,
    filter_sessions,
    format_delta_ms,
    format_lap_ms,
    quantile,
    resolve_session_type,
)


def _make_session_row(
    sid: str,
    *,
    started_at: str = "2026-10-14T19:15:00+00:00",
    track: str = "Vallelunga",
    car: str = "Porsche 911 GT3 R",
    notes: str = "",
    session_type: str = "p",
    status: str = "stopped",
) -> dict[str, str]:
    return {
        "session_id": sid,
        "started_at": started_at,
        "ended_at": started_at,
        "track": track,
        "car": car,
        "notes": notes,
        "session_type": session_type,
        "status": status,
    }


def _make_lap_row(
    sid: str,
    n: int,
    ms: int,
    *,
    note: str = "",
    session_type: str = "",
) -> dict[str, object]:
    return {
        "session_id": sid,
        "session_type": session_type,
        "lap_number": str(n),
        "lap_time": format_lap_ms(ms),
        "lap_time_ms": str(ms),
        "recorded_at": "2026-10-14T19:20:00+00:00",
        "source": "mock",
        "raw_text": format_lap_ms(ms),
        "note": note,
    }


def test_format_helpers() -> None:
    assert format_lap_ms(None) == "--:--.---"
    assert format_lap_ms(95_090) == "1:35.090"
    assert format_lap_ms(55_400.6) == "0:55.401"
    assert format_delta_ms(None) == "--"
    assert format_delta_ms(0) == "+0.000s"
    assert format_delta_ms(420) == "+0.420s"
    assert format_delta_ms(-125) == "-0.125s"


def test_quantile_and_compute_lap_stats() -> None:
    assert quantile([], 0.5) is None
    assert quantile([95_000], 0.25) == 95_000.0
    assert quantile([95_000], 0.75) == 95_000.0

    stats = compute_lap_stats([100_000, 94_000, 96_000, 98_000])
    assert stats["best_ms"] == 94_000
    assert stats["worst_ms"] == 100_000
    assert stats["median_ms"] == 97_000.0
    assert stats["q1_ms"] == 95_500.0
    assert stats["q3_ms"] == 98_500.0
    assert stats["iqr_ms"] == 3_000.0
    assert stats["mean_ms"] == 97_000.0

    odd = compute_lap_stats([90_000, 92_000, 94_000, 96_000, 98_000])
    assert odd["best_ms"] == 90_000
    assert odd["q1_ms"] == 92_000.0
    assert odd["median_ms"] == 94_000.0
    assert odd["q3_ms"] == 96_000.0
    assert odd["iqr_ms"] == 4_000.0
    assert odd["worst_ms"] == 98_000

    empty = compute_lap_stats([])
    assert all(v is None for v in empty.values())


def test_outlier_trimming_at_107_percent_boundary() -> None:
    assert OUTLIER_THRESHOLD_RATIO == 1.07
    srow = _make_session_row("s1", notes="soft tyres")
    laps = [
        _make_lap_row("s1", 1, 107_001, note="out-lap, cold tyres"),
        _make_lap_row("s1", 2, 100_000),
        _make_lap_row("s1", 3, 101_000),
        _make_lap_row("s1", 4, 102_000),
        _make_lap_row("s1", 5, 107_000, note="on boundary"),
    ]

    trimmed = enrich_session(srow, laps, trim_outliers=True)
    assert trimmed["best_ms"] == 100_000
    assert trimmed["lap_count"] == 5
    assert trimmed["outlier_count"] == 1
    assert trimmed["visible_lap_count"] == 4
    assert [l["lap_number"] for l in trimmed["visible_laps"]] == [2, 3, 4, 5]
    assert trimmed["median_ms"] == 101_500.0
    assert trimmed["worst_ms"] == 107_000

    raw = enrich_session(srow, laps, trim_outliers=False)
    assert raw["outlier_count"] == 1
    assert raw["visible_lap_count"] == 5
    assert raw["median_ms"] == 102_000.0
    assert raw["worst_ms"] == 107_001


def test_legacy_blank_session_type_and_laps_csv_fallback() -> None:
    eff, legacy = resolve_session_type({"session_type": ""}, [{"session_type": ""}])
    assert eff == SESSION_TYPE_PRACTICE
    assert legacy is True

    eff2, legacy2 = resolve_session_type(
        {"session_type": ""}, [{"session_type": "r"}]
    )
    assert eff2 == SESSION_TYPE_RACE
    assert legacy2 is False

    assert resolve_session_type({"session_type": "p"}) == (SESSION_TYPE_PRACTICE, False)
    assert resolve_session_type({"session_type": "r"}) == (SESSION_TYPE_RACE, False)


def test_hide_zero_lap_sessions_and_notes_search() -> None:
    s1 = enrich_session(
        _make_session_row("s1", notes="soft tyres, 15L fuel", session_type=""),
        [
            _make_lap_row("s1", 1, 108_000, note="spin at Tornantino"),
            _make_lap_row("s1", 2, 95_000, note="clean lap"),
        ],
        trim_outliers=True,
    )
    s2 = enrich_session(
        _make_session_row(
            "s2",
            started_at="2026-10-15T19:00:00+00:00",
            notes="aborted capture",
            session_type="p",
        ),
        [],
        trim_outliers=True,
    )
    s3 = enrich_session(
        _make_session_row(
            "s3",
            started_at="2026-10-16T19:00:00+00:00",
            track="Monza",
            car="Ferrari 488 GT3",
            notes="10-lap sprint race",
            session_type="r",
        ),
        [_make_lap_row("s3", 1, 110_000, note="T1 chicane traffic")],
        trim_outliers=True,
    )

    visible = filter_sessions([s1, s2, s3], hide_empty=True)
    assert [s["session_id"] for s in visible] == ["s1", "s3"]

    with_empty = filter_sessions([s1, s2, s3], hide_empty=False)
    assert [s["session_id"] for s in with_empty] == ["s1", "s2", "s3"]

    practice = filter_sessions([s1, s2, s3], session_type="p", hide_empty=True)
    assert [s["session_id"] for s in practice] == ["s1"]

    race = filter_sessions([s1, s2, s3], session_type="r", hide_empty=True)
    assert [s["session_id"] for s in race] == ["s3"]

    assert [
        s["session_id"]
        for s in filter_sessions([s1, s2, s3], notes_query="SOFT TYRES")
    ] == ["s1"]
    assert [
        s["session_id"]
        for s in filter_sessions([s1, s2, s3], notes_query="tornantino")
    ] == ["s1"]
    assert [
        s["session_id"]
        for s in filter_sessions([s1, s2, s3], notes_query="chicane")
    ] == ["s3"]
    assert [
        s["session_id"]
        for s in filter_sessions([s1, s2, s3], notes_query="ferrari")
    ] == ["s3"]
