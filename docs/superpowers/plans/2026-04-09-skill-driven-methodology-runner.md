# Skill-Driven Methodology Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement skill-driven specialization for methodology-runner: per-phase Skill-Selector agent, auto-discovered skill catalog, baseline skills configuration, prelude-prepending feature in prompt-runner, and a new PH-002 Architecture phase.

**Architecture:** Per-phase skill selection decouples technology-specific knowledge from the generic methodology. A Skill-Selector Claude call runs once per phase before its meta-prompt, picks skills from a baseline YAML config plus auto-discovered catalog, and emits a locked `phase-NNN-skills.yaml`. The orchestrator builds generator/judge prelude files from that manifest and passes them to prompt-runner through two new CLI flags. A new PH-002 Architecture phase is inserted between Feature Specification and Solution Design to produce a `stack-manifest.yaml` that later phases consume.

**Tech Stack:** Python 3.11+, stdlib only (`argparse`, `dataclasses`, `pathlib`, `subprocess`, `json`), `pyyaml` already transitive via dev deps, pytest for tests. No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-04-09-skill-driven-methodology-runner-design.md`

---

## Scope

This plan covers the **Python code, data files, and documentation updates** for methodology-runner and prompt-runner. It does **not** cover:

- **Authoring the 18 v1 SKILL.md files** for the `methodology-runner-skills` companion plugin. That is a separate plan (content authoring, no code dependencies) and should be written as `docs/superpowers/plans/2026-04-10-methodology-runner-skills-pack.md` once this plan is complete or running in parallel. Implementation of methodology-runner can be fully tested with mock catalogs and a single throwaway SKILL.md file used only by Phase 0 validation.
- **Publishing to PyPI or the Claude Code plugin library.** Distribution work is deferred until the skill pack exists.

## File structure

### New files (Python)

| File | Responsibility |
|---|---|
| `.methodology/src/cli/methodology_runner/constants.py` | Numeric thresholds and mode switches (MAX_SKILLS_PER_PHASE, ARTIFACT_FULL_CONTENT_THRESHOLD, MAX_CATALOG_SIZE_WARNING, SKILL_LOADING_MODE, MAX_CROSS_REF_RETRIES). |
| `.methodology/src/cli/methodology_runner/skill_catalog.py` | Walk three discovery paths, parse SKILL.md frontmatter, build in-memory catalog keyed by skill ID. |
| `.methodology/src/cli/methodology_runner/baseline_config.py` | Load and validate `.methodology/docs/skills-baselines.yaml` at run start. |
| `.methodology/src/cli/methodology_runner/artifact_summarizer.py` | Size-threshold-gated summarization of prior phase artifacts, with on-disk caching. |
| `.methodology/src/cli/methodology_runner/skill_selector.py` | Assemble Skill-Selector Claude prompt, invoke, parse YAML output, validate against catalog and baselines. |
| `.methodology/src/cli/methodology_runner/prelude.py` | Build generator and judge prelude text files from a PhaseSkillManifest, with dual skill-tool/inline modes. |
| `.methodology/src/cli/methodology_runner/phase_0_validation.py` | Standalone Phase 0 experiment: create a test skill, invoke claude --print, check whether the Skill tool worked. |

### New files (tests)

| File | What it tests |
|---|---|
| `.methodology/tests/cli/methodology_runner/test_constants.py` | Constants exist with expected values. |
| `.methodology/tests/cli/methodology_runner/test_skill_catalog.py` | Discovery walking, frontmatter parsing, duplicate resolution, invalid entry handling, empty-catalog halt. |
| `.methodology/tests/cli/methodology_runner/test_baseline_config.py` | Parsing, schema validation, missing baseline IDs, phase-coverage check. |
| `.methodology/tests/cli/methodology_runner/test_artifact_summarizer.py` | Size threshold, cache hit/miss, cache invalidation, REQUEST_FULL_ARTIFACT escape hatch. |
| `.methodology/tests/cli/methodology_runner/test_skill_selector.py` | Prompt assembly, YAML output parsing, failure modes 1-5 (selector error, malformed YAML, missing fields, unknown skill ID, missing baseline). |
| `.methodology/tests/cli/methodology_runner/test_prelude.py` | Dual-mode prelude construction, MAX_SKILLS_PER_PHASE cap, empty prelude fallback. |
| `.methodology/tests/cli/methodology_runner/test_orchestrator_skills.py` | End-to-end orchestrator integration with mocked claude client and mock catalog; verifies the retry loop keeps the skill manifest locked. |

### New files (data)

| File | Purpose |
|---|---|
| `.methodology/docs/skills-baselines.yaml` | Per-phase baseline skill configuration; the non-negotiable floor. |

### Modified files

| File | What changes |
|---|---|
| `.methodology/src/cli/methodology_runner/models.py` | Add `SkillCatalogEntry`, `PhaseSkillManifest`, `SkillChoice`, `BaselineSkillConfig`, `PreludeSpec` dataclasses. |
| `.methodology/src/cli/methodology_runner/phases.py` | Insert new `_PHASE_2_ARCHITECTURE`; renumber existing `_PHASE_2`..`_PHASE_6` to `_PHASE_3`..`_PHASE_7`; add new output path constant for the stack manifest; update phase IDs and predecessor links. |
| `.methodology/src/cli/methodology_runner/orchestrator.py` | Call catalog discovery + baseline validation at run start; invoke Skill-Selector once per phase; build prelude files; pass prelude paths to prompt-runner; keep skill manifest locked across cross-ref retries. |
| `.methodology/src/cli/methodology_runner/prompt_generator.py` | Accept optional `phase_skill_manifest` in `PromptGenerationContext`; include a brief skill-manifest section in the meta-prompt so the prompt architect knows which skills are available. |
| `.methodology/src/cli/methodology_runner/cli.py` | Add `--rerun-selector` flag to `resume` subcommand. |
| `.prompt-runner/src/cli/prompt_runner/runner.py` | Accept optional `generator_prelude` and `judge_prelude` strings in `RunConfig`; prepend them to generator and judge messages in `build_initial_generator_message`, `build_initial_judge_message`, `build_revision_generator_message`, `build_revision_judge_message`. |
| `.prompt-runner/src/cli/prompt_runner/__main__.py` | Add `--generator-prelude PATH` and `--judge-prelude PATH` flags to the `run` subcommand; read prelude files at startup and populate `RunConfig`. |
| `.methodology/docs/M-002-phase-definitions.md` | Insert new PH-002 Architecture phase YAML; renumber existing PH-002..PH-006 to PH-003..PH-007 throughout; update dependency graph diagram and cross-references in the end-of-file summary table. |
| `.methodology/docs/design/components/CD-002-methodology-runner.md` | Add a new subsection on skill-driven per-phase selection; update the per-phase flow diagram; document dual prelude modes; document the SKILL_LOADING_MODE switch and Phase 0 validation gate. |

### Files NOT touched

- `.methodology/src/cli/methodology_runner/cross_reference.py` — cross-reference module is skill-unaware by design.
- `.prompt-runner/src/cli/prompt_runner/parser.py` / `claude_client.py` / `verdict.py` — prelude feature only touches `runner.py` and `__main__.py`.
- Existing workspace `state.json` files — discarded per greenfield policy.

---

## Task 0: Phase 0 — Skill tool availability validation

Determines whether the Skill tool is available inside nested `claude --print` subprocesses. The result decides the default value of `SKILL_LOADING_MODE`.

**Files:**
- Create: `.methodology/src/cli/methodology_runner/phase_0_validation.py`
- Create: `runs/phase-0-validation/validation-report.md` (generated artifact, committed)

- [ ] **Step 1: Create `.methodology/src/cli/methodology_runner/phase_0_validation.py`**

```python
"""Phase 0 validation experiment.

Determines whether the Claude Code Skill tool is available inside
nested ``claude --print`` subprocess invocations spawned by prompt-runner.
The result selects the default ``SKILL_LOADING_MODE``:

- Outcome A: Skill tool works  -> mode "skill-tool" (primary design)
- Outcome B: Skill tool absent  -> mode "inline"      (fallback design)

Usage::

    python -m methodology_runner.phase_0_validation

The script creates a temporary test skill under ``~/.claude/skills/``,
invokes ``claude --print`` with a prompt that instructs the agent to
invoke ``Skill("test-marker-<timestamp>")`` and echo back a distinctive
sentinel string, inspects the response, removes the temporary skill,
and writes ``runs/phase-0-validation/validation-report.md``.

The report is a release gate: methodology-runner refuses to start in
skill-tool mode unless this report exists and records a successful
outcome.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SENTINEL = "PH0_SKILL_TOOL_SENTINEL_42_UNIQUE"
"""Distinctive string the test skill's body contains. Presence in the
Claude response confirms the Skill tool loaded the skill."""

TEST_SKILL_NAME_PREFIX = "ph0-test-marker"
REPORT_DIR = Path("runs/phase-0-validation")
REPORT_FILENAME = "validation-report.md"


@dataclass
class ValidationOutcome:
    success: bool
    mode: str  # "skill-tool" or "inline"
    rationale: str
    claude_stdout: str
    claude_stderr: str


def _skills_root() -> Path:
    return Path.home() / ".claude" / "skills"


def _make_test_skill(skill_dir: Path) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {skill_dir.name}
description: Phase 0 validation marker skill for methodology-runner
---

# Phase 0 Validation Marker

This skill exists only to verify that the Skill tool works inside
nested claude --print calls. Its body contains a unique sentinel:

{SENTINEL}

If you can see this sentinel in the response, the Skill tool has
successfully loaded this skill.
""",
        encoding="utf-8",
    )


def _remove_test_skill(skill_dir: Path) -> None:
    if skill_dir.exists():
        shutil.rmtree(skill_dir)


def _run_claude_print(skill_name: str) -> tuple[str, str, int]:
    prompt = (
        f"Invoke the Skill tool with skill name '{skill_name}'. "
        f"Then echo the unique sentinel string that appears in the "
        f"skill body. Your response must contain the exact sentinel."
    )
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return result.stdout, result.stderr, result.returncode


def run_validation() -> ValidationOutcome:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    skill_name = f"{TEST_SKILL_NAME_PREFIX}-{timestamp}"
    skill_dir = _skills_root() / skill_name

    _make_test_skill(skill_dir)
    try:
        stdout, stderr, rc = _run_claude_print(skill_name)
    finally:
        _remove_test_skill(skill_dir)

    if rc != 0:
        return ValidationOutcome(
            success=False,
            mode="inline",
            rationale=(
                f"claude --print exited with status {rc}. "
                f"Cannot verify Skill tool availability; defaulting "
                f"to inline mode so methodology-runner can proceed."
            ),
            claude_stdout=stdout,
            claude_stderr=stderr,
        )

    if SENTINEL in stdout:
        return ValidationOutcome(
            success=True,
            mode="skill-tool",
            rationale=(
                "The sentinel string from the test skill body was "
                "found in the claude --print response. The Skill tool "
                "is available in nested subprocess calls."
            ),
            claude_stdout=stdout,
            claude_stderr=stderr,
        )

    return ValidationOutcome(
        success=True,
        mode="inline",
        rationale=(
            "The sentinel string was not found in the claude --print "
            "response. The Skill tool is either unavailable or did "
            "not load the test skill. Falling back to inline mode."
        ),
        claude_stdout=stdout,
        claude_stderr=stderr,
    )


def write_report(outcome: ValidationOutcome, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    report = f"""# Phase 0 Validation Report

**Date:** {now}
**Experiment:** Skill tool availability in nested claude --print

## Outcome

- **Success:** {outcome.success}
- **Selected mode:** `{outcome.mode}`

## Rationale

{outcome.rationale}

## Raw claude --print output

### stdout (first 2000 chars)

```
{outcome.claude_stdout[:2000]}
```

### stderr (first 2000 chars)

```
{outcome.claude_stderr[:2000]}
```

## Sentinel

Expected to find: `{SENTINEL}`
Found in stdout:  {SENTINEL in outcome.claude_stdout}
"""
    report_path.write_text(report, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Phase 0 validation for methodology-runner."
    )
    parser.add_argument(
        "--report-dir",
        default=str(REPORT_DIR),
        help="Directory to write the validation report (default: runs/phase-0-validation).",
    )
    args = parser.parse_args(argv)

    outcome = run_validation()
    report_path = Path(args.report_dir) / REPORT_FILENAME
    write_report(outcome, report_path)

    sys.stdout.write(
        f"Phase 0 validation: {outcome.mode} "
        f"({'PASS' if outcome.success else 'FAIL'})\n"
        f"Report written to: {report_path}\n"
    )
    return 0 if outcome.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run Phase 0 validation**

Run: `python -m methodology_runner.phase_0_validation`

Expected: exits 0; prints "Phase 0 validation: <mode> (PASS)"; writes `runs/phase-0-validation/validation-report.md`.

If `claude` is not on PATH, the script will raise `FileNotFoundError`. In that case, the user must install the Claude CLI first and re-run. Do not suppress this — Phase 0 validation without a real `claude` binary is meaningless.

- [ ] **Step 3: Commit Phase 0 script and report**

```bash
git add .methodology/src/cli/methodology_runner/phase_0_validation.py runs/phase-0-validation/validation-report.md
git commit -m "feat(methodology-runner): phase 0 skill tool availability validation"
```

---

## Task 1: Add `constants.py`

Central manifest-constants file per CLAUDE.md rule against literal constants scattered through code.

**Files:**
- Create: `.methodology/src/cli/methodology_runner/constants.py`
- Create: `.methodology/tests/cli/methodology_runner/test_constants.py`

- [ ] **Step 1: Write the failing test**

Create `.methodology/tests/cli/methodology_runner/test_constants.py`:

```python
"""Tests for methodology_runner.constants."""
from methodology_runner import constants


def test_max_skills_per_phase_is_positive_int():
    assert isinstance(constants.MAX_SKILLS_PER_PHASE, int)
    assert constants.MAX_SKILLS_PER_PHASE > 0


def test_artifact_full_content_threshold_is_positive_int():
    assert isinstance(constants.ARTIFACT_FULL_CONTENT_THRESHOLD, int)
    assert constants.ARTIFACT_FULL_CONTENT_THRESHOLD > 0


def test_max_catalog_size_warning_is_positive_int():
    assert isinstance(constants.MAX_CATALOG_SIZE_WARNING, int)
    assert constants.MAX_CATALOG_SIZE_WARNING > 0


def test_skill_loading_mode_is_one_of_two_values():
    assert constants.SKILL_LOADING_MODE in ("skill-tool", "inline")


def test_max_cross_ref_retries_is_non_negative():
    assert isinstance(constants.MAX_CROSS_REF_RETRIES, int)
    assert constants.MAX_CROSS_REF_RETRIES >= 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest .methodology/tests/cli/methodology_runner/test_constants.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'methodology_runner.constants'`

- [ ] **Step 3: Create `.methodology/src/cli/methodology_runner/constants.py`**

```python
"""Tunable constants for the methodology-runner pipeline.

All numeric thresholds and mode switches referenced by multiple
modules live here so they can be adjusted in one place without
hunting through the codebase.  Per CLAUDE.md: never scatter literal
constants through code.

Any constant that becomes user-configurable in the future should
first be promoted to a CLI flag; until then, changes here require
a code change and re-release.
"""
from __future__ import annotations


ARTIFACT_FULL_CONTENT_THRESHOLD = 5000
"""Size (in bytes) above which a prior-phase artifact is replaced by a
summary rather than passed in full to the Skill-Selector."""

MAX_SKILLS_PER_PHASE = 8
"""Maximum number of skills (generator + judge combined, counted uniquely)
the Skill-Selector is allowed to pick for a single phase.  Caps the
generator prelude size under the inline fallback design."""

MAX_CATALOG_SIZE_WARNING = 100
"""Catalog entry count above which a warning is logged.  Not a halt;
simply a hint that context may become tight."""

SKILL_LOADING_MODE = "skill-tool"
"""Default skill-loading mode for the prelude.

- "skill-tool": prelude instructs the generator/judge to invoke the
  Claude Code Skill tool by name.  Requires Phase 0 validation to
  have confirmed that the Skill tool works inside nested claude
  --print calls.
- "inline": prelude contains the full SKILL.md content of every
  selected skill, delimited by section markers.  Fallback design
  with zero dependency on the Skill tool.

Flipped via Phase 0 validation outcome.  See
``phase_0_validation.py`` and spec section 9.
"""

MAX_CROSS_REF_RETRIES = 2
"""Default maximum re-generation attempts when a phase's cross-reference
verification fails.  Mirrors the existing default in orchestrator.py;
re-exported here for consistency."""
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest .methodology/tests/cli/methodology_runner/test_constants.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add .methodology/src/cli/methodology_runner/constants.py .methodology/tests/cli/methodology_runner/test_constants.py
git commit -m "feat(methodology-runner): add constants module for tunable thresholds"
```

---

## Task 2: Add new dataclasses to `models.py`

Introduces dataclasses the rest of the implementation needs: skill catalog entry, phase skill manifest, baseline config, and prelude spec.

**Files:**
- Modify: `.methodology/src/cli/methodology_runner/models.py`
- Create: `.methodology/tests/cli/methodology_runner/test_models_skills.py`

- [ ] **Step 1: Write the failing test**

Create `.methodology/tests/cli/methodology_runner/test_models_skills.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest .methodology/tests/cli/methodology_runner/test_models_skills.py -v`
Expected: FAIL — import errors for the new dataclasses.

- [ ] **Step 3: Add the new dataclasses to `.methodology/src/cli/methodology_runner/models.py`**

Append the following after the existing `ProjectState` class (at the end of the file, before any trailing blank lines):

```python
# ---------------------------------------------------------------------------
# Skill-routing types  (CD-002 Section 11 — skill-driven selection)
# ---------------------------------------------------------------------------

class SkillSource(Enum):
    """Why the Skill-Selector picked a given skill for a phase."""

    BASELINE = "baseline"
    EXPERTISE_MAPPING = "expertise-mapping"
    SELECTOR_JUDGMENT = "selector-judgment"


@dataclass(frozen=True)
class SkillCatalogEntry:
    """A single SKILL.md discovered on disk.

    Holds just enough metadata to present the compact catalog to the
    Skill-Selector without loading the full SKILL.md body.  See
    ``skill_catalog.py`` for discovery.
    """

    id: str
    description: str
    source_path: Path
    source_location: str  # "project" | "user" | "plugin"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "source_path": str(self.source_path),
            "source_location": self.source_location,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SkillCatalogEntry:
        return cls(
            id=d["id"],
            description=d["description"],
            source_path=Path(d["source_path"]),
            source_location=d["source_location"],
        )


@dataclass(frozen=True)
class SkillChoice:
    """One skill the selector picked for a phase.

    ``source`` records why the skill was chosen.  ``mapped_from`` is
    populated only when ``source == EXPERTISE_MAPPING`` and records
    the free-text expertise string from the stack manifest that the
    selector matched against this skill.
    """

    id: str
    source: SkillSource
    rationale: str
    mapped_from: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "source": self.source.value,
            "rationale": self.rationale,
        }
        if self.mapped_from is not None:
            d["mapped_from"] = self.mapped_from
        return d

    @classmethod
    def from_dict(cls, d: dict) -> SkillChoice:
        return cls(
            id=d["id"],
            source=SkillSource(d["source"]),
            rationale=d["rationale"],
            mapped_from=d.get("mapped_from"),
        )


@dataclass(frozen=True)
class PhaseSkillManifest:
    """The Skill-Selector's output for a single phase.

    Persisted to the workspace as ``phase-NNN-skills.yaml`` before the
    phase runs, and read back by the orchestrator to build prelude
    files.  Locked across cross-reference retries within the same
    enhancement run.
    """

    phase_id: str
    selector_run_at: str
    selector_model: str
    generator_skills: list[SkillChoice]
    judge_skills: list[SkillChoice]
    overall_rationale: str

    def to_dict(self) -> dict:
        return {
            "phase_id": self.phase_id,
            "selector_run_at": self.selector_run_at,
            "selector_model": self.selector_model,
            "generator_skills": [s.to_dict() for s in self.generator_skills],
            "judge_skills": [s.to_dict() for s in self.judge_skills],
            "overall_rationale": self.overall_rationale,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PhaseSkillManifest:
        return cls(
            phase_id=d["phase_id"],
            selector_run_at=d["selector_run_at"],
            selector_model=d["selector_model"],
            generator_skills=[
                SkillChoice.from_dict(s) for s in d["generator_skills"]
            ],
            judge_skills=[
                SkillChoice.from_dict(s) for s in d["judge_skills"]
            ],
            overall_rationale=d["overall_rationale"],
        )


@dataclass(frozen=True)
class BaselineSkillConfig:
    """Parsed ``skills-baselines.yaml``.

    Maps phase_id to generator and judge baseline skill ID lists.  The
    Skill-Selector treats these as the non-negotiable floor; they must
    appear in every PhaseSkillManifest with ``source: baseline``.
    """

    version: int
    phases: dict[str, dict[str, list[str]]]
    # phases[phase_id] == {"generator": [...], "judge": [...]}

    def baselines_for(self, phase_id: str) -> tuple[list[str], list[str]]:
        """Return ``(generator_baseline, judge_baseline)`` for *phase_id*.

        Raises ``KeyError`` if the phase has no entry in the config.
        """
        entry = self.phases[phase_id]
        return list(entry.get("generator", [])), list(entry.get("judge", []))

    def all_baseline_ids(self) -> set[str]:
        """Return every skill ID referenced by any baseline, flat."""
        out: set[str] = set()
        for entry in self.phases.values():
            out.update(entry.get("generator", []))
            out.update(entry.get("judge", []))
        return out


@dataclass(frozen=True)
class PreludeSpec:
    """Built from a ``PhaseSkillManifest`` by ``prelude.py``.

    ``generator_text`` and ``judge_text`` are the exact content that
    will be written to disk and passed to prompt-runner via the
    ``--generator-prelude`` and ``--judge-prelude`` flags.  ``mode``
    records which design (``skill-tool`` or ``inline``) was used so
    callers can log it.
    """

    generator_text: str
    judge_text: str
    mode: str  # "skill-tool" | "inline"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest .methodology/tests/cli/methodology_runner/test_models_skills.py -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Verify existing model tests still pass**

Run: `pytest .methodology/tests/cli/methodology_runner/ -v`
Expected: all tests PASS (previously passing tests must not regress)

- [ ] **Step 6: Commit**

```bash
git add .methodology/src/cli/methodology_runner/models.py .methodology/tests/cli/methodology_runner/test_models_skills.py
git commit -m "feat(methodology-runner): add skill-routing dataclasses to models"
```

---

## Task 3: Skill catalog discovery

Walks three locations (`workspace/.claude/skills/`, `~/.claude/skills/`, `~/.claude/plugins/*/skills/`) and builds an in-memory catalog from SKILL.md frontmatter.

**Files:**
- Create: `.methodology/src/cli/methodology_runner/skill_catalog.py`
- Create: `.methodology/tests/cli/methodology_runner/test_skill_catalog.py`

- [ ] **Step 1: Write the failing tests**

Create `.methodology/tests/cli/methodology_runner/test_skill_catalog.py`:

```python
"""Tests for skill catalog discovery."""
from pathlib import Path

import pytest

from methodology_runner.skill_catalog import (
    CatalogBuildError,
    build_catalog,
    parse_skill_md,
)


def _write_skill(dir_path: Path, name: str, description: str) -> Path:
    skill_dir = dir_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"""---
name: {name}
description: {description}
---

# {name}

Body content.
""",
        encoding="utf-8",
    )
    return skill_md


def test_parse_skill_md_extracts_name_and_description(tmp_path: Path):
    path = _write_skill(tmp_path / "skills", "tdd", "Test-driven development")
    entry = parse_skill_md(path, source_location="user")
    assert entry is not None
    assert entry.id == "tdd"
    assert entry.description == "Test-driven development"
    assert entry.source_location == "user"


def test_parse_skill_md_returns_none_for_missing_frontmatter(tmp_path: Path):
    path = tmp_path / "bad" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("# no frontmatter\n\nbody", encoding="utf-8")
    assert parse_skill_md(path, source_location="user") is None


def test_parse_skill_md_derives_id_from_directory_when_name_missing(tmp_path: Path):
    path = tmp_path / "my-skill" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        """---
description: A skill without an explicit name field
---
body
""",
        encoding="utf-8",
    )
    entry = parse_skill_md(path, source_location="user")
    assert entry is not None
    assert entry.id == "my-skill"


def test_parse_skill_md_rejects_empty_description(tmp_path: Path):
    path = tmp_path / "empty" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        """---
name: empty
description:
---
body
""",
        encoding="utf-8",
    )
    assert parse_skill_md(path, source_location="user") is None


def test_build_catalog_walks_three_locations(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    _write_skill(workspace / ".claude" / "skills", "proj-skill", "Project")
    _write_skill(user_home / ".claude" / "skills", "user-skill", "User")
    _write_skill(
        user_home / ".claude" / "plugins" / "somepkg" / "skills",
        "plugin-skill",
        "Plugin",
    )
    catalog = build_catalog(workspace=workspace, user_home=user_home)
    ids = {e.id for e in catalog.values()}
    assert ids == {"proj-skill", "user-skill", "plugin-skill"}


def test_build_catalog_priority_project_beats_user_beats_plugin(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    _write_skill(workspace / ".claude" / "skills", "same", "from project")
    _write_skill(user_home / ".claude" / "skills", "same", "from user")
    _write_skill(
        user_home / ".claude" / "plugins" / "pk" / "skills",
        "same",
        "from plugin",
    )
    catalog = build_catalog(workspace=workspace, user_home=user_home)
    assert catalog["same"].description == "from project"
    assert catalog["same"].source_location == "project"


def test_build_catalog_empty_raises_catalog_build_error(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    workspace.mkdir()
    user_home.mkdir()
    with pytest.raises(CatalogBuildError) as exc_info:
        build_catalog(workspace=workspace, user_home=user_home)
    assert "no Claude Code skills discovered" in str(exc_info.value).lower()


def test_build_catalog_skips_invalid_entries_but_keeps_valid_ones(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    _write_skill(user_home / ".claude" / "skills", "good", "Good skill")
    # Invalid one
    bad = user_home / ".claude" / "skills" / "bad" / "SKILL.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("# no frontmatter", encoding="utf-8")
    catalog = build_catalog(workspace=workspace, user_home=user_home)
    assert "good" in catalog
    assert "bad" not in catalog
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest .methodology/tests/cli/methodology_runner/test_skill_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'methodology_runner.skill_catalog'`

- [ ] **Step 3: Create `.methodology/src/cli/methodology_runner/skill_catalog.py`**

```python
"""Auto-discovery of Claude Code skills from the local filesystem.

Walks three locations in priority order, parses SKILL.md YAML
frontmatter, and returns an in-memory catalog keyed by skill ID.

Priority order (highest first):

1. ``<workspace>/.claude/skills/**/SKILL.md``
2. ``~/.claude/skills/**/SKILL.md``
3. ``~/.claude/plugins/*/skills/**/SKILL.md``

Higher-priority locations shadow lower ones; overrides are logged.
If the final catalog is empty, :class:`CatalogBuildError` is raised
so the orchestrator can halt before any phase runs (spec failure
mode 7).

The catalog is never persisted to disk.  SKILL.md files on disk are
the single source of truth; the catalog is rebuilt on every run.
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from .models import SkillCatalogEntry


logger = logging.getLogger(__name__)


_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL
)
"""Matches a SKILL.md YAML frontmatter block at the start of the file."""

_VALID_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
"""Valid skill IDs are lowercase kebab-case, starting with a letter or digit."""


class CatalogBuildError(RuntimeError):
    """Raised when catalog discovery cannot yield at least one valid skill."""


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    """Extract simple ``key: value`` pairs from a SKILL.md frontmatter block.

    Returns None if the file has no frontmatter.  We intentionally do
    not bring in PyYAML for this — SKILL.md frontmatter fields we care
    about (``name``, ``description``) are always plain strings, and a
    small hand-rolled parser avoids a dependency.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None
    body = match.group(1)
    out: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def parse_skill_md(
    path: Path, source_location: str,
) -> SkillCatalogEntry | None:
    """Parse a single SKILL.md file.  Returns None on any validation failure.

    Invalid entries are logged at WARNING level but do not halt the
    catalog build — they are simply skipped.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("skill_catalog: cannot read %s: %s", path, exc)
        return None

    frontmatter = _parse_frontmatter(text)
    if frontmatter is None:
        logger.warning("skill_catalog: %s has no YAML frontmatter; skipping", path)
        return None

    skill_id = frontmatter.get("name") or path.parent.name
    if not skill_id or not _VALID_ID_RE.match(skill_id):
        logger.warning(
            "skill_catalog: %s has invalid or missing id %r; skipping",
            path, skill_id,
        )
        return None

    description = frontmatter.get("description", "").strip()
    if not description:
        logger.warning(
            "skill_catalog: %s has empty description; skipping", path,
        )
        return None

    return SkillCatalogEntry(
        id=skill_id,
        description=description,
        source_path=path.resolve(),
        source_location=source_location,
    )


def _walk_skills(root: Path) -> list[Path]:
    """Yield every SKILL.md path under *root*.  Missing root is fine."""
    if not root.exists():
        return []
    return sorted(root.rglob("SKILL.md"))


def build_catalog(
    *,
    workspace: Path,
    user_home: Path | None = None,
) -> dict[str, SkillCatalogEntry]:
    """Build the skill catalog by walking the three discovery locations.

    Parameters
    ----------
    workspace:
        The methodology-runner workspace directory.  Project-local
        skills live under ``<workspace>/.claude/skills/``.
    user_home:
        Home directory to look under.  Defaults to ``Path.home()``.
        Exposed for testing.

    Returns
    -------
    dict[str, SkillCatalogEntry]
        Keyed by skill ID.  Higher-priority locations shadow lower
        ones; every shadow is logged at INFO level.

    Raises
    ------
    CatalogBuildError
        If no valid skills are discovered across all three locations.
    """
    if user_home is None:
        user_home = Path.home()

    # (location_label, root_path) in priority order: first wins.
    sources: list[tuple[str, Path]] = [
        ("project", workspace / ".claude" / "skills"),
        ("user", user_home / ".claude" / "skills"),
    ]
    # Plugins: one sub-root per plugin directory under ~/.claude/plugins
    plugins_dir = user_home / ".claude" / "plugins"
    if plugins_dir.exists():
        for plugin in sorted(plugins_dir.iterdir()):
            if plugin.is_dir():
                sources.append(("plugin", plugin / "skills"))

    catalog: dict[str, SkillCatalogEntry] = {}
    for source_location, root in sources:
        for skill_md in _walk_skills(root):
            entry = parse_skill_md(skill_md, source_location=source_location)
            if entry is None:
                continue
            existing = catalog.get(entry.id)
            if existing is None:
                catalog[entry.id] = entry
                continue
            # Shadowing: higher priority was registered first, so
            # keep existing and log the override.
            logger.info(
                "skill_catalog: %s at %s shadowed by %s at %s",
                entry.id,
                entry.source_path,
                existing.source_location,
                existing.source_path,
            )

    if not catalog:
        raise CatalogBuildError(
            "no Claude Code skills discovered.\n\n"
            "Searched:\n"
            + "\n".join(f"  - {lbl}: {root}" for lbl, root in sources)
            + "\n\nInstall the baseline skill pack with:\n"
            "  /plugin install methodology-runner-skills\n"
            "Or place your own SKILL.md files under .claude/skills/ in "
            "this workspace, or under ~/.claude/skills/ for your user."
        )

    return catalog
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest .methodology/tests/cli/methodology_runner/test_skill_catalog.py -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Commit**

```bash
git add .methodology/src/cli/methodology_runner/skill_catalog.py .methodology/tests/cli/methodology_runner/test_skill_catalog.py
git commit -m "feat(methodology-runner): auto-discover skill catalog from filesystem"
```

---

## Task 4: Baseline skills configuration

Loads and validates `.methodology/docs/skills-baselines.yaml` at run start.

**Files:**
- Create: `.methodology/src/cli/methodology_runner/baseline_config.py`
- Create: `.methodology/docs/skills-baselines.yaml`
- Create: `.methodology/tests/cli/methodology_runner/test_baseline_config.py`

- [ ] **Step 1: Write the failing tests**

Create `.methodology/tests/cli/methodology_runner/test_baseline_config.py`:

```python
"""Tests for baseline skill configuration loading."""
from pathlib import Path

import pytest

from methodology_runner.baseline_config import (
    BaselineConfigError,
    load_baseline_config,
    validate_against_catalog,
)
from methodology_runner.models import (
    BaselineSkillConfig,
    SkillCatalogEntry,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_baseline_config_happy_path(tmp_path: Path):
    _write(tmp_path / "skills-baselines.yaml", """
version: 1
phases:
  PH-000-requirements-inventory:
    generator: [requirements-extraction, traceability-discipline]
    judge: [requirements-quality-review, traceability-discipline]
""")
    cfg = load_baseline_config(tmp_path / "skills-baselines.yaml")
    assert cfg.version == 1
    gen, jud = cfg.baselines_for("PH-000-requirements-inventory")
    assert gen == ["requirements-extraction", "traceability-discipline"]
    assert jud == ["requirements-quality-review", "traceability-discipline"]


def test_load_baseline_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(BaselineConfigError) as exc_info:
        load_baseline_config(tmp_path / "nope.yaml")
    assert "not found" in str(exc_info.value).lower()


def test_load_baseline_config_malformed_yaml_raises(tmp_path: Path):
    _write(tmp_path / "bad.yaml", "version: 1\n  - oops not a mapping")
    with pytest.raises(BaselineConfigError):
        load_baseline_config(tmp_path / "bad.yaml")


def test_load_baseline_config_missing_version_raises(tmp_path: Path):
    _write(tmp_path / "noversion.yaml", "phases: {}")
    with pytest.raises(BaselineConfigError):
        load_baseline_config(tmp_path / "noversion.yaml")


def test_validate_against_catalog_happy_path(tmp_path: Path):
    cfg = BaselineSkillConfig(
        version=1,
        phases={"PH-X": {"generator": ["a"], "judge": ["b"]}},
    )
    catalog = {
        "a": SkillCatalogEntry(
            id="a", description="A", source_path=Path("/a"), source_location="user",
        ),
        "b": SkillCatalogEntry(
            id="b", description="B", source_path=Path("/b"), source_location="user",
        ),
    }
    validate_against_catalog(cfg, catalog)  # no exception


def test_validate_against_catalog_missing_skill_raises():
    cfg = BaselineSkillConfig(
        version=1,
        phases={"PH-X": {"generator": ["missing"], "judge": []}},
    )
    with pytest.raises(BaselineConfigError) as exc_info:
        validate_against_catalog(cfg, {})
    assert "missing" in str(exc_info.value)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest .methodology/tests/cli/methodology_runner/test_baseline_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'methodology_runner.baseline_config'`

- [ ] **Step 3: Create `.methodology/src/cli/methodology_runner/baseline_config.py`**

```python
"""Load and validate ``.methodology/docs/skills-baselines.yaml``.

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
from typing import Any

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
            f"Expected file at .methodology/docs/skills-baselines.yaml.\n"
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
```

- [ ] **Step 4: Create `.methodology/docs/skills-baselines.yaml`**

```yaml
# Non-negotiable baseline skills per methodology phase.
#
# The Skill-Selector treats these as a required floor and may add
# additional skills on top based on stack-manifest expertise hints
# and judgments about prior phase artifacts.
#
# Changing this file does not require a code change.  methodology-runner
# reads it fresh at the start of every run.
#
# Every skill ID referenced here must exist in the discovered skill
# catalog at run start, or methodology-runner halts before any phase
# executes (spec failure mode 9).

version: 1

phases:
  PH-000-requirements-inventory:
    generator_baseline:
      - requirements-extraction
      - traceability-discipline
    judge_baseline:
      - requirements-quality-review
      - traceability-discipline

  PH-001-feature-specification:
    generator_baseline:
      - feature-specification
      - traceability-discipline
    judge_baseline:
      - feature-quality-review
      - traceability-discipline

  PH-002-architecture:
    generator_baseline:
      - tech-stack-catalog
      - architecture-decomposition
      - traceability-discipline
    judge_baseline:
      - architecture-review
      - traceability-discipline

  PH-003-solution-design:
    generator_baseline:
      - solution-design-patterns
      - traceability-discipline
    judge_baseline:
      - solution-design-review
      - traceability-discipline

  PH-004-interface-contracts:
    generator_baseline:
      - contract-first-design
      - traceability-discipline
    judge_baseline:
      - contract-review
      - traceability-discipline

  PH-005-intelligent-simulations:
    generator_baseline:
      - simulation-framework
      - traceability-discipline
    judge_baseline:
      - simulation-review
      - traceability-discipline

  PH-006-incremental-implementation:
    generator_baseline:
      - tdd
      - traceability-discipline
    judge_baseline:
      - code-review-discipline
      - traceability-discipline

  PH-007-verification-sweep:
    generator_baseline:
      - cross-component-verification
      - traceability-discipline
    judge_baseline:
      - verification-review
      - traceability-discipline
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest .methodology/tests/cli/methodology_runner/test_baseline_config.py -v`
Expected: PASS, 6 tests

- [ ] **Step 6: Commit**

```bash
git add .methodology/src/cli/methodology_runner/baseline_config.py .methodology/tests/cli/methodology_runner/test_baseline_config.py .methodology/docs/skills-baselines.yaml
git commit -m "feat(methodology-runner): baseline skills config loader and data file"
```

---

## Task 5: Artifact summarizer

Produces a short AI-generated summary of prior phase artifacts that exceed the size threshold, caches the summary on disk, and returns it on subsequent calls.

**Files:**
- Create: `.methodology/src/cli/methodology_runner/artifact_summarizer.py`
- Create: `.methodology/tests/cli/methodology_runner/test_artifact_summarizer.py`

- [ ] **Step 1: Write the failing tests**

Create `.methodology/tests/cli/methodology_runner/test_artifact_summarizer.py`:

```python
"""Tests for artifact summarization with caching."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from methodology_runner.artifact_summarizer import (
    ArtifactSummaryProvider,
    SummarizerResult,
)
from methodology_runner.constants import ARTIFACT_FULL_CONTENT_THRESHOLD


@dataclass
class _StubClient:
    responses: list[str]
    received: list[str] = field(default_factory=list)
    _idx: int = 0

    def call(self, call: Any):  # matches ClaudeClient protocol minimally
        self.received.append(call.prompt)
        text = self.responses[self._idx]
        self._idx += 1
        from prompt_runner.claude_client import ClaudeResponse
        return ClaudeResponse(stdout=text, stderr="", returncode=0)


def _small_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("small artifact body", encoding="utf-8")


def _large_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * (ARTIFACT_FULL_CONTENT_THRESHOLD + 10), encoding="utf-8")


def test_small_artifact_returned_in_full_no_claude_call(tmp_path: Path):
    art = tmp_path / "small.md"
    _small_file(art)
    client = _StubClient(responses=[])
    provider = ArtifactSummaryProvider(
        cache_dir=tmp_path / ".cache",
        claude_client=client,
    )
    result = provider.get(art)
    assert result.full_content == "small artifact body"
    assert result.summary is None
    assert client.received == []


def test_large_artifact_triggers_summary_call(tmp_path: Path):
    art = tmp_path / "big.md"
    _large_file(art)
    client = _StubClient(responses=["A concise summary of the file."])
    provider = ArtifactSummaryProvider(
        cache_dir=tmp_path / ".cache",
        claude_client=client,
    )
    result = provider.get(art)
    assert result.full_content is None
    assert result.summary == "A concise summary of the file."
    assert len(client.received) == 1


def test_cached_summary_returned_without_second_call(tmp_path: Path):
    art = tmp_path / "big.md"
    _large_file(art)
    client = _StubClient(responses=["first summary"])
    provider = ArtifactSummaryProvider(
        cache_dir=tmp_path / ".cache",
        claude_client=client,
    )
    provider.get(art)
    # Second provider reading same cache dir: no new client calls.
    client2 = _StubClient(responses=[])
    provider2 = ArtifactSummaryProvider(
        cache_dir=tmp_path / ".cache",
        claude_client=client2,
    )
    result = provider2.get(art)
    assert result.summary == "first summary"
    assert client2.received == []


def test_cache_invalidates_when_artifact_changes(tmp_path: Path):
    art = tmp_path / "big.md"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text("x" * (ARTIFACT_FULL_CONTENT_THRESHOLD + 10), encoding="utf-8")
    client = _StubClient(responses=["old", "new"])
    provider = ArtifactSummaryProvider(
        cache_dir=tmp_path / ".cache",
        claude_client=client,
    )
    first = provider.get(art)
    assert first.summary == "old"

    # Rewrite the file with different content but same size
    art.write_text("y" * (ARTIFACT_FULL_CONTENT_THRESHOLD + 10), encoding="utf-8")
    second = provider.get(art)
    assert second.summary == "new"
    assert len(client.received) == 2


def test_get_returns_error_when_file_missing(tmp_path: Path):
    provider = ArtifactSummaryProvider(
        cache_dir=tmp_path / ".cache",
        claude_client=_StubClient(responses=[]),
    )
    try:
        provider.get(tmp_path / "missing.md")
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest .methodology/tests/cli/methodology_runner/test_artifact_summarizer.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create `.methodology/src/cli/methodology_runner/artifact_summarizer.py`**

```python
"""Size-threshold-gated summarization of prior phase artifacts.

The Skill-Selector receives every prior phase artifact as input.
Small artifacts (under ``ARTIFACT_FULL_CONTENT_THRESHOLD`` bytes) are
passed in full.  Larger artifacts are replaced by a short
AI-generated summary, computed once and cached on disk so later
selector invocations reuse it.

Cache layout::

    <workspace>/.methodology-runner/artifact-summaries/
        <sha256-of-path>-<sha256-of-content>.txt

The cache key includes both the absolute path and a content hash,
so a file that is rewritten with new content gets re-summarized
but a file that is merely touched does not.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import ARTIFACT_FULL_CONTENT_THRESHOLD

if TYPE_CHECKING:
    from prompt_runner.claude_client import ClaudeClient, ClaudeCall


@dataclass(frozen=True)
class SummarizerResult:
    """Outcome of a single ``provider.get(path)`` call.

    Exactly one of ``full_content`` or ``summary`` is non-None.
    """

    path: Path
    size_bytes: int
    full_content: str | None
    summary: str | None


SUMMARY_PROMPT_TEMPLATE = """\
You are summarizing a prior-phase artifact from an AI-driven development
methodology pipeline.  A downstream Skill-Selector agent will read your
summary to decide which specialized knowledge skills the next phase
needs.

Produce a concise 1-2 paragraph summary focused on:

- What kind of artifact this is and which phase produced it.
- The key technical decisions, components, frameworks, or types declared.
- Any implications for what skills the next phase will need.

Do NOT reproduce the full content.  Do NOT list every element.  Keep
the summary under 500 words.

---

# Source artifact

Path: {path}
Size: {size_bytes} bytes

---

# Content

{content}
"""


class ArtifactSummaryProvider:
    """Returns either full content (small files) or a cached summary (large).

    Parameters
    ----------
    cache_dir:
        Directory where summaries are persisted.  Created on demand.
    claude_client:
        Injected Claude client used for summarization calls.
    model:
        Optional model override forwarded to claude.
    threshold:
        Size (in bytes) above which summaries are produced.  Defaults
        to :data:`ARTIFACT_FULL_CONTENT_THRESHOLD`.
    """

    def __init__(
        self,
        *,
        cache_dir: Path,
        claude_client: "ClaudeClient",
        model: str | None = None,
        threshold: int = ARTIFACT_FULL_CONTENT_THRESHOLD,
    ) -> None:
        self._cache_dir = cache_dir
        self._claude_client = claude_client
        self._model = model
        self._threshold = threshold

    def get(self, path: Path) -> SummarizerResult:
        """Return the full content or a cached summary for *path*.

        Raises :class:`FileNotFoundError` if the artifact does not
        exist.
        """
        if not path.exists():
            raise FileNotFoundError(f"artifact not found: {path}")

        content = path.read_text(encoding="utf-8")
        size = len(content.encode("utf-8"))

        if size <= self._threshold:
            return SummarizerResult(
                path=path,
                size_bytes=size,
                full_content=content,
                summary=None,
            )

        cache_path = self._cache_path_for(path, content)
        if cache_path.exists():
            cached = cache_path.read_text(encoding="utf-8")
            return SummarizerResult(
                path=path,
                size_bytes=size,
                full_content=None,
                summary=cached,
            )

        summary = self._call_claude_for_summary(path, content, size)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(summary, encoding="utf-8")
        return SummarizerResult(
            path=path,
            size_bytes=size,
            full_content=None,
            summary=summary,
        )

    def _cache_path_for(self, path: Path, content: str) -> Path:
        path_hash = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return self._cache_dir / f"{path_hash}-{content_hash}.txt"

    def _call_claude_for_summary(
        self, path: Path, content: str, size_bytes: int,
    ) -> str:
        from prompt_runner.claude_client import ClaudeCall

        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            path=path,
            size_bytes=size_bytes,
            content=content,
        )
        logs_dir = self._cache_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stem = f"summarize-{uuid.uuid4().hex[:8]}"
        call = ClaudeCall(
            prompt=prompt,
            session_id=str(uuid.uuid4()),
            new_session=True,
            model=self._model,
            stdout_log_path=logs_dir / f"{stem}.stdout.log",
            stderr_log_path=logs_dir / f"{stem}.stderr.log",
            stream_header=f"── artifact summary / {path.name} ──",
            workspace_dir=path.parent,
        )
        response = self._claude_client.call(call)
        return response.stdout.strip()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest .methodology/tests/cli/methodology_runner/test_artifact_summarizer.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add .methodology/src/cli/methodology_runner/artifact_summarizer.py .methodology/tests/cli/methodology_runner/test_artifact_summarizer.py
git commit -m "feat(methodology-runner): artifact summarizer with disk cache"
```

---

## Task 6: Skill-Selector agent

The Skill-Selector assembles a Claude prompt that includes the phase definition, compact skill catalog, prior artifacts (full or summarized), and stack manifest. It parses the YAML reply, validates it, and returns a PhaseSkillManifest.

**Files:**
- Create: `.methodology/src/cli/methodology_runner/skill_selector.py`
- Create: `.methodology/tests/cli/methodology_runner/test_skill_selector.py`

- [ ] **Step 1: Write the failing tests**

Create `.methodology/tests/cli/methodology_runner/test_skill_selector.py`:

```python
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
```

Note: these tests depend on `get_phase("PH-006-incremental-implementation")` which does not yet exist. Task 7 renumbers phases and creates this ID. Until Task 7 is complete, replace this call with a hand-built `PhaseConfig` fixture in the tests or skip running this suite. After Task 7, switch back to `get_phase(...)`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest .methodology/tests/cli/methodology_runner/test_skill_selector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'methodology_runner.skill_selector'`

- [ ] **Step 3: Create `.methodology/src/cli/methodology_runner/skill_selector.py`**

```python
"""Skill-Selector agent.

Runs once per phase before the phase's meta-prompt.  Assembles a
Claude prompt from the phase definition, the compact skill catalog,
prior phase artifacts, and the stack manifest (if any), invokes
Claude, parses the YAML reply, and validates it against the catalog
and the baseline config.

On success, returns a :class:`PhaseSkillManifest` ready to be written
to the workspace as ``phase-NNN-skills.yaml`` and used to build
preludes.  On any validation failure, raises :class:`SelectorError`
so the orchestrator can halt the phase (critical halt semantics per
spec section 12).

See spec section 6 for the selector design.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .artifact_summarizer import ArtifactSummaryProvider
from .constants import MAX_SKILLS_PER_PHASE
from .models import (
    BaselineSkillConfig,
    PhaseConfig,
    PhaseSkillManifest,
    SkillCatalogEntry,
    SkillChoice,
    SkillSource,
)

if TYPE_CHECKING:
    from prompt_runner.claude_client import ClaudeClient


class SelectorError(RuntimeError):
    """Raised on any selector invocation or validation failure."""


@dataclass(frozen=True)
class SelectorInputs:
    """Everything the selector needs to decide a phase's skill set."""

    phase_config: PhaseConfig
    catalog: dict[str, SkillCatalogEntry]
    baseline_config: BaselineSkillConfig
    workspace_dir: Path
    prior_artifact_paths: list[Path]
    stack_manifest_path: Path | None


_SELECTOR_SYSTEM_PROMPT = """\
You are the Skill-Selector for an AI-driven software development
methodology pipeline.  Your sole job is to choose which Claude Code
skills the generator agent and the judge agent should load for one
specific phase of the pipeline.

You do not generate artifacts, you do not evaluate artifacts, and
you do not modify any prior work.  You only pick skills.

## Inputs you will receive

1. The phase definition (purpose, inputs, outputs, quality focus).
2. A baseline skill list for this phase that MUST appear in your
   output unchanged, with source: baseline.
3. The compact skill catalog: every available skill ID with its
   one-line description only.  No skill body content.
4. Summaries (or full content) of every prior-phase artifact in
   the workspace.
5. The stack manifest, if it exists yet (from PH-002 Architecture
   or later).  Read its expected_expertise lists carefully — each
   entry is a free-text description of the kind of knowledge a
   component needs.  Map each description to one or more concrete
   skill IDs from the catalog.

## Output contract

Your entire response MUST be a single valid YAML document with
EXACTLY these top-level keys (no extras, no prose before or after):

    phase_id:          the phase ID (string)
    selector_run_at:   ISO 8601 timestamp
    selector_model:    the model you are running as (string)
    generator_skills:  list of skill choices for the generator
    judge_skills:      list of skill choices for the judge
    overall_rationale: free text explaining the selection as a whole

Every entry in generator_skills and judge_skills must have:

    id:         a skill ID that exists in the catalog
    source:     one of "baseline", "expertise-mapping", "selector-judgment"
    rationale:  why you picked it (non-empty)

Entries with source "expertise-mapping" MUST include:

    mapped_from: the exact expertise string from the stack manifest

## Rules you must follow

- Every baseline skill must appear in your output with source: baseline.
- Every skill ID you emit must exist in the catalog.
- Never invent skill IDs.  If you believe a skill is missing from the
  catalog, say so in overall_rationale but do NOT include it in the
  lists.
- The combined unique skill count (generator + judge) must not
  exceed {max_skills}.  If you want more, prioritize and explain the
  trade-off in overall_rationale.

Do not wrap your YAML in a code fence.  Do not prepend or append
any prose.  Your entire response is the YAML document.
"""


def _build_compact_catalog_block(catalog: dict[str, SkillCatalogEntry]) -> str:
    lines = []
    for skill_id in sorted(catalog):
        entry = catalog[skill_id]
        lines.append(f"- id: {skill_id}")
        lines.append(f"  description: {entry.description}")
    return "\n".join(lines)


def _build_prior_artifacts_block(
    summarizer: ArtifactSummaryProvider, paths: list[Path],
) -> str:
    if not paths:
        return "(no prior artifacts — this is the first phase)"
    blocks: list[str] = []
    for path in paths:
        try:
            result = summarizer.get(path)
        except FileNotFoundError:
            blocks.append(f"### {path}\n\n(file not found on disk)")
            continue
        if result.full_content is not None:
            blocks.append(
                f"### {path}  ({result.size_bytes} bytes — full content)\n\n"
                f"```\n{result.full_content}\n```"
            )
        else:
            blocks.append(
                f"### {path}  ({result.size_bytes} bytes — AI summary)\n\n"
                f"{result.summary}"
            )
    return "\n\n".join(blocks)


def _build_stack_manifest_block(path: Path | None) -> str:
    if path is None or not path.exists():
        return (
            "(no stack manifest yet — this phase runs before or as "
            "PH-002 Architecture)"
        )
    return f"```yaml\n{path.read_text(encoding='utf-8')}\n```"


def _assemble_selector_prompt(
    inputs: SelectorInputs,
    summarizer: ArtifactSummaryProvider,
    selector_model: str | None,
) -> str:
    gen_base, jud_base = inputs.baseline_config.baselines_for(
        inputs.phase_config.phase_id,
    )
    system = _SELECTOR_SYSTEM_PROMPT.format(max_skills=MAX_SKILLS_PER_PHASE)
    return f"""{system}

---

# Phase definition

Phase ID: {inputs.phase_config.phase_id}
Phase name: {inputs.phase_config.phase_name}
Purpose / generation instructions:
{inputs.phase_config.generation_instructions}

Judge guidance:
{inputs.phase_config.judge_guidance}

---

# Baseline skills for this phase (MUST appear with source: baseline)

Generator baseline: {', '.join(gen_base) or '(none)'}
Judge baseline:     {', '.join(jud_base) or '(none)'}

---

# Compact skill catalog

{_build_compact_catalog_block(inputs.catalog)}

---

# Stack manifest

{_build_stack_manifest_block(inputs.stack_manifest_path)}

---

# Prior phase artifacts

{_build_prior_artifacts_block(summarizer, inputs.prior_artifact_paths)}

---

Produce the phase-skills YAML for phase {inputs.phase_config.phase_id}.
Remember: your entire response is a single YAML document; no code fence,
no commentary.

Use {selector_model or 'the current model'} as the selector_model value.
Use {datetime.now(timezone.utc).isoformat()} as the selector_run_at value.
"""


def _parse_and_validate(
    yaml_text: str,
    inputs: SelectorInputs,
) -> PhaseSkillManifest:
    try:
        raw = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise SelectorError(
            f"selector output is not parseable YAML: {exc}\n\n"
            f"Raw output:\n{yaml_text}"
        ) from exc

    if not isinstance(raw, dict):
        raise SelectorError(
            f"selector output must be a YAML mapping, got {type(raw).__name__}"
        )

    required_top = {
        "phase_id", "selector_run_at", "selector_model",
        "generator_skills", "judge_skills", "overall_rationale",
    }
    missing = required_top - set(raw.keys())
    if missing:
        raise SelectorError(
            f"selector output missing required top-level fields: "
            f"{sorted(missing)}"
        )

    def _parse_skill_list(key: str) -> list[SkillChoice]:
        items = raw.get(key)
        if not isinstance(items, list):
            raise SelectorError(f"{key} must be a list")
        out: list[SkillChoice] = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise SelectorError(f"{key}[{i}] must be a mapping")
            if "id" not in item or "source" not in item or "rationale" not in item:
                raise SelectorError(
                    f"{key}[{i}] missing required fields (id, source, rationale)"
                )
            try:
                source = SkillSource(item["source"])
            except ValueError as exc:
                raise SelectorError(
                    f"{key}[{i}] has invalid source {item['source']!r}: "
                    f"must be one of {[s.value for s in SkillSource]}"
                ) from exc
            out.append(
                SkillChoice(
                    id=item["id"],
                    source=source,
                    rationale=str(item["rationale"]),
                    mapped_from=item.get("mapped_from"),
                )
            )
        return out

    generator = _parse_skill_list("generator_skills")
    judge = _parse_skill_list("judge_skills")

    # All IDs must exist in catalog
    unknown_gen = [s.id for s in generator if s.id not in inputs.catalog]
    unknown_jud = [s.id for s in judge if s.id not in inputs.catalog]
    if unknown_gen or unknown_jud:
        raise SelectorError(
            "selector picked unknown skill IDs not in catalog:\n"
            + "".join(f"  - generator: {s}\n" for s in unknown_gen)
            + "".join(f"  - judge: {s}\n" for s in unknown_jud)
        )

    # Baselines must all be present
    gen_base, jud_base = inputs.baseline_config.baselines_for(
        inputs.phase_config.phase_id,
    )
    gen_ids = {s.id for s in generator if s.source == SkillSource.BASELINE}
    jud_ids = {s.id for s in judge if s.source == SkillSource.BASELINE}
    missing_gen = [b for b in gen_base if b not in gen_ids]
    missing_jud = [b for b in jud_base if b not in jud_ids]
    if missing_gen or missing_jud:
        raise SelectorError(
            "selector output missing required baseline skills:\n"
            + "".join(f"  - generator baseline: {s}\n" for s in missing_gen)
            + "".join(f"  - judge baseline: {s}\n" for s in missing_jud)
        )

    # Cap check
    unique_total = len({s.id for s in generator} | {s.id for s in judge})
    if unique_total > MAX_SKILLS_PER_PHASE:
        raise SelectorError(
            f"selector picked {unique_total} unique skills but cap is "
            f"{MAX_SKILLS_PER_PHASE}"
        )

    return PhaseSkillManifest(
        phase_id=raw["phase_id"],
        selector_run_at=raw["selector_run_at"],
        selector_model=raw["selector_model"],
        generator_skills=generator,
        judge_skills=judge,
        overall_rationale=str(raw["overall_rationale"]),
    )


def invoke_skill_selector(
    inputs: SelectorInputs,
    *,
    claude_client: "ClaudeClient",
    model: str | None,
) -> PhaseSkillManifest:
    """Run the Skill-Selector for *inputs.phase_config*.

    Assembles the selector prompt, invokes Claude, parses and
    validates the YAML reply, and returns a ``PhaseSkillManifest``.
    """
    cache_dir = inputs.workspace_dir / ".methodology-runner" / "artifact-summaries"
    summarizer = ArtifactSummaryProvider(
        cache_dir=cache_dir,
        claude_client=claude_client,
        model=model,
    )
    prompt = _assemble_selector_prompt(inputs, summarizer, selector_model=model)

    from prompt_runner.claude_client import ClaudeCall, ClaudeInvocationError

    logs_dir = inputs.workspace_dir / ".methodology-runner" / "runs" / "selector-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stem = f"selector-{inputs.phase_config.phase_id}-{uuid.uuid4().hex[:8]}"
    call = ClaudeCall(
        prompt=prompt,
        session_id=str(uuid.uuid4()),
        new_session=True,
        model=model,
        stdout_log_path=logs_dir / f"{stem}.stdout.log",
        stderr_log_path=logs_dir / f"{stem}.stderr.log",
        stream_header=f"── skill-selector / {inputs.phase_config.phase_id} ──",
        workspace_dir=inputs.workspace_dir,
    )
    try:
        response = claude_client.call(call)
    except ClaudeInvocationError as exc:
        raise SelectorError(
            f"skill-selector claude call failed: {exc}"
        ) from exc

    return _parse_and_validate(response.stdout, inputs)
```

- [ ] **Step 4: Run the tests**

Run: `pytest .methodology/tests/cli/methodology_runner/test_skill_selector.py -v`

Expected: 5 tests fail with `ValueError: Unknown phase_id 'PH-006-incremental-implementation'` — because the phase renumbering in Task 7 hasn't happened yet. **This is expected**; defer running these tests until after Task 7 is complete. Skip this step for now.

- [ ] **Step 5: Commit**

```bash
git add .methodology/src/cli/methodology_runner/skill_selector.py .methodology/tests/cli/methodology_runner/test_skill_selector.py
git commit -m "feat(methodology-runner): skill-selector agent with output validation"
```

---

## Task 7: Insert PH-002 Architecture phase and renumber

Inserts a new `_PHASE_2_ARCHITECTURE` between Feature Specification and Solution Design; renumbers existing `_PHASE_2`..`_PHASE_6` to `_PHASE_3`..`_PHASE_7`; adds the `stack-manifest.yaml` output path; updates the `PHASES` list.

**Files:**
- Modify: `.methodology/src/cli/methodology_runner/phases.py`
- Create: `.methodology/tests/cli/methodology_runner/test_phases_renumbered.py`

- [ ] **Step 1: Write the failing test**

Create `.methodology/tests/cli/methodology_runner/test_phases_renumbered.py`:

```python
"""Tests for the new PH-002 Architecture phase and renumbering."""
from methodology_runner.phases import (
    PHASES,
    PHASE_MAP,
    get_phase,
)


EXPECTED_ORDER = [
    ("PH-000-requirements-inventory", 0),
    ("PH-001-feature-specification", 1),
    ("PH-002-architecture", 2),
    ("PH-003-solution-design", 3),
    ("PH-004-interface-contracts", 4),
    ("PH-005-intelligent-simulations", 5),
    ("PH-006-incremental-implementation", 6),
    ("PH-007-verification-sweep", 7),
]


def test_eight_phases_in_order():
    ids = [p.phase_id for p in PHASES]
    assert ids == [pid for pid, _ in EXPECTED_ORDER]


def test_phase_numbers_match_order():
    for phase, (expected_id, expected_num) in zip(PHASES, EXPECTED_ORDER):
        assert phase.phase_id == expected_id
        assert phase.phase_number == expected_num


def test_architecture_phase_outputs_stack_manifest():
    arch = get_phase("PH-002-architecture")
    assert "stack-manifest" in arch.output_artifact_path
    assert arch.output_format == "yaml"
    assert arch.predecessors == ["PH-001-feature-specification"]


def test_solution_design_predecessor_is_architecture():
    sd = get_phase("PH-003-solution-design")
    assert "PH-002-architecture" in sd.predecessors


def test_incremental_implementation_predecessors_include_simulations():
    impl = get_phase("PH-006-incremental-implementation")
    assert "PH-005-intelligent-simulations" in impl.predecessors
    assert "PH-004-interface-contracts" in impl.predecessors


def test_verification_sweep_is_final_phase():
    ids = [p.phase_id for p in PHASES]
    assert ids[-1] == "PH-007-verification-sweep"


def test_phase_map_round_trip():
    for phase in PHASES:
        assert PHASE_MAP[phase.phase_id] is phase
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest .methodology/tests/cli/methodology_runner/test_phases_renumbered.py -v`
Expected: FAIL — phase count is 7, new PH-002 Architecture does not exist, phase IDs still use old numbering.

- [ ] **Step 3: Modify `.methodology/src/cli/methodology_runner/phases.py`**

Edit the file as follows. These are targeted edits — do not rewrite the whole file.

**Edit 3a:** Add new output path constant for the stack manifest. Find the existing output-path constants block (around line 45-51) and add the new stack manifest line after `_OUTPUT_PHASE_1` with a clear comment; shift the others by one and rename them to match the new numbering:

Replace:
```python
_OUTPUT_PHASE_0 = "docs/requirements/requirements-inventory.yaml"
_OUTPUT_PHASE_1 = "docs/features/feature-specification.yaml"
_OUTPUT_PHASE_2 = "docs/design/solution-design.yaml"
_OUTPUT_PHASE_3 = "docs/design/interface-contracts.yaml"
_OUTPUT_PHASE_4 = "docs/simulations/simulation-definitions.yaml"
_OUTPUT_PHASE_5 = "docs/implementation/implementation-plan.yaml"
_OUTPUT_PHASE_6 = "docs/verification/verification-report.yaml"
```

With:
```python
_OUTPUT_PHASE_0 = "docs/requirements/requirements-inventory.yaml"
_OUTPUT_PHASE_1 = "docs/features/feature-specification.yaml"
_OUTPUT_PHASE_2 = "docs/architecture/stack-manifest.yaml"
_OUTPUT_PHASE_3 = "docs/design/solution-design.yaml"
_OUTPUT_PHASE_4 = "docs/design/interface-contracts.yaml"
_OUTPUT_PHASE_5 = "docs/simulations/simulation-definitions.yaml"
_OUTPUT_PHASE_6 = "docs/implementation/implementation-plan.yaml"
_OUTPUT_PHASE_7 = "docs/verification/verification-report.yaml"
```

**Edit 3b:** Add the new `_PHASE_2_ARCHITECTURE` definition. Insert it immediately after the existing `_PHASE_1` block and before the existing `_PHASE_2` (Solution Design) block:

```python
# ---------------------------------------------------------------------------
# Phase 2: Architecture
# ---------------------------------------------------------------------------

_PHASE_2_ARCHITECTURE = PhaseConfig(
    phase_id="PH-002-architecture",
    phase_name="Architecture",
    phase_number=2,
    abbreviation="AR",
    predecessors=["PH-001-feature-specification"],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Feature specification produced by Phase 1",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_0),
            role=InputRole.UPSTREAM_TRACEABILITY,
            format="yaml",
            description=(
                "Requirements inventory for upstream traceability "
                "of expected_expertise choices"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_2,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_2],
    extraction_focus=(
        "Component completeness: every feature from the feature spec\n"
        "must be served by at least one declared component.  Technology\n"
        "coherence: each component has a single named technology and a\n"
        "coherent frameworks list.  Expertise articulation: each\n"
        "component declares a non-empty expected_expertise list of\n"
        "free-text descriptions of the knowledge needed to build it.\n"
        "Integration completeness: every cross-component data flow\n"
        "implied by the features is captured as a named integration\n"
        "point."
    ),
    generation_instructions=(
        "Read the feature specification and produce a stack manifest YAML\n"
        "file.  The file decomposes the enhancement into technology\n"
        "components and declares what knowledge each component needs.\n"
        "\n"
        "components:\n"
        "  - id: CMP-NNN-<slug>\n"
        "    name: descriptive component name\n"
        "    role: one-sentence role summary\n"
        "    technology: e.g. python, typescript, go, rust\n"
        "    runtime: e.g. python3.12, node22, go1.22\n"
        "    frameworks: [name1, name2]\n"
        "    persistence: e.g. postgresql, sqlite, none\n"
        "    expected_expertise:\n"
        "      - \"Free-text description of knowledge this component needs\"\n"
        "      - \"Additional knowledge area\"\n"
        "    features_served: [FT-NNN, ...]\n"
        "\n"
        "integration_points:\n"
        "  - id: IP-NNN\n"
        "    between: [CMP-NNN-a, CMP-NNN-b]\n"
        "    protocol: e.g. HTTP/JSON over TLS\n"
        "    contract_source: where the contract will be defined\n"
        "\n"
        "rationale: |\n"
        "  Prose explanation of the decomposition choices.\n"
        "\n"
        "The expected_expertise field MUST use free-text, human-readable\n"
        "descriptions (not Claude Code skill IDs).  A later Skill-Selector\n"
        "agent maps each description to concrete skills from a catalog;\n"
        "the architect phase is decoupled from the skill catalog so that\n"
        "architecture outputs are portable across skill pack versions."
    ),
    judge_guidance=(
        "Check for these failure modes:\n"
        "\n"
        "1. Feature coverage gaps: every FT-* feature from Phase 1 must\n"
        "   appear in at least one component's features_served list.\n"
        "2. Expertise articulation: every component must have a non-empty\n"
        "   expected_expertise list of free-text descriptions.  Flag any\n"
        "   component whose expertise list looks like concrete skill IDs\n"
        "   (e.g., 'python-backend-impl') rather than descriptions\n"
        "   (e.g., 'Python backend development').\n"
        "3. Orphan integration points: every integration_point must\n"
        "   reference two components both present in the components list.\n"
        "4. Technology coherence: flag components whose frameworks list\n"
        "   includes items from incompatible ecosystems (e.g., python\n"
        "   technology with a react framework entry).\n"
        "5. Missing rationale: the rationale field must explain the\n"
        "   decomposition, not merely restate the component names."
    ),
    artifact_format="yaml",
    artifact_schema_description=(
        "components:\n"
        "  - id: \"CMP-NNN-<slug>\"\n"
        "    name: \"...\"\n"
        "    role: \"...\"\n"
        "    technology: \"...\"\n"
        "    runtime: \"...\"\n"
        "    frameworks: [\"...\"]\n"
        "    persistence: \"...\"\n"
        "    expected_expertise: [\"...\", \"...\"]\n"
        "    features_served: [\"FT-NNN\", ...]\n"
        "\n"
        "integration_points:\n"
        "  - id: \"IP-NNN\"\n"
        "    between: [\"CMP-NNN-a\", \"CMP-NNN-b\"]\n"
        "    protocol: \"...\"\n"
        "    contract_source: \"...\"\n"
        "\n"
        "rationale: |\n"
        "  ..."
    ),
    checklist_examples_good=[
        (
            "Every FT-* feature from Phase 1 appears in the features_served "
            "list of at least one component in the stack manifest"
        ),
        (
            "Every component has a non-empty expected_expertise list where "
            "entries are free-text descriptions of required knowledge, not "
            "concrete Claude Code skill IDs"
        ),
    ],
    checklist_examples_bad=[
        "The architecture is reasonable",
        "Technologies are chosen",
    ],
)
```

**Edit 3c:** Update the existing `_PHASE_2` (Solution Design) definition to change its phase_id, phase_number, predecessors, and input source templates. Find:

```python
_PHASE_2 = PhaseConfig(
    phase_id="PH-002-solution-design",
    phase_name="Solution Design",
    phase_number=2,
    abbreviation="SD",
    predecessors=["PH-001-feature-specification"],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Feature specification produced by Phase 1",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_0),
            role=InputRole.UPSTREAM_TRACEABILITY,
            format="yaml",
            description=(
                "Requirements inventory for upstream traceability "
                "verification"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_2,
```

Replace with:

```python
_PHASE_3 = PhaseConfig(
    phase_id="PH-003-solution-design",
    phase_name="Solution Design",
    phase_number=3,
    abbreviation="SD",
    predecessors=["PH-002-architecture"],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_2),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Stack manifest produced by Phase 2 Architecture",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.UPSTREAM_TRACEABILITY,
            format="yaml",
            description=(
                "Feature specification for upstream traceability "
                "verification"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_3,
```

**Edit 3d:** Rename `_PHASE_3` -> `_PHASE_4` with updated IDs, numbers, predecessors, and template references. Find:

```python
_PHASE_3 = PhaseConfig(
    phase_id="PH-003-interface-contracts",
    phase_name="Interface Contracts",
    phase_number=3,
    abbreviation="CI",
    predecessors=["PH-002-solution-design"],
```

Replace with:

```python
_PHASE_4 = PhaseConfig(
    phase_id="PH-004-interface-contracts",
    phase_name="Interface Contracts",
    phase_number=4,
    abbreviation="CI",
    predecessors=["PH-003-solution-design"],
```

In the same phase block, find its input source templates and update references to `_OUTPUT_PHASE_2` → `_OUTPUT_PHASE_3` (solution design) and `_OUTPUT_PHASE_1` → `_OUTPUT_PHASE_1` (feature spec — unchanged). Find:

```python
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_2),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Solution design with components and interactions from Phase 2",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Feature specification for validating that contracts "
                "cover all acceptance criteria"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_3,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_3],
```

Replace with:

```python
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_3),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Solution design with components and interactions from Phase 3",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Feature specification for validating that contracts "
                "cover all acceptance criteria"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_4,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_4],
```

**Edit 3e:** Rename `_PHASE_4` -> `_PHASE_5` (Intelligent Simulations). Find:

```python
_PHASE_4 = PhaseConfig(
    phase_id="PH-004-intelligent-simulations",
    phase_name="Intelligent Simulations",
    phase_number=4,
    abbreviation="IS",
    predecessors=["PH-003-interface-contracts"],
```

Replace with:

```python
_PHASE_5 = PhaseConfig(
    phase_id="PH-005-intelligent-simulations",
    phase_name="Intelligent Simulations",
    phase_number=5,
    abbreviation="IS",
    predecessors=["PH-004-interface-contracts"],
```

In the same block, update the input templates. Find:

```python
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_3),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Interface contracts from Phase 3",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Feature specification for validating that simulations "
                "cover all acceptance criteria"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_4,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_4],
```

Replace with:

```python
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_4),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Interface contracts from Phase 4",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Feature specification for validating that simulations "
                "cover all acceptance criteria"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_5,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_5],
```

**Edit 3f:** Rename `_PHASE_5` -> `_PHASE_6` (Incremental Implementation, was "Implementation Plan"). Find:

```python
_PHASE_5 = PhaseConfig(
    phase_id="PH-005-implementation-plan",
    phase_name="Implementation Plan",
    phase_number=5,
    abbreviation="II",
    predecessors=[
        "PH-003-interface-contracts",
        "PH-004-intelligent-simulations",
    ],
```

Replace with:

```python
_PHASE_6 = PhaseConfig(
    phase_id="PH-006-incremental-implementation",
    phase_name="Incremental Implementation",
    phase_number=6,
    abbreviation="II",
    predecessors=[
        "PH-004-interface-contracts",
        "PH-005-intelligent-simulations",
    ],
```

In the same block, update the input source templates. The block currently references `_OUTPUT_PHASE_3`, `_OUTPUT_PHASE_4`, `_OUTPUT_PHASE_1`, `_OUTPUT_PHASE_2`. Shift each: `_OUTPUT_PHASE_3` → `_OUTPUT_PHASE_4`, `_OUTPUT_PHASE_4` → `_OUTPUT_PHASE_5`, `_OUTPUT_PHASE_2` → `_OUTPUT_PHASE_3`, `_OUTPUT_PHASE_1` → `_OUTPUT_PHASE_1` (unchanged). Find and replace in this specific block:

- `_tpl(_OUTPUT_PHASE_3)` → `_tpl(_OUTPUT_PHASE_4)` (was interface contracts, still is)
- `_tpl(_OUTPUT_PHASE_4)` → `_tpl(_OUTPUT_PHASE_5)` (was simulation specs, still is)
- `_tpl(_OUTPUT_PHASE_2)` → `_tpl(_OUTPUT_PHASE_3)` (was solution design, still is)

And update the output artifact path and expected files. Find:

```python
    output_artifact_path=_OUTPUT_PHASE_5,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_5],
```

Replace with:

```python
    output_artifact_path=_OUTPUT_PHASE_6,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_6],
```

**Edit 3g:** Rename `_PHASE_6` -> `_PHASE_7` (Verification Sweep). Find:

```python
_PHASE_6 = PhaseConfig(
    phase_id="PH-006-verification-sweep",
    phase_name="Verification Sweep",
    phase_number=6,
    abbreviation="VS",
    predecessors=["PH-005-implementation-plan"],
```

Replace with:

```python
_PHASE_7 = PhaseConfig(
    phase_id="PH-007-verification-sweep",
    phase_name="Verification Sweep",
    phase_number=7,
    abbreviation="VS",
    predecessors=["PH-006-incremental-implementation"],
```

In the same block, update input templates. Find the four `InputSourceTemplate` entries that reference `_OUTPUT_PHASE_1`, `_OUTPUT_PHASE_5`, `_OUTPUT_PHASE_2`, `_OUTPUT_PHASE_0`, and shift the two middle ones:

- `_tpl(_OUTPUT_PHASE_1)` → unchanged (feature spec)
- `_tpl(_OUTPUT_PHASE_5)` → `_tpl(_OUTPUT_PHASE_6)` (implementation plan, renumbered)
- `_tpl(_OUTPUT_PHASE_2)` → `_tpl(_OUTPUT_PHASE_3)` (solution design, renumbered)
- `_tpl(_OUTPUT_PHASE_0)` → unchanged (requirements inventory)

And update the output path. Find:

```python
    output_artifact_path=_OUTPUT_PHASE_6,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_6],
```

Replace with:

```python
    output_artifact_path=_OUTPUT_PHASE_7,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_7],
```

**Edit 3h:** Update the `PHASES` registry at the bottom of the file. Find:

```python
PHASES: list[PhaseConfig] = [
    _PHASE_0,
    _PHASE_1,
    _PHASE_2,
    _PHASE_3,
    _PHASE_4,
    _PHASE_5,
    _PHASE_6,
]
"""All seven phases in execution order (Phase 0 first, Phase 6 last)."""
```

Replace with:

```python
PHASES: list[PhaseConfig] = [
    _PHASE_0,
    _PHASE_1,
    _PHASE_2_ARCHITECTURE,
    _PHASE_3,
    _PHASE_4,
    _PHASE_5,
    _PHASE_6,
    _PHASE_7,
]
"""All eight phases in execution order (Phase 0 first, Phase 7 last)."""
```

**Edit 3i:** Update the module docstring workspace layout comment at the top of phases.py. Find:

```python
Output paths align with CD-002 Section 4.5 workspace layout::

    docs/requirements/requirements-inventory.yaml   # Phase 0
    docs/features/feature-specification.yaml        # Phase 1
    docs/design/solution-design.yaml                # Phase 2
    docs/design/interface-contracts.yaml            # Phase 3
    docs/simulations/simulation-definitions.yaml    # Phase 4
    docs/implementation/implementation-plan.yaml    # Phase 5
    docs/verification/verification-report.yaml      # Phase 6
```

Replace with:

```python
Output paths align with CD-002 Section 4.5 workspace layout::

    docs/requirements/requirements-inventory.yaml   # Phase 0
    docs/features/feature-specification.yaml        # Phase 1
    docs/architecture/stack-manifest.yaml           # Phase 2 (NEW)
    docs/design/solution-design.yaml                # Phase 3
    docs/design/interface-contracts.yaml            # Phase 4
    docs/simulations/simulation-definitions.yaml    # Phase 5
    docs/implementation/implementation-plan.yaml    # Phase 6
    docs/verification/verification-report.yaml      # Phase 7
```

**Edit 3j:** Also update the orchestrator's workspace initialization, which currently creates only the 7 original docs subdirectories. Open `.methodology/src/cli/methodology_runner/orchestrator.py`, find `initialize_workspace`, and find:

```python
    for subdir in (
        "docs/requirements",
        "docs/features",
        "docs/design",
        "docs/simulations",
        "docs/implementation",
        "docs/verification",
    ):
        (workspace / subdir).mkdir(parents=True, exist_ok=True)
```

Replace with:

```python
    for subdir in (
        "docs/requirements",
        "docs/features",
        "docs/architecture",
        "docs/design",
        "docs/simulations",
        "docs/implementation",
        "docs/verification",
    ):
        (workspace / subdir).mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run the renumbering test**

Run: `pytest .methodology/tests/cli/methodology_runner/test_phases_renumbered.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Run all methodology-runner tests and fix regressions**

Run: `pytest .methodology/tests/cli/methodology_runner/ -v`

Expected: several pre-existing tests in `test_cli.py` and `test_prompt_generator.py` will fail because they hardcode old phase IDs (`PH-002-solution-design`, `PH-003-interface-contracts`, `PH-004-intelligent-simulations`, `PH-005-implementation-plan`, `PH-006-verification-sweep`).

**Fix each failure by searching the test file for the old phase ID and updating it:**

- `PH-002-solution-design` → `PH-003-solution-design`
- `PH-003-interface-contracts` → `PH-004-interface-contracts`
- `PH-004-intelligent-simulations` → `PH-005-intelligent-simulations`
- `PH-005-implementation-plan` → `PH-006-incremental-implementation`
- `PH-006-verification-sweep` → `PH-007-verification-sweep`

Use Grep to find all occurrences:

```bash
grep -rn "PH-002-solution-design\|PH-003-interface-contracts\|PH-004-intelligent-simulations\|PH-005-implementation-plan\|PH-006-verification-sweep" tests/ src/
```

Update each to the new ID. Also search for `PH-006` in contexts that expect 7 phases and need updating to `PH-007` (e.g., "last phase", "phase 6 is final", counts of 7 phases becoming 8). Look especially at `.methodology/tests/cli/methodology_runner/test_cli.py::_downstream_phase_ids` tests and any test that iterates `PHASES` and hardcodes phase counts.

Re-run `pytest .methodology/tests/cli/methodology_runner/ -v` after each batch of fixes until all tests pass.

- [ ] **Step 6: Run skill-selector tests (deferred from Task 6)**

Now that `PH-006-incremental-implementation` exists, run:

Run: `pytest .methodology/tests/cli/methodology_runner/test_skill_selector.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 7: Run the full test suite**

Run: `pytest -v`
Expected: all methodology-runner and prompt-runner tests pass.

- [ ] **Step 8: Commit**

```bash
git add .methodology/src/cli/methodology_runner/phases.py .methodology/src/cli/methodology_runner/orchestrator.py .methodology/tests/cli/methodology_runner/test_phases_renumbered.py .methodology/tests/cli/methodology_runner/test_cli.py .methodology/tests/cli/methodology_runner/test_prompt_generator.py .methodology/tests/cli/methodology_runner/test_cross_reference.py
git commit -m "feat(methodology-runner): insert PH-002 Architecture phase and renumber downstream phases"
```

---

## Task 8: Prelude construction

Builds generator and judge prelude text files from a `PhaseSkillManifest`, with two designs: primary (Skill tool invocation) and fallback (inline SKILL.md content).

**Files:**
- Create: `.methodology/src/cli/methodology_runner/prelude.py`
- Create: `.methodology/tests/cli/methodology_runner/test_prelude.py`

- [ ] **Step 1: Write the failing tests**

Create `.methodology/tests/cli/methodology_runner/test_prelude.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest .methodology/tests/cli/methodology_runner/test_prelude.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'methodology_runner.prelude'`

- [ ] **Step 3: Create `.methodology/src/cli/methodology_runner/prelude.py`**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest .methodology/tests/cli/methodology_runner/test_prelude.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add .methodology/src/cli/methodology_runner/prelude.py .methodology/tests/cli/methodology_runner/test_prelude.py
git commit -m "feat(methodology-runner): prelude builder with skill-tool and inline modes"
```

---

## Task 9: Prompt-runner prelude prepending

Modifies `prompt_runner/runner.py` to accept optional generator and judge prelude strings in `RunConfig` and prepend them to every generator and judge message (initial and revise-loop variants).

**Files:**
- Modify: `.prompt-runner/src/cli/prompt_runner/runner.py`
- Modify: `.prompt-runner/tests/cli/prompt_runner/test_runner.py`

- [ ] **Step 1: Write the failing tests**

Append to `.prompt-runner/tests/cli/prompt_runner/test_runner.py`:

```python
# ---------------------------------------------------------------------------
# Prelude prepending (spec section 9)
# ---------------------------------------------------------------------------

from prompt_runner.runner import RunConfig


def test_run_config_defaults_have_none_preludes():
    cfg = RunConfig()
    assert cfg.generator_prelude is None
    assert cfg.judge_prelude is None


def test_build_initial_generator_message_prepends_generator_prelude():
    p = _pair(1, "X", gen="the task body")
    msg = build_initial_generator_message(
        p, [], generator_prelude="# GEN PRELUDE TEXT",
    )
    assert msg.startswith("# GEN PRELUDE TEXT")
    assert "the task body" in msg
    # Horizontal rule or blank line must separate prelude from task
    assert "\n\n" in msg.split("the task body")[0]


def test_build_initial_generator_message_no_prelude_unchanged():
    p = _pair(1, "X", gen="the task body")
    msg_with = build_initial_generator_message(p, [], generator_prelude=None)
    msg_without = build_initial_generator_message(p, [])
    assert msg_with == msg_without


def test_build_initial_judge_message_prepends_judge_prelude():
    p = _pair(1, "X")
    msg = build_initial_judge_message(
        p, "artifact", judge_prelude="# JUD PRELUDE",
    )
    assert msg.startswith("# JUD PRELUDE")


def test_build_revision_generator_message_prepends_prelude():
    msg = build_revision_generator_message(
        "feedback", generator_prelude="# GEN REVISE PRELUDE",
    )
    assert msg.startswith("# GEN REVISE PRELUDE")
    assert "feedback" in msg


def test_build_revision_judge_message_prepends_prelude():
    msg = build_revision_judge_message(
        "revised artifact", judge_prelude="# JUD REVISE PRELUDE",
    )
    assert msg.startswith("# JUD REVISE PRELUDE")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest .prompt-runner/tests/cli/prompt_runner/test_runner.py -v -k "prelude or run_config_defaults"`
Expected: FAIL — `TypeError: build_initial_generator_message() got an unexpected keyword argument 'generator_prelude'` and `AttributeError: 'RunConfig' object has no attribute 'generator_prelude'`.

- [ ] **Step 3: Modify `.prompt-runner/src/cli/prompt_runner/runner.py`**

Find the `RunConfig` dataclass and add the two fields:

```python
@dataclass(frozen=True)
class RunConfig:
    max_iterations: int = MAX_ITERATIONS_DEFAULT
    model: str | None = None
    only: int | None = None
    dry_run: bool = False
```

Replace with:

```python
@dataclass(frozen=True)
class RunConfig:
    max_iterations: int = MAX_ITERATIONS_DEFAULT
    model: str | None = None
    only: int | None = None
    dry_run: bool = False
    generator_prelude: str | None = None
    """Optional text prepended to every generator Claude message in this
    run.  Used by methodology-runner to inject phase-specific skill
    loading instructions.  prompt-runner treats this as opaque text —
    it does not parse, interpret, or modify it."""
    judge_prelude: str | None = None
    """Optional text prepended to every judge Claude message in this
    run.  Symmetric to generator_prelude."""
```

Next, update the four message builders. Find:

```python
def build_initial_generator_message(
    pair: PromptPair, prior_artifacts: list[PriorArtifact]
) -> str:
    sections: list[str] = []

    if prior_artifacts:
```

Replace with:

```python
def build_initial_generator_message(
    pair: PromptPair,
    prior_artifacts: list[PriorArtifact],
    generator_prelude: str | None = None,
) -> str:
    sections: list[str] = []

    if generator_prelude:
        sections.append(generator_prelude)

    if prior_artifacts:
```

Find:

```python
def build_initial_judge_message(
    pair: PromptPair, artifact: str, generator_files: list[Path] | None = None,
) -> str:
    files_section = _format_generator_files_section(generator_files or [])
    return (
        f"{pair.validation_prompt}"
        f"{_HORIZONTAL_RULE}"
```

Replace with:

```python
def build_initial_judge_message(
    pair: PromptPair,
    artifact: str,
    generator_files: list[Path] | None = None,
    judge_prelude: str | None = None,
) -> str:
    files_section = _format_generator_files_section(generator_files or [])
    prelude_block = f"{judge_prelude}{_HORIZONTAL_RULE}" if judge_prelude else ""
    return (
        f"{prelude_block}"
        f"{pair.validation_prompt}"
        f"{_HORIZONTAL_RULE}"
```

Find:

```python
def build_revision_generator_message(judge_output: str) -> str:
    return (
        f"{REVISION_GENERATOR_PREAMBLE}\n\n"
        f"# Judge feedback\n\n{judge_output}"
        f"{_HORIZONTAL_RULE}"
        f"{PROJECT_ORGANISER_INSTRUCTION}"
    )
```

Replace with:

```python
def build_revision_generator_message(
    judge_output: str,
    generator_prelude: str | None = None,
) -> str:
    prelude_block = f"{generator_prelude}{_HORIZONTAL_RULE}" if generator_prelude else ""
    return (
        f"{prelude_block}"
        f"{REVISION_GENERATOR_PREAMBLE}\n\n"
        f"# Judge feedback\n\n{judge_output}"
        f"{_HORIZONTAL_RULE}"
        f"{PROJECT_ORGANISER_INSTRUCTION}"
    )
```

Find:

```python
def build_revision_judge_message(
    new_artifact: str, generator_files: list[Path] | None = None,
) -> str:
    files_section = _format_generator_files_section(generator_files or [])
    return (
        f"{ANTI_ANCHORING_CLAUSE}\n\n"
```

Replace with:

```python
def build_revision_judge_message(
    new_artifact: str,
    generator_files: list[Path] | None = None,
    judge_prelude: str | None = None,
) -> str:
    files_section = _format_generator_files_section(generator_files or [])
    prelude_block = f"{judge_prelude}{_HORIZONTAL_RULE}" if judge_prelude else ""
    return (
        f"{prelude_block}"
        f"{ANTI_ANCHORING_CLAUSE}\n\n"
```

Next, wire the prelude fields from `RunConfig` into the call sites inside `run_prompt`. Find:

```python
    for iteration_number in range(1, config.max_iterations + 1):
        is_first = iteration_number == 1

        gen_msg = (
            build_initial_generator_message(pair, prior_artifacts)
            if is_first
            else build_revision_generator_message(iterations[-1].judge_output)
        )
```

Replace with:

```python
    for iteration_number in range(1, config.max_iterations + 1):
        is_first = iteration_number == 1

        gen_msg = (
            build_initial_generator_message(
                pair, prior_artifacts,
                generator_prelude=config.generator_prelude,
            )
            if is_first
            else build_revision_generator_message(
                iterations[-1].judge_output,
                generator_prelude=config.generator_prelude,
            )
        )
```

Find:

```python
        jud_msg = (
            build_initial_judge_message(pair, gen_response.stdout, files_so_far)
            if is_first
            else build_revision_judge_message(gen_response.stdout, files_so_far)
        )
```

Replace with:

```python
        jud_msg = (
            build_initial_judge_message(
                pair, gen_response.stdout, files_so_far,
                judge_prelude=config.judge_prelude,
            )
            if is_first
            else build_revision_judge_message(
                gen_response.stdout, files_so_far,
                judge_prelude=config.judge_prelude,
            )
        )
```

- [ ] **Step 4: Run the prelude tests**

Run: `pytest .prompt-runner/tests/cli/prompt_runner/test_runner.py -v -k "prelude or run_config_defaults"`
Expected: PASS, 6 tests

- [ ] **Step 5: Run the full prompt-runner test suite to verify no regressions**

Run: `pytest .prompt-runner/tests/cli/prompt_runner/ -v`
Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add .prompt-runner/src/cli/prompt_runner/runner.py .prompt-runner/tests/cli/prompt_runner/test_runner.py
git commit -m "feat(prompt-runner): prepend generator and judge preludes to every claude call"
```

---

## Task 10: Prompt-runner CLI flags for prelude files

Adds `--generator-prelude PATH` and `--judge-prelude PATH` flags to `prompt-runner run`. Reads files at startup, populates `RunConfig` with contents.

**Files:**
- Modify: `.prompt-runner/src/cli/prompt_runner/__main__.py`
- Modify: `.prompt-runner/tests/cli/prompt_runner/test_claude_client.py` (or create a new CLI integration test file)

- [ ] **Step 1: Write the failing test**

Append to `.prompt-runner/tests/cli/prompt_runner/test_claude_client.py` (or preferably create a new `.prompt-runner/tests/cli/prompt_runner/test_cli_prelude.py`):

Create `.prompt-runner/tests/cli/prompt_runner/test_cli_prelude.py`:

```python
"""CLI-level tests for the --generator-prelude and --judge-prelude flags."""
from pathlib import Path

import pytest

from prompt_runner.__main__ import _build_parser


def test_run_parser_accepts_generator_prelude_flag():
    parser = _build_parser()
    args = parser.parse_args([
        "run", "file.md",
        "--generator-prelude", "/tmp/gp.txt",
        "--judge-prelude", "/tmp/jp.txt",
    ])
    assert args.generator_prelude == "/tmp/gp.txt"
    assert args.judge_prelude == "/tmp/jp.txt"


def test_run_parser_prelude_flags_default_to_none():
    parser = _build_parser()
    args = parser.parse_args(["run", "file.md"])
    assert args.generator_prelude is None
    assert args.judge_prelude is None


def test_cmd_run_reads_prelude_files(tmp_path: Path, monkeypatch):
    gp = tmp_path / "gp.txt"
    jp = tmp_path / "jp.txt"
    gp.write_text("GEN-PRELUDE-BODY", encoding="utf-8")
    jp.write_text("JUD-PRELUDE-BODY", encoding="utf-8")

    captured: dict = {}

    def fake_run_pipeline(**kwargs):
        captured.update(kwargs)
        from prompt_runner.runner import PipelineResult
        return PipelineResult(prompt_results=[], halted_early=False, halt_reason=None)

    from prompt_runner import __main__ as m
    monkeypatch.setattr(m, "run_pipeline", fake_run_pipeline)

    # Minimal valid prompt file
    pfile = tmp_path / "pr.md"
    pfile.write_text(
        "# Header\n\n## Prompt 1: X\n\n```\ngen\n```\n\n```\nval\n```\n",
        encoding="utf-8",
    )

    rc = m.main([
        "run", str(pfile),
        "--generator-prelude", str(gp),
        "--judge-prelude", str(jp),
        "--dry-run",
        "--output-dir", str(tmp_path / "out"),
    ])
    assert rc == 0
    cfg = captured["config"]
    assert cfg.generator_prelude == "GEN-PRELUDE-BODY"
    assert cfg.judge_prelude == "JUD-PRELUDE-BODY"


def test_cmd_run_missing_prelude_file_errors(tmp_path: Path, capsys):
    from prompt_runner import __main__ as m
    pfile = tmp_path / "pr.md"
    pfile.write_text(
        "# H\n\n## Prompt 1: X\n\n```\ngen\n```\n\n```\nval\n```\n",
        encoding="utf-8",
    )
    rc = m.main([
        "run", str(pfile),
        "--generator-prelude", str(tmp_path / "nope.txt"),
        "--dry-run",
    ])
    assert rc != 0
    captured = capsys.readouterr()
    assert "prelude" in captured.err.lower() or "not found" in captured.err.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest .prompt-runner/tests/cli/prompt_runner/test_cli_prelude.py -v`
Expected: FAIL — parser does not know the new flags.

- [ ] **Step 3: Modify `.prompt-runner/src/cli/prompt_runner/__main__.py`**

Find the `_cmd_run` function. Just after the existing `config = RunConfig(...)` block, read the prelude files. Find:

```python
def _cmd_run(args: argparse.Namespace) -> int:
    source = Path(args.file)
    try:
        pairs = parse_file(source)
    except ParseError as err:
        _print_error_banner(err.error_id, err.message)
        return 2

    config = RunConfig(
        max_iterations=args.max_iterations,
        model=args.model,
        only=args.only,
        dry_run=args.dry_run,
    )
```

Replace with:

```python
def _cmd_run(args: argparse.Namespace) -> int:
    source = Path(args.file)
    try:
        pairs = parse_file(source)
    except ParseError as err:
        _print_error_banner(err.error_id, err.message)
        return 2

    generator_prelude: str | None = None
    judge_prelude: str | None = None
    if args.generator_prelude:
        gp_path = Path(args.generator_prelude)
        if not gp_path.exists():
            _print_error_banner(
                "R-PRELUDE-NOT-FOUND",
                f"--generator-prelude file not found: {gp_path}",
            )
            return 2
        generator_prelude = gp_path.read_text(encoding="utf-8")
    if args.judge_prelude:
        jp_path = Path(args.judge_prelude)
        if not jp_path.exists():
            _print_error_banner(
                "R-PRELUDE-NOT-FOUND",
                f"--judge-prelude file not found: {jp_path}",
            )
            return 2
        judge_prelude = jp_path.read_text(encoding="utf-8")

    config = RunConfig(
        max_iterations=args.max_iterations,
        model=args.model,
        only=args.only,
        dry_run=args.dry_run,
        generator_prelude=generator_prelude,
        judge_prelude=judge_prelude,
    )
```

Find the `_build_parser` function's `run_cmd.add_argument` block (around line 144-173). After the `--dry-run` flag registration and before `run_cmd.set_defaults(func=_cmd_run)`, add:

```python
    run_cmd.add_argument(
        "--generator-prelude",
        default=None,
        help=(
            "Path to a text file whose contents are prepended to every "
            "generator Claude message in this run.  Used by "
            "methodology-runner to inject phase-specific skill loading "
            "instructions; opaque text from prompt-runner's perspective."
        ),
    )
    run_cmd.add_argument(
        "--judge-prelude",
        default=None,
        help=(
            "Path to a text file whose contents are prepended to every "
            "judge Claude message in this run.  Symmetric to "
            "--generator-prelude."
        ),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest .prompt-runner/tests/cli/prompt_runner/test_cli_prelude.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add .prompt-runner/src/cli/prompt_runner/__main__.py .prompt-runner/tests/cli/prompt_runner/test_cli_prelude.py
git commit -m "feat(prompt-runner): add --generator-prelude and --judge-prelude CLI flags"
```

---

## Task 11: Orchestrator integration — catalog discovery and baseline validation at run start

Calls `build_catalog()` and `load_baseline_config() + validate_against_catalog()` once at the start of every run. Halts with a clear error if either fails.

**Files:**
- Modify: `.methodology/src/cli/methodology_runner/orchestrator.py`
- Create: `.methodology/tests/cli/methodology_runner/test_orchestrator_skills.py`

- [ ] **Step 1: Write the failing test**

Create `.methodology/tests/cli/methodology_runner/test_orchestrator_skills.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest .methodology/tests/cli/methodology_runner/test_orchestrator_skills.py -v`
Expected: FAIL — `build_run_skill_context` does not yet exist in orchestrator.

- [ ] **Step 3: Add `build_run_skill_context` to `.methodology/src/cli/methodology_runner/orchestrator.py`**

Near the top of the file, after the existing imports, add:

```python
from .baseline_config import (
    BaselineConfigError,
    load_baseline_config,
    validate_against_catalog,
)
from .models import BaselineSkillConfig, SkillCatalogEntry
from .skill_catalog import CatalogBuildError, build_catalog
```

Just after the `_git_discard_file` helper (around line 194), add:

```python
# ---------------------------------------------------------------------------
# Run-scoped skill context (CD-002 Section 11 — skill-driven selection)
# ---------------------------------------------------------------------------

@dataclass
class RunSkillContext:
    """Catalog and baseline config loaded once per run.

    Built by ``build_run_skill_context`` before any phase executes.
    Used by the orchestrator to invoke the Skill-Selector and build
    prelude files for each phase.
    """

    catalog: dict[str, SkillCatalogEntry]
    baseline_config: BaselineSkillConfig


BASELINE_SKILLS_PATH = ".methodology/docs/skills-baselines.yaml"
"""Path (relative to repo root or workspace) to the baseline skill config."""


def build_run_skill_context(
    *,
    workspace: Path,
    baseline_path: Path | None = None,
    user_home: Path | None = None,
) -> RunSkillContext:
    """Load the skill catalog and baseline config for a run.

    Runs once at the start of every invocation of ``run_pipeline``
    (before any phase executes).  Raises on any failure so the
    orchestrator halts immediately — per spec failure modes 7 and 9.
    """
    catalog = build_catalog(workspace=workspace, user_home=user_home)

    if baseline_path is None:
        # Prefer a workspace-local copy if one exists, otherwise fall back
        # to the repo-level copy next to the CLI install.
        ws_copy = workspace / BASELINE_SKILLS_PATH
        if ws_copy.exists():
            baseline_path = ws_copy
        else:
            # Repo-root path: same working directory as the CLI invocation.
            baseline_path = Path(BASELINE_SKILLS_PATH)

    baseline_config = load_baseline_config(baseline_path)
    validate_against_catalog(baseline_config, catalog)
    return RunSkillContext(catalog=catalog, baseline_config=baseline_config)
```

Then wire it into `run_pipeline`. Find the section near the top of `run_pipeline`:

```python
    # ---- workspace and state ----
    workspace = initialize_workspace(config)

    state: ProjectState | None = None
    if config.resume:
        state = load_project_state(workspace)
```

Replace with:

```python
    # ---- workspace and state ----
    workspace = initialize_workspace(config)

    # ---- skill catalog + baseline config (run-scoped) ----
    try:
        skill_ctx = build_run_skill_context(workspace=workspace)
    except (CatalogBuildError, BaselineConfigError) as exc:
        return PipelineResult(
            workspace_dir=workspace,
            phase_results=[],
            halted_early=True,
            halt_reason=f"skill context build failed: {exc}",
            end_to_end_result=None,
            wall_time_seconds=time.monotonic() - t0,
        )

    state: ProjectState | None = None
    if config.resume:
        state = load_project_state(workspace)
```

Also, pass `skill_ctx` into `_run_single_phase` (see Task 12 for wiring the rest). Update the call site in the phase loop:

Find:

```python
        # Execute
        result = _run_single_phase(
            phase, state, workspace, config,
            claude_client=claude_client,
            cross_ref_only=cross_ref_only,
        )
```

Replace with:

```python
        # Execute
        result = _run_single_phase(
            phase, state, workspace, config,
            claude_client=claude_client,
            cross_ref_only=cross_ref_only,
            skill_ctx=skill_ctx,
        )
```

And update the signature of `_run_single_phase` to accept `skill_ctx` (the parameter will be consumed fully in Task 12; for now, just accept it as an unused argument so the integration test passes). Find:

```python
def _run_single_phase(
    phase_config: PhaseConfig,
    state: ProjectState,
    workspace: Path,
    config: PipelineConfig,
    claude_client: ClaudeClient | None = None,
    cross_ref_only: bool = False,
) -> PhaseResult:
```

Replace with:

```python
def _run_single_phase(
    phase_config: PhaseConfig,
    state: ProjectState,
    workspace: Path,
    config: PipelineConfig,
    claude_client: ClaudeClient | None = None,
    cross_ref_only: bool = False,
    skill_ctx: RunSkillContext | None = None,
) -> PhaseResult:
```

- [ ] **Step 4: Run the integration test**

Run: `pytest .methodology/tests/cli/methodology_runner/test_orchestrator_skills.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Run all methodology-runner tests**

Run: `pytest .methodology/tests/cli/methodology_runner/ -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add .methodology/src/cli/methodology_runner/orchestrator.py .methodology/tests/cli/methodology_runner/test_orchestrator_skills.py
git commit -m "feat(methodology-runner): load skill catalog and baseline config at run start"
```

---

## Task 12: Orchestrator integration — per-phase selector invocation and prelude wiring

Wires the Skill-Selector into `_run_single_phase`: runs the selector once per phase, writes `phase-NNN-skills.yaml`, builds preludes via `prelude.py`, writes them to disk, and passes their paths to the prompt-runner invocation. The skill manifest is locked across cross-ref retries by default.

**Files:**
- Modify: `.methodology/src/cli/methodology_runner/orchestrator.py`
- Modify: `.methodology/tests/cli/methodology_runner/test_orchestrator_skills.py`

- [ ] **Step 1: Write the failing tests**

Append to `.methodology/tests/cli/methodology_runner/test_orchestrator_skills.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest .methodology/tests/cli/methodology_runner/test_orchestrator_skills.py::test_orchestrator_runs_selector_once_per_phase_and_writes_manifest -v`
Expected: FAIL — `run_selector_and_build_prelude` does not exist.

- [ ] **Step 3: Add `run_selector_and_build_prelude` to `.methodology/src/cli/methodology_runner/orchestrator.py`**

Add the import at the top of the file:

```python
from .prelude import PreludeBuildError, build_prelude
from .skill_selector import SelectorError, SelectorInputs, invoke_skill_selector
```

Add the helper and wrapper dataclass near the `RunSkillContext` definition:

```python
@dataclass
class PhaseSkillArtifacts:
    """Paths and mode returned by ``run_selector_and_build_prelude``.

    The orchestrator uses these to pass prelude file paths into the
    prompt-runner invocation for a phase.
    """

    manifest_path: Path
    generator_prelude_path: Path
    judge_prelude_path: Path
    mode: str


def _phase_skills_filename(phase_config: "PhaseConfig") -> str:
    """Return ``phase-NNN-skills.yaml`` for *phase_config*."""
    return f"phase-{phase_config.phase_number:03d}-skills.yaml"


def _prior_artifact_paths(
    phase_config: "PhaseConfig",
    state: ProjectState,
    workspace: Path,
) -> list[Path]:
    """Return paths to every completed predecessor phase's output artifact."""
    out: list[Path] = []
    for ps in state.phases:
        if ps.status not in _COMPLETED_STATUSES:
            continue
        cfg = PHASE_MAP.get(ps.phase_id)
        if cfg is None:
            continue
        artifact = workspace / cfg.output_artifact_path
        if artifact.exists():
            out.append(artifact)
    return out


def _stack_manifest_path(workspace: Path) -> Path | None:
    """Return path to stack-manifest.yaml if it exists, else None."""
    p = workspace / "docs" / "architecture" / "stack-manifest.yaml"
    return p if p.exists() else None


def run_selector_and_build_prelude(
    *,
    phase_config: "PhaseConfig",
    skill_ctx: RunSkillContext,
    workspace: Path,
    run_dir: Path,
    claude_client: "ClaudeClient",
    model: str | None,
    state: ProjectState | None = None,
    existing_manifest_path: Path | None = None,
) -> PhaseSkillArtifacts:
    """Run the Skill-Selector for one phase and write preludes.

    On success, writes three files to *run_dir*:
    - ``phase-NNN-skills.yaml`` (the selector's locked output)
    - ``generator-prelude.txt``
    - ``judge-prelude.txt``

    If *existing_manifest_path* points at a readable manifest, the
    selector is skipped and that manifest is used as-is.  This is how
    cross-ref retries preserve the locked skill manifest across
    iterations.
    """
    from .models import PhaseSkillManifest

    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / _phase_skills_filename(phase_config)

    if existing_manifest_path is not None and existing_manifest_path.exists():
        raw = existing_manifest_path.read_text(encoding="utf-8")
        manifest = PhaseSkillManifest.from_dict(yaml.safe_load(raw))
    else:
        if state is None:
            prior_paths: list[Path] = []
        else:
            prior_paths = _prior_artifact_paths(phase_config, state, workspace)
        inputs = SelectorInputs(
            phase_config=phase_config,
            catalog=skill_ctx.catalog,
            baseline_config=skill_ctx.baseline_config,
            workspace_dir=workspace,
            prior_artifact_paths=prior_paths,
            stack_manifest_path=_stack_manifest_path(workspace),
        )
        try:
            manifest = invoke_skill_selector(
                inputs, claude_client=claude_client, model=model,
            )
        except SelectorError as exc:
            raise RuntimeError(
                f"Skill-Selector halted for {phase_config.phase_id}: {exc}"
            ) from exc
        manifest_path.write_text(
            yaml.safe_dump(manifest.to_dict(), sort_keys=False),
            encoding="utf-8",
        )

    try:
        prelude_spec = build_prelude(manifest, skill_ctx.catalog)
    except PreludeBuildError as exc:
        raise RuntimeError(
            f"Prelude build failed for {phase_config.phase_id}: {exc}"
        ) from exc

    gen_path = run_dir / "generator-prelude.txt"
    jud_path = run_dir / "judge-prelude.txt"
    gen_path.write_text(prelude_spec.generator_text, encoding="utf-8")
    jud_path.write_text(prelude_spec.judge_text, encoding="utf-8")

    return PhaseSkillArtifacts(
        manifest_path=manifest_path,
        generator_prelude_path=gen_path,
        judge_prelude_path=jud_path,
        mode=prelude_spec.mode,
    )
```

Also add the `import yaml` near the existing `import json` at the top of orchestrator.py (after line 28):

```python
import yaml
```

- [ ] **Step 4: Wire the selector into `_run_single_phase`**

Find the section in `_run_single_phase` that creates `run_dir` and generates the prompt file (around line 640-670):

```python
    run_dir = _phase_run_dir(workspace, phase_config)
    run_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = run_dir / "prompt-file.md"
    cross_ref_path = run_dir / "cross-ref-result.json"
    policy = _effective_escalation_policy(config, phase_config)
    max_retries = config.max_cross_ref_retries
    iteration_count = 0
```

Replace with:

```python
    run_dir = _phase_run_dir(workspace, phase_config)
    run_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = run_dir / "prompt-file.md"
    cross_ref_path = run_dir / "cross-ref-result.json"
    policy = _effective_escalation_policy(config, phase_config)
    max_retries = config.max_cross_ref_retries
    iteration_count = 0

    # Skill-Selector: run once per phase; reuse across cross-ref retries.
    skill_artifacts: PhaseSkillArtifacts | None = None
    if skill_ctx is not None and not cross_ref_only:
        existing = run_dir / _phase_skills_filename(phase_config)
        try:
            skill_artifacts = run_selector_and_build_prelude(
                phase_config=phase_config,
                skill_ctx=skill_ctx,
                workspace=workspace,
                run_dir=run_dir,
                claude_client=claude_client,
                model=config.model,
                state=state,
                existing_manifest_path=existing if existing.exists() else None,
            )
        except RuntimeError as exc:
            ps.status = PhaseStatus.FAILED
            save_project_state(state, workspace)
            return _make_failed_result(
                phase_id, prompt_file, 0,
                time.monotonic() - t0, str(exc),
            )
```

Next, thread the prelude paths into the prompt-runner invocations. Find the existing `_invoke_prompt_runner` signature and call sites. Update `_invoke_prompt_runner_library` first:

Find:

```python
def _invoke_prompt_runner_library(
    md_file: Path,
    workspace: Path,
    run_dir: Path,
    config: PipelineConfig,
    claude_client: ClaudeClient | None = None,
) -> tuple[bool, int, str | None]:
    """Invoke prompt-runner via direct library call (preferred).

    Returns ``(success, total_iteration_count, error_message_or_none)``.
    """
    from prompt_runner.parser import parse_file
    from prompt_runner.runner import RunConfig
    from prompt_runner.runner import run_pipeline as pr_run_pipeline

    if claude_client is None:
        from prompt_runner.claude_client import RealClaudeClient
        claude_client = RealClaudeClient()

    pairs = parse_file(md_file)
    max_iters = config.max_prompt_runner_iterations or 3
    pr_config = RunConfig(max_iterations=max_iters, model=config.model)
```

Replace with:

```python
def _invoke_prompt_runner_library(
    md_file: Path,
    workspace: Path,
    run_dir: Path,
    config: PipelineConfig,
    claude_client: ClaudeClient | None = None,
    generator_prelude_path: Path | None = None,
    judge_prelude_path: Path | None = None,
) -> tuple[bool, int, str | None]:
    """Invoke prompt-runner via direct library call (preferred).

    Returns ``(success, total_iteration_count, error_message_or_none)``.
    """
    from prompt_runner.parser import parse_file
    from prompt_runner.runner import RunConfig
    from prompt_runner.runner import run_pipeline as pr_run_pipeline

    if claude_client is None:
        from prompt_runner.claude_client import RealClaudeClient
        claude_client = RealClaudeClient()

    pairs = parse_file(md_file)
    max_iters = config.max_prompt_runner_iterations or 3

    generator_prelude: str | None = None
    judge_prelude: str | None = None
    if generator_prelude_path is not None:
        generator_prelude = generator_prelude_path.read_text(encoding="utf-8")
    if judge_prelude_path is not None:
        judge_prelude = judge_prelude_path.read_text(encoding="utf-8")

    pr_config = RunConfig(
        max_iterations=max_iters,
        model=config.model,
        generator_prelude=generator_prelude,
        judge_prelude=judge_prelude,
    )
```

Update `_invoke_prompt_runner_subprocess` to append the new flags. Find:

```python
    base_args = [
        "run", str(md_file),
        "--project-dir", str(workspace),
        "--max-iterations", str(max_iters),
    ]
    if config.model:
        base_args.extend(["--model", config.model])
```

Replace with:

```python
    base_args = [
        "run", str(md_file),
        "--project-dir", str(workspace),
        "--max-iterations", str(max_iters),
    ]
    if config.model:
        base_args.extend(["--model", config.model])
    if generator_prelude_path is not None:
        base_args.extend(["--generator-prelude", str(generator_prelude_path)])
    if judge_prelude_path is not None:
        base_args.extend(["--judge-prelude", str(judge_prelude_path)])
```

And update its signature. Find:

```python
def _invoke_prompt_runner_subprocess(
    md_file: Path,
    workspace: Path,
    config: PipelineConfig,
) -> tuple[bool, int, str | None]:
```

Replace with:

```python
def _invoke_prompt_runner_subprocess(
    md_file: Path,
    workspace: Path,
    config: PipelineConfig,
    generator_prelude_path: Path | None = None,
    judge_prelude_path: Path | None = None,
) -> tuple[bool, int, str | None]:
```

Update `_invoke_prompt_runner` (the dispatcher). Find:

```python
def _invoke_prompt_runner(
    md_file: Path,
    workspace: Path,
    run_dir: Path,
    config: PipelineConfig,
    claude_client: ClaudeClient | None = None,
) -> tuple[bool, int, str | None]:
    """Invoke prompt-runner, trying library call first then subprocess.

    Returns ``(success, iteration_count, error_message_or_none)``.
    """
    try:
        return _invoke_prompt_runner_library(
            md_file, workspace, run_dir, config, claude_client,
        )
    except ImportError:
        return _invoke_prompt_runner_subprocess(md_file, workspace, config)
```

Replace with:

```python
def _invoke_prompt_runner(
    md_file: Path,
    workspace: Path,
    run_dir: Path,
    config: PipelineConfig,
    claude_client: ClaudeClient | None = None,
    generator_prelude_path: Path | None = None,
    judge_prelude_path: Path | None = None,
) -> tuple[bool, int, str | None]:
    """Invoke prompt-runner, trying library call first then subprocess.

    Returns ``(success, iteration_count, error_message_or_none)``.
    """
    try:
        return _invoke_prompt_runner_library(
            md_file, workspace, run_dir, config, claude_client,
            generator_prelude_path=generator_prelude_path,
            judge_prelude_path=judge_prelude_path,
        )
    except ImportError:
        return _invoke_prompt_runner_subprocess(
            md_file, workspace, config,
            generator_prelude_path=generator_prelude_path,
            judge_prelude_path=judge_prelude_path,
        )
```

Finally, update the two call sites inside `_run_single_phase` that invoke `_invoke_prompt_runner` to pass the prelude paths. Find the first call:

```python
        # Step 4-5: invoke prompt-runner
        pr_run_dir = run_dir / "prompt-runner-output"
        success, iteration_count, pr_error = _invoke_prompt_runner(
            prompt_file, workspace, pr_run_dir, config, claude_client,
        )
```

Replace with:

```python
        # Step 4-5: invoke prompt-runner
        pr_run_dir = run_dir / "prompt-runner-output"
        gen_prelude_path = (
            skill_artifacts.generator_prelude_path if skill_artifacts else None
        )
        jud_prelude_path = (
            skill_artifacts.judge_prelude_path if skill_artifacts else None
        )
        success, iteration_count, pr_error = _invoke_prompt_runner(
            prompt_file, workspace, pr_run_dir, config, claude_client,
            generator_prelude_path=gen_prelude_path,
            judge_prelude_path=jud_prelude_path,
        )
```

Find the second call (inside the cross-ref retry loop):

```python
        # Re-run prompt-runner on the revised file
        retry_run_dir = run_dir / f"prompt-runner-output-retry-{attempt + 1}"
        success, extra_iters, pr_error = _invoke_prompt_runner(
            prompt_file, workspace, retry_run_dir, config, claude_client,
        )
```

Replace with:

```python
        # Re-run prompt-runner on the revised file — reuse locked prelude paths
        retry_run_dir = run_dir / f"prompt-runner-output-retry-{attempt + 1}"
        success, extra_iters, pr_error = _invoke_prompt_runner(
            prompt_file, workspace, retry_run_dir, config, claude_client,
            generator_prelude_path=gen_prelude_path,
            judge_prelude_path=jud_prelude_path,
        )
```

- [ ] **Step 5: Run the new orchestrator integration test**

Run: `pytest .methodology/tests/cli/methodology_runner/test_orchestrator_skills.py -v`
Expected: all 4 tests pass.

- [ ] **Step 6: Run the full test suite and fix any regressions**

Run: `pytest -v`
Expected: all tests pass. If any test in `test_cli.py` or `test_cross_reference.py` mocks `_invoke_prompt_runner` or `_run_single_phase`, update those mocks to accept the new keyword arguments.

- [ ] **Step 7: Commit**

```bash
git add .methodology/src/cli/methodology_runner/orchestrator.py .methodology/tests/cli/methodology_runner/test_orchestrator_skills.py
git commit -m "feat(methodology-runner): invoke skill selector per phase and wire preludes"
```

---

## Task 13: Cross-ref retry keeps skill manifest locked

Verifies that when a cross-reference retry loop re-generates the prompt file, the skill manifest (and thus the prelude) is reused unchanged. Adds a dedicated test and a `--rerun-selector` CLI flag to `resume` that lets the user override the lock.

**Files:**
- Modify: `.methodology/src/cli/methodology_runner/cli.py`
- Modify: `.methodology/src/cli/methodology_runner/orchestrator.py` (add `rerun_selector` to `PipelineConfig`)
- Create: `.methodology/tests/cli/methodology_runner/test_cross_ref_retry_skills.py`

- [ ] **Step 1: Write the failing test**

Create `.methodology/tests/cli/methodology_runner/test_cross_ref_retry_skills.py`:

```python
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
    for name in ("requirements-extraction", "traceability-discipline", "requirements-quality-review"):
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
overall_rationale: Previous manifest
""",
        encoding="utf-8",
    )

    catalog = _catalog(tmp_path)
    baseline = BaselineSkillConfig(
        version=1,
        phases={
            "PH-000-requirements-inventory": {
                "generator": ["requirements-extraction", "traceability-discipline"],
                "judge": ["requirements-quality-review", "traceability-discipline"],
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
        model="test",
        state=None,
        existing_manifest_path=existing,
    )

    # Selector was NOT called because manifest already exists
    fake_client.call.assert_not_called()
    assert result.generator_prelude_path.exists()
    assert result.judge_prelude_path.exists()
```

- [ ] **Step 2: Run the test to verify it passes**

Since Task 12 already implemented the `existing_manifest_path` skip behavior, this test should pass immediately:

Run: `pytest .methodology/tests/cli/methodology_runner/test_cross_ref_retry_skills.py -v`
Expected: PASS.

- [ ] **Step 3: Add `rerun_selector` field to `PipelineConfig`**

In `.methodology/src/cli/methodology_runner/orchestrator.py`, find:

```python
@dataclass
class PipelineConfig:
    """Configuration for a methodology-runner pipeline execution."""

    requirements_path: Path
    workspace_dir: Path | None = None
    model: str | None = None
    resume: bool = False
    phases_to_run: list[str] | None = None
    max_prompt_runner_iterations: int | None = None
    escalation_policy: EscalationPolicy | None = None
    max_cross_ref_retries: int = MAX_CROSS_REF_RETRIES
```

Replace with:

```python
@dataclass
class PipelineConfig:
    """Configuration for a methodology-runner pipeline execution."""

    requirements_path: Path
    workspace_dir: Path | None = None
    model: str | None = None
    resume: bool = False
    phases_to_run: list[str] | None = None
    max_prompt_runner_iterations: int | None = None
    escalation_policy: EscalationPolicy | None = None
    max_cross_ref_retries: int = MAX_CROSS_REF_RETRIES
    rerun_selector: bool = False
    """On resume, force the Skill-Selector to re-run even if a
    phase-NNN-skills.yaml already exists in the run directory.  By
    default the existing manifest is reused to preserve determinism
    within a single enhancement run."""
```

Next, use `rerun_selector` inside `_run_single_phase` when deciding whether to pass `existing_manifest_path`. Find:

```python
    # Skill-Selector: run once per phase; reuse across cross-ref retries.
    skill_artifacts: PhaseSkillArtifacts | None = None
    if skill_ctx is not None and not cross_ref_only:
        existing = run_dir / _phase_skills_filename(phase_config)
        try:
            skill_artifacts = run_selector_and_build_prelude(
                phase_config=phase_config,
                skill_ctx=skill_ctx,
                workspace=workspace,
                run_dir=run_dir,
                claude_client=claude_client,
                model=config.model,
                state=state,
                existing_manifest_path=existing if existing.exists() else None,
            )
```

Replace with:

```python
    # Skill-Selector: run once per phase; reuse across cross-ref retries.
    # On resume with --rerun-selector, overwrite an existing manifest.
    skill_artifacts: PhaseSkillArtifacts | None = None
    if skill_ctx is not None and not cross_ref_only:
        existing = run_dir / _phase_skills_filename(phase_config)
        reuse_existing = existing.exists() and not config.rerun_selector
        try:
            skill_artifacts = run_selector_and_build_prelude(
                phase_config=phase_config,
                skill_ctx=skill_ctx,
                workspace=workspace,
                run_dir=run_dir,
                claude_client=claude_client,
                model=config.model,
                state=state,
                existing_manifest_path=existing if reuse_existing else None,
            )
```

- [ ] **Step 4: Add `--rerun-selector` flag to `cli.py resume` subcommand**

In `.methodology/src/cli/methodology_runner/cli.py`, find the `resume_cmd` block in `_build_parser`:

```python
    resume_cmd.add_argument(
        "--max-cross-ref-retries",
        type=int,
        default=2,
        help="Max retries for cross-reference verification failures (default: 2).",
    )
    resume_cmd.set_defaults(func=cmd_resume)
```

Replace with:

```python
    resume_cmd.add_argument(
        "--max-cross-ref-retries",
        type=int,
        default=2,
        help="Max retries for cross-reference verification failures (default: 2).",
    )
    resume_cmd.add_argument(
        "--rerun-selector",
        action="store_true",
        help=(
            "On resume, force the Skill-Selector to re-run for the "
            "halted phase even if a phase-NNN-skills.yaml already "
            "exists.  Default: reuse the existing manifest to preserve "
            "deterministic semantics within a run."
        ),
    )
    resume_cmd.set_defaults(func=cmd_resume)
```

Then propagate the flag into `PipelineConfig` inside `cmd_resume`. Find:

```python
    config = PipelineConfig(
        requirements_path=state.requirements_path,
        workspace_dir=workspace,
        model=args.model or state.model,
        resume=True,
        phases_to_run=phases_to_run,
        max_prompt_runner_iterations=args.max_iterations,
        escalation_policy=escalation_policy,
        max_cross_ref_retries=args.max_cross_ref_retries,
    )
```

Replace with:

```python
    config = PipelineConfig(
        requirements_path=state.requirements_path,
        workspace_dir=workspace,
        model=args.model or state.model,
        resume=True,
        phases_to_run=phases_to_run,
        max_prompt_runner_iterations=args.max_iterations,
        escalation_policy=escalation_policy,
        max_cross_ref_retries=args.max_cross_ref_retries,
        rerun_selector=args.rerun_selector,
    )
```

- [ ] **Step 5: Run the test again plus full suite**

Run: `pytest .methodology/tests/cli/methodology_runner/ -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add .methodology/src/cli/methodology_runner/cli.py .methodology/src/cli/methodology_runner/orchestrator.py .methodology/tests/cli/methodology_runner/test_cross_ref_retry_skills.py
git commit -m "feat(methodology-runner): cross-ref retry locks skill manifest; add --rerun-selector"
```

---

## Task 14: Thread phase skill manifest into prompt generator context

Adds an optional `phase_skill_manifest` field to `PromptGenerationContext` and mentions the selected skills in the meta-prompt so the prompt architect knows which skills will be active. This is a lightweight awareness hook — the real skill loading happens via the prelude.

**Files:**
- Modify: `.methodology/src/cli/methodology_runner/prompt_generator.py`
- Modify: `.methodology/src/cli/methodology_runner/orchestrator.py`
- Modify: `.methodology/tests/cli/methodology_runner/test_prompt_generator.py`

- [ ] **Step 1: Write the failing test**

Append to `.methodology/tests/cli/methodology_runner/test_prompt_generator.py`:

```python
def test_meta_prompt_includes_skill_manifest_section_when_provided(tmp_path):
    from methodology_runner.models import (
        PhaseSkillManifest, SkillChoice, SkillSource,
    )
    from methodology_runner.phases import get_phase
    from methodology_runner.prompt_generator import (
        PromptGenerationContext, assemble_meta_prompt,
    )
    manifest = PhaseSkillManifest(
        phase_id="PH-000-requirements-inventory",
        selector_run_at="2026-04-09T10:00:00+00:00",
        selector_model="test",
        generator_skills=[
            SkillChoice(
                id="requirements-extraction",
                source=SkillSource.BASELINE,
                rationale="Baseline",
            ),
        ],
        judge_skills=[],
        overall_rationale="Test",
    )
    ctx = PromptGenerationContext(
        phase_config=get_phase("PH-000-requirements-inventory"),
        workspace_dir=tmp_path,
        phase_skill_manifest=manifest,
    )
    prompt = assemble_meta_prompt(ctx)
    assert "requirements-extraction" in prompt
    assert "generator_skills" in prompt.lower() or "generator skill" in prompt.lower()


def test_meta_prompt_without_skill_manifest_omits_section(tmp_path):
    from methodology_runner.phases import get_phase
    from methodology_runner.prompt_generator import (
        PromptGenerationContext, assemble_meta_prompt,
    )
    ctx = PromptGenerationContext(
        phase_config=get_phase("PH-000-requirements-inventory"),
        workspace_dir=tmp_path,
    )
    prompt = assemble_meta_prompt(ctx)
    # Should not raise; should not contain a skill manifest header
    assert "SKILL MANIFEST" not in prompt
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest .methodology/tests/cli/methodology_runner/test_prompt_generator.py::test_meta_prompt_includes_skill_manifest_section_when_provided .methodology/tests/cli/methodology_runner/test_prompt_generator.py::test_meta_prompt_without_skill_manifest_omits_section -v`
Expected: FAIL — `PromptGenerationContext` has no `phase_skill_manifest` field.

- [ ] **Step 3: Update `PromptGenerationContext`**

In `.methodology/src/cli/methodology_runner/prompt_generator.py`, find:

```python
@dataclass(frozen=True)
class PromptGenerationContext:
    """Everything needed to generate a prompt-runner input file."""

    phase_config: PhaseConfig
    workspace_dir: Path
    completed_phases: list[PhaseState] = field(default_factory=list)
    cross_ref_feedback: CrossReferenceResult | None = None
```

Replace with:

```python
@dataclass(frozen=True)
class PromptGenerationContext:
    """Everything needed to generate a prompt-runner input file."""

    phase_config: PhaseConfig
    workspace_dir: Path
    completed_phases: list[PhaseState] = field(default_factory=list)
    cross_ref_feedback: CrossReferenceResult | None = None
    phase_skill_manifest: "PhaseSkillManifest | None" = None
```

Add the forward reference import at the top of the file (next to the other models imports):

```python
from .models import (
    CrossReferenceResult,
    InputRole,
    PhaseConfig,
    PhaseSkillManifest,
    PhaseState,
)
```

- [ ] **Step 4: Update `assemble_meta_prompt` to include the skill manifest block**

Find the `assemble_meta_prompt` function. Locate the section where it substitutes into `META_PROMPT_TEMPLATE` and add a new block before the final template.format() call. Find (near the top of `assemble_meta_prompt`):

```python
def assemble_meta_prompt(context: PromptGenerationContext) -> str:
```

After the existing context processing and before the final return statement, add logic to format a skill manifest section. Specifically, find the return statement that calls `.format(...)` on the template, and replace with a version that prepends a skill manifest block when one is provided. As a minimally invasive change, find the line in `assemble_meta_prompt` that returns the formatted template (search for `META_PROMPT_TEMPLATE.format` or `return template.format` — look for whatever pattern is used) and wrap the return:

```python
    meta = META_PROMPT_TEMPLATE.format(
        # ... existing keyword args unchanged ...
    )
    if context.phase_skill_manifest is not None:
        skill_block = _format_skill_manifest_block(context.phase_skill_manifest)
        meta = f"{skill_block}\n\n{meta}"
    return meta
```

Add the helper `_format_skill_manifest_block` near the other private helpers:

```python
def _format_skill_manifest_block(manifest: PhaseSkillManifest) -> str:
    """Return a short human-readable summary of the phase's skill manifest.

    This is prepended to the meta-prompt so the prompt architect is
    aware of which skills will be active for the generator and judge
    when the prompt-runner file executes.  Note: the actual skill
    loading happens via the prelude, not the meta-prompt — this
    section is purely informational for the architect.
    """
    lines = [
        "## PHASE SKILL MANIFEST",
        "",
        f"The Skill-Selector has chosen the following skills for "
        f"{manifest.phase_id}.",
        "Generator calls will load these via a prelude; judge calls "
        "load their own set.",
        "",
        "Generator skills:",
    ]
    if manifest.generator_skills:
        for sc in manifest.generator_skills:
            lines.append(f"  - {sc.id} ({sc.source.value})")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("Judge skills:")
    if manifest.judge_skills:
        for sc in manifest.judge_skills:
            lines.append(f"  - {sc.id} ({sc.source.value})")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append(f"Rationale: {manifest.overall_rationale}")
    lines.append("")
    lines.append("---")
    return "\n".join(lines)
```

- [ ] **Step 5: Thread the manifest from orchestrator into `PromptGenerationContext`**

In `.methodology/src/cli/methodology_runner/orchestrator.py`, find the two places where `PromptGenerationContext` is constructed inside `_run_single_phase` — once for the initial generation and once for the cross-ref retry re-generation. Both look like:

```python
        completed_states = _get_completed_phase_states(state)
        ctx = PromptGenerationContext(
            phase_config=phase_config,
            workspace_dir=workspace,
            completed_phases=completed_states,
        )
```

And (for the retry):

```python
        feedback = _reconstruct_cross_ref_feedback(cross_ref_result)
        completed_states = _get_completed_phase_states(state)
        ctx = PromptGenerationContext(
            phase_config=phase_config,
            workspace_dir=workspace,
            completed_phases=completed_states,
            cross_ref_feedback=feedback,
        )
```

Add the `phase_skill_manifest` to both. We need to load it from the manifest file on disk:

Add this helper to orchestrator.py near the other helpers:

```python
def _load_phase_skill_manifest(
    run_dir: Path, phase_config: "PhaseConfig",
) -> "PhaseSkillManifest | None":
    """Load ``phase-NNN-skills.yaml`` from *run_dir* if present."""
    from .models import PhaseSkillManifest
    path = run_dir / _phase_skills_filename(phase_config)
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PhaseSkillManifest.from_dict(raw)
```

Then update the two context constructions:

```python
        completed_states = _get_completed_phase_states(state)
        ctx = PromptGenerationContext(
            phase_config=phase_config,
            workspace_dir=workspace,
            completed_phases=completed_states,
            phase_skill_manifest=_load_phase_skill_manifest(run_dir, phase_config),
        )
```

And the retry version:

```python
        feedback = _reconstruct_cross_ref_feedback(cross_ref_result)
        completed_states = _get_completed_phase_states(state)
        ctx = PromptGenerationContext(
            phase_config=phase_config,
            workspace_dir=workspace,
            completed_phases=completed_states,
            cross_ref_feedback=feedback,
            phase_skill_manifest=_load_phase_skill_manifest(run_dir, phase_config),
        )
```

- [ ] **Step 6: Run the tests**

Run: `pytest .methodology/tests/cli/methodology_runner/test_prompt_generator.py -v`
Expected: PASS.

Run: `pytest .methodology/tests/cli/methodology_runner/ -v`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add .methodology/src/cli/methodology_runner/prompt_generator.py .methodology/src/cli/methodology_runner/orchestrator.py .methodology/tests/cli/methodology_runner/test_prompt_generator.py
git commit -m "feat(methodology-runner): inject phase skill manifest into meta-prompt context"
```

---

## Task 15: Update `.methodology/docs/M-002-phase-definitions.md`

Inserts the new PH-002 Architecture phase as a YAML block and renumbers the existing PH-002..PH-006 to PH-003..PH-007 throughout the file. Updates the dependency-graph diagram at the top of the file and the summary table at the end.

**Files:**
- Modify: `.methodology/docs/M-002-phase-definitions.md`

This is a large content edit, not code. No automated test; the verification is manual review plus a grep for any remaining stale phase IDs.

- [ ] **Step 1: Update the dependency-graph diagram at the top of the file (lines 11-22)**

Find:

```
# Dependency graph:
#
#   PH-000 (Requirements Inventory)
#     └─► PH-001 (Feature Specification)
#           └─► PH-002 (Solution Design)
#                 └─► PH-003 (Contract-First Interface Definitions)
#                       └─► PH-004 (Intelligent Simulations)
#                       │     │
#                       ▼     ▼
#                     PH-005 (Incremental Implementation) ◄── PH-001
#                       └─► PH-006 (Verification Sweep) ◄── PH-000, PH-001
#
```

Replace with:

```
# Dependency graph:
#
#   PH-000 (Requirements Inventory)
#     └─► PH-001 (Feature Specification)
#           └─► PH-002 (Architecture)
#                 └─► PH-003 (Solution Design)
#                       └─► PH-004 (Contract-First Interface Definitions)
#                             └─► PH-005 (Intelligent Simulations)
#                             │     │
#                             ▼     ▼
#                           PH-006 (Incremental Implementation) ◄── PH-001
#                             └─► PH-007 (Verification Sweep) ◄── PH-000, PH-001
#
```

- [ ] **Step 2: Insert new PH-002 Architecture phase YAML**

Find the "PHASE 2: SOLUTION DESIGN" banner in the file (around line 944) and insert a new PH-002 Architecture block before it. The new block follows the same Phase Processing Unit schema as existing phases. Use this content:

```yaml


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: ARCHITECTURE
# ═══════════════════════════════════════════════════════════════════════════════
#
# Purpose: Decompose the enhancement into technology components, declaring for
# each its role, technology stack, candidate frameworks, and the expertise
# required to build it (as free-text descriptions, not concrete skill IDs).
#
# This phase does not design the components in detail (that is Solution
# Design's job in PH-003).  It produces the bridge artifact that turns a
# feature specification into a technology-aware plan without coupling itself
# to any specific skill catalog.
#
# The critical discipline here is decoupling: expected_expertise uses
# human-readable free-text descriptions.  A downstream Skill-Selector agent
# maps each description to concrete Claude Code skills at run time.  The
# architect does not need to know which skills are installed.
# ═══════════════════════════════════════════════════════════════════════════════

phase_2_architecture:

  phase_processing_unit:

    phase_id: "PH-002-architecture"
    phase_name: "Architecture"
    version: "1.0.0"

    input_sources:
      artifacts:
        - ref: "{workspace}/docs/features/feature-specification.yaml"
          role: "primary"
          format: "yaml"
          description: >
            Feature specification produced by Phase 1.  Every feature must
            be served by at least one component declared in the stack
            manifest.
          content_hash: ""
          version: ""

        - ref: "{workspace}/docs/requirements/requirements-inventory.yaml"
          role: "upstream_traceability"
          format: "yaml"
          description: >
            Requirements inventory for upstream traceability of the
            technology decomposition.
          content_hash: ""
          version: ""

      external_references: []

    phase_output:
      primary_artifact:
        path: "{workspace}/docs/architecture/stack-manifest.yaml"
        format: "yaml"
        description: >
          The stack manifest declares the components, their technology
          stacks, frameworks, and expected expertise, plus the integration
          points between them.

      schema: |
        components:
          - id: CMP-NNN-<slug>
            name: ...
            role: ...
            technology: python | typescript | go | rust | ...
            runtime: ...
            frameworks: [...]
            persistence: ...
            expected_expertise:
              - "Free-text description of required knowledge"
              - ...
            features_served: [FT-NNN, ...]

        integration_points:
          - id: IP-NNN
            between: [CMP-NNN-a, CMP-NNN-b]
            protocol: ...
            contract_source: ...

        rationale: |
          Prose explanation of the decomposition choices.

    checklist_extraction:

      extractor_agent: "checklist-extractor"

      extraction_focus: |
        Every feature must be served by at least one component.  Every
        component must declare a non-empty expected_expertise list of
        free-text descriptions.  Every integration point must reference
        two components in the manifest.  The decomposition must be
        traceable to the features and requirements that motivated it.

    generation:
      generator_agent: "artifact-generator"

    judging:
      judge_agent: "artifact-judge"

      judge_guidance: |
        1. Feature coverage gaps: every FT-* must appear in at least one
           component's features_served list.
        2. Expertise articulation: every component must have a non-empty
           expected_expertise list of free-text descriptions.  Flag any
           component whose expertise list looks like concrete skill IDs
           (e.g., 'python-backend-impl') rather than descriptions
           (e.g., 'Python backend development').
        3. Orphan integration points: every integration_point must
           reference two components present in the components list.
        4. Technology coherence: flag components whose frameworks list
           includes items from incompatible ecosystems.
        5. Missing rationale: the rationale field must explain the
           decomposition, not merely restate the component names.

    escalation_policy: "halt"


```

- [ ] **Step 3: Renumber all downstream phase banners and phase_id values**

Use the Edit tool with `replace_all: true` for each of the following substitutions in `.methodology/docs/M-002-phase-definitions.md`. Run them one at a time in this order:

1. `"PH-002-solution-design"` → `"PH-003-solution-design"` (replace_all)
2. `"PH-003-contract-first-interfaces"` → `"PH-004-contract-first-interfaces"` (replace_all)
3. `"PH-004-intelligent-simulations"` → `"PH-005-intelligent-simulations"` (replace_all)
4. `"PH-005-incremental-implementation"` → `"PH-006-incremental-implementation"` (replace_all)
5. `"PH-006-verification-sweep"` → `"PH-007-verification-sweep"` (replace_all)

Then update the banner headers:

6. `PHASE 2: SOLUTION DESIGN` → `PHASE 3: SOLUTION DESIGN` (replace_all)
7. `PHASE 3: CONTRACT-FIRST INTERFACES` → `PHASE 4: CONTRACT-FIRST INTERFACES` (replace_all)
8. `PHASE 4: INTELLIGENT SIMULATIONS` → `PHASE 5: INTELLIGENT SIMULATIONS` (replace_all)
9. `PHASE 5: INCREMENTAL IMPLEMENTATION` → `PHASE 6: INCREMENTAL IMPLEMENTATION` (replace_all)
10. `PHASE 6: VERIFICATION SWEEP` → `PHASE 7: VERIFICATION SWEEP` (replace_all)

Then update the top-level dict keys (e.g., `phase_2_solution_design:`):

11. `phase_2_solution_design:` → `phase_3_solution_design:`
12. `phase_3_contract_first_interfaces:` → `phase_4_contract_first_interfaces:`
13. `phase_4_intelligent_simulations:` → `phase_5_intelligent_simulations:`
14. `phase_5_incremental_implementation:` → `phase_6_incremental_implementation:`
15. `phase_6_verification_sweep:` → `phase_7_verification_sweep:`

- [ ] **Step 4: Update the summary table at the bottom of the file**

Find (around lines 3495-3502):

```
# PH-002   Feature specification            Solution design (YAML)          CMP-* ← FT-*, INT-* ← FT-*
# PH-003   Solution design                  Interface contracts (YAML)      CTR-* ← INT-*, TYP-* shared
# PH-004   Interface contracts              Simulation definitions (YAML)   SIM-* ← CTR-*, SCN-* ← AC-*
# PH-005   Contracts + simulations + feats  Implementation plan (YAML)      UT-* ← AC-*, IT-* ← SCN-*
# PH-006   Features + inventory + system    Verification report (YAML)      E2E-* ← AC-* ← FT-* ← RI-*
```

Replace with:

```
# PH-002   Feature specification            Stack manifest (YAML)           CMP-* ← FT-*, expertise free-text
# PH-003   Stack manifest                   Solution design (YAML)          INT-* ← CMP-*, design detail
# PH-004   Solution design                  Interface contracts (YAML)      CTR-* ← INT-*, TYP-* shared
# PH-005   Interface contracts              Simulation definitions (YAML)   SIM-* ← CTR-*, SCN-* ← AC-*
# PH-006   Contracts + simulations + feats  Implementation plan (YAML)      UT-* ← AC-*, IT-* ← SCN-*
# PH-007   Features + inventory + system    Verification report (YAML)      E2E-* ← AC-* ← FT-* ← RI-*
```

- [ ] **Step 5: Also update the top comment line that says "PH-000 through PH-006"**

Find:

```
# This document defines seven phases (PH-000 through PH-006) that compose the
```

Replace with:

```
# This document defines eight phases (PH-000 through PH-007) that compose the
```

- [ ] **Step 6: Verify there are no leftover stale phase IDs**

Run:

```bash
grep -nE 'PH-00[0-7]' .methodology/docs/M-002-phase-definitions.md
```

Expected: only the new IDs `PH-000` through `PH-007` appear; no `PH-006-incremental-implementation` paired with number 5, no `PH-002-solution-design`, etc. Visually scan the output to confirm the IDs and surrounding phase numbers are internally consistent.

- [ ] **Step 7: Commit**

```bash
git add .methodology/docs/M-002-phase-definitions.md
git commit -m "docs(methodology): insert PH-002 Architecture phase and renumber downstream phases"
```

---

## Task 16: Update `.methodology/docs/design/components/CD-002-methodology-runner.md`

Adds a new section on skill-driven per-phase selection and updates the per-phase flow diagram to include the Skill-Selector step and cross-ref retry loop. Documents the dual prelude modes and the SKILL_LOADING_MODE switch.

**Files:**
- Modify: `.methodology/docs/design/components/CD-002-methodology-runner.md`

- [ ] **Step 1: Add a new section 11 on skill-driven selection**

Append the following section to the end of the file (before any trailing blank lines):

```markdown

---

## 11. Skill-driven per-phase selection

This section documents how methodology-runner specializes each phase's
knowledge for the technology stack being developed, without coupling
the methodology text itself to any specific language or framework.

### 11.1 Skill catalog discovery

At the start of every `run_pipeline` invocation (before any phase
executes), the orchestrator calls `skill_catalog.build_catalog()` to
walk three locations in priority order:

1. `<workspace>/.claude/skills/**/SKILL.md` — project-local skills
2. `~/.claude/skills/**/SKILL.md` — user-global skills
3. `~/.claude/plugins/*/skills/**/SKILL.md` — plugin-installed skills

Each SKILL.md is parsed for YAML frontmatter (`name` and
`description`) and registered in an in-memory catalog keyed by skill
ID.  Higher-priority locations shadow lower ones; overrides are
logged.

If the resulting catalog is empty, the orchestrator halts with an
actionable error before any phase runs (failure mode 7).

### 11.2 Baseline skills configuration

The file `.methodology/docs/skills-baselines.yaml` declares the
non-negotiable skills per phase.  It is read at run start by
`baseline_config.load_baseline_config()` and validated against the
catalog by `baseline_config.validate_against_catalog()`.  Any baseline
skill ID that is not in the catalog is a critical halt (failure mode
9).

This file is intentionally data, not code: adding or removing a
baseline skill is a one-line edit and takes effect on the next run.

### 11.3 Skill-Selector agent (per-phase)

Before each phase's meta-prompt runs, the orchestrator invokes the
Skill-Selector via `skill_selector.invoke_skill_selector()`.  The
selector is a single Claude call with four inputs:

- The phase definition (from `PhaseConfig`)
- The baseline skills for this phase (from `skills-baselines.yaml`)
- The compact catalog (ID + description only, not full SKILL.md bodies)
- Prior phase artifacts (small ones in full; large ones summarized
  and cached by `artifact_summarizer.ArtifactSummaryProvider`)
- The stack manifest, if it exists (from PH-002 Architecture)

The selector emits a YAML document which is parsed, validated
(failure modes 1-6), and persisted to the phase's run directory as
`phase-NNN-skills.yaml`.  The file is committed to the workspace git
repo along with the phase's output artifact.

**Locking:** the manifest is locked across cross-reference retries
within a single run.  A retry regenerates the prompt-runner .md file
but reuses the locked skill manifest and prelude.  On `resume`, the
user can pass `--rerun-selector` to force a new selector invocation
for the halted phase.

### 11.4 Prelude construction (dual mode)

`prelude.build_prelude()` converts a `PhaseSkillManifest` into two
text blocks (generator and judge) using one of two designs:

- **`skill-tool` mode** (primary): the prelude instructs the agent to
  invoke the Claude Code Skill tool by name for each selected skill.
  The agent loads SKILL.md content just-in-time.  Depends on the
  Skill tool being available inside nested `claude --print`
  subprocess calls.
- **`inline` mode** (fallback): the prelude embeds the full SKILL.md
  body (minus frontmatter) of every selected skill, delimited by
  section markers.  Larger preludes but zero dependency on the Skill
  tool.

The default mode is set by `constants.SKILL_LOADING_MODE`.  Phase 0
validation (see `phase_0_validation.py`) determines which mode works
in the deployment environment and records its verdict in
`runs/phase-0-validation/validation-report.md`.

Both prelude texts are written to the phase's run directory as
`generator-prelude.txt` and `judge-prelude.txt` and passed to
prompt-runner via two new CLI flags.

### 11.5 Prompt-runner prelude flags

`prompt-runner run` accepts two new optional flags:

- `--generator-prelude PATH` — file whose contents are prepended to
  every generator Claude message in the run
- `--judge-prelude PATH` — symmetric for judge messages

Prelude content is read once at startup and cached for the duration.
prompt-runner does not parse, interpret, or modify the content; it
treats it as opaque text so the tool remains skill-agnostic and
usable outside methodology-runner.

The orchestrator passes prelude file paths into `_invoke_prompt_runner`,
which threads them into the library call via `RunConfig.generator_prelude`
and `RunConfig.judge_prelude`, or into the subprocess call via the CLI
flags.

### 11.6 Per-phase execution flow

```
┌──────────────────────────────────────────────────────────────────┐
│ _run_single_phase (per-phase)                                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Mark phase RUNNING                                           │
│  2. Invoke Skill-Selector                                        │
│       - skip if phase-NNN-skills.yaml exists and not             │
│         --rerun-selector                                         │
│       - validate catalog membership + baseline coverage          │
│       - any failure = critical halt                              │
│  3. Build generator-prelude.txt and judge-prelude.txt            │
│  4. Generate phase-NNN-prompts.md via existing meta-prompt       │
│                                                                  │
│  ┌─ cross-reference retry loop (max N=2) ──────────────────┐     │
│  │                                                         │     │
│  │  5. Invoke prompt-runner with prelude file paths        │     │
│  │  6. Cross-reference verification                        │     │
│  │     - pass  → exit loop, go to step 7                   │     │
│  │     - fail  → if retries remaining:                     │     │
│  │                 re-generate prompt file with cross-ref  │     │
│  │                 feedback; skill manifest stays LOCKED   │     │
│  │                 back to step 5                          │     │
│  │               if retries exhausted:                     │     │
│  │                 critical halt (failure mode 11)         │     │
│  │                                                         │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  7. Commit all phase artifacts including phase-NNN-skills.yaml,  │
│     generator-prelude.txt, judge-prelude.txt                     │
│  8. Mark phase COMPLETED                                         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 11.7 Phase 0 validation (release gate)

Before first use of `skill-tool` mode, Phase 0 validation must be
run: `python -m methodology_runner.phase_0_validation`.

The script creates a temporary test skill under `~/.claude/skills/`,
invokes `claude --print` with an instruction to load it via the
Skill tool, and inspects the response for a distinctive sentinel
string.  If found, `skill-tool` mode is verified and the report is
committed as a release gate.  If not, the fallback `inline` mode is
used.

Failure mode 14: methodology-runner refuses to start in `skill-tool`
mode unless `runs/phase-0-validation/validation-report.md` exists and
records a successful outcome.
```

- [ ] **Step 2: Commit**

```bash
git add .methodology/docs/design/components/CD-002-methodology-runner.md
git commit -m "docs(design): document skill-driven per-phase selection in CD-002"
```

---

## Task 17: Smoke test — full pipeline with mock catalog

End-to-end test that drives the orchestrator through a minimal pipeline run using a scripted `ClaudeClient` and a mock catalog. Verifies that all the pieces wire together.

**Files:**
- Create: `.methodology/tests/cli/methodology_runner/test_smoke_skill_driven.py`

- [ ] **Step 1: Write the smoke test**

Create `.methodology/tests/cli/methodology_runner/test_smoke_skill_driven.py`:

```python
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
```

- [ ] **Step 2: Run the smoke test**

Run: `pytest .methodology/tests/cli/methodology_runner/test_smoke_skill_driven.py -v`
Expected: PASS.

If the test fails because of scripted-response count mismatches (the orchestrator may call Claude more or fewer times than the test expects), add diagnostic print of `client.received` and adjust the scripted responses list until the test passes. The goal is not perfect response counting; the goal is that the phase completes without a halt and writes the expected files.

- [ ] **Step 3: Run the full test suite one last time**

Run: `pytest -v`
Expected: all tests across methodology-runner and prompt-runner pass.

- [ ] **Step 4: Commit**

```bash
git add .methodology/tests/cli/methodology_runner/test_smoke_skill_driven.py
git commit -m "test(methodology-runner): end-to-end smoke test with mocked catalog"
```

---

## Task 18: Verify `pyproject.toml` declares `pyyaml`

`baseline_config.py` and `orchestrator.py` now import `yaml` directly. Historically it was used only by tests or indirectly; ensure it is declared as a runtime dependency.

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Check whether yaml is already a runtime dep**

Run: `grep -n pyyaml pyproject.toml || echo not declared`
Expected: `not declared` or a dev-only declaration.

- [ ] **Step 2: Add `pyyaml` to `[project].dependencies`**

Open `pyproject.toml`. Find:

```toml
[project]
name = "prompt-runner"
version = "0.1.0"
description = "Run prompt/validator pairs from a markdown file through the Claude CLI with a revision loop"
requires-python = ">=3.11"
```

Replace with:

```toml
[project]
name = "prompt-runner"
version = "0.1.0"
description = "Run prompt/validator pairs from a markdown file through the Claude CLI with a revision loop"
requires-python = ">=3.11"
dependencies = [
    "pyyaml>=6.0",
]
```

- [ ] **Step 3: Re-install the project to ensure the dep is present**

Run: `pip install -e . --quiet`
Expected: success; `pyyaml` installed if it was not already.

- [ ] **Step 4: Re-run the full test suite**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "chore(deps): declare pyyaml as a runtime dependency"
```

---

## Follow-up plans

Two additional plans should be written and executed to complete the full spec:

1. **`docs/superpowers/plans/2026-04-10-methodology-runner-skills-pack.md`** — authoring the 18 v1 SKILL.md files listed in spec section 11 plus the plugin manifest and README. This is content work that does not depend on the Python implementation and can proceed in parallel once the Python scaffolding is stable. Each SKILL.md needs 100-300 lines of real content: conventions, examples, anti-patterns. Suggested structure: one task per skill, grouped by methodology phase, with the task output being a reviewed SKILL.md file.

2. **`docs/superpowers/plans/2026-04-11-methodology-runner-distribution.md`** — PyPI publishing for `methodology-runner`, Claude Code plugin library publishing for `methodology-runner-skills`, release notes, and version pinning conventions. Blocked on both the Python plan (this one) and the skill-pack plan being complete and green.

Neither follow-up plan blocks this plan's execution. This plan produces a fully working skill-driven methodology-runner that can be tested against a hand-authored skill pack as soon as the first few SKILL.md files exist.

---

## Self-review checklist (for the plan author)

Covered spec sections:

- Section 4 "Design overview" — captured in Tasks 11–14 orchestrator changes and in the CD-002 update in Task 16.
- Section 5 "New methodology phase PH-002 Architecture" — Task 7 (phases.py) and Task 15 (M-002).
- Section 6 "Skill-Selector agent" — Task 6.
- Section 7 "Skill catalog discovery" — Task 3.
- Section 8 "Baseline skills configuration" — Task 4.
- Section 8A "Context budget management" — Tasks 1 (constants), 5 (summarizer), 6 (selector two-pass), 8 (MAX_SKILLS_PER_PHASE cap enforced in prelude resolver).
- Section 9 "Prompt-runner prelude feature" — Tasks 8 (builder), 9 (runner), 10 (CLI).
- Section 10 "Generic role preservation" — no code change (by design).
- Section 11 "Distribution and packaging" — deferred to follow-up plan.
- Section 12 "Error handling" — failure modes 1-9, 11-14 handled by Tasks 3, 4, 6, 11, 12, 13, and phase_0_validation. Failure mode 10 (duplicate skill ID) is logged by `skill_catalog.build_catalog`.
- Section 13 "Data schemas summary" — Task 2 dataclasses.
- Section 14 "Implementation impact" — Tasks 0, 1-17, plus the deferred skill-pack and distribution plans.

Placeholder scan: no "TBD", no "implement later", no "similar to Task N" without code; every code step contains complete code or a complete edit instruction.

Type consistency: `PhaseSkillManifest`, `SkillChoice`, `SkillCatalogEntry`, `BaselineSkillConfig`, `PreludeSpec`, `RunSkillContext`, `PhaseSkillArtifacts`, `SelectorInputs` are introduced in Tasks 2, 6, 11, 12 and used consistently throughout later tasks. `build_prelude(manifest, catalog, mode=...)` signature is consistent between Task 8 definition and Task 12 call site. `run_selector_and_build_prelude` signature is consistent between Task 12 definition and Task 13 test.

Known risks during execution:

- Task 7's renumbering will ripple through `test_cli.py`, `test_cross_reference.py`, and `test_prompt_generator.py`. Budget enough effort for fixing those mocks. Steps 5-7 of Task 7 describe the remediation loop.
- Task 12 modifies `_invoke_prompt_runner` and its two variants; any existing test that mocks those functions will need its mock signature updated.
- Task 15 is a large manual edit. Grep for stale IDs at the end (Step 6) to catch missed replacements.
- Task 17's smoke test depends on exactly matching scripted response counts. If the orchestrator makes more or fewer Claude calls than listed, adjust the script rather than the orchestrator.
