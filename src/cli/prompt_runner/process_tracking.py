"""Helpers for persisting spawned child-process metadata."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_spawn_metadata(
    metadata_path: Path,
    *,
    kind: str,
    pid: int,
    argv: list[str],
    cwd: Path,
) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": kind,
        "pid": int(pid),
        "parent_pid": os.getpid(),
        "argv": argv,
        "cwd": str(cwd),
        "started_at": _now_iso(),
        "status": "running",
        "returncode": None,
        "finished_at": None,
    }
    metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def mark_process_completed(metadata_path: Path, *, returncode: int) -> None:
    if metadata_path.exists():
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        payload = {}
    payload["status"] = "completed"
    payload["returncode"] = returncode
    payload["finished_at"] = _now_iso()
    metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
