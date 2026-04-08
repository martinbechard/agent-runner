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
