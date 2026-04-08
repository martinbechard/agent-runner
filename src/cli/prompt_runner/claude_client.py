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


import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass as _dataclass


# Environment variable the parent Claude Code process sets. Removing it from
# the child's environment allows a nested claude -p invocation to work
# correctly when prompt-runner is itself being run from inside Claude Code.
# (Without this, the child claude may refuse to start or behave oddly.)
_STRIPPED_ENV_VAR = "CLAUDECODE"


def _ensure_claude_on_path() -> None:
    """Raise ClaudeBinaryNotFound if the claude CLI is not on PATH."""
    if shutil.which("claude") is None:
        raise ClaudeBinaryNotFound(
            "cannot find the 'claude' command on PATH. "
            "Install the Claude CLI and make sure 'claude' is on your PATH."
        )


def _build_child_env() -> dict:
    """Copy the current env and strip CLAUDECODE so a child claude can spawn."""
    env = os.environ.copy()
    env.pop(_STRIPPED_ENV_VAR, None)
    return env


@_dataclass
class RealClaudeClient:
    """Popen-backed streaming client using stream-json output format.

    Why stream-json rather than text: when claude's stdout is a pipe (not a
    TTY), it block-buffers text output — so nothing reaches us until a large
    buffer fills, defeating live streaming. stream-json emits one JSON event
    per line, explicitly flushed, which gives us true line-by-line streaming.
    We parse each event's assistant-text blocks and both display them to the
    terminal live AND accumulate them into a plain-text response string for
    the runner (which stores it in iter-NN-<role>.md).

    On each call():
      1. Builds an argv for `claude --print <prompt> --output-format stream-json --verbose ...`.
      2. Spawns the subprocess with a stripped CLAUDECODE env so a nested
         claude can work when prompt-runner is itself run from Claude Code.
      3. Starts a background thread reading stderr into an in-memory buffer
         and the stderr log file (prevents pipe-buffer deadlock).
      4. Iterates stdout line by line on the main thread. Each line is:
           - written verbatim to stdout_log_path (raw NDJSON audit trail),
           - parsed as a JSON event,
           - if the event is an assistant-message-with-text-blocks, the text
             is printed to sys.stdout indented AND appended to an in-memory
             text buffer that becomes ClaudeResponse.stdout.
      5. Waits for the subprocess, joins the stderr thread, and returns the
         ClaudeResponse. Raises ClaudeInvocationError with the partial
         response if returncode != 0.
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
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding="utf-8",
            env=_build_child_env(),
        )
        assert proc.stdout is not None and proc.stderr is not None

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

        # Reconstructed plain text from assistant events — this becomes
        # response.stdout, which the runner writes to iter-NN-<role>.md.
        text_buffer: list[str] = []

        with open(call.stdout_log_path, "a", encoding="utf-8") as log:
            for line in proc.stdout:
                # Raw NDJSON line goes to the log unchanged.
                log.write(line)
                log.flush()
                # Extract text blocks from assistant events.
                text = _extract_assistant_text(line)
                if text:
                    text_buffer.append(text)
                    # Display indented so it visually nests under stream_header.
                    for display_line in text.splitlines(keepends=True):
                        sys.stdout.write("    " + display_line)
                    if not text.endswith("\n"):
                        sys.stdout.write("\n")
                    sys.stdout.flush()

        returncode = proc.wait()
        stderr_thread.join()

        reconstructed = "".join(text_buffer)
        response = ClaudeResponse(
            stdout=reconstructed,
            stderr="".join(stderr_buffer),
            returncode=returncode,
        )
        if returncode != 0:
            raise ClaudeInvocationError(call, response)
        return response

    @staticmethod
    def _build_argv(call: ClaudeCall) -> list[str]:
        argv = [
            "claude",
            "--print", call.prompt,
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            "--permission-mode", "acceptEdits",
        ]
        if call.model is not None:
            argv += ["--model", call.model]
        if call.new_session:
            argv += ["--session-id", call.session_id]
        else:
            argv += ["--resume", call.session_id]
        return argv


def _extract_assistant_text(ndjson_line: str) -> str:
    """Return the concatenated text of all text blocks in an assistant event.

    Returns empty string if the line is not a parseable JSON object, is not
    an assistant event, or contains no text blocks. Tool-use blocks and
    non-assistant event types (system, user, result) are ignored — they are
    preserved in the raw stdout_log but not surfaced to the runner.
    """
    line = ndjson_line.strip()
    if not line:
        return ""
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return ""
    if not isinstance(event, dict) or event.get("type") != "assistant":
        return ""
    message = event.get("message", {})
    if not isinstance(message, dict):
        return ""
    pieces: list[str] = []
    for block in message.get("content", []) or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text_value = block.get("text", "")
            if isinstance(text_value, str) and text_value:
                pieces.append(text_value)
    return "".join(pieces)
