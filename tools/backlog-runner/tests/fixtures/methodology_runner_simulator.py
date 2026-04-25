"""Test fixture that simulates methodology-runner deferred merge output."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


HANDOFF_STATUS = "target_merge_pending"
RUN_COMMAND = "run"
DEFAULT_TARGET_BRANCH = "main"
DELIVERY_DIRNAME = "simulated-delivery"
HANDOFF_FILENAME = "target-merge-handoff.json"
GIT_USER_EMAIL = "simulator@example.com"
GIT_USER_NAME = "Methodology Runner Simulator"
SUCCESS_EXIT_CODE = 0
ERROR_EXIT_CODE = 1
EMPTY_TREE_EXIT_CODE = 1


class SimulatorError(RuntimeError):
    """Raised when the simulator cannot produce a valid handoff."""


def main(argv: list[str] | None = None) -> int:
    """Run the simulator CLI."""
    try:
        args = parse_args(argv)
        simulate_run(args)
    except SimulatorError as exc:
        print(str(exc), file=sys.stderr)
        return ERROR_EXIT_CODE
    return SUCCESS_EXIT_CODE


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the methodology-runner subset used by backlog-runner."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser(RUN_COMMAND)
    run_parser.add_argument("requirements_file", type=Path)
    run_parser.add_argument("--application-repo", type=Path, required=True)
    run_parser.add_argument("--change-id", required=True)
    run_parser.add_argument("--branch-name", required=True)
    run_parser.add_argument("--workspace", type=Path, required=True)
    run_parser.add_argument("--target-branch", default=DEFAULT_TARGET_BRANCH)
    run_parser.add_argument("--base-branch")
    run_parser.add_argument("--skip-target-merge", action="store_true")
    run_parser.add_argument("--backend")
    run_parser.add_argument("--model")
    run_parser.add_argument("--max-iterations")
    return parser.parse_args(argv)


def simulate_run(args: argparse.Namespace) -> None:
    """Create a feature worktree, commit simulated work, and write a handoff."""
    if args.command != RUN_COMMAND:
        raise SimulatorError(f"unsupported command: {args.command}")
    if not args.skip_target_merge:
        raise SimulatorError("simulator expects --skip-target-merge")
    requirements_file = args.requirements_file.resolve()
    application_repo = args.application_repo.resolve()
    workspace = args.workspace.resolve()
    target_branch = str(args.target_branch)
    base_ref = str(args.base_branch or args.target_branch)
    change_id = str(args.change_id)
    branch_name = str(args.branch_name)

    ensure_worktree(
        application_repo=application_repo,
        workspace=workspace,
        branch_name=branch_name,
        base_ref=base_ref,
    )
    configure_git_user(workspace)
    delivery_path = write_delivery_file(
        workspace=workspace,
        requirements_file=requirements_file,
        change_id=change_id,
    )
    commit_if_needed(workspace, f"Simulate methodology delivery {change_id}")
    source_commit = git(workspace, "rev-parse", "HEAD")
    base_commit = git(application_repo, "rev-parse", target_branch)
    handoff_path = write_handoff(
        workspace=workspace,
        change_id=change_id,
        branch_name=branch_name,
        target_branch=target_branch,
        source_commit=source_commit,
        base_commit=base_commit,
    )
    commit_if_needed(workspace, f"Record target merge handoff {change_id}")
    if not delivery_path.exists() or not handoff_path.exists():
        raise SimulatorError("simulator did not write expected artifacts")


def ensure_worktree(
    *,
    application_repo: Path,
    workspace: Path,
    branch_name: str,
    base_ref: str,
) -> None:
    """Create the feature worktree when it does not already exist."""
    if workspace.exists():
        return
    workspace.parent.mkdir(parents=True, exist_ok=True)
    git(
        application_repo,
        "worktree",
        "add",
        str(workspace),
        "-b",
        branch_name,
        base_ref,
    )


def configure_git_user(workspace: Path) -> None:
    """Set deterministic commit identity for the simulator worktree."""
    git(workspace, "config", "user.email", GIT_USER_EMAIL)
    git(workspace, "config", "user.name", GIT_USER_NAME)


def write_delivery_file(
    *,
    workspace: Path,
    requirements_file: Path,
    change_id: str,
) -> Path:
    """Write a deterministic delivery artifact from the backlog item."""
    delivery_path = workspace / DELIVERY_DIRNAME / f"{change_id}.txt"
    delivery_path.parent.mkdir(parents=True, exist_ok=True)
    source_text = requirements_file.read_text(encoding="utf-8")
    delivery_path.write_text(
        f"change_id: {change_id}\n\n{source_text}",
        encoding="utf-8",
    )
    return delivery_path


def write_handoff(
    *,
    workspace: Path,
    change_id: str,
    branch_name: str,
    target_branch: str,
    source_commit: str,
    base_commit: str,
) -> Path:
    """Write the deferred target merge handoff expected by backlog-runner."""
    handoff_path = (
        workspace
        / "docs"
        / "changes"
        / change_id
        / "execution"
        / HANDOFF_FILENAME
    )
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "change_id": change_id,
        "source_branch": branch_name,
        "target_branch": target_branch,
        "source_commit": source_commit,
        "handoff_commit": None,
        "base_commit": base_commit,
        "status": HANDOFF_STATUS,
    }
    handoff_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return handoff_path


def commit_if_needed(repo: Path, message: str) -> str:
    """Commit pending changes and return HEAD."""
    git(repo, "add", "-A")
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == SUCCESS_EXIT_CODE:
        return git(repo, "rev-parse", "HEAD")
    if result.returncode != EMPTY_TREE_EXIT_CODE:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SimulatorError(f"git diff --cached --quiet failed: {detail}")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def git(repo: Path, *args: str) -> str:
    """Run git in repo and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SimulatorError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
