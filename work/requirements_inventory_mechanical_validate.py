#!/usr/bin/env python3
"""Deterministic requirements-inventory mechanical validation helper.

This script checks structural properties and explicit source-sentence coverage.
It does not make semantic judgments about whether a decomposition is good.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml


RI_ID_RE = re.compile(r"^RI-\d{3}$")


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


def workdir_from_argv() -> Path:
    if len(sys.argv) not in (1, 2, 4):
        raise SystemExit(
            "usage: requirements_inventory_mechanical_validate.py [run_dir] "
            "or requirements_inventory_mechanical_validate.py <run_dir> <request_path> <artifact_prefix>"
        )
    if len(sys.argv) == 2:
        return Path(sys.argv[1])
    return Path("work")


def request_path_from_argv() -> Path:
    if len(sys.argv) == 4:
        return Path(sys.argv[2])
    return Path("docs/requests/hello-world-python-app.md")


def artifact_prefix_from_argv() -> str:
    if len(sys.argv) == 4:
        return sys.argv[3]
    return "requirements-inventory"


def normalize_ws(text: str) -> str:
    return " ".join(text.split())


def extract_source_sentences(raw_request_path: Path) -> list[tuple[str, str]]:
    lines = raw_request_path.read_text(encoding="utf-8").splitlines()
    units: list[tuple[str, str]] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        if stripped.endswith(":"):
            index += 1
            continue

        start = index + 1
        end = start

        if stripped.startswith("- "):
            parts = [stripped[2:].strip()]
            index += 1
            while index < len(lines):
                cont = lines[index]
                cont_stripped = cont.strip()
                if not cont_stripped:
                    break
                if cont.lstrip() == cont and cont_stripped.startswith("- "):
                    break
                if cont.lstrip() == cont and cont_stripped.endswith(":"):
                    break
                parts.append(cont_stripped)
                end = index + 1
                index += 1
        else:
            parts = [stripped]
            index += 1
            while index < len(lines):
                cont = lines[index]
                cont_stripped = cont.strip()
                if not cont_stripped or cont_stripped.startswith("#") or cont_stripped.endswith(":") or cont_stripped.startswith("- "):
                    break
                parts.append(cont_stripped)
                end = index + 1
                index += 1

        sentence = normalize_ws(" ".join(parts))
        source_ref = f"{raw_request_path}#L{start}-L{end}"
        units.append((source_ref, sentence))

        while index < len(lines) and not lines[index].strip():
            index += 1

    return units


def main() -> int:
    workdir = workdir_from_argv()
    raw_request_path = request_path_from_argv()
    artifact_prefix = artifact_prefix_from_argv()
    inventory_path = workdir / f"{artifact_prefix}.yaml"
    trace_path = workdir / f"{artifact_prefix}-traceability.yaml"
    checklist_path = workdir / f"{artifact_prefix}-checklist.yaml"
    output_path = workdir / f"{artifact_prefix}-mechanical-validation.yaml"

    inventory_ref_prefix = f"{workdir}/{artifact_prefix}.yaml"
    trace_ref_prefix = f"{workdir}/{artifact_prefix}-traceability.yaml"
    artifact_ref_re = re.compile(
        rf"^{re.escape(inventory_ref_prefix)}#\$\.(inventory_items)\[(\d+)\]$"
    )
    line_locator_re = re.compile(rf"^{re.escape(str(raw_request_path))}#L\d+-L\d+$")

    inventory_doc = load_yaml(inventory_path)
    trace_doc = load_yaml(trace_path)
    checklist_doc = load_yaml(checklist_path)

    inventory_items = inventory_doc.get("inventory_items", [])
    trace_entries = trace_doc.get("traceability", [])
    checklist_items = checklist_doc.get("checklist_items", [])
    source_units = extract_source_sentences(raw_request_path)
    source_sentence_by_ref = {ref: sentence for ref, sentence in source_units}

    results: list[dict[str, Any]] = []

    ids = [item.get("id", "") for item in inventory_items]
    unique_id_ok = len(ids) == len(set(ids)) and all(RI_ID_RE.match(ri_id or "") for ri_id in ids)
    results.append(
        result(
            "M-RI-001",
            "pass" if unique_id_ok else "fail",
            "" if unique_id_ok else "Inventory IDs must be unique and match RI-###.",
            [inventory_ref_prefix],
        )
    )

    sentence_grounding_ok = True
    sentence_grounding_details: list[str] = []
    sentence_grounding_locations: list[str] = []
    for idx, item in enumerate(inventory_items):
        source_ref = item.get("source_ref", "")
        source_sentence = normalize_ws(item.get("source_sentence", ""))
        sentence_grounding_locations.append(
            f"{inventory_ref_prefix}#$.inventory_items[{idx}]"
        )
        if not line_locator_re.match(source_ref):
            sentence_grounding_ok = False
            sentence_grounding_details.append(
                f"{item.get('id', f'item[{idx}]')} has invalid source_ref: {source_ref}"
            )
            continue
        expected_sentence = source_sentence_by_ref.get(source_ref)
        if expected_sentence is None:
            sentence_grounding_ok = False
            sentence_grounding_details.append(
                f"{item.get('id', f'item[{idx}]')} source_ref does not map to a source sentence: {source_ref}"
            )
            continue
        if source_sentence != expected_sentence:
            sentence_grounding_ok = False
            sentence_grounding_details.append(
                f"{item.get('id', f'item[{idx}]')} source_sentence does not exactly match {source_ref}."
            )
    results.append(
        result(
            "M-RI-002",
            "pass" if sentence_grounding_ok else "fail",
            " ".join(sentence_grounding_details),
            sentence_grounding_locations or [inventory_ref_prefix],
        )
    )

    coverage_ok = True
    coverage_details: list[str] = []
    coverage_locations: list[str] = []
    for source_ref, sentence in source_units:
        matching_inventory = [
            item for item in inventory_items
            if item.get("source_ref") == source_ref
            and normalize_ws(item.get("source_sentence", "")) == sentence
        ]
        matching_trace = [item for item in trace_entries if item.get("source_ref") == source_ref]
        coverage_locations.extend(
            f"{inventory_ref_prefix}#$.inventory_items[{inventory_items.index(item)}]"
            for item in matching_inventory
        )
        coverage_locations.extend(
            f"{trace_ref_prefix}#$.traceability[{trace_entries.index(item)}]"
            for item in matching_trace
        )
        if not matching_inventory:
            coverage_ok = False
            coverage_details.append(f"{source_ref} is not covered by any inventory item.")
        if len(matching_trace) < len(matching_inventory):
            coverage_ok = False
            coverage_details.append(f"{source_ref} is missing one or more matching traceability entries.")
    results.append(
        result(
            "M-RI-003",
            "pass" if coverage_ok else "fail",
            " ".join(coverage_details),
            sorted(set(coverage_locations)),
        )
    )

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
            f"{trace_ref_prefix}#$.traceability[{trace_entries.index(entry)}]"
        )
        if entry.get("source_ref") != item.get("source_ref"):
            trace_ok = False
            trace_details.append(f"{ri_id} source_ref mismatch between inventory and traceability.")
        artifact_ref = entry.get("artifact_element_ref", "")
        match = artifact_ref_re.match(artifact_ref)
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
            "M-RI-004",
            "pass" if trace_ok else "fail",
            " ".join(trace_details),
            sorted(set(trace_locations)) or [trace_ref_prefix],
        )
    )

    checklist_shape_ok = checklist_doc.keys() == {"checklist_items"} and isinstance(checklist_items, list)
    results.append(
        result(
            "M-RI-005",
            "pass" if checklist_shape_ok else "fail",
            "" if checklist_shape_ok else "Checklist must contain exactly one top-level key: checklist_items.",
            [f"{workdir}/{artifact_prefix}-checklist.yaml"],
        )
    )

    overall_status = "pass" if all(r["status"] == "pass" for r in results) else "fail"

    report = {
        "mechanical_validation": {
            "overall_status": overall_status,
            "checklist_results": results,
            "unchecked_checklist_item_ids": [],
            "notes": [
                "This report covers only deterministic checks.",
                "Source coverage is verified by exact source_sentence matching.",
            ],
        }
    }

    output_path.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
