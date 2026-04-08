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


def test_real_client_raises_when_claude_not_on_path(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(ClaudeBinaryNotFound):
        RealClaudeClient()


def test_real_client_writes_stdout_log(monkeypatch, log_paths):
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")

    def fake_popen(*args, **kwargs):
        return _FakeProcess(stdout_lines=["hello\n", "world\n"], stderr_lines=[])

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealClaudeClient()
    response = client.call(_call(stdout_log, stderr_log))
    assert response.returncode == 0
    assert response.stdout == "hello\nworld\n"
    assert stdout_log.read_text() == "hello\nworld\n"
    assert stderr_log.read_text() == ""


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
            stdout_lines=["partial\n"], stderr_lines=["boom\n"], returncode=1
        ),
    )
    client = RealClaudeClient()
    with pytest.raises(ClaudeInvocationError) as exc_info:
        client.call(_call(stdout_log, stderr_log))
    assert exc_info.value.response.stdout == "partial\n"
    assert exc_info.value.response.stderr == "boom\n"
    assert exc_info.value.response.returncode == 1


def test_real_client_argv_uses_session_id_on_first_call(monkeypatch, log_paths):
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    captured: dict = {}

    def fake_popen(argv, *a, **k):
        captured["argv"] = argv
        return _FakeProcess(stdout_lines=["x\n"], stderr_lines=[])

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealClaudeClient()
    client.call(_call(stdout_log, stderr_log))
    assert "--session-id" in captured["argv"]
    assert "--resume" not in captured["argv"]


def test_real_client_argv_uses_resume_on_subsequent_call(monkeypatch, log_paths):
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    captured: dict = {}

    def fake_popen(argv, *a, **k):
        captured["argv"] = argv
        return _FakeProcess(stdout_lines=["x\n"], stderr_lines=[])

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
