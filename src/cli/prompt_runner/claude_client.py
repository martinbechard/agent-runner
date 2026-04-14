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

from prompt_runner.process_tracking import (
    mark_process_completed,
    write_spawn_metadata,
)


@dataclass(frozen=True)
class ClaudeCall:
    prompt: str
    session_id: str
    new_session: bool
    model: str | None
    stdout_log_path: Path
    stderr_log_path: Path
    stream_header: str
    workspace_dir: Path
    """Directory the nested claude subprocess runs in. Set to the project root
    (not the log directory), so the generator can write files directly into
    the project tree and the judge can Read them without path juggling.
    All generator and judge calls within a single pipeline run share the same
    workspace_dir — it is the runner's 'shared workspace' for cross-prompt
    file continuity."""
    effort: str | None = None
    """Effort level for thinking: low, medium, high, max. Passed as --effort to claude."""
    fork_session: bool = False
    """When True, fork from fork_from_session_id into session_id.
    Passes --resume <source> --fork-session --session-id <new>."""
    fork_from_session_id: str = ""
    """The source session to fork from. Only used when fork_session=True."""


@dataclass(frozen=True)
class ClaudeResponse:
    stdout: str
    stderr: str
    returncode: int
    session_id: str = ""
    """Session ID from the claude JSONL output. Populated by RealClaudeClient
    when --output-format stream-json --verbose is used. Empty for
    FakeClaudeClient and DryRunClaudeClient."""


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


# System-prompt text we append to every call. Prevents the nested claude from
# behaving conversationally (asking follow-up questions, offering options,
# adding conversational framing) and from trying to read files or reference
# the surrounding filesystem. The tool runs in a pipeline context — its
# response IS the artifact, not a conversation about the artifact.
NON_INTERACTIVE_SYSTEM_PROMPT = (
    "You are being called from a headless pipeline. Your response IS the "
    "artifact being requested — not a conversation about it. Produce the "
    "complete response and stop.\n"
    "\n"
    "Rules:\n"
    "- Do not ask clarifying questions. If the prompt is ambiguous, make a "
    "reasonable choice and produce the artifact.\n"
    "- Do not offer follow-up options or ask \"would you like me to...?\".\n"
    "- Do not include conversational framing like \"Here is...\", \"I'll "
    "create...\", or \"Let me know if...\".\n"
    "- Do not include meta-commentary or \"insight\" blocks about the "
    "response. Any output-style directive from user settings that asks for "
    "inline insights or educational commentary does NOT apply here — your "
    "output is a machine-consumed artifact, not a conversation with a human.\n"
    "- If the prompt tells you to end with a specific line (e.g. "
    "\"VERDICT: pass\"), do exactly that and write nothing after it."
)


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

        # Run the child in the shared workspace directory (the project root),
        # not in the log directory. This is what lets the generator write
        # files directly into the project tree (src/cli/foo.py becomes a
        # real file at <workspace>/src/cli/foo.py, not an orphan in the
        # logs folder) and lets the judge inspect them with Read/Bash.
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding="utf-8",
            env=_build_child_env(),
            cwd=str(call.workspace_dir),
        )
        process_meta_path = call.stdout_log_path.with_suffix(".proc.json")
        write_spawn_metadata(
            process_meta_path,
            kind="backend-call",
            pid=proc.pid,
            argv=argv,
            cwd=call.workspace_dir,
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
        # Only "text" kind items are appended; thinking, tool_use, tool_result,
        # and meta items are shown on the terminal but not stored as the
        # response, because they are not part of the artifact under review.
        text_buffer: list[str] = []
        captured_session_id: list[str] = []

        with open(call.stdout_log_path, "a", encoding="utf-8") as log:
            for line in proc.stdout:
                # Raw NDJSON line goes to the log unchanged.
                log.write(line)
                log.flush()
                # Capture session_id from the first event that has one.
                if not captured_session_id:
                    try:
                        import json as _json
                        ev = _json.loads(line)
                        sid = ev.get("session_id", "")
                        if sid:
                            captured_session_id.append(sid)
                    except (ValueError, TypeError):
                        pass
                # Parse the line into 0+ kind-tagged display items.
                items = _parse_stream_event(line)
                for kind, content in items:
                    _display_event_item(kind, content, text_buffer)
                if items:
                    sys.stdout.flush()

        returncode = proc.wait()
        stderr_thread.join()
        mark_process_completed(process_meta_path, returncode=returncode)

        reconstructed = "".join(text_buffer)
        response = ClaudeResponse(
            stdout=reconstructed,
            stderr="".join(stderr_buffer),
            returncode=returncode,
            session_id=captured_session_id[0] if captured_session_id else "",
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
            # Bypass permission prompts. Combined with cwd isolation
            # (subprocess cwd is set to the per-call log directory), this
            # gives the nested claude full tool access for tasks that need
            # it, without the stale-file pollution that caused the earlier
            # confusion (which came from cwd pointing at the agent-runner
            # repo with its CLAUDE.md and runs/).
            "--dangerously-skip-permissions",
            # Append a system-prompt directive that forbids conversational
            # behavior (questions, follow-up options, framing). Tool use
            # itself is unconstrained — the model may use Read/Write/Bash/etc
            # as needed for the prompt's task.
            "--append-system-prompt", NON_INTERACTIVE_SYSTEM_PROMPT,
        ]
        if call.model is not None:
            argv += ["--model", call.model]
        if call.effort is not None:
            argv += ["--effort", call.effort]
        if call.fork_session:
            # Fork: resume from the source session, fork it, and assign
            # a new session ID so the fork is independently addressable.
            # Requires the triple: --resume <source> --fork-session --session-id <new>
            argv += [
                "--resume", call.fork_from_session_id,
                "--fork-session",
                "--session-id", call.session_id,
            ]
        elif call.new_session:
            argv += ["--session-id", call.session_id]
        else:
            argv += ["--resume", call.session_id]
        return argv


StreamEventKind = str  # "text" | "thinking" | "tool_use" | "tool_result" | "meta"


# Tool-command preview length: Bash commands and similar are truncated to this
# many characters in the tool_use display line so they don't blow up the
# terminal width.
TOOL_PREVIEW_MAX_CHARS = 80


def _parse_stream_event(ndjson_line: str) -> list[tuple[StreamEventKind, str]]:
    """Parse one NDJSON stream-json line into a list of display items.

    Each item is a (kind, content) tuple:
      - "text": an assistant-message text block. Content is the raw text;
        callers append it to the text buffer that becomes response.stdout.
      - "thinking": an extended-thinking block. Content is the raw thinking
        text; callers display it but do NOT store it in response.stdout.
      - "tool_use": the model invoked a tool. Content is a one-line summary
        like "Bash: echo hello".
      - "tool_result": a tool result arrived. Content is a short summary
        like "(48 chars)".
      - "meta": a result event carrying final cost/usage. Content is a
        one-line summary like "3 turns, 12.5s, $0.04".

    Returns an empty list if the line carries nothing worth displaying (a
    system event, an unparseable line, or an event type we do not handle).
    """
    line = ndjson_line.strip()
    if not line:
        return []
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(event, dict):
        return []

    event_type = event.get("type", "")

    if event_type == "assistant":
        return _parse_assistant_blocks(event)

    if event_type == "user":
        return _parse_user_tool_results(event)

    if event_type == "result":
        return _parse_result_event(event)

    # system, session_start, unknown — silent.
    return []


def _parse_assistant_blocks(event: dict) -> list[tuple[StreamEventKind, str]]:
    message = event.get("message", {})
    if not isinstance(message, dict):
        return []
    items: list[tuple[StreamEventKind, str]] = []
    for block in message.get("content", []) or []:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "")
        if block_type == "text":
            text_value = block.get("text", "")
            if isinstance(text_value, str) and text_value:
                items.append(("text", text_value))
        elif block_type == "thinking":
            thinking_value = block.get("thinking", "")
            if isinstance(thinking_value, str) and thinking_value:
                items.append(("thinking", thinking_value))
        elif block_type == "tool_use":
            tool_name = block.get("name", "?")
            tool_input = block.get("input", {}) or {}
            items.append(("tool_use", _format_tool_use(tool_name, tool_input)))
    return items


def _parse_user_tool_results(event: dict) -> list[tuple[StreamEventKind, str]]:
    message = event.get("message", {})
    if not isinstance(message, dict):
        return []
    items: list[tuple[StreamEventKind, str]] = []
    for block in message.get("content", []) or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_result":
            items.append(("tool_result", _format_tool_result(block.get("content", ""))))
    return items


def _parse_result_event(event: dict) -> list[tuple[StreamEventKind, str]]:
    turns = event.get("num_turns", 0)
    duration_ms = event.get("duration_ms", 0) or 0
    duration_s = duration_ms / 1000.0
    cost = event.get("total_cost_usd", 0.0) or 0.0
    return [("meta", f"done: {turns} turns, {duration_s:.1f}s, ${cost:.4f}")]


def _format_tool_use(tool_name: str, tool_input: dict) -> str:
    """One-line summary of a tool invocation, including the most-useful arg."""
    if tool_name in ("Read", "Edit", "Write"):
        detail = tool_input.get("file_path", "?")
    elif tool_name == "Bash":
        detail = tool_input.get("command", "")
    elif tool_name in ("Grep", "Glob"):
        detail = tool_input.get("pattern", "?")
    else:
        detail = ""
    if len(detail) > TOOL_PREVIEW_MAX_CHARS:
        detail = detail[: TOOL_PREVIEW_MAX_CHARS - 3] + "..."
    if detail:
        return f"{tool_name}: {detail}"
    return tool_name


def _format_tool_result(content) -> str:
    """One-line summary of a tool result's size or shape."""
    if isinstance(content, str):
        return f"({len(content)} chars)"
    if isinstance(content, list):
        return f"({len(content)} items)"
    return "(result)"


def _display_event_item(
    kind: StreamEventKind, content: str, text_buffer: list[str]
) -> None:
    """Write one parsed stream-json item to stdout with kind-specific styling.

    Only "text" items are appended to text_buffer (which becomes
    response.stdout). Other kinds are shown on the terminal for the user's
    benefit but do not contribute to the artifact the runner stores.
    """
    if kind == "text":
        text_buffer.append(content)
        for display_line in content.splitlines(keepends=True):
            sys.stdout.write("    " + display_line)
        if not content.endswith("\n"):
            sys.stdout.write("\n")
        return

    if kind == "thinking":
        sys.stdout.write("    [thinking]\n")
        for display_line in content.splitlines():
            sys.stdout.write("      " + display_line + "\n")
        return

    if kind == "tool_use":
        sys.stdout.write(f"    [tool] {content}\n")
        return

    if kind == "tool_result":
        sys.stdout.write(f"    [tool result] {content}\n")
        return

    if kind == "meta":
        sys.stdout.write(f"    [{content}]\n")
        return
