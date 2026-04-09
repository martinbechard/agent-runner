"""Tests for orchestrator skill-catalog and baseline integration."""
from pathlib import Path

import pytest

from methodology_runner.orchestrator import (
    PipelineConfig,
    build_run_skill_context,
)
from methodology_runner.skill_catalog import CatalogBuildError
from methodology_runner.baseline_config import BaselineConfigError


def _requirements(tmp_path: Path) -> Path:
    req = tmp_path / "req.md"
    req.write_text("# Requirements\n\n- do the thing\n", encoding="utf-8")
    return req


def _write_skill(root: Path, name: str, desc: str) -> None:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n\nbody\n",
        encoding="utf-8",
    )


def _write_baseline(
    baseline_path: Path, phase_id: str, gen: list[str], jud: list[str],
) -> None:
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["version: 1", "phases:", f"  {phase_id}:"]
    lines.append("    generator_baseline:")
    for s in gen:
        lines.append(f"      - {s}")
    lines.append("    judge_baseline:")
    for s in jud:
        lines.append(f"      - {s}")
    baseline_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_build_run_skill_context_happy_path(tmp_path: Path):
    # Arrange: fake workspace with skills, fake user home with skills,
    # valid baseline config in workspace.
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    _write_skill(workspace / ".claude" / "skills", "tdd", "TDD")
    _write_skill(user_home / ".claude" / "skills", "traceability-discipline", "Trace")
    baseline = workspace / "docs" / "methodology" / "skills-baselines.yaml"
    _write_baseline(
        baseline, "PH-000-requirements-inventory",
        gen=["tdd"], jud=["traceability-discipline"],
    )
    # Act
    ctx = build_run_skill_context(
        workspace=workspace,
        baseline_path=baseline,
        user_home=user_home,
    )
    # Assert
    assert "tdd" in ctx.catalog
    assert "traceability-discipline" in ctx.catalog
    assert ctx.baseline_config.version == 1


def test_build_run_skill_context_empty_catalog_raises(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    user_home = tmp_path / "home"
    user_home.mkdir()
    baseline = workspace / "skills-baselines.yaml"
    _write_baseline(
        baseline, "PH-X", gen=["a"], jud=["b"],
    )
    with pytest.raises(CatalogBuildError):
        build_run_skill_context(
            workspace=workspace,
            baseline_path=baseline,
            user_home=user_home,
        )


def test_build_run_skill_context_baseline_missing_from_catalog_raises(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    _write_skill(user_home / ".claude" / "skills", "only-skill", "Only")
    baseline = workspace / "skills-baselines.yaml"
    _write_baseline(
        baseline, "PH-X", gen=["only-skill"], jud=["missing-skill"],
    )
    with pytest.raises(BaselineConfigError) as exc_info:
        build_run_skill_context(
            workspace=workspace,
            baseline_path=baseline,
            user_home=user_home,
        )
    assert "missing-skill" in str(exc_info.value)
