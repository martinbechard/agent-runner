"""Pipeline orchestrator for methodology-runner.

Sequences the methodology phases, manages the workspace and git,
invokes prompt-runner with the checked-in phase prompt modules, runs
cross-reference verification, and handles escalation and resumption.

See .methodology/docs/design/components/CD-002-methodology-runner.md Sections 5-9.

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
import fcntl
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from typing import TYPE_CHECKING

from .models import (
    CrossRefResult,
    EscalationPolicy,
    PhaseResult,
    PhaseState,
    PhaseStatus,
    ProjectState,
)
from .phases import (
    PHASES,
    PHASE_MAP,
    get_phase,
    normalize_phase_selection,
    resolve_input_sources,
)
from .cross_reference import (
    CrossReferenceError,
    verify_end_to_end,
    verify_phase_cross_references,
)
from prompt_runner.client_factory import make_client

if TYPE_CHECKING:
    from .models import PhaseConfig
    from prompt_runner.client_types import AgentClient


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CROSS_REF_RETRIES = 2
"""Default maximum re-generation attempts when cross-ref verification fails."""

METHODOLOGY_DIR = ".methodology-runner"
"""Hidden directory within the workspace for methodology control state."""

RUN_FILES_DIRNAME = ".run-files"
"""Shared execution-artifact root in the workspace."""

METHODOLOGY_RUN_FILES_SUBDIR = "methodology-runner"
"""Methodology-owned artifacts within the shared .run-files tree."""

STATE_FILENAME = "state.json"
"""Name of the project-state JSON file inside METHODOLOGY_DIR."""

SUMMARY_FILENAME = "summary.txt"
"""Human-readable summary written after pipeline completion."""

PROCESS_LOG_FILENAME = "process.log"
"""Debug/process log for methodology-runner itself."""

REQUIREMENTS_DEST = "docs/requirements"
"""Workspace-relative directory where the raw requirements are copied."""

RAW_REQUIREMENTS_FILENAME = "raw-requirements.md"
"""Filename for the copied requirements document."""

LOCK_FILENAME = "run.lock"
"""Workspace lock file — prevents concurrent methodology-runner instances
on the same workspace. Uses fcntl.flock so the OS auto-releases on crash."""


class WorkspaceLockError(RuntimeError):
    """Raised when another methodology-runner instance holds the workspace lock."""


class _WorkspaceLock:
    """Exclusive file lock on a workspace directory.

    Uses ``fcntl.flock`` with ``LOCK_NB`` (non-blocking). If another
    process holds the lock, raises :class:`WorkspaceLockError`
    immediately. The OS releases the lock automatically if the holding
    process dies — no stale-lock cleanup needed.
    """

    def __init__(self, workspace: Path) -> None:
        self._lock_path = workspace / METHODOLOGY_DIR / LOCK_FILENAME
        self._fd: int | None = None

    def acquire(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(self._lock_path, "w")
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            self._fd.close()
            self._fd = None
            raise WorkspaceLockError(
                f"Another methodology-runner instance is already running "
                f"on this workspace.\n"
                f"Lock file: {self._lock_path}\n\n"
                f"Wait for it to finish, or kill the stale process."
            )
        import os
        self._fd.write(str(os.getpid()))
        self._fd.flush()

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            self._fd.close()
            self._fd = None
            self._lock_path.unlink(missing_ok=True)


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
    backend: str = "codex"
    model: str | None = None
    resume: bool = False
    phases_to_run: list[str] | None = None
    max_prompt_runner_iterations: int | None = None
    debug: int = 0
    """When > 0, enable depth-limited prompt-runner tracing in per-phase
    process logs and any methodology-owned debug logging."""
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
    execution_scope: str = "all-phases"
    selected_phase_ids: list[str] | None = None


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


def _process_log_path(workspace: Path) -> Path:
    return workspace / METHODOLOGY_DIR / PROCESS_LOG_FILENAME


def _append_process_log(workspace: Path, source: str, message: str) -> None:
    path = _process_log_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(path, "a", encoding="utf-8") as log:
        for line in message.splitlines(keepends=True):
            log.write(f"{timestamp} [{source}] {line}")
        if message and not message.endswith("\n"):
            log.write("\n")


@contextmanager
def _debug_trace(workspace: Path, debug_depth: int):
    if debug_depth <= 0:
        yield
        return

    package_root = Path(__file__).resolve().parent
    local = threading.local()

    def tracer(frame, event, arg):
        filename = frame.f_code.co_filename
        if not filename:
            return tracer
        try:
            frame_path = Path(filename).resolve()
        except OSError:
            return tracer
        if package_root not in frame_path.parents and frame_path != package_root:
            return tracer

        stack = getattr(local, "stack", [])
        if event == "call":
            stack = stack + [frame]
            local.stack = stack
            if len(stack) <= debug_depth:
                rel = frame_path.relative_to(package_root)
                _append_process_log(
                    workspace,
                    "debug-trace",
                    f"call depth={len(stack)} {rel}:{frame.f_lineno} {frame.f_code.co_name}()",
                )
            return tracer
        if event in {"return", "exception"}:
            if not stack:
                return tracer
            depth = len(stack)
            if depth <= debug_depth:
                rel = frame_path.relative_to(package_root)
                label = "return" if event == "return" else "exception"
                _append_process_log(
                    workspace,
                    "debug-trace",
                    f"{label} depth={depth} {rel}:{frame.f_lineno} {frame.f_code.co_name}()",
                )
            local.stack = stack[:-1]
            return tracer
        return tracer

    previous_profile = sys.getprofile()
    sys.setprofile(tracer)
    threading.setprofile(tracer)
    _append_process_log(workspace, "debug-trace", f"enabled depth={debug_depth}")
    try:
        yield
    finally:
        sys.setprofile(previous_profile)
        threading.setprofile(None)
        _append_process_log(workspace, "debug-trace", "disabled")


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


def _summary_path(workspace: Path) -> Path:
    """Return the methodology summary path under the shared .run-files tree."""
    return (
        workspace
        / RUN_FILES_DIRNAME
        / METHODOLOGY_RUN_FILES_SUBDIR
        / SUMMARY_FILENAME
    )


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
        backend=config.backend,
        execution_scope=(
            "selected-phases"
            if config.phases_to_run is not None
            else "all-phases"
        ),
        selected_phase_ids=(
            list(config.phases_to_run)
            if config.phases_to_run is not None
            else None
        ),
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
# Prompt-runner invocation (CD-002 Section 6)
# ---------------------------------------------------------------------------

def _invoke_prompt_runner_library(
    md_file: Path,
    workspace: Path,
    run_id: str,
    config: PipelineConfig,
    claude_client: AgentClient | None = None,
    generator_prelude: str | None = None,
    judge_prelude: str | None = None,
    placeholder_values: dict[str, str] | None = None,
) -> tuple[bool, int, str | None]:
    """Invoke prompt-runner via direct library call (preferred).

    Returns ``(success, total_iteration_count, error_message_or_none)``.
    """
    from prompt_runner.parser import parse_file
    from prompt_runner.runner import RunConfig
    from prompt_runner.runner import run_pipeline as pr_run_pipeline

    if claude_client is None:
        claude_client = make_client(config.backend)

    pairs = parse_file(md_file)
    max_iters = config.max_prompt_runner_iterations or 3

    pr_config = RunConfig(
        backend=config.backend,
        max_iterations=max_iters,
        model=config.model,
        debug=config.debug,
        generator_prelude=generator_prelude,
        judge_prelude=judge_prelude,
        include_project_organiser=False,
        placeholder_values=placeholder_values or {},
        run_id_override=run_id,
    )

    pr_result = pr_run_pipeline(
        pairs=pairs,
        run_dir=workspace,
        config=pr_config,
        claude_client=claude_client,
        source_file=md_file,
        source_project_dir=workspace,
        worktree_dir=workspace,
    )

    total_iterations = sum(
        len(pr.iterations) for pr in pr_result.prompt_results
    )

    if pr_result.halted_early:
        return False, total_iterations, pr_result.halt_reason

    return True, total_iterations, None


def _invoke_prompt_runner(
    md_file: Path,
    workspace: Path,
    run_id: str,
    config: PipelineConfig,
    claude_client: AgentClient | None = None,
    generator_prelude: str | None = None,
    judge_prelude: str | None = None,
    placeholder_values: dict[str, str] | None = None,
) -> tuple[bool, int, str | None]:
    """Invoke prompt-runner via the in-process library path.

    Returns ``(success, iteration_count, error_message_or_none)``.
    """
    return _invoke_prompt_runner_library(
        md_file, workspace, run_id, config, claude_client,
        generator_prelude=generator_prelude,
        judge_prelude=judge_prelude,
        placeholder_values=placeholder_values,
    )


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
    """Return the methodology phase-artifact directory under shared .run-files."""
    return workspace / RUN_FILES_DIRNAME / phase_config.phase_id


def _resolve_phase_prompt_module_path(phase_config: PhaseConfig) -> Path:
    """Return the checked-in prompt module path for a phase."""
    if not phase_config.prompt_module_path:
        raise RuntimeError(
            f"No prompt module is registered for {phase_config.phase_id}"
        )
    path = Path(phase_config.prompt_module_path).resolve()
    if not path.exists():
        raise RuntimeError(
            f"Prompt module for {phase_config.phase_id} does not exist: {path}"
        )
    return path


def _phase_placeholder_values(phase_config: PhaseConfig) -> dict[str, str]:
    """Return prompt-runner placeholder bindings for a phase."""
    values: dict[str, str] = {}
    if phase_config.phase_id == "PH-000-requirements-inventory":
        values["raw_requirements_path"] = (
            f"{REQUIREMENTS_DEST}/{RAW_REQUIREMENTS_FILENAME}"
        )
    if phase_config.phase_id == "PH-006-incremental-implementation":
        repo_root = Path(__file__).resolve().parents[4]
        prompt_runner_pythonpath = repo_root / ".prompt-runner" / "src" / "cli"
        values["prompt_runner_command"] = (
            f'PYTHONPATH="{prompt_runner_pythonpath}" '
            f'"{sys.executable}" -m prompt_runner'
        )
    return values


def _cross_ref_retry_guidance(result: CrossRefResult) -> str:
    """Render cross-reference findings as retry guidance text."""
    lines = [
        "Cross-reference retry guidance:",
        "The previous phase output failed cross-reference verification.",
        "Address the following issues in this retry execution:",
    ]
    if result.issues:
        for issue in result.issues:
            lines.append(f"- {issue}")
    else:
        lines.append("- Cross-reference failed without a specific issue list.")
    return "\n".join(lines) + "\n"


def _write_retry_guidance_artifact(
    destination: Path,
    guidance: str,
) -> Path:
    """Write retry guidance to a run-local artifact for traceability."""
    destination.write_text(guidance, encoding="utf-8")
    return destination


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
    claude_client: AgentClient | None = None,
    cross_ref_only: bool = False,
) -> PhaseResult:
    """Execute one methodology phase end-to-end.

    Handles prompt-module selection, prompt-runner invocation, cross-reference
    verification with retry guidance, state updates, and git
    commits.

    When *cross_ref_only* is True (resume of a phase that already passed
    prompt-runner), skips steps 1-6 and runs only cross-ref verification.
    """
    phase_id = phase_config.phase_id
    ps = _find_phase_state(state, phase_id)
    t0 = time.monotonic()

    run_dir = _phase_run_dir(workspace, phase_config)
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        prompt_file = _resolve_phase_prompt_module_path(phase_config)
    except RuntimeError as exc:
        ps.status = PhaseStatus.FAILED
        save_project_state(state, workspace)
        return _make_failed_result(
            phase_id,
            run_dir / "prompt-file.md",
            0,
            time.monotonic() - t0,
            str(exc),
        )
    cross_ref_path = run_dir / "cross-ref-result.json"
    policy = _effective_escalation_policy(config, phase_config)
    max_retries = config.max_cross_ref_retries
    iteration_count = 0
    placeholder_values = _phase_placeholder_values(phase_config)

    # ------------------------------------------------------------------
    # Steps 1-6: prompt-runner against the checked-in prompt module
    # (skip if cross_ref_only)
    # ------------------------------------------------------------------
    if not cross_ref_only:
        # Step 1-2: mark running
        ps.status = PhaseStatus.RUNNING
        ps.started_at = _iso_now()
        state.current_phase = phase_id
        save_project_state(state, workspace)

        ps.prompt_file = str(prompt_file)
        save_project_state(state, workspace)

        # Step 3-4: invoke prompt-runner.
        # The directory basename becomes prompt-runner's `run_id`, which
        # feeds uuid5-derived claude session IDs. Including the phase
        # number keeps those session IDs unique across phases — without
        # it, every phase's prompt-1 gen/jud sessions collide on the
        # same UUID and claude rejects the second invocation with
        # "Session ID ... is already in use".
        pr_run_id = phase_id
        success, iteration_count, pr_error = _invoke_prompt_runner(
            prompt_file, workspace, pr_run_id, config, claude_client,
            placeholder_values=placeholder_values,
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

        # Step 5: mark prompt-runner passed (only reached when success)
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
                backend=config.backend,
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

        # Retry: reuse the same checked-in prompt module with runtime guidance
        # derived from cross-reference feedback.
        if attempt >= max_retries:
            break

        guidance = _cross_ref_retry_guidance(cross_ref_result)
        _write_retry_guidance_artifact(
            run_dir / f"retry-guidance-{attempt + 1}.txt",
            guidance,
        )

        # Re-run prompt-runner on the same prompt module with retry guidance.
        # Phase number included so the retry run_id differs from other phases'
        # retries (same session-collision concern as the main invocation above).
        retry_run_id = f"{phase_id}-retry-{attempt + 1}"
        success, extra_iters, pr_error = _invoke_prompt_runner(
            prompt_file, workspace, retry_run_id, config, claude_client,
            generator_prelude=guidance,
            judge_prelude=guidance,
            placeholder_values=placeholder_values,
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
    """Write a human-readable summary to .run-files/methodology-runner/summary.txt.

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
    if result.execution_scope == "selected-phases":
        selected = ", ".join(result.selected_phase_ids or [])
        lines.append(f"Execution scope: selected phases ({selected})")
    else:
        lines.append("Execution scope: all phases")
    if result.halt_reason:
        lines.append(f"Halt reason:     {result.halt_reason}")

    target_phase_ids = (
        list(result.selected_phase_ids)
        if result.selected_phase_ids is not None
        else [phase.phase_id for phase in PHASES]
    )
    completed_count = sum(
        1 for pr in result.phase_results
        if pr.phase_id in target_phase_ids and pr.status == PhaseStatus.COMPLETED
    )
    lines.append(
        f"Phases completed in scope: {completed_count}/{len(target_phase_ids)}"
    )
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

    summary_path = _summary_path(workspace)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline(
    config: PipelineConfig,
    *,
    claude_client: AgentClient | None = None,
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
        Optional injected backend client (for testing).  When None,
        a real backend client is created internally.
    """
    t0 = time.monotonic()

    # ---- workspace and state ----
    workspace = initialize_workspace(config)

    # ---- workspace lock (prevent concurrent instances) ----
    lock = _WorkspaceLock(workspace)
    with _debug_trace(workspace, config.debug):
        try:
            lock.acquire()
        except WorkspaceLockError as exc:
            return PipelineResult(
                workspace_dir=workspace,
                phase_results=[],
                halted_early=True,
                halt_reason=str(exc),
                end_to_end_result=None,
                wall_time_seconds=time.monotonic() - t0,
                execution_scope=(
                    "selected-phases"
                    if config.phases_to_run is not None
                    else "all-phases"
                ),
                selected_phase_ids=(
                    list(config.phases_to_run)
                    if config.phases_to_run is not None
                    else None
                ),
            )

        try:
            state: ProjectState | None = None
            if config.resume:
                state = load_project_state(workspace)

            if state is None:
                state = _create_initial_state(workspace, config)
                save_project_state(state, workspace)
            else:
                state.execution_scope = (
                    "selected-phases"
                    if config.phases_to_run is not None
                    else "all-phases"
                )
                state.selected_phase_ids = (
                    list(config.phases_to_run)
                    if config.phases_to_run is not None
                    else None
                )
                save_project_state(state, workspace)

            # ---- backend client ----
            if claude_client is None:
                claude_client = make_client(config.backend)

            # ---- determine phases ----
            phases_to_run: list[PhaseConfig] = list(PHASES)
            if config.phases_to_run is not None:
                phases_to_run = [
                    get_phase(pid)
                    for pid in normalize_phase_selection(config.phases_to_run)
                ]

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
                    phase,
                    state,
                    workspace,
                    config,
                    claude_client=claude_client,
                    cross_ref_only=cross_ref_only,
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
                        execution_scope=state.execution_scope,
                        selected_phase_ids=(
                            list(state.selected_phase_ids)
                            if state.selected_phase_ids is not None
                            else None
                        ),
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
                        backend=config.backend,
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
            state.finished_at = _iso_now() if all_done and not halted_early else None
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
                execution_scope=state.execution_scope,
                selected_phase_ids=(
                    list(state.selected_phase_ids)
                    if state.selected_phase_ids is not None
                    else None
                ),
            )

            # Final summary with end-to-end results and halt status
            write_summary(workspace, pipeline_result)
            return pipeline_result
        finally:
            lock.release()
