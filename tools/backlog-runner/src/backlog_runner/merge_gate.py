"""Serialized target merge gate."""

from __future__ import annotations

import json
from pathlib import Path

from backlog_runner.git_ops import GitError, commit_all, git, rev_parse, status_porcelain
from backlog_runner.models import BacklogItemRecord, MergeOutcome, MergeResult
from backlog_runner.paths import BacklogPaths


HANDOFF_PENDING_STATUS = "target_merge_pending"


class MergeGateError(RuntimeError):
    """Raised when merge handoff validation fails."""


def merge_record(
    *,
    paths: BacklogPaths,
    application_repo: Path,
    record: BacklogItemRecord,
    target_branch: str,
) -> MergeResult:
    """Merge one target_merge_pending item into the target branch."""
    try:
        handoff = _load_handoff(record)
        source_branch = str(handoff["source_branch"])
        handoff_target_branch = str(handoff["target_branch"])
        source_commit = _optional_string(handoff.get("source_commit"))
        handoff_commit = _optional_string(handoff.get("handoff_commit"))
        if handoff.get("status") != HANDOFF_PENDING_STATUS:
            raise MergeGateError("target merge handoff is not pending")
        if handoff_target_branch != target_branch:
            raise MergeGateError(
                f"handoff target {handoff_target_branch} does not match {target_branch}",
            )
        if source_commit is not None and not is_source_commit_valid(
            application_repo,
            source_commit,
            source_branch,
        ):
            raise MergeGateError(
                f"source commit {source_commit} is not on {source_branch}",
            )
        if status_porcelain(application_repo):
            raise MergeGateError(f"target worktree is not clean: {application_repo}")
        if handoff_commit is not None:
            git(application_repo, "merge", "--squash", handoff_commit)
        else:
            git(application_repo, "merge", "--squash", source_branch)
        target_commit = commit_all(application_repo, f"Apply {record.change_id}")
        result = MergeResult(
            item_key=record.item_key,
            outcome=MergeOutcome.MERGED,
            source_branch=source_branch,
            target_branch=target_branch,
            source_commit=source_commit,
            target_commit=target_commit,
        )
    except (GitError, MergeGateError, KeyError) as exc:
        _abort_merge(application_repo)
        result = MergeResult(
            item_key=record.item_key,
            outcome=MergeOutcome.MERGE_FAILED,
            source_branch=record.branch_name,
            target_branch=target_branch,
            failure_reason=str(exc),
        )
    write_merge_result(paths, result)
    return result


def is_source_commit_valid(repo: Path, source_commit: str, source_branch: str) -> bool:
    """Return whether source_commit is reachable from source_branch."""
    try:
        rev_parse(repo, source_commit)
        rev_parse(repo, source_branch)
    except GitError:
        return False
    from backlog_runner.git_ops import is_ancestor

    return is_ancestor(repo, source_commit, source_branch)


def write_merge_result(paths: BacklogPaths, result: MergeResult) -> Path:
    """Write one merge result."""
    path = paths.merge_result_path(result.item_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return path


def _load_handoff(record: BacklogItemRecord) -> dict[str, object]:
    path = (
        record.workspace_path
        / "docs"
        / "changes"
        / record.change_id
        / "execution"
        / "target-merge-handoff.json"
    )
    if not path.exists():
        raise MergeGateError(f"target merge handoff not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MergeGateError("target merge handoff is not an object")
    return data


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _abort_merge(repo: Path) -> None:
    try:
        git(repo, "merge", "--abort")
    except GitError:
        try:
            git(repo, "reset", "--merge")
        except GitError:
            return
