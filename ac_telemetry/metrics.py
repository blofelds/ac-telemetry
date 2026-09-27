"""Prometheus metrics for capture health, sessions, and lap detection."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

from ac_telemetry.capture import CaptureStats

REGISTRY = CollectorRegistry()

UP = Gauge(
    "ac_telemetry_up",
    "1 if the service process is running",
    registry=REGISTRY,
)
CAPTURE_RUNNING = Gauge(
    "ac_telemetry_capture_running",
    "1 if the capture loop is running",
    registry=REGISTRY,
)
CAPTURE_FPS = Gauge(
    "ac_telemetry_capture_fps",
    "Measured capture frames per second",
    registry=REGISTRY,
)
LAST_FRAME_AGE = Gauge(
    "ac_telemetry_last_frame_age_seconds",
    "Seconds since the last successful frame (NaN if never)",
    registry=REGISTRY,
)
CAPTURE_ERRORS = Counter(
    "ac_telemetry_capture_errors_total",
    "Total capture errors since process start",
    registry=REGISTRY,
)
FRAMES_TOTAL = Counter(
    "ac_telemetry_frames_total",
    "Total frames captured since process start",
    registry=REGISTRY,
)
SESSIONS_STARTED = Counter(
    "ac_telemetry_sessions_started_total",
    "Sessions started via API (manual metadata)",
    registry=REGISTRY,
)
SESSIONS_ENDED = Counter(
    "ac_telemetry_sessions_ended_total",
    "Sessions ended via API",
    registry=REGISTRY,
)
SESSIONS_OPEN = Gauge(
    "ac_telemetry_sessions_open",
    "1 if a session is currently running",
    registry=REGISTRY,
)
DETECT_LATENCY = Gauge(
    "ac_telemetry_detect_latency_seconds",
    "Last lap-time detect duration in seconds",
    registry=REGISTRY,
)
DETECT_FAILURES = Counter(
    "ac_telemetry_detect_failures_total",
    "Lap-time OCR/read failures since process start",
    registry=REGISTRY,
)
DETECT_DROPS = Counter(
    "ac_telemetry_detect_drops_total",
    "Detect ticks dropped because a previous tick was still busy",
    registry=REGISTRY,
)
LAPS_RECORDED = Counter(
    "ac_telemetry_laps_recorded_total",
    "Completed laps persisted to CSV",
    registry=REGISTRY,
)
SIGNAL_LAP_TIME_MS = Gauge(
    "ac_telemetry_signal_lap_time_ms",
    "Last displayed lap time in milliseconds (NaN if unknown)",
    registry=REGISTRY,
)

UP.set(1)
SESSIONS_OPEN.set(0)
SIGNAL_LAP_TIME_MS.set(float("nan"))

_last_error_count = 0
_last_frame_count = 0


def sync_from_stats(stats: CaptureStats) -> None:
    """Push CaptureStats into Prometheus gauges/counters."""
    global _last_error_count, _last_frame_count

    CAPTURE_RUNNING.set(1 if stats.running else 0)
    CAPTURE_FPS.set(stats.measured_fps)
    age = stats.last_frame_age_seconds()
    if age is None:
        LAST_FRAME_AGE.set(float("nan"))
    else:
        LAST_FRAME_AGE.set(age)

    if stats.errors > _last_error_count:
        CAPTURE_ERRORS.inc(stats.errors - _last_error_count)
        _last_error_count = stats.errors
    if stats.frames > _last_frame_count:
        FRAMES_TOTAL.inc(stats.frames - _last_frame_count)
        _last_frame_count = stats.frames


def observe_detect(
    *,
    latency_seconds: float | None = None,
    failure: bool = False,
    lap_recorded: bool = False,
    dropped: bool = False,
    displayed_time_ms: int | None = None,
) -> None:
    """Update detect-related metrics from the detect worker."""
    if latency_seconds is not None:
        DETECT_LATENCY.set(latency_seconds)
    if failure:
        DETECT_FAILURES.inc()
    if lap_recorded:
        LAPS_RECORDED.inc()
    if dropped:
        DETECT_DROPS.inc()
    if displayed_time_ms is not None:
        SIGNAL_LAP_TIME_MS.set(displayed_time_ms)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
