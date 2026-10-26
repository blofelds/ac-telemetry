"""GT alignment + write% / ocr-sample% reports for every lap.

write%     = exact CSV LAST matches / scoring GT laps (extras & misses separate)
ocr-sample%= samples equal to that lap's GT in the hold window / samples
             in window (also rolled up stint-wide)

Operator marks on GT rows:
  normal — true on-screen lap that should match a CSV write (default)
  double — false extra CSV write; annotated but excluded from write% denom/num
  skip   — on-screen lap with no CSV write; counts as a miss (denom only)

Every GT lap gets a review row (ROI frames, OCR histogram, CSV write) —
not only mismatches. Mismatches are flagged visually in Markdown.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ac_telemetry.accuracy.ocr_log import OcrSampleLog
from ac_telemetry.accuracy.paths import (
    gt_path,
    ocr_samples_path,
    review_md_path,
    roi_manifest_path,
    score_json_path,
    score_md_path,
    session_dir,
)
from ac_telemetry.detect.readers import format_lap_time_ms, parse_lap_time_text
from ac_telemetry.store.laps import LapStore

logger = logging.getLogger(__name__)

# Per-row operator marks (persisted on gt.json / gt_draft.json).
MARK_NORMAL = "normal"
MARK_DOUBLE = "double"
MARK_SKIP = "skip"
VALID_MARKS = frozenset({MARK_NORMAL, MARK_DOUBLE, MARK_SKIP})


def normalize_mark(value: Any) -> str:
    """Normalize operator mark to normal | double | skip."""
    raw = str(value or MARK_NORMAL).strip().lower()
    if raw in ("double", "dbl", "extra", "false_extra"):
        return MARK_DOUBLE
    if raw in ("skip", "miss", "missing", "no_csv"):
        return MARK_SKIP
    if raw in ("normal", "ok", "match_target", ""):
        return MARK_NORMAL
    if raw in VALID_MARKS:
        return raw
    return MARK_NORMAL


def normalize_lap_text(text: str | None) -> str | None:
    """Normalize operator/CSV/OCR text to ``M:SS.mmm`` or None."""
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    parsed = parse_lap_time_text(raw)
    if parsed is None:
        return None
    return parsed[0]


def normalize_lap_ms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        ms = int(value)
    except (TypeError, ValueError):
        text = normalize_lap_text(str(value))
        if text is None:
            return None
        parsed = parse_lap_time_text(text)
        return None if parsed is None else parsed[1]
    if ms <= 0:
        return None
    return ms


def load_gt_list(raw: Any) -> list[dict[str, Any]]:
    """Accept list of strings/ms/dicts → normalized GT rows.

    Dict items may include ``mark`` (normal|double|skip) and optional
    ``csv_lap_number`` (needed so doubles can consume their CSV write).
    """
    if isinstance(raw, dict) and "laps" in raw:
        raw = raw["laps"]
    if not isinstance(raw, list):
        raise ValueError("GT must be a list of lap times (or {laps: [...]})")
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw, start=1):
        csv_lap_number: Any = None
        if isinstance(item, dict):
            text = normalize_lap_text(
                item.get("lap_time") or item.get("text") or item.get("time")
            )
            ms = normalize_lap_ms(item.get("lap_time_ms") or item.get("ms"))
            note = str(item.get("note") or "")
            mark = normalize_mark(item.get("mark") or item.get("status"))
            csv_lap_number = item.get("csv_lap_number")
            if text is None and ms is not None:
                text = format_lap_time_ms(ms)
            if ms is None and text is not None:
                parsed = parse_lap_time_text(text)
                ms = None if parsed is None else parsed[1]
        elif isinstance(item, (int, float)):
            ms = normalize_lap_ms(item)
            text = format_lap_time_ms(ms) if ms is not None else None
            note = ""
            mark = MARK_NORMAL
        else:
            text = normalize_lap_text(str(item))
            ms = None
            if text is not None:
                parsed = parse_lap_time_text(text)
                ms = None if parsed is None else parsed[1]
            note = ""
            mark = MARK_NORMAL
        if text is None or ms is None:
            raise ValueError(f"GT lap #{i} is not a valid lap time: {item!r}")
        row: dict[str, Any] = {
            "gt_index": i,
            "lap_time": text,
            "lap_time_ms": ms,
            "note": note,
            "mark": mark,
        }
        if csv_lap_number is not None and str(csv_lap_number).strip() != "":
            row["csv_lap_number"] = csv_lap_number
        out.append(row)
    return out


def prefills_from_csv(laps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a GT draft from CSV rows (operator confirms/edits)."""
    # CSV list_laps is newest-first; GT order is chronological.
    chronological = list(reversed(laps))
    draft: list[dict[str, Any]] = []
    for i, row in enumerate(chronological, start=1):
        text = normalize_lap_text(row.get("lap_time") or row.get("raw_text"))
        ms = normalize_lap_ms(row.get("lap_time_ms"))
        if text is None and ms is not None:
            text = format_lap_time_ms(ms)
        if ms is None and text is not None:
            parsed = parse_lap_time_text(text)
            ms = None if parsed is None else parsed[1]
        if text is None or ms is None:
            continue
        draft.append(
            {
                "gt_index": i,
                "lap_time": text,
                "lap_time_ms": ms,
                "note": "prefill from CSV — confirm/edit",
                "mark": MARK_NORMAL,
                "csv_lap_number": row.get("lap_number"),
                "csv_recorded_at": row.get("recorded_at"),
            }
        )
    return draft


def scoring_gt_laps(gt_laps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """GT rows that count toward write% (excludes doubles)."""
    return [g for g in gt_laps if normalize_mark(g.get("mark")) != MARK_DOUBLE]


def double_gt_laps(gt_laps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [g for g in gt_laps if normalize_mark(g.get("mark")) == MARK_DOUBLE]


def _csv_lap_number_key(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _consume_double_csv_indices(
    doubles: list[dict[str, Any]],
    csv_chrono: list[tuple[int, dict[str, Any]]],
) -> set[int]:
    """CSV indices claimed by double marks (not extras, not match targets)."""
    used: set[int] = set()
    by_number: dict[str, int] = {}
    for j, (_ci, row) in enumerate(csv_chrono):
        key = _csv_lap_number_key(row.get("lap_number"))
        if key is not None and key not in by_number:
            by_number[key] = j

    for gt in doubles:
        key = _csv_lap_number_key(gt.get("csv_lap_number"))
        if key is not None and key in by_number:
            used.add(by_number[key])
            continue
        # Fall back: next unused CSV row whose text matches the double time.
        gt_text = gt.get("lap_time")
        for j, (_ci, row) in enumerate(csv_chrono):
            if j in used:
                continue
            row_text = normalize_lap_text(row.get("lap_time") or row.get("raw_text"))
            if row_text == gt_text:
                used.add(j)
                break
    return used


def align_csv_to_gt(
    gt_laps: list[dict[str, Any]],
    csv_laps: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Sequential exact-match alignment with double/skip marks.

    Returns (matches, misses, extras, doubles_annotated).
    matches: {gt, csv, gt_index, csv_index} for scoring GT (normal + skip)
    misses: scoring GT rows with no CSV exact match (includes skips)
    extras: CSV rows not consumed by a match or a double mark
    doubles_annotated: double-marked GT rows (excluded from write%)
    """
    # Chronological CSV (oldest first).
    csv_chrono: list[tuple[int, dict[str, Any]]] = []
    for idx, row in enumerate(reversed(csv_laps)):
        csv_chrono.append((idx, row))

    doubles = double_gt_laps(gt_laps)
    targets = scoring_gt_laps(gt_laps)
    used_csv: set[int] = _consume_double_csv_indices(doubles, csv_chrono)

    matches: list[dict[str, Any]] = []
    misses: list[dict[str, Any]] = []
    csv_i = 0

    for gt in targets:
        mark = normalize_mark(gt.get("mark"))
        # Skip = on-screen lap with no CSV write → always counts as a miss.
        if mark == MARK_SKIP:
            misses.append(dict(gt))
            continue
        gt_text = gt["lap_time"]
        found = None
        for j in range(csv_i, len(csv_chrono)):
            if j in used_csv:
                continue
            _ci, row = csv_chrono[j]
            row_text = normalize_lap_text(row.get("lap_time") or row.get("raw_text"))
            if row_text == gt_text:
                found = j
                break
        if found is None:
            misses.append(dict(gt))
            continue
        _ci, row = csv_chrono[found]
        used_csv.add(found)
        matches.append(
            {
                "gt": gt,
                "csv": row,
                "gt_index": gt["gt_index"],
                "csv_index": found,
            }
        )
        csv_i = found + 1

    extras: list[dict[str, Any]] = []
    for j, (_ci, row) in enumerate(csv_chrono):
        if j not in used_csv:
            extras.append(row)

    doubles_annotated = [dict(g) for g in doubles]
    return matches, misses, extras, doubles_annotated


def _parse_recorded_at(value: str | None) -> float | None:
    if not value:
        return None
    try:
        # Accept ISO with/without Z.
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _sample_windows(
    gt_laps: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    samples: list[dict[str, Any]],
) -> dict[int, tuple[float, float]]:
    """Per GT index → (wall_start, wall_end) for OCR hold window.

    Matched laps: from previous match write (or first sample) to this write.
    Misses: gap between neighboring match windows (or full span fallback).
    """
    if not samples:
        return {}

    sample_walls = [float(s["wall_s"]) for s in samples if "wall_s" in s]
    if not sample_walls:
        return {}
    span_start = min(sample_walls)
    span_end = max(sample_walls) + 1e-3

    match_by_gt = {m["gt_index"]: m for m in matches}
    write_times: dict[int, float] = {}
    for gt_index, m in match_by_gt.items():
        wall = _parse_recorded_at(m["csv"].get("recorded_at"))
        if wall is None:
            # Fall back: first sample whose text equals GT near end of stream.
            gt_text = m["gt"]["lap_time"]
            for s in samples:
                if normalize_lap_text(s.get("text")) == gt_text and s.get("ok", True):
                    wall = float(s["wall_s"])
            if wall is None:
                continue
        write_times[gt_index] = wall

    # Ordered GT indices with known write times.
    ordered_writes = sorted(write_times.items(), key=lambda kv: kv[1])
    windows: dict[int, tuple[float, float]] = {}

    for i, gt in enumerate(gt_laps):
        gi = gt["gt_index"]
        if gi in write_times:
            # Start: previous write time, else span_start.
            prev_wall = span_start
            for pj, pw in ordered_writes:
                if pw < write_times[gi]:
                    prev_wall = pw
                else:
                    break
            # Small epsilon so previous write sample is excluded.
            start = prev_wall + 1e-6 if prev_wall > span_start else span_start
            end = write_times[gi] + 0.05  # include samples around CSV write
            windows[gi] = (start, end)
        else:
            # Miss: place between neighboring known writes.
            prev_end = span_start
            next_start = span_end
            earlier = [w for g, w in ordered_writes if g < gi]
            later = [w for g, w in ordered_writes if g > gi]
            if earlier:
                prev_end = earlier[-1] + 1e-6
            if later:
                next_start = later[0]
            # If no neighbors, use equal slices of the full span.
            if not earlier and not later and gt_laps:
                slice_len = (span_end - span_start) / max(1, len(gt_laps))
                start = span_start + (i * slice_len)
                end = start + slice_len
                windows[gi] = (start, end)
            else:
                windows[gi] = (prev_end, next_start)

    return windows


def _histogram(texts: list[str]) -> list[dict[str, Any]]:
    counts = Counter(texts)
    return [
        {"text": text, "count": count}
        for text, count in counts.most_common()
    ]


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def score_session(
    *,
    data_dir: Path,
    session_id: str,
    gt_laps: list[dict[str, Any]],
    subdir: str = "accuracy",
    lap_store: LapStore | None = None,
) -> dict[str, Any]:
    """Compute write%/ocr-sample% and every-lap review; write JSON+Markdown."""
    sdir = session_dir(data_dir, session_id, subdir=subdir)
    sdir.mkdir(parents=True, exist_ok=True)

    store = lap_store or LapStore(data_dir)
    csv_laps = store.list_laps(session_id=session_id, limit=500)
    samples = OcrSampleLog.read_all(ocr_samples_path(sdir))
    manifest = _load_manifest(roi_manifest_path(sdir))

    matches, misses, extras, doubles_annotated = align_csv_to_gt(gt_laps, csv_laps)
    scoring = scoring_gt_laps(gt_laps)
    gt_n = len(scoring)  # write% denominator excludes doubles
    match_n = len(matches)
    write_pct = (100.0 * match_n / gt_n) if gt_n else 0.0

    # OCR windows only for scoring targets (doubles are annotated separately).
    windows = _sample_windows(scoring, matches, samples)
    match_by_gt = {m["gt_index"]: m for m in matches}

    # Resolve CSV row for doubles (annotation only).
    csv_chrono = list(reversed(csv_laps))
    csv_by_number: dict[str, dict[str, Any]] = {}
    for row in csv_chrono:
        key = _csv_lap_number_key(row.get("lap_number"))
        if key is not None and key not in csv_by_number:
            csv_by_number[key] = row

    per_lap: list[dict[str, Any]] = []
    stint_equal = 0
    stint_total = 0

    for gt in gt_laps:
        gi = gt["gt_index"]
        gt_text = gt["lap_time"]
        mark = normalize_mark(gt.get("mark"))
        matched = gi in match_by_gt
        csv_row = match_by_gt[gi]["csv"] if matched else None
        if mark == MARK_DOUBLE and csv_row is None:
            key = _csv_lap_number_key(gt.get("csv_lap_number"))
            if key is not None:
                csv_row = csv_by_number.get(key)
            if csv_row is None:
                # Text-match fallback for annotation.
                for row in csv_chrono:
                    if normalize_lap_text(row.get("lap_time") or row.get("raw_text")) == gt_text:
                        csv_row = row
                        break

        win = windows.get(gi) if mark != MARK_DOUBLE else None
        win_samples = []
        if win is not None:
            start, end = win
            win_samples = [
                s
                for s in samples
                if s.get("ok", True)
                and "wall_s" in s
                and start <= float(s["wall_s"]) <= end
                and normalize_lap_text(s.get("text")) is not None
            ]
        equal = [
            s
            for s in win_samples
            if normalize_lap_text(s.get("text")) == gt_text
        ]
        total = len(win_samples)
        eq = len(equal)
        if mark != MARK_DOUBLE:
            stint_equal += eq
            stint_total += total
        ocr_pct = (100.0 * eq / total) if total else None

        texts = [
            t
            for t in (normalize_lap_text(s.get("text")) for s in win_samples)
            if t is not None
        ]
        hist = _histogram(texts)

        roi_frames: list[dict[str, Any]] = []
        if win is not None:
            start, end = win
            for row in manifest:
                if "wall_s" not in row:
                    continue
                if start <= float(row["wall_s"]) <= end:
                    roi_frames.append(
                        {
                            "seq": row.get("seq"),
                            "path": row.get("path"),
                            "text": row.get("text"),
                            "wall_s": row.get("wall_s"),
                            "mono_s": row.get("mono_s"),
                        }
                    )

        if mark == MARK_DOUBLE:
            status = "double"
        elif mark == MARK_SKIP:
            status = "skip"
        elif matched:
            status = "match"
        else:
            status = "miss"
        csv_text = None
        if csv_row is not None:
            csv_text = normalize_lap_text(
                csv_row.get("lap_time") or csv_row.get("raw_text")
            )
            if mark == MARK_NORMAL and csv_text != gt_text:
                status = "mismatch"

        per_lap.append(
            {
                "gt_index": gi,
                "gt_lap_time": gt_text,
                "gt_lap_time_ms": gt["lap_time_ms"],
                "mark": mark,
                "status": status,
                "csv_lap_time": csv_text,
                "csv_lap_number": (
                    gt.get("csv_lap_number")
                    if csv_row is None
                    else csv_row.get("lap_number")
                ),
                "csv_recorded_at": None
                if csv_row is None
                else csv_row.get("recorded_at"),
                "ocr_sample_equal": eq,
                "ocr_sample_total": total,
                "ocr_sample_pct": None if ocr_pct is None else round(ocr_pct, 2),
                "ocr_histogram": hist,
                "roi_frame_count": len(roi_frames),
                "roi_frames": roi_frames[:40],  # cap JSON size; full list in review.md
                "window_wall_s": None if win is None else [round(win[0], 3), round(win[1], 3)],
                "note": gt.get("note") or "",
            }
        )

    stint_ocr_pct = (100.0 * stint_equal / stint_total) if stint_total else None

    report: dict[str, Any] = {
        "session_id": session_id,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "gt_laps": gt_n,
        "gt_laps_total": len(gt_laps),
        "gt_doubles": len(doubles_annotated),
        "gt_skips": sum(
            1 for g in gt_laps if normalize_mark(g.get("mark")) == MARK_SKIP
        ),
        "csv_laps": len(csv_laps),
        "write_matches": match_n,
        "write_misses": len(misses),
        "write_extras": len(extras),
        "write_doubles": len(doubles_annotated),
        "write_pct": round(write_pct, 2),
        "ocr_sample_equal": stint_equal,
        "ocr_sample_total": stint_total,
        "ocr_sample_pct": None if stint_ocr_pct is None else round(stint_ocr_pct, 2),
        "extras": [
            {
                "lap_number": r.get("lap_number"),
                "lap_time": normalize_lap_text(r.get("lap_time")),
                "recorded_at": r.get("recorded_at"),
            }
            for r in extras
        ],
        "misses": [
            {
                "gt_index": m["gt_index"],
                "lap_time": m["lap_time"],
                "mark": normalize_mark(m.get("mark")),
            }
            for m in misses
        ],
        "doubles": [
            {
                "gt_index": d["gt_index"],
                "lap_time": d["lap_time"],
                "csv_lap_number": d.get("csv_lap_number"),
            }
            for d in doubles_annotated
        ],
        "per_lap": per_lap,
        "artefact_dir": str(sdir),
    }

    # Persist GT + scores.
    gt_path(sdir).write_text(
        json.dumps({"session_id": session_id, "laps": gt_laps}, indent=2) + "\n",
        encoding="utf-8",
    )
    score_json_path(sdir).write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    md = render_score_markdown(report)
    score_md_path(sdir).write_text(md, encoding="utf-8")
    review_md_path(sdir).write_text(render_review_markdown(report, sdir), encoding="utf-8")
    return report


def render_score_markdown(report: dict[str, Any]) -> str:
    doubles_n = report.get("write_doubles", report.get("gt_doubles", 0))
    skips_n = report.get("gt_skips", 0)
    lines = [
        f"# Stint accuracy — `{report['session_id']}`",
        "",
        f"- **write%**: {report['write_pct']}% "
        f"({report['write_matches']}/{report['gt_laps']} exact CSV matches; "
        f"denom excludes doubles)",
        f"- **ocr-sample%**: "
        f"{report['ocr_sample_pct'] if report['ocr_sample_pct'] is not None else 'n/a'}% "
        f"({report['ocr_sample_equal']}/{report['ocr_sample_total']} samples)",
        f"- misses: {report['write_misses']} · extras: {report['write_extras']} "
        f"· doubles: {doubles_n} · skips: {skips_n}",
        f"- artefacts: `{report['artefact_dir']}`",
        "",
        "| GT# | GT | mark | CSV | status | ocr% | ROI frames |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for lap in report["per_lap"]:
        flag = {
            "match": "✓",
            "miss": "❌ miss",
            "mismatch": "❌ mismatch",
            "double": "◎ double",
            "skip": "○ skip",
        }.get(lap["status"], lap["status"])
        ocr = (
            "n/a"
            if lap["ocr_sample_pct"] is None
            else f"{lap['ocr_sample_pct']}% ({lap['ocr_sample_equal']}/{lap['ocr_sample_total']})"
        )
        mark = lap.get("mark") or "normal"
        lines.append(
            f"| {lap['gt_index']} | {lap['gt_lap_time']} | {mark} | "
            f"{lap['csv_lap_time'] or '—'} | {flag} | {ocr} | "
            f"{lap['roi_frame_count']} |"
        )
    lines.append("")
    if report.get("doubles"):
        lines.append("## Doubles (false extra CSV — excluded from write%)")
        lines.append("")
        for d in report["doubles"]:
            lines.append(
                f"- GT #{d.get('gt_index')} time={d.get('lap_time')} "
                f"csv_lap_number={d.get('csv_lap_number')}"
            )
        lines.append("")
    if report["extras"]:
        lines.append("## Extras (CSV without GT match)")
        lines.append("")
        for ex in report["extras"]:
            lines.append(
                f"- lap_number={ex.get('lap_number')} "
                f"time={ex.get('lap_time')} at {ex.get('recorded_at')}"
            )
        lines.append("")
    lines.append("See `review.md` for every-lap OCR histograms and ROI paths.")
    lines.append("")
    return "\n".join(lines)


def render_review_markdown(report: dict[str, Any], sdir: Path) -> str:
    """Per-lap review for *every* GT lap (target >99% means inspect all)."""
    lines = [
        f"# Every-lap review — `{report['session_id']}`",
        "",
        "Inspect **every** GT lap (not only failures). Mismatches marked ❌.",
        "Doubles (◎) are annotated false extras; skips (○) are GT without CSV.",
        "",
    ]
    for lap in report["per_lap"]:
        if lap["status"] == "match":
            flag = "✓"
        elif lap["status"] == "double":
            flag = "◎"
        elif lap["status"] == "skip":
            flag = "○"
        else:
            flag = "❌"
        mark = lap.get("mark") or "normal"
        lines.append(f"## {flag} GT #{lap['gt_index']}: `{lap['gt_lap_time']}`")
        lines.append("")
        lines.append(f"- mark: **{mark}** · status: **{lap['status']}**")
        lines.append(
            f"- CSV write: `{lap['csv_lap_time'] or '—'}` "
            f"(lap_number={lap['csv_lap_number']}, at {lap['csv_recorded_at']})"
        )
        ocr = (
            "n/a (no samples in window)"
            if lap["ocr_sample_pct"] is None
            else f"{lap['ocr_sample_pct']}% "
            f"({lap['ocr_sample_equal']}/{lap['ocr_sample_total']})"
        )
        lines.append(f"- ocr-sample%: {ocr}")
        if lap.get("window_wall_s"):
            lines.append(f"- window wall_s: {lap['window_wall_s']}")
        lines.append("- OCR histogram:")
        if not lap["ocr_histogram"]:
            lines.append("  - _(empty)_")
        else:
            for row in lap["ocr_histogram"]:
                mark = " ← GT" if row["text"] == lap["gt_lap_time"] else ""
                lines.append(f"  - `{row['text']}` × {row['count']}{mark}")
        lines.append(f"- ROI frames in window: {lap['roi_frame_count']}")
        # Prefer full manifest slice from disk for review (not capped JSON).
        frames = lap.get("roi_frames") or []
        for fr in frames[:60]:
            rel = fr.get("path") or ""
            abs_path = sdir / rel if rel and not Path(rel).is_absolute() else Path(rel)
            lines.append(
                f"  - seq={fr.get('seq')} text=`{fr.get('text')}` "
                f"`{abs_path}`"
            )
        if lap["roi_frame_count"] > 60:
            lines.append(f"  - … +{lap['roi_frame_count'] - 60} more (see roi_manifest.jsonl)")
        lines.append("")
    return "\n".join(lines)


def save_gt(
    *,
    data_dir: Path,
    session_id: str,
    gt_laps: list[dict[str, Any]],
    subdir: str = "accuracy",
) -> Path:
    sdir = session_dir(data_dir, session_id, subdir=subdir)
    sdir.mkdir(parents=True, exist_ok=True)
    path = gt_path(sdir)
    path.write_text(
        json.dumps({"session_id": session_id, "laps": gt_laps}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
