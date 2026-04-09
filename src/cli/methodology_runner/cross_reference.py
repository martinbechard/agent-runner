"""Cross-reference verification for methodology-runner phases.

Runs after prompt-runner has completed a phase's incremental prompts.
Verifies that the phase's output integrates correctly with all prior
phases' outputs by calling Claude with tool access to inspect the
workspace.

See docs/design/components/CD-002-methodology-runner.md Section 8.

Public API
----------
verify_phase_cross_references(phase, workspace, completed_phases, model)
    Run cross-reference verification for a single completed phase.

verify_end_to_end(workspace, model)
    Run final end-to-end verification across all phases.

Constants
---------
CROSS_REF_SYSTEM_PROMPT
    System prompt appended to every cross-reference verification call.
PHASE_CROSS_REF_CHECKS
    Per-phase verification check templates keyed by phase_id.
END_TO_END_PROMPT_TEMPLATE
    Template for the final end-to-end verification prompt.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from .models import (
    CrossRefCheckResult,
    CrossRefIssue,
    CrossRefResult,
    CrossReferenceResult,
    PhaseConfig,
)
from .phases import PHASES, PHASE_MAP

if TYPE_CHECKING:
    from prompt_runner.claude_client import ClaudeClient


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CROSS_REF_LOG_DIR = "cross-ref-logs"
"""Subdirectory within the workspace for cross-reference verification logs."""

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n(.*?)```",
    re.DOTALL,
)
"""Matches a fenced JSON code block in Claude's output."""

_BARE_JSON_RE = re.compile(
    r'\{\s*"verdict"\s*:.*\}',
    re.DOTALL,
)
"""Fallback: matches bare JSON starting with a "verdict" key."""

_CATEGORY_NAMES = ("traceability", "coverage", "consistency", "integration")
"""The four verification categories in check order."""


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

class CrossReferenceError(Exception):
    """Raised when cross-reference verification fails to produce a result."""

    def __init__(self, phase_id: str, reason: str) -> None:
        super().__init__(
            f"Cross-reference verification for {phase_id}: {reason}"
        )
        self.phase_id = phase_id
        self.reason = reason


# ---------------------------------------------------------------------------
# System prompt (CD-002 Section 8.2)
# ---------------------------------------------------------------------------

CROSS_REF_SYSTEM_PROMPT = """\
You are a cross-reference verification agent for an AI-driven software
development pipeline.  Your job is to verify that the output of a
methodology phase is correctly integrated with all prior phase outputs.

You have tool access.  Use the Read tool to inspect files in the workspace.
Use Grep to search for specific element IDs.  Do not hallucinate file
contents -- always read them.

Be thorough and systematic.  Check every element, not just a sample.
Report every issue found -- do not stop at the first failure.

Your response must end with a single JSON code block containing the
verification result.  The JSON must match this exact structure:

{
  "verdict": "pass" or "fail",
  "checks": {
    "traceability": {
      "status": "pass" or "fail",
      "issues": []
    },
    "coverage": {
      "status": "pass" or "fail",
      "issues": []
    },
    "consistency": {
      "status": "pass" or "fail",
      "issues": []
    },
    "integration": {
      "status": "pass" or "fail",
      "issues": []
    }
  },
  "coverage_percentages": {
    "traceability": <0-100 float>,
    "coverage": <0-100 float>,
    "consistency": <0-100 float>,
    "integration": <0-100 float>
  }
}

Each issue must have:
  "category": which check found it
  "description": what is wrong
  "affected_elements": list of element ID strings involved
  "severity": "blocking" or "warning"

The "coverage_percentages" object reports the actual percentage of
elements that passed each check (0 to 100).  For example, if 17 out
of 20 RI-* items have valid traceability, report 85.0 for traceability.
This is distinct from the binary pass/fail "status" in each check.

The overall verdict is "pass" only if all four checks pass (no blocking
issues).  Warning-severity issues do not block the verdict."""


# ---------------------------------------------------------------------------
# Per-phase cross-reference check templates (CD-002 Section 8.1)
# ---------------------------------------------------------------------------

PHASE_CROSS_REF_CHECKS: dict[str, str] = {
    # ------------------------------------------------------------------
    # Phase 0: Requirements Inventory
    # ------------------------------------------------------------------
    "PH-000-requirements-inventory": """\
## Phase 0: Requirements Inventory -- Cross-Reference Checks

Current phase output: {output_path}
Raw requirements source: docs/requirements/raw-requirements.md

### 1. Traceability
Read the requirements inventory YAML at {output_path}.
For each RI-* item, verify that:
- The verbatim_quote text can be found in docs/requirements/raw-requirements.md.
- The source_location field references a real section or paragraph heading.
Use the Read tool on both files.  Search for each verbatim_quote in the raw
requirements using Grep.

### 2. Coverage
Read every section and paragraph in docs/requirements/raw-requirements.md.
Identify every statement containing shall, must, will, should, or an
imperative verb describing system behaviour.  Verify each has at least one
corresponding RI-* item.  Flag sections with zero RI-* coverage.

### 3. Consistency
Verify that:
- All RI-NNN IDs are unique and follow the zero-padded three-digit pattern.
- Category values are one of: functional, non_functional, constraint, assumption.
- The YAML is structurally valid with all required fields present.
- No RI-* item has an empty verbatim_quote or source_location.

### 4. Integration
Phase 0 is the first phase, so integration checks are minimal:
- Verify the inventory does not invent requirements absent from the source.
- Verify no compound requirements (containing 'and'/'or' joining independent
  clauses describing distinct behaviours) remain unsplit.\
""",

    # ------------------------------------------------------------------
    # Phase 1: Feature Specification
    # ------------------------------------------------------------------
    "PH-001-feature-specification": """\
## Phase 1: Feature Specification -- Cross-Reference Checks

Current phase output: {output_path}
Prior phase outputs:
  Phase 0 (Requirements Inventory): docs/requirements/requirements-inventory.yaml

### 1. Traceability
Read {output_path}.  For each FT-* feature:
- Read its source_inventory_refs list.
- For each RI-NNN in that list, verify it exists in the Phase 0 inventory.
Flag any FT-* whose source_inventory_refs is empty or contains non-existent
RI-* IDs.

### 2. Coverage
Read docs/requirements/requirements-inventory.yaml.  Collect all RI-NNN IDs.
For each RI-NNN, verify it appears in:
- At least one feature's source_inventory_refs list, OR
- The out_of_scope section with a stated reason.
Flag every RI-NNN that is neither traced nor out-of-scope.

### 3. Consistency
Verify that:
- All FT-NNN IDs are unique and follow the pattern.
- All AC-NNN-NN IDs are unique and follow the pattern.
- Every RI-NNN in source_inventory_refs exists in Phase 0.
- Every FT-NNN in dependencies exists in this specification.
- Every CC-NNN in cross_cutting_concerns references existing FT-NNN IDs.

### 4. Integration
- Verify no feature contradicts another feature's assumptions.
- Verify no scope creep: every feature traces to at least one RI-* item.
- Verify dependency declarations are acyclic.\
""",

    # ------------------------------------------------------------------
    # Phase 2: Architecture
    # ------------------------------------------------------------------
    "PH-002-architecture": """\
## Phase 2: Architecture -- Cross-Reference Checks

Current phase output: {output_path}
Prior phase outputs:
  Phase 0 (Requirements Inventory): docs/requirements/requirements-inventory.yaml
  Phase 1 (Feature Specification): docs/features/feature-specification.yaml

### 1. Traceability
Read {output_path}.  For each CMP-* component:
- Read its features_served list.
- For each FT-NNN, verify it exists in Phase 1.
Flag any component with an empty features_served list or non-existent feature refs.

### 2. Coverage
Read docs/features/feature-specification.yaml.  Collect all FT-NNN IDs.
For each FT-NNN, verify it appears in at least one component's
features_served list.  Flag any untraced features.

### 3. Consistency
Verify that:
- All CMP-NNN IDs are unique.
- All IP-NNN IDs are unique.
- Every component in an integration_point's between list exists as a component.
- Every component has a non-empty expected_expertise list.
- The rationale field is non-empty and explains decomposition choices.

### 4. Integration
- Flag components with no features_served entries.
- Verify integration_points reference two distinct components each.
- Verify technology choices are coherent with frameworks listed.\
""",

    # ------------------------------------------------------------------
    # Phase 3: Solution Design
    # ------------------------------------------------------------------
    "PH-003-solution-design": """\
## Phase 3: Solution Design -- Cross-Reference Checks

Current phase output: {output_path}
Prior phase outputs:
  Phase 1 (Feature Specification): docs/features/feature-specification.yaml
  Phase 2 (Architecture): docs/architecture/stack-manifest.yaml

### 1. Traceability
Read {output_path}.  For each CMP-* component:
- Read its feature_realization_map.
- For each FT-NNN key, verify the FT-NNN exists in Phase 1.
Flag any CMP-* with an empty feature_realization_map or non-existent feature refs.

### 2. Coverage
Read docs/features/feature-specification.yaml.  Collect all FT-NNN IDs.
For each FT-NNN, verify it appears in at least one component's
feature_realization_map.  Flag any untraced features.

### 3. Consistency
Verify that:
- All CMP-NNN IDs are unique.
- All INT-NNN IDs are unique.
- Every CMP-NNN in a dependencies list exists as a component.
- Every INT-NNN source and target reference existing CMP-NNN IDs.
- If CMP-A depends on CMP-B, at least one INT-* exists between them.

### 4. Integration
- Flag orphan components (not in any feature_realization_map and not a
  dependency of any other component).
- Flag god components (in more than 60% of features).
- Verify every dependency edge has a corresponding INT-* interaction.\
""",

    # ------------------------------------------------------------------
    # Phase 4: Interface Contracts
    # ------------------------------------------------------------------
    "PH-004-interface-contracts": """\
## Phase 4: Interface Contracts -- Cross-Reference Checks

Current phase output: {output_path}
Prior phase outputs:
  Phase 1 (Feature Specification): docs/features/feature-specification.yaml
  Phase 3 (Solution Design): docs/design/solution-design.yaml

### 1. Traceability
Read {output_path}.  For each CTR-* contract:
- Verify interaction_ref points to an existing INT-NNN in Phase 3.
- Verify source_component and target_component match the INT's source/target.
Flag any CTR-* with a missing or incorrect interaction_ref.

### 2. Coverage
Read docs/design/solution-design.yaml.  Collect all INT-NNN IDs.
For each INT-NNN, verify at least one CTR-* has a matching interaction_ref.
Flag uncovered interactions.

### 3. Consistency
Verify that:
- All CTR-NNN IDs are unique.
- source_component and target_component reference existing CMP-NNN IDs.
- Every operation has non-empty request_schema and response_schema.
- No schema field has type 'object', 'any', or 'unknown'.
- Every operation defines at least one error_type.

### 4. Integration
- Verify contracts are consistent with Phase 1 acceptance criteria.
- Verify no contract introduces operations not implied by Phase 3 interactions.
- Verify behavioural specs are achievable given Phase 3 component responsibilities.\
""",

    # ------------------------------------------------------------------
    # Phase 5: Intelligent Simulations
    # ------------------------------------------------------------------
    "PH-005-intelligent-simulations": """\
## Phase 5: Intelligent Simulations -- Cross-Reference Checks

Current phase output: {output_path}
Prior phase outputs:
  Phase 1 (Feature Specification): docs/features/feature-specification.yaml
  Phase 4 (Interface Contracts): docs/design/interface-contracts.yaml

### 1. Traceability
Read {output_path}.  For each SIM-* simulation:
- Verify contract_ref points to an existing CTR-NNN in Phase 4.
Flag any SIM-* with a missing or incorrect contract_ref.

### 2. Coverage
Read docs/design/interface-contracts.yaml.  Collect all CTR-NNN IDs.
For each CTR-NNN, verify at least one SIM-* has a matching contract_ref.
Also verify each SIM has at least one happy_path, one error_path, and one
edge_case scenario.

### 3. Consistency
Verify that:
- All SIM-NNN IDs are unique.
- Scenario inputs match the contract's request_schema field structure.
- Expected outputs match the contract's response_schema structure.
- Error path scenarios trigger error types defined in the contract.

### 4. Integration
- Verify simulations do not embed implementation-specific knowledge
  (internal IDs, timestamps, database details).
- Verify scenario data is realistic given contract constraints.\
""",

    # ------------------------------------------------------------------
    # Phase 6: Incremental Implementation
    # ------------------------------------------------------------------
    "PH-006-incremental-implementation": """\
## Phase 6: Incremental Implementation -- Cross-Reference Checks

Current phase output: {output_path}
Prior phase outputs:
  Phase 1 (Feature Specification): docs/features/feature-specification.yaml
  Phase 3 (Solution Design): docs/design/solution-design.yaml
  Phase 4 (Interface Contracts): docs/design/interface-contracts.yaml
  Phase 5 (Intelligent Simulations): docs/simulations/simulation-definitions.yaml

### 1. Traceability
Read {output_path}.  For each build_order step:
- Verify component_ref references an existing CMP-NNN from Phase 3.
- Verify contracts_implemented references existing CTR-NNN from Phase 4.
- Verify simulations_used references existing SIM-NNN from Phase 5.
For each unit test:
- Verify acceptance_criteria_refs reference existing AC-NNN-NN from Phase 1.
- Verify contract_ref references an existing CTR-NNN from Phase 4.

### 2. Coverage
- Every CMP-NNN from Phase 3 must appear in the build_order.
- Every CTR-NNN from Phase 4 must appear in at least one step's
  contracts_implemented.
- Every SIM-NNN from Phase 5 must appear in the simulation_replacement_sequence.
- Every AC-NNN-NN from Phase 1 must be referenced by at least one test.

### 3. Consistency
Verify that:
- Build order respects the Phase 3 dependency graph: no component is built
  before its dependencies are built or simulated.
- Every SIM-* in simulation_replacement_sequence has a valid replaced_at_step.
- integration_tests_to_rerun references actual integration test names.

### 4. Integration
- Verify no build step references a contract belonging to a not-yet-built
  component without a simulation standing in.
- Verify simulation replacement is consistent with the build order.
- Verify test coverage aligns with Phase 1 acceptance criteria priorities.\
""",

    # ------------------------------------------------------------------
    # Phase 7: Verification Sweep
    # ------------------------------------------------------------------
    "PH-007-verification-sweep": """\
## Phase 7: Verification Sweep -- Cross-Reference Checks

Current phase output: {output_path}
Prior phase outputs:
  Phase 0 (Requirements Inventory): docs/requirements/requirements-inventory.yaml
  Phase 1 (Feature Specification): docs/features/feature-specification.yaml
  Phase 3 (Solution Design): docs/design/solution-design.yaml
  Phase 6 (Incremental Implementation): docs/implementation/implementation-plan.yaml

### 1. Traceability
Read {output_path}.  For each E2E-* test:
- Verify feature_ref references an existing FT-NNN from Phase 1.
- Verify acceptance_criteria_refs reference existing AC-NNN-NN from Phase 1.
For each traceability_matrix row:
- Verify inventory_ref references an existing RI-NNN from Phase 0.
- Verify feature_refs reference existing FT-NNN from Phase 1.
- Verify e2e_test_refs reference existing E2E-* tests in this file.

### 2. Coverage
Read docs/requirements/requirements-inventory.yaml.  Collect all RI-NNN IDs.
For each RI-NNN, verify the traceability_matrix contains a row with a
complete chain: non-empty feature_refs, acceptance_criteria_refs, AND
e2e_test_refs.  Flag any RI-NNN without a complete chain.
Verify coverage_summary numbers match actual counts.

### 3. Consistency
Verify that:
- All E2E-* IDs are unique.
- Every ID reference resolves to the correct source phase.
- coverage_summary.total_requirements matches the RI-* count in Phase 0.
- covered + partial + uncovered = total_requirements.
- coverage_percentage = (covered / total_requirements) * 100.

### 4. Integration
- Verify E2E tests exercise the component interaction paths from Phase 3.
- Verify no E2E test references features marked out-of-scope in Phase 1.
- Verify alignment with the Phase 6 implementation plan.\
""",
}


# ---------------------------------------------------------------------------
# End-to-end verification prompt template
# ---------------------------------------------------------------------------

END_TO_END_PROMPT_TEMPLATE = """\
You are performing a final end-to-end verification across all seven phases
of an AI-driven software development methodology.

## All phase outputs

  Phase 0 (Requirements Inventory): docs/requirements/requirements-inventory.yaml
  Phase 1 (Feature Specification): docs/features/feature-specification.yaml
  Phase 2 (Solution Design): docs/design/solution-design.yaml
  Phase 3 (Interface Contracts): docs/design/interface-contracts.yaml
  Phase 4 (Intelligent Simulations): docs/simulations/simulation-definitions.yaml
  Phase 5 (Implementation Plan): docs/implementation/implementation-plan.yaml
  Phase 6 (Verification Sweep): docs/verification/verification-report.yaml

## End-to-End Traceability Verification

Trace every RI-* item from the Phase 0 requirements inventory through the
full chain to E2E tests.  For each RI-NNN:

1. Find which FT-* features reference it (source_inventory_refs in Phase 1).
2. Find which CMP-* components realize those features (feature_realization_map
   in Phase 2).
3. Find which INT-* interactions connect those components (Phase 2).
4. Find which CTR-* contracts cover those interactions (Phase 3).
5. Find which SIM-* simulations verify those contracts (Phase 4).
6. Find which build steps implement those components (Phase 5).
7. Find which E2E-* tests verify those features (Phase 6).

Report any broken chain -- an RI-* item that cannot be traced to an E2E
test, or any intermediate element that is orphaned.

### 1. Traceability
- Every RI-* must reach at least one E2E-* through the full chain.
- Every FT-* must be realized by at least one CMP-*.
- Every INT-* must have at least one CTR-*.
- Every CTR-* must have at least one SIM-*.
- Every CMP-* must appear in the build_order.

### 2. Coverage
- Calculate the percentage of RI-* items with complete chains.
- Flag RI-* items that are explicitly out-of-scope (acceptable gaps but
  must be documented in Phase 1's out_of_scope section).
- Flag intermediate elements (FT, CMP, INT, CTR, SIM) not reachable from
  any RI-*.

### 3. Consistency
- All cross-file ID references must resolve.
- No circular dependencies in the traceability chain.
- ID formats must match their expected patterns.

### 4. Integration
- The verification report's coverage_summary must accurately reflect the
  traceability matrix.
- The implementation plan's test coverage must align with Phase 6's E2E tests.
- No phase's output may contradict another phase's output.

## Instructions

1. Read ALL seven phase output files using the Read tool.
2. Build the full traceability chain for every RI-* item.
3. Report broken chains, orphaned elements, and coverage gaps.
4. Produce your verification result as a JSON code block at the end.\
"""


# ---------------------------------------------------------------------------
# Phase-level prompt template
# ---------------------------------------------------------------------------

_CROSS_REF_PROMPT_TEMPLATE = """\
You are verifying the output of Phase {phase_number} ({phase_name}) of an
AI-driven software development methodology.

## Files to inspect

Current phase output:
  {output_path}

Prior phase outputs:
{prior_phases_block}

## Verification checks

Perform these checks in order.  For each check, report every issue
found -- do not stop at the first failure.

{phase_checks}

## Instructions

1. Read each file listed above using the Read tool.  Do not guess contents.
2. Parse the YAML structures and systematically verify each check.
3. Use Grep to search for specific element IDs across files.
4. Produce your verification result as a JSON code block at the end of
   your response.

The overall verdict is "pass" only if all four checks have no blocking
issues.  Warning-severity issues do not block the verdict.\
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_prior_phases_block(completed_phases: list[str]) -> str:
    """Format completed phases as a list of file paths for the prompt."""
    if not completed_phases:
        return "  (none -- this is the first phase)"
    lines: list[str] = []
    for phase_id in completed_phases:
        config = PHASE_MAP.get(phase_id)
        if config is not None:
            lines.append(
                f"  Phase {config.phase_number} ({config.phase_name}): "
                f"{config.output_artifact_path}"
            )
    return "\n".join(lines) if lines else "  (none)"


def _extract_json_block(text: str) -> str | None:
    """Extract the first JSON block from Claude's response.

    Tries fenced code blocks first, then falls back to bare JSON
    starting with a ``"verdict"`` key.
    """
    match = _JSON_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()

    match = _BARE_JSON_RE.search(text)
    if match:
        return match.group(0).strip()

    return None


def _parse_check_result(raw: dict) -> CrossRefCheckResult:
    """Parse a single check category from the JSON result."""
    issues: list[CrossRefIssue] = []
    for issue_raw in raw.get("issues", []):
        issues.append(CrossRefIssue(
            category=str(issue_raw.get("category", "")),
            description=str(issue_raw.get("description", "")),
            affected_elements=[
                str(e) for e in issue_raw.get("affected_elements", [])
            ],
            severity=str(issue_raw.get("severity", "warning")),
        ))
    return CrossRefCheckResult(
        status=str(raw.get("status", "fail")),
        issues=issues,
    )


def _collect_issues(
    result: CrossReferenceResult,
) -> tuple[list[str], list[str], list[str]]:
    """Extract formatted issues, traceability gaps, and orphaned elements.

    Replicates the issue-routing logic from
    :meth:`CrossRefResult.from_cross_reference_result` but returns
    the three lists separately so the caller can combine them with
    actual coverage percentages.
    """
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

    return all_issues, traceability_gaps, orphaned_elements


def _build_coverage_summary(
    result: CrossReferenceResult,
    raw_percentages: dict,
) -> dict[str, float]:
    """Build coverage_summary from Claude's percentages or binary fallback.

    When Claude provides ``coverage_percentages`` in the JSON (values
    from 0 to 100), those are normalised to 0.0-1.0 fractions.  When
    percentages are absent for a category, the summary falls back to
    1.0 if the check passed and 0.0 if it failed.
    """
    checks = [
        result.traceability,
        result.coverage,
        result.consistency,
        result.integration,
    ]
    summary: dict[str, float] = {}
    for cat, chk in zip(_CATEGORY_NAMES, checks):
        raw_pct = raw_percentages.get(cat) if raw_percentages else None
        if raw_pct is not None:
            try:
                pct = float(raw_pct)
                summary[cat] = max(0.0, min(1.0, pct / 100.0))
            except (TypeError, ValueError):
                summary[cat] = 1.0 if chk.status == "pass" else 0.0
        else:
            summary[cat] = 1.0 if chk.status == "pass" else 0.0
    return summary


def _parse_cross_ref_result(claude_output: str) -> CrossRefResult:
    """Parse Claude's output into a CrossRefResult.

    Extracts a JSON code block from the response, parses it into a
    :class:`CrossReferenceResult` for structured issue data, then
    builds a :class:`CrossRefResult` directly -- using Claude's
    ``coverage_percentages`` when present (actual element-level
    coverage) and falling back to binary 1.0/0.0 otherwise.

    Raises :class:`CrossReferenceError` if the output cannot be parsed.
    """
    json_text = _extract_json_block(claude_output)
    if json_text is None:
        raise CrossReferenceError(
            "unknown",
            "No JSON block found in Claude's response.  "
            "Expected a fenced ```json ... ``` block or bare JSON with "
            "a \"verdict\" key.",
        )

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise CrossReferenceError(
            "unknown",
            f"Invalid JSON in Claude's response: {exc}",
        ) from exc

    if not isinstance(data, dict):
        raise CrossReferenceError(
            "unknown",
            f"Expected a JSON object, got {type(data).__name__}.",
        )

    checks = data.get("checks")
    if not isinstance(checks, dict) or not checks:
        raise CrossReferenceError(
            "unknown",
            "Missing or invalid 'checks' key in verification result.",
        )

    structured = CrossReferenceResult(
        verdict=str(data.get("verdict", "fail")),
        traceability=_parse_check_result(
            checks.get("traceability", {}),
        ),
        coverage=_parse_check_result(
            checks.get("coverage", {}),
        ),
        consistency=_parse_check_result(
            checks.get("consistency", {}),
        ),
        integration=_parse_check_result(
            checks.get("integration", {}),
        ),
    )

    all_issues, traceability_gaps, orphaned_elements = _collect_issues(
        structured,
    )
    coverage_summary = _build_coverage_summary(
        structured, data.get("coverage_percentages", {}),
    )

    return CrossRefResult(
        passed=structured.verdict == "pass",
        issues=all_issues,
        traceability_gaps=traceability_gaps,
        orphaned_elements=orphaned_elements,
        coverage_summary=coverage_summary,
    )


def assemble_cross_ref_prompt(
    phase: PhaseConfig,
    completed_phases: list[str],
) -> str:
    """Build the cross-reference verification prompt for a phase.

    Exposed for testing.  The verify functions call this internally.
    """
    template = PHASE_CROSS_REF_CHECKS.get(phase.phase_id)
    if template is None:
        raise CrossReferenceError(
            phase.phase_id,
            f"No cross-reference check template for {phase.phase_id}.",
        )

    phase_checks = template.format(output_path=phase.output_artifact_path)
    prior_block = _format_prior_phases_block(completed_phases)

    return _CROSS_REF_PROMPT_TEMPLATE.format(
        phase_number=phase.phase_number,
        phase_name=phase.phase_name,
        output_path=phase.output_artifact_path,
        prior_phases_block=prior_block,
        phase_checks=phase_checks,
    )


def assemble_end_to_end_prompt() -> str:
    """Build the end-to-end verification prompt.

    Exposed for testing.  The verify_end_to_end function calls this
    internally.  The template is self-contained -- it lists all seven
    phase output paths.
    """
    return END_TO_END_PROMPT_TEMPLATE


def _build_full_prompt(user_prompt: str) -> str:
    """Prepend CROSS_REF_SYSTEM_PROMPT to the user prompt.

    The ``ClaudeCall`` dataclass has no ``system_prompt`` field, so we
    inject the cross-reference instructions (JSON output schema, tool-use
    guidance, severity definitions) as a preamble to the user prompt.
    ``RealClaudeClient`` separately appends ``NON_INTERACTIVE_SYSTEM_PROMPT``
    via ``--append-system-prompt``, so the two are complementary.
    """
    return CROSS_REF_SYSTEM_PROMPT + "\n\n---\n\n" + user_prompt


def _call_claude_for_verification(
    prompt: str,
    phase_id: str,
    workspace: Path,
    model: str | None,
    claude_client: ClaudeClient | None,
) -> CrossRefResult:
    """Invoke Claude with the verification prompt and parse the result.

    Prepends :data:`CROSS_REF_SYSTEM_PROMPT` to *prompt* so Claude
    receives the JSON output schema and tool-use instructions.

    If *claude_client* is None, creates a
    :class:`~prompt_runner.claude_client.RealClaudeClient`.
    """
    from prompt_runner.claude_client import ClaudeCall

    if claude_client is None:
        from prompt_runner.claude_client import RealClaudeClient
        claude_client = RealClaudeClient()

    full_prompt = _build_full_prompt(prompt)

    log_dir = workspace / CROSS_REF_LOG_DIR / phase_id
    log_dir.mkdir(parents=True, exist_ok=True)

    session_id = str(uuid.uuid4())
    call = ClaudeCall(
        prompt=full_prompt,
        session_id=session_id,
        new_session=True,
        model=model,
        stdout_log_path=log_dir / "stdout.log",
        stderr_log_path=log_dir / "stderr.log",
        stream_header=(
            f"[methodology-runner] Cross-reference verification "
            f"for {phase_id}"
        ),
        workspace_dir=workspace,
    )

    try:
        response = claude_client.call(call)
    except Exception as exc:
        raise CrossReferenceError(
            phase_id,
            f"Claude invocation failed: {exc}",
        ) from exc

    content = response.stdout.strip()
    if not content:
        raise CrossReferenceError(
            phase_id,
            "Claude returned an empty response.",
        )

    try:
        return _parse_cross_ref_result(content)
    except CrossReferenceError:
        raise
    except Exception as exc:
        raise CrossReferenceError(
            phase_id,
            f"Failed to parse verification result: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_phase_cross_references(
    phase: PhaseConfig,
    workspace: Path,
    completed_phases: list[str],
    model: str | None = None,
    *,
    claude_client: ClaudeClient | None = None,
) -> CrossRefResult:
    """Run cross-reference verification for a completed phase.

    Calls Claude with tool access to inspect the workspace.  Claude
    checks traceability, coverage, consistency, and integration with
    prior phases.

    Parameters
    ----------
    phase:
        Configuration for the phase that just completed.
    workspace:
        Root of the project workspace.
    completed_phases:
        Phase IDs of all phases completed before this one.
    model:
        Optional Claude model override.
    claude_client:
        Optional injected client (for testing).  Defaults to
        :class:`~prompt_runner.claude_client.RealClaudeClient`.

    Returns
    -------
    CrossRefResult with pass/fail and specific issues.
    """
    prompt = assemble_cross_ref_prompt(phase, completed_phases)
    return _call_claude_for_verification(
        prompt=prompt,
        phase_id=phase.phase_id,
        workspace=workspace,
        model=model,
        claude_client=claude_client,
    )


def verify_end_to_end(
    workspace: Path,
    model: str | None = None,
    *,
    claude_client: ClaudeClient | None = None,
) -> CrossRefResult:
    """Run final end-to-end verification across all phases.

    Called after all 7 phases complete.  Traces every requirement from
    Phase 0 through to Phase 6 and reports any broken chains or
    coverage gaps.

    Parameters
    ----------
    workspace:
        Root of the project workspace.
    model:
        Optional Claude model override.
    claude_client:
        Optional injected client (for testing).  Defaults to
        :class:`~prompt_runner.claude_client.RealClaudeClient`.

    Returns
    -------
    CrossRefResult with pass/fail and specific issues.
    """
    prompt = assemble_end_to_end_prompt()
    return _call_claude_for_verification(
        prompt=prompt,
        phase_id="end-to-end",
        workspace=workspace,
        model=model,
        claude_client=claude_client,
    )
