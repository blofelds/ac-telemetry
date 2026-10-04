#!/usr/bin/env python3
"""Offline last_lap gate proof on card-native MJPEG clips.

Replays each clip through the same template reader + DetectService._handle_reading
path as live (ROI / templates / threshold from config). Compares:

  before  — min_lap_ms=30000, last_lap_stable_ms=0   (#24 / main)
  after   — min_lap_ms=30000, last_lap_stable_ms=3000 (#25)

Card clips in this stint are only ~0.6–3s long, so raw PTS replay cannot show
mid-lap extras after the 30s gate re-opens. Pass --pad-midlap to hold the
dominant OCR value out past 85s and inject a brief flicker variant taken from
the clip's own OCR (session-like stress). Session CSV timing for 6aea35251c54
is covered by tests/test_lap_times.py + the JSON fixture.

Usage (from repo root, venv active):

  python scripts/replay_last_lap_clips.py
  python scripts/replay_last_lap_clips.py --pad-midlap
  python scripts/replay_last_lap_clips.py \\
      --card-dir ~/ac-telemetry-testdata/pi-stint-20261004/card
"""

from __future__ import annotations

import argparse
import json
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

DEFAULT_CARD = Path.home() / "ac-telemetry-testdata/pi-stint-20261004/card"


def _make_service(
    min_lap_ms: int, last_lap_stable_ms: int
) -> tuple[DetectService, list[dict[str, Any]]]:
    settings = load_settings()
    settings.detect.enabled = True
    settings.detect.debounce_reads = 2
    settings.detect.lap_time.reader = "template"
    settings.detect.lap_time.mode = "last_lap"
    settings.detect.lap_time.min_lap_ms = min_lap_ms
    settings.detect.lap_time.last_lap_stable_ms = last_lap_stable_ms
    settings.detect.lap_time.templates_dir = "templates/lap_time_digits/ac_720p_pi"
    settings.detect.lap_time.match_threshold = 0.50
    settings.detect.debug_dump.enabled = False
    recorded: list[dict[str, Any]] = []

    def _append(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        recorded.append(out)
        return out

    detect = DetectService(
        settings=settings,
        get_frame=lambda: None,
        get_session_id=lambda: "replay",
        record_lap=_append,
    )
    detect.state.enabled = True
    detect.state.reader = "template"
    detect.state.mode = "last_lap"
    detect._reader = build_lap_time_reader(
        "template",
        templates_dir=settings.detect.lap_time.templates_dir,
        match_threshold=0.50,
    )
    return detect, recorded


def _reading(ms: int | None) -> LapTimeReading:
    if ms is None:
        return LapTimeReading(ok=False, error="no read")
    return LapTimeReading(ok=True, text=format_lap_time_ms(ms), lap_time_ms=ms)


def _extract_ocr(clip: Path) -> tuple[list[tuple[float, int | None]], float]:
    settings = load_settings()
    cap = cv2.VideoCapture(str(clip))
    src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    roi = settings.rois["lap_time"]
    reader = build_lap_time_reader(
        "template",
        templates_dir="templates/lap_time_digits/ac_720p_pi",
        match_threshold=0.50,
    )
    seq: list[tuple[float, int | None]] = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        reading = reader.read(crop_roi(frame, roi))
        seq.append((idx / src_fps, reading.lap_time_ms if reading.ok else None))
        idx += 1
    cap.release()
    return seq, src_fps


def _sample_detect(
    seq: list[tuple[float, int | None]], src_fps: float, detect_fps: float = 2.0
) -> list[tuple[float, int | None]]:
    step = max(1, int(round(src_fps / detect_fps)))
    return [seq[i] for i in range(0, len(seq), step)]


def _dominant(seq: list[tuple[float, int | None]]) -> int | None:
    vals = [ms for _, ms in seq if ms is not None]
    if not vals:
        return None
    filtered = [v for v in vals if v < 480_000]
    pool = filtered or vals
    return Counter(pool).most_common(1)[0][0]


def _variants(seq: list[tuple[float, int | None]], dominant: int) -> list[int]:
    return sorted(
        {
            ms
            for _, ms in seq
            if ms is not None and ms != dominant and abs(ms - dominant) <= 500
        }
    )


def _pad_midlap(
    events: list[tuple[float, int | None]],
    seq: list[tuple[float, int | None]],
    pad_to: float = 90.0,
) -> tuple[list[tuple[float, int | None]], int | None, list[int]]:
    dominant = _dominant(seq)
    if dominant is None:
        return events, None, []
    variants = _variants(seq, dominant)
    out = list(events)
    t = out[-1][0] if out else 0.0
    hold_end = pad_to - 5.0
    while t < hold_end:
        t += 0.5
        out.append((t, dominant))
    if variants:
        flicker_t = max(t + 0.5, 85.0)
        alt = variants[0]
        for i in range(4):
            out.append((flicker_t + i * 0.5, alt))
        for i in range(6):
            out.append((flicker_t + 2.0 + i * 0.5, dominant))
    return out, dominant, variants


def _replay(
    events: list[tuple[float, int | None]], min_lap_ms: int, last_lap_stable_ms: int
) -> list[str]:
    detect, recorded = _make_service(min_lap_ms, last_lap_stable_ms)
    mono = {"t": 0.0}
    real = time.monotonic
    time.monotonic = lambda: mono["t"]  # type: ignore[assignment]
    try:
        for t, ms in events:
            mono["t"] = t
            detect._handle_reading(detect.settings.detect, _reading(ms), 0.01)
    finally:
        time.monotonic = real  # type: ignore[assignment]
    return [str(r["lap_time"]) for r in recorded]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--card-dir",
        type=Path,
        default=DEFAULT_CARD,
        help=f"Directory of *_card_1280x720.mjpeg (default: {DEFAULT_CARD})",
    )
    parser.add_argument(
        "--pad-midlap",
        action="store_true",
        help="Hold dominant OCR past 85s and inject brief clip-derived flicker",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write machine-readable results",
    )
    args = parser.parse_args()
    card_dir: Path = args.card_dir
    if not card_dir.is_dir():
        print(f"card dir not found: {card_dir}", file=sys.stderr)
        return 1

    clips = sorted(card_dir.glob("20261004-*_card_1280x720.mjpeg"))
    if not clips:
        clips = sorted(card_dir.glob("*_card_1280x720.mjpeg"))
    if not clips:
        print(f"no card MJPEG clips in {card_dir}", file=sys.stderr)
        return 1

    rows: list[dict[str, Any]] = []
    mode = "pad_midlap" if args.pad_midlap else "raw_pts"
    print(f"mode={mode} card_dir={card_dir}")
    print(
        f"{'clip':<42} {'dur':>6} {'#24 n':>5} {'#25 n':>5}  before → after"
    )
    for clip in clips:
        seq, src_fps = _extract_ocr(clip)
        events = _sample_detect(seq, src_fps, 2.0)
        dur = seq[-1][0] if seq else 0.0
        variants: list[int] = []
        dominant: int | None = None
        if args.pad_midlap:
            events, dominant, variants = _pad_midlap(events, seq)
        before = _replay(events, 30_000, 0)
        after = _replay(events, 30_000, 3_000)
        rows.append(
            {
                "clip": clip.name,
                "duration_s": round(dur, 3),
                "mode": mode,
                "dominant": format_lap_time_ms(dominant) if dominant else None,
                "variants": [format_lap_time_ms(v) for v in variants],
                "before_24": before,
                "after_25": after,
            }
        )
        print(
            f"{clip.name:<42} {dur:6.2f} {len(before):5d} {len(after):5d}  "
            f"{before} → {after}"
        )

    if args.json_out:
        args.json_out.write_text(json.dumps(rows, indent=2) + "\n")
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
