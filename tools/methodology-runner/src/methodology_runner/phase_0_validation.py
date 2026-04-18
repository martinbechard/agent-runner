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
]
EXPECTED_COVERAGE_TOP_LEVEL_KEYS = [
    "source_document",
    "inventory_document",
    "coverage_check",
    "coverage_verdict",
]
REQUIRED_ITEM_FIELDS = [
    "id",
    "category",
    "verbatim_quote",
    "normalized_requirement",
    "justification",
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


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _extract_requirement_phrases(raw_requirements_path: Path) -> list[str]:
    text = raw_requirements_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    phrases: list[str] = []
    paragraph_lines: list[str] = []
    current_bullet: list[str] | None = None
    in_requirement_section = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        paragraph = _normalize(" ".join(paragraph_lines))
        if paragraph:
            phrases.append(paragraph)
        paragraph_lines = []

    def flush_bullet() -> None:
        nonlocal current_bullet
        if not current_bullet:
            return
        bullet = _normalize(" ".join(current_bullet))
        if bullet:
            phrases.append(bullet)
        current_bullet = None

    for raw_line in lines:
        stripped = raw_line.strip()

        if not stripped:
            flush_paragraph()
            flush_bullet()
            continue

        if stripped.startswith("#"):
            flush_paragraph()
            flush_bullet()
            continue

        if stripped.endswith(":"):
            flush_paragraph()
            flush_bullet()
            in_requirement_section = stripped in {
                "Requirements:",
                "Constraints:",
                "Definition of done:",
            }
            continue

        if raw_line.startswith("- "):
            flush_paragraph()
            flush_bullet()
            if in_requirement_section:
                current_bullet = [raw_line[2:].strip()]
            else:
                paragraph_lines.append(stripped)
            continue

        if current_bullet is not None:
            current_bullet.append(stripped)
            continue

        paragraph_lines.append(stripped)

    flush_paragraph()
    flush_bullet()
    return phrases


def build_report(
    requirements_inventory_path: Path,
    requirements_coverage_path: Path,
    raw_requirements_path: Path,
) -> dict:
    inventory = _load_yaml(requirements_inventory_path)
    coverage = _load_yaml(requirements_coverage_path)
    raw_text = raw_requirements_path.read_text(encoding="utf-8")
    normalized_raw_text = _normalize(raw_text)
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
            "id": "inventory_source_document",
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
    normalized_requirement_issues = []
    justification_issues = []
    for item in items:
        quote = item.get("verbatim_quote")
        if not isinstance(quote, str) or not quote.strip():
            quote_issues.append({"id": item.get("id"), "issue": "missing_quote"})
        elif _normalize(quote) not in normalized_raw_text:
            quote_issues.append({"id": item.get("id"), "quote": quote})
        normalized_requirement = item.get("normalized_requirement")
        if not isinstance(normalized_requirement, str) or not normalized_requirement.strip():
            normalized_requirement_issues.append(
                {"id": item.get("id"), "issue": "missing_normalized_requirement"}
            )
        justification = item.get("justification")
        if not isinstance(justification, str):
            justification_issues.append(
                {"id": item.get("id"), "issue": "missing_justification"}
            )
    checks.append(
        {
            "id": "verbatim_quotes",
            "status": "pass" if not quote_issues else "fail",
            "details": quote_issues,
        }
    )
    checks.append(
        {
            "id": "normalized_requirements",
            "status": "pass" if not normalized_requirement_issues else "fail",
            "details": normalized_requirement_issues,
        }
    )
    checks.append(
        {
            "id": "justifications",
            "status": "pass" if not justification_issues else "fail",
            "details": justification_issues,
        }
    )

    coverage_keys = list(coverage.keys()) if isinstance(coverage, dict) else []
    checks.append(
        {
            "id": "coverage_top_level_keys",
            "status": "pass"
            if coverage_keys == EXPECTED_COVERAGE_TOP_LEVEL_KEYS else "fail",
            "expected": EXPECTED_COVERAGE_TOP_LEVEL_KEYS,
            "actual": coverage_keys,
        }
    )

    coverage_source_document_ok = (
        coverage.get("source_document") == "docs/requirements/raw-requirements.md"
    )
    checks.append(
        {
            "id": "coverage_source_document",
            "status": "pass" if coverage_source_document_ok else "fail",
            "actual": coverage.get("source_document"),
        }
    )

    inventory_document_ok = (
        coverage.get("inventory_document")
        == "docs/requirements/requirements-inventory.yaml"
    )
    checks.append(
        {
            "id": "coverage_inventory_document",
            "status": "pass" if inventory_document_ok else "fail",
            "actual": coverage.get("inventory_document"),
        }
    )

    coverage_check = coverage.get("coverage_check", {})
    normalized_source_phrases = {_normalize(phrase): phrase for phrase in source_phrases}
    coverage_missing = []
    coverage_bad_refs = []
    coverage_invented = []
    for phrase in source_phrases:
        refs = None
        for actual_phrase, candidate_refs in coverage_check.items():
            if actual_phrase == "status":
                continue
            if _normalize(actual_phrase) == _normalize(phrase):
                refs = candidate_refs
                break
        if not isinstance(refs, list) or not refs:
            coverage_missing.append(phrase)
            continue
        bad = [ref for ref in refs if ref not in ids]
        if bad:
            coverage_bad_refs.append({"phrase": phrase, "bad_refs": bad})
    for actual_phrase in coverage_check:
        if actual_phrase == "status":
            continue
        if _normalize(actual_phrase) not in normalized_source_phrases:
            coverage_invented.append(actual_phrase)
    checks.append(
        {
            "id": "coverage_check",
            "status": "pass"
            if not coverage_missing and not coverage_bad_refs and not coverage_invented
            else "fail",
            "missing_phrases": coverage_missing,
            "bad_refs": coverage_bad_refs,
            "invented_phrases": coverage_invented,
        }
    )

    coverage_verdict = coverage.get("coverage_verdict", {})
    verdict_ok = (
        coverage_verdict.get("total_upstream_phrases") == len(source_phrases)
        and coverage_verdict.get("covered") == len(source_phrases)
        and coverage_verdict.get("orphaned") == 0
        and coverage_verdict.get("invented") == 0
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
        "requirements_coverage_path": str(requirements_coverage_path),
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
        "--requirements-coverage",
        default="docs/requirements/requirements-inventory-coverage.yaml",
        help="Path to the requirements inventory coverage YAML relative to cwd.",
    )
    parser.add_argument(
        "--raw-requirements",
        default="docs/requirements/raw-requirements.md",
        help="Path to the raw requirements markdown relative to cwd.",
    )
    args = parser.parse_args(argv)

    inventory_path = Path(args.requirements_inventory)
    raw_requirements_path = Path(args.raw_requirements)
    coverage_path = Path(args.requirements_coverage)
    try:
        report = build_report(inventory_path, coverage_path, raw_requirements_path)
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
