"""Append-only OCR sample log (JSONL) for ocr-sample% scoring."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class OcrSampleLog:
    """Thread-safe JSONL writer for per-detect OCR samples."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._count = 0

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def append(self, row: dict[str, Any]) -> None:
        line = json.dumps(row, separators=(",", ":"), ensure_ascii=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.write("\n")
            self._count += 1

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    @staticmethod
    def read_all(path: Path) -> list[dict[str, Any]]:
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
                    logger.debug("Skipping bad ocr_samples line: %s", line[:80])
        return rows
