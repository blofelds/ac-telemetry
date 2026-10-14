"""GT eyeballing helper — crops, confirm API, stint CSV note/times."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ac_telemetry.accuracy.helper import (
    GT_CONFIRMED_NOTE,
    resolve_roi_file,
    select_display_crops,
)
from ac_telemetry.accuracy.paths import gt_draft_path, gt_path, session_dir
from ac_telemetry.api import create_app
from ac_telemetry.capture import CaptureService
from ac_telemetry.settings import load_settings
from ac_telemetry.store import LapStore, SessionStore
from ac_telemetry.store.laps import LAP_FIELDS


def test_select_display_crops_first_and_last() -> None:
    frames = [{"seq": i} for i in (1, 2, 3)]
    picked = select_display_crops(frames, max_display=2)
    assert [f["seq"] for f in picked] == [1, 3]


def test_select_display_crops_when_only_two() -> None:
    frames = [{"seq": 1}, {"seq": 2}]
    assert select_display_crops(frames, max_display=2) == frames


def test_lap_store_note_column_migration(tmp_path: Path) -> None:
    data_dir = tmp_path / "sessions"
    data_dir.mkdir(parents=True)
    legacy = data_dir / "laps.csv"
    legacy.write_text(
        "session_id,lap_number,lap_time,lap_time_ms,recorded_at,source,raw_text\n"
        "s1,1,1:07.717,67717,2026-01-01T00:00:00+00:00,mock,1:07.717\n",
        encoding="utf-8",
    )
    store = LapStore(data_dir)
    store.ensure()
    header = legacy.read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == LAP_FIELDS
    rows = store.list_laps(session_id="s1", limit=10)
    assert rows[0]["lap_time"] == "1:07.717"
    assert rows[0].get("note", "") == ""


def test_lap_store_update_session_laps_note_and_times(tmp_path: Path) -> None:
    store = LapStore(tmp_path / "sessions")
    store.ensure()
    store.append_lap(
        {
            "session_id": "s1",
            "lap_number": 1,
            "lap_time": "1:07.717",
            "lap_time_ms": 67_717,
            "source": "mock",
            "raw_text": "1:07.717",
        }
    )
    store.append_lap(
        {
            "session_id": "s1",
            "lap_number": 2,
            "lap_time": "1:08.100",
            "lap_time_ms": 68_100,
            "source": "mock",
            "raw_text": "1:08.100",
        }
    )
    store.append_lap(
        {
            "session_id": "other",
            "lap_number": 1,
            "lap_time": "2:00.000",
            "lap_time_ms": 120_000,
            "source": "mock",
            "raw_text": "2:00.000",
        }
    )
    result = store.update_session_laps(
        "s1",
        note=GT_CONFIRMED_NOTE,
        lap_updates=[
            {"lap_number": 1, "lap_time": "1:07.800"},
            {"lap_number": 2, "lap_time": "1:08.100"},
        ],
    )
    assert result["updated"] == 2
    assert result["times_changed"] == 1
    s1 = list(reversed(store.list_laps(session_id="s1", limit=10)))
    assert [r["note"] for r in s1] == [GT_CONFIRMED_NOTE, GT_CONFIRMED_NOTE]
    assert s1[0]["lap_time"] == "1:07.800"
    assert s1[0]["lap_time_ms"] == "67800"
    assert s1[1]["lap_time"] == "1:08.100"
    other = store.list_laps(session_id="other", limit=5)[0]
    assert other.get("note", "") == ""
    assert other["lap_time"] == "2:00.000"


def _enabled_client(tmp_path: Path) -> tuple[TestClient, SessionStore, LapStore, Path]:
    from ac_telemetry.accuracy import maybe_accuracy_session

    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    settings.accuracy.enabled = True
    settings.accuracy.roi_tee = False
    settings.accuracy.ocr_log = True
    settings.accuracy.with_session = False

    store = SessionStore(settings.data_dir)
    store.ensure()
    lap_store = LapStore(settings.data_dir)
    lap_store.ensure()
    capture = CaptureService(settings=settings)
    accuracy = maybe_accuracy_session(settings.accuracy, settings.data_dir)
    assert accuracy is not None
    app = create_app(
        settings,
        capture,
        store,
        lap_store=lap_store,
        accuracy=accuracy,
    )
    return TestClient(app), store, lap_store, settings.data_dir


def test_helper_routes_404_when_disabled(tmp_path: Path) -> None:
    settings = load_settings()
    settings.data_dir = tmp_path / "sessions"
    settings.backend = "mock"
    settings.accuracy.enabled = False
    store = SessionStore(settings.data_dir)
    store.ensure()
    capture = CaptureService(settings=settings)
    app = create_app(settings, capture, store, accuracy=None)
    client = TestClient(app)
    assert client.get("/accuracy").status_code == 404
    assert client.get("/api/accuracy/sessions/x/helper").status_code == 404


def test_helper_page_and_confirm(tmp_path: Path) -> None:
    client, store, lap_store, data_dir = _enabled_client(tmp_path)
    created = client.post(
        "/api/sessions", json={"track": "Monza", "car": "Test", "notes": ""}
    )
    assert created.status_code == 201
    sid = created.json()["session"]["session_id"]
    client.post("/api/sessions/current/end")

    lap_store.append_lap(
        {
            "session_id": sid,
            "lap_number": 1,
            "lap_time": "1:07.717",
            "lap_time_ms": 67_717,
            "source": "mock",
            "raw_text": "1:07.717",
        }
    )
    lap_store.append_lap(
        {
            "session_id": sid,
            "lap_number": 2,
            "lap_time": "1:08.200",
            "lap_time_ms": 68_200,
            "source": "mock",
            "raw_text": "1:08.200",
        }
    )

    # Tee artefacts: three frames in one hold → helper shows first+last.
    sdir = session_dir(data_dir, sid, subdir="accuracy")
    roi = sdir / "roi"
    roi.mkdir(parents=True)
    manifest_lines = []
    for seq, mono in ((1, 100), (2, 200), (3, 300)):
        name = f"{seq:06d}_{mono}.jpg"
        (roi / name).write_bytes(b"\xff\xd8\xff\xd9")  # minimal JPEG marker
        manifest_lines.append(
            json.dumps(
                {
                    "seq": seq,
                    "session_id": sid,
                    "mono_s": mono / 1000.0,
                    "wall_s": 1000.0 + seq,
                    "ok": True,
                    "text": "1:07.717",
                    "lap_time_ms": 67_717,
                    "path": f"roi/{name}",
                }
            )
        )
    # Second hold for lap 2 (two frames only).
    for seq, mono in ((4, 400), (5, 500)):
        name = f"{seq:06d}_{mono}.jpg"
        (roi / name).write_bytes(b"\xff\xd8\xff\xd9")
        manifest_lines.append(
            json.dumps(
                {
                    "seq": seq,
                    "session_id": sid,
                    "mono_s": mono / 1000.0,
                    "wall_s": 2000.0 + seq,
                    "ok": True,
                    "text": "1:08.200",
                    "lap_time_ms": 68_200,
                    "path": f"roi/{name}",
                }
            )
        )
    (sdir / "roi_manifest.jsonl").write_text(
        "\n".join(manifest_lines) + "\n", encoding="utf-8"
    )

    page = client.get("/accuracy")
    assert page.status_code == 200
    assert "GT eyeball" in page.text

    page_sid = client.get(f"/accuracy/{sid}")
    assert page_sid.status_code == 200

    helper = client.get(f"/api/accuracy/sessions/{sid}/helper")
    assert helper.status_code == 200
    body = helper.json()
    assert body["session_id"] == sid
    assert len(body["laps"]) == 2
    assert len(body["laps"][0]["crops"]) == 2
    assert body["laps"][0]["crops"][0]["seq"] == 1
    assert body["laps"][0]["crops"][1]["seq"] == 3
    assert len(body["laps"][1]["crops"]) == 2
    assert body["laps"][1]["crops"][0]["seq"] == 4
    assert body["laps"][1]["crops"][1]["seq"] == 5

    crop = client.get(body["laps"][0]["crops"][0]["url"])
    assert crop.status_code == 200
    assert crop.headers["content-type"].startswith("image/jpeg")

    # Non-JPEG / unsafe names rejected (URL normalizers may collapse "../").
    assert (
        client.get(f"/api/accuracy/sessions/{sid}/roi/not-a-jpeg.png").status_code
        == 400
    )
    from ac_telemetry.accuracy.helper import resolve_roi_file
    import pytest

    with pytest.raises(ValueError):
        resolve_roi_file(
            data_dir=data_dir,
            session_id=sid,
            filename="../gt.json",
            subdir="accuracy",
        )

    confirmed = client.post(
        f"/api/accuracy/sessions/{sid}/gt/confirm",
        json={
            "laps": [
                {
                    "lap_time": "1:07.800",
                    "csv_lap_number": 1,
                    "note": "gt_confirmed",
                },
                {
                    "lap_time": "1:08.200",
                    "csv_lap_number": 2,
                },
            ],
            "score": True,
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    payload = confirmed.json()
    assert payload["ok"] is True
    assert payload["csv_laps_updated"] == 2
    assert payload["csv_note"] == GT_CONFIRMED_NOTE
    assert payload["score"]["write_pct"] == 100.0

    draft = gt_draft_path(sdir)
    gt = gt_path(sdir)
    assert draft.is_file()
    assert gt.is_file()
    draft_data = json.loads(draft.read_text(encoding="utf-8"))
    assert draft_data["laps"][0]["lap_time"] == "1:07.800"

    chrono = list(reversed(lap_store.list_laps(session_id=sid, limit=10)))
    assert all(r["note"] == GT_CONFIRMED_NOTE for r in chrono)
    assert chrono[0]["lap_time"] == "1:07.800"
    assert chrono[0]["lap_time_ms"] == "67800"
    assert chrono[1]["lap_time"] == "1:08.200"
