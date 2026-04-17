"""Tests for methodology-runner prompt-module execution path."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from methodology_runner.orchestrator import (
    PipelineConfig,
    _invoke_prompt_runner_library,
)
from methodology_runner.phases import get_phase


def test_all_phases_have_checked_in_prompt_modules() -> None:
    for phase_id in (
        "PH-000-requirements-inventory",
        "PH-001-feature-specification",
        "PH-002-architecture",
        "PH-003-solution-design",
        "PH-004-interface-contracts",
        "PH-005-intelligent-simulations",
        "PH-006-incremental-implementation",
        "PH-007-verification-sweep",
    ):
        phase = get_phase(phase_id)
        assert phase.prompt_module_path is not None
        assert Path(phase.prompt_module_path).exists()


def test_invoke_prompt_runner_uses_prompt_module_as_source_and_workspace_as_project(
    tmp_path: Path,
    monkeypatch,
) -> None:
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text(
        "## Prompt 1: X\n\n"
        "### Generation Prompt\n\n"
        "gen\n\n"
        "### Validation Prompt\n\n"
        "val\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_dir = tmp_path / "run"
    config = PipelineConfig(
        requirements_path=tmp_path / "req.md",
        workspace_dir=workspace,
        backend="codex",
    )
    captured: dict[str, object] = {}

    def fake_run_pipeline(*, pairs, run_dir, config, claude_client, source_file, source_project_dir, resume=False, worktree_dir=None):
        captured["pairs"] = pairs
        captured["run_dir"] = run_dir
        captured["config"] = config
        captured["source_file"] = source_file
        captured["source_project_dir"] = source_project_dir
        captured["resume"] = resume
        captured["worktree_dir"] = worktree_dir
        return SimpleNamespace(
            prompt_results=[],
            halted_early=False,
            halt_reason=None,
        )

    monkeypatch.setattr("prompt_runner.runner.run_pipeline", fake_run_pipeline)

    ok, iterations, error = _invoke_prompt_runner_library(
        prompt_file,
        workspace,
        run_dir,
        config,
        claude_client=object(),
        placeholder_values={"raw_requirements_path": "docs/requirements/raw-requirements.md"},
    )

    assert ok is True
    assert iterations == 0
    assert error is None
    assert captured["source_file"] == prompt_file
    assert captured["source_project_dir"] == workspace
    assert captured["worktree_dir"] is None
    run_config = captured["config"]
    assert run_config.placeholder_values == {
        "raw_requirements_path": "docs/requirements/raw-requirements.md",
    }
