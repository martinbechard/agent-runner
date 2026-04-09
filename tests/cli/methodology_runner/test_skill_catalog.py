"""Tests for skill catalog discovery."""
from pathlib import Path

import pytest

from methodology_runner.skill_catalog import (
    CatalogBuildError,
    build_catalog,
    parse_skill_md,
)


def _write_skill(dir_path: Path, name: str, description: str) -> Path:
    skill_dir = dir_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"""---
name: {name}
description: {description}
---

# {name}

Body content.
""",
        encoding="utf-8",
    )
    return skill_md


def test_parse_skill_md_extracts_name_and_description(tmp_path: Path):
    path = _write_skill(tmp_path / "skills", "tdd", "Test-driven development")
    entry = parse_skill_md(path, source_location="user")
    assert entry is not None
    assert entry.id == "tdd"
    assert entry.description == "Test-driven development"
    assert entry.source_location == "user"


def test_parse_skill_md_returns_none_for_missing_frontmatter(tmp_path: Path):
    path = tmp_path / "bad" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("# no frontmatter\n\nbody", encoding="utf-8")
    assert parse_skill_md(path, source_location="user") is None


def test_parse_skill_md_derives_id_from_directory_when_name_missing(tmp_path: Path):
    path = tmp_path / "my-skill" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        """---
description: A skill without an explicit name field
---
body
""",
        encoding="utf-8",
    )
    entry = parse_skill_md(path, source_location="user")
    assert entry is not None
    assert entry.id == "my-skill"


def test_parse_skill_md_rejects_empty_description(tmp_path: Path):
    path = tmp_path / "empty" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        """---
name: empty
description:
---
body
""",
        encoding="utf-8",
    )
    assert parse_skill_md(path, source_location="user") is None


def test_build_catalog_walks_three_locations(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    _write_skill(workspace / ".claude" / "skills", "proj-skill", "Project")
    _write_skill(user_home / ".claude" / "skills", "user-skill", "User")
    _write_skill(
        user_home / ".claude" / "plugins" / "somepkg" / "skills",
        "plugin-skill",
        "Plugin",
    )
    catalog = build_catalog(workspace=workspace, user_home=user_home)
    ids = {e.id for e in catalog.values()}
    assert ids == {"proj-skill", "user-skill", "plugin-skill"}


def test_build_catalog_priority_project_beats_user_beats_plugin(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    _write_skill(workspace / ".claude" / "skills", "same", "from project")
    _write_skill(user_home / ".claude" / "skills", "same", "from user")
    _write_skill(
        user_home / ".claude" / "plugins" / "pk" / "skills",
        "same",
        "from plugin",
    )
    catalog = build_catalog(workspace=workspace, user_home=user_home)
    assert catalog["same"].description == "from project"
    assert catalog["same"].source_location == "project"


def test_build_catalog_empty_raises_catalog_build_error(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    workspace.mkdir()
    user_home.mkdir()
    with pytest.raises(CatalogBuildError) as exc_info:
        build_catalog(workspace=workspace, user_home=user_home)
    assert "no claude code skills discovered" in str(exc_info.value).lower()


def test_build_catalog_skips_invalid_entries_but_keeps_valid_ones(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    _write_skill(user_home / ".claude" / "skills", "good", "Good skill")
    # Invalid one
    bad = user_home / ".claude" / "skills" / "bad" / "SKILL.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("# no frontmatter", encoding="utf-8")
    catalog = build_catalog(workspace=workspace, user_home=user_home)
    assert "good" in catalog
    assert "bad" not in catalog
