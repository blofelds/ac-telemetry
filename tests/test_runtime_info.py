"""Runtime identity helpers used by debug dumps and the phone UI footer."""

from __future__ import annotations

from ac_telemetry import runtime_info
from ac_telemetry.runtime_info import short_git_sha
from ac_telemetry.web import STATUS_HTML


def test_short_git_sha_truncates(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_info,
        "git_identity",
        lambda: {"git_sha": "abcdef0123456789deadbeef", "git_dirty": False},
    )
    assert short_git_sha() == "abcdef01"
    assert short_git_sha(length=12) == "abcdef012345"


def test_short_git_sha_unknown_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_info,
        "git_identity",
        lambda: {"git_sha": None, "git_dirty": None},
    )
    assert short_git_sha() == "unknown"


def test_status_html_footer_embeds_commit() -> None:
    assert 'class="build"' in STATUS_HTML
    assert "commit " in STATUS_HTML
    assert "__GIT_SHA__" not in STATUS_HTML
    # Real checkout → short hex; otherwise the explicit fallback.
    marker = STATUS_HTML.split('class="build">', 1)[1].split("</div>", 1)[0]
    assert marker.startswith("commit ")
    token = marker.removeprefix("commit ").strip()
    assert token == "unknown" or (
        7 <= len(token) <= 12 and all(c in "0123456789abcdef" for c in token.lower())
    )
