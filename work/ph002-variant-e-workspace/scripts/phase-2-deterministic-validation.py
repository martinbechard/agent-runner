"""Deterministic validation for PH-002 architecture stack manifests."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


EXPECTED_TOP_LEVEL_KEYS = [
    "components",
    "integration_points",
    "rationale",
]
REQUIRED_COMPONENT_FIELDS = [
    "id",
    "name",
    "role",
    "technology",
    "runtime",
    "frameworks",
    "persistence",
    "expected_expertise",
    "features_served",
]
REQUIRED_INTEGRATION_FIELDS = [
    "id",
    "between",
    "protocol",
    "contract_source",
]
PYTHON_FRAMEWORKS = {
    "fastapi",
    "flask",
    "django",
    "typer",
    "click",
    "pytest",
}
TYPESCRIPT_FRAMEWORKS = {
    "react",
    "nextjs",
    "express",
    "fastify",
    "vite",
    "jest",
    "vitest",
    "hono",
}


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _looks_like_slug(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", value))


def _framework_coherence_issues(technology: str, frameworks: list[str]) -> list[str]:
    tech = technology.strip().lower()
    normalized = [framework.strip().lower() for framework in frameworks]
    issues: list[str] = []
    if tech == "python":
        bad = sorted(framework for framework in normalized if framework in TYPESCRIPT_FRAMEWORKS)
        if bad:
            issues.append(f"python_with_typescript_frameworks:{','.join(bad)}")
    if tech in {"typescript", "javascript"}:
        bad = sorted(framework for framework in normalized if framework in PYTHON_FRAMEWORKS)
        if bad:
            issues.append(f"typescript_with_python_frameworks:{','.join(bad)}")
    return issues


def build_report(stack_manifest_path: Path, feature_spec_path: Path, requirements_inventory_path: Path) -> dict:
    stack_manifest = _load_yaml(stack_manifest_path)
    feature_spec = _load_yaml(feature_spec_path)
    requirements_inventory = _load_yaml(requirements_inventory_path)

    checks: list[dict] = []

    actual_keys = list(stack_manifest.keys()) if isinstance(stack_manifest, dict) else []
    checks.append(
        {
            "id": "top_level_keys",
            "status": "pass" if actual_keys == EXPECTED_TOP_LEVEL_KEYS else "fail",
            "expected": EXPECTED_TOP_LEVEL_KEYS,
            "actual": actual_keys,
        }
    )

    component_ids: list[str] = []
    component_field_issues: list[dict] = []
    expertise_issues: list[dict] = []
    coherence_issues: list[dict] = []
    for component in stack_manifest.get("components", []):
        component_id = component.get("id", "(missing-id)")
        if isinstance(component_id, str):
            component_ids.append(component_id)
        missing = [field_name for field_name in REQUIRED_COMPONENT_FIELDS if field_name not in component]
        if missing:
            component_field_issues.append({"component_id": component_id, "missing_fields": missing})
        expertise = component.get("expected_expertise", [])
        if not isinstance(expertise, list) or not expertise:
            expertise_issues.append({"component_id": component_id, "issue": "missing_expected_expertise"})
        else:
            for entry in expertise:
                if not isinstance(entry, str) or not entry.strip():
                    expertise_issues.append({"component_id": component_id, "issue": "blank_expertise_entry"})
                elif _looks_like_slug(entry.strip()):
                    expertise_issues.append({"component_id": component_id, "issue": "slug_like_expertise_entry", "entry": entry})
        frameworks = component.get("frameworks", [])
        if isinstance(frameworks, list):
            bad = _framework_coherence_issues(str(component.get("technology", "")), frameworks)
            if bad:
                coherence_issues.append({"component_id": component_id, "issues": bad})

    duplicate_components = sorted(component_id for component_id in set(component_ids) if component_ids.count(component_id) > 1)
    checks.append(
        {
            "id": "component_structure",
            "status": "pass" if not component_field_issues and not duplicate_components else "fail",
            "missing_fields": component_field_issues,
            "duplicate_component_ids": duplicate_components,
        }
    )
    checks.append(
        {
            "id": "expected_expertise",
            "status": "pass" if not expertise_issues else "fail",
            "details": expertise_issues,
        }
    )
    checks.append(
        {
            "id": "technology_framework_coherence",
            "status": "pass" if not coherence_issues else "fail",
            "details": coherence_issues,
        }
    )

    feature_ids = [feature["id"] for feature in feature_spec.get("features", [])]
    coverage: dict[str, list[str]] = {feature_id: [] for feature_id in feature_ids}
    empty_features_served: list[str] = []
    for component in stack_manifest.get("components", []):
        component_id = str(component.get("id", "(missing-id)"))
        features_served = component.get("features_served", [])
        if not features_served:
            empty_features_served.append(component_id)
        for feature_id in features_served:
            coverage.setdefault(feature_id, []).append(component_id)
    missing_feature_refs = [feature_id for feature_id in feature_ids if not coverage.get(feature_id)]
    checks.append(
        {
            "id": "feature_coverage",
            "status": "pass" if not missing_feature_refs and not empty_features_served else "fail",
            "missing_feature_refs": missing_feature_refs,
            "empty_features_served": empty_features_served,
            "coverage": coverage,
        }
    )

    integration_ids: list[str] = []
    integration_issues: list[dict] = []
    for integration_point in stack_manifest.get("integration_points", []):
        integration_id = integration_point.get("id", "(missing-id)")
        if isinstance(integration_id, str):
            integration_ids.append(integration_id)
        missing = [field_name for field_name in REQUIRED_INTEGRATION_FIELDS if field_name not in integration_point]
        if missing:
            integration_issues.append({"integration_id": integration_id, "issue": "missing_fields", "missing_fields": missing})
            continue
        between = integration_point.get("between", [])
        if not isinstance(between, list) or len(between) != 2:
            integration_issues.append({"integration_id": integration_id, "issue": "between_must_have_two_components", "between": between})
            continue
        if between[0] == between[1]:
            integration_issues.append({"integration_id": integration_id, "issue": "between_components_must_be_distinct", "between": between})
        for component_id in between:
            if component_id not in component_ids:
                integration_issues.append({"integration_id": integration_id, "issue": "unknown_component", "component_id": component_id})
        if not str(integration_point.get("protocol", "")).strip():
            integration_issues.append({"integration_id": integration_id, "issue": "blank_protocol"})
        if not str(integration_point.get("contract_source", "")).strip():
            integration_issues.append({"integration_id": integration_id, "issue": "blank_contract_source"})
    duplicate_integrations = sorted(integration_id for integration_id in set(integration_ids) if integration_ids.count(integration_id) > 1)
    checks.append(
        {
            "id": "integration_points",
            "status": "pass" if not integration_issues and not duplicate_integrations else "fail",
            "details": integration_issues,
            "duplicate_integration_ids": duplicate_integrations,
        }
    )

    rationale = stack_manifest.get("rationale", "")
    checks.append(
        {
            "id": "rationale",
            "status": "pass" if isinstance(rationale, str) and rationale.strip() else "fail",
            "actual": rationale,
        }
    )

    inventory_ids = [item["id"] for item in requirements_inventory.get("items", [])]
    feature_traceability: dict[str, list[str]] = {}
    unknown_feature_refs: list[dict] = []
    for feature in feature_spec.get("features", []):
        feature_id = feature.get("id", "(missing-id)")
        refs = feature.get("source_inventory_refs", [])
        feature_traceability[str(feature_id)] = list(refs)
        for ref in refs:
            if ref not in inventory_ids:
                unknown_feature_refs.append({"feature_id": feature_id, "inventory_ref": ref})
    checks.append(
        {
            "id": "upstream_feature_traceability",
            "status": "pass" if not unknown_feature_refs else "fail",
            "details": unknown_feature_refs,
            "feature_traceability": feature_traceability,
        }
    )

    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {
        "validator": "phase_2_validation",
        "stack_manifest_path": str(stack_manifest_path),
        "feature_spec_path": str(feature_spec_path),
        "requirements_inventory_path": str(requirements_inventory_path),
        "overall_status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic validation for PH-002 architecture stack manifests.",
    )
    parser.add_argument(
        "--stack-manifest",
        default="docs/architecture/stack-manifest.yaml",
        help="Path to the stack manifest YAML relative to cwd.",
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

    try:
        report = build_report(
            Path(args.stack_manifest),
            Path(args.feature_spec),
            Path(args.requirements_inventory),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "validator": "phase_2_validation",
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
