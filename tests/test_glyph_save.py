"""Glyph save API — cut real AC digit PNGs from a fake lap_time ROI."""

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


def _client(tmp_path: Path) -> tuple[TestClient, CaptureService, Path]:
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.glyphs_dir = tmp_path / "glyphs"
    settings.backend = "mock"
    settings.detect.enabled = False
    settings.rois = {
        "lap_time": RoiRect(x=10, y=20, width=40, height=12),
    }
    store = SessionStore(settings.data_dir)
    store.ensure()
    capture = CaptureService(settings=settings)
    app = create_app(settings, capture, store)
    return TestClient(app), capture, settings.glyphs_dir


def _inject_frame(capture: CaptureService) -> None:
    frame = np.zeros((72, 128, 3), dtype=np.uint8)
    # Bright white-ish digits strip inside the ROI (BGR).
    frame[20:32, 10:50] = (220, 220, 220)
    frame[22:30, 14:18] = (255, 255, 255)
    with capture._frame_lock:
        capture._latest_frame = frame


def test_save_glyph_requires_frame(tmp_path: Path) -> None:
    client, _capture, glyphs_dir = _client(tmp_path)
    r = client.post("/api/debug/glyphs/save", json={"symbol": "5"})
    assert r.status_code == 400
    assert "No frame" in r.json()["detail"]
    assert not glyphs_dir.exists() or not any(glyphs_dir.rglob("*.png"))


def test_save_named_glyph_and_pending(tmp_path: Path) -> None:
    client, capture, glyphs_dir = _client(tmp_path)
    _inject_frame(capture)

    named = client.post("/api/debug/glyphs/save", json={"symbol": "5"})
    assert named.status_code == 200
    body = named.json()
    assert body["ok"] is True
    assert body["filename"] == "5.png"
    assert body["width"] == 40 and body["height"] == 12
    path = Path(body["path"])
    assert path.is_file()
    assert path.parent == glyphs_dir
    decoded = cv2.imread(str(path), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[0] == 12 and decoded.shape[1] == 40

    colon = client.post("/api/debug/glyphs/save", json={"symbol": ":"})
    assert colon.status_code == 200
    assert colon.json()["filename"] == "colon.png"
    assert (glyphs_dir / "colon.png").is_file()

    period = client.post("/api/debug/glyphs/save", json={"symbol": "period"})
    assert period.status_code == 200
    assert period.json()["filename"] == "period.png"

    pending = client.post("/api/debug/glyphs/save", json={})
    assert pending.status_code == 200
    pbody = pending.json()
    assert pbody["filename"].endswith(".png")
    assert Path(pbody["path"]).parent.name == "pending"
    assert Path(pbody["path"]).is_file()


def test_save_glyph_subcrop(tmp_path: Path) -> None:
    client, capture, glyphs_dir = _client(tmp_path)
    _inject_frame(capture)

    r = client.post(
        "/api/debug/glyphs/save",
        json={"symbol": "1", "x": 4, "y": 2, "width": 8, "height": 8},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "1.png"
    assert body["width"] == 8 and body["height"] == 8
    decoded = cv2.imread(str(glyphs_dir / "1.png"), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[0] == 8 and decoded.shape[1] == 8


def test_save_glyph_rejects_bad_symbol_and_roi(tmp_path: Path) -> None:
    client, capture, _glyphs_dir = _client(tmp_path)
    _inject_frame(capture)

    bad = client.post("/api/debug/glyphs/save", json={"symbol": "X"})
    assert bad.status_code == 400

    missing = client.post(
        "/api/debug/glyphs/save",
        json={"roi_name": "nope", "symbol": "0"},
    )
    assert missing.status_code == 404


def test_debug_page_mentions_save_glyph(tmp_path: Path) -> None:
    client, _capture, _glyphs_dir = _client(tmp_path)
    page = client.get("/debug")
    assert page.status_code == 200
    assert "Save glyph" in page.text
    assert "/api/debug/glyphs/save" in page.text
    info = client.get("/api/debug/info").json()
    assert "glyphs_dir" in info
