"""Codex CLI subprocess wrapper for prompt-runner."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
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


def _normalize_codex_effort(effort: str) -> str:
    """Translate prompt-runner effort labels to Codex config values."""
    normalized = effort.strip().lower()
    if normalized == "max":
        return "xhigh"
    return normalized


def _append_aggregate_log(
    path: Path | None,
    prefix: str,
    stream: str,
    chunk: str,
) -> None:
    if path is None or not chunk:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(path, "a", encoding="utf-8") as log:
        for line in chunk.splitlines(keepends=True):
            log.write(f"{timestamp} [{prefix} {stream}] {line}")
        if chunk and not chunk.endswith("\n"):
            log.write("\n")


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

    verbose: bool = False

    def __post_init__(self) -> None:
        _ensure_codex_on_path()

    @staticmethod
    def _resolve_agent_path(agent_name: str, worktree_dir: Path) -> Path | None:
        candidates = [
            worktree_dir / ".codex" / "agents" / f"{agent_name}.toml",
            Path.home() / ".codex" / "agents" / f"{agent_name}.toml",
        ]
        for path in candidates:
            if path.exists():
                return path
        return None

    @classmethod
    def _load_agent_contract(
        cls, agent_name: str | None, worktree_dir: Path,
    ) -> tuple[str, str | None]:
        if not agent_name:
            return "", None
        agent_path = cls._resolve_agent_path(agent_name, worktree_dir)
        if agent_path is None:
            raise FileNotFoundError(
                f"cannot find Codex custom agent '{agent_name}' in "
                f"{worktree_dir / '.codex' / 'agents'} or {Path.home() / '.codex' / 'agents'}"
            )
        payload = tomllib.loads(agent_path.read_text(encoding="utf-8"))
        instructions = str(payload.get("developer_instructions", "")).strip()
        if not instructions:
            raise ValueError(
                f"Codex custom agent '{agent_name}' has no developer_instructions: {agent_path}"
            )
        return instructions, str(agent_path)

    @staticmethod
    def _prepare_log_paths(call: ClaudeCall) -> None:
        call.stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
        call.stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
        if call.stdout_log_path == call.stderr_log_path:
            call.stdout_log_path.touch(exist_ok=True)
            return
        call.stdout_log_path.write_text("", encoding="utf-8")
        call.stderr_log_path.write_text("", encoding="utf-8")

    @staticmethod
    def _process_meta_path(call: ClaudeCall) -> Path:
        state_root = call.worktree_dir / ".run-files" / "backend-state" / "codex"
        meta_dir = state_root / "process"
        meta_dir.mkdir(parents=True, exist_ok=True)
        return meta_dir / f"{call.session_id or 'session'}.proc.json"

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

        try:
            agent_instructions, agent_path = self._load_agent_contract(
                call.agent_name, call.worktree_dir,
            )
        except (FileNotFoundError, ValueError, tomllib.TOMLDecodeError) as exc:
            raise ClaudeInvocationError(
                call,
                ClaudeResponse(stdout="", stderr=str(exc), returncode=1),
            ) from exc

        argv, message_path = self._build_argv(
            call, agent_instructions=agent_instructions,
        )
        self._prepare_log_paths(call)
        process_meta_path = self._process_meta_path(call)

        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            cwd=str(call.worktree_dir),
        )
        write_spawn_metadata(
            process_meta_path,
            kind="backend-call",
            pid=proc.pid,
            argv=argv,
            cwd=call.worktree_dir,
            extra={
                "agent_name": call.agent_name,
                "agent_path": agent_path,
                "agent_loaded": bool(call.agent_name),
            },
        )
        assert proc.stdout is not None and proc.stderr is not None

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        def drain_stdout() -> None:
            assert proc.stdout is not None
            with open(call.stdout_log_path, "a", encoding="utf-8") as log:
                for chunk in proc.stdout:
                    stdout_chunks.append(chunk)
                    log.write(chunk)
                    log.flush()
                    _append_aggregate_log(
                        call.aggregate_log_path,
                        call.aggregate_log_prefix or call.stream_header,
                        "stdout",
                        chunk,
                    )
                    if self.verbose:
                        sys.stdout.write(chunk)
                        sys.stdout.flush()

        def drain_stderr() -> None:
            assert proc.stderr is not None
            with open(call.stderr_log_path, "a", encoding="utf-8") as log:
                for chunk in proc.stderr:
                    stderr_chunks.append(chunk)
                    log.write(chunk)
                    log.flush()
                    _append_aggregate_log(
                        call.aggregate_log_path,
                        call.aggregate_log_prefix or call.stream_header,
                        "stderr",
                        chunk,
                    )
                    if self.verbose:
                        sys.stderr.write(chunk)
                        sys.stderr.flush()

        stdout_thread = threading.Thread(target=drain_stdout, daemon=True)
        stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        returncode = proc.wait()
        stdout_thread.join()
        stderr_thread.join()
        mark_process_completed(
            process_meta_path, returncode=returncode,
        )
        stdout = "".join(stdout_chunks)
        stderr = "".join(stderr_chunks)

        last_message = ""
        if message_path.exists():
            last_message = message_path.read_text(encoding="utf-8").strip()
        if not last_message:
            last_message = _extract_last_agent_message(stdout) or stdout.strip()

        session_id = call.session_id
        match = _SESSION_RE.search(stdout)
        if match:
            session_id = match.group(1)

        response = ClaudeResponse(
            stdout=last_message,
            stderr=stderr,
            returncode=returncode,
            session_id=session_id,
        )
        if returncode != 0:
            raise ClaudeInvocationError(call, response)
        return response

    @staticmethod
    def _build_argv(
        call: ClaudeCall,
        *,
        agent_instructions: str = "",
    ) -> tuple[list[str], Path]:
        state_root = call.worktree_dir / ".run-files" / "backend-state" / "codex"
        log_dir = state_root / "log"
        sqlite_home = state_root / "sqlite"
        message_dir = state_root / "messages"
        message_dir.mkdir(parents=True, exist_ok=True)
        message_path = message_dir / f"{call.session_id or 'session'}.last-message.txt"
        log_dir.mkdir(parents=True, exist_ok=True)
        sqlite_home.mkdir(parents=True, exist_ok=True)
        common_overrides = [
            "-c", f'projects."{call.worktree_dir}".trust_level="trusted"',
            "-c", 'history.persistence="none"',
            "-c", f'log_dir="{log_dir}"',
            "-c", f'sqlite_home="{sqlite_home}"',
        ]
        base = [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            *common_overrides,
            "--json",
            "--skip-git-repo-check",
            "--output-last-message", str(message_path),
        ]
        if call.model is not None:
            base += ["--model", call.model]
        if call.effort is not None:
            base += [
                "-c",
                f'model_reasoning_effort="{_normalize_codex_effort(call.effort)}"',
            ]
        sections = [NON_INTERACTIVE_PROMPT_PREFIX]
        if call.agent_name:
            sections.append(f"Assume the `{call.agent_name}` agent role.")
        if agent_instructions:
            sections.extend([agent_instructions, call.prompt])
        else:
            sections.append(call.prompt)
        prompt = "\n\n---\n\n".join(sections)
        return [*base, prompt], message_path
