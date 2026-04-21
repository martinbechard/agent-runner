"""Tests for fork-point variant execution."""
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from prompt_runner.parser import ForkPoint, PromptPair, VariantPrompt, parse_text
from prompt_runner.runner import (
    RUN_FILES_DIRNAME,
    RunConfig,
    run_pipeline,
    _serialize_pairs_to_md,
)
from prompt_runner.claude_client import ClaudeResponse, FakeClaudeClient


@pytest.fixture(autouse=True)
def _mock_subprocess_popen(monkeypatch):
    """Prevent fork tests from spawning real prompt-runner subprocesses
    that would invoke the Claude API. Each Popen call returns a mock
    process with returncode=0."""
    def fake_popen(cmd, **kwargs):
        proc = MagicMock()
        proc.pid = 12345
        proc.returncode = 0
        proc.wait.return_value = 0
        proc.communicate.return_value = (b"", b"")
        proc.stdout = b""
        proc.stderr = b""
        # Write a minimal summary.txt so the runner can read it
        for i, arg in enumerate(cmd):
            if arg == "--run-dir" and i + 1 < len(cmd):
                run_dir = Path(cmd[i + 1])
                run_dir.mkdir(parents=True, exist_ok=True)
                _run_files(run_dir).mkdir(parents=True, exist_ok=True)
                (_run_files(run_dir) / "summary.txt").write_text(
                    "Prompt Runner — Run Summary\nStatus: completed\n"
                )
                break
        return proc
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    import prompt_runner.runner as _runner
    monkeypatch.setattr(_runner, "_git_is_worktree", lambda *_args, **_kwargs: False)


def _worktree(tmp_path: Path) -> Path:
    w = tmp_path / "worktree"
    w.mkdir(exist_ok=True)
    return w


def _run_files(run_dir: Path) -> Path:
    return run_dir / RUN_FILES_DIRNAME


def _variant_run_dir(run_root: Path, fork_index: int, variant_name: str) -> Path:
    return run_root / f".variant-{fork_index:02d}-{variant_name.lower()}"


INPUT_WITH_FORK = """\
## Prompt 1: Setup

### Generation Prompt

gen 1

### Validation Prompt

val 1

## Prompt 2: Audit [VARIANTS]

### Variant A: Approach one

#### Generation Prompt

gen 2a

#### Validation Prompt

val 2a

### Variant B: Approach two

#### Generation Prompt

gen 2b

#### Validation Prompt

val 2b

## Prompt 3: Final

### Generation Prompt

gen 3

### Validation Prompt

val 3
"""


INPUT_WITH_SELECTION = """\
## Prompt 1: Setup

### Generation Prompt

gen 1

### Validation Prompt

val 1

## Prompt 2: Choose UI [VARIANTS] [SELECT]

### Variant A: Bold layout

#### Generation Prompt

gen 2a

#### Validation Prompt

val 2a

### Variant B: Quiet layout

#### Generation Prompt

gen 2b

#### Validation Prompt

val 2b

### Selection Include Files

ui.txt

### Selector Prompt

Select the best UI variant.

## Prompt 3: Finalize

### Generation Prompt

gen 3

### Validation Prompt

val 3
"""


def test_serialize_pairs_to_md():
    pair = PromptPair(
        index=1, title="Test", generation_prompt="gen body",
        validation_prompt="val body", retry_prompt="", heading_line=1,
        generation_line=2, validation_line=5, retry_line=0,
    )
    md = _serialize_pairs_to_md([pair])
    assert "## Prompt 1: Test" in md
    assert "### Generation Prompt" in md
    assert "### Validation Prompt" in md
    assert "gen body" in md
    assert "val body" in md


def test_serialize_pair_without_validator():
    pair = PromptPair(
        index=1, title="No val", generation_prompt="gen",
        validation_prompt="", retry_prompt="", heading_line=1,
        generation_line=2, validation_line=0, retry_line=0,
    )
    md = _serialize_pairs_to_md([pair])
    assert "## Prompt 1: No val" in md
    assert "### Generation Prompt" in md
    assert "gen" in md
    assert "### Validation Prompt" not in md


def test_serialize_multiple_pairs():
    pairs = [
        PromptPair(
            index=1, title="First", generation_prompt="gen1",
            validation_prompt="val1", retry_prompt="", heading_line=1,
            generation_line=2, validation_line=5, retry_line=0,
        ),
        PromptPair(
            index=2, title="Second", generation_prompt="gen2",
            validation_prompt="val2", retry_prompt="", heading_line=8,
            generation_line=9, validation_line=12, retry_line=0,
        ),
    ]
    md = _serialize_pairs_to_md(pairs)
    assert "## Prompt 1: First" in md
    assert "## Prompt 2: Second" in md
    assert "gen1" in md
    assert "gen2" in md
    assert "val1" in md
    assert "val2" in md


def test_parse_text_with_fork_returns_fork_point():
    """parse_text on INPUT_WITH_FORK yields a PromptPair, a ForkPoint, and another PromptPair."""
    items = parse_text(INPUT_WITH_FORK)
    assert len(items) == 3
    assert isinstance(items[0], PromptPair)
    assert isinstance(items[1], ForkPoint)
    assert isinstance(items[2], PromptPair)

    fork: ForkPoint = items[1]  # type: ignore[assignment]
    assert fork.index == 2
    assert fork.title == "Audit"
    assert len(fork.variants) == 2
    assert fork.variants[0].variant_name == "A"
    assert fork.variants[1].variant_name == "B"


def test_fork_point_creates_variant_directories(tmp_path: Path):
    """Verify that a fork point creates per-variant worktree copies
    and run directories."""
    items = parse_text(INPUT_WITH_FORK)
    worktree = _worktree(tmp_path)
    # Write a marker file so we can verify the worktree was copied.
    (worktree / "marker.txt").write_text("original")

    # Prompt 1 needs gen + judge responses.
    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="artifact 1", stderr="", returncode=0),
        ClaudeResponse(stdout="VERDICT: pass", stderr="", returncode=0),
    ])

    result = run_pipeline(
        pairs=items,
        run_dir=tmp_path / "run",
        config=RunConfig(max_iterations=3),
        claude_client=client,
        source_file=tmp_path / "src.md",
        worktree_dir=worktree,
    )

    # One ForkResult should be collected.
    assert len(result.fork_results) == 1
    fr = result.fork_results[0]
    assert fr.fork_index == 2
    assert fr.fork_title == "Audit"

    # Two VariantResults (one per variant, even if subprocess failed).
    assert len(fr.variant_results) == 2
    assert fr.variant_results[0].variant_name == "A"
    assert fr.variant_results[1].variant_name == "B"

    comparison_path = _run_files(tmp_path / "run") / "fork-02-audit.comparison.txt"
    variant_a = _variant_run_dir(tmp_path / "run", 2, "A")
    variant_b = _variant_run_dir(tmp_path / "run", 2, "B")
    assert comparison_path.exists()
    assert (_run_files(tmp_path / "run") / "process.log").exists()
    assert variant_a.exists()
    assert variant_b.exists()

    # Each variant worktree should be a copy of the original (marker.txt present).
    assert (variant_a / "marker.txt").exists()
    assert (variant_b / "marker.txt").exists()

    # Synthetic prompt file should have been written for each variant.
    assert (_run_files(variant_a) / "synthetic-prompt.md").exists()
    assert (_run_files(variant_b) / "synthetic-prompt.md").exists()

    # Comparison report should exist.
    assert (_run_files(variant_a) / "child-process.json").exists()
    assert (_run_files(variant_b) / "child-process.json").exists()
    assert (_run_files(variant_a) / "child.stdout.log").exists()
    assert (_run_files(variant_a) / "child.stderr.log").exists()
    assert (_run_files(variant_b) / "child.stdout.log").exists()
    assert (_run_files(variant_b) / "child.stderr.log").exists()

    # Parent pipeline does not continue past the fork — no extra prompt_results.
    # (Only prompt 1 ran in the parent.)
    assert len(result.prompt_results) == 1
    assert not result.halted_early


def test_fork_subprocess_propagates_backend(tmp_path: Path, monkeypatch):
    import prompt_runner.runner as _runner
    items = parse_text(INPUT_WITH_FORK)
    worktree = _worktree(tmp_path)

    captured_cmds: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        captured_cmds.append(cmd)
        proc = MagicMock()
        proc.pid = 12345
        proc.returncode = 0
        proc.wait.return_value = 0
        proc.communicate.return_value = (b"", b"")
        proc.stdout = b""
        proc.stderr = b""
        for i, arg in enumerate(cmd):
            if arg == "--run-dir" and i + 1 < len(cmd):
                run_dir = Path(cmd[i + 1])
                run_dir.mkdir(parents=True, exist_ok=True)
                _run_files(run_dir).mkdir(parents=True, exist_ok=True)
                (_run_files(run_dir) / "summary.txt").write_text(
                    "Prompt Runner — Run Summary\nStatus: completed\n"
                )
                break
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(_runner, "_git_is_worktree", lambda *_args, **_kwargs: False)

    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="artifact 1", stderr="", returncode=0),
        ClaudeResponse(stdout="VERDICT: pass", stderr="", returncode=0),
    ])

    run_pipeline(
        pairs=items,
        run_dir=tmp_path / "run",
        config=RunConfig(max_iterations=3, backend="codex"),
        claude_client=client,
        source_file=tmp_path / "src.md",
        worktree_dir=worktree,
    )

    assert captured_cmds, "expected fork subprocesses to be spawned"
    assert all("--backend" in cmd for cmd in captured_cmds)
    assert all("codex" in cmd for cmd in captured_cmds)
    assert all("--run-dir" in cmd for cmd in captured_cmds)
    for cmd in captured_cmds:
        run_dir = Path(cmd[cmd.index("--run-dir") + 1])
        assert run_dir.name.startswith(".variant-")


def test_fork_synthetic_prompt_contains_variant_and_tail(tmp_path: Path):
    """The synthetic prompt for each variant includes that variant's pairs and
    the items that come after the fork in the original file."""
    items = parse_text(INPUT_WITH_FORK)
    worktree = _worktree(tmp_path)

    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="artifact 1", stderr="", returncode=0),
        ClaudeResponse(stdout="VERDICT: pass", stderr="", returncode=0),
    ])

    run_pipeline(
        pairs=items,
        run_dir=tmp_path / "run",
        config=RunConfig(max_iterations=3),
        claude_client=client,
        source_file=tmp_path / "src.md",
        worktree_dir=worktree,
    )

    variant_a = _variant_run_dir(tmp_path / "run", 2, "A")
    variant_b = _variant_run_dir(tmp_path / "run", 2, "B")
    synthetic_a = (_run_files(variant_a) / "synthetic-prompt.md").read_text()
    synthetic_b = (_run_files(variant_b) / "synthetic-prompt.md").read_text()

    # Variant A's own prompt
    assert "gen 2a" in synthetic_a
    assert "val 2a" in synthetic_a
    # Tail prompt (Prompt 3) is included
    assert "gen 3" in synthetic_a
    assert "val 3" in synthetic_a

    # Variant B's own prompt
    assert "gen 2b" in synthetic_b
    assert "val 2b" in synthetic_b
    # Variant A's prompt should NOT appear in B's synthetic file
    assert "gen 2a" not in synthetic_b
    assert "gen 3" in synthetic_b


def test_fork_point_runs_only_selected_variant(tmp_path: Path):
    items = parse_text(INPUT_WITH_FORK)
    worktree = _worktree(tmp_path)
    (worktree / "marker.txt").write_text("original")

    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="artifact 1", stderr="", returncode=0),
        ClaudeResponse(stdout="VERDICT: pass", stderr="", returncode=0),
    ])

    result = run_pipeline(
        pairs=items,
        run_dir=tmp_path / "run",
        config=RunConfig(max_iterations=3, only=2, variant="B"),
        claude_client=client,
        source_file=tmp_path / "src.md",
        worktree_dir=worktree,
    )

    assert len(result.fork_results) == 1
    fr = result.fork_results[0]
    assert len(fr.variant_results) == 1
    assert fr.variant_results[0].variant_name == "B"

    variant_a = _variant_run_dir(tmp_path / "run", 2, "A")
    variant_b = _variant_run_dir(tmp_path / "run", 2, "B")
    assert not variant_a.exists()
    assert variant_b.exists()


def test_selection_fork_promotes_selected_variant_and_continues(tmp_path: Path, monkeypatch):
    import prompt_runner.runner as _runner

    items = parse_text(INPUT_WITH_SELECTION)
    worktree = _worktree(tmp_path)
    (worktree / "marker.txt").write_text("original")
    (worktree / "ui.txt").write_text("baseline\n")

    def fake_popen(cmd, **kwargs):
        proc = MagicMock()
        proc.pid = 12345
        proc.returncode = 0
        proc.wait.return_value = 0
        proc.communicate.return_value = ("", "")
        proc.stdout = []
        proc.stderr = []
        for i, arg in enumerate(cmd):
            if arg == "--run-dir" and i + 1 < len(cmd):
                run_dir = Path(cmd[i + 1])
                run_dir.mkdir(parents=True, exist_ok=True)
                _run_files(run_dir).mkdir(parents=True, exist_ok=True)
                synthetic = (_run_files(run_dir) / "synthetic-prompt.md").read_text(encoding="utf-8")
                if "gen 2a" in synthetic:
                    variant_name = "A"
                    ui_body = "Variant A\n"
                else:
                    variant_name = "B"
                    ui_body = "Variant B\n"
                (run_dir / "ui.txt").write_text(ui_body, encoding="utf-8")
                (_run_files(run_dir) / "summary.txt").write_text(
                    f"Prompt Runner — Run Summary\nStatus: completed\nVariant: {variant_name}\n",
                    encoding="utf-8",
                )
                (_run_files(run_dir) / "manifest.json").write_text(
                    json.dumps({"halt_reason": None}),
                    encoding="utf-8",
                )
                break
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(_runner, "_git_is_worktree", lambda *_args, **_kwargs: False)

    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="artifact 1", stderr="", returncode=0),
        ClaudeResponse(stdout="VERDICT: pass", stderr="", returncode=0),
        ClaudeResponse(
            stdout="VERDICT: select\nSELECTED_VARIANT: B\nRATIONALE: Stronger composition.\n",
            stderr="",
            returncode=0,
        ),
        ClaudeResponse(stdout="artifact 3", stderr="", returncode=0),
        ClaudeResponse(stdout="VERDICT: pass", stderr="", returncode=0),
    ])

    result = run_pipeline(
        pairs=items,
        run_dir=tmp_path / "run",
        config=RunConfig(max_iterations=3),
        claude_client=client,
        source_file=tmp_path / "src.md",
        worktree_dir=worktree,
    )

    assert not result.halted_early
    assert len(result.prompt_results) == 2
    assert [r.pair.index for r in result.prompt_results] == [1, 3]
    assert len(result.fork_results) == 1
    assert result.fork_results[0].selected_variant == "B"
    assert (worktree / "ui.txt").read_text(encoding="utf-8") == "Variant B\n"

    selection_dir = (
        _run_files(tmp_path / "run") / "setup" / "prompt-02.selection"
    )
    assert (selection_dir / "selector" / "decision.json").exists()
    selector_prompt = (selection_dir / "selector" / "selector-prompt.md").read_text(
        encoding="utf-8"
    )
    assert "use exactly one of these canonical variant keys" in selector_prompt
    assert "- A" in selector_prompt
    assert "- B" in selector_prompt
    assert "gen 3" not in (
        selection_dir / "variants" / "a" / "workspace" / ".run-files" / "synthetic-prompt.md"
    ).read_text(encoding="utf-8")
    assert "gen 3" not in (
        selection_dir / "variants" / "b" / "workspace" / ".run-files" / "synthetic-prompt.md"
    ).read_text(encoding="utf-8")
    assert (_run_files(tmp_path / "run") / "setup" / "prompt-02.selected-variant.txt").exists()


def test_model_override_used_in_make_call(tmp_path: Path):
    """When pair has model_override, it's used instead of config.model."""
    from prompt_runner.runner import _make_call

    pair = PromptPair(
        index=1, title="X", generation_prompt="g", validation_prompt="v",
        retry_prompt="", heading_line=1, generation_line=2, validation_line=5,
        retry_line=0,
        model_override="claude-sonnet-4-6",
    )
    call = _make_call(
        prompt="test", session_id="sid", new_session=True,
        model=pair.model_override or "default-model",
        effort=pair.effort_override,
        module_log_path=tmp_path / "module.log", iteration=1, role="generator",
        pair=pair, worktree_dir=tmp_path, run_dir=tmp_path,
    )
    assert call.model == "claude-sonnet-4-6"
    assert call.effort is None
    assert call.agent_name == "prompt-runner-generator"


def test_effort_override_in_make_call(tmp_path: Path):
    """When pair has effort_override, it's threaded through to ClaudeCall."""
    from prompt_runner.runner import _make_call

    pair = PromptPair(
        index=1, title="X", generation_prompt="g", validation_prompt="v",
        retry_prompt="", heading_line=1, generation_line=2, validation_line=5,
        retry_line=0,
        effort_override="low",
    )
    call = _make_call(
        prompt="test", session_id="sid", new_session=True,
        model=None, effort=pair.effort_override,
        module_log_path=tmp_path / "module.log", iteration=1, role="generator",
        pair=pair, worktree_dir=tmp_path, run_dir=tmp_path,
    )
    assert call.effort == "low"
    assert call.agent_name == "prompt-runner-generator"


def test_serialize_preserves_model_and_effort():
    """_serialize_pairs_to_md writes [MODEL:] and [EFFORT:] directives in headings."""
    pair = PromptPair(
        index=1, title="Test", generation_prompt="gen",
        validation_prompt="val", retry_prompt="", heading_line=1,
        generation_line=2, validation_line=5, retry_line=0,
        model_override="claude-sonnet-4-6",
        effort_override="medium",
    )
    md = _serialize_pairs_to_md([pair])
    assert "[MODEL:claude-sonnet-4-6]" in md
    assert "[EFFORT:medium]" in md


def test_serialize_omits_directives_when_not_set():
    """_serialize_pairs_to_md does not add directive text when fields are None."""
    pair = PromptPair(
        index=1, title="Plain", generation_prompt="gen",
        validation_prompt="val", retry_prompt="", heading_line=1,
        generation_line=2, validation_line=5, retry_line=0,
    )
    md = _serialize_pairs_to_md([pair])
    assert "[MODEL:" not in md
    assert "[EFFORT:" not in md


def test_variant_sequential_flag_accepted(tmp_path: Path):
    """RunConfig.variant_sequential is accepted and stored."""
    cfg = RunConfig(variant_sequential=True)
    assert cfg.variant_sequential is True

    cfg2 = RunConfig()
    assert cfg2.variant_sequential is False


def test_variant_sequential_does_not_preconsume_child_pipes(tmp_path: Path, monkeypatch):
    import prompt_runner.runner as _runner

    items = parse_text(INPUT_WITH_FORK)
    worktree = _worktree(tmp_path)
    communicate_calls = 0

    def fake_popen(cmd, **kwargs):
        nonlocal communicate_calls
        proc = MagicMock()
        proc.pid = 12345
        proc.returncode = 0
        proc.wait.return_value = 0

        def fake_communicate():
            nonlocal communicate_calls
            communicate_calls += 1
            return ("", "")

        proc.communicate.side_effect = fake_communicate
        proc.stdout = []
        proc.stderr = []
        for i, arg in enumerate(cmd):
            if arg == "--run-dir" and i + 1 < len(cmd):
                run_dir = Path(cmd[i + 1])
                run_dir.mkdir(parents=True, exist_ok=True)
                _run_files(run_dir).mkdir(parents=True, exist_ok=True)
                (_run_files(run_dir) / "summary.txt").write_text(
                    "Prompt Runner — Run Summary\nStatus: completed\n"
                )
                (_run_files(run_dir) / "manifest.json").write_text(
                    json.dumps({"halt_reason": None})
                )
                break
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(_runner, "_git_is_worktree", lambda *_args, **_kwargs: False)

    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="artifact 1", stderr="", returncode=0),
        ClaudeResponse(stdout="VERDICT: pass", stderr="", returncode=0),
    ])

    run_pipeline(
        pairs=items,
        run_dir=tmp_path / "run",
        config=RunConfig(max_iterations=3, variant_sequential=True),
        claude_client=client,
        source_file=tmp_path / "src.md",
        worktree_dir=worktree,
    )

    assert communicate_calls == 0


def test_comparison_report_contains_variant_names(tmp_path: Path):
    """The comparison.txt should list each variant's name and exit code."""
    items = parse_text(INPUT_WITH_FORK)
    worktree = _worktree(tmp_path)
    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="artifact 1", stderr="", returncode=0),
        ClaudeResponse(stdout="VERDICT: pass", stderr="", returncode=0),
    ])
    run_pipeline(
        pairs=items,
        run_dir=tmp_path / "run",
        config=RunConfig(max_iterations=3),
        claude_client=client,
        source_file=tmp_path / "src.md",
        worktree_dir=worktree,
    )
    comparison = (_run_files(tmp_path / "run") / "fork-02-audit.comparison.txt").read_text()
    assert "Variant A" in comparison or "variant-a" in comparison.lower()
    assert "Variant B" in comparison or "variant-b" in comparison.lower()
    # Exit codes should be mentioned
    assert "0" in comparison  # both variants exit 0 in mock


def test_run_pipeline_no_fork_unaffected(tmp_path: Path):
    """A pipeline without fork points behaves identically to before."""
    pair1 = PromptPair(
        index=1, title="Only", generation_prompt="do it",
        validation_prompt="check it", retry_prompt="", heading_line=1,
        generation_line=2, validation_line=5, retry_line=0,
    )
    worktree = _worktree(tmp_path)
    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="done", stderr="", returncode=0),
        ClaudeResponse(stdout="VERDICT: pass", stderr="", returncode=0),
    ])
    result = run_pipeline(
        pairs=[pair1],
        run_dir=tmp_path / "run",
        config=RunConfig(),
        claude_client=client,
        source_file=tmp_path / "src.md",
        worktree_dir=worktree,
    )
    assert not result.halted_early
    assert len(result.prompt_results) == 1
    assert len(result.fork_results) == 0
