"""CSV session + lap stores.

SQLite is intentionally deferred. Stable columns here so later migration
stays boring. Capture no longer owns session lifecycle; the phone API does.
Ending a session may snapshot current capture stats into the row.
"""

from __future__ import annotations

import csv
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ac_telemetry.capture import CaptureStats
from ac_telemetry.store.laps import LAP_FIELDS, LapStore

logger = logging.getLogger(__name__)

__all__ = [
    "LAP_FIELDS",
    "LapStore",
    "SESSION_FIELDS",
    "SessionConflict",
    "SessionNotFound",
    "SessionStore",
]

SESSION_FIELDS = [
    "session_id",
    "started_at",
    "ended_at",
    "track",
    "car",
    "notes",
    "backend",
    "profile",
    "device",
    "width",
    "height",
    "target_fps",
    "frames",
    "errors",
    "avg_fps",
    "status",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _empty_row(**overrides: Any) -> dict[str, Any]:
    row = {k: "" for k in SESSION_FIELDS}
    row.update(overrides)
    return row


class SessionStore:
    """Append-only sessions.csv under data_dir; last row per id wins."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.path = data_dir / "sessions.csv"
        self._lock = threading.Lock()
        self._open: dict[str, dict] = {}

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            with self.path.open("w", newline="", encoding="utf-8") as fh:
                csv.DictWriter(fh, fieldnames=SESSION_FIELDS).writeheader()
            return
        self._migrate_header_if_needed()

    def _migrate_header_if_needed(self) -> None:
        """Rewrite CSV if Slice 0 columns lack track/car/notes."""
        with self.path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                return
            if list(reader.fieldnames) == SESSION_FIELDS:
                return
            rows = list(reader)
        logger.info(
            "Migrating sessions.csv header %s → Slice 1 columns",
            reader.fieldnames,
        )
        with self.path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=SESSION_FIELDS)
            writer.writeheader()
            for raw in rows:
                writer.writerow({k: raw.get(k, "") for k in SESSION_FIELDS})

    def current_session(self) -> dict | None:
        with self._lock:
            if not self._open:
                return None
            # At most one open session in Slice 1 (single-driver Pi).
            return dict(next(iter(self._open.values())))

    def start_session(
        self,
        *,
        track: str = "",
        car: str = "",
        notes: str = "",
        stats: CaptureStats | None = None,
    ) -> dict:
        """Create a running session from phone/API metadata."""
        self.ensure()
        with self._lock:
            if self._open:
                open_id = next(iter(self._open))
                raise SessionConflict(
                    f"Session {open_id} is already running; end it first"
                )
            session_id = uuid.uuid4().hex[:12]
            row = _empty_row(
                session_id=session_id,
                started_at=_utc_now_iso(),
                track=(track or "").strip(),
                car=(car or "").strip(),
                notes=(notes or "").strip(),
                status="running",
            )
            if stats is not None:
                self._apply_capture_snapshot(row, stats, ending=False)
            self._open[session_id] = row
            self._append(row)
        logger.info(
            "Session started id=%s track=%r car=%r",
            session_id,
            row["track"],
            row["car"],
        )
        return dict(row)

    def end_session(
        self,
        session_id: str,
        *,
        stats: CaptureStats | None = None,
    ) -> dict:
        """Mark a session stopped and append the final CSV row."""
        self.ensure()
        with self._lock:
            row = self._open.pop(session_id, None)
            if row is None:
                # Recover from process restart: load last known row from CSV.
                row = self._lookup_unlocked(session_id)
                if row is None:
                    raise SessionNotFound(f"Unknown session: {session_id}")
                if row.get("status") == "stopped" and row.get("ended_at"):
                    raise SessionConflict(f"Session {session_id} already ended")
                row = dict(row)
            row["ended_at"] = _utc_now_iso()
            row["status"] = "stopped"
            if stats is not None:
                self._apply_capture_snapshot(row, stats, ending=True)
            self._append(row)
        logger.info("Session stopped id=%s", session_id)
        return dict(row)

    def end_current(self, *, stats: CaptureStats | None = None) -> dict:
        current = self.current_session()
        if current is None:
            raise SessionNotFound("No running session")
        return self.end_session(current["session_id"], stats=stats)

    @staticmethod
    def _apply_capture_snapshot(
        row: dict, stats: CaptureStats, *, ending: bool
    ) -> None:
        row["backend"] = stats.backend
        row["profile"] = stats.profile
        row["device"] = stats.device
        row["width"] = stats.width
        row["height"] = stats.height
        row["target_fps"] = stats.target_fps
        if ending:
            row["frames"] = stats.frames
            row["errors"] = stats.errors
            row["avg_fps"] = round(stats.measured_fps, 2)

    def _append(self, row: dict) -> None:
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=SESSION_FIELDS).writerow(
                {k: row.get(k, "") for k in SESSION_FIELDS}
            )

    def _lookup_unlocked(self, session_id: str) -> dict | None:
        by_id = self._all_by_id_unlocked()
        return by_id.get(session_id)

    def _all_by_id_unlocked(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        with self.path.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        by_id: dict[str, dict] = {}
        for row in rows:
            sid = row.get("session_id") or ""
            if sid:
                by_id[sid] = row
        return by_id

    def get_session(self, session_id: str) -> dict | None:
        self.ensure()
        with self._lock:
            if session_id in self._open:
                return dict(self._open[session_id])
            return self._lookup_unlocked(session_id)

    def list_sessions(self, limit: int = 50) -> list[dict]:
        """Newest-first history; open in-memory rows win over CSV."""
        self.ensure()
        limit = max(1, min(limit, 500))
        with self._lock:
            by_id = self._all_by_id_unlocked()
            by_id.update(self._open)
            ordered = list(by_id.values())
        # Prefer started_at then file order; reverse for newest first.
        ordered.sort(key=lambda r: r.get("started_at") or "", reverse=True)
        return ordered[:limit]

    def recent_sessions(self, limit: int = 10) -> list[dict]:
        """Alias kept for Slice 0 callers."""
        return self.list_sessions(limit=limit)


class SessionNotFound(Exception):
    """Requested session id does not exist."""


class SessionConflict(Exception):
    """Invalid session state transition (already open / already ended)."""
