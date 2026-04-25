from pathlib import Path

import yaml

from methodology_runner.phase_0_validation import build_report, generate_inventory


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_build_report_passes_with_separate_inventory_and_coverage_files(tmp_path: Path):
    raw_requirements = tmp_path / "docs" / "requirements" / "raw-requirements.md"
    raw_requirements.parent.mkdir(parents=True, exist_ok=True)
    raw_requirements.write_text(
        "Requirements:\n- Include a short README.\n",
        encoding="utf-8",
    )

    inventory = tmp_path / "docs" / "requirements" / "requirements-inventory.yaml"
    _write_yaml(
        inventory,
        {
            "source_document": "docs/requirements/raw-requirements.md",
            "items": [
                {
                    "id": "RI-001",
                    "category": "functional",
                    "verbatim_quote": "Include a short README.",
                    "normalized_requirement": "The system shall include a short README.",
                    "justification": "",
                    "source_location": "Requirements > bullet 1",
                    "tags": ["readme"],
                    "rationale": {
                        "rule": "single-clause extraction",
                        "because": "The bullet contains one requirement-bearing statement.",
                    },
                    "open_assumptions": [],
                }
            ],
            "out_of_scope": [],
        },
    )

    coverage = tmp_path / "docs" / "requirements" / "requirements-inventory-coverage.yaml"
    _write_yaml(
        coverage,
        {
            "source_document": "docs/requirements/raw-requirements.md",
            "inventory_document": "docs/requirements/requirements-inventory.yaml",
            "coverage_check": {
                "Include a short README.": ["RI-001"],
                "status": "1/1 requirement-bearing phrases covered, 0 orphans, 0 invented",
            },
            "coverage_verdict": {
                "total_upstream_phrases": 1,
                "covered": 1,
                "orphaned": 0,
                "invented": 0,
                "verdict": "PASS",
            },
        },
    )

    report = build_report(inventory, coverage, raw_requirements)

    assert report["overall_status"] == "pass"
    assert report["failed_checks"] == []


def test_build_report_fails_when_inventory_contains_coverage_fields(tmp_path: Path):
    raw_requirements = tmp_path / "docs" / "requirements" / "raw-requirements.md"
    raw_requirements.parent.mkdir(parents=True, exist_ok=True)
    raw_requirements.write_text(
        "Requirements:\n- Include a short README.\n",
        encoding="utf-8",
    )

    inventory = tmp_path / "docs" / "requirements" / "requirements-inventory.yaml"
    _write_yaml(
        inventory,
        {
            "source_document": "docs/requirements/raw-requirements.md",
            "items": [],
            "out_of_scope": [],
            "coverage_check": {},
            "coverage_verdict": {},
        },
    )

    coverage = tmp_path / "docs" / "requirements" / "requirements-inventory-coverage.yaml"
    _write_yaml(
        coverage,
        {
            "source_document": "docs/requirements/raw-requirements.md",
            "inventory_document": "docs/requirements/requirements-inventory.yaml",
            "coverage_check": {
                "Include a short README.": ["RI-001"],
                "status": "1/1 requirement-bearing phrases covered, 0 orphans, 0 invented",
            },
            "coverage_verdict": {
                "total_upstream_phrases": 1,
                "covered": 1,
                "orphaned": 0,
                "invented": 0,
                "verdict": "PASS",
            },
        },
    )

    report = build_report(inventory, coverage, raw_requirements)

    assert report["overall_status"] == "fail"
    assert "top_level_keys" in report["failed_checks"]


def test_build_report_fails_when_normalized_requirement_is_missing(tmp_path: Path):
    raw_requirements = tmp_path / "docs" / "requirements" / "raw-requirements.md"
    raw_requirements.parent.mkdir(parents=True, exist_ok=True)
    raw_requirements.write_text(
        "Requirements:\n- Include a short README.\n",
        encoding="utf-8",
    )

    inventory = tmp_path / "docs" / "requirements" / "requirements-inventory.yaml"
    _write_yaml(
        inventory,
        {
            "source_document": "docs/requirements/raw-requirements.md",
            "items": [
                {
                    "id": "RI-001",
                    "category": "functional",
                    "verbatim_quote": "Include a short README.",
                    "justification": "",
                    "source_location": "Requirements > bullet 1",
                    "tags": ["readme"],
                    "rationale": {
                        "rule": "single-clause extraction",
                        "because": "The bullet contains one requirement-bearing statement.",
                    },
                    "open_assumptions": [],
                }
            ],
            "out_of_scope": [],
        },
    )

    coverage = tmp_path / "docs" / "requirements" / "requirements-inventory-coverage.yaml"
    _write_yaml(
        coverage,
        {
            "source_document": "docs/requirements/raw-requirements.md",
            "inventory_document": "docs/requirements/requirements-inventory.yaml",
            "coverage_check": {
                "Include a short README.": ["RI-001"],
                "status": "1/1 requirement-bearing phrases covered, 0 orphans, 0 invented",
            },
            "coverage_verdict": {
                "total_upstream_phrases": 1,
                "covered": 1,
                "orphaned": 0,
                "invented": 0,
                "verdict": "PASS",
            },
        },
    )

    report = build_report(inventory, coverage, raw_requirements)

    assert report["overall_status"] == "fail"
    assert "item_required_fields" in report["failed_checks"]
    assert "normalized_requirements" in report["failed_checks"]


def test_build_report_fails_when_justification_is_missing(tmp_path: Path):
    raw_requirements = tmp_path / "docs" / "requirements" / "raw-requirements.md"
    raw_requirements.parent.mkdir(parents=True, exist_ok=True)
    raw_requirements.write_text(
        "Requirements:\n- Include a short README.\n",
        encoding="utf-8",
    )

    inventory = tmp_path / "docs" / "requirements" / "requirements-inventory.yaml"
    _write_yaml(
        inventory,
        {
            "source_document": "docs/requirements/raw-requirements.md",
            "items": [
                {
                    "id": "RI-001",
                    "category": "functional",
                    "verbatim_quote": "Include a short README.",
                    "normalized_requirement": "The system shall include a short README.",
                    "source_location": "Requirements > bullet 1",
                    "tags": ["readme"],
                    "rationale": {
                        "rule": "single-clause extraction",
                        "because": "The bullet contains one requirement-bearing statement.",
                    },
                    "open_assumptions": [],
                }
            ],
            "out_of_scope": [],
        },
    )

    coverage = tmp_path / "docs" / "requirements" / "requirements-inventory-coverage.yaml"
    _write_yaml(
        coverage,
        {
            "source_document": "docs/requirements/raw-requirements.md",
            "inventory_document": "docs/requirements/requirements-inventory.yaml",
            "coverage_check": {
                "Include a short README.": ["RI-001"],
                "status": "1/1 requirement-bearing phrases covered, 0 orphans, 0 invented",
            },
            "coverage_verdict": {
                "total_upstream_phrases": 1,
                "covered": 1,
                "orphaned": 0,
                "invented": 0,
                "verdict": "PASS",
            },
        },
    )

    report = build_report(inventory, coverage, raw_requirements)

    assert report["overall_status"] == "fail"
    assert "item_required_fields" in report["failed_checks"]
    assert "justifications" in report["failed_checks"]


def test_generate_inventory_writes_valid_seed_inventory_and_coverage(tmp_path: Path):
    raw_requirements = tmp_path / "docs" / "requirements" / "raw-requirements.md"
    raw_requirements.parent.mkdir(parents=True, exist_ok=True)
    raw_requirements.write_text(
        "# Request\n\n"
        "The application must support these inputs:\n\n"
        "1. A workspace that contains `.run-files`.\n"
        "2. A comparison manifest JSON file.\n\n"
        "The app must reject paths outside configured allowed roots.\n\n"
        "The report view must show:\n\n"
        "- Report title.\n"
        "- Total cost.\n",
        encoding="utf-8",
    )
    inventory = tmp_path / "docs" / "requirements" / "requirements-inventory.yaml"
    coverage = tmp_path / "docs" / "requirements" / "requirements-inventory-coverage.yaml"

    generate_inventory(inventory, coverage, raw_requirements)

    report = build_report(inventory, coverage, raw_requirements)
    data = yaml.safe_load(inventory.read_text(encoding="utf-8"))
    quotes = [item["verbatim_quote"] for item in data["items"]]

    assert report["overall_status"] == "pass"
    assert "A workspace that contains `.run-files`." in quotes
    assert "A comparison manifest JSON file." in quotes
    assert "The app must reject paths outside configured allowed roots." in quotes
    assert "- Report title. - Total cost." in quotes
