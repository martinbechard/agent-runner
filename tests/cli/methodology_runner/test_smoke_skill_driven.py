"""Smoke test: single-phase pipeline end-to-end with mocked catalog.

Exercises catalog discovery, baseline validation, per-phase selector
invocation, prelude construction, and prompt-runner invocation using
scripted Claude responses throughout.  Does not verify real-world
behavior with a live claude CLI — that belongs in a separate
integration test directory.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


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
                f"out of responses at call #{len(self.received)}"
            )
        text = self.responses[self._idx]
        self._idx += 1
        return ClaudeResponse(stdout=text, stderr="", returncode=0)


def _write_skill(root: Path, name: str, desc: str, body: str = "body") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return p


def test_phase_0_single_phase_runs_end_to_end_with_mock_catalog(
    tmp_path: Path, monkeypatch,
):
    # ---- arrange workspace + skills + baseline config ----
    workspace = tmp_path / "ws"
    workspace.mkdir()
    user_home = tmp_path / "home"
    # The skill pack
    _write_skill(user_home / ".claude" / "skills", "requirements-extraction", "Extract reqs")
    _write_skill(user_home / ".claude" / "skills", "traceability-discipline", "Universal traceability")
    _write_skill(user_home / ".claude" / "skills", "requirements-quality-review", "QA reqs")

    # Baseline config alongside workspace
    baseline = workspace / "docs" / "methodology" / "skills-baselines.yaml"
    baseline.parent.mkdir(parents=True)
    baseline.write_text(
        """\
version: 1
phases:
  PH-000-requirements-inventory:
    generator_baseline:
      - requirements-extraction
      - traceability-discipline
    judge_baseline:
      - requirements-quality-review
      - traceability-discipline
""",
        encoding="utf-8",
    )

    # Monkeypatch Path.home() to our fake home
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_home))

    # ---- arrange requirements file ----
    req = tmp_path / "req.md"
    req.write_text("# Req\n\n- the system shall do the thing\n", encoding="utf-8")

    # ---- scripted claude responses ----
    # 1) Skill-Selector reply (YAML)
    selector_reply = """\
phase_id: PH-000-requirements-inventory
selector_run_at: 2026-04-09T10:00:00+00:00
selector_model: test
generator_skills:
  - id: requirements-extraction
    source: baseline
    rationale: Baseline
  - id: traceability-discipline
    source: baseline
    rationale: Baseline
judge_skills:
  - id: requirements-quality-review
    source: baseline
    rationale: Baseline
  - id: traceability-discipline
    source: baseline
    rationale: Baseline
overall_rationale: Requirements extraction phase; baseline only.
"""
    # 2) Prompt generator meta-prompt reply (a valid prompt-runner .md file)
    meta_reply = """\
# Phase 0 prompts

## Prompt 1: Extract requirements

```
Generator prompt body
```

```
Validator prompt body
```
"""
    # 3) Generator response within prompt-runner
    generator_reply = "items:\n  - id: RI-001\n    verbatim_quote: the system shall do the thing\n"
    # 4) Judge response within prompt-runner
    judge_reply = "Looks good.\n\nVERDICT: pass"
    # 5) Cross-reference verification reply
    xref_reply = """\
verdict: pass
traceability:
  status: pass
  issues: []
coverage:
  status: pass
  issues: []
consistency:
  status: pass
  issues: []
integration:
  status: pass
  issues: []
"""

    client = _ScriptedClaude(
        responses=[selector_reply, meta_reply, generator_reply, judge_reply, xref_reply],
    )

    # ---- act ----
    from methodology_runner.orchestrator import (
        PipelineConfig, run_pipeline,
    )
    cfg = PipelineConfig(
        requirements_path=req,
        workspace_dir=workspace,
        phases_to_run=["PH-000-requirements-inventory"],
        max_cross_ref_retries=0,
    )
    result = run_pipeline(cfg, claude_client=client)

    # ---- assert ----
    # The selector was called at least once
    assert len(client.received) >= 1
    # phase-000-skills.yaml exists
    manifest = workspace / ".methodology-runner" / "runs" / "phase-0" / "phase-000-skills.yaml"
    assert manifest.exists()
    content = manifest.read_text("utf-8")
    assert "requirements-extraction" in content
    # Prelude files exist
    gp = workspace / ".methodology-runner" / "runs" / "phase-0" / "generator-prelude.txt"
    jp = workspace / ".methodology-runner" / "runs" / "phase-0" / "judge-prelude.txt"
    assert gp.exists()
    assert jp.exists()
