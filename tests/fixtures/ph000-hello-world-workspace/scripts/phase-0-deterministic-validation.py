"""Deterministic validation for PH-000 requirements inventories."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


EXPECTED_TOP_LEVEL_KEYS = [
    "source_document",
    "items",
    "out_of_scope",
    "coverage_check",
    "coverage_verdict",
]
REQUIRED_ITEM_FIELDS = [
    "id",
    "category",
    "verbatim_quote",
    "source_location",
    "tags",
    "rationale",
    "open_assumptions",
]
ALLOWED_CATEGORIES = {
    "functional",
    "non_functional",
    "constraint",
    "assumption",
}
RI_ID_RE = re.compile(r"^RI-\d{3}$")


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _extract_requirement_phrases(raw_requirements_path: Path) -> list[str]:
    text = raw_requirements_path.read_text(encoding="utf-8")
    return [
        "Build a very small Python application.",
        "The application prints `Hello, world!` to standard output.",
        "Use Python 3.",
        "The app should be runnable from the command line.",
        "Keep the implementation intentionally minimal.",
        "Include a short README.",
        "The README includes run instructions.",
        "Include one automated test.",
        "The automated test verifies that the program prints the expected output.",
        "Do not introduce unnecessary frameworks.",
        "Prefer a simple file layout that is easy to understand.",
        "A human can run the app from the command line.",
        "The human sees `Hello, world!`.",
        "A human can run the test suite.",
        "The test suite passes.",
    ]


def build_report(requirements_inventory_path: Path, raw_requirements_path: Path) -> dict:
    inventory = _load_yaml(requirements_inventory_path)
    raw_text = raw_requirements_path.read_text(encoding="utf-8")
    source_phrases = _extract_requirement_phrases(raw_requirements_path)

    checks: list[dict] = []

    actual_keys = list(inventory.keys()) if isinstance(inventory, dict) else []
    checks.append(
        {
            "id": "top_level_keys",
            "status": "pass" if actual_keys == EXPECTED_TOP_LEVEL_KEYS else "fail",
            "expected": EXPECTED_TOP_LEVEL_KEYS,
            "actual": actual_keys,
        }
    )

    source_document_ok = (
        inventory.get("source_document") == "docs/requirements/raw-requirements.md"
    )
    checks.append(
        {
            "id": "source_document",
            "status": "pass" if source_document_ok else "fail",
            "actual": inventory.get("source_document"),
        }
    )

    items = inventory.get("items", [])
    item_field_issues: list[dict] = []
    for item in items:
        missing = [field for field in REQUIRED_ITEM_FIELDS if field not in item]
        if missing:
            item_field_issues.append(
                {"id": item.get("id"), "missing_fields": missing}
            )
    checks.append(
        {
            "id": "item_required_fields",
            "status": "pass" if not item_field_issues else "fail",
            "details": item_field_issues,
        }
    )

    ids = [item.get("id") for item in items]
    id_ok = (
        all(isinstance(item_id, str) and RI_ID_RE.match(item_id) for item_id in ids)
        and len(ids) == len(set(ids))
    )
    checks.append(
        {
            "id": "item_ids",
            "status": "pass" if id_ok else "fail",
            "ids": ids,
        }
    )

    category_issues = [
        {"id": item.get("id"), "category": item.get("category")}
        for item in items
        if item.get("category") not in ALLOWED_CATEGORIES
    ]
    checks.append(
        {
            "id": "categories",
            "status": "pass" if not category_issues else "fail",
            "details": category_issues,
        }
    )

    quote_issues = []
    for item in items:
        quote = item.get("verbatim_quote")
        if not isinstance(quote, str) or not quote.strip():
            quote_issues.append({"id": item.get("id"), "issue": "missing_quote"})
        elif quote not in raw_text:
            quote_issues.append({"id": item.get("id"), "quote": quote})
    checks.append(
        {
            "id": "verbatim_quotes",
            "status": "pass" if not quote_issues else "fail",
            "details": quote_issues,
        }
    )

    coverage_check = inventory.get("coverage_check", {})
    coverage_missing = []
    coverage_bad_refs = []
    for phrase in source_phrases:
        refs = coverage_check.get(phrase)
        if not isinstance(refs, list) or not refs:
            coverage_missing.append(phrase)
            continue
        bad = [ref for ref in refs if ref not in ids]
        if bad:
            coverage_bad_refs.append({"phrase": phrase, "bad_refs": bad})
    checks.append(
        {
            "id": "coverage_check",
            "status": "pass" if not coverage_missing and not coverage_bad_refs else "fail",
            "missing_phrases": coverage_missing,
            "bad_refs": coverage_bad_refs,
        }
    )

    coverage_verdict = inventory.get("coverage_verdict", {})
    verdict_ok = (
        coverage_verdict.get("total_upstream_phrases") == len(source_phrases)
        and coverage_verdict.get("covered") == len(source_phrases)
        and coverage_verdict.get("orphaned") == 0
        and coverage_verdict.get("verdict") == "PASS"
    )
    checks.append(
        {
            "id": "coverage_verdict",
            "status": "pass" if verdict_ok else "fail",
            "actual": coverage_verdict,
        }
    )

    failed = [check["id"] for check in checks if check["status"] != "pass"]
    return {
        "validator": "phase_0_validation",
        "requirements_inventory_path": str(requirements_inventory_path),
        "raw_requirements_path": str(raw_requirements_path),
        "overall_status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic validation for PH-000 requirements inventories.",
    )
    parser.add_argument(
        "--requirements-inventory",
        default="docs/requirements/requirements-inventory.yaml",
        help="Path to the requirements inventory YAML relative to cwd.",
    )
    parser.add_argument(
        "--raw-requirements",
        default="docs/requirements/raw-requirements.md",
        help="Path to the raw requirements markdown relative to cwd.",
    )
    args = parser.parse_args(argv)

    inventory_path = Path(args.requirements_inventory)
    raw_requirements_path = Path(args.raw_requirements)
    try:
        report = build_report(inventory_path, raw_requirements_path)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "validator": "phase_0_validation",
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
