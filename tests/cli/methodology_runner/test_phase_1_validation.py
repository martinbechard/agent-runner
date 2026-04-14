from pathlib import Path

from methodology_runner.phase_1_validation import build_report, main


def _write_inputs(tmp_path: Path, *, feature_spec_text: str, inventory_text: str) -> tuple[Path, Path]:
    feature_spec = tmp_path / "docs" / "features" / "feature-specification.yaml"
    inventory = tmp_path / "docs" / "requirements" / "requirements-inventory.yaml"
    feature_spec.parent.mkdir(parents=True, exist_ok=True)
    inventory.parent.mkdir(parents=True, exist_ok=True)
    feature_spec.write_text(feature_spec_text, encoding="utf-8")
    inventory.write_text(inventory_text, encoding="utf-8")
    return feature_spec, inventory


def test_build_report_passes_on_minimal_valid_spec(tmp_path: Path):
    feature_spec, inventory = _write_inputs(
        tmp_path,
        feature_spec_text="""features:
  - id: "FT-001"
    name: "Runtime"
    description: "Run the app."
    source_inventory_refs: ["RI-001", "RI-002"]
    acceptance_criteria: []
    dependencies: []
out_of_scope: []
cross_cutting_concerns: []
""",
        inventory_text="""items:
  - id: "RI-001"
  - id: "RI-002"
""",
    )
    report = build_report(feature_spec, inventory)
    assert report["overall_status"] == "pass"
    assert report["failed_checks"] == []


def test_build_report_fails_missing_inventory_coverage(tmp_path: Path):
    feature_spec, inventory = _write_inputs(
        tmp_path,
        feature_spec_text="""features:
  - id: "FT-001"
    name: "Runtime"
    description: "Run the app."
    source_inventory_refs: ["RI-001"]
    acceptance_criteria: []
    dependencies: []
out_of_scope: []
cross_cutting_concerns: []
""",
        inventory_text="""items:
  - id: "RI-001"
  - id: "RI-002"
""",
    )
    report = build_report(feature_spec, inventory)
    assert report["overall_status"] == "fail"
    assert "inventory_coverage" in report["failed_checks"]


def test_main_returns_one_when_checks_fail(tmp_path: Path, monkeypatch):
    _write_inputs(
        tmp_path,
        feature_spec_text="""features: []
out_of_scope: []
cross_cutting_concerns: []
""",
        inventory_text="""items:
  - id: "RI-001"
""",
    )
    monkeypatch.chdir(tmp_path)
    rc = main([])
    assert rc == 1
