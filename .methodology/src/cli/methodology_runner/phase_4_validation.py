from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _fields_have_holes(fields: list[dict]) -> bool:
    return any(field.get("type") in {"object", "any", "unknown"} for field in fields)


def build_report(solution_design_path: Path, feature_spec_path: Path, contracts_path: Path) -> dict:
    solution = _load_yaml(solution_design_path)
    feature_spec = _load_yaml(feature_spec_path)
    contracts_doc = _load_yaml(contracts_path)

    checks = []
    actual_keys = list(contracts_doc.keys()) if isinstance(contracts_doc, dict) else []
    checks.append({"id": "top_level_keys", "status": "pass" if actual_keys == ["contracts"] else "fail", "actual": actual_keys})

    interactions = {interaction["id"] for interaction in solution.get("interactions", [])}
    components = {component["id"] for component in solution.get("components", [])}
    contracts = contracts_doc.get("contracts", [])

    required_fields = {"id", "name", "interaction_ref", "source_component", "target_component", "operations", "behavioral_specs"}
    missing_contract_fields = []
    interaction_coverage = {interaction_id: 0 for interaction_id in interactions}
    schema_holes = []
    behavior_gaps = []
    bad_refs = []
    for contract in contracts:
        missing = sorted(required_fields - set(contract.keys()))
        if missing:
            missing_contract_fields.append({"contract_id": contract.get("id"), "missing_fields": missing})
        interaction_ref = contract.get("interaction_ref")
        if interaction_ref in interaction_coverage:
            interaction_coverage[interaction_ref] += 1
        else:
            bad_refs.append({"contract_id": contract.get("id"), "interaction_ref": interaction_ref})
        if contract.get("source_component") not in components or contract.get("target_component") not in components:
            bad_refs.append({"contract_id": contract.get("id"), "issue": "unknown_component"})
        if not contract.get("behavioral_specs"):
            behavior_gaps.append(contract.get("id"))
        for op in contract.get("operations", []):
            req_fields = op.get("request_schema", {}).get("fields", [])
            resp_fields = op.get("response_schema", {}).get("fields", [])
            if _fields_have_holes(req_fields) or _fields_have_holes(resp_fields):
                schema_holes.append({"contract_id": contract.get("id"), "operation": op.get("name")})
            if not op.get("error_types"):
                behavior_gaps.append(f"{contract.get('id')}:{op.get('name')}:error_types")

    missing_contracts = [interaction_id for interaction_id, count in interaction_coverage.items() if count == 0]
    checks.append({"id": "contract_required_fields", "status": "pass" if not missing_contract_fields else "fail", "details": missing_contract_fields})
    checks.append({"id": "interaction_coverage", "status": "pass" if not missing_contracts else "fail", "missing_interactions": missing_contracts})
    checks.append({"id": "reference_validity", "status": "pass" if not bad_refs else "fail", "details": bad_refs})
    checks.append({"id": "schema_precision", "status": "pass" if not schema_holes else "fail", "details": schema_holes})
    checks.append({"id": "behavioral_specs", "status": "pass" if not behavior_gaps else "fail", "details": behavior_gaps})

    feature_ids = {feature["id"] for feature in feature_spec.get("features", [])}
    unrelated_refs = []
    for contract in contracts:
        if contract.get("interaction_ref") == "INT-001" and "FT-002" not in feature_ids:
            unrelated_refs.append(contract.get("id"))
    checks.append({"id": "feature_spec_reference_context", "status": "pass" if not unrelated_refs else "fail", "details": unrelated_refs})

    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {"validator": "phase_4_validation", "overall_status": "pass" if not failed else "fail", "failed_checks": failed, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solution-design", default="docs/design/solution-design.yaml")
    parser.add_argument("--feature-spec", default="docs/features/feature-specification.yaml")
    parser.add_argument("--contracts", default="docs/design/interface-contracts.yaml")
    args = parser.parse_args(argv)
    try:
        report = build_report(Path(args.solution_design), Path(args.feature_spec), Path(args.contracts))
    except Exception as exc:
        print(json.dumps({"validator": "phase_4_validation", "overall_status": "error", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
