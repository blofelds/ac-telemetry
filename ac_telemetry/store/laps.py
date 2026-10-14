"""CSV lap store — append-mostly rows keyed by session_id (SQLite later)."""

from __future__ import annotations

import csv
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ac_telemetry.detect.readers import format_lap_time_ms, parse_lap_time_text

logger = logging.getLogger(__name__)

LAP_FIELDS = [
    "session_id",
    "lap_number",
    "lap_time",
    "lap_time_ms",
    "recorded_at",
    "source",
    "raw_text",
    "note",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class LapStore:
    """Append lap rows to ``laps.csv`` under the session data directory."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.path = data_dir / "laps.csv"
        self._lock = threading.Lock()

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            with self.path.open("w", newline="", encoding="utf-8") as fh:
                csv.DictWriter(fh, fieldnames=LAP_FIELDS).writeheader()
            return
        self._migrate_header_if_needed()

    def _migrate_header_if_needed(self) -> None:
        """Rewrite CSV when older headers lack newer columns (e.g. note)."""
        with self.path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                return
            if list(reader.fieldnames) == LAP_FIELDS:
                return
            rows = list(reader)
        logger.info(
            "Migrating laps.csv header %s → %s",
            reader.fieldnames,
            LAP_FIELDS,
        )
        with self.path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=LAP_FIELDS)
            writer.writeheader()
            for raw in rows:
                writer.writerow({k: raw.get(k, "") for k in LAP_FIELDS})

    def append_lap(self, row: dict[str, Any]) -> dict[str, Any]:
        """Persist one lap; fills ``recorded_at`` when missing."""
        self.ensure()
        out = {k: row.get(k, "") for k in LAP_FIELDS}
        if not out.get("recorded_at"):
            out["recorded_at"] = _utc_now_iso()
        with self._lock:
            with self.path.open("a", newline="", encoding="utf-8") as fh:
                csv.DictWriter(fh, fieldnames=LAP_FIELDS).writerow(out)
        logger.debug(
            "Lap CSV append session=%s n=%s time=%s",
            out.get("session_id"),
            out.get("lap_number"),
            out.get("lap_time"),
        )
        return dict(out)

    def list_laps(
        self,
        *,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Newest-first lap history, optionally filtered by session."""
        self.ensure()
        limit = max(1, min(limit, 500))
        with self._lock:
            with self.path.open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        if session_id:
            rows = [r for r in rows if r.get("session_id") == session_id]
        rows.reverse()
        return rows[:limit]

    @staticmethod
    def _normalize_time_fields(
        lap_time: Any, lap_time_ms: Any
    ) -> tuple[str, str] | None:
        """Return ``(lap_time, lap_time_ms_str)`` or None if invalid."""
        if lap_time is not None and str(lap_time).strip() != "":
            parsed = parse_lap_time_text(str(lap_time).strip())
            if parsed is not None:
                text, ms = parsed
                return text, str(ms)
        if lap_time_ms is not None and str(lap_time_ms).strip() != "":
            try:
                ms_i = int(lap_time_ms)
            except (TypeError, ValueError):
                return None
            if ms_i > 0:
                return format_lap_time_ms(ms_i), str(ms_i)
        return None

    def update_session_laps(
        self,
        session_id: str,
        *,
        note: str | None = None,
        lap_updates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Update all rows for ``session_id`` (note + optional lap times).

        * Every matching row gets ``note`` when provided (e.g. ``gt_confirmed``).
        * ``lap_updates`` with ``lap_number`` target that row; others apply in
          chronological (file) order among session rows.
        * ``lap_time`` / ``lap_time_ms`` stay consistent when a time changes.

        Returns ``{updated, session_laps, times_changed}``.
        """
        self.ensure()
        updates = list(lap_updates or [])
        with self._lock:
            with self.path.open(encoding="utf-8") as fh:
                all_rows = list(csv.DictReader(fh))

            session_idxs = [
                i
                for i, r in enumerate(all_rows)
                if r.get("session_id") == session_id
            ]
            by_number: dict[str, int] = {}
            for i in session_idxs:
                num = str(all_rows[i].get("lap_number") or "").strip()
                if num and num not in by_number:
                    by_number[num] = i

            # Map each session row index → optional time update.
            time_by_idx: dict[int, tuple[str, str]] = {}
            positional = [u for u in updates if not str(u.get("lap_number") or "").strip()]
            for u in updates:
                num = str(u.get("lap_number") or "").strip()
                if not num:
                    continue
                idx = by_number.get(num)
                if idx is None:
                    continue
                normalized = self._normalize_time_fields(
                    u.get("lap_time"), u.get("lap_time_ms")
                )
                if normalized is not None:
                    time_by_idx[idx] = normalized
            for pos, u in enumerate(positional):
                if pos >= len(session_idxs):
                    break
                idx = session_idxs[pos]
                if idx in time_by_idx:
                    continue
                normalized = self._normalize_time_fields(
                    u.get("lap_time"), u.get("lap_time_ms")
                )
                if normalized is not None:
                    time_by_idx[idx] = normalized

            times_changed = 0
            for i in session_idxs:
                row = {k: all_rows[i].get(k, "") for k in LAP_FIELDS}
                if note is not None:
                    row["note"] = note
                if i in time_by_idx:
                    text, ms_s = time_by_idx[i]
                    old_text = str(row.get("lap_time") or "")
                    old_ms = str(row.get("lap_time_ms") or "")
                    row["lap_time"] = text
                    row["lap_time_ms"] = ms_s
                    if text != old_text or ms_s != old_ms:
                        times_changed += 1
                all_rows[i] = row

            with self.path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=LAP_FIELDS)
                writer.writeheader()
                for raw in all_rows:
                    writer.writerow({k: raw.get(k, "") for k in LAP_FIELDS})

        return {
            "updated": len(session_idxs),
            "session_laps": len(session_idxs),
            "times_changed": times_changed,
        }
