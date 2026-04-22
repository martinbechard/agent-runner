"""Command-line interface for methodology-runner.

Provides four subcommands:

    run      Execute the full methodology pipeline on a requirements file.
    status   Show per-phase status for an existing workspace.
    resume   Resume a halted or interrupted pipeline run.
    reset    Reset a phase and all downstream phases to pending.

Exit codes (CD-002 Section 10.6):
    0  All phases completed successfully.
    1  Pipeline halted due to escalation or phase failure.
    2  Usage error (missing file, bad arguments, missing dependency).

See tools/methodology-runner/docs/design/components/CD-002-methodology-runner.md
Section 10.6.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    EscalationPolicy,
    METHODOLOGY_LIFECYCLE_PHASE_ID,
    PhaseStatus,
    ProjectState,
)
from prompt_runner.config import resolve_default_backend
from prompt_runner.client_factory import check_backend_cli

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXIT_SUCCESS = 0
EXIT_ESCALATION = 1
EXIT_USAGE_ERROR = 2

BANNER_RULE = "=" * 60

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
"""Regex for slugifying a requirements filename."""

_STATUS_LABELS: dict[PhaseStatus, str] = {
    PhaseStatus.PENDING: "pending",
    PhaseStatus.IN_PROGRESS: "in progress",
    PhaseStatus.RUNNING: "running",
    PhaseStatus.PROMPT_RUNNER_PASSED: "prompt-runner passed",
    PhaseStatus.CROSS_REF_PASSED: "cross-ref passed",
    PhaseStatus.COMPLETED: "completed",
    PhaseStatus.FAILED: "FAILED",
    PhaseStatus.ESCALATED: "ESCALATED (human review needed)",
    PhaseStatus.SKIPPED: "skipped",
}

_STATE_FILENAME = ".methodology-runner/state.json"
"""Relative path to the state file within a workspace."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert a filename stem to a URL-safe slug."""
    return _SLUG_STRIP_RE.sub("-", name.lower()).strip("-")


def _auto_workspace(requirements_path: Path) -> Path:
    """Generate a timestamped workspace directory name under ``./runs/``."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    slug = _slugify(requirements_path.stem)
    return Path("runs") / f"{timestamp}-{slug}"


def _resolve_workspace(workspace_arg: str | None, requirements_path: Path) -> Path:
    """Resolve an explicit workspace or auto-generate one."""
    if workspace_arg is not None:
        return Path(workspace_arg).resolve()
    return _auto_workspace(requirements_path).resolve()


def _git(args: list[str], *, cwd: Path) -> str:
    """Run a git command and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def _derive_change_branch_name(
    requirements_path: Path,
    change_id: str | None,
    explicit_branch_name: str | None,
) -> str:
    """Return the branch name for one change run."""
    if explicit_branch_name:
        return explicit_branch_name
    stem_slug = _slugify(requirements_path.stem)
    if change_id is None:
        return stem_slug
    if stem_slug.startswith(change_id):
        return stem_slug
    if stem_slug:
        return f"{change_id}-{stem_slug}"
    return change_id


def _default_change_worktree(
    application_repo: Path,
    branch_name: str,
) -> Path:
    """Return the default sibling worktree path for one change branch."""
    return (
        application_repo.parent
        / f"{application_repo.name}-worktrees"
        / branch_name
    )


def _prepare_application_worktree(
    *,
    application_repo: Path,
    requirements_path: Path,
    workspace_arg: str | None,
    change_id: str | None,
    branch_name_arg: str | None,
) -> tuple[Path, str]:
    """Create or reuse the application worktree for one change run."""
    repo = application_repo.resolve()
    if not repo.exists():
        raise RuntimeError(f"Application repo not found: {repo}")
    try:
        repo_root = Path(_git(["rev-parse", "--show-toplevel"], cwd=repo)).resolve()
    except RuntimeError as exc:
        raise RuntimeError(f"Application repo is not a git checkout: {repo}") from exc

    if _git(["status", "--porcelain"], cwd=repo_root):
        raise RuntimeError(
            f"Application repo checkout is not clean: {repo_root}"
        )

    branch_name = _derive_change_branch_name(
        requirements_path,
        change_id,
        branch_name_arg,
    )
    workspace = (
        Path(workspace_arg).resolve()
        if workspace_arg is not None
        else _default_change_worktree(repo_root, branch_name).resolve()
    )

    if workspace.exists():
        if not (workspace / ".git").exists() and not (workspace / ".git").is_file():
            raise RuntimeError(
                f"Requested workspace exists but is not a git worktree: {workspace}"
            )
        current_branch = _git(["branch", "--show-current"], cwd=workspace)
        if current_branch != branch_name:
            raise RuntimeError(
                "Requested workspace already exists on a different branch: "
                f"{workspace} (current={current_branch}, expected={branch_name})"
            )
        return workspace, branch_name

    workspace.parent.mkdir(parents=True, exist_ok=True)
    existing_branches = {
        line.removeprefix("* ").strip()
        for line in _git(["branch", "--list"], cwd=repo_root).splitlines()
        if line.strip()
    }
    worktree_args = ["worktree", "add", str(workspace)]
    if branch_name in existing_branches:
        worktree_args.append(branch_name)
    else:
        worktree_args.extend(["-b", branch_name])
    try:
        _git(worktree_args, cwd=repo_root)
    except RuntimeError as exc:
        raise RuntimeError(
            f"Could not create application worktree {workspace}: {exc}"
        ) from exc
    return workspace, branch_name


def _print_banner(title: str) -> None:
    sys.stdout.write(f"\n{BANNER_RULE}\n{title}\n{BANNER_RULE}\n")
    sys.stdout.flush()


def _print_error(message: str) -> None:
    sys.stderr.write(f"\nError: {message}\n")
    sys.stderr.flush()


def _load_state(workspace: Path) -> ProjectState | None:
    """Load project state from a workspace, returning None if missing."""
    state_path = workspace / _STATE_FILENAME
    if not state_path.exists():
        return None
    return ProjectState.load(state_path)


def _any_escalated(phase_results: list | dict) -> bool:
    """Check if any phase result has ESCALATED status.

    Accepts both ``list[PhaseResult]`` (from PipelineResult) and
    ``dict[str, PhaseResult]`` (from ProjectState).
    """
    items = phase_results.values() if isinstance(phase_results, dict) else phase_results
    return any(pr.status == PhaseStatus.ESCALATED for pr in items)


def _find_lifecycle_phase(state: ProjectState, phase_id: str):
    """Return one lifecycle phase state by ID."""
    for lifecycle_phase in state.lifecycle_phases:
        if lifecycle_phase.phase_id == phase_id:
            return lifecycle_phase
    return None


def _pending_manual_lifecycle_phase_ids(state: ProjectState) -> list[str]:
    """Return pending manual lifecycle phases from the current state."""
    return [
        phase.phase_id
        for phase in state.lifecycle_phases
        if phase.execution_kind == "manual" and phase.status == PhaseStatus.PENDING
    ]


def _format_duration(seconds: float) -> str:
    """Format seconds as a human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds) // 60
    remaining = seconds - (minutes * 60)
    return f"{minutes}m {remaining:.1f}s"


def _phase_run_artifact_dir(workspace: Path, phase_number: int) -> Path:
    """Return the methodology-runner run-artifact directory for one phase."""
    return workspace / ".methodology-runner" / "runs" / f"phase-{phase_number}"


def _reset_phase_selection(
    workspace: Path,
    phase_id: str,
    *,
    cleanup_files: bool,
) -> list[str]:
    """Reset one phase plus downstream phases, optionally deleting artifacts."""
    from .phases import PHASE_MAP
    from .orchestrator import _change_record_root, save_project_state

    ids_to_reset = _downstream_phase_ids(phase_id)
    state = _load_state(workspace)

    if state is not None:
        for ps in state.phases:
            if ps.phase_id in ids_to_reset:
                ps.status = PhaseStatus.PENDING
                ps.started_at = None
                ps.completed_at = None
                ps.cross_ref_retries = 0
                ps.git_commit = None
                ps.prompt_file = None
                ps.cross_ref_result_path = None
        for rid in ids_to_reset:
            state.phase_results.pop(rid, None)
        methodology = _find_lifecycle_phase(state, METHODOLOGY_LIFECYCLE_PHASE_ID)
        if methodology is not None:
            methodology.status = PhaseStatus.PENDING
            methodology.started_at = None
            methodology.completed_at = None
        for lifecycle_phase in state.lifecycle_phases:
            if lifecycle_phase.phase_id == "LC-000-change-preparation":
                continue
            if lifecycle_phase.phase_id != METHODOLOGY_LIFECYCLE_PHASE_ID:
                lifecycle_phase.status = PhaseStatus.PENDING
                lifecycle_phase.started_at = None
                lifecycle_phase.completed_at = None
        state.current_phase = None
        state.current_lifecycle_phase_id = METHODOLOGY_LIFECYCLE_PHASE_ID
        state.finished_at = None
        save_project_state(state, workspace)

    if cleanup_files:
        for rid in ids_to_reset:
            phase = PHASE_MAP[rid]
            for relpath in phase.expected_output_files:
                (workspace / relpath).unlink(missing_ok=True)
            shutil.rmtree(
                _phase_run_artifact_dir(workspace, phase.phase_number),
                ignore_errors=True,
            )
        if state is not None:
            shutil.rmtree(
                _change_record_root(workspace, state.change_id or workspace.name),
                ignore_errors=True,
            )

    return ids_to_reset


def _validate_resettable_phase_subset(
    reset_requested: bool,
    phases_to_run: list[str] | None,
) -> str | None:
    """Return the single selected phase ID if --reset is allowed."""
    if not reset_requested:
        return None
    if phases_to_run is None or len(phases_to_run) != 1:
        raise ValueError("--reset requires exactly one phase selected via --phases")
    return phases_to_run[0]


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    """Execute the methodology pipeline or a selected phase subset."""
    requirements_path = Path(args.requirements_file).resolve()
    if not requirements_path.exists():
        _print_error(f"Requirements file not found: {requirements_path}")
        return EXIT_USAGE_ERROR

    backend = resolve_default_backend(requirements_path, args.backend)

    # Pre-flight checks for external dependencies
    backend_err = check_backend_cli(backend)
    if backend_err is not None:
        _print_error(backend_err)
        return EXIT_USAGE_ERROR

    try:
        if args.application_repo is not None:
            workspace, branch_name = _prepare_application_worktree(
                application_repo=Path(args.application_repo),
                requirements_path=requirements_path,
                workspace_arg=args.workspace,
                change_id=args.change_id,
                branch_name_arg=args.branch_name,
            )
        else:
            workspace = _resolve_workspace(args.workspace, requirements_path)
            branch_name = None
    except RuntimeError as exc:
        _print_error(str(exc))
        return EXIT_USAGE_ERROR

    # Late import so --help works even without prompt-runner installed.
    try:
        from .orchestrator import PipelineConfig, run_pipeline
        from .phases import normalize_phase_selection
    except ImportError as exc:
        _print_error(
            f"Could not import methodology-runner orchestrator: {exc}\n"
            "Make sure prompt-runner is installed: pip install -e tools/prompt-runner"
        )
        return EXIT_USAGE_ERROR

    escalation_policy: EscalationPolicy | None = None
    if args.escalation_policy is not None:
        escalation_policy = EscalationPolicy(
            args.escalation_policy.replace("-", "_")
        )

    phases_to_run: list[str] | None = None
    if args.phases is not None:
        phases_to_run = normalize_phase_selection(
            [p.strip() for p in args.phases.split(",") if p.strip()]
        )
    try:
        reset_phase_id = _validate_resettable_phase_subset(args.reset, phases_to_run)
    except ValueError as exc:
        _print_error(str(exc))
        return EXIT_USAGE_ERROR

    if reset_phase_id is not None:
        _reset_phase_selection(workspace, reset_phase_id, cleanup_files=True)

    config = PipelineConfig(
        requirements_path=requirements_path,
        workspace_dir=workspace,
        backend=backend,
        model=args.model,
        resume=False,
        phases_to_run=phases_to_run,
        max_prompt_runner_iterations=args.max_iterations,
        debug=args.debug,
        escalation_policy=escalation_policy,
        max_cross_ref_retries=args.max_cross_ref_retries,
    )

    _print_banner("Methodology Runner -- Starting pipeline")
    sys.stdout.write(f"Requirements: {requirements_path}\n")
    if args.application_repo is not None:
        sys.stdout.write(f"Application:  {Path(args.application_repo).resolve()}\n")
        sys.stdout.write(f"Branch:       {branch_name}\n")
    sys.stdout.write(f"Workspace:    {workspace}\n")
    if phases_to_run is None:
        sys.stdout.write("Phases:       all\n")
    else:
        sys.stdout.write(f"Phases:       {', '.join(phases_to_run)}\n")
    if args.model:
        sys.stdout.write(f"Model:        {args.model}\n")
    sys.stdout.write(f"Backend:      {backend}\n")
    sys.stdout.write("\n")
    sys.stdout.flush()

    result = run_pipeline(config)

    _print_pipeline_result(result)

    if result.halted_early or _any_escalated(result.phase_results):
        return EXIT_ESCALATION

    return EXIT_SUCCESS


def _print_pipeline_result(result: object) -> None:
    """Print a human-readable summary of a PipelineResult."""
    from .orchestrator import PipelineResult

    if not isinstance(result, PipelineResult):
        return

    _print_banner("Methodology Runner -- Pipeline Summary")
    sys.stdout.write(f"Workspace:    {result.workspace_dir}\n")
    sys.stdout.write(f"Wall time:    {_format_duration(result.wall_time_seconds)}\n")
    sys.stdout.write(f"Halted early: {result.halted_early}\n")
    if result.halt_reason:
        sys.stdout.write(f"Halt reason:  {result.halt_reason}\n")
    sys.stdout.write(
        "Lifecycle:    outer lifecycle phases are tracked explicitly; "
        "automation covers "
        f"{METHODOLOGY_LIFECYCLE_PHASE_ID} plus LC-002 through LC-006.\n"
    )
    sys.stdout.write("\n")

    _print_phase_table(result.phase_results)

    if result.end_to_end_result is not None:
        xref = result.end_to_end_result
        label = "PASS" if xref.passed else "FAIL"
        sys.stdout.write(f"\nEnd-to-end verification: {label}\n")
        if xref.issues:
            for issue in xref.issues:
                sys.stdout.write(f"  - {issue}\n")

    sys.stdout.write(f"\n{BANNER_RULE}\n")
    sys.stdout.flush()


def _print_phase_table(phase_results: list) -> None:
    """Print a formatted table of phase results."""
    sys.stdout.write(f"{'Phase':<45} {'Status':<30} {'Time':>8}\n")
    sys.stdout.write(f"{'-' * 45} {'-' * 30} {'-' * 8}\n")

    for pr in phase_results:
        label = _STATUS_LABELS.get(pr.status, pr.status.value)
        time_str = _format_duration(pr.wall_time_seconds)
        phase_display = f"{pr.phase_id}: {pr.prompt_runner_file}"
        if len(phase_display) > 44:
            phase_display = phase_display[:41] + "..."
        sys.stdout.write(f"{phase_display:<45} {label:<30} {time_str:>8}\n")

    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Subcommand: status
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> int:
    """Show per-phase status for an existing workspace."""
    workspace = Path(args.workspace_dir).resolve()
    if not workspace.exists():
        _print_error(f"Workspace not found: {workspace}")
        return EXIT_USAGE_ERROR

    state = _load_state(workspace)
    if state is None:
        _print_error(
            f"No state file found in workspace: {workspace}\n"
            f"Expected: {workspace / _STATE_FILENAME}"
        )
        return EXIT_USAGE_ERROR

    _print_banner("Methodology Runner -- Project Status")
    sys.stdout.write(f"Workspace:     {state.workspace_dir}\n")
    if state.change_id:
        sys.stdout.write(f"Change ID:     {state.change_id}\n")
    sys.stdout.write(f"Requirements:  {state.requirements_path}\n")
    sys.stdout.write(f"Started at:    {state.started_at}\n")
    methodology = _find_lifecycle_phase(state, METHODOLOGY_LIFECYCLE_PHASE_ID)
    if methodology is not None and methodology.completed_at:
        sys.stdout.write(f"Methodology completed at: {methodology.completed_at}\n")
    if state.finished_at:
        sys.stdout.write(f"Lifecycle finished at: {state.finished_at}\n")
    if state.current_lifecycle_phase_id:
        sys.stdout.write(
            f"Current lifecycle phase: {state.current_lifecycle_phase_id}\n"
        )
    if (
        state.current_lifecycle_phase_id == METHODOLOGY_LIFECYCLE_PHASE_ID
        and state.current_phase
    ):
        sys.stdout.write(f"Current methodology phase: {state.current_phase}\n")
    if state.model:
        sys.stdout.write(f"Model:         {state.model}\n")
    sys.stdout.write("\n")

    pending_manual = _pending_manual_lifecycle_phase_ids(state)
    if pending_manual:
        sys.stdout.write(
            "Automation boundary: some lifecycle phases remain manual: "
            f"{', '.join(pending_manual)}\n\n"
        )

    sys.stdout.write(
        f"{'Lifecycle Phase ID':<45} {'Status':<30} {'Exec':<10}\n"
    )
    sys.stdout.write(f"{'-' * 45} {'-' * 30} {'-' * 10}\n")
    for lifecycle_phase in state.lifecycle_phases:
        label = _STATUS_LABELS.get(
            lifecycle_phase.status,
            lifecycle_phase.status.value,
        )
        sys.stdout.write(
            f"{lifecycle_phase.phase_id:<45} "
            f"{label:<30} "
            f"{lifecycle_phase.execution_kind:<10}\n"
        )

    if state.current_lifecycle_phase_id == METHODOLOGY_LIFECYCLE_PHASE_ID:
        sys.stdout.write("\nNested methodology phases under LC-001:\n")
        sys.stdout.write(f"{'Phase ID':<40} {'Status':<30} {'Retries':>8}\n")
        sys.stdout.write(f"{'-' * 40} {'-' * 30} {'-' * 8}\n")
        for ps in state.phases:
            label = _STATUS_LABELS.get(ps.status, ps.status.value)
            sys.stdout.write(
                f"{ps.phase_id:<40} {label:<30} {ps.cross_ref_retries:>8}\n"
            )
    else:
        sys.stdout.write(
            "\nNested methodology phases are currently inactive because "
            f"{METHODOLOGY_LIFECYCLE_PHASE_ID} is not the active lifecycle phase.\n"
        )

    if state.phase_results:
        sys.stdout.write("\nCompleted phase results (methodology):\n")
        for phase_id, pr in state.phase_results.items():
            xref_status = ""
            if pr.cross_ref_result is not None:
                xref_status = " (cross-ref: PASS)" if pr.cross_ref_result.passed else " (cross-ref: FAIL)"
            sys.stdout.write(
                f"  {phase_id}: {_STATUS_LABELS.get(pr.status, pr.status.value)}"
                f" -- {pr.iteration_count} iterations, "
                f"{_format_duration(pr.wall_time_seconds)}{xref_status}\n"
            )

    sys.stdout.write(f"\n{BANNER_RULE}\n")
    sys.stdout.flush()

    if _any_escalated(state.phase_results):
        return EXIT_ESCALATION

    return EXIT_SUCCESS


# ---------------------------------------------------------------------------
# Subcommand: resume
# ---------------------------------------------------------------------------

def cmd_resume(args: argparse.Namespace) -> int:
    """Resume a halted or interrupted pipeline run."""
    workspace = Path(args.workspace_dir).resolve()
    if not workspace.exists():
        _print_error(f"Workspace not found: {workspace}")
        return EXIT_USAGE_ERROR

    state = _load_state(workspace)
    if state is None:
        _print_error(
            f"No state file found in workspace: {workspace}\n"
            "Cannot resume a project that has not been started."
        )
        return EXIT_USAGE_ERROR

    current_lifecycle = (
        _find_lifecycle_phase(state, state.current_lifecycle_phase_id)
        if state.current_lifecycle_phase_id
        else None
    )
    if (
        current_lifecycle is not None
        and current_lifecycle.execution_kind == "manual"
        and state.current_lifecycle_phase_id != METHODOLOGY_LIFECYCLE_PHASE_ID
    ):
        pending_manual = _pending_manual_lifecycle_phase_ids(state)
        _print_banner("Methodology Runner -- Resume Blocked At Manual Lifecycle Phase")
        sys.stdout.write(f"Workspace:    {workspace}\n")
        sys.stdout.write(
            "Resume can automate lifecycle phases only when their execution "
            "kind is automated.\n"
        )
        sys.stdout.write(
            f"Current lifecycle phase: {state.current_lifecycle_phase_id}\n"
        )
        if pending_manual:
            sys.stdout.write("Remaining manual lifecycle phases:\n")
            for lifecycle_phase_id in pending_manual:
                sys.stdout.write(f"  - {lifecycle_phase_id}\n")
        sys.stdout.write(f"\n{BANNER_RULE}\n")
        sys.stdout.flush()
        return EXIT_USAGE_ERROR

    # Pre-flight checks for external dependencies
    backend = args.backend or state.backend or resolve_default_backend(
        state.requirements_path, None
    )
    backend_err = check_backend_cli(backend)
    if backend_err is not None:
        _print_error(backend_err)
        return EXIT_USAGE_ERROR

    # Late import so --help works even without prompt-runner installed.
    try:
        from .orchestrator import PipelineConfig, run_pipeline
        from .phases import normalize_phase_selection
    except ImportError as exc:
        _print_error(
            f"Could not import methodology-runner orchestrator: {exc}\n"
            "Make sure prompt-runner is installed: pip install -e tools/prompt-runner"
        )
        return EXIT_USAGE_ERROR

    escalation_policy: EscalationPolicy | None = None
    if args.escalation_policy is not None:
        escalation_policy = EscalationPolicy(
            args.escalation_policy.replace("-", "_")
        )

    phases_to_run: list[str] | None = None
    if args.phases is not None:
        phases_to_run = normalize_phase_selection(
            [p.strip() for p in args.phases.split(",") if p.strip()]
        )
    try:
        reset_phase_id = _validate_resettable_phase_subset(args.reset, phases_to_run)
    except ValueError as exc:
        _print_error(str(exc))
        return EXIT_USAGE_ERROR

    if reset_phase_id is not None:
        _reset_phase_selection(workspace, reset_phase_id, cleanup_files=True)

    config = PipelineConfig(
        requirements_path=state.requirements_path,
        workspace_dir=workspace,
        backend=backend,
        model=args.model or state.model,
        resume=True,
        phases_to_run=phases_to_run,
        max_prompt_runner_iterations=args.max_iterations,
        debug=args.debug,
        escalation_policy=escalation_policy,
        max_cross_ref_retries=args.max_cross_ref_retries,
    )

    _print_banner("Methodology Runner -- Resuming pipeline")
    sys.stdout.write(f"Workspace:    {workspace}\n")
    sys.stdout.write(f"Requirements: {state.requirements_path}\n")
    sys.stdout.write(
        f"Lifecycle:    resuming nested methodology phases inside "
        f"{METHODOLOGY_LIFECYCLE_PHASE_ID}\n"
    )
    if phases_to_run is None:
        sys.stdout.write("Phases:       all incomplete methodology phases\n")
    else:
        sys.stdout.write(f"Phases:       {', '.join(phases_to_run)}\n")
    if config.model:
        sys.stdout.write(f"Model:        {config.model}\n")
    sys.stdout.write(f"Backend:      {config.backend}\n")
    sys.stdout.write("\n")
    sys.stdout.flush()

    result = run_pipeline(config)

    _print_pipeline_result(result)

    if result.halted_early or _any_escalated(result.phase_results):
        return EXIT_ESCALATION

    return EXIT_SUCCESS


# ---------------------------------------------------------------------------
# Subcommand: reset
# ---------------------------------------------------------------------------

def _downstream_phase_ids(phase_id: str) -> list[str]:
    """Return *phase_id* plus all phases that transitively depend on it.

    Walks the predecessor graph defined in phases.py to find every phase
    whose execution depends (directly or indirectly) on *phase_id*.
    """
    from .phases import PHASES

    # Build a reverse dependency map: phase_id -> set of phases that need it
    dependents: dict[str, set[str]] = {p.phase_id: set() for p in PHASES}
    for p in PHASES:
        for pred in p.predecessors:
            dependents.setdefault(pred, set()).add(p.phase_id)

    # BFS from the target phase
    to_reset: list[str] = [phase_id]
    visited: set[str] = {phase_id}
    queue = [phase_id]
    while queue:
        current = queue.pop(0)
        for dep in dependents.get(current, set()):
            if dep not in visited:
                visited.add(dep)
                to_reset.append(dep)
                queue.append(dep)

    return to_reset


def cmd_reset(args: argparse.Namespace) -> int:
    """Reset a phase and all downstream phases to pending status."""
    workspace = Path(args.workspace_dir).resolve()
    if not workspace.exists():
        _print_error(f"Workspace not found: {workspace}")
        return EXIT_USAGE_ERROR

    state = _load_state(workspace)
    if state is None:
        _print_error(
            f"No state file found in workspace: {workspace}\n"
            "Cannot reset a project that has not been started."
        )
        return EXIT_USAGE_ERROR

    phase_id = args.phase

    # Validate the phase ID
    from .phases import PHASE_MAP
    if phase_id not in PHASE_MAP:
        valid = ", ".join(sorted(PHASE_MAP))
        _print_error(f"Unknown phase ID: {phase_id}\nValid IDs: {valid}")
        return EXIT_USAGE_ERROR

    ids_to_reset = _reset_phase_selection(workspace, phase_id, cleanup_files=False)
    reset_count = len(ids_to_reset)

    _print_banner("Methodology Runner -- Phase Reset")
    sys.stdout.write(f"Workspace: {workspace}\n")
    sys.stdout.write(f"Target:    {phase_id}\n")
    sys.stdout.write(f"Reset {reset_count} phase(s) to pending:\n")
    for rid in ids_to_reset:
        sys.stdout.write(f"  - {rid}\n")
    sys.stdout.write(f"\n{BANNER_RULE}\n")
    sys.stdout.flush()

    return EXIT_SUCCESS


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with subcommands."""
    root = argparse.ArgumentParser(
        prog="methodology-runner",
        description=(
            "Orchestrate AI-driven development phases via prompt-runner. "
            "Decomposes a requirements document into 7 methodology phases, "
            "generates prompt-runner files, executes them, and verifies "
            "cross-phase consistency."
        ),
    )
    sub = root.add_subparsers(dest="command", required=True)

    # ── run ──────────────────────────────────────────────────────────────
    run_cmd = sub.add_parser(
        "run",
        help="Execute the methodology pipeline or a selected phase subset.",
    )
    run_cmd.add_argument(
        "requirements_file",
        help="Path to the requirements markdown file.",
    )
    run_cmd.add_argument(
        "--workspace",
        default=None,
        help=(
            "Workspace directory. When --application-repo is set, this is the "
            "change worktree path to create or reuse. Otherwise it defaults to "
            "./runs/<timestamp>-<slugified-requirements-name>/."
        ),
    )
    run_cmd.add_argument(
        "--application-repo",
        default=None,
        help=(
            "Application repository checkout. When provided, methodology-runner "
            "creates or reuses a git worktree for this change before execution."
        ),
    )
    run_cmd.add_argument(
        "--change-id",
        default=None,
        help=(
            "Stable change identifier used to derive the branch/worktree name "
            "when --application-repo is provided."
        ),
    )
    run_cmd.add_argument(
        "--branch-name",
        default=None,
        help=(
            "Explicit branch name to use with --application-repo. Defaults to "
            "the requirements filename stem, optionally prefixed by --change-id."
        ),
    )
    run_cmd.add_argument(
        "--backend",
        choices=["claude", "codex"],
        default=None,
        help=(
            "Agent backend to use for prompt generation, prompt-runner, and "
            "verification. Overrides [run].backend from prompt-runner.toml; "
            "defaults to claude if neither is set."
        ),
    )
    run_cmd.add_argument(
        "--model",
        default=None,
        help="Model to use with the selected backend CLI.",
    )
    run_cmd.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Override max prompt-runner iterations per prompt.",
    )
    run_cmd.add_argument(
        "--debug",
        nargs="?",
        const=3,
        default=0,
        type=int,
        metavar="N",
        help=(
            "Enable depth-limited debug tracing. Passed through to "
            "prompt-runner. Default depth is 3 when the flag is present "
            "without a value."
        ),
    )
    run_cmd.add_argument(
        "--phases",
        default=None,
        help=(
            "Comma-separated full phase IDs to run (e.g. "
            "PH-000-requirements-inventory,PH-001-feature-specification). "
            "The selected subset is executed in methodology order."
        ),
    )
    run_cmd.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Before running, reset and clean the selected phase and downstream "
            "artifacts. Requires exactly one phase via --phases."
        ),
    )
    run_cmd.add_argument(
        "--escalation-policy",
        default=None,
        choices=["halt", "flag-and-continue", "human-review"],
        help="Override the escalation policy for all phases.",
    )
    run_cmd.add_argument(
        "--max-cross-ref-retries",
        type=int,
        default=2,
        help="Max retries for cross-reference verification failures (default: 2).",
    )
    run_cmd.set_defaults(func=cmd_run)

    # ── status ───────────────────────────────────────────────────────────
    status_cmd = sub.add_parser(
        "status",
        help="Show per-phase status for an existing workspace.",
    )
    status_cmd.add_argument(
        "workspace_dir",
        help="Path to the methodology-runner workspace directory.",
    )
    status_cmd.set_defaults(func=cmd_status)

    # ── resume ───────────────────────────────────────────────────────────
    resume_cmd = sub.add_parser(
        "resume",
        help="Resume a halted or interrupted pipeline run or selected phase subset.",
    )
    resume_cmd.add_argument(
        "workspace_dir",
        help="Path to the methodology-runner workspace directory.",
    )
    resume_cmd.add_argument(
        "--backend",
        choices=["claude", "codex"],
        default=None,
        help="Agent backend to use (defaults to the backend stored in state).",
    )
    resume_cmd.add_argument(
        "--model",
        default=None,
        help="Model to use (overrides the saved model from the prior run).",
    )
    resume_cmd.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Override max prompt-runner iterations per prompt.",
    )
    resume_cmd.add_argument(
        "--debug",
        nargs="?",
        const=3,
        default=0,
        type=int,
        metavar="N",
        help=(
            "Enable depth-limited debug tracing. Passed through to "
            "prompt-runner. Default depth is 3 when the flag is present "
            "without a value."
        ),
    )
    resume_cmd.add_argument(
        "--phases",
        default=None,
        help=(
            "Comma-separated full phase IDs to run (e.g. "
            "PH-000-requirements-inventory,PH-001-feature-specification). "
            "The selected subset is executed in methodology order."
        ),
    )
    resume_cmd.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Before resuming, reset and clean the selected phase and downstream "
            "artifacts. Requires exactly one phase via --phases."
        ),
    )
    resume_cmd.add_argument(
        "--escalation-policy",
        default=None,
        choices=["halt", "flag-and-continue", "human-review"],
        help="Override the escalation policy for all phases.",
    )
    resume_cmd.add_argument(
        "--max-cross-ref-retries",
        type=int,
        default=2,
        help="Max retries for cross-reference verification failures (default: 2).",
    )
    resume_cmd.set_defaults(func=cmd_resume)

    # ── reset ────────────────────────────────────────────────────────────
    reset_cmd = sub.add_parser(
        "reset",
        help="Reset a phase and all downstream phases to pending.",
    )
    reset_cmd.add_argument(
        "workspace_dir",
        help="Path to the methodology-runner workspace directory.",
    )
    reset_cmd.add_argument(
        "--phase",
        required=True,
        help="Phase ID to reset (e.g. PH-004-interface-contracts).",
    )
    reset_cmd.set_defaults(func=cmd_reset)

    return root


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        0 on success, 1 on escalation/halt, 2 on usage error.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted.\n")
        return EXIT_ESCALATION
    except Exception as exc:
        _print_error(str(exc))
        return EXIT_ESCALATION
