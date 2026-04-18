from __future__ import annotations

from pathlib import Path

from methodology_runner.phase_6_validation import build_report


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_phase_6_validation_accepts_valid_workflow_and_run_report(
    tmp_path: Path,
) -> None:
    workflow = _write(
        tmp_path / "docs" / "implementation" / "implementation-workflow.md",
        """### Module
implementation-workflow

## Prompt 1: Create Failing Test

### Generation Prompt

Use TDD. Write a failing test first, run pytest -q, then implement the
smallest slice needed.

### Validation Prompt

Review the new test-first slice.

## Prompt 2: Final Verification

### Generation Prompt

Run the relevant tests and perform final verification of the assembled
implementation.

### Validation Prompt

Review the final verification outcome.
""",
    )

    child_run_dir = tmp_path / "child-run"
    _write(
        child_run_dir / ".run-files" / "implementation-workflow" / "summary.txt",
        "Status: completed\n",
    )

    run_report = _write(
        tmp_path / "docs" / "implementation" / "implementation-run-report.yaml",
        f"""child_prompt_path: "docs/implementation/implementation-workflow.md"
child_run_dir: "{child_run_dir}"
execution_mode: "fresh"
completion_status: "completed"
halt_reason: ""
prompt_results:
  - prompt_index: 1
    title: "Create Failing Test"
    verdict: "pass"
    iterations: 1
files_changed:
  - "tests/test_app.py"
  - "app.py"
test_commands_observed:
  - command: "pytest -q"
    exit_code: 0
next_action: "none"
""",
    )

    report = build_report(workflow, run_report, check_run_report=True)
    assert report["overall_status"] == "pass"
    assert report["failed_checks"] == []


def test_phase_6_validation_rejects_completed_report_with_halt_reason(
    tmp_path: Path,
) -> None:
    workflow = _write(
        tmp_path / "docs" / "implementation" / "implementation-workflow.md",
        """### Module
implementation-workflow

## Prompt 1: Create Failing Test

### Generation Prompt

Use TDD and run pytest -q.

### Validation Prompt

Review.

## Prompt 2: Final Verification

### Generation Prompt

Perform final verification.

### Validation Prompt

Review.
""",
    )

    child_run_dir = tmp_path / "child-run"
    _write(
        child_run_dir / ".run-files" / "implementation-workflow" / "summary.txt",
        "Status: completed\n",
    )

    run_report = _write(
        tmp_path / "docs" / "implementation" / "implementation-run-report.yaml",
        f"""child_prompt_path: "docs/implementation/implementation-workflow.md"
child_run_dir: "{child_run_dir}"
execution_mode: "resume"
completion_status: "completed"
halt_reason: "unexpected stop"
prompt_results:
  - prompt_index: 1
    title: "Create Failing Test"
    verdict: "pass"
    iterations: 1
files_changed:
  - "tests/test_app.py"
test_commands_observed:
  - command: "pytest -q"
    exit_code: 0
next_action: "none"
""",
    )

    report = build_report(workflow, run_report, check_run_report=True)
    assert report["overall_status"] == "fail"
    assert "run_report" in report["failed_checks"]
