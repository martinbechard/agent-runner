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
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=tmp_path)
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
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=tmp_path)
    assert catalog["same"].description == "from project"
    assert catalog["same"].source_location == "project"


def test_build_catalog_empty_raises_catalog_build_error(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    workspace.mkdir()
    user_home.mkdir()
    with pytest.raises(CatalogBuildError) as exc_info:
        build_catalog(workspace=workspace, user_home=user_home, cwd=tmp_path)
    assert "no claude code skills discovered" in str(exc_info.value).lower()


def test_build_catalog_skips_invalid_entries_but_keeps_valid_ones(tmp_path: Path):
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    _write_skill(user_home / ".claude" / "skills", "good", "Good skill")
    # Invalid one
    bad = user_home / ".claude" / "skills" / "bad" / "SKILL.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("# no frontmatter", encoding="utf-8")
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=tmp_path)
    assert "good" in catalog
    assert "bad" not in catalog


def test_build_catalog_walks_cwd_plugins_dir(tmp_path: Path):
    """cwd-based plugin discovery: if cwd/plugins/<pack>/skills/ exists,
    SKILL.md files under it are discovered without any symlink setup."""
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    cwd = tmp_path / "repo"
    # Don't put skills in workspace, user, or ~/.claude/plugins —
    # only in cwd/plugins. Discovery should still find them.
    _write_skill(
        cwd / "plugins" / "methodology-runner-skills" / "skills",
        "tdd", "Test-driven development",
    )
    _write_skill(
        cwd / "plugins" / "methodology-runner-skills" / "skills",
        "traceability-discipline", "Universal traceability",
    )
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=cwd)
    assert "tdd" in catalog
    assert "traceability-discipline" in catalog
    assert catalog["tdd"].source_location == "cwd-plugin"


def test_cwd_plugin_shadows_user_installed_plugin(tmp_path: Path):
    """When the same skill exists in cwd/plugins/ and ~/.claude/plugins/,
    the cwd version wins (dev override)."""
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    cwd = tmp_path / "repo"
    _write_skill(
        cwd / "plugins" / "methodology-runner-skills" / "skills",
        "tdd", "dev version",
    )
    _write_skill(
        user_home / ".claude" / "plugins" / "some-pack" / "skills",
        "tdd", "installed version",
    )
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=cwd)
    assert catalog["tdd"].description == "dev version"
    assert catalog["tdd"].source_location == "cwd-plugin"


def test_project_local_still_beats_cwd_plugin(tmp_path: Path):
    """Workspace-local skills still take priority over cwd plugins."""
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    cwd = tmp_path / "repo"
    _write_skill(workspace / ".claude" / "skills", "tdd", "workspace version")
    _write_skill(
        cwd / "plugins" / "methodology-runner-skills" / "skills",
        "tdd", "cwd version",
    )
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=cwd)
    assert catalog["tdd"].description == "workspace version"
    assert catalog["tdd"].source_location == "project"


def test_build_catalog_defaults_cwd_to_current_working_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """When cwd is not passed, Path.cwd() is used."""
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    fake_cwd = tmp_path / "repo"
    _write_skill(
        fake_cwd / "plugins" / "pack" / "skills", "tdd", "from cwd",
    )
    monkeypatch.chdir(fake_cwd)
    catalog = build_catalog(workspace=workspace, user_home=user_home)
    # cwd should default to Path.cwd() which is now fake_cwd
    assert "tdd" in catalog
    assert catalog["tdd"].description == "from cwd"


def test_empty_cwd_plugins_dir_does_not_affect_discovery(tmp_path: Path):
    """If cwd/plugins exists but is empty, discovery still works."""
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    cwd = tmp_path / "repo"
    (cwd / "plugins").mkdir(parents=True)  # empty plugins dir
    _write_skill(user_home / ".claude" / "skills", "tdd", "user version")
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=cwd)
    assert catalog["tdd"].source_location == "user"


def test_nonexistent_cwd_plugins_dir_is_skipped(tmp_path: Path):
    """If cwd/plugins does not exist at all, no error — just skip it."""
    workspace = tmp_path / "ws"
    user_home = tmp_path / "home"
    cwd = tmp_path / "repo"
    cwd.mkdir()  # exists but no plugins subdir
    _write_skill(user_home / ".claude" / "skills", "tdd", "user version")
    catalog = build_catalog(workspace=workspace, user_home=user_home, cwd=cwd)
    assert catalog["tdd"].source_location == "user"
