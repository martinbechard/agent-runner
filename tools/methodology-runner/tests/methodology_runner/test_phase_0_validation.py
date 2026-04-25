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
        "Build a local web application for browsing prompt-runner and methodology-runner "
        "execution reports. The application should provide the same core insight as "
        "the static HTML report generated by the existing timeline utility.\n\n"
        "## Users\n\n"
        "- A maintainer diagnosing token usage, cost, tool activity, retries, and judge decisions.\n\n"
        "The application must support these inputs:\n\n"
        "1. A workspace that contains `.run-files`.\n"
        "2. A comparison manifest JSON file.\n\n"
        "The app must include at least one small sample run fixture that can be loaded "
        "without external files.\n\n"
        "The app must reject paths outside configured allowed roots.\n\n"
        "The parser must normalize every supported input shape into a report document "
        "with these concepts:\n\n"
        "- Report title.\n"
        "- Source path.\n"
        "- A list of parsing warnings that do not prevent display.\n\n"
        "The report view must show:\n\n"
        "- Report title.\n"
        "- Total cost.\n\n"
        "## Search and Filtering\n\n"
        "The report view must provide:\n\n"
        "- Toggle to show only rows with warnings, errors, or failed/revise verdicts.\n\n"
        "Search and filters must not mutate the parsed report document.\n\n"
        "## Drill-Down Navigation\n\n"
        "When a methodology workspace includes a PH-006 implementation workflow child report:\n\n"
        "- The parent report must show a drill-down link on the PH-006 phase.\n\n"
        "## Implementation Expectations\n\n"
        "- Use TypeScript for application code.\n",
        encoding="utf-8",
    )
    inventory = tmp_path / "docs" / "requirements" / "requirements-inventory.yaml"
    coverage = tmp_path / "docs" / "requirements" / "requirements-inventory-coverage.yaml"

    generate_inventory(inventory, coverage, raw_requirements)

    report = build_report(inventory, coverage, raw_requirements)
    data = yaml.safe_load(inventory.read_text(encoding="utf-8"))
    quotes = [item["verbatim_quote"] for item in data["items"]]
    categories = {item["verbatim_quote"]: item["category"] for item in data["items"]}
    normalized_requirements = {
        item["verbatim_quote"]: item["normalized_requirement"] for item in data["items"]
    }
    source_locations = {item["verbatim_quote"]: item["source_location"] for item in data["items"]}

    assert report["overall_status"] == "pass"
    assert categories[
        "Build a local web application for browsing prompt-runner and methodology-runner "
        "execution reports. The application should provide the same core insight as "
        "the static HTML report generated by the existing timeline utility."
    ] == "functional"
    assert (
        "A maintainer diagnosing token usage, cost, tool activity, retries, and judge decisions."
        in quotes
    )
    assert source_locations[
        "A maintainer diagnosing token usage, cost, tool activity, retries, and judge decisions."
    ] == "Request > Users > bullet 1"
    assert "A workspace that contains `.run-files`." in quotes
    assert normalized_requirements["A workspace that contains `.run-files`."] == (
        "The application must support these inputs: A workspace that contains `.run-files`."
    )
    assert "A comparison manifest JSON file." in quotes
    assert categories[
        "The app must include at least one small sample run fixture that can be loaded "
        "without external files."
    ] == "functional"
    assert "The app must reject paths outside configured allowed roots." in quotes
    assert categories["The app must reject paths outside configured allowed roots."] == "constraint"
    assert "Report title." in quotes
    report_title_requirements = [
        item["normalized_requirement"]
        for item in data["items"]
        if item["verbatim_quote"] == "Report title."
    ]
    assert sorted(report_title_requirements) == [
        "The parser must normalize every supported input shape into a report document "
        "with these concepts: Report title.",
        "The report view must show: Report title.",
    ]
    assert normalized_requirements["Source path."] == (
        "The parser must normalize every supported input shape into a report document "
        "with these concepts: Source path."
    )
    assert normalized_requirements[
        "A list of parsing warnings that do not prevent display."
    ] == (
        "The parser must normalize every supported input shape into a report document "
        "with these concepts: A list of parsing warnings that do not prevent display."
    )
    assert normalized_requirements["Total cost."] == "The report view must show: Total cost."
    assert categories[
        "Toggle to show only rows with warnings, errors, or failed/revise verdicts."
    ] == "functional"
    assert normalized_requirements[
        "Toggle to show only rows with warnings, errors, or failed/revise verdicts."
    ] == (
        "The report view must provide: Toggle to show only rows with warnings, errors, "
        "or failed/revise verdicts."
    )
    assert normalized_requirements[
        "Search and filters must not mutate the parsed report document."
    ] == "Search and filters must not mutate the parsed report document."
    assert normalized_requirements[
        "The parent report must show a drill-down link on the PH-006 phase."
    ] == (
        "When a methodology workspace includes a PH-006 implementation workflow child "
        "report: The parent report must show a drill-down link on the PH-006 phase."
    )
    assert "Use TypeScript for application code." in quotes
    assert not any(
        item["source_location"].startswith("Source coverage") for item in data["items"]
    )
