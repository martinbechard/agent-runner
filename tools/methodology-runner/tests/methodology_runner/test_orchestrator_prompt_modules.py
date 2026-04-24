"""Tests for methodology-runner prompt-module execution path."""
from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from methodology_runner.models import (
    METHODOLOGY_LIFECYCLE_PHASE_ID,
    PhaseResult,
    PhaseState,
    PhaseStatus,
    ProjectState,
)
from methodology_runner.orchestrator import (
    PipelineConfig,
    PHASE_5_NO_TARGETS_SKIP_REASON,
    _phase_path_mappings,
    _phase_placeholder_values,
    _resolve_bundled_skills_root,
    _resolve_prompt_runner_src_root,
    _resolve_phase_prompt_module_path,
    _invoke_prompt_runner_library,
    _verify_predecessor_artifacts,
    run_pipeline,
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
        assert _resolve_phase_prompt_module_path(phase).exists()


def test_phase_validation_prompts_have_value_and_fidelity_standard() -> None:
    prompt_dir = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "methodology_runner"
        / "prompts"
    )
    for prompt_name in (
        "PR-025-ph000-requirements-inventory.md",
        "PR-023-ph001-feature-specification.md",
        "PR-024-ph002-architecture.md",
        "PR-026-ph003-solution-design.md",
        "PR-027-ph004-interface-contracts.md",
        "PR-028-ph005-intelligent-simulations.md",
        "PR-029-ph006-incremental-implementation.md",
        "PR-030-ph007-verification-sweep.md",
    ):
        text = (prompt_dir / prompt_name).read_text(encoding="utf-8")
        validation_prompt_count = sum(
            1 for line in text.splitlines() if line == "### Validation Prompt"
        )
        assert validation_prompt_count > 0, prompt_name
        assert text.count("Value and fidelity standard:") == validation_prompt_count


def test_phase_prompts_do_not_depend_on_external_agent_assets() -> None:
    tool_root = Path(__file__).resolve().parents[2]
    package_root = tool_root / "src" / "methodology_runner"
    prompt_dir = package_root / "prompts"
    bundled_skill_paths = [
        tool_root / "skills" / "structured-design" / "SKILL.md",
        tool_root / "skills" / "structured-review" / "SKILL.md",
        tool_root / "skills" / "structured-review" / "references" / "generic-structured-document-checklist.md",
    ]

    for skill_path in bundled_skill_paths:
        assert skill_path.exists()

    for prompt_path in (
        prompt_dir / "PR-024-ph002-architecture.md",
        prompt_dir / "PR-026-ph003-solution-design.md",
    ):
        text = prompt_path.read_text(encoding="utf-8")
        assert "agent-assets/skills" not in text
        assert "{{INCLUDE:skills/structured-design/SKILL.md}}" in text
        assert "{{INCLUDE:skills/structured-review/SKILL.md}}" in text


def test_ph002_prompt_module_requires_compact_architecture_schema() -> None:
    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "methodology_runner"
        / "prompts"
        / "PR-024-ph002-architecture.md"
    )
    text = prompt_path.read_text(encoding="utf-8")

    assert "The output schema below is authoritative" in text
    assert "top-level keys exactly `components`, `integration_points`, `rationale`" in text
    assert "component IDs must use `CMP-NNN`" in text
    assert "component feature coverage must be expressed in `features_served`" in text
    assert "every component must declare `simulation_target` and `simulation_boundary`" in text
    assert "each integration point `between` list must name exactly two distinct" in text
    assert "Do not use `MODULE-*`" in text
    assert "structured-design sections such as `system_shape`, `finality`" in text
    assert "as substitutes for `CMP-*`\n  components with `features_served`" in text
    assert "documentation, verification, or test-suite\n  components" in text


def test_ph003_prompt_module_requires_processing_examples_and_ui_mockups() -> None:
    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "methodology_runner"
        / "prompts"
        / "PR-026-ph003-solution-design.md"
    )
    text = prompt_path.read_text(encoding="utf-8")

    assert "processing_functions" in text
    assert "ui_surfaces" in text
    assert "examples" in text
    assert "input" in text
    assert "output" in text
    assert "html_mockup" in text
    assert "HTML fragment" in text


def test_phase_path_mappings_resolve_bundled_skill_root() -> None:
    path_mappings = _phase_path_mappings()
    skills_root = _resolve_bundled_skills_root()

    assert path_mappings["skills/"] == str(skills_root)
    assert (skills_root / "structured-design" / "SKILL.md").exists()
    assert (skills_root / "structured-review" / "SKILL.md").exists()


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
    config = PipelineConfig(
        requirements_path=tmp_path / "req.md",
        workspace_dir=workspace,
        backend="codex",
        debug=4,
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
        "PH-000-requirements-inventory",
        config,
        claude_client=object(),
        placeholder_values={"raw_requirements_path": "docs/requirements/raw-requirements.md"},
    )

    assert ok is True
    assert iterations == 0
    assert error is None
    assert captured["source_file"] == prompt_file
    assert captured["run_dir"] == workspace
    assert captured["source_project_dir"] == workspace
    assert captured["worktree_dir"] == workspace
    run_config = captured["config"]
    assert run_config.debug == 4
    assert run_config.generator_prelude is None
    assert run_config.judge_prelude is None
    assert run_config.placeholder_values == {
        "raw_requirements_path": "docs/requirements/raw-requirements.md",
    }
    assert run_config.path_mappings["skills/"].endswith("/skills")
    assert run_config.run_id_override == "PH-000-requirements-inventory"


def test_phase_placeholder_values_include_ph006_prompt_runner_command() -> None:
    phase = get_phase("PH-006-incremental-implementation")
    config = PipelineConfig(
        requirements_path=Path("req.md"),
        workspace_dir=Path("workspace"),
        backend="codex",
    )
    values = _phase_placeholder_values(phase, config)

    assert "prompt_runner_command" in values
    expected_src = _resolve_prompt_runner_src_root()
    assert values["prompt_runner_command"] == (
        f"PYTHONPATH={shlex.quote(str(expected_src))} "
        f"{shlex.quote(sys.executable)} -m prompt_runner"
    )
    assert values["methodology_backend"] == "codex"


def test_ph006_prompt_module_enforces_exact_tdd_and_report_evidence_contract() -> None:
    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "methodology_runner"
        / "prompts"
        / "PR-029-ph006-incremental-implementation.md"
    )
    text = prompt_path.read_text(encoding="utf-8")

    assert "same exact test command" in text
    assert "--simulations\ndocs/simulations/simulation-definitions.yaml" in text
    assert "failing or tightened-test outcome" not in text
    assert "failing or tightened-test" in text
    assert "## Command Reports" in text
    assert "plain-text command-report block" in text
    assert "### Command Report 1" in text
    assert "stdout_excerpt" in text
    assert "stderr_excerpt" in text
    assert "must not claim a fixed baseline runtime state" in text
    assert "from the current ... behavior" in text
    assert "required literal `T`" in text
    assert "ISO-only formatting" in text
    assert "date-and-time line" in text
    assert "generic timestamp-only output" in text
    assert "non-`None` tzinfo requirement" in text
    assert "Upstream semantic contradiction or unsupported exclusion" in text
    assert "arbitrary non-empty text as sufficient" in text
    assert "date-and-time-bearing value from the same run" in text
    assert "Weak datetime semantic verification" in text
    assert "does not expose a trustworthy stdout/stderr split" in text
    assert "exactly one of `stdout_excerpt` or" in text
    assert "stale halted child snapshot" in text
    assert "resume the child workflow again" in text
    assert "file-level, type-level, and function-level comments" in text
    assert "steady-state software" in text
    assert "typical setup\n  and operation entries" in text
    assert "authoritative handoff for gradual implementation" in text
    assert "simulation artifact paths" in text
    assert "configuration, startup command, import path, service URL" in text


def test_ph005_prompt_module_requires_compile_checked_component_simulations() -> None:
    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "methodology_runner"
        / "prompts"
        / "PR-028-ph005-intelligent-simulations.md"
    )
    text = prompt_path.read_text(encoding="utf-8")

    assert "This phase simulates system components, not test suites." in text
    assert "simulation_target: true" in text
    assert "explicit language interface" in text
    assert "compile_commands" in text
    assert "legacy contract-scenario schema" in text
    assert "documentation, verification, or test-suite" in text
    assert "exactly `simulations: []`" in text
    assert "no interface or implementation files are required" in text
    assert "Every simulation must document how downstream work should use it" in text
    assert "Every simulation must list every created simulation artifact" in text
    assert "phase_6_usage" in text


def test_ph005_skips_prompt_runner_when_architecture_has_no_simulation_targets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    req = workspace / "docs" / "requirements" / "raw-requirements.md"
    req.parent.mkdir(parents=True, exist_ok=True)
    req.write_text("# Requirements\n", encoding="utf-8")
    architecture = workspace / "docs" / "architecture" / "architecture-design.yaml"
    architecture.parent.mkdir(parents=True, exist_ok=True)
    architecture.write_text(
        "components:\n"
        "  - id: CMP-001\n"
        "    name: Single-process clock app\n"
        "    type: application\n"
        "    responsibility: Print greeting and current date-time.\n"
        "    features_served: [FEAT-001]\n"
        "    contracts: []\n"
        "    depends_on: []\n"
        "    simulation_target: false\n"
        "    simulation_boundary: none\n"
        "integration_points: []\n"
        "rationale: No external service boundary needs a simulation.\n",
        encoding="utf-8",
    )
    contracts = workspace / "docs" / "design" / "interface-contracts.yaml"
    contracts.parent.mkdir(parents=True, exist_ok=True)
    contracts.write_text("contracts: []\n", encoding="utf-8")

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
                status=(
                    PhaseStatus.COMPLETED
                    if phase.phase_id == "PH-004-interface-contracts"
                    else PhaseStatus.PENDING
                ),
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
    )
    phase = get_phase("PH-005-intelligent-simulations")

    def fail_if_invoked(*args, **kwargs):
        raise AssertionError("prompt-runner should not run when PH-005 is empty")

    def fail_if_cross_ref_invoked(*args, **kwargs):
        raise AssertionError("cross-reference should not run for skipped PH-005")

    monkeypatch.setattr(
        "methodology_runner.orchestrator._invoke_prompt_runner",
        fail_if_invoked,
    )
    monkeypatch.setattr(
        "methodology_runner.orchestrator.verify_phase_cross_references",
        fail_if_cross_ref_invoked,
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

    artifact = workspace / "docs" / "simulations" / "simulation-definitions.yaml"
    phase_state = next(ps for ps in state.phases if ps.phase_id == phase.phase_id)
    assert result.status == PhaseStatus.SKIPPED
    assert result.iteration_count == 0
    assert result.prompt_runner_success is False
    assert artifact.read_text(encoding="utf-8") == "simulations: []\n"
    assert phase_state.status == PhaseStatus.SKIPPED
    assert phase_state.completed_at is not None
    assert phase_state.git_commit == "deadbeef"
    assert state.phase_results[phase.phase_id] == result
    skip_reason = workspace / ".run-files" / phase.phase_id / "skip-reason.txt"
    assert skip_reason.read_text(encoding="utf-8") == (
        PHASE_5_NO_TARGETS_SKIP_REASON + "\n"
    )
    assert _verify_predecessor_artifacts(
        get_phase("PH-006-incremental-implementation"),
        state,
        workspace,
    ) is None


def test_ph004_prompt_module_requires_non_empty_response_schemas() -> None:
    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "methodology_runner"
        / "prompts"
        / "PR-027-ph004-interface-contracts.md"
    )
    text = prompt_path.read_text(encoding="utf-8")

    assert "response_schema:" in text
    assert "fields: []" not in text
    assert "response_schema.fields must be explicit non-empty" in text


def test_ph007_prompt_module_uses_compatibility_not_overconstraint() -> None:
    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "methodology_runner"
        / "prompts"
        / "PR-030-ph007-verification-sweep.md"
    )
    text = prompt_path.read_text(encoding="utf-8")

    assert "A compatible refinement is" in text
    assert "contradiction or unsupported exclusion is not" in text
    assert "more specific formatting" in text
    assert "Upstream semantic contradiction or unsupported exclusion" in text
    assert "runtime-volatile" in text
    assert "methodology_runner.phase_7_validation" in text
    assert "Volatile-literal overreach" in text
    assert "Methodology self-validation leakage" in text
    assert "Delivery-quality omission" in text
    assert "file-level, type-level,\n  and function-level comments" in text
    assert "setup and operation entries" in text


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
        / ".run-files"
        / "PH-000-requirements-inventory"
        / "retry-guidance-1.txt"
    )
    assert retry_guidance.exists()
    assert "fix this" in retry_guidance.read_text(encoding="utf-8")


def test_run_pipeline_debug_writes_methodology_process_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    req = tmp_path / "req.md"
    req.write_text("# Requirements\n", encoding="utf-8")
    config = PipelineConfig(
        requirements_path=req,
        workspace_dir=workspace,
        backend="codex",
        debug=2,
        phases_to_run=["PH-000-requirements-inventory"],
    )

    def fake_run_single_phase(
        phase,
        state,
        workspace_dir,
        pipeline_config,
        claude_client=None,
        cross_ref_only=False,
    ):
        return SimpleNamespace(
            phase_id=phase.phase_id,
            status=PhaseStatus.COMPLETED,
            prompt_runner_file="prompt.md",
            iteration_count=0,
            wall_time_seconds=0.1,
            prompt_runner_success=True,
            cross_ref_result=None,
            error_message=None,
        )

    monkeypatch.setattr(
        "methodology_runner.orchestrator._run_single_phase",
        fake_run_single_phase,
    )
    monkeypatch.setattr(
        "methodology_runner.orchestrator._git_commit",
        lambda workspace, message: "deadbeef",
    )
    monkeypatch.setattr(
        "methodology_runner.orchestrator.verify_end_to_end",
        lambda **kwargs: SimpleNamespace(
            passed=True,
            issues=[],
            traceability_gaps=[],
            orphaned_elements=[],
            coverage_summary={},
        ),
    )

    result = run_pipeline(config, claude_client=object())
    assert result.halted_early is False
    process_log = workspace / ".methodology-runner" / "process.log"
    text = process_log.read_text(encoding="utf-8")
    assert "[debug-trace] enabled depth=2" in text


def test_selected_phase_run_keeps_lifecycle_inside_lc001_when_full_methodology_is_not_done(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    req = tmp_path / "req.md"
    req.write_text("# Requirements\n", encoding="utf-8")
    config = PipelineConfig(
        requirements_path=req,
        workspace_dir=workspace,
        backend="codex",
        phases_to_run=["PH-000-requirements-inventory"],
    )

    def fake_run_single_phase(
        phase,
        state,
        workspace_dir,
        pipeline_config,
        claude_client=None,
        cross_ref_only=False,
    ):
        phase_state = next(ps for ps in state.phases if ps.phase_id == phase.phase_id)
        phase_state.status = PhaseStatus.COMPLETED
        state.phase_results[phase.phase_id] = PhaseResult(
            phase_id=phase.phase_id,
            status=PhaseStatus.COMPLETED,
            prompt_runner_file="prompt.md",
            iteration_count=1,
            wall_time_seconds=0.1,
            prompt_runner_exit_code=0,
            prompt_runner_success=True,
            cross_ref_result=None,
            error_message=None,
        )
        return state.phase_results[phase.phase_id]

    monkeypatch.setattr(
        "methodology_runner.orchestrator._run_single_phase",
        fake_run_single_phase,
    )
    monkeypatch.setattr(
        "methodology_runner.orchestrator._git_commit",
        lambda workspace, message: "deadbeef",
    )
    monkeypatch.setattr(
        "methodology_runner.orchestrator.verify_end_to_end",
        lambda **kwargs: SimpleNamespace(
            passed=True,
            issues=[],
            traceability_gaps=[],
            orphaned_elements=[],
            coverage_summary={},
        ),
    )

    result = run_pipeline(config, claude_client=object())

    assert result.halted_early is False
    state = ProjectState.load(workspace / ".methodology-runner" / "state.json")
    assert state.current_phase is None
    assert state.finished_at is None
    assert state.current_lifecycle_phase_id == METHODOLOGY_LIFECYCLE_PHASE_ID
    methodology = next(
        phase
        for phase in state.lifecycle_phases
        if phase.phase_id == METHODOLOGY_LIFECYCLE_PHASE_ID
    )
    assert methodology.status == PhaseStatus.IN_PROGRESS


def test_full_run_auto_finalizes_and_merges_into_main(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "hello-clock"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Tester"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "commit", "--allow-empty", "-m", "Initial empty commit"], cwd=repo, check=True)

    worktrees = tmp_path / "worktrees"
    worktrees.mkdir()
    feature_worktree = worktrees / "change-001-hello-world"
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "worktree",
            "add",
            str(feature_worktree),
            "-b",
            "change-001-hello-world",
        ],
        check=True,
    )

    req = tmp_path / "req.md"
    req.write_text("# Requirements\nCreate hello world.\n", encoding="utf-8")
    config = PipelineConfig(
        requirements_path=req,
        workspace_dir=feature_worktree,
        backend="codex",
    )

    def fake_run_single_phase(
        phase,
        state,
        workspace_dir,
        pipeline_config,
        claude_client=None,
        cross_ref_only=False,
    ):
        phase_state = next(ps for ps in state.phases if ps.phase_id == phase.phase_id)
        phase_state.status = PhaseStatus.COMPLETED
        output = workspace_dir / phase.output_artifact_path
        output.parent.mkdir(parents=True, exist_ok=True)

        if phase.phase_id == "PH-000-requirements-inventory":
            output.write_text("items: []\n", encoding="utf-8")
            (workspace_dir / "docs/requirements/requirements-inventory-coverage.yaml").write_text(
                "coverage_verdict:\n  verdict: PASS\n",
                encoding="utf-8",
            )
        elif phase.phase_id == "PH-001-feature-specification":
            output.write_text(
                "features:\n"
                "  - id: \"FT-001\"\n"
                "    name: \"Command-Line Hello World Application\"\n"
                "    description: \"Print Hello, world! from the command line.\"\n"
                "    source_inventory_refs: [\"RI-001\"]\n"
                "    acceptance_criteria:\n"
                "      - id: \"AC-001-01\"\n"
                "        description: \"The command prints Hello, world!.\"\n"
                "    dependencies: []\n"
                "cross_cutting_concerns: []\n"
                "out_of_scope: []\n",
                encoding="utf-8",
            )
        elif phase.phase_id == "PH-002-architecture":
            output.write_text("components: []\ninteractions: []\n", encoding="utf-8")
        elif phase.phase_id == "PH-003-solution-design":
            output.write_text(
                "components:\n"
                "  - id: \"CMP-1\"\n"
                "    name: \"Command-line application\"\n"
                "    responsibility: \"Runs the public hello-world command.\"\n"
                "    technology: \"Python 3\"\n"
                "    feature_realization_map:\n"
                "      FT-001: \"Implements the command-line behavior.\"\n"
                "    dependencies: []\n"
                "    processing_functions:\n"
                "      - name: \"main\"\n"
                "        purpose: \"Runs the CLI entrypoint.\"\n"
                "        triggered_by_features: [\"FT-001\"]\n"
                "        examples:\n"
                "          - name: \"default run\"\n"
                "            input: {}\n"
                "            output:\n"
                "              stdout: \"Hello, world!\\n\"\n"
                "    ui_surfaces: []\n"
                "interactions: []\n",
                encoding="utf-8",
            )
        elif phase.phase_id == "PH-004-interface-contracts":
            output.write_text(
                "contracts:\n"
                "  - id: \"CTR-001\"\n"
                "    name: \"Public Entry Contract\"\n"
                "    interaction_ref: \"INT-001\"\n"
                "    source_component: \"CMP-3\"\n"
                "    target_component: \"CMP-1\"\n"
                "    operations:\n"
                "      - name: \"execute_public_entry_path\"\n"
                "        description: \"Run the command-line application.\"\n"
                "        request_schema:\n"
                "          fields:\n"
                "            - name: \"entry_command\"\n"
                "              type: \"string\"\n"
                "              required: true\n"
                "              constraints: \"Must be python3 hello_world.py\"\n"
                "        response_schema:\n"
                "          fields:\n"
                "            - name: \"stdout_text\"\n"
                "              type: \"string\"\n"
                "              required: true\n"
                "              constraints: \"Must equal Hello, world!\\\\n\"\n"
                "        error_types: []\n"
                "    behavioral_specs:\n"
                "      - precondition: \"A caller invokes the public command.\"\n"
                "        postcondition: \"The exact stdout is observed.\"\n"
                "        invariant: \"The command stays framework-free.\"\n",
                encoding="utf-8",
            )
        elif phase.phase_id == "PH-005-intelligent-simulations":
            output.write_text("simulations: []\n", encoding="utf-8")
        elif phase.phase_id == "PH-006-incremental-implementation":
            output.write_text("### Module\nimplementation-workflow\n", encoding="utf-8")
            (workspace_dir / "docs/implementation/implementation-run-report.yaml").write_text(
                "completion_status: \"completed\"\n",
                encoding="utf-8",
            )
            (workspace_dir / "hello_world.py").write_text(
                "def main() -> None:\n    print(\"Hello, world!\")\n\n\nif __name__ == \"__main__\":\n    main()\n",
                encoding="utf-8",
            )
            (workspace_dir / "README.md").write_text(
                "# Hello World\n\nRun:\n\npython3 hello_world.py\n",
                encoding="utf-8",
            )
            tests_dir = workspace_dir / "tests"
            tests_dir.mkdir(exist_ok=True)
            (tests_dir / "__init__.py").write_text("", encoding="utf-8")
            (tests_dir / "test_cli.py").write_text(
                "def test_cli() -> None:\n    assert True\n",
                encoding="utf-8",
            )
            (tests_dir / "test_readme.py").write_text(
                "def test_readme() -> None:\n    assert True\n",
                encoding="utf-8",
            )
        elif phase.phase_id == "PH-007-verification-sweep":
            output.write_text("coverage_summary:\n  satisfaction_percentage: 100.0\n", encoding="utf-8")

        result = PhaseResult(
            phase_id=phase.phase_id,
            status=PhaseStatus.COMPLETED,
            prompt_runner_file="prompt.md",
            iteration_count=1,
            wall_time_seconds=0.1,
            prompt_runner_exit_code=0,
            prompt_runner_success=True,
            cross_ref_result=None,
            error_message=None,
        )
        state.phase_results[phase.phase_id] = result
        return result

    monkeypatch.setattr(
        "methodology_runner.orchestrator._run_single_phase",
        fake_run_single_phase,
    )
    monkeypatch.setattr(
        "methodology_runner.orchestrator.verify_end_to_end",
        lambda **kwargs: SimpleNamespace(
            passed=True,
            issues=[],
            traceability_gaps=[],
            orphaned_elements=[],
            coverage_summary={},
        ),
    )

    result = run_pipeline(config, claude_client=object())

    assert result.halted_early is False
    assert not (feature_worktree / ".methodology-runner").exists()
    assert not (feature_worktree / ".run-files").exists()
    assert (repo / "hello_world.py").exists()
    assert (repo / "README.md").exists()
    assert (repo / "tests" / "test_cli.py").exists()
    assert (
        repo
        / "docs"
        / "changes"
        / "change-001-hello-world"
        / "analysis"
        / "feature-specification.yaml"
    ).exists()
    assert (
        repo / "docs" / "features" / "hello-clock-capabilities.md"
    ).exists()
    assert (
        repo / "docs" / "design" / "hello-clock-design.md"
    ).exists()
    assert (
        repo / "docs" / "contracts" / "hello-clock-contracts.md"
    ).exists()
