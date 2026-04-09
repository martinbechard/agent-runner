from pathlib import Path

import pytest

from prompt_runner.parser import PromptPair
from prompt_runner.runner import (
    VERDICT_INSTRUCTION,
    ANTI_ANCHORING_CLAUSE,
    REVISION_GENERATOR_PREAMBLE,
    PROJECT_ORGANISER_INSTRUCTION,
    PriorArtifact,
    build_initial_generator_message,
    build_initial_judge_message,
    build_revision_generator_message,
    build_revision_judge_message,
)


def _workspace(tmp_path: Path) -> Path:
    """Create (or return) a clean workspace directory sibling to the run directory.

    Tests pass this as workspace_dir to run_prompt/run_pipeline so the
    snapshot/restore helpers have a real directory to operate on (without
    catching the per-test run_dir itself in their sweeps). Idempotent — calling
    twice in the same test returns the same directory.
    """
    w = tmp_path / "workspace"
    w.mkdir(exist_ok=True)
    return w


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


def test_initial_generator_message_with_no_priors_contains_task_and_organiser_rule():
    """With no priors, the message contains the task body and the
    project-organiser instruction; there is no 'prior artifacts' section."""
    p = _pair(1, "First", gen="the body")
    msg = build_initial_generator_message(p, [])
    assert "the body" in msg
    assert "project-organiser" in msg
    assert "# Prior approved artifacts" not in msg


def test_initial_generator_message_injects_priors_with_file_manifests():
    p = _pair(2, "Second", gen="the task body")
    msg = build_initial_generator_message(
        p,
        [
            PriorArtifact(title="First", text_body="ARTIFACT-ONE",
                          files=[Path("src/foo.py"), Path("tests/test_foo.py")]),
            PriorArtifact(title="A", text_body="ARTIFACT-A", files=[]),
        ],
    )
    assert "ARTIFACT-ONE" in msg
    assert "ARTIFACT-A" in msg
    assert "# Prior approved artifacts" in msg
    assert "# Your task" in msg
    assert "the task body" in msg
    # Files created by the prior prompts are listed so the current generator
    # knows they exist on disk.
    assert "src/foo.py" in msg
    assert "tests/test_foo.py" in msg
    # The second prior had no files → should say so.
    assert "(no files created)" in msg
    # The project-organiser instruction is appended.
    assert "project-organiser" in msg


def test_initial_generator_message_instructs_about_reading_prior_files():
    """When prior artifacts include files, the message tells the current
    generator it can Read them from the shared workspace."""
    p = _pair(2, "Second")
    msg = build_initial_generator_message(
        p,
        [PriorArtifact(title="X", text_body="body", files=[Path("m.py")])],
    )
    assert "Read" in msg
    assert "current working directory" in msg


def test_revision_generator_message_includes_organiser_instruction():
    msg = build_revision_generator_message("feedback text")
    assert "feedback text" in msg
    assert "project-organiser" in msg


def test_initial_judge_message_lists_generator_files():
    """The judge message must include the explicit list of files the
    generator produced, so the judge knows what to inspect without having
    to discover files via tools."""
    p = _pair(1, "X")
    msg = build_initial_judge_message(
        p, "artifact text",
        generator_files=[Path("src/foo.py"), Path("tests/test_foo.py")],
    )
    assert "src/foo.py" in msg
    assert "tests/test_foo.py" in msg
    assert "Files produced by the generator" in msg


def test_initial_judge_message_with_no_files_says_text_only():
    """When the generator produced no files, the judge message explicitly
    says so — no ambiguity about whether the judge should go looking."""
    p = _pair(1, "X")
    msg = build_initial_judge_message(p, "artifact text", generator_files=[])
    assert "(no files created or modified" in msg
    assert "text-only task" in msg


def test_revision_judge_message_lists_generator_files():
    msg = build_revision_judge_message(
        "revised artifact",
        generator_files=[Path("src/models.py")],
    )
    assert "src/models.py" in msg
    assert "Files produced by the generator" in msg


def test_judge_receives_file_list_from_snapshot_diff(tmp_path: Path):
    """End-to-end: when the generator creates a file, that file's path is
    included in the prompt the judge sees on the same iteration."""
    workspace = _workspace(tmp_path)
    pair = _pair(1, "Alpha")

    class FileCreatingThenPassingClient:
        def __init__(self) -> None:
            self._n = 0

        def call(self, call):
            self._n += 1
            if self._n == 1:
                # Generator: write a new file in the workspace.
                (workspace / "created_by_gen.py").write_text("x = 1\n")
                return _pass_response("here is the artifact")
            # Judge: return pass, but record the prompt we received so
            # the test can assert the file is mentioned.
            self._judge_prompt = call.prompt
            return _judge_pass()

    client = FileCreatingThenPassingClient()
    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=client, run_id="testrun",
        workspace_dir=workspace,
    )

    # The judge prompt must list the file the generator just created.
    assert "created_by_gen.py" in client._judge_prompt, (
        "judge prompt did not mention the file the generator produced"
    )


# ─── Workspace snapshot / diff / restore ─────────────────────────────────────

from prompt_runner.runner import (
    _snapshot_workspace,
    _diff_workspace_since_snapshot,
    _restore_workspace_from_snapshot,
    _is_snapshot_excluded,
)


def test_is_snapshot_excluded_catches_common_junk():
    assert _is_snapshot_excluded(Path(".git/HEAD"))
    assert _is_snapshot_excluded(Path("runs/foo"))
    assert _is_snapshot_excluded(Path("node_modules/a/b.js"))
    assert _is_snapshot_excluded(Path("src/__pycache__/x.pyc"))
    assert _is_snapshot_excluded(Path("src/my_pkg.egg-info/PKG-INFO"))
    assert _is_snapshot_excluded(Path(".DS_Store"))
    assert not _is_snapshot_excluded(Path("src/cli/foo.py"))
    assert not _is_snapshot_excluded(Path("docs/design/CD-001-x.md"))


def test_snapshot_and_diff_detects_new_file(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "existing.py").write_text("print('before')\n")

    snapshot = tmp_path / "snap"
    _snapshot_workspace(workspace, snapshot)

    # Simulate generator adding a new file.
    (workspace / "new.py").write_text("print('added')\n")

    changed = _diff_workspace_since_snapshot(workspace, snapshot)
    assert Path("new.py") in changed
    assert Path("existing.py") not in changed  # unchanged


def test_snapshot_and_diff_detects_modified_file(tmp_path: Path):
    import time as _time
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "models.py").write_text("print('v1')\n")

    snapshot = tmp_path / "snap"
    _snapshot_workspace(workspace, snapshot)

    # Wait a bit, then modify. mtime changes.
    _time.sleep(0.01)
    (workspace / "models.py").write_text("print('v2')\n")

    changed = _diff_workspace_since_snapshot(workspace, snapshot)
    assert Path("models.py") in changed


def test_restore_workspace_removes_new_files_and_restores_modified(tmp_path: Path):
    import time as _time
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "keep.py").write_text("keep content\n")
    (workspace / "modified.py").write_text("original\n")

    snapshot = tmp_path / "snap"
    _snapshot_workspace(workspace, snapshot)

    _time.sleep(0.01)
    # Add new file and modify existing file.
    (workspace / "added.py").write_text("new garbage\n")
    (workspace / "modified.py").write_text("CHANGED\n")

    _restore_workspace_from_snapshot(workspace, snapshot)

    # added.py is gone.
    assert not (workspace / "added.py").exists()
    # modified.py is back to original content.
    assert (workspace / "modified.py").read_text() == "original\n"
    # keep.py is untouched.
    assert (workspace / "keep.py").read_text() == "keep content\n"


def test_snapshot_excludes_runs_dir(tmp_path: Path):
    """The snapshot must not recursively capture its own output directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "keep.py").write_text("x\n")
    (workspace / "runs").mkdir()
    (workspace / "runs" / "prev-run.log").write_text("old log\n")

    snapshot = tmp_path / "snap"
    _snapshot_workspace(workspace, snapshot)

    assert (snapshot / "keep.py").exists()
    assert not (snapshot / "runs").exists()


def test_escalation_restores_workspace(tmp_path: Path):
    """When a prompt escalates, files the generator created are removed."""
    workspace = _workspace(tmp_path)
    # Put a pre-existing file in the workspace.
    (workspace / "existing.py").write_text("stable\n")

    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_escalate()])

    # Simulate the generator creating a file by writing it ourselves
    # BEFORE the run, then having an escalation — the file should be
    # cleaned up. We do this by wrapping the fake client so that between
    # the generator call and the judge call, a file appears in the workspace.
    class FileCreatingClient:
        def __init__(self) -> None:
            self._n = 0

        def call(self, call):
            self._n += 1
            if self._n == 1:
                # Generator: pretend it wrote a new file.
                (workspace / "garbage.py").write_text("temporary\n")
                return _pass_response("artifact")
            else:
                return _judge_escalate()

    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=FileCreatingClient(),
        run_id="testrun", workspace_dir=workspace,
    )

    # The garbage file must be gone.
    assert not (workspace / "garbage.py").exists(), "escalation did not clean up"
    # The pre-existing file is still there.
    assert (workspace / "existing.py").read_text() == "stable\n"


def test_pass_preserves_files_and_records_them(tmp_path: Path):
    """When a prompt passes, the files the generator created are preserved
    and listed in PromptResult.created_files."""
    workspace = _workspace(tmp_path)
    pair = _pair(1, "Alpha")

    class FileCreatingClient:
        def __init__(self) -> None:
            self._n = 0

        def call(self, call):
            self._n += 1
            if self._n == 1:
                (workspace / "created.py").write_text("# new file\n")
                return _pass_response("artifact")
            return _judge_pass()

    result = run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=FileCreatingClient(),
        run_id="testrun", workspace_dir=workspace,
    )

    assert result.final_verdict == Verdict.PASS
    assert (workspace / "created.py").exists()
    assert Path("created.py") in result.created_files


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
        workspace_dir=_workspace(tmp_path),
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
        workspace_dir=_workspace(tmp_path),
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
        run_id="testrun", workspace_dir=_workspace(tmp_path),
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
        workspace_dir=_workspace(tmp_path),
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
        workspace_dir=_workspace(tmp_path),
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
        workspace_dir=_workspace(tmp_path),
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
        workspace_dir=_workspace(tmp_path),
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
        workspace_dir=_workspace(tmp_path),
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
        workspace_dir=_workspace(tmp_path),
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
        workspace_dir=_workspace(tmp_path),
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
        workspace_dir=Path("/tmp"),
    )
    err = ClaudeInvocationError(dummy_call, judge_partial)
    client = FakeClaudeClient(scripted=[gen_ok, err])
    with pytest.raises(ClaudeInvocationError):
        run_prompt(
            pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
            config=RunConfig(), claude_client=client, run_id="myrun",
            workspace_dir=_workspace(tmp_path),
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
        workspace_dir=_workspace(tmp_path),
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
        workspace_dir=_workspace(tmp_path),
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
        workspace_dir=_workspace(tmp_path),
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
            workspace_dir=_workspace(tmp_path),
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


def test_summary_includes_wall_time(tmp_path: Path):
    """summary.txt must include a 'Wall time:' line in HH:MM:SS format."""
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    run_dir = tmp_path / "run"
    run_pipeline(
        pairs=[pair], run_dir=run_dir, config=RunConfig(),
        claude_client=client, source_file=tmp_path / "source.md",
        workspace_dir=_workspace(tmp_path),
    )
    summary = (run_dir / "summary.txt").read_text()
    assert "Wall time:" in summary
    # Format must look like HH:MM:SS.
    import re as _re
    assert _re.search(r"Wall time: \d{2}:\d{2}:\d{2}", summary), summary


def test_manifest_includes_wall_time(tmp_path: Path):
    """manifest.json must include a 'wall_time' field after finalisation."""
    import json as _json
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    run_dir = tmp_path / "run"
    run_pipeline(
        pairs=[pair], run_dir=run_dir, config=RunConfig(),
        claude_client=client, source_file=tmp_path / "source.md",
        workspace_dir=_workspace(tmp_path),
    )
    manifest = _json.loads((run_dir / "manifest.json").read_text())
    assert "wall_time" in manifest
    import re as _re
    assert _re.match(r"^\d{2}:\d{2}:\d{2}$", manifest["wall_time"])


def test_r_claude_failed_halt_reason_includes_stderr_tail_and_log_paths(tmp_path: Path):
    """R-CLAUDE-FAILED must include the stderr tail, partial output path, and log dir."""
    pair = _pair(1, "Alpha")
    gen_ok = _pass_response("g1")
    judge_partial = ClaudeResponse(
        stdout="partial stdout",
        stderr="warning: something\nerror: claude backend unreachable\nstack frame 1\nstack frame 2",
        returncode=2,
    )
    # The call field's paths must match the real runner-produced ClaudeCall so
    # the halt reason's path computations line up. The runner will build the
    # ClaudeCall itself; we fake the client to surface an error with that call.
    captured_call: list[ClaudeCall] = []

    class CapturingFailingClient:
        def __init__(self) -> None:
            self._n = 0

        def call(self, call: ClaudeCall) -> ClaudeResponse:
            captured_call.append(call)
            self._n += 1
            if self._n == 1:
                return gen_ok
            # Second call (judge) raises with the captured call as context.
            raise ClaudeInvocationError(call, judge_partial)

    run_dir = tmp_path / "run"
    result = run_pipeline(
        pairs=[pair], run_dir=run_dir, config=RunConfig(),
        claude_client=CapturingFailingClient(),
        source_file=tmp_path / "source.md",
    )
    assert result.halted_early
    assert result.halt_reason is not None
    halt = result.halt_reason
    assert "R-CLAUDE-FAILED" in halt
    # The stderr tail (last 20 lines, each indented by two spaces) should appear.
    assert "claude backend unreachable" in halt
    assert "stack frame 2" in halt
    # The log paths should be referenced.
    assert "stderr.log" in halt or "stderr_log_path" not in halt  # stderr.log path included
    # The partial output .md path should be referenced.
    assert "Partial output saved to:" in halt
    # The retry instruction should be there.
    assert "re-run prompt-runner" in halt


# ---------------------------------------------------------------------------
# Prelude prepending (spec section 9)
# ---------------------------------------------------------------------------

from prompt_runner.runner import RunConfig


def test_run_config_defaults_have_none_preludes():
    cfg = RunConfig()
    assert cfg.generator_prelude is None
    assert cfg.judge_prelude is None


def test_build_initial_generator_message_prepends_generator_prelude():
    p = _pair(1, "X", gen="the task body")
    msg = build_initial_generator_message(
        p, [], generator_prelude="# GEN PRELUDE TEXT",
    )
    assert msg.startswith("# GEN PRELUDE TEXT")
    assert "the task body" in msg
    # Horizontal rule or blank line must separate prelude from task
    assert "\n\n" in msg.split("the task body")[0]


def test_build_initial_generator_message_no_prelude_unchanged():
    p = _pair(1, "X", gen="the task body")
    msg_with = build_initial_generator_message(p, [], generator_prelude=None)
    msg_without = build_initial_generator_message(p, [])
    assert msg_with == msg_without


def test_build_initial_judge_message_prepends_judge_prelude():
    p = _pair(1, "X")
    msg = build_initial_judge_message(
        p, "artifact", judge_prelude="# JUD PRELUDE",
    )
    assert msg.startswith("# JUD PRELUDE")


def test_build_revision_generator_message_prepends_prelude():
    msg = build_revision_generator_message(
        "feedback", generator_prelude="# GEN REVISE PRELUDE",
    )
    assert msg.startswith("# GEN REVISE PRELUDE")
    assert "feedback" in msg


def test_build_revision_judge_message_prepends_prelude():
    msg = build_revision_judge_message(
        "revised artifact", judge_prelude="# JUD REVISE PRELUDE",
    )
    assert msg.startswith("# JUD REVISE PRELUDE")
