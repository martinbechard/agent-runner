"""Path helpers for backlog-runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backlog_runner.models import ItemType


STATE_DIRNAME = ".backlog-runner"
STATE_FILENAME = "state.json"
LOCK_FILENAME = "run.lock"
STOP_FILENAME = "stop"
CLAIMS_DIRNAME = "claims"
RESULTS_DIRNAME = "results"
LOGS_DIRNAME = "logs"
WORKER_RESULTS_DIRNAME = "workers"
MERGE_RESULTS_DIRNAME = "merges"

FEATURE_BACKLOG_DIR = "docs/feature-backlog"
DEFECT_BACKLOG_DIR = "docs/defect-backlog"
ANALYSIS_BACKLOG_DIR = "docs/analysis-backlog"
INVESTIGATION_BACKLOG_DIR = "docs/investigation-backlog"
HOLDING_DIR = "docs/holding"
COMPLETED_BACKLOG_DIR = "docs/completed-backlog"
FAILED_BACKLOG_DIR = "docs/failed-backlog"

FEATURE_ARCHIVE_DIR = "features"
DEFECT_ARCHIVE_DIR = "defects"
ANALYSIS_ARCHIVE_DIR = "analyses"
INVESTIGATION_ARCHIVE_DIR = "investigations"


ACTIVE_FOLDER_TYPES: tuple[tuple[str, ItemType], ...] = (
    (DEFECT_BACKLOG_DIR, ItemType.DEFECT),
    (FEATURE_BACKLOG_DIR, ItemType.FEATURE),
    (INVESTIGATION_BACKLOG_DIR, ItemType.INVESTIGATION),
    (ANALYSIS_BACKLOG_DIR, ItemType.ANALYSIS),
)

ARCHIVE_TYPE_DIRS: dict[ItemType, str] = {
    ItemType.FEATURE: FEATURE_ARCHIVE_DIR,
    ItemType.DEFECT: DEFECT_ARCHIVE_DIR,
    ItemType.ANALYSIS: ANALYSIS_ARCHIVE_DIR,
    ItemType.INVESTIGATION: INVESTIGATION_ARCHIVE_DIR,
}


@dataclass(frozen=True)
class BacklogPaths:
    """Resolved path bundle for one BacklogRoot."""

    backlog_root: Path

    @property
    def state_root(self) -> Path:
        """Return the runner-owned state directory."""
        return self.backlog_root / STATE_DIRNAME

    @property
    def state_file(self) -> Path:
        """Return the durable state file path."""
        return self.state_root / STATE_FILENAME

    @property
    def lock_file(self) -> Path:
        """Return the supervisor lock file path."""
        return self.state_root / LOCK_FILENAME

    @property
    def stop_file(self) -> Path:
        """Return the stop marker path."""
        return self.state_root / STOP_FILENAME

    @property
    def claims_dir(self) -> Path:
        """Return the claims directory."""
        return self.state_root / CLAIMS_DIRNAME

    @property
    def results_dir(self) -> Path:
        """Return the results directory."""
        return self.state_root / RESULTS_DIRNAME

    @property
    def worker_results_dir(self) -> Path:
        """Return worker result directory."""
        return self.results_dir / WORKER_RESULTS_DIRNAME

    @property
    def merge_results_dir(self) -> Path:
        """Return merge result directory."""
        return self.results_dir / MERGE_RESULTS_DIRNAME

    @property
    def logs_dir(self) -> Path:
        """Return per-item log directory."""
        return self.state_root / LOGS_DIRNAME

    def ensure_state_dirs(self) -> None:
        """Create runner-owned state directories."""
        for path in (
            self.state_root,
            self.claims_dir,
            self.worker_results_dir,
            self.merge_results_dir,
            self.logs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def claim_path(self, item_key: str) -> Path:
        """Return the claim file path for an item key."""
        return self.claims_dir / f"{_safe_key(item_key)}.json"

    def worker_result_path(self, item_key: str) -> Path:
        """Return the worker result path for an item key."""
        return self.worker_results_dir / f"{_safe_key(item_key)}.json"

    def merge_result_path(self, item_key: str) -> Path:
        """Return the merge result path for an item key."""
        return self.merge_results_dir / f"{_safe_key(item_key)}.json"

    def stdout_log_path(self, item_key: str) -> Path:
        """Return stdout log path for an item key."""
        return self.logs_dir / f"{_safe_key(item_key)}.stdout.log"

    def stderr_log_path(self, item_key: str) -> Path:
        """Return stderr log path for an item key."""
        return self.logs_dir / f"{_safe_key(item_key)}.stderr.log"

    def completed_archive_path(self, item_type: ItemType, filename: str) -> Path:
        """Return completed archive path for one item."""
        return (
            self.backlog_root
            / COMPLETED_BACKLOG_DIR
            / ARCHIVE_TYPE_DIRS[item_type]
            / filename
        )

    def failed_archive_path(self, item_type: ItemType, filename: str) -> Path:
        """Return failed archive path for one item."""
        return (
            self.backlog_root
            / FAILED_BACKLOG_DIR
            / ARCHIVE_TYPE_DIRS[item_type]
            / filename
        )


def _safe_key(item_key: str) -> str:
    """Convert an item key to a filename-safe token."""
    return item_key.replace(":", "__").replace("/", "_")
