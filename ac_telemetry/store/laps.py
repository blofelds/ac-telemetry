"""CSV lap store — append-only rows keyed by session_id (SQLite later)."""

from __future__ import annotations

import csv
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LAP_FIELDS = [
    "session_id",
    "lap_number",
    "lap_time",
    "lap_time_ms",
    "recorded_at",
    "source",
    "raw_text",
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
