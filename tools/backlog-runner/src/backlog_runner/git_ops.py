"""Git command helpers for backlog-runner."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """Raised when a git command fails."""


def git(repo: Path, *args: str) -> str:
    """Run git in *repo* and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise GitError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def status_porcelain(repo: Path) -> str:
    """Return git status porcelain output."""
    return git(repo, "status", "--porcelain")


def current_branch(repo: Path) -> str:
    """Return the current branch name."""
    return git(repo, "branch", "--show-current")


def rev_parse(repo: Path, ref: str) -> str:
    """Resolve a git ref to a commit."""
    return git(repo, "rev-parse", ref)


def commit_all(repo: Path, message: str) -> str:
    """Stage all changes and commit when needed."""
    git(repo, "add", "-A")
    if not status_porcelain(repo):
        return rev_parse(repo, "HEAD")
    git(repo, "commit", "-m", message)
    return rev_parse(repo, "HEAD")


def commit_paths(repo: Path, message: str, paths: list[Path]) -> str:
    """Stage selected paths and commit when needed."""
    relative_paths = [_relative_to_repo(repo, path) for path in paths]
    git(repo, "add", "-A", "--", *relative_paths)
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return rev_parse(repo, "HEAD")
    git(repo, "commit", "-m", message)
    return rev_parse(repo, "HEAD")


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    """Return whether *ancestor* is an ancestor of *descendant*."""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _relative_to_repo(repo: Path, path: Path) -> str:
    """Return *path* relative to repo."""
    return str(path.resolve().relative_to(repo.resolve()))
