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
  - id: "CMP-1"
    name: "CLI"
    responsibility: "Owns runtime behavior."
    technology: "Python 3"
    feature_realization_map:
      FT-001: "Runs the CLI."
    dependencies: []
  - id: "CMP-2"
    name: "README"
    responsibility: "Owns run instructions."
    technology: "Markdown"
    feature_realization_map:
      FT-002: "Documents the CLI."
    dependencies: ["CMP-1"]
interactions:
  - id: "INT-001"
    source: "CMP-2"
    target: "CMP-1"
    protocol: "event"
    data_exchanged: "Documented command and expected output."
    triggered_by: "README update."
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
    name: "README"
    description: "README documents the CLI."
    source_inventory_refs: ["RI-002"]
    acceptance_criteria:
      - id: "AC-002"
        description: "README exists."
    dependencies: ["FT-001"]
""",
    )
    contracts = _write(
        tmp_path / "docs" / "design" / "interface-contracts.yaml",
        """contracts:
  - id: "CTR-001"
    name: "README Runtime Reference Event Contract"
    interaction_ref: "INT-001"
    source_component: "CMP-2"
    target_component: "CMP-1"
    operations:
      - name: "publish_documented_runtime_reference"
        description: "Publishes the documented runtime reference."
        request_schema:
          fields:
            - name: "documentation_artifact_path"
              type: "string"
              required: true
              constraints: "Non-empty relative path."
        response_schema:
          fields:
            - name: "accepted"
              type: "boolean"
              required: true
              constraints: "True when the event payload is accepted."
        error_types:
          - name: "invalid_emitter"
            condition: "Source is not CMP-2."
            http_status: 400
    behavioral_specs:
      - precondition: "CMP-2 has a README reference payload."
        postcondition: "The contract yields an acknowledgement payload."
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
  - id: "CMP-1"
    name: "CLI"
    responsibility: "Owns runtime behavior."
    technology: "Python 3"
    feature_realization_map:
      FT-001: "Runs the CLI."
    dependencies: []
  - id: "CMP-2"
    name: "README"
    responsibility: "Owns run instructions."
    technology: "Markdown"
    feature_realization_map:
      FT-002: "Documents the CLI."
    dependencies: ["CMP-1"]
interactions:
  - id: "INT-001"
    source: "CMP-2"
    target: "CMP-1"
    protocol: "event"
    data_exchanged: "Documented command and expected output."
    triggered_by: "README update."
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
    name: "README"
    description: "README documents the CLI."
    source_inventory_refs: ["RI-002"]
    acceptance_criteria:
      - id: "AC-002"
        description: "README exists."
    dependencies: ["FT-001"]
""",
    )
    contracts = _write(
        tmp_path / "docs" / "design" / "interface-contracts.yaml",
        """contracts:
  - id: "CTR-001"
    name: "README Runtime Reference Event Contract"
    interaction_ref: "INT-001"
    source_component: "CMP-2"
    target_component: "CMP-1"
    operations:
      - name: "publish_documented_runtime_reference"
        description: "Publishes the documented runtime reference."
        request_schema:
          fields:
            - name: "documentation_artifact_path"
              type: "string"
              required: true
              constraints: "Non-empty relative path."
        response_schema:
          fields: []
        error_types:
          - name: "invalid_emitter"
            condition: "Source is not CMP-2."
            http_status: 400
    behavioral_specs:
      - precondition: "CMP-2 has a README reference payload."
        postcondition: "The contract yields an acknowledgement payload."
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
