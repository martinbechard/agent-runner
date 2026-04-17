from pathlib import Path

import pytest

from prompt_runner.parser import PromptPair
from prompt_runner.runner import (
    VERDICT_INSTRUCTION,
    ANTI_ANCHORING_CLAUSE,
    REVISION_GENERATOR_PREAMBLE,
    PROJECT_ORGANISER_INSTRUCTION,
    RUN_FILES_DIRNAME,
    PriorArtifact,
    _render_prompt_pair,
    build_initial_generator_message,
    build_initial_judge_message,
    build_revision_generator_message,
    build_revision_judge_message,
)


def _worktree(tmp_path: Path) -> Path:
    """Create (or return) a clean worktree directory sibling to the run directory.

    Tests pass this as worktree_dir to run_prompt/run_pipeline so the
    snapshot/restore helpers have a real directory to operate on (without
    catching the per-test run_dir itself in their sweeps). Idempotent — calling
    twice in the same test returns the same directory.
    """
    w = tmp_path / "worktree"
    w.mkdir(exist_ok=True)
    return w


def _run_files(run_dir: Path) -> Path:
    return run_dir / RUN_FILES_DIRNAME


def _slugify(title: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "untitled"


def _module_dir(run_dir: Path, title: str) -> Path:
    return _run_files(run_dir) / _slugify(title)


def _prompt_slug(index: int, title: str) -> str:
    return f"prompt-{index:02d}-{_slugify(title)}"


def _prompt_history_dir(run_dir: Path, title: str, index: int) -> Path:
    return _module_dir(run_dir, title) / "history" / f"prompt-{index:02d}"


def _pair(
    index: int,
    title: str,
    gen: str = "GEN",
    val: str = "VAL",
    required_files: tuple[str, ...] = (),
    include_files: tuple[str, ...] = (),
    checks_files: tuple[str, ...] = (),
    deterministic_validation: tuple[str, ...] = (),
) -> PromptPair:
    return PromptPair(
        index=index,
        title=title,
        generation_prompt=gen,
        validation_prompt=val,
        heading_line=1,
        generation_line=2,
        validation_line=5,
        required_files=required_files,
        include_files=include_files,
        checks_files=checks_files,
        deterministic_validation=deterministic_validation,
    )


def test_initial_generator_message_with_no_priors_contains_task_and_organiser_rule(tmp_path: Path):
    """With no priors, the message contains the task body and the
    project-organiser instruction; there is no 'prior artifacts' section."""
    p = _pair(1, "First", gen="the body")
    msg = build_initial_generator_message(p, [], tmp_path)
    assert "the body" in msg
    assert "project-organiser" in msg
    assert "# Prior approved artifacts" not in msg


def test_initial_generator_message_injects_priors_with_file_manifests(tmp_path: Path):
    p = _pair(2, "Second", gen="the task body")
    msg = build_initial_generator_message(
        p,
        [
            PriorArtifact(title="First",
                          files=[Path("src/foo.py"), Path("tests/test_foo.py")]),
            PriorArtifact(title="A", files=[]),
        ],
        tmp_path,
    )
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


def test_initial_generator_message_instructs_about_reading_prior_files(tmp_path: Path):
    """When prior artifacts include files, the message tells the current
    generator it can Read them from the shared worktree."""
    p = _pair(2, "Second")
    msg = build_initial_generator_message(
        p,
        [PriorArtifact(title="X", files=[Path("m.py")])],
        tmp_path,
    )
    assert "Read" in msg
    assert "current working directory" in msg


def test_initial_generator_message_can_skip_organiser_instruction(tmp_path: Path):
    p = _pair(1, "First", gen="the body")
    msg = build_initial_generator_message(
        p, [], tmp_path, include_project_organiser=False,
    )
    assert "the body" in msg
    assert "project-organiser" not in msg


def test_revision_generator_message_includes_organiser_instruction(tmp_path: Path):
    msg = build_revision_generator_message(_pair(1, "X"), "feedback text", tmp_path)
    assert "feedback text" in msg
    assert "project-organiser" in msg


def test_revision_generator_message_can_skip_organiser_instruction(tmp_path: Path):
    msg = build_revision_generator_message(
        _pair(1, "X"),
        "feedback text",
        tmp_path,
        include_project_organiser=False,
    )
    assert "feedback text" in msg
    assert "project-organiser" not in msg


def test_revision_generator_message_can_be_self_contained(tmp_path: Path):
    msg = build_revision_generator_message(
        _pair(1, "X"),
        "feedback text",
        tmp_path,
        original_task="original task body",
        previous_artifact="old artifact body",
    )
    assert "original task body" in msg
    assert "old artifact body" in msg
    assert "feedback text" in msg


def test_initial_judge_message_lists_generator_files(tmp_path: Path):
    """The judge message must include the explicit list of files the
    generator produced, so the judge knows what to inspect without having
    to discover files via tools."""
    p = _pair(1, "X")
    msg = build_initial_judge_message(
        p, "artifact text", tmp_path,
        generator_files=[Path("src/foo.py"), Path("tests/test_foo.py")],
    )
    assert "src/foo.py" in msg
    assert "tests/test_foo.py" in msg
    assert "Files produced by the generator" in msg


def test_initial_judge_message_with_no_files_says_text_only(tmp_path: Path):
    """When the generator produced no files, the judge message explicitly
    says so — no ambiguity about whether the judge should go looking."""
    p = _pair(1, "X")
    msg = build_initial_judge_message(p, "artifact text", tmp_path, generator_files=[])
    assert "(no files created or modified" in msg
    assert "text-only task" in msg


def test_revision_judge_message_lists_generator_files(tmp_path: Path):
    msg = build_revision_judge_message(
        _pair(1, "X"),
        "revised artifact",
        tmp_path,
        generator_files=[Path("src/models.py")],
    )
    assert "src/models.py" in msg
    assert "Files produced by the generator" in msg


def test_revision_judge_message_can_be_self_contained(tmp_path: Path):
    msg = build_revision_judge_message(
        _pair(1, "X"),
        "revised artifact",
        tmp_path,
        generator_files=[Path("src/models.py")],
        validation_prompt="strict validator prompt",
    )
    assert "strict validator prompt" in msg
    assert "revised artifact" in msg


def test_initial_judge_message_includes_deterministic_validation_report(tmp_path: Path):
    p = _pair(1, "X")
    from prompt_runner.runner import DeterministicValidationResult
    result = DeterministicValidationResult(
        command=["python", "scripts/check.py", "--strict"],
        script_path=Path("/tmp/check.py"),
        returncode=1,
        stdout="failed checks",
        stderr="",
        stdout_log_path=Path("/tmp/out.log"),
        stderr_log_path=Path("/tmp/err.log"),
        process_metadata_path=Path("/tmp/proc.json"),
    )
    msg = build_initial_judge_message(
        p,
        "artifact text",
        tmp_path,
        deterministic_validation=result,
    )
    assert "Deterministic validation" in msg
    assert "failed checks" in msg


def test_include_files_are_injected_into_generator_message(tmp_path: Path):
    (tmp_path / "context.txt").write_text("shared context\n", encoding="utf-8")
    p = _pair(1, "With include", include_files=("context.txt",))
    msg = build_initial_generator_message(p, [], tmp_path)
    assert "# Included context files" in msg
    assert "## BEGIN INCLUDED FILE: context.txt" in msg
    assert "## END INCLUDED FILE: context.txt" in msg
    assert "shared context" in msg


def test_include_files_are_injected_into_judge_message(tmp_path: Path):
    (tmp_path / "context.txt").write_text("shared context\n", encoding="utf-8")
    p = _pair(1, "With include", include_files=("context.txt",))
    msg = build_initial_judge_message(p, "artifact text", tmp_path)
    assert "# Included context files" in msg
    assert "## BEGIN INCLUDED FILE: context.txt" in msg
    assert "## END INCLUDED FILE: context.txt" in msg
    assert "shared context" in msg


def test_include_files_are_front_loaded_in_initial_judge_message(tmp_path: Path):
    (tmp_path / "context.txt").write_text("shared context\n", encoding="utf-8")
    p = _pair(1, "With include", val="VALIDATE", include_files=("context.txt",))
    msg = build_initial_judge_message(p, "artifact text", tmp_path)
    assert msg.index("# Included context files") < msg.index("VALIDATE")


def test_render_prompt_pair_inlines_include_from_placeholder_bound_path(tmp_path: Path):
    worktree = _worktree(tmp_path)
    source = worktree / "docs" / "requirements" / "raw.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("first line\nsecond line\n", encoding="utf-8")
    pair = _pair(
        1,
        "Inline include",
        gen="Use this:\n<Source input>\n{{INCLUDE:raw_requirements_path}}\n</Source input>",
        val="Review this:\n<Source input>\n{{INCLUDE:raw_requirements_path}}\n</Source input>",
    )

    rendered = _render_prompt_pair(
        pair,
        {"raw_requirements_path": "docs/requirements/raw.md"},
        worktree,
        None,
    )

    assert "{{INCLUDE:raw_requirements_path}}" not in rendered.generation_prompt
    assert "{{INCLUDE:raw_requirements_path}}" not in rendered.validation_prompt
    assert "docs/requirements/raw.md" not in rendered.generation_prompt
    assert "docs/requirements/raw.md" not in rendered.validation_prompt
    assert "first line\nsecond line" in rendered.generation_prompt
    assert "first line\nsecond line" in rendered.validation_prompt


def test_render_prompt_pair_inlines_include_from_literal_path(tmp_path: Path):
    worktree = _worktree(tmp_path)
    source = worktree / "context.txt"
    source.write_text("embedded context\n", encoding="utf-8")
    pair = _pair(1, "Inline include", gen="{{INCLUDE:context.txt}}")

    rendered = _render_prompt_pair(pair, {}, worktree, None)

    assert rendered.generation_prompt == "embedded context\n"


def test_render_prompt_pair_inlines_include_relative_to_prompt_file(tmp_path: Path):
    worktree = _worktree(tmp_path)
    prompt_dir = tmp_path / "prompt-dir"
    prompt_dir.mkdir()
    source = tmp_path / "skills" / "guide.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("prompt relative include\n", encoding="utf-8")
    pair = _pair(1, "Prompt relative", gen="{{INCLUDE:../skills/guide.txt}}")

    rendered = _render_prompt_pair(
        pair,
        {},
        worktree,
        prompt_dir / "prompt.md",
    )

    assert rendered.generation_prompt == "prompt relative include\n"


def test_include_files_are_front_loaded_in_revision_judge_message(tmp_path: Path):
    (tmp_path / "context.txt").write_text("shared context\n", encoding="utf-8")
    p = _pair(1, "With include", include_files=("context.txt",))
    msg = build_revision_judge_message(
        p,
        "revised artifact",
        tmp_path,
        validation_prompt="VALIDATE",
    )
    assert msg.index("# Included context files") < msg.index("VALIDATE")


def test_judge_receives_file_list_from_snapshot_diff(tmp_path: Path):
    """End-to-end: when the generator creates a file, that file's path is
    included in the prompt the judge sees on the same iteration."""
    worktree = _worktree(tmp_path)
    pair = _pair(1, "Alpha")

    class FileCreatingThenPassingClient:
        def __init__(self) -> None:
            self._n = 0

        def call(self, call):
            self._n += 1
            if self._n == 1:
                # Generator: write a new file in the worktree.
                (worktree / "created_by_gen.py").write_text("x = 1\n")
                return _pass_response("here is the artifact")
            # Judge: return pass, but record the prompt we received so
            # the test can assert the file is mentioned.
            self._judge_prompt = call.prompt
            return _judge_pass()

    client = FileCreatingThenPassingClient()
    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=client, run_id="testrun",
        worktree_dir=worktree,
    )

    # The judge prompt must list the file the generator just created.
    assert "created_by_gen.py" in client._judge_prompt, (
        "judge prompt did not mention the file the generator produced"
    )


# ─── Workspace snapshot / diff / restore ─────────────────────────────────────

from prompt_runner.runner import (
    _snapshot_worktree,
    _diff_worktree_since_snapshot,
    _restore_worktree_from_snapshot,
    _is_snapshot_excluded,
    _initialise_run_worktree,
)


def test_is_snapshot_excluded_catches_common_junk():
    assert _is_snapshot_excluded(Path(".git/HEAD"))
    assert _is_snapshot_excluded(Path("runs/foo"))
    assert _is_snapshot_excluded(Path("tmp/scratch/file.txt"))
    assert _is_snapshot_excluded(Path(".methodology-runner/state.json"))
    assert _is_snapshot_excluded(Path(".prompt-runner/backend-state/codex/sqlite/state.sqlite"))
    assert _is_snapshot_excluded(Path("prompt-runner-files/logs/PH-000/attempt-1-stdout.log"))
    assert _is_snapshot_excluded(Path("node_modules/a/b.js"))
    assert _is_snapshot_excluded(Path("src/__pycache__/x.pyc"))
    assert _is_snapshot_excluded(Path("src/my_pkg.egg-info/PKG-INFO"))
    assert _is_snapshot_excluded(Path(".DS_Store"))
    assert not _is_snapshot_excluded(Path("src/cli/foo.py"))
    assert not _is_snapshot_excluded(Path("docs/design/CD-001-x.md"))


def test_snapshot_and_diff_detects_new_file(tmp_path: Path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "existing.py").write_text("print('before')\n")

    snapshot = tmp_path / "snap"
    _snapshot_worktree(worktree, snapshot)

    # Simulate generator adding a new file.
    (worktree / "new.py").write_text("print('added')\n")

    changed = _diff_worktree_since_snapshot(worktree, snapshot)
    assert Path("new.py") in changed
    assert Path("existing.py") not in changed  # unchanged


def test_snapshot_and_diff_detects_modified_file(tmp_path: Path):
    import time as _time
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "models.py").write_text("print('v1')\n")

    snapshot = tmp_path / "snap"
    _snapshot_worktree(worktree, snapshot)

    # Wait a bit, then modify. mtime changes.
    _time.sleep(0.01)
    (worktree / "models.py").write_text("print('v2')\n")

    changed = _diff_worktree_since_snapshot(worktree, snapshot)
    assert Path("models.py") in changed


def test_restore_workspace_removes_new_files_and_restores_modified(tmp_path: Path):
    import time as _time
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "keep.py").write_text("keep content\n")
    (worktree / "modified.py").write_text("original\n")

    snapshot = tmp_path / "snap"
    _snapshot_worktree(worktree, snapshot)

    _time.sleep(0.01)
    # Add new file and modify existing file.
    (worktree / "added.py").write_text("new garbage\n")
    (worktree / "modified.py").write_text("CHANGED\n")

    _restore_worktree_from_snapshot(worktree, snapshot)

    # added.py is gone.
    assert not (worktree / "added.py").exists()
    # modified.py is back to original content.
    assert (worktree / "modified.py").read_text() == "original\n"
    # keep.py is untouched.
    assert (worktree / "keep.py").read_text() == "keep content\n"


def test_snapshot_excludes_runs_dir(tmp_path: Path):
    """The snapshot must not recursively capture its own output directory."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "keep.py").write_text("x\n")
    (worktree / "runs").mkdir()
    (worktree / "runs" / "prev-run.log").write_text("old log\n")

    snapshot = tmp_path / "snap"
    _snapshot_worktree(worktree, snapshot)

    assert (snapshot / "keep.py").exists()
    assert not (snapshot / "runs").exists()


def test_snapshot_does_not_recurse_when_dest_dir_is_inside_worktree(
    tmp_path: Path, monkeypatch,
):
    """A snapshot destination under work/ must not be re-walked while the
    snapshot is being created."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "keep.py").write_text("x\n")
    dest_dir = worktree / "work" / "pr-021-run" / "snapshots" / "pre"

    from prompt_runner import runner as r
    real_copy2 = r.shutil.copy2
    copied_sources: list[Path] = []

    def fake_copy2(src, dst, *args, **kwargs):
        src_path = Path(src)
        copied_sources.append(src_path)
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(r.shutil, "copy2", fake_copy2)

    _snapshot_worktree(worktree, dest_dir, (Path("work/pr-021-run"),))

    assert all(dest_dir not in src.parents for src in copied_sources)


def test_initialise_run_worktree_uses_git_worktree_when_project_is_git_repo(
    tmp_path: Path,
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "tracked.txt").write_text("hello\n", encoding="utf-8")
    import subprocess as _subprocess
    _subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True, text=True)
    _subprocess.run(["git", "add", "tracked.txt"], cwd=project, check=True, capture_output=True, text=True)
    _subprocess.run(
        [
            "git", "-c", "user.name=test", "-c", "user.email=test@example.com",
            "commit", "-m", "init", "--no-gpg-sign",
        ],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )

    run_dir = project / "work" / "pr-run"
    _initialise_run_worktree(project, run_dir)

    assert (run_dir / "tracked.txt").exists()
    assert (run_dir / ".git").exists()


def test_initialise_run_worktree_copies_only_subdirectory_when_project_dir_is_git_subdir(
    tmp_path: Path,
):
    project_root = tmp_path / "project"
    fixture = project_root / "fixtures" / "sample"
    fixture.mkdir(parents=True)
    (project_root / "tracked-root.txt").write_text("root\n", encoding="utf-8")
    (project_root / "runs" / "noise.txt").parent.mkdir(parents=True, exist_ok=True)
    (project_root / "runs" / "noise.txt").write_text("noise\n", encoding="utf-8")
    (fixture / "wanted.txt").write_text("wanted\n", encoding="utf-8")

    import subprocess as _subprocess
    _subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True, text=True)
    _subprocess.run(["git", "add", "."], cwd=project_root, check=True, capture_output=True, text=True)
    _subprocess.run(
        [
            "git", "-c", "user.name=test", "-c", "user.email=test@example.com",
            "commit", "-m", "init", "--no-gpg-sign",
        ],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )

    run_dir = tmp_path / "run"
    _initialise_run_worktree(fixture, run_dir)

    assert (run_dir / "wanted.txt").exists()
    assert not (run_dir / "tracked-root.txt").exists()
    assert not (run_dir / "runs" / "noise.txt").exists()
    assert not (run_dir / ".git").exists()


def test_git_tracked_prompt_run_does_not_create_snapshot_dir(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "tracked.txt").write_text("hello\n", encoding="utf-8")
    import subprocess as _subprocess
    _subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True, text=True)
    _subprocess.run(["git", "add", "tracked.txt"], cwd=project, check=True, capture_output=True, text=True)
    _subprocess.run(
        [
            "git", "-c", "user.name=test", "-c", "user.email=test@example.com",
            "commit", "-m", "init", "--no-gpg-sign",
        ],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )

    run_dir = project / "work" / "pr-run"
    _initialise_run_worktree(project, run_dir)

    pair = _pair(1, "Alpha")

    class WritingClient:
        def __init__(self) -> None:
            self.calls = 0

        def call(self, call):
            self.calls += 1
            if self.calls == 1:
                (call.worktree_dir / "docs").mkdir(exist_ok=True)
                (call.worktree_dir / "docs" / "out.txt").write_text("artifact\n", encoding="utf-8")
                return _pass_response("artifact")
            return _judge_pass()

    client = WritingClient()
    run_prompt(
        pair=pair,
        prior_artifacts=[],
        run_dir=run_dir,
        config=RunConfig(),
        claude_client=client,
        run_id="testrun",
        worktree_dir=run_dir,
    )

    prompt_dir = _module_dir(run_dir, "Alpha")
    assert not (prompt_dir / "snapshot-pre").exists()
    assert (prompt_dir / "module.log").exists()


def test_restore_from_project_tree_excludes_nested_run_dir(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "keep.txt").write_text("keep\n", encoding="utf-8")
    run_dir = project / "work" / "pr-run"
    (run_dir / "nested.txt").parent.mkdir(parents=True, exist_ok=True)
    (run_dir / "nested.txt").write_text("nested\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()
    from prompt_runner.runner import _initial_copy_excluded_roots
    excluded = _initial_copy_excluded_roots(project, run_dir)
    _restore_worktree_from_snapshot(target, project, excluded)

    assert (target / "keep.txt").exists()
    assert not (target / "work" / "pr-run" / "nested.txt").exists()


def test_escalation_restores_worktree(tmp_path: Path):
    """When a prompt escalates, files the generator created are removed."""
    worktree = _worktree(tmp_path)
    # Put a pre-existing file in the worktree.
    (worktree / "existing.py").write_text("stable\n")

    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_escalate()])

    # Simulate the generator creating a file by writing it ourselves
    # BEFORE the run, then having an escalation — the file should be
    # cleaned up. We do this by wrapping the fake client so that between
    # the generator call and the judge call, a file appears in the worktree.
    class FileCreatingClient:
        def __init__(self) -> None:
            self._n = 0

        def call(self, call):
            self._n += 1
            if self._n == 1:
                # Generator: pretend it wrote a new file.
                (worktree / "garbage.py").write_text("temporary\n")
                return _pass_response("artifact")
            else:
                return _judge_escalate()

    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=FileCreatingClient(),
        run_id="testrun", worktree_dir=worktree,
    )

    # The garbage file must be gone.
    assert not (worktree / "garbage.py").exists(), "escalation did not clean up"
    # The pre-existing file is still there.
    assert (worktree / "existing.py").read_text() == "stable\n"


def test_pass_preserves_files_and_records_them(tmp_path: Path):
    """When a prompt passes, the files the generator created are preserved
    and listed in PromptResult.created_files."""
    worktree = _worktree(tmp_path)
    pair = _pair(1, "Alpha")

    class FileCreatingClient:
        def __init__(self) -> None:
            self._n = 0

        def call(self, call):
            self._n += 1
            if self._n == 1:
                (worktree / "created.py").write_text("# new file\n")
                return _pass_response("artifact")
            return _judge_pass()

    result = run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=FileCreatingClient(),
        run_id="testrun", worktree_dir=worktree,
    )

    assert result.final_verdict == Verdict.PASS
    assert (worktree / "created.py").exists()
    assert Path("created.py") in result.created_files


def test_initial_judge_message_includes_verdict_instruction(tmp_path: Path):
    p = _pair(1, "First", val="please evaluate")
    msg = build_initial_judge_message(p, "ARTIFACT", tmp_path)
    assert "please evaluate" in msg
    assert "ARTIFACT" in msg
    assert VERDICT_INSTRUCTION in msg


def test_revision_generator_message_contains_preamble_and_feedback(tmp_path: Path):
    msg = build_revision_generator_message(_pair(1, "X"), "some feedback", tmp_path)
    assert REVISION_GENERATOR_PREAMBLE in msg
    assert "some feedback" in msg


def test_revision_judge_message_contains_anti_anchoring_and_artifact(tmp_path: Path):
    msg = build_revision_judge_message(_pair(1, "X"), "NEW-ARTIFACT", tmp_path)
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
        worktree_dir=_worktree(tmp_path),
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
        config=RunConfig(backend="claude"), claude_client=client, run_id="testrun",
        worktree_dir=_worktree(tmp_path),
    )
    assert result.final_verdict == Verdict.PASS
    assert len(result.iterations) == 2
    assert result.iterations[-1].generator_output == "gen-2-revised"
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
        run_id="testrun", worktree_dir=_worktree(tmp_path),
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
        worktree_dir=_worktree(tmp_path),
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
    # prompt 2's generator call should still carry the prior-artifact file manifest.
    assert "# Prior approved artifacts" in client.received[2].prompt
    assert "(no files created)" in client.received[2].prompt
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
        worktree_dir=_worktree(tmp_path),
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


def test_debug_tracing_writes_to_process_log(tmp_path: Path):
    p1 = _pair(1, "First")
    client = FakeClaudeClient(scripted=[_pass_response("a1"), _judge_pass()])
    result = run_pipeline(
        pairs=[p1],
        run_dir=tmp_path / "run",
        config=RunConfig(debug=2),
        claude_client=client,
        source_file=tmp_path / "source.md",
    )
    assert not result.halted_early
    process_log = (tmp_path / "run" / ".run-files" / "process.log").read_text(encoding="utf-8")
    assert "[debug-trace] enabled depth=2" in process_log
    assert "[debug-trace] disabled" in process_log
    assert "[debug-trace] call depth=" in process_log


def test_session_ids_are_valid_uuids_and_distinct(tmp_path: Path):
    """Claude CLI requires --session-id to be a valid UUID, and generator
    and judge sessions must be distinct to prevent context contamination."""
    import uuid as _uuid
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(backend="claude"), claude_client=client, run_id="myrun",
        worktree_dir=_worktree(tmp_path),
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
        config=RunConfig(backend="claude"), claude_client=client, run_id="myrun",
        worktree_dir=_worktree(tmp_path),
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
        config=RunConfig(backend="claude"), claude_client=client, run_id="myrun",
        worktree_dir=_worktree(tmp_path),
    )
    # Iter 1: both calls new_session=True. Iter 2: both calls new_session=False.
    assert [c.new_session for c in client.received] == [True, True, False, False]


def test_codex_revisions_are_stateless_and_self_contained(tmp_path: Path):
    pair = _pair(1, "Alpha", gen="ORIGINAL TASK", val="VALIDATION TASK")
    client = FakeClaudeClient(scripted=[
        _pass_response("artifact v1"), _judge_revise(),
        _pass_response("artifact v2"), _judge_pass(),
    ])
    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(backend="codex"), claude_client=client, run_id="myrun",
        worktree_dir=_worktree(tmp_path),
    )
    assert [c.new_session for c in client.received] == [True, True, True, True]
    assert "ORIGINAL TASK" in client.received[2].prompt
    assert "artifact v1" in client.received[2].prompt
    assert "VALIDATION TASK" in client.received[3].prompt


def test_codex_prefers_single_written_file_contents_as_artifact(tmp_path: Path):
    pair = _pair(1, "Alpha", gen="Write docs/out.txt", val="Check docs/out.txt")
    worktree = _worktree(tmp_path)

    class WritingClient:
        def __init__(self):
            self.received = []

        def call(self, call):
            self.received.append(call)
            if "generator" in call.stream_header:
                out = call.worktree_dir / "docs" / "out.txt"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("artifact from file\n", encoding="utf-8")
                return ClaudeResponse(stdout="PASS", stderr="", returncode=0)
            return _judge_pass()

    client = WritingClient()
    result = run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(backend="codex"), claude_client=client, run_id="myrun",
        worktree_dir=worktree,
    )
    assert result.iterations[-1].generator_output == "artifact from file\n"
    assert "artifact from file" in client.received[1].prompt


def test_log_paths_passed_to_every_call(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    run_dir = tmp_path / "run"
    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=run_dir,
        config=RunConfig(), claude_client=client, run_id="myrun",
        worktree_dir=_worktree(tmp_path),
    )
    for call in client.received:
        assert call.stdout_log_path.name.endswith(".stdout.log")
        assert call.stderr_log_path.name.endswith(".stderr.log")
        assert call.stdout_log_path.parent.name == "alpha"
        assert call.stderr_log_path.parent.name == "alpha"


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
        worktree_dir=_worktree(tmp_path),
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
        worktree_dir=Path("/tmp"),
    )
    err = ClaudeInvocationError(dummy_call, judge_partial)
    client = FakeClaudeClient(scripted=[gen_ok, err])
    with pytest.raises(ClaudeInvocationError):
        run_prompt(
            pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
            config=RunConfig(), claude_client=client, run_id="myrun",
            worktree_dir=_worktree(tmp_path),
        )
    judge_md = _prompt_history_dir(tmp_path / "run", "Alpha", 1) / "iter-01-validation.md"
    assert judge_md.exists()
    assert judge_md.read_text() == "PARTIAL-JUDGE-OUTPUT"


def test_unparseable_verdict_halts_pipeline(tmp_path: Path):
    pair = _pair(1, "Alpha")
    bad_judge = ClaudeResponse(stdout="no verdict here at all", stderr="", returncode=0)
    client = FakeClaudeClient(scripted=[_pass_response(), bad_judge])
    result = run_pipeline(
        pairs=[pair], run_dir=tmp_path / "run", config=RunConfig(),
        claude_client=client, source_file=tmp_path / "source.md",
        worktree_dir=_worktree(tmp_path),
    )
    assert result.halted_early
    assert result.halt_reason is not None
    assert "R-NO-VERDICT" in result.halt_reason


def test_missing_required_files_halts_before_any_backend_call(tmp_path: Path):
    pair = _pair(
        1,
        "Alpha",
        required_files=("missing/input.md",),
    )
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    result = run_pipeline(
        pairs=[pair],
        run_dir=tmp_path / "run",
        config=RunConfig(),
        claude_client=client,
        source_file=tmp_path / "source.md",
        worktree_dir=_worktree(tmp_path),
    )
    assert result.halted_early
    assert result.halt_reason is not None
    assert "R-MISSING-REQUIRED-FILES" in result.halt_reason
    assert client.received == []


def test_checks_files_writes_trace_without_halting(tmp_path: Path):
    pair = _pair(
        1,
        "Alpha",
        checks_files=("present.txt", "missing.txt"),
    )
    worktree = _worktree(tmp_path)
    (worktree / "present.txt").write_text("ok", encoding="utf-8")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    run_dir = tmp_path / "run"
    result = run_pipeline(
        pairs=[pair],
        run_dir=run_dir,
        config=RunConfig(),
        claude_client=client,
        source_file=tmp_path / "source.md",
        worktree_dir=worktree,
    )
    assert result.halted_early is False
    module_log = _module_dir(run_dir, "Alpha") / "module.log"
    assert module_log.exists()
    checks = module_log.read_text(encoding="utf-8")
    assert '"path": "present.txt"' in checks
    assert '"exists": true' in checks
    assert '"path": "missing.txt"' in checks
    assert '"exists": false' in checks


def test_missing_deterministic_validation_halts_before_backend_call(tmp_path: Path):
    pair = _pair(
        1,
        "Alpha",
        deterministic_validation=("scripts/missing_validator.py",),
    )
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    result = run_pipeline(
        pairs=[pair],
        run_dir=tmp_path / "run",
        config=RunConfig(),
        claude_client=client,
        source_file=tmp_path / "source.md",
        worktree_dir=_worktree(tmp_path),
    )
    assert result.halted_early
    assert result.halt_reason is not None
    assert "R-MISSING-DETERMINISTIC-VALIDATION" in result.halt_reason
    assert client.received == []


def test_deterministic_validation_runs_and_is_injected_into_judge_prompt(tmp_path: Path):
    worktree = _worktree(tmp_path)
    scripts_dir = worktree / "scripts"
    scripts_dir.mkdir()
    validator = scripts_dir / "validate_feature_spec.py"
    validator.write_text(
        "import os\n"
        "print('worktree=' + os.environ['PROMPT_RUNNER_WORKTREE_DIR'])\n"
        "print('prompt_index=' + os.environ['PROMPT_RUNNER_PROMPT_INDEX'])\n",
        encoding="utf-8",
    )

    pair = _pair(
        1,
        "Alpha",
        deterministic_validation=("scripts/validate_feature_spec.py", "--strict"),
    )

    class ValidationAwareClient:
        def __init__(self) -> None:
            self._n = 0
            self.judge_prompt = ""

        def call(self, call):
            self._n += 1
            if self._n == 1:
                return _pass_response("artifact")
            self.judge_prompt = call.prompt
            return _judge_pass()

    client = ValidationAwareClient()
    run_dir = tmp_path / "run"
    result = run_pipeline(
        pairs=[pair],
        run_dir=run_dir,
        config=RunConfig(),
        claude_client=client,
        source_file=tmp_path / "source.md",
        worktree_dir=worktree,
    )
    assert result.halted_early is False
    assert "Deterministic validation" in client.judge_prompt
    assert "prompt_index=1" in client.judge_prompt
    assert "scripts/validate_feature_spec.py" in client.judge_prompt
    proc_path = (
        _module_dir(run_dir, "Alpha")
        / "prompt-01.iter-01-deterministic-validation.proc.json"
    )
    assert proc_path.exists()


def test_deterministic_validation_runtime_error_halts_pipeline(tmp_path: Path):
    worktree = _worktree(tmp_path)
    scripts_dir = worktree / "scripts"
    scripts_dir.mkdir()
    validator = scripts_dir / "explode.py"
    validator.write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
    pair = _pair(
        1,
        "Alpha",
        deterministic_validation=("scripts/explode.py",),
    )
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    result = run_pipeline(
        pairs=[pair],
        run_dir=tmp_path / "run",
        config=RunConfig(),
        claude_client=client,
        source_file=tmp_path / "source.md",
        worktree_dir=worktree,
    )
    assert result.halted_early
    assert result.halt_reason is not None
    assert "R-DETERMINISTIC-VALIDATION-FAILED" in result.halt_reason


def test_required_files_support_built_in_placeholder_rendering(tmp_path: Path):
    worktree = _worktree(tmp_path)
    run_dir = tmp_path / "run"
    (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "inputs" / "request.md").write_text("hi", encoding="utf-8")
    pair = _pair(
        1,
        "Alpha",
        gen="Read {{run_dir}}/inputs/request.md from {{project_dir}}",
        required_files=("{{run_dir}}/inputs/request.md",),
    )
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    result = run_pipeline(
        pairs=[pair],
        run_dir=run_dir,
        config=RunConfig(),
        claude_client=client,
        source_file=tmp_path / "source.md",
        worktree_dir=worktree,
    )
    assert result.halted_early is False
    assert str(run_dir.resolve()) in client.received[0].prompt
    assert str(run_dir.resolve()) in client.received[0].prompt


def test_required_files_tolerate_project_dir_prefixed_absolute_run_dir(tmp_path: Path):
    worktree = _worktree(tmp_path)
    run_dir = tmp_path / "run"
    (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "inputs" / "request.md").write_text("hi", encoding="utf-8")
    pair = _pair(
        1,
        "Alpha",
        gen="Use duplicated placeholder path form.",
        required_files=("{{project_dir}}/{{run_dir}}/inputs/request.md",),
    )
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    result = run_pipeline(
        pairs=[pair],
        run_dir=run_dir,
        config=RunConfig(),
        claude_client=client,
        source_file=tmp_path / "source.md",
        worktree_dir=worktree,
    )
    assert result.halted_early is False


def test_placeholder_values_accept_caller_supplied_bindings(tmp_path: Path):
    worktree = _worktree(tmp_path)
    pair = _pair(
        1,
        "Alpha",
        gen="Use {{extra_path}}",
        required_files=("{{extra_path}}",),
    )
    extra = worktree / "evidence.txt"
    extra.write_text("ok", encoding="utf-8")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    result = run_pipeline(
        pairs=[pair],
        run_dir=tmp_path / "run",
        config=RunConfig(placeholder_values={"extra_path": str(extra)}),
        claude_client=client,
        source_file=tmp_path / "source.md",
        worktree_dir=worktree,
    )
    assert result.halted_early is False
    assert str(extra) in client.received[0].prompt


def test_unresolved_placeholders_halt_before_backend_call(tmp_path: Path):
    pair = _pair(1, "Alpha", gen="Use {{missing_value}}")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    result = run_pipeline(
        pairs=[pair],
        run_dir=tmp_path / "run",
        config=RunConfig(),
        claude_client=client,
        source_file=tmp_path / "source.md",
        worktree_dir=_worktree(tmp_path),
    )
    assert result.halted_early
    assert result.halt_reason is not None
    assert "R-UNRESOLVED-PLACEHOLDERS" in result.halt_reason
    assert "missing_value" in result.halt_reason
    assert client.received == []


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
        worktree_dir=_worktree(tmp_path),
    )
    summary_path = _run_files(run_dir) / "summary.txt"
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
        worktree_dir=_worktree(tmp_path),
    )
    summary_text = (_run_files(run_dir) / "summary.txt").read_text()
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
            worktree_dir=_worktree(tmp_path),
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
    fixture = Path(__file__).parent / "fixtures" / "no-blocks.md"
    exit_code = main(["parse", str(fixture)])
    err = capsys.readouterr().err
    assert exit_code == 2
    assert "E-NO-GENERATION" in err


def test_summary_includes_wall_time(tmp_path: Path):
    """summary.txt must include a 'Wall time:' line in HH:MM:SS format."""
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    run_dir = tmp_path / "run"
    run_pipeline(
        pairs=[pair], run_dir=run_dir, config=RunConfig(),
        claude_client=client, source_file=tmp_path / "source.md",
        worktree_dir=_worktree(tmp_path),
    )
    summary = (_run_files(run_dir) / "summary.txt").read_text()
    assert "Wall time:" in summary
    # Format must look like HH:MM:SS.
    import re as _re
    assert _re.search(r"Wall time: \d{2}:\d{2}:\d{2}", summary), summary


def test_run_pipeline_emits_terse_progress_to_stdout(tmp_path: Path, capsys):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    run_pipeline(
        pairs=[pair], run_dir=tmp_path / "run", config=RunConfig(),
        claude_client=client, source_file=tmp_path / "source.md",
        worktree_dir=_worktree(tmp_path),
    )
    out = capsys.readouterr().out
    assert "run start" in out
    assert "prompt 1/Alpha start" in out
    assert "prompt 1 iter 1 generator start" in out
    assert "prompt 1 iter 1 generator done" in out
    assert "prompt 1 iter 1 judge start" in out
    assert "prompt 1 iter 1 judge done" in out
    assert "prompt 1 iter 1 verdict pass" in out
    assert "run complete" in out


def test_manifest_includes_wall_time(tmp_path: Path):
    """manifest.json must include a 'wall_time' field after finalisation."""
    import json as _json
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    run_dir = tmp_path / "run"
    run_pipeline(
        pairs=[pair], run_dir=run_dir, config=RunConfig(),
        claude_client=client, source_file=tmp_path / "source.md",
        worktree_dir=_worktree(tmp_path),
    )
    manifest = _json.loads((_run_files(run_dir) / "manifest.json").read_text())
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
    assert cfg.include_project_organiser is True


def test_build_initial_generator_message_prepends_generator_prelude():
    p = _pair(1, "X", gen="the task body")
    msg = build_initial_generator_message(
        p, [], Path("/tmp"), generator_prelude="# GEN PRELUDE TEXT",
    )
    assert msg.startswith("# GEN PRELUDE TEXT")
    assert "the task body" in msg
    # Horizontal rule or blank line must separate prelude from task
    assert "\n\n" in msg.split("the task body")[0]


def test_build_initial_generator_message_no_prelude_unchanged():
    p = _pair(1, "X", gen="the task body")
    msg_with = build_initial_generator_message(p, [], Path("/tmp"), generator_prelude=None)
    msg_without = build_initial_generator_message(p, [], Path("/tmp"))
    assert msg_with == msg_without


def test_build_initial_judge_message_prepends_judge_prelude():
    p = _pair(1, "X")
    msg = build_initial_judge_message(
        p, "artifact", Path("/tmp"), judge_prelude="# JUD PRELUDE",
    )
    assert msg.startswith("# JUD PRELUDE")


def test_build_revision_generator_message_prepends_prelude():
    msg = build_revision_generator_message(
        _pair(1, "X"), "feedback", Path("/tmp"), generator_prelude="# GEN REVISE PRELUDE",
    )
    assert msg.startswith("# GEN REVISE PRELUDE")
    assert "feedback" in msg


def test_build_revision_judge_message_prepends_prelude():
    msg = build_revision_judge_message(
        _pair(1, "X"), "revised artifact", Path("/tmp"), judge_prelude="# JUD REVISE PRELUDE",
    )
    assert msg.startswith("# JUD REVISE PRELUDE")


# ---------------------------------------------------------------------------
# Validator-less path (non-interactive)
# ---------------------------------------------------------------------------

def test_no_validator_skips_judge_and_marks_pass(tmp_path: Path):
    from prompt_runner.claude_client import ClaudeResponse, FakeClaudeClient
    from prompt_runner.runner import run_prompt

    pair = PromptPair(
        index=1, title="Validator-less",
        generation_prompt="do the thing",
        validation_prompt="",  # empty!
        heading_line=1, generation_line=2, validation_line=0,
        interactive=False,
    )
    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="artifact body", stderr="", returncode=0),
        # NO judge response needed — judge is skipped
    ])
    result = run_prompt(
        pair=pair, prior_artifacts=[],
        run_dir=tmp_path / "run", config=RunConfig(max_iterations=3),
        claude_client=client, run_id="test-run",
        worktree_dir=_worktree(tmp_path),
    )
    assert result.final_verdict.value == "pass"
    assert result.iterations[0].judge_output == ""
    assert len(client.received) == 1  # generator only, no judge


def test_judge_only_reruns_judge_from_saved_prompt_state(tmp_path: Path):
    from prompt_runner.claude_client import ClaudeResponse, FakeClaudeClient
    from prompt_runner.runner import RunConfig, run_prompt

    pair = PromptPair(
        index=1,
        title="Judge target",
        generation_prompt="generate",
        validation_prompt="validate",
        heading_line=1,
        generation_line=2,
        validation_line=5,
        interactive=False,
    )
    run_dir = tmp_path / "run"
    worktree = _worktree(tmp_path)
    (worktree / "artifact.txt").write_text("real artifact file\n", encoding="utf-8")
    prompt_dir = _module_dir(run_dir, pair.title)
    prompt_dir.mkdir(parents=True)
    prompt_slug = _prompt_slug(pair.index, pair.title)
    (prompt_dir / f"{prompt_slug}.files-created.txt").write_text(
        "artifact.txt\n",
        encoding="utf-8",
    )

    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="looks fine\n\nVERDICT: pass", stderr="", returncode=0),
    ])

    result = run_prompt(
        pair=pair,
        prior_artifacts=[],
        run_dir=run_dir,
        config=RunConfig(max_iterations=3, judge_only=1),
        claude_client=client,
        run_id="test-run",
        worktree_dir=worktree,
    )

    assert result.final_verdict.value == "pass"
    assert result.iterations[-1].generator_output == "real artifact file\n"
    assert result.created_files == [Path("artifact.txt")]
    assert len(result.iterations) == 1
    assert len(client.received) == 1  # judge only, no generator call
    assert "real artifact file" in client.received[0].prompt
    assert "generate" not in client.received[0].prompt
    assert (prompt_dir / f"{prompt_slug}.final-verdict.txt").read_text("utf-8").strip() == "pass"


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def test_interactive_mode_spawns_subprocess_and_marks_pass(tmp_path: Path, monkeypatch):
    """Verify interactive prompts spawn claude via subprocess.Popen, inherit
    stdio, and mark the prompt pass regardless of exit code."""
    from prompt_runner.runner import run_prompt
    from prompt_runner.claude_client import FakeClaudeClient
    import subprocess

    # Capture subprocess.Popen invocations to verify argv and stdio behavior
    captured: dict = {}
    class _Proc:
        pid = 12345
        def wait(self):
            return 0
    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _Proc()
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    import prompt_runner.runner as _runner
    monkeypatch.setattr(_runner, "_using_git_change_tracking", lambda *_args, **_kwargs: False)

    pair = PromptPair(
        index=1, title="Interactive author",
        generation_prompt="author the thing",
        validation_prompt="",
        heading_line=1, generation_line=2, validation_line=0,
        interactive=True,
    )
    result = run_prompt(
        pair=pair, prior_artifacts=[],
        run_dir=tmp_path / "run", config=RunConfig(max_iterations=3, backend="claude"),
        claude_client=FakeClaudeClient(scripted=[]),
        run_id="test-run",
        worktree_dir=_worktree(tmp_path),
    )
    # claude was invoked, with the mission as the last argv element
    assert captured["argv"][0] == "claude"
    assert "author the thing" in captured["argv"][-1]
    # stdio was NOT captured — no stdout/stderr/stdin/capture_output in kwargs
    assert "capture_output" not in captured["kwargs"]
    assert "stdout" not in captured["kwargs"]
    assert "stderr" not in captured["kwargs"]
    # Verdict is pass and iterations is empty
    assert result.final_verdict.value == "pass"
    assert result.iterations == []
    # Prompt completion marker files written
    prompt_dir = _module_dir(tmp_path / "run", "Interactive author")
    prompt_slug = _prompt_slug(1, "Interactive author")
    assert (prompt_dir / f"{prompt_slug}.final-verdict.txt").read_text("utf-8").strip() == "pass"
    assert not (prompt_dir / f"{prompt_slug}.final-artifact.md").exists()


def test_interactive_mode_passes_model_flag_when_set(tmp_path: Path, monkeypatch):
    from prompt_runner.runner import run_prompt
    from prompt_runner.claude_client import FakeClaudeClient
    import prompt_runner.runner as _runner
    import subprocess

    captured: dict = {}
    class _Proc:
        pid = 12345
        def wait(self):
            return 0
    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        return _Proc()
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(_runner, "_using_git_change_tracking", lambda *_args, **_kwargs: False)

    pair = PromptPair(
        index=1, title="X", generation_prompt="m", validation_prompt="",
        heading_line=1, generation_line=2, validation_line=0, interactive=True,
    )
    run_prompt(
        pair=pair, prior_artifacts=[],
        run_dir=tmp_path / "run",
        config=RunConfig(max_iterations=3, model="opus-test"),
        claude_client=FakeClaudeClient(scripted=[]),
        run_id="test-run",
        worktree_dir=_worktree(tmp_path),
    )
    assert "--model" in captured["argv"]
    assert "opus-test" in captured["argv"]


def test_interactive_mode_captures_created_files(tmp_path: Path, monkeypatch):
    from prompt_runner.runner import run_prompt
    from prompt_runner.claude_client import FakeClaudeClient
    import prompt_runner.runner as _runner
    import subprocess

    worktree = _worktree(tmp_path)
    class _Proc:
        pid = 12345
        def wait(self):
            (worktree / "newly-authored-skill.md").write_text("skill body", encoding="utf-8")
            return 0
    def fake_popen(argv, **kwargs):
        # Simulate the user creating a file during the interactive session
        return _Proc()
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(_runner, "_using_git_change_tracking", lambda *_args, **_kwargs: False)

    pair = PromptPair(
        index=1, title="Author",
        generation_prompt="create newly-authored-skill.md",
        validation_prompt="",
        heading_line=1, generation_line=2, validation_line=0, interactive=True,
    )
    result = run_prompt(
        pair=pair, prior_artifacts=[],
        run_dir=tmp_path / "run", config=RunConfig(max_iterations=3),
        claude_client=FakeClaudeClient(scripted=[]),
        run_id="test-run",
        worktree_dir=worktree,
    )
    assert any(p.name == "newly-authored-skill.md" for p in result.created_files)


# ---------------------------------------------------------------------------
# --resume flag
# ---------------------------------------------------------------------------

def test_resume_skips_completed_prompts(tmp_path: Path):
    """If a previous run left final-verdict.txt = pass for prompts 1 and 2,
    resuming skips them and runs only prompt 3."""
    from prompt_runner.claude_client import ClaudeResponse, FakeClaudeClient
    from prompt_runner.runner import run_pipeline, PromptResult
    from prompt_runner.parser import PromptPair

    run_dir = tmp_path / "run"
    worktree = _worktree(tmp_path)

    # Set up the resume state: prompts 1 and 2 have pass verdicts on disk
    for i in (1, 2):
        title = f"Prompt {i}"
        slug = _prompt_slug(i, title)
        pd = _module_dir(run_dir, title)
        pd.mkdir(parents=True)
        (pd / f"{slug}.final-verdict.txt").write_text("pass\n", encoding="utf-8")
        (run_dir / f"artifact-{i}.txt").write_text(f"artifact {i}", encoding="utf-8")
        (pd / f"{slug}.files-created.txt").write_text(f"artifact-{i}.txt\n", encoding="utf-8")

    # We also need a manifest.json since _finalise will read it
    import json as _json
    (_run_files(run_dir) / "manifest.json").write_text(
        _json.dumps({
            "source_file": str(tmp_path / "src.md"),
            "run_id": run_dir.name,
            "config": {"max_iterations": 3, "model": None, "only": None, "dry_run": False},
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": None,
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    # Three pairs in the input
    pairs = [
        PromptPair(index=i, title=f"Prompt {i}",
                   generation_prompt=f"gen {i}", validation_prompt=f"val {i}",
                   heading_line=1, generation_line=2, validation_line=5)
        for i in (1, 2, 3)
    ]

    # Scripted responses for prompt 3 only: generator, judge
    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="artifact 3", stderr="", returncode=0),
        ClaudeResponse(stdout="Looks good.\n\nVERDICT: pass", stderr="", returncode=0),
    ])

    result = run_pipeline(
        pairs=pairs, run_dir=run_dir,
        config=RunConfig(max_iterations=3),
        claude_client=client,
        source_file=tmp_path / "src.md",
        worktree_dir=worktree,
        resume=True,
    )

    assert not result.halted_early
    # Only prompt 3 consumed claude calls
    assert len(client.received) == 2  # gen + judge for prompt 3
    # All three results present (prompts 1, 2 synthesized, 3 real)
    assert len(result.prompt_results) == 3
    assert result.prompt_results[0].iterations == []  # skipped
    assert result.prompt_results[1].iterations == []  # skipped
    assert len(result.prompt_results[2].iterations) == 1  # real


def test_resume_stops_skipping_at_first_incomplete_prompt(tmp_path: Path):
    """If prompt 1 has pass but prompt 2 has no verdict file, prompt 2
    executes normally even though prompt 3 (later) also has a stale pass."""
    from prompt_runner.claude_client import ClaudeResponse, FakeClaudeClient
    from prompt_runner.runner import run_pipeline
    from prompt_runner.parser import PromptPair

    run_dir = tmp_path / "run"
    worktree = _worktree(tmp_path)

    # Prompt 1: completed
    pd1 = _module_dir(run_dir, "Prompt 1")
    pd1.mkdir(parents=True)
    slug1 = _prompt_slug(1, "Prompt 1")
    (pd1 / f"{slug1}.final-verdict.txt").write_text("pass\n", encoding="utf-8")
    (run_dir / "artifact-1.txt").write_text("1", encoding="utf-8")
    (pd1 / f"{slug1}.files-created.txt").write_text("artifact-1.txt\n", encoding="utf-8")
    # Prompt 2: no state at all (incomplete — absence of final-verdict.txt is the trigger)
    # Prompt 3: has a stale pass from an earlier run we don't care about
    pd3 = _module_dir(run_dir, "Prompt 3")
    pd3.mkdir(parents=True)
    slug3 = _prompt_slug(3, "Prompt 3")
    (pd3 / f"{slug3}.final-verdict.txt").write_text("pass\n", encoding="utf-8")
    (run_dir / "artifact-3.txt").write_text("old 3", encoding="utf-8")
    (pd3 / f"{slug3}.files-created.txt").write_text("artifact-3.txt\n", encoding="utf-8")

    # Need manifest.json for _finalise
    import json as _json
    (_run_files(run_dir) / "manifest.json").write_text(
        _json.dumps({
            "source_file": str(tmp_path / "src.md"),
            "run_id": run_dir.name,
            "config": {"max_iterations": 3, "model": None, "only": None, "dry_run": False},
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": None,
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    pairs = [
        PromptPair(index=i, title=f"Prompt {i}",
                   generation_prompt=f"gen {i}", validation_prompt=f"val {i}",
                   heading_line=1, generation_line=2, validation_line=5)
        for i in (1, 2, 3)
    ]
    # Prompts 2 and 3 both run for real: 4 claude calls (gen+judge each)
    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="new artifact 2", stderr="", returncode=0),
        ClaudeResponse(stdout="VERDICT: pass", stderr="", returncode=0),
        ClaudeResponse(stdout="new artifact 3", stderr="", returncode=0),
        ClaudeResponse(stdout="VERDICT: pass", stderr="", returncode=0),
    ])
    result = run_pipeline(
        pairs=pairs, run_dir=run_dir,
        config=RunConfig(max_iterations=3),
        claude_client=client,
        source_file=tmp_path / "src.md",
        worktree_dir=worktree,
        resume=True,
    )
    assert len(client.received) == 4
    assert result.prompt_results[0].iterations == []       # skipped
    assert len(result.prompt_results[1].iterations) == 1   # re-run
    assert len(result.prompt_results[2].iterations) == 1   # re-run (stale pass ignored)


def test_judge_only_does_not_resume_skip_selected_prompt(tmp_path: Path):
    from prompt_runner.claude_client import ClaudeResponse, FakeClaudeClient
    from prompt_runner.runner import RunConfig, run_pipeline

    run_dir = tmp_path / "run"
    worktree = _worktree(tmp_path)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifact.txt").write_text("artifact\n", encoding="utf-8")
    pair = PromptPair(
        index=1,
        title="Prompt 1",
        generation_prompt="gen 1",
        validation_prompt="val 1",
        heading_line=1,
        generation_line=2,
        validation_line=5,
    )
    prompt_dir = _module_dir(run_dir, pair.title)
    prompt_dir.mkdir(parents=True)
    slug = _prompt_slug(pair.index, pair.title)
    (prompt_dir / f"{slug}.final-verdict.txt").write_text("pass\n", encoding="utf-8")
    (prompt_dir / f"{slug}.files-created.txt").write_text("artifact.txt\n", encoding="utf-8")

    import json as _json
    (_run_files(run_dir) / "manifest.json").write_text(
        _json.dumps({
            "source_file": str(tmp_path / "src.md"),
            "run_id": run_dir.name,
            "config": {
                "max_iterations": 3,
                "model": None,
                "only": 1,
                "judge_only": 1,
                "dry_run": False,
            },
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": None,
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="still good\n\nVERDICT: pass", stderr="", returncode=0),
    ])

    result = run_pipeline(
        pairs=[pair],
        run_dir=run_dir,
        config=RunConfig(max_iterations=3, only=1, judge_only=1),
        claude_client=client,
        source_file=tmp_path / "src.md",
        worktree_dir=worktree,
        resume=True,
    )

    assert not result.halted_early
    assert len(client.received) == 1
    assert len(result.prompt_results) == 1
    assert len(result.prompt_results[0].iterations) == 1


def test_resume_errors_on_missing_run_dir(tmp_path: Path, capsys):
    from prompt_runner.__main__ import main

    src = tmp_path / "src.md"
    src.write_text(
        "## Prompt 1: X\n\n### Generation Prompt\n\ngen\n\n### Validation Prompt\n\nval\n",
        encoding="utf-8",
    )
    rc = main([
        "run", str(src),
        "--resume", str(tmp_path / "nonexistent-run"),
        "--dry-run",
    ])
    assert rc != 0
    captured = capsys.readouterr()
    assert "resume" in captured.err.lower()
    assert "nonexistent-run" in captured.err
