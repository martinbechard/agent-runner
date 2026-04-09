"""Load and validate ``docs/methodology/skills-baselines.yaml``.

The baseline config declares the non-negotiable skills per phase.
It is read at the start of every run; changes take effect on the
next invocation without a code change.

Validation is two-step:

1. **Load-time** (``load_baseline_config``): the file parses, has
   the expected top-level shape, and ``version`` is an int.
2. **Catalog-time** (``validate_against_catalog``): every skill ID
   referenced by any baseline exists in the discovered catalog.
   Failing this check is a critical halt (spec failure mode 9).
"""
from __future__ import annotations

from pathlib import Path

import yaml  # PyYAML is a transitive dev dep; add explicitly if missing

from .models import BaselineSkillConfig, SkillCatalogEntry


class BaselineConfigError(RuntimeError):
    """Raised on load or validation failure of skills-baselines.yaml."""


def load_baseline_config(path: Path) -> BaselineSkillConfig:
    """Parse and shape-validate ``skills-baselines.yaml``.

    Raises :class:`BaselineConfigError` on any failure: missing file,
    malformed YAML, wrong shape, or missing required fields.
    """
    if not path.exists():
        raise BaselineConfigError(
            f"baseline skills config not found: {path}\n\n"
            f"Expected file at docs/methodology/skills-baselines.yaml.\n"
            f"Create it or install methodology-runner-skills."
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise BaselineConfigError(
            f"malformed YAML in {path}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise BaselineConfigError(
            f"{path}: top-level must be a mapping, got {type(raw).__name__}"
        )

    version = raw.get("version")
    if not isinstance(version, int):
        raise BaselineConfigError(
            f"{path}: 'version' must be an int, got {version!r}"
        )

    phases_raw = raw.get("phases")
    if not isinstance(phases_raw, dict):
        raise BaselineConfigError(
            f"{path}: 'phases' must be a mapping, got {type(phases_raw).__name__}"
        )

    phases: dict[str, dict[str, list[str]]] = {}
    for phase_id, entry in phases_raw.items():
        if not isinstance(entry, dict):
            raise BaselineConfigError(
                f"{path}: phase {phase_id!r} entry must be a mapping"
            )
        generator = entry.get("generator_baseline") or entry.get("generator") or []
        judge = entry.get("judge_baseline") or entry.get("judge") or []
        if not isinstance(generator, list) or not all(isinstance(s, str) for s in generator):
            raise BaselineConfigError(
                f"{path}: phase {phase_id!r} generator baseline must be a list of strings"
            )
        if not isinstance(judge, list) or not all(isinstance(s, str) for s in judge):
            raise BaselineConfigError(
                f"{path}: phase {phase_id!r} judge baseline must be a list of strings"
            )
        phases[phase_id] = {"generator": list(generator), "judge": list(judge)}

    return BaselineSkillConfig(version=version, phases=phases)


def validate_against_catalog(
    config: BaselineSkillConfig,
    catalog: dict[str, SkillCatalogEntry],
) -> None:
    """Ensure every baseline skill ID exists in the discovered catalog.

    Raises :class:`BaselineConfigError` listing every missing skill.
    This is a critical halt — the orchestrator must refuse to start
    when baseline skills are not installed.
    """
    missing: list[str] = sorted(
        skill_id
        for skill_id in config.all_baseline_ids()
        if skill_id not in catalog
    )
    if not missing:
        return
    lines = [
        "skills-baselines.yaml references skills that are not installed:",
        "",
    ]
    for sid in missing:
        lines.append(f"  - {sid}")
    lines.extend([
        "",
        "Install methodology-runner-skills or edit skills-baselines.yaml.",
    ])
    raise BaselineConfigError("\n".join(lines))
