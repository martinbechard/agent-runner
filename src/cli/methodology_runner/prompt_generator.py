"""Prompt generator for methodology-runner phases.

Assembles a meta-prompt from a PhaseConfig and workspace state, calls
Claude to produce a prompt-runner .md file, validates the output, and
writes it to the workspace.

See docs/design/components/CD-002-methodology-runner.md Section 7.

Public API
----------
generate_phase_prompts(phase, workspace, model)
    Simple API that creates a RealClaudeClient internally.

generate_prompt_file(context, claude_client, output_path, model)
    Testable API accepting a ClaudeClient protocol.

assemble_meta_prompt(context)
    Build the meta-prompt string.  Exposed for testing.

META_PROMPT_TEMPLATE
    Template string with named placeholders.
"""
from __future__ import annotations

import re
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
from .phases import PHASE_MAP, resolve_input_sources

if TYPE_CHECKING:
    from prompt_runner.claude_client import ClaudeClient


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
a generator Claude session produces an artifact and a separate judge
Claude session evaluates it.  The judge can request revisions up to
3 times.  Prior approved artifacts are carried as context to later
prompts.

You must produce a complete .md file.  Do not produce the artifacts
themselves -- produce the prompts that will instruct another Claude
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

The following input files are available in the workspace.  Generators
can Read any of them.  Their content is shown below for your reference
when designing prompts.

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

Example structure:

## Prompt 1: Extract Requirements Checklist

Generation prompt -- instructs the generator what to produce.

```
Read docs/requirements/raw-requirements.md and extract a structured
inventory of all requirements.  Write the result to
docs/requirements/requirements-inventory.yaml using the Write tool.
```

Validation prompt -- tells the judge what to verify.

```
Read docs/requirements/requirements-inventory.yaml.
Evaluate the requirements inventory against these criteria:
1. Every section of raw-requirements.md has at least one item.
2. Each item has a valid RI-NNN id.
End with VERDICT: pass, VERDICT: revise, or VERDICT: escalate.
```

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


def _assemble_input_context(phase: PhaseConfig, workspace: Path) -> str:
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

    blocks: list[str] = []
    for path, role, description in resolved:
        content, truncated = _read_and_truncate(path)
        try:
            rel_path = path.relative_to(workspace)
        except ValueError:
            rel_path = path
        header = f"# Input: {rel_path} (role: {role.value})"
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

def assemble_meta_prompt(context: PromptGenerationContext) -> str:
    """Build the complete meta-prompt string from context.

    Exposed for testing.  The generate_prompt_file function calls this
    internally; tests can call it directly to inspect the assembled
    prompt without invoking Claude.
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
        extraction_focus=phase.extraction_focus,
        artifact_schema_description=phase.artifact_schema_description,
        judge_guidance=phase.judge_guidance,
        checklist_good_block=_format_bullet_list(
            phase.checklist_examples_good,
        ),
        checklist_bad_block=_format_bullet_list(
            phase.checklist_examples_bad,
        ),
        input_context=_assemble_input_context(phase, workspace),
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
    claude_client: ClaudeClient,
    output_path: Path | None = None,
    model: str | None = None,
) -> Path:
    """Call Claude to produce a prompt-runner .md file for a phase.

    Assembles the meta-prompt from the context, calls Claude, validates
    the result, writes it to *output_path* (or a default location), and
    returns the path.

    Raises PromptGenerationError if Claude fails to produce a valid
    prompt-runner file after MAX_GENERATION_ATTEMPTS attempts.
    """
    from prompt_runner.claude_client import ClaudeCall

    phase = context.phase_config
    workspace = context.workspace_dir

    if output_path is None:
        output_dir = workspace / PROMPT_RUNNER_FILES_DIR
        output_path = output_dir / f"{phase.phase_id}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log_dir = workspace / PROMPT_RUNNER_FILES_DIR / "logs" / phase.phase_id
    log_dir.mkdir(parents=True, exist_ok=True)

    meta_prompt = assemble_meta_prompt(context)

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

        session_id = str(uuid.uuid4())
        call = ClaudeCall(
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

        try:
            response = claude_client.call(call)
        except Exception as exc:
            raise PromptGenerationError(
                phase.phase_id,
                f"Claude invocation failed: {exc}",
            ) from exc

        content = response.stdout.strip()
        if not content:
            last_issues = ["Claude returned an empty response"]
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


def generate_phase_prompts(
    phase: PhaseConfig,
    workspace: Path,
    model: str | None = None,
) -> Path:
    """Call Claude to produce a prompt-runner .md file for this phase.

    Simple API that creates a RealClaudeClient internally.  For testable
    code, use generate_prompt_file with a ClaudeClient protocol object.

    Reads the input source files from the workspace, assembles them
    with the phase configuration into a meta-prompt, calls Claude,
    writes the resulting .md file to:
        {workspace}/prompt-runner-files/{phase.phase_id}.md

    Returns the path to the written .md file.
    """
    from prompt_runner.claude_client import RealClaudeClient

    client = RealClaudeClient()
    context = PromptGenerationContext(
        phase_config=phase,
        workspace_dir=workspace,
    )
    return generate_prompt_file(context, client, model=model)
