"""Background detect loop: sample latest frame at low FPS, never block capture."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ac_telemetry.detect.dump import LastDetectDump, build_dump_meta
from ac_telemetry.detect.readers import (
    LapTimeReader,
    LapTimeReading,
    build_lap_time_reader,
    format_lap_time_ms,
)
from ac_telemetry.detect.roi import crop_roi
from ac_telemetry.settings import DetectSettings, Settings

logger = logging.getLogger(__name__)

# Coarse stall threshold: last tick older than this × detect interval → degraded.
# ~3–5× covers scheduling jitter without false alarms at default 2 fps.
STALE_TICK_MULTIPLIER = 4.0


@dataclass
class LiveLapState:
    """In-memory view of the latest lap-time read (for API/UI)."""

    displayed_time: str | None = None
    displayed_time_ms: int | None = None
    last_recorded_time: str | None = None
    last_recorded_time_ms: int | None = None
    lap_number: int = 0
    last_error: str | None = None
    last_detect_at: float | None = None
    last_latency_seconds: float | None = None
    reader: str = "mock"
    mode: str = "last_lap"
    enabled: bool = False
    drops: int = 0
    failures: int = 0
    reads_ok: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "reader": self.reader,
            "mode": self.mode,
            "displayed_time": self.displayed_time,
            "displayed_time_ms": self.displayed_time_ms,
            "last_recorded_time": self.last_recorded_time,
            "last_recorded_time_ms": self.last_recorded_time_ms,
            "lap_number": self.lap_number,
            "last_error": self.last_error,
            "last_detect_at": self.last_detect_at,
            "last_latency_seconds": self.last_latency_seconds,
            "drops": self.drops,
            "failures": self.failures,
            "reads_ok": self.reads_ok,
        }


@dataclass
class DetectService:
    """Low-FPS worker that crops ``lap_time`` and records completed laps to CSV."""

    settings: Settings
    get_frame: Callable[[], Any | None]
    get_session_id: Callable[[], str | None]
    record_lap: Callable[[dict[str, Any]], dict[str, Any]]
    on_metrics: Callable[..., None] | None = None
    # Optional capture identity for detect dumps (frames counter, age).
    get_capture_info: Callable[[], dict[str, Any]] | None = None
    state: LiveLapState = field(default_factory=LiveLapState)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _busy: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _dump_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _reader: LapTimeReader | None = field(default=None, init=False, repr=False)
    _stable_text: str | None = field(default=None, init=False, repr=False)
    _stable_ms: int | None = field(default=None, init=False, repr=False)
    _stable_count: int = field(default=0, init=False, repr=False)
    _prev_stable_ms: int | None = field(default=None, init=False, repr=False)
    # Wall-clock of last successful last_lap CSV write (monotonic seconds).
    _last_lap_record_mono: float | None = field(default=None, init=False, repr=False)
    # When the current candidate LAST text first appeared (monotonic seconds).
    _candidate_stable_mono: float | None = field(default=None, init=False, repr=False)
    _last_dump: LastDetectDump = field(default_factory=LastDetectDump, init=False, repr=False)
    _failures_since_dump: int = field(default=0, init=False, repr=False)
    # Monotonic time of last completed detect-loop iteration (tick or drop).
    _last_tick_mono: float | None = field(default=None, init=False, repr=False)

    def start(self) -> None:
        detect = self.settings.detect
        self.state.enabled = detect.enabled
        self.state.reader = detect.lap_time.reader
        self.state.mode = detect.lap_time.mode
        if not detect.enabled:
            logger.info("Detect disabled in config")
            return
        if "lap_time" not in self.settings.rois and detect.lap_time.reader != "mock":
            logger.warning(
                "detect.enabled but rois.lap_time missing; "
                "tesseract/template reads will fail until ROI is configured"
            )
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._reader = build_lap_time_reader(
                detect.lap_time.reader,
                mock_interval_seconds=detect.lap_time.mock_interval_seconds,
                templates_dir=detect.lap_time.templates_dir,
                match_threshold=detect.lap_time.match_threshold,
            )
            self._thread = threading.Thread(
                target=self._run, name="detect-loop", daemon=True
            )
            self._thread.start()
            logger.info(
                "Detect started reader=%s mode=%s fps=%.1f debug_dump=%s",
                detect.lap_time.reader,
                detect.lap_time.mode,
                detect.fps,
                detect.debug_dump.enabled,
            )

    def request_stop(self) -> None:
        """Non-blocking stop signal (safe from a SIGINT handler)."""
        self._stop.set()

    def stop(self, timeout: float = 5.0) -> None:
        self.request_stop()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

    def reset_for_session(self) -> None:
        """Clear per-session lap counters when a new session starts."""
        self.state.lap_number = 0
        self.state.last_recorded_time = None
        self.state.last_recorded_time_ms = None
        self._prev_stable_ms = None
        self._stable_text = None
        self._stable_ms = None
        self._stable_count = 0
        self._last_lap_record_mono = None
        self._candidate_stable_mono = None

    def get_last_dump(self) -> LastDetectDump:
        """Return the in-memory last detect dump (may be empty)."""
        return self._last_dump

    def last_dump_json(self) -> dict[str, Any] | None:
        with self._dump_lock:
            return self._last_dump.as_json()

    def last_dump_roi_png(self) -> bytes | None:
        with self._dump_lock:
            return self._last_dump.roi_png()

    def last_dump_mask_png(self) -> bytes | None:
        with self._dump_lock:
            return self._last_dump.mask_png()

    def last_dump_annotated_png(self) -> bytes | None:
        with self._dump_lock:
            return self._last_dump.annotated_png()

    def is_alive(self) -> bool:
        """True when the detect-loop thread is still running."""
        thread = self._thread
        return thread is not None and thread.is_alive()

    def liveness(self) -> dict[str, Any]:
        """Detect-loop health for ``/api/status`` (distinct from capture.running).

        ``health`` is one of ``ok`` / ``degraded`` / ``stopped``. When detect is
        disabled in config, health is ``stopped`` with ``enabled=false`` so the
        UI can show a muted off state rather than a crash alarm.
        """
        detect = self.settings.detect
        enabled = bool(detect.enabled)
        thread = self._thread
        alive = thread is not None and thread.is_alive()
        interval = 1.0 / max(detect.fps, 0.1)
        stale_after_s = interval * STALE_TICK_MULTIPLIER

        last_tick_mono = self._last_tick_mono
        if last_tick_mono is None:
            last_tick_age_s: float | None = None
        else:
            last_tick_age_s = round(max(0.0, time.monotonic() - last_tick_mono), 3)

        if not enabled:
            health = "stopped"
        elif alive:
            if (
                last_tick_age_s is not None
                and last_tick_age_s > stale_after_s
            ):
                health = "degraded"
            else:
                health = "ok"
        elif thread is not None:
            # Thread was started but is no longer alive (crash / exit).
            health = "degraded"
        else:
            health = "stopped"

        return {
            "enabled": enabled,
            "running": bool(enabled and alive),
            "alive": alive,
            "last_tick_age_s": last_tick_age_s,
            "stale_after_s": round(stale_after_s, 3) if enabled else None,
            "health": health,
        }

    def _mark_tick(self) -> None:
        self._last_tick_mono = time.monotonic()

    def _run(self) -> None:
        detect = self.settings.detect
        interval = 1.0 / max(detect.fps, 0.1)
        self._mark_tick()
        while not self._stop.is_set():
            tick = time.monotonic()
            if detect.drop_under_pressure and self._busy.is_set():
                self.state.drops += 1
                if self.on_metrics is not None:
                    self.on_metrics(dropped=True)
                self._mark_tick()
                self._sleep_remaining(tick, interval)
                continue
            self._busy.set()
            try:
                self._tick(detect)
            finally:
                self._busy.clear()
            self._mark_tick()
            self._sleep_remaining(tick, interval)

    def _sleep_remaining(self, tick: float, interval: float) -> None:
        sleep_for = interval - (time.monotonic() - tick)
        if sleep_for <= 0:
            return
        deadline = time.monotonic() + sleep_for
        while not self._stop.is_set() and time.monotonic() < deadline:
            # Clamp: between the deadline check and sleep, mono can overrun
            # (ValueError: sleep length must be non-negative).
            remaining = deadline - time.monotonic()
            time.sleep(max(0.0, min(0.05, remaining)))

    def _tick(self, detect: DetectSettings) -> None:
        assert self._reader is not None
        started = time.perf_counter()
        roi_img = None
        roi = self.settings.rois.get("lap_time")
        if self._reader.name != "mock":
            frame = self.get_frame()
            if frame is not None and roi is not None:
                roi_img = crop_roi(frame, roi)
            elif frame is None:
                reading = LapTimeReading(ok=False, error="no frame yet")
                self._handle_reading(
                    detect, reading, time.perf_counter() - started, roi_img=None
                )
                return
            elif roi is None:
                reading = LapTimeReading(ok=False, error="rois.lap_time not configured")
                self._handle_reading(
                    detect, reading, time.perf_counter() - started, roi_img=None
                )
                return

        reading = self._reader.read(roi_img)
        latency = time.perf_counter() - started
        self._handle_reading(detect, reading, latency, roi_img=roi_img)

    def _should_stash_dump(self, detect: DetectSettings, *, ok: bool) -> bool:
        dump_cfg = detect.debug_dump
        if not dump_cfg.enabled:
            return False
        if ok:
            return bool(dump_cfg.on_success)
        self._failures_since_dump += 1
        every = max(1, int(dump_cfg.every_n_failures))
        if self._failures_since_dump >= every:
            self._failures_since_dump = 0
            return True
        return False

    def _stash_dump(
        self,
        detect: DetectSettings,
        reading: LapTimeReading,
        latency: float,
        *,
        roi_img: Any | None,
        ok: bool,
    ) -> None:
        if not self._should_stash_dump(detect, ok=ok):
            return

        diagnostics = reading.diagnostics
        mask = None
        if diagnostics is not None:
            mask = diagnostics.get("mask")
            # If mask missing but we have ROI, compute white_mask cheaply once.
            if mask is None and roi_img is not None:
                try:
                    from ac_telemetry.detect.template_matcher import white_mask

                    mask = white_mask(roi_img)
                except Exception:  # noqa: BLE001
                    mask = None

        capture_info = None
        if self.get_capture_info is not None:
            try:
                capture_info = self.get_capture_info()
            except Exception:  # noqa: BLE001
                capture_info = None

        # Copy ROI/mask so later capture overwrites cannot mutate the dump.
        roi_copy = None
        mask_copy = None
        try:
            if roi_img is not None:
                roi_copy = roi_img.copy()
            if mask is not None:
                mask_copy = mask.copy()
        except AttributeError:
            roi_copy = roi_img
            mask_copy = mask

        meta = build_dump_meta(
            settings=self.settings,
            ok=ok,
            error=None if ok else (reading.error or "read failed"),
            latency_seconds=latency,
            reading_text=reading.text or "",
            reading_ms=reading.lap_time_ms,
            diagnostics=diagnostics,
            roi=self.settings.rois.get("lap_time"),
            roi_bgr=roi_copy,
            mask=mask_copy,
            capture_info=capture_info,
        )

        with self._dump_lock:
            self._last_dump.meta = meta
            self._last_dump.roi_bgr = roi_copy
            self._last_dump.mask = mask_copy
            self._last_dump.captured_at = time.time()

    def _handle_reading(
        self,
        detect: DetectSettings,
        reading: LapTimeReading,
        latency: float,
        *,
        roi_img: Any | None = None,
    ) -> None:
        self.state.last_latency_seconds = round(latency, 4)
        self.state.last_detect_at = time.time()

        if not reading.ok or reading.lap_time_ms is None:
            self.state.failures += 1
            self.state.last_error = reading.error or "read failed"
            self._stash_dump(detect, reading, latency, roi_img=roi_img, ok=False)
            if self.on_metrics is not None:
                self.on_metrics(latency_seconds=latency, failure=True)
            return

        self.state.reads_ok += 1
        self.state.last_error = None
        self.state.displayed_time = reading.text
        self.state.displayed_time_ms = reading.lap_time_ms
        self._stash_dump(detect, reading, latency, roi_img=roi_img, ok=True)
        if self.on_metrics is not None:
            self.on_metrics(
                latency_seconds=latency,
                displayed_time_ms=reading.lap_time_ms,
            )

        # Debounce: require N identical consecutive reads before acting.
        if reading.text == self._stable_text:
            self._stable_count += 1
        else:
            self._stable_text = reading.text
            self._stable_ms = reading.lap_time_ms
            self._stable_count = 1
            self._candidate_stable_mono = time.monotonic()

        if self._stable_count < max(1, detect.debounce_reads):
            return
        if self._stable_ms is None:
            return

        # Already acted on this stable value.
        if self._stable_ms == self._prev_stable_ms:
            return

        mode = detect.lap_time.mode
        should_record = False
        record_ms = self._stable_ms
        record_text = self._stable_text or format_lap_time_ms(record_ms)

        if mode == "last_lap":
            # New distinct last-lap value → record it (skip the initial 0:00 seed).
            # Gate on wall-clock since last CSV write (≥ min_lap_ms) so OCR flicker
            # within one real lap cannot spam rows. Also require the new text to
            # hold long enough (base last_lap_stable_ms, or last_lap_early_stable_ms
            # while the gap is still below last_lap_early_window_ms) — after the
            # wall gate re-opens while HUD LAST is unchanged, brief distinct OCR
            # still commits without a hold. Failed OCR reads do not reset the
            # candidate timer (soft MJPEG often has sparse successes of a real
            # held LAST). Do NOT reject close lap *values* — real consecutive
            # laps can differ by only tens of ms.
            if record_ms > 0 and record_ms != self.state.last_recorded_time_ms:
                if not self._last_lap_wall_clock_ok(detect):
                    # Leave _prev_stable_ms unset so we retry once the gate opens.
                    return
                if not self._last_lap_stable_hold_ok(detect):
                    # Same: retry while the candidate keeps holding.
                    return
                should_record = True
        else:  # current_timer
            # Record previous stable time when the timer resets downward.
            if (
                self._prev_stable_ms is not None
                and self._prev_stable_ms >= detect.lap_time.min_lap_ms
                and record_ms + detect.lap_time.reset_slack_ms < self._prev_stable_ms
            ):
                should_record = True
                record_ms = self._prev_stable_ms
                record_text = format_lap_time_ms(record_ms)

        self._prev_stable_ms = self._stable_ms

        if not should_record:
            return

        session_id = self.get_session_id()
        if not session_id:
            # Still update "last seen" so UI shows the read; do not write CSV.
            self.state.last_recorded_time = record_text
            self.state.last_recorded_time_ms = record_ms
            return

        self.state.lap_number += 1
        row = {
            "session_id": session_id,
            "lap_number": self.state.lap_number,
            "lap_time": record_text,
            "lap_time_ms": record_ms,
            "source": self._reader.name if self._reader is not None else "unknown",
            "raw_text": reading.text,
        }
        try:
            saved = self.record_lap(row)
        except Exception as exc:  # noqa: BLE001
            self.state.failures += 1
            self.state.last_error = f"persist failed: {exc}"
            logger.exception("Failed to persist lap: %s", exc)
            if self.on_metrics is not None:
                self.on_metrics(failure=True)
            return

        self.state.last_recorded_time = saved.get("lap_time", record_text)
        self.state.last_recorded_time_ms = int(saved.get("lap_time_ms") or record_ms)
        if mode == "last_lap":
            self._last_lap_record_mono = time.monotonic()
        if self.on_metrics is not None:
            self.on_metrics(lap_recorded=True)
        logger.info(
            "Lap recorded session=%s n=%s time=%s",
            session_id,
            self.state.lap_number,
            record_text,
        )

    def _last_lap_wall_clock_ok(self, detect: DetectSettings) -> bool:
        """True if enough wall time has passed since the last last_lap CSV write."""
        if self._last_lap_record_mono is None:
            return True
        min_lap_ms = max(0, int(detect.lap_time.min_lap_ms))
        elapsed_ms = (time.monotonic() - self._last_lap_record_mono) * 1000.0
        return elapsed_ms >= min_lap_ms

    def _last_lap_required_hold_ms(self, detect: DetectSettings) -> int:
        """Hold ms required for the current wall-gap (base vs early-window boost)."""
        base = max(0, int(detect.lap_time.last_lap_stable_ms))
        early_window = max(0, int(detect.lap_time.last_lap_early_window_ms))
        early_hold = max(0, int(detect.lap_time.last_lap_early_stable_ms))
        if (
            early_window > 0
            and early_hold > base
            and self._last_lap_record_mono is not None
        ):
            gap_ms = (time.monotonic() - self._last_lap_record_mono) * 1000.0
            if gap_ms < early_window:
                return early_hold
        return base

    def _last_lap_stable_hold_ok(self, detect: DetectSettings) -> bool:
        """True if the candidate LAST text has been held long enough to accept."""
        hold_ms = self._last_lap_required_hold_ms(detect)
        if hold_ms <= 0:
            return True
        if self._candidate_stable_mono is None:
            return False
        elapsed_ms = (time.monotonic() - self._candidate_stable_mono) * 1000.0
        return elapsed_ms >= hold_ms
