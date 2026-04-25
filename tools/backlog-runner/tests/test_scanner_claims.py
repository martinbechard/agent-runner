from __future__ import annotations

from pathlib import Path

from backlog_runner.claims import create_claim
from backlog_runner.models import ItemType
from backlog_runner.paths import BacklogPaths
from backlog_runner.scanner import scan_backlog


def test_scan_backlog_discovers_typed_items_and_dependencies(tmp_path: Path) -> None:
    backlog_root = tmp_path
    feature_dir = backlog_root / "docs" / "feature-backlog"
    feature_dir.mkdir(parents=True)
    item_path = feature_dir / "Add Search.md"
    item_path.write_text(
        "# Add Search\n\nDependencies: base-login, account-page\n",
        encoding="utf-8",
    )

    result = scan_backlog(backlog_root)

    assert result.invalid_files == []
    assert len(result.items) == 1
    item = result.items[0]
    assert item.item_type == ItemType.FEATURE
    assert item.slug == "add-search"
    assert item.dependencies == ["base-login", "account-page"]


def test_create_claim_is_atomic_per_item(tmp_path: Path) -> None:
    backlog_root = tmp_path
    feature_dir = backlog_root / "docs" / "feature-backlog"
    feature_dir.mkdir(parents=True)
    item_path = feature_dir / "Add Search.md"
    item_path.write_text("# Add Search\n", encoding="utf-8")
    item = scan_backlog(backlog_root).items[0]
    paths = BacklogPaths(backlog_root)

    first = create_claim(paths, item)
    second = create_claim(paths, item)

    assert first is not None
    assert second is None
    assert paths.claim_path(item.key).exists()
