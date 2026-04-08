"""Claude CLI subprocess wrapper with streaming output and per-invocation logs.

This module defines the ClaudeClient protocol plus three implementations:
- FakeClaudeClient: scripted responses for unit tests.
- DryRunClaudeClient: records calls and returns a placeholder response.
- RealClaudeClient: Popen-backed streaming client (added in Task 7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ClaudeCall:
    prompt: str
    session_id: str
    new_session: bool
    model: str | None
    stdout_log_path: Path
    stderr_log_path: Path
    stream_header: str


@dataclass(frozen=True)
class ClaudeResponse:
    stdout: str
    stderr: str
    returncode: int


class ClaudeBinaryNotFound(Exception):
    """Raised by the real client at startup when `claude` is not on PATH."""


class ClaudeInvocationError(Exception):
    """Raised when a claude invocation exits non-zero.

    Carries a partial ClaudeResponse so the runner can persist whatever output
    was captured before the failure.
    """

    def __init__(self, call: ClaudeCall, response: ClaudeResponse) -> None:
        super().__init__(
            f"claude -p exited with status {response.returncode} "
            f"for {call.stream_header}"
        )
        self.call = call
        self.response = response


class ClaudeClient(Protocol):
    def call(self, call: ClaudeCall) -> ClaudeResponse: ...


@dataclass
class FakeClaudeClient:
    """Scripted test double.

    Pass a list of ClaudeResponse (or ClaudeInvocationError) in the order they
    should be returned. The client records every ClaudeCall it receives.
    """

    scripted: list[ClaudeResponse | ClaudeInvocationError]
    received: list[ClaudeCall] = field(default_factory=list)
    _index: int = 0

    def call(self, call: ClaudeCall) -> ClaudeResponse:
        self.received.append(call)
        if self._index >= len(self.scripted):
            raise AssertionError(
                f"FakeClaudeClient ran out of scripted responses "
                f"(received {len(self.received)}, scripted {len(self.scripted)})"
            )
        item = self.scripted[self._index]
        self._index += 1
        if isinstance(item, ClaudeInvocationError):
            raise item
        return item


@dataclass
class DryRunClaudeClient:
    """Returns a placeholder response without invoking claude.

    Used when --dry-run is passed on the CLI. Writes no log files.
    """

    received: list[ClaudeCall] = field(default_factory=list)

    def call(self, call: ClaudeCall) -> ClaudeResponse:
        self.received.append(call)
        placeholder = (
            f"[dry-run] would have called claude with "
            f"session={call.session_id}, resume={not call.new_session}, "
            f"model={call.model}, prompt_len={len(call.prompt)}"
        )
        return ClaudeResponse(stdout=placeholder, stderr="", returncode=0)


import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass as _dataclass


def _ensure_claude_on_path() -> None:
    """Raise ClaudeBinaryNotFound if the claude CLI is not on PATH."""
    if shutil.which("claude") is None:
        raise ClaudeBinaryNotFound(
            "cannot find the 'claude' command on PATH. "
            "Install the Claude CLI and make sure 'claude' is on your PATH."
        )


@_dataclass
class RealClaudeClient:
    """Popen-backed streaming client.

    On each call():
      1. Builds an argv for `claude -p --output-format text ...`.
      2. Spawns the subprocess with pipes for stdin/stdout/stderr.
      3. Writes the prompt to stdin and closes it.
      4. Starts a background thread that reads stderr to an in-memory buffer
         AND the stderr_log_path (prevents pipe-buffer deadlock).
      5. Iterates stdout line-by-line on the main thread, writing each line to
         sys.stdout (indented), to an in-memory buffer, and to stdout_log_path.
      6. Waits for the subprocess, joins the stderr thread, and returns the
         ClaudeResponse.
      7. If returncode != 0, raises ClaudeInvocationError carrying the partial
         response.
    """

    def __post_init__(self) -> None:
        _ensure_claude_on_path()

    def call(self, call: ClaudeCall) -> ClaudeResponse:
        argv = self._build_argv(call)
        sys.stdout.write(call.stream_header + "\n")
        sys.stdout.flush()

        # Truncate log files at the start of the call; we append during streaming.
        call.stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
        call.stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
        call.stdout_log_path.write_text("", encoding="utf-8")
        call.stderr_log_path.write_text("", encoding="utf-8")

        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding="utf-8",
        )
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None

        proc.stdin.write(call.prompt)
        proc.stdin.close()

        stderr_buffer: list[str] = []

        def drain_stderr() -> None:
            assert proc.stderr is not None
            with open(call.stderr_log_path, "a", encoding="utf-8") as log:
                for chunk in proc.stderr:
                    stderr_buffer.append(chunk)
                    log.write(chunk)
                    log.flush()

        stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
        stderr_thread.start()

        stdout_buffer: list[str] = []
        with open(call.stdout_log_path, "a", encoding="utf-8") as log:
            for line in proc.stdout:
                indented = "    " + line if not line.startswith("    ") else line
                sys.stdout.write(indented)
                sys.stdout.flush()
                stdout_buffer.append(line)
                log.write(line)
                log.flush()

        returncode = proc.wait()
        stderr_thread.join()

        response = ClaudeResponse(
            stdout="".join(stdout_buffer),
            stderr="".join(stderr_buffer),
            returncode=returncode,
        )
        if returncode != 0:
            raise ClaudeInvocationError(call, response)
        return response

    @staticmethod
    def _build_argv(call: ClaudeCall) -> list[str]:
        argv = ["claude", "-p", "--output-format", "text"]
        if call.model is not None:
            argv += ["--model", call.model]
        if call.new_session:
            argv += ["--session-id", call.session_id]
        else:
            argv += ["--resume", call.session_id]
        return argv
