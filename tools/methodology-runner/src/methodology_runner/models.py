"""Data models for methodology-runner.

Defines all dataclasses and enums shared across the methodology-runner
system.  No dependencies on other methodology-runner modules; imports
from the standard library only.

See tools/methodology-runner/docs/design/components/CD-002-methodology-runner.md
section 10.1.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EscalationPolicy(Enum):
    """How the orchestrator reacts when a phase fails its retry budget."""

    HALT = "halt"
    FLAG_AND_CONTINUE = "flag_and_continue"
    HUMAN_REVIEW = "human_review"


class PhaseStatus(Enum):
    """Lifecycle status of a single phase execution.

    CD-002 Section 9.2 transitions::

        pending --> in_progress      # orchestrator starts the phase
        in_progress --> completed    # prompt-runner + cross-ref both passed
        in_progress --> failed       # prompt-runner escalated or retries exhausted
        in_progress --> escalated    # max retries reached, halting
        failed --> in_progress       # user explicitly retries via CLI

    Refined two-stage completion substates::

        running -> prompt_runner_passed -> cross_ref_passed
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RUNNING = "running"
    PROMPT_RUNNER_PASSED = "prompt_runner_passed"
    CROSS_REF_PASSED = "cross_ref_passed"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"
    SKIPPED = "skipped"


class InputRole(Enum):
    """Semantic role of an input artifact within a phase."""

    PRIMARY = "primary"
    VALIDATION_REFERENCE = "validation_reference"
    UPSTREAM_TRACEABILITY = "upstream_traceability"


# ---------------------------------------------------------------------------
# Configuration types  (frozen -- static per-project)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArtifactRef:
    """Reference to a resolved input or output artifact.

    Used at runtime once workspace paths are known.  For template-based
    references that contain ``{workspace}`` placeholders, see
    :class:`InputSourceTemplate`.
    """

    path: str
    role: str
    format: str
    description: str

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "role": self.role,
            "format": self.format,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ArtifactRef:
        return cls(
            path=d["path"],
            role=d["role"],
            format=d["format"],
            description=d["description"],
        )


@dataclass(frozen=True)
class InputSourceTemplate:
    """Template for an input artifact reference.

    *ref_template* contains a ``{workspace}`` placeholder that the
    orchestrator resolves against the actual workspace path at runtime.
    """

    ref_template: str
    role: InputRole
    format: str
    description: str

    def resolve(self, workspace: str) -> ArtifactRef:
        """Resolve the template against a concrete *workspace* path."""
        return ArtifactRef(
            path=self.ref_template.replace("{workspace}", workspace),
            role=self.role.value,
            format=self.format,
            description=self.description,
        )

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "ref_template": self.ref_template,
            "role": self.role.value,
            "format": self.format,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> InputSourceTemplate:
        return cls(
            ref_template=d["ref_template"],
            role=InputRole(d["role"]),
            format=d["format"],
            description=d["description"],
        )


DEFAULT_MAX_PROMPT_RUNNER_ITERATIONS = 3


@dataclass(frozen=True)
class PhaseConfig:
    """Complete configuration for one methodology phase.

    Instances are built once in *phases.py* and reused across projects.
    Merges fields from CD-002 Section 10.1 and the task specification.
    """

    # -- identity ------------------------------------------------------------
    phase_id: str
    phase_name: str
    phase_number: int
    abbreviation: str

    # -- dependency graph ----------------------------------------------------
    predecessors: list[str]

    # -- inputs / outputs ----------------------------------------------------
    input_source_templates: list[InputSourceTemplate]
    output_artifact_path: str
    output_format: str
    expected_output_files: list[str]

    # -- methodology content -------------------------------------------------
    extraction_focus: str
    generation_instructions: str
    judge_guidance: str
    artifact_format: str
    artifact_schema_description: str

    # -- checklist examples --------------------------------------------------
    checklist_examples_good: list[str]
    checklist_examples_bad: list[str]
    prompt_module_path: str | None = None

    # -- tunables (defaults) -------------------------------------------------
    max_prompt_runner_iterations: int = DEFAULT_MAX_PROMPT_RUNNER_ITERATIONS
    escalation_policy: EscalationPolicy = EscalationPolicy.HALT

    @property
    def example_checklist_items(self) -> list[str]:
        """Combined checklist examples for the meta-prompt.

        CD-002 Section 10.1 defines a single ``example_checklist_items``
        list.  The task spec refines this into good/bad splits.  This
        property provides CD-002 compatibility.
        """
        return self.checklist_examples_good + self.checklist_examples_bad

    @property
    def input_artifacts(self) -> list[InputSourceTemplate]:
        """Alias matching the CD-002 Section 10.1 field name."""
        return self.input_source_templates

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "phase_id": self.phase_id,
            "phase_name": self.phase_name,
            "phase_number": self.phase_number,
            "abbreviation": self.abbreviation,
            "predecessors": list(self.predecessors),
            "input_source_templates": [
                t.to_dict() for t in self.input_source_templates
            ],
            "output_artifact_path": self.output_artifact_path,
            "output_format": self.output_format,
            "prompt_module_path": self.prompt_module_path,
            "expected_output_files": list(self.expected_output_files),
            "extraction_focus": self.extraction_focus,
            "generation_instructions": self.generation_instructions,
            "judge_guidance": self.judge_guidance,
            "artifact_format": self.artifact_format,
            "artifact_schema_description": self.artifact_schema_description,
            "checklist_examples_good": list(self.checklist_examples_good),
            "checklist_examples_bad": list(self.checklist_examples_bad),
            "max_prompt_runner_iterations": self.max_prompt_runner_iterations,
            "escalation_policy": self.escalation_policy.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PhaseConfig:
        return cls(
            phase_id=d["phase_id"],
            phase_name=d["phase_name"],
            phase_number=d["phase_number"],
            abbreviation=d["abbreviation"],
            predecessors=list(d["predecessors"]),
            input_source_templates=[
                InputSourceTemplate.from_dict(t)
                for t in d["input_source_templates"]
            ],
            output_artifact_path=d["output_artifact_path"],
            output_format=d["output_format"],
            prompt_module_path=d.get("prompt_module_path"),
            expected_output_files=list(d["expected_output_files"]),
            extraction_focus=d["extraction_focus"],
            generation_instructions=d["generation_instructions"],
            judge_guidance=d["judge_guidance"],
            artifact_format=d["artifact_format"],
            artifact_schema_description=d["artifact_schema_description"],
            checklist_examples_good=list(d["checklist_examples_good"]),
            checklist_examples_bad=list(d["checklist_examples_bad"]),
            max_prompt_runner_iterations=d.get(
                "max_prompt_runner_iterations",
                DEFAULT_MAX_PROMPT_RUNNER_ITERATIONS,
            ),
            escalation_policy=EscalationPolicy(
                d.get("escalation_policy", EscalationPolicy.HALT.value)
            ),
        )


# ---------------------------------------------------------------------------
# Cross-reference verification types  (frozen -- immutable results)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CrossRefIssue:
    """A single cross-reference verification issue."""

    category: str
    description: str
    affected_elements: list[str]
    severity: str

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "description": self.description,
            "affected_elements": list(self.affected_elements),
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CrossRefIssue:
        return cls(
            category=d["category"],
            description=d["description"],
            affected_elements=list(d["affected_elements"]),
            severity=d["severity"],
        )


@dataclass(frozen=True)
class CrossRefCheckResult:
    """Result of one verification check category (e.g. traceability)."""

    status: str
    issues: list[CrossRefIssue]

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "issues": [i.to_dict() for i in self.issues],
        }

    @classmethod
    def from_dict(cls, d: dict) -> CrossRefCheckResult:
        return cls(
            status=d["status"],
            issues=[CrossRefIssue.from_dict(i) for i in d["issues"]],
        )


@dataclass(frozen=True)
class CrossReferenceResult:
    """Complete structured cross-reference verification result for a phase.

    Models the four-category verification output defined in CD-002
    Section 8.2: traceability, coverage, consistency, integration.
    """

    verdict: str
    traceability: CrossRefCheckResult
    coverage: CrossRefCheckResult
    consistency: CrossRefCheckResult
    integration: CrossRefCheckResult

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "traceability": self.traceability.to_dict(),
            "coverage": self.coverage.to_dict(),
            "consistency": self.consistency.to_dict(),
            "integration": self.integration.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> CrossReferenceResult:
        return cls(
            verdict=d["verdict"],
            traceability=CrossRefCheckResult.from_dict(d["traceability"]),
            coverage=CrossRefCheckResult.from_dict(d["coverage"]),
            consistency=CrossRefCheckResult.from_dict(d["consistency"]),
            integration=CrossRefCheckResult.from_dict(d["integration"]),
        )


@dataclass(frozen=True)
class CrossRefResult:
    """Flat summary of cross-reference verification for a phase.

    A simplified view used in :class:`PhaseResult` for quick status
    checks.  For the full structured four-category model, see
    :class:`CrossReferenceResult`.
    """

    passed: bool
    issues: list[str]
    traceability_gaps: list[str]
    orphaned_elements: list[str]
    coverage_summary: dict[str, float]

    @classmethod
    def from_cross_reference_result(
        cls, result: CrossReferenceResult,
    ) -> CrossRefResult:
        """Build a flat summary from a structured CrossReferenceResult."""
        all_issues: list[str] = []
        traceability_gaps: list[str] = []
        orphaned_elements: list[str] = []

        for check in (
            result.traceability,
            result.coverage,
            result.consistency,
            result.integration,
        ):
            for issue in check.issues:
                all_issues.append(
                    f"[{issue.category}/{issue.severity}] {issue.description}"
                )
                if issue.category == "traceability":
                    traceability_gaps.extend(issue.affected_elements)
                if issue.category == "integration":
                    orphaned_elements.extend(issue.affected_elements)

        categories = ["traceability", "coverage", "consistency", "integration"]
        checks = [
            result.traceability,
            result.coverage,
            result.consistency,
            result.integration,
        ]
        coverage_summary = {
            cat: (1.0 if chk.status == "pass" else 0.0)
            for cat, chk in zip(categories, checks)
        }

        return cls(
            passed=result.verdict == "pass",
            issues=all_issues,
            traceability_gaps=traceability_gaps,
            orphaned_elements=orphaned_elements,
            coverage_summary=coverage_summary,
        )

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "issues": list(self.issues),
            "traceability_gaps": list(self.traceability_gaps),
            "orphaned_elements": list(self.orphaned_elements),
            "coverage_summary": dict(self.coverage_summary),
        }

    @classmethod
    def from_dict(cls, d: dict) -> CrossRefResult:
        return cls(
            passed=d["passed"],
            issues=list(d["issues"]),
            traceability_gaps=list(d["traceability_gaps"]),
            orphaned_elements=list(d["orphaned_elements"]),
            coverage_summary={
                k: float(v) for k, v in d["coverage_summary"].items()
            },
        )


# ---------------------------------------------------------------------------
# Runtime state types
# ---------------------------------------------------------------------------

@dataclass
class PhaseState:
    """Mutable tracking state for one phase within a project run.

    Tracks lifecycle status, timing, paths to run artifacts, retry
    counts, and the git commit that sealed the phase.  Defined in
    CD-002 Section 10.1 and Section 9.1.
    """

    phase_id: str
    status: PhaseStatus
    started_at: str | None
    completed_at: str | None
    prompt_file: str | None
    cross_ref_result_path: str | None
    cross_ref_retries: int
    git_commit: str | None

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "phase_id": self.phase_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "prompt_file": self.prompt_file,
            "cross_ref_result_path": self.cross_ref_result_path,
            "cross_ref_retries": self.cross_ref_retries,
            "git_commit": self.git_commit,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PhaseState:
        return cls(
            phase_id=d["phase_id"],
            status=PhaseStatus(d["status"]),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            prompt_file=d.get("prompt_file"),
            cross_ref_result_path=d.get("cross_ref_result_path"),
            cross_ref_retries=d.get("cross_ref_retries", 0),
            git_commit=d.get("git_commit"),
        )


@dataclass(frozen=True)
class PhaseResult:
    """Frozen outcome of executing one phase (prompt-runner + cross-ref).

    Created once when a phase finishes and stored in
    ``ProjectState.phase_results``.
    """

    # -- required fields -----------------------------------------------------
    phase_id: str
    status: PhaseStatus
    prompt_runner_file: str
    iteration_count: int
    wall_time_seconds: float

    # -- optional fields -----------------------------------------------------
    prompt_runner_exit_code: int | None = None
    prompt_runner_success: bool = False
    cross_ref_result: CrossRefResult | None = None
    prompt_file_path: Path | None = None
    run_dir: Path | None = None
    error_message: str | None = None

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "phase_id": self.phase_id,
            "status": self.status.value,
            "prompt_runner_file": self.prompt_runner_file,
            "iteration_count": self.iteration_count,
            "wall_time_seconds": self.wall_time_seconds,
            "prompt_runner_exit_code": self.prompt_runner_exit_code,
            "prompt_runner_success": self.prompt_runner_success,
            "cross_ref_result": (
                self.cross_ref_result.to_dict()
                if self.cross_ref_result is not None
                else None
            ),
            "prompt_file_path": (
                str(self.prompt_file_path)
                if self.prompt_file_path is not None
                else None
            ),
            "run_dir": (
                str(self.run_dir)
                if self.run_dir is not None
                else None
            ),
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PhaseResult:
        raw_xref = d.get("cross_ref_result")
        raw_pfp = d.get("prompt_file_path")
        raw_rd = d.get("run_dir")
        return cls(
            phase_id=d["phase_id"],
            status=PhaseStatus(d["status"]),
            prompt_runner_file=d["prompt_runner_file"],
            iteration_count=d["iteration_count"],
            wall_time_seconds=d["wall_time_seconds"],
            prompt_runner_exit_code=d.get("prompt_runner_exit_code"),
            prompt_runner_success=d.get("prompt_runner_success", False),
            cross_ref_result=(
                CrossRefResult.from_dict(raw_xref)
                if raw_xref is not None
                else None
            ),
            prompt_file_path=(
                Path(raw_pfp) if raw_pfp is not None else None
            ),
            run_dir=Path(raw_rd) if raw_rd is not None else None,
            error_message=d.get("error_message"),
        )


@dataclass
class ProjectState:
    """Full project state, persisted to JSON on disk.

    Tracks the workspace directory, timing, per-phase mutable state
    (via *phases*), and per-phase frozen results (via *phase_results*)
    for an in-progress or completed methodology run.
    """

    # -- required fields (from task spec) ------------------------------------
    workspace_dir: Path
    requirements_path: Path
    phase_results: dict[str, PhaseResult]
    started_at: str
    git_initialized: bool

    # -- optional fields -----------------------------------------------------
    project_name: str = ""
    model: str | None = None
    backend: str = "codex"
    execution_scope: str = "all-phases"
    selected_phase_ids: list[str] | None = None
    finished_at: str | None = None
    current_phase: str | None = None
    phases: list[PhaseState] = field(default_factory=list)

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "workspace_dir": str(self.workspace_dir),
            "requirements_path": str(self.requirements_path),
            "phase_results": {
                k: v.to_dict() for k, v in self.phase_results.items()
            },
            "started_at": self.started_at,
            "git_initialized": self.git_initialized,
            "project_name": self.project_name,
            "model": self.model,
            "backend": self.backend,
            "execution_scope": self.execution_scope,
            "selected_phase_ids": (
                list(self.selected_phase_ids)
                if self.selected_phase_ids is not None
                else None
            ),
            "finished_at": self.finished_at,
            "current_phase": self.current_phase,
            "phases": [p.to_dict() for p in self.phases],
        }

    @classmethod
    def from_dict(cls, d: dict) -> ProjectState:
        return cls(
            workspace_dir=Path(d["workspace_dir"]),
            requirements_path=Path(d["requirements_path"]),
            phase_results={
                k: PhaseResult.from_dict(v)
                for k, v in d["phase_results"].items()
            },
            started_at=d["started_at"],
            git_initialized=d["git_initialized"],
            project_name=d.get("project_name", ""),
            model=d.get("model"),
            backend=d.get("backend", "claude"),
            execution_scope=d.get("execution_scope", "all-phases"),
            selected_phase_ids=(
                list(d["selected_phase_ids"])
                if d.get("selected_phase_ids") is not None
                else None
            ),
            finished_at=d.get("finished_at"),
            current_phase=d.get("current_phase"),
            phases=[
                PhaseState.from_dict(p)
                for p in d.get("phases", [])
            ],
        )

    # -- persistence ---------------------------------------------------------

    def save(self, path: Path) -> None:
        """Write project state as JSON to *path* (atomic via temp file)."""
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> ProjectState:
        """Read project state from a JSON file at *path*."""
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(raw)
