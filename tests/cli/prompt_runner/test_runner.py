from pathlib import Path

import pytest

from prompt_runner.parser import PromptPair
from prompt_runner.runner import (
    VERDICT_INSTRUCTION,
    ANTI_ANCHORING_CLAUSE,
    REVISION_GENERATOR_PREAMBLE,
    build_initial_generator_message,
    build_initial_judge_message,
    build_revision_generator_message,
    build_revision_judge_message,
)


def _pair(index: int, title: str, gen: str = "GEN", val: str = "VAL") -> PromptPair:
    return PromptPair(
        index=index,
        title=title,
        generation_prompt=gen,
        validation_prompt=val,
        heading_line=1,
        generation_line=2,
        validation_line=5,
    )


def test_initial_generator_message_with_no_priors_is_verbatim():
    p = _pair(1, "First", gen="the body")
    assert build_initial_generator_message(p, []) == "the body"


def test_initial_generator_message_injects_priors():
    p = _pair(2, "Second", gen="the task body")
    msg = build_initial_generator_message(
        p,
        [("First", "ARTIFACT-ONE"), ("A", "ARTIFACT-A")],
    )
    assert "ARTIFACT-ONE" in msg
    assert "ARTIFACT-A" in msg
    assert "# Prior approved artifacts" in msg
    assert "# Your task" in msg
    assert "the task body" in msg


def test_initial_judge_message_includes_verdict_instruction():
    p = _pair(1, "First", val="please evaluate")
    msg = build_initial_judge_message(p, "ARTIFACT")
    assert "please evaluate" in msg
    assert "ARTIFACT" in msg
    assert VERDICT_INSTRUCTION in msg


def test_revision_generator_message_contains_preamble_and_feedback():
    msg = build_revision_generator_message("some feedback")
    assert REVISION_GENERATOR_PREAMBLE in msg
    assert "some feedback" in msg


def test_revision_judge_message_contains_anti_anchoring_and_artifact():
    msg = build_revision_judge_message("NEW-ARTIFACT")
    assert ANTI_ANCHORING_CLAUSE in msg
    assert "NEW-ARTIFACT" in msg
    assert VERDICT_INSTRUCTION in msg


from prompt_runner.claude_client import (
    ClaudeCall,
    ClaudeInvocationError,
    ClaudeResponse,
    FakeClaudeClient,
)
from prompt_runner.runner import (
    PipelineResult,
    PromptResult,
    RunConfig,
    run_pipeline,
    run_prompt,
)
from prompt_runner.verdict import Verdict


def _pass_response(text: str = "ARTIFACT") -> ClaudeResponse:
    return ClaudeResponse(stdout=text, stderr="", returncode=0)


def _judge_pass() -> ClaudeResponse:
    return ClaudeResponse(stdout="All good.\n\nVERDICT: pass", stderr="", returncode=0)


def _judge_revise(note: str = "Fix this.") -> ClaudeResponse:
    return ClaudeResponse(
        stdout=f"{note}\n\nVERDICT: revise", stderr="", returncode=0
    )


def _judge_escalate() -> ClaudeResponse:
    return ClaudeResponse(
        stdout="Cannot continue.\n\nVERDICT: escalate", stderr="", returncode=0
    )


def test_single_prompt_passes_first_try(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response("gen-output"), _judge_pass()])
    result = run_prompt(
        pair=pair,
        prior_artifacts=[],
        run_dir=tmp_path / "run",
        config=RunConfig(),
        claude_client=client,
        run_id="testrun",
    )
    assert result.final_verdict == Verdict.PASS
    assert len(result.iterations) == 1
    assert len(client.received) == 2  # one generator, one judge
    assert client.received[0].new_session is True
    assert client.received[1].new_session is True
    assert client.received[0].session_id != client.received[1].session_id


def test_single_prompt_passes_on_second_iteration(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[
        _pass_response("gen-1"),
        _judge_revise("needs work"),
        _pass_response("gen-2-revised"),
        _judge_pass(),
    ])
    result = run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=client, run_id="testrun",
    )
    assert result.final_verdict == Verdict.PASS
    assert len(result.iterations) == 2
    assert result.final_artifact == "gen-2-revised"
    assert len(client.received) == 4
    # Iteration 1 uses new sessions; iteration 2 resumes.
    assert client.received[0].new_session is True
    assert client.received[1].new_session is True
    assert client.received[2].new_session is False
    assert client.received[3].new_session is False
    # Generator's revision call contains the judge's feedback.
    assert "needs work" in client.received[2].prompt


def test_escalation_on_max_iterations(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[
        _pass_response("g1"), _judge_revise("r1"),
        _pass_response("g2"), _judge_revise("r2"),
        _pass_response("g3"), _judge_revise("r3"),
    ])
    result = run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(max_iterations=3), claude_client=client,
        run_id="testrun",
    )
    assert result.final_verdict == Verdict.ESCALATE
    assert len(result.iterations) == 3
    assert len(client.received) == 6


def test_direct_escalation(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response("g1"), _judge_escalate()])
    result = run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=client, run_id="testrun",
    )
    assert result.final_verdict == Verdict.ESCALATE
    assert len(result.iterations) == 1
    assert len(client.received) == 2


def test_prior_artifacts_injected_into_next_prompt(tmp_path: Path):
    p1 = _pair(1, "First")
    p2 = _pair(2, "Second")
    client = FakeClaudeClient(scripted=[
        _pass_response("ARTIFACT-ONE"), _judge_pass(),
        _pass_response("ARTIFACT-TWO"), _judge_pass(),
    ])
    result = run_pipeline(
        pairs=[p1, p2],
        run_dir=tmp_path / "run",
        config=RunConfig(),
        claude_client=client,
        source_file=tmp_path / "source.md",
    )
    assert not result.halted_early
    # prompt 2's generator call (index 2 in received) should contain ARTIFACT-ONE.
    assert "ARTIFACT-ONE" in client.received[2].prompt
    # prompt 1's generator call should not mention "Prior approved artifacts".
    assert "Prior approved artifacts" not in client.received[0].prompt


def test_escalation_halts_pipeline(tmp_path: Path):
    p1 = _pair(1, "First")
    p2 = _pair(2, "Second")
    p3 = _pair(3, "Third")
    client = FakeClaudeClient(scripted=[
        _pass_response("a1"), _judge_pass(),    # p1 passes
        _pass_response("a2"), _judge_escalate(),  # p2 escalates
        # p3 must not run
    ])
    result = run_pipeline(
        pairs=[p1, p2, p3], run_dir=tmp_path / "run", config=RunConfig(),
        claude_client=client, source_file=tmp_path / "source.md",
    )
    assert result.halted_early
    assert len(result.prompt_results) == 2
    assert len(client.received) == 4
    # Explicitly verify p3 was never invoked (more robust than len-only check).
    for call in client.received:
        assert "prompt-3" not in call.session_id, (
            f"Prompt 3 should not have been called, but got: {call.session_id}"
        )


def test_only_flag_runs_single_prompt(tmp_path: Path):
    p1 = _pair(1, "First")
    p2 = _pair(2, "Second")
    p3 = _pair(3, "Third")
    client = FakeClaudeClient(scripted=[_pass_response("a2"), _judge_pass()])
    result = run_pipeline(
        pairs=[p1, p2, p3], run_dir=tmp_path / "run",
        config=RunConfig(only=2), claude_client=client,
        source_file=tmp_path / "source.md",
    )
    assert not result.halted_early
    assert len(client.received) == 2
    # Prompt 2's generator call should NOT contain any prior-artifact injection.
    assert "Prior approved artifacts" not in client.received[0].prompt


def test_session_ids_are_valid_uuids_and_distinct(tmp_path: Path):
    """Claude CLI requires --session-id to be a valid UUID, and generator
    and judge sessions must be distinct to prevent context contamination."""
    import uuid as _uuid
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=client, run_id="myrun",
    )
    gen_call, jud_call = client.received
    # Must be valid UUIDs.
    _uuid.UUID(gen_call.session_id)
    _uuid.UUID(jud_call.session_id)
    # Must be distinct.
    assert gen_call.session_id != jud_call.session_id


def test_session_ids_are_deterministic(tmp_path: Path):
    """Iteration 2's --resume must use the same session ID that iteration 1
    created with --session-id, so the mapping from logical label to UUID
    must be stable across iterations."""
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[
        _pass_response(), _judge_revise(),
        _pass_response(), _judge_pass(),
    ])
    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=client, run_id="myrun",
    )
    # Iteration 1 generator and iteration 2 generator share the same session.
    assert client.received[0].session_id == client.received[2].session_id
    # Same for judge.
    assert client.received[1].session_id == client.received[3].session_id


def test_resume_flag_set_on_iterations_after_first(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[
        _pass_response(), _judge_revise(),
        _pass_response(), _judge_pass(),
    ])
    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=client, run_id="myrun",
    )
    # Iter 1: both calls new_session=True. Iter 2: both calls new_session=False.
    assert [c.new_session for c in client.received] == [True, True, False, False]


def test_log_paths_passed_to_every_call(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    run_dir = tmp_path / "run"
    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=run_dir,
        config=RunConfig(), claude_client=client, run_id="myrun",
    )
    for call in client.received:
        assert call.stdout_log_path.parent.parent == run_dir / "logs"
        assert call.stdout_log_path.name.startswith("iter-01-")
        assert call.stdout_log_path.name.endswith(".stdout.log")


def test_logs_dir_created_before_first_call(tmp_path: Path):
    pair = _pair(1, "Alpha")
    captured = []

    class AssertingClient:
        def call(self, call):
            # Capture the existence of the parent dir at the moment of the call.
            captured.append(call.stdout_log_path.parent.exists())
            return _pass_response() if "generator" in call.stream_header else _judge_pass()

    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=AssertingClient(), run_id="myrun",
    )
    assert all(captured), "logs directory was not created before a claude call"


def test_halt_on_claude_failure_writes_partial_md(tmp_path: Path):
    pair = _pair(1, "Alpha")
    gen_ok = _pass_response("g1")
    judge_partial = ClaudeResponse(stdout="PARTIAL-JUDGE-OUTPUT", stderr="oops", returncode=1)
    # Need a real ClaudeCall for the error's .call field; use any.
    # The fake client raises this exception on the second call.
    dummy_call = ClaudeCall(
        prompt="", session_id="x", new_session=True, model=None,
        stdout_log_path=Path("/tmp/x"), stderr_log_path=Path("/tmp/x"),
        stream_header="── test ──",
    )
    err = ClaudeInvocationError(dummy_call, judge_partial)
    client = FakeClaudeClient(scripted=[gen_ok, err])
    with pytest.raises(ClaudeInvocationError):
        run_prompt(
            pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
            config=RunConfig(), claude_client=client, run_id="myrun",
        )
    judge_md = tmp_path / "run" / "prompt-01-alpha" / "iter-01-judge.md"
    assert judge_md.exists()
    assert judge_md.read_text() == "PARTIAL-JUDGE-OUTPUT"


def test_unparseable_verdict_halts_pipeline(tmp_path: Path):
    pair = _pair(1, "Alpha")
    bad_judge = ClaudeResponse(stdout="no verdict here at all", stderr="", returncode=0)
    client = FakeClaudeClient(scripted=[_pass_response(), bad_judge])
    result = run_pipeline(
        pairs=[pair], run_dir=tmp_path / "run", config=RunConfig(),
        claude_client=client, source_file=tmp_path / "source.md",
    )
    assert result.halted_early
    assert result.halt_reason is not None
    assert "R-NO-VERDICT" in result.halt_reason


def test_dry_run_makes_no_real_calls(tmp_path: Path):
    from prompt_runner.claude_client import DryRunClaudeClient
    pair = _pair(1, "Alpha")
    client = DryRunClaudeClient()
    # DryRunClaudeClient returns stdout that has no VERDICT line, so we expect
    # the pipeline to halt at the first judge call with R-NO-VERDICT — that is
    # the correct dry-run behaviour because dry-run is about skipping the
    # subprocess, not about bypassing verdict parsing. The test asserts that no
    # subprocess-style activity happened (the DryRunClient recorded the call
    # but didn't spawn anything).
    result = run_pipeline(
        pairs=[pair], run_dir=tmp_path / "run",
        config=RunConfig(dry_run=True), claude_client=client,
        source_file=tmp_path / "source.md",
    )
    # At least the first generator call was recorded.
    assert len(client.received) >= 1
    assert result.halted_early  # because DryRun responses have no VERDICT line


def test_summary_txt_is_written_on_halt(tmp_path: Path):
    """Halting the pipeline must write summary.txt before exit."""
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_escalate()])
    run_dir = tmp_path / "run"
    run_pipeline(
        pairs=[pair], run_dir=run_dir, config=RunConfig(),
        claude_client=client, source_file=tmp_path / "source.md",
    )
    summary_path = run_dir / "summary.txt"
    assert summary_path.exists()
    text = summary_path.read_text()
    assert "alpha" in text
    assert "escalate" in text
    assert "halted" in text


def test_skipped_prompts_appear_in_summary(tmp_path: Path):
    """Prompts that never ran (because the pipeline halted earlier) must appear as 'skipped' in summary.txt."""
    p1 = _pair(1, "First")
    p2 = _pair(2, "Second")
    p3 = _pair(3, "Third")
    client = FakeClaudeClient(scripted=[
        _pass_response("a1"), _judge_pass(),      # p1 passes
        _pass_response("a2"), _judge_escalate(),  # p2 escalates
        # p3 never runs
    ])
    run_dir = tmp_path / "run"
    run_pipeline(
        pairs=[p1, p2, p3], run_dir=run_dir, config=RunConfig(),
        claude_client=client, source_file=tmp_path / "source.md",
    )
    summary_text = (run_dir / "summary.txt").read_text()
    # p1 ran and passed
    assert "first" in summary_text
    assert "pass" in summary_text
    # p2 ran and escalated
    assert "second" in summary_text
    assert "escalate" in summary_text
    # p3 never ran — must appear as "skipped"
    assert "third" in summary_text
    assert "skipped" in summary_text


def test_max_iterations_zero_raises(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[])
    with pytest.raises(ValueError, match="max_iterations must be >= 1"):
        run_prompt(
            pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
            config=RunConfig(max_iterations=0),
            claude_client=client, run_id="testrun",
        )


from prompt_runner.__main__ import main


def test_cli_parse_subcommand_prints_all_prompts(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures" / "sample-prompts.md"
    exit_code = main(["parse", str(fixture)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Prompt 1: First Thing" in out
    assert "Prompt 2: Second Thing" in out


def test_cli_parse_subcommand_reports_parse_error(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures" / "missing-validator.md"
    exit_code = main(["parse", str(fixture)])
    err = capsys.readouterr().err
    assert exit_code == 2
    assert "E-MISSING-VALIDATION" in err
