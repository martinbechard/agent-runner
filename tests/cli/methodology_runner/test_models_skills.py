"""Tests for the skill-related dataclasses added to models.py."""
from pathlib import Path

from methodology_runner.models import (
    BaselineSkillConfig,
    PhaseSkillManifest,
    PreludeSpec,
    SkillCatalogEntry,
    SkillChoice,
    SkillSource,
)


def test_skill_catalog_entry_round_trip():
    entry = SkillCatalogEntry(
        id="tdd",
        description="Test-driven development discipline",
        source_path=Path("/home/me/.claude/skills/tdd/SKILL.md"),
        source_location="user",
    )
    d = entry.to_dict()
    assert d["id"] == "tdd"
    assert d["source_location"] == "user"
    restored = SkillCatalogEntry.from_dict(d)
    assert restored == entry


def test_skill_choice_minimal_fields():
    choice = SkillChoice(
        id="python-backend-impl",
        source=SkillSource.EXPERTISE_MAPPING,
        rationale="Catalog match for Python backend expertise",
        mapped_from="Python backend development",
    )
    d = choice.to_dict()
    assert d["id"] == "python-backend-impl"
    assert d["source"] == "expertise-mapping"
    restored = SkillChoice.from_dict(d)
    assert restored == choice


def test_skill_choice_baseline_has_no_mapped_from():
    choice = SkillChoice(
        id="tdd",
        source=SkillSource.BASELINE,
        rationale="Baseline for this phase",
    )
    assert choice.mapped_from is None
    d = choice.to_dict()
    assert "mapped_from" not in d or d["mapped_from"] is None


def test_phase_skill_manifest_yaml_round_trip():
    manifest = PhaseSkillManifest(
        phase_id="PH-006-incremental-implementation",
        selector_run_at="2026-04-09T10:42:17+00:00",
        selector_model="claude-opus-4-6",
        generator_skills=[
            SkillChoice(
                id="tdd",
                source=SkillSource.BASELINE,
                rationale="Baseline",
            ),
        ],
        judge_skills=[
            SkillChoice(
                id="code-review-discipline",
                source=SkillSource.BASELINE,
                rationale="Baseline",
            ),
        ],
        overall_rationale="Implementation phase with TDD baseline.",
    )
    d = manifest.to_dict()
    restored = PhaseSkillManifest.from_dict(d)
    assert restored == manifest


def test_baseline_skill_config_lookup():
    cfg = BaselineSkillConfig(
        version=1,
        phases={
            "PH-000-requirements-inventory": {
                "generator": ["requirements-extraction", "traceability-discipline"],
                "judge": ["requirements-quality-review", "traceability-discipline"],
            },
        },
    )
    gen, jud = cfg.baselines_for("PH-000-requirements-inventory")
    assert gen == ["requirements-extraction", "traceability-discipline"]
    assert jud == ["requirements-quality-review", "traceability-discipline"]


def test_baseline_skill_config_missing_phase_raises_key_error():
    cfg = BaselineSkillConfig(version=1, phases={})
    try:
        cfg.baselines_for("PH-999-nope")
    except KeyError:
        return
    raise AssertionError("expected KeyError for missing phase")


def test_prelude_spec_has_text_fields():
    spec = PreludeSpec(
        generator_text="# Gen prelude",
        judge_text="# Jud prelude",
        mode="skill-tool",
    )
    assert spec.generator_text == "# Gen prelude"
    assert spec.judge_text == "# Jud prelude"
    assert spec.mode == "skill-tool"
