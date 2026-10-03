"""File / video capture backend: synthetic clip + PNG sequence."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from ac_telemetry.capture import FileFrameSource, build_source
from ac_telemetry.settings import CaptureProfile, Settings, load_settings, normalize_backend


def _profile() -> CaptureProfile:
    return CaptureProfile(
        name="pi2b",
        width=320,
        height=180,
        fps=10.0,
        max_width=1280,
        max_height=720,
        max_fps=15.0,
    )


def _write_synthetic_mp4(path: Path, *, frames: int = 6) -> None:
    """Tiny HUD-ish clip for offline tests (not a real AC dump)."""
    w, h = 320, 180
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, 10.0, (w, h))
    assert writer.isOpened(), "OpenCV could not open VideoWriter for test mp4"
    for i in range(frames):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:] = (20, 20, 20)
        # Fake last-lap digits area near the default 720p ROI scale.
        cv2.rectangle(frame, (20, 60), (100, 85), (240, 240, 240), -1)
        cv2.putText(
            frame,
            f"1:2{i}.00{i}",
            (24, 78),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (10, 10, 10),
            1,
            cv2.LINE_AA,
        )
        writer.write(frame)
    writer.release()


def _write_png_sequence(dir_path: Path, *, frames: int = 4) -> str:
    dir_path.mkdir(parents=True, exist_ok=True)
    for i in range(frames):
        img = np.full((180, 320, 3), 30 + i * 10, dtype=np.uint8)
        cv2.putText(
            img,
            str(i),
            (140, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            2.0,
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )
        cv2.imwrite(str(dir_path / f"frame_{i:04d}.png"), img)
    return str(dir_path / "frame_%04d.png")


def test_normalize_backend_aliases() -> None:
    assert normalize_backend("file") == "file"
    assert normalize_backend("video") == "file"
    assert normalize_backend("V4L2") == "v4l2"
    with pytest.raises(ValueError):
        normalize_backend("camera")


def test_file_source_reads_and_loops_mp4(tmp_path: Path) -> None:
    clip = tmp_path / "smoke.mp4"
    _write_synthetic_mp4(clip, frames=5)
    source = FileFrameSource(str(clip), _profile(), loop=True)
    width, height = source.open()
    assert width == 320
    assert height == 180
    got = 0
    for _ in range(12):  # more than clip length → must loop
        ok, frame = source.read()
        assert ok is True
        assert frame is not None
        assert frame.shape[0] == 180
        assert frame.shape[1] == 320
        got += 1
    source.close()
    assert got == 12


def test_file_source_stops_at_eof_without_loop(tmp_path: Path) -> None:
    clip = tmp_path / "once.mp4"
    _write_synthetic_mp4(clip, frames=3)
    source = FileFrameSource(str(clip), _profile(), loop=False)
    source.open()
    oks = []
    for _ in range(8):
        ok, _frame = source.read()
        oks.append(ok)
        if not ok:
            break
    source.close()
    assert any(oks)
    assert oks[-1] is False
    assert sum(1 for x in oks if x) == 3


def test_file_source_png_sequence(tmp_path: Path) -> None:
    pattern = _write_png_sequence(tmp_path / "seq", frames=4)
    source = FileFrameSource(pattern, _profile(), loop=True)
    source.open()
    for _ in range(6):
        ok, frame = source.read()
        assert ok is True
        assert frame is not None
    source.close()


def test_file_source_missing_path(tmp_path: Path) -> None:
    source = FileFrameSource(str(tmp_path / "missing.mp4"), _profile())
    with pytest.raises(RuntimeError, match="not found"):
        source.open()


def test_file_source_requires_file_path() -> None:
    source = FileFrameSource("", _profile())
    with pytest.raises(RuntimeError, match="file_path"):
        source.open()


def test_build_source_file_and_video_alias(tmp_path: Path) -> None:
    clip = tmp_path / "a.mp4"
    _write_synthetic_mp4(clip, frames=2)
    for backend in ("file", "video"):
        settings = Settings(
            backend=backend,  # type: ignore[arg-type]
            file_path=str(clip),
            loop=True,
            profiles={"pi2b": _profile()},
        )
        source = build_source(settings, _profile())
        assert isinstance(source, FileFrameSource)
        source.open()
        ok, frame = source.read()
        assert ok and frame is not None
        source.close()


def test_load_settings_nested_capture_block(tmp_path: Path) -> None:
    clip = tmp_path / "nested.mp4"
    _write_synthetic_mp4(clip, frames=2)
    cfg = tmp_path / "sandbox.yaml"
    cfg.write_text(
        f"""
profile: pi2b
port: 8742
capture:
  source: video
  file_path: {clip}
  loop: true
detect:
  enabled: false
""",
        encoding="utf-8",
    )
    settings = load_settings(cfg)
    assert settings.backend == "file"
    assert settings.file_path == str(clip)
    assert settings.loop is True
    assert settings.port == 8742
