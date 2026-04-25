"""Atomic claim handling."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from backlog_runner.models import BacklogItem, ClaimRecord
from backlog_runner.paths import BacklogPaths


WRITE_FLAGS = os.O_CREAT | os.O_EXCL | os.O_WRONLY
WRITE_MODE = 0o644


def create_claim(paths: BacklogPaths, item: BacklogItem) -> ClaimRecord | None:
    """Create an atomic claim, returning None when it already exists."""
    paths.ensure_state_dirs()
    claim = ClaimRecord(
        item_key=item.key,
        claim_id=f"{item.key}:{_timestamp()}",
        created_at=_timestamp(),
        source_path=item.source_path,
    )
    claim_path = paths.claim_path(item.key)
    payload = json.dumps(claim.to_dict(), indent=2, sort_keys=False) + "\n"
    try:
        fd = os.open(claim_path, WRITE_FLAGS, WRITE_MODE)
    except FileExistsError:
        return None
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(payload)
    return claim


def read_claim(path: Path) -> ClaimRecord:
    """Read one claim record."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return ClaimRecord.from_dict(data)


def release_claim(paths: BacklogPaths, item_key: str) -> None:
    """Delete a claim file when present."""
    paths.claim_path(item_key).unlink(missing_ok=True)


def _timestamp() -> str:
    """Return an ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()
