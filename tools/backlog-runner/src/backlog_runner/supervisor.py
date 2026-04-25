"""Backlog-runner supervisor."""

from __future__ import annotations

import fcntl
import os
import time
from dataclasses import dataclass
from pathlib import Path

from backlog_runner.archive import archive_completed, archive_failed
from backlog_runner.claims import create_claim, release_claim
from backlog_runner.git_ops import GitError, commit_paths, git
from backlog_runner.merge_gate import merge_record
from backlog_runner.models import (
    BacklogItem,
    BacklogItemRecord,
    BacklogState,
    ItemStatus,
    MergeOutcome,
    WorkerOutcome,
)
from backlog_runner.paths import BacklogPaths
from backlog_runner.scanner import InvalidBacklogFile, scan_backlog
from backlog_runner.worker import (
    RunningWorker,
    WorkerLaunchConfig,
    reap_worker,
    start_worker,
)


DEFAULT_MAX_WORKERS = 2
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
LOCK_MODE = "w"


class SupervisorLockError(RuntimeError):
    """Raised when another supervisor owns the BacklogRoot."""


@dataclass(frozen=True)
class SupervisorConfig:
    """Runtime configuration for the backlog supervisor."""

    backlog_root: Path
    application_repo: Path
    target_branch: str
    base_branch: str | None = None
    backend: str | None = None
    model: str | None = None
    max_workers: int = DEFAULT_MAX_WORKERS
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    methodology_runner_command: str = "methodology-runner"
    max_iterations: int | None = None
    dry_run: bool = False


@dataclass(frozen=True)
class SupervisorRunResult:
    """Summary returned by one supervisor run."""

    dispatched: int
    merged: int
    failed: int
    invalid_files: list[InvalidBacklogFile]


class SupervisorLock:
    """Exclusive lock for one BacklogRoot."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> SupervisorLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open(LOCK_MODE)
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            self.handle.close()
            self.handle = None
            raise SupervisorLockError(
                f"another backlog-runner is active: {self.path}",
            ) from exc
        self.handle.write(str(os.getpid()))
        self.handle.flush()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.handle is None:
            return
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()
        self.path.unlink(missing_ok=True)
        self.handle = None


def run_once(config: SupervisorConfig) -> SupervisorRunResult:
    """Run one bounded supervisor cycle."""
    paths = BacklogPaths(config.backlog_root.resolve())
    _ensure_state_root_ignored(config, paths)
    paths.ensure_state_dirs()
    with SupervisorLock(paths.lock_file):
        state = BacklogState.load(paths.state_file)
        scan = scan_backlog(paths.backlog_root)
        _refresh_queued_records(config, paths, state, scan.items)
        dispatched, failed = _dispatch_and_wait(config, paths, state)
        merged, merge_failures = _drain_merge_queue(config, paths, state)
        failed += merge_failures
        state.save(paths.state_file)
        return SupervisorRunResult(
            dispatched=dispatched,
            merged=merged,
            failed=failed,
            invalid_files=scan.invalid_files,
        )


def run_loop(config: SupervisorConfig) -> None:
    """Run the supervisor until a stop marker appears."""
    paths = BacklogPaths(config.backlog_root.resolve())
    _ensure_state_root_ignored(config, paths)
    while not paths.stop_file.exists():
        run_once(config)
        time.sleep(config.poll_interval_seconds)


def request_stop(backlog_root: Path) -> Path:
    """Write a stop marker for a BacklogRoot."""
    paths = BacklogPaths(backlog_root.resolve())
    paths.ensure_state_dirs()
    paths.stop_file.write_text("stop\n", encoding="utf-8")
    return paths.stop_file


def _refresh_queued_records(
    config: SupervisorConfig,
    paths: BacklogPaths,
    state: BacklogState,
    items: list[BacklogItem],
) -> None:
    completed_slugs = {
        record.slug
        for record in state.records.values()
        if record.status == ItemStatus.COMPLETED
    }
    for item in items:
        record = state.records.get(item.key)
        if record is not None and record.status not in {
            ItemStatus.QUEUED,
            ItemStatus.BLOCKED,
        }:
            continue
        status = (
            ItemStatus.BLOCKED
            if any(dep not in completed_slugs for dep in item.dependencies)
            else ItemStatus.QUEUED
        )
        state.records[item.key] = _record_for_item(
            config=config,
            item=item,
            status=status,
        )
    state.save(paths.state_file)


def _dispatch_and_wait(
    config: SupervisorConfig,
    paths: BacklogPaths,
    state: BacklogState,
) -> tuple[int, int]:
    launch_config = WorkerLaunchConfig(
        methodology_runner_command=config.methodology_runner_command,
        application_repo=config.application_repo.resolve(),
        target_branch=config.target_branch,
        base_branch=config.base_branch,
        backend=config.backend,
        model=config.model,
        max_iterations=config.max_iterations,
    )
    runnable = [
        record
        for record in state.records.values()
        if record.status == ItemStatus.QUEUED
    ][:max(config.max_workers, 0)]
    running: list[RunningWorker] = []
    failed = 0
    for record in runnable:
        claim_item = BacklogItem(
            item_type=record.item_type,
            slug=record.slug,
            source_path=record.source_path,
            dependencies=list(record.dependencies),
        )
        claim = create_claim(paths, claim_item)
        if claim is None:
            continue
        record.claim_id = claim.claim_id
        record.status = ItemStatus.CLAIMED
        record.worker_result_path = paths.worker_result_path(record.item_key)
        if config.dry_run:
            continue
        worker = start_worker(paths, record, launch_config)
        record.status = ItemStatus.RUNNING
        record.process_id = worker.process.pid
        running.append(worker)
    state.save(paths.state_file)
    for worker in running:
        worker.process.wait()
        result = reap_worker(paths, worker)
        if result is None:
            continue
        record = state.records[worker.record.item_key]
        record.process_id = None
        record.worker_result_path = paths.worker_result_path(record.item_key)
        if result.outcome == WorkerOutcome.TARGET_MERGE_PENDING:
            record.status = ItemStatus.TARGET_MERGE_PENDING
            record.error_summary = None
        else:
            record.status = ItemStatus.FAILED
            record.error_summary = result.error_summary
            archived_path = archive_failed(paths, record)
            _commit_archive_move(config, record.source_path, archived_path)
            release_claim(paths, record.item_key)
            failed += 1
    state.save(paths.state_file)
    return len(running), failed


def _drain_merge_queue(
    config: SupervisorConfig,
    paths: BacklogPaths,
    state: BacklogState,
) -> tuple[int, int]:
    merged = 0
    failed = 0
    pending = [
        record
        for record in state.records.values()
        if record.status == ItemStatus.TARGET_MERGE_PENDING
    ]
    for record in pending:
        if config.dry_run:
            continue
        result = merge_record(
            paths=paths,
            application_repo=config.application_repo.resolve(),
            record=record,
            target_branch=config.target_branch,
        )
        record.merge_result_path = paths.merge_result_path(record.item_key)
        if result.outcome == MergeOutcome.MERGED:
            record.status = ItemStatus.COMPLETED
            archived_path = archive_completed(paths, record)
            _commit_archive_move(config, record.source_path, archived_path)
            release_claim(paths, record.item_key)
            merged += 1
        else:
            record.status = ItemStatus.FAILED
            record.error_summary = result.failure_reason
            archived_path = archive_failed(paths, record)
            _commit_archive_move(config, record.source_path, archived_path)
            release_claim(paths, record.item_key)
            failed += 1
    state.save(paths.state_file)
    return merged, failed


def _record_for_item(
    *,
    config: SupervisorConfig,
    item: BacklogItem,
    status: ItemStatus,
) -> BacklogItemRecord:
    branch_name = item.change_id
    workspace_path = (
        config.application_repo.resolve().parent
        / f"{config.application_repo.resolve().name}-worktrees"
        / branch_name
    )
    return BacklogItemRecord(
        item_key=item.key,
        item_type=item.item_type,
        slug=item.slug,
        source_path=item.source_path,
        status=status,
        change_id=item.change_id,
        branch_name=branch_name,
        workspace_path=workspace_path,
        dependencies=list(item.dependencies),
    )


def _commit_archive_move(
    config: SupervisorConfig,
    source_path: Path,
    archived_path: Path,
) -> None:
    """Commit archive movement when backlog folders are in the application repo."""
    application_repo = config.application_repo.resolve()
    try:
        source_path.resolve().relative_to(application_repo)
        archived_path.resolve().relative_to(application_repo)
    except ValueError:
        return
    try:
        commit_paths(
            application_repo,
            f"Archive backlog item {source_path.stem}",
            [source_path, archived_path],
        )
    except (GitError, ValueError) as exc:
        raise RuntimeError(f"Could not commit backlog archive move: {exc}") from exc


def _ensure_state_root_ignored(
    config: SupervisorConfig,
    paths: BacklogPaths,
) -> None:
    """Ignore .backlog-runner locally when it lives in the application repo."""
    application_repo = config.application_repo.resolve()
    try:
        state_rel = paths.state_root.resolve().relative_to(application_repo)
    except ValueError:
        return
    if str(state_rel) != ".backlog-runner":
        return
    try:
        exclude_ref = git(application_repo, "rev-parse", "--git-path", "info/exclude")
    except GitError:
        return
    exclude_path = Path(exclude_ref)
    if not exclude_path.is_absolute():
        exclude_path = application_repo / exclude_path
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    ignore_line = ".backlog-runner/"
    if ignore_line in existing.splitlines():
        return
    with exclude_path.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(f"{ignore_line}\n")
