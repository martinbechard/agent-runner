from pathlib import Path

import pytest

from prompt_runner.claude_client import (
    ClaudeCall,
    ClaudeInvocationError,
    ClaudeResponse,
    DryRunClaudeClient,
    FakeClaudeClient,
)


def _make_call(prefix: str = "test") -> ClaudeCall:
    return ClaudeCall(
        prompt="a prompt body",
        session_id=f"{prefix}-session",
        new_session=True,
        model=None,
        stdout_log_path=Path(f"/tmp/{prefix}.stdout.log"),
        stderr_log_path=Path(f"/tmp/{prefix}.stderr.log"),
        stream_header=f"── {prefix} ──",
    )


def test_fake_client_returns_scripted_responses_in_order():
    client = FakeClaudeClient(
        scripted=[
            ClaudeResponse(stdout="first", stderr="", returncode=0),
            ClaudeResponse(stdout="second", stderr="", returncode=0),
        ]
    )
    call_a = _make_call("a")
    call_b = _make_call("b")
    assert client.call(call_a).stdout == "first"
    assert client.call(call_b).stdout == "second"
    assert client.received == [call_a, call_b]


def test_fake_client_raises_when_scripted_list_exhausted():
    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="only", stderr="", returncode=0)
    ])
    client.call(_make_call())
    with pytest.raises(AssertionError, match="ran out of scripted responses"):
        client.call(_make_call())


def test_fake_client_raises_scripted_invocation_error():
    partial = ClaudeResponse(stdout="partial", stderr="boom", returncode=1)
    err = ClaudeInvocationError(_make_call("err"), partial)
    client = FakeClaudeClient(scripted=[err])
    with pytest.raises(ClaudeInvocationError) as exc_info:
        client.call(_make_call("err"))
    assert exc_info.value.response.stdout == "partial"


def test_dry_run_client_returns_placeholder_and_records_call():
    client = DryRunClaudeClient()
    call = _make_call("dry")
    response = client.call(call)
    assert response.returncode == 0
    assert "dry-run" in response.stdout
    assert "dry-session" in response.stdout
    assert client.received == [call]


from unittest.mock import MagicMock

from prompt_runner.claude_client import (
    ClaudeBinaryNotFound,
    RealClaudeClient,
)


class _FakeProcess:
    def __init__(self, stdout_lines: list[str], stderr_lines: list[str], returncode: int = 0):
        self._stdout_lines = iter(stdout_lines)
        self._stderr_lines = iter(stderr_lines)
        self._returncode = returncode
        self.stdin = MagicMock()
        self.stdout = self
        self.stderr = _FakeStream(stderr_lines)

    def __iter__(self):
        return self._stdout_lines

    def wait(self):
        return self._returncode


class _FakeStream:
    def __init__(self, lines: list[str]):
        self._lines = iter(lines)

    def __iter__(self):
        return self._lines


@pytest.fixture
def log_paths(tmp_path):
    return tmp_path / "out.log", tmp_path / "err.log"


def _call(stdout_log: Path, stderr_log: Path) -> ClaudeCall:
    return ClaudeCall(
        prompt="test prompt",
        session_id="s",
        new_session=True,
        model=None,
        stdout_log_path=stdout_log,
        stderr_log_path=stderr_log,
        stream_header="── test ──",
    )


def _assistant_event(text: str) -> str:
    """Build a stream-json assistant event line carrying a single text block."""
    import json as _json
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    }
    return _json.dumps(event) + "\n"


def _system_event() -> str:
    """Build a non-text stream-json event that should be ignored by the parser."""
    return '{"type": "system", "subtype": "init"}\n'


def test_real_client_raises_when_claude_not_on_path(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(ClaudeBinaryNotFound):
        RealClaudeClient()


def test_real_client_reconstructs_text_from_stream_json(monkeypatch, log_paths):
    """stream-json assistant events are parsed and their text blocks
    concatenated into ClaudeResponse.stdout."""
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    lines = [
        _system_event(),
        _assistant_event("hello "),
        _assistant_event("world"),
    ]
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *a, **k: _FakeProcess(stdout_lines=lines, stderr_lines=[]),
    )
    client = RealClaudeClient()
    response = client.call(_call(stdout_log, stderr_log))
    assert response.returncode == 0
    assert response.stdout == "hello world"
    # The raw stdout log contains every event line verbatim (for debugging),
    # not the reconstructed plain text.
    raw = stdout_log.read_text()
    assert '"type": "assistant"' in raw
    assert '"type": "system"' in raw
    assert stderr_log.read_text() == ""


def test_real_client_ignores_malformed_json_lines(monkeypatch, log_paths):
    """A stream-json line that is not parseable JSON is written to the log
    but does not crash the reader and does not contribute to response.stdout."""
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    lines = [
        "not json at all\n",
        _assistant_event("real text"),
    ]
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *a, **k: _FakeProcess(stdout_lines=lines, stderr_lines=[]),
    )
    client = RealClaudeClient()
    response = client.call(_call(stdout_log, stderr_log))
    assert response.stdout == "real text"
    assert "not json at all" in stdout_log.read_text()


def test_real_client_writes_stderr_log(monkeypatch, log_paths):
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *a, **k: _FakeProcess(stdout_lines=[], stderr_lines=["warning\n"]),
    )
    client = RealClaudeClient()
    response = client.call(_call(stdout_log, stderr_log))
    assert response.stderr == "warning\n"
    assert stderr_log.read_text() == "warning\n"


def test_real_client_nonzero_exit_raises_with_partial(monkeypatch, log_paths):
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *a, **k: _FakeProcess(
            stdout_lines=[_assistant_event("partial output")],
            stderr_lines=["boom\n"],
            returncode=1,
        ),
    )
    client = RealClaudeClient()
    with pytest.raises(ClaudeInvocationError) as exc_info:
        client.call(_call(stdout_log, stderr_log))
    assert exc_info.value.response.stdout == "partial output"
    assert exc_info.value.response.stderr == "boom\n"
    assert exc_info.value.response.returncode == 1


def test_real_client_argv_uses_session_id_on_first_call(monkeypatch, log_paths):
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    captured: dict = {}

    def fake_popen(argv, *a, **k):
        captured["argv"] = argv
        captured["cwd"] = k.get("cwd")
        return _FakeProcess(stdout_lines=[_assistant_event("x")], stderr_lines=[])

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealClaudeClient()
    client.call(_call(stdout_log, stderr_log))
    argv = captured["argv"]
    assert "--session-id" in argv
    assert "--resume" not in argv
    # stream-json format flags must be present.
    assert "--output-format" in argv
    assert "stream-json" in argv
    assert "--verbose" in argv
    # Isolation flags. --bare is intentionally NOT used (breaks keychain auth).
    assert "--bare" not in argv
    assert "--disable-slash-commands" in argv
    assert "--tools" in argv
    # --tools is followed by empty string (disable all tools).
    tools_idx = argv.index("--tools")
    assert argv[tools_idx + 1] == ""
    assert "--dangerously-skip-permissions" in argv
    # Max agentic turns cap.
    assert "--max-turns" in argv
    max_turns_idx = argv.index("--max-turns")
    assert argv[max_turns_idx + 1] == "1"
    # Non-interactive system prompt is appended.
    assert "--append-system-prompt" in argv
    sp_idx = argv.index("--append-system-prompt")
    sys_prompt = argv[sp_idx + 1]
    assert "Do not ask clarifying questions" in sys_prompt
    assert "Do not offer follow-up options" in sys_prompt
    # Subprocess cwd is set to the log directory (not inherited from parent).
    assert captured["cwd"] == str(stdout_log.parent)


def test_real_client_argv_uses_resume_on_subsequent_call(monkeypatch, log_paths):
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    captured: dict = {}

    def fake_popen(argv, *a, **k):
        captured["argv"] = argv
        return _FakeProcess(stdout_lines=[_assistant_event("x")], stderr_lines=[])

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealClaudeClient()
    call = ClaudeCall(
        prompt="p", session_id="s", new_session=False, model=None,
        stdout_log_path=stdout_log, stderr_log_path=stderr_log,
        stream_header="── test ──",
    )
    client.call(call)
    assert "--resume" in captured["argv"]
    assert "--session-id" not in captured["argv"]


def test_real_client_strips_claudecode_env_var(monkeypatch, log_paths):
    """The child claude must not inherit CLAUDECODE, otherwise a nested
    claude -p call from inside Claude Code refuses to start."""
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setenv("CLAUDECODE", "1")
    captured: dict = {}

    def fake_popen(argv, *a, **k):
        captured["env"] = k.get("env") or {}
        return _FakeProcess(stdout_lines=[_assistant_event("ok")], stderr_lines=[])

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealClaudeClient()
    client.call(_call(stdout_log, stderr_log))
    assert "CLAUDECODE" not in captured["env"], (
        f"CLAUDECODE leaked into child env: {captured['env'].get('CLAUDECODE')}"
    )


# ─── _parse_stream_event tests ──────────────────────────────────────────────

def _thinking_event(text: str) -> str:
    import json as _json
    return _json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "thinking", "thinking": text}]},
    }) + "\n"


def _tool_use_event(name: str, tool_input: dict) -> str:
    import json as _json
    return _json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]},
    }) + "\n"


def _tool_result_event(content: str) -> str:
    import json as _json
    return _json.dumps({
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": content}]},
    }) + "\n"


def _result_event(turns: int = 3, duration_ms: int = 12500, cost_usd: float = 0.0421) -> str:
    import json as _json
    return _json.dumps({
        "type": "result",
        "num_turns": turns,
        "duration_ms": duration_ms,
        "total_cost_usd": cost_usd,
    }) + "\n"


def test_parse_stream_event_text_block():
    from prompt_runner.claude_client import _parse_stream_event
    items = _parse_stream_event(_assistant_event("hello world"))
    assert items == [("text", "hello world")]


def test_parse_stream_event_thinking_block():
    from prompt_runner.claude_client import _parse_stream_event
    items = _parse_stream_event(_thinking_event("let me think about this"))
    assert items == [("thinking", "let me think about this")]


def test_parse_stream_event_tool_use_bash():
    from prompt_runner.claude_client import _parse_stream_event
    items = _parse_stream_event(_tool_use_event("Bash", {"command": "echo hi"}))
    assert items == [("tool_use", "Bash: echo hi")]


def test_parse_stream_event_tool_use_read():
    from prompt_runner.claude_client import _parse_stream_event
    items = _parse_stream_event(_tool_use_event("Read", {"file_path": "/tmp/x.py"}))
    assert items == [("tool_use", "Read: /tmp/x.py")]


def test_parse_stream_event_tool_use_long_bash_truncated():
    from prompt_runner.claude_client import _parse_stream_event, TOOL_PREVIEW_MAX_CHARS
    long_cmd = "echo " + "x" * 200
    items = _parse_stream_event(_tool_use_event("Bash", {"command": long_cmd}))
    assert len(items) == 1
    kind, content = items[0]
    assert kind == "tool_use"
    assert content.startswith("Bash: ")
    # The displayed portion (after "Bash: ") must be within the preview limit.
    displayed = content[len("Bash: "):]
    assert len(displayed) <= TOOL_PREVIEW_MAX_CHARS


def test_parse_stream_event_tool_result():
    from prompt_runner.claude_client import _parse_stream_event
    items = _parse_stream_event(_tool_result_event("file contents here"))
    assert items == [("tool_result", "(18 chars)")]


def test_parse_stream_event_result_event():
    from prompt_runner.claude_client import _parse_stream_event
    items = _parse_stream_event(_result_event(turns=3, duration_ms=12500, cost_usd=0.0421))
    assert items == [("meta", "done: 3 turns, 12.5s, $0.0421")]


def test_parse_stream_event_system_event_silent():
    """System events (hook_started, session_start, etc) must produce no items."""
    from prompt_runner.claude_client import _parse_stream_event
    items = _parse_stream_event('{"type":"system","subtype":"hook_started"}\n')
    assert items == []


def test_thinking_does_not_pollute_response_stdout(monkeypatch, log_paths):
    """Thinking blocks must be displayed but must not end up in response.stdout."""
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    lines = [
        _thinking_event("internal reasoning"),
        _assistant_event("the actual answer"),
    ]
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *a, **k: _FakeProcess(stdout_lines=lines, stderr_lines=[]),
    )
    client = RealClaudeClient()
    response = client.call(_call(stdout_log, stderr_log))
    assert response.stdout == "the actual answer"
    # The raw log still has both events for debugging.
    raw = stdout_log.read_text()
    assert "internal reasoning" in raw
    assert "the actual answer" in raw


def test_tool_use_does_not_pollute_response_stdout(monkeypatch, log_paths):
    """Tool-use blocks must be displayed but must not end up in response.stdout."""
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    lines = [
        _tool_use_event("Bash", {"command": "echo hi"}),
        _assistant_event("the textual answer"),
    ]
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *a, **k: _FakeProcess(stdout_lines=lines, stderr_lines=[]),
    )
    client = RealClaudeClient()
    response = client.call(_call(stdout_log, stderr_log))
    assert response.stdout == "the textual answer"
    assert "echo hi" not in response.stdout
