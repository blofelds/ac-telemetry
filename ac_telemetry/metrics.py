"""Prometheus metrics for capture health (Slice 0)."""

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

UP.set(1)

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


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
