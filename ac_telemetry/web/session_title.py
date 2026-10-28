"""UI-only session title formatting.

Display convention: ``DD/MM/YY HH:MM <hash4> <car> - <track>`` in
Europe/London. Storage, CSV, API payloads, and folder names are untouched —
callers format labels in the browser (or tests) from existing session fields.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

DISPLAY_TIMEZONE = "Europe/London"
_TZ = ZoneInfo(DISPLAY_TIMEZONE)

# Missing stamp / identity placeholders keep the title shape stable in lists.
_MISSING_STAMP = "--/--/-- --:--"
_MISSING_HASH = "----"
_MISSING_PART = "—"

# Browser twin of format_session_title — keep behaviour in lockstep with tests.
SESSION_TITLE_JS = r"""
function formatSessionTitle(session) {
  const s = session || {};
  const id = String(s.session_id || s.id || "");
  const hash4 = id ? id.slice(0, 4) : "----";
  const car = String(s.car || "").trim() || "\u2014";
  const track = String(s.track || "").trim() || "\u2014";
  let stamp = "--/--/-- --:--";
  if (s.started_at) {
    const d = new Date(s.started_at);
    if (!Number.isNaN(d.getTime())) {
      const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Europe/London",
        day: "2-digit",
        month: "2-digit",
        year: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }).formatToParts(d);
      const get = (type) => {
        const hit = parts.find((p) => p.type === type);
        return hit ? hit.value : "";
      };
      stamp =
        get("day") +
        "/" +
        get("month") +
        "/" +
        get("year") +
        " " +
        get("hour") +
        ":" +
        get("minute");
    }
  }
  return stamp + " " + hash4 + " " + car + " - " + track;
}
""".strip()


def _parse_started_at(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # CSV / API use ISO-8601; tolerate trailing Z from other producers.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_session_stamp(started_at: Any) -> str:
    """Format ``started_at`` as ``DD/MM/YY HH:MM`` in Europe/London."""
    dt = _parse_started_at(started_at)
    if dt is None:
        return _MISSING_STAMP
    local = dt.astimezone(_TZ)
    return local.strftime("%d/%m/%y %H:%M")


def format_session_title(session: Mapping[str, Any] | None) -> str:
    """Build the UI session title from existing session fields.

    Example: ``27/10/26 14:05 a3f9 Audi R8 LMS - Brands Hatch``.
    """
    s = session or {}
    sid = str(s.get("session_id") or s.get("id") or "")
    hash4 = sid[:4] if sid else _MISSING_HASH
    car = str(s.get("car") or "").strip() or _MISSING_PART
    track = str(s.get("track") or "").strip() or _MISSING_PART
    stamp = format_session_stamp(s.get("started_at"))
    return f"{stamp} {hash4} {car} - {track}"
