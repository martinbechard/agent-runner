"""Methodology-runner worker process handling."""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from backlog_runner.models import (
    BacklogItemRecord,
    WorkerOutcome,
    WorkerResult,
)
from backlog_runner.paths import BacklogPaths


HANDOFF_RELATIVE_PATH = "docs/changes/{change_id}/execution/target-merge-handoff.json"
HANDOFF_PENDING_STATUS = "target_merge_pending"


@dataclass(frozen=True)
class WorkerLaunchConfig:
    """Configuration needed to launch methodology-runner."""

    methodology_runner_command: str
    application_repo: Path
    target_branch: str
    base_branch: str | None = None
    backend: str | None = None
    model: str | None = None
    max_iterations: int | None = None


@dataclass
class RunningWorker:
    """One active methodology-runner subprocess."""

    record: BacklogItemRecord
    process: subprocess.Popen[bytes]
    stdout_path: Path
    stderr_path: Path


def build_worker_command(
    record: BacklogItemRecord,
    config: WorkerLaunchConfig,
) -> list[str]:
    """Build the methodology-runner command for one backlog item."""
    command = [
        *shlex.split(config.methodology_runner_command),
        "run",
        str(record.source_path),
        "--application-repo",
        str(config.application_repo),
        "--change-id",
        record.change_id,
        "--branch-name",
        record.branch_name,
        "--workspace",
        str(record.workspace_path),
        "--target-branch",
        config.target_branch,
        "--skip-target-merge",
    ]
    if config.base_branch is not None:
        command.extend(["--base-branch", config.base_branch])
    if config.backend is not None:
        command.extend(["--backend", config.backend])
    if config.model is not None:
        command.extend(["--model", config.model])
    if config.max_iterations is not None:
        command.extend(["--max-iterations", str(config.max_iterations)])
    return command


def start_worker(
    paths: BacklogPaths,
    record: BacklogItemRecord,
    config: WorkerLaunchConfig,
) -> RunningWorker:
    """Start methodology-runner for one item."""
    paths.ensure_state_dirs()
    stdout_path = paths.stdout_log_path(record.item_key)
    stderr_path = paths.stderr_log_path(record.item_key)
    stdout_handle = stdout_path.open("wb")
    stderr_handle = stderr_path.open("wb")
    try:
        process = subprocess.Popen(
            build_worker_command(record, config),
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()
    return RunningWorker(
        record=record,
        process=process,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def reap_worker(paths: BacklogPaths, worker: RunningWorker) -> WorkerResult | None:
    """Return a worker result when the process has exited."""
    exit_code = worker.process.poll()
    if exit_code is None:
        return None
    result = classify_worker_exit(worker.record, exit_code)
    write_worker_result(paths, result)
    return result


def classify_worker_exit(record: BacklogItemRecord, exit_code: int) -> WorkerResult:
    """Classify an exited methodology-runner worker."""
    handoff_path = handoff_path_for_record(record)
    if exit_code != 0:
        return WorkerResult(
            item_key=record.item_key,
            outcome=WorkerOutcome.FAILED,
            exit_code=exit_code,
            handoff_path=handoff_path if handoff_path.exists() else None,
            error_summary=f"methodology-runner exited with {exit_code}",
        )
    if not handoff_path.exists():
        return WorkerResult(
            item_key=record.item_key,
            outcome=WorkerOutcome.INCOMPLETE,
            exit_code=exit_code,
            error_summary="target merge handoff not found",
        )
    try:
        data = json.loads(handoff_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return WorkerResult(
            item_key=record.item_key,
            outcome=WorkerOutcome.INCOMPLETE,
            exit_code=exit_code,
            handoff_path=handoff_path,
            error_summary=f"invalid target merge handoff: {exc}",
        )
    if data.get("status") != HANDOFF_PENDING_STATUS:
        return WorkerResult(
            item_key=record.item_key,
            outcome=WorkerOutcome.INCOMPLETE,
            exit_code=exit_code,
            handoff_path=handoff_path,
            error_summary="target merge handoff is not pending",
        )
    return WorkerResult(
        item_key=record.item_key,
        outcome=WorkerOutcome.TARGET_MERGE_PENDING,
        exit_code=exit_code,
        handoff_path=handoff_path,
    )


def handoff_path_for_record(record: BacklogItemRecord) -> Path:
    """Return expected methodology-runner handoff path for a record."""
    return record.workspace_path / HANDOFF_RELATIVE_PATH.format(
        change_id=record.change_id,
    )


def write_worker_result(paths: BacklogPaths, result: WorkerResult) -> Path:
    """Write one worker result."""
    path = paths.worker_result_path(result.item_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return path
