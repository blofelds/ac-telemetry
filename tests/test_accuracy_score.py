"""Unit tests for GT alignment / write% / ocr-sample% (no live capture)."""

from __future__ import annotations

import json
from pathlib import Path

from ac_telemetry.accuracy.ocr_log import OcrSampleLog
from ac_telemetry.accuracy.paths import ocr_samples_path, session_dir
from ac_telemetry.accuracy.score import (
    align_csv_to_gt,
    load_gt_list,
    normalize_lap_text,
    prefills_from_csv,
    score_session,
)
from ac_telemetry.store.laps import LapStore


def test_normalize_and_load_gt() -> None:
    assert normalize_lap_text("1:07.717") == "1:07.717"
    assert normalize_lap_text("01:07.717") == "1:07.717"
    laps = load_gt_list(["1:07.717", 141_430, {"lap_time": "1:07.538", "note": "ok"}])
    assert [x["lap_time"] for x in laps] == ["1:07.717", "2:21.430", "1:07.538"]


def test_align_exact_with_extras_and_miss() -> None:
    gt = load_gt_list(["1:00.000", "1:01.000", "1:02.000"])
    # list_laps style: newest-first
    csv = [
        {"lap_time": "1:02.000", "lap_number": "3", "recorded_at": "2026-10-11T12:03:00+00:00"},
        {"lap_time": "9:99.999", "lap_number": "2", "recorded_at": "2026-10-11T12:02:00+00:00"},  # extra (invalid norm?)
        {"lap_time": "1:00.000", "lap_number": "1", "recorded_at": "2026-10-11T12:01:00+00:00"},
    ]
    # Fix extra to a valid but unmatched time
    csv[1]["lap_time"] = "1:55.000"
    matches, misses, extras = align_csv_to_gt(gt, csv)
    assert [m["gt"]["lap_time"] for m in matches] == ["1:00.000", "1:02.000"]
    assert [m["lap_time"] for m in misses] == ["1:01.000"]
    assert [e["lap_time"] for e in extras] == ["1:55.000"]


def test_score_session_write_and_ocr_pct(tmp_path: Path) -> None:
    data_dir = tmp_path / "sessions"
    store = LapStore(data_dir)
    store.ensure()
    sid = "abc123score"
    # Chronological writes
    store.append_lap(
        {
            "session_id": sid,
            "lap_number": 1,
            "lap_time": "1:00.000",
            "lap_time_ms": 60_000,
            "recorded_at": "2026-10-11T12:01:00+00:00",
            "source": "mock",
            "raw_text": "1:00.000",
        }
    )
    store.append_lap(
        {
            "session_id": sid,
            "lap_number": 2,
            "lap_time": "1:01.000",
            "lap_time_ms": 61_000,
            "recorded_at": "2026-10-11T12:02:00+00:00",
            "source": "mock",
            "raw_text": "1:01.000",
        }
    )

    sdir = session_dir(data_dir, sid)
    sdir.mkdir(parents=True)
    log = OcrSampleLog(ocr_samples_path(sdir))
    log.open()
    # Window 1: mostly correct, one flicker
    for i, text in enumerate(["1:00.000", "1:00.000", "1:00.100", "1:00.000"]):
        log.append(
            {
                "session_id": sid,
                "mono_s": 100.0 + i,
                "wall_s": 1_760_185_260.0 + i,  # around 12:01
                "ok": True,
                "text": text,
                "lap_time_ms": 60_000 if text.startswith("1:00.0") else 60_100,
                "error": "",
            }
        )
    # Window 2: all correct
    for i in range(3):
        log.append(
            {
                "session_id": sid,
                "mono_s": 200.0 + i,
                "wall_s": 1_760_185_320.0 + i,  # around 12:02
                "ok": True,
                "text": "1:01.000",
                "lap_time_ms": 61_000,
                "error": "",
            }
        )

    # Use wall times matching recorded_at
    # 2026-10-11T12:01:00Z = 1760184060? Let's compute from the ISO we wrote.
    from datetime import datetime, timezone

    t1 = datetime(2026, 10, 11, 12, 1, 0, tzinfo=timezone.utc).timestamp()
    t2 = datetime(2026, 10, 11, 12, 2, 0, tzinfo=timezone.utc).timestamp()
    # Rewrite samples with correct walls
    ocr_samples_path(sdir).write_text("", encoding="utf-8")
    log = OcrSampleLog(ocr_samples_path(sdir))
    for i, text in enumerate(["1:00.000", "1:00.000", "1:00.100", "1:00.000"]):
        log.append(
            {
                "session_id": sid,
                "mono_s": float(i),
                "wall_s": t1 - 3 + i,
                "ok": True,
                "text": text,
                "lap_time_ms": 60_000,
                "error": "",
            }
        )
    for i in range(3):
        log.append(
            {
                "session_id": sid,
                "mono_s": 10.0 + i,
                "wall_s": t2 - 2 + i,
                "ok": True,
                "text": "1:01.000",
                "lap_time_ms": 61_000,
                "error": "",
            }
        )

    gt = load_gt_list(["1:00.000", "1:01.000"])
    report = score_session(
        data_dir=data_dir,
        session_id=sid,
        gt_laps=gt,
        lap_store=store,
    )
    assert report["write_pct"] == 100.0
    assert report["write_matches"] == 2
    assert report["write_misses"] == 0
    assert report["write_extras"] == 0
    assert report["ocr_sample_total"] >= 5
    assert report["ocr_sample_pct"] is not None
    assert report["ocr_sample_pct"] < 100.0  # flicker in lap 1
    assert len(report["per_lap"]) == 2
    assert report["per_lap"][0]["status"] == "match"
    assert (Path(report["artefact_dir"]) / "score.md").is_file()
    assert (Path(report["artefact_dir"]) / "review.md").is_file()
    review = (Path(report["artefact_dir"]) / "review.md").read_text(encoding="utf-8")
    assert "GT #1" in review and "GT #2" in review


def test_prefill_from_csv_order(tmp_path: Path) -> None:
    store = LapStore(tmp_path)
    store.ensure()
    store.append_lap(
        {
            "session_id": "s1",
            "lap_number": 1,
            "lap_time": "1:10.000",
            "lap_time_ms": 70_000,
            "source": "mock",
            "raw_text": "1:10.000",
        }
    )
    store.append_lap(
        {
            "session_id": "s1",
            "lap_number": 2,
            "lap_time": "1:11.000",
            "lap_time_ms": 71_000,
            "source": "mock",
            "raw_text": "1:11.000",
        }
    )
    draft = prefills_from_csv(store.list_laps(session_id="s1", limit=50))
    assert [d["lap_time"] for d in draft] == ["1:10.000", "1:11.000"]
