#!/usr/bin/env python3
"""Deterministic PH-000 mechanical validation helper for the hello-world run.

This script checks only mechanical properties of the generated inventory,
traceability mapping, and checklist. It does not try to make semantic or
judgment calls. The output is intended to be read by an AI validator, which
can then complete the remaining review.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


WORKDIR = Path("work")
INVENTORY_PATH = WORKDIR / "requirements-inventory.yaml"
TRACE_PATH = WORKDIR / "requirements-inventory-traceability.yaml"
CHECKLIST_PATH = WORKDIR / "requirements-inventory-checklist.yaml"
OUTPUT_PATH = WORKDIR / "requirements-inventory-mechanical-validation.yaml"
RAW_REQUEST_PATH = "docs/requests/hello-world-python-app.md"

RI_ID_RE = re.compile(r"^RI-\d{3}$")
LINE_LOCATOR_RE = re.compile(
    r"^docs/requests/hello-world-python-app\.md#L\d+-L\d+$"
)
ARTIFACT_REF_RE = re.compile(
    r"^work/requirements-inventory\.yaml#\$\.(inventory_items)\[(\d+)\]$"
)


EXPECTED_LINE_COUNTS = {
    "docs/requests/hello-world-python-app.md#L3-L4": 2,
    "docs/requests/hello-world-python-app.md#L8-L8": 1,
    "docs/requests/hello-world-python-app.md#L9-L9": 1,
    "docs/requests/hello-world-python-app.md#L10-L10": 1,
    "docs/requests/hello-world-python-app.md#L11-L11": 2,
    "docs/requests/hello-world-python-app.md#L12-L13": 2,
    "docs/requests/hello-world-python-app.md#L17-L17": 1,
    "docs/requests/hello-world-python-app.md#L18-L18": 2,
    "docs/requests/hello-world-python-app.md#L22-L22": 2,
    "docs/requests/hello-world-python-app.md#L23-L23": 2,
}


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def result(item_id: str, status: str, details: str, artifact_locations: list[str]) -> dict[str, Any]:
    return {
        "checklist_item_id": item_id,
        "status": status,
        "details": details,
        "artifact_locations": artifact_locations,
    }


def main() -> int:
    inventory_doc = load_yaml(INVENTORY_PATH)
    trace_doc = load_yaml(TRACE_PATH)
    checklist_doc = load_yaml(CHECKLIST_PATH)

    inventory_items = inventory_doc.get("inventory_items", [])
    trace_entries = trace_doc.get("traceability", [])
    checklist_items = checklist_doc.get("checklist_items", [])

    checklist_by_id = {item["id"]: item for item in checklist_items}
    inventory_by_id = {item.get("id"): item for item in inventory_items}
    trace_by_id = {item.get("ri_id"): item for item in trace_entries}

    results: list[dict[str, Any]] = []

    # CL-RI-001: per-line coverage count and traceability existence.
    coverage_ok = True
    coverage_details: list[str] = []
    coverage_locations: list[str] = []
    for source_ref, expected_count in EXPECTED_LINE_COUNTS.items():
        matching_inventory = [item for item in inventory_items if item.get("source_ref") == source_ref]
        matching_trace = [item for item in trace_entries if item.get("source_ref") == source_ref]
        coverage_locations.extend(
            f"work/requirements-inventory.yaml#$.inventory_items[{inventory_items.index(item)}]"
            for item in matching_inventory
        )
        coverage_locations.extend(
            f"work/requirements-inventory-traceability.yaml#$.traceability[{trace_entries.index(item)}]"
            for item in matching_trace
        )
        if len(matching_inventory) < expected_count:
            coverage_ok = False
            coverage_details.append(
                f"{source_ref} has {len(matching_inventory)} inventory items; expected at least {expected_count}."
            )
        if len(matching_trace) < expected_count:
            coverage_ok = False
            coverage_details.append(
                f"{source_ref} has {len(matching_trace)} traceability entries; expected at least {expected_count}."
            )
    results.append(
        result(
            "CL-RI-001",
            "pass" if coverage_ok else "fail",
            " ".join(coverage_details),
            sorted(set(coverage_locations)),
        )
    )

    # CL-RI-002..010: mechanically check expected counts per request line.
    line_to_check_id = {
        "docs/requests/hello-world-python-app.md#L3-L4": "CL-RI-002",
        "docs/requests/hello-world-python-app.md#L8-L8": "CL-RI-003",
        "docs/requests/hello-world-python-app.md#L9-L9": "CL-RI-004",
        "docs/requests/hello-world-python-app.md#L10-L10": "CL-RI-005",
        "docs/requests/hello-world-python-app.md#L11-L11": "CL-RI-006",
        "docs/requests/hello-world-python-app.md#L12-L13": "CL-RI-007",
        "docs/requests/hello-world-python-app.md#L17-L17": "CL-RI-008",
        "docs/requests/hello-world-python-app.md#L18-L18": "CL-RI-009",
        "docs/requests/hello-world-python-app.md#L22-L22": "CL-RI-010",
    }
    for source_ref, check_id in line_to_check_id.items():
        expected_count = EXPECTED_LINE_COUNTS[source_ref]
        matching_inventory = [item for item in inventory_items if item.get("source_ref") == source_ref]
        locations = [
            f"work/requirements-inventory.yaml#$.inventory_items[{inventory_items.index(item)}]"
            for item in matching_inventory
        ]
        status = "pass" if len(matching_inventory) == expected_count else "fail"
        details = ""
        if status == "fail":
            details = f"{source_ref} has {len(matching_inventory)} inventory items; expected {expected_count}."
        results.append(result(check_id, status, details, locations))

    # CL-RI-011: unique RI IDs with correct pattern.
    ids = [item.get("id", "") for item in inventory_items]
    unique_id_ok = len(ids) == len(set(ids)) and all(RI_ID_RE.match(ri_id or "") for ri_id in ids)
    results.append(
        result(
            "CL-RI-011",
            "pass" if unique_id_ok else "fail",
            "" if unique_id_ok else "Inventory IDs must be unique and match RI-###.",
            ["work/requirements-inventory.yaml"],
        )
    )

    # CL-RI-012: source_ref format and file target.
    source_ref_ok = all(LINE_LOCATOR_RE.match(item.get("source_ref", "")) for item in inventory_items)
    results.append(
        result(
            "CL-RI-012",
            "pass" if source_ref_ok else "fail",
            "" if source_ref_ok else f"Every inventory item source_ref must target {RAW_REQUEST_PATH} with Lx-Ly.",
            ["work/requirements-inventory.yaml"],
        )
    )

    # CL-RI-013: exactly one traceability entry per inventory item with matching ri_id and source_ref.
    trace_ok = True
    trace_details: list[str] = []
    trace_locations: list[str] = []
    for idx, item in enumerate(inventory_items):
        ri_id = item.get("id")
        matching = [entry for entry in trace_entries if entry.get("ri_id") == ri_id]
        if len(matching) != 1:
            trace_ok = False
            trace_details.append(f"{ri_id} has {len(matching)} traceability entries; expected 1.")
            continue
        entry = matching[0]
        trace_locations.append(
            f"work/requirements-inventory-traceability.yaml#$.traceability[{trace_entries.index(entry)}]"
        )
        if entry.get("source_ref") != item.get("source_ref"):
            trace_ok = False
            trace_details.append(f"{ri_id} source_ref mismatch between inventory and traceability.")
        artifact_ref = entry.get("artifact_element_ref", "")
        match = ARTIFACT_REF_RE.match(artifact_ref)
        if not match:
            trace_ok = False
            trace_details.append(f"{ri_id} artifact_element_ref is invalid: {artifact_ref}")
            continue
        ref_index = int(match.group(2))
        if ref_index != idx:
            trace_ok = False
            trace_details.append(f"{ri_id} artifact_element_ref points to index {ref_index}; expected {idx}.")
    results.append(
        result(
            "CL-RI-013",
            "pass" if trace_ok else "fail",
            " ".join(trace_details),
            sorted(set(trace_locations)) or ["work/requirements-inventory-traceability.yaml"],
        )
    )

    unchecked = ["CL-RI-014"]
    overall_status = "pass" if all(r["status"] == "pass" for r in results) else "fail"

    report = {
        "mechanical_validation": {
            "overall_status": overall_status,
            "checklist_results": results,
            "unchecked_checklist_item_ids": unchecked,
            "notes": [
                "This report covers only deterministic checks.",
                "Unchecked checklist items require non-mechanical review in the next validation step.",
            ],
        }
    }

    OUTPUT_PATH.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
