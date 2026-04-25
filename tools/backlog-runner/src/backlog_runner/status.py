"""Status rendering for backlog-runner."""

from __future__ import annotations

from pathlib import Path

from backlog_runner.models import BacklogState
from backlog_runner.paths import BacklogPaths
from backlog_runner.scanner import scan_backlog


def render_status(backlog_root: Path) -> str:
    """Return human-readable backlog-runner status."""
    paths = BacklogPaths(backlog_root.resolve())
    state = BacklogState.load(paths.state_file)
    scan = scan_backlog(paths.backlog_root)
    lines = [f"Backlog root: {paths.backlog_root}"]
    lines.append(f"Stop requested: {'yes' if paths.stop_file.exists() else 'no'}")
    if scan.invalid_files:
        lines.append("Invalid files:")
        for invalid in scan.invalid_files:
            lines.append(f"  - {invalid.path}: {invalid.reason}")
    if not state.records:
        lines.append("Items: none")
        return "\n".join(lines) + "\n"
    lines.append("Items:")
    for key, record in sorted(state.records.items()):
        lines.append(
            f"  - {key}: {record.status.value} "
            f"branch={record.branch_name} workspace={record.workspace_path}"
        )
        if record.error_summary:
            lines.append(f"    error={record.error_summary}")
    return "\n".join(lines) + "\n"
