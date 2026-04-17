"""Tests for methodology-runner prompt-module execution path."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from methodology_runner.models import (
    PhaseState,
    PhaseStatus,
    ProjectState,
)
from methodology_runner.orchestrator import (
    PipelineConfig,
    _invoke_prompt_runner_library,
    _run_single_phase,
)
from methodology_runner.phases import PHASES, get_phase


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
    assert captured["worktree_dir"] == workspace
    run_config = captured["config"]
    assert run_config.generator_prelude is None
    assert run_config.judge_prelude is None
    assert run_config.placeholder_values == {
        "raw_requirements_path": "docs/requirements/raw-requirements.md",
    }


def test_cross_ref_retry_preserves_existing_artifact_for_retry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    req = workspace / "docs" / "requirements" / "raw-requirements.md"
    req.parent.mkdir(parents=True, exist_ok=True)
    req.write_text("# Requirements\n", encoding="utf-8")

    state = ProjectState(
        workspace_dir=workspace,
        requirements_path=req,
        phase_results={},
        started_at="2026-04-17T12:00:00Z",
        git_initialized=False,
        model=None,
        phases=[
            PhaseState(
                phase_id=phase.phase_id,
                status=PhaseStatus.PENDING,
                started_at=None,
                completed_at=None,
                prompt_file=None,
                cross_ref_result_path=None,
                cross_ref_retries=0,
                git_commit=None,
            )
            for phase in PHASES
        ],
    )
    config = PipelineConfig(
        requirements_path=req,
        workspace_dir=workspace,
        backend="codex",
        max_cross_ref_retries=1,
    )
    phase = get_phase("PH-000-requirements-inventory")
    artifact_path = workspace / phase.output_artifact_path
    invoke_calls: list[int] = []
    verify_calls: list[int] = []

    def fake_invoke(
        prompt_file,
        workspace_dir,
        run_dir,
        pipeline_config,
        claude_client,
        generator_prelude=None,
        judge_prelude=None,
        placeholder_values=None,
    ):
        if not invoke_calls:
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text("first pass\n", encoding="utf-8")
        else:
            assert generator_prelude is not None
            assert judge_prelude is not None
            assert generator_prelude == judge_prelude
            assert "Cross-reference retry guidance:" in generator_prelude
            assert artifact_path.read_text(encoding="utf-8") == "first pass\n"
            artifact_path.write_text("second pass\n", encoding="utf-8")
        invoke_calls.append(1)
        return True, 1, None

    def fake_verify(**kwargs):
        verify_calls.append(1)
        if len(verify_calls) == 1:
            return SimpleNamespace(
                passed=False,
                issues=["fix this"],
                traceability_gaps=[],
                orphaned_elements=[],
                coverage_summary={},
                to_dict=lambda: {
                    "passed": False,
                    "issues": ["fix this"],
                    "traceability_gaps": [],
                    "orphaned_elements": [],
                    "coverage_summary": {},
                },
            )
        return SimpleNamespace(
            passed=True,
            issues=[],
            traceability_gaps=[],
            orphaned_elements=[],
            coverage_summary={},
            to_dict=lambda: {
                "passed": True,
                "issues": [],
                "traceability_gaps": [],
                "orphaned_elements": [],
                "coverage_summary": {},
            },
        )

    monkeypatch.setattr(
        "methodology_runner.orchestrator._invoke_prompt_runner",
        fake_invoke,
    )
    monkeypatch.setattr(
        "methodology_runner.orchestrator.verify_phase_cross_references",
        fake_verify,
    )
    monkeypatch.setattr(
        "methodology_runner.orchestrator._git_commit",
        lambda workspace, message: "deadbeef",
    )

    result = _run_single_phase(
        phase,
        state,
        workspace,
        config,
        claude_client=object(),
    )

    assert result.status == PhaseStatus.COMPLETED
    assert len(invoke_calls) == 2
    assert artifact_path.read_text(encoding="utf-8") == "second pass\n"
    retry_guidance = (
        workspace
        / ".methodology-runner"
        / "runs"
        / "phase-0"
        / "retry-guidance-1.txt"
    )
    assert retry_guidance.exists()
    assert "fix this" in retry_guidance.read_text(encoding="utf-8")
