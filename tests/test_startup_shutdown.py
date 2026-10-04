"""Startup / Ctrl-C: open timeout + SIGINT must exit (not leave uvicorn running)."""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from ac_telemetry.capture import (
    CaptureService,
    FrameSource,
    _v4l2_source_arg,
)
from ac_telemetry.main import needs_opencv, preload_opencv_if_needed
from ac_telemetry.settings import CaptureProfile, load_settings


def test_needs_opencv_for_file_v4l2_and_template_detect() -> None:
    mock_detect = SimpleNamespace(
        enabled=True, lap_time=SimpleNamespace(reader="mock")
    )
    assert needs_opencv(SimpleNamespace(backend="mock", detect=mock_detect)) is False
    assert needs_opencv(SimpleNamespace(backend="file", detect=mock_detect)) is True
    assert needs_opencv(SimpleNamespace(backend="v4l2", detect=mock_detect)) is True
    template_detect = SimpleNamespace(
        enabled=True, lap_time=SimpleNamespace(reader="template")
    )
    assert (
        needs_opencv(SimpleNamespace(backend="mock", detect=template_detect)) is True
    )
    assert needs_opencv(
        SimpleNamespace(backend="mock", detect=SimpleNamespace(enabled=False))
    ) is False


def test_preload_opencv_skipped_for_mock() -> None:
    settings = SimpleNamespace(
        backend="mock",
        detect=SimpleNamespace(enabled=True, lap_time=SimpleNamespace(reader="mock")),
    )
    assert preload_opencv_if_needed(settings) == 0.0


def test_v4l2_source_arg_maps_dev_path_and_digits() -> None:
    assert _v4l2_source_arg("/dev/video0") == 0
    assert _v4l2_source_arg("/dev/video2") == 2
    assert _v4l2_source_arg("0") == 0
    assert _v4l2_source_arg(" 1 ") == 1
    assert _v4l2_source_arg("/dev/videoX") == "/dev/videoX"


class _HangOpenSource:
    """FrameSource whose open() blocks until cancelled via close()."""

    def __init__(self) -> None:
        self._release = threading.Event()
        self.opened = False

    def open(self) -> tuple[int, int]:
        self._release.wait(timeout=60.0)
        self.opened = True
        return 320, 180

    def read(self) -> tuple[bool, object | None]:
        return False, None

    def close(self) -> None:
        self._release.set()


def test_capture_open_timeout_surfaces_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings()
    settings.backend = "mock"
    settings.data_dir = tmp_path / "sessions"
    settings.record_dir = tmp_path / "recordings"
    settings.capture_open_timeout_seconds = 0.3
    settings.profiles = {
        "pi2b": CaptureProfile(
            name="pi2b",
            width=320,
            height=180,
            fps=5.0,
            max_width=1280,
            max_height=720,
            max_fps=15.0,
        )
    }
    settings.profile = "pi2b"

    hung = _HangOpenSource()

    def _fake_build_source(_settings, _profile) -> FrameSource:
        return hung  # type: ignore[return-value]

    monkeypatch.setattr("ac_telemetry.capture.build_source", _fake_build_source)
    capture = CaptureService(settings=settings)
    capture.start()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not capture.stats.last_error:
        time.sleep(0.05)
    capture.stop(timeout=1.0, recorder_join_timeout=0.5)
    assert "timed out" in (capture.stats.last_error or "").lower()


def test_sigint_exits_mock_server_quickly(tmp_path: Path) -> None:
    """Regression: custom SIGINT used to stop workers but leave uvicorn running."""
    repo = Path(__file__).resolve().parents[1]
    data_dir = tmp_path / "sessions"
    data_dir.mkdir()
    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "AC_TELEMETRY_BACKEND": "mock",
        "AC_TELEMETRY_PORT": "18743",
        "AC_TELEMETRY_HOST": "127.0.0.1",
        "AC_TELEMETRY_DATA_DIR": str(data_dir),
        "AC_TELEMETRY_DETECT_DEBUG_DUMP": "0",
    }
    # Disable detect templates / keep detect mock via YAML override in config.
    cfg = tmp_path / "mock.yaml"
    cfg.write_text(
        "\n".join(
            [
                "profile: pi2b",
                "backend: mock",
                "host: '127.0.0.1'",
                "port: 18743",
                f"data_dir: {data_dir}",
                "detect:",
                "  enabled: true",
                "  fps: 1.0",
                "  lap_time:",
                "    reader: mock",
                "    mock_interval_seconds: 60",
                "  debug_dump:",
                "    enabled: false",
                "profiles:",
                "  pi2b:",
                "    width: 320",
                "    height: 180",
                "    fps: 5",
                "    max_width: 1280",
                "    max_height: 720",
                "    max_fps: 15",
            ]
        ),
        encoding="utf-8",
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "ac_telemetry.main", "--config", str(cfg)],
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        import socket

        ready_deadline = time.monotonic() + 30.0
        while time.monotonic() < ready_deadline:
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                pytest.fail(f"process exited early rc={proc.returncode}: {out}")
            try:
                with socket.create_connection(("127.0.0.1", 18743), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            proc.send_signal(signal.SIGKILL)
            out = proc.stdout.read() if proc.stdout else ""
            pytest.fail(f"server did not listen within 30s: {out}")

        t0 = time.perf_counter()
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=8.0)
        except subprocess.TimeoutExpired:
            proc.send_signal(signal.SIGKILL)
            out = proc.stdout.read() if proc.stdout else ""
            pytest.fail(f"SIGINT did not exit within 8s: {out}")
        elapsed = time.perf_counter() - t0
        assert elapsed < 8.0
        assert proc.returncode is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
