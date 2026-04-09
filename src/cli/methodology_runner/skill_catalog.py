"""Auto-discovery of Claude Code skills from the local filesystem.

Walks three locations in priority order, parses SKILL.md YAML
frontmatter, and returns an in-memory catalog keyed by skill ID.

Priority order (highest first):

1. ``<workspace>/.claude/skills/**/SKILL.md``
2. ``~/.claude/skills/**/SKILL.md``
3. ``~/.claude/plugins/*/skills/**/SKILL.md``

Higher-priority locations shadow lower ones; overrides are logged.
If the final catalog is empty, :class:`CatalogBuildError` is raised
so the orchestrator can halt before any phase runs (spec failure
mode 7).

The catalog is never persisted to disk.  SKILL.md files on disk are
the single source of truth; the catalog is rebuilt on every run.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .models import SkillCatalogEntry


logger = logging.getLogger(__name__)


_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL
)
"""Matches a SKILL.md YAML frontmatter block at the start of the file."""

_VALID_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
"""Valid skill IDs are lowercase kebab-case, starting with a letter or digit."""


class CatalogBuildError(RuntimeError):
    """Raised when catalog discovery cannot yield at least one valid skill."""


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    """Extract simple ``key: value`` pairs from a SKILL.md frontmatter block.

    Returns None if the file has no frontmatter.  We intentionally do
    not bring in PyYAML for this — SKILL.md frontmatter fields we care
    about (``name``, ``description``) are always plain strings, and a
    small hand-rolled parser avoids a dependency.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None
    body = match.group(1)
    out: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def parse_skill_md(
    path: Path, source_location: str,
) -> SkillCatalogEntry | None:
    """Parse a single SKILL.md file.  Returns None on any validation failure.

    Invalid entries are logged at WARNING level but do not halt the
    catalog build — they are simply skipped.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("skill_catalog: cannot read %s: %s", path, exc)
        return None

    frontmatter = _parse_frontmatter(text)
    if frontmatter is None:
        logger.warning("skill_catalog: %s has no YAML frontmatter; skipping", path)
        return None

    skill_id = frontmatter.get("name") or path.parent.name
    if not skill_id or not _VALID_ID_RE.match(skill_id):
        logger.warning(
            "skill_catalog: %s has invalid or missing id %r; skipping",
            path, skill_id,
        )
        return None

    description = frontmatter.get("description", "").strip()
    if not description:
        logger.warning(
            "skill_catalog: %s has empty description; skipping", path,
        )
        return None

    return SkillCatalogEntry(
        id=skill_id,
        description=description,
        source_path=path.resolve(),
        source_location=source_location,
    )


def _walk_skills(root: Path) -> list[Path]:
    """Yield every SKILL.md path under *root*.  Missing root is fine."""
    if not root.exists():
        return []
    return sorted(root.rglob("SKILL.md"))


def build_catalog(
    *,
    workspace: Path,
    user_home: Path | None = None,
) -> dict[str, SkillCatalogEntry]:
    """Build the skill catalog by walking the three discovery locations.

    Parameters
    ----------
    workspace:
        The methodology-runner workspace directory.  Project-local
        skills live under ``<workspace>/.claude/skills/``.
    user_home:
        Home directory to look under.  Defaults to ``Path.home()``.
        Exposed for testing.

    Returns
    -------
    dict[str, SkillCatalogEntry]
        Keyed by skill ID.  Higher-priority locations shadow lower
        ones; every shadow is logged at INFO level.

    Raises
    ------
    CatalogBuildError
        If no valid skills are discovered across all three locations.
    """
    if user_home is None:
        user_home = Path.home()

    # (location_label, root_path) in priority order: first wins.
    sources: list[tuple[str, Path]] = [
        ("project", workspace / ".claude" / "skills"),
        ("user", user_home / ".claude" / "skills"),
    ]
    # Plugins: one sub-root per plugin directory under ~/.claude/plugins
    plugins_dir = user_home / ".claude" / "plugins"
    if plugins_dir.exists():
        for plugin in sorted(plugins_dir.iterdir()):
            if plugin.is_dir():
                sources.append(("plugin", plugin / "skills"))

    catalog: dict[str, SkillCatalogEntry] = {}
    for source_location, root in sources:
        for skill_md in _walk_skills(root):
            entry = parse_skill_md(skill_md, source_location=source_location)
            if entry is None:
                continue
            existing = catalog.get(entry.id)
            if existing is None:
                catalog[entry.id] = entry
                continue
            # Shadowing: higher priority was registered first, so
            # keep existing and log the override.
            logger.info(
                "skill_catalog: %s at %s shadowed by %s at %s",
                entry.id,
                entry.source_path,
                existing.source_location,
                existing.source_path,
            )

    if not catalog:
        raise CatalogBuildError(
            "no Claude Code skills discovered.\n\n"
            "Searched:\n"
            + "\n".join(f"  - {lbl}: {root}" for lbl, root in sources)
            + "\n\nInstall the baseline skill pack with:\n"
            "  /plugin install methodology-runner-skills\n"
            "Or place your own SKILL.md files under .claude/skills/ in "
            "this workspace, or under ~/.claude/skills/ for your user."
        )

    return catalog
