"""Detect dump API: last failure JSON + lossless ROI/mask PNGs."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.detect import DetectService
from ac_telemetry.detect.readers import resolve_templates_dir
from ac_telemetry.settings import RoiRect, load_settings
from ac_telemetry.store import LapStore, SessionStore

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

TEMPLATES_CAPTURE = resolve_templates_dir(
    "templates/lap_time_digits/ac_720p_capture"
)


def _app_with_detect(tmp_path: Path) -> tuple[TestClient, DetectService, CaptureService]:
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    settings.detect.enabled = True
    settings.detect.debug_dump.enabled = True
    settings.detect.debug_dump.on_success = False
    settings.detect.lap_time.reader = "template"
    settings.detect.lap_time.templates_dir = str(TEMPLATES_CAPTURE)
    settings.rois = {
        "lap_time": RoiRect(x=0, y=0, width=84, height=17),
    }
    store = SessionStore(settings.data_dir)
    store.ensure()
    lap_store = LapStore(settings.data_dir)
    lap_store.ensure()
    capture = CaptureService(settings=settings)
    detect = DetectService(
        settings=settings,
        get_frame=capture.get_latest_frame,
        get_session_id=lambda: None,
        record_lap=lap_store.append_lap,
        get_capture_info=lambda: capture.stats.as_dict(),
    )
    # Build reader without starting the background thread.
    from ac_telemetry.detect.readers import build_lap_time_reader

    detect._reader = build_lap_time_reader(
        "template",
        templates_dir=TEMPLATES_CAPTURE,
        match_threshold=settings.detect.lap_time.match_threshold,
    )
    detect.state.enabled = True
    detect.state.reader = "template"
    app = create_app(
        settings, capture, store, lap_store=lap_store, detect=detect
    )
    return TestClient(app), detect, capture


def test_detect_dump_endpoints_empty_before_failure(tmp_path: Path) -> None:
    client, _detect, _capture = _app_with_detect(tmp_path)
    assert client.get("/api/debug/detect/last.json").status_code == 404
    assert client.get("/api/debug/detect/last_roi.png").status_code == 503
    assert client.get("/api/debug/detect/last_mask.png").status_code == 503


def test_detect_dump_on_fixture_failure_path(tmp_path: Path) -> None:
    """Black ROI → no glyphs matched; dump retains exact crop + mask + scores."""
    client, detect, capture = _app_with_detect(tmp_path)

    frame = np.zeros((48, 128, 3), dtype=np.uint8)
    with capture._frame_lock:
        capture._latest_frame = frame
        capture.stats.frames = 42
        capture.stats.last_frame_at = __import__("time").time()

    detect._tick(detect.settings.detect)

    assert detect.state.last_error == "no glyphs matched in ROI"
    assert detect.state.failures >= 1

    info = client.get("/api/debug/info").json()
    assert info["has_detect_dump"] is True
    assert info["templates_dir"]
    assert "match_threshold" in info
    assert info["match_threshold"] == 0.5

    meta = client.get("/api/debug/detect/last.json")
    assert meta.status_code == 200
    body = meta.json()
    assert body["ok"] is False
    assert body["error"] == "no glyphs matched in ROI"
    assert body["roi"]["width"] == 84
    assert body["white_mask"]["ink_pixels"] == 0
    assert body["spans"] == []
    assert body["glyphs"] == []
    assert body["config"]["reader"] == "template"
    assert body["config"]["match_threshold"] == 0.5
    assert body["runtime"]["opencv_version"]
    assert body["frame"]["capture_frames"] == 42
    assert body["frame"]["roi_sha256"]

    roi = client.get("/api/debug/detect/last_roi.png")
    assert roi.status_code == 200
    assert roi.headers["content-type"] == "image/png"
    assert roi.content[:8] == b"\x89PNG\r\n\x1a\n"
    decoded = cv2.imdecode(np.frombuffer(roi.content, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[0] == 17 and decoded.shape[1] == 84

    mask = client.get("/api/debug/detect/last_mask.png")
    assert mask.status_code == 200
    assert mask.content[:8] == b"\x89PNG\r\n\x1a\n"
    mask_arr = cv2.imdecode(
        np.frombuffer(mask.content, dtype=np.uint8), cv2.IMREAD_GRAYSCALE
    )
    assert mask_arr is not None
    assert int((mask_arr > 0).sum()) == 0

    annotated = client.get("/api/debug/detect/last_annotated.png")
    assert annotated.status_code == 200
    assert annotated.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_detect_dump_keeps_glyph_scores_on_soft_fail(tmp_path: Path) -> None:
    """Ink segments but does not match templates → chosen null + candidates."""
    client, detect, capture = _app_with_detect(tmp_path)

    # Bright vertical bars that pass white_mask / column spans but are not
    # real digit shapes — scores stay below the 0.50 threshold.
    h, w = 17, 84
    detect.settings.rois["lap_time"] = RoiRect(x=0, y=0, width=w, height=h)
    crop = np.zeros((h, w, 3), dtype=np.uint8)
    for x0, x1 in ((4, 10), (16, 22), (30, 40), (48, 54), (60, 78)):
        crop[:, x0:x1] = (255, 255, 255)
        # Poke a hole so the blob is not a solid rectangle identical to any template.
        crop[3:6, x0 + 1 : x1 - 1] = (0, 0, 0)
        crop[10:13, x0 + 1 : x1 - 1] = (0, 0, 0)

    frame = np.zeros((h + 4, w + 4, 3), dtype=np.uint8)
    frame[0:h, 0:w] = crop
    with capture._frame_lock:
        capture._latest_frame = frame
        capture.stats.frames = 7

    detect._tick(detect.settings.detect)
    resp = client.get("/api/debug/detect/last.json")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] == "no glyphs matched in ROI"
    assert body["white_mask"]["ink_pixels"] > 0
    assert len(body["spans"]) >= 1
    assert len(body["glyphs"]) >= 1
    first = body["glyphs"][0]
    assert first["chosen"] is None
    assert first["candidates"]
    assert first["candidates"][0]["score"] < first["threshold"]
    assert first["candidates"][0]["label"] in list("0123456789") + [":", "."]

    roi = client.get("/api/debug/detect/last_roi.png")
    assert roi.status_code == 200
    decoded = cv2.imdecode(np.frombuffer(roi.content, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[0] == h and decoded.shape[1] == w
