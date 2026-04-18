"""Helpers for structured per-call log metadata sidecars."""
from __future__ import annotations

import json
from pathlib import Path


def metadata_path_for_log(stdout_log_path: Path) -> Path:
    return stdout_log_path.with_suffix(".meta.json")


def write_call_metadata(
    stdout_log_path: Path,
    *,
    model: str | None,
    backend: str | None = None,
    role: str | None = None,
) -> Path:
    payload = {
        "model": model,
        "backend": backend,
        "role": role,
    }
    path = metadata_path_for_log(stdout_log_path)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
