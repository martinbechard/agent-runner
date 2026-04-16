"""Tests that cross-ref retry preserves the locked skill manifest."""
from pathlib import Path
from unittest.mock import MagicMock

from methodology_runner.models import (
    BaselineSkillConfig,
    PhaseSkillManifest,
    SkillCatalogEntry,
    SkillChoice,
    SkillSource,
)
from methodology_runner.orchestrator import (
    PhaseSkillArtifacts,
    RunSkillContext,
    run_selector_and_build_prelude,
)
from methodology_runner.phases import get_phase


def _catalog(tmp_path: Path) -> dict[str, SkillCatalogEntry]:
    out = {}
    for name in ("ph000-requirements-extraction", "traceability-discipline", "ph000-requirements-quality-review"):
        p = tmp_path / name / "SKILL.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"---\nname: {name}\ndescription: {name}\n---\n\nbody\n",
            encoding="utf-8",
        )
        out[name] = SkillCatalogEntry(
            id=name, description=name,
            source_path=p, source_location="user",
        )
    return out


def test_existing_manifest_skips_selector_invocation(tmp_path: Path):
    workspace = tmp_path / "ws"
    run_dir = workspace / ".methodology-runner" / "runs" / "phase-0"
    run_dir.mkdir(parents=True)

    # Write a pre-existing phase-000-skills.yaml
    existing = run_dir / "phase-000-skills.yaml"
    existing.write_text(
        """\
phase_id: PH-000-requirements-inventory
selector_run_at: 2026-04-09T10:00:00+00:00
selector_model: previous
generator_skills:
  - id: ph000-requirements-extraction
    source: baseline
    rationale: Baseline
  - id: traceability-discipline
    source: baseline
    rationale: Baseline
judge_skills:
  - id: ph000-requirements-quality-review
    source: baseline
    rationale: Baseline
  - id: traceability-discipline
    source: baseline
    rationale: Baseline
overall_rationale: Previous manifest
""",
        encoding="utf-8",
    )

    catalog = _catalog(tmp_path)
    baseline = BaselineSkillConfig(
        version=1,
        phases={
            "PH-000-requirements-inventory": {
                "generator": ["ph000-requirements-extraction", "traceability-discipline"],
                "judge": ["ph000-requirements-quality-review", "traceability-discipline"],
            },
        },
    )
    ctx = RunSkillContext(catalog=catalog, baseline_config=baseline)
    phase = get_phase("PH-000-requirements-inventory")
    fake_client = MagicMock()

    result = run_selector_and_build_prelude(
        phase_config=phase,
        skill_ctx=ctx,
        workspace=workspace,
        run_dir=run_dir,
        claude_client=fake_client,
        backend="claude",
        model="test",
        state=None,
        existing_manifest_path=existing,
    )

    # Selector was NOT called because manifest already exists
    fake_client.call.assert_not_called()
    assert result.generator_prelude_path.exists()
    assert result.judge_prelude_path.exists()
