"""GT eyeballing helper — page data, crop pick, confirm → gt + stint CSV."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ac_telemetry.accuracy.paths import (
    gt_draft_path,
    gt_path,
    roi_manifest_path,
    session_dir,
)
from ac_telemetry.accuracy.score import (
    MARK_DOUBLE,
    MARK_NORMAL,
    MARK_SKIP,
    load_gt_list,
    normalize_lap_text,
    normalize_mark,
    prefills_from_csv,
    save_gt,
    score_session,
)
from ac_telemetry.store.laps import LapStore

logger = logging.getLogger(__name__)

# Written onto CSV lap rows when Confirm succeeds (doubles use GT_DOUBLE_NOTE).
GT_CONFIRMED_NOTE = "gt_confirmed"
GT_DOUBLE_NOTE = "gt_double"

# CSV notes that mean the helper (or an equivalent confirm) has stamped the stint.
_GT_CONFIRMED_CSV_NOTES = frozenset({GT_CONFIRMED_NOTE, GT_DOUBLE_NOTE})


def select_display_crops(
    frames: list[dict[str, Any]], *, max_display: int = 2
) -> list[dict[str, Any]]:
    """Pick up to ``max_display`` tee frames for the helper UI.

    With the default hold cap of 3 (first/middle/last), show **first + last**.
    When fewer frames exist, return all of them (e.g. first+middle).
    """
    if max_display <= 0 or not frames:
        return []
    if len(frames) <= max_display:
        return list(frames)
    if max_display == 1:
        return [frames[0]]
    # first + last (skip middle when three exist)
    return [frames[0], frames[-1]]


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


def group_hold_frames(manifest: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group consecutive manifest rows that share the same OCR text hold."""
    holds: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_key: str | None = None
    for row in manifest:
        text = (row.get("text") or "").strip()
        key = f"t:{text}" if text else f"empty:{row.get('seq')}"
        if current_key is None:
            current_key = key
            current = [row]
            continue
        if key == current_key and text:
            current.append(row)
        else:
            if current:
                holds.append(current)
            current_key = key
            current = [row]
    if current:
        holds.append(current)
    return holds


def _crop_url(session_id: str, rel_path: str | None) -> str | None:
    if not rel_path:
        return None
    name = Path(str(rel_path)).name
    if not name or name in (".", ".."):
        return None
    return f"/api/accuracy/sessions/{session_id}/roi/{name}"


def _match_holds_to_laps(
    laps: list[dict[str, Any]],
    holds: list[list[dict[str, Any]]],
) -> list[list[dict[str, Any]]]:
    """Pair each lap with the next unused hold whose OCR text matches."""
    unused = list(holds)
    out: list[list[dict[str, Any]]] = []
    for lap in laps:
        gt_text = normalize_lap_text(lap.get("lap_time"))
        chosen: list[dict[str, Any]] = []
        if gt_text is not None:
            for i, hold in enumerate(unused):
                hold_text = normalize_lap_text((hold[0].get("text") if hold else None))
                if hold_text == gt_text:
                    chosen = hold
                    del unused[i]
                    break
        out.append(chosen)
    return out


def _load_saved_gt_laps(sdir: Path) -> list[dict[str, Any]]:
    """Prefer gt_draft.json, else gt.json — empty if neither exists."""
    for path in (gt_draft_path(sdir), gt_path(sdir)):
        if not path.is_file():
            continue
        try:
            return load_gt_list(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, json.JSONDecodeError):
            logger.warning("Ignoring invalid GT file at %s", path)
    return []


def _csv_has_gt_confirmed_note(
    lap_store: LapStore | None, session_id: str
) -> bool:
    """True when any laps.csv row for the session carries a confirm note."""
    if lap_store is None:
        return False
    for row in lap_store.list_laps(session_id=session_id, limit=500):
        note = str(row.get("note") or "").strip()
        if note in _GT_CONFIRMED_CSV_NOTES:
            return True
    return False


def detect_gt_confirmed(
    *,
    data_dir: Path,
    session_id: str,
    lap_store: LapStore | None = None,
    subdir: str = "accuracy",
) -> dict[str, Any]:
    """Whether this session already has confirmed GT (Confirm / gt artefacts).

    Confirmed when any of:
    - ``gt.json`` exists under the accuracy session dir
    - ``gt_draft.json`` exists (helper Confirm draft)
    - any ``laps.csv`` row has ``note=gt_confirmed`` (or ``gt_double``)

    Returns ``gt_confirmed`` plus the matching ``via`` reasons so the helper
    UI can show a clear badge without re-deriving the rules in JS.
    """
    sdir = session_dir(data_dir, session_id, subdir=subdir)
    via: list[str] = []
    if gt_path(sdir).is_file():
        via.append("gt.json")
    if gt_draft_path(sdir).is_file():
        via.append("gt_draft.json")
    if _csv_has_gt_confirmed_note(lap_store, session_id):
        via.append("laps.csv")
    return {
        "session_id": session_id,
        "gt_confirmed": bool(via),
        "via": via,
    }


def list_gt_confirmed_status(
    *,
    data_dir: Path,
    session_ids: list[str],
    lap_store: LapStore | None = None,
    subdir: str = "accuracy",
) -> dict[str, dict[str, Any]]:
    """Map session_id → detect_gt_confirmed result (for the helper session list)."""
    out: dict[str, dict[str, Any]] = {}
    for sid in session_ids:
        sid_s = str(sid or "").strip()
        if not sid_s:
            continue
        out[sid_s] = detect_gt_confirmed(
            data_dir=data_dir,
            session_id=sid_s,
            lap_store=lap_store,
            subdir=subdir,
        )
    return out


def _merge_saved_marks(
    draft_laps: list[dict[str, Any]],
    saved: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rebuild page laps in saved GT order, attaching CSV prefill metadata.

    Preserves skip positions between CSV-backed rows. Any new CSV rows not
    referenced in the saved GT are appended at the end as normal.
    """
    if not saved:
        return draft_laps

    by_csv: dict[str, dict[str, Any]] = {}
    for lap in draft_laps:
        key = lap.get("csv_lap_number")
        key_s = str(key).strip() if key is not None else ""
        if key_s and key_s not in by_csv:
            by_csv[key_s] = lap

    used_csv: set[str] = set()
    merged: list[dict[str, Any]] = []
    for row in saved:
        mark = normalize_mark(row.get("mark"))
        key = row.get("csv_lap_number")
        key_s = str(key).strip() if key is not None else ""
        if key_s and key_s in by_csv:
            out = dict(by_csv[key_s])
            out["mark"] = mark
            out["lap_time"] = row.get("lap_time") or out.get("lap_time")
            out["lap_time_ms"] = row.get("lap_time_ms") or out.get("lap_time_ms")
            if row.get("note"):
                out["note"] = row["note"]
            used_csv.add(key_s)
            merged.append(out)
            continue
        # Skip (or other GT-only) row — keep in saved order.
        merged.append(
            {
                "gt_index": 0,
                "lap_time": row["lap_time"],
                "lap_time_ms": row["lap_time_ms"],
                "note": row.get("note")
                or (
                    "skip — on-screen, no CSV"
                    if mark == MARK_SKIP
                    else row.get("note") or ""
                ),
                "mark": mark,
            }
        )

    for lap in draft_laps:
        key = lap.get("csv_lap_number")
        key_s = str(key).strip() if key is not None else ""
        if key_s and key_s not in used_csv:
            out = dict(lap)
            out["mark"] = normalize_mark(out.get("mark"))
            merged.append(out)

    for i, lap in enumerate(merged, start=1):
        lap["gt_index"] = i
    return merged


def build_helper_page_data(
    *,
    data_dir: Path,
    session_id: str,
    lap_store: LapStore | None,
    subdir: str = "accuracy",
) -> dict[str, Any]:
    """Laps + up to two crop URLs each for the eyeballing helper page."""
    sdir = session_dir(data_dir, session_id, subdir=subdir)
    manifest = _load_manifest(roi_manifest_path(sdir))
    holds = [
        h
        for h in group_hold_frames(manifest)
        if h and normalize_lap_text((h[0].get("text") or "")) is not None
    ]

    if lap_store is None:
        draft_laps: list[dict[str, Any]] = []
    else:
        csv_laps = lap_store.list_laps(session_id=session_id, limit=500)
        draft_laps = prefills_from_csv(csv_laps)

    saved = _load_saved_gt_laps(sdir)
    draft_laps = _merge_saved_marks(draft_laps, saved)

    paired = _match_holds_to_laps(draft_laps, holds)
    page_laps: list[dict[str, Any]] = []
    for lap, hold in zip(draft_laps, paired, strict=True):
        display = select_display_crops(hold, max_display=2)
        crops = []
        for frame in display:
            url = _crop_url(session_id, frame.get("path"))
            if url is None:
                continue
            crops.append(
                {
                    "url": url,
                    "path": frame.get("path"),
                    "seq": frame.get("seq"),
                    "text": frame.get("text"),
                    "mono_s": frame.get("mono_s"),
                    "wall_s": frame.get("wall_s"),
                }
            )
        page_laps.append(
            {
                "gt_index": lap.get("gt_index"),
                "lap_time": lap.get("lap_time"),
                "lap_time_ms": lap.get("lap_time_ms"),
                "csv_lap_number": lap.get("csv_lap_number"),
                "csv_recorded_at": lap.get("csv_recorded_at"),
                "note": lap.get("note") or "",
                "mark": normalize_mark(lap.get("mark")),
                "crops": crops,
            }
        )

    confirmed = detect_gt_confirmed(
        data_dir=data_dir,
        session_id=session_id,
        lap_store=lap_store,
        subdir=subdir,
    )
    return {
        "session_id": session_id,
        "laps": page_laps,
        "roi_frame_count": len(manifest),
        "hold_count": len(holds),
        "artefact_dir": str(sdir),
        "gt_confirmed": confirmed["gt_confirmed"],
        "gt_confirmed_via": confirmed["via"],
        "marks": [MARK_NORMAL, MARK_DOUBLE, MARK_SKIP],
        "note": (
            "Edit times and mark double/skip, then Confirm — writes "
            "gt_draft.json + gt.json and updates laps.csv notes/times."
        ),
    }


def save_gt_draft(
    *,
    data_dir: Path,
    session_id: str,
    gt_laps: list[dict[str, Any]],
    subdir: str = "accuracy",
) -> Path:
    """Persist operator-confirmed draft under the accuracy session dir."""
    sdir = session_dir(data_dir, session_id, subdir=subdir)
    sdir.mkdir(parents=True, exist_ok=True)
    path = gt_draft_path(sdir)
    path.write_text(
        json.dumps({"session_id": session_id, "laps": gt_laps}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _lap_updates_from_gt(
    gt_laps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map GT rows with a CSV ref → LapStore updates (skips have no CSV)."""
    updates: list[dict[str, Any]] = []
    for gt in gt_laps:
        mark = normalize_mark(gt.get("mark"))
        if mark == MARK_SKIP:
            continue
        csv_n = gt.get("csv_lap_number")
        if csv_n is None or str(csv_n).strip() == "":
            continue
        updates.append(
            {
                "lap_time": gt["lap_time"],
                "lap_time_ms": gt["lap_time_ms"],
                "lap_number": csv_n,
            }
        )
    return updates


def _gt_row_for_files(g: dict[str, Any], *, default_note: str) -> dict[str, Any]:
    """Shape a GT row for gt_draft.json / gt.json (keeps mark + csv ref)."""
    mark = normalize_mark(g.get("mark"))
    if mark == MARK_DOUBLE:
        note = g.get("note") or GT_DOUBLE_NOTE
    elif mark == MARK_SKIP:
        note = g.get("note") or "skip — on-screen, no CSV"
    else:
        note = g.get("note") or default_note
    row: dict[str, Any] = {
        "gt_index": g["gt_index"],
        "lap_time": g["lap_time"],
        "lap_time_ms": g["lap_time_ms"],
        "mark": mark,
        "note": note,
    }
    csv_n = g.get("csv_lap_number")
    if csv_n is not None and str(csv_n).strip() != "":
        row["csv_lap_number"] = csv_n
    return row


def enrich_gt_with_csv_refs(
    raw_laps: Any,
    *,
    lap_store: LapStore | None,
    session_id: str,
) -> list[dict[str, Any]]:
    """Normalize GT and carry csv_lap_number from confirm body or CSV order."""
    # Preserve csv_lap_number / mark from dict items before load_gt_list.
    csv_refs: list[Any] = []
    marks: list[Any] = []
    items: Any = raw_laps
    if isinstance(raw_laps, dict) and "laps" in raw_laps:
        items = raw_laps["laps"]
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                csv_refs.append(item.get("csv_lap_number"))
                marks.append(item.get("mark") or item.get("status"))
            else:
                csv_refs.append(None)
                marks.append(None)

    gt_laps = load_gt_list(raw_laps)

    # Fill missing csv_lap_number from chronological CSV prefill order —
    # but never invent a CSV ref for explicit skips (GT without CSV).
    chrono_nums: list[Any] = []
    if lap_store is not None:
        csv_laps = lap_store.list_laps(session_id=session_id, limit=500)
        for row in prefills_from_csv(csv_laps):
            chrono_nums.append(row.get("csv_lap_number"))

    # Positional fill only among non-skip rows that lack an explicit csv ref,
    # walking CSV numbers in order so inserted skips do not shift refs.
    chrono_i = 0
    for i, gt in enumerate(gt_laps):
        if i < len(marks) and marks[i] is not None:
            gt["mark"] = normalize_mark(marks[i])
        mark = normalize_mark(gt.get("mark"))
        ref = csv_refs[i] if i < len(csv_refs) else None
        if mark == MARK_SKIP:
            # Keep explicit csv_lap_number if the client sent one; otherwise none.
            if ref is not None and str(ref).strip() != "":
                gt["csv_lap_number"] = ref
            else:
                gt.pop("csv_lap_number", None)
            continue
        if ref is None or str(ref).strip() == "":
            while chrono_i < len(chrono_nums):
                candidate = chrono_nums[chrono_i]
                chrono_i += 1
                if candidate is not None and str(candidate).strip() != "":
                    ref = candidate
                    break
        else:
            # Advance chrono past this number when present so later fills stay aligned.
            key = str(ref).strip()
            for j in range(chrono_i, len(chrono_nums)):
                if str(chrono_nums[j] or "").strip() == key:
                    chrono_i = j + 1
                    break
        if ref is not None and str(ref).strip() != "":
            gt["csv_lap_number"] = ref
    return gt_laps


def confirm_helper_gt(
    *,
    data_dir: Path,
    session_id: str,
    raw_laps: list[Any],
    lap_store: LapStore | None,
    subdir: str = "accuracy",
    score: bool = True,
    note: str = GT_CONFIRMED_NOTE,
) -> dict[str, Any]:
    """Confirm GT from the helper: draft + gt.json + stint CSV note/times."""
    gt_laps = enrich_gt_with_csv_refs(
        raw_laps, lap_store=lap_store, session_id=session_id
    )
    gt_for_files = [
        _gt_row_for_files(g, default_note=note) for g in gt_laps
    ]

    draft_path = save_gt_draft(
        data_dir=data_dir,
        session_id=session_id,
        gt_laps=gt_for_files,
        subdir=subdir,
    )
    gt_file = save_gt(
        data_dir=data_dir,
        session_id=session_id,
        gt_laps=gt_for_files,
        subdir=subdir,
    )

    csv_updated = 0
    if lap_store is not None:
        updates = _lap_updates_from_gt(gt_laps)
        # Stamp session CSV rows with the confirm note; double/skip annotation
        # lives on gt.json / gt_draft.json via mark= (avoids per-row CSV notes).
        result = lap_store.update_session_laps(
            session_id,
            note=note,
            lap_updates=updates,
        )
        csv_updated = int(result.get("updated", 0))

    payload: dict[str, Any] = {
        "ok": True,
        "session_id": session_id,
        "gt_draft_path": str(draft_path),
        "gt_path": str(gt_file),
        "gt_laps": len(gt_for_files),
        "gt_doubles": sum(
            1 for g in gt_for_files if g.get("mark") == MARK_DOUBLE
        ),
        "gt_skips": sum(1 for g in gt_for_files if g.get("mark") == MARK_SKIP),
        "csv_laps_updated": csv_updated,
        "csv_note": note,
    }
    if score:
        if lap_store is None:
            raise ValueError("Lap store not configured")
        report = score_session(
            data_dir=data_dir,
            session_id=session_id,
            gt_laps=gt_for_files,
            subdir=subdir,
            lap_store=lap_store,
        )
        payload["score"] = {
            "write_pct": report["write_pct"],
            "ocr_sample_pct": report["ocr_sample_pct"],
            "write_matches": report["write_matches"],
            "write_misses": report["write_misses"],
            "write_extras": report["write_extras"],
            "write_doubles": report.get("write_doubles", 0),
            "gt_skips": report.get("gt_skips", 0),
            "artefact_dir": report["artefact_dir"],
            "score_json": f"{report['artefact_dir']}/score.json",
            "score_md": f"{report['artefact_dir']}/score.md",
            "review_md": f"{report['artefact_dir']}/review.md",
        }
    return payload


def resolve_roi_file(
    *,
    data_dir: Path,
    session_id: str,
    filename: str,
    subdir: str = "accuracy",
) -> Path:
    """Resolve a tee JPEG under the session roi/ dir (path-traversal safe)."""
    name = Path(filename).name
    if name != filename or name in ("", ".", ".."):
        raise ValueError("Invalid ROI filename")
    if not name.lower().endswith((".jpg", ".jpeg")):
        raise ValueError("ROI file must be a JPEG")
    sdir = session_dir(data_dir, session_id, subdir=subdir)
    roi_root = (sdir / "roi").resolve()
    path = (roi_root / name).resolve()
    try:
        path.relative_to(roi_root)
    except ValueError as exc:
        raise ValueError("ROI path escapes session directory") from exc
    return path
