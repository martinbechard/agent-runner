from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_report(contracts_path: Path, simulations_path: Path, feature_spec_path: Path, solution_design_path: Path, plan_path: Path) -> dict:
    contracts_doc = _load_yaml(contracts_path)
    simulations_doc = _load_yaml(simulations_path)
    feature_spec = _load_yaml(feature_spec_path)
    solution_design = _load_yaml(solution_design_path)
    plan = _load_yaml(plan_path)

    checks = []
    actual_keys = list(plan.keys()) if isinstance(plan, dict) else []
    expected_keys = ["build_order", "unit_test_plan", "integration_test_plan", "simulation_replacement_sequence"]
    checks.append({"id": "top_level_keys", "status": "pass" if actual_keys == expected_keys else "fail", "actual": actual_keys})

    component_ids = [component["id"] for component in solution_design.get("components", [])]
    contract_ids = {contract["id"] for contract in contracts_doc.get("contracts", [])}
    sim_ids = {simulation["id"] for simulation in simulations_doc.get("simulations", [])}
    ac_ids = {ac["id"] for feature in feature_spec.get("features", []) for ac in feature.get("acceptance_criteria", [])}

    build_steps = plan.get("build_order", [])
    built_components = [step.get("component_ref") for step in build_steps]
    missing_components = [component_id for component_id in component_ids if component_id not in built_components]
    checks.append({"id": "component_build_coverage", "status": "pass" if not missing_components else "fail", "missing_components": missing_components})

    dep_map = {component["id"]: component.get("dependencies", []) for component in solution_design.get("components", [])}
    step_index = {step.get("component_ref"): step.get("step") for step in build_steps}
    ordering_issues = []
    for component_id, deps in dep_map.items():
        for dep in deps:
            if component_id in step_index and dep in step_index and step_index[dep] >= step_index[component_id]:
                ordering_issues.append({"component_ref": component_id, "dependency": dep})
    checks.append({"id": "dependency_order", "status": "pass" if not ordering_issues else "fail", "details": ordering_issues})

    planned_contracts = {contract_id for step in build_steps for contract_id in step.get("contracts_implemented", [])}
    missing_contracts = sorted(contract_ids - planned_contracts)
    checks.append({"id": "contract_coverage", "status": "pass" if not missing_contracts else "fail", "missing_contracts": missing_contracts})

    referenced_acs = {
        ac_id
        for entry in plan.get("unit_test_plan", [])
        for test in entry.get("tests", [])
        for ac_id in test.get("acceptance_criteria_refs", [])
    }
    integration_sims = {sim_id for test in plan.get("integration_test_plan", []) for sim_id in test.get("scenarios_from", [])}
    missing_acs = sorted(ac_ids - referenced_acs)
    checks.append({"id": "acceptance_criteria_coverage", "status": "pass" if not missing_acs else "fail", "missing_acceptance_criteria": missing_acs})

    replacement_refs = {entry.get("simulation_ref") for entry in plan.get("simulation_replacement_sequence", [])}
    missing_sims = sorted(sim_ids - replacement_refs)
    checks.append({"id": "simulation_replacement_coverage", "status": "pass" if not missing_sims else "fail", "missing_simulations": missing_sims})

    rerun_issues = []
    for entry in plan.get("simulation_replacement_sequence", []):
        if not entry.get("integration_tests_to_rerun"):
            rerun_issues.append({"simulation_ref": entry.get("simulation_ref"), "issue": "missing_reruns"})
        if entry.get("simulation_ref") not in integration_sims:
            rerun_issues.append({"simulation_ref": entry.get("simulation_ref"), "issue": "simulation_not_used_in_integration_tests"})
    checks.append({"id": "simulation_rerun_links", "status": "pass" if not rerun_issues else "fail", "details": rerun_issues})

    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {"validator": "phase_6_validation", "overall_status": "pass" if not failed else "fail", "failed_checks": failed, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contracts", default="docs/design/interface-contracts.yaml")
    parser.add_argument("--simulations", default="docs/simulations/simulation-definitions.yaml")
    parser.add_argument("--feature-spec", default="docs/features/feature-specification.yaml")
    parser.add_argument("--solution-design", default="docs/design/solution-design.yaml")
    parser.add_argument("--implementation-plan", default="docs/implementation/implementation-plan.yaml")
    args = parser.parse_args(argv)
    try:
        report = build_report(Path(args.contracts), Path(args.simulations), Path(args.feature_spec), Path(args.solution_design), Path(args.implementation_plan))
    except Exception as exc:
        print(json.dumps({"validator": "phase_6_validation", "overall_status": "error", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
