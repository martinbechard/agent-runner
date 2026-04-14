from pathlib import Path

import pytest

from prompt_runner.claude_client import ClaudeCall, ClaudeInvocationError
from prompt_runner.codex_client import (
    CodexBinaryNotFound,
    NON_INTERACTIVE_PROMPT_PREFIX,
    RealCodexClient,
)


def _call(tmp_path: Path, *, new_session: bool, session_id: str = "sid") -> ClaudeCall:
    return ClaudeCall(
        prompt="test prompt",
        session_id=session_id,
        new_session=new_session,
        model="gpt-5.4",
        stdout_log_path=tmp_path / "stdout.log",
        stderr_log_path=tmp_path / "stderr.log",
        stream_header="header",
        workspace_dir=tmp_path,
    )


class _Completed:
    def __init__(self, *, stdout: str, stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class _FakePopen:
    def __init__(self, *, stdout: str, stderr: str = "", returncode: int = 0, pid: int = 43210):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.pid = pid

    def communicate(self):
        return self._stdout, self._stderr


def test_raises_when_codex_not_on_path(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(CodexBinaryNotFound):
        RealCodexClient()


def test_new_session_uses_codex_exec_and_reads_last_message(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")
    captured: dict = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_path.write_text("artifact body\n", encoding="utf-8")
        return _FakePopen(stdout="session id: 123e4567-e89b-12d3-a456-426614174000\n")

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealCodexClient()
    response = client.call(_call(tmp_path, new_session=True))
    assert captured["argv"][:2] == ["codex", "exec"]
    assert "--json" in captured["argv"]
    assert f'projects."{tmp_path}".trust_level="trusted"' in captured["argv"]
    assert 'approval_policy="never"' in captured["argv"]
    assert 'history.persistence="none"' in captured["argv"]
    assert 'sandbox_mode="danger-full-access"' in captured["argv"]
    assert any(arg.startswith('log_dir="') for arg in captured["argv"])
    assert any(arg.startswith('sqlite_home="') for arg in captured["argv"])
    assert captured["argv"][-1].startswith(NON_INTERACTIVE_PROMPT_PREFIX)
    assert "test prompt" in captured["argv"][-1]
    assert response.stdout == "artifact body"
    assert response.session_id == "123e4567-e89b-12d3-a456-426614174000"
    process_meta = (tmp_path / "stdout.proc.json").read_text(encoding="utf-8")
    assert '"pid": 43210' in process_meta
    assert '"status": "completed"' in process_meta


def test_output_last_message_uses_absolute_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")
    captured: dict = {}

    call = ClaudeCall(
        prompt="test prompt",
        session_id="sid",
        new_session=True,
        model="gpt-5.4",
        stdout_log_path=Path("relative") / "stdout.log",
        stderr_log_path=Path("relative") / "stderr.log",
        stream_header="header",
        workspace_dir=tmp_path,
    )

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_path.parent.mkdir(parents=True, exist_ok=True)
        message_path.write_text("artifact body\n", encoding="utf-8")
        return _FakePopen(stdout="")

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealCodexClient()
    client.call(call)
    message_arg = captured["argv"][captured["argv"].index("--output-last-message") + 1]
    assert Path(message_arg).is_absolute()


def test_subsequent_calls_still_use_stateless_codex_exec(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")
    captured: dict = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_path.write_text("revised artifact\n", encoding="utf-8")
        return _FakePopen(stdout="")

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealCodexClient()
    response = client.call(_call(tmp_path, new_session=False, session_id="resume-sid"))
    assert captured["argv"][:2] == ["codex", "exec"]
    assert "resume" not in captured["argv"]
    assert "--json" in captured["argv"]
    assert response.stdout == "revised artifact"
    assert response.session_id == "resume-sid"


def test_falls_back_to_last_agent_message_when_sidecar_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")

    def fake_popen(argv, **kwargs):
        return _FakePopen(
            stdout=(
                '{"type":"thread.started","thread_id":"abc"}\n'
                '{"type":"turn.started"}\n'
                '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"VERDICT: pass"}}\n'
                '{"type":"turn.completed","usage":{"input_tokens":1,"cached_input_tokens":0,"output_tokens":2}}\n'
            )
        )

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealCodexClient()
    response = client.call(_call(tmp_path, new_session=True))
    assert response.stdout == "VERDICT: pass"


def test_nonzero_exit_raises_with_partial_message(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")

    def fake_popen(argv, **kwargs):
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_path.write_text("partial artifact\n", encoding="utf-8")
        return _FakePopen(stdout="", stderr="boom\n", returncode=1)

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealCodexClient()
    with pytest.raises(ClaudeInvocationError) as exc_info:
        client.call(_call(tmp_path, new_session=True))
    assert exc_info.value.response.stdout == "partial artifact"
    assert exc_info.value.response.stderr == "boom\n"


def test_fork_session_is_unsupported(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")
    client = RealCodexClient()
    call = _call(tmp_path, new_session=True)
    call = ClaudeCall(**{**call.__dict__, "fork_session": True})
    with pytest.raises(ClaudeInvocationError) as exc_info:
        client.call(call)
    assert "fork-session" in exc_info.value.response.stderr
