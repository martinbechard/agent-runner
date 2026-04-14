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

See docs/design/components/CD-002-methodology-runner.md Section 10.6.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    EscalationPolicy,
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


def _format_duration(seconds: float) -> str:
    """Format seconds as a human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds) // 60
    remaining = seconds - (minutes * 60)
    return f"{minutes}m {remaining:.1f}s"


def _check_prompt_runner_cli() -> str | None:
    """Return an error message if ``prompt-runner`` is not on PATH."""
    if shutil.which("prompt-runner") is None:
        return (
            "The 'prompt-runner' CLI is not on PATH.\n"
            "Install it with: pip install -e .[dev]"
        )
    return None


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

    workspace = _resolve_workspace(args.workspace, requirements_path)

    # Late import so --help works even without prompt-runner installed.
    try:
        from .orchestrator import PipelineConfig, run_pipeline
        from .phases import normalize_phase_selection
    except ImportError as exc:
        _print_error(
            f"Could not import methodology-runner orchestrator: {exc}\n"
            "Make sure prompt-runner is installed: pip install -e .[dev]"
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

    config = PipelineConfig(
        requirements_path=requirements_path,
        workspace_dir=workspace,
        backend=backend,
        model=args.model,
        resume=False,
        phases_to_run=phases_to_run,
        max_prompt_runner_iterations=args.max_iterations,
        escalation_policy=escalation_policy,
        max_cross_ref_retries=args.max_cross_ref_retries,
    )

    _print_banner("Methodology Runner -- Starting pipeline")
    sys.stdout.write(f"Requirements: {requirements_path}\n")
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
    sys.stdout.write(f"Requirements:  {state.requirements_path}\n")
    sys.stdout.write(f"Started at:    {state.started_at}\n")
    if state.finished_at:
        sys.stdout.write(f"Finished at:   {state.finished_at}\n")
    if state.current_phase:
        sys.stdout.write(f"Current phase: {state.current_phase}\n")
    if state.model:
        sys.stdout.write(f"Model:         {state.model}\n")
    sys.stdout.write("\n")

    # Phase state table
    sys.stdout.write(f"{'Phase ID':<40} {'Status':<30} {'Retries':>8}\n")
    sys.stdout.write(f"{'-' * 40} {'-' * 30} {'-' * 8}\n")

    for ps in state.phases:
        label = _STATUS_LABELS.get(ps.status, ps.status.value)
        sys.stdout.write(
            f"{ps.phase_id:<40} {label:<30} {ps.cross_ref_retries:>8}\n"
        )

    # Phase results (if any)
    if state.phase_results:
        sys.stdout.write("\nCompleted phase results:\n")
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
            "Make sure prompt-runner is installed: pip install -e .[dev]"
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

    config = PipelineConfig(
        requirements_path=state.requirements_path,
        workspace_dir=workspace,
        backend=backend,
        model=args.model or state.model,
        resume=True,
        phases_to_run=phases_to_run,
        max_prompt_runner_iterations=args.max_iterations,
        escalation_policy=escalation_policy,
        max_cross_ref_retries=args.max_cross_ref_retries,
        rerun_selector=args.rerun_selector,
    )

    _print_banner("Methodology Runner -- Resuming pipeline")
    sys.stdout.write(f"Workspace:    {workspace}\n")
    sys.stdout.write(f"Requirements: {state.requirements_path}\n")
    if phases_to_run is None:
        sys.stdout.write("Phases:       all\n")
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

    # Find all phases to reset (target + downstream)
    ids_to_reset = _downstream_phase_ids(phase_id)

    reset_count = 0
    for ps in state.phases:
        if ps.phase_id in ids_to_reset:
            ps.status = PhaseStatus.PENDING
            ps.started_at = None
            ps.completed_at = None
            ps.cross_ref_retries = 0
            ps.git_commit = None
            reset_count += 1

    # Remove corresponding phase results
    for rid in ids_to_reset:
        state.phase_results.pop(rid, None)

    # Clear finished_at since the project is no longer complete
    state.finished_at = None

    # Persist
    from .orchestrator import save_project_state
    save_project_state(state, workspace)

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
            "Workspace directory. "
            "Default: ./runs/<timestamp>-<slugified-requirements-name>/"
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
        "--phases",
        default=None,
        help=(
            "Comma-separated full phase IDs to run (e.g. "
            "PH-000-requirements-inventory,PH-001-feature-specification). "
            "The selected subset is executed in methodology order."
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
        "--phases",
        default=None,
        help=(
            "Comma-separated full phase IDs to run (e.g. "
            "PH-000-requirements-inventory,PH-001-feature-specification). "
            "The selected subset is executed in methodology order."
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
    resume_cmd.add_argument(
        "--rerun-selector",
        action="store_true",
        help=(
            "On resume, force the Skill-Selector to re-run for the "
            "halted phase even if a phase-NNN-skills.yaml already "
            "exists.  Default: reuse the existing manifest to preserve "
            "deterministic semantics within a run."
        ),
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
