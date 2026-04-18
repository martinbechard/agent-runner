from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_report(feature_spec_path: Path, implementation_plan_path: Path, solution_design_path: Path, requirements_inventory_path: Path, verification_report_path: Path) -> dict:
    feature_spec = _load_yaml(feature_spec_path)
    implementation_plan = _load_yaml(implementation_plan_path)
    solution_design = _load_yaml(solution_design_path)
    requirements_inventory = _load_yaml(requirements_inventory_path)
    report = _load_yaml(verification_report_path)

    checks = []
    actual_keys = list(report.keys()) if isinstance(report, dict) else []
    expected_keys = ["e2e_tests", "traceability_matrix", "coverage_summary"]
    checks.append({"id": "top_level_keys", "status": "pass" if actual_keys == expected_keys else "fail", "actual": actual_keys})

    feature_ids = {feature["id"] for feature in feature_spec.get("features", [])}
    ac_ids = {ac["id"] for feature in feature_spec.get("features", []) for ac in feature.get("acceptance_criteria", [])}
    ri_ids = {item["id"] for item in requirements_inventory.get("items", [])}
    e2e_ids = {test["id"] for test in report.get("e2e_tests", [])}

    required_e2e_fields = {"id", "name", "feature_ref", "acceptance_criteria_refs", "type", "setup", "actions", "assertions"}
    e2e_field_issues = []
    bad_e2e_refs = []
    for test in report.get("e2e_tests", []):
        missing = sorted(required_e2e_fields - set(test.keys()))
        if missing:
            e2e_field_issues.append({"e2e_id": test.get("id"), "missing_fields": missing})
        if test.get("feature_ref") not in feature_ids:
            bad_e2e_refs.append({"e2e_id": test.get("id"), "feature_ref": test.get("feature_ref")})
        bad_acs = [ac for ac in test.get("acceptance_criteria_refs", []) if ac not in ac_ids]
        if bad_acs:
            bad_e2e_refs.append({"e2e_id": test.get("id"), "bad_acceptance_criteria": bad_acs})
    checks.append({"id": "e2e_required_fields", "status": "pass" if not e2e_field_issues else "fail", "details": e2e_field_issues})
    checks.append({"id": "e2e_reference_validity", "status": "pass" if not bad_e2e_refs else "fail", "details": bad_e2e_refs})

    rows = report.get("traceability_matrix", [])
    row_issues = []
    seen_ris = set()
    status_counts = {"covered": 0, "partial": 0, "uncovered": 0}
    for row in rows:
        ri = row.get("inventory_ref")
        seen_ris.add(ri)
        if ri not in ri_ids:
            row_issues.append({"inventory_ref": ri, "issue": "unknown_inventory_ref"})
        for ft in row.get("feature_refs", []):
            if ft not in feature_ids:
                row_issues.append({"inventory_ref": ri, "issue": "bad_feature_ref", "value": ft})
        for ac in row.get("acceptance_criteria_refs", []):
            if ac not in ac_ids:
                row_issues.append({"inventory_ref": ri, "issue": "bad_acceptance_criteria_ref", "value": ac})
        for e2e in row.get("e2e_test_refs", []):
            if e2e not in e2e_ids:
                row_issues.append({"inventory_ref": ri, "issue": "bad_e2e_ref", "value": e2e})
        status = row.get("coverage_status")
        if status not in status_counts:
            row_issues.append({"inventory_ref": ri, "issue": "bad_status", "value": status})
        else:
            status_counts[status] += 1
            if status == "covered" and (not row.get("feature_refs") or not row.get("acceptance_criteria_refs") or not row.get("e2e_test_refs")):
                row_issues.append({"inventory_ref": ri, "issue": "covered_row_incomplete"})
    missing_rows = sorted(ri_ids - seen_ris)
    checks.append({"id": "traceability_matrix_rows", "status": "pass" if not row_issues and not missing_rows else "fail", "details": row_issues, "missing_inventory_refs": missing_rows})

    summary = report.get("coverage_summary", {})
    summary_ok = (
        summary.get("total_requirements") == len(ri_ids)
        and summary.get("covered") == status_counts["covered"]
        and summary.get("partial") == status_counts["partial"]
        and summary.get("uncovered") == status_counts["uncovered"]
    )
    checks.append({"id": "coverage_summary", "status": "pass" if summary_ok else "fail", "actual": summary})

    unit_tests = {
        test.get("name")
        for entry in implementation_plan.get("unit_test_plan", [])
        for test in entry.get("tests", [])
        if test.get("name")
    }
    integration_tests = {
        test.get("name")
        for test in implementation_plan.get("integration_test_plan", [])
        if test.get("name")
    }
    component_ids = {component["id"] for component in solution_design.get("components", [])}
    has_upstream_test_plan = bool(unit_tests or integration_tests)
    checks.append(
        {
            "id": "upstream_context",
            "status": "pass" if has_upstream_test_plan and component_ids else "fail",
            "details": {
                "unit_tests": sorted(unit_tests),
                "integration_tests": sorted(integration_tests),
                "components": sorted(component_ids),
            },
        }
    )

    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {"validator": "phase_7_validation", "overall_status": "pass" if not failed else "fail", "failed_checks": failed, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-spec", default="docs/features/feature-specification.yaml")
    parser.add_argument("--implementation-plan", default="docs/implementation/implementation-plan.yaml")
    parser.add_argument("--solution-design", default="docs/design/solution-design.yaml")
    parser.add_argument("--requirements-inventory", default="docs/requirements/requirements-inventory.yaml")
    parser.add_argument("--verification-report", default="docs/verification/verification-report.yaml")
    args = parser.parse_args(argv)
    try:
        report = build_report(Path(args.feature_spec), Path(args.implementation_plan), Path(args.solution_design), Path(args.requirements_inventory), Path(args.verification_report))
    except Exception as exc:
        print(json.dumps({"validator": "phase_7_validation", "overall_status": "error", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
