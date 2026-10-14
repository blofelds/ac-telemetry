"""Filesystem layout for accuracy artefacts (under data_dir/accuracy/)."""

from __future__ import annotations

from pathlib import Path


def accuracy_root(data_dir: Path, *, subdir: str = "accuracy") -> Path:
    return Path(data_dir) / subdir


def session_dir(
    data_dir: Path, session_id: str, *, subdir: str = "accuracy"
) -> Path:
    return accuracy_root(data_dir, subdir=subdir) / session_id


def ocr_samples_path(session_dir_path: Path) -> Path:
    return session_dir_path / "ocr_samples.jsonl"


def roi_manifest_path(session_dir_path: Path) -> Path:
    return session_dir_path / "roi_manifest.jsonl"


def gt_path(session_dir_path: Path) -> Path:
    return session_dir_path / "gt.json"


def gt_draft_path(session_dir_path: Path) -> Path:
    """Operator-confirmed draft written by the GT eyeballing helper."""
    return session_dir_path / "gt_draft.json"


def score_json_path(session_dir_path: Path) -> Path:
    return session_dir_path / "score.json"


def score_md_path(session_dir_path: Path) -> Path:
    return session_dir_path / "score.md"


def review_md_path(session_dir_path: Path) -> Path:
    return session_dir_path / "review.md"
