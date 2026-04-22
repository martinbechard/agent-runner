from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


_WORKFLOW_MODULE_RE = re.compile(r"^### Module\s*$", re.MULTILINE)
_PROMPT_HEADING_RE = re.compile(r"^##\s+Prompt\b", re.MULTILINE)
_LEVEL3_RE = re.compile(r"^###\s+(.+?)\s*$")
_MARKDOWN_LIST_RE = re.compile(r"^(?:[-+*]|\d+\.)\s+")
_LOOSE_TDD_RE = re.compile(r"failing\s+or\s+tighten(?:ed|ing)?[-\s]test")
_ASSUMED_BASELINE_RE = re.compile(r"from the current .+? behavior", re.IGNORECASE)


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


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _validate_workflow_prompt(path: Path) -> dict:
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
    bad_path_entries = _bad_path_metadata_entries(text)
    checks.append(
        {
            "id": "path_metadata_entries_plain",
            "status": "pass" if not bad_path_entries else "fail",
            "details": bad_path_entries,
        }
    )

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
) -> dict:
    checks = [_validate_workflow_prompt(workflow_prompt_path)]
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
    parser.add_argument("--check-run-report", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_report(
            Path(args.workflow_prompt),
            Path(args.run_report),
            check_run_report=args.check_run_report,
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
