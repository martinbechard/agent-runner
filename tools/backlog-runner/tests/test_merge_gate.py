from __future__ import annotations

import json
import subprocess
from pathlib import Path

from backlog_runner.merge_gate import merge_record
from backlog_runner.models import BacklogItemRecord, ItemStatus, ItemType, MergeOutcome
from backlog_runner.paths import BacklogPaths


def test_merge_record_squash_merges_feature_branch(tmp_path: Path) -> None:
    repo = tmp_path / "app"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "tester@example.com")
    _git(repo, "config", "user.name", "Tester")
    (repo / "README.md").write_text("# App\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "Initial")
    _git(repo, "checkout", "-b", "feature-add-search")
    (repo / "search.txt").write_text("search\n", encoding="utf-8")
    _git(repo, "add", "search.txt")
    _git(repo, "commit", "-m", "Add search")
    source_commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "main")

    workspace = tmp_path / "app-worktrees" / "feature-add-search"
    handoff = (
        workspace
        / "docs"
        / "changes"
        / "feature-add-search"
        / "execution"
        / "target-merge-handoff.json"
    )
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        json.dumps(
            {
                "change_id": "feature-add-search",
                "source_branch": "feature-add-search",
                "target_branch": "main",
                "source_commit": source_commit,
                "handoff_commit": None,
                "base_commit": None,
                "status": "target_merge_pending",
            },
        ) + "\n",
        encoding="utf-8",
    )
    record = BacklogItemRecord(
        item_key="feature:add-search",
        item_type=ItemType.FEATURE,
        slug="add-search",
        source_path=tmp_path / "docs" / "feature-backlog" / "add-search.md",
        status=ItemStatus.TARGET_MERGE_PENDING,
        change_id="feature-add-search",
        branch_name="feature-add-search",
        workspace_path=workspace,
    )

    result = merge_record(
        paths=BacklogPaths(tmp_path),
        application_repo=repo,
        record=record,
        target_branch="main",
    )

    assert result.outcome == MergeOutcome.MERGED
    assert result.target_commit is not None
    assert (repo / "search.txt").read_text(encoding="utf-8") == "search\n"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()
