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
    "processing_functions",
    "ui_surfaces",
]
REQUIRED_PROCESSING_FUNCTION_FIELDS = [
    "name",
    "purpose",
    "triggered_by_features",
    "examples",
]
REQUIRED_PROCESSING_EXAMPLE_FIELDS = ["name", "input", "output"]
REQUIRED_UI_SURFACE_FIELDS = [
    "name",
    "purpose",
    "triggered_by_features",
    "html_mockup",
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


def _architecture_stack_features(architecture_components: list[dict]) -> set[str]:
    """Return features supported by the architecture stack contract.

    Current architecture components carry feature ownership in
    ``features_served``. Older shapes sometimes stored feature ids directly in
    ``supports`` as a list. Newer shapes use ``supports`` as a mapping for
    inventory refs, so we must not iterate that mapping as if its keys were
    feature ids.
    """
    features_served = {
        feature
        for component in architecture_components
        for feature in component.get("features_served", [])
        if isinstance(feature, str)
    }
    if features_served:
        return features_served

    legacy_supports = {
        feature
        for component in architecture_components
        for feature in component.get("supports", [])
        if isinstance(feature, str)
    }
    return legacy_supports


def _has_html_markup(value) -> bool:
    """Return whether a value looks like a non-empty HTML fragment."""
    return isinstance(value, str) and "<" in value and ">" in value and bool(value.strip())


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
    processing_function_issues = []
    ui_surface_issues = []
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
        processing_functions = component.get("processing_functions", [])
        if not isinstance(processing_functions, list):
            processing_function_issues.append(
                {
                    "component_id": component.get("id"),
                    "issue": "processing_functions_must_be_list",
                }
            )
            processing_functions = []
        for index, function in enumerate(processing_functions):
            function_name = function.get("name") if isinstance(function, dict) else None
            if not isinstance(function, dict):
                processing_function_issues.append(
                    {
                        "component_id": component.get("id"),
                        "function_index": index,
                        "issue": "processing_function_must_be_mapping",
                    }
                )
                continue
            missing_function_fields = [
                field for field in REQUIRED_PROCESSING_FUNCTION_FIELDS if field not in function
            ]
            if missing_function_fields:
                processing_function_issues.append(
                    {
                        "component_id": component.get("id"),
                        "function": function_name,
                        "issue": "missing_processing_function_fields",
                        "missing_fields": missing_function_fields,
                    }
                )
            examples = function.get("examples", [])
            if not isinstance(examples, list) or not examples:
                processing_function_issues.append(
                    {
                        "component_id": component.get("id"),
                        "function": function_name,
                        "issue": "missing_processing_function_examples",
                    }
                )
                continue
            for example_index, example in enumerate(examples):
                if not isinstance(example, dict):
                    processing_function_issues.append(
                        {
                            "component_id": component.get("id"),
                            "function": function_name,
                            "example_index": example_index,
                            "issue": "processing_example_must_be_mapping",
                        }
                    )
                    continue
                missing_example_fields = [
                    field for field in REQUIRED_PROCESSING_EXAMPLE_FIELDS if field not in example
                ]
                if missing_example_fields:
                    processing_function_issues.append(
                        {
                            "component_id": component.get("id"),
                            "function": function_name,
                            "example": example.get("name"),
                            "issue": "missing_processing_example_fields",
                            "missing_fields": missing_example_fields,
                        }
                    )
        ui_surfaces = component.get("ui_surfaces", [])
        if not isinstance(ui_surfaces, list):
            ui_surface_issues.append(
                {"component_id": component.get("id"), "issue": "ui_surfaces_must_be_list"}
            )
            ui_surfaces = []
        for index, surface in enumerate(ui_surfaces):
            surface_name = surface.get("name") if isinstance(surface, dict) else None
            if not isinstance(surface, dict):
                ui_surface_issues.append(
                    {
                        "component_id": component.get("id"),
                        "ui_index": index,
                        "issue": "ui_surface_must_be_mapping",
                    }
                )
                continue
            missing_surface_fields = [
                field for field in REQUIRED_UI_SURFACE_FIELDS if field not in surface
            ]
            if missing_surface_fields:
                ui_surface_issues.append(
                    {
                        "component_id": component.get("id"),
                        "ui_surface": surface_name,
                        "issue": "missing_ui_surface_fields",
                        "missing_fields": missing_surface_fields,
                    }
                )
            if not _has_html_markup(surface.get("html_mockup")):
                ui_surface_issues.append(
                    {
                        "component_id": component.get("id"),
                        "ui_surface": surface_name,
                        "issue": "missing_html_mockup",
                    }
                )
    checks.append({"id": "component_required_fields", "status": "pass" if not missing_component_fields else "fail", "details": missing_component_fields})
    checks.append({"id": "orphan_components", "status": "pass" if not orphan_components else "fail", "details": orphan_components})
    checks.append({"id": "processing_function_examples", "status": "pass" if not processing_function_issues else "fail", "details": processing_function_issues})
    checks.append({"id": "ui_html_mockups", "status": "pass" if not ui_surface_issues else "fail", "details": ui_surface_issues})

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

    stack_features = _architecture_stack_features(architecture_components)
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
