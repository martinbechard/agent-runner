"""Tests for prelude construction."""
from pathlib import Path

import pytest

from methodology_runner.models import (
    PhaseSkillManifest,
    SkillCatalogEntry,
    SkillChoice,
    SkillSource,
)
from methodology_runner.prelude import (
    PreludeBuildError,
    build_prelude,
)


def _manifest() -> PhaseSkillManifest:
    return PhaseSkillManifest(
        phase_id="PH-006-incremental-implementation",
        selector_run_at="2026-04-09T10:00:00+00:00",
        selector_model="test",
        generator_skills=[
            SkillChoice(id="tdd", source=SkillSource.BASELINE, rationale="B"),
            SkillChoice(
                id="python-backend-impl",
                source=SkillSource.EXPERTISE_MAPPING,
                mapped_from="Python backend development",
                rationale="Map",
            ),
        ],
        judge_skills=[
            SkillChoice(
                id="code-review-discipline",
                source=SkillSource.BASELINE,
                rationale="B",
            ),
        ],
        overall_rationale="Test manifest",
    )


def _catalog(tmp_path: Path) -> dict[str, SkillCatalogEntry]:
    def _mk(name: str, body: str) -> Path:
        d = tmp_path / name
        d.mkdir(parents=True, exist_ok=True)
        p = d / "SKILL.md"
        p.write_text(
            f"---\nname: {name}\ndescription: {name} skill\n---\n\n{body}\n",
            encoding="utf-8",
        )
        return p
    return {
        "tdd": SkillCatalogEntry(
            id="tdd", description="TDD",
            source_path=_mk("tdd", "TDD body content"),
            source_location="user",
        ),
        "python-backend-impl": SkillCatalogEntry(
            id="python-backend-impl", description="Python backend",
            source_path=_mk("python-backend-impl", "Python backend body"),
            source_location="user",
        ),
        "code-review-discipline": SkillCatalogEntry(
            id="code-review-discipline", description="Code review",
            source_path=_mk("code-review-discipline", "Code review body"),
            source_location="user",
        ),
    }


def test_skill_tool_mode_lists_skill_ids(tmp_path: Path):
    spec = build_prelude(_manifest(), _catalog(tmp_path), mode="skill-tool")
    assert "tdd" in spec.generator_text
    assert "python-backend-impl" in spec.generator_text
    assert "code-review-discipline" in spec.judge_text
    assert "Skill tool" in spec.generator_text
    # Body content NOT inlined in skill-tool mode
    assert "TDD body content" not in spec.generator_text


def test_inline_mode_embeds_skill_bodies(tmp_path: Path):
    spec = build_prelude(_manifest(), _catalog(tmp_path), mode="inline")
    assert "TDD body content" in spec.generator_text
    assert "Python backend body" in spec.generator_text
    assert "Code review body" in spec.judge_text
    assert spec.mode == "inline"


def test_inline_mode_strips_frontmatter(tmp_path: Path):
    spec = build_prelude(_manifest(), _catalog(tmp_path), mode="inline")
    # Frontmatter delimiters and keys must NOT leak into the prelude
    assert "name: tdd" not in spec.generator_text
    assert "description: tdd skill" not in spec.generator_text


def test_build_prelude_rejects_unknown_mode(tmp_path: Path):
    with pytest.raises(PreludeBuildError):
        build_prelude(_manifest(), _catalog(tmp_path), mode="banana")


def test_build_prelude_rejects_skill_not_in_catalog(tmp_path: Path):
    manifest = _manifest()
    partial = {
        "tdd": _catalog(tmp_path)["tdd"],
        # python-backend-impl and code-review-discipline missing
    }
    with pytest.raises(PreludeBuildError) as exc_info:
        build_prelude(manifest, partial, mode="inline")
    assert "python-backend-impl" in str(exc_info.value)


def test_build_prelude_empty_skill_list_produces_empty_body(tmp_path: Path):
    from methodology_runner.models import PhaseSkillManifest
    empty = PhaseSkillManifest(
        phase_id="PH-000-requirements-inventory",
        selector_run_at="2026-04-09T10:00:00+00:00",
        selector_model="test",
        generator_skills=[],
        judge_skills=[],
        overall_rationale="No skills needed",
    )
    spec = build_prelude(empty, {}, mode="skill-tool")
    assert spec.generator_text  # non-empty header even with no skills
    assert spec.judge_text
