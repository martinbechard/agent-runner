"""Prompt generator for methodology-runner phases.

Assembles a meta-prompt from a PhaseConfig and workspace state, calls
the configured backend to produce a prompt-runner .md file, validates the output, and
writes it to the workspace.

See .methodology/docs/design/components/CD-002-methodology-runner.md Section 7.

Public API
----------
generate_prompt_file(context, claude_client, output_path, model)
    Testable API accepting an AgentClient protocol.

assemble_meta_prompt(context)
    Build the meta-prompt string.  Exposed for testing.

META_PROMPT_TEMPLATE
    Template string with named placeholders.
"""
from __future__ import annotations

import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .models import (
    CrossReferenceResult,
    InputRole,
    PhaseConfig,
    PhaseSkillManifest,
    PhaseState,
)
from .log_metadata import write_call_metadata
from .phases import PHASE_MAP, resolve_input_sources

if TYPE_CHECKING:
    from prompt_runner.client_types import AgentClient


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_INPUT_FILE_CHARS = 50_000
"""Maximum characters from a single input file before truncation."""

PROMPT_RUNNER_FILES_DIR = "prompt-runner-files"
"""Subdirectory within the workspace for generated prompt-runner .md files."""

MIN_PROMPTS = 1
"""Minimum number of ## Prompt sections in valid output."""

CODE_BLOCKS_PER_PROMPT = 2
"""Each prompt section requires exactly two fenced code blocks."""

MAX_GENERATION_ATTEMPTS = 2
"""Initial attempt plus one retry with validation feedback."""

_HEADING_RE = re.compile(r"^## Prompt \d+:", re.MULTILINE)
"""Matches prompt-runner section headings."""

_FENCE_RE = re.compile(r"^```", re.MULTILINE)
"""Matches code fence boundaries (opening or closing)."""


_PH000_CODEX_TEMPLATE = """\
## Prompt 1: Produce Requirements Inventory [MODEL:gpt-5.4]

```required-files
docs/requirements/raw-requirements.md
```

```
You are producing the phase artifact for PH-000-requirements-inventory.

Read:
- docs/requirements/raw-requirements.md

Write:
- docs/requirements/requirements-inventory.yaml

Task:
Produce the final acceptance-ready YAML requirements inventory in one file.
Use this prompt pair's built-in revise loop to correct any issues the judge
finds. Do not create draft-only or partial versions on purpose.

Use the selected generator skills loaded in the prelude as the primary source
of phase-specific extraction, traceability, and decomposition discipline.
The prompt contract here is intentionally stable:
- read the copied raw requirements from the methodology worktree
- write exactly one acceptance-ready inventory file
- satisfy the required artifact schema and structural rules
- revise that same file until the judge can pass or escalate

Artifact contract:
- Inventory the requirement-bearing content from the source document.
- Preserve exact source wording in each item's verbatim_quote.
- Split independent requirements into separate RI-* items when the selected
  skills determine they are separable.
- Use sequential zero-padded IDs starting at RI-001.
- Use only these categories: functional, non_functional, constraint,
  assumption.
- Include source_location for every item using a consistent section-and-local
  reference scheme.
- Add concise domain tags for cross-referencing.
- For rationale, use:
  rule: the rule applied
  because: why the item is represented separately
- For open_assumptions, include only specifics that go beyond the quote. If
  none, use an empty list.
- Capture explicitly deferred items in out_of_scope with an inventory_ref and
  reason.
- Build coverage_check by mapping requirement-bearing source phrases or bullets
  to the RI-* IDs that cover them.
- Build coverage_verdict with conservative counts and PASS/FAIL based on file
  contents.

Output schema to satisfy:
source_document: "docs/requirements/raw-requirements.md"
items:
  - id: "RI-NNN"
    category: "functional"
    verbatim_quote: "exact source text"
    source_location: "Section > paragraph-or-bullet-id"
    tags: ["..."]
    rationale:
      rule: "..."
      because: "..."
    open_assumptions:
      - id: "ASM-NNN"
        detail: "..."
        needs: "..."
        status: "open"
out_of_scope:
  - inventory_ref: "RI-NNN"
    reason: "..."
coverage_check:
  "phrase from source": ["RI-NNN"]
  status: "N/N phrases covered, 0 orphans, 0 invented"
coverage_verdict:
  total_upstream_phrases: 0
  covered: 0
  orphaned: 0
  out_of_scope: 0
  open_assumptions: 0
  verdict: "PASS"

Acceptance requirements:
- The file must be valid YAML parseable by a standard YAML parser.
- The top-level keys must appear exactly as required:
  source_document
  items
  out_of_scope
  coverage_check
  coverage_verdict
- Every RI-* item must contain:
  id
  category
  verbatim_quote
  source_location
  tags
  rationale
  open_assumptions
- Rationale must contain both rule and because.
- Every open assumption must contain id, detail, needs, and status.
- All RI-* IDs must be unique, sequential, and zero-padded to three digits.
- Do not create any files other than docs/requirements/requirements-inventory.yaml.
- Use the Write tool to write the full file contents to docs/requirements/requirements-inventory.yaml.
```

```
Read:
- docs/requirements/raw-requirements.md
- docs/requirements/requirements-inventory.yaml

Run the PH-000 acceptance review with a requirements-quality and traceability mindset.
Use the selected judge skills loaded in the prelude as the primary source of
phase-specific review discipline. The stable prompt contract here is to decide
whether the generated file satisfies the PH-000 artifact contract and the
selected review skills, then drive revision through this prompt pair's built-in
loop.

Acceptance checklist:
1. Every requirement-bearing source statement is represented by at least one
   RI-* item or an explicit out_of_scope entry when the source clearly defers it.
2. Every verbatim_quote can be found verbatim in the source document.
3. Any unsplit compound requirement, invented requirement, unsupported
   assumption, or category drift identified by the selected judge skills is
   called out explicitly.
4. source_location values are specific and consistent enough to trace each
   item back to the original document quickly.
5. The YAML structure matches the required top-level keys and item fields.
6. coverage_check maps source phrases to RI-* IDs precisely rather than
   summarizing loosely.
7. coverage_verdict counts are internally consistent with the file contents and
   remain conservative.
8. out_of_scope contains only explicitly deferred items from the source.

Review instructions:
- Compare section by section.
- Flag missing traceability, invented text, category drift, and unsplit compounds explicitly.
- If you find issues, cite the exact RI-* IDs or missing source locations involved.
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary
- Use VERDICT: pass only if the artifact is phase-ready with no material omissions or traceability defects.
- Use VERDICT: revise if the artifact can be corrected within this same file.
- Use VERDICT: escalate only if the source is too ambiguous or contradictory to inventory faithfully without external clarification.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
"""


def _deterministic_prompt_file_content(
    context: PromptGenerationContext,
) -> str | None:
    """Return a canned prompt-runner file when the phase has a stable template."""
    if (
        context.input_context_mode == "file-reference"
        and context.phase_config.phase_id == "PH-000-requirements-inventory"
    ):
        return _PH000_CODEX_TEMPLATE
    return None


# ---------------------------------------------------------------------------
# Error types (CD-002 Section 10.3)
# ---------------------------------------------------------------------------

class PromptGenerationError(Exception):
    """Raised when prompt file generation fails."""

    def __init__(self, phase_id: str, reason: str) -> None:
        super().__init__(f"Phase {phase_id}: {reason}")
        self.phase_id = phase_id
        self.reason = reason


# ---------------------------------------------------------------------------
# Context dataclass (CD-002 Section 10.3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PromptGenerationContext:
    """Everything needed to generate a prompt-runner input file."""

    phase_config: PhaseConfig
    workspace_dir: Path
    completed_phases: list[PhaseState] = field(default_factory=list)
    cross_ref_feedback: CrossReferenceResult | None = None
    phase_skill_manifest: "PhaseSkillManifest | None" = None
    input_context_mode: str = "embed"


# ---------------------------------------------------------------------------
# Meta-prompt template (CD-002 Section 7.2)
# ---------------------------------------------------------------------------

META_PROMPT_TEMPLATE = """\
## ROLE AND TASK

You are a prompt architect for an AI-driven software development
pipeline.  Your job is to produce a prompt-runner input file (.md)
that, when executed by prompt-runner, will produce the artifacts
for one phase of the methodology.

prompt-runner executes each prompt pair sequentially.  For each pair,
a generator session produces an artifact and a separate judge
session evaluates it.  The judge can request revisions up to
3 times.  Prior approved artifacts are carried as context to later
prompts.

You must produce a complete .md file.  Do not produce the artifacts
themselves -- produce the prompts that will instruct another agent
to produce them.

YOUR ENTIRE RESPONSE must be a valid prompt-runner markdown file and
nothing else.  No preamble, no explanation, no commentary outside
the file content.

---

## PHASE CONFIGURATION

Phase: {phase_id} -- {phase_name}

Purpose:
{generation_instructions}

Input artifacts (files that exist in the workspace and can be read
by generators):
{input_artifacts_block}

Output artifact:
  - Path: {output_artifact_path}
  - Format: {output_format}

Expected output files:
{expected_output_files_block}

Deterministic validation helper:
{deterministic_validation_block}

Extraction focus (what the phase's checklist should verify):
{extraction_focus}

Artifact schema:
{artifact_schema_description}

Judge guidance (what the judge should specifically look for):
{judge_guidance}

Example good checklist items (calibrate quality -- criteria at this
level of specificity):
{checklist_good_block}

Example bad checklist items (too vague -- avoid this level):
{checklist_bad_block}

---

## INPUT CONTEXT

{input_context_intro}

{input_context}

---

## PRIOR PHASE CONTEXT

{prior_phases_block}

---

## PROMPT-RUNNER FORMAT CONSTRAINTS

Your output must be a valid prompt-runner input file.  The format is:

1. The file contains one or more prompt sections.
2. Each section starts with a level-2 heading:
   ## Prompt N: Descriptive Title
3. Each section contains exactly two fenced code blocks (triple
   backticks).  The first is the generation prompt, the second is
   the validation prompt.
4. CRITICAL: prompt bodies must NOT contain triple-backtick fences
   inside them.  If a prompt needs to show code examples, use
   4-space indentation or describe the code in prose.
5. Prose, notes, and explanations may appear between the heading
   and first fence, between the fences, and after the second fence
   -- but they are ignored by prompt-runner.
6. Optional typed blocks may appear before the generation prompt.
   The available typed block names are:
   - required-files
   - checks-files
   - deterministic-validation
   The deterministic-validation block is a Python argv list. prompt-runner
   executes that script after the generator writes files and before the judge
   runs, then injects the script's stdout, stderr, and return code into the
   judge prompt.

---

## DECOMPOSITION GUIDANCE

Decide how many prompts are needed based on the complexity of what
this phase must produce.  Guidelines:

- Simple phases (Phase 0: flat extraction): 2-3 prompts.
- Medium phases (Phase 1-2: structuring and design): 3-5 prompts.
- Complex phases (Phase 3-5: contracts, simulations, implementation):
  4-7 prompts.

Each prompt should produce a coherent, self-contained increment.
Later prompts build on earlier ones.  Common decomposition patterns:

- Extract-then-structure: first prompt extracts raw data, second
  organises it, third fills in details.
- Section-by-section: one prompt per major section of the output
  artifact.
- Scaffold-then-populate: first prompt creates the skeleton with
  IDs and structure, subsequent prompts fill in content.

Each generation prompt must instruct the generator to write files
in the workspace using the Write tool.  Tell it exactly which file
path to write to.

Each validation prompt must tell the judge what to verify.  Include:
- Specific checklist criteria (derived from the extraction focus).
- Instructions to Read the generated file and check structure.
- Instructions to verify traceability to input artifacts.
- The verdict instruction: end with VERDICT: pass, VERDICT: revise,
  or VERDICT: escalate.

---

## WORKSPACE CONVENTIONS

- Phase output goes in the workspace root at the output artifact
  path shown above.
- Generators have full tool access (Read, Write, Bash).
- Files are tracked by git; judges see the diff.
- The workspace root is the generators' cwd.
{cross_ref_feedback_block}"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_and_truncate(path: Path) -> tuple[str, bool]:
    """Read a file, truncating if it exceeds MAX_INPUT_FILE_CHARS.

    Returns (content, was_truncated).
    """
    content = path.read_text(encoding="utf-8")
    if len(content) <= MAX_INPUT_FILE_CHARS:
        return content, False
    return content[:MAX_INPUT_FILE_CHARS], True


def _assemble_input_context(
    phase: PhaseConfig,
    workspace: Path,
    *,
    mode: str = "embed",
) -> str:
    """Read input files and assemble them into a context block.

    Each input file is rendered with a header showing its resolved path
    and role.  Files exceeding MAX_INPUT_FILE_CHARS are truncated with
    a note.  Missing files raise PromptGenerationError.
    """
    resolved = resolve_input_sources(phase, workspace)
    missing = [(p, desc) for p, _role, desc in resolved if not p.exists()]
    if missing:
        details = "\n".join(f"  - {p} ({desc})" for p, desc in missing)
        predecessors = (
            ", ".join(phase.predecessors)
            if phase.predecessors
            else "(none -- this is the first phase)"
        )
        raise PromptGenerationError(
            phase.phase_id,
            f"Input files missing (expected from predecessors: "
            f"{predecessors}):\n{details}",
        )

    if mode not in ("embed", "file-reference"):
        raise PromptGenerationError(
            phase.phase_id,
            f"unknown input context mode: {mode!r}",
        )

    blocks: list[str] = []
    for path, role, description in resolved:
        try:
            rel_path = path.relative_to(workspace)
        except ValueError:
            rel_path = path
        header = f"# Input: {rel_path} (role: {role.value})"
        if mode == "file-reference":
            block = (
                f"{header}\n"
                f"# {description}\n\n"
                f"Read this file directly from the workspace when designing "
                f"prompts: {rel_path}"
            )
        else:
            content, truncated = _read_and_truncate(path)
            block = f"{header}\n# {description}\n\n{content}"
            if truncated:
                block += (
                    f"\n\n[... truncated at {MAX_INPUT_FILE_CHARS:,} characters."
                    f"  Generators should Read the full file directly. ...]"
                )
        blocks.append(block)

    return "\n\n---\n\n".join(blocks) if blocks else "(no input files)"


def _format_bullet_list(items: list[str]) -> str:
    """Format a list of strings as a markdown bullet list."""
    if not items:
        return "(none)"
    return "\n".join(f"- {item}" for item in items)


def _format_input_artifacts_block(
    phase: PhaseConfig, workspace: Path,
) -> str:
    """Format input artifacts summary (paths and roles, no content)."""
    resolved = resolve_input_sources(phase, workspace)
    if not resolved:
        return "  (no input artifacts -- this is the first phase)"
    lines: list[str] = []
    for path, role, description in resolved:
        try:
            rel_path = path.relative_to(workspace)
        except ValueError:
            rel_path = path
        lines.append(f"  - {rel_path} (role: {role.value})")
        lines.append(f"    {description}")
    return "\n".join(lines)


def _format_expected_files_block(files: list[str]) -> str:
    """Format expected output files as a bullet list."""
    return "\n".join(f"  - {f}" for f in files)


def _prepare_deterministic_validation_helper(
    phase: PhaseConfig,
    output_dir: Path,
) -> Path | None:
    if phase.phase_id != "PH-001-feature-specification":
        return None
    source = Path(__file__).with_name("phase_1_validation.py")
    helper_path = output_dir / "phase-1-deterministic-validation.py"
    helper_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, helper_path)
    return helper_path


def _format_deterministic_validation_block(helper_path: Path | None) -> str:
    if helper_path is None:
        return "  (no staged helper for this phase)"
    return "\n".join(
        [
            f"  - Script path: {helper_path}",
            "  - If you use deterministic validation, add one top-level",
            "    typed block named `deterministic-validation` before the",
            "    generator prompt for the prompt pair that writes",
            "    `docs/features/feature-specification.yaml`.",
            "  - The block's argv lines should be, in order:",
            f"    1. {helper_path}",
            "    2. --feature-spec",
            "    3. docs/features/feature-specification.yaml",
            "    4. --requirements-inventory",
            "    5. docs/requirements/requirements-inventory.yaml",
            "  - Do not show this block as a fenced example inside a prompt body;",
            "    place it directly as a top-level typed block in the generated",
            "    prompt-runner file.",
            "  - Use this helper for deterministic schema, RI-coverage, dependency-target,",
            "    and cross-cutting-concern cardinality checks so the judge can focus on",
            "    semantic issues and unsupported scope.",
        ]
    )


def _format_prior_phases_block(completed_phases: list[PhaseState]) -> str:
    """Format prior completed phases with their artifact paths."""
    if not completed_phases:
        return (
            "No prior phases have completed yet.  This is the first phase."
        )

    lines = ["The following phases have already completed:"]
    for ps in completed_phases:
        config = PHASE_MAP.get(ps.phase_id)
        phase_name = config.phase_name if config else ps.phase_id
        artifact_path = (
            config.output_artifact_path if config else "(unknown)"
        )
        lines.append(f"  Phase {ps.phase_id}: {phase_name}")
        lines.append(f"    Output: {artifact_path}")
        lines.append(f"    Status: {ps.status.value}")
    lines.append("")
    lines.append(
        "The artifacts from these phases are available in the workspace."
    )
    lines.append(
        "Your prompts should instruct generators to Read them as needed."
    )
    return "\n".join(lines)


def _format_skill_manifest_block(manifest: PhaseSkillManifest) -> str:
    """Return a short human-readable summary of the phase's skill manifest.

    This is prepended to the meta-prompt so the prompt architect is
    aware of which skills will be active for the generator and judge
    when the prompt-runner file executes.  Note: the actual skill
    loading happens via the prelude, not the meta-prompt — this
    section is purely informational for the architect.
    """
    lines = [
        "## PHASE SKILL MANIFEST",
        "",
        f"The Skill-Selector has chosen the following skills for "
        f"{manifest.phase_id}.",
        "Generator calls will load these via a prelude; judge calls "
        "load their own set.",
        "",
        "Generator skills:",
    ]
    if manifest.generator_skills:
        for sc in manifest.generator_skills:
            lines.append(f"  - {sc.id} ({sc.source.value})")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("Judge skills:")
    if manifest.judge_skills:
        for sc in manifest.judge_skills:
            lines.append(f"  - {sc.id} ({sc.source.value})")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append(f"Rationale: {manifest.overall_rationale}")
    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def _format_cross_ref_feedback(
    feedback: CrossReferenceResult | None,
) -> str:
    """Format cross-reference feedback as Section 7 of the meta-prompt.

    Returns an empty string when there is no feedback (first attempt).
    """
    if feedback is None:
        return ""

    lines: list[str] = [
        "\n---\n",
        "## CROSS-REFERENCE FEEDBACK",
        "",
        "The previous execution of this phase's prompts completed, but",
        "cross-reference verification found the following issues:",
        "",
    ]

    for category_name, check_result in [
        ("traceability", feedback.traceability),
        ("coverage", feedback.coverage),
        ("consistency", feedback.consistency),
        ("integration", feedback.integration),
    ]:
        for issue in check_result.issues:
            lines.append(f"  - Category: {category_name}")
            lines.append(f"    Description: {issue.description}")
            elements = ", ".join(issue.affected_elements)
            lines.append(f"    Affected elements: {elements}")
            lines.append(f"    Severity: {issue.severity}")
            lines.append("")

    lines.append("Your revised prompt file must address these issues.")
    lines.append("Ensure that generators produce artifacts that resolve")
    lines.append("every blocking issue listed above.")
    return "\n".join(lines)


def _validate_prompt_runner_file(content: str) -> list[str]:
    """Validate structural correctness of a prompt-runner .md file.

    Returns a list of issues found.  Empty list means the file is valid.
    Checks:
    - At least one ``## Prompt N:`` heading exists.
    - Each section has exactly two fenced code blocks (4 fence markers).
    """
    issues: list[str] = []

    headings = _HEADING_RE.findall(content)
    if len(headings) < MIN_PROMPTS:
        issues.append(
            f"Expected at least {MIN_PROMPTS} '## Prompt N:' heading(s), "
            f"found {len(headings)}"
        )
        return issues

    # Split content by headings; sections[0] is the preamble,
    # sections[1:] are the section bodies.
    sections = _HEADING_RE.split(content)
    section_bodies = sections[1:]
    expected_fences = CODE_BLOCKS_PER_PROMPT * 2  # open + close per block

    for i, body in enumerate(section_bodies, start=1):
        fences = _FENCE_RE.findall(body)
        fence_count = len(fences)
        if fence_count < expected_fences:
            issues.append(
                f"Prompt {i}: expected {expected_fences} fence markers "
                f"({CODE_BLOCKS_PER_PROMPT} code blocks), "
                f"found {fence_count}"
            )
        elif fence_count > expected_fences:
            issues.append(
                f"Prompt {i}: found {fence_count} fence markers "
                f"(expected {expected_fences}) -- possible nested "
                f"fences inside a code block"
            )

    return issues


# ---------------------------------------------------------------------------
# Meta-prompt assembly (CD-002 Section 10.3)
# ---------------------------------------------------------------------------

def assemble_meta_prompt(
    context: PromptGenerationContext,
    *,
    deterministic_validation_helper_path: Path | None = None,
) -> str:
    """Build the complete meta-prompt string from context.

    Exposed for testing.  The generate_prompt_file function calls this
    internally; tests can call it directly to inspect the assembled
    prompt without invoking the backend.
    """
    phase = context.phase_config
    workspace = context.workspace_dir

    meta = META_PROMPT_TEMPLATE.format(
        phase_id=phase.phase_id,
        phase_name=phase.phase_name,
        generation_instructions=phase.generation_instructions,
        input_artifacts_block=_format_input_artifacts_block(
            phase, workspace,
        ),
        output_artifact_path=phase.output_artifact_path,
        output_format=phase.output_format,
        expected_output_files_block=_format_expected_files_block(
            phase.expected_output_files,
        ),
        deterministic_validation_block=_format_deterministic_validation_block(
            deterministic_validation_helper_path,
        ),
        extraction_focus=phase.extraction_focus,
        artifact_schema_description=phase.artifact_schema_description,
        judge_guidance=phase.judge_guidance,
        checklist_good_block=_format_bullet_list(
            phase.checklist_examples_good,
        ),
        checklist_bad_block=_format_bullet_list(
            phase.checklist_examples_bad,
        ),
        input_context_intro=(
            "The following input files are available in the workspace.  "
            "Generators can Read any of them.  Their content is shown below "
            "for your reference when designing prompts."
            if context.input_context_mode == "embed"
            else
            "The following input files are available in the workspace.  "
            "Do not rely on inlined file contents; read the files directly "
            "from the workspace when you need more detail while designing "
            "prompts."
        ),
        input_context=_assemble_input_context(
            phase,
            workspace,
            mode=context.input_context_mode,
        ),
        prior_phases_block=_format_prior_phases_block(
            context.completed_phases,
        ),
        cross_ref_feedback_block=_format_cross_ref_feedback(
            context.cross_ref_feedback,
        ),
    )
    if context.phase_skill_manifest is not None:
        skill_block = _format_skill_manifest_block(context.phase_skill_manifest)
        meta = f"{skill_block}\n\n{meta}"
    return meta


# ---------------------------------------------------------------------------
# Generation functions
# ---------------------------------------------------------------------------

def generate_prompt_file(
    context: PromptGenerationContext,
    claude_client: AgentClient,
    output_path: Path | None = None,
    model: str | None = None,
) -> Path:
    """Call the configured backend to produce a prompt-runner .md file for a phase.

    Assembles the meta-prompt from the context, calls the backend, validates
    the result, writes it to *output_path* (or a default location), and
    returns the path.

    Raises PromptGenerationError if the backend fails to produce a valid
    prompt-runner file after MAX_GENERATION_ATTEMPTS attempts.
    """
    from prompt_runner.client_types import AgentCall

    phase = context.phase_config
    workspace = context.workspace_dir

    if output_path is None:
        output_dir = workspace / PROMPT_RUNNER_FILES_DIR
        output_path = output_dir / f"{phase.phase_id}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    deterministic_validation_helper = _prepare_deterministic_validation_helper(
        phase,
        output_path.parent,
    )

    log_dir = workspace / PROMPT_RUNNER_FILES_DIR / "logs" / phase.phase_id
    log_dir.mkdir(parents=True, exist_ok=True)

    deterministic = _deterministic_prompt_file_content(context)
    if deterministic is not None:
        output_path.write_text(deterministic + "\n", encoding="utf-8")
        return output_path

    meta_prompt = assemble_meta_prompt(
        context,
        deterministic_validation_helper_path=deterministic_validation_helper,
    )

    last_issues: list[str] = []
    for attempt in range(MAX_GENERATION_ATTEMPTS):
        prompt = meta_prompt
        if attempt > 0 and last_issues:
            prompt += (
                "\n\n---\n\n## RETRY FEEDBACK\n\n"
                "Your previous response was not a valid prompt-runner "
                "file.  Issues found:\n"
                + "\n".join(f"- {issue}" for issue in last_issues)
                + "\n\nPlease produce a corrected version."
            )

        prompt_input_path = log_dir / f"attempt-{attempt + 1}-input-prompt.md"
        prompt_input_path.write_text(prompt, encoding="utf-8")

        session_id = str(uuid.uuid4())
        call = AgentCall(
            prompt=prompt,
            session_id=session_id,
            new_session=True,
            model=model,
            stdout_log_path=log_dir / f"attempt-{attempt + 1}-stdout.log",
            stderr_log_path=log_dir / f"attempt-{attempt + 1}-stderr.log",
            stream_header=(
                f"[methodology-runner] Generating prompt file for "
                f"{phase.phase_id} (attempt {attempt + 1}/"
                f"{MAX_GENERATION_ATTEMPTS})"
            ),
            workspace_dir=workspace,
        )
        write_call_metadata(
            call.stdout_log_path,
            model=model,
            role="prompt-generator",
        )

        try:
            response = claude_client.call(call)
        except Exception as exc:
            raise PromptGenerationError(
                phase.phase_id,
                f"backend invocation failed: {exc}",
            ) from exc

        content = response.stdout.strip()
        if not content:
            last_issues = ["backend returned an empty response"]
            continue

        last_issues = _validate_prompt_runner_file(content)
        if not last_issues:
            output_path.write_text(content + "\n", encoding="utf-8")
            return output_path

    issue_text = "\n".join(f"  - {i}" for i in last_issues)
    raise PromptGenerationError(
        phase.phase_id,
        f"Failed to produce a valid prompt-runner file after "
        f"{MAX_GENERATION_ATTEMPTS} attempts.  Last issues:\n"
        f"{issue_text}",
    )
