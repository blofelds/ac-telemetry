"""Current-session stint list helpers (phone UI).

Concept 1 — under the live strip: ``# · time · Δ to best`` with BEST tinted.
Uses existing ``GET /api/laps?session_id=`` rows; no schema change.
Browser twin lives in ``STINT_SCROLL_JS`` (keep behaviour in lockstep with tests).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

# Soft pit/traffic gate: grey rows at or above this multiple of session best.
OUTLIER_FACTOR = 1.5

# Browser twin of parse / best / delta — keep in lockstep with tests.
STINT_SCROLL_JS = r"""
function parseLapMs(row) {
  const raw = row && row.lap_time_ms;
  if (raw == null || raw === "") return null;
  const ms = Number(raw);
  return Number.isFinite(ms) && ms > 0 ? ms : null;
}

function formatDeltaMs(deltaMs) {
  // Concept 1: seconds to hundredths — +0.32 / BEST.
  const sec = Math.abs(deltaMs) / 1000;
  const body = sec.toFixed(2);
  if (deltaMs === 0) return "BEST";
  return (deltaMs > 0 ? "+" : "\u2212") + body;
}

function sessionBestMs(laps) {
  let best = null;
  for (const row of laps || []) {
    const ms = parseLapMs(row);
    if (ms == null) continue;
    if (best == null || ms < best) best = ms;
  }
  return best;
}

function stintRowClass(ms, bestMs) {
  if (ms == null) return "outlier";
  if (bestMs == null) return "";
  if (ms === bestMs) return "best";
  if (ms >= bestMs * 1.5) return "outlier";
  return "";
}
""".strip()


def parse_lap_ms(row: Mapping[str, Any] | None) -> int | None:
    """Positive ``lap_time_ms`` from a CSV/API lap row, or None."""
    if not row:
        return None
    raw = row.get("lap_time_ms")
    if raw is None or raw == "":
        return None
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        try:
            ms = int(float(str(raw)))
        except (TypeError, ValueError):
            return None
    return ms if ms > 0 else None


def format_delta_ms(delta_ms: int) -> str:
    """Format Δ-to-best as ``BEST``, ``+0.32``, or ``−0.32`` (hundredths)."""
    if delta_ms == 0:
        return "BEST"
    sec = abs(delta_ms) / 1000.0
    body = f"{sec:.2f}"
    return ("+" if delta_ms > 0 else "\u2212") + body


def session_best_ms(laps: Sequence[Mapping[str, Any]] | None) -> int | None:
    """Fastest positive ``lap_time_ms`` in the session, or None."""
    best: int | None = None
    for row in laps or ():
        ms = parse_lap_ms(row)
        if ms is None:
            continue
        if best is None or ms < best:
            best = ms
    return best


def stint_row_class(ms: int | None, best_ms: int | None) -> str:
    """CSS class for a stint row: ``best``, ``outlier``, or empty."""
    if ms is None:
        return "outlier"
    if best_ms is None:
        return ""
    if ms == best_ms:
        return "best"
    if ms >= int(best_ms * OUTLIER_FACTOR):
        return "outlier"
    return ""
