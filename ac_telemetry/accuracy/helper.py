"""GT eyeballing helper — page data, crop pick, confirm → gt + stint CSV."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ac_telemetry.accuracy.paths import (
    gt_draft_path,
    roi_manifest_path,
    session_dir,
)
from ac_telemetry.accuracy.score import (
    load_gt_list,
    normalize_lap_text,
    prefills_from_csv,
    save_gt,
    score_session,
)
from ac_telemetry.store.laps import LapStore

logger = logging.getLogger(__name__)

# Written onto every CSV lap row for the session when Confirm succeeds.
GT_CONFIRMED_NOTE = "gt_confirmed"


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
                "crops": crops,
            }
        )

    return {
        "session_id": session_id,
        "laps": page_laps,
        "roi_frame_count": len(manifest),
        "hold_count": len(holds),
        "artefact_dir": str(sdir),
        "note": (
            "Edit lap times, then Confirm — writes gt_draft.json + gt.json "
            "and updates laps.csv notes/times."
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
    """Map GT rows → LapStore.update_session_laps updates (by csv_lap_number)."""
    updates: list[dict[str, Any]] = []
    for gt in gt_laps:
        text = gt["lap_time"]
        ms = gt["lap_time_ms"]
        entry: dict[str, Any] = {
            "lap_time": text,
            "lap_time_ms": ms,
        }
        csv_n = gt.get("csv_lap_number")
        if csv_n is not None and str(csv_n).strip() != "":
            entry["lap_number"] = csv_n
        updates.append(entry)
    return updates


def enrich_gt_with_csv_refs(
    raw_laps: Any,
    *,
    lap_store: LapStore | None,
    session_id: str,
) -> list[dict[str, Any]]:
    """Normalize GT and carry csv_lap_number from confirm body or CSV order."""
    # Preserve csv_lap_number from dict items before load_gt_list strips unknowns.
    csv_refs: list[Any] = []
    items: Any = raw_laps
    if isinstance(raw_laps, dict) and "laps" in raw_laps:
        items = raw_laps["laps"]
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                csv_refs.append(item.get("csv_lap_number"))
            else:
                csv_refs.append(None)

    gt_laps = load_gt_list(raw_laps)

    # Fill missing csv_lap_number from chronological CSV prefill order.
    chrono_nums: list[Any] = []
    if lap_store is not None:
        csv_laps = lap_store.list_laps(session_id=session_id, limit=500)
        for row in prefills_from_csv(csv_laps):
            chrono_nums.append(row.get("csv_lap_number"))

    for i, gt in enumerate(gt_laps):
        ref = csv_refs[i] if i < len(csv_refs) else None
        if ref is None or str(ref).strip() == "":
            if i < len(chrono_nums):
                ref = chrono_nums[i]
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
    # Persist GT rows without csv_lap_number noise in gt.json (keep note/time).
    gt_for_files = [
        {
            "gt_index": g["gt_index"],
            "lap_time": g["lap_time"],
            "lap_time_ms": g["lap_time_ms"],
            "note": g.get("note") or note,
        }
        for g in gt_laps
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
