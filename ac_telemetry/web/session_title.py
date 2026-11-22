"""UI-only session title formatting.

Phone History layout A, dossier header B, and current-strip B share
``format_session_identity`` (``track · car``), with stamp/hash demoted to a
muted meta line. History shows a compact live cue only while running.

Legacy ``format_session_title`` remains available:
``DD/MM/YY HH:MM <hash4> <car> - <track>`` in Europe/London.

Accuracy picker (mockup A + short hash) uses ``format_accuracy_session_title``:
``<track> · <car> · DD/MM HH:MM · <hash4>`` — GT suffix is applied by the
picker (`` · GT confirmed`` / `` · GT``).

Storage, CSV, API payloads, and folder names are untouched — callers format
labels in the browser (or tests) from existing session fields.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

DISPLAY_TIMEZONE = "Europe/London"
_TZ = ZoneInfo(DISPLAY_TIMEZONE)

# Missing stamp / identity placeholders keep the title shape stable in lists.
_MISSING_STAMP = "--/--/-- --:--"
_MISSING_STAMP_SHORT = "--/-- --:--"
_MISSING_HASH = "----"
_MISSING_PART = "—"

# Browser twin of the Python formatters — keep behaviour in lockstep with tests.
SESSION_TITLE_JS = r"""
function _sessionIdHash4(session) {
  const s = session || {};
  const id = String(s.session_id || s.id || "");
  return id ? id.slice(0, 4) : "----";
}

function _sessionParts(session) {
  const s = session || {};
  return {
    hash4: _sessionIdHash4(s),
    car: String(s.car || "").trim() || "\u2014",
    track: String(s.track || "").trim() || "\u2014",
  };
}

function _formatStampParts(startedAt, { withYear }) {
  if (!startedAt) {
    return withYear ? "--/--/-- --:--" : "--/-- --:--";
  }
  const d = new Date(startedAt);
  if (Number.isNaN(d.getTime())) {
    return withYear ? "--/--/-- --:--" : "--/-- --:--";
  }
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
  const dayMonth = get("day") + "/" + get("month");
  const hm = get("hour") + ":" + get("minute");
  if (withYear) {
    return dayMonth + "/" + get("year") + " " + hm;
  }
  return dayMonth + " " + hm;
}

function formatSessionStamp(startedAt) {
  return _formatStampParts(startedAt, { withYear: true });
}

function formatSessionStampShort(startedAt) {
  return _formatStampParts(startedAt, { withYear: false });
}

// Dossier B / Current B / History A call sites that pass the session object.
function sessionHash4(session) {
  return _sessionIdHash4(session);
}

function formatSessionHash4(session) {
  return _sessionIdHash4(session);
}

function sessionStamp(session) {
  const s = session || {};
  return formatSessionStamp(s.started_at);
}

function formatSessionIdentity(session) {
  // History A / Dossier B / Current B: track · car
  const { car, track } = _sessionParts(session);
  return track + " \u00b7 " + car;
}

function formatSessionTitle(session) {
  const s = session || {};
  const { hash4, car, track } = _sessionParts(s);
  const stamp = formatSessionStamp(s.started_at);
  return stamp + " " + hash4 + " " + car + " - " + track;
}

function formatAccuracySessionTitle(session) {
  // Accuracy picker A: track · car · DD/MM HH:MM · hash4
  const s = session || {};
  const { hash4, car, track } = _sessionParts(s);
  const stamp = formatSessionStampShort(s.started_at);
  return track + " \u00b7 " + car + " \u00b7 " + stamp + " \u00b7 " + hash4;
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


def _session_fields(session: Mapping[str, Any] | None) -> tuple[str, str, str]:
    s = session or {}
    sid = str(s.get("session_id") or s.get("id") or "")
    hash4 = sid[:4] if sid else _MISSING_HASH
    car = str(s.get("car") or "").strip() or _MISSING_PART
    track = str(s.get("track") or "").strip() or _MISSING_PART
    return hash4, car, track


def format_session_stamp(started_at: Any) -> str:
    """Format ``started_at`` as ``DD/MM/YY HH:MM`` in Europe/London."""
    dt = _parse_started_at(started_at)
    if dt is None:
        return _MISSING_STAMP
    local = dt.astimezone(_TZ)
    return local.strftime("%d/%m/%y %H:%M")


def format_session_stamp_short(started_at: Any) -> str:
    """Format ``started_at`` as ``DD/MM HH:MM`` in Europe/London (no year)."""
    dt = _parse_started_at(started_at)
    if dt is None:
        return _MISSING_STAMP_SHORT
    local = dt.astimezone(_TZ)
    return local.strftime("%d/%m %H:%M")


def format_session_hash4(session: Mapping[str, Any] | None) -> str:
    """First four characters of session id, or ``----`` when missing."""
    hash4, _, _ = _session_fields(session)
    return hash4


def format_session_identity(session: Mapping[str, Any] | None) -> str:
    """Brief History / dossier / current-strip title: ``track · car``."""
    _, car, track = _session_fields(session)
    return f"{track} · {car}"


def format_session_title(session: Mapping[str, Any] | None) -> str:
    """Build the legacy full session title.

    Example: ``27/10/26 14:05 a3f9 Audi R8 LMS - Brands Hatch``.
    """
    hash4, car, track = _session_fields(session)
    stamp = format_session_stamp((session or {}).get("started_at"))
    return f"{stamp} {hash4} {car} - {track}"


def format_accuracy_session_title(session: Mapping[str, Any] | None) -> str:
    """Build Accuracy picker title A with short hash before the GT suffix.

    Example: ``Vallelunga Club · Abarth · 22/11 14:05 · a3f9``.
    The picker appends `` · GT confirmed`` or `` · GT`` when confirmed.
    """
    hash4, car, track = _session_fields(session)
    stamp = format_session_stamp_short((session or {}).get("started_at"))
    return f"{track} · {car} · {stamp} · {hash4}"
