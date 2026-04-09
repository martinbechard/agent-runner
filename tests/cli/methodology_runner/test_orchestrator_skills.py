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


# ---------------------------------------------------------------------------
# Per-phase selector invocation
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field
from typing import Any


@dataclass
class _ScriptedClaude:
    responses: list[str]
    received: list[str] = field(default_factory=list)
    _idx: int = 0

    def call(self, call):
        from prompt_runner.claude_client import ClaudeResponse
        self.received.append(call.prompt)
        if self._idx >= len(self.responses):
            raise AssertionError(
                f"ScriptedClaude ran out of responses at {len(self.received)}"
            )
        text = self.responses[self._idx]
        self._idx += 1
        return ClaudeResponse(stdout=text, stderr="", returncode=0)


def _minimal_selector_reply(phase_id: str, gen: list[str], jud: list[str]) -> str:
    gen_lines = "\n".join(
        f"  - id: {s}\n    source: baseline\n    rationale: Baseline"
        for s in gen
    )
    jud_lines = "\n".join(
        f"  - id: {s}\n    source: baseline\n    rationale: Baseline"
        for s in jud
    )
    return (
        f"phase_id: {phase_id}\n"
        f"selector_run_at: 2026-04-09T10:00:00+00:00\n"
        f"selector_model: test\n"
        f"generator_skills:\n{gen_lines}\n"
        f"judge_skills:\n{jud_lines}\n"
        f"overall_rationale: Test manifest\n"
    )


def test_orchestrator_runs_selector_once_per_phase_and_writes_manifest(tmp_path: Path):
    from methodology_runner.orchestrator import (
        run_selector_and_build_prelude,
    )
    from methodology_runner.phases import get_phase
    from methodology_runner.models import BaselineSkillConfig, SkillCatalogEntry
    from methodology_runner.orchestrator import RunSkillContext

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".methodology-runner" / "runs" / "phase-0").mkdir(parents=True)

    catalog = {
        "requirements-extraction": SkillCatalogEntry(
            id="requirements-extraction", description="Extract reqs",
            source_path=tmp_path / "a" / "SKILL.md", source_location="user",
        ),
        "traceability-discipline": SkillCatalogEntry(
            id="traceability-discipline", description="Trace",
            source_path=tmp_path / "b" / "SKILL.md", source_location="user",
        ),
        "requirements-quality-review": SkillCatalogEntry(
            id="requirements-quality-review", description="QA reqs",
            source_path=tmp_path / "c" / "SKILL.md", source_location="user",
        ),
    }
    # Write minimal SKILL.md bodies for inline-mode prelude
    for e in catalog.values():
        e.source_path.parent.mkdir(parents=True, exist_ok=True)
        e.source_path.write_text(
            f"---\nname: {e.id}\ndescription: {e.description}\n---\n\nbody\n",
            encoding="utf-8",
        )

    baseline = BaselineSkillConfig(
        version=1,
        phases={
            "PH-000-requirements-inventory": {
                "generator": ["requirements-extraction", "traceability-discipline"],
                "judge": ["requirements-quality-review", "traceability-discipline"],
            },
        },
    )
    skill_ctx = RunSkillContext(catalog=catalog, baseline_config=baseline)
    phase = get_phase("PH-000-requirements-inventory")

    client = _ScriptedClaude(responses=[
        _minimal_selector_reply(
            "PH-000-requirements-inventory",
            gen=["requirements-extraction", "traceability-discipline"],
            jud=["requirements-quality-review", "traceability-discipline"],
        ),
    ])

    result = run_selector_and_build_prelude(
        phase_config=phase,
        skill_ctx=skill_ctx,
        workspace=workspace,
        run_dir=workspace / ".methodology-runner" / "runs" / "phase-0",
        claude_client=client,
        model="test",
    )

    # Manifest YAML committed to workspace
    manifest_path = workspace / ".methodology-runner" / "runs" / "phase-0" / "phase-000-skills.yaml"
    assert manifest_path.exists()
    assert "PH-000-requirements-inventory" in manifest_path.read_text("utf-8")
    # Prelude files written
    assert result.generator_prelude_path.exists()
    assert result.judge_prelude_path.exists()
    assert len(client.received) == 1  # selector called once
