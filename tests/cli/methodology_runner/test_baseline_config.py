"""Tests for baseline skill configuration loading."""
from pathlib import Path

import pytest

from methodology_runner.baseline_config import (
    BaselineConfigError,
    load_baseline_config,
    validate_against_catalog,
)
from methodology_runner.models import (
    BaselineSkillConfig,
    SkillCatalogEntry,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_baseline_config_happy_path(tmp_path: Path):
    _write(tmp_path / "skills-baselines.yaml", """
version: 1
phases:
  PH-000-requirements-inventory:
    generator: [requirements-extraction, traceability-discipline]
    judge: [requirements-quality-review, traceability-discipline]
""")
    cfg = load_baseline_config(tmp_path / "skills-baselines.yaml")
    assert cfg.version == 1
    gen, jud = cfg.baselines_for("PH-000-requirements-inventory")
    assert gen == ["requirements-extraction", "traceability-discipline"]
    assert jud == ["requirements-quality-review", "traceability-discipline"]


def test_load_baseline_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(BaselineConfigError) as exc_info:
        load_baseline_config(tmp_path / "nope.yaml")
    assert "not found" in str(exc_info.value).lower()


def test_load_baseline_config_malformed_yaml_raises(tmp_path: Path):
    _write(tmp_path / "bad.yaml", "version: 1\n  - oops not a mapping")
    with pytest.raises(BaselineConfigError):
        load_baseline_config(tmp_path / "bad.yaml")


def test_load_baseline_config_missing_version_raises(tmp_path: Path):
    _write(tmp_path / "noversion.yaml", "phases: {}")
    with pytest.raises(BaselineConfigError):
        load_baseline_config(tmp_path / "noversion.yaml")


def test_validate_against_catalog_happy_path(tmp_path: Path):
    cfg = BaselineSkillConfig(
        version=1,
        phases={"PH-X": {"generator": ["a"], "judge": ["b"]}},
    )
    catalog = {
        "a": SkillCatalogEntry(
            id="a", description="A", source_path=Path("/a"), source_location="user",
        ),
        "b": SkillCatalogEntry(
            id="b", description="B", source_path=Path("/b"), source_location="user",
        ),
    }
    validate_against_catalog(cfg, catalog)  # no exception


def test_validate_against_catalog_missing_skill_raises():
    cfg = BaselineSkillConfig(
        version=1,
        phases={"PH-X": {"generator": ["missing"], "judge": []}},
    )
    with pytest.raises(BaselineConfigError) as exc_info:
        validate_against_catalog(cfg, {})
    assert "missing" in str(exc_info.value)
