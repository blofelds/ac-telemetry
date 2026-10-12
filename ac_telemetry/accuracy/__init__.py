"""Optional stint LAST accuracy tooling (ROI tee + OCR log + GT scores).

**Default off.** Isolated package — enable via ``accuracy.enabled`` /
``AC_TELEMETRY_ACCURACY_ENABLED=1``. Core detect/CSV does not import this
module; ``main`` wires an optional ``on_sample`` hook only when enabled.

Disable: set ``accuracy.enabled: false`` (YAML default) or env ``0``/``false``.
Remove later: delete this package + ``accuracy`` config block + the thin
wiring in ``main.py`` / ``api`` / ``settings`` (see docs/STINT_ACCURACY.md).
"""

from __future__ import annotations

from ac_telemetry.accuracy.session import AccuracySession, maybe_accuracy_session
from ac_telemetry.settings import AccuracySettings

__all__ = [
    "AccuracySession",
    "AccuracySettings",
    "maybe_accuracy_session",
]
