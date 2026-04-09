"""Tests for the Skill-Selector agent."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from methodology_runner.models import (
    BaselineSkillConfig,
    SkillCatalogEntry,
)
from methodology_runner.skill_selector import (
    SelectorError,
    SelectorInputs,
    invoke_skill_selector,
)


@dataclass
class _StubClient:
    responses: list[str]
    received: list[str] = field(default_factory=list)
    _idx: int = 0

    def call(self, call: Any):
        from prompt_runner.claude_client import ClaudeResponse
        self.received.append(call.prompt)
        text = self.responses[self._idx]
        self._idx += 1
        return ClaudeResponse(stdout=text, stderr="", returncode=0)


def _catalog() -> dict[str, SkillCatalogEntry]:
    return {
        "tdd": SkillCatalogEntry(
            id="tdd", description="Test-driven development",
            source_path=Path("/tdd"), source_location="user",
        ),
        "traceability-discipline": SkillCatalogEntry(
            id="traceability-discipline", description="Universal traceability",
            source_path=Path("/tr"), source_location="user",
        ),
        "python-backend-impl": SkillCatalogEntry(
            id="python-backend-impl", description="Python backend conventions",
            source_path=Path("/pb"), source_location="user",
        ),
    }


def _baseline() -> BaselineSkillConfig:
    return BaselineSkillConfig(
        version=1,
        phases={
            "PH-006-incremental-implementation": {
                "generator": ["tdd", "traceability-discipline"],
                "judge": ["traceability-discipline"],
            },
        },
    )


def _selector_inputs(tmp_path: Path) -> SelectorInputs:
    from methodology_runner.phases import get_phase
    return SelectorInputs(
        phase_config=get_phase("PH-006-incremental-implementation"),
        catalog=_catalog(),
        baseline_config=_baseline(),
        workspace_dir=tmp_path,
        prior_artifact_paths=[],
        stack_manifest_path=None,
    )


def _valid_yaml_reply() -> str:
    return """\
phase_id: PH-006-incremental-implementation
selector_run_at: 2026-04-09T10:00:00+00:00
selector_model: test-model
generator_skills:
  - id: tdd
    source: baseline
    rationale: Baseline for implementation phase
  - id: traceability-discipline
    source: baseline
    rationale: Universal baseline
  - id: python-backend-impl
    source: expertise-mapping
    mapped_from: Python backend development
    rationale: Stack manifest declared Python backend
judge_skills:
  - id: traceability-discipline
    source: baseline
    rationale: Baseline
overall_rationale: |
  Implementation phase for a Python backend component.
"""


def test_invoke_selector_happy_path(tmp_path: Path):
    client = _StubClient(responses=[_valid_yaml_reply()])
    manifest = invoke_skill_selector(
        _selector_inputs(tmp_path), claude_client=client, model="test-model",
    )
    assert manifest.phase_id == "PH-006-incremental-implementation"
    assert len(manifest.generator_skills) == 3
    assert manifest.generator_skills[0].id == "tdd"
    assert manifest.generator_skills[2].mapped_from == "Python backend development"


def test_malformed_yaml_raises_selector_error(tmp_path: Path):
    client = _StubClient(responses=["not: [valid: yaml"])
    with pytest.raises(SelectorError) as exc_info:
        invoke_skill_selector(
            _selector_inputs(tmp_path), claude_client=client, model="test-model",
        )
    assert "yaml" in str(exc_info.value).lower()


def test_missing_required_field_raises(tmp_path: Path):
    reply = """
phase_id: PH-006-incremental-implementation
generator_skills: []
judge_skills: []
overall_rationale: missing selector_run_at and selector_model
"""
    client = _StubClient(responses=[reply])
    with pytest.raises(SelectorError) as exc_info:
        invoke_skill_selector(
            _selector_inputs(tmp_path), claude_client=client, model="test-model",
        )
    assert "selector_run_at" in str(exc_info.value) or "required" in str(exc_info.value).lower()


def test_unknown_skill_id_raises(tmp_path: Path):
    reply = """\
phase_id: PH-006-incremental-implementation
selector_run_at: 2026-04-09T10:00:00+00:00
selector_model: test-model
generator_skills:
  - id: tdd
    source: baseline
    rationale: Baseline
  - id: traceability-discipline
    source: baseline
    rationale: Baseline
  - id: does-not-exist
    source: selector-judgment
    rationale: Invented
judge_skills:
  - id: traceability-discipline
    source: baseline
    rationale: Baseline
overall_rationale: Test
"""
    client = _StubClient(responses=[reply])
    with pytest.raises(SelectorError) as exc_info:
        invoke_skill_selector(
            _selector_inputs(tmp_path), claude_client=client, model="test-model",
        )
    assert "does-not-exist" in str(exc_info.value)


def test_missing_baseline_skill_raises(tmp_path: Path):
    # tdd is a baseline but not in the reply
    reply = """\
phase_id: PH-006-incremental-implementation
selector_run_at: 2026-04-09T10:00:00+00:00
selector_model: test-model
generator_skills:
  - id: traceability-discipline
    source: baseline
    rationale: Baseline
judge_skills:
  - id: traceability-discipline
    source: baseline
    rationale: Baseline
overall_rationale: Oops, forgot tdd
"""
    client = _StubClient(responses=[reply])
    with pytest.raises(SelectorError) as exc_info:
        invoke_skill_selector(
            _selector_inputs(tmp_path), claude_client=client, model="test-model",
        )
    assert "tdd" in str(exc_info.value)
    assert "baseline" in str(exc_info.value).lower()
