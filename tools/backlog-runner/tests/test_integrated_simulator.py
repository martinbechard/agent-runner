from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from backlog_runner.models import BacklogState, ItemStatus, MergeOutcome
from backlog_runner.paths import BacklogPaths
from backlog_runner.supervisor import SupervisorConfig, run_once


MAX_WORKERS = 1
NO_FAILURES = 0
SUCCESS_EXIT_CODE = 0
TARGET_BRANCH = "main"
FEATURE_ITEM_FILENAME = "Add Search.md"
FEATURE_ITEM_KEY = "feature:add-search"
FEATURE_CHANGE_ID = "feature-add-search"
SIMULATOR_SCRIPT = "fixtures/methodology_runner_simulator.py"
INITIAL_COMMIT_MESSAGE = "Initial backlog"


def test_once_runs_simulated_methodology_merges_and_archives(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "app"
    simulator_path = Path(__file__).parent / SIMULATOR_SCRIPT
    _initialize_repo_with_backlog_item(repo)

    result = run_once(
        SupervisorConfig(
            backlog_root=repo,
            application_repo=repo,
            target_branch=TARGET_BRANCH,
            base_branch=TARGET_BRANCH,
            methodology_runner_command=f"{sys.executable} {simulator_path}",
            max_workers=MAX_WORKERS,
        ),
    )

    paths = BacklogPaths(repo)
    state = BacklogState.load(paths.state_file)
    record = state.records[FEATURE_ITEM_KEY]
    merge_result = json.loads(
        paths.merge_result_path(FEATURE_ITEM_KEY).read_text(encoding="utf-8"),
    )

    assert result.dispatched == MAX_WORKERS
    assert result.merged == MAX_WORKERS
    assert result.failed == NO_FAILURES
    assert record.status == ItemStatus.COMPLETED
    assert (repo / "simulated-delivery" / f"{FEATURE_CHANGE_ID}.txt").exists()
    assert not (repo / "docs" / "feature-backlog" / FEATURE_ITEM_FILENAME).exists()
    assert (
        repo
        / "docs"
        / "completed-backlog"
        / "features"
        / FEATURE_ITEM_FILENAME
    ).exists()
    assert merge_result["outcome"] == MergeOutcome.MERGED.value
    assert merge_result["source_branch"] == FEATURE_CHANGE_ID
    assert merge_result["target_branch"] == TARGET_BRANCH
    assert _git(repo, "branch", "--show-current") == TARGET_BRANCH
    assert _git(repo, "status", "--porcelain") == ""


def _initialize_repo_with_backlog_item(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init", "-b", TARGET_BRANCH)
    _git(repo, "config", "user.email", "tester@example.com")
    _git(repo, "config", "user.name", "Tester")
    feature_dir = repo / "docs" / "feature-backlog"
    feature_dir.mkdir(parents=True)
    (repo / "README.md").write_text("# Test App\n", encoding="utf-8")
    (feature_dir / FEATURE_ITEM_FILENAME).write_text(
        "# Add Search\n\nBuild a search entry point.\n",
        encoding="utf-8",
    )
    _git(repo, "add", "README.md", str(feature_dir / FEATURE_ITEM_FILENAME))
    _git(repo, "commit", "-m", INITIAL_COMMIT_MESSAGE)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == SUCCESS_EXIT_CODE, result.stderr
    return result.stdout.strip()
