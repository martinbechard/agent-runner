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
