"""ROI debug JPEG helpers and API (skip encode tests without OpenCV)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.settings import RoiRect, load_settings
from ac_telemetry.store import SessionStore

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def _client(tmp_path: Path) -> tuple[TestClient, CaptureService]:
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    settings.detect.enabled = False
    settings.rois = {
        "lap_time": RoiRect(x=10, y=20, width=40, height=12),
    }
    store = SessionStore(settings.data_dir)
    store.ensure()
    capture = CaptureService(settings=settings)
    app = create_app(settings, capture, store)
    return TestClient(app), capture


def test_debug_endpoints_without_frame_return_503(tmp_path: Path) -> None:
    client, _capture = _client(tmp_path)
    assert client.get("/api/debug/frame.jpg").status_code == 503
    assert client.get("/api/debug/roi/lap_time.jpg").status_code == 503
    assert client.get("/api/debug/overlay/lap_time.jpg").status_code == 503
    assert client.get("/api/debug/roi/missing.jpg").status_code == 404


def test_debug_info_and_page(tmp_path: Path) -> None:
    client, _capture = _client(tmp_path)
    info = client.get("/api/debug/info").json()
    assert info["roi"]["width"] == 40
    assert info["frame"]["available"] is False
    page = client.get("/debug")
    assert page.status_code == 200
    assert "ROI debug" in page.text
    assert "last_error" in page.text


def test_jpeg_from_injected_frame(tmp_path: Path) -> None:
    client, capture = _client(tmp_path)
    # Synthetic BGR frame with a bright ROI patch.
    frame = np.zeros((72, 128, 3), dtype=np.uint8)
    frame[20:32, 10:50] = (0, 0, 200)
    with capture._frame_lock:
        capture._latest_frame = frame

    full = client.get("/api/debug/frame.jpg")
    assert full.status_code == 200
    assert full.headers["content-type"] == "image/jpeg"
    assert full.content[:2] == b"\xff\xd8"

    crop = client.get("/api/debug/roi/lap_time.jpg")
    assert crop.status_code == 200
    assert crop.content[:2] == b"\xff\xd8"
    # Crop should be smaller than the full frame JPEG for this solid patch.
    assert len(crop.content) < len(full.content)

    overlay = client.get("/api/debug/overlay/lap_time.jpg")
    assert overlay.status_code == 200
    assert overlay.content[:2] == b"\xff\xd8"

    info = client.get("/api/debug/info").json()
    assert info["frame"]["available"] is True
