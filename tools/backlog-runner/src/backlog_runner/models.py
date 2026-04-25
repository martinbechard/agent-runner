"""Serializable models for backlog-runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ItemType(Enum):
    """Backlog item type derived from its active folder."""

    FEATURE = "feature"
    DEFECT = "defect"
    ANALYSIS = "analysis"
    INVESTIGATION = "investigation"


class ItemStatus(Enum):
    """Durable queue status for one backlog item."""

    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    TARGET_MERGE_PENDING = "target_merge_pending"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    ABANDONED = "abandoned"


class WorkerOutcome(Enum):
    """Terminal worker outcome before target merge."""

    TARGET_MERGE_PENDING = "target_merge_pending"
    FAILED = "failed"
    CRASHED = "crashed"
    BLOCKED = "blocked"
    INCOMPLETE = "incomplete"


class MergeOutcome(Enum):
    """Terminal merge outcome."""

    MERGED = "merged"
    MERGE_FAILED = "merge_failed"


@dataclass(frozen=True)
class BacklogItem:
    """One markdown backlog item discovered in an active folder."""

    item_type: ItemType
    slug: str
    source_path: Path
    dependencies: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Return the durable queue key for this item."""
        return f"{self.item_type.value}:{self.slug}"

    @property
    def change_id(self) -> str:
        """Return the default methodology-runner change id."""
        return f"{self.item_type.value}-{self.slug}"


@dataclass(frozen=True)
class ClaimRecord:
    """Atomic claim state for one item."""

    item_key: str
    claim_id: str
    created_at: str
    source_path: Path

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-compatible mapping."""
        return {
            "item_key": self.item_key,
            "claim_id": self.claim_id,
            "created_at": self.created_at,
            "source_path": str(self.source_path),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> ClaimRecord:
        """Build a claim record from JSON data."""
        return cls(
            item_key=data["item_key"],
            claim_id=data["claim_id"],
            created_at=data["created_at"],
            source_path=Path(data["source_path"]),
        )


@dataclass
class BacklogItemRecord:
    """Durable state for one known backlog item."""

    item_key: str
    item_type: ItemType
    slug: str
    source_path: Path
    status: ItemStatus
    change_id: str
    branch_name: str
    workspace_path: Path
    dependencies: list[str] = field(default_factory=list)
    claim_id: str | None = None
    process_id: int | None = None
    worker_result_path: Path | None = None
    merge_result_path: Path | None = None
    error_summary: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible mapping."""
        return {
            "item_key": self.item_key,
            "item_type": self.item_type.value,
            "slug": self.slug,
            "source_path": str(self.source_path),
            "status": self.status.value,
            "change_id": self.change_id,
            "branch_name": self.branch_name,
            "workspace_path": str(self.workspace_path),
            "dependencies": list(self.dependencies),
            "claim_id": self.claim_id,
            "process_id": self.process_id,
            "worker_result_path": (
                str(self.worker_result_path)
                if self.worker_result_path is not None
                else None
            ),
            "merge_result_path": (
                str(self.merge_result_path)
                if self.merge_result_path is not None
                else None
            ),
            "error_summary": self.error_summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BacklogItemRecord:
        """Build an item record from JSON data."""
        raw_worker_path = data.get("worker_result_path")
        raw_merge_path = data.get("merge_result_path")
        raw_process_id = data.get("process_id")
        return cls(
            item_key=str(data["item_key"]),
            item_type=ItemType(str(data["item_type"])),
            slug=str(data["slug"]),
            source_path=Path(str(data["source_path"])),
            status=ItemStatus(str(data["status"])),
            change_id=str(data["change_id"]),
            branch_name=str(data["branch_name"]),
            workspace_path=Path(str(data["workspace_path"])),
            dependencies=[str(item) for item in data.get("dependencies", [])],
            claim_id=(
                str(data["claim_id"])
                if data.get("claim_id") is not None
                else None
            ),
            process_id=(
                int(raw_process_id)
                if raw_process_id is not None
                else None
            ),
            worker_result_path=(
                Path(str(raw_worker_path))
                if raw_worker_path is not None
                else None
            ),
            merge_result_path=(
                Path(str(raw_merge_path))
                if raw_merge_path is not None
                else None
            ),
            error_summary=(
                str(data["error_summary"])
                if data.get("error_summary") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class WorkerResult:
    """Durable methodology worker result."""

    item_key: str
    outcome: WorkerOutcome
    exit_code: int
    handoff_path: Path | None = None
    error_summary: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible mapping."""
        return {
            "item_key": self.item_key,
            "outcome": self.outcome.value,
            "exit_code": self.exit_code,
            "handoff_path": (
                str(self.handoff_path)
                if self.handoff_path is not None
                else None
            ),
            "error_summary": self.error_summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> WorkerResult:
        """Build a worker result from JSON data."""
        raw_handoff_path = data.get("handoff_path")
        return cls(
            item_key=str(data["item_key"]),
            outcome=WorkerOutcome(str(data["outcome"])),
            exit_code=int(data["exit_code"]),
            handoff_path=(
                Path(str(raw_handoff_path))
                if raw_handoff_path is not None
                else None
            ),
            error_summary=(
                str(data["error_summary"])
                if data.get("error_summary") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class MergeResult:
    """Durable target merge result."""

    item_key: str
    outcome: MergeOutcome
    source_branch: str
    target_branch: str
    source_commit: str | None = None
    target_commit: str | None = None
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible mapping."""
        return {
            "item_key": self.item_key,
            "outcome": self.outcome.value,
            "source_branch": self.source_branch,
            "target_branch": self.target_branch,
            "source_commit": self.source_commit,
            "target_commit": self.target_commit,
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> MergeResult:
        """Build a merge result from JSON data."""
        return cls(
            item_key=str(data["item_key"]),
            outcome=MergeOutcome(str(data["outcome"])),
            source_branch=str(data["source_branch"]),
            target_branch=str(data["target_branch"]),
            source_commit=(
                str(data["source_commit"])
                if data.get("source_commit") is not None
                else None
            ),
            target_commit=(
                str(data["target_commit"])
                if data.get("target_commit") is not None
                else None
            ),
            failure_reason=(
                str(data["failure_reason"])
                if data.get("failure_reason") is not None
                else None
            ),
        )


@dataclass
class BacklogState:
    """Top-level persisted backlog-runner state."""

    records: dict[str, BacklogItemRecord] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible mapping."""
        return {
            "records": {
                key: record.to_dict()
                for key, record in sorted(self.records.items())
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BacklogState:
        """Build state from JSON data."""
        raw_records = data.get("records", {})
        if not isinstance(raw_records, dict):
            raw_records = {}
        return cls(
            records={
                str(key): BacklogItemRecord.from_dict(value)
                for key, value in raw_records.items()
                if isinstance(value, dict)
            },
        )

    @classmethod
    def load(cls, path: Path) -> BacklogState:
        """Load state from disk or return an empty state when absent."""
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def save(self, path: Path) -> None:
        """Atomically write state to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
