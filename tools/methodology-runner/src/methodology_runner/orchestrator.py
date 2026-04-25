"""Pipeline orchestrator for methodology-runner.

Sequences the methodology phases, manages the workspace and git,
invokes prompt-runner with the checked-in phase prompt modules, runs
cross-reference verification, and handles escalation and resumption.

See tools/methodology-runner/docs/design/components/CD-002-methodology-runner.md
Sections 5-9.

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
import shlex
import shutil
import subprocess
import sys
import threading
import time
import yaml
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from typing import TYPE_CHECKING

from .models import (
    CrossRefResult,
    EscalationPolicy,
    METHODOLOGY_LIFECYCLE_PHASE_ID,
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

CHANGE_RECORD_ROOT = "docs/changes"
"""Root for preserved per-change records."""

TARGET_MERGE_HANDOFF_FILENAME = "target-merge-handoff.json"
"""Filename for the target-merge handoff written when target merge is skipped."""

TARGET_MERGE_PENDING_STATUS = "target_merge_pending"
"""Status written into the target-merge handoff."""

STEADY_STATE_DOC_ROOTS = (
    "docs/features",
    "docs/design",
    "docs/contracts",
)
"""Markdown doc roots that survive beyond one methodology run."""

_CHANGE_RECORD_ARTIFACT_MAP: tuple[tuple[str, str], ...] = (
    (f"{REQUIREMENTS_DEST}/{RAW_REQUIREMENTS_FILENAME}", "request/raw-requirements.md"),
    ("docs/requirements/requirements-inventory.yaml", "analysis/requirements-inventory.yaml"),
    (
        "docs/requirements/requirements-inventory-coverage.yaml",
        "analysis/requirements-inventory-coverage.yaml",
    ),
    ("docs/features/feature-specification.yaml", "analysis/feature-specification.yaml"),
    ("docs/architecture/architecture-design.yaml", "analysis/architecture-design.yaml"),
    ("docs/design/solution-design.yaml", "analysis/solution-design.yaml"),
    ("docs/design/interface-contracts.yaml", "analysis/interface-contracts.yaml"),
    ("docs/simulations/simulation-definitions.yaml", "analysis/simulation-definitions.yaml"),
    ("docs/implementation/implementation-workflow.md", "execution/implementation-workflow.md"),
    (
        "docs/implementation/implementation-run-report.yaml",
        "execution/implementation-run-report.yaml",
    ),
    ("docs/verification/verification-report.yaml", "verification/verification-report.yaml"),
)
"""In-run artifacts promoted into docs/changes/<change-id>/..."""

_RUNNER_STATE_ARTIFACT_MAP: tuple[tuple[str, str], ...] = (
    (f"{METHODOLOGY_DIR}/{STATE_FILENAME}", "execution/methodology-state.json"),
    (
        f"{RUN_FILES_DIRNAME}/{METHODOLOGY_RUN_FILES_SUBDIR}/{SUMMARY_FILENAME}",
        "execution/methodology-summary.txt",
    ),
)
"""Runner-managed state we preserve before deleting workspace control data."""

_TEMP_WORKING_PATHS: tuple[str, ...] = (
    f"{REQUIREMENTS_DEST}/{RAW_REQUIREMENTS_FILENAME}",
    "docs/requirements/requirements-inventory.yaml",
    "docs/requirements/requirements-inventory-coverage.yaml",
    "docs/features/feature-specification.yaml",
    "docs/architecture/architecture-design.yaml",
    "docs/design/solution-design.yaml",
    "docs/design/interface-contracts.yaml",
    "docs/simulations/simulation-definitions.yaml",
    "docs/implementation/implementation-workflow.md",
    "docs/implementation/implementation-run-report.yaml",
    "docs/verification/verification-report.yaml",
)
"""Temporary phase-working files removed once preserved and integrated."""

_FINAL_CLEANUP_PATHS: tuple[str, ...] = (
    METHODOLOGY_DIR,
    RUN_FILES_DIRNAME,
    "cross-ref-logs",
    "timeline.html",
    "timeline-implementation-workflow.html",
)
"""Intermediate execution state removed before the final repo commit."""

_TRANSIENT_DELIVERY_DIR_NAMES = frozenset({
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "htmlcov",
})
"""Generated cache/build directories that must not be delivered as app code."""

_TRANSIENT_DELIVERY_FILE_NAMES = frozenset({
    ".coverage",
    "coverage.xml",
})
"""Generated cache/report files that must not be delivered as app code."""

_TRANSIENT_DELIVERY_FILE_SUFFIXES = (".pyc", ".pyo")
"""Generated Python bytecode suffixes excluded from final integration."""


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
    PhaseStatus.SKIPPED,
})
"""Phase statuses that count as 'done' for dependency and skip checks."""

PHASE_5_SIMULATIONS_ID = "PH-005-intelligent-simulations"
"""Phase id for compile-checked component simulation generation."""

PHASE_5_NO_TARGETS_SKIP_REASON = (
    "Skipped PH-005 because architecture declares no simulation targets."
)
"""Run-artifact reason recorded when PH-005 has no simulation work."""


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
    skip_target_merge: bool = False
    target_branch: str | None = None
    base_commit: str | None = None


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


def _git_status_porcelain(workspace: Path) -> str:
    """Return porcelain git status for *workspace*."""
    return _git(workspace, "status", "--porcelain")


def _git_branch_exists(workspace: Path, branch: str) -> bool:
    """Return whether *branch* exists locally."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _git_current_branch(workspace: Path) -> str:
    """Return the current git branch name for *workspace*."""
    return _git(workspace, "branch", "--show-current")


def _git_worktree_entries(workspace: Path) -> list[dict[str, str]]:
    """Return parsed `git worktree list --porcelain` entries."""
    output = _git(workspace, "worktree", "list", "--porcelain")
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        else:
            current[key] = value
    if current:
        entries.append(current)
    return entries


def _target_integration_branch(workspace: Path, source_branch: str) -> str:
    """Choose the branch that should receive the finalized change."""
    for candidate in ("main", "master"):
        if candidate != source_branch and _git_branch_exists(workspace, candidate):
            return candidate
    return source_branch


def _find_branch_worktree_path(workspace: Path, branch: str) -> Path | None:
    """Return the path of an existing worktree that has *branch* checked out."""
    for entry in _git_worktree_entries(workspace):
        if entry.get("branch") == branch:
            return Path(entry["path"]).resolve()
    return None


def _resolve_target_branch(
    workspace: Path,
    source_branch: str,
    configured_target_branch: str | None,
) -> str:
    """Return the configured target branch or the default integration branch."""
    if configured_target_branch:
        return configured_target_branch
    return _target_integration_branch(workspace, source_branch)


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


def _find_lifecycle_phase_state(
    state: ProjectState,
    phase_id: str,
) -> "LifecyclePhaseState":
    """Locate the LifecyclePhaseState for *phase_id* within *state*."""
    from .models import LifecyclePhaseState

    for lifecycle_phase in state.lifecycle_phases:
        if lifecycle_phase.phase_id == phase_id:
            return lifecycle_phase
    raise ValueError(f"Lifecycle phase {phase_id} not found in project state")


def _pending_manual_lifecycle_phase_ids(state: ProjectState) -> list[str]:
    """Return manual lifecycle phases that remain after automated execution."""
    return [
        phase.phase_id
        for phase in state.lifecycle_phases
        if (
            phase.phase_id != METHODOLOGY_LIFECYCLE_PHASE_ID
            and phase.execution_kind == "manual"
            and phase.status == PhaseStatus.PENDING
        )
    ]


def _activate_methodology_execution_lifecycle(state: ProjectState) -> None:
    """Mark LC-000 complete and LC-001 active before PH-* execution starts."""
    started_at = state.started_at or _iso_now()
    preparation = _find_lifecycle_phase_state(state, "LC-000-change-preparation")
    if preparation.status == PhaseStatus.PENDING:
        preparation.status = PhaseStatus.COMPLETED
        preparation.started_at = started_at
        preparation.completed_at = started_at

    methodology = _find_lifecycle_phase_state(state, METHODOLOGY_LIFECYCLE_PHASE_ID)
    if methodology.status != PhaseStatus.COMPLETED:
        methodology.status = PhaseStatus.IN_PROGRESS
        if methodology.started_at is None:
            methodology.started_at = started_at
        methodology.completed_at = None
        state.current_lifecycle_phase_id = methodology.phase_id


def _finalize_lifecycle_after_methodology_run(
    state: ProjectState,
    *,
    halted_early: bool,
    in_scope_done: bool,
    all_done: bool,
) -> None:
    """Synchronize LC-001 and outer lifecycle progression after PH-* execution."""
    methodology = _find_lifecycle_phase_state(state, METHODOLOGY_LIFECYCLE_PHASE_ID)
    if halted_early:
        methodology.status = (
            PhaseStatus.ESCALATED
            if any(ps.status == PhaseStatus.ESCALATED for ps in state.phases)
            else PhaseStatus.FAILED
        )
        methodology.completed_at = None
        state.current_lifecycle_phase_id = methodology.phase_id
        return

    if not in_scope_done or not all_done:
        methodology.status = PhaseStatus.IN_PROGRESS
        methodology.completed_at = None
        state.current_lifecycle_phase_id = methodology.phase_id
        return

    methodology.status = PhaseStatus.COMPLETED
    methodology.completed_at = _iso_now()
    pending_next = [
        phase.phase_id
        for phase in state.lifecycle_phases
        if phase.phase_id != METHODOLOGY_LIFECYCLE_PHASE_ID
        and phase.status == PhaseStatus.PENDING
    ]
    state.current_lifecycle_phase_id = pending_next[0] if pending_next else None


def _iso_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _change_record_root(workspace: Path, change_id: str) -> Path:
    """Return docs/changes/<change-id> inside the application worktree."""
    return workspace / CHANGE_RECORD_ROOT / change_id


def _copy_preserved_artifact(src: Path, dest: Path) -> None:
    """Copy one preserved artifact, creating parent directories as needed."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _remove_transient_delivery_artifacts(workspace: Path) -> None:
    """Remove generated caches and bytecode before committing delivered changes."""
    for path in sorted(workspace.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if ".git" in path.parts:
            continue
        if path.is_dir() and path.name in _TRANSIENT_DELIVERY_DIR_NAMES:
            shutil.rmtree(path, ignore_errors=True)
            continue
        if path.is_file() and (
            path.name in _TRANSIENT_DELIVERY_FILE_NAMES
            or path.name.endswith(_TRANSIENT_DELIVERY_FILE_SUFFIXES)
        ):
            path.unlink(missing_ok=True)


def _slugify_doc_segment(value: str) -> str:
    """Return a stable kebab-case segment for generated doc filenames."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "artifact"


def _project_doc_slug(workspace: Path) -> str:
    """Return a stable project slug for current-state markdown docs."""
    try:
        common_dir = Path(_git(workspace, "rev-parse", "--git-common-dir")).resolve()
        return _slugify_doc_segment(common_dir.parent.name)
    except RuntimeError:
        return _slugify_doc_segment(workspace.name)


def _project_doc_title(workspace: Path) -> str:
    """Return a readable project title derived from the project slug."""
    return _project_doc_slug(workspace).replace("-", " ").title()


def _load_yaml_document(path: Path) -> dict:
    """Load a YAML document from *path* as a mapping."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RuntimeError(f"Expected YAML mapping in {path}")
    return loaded


def _render_features_markdown(
    *,
    project_title: str,
    change_id: str,
    feature_spec: dict,
) -> str:
    """Render the durable current-state feature markdown doc."""
    lines = [
        f"# {project_title} Capabilities",
        "",
        f"Updated from `{change_id}`.",
        "",
    ]

    features = feature_spec.get("features", [])
    if features:
        lines.extend(["## Features", ""])
        for feature in features:
            lines.append(f"### {feature['id']} {feature['name']}")
            lines.append("")
            lines.append(feature["description"])
            lines.append("")
            dependencies = feature.get("dependencies") or []
            lines.append(
                "Dependencies: "
                + (", ".join(dependencies) if dependencies else "None")
            )
            source_refs = feature.get("source_inventory_refs") or []
            if source_refs:
                lines.append("Source inventory refs: " + ", ".join(source_refs))
            lines.append("")
            lines.append("Acceptance Criteria")
            for criterion in feature.get("acceptance_criteria", []):
                lines.append(f"- `{criterion['id']}` {criterion['description']}")
            lines.append("")

    out_of_scope = feature_spec.get("out_of_scope", [])
    if out_of_scope:
        lines.extend(["## Qualitative Or Deferred Requirements", ""])
        for item in out_of_scope:
            lines.append(
                f"- `{item['inventory_ref']}` {item['reason']}"
            )
        lines.append("")

    cross_cutting = feature_spec.get("cross_cutting_concerns", [])
    if cross_cutting:
        lines.extend(["## Cross-Cutting Concerns", ""])
        for concern in cross_cutting:
            lines.append(f"### {concern['id']} {concern['name']}")
            lines.append("")
            lines.append(concern["description"])
            affected = concern.get("affected_features") or []
            if affected:
                lines.append("")
                lines.append("Affected features: " + ", ".join(affected))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_design_markdown(
    *,
    project_title: str,
    change_id: str,
    solution_design: dict,
) -> str:
    """Render the durable current-state design markdown doc."""
    lines = [
        f"# {project_title} Design",
        "",
        f"Updated from `{change_id}`.",
        "",
    ]

    components = solution_design.get("components", [])
    if components:
        lines.extend(["## Components", ""])
        for component in components:
            lines.append(f"### {component['id']} {component['name']}")
            lines.append("")
            lines.append(component["responsibility"])
            lines.append("")
            lines.append(f"Technology: {component['technology']}")
            dependencies = component.get("dependencies") or []
            lines.append(
                "Dependencies: "
                + (", ".join(dependencies) if dependencies else "None")
            )
            lines.append("")
            lines.append("Feature Realization")
            for feature_id, summary in (component.get("feature_realization_map") or {}).items():
                lines.append(f"- `{feature_id}` {summary}")
            lines.append("")

    interactions = solution_design.get("interactions", [])
    if interactions:
        lines.extend(["## Interactions", ""])
        for interaction in interactions:
            lines.append(
                f"### {interaction['id']} {interaction['source']} -> {interaction['target']}"
            )
            lines.append("")
            lines.append(f"Protocol: {interaction['protocol']}")
            lines.append("")
            lines.append(interaction["data_exchanged"])
            lines.append("")
            lines.append(f"Triggered by: {interaction['triggered_by']}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_contracts_markdown(
    *,
    project_title: str,
    change_id: str,
    contracts_doc: dict,
) -> str:
    """Render the durable current-state contract markdown doc."""
    lines = [
        f"# {project_title} Contracts",
        "",
        f"Updated from `{change_id}`.",
        "",
    ]

    for contract in contracts_doc.get("contracts", []):
        lines.append(f"## {contract['id']} {contract['name']}")
        lines.append("")
        lines.append(f"Interaction ref: `{contract['interaction_ref']}`")
        lines.append("")
        lines.append(
            f"Source component: `{contract['source_component']}`  "
            f"Target component: `{contract['target_component']}`"
        )
        lines.append("")
        for operation in contract.get("operations", []):
            lines.append(f"### Operation: {operation['name']}")
            lines.append("")
            lines.append(operation["description"])
            lines.append("")
            lines.append("#### Request Fields")
            for field in operation.get("request_schema", {}).get("fields", []):
                lines.append(
                    f"- `{field['name']}` ({field['type']}, required={field['required']}): "
                    f"{field['constraints']}"
                )
            lines.append("")
            lines.append("#### Response Fields")
            for field in operation.get("response_schema", {}).get("fields", []):
                lines.append(
                    f"- `{field['name']}` ({field['type']}, required={field['required']}): "
                    f"{field['constraints']}"
                )
            errors = operation.get("error_types") or []
            if errors:
                lines.append("")
                lines.append("#### Error Types")
                for error in errors:
                    lines.append(
                        f"- `{error['name']}` ({error['http_status']}): {error['condition']}"
                    )
            lines.append("")
        behavioral_specs = contract.get("behavioral_specs") or []
        if behavioral_specs:
            lines.append("### Behavioral Specs")
            lines.append("")
            for spec in behavioral_specs:
                lines.append(f"- Precondition: {spec['precondition']}")
                lines.append(f"- Postcondition: {spec['postcondition']}")
                lines.append(f"- Invariant: {spec['invariant']}")
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _write_steady_state_docs(workspace: Path, state: ProjectState) -> None:
    """Generate deterministic current-state markdown docs from preserved artifacts."""
    change_root = _change_record_root(workspace, state.change_id or workspace.name)
    analysis_root = change_root / "analysis"
    project_slug = _project_doc_slug(workspace)
    project_title = _project_doc_title(workspace)

    feature_spec = _load_yaml_document(analysis_root / "feature-specification.yaml")
    solution_design = _load_yaml_document(analysis_root / "solution-design.yaml")
    contracts_doc = _load_yaml_document(analysis_root / "interface-contracts.yaml")

    feature_doc = workspace / "docs" / "features" / f"{project_slug}-capabilities.md"
    design_doc = workspace / "docs" / "design" / f"{project_slug}-design.md"
    contracts_doc_path = workspace / "docs" / "contracts" / f"{project_slug}-contracts.md"

    feature_doc.parent.mkdir(parents=True, exist_ok=True)
    design_doc.parent.mkdir(parents=True, exist_ok=True)
    contracts_doc_path.parent.mkdir(parents=True, exist_ok=True)

    feature_doc.write_text(
        _render_features_markdown(
            project_title=project_title,
            change_id=state.change_id or workspace.name,
            feature_spec=feature_spec,
        ),
        encoding="utf-8",
    )
    design_doc.write_text(
        _render_design_markdown(
            project_title=project_title,
            change_id=state.change_id or workspace.name,
            solution_design=solution_design,
        ),
        encoding="utf-8",
    )
    contracts_doc_path.write_text(
        _render_contracts_markdown(
            project_title=project_title,
            change_id=state.change_id or workspace.name,
            contracts_doc=contracts_doc,
        ),
        encoding="utf-8",
    )


def _start_lifecycle_phase(
    state: ProjectState,
    workspace: Path,
    phase_id: str,
    *,
    persist: bool = True,
) -> None:
    """Mark one lifecycle phase in progress and optionally persist state."""
    lifecycle = _find_lifecycle_phase_state(state, phase_id)
    lifecycle.status = PhaseStatus.IN_PROGRESS
    if lifecycle.started_at is None:
        lifecycle.started_at = _iso_now()
    lifecycle.completed_at = None
    state.current_lifecycle_phase_id = phase_id
    if persist:
        save_project_state(state, workspace)


def _complete_lifecycle_phase(
    state: ProjectState,
    workspace: Path,
    phase_id: str,
    *,
    persist: bool = True,
) -> None:
    """Mark one lifecycle phase completed and optionally persist state."""
    lifecycle = _find_lifecycle_phase_state(state, phase_id)
    lifecycle.status = PhaseStatus.COMPLETED
    if lifecycle.started_at is None:
        lifecycle.started_at = _iso_now()
    lifecycle.completed_at = _iso_now()
    state.current_lifecycle_phase_id = phase_id
    if persist:
        save_project_state(state, workspace)


def _fail_lifecycle_phase(
    state: ProjectState,
    workspace: Path,
    phase_id: str,
    *,
    persist: bool = True,
) -> None:
    """Mark one lifecycle phase failed and optionally persist state."""
    lifecycle = _find_lifecycle_phase_state(state, phase_id)
    lifecycle.status = PhaseStatus.FAILED
    if lifecycle.started_at is None:
        lifecycle.started_at = _iso_now()
    lifecycle.completed_at = None
    state.current_lifecycle_phase_id = phase_id
    if persist:
        save_project_state(state, workspace)


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


def _architecture_declares_no_simulation_targets(workspace: Path) -> bool:
    """Return whether architecture explicitly marks every component non-simulated.

    The skip decision is intentionally strict: malformed architecture, missing
    components, non-dict component entries, or absent ``simulation_target``
    declarations all return False so PH-005 still runs and surfaces the problem
    through its normal prompt-runner and validation path.
    """
    architecture_phase = PHASE_MAP.get("PH-002-architecture")
    if architecture_phase is None:
        return False
    architecture_path = workspace / architecture_phase.output_artifact_path
    try:
        raw_architecture = yaml.safe_load(
            architecture_path.read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(raw_architecture, dict):
        return False
    components = raw_architecture.get("components")
    if not isinstance(components, list):
        return False
    for component in components:
        if not isinstance(component, dict):
            return False
        if component.get("simulation_target") is not False:
            return False
    return True


def _should_skip_phase_5_simulations(
    phase_config: PhaseConfig,
    workspace: Path,
) -> bool:
    """Return whether PH-005 has no component simulations to generate."""
    return (
        phase_config.phase_id == PHASE_5_SIMULATIONS_ID
        and _architecture_declares_no_simulation_targets(workspace)
    )


def _write_empty_simulations_artifact(
    workspace: Path,
    phase_config: PhaseConfig,
) -> Path:
    """Write the canonical empty PH-005 simulations manifest."""
    artifact_path = workspace / phase_config.output_artifact_path
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("simulations: []\n", encoding="utf-8")
    return artifact_path


def _target_merge_handoff_path(change_root: Path) -> Path:
    """Return the target-merge handoff path under one change record."""
    return change_root / "execution" / TARGET_MERGE_HANDOFF_FILENAME


def _write_target_merge_handoff(
    *,
    path: Path,
    change_id: str,
    source_branch: str,
    target_branch: str,
    source_commit: str,
    handoff_commit: str | None,
    base_commit: str | None,
) -> None:
    """Write the target-merge handoff consumed by backlog-runner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "change_id": change_id,
                "source_branch": source_branch,
                "target_branch": target_branch,
                "source_commit": source_commit,
                "handoff_commit": handoff_commit,
                "base_commit": base_commit,
                "status": TARGET_MERGE_PENDING_STATUS,
            },
            indent=2,
            sort_keys=False,
        ) + "\n",
        encoding="utf-8",
    )


def _automate_completed_lifecycle(
    state: ProjectState,
    workspace: Path,
    config: PipelineConfig,
) -> str | None:
    """Execute LC-002 through LC-006 and return an error string on failure."""
    change_id = state.change_id or workspace.name
    change_root = _change_record_root(workspace, change_id)

    # LC-002 Change-Record Preservation
    _start_lifecycle_phase(
        state, workspace, "LC-002-change-record-preservation", persist=True
    )
    for src_rel, dest_rel in _CHANGE_RECORD_ARTIFACT_MAP:
        src = workspace / src_rel
        if not src.exists():
            _fail_lifecycle_phase(
                state, workspace, "LC-002-change-record-preservation", persist=True
            )
            return f"Missing change-record source artifact: {src_rel}"
        _copy_preserved_artifact(src, change_root / dest_rel)
    _complete_lifecycle_phase(
        state, workspace, "LC-002-change-record-preservation", persist=True
    )

    # LC-003 Runner-State Archival
    _start_lifecycle_phase(
        state, workspace, "LC-003-runner-state-archival", persist=True
    )
    for src_rel, dest_rel in _RUNNER_STATE_ARTIFACT_MAP:
        src = workspace / src_rel
        if src.exists():
            _copy_preserved_artifact(src, change_root / dest_rel)
    _complete_lifecycle_phase(
        state, workspace, "LC-003-runner-state-archival", persist=True
    )

    # LC-004 Temporary-Artifact Cleanup
    _start_lifecycle_phase(
        state, workspace, "LC-004-temporary-artifact-cleanup", persist=True
    )
    for relpath in _TEMP_WORKING_PATHS:
        (workspace / relpath).unlink(missing_ok=True)
    _complete_lifecycle_phase(
        state, workspace, "LC-004-temporary-artifact-cleanup", persist=True
    )

    # LC-005 Steady-State Integration
    _start_lifecycle_phase(
        state, workspace, "LC-005-steady-state-integration", persist=True
    )
    try:
        _write_steady_state_docs(workspace, state)
    except (FileNotFoundError, RuntimeError, yaml.YAMLError) as exc:
        _fail_lifecycle_phase(
            state, workspace, "LC-005-steady-state-integration", persist=True
        )
        return f"Steady-state integration failed: {exc}"
    _complete_lifecycle_phase(
        state, workspace, "LC-005-steady-state-integration", persist=True
    )

    # LC-006 Final Review And History Integration
    _start_lifecycle_phase(
        state, workspace, "LC-006-final-review-and-history-integration", persist=True
    )
    source_branch = _git_current_branch(workspace)
    target_branch = _resolve_target_branch(
        workspace,
        source_branch,
        config.target_branch,
    )

    target_worktree: Path | None = None
    if not config.skip_target_merge:
        target_worktree = _find_branch_worktree_path(workspace, target_branch)
        if target_worktree is None:
            _fail_lifecycle_phase(
                state,
                workspace,
                "LC-006-final-review-and-history-integration",
                persist=True,
            )
            return f"No worktree found with target branch checked out: {target_branch}"

        if target_worktree != workspace and _git_status_porcelain(target_worktree):
            _fail_lifecycle_phase(
                state,
                workspace,
                "LC-006-final-review-and-history-integration",
                persist=True,
            )
            return f"Target worktree is not clean: {target_worktree}"

    for relpath in _FINAL_CLEANUP_PATHS:
        target = workspace / relpath
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
    _remove_transient_delivery_artifacts(workspace)

    state.finished_at = _iso_now()
    _complete_lifecycle_phase(
        state,
        workspace,
        "LC-006-final-review-and-history-integration",
        persist=False,
    )
    state.current_lifecycle_phase_id = None
    final_state_path = change_root / "execution" / "final-lifecycle-state.json"
    final_state_path.parent.mkdir(parents=True, exist_ok=True)
    final_state_path.write_text(
        json.dumps(state.to_dict(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    final_commit_message = f"Finalize lifecycle for {change_id}"
    try:
        source_commit = _git_commit(workspace, final_commit_message)
    except RuntimeError as exc:
        return f"Final lifecycle commit failed on {source_branch}: {exc}"

    if config.skip_target_merge:
        handoff_path = _target_merge_handoff_path(change_root)
        _write_target_merge_handoff(
            path=handoff_path,
            change_id=change_id,
            source_branch=source_branch,
            target_branch=target_branch,
            source_commit=source_commit,
            handoff_commit=None,
            base_commit=config.base_commit,
        )
        try:
            _git_commit(
                workspace,
                f"Record target merge handoff for {change_id}",
            )
        except RuntimeError as exc:
            return f"Target merge handoff commit failed on {source_branch}: {exc}"
        return None

    if target_branch != source_branch:
        try:
            _git(target_worktree, "merge", "--squash", source_branch)
            _git_commit(target_worktree, f"Apply {change_id}")
        except RuntimeError as exc:
            return f"Target branch integration failed: {exc}"
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
        path_mappings=_phase_path_mappings(),
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
    """Return phase_ids whose status satisfies downstream dependencies."""
    return [
        ps.phase_id for ps in state.phases
        if ps.status in _COMPLETED_STATUSES
    ]


def _get_completed_phase_states(state: ProjectState) -> list[PhaseState]:
    """Return PhaseState objects that satisfy downstream dependencies."""
    return [
        ps for ps in state.phases
        if ps.status in _COMPLETED_STATUSES
    ]


def _phase_run_dir(workspace: Path, phase_config: PhaseConfig) -> Path:
    """Return the methodology phase-artifact directory under shared .run-files."""
    return workspace / RUN_FILES_DIRNAME / phase_config.phase_id


def _resolve_phase_prompt_module_path(phase_config: PhaseConfig) -> Path:
    """Return the bundled prompt module path for a phase."""
    if not phase_config.prompt_module_path:
        raise RuntimeError(
            f"No prompt module is registered for {phase_config.phase_id}"
        )
    raw_path = Path(phase_config.prompt_module_path)
    candidates = [
        raw_path.resolve(),
        (Path(__file__).resolve().parent / raw_path).resolve(),
    ]
    for path in candidates:
        if path.exists():
            return path
    raise RuntimeError(
        f"Prompt module for {phase_config.phase_id} does not exist. "
        f"Tried: {', '.join(str(path) for path in candidates)}"
    )


def _phase_placeholder_values(
    phase_config: PhaseConfig,
    config: PipelineConfig,
) -> dict[str, str]:
    """Return prompt-runner placeholder bindings for a phase."""
    values: dict[str, str] = {}
    if phase_config.phase_id == "PH-000-requirements-inventory":
        methodology_src = _resolve_methodology_runner_src_root()
        values["raw_requirements_path"] = (
            f"{REQUIREMENTS_DEST}/{RAW_REQUIREMENTS_FILENAME}"
        )
        values["phase_0_bootstrap_command"] = (
            f"PYTHONPATH={shlex.quote(str(methodology_src))} "
            f"{shlex.quote(sys.executable)} "
            "-m methodology_runner.phase_0_validation"
        )
    if phase_config.phase_id == "PH-006-incremental-implementation":
        prompt_runner_src = _resolve_prompt_runner_src_root()
        values["prompt_runner_command"] = (
            f"PYTHONPATH={shlex.quote(str(prompt_runner_src))} "
            f"{shlex.quote(sys.executable)} -m prompt_runner"
        )
        values["methodology_backend"] = config.backend
    return values


def _resolve_bundled_skills_root() -> Path:
    """Resolve the methodology-runner bundled skills root."""
    package_root = Path(__file__).resolve().parent
    candidates = [
        package_root / "skills",
        package_root.parent.parent / "skills",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _resolve_prompt_runner_src_root() -> Path:
    """Resolve the prompt-runner source root for PH-006 shell commands."""
    package_root = Path(__file__).resolve().parent
    candidates = [
        package_root.parents[2] / "prompt-runner" / "src",
        package_root / "prompt_runner",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _resolve_methodology_runner_src_root() -> Path:
    """Resolve the methodology-runner source root for PH-000 bootstrap commands."""
    return Path(__file__).resolve().parents[1]


def _phase_path_mappings() -> dict[str, str]:
    """Return prompt-runner root-prefix mappings for methodology prompts."""
    return {
        "skills/": str(_resolve_bundled_skills_root()),
    }


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
    placeholder_values = _phase_placeholder_values(phase_config, config)

    should_skip_phase_5 = _should_skip_phase_5_simulations(
        phase_config,
        workspace,
    )
    if not cross_ref_only and should_skip_phase_5:
        now = _iso_now()
        ps.status = PhaseStatus.SKIPPED
        ps.started_at = ps.started_at or now
        ps.completed_at = now
        ps.prompt_file = str(prompt_file)
        state.current_phase = phase_id
        _write_empty_simulations_artifact(workspace, phase_config)
        (run_dir / "skip-reason.txt").write_text(
            PHASE_5_NO_TARGETS_SKIP_REASON + "\n",
            encoding="utf-8",
        )
        try:
            ps.git_commit = _git_commit(
                workspace,
                f"Phase {phase_config.phase_number}: "
                f"{phase_config.phase_name} -- skipped",
            )
        except RuntimeError:
            pass

        phase_result = PhaseResult(
            phase_id=phase_id,
            status=PhaseStatus.SKIPPED,
            prompt_runner_file=str(prompt_file),
            iteration_count=0,
            wall_time_seconds=time.monotonic() - t0,
            prompt_runner_success=False,
            cross_ref_result=None,
            prompt_file_path=prompt_file,
            run_dir=run_dir,
        )
        state.phase_results[phase_id] = phase_result
        save_project_state(state, workspace)
        return phase_result

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
    state = load_project_state(workspace)
    if state is not None:
        lines.append(f"Change ID:       {state.change_id}")
        if state.current_lifecycle_phase_id:
            lines.append(f"Current lifecycle phase: {state.current_lifecycle_phase_id}")
        methodology = _find_lifecycle_phase_state(
            state, METHODOLOGY_LIFECYCLE_PHASE_ID
        )
        if methodology.completed_at:
            lines.append(f"Methodology completed at: {methodology.completed_at}")
        if state.finished_at:
            lines.append(f"Lifecycle finished at: {state.finished_at}")

    target_phase_ids = (
        list(result.selected_phase_ids)
        if result.selected_phase_ids is not None
        else [phase.phase_id for phase in PHASES]
    )
    completed_count = sum(
        1 for pr in result.phase_results
        if pr.phase_id in target_phase_ids and pr.status in _COMPLETED_STATUSES
    )
    lines.append(
        f"Phases completed or skipped in scope: "
        f"{completed_count}/{len(target_phase_ids)}"
    )
    lines.append("")
    if state is not None:
        lines.append("-" * 60)
        lines.append("Lifecycle Phases")
        lines.append("-" * 60)
        for lifecycle_phase in state.lifecycle_phases:
            lines.append(
                "  "
                f"{lifecycle_phase.phase_id} ({lifecycle_phase.phase_name})"
            )
            lines.append(
                "    "
                f"Status:         {lifecycle_phase.status.value}"
            )
            lines.append(
                "    "
                f"Execution kind: {lifecycle_phase.execution_kind}"
            )
            if lifecycle_phase.started_at:
                lines.append(
                    "    "
                    f"Started at:     {lifecycle_phase.started_at}"
                )
            if lifecycle_phase.completed_at:
                lines.append(
                    "    "
                    f"Completed at:   {lifecycle_phase.completed_at}"
                )
        pending_manual = _pending_manual_lifecycle_phase_ids(state)
        lines.append("")
        if pending_manual:
            lines.append(
                "Automation boundary: methodology-runner automates only "
                f"{METHODOLOGY_LIFECYCLE_PHASE_ID}; remaining lifecycle phases "
                f"stay manual: {', '.join(pending_manual)}"
            )
        else:
            lines.append(
                "Automation boundary: no manual lifecycle phases remain pending."
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

            phase_results: list[PhaseResult] = []
            halted_early = False
            halt_reason: str | None = None
            lifecycle_only_resume = (
                config.resume
                and state.current_lifecycle_phase_id is not None
                and state.current_lifecycle_phase_id != METHODOLOGY_LIFECYCLE_PHASE_ID
            )

            # ---- determine phases ----
            phases_to_run: list[PhaseConfig] = list(PHASES)
            if config.phases_to_run is not None:
                phases_to_run = [
                    get_phase(pid)
                    for pid in normalize_phase_selection(config.phases_to_run)
                ]

            if not lifecycle_only_resume:
                _activate_methodology_execution_lifecycle(state)
                save_project_state(state, workspace)

                # ---- execute methodology phases ----
                for phase in phases_to_run:
                    ps = _find_phase_state(state, phase.phase_id)

                    # Resume: skip phases whose status already satisfies
                    # downstream dependencies.
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

                    result = _run_single_phase(
                        phase,
                        state,
                        workspace,
                        config,
                        claude_client=claude_client,
                        cross_ref_only=cross_ref_only,
                    )
                    phase_results.append(result)

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

                    if result.status in (PhaseStatus.FAILED, PhaseStatus.ESCALATED):
                        policy = _effective_escalation_policy(config, phase)
                        if policy != EscalationPolicy.FLAG_AND_CONTINUE:
                            halted_early = True
                            halt_reason = result.error_message
                            break
            else:
                phase_results = [
                    state.phase_results[phase.phase_id]
                    for phase in phases_to_run
                    if phase.phase_id in state.phase_results
                ]
                    # FLAG_AND_CONTINUE: keep going (subsequent phases may fail
                    # their predecessor check, which is correct behaviour)

            # ---- end-to-end verification ----
            end_to_end_result: CrossRefResult | None = None
            all_done = all(
                _find_phase_state(state, p.phase_id).status in _COMPLETED_STATUSES
                for p in PHASES
            )
            in_scope_done = all(
                _find_phase_state(state, p.phase_id).status in _COMPLETED_STATUSES
                for p in phases_to_run
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

            # ---- finalise methodology boundary ----
            state.finished_at = None
            state.current_phase = None
            _finalize_lifecycle_after_methodology_run(
                state,
                halted_early=halted_early,
                in_scope_done=in_scope_done,
                all_done=all_done,
            )
            save_project_state(state, workspace)

            lifecycle_error: str | None = None
            if all_done and not halted_early:
                lifecycle_error = _automate_completed_lifecycle(
                    state,
                    workspace,
                    config,
                )
                if lifecycle_error is not None:
                    halted_early = True
                    halt_reason = lifecycle_error
                else:
                    state.current_lifecycle_phase_id = None

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

            # Final summary with end-to-end results and halt status.
            # If lifecycle finalization removed .run-files, keep the result
            # in-memory/CLI only and avoid recreating runner-owned roots.
            if (workspace / RUN_FILES_DIRNAME).exists():
                write_summary(workspace, pipeline_result)
            return pipeline_result
        finally:
            lock.release()
