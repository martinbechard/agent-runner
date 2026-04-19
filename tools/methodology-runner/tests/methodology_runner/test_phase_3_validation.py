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
