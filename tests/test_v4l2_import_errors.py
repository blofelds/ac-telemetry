"""V4L2 OpenCV import failures must surface the real cause."""

from __future__ import annotations

import builtins
from typing import Any

import pytest

from ac_telemetry.capture import V4L2FrameSource, _v4l2_cv2_import_failure
from ac_telemetry.settings import CaptureProfile


def _profile() -> CaptureProfile:
    return CaptureProfile(
        name="pi2b",
        width=640,
        height=480,
        fps=10.0,
        max_width=1280,
        max_height=720,
        max_fps=15.0,
    )


def test_helper_suggests_capture_extra_only_when_cv2_missing() -> None:
    exc = ModuleNotFoundError("No module named 'cv2'", name="cv2")
    err = _v4l2_cv2_import_failure(exc)
    assert isinstance(err, RuntimeError)
    msg = str(err)
    assert ".[capture]" in msg or "ac-telemetry[capture]" in msg
    # Pi 2B path prefers apt OpenCV; x86 may still use the capture extra.
    assert "python3-opencv" in msg or "opencv-python-headless" in msg
    assert "SIGILL" in msg or "system-site-packages" in msg


def test_helper_surfaces_openblas_shared_lib_error() -> None:
    exc = ImportError(
        "libopenblas.so.0: cannot open shared object file: No such file or directory"
    )
    err = _v4l2_cv2_import_failure(exc)
    msg = str(err)
    assert "libopenblas.so.0" in msg
    assert "apt install libopenblas0" in msg
    assert ".[capture]" not in msg


def test_helper_surfaces_numpy_load_error() -> None:
    exc = ImportError("numpy.core.multiarray failed to import")
    err = _v4l2_cv2_import_failure(exc)
    msg = str(err)
    assert "numpy" in msg.lower()
    assert "libopenblas0" in msg
    assert ".[capture]" not in msg


def test_open_chains_openblas_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any):
        if name == "cv2" or name.startswith("cv2."):
            raise ImportError(
                "libopenblas.so.0: cannot open shared object file: "
                "No such file or directory"
            )
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    source = V4L2FrameSource("/dev/video0", _profile())
    with pytest.raises(RuntimeError) as raised:
        source.open()
    msg = str(raised.value)
    assert "libopenblas.so.0" in msg
    assert ".[capture]" not in msg
    assert raised.value.__cause__ is not None
    assert "libopenblas" in str(raised.value.__cause__).lower()


def test_open_suggests_capture_when_cv2_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any):
        if name == "cv2" or name.startswith("cv2."):
            raise ModuleNotFoundError("No module named 'cv2'", name="cv2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    source = V4L2FrameSource("/dev/video0", _profile())
    with pytest.raises(RuntimeError) as raised:
        source.open()
    msg = str(raised.value)
    assert "python3-opencv" in msg or "opencv-python-headless" in msg
    assert ".[capture]" in msg or "ac-telemetry[capture]" in msg
