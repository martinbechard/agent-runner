"""Build generator and judge prelude text from a PhaseSkillManifest.

Two designs exist in parallel:

- ``skill-tool`` (primary): the prelude instructs the agent to invoke
  the Claude Code Skill tool by name.  SKILL.md body content is NOT
  included; the agent loads it just-in-time.  Depends on the Skill
  tool being available inside nested claude --print subprocesses
  (verified by Phase 0 validation).
- ``inline`` (fallback): the prelude embeds the full SKILL.md body
  (minus frontmatter) of every selected skill.  Zero dependency on
  the Skill tool, but larger prelude size.  ``MAX_SKILLS_PER_PHASE``
  is a hard cap under this design.

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


def _build_skill_tool_text(
    role: str,
    phase_id: str,
    resolved: list[tuple[SkillChoice, SkillCatalogEntry]],
    overall_rationale: str,
) -> str:
    if not resolved:
        return (
            f"# Phase {phase_id} — {role} Prelude\n\n"
            f"No specialized skills are required for this {role} call.\n"
            f"Proceed with the task below.\n\n---\n\n"
        )

    skill_lines = "\n".join(f"- {ch.id}" for ch, _ in resolved)
    return (
        f"# Phase {phase_id} — {role} Prelude\n\n"
        f"Before you begin the task below, invoke the following Claude Code "
        f"skills in the order listed.  Each skill must be invoked via the "
        f"Skill tool with its exact ID.\n\n"
        f"Skills to load:\n{skill_lines}\n\n"
        f"Rationale for this skill set (for your awareness):\n"
        f"{overall_rationale}\n\n"
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
    sections.append("")
    sections.append("After you have applied this knowledge, proceed with the "
                    "task below.")
    sections.append("")
    sections.append("---")
    sections.append("")
    return "\n".join(sections)


def build_prelude(
    manifest: PhaseSkillManifest,
    catalog: dict[str, SkillCatalogEntry],
    *,
    mode: str | None = None,
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
    if effective_mode not in ("skill-tool", "inline"):
        raise PreludeBuildError(
            f"unknown skill loading mode: {effective_mode!r}; "
            f"must be 'skill-tool' or 'inline'"
        )

    gen_resolved = _resolve_skills(manifest.generator_skills, catalog)
    jud_resolved = _resolve_skills(manifest.judge_skills, catalog)

    if effective_mode == "skill-tool":
        gen_text = _build_skill_tool_text(
            "Generator", manifest.phase_id, gen_resolved,
            manifest.overall_rationale,
        )
        jud_text = _build_skill_tool_text(
            "Judge", manifest.phase_id, jud_resolved,
            manifest.overall_rationale,
        )
    else:
        gen_text = _build_inline_text(
            "Generator", manifest.phase_id, gen_resolved,
            manifest.overall_rationale,
        )
        jud_text = _build_inline_text(
            "Judge", manifest.phase_id, jud_resolved,
            manifest.overall_rationale,
        )

    return PreludeSpec(
        generator_text=gen_text,
        judge_text=jud_text,
        mode=effective_mode,
    )
