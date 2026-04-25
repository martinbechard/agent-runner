from __future__ import annotations

from pathlib import Path

from backlog_runner.models import BacklogItemRecord, ItemStatus, ItemType
from backlog_runner.worker import WorkerLaunchConfig, build_worker_command


def test_build_worker_command_uses_skip_target_merge(tmp_path: Path) -> None:
    record = BacklogItemRecord(
        item_key="feature:add-search",
        item_type=ItemType.FEATURE,
        slug="add-search",
        source_path=tmp_path / "docs" / "feature-backlog" / "add-search.md",
        status=ItemStatus.QUEUED,
        change_id="feature-add-search",
        branch_name="feature-add-search",
        workspace_path=tmp_path / "app-worktrees" / "feature-add-search",
    )
    config = WorkerLaunchConfig(
        methodology_runner_command="python -m methodology_runner",
        application_repo=tmp_path / "app",
        target_branch="main",
        base_branch="main",
        backend="codex",
        model="gpt-test",
        max_iterations=2,
    )

    command = build_worker_command(record, config)

    assert command[:4] == ["python", "-m", "methodology_runner", "run"]
    assert "--application-repo" in command
    assert "--target-branch" in command
    assert "--base-branch" in command
    assert "--skip-target-merge" in command
    assert "--max-iterations" in command
