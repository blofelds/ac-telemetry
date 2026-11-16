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
    def _lap_ms(row: dict[str, Any]) -> int | None:
        raw = row.get("lap_time_ms")
        if raw is None or str(raw).strip() == "":
            return None
        try:
            ms = int(raw)
        except (TypeError, ValueError):
            return None
        return ms if ms > 0 else None

    @staticmethod
    def format_delta_ms(delta_ms: int) -> str:
        """ACC-style gap: ``BEST``, ``+0.320``, or ``+1:02.100`` if ≥60s."""
        if delta_ms == 0:
            return "BEST"
        sign = "+" if delta_ms > 0 else "-"
        abs_ms = abs(int(delta_ms))
        if abs_ms >= 60_000:
            return sign + format_lap_time_ms(abs_ms)
        seconds = abs_ms / 1000.0
        return f"{sign}{seconds:.3f}"

    @classmethod
    def min_contiguous_avg_ms(
        cls,
        laps_chrono: list[dict[str, Any]],
        window: int,
    ) -> int | None:
        """Minimum mean over any contiguous run of ``window`` timed laps.

        ``laps_chrono`` must be oldest-first session order. A window counts
        only when every lap in it has a valid ``lap_time_ms`` (invalid rows
        break contiguity). Returns ``None`` when no such window exists.
        """
        if window < 1 or len(laps_chrono) < window:
            return None
        times = [cls._lap_ms(row) for row in laps_chrono]
        best: int | None = None
        for i in range(len(times) - window + 1):
            chunk = times[i : i + window]
            if any(ms is None for ms in chunk):
                continue
            total = 0
            for ms in chunk:
                assert ms is not None  # narrowed by the any(...) check above
                total += ms
            avg = total // window
            if best is None or avg < best:
                best = avg
        return best

    def summarize_session(
        self,
        session_id: str,
        *,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Aggregate lap stats + per-lap Δ to best for a session dossier.

        Laps are newest-first (same as ``list_laps``). Invalid / missing
        ``lap_time_ms`` rows stay in the list with null deltas and are
        excluded from best and from contiguous pace windows.
        """
        laps = self.list_laps(session_id=session_id, limit=limit)
        timed: list[tuple[dict[str, Any], int]] = []
        for row in laps:
            ms = self._lap_ms(row)
            if ms is not None:
                timed.append((row, ms))

        best_ms: int | None = None
        best_lap_number: str | None = None
        best_lap_time: str | None = None

        if timed:
            best_ms = min(ms for _, ms in timed)
            # Prefer the chronologically earliest best when times tie.
            best_row = None
            for row, ms in reversed(timed):
                if ms == best_ms:
                    best_row = row
                    break
            if best_row is not None:
                best_lap_number = str(best_row.get("lap_number") or "") or None
                best_lap_time = str(best_row.get("lap_time") or "") or format_lap_time_ms(
                    best_ms
                )

        # Contiguous pace uses chronological (oldest-first) order.
        chrono = list(reversed(laps))
        pace_5_ms = self.min_contiguous_avg_ms(chrono, 5)
        pace_10_ms = self.min_contiguous_avg_ms(chrono, 10)
        pace_5_lap_time = format_lap_time_ms(pace_5_ms) if pace_5_ms is not None else None
        pace_10_lap_time = (
            format_lap_time_ms(pace_10_ms) if pace_10_ms is not None else None
        )

        enriched: list[dict[str, Any]] = []
        for row in laps:
            out = dict(row)
            ms = self._lap_ms(row)
            if ms is None or best_ms is None:
                out["delta_ms"] = None
                out["delta_text"] = None
                out["is_best"] = False
            else:
                delta = ms - best_ms
                out["delta_ms"] = delta
                out["delta_text"] = self.format_delta_ms(delta)
                out["is_best"] = delta == 0
            enriched.append(out)

        return {
            "session_id": session_id,
            "lap_count": len(laps),
            "timed_lap_count": len(timed),
            "best_ms": best_ms,
            "best_lap_time": best_lap_time,
            "best_lap_number": best_lap_number,
            "pace_5_ms": pace_5_ms,
            "pace_5_lap_time": pace_5_lap_time,
            "pace_10_ms": pace_10_ms,
            "pace_10_lap_time": pace_10_lap_time,
            "laps": enriched,
        }

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
