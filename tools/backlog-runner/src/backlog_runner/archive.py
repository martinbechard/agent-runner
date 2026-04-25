"""Archive routing for backlog items."""

from __future__ import annotations

import shutil
from pathlib import Path

from backlog_runner.models import BacklogItemRecord
from backlog_runner.paths import BacklogPaths


MAX_ARCHIVE_DEDUPLICATION_ATTEMPTS = 1000


def archive_completed(paths: BacklogPaths, record: BacklogItemRecord) -> Path:
    """Move a backlog item to completed archive."""
    return _move_to(paths.completed_archive_path(record.item_type, record.source_path.name), record)


def archive_failed(paths: BacklogPaths, record: BacklogItemRecord) -> Path:
    """Move a backlog item to failed archive."""
    return _move_to(paths.failed_archive_path(record.item_type, record.source_path.name), record)


def _move_to(target: Path, record: BacklogItemRecord) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = _deduplicate(target)
    if record.source_path.exists():
        shutil.move(str(record.source_path), str(target))
    return target


def _deduplicate(target: Path) -> Path:
    stem = target.stem
    suffix = target.suffix
    for index in range(1, MAX_ARCHIVE_DEDUPLICATION_ATTEMPTS):
        candidate = target.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find archive destination for {target}")
