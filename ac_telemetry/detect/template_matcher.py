"""OpenCV template matching for Assetto Corsa block-font digits.

Ported from blofelds/acc-telemetry ``ac_speed_reader`` — smallest useful
slice for live Pi capture. Prefer this when Tesseract misreads AC's block
font; keep ``mock`` / ``tesseract`` available as alternate readers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Default canvas matches acc-telemetry speed_digits/ac_1080p (H×W).
_DEFAULT_CANVAS = (28, 24)
_MATCH_THRESHOLD = 0.50


def white_mask(roi_bgr: Any) -> Any:
    """Keep white digit strokes; drop the dark cabin behind them."""
    import cv2

    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (0, 0, 150), (180, 80, 255))


def segment_glyphs(roi_bgr: Any, *, min_rows: int = 3) -> list[Any]:
    """Return one binary glyph per ink blob, left to right.

    ``min_rows`` is lower than the speed reader (6) so colon/period dots
    survive segmentation inside a lap-time crop.
    """
    if roi_bgr is None or getattr(roi_bgr, "size", 0) == 0:
        return []
    mask = white_mask(roi_bgr)
    glyphs: list[Any] = []
    for start, end in _column_spans(mask):
        glyph = _trim_rows(mask[:, start:end], min_rows=min_rows)
        if glyph is not None:
            glyphs.append(glyph)
    return glyphs


def _column_spans(mask: Any) -> list[tuple[int, int]]:
    """Ink runs left-to-right.

    Width may be 1: AC ``:`` / ``.`` are often a single bright column after
    ``white_mask``. Requiring ``>= 2`` dropped the colon on real 720p crops
    and produced digit soup like ``183188`` instead of ``1:03.168``.
    """
    counts = (mask > 0).sum(axis=0)
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for x, count in enumerate(counts):
        if count >= 2 and start is None:
            start = x
        elif count < 2 and start is not None:
            if x - start >= 1:
                spans.append((start, x))
            start = None
    if start is not None and mask.shape[1] - start >= 1:
        spans.append((start, mask.shape[1]))
    return spans


def _trim_rows(glyph: Any, *, min_rows: int) -> Any | None:
    import numpy as np

    rows = np.where(glyph.any(axis=1))[0]
    if len(rows) < min_rows:
        return None
    return glyph[rows[0] : rows[-1] + 1, :]


def _trim_to_ink(mask: Any) -> Any | None:
    """Crop a binary mask to its ink bounding box (rows and columns)."""
    import numpy as np

    if mask is None or getattr(mask, "size", 0) == 0:
        return None
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    return mask[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]

def pad_glyph(
    glyph: Any,
    height: int = _DEFAULT_CANVAS[0],
    width: int = _DEFAULT_CANVAS[1],
) -> Any:
    """Center a glyph on a fixed canvas (scale down only — matches templates).

    Templates from acc-telemetry already include padding inside the canvas.
    Upscaling ink to fill the canvas would disagree with that layout and kill
    match scores for smaller 720p crops; prefer the matching ``ac_720p`` set.
    """
    import cv2
    import numpy as np

    canvas = np.zeros((height, width), np.uint8)
    image = glyph
    h, w = image.shape[:2]
    if h < 1 or w < 1:
        return canvas
    if h > height or w > width:
        scale = min(width / w, height / h)
        image = cv2.resize(
            image,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_NEAREST,
        )
        h, w = image.shape[:2]
    y0 = max(0, (height - h) // 2)
    x0 = max(0, (width - w) // 2)
    yh = min(h, height - y0)
    xw = min(w, width - x0)
    canvas[y0 : y0 + yh, x0 : x0 + xw] = image[:yh, :xw]
    return canvas


class DigitTemplateMatcher:
    """Match segmented glyphs against saved 0–9 / colon / period templates."""

    def __init__(
        self,
        template_dir: str | Path,
        *,
        match_threshold: float = _MATCH_THRESHOLD,
    ) -> None:
        self.template_dir = Path(template_dir)
        self.match_threshold = float(match_threshold)
        self.templates = self._load_templates(self.template_dir)
        # Infer canvas from any loaded digit template.
        sample = next(
            (self.templates[d] for d in "0123456789" if d in self.templates),
            None,
        )
        if sample is not None:
            self.canvas = (int(sample.shape[0]), int(sample.shape[1]))
        else:
            self.canvas = _DEFAULT_CANVAS

    @property
    def has_templates(self) -> bool:
        """True when at least one digit PNG loaded.

        Live Pi sets may be incomplete (only digits seen on-capture). Matching
        still works for those labels; missing digits simply cannot win.
        """
        return any(d in self.templates for d in "0123456789")

    @property
    def missing_digits(self) -> list[str]:
        return [d for d in "0123456789" if d not in self.templates]

    def match_glyph(self, glyph: Any) -> str | None:
        """Return ``'0'-'9'``, ``':'``, ``'.'``, or None."""
        label, _candidates, _threshold = self.match_glyph_detailed(glyph)
        return label

    def match_glyph_detailed(
        self, glyph: Any
    ) -> tuple[str | None, list[dict[str, Any]], float]:
        """Same decision as ``match_glyph``, plus scored candidates for dumps.

        Match thresholds and separators are unchanged — this only retains the
        ``TM_CCOEFF_NORMED`` floats that were previously discarded.
        """
        digit_threshold = self.match_threshold
        digit, digit_scores = self._best_label(
            glyph,
            labels=tuple("0123456789"),
            threshold=digit_threshold,
        )
        if digit is not None:
            return digit, digit_scores, digit_threshold

        h, w = int(glyph.shape[0]), int(glyph.shape[1])
        narrow = w <= max(8, int(self.canvas[1] * 0.45))
        if not narrow:
            return None, digit_scores, digit_threshold

        sep_threshold = min(0.35, self.match_threshold)
        sep, sep_scores = self._best_label(
            glyph, labels=(".", ":"), threshold=sep_threshold
        )
        # Merge digit + separator score tables (sorted by score desc).
        merged = sorted(
            digit_scores + sep_scores,
            key=lambda row: row["score"],
            reverse=True,
        )
        if sep is not None:
            return sep, merged, sep_threshold
        ink = int((glyph > 0).sum())
        if ink < 60:
            heuristic = "." if h < int(self.canvas[0] * 0.45) else ":"
            return heuristic, merged, sep_threshold
        return None, merged, digit_threshold

    def _best_label(
        self,
        glyph: Any,
        *,
        labels: tuple[str, ...],
        threshold: float,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        import cv2

        scores: list[dict[str, Any]] = []
        best: str | None = None
        best_score = float(threshold)
        for label in labels:
            template = self.templates.get(label)
            if template is None:
                continue
            th, tw = int(template.shape[0]), int(template.shape[1])
            probe = pad_glyph(glyph, th, tw).astype("float32")
            if probe.shape[0] < th or probe.shape[1] < tw:
                continue
            score = float(
                cv2.matchTemplate(probe, template, cv2.TM_CCOEFF_NORMED).max()
            )
            scores.append({"label": label, "score": round(score, 4)})
            if score > best_score:
                best_score = score
                best = label
        scores.sort(key=lambda row: row["score"], reverse=True)
        return best, scores

    def read_symbols(self, roi_bgr: Any) -> str | None:
        """Match every glyph left-to-right into a raw symbol string."""
        raw, _diag = self.read_symbols_with_diagnostics(roi_bgr)
        return raw

    def read_symbols_with_diagnostics(
        self, roi_bgr: Any
    ) -> tuple[str | None, dict[str, Any]]:
        """Match glyphs and retain spans / per-glyph scores for a detect dump.

        Does not change match decisions — only records what ``match_glyph``
        already computed so failure dumps can explain low scores vs empty ink.
        """
        import numpy as np

        empty: dict[str, Any] = {
            "white_mask": {"v_min": 150, "s_max": 80, "ink_pixels": 0},
            "spans": [],
            "glyphs": [],
            "mask": None,
            "canvas": {"height": self.canvas[0], "width": self.canvas[1]},
            "match_threshold": self.match_threshold,
            "templates_dir": str(self.template_dir),
            "template_labels": sorted(self.templates.keys()),
        }
        if roi_bgr is None or getattr(roi_bgr, "size", 0) == 0:
            return None, empty

        mask = white_mask(roi_bgr)
        ink_pixels = int((mask > 0).sum())
        spans = _column_spans(mask)
        span_rows: list[dict[str, Any]] = []
        glyph_rows: list[dict[str, Any]] = []
        symbols: list[str] = []
        failed = False

        for start, end in spans:
            width = end - start
            ink_rows = int((mask[:, start:end] > 0).sum(axis=0).max()) if width else 0
            # Approximate ink-row count as rows with any ink in the span.
            ink_row_count = int(np.count_nonzero((mask[:, start:end] > 0).any(axis=1)))
            span_rows.append(
                {
                    "x0": int(start),
                    "x1": int(end),
                    "width": int(width),
                    "ink_rows": ink_row_count,
                    "max_col_ink": ink_rows,
                }
            )
            # Match segment_glyphs: drop spans that fail min_rows (do not fail).
            glyph = _trim_rows(mask[:, start:end], min_rows=3)
            if glyph is None:
                continue
            label, candidates, threshold = self.match_glyph_detailed(glyph)
            glyph_rows.append(
                {
                    "index": len(glyph_rows),
                    "span": [int(start), int(end)],
                    "candidates": candidates[:8],
                    "chosen": label,
                    "threshold": threshold,
                    "canvas": {
                        "height": int(self.canvas[0]),
                        "width": int(self.canvas[1]),
                    },
                }
            )
            if label is None:
                failed = True
                break
            symbols.append(label)

        diag: dict[str, Any] = {
            "white_mask": {
                "v_min": 150,
                "s_max": 80,
                "ink_pixels": ink_pixels,
            },
            "spans": span_rows,
            "glyphs": glyph_rows,
            "mask": mask,
            "canvas": {"height": self.canvas[0], "width": self.canvas[1]},
            "match_threshold": self.match_threshold,
            "templates_dir": str(self.template_dir.resolve()),
            "template_labels": sorted(self.templates.keys()),
        }
        if failed or not symbols:
            return None, diag
        return _normalize_time_symbols("".join(symbols)), diag

    @staticmethod
    def _load_templates(template_dir: Path) -> dict[str, Any]:
        """Load digit PNGs and normalize to the same space as ROI probes.

        Save-glyph / VLC crops are midtone RGB on a dark pad. Live matching
        probes are ``white_mask`` binary blobs trimmed to ink. Comparing those
        directly with ``matchTemplate`` mis-ranks lookalikes (0→8, 6→8) and
        fails thin separators. Binarize + trim + pad onto one canvas so probes
        and templates share geometry.
        """
        import cv2
        import numpy as np

        if not template_dir.is_dir():
            raise FileNotFoundError(
                f"Digit templates not found: {template_dir}"
            )

        raw: dict[str, Any] = {}
        for digit in "0123456789":
            path = template_dir / f"{digit}.png"
            if not path.is_file():
                continue
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"Unreadable digit template {path}")
            trimmed = _trim_to_ink(white_mask(image))
            if trimmed is None:
                raise ValueError(
                    f"Digit template {path} has no ink after white_mask; "
                    "re-crop a brighter glyph."
                )
            raw[digit] = trimmed

        if not raw:
            raise FileNotFoundError(
                f"No digit templates under {template_dir}. "
                "Need at least one of 0.png … 9.png."
            )

        for filename, label in (("colon.png", ":"), ("period.png", ".")):
            path = template_dir / filename
            if not path.is_file():
                continue
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                continue
            trimmed = _trim_to_ink(white_mask(image))
            if trimmed is not None:
                raw[label] = trimmed

        # Common canvas from digit ink boxes (separators are tiny).
        digit_shapes = [raw[d].shape for d in "0123456789" if d in raw]
        canvas_h = max(h for h, _w in digit_shapes)
        canvas_w = max(w for _h, w in digit_shapes)
        return {
            label: pad_glyph(glyph, canvas_h, canvas_w).astype(np.float32)
            for label, glyph in raw.items()
        }



def _normalize_time_symbols(raw: str) -> str | None:
    """Insert a missing ``.`` when period ink was too faint to segment.

    AC last-lap HUD is ``M:SS.mmm`` / ``MM:SS.mmm``. Colon usually survives
    as two stacked dots; the decimal can vanish on a small 720p crop. If we
    already have ``M:SSmmm`` (5–6 digits + one colon), restore the period.
    """
    if not raw:
        return None
    if "." in raw:
        return raw
    # e.g. 1:44321 → 1:44.321 ; 12:34567 → 12:34.567
    import re

    match = re.fullmatch(r"(\d{1,2}):(\d{5})", raw)
    if match:
        minutes, rest = match.group(1), match.group(2)
        return f"{minutes}:{rest[:2]}.{rest[2:]}"
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(\d{3})", raw)
    if match:
        return f"{match.group(1)}:{match.group(2)}.{match.group(3)}"
    return raw
