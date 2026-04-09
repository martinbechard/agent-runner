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
