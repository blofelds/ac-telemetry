"""Cheap runtime identity for debug dumps (git SHA, OpenCV, versions)."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def git_identity() -> dict[str, Any]:
    """Best-effort ``git rev-parse`` for the running checkout."""
    root = _repo_root()
    sha = None
    dirty = None
    try:
        sha = (
            subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            .decode("utf-8", errors="replace")
            .strip()
            or None
        )
        status = (
            subprocess.check_output(
                ["git", "-C", str(root), "status", "--porcelain"],
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            .decode("utf-8", errors="replace")
            .strip()
        )
        dirty = bool(status)
    except (OSError, subprocess.SubprocessError):
        pass
    return {"git_sha": sha, "git_dirty": dirty}


@lru_cache(maxsize=1)
def library_versions() -> dict[str, Any]:
    opencv = None
    numpy_v = None
    try:
        import cv2

        opencv = getattr(cv2, "__version__", None)
    except Exception:  # noqa: BLE001
        pass
    try:
        import numpy

        numpy_v = getattr(numpy, "__version__", None)
    except Exception:  # noqa: BLE001
        pass
    return {"opencv_version": opencv, "numpy_version": numpy_v}


def runtime_snapshot(*, app_version: str = "0.3.0") -> dict[str, Any]:
    """Small dict safe to embed in ``/api/debug/info`` and detect dumps."""
    out = {"app_version": app_version}
    out.update(git_identity())
    out.update(library_versions())
    return out
