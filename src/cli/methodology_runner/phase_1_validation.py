"""Deterministic validation for PH-001 feature specifications.

This validator covers the structural and traceability checks that do not need
an LLM:
- YAML parses
- expected top-level keys exist in order
- every feature has required fields
- every RI item is covered by a feature or out_of_scope
- dependency targets exist and are not self-dependencies
- each cross-cutting concern affects at least two features

Exit codes:
- 0: all deterministic checks passed
- 1: one or more deterministic checks failed
- 2: validator execution error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


EXPECTED_TOP_LEVEL_KEYS = [
    "features",
    "out_of_scope",
    "cross_cutting_concerns",
]
REQUIRED_FEATURE_FIELDS = [
    "id",
    "name",
    "description",
    "source_inventory_refs",
    "acceptance_criteria",
    "dependencies",
]


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _out_of_scope_ref(item: dict) -> str | None:
    for key in ("inventory_ref", "source_inventory_ref", "inventory_id", "id"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def build_report(feature_spec_path: Path, requirements_inventory_path: Path) -> dict:
    feature_spec = _load_yaml(feature_spec_path)
    inventory = _load_yaml(requirements_inventory_path)

    checks: list[dict] = []

    actual_keys = list(feature_spec.keys()) if isinstance(feature_spec, dict) else []
    checks.append(
        {
            "id": "top_level_keys",
            "status": "pass" if actual_keys == EXPECTED_TOP_LEVEL_KEYS else "fail",
            "expected": EXPECTED_TOP_LEVEL_KEYS,
            "actual": actual_keys,
        }
    )

    missing_feature_fields: list[dict] = []
    feature_ids = set()
    for feature in feature_spec.get("features", []):
        feature_id = feature.get("id")
        if isinstance(feature_id, str):
            feature_ids.add(feature_id)
        missing = [
            field_name
            for field_name in REQUIRED_FEATURE_FIELDS
            if field_name not in feature
        ]
        if missing:
            missing_feature_fields.append(
                {
                    "feature_id": feature_id,
                    "missing_fields": missing,
                }
            )
    checks.append(
        {
            "id": "feature_required_fields",
            "status": "pass" if not missing_feature_fields else "fail",
            "details": missing_feature_fields,
        }
    )

    inventory_ids = [item["id"] for item in inventory.get("items", [])]
    coverage: dict[str, list[str]] = {ri_id: [] for ri_id in inventory_ids}
    for feature in feature_spec.get("features", []):
        feature_id = feature.get("id", "(missing-id)")
        for ri_id in feature.get("source_inventory_refs", []):
            coverage.setdefault(ri_id, []).append(str(feature_id))
    for out_of_scope_item in feature_spec.get("out_of_scope", []):
        ri_id = _out_of_scope_ref(out_of_scope_item)
        if ri_id:
            coverage.setdefault(ri_id, []).append("out_of_scope")

    missing_inventory_refs = [
        ri_id
        for ri_id in inventory_ids
        if not coverage.get(ri_id)
    ]
    checks.append(
        {
            "id": "inventory_coverage",
            "status": "pass" if not missing_inventory_refs else "fail",
            "missing_inventory_refs": missing_inventory_refs,
            "coverage": coverage,
        }
    )

    dependency_issues: list[dict] = []
    for feature in feature_spec.get("features", []):
        feature_id = feature.get("id", "(missing-id)")
        for dependency_id in feature.get("dependencies", []):
            if dependency_id == feature_id:
                dependency_issues.append(
                    {
                        "feature_id": feature_id,
                        "dependency_id": dependency_id,
                        "issue": "self_dependency",
                    }
                )
            elif dependency_id not in feature_ids:
                dependency_issues.append(
                    {
                        "feature_id": feature_id,
                        "dependency_id": dependency_id,
                        "issue": "missing_target",
                    }
                )
    checks.append(
        {
            "id": "dependencies",
            "status": "pass" if not dependency_issues else "fail",
            "details": dependency_issues,
        }
    )

    cross_cutting_issues: list[dict] = []
    for concern in feature_spec.get("cross_cutting_concerns", []):
        concern_id = concern.get("id", "(missing-id)")
        affected_features = concern.get("affected_features", [])
        if len(affected_features) < 2:
            cross_cutting_issues.append(
                {
                    "concern_id": concern_id,
                    "affected_features": affected_features,
                    "issue": "too_few_affected_features",
                }
            )
    checks.append(
        {
            "id": "cross_cutting_concerns",
            "status": "pass" if not cross_cutting_issues else "fail",
            "details": cross_cutting_issues,
        }
    )

    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {
        "validator": "phase_1_validation",
        "feature_spec_path": str(feature_spec_path),
        "requirements_inventory_path": str(requirements_inventory_path),
        "overall_status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic validation for PH-001 feature specifications.",
    )
    parser.add_argument(
        "--feature-spec",
        default="docs/features/feature-specification.yaml",
        help="Path to the feature specification YAML relative to cwd.",
    )
    parser.add_argument(
        "--requirements-inventory",
        default="docs/requirements/requirements-inventory.yaml",
        help="Path to the requirements inventory YAML relative to cwd.",
    )
    args = parser.parse_args(argv)

    feature_spec_path = Path(args.feature_spec)
    inventory_path = Path(args.requirements_inventory)
    try:
        report = build_report(feature_spec_path, inventory_path)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(
            json.dumps(
                {
                    "validator": "phase_1_validation",
                    "overall_status": "error",
                    "error": str(exc),
                },
                indent=2,
            )
        )
        return 2

    print(json.dumps(report, indent=2))
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
