from __future__ import annotations

from pathlib import Path

from methodology_runner.phase_4_validation import build_report


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_phase_4_validation_accepts_non_empty_request_and_response_schemas(
    tmp_path: Path,
) -> None:
    solution = _write(
        tmp_path / "docs" / "design" / "solution-design.yaml",
        """components:
  - id: "CMP-001"
    name: "CLI Entry Point"
    responsibility: "Owns command-line invocation."
    technology: "Python 3"
    feature_realization_map:
      FT-001: "Runs the CLI."
    dependencies: []
  - id: "CMP-002"
    name: "Greeting Renderer"
    responsibility: "Owns greeting text generation."
    technology: "Python 3"
    feature_realization_map:
      FT-002: "Produces the greeting text."
    dependencies: []
interactions:
  - id: "INT-001"
    source: "CMP-001"
    target: "CMP-002"
    protocol: "function-call"
    data_exchanged: "Greeting request and rendered greeting text."
    triggered_by: "CLI invocation."
""",
    )
    feature_spec = _write(
        tmp_path / "docs" / "features" / "feature-specification.yaml",
        """features:
  - id: "FT-001"
    name: "CLI"
    description: "Run the CLI."
    source_inventory_refs: ["RI-001"]
    acceptance_criteria:
      - id: "AC-001"
        description: "CLI runs."
    dependencies: []
  - id: "FT-002"
    name: "Greeting rendering"
    description: "Renderer returns the expected greeting text."
    source_inventory_refs: ["RI-002"]
    acceptance_criteria:
      - id: "AC-002"
        description: "Greeting text is returned."
    dependencies: ["FT-001"]
""",
    )
    contracts = _write(
        tmp_path / "docs" / "design" / "interface-contracts.yaml",
        """contracts:
  - id: "CTR-001"
    name: "Greeting Rendering Contract"
    interaction_ref: "INT-001"
    source_component: "CMP-001"
    target_component: "CMP-002"
    operations:
      - name: "render_greeting"
        description: "Returns the command-line greeting text."
        request_schema:
          fields:
            - name: "locale"
              type: "string"
              required: true
              constraints: "Supported locale identifier."
        response_schema:
          fields:
            - name: "greeting"
              type: "string"
              required: true
              constraints: "Exactly the rendered greeting text."
        error_types:
          - name: "unsupported_locale"
            condition: "Locale is not supported."
            http_status: 400
    behavioral_specs:
      - precondition: "The CLI requests a supported locale."
        postcondition: "The renderer returns a greeting string."
        invariant: "The response schema remains non-empty."
""",
    )

    report = build_report(solution, feature_spec, contracts)
    assert report["overall_status"] == "pass"
    assert report["failed_checks"] == []


def test_phase_4_validation_rejects_empty_response_schema_fields(
    tmp_path: Path,
) -> None:
    solution = _write(
        tmp_path / "docs" / "design" / "solution-design.yaml",
        """components:
  - id: "CMP-001"
    name: "CLI Entry Point"
    responsibility: "Owns command-line invocation."
    technology: "Python 3"
    feature_realization_map:
      FT-001: "Runs the CLI."
    dependencies: []
  - id: "CMP-002"
    name: "Greeting Renderer"
    responsibility: "Owns greeting text generation."
    technology: "Python 3"
    feature_realization_map:
      FT-002: "Produces the greeting text."
    dependencies: []
interactions:
  - id: "INT-001"
    source: "CMP-001"
    target: "CMP-002"
    protocol: "function-call"
    data_exchanged: "Greeting request and rendered greeting text."
    triggered_by: "CLI invocation."
""",
    )
    feature_spec = _write(
        tmp_path / "docs" / "features" / "feature-specification.yaml",
        """features:
  - id: "FT-001"
    name: "CLI"
    description: "Run the CLI."
    source_inventory_refs: ["RI-001"]
    acceptance_criteria:
      - id: "AC-001"
        description: "CLI runs."
    dependencies: []
  - id: "FT-002"
    name: "Greeting rendering"
    description: "Renderer returns the expected greeting text."
    source_inventory_refs: ["RI-002"]
    acceptance_criteria:
      - id: "AC-002"
        description: "Greeting text is returned."
    dependencies: ["FT-001"]
""",
    )
    contracts = _write(
        tmp_path / "docs" / "design" / "interface-contracts.yaml",
        """contracts:
  - id: "CTR-001"
    name: "Greeting Rendering Contract"
    interaction_ref: "INT-001"
    source_component: "CMP-001"
    target_component: "CMP-002"
    operations:
      - name: "render_greeting"
        description: "Returns the command-line greeting text."
        request_schema:
          fields:
            - name: "locale"
              type: "string"
              required: true
              constraints: "Supported locale identifier."
        response_schema:
          fields: []
        error_types:
          - name: "unsupported_locale"
            condition: "Locale is not supported."
            http_status: 400
    behavioral_specs:
      - precondition: "The CLI requests a supported locale."
        postcondition: "The renderer returns a greeting string."
        invariant: "The response schema remains non-empty."
""",
    )

    report = build_report(solution, feature_spec, contracts)
    assert report["overall_status"] == "fail"
    assert "schema_precision" in report["failed_checks"]
    schema_check = next(check for check in report["checks"] if check["id"] == "schema_precision")
    assert schema_check["status"] == "fail"
    assert {
        detail["issue"] for detail in schema_check["details"] if detail["contract_id"] == "CTR-001"
    } == {"empty_schema_fields"}


def test_phase_4_validation_accepts_empty_contracts_when_no_interactions(
    tmp_path: Path,
) -> None:
    solution = _write(
        tmp_path / "docs" / "design" / "solution-design.yaml",
        """components:
  - id: "CMP-001"
    name: "CLI Entry Point"
    responsibility: "Owns command-line invocation."
    technology: "Python 3"
    feature_realization_map:
      FT-001: "Runs the CLI."
    dependencies: []
interactions: []
""",
    )
    feature_spec = _write(
        tmp_path / "docs" / "features" / "feature-specification.yaml",
        """features:
  - id: "FT-001"
    name: "CLI"
    description: "Run the CLI."
    source_inventory_refs: ["RI-001"]
    acceptance_criteria:
      - id: "AC-001"
        description: "CLI runs."
    dependencies: []
""",
    )
    contracts = _write(
        tmp_path / "docs" / "design" / "interface-contracts.yaml",
        "contracts: []\n",
    )

    report = build_report(solution, feature_spec, contracts)

    assert report["overall_status"] == "pass"
    assert report["failed_checks"] == []
