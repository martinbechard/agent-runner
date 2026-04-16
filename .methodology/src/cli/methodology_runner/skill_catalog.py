"""Auto-discovery of backend skills from the local filesystem.

Walks five locations in priority order, parses SKILL.md YAML
frontmatter, and returns an in-memory catalog keyed by skill ID.

Priority order (highest first):

1. ``<workspace>/.<backend>/skills/**/SKILL.md``
2. ``<cwd>/.methodology/skills/**/SKILL.md``
3. ``<cwd>/plugins/*/skills/**/SKILL.md``
4. ``~/.<backend>/skills/**/SKILL.md``
5. ``~/.<backend>/plugins/*/skills/**/SKILL.md``

Higher-priority locations shadow lower ones; overrides are logged.
If the final catalog is empty, :class:`CatalogBuildError` is raised
so the orchestrator can halt before any phase runs (spec failure
mode 7).

The repo-methodology slot (priority 2) lets this repository ship its
own methodology skills under ``.methodology/skills/`` without mixing
them into the project tree. The cwd-plugin slot remains as a lower-
priority compatibility path for generic plugin-based skill packs.

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
    backend: str = "codex",
    user_home: Path | None = None,
    cwd: Path | None = None,
) -> dict[str, SkillCatalogEntry]:
    """Build the skill catalog by walking the five discovery locations.

    Parameters
    ----------
    workspace:
        The methodology-runner workspace directory.  Project-local
        skills live under ``<workspace>/.<backend>/skills/``.
    backend:
        Skill namespace to search under.  Typically ``claude`` or ``codex``.
    user_home:
        Home directory to look under.  Defaults to ``Path.home()``.
        Exposed for testing.
    cwd:
        Working directory to check for repo-local methodology skills and
        compatibility plugin skill packs. Defaults to ``Path.cwd()``.

    Returns
    -------
    dict[str, SkillCatalogEntry]
        Keyed by skill ID.  Higher-priority locations shadow lower
        ones; every shadow is logged at INFO level.

    Raises
    ------
    CatalogBuildError
        If no valid skills are discovered across all five locations.
    """
    if user_home is None:
        user_home = Path.home()
    if cwd is None:
        cwd = Path.cwd()

    # (location_label, root_path) in priority order: first wins.
    # Priority: project > repo-methodology > cwd-plugin > user > plugin.
    sources: list[tuple[str, Path]] = [
        ("project", workspace / f".{backend}" / "skills"),
        ("repo-methodology", cwd / ".methodology" / "skills"),
    ]

    # cwd-plugin discovery: walk <cwd>/plugins/*/skills/ as a compatibility
    # path for repo-local plugin packs. Placed after repo-methodology so the
    # canonical methodology tree wins, but before user and user-installed
    # plugins so repo-local dev versions still shadow installed versions.
    cwd_plugins_dir = cwd / "plugins"
    if cwd_plugins_dir.exists():
        for plugin in sorted(cwd_plugins_dir.iterdir()):
            if plugin.is_dir():
                sources.append(("cwd-plugin", plugin / "skills"))

    sources.append(("user", user_home / f".{backend}" / "skills"))

    # Plugins: one sub-root per plugin directory under ~/.<backend>/plugins
    plugins_dir = user_home / f".{backend}" / "plugins"
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
            f"no {backend} skills discovered.\n\n"
            "Searched:\n"
            + "\n".join(f"  - {lbl}: {root}" for lbl, root in sources)
            + "\n\nAdd skills in one of these places:\n"
            + f"  - <repo>/.methodology/skills/\n"
            + f"  - <workspace>/.{backend}/skills/\n"
            + f"  - ~/.{backend}/skills/\n"
        )

    return catalog
