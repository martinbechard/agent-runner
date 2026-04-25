"""Deterministic validation for PH-002 architecture artifacts."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


EXPECTED_ARCHITECTURE_DESIGN_TOP_LEVEL_KEYS = [
    "components",
    "related_artifacts",
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
    "simulation_target",
    "simulation_boundary",
    "examples",
]
REQUIRED_INTEGRATION_FIELDS = [
    "id",
    "between",
    "protocol",
    "contract_source",
    "examples",
]
REQUIRED_EXAMPLE_FIELDS = [
    "name",
    "scenario",
    "expected_outcome",
    "feature_refs",
]
REQUIRED_RELATED_ARTIFACT_FIELDS = [
    "id",
    "name",
    "artifact_type",
    "scope",
    "related_components",
    "features_served",
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
SUPPORT_ARTIFACT_ROLE_MARKERS = (
    "documentation",
    "readme",
    "verification",
    "test",
    "test-suite",
)
SUPPORT_FEATURE_MARKERS = (
    "readme",
    "documentation",
    "document",
    "run instruction",
    "run instructions",
    "runbook",
    "automated test",
    "test suite",
    "verification",
    "verify",
    "report",
)
SUPPORT_ARTIFACT_TECHNOLOGIES = {"markdown"}
SUPPORT_ARTIFACT_RUNTIME_MARKERS = ("none", "test runner", "unittest", "pytest")
HUMAN_OR_SUPPORT_PROTOCOL_MARKERS = (
    "human",
    "instruction",
    "documentation",
    "readme",
    "verification",
    "test",
)
SIMULATABLE_BOUNDARIES = {
    "dependency-injection",
    "api",
    "library",
    "service",
    "command",
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


def _is_support_artifact_role(role: str) -> bool:
    """Return whether a component role describes support artifacts, not runtime."""
    normalized_role = role.strip().lower()
    return any(marker in normalized_role for marker in SUPPORT_ARTIFACT_ROLE_MARKERS)


def _is_support_artifact_component(component: dict) -> bool:
    """Detect README, documentation, test, and verification artifacts as components."""
    if not _is_support_artifact_role(str(component.get("role", ""))):
        return False

    technology = str(component.get("technology", "")).strip().lower()
    runtime = str(component.get("runtime", "")).strip().lower()
    name = str(component.get("name", "")).strip().lower()

    return (
        technology in SUPPORT_ARTIFACT_TECHNOLOGIES
        or any(marker in runtime for marker in SUPPORT_ARTIFACT_RUNTIME_MARKERS)
        or any(marker in name for marker in SUPPORT_ARTIFACT_ROLE_MARKERS)
    )


def _is_human_or_support_protocol(protocol: str) -> bool:
    """Return whether an integration protocol is not a runtime dependency."""
    normalized_protocol = protocol.strip().lower()
    return any(marker in normalized_protocol for marker in HUMAN_OR_SUPPORT_PROTOCOL_MARKERS)


def _has_real_runtime_consumer(
    component_id: str,
    components_by_id: dict[str, dict],
    integration_points: list[dict],
) -> bool:
    """Return whether a simulated provider is consumed by another runtime component."""
    for integration_point in integration_points:
        between = integration_point.get("between", [])
        if not isinstance(between, list) or len(between) != 2 or component_id not in between:
            continue

        other_component_id = between[1] if between[0] == component_id else between[0]
        other_component = components_by_id.get(str(other_component_id))
        if other_component is None:
            continue
        if _is_support_artifact_component(other_component):
            continue
        if _is_human_or_support_protocol(str(integration_point.get("protocol", ""))):
            continue
        return True

    return False


def _detect_artifact_shape(artifact: object) -> str:
    if not isinstance(artifact, dict):
        return "invalid"
    actual_keys = list(artifact.keys())
    if actual_keys == EXPECTED_ARCHITECTURE_DESIGN_TOP_LEVEL_KEYS:
        return "architecture_design"
    if {
        "components",
        "related_artifacts",
        "integration_points",
        "rationale",
    }.issubset(set(actual_keys)):
        return "structured_architecture"
    return "invalid"


def _is_support_feature(feature: dict) -> bool:
    """Return whether a feature describes a non-component support artifact."""
    text_parts: list[str] = []
    for key in ("name", "description"):
        value = feature.get(key)
        if isinstance(value, str):
            text_parts.append(value)
    for criterion in feature.get("acceptance_criteria", []):
        if isinstance(criterion, dict) and isinstance(criterion.get("description"), str):
            text_parts.append(criterion["description"])
    normalized = " ".join(text_parts).lower()
    return any(marker in normalized for marker in SUPPORT_FEATURE_MARKERS)


def _example_issues(owner_type: str, owner_id: str, examples: object, feature_id_set: set[str]) -> list[dict]:
    """Validate conceptual examples attached to a component or integration point."""
    if not isinstance(examples, list):
        return [{"owner_type": owner_type, "owner_id": owner_id, "issue": "examples_must_be_list"}]
    if not examples:
        return [{"owner_type": owner_type, "owner_id": owner_id, "issue": "missing_examples"}]

    issues: list[dict] = []
    for index, example in enumerate(examples):
        if not isinstance(example, dict):
            issues.append(
                {
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "example_index": index,
                    "issue": "example_must_be_mapping",
                }
            )
            continue

        missing = [field_name for field_name in REQUIRED_EXAMPLE_FIELDS if field_name not in example]
        if missing:
            issues.append(
                {
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "example_index": index,
                    "issue": "missing_example_fields",
                    "missing_fields": missing,
                }
            )

        for field_name in ("name", "scenario", "expected_outcome"):
            if field_name in example and not str(example.get(field_name, "")).strip():
                issues.append(
                    {
                        "owner_type": owner_type,
                        "owner_id": owner_id,
                        "example_index": index,
                        "issue": "blank_example_field",
                        "field": field_name,
                    }
                )

        feature_refs = example.get("feature_refs", [])
        if not isinstance(feature_refs, list) or not feature_refs:
            issues.append(
                {
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "example_index": index,
                    "issue": "example_feature_refs_must_be_non_empty_list",
                }
            )
            continue
        for feature_id in feature_refs:
            if feature_id not in feature_id_set:
                issues.append(
                    {
                        "owner_type": owner_type,
                        "owner_id": owner_id,
                        "example_index": index,
                        "issue": "unknown_example_feature_ref",
                        "feature_id": feature_id,
                    }
                )
    return issues


def build_report(architecture_design_path: Path, feature_spec_path: Path, requirements_inventory_path: Path) -> dict:
    architecture_design = _load_yaml(architecture_design_path)
    feature_spec = _load_yaml(feature_spec_path)
    requirements_inventory = _load_yaml(requirements_inventory_path)

    checks: list[dict] = []

    actual_keys = list(architecture_design.keys()) if isinstance(architecture_design, dict) else []
    artifact_shape = _detect_artifact_shape(architecture_design)
    checks.append(
        {
            "id": "top_level_keys",
            "status": "pass" if artifact_shape == "architecture_design" else "fail",
            "expected": {
                "architecture_design": EXPECTED_ARCHITECTURE_DESIGN_TOP_LEVEL_KEYS,
                "structured_architecture": [
                    "components",
                    "related_artifacts",
                    "integration_points",
                    "rationale",
                ],
            },
            "actual": actual_keys,
            "artifact_shape": artifact_shape,
        }
    )

    feature_ids = [feature["id"] for feature in feature_spec.get("features", [])]
    feature_id_set = set(feature_ids)

    component_ids: list[str] = []
    components_by_id: dict[str, dict] = {}
    component_field_issues: list[dict] = []
    example_issues: list[dict] = []
    expertise_issues: list[dict] = []
    coherence_issues: list[dict] = []
    support_artifact_component_issues: list[dict] = []
    simulation_target_issues: list[dict] = []
    related_artifacts = architecture_design.get("related_artifacts", [])
    if not isinstance(related_artifacts, list):
        related_artifacts = []
    integration_points = architecture_design.get("integration_points", [])
    if not isinstance(integration_points, list):
        integration_points = []
    for component in architecture_design.get("components", []):
        component_id = component.get("id", "(missing-id)")
        if isinstance(component_id, str):
            component_ids.append(component_id)
            components_by_id[component_id] = component
        missing = [field_name for field_name in REQUIRED_COMPONENT_FIELDS if field_name not in component]
        if missing:
            component_field_issues.append({"component_id": component_id, "missing_fields": missing})
        example_issues.extend(
            _example_issues("component", str(component_id), component.get("examples"), feature_id_set)
        )
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
        if "simulation_target" in component and not isinstance(component.get("simulation_target"), bool):
            simulation_target_issues.append(
                {
                    "component_id": component_id,
                    "issue": "simulation_target_must_be_boolean",
                    "actual": component.get("simulation_target"),
                }
            )
        if "simulation_boundary" in component and not str(component.get("simulation_boundary", "")).strip():
            simulation_target_issues.append(
                {"component_id": component_id, "issue": "blank_simulation_boundary"}
            )
        role = str(component.get("role", "")).lower()
        if component.get("simulation_target") is True and any(
            marker in role for marker in ("documentation", "verification", "test")
        ):
            simulation_target_issues.append(
                {"component_id": component_id, "issue": "non_runtime_component_marked_simulation_target", "role": role}
            )
        if _is_support_artifact_component(component):
            support_artifact_component_issues.append(
                {
                    "component_id": component_id,
                    "issue": "support_artifact_modeled_as_component",
                    "role": component.get("role"),
                    "technology": component.get("technology"),
                    "runtime": component.get("runtime"),
                }
            )
        if component.get("simulation_target") is True:
            boundary = str(component.get("simulation_boundary", "")).strip().lower()
            if boundary not in SIMULATABLE_BOUNDARIES:
                simulation_target_issues.append(
                    {
                        "component_id": component_id,
                        "issue": "simulation_target_without_simulatable_boundary",
                        "simulation_boundary": component.get("simulation_boundary"),
                    }
                )
    for component_id, component in components_by_id.items():
        if component.get("simulation_target") is True and not _has_real_runtime_consumer(
            component_id,
            components_by_id,
            integration_points,
        ):
            simulation_target_issues.append(
                {
                    "component_id": component_id,
                    "issue": "simulation_target_without_real_runtime_consumer",
                }
            )

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
    checks.append(
        {
            "id": "support_artifacts_not_components",
            "status": "pass" if not support_artifact_component_issues else "fail",
            "details": support_artifact_component_issues,
        }
    )
    checks.append(
        {
            "id": "simulation_target_classification",
            "status": "pass" if not simulation_target_issues else "fail",
            "details": simulation_target_issues,
        }
    )

    support_feature_ids = [
        str(feature.get("id"))
        for feature in feature_spec.get("features", [])
        if isinstance(feature.get("id"), str) and _is_support_feature(feature)
    ]
    support_feature_id_set = set(support_feature_ids)

    coverage: dict[str, list[str]] = {feature_id: [] for feature_id in feature_ids}
    empty_features_served: list[str] = []
    for component in architecture_design.get("components", []):
        component_id = str(component.get("id", "(missing-id)"))
        features_served = component.get("features_served", [])
        if not features_served:
            empty_features_served.append(component_id)
        for feature_id in features_served:
            coverage.setdefault(feature_id, []).append(component_id)
    missing_feature_refs = [
        feature_id
        for feature_id in feature_ids
        if feature_id not in support_feature_id_set and not coverage.get(feature_id)
    ]
    checks.append(
        {
            "id": "feature_coverage",
            "status": "pass" if not missing_feature_refs and not empty_features_served else "fail",
            "missing_feature_refs": missing_feature_refs,
            "empty_features_served": empty_features_served,
            "support_feature_refs": support_feature_ids,
            "coverage": coverage,
        }
    )

    related_artifact_ids: list[str] = []
    related_artifact_issues: list[dict] = []
    related_artifact_coverage: dict[str, list[str]] = {feature_id: [] for feature_id in feature_ids}
    for artifact in related_artifacts:
        artifact_id = artifact.get("id", "(missing-id)") if isinstance(artifact, dict) else "(non-mapping)"
        if not isinstance(artifact, dict):
            related_artifact_issues.append({"artifact_id": artifact_id, "issue": "related_artifact_must_be_mapping"})
            continue
        if isinstance(artifact_id, str):
            related_artifact_ids.append(artifact_id)
        if not isinstance(artifact_id, str) or not re.fullmatch(r"ART-\d{3}", artifact_id):
            related_artifact_issues.append({"artifact_id": artifact_id, "issue": "invalid_artifact_id"})
        missing = [field_name for field_name in REQUIRED_RELATED_ARTIFACT_FIELDS if field_name not in artifact]
        if missing:
            related_artifact_issues.append(
                {"artifact_id": artifact_id, "issue": "missing_fields", "missing_fields": missing}
            )
            continue
        if not str(artifact.get("name", "")).strip():
            related_artifact_issues.append({"artifact_id": artifact_id, "issue": "blank_name"})
        if not str(artifact.get("artifact_type", "")).strip():
            related_artifact_issues.append({"artifact_id": artifact_id, "issue": "blank_artifact_type"})
        if "path" in artifact:
            related_artifact_issues.append(
                {
                    "artifact_id": artifact_id,
                    "issue": "architecture_related_artifact_must_not_specify_path",
                    "path": artifact.get("path"),
                }
            )
        scope = str(artifact.get("scope", "")).strip().lower()
        if scope not in {"system", "component"}:
            related_artifact_issues.append({"artifact_id": artifact_id, "issue": "invalid_scope", "scope": artifact.get("scope")})
        related_components = artifact.get("related_components", [])
        if not isinstance(related_components, list):
            related_artifact_issues.append({"artifact_id": artifact_id, "issue": "related_components_must_be_list"})
            related_components = []
        if scope == "component" and not related_components:
            related_artifact_issues.append({"artifact_id": artifact_id, "issue": "component_scoped_artifact_without_component"})
        for component_id in related_components:
            if component_id not in component_ids:
                related_artifact_issues.append(
                    {"artifact_id": artifact_id, "issue": "unknown_related_component", "component_id": component_id}
                )
        artifact_features = artifact.get("features_served", [])
        if not isinstance(artifact_features, list) or not artifact_features:
            related_artifact_issues.append({"artifact_id": artifact_id, "issue": "missing_features_served"})
            artifact_features = []
        for feature_id in artifact_features:
            if feature_id not in feature_id_set:
                related_artifact_issues.append(
                    {"artifact_id": artifact_id, "issue": "unknown_feature", "feature_id": feature_id}
                )
                continue
            related_artifact_coverage.setdefault(feature_id, []).append(str(artifact_id))
    duplicate_related_artifacts = sorted(
        artifact_id for artifact_id in set(related_artifact_ids) if related_artifact_ids.count(artifact_id) > 1
    )
    missing_support_artifact_coverage = [
        feature_id for feature_id in support_feature_ids if not related_artifact_coverage.get(feature_id)
    ]
    checks.append(
        {
            "id": "related_artifacts",
            "status": "pass"
            if not related_artifact_issues and not duplicate_related_artifacts and not missing_support_artifact_coverage
            else "fail",
            "details": related_artifact_issues,
            "duplicate_artifact_ids": duplicate_related_artifacts,
            "missing_support_feature_refs": missing_support_artifact_coverage,
            "coverage": related_artifact_coverage,
        }
    )

    integration_ids: list[str] = []
    integration_issues: list[dict] = []
    for integration_point in architecture_design.get("integration_points", []):
        integration_id = integration_point.get("id", "(missing-id)")
        if isinstance(integration_id, str):
            integration_ids.append(integration_id)
        missing = [field_name for field_name in REQUIRED_INTEGRATION_FIELDS if field_name not in integration_point]
        example_issues.extend(
            _example_issues("integration_point", str(integration_id), integration_point.get("examples"), feature_id_set)
        )
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
    checks.append(
        {
            "id": "architecture_examples",
            "status": "pass" if not example_issues else "fail",
            "details": example_issues,
        }
    )

    rationale = architecture_design.get("rationale", "")
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
        "architecture_design_path": str(architecture_design_path),
        "feature_spec_path": str(feature_spec_path),
        "requirements_inventory_path": str(requirements_inventory_path),
        "overall_status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic validation for PH-002 architecture design artifacts.",
    )
    parser.add_argument(
        "--architecture-design",
        default="docs/architecture/architecture-design.yaml",
        help="Path to the architecture design YAML relative to cwd.",
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
            Path(args.architecture_design),
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
