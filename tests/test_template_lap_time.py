"""Tests for OpenCV digit-template lap-time reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from ac_telemetry.detect.readers import (
    TemplateLapTimeReader,
    build_lap_time_reader,
    resolve_templates_dir,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lap_time"
TEMPLATES_720P = resolve_templates_dir("templates/lap_time_digits/ac_720p")
TEMPLATES_1080P = resolve_templates_dir("templates/lap_time_digits/ac_1080p")


def _cv2():
    return pytest.importorskip("cv2")


def test_build_template_aliases() -> None:
    a = build_lap_time_reader("template", templates_dir=TEMPLATES_720P)
    b = build_lap_time_reader("assetto_corsa", templates_dir=TEMPLATES_720P)
    assert a.name == "template"
    assert b.name == "template"
    assert isinstance(a, TemplateLapTimeReader)


def test_template_reader_reads_synthetic_720p_crop() -> None:
    cv2 = _cv2()
    path = FIXTURES / "1_44_321.png"
    assert path.is_file(), path
    image = cv2.imread(str(path))
    assert image is not None
    reader = TemplateLapTimeReader(TEMPLATES_720P)
    reading = reader.read(image)
    assert reading.ok, reading.error
    assert reading.text == "1:44.321"
    assert reading.lap_time_ms == 104_321


def test_template_reader_reads_synthetic_1080p_crop() -> None:
    cv2 = _cv2()
    path = FIXTURES / "1_44_321_1080.png"
    image = cv2.imread(str(path))
    assert image is not None
    reader = TemplateLapTimeReader(TEMPLATES_1080P)
    reading = reader.read(image)
    assert reading.ok, reading.error
    assert reading.text == "1:44.321"


def test_template_reader_empty_roi() -> None:
    reader = TemplateLapTimeReader(TEMPLATES_720P)
    reading = reader.read(None)
    assert not reading.ok
    assert "empty ROI" in reading.error


def test_template_reader_missing_dir() -> None:
    reader = TemplateLapTimeReader("/tmp/ac-telemetry-missing-templates-xyz")
    reading = reader.read(None)
    # ensure() fails before empty-ROI check when templates missing
    reading2 = reader.read(__import__("numpy").zeros((10, 40, 3), dtype="uint8"))
    assert not reading2.ok
    assert "unavailable" in reading2.error or "not found" in reading2.error.lower()
