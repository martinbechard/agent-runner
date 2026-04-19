from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


EXPECTED_TOP_LEVEL_KEYS = ["components", "interactions"]
REQUIRED_COMPONENT_FIELDS = [
    "id",
    "name",
    "responsibility",
    "technology",
    "feature_realization_map",
    "dependencies",
]
REQUIRED_INTERACTION_FIELDS = [
    "id",
    "source",
    "target",
    "protocol",
    "data_exchanged",
    "triggered_by",
]
ALLOWED_PROTOCOLS = {"sync-call", "async-message", "event", "shared-store"}


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_report(solution_design_path: Path, architecture_design_path: Path, feature_spec_path: Path) -> dict:
    design = _load_yaml(solution_design_path)
    architecture = _load_yaml(architecture_design_path)
    feature_spec = _load_yaml(feature_spec_path)

    checks = []
    actual_keys = list(design.keys()) if isinstance(design, dict) else []
    checks.append({"id": "top_level_keys", "status": "pass" if actual_keys == EXPECTED_TOP_LEVEL_KEYS else "fail", "actual": actual_keys})

    components = design.get("components", [])
    interactions = design.get("interactions", [])
    component_ids = {component.get("id") for component in components}
    feature_ids = {feature.get("id") for feature in feature_spec.get("features", [])}

    missing_component_fields = []
    orphan_components = []
    covered_features = set()
    for component in components:
        missing = [field for field in REQUIRED_COMPONENT_FIELDS if field not in component]
        if missing:
            missing_component_fields.append({"component_id": component.get("id"), "missing_fields": missing})
        frm = component.get("feature_realization_map", {})
        if not isinstance(frm, dict) or not frm:
            orphan_components.append(component.get("id"))
        else:
            covered_features.update(frm.keys())
    checks.append({"id": "component_required_fields", "status": "pass" if not missing_component_fields else "fail", "details": missing_component_fields})
    checks.append({"id": "orphan_components", "status": "pass" if not orphan_components else "fail", "details": orphan_components})

    uncovered_features = sorted(feature_ids - covered_features)
    checks.append({"id": "feature_coverage", "status": "pass" if not uncovered_features else "fail", "uncovered_features": uncovered_features})

    missing_interaction_fields = []
    bad_interactions = []
    dependency_gaps = []
    for interaction in interactions:
        missing = [field for field in REQUIRED_INTERACTION_FIELDS if field not in interaction]
        if missing:
            missing_interaction_fields.append({"interaction_id": interaction.get("id"), "missing_fields": missing})
            continue
        if interaction.get("source") not in component_ids or interaction.get("target") not in component_ids:
            bad_interactions.append({"interaction_id": interaction.get("id"), "issue": "unknown_component"})
        if interaction.get("protocol") not in ALLOWED_PROTOCOLS:
            bad_interactions.append({"interaction_id": interaction.get("id"), "issue": "invalid_protocol"})
    for component in components:
        for dep in component.get("dependencies", []):
            if dep not in component_ids:
                dependency_gaps.append({"component_id": component.get("id"), "dependency": dep, "issue": "unknown_dependency"})
                continue
            if not any(
                {interaction.get("source"), interaction.get("target")} == {component.get("id"), dep}
                for interaction in interactions
            ):
                dependency_gaps.append({"component_id": component.get("id"), "dependency": dep, "issue": "missing_interaction"})
    checks.append({"id": "interaction_required_fields", "status": "pass" if not missing_interaction_fields else "fail", "details": missing_interaction_fields})
    checks.append({"id": "interaction_validity", "status": "pass" if not bad_interactions else "fail", "details": bad_interactions})
    checks.append({"id": "dependency_interactions", "status": "pass" if not dependency_gaps else "fail", "details": dependency_gaps})

    architecture_components = architecture.get("system_shape", {}).get("components", [])
    if not architecture_components:
        architecture_components = architecture.get("system_shape", {}).get("modules", [])
    if not architecture_components:
        architecture_components = architecture.get("components", [])

    stack_features = {
        feature
        for component in architecture_components
        for feature in component.get("supports", [])
    }
    if not stack_features:
        stack_features = {
            feature
            for component in architecture_components
            for feature in component.get("features_served", [])
        }
    stack_alignment_failures = sorted(feature_ids - stack_features)
    checks.append({"id": "stack_alignment", "status": "pass" if not stack_alignment_failures else "fail", "details": stack_alignment_failures})

    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {
        "validator": "phase_3_validation",
        "overall_status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solution-design", default="docs/design/solution-design.yaml")
    parser.add_argument("--architecture-design", default="docs/architecture/architecture-design.yaml")
    parser.add_argument("--feature-spec", default="docs/features/feature-specification.yaml")
    args = parser.parse_args(argv)
    try:
        report = build_report(
            Path(args.solution_design),
            Path(args.architecture_design),
            Path(args.feature_spec),
        )
    except Exception as exc:
        print(json.dumps({"validator": "phase_3_validation", "overall_status": "error", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
