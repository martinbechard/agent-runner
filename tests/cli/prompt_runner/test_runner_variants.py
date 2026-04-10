"""Tests for fork-point variant execution."""
from pathlib import Path

import pytest

from prompt_runner.parser import ForkPoint, PromptPair, VariantPrompt, parse_text
from prompt_runner.runner import (
    RunConfig,
    run_pipeline,
    _serialize_pairs_to_md,
)
from prompt_runner.claude_client import ClaudeResponse, FakeClaudeClient


def _workspace(tmp_path: Path) -> Path:
    w = tmp_path / "workspace"
    w.mkdir(exist_ok=True)
    return w


INPUT_WITH_FORK = """\
## Prompt 1: Setup

```
gen 1
```

```
val 1
```

## Prompt 2: Audit [VARIANTS]

### Variant A: Approach one

```
gen 2a
```

```
val 2a
```

### Variant B: Approach two

```
gen 2b
```

```
val 2b
```

## Prompt 3: Final

```
gen 3
```

```
val 3
```
"""


def test_serialize_pairs_to_md():
    pair = PromptPair(
        index=1, title="Test", generation_prompt="gen body",
        validation_prompt="val body", heading_line=1,
        generation_line=2, validation_line=5,
    )
    md = _serialize_pairs_to_md([pair])
    assert "## Prompt 1: Test" in md
    assert "gen body" in md
    assert "val body" in md


def test_serialize_pair_without_validator():
    pair = PromptPair(
        index=1, title="No val", generation_prompt="gen",
        validation_prompt="", heading_line=1,
        generation_line=2, validation_line=0,
    )
    md = _serialize_pairs_to_md([pair])
    assert "## Prompt 1: No val" in md
    assert "gen" in md
    # Should have only one code fence pair (open + close)
    assert md.count("```") == 2


def test_serialize_multiple_pairs():
    pairs = [
        PromptPair(
            index=1, title="First", generation_prompt="gen1",
            validation_prompt="val1", heading_line=1,
            generation_line=2, validation_line=5,
        ),
        PromptPair(
            index=2, title="Second", generation_prompt="gen2",
            validation_prompt="val2", heading_line=8,
            generation_line=9, validation_line=12,
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
    """Verify that a fork point creates per-variant workspace copies
    and run directories."""
    items = parse_text(INPUT_WITH_FORK)
    workspace = _workspace(tmp_path)
    # Write a marker file so we can verify the workspace was copied.
    (workspace / "marker.txt").write_text("original")

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
        workspace_dir=workspace,
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

    # Variant directories must have been created.
    fork_dir = tmp_path / "run" / "fork-02-audit"
    assert fork_dir.exists()
    assert (fork_dir / "variant-a").exists()
    assert (fork_dir / "variant-b").exists()

    # Each variant workspace should be a copy of the original (marker.txt present).
    assert (fork_dir / "variant-a" / "workspace" / "marker.txt").exists()
    assert (fork_dir / "variant-b" / "workspace" / "marker.txt").exists()

    # Synthetic prompt file should have been written for each variant.
    assert (fork_dir / "variant-a" / "synthetic-prompt.md").exists()
    assert (fork_dir / "variant-b" / "synthetic-prompt.md").exists()

    # Comparison report should exist.
    assert (fork_dir / "comparison.txt").exists()

    # Parent pipeline does not continue past the fork — no extra prompt_results.
    # (Only prompt 1 ran in the parent.)
    assert len(result.prompt_results) == 1
    assert not result.halted_early


def test_fork_synthetic_prompt_contains_variant_and_tail(tmp_path: Path):
    """The synthetic prompt for each variant includes that variant's pairs and
    the items that come after the fork in the original file."""
    items = parse_text(INPUT_WITH_FORK)
    workspace = _workspace(tmp_path)

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
        workspace_dir=workspace,
    )

    fork_dir = tmp_path / "run" / "fork-02-audit"
    synthetic_a = (fork_dir / "variant-a" / "synthetic-prompt.md").read_text()
    synthetic_b = (fork_dir / "variant-b" / "synthetic-prompt.md").read_text()

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


def test_variant_sequential_flag_accepted(tmp_path: Path):
    """RunConfig.variant_sequential is accepted and stored."""
    cfg = RunConfig(variant_sequential=True)
    assert cfg.variant_sequential is True

    cfg2 = RunConfig()
    assert cfg2.variant_sequential is False


def test_run_pipeline_no_fork_unaffected(tmp_path: Path):
    """A pipeline without fork points behaves identically to before."""
    pair1 = PromptPair(
        index=1, title="Only", generation_prompt="do it",
        validation_prompt="check it", heading_line=1,
        generation_line=2, validation_line=5,
    )
    workspace = _workspace(tmp_path)
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
        workspace_dir=workspace,
    )
    assert not result.halted_early
    assert len(result.prompt_results) == 1
    assert len(result.fork_results) == 0
