"""Deterministic validation for PH-005 component simulation artifacts."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml


REQUIRED_SIMULATION_FIELDS = {
    "id",
    "component_ref",
    "simulated_component",
    "purpose",
    "interface",
    "implementation",
    "usage",
    "artifacts",
    "integration_scenarios",
    "compile_commands",
    "validation_rules",
}
REQUIRED_INTERFACE_FIELDS = {"language", "kind", "path", "symbol", "contract_refs"}
REQUIRED_IMPLEMENTATION_FIELDS = {"path", "symbol", "implements", "behavior"}
REQUIRED_USAGE_FIELDS = {
    "mode",
    "instructions",
    "integration_reference",
    "configuration",
    "startup",
    "retirement",
    "documentation",
}
REQUIRED_USAGE_DOCUMENTATION_FIELDS = {"location", "path"}
REQUIRED_ARTIFACT_FIELDS = {"path", "role", "description", "phase_6_usage"}
USAGE_MODES = {"skeleton", "stub", "mock", "fake", "adapter", "service"}
USAGE_DOCUMENTATION_LOCATIONS = {"inline_comments", "readme"}
LEGACY_CONTRACT_SCENARIO_FIELDS = {"contract_ref", "scenario_bank", "llm_adjuster"}
NON_SIMULATION_ROLE_MARKERS = ("documentation", "verification", "test")


def _load_yaml(path: Path) -> Any:
    """Load a YAML file and normalize empty documents to an empty mapping."""
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _workspace_root(simulations_path: Path) -> Path:
    """Infer the project root from the standard docs/simulations output path."""
    resolved = simulations_path.resolve()
    if resolved.parent.name == "simulations" and resolved.parent.parent.name == "docs":
        return resolved.parent.parent.parent
    return resolved.parent


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    """Return only mapping items from a YAML list-like value."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _is_non_simulation_role(role: Any) -> bool:
    """Detect component roles that describe consumers rather than providers."""
    normalized = str(role or "").strip().lower()
    return any(marker in normalized for marker in NON_SIMULATION_ROLE_MARKERS)


def _is_non_empty_string(value: Any) -> bool:
    """Return whether *value* is a non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def _path_status(root: Path, raw_path: Any) -> dict[str, Any]:
    """Validate that a manifest source path is relative and exists."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        return {"path": raw_path, "exists": False, "issue": "blank_path"}
    path = Path(raw_path)
    if path.is_absolute():
        return {"path": raw_path, "exists": False, "issue": "absolute_path_not_allowed"}
    full_path = root / path
    return {"path": raw_path, "exists": full_path.exists()}


def _run_command(command: str, cwd: Path) -> dict[str, Any]:
    """Run one declared compile or interface-check command from the workspace root."""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "status": "fail",
            "issue": "timeout",
            "stdout_excerpt": (exc.stdout or "")[:400],
            "stderr_excerpt": (exc.stderr or "")[:400],
        }
    return {
        "command": command,
        "status": "pass" if completed.returncode == 0 else "fail",
        "exit_code": completed.returncode,
        "stdout_excerpt": completed.stdout[:400],
        "stderr_excerpt": completed.stderr[:400],
    }


def build_report(
    architecture_path: Path,
    contracts_path: Path,
    feature_spec_path: Path,
    simulations_path: Path,
) -> dict:
    """Build the deterministic validation report for a PH-005 artifact."""
    architecture_doc = _load_yaml(architecture_path)
    contracts_doc = _load_yaml(contracts_path)
    feature_spec = _load_yaml(feature_spec_path)
    simulations_doc = _load_yaml(simulations_path)
    workspace_root = _workspace_root(simulations_path)

    checks: list[dict[str, Any]] = []
    actual_keys = list(simulations_doc.keys()) if isinstance(simulations_doc, dict) else []
    checks.append(
        {
            "id": "top_level_keys",
            "status": "pass" if actual_keys == ["simulations"] else "fail",
            "actual": actual_keys,
        }
    )

    components = {
        component.get("id"): component
        for component in _as_dict_list(architecture_doc.get("components", []))
        if isinstance(component.get("id"), str)
    }
    simulation_target_issues: list[dict[str, Any]] = []
    target_component_ids: set[str] = set()
    for component_id, component in components.items():
        if "simulation_target" not in component:
            simulation_target_issues.append(
                {"component_id": component_id, "issue": "missing_simulation_target"}
            )
            continue
        if "simulation_boundary" not in component:
            simulation_target_issues.append(
                {"component_id": component_id, "issue": "missing_simulation_boundary"}
            )
        if not isinstance(component.get("simulation_target"), bool):
            simulation_target_issues.append(
                {
                    "component_id": component_id,
                    "issue": "simulation_target_must_be_boolean",
                    "actual": component.get("simulation_target"),
                }
            )
            continue
        if component.get("simulation_target") is True:
            target_component_ids.add(component_id)
            if _is_non_simulation_role(component.get("role")):
                simulation_target_issues.append(
                    {
                        "component_id": component_id,
                        "issue": "non_runtime_component_marked_simulation_target",
                        "role": component.get("role"),
                    }
                )
    checks.append(
        {
            "id": "architecture_simulation_targets",
            "status": "pass" if not simulation_target_issues else "fail",
            "details": simulation_target_issues,
            "target_component_ids": sorted(target_component_ids),
        }
    )

    contract_ids = {
        contract["id"]
        for contract in _as_dict_list(contracts_doc.get("contracts", []))
        if "id" in contract
    }
    simulations = _as_dict_list(simulations_doc.get("simulations", [])) if isinstance(simulations_doc, dict) else []

    required_field_issues: list[dict[str, Any]] = []
    legacy_shape_issues: list[dict[str, Any]] = []
    duplicate_ids: list[str] = []
    seen_ids: list[str] = []
    component_coverage: dict[str, list[str]] = {component_id: [] for component_id in target_component_ids}
    bad_component_refs: list[dict[str, Any]] = []
    interface_issues: list[dict[str, Any]] = []
    usage_issues: list[dict[str, Any]] = []
    artifact_issues: list[dict[str, Any]] = []
    path_issues: list[dict[str, Any]] = []
    compile_results: list[dict[str, Any]] = []

    for simulation in simulations:
        simulation_id = str(simulation.get("id", "(missing-id)"))
        seen_ids.append(simulation_id)
        missing = sorted(REQUIRED_SIMULATION_FIELDS - set(simulation.keys()))
        if missing:
            required_field_issues.append({"simulation_id": simulation_id, "missing_fields": missing})
        legacy_fields = sorted(LEGACY_CONTRACT_SCENARIO_FIELDS & set(simulation.keys()))
        if legacy_fields:
            legacy_shape_issues.append({"simulation_id": simulation_id, "legacy_fields": legacy_fields})

        component_ref = simulation.get("component_ref")
        if component_ref in component_coverage:
            component_coverage[str(component_ref)].append(simulation_id)
        elif component_ref not in components:
            bad_component_refs.append(
                {"simulation_id": simulation_id, "component_ref": component_ref, "issue": "unknown_component"}
            )
        else:
            bad_component_refs.append(
                {"simulation_id": simulation_id, "component_ref": component_ref, "issue": "component_not_marked_simulation_target"}
            )

        interface = simulation.get("interface", {})
        implementation = simulation.get("implementation", {})
        if not isinstance(interface, dict):
            interface_issues.append({"simulation_id": simulation_id, "issue": "interface_must_be_mapping"})
            interface = {}
        if not isinstance(implementation, dict):
            interface_issues.append({"simulation_id": simulation_id, "issue": "implementation_must_be_mapping"})
            implementation = {}

        missing_interface = sorted(REQUIRED_INTERFACE_FIELDS - set(interface.keys()))
        if missing_interface:
            interface_issues.append(
                {
                    "simulation_id": simulation_id,
                    "issue": "missing_interface_fields",
                    "missing_fields": missing_interface,
                }
            )
        missing_implementation = sorted(REQUIRED_IMPLEMENTATION_FIELDS - set(implementation.keys()))
        if missing_implementation:
            interface_issues.append(
                {"simulation_id": simulation_id, "issue": "missing_implementation_fields", "missing_fields": missing_implementation}
            )
        if (
            interface.get("symbol")
            and implementation.get("implements")
            and interface.get("symbol") != implementation.get("implements")
        ):
            interface_issues.append(
                {
                    "simulation_id": simulation_id,
                    "issue": "implementation_does_not_name_interface_symbol",
                    "interface_symbol": interface.get("symbol"),
                    "implements": implementation.get("implements"),
                }
            )
        contract_refs = interface.get("contract_refs", [])
        if not isinstance(contract_refs, list) or not contract_refs:
            interface_issues.append({"simulation_id": simulation_id, "issue": "missing_contract_refs"})
        else:
            unknown_contract_refs = sorted(ref for ref in contract_refs if ref not in contract_ids)
            if unknown_contract_refs:
                interface_issues.append(
                    {"simulation_id": simulation_id, "issue": "unknown_contract_refs", "contract_refs": unknown_contract_refs}
                )

        integration_scenarios = simulation.get("integration_scenarios", [])
        if not isinstance(integration_scenarios, list) or not integration_scenarios:
            interface_issues.append({"simulation_id": simulation_id, "issue": "missing_integration_scenarios"})

        declared_artifact_paths: set[str] = set()
        artifacts = simulation.get("artifacts", [])
        if not isinstance(artifacts, list) or not artifacts:
            artifact_issues.append({"simulation_id": simulation_id, "issue": "missing_artifacts"})
        else:
            for artifact_index, artifact in enumerate(artifacts):
                if not isinstance(artifact, dict):
                    artifact_issues.append(
                        {
                            "simulation_id": simulation_id,
                            "artifact_index": artifact_index,
                            "issue": "artifact_must_be_mapping",
                        }
                    )
                    continue
                missing_artifact_fields = sorted(REQUIRED_ARTIFACT_FIELDS - set(artifact.keys()))
                if missing_artifact_fields:
                    artifact_issues.append(
                        {
                            "simulation_id": simulation_id,
                            "artifact_index": artifact_index,
                            "issue": "missing_artifact_fields",
                            "missing_fields": missing_artifact_fields,
                        }
                    )
                raw_artifact_path = artifact.get("path")
                if _is_non_empty_string(raw_artifact_path):
                    declared_artifact_paths.add(str(raw_artifact_path))
                for field in ("role", "description", "phase_6_usage"):
                    if not _is_non_empty_string(artifact.get(field)):
                        artifact_issues.append(
                            {
                                "simulation_id": simulation_id,
                                "artifact_index": artifact_index,
                                "issue": f"blank_artifact_{field}",
                            }
                        )
                status = _path_status(workspace_root, raw_artifact_path)
                if not status.get("exists"):
                    path_issues.append(
                        {
                            "simulation_id": simulation_id,
                            "role": f"artifact:{artifact.get('role', artifact_index)}",
                            **status,
                        }
                    )
        for declared_role, declared_path in (
            ("interface", interface.get("path")),
            ("implementation", implementation.get("path")),
        ):
            if _is_non_empty_string(declared_path) and declared_path not in declared_artifact_paths:
                artifact_issues.append(
                    {
                        "simulation_id": simulation_id,
                        "issue": "declared_source_missing_from_artifacts",
                        "role": declared_role,
                        "path": declared_path,
                    }
                )

        usage = simulation.get("usage", {})
        if not isinstance(usage, dict):
            usage_issues.append({"simulation_id": simulation_id, "issue": "usage_must_be_mapping"})
            usage = {}
        missing_usage_fields = sorted(REQUIRED_USAGE_FIELDS - set(usage.keys()))
        if missing_usage_fields:
            usage_issues.append(
                {
                    "simulation_id": simulation_id,
                    "issue": "missing_usage_fields",
                    "missing_fields": missing_usage_fields,
                }
            )
        mode = usage.get("mode")
        if mode not in USAGE_MODES:
            usage_issues.append(
                {
                    "simulation_id": simulation_id,
                    "issue": "invalid_usage_mode",
                    "mode": mode,
                    "allowed_modes": sorted(USAGE_MODES),
                }
            )
        for field in ("instructions", "integration_reference", "retirement"):
            if not _is_non_empty_string(usage.get(field)):
                usage_issues.append(
                    {"simulation_id": simulation_id, "issue": f"blank_usage_{field}"}
                )
        if not isinstance(usage.get("configuration"), dict):
            usage_issues.append({"simulation_id": simulation_id, "issue": "configuration_must_be_mapping"})
        if not isinstance(usage.get("startup"), list):
            usage_issues.append({"simulation_id": simulation_id, "issue": "startup_must_be_list"})

        documentation = usage.get("documentation", {})
        if not isinstance(documentation, dict):
            usage_issues.append({"simulation_id": simulation_id, "issue": "documentation_must_be_mapping"})
            documentation = {}
        missing_documentation_fields = sorted(
            REQUIRED_USAGE_DOCUMENTATION_FIELDS - set(documentation.keys())
        )
        if missing_documentation_fields:
            usage_issues.append(
                {
                    "simulation_id": simulation_id,
                    "issue": "missing_usage_documentation_fields",
                    "missing_fields": missing_documentation_fields,
                }
            )
        documentation_location = documentation.get("location")
        documentation_path = documentation.get("path")
        if documentation_location not in USAGE_DOCUMENTATION_LOCATIONS:
            usage_issues.append(
                {
                    "simulation_id": simulation_id,
                    "issue": "invalid_usage_documentation_location",
                    "location": documentation_location,
                    "allowed_locations": sorted(USAGE_DOCUMENTATION_LOCATIONS),
                }
            )
        documentation_status = _path_status(workspace_root, documentation_path)
        if not documentation_status.get("exists"):
            path_issues.append(
                {
                    "simulation_id": simulation_id,
                    "role": "usage_documentation",
                    **documentation_status,
                }
            )
        if _is_non_empty_string(documentation_path) and documentation_path not in declared_artifact_paths:
            artifact_issues.append(
                {
                    "simulation_id": simulation_id,
                    "issue": "usage_documentation_missing_from_artifacts",
                    "path": documentation_path,
                }
            )

        for path_role, raw_path in (
            ("interface", interface.get("path")),
            ("implementation", implementation.get("path")),
        ):
            status = _path_status(workspace_root, raw_path)
            if not status.get("exists"):
                path_issues.append({"simulation_id": simulation_id, "role": path_role, **status})

        compile_commands = simulation.get("compile_commands", [])
        if not isinstance(compile_commands, list) or not compile_commands:
            interface_issues.append({"simulation_id": simulation_id, "issue": "missing_compile_commands"})
        else:
            for command in compile_commands:
                if not isinstance(command, str) or not command.strip():
                    compile_results.append(
                        {"simulation_id": simulation_id, "command": command, "status": "fail", "issue": "blank_compile_command"}
                    )
                    continue
                compile_results.append({"simulation_id": simulation_id, **_run_command(command, workspace_root)})

    duplicate_ids = sorted(
        simulation_id for simulation_id in set(seen_ids) if seen_ids.count(simulation_id) > 1
    )
    missing_target_coverage = sorted(component_id for component_id, sim_ids in component_coverage.items() if not sim_ids)

    checks.append(
        {
            "id": "simulation_required_fields",
            "status": "pass" if not required_field_issues and not duplicate_ids else "fail",
            "details": required_field_issues,
            "duplicate_simulation_ids": duplicate_ids,
        }
    )
    checks.append(
        {
            "id": "legacy_contract_scenario_shape",
            "status": "pass" if not legacy_shape_issues else "fail",
            "details": legacy_shape_issues,
        }
    )
    checks.append(
        {
            "id": "component_target_coverage",
            "status": "pass" if not missing_target_coverage and not bad_component_refs else "fail",
            "missing_target_component_refs": missing_target_coverage,
            "bad_component_refs": bad_component_refs,
            "coverage": component_coverage,
        }
    )
    checks.append(
        {
            "id": "interface_implementation_contract",
            "status": "pass" if not interface_issues else "fail",
            "details": interface_issues,
        }
    )
    checks.append(
        {
            "id": "simulation_usage_documentation",
            "status": "pass" if not usage_issues else "fail",
            "details": usage_issues,
        }
    )
    checks.append(
        {
            "id": "simulation_artifact_list",
            "status": "pass" if not artifact_issues else "fail",
            "details": artifact_issues,
        }
    )
    checks.append(
        {
            "id": "simulation_file_paths",
            "status": "pass" if not path_issues else "fail",
            "details": path_issues,
            "workspace_root": str(workspace_root),
        }
    )
    failed_compile_results = [result for result in compile_results if result.get("status") != "pass"]
    checks.append(
        {
            "id": "compile_commands",
            "status": "pass" if not failed_compile_results else "fail",
            "details": compile_results,
        }
    )

    feature_ids = {
        feature["id"]
        for feature in _as_dict_list(feature_spec.get("features", []))
        if "id" in feature
    }
    checks.append(
        {
            "id": "feature_context",
            "status": "pass" if feature_ids else "fail",
            "details": sorted(feature_ids),
        }
    )

    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {
        "validator": "phase_5_validation",
        "overall_status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--architecture", default="docs/architecture/architecture-design.yaml")
    parser.add_argument("--contracts", default="docs/design/interface-contracts.yaml")
    parser.add_argument("--feature-spec", default="docs/features/feature-specification.yaml")
    parser.add_argument("--simulations", default="docs/simulations/simulation-definitions.yaml")
    args = parser.parse_args(argv)
    try:
        report = build_report(
            Path(args.architecture),
            Path(args.contracts),
            Path(args.feature_spec),
            Path(args.simulations),
        )
    except Exception as exc:
        print(
            json.dumps(
                {"validator": "phase_5_validation", "overall_status": "error", "error": str(exc)},
                indent=2,
            )
        )
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
