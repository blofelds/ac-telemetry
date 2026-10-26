#!/usr/bin/env python3
"""Full-video / card_long LAST accuracy replay harness.

Replays master MKVs through the production template reader +
``DetectService._handle_reading`` path (PTS as monotonic clock), then scores
CSV writes against operator GT:

  exact   — GT LAST strings present in the write list (set membership)
  written — number of CSV writes
  extra   — writes that are not exact GT strings (flicker / wrong membership)
  missed  — GT strings never written

This is the **full-video** measurement layer for when card_long masters are
available on disk (Cursor-hosted env or Latitude). ROI-crop CI fixtures are a
**later** layer — they are not implemented here. See ``docs/ACCURACY_HISTORY.md``.

Usage (from repo root, venv active):

  python scripts/replay_accuracy.py
  python scripts/replay_accuracy.py \\
      --video-dir ~/ac-telemetry-testdata/card_long
  python scripts/replay_accuracy.py --only 123100 --json-out /tmp/out.json

Default video dir tries ``$AC_TELEMETRY_CARD_LONG`` then
``~/ac-telemetry-testdata/card_long``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import cv2

from ac_telemetry.detect.readers import (
    LapTimeReading,
    build_lap_time_reader,
    format_lap_time_ms,
)
from ac_telemetry.detect.roi import crop_roi
from ac_telemetry.detect.service import DetectService
from ac_telemetry.settings import load_settings

# Operator eyeballed GT (driven LAST only — lap 1 is "-" / no write).
# Source of truth: store docs/card-long-artefacts.md (not shipped in git).
CARD_LONG_GT: dict[str, list[str]] = {
    "20261005-123100": [
        "1:18.795",
        "1:03.795",
        "1:03.081",
        "1:03.201",
        "1:03.654",
        "1:02.914",
        "1:03.330",
        "1:03.021",
        "1:03.020",
    ],
    "20261005-124252": [
        "1:59.980",
        "1:54.704",
        "1:52.581",
        "1:55.158",
    ],
    "20261006-213419": [
        "1:05.325",
        "1:03.457",
        "1:02.545",
        "1:02.705",
        "1:02.555",
        "1:02.788",
        "1:03.488",
        "1:03.413",
        "1:02.945",
        "1:02.619",
        "1:02.836",
        "1:03.173",
    ],
}

DEFAULT_CARD_LONG_CANDIDATES = (
    Path(os.environ["AC_TELEMETRY_CARD_LONG"])
    if os.environ.get("AC_TELEMETRY_CARD_LONG")
    else None,
    Path.home() / "ac-telemetry-testdata" / "card_long",
    Path("/home/ubuntu/ac-telemetry-testdata/card_long"),
    Path("/home/user1/ac-telemetry-testdata/card_long"),
)


def _resolve_video_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    for cand in DEFAULT_CARD_LONG_CANDIDATES:
        if cand is not None and cand.is_dir():
            return cand
    return Path.home() / "ac-telemetry-testdata" / "card_long"


def _dataset_id_for(path: Path) -> str | None:
    """Map ``20261005-123100_1280x720.mkv`` → ``20261005-123100``."""
    stem = path.stem
    for key in CARD_LONG_GT:
        if stem.startswith(key):
            return key
    # Fallback: first two underscore-separated tokens if they look like YYYYMMDD-HHMMSS
    parts = stem.split("_")
    if parts and len(parts[0]) >= 15 and parts[0][8] == "-":
        return parts[0]
    return None


def _make_service() -> tuple[DetectService, list[dict[str, Any]]]:
    """Production knobs from config; record_lap captures writes in memory."""
    settings = load_settings()
    settings.detect.enabled = True
    settings.detect.debug_dump.enabled = False
    recorded: list[dict[str, Any]] = []

    def _append(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        recorded.append(out)
        return out

    detect = DetectService(
        settings=settings,
        get_frame=lambda: None,
        get_session_id=lambda: "replay_accuracy",
        record_lap=_append,
    )
    detect.state.enabled = True
    detect.state.reader = settings.detect.lap_time.reader
    detect.state.mode = settings.detect.lap_time.mode
    detect._reader = build_lap_time_reader(
        settings.detect.lap_time.reader,
        templates_dir=settings.detect.lap_time.templates_dir,
        match_threshold=settings.detect.lap_time.match_threshold,
    )
    return detect, recorded


def _reading(ms: int | None) -> LapTimeReading:
    if ms is None:
        return LapTimeReading(ok=False, error="no read")
    return LapTimeReading(ok=True, text=format_lap_time_ms(ms), lap_time_ms=ms)


def score_writes(writes: list[str], gt: list[str]) -> dict[str, Any]:
    """Membership score: exact GT presence, extras, missed."""
    write_set = set(writes)
    gt_set = set(gt)
    exact = sorted(gt_set & write_set)
    extra = [w for w in writes if w not in gt_set]
    missed = sorted(gt_set - write_set)
    return {
        "exact": len(exact),
        "expected": len(gt),
        "written": len(writes),
        "extra": len(extra),
        "missed": len(missed),
        "exact_str": f"{len(exact)}/{len(gt)}",
        "gate_str": f"{len(writes)}/{len(extra)}/{len(missed)}",
        "writes": writes,
        "exact_matches": exact,
        "extras": extra,
        "missed_gt": missed,
    }


def replay_video(
    path: Path,
    *,
    detect_fps: float = 2.0,
    src_fps_hint: float | None = None,
) -> dict[str, Any]:
    """OCR + gate one full master; return OCR stats, writes, and optional score."""
    settings = load_settings()
    roi = settings.rois["lap_time"]
    reader = build_lap_time_reader(
        settings.detect.lap_time.reader,
        templates_dir=settings.detect.lap_time.templates_dir,
        match_threshold=settings.detect.lap_time.match_threshold,
    )

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {path}")
    prop_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    src_fps = src_fps_hint or (prop_fps if prop_fps > 1.0 else 30.0)
    step = max(1, int(round(src_fps / detect_fps)))

    events: list[tuple[float, int | None]] = []
    ocr_ok = 0
    ocr_fail = 0
    text_counter: Counter[str] = Counter()
    frame_index = 0
    t0 = time.perf_counter()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_index % step == 0:
            reading = reader.read(crop_roi(frame, roi))
            pts = frame_index / src_fps
            if reading.ok and reading.lap_time_ms is not None:
                ocr_ok += 1
                text_counter[reading.text or format_lap_time_ms(reading.lap_time_ms)] += 1
                events.append((pts, reading.lap_time_ms))
            else:
                ocr_fail += 1
                events.append((pts, None))
        frame_index += 1
    cap.release()
    ocr_wall_s = time.perf_counter() - t0

    detect, recorded = _make_service()
    mono = {"t": 0.0}
    real_mono = time.monotonic
    time.monotonic = lambda: mono["t"]  # type: ignore[assignment]
    try:
        for t, ms in events:
            mono["t"] = t
            detect._handle_reading(detect.settings.detect, _reading(ms), 0.01)
    finally:
        time.monotonic = real_mono  # type: ignore[assignment]

    writes = [str(r["lap_time"]) for r in recorded]
    dataset_id = _dataset_id_for(path)
    gt = CARD_LONG_GT.get(dataset_id or "", [])
    result: dict[str, Any] = {
        "path": str(path),
        "dataset_id": dataset_id,
        "src_fps": src_fps,
        "detect_fps": detect_fps,
        "frame_step": step,
        "frames": frame_index,
        "samples": len(events),
        "ocr": {
            "ok": ocr_ok,
            "fail": ocr_fail,
            "success_rate": round(ocr_ok / max(1, ocr_ok + ocr_fail), 4),
            "wall_s": round(ocr_wall_s, 2),
            "top_texts": text_counter.most_common(12),
        },
        "writes": writes,
    }
    if gt:
        result["gt"] = gt
        result["score"] = score_writes(writes, gt)
    else:
        result["score"] = None
        result["note"] = "no built-in GT for this filename; writes only"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--video-dir",
        type=Path,
        default=None,
        help="Directory of card_long master MKVs (default: env / ~/ac-telemetry-testdata/card_long)",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Substring filter on filename (repeatable), e.g. --only 123100",
    )
    parser.add_argument(
        "--detect-fps",
        type=float,
        default=2.0,
        help="Detect sample rate (default 2.0; frame step = round(src_fps / detect_fps))",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write machine-readable results JSON",
    )
    args = parser.parse_args()

    video_dir = _resolve_video_dir(args.video_dir)
    if not video_dir.is_dir():
        print(
            f"card_long dir not found: {video_dir}\n"
            "Full-video replay needs master MKVs on disk. "
            "ROI-fixture CI is a later layer (docs/ACCURACY_HISTORY.md).",
            file=sys.stderr,
        )
        return 1

    videos = sorted(video_dir.glob("*.mkv")) + sorted(video_dir.glob("*.mp4"))
    if args.only:
        videos = [
            v
            for v in videos
            if any(token in v.name for token in args.only)
        ]
    # Prefer known GT masters first; still allow unknown files.
    known = [v for v in videos if _dataset_id_for(v) in CARD_LONG_GT]
    unknown = [v for v in videos if v not in known]
    videos = known + unknown
    if not videos:
        print(f"no videos in {video_dir}", file=sys.stderr)
        return 1

    print(
        f"layer=full_video video_dir={video_dir} detect_fps={args.detect_fps} "
        f"n={len(videos)}"
    )
    print(
        f"{'id':<22} {'exact':>7} {'gate w/x/m':>12}  writes"
    )

    rows: list[dict[str, Any]] = []
    total_exact = 0
    total_expected = 0
    for path in videos:
        row = replay_video(path, detect_fps=args.detect_fps)
        rows.append(row)
        ds = row.get("dataset_id") or path.stem
        score = row.get("score")
        if score:
            total_exact += int(score["exact"])
            total_expected += int(score["expected"])
            print(
                f"{ds:<22} {score['exact_str']:>7} {score['gate_str']:>12}  "
                f"{score['writes']}"
            )
        else:
            print(f"{ds:<22} {'—':>7} {'—':>12}  {row['writes']}")

    if total_expected:
        print(f"overall exact {total_exact}/{total_expected}")

    payload = {
        "layer": "full_video",
        "video_dir": str(video_dir),
        "detect_fps": args.detect_fps,
        "overall_exact": f"{total_exact}/{total_expected}" if total_expected else None,
        "videos": rows,
        "note": (
            "Full-video / card_long harness. ROI-fixture CI scoring is a later "
            "layer — not run by this script."
        ),
    }
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
