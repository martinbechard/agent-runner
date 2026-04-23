from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


_METHODOLOGY_SELF_VALIDATION_MARKERS = (
    "methodology_runner.phase_7_validation",
)


def _iter_prompt_blocks(workflow_text: str) -> list[str]:
    matches = list(
        re.finditer(r"(?m)^## Prompt \d+: .+$", workflow_text)
    )
    if not matches:
        return []
    blocks: list[str] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(workflow_text)
        blocks.append(workflow_text[start:end])
    return blocks


def _workflow_has_final_verification_prompt(workflow_text: str) -> bool:
    prompt_blocks = _iter_prompt_blocks(workflow_text)
    if not prompt_blocks:
        return False
    last_prompt = prompt_blocks[-1].lower()
    indicators = (
        "final verification",
        "full verification",
        "verification commands",
        "prompt-3-final-verification-report.md",
        "preserve the final command evidence",
    )
    return any(indicator in last_prompt for indicator in indicators)


def _is_methodology_self_validation_command(command: object) -> bool:
    if not isinstance(command, str):
        return False
    return any(marker in command for marker in _METHODOLOGY_SELF_VALIDATION_MARKERS)


def build_report(
    feature_spec_path: Path,
    requirements_inventory_path: Path,
    implementation_workflow_path: Path,
    implementation_run_report_path: Path,
    verification_report_path: Path,
) -> dict:
    feature_spec = _load_yaml(feature_spec_path)
    requirements_inventory = _load_yaml(requirements_inventory_path)
    implementation_workflow = implementation_workflow_path.read_text(encoding="utf-8")
    implementation_run_report = _load_yaml(implementation_run_report_path)
    report = _load_yaml(verification_report_path)

    checks = []
    actual_keys = list(report.keys()) if isinstance(report, dict) else []
    expected_keys = ["verification_commands", "requirement_results", "coverage_summary"]
    checks.append(
        {
            "id": "top_level_keys",
            "status": "pass" if actual_keys == expected_keys else "fail",
            "actual": actual_keys,
        }
    )

    feature_ids = {feature["id"] for feature in feature_spec.get("features", [])}
    ri_ids = {item["id"] for item in requirements_inventory.get("items", [])}

    command_rows = report.get("verification_commands", [])
    command_issues = []
    self_validation_commands = []
    for row in command_rows:
        missing = sorted({"command", "exit_code", "purpose", "evidence"} - set(row.keys()))
        if missing:
            command_issues.append({"command": row.get("command"), "missing": missing})
        if _is_methodology_self_validation_command(row.get("command")):
            self_validation_commands.append(row.get("command"))
    checks.append(
        {
            "id": "verification_commands_shape",
            "status": "pass" if not command_issues else "fail",
            "details": command_issues,
        }
    )
    checks.append(
        {
            "id": "verification_commands_workspace_scope",
            "status": "pass" if not self_validation_commands else "fail",
            "details": self_validation_commands,
        }
    )

    workflow_completion_ok = implementation_run_report.get("completion_status") == "completed"
    checks.append(
        {
            "id": "child_run_completed",
            "status": "pass" if workflow_completion_ok else "fail",
            "actual": implementation_run_report.get("completion_status"),
        }
    )

    if not _workflow_has_final_verification_prompt(implementation_workflow):
        checks.append({"id": "workflow_final_verification_prompt", "status": "fail"})
    else:
        checks.append({"id": "workflow_final_verification_prompt", "status": "pass"})

    rows = report.get("requirement_results", [])
    row_issues = []
    seen_ris = set()
    status_counts = {"satisfied": 0, "partial": 0, "unsatisfied": 0}
    report_commands = {row.get("command") for row in command_rows if row.get("command")}
    for row in rows:
        ri = row.get("inventory_ref")
        seen_ris.add(ri)
        if ri not in ri_ids:
            row_issues.append({"inventory_ref": ri, "issue": "unknown_inventory_ref"})
        for ft in row.get("feature_refs", []):
            if ft not in feature_ids:
                row_issues.append({"inventory_ref": ri, "issue": "bad_feature_ref", "value": ft})
        status = row.get("status")
        if status not in status_counts:
            row_issues.append({"inventory_ref": ri, "issue": "bad_status", "value": status})
        else:
            status_counts[status] += 1
        evidence = row.get("evidence")
        if not isinstance(evidence, dict):
            row_issues.append({"inventory_ref": ri, "issue": "missing_evidence_block"})
            continue
        missing_evidence = sorted({"files", "commands", "notes"} - set(evidence.keys()))
        if missing_evidence:
            row_issues.append(
                {
                    "inventory_ref": ri,
                    "issue": "bad_evidence_shape",
                    "missing": missing_evidence,
                }
            )
        for command in evidence.get("commands") or []:
            if command not in report_commands:
                row_issues.append(
                    {
                        "inventory_ref": ri,
                        "issue": "evidence_command_not_declared",
                        "value": command,
                    }
                )
        if status == "satisfied":
            files = evidence.get("files") or []
            commands = evidence.get("commands") or []
            if not files and not commands:
                row_issues.append({"inventory_ref": ri, "issue": "satisfied_without_evidence"})
    missing_rows = sorted(ri_ids - seen_ris)
    checks.append(
        {
            "id": "requirement_results_rows",
            "status": "pass" if not row_issues and not missing_rows else "fail",
            "details": row_issues,
            "missing_inventory_refs": missing_rows,
        }
    )

    summary = report.get("coverage_summary", {})
    summary_ok = (
        summary.get("total_requirements") == len(ri_ids)
        and summary.get("satisfied") == status_counts["satisfied"]
        and summary.get("partial") == status_counts["partial"]
        and summary.get("unsatisfied") == status_counts["unsatisfied"]
    )
    checks.append(
        {
            "id": "coverage_summary",
            "status": "pass" if summary_ok else "fail",
            "actual": summary,
        }
    )

    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {
        "validator": "phase_7_validation",
        "overall_status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-spec", default="docs/features/feature-specification.yaml")
    parser.add_argument("--requirements-inventory", default="docs/requirements/requirements-inventory.yaml")
    parser.add_argument("--implementation-workflow", default="docs/implementation/implementation-workflow.md")
    parser.add_argument("--implementation-run-report", default="docs/implementation/implementation-run-report.yaml")
    parser.add_argument("--verification-report", default="docs/verification/verification-report.yaml")
    args = parser.parse_args(argv)
    try:
        report = build_report(
            Path(args.feature_spec),
            Path(args.requirements_inventory),
            Path(args.implementation_workflow),
            Path(args.implementation_run_report),
            Path(args.verification_report),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "validator": "phase_7_validation",
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
