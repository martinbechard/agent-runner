import json
from pathlib import Path

import pytest

from prompt_runner.claude_client import ClaudeCall, ClaudeInvocationError
from prompt_runner.codex_client import (
    CodexBinaryNotFound,
    NON_INTERACTIVE_PROMPT_PREFIX,
    RealCodexClient,
)


def _call(
    tmp_path: Path,
    *,
    new_session: bool,
    session_id: str = "sid",
    agent_name: str | None = None,
) -> ClaudeCall:
    return ClaudeCall(
        prompt="test prompt",
        session_id=session_id,
        new_session=new_session,
        model="gpt-5.4",
        stdout_log_path=tmp_path / "stdout.log",
        stderr_log_path=tmp_path / "stderr.log",
        stream_header="header",
        worktree_dir=tmp_path,
        agent_name=agent_name,
    )


class _FakePopen:
    def __init__(self, *, stdout: str, stderr: str = "", returncode: int = 0, pid: int = 43210):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.pid = pid
        self.stdout = iter(stdout.splitlines(keepends=True))
        self.stderr = iter(stderr.splitlines(keepends=True))

    def wait(self):
        return self.returncode


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
    assert "--ignore-user-config" in captured["argv"]
    assert "--ignore-rules" in captured["argv"]
    assert "--dangerously-bypass-approvals-and-sandbox" in captured["argv"]
    assert "--json" in captured["argv"]
    assert f'projects."{tmp_path}".trust_level="trusted"' in captured["argv"]
    assert 'history.persistence="none"' in captured["argv"]
    assert any(arg.startswith('log_dir="') for arg in captured["argv"])
    assert any(arg.startswith('sqlite_home="') for arg in captured["argv"])
    assert captured["argv"][-1].startswith(NON_INTERACTIVE_PROMPT_PREFIX)
    assert "test prompt" in captured["argv"][-1]
    assert response.stdout == "artifact body"
    assert response.session_id == "123e4567-e89b-12d3-a456-426614174000"
    process_meta = (
        tmp_path / ".run-files" / "backend-state" / "codex" / "process" / "sid.proc.json"
    ).read_text(encoding="utf-8")
    assert '"pid": 43210' in process_meta
    assert '"status": "completed"' in process_meta
    assert (tmp_path / "stdout.log").exists()
    assert (tmp_path / "stderr.log").exists()


def test_codex_call_loads_custom_agent_contract_and_logs_it(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")
    agent_dir = tmp_path / ".codex" / "agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "prompt-runner-generator.toml").write_text(
        'name = "prompt-runner-generator"\n'
        'developer_instructions = """You are the generator contract."""\n',
        encoding="utf-8",
    )
    captured: dict = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_path.write_text("artifact body\n", encoding="utf-8")
        return _FakePopen(stdout="")

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealCodexClient()
    response = client.call(
        _call(
            tmp_path,
            new_session=True,
            agent_name="prompt-runner-generator",
        )
    )
    assert response.stdout == "artifact body"
    prompt = captured["argv"][-1]
    assert "You are the generator contract." in prompt
    assert "test prompt" in prompt
    process_meta = json.loads(
        (
            tmp_path / ".run-files" / "backend-state" / "codex" / "process" / "sid.proc.json"
        ).read_text(encoding="utf-8")
    )
    assert process_meta["agent_name"] == "prompt-runner-generator"
    assert process_meta["agent_loaded"] is True
    assert process_meta["agent_path"].endswith("prompt-runner-generator.toml")


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
        worktree_dir=tmp_path,
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


def test_effort_override_is_forwarded_to_codex_config(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")
    captured: dict = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_path.write_text("artifact body\n", encoding="utf-8")
        return _FakePopen(stdout="")

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealCodexClient()
    call = _call(tmp_path, new_session=True)
    call = ClaudeCall(**{**call.__dict__, "effort": "high"})
    response = client.call(call)
    assert response.stdout == "artifact body"
    assert '-c' in captured["argv"]
    assert 'model_reasoning_effort="high"' in captured["argv"]


def test_effort_max_is_normalized_to_xhigh_for_codex(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")
    captured: dict = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_path.write_text("artifact body\n", encoding="utf-8")
        return _FakePopen(stdout="")

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealCodexClient()
    call = _call(tmp_path, new_session=True)
    call = ClaudeCall(**{**call.__dict__, "effort": "max"})
    response = client.call(call)
    assert response.stdout == "artifact body"
    assert 'model_reasoning_effort="xhigh"' in captured["argv"]


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


def test_parses_usage_and_duration_from_codex_json(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")

    def fake_popen(argv, **kwargs):
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_path.write_text("artifact body\n", encoding="utf-8")
        return _FakePopen(
            stdout=(
                '{"type":"turn.started"}\n'
                '{"type":"turn.completed","duration_ms":1234,"usage":{"input_tokens":11,"cached_input_tokens":2,"output_tokens":5}}\n'
            )
        )

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealCodexClient()
    response = client.call(_call(tmp_path, new_session=True))
    assert response.stdout == "artifact body"
    assert response.duration_ms == 1234
    assert response.usage is not None
    assert response.usage.input_tokens == 11
    assert response.usage.cached_input_tokens == 2
    assert response.usage.output_tokens == 5
    assert response.usage.total_tokens == 18


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


def test_retries_transient_high_demand_failure(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")
    sleeps: list[float] = []
    attempts = {"count": 0}

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def fake_popen(argv, **kwargs):
        attempts["count"] += 1
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        if attempts["count"] == 1:
            return _FakePopen(
                stdout=(
                    '{"type":"turn.started"}\n'
                    '{"type":"error","message":"We\'re currently experiencing high demand, which may cause temporary errors."}\n'
                    '{"type":"turn.failed","error":{"message":"We\'re currently experiencing high demand, which may cause temporary errors."}}\n'
                ),
                returncode=1,
            )
        message_path.write_text("artifact body\n", encoding="utf-8")
        return _FakePopen(stdout='{"type":"turn.completed"}\n')

    monkeypatch.setattr("time.sleep", fake_sleep)
    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealCodexClient()
    response = client.call(_call(tmp_path, new_session=True))
    assert response.stdout == "artifact body"
    assert attempts["count"] == 2
    assert sleeps == [2.0]
    stderr_log = (tmp_path / "stderr.log").read_text(encoding="utf-8")
    assert "transient codex failure on attempt 1" in stderr_log


def test_creates_stdout_and_stderr_logs_before_completion(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")

    def fake_popen(argv, **kwargs):
        stdout_log = tmp_path / "stdout.log"
        stderr_log = tmp_path / "stderr.log"
        assert stdout_log.exists()
        assert stderr_log.exists()
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_path.write_text("artifact body\n", encoding="utf-8")
        return _FakePopen(stdout='{"type":"turn.started"}\n', stderr="warn\n")

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealCodexClient()
    response = client.call(_call(tmp_path, new_session=True))
    assert response.stdout == "artifact body"
    assert (tmp_path / "stdout.log").read_text(encoding="utf-8") == '{"type":"turn.started"}\n'
    assert (tmp_path / "stderr.log").read_text(encoding="utf-8") == "warn\n"


def test_aggregate_process_log_receives_live_stdout_and_stderr(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")
    aggregate_log = tmp_path / "process.log"

    def fake_popen(argv, **kwargs):
        message_path = Path(argv[argv.index("--output-last-message") + 1])
        message_path.write_text("artifact body\n", encoding="utf-8")
        return _FakePopen(stdout='{"type":"turn.started"}\n', stderr="warn\n")

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealCodexClient()
    call = _call(tmp_path, new_session=True)
    call = ClaudeCall(**{**call.__dict__, "aggregate_log_path": aggregate_log, "aggregate_log_prefix": "generator prompt=1 iter=1"})
    response = client.call(call)
    assert response.stdout == "artifact body"
    text = aggregate_log.read_text(encoding="utf-8")
    assert "[generator prompt=1 iter=1 stdout]" in text
    assert "[generator prompt=1 iter=1 stderr]" in text


def test_fork_session_is_unsupported(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")
    client = RealCodexClient()
    call = _call(tmp_path, new_session=True)
    call = ClaudeCall(**{**call.__dict__, "fork_session": True})
    with pytest.raises(ClaudeInvocationError) as exc_info:
        client.call(call)
    assert "fork-session" in exc_info.value.response.stderr
