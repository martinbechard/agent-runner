from __future__ import annotations

from pathlib import Path

from methodology_runner.phase_7_validation import build_report


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_phase_7_validation_accepts_truthful_verification_report(
    tmp_path: Path,
) -> None:
    feature_spec = _write(
        tmp_path / "docs" / "features" / "feature-specification.yaml",
        """features:
  - id: "FT-001"
    name: "CLI Hello World"
    description: "Print Hello, world!"
    source_inventory_refs: ["RI-001"]
    acceptance_criteria: []
    dependencies: []
out_of_scope: []
cross_cutting_concerns: []
""",
    )
    requirements_inventory = _write(
        tmp_path / "docs" / "requirements" / "requirements-inventory.yaml",
        """source_document: "docs/requirements/raw-requirements.md"
items:
  - id: "RI-001"
    category: "functional"
    verbatim_quote: "Build a Python application."
    normalized_requirement: "The system shall provide a Python application."
    justification: ""
    source_location: "Goal > paragraph 1"
    tags: ["python"]
    rationale:
      rule: "Direct extraction"
      because: "Core deliverable."
    open_assumptions: []
out_of_scope: []
""",
    )
    workflow = _write(
        tmp_path / "docs" / "implementation" / "implementation-workflow.md",
        """### Module
implementation-workflow

## Prompt 1: Build App

### Generation Prompt

Use TDD, write a failing test, then implement the app.

### Validation Prompt

Review.

## Prompt 2: Final Verification

### Generation Prompt

Perform final verification.

### Validation Prompt

Review.
""",
    )
    run_report = _write(
        tmp_path / "docs" / "implementation" / "implementation-run-report.yaml",
        """child_prompt_path: "docs/implementation/implementation-workflow.md"
child_run_dir: "/tmp/child-run"
execution_mode: "fresh"
completion_status: "completed"
halt_reason: ""
prompt_results:
  - prompt_index: 1
    title: "Build App"
    verdict: "pass"
    iterations: 1
files_changed:
  - "app.py"
  - "tests/test_app.py"
test_commands_observed:
  - command: "pytest -q"
    exit_code: 0
next_action: "none"
""",
    )
    verification_report = _write(
        tmp_path / "docs" / "verification" / "verification-report.yaml",
        """verification_commands:
  - command: "pytest -q"
    exit_code: 0
    purpose: "Verify the application output test passes."
    evidence: "tests/test_app.py passes against app.py"
requirement_results:
  - inventory_ref: "RI-001"
    feature_refs: ["FT-001"]
    status: "satisfied"
    evidence:
      files: ["app.py", "tests/test_app.py"]
      commands: ["pytest -q"]
      notes: "The built application exists and the test suite passes."
coverage_summary:
  total_requirements: 1
  satisfied: 1
  partial: 0
  unsatisfied: 0
""",
    )

    report = build_report(
        feature_spec,
        requirements_inventory,
        workflow,
        run_report,
        verification_report,
    )
    assert report["overall_status"] == "pass"
    assert report["failed_checks"] == []


def test_phase_7_validation_accepts_phase_7_rerun_command(
    tmp_path: Path,
) -> None:
    feature_spec = _write(
        tmp_path / "docs" / "features" / "feature-specification.yaml",
        """features:
  - id: "FT-001"
    name: "CLI Hello World"
    description: "Print Hello, world!"
    source_inventory_refs: ["RI-001"]
    acceptance_criteria: []
    dependencies: []
out_of_scope: []
cross_cutting_concerns: []
""",
    )
    requirements_inventory = _write(
        tmp_path / "docs" / "requirements" / "requirements-inventory.yaml",
        """source_document: "docs/requirements/raw-requirements.md"
items:
  - id: "RI-001"
    category: "functional"
    verbatim_quote: "Build a Python application."
    normalized_requirement: "The system shall provide a Python application."
    justification: ""
    source_location: "Goal > paragraph 1"
    tags: ["python"]
    rationale:
      rule: "Direct extraction"
      because: "Core deliverable."
    open_assumptions: []
out_of_scope: []
""",
    )
    workflow = _write(
        tmp_path / "docs" / "implementation" / "implementation-workflow.md",
        """### Module
implementation-workflow

## Prompt 1: Build App

### Generation Prompt

Use TDD and run final verification.

### Validation Prompt

Review.

## Prompt 2: Final Verification

### Generation Prompt

Perform final verification.

### Validation Prompt

Review.
""",
    )
    run_report = _write(
        tmp_path / "docs" / "implementation" / "implementation-run-report.yaml",
        """child_prompt_path: "docs/implementation/implementation-workflow.md"
child_run_dir: "/tmp/child-run"
execution_mode: "fresh"
completion_status: "completed"
halt_reason: ""
prompt_results:
  - prompt_index: 1
    title: "Build App"
    verdict: "pass"
    iterations: 1
files_changed:
  - "app.py"
test_commands_observed:
  - command: "python app.py"
    exit_code: 0
next_action: "none"
""",
    )
    verification_report = _write(
        tmp_path / "docs" / "verification" / "verification-report.yaml",
        """verification_commands:
  - command: "pytest -q"
    exit_code: 0
    purpose: "Verify the application output test passes."
    evidence: "tests/test_app.py passes against app.py"
requirement_results:
  - inventory_ref: "RI-001"
    feature_refs: ["FT-001"]
    status: "satisfied"
    evidence:
      files: ["app.py"]
      commands: ["pytest -q"]
      notes: "Claimed satisfied."
coverage_summary:
  total_requirements: 1
  satisfied: 1
  partial: 0
  unsatisfied: 0
""",
    )

    report = build_report(
        feature_spec,
        requirements_inventory,
        workflow,
        run_report,
        verification_report,
    )
    assert report["overall_status"] == "pass"
    assert report["failed_checks"] == []


def test_phase_7_validation_rejects_requirement_row_command_not_declared(
    tmp_path: Path,
) -> None:
    feature_spec = _write(
        tmp_path / "docs" / "features" / "feature-specification.yaml",
        """features:
  - id: "FT-001"
    name: "CLI Hello World"
    description: "Print Hello, world!"
    source_inventory_refs: ["RI-001"]
    acceptance_criteria: []
    dependencies: []
out_of_scope: []
cross_cutting_concerns: []
""",
    )
    requirements_inventory = _write(
        tmp_path / "docs" / "requirements" / "requirements-inventory.yaml",
        """source_document: "docs/requirements/raw-requirements.md"
items:
  - id: "RI-001"
    category: "functional"
    verbatim_quote: "Build a Python application."
    normalized_requirement: "The system shall provide a Python application."
    justification: ""
    source_location: "Goal > paragraph 1"
    tags: ["python"]
    rationale:
      rule: "Direct extraction"
      because: "Core deliverable."
    open_assumptions: []
out_of_scope: []
""",
    )
    workflow = _write(
        tmp_path / "docs" / "implementation" / "implementation-workflow.md",
        """### Module
implementation-workflow

## Prompt 1: Build App

### Generation Prompt

Use TDD and run final verification.

### Validation Prompt

Review.

## Prompt 2: Final Verification

### Generation Prompt

Perform final verification.

### Validation Prompt

Review.
""",
    )
    run_report = _write(
        tmp_path / "docs" / "implementation" / "implementation-run-report.yaml",
        """child_prompt_path: "docs/implementation/implementation-workflow.md"
child_run_dir: "/tmp/child-run"
execution_mode: "fresh"
completion_status: "completed"
halt_reason: ""
prompt_results:
  - prompt_index: 1
    title: "Build App"
    verdict: "pass"
    iterations: 1
files_changed:
  - "app.py"
test_commands_observed:
  - command: "python app.py"
    exit_code: 0
next_action: "none"
""",
    )
    verification_report = _write(
        tmp_path / "docs" / "verification" / "verification-report.yaml",
        """verification_commands:
  - command: "pytest -q"
    exit_code: 0
    purpose: "Verify the application output test passes."
    evidence: "tests/test_app.py passes against app.py"
requirement_results:
  - inventory_ref: "RI-001"
    feature_refs: ["FT-001"]
    status: "satisfied"
    evidence:
      files: ["app.py"]
      commands: ["python app.py"]
      notes: "Claimed satisfied."
coverage_summary:
  total_requirements: 1
  satisfied: 1
  partial: 0
  unsatisfied: 0
""",
    )

    report = build_report(
        feature_spec,
        requirements_inventory,
        workflow,
        run_report,
        verification_report,
    )
    assert report["overall_status"] == "fail"
    assert "requirement_results_rows" in report["failed_checks"]
