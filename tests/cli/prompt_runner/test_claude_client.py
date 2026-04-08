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
        return _FakeProcess(stdout_lines=[_assistant_event("x")], stderr_lines=[])

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealClaudeClient()
    client.call(_call(stdout_log, stderr_log))
    assert "--session-id" in captured["argv"]
    assert "--resume" not in captured["argv"]
    # stream-json format flags must be present.
    assert "--output-format" in captured["argv"]
    assert "stream-json" in captured["argv"]
    assert "--verbose" in captured["argv"]


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
