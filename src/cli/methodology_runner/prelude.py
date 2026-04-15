"""Build generator and judge prelude text from a PhaseSkillManifest.

Three designs exist in parallel:

- ``skill-tool`` (primary): the prelude instructs the agent to load
  skills by exact ID.  SKILL.md body content is NOT included; the
  agent loads it just-in-time.
- ``inline`` (fallback): the prelude embeds the full SKILL.md body
  (minus frontmatter) of every selected skill.  Zero dependency on
  the Skill tool, but larger prelude size.  ``MAX_SKILLS_PER_PHASE``
  is a hard cap under this design.
- ``file-reference`` (lightweight fallback): the prelude lists the
  selected local ``SKILL.md`` files and instructs the agent to read
  them before starting the task.  This avoids both backend-specific
  Skill tool wording and the prompt bloat of full inline embedding.

The choice of design is driven by ``constants.SKILL_LOADING_MODE``,
which Phase 0 validation sets to the working mode.  Callers can
override by passing an explicit ``mode`` argument to
:func:`build_prelude`.

See spec section 9.
"""
from __future__ import annotations

import re
from pathlib import Path

from .constants import SKILL_LOADING_MODE
from .models import (
    PhaseSkillManifest,
    PreludeSpec,
    SkillCatalogEntry,
    SkillChoice,
)


class PreludeBuildError(RuntimeError):
    """Raised when a prelude cannot be constructed."""


_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
"""Matches and removes the YAML frontmatter at the start of a SKILL.md body."""


_SEPARATOR = "═══════════════════════════════════════════════════════════"


def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1).lstrip()


def _resolve_skills(
    choices: list[SkillChoice],
    catalog: dict[str, SkillCatalogEntry],
) -> list[tuple[SkillChoice, SkillCatalogEntry]]:
    resolved: list[tuple[SkillChoice, SkillCatalogEntry]] = []
    missing: list[str] = []
    for choice in choices:
        entry = catalog.get(choice.id)
        if entry is None:
            missing.append(choice.id)
            continue
        resolved.append((choice, entry))
    if missing:
        raise PreludeBuildError(
            "prelude references skills not in catalog: " + ", ".join(missing)
        )
    return resolved


def _review_output_instruction(
    role: str,
    resolved: list[tuple[SkillChoice, SkillCatalogEntry]],
) -> str:
    if role != "Judge":
        return ""
    ids = {choice.id for choice, _ in resolved}
    if "structured-debate" not in ids and "rule-writing" not in ids:
        return ""

    lines = [
        "Feedback discipline for this judge call:",
        "- When you return revise feedback, make the reasoning inspectable rather than conversational.",
    ]
    if "structured-debate" in ids:
        lines.extend([
            "- For each major finding, explicitly separate the claim under review, the objection, the assessment, and the impact.",
            "- Use short causal lines such as `BECAUSE:` and `IMPACT:` so the generator can see why the criticism lands.",
        ])
    if "rule-writing" in ids:
        lines.extend([
            "- For each required correction, include at least one explicit `RULE:` block telling the generator what MUST, MUST NOT, SHOULD, or SHOULD NOT change.",
            "- Each `RULE:` block should have at least one `BECAUSE:` line explaining why that correction is necessary.",
        ])
    lines.append("- End with the required verdict line exactly as instructed by the task.")
    return "\n".join(lines)


def _build_skill_tool_text(
    role: str,
    phase_id: str,
    resolved: list[tuple[SkillChoice, SkillCatalogEntry]],
    overall_rationale: str,
    backend: str,
) -> str:
    if not resolved:
        return (
            f"# Phase {phase_id} — {role} Prelude\n\n"
            f"No specialized skills are required for this {role} call.\n"
            f"Proceed with the task below.\n\n---\n\n"
        )

    skill_lines = "\n".join(f"- {ch.id}" for ch, _ in resolved)
    if backend == "claude":
        instruction = (
            "Before you begin the task below, invoke the following skills in "
            "the order listed. Each skill must be invoked via the Skill tool "
            "with its exact ID."
        )
    else:
        instruction = (
            "Before you begin the task below, load and apply the following "
            "skills in the order listed. Refer to each skill by its exact ID."
        )
    return (
        f"# Phase {phase_id} — {role} Prelude\n\n"
        f"{instruction}\n\n"
        f"Skills to load:\n{skill_lines}\n\n"
        f"Rationale for this skill set (for your awareness):\n"
        f"{overall_rationale}\n\n"
        f"{_review_output_instruction(role, resolved)}\n\n"
        f"After you have loaded these skills, proceed with the task below.\n\n"
        f"---\n\n"
    )


def _build_inline_text(
    role: str,
    phase_id: str,
    resolved: list[tuple[SkillChoice, SkillCatalogEntry]],
    overall_rationale: str,
) -> str:
    if not resolved:
        return (
            f"# Phase {phase_id} — {role} Prelude (Inline Skill Content)\n\n"
            f"No specialized skills are required for this {role} call.\n"
            f"Proceed with the task below.\n\n---\n\n"
        )

    sections: list[str] = [
        f"# Phase {phase_id} — {role} Prelude (Inline Skill Content)",
        "",
        "The following specialized knowledge applies to this task.  Read and "
        "apply every section before beginning the task below.",
        "",
    ]
    for choice, entry in resolved:
        try:
            body = entry.source_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PreludeBuildError(
                f"cannot read SKILL.md for {entry.id} at {entry.source_path}: {exc}"
            ) from exc
        body_stripped = _strip_frontmatter(body).rstrip()
        sections.append(_SEPARATOR)
        sections.append(f"Skill: {entry.id}")
        sections.append(f"Source: {entry.source_path}")
        sections.append(_SEPARATOR)
        sections.append("")
        sections.append(body_stripped)
        sections.append("")
    sections.append(_SEPARATOR)
    sections.append("End of skill content")
    sections.append(_SEPARATOR)
    sections.append("")
    sections.append("Rationale for this skill set (for your awareness):")
    sections.append(overall_rationale)
    review_instruction = _review_output_instruction(role, resolved)
    if review_instruction:
        sections.append("")
        sections.append(review_instruction)
    sections.append("")
    sections.append("After you have applied this knowledge, proceed with the "
                    "task below.")
    sections.append("")
    sections.append("---")
    sections.append("")
    return "\n".join(sections)


def _build_file_reference_text(
    role: str,
    phase_id: str,
    resolved: list[tuple[SkillChoice, SkillCatalogEntry]],
    overall_rationale: str,
) -> str:
    if not resolved:
        return (
            f"# Phase {phase_id} — {role} Prelude (Skill File References)\n\n"
            f"No specialized skills are required for this {role} call.\n"
            f"Proceed with the task below.\n\n---\n\n"
        )

    skill_lines = "\n".join(
        f"- {choice.id}: {entry.source_path}"
        for choice, entry in resolved
    )
    return (
        f"# Phase {phase_id} — {role} Prelude (Skill File References)\n\n"
        "Before you begin the task below, read and apply each of the "
        "following local skill files in the order listed.\n\n"
        f"Skill files to read:\n{skill_lines}\n\n"
        "Treat those files as the specialized guidance for this task, then "
        "proceed with the task below.\n\n"
        "Rationale for this skill set (for your awareness):\n"
        f"{overall_rationale}\n\n"
        f"{_review_output_instruction(role, resolved)}\n\n"
        "---\n\n"
    )


def build_prelude(
    manifest: PhaseSkillManifest,
    catalog: dict[str, SkillCatalogEntry],
    *,
    mode: str | None = None,
    backend: str = "codex",
) -> PreludeSpec:
    """Construct generator and judge prelude text for a phase.

    Parameters
    ----------
    manifest:
        The selector's locked output for this phase.
    catalog:
        The discovered skill catalog.  Used in inline mode to read
        SKILL.md bodies, and in skill-tool mode to validate that
        every chosen ID is discoverable at run time.
    mode:
        Optional override.  Defaults to ``constants.SKILL_LOADING_MODE``.

    Raises
    ------
    PreludeBuildError
        If the mode is invalid, or any skill in the manifest is not
        present in the catalog, or a SKILL.md body cannot be read.
    """
    effective_mode = mode if mode is not None else SKILL_LOADING_MODE
    if effective_mode not in ("skill-tool", "inline", "file-reference"):
        raise PreludeBuildError(
            f"unknown skill loading mode: {effective_mode!r}; "
            f"must be 'skill-tool', 'inline', or 'file-reference'"
        )

    gen_resolved = _resolve_skills(manifest.generator_skills, catalog)
    jud_resolved = _resolve_skills(manifest.judge_skills, catalog)

    if effective_mode == "skill-tool":
        gen_text = _build_skill_tool_text(
            "Generator", manifest.phase_id, gen_resolved,
            manifest.overall_rationale,
            backend,
        )
        jud_text = _build_skill_tool_text(
            "Judge", manifest.phase_id, jud_resolved,
            manifest.overall_rationale,
            backend,
        )
    elif effective_mode == "inline":
        gen_text = _build_inline_text(
            "Generator", manifest.phase_id, gen_resolved,
            manifest.overall_rationale,
        )
        jud_text = _build_inline_text(
            "Judge", manifest.phase_id, jud_resolved,
            manifest.overall_rationale,
        )
    else:
        gen_text = _build_file_reference_text(
            "Generator", manifest.phase_id, gen_resolved,
            manifest.overall_rationale,
        )
        jud_text = _build_file_reference_text(
            "Judge", manifest.phase_id, jud_resolved,
            manifest.overall_rationale,
        )

    return PreludeSpec(
        generator_text=gen_text,
        judge_text=jud_text,
        mode=effective_mode,
    )
