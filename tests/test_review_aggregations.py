"""Unit tests for review view aggregations, CSV store loading, and GT detection."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ac_telemetry.accuracy.paths import gt_draft_path, gt_path, session_dir
from ac_telemetry.store import LAP_FIELDS, SESSION_FIELDS, LapStore, SessionStore
from ac_telemetry.web.review import (
    build_activity_buckets,
    build_combo_leaderboard,
    build_pace_progression,
    build_practice_vs_race,
    build_review_payload,
    build_stint_comparison,
    enrich_session,
    format_lap_ms,
)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _make_session_row(
    sid: str,
    *,
    started_at: str = "2026-10-14T19:15:00+00:00",
    track: str = "Vallelunga",
    car: str = "Porsche 911 GT3 R",
    notes: str = "",
    session_type: str = "p",
) -> dict[str, str]:
    return {
        "session_id": sid,
        "started_at": started_at,
        "ended_at": started_at,
        "track": track,
        "car": car,
        "notes": notes,
        "session_type": session_type,
        "status": "stopped",
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


def test_leaderboard_progression_stints_pvr_and_activity() -> None:
    s1 = enrich_session(
        _make_session_row(
            "s1",
            started_at="2026-10-14T19:00:00+00:00",
            track="Vallelunga",
            car="Porsche 911 GT3 R",
            notes="baseline, medium tyres",
            session_type="",
        ),
        [
            _make_lap_row("s1", 1, 105_000, note="out-lap"),
            _make_lap_row("s1", 2, 95_400),
            _make_lap_row("s1", 3, 95_000),
            _make_lap_row("s1", 4, 95_600),
        ],
        gt_confirmed=True,
        trim_outliers=True,
    )
    s2 = enrich_session(
        _make_session_row(
            "s2",
            started_at="2026-10-21T19:00:00+00:00",
            track="Vallelunga",
            car="Porsche 911 GT3 R",
            notes="race stint",
            session_type="r",
        ),
        [
            _make_lap_row("s2", 1, 95_800),
            _make_lap_row("s2", 2, 95_500),
            _make_lap_row("s2", 3, 96_100),
        ],
        gt_confirmed=True,
        trim_outliers=True,
    )
    s3 = enrich_session(
        _make_session_row(
            "s3",
            started_at="2026-10-28T19:00:00+00:00",
            track="Vallelunga",
            car="Porsche 911 GT3 R",
            notes="soft tyres PB",
            session_type="p",
        ),
        [
            _make_lap_row("s3", 1, 94_200),
            _make_lap_row("s3", 2, 94_000),
            _make_lap_row("s3", 3, 94_600),
        ],
        gt_confirmed=False,
        trim_outliers=True,
    )
    s4 = enrich_session(
        _make_session_row(
            "s4",
            started_at="2026-10-28T20:00:00+00:00",
            track="Monza",
            car="Ferrari 488 GT3",
            notes="practice only",
            session_type="p",
        ),
        [_make_lap_row("s4", 1, 110_000)],
        gt_confirmed=False,
        trim_outliers=True,
    )

    sessions = [s1, s2, s3, s4]

    combos = build_combo_leaderboard(sessions)
    assert len(combos) == 2
    val = combos[0]
    assert val["track"] == "Vallelunga"
    assert val["pb_ms"] == 94_000
    assert val["pb_time"] == "1:34.000"
    assert val["recent_median_ms"] == 94_200.0
    assert val["practice_pb_ms"] == 94_000
    assert val["race_pb_ms"] == 95_500
    assert val["pvr_delta_ms"] == 1_500
    assert val["session_count"] == 3
    assert val["lap_count"] == 9
    assert val["gt_count"] == 2
    assert val["legacy_count"] == 1
    assert combos[1]["pvr_delta_ms"] is None

    prog = build_pace_progression(
        sessions, track="Vallelunga", car="Porsche 911 GT3 R"
    )
    assert [p["session_id"] for p in prog["points"]] == ["s1", "s2", "s3"]
    assert [p["best_ms"] for p in prog["points"]] == [95_000, 95_500, 94_000]
    assert [p["running_pb_ms"] for p in prog["points"]] == [95_000, 95_000, 94_000]
    assert prog["gain_ms"] == -1_000

    stints = build_stint_comparison([s1, s2, s3], session_ids=["s1", "s3"])
    assert [st["session_id"] for st in stints["stints"]] == ["s1", "s3"]
    assert stints["stints"][0]["min_ms"] == 95_000
    assert stints["stints"][0]["median_ms"] == 95_400.0
    assert stints["stints"][0]["iqr_ms"] == 300.0
    assert stints["stints"][1]["min_ms"] == 94_000

    pvr = build_practice_vs_race(sessions)
    assert len(pvr) == 1
    assert pvr[0]["track"] == "Vallelunga"
    assert pvr[0]["practice_best_ms"] == 94_000
    assert pvr[0]["race_best_ms"] == 95_500
    assert pvr[0]["best_delta_ms"] == 1_500
    assert pvr[0]["practice_laps"] == 6
    assert pvr[0]["race_laps"] == 3
    assert pvr[0]["legacy_count"] == 1

    activity = build_activity_buckets(sessions)
    assert [w["week_key"] for w in activity["weeks"]] == [
        "2026-10-12",
        "2026-10-19",
        "2026-10-26",
    ]
    assert activity["weeks"][0]["practice_laps"] == 3
    assert activity["weeks"][0]["race_laps"] == 0
    assert activity["weeks"][1]["race_laps"] == 3
    assert activity["weeks"][2]["by_track"] == {"Vallelunga": 3, "Monza": 1}
    assert activity["practice_total_laps"] == 7
    assert activity["race_total_laps"] == 3


def test_build_review_payload_reads_existing_csv_stores_and_gt(
    tmp_path: Path,
) -> None:
    """Reuses SessionStore + LapStore without altering CSV schemas; detects GT."""
    data_dir = tmp_path / "sessions"
    _write_csv(
        data_dir / "sessions.csv",
        SESSION_FIELDS,
        [
            _make_session_row(
                "sess-csv-gt",
                started_at="2026-10-14T19:00:00+00:00",
                track="Vallelunga",
                car="Porsche 911 GT3 R",
                notes="medium tyres",
                session_type="",
            ),
            _make_session_row(
                "sess-file-gt",
                started_at="2026-10-20T19:00:00+00:00",
                track="Vallelunga",
                car="Porsche 911 GT3 R",
                notes="sprint race",
                session_type="r",
            ),
            _make_session_row(
                "sess-empty",
                started_at="2026-10-21T19:00:00+00:00",
                track="Monza",
                car="Ferrari 488 GT3",
                notes="aborted",
                session_type="p",
            ),
        ],
    )
    _write_csv(
        data_dir / "laps.csv",
        LAP_FIELDS,
        [
            _make_lap_row("sess-csv-gt", 1, 105_000, note="gt_confirmed"),
            _make_lap_row("sess-csv-gt", 2, 95_000, note="gt_confirmed"),
            _make_lap_row("sess-file-gt", 1, 95_800, session_type="r"),
            _make_lap_row("sess-file-gt", 2, 95_400, session_type="r"),
        ],
    )

    sdir = session_dir(data_dir, "sess-file-gt", subdir="accuracy")
    sdir.mkdir(parents=True)
    gt_path(sdir).write_text(
        json.dumps({"laps": ["1:35.800", "1:35.400"]}), encoding="utf-8"
    )
    assert not gt_draft_path(sdir).exists()

    store = SessionStore(data_dir)
    lap_store = LapStore(data_dir)
    payload = build_review_payload(store, lap_store, data_dir=data_dir)

    assert payload["summary"]["total_sessions"] == 3
    assert payload["summary"]["session_count"] == 2
    assert payload["summary"]["empty_session_count"] == 1
    assert payload["summary"]["gt_confirmed_count"] == 2
    assert payload["summary"]["legacy_blank_count"] == 1
    assert payload["summary"]["outlier_count"] == 1
    assert payload["summary"]["visible_laps"] == 3
    assert payload["summary"]["raw_laps"] == 4
    assert payload["options"]["tracks"] == ["Monza", "Vallelunga"]
    assert payload["options"]["cars"] == ["Ferrari 488 GT3", "Porsche 911 GT3 R"]
    assert len(payload["combos"]) == 1
    assert len(payload["practice_vs_race"]) == 1

    assert (
        (data_dir / "sessions.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
        == SESSION_FIELDS
    )
    assert (
        (data_dir / "laps.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
        == LAP_FIELDS
    )
