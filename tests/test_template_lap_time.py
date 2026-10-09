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
    Full live-sourced ``0–9`` set labels digit spans; midtone gap recovery
    restores ``:`` / ``.`` so parse succeeds.
    """
    cv2 = _cv2()
    from ac_telemetry.detect.template_matcher import DigitTemplateMatcher

    path = FIXTURES / "ac_720p_pi_1_35_113.png"
    assert path.is_file(), path
    image = cv2.imread(str(path))
    assert image is not None

    matcher = DigitTemplateMatcher(TEMPLATES_PI)
    assert matcher.has_templates
    assert matcher.missing_digits == []
    assert ":" in matcher.templates and "." in matcher.templates
    raw, diag = matcher.read_symbols_with_diagnostics(image)
    digits = [g["chosen"] for g in diag["glyphs"] if g["chosen"] not in (None, ".", ":")]
    assert digits == ["1", "3", "5", "1", "1", "3"], digits
    assert raw == "1:35.113"
    assert raw != "796719"

    reader = TemplateLapTimeReader(TEMPLATES_PI)
    reading = reader.read(image)
    assert reading.ok, reading.error
    assert reading.text == "1:35.113"
    assert reading.lap_time_ms == 95_113


def test_pi_templates_rematch_dump_2_34_492_digits() -> None:
    """Second live dump covers ``2``/``4``/``9`` from the completed Pi set.

    Ground truth ``2:34.492`` (dump ``20261002-000013``). Colon may come from
    midtone gap match; period can fall back to digit-soup normalize.
    """
    cv2 = _cv2()
    from ac_telemetry.detect.template_matcher import DigitTemplateMatcher

    path = FIXTURES / "ac_720p_pi_2_34_492.png"
    assert path.is_file(), path
    image = cv2.imread(str(path))
    assert image is not None

    matcher = DigitTemplateMatcher(TEMPLATES_PI)
    assert matcher.missing_digits == []
    raw, diag = matcher.read_symbols_with_diagnostics(image)
    digits = [g["chosen"] for g in diag["glyphs"] if g["chosen"] not in (None, ".", ":")]
    assert digits == ["2", "3", "4", "4", "9", "2"], digits
    assert raw == "2:34.492"

    reader = TemplateLapTimeReader(TEMPLATES_PI)
    reading = reader.read(image)
    assert reading.ok, reading.error
    assert reading.text == "2:34.492"
    assert reading.lap_time_ms == 154_492


def test_pi_templates_rematch_dump_1_07_960_span_recovery() -> None:
    """Dump ``20261002-002656``: span recovery + separator recovery → parse.

    Ground truth ``1:07.960``. Span recovery yields digits ``107960``; midtone
    gap match inserts ``:`` / ``.`` (normalize remains the digit-soup fallback).
    """
    cv2 = _cv2()
    from ac_telemetry.detect.template_matcher import DigitTemplateMatcher

    path = FIXTURES / "ac_720p_pi_1_07_960.png"
    assert path.is_file(), path
    image = cv2.imread(str(path))
    assert image is not None

    matcher = DigitTemplateMatcher(TEMPLATES_PI)
    assert matcher.missing_digits == []
    raw, diag = matcher.read_symbols_with_diagnostics(image)
    digits = [g["chosen"] for g in diag["glyphs"] if g["chosen"] not in (None, ".", ":")]
    seps = [g for g in diag["glyphs"] if g.get("role") == "separator"]
    assert digits == ["1", "0", "7", "9", "6", "0"], digits
    assert raw == "1:07.960"
    assert {g["chosen"] for g in seps} == {":", "."}
    assert None not in digits

    reader = TemplateLapTimeReader(TEMPLATES_PI)
    reading = reader.read(image)
    assert reading.ok, reading.error
    assert reading.text == "1:07.960"
    assert reading.lap_time_ms == 67_960
    assert reading.error != "no glyphs matched in ROI"


def test_normalize_restores_digit_only_separators() -> None:
    from ac_telemetry.detect.template_matcher import _normalize_time_symbols

    assert _normalize_time_symbols("107960") == "1:07.960"
    assert _normalize_time_symbols("103168") == "1:03.168"
    assert _normalize_time_symbols("146177") == "1:46.177"
    assert _normalize_time_symbols("1246177") == "12:46.177"
    assert _normalize_time_symbols("1:07960") == "1:07.960"
    # Seconds ≥ 60 must not become a fake lap time.
    assert _normalize_time_symbols("199999") == "199999"


def test_column_spans_keep_single_pixel_colon() -> None:
    import numpy as np

    # Two digits with a 1-column colon between them (count>=2 each col).
    mask = np.zeros((12, 20), np.uint8)
    mask[:, 1:4] = 255
    mask[2:5, 7] = 255
    mask[7:10, 7] = 255
    mask[:, 10:18] = 255
    assert _column_spans(mask) == [(1, 4), (7, 8), (10, 18)]


def test_column_spans_absorb_thin_bridge_and_split_glue() -> None:
    """Synthetic: multi-col 1-ink bridge + oversized glued run."""
    import numpy as np

    from ac_telemetry.detect.template_matcher import (
        _absorb_thin_bridges,
        _raw_column_spans,
        _split_oversized_spans,
    )

    mask = np.zeros((12, 40), np.uint8)
    # Digit A (wide)
    mask[:, 2:8] = 255
    # 1-ink bridge (top-bar style) — must be >=2 cols to absorb
    mask[0, 8:12] = 255
    # Narrow stem
    mask[:, 12:15] = 255
    # Glued pair: two peaks with a valley at x=27
    mask[:, 18:27] = 255
    mask[:, 27] = 0
    mask[2:6, 27] = 255  # weak valley (4 ink rows)
    mask[:, 28:36] = 255
    # Boost edges so valley is a local min near midpoint
    mask[:, 18] = 255
    mask[:, 26] = 255
    mask[:, 28] = 255
    mask[:, 35] = 255

    raw = _raw_column_spans(mask)
    assert (12, 15) in raw or any(s == 12 for s, _e in raw)
    absorbed = _absorb_thin_bridges(mask, raw)
    # Stem span should start at bridge start (8)
    assert any(s == 8 and e == 15 for s, e in absorbed), absorbed

    # Oversized glue alone
    glue = np.zeros((12, 30), np.uint8)
    glue[:, 2:14] = 255
    glue[:, 14] = 40  # will set properly below
    glue[:, 14] = 0
    glue[4:8, 14] = 255  # valley count=4
    glue[:, 15:26] = 255
    glue[0:12, 2] = 255
    glue[0:12, 13] = 255
    glue[0:12, 15] = 255
    glue[0:12, 25] = 255
    spans = [(2, 26)]
    split = _split_oversized_spans(glue, spans, typical_width=11)
    assert len(split) == 2, split
    assert split[0][1] == split[1][0]
    assert all(e - s <= 16 for s, e in split), split


def test_column_spans_skips_single_col_bridge() -> None:
    """A lone 1-ink speck between full digits must not be absorbed."""
    import numpy as np

    from ac_telemetry.detect.template_matcher import _absorb_thin_bridges

    mask = np.zeros((12, 30), np.uint8)
    mask[:, 2:12] = 255
    mask[5, 12] = 255  # single speck
    mask[:, 13:23] = 255
    raw = [(2, 12), (13, 23)]
    assert _absorb_thin_bridges(mask, raw) == raw


def test_column_spans_merge_narrow_single_bridge_and_leading_topbar() -> None:
    """Split ``7`` body/stem + orphaned 1-ink top bar rejoin for soft capture."""
    import numpy as np

    from ac_telemetry.detect.template_matcher import (
        _absorb_leading_one_ink,
        _absorb_narrow_single_bridge,
    )

    # Narrow stub | 1-ink gap | narrow stem → one digit-sized span
    mask = np.zeros((12, 24), np.uint8)
    mask[:, 4:7] = 255
    mask[0, 7] = 255
    mask[:, 8:11] = 255
    merged = _absorb_narrow_single_bridge(mask, [(4, 7), (8, 11)])
    assert merged == [(4, 11)], merged

    # Full-width digits with a 1-ink speck must stay split
    wide = np.zeros((12, 30), np.uint8)
    wide[:, 2:12] = 255
    wide[5, 12] = 255
    wide[:, 13:23] = 255
    assert _absorb_narrow_single_bridge(wide, [(2, 12), (13, 23)]) == [
        (2, 12),
        (13, 23),
    ]

    # Orphaned top bar (count==1) left of a narrow stem
    top = np.zeros((12, 20), np.uint8)
    top[0, 3:8] = 255  # five 1-ink cols
    top[:, 8:11] = 255  # stem
    extended = _absorb_leading_one_ink(top, [(8, 11)])
    assert extended == [(3, 11)], extended


def test_pi_templates_load_soft_variants() -> None:
    """``7b.png`` / ``8b.png`` share labels; canvas stays primary-sized."""
    from ac_telemetry.detect.template_matcher import DigitTemplateMatcher

    matcher = DigitTemplateMatcher(TEMPLATES_PI)
    assert len(matcher.templates["7"]) >= 2
    assert len(matcher.templates["8"]) >= 2
    # Primary canvas for ac_720p_pi digits is 12×11 after pad.
    assert matcher.canvas == (12, 11)
    assert all(t.shape == matcher.canvas for t in matcher.templates["8"])


def test_pi_templates_card_long_soft_1_18_795() -> None:
    """Card-long soft LAST ``1:18.795`` — span recovery + soft ``7b``/``8b``.

    Baseline Pi templates alone read this crop as ``1:19.195`` (``8→9``,
    severed ``7→1``). Soft variants + ``7`` span recovery restore GT.
    """
    cv2 = _cv2()
    path = FIXTURES / "ac_720p_pi_card_long_1_18_795.png"
    assert path.is_file(), path
    image = cv2.imread(str(path))
    assert image is not None
    reader = TemplateLapTimeReader(TEMPLATES_PI)
    reading = reader.read(image)
    assert reading.ok, reading.error
    assert reading.text == "1:18.795"
    assert reading.lap_time_ms == 78_795


def test_lookalike_margin_rejects_tight_3_vs_8() -> None:
    """Synthetic: ``8`` barely beating ``3`` must fail closed."""
    import numpy as np

    from ac_telemetry.detect.template_matcher import DigitTemplateMatcher

    matcher = DigitTemplateMatcher(TEMPLATES_PI)
    # Build a probe from the primary ``3`` template ink (already padded).
    glyph3 = (matcher.templates["3"][0] > 0).astype(np.uint8) * 255
    # Trim to ink like live probes.
    from ac_telemetry.detect.template_matcher import _trim_to_ink

    trimmed = _trim_to_ink(glyph3)
    assert trimmed is not None
    label, scores, _thr = matcher.match_glyph_detailed(trimmed)
    # Clear ``3`` must still win.
    assert label == "3", (label, scores[:3])

    # Force a near-tie: report reject helper directly.
    fake = [
        {"label": "8", "score": 0.689},
        {"label": "3", "score": 0.688},
    ]
    assert matcher._lookalike_margin_reject("8", fake) is True
    fake_clear = [
        {"label": "3", "score": 0.77},
        {"label": "8", "score": 0.45},
    ]
    assert matcher._lookalike_margin_reject("3", fake_clear) is False


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
