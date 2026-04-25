from __future__ import annotations

import json
import subprocess
from pathlib import Path

from methodology_runner.models import ProjectState
from methodology_runner.orchestrator import PipelineConfig, _automate_completed_lifecycle


def test_completed_lifecycle_can_skip_target_merge(tmp_path: Path) -> None:
    repo = tmp_path / "app"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "tester@example.com")
    _git(repo, "config", "user.name", "Tester")
    _git(repo, "commit", "--allow-empty", "-m", "Initial")

    worktrees = tmp_path / "worktrees"
    worktrees.mkdir()
    feature_worktree = worktrees / "feature-add-search"
    _git(repo, "worktree", "add", str(feature_worktree), "-b", "feature-add-search")
    _write_lifecycle_inputs(feature_worktree)
    (feature_worktree / "search.txt").write_text("search\n", encoding="utf-8")

    requirements_path = feature_worktree / "docs" / "requirements" / "raw-requirements.md"
    state = ProjectState(
        workspace_dir=feature_worktree,
        requirements_path=requirements_path,
        phase_results={},
        started_at="2026-04-24T00:00:00Z",
        git_initialized=True,
        change_id="feature-add-search",
    )
    config = PipelineConfig(
        requirements_path=requirements_path,
        workspace_dir=feature_worktree,
        skip_target_merge=True,
        target_branch="main",
    )

    error = _automate_completed_lifecycle(state, feature_worktree, config)

    assert error is None
    assert not (repo / "search.txt").exists()
    assert not (feature_worktree / ".methodology-runner").exists()
    handoff_path = (
        feature_worktree
        / "docs"
        / "changes"
        / "feature-add-search"
        / "execution"
        / "target-merge-handoff.json"
    )
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff["status"] == "target_merge_pending"
    assert handoff["source_branch"] == "feature-add-search"
    assert handoff["target_branch"] == "main"
    assert handoff["source_commit"]


def _write_lifecycle_inputs(workspace: Path) -> None:
    (workspace / ".methodology-runner").mkdir(parents=True)
    summary_dir = workspace / ".run-files" / "methodology-runner"
    summary_dir.mkdir(parents=True)
    (summary_dir / "summary.txt").write_text("summary\n", encoding="utf-8")
    _write(workspace / "docs/requirements/raw-requirements.md", "# Requirements\n")
    _write(workspace / "docs/requirements/requirements-inventory.yaml", "items: []\n")
    _write(
        workspace / "docs/requirements/requirements-inventory-coverage.yaml",
        "coverage_verdict:\n  verdict: PASS\n",
    )
    _write(
        workspace / "docs/features/feature-specification.yaml",
        "features:\n"
        "  - id: FT-001\n"
        "    name: Search\n"
        "    description: Add search.\n"
        "    acceptance_criteria: []\n"
        "cross_cutting_concerns: []\n"
        "out_of_scope: []\n",
    )
    _write(workspace / "docs/architecture/architecture-design.yaml", "components: []\n")
    _write(
        workspace / "docs/design/solution-design.yaml",
        "components:\n"
        "  - id: CMP-001\n"
        "    name: Search component\n"
        "    responsibility: Run search.\n"
        "    technology: Python\n"
        "    feature_realization_map:\n"
        "      FT-001: Implements search.\n"
        "    dependencies: []\n"
        "    processing_functions: []\n"
        "    ui_surfaces: []\n"
        "implementation_files:\n"
        "  - path: search.py\n"
        "    role: source\n"
        "    component_refs: [CMP-001]\n"
        "    artifact_ref: null\n"
        "    features_supported: [FT-001]\n"
        "    purpose: Contains search implementation.\n"
        "interactions: []\n",
    )
    _write(
        workspace / "docs/design/interface-contracts.yaml",
        "contracts: []\n",
    )
    _write(workspace / "docs/simulations/simulation-definitions.yaml", "simulations: []\n")
    _write(workspace / "docs/implementation/implementation-workflow.md", "workflow\n")
    _write(
        workspace / "docs/implementation/implementation-run-report.yaml",
        "completion_status: completed\n",
    )
    _write(
        workspace / "docs/verification/verification-report.yaml",
        "coverage_summary:\n  satisfaction_percentage: 100\n",
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
