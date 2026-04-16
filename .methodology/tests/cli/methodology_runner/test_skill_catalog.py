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


def test_build_catalog_walks_four_locations(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    cwd = tmp_path / "repo"
    _write_skill(workspace / ".claude" / "skills", "proj-skill", "Project")
    _write_skill(cwd / ".methodology" / "skills", "repo-skill", "Repo methodology")
    _write_skill(user_home / ".claude" / "skills", "user-skill", "User")
    _write_skill(
        user_home / ".claude" / "plugins" / "somepkg" / "skills",
        "plugin-skill",
        "Plugin",
    )
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=cwd, backend="claude")
    ids = {e.id for e in catalog.values()}
    assert ids == {"proj-skill", "repo-skill", "user-skill", "plugin-skill"}


def test_build_catalog_priority_project_beats_repo_beats_user_beats_plugin(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    cwd = tmp_path / "repo"
    _write_skill(workspace / ".claude" / "skills", "same", "from project")
    _write_skill(cwd / ".methodology" / "skills", "same", "from repo")
    _write_skill(user_home / ".claude" / "skills", "same", "from user")
    _write_skill(
        user_home / ".claude" / "plugins" / "pk" / "skills",
        "same",
        "from plugin",
    )
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=cwd, backend="claude")
    assert catalog["same"].description == "from project"
    assert catalog["same"].source_location == "project"


def test_build_catalog_empty_raises_catalog_build_error(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    workspace.mkdir()
    user_home.mkdir()
    with pytest.raises(CatalogBuildError) as exc_info:
        build_catalog(workspace=workspace, user_home=user_home, cwd=tmp_path, backend="claude")
    assert "no claude skills discovered" in str(exc_info.value).lower()


def test_build_catalog_skips_invalid_entries_but_keeps_valid_ones(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    _write_skill(user_home / ".claude" / "skills", "good", "Good skill")
    # Invalid one
    bad = user_home / ".claude" / "skills" / "bad" / "SKILL.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("# no frontmatter", encoding="utf-8")
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=tmp_path, backend="claude")
    assert "good" in catalog
    assert "bad" not in catalog


def test_build_catalog_walks_repo_methodology_dir(tmp_path: Path):
    """Repo-local methodology skills under .methodology/skills/ are discovered."""
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    cwd = tmp_path / "repo"
    _write_skill(cwd / ".methodology" / "skills", "tdd", "Test-driven development")
    _write_skill(cwd / ".methodology" / "skills", "traceability-discipline", "Universal traceability")
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=cwd, backend="claude")
    assert "tdd" in catalog
    assert "traceability-discipline" in catalog
    assert catalog["tdd"].source_location == "repo-methodology"


def test_repo_methodology_shadows_user_installed_plugin(tmp_path: Path):
    """When the same skill exists in .methodology/skills/ and ~/.claude/plugins/,
    the repo-local methodology version wins."""
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    cwd = tmp_path / "repo"
    _write_skill(cwd / ".methodology" / "skills", "tdd", "repo version")
    _write_skill(
        user_home / ".claude" / "plugins" / "some-pack" / "skills",
        "tdd", "installed version",
    )
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=cwd, backend="claude")
    assert catalog["tdd"].description == "repo version"
    assert catalog["tdd"].source_location == "repo-methodology"


def test_project_local_still_beats_repo_methodology(tmp_path: Path):
    """Workspace-local skills still take priority over repo-local methodology skills."""
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    cwd = tmp_path / "repo"
    _write_skill(workspace / ".claude" / "skills", "tdd", "workspace version")
    _write_skill(cwd / ".methodology" / "skills", "tdd", "repo version")
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=cwd, backend="claude")
    assert catalog["tdd"].description == "workspace version"
    assert catalog["tdd"].source_location == "project"


def test_build_catalog_defaults_cwd_to_current_working_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """When cwd is not passed, Path.cwd() is used."""
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    fake_cwd = tmp_path / "repo"
    _write_skill(fake_cwd / ".methodology" / "skills", "tdd", "from cwd")
    monkeypatch.chdir(fake_cwd)
    catalog = build_catalog(workspace=workspace, user_home=user_home, backend="claude")
    # cwd should default to Path.cwd() which is now fake_cwd
    assert "tdd" in catalog
    assert catalog["tdd"].description == "from cwd"


def test_empty_repo_methodology_dir_does_not_affect_discovery(tmp_path: Path):
    """If .methodology/skills exists but is empty, discovery still works."""
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    cwd = tmp_path / "repo"
    (cwd / ".methodology" / "skills").mkdir(parents=True)
    _write_skill(user_home / ".claude" / "skills", "tdd", "user version")
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=cwd, backend="claude")
    assert catalog["tdd"].source_location == "user"


def test_nonexistent_repo_methodology_dir_is_skipped(tmp_path: Path):
    """If .methodology/skills does not exist, discovery just skips it."""
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    cwd = tmp_path / "repo"
    cwd.mkdir()
    _write_skill(user_home / ".claude" / "skills", "tdd", "user version")
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=cwd, backend="claude")
    assert catalog["tdd"].source_location == "user"
