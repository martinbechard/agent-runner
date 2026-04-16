from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_report(contracts_path: Path, feature_spec_path: Path, simulations_path: Path) -> dict:
    contracts_doc = _load_yaml(contracts_path)
    feature_spec = _load_yaml(feature_spec_path)
    simulations_doc = _load_yaml(simulations_path)

    checks = []
    actual_keys = list(simulations_doc.keys()) if isinstance(simulations_doc, dict) else []
    checks.append({"id": "top_level_keys", "status": "pass" if actual_keys == ["simulations"] else "fail", "actual": actual_keys})

    contract_ids = {contract["id"] for contract in contracts_doc.get("contracts", [])}
    simulations = simulations_doc.get("simulations", [])
    required_fields = {"id", "contract_ref", "description", "scenario_bank", "llm_adjuster", "validation_rules"}
    missing_fields = []
    coverage = {contract_id: 0 for contract_id in contract_ids}
    scenario_gaps = []
    assertion_gaps = []
    bad_refs = []
    for simulation in simulations:
        missing = sorted(required_fields - set(simulation.keys()))
        if missing:
            missing_fields.append({"simulation_id": simulation.get("id"), "missing_fields": missing})
        contract_ref = simulation.get("contract_ref")
        if contract_ref in coverage:
            coverage[contract_ref] += 1
        else:
            bad_refs.append({"simulation_id": simulation.get("id"), "contract_ref": contract_ref})
        seen_types = {scenario.get("type") for scenario in simulation.get("scenario_bank", [])}
        for required_type in ("happy_path", "error_path", "edge_case"):
            if required_type not in seen_types:
                scenario_gaps.append({"simulation_id": simulation.get("id"), "missing_type": required_type})
        for scenario in simulation.get("scenario_bank", []):
            if not scenario.get("assertions"):
                assertion_gaps.append({"simulation_id": simulation.get("id"), "scenario": scenario.get("name")})
    missing_contracts = [contract_id for contract_id, count in coverage.items() if count == 0]
    checks.append({"id": "simulation_required_fields", "status": "pass" if not missing_fields else "fail", "details": missing_fields})
    checks.append({"id": "contract_coverage", "status": "pass" if not missing_contracts else "fail", "missing_contracts": missing_contracts})
    checks.append({"id": "scenario_type_coverage", "status": "pass" if not scenario_gaps else "fail", "details": scenario_gaps})
    checks.append({"id": "assertion_presence", "status": "pass" if not assertion_gaps else "fail", "details": assertion_gaps})
    checks.append({"id": "reference_validity", "status": "pass" if not bad_refs else "fail", "details": bad_refs})

    feature_ids = {feature["id"] for feature in feature_spec.get("features", [])}
    checks.append({"id": "feature_context", "status": "pass" if feature_ids else "fail", "details": sorted(feature_ids)})

    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {"validator": "phase_5_validation", "overall_status": "pass" if not failed else "fail", "failed_checks": failed, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contracts", default="docs/design/interface-contracts.yaml")
    parser.add_argument("--feature-spec", default="docs/features/feature-specification.yaml")
    parser.add_argument("--simulations", default="docs/simulations/simulation-definitions.yaml")
    args = parser.parse_args(argv)
    try:
        report = build_report(Path(args.contracts), Path(args.feature_spec), Path(args.simulations))
    except Exception as exc:
        print(json.dumps({"validator": "phase_5_validation", "overall_status": "error", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
