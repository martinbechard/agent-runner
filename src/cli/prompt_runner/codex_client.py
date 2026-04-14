"""Codex CLI subprocess wrapper for prompt-runner."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from prompt_runner.claude_client import (
    ClaudeCall,
    ClaudeInvocationError,
    ClaudeResponse,
)
from prompt_runner.process_tracking import (
    mark_process_completed,
    write_spawn_metadata,
)


class CodexBinaryNotFound(Exception):
    """Raised when the `codex` CLI is not on PATH."""


_SESSION_RE = re.compile(r"session id:\s*([0-9a-fA-F-]{36})", re.IGNORECASE)

NON_INTERACTIVE_PROMPT_PREFIX = (
    "You are being called from a headless pipeline. Your response IS the "
    "requested artifact or verdict, not a conversation about it.\n\n"
    "Rules:\n"
    "- Do not ask clarifying questions. If the prompt is ambiguous, make a "
    "reasonable choice and produce the artifact.\n"
    "- Do not include conversational framing like \"Here is...\", "
    "\"I created...\", or \"Let me know if...\".\n"
    "- Do not include meta-commentary, summaries of what you did, or tool "
    "narration unless the prompt explicitly asks for them.\n"
    "- If the prompt instructs you to write a file, write it and return only "
    "the requested final artifact text or verdict.\n"
)


def _extract_last_agent_message(stdout: str) -> str:
    """Best-effort fallback for Codex JSON mode when no sidecar is written."""
    last_text = ""
    for raw in stdout.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        item = obj.get("item", {})
        if obj.get("type") == "item.completed" and item.get("type") == "agent_message":
            text = item.get("text", "")
            if text:
                last_text = text.strip()
    return last_text


def _ensure_codex_on_path() -> None:
    if shutil.which("codex") is None:
        raise CodexBinaryNotFound(
            "cannot find the 'codex' command on PATH. "
            "Install Codex and make sure 'codex' is on your PATH."
        )


@dataclass
class RealCodexClient:
    """Uses stateless `codex exec` calls for prompt-runner generator/judge turns."""

    def __post_init__(self) -> None:
        _ensure_codex_on_path()

    def call(self, call: ClaudeCall) -> ClaudeResponse:
        if call.fork_session:
            raise ClaudeInvocationError(
                call,
                ClaudeResponse(
                    stdout="",
                    stderr=(
                        "prompt-runner Codex backend does not support "
                        "non-interactive fork-session calls"
                    ),
                    returncode=1,
                ),
            )

        argv, message_path = self._build_argv(call)
        call.stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
        call.stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
        process_meta_path = call.stdout_log_path.with_suffix(".proc.json")

        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=str(call.workspace_dir),
        )
        write_spawn_metadata(
            process_meta_path,
            kind="backend-call",
            pid=proc.pid,
            argv=argv,
            cwd=call.workspace_dir,
        )
        stdout, stderr = proc.communicate()
        result = subprocess.CompletedProcess(
            args=argv,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
        )
        mark_process_completed(
            process_meta_path, returncode=result.returncode,
        )

        call.stdout_log_path.write_text(result.stdout, encoding="utf-8")
        call.stderr_log_path.write_text(result.stderr, encoding="utf-8")

        last_message = ""
        if message_path.exists():
            last_message = message_path.read_text(encoding="utf-8").strip()
        if not last_message:
            last_message = _extract_last_agent_message(result.stdout) or result.stdout.strip()

        session_id = call.session_id
        match = _SESSION_RE.search(result.stdout)
        if match:
            session_id = match.group(1)

        response = ClaudeResponse(
            stdout=last_message,
            stderr=result.stderr,
            returncode=result.returncode,
            session_id=session_id,
        )
        if result.returncode != 0:
            raise ClaudeInvocationError(call, response)
        return response

    @staticmethod
    def _build_argv(call: ClaudeCall) -> tuple[list[str], Path]:
        message_path = call.stdout_log_path.resolve().with_suffix(".last-message.txt")
        state_root = call.workspace_dir / ".prompt-runner" / "backend-state" / "codex"
        log_dir = state_root / "log"
        sqlite_home = state_root / "sqlite"
        log_dir.mkdir(parents=True, exist_ok=True)
        sqlite_home.mkdir(parents=True, exist_ok=True)
        common_overrides = [
            "-c", f'projects."{call.workspace_dir}".trust_level="trusted"',
            "-c", 'approval_policy="never"',
            "-c", 'history.persistence="none"',
            "-c", 'sandbox_mode="danger-full-access"',
            "-c", f'log_dir="{log_dir}"',
            "-c", f'sqlite_home="{sqlite_home}"',
        ]
        base = [
            "codex",
            "exec",
            *common_overrides,
            "--json",
            "--skip-git-repo-check",
            "--output-last-message", str(message_path),
        ]
        if call.model is not None:
            base += ["--model", call.model]
        prompt = f"{NON_INTERACTIVE_PROMPT_PREFIX}\n\n---\n\n{call.prompt}"
        return [*base, prompt], message_path
