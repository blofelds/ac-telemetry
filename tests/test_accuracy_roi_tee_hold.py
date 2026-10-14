"""ROI tee hold bucketing: ≤N JPEGs per stable LAST hold; OCR log full-rate."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ac_telemetry.accuracy.roi_tee import (
    HoldTeeSampler,
    RoiTeeWriter,
    hold_key_for_sample,
    select_hold_tee_indices,
)
from ac_telemetry.accuracy.session import AccuracySession
from ac_telemetry.settings import AccuracySettings


def test_select_hold_tee_indices_default_three() -> None:
    assert select_hold_tee_indices(0, 3) == []
    assert select_hold_tee_indices(1, 3) == [0]
    assert select_hold_tee_indices(2, 3) == [0, 1]
    assert select_hold_tee_indices(3, 3) == [0, 1, 2]
    assert select_hold_tee_indices(5, 3) == [0, 2, 4]
    assert select_hold_tee_indices(6, 3) == [0, 2, 5]
    assert select_hold_tee_indices(10, 3) == [0, 4, 9]


def test_select_hold_tee_indices_other_caps() -> None:
    assert select_hold_tee_indices(10, 1) == [0]
    assert select_hold_tee_indices(10, 2) == [0, 9]
    assert select_hold_tee_indices(10, 0) == list(range(10))  # unlimited
    assert select_hold_tee_indices(4, 4) == [0, 1, 2, 3]
    # Even spacing for caps > 3
    assert select_hold_tee_indices(9, 5) == [0, 2, 4, 6, 8]


def test_hold_key_buckets_by_text() -> None:
    assert hold_key_for_sample(text="1:07.717", lap_time_ms=67_717, ok=True) == (
        hold_key_for_sample(text="1:07.717", lap_time_ms=99, ok=False)
    )
    assert hold_key_for_sample(text="1:07.717", lap_time_ms=67_717, ok=True) != (
        hold_key_for_sample(text="1:08.001", lap_time_ms=68_001, ok=True)
    )
    assert hold_key_for_sample(text="", lap_time_ms=None, ok=False) == "empty"


def test_hold_tee_sampler_emits_first_middle_last_on_boundary() -> None:
    sampler = HoldTeeSampler(max_per_hold=3)
    # First hold: 5 samples — nothing emitted until key changes.
    for i in range(5):
        ready = sampler.push("t:A", f"A{i}")
        assert ready == []
    # New hold flushes previous: indices 0, 2, 4
    ready = sampler.push("t:B", "B0")
    assert ready == ["A0", "A2", "A4"]
    ready = sampler.push("t:B", "B1")
    assert ready == []
    # Session end
    assert sampler.flush() == ["B0", "B1"]


def test_hold_tee_sampler_unlimited_passthrough() -> None:
    sampler = HoldTeeSampler(max_per_hold=0)
    assert sampler.push("t:A", "x") == ["x"]
    assert sampler.push("t:A", "y") == ["y"]


def test_roi_tee_writer_caps_jpegs_per_hold(tmp_path: Path) -> None:
    writer = RoiTeeWriter(
        session_dir=tmp_path,
        fmt="jpeg_seq",
        max_per_hold=3,
        queue_size=4,
    )
    writer.start("sess1")
    roi = np.zeros((17, 84, 3), dtype=np.uint8)
    # Hold A: 7 frames
    for i in range(7):
        roi[:] = i
        writer.offer(
            mono_s=float(i),
            wall_s=1000.0 + i,
            roi_bgr=roi,
            text="1:07.717",
            lap_time_ms=67_717,
            ok=True,
        )
    # Hold B: 2 frames (forces flush of A)
    for i in range(2):
        writer.offer(
            mono_s=10.0 + i,
            wall_s=1010.0 + i,
            roi_bgr=roi,
            text="1:08.100",
            lap_time_ms=68_100,
            ok=True,
        )
    status = writer.stop(join_timeout=5.0)
    jpg = sorted((tmp_path / "roi").glob("*.jpg"))
    # Hold A → 3, hold B → 2
    assert len(jpg) == 5, [p.name for p in jpg]
    assert status["frames_written"] == 5
    assert status["frames_seen"] == 9
    assert status["max_per_hold"] == 3
    manifest_lines = (tmp_path / "roi_manifest.jsonl").read_text().strip().splitlines()
    assert len(manifest_lines) == 5


def test_accuracy_session_ocr_log_full_rate_while_tee_capped(tmp_path: Path) -> None:
    settings = AccuracySettings(
        enabled=True,
        with_session=True,
        roi_tee=True,
        ocr_log=True,
        roi_tee_max_per_hold=3,
    )
    session = AccuracySession(settings, tmp_path)
    started = session.start("s1")
    assert started["ok"] is True
    roi = np.zeros((17, 84, 3), dtype=np.uint8)
    n = 12
    for i in range(n):
        session.on_sample(
            session_id="s1",
            mono_s=float(i),
            wall_s=2000.0 + i,
            ok=True,
            text="1:07.717",
            lap_time_ms=67_717,
            error="",
            roi_img=roi,
        )
    stopped = session.stop()
    assert stopped["ocr_samples"] == n
    ocr_path = tmp_path / "accuracy" / "s1" / "ocr_samples.jsonl"
    assert ocr_path.is_file()
    assert len(ocr_path.read_text().strip().splitlines()) == n
    jpg = list((tmp_path / "accuracy" / "s1" / "roi").glob("*.jpg"))
    assert len(jpg) == 3  # single hold → first/middle/last


def test_accuracy_settings_default_max_per_hold() -> None:
    assert AccuracySettings().roi_tee_max_per_hold == 3
    assert AccuracySettings().enabled is False
