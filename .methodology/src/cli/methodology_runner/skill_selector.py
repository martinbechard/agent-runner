"""Skill-Selector agent.

Runs once per phase before the phase's meta-prompt.  Assembles a
selector prompt from the phase definition, the compact skill catalog,
prior phase artifacts, and the stack manifest (if any), invokes
the configured backend, parses the JSON reply, and validates it against the
catalog and the baseline config.

On success, returns a :class:`PhaseSkillManifest` ready to be written
to the workspace as ``phase-NNN-skills.yaml`` and used to build
preludes.  On any validation failure, raises :class:`SelectorError`
so the orchestrator can halt the phase (critical halt semantics per
spec section 12).

See spec section 6 for the selector design.
"""
from __future__ import annotations

import uuid
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .artifact_summarizer import ArtifactSummaryProvider
from .constants import MAX_SKILLS_PER_PHASE
from .log_metadata import write_call_metadata
from .models import (
    BaselineSkillConfig,
    PhaseConfig,
    PhaseSkillManifest,
    SkillCatalogEntry,
    SkillChoice,
    SkillSource,
)

if TYPE_CHECKING:
    from prompt_runner.client_types import AgentClient


class SelectorError(RuntimeError):
    """Raised on any selector invocation or validation failure."""


@dataclass(frozen=True)
class SelectorInputs:
    """Everything the selector needs to decide a phase's skill set."""

    phase_config: PhaseConfig
    catalog: dict[str, SkillCatalogEntry]
    baseline_config: BaselineSkillConfig
    workspace_dir: Path
    prior_artifact_paths: list[Path]
    stack_manifest_path: Path | None


_SELECTOR_SYSTEM_PROMPT = """\
You are the Skill-Selector for an AI-driven software development
methodology pipeline.  Your sole job is to choose which skills
the generator agent and the judge agent should load for one
specific phase of the pipeline.

You do not generate artifacts, you do not evaluate artifacts, and
you do not modify any prior work.  You only pick skills.

## Inputs you will receive

1. The phase definition (purpose, inputs, outputs, quality focus).
2. A baseline skill list for this phase that MUST appear in your
   output unchanged, with source: baseline.
3. The compact skill catalog: every available skill ID with its
   one-line description only.  No skill body content.
4. Summaries (or full content) of every prior-phase artifact in
   the workspace.
5. The stack manifest, if it exists yet (from PH-002 Architecture
   or later).  Read its expected_expertise lists carefully — each
   entry is a free-text description of the kind of knowledge a
   component needs.  Map each description to one or more concrete
   skill IDs from the catalog.

## Output contract

Your entire response MUST be a single valid JSON object with
EXACTLY these top-level keys (no extras, no prose before or after):

    "phase_id":          the phase ID (string)
    "selector_run_at":   ISO 8601 timestamp
    "selector_model":    the model you are running as (string)
    "generator_skills":  list of skill choices for the generator
    "judge_skills":      list of skill choices for the judge
    "overall_rationale": free text explaining the selection as a whole

Every entry in generator_skills and judge_skills must have:

    "id":         a skill ID that exists in the catalog
    "source":     one of "baseline", "expertise-mapping", "selector-judgment"
    "rationale":  why you picked it (non-empty)

Entries with source "expertise-mapping" MUST include:

    "mapped_from": the exact expertise string from the stack manifest

## Rules you must follow

- Every baseline skill must appear in your output with source: baseline.
- Every skill ID you emit must exist in the catalog.
- Never invent skill IDs.  If you believe a skill is missing from the
  catalog, say so in overall_rationale but do NOT include it in the
  lists.
- The combined unique skill count (generator + judge) must not
  exceed {max_skills}.  If you want more, prioritize and explain the
  trade-off in overall_rationale.

Do not wrap your JSON in a code fence.  Do not prepend or append
any prose.  Your entire response is the JSON object.
"""


def _build_compact_catalog_block(catalog: dict[str, SkillCatalogEntry]) -> str:
    lines = []
    for skill_id in sorted(catalog):
        entry = catalog[skill_id]
        lines.append(f"- id: {skill_id}")
        lines.append(f"  description: {entry.description}")
    return "\n".join(lines)


def _build_prior_artifacts_block(
    summarizer: ArtifactSummaryProvider, paths: list[Path],
) -> str:
    if not paths:
        return "(no prior artifacts — this is the first phase)"
    blocks: list[str] = []
    for path in paths:
        try:
            result = summarizer.get(path)
        except FileNotFoundError:
            blocks.append(f"### {path}\n\n(file not found on disk)")
            continue
        if result.full_content is not None:
            blocks.append(
                f"### {path}  ({result.size_bytes} bytes — full content)\n\n"
                f"```\n{result.full_content}\n```"
            )
        else:
            blocks.append(
                f"### {path}  ({result.size_bytes} bytes — AI summary)\n\n"
                f"{result.summary}"
            )
    return "\n\n".join(blocks)


def _build_stack_manifest_block(path: Path | None) -> str:
    if path is None or not path.exists():
        return (
            "(no stack manifest yet — this phase runs before or as "
            "PH-002 Architecture)"
        )
    return f"```yaml\n{path.read_text(encoding='utf-8')}\n```"


def _assemble_selector_prompt(
    inputs: SelectorInputs,
    summarizer: ArtifactSummaryProvider,
    selector_model: str | None,
) -> str:
    gen_base, jud_base = inputs.baseline_config.baselines_for(
        inputs.phase_config.phase_id,
    )
    system = _SELECTOR_SYSTEM_PROMPT.format(max_skills=MAX_SKILLS_PER_PHASE)
    return f"""{system}

---

# Phase definition

Phase ID: {inputs.phase_config.phase_id}
Phase name: {inputs.phase_config.phase_name}
Purpose / generation instructions:
{inputs.phase_config.generation_instructions}

Judge guidance:
{inputs.phase_config.judge_guidance}

---

# Baseline skills for this phase (MUST appear with source: baseline)

Generator baseline: {', '.join(gen_base) or '(none)'}
Judge baseline:     {', '.join(jud_base) or '(none)'}

---

# Compact skill catalog

{_build_compact_catalog_block(inputs.catalog)}

---

# Stack manifest

{_build_stack_manifest_block(inputs.stack_manifest_path)}

---

# Prior phase artifacts

{_build_prior_artifacts_block(summarizer, inputs.prior_artifact_paths)}

---

Produce the phase-skills JSON for phase {inputs.phase_config.phase_id}.
Remember: your entire response is a single JSON object; no code fence,
no commentary.

Use {selector_model or 'the current model'} as the selector_model value.
Use {datetime.now(timezone.utc).isoformat()} as the selector_run_at value.
"""


def _parse_and_validate(
    json_text: str,
    inputs: SelectorInputs,
) -> PhaseSkillManifest:
    try:
        raw = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise SelectorError(
            f"selector output is not parseable JSON: {exc}\n\n"
            f"Raw output:\n{json_text}"
        ) from exc

    if not isinstance(raw, dict):
        raise SelectorError(
            f"selector output must be a JSON object, got {type(raw).__name__}"
        )

    required_top = {
        "phase_id", "selector_run_at", "selector_model",
        "generator_skills", "judge_skills", "overall_rationale",
    }
    missing = required_top - set(raw.keys())
    if missing:
        raise SelectorError(
            f"selector output missing required top-level fields: "
            f"{sorted(missing)}"
        )

    def _parse_skill_list(key: str) -> list[SkillChoice]:
        items = raw.get(key)
        if not isinstance(items, list):
            raise SelectorError(f"{key} must be a list")
        out: list[SkillChoice] = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise SelectorError(f"{key}[{i}] must be a mapping")
            if "id" not in item or "source" not in item or "rationale" not in item:
                raise SelectorError(
                    f"{key}[{i}] missing required fields (id, source, rationale)"
                )
            try:
                source = SkillSource(item["source"])
            except ValueError as exc:
                raise SelectorError(
                    f"{key}[{i}] has invalid source {item['source']!r}: "
                    f"must be one of {[s.value for s in SkillSource]}"
                ) from exc
            out.append(
                SkillChoice(
                    id=item["id"],
                    source=source,
                    rationale=str(item["rationale"]),
                    mapped_from=item.get("mapped_from"),
                )
            )
        return out

    generator = _parse_skill_list("generator_skills")
    judge = _parse_skill_list("judge_skills")

    # All IDs must exist in catalog
    unknown_gen = [s.id for s in generator if s.id not in inputs.catalog]
    unknown_jud = [s.id for s in judge if s.id not in inputs.catalog]
    if unknown_gen or unknown_jud:
        raise SelectorError(
            "selector picked unknown skill IDs not in catalog:\n"
            + "".join(f"  - generator: {s}\n" for s in unknown_gen)
            + "".join(f"  - judge: {s}\n" for s in unknown_jud)
        )

    # Baselines must all be present
    gen_base, jud_base = inputs.baseline_config.baselines_for(
        inputs.phase_config.phase_id,
    )
    gen_ids = {s.id for s in generator if s.source == SkillSource.BASELINE}
    jud_ids = {s.id for s in judge if s.source == SkillSource.BASELINE}
    missing_gen = [b for b in gen_base if b not in gen_ids]
    missing_jud = [b for b in jud_base if b not in jud_ids]
    if missing_gen or missing_jud:
        raise SelectorError(
            "selector output missing required baseline skills:\n"
            + "".join(f"  - generator baseline: {s}\n" for s in missing_gen)
            + "".join(f"  - judge baseline: {s}\n" for s in missing_jud)
        )

    # Cap check
    unique_total = len({s.id for s in generator} | {s.id for s in judge})
    if unique_total > MAX_SKILLS_PER_PHASE:
        raise SelectorError(
            f"selector picked {unique_total} unique skills but cap is "
            f"{MAX_SKILLS_PER_PHASE}"
        )

    return PhaseSkillManifest(
        phase_id=raw["phase_id"],
        selector_run_at=raw["selector_run_at"],
        selector_model=raw["selector_model"],
        generator_skills=generator,
        judge_skills=judge,
        overall_rationale=str(raw["overall_rationale"]),
    )


def invoke_skill_selector(
    inputs: SelectorInputs,
    *,
    claude_client: "AgentClient",
    model: str | None,
) -> PhaseSkillManifest:
    """Run the Skill-Selector for *inputs.phase_config*.

    Assembles the selector prompt, invokes the configured backend, parses and
    validates the JSON reply, and returns a ``PhaseSkillManifest``.
    """
    cache_dir = inputs.workspace_dir / ".methodology-runner" / "artifact-summaries"
    summarizer = ArtifactSummaryProvider(
        cache_dir=cache_dir,
        claude_client=claude_client,
        model=model,
    )
    prompt = _assemble_selector_prompt(inputs, summarizer, selector_model=model)

    from prompt_runner.client_types import AgentCall, AgentInvocationError

    logs_dir = inputs.workspace_dir / ".methodology-runner" / "runs" / "selector-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stem = f"selector-{inputs.phase_config.phase_id}-{uuid.uuid4().hex[:8]}"
    call = AgentCall(
        prompt=prompt,
        session_id=str(uuid.uuid4()),
        new_session=True,
        model=model,
        stdout_log_path=logs_dir / f"{stem}.stdout.log",
        stderr_log_path=logs_dir / f"{stem}.stderr.log",
        stream_header=f"── skill-selector / {inputs.phase_config.phase_id} ──",
        worktree_dir=inputs.workspace_dir,
    )
    write_call_metadata(
        call.stdout_log_path,
        model=model,
        role="skill-selector",
    )
    try:
        response = claude_client.call(call)
    except AgentInvocationError as exc:
        raise SelectorError(
            f"skill-selector backend call failed: {exc}"
        ) from exc

    return _parse_and_validate(response.stdout, inputs)
