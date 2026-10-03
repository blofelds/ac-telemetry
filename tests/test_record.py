"""In-app card-native record tee: start/stop API + file backend."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.record import FrameRecorder
from ac_telemetry.settings import load_settings
from ac_telemetry.store import SessionStore

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def _client(tmp_path: Path) -> tuple[TestClient, CaptureService, Path]:
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.record_dir = tmp_path / "recordings"
    settings.record_default_seconds = 5.0
    settings.record_max_seconds = 10.0
    settings.backend = "mock"
    store = SessionStore(settings.data_dir)
    store.ensure()
    capture = CaptureService(settings=settings)
    capture.stats.width = 1280
    capture.stats.height = 720
    capture.stats.target_fps = 10.0
    app = create_app(settings, capture, store)
    return TestClient(app), capture, settings.record_dir


def test_record_status_idle(tmp_path: Path) -> None:
    client, _capture, record_dir = _client(tmp_path)
    r = client.get("/api/debug/record/status")
    assert r.status_code == 200
    body = r.json()
    assert body["recording"] is False
    assert body["record_dir"] == str(record_dir)
    assert body["record_max_seconds"] == 10.0


def test_record_start_stop_writes_1280x720(tmp_path: Path) -> None:
    client, capture, record_dir = _client(tmp_path)
    start = client.post(
        "/api/debug/record/start",
        json={"duration_seconds": 3},
    )
    assert start.status_code == 200, start.text
    body = start.json()
    assert body["ok"] is True
    assert body["recording"] is True
    path = Path(body["path"])
    assert path.parent == record_dir
    assert path.suffix in {".avi", ".mkv"}

    # Tee synthetic full frames the way the capture loop would.
    for i in range(12):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:] = (10, 20 + i, 30)
        assert capture.recorder is not None
        capture.recorder.offer_frame(frame)
        time.sleep(0.12)

    stop = client.post("/api/debug/record/stop")
    assert stop.status_code == 200, stop.text
    stopped = stop.json()
    assert stopped["recording"] is False
    assert stopped["finished"] is True
    assert stopped["frames_written"] >= 1
    assert path.is_file()
    assert path.stat().st_size > 0

    cap = cv2.VideoCapture(str(path))
    assert cap.isOpened()
    ok, frame = cap.read()
    cap.release()
    assert ok
    assert frame is not None
    assert frame.shape[1] == 1280
    assert frame.shape[0] == 720

    status = client.get("/api/debug/record/status").json()
    assert status["recording"] is False
    assert status["frames_written"] >= 1


def test_record_rejects_over_max_duration(tmp_path: Path) -> None:
    client, _capture, _dir = _client(tmp_path)
    r = client.post(
        "/api/debug/record/start",
        json={"duration_seconds": 999},
    )
    assert r.status_code == 400
    assert "max_seconds" in r.json()["detail"]


def test_record_rejects_double_start(tmp_path: Path) -> None:
    client, capture, _dir = _client(tmp_path)
    assert client.post("/api/debug/record/start", json={"duration_seconds": 5}).status_code == 200
    second = client.post("/api/debug/record/start", json={"duration_seconds": 5})
    assert second.status_code == 409
    # Cleanup
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert capture.recorder is not None
    capture.recorder.offer_frame(frame)
    client.post("/api/debug/record/stop")


def test_frame_recorder_direct_file(tmp_path: Path) -> None:
    """Unit-level: recorder writes a readable clip at requested geometry."""
    rec = FrameRecorder(
        output_dir=tmp_path,
        default_seconds=2,
        max_seconds=5,
        fps=2.0,
    )
    status = rec.start(duration_seconds=2, width=1280, height=720, fps=2.0)
    path = Path(status["path"])
    for _ in range(6):
        rec.offer_frame(np.full((720, 1280, 3), 40, dtype=np.uint8))
        time.sleep(0.15)
    done = rec.stop()
    assert done["frames_written"] >= 1
    assert path.is_file()
    cap = cv2.VideoCapture(str(path))
    ok, frame = cap.read()
    cap.release()
    assert ok and frame is not None
    assert (frame.shape[1], frame.shape[0]) == (1280, 720)
