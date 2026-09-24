"""CSV session stub — write a session row on capture start/stop.

SQLite is intentionally deferred (Slice 5). Stable columns here so later
migration stays boring.
"""

from __future__ import annotations

import csv
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ac_telemetry.capture import CaptureStats

logger = logging.getLogger(__name__)

SESSION_FIELDS = [
    "session_id",
    "started_at",
    "ended_at",
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


class SessionStore:
    """Append-only sessions.csv under data_dir."""

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

    def start_session(self, stats: CaptureStats) -> str:
        self.ensure()
        session_id = uuid.uuid4().hex[:12]
        row = {
            "session_id": session_id,
            "started_at": _utc_now_iso(),
            "ended_at": "",
            "backend": stats.backend,
            "profile": stats.profile,
            "device": stats.device,
            "width": stats.width,
            "height": stats.height,
            "target_fps": stats.target_fps,
            "frames": 0,
            "errors": 0,
            "avg_fps": "",
            "status": "running",
        }
        with self._lock:
            self._open[session_id] = row
            self._append(row)
        logger.info("Session started id=%s", session_id)
        return session_id

    def end_session(self, session_id: str, stats: CaptureStats) -> None:
        self.ensure()
        with self._lock:
            row = self._open.pop(session_id, None)
            if row is None:
                row = {"session_id": session_id, "started_at": ""}
            row.update(
                {
                    "ended_at": _utc_now_iso(),
                    "backend": stats.backend,
                    "profile": stats.profile,
                    "device": stats.device,
                    "width": stats.width,
                    "height": stats.height,
                    "target_fps": stats.target_fps,
                    "frames": stats.frames,
                    "errors": stats.errors,
                    "avg_fps": round(stats.measured_fps, 2),
                    "status": "stopped",
                }
            )
            self._append(row)
        logger.info(
            "Session stopped id=%s frames=%s errors=%s",
            session_id,
            stats.frames,
            stats.errors,
        )

    def _append(self, row: dict) -> None:
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=SESSION_FIELDS).writerow(
                {k: row.get(k, "") for k in SESSION_FIELDS}
            )

    def recent_sessions(self, limit: int = 10) -> list[dict]:
        self.ensure()
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        # Last write wins per session_id (start then stop both append).
        by_id: dict[str, dict] = {}
        for row in rows:
            by_id[row["session_id"]] = row
        ordered = list(by_id.values())
        return ordered[-limit:][::-1]
