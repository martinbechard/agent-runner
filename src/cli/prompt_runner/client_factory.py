"""Backend-specific client helpers for prompt-runner."""
from __future__ import annotations

import shutil

from prompt_runner.claude_client import (
    ClaudeBinaryNotFound,
    DryRunClaudeClient,
    RealClaudeClient,
)
from prompt_runner.codex_client import CodexBinaryNotFound, RealCodexClient


def make_client(backend: str, *, dry_run: bool = False):
    if dry_run:
        return DryRunClaudeClient()
    if backend == "claude":
        return RealClaudeClient()
    if backend == "codex":
        return RealCodexClient()
    raise ValueError(f"unknown backend: {backend}")


def check_backend_cli(backend: str) -> str | None:
    if backend == "claude":
        if shutil.which("claude") is None:
            return (
                "The 'claude' CLI is not on PATH.\n"
                "Install it from https://claude.ai/download and ensure "
                "'claude' is available in your shell."
            )
        return None
    if backend == "codex":
        if shutil.which("codex") is None:
            return (
                "The 'codex' CLI is not on PATH.\n"
                "Install Codex and ensure 'codex' is available in your shell."
            )
        return None
    return f"Unknown backend: {backend}"

