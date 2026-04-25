"""Backlog folder scanner."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from backlog_runner.models import BacklogItem
from backlog_runner.paths import ACTIVE_FOLDER_TYPES


MARKDOWN_SUFFIX = ".md"
DEPENDENCIES_HEADING_RE = re.compile(r"^#{1,6}\s+dependencies\s*$", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s+")
INLINE_DEPENDENCIES_RE = re.compile(r"^dependencies\s*:\s*(.+)$", re.IGNORECASE)
SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class InvalidBacklogFile:
    """Invalid backlog file discovered during scanning."""

    path: Path
    reason: str


@dataclass(frozen=True)
class ScanResult:
    """Scanner output."""

    items: list[BacklogItem] = field(default_factory=list)
    invalid_files: list[InvalidBacklogFile] = field(default_factory=list)


def scan_backlog(backlog_root: Path) -> ScanResult:
    """Scan active backlog folders under *backlog_root*."""
    items: list[BacklogItem] = []
    invalid_files: list[InvalidBacklogFile] = []
    for rel_dir, item_type in ACTIVE_FOLDER_TYPES:
        folder = backlog_root / rel_dir
        if not folder.exists():
            continue
        for path in sorted(folder.glob(f"*{MARKDOWN_SUFFIX}")):
            slug = slugify(path.stem)
            if not slug:
                invalid_files.append(
                    InvalidBacklogFile(path=path, reason="empty slug"),
                )
                continue
            try:
                dependencies = parse_dependencies(path)
            except OSError as exc:
                invalid_files.append(
                    InvalidBacklogFile(path=path, reason=str(exc)),
                )
                continue
            items.append(
                BacklogItem(
                    item_type=item_type,
                    slug=slug,
                    source_path=path,
                    dependencies=dependencies,
                ),
            )
    return ScanResult(items=items, invalid_files=invalid_files)


def slugify(value: str) -> str:
    """Return a stable slug for a backlog filename stem."""
    return SLUG_RE.sub("-", value.lower()).strip("-")


def parse_dependencies(path: Path) -> list[str]:
    """Parse simple dependency metadata from a backlog item."""
    lines = path.read_text(encoding="utf-8").splitlines()
    dependencies: list[str] = []
    in_dependencies = False
    for line in lines:
        stripped = line.strip()
        inline_match = INLINE_DEPENDENCIES_RE.match(stripped)
        if inline_match is not None:
            dependencies.extend(_split_dependency_text(inline_match.group(1)))
            continue
        if DEPENDENCIES_HEADING_RE.match(stripped):
            in_dependencies = True
            continue
        if in_dependencies and HEADING_RE.match(stripped):
            in_dependencies = False
        if not in_dependencies:
            continue
        if stripped.startswith(("-", "*")):
            dependencies.extend(_split_dependency_text(stripped[1:].strip()))
    return dependencies


def _split_dependency_text(value: str) -> list[str]:
    """Split a dependency list into normalized slugs."""
    return [
        slugify(part)
        for part in re.split(r"[, ]+", value)
        if slugify(part)
    ]
