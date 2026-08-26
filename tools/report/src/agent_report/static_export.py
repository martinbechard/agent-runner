# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Render and stage portable Codex Agent Report exports.
# Design: docs/design/components/CD-006-agent-report-static-export.md

"""Deterministic, privacy-bounded static export for Codex Agent Report data.

Callers inject snapshot conversion, path authorization, atomic publication, and
optional SQLite archive creation. This module owns only validated staged bytes.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import Enum
import hashlib
import html
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Callable, Literal, NoReturn, Protocol, TypeAlias
from urllib.parse import urlsplit


MANIFEST_VERSION = 1
DEFAULT_SUMMARY_MAX_BYTES = 2_097_152
DEFAULT_DIRECTORY_PAGE_SIZE = 500
MAX_DIRECTORY_PAGES_PER_COLLECTION = 9_999
STAGING_PREFIX = ".agent-report-export-"
STALE_STAGING_SECONDS = 86_400
COPYRIGHT_NOTICE = "© 2026 Martin.Bechard@DevConsult.ca · MIT License"

SUMMARY_OMISSION_PRIORITY: tuple[str, ...] = (
    "recent_activity",
    "agents",
    "coordination",
    "time_and_runtime",
    "model_tokens_and_cost",
)

REPORT_CSS = """\
:root { color-scheme: light dark; font-family: system-ui, sans-serif; }
body { margin: 0 auto; max-width: 78rem; padding: 1.5rem; line-height: 1.5; }
nav { display: flex; flex-wrap: wrap; gap: .75rem; margin-block: 1rem; }
a { color: #1769aa; } a:focus, button:focus, input:focus { outline: 3px solid #f59e0b; outline-offset: 2px; }
table { border-collapse: collapse; width: 100%; } th, td { border: 1px solid #777; padding: .4rem; text-align: left; }
.state, .evidence, .warning, .omission { border-left: .35rem solid #64748b; padding: .5rem .75rem; }
.warning { border-color: #b45309; } .omission { border-color: #9333ea; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: .75rem; }
.metric { border: 1px solid #777; border-radius: .35rem; padding: .75rem; }
.empty { font-style: italic; } [hidden] { display: none !important; }
.agent-report-copyright { margin-top: 2rem; padding-top: .75rem; border-top: 1px solid currentColor; opacity: .62; text-align: center; font: 10px/1.4 ui-monospace, monospace; }
"""

REPORT_JS = """\
(function () {
  "use strict";
  function filterRows(input) {
    var query = input.value.toLocaleLowerCase();
    document.querySelectorAll("[data-filter-item]").forEach(function (item) {
      item.hidden = item.textContent.toLocaleLowerCase().indexOf(query) === -1;
    });
  }
  document.querySelectorAll("[data-local-filter]").forEach(function (input) {
    input.addEventListener("input", function () { filterRows(input); });
  });
}());
"""


ProgressCallback: TypeAlias = Callable[["ExportProgress"], None]
EvidenceKind: TypeAlias = Literal[
    "measured", "derived", "inferred", "unavailable", "estimated"
]
FileRole: TypeAlias = Literal[
    "entry",
    "data-json",
    "summary-markdown",
    "turns-csv",
    "work-units-csv",
    "stylesheet",
    "classic-script",
    "agents-page",
    "turns-page",
    "events-page",
    "heatmap-page",
    "sequence-page",
    "sqlite-archive",
]
JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class ExportMode(str, Enum):
    SUMMARY = "summary"
    DIRECTORY = "directory"


class SnapshotState(str, Enum):
    LIVE = "live"
    SEALED = "sealed"


class ExportState(str, Enum):
    VALIDATING = "validating"
    STAGING = "staging"
    RENDERING = "rendering"
    VERIFYING = "verifying"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExportScope:
    include_children: bool
    include_collaborators: bool


@dataclass(frozen=True, slots=True)
class SnapshotProvenance:
    snapshot_id: str
    revision: str
    root_thread_id: str
    scope: ExportScope
    observed_at: datetime
    state: SnapshotState
    source_digest: str
    parser_version: str
    pricing_version: str
    pricing_digest: str
    formatter_version: str
    formatter_digest: str


@dataclass(frozen=True, slots=True)
class MetricExport:
    metric_id: str
    label: str
    display_value: str
    numeric_value: int | float | None
    unit: str | None
    evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class ExportWarningRecord:
    """Carry one privacy-bounded warning across export surfaces."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SummaryExport:
    title: str
    goal: str | None
    run_state: str
    metrics: tuple[MetricExport, ...]
    recent_activity: tuple[str, ...]
    warnings: tuple[ExportWarningRecord, ...]


@dataclass(frozen=True, slots=True)
class AgentExportRow:
    thread_id: str
    parent_thread_id: str | None
    task_title: str
    agent_role: str
    model: str
    effort: str
    started_at: str
    last_observed_at: str
    terminal_state: str
    turn_count: int
    tool_count: int
    mcp_call_count: int
    wall_time_ms: int
    agent_time_ms: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    estimated_cost_usd: float | None
    cost_evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class TurnExportRow:
    thread_id: str
    turn_id: str
    started_at: str
    completed_at: str
    duration_ms: int
    time_to_first_token_ms: int | None
    outcome: str
    abort_reason: str
    abort_event_timestamp: str
    abort_initiator_thread_id: str
    abort_initiator_agent_path: str
    abort_initiator_turn_id: str
    abort_initiator_relationship: str
    abort_request_source_path: str
    abort_request_source_ordinal: int
    phase_id: str
    lane_id: str
    work_unit_id: str
    activity: str
    attribution_confidence: str
    input_tokens: int
    cached_input_tokens: int
    uncached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    processed_tokens: int
    source_path: str
    source_ordinal: int


@dataclass(frozen=True, slots=True)
class WorkUnitExportRow:
    work_unit_id: str
    phase_id: str
    lane_id: str
    activity: str
    turn_ids: tuple[str, ...]
    allocation_method: str
    attribution_confidence: str
    input_tokens: int
    cached_input_tokens: int
    uncached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    processed_tokens: int
    cost_status: str
    estimated_usd: float | None


@dataclass(frozen=True, slots=True)
class EventExportRow:
    event_id: str
    thread_id: str
    turn_id: str | None
    timestamp: str
    kind: str
    label: str
    summary: str
    evidence: EvidenceKind
    source_ordinal: int


@dataclass(frozen=True, slots=True)
class HeatmapCellExport:
    thread_id: str
    bucket_start: str
    bucket_end: str
    measure: str
    numeric_value: int | float
    display_value: str
    evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class SequenceParticipantExport:
    thread_id: str
    parent_thread_id: str | None
    display_name: str
    role: str


@dataclass(frozen=True, slots=True)
class SequenceEventExport:
    sequence_order: int
    event_id: str
    timestamp: str
    kind: str
    source_thread_id: str
    target_thread_id: str | None
    label: str
    detail: str
    evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class CodexExportModel:
    provenance: SnapshotProvenance
    summary: SummaryExport
    agents: tuple[AgentExportRow, ...]
    turns: tuple[TurnExportRow, ...]
    work_units: tuple[WorkUnitExportRow, ...]
    events: tuple[EventExportRow, ...]
    heatmap_cells: tuple[HeatmapCellExport, ...]
    sequence_participants: tuple[SequenceParticipantExport, ...]
    sequence_events: tuple[SequenceEventExport, ...]


@dataclass(frozen=True, slots=True)
class ExportRequest:
    operation_id: str
    snapshot_id: str
    revision: str
    mode: ExportMode
    requested_target: Path
    replace: bool
    include_sqlite: bool = False
    page_size: int = DEFAULT_DIRECTORY_PAGE_SIZE
    summary_max_bytes: int = DEFAULT_SUMMARY_MAX_BYTES


@dataclass(frozen=True, slots=True)
class PublicationPlan:
    adapter_name: Literal["tauri", "cli", "mcp"]
    authority_token: str
    requested_target: Path
    absolute_target: Path
    staging_directory: Path
    target_kind: Literal["file", "directory"]
    commit_strategy: Literal[
        "atomic-file-replace",
        "atomic-directory-rename",
        "atomic-directory-exchange",
    ]
    replace: bool


class PublicationAdapter(Protocol):
    def authorize(self, request: ExportRequest) -> PublicationPlan:
        raise NotImplementedError

    def publish(
        self,
        plan: PublicationPlan,
        staged_entry: Path,
        expected_relative_paths: tuple[PurePosixPath, ...],
    ) -> Path:
        raise NotImplementedError

    def discard(self, plan: PublicationPlan) -> None:
        raise NotImplementedError

    def cleanup_stale(self, *, older_than: datetime) -> tuple[Path, ...]:
        raise NotImplementedError


class CancellationToken(Protocol):
    def raise_if_cancelled(self) -> None:
        raise NotImplementedError


class SQLiteArchiveWriter(Protocol):
    def write_archive(
        self,
        destination: Path,
        provenance: SnapshotProvenance,
        cancellation: CancellationToken,
    ) -> None:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ManifestFile:
    path: PurePosixPath
    role: FileRole
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ManifestOmission:
    section: str
    reason: str
    recovery: str


@dataclass(frozen=True, slots=True)
class ExportManifest:
    manifest_version: int
    snapshot_id: str
    revision: str
    root_thread_id: str
    include_children: bool
    include_collaborators: bool
    observed_at: str
    snapshot_state: Literal["live", "sealed"]
    source_digest: str
    parser_version: str
    pricing_version: str
    pricing_digest: str
    formatter_version: str
    formatter_digest: str
    files: tuple[ManifestFile, ...]
    omissions: tuple[ManifestOmission, ...]
    warnings: tuple[ExportWarningRecord, ...]


@dataclass(frozen=True, slots=True)
class ExportProgress:
    operation_id: str
    state: ExportState
    completed: int
    total: int | None
    message: str


@dataclass(frozen=True, slots=True)
class ExportResult:
    operation_id: str
    snapshot_id: str
    revision: str
    mode: ExportMode
    published_target: Path
    manifest_sha256: str | None
    file_count: int
    total_byte_count: int
    warnings: tuple[ExportWarningRecord, ...]
    omissions: tuple[ManifestOmission, ...]


@dataclass(frozen=True, slots=True)
class ExportErrorRecord:
    code: str
    message: str
    operation_id: str
    recoverable: bool
    target: str | None = None
    requested_snapshot_id: str | None = None
    supplied_snapshot_id: str | None = None
    requested_revision: str | None = None
    supplied_revision: str | None = None
    actual_bytes: int | None = None
    maximum_bytes: int | None = None
    written_files: tuple[str, ...] = ()
    warnings: tuple[ExportWarningRecord, ...] = ()
    commit_strategy: str | None = None


class StaticExportError(RuntimeError):
    """Expected exporter failure with a stable, privacy-bounded record."""

    def __init__(self, error: ExportErrorRecord) -> None:
        self.error = error
        super().__init__(f"{error.code}: {error.message}")

    @classmethod
    def from_code(
        cls,
        code: str,
        message: str,
        *,
        operation_id: str,
        recoverable: bool = True,
        target: str | None = None,
        requested_snapshot_id: str | None = None,
        supplied_snapshot_id: str | None = None,
        requested_revision: str | None = None,
        supplied_revision: str | None = None,
        actual_bytes: int | None = None,
        maximum_bytes: int | None = None,
        written_files: tuple[str, ...] = (),
        warnings: tuple[ExportWarningRecord, ...] = (),
        commit_strategy: str | None = None,
    ) -> StaticExportError:
        return cls(
            ExportErrorRecord(
                code=code,
                message=message,
                operation_id=operation_id,
                recoverable=recoverable,
                target=target,
                requested_snapshot_id=requested_snapshot_id,
                supplied_snapshot_id=supplied_snapshot_id,
                requested_revision=requested_revision,
                supplied_revision=supplied_revision,
                actual_bytes=actual_bytes,
                maximum_bytes=maximum_bytes,
                written_files=written_files,
                warnings=warnings,
                commit_strategy=commit_strategy,
            )
        )


def _emit_progress(
    callback: ProgressCallback | None,
    operation_id: str,
    state: ExportState,
    completed: int,
    total: int | None,
    message: str,
) -> None:
    if callback is not None:
        callback(ExportProgress(operation_id, state, completed, total, message))


def _fail(
    code: str,
    message: str,
    *,
    operation_id: str = "unknown",
    target: str | None = None,
    actual_bytes: int | None = None,
    maximum_bytes: int | None = None,
    commit_strategy: str | None = None,
) -> NoReturn:
    raise StaticExportError.from_code(
        code,
        message,
        operation_id=operation_id,
        target=target,
        actual_bytes=actual_bytes,
        maximum_bytes=maximum_bytes,
        commit_strategy=commit_strategy,
    )


def _validate_snapshot_binding(model: CodexExportModel, request: ExportRequest) -> None:
    provenance = model.provenance
    if request.snapshot_id != provenance.snapshot_id or request.revision != provenance.revision:
        raise StaticExportError.from_code(
            "REPORT_SNAPSHOT_CONFLICT",
            "The export request does not match the supplied snapshot revision.",
            operation_id=request.operation_id or "unknown",
            target=str(request.requested_target),
            requested_snapshot_id=request.snapshot_id,
            supplied_snapshot_id=provenance.snapshot_id,
            requested_revision=request.revision,
            supplied_revision=provenance.revision,
        )


def _is_digest(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validate_request(model: CodexExportModel, request: ExportRequest) -> None:
    provenance = model.provenance
    identifiers = (
        request.operation_id,
        request.snapshot_id,
        request.revision,
        provenance.snapshot_id,
        provenance.revision,
        provenance.root_thread_id,
        provenance.parser_version,
        provenance.pricing_version,
        provenance.formatter_version,
    )
    if any(not isinstance(value, str) or not value for value in identifiers):
        _fail("REPORT_INVALID_REQUEST", "Required export identifiers must be non-empty.", operation_id=request.operation_id or "unknown")
    if not isinstance(request.mode, ExportMode):
        _fail("REPORT_INVALID_REQUEST", "Export mode must be directory or summary.", operation_id=request.operation_id)
    if not isinstance(request.requested_target, Path):
        _fail("REPORT_INVALID_REQUEST", "The requested target must be a path.", operation_id=request.operation_id)
    if type(request.replace) is not bool or type(request.include_sqlite) is not bool:
        _fail("REPORT_INVALID_REQUEST", "Replacement and SQLite options must be Boolean values.", operation_id=request.operation_id)
    if type(request.page_size) is not int or not 1 <= request.page_size <= 500:
        _fail("REPORT_INVALID_REQUEST", "Directory page size must be between 1 and 500.", operation_id=request.operation_id)
    if type(request.summary_max_bytes) is not int or not 65_536 <= request.summary_max_bytes <= DEFAULT_SUMMARY_MAX_BYTES:
        _fail("REPORT_INVALID_REQUEST", "Summary byte limit must be between 65,536 and 2,097,152.", operation_id=request.operation_id)
    if request.include_sqlite and request.mode is not ExportMode.DIRECTORY:
        _fail("REPORT_INVALID_REQUEST", "SQLite archive output is valid only in directory mode.", operation_id=request.operation_id)
    if request.include_sqlite and not isinstance(model, CodexExportModel):
        _fail("REPORT_INVALID_REQUEST", "A Codex export model is required.", operation_id=request.operation_id)
    if provenance.observed_at.tzinfo is None or provenance.observed_at.utcoffset() is None:
        _fail("REPORT_INVALID_REQUEST", "Snapshot observation time must include a time zone.", operation_id=request.operation_id)
    if not all(_is_digest(value) for value in (provenance.source_digest, provenance.pricing_digest, provenance.formatter_digest)):
        _fail("REPORT_INVALID_REQUEST", "Snapshot provenance digests must be lowercase SHA-256 values.", operation_id=request.operation_id)
    exact_tuples = (
        model.summary.metrics,
        model.summary.recent_activity,
        model.summary.warnings,
        model.agents,
        model.turns,
        model.work_units,
        model.events,
        model.heatmap_cells,
        model.sequence_participants,
        model.sequence_events,
    )
    if any(type(value) is not tuple for value in exact_tuples):
        _fail("REPORT_INVALID_REQUEST", "Exporter collections must use exact immutable tuple contracts.", operation_id=request.operation_id)
    if any(
        type(warning) is not ExportWarningRecord
        or type(warning.code) is not str
        or type(warning.message) is not str
        for warning in model.summary.warnings
    ):
        _fail(
            "REPORT_INVALID_REQUEST",
            "Export warnings must use structured code and message records.",
            operation_id=request.operation_id,
        )
    _validate_snapshot_binding(model, request)


def _validate_plan(plan: PublicationPlan, request: ExportRequest) -> None:
    expected_kind = "file" if request.mode is ExportMode.SUMMARY else "directory"
    strategies = {
        "file": ("atomic-file-replace",),
        "directory": ("atomic-directory-rename", "atomic-directory-exchange"),
    }
    if (
        plan.adapter_name not in ("tauri", "cli", "mcp")
        or not plan.authority_token
        or plan.requested_target != request.requested_target
        or plan.target_kind != expected_kind
        or plan.commit_strategy not in strategies[expected_kind]
        or plan.replace != request.replace
        or not plan.absolute_target.is_absolute()
    ):
        _fail("REPORT_OUTPUT_PATH_INVALID", "The publication plan does not match the export request.", operation_id=request.operation_id, target=str(request.requested_target))
    staging = plan.staging_directory
    try:
        valid_staging = (
            staging.is_absolute()
            and staging.name.startswith(STAGING_PREFIX)
            and staging.parent.resolve() == plan.absolute_target.parent.resolve()
            and staging.exists()
            and staging.is_dir()
            and not staging.is_symlink()
            and not any(staging.iterdir())
            and staging.resolve() != plan.absolute_target.resolve()
        )
    except OSError as exc:
        raise StaticExportError.from_code(
            "REPORT_OUTPUT_PATH_INVALID",
            "The authorized staging directory cannot be validated.",
            operation_id=request.operation_id,
            target=str(request.requested_target),
        ) from exc
    if not valid_staging:
        _fail("REPORT_OUTPUT_PATH_INVALID", "The authorized staging directory is not empty and same-parent.", operation_id=request.operation_id, target=str(request.requested_target))


def _check_cancelled(cancellation: CancellationToken, operation_id: str) -> None:
    try:
        cancellation.raise_if_cancelled()
    except StaticExportError:
        raise
    except Exception as exc:
        raise StaticExportError.from_code(
            "REPORT_EXPORT_CANCELLED",
            "The export was cancelled before publication.",
            operation_id=operation_id,
        ) from exc


def _write_file(path: Path, payload: bytes, operation_id: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise StaticExportError.from_code(
            "REPORT_EXPORT_WRITE_FAILED",
            "A staged export file could not be written.",
            operation_id=operation_id,
        ) from exc


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _deduplicate(
    values: tuple[ExportWarningRecord, ...],
) -> tuple[ExportWarningRecord, ...]:
    return tuple(dict.fromkeys(values))


def _warning_text(warning: ExportWarningRecord) -> str:
    return f"{warning.code}: {warning.message}"


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _summary_document(
    model: CodexExportModel,
    included: tuple[str, ...],
    omissions: tuple[ManifestOmission, ...],
    recent_activity_count: int,
    agent_count: int,
) -> bytes:
    provenance = model.provenance
    summary = model.summary
    title = summary.title or "Agent Report"
    metrics = "".join(
        '<div class="metric"><strong>{}</strong><div>{}</div><div class="evidence">Evidence: {}</div></div>'.format(
            _escape(metric.label), _escape(metric.display_value), _escape(metric.evidence)
        )
        for metric in summary.metrics
    )
    warnings = "".join(
        f'<li class="warning">{_escape(_warning_text(warning))}</li>'
        for warning in _deduplicate(summary.warnings)
    ) or "<li>None</li>"
    optional = ""
    if "recent_activity" in included:
        items = "".join(
            f"<li>{_escape(value)}</li>"
            for value in summary.recent_activity[:recent_activity_count]
        ) or "<li>No recent activity</li>"
        optional += f"<section><h2>Recent activity</h2><ul>{items}</ul></section>"
    if "agents" in included:
        rows = "".join(
            f"<tr><td>{_escape(row.task_title)}</td><td>{_escape(row.agent_role)}</td><td>{_escape(row.terminal_state)}</td></tr>"
            for row in model.agents[:agent_count]
        ) or '<tr><td colspan="3">No agents</td></tr>'
        optional += f"<section><h2>Agents</h2><table><thead><tr><th>Task</th><th>Role</th><th>State</th></tr></thead><tbody>{rows}</tbody></table></section>"
    if "coordination" in included:
        optional += (
            "<section><h2>Coordination</h2>"
            f"<p>{len(model.sequence_participants)} participants and {len(model.sequence_events)} sequence events.</p></section>"
        )
    if "time_and_runtime" in included:
        wall = sum(row.wall_time_ms for row in model.agents)
        agent = sum(row.agent_time_ms for row in model.agents)
        optional += f"<section><h2>Time and runtime</h2><p>Wall time: {wall} ms. Agent time: {agent} ms.</p></section>"
    if "model_tokens_and_cost" in included:
        tokens = sum(row.input_tokens + row.output_tokens + row.reasoning_tokens for row in model.agents)
        optional += f"<section><h2>Model, tokens, and cost</h2><p>Processed token components: {tokens}. Values retain their evidence labels.</p></section>"
    omitted = "".join(
        '<li class="omission"><strong>{}</strong>: {} {}</li>'.format(
            _escape(item.section), _escape(item.reason), _escape(item.recovery)
        )
        for item in omissions
    ) or "<li>None</li>"
    goal = f"<p><strong>Goal:</strong> {_escape(summary.goal)}</p>" if summary.goal else ""
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(title)}</title><style>{REPORT_CSS}</style></head>
<body><main><h1>{_escape(title)}</h1>{goal}
<p class="state">Run state: {_escape(summary.run_state)}. Snapshot state: {_escape(provenance.state.value)}.</p>
<section><h2>Scope and provenance</h2><dl>
<dt>Snapshot</dt><dd>{_escape(provenance.snapshot_id)}</dd><dt>Revision</dt><dd>{_escape(provenance.revision)}</dd>
<dt>Root thread</dt><dd>{_escape(provenance.root_thread_id)}</dd><dt>Observed</dt><dd>{_escape(_iso_utc(provenance.observed_at))}</dd>
<dt>Relationships</dt><dd>Children: {str(provenance.scope.include_children).lower()}; collaborators: {str(provenance.scope.include_collaborators).lower()}</dd>
<dt>Parser</dt><dd>{_escape(provenance.parser_version)}</dd><dt>Pricing</dt><dd>{_escape(provenance.pricing_version)}</dd>
<dt>Formatter</dt><dd>{_escape(provenance.formatter_version)}</dd><dt>Source digest</dt><dd>{_escape(provenance.source_digest)}</dd>
<dt>Pricing digest</dt><dd>{_escape(provenance.pricing_digest)}</dd><dt>Formatter digest</dt><dd>{_escape(provenance.formatter_digest)}</dd>
</dl></section><section><h2>Headline metrics</h2><div class="metric-grid">{metrics}</div></section>
<section><h2>Warnings</h2><ul>{warnings}</ul></section>{optional}
<section><h2>Omissions</h2><ul>{omitted}</ul></section>
<footer class="agent-report-copyright">{COPYRIGHT_NOTICE}</footer></main>
<script>{REPORT_JS}</script></body></html>\n"""
    return document.encode("utf-8")


def _render_summary(
    model: CodexExportModel,
    max_bytes: int,
    cancellation: CancellationToken,
) -> tuple[bytes, tuple[ManifestOmission, ...]]:
    included = list(SUMMARY_OMISSION_PRIORITY)
    omitted_names: list[str] = []
    recent_activity_count = len(model.summary.recent_activity)
    agent_count = len(model.agents)
    operation_id = model.provenance.snapshot_id

    def current_omissions() -> tuple[ManifestOmission, ...]:
        return tuple(
            ManifestOmission(
                section=name,
                reason=f"Omitted to keep the summary within {max_bytes} UTF-8 bytes.",
                recovery="Use a directory export or the dynamic application.",
            )
            for name in SUMMARY_OMISSION_PRIORITY
            if name in omitted_names
        )

    def render_current() -> tuple[bytes, tuple[ManifestOmission, ...]]:
        omissions = current_omissions()
        return (
            _summary_document(
                model,
                tuple(included),
                omissions,
                recent_activity_count,
                agent_count,
            ),
            omissions,
        )

    while True:
        _check_cancelled(cancellation, operation_id)
        payload, omissions = render_current()
        if len(payload) <= max_bytes:
            _check_cancelled(cancellation, operation_id)
            return payload, omissions
        if included:
            lowest = included[-1]
            if lowest == "agents" and agent_count:
                if "agents" not in omitted_names:
                    omitted_names.append("agents")
                low, high = 1, agent_count - 1
                best_count = 0
                best_payload = b""
                best_omissions: tuple[ManifestOmission, ...] = ()
                while low <= high:
                    _check_cancelled(cancellation, operation_id)
                    candidate = (low + high) // 2
                    agent_count = candidate
                    candidate_payload, candidate_omissions = render_current()
                    if len(candidate_payload) <= max_bytes:
                        best_count = candidate
                        best_payload = candidate_payload
                        best_omissions = candidate_omissions
                        low = candidate + 1
                    else:
                        high = candidate - 1
                if best_count:
                    _check_cancelled(cancellation, operation_id)
                    return best_payload, best_omissions
                agent_count = 0
                included.pop()
            elif lowest == "recent_activity" and recent_activity_count:
                if "recent_activity" not in omitted_names:
                    omitted_names.append("recent_activity")
                low, high = 1, recent_activity_count - 1
                best_count = 0
                best_payload = b""
                best_omissions = ()
                while low <= high:
                    _check_cancelled(cancellation, operation_id)
                    candidate = (low + high) // 2
                    recent_activity_count = candidate
                    candidate_payload, candidate_omissions = render_current()
                    if len(candidate_payload) <= max_bytes:
                        best_count = candidate
                        best_payload = candidate_payload
                        best_omissions = candidate_omissions
                        low = candidate + 1
                    else:
                        high = candidate - 1
                if best_count:
                    _check_cancelled(cancellation, operation_id)
                    return best_payload, best_omissions
                recent_activity_count = 0
                included.pop()
            else:
                included.pop()
                if lowest not in omitted_names:
                    omitted_names.append(lowest)
            continue
        raise StaticExportError.from_code(
            "REPORT_SUMMARY_CAP_TOO_SMALL",
            "The required summary content exceeds the selected byte limit.",
            operation_id=operation_id,
            actual_bytes=len(payload),
            maximum_bytes=max_bytes,
        )


def _report_dict(model: CodexExportModel) -> dict[str, JsonValue]:
    provenance = model.provenance
    return {
        "provenance": {
            "snapshot_id": provenance.snapshot_id,
            "revision": provenance.revision,
            "root_thread_id": provenance.root_thread_id,
            "scope": asdict(provenance.scope),
            "observed_at": _iso_utc(provenance.observed_at),
            "state": provenance.state.value,
            "source_digest": provenance.source_digest,
            "parser_version": provenance.parser_version,
            "pricing_version": provenance.pricing_version,
            "pricing_digest": provenance.pricing_digest,
            "formatter_version": provenance.formatter_version,
            "formatter_digest": provenance.formatter_digest,
        },
        "summary": asdict(model.summary),
        "agents": [asdict(row) for row in model.agents],
        "turns": [asdict(row) for row in model.turns],
        "work_units": [asdict(row) for row in model.work_units],
        "events": [asdict(row) for row in model.events],
        "heatmap_cells": [asdict(row) for row in model.heatmap_cells],
        "sequence_participants": [asdict(row) for row in model.sequence_participants],
        "sequence_events": [asdict(row) for row in model.sequence_events],
    }


def _render_report_json(model: CodexExportModel) -> bytes:
    return (json.dumps(_report_dict(model), indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _csv_bytes(rows: list[list[str | int | float | None]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _render_turns_csv(rows: tuple[TurnExportRow, ...]) -> bytes:
    header = [
        "thread_id", "turn_id", "started_at", "completed_at", "duration_ms",
        "time_to_first_token_ms", "outcome", "abort_reason", "abort_event_timestamp",
        "abort_initiator_thread_id", "abort_initiator_agent_path", "abort_initiator_turn_id",
        "abort_initiator_relationship", "abort_request_source_path", "abort_request_source_ordinal",
        "phase_id", "lane_id", "work_unit_id", "activity", "attribution_confidence",
        "input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens",
        "reasoning_tokens", "processed_tokens", "source_path", "source_ordinal",
    ]
    values = [
        [
            row.thread_id, row.turn_id, row.started_at, row.completed_at, row.duration_ms,
            row.time_to_first_token_ms, row.outcome, row.abort_reason, row.abort_event_timestamp,
            row.abort_initiator_thread_id, row.abort_initiator_agent_path, row.abort_initiator_turn_id,
            row.abort_initiator_relationship, row.abort_request_source_path, row.abort_request_source_ordinal,
            row.phase_id, row.lane_id, row.work_unit_id, row.activity, row.attribution_confidence,
            row.input_tokens, row.cached_input_tokens, row.uncached_input_tokens, row.output_tokens,
            row.reasoning_tokens, row.processed_tokens, row.source_path, row.source_ordinal,
        ]
        for row in rows
    ]
    return _csv_bytes([header, *values])


def _render_work_units_csv(rows: tuple[WorkUnitExportRow, ...]) -> bytes:
    header = [
        "work_unit_id", "phase_id", "lane_id", "activity", "turn_ids",
        "allocation_method", "attribution_confidence", "input_tokens", "cached_input_tokens",
        "uncached_input_tokens", "output_tokens", "reasoning_tokens", "processed_tokens",
        "cost_status", "estimated_usd",
    ]
    values = [
        [
            row.work_unit_id, row.phase_id, row.lane_id, row.activity, " ".join(row.turn_ids),
            row.allocation_method, row.attribution_confidence, row.input_tokens,
            row.cached_input_tokens, row.uncached_input_tokens, row.output_tokens,
            row.reasoning_tokens, row.processed_tokens, row.cost_status,
            "" if row.estimated_usd is None else f"{row.estimated_usd:.8f}",
        ]
        for row in rows
    ]
    return _csv_bytes([header, *values])


def _render_report_markdown(model: CodexExportModel) -> bytes:
    provenance = model.provenance
    lines = [
        f"# {model.summary.title}", "",
        f"- Root thread: `{provenance.root_thread_id}`",
        f"- Snapshot: `{provenance.snapshot_id}`",
        f"- Revision: `{provenance.revision}`",
        f"- State: `{provenance.state.value}`",
        f"- Observed at: `{_iso_utc(provenance.observed_at)}`",
        f"- Include children: `{str(provenance.scope.include_children).lower()}`",
        f"- Include collaborators: `{str(provenance.scope.include_collaborators).lower()}`",
        "", "## Metrics", "",
    ]
    for metric in model.summary.metrics:
        lines.extend((f"- {metric.label}: {metric.display_value}", f"  - Evidence: `{metric.evidence}`"))
    lines.extend(("", "## Warnings", ""))
    lines.extend(
        f"- {_warning_text(warning)}"
        for warning in _deduplicate(model.summary.warnings)
    )
    lines.extend(("", "## Recent activity", ""))
    lines.extend(f"- {activity}" for activity in model.summary.recent_activity)
    return ("\n".join(lines) + "\n").encode("utf-8")


def _page_shell(title: str, body: str, *, asset_prefix: str, index_prefix: str, navigation: str = "") -> bytes:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(title)}</title><link rel="stylesheet" href="{asset_prefix}assets/report.css">
<script src="{asset_prefix}assets/report.js" defer></script></head>
<body><nav><a href="{index_prefix}index.html">Report index</a>{navigation}</nav><main><h1>{_escape(title)}</h1>{body}<footer class="agent-report-copyright">{COPYRIGHT_NOTICE}</footer></main></body></html>\n""".encode("utf-8")


def _collection_navigation(folder: str, page: int, pages: int) -> str:
    links = []
    if page > 1:
        links.append(f'<a href="page-{page - 1:04d}.html">Previous</a>')
    if page < pages:
        links.append(f'<a href="page-{page + 1:04d}.html">Next</a>')
    return "".join(links)


def _render_agent_page(rows: tuple[AgentExportRow, ...], page: int, pages: int) -> bytes:
    body = '<label>Filter <input data-local-filter></label>'
    if rows:
        body += "<table><thead><tr><th>Thread</th><th>Task</th><th>Role</th><th>State</th><th>Evidence</th></tr></thead><tbody>"
        body += "".join(
            '<tr data-filter-item><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
                _escape(row.thread_id), _escape(row.task_title), _escape(row.agent_role),
                _escape(row.terminal_state), _escape(row.cost_evidence),
            )
            for row in rows
        ) + "</tbody></table>"
    else:
        body += '<p class="empty">No agents</p>'
    body += f"<p>Page {page} of {pages}; {len(rows)} items on this page.</p>"
    return _page_shell("Agents", body, asset_prefix="../../", index_prefix="../../", navigation=_collection_navigation("agents", page, pages))


def _render_turn_page(rows: tuple[TurnExportRow, ...], page: int, pages: int) -> bytes:
    body = '<label>Filter <input data-local-filter></label>'
    if rows:
        body += "<table><thead><tr><th>Turn</th><th>Activity</th><th>Outcome</th><th>Duration</th><th>Evidence</th></tr></thead><tbody>"
        body += "".join(
            '<tr data-filter-item><td>{}</td><td>{}</td><td>{}</td><td>{} ms</td><td>{}</td></tr>'.format(
                _escape(row.turn_id), _escape(row.activity), _escape(row.outcome), row.duration_ms,
                _escape(row.attribution_confidence),
            )
            for row in rows
        ) + "</tbody></table>"
    else:
        body += '<p class="empty">No turns</p>'
    body += f"<p>Page {page} of {pages}; {len(rows)} items on this page.</p>"
    return _page_shell("Turns", body, asset_prefix="../../", index_prefix="../../", navigation=_collection_navigation("turns", page, pages))


def _render_event_page(rows: tuple[EventExportRow, ...], page: int, pages: int) -> bytes:
    body = '<label>Filter <input data-local-filter></label>'
    if rows:
        body += "<ol>" + "".join(
            '<li data-filter-item><strong>{}</strong> {} <span class="evidence">Evidence: {}</span></li>'.format(
                _escape(row.label), _escape(row.summary), _escape(row.evidence)
            )
            for row in rows
        ) + "</ol>"
    else:
        body += '<p class="empty">No events</p>'
    body += f"<p>Page {page} of {pages}; {len(rows)} items on this page.</p>"
    return _page_shell("Events", body, asset_prefix="../../", index_prefix="../../", navigation=_collection_navigation("events", page, pages))


def _render_heatmap_page(cells: tuple[HeatmapCellExport, ...]) -> bytes:
    rows = "".join(
        '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            _escape(cell.thread_id), _escape(cell.bucket_start), _escape(cell.bucket_end),
            _escape(cell.display_value), _escape(cell.evidence),
        )
        for cell in cells
    ) or '<tr><td colspan="5">No heatmap cells</td></tr>'
    body = f"<table><thead><tr><th>Thread</th><th>Start</th><th>End</th><th>Value</th><th>Evidence</th></tr></thead><tbody>{rows}</tbody></table>"
    return _page_shell("Execution heatmap", body, asset_prefix="../../", index_prefix="../../")


def _render_sequence_page(
    participants: tuple[SequenceParticipantExport, ...],
    events: tuple[SequenceEventExport, ...],
) -> bytes:
    people = "".join(f"<li>{_escape(row.display_name)} — {_escape(row.role)}</li>" for row in participants) or "<li>No participants</li>"
    event_rows = "".join(
        '<li><strong>{}</strong> {} to {}: {} <span class="evidence">Evidence: {}</span></li>'.format(
            _escape(row.source_thread_id), _escape(row.kind), _escape(row.target_thread_id or "none"),
            _escape(row.detail), _escape(row.evidence),
        )
        for row in events
    ) or "<li>No sequence events</li>"
    body = f"<section><h2>Participants</h2><ul>{people}</ul></section><section><h2>Sequence ledger</h2><ol>{event_rows}</ol></section>"
    return _page_shell("Agent sequence", body, asset_prefix="../", index_prefix="../")


def _render_index(model: CodexExportModel) -> bytes:
    provenance = model.provenance
    metrics = "".join(f'<li>{_escape(metric.label)}: {_escape(metric.display_value)} ({_escape(metric.evidence)})</li>' for metric in model.summary.metrics)
    warnings = "".join(
        f'<li class="warning">{_escape(_warning_text(warning))}</li>'
        for warning in _deduplicate(model.summary.warnings)
    ) or "<li>None</li>"
    body = f"""<p class="state">Snapshot {_escape(provenance.snapshot_id)}, revision {_escape(provenance.revision)}, state {_escape(provenance.state.value)}.</p>
<p>Observed {_escape(_iso_utc(provenance.observed_at))}. Children: {str(provenance.scope.include_children).lower()}; collaborators: {str(provenance.scope.include_collaborators).lower()}.</p>
<section><h2>Metrics</h2><ul>{metrics}</ul></section><section><h2>Warnings</h2><ul>{warnings}</ul></section>
<section><h2>Report views and data</h2><nav>
<a href="pages/agents/page-0001.html">Agents</a><a href="pages/turns/page-0001.html">Turns</a>
<a href="pages/events/page-0001.html">Events</a><a href="pages/heatmap/overview.html">Heatmap</a>
<a href="sequence/index.html">Sequence</a><a href="manifest.json">Manifest</a>
<a href="report.json">JSON</a><a href="turns.csv">Turns CSV</a><a href="work-units.csv">Work units CSV</a><a href="report.md">Markdown</a>
</nav></section>"""
    return _page_shell(model.summary.title or "Agent Report", body, asset_prefix="", index_prefix="")


def _page_count(item_count: int, page_size: int, operation_id: str) -> int:
    pages = max(1, (item_count + page_size - 1) // page_size)
    if pages > MAX_DIRECTORY_PAGES_PER_COLLECTION:
        _fail("REPORT_EXPORT_TOO_MANY_PAGES", "A directory collection needs more than 9,999 pages.", operation_id=operation_id)
    return pages


def _render_directory(
    model: CodexExportModel,
    root: Path,
    page_size: int,
    include_sqlite: bool,
    archive_writer: SQLiteArchiveWriter | None,
    cancellation: CancellationToken,
    progress: ProgressCallback | None,
    operation_id: str,
) -> tuple[PurePosixPath, ...]:
    files: list[PurePosixPath] = []

    def write(relative: str, payload: bytes) -> None:
        _check_cancelled(cancellation, operation_id)
        _write_file(root / PurePosixPath(relative), payload, operation_id)
        files.append(PurePosixPath(relative))
        _check_cancelled(cancellation, operation_id)

    write("index.html", _render_index(model))
    write("assets/report.css", REPORT_CSS.encode("utf-8"))
    write("assets/report.js", REPORT_JS.encode("utf-8"))
    write("report.json", _render_report_json(model))
    write("turns.csv", _render_turns_csv(model.turns))
    write("work-units.csv", _render_work_units_csv(model.work_units))
    write("report.md", _render_report_markdown(model))

    agent_pages = _page_count(len(model.agents), page_size, operation_id)
    for page in range(1, agent_pages + 1):
        start = (page - 1) * page_size
        rows = model.agents[start : start + page_size]
        write(f"pages/agents/page-{page:04d}.html", _render_agent_page(rows, page, agent_pages))
    _emit_progress(progress, operation_id, ExportState.RENDERING, 15, 100, "Rendered agent pages.")

    turn_pages = _page_count(len(model.turns), page_size, operation_id)
    for page in range(1, turn_pages + 1):
        start = (page - 1) * page_size
        rows = model.turns[start : start + page_size]
        write(f"pages/turns/page-{page:04d}.html", _render_turn_page(rows, page, turn_pages))
    _emit_progress(progress, operation_id, ExportState.RENDERING, 35, 100, "Rendered turn pages.")

    event_pages = _page_count(len(model.events), page_size, operation_id)
    for page in range(1, event_pages + 1):
        start = (page - 1) * page_size
        rows = model.events[start : start + page_size]
        write(f"pages/events/page-{page:04d}.html", _render_event_page(rows, page, event_pages))
    _emit_progress(progress, operation_id, ExportState.RENDERING, 55, 100, "Rendered event pages.")

    write("pages/heatmap/overview.html", _render_heatmap_page(model.heatmap_cells))
    write("sequence/index.html", _render_sequence_page(model.sequence_participants, model.sequence_events))
    _emit_progress(progress, operation_id, ExportState.RENDERING, 80, 100, "Rendered heatmap and sequence pages.")

    if include_sqlite:
        if archive_writer is None:
            _fail("REPORT_INVALID_REQUEST", "SQLite output requires an archive writer.", operation_id=operation_id)
        _check_cancelled(cancellation, operation_id)
        destination = root / "report.sqlite"
        try:
            archive_writer.write_archive(destination, model.provenance, cancellation)
        except StaticExportError:
            raise
        except Exception as exc:
            raise StaticExportError.from_code(
                "REPORT_EXPORT_RENDER_FAILED",
                "The privacy-bounded SQLite archive could not be created.",
                operation_id=operation_id,
            ) from exc
        if not destination.is_file() or destination.is_symlink():
            _fail("REPORT_EXPORT_INTEGRITY_FAILED", "The archive writer did not create one regular staged file.", operation_id=operation_id)
        files.append(PurePosixPath("report.sqlite"))
        _check_cancelled(cancellation, operation_id)
        _emit_progress(progress, operation_id, ExportState.RENDERING, 85, 100, "Rendered the optional SQLite archive.")
    return tuple(files)


_ROLES: dict[PurePosixPath, FileRole] = {
    PurePosixPath("index.html"): "entry",
    PurePosixPath("report.json"): "data-json",
    PurePosixPath("report.md"): "summary-markdown",
    PurePosixPath("turns.csv"): "turns-csv",
    PurePosixPath("work-units.csv"): "work-units-csv",
    PurePosixPath("assets/report.css"): "stylesheet",
    PurePosixPath("assets/report.js"): "classic-script",
    PurePosixPath("pages/heatmap/overview.html"): "heatmap-page",
    PurePosixPath("sequence/index.html"): "sequence-page",
    PurePosixPath("report.sqlite"): "sqlite-archive",
}


def _file_role(path: PurePosixPath) -> FileRole:
    if path in _ROLES:
        return _ROLES[path]
    if path.parent == PurePosixPath("pages/agents") and re.fullmatch(r"page-[0-9]{4}\.html", path.name):
        return "agents-page"
    if path.parent == PurePosixPath("pages/turns") and re.fullmatch(r"page-[0-9]{4}\.html", path.name):
        return "turns-page"
    if path.parent == PurePosixPath("pages/events") and re.fullmatch(r"page-[0-9]{4}\.html", path.name):
        return "events-page"
    _fail("REPORT_EXPORT_INTEGRITY_FAILED", "The staged inventory contains an unsupported path.")


def _manifest_file(root: Path, relative: PurePosixPath, operation_id: str) -> ManifestFile:
    path = root / relative
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise StaticExportError.from_code(
            "REPORT_EXPORT_WRITE_FAILED",
            "A staged payload could not be read for hashing.",
            operation_id=operation_id,
        ) from exc
    return ManifestFile(relative, _file_role(relative), len(payload), hashlib.sha256(payload).hexdigest())


def _build_manifest(
    provenance: SnapshotProvenance,
    files: tuple[ManifestFile, ...],
    omissions: tuple[ManifestOmission, ...],
    warnings: tuple[ExportWarningRecord, ...],
) -> ExportManifest:
    return ExportManifest(
        manifest_version=MANIFEST_VERSION,
        snapshot_id=provenance.snapshot_id,
        revision=provenance.revision,
        root_thread_id=provenance.root_thread_id,
        include_children=provenance.scope.include_children,
        include_collaborators=provenance.scope.include_collaborators,
        observed_at=_iso_utc(provenance.observed_at),
        snapshot_state=provenance.state.value,
        source_digest=provenance.source_digest,
        parser_version=provenance.parser_version,
        pricing_version=provenance.pricing_version,
        pricing_digest=provenance.pricing_digest,
        formatter_version=provenance.formatter_version,
        formatter_digest=provenance.formatter_digest,
        files=tuple(sorted(files, key=lambda item: item.path.as_posix())),
        omissions=omissions,
        warnings=_deduplicate(warnings),
    )


def _manifest_bytes(manifest: ExportManifest) -> bytes:
    payload = {
        "manifest_version": manifest.manifest_version,
        "snapshot_id": manifest.snapshot_id,
        "revision": manifest.revision,
        "root_thread_id": manifest.root_thread_id,
        "include_children": manifest.include_children,
        "include_collaborators": manifest.include_collaborators,
        "observed_at": manifest.observed_at,
        "snapshot_state": manifest.snapshot_state,
        "source_digest": manifest.source_digest,
        "parser_version": manifest.parser_version,
        "pricing_version": manifest.pricing_version,
        "pricing_digest": manifest.pricing_digest,
        "formatter_version": manifest.formatter_version,
        "formatter_digest": manifest.formatter_digest,
        "files": [
            {"path": item.path.as_posix(), "role": item.role, "byte_count": item.byte_count, "sha256": item.sha256}
            for item in manifest.files
        ],
        "omissions": [asdict(item) for item in manifest.omissions],
        "warnings": [asdict(item) for item in manifest.warnings],
    }
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def _valid_manifest_path(path: PurePosixPath) -> bool:
    return (
        not path.is_absolute()
        and bool(path.parts)
        and ".." not in path.parts
        and "." not in path.parts
        and "\\" not in path.as_posix()
        and path.as_posix() == PurePosixPath(path.as_posix()).as_posix()
    )


def _verify_staged_directory(root: Path, manifest: ExportManifest) -> None:
    operation_id = manifest.snapshot_id or "unknown"
    try:
        canonical_root = root.resolve(strict=True)
    except OSError as exc:
        raise StaticExportError.from_code(
            "REPORT_EXPORT_INTEGRITY_FAILED", "The staging root cannot be resolved.", operation_id=operation_id
        ) from exc
    expected = tuple(item.path for item in manifest.files)
    if len(set(expected)) != len(expected) or any(not _valid_manifest_path(path) for path in expected):
        _fail("REPORT_EXPORT_INTEGRITY_FAILED", "Manifest paths must be unique, normalized, relative, and contained.", operation_id=operation_id)
    actual: list[PurePosixPath] = []
    try:
        for path in root.rglob("*"):
            if path.is_symlink():
                _fail("REPORT_EXPORT_INTEGRITY_FAILED", "Symbolic links are not valid export payloads.", operation_id=operation_id)
            if path.is_file():
                relative = PurePosixPath(path.relative_to(root).as_posix())
                if relative != PurePosixPath("manifest.json"):
                    actual.append(relative)
            elif not path.is_dir():
                _fail("REPORT_EXPORT_INTEGRITY_FAILED", "Only regular files and directories are valid export payloads.", operation_id=operation_id)
    except OSError as exc:
        raise StaticExportError.from_code(
            "REPORT_EXPORT_INTEGRITY_FAILED", "The staged export inventory cannot be inspected.", operation_id=operation_id
        ) from exc
    if tuple(sorted(actual, key=PurePosixPath.as_posix)) != tuple(sorted(expected, key=PurePosixPath.as_posix)):
        _fail("REPORT_EXPORT_INTEGRITY_FAILED", "The staged file inventory does not match the manifest.", operation_id=operation_id)
    required = {
        PurePosixPath("index.html"),
        PurePosixPath("report.json"),
        PurePosixPath("report.md"),
        PurePosixPath("turns.csv"),
        PurePosixPath("work-units.csv"),
        PurePosixPath("assets/report.css"),
        PurePosixPath("assets/report.js"),
        PurePosixPath("pages/agents/page-0001.html"),
        PurePosixPath("pages/turns/page-0001.html"),
        PurePosixPath("pages/events/page-0001.html"),
        PurePosixPath("pages/heatmap/overview.html"),
        PurePosixPath("sequence/index.html"),
    }
    if not required.issubset(set(expected)):
        _fail("REPORT_EXPORT_INTEGRITY_FAILED", "The staged directory is missing a required manifest-version-one file.", operation_id=operation_id)
    for item in manifest.files:
        try:
            expected_role = _file_role(item.path)
        except StaticExportError as exc:
            raise StaticExportError(replace(exc.error, operation_id=operation_id)) from exc
        if item.role != expected_role:
            _fail("REPORT_EXPORT_INTEGRITY_FAILED", "A staged payload has the wrong manifest role.", operation_id=operation_id)
    for folder in ("agents", "turns", "events"):
        pages = sorted(
            path.name
            for path in expected
            if path.parent == PurePosixPath(f"pages/{folder}")
        )
        consecutive = [f"page-{number:04d}.html" for number in range(1, len(pages) + 1)]
        if pages != consecutive or len(pages) > MAX_DIRECTORY_PAGES_PER_COLLECTION:
            _fail("REPORT_EXPORT_INTEGRITY_FAILED", "Collection pages must be consecutive and bounded.", operation_id=operation_id)
    for item in manifest.files:
        path = root / item.path
        try:
            if not path.resolve(strict=True).is_relative_to(canonical_root):
                _fail("REPORT_EXPORT_INTEGRITY_FAILED", "A staged payload escapes the export root.", operation_id=operation_id)
            payload = path.read_bytes()
        except OSError as exc:
            raise StaticExportError.from_code(
                "REPORT_EXPORT_INTEGRITY_FAILED", "A staged payload cannot be inspected.", operation_id=operation_id
            ) from exc
        if len(payload) != item.byte_count or hashlib.sha256(payload).hexdigest() != item.sha256:
            _fail("REPORT_EXPORT_INTEGRITY_FAILED", "A staged payload digest or byte count does not match.", operation_id=operation_id)
        if path.suffix in (".html", ".js"):
            text = payload.decode("utf-8")
            if re.search(r"\bfetch\s*\(|XMLHttpRequest|type\s*=\s*[\"']module|serviceWorker|sqlite.{0,8}wasm|https?://", text, re.IGNORECASE):
                _fail("REPORT_EXPORT_INTEGRITY_FAILED", "A static startup file contains a forbidden network or module mechanism.", operation_id=operation_id)
        if path.suffix == ".html":
            text = payload.decode("utf-8")
            for raw in re.findall(r"(?:href|src)=[\"']([^\"']+)[\"']", text, re.IGNORECASE):
                split = urlsplit(raw)
                if split.scheme or split.netloc or not split.path:
                    if split.scheme or split.netloc:
                        _fail("REPORT_EXPORT_INTEGRITY_FAILED", "A static page contains a non-relative link.", operation_id=operation_id)
                    continue
                relative_link = PurePosixPath(split.path)
                if relative_link.is_absolute() or "\\" in split.path:
                    _fail("REPORT_EXPORT_INTEGRITY_FAILED", "A static page link is not normalized and relative.", operation_id=operation_id)
                resolved = (path.parent / relative_link).resolve()
                if not resolved.is_relative_to(canonical_root) or not resolved.is_file():
                    _fail("REPORT_EXPORT_INTEGRITY_FAILED", "A static page link is unresolved or escapes the export root.", operation_id=operation_id)
    manifest_path = root / "manifest.json"
    if manifest_path.exists() and manifest_path.read_bytes() != _manifest_bytes(manifest):
        _fail("REPORT_EXPORT_INTEGRITY_FAILED", "The staged manifest is not canonical.", operation_id=operation_id)


def _verify_summary(payload: bytes, maximum: int, operation_id: str) -> None:
    if len(payload) > maximum:
        _fail("REPORT_SUMMARY_CAP_TOO_SMALL", "The summary exceeds the selected byte limit.", operation_id=operation_id, actual_bytes=len(payload), maximum_bytes=maximum)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StaticExportError.from_code(
            "REPORT_EXPORT_INTEGRITY_FAILED", "The summary is not valid UTF-8.", operation_id=operation_id
        ) from exc
    if re.search(r"(?:href|src)=[\"']|\bfetch\s*\(|XMLHttpRequest|type\s*=\s*[\"']module|serviceWorker|https?://", text, re.IGNORECASE):
        _fail("REPORT_EXPORT_INTEGRITY_FAILED", "The summary is not self-contained.", operation_id=operation_id)


def _published_counts(
    target: Path,
    mode: ExportMode,
    operation_id: str,
) -> tuple[int, int]:
    """Count final published bytes without disclosing artifact paths on failure."""

    try:
        if target.is_symlink():
            raise OSError("published target is a symbolic link")
        if mode is ExportMode.SUMMARY:
            if not target.is_file():
                raise OSError("published summary is not a regular file")
            return 1, len(target.read_bytes())
        if not target.is_dir():
            raise OSError("published directory is not a directory")
        files: list[Path] = []
        for path in target.rglob("*"):
            if path.is_symlink():
                raise OSError("published artifact contains a symbolic link")
            if path.is_file():
                files.append(path)
            elif not path.is_dir():
                raise OSError("published artifact contains a non-regular entry")
        return len(files), sum(len(path.read_bytes()) for path in files)
    except OSError as exc:
        raise StaticExportError.from_code(
            "REPORT_EXPORT_PUBLICATION_FAILED",
            "The published artifact could not be counted safely.",
            operation_id=operation_id,
        ) from exc


class StaticExporter:
    """Render one coherent Codex snapshot and hand it to one publisher."""

    def __init__(self, archive_writer: SQLiteArchiveWriter | None = None) -> None:
        self._archive_writer = archive_writer

    def export(
        self,
        model: CodexExportModel,
        request: ExportRequest,
        publication: PublicationAdapter,
        cancellation: CancellationToken,
        progress: ProgressCallback | None = None,
    ) -> ExportResult:
        _emit_progress(progress, request.operation_id or "unknown", ExportState.VALIDATING, 0, 100, "Validating export request.")
        plan: PublicationPlan | None = None
        phase = ExportState.VALIDATING
        try:
            _validate_request(model, request)
            if request.include_sqlite and self._archive_writer is None:
                _fail(
                    "REPORT_INVALID_REQUEST",
                    "SQLite output requires an archive writer.",
                    operation_id=request.operation_id,
                )
            _check_cancelled(cancellation, request.operation_id)
            try:
                plan = publication.authorize(request)
            except StaticExportError:
                raise
            except Exception as exc:
                raise StaticExportError.from_code(
                    "REPORT_EXPORT_PUBLICATION_FAILED",
                    "The publication adapter could not authorize the target.",
                    operation_id=request.operation_id,
                    target=str(request.requested_target),
                ) from exc
            _validate_plan(plan, request)
            phase = ExportState.STAGING
            _emit_progress(progress, request.operation_id, ExportState.STAGING, 5, 100, "Allocated authorized staging.")
            _check_cancelled(cancellation, request.operation_id)
            phase = ExportState.RENDERING
            _emit_progress(progress, request.operation_id, ExportState.RENDERING, 10, 100, "Rendering static export.")

            warnings = _deduplicate(model.summary.warnings)
            manifest_sha256: str | None = None
            omissions: tuple[ManifestOmission, ...] = ()
            if request.mode is ExportMode.SUMMARY:
                try:
                    payload, omissions = _render_summary(model, request.summary_max_bytes, cancellation)
                except StaticExportError as exc:
                    raise StaticExportError(replace(exc.error, operation_id=request.operation_id)) from exc
                staged_entry = plan.staging_directory / plan.absolute_target.name
                _write_file(staged_entry, payload, request.operation_id)
                payload_paths = (PurePosixPath(plan.absolute_target.name),)
                phase = ExportState.VERIFYING
                _emit_progress(progress, request.operation_id, ExportState.VERIFYING, 90, 100, "Verifying staged summary.")
                _check_cancelled(cancellation, request.operation_id)
                _verify_summary(staged_entry.read_bytes(), request.summary_max_bytes, request.operation_id)
                expected_paths = payload_paths
            else:
                staged_entry = plan.staging_directory
                payload_paths = _render_directory(
                    model,
                    staged_entry,
                    request.page_size,
                    request.include_sqlite,
                    self._archive_writer,
                    cancellation,
                    progress,
                    request.operation_id,
                )
                file_entries = tuple(_manifest_file(staged_entry, path, request.operation_id) for path in payload_paths)
                manifest = _build_manifest(model.provenance, file_entries, (), warnings)
                manifest_payload = _manifest_bytes(manifest)
                _write_file(staged_entry / "manifest.json", manifest_payload, request.operation_id)
                manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
                phase = ExportState.VERIFYING
                _emit_progress(progress, request.operation_id, ExportState.VERIFYING, 90, 100, "Verifying staged directory.")
                _check_cancelled(cancellation, request.operation_id)
                _verify_staged_directory(staged_entry, manifest)
                expected_paths = tuple(sorted((*payload_paths, PurePosixPath("manifest.json")), key=PurePosixPath.as_posix))

            _check_cancelled(cancellation, request.operation_id)
            phase = ExportState.PUBLISHING
            _emit_progress(progress, request.operation_id, ExportState.PUBLISHING, 95, 100, "Publishing static export.")
            try:
                published_target = publication.publish(plan, staged_entry, expected_paths)
            except StaticExportError:
                raise
            except Exception as exc:
                raise StaticExportError.from_code(
                    "REPORT_EXPORT_PUBLICATION_FAILED",
                    "The authorized atomic publication operation failed.",
                    operation_id=request.operation_id,
                    target=str(request.requested_target),
                    commit_strategy=plan.commit_strategy,
                ) from exc
            if published_target != plan.absolute_target:
                _fail("REPORT_EXPORT_PUBLICATION_FAILED", "The publisher returned a different target.", operation_id=request.operation_id, target=str(request.requested_target), commit_strategy=plan.commit_strategy)
            file_count, total_byte_count = _published_counts(
                published_target,
                request.mode,
                request.operation_id,
            )
            _emit_progress(progress, request.operation_id, ExportState.PUBLISHED, 100, 100, "Static export published.")
            return ExportResult(
                operation_id=request.operation_id,
                snapshot_id=request.snapshot_id,
                revision=request.revision,
                mode=request.mode,
                published_target=published_target,
                manifest_sha256=manifest_sha256,
                file_count=file_count,
                total_byte_count=total_byte_count,
                warnings=warnings,
                omissions=omissions,
            )
        except StaticExportError as exc:
            if plan is not None:
                try:
                    publication.discard(plan)
                except Exception:
                    pass
            terminal = ExportState.CANCELLED if exc.error.code == "REPORT_EXPORT_CANCELLED" else ExportState.FAILED
            _emit_progress(progress, request.operation_id or "unknown", terminal, 0, 100, "Export cancelled." if terminal is ExportState.CANCELLED else "Export failed.")
            raise
        except Exception as exc:
            if plan is not None:
                try:
                    publication.discard(plan)
                except Exception:
                    pass
            code = "REPORT_EXPORT_PUBLICATION_FAILED" if phase is ExportState.PUBLISHING else "REPORT_EXPORT_RENDER_FAILED"
            _emit_progress(progress, request.operation_id or "unknown", ExportState.FAILED, 0, 100, "Export failed.")
            raise StaticExportError.from_code(
                code,
                "The export failed without exposing staged content.",
                operation_id=request.operation_id or "unknown",
                target=str(request.requested_target),
                commit_strategy=plan.commit_strategy if plan is not None and phase is ExportState.PUBLISHING else None,
            ) from exc

    def cleanup_stale_staging(
        self,
        publication: PublicationAdapter,
        *,
        now: datetime,
    ) -> tuple[Path, ...]:
        if now.tzinfo is None or now.utcoffset() is None:
            _fail("REPORT_INVALID_REQUEST", "Staging cleanup time must include a time zone.")
        return publication.cleanup_stale(older_than=now - timedelta(seconds=STALE_STAGING_SECONDS))
