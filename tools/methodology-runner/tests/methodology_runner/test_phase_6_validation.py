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

Use TDD. Write a failing test first, run python3 -m unittest test_hello.py,
then implement the
smallest slice needed. Record stdout, stderr, and exit code outcomes.

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
  - command: "python3 -m unittest test_hello.py"
    exit_code: 0
    stdout_excerpt: "Ran 1 test in 0.01s\\n\\nOK"
    stderr_excerpt: ""
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

Use TDD and run python3 -m unittest test_hello.py. Record stdout, stderr,
and exit code outcomes.

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
  - command: "python3 -m unittest test_hello.py"
    exit_code: 0
    stdout_excerpt: "Ran 1 test in 0.01s\\n\\nOK"
    stderr_excerpt: ""
next_action: "none"
""",
    )

    report = build_report(workflow, run_report, check_run_report=True)
    assert report["overall_status"] == "fail"
    assert "run_report" in report["failed_checks"]


def test_phase_6_validation_rejects_markdown_list_path_entries(
    tmp_path: Path,
) -> None:
    workflow = _write(
        tmp_path / "docs" / "implementation" / "implementation-workflow.md",
        """### Module
implementation-workflow

## Prompt 1: Create Failing Test

### Required Files

- `docs/features/feature-specification.yaml`

### Checks Files

`main.py`

### Generation Prompt

Use TDD and run python3 -m unittest test_hello.py.

### Validation Prompt

Review.

## Prompt 2: Final Verification

### Generation Prompt

Perform final verification.

### Validation Prompt

Review.
""",
    )

    report = build_report(workflow)
    assert report["overall_status"] == "fail"
    assert "workflow_prompt" in report["failed_checks"]
    workflow_check = next(check for check in report["checks"] if check["id"] == "workflow_prompt")
    path_check = next(check for check in workflow_check["checks"] if check["id"] == "path_metadata_entries_plain")
    assert path_check["status"] == "fail"
    assert len(path_check["details"]) == 2


def test_phase_6_validation_rejects_loose_tdd_wording_and_missing_output_details(
    tmp_path: Path,
) -> None:
    workflow = _write(
        tmp_path / "docs" / "implementation" / "implementation-workflow.md",
        """### Module
implementation-workflow

## Prompt 1: README Alignment

### Generation Prompt

Run python3 -m unittest tests.test_cli before the README implementation change.
Record the observed failing or tightened-test run from that command.

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
execution_mode: "fresh"
completion_status: "completed"
halt_reason: ""
prompt_results:
  - prompt_index: 1
    title: "README Alignment"
    verdict: "pass"
    iterations: 1
files_changed:
  - "README.md"
test_commands_observed:
  - command: "python3 -m unittest tests.test_cli"
    exit_code: 0
next_action: "none"
""",
    )

    report = build_report(workflow, run_report, check_run_report=True)
    assert report["overall_status"] == "fail"
    workflow_check = next(check for check in report["checks"] if check["id"] == "workflow_prompt")
    loose_tdd_check = next(
        check for check in workflow_check["checks"] if check["id"] == "forbidden_loose_tdd_phrase"
    )
    assert loose_tdd_check["status"] == "fail"
    run_report_check = next(check for check in report["checks"] if check["id"] == "run_report")
    commands_shape = next(
        check for check in run_report_check["checks"] if check["id"] == "test_commands_shape"
    )
    assert commands_shape["status"] == "fail"
