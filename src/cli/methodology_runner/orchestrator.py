"""Pipeline orchestrator for methodology-runner.

Sequences the 7 methodology phases, manages the workspace and git,
invokes the prompt generator and prompt-runner for each phase, runs
cross-reference verification, and handles escalation and resumption.

See docs/design/components/CD-002-methodology-runner.md Sections 5-9.

Public API
----------
PipelineConfig
    Configuration dataclass for a methodology run.
PipelineResult
    Outcome dataclass returned by run_pipeline.
run_pipeline(config, *, claude_client=None)
    Execute the full methodology pipeline.
initialize_workspace(config)
    Create workspace directory structure, copy requirements, init git.
load_project_state(workspace)
    Load persisted state from disk (or None).
save_project_state(state, workspace)
    Atomically write state to disk.
write_summary(workspace, result)
    Write a human-readable summary file.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .models import (
    CrossRefCheckResult,
    CrossRefIssue,
    CrossRefResult,
    CrossReferenceResult,
    EscalationPolicy,
    PhaseResult,
    PhaseState,
    PhaseStatus,
    ProjectState,
)
from .phases import PHASES, PHASE_MAP, get_phase, resolve_input_sources
from .prompt_generator import (
    PromptGenerationContext,
    PromptGenerationError,
    generate_prompt_file,
)
from .cross_reference import (
    CrossReferenceError,
    verify_end_to_end,
    verify_phase_cross_references,
)
from .baseline_config import (
    BaselineConfigError,
    load_baseline_config,
    validate_against_catalog,
)
from .models import BaselineSkillConfig, SkillCatalogEntry
from .skill_catalog import CatalogBuildError, build_catalog

if TYPE_CHECKING:
    from .models import PhaseConfig
    from prompt_runner.claude_client import ClaudeClient


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CROSS_REF_RETRIES = 2
"""Default maximum re-generation attempts when cross-ref verification fails."""

METHODOLOGY_DIR = ".methodology-runner"
"""Hidden directory within the workspace for internal state and run artifacts."""

STATE_FILENAME = "state.json"
"""Name of the project-state JSON file inside METHODOLOGY_DIR."""

RUNS_SUBDIR = "runs"
"""Subdirectory of METHODOLOGY_DIR holding per-phase run artifacts."""

SUMMARY_FILENAME = "summary.txt"
"""Human-readable summary written after pipeline completion."""

REQUIREMENTS_DEST = "docs/requirements"
"""Workspace-relative directory where the raw requirements are copied."""

RAW_REQUIREMENTS_FILENAME = "raw-requirements.md"
"""Filename for the copied requirements document."""

_ISSUE_RE = re.compile(r"^\[(\w+)/(\w+)\] (.+)$")
"""Parses formatted issue strings from CrossRefResult.issues."""

_PROMPT_HEADING_RE = re.compile(r"^## Prompt \d+:", re.MULTILINE)
"""Counts prompt sections in a prompt-runner .md file."""

_COMPLETED_STATUSES = frozenset({
    PhaseStatus.COMPLETED,
    PhaseStatus.CROSS_REF_PASSED,
})
"""Phase statuses that count as 'done' for dependency and skip checks."""


# ---------------------------------------------------------------------------
# Configuration and result types (task-spec interface)
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    """Configuration for a methodology-runner pipeline execution."""

    requirements_path: Path
    workspace_dir: Path | None = None
    model: str | None = None
    resume: bool = False
    phases_to_run: list[str] | None = None
    max_prompt_runner_iterations: int | None = None
    escalation_policy: EscalationPolicy | None = None
    max_cross_ref_retries: int = MAX_CROSS_REF_RETRIES


@dataclass
class PipelineResult:
    """Outcome of a full or partial methodology pipeline execution."""

    workspace_dir: Path
    phase_results: list[PhaseResult]
    halted_early: bool
    halt_reason: str | None
    end_to_end_result: CrossRefResult | None
    wall_time_seconds: float


# ---------------------------------------------------------------------------
# Git helpers (CD-002 Section 5)
# ---------------------------------------------------------------------------

def _git(workspace: Path, *args: str) -> str:
    """Run a git command in *workspace* and return stripped stdout.

    Raises RuntimeError on non-zero exit.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def _git_init(workspace: Path) -> None:
    """Initialize a git repo in *workspace* if not already present."""
    if (workspace / ".git").exists():
        return
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "methodology-runner@local")
    _git(workspace, "config", "user.name", "Methodology Runner")


def _git_commit(workspace: Path, message: str) -> str:
    """Stage all changes and commit.  Returns the commit hash.

    If there are no changes to commit, returns the current HEAD hash.
    """
    _git(workspace, "add", "-A")
    status = _git(workspace, "status", "--porcelain")
    if not status:
        return _git(workspace, "rev-parse", "HEAD")
    _git(workspace, "commit", "-m", message)
    return _git(workspace, "rev-parse", "HEAD")


def _git_diff(workspace: Path) -> str:
    """Return the diff of uncommitted changes in *workspace*."""
    return _git(workspace, "diff")


def _git_discard_file(workspace: Path, rel_path: str) -> None:
    """Discard uncommitted changes to a single file, or delete it if untracked."""
    abs_path = workspace / rel_path
    try:
        _git(workspace, "checkout", "--", rel_path)
    except RuntimeError:
        if abs_path.exists():
            abs_path.unlink()


# ---------------------------------------------------------------------------
# Run-scoped skill context (CD-002 Section 11 — skill-driven selection)
# ---------------------------------------------------------------------------

@dataclass
class RunSkillContext:
    """Catalog and baseline config loaded once per run.

    Built by ``build_run_skill_context`` before any phase executes.
    Used by the orchestrator to invoke the Skill-Selector and build
    prelude files for each phase.
    """

    catalog: dict[str, SkillCatalogEntry]
    baseline_config: BaselineSkillConfig


BASELINE_SKILLS_PATH = "docs/methodology/skills-baselines.yaml"
"""Path (relative to repo root or workspace) to the baseline skill config."""


def build_run_skill_context(
    *,
    workspace: Path,
    baseline_path: Path | None = None,
    user_home: Path | None = None,
) -> RunSkillContext:
    """Load the skill catalog and baseline config for a run.

    Runs once at the start of every invocation of ``run_pipeline``
    (before any phase executes).  Raises on any failure so the
    orchestrator halts immediately — per spec failure modes 7 and 9.
    """
    catalog = build_catalog(workspace=workspace, user_home=user_home)

    if baseline_path is None:
        # Prefer a workspace-local copy if one exists, otherwise fall back
        # to the repo-level copy next to the CLI install.
        ws_copy = workspace / BASELINE_SKILLS_PATH
        if ws_copy.exists():
            baseline_path = ws_copy
        else:
            # Repo-root path: same working directory as the CLI invocation.
            baseline_path = Path(BASELINE_SKILLS_PATH)

    baseline_config = load_baseline_config(baseline_path)
    validate_against_catalog(baseline_config, catalog)
    return RunSkillContext(catalog=catalog, baseline_config=baseline_config)


# ---------------------------------------------------------------------------
# Workspace initialization (CD-002 Section 5.1)
# ---------------------------------------------------------------------------

def initialize_workspace(config: PipelineConfig) -> Path:
    """Create workspace directory structure, copy requirements, init git.

    Returns the resolved workspace path.  Idempotent -- safe to call on
    an existing workspace.
    """
    workspace = config.workspace_dir
    if workspace is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        workspace = Path.cwd() / f"methodology-workspace-{timestamp}"

    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    # Internal directories
    meth_dir = workspace / METHODOLOGY_DIR
    meth_dir.mkdir(exist_ok=True)
    (meth_dir / RUNS_SUBDIR).mkdir(exist_ok=True)

    # Phase-output directories (CD-002 Section 4.5)
    for subdir in (
        "docs/requirements",
        "docs/features",
        "docs/architecture",
        "docs/design",
        "docs/simulations",
        "docs/implementation",
        "docs/verification",
    ):
        (workspace / subdir).mkdir(parents=True, exist_ok=True)

    # Copy raw requirements
    req_dest = workspace / REQUIREMENTS_DEST / RAW_REQUIREMENTS_FILENAME
    if not req_dest.exists():
        src = config.requirements_path.resolve()
        if not src.exists():
            raise FileNotFoundError(
                f"Requirements file not found: {src}"
            )
        shutil.copy2(src, req_dest)

    # Git (CD-002 Section 5.1)
    _git_init(workspace)
    try:
        _git(workspace, "rev-parse", "HEAD")
    except RuntimeError:
        _git_commit(workspace, "Initial workspace with raw requirements")

    return workspace


# ---------------------------------------------------------------------------
# State management (CD-002 Section 9)
# ---------------------------------------------------------------------------

def _state_path(workspace: Path) -> Path:
    """Return the path to the project-state file."""
    return workspace / METHODOLOGY_DIR / STATE_FILENAME


def load_project_state(workspace: Path) -> ProjectState | None:
    """Load project state from disk.  Returns None if no state file exists."""
    path = _state_path(workspace)
    if not path.exists():
        return None
    return ProjectState.load(path)


def save_project_state(state: ProjectState, workspace: Path) -> None:
    """Atomically write project state to disk."""
    path = _state_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    state.save(path)


def _create_initial_state(
    workspace: Path,
    config: PipelineConfig,
) -> ProjectState:
    """Create a fresh ProjectState with all phases set to PENDING."""
    phase_states = [
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
    ]
    return ProjectState(
        workspace_dir=workspace,
        requirements_path=config.requirements_path.resolve(),
        phase_results={},
        started_at=_iso_now(),
        git_initialized=True,
        project_name=config.requirements_path.stem,
        model=config.model,
        phases=phase_states,
    )


def _find_phase_state(state: ProjectState, phase_id: str) -> PhaseState:
    """Locate the PhaseState for *phase_id* within *state.phases*.

    Raises ValueError if not found.
    """
    for ps in state.phases:
        if ps.phase_id == phase_id:
            return ps
    raise ValueError(f"Phase {phase_id} not found in project state")


def _iso_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Artifact verification
# ---------------------------------------------------------------------------

def _verify_predecessor_artifacts(
    phase_config: PhaseConfig,
    state: ProjectState,
    workspace: Path,
) -> str | None:
    """Check that predecessor phases are completed and their artifacts exist.

    Returns an error message string if verification fails, or None when
    all predecessors are satisfied.  Checks both the PhaseState status
    and the physical existence of each predecessor's output artifact on
    disk, so a deleted file between runs is caught before we start.
    """
    for pred_id in phase_config.predecessors:
        pred_ps = _find_phase_state(state, pred_id)
        if pred_ps.status not in _COMPLETED_STATUSES:
            return (
                f"Predecessor {pred_id} not completed "
                f"(status: {pred_ps.status.value}); "
                f"cannot start {phase_config.phase_id}"
            )
        pred_cfg = PHASE_MAP.get(pred_id)
        if pred_cfg is not None:
            artifact = workspace / pred_cfg.output_artifact_path
            if not artifact.exists():
                return (
                    f"Predecessor {pred_id} is marked completed but "
                    f"its output artifact is missing: "
                    f"{pred_cfg.output_artifact_path}"
                )
    return None


def _verify_phase_output_exists(
    phase_config: PhaseConfig,
    workspace: Path,
) -> str | None:
    """Check that the phase's own output artifact exists on disk.

    Used before running cross-ref-only on resume to ensure the file
    that cross-reference verification will inspect actually exists.
    Returns an error message on failure, None on success.
    """
    artifact = workspace / phase_config.output_artifact_path
    if not artifact.exists():
        return (
            f"Phase {phase_config.phase_id} is marked as "
            f"prompt_runner_passed but its output artifact is missing: "
            f"{phase_config.output_artifact_path}"
        )
    return None


# ---------------------------------------------------------------------------
# Cross-ref feedback reconstruction
# ---------------------------------------------------------------------------

def _reconstruct_cross_ref_feedback(
    result: CrossRefResult,
) -> CrossReferenceResult:
    """Rebuild a structured CrossReferenceResult from a flat CrossRefResult.

    The cross-reference module's public API returns CrossRefResult (flat).
    The prompt generator's PromptGenerationContext.cross_ref_feedback needs
    CrossReferenceResult (structured).  This helper parses the formatted
    issue strings back into structured objects.
    """
    category_issues: dict[str, list[CrossRefIssue]] = {
        cat: [] for cat in ("traceability", "coverage", "consistency", "integration")
    }

    for issue_str in result.issues:
        match = _ISSUE_RE.match(issue_str)
        if not match:
            continue
        cat, sev, desc = match.groups()
        affected: list[str] = []
        if cat == "traceability":
            affected = list(result.traceability_gaps)
        elif cat == "integration":
            affected = list(result.orphaned_elements)
        if cat in category_issues:
            category_issues[cat].append(
                CrossRefIssue(
                    category=cat,
                    description=desc,
                    affected_elements=affected,
                    severity=sev,
                )
            )

    def _to_check(cat: str) -> CrossRefCheckResult:
        issues = category_issues[cat]
        has_blocking = any(i.severity == "blocking" for i in issues)
        return CrossRefCheckResult(
            status="fail" if has_blocking else "pass",
            issues=issues,
        )

    return CrossReferenceResult(
        verdict="pass" if result.passed else "fail",
        traceability=_to_check("traceability"),
        coverage=_to_check("coverage"),
        consistency=_to_check("consistency"),
        integration=_to_check("integration"),
    )


# ---------------------------------------------------------------------------
# Prompt-runner invocation (CD-002 Section 6)
# ---------------------------------------------------------------------------

def _invoke_prompt_runner_library(
    md_file: Path,
    workspace: Path,
    run_dir: Path,
    config: PipelineConfig,
    claude_client: ClaudeClient | None = None,
) -> tuple[bool, int, str | None]:
    """Invoke prompt-runner via direct library call (preferred).

    Returns ``(success, total_iteration_count, error_message_or_none)``.
    """
    from prompt_runner.parser import parse_file
    from prompt_runner.runner import RunConfig
    from prompt_runner.runner import run_pipeline as pr_run_pipeline

    if claude_client is None:
        from prompt_runner.claude_client import RealClaudeClient
        claude_client = RealClaudeClient()

    pairs = parse_file(md_file)
    max_iters = config.max_prompt_runner_iterations or 3
    pr_config = RunConfig(max_iterations=max_iters, model=config.model)

    pr_result = pr_run_pipeline(
        pairs=pairs,
        run_dir=run_dir,
        config=pr_config,
        claude_client=claude_client,
        source_file=md_file,
        workspace_dir=workspace,
    )

    total_iterations = sum(
        len(pr.iterations) for pr in pr_result.prompt_results
    )

    if pr_result.halted_early:
        return False, total_iterations, pr_result.halt_reason

    return True, total_iterations, None


def _invoke_prompt_runner_subprocess(
    md_file: Path,
    workspace: Path,
    config: PipelineConfig,
) -> tuple[bool, int, str | None]:
    """Invoke prompt-runner via subprocess (fallback).

    Returns ``(success, estimated_iteration_count, error_message_or_none)``.
    The iteration count is estimated from the number of prompt headings
    in the .md file (one iteration per prompt assumed).
    """
    max_iters = config.max_prompt_runner_iterations or 3
    content = md_file.read_text(encoding="utf-8")
    prompt_count = len(_PROMPT_HEADING_RE.findall(content))

    base_args = [
        "run", str(md_file),
        "--project-dir", str(workspace),
        "--max-iterations", str(max_iters),
    ]
    if config.model:
        base_args.extend(["--model", config.model])

    # Try the installed entry-point first
    result = subprocess.run(
        ["prompt-runner", *base_args],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode == 127:  # command not found
        result = subprocess.run(
            [sys.executable, "-m", "prompt_runner", *base_args],
            capture_output=True,
            text=True,
            check=False,
        )

    if result.returncode == 0:
        return True, prompt_count, None

    error = result.stderr.strip() or result.stdout.strip() or "(no output)"
    return False, prompt_count, f"Exit code {result.returncode}: {error}"


def _invoke_prompt_runner(
    md_file: Path,
    workspace: Path,
    run_dir: Path,
    config: PipelineConfig,
    claude_client: ClaudeClient | None = None,
) -> tuple[bool, int, str | None]:
    """Invoke prompt-runner, trying library call first then subprocess.

    Returns ``(success, iteration_count, error_message_or_none)``.
    """
    try:
        return _invoke_prompt_runner_library(
            md_file, workspace, run_dir, config, claude_client,
        )
    except ImportError:
        return _invoke_prompt_runner_subprocess(md_file, workspace, config)


# ---------------------------------------------------------------------------
# Phase-execution helpers
# ---------------------------------------------------------------------------

def _get_completed_phase_ids(state: ProjectState) -> list[str]:
    """Return phase_ids whose status counts as completed."""
    return [
        ps.phase_id for ps in state.phases
        if ps.status in _COMPLETED_STATUSES
    ]


def _get_completed_phase_states(state: ProjectState) -> list[PhaseState]:
    """Return PhaseState objects for all completed phases."""
    return [
        ps for ps in state.phases
        if ps.status in _COMPLETED_STATUSES
    ]


def _phase_run_dir(workspace: Path, phase_config: PhaseConfig) -> Path:
    """Return the run-artifact directory for a phase."""
    return (
        workspace
        / METHODOLOGY_DIR
        / RUNS_SUBDIR
        / f"phase-{phase_config.phase_number}"
    )


def _effective_escalation_policy(
    config: PipelineConfig,
    phase_config: PhaseConfig,
) -> EscalationPolicy:
    """Determine the escalation policy to use for a phase."""
    return config.escalation_policy or phase_config.escalation_policy


def _status_for_policy(policy: EscalationPolicy) -> PhaseStatus:
    """Map an escalation policy to the PhaseStatus used on failure.

    Consistent across prompt-runner and cross-ref failure paths:
    - HALT -> FAILED
    - FLAG_AND_CONTINUE -> FAILED
    - HUMAN_REVIEW -> ESCALATED
    """
    if policy == EscalationPolicy.HUMAN_REVIEW:
        return PhaseStatus.ESCALATED
    return PhaseStatus.FAILED


def _make_failed_result(
    phase_id: str,
    prompt_file: Path,
    iteration_count: int,
    wall_time: float,
    error: str,
    status: PhaseStatus = PhaseStatus.FAILED,
    cross_ref: CrossRefResult | None = None,
    pr_success: bool = False,
) -> PhaseResult:
    """Construct a PhaseResult for a failed phase execution."""
    return PhaseResult(
        phase_id=phase_id,
        status=status,
        prompt_runner_file=str(prompt_file),
        iteration_count=iteration_count,
        wall_time_seconds=wall_time,
        prompt_runner_success=pr_success,
        cross_ref_result=cross_ref,
        error_message=error,
    )


# ---------------------------------------------------------------------------
# Single phase execution
# ---------------------------------------------------------------------------

def _run_single_phase(
    phase_config: PhaseConfig,
    state: ProjectState,
    workspace: Path,
    config: PipelineConfig,
    claude_client: ClaudeClient | None = None,
    cross_ref_only: bool = False,
    skill_ctx: RunSkillContext | None = None,
) -> PhaseResult:
    """Execute one methodology phase end-to-end.

    Handles prompt generation, prompt-runner invocation, cross-reference
    verification with re-generation retries, state updates, and git
    commits.

    When *cross_ref_only* is True (resume of a phase that already passed
    prompt-runner), skips steps 1-6 and runs only cross-ref verification.
    """
    phase_id = phase_config.phase_id
    ps = _find_phase_state(state, phase_id)
    t0 = time.monotonic()

    run_dir = _phase_run_dir(workspace, phase_config)
    run_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = run_dir / "prompt-file.md"
    cross_ref_path = run_dir / "cross-ref-result.json"
    policy = _effective_escalation_policy(config, phase_config)
    max_retries = config.max_cross_ref_retries
    iteration_count = 0

    # ------------------------------------------------------------------
    # Steps 1-6: prompt generation + prompt-runner  (skip if cross_ref_only)
    # ------------------------------------------------------------------
    if not cross_ref_only:
        # Step 1-2: mark running
        ps.status = PhaseStatus.RUNNING
        ps.started_at = _iso_now()
        state.current_phase = phase_id
        save_project_state(state, workspace)

        # Step 3: generate prompt-runner .md file
        completed_states = _get_completed_phase_states(state)
        ctx = PromptGenerationContext(
            phase_config=phase_config,
            workspace_dir=workspace,
            completed_phases=completed_states,
        )
        try:
            generate_prompt_file(ctx, claude_client, prompt_file, config.model)
        except PromptGenerationError as exc:
            ps.status = PhaseStatus.FAILED
            save_project_state(state, workspace)
            return _make_failed_result(
                phase_id, prompt_file, 0,
                time.monotonic() - t0, str(exc),
            )

        ps.prompt_file = str(prompt_file)
        save_project_state(state, workspace)

        # Step 4-5: invoke prompt-runner
        pr_run_dir = run_dir / "prompt-runner-output"
        success, iteration_count, pr_error = _invoke_prompt_runner(
            prompt_file, workspace, pr_run_dir, config, claude_client,
        )

        if not success:
            # All three policies return immediately on prompt-runner
            # failure.  Only the status differs (FAILED vs ESCALATED).
            fail_status = _status_for_policy(policy)
            ps.status = fail_status
            save_project_state(state, workspace)
            return _make_failed_result(
                phase_id, prompt_file, iteration_count,
                time.monotonic() - t0,
                f"prompt-runner failed: {pr_error}",
                status=fail_status,
            )

        # Step 6: mark prompt-runner passed (only reached when success)
        ps.status = PhaseStatus.PROMPT_RUNNER_PASSED
        save_project_state(state, workspace)
    else:
        # cross_ref_only path: verify the output artifact still exists
        # before attempting cross-ref verification.
        err = _verify_phase_output_exists(phase_config, workspace)
        if err is not None:
            ps.status = PhaseStatus.FAILED
            save_project_state(state, workspace)
            return _make_failed_result(
                phase_id, prompt_file, 0,
                time.monotonic() - t0, err,
            )
        # Also verify predecessor artifacts for cross-ref context
        err = _verify_predecessor_artifacts(phase_config, state, workspace)
        if err is not None:
            ps.status = PhaseStatus.FAILED
            save_project_state(state, workspace)
            return _make_failed_result(
                phase_id, prompt_file, 0,
                time.monotonic() - t0, err,
            )

    # ------------------------------------------------------------------
    # Steps 7-9: cross-reference verification with retry loop
    # ------------------------------------------------------------------
    completed_ids = _get_completed_phase_ids(state)
    cross_ref_result: CrossRefResult | None = None

    for attempt in range(max_retries + 1):
        # Run cross-ref check
        try:
            cross_ref_result = verify_phase_cross_references(
                phase=phase_config,
                workspace=workspace,
                completed_phases=completed_ids,
                model=config.model,
                claude_client=claude_client,
            )
        except CrossReferenceError as exc:
            cross_ref_result = CrossRefResult(
                passed=False,
                issues=[str(exc)],
                traceability_gaps=[],
                orphaned_elements=[],
                coverage_summary={},
            )

        ps.cross_ref_retries = attempt
        ps.cross_ref_result_path = str(cross_ref_path)

        # Persist cross-ref result
        cross_ref_path.write_text(
            json.dumps(cross_ref_result.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

        if cross_ref_result.passed:
            break

        # Retry: re-generate with feedback, re-run prompt-runner
        if attempt >= max_retries:
            break

        # Discard the failed phase output before re-generation
        _git_discard_file(workspace, phase_config.output_artifact_path)

        # Re-generate the prompt file with cross-ref feedback
        feedback = _reconstruct_cross_ref_feedback(cross_ref_result)
        completed_states = _get_completed_phase_states(state)
        ctx = PromptGenerationContext(
            phase_config=phase_config,
            workspace_dir=workspace,
            completed_phases=completed_states,
            cross_ref_feedback=feedback,
        )
        try:
            generate_prompt_file(ctx, claude_client, prompt_file, config.model)
        except PromptGenerationError as exc:
            ps.status = PhaseStatus.FAILED
            save_project_state(state, workspace)
            return _make_failed_result(
                phase_id, prompt_file, iteration_count,
                time.monotonic() - t0,
                f"Re-generation after cross-ref failure failed: {exc}",
                cross_ref=cross_ref_result,
                pr_success=True,
            )

        # Re-run prompt-runner on the revised file
        retry_run_dir = run_dir / f"prompt-runner-output-retry-{attempt + 1}"
        success, extra_iters, pr_error = _invoke_prompt_runner(
            prompt_file, workspace, retry_run_dir, config, claude_client,
        )
        iteration_count += extra_iters

        if not success:
            # Prompt-runner failed on retry -- stop retrying cross-ref
            cross_ref_result = CrossRefResult(
                passed=False,
                issues=[f"prompt-runner failed on retry {attempt + 1}: {pr_error}"],
                traceability_gaps=[],
                orphaned_elements=[],
                coverage_summary={},
            )
            break

    # Evaluate final cross-ref outcome
    if cross_ref_result is not None and not cross_ref_result.passed:
        fail_status = _status_for_policy(policy)
        ps.status = fail_status
        save_project_state(state, workspace)
        return _make_failed_result(
            phase_id, prompt_file, iteration_count,
            time.monotonic() - t0,
            (
                f"Cross-reference verification failed after "
                f"{ps.cross_ref_retries + 1} attempt(s)"
            ),
            status=fail_status,
            cross_ref=cross_ref_result,
            pr_success=True,
        )

    # ------------------------------------------------------------------
    # Step 9-10: mark completed, git commit
    # ------------------------------------------------------------------
    ps.status = PhaseStatus.CROSS_REF_PASSED
    save_project_state(state, workspace)

    commit_msg = (
        f"Phase {phase_config.phase_number}: "
        f"{phase_config.phase_name} -- completed"
    )
    try:
        commit_hash = _git_commit(workspace, commit_msg)
        ps.git_commit = commit_hash
    except RuntimeError:
        pass  # non-fatal: git commit failure does not block the pipeline

    ps.status = PhaseStatus.COMPLETED
    ps.completed_at = _iso_now()
    save_project_state(state, workspace)

    wall_time = time.monotonic() - t0
    phase_result = PhaseResult(
        phase_id=phase_id,
        status=PhaseStatus.COMPLETED,
        prompt_runner_file=str(prompt_file),
        iteration_count=iteration_count,
        wall_time_seconds=wall_time,
        prompt_runner_success=True,
        cross_ref_result=cross_ref_result,
        prompt_file_path=prompt_file,
        run_dir=run_dir,
    )
    state.phase_results[phase_id] = phase_result
    save_project_state(state, workspace)

    return phase_result


# ---------------------------------------------------------------------------
# Reporting (CD-002 Section 4.5 workspace layout)
# ---------------------------------------------------------------------------

def write_summary(workspace: Path, result: PipelineResult) -> None:
    """Write a human-readable summary to .methodology-runner/summary.txt.

    Called incrementally after each phase and once at pipeline end.
    Each call overwrites the file so it always reflects the latest state.
    """
    lines: list[str] = [
        "=" * 60,
        "Methodology Runner -- Pipeline Summary",
        "=" * 60,
        "",
        f"Workspace:       {result.workspace_dir}",
        f"Total wall time: {result.wall_time_seconds:.1f}s",
        f"Halted early:    {result.halted_early}",
    ]
    if result.halt_reason:
        lines.append(f"Halt reason:     {result.halt_reason}")

    completed_count = sum(
        1 for pr in result.phase_results
        if pr.status == PhaseStatus.COMPLETED
    )
    lines.append(f"Phases completed: {completed_count}/{len(result.phase_results)}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("Phase Results")
    lines.append("-" * 60)

    for pr in result.phase_results:
        phase = PHASE_MAP.get(pr.phase_id)
        name = phase.phase_name if phase else pr.phase_id
        lines.append("")
        lines.append(f"  {pr.phase_id} ({name})")
        lines.append(f"    Status:     {pr.status.value}")
        lines.append(f"    Iterations: {pr.iteration_count}")
        lines.append(f"    Wall time:  {pr.wall_time_seconds:.1f}s")

        if pr.cross_ref_result is not None:
            xr = pr.cross_ref_result
            lines.append(f"    Cross-ref:  {'PASS' if xr.passed else 'FAIL'}")
            if xr.coverage_summary:
                parts = [
                    f"{k}: {v:.0%}" for k, v in xr.coverage_summary.items()
                ]
                lines.append(f"    Coverage:   {', '.join(parts)}")
            if xr.issues:
                limit = 5
                lines.append(f"    Issues ({len(xr.issues)}):")
                for issue in xr.issues[:limit]:
                    lines.append(f"      - {issue}")
                if len(xr.issues) > limit:
                    lines.append(
                        f"      ... and {len(xr.issues) - limit} more"
                    )

        if pr.error_message:
            lines.append(f"    Error:      {pr.error_message}")

    if result.end_to_end_result is not None:
        lines.append("")
        lines.append("-" * 60)
        lines.append("End-to-End Verification")
        lines.append("-" * 60)
        e2e = result.end_to_end_result
        lines.append(f"  Verdict: {'PASS' if e2e.passed else 'FAIL'}")
        if e2e.coverage_summary:
            for k, v in e2e.coverage_summary.items():
                lines.append(f"  {k}: {v:.0%}")
        if e2e.issues:
            lines.append(f"  Issues ({len(e2e.issues)}):")
            for issue in e2e.issues:
                lines.append(f"    - {issue}")

    lines.extend(["", "=" * 60, ""])

    summary_path = workspace / METHODOLOGY_DIR / SUMMARY_FILENAME
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline(
    config: PipelineConfig,
    *,
    claude_client: ClaudeClient | None = None,
) -> PipelineResult:
    """Execute the methodology pipeline.

    Sequences all 7 phases (or a subset specified by
    ``config.phases_to_run``), generates prompt-runner input files,
    invokes prompt-runner, runs cross-reference verification, and
    manages workspace state and git commits.

    When ``config.resume`` is True, loads existing state and skips
    phases that have already completed.

    The summary file is updated incrementally after each phase
    completes, so a crash mid-pipeline still leaves a readable
    summary of progress.

    Parameters
    ----------
    config:
        Pipeline configuration.
    claude_client:
        Optional injected ClaudeClient (for testing).  When None,
        a RealClaudeClient is created internally.
    """
    t0 = time.monotonic()

    # ---- workspace and state ----
    workspace = initialize_workspace(config)

    # ---- skill catalog + baseline config (run-scoped) ----
    try:
        skill_ctx = build_run_skill_context(workspace=workspace)
    except (CatalogBuildError, BaselineConfigError) as exc:
        return PipelineResult(
            workspace_dir=workspace,
            phase_results=[],
            halted_early=True,
            halt_reason=f"skill context build failed: {exc}",
            end_to_end_result=None,
            wall_time_seconds=time.monotonic() - t0,
        )

    state: ProjectState | None = None
    if config.resume:
        state = load_project_state(workspace)

    if state is None:
        state = _create_initial_state(workspace, config)
        save_project_state(state, workspace)

    # ---- claude client ----
    if claude_client is None:
        try:
            from prompt_runner.claude_client import RealClaudeClient
            claude_client = RealClaudeClient()
        except ImportError:
            pass  # will use subprocess fallback for prompt-runner;
                  # prompt generator and cross-ref will create their own

    # ---- determine phases ----
    phases_to_run: list[PhaseConfig] = list(PHASES)
    if config.phases_to_run is not None:
        phases_to_run = [get_phase(pid) for pid in config.phases_to_run]

    # ---- execute phases ----
    phase_results: list[PhaseResult] = []
    halted_early = False
    halt_reason: str | None = None

    for phase in phases_to_run:
        ps = _find_phase_state(state, phase.phase_id)

        # Resume: skip completed phases
        if config.resume and ps.status in _COMPLETED_STATUSES:
            existing = state.phase_results.get(phase.phase_id)
            if existing is not None:
                phase_results.append(existing)
            continue

        # Resume: re-run cross-ref only if prompt-runner already passed
        cross_ref_only = (
            config.resume
            and ps.status == PhaseStatus.PROMPT_RUNNER_PASSED
        )

        # Predecessor check: verify both status and artifact existence
        if not cross_ref_only:
            err = _verify_predecessor_artifacts(phase, state, workspace)
            if err is not None:
                halted_early = True
                halt_reason = err
                break

        # Execute
        result = _run_single_phase(
            phase, state, workspace, config,
            claude_client=claude_client,
            cross_ref_only=cross_ref_only,
            skill_ctx=skill_ctx,
        )
        phase_results.append(result)

        # Incremental summary: overwrite after each phase so a crash
        # mid-pipeline still leaves a readable summary of progress.
        write_summary(
            workspace,
            PipelineResult(
                workspace_dir=workspace,
                phase_results=list(phase_results),
                halted_early=False,
                halt_reason=None,
                end_to_end_result=None,
                wall_time_seconds=time.monotonic() - t0,
            ),
        )

        # Handle failure
        if result.status in (PhaseStatus.FAILED, PhaseStatus.ESCALATED):
            policy = _effective_escalation_policy(config, phase)
            if policy != EscalationPolicy.FLAG_AND_CONTINUE:
                halted_early = True
                halt_reason = result.error_message
                break
            # FLAG_AND_CONTINUE: keep going (subsequent phases may fail
            # their predecessor check, which is correct behaviour)

    # ---- end-to-end verification ----
    end_to_end_result: CrossRefResult | None = None
    all_done = all(
        _find_phase_state(state, p.phase_id).status in _COMPLETED_STATUSES
        for p in PHASES
    )

    if all_done and not halted_early:
        try:
            end_to_end_result = verify_end_to_end(
                workspace=workspace,
                model=config.model,
                claude_client=claude_client,
            )
        except CrossReferenceError as exc:
            end_to_end_result = CrossRefResult(
                passed=False,
                issues=[str(exc)],
                traceability_gaps=[],
                orphaned_elements=[],
                coverage_summary={},
            )

    # ---- finalise ----
    state.finished_at = _iso_now()
    state.current_phase = None
    save_project_state(state, workspace)

    wall_time = time.monotonic() - t0
    pipeline_result = PipelineResult(
        workspace_dir=workspace,
        phase_results=phase_results,
        halted_early=halted_early,
        halt_reason=halt_reason,
        end_to_end_result=end_to_end_result,
        wall_time_seconds=wall_time,
    )

    # Final summary with end-to-end results and halt status
    write_summary(workspace, pipeline_result)
    return pipeline_result
