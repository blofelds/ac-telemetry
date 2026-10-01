"""Tests for OpenCV digit-template lap-time reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from ac_telemetry.detect.readers import (
    TemplateLapTimeReader,
    build_lap_time_reader,
    resolve_templates_dir,
)
from ac_telemetry.detect.template_matcher import _column_spans

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lap_time"
TEMPLATES_720P = resolve_templates_dir("templates/lap_time_digits/ac_720p")
TEMPLATES_1080P = resolve_templates_dir("templates/lap_time_digits/ac_1080p")
TEMPLATES_CAPTURE = resolve_templates_dir(
    "templates/lap_time_digits/ac_720p_capture"
)
TEMPLATES_PI = resolve_templates_dir("templates/lap_time_digits/ac_720p_pi")


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


def test_template_reader_reads_ac_720p_capture_vlc_crop() -> None:
    """Real AC LAST crop (VLC 720p) against capture-derived midtone glyphs.

    Regression for ``no glyphs matched in ROI`` / digit soup when grayscale
    Save-glyph PNGs were matched against binary ``white_mask`` probes without
    load-time normalize, and 1px colon spans were dropped.
    """
    cv2 = _cv2()
    path = FIXTURES / "ac_720p_capture_1_03_168.png"
    assert path.is_file(), path
    image = cv2.imread(str(path))
    assert image is not None
    reader = TemplateLapTimeReader(TEMPLATES_CAPTURE)
    reading = reader.read(image)
    assert reading.ok, reading.error
    assert reading.text == "1:03.168"
    assert reading.lap_time_ms == 63_168


def test_pi_templates_rematch_live_dump_digits() -> None:
    """Live Pi dump ROI rematches digit labels with ac_720p_pi (not 796719).

    Ground truth ``1:35.113``. Capture-domain templates chose ``796719``.
    Live-sourced ``1``/``3``/``5`` should label spans ``135113``. Separators
    are still missing from the mask path — parse may fail until a follow-on
    separator fix; this test only asserts digit labels beat the dump failure.
    """
    cv2 = _cv2()
    from ac_telemetry.detect.template_matcher import DigitTemplateMatcher

    path = FIXTURES / "ac_720p_pi_1_35_113.png"
    assert path.is_file(), path
    image = cv2.imread(str(path))
    assert image is not None

    matcher = DigitTemplateMatcher(TEMPLATES_PI)
    assert matcher.has_templates
    assert matcher.missing_digits == list("0246789")
    raw, diag = matcher.read_symbols_with_diagnostics(image)
    chosen = [g["chosen"] for g in diag["glyphs"]]
    assert chosen == ["1", "3", "5", "1", "1", "3"], chosen
    assert raw == "135113"
    assert raw != "796719"

    # Reader surface: digits OK, separators still absent → pattern fail (F).
    reader = TemplateLapTimeReader(TEMPLATES_PI)
    reading = reader.read(image)
    assert reading.text == "135113"
    assert not reading.ok
    assert "no lap-time pattern" in (reading.error or "")


def test_column_spans_keep_single_pixel_colon() -> None:
    import numpy as np

    # Two digits with a 1-column colon between them (count>=2 each col).
    mask = np.zeros((12, 20), np.uint8)
    mask[:, 1:4] = 255
    mask[2:5, 7] = 255
    mask[7:10, 7] = 255
    mask[:, 10:18] = 255
    assert _column_spans(mask) == [(1, 4), (7, 8), (10, 18)]


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
