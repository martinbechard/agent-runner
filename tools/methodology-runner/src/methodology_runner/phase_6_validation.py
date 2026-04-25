from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


_WORKFLOW_MODULE_RE = re.compile(r"^### Module\s*$", re.MULTILINE)
_PROMPT_HEADING_RE = re.compile(r"^##\s+Prompt\b", re.MULTILINE)
_PROMPT_TITLE_RE = re.compile(r"^##\s+Prompt\s+(\d+):\s+(.+?)\s*$")
_LEVEL3_RE = re.compile(r"^###\s+(.+?)\s*$")
_MARKDOWN_LIST_RE = re.compile(r"^(?:[-+*]|\d+\.)\s+")
_LOOSE_TDD_RE = re.compile(r"failing\s+or\s+tighten(?:ed|ing)?[-\s]test")
_ASSUMED_BASELINE_RE = re.compile(r"from the current .+? behavior", re.IGNORECASE)


def _has_delivery_quality_signal(lower_text: str) -> bool:
    file_comment = "file-level" in lower_text or "file comment" in lower_text
    type_comment = "type-level" in lower_text or "type comment" in lower_text
    function_comment = "function-level" in lower_text or "function comment" in lower_text
    comments = "comment" in lower_text or "docstring" in lower_text
    code_quality = (
        file_comment
        and type_comment
        and function_comment
        and comments
        and ("best practice" in lower_text or "project-local" in lower_text)
    )
    steady_state_docs = (
        "steady-state" in lower_text
        and ("documentation" in lower_text or "docs" in lower_text)
        and (
            "previous state" in lower_text
            or "older" in lower_text
            or "previous behavior" in lower_text
            or "prior behavior" in lower_text
        )
    )
    readme_operations = (
        "readme" in lower_text
        and (
            "setup" in lower_text
            or "installation" in lower_text
            or "prerequisites" in lower_text
        )
        and (
            "operation" in lower_text
            or "operate" in lower_text
            or "run or start" in lower_text
            or "run/start" in lower_text
        )
    )
    return code_quality and steady_state_docs and readme_operations


def _bad_path_metadata_entries(text: str) -> list[dict]:
    lines = text.splitlines()
    active_section: str | None = None
    bad_entries: list[dict] = []
    for line_number, raw_line in enumerate(lines, start=1):
        heading_match = _LEVEL3_RE.match(raw_line)
        if heading_match is not None:
            normalized = " ".join(heading_match.group(1).strip().lower().split())
            if normalized in {"required files", "checks files", "include files"}:
                active_section = heading_match.group(1).strip()
            else:
                active_section = None
            continue
        if raw_line.startswith("## "):
            active_section = None
            continue
        if active_section is None:
            continue
        stripped = raw_line.strip()
        if not stripped:
            continue
        if _MARKDOWN_LIST_RE.match(stripped) or (
            stripped.startswith("`") and stripped.endswith("`") and len(stripped) >= 2
        ):
            bad_entries.append(
                {
                    "line": line_number,
                    "section": active_section,
                    "entry": stripped,
                }
            )
    return bad_entries


def _child_prompt_file_sections(text: str) -> list[dict]:
    prompts: list[dict] = []
    current_prompt: dict | None = None
    active_section: str | None = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        prompt_match = _PROMPT_TITLE_RE.match(raw_line)
        if prompt_match is not None:
            current_prompt = {
                "prompt_index": int(prompt_match.group(1)),
                "title": prompt_match.group(2).strip(),
                "required_files": [],
                "checks_files": [],
            }
            prompts.append(current_prompt)
            active_section = None
            continue

        heading_match = _LEVEL3_RE.match(raw_line)
        if heading_match is not None:
            normalized = " ".join(heading_match.group(1).strip().lower().split())
            active_section = (
                normalized
                if normalized in {"required files", "checks files"}
                else None
            )
            continue

        if raw_line.startswith("## "):
            active_section = None
            continue

        if current_prompt is None or active_section is None:
            continue

        stripped = raw_line.strip()
        if not stripped:
            continue

        entry = {
            "line": line_number,
            "path": stripped,
        }
        if active_section == "required files":
            current_prompt["required_files"].append(entry)
        elif active_section == "checks files":
            current_prompt["checks_files"].append(entry)

    return prompts


def _workflow_workspace_root(path: Path) -> Path:
    resolved = path.resolve()
    if (
        resolved.name == "implementation-workflow.md"
        and resolved.parent.name == "implementation"
        and resolved.parent.parent.name == "docs"
    ):
        return resolved.parent.parent.parent
    return Path.cwd()


def _is_plain_relative_file_path(path_text: str) -> bool:
    if path_text.startswith("`") or _MARKDOWN_LIST_RE.match(path_text):
        return False
    if "{{" in path_text or "}}" in path_text:
        return False
    return not Path(path_text).is_absolute()


def _required_files_available_check(text: str, workflow_path: Path) -> dict:
    workspace_root = _workflow_workspace_root(workflow_path)
    available_paths: set[str] = set()
    missing_entries: list[dict] = []

    for prompt in _child_prompt_file_sections(text):
        for required in prompt["required_files"]:
            path_text = required["path"]
            if not _is_plain_relative_file_path(path_text):
                continue
            if path_text in available_paths:
                continue
            if (workspace_root / path_text).exists():
                available_paths.add(path_text)
                continue
            missing_entries.append(
                {
                    "prompt_index": prompt["prompt_index"],
                    "title": prompt["title"],
                    "line": required["line"],
                    "path": path_text,
                }
            )

        for checked in prompt["checks_files"]:
            path_text = checked["path"]
            if _is_plain_relative_file_path(path_text):
                available_paths.add(path_text)

    return {
        "id": "required_files_available",
        "status": "pass" if not missing_entries else "fail",
        "workspace_root": str(workspace_root),
        "missing": missing_entries,
    }


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _as_dict_list(value) -> list[dict]:
    """Return mapping items from a YAML list-like value."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _simulation_artifact_usage_check(
    workflow_text: str,
    simulations_path: Path | None,
) -> dict | None:
    """Check that generated workflows name declared simulation artifacts."""
    if simulations_path is None:
        return None
    if not simulations_path.exists():
        return {
            "id": "simulation_artifact_usage_signal",
            "status": "fail",
            "issue": "simulations_file_missing",
            "path": str(simulations_path),
        }
    simulations_doc = _load_yaml(simulations_path) or {}
    simulations = _as_dict_list(simulations_doc.get("simulations", []))
    simulation_ids: list[str] = []
    artifact_paths: list[str] = []
    for simulation in simulations:
        simulation_id = simulation.get("id")
        if isinstance(simulation_id, str) and simulation_id.strip():
            simulation_ids.append(simulation_id)
        for artifact in _as_dict_list(simulation.get("artifacts", [])):
            artifact_path = artifact.get("path")
            if isinstance(artifact_path, str) and artifact_path.strip():
                artifact_paths.append(artifact_path)
    if not simulation_ids and not artifact_paths:
        return {
            "id": "simulation_artifact_usage_signal",
            "status": "pass",
            "simulation_ids": [],
            "artifact_paths": [],
        }
    missing_ids = sorted(sim_id for sim_id in simulation_ids if sim_id not in workflow_text)
    missing_paths = sorted(path for path in artifact_paths if path not in workflow_text)
    return {
        "id": "simulation_artifact_usage_signal",
        "status": "pass" if not missing_ids and not missing_paths else "fail",
        "simulation_ids": sorted(simulation_ids),
        "artifact_paths": sorted(artifact_paths),
        "missing_simulation_ids": missing_ids,
        "missing_artifact_paths": missing_paths,
    }


def _workflow_mentions_artifact_path(
    workflow_text: str,
    artifact_path: str,
    artifact_type: str,
    prompt_sections: list[dict],
) -> bool:
    if artifact_path in workflow_text:
        return True
    normalized = artifact_path.rstrip("/")
    if not normalized:
        return False
    path_name = Path(normalized).name
    directory_like = artifact_type in {"test-suite", "directory"} or "." not in path_name
    if not directory_like:
        return False
    prefix = f"{normalized}/"
    for prompt in prompt_sections:
        for entry in prompt["required_files"] + prompt["checks_files"]:
            if entry["path"].startswith(prefix):
                return True
    return False


def _solution_design_implementation_file_usage_check(
    workflow_text: str,
    solution_design_path: Path | None,
) -> dict | None:
    """Check that PH-006 workflow carries PH-003 implementation file paths forward."""
    if solution_design_path is None:
        return None
    if not solution_design_path.exists():
        return {
            "id": "solution_design_implementation_file_usage_signal",
            "status": "fail",
            "issue": "solution_design_file_missing",
            "path": str(solution_design_path),
        }

    solution_design = _load_yaml(solution_design_path) or {}
    implementation_files = _as_dict_list(solution_design.get("implementation_files", []))
    prompt_sections = _child_prompt_file_sections(workflow_text)
    file_paths: list[dict] = []
    missing_paths: list[dict] = []

    for implementation_file in implementation_files:
        path_value = implementation_file.get("path")
        role = implementation_file.get("role", "")
        artifact_ref = implementation_file.get("artifact_ref")
        if not isinstance(path_value, str) or not path_value.strip():
            continue
        path_text = path_value.strip()
        path_record = {
            "path": path_text,
            "role": role,
            "artifact_ref": artifact_ref,
        }
        file_paths.append(path_record)
        if not _workflow_mentions_artifact_path(
            workflow_text,
            path_text,
            str(role),
            prompt_sections,
        ):
            missing_paths.append(path_record)

    return {
        "id": "solution_design_implementation_file_usage_signal",
        "status": "pass" if not missing_paths else "fail",
        "implementation_file_paths": file_paths,
        "missing_implementation_file_paths": missing_paths,
    }


def _validate_workflow_prompt(
    path: Path,
    simulations_path: Path | None = None,
    solution_design_path: Path | None = None,
) -> dict:
    text = path.read_text(encoding="utf-8")
    lower_text = text.lower()
    checks: list[dict] = []

    checks.append(
        {
            "id": "workflow_exists",
            "status": "pass" if path.exists() else "fail",
        }
    )
    checks.append(
        {
            "id": "module_block_present",
            "status": "pass" if _WORKFLOW_MODULE_RE.search(text) else "fail",
        }
    )
    checks.append(
        {
            "id": "module_slug",
            "status": "pass" if "implementation-workflow" in text else "fail",
        }
    )

    prompt_count = len(_PROMPT_HEADING_RE.findall(text))
    checks.append(
        {
            "id": "prompt_count",
            "status": "pass" if prompt_count >= 2 else "fail",
            "actual_prompt_count": prompt_count,
        }
    )

    checks.append(
        {
            "id": "tdd_signal",
            "status": (
                "pass"
                if (
                    "failing test" in text.lower()
                    or "test first" in text.lower()
                    or "tdd" in text.lower()
                )
                else "fail"
            ),
        }
    )
    checks.append(
        {
            "id": "forbidden_loose_tdd_phrase",
            "status": "fail" if _LOOSE_TDD_RE.search(lower_text) else "pass",
        }
    )
    checks.append(
        {
            "id": "forbidden_assumed_baseline_phrase",
            "status": "fail" if _ASSUMED_BASELINE_RE.search(text) else "pass",
        }
    )
    checks.append(
        {
            "id": "test_execution_signal",
            "status": (
                "pass"
                if (
                    "pytest" in lower_text
                    or "python3 -m unittest" in lower_text
                    or "python -m unittest" in lower_text
                    or "run the relevant tests" in lower_text
                    or "run the relevant test command" in lower_text
                    or "run both the automated test command" in lower_text
                )
                else "fail"
            ),
        }
    )
    checks.append(
        {
            "id": "command_outcome_detail_signal",
            "status": (
                "pass"
                if (
                    "stdout" in lower_text
                    and "stderr" in lower_text
                    and "exit code" in lower_text
                )
                else "fail"
            ),
        }
    )
    checks.append(
        {
            "id": "final_verification_signal",
            "status": (
                "pass"
                if "final verification" in text.lower()
                or "full verification" in text.lower()
                else "fail"
            ),
        }
    )
    checks.append(
        {
            "id": "delivery_quality_signal",
            "status": "pass" if _has_delivery_quality_signal(lower_text) else "fail",
        }
    )
    bad_path_entries = _bad_path_metadata_entries(text)
    checks.append(
        {
            "id": "path_metadata_entries_plain",
            "status": "pass" if not bad_path_entries else "fail",
            "details": bad_path_entries,
        }
    )
    checks.append(_required_files_available_check(text, path))
    simulation_artifact_check = _simulation_artifact_usage_check(text, simulations_path)
    if simulation_artifact_check is not None:
        checks.append(simulation_artifact_check)
    solution_design_file_check = _solution_design_implementation_file_usage_check(
        text,
        solution_design_path,
    )
    if solution_design_file_check is not None:
        checks.append(solution_design_file_check)

    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {
        "id": "workflow_prompt",
        "status": "pass" if not failed else "fail",
        "checks": checks,
    }


def _validate_run_report(workflow_prompt_path: Path, run_report_path: Path) -> dict:
    checks: list[dict] = []
    if not run_report_path.exists():
        return {
            "id": "run_report",
            "status": "fail",
            "checks": [{"id": "run_report_exists", "status": "fail"}],
        }

    report = _load_yaml(run_report_path)
    actual_keys = list(report.keys()) if isinstance(report, dict) else []
    expected_keys = [
        "child_prompt_path",
        "child_run_dir",
        "execution_mode",
        "completion_status",
        "halt_reason",
        "prompt_results",
        "files_changed",
        "test_commands_observed",
        "next_action",
    ]
    checks.append(
        {
            "id": "top_level_keys",
            "status": "pass" if actual_keys == expected_keys else "fail",
            "actual": actual_keys,
        }
    )

    checks.append(
        {
            "id": "child_prompt_path",
            "status": (
                "pass"
                if report.get("child_prompt_path")
                == "docs/implementation/implementation-workflow.md"
                else "fail"
            ),
        }
    )
    checks.append(
        {
            "id": "execution_mode",
            "status": (
                "pass"
                if report.get("execution_mode") in {"fresh", "resume"}
                else "fail"
            ),
            "actual": report.get("execution_mode"),
        }
    )
    checks.append(
        {
            "id": "completion_status",
            "status": (
                "pass"
                if report.get("completion_status") in {"completed", "halted"}
                else "fail"
            ),
            "actual": report.get("completion_status"),
        }
    )

    prompt_results = report.get("prompt_results")
    prompt_results_ok = isinstance(prompt_results, list) and bool(prompt_results)
    checks.append(
        {
            "id": "prompt_results_present",
            "status": "pass" if prompt_results_ok else "fail",
        }
    )

    if prompt_results_ok:
        bad_prompt_rows = []
        for row in prompt_results:
            missing = sorted(
                {"prompt_index", "title", "verdict", "iterations"} - set(row.keys())
            )
            if missing:
                bad_prompt_rows.append(
                    {"prompt_index": row.get("prompt_index"), "missing": missing}
                )
        checks.append(
            {
                "id": "prompt_results_shape",
                "status": "pass" if not bad_prompt_rows else "fail",
                "details": bad_prompt_rows,
            }
        )

    tests = report.get("test_commands_observed")
    tests_ok = isinstance(tests, list)
    checks.append(
        {
            "id": "test_commands_present",
            "status": "pass" if tests_ok else "fail",
        }
    )
    if tests_ok:
        bad_tests = []
        for row in tests:
            missing = sorted(
                {
                    "command",
                    "exit_code",
                    "stdout_excerpt",
                    "stderr_excerpt",
                }
                - set(row.keys())
            )
            if missing:
                bad_tests.append({"command": row.get("command"), "missing": missing})
        checks.append(
            {
                "id": "test_commands_shape",
                "status": "pass" if not bad_tests else "fail",
                "details": bad_tests,
            }
        )

    summary_path = (
        Path(report.get("child_run_dir", "."))
        / ".run-files"
        / "implementation-workflow"
        / "summary.txt"
    )
    summary_exists = summary_path.exists()
    checks.append(
        {
            "id": "child_summary_exists",
            "status": "pass" if summary_exists else "fail",
            "path": str(summary_path),
        }
    )
    if summary_exists:
        summary_text = summary_path.read_text(encoding="utf-8")
        completed = "Status: completed" in summary_text
        expected_completed = report.get("completion_status") == "completed"
        checks.append(
            {
                "id": "summary_matches_report",
                "status": "pass" if completed == expected_completed else "fail",
            }
        )

    all_pass = (
        isinstance(prompt_results, list)
        and prompt_results
        and all(row.get("verdict") == "pass" for row in prompt_results)
    )
    if report.get("completion_status") == "completed":
        checks.append(
            {
                "id": "completed_run_all_pass",
                "status": "pass" if all_pass else "fail",
            }
        )
        checks.append(
            {
                "id": "completed_run_halt_reason_blank",
                "status": "pass" if not report.get("halt_reason") else "fail",
            }
        )
    else:
        checks.append(
            {
                "id": "halted_run_has_reason",
                "status": "pass" if report.get("halt_reason") else "fail",
            }
        )

    checks.append(
        {
            "id": "workflow_prompt_still_exists",
            "status": "pass" if workflow_prompt_path.exists() else "fail",
        }
    )

    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {
        "id": "run_report",
        "status": "pass" if not failed else "fail",
        "checks": checks,
    }


def build_report(
    workflow_prompt_path: Path,
    run_report_path: Path | None = None,
    check_run_report: bool = False,
    simulations_path: Path | None = None,
    solution_design_path: Path | None = None,
) -> dict:
    checks = [
        _validate_workflow_prompt(
            workflow_prompt_path,
            simulations_path,
            solution_design_path,
        )
    ]
    if check_run_report:
        assert run_report_path is not None
        checks.append(_validate_run_report(workflow_prompt_path, run_report_path))
    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {
        "validator": "phase_6_validation",
        "overall_status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workflow-prompt",
        default="docs/implementation/implementation-workflow.md",
    )
    parser.add_argument(
        "--run-report",
        default="docs/implementation/implementation-run-report.yaml",
    )
    parser.add_argument(
        "--simulations",
        default=None,
        help="Optional PH-005 simulation definitions for artifact usage checks.",
    )
    parser.add_argument(
        "--solution-design",
        default=None,
        help="Optional PH-003 solution design for implementation file path checks.",
    )
    parser.add_argument("--check-run-report", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_report(
            Path(args.workflow_prompt),
            Path(args.run_report),
            check_run_report=args.check_run_report,
            simulations_path=Path(args.simulations) if args.simulations else None,
            solution_design_path=(
                Path(args.solution_design) if args.solution_design else None
            ),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "validator": "phase_6_validation",
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
