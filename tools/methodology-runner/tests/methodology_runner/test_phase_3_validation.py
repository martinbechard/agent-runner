from pathlib import Path

import yaml

from methodology_runner.phase_3_validation import build_report


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_build_report_accepts_system_shape_components_for_stack_alignment(tmp_path: Path):
    solution_design = tmp_path / "docs" / "design" / "solution-design.yaml"
    _write_yaml(
        solution_design,
        {
            "components": [
                {
                    "id": "CMP-001",
                    "name": "CLI application",
                    "responsibility": "Owns the runtime behavior.",
                    "technology": "Python 3",
                    "feature_realization_map": {
                        "FT-001": "Provides the hello-world runtime behavior.",
                    },
                    "dependencies": [],
                }
            ],
            "interactions": [],
        },
    )

    architecture_design = tmp_path / "docs" / "architecture" / "architecture-design.yaml"
    _write_yaml(
        architecture_design,
        {
            "system_shape": {
                "components": [
                    {
                        "id": "CMP-001",
                        "supports": ["FT-001"],
                        "features_served": ["FT-001"],
                    }
                ]
            }
        },
    )

    feature_spec = tmp_path / "docs" / "features" / "feature-specification.yaml"
    _write_yaml(
        feature_spec,
        {
            "features": [
                {
                    "id": "FT-001",
                    "name": "Hello world",
                }
            ]
        },
    )

    report = build_report(solution_design, architecture_design, feature_spec)

    assert report["overall_status"] == "pass"
    failed = {check["id"] for check in report["checks"] if check["status"] != "pass"}
    assert "stack_alignment" not in failed


def test_build_report_prefers_features_served_when_supports_is_mapping(tmp_path: Path):
    solution_design = tmp_path / "docs" / "design" / "solution-design.yaml"
    _write_yaml(
        solution_design,
        {
            "components": [
                {
                    "id": "CMP-001",
                    "name": "CLI application",
                    "responsibility": "Owns the runtime behavior.",
                    "technology": {
                        "language": "Python 3",
                        "framework": "None",
                        "runtime_style": "Local command-line execution",
                    },
                    "feature_realization_map": {
                        "FT-001": "Provides the hello-world runtime behavior.",
                    },
                    "dependencies": [],
                },
                {
                    "id": "CMP-002",
                    "name": "README",
                    "responsibility": "Owns run instructions.",
                    "technology": {
                        "format": "Markdown",
                        "framework": "None",
                    },
                    "feature_realization_map": {
                        "FT-002": "Documents how to run the CLI application.",
                    },
                    "dependencies": ["CMP-001"],
                },
                {
                    "id": "CMP-003",
                    "name": "Automated test",
                    "responsibility": "Owns the output verification path.",
                    "technology": {
                        "language": "Python 3",
                        "framework": "Python standard-library testing only",
                        "runtime_style": "Local test-suite execution",
                    },
                    "feature_realization_map": {
                        "FT-003": "Checks the observed stdout output.",
                    },
                    "dependencies": ["CMP-001"],
                },
            ],
            "interactions": [
                {
                    "id": "INT-001",
                    "source": "CMP-002",
                    "target": "CMP-001",
                    "protocol": "sync-call",
                    "data_exchanged": "Run instructions",
                    "triggered_by": "Human follows README",
                },
                {
                    "id": "INT-002",
                    "source": "CMP-003",
                    "target": "CMP-001",
                    "protocol": "sync-call",
                    "data_exchanged": "Observed stdout",
                    "triggered_by": "Test execution",
                },
            ],
        },
    )

    architecture_design = tmp_path / "docs" / "architecture" / "architecture-design.yaml"
    _write_yaml(
        architecture_design,
        {
            "system_shape": {
                "components": [
                    {
                        "id": "CMP-001",
                        "supports": {
                            "inventory_refs": ["RI-001", "RI-002", "RI-003", "RI-009"],
                        },
                        "features_served": ["FT-001"],
                    },
                    {
                        "id": "CMP-002",
                        "supports": {
                            "inventory_refs": ["RI-005"],
                        },
                        "features_served": ["FT-002"],
                    },
                    {
                        "id": "CMP-003",
                        "supports": {
                            "inventory_refs": ["RI-002", "RI-006", "RI-010"],
                        },
                        "features_served": ["FT-003"],
                    },
                ]
            }
        },
    )

    feature_spec = tmp_path / "docs" / "features" / "feature-specification.yaml"
    _write_yaml(
        feature_spec,
        {
            "features": [
                {"id": "FT-001", "name": "Hello world"},
                {"id": "FT-002", "name": "Run instructions"},
                {"id": "FT-003", "name": "Output verification"},
            ]
        },
    )

    report = build_report(solution_design, architecture_design, feature_spec)

    assert report["overall_status"] == "pass"
    failed = {check["id"] for check in report["checks"] if check["status"] != "pass"}
    assert "stack_alignment" not in failed
