"""Tests for PH-002 architecture deterministic validation."""
from __future__ import annotations

from pathlib import Path

from methodology_runner.phase_2_validation import build_report


def _write(path: Path, content: str) -> Path:
    """Write a temporary fixture file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _requirements_inventory(tmp_path: Path) -> Path:
    """Create a minimal requirements inventory used by architecture tests."""
    return _write(
        tmp_path / "docs" / "requirements" / "requirements-inventory.yaml",
        """items:
  - id: "RI-001"
    normalized_requirement: "Build the application."
  - id: "RI-002"
    normalized_requirement: "Document how to run it."
  - id: "RI-003"
    normalized_requirement: "Verify the expected output."
""",
    )


def _feature_spec(tmp_path: Path) -> Path:
    """Create a feature spec with runtime, README, and verification features."""
    return _write(
        tmp_path / "docs" / "features" / "feature-specification.yaml",
        """features:
  - id: "FT-001"
    name: "Runtime behavior"
    source_inventory_refs: ["RI-001"]
  - id: "FT-002"
    name: "Run documentation"
    source_inventory_refs: ["RI-002"]
  - id: "FT-003"
    name: "Automated verification"
    source_inventory_refs: ["RI-003"]
""",
    )


def _check(report: dict, check_id: str) -> dict:
    """Return one deterministic check from a PH-002 report."""
    for check in report["checks"]:
        if check["id"] == check_id:
            return check
    raise AssertionError(f"missing check: {check_id}")


def test_phase_2_validation_rejects_support_artifacts_as_components(
    tmp_path: Path,
) -> None:
    """Reject README/test components that make a simple CLI look simulatable."""
    architecture = _write(
        tmp_path / "docs" / "architecture" / "architecture-design.yaml",
        """components:
  - id: "CMP-001"
    name: "Hello World command-line application"
    role: "runtime"
    technology: "Python"
    runtime: "Python 3"
    frameworks: []
    persistence: "none"
    expected_expertise: ["Python command-line application development"]
    features_served: ["FT-001"]
    simulation_target: true
    simulation_boundary: "command"
    examples:
      - name: "Run greeting"
        scenario: "A user starts the command-line application."
        expected_outcome: "The application emits the requested greeting."
        feature_refs: ["FT-001"]
  - id: "CMP-002"
    name: "Run instructions documentation"
    role: "documentation"
    technology: "Markdown"
    runtime: "none"
    frameworks: []
    persistence: "none"
    expected_expertise: ["README authoring"]
    features_served: ["FT-002"]
    simulation_target: false
    simulation_boundary: "none"
    examples:
      - name: "Read run guidance"
        scenario: "A user opens the run instructions."
        expected_outcome: "The instructions describe how to run the application."
        feature_refs: ["FT-002"]
  - id: "CMP-003"
    name: "Automated output verification"
    role: "verification"
    technology: "Python"
    runtime: "Python 3 test runner"
    frameworks: []
    persistence: "none"
    expected_expertise: ["Python test authoring"]
    features_served: ["FT-003"]
    simulation_target: false
    simulation_boundary: "none"
    examples:
      - name: "Verify command output"
        scenario: "The verification executes the command."
        expected_outcome: "The verification observes the expected output."
        feature_refs: ["FT-003"]
related_artifacts: []
integration_points:
  - id: "IP-001"
    between: ["CMP-002", "CMP-001"]
    protocol: "human-instruction"
    contract_source: "FT-002"
    examples:
      - name: "Follow README instructions"
        scenario: "A user follows the documentation to invoke the CLI."
        expected_outcome: "The CLI is run through human instructions."
        feature_refs: ["FT-002"]
  - id: "IP-002"
    between: ["CMP-003", "CMP-001"]
    protocol: "command"
    contract_source: "FT-003"
    examples:
      - name: "Test invokes CLI"
        scenario: "The verification invokes the command."
        expected_outcome: "The command output is available for assertion."
        feature_refs: ["FT-003"]
rationale: "Separate docs and tests consume the runtime command."
""",
    )

    report = build_report(architecture, _feature_spec(tmp_path), _requirements_inventory(tmp_path))

    assert report["overall_status"] == "fail"
    support_check = _check(report, "support_artifacts_not_components")
    assert support_check["status"] == "fail"
    assert {issue["component_id"] for issue in support_check["details"]} == {
        "CMP-002",
        "CMP-003",
    }
    simulation_check = _check(report, "simulation_target_classification")
    assert simulation_check["status"] == "fail"
    assert {
        issue["issue"]
        for issue in simulation_check["details"]
        if issue["component_id"] == "CMP-001"
    } == {"simulation_target_without_real_runtime_consumer"}


def test_phase_2_validation_accepts_single_component_without_simulations(
    tmp_path: Path,
) -> None:
    """Accept a minimal app when support deliverables remain responsibilities."""
    architecture = _write(
        tmp_path / "docs" / "architecture" / "architecture-design.yaml",
        """components:
  - id: "CMP-001"
    name: "Hello World CLI application"
    role: "runtime"
    technology: "Python"
    runtime: "Python 3"
    frameworks: []
    persistence: "none"
    expected_expertise: ["Python command-line application development"]
    features_served: ["FT-001", "FT-002", "FT-003"]
    simulation_target: false
    simulation_boundary: "none"
    examples:
      - name: "Run hello world"
        scenario: "A user runs the CLI from a shell."
        expected_outcome: "The CLI prints the required greeting and exits successfully."
        feature_refs: ["FT-001"]
related_artifacts:
  - id: "ART-001"
    name: "Run instructions README"
    artifact_type: "readme"
    scope: "system"
    related_components: ["CMP-001"]
    features_served: ["FT-002"]
  - id: "ART-002"
    name: "CLI output test"
    artifact_type: "automated-test"
    scope: "component"
    related_components: ["CMP-001"]
    features_served: ["FT-003"]
integration_points: []
rationale: "One CLI component owns runtime behavior, README guidance, and tests because there is no service boundary."
""",
    )

    report = build_report(architecture, _feature_spec(tmp_path), _requirements_inventory(tmp_path))

    assert report["overall_status"] == "pass"


def test_phase_2_validation_requires_related_artifacts_for_support_features(
    tmp_path: Path,
) -> None:
    """Require README/test features to be represented outside components."""
    architecture = _write(
        tmp_path / "docs" / "architecture" / "architecture-design.yaml",
        """components:
  - id: "CMP-001"
    name: "Hello World CLI application"
    role: "runtime"
    technology: "Python"
    runtime: "Python 3"
    frameworks: []
    persistence: "none"
    expected_expertise: ["Python command-line application development"]
    features_served: ["FT-001", "FT-002", "FT-003"]
    simulation_target: false
    simulation_boundary: "none"
    examples:
      - name: "Run hello world"
        scenario: "A user runs the CLI from a shell."
        expected_outcome: "The CLI prints the required greeting and exits successfully."
        feature_refs: ["FT-001"]
related_artifacts: []
integration_points: []
rationale: "One CLI component owns behavior, while support artifacts were not listed."
""",
    )

    report = build_report(architecture, _feature_spec(tmp_path), _requirements_inventory(tmp_path))

    related_artifacts_check = _check(report, "related_artifacts")
    assert related_artifacts_check["status"] == "fail"
    assert related_artifacts_check["missing_support_feature_refs"] == ["FT-002", "FT-003"]


def test_phase_2_validation_accepts_provider_consumed_by_runtime_component(
    tmp_path: Path,
) -> None:
    """Allow simulations when a real runtime component consumes a provider."""
    architecture = _write(
        tmp_path / "docs" / "architecture" / "architecture-design.yaml",
        """components:
  - id: "CMP-001"
    name: "Checkout application"
    role: "runtime"
    technology: "Python"
    runtime: "Python 3"
    frameworks: []
    persistence: "none"
    expected_expertise: ["Python application development"]
    features_served: ["FT-001", "FT-002", "FT-003"]
    simulation_target: false
    simulation_boundary: "none"
    examples:
      - name: "Checkout with current time"
        scenario: "A checkout flow asks for the current time."
        expected_outcome: "The application receives a time value from the provider."
        feature_refs: ["FT-001"]
  - id: "CMP-002"
    name: "Clock provider"
    role: "runtime"
    technology: "Python"
    runtime: "Python 3"
    frameworks: []
    persistence: "none"
    expected_expertise: ["Clock provider interface design"]
    features_served: ["FT-001"]
    simulation_target: true
    simulation_boundary: "dependency-injection"
    examples:
      - name: "Provide current time"
        scenario: "The application asks the provider for the current time."
        expected_outcome: "The provider returns a timestamp value."
        feature_refs: ["FT-001"]
related_artifacts:
  - id: "ART-001"
    name: "Run instructions README"
    artifact_type: "readme"
    scope: "system"
    related_components: ["CMP-001"]
    features_served: ["FT-002"]
  - id: "ART-002"
    name: "Checkout verification test"
    artifact_type: "automated-test"
    scope: "component"
    related_components: ["CMP-001"]
    features_served: ["FT-003"]
integration_points:
  - id: "IP-001"
    between: ["CMP-001", "CMP-002"]
    protocol: "dependency-injection"
    contract_source: "FT-001"
    examples:
      - name: "Application requests time"
        scenario: "The checkout application invokes the injected clock provider."
        expected_outcome: "The provider returns the time used by the checkout application."
        feature_refs: ["FT-001"]
rationale: "The checkout application consumes time through a provider boundary."
""",
    )

    report = build_report(architecture, _feature_spec(tmp_path), _requirements_inventory(tmp_path))

    assert report["overall_status"] == "pass"


def test_phase_2_validation_accepts_internal_library_provider(
    tmp_path: Path,
) -> None:
    """Allow a single deployable app to simulate an internal provider library."""
    architecture = _write(
        tmp_path / "docs" / "architecture" / "architecture-design.yaml",
        """components:
  - id: "CMP-001"
    name: "Web report application"
    role: "runtime"
    technology: "TypeScript"
    runtime: "Node 22"
    frameworks: ["vite"]
    persistence: "none"
    expected_expertise: ["TypeScript web application development"]
    features_served: ["FT-001", "FT-002", "FT-003"]
    simulation_target: false
    simulation_boundary: "none"
    examples:
      - name: "Render normalized report"
        scenario: "A user opens a report file in the local web app."
        expected_outcome: "The app renders timeline data returned by the parser."
        feature_refs: ["FT-001"]
  - id: "CMP-002"
    name: "Report data parser"
    role: "library"
    technology: "TypeScript"
    runtime: "Node 22"
    frameworks: []
    persistence: "none"
    expected_expertise: ["Parser interface and data normalization design"]
    features_served: ["FT-001"]
    simulation_target: true
    simulation_boundary: "library"
    examples:
      - name: "Parse report JSON"
        scenario: "The web app requests normalized data for a selected report."
        expected_outcome: "The parser returns rows and details for the UI."
        feature_refs: ["FT-001"]
related_artifacts:
  - id: "ART-001"
    name: "Run instructions README"
    artifact_type: "readme"
    scope: "system"
    related_components: ["CMP-001", "CMP-002"]
    features_served: ["FT-002"]
  - id: "ART-002"
    name: "Report rendering verification"
    artifact_type: "automated-test"
    scope: "component"
    related_components: ["CMP-001"]
    features_served: ["FT-003"]
integration_points:
  - id: "IP-001"
    between: ["CMP-001", "CMP-002"]
    protocol: "library"
    contract_source: "FT-001"
    examples:
      - name: "Application calls parser library"
        scenario: "The web app loads report data by calling the parser library."
        expected_outcome: "Normalized report data flows back to the application."
        feature_refs: ["FT-001"]
rationale: "The app and parser ship together but have a useful library boundary for staged implementation."
""",
    )

    report = build_report(architecture, _feature_spec(tmp_path), _requirements_inventory(tmp_path))

    assert report["overall_status"] == "pass"


def test_phase_2_validation_rejects_related_artifact_paths(
    tmp_path: Path,
) -> None:
    """Keep concrete file paths out of conceptual architecture artifacts."""
    architecture = _write(
        tmp_path / "docs" / "architecture" / "architecture-design.yaml",
        """components:
  - id: "CMP-001"
    name: "Hello World CLI application"
    role: "runtime"
    technology: "Python"
    runtime: "Python 3"
    frameworks: []
    persistence: "none"
    expected_expertise: ["Python command-line application development"]
    features_served: ["FT-001", "FT-002", "FT-003"]
    simulation_target: false
    simulation_boundary: "none"
    examples:
      - name: "Run hello world"
        scenario: "A user runs the CLI from a shell."
        expected_outcome: "The CLI prints the required greeting and exits successfully."
        feature_refs: ["FT-001"]
related_artifacts:
  - id: "ART-001"
    name: "Run instructions README"
    artifact_type: "readme"
    path: "README.md"
    scope: "system"
    related_components: ["CMP-001"]
    features_served: ["FT-002"]
  - id: "ART-002"
    name: "CLI output test"
    artifact_type: "automated-test"
    scope: "component"
    related_components: ["CMP-001"]
    features_served: ["FT-003"]
integration_points: []
rationale: "One CLI component owns runtime behavior and conceptual support artifacts."
""",
    )

    report = build_report(architecture, _feature_spec(tmp_path), _requirements_inventory(tmp_path))

    assert report["overall_status"] == "fail"
    related_artifacts_check = _check(report, "related_artifacts")
    assert {
        issue["issue"] for issue in related_artifacts_check["details"]
    } == {"architecture_related_artifact_must_not_specify_path"}


def test_phase_2_validation_requires_component_examples(tmp_path: Path) -> None:
    """Require PH-002 architecture to carry concrete behavioral examples."""
    architecture = _write(
        tmp_path / "docs" / "architecture" / "architecture-design.yaml",
        """components:
  - id: "CMP-001"
    name: "Hello World CLI application"
    role: "runtime"
    technology: "Python"
    runtime: "Python 3"
    frameworks: []
    persistence: "none"
    expected_expertise: ["Python command-line application development"]
    features_served: ["FT-001", "FT-002", "FT-003"]
    simulation_target: false
    simulation_boundary: "none"
    examples: []
related_artifacts:
  - id: "ART-001"
    name: "Run instructions README"
    artifact_type: "readme"
    scope: "system"
    related_components: ["CMP-001"]
    features_served: ["FT-002"]
  - id: "ART-002"
    name: "CLI output test"
    artifact_type: "automated-test"
    scope: "component"
    related_components: ["CMP-001"]
    features_served: ["FT-003"]
integration_points: []
rationale: "One CLI component owns runtime behavior and conceptual support artifacts."
""",
    )

    report = build_report(architecture, _feature_spec(tmp_path), _requirements_inventory(tmp_path))

    assert report["overall_status"] == "fail"
    examples_check = _check(report, "architecture_examples")
    assert examples_check["status"] == "fail"
    assert examples_check["details"] == [
        {
            "owner_type": "component",
            "owner_id": "CMP-001",
            "issue": "missing_examples",
        }
    ]
