"""Detect loop pacing: overrun must not crash the detect thread."""

from __future__ import annotations

from pathlib import Path

import pytest

from ac_telemetry.detect import DetectService
from ac_telemetry.settings import load_settings
from ac_telemetry.store import LapStore


def _detect_service(tmp_path: Path) -> DetectService:
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.detect.enabled = True
    settings.detect.lap_time.reader = "mock"
    lap_store = LapStore(settings.data_dir)
    lap_store.ensure()
    return DetectService(
        settings=settings,
        get_frame=lambda: None,
        get_session_id=lambda: None,
        record_lap=lap_store.append_lap,
    )


def test_sleep_remaining_overrun_returns_without_sleep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a tick already overran the interval, skip sleep (no exception)."""
    service = _detect_service(tmp_path)
    slept: list[float] = []
    monkeypatch.setattr("ac_telemetry.detect.service.time.sleep", slept.append)
    monkeypatch.setattr(
        "ac_telemetry.detect.service.time.monotonic", lambda: 10.0
    )

    # tick 10s ago with 100ms interval → already overrun
    service._sleep_remaining(tick=0.0, interval=0.1)
    assert slept == []


def test_sleep_remaining_clamps_past_deadline_chunk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Race: mono passes deadline between while-check and sleep → clamp to 0."""
    service = _detect_service(tmp_path)
    slept: list[float] = []
    monkeypatch.setattr("ac_telemetry.detect.service.time.sleep", slept.append)

    # Sequence drives: positive sleep_for, enter loop, then remaining < 0.
    # mono[0]: sleep_for = 0.1 - (0.0 - 0.0) = 0.1
    # mono[1]: deadline = 0.0 + 0.1 = 0.1
    # mono[2]: while check 0.099 < 0.1 → enter
    # mono[3]: remaining = 0.1 - 0.101 = -0.001 → must clamp
    # mono[4]: while check 0.2 < 0.1 → exit
    monos = iter([0.0, 0.0, 0.099, 0.101, 0.2])
    monkeypatch.setattr(
        "ac_telemetry.detect.service.time.monotonic", lambda: next(monos)
    )

    service._sleep_remaining(tick=0.0, interval=0.1)

    assert slept == [0.0]
    assert all(s >= 0.0 for s in slept)
