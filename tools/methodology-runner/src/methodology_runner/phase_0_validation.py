"""Deterministic validation for PH-000 requirements inventories."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
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
NUMBERED_LIST_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")
REQUIREMENT_SIGNAL_RE = re.compile(
    r"\b(must|should|shall|will|need to|needs to|not|do not|can|include|contains|support|"
    r"provide|provides|show|expose|cover|handle|reject|rejects|run|runs|build|builds|"
    r"reviewing|comparing|diagnosing|"
    r"use|keep|comment|add|prefer|describe|document)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _SourceEntry:
    """One contiguous source span used to seed a PH-000 inventory item."""

    quote: str
    section: str
    location_kind: str
    location_index: int
    lead_in: str = ""


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _category_for(text: str) -> str:
    normalized = text.lower()
    if any(term in normalized for term in ("assuming", "given that", "provided that")):
        return "assumption"
    if any(
        term in normalized
        for term in (
            "must not",
            "shall not",
            "may not",
            "cannot",
            "can't",
            "do not access",
            "do not execute",
            "do not expose",
            "do not mutate",
            "do not read",
            "do not write",
            "local-only",
            "outside configured allowed roots",
            "outside the configured allowed roots",
            "outside allowed roots",
            "arbitrary file reads",
        )
    ):
        return "constraint"
    if any(
        term in normalized
        for term in (
            "must",
            "shall",
            "will",
            "need to",
            "needs to",
            "build",
            "include",
            "contains",
            "support",
            "provide",
            "show",
            "expose",
            "cover",
            "handle",
            "reject",
            "run",
            "load",
            "parse",
            "normalize",
            "display",
            "render",
            "open",
            "link",
            "filter",
            "toggle",
            "sort",
            "group",
            "aggregate",
            "document",
            "implement",
            "create",
        )
    ):
        return "functional"
    if any(term in normalized for term in ("should", "may", "can be")):
        return "non_functional"
    return "functional"


def _short_tags(section: str, quote: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", f"{section} {quote}".lower())
    stop_words = {
        "the",
        "and",
        "for",
        "must",
        "should",
        "with",
        "when",
        "that",
        "this",
        "from",
        "into",
        "each",
        "available",
    }
    tags: list[str] = []
    for word in words:
        cleaned = word.strip("-")
        if cleaned in stop_words or cleaned in tags:
            continue
        tags.append(cleaned[:32])
        if len(tags) == 4:
            break
    return tags or ["requirement"]


def _standalone_requirement(entry: _SourceEntry) -> str:
    quote = entry.quote.strip()
    context = entry.lead_in.rstrip(":").strip()
    if context:
        return f"{context}: {quote}"
    if REQUIREMENT_SIGNAL_RE.search(quote):
        return quote
    return f"{entry.section}: {quote}"


def _source_location(entry: _SourceEntry) -> str:
    return f"{entry.section} > {entry.location_kind} {entry.location_index}"


def _is_requirement_entry(entry: _SourceEntry) -> bool:
    if entry.location_kind in {"bullet", "numbered item"}:
        return True
    combined = f"{entry.lead_in} {entry.quote}"
    if REQUIREMENT_SIGNAL_RE.search(combined):
        return True
    # Field and metric lists under requirement-bearing lead-ins are still
    # useful downstream, even when the individual field name has no modal verb.
    return bool(entry.lead_in)


def _parse_source_entries(raw_requirements_path: Path) -> list[_SourceEntry]:
    """Extract contiguous paragraphs and list items with section locations."""
    lines = raw_requirements_path.read_text(encoding="utf-8").splitlines()
    section_stack: list[str] = []
    entries: list[_SourceEntry] = []
    paragraph: list[str] = []
    paragraph_start = 0
    lead_in = ""
    list_after_lead_in = False
    counters: dict[tuple[str, str], int] = {}

    def section_name() -> str:
        return " > ".join(section_stack) if section_stack else "Document"

    def next_index(kind: str) -> int:
        key = (section_name(), kind)
        counters[key] = counters.get(key, 0) + 1
        return counters[key]

    def append_entry(quote: str, kind: str, start_index: int | None = None) -> None:
        nonlocal list_after_lead_in
        normalized = _normalize(quote)
        if not normalized:
            return
        index = start_index if start_index is not None else next_index(kind)
        entry = _SourceEntry(
            quote=normalized,
            section=section_name(),
            location_kind=kind,
            location_index=index,
            lead_in=lead_in,
        )
        if _is_requirement_entry(entry):
            entries.append(entry)
        list_after_lead_in = kind in {"bullet", "numbered item"} and bool(lead_in)

    def flush_paragraph() -> None:
        nonlocal paragraph, paragraph_start, lead_in
        if not paragraph:
            return
        text = _normalize(" ".join(paragraph))
        paragraph = []
        if not text:
            return
        if text.endswith(":"):
            lead_in = text
            return
        append_entry(text, "paragraph", paragraph_start or None)
        lead_in = ""

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            flush_paragraph()
            if list_after_lead_in:
                lead_in = ""
                list_after_lead_in = False
            continue
        if stripped.startswith("#"):
            flush_paragraph()
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped[level:].strip()
            section_stack = section_stack[: max(level - 1, 0)] + [title]
            lead_in = ""
            continue
        if raw_line.startswith("- "):
            flush_paragraph()
            append_entry(raw_line[2:].strip(), "bullet")
            continue
        numbered = NUMBERED_LIST_RE.match(raw_line)
        if numbered is not None:
            flush_paragraph()
            append_entry(numbered.group(2).strip(), "numbered item", int(numbered.group(1)))
            continue
        if not paragraph:
            paragraph_start = next_index("paragraph")
        paragraph.append(stripped)

    flush_paragraph()
    return entries


def generate_inventory(
    requirements_inventory_path: Path,
    requirements_coverage_path: Path,
    raw_requirements_path: Path,
) -> None:
    """Write deterministic PH-000 inventory and coverage seed artifacts."""
    entries = _parse_source_entries(raw_requirements_path)
    items: list[dict] = []
    for index, entry in enumerate(entries, start=1):
        item_id = f"RI-{index:03d}"
        items.append(
            {
                "id": item_id,
                "category": _category_for(f"{entry.lead_in} {entry.quote}"),
                "verbatim_quote": entry.quote,
                "normalized_requirement": _standalone_requirement(entry),
                "justification": "",
                "source_location": _source_location(entry),
                "tags": _short_tags(entry.section, entry.quote),
                "rationale": {
                    "rule": "deterministic source-span extraction",
                    "because": (
                        "The source span is a contiguous requirement-bearing "
                        "paragraph or list item in the raw request."
                    ),
                },
                "open_assumptions": [],
            }
        )

    item_ids = {item["id"] for item in items}
    source_phrases = _extract_requirement_phrases(raw_requirements_path)
    coverage_check: dict[str, list[str] | str] = {}
    for phrase in source_phrases:
        normalized_phrase = _normalize(phrase)
        refs = [
            item["id"]
            for item in items
            if _normalize(item["verbatim_quote"]) in normalized_phrase
            or normalized_phrase in _normalize(item["verbatim_quote"])
        ]
        if not refs:
            fallback_id = f"RI-{len(items) + 1:03d}"
            fallback_entry = _SourceEntry(
                quote=phrase,
                section="Source coverage",
                location_kind="phrase",
                location_index=len(items) + 1,
            )
            items.append(
                {
                    "id": fallback_id,
                    "category": _category_for(phrase),
                    "verbatim_quote": phrase,
                    "normalized_requirement": _standalone_requirement(fallback_entry),
                    "justification": "",
                    "source_location": _source_location(fallback_entry),
                    "tags": _short_tags(fallback_entry.section, phrase),
                    "rationale": {
                        "rule": "coverage fallback extraction",
                        "because": (
                            "The deterministic coverage phrase did not map to "
                            "an earlier source-span item, so it was preserved "
                            "as its own contiguous requirement phrase."
                        ),
                    },
                    "open_assumptions": [],
                }
            )
            item_ids.add(fallback_id)
            refs = [fallback_id]
        coverage_check[phrase] = [ref for ref in refs if ref in item_ids]

    total = len(source_phrases)
    coverage_check["status"] = (
        f"{total}/{total} requirement-bearing phrases covered, 0 orphans, 0 invented"
    )
    inventory = {
        "source_document": "docs/requirements/raw-requirements.md",
        "items": items,
        "out_of_scope": [],
    }
    coverage = {
        "source_document": "docs/requirements/raw-requirements.md",
        "inventory_document": "docs/requirements/requirements-inventory.yaml",
        "coverage_check": coverage_check,
        "coverage_verdict": {
            "total_upstream_phrases": total,
            "covered": total,
            "orphaned": 0,
            "invented": 0,
            "verdict": "PASS",
        },
    }
    requirements_inventory_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_coverage_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_inventory_path.write_text(
        yaml.safe_dump(inventory, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    requirements_coverage_path.write_text(
        yaml.safe_dump(coverage, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


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
    parser.add_argument(
        "--generate",
        action="store_true",
        help=(
            "Generate deterministic seed inventory and coverage artifacts "
            "before validating them."
        ),
    )
    args = parser.parse_args(argv)

    inventory_path = Path(args.requirements_inventory)
    raw_requirements_path = Path(args.raw_requirements)
    coverage_path = Path(args.requirements_coverage)
    try:
        if args.generate:
            generate_inventory(inventory_path, coverage_path, raw_requirements_path)
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
