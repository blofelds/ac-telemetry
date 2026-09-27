"""Pluggable lap-time readers: mock (always available) and optional tesseract."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)

# AC-style times: "1:44.321", "01:44.321", sometimes "1:44:321"
_TIME_RE = re.compile(
    r"(?P<m>\d{1,2})[:.](?P<s>\d{2})[.:](?P<ms>\d{1,3})"
)


@dataclass(frozen=True)
class LapTimeReading:
    """One read attempt against the lap_time ROI (or mock clock)."""

    ok: bool
    text: str = ""
    lap_time_ms: int | None = None
    error: str = ""


class LapTimeReader(Protocol):
    name: str

    def read(self, roi_bgr: Any | None) -> LapTimeReading:
        """Parse a lap time from a tiny BGR crop (may be None for mock)."""


def parse_lap_time_text(text: str) -> tuple[str, int] | None:
    """Normalize HUD text to ``M:SS.mmm`` and milliseconds, or None."""
    if not text:
        return None
    cleaned = text.strip().replace(" ", "")
    match = _TIME_RE.search(cleaned)
    if not match:
        return None
    minutes = int(match.group("m"))
    seconds = int(match.group("s"))
    ms_raw = match.group("ms").ljust(3, "0")[:3]
    millis = int(ms_raw)
    if seconds >= 60 or millis >= 1000:
        return None
    total_ms = minutes * 60_000 + seconds * 1000 + millis
    # Reject absurd values (idle/menu OCR noise).
    if total_ms <= 0 or total_ms > 30 * 60_000:
        return None
    normalized = f"{minutes}:{seconds:02d}.{millis:03d}"
    return normalized, total_ms


def format_lap_time_ms(total_ms: int) -> str:
    minutes, rem = divmod(max(0, int(total_ms)), 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


class MockLapTimeReader:
    """Synthetic last-lap times — no OpenCV/OCR. Useful on laptop and Pi.

    Emits a new completed lap every ``interval_seconds``. Between emissions the
    same last-lap text is returned (stable for debounce).
    """

    name = "mock"

    def __init__(self, interval_seconds: float = 45.0) -> None:
        self.interval_seconds = max(1.0, float(interval_seconds))
        self._started = time.monotonic()
        self._lap_index = 0
        self._last_text = "0:00.000"
        self._last_ms = 0

    def read(self, roi_bgr: Any | None = None) -> LapTimeReading:
        del roi_bgr  # mock does not need pixels
        elapsed = time.monotonic() - self._started
        completed = int(elapsed // self.interval_seconds)
        if completed > self._lap_index:
            self._lap_index = completed
            # Deterministic-ish fake times around 1:40–1:50.
            base = 100_000 + (self._lap_index * 1234) % 10_000
            self._last_ms = base
            self._last_text = format_lap_time_ms(base)
        return LapTimeReading(ok=True, text=self._last_text, lap_time_ms=self._last_ms)


class TesseractLapTimeReader:
    """Optional OCR path via pytesseract (not installed by default on Pi 2B).

    Keep the ROI tiny. On Pi 2B this is best-effort — if tesseract or
    pytesseract is missing, every read fails soft with a clear error.
    """

    name = "tesseract"

    def __init__(self, *, psm: int = 7, whitelist: str = "0123456789:.") -> None:
        self._psm = psm
        self._whitelist = whitelist
        self._checked = False
        self._available = False
        self._import_error = ""

    def _ensure(self) -> bool:
        if self._checked:
            return self._available
        self._checked = True
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401

            self._available = True
        except ImportError as exc:
            self._available = False
            self._import_error = (
                f"tesseract reader unavailable ({exc}). "
                "Install tesseract-ocr + pytesseract + Pillow on a host that "
                "can afford OCR, or use reader: mock on Pi 2B."
            )
            logger.warning("%s", self._import_error)
        return self._available

    def read(self, roi_bgr: Any | None) -> LapTimeReading:
        if not self._ensure():
            return LapTimeReading(ok=False, error=self._import_error)
        if roi_bgr is None:
            return LapTimeReading(ok=False, error="empty ROI (no frame)")
        try:
            import cv2
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            return LapTimeReading(ok=False, error=str(exc))

        try:
            if len(roi_bgr.shape) == 3:
                gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
            else:
                gray = roi_bgr
            # Light upscale helps tiny HUD digits; still cheap vs full-frame OCR.
            h, w = gray.shape[:2]
            if w < 160:
                scale = max(2, 160 // max(w, 1))
                gray = cv2.resize(
                    gray, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC
                )
            pil = Image.fromarray(gray)
            config = f"--psm {self._psm} -c tessedit_char_whitelist={self._whitelist}"
            raw = pytesseract.image_to_string(pil, config=config) or ""
        except Exception as exc:  # noqa: BLE001 — soft-fail into metrics
            return LapTimeReading(ok=False, error=f"ocr failed: {exc}")

        parsed = parse_lap_time_text(raw)
        if parsed is None:
            return LapTimeReading(
                ok=False,
                text=raw.strip(),
                error="no lap-time pattern in OCR text",
            )
        text, ms = parsed
        return LapTimeReading(ok=True, text=text, lap_time_ms=ms)


ReaderName = Literal["mock", "tesseract"]


def build_lap_time_reader(
    name: ReaderName,
    *,
    mock_interval_seconds: float = 45.0,
) -> LapTimeReader:
    if name == "mock":
        return MockLapTimeReader(interval_seconds=mock_interval_seconds)
    if name == "tesseract":
        return TesseractLapTimeReader()
    raise ValueError(f"Unknown lap_time reader: {name!r}")
