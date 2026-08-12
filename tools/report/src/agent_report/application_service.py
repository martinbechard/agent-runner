# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Coordinate shared report scope, snapshot, query, export, and lifecycle operations.
# Design: docs/design/components/CD-002-agent-report-application-service.md

"""Transport-neutral, process-local application service for Agent Report."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import secrets
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import TracebackType
from typing import Final, Generic, Literal, Protocol, TypeVar, cast


PROTOCOL_VERSION: Final[int] = 1
DEFAULT_PAGE_SIZE: Final[int] = 100
MAX_PAGE_SIZE: Final[int] = 500
MAX_HEATMAP_CELLS: Final[int] = 2_000
# Retained as an import-compatible name for callers that used the original
# narrow time-series contract. Protocol version 1 applies the same ceiling to
# the canonical grouped heatmap.
MAX_TIME_BUCKETS: Final[int] = MAX_HEATMAP_CELLS
MAX_ID_BYTES: Final[int] = 256
MAX_FILTER_VALUES: Final[int] = 500
MAX_TEXT_BYTES: Final[int] = 4_096
MAX_DETAIL_FIELD_BYTES: Final[int] = 16_384
MAX_WARNINGS: Final[int] = 100
MAX_PROVENANCE_ITEMS: Final[int] = 100
MAX_RECENT_ACTIVITY: Final[int] = 100

_PREFLIGHT_TOKEN_TTL_SECONDS: Final[int] = 300
_MAX_PREFLIGHT_TOKENS: Final[int] = 1_024
_MAX_CURSOR_TOKENS: Final[int] = 4_096

ReportErrorCode = Literal[
    "REPORT_CANCELLED",
    "REPORT_CURSOR_CONFLICT",
    "REPORT_DISCOVERY_FAILED",
    "REPORT_EVENT_NOT_FOUND",
    "REPORT_EXPORT_FAILED",
    "REPORT_GENERATION_FAILED",
    "REPORT_INTERNAL_ERROR",
    "REPORT_INVALID_REQUEST",
    "REPORT_NOT_FOUND",
    "REPORT_PRIVACY_FAILED",
    "REPORT_SCOPE_CONFLICT",
    "REPORT_SNAPSHOT_CONFLICT",
    "REPORT_SNAPSHOT_NOT_FOUND",
    "REPORT_WRITE_FAILED",
]
EvidenceKind = Literal["measured", "derived", "inferred", "unavailable", "estimated"]
SnapshotMode = Literal["live", "sealed"]
ExportMode = Literal["directory", "summary"]
AutomationSurface = Literal["tauri", "cli", "mcp"]
SequenceGrouping = Literal["none", "repeated_messages", "delegation", "agent"]
SortDirection = Literal["ascending", "descending"]
AgentSortKey = Literal["last_activity_at", "started_at", "agent_id"]
TurnSortKey = Literal["started_at", "ended_at", "turn_id"]
EventSortKey = Literal["occurred_at", "event_id"]
SequenceSortKey = Literal["occurred_at", "sequence_id"]
CoordinationSortKey = Literal["occurred_at", "coordination_id"]
HeatmapGroupBy = Literal["agent", "event_kind", "work_item"]
HeatmapColorSemantic = Literal["sequential_nonnegative", "diverging_signed"]
HeatmapScaleBasis = Literal["visible_row_maximum", "context_window_capacity"]
TimeMeasure = Literal[
    "wall_time",
    "uncached_input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cost_usd",
]
SourceRelationship = Literal["root", "child", "collaborator"]

_EVIDENCE_KINDS: Final[frozenset[str]] = frozenset(
    {"measured", "derived", "inferred", "unavailable", "estimated"}
)
_TIME_MEASURES: Final[frozenset[str]] = frozenset(
    {
        "wall_time",
        "uncached_input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cost_usd",
    }
)
_GROUPINGS: Final[frozenset[str]] = frozenset(
    {"none", "repeated_messages", "delegation", "agent"}
)
_SORT_DIRECTIONS: Final[frozenset[str]] = frozenset({"ascending", "descending"})
_AGENT_SORT_KEYS: Final[frozenset[str]] = frozenset(
    {"last_activity_at", "started_at", "agent_id"}
)
_TURN_SORT_KEYS: Final[frozenset[str]] = frozenset(
    {"started_at", "ended_at", "turn_id"}
)
_EVENT_SORT_KEYS: Final[frozenset[str]] = frozenset({"occurred_at", "event_id"})
_SEQUENCE_SORT_KEYS: Final[frozenset[str]] = frozenset({"occurred_at", "sequence_id"})
_COORDINATION_SORT_KEYS: Final[frozenset[str]] = frozenset(
    {"occurred_at", "coordination_id"}
)
_HEATMAP_GROUPS: Final[frozenset[str]] = frozenset({"agent", "event_kind", "work_item"})
_HEATMAP_RESOLUTIONS: Final[frozenset[int]] = frozenset({1, 5, 15, 30, 60})
_SURFACES: Final[frozenset[str]] = frozenset({"tauri", "cli", "mcp"})
_EVENT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"evt_[0-9a-f]{24}\Z")
_OPERATION_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"op_[0-9a-f]{24}\Z")
_LOWER_HEX_DIGEST: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}\Z")
_ABSOLUTE_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:^|\s)(?:/[^\s]*|[A-Za-z]:[\\/][^\s]*)"
)


@dataclass(frozen=True, slots=True)
class WarningRecord:
    """Describe one bounded, caller-safe non-terminal report warning."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ReportError:
    """Describe one safe failure that an adapter can map without string inspection."""

    code: ReportErrorCode
    message: str
    recoverable: bool
    operation_id: str | None = None
    current_source_revision: str | None = None
    preflight_required: bool = False
    restart_from_first_page: bool = False


T = TypeVar("T")
F = TypeVar("F")
S = TypeVar("S")


@dataclass(frozen=True, slots=True)
class ServiceResult(Generic[T]):
    """Contain exactly one successful value or one structured report error."""

    ok: bool
    value: T | None = None
    error: ReportError | None = None

    def __post_init__(self) -> None:
        if self.ok != (self.value is not None and self.error is None):
            raise ValueError("ServiceResult must contain exactly one value or error")


@dataclass(frozen=True, slots=True)
class OperationContext:
    """Bind one call to the supported protocol and a caller-supplied operation ID."""

    protocol_version: int
    operation_id: str


class CancellationToken(Protocol):
    """Expose cooperative cancellation without coupling the service to a transport."""

    def is_cancelled(self) -> bool:
        """Return whether the caller has requested cancellation."""

        ...


ProgressSink = Callable[[str, int, int | None, str], None]


@dataclass(frozen=True, slots=True)
class ReportScope:
    """Select a root task and its independent relationship closures."""

    root_thread_id: str
    include_children: bool = False
    include_collaborators: bool = False


@dataclass(frozen=True, slots=True)
class PreflightReportRequest:
    """Request read-only discovery for an exact report scope."""

    scope: ReportScope


@dataclass(frozen=True, slots=True)
class OpenSnapshotRequest:
    """Request a coherent snapshot from an accepted preflight binding."""

    scope: ReportScope
    preflight_token: str
    source_revision: str


@dataclass(frozen=True, slots=True)
class SnapshotRequest:
    """Select one open process-local snapshot."""

    snapshot_id: str


@dataclass(frozen=True, slots=True)
class AgentFilters:
    """Restrict agent rows by text, identities, roles, and states."""

    query: str = ""
    agent_ids: Sequence[str] = ()
    roles: Sequence[str] = ()
    states: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class AgentSort:
    """Select one canonical agent ordering with its fixed identity tie break."""

    key: AgentSortKey = "last_activity_at"
    direction: SortDirection = "descending"
    tie_break_key: Literal["agent_id"] = "agent_id"
    tie_break_direction: Literal["ascending"] = "ascending"


@dataclass(frozen=True, slots=True)
class TurnFilters:
    """Restrict turn rows by identities, states, agents, and time."""

    turn_ids: Sequence[str] = ()
    agent_ids: Sequence[str] = ()
    states: Sequence[str] = ()
    from_time: datetime | None = None
    to_time: datetime | None = None


@dataclass(frozen=True, slots=True)
class TurnSort:
    """Select one canonical turn ordering with its fixed identity tie break."""

    key: TurnSortKey = "started_at"
    direction: SortDirection = "ascending"
    tie_break_key: Literal["turn_id"] = "turn_id"
    tie_break_direction: Literal["ascending"] = "ascending"


@dataclass(frozen=True, slots=True)
class EventFilters:
    """Restrict event rows by identities, kinds, agents, turns, and time."""

    event_ids: Sequence[str] = ()
    agent_ids: Sequence[str] = ()
    turn_ids: Sequence[str] = ()
    kinds: Sequence[str] = ()
    from_time: datetime | None = None
    to_time: datetime | None = None


@dataclass(frozen=True, slots=True)
class EventSort:
    """Select one canonical event ordering with its fixed identity tie break."""

    key: EventSortKey = "occurred_at"
    direction: SortDirection = "ascending"
    tie_break_key: Literal["event_id"] = "event_id"
    tie_break_direction: Literal["ascending"] = "ascending"


@dataclass(frozen=True, slots=True)
class ListAgentsRequest:
    """Request one stable page of agents."""

    snapshot_id: str
    filters: AgentFilters = AgentFilters()
    sort: AgentSort = AgentSort()
    cursor: str | None = None
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class ListTurnsRequest:
    """Request one stable page of turns."""

    snapshot_id: str
    filters: TurnFilters = TurnFilters()
    sort: TurnSort = TurnSort()
    cursor: str | None = None
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class ListEventsRequest:
    """Request one stable page of events."""

    snapshot_id: str
    filters: EventFilters = EventFilters()
    sort: EventSort = EventSort()
    cursor: str | None = None
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class HeatmapQueryRequest:
    """Request one bounded grouped heatmap for a supported measure."""

    snapshot_id: str
    from_time: datetime
    to_time: datetime
    measure: TimeMeasure
    requested_resolution_minutes: int
    group_by: HeatmapGroupBy
    maximum_rows: int = 100


@dataclass(frozen=True, slots=True)
class SequenceFilters:
    """Select sequence focus, event kinds, grouping, and reasoning disclosure."""

    focus_agent_id: str | None = None
    event_filters: EventFilters = EventFilters()
    grouping: SequenceGrouping = "none"
    include_reasoning: bool = False


@dataclass(frozen=True, slots=True)
class SequenceSort:
    """Select the canonical chronological sequence ordering."""

    key: SequenceSortKey = "occurred_at"
    direction: SortDirection = "ascending"
    tie_break_key: Literal["sequence_id"] = "sequence_id"
    tie_break_direction: Literal["ascending"] = "ascending"


@dataclass(frozen=True, slots=True)
class SequenceQueryRequest:
    """Request one stable page of delegation and communication sequence rows."""

    snapshot_id: str
    filters: SequenceFilters = SequenceFilters()
    sort: SequenceSort = SequenceSort()
    cursor: str | None = None
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class CoordinationFilters:
    """Select exact canonical coordination identifiers and evidence."""

    work_item_id: str | None = None
    delegated_root_id: str | None = None
    agent_id: str | None = None
    operation: str | None = None
    evidence: EvidenceKind | None = None


@dataclass(frozen=True, slots=True)
class CoordinationSort:
    """Select the canonical chronological coordination ordering."""

    key: CoordinationSortKey = "occurred_at"
    direction: SortDirection = "ascending"
    tie_break_key: Literal["coordination_id"] = "coordination_id"
    tie_break_direction: Literal["ascending"] = "ascending"


@dataclass(frozen=True, slots=True)
class CoordinationQueryRequest:
    """Request one stable page of evidence-derived coordination rows."""

    snapshot_id: str
    filters: CoordinationFilters = CoordinationFilters()
    sort: CoordinationSort = CoordinationSort()
    cursor: str | None = None
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class EventDetailsRequest:
    """Request bounded lazy detail for one deterministic event ID."""

    snapshot_id: str
    event_id: str


@dataclass(frozen=True, slots=True)
class RefreshSnapshotRequest:
    """Request an explicit refresh of one open snapshot."""

    snapshot_id: str


@dataclass(frozen=True, slots=True)
class ExportSnapshotRequest:
    """Request staged and atomically published output for one snapshot."""

    snapshot_id: str
    surface: AutomationSurface
    target: Path
    replace: bool
    mode: ExportMode | None = None
    include_sqlite_archive: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedExportRequest:
    """Carry a validated non-optional export mode to the renderer."""

    snapshot_id: str
    surface: AutomationSurface
    target: Path
    replace: bool
    mode: ExportMode
    include_sqlite_archive: bool


@dataclass(frozen=True, slots=True)
class CloseSnapshotRequest:
    """Request release of one process-local snapshot handle."""

    snapshot_id: str


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """Return bounded scope counts and an opaque accepted binding token."""

    preflight_token: str
    root_thread_id: str
    include_children: bool
    include_collaborators: bool
    source_revision: str
    log_count: int
    total_bytes: int
    child_count: int
    collaborator_count: int
    cached_file_count: int
    changed_file_count: int
    known_event_count: int | None
    warnings: Sequence[WarningRecord]


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    """Describe one immutable coherent snapshot revision."""

    protocol_version: int
    snapshot_id: str
    revision_id: str
    scope: ReportScope
    source_revision: str
    parser_version: str
    pricing_version: str
    pricing_digest: str
    formatter_version: str
    formatter_digest: str
    observation_time: datetime
    mode: SnapshotMode
    warnings: Sequence[WarningRecord]


@dataclass(frozen=True, slots=True)
class MetricValue:
    """Expose one raw and formatted metric with evidence and provenance."""

    metric_id: str
    label: str
    value: int | float | str | None
    formatted_value: str
    unit: str | None
    evidence: EvidenceKind
    provenance: str
    description: str | None


@dataclass(frozen=True, slots=True)
class MetricGroup:
    """Group related summary metrics under one stable identifier."""

    group_id: Literal[
        "overview",
        "model",
        "context",
        "inference",
        "runtime",
        "waits",
        "work_items",
        "claims",
        "provenance",
    ]
    label: str
    metrics: Sequence[MetricValue]


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Describe one exact aware half-open report range."""

    from_time: datetime
    to_time: datetime


@dataclass(frozen=True, slots=True)
class SignificantActivity:
    """Describe one recent significant report event."""

    event_id: str
    occurred_at: datetime
    label: str
    evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class SummaryResult:
    """Return bounded display-ready snapshot metadata and grouped metrics."""

    snapshot_id: str
    revision_id: str
    title: str
    goal: str | None
    state: str
    scope: ReportScope
    observed_at: datetime
    mode: SnapshotMode
    time_range: TimeRange | None
    metric_groups: Sequence[MetricGroup]
    provenance: Sequence[str]
    recent_activity: Sequence[SignificantActivity]
    warnings: Sequence[WarningRecord]


@dataclass(frozen=True, slots=True)
class AgentRow:
    """Represent one agent in canonical list order."""

    agent_id: str
    parent_agent_id: str | None
    nickname: str | None
    role: str | None
    state: str
    started_at: datetime | None
    ended_at: datetime | None
    last_activity_at: datetime | None
    turn_count: int
    event_count: int
    evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class TurnRow:
    """Represent one turn in canonical list order."""

    turn_id: str
    agent_id: str
    started_at: datetime
    ended_at: datetime | None
    state: str
    event_count: int
    summary: str | None
    evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class EventRow:
    """Represent one bounded event in canonical list order."""

    event_id: str
    occurred_at: datetime
    agent_id: str | None
    turn_id: str | None
    kind: str
    summary: str
    evidence: EvidenceKind
    source_key: str | None
    has_detail: bool


@dataclass(frozen=True, slots=True)
class HeatmapCell:
    """Represent one bounded interval in a grouped heatmap row."""

    start_time: datetime
    end_time: datetime
    value: int | float | None
    count: int
    evidence: EvidenceKind
    primary_label: str
    secondary_label: str | None


@dataclass(frozen=True, slots=True)
class HeatmapScale:
    """Describe the value and color semantics for one heatmap row."""

    minimum: int | float
    maximum: int | float
    color_semantic: HeatmapColorSemantic
    basis: HeatmapScaleBasis


@dataclass(frozen=True, slots=True)
class HeatmapRow:
    """Represent one deterministically ordered grouped heatmap row."""

    row_id: str
    label: str
    scale: HeatmapScale
    cells: Sequence[HeatmapCell]


@dataclass(frozen=True, slots=True)
class SequenceRow:
    """Represent one delegation or communication sequence item."""

    sequence_id: str
    group_id: str | None
    occurred_at: datetime
    from_agent_id: str | None
    from_agent_label: str | None
    to_agent_id: str | None
    to_agent_label: str | None
    kind: str
    summary: str
    evidence: EvidenceKind
    event_id: str | None
    repeat_count: int
    reasoning_available: bool


@dataclass(frozen=True, slots=True)
class SequenceGroup:
    """Describe one node in the sequence grouping hierarchy."""

    group_id: str
    parent_group_id: str | None
    depth: int
    label: str
    collapsible: bool


@dataclass(frozen=True, slots=True)
class CoordinationRow:
    """Represent one evidence-labeled coordination action."""

    coordination_id: str
    occurred_at: datetime
    work_item_id: str | None
    delegated_root_id: str | None
    agent_id: str | None
    related_agent_ids: Sequence[str]
    operation: str
    summary: str
    evidence: EvidenceKind
    event_id: str | None


@dataclass(frozen=True, slots=True)
class Disclosure:
    """Expose one bounded structured event-detail disclosure."""

    label: str
    content: str
    redacted: bool


@dataclass(frozen=True, slots=True)
class EventDetail:
    """Return bounded, redacted detail for one snapshot event."""

    snapshot_id: str
    revision_id: str
    event_id: str
    occurred_at: datetime
    kind: str
    title: str
    evidence: EvidenceKind
    provenance: Sequence[str]
    summary: str | None
    disclosures: Sequence[Disclosure]
    source_key: str | None


@dataclass(frozen=True, slots=True)
class PageResult(Generic[T, F, S]):
    """Return one immutable stable page and its opaque continuation cursor."""

    snapshot_id: str
    revision_id: str
    operation: str
    items: Sequence[T]
    applied_filters: F
    applied_sort: S
    page_size: int
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class HeatmapResult:
    """Return a bounded grouped heatmap with complete applied facets."""

    snapshot_id: str
    revision_id: str
    measure: TimeMeasure
    group_by: HeatmapGroupBy
    from_time: datetime
    to_time: datetime
    requested_resolution_minutes: int
    actual_resolution_minutes: int
    maximum_rows: int
    omitted_row_count: int
    row_order: Literal["activity_descending_id_ascending"]
    total_cell_count: int
    rows: Sequence[HeatmapRow]
    provenance: Sequence[str]


@dataclass(frozen=True, slots=True)
class SequenceResult:
    """Return one canonical sequence page and its exact group hierarchy."""

    page: PageResult[SequenceRow, SequenceFilters, SequenceSort]
    groups: Sequence[SequenceGroup]


@dataclass(frozen=True, slots=True)
class RefreshSnapshotResult:
    """Return whether refresh published a changed coherent binding."""

    changed: bool
    snapshot: SnapshotMetadata


@dataclass(frozen=True, slots=True)
class ExportOmission:
    """Describe one structured export omission and its recovery."""

    section: str
    reason: str
    recovery: str


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Describe a completed atomic export publication."""

    operation_id: str
    snapshot_id: str
    revision_id: str
    mode: ExportMode
    published_target: Path
    manifest_sha256: str | None
    file_count: int
    total_byte_count: int
    warnings: Sequence[WarningRecord]
    omissions: Sequence[ExportOmission]


@dataclass(frozen=True, slots=True)
class CloseSnapshotResult:
    """Report whether the requested live snapshot handle was closed."""

    snapshot_id: str
    closed: bool


DiscoveryFailureKind = Literal[
    "not_found", "invalid_root", "protocol", "read", "cancelled"
]
NormalizationFailureKind = Literal["source_conflict", "parse", "privacy", "cancelled"]
RepositoryFailureKind = Literal[
    "schema_newer", "binding_conflict", "read", "publish", "cancelled"
]
QueryFailureKind = Literal[
    "invalid_request", "event_not_found", "read", "privacy", "cancelled"
]
ExportRenderFailureKind = Literal["invalid_request", "privacy", "render", "cancelled"]
PublicationFailureKind = Literal[
    "unauthorized_target", "replace_required", "write", "cancelled"
]
InfrastructureFailureKind = Literal["clock", "id_factory", "logging"]


@dataclass(frozen=True, slots=True)
class DiscoveryFailure(Exception):
    """Report a classified safe discovery-port failure."""

    kind: DiscoveryFailureKind
    safe_message: str
    recoverable: bool


@dataclass(frozen=True, slots=True)
class NormalizationFailure(Exception):
    """Report a classified safe normalization-port failure."""

    kind: NormalizationFailureKind
    safe_message: str
    recoverable: bool
    current_source_revision: str | None = None


@dataclass(frozen=True, slots=True)
class RepositoryFailure(Exception):
    """Report a classified safe repository-port failure."""

    kind: RepositoryFailureKind
    safe_message: str
    recoverable: bool
    current_source_revision: str | None = None


@dataclass(frozen=True, slots=True)
class QueryFailure(Exception):
    """Report a classified safe query-port failure."""

    kind: QueryFailureKind
    safe_message: str
    recoverable: bool


@dataclass(frozen=True, slots=True)
class ExportRenderFailure(Exception):
    """Report a classified safe export-renderer failure."""

    kind: ExportRenderFailureKind
    safe_message: str
    recoverable: bool


@dataclass(frozen=True, slots=True)
class PublicationFailure(Exception):
    """Report a classified safe publication-port failure."""

    kind: PublicationFailureKind
    safe_message: str
    recoverable: bool


@dataclass(frozen=True, slots=True)
class InfrastructureFailure(Exception):
    """Report a non-recoverable clock, ID, or logging failure."""

    kind: InfrastructureFailureKind
    safe_message: str
    recoverable: Literal[False] = False


DependencyFailure = (
    DiscoveryFailure
    | NormalizationFailure
    | RepositoryFailure
    | QueryFailure
    | ExportRenderFailure
    | PublicationFailure
    | InfrastructureFailure
)
_DEPENDENCY_FAILURE_CLASSES = (
    DiscoveryFailure,
    NormalizationFailure,
    RepositoryFailure,
    QueryFailure,
    ExportRenderFailure,
    PublicationFailure,
    InfrastructureFailure,
)


@dataclass(frozen=True, slots=True)
class DiscoveredSource:
    """Describe one authorized source without exposing it in public results."""

    source_key: str
    authorized_path: Path
    source_revision: str
    byte_count: int
    relationship: SourceRelationship


@dataclass(frozen=True, slots=True)
class DiscoveredScope:
    """Carry bounded discovery metadata for one exact scope."""

    scope: ReportScope
    source_revision: str
    sources: Sequence[DiscoveredSource]
    log_count: int
    total_bytes: int
    child_count: int
    collaborator_count: int
    cached_file_count: int
    changed_file_count: int
    warnings: Sequence[WarningRecord]


class NormalizedRevision(Protocol):
    """Expose only the binding and privacy proof needed for publication."""

    @property
    def source_revision(self) -> str:
        """Return the exact normalized source revision."""

        ...

    @property
    def privacy_validated(self) -> bool:
        """Return whether normalization completed its privacy gate."""

        ...


@dataclass(frozen=True, slots=True)
class PublishedRevision:
    """Identify one repository-committed coherent revision."""

    revision_id: str
    source_revision: str


class SnapshotReadHandle(Protocol):
    """Expose an opaque repository read binding for the service lease lifetime."""

    @property
    def revision_id(self) -> str:
        """Return the committed revision identifier."""

        ...

    @property
    def source_revision(self) -> str:
        """Return the source revision represented by this handle."""

        ...


@dataclass(frozen=True, slots=True)
class QuerySlice(Generic[T]):
    """Return dependency-owned page items and an opaque continuation position."""

    items: Sequence[T]
    next_position: str | None


class StagedExport(Protocol):
    """Expose only the mode and opaque staging identity needed for publication."""

    @property
    def mode(self) -> ExportMode:
        """Return the staged export mode."""

        ...

    @property
    def stage_id(self) -> str:
        """Return the opaque staging identity."""

        ...


class DiscoveryPort(Protocol):
    """Discover authorized Codex sources without returning transcript content."""

    def preflight(
        self,
        scope: ReportScope,
        roots: Sequence[Path],
        cancellation: CancellationToken,
        progress: ProgressSink | None,
    ) -> DiscoveredScope:
        """Discover bounded metadata for a new preflight."""

        ...

    def recheck(
        self,
        scope: ReportScope,
        roots: Sequence[Path],
        cancellation: CancellationToken,
        progress: ProgressSink | None,
    ) -> DiscoveredScope:
        """Rediscover an accepted scope before open or refresh."""

        ...


class NormalizationPort(Protocol):
    """Normalize an accepted source revision behind the privacy boundary."""

    def normalize(
        self,
        discovered: DiscoveredScope,
        parser_version: str,
        pricing_digest: str,
        formatter_digest: str,
        cancellation: CancellationToken,
        progress: ProgressSink | None,
    ) -> NormalizedRevision:
        """Return one privacy-validated candidate revision."""

        ...


class EventRepositoryPort(Protocol):
    """Publish and lease coherent derived revisions without exposing storage paths."""

    def known_event_count(self, source_revision: str) -> int | None:
        """Return a cached count when one is available."""

        ...

    def reuse_or_publish(
        self,
        revision: NormalizedRevision,
        cancellation: CancellationToken,
        progress: ProgressSink | None,
    ) -> PublishedRevision:
        """Reuse or atomically publish one coherent normalized revision."""

        ...

    def open_read(self, revision_id: str) -> SnapshotReadHandle:
        """Open one opaque read handle for a committed revision."""

        ...

    def release_read(self, handle: SnapshotReadHandle) -> None:
        """Release one read handle exactly once."""

        ...


class QueryPort(Protocol):
    """Read privacy-bounded report semantics from a leased snapshot handle."""

    def get_summary(
        self,
        handle: SnapshotReadHandle,
        snapshot: SnapshotMetadata,
        cancellation: CancellationToken,
    ) -> SummaryResult:
        """Return the bounded summary for a snapshot."""

        ...

    def list_agents(
        self,
        handle: SnapshotReadHandle,
        filters: AgentFilters,
        sort: AgentSort,
        after: str | None,
        limit: int,
        cancellation: CancellationToken,
    ) -> QuerySlice[AgentRow]:
        """Return one canonical agent slice."""

        ...

    def list_turns(
        self,
        handle: SnapshotReadHandle,
        filters: TurnFilters,
        sort: TurnSort,
        after: str | None,
        limit: int,
        cancellation: CancellationToken,
    ) -> QuerySlice[TurnRow]:
        """Return one canonical turn slice."""

        ...

    def list_events(
        self,
        handle: SnapshotReadHandle,
        filters: EventFilters,
        sort: EventSort,
        after: str | None,
        limit: int,
        cancellation: CancellationToken,
    ) -> QuerySlice[EventRow]:
        """Return one canonical event slice."""

        ...

    def query_time_range(
        self,
        handle: SnapshotReadHandle,
        request: HeatmapQueryRequest,
        actual_resolution_minutes: int,
        cancellation: CancellationToken,
    ) -> HeatmapResult:
        """Return one bounded grouped heatmap result."""

        ...

    def query_sequence(
        self,
        handle: SnapshotReadHandle,
        request: SequenceQueryRequest,
        after: str | None,
        cancellation: CancellationToken,
    ) -> SequenceResult:
        """Return one bounded sequence page and group hierarchy."""

        ...

    def query_coordination(
        self,
        handle: SnapshotReadHandle,
        request: CoordinationQueryRequest,
        after: str | None,
        cancellation: CancellationToken,
    ) -> QuerySlice[CoordinationRow]:
        """Return one bounded coordination slice."""

        ...

    def get_event_details(
        self,
        handle: SnapshotReadHandle,
        event_id: str,
        cancellation: CancellationToken,
    ) -> EventDetail | None:
        """Return bounded detail or no value for an absent event."""

        ...


class ExportRendererPort(Protocol):
    """Stage a complete directory or explicit summary without publishing it."""

    def stage(
        self,
        handle: SnapshotReadHandle,
        request: ResolvedExportRequest,
        cancellation: CancellationToken,
        progress: ProgressSink | None,
    ) -> StagedExport:
        """Return one opaque staged export."""

        ...


class PublicationPort(Protocol):
    """Authorize, publish, and discard surface-owned staged exports."""

    def publish(
        self,
        staged: StagedExport,
        target: Path,
        replace: bool,
        cancellation: CancellationToken,
    ) -> ExportResult:
        """Atomically publish one validated stage."""

        ...

    def discard(self, staged: StagedExport) -> None:
        """Best-effort discard one unpublished or completed stage."""

        ...


class ClockPort(Protocol):
    """Supply deterministic UTC observation times."""

    def now_utc(self) -> datetime:
        """Return the current timezone-aware UTC time."""

        ...


class IdFactoryPort(Protocol):
    """Supply opaque snapshot identities and per-instance integrity keys."""

    def new_snapshot_id(self) -> str:
        """Return one new opaque snapshot ID."""

        ...

    def new_token_key(self) -> bytes:
        """Return one unpredictable per-service token integrity key."""

        ...


class LoggerPort(Protocol):
    """Receive bounded operation metadata without sensitive request content."""

    def info(self, event: str, fields: Mapping[str, str | int | bool | None]) -> None:
        """Record one bounded informational event."""

        ...

    def error(self, event: str, fields: Mapping[str, str | int | bool | None]) -> None:
        """Record one bounded failure event."""

        ...


@dataclass(frozen=True, slots=True)
class ApplicationServiceConfig:
    """Configure one immutable process-local application service instance."""

    authorized_source_roots: Sequence[Path]
    parser_version: str
    pricing_version: str
    pricing_digest: str
    formatter_version: str
    formatter_digest: str
    default_page_size: int = DEFAULT_PAGE_SIZE
    max_page_size: int = MAX_PAGE_SIZE
    max_heatmap_cells: int = MAX_HEATMAP_CELLS


@dataclass(frozen=True, slots=True)
class ApplicationServiceDependencies:
    """Inject every discovery, storage, query, export, and infrastructure port."""

    discovery: DiscoveryPort
    normalization: NormalizationPort
    repository: EventRepositoryPort
    queries: QueryPort
    exporter: ExportRendererPort
    publisher: PublicationPort
    clock: ClockPort
    ids: IdFactoryPort
    logger: LoggerPort


_SnapshotStatus = Literal["ready", "refreshing", "exporting", "closing", "closed"]


@dataclass(frozen=True, slots=True)
class _PreflightClaims:
    scope: ReportScope
    source_revision: str
    parser_version: str
    pricing_version: str
    pricing_digest: str
    formatter_version: str
    formatter_digest: str


@dataclass(frozen=True, slots=True)
class _CursorClaims:
    snapshot_id: str
    revision_id: str
    operation: str
    filters_digest: str
    sort: str
    page_size: int
    position: str


@dataclass(slots=True)
class _SnapshotState:
    metadata: SnapshotMetadata
    scope: ReportScope
    revision_id: str
    read_handle: SnapshotReadHandle
    status: _SnapshotStatus = "ready"
    active_readers: int = 0
    mutation_active: bool = False


class _TokenDecodeError(ValueError):
    pass


class _OpaqueTokenCodec:
    def __init__(self, integrity_key: bytes) -> None:
        if not isinstance(integrity_key, bytes) or len(integrity_key) < 16:
            raise ValueError("token integrity key must contain at least 16 bytes")
        self._integrity_key = integrity_key
        self._preflight_claims: dict[str, _PreflightClaims] = {}
        self._cursor_claims: dict[str, _CursorClaims] = {}

    def encode_preflight(self, claims: _PreflightClaims) -> str:
        token = self._new_token("preflight", self._preflight_claims)
        self._preflight_claims[token] = claims
        return token

    def decode_preflight(self, token: str) -> _PreflightClaims:
        try:
            return self._preflight_claims[token]
        except (KeyError, TypeError) as error:
            raise _TokenDecodeError("unknown preflight token") from error

    def encode_cursor(self, claims: _CursorClaims) -> str:
        token = self._new_token("cursor", self._cursor_claims)
        self._cursor_claims[token] = claims
        self._trim(self._cursor_claims, _MAX_CURSOR_TOKENS)
        return token

    def decode_cursor(self, token: str) -> _CursorClaims:
        try:
            return self._cursor_claims[token]
        except (KeyError, TypeError) as error:
            raise _TokenDecodeError("unknown cursor token") from error

    def invalidate_preflight(self, token: str) -> None:
        self._preflight_claims.pop(token, None)

    def invalidate_snapshot_cursors(self, snapshot_id: str) -> None:
        for token, claims in tuple(self._cursor_claims.items()):
            if claims.snapshot_id == snapshot_id:
                del self._cursor_claims[token]

    def clear(self) -> None:
        self._preflight_claims.clear()
        self._cursor_claims.clear()

    def _new_token(self, kind: str, existing: Mapping[str, object]) -> str:
        while True:
            nonce = secrets.token_bytes(32)
            digest = hmac.new(
                self._integrity_key, kind.encode("ascii") + nonce, hashlib.sha256
            ).digest()
            token = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
            if token not in existing:
                return token

    @staticmethod
    def _trim(values: dict[str, T], maximum: int) -> None:
        while len(values) > maximum:
            del values[next(iter(values))]


class _ReadLease:
    def __init__(
        self, service: ApplicationService, snapshot_id: str, state: _SnapshotState
    ) -> None:
        self._service = service
        self._snapshot_id = snapshot_id
        self._state = state
        self._released = False

    @property
    def state(self) -> _SnapshotState:
        return self._state

    def __enter__(self) -> _SnapshotState:
        return self._state

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        if not self._released:
            with self._service._state_changed:
                self._state.active_readers -= 1
                self._released = True
                self._service._state_changed.notify_all()
        return False


class _MutationLease:
    def __init__(
        self,
        service: ApplicationService,
        snapshot_id: str,
        state: _SnapshotState,
        status: Literal["refreshing", "exporting", "closing"],
    ) -> None:
        self._service = service
        self._snapshot_id = snapshot_id
        self._state = state
        self._status = status
        self._released = False

    @property
    def state(self) -> _SnapshotState:
        return self._state

    def __enter__(self) -> _SnapshotState:
        return self._state

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        if not self._released:
            with self._service._state_changed:
                self._state.mutation_active = False
                if self._state.status != "closed":
                    self._state.status = "ready"
                self._released = True
                self._service._state_changed.notify_all()
        return False


def _validate_context(context: OperationContext) -> ReportError | None:
    if (
        isinstance(context.protocol_version, bool)
        or context.protocol_version != PROTOCOL_VERSION
    ):
        return _invalid("The report protocol version is not supported.")
    if not (
        isinstance(context.operation_id, str)
        and _OPERATION_ID_PATTERN.fullmatch(context.operation_id)
    ):
        return _invalid("operation_id must use the supported cryptographic format.")
    return None


def _validate_page(page_size: int, maximum: int) -> ReportError | None:
    if isinstance(page_size, bool) or not isinstance(page_size, int):
        return _invalid("page_size must be an integer.")
    if not 1 <= page_size <= maximum:
        return _invalid(f"page_size must be from 1 through {maximum}.")
    return None


def _validate_range(from_time: datetime, to_time: datetime) -> ReportError | None:
    if not _aware_datetime(from_time) or not _aware_datetime(to_time):
        return _invalid("The time range must use timezone-aware datetimes.")
    if from_time >= to_time:
        return _invalid("from_time must be earlier than to_time.")
    return None


def _map_dependency_failure(
    operation_id: str, failure: DependencyFailure
) -> ReportError:
    code: ReportErrorCode
    preflight_required = False
    restart = False
    current_revision = getattr(failure, "current_source_revision", None)
    if isinstance(failure, DiscoveryFailure):
        code = cast(
            ReportErrorCode,
            {
                "not_found": "REPORT_NOT_FOUND",
                "invalid_root": "REPORT_INVALID_REQUEST",
                "protocol": "REPORT_DISCOVERY_FAILED",
                "read": "REPORT_DISCOVERY_FAILED",
                "cancelled": "REPORT_CANCELLED",
            }[failure.kind],
        )
    elif isinstance(failure, NormalizationFailure):
        code = cast(
            ReportErrorCode,
            {
                "source_conflict": "REPORT_SCOPE_CONFLICT",
                "parse": "REPORT_GENERATION_FAILED",
                "privacy": "REPORT_PRIVACY_FAILED",
                "cancelled": "REPORT_CANCELLED",
            }[failure.kind],
        )
        preflight_required = failure.kind == "source_conflict"
    elif isinstance(failure, RepositoryFailure):
        code = cast(
            ReportErrorCode,
            {
                "schema_newer": "REPORT_SNAPSHOT_CONFLICT",
                "binding_conflict": "REPORT_SNAPSHOT_CONFLICT",
                "read": "REPORT_GENERATION_FAILED",
                "publish": "REPORT_GENERATION_FAILED",
                "cancelled": "REPORT_CANCELLED",
            }[failure.kind],
        )
    elif isinstance(failure, QueryFailure):
        code = cast(
            ReportErrorCode,
            {
                "invalid_request": "REPORT_INVALID_REQUEST",
                "event_not_found": "REPORT_EVENT_NOT_FOUND",
                "read": "REPORT_GENERATION_FAILED",
                "privacy": "REPORT_PRIVACY_FAILED",
                "cancelled": "REPORT_CANCELLED",
            }[failure.kind],
        )
    elif isinstance(failure, ExportRenderFailure):
        code = cast(
            ReportErrorCode,
            {
                "invalid_request": "REPORT_INVALID_REQUEST",
                "privacy": "REPORT_PRIVACY_FAILED",
                "render": "REPORT_EXPORT_FAILED",
                "cancelled": "REPORT_CANCELLED",
            }[failure.kind],
        )
    elif isinstance(failure, PublicationFailure):
        code = cast(
            ReportErrorCode,
            {
                "unauthorized_target": "REPORT_INVALID_REQUEST",
                "replace_required": "REPORT_INVALID_REQUEST",
                "write": "REPORT_WRITE_FAILED",
                "cancelled": "REPORT_CANCELLED",
            }[failure.kind],
        )
    else:
        code = "REPORT_INTERNAL_ERROR"
    message = failure.safe_message
    if not _valid_text(message, MAX_TEXT_BYTES, trim=False):
        return _safe_internal_error(operation_id)
    return ReportError(
        code=code,
        message=message,
        recoverable=failure.recoverable,
        operation_id=operation_id,
        current_source_revision=current_revision,
        preflight_required=preflight_required,
        restart_from_first_page=restart,
    )


def _safe_internal_error(operation_id: str) -> ReportError:
    return ReportError(
        code="REPORT_INTERNAL_ERROR",
        message="The report operation failed unexpectedly.",
        recoverable=False,
        operation_id=operation_id or None,
    )


def _invalid(message: str, operation_id: str | None = None) -> ReportError:
    return ReportError(
        code="REPORT_INVALID_REQUEST",
        message=message,
        recoverable=True,
        operation_id=operation_id,
    )


def _success(value: T) -> ServiceResult[T]:
    return ServiceResult(ok=True, value=value)


def _failure(error: ReportError) -> ServiceResult[T]:
    return ServiceResult(ok=False, error=error)


def _cancelled(operation_id: str) -> ReportError:
    return ReportError(
        code="REPORT_CANCELLED",
        message="The report operation was cancelled.",
        recoverable=True,
        operation_id=operation_id,
    )


def _snapshot_conflict(operation_id: str | None = None) -> ReportError:
    return ReportError(
        code="REPORT_SNAPSHOT_CONFLICT",
        message="The snapshot is busy with another report operation.",
        recoverable=True,
        operation_id=operation_id,
    )


def _snapshot_not_found(operation_id: str | None = None) -> ReportError:
    return ReportError(
        code="REPORT_SNAPSHOT_NOT_FOUND",
        message="The requested report snapshot is not open.",
        recoverable=True,
        operation_id=operation_id,
    )


def _cursor_conflict(operation_id: str | None = None) -> ReportError:
    return ReportError(
        code="REPORT_CURSOR_CONFLICT",
        message="The cursor does not match this snapshot query.",
        recoverable=True,
        operation_id=operation_id,
        restart_from_first_page=True,
    )


def _valid_text(value: object, maximum: int, *, trim: bool) -> bool:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        return False
    return not trim or value == value.strip()


def _aware_datetime(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _validate_identifier(value: object, label: str) -> ReportError | None:
    if not _valid_text(value, MAX_ID_BYTES, trim=True):
        return _invalid(f"{label} must be a non-empty bounded identifier.")
    return None


def _validate_scope(scope: ReportScope) -> ReportError | None:
    error = _validate_identifier(scope.root_thread_id, "root_thread_id")
    if error is not None:
        return error
    if (
        type(scope.include_children) is not bool
        or type(scope.include_collaborators) is not bool
    ):
        return _invalid("Report scope relationship flags must be booleans.")
    return None


def _validate_filter_values(values: Sequence[str], label: str) -> ReportError | None:
    if isinstance(values, (str, bytes)) or len(values) > MAX_FILTER_VALUES:
        return _invalid(f"{label} must contain at most {MAX_FILTER_VALUES} values.")
    seen: set[str] = set()
    for value in values:
        error = _validate_identifier(value, label)
        if error is not None:
            return error
        if value in seen:
            return _invalid(f"{label} must not contain duplicate values.")
        seen.add(value)
    return None


def _validate_optional_range(
    from_time: datetime | None, to_time: datetime | None
) -> ReportError | None:
    if (from_time is None) != (to_time is None):
        return _invalid("Both from_time and to_time are required for a filter range.")
    if from_time is not None and to_time is not None:
        return _validate_range(from_time, to_time)
    return None


def _canonical_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_canonical_value(item) for item in value]
    return value


def _filters_digest(value: object) -> str:
    payload = json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _contains_absolute_path(value: str) -> bool:
    return bool(_ABSOLUTE_PATH_PATTERN.search(value))


def _validate_bounded_text(
    value: str | None, label: str, maximum: int = MAX_TEXT_BYTES
) -> ReportError | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value.encode("utf-8")) > maximum:
        return _safe_internal_error("")
    if _contains_absolute_path(value):
        return ReportError(
            code="REPORT_PRIVACY_FAILED",
            message=f"The {label} failed report privacy validation.",
            recoverable=False,
        )
    return None


def _validate_warning(warning: WarningRecord) -> bool:
    return _valid_text(warning.code, MAX_TEXT_BYTES, trim=False) and _valid_text(
        warning.message, MAX_TEXT_BYTES, trim=False
    )


def _bounded_warnings(
    values: Sequence[WarningRecord],
) -> tuple[WarningRecord, ...] | None:
    if any(not _validate_warning(value) for value in values):
        return None
    if len(values) <= MAX_WARNINGS:
        return tuple(values)
    return tuple(values[: MAX_WARNINGS - 1]) + (
        WarningRecord(
            code="REPORT_WARNINGS_OMITTED",
            message="Additional report warnings were omitted.",
        ),
    )


def _bounded_strings(
    values: Sequence[str], maximum_items: int
) -> tuple[str, ...] | None:
    if any(
        not _valid_text(value, MAX_TEXT_BYTES, trim=False)
        or _contains_absolute_path(value)
        for value in values
    ):
        return None
    if len(values) <= maximum_items:
        return tuple(values)
    return tuple(values[: maximum_items - 1]) + (
        "Additional report entries were omitted.",
    )


def _bounded_export_omissions(
    values: Sequence[ExportOmission],
) -> tuple[ExportOmission, ...] | None:
    if len(values) > MAX_PROVENANCE_ITEMS:
        return None
    for value in values:
        if any(
            _validate_bounded_text(text, "export omission") is not None
            for text in (value.section, value.reason, value.recovery)
        ):
            return None
    return tuple(values)


class ApplicationService:
    """Coordinate one process-local report lifecycle through injected ports.

    Construct the service with validated immutable configuration and one dependency
    bundle. Callers preflight a scope, open a snapshot, query or export it, and close
    it. Expected failures return ``ServiceResult`` errors. ``close()`` rejects new
    work, drains active leases, and releases every remaining repository handle.
    """

    def __init__(
        self,
        config: ApplicationServiceConfig,
        dependencies: ApplicationServiceDependencies,
    ) -> None:
        _validate_config(config)
        self._config = replace(
            config, authorized_source_roots=tuple(config.authorized_source_roots)
        )
        self._dependencies = dependencies
        self._snapshots: dict[str, _SnapshotState] = {}
        self._closed = False
        self._state_lock = threading.RLock()
        self._state_changed = threading.Condition(self._state_lock)
        self._preflight_expiry: dict[str, datetime] = {}
        try:
            integrity_key = dependencies.ids.new_token_key()
            self._token_codec = _OpaqueTokenCodec(integrity_key)
        except (InfrastructureFailure, ValueError, TypeError) as error:
            raise RuntimeError(
                "Unable to initialize report token integrity."
            ) from error
        except Exception as error:
            raise RuntimeError("Unable to initialize the report service.") from error

    def preflight_report(
        self,
        context: OperationContext,
        request: PreflightReportRequest,
        *,
        cancellation: CancellationToken,
        progress: ProgressSink | None = None,
    ) -> ServiceResult[PreflightResult]:
        """Discover one scope and return a signed binding without creating a snapshot."""

        error = self._common_gate(context)
        if error is None:
            error = _validate_scope(request.scope)
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))
        if cancellation.is_cancelled():
            return _failure(_cancelled(context.operation_id))
        try:
            discovered = self._dependencies.discovery.preflight(
                request.scope,
                self._config.authorized_source_roots,
                cancellation,
                progress,
            )
            if cancellation.is_cancelled():
                return _failure(_cancelled(context.operation_id))
            validation = self._validate_discovered(discovered, request.scope)
            if validation is not None:
                return _failure(self._with_operation(validation, context.operation_id))
            known_event_count = self._dependencies.repository.known_event_count(
                discovered.source_revision
            )
            if cancellation.is_cancelled():
                return _failure(_cancelled(context.operation_id))
            if known_event_count is not None and (
                isinstance(known_event_count, bool)
                or not isinstance(known_event_count, int)
                or known_event_count < 0
            ):
                return _failure(_safe_internal_error(context.operation_id))
            warnings = _bounded_warnings(discovered.warnings)
            if warnings is None:
                return _failure(_safe_internal_error(context.operation_id))
            now = self._dependencies.clock.now_utc()
            if not _aware_datetime(now):
                return _failure(_safe_internal_error(context.operation_id))
            claims = _PreflightClaims(
                scope=request.scope,
                source_revision=discovered.source_revision,
                parser_version=self._config.parser_version,
                pricing_version=self._config.pricing_version,
                pricing_digest=self._config.pricing_digest,
                formatter_version=self._config.formatter_version,
                formatter_digest=self._config.formatter_digest,
            )
            with self._state_changed:
                if self._closed:
                    return _failure(_snapshot_conflict(context.operation_id))
                self._purge_preflight_locked(now)
                while len(self._preflight_expiry) >= _MAX_PREFLIGHT_TOKENS:
                    oldest = next(iter(self._preflight_expiry))
                    del self._preflight_expiry[oldest]
                    self._token_codec.invalidate_preflight(oldest)
                token = self._token_codec.encode_preflight(claims)
                self._preflight_expiry[token] = now + timedelta(
                    seconds=_PREFLIGHT_TOKEN_TTL_SECONDS
                )
            return _success(
                PreflightResult(
                    preflight_token=token,
                    root_thread_id=request.scope.root_thread_id,
                    include_children=request.scope.include_children,
                    include_collaborators=request.scope.include_collaborators,
                    source_revision=discovered.source_revision,
                    log_count=discovered.log_count,
                    total_bytes=discovered.total_bytes,
                    child_count=discovered.child_count,
                    collaborator_count=discovered.collaborator_count,
                    cached_file_count=discovered.cached_file_count,
                    changed_file_count=discovered.changed_file_count,
                    known_event_count=known_event_count,
                    warnings=warnings,
                )
            )
        except _DEPENDENCY_FAILURE_CLASSES as failure:
            self._log_dependency_failure(
                context.operation_id, "preflight", "discovery_or_repository", failure
            )
            return _failure(_map_dependency_failure(context.operation_id, failure))
        except Exception as unexpected:
            self._log_unexpected(
                context.operation_id,
                "preflight",
                "discovery_or_repository",
                unexpected,
            )
            return _failure(_safe_internal_error(context.operation_id))

    def open_snapshot(
        self,
        context: OperationContext,
        request: OpenSnapshotRequest,
        *,
        cancellation: CancellationToken,
        progress: ProgressSink | None = None,
    ) -> ServiceResult[SnapshotMetadata]:
        """Normalize and publish one coherent snapshot from an accepted preflight."""

        error = self._common_gate(context)
        if error is None:
            error = _validate_scope(request.scope)
        if error is None and not _valid_text(
            request.preflight_token, MAX_ID_BYTES, trim=True
        ):
            error = _invalid("preflight_token must be a valid opaque token.")
        if error is None:
            error = _validate_identifier(request.source_revision, "source_revision")
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))
        if cancellation.is_cancelled():
            return _failure(_cancelled(context.operation_id))
        try:
            claims = self._consume_preflight(request.preflight_token)
        except _DEPENDENCY_FAILURE_CLASSES as failure:
            self._log_dependency_failure(
                context.operation_id, "open_snapshot", "clock", failure
            )
            return _failure(_map_dependency_failure(context.operation_id, failure))
        except Exception as unexpected:
            self._log_unexpected(
                context.operation_id, "open_snapshot", "clock", unexpected
            )
            return _failure(_safe_internal_error(context.operation_id))
        if claims is None:
            return _failure(
                ReportError(
                    code="REPORT_SCOPE_CONFLICT",
                    message="The preflight binding is invalid or stale.",
                    recoverable=True,
                    operation_id=context.operation_id,
                    preflight_required=True,
                )
            )
        if (
            claims.scope != request.scope
            or claims.source_revision != request.source_revision
            or claims.parser_version != self._config.parser_version
            or claims.pricing_version != self._config.pricing_version
            or claims.pricing_digest != self._config.pricing_digest
            or claims.formatter_version != self._config.formatter_version
            or claims.formatter_digest != self._config.formatter_digest
        ):
            return _failure(
                ReportError(
                    code="REPORT_SCOPE_CONFLICT",
                    message="The preflight binding does not match this report request.",
                    recoverable=True,
                    operation_id=context.operation_id,
                    preflight_required=True,
                )
            )
        handle: SnapshotReadHandle | None = None
        try:
            discovered = self._dependencies.discovery.recheck(
                request.scope,
                self._config.authorized_source_roots,
                cancellation,
                progress,
            )
            validation = self._validate_discovered(discovered, request.scope)
            if validation is not None:
                return _failure(self._with_operation(validation, context.operation_id))
            if discovered.source_revision != request.source_revision:
                return _failure(
                    ReportError(
                        code="REPORT_SCOPE_CONFLICT",
                        message="The report source changed after preflight.",
                        recoverable=True,
                        operation_id=context.operation_id,
                        current_source_revision=discovered.source_revision,
                        preflight_required=True,
                    )
                )
            if cancellation.is_cancelled():
                return _failure(_cancelled(context.operation_id))
            normalized = self._dependencies.normalization.normalize(
                discovered,
                self._config.parser_version,
                self._config.pricing_digest,
                self._config.formatter_digest,
                cancellation,
                progress,
            )
            if (
                not normalized.privacy_validated
                or normalized.source_revision != discovered.source_revision
            ):
                return _failure(
                    ReportError(
                        code="REPORT_PRIVACY_FAILED",
                        message="The normalized report revision failed privacy validation.",
                        recoverable=False,
                        operation_id=context.operation_id,
                    )
                )
            if cancellation.is_cancelled():
                return _failure(_cancelled(context.operation_id))
            try:
                published = self._dependencies.repository.reuse_or_publish(
                    normalized, cancellation, progress
                )
            except RepositoryFailure as failure:
                self._log_dependency_failure(
                    context.operation_id,
                    "open_snapshot",
                    "repository",
                    failure,
                )
                return _failure(
                    self._map_repository_publication_failure(
                        context.operation_id, failure
                    )
                )
            if (
                published.source_revision != discovered.source_revision
                or not _valid_text(published.revision_id, MAX_ID_BYTES, trim=True)
            ):
                return _failure(_safe_internal_error(context.operation_id))
            if cancellation.is_cancelled():
                return _failure(_cancelled(context.operation_id))
            handle = self._dependencies.repository.open_read(published.revision_id)
            if (
                handle.revision_id != published.revision_id
                or handle.source_revision != published.source_revision
            ):
                return _failure(_safe_internal_error(context.operation_id))
            snapshot_id = self._dependencies.ids.new_snapshot_id()
            observation_time = self._dependencies.clock.now_utc()
            if _validate_identifier(
                snapshot_id, "snapshot_id"
            ) is not None or not _aware_datetime(observation_time):
                return _failure(_safe_internal_error(context.operation_id))
            if cancellation.is_cancelled():
                return _failure(_cancelled(context.operation_id))
            warnings = _bounded_warnings(discovered.warnings)
            if warnings is None:
                return _failure(_safe_internal_error(context.operation_id))
            metadata = SnapshotMetadata(
                protocol_version=PROTOCOL_VERSION,
                snapshot_id=snapshot_id,
                revision_id=published.revision_id,
                scope=request.scope,
                source_revision=published.source_revision,
                parser_version=self._config.parser_version,
                pricing_version=self._config.pricing_version,
                pricing_digest=self._config.pricing_digest,
                formatter_version=self._config.formatter_version,
                formatter_digest=self._config.formatter_digest,
                observation_time=observation_time.astimezone(timezone.utc),
                mode="live",
                warnings=warnings,
            )
            with self._state_changed:
                if self._closed or snapshot_id in self._snapshots:
                    return _failure(_safe_internal_error(context.operation_id))
                self._snapshots[snapshot_id] = _SnapshotState(
                    metadata=metadata,
                    scope=request.scope,
                    revision_id=published.revision_id,
                    read_handle=handle,
                )
                handle = None
            return _success(metadata)
        except _DEPENDENCY_FAILURE_CLASSES as failure:
            self._log_dependency_failure(
                context.operation_id, "open_snapshot", "snapshot_dependencies", failure
            )
            return _failure(_map_dependency_failure(context.operation_id, failure))
        except Exception as unexpected:
            self._log_unexpected(
                context.operation_id,
                "open_snapshot",
                "snapshot_dependencies",
                unexpected,
            )
            return _failure(_safe_internal_error(context.operation_id))
        finally:
            if handle is not None:
                self._release_handle_cleanup(
                    handle, context.operation_id, "open_snapshot"
                )

    def get_summary(
        self,
        context: OperationContext,
        request: SnapshotRequest,
        *,
        cancellation: CancellationToken,
    ) -> ServiceResult[SummaryResult]:
        """Return a bounded sanitized summary while holding a read lease."""

        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is not None:
            return _failure(error)
        lease_result = _acquire_read(self, request.snapshot_id)
        if not lease_result.ok:
            return cast(ServiceResult[SummaryResult], lease_result)
        lease = cast(_ReadLease, lease_result.value)
        try:
            with lease as state:
                if cancellation.is_cancelled():
                    return _failure(_cancelled(context.operation_id))
                try:
                    result = self._dependencies.queries.get_summary(
                        state.read_handle, state.metadata, cancellation
                    )
                except _DEPENDENCY_FAILURE_CLASSES as failure:
                    self._log_dependency_failure(
                        context.operation_id, "get_summary", "query", failure
                    )
                    return _failure(
                        _map_dependency_failure(context.operation_id, failure)
                    )
                except Exception as unexpected:
                    self._log_unexpected(
                        context.operation_id, "get_summary", "query", unexpected
                    )
                    return _failure(_safe_internal_error(context.operation_id))
                if cancellation.is_cancelled():
                    return _failure(_cancelled(context.operation_id))
                normalized = self._normalize_summary(result, state.metadata)
                if isinstance(normalized, ReportError):
                    return _failure(
                        self._with_operation(normalized, context.operation_id)
                    )
                return _success(normalized)
        finally:
            # The context manager owns the count; this finally documents the
            # contract that every return and exception crosses lease cleanup.
            pass

    def list_agents(
        self,
        context: OperationContext,
        request: ListAgentsRequest,
        *,
        cancellation: CancellationToken,
    ) -> ServiceResult[PageResult[AgentRow, AgentFilters, AgentSort]]:
        """Return one stable agent page bound to all filters and page options."""

        request = replace(
            request,
            filters=replace(
                request.filters,
                agent_ids=tuple(request.filters.agent_ids),
                roles=tuple(request.filters.roles),
                states=tuple(request.filters.states),
            ),
        )
        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None:
            error = self._validate_agent_filters(request.filters)
        if error is None:
            error = self._validate_agent_sort(request.sort)
        if error is None:
            error = _validate_page(request.page_size, self._config.max_page_size)
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))

        def query(
            handle: SnapshotReadHandle, after: str | None
        ) -> QuerySlice[AgentRow]:
            return self._run_query_call(
                context,
                "list_agents",
                cancellation,
                lambda: self._dependencies.queries.list_agents(
                    handle,
                    request.filters,
                    request.sort,
                    after,
                    request.page_size,
                    cancellation,
                ),
            )

        return _query_page(
            self,
            context,
            request,
            "list_agents",
            request.filters,
            request.sort,
            query,
        )

    def list_turns(
        self,
        context: OperationContext,
        request: ListTurnsRequest,
        *,
        cancellation: CancellationToken,
    ) -> ServiceResult[PageResult[TurnRow, TurnFilters, TurnSort]]:
        """Return one stable turn page bound to all filters and page options."""

        request = replace(
            request,
            filters=replace(
                request.filters,
                turn_ids=tuple(request.filters.turn_ids),
                agent_ids=tuple(request.filters.agent_ids),
                states=tuple(request.filters.states),
                from_time=_utc_or_none(request.filters.from_time),
                to_time=_utc_or_none(request.filters.to_time),
            ),
        )
        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None:
            error = self._validate_turn_filters(request.filters)
        if error is None:
            error = self._validate_turn_sort(request.sort)
        if error is None:
            error = _validate_page(request.page_size, self._config.max_page_size)
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))

        def query(handle: SnapshotReadHandle, after: str | None) -> QuerySlice[TurnRow]:
            return self._run_query_call(
                context,
                "list_turns",
                cancellation,
                lambda: self._dependencies.queries.list_turns(
                    handle,
                    request.filters,
                    request.sort,
                    after,
                    request.page_size,
                    cancellation,
                ),
            )

        return _query_page(
            self,
            context,
            request,
            "list_turns",
            request.filters,
            request.sort,
            query,
        )

    def list_events(
        self,
        context: OperationContext,
        request: ListEventsRequest,
        *,
        cancellation: CancellationToken,
    ) -> ServiceResult[PageResult[EventRow, EventFilters, EventSort]]:
        """Return one stable bounded event page bound to all selectors."""

        request = replace(request, filters=_immutable_event_filters(request.filters))
        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None:
            error = self._validate_event_filters(request.filters)
        if error is None:
            error = self._validate_event_sort(request.sort)
        if error is None:
            error = _validate_page(request.page_size, self._config.max_page_size)
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))

        def query(
            handle: SnapshotReadHandle, after: str | None
        ) -> QuerySlice[EventRow]:
            return self._run_query_call(
                context,
                "list_events",
                cancellation,
                lambda: self._dependencies.queries.list_events(
                    handle,
                    request.filters,
                    request.sort,
                    after,
                    request.page_size,
                    cancellation,
                ),
            )

        return _query_page(
            self,
            context,
            request,
            "list_events",
            request.filters,
            request.sort,
            query,
        )

    def query_time_range(
        self,
        context: OperationContext,
        request: HeatmapQueryRequest,
        *,
        cancellation: CancellationToken,
    ) -> ServiceResult[HeatmapResult]:
        """Return a grouped heatmap with at most 2,000 cells."""

        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None:
            error = _validate_range(request.from_time, request.to_time)
        if error is None and request.measure not in _TIME_MEASURES:
            error = _invalid("The requested time-series measure is not supported.")
        if error is None and request.group_by not in _HEATMAP_GROUPS:
            error = _invalid("The heatmap grouping is not supported.")
        if error is None and (
            isinstance(request.requested_resolution_minutes, bool)
            or not isinstance(request.requested_resolution_minutes, int)
            or request.requested_resolution_minutes not in _HEATMAP_RESOLUTIONS
        ):
            error = _invalid(
                "requested_resolution_minutes must be one of 1, 5, 15, 30, or 60."
            )
        if error is None and (
            isinstance(request.maximum_rows, bool)
            or not isinstance(request.maximum_rows, int)
            or not 1 <= request.maximum_rows <= 200
        ):
            error = _invalid("maximum_rows must be from 1 through 200.")
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))
        actual_resolution = request.requested_resolution_minutes
        lease_result = _acquire_read(self, request.snapshot_id)
        if not lease_result.ok:
            return cast(ServiceResult[HeatmapResult], lease_result)
        lease = cast(_ReadLease, lease_result.value)
        with lease as state:
            try:
                result = self._run_query_call(
                    context,
                    "query_time_range",
                    cancellation,
                    lambda: self._dependencies.queries.query_time_range(
                        state.read_handle,
                        request,
                        actual_resolution,
                        cancellation,
                    ),
                )
                coarsened_resolution = _actual_resolution_minutes(
                    request.from_time,
                    request.to_time,
                    request.requested_resolution_minutes,
                    self._config.max_heatmap_cells,
                    len(result.rows),
                )
                if coarsened_resolution != actual_resolution:
                    actual_resolution = coarsened_resolution
                    result = self._run_query_call(
                        context,
                        "query_time_range",
                        cancellation,
                        lambda: self._dependencies.queries.query_time_range(
                            state.read_handle,
                            request,
                            actual_resolution,
                            cancellation,
                        ),
                    )
            except _OperationFailure as failure:
                return _failure(failure.error)
            validation = self._validate_heatmap(
                result, request, actual_resolution, state.metadata
            )
            if validation is not None:
                return _failure(self._with_operation(validation, context.operation_id))
            return _success(
                replace(
                    result,
                    from_time=result.from_time.astimezone(timezone.utc),
                    to_time=result.to_time.astimezone(timezone.utc),
                    rows=tuple(
                        replace(
                            row,
                            cells=tuple(
                                replace(
                                    cell,
                                    start_time=cell.start_time.astimezone(timezone.utc),
                                    end_time=cell.end_time.astimezone(timezone.utc),
                                )
                                for cell in row.cells
                            ),
                        )
                        for row in result.rows
                    ),
                    provenance=cast(
                        tuple[str, ...],
                        _bounded_strings(result.provenance, MAX_PROVENANCE_ITEMS),
                    ),
                )
            )

    def query_sequence(
        self,
        context: OperationContext,
        request: SequenceQueryRequest,
        *,
        cancellation: CancellationToken,
    ) -> ServiceResult[SequenceResult]:
        """Return one stable bounded delegation or communication sequence page."""

        request = replace(
            request,
            filters=replace(
                request.filters,
                event_filters=_immutable_event_filters(request.filters.event_filters),
            ),
        )
        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None and request.filters.focus_agent_id is not None:
            error = _validate_identifier(
                request.filters.focus_agent_id, "focus_agent_id"
            )
        if error is None:
            error = self._validate_event_filters(request.filters.event_filters)
        if error is None and request.filters.grouping not in _GROUPINGS:
            error = _invalid("The sequence grouping is not supported.")
        if error is None and type(request.filters.include_reasoning) is not bool:
            error = _invalid("include_reasoning must be a boolean.")
        if error is None:
            error = self._validate_sequence_sort(request.sort)
        if error is None:
            error = _validate_page(request.page_size, self._config.max_page_size)
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))

        def query(handle: SnapshotReadHandle, after: str | None) -> SequenceResult:
            return self._run_query_call(
                context,
                "query_sequence",
                cancellation,
                lambda: self._dependencies.queries.query_sequence(
                    handle, request, after, cancellation
                ),
            )

        return _query_sequence_result(
            self,
            context,
            request,
            "query_sequence",
            query,
        )

    def query_coordination(
        self,
        context: OperationContext,
        request: CoordinationQueryRequest,
        *,
        cancellation: CancellationToken,
    ) -> ServiceResult[
        PageResult[CoordinationRow, CoordinationFilters, CoordinationSort]
    ]:
        """Return one stable bounded coordination page with explicit evidence labels."""

        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None:
            error = self._validate_coordination_filters(request.filters)
        if error is None:
            error = self._validate_coordination_sort(request.sort)
        if error is None:
            error = _validate_page(request.page_size, self._config.max_page_size)
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))

        def query(
            handle: SnapshotReadHandle, after: str | None
        ) -> QuerySlice[CoordinationRow]:
            return self._run_query_call(
                context,
                "query_coordination",
                cancellation,
                lambda: self._dependencies.queries.query_coordination(
                    handle, request, after, cancellation
                ),
            )

        return _query_page(
            self,
            context,
            request,
            "query_coordination",
            request.filters,
            request.sort,
            query,
        )

    def get_event_details(
        self,
        context: OperationContext,
        request: EventDetailsRequest,
        *,
        cancellation: CancellationToken,
    ) -> ServiceResult[EventDetail]:
        """Resolve one event lazily and return bounded redacted detail."""

        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None and not (
            isinstance(request.event_id, str)
            and _EVENT_ID_PATTERN.fullmatch(request.event_id)
        ):
            error = _invalid("event_id must use the supported snapshot event format.")
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))
        lease_result = _acquire_read(self, request.snapshot_id)
        if not lease_result.ok:
            return cast(ServiceResult[EventDetail], lease_result)
        lease = cast(_ReadLease, lease_result.value)
        with lease as state:
            try:
                detail = self._run_query_call(
                    context,
                    "get_event_details",
                    cancellation,
                    lambda: self._dependencies.queries.get_event_details(
                        state.read_handle, request.event_id, cancellation
                    ),
                )
            except _OperationFailure as failure:
                return _failure(failure.error)
            if detail is None:
                return _failure(
                    ReportError(
                        code="REPORT_EVENT_NOT_FOUND",
                        message="The event was not found in this report snapshot.",
                        recoverable=True,
                        operation_id=context.operation_id,
                    )
                )
            normalized = self._normalize_event_detail(
                detail, request.snapshot_id, request.event_id
            )
            if isinstance(normalized, ReportError):
                return _failure(self._with_operation(normalized, context.operation_id))
            return _success(normalized)

    def refresh_snapshot(
        self,
        context: OperationContext,
        request: RefreshSnapshotRequest,
        *,
        cancellation: CancellationToken,
        progress: ProgressSink | None = None,
    ) -> ServiceResult[RefreshSnapshotResult]:
        """Explicitly replace a snapshot only after a changed revision is committed."""

        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is not None:
            return _failure(error)
        lease_result = _acquire_mutation(
            self,
            request.snapshot_id,
            "refreshing",
            require_no_readers=True,
        )
        if not lease_result.ok:
            return cast(ServiceResult[RefreshSnapshotResult], lease_result)
        lease = cast(_MutationLease, lease_result.value)
        new_handle: SnapshotReadHandle | None = None
        with lease as state:
            try:
                if cancellation.is_cancelled():
                    return _failure(_cancelled(context.operation_id))
                discovered = self._dependencies.discovery.recheck(
                    state.scope,
                    self._config.authorized_source_roots,
                    cancellation,
                    progress,
                )
                validation = self._validate_discovered(discovered, state.scope)
                if validation is not None:
                    return _failure(
                        self._with_operation(validation, context.operation_id)
                    )
                if cancellation.is_cancelled():
                    return _failure(_cancelled(context.operation_id))
                if discovered.source_revision == state.metadata.source_revision:
                    return _success(
                        RefreshSnapshotResult(changed=False, snapshot=state.metadata)
                    )
                normalized = self._dependencies.normalization.normalize(
                    discovered,
                    self._config.parser_version,
                    self._config.pricing_digest,
                    self._config.formatter_digest,
                    cancellation,
                    progress,
                )
                if (
                    not normalized.privacy_validated
                    or normalized.source_revision != discovered.source_revision
                ):
                    return _failure(
                        ReportError(
                            code="REPORT_PRIVACY_FAILED",
                            message="The normalized report revision failed privacy validation.",
                            recoverable=False,
                            operation_id=context.operation_id,
                        )
                    )
                if cancellation.is_cancelled():
                    return _failure(_cancelled(context.operation_id))
                try:
                    published = self._dependencies.repository.reuse_or_publish(
                        normalized, cancellation, progress
                    )
                except RepositoryFailure as failure:
                    self._log_dependency_failure(
                        context.operation_id,
                        "refresh_snapshot",
                        "repository",
                        failure,
                    )
                    return _failure(
                        self._map_repository_publication_failure(
                            context.operation_id, failure
                        )
                    )
                if (
                    published.source_revision != discovered.source_revision
                    or not _valid_text(published.revision_id, MAX_ID_BYTES, trim=True)
                ):
                    return _failure(_safe_internal_error(context.operation_id))
                if cancellation.is_cancelled():
                    return _failure(_cancelled(context.operation_id))
                new_handle = self._dependencies.repository.open_read(
                    published.revision_id
                )
                if (
                    new_handle.revision_id != published.revision_id
                    or new_handle.source_revision != published.source_revision
                ):
                    return _failure(_safe_internal_error(context.operation_id))
                observation_time = self._dependencies.clock.now_utc()
                warnings = _bounded_warnings(discovered.warnings)
                if not _aware_datetime(observation_time) or warnings is None:
                    return _failure(_safe_internal_error(context.operation_id))
                if cancellation.is_cancelled():
                    return _failure(_cancelled(context.operation_id))
                new_metadata = replace(
                    state.metadata,
                    revision_id=published.revision_id,
                    source_revision=published.source_revision,
                    observation_time=observation_time.astimezone(timezone.utc),
                    warnings=warnings,
                )
                old_handle = state.read_handle
                with self._state_changed:
                    if (
                        self._closed
                        or self._snapshots.get(request.snapshot_id) is not state
                    ):
                        return _failure(_safe_internal_error(context.operation_id))
                    state.metadata = new_metadata
                    state.revision_id = published.revision_id
                    state.read_handle = new_handle
                    self._token_codec.invalidate_snapshot_cursors(request.snapshot_id)
                    new_handle = None
                release_error = self._release_handle(
                    old_handle, context.operation_id, "refresh_snapshot"
                )
                if release_error is not None:
                    return _failure(release_error)
                return _success(
                    RefreshSnapshotResult(changed=True, snapshot=new_metadata)
                )
            except _DEPENDENCY_FAILURE_CLASSES as failure:
                self._log_dependency_failure(
                    context.operation_id,
                    "refresh_snapshot",
                    "refresh_dependencies",
                    failure,
                )
                return _failure(_map_dependency_failure(context.operation_id, failure))
            except Exception as unexpected:
                self._log_unexpected(
                    context.operation_id,
                    "refresh_snapshot",
                    "refresh_dependencies",
                    unexpected,
                )
                return _failure(_safe_internal_error(context.operation_id))
            finally:
                if new_handle is not None:
                    self._release_handle_cleanup(
                        new_handle, context.operation_id, "refresh_snapshot"
                    )

    def export_snapshot(
        self,
        context: OperationContext,
        request: ExportSnapshotRequest,
        *,
        cancellation: CancellationToken,
        progress: ProgressSink | None = None,
    ) -> ServiceResult[ExportResult]:
        """Stage and atomically publish directory-default or explicit-summary output."""

        error = self._common_snapshot_gate(context, request.snapshot_id)
        mode_result = resolve_automation_export_mode(request.surface, request.mode)
        if error is None and not mode_result.ok:
            error = cast(ReportError, mode_result.error)
        if error is None and (
            not isinstance(request.target, Path) or not request.target.is_absolute()
        ):
            error = _invalid("The export target must be an absolute path.")
        if error is None and type(request.replace) is not bool:
            error = _invalid("replace must be a boolean.")
        if error is None and type(request.include_sqlite_archive) is not bool:
            error = _invalid("include_sqlite_archive must be a boolean.")
        mode = mode_result.value
        if error is None and request.include_sqlite_archive and mode != "directory":
            error = _invalid(
                "include_sqlite_archive is available only for directory exports."
            )
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))
        resolved = ResolvedExportRequest(
            snapshot_id=request.snapshot_id,
            surface=request.surface,
            target=request.target,
            replace=request.replace,
            mode=cast(ExportMode, mode),
            include_sqlite_archive=request.include_sqlite_archive,
        )
        lease_result = _acquire_mutation(
            self,
            request.snapshot_id,
            "exporting",
            require_no_readers=True,
        )
        if not lease_result.ok:
            return cast(ServiceResult[ExportResult], lease_result)
        lease = cast(_MutationLease, lease_result.value)
        staged: StagedExport | None = None
        published = False
        with lease as state:
            try:
                if cancellation.is_cancelled():
                    return _failure(_cancelled(context.operation_id))
                staged = self._dependencies.exporter.stage(
                    state.read_handle, resolved, cancellation, progress
                )
                if staged.mode != resolved.mode or not _valid_text(
                    staged.stage_id, MAX_ID_BYTES, trim=True
                ):
                    return _failure(_safe_internal_error(context.operation_id))
                if cancellation.is_cancelled():
                    return _failure(_cancelled(context.operation_id))
                result = self._dependencies.publisher.publish(
                    staged,
                    request.target,
                    request.replace,
                    cancellation,
                )
                published = True
                validation = self._validate_export_result(
                    result,
                    resolved,
                    context.operation_id,
                    state.metadata,
                )
                if validation is not None:
                    return _failure(
                        self._with_operation(validation, context.operation_id)
                    )
                return _success(
                    replace(
                        result,
                        warnings=cast(
                            tuple[WarningRecord, ...],
                            _bounded_warnings(result.warnings),
                        ),
                        omissions=cast(
                            tuple[ExportOmission, ...],
                            _bounded_export_omissions(result.omissions),
                        ),
                    )
                )
            except _DEPENDENCY_FAILURE_CLASSES as failure:
                self._log_dependency_failure(
                    context.operation_id,
                    "export_snapshot",
                    "exporter_or_publisher",
                    failure,
                )
                return _failure(_map_dependency_failure(context.operation_id, failure))
            except Exception as unexpected:
                self._log_unexpected(
                    context.operation_id,
                    "export_snapshot",
                    "exporter_or_publisher",
                    unexpected,
                )
                return _failure(_safe_internal_error(context.operation_id))
            finally:
                if staged is not None and not published:
                    self._discard_stage(staged, context.operation_id)

    def close_snapshot(
        self, context: OperationContext, request: CloseSnapshotRequest
    ) -> ServiceResult[CloseSnapshotResult]:
        """Release one idle snapshot handle without purging derived repository data."""

        error = self._common_gate(context)
        if error is None:
            error = _validate_identifier(request.snapshot_id, "snapshot_id")
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))
        with self._state_changed:
            if request.snapshot_id not in self._snapshots:
                return _success(
                    CloseSnapshotResult(snapshot_id=request.snapshot_id, closed=False)
                )
        lease_result = _acquire_mutation(
            self,
            request.snapshot_id,
            "closing",
            require_no_readers=True,
        )
        if not lease_result.ok:
            return cast(ServiceResult[CloseSnapshotResult], lease_result)
        lease = cast(_MutationLease, lease_result.value)
        with lease as state:
            with self._state_changed:
                if self._snapshots.get(request.snapshot_id) is not state:
                    return _success(
                        CloseSnapshotResult(
                            snapshot_id=request.snapshot_id, closed=False
                        )
                    )
                del self._snapshots[request.snapshot_id]
                state.status = "closed"
                self._token_codec.invalidate_snapshot_cursors(request.snapshot_id)
            release_error = self._release_handle(
                state.read_handle, context.operation_id, "close_snapshot"
            )
            if release_error is not None:
                return _failure(release_error)
            return _success(
                CloseSnapshotResult(snapshot_id=request.snapshot_id, closed=True)
            )

    def close(self) -> None:
        """Reject new work, drain active leases, and release every remaining handle."""

        with self._state_changed:
            if self._closed and not self._snapshots:
                return
            self._closed = True
            while any(
                state.active_readers > 0 or state.mutation_active
                for state in self._snapshots.values()
            ):
                self._state_changed.wait()
            states = tuple(self._snapshots.values())
            self._snapshots.clear()
            self._preflight_expiry.clear()
            self._token_codec.clear()
            for state in states:
                state.status = "closed"
        for state in states:
            self._release_handle_cleanup(state.read_handle, "shutdown", "close")

    def _common_gate(self, context: OperationContext) -> ReportError | None:
        error = _validate_context(context)
        if error is not None:
            return error
        with self._state_changed:
            if self._closed:
                return ReportError(
                    code="REPORT_SNAPSHOT_CONFLICT",
                    message="The report service is closed.",
                    recoverable=False,
                    operation_id=context.operation_id,
                )
        return None

    def _consume_preflight(self, token: str) -> _PreflightClaims | None:
        now = self._dependencies.clock.now_utc()
        if not _aware_datetime(now):
            raise InfrastructureFailure(
                "clock", "The report clock returned an invalid observation time."
            )
        with self._state_changed:
            self._purge_preflight_locked(now)
            if token not in self._preflight_expiry:
                return None
            del self._preflight_expiry[token]
            try:
                return self._token_codec.decode_preflight(token)
            except _TokenDecodeError:
                return None
            finally:
                self._token_codec.invalidate_preflight(token)

    def _purge_preflight_locked(self, now: datetime) -> None:
        for token, expires_at in tuple(self._preflight_expiry.items()):
            if expires_at <= now:
                del self._preflight_expiry[token]
                self._token_codec.invalidate_preflight(token)

    def _common_snapshot_gate(
        self, context: OperationContext, snapshot_id: str
    ) -> ReportError | None:
        error = self._common_gate(context)
        if error is None:
            error = _validate_identifier(snapshot_id, "snapshot_id")
        return self._with_operation(error, context.operation_id) if error else None

    @staticmethod
    def _with_operation(error: ReportError, operation_id: str) -> ReportError:
        if error.operation_id == operation_id:
            return error
        return replace(error, operation_id=operation_id)

    def _validate_discovered(
        self, discovered: DiscoveredScope, expected_scope: ReportScope
    ) -> ReportError | None:
        if discovered.scope != expected_scope or not _valid_text(
            discovered.source_revision, MAX_TEXT_BYTES, trim=True
        ):
            return _safe_internal_error("")
        counts = (
            discovered.log_count,
            discovered.total_bytes,
            discovered.child_count,
            discovered.collaborator_count,
            discovered.cached_file_count,
            discovered.changed_file_count,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts
        ):
            return _safe_internal_error("")
        for source in discovered.sources:
            if (
                not _valid_text(source.source_key, MAX_ID_BYTES, trim=True)
                or not isinstance(source.authorized_path, Path)
                or not source.authorized_path.is_absolute()
                or not _valid_text(source.source_revision, MAX_TEXT_BYTES, trim=True)
                or isinstance(source.byte_count, bool)
                or not isinstance(source.byte_count, int)
                or source.byte_count < 0
                or source.relationship not in {"root", "child", "collaborator"}
            ):
                return _safe_internal_error("")
        return None

    @staticmethod
    def _validate_agent_filters(filters: AgentFilters) -> ReportError | None:
        if (
            not isinstance(filters.query, str)
            or len(filters.query.encode("utf-8")) > MAX_TEXT_BYTES
        ):
            return _invalid("query must be bounded text.")
        for label, values in (
            ("agent_ids", filters.agent_ids),
            ("roles", filters.roles),
            ("states", filters.states),
        ):
            error = _validate_filter_values(values, label)
            if error is not None:
                return error
        return None

    @staticmethod
    def _validate_agent_sort(sort: AgentSort) -> ReportError | None:
        if (
            sort.key not in _AGENT_SORT_KEYS
            or sort.direction not in _SORT_DIRECTIONS
            or sort.tie_break_key != "agent_id"
            or sort.tie_break_direction != "ascending"
        ):
            return _invalid("The requested agent sort is not supported.")
        return None

    @staticmethod
    def _validate_turn_filters(filters: TurnFilters) -> ReportError | None:
        for label, values in (
            ("turn_ids", filters.turn_ids),
            ("agent_ids", filters.agent_ids),
            ("states", filters.states),
        ):
            error = _validate_filter_values(values, label)
            if error is not None:
                return error
        return _validate_optional_range(filters.from_time, filters.to_time)

    @staticmethod
    def _validate_turn_sort(sort: TurnSort) -> ReportError | None:
        if (
            sort.key not in _TURN_SORT_KEYS
            or sort.direction not in _SORT_DIRECTIONS
            or sort.tie_break_key != "turn_id"
            or sort.tie_break_direction != "ascending"
        ):
            return _invalid("The requested turn sort is not supported.")
        return None

    @staticmethod
    def _validate_event_sort(sort: EventSort) -> ReportError | None:
        if (
            sort.key not in _EVENT_SORT_KEYS
            or sort.direction not in _SORT_DIRECTIONS
            or sort.tie_break_key != "event_id"
            or sort.tie_break_direction != "ascending"
        ):
            return _invalid("The requested event sort is not supported.")
        return None

    @staticmethod
    def _validate_sequence_sort(sort: SequenceSort) -> ReportError | None:
        if (
            sort.key not in _SEQUENCE_SORT_KEYS
            or sort.direction not in _SORT_DIRECTIONS
            or sort.tie_break_key != "sequence_id"
            or sort.tie_break_direction != "ascending"
        ):
            return _invalid("The requested sequence sort is not supported.")
        return None

    @staticmethod
    def _validate_coordination_filters(
        filters: CoordinationFilters,
    ) -> ReportError | None:
        for label, value in (
            ("work_item_id", filters.work_item_id),
            ("delegated_root_id", filters.delegated_root_id),
            ("agent_id", filters.agent_id),
            ("operation", filters.operation),
        ):
            if value is not None:
                error = _validate_identifier(value, label)
                if error is not None:
                    return error
        if filters.evidence is not None and filters.evidence not in _EVIDENCE_KINDS:
            return _invalid("The coordination evidence selector is not supported.")
        return None

    @staticmethod
    def _validate_coordination_sort(sort: CoordinationSort) -> ReportError | None:
        if (
            sort.key not in _COORDINATION_SORT_KEYS
            or sort.direction not in _SORT_DIRECTIONS
            or sort.tie_break_key != "coordination_id"
            or sort.tie_break_direction != "ascending"
        ):
            return _invalid("The requested coordination sort is not supported.")
        return None

    @staticmethod
    def _validate_event_filters(filters: EventFilters) -> ReportError | None:
        for label, values in (
            ("event_ids", filters.event_ids),
            ("agent_ids", filters.agent_ids),
            ("turn_ids", filters.turn_ids),
            ("kinds", filters.kinds),
        ):
            error = _validate_filter_values(values, label)
            if error is not None:
                return error
        if any(not _EVENT_ID_PATTERN.fullmatch(value) for value in filters.event_ids):
            return _invalid("event_ids must use the supported snapshot event format.")
        return _validate_optional_range(filters.from_time, filters.to_time)

    def _run_query_call(
        self,
        context: OperationContext,
        operation: str,
        cancellation: CancellationToken,
        call: Callable[[], T],
    ) -> T:
        if cancellation.is_cancelled():
            raise _OperationFailure(_cancelled(context.operation_id))
        try:
            result = call()
        except _DEPENDENCY_FAILURE_CLASSES as failure:
            self._log_dependency_failure(
                context.operation_id, operation, "query", failure
            )
            raise _OperationFailure(
                _map_dependency_failure(context.operation_id, failure)
            ) from None
        except Exception as unexpected:
            self._log_unexpected(context.operation_id, operation, "query", unexpected)
            raise _OperationFailure(
                _safe_internal_error(context.operation_id)
            ) from None
        if cancellation.is_cancelled():
            raise _OperationFailure(_cancelled(context.operation_id))
        return result

    def _normalize_summary(
        self, result: SummaryResult, metadata: SnapshotMetadata
    ) -> SummaryResult | ReportError:
        title = (
            result.title
            if isinstance(result.title, str) and result.title
            else "Agent Report"
        )
        if (
            result.snapshot_id != metadata.snapshot_id
            or result.revision_id != metadata.revision_id
            or result.scope != metadata.scope
            or not _aware_datetime(result.observed_at)
            or result.mode not in {"live", "sealed"}
            or (
                result.time_range is not None
                and _validate_range(
                    result.time_range.from_time, result.time_range.to_time
                )
                is not None
            )
        ):
            return _safe_internal_error("")
        for label, value in (
            ("title", result.title),
            ("goal", result.goal),
            ("state", result.state),
        ):
            error = _validate_bounded_text(value, label)
            if error is not None:
                return error
        if len(result.metric_groups) > MAX_FILTER_VALUES:
            return _safe_internal_error("")
        groups: list[MetricGroup] = []
        metric_count = 0
        group_ids: set[str] = set()
        allowed_group_ids = {
            "overview",
            "model",
            "context",
            "inference",
            "runtime",
            "waits",
            "work_items",
            "claims",
            "provenance",
        }
        for group in result.metric_groups:
            if group.group_id not in allowed_group_ids or group.group_id in group_ids:
                return _safe_internal_error("")
            group_ids.add(group.group_id)
            error = _validate_bounded_text(group.label, "metric group label")
            if error is not None:
                return error
            metric_count += len(group.metrics)
            if metric_count > MAX_FILTER_VALUES:
                return _safe_internal_error("")
            metrics: list[MetricValue] = []
            metric_ids: set[str] = set()
            for metric in group.metrics:
                if (
                    metric.evidence not in _EVIDENCE_KINDS
                    or metric.metric_id in metric_ids
                ):
                    return _safe_internal_error("")
                metric_ids.add(metric.metric_id)
                for label, value in (
                    ("metric ID", metric.metric_id),
                    ("metric label", metric.label),
                    ("metric formatted value", metric.formatted_value),
                    ("metric unit", metric.unit),
                    ("metric provenance", metric.provenance),
                    ("metric description", metric.description),
                    (
                        "metric raw value",
                        metric.value if isinstance(metric.value, str) else None,
                    ),
                ):
                    error = _validate_bounded_text(value, label)
                    if error is not None:
                        return error
                metrics.append(metric)
            groups.append(replace(group, metrics=tuple(metrics)))
        warnings = _bounded_warnings(result.warnings)
        provenance = _bounded_strings(result.provenance, MAX_PROVENANCE_ITEMS)
        if warnings is None or provenance is None:
            return ReportError(
                code="REPORT_PRIVACY_FAILED",
                message="The report summary failed privacy validation.",
                recoverable=False,
            )
        if len(result.recent_activity) > MAX_RECENT_ACTIVITY:
            return _safe_internal_error("")
        activities: list[SignificantActivity] = []
        for item in result.recent_activity:
            if (
                not _EVENT_ID_PATTERN.fullmatch(item.event_id)
                or not _aware_datetime(item.occurred_at)
                or item.evidence not in _EVIDENCE_KINDS
            ):
                return _safe_internal_error("")
            error = _validate_bounded_text(item.label, "activity label")
            if error is not None:
                return error
            activities.append(
                replace(item, occurred_at=item.occurred_at.astimezone(timezone.utc))
            )
        return replace(
            result,
            title=title,
            observed_at=result.observed_at.astimezone(timezone.utc),
            time_range=(
                replace(
                    result.time_range,
                    from_time=result.time_range.from_time.astimezone(timezone.utc),
                    to_time=result.time_range.to_time.astimezone(timezone.utc),
                )
                if result.time_range is not None
                else None
            ),
            metric_groups=tuple(groups),
            provenance=provenance,
            warnings=warnings,
            recent_activity=tuple(activities),
        )

    def _validate_heatmap(
        self,
        result: HeatmapResult,
        request: HeatmapQueryRequest,
        actual_resolution: int,
        metadata: SnapshotMetadata,
    ) -> ReportError | None:
        if (
            result.snapshot_id != metadata.snapshot_id
            or result.revision_id != metadata.revision_id
            or result.measure != request.measure
            or result.group_by != request.group_by
            or result.requested_resolution_minutes
            != request.requested_resolution_minutes
            or result.actual_resolution_minutes != actual_resolution
            or result.maximum_rows != request.maximum_rows
            or isinstance(result.omitted_row_count, bool)
            or not isinstance(result.omitted_row_count, int)
            or result.omitted_row_count < 0
            or result.row_order != "activity_descending_id_ascending"
            or isinstance(result.total_cell_count, bool)
            or not isinstance(result.total_cell_count, int)
            or result.total_cell_count < 0
            or not _aware_datetime(result.from_time)
            or not _aware_datetime(result.to_time)
            or result.from_time.astimezone(timezone.utc)
            != request.from_time.astimezone(timezone.utc)
            or result.to_time.astimezone(timezone.utc)
            != request.to_time.astimezone(timezone.utc)
            or len(result.rows) > request.maximum_rows
            or result.total_cell_count > self._config.max_heatmap_cells
            or result.total_cell_count != sum(len(row.cells) for row in result.rows)
        ):
            return _safe_internal_error("")
        seen_rows: set[str] = set()
        for row in result.rows:
            if (
                _validate_identifier(row.row_id, "row_id") is not None
                or row.row_id in seen_rows
                or not _valid_row_texts(row.label)
                or isinstance(row.scale.minimum, bool)
                or not isinstance(row.scale.minimum, (int, float))
                or isinstance(row.scale.maximum, bool)
                or not isinstance(row.scale.maximum, (int, float))
                or row.scale.minimum > row.scale.maximum
                or row.scale.color_semantic
                not in {"sequential_nonnegative", "diverging_signed"}
                or row.scale.basis
                not in {"visible_row_maximum", "context_window_capacity"}
            ):
                return _safe_internal_error("")
            seen_rows.add(row.row_id)
            previous_end: datetime | None = None
            for cell in row.cells:
                if (
                    not _aware_datetime(cell.start_time)
                    or not _aware_datetime(cell.end_time)
                    or cell.start_time >= cell.end_time
                    or (previous_end is not None and cell.start_time < previous_end)
                    or isinstance(cell.count, bool)
                    or not isinstance(cell.count, int)
                    or cell.count < 0
                    or cell.evidence not in _EVIDENCE_KINDS
                    or not _valid_row_texts(cell.primary_label)
                    or (
                        cell.secondary_label is not None
                        and not _valid_row_texts(cell.secondary_label)
                    )
                ):
                    return _safe_internal_error("")
                previous_end = cell.end_time
        if _bounded_strings(result.provenance, MAX_PROVENANCE_ITEMS) is None:
            return ReportError(
                code="REPORT_PRIVACY_FAILED",
                message="The heatmap provenance failed privacy validation.",
                recoverable=False,
            )
        return None

    def _normalize_event_detail(
        self, detail: EventDetail, snapshot_id: str, event_id: str
    ) -> EventDetail | ReportError:
        with self._state_changed:
            state = self._snapshots.get(snapshot_id)
        expected_revision = state.metadata.revision_id if state is not None else None
        if (
            detail.snapshot_id != snapshot_id
            or detail.revision_id != expected_revision
            or detail.event_id != event_id
            or not _aware_datetime(detail.occurred_at)
            or detail.evidence not in _EVIDENCE_KINDS
            or (
                detail.source_key is not None
                and _validate_identifier(detail.source_key, "source_key") is not None
            )
        ):
            return _safe_internal_error("")
        for label, value in (
            ("event kind", detail.kind),
            ("event title", detail.title),
            ("event summary", detail.summary),
        ):
            error = _validate_bounded_text(value, label)
            if error is not None:
                return error
        provenance = _bounded_strings(detail.provenance, MAX_PROVENANCE_ITEMS)
        if provenance is None:
            return ReportError(
                code="REPORT_PRIVACY_FAILED",
                message="The event provenance failed privacy validation.",
                recoverable=False,
            )
        if len(detail.disclosures) > MAX_PROVENANCE_ITEMS:
            return _safe_internal_error("")
        disclosures: list[Disclosure] = []
        for disclosure in detail.disclosures:
            if (
                type(disclosure.redacted) is not bool
                or _validate_bounded_text(disclosure.label, "disclosure label")
                is not None
                or not isinstance(disclosure.content, str)
                or _contains_absolute_path(disclosure.content)
            ):
                return ReportError(
                    code="REPORT_PRIVACY_FAILED",
                    message="The event detail failed privacy validation.",
                    recoverable=False,
                )
            if len(disclosure.content.encode("utf-8")) > MAX_DETAIL_FIELD_BYTES:
                disclosures.append(
                    replace(
                        disclosure,
                        content="Content omitted because it exceeded the detail limit.",
                        redacted=True,
                    )
                )
            else:
                disclosures.append(disclosure)
        return replace(
            detail,
            occurred_at=detail.occurred_at.astimezone(timezone.utc),
            provenance=provenance,
            disclosures=tuple(disclosures),
        )

    @staticmethod
    def _validate_export_result(
        result: ExportResult,
        request: ResolvedExportRequest,
        operation_id: str,
        metadata: SnapshotMetadata,
    ) -> ReportError | None:
        if (
            result.operation_id != operation_id
            or result.snapshot_id != request.snapshot_id
            or result.revision_id != metadata.revision_id
            or result.mode != request.mode
            or result.published_target != request.target
            or not result.published_target.is_absolute()
            or (
                result.manifest_sha256 is not None
                and not _LOWER_HEX_DIGEST.fullmatch(result.manifest_sha256)
            )
            or isinstance(result.file_count, bool)
            or not isinstance(result.file_count, int)
            or result.file_count < 0
            or isinstance(result.total_byte_count, bool)
            or not isinstance(result.total_byte_count, int)
            or result.total_byte_count < 0
        ):
            return _safe_internal_error("")
        if (
            _bounded_warnings(result.warnings) is None
            or _bounded_export_omissions(result.omissions) is None
        ):
            return _safe_internal_error("")
        return None

    @staticmethod
    def _map_repository_publication_failure(
        operation_id: str, failure: RepositoryFailure
    ) -> ReportError:
        if failure.kind in {"schema_newer", "binding_conflict"}:
            if not _valid_text(failure.safe_message, MAX_TEXT_BYTES, trim=False):
                return _safe_internal_error(operation_id)
            return ReportError(
                code="REPORT_SCOPE_CONFLICT",
                message=failure.safe_message,
                recoverable=failure.recoverable,
                operation_id=operation_id,
                current_source_revision=failure.current_source_revision,
                preflight_required=True,
            )
        return _map_dependency_failure(operation_id, failure)

    def _release_handle(
        self, handle: SnapshotReadHandle, operation_id: str, operation: str
    ) -> ReportError | None:
        try:
            self._dependencies.repository.release_read(handle)
        except _DEPENDENCY_FAILURE_CLASSES as failure:
            self._log_dependency_failure(
                operation_id, operation, "repository", failure, cleanup=True
            )
            return _safe_internal_error(operation_id)
        except Exception as unexpected:
            self._log_unexpected(
                operation_id, operation, "repository", unexpected, cleanup=True
            )
            return _safe_internal_error(operation_id)
        return None

    def _release_handle_cleanup(
        self, handle: SnapshotReadHandle, operation_id: str, operation: str
    ) -> None:
        self._release_handle(handle, operation_id, operation)

    def _discard_stage(self, staged: StagedExport, operation_id: str) -> None:
        try:
            self._dependencies.publisher.discard(staged)
        except _DEPENDENCY_FAILURE_CLASSES as failure:
            self._log_dependency_failure(
                operation_id,
                "export_snapshot",
                "publisher",
                failure,
                cleanup=True,
            )
        except Exception as unexpected:
            self._log_unexpected(
                operation_id,
                "export_snapshot",
                "publisher",
                unexpected,
                cleanup=True,
            )

    def _log_dependency_failure(
        self,
        operation_id: str,
        operation: str,
        dependency: str,
        failure: BaseException,
        *,
        cleanup: bool = False,
    ) -> None:
        fields_value: dict[str, str | int | bool | None] = {
            "operation_id": operation_id,
            "operation": operation,
            "dependency": dependency,
            "kind": cast(str, getattr(failure, "kind", "unknown")),
        }
        if cleanup:
            fields_value["cleanup"] = True
        self._safe_log("error", "report_dependency_failed", fields_value)

    def _log_unexpected(
        self,
        operation_id: str,
        operation: str,
        dependency: str,
        failure: BaseException,
        *,
        cleanup: bool = False,
    ) -> None:
        fields_value: dict[str, str | int | bool | None] = {
            "operation_id": operation_id,
            "operation": operation,
            "dependency": dependency,
            "exception_class": type(failure).__name__,
            "detail": str(failure)[:2048],
        }
        if cleanup:
            fields_value["cleanup"] = True
        self._safe_log("error", "report_unexpected_failure", fields_value)

    def _safe_log(
        self,
        level: Literal["info", "error"],
        event: str,
        values: Mapping[str, str | int | bool | None],
    ) -> None:
        try:
            getattr(self._dependencies.logger, level)(event, values)
        except Exception:
            # Logging is diagnostic only and must never replace service authority.
            return


class _OperationFailure(RuntimeError):
    def __init__(self, error: ReportError) -> None:
        super().__init__(error.code)
        self.error = error


def _require_snapshot(
    self: ApplicationService, snapshot_id: str
) -> ServiceResult[_SnapshotState]:
    with self._state_changed:
        state = self._snapshots.get(snapshot_id)
        if state is None or state.status == "closed":
            return _failure(_snapshot_not_found())
        return _success(state)


def _acquire_read(
    self: ApplicationService, snapshot_id: str
) -> ServiceResult[_ReadLease]:
    with self._state_changed:
        if self._closed:
            return _failure(_snapshot_conflict())
        state = self._snapshots.get(snapshot_id)
        if state is None or state.status == "closed":
            return _failure(_snapshot_not_found())
        if state.status != "ready" or state.mutation_active:
            return _failure(_snapshot_conflict())
        state.active_readers += 1
        return _success(_ReadLease(self, snapshot_id, state))


def _acquire_mutation(
    self: ApplicationService,
    snapshot_id: str,
    status: Literal["refreshing", "exporting", "closing"],
    *,
    require_no_readers: bool,
) -> ServiceResult[_MutationLease]:
    with self._state_changed:
        if self._closed:
            return _failure(_snapshot_conflict())
        state = self._snapshots.get(snapshot_id)
        if state is None or state.status == "closed":
            return _failure(_snapshot_not_found())
        if (
            state.status != "ready"
            or state.mutation_active
            or (require_no_readers and state.active_readers > 0)
        ):
            return _failure(_snapshot_conflict())
        state.mutation_active = True
        state.status = status
        return _success(_MutationLease(self, snapshot_id, state, status))


def _query_page(
    self: ApplicationService,
    context: OperationContext,
    request: (
        ListAgentsRequest
        | ListTurnsRequest
        | ListEventsRequest
        | CoordinationQueryRequest
    ),
    operation: str,
    filters: F,
    sort: S,
    query: Callable[[SnapshotReadHandle, str | None], QuerySlice[T]],
) -> ServiceResult[PageResult[T, F, S]]:
    digest = _filters_digest(filters)
    sort_binding = _filters_digest(sort)
    lease_result = _acquire_read(self, request.snapshot_id)
    if not lease_result.ok:
        return cast(ServiceResult[PageResult[T, F, S]], lease_result)
    lease = cast(_ReadLease, lease_result.value)
    with lease as state:
        after: str | None = None
        if request.cursor is not None:
            if not _valid_text(request.cursor, MAX_ID_BYTES, trim=True):
                return _failure(_cursor_conflict(context.operation_id))
            try:
                with self._state_changed:
                    claims = self._token_codec.decode_cursor(request.cursor)
            except _TokenDecodeError:
                return _failure(_cursor_conflict(context.operation_id))
            if (
                claims
                != _CursorClaims(
                    snapshot_id=request.snapshot_id,
                    revision_id=state.revision_id,
                    operation=operation,
                    filters_digest=digest,
                    sort=sort_binding,
                    page_size=request.page_size,
                    position=claims.position,
                )
                or _validate_identifier(claims.position, "cursor position") is not None
            ):
                return _failure(_cursor_conflict(context.operation_id))
            after = claims.position
        try:
            query_slice = query(state.read_handle, after)
        except _OperationFailure as failure:
            return _failure(failure.error)
        except Exception:
            return _failure(_safe_internal_error(context.operation_id))
        if (
            not isinstance(query_slice, QuerySlice)
            or len(query_slice.items) > request.page_size
            or (
                query_slice.next_position is not None
                and _validate_identifier(query_slice.next_position, "cursor position")
                is not None
            )
        ):
            return _failure(_safe_internal_error(context.operation_id))
        normalized = _normalize_page_items(operation, query_slice.items, sort)
        if isinstance(normalized, ReportError):
            return _failure(self._with_operation(normalized, context.operation_id))
        next_cursor = None
        if query_slice.next_position is not None:
            with self._state_changed:
                next_cursor = self._token_codec.encode_cursor(
                    _CursorClaims(
                        snapshot_id=request.snapshot_id,
                        revision_id=state.revision_id,
                        operation=operation,
                        filters_digest=digest,
                        sort=sort_binding,
                        page_size=request.page_size,
                        position=query_slice.next_position,
                    )
                )
        return _success(
            PageResult(
                snapshot_id=request.snapshot_id,
                revision_id=state.metadata.revision_id,
                operation=operation,
                items=cast(tuple[T, ...], normalized),
                applied_filters=filters,
                applied_sort=sort,
                page_size=request.page_size,
                next_cursor=next_cursor,
            )
        )


def _query_sequence_result(
    self: ApplicationService,
    context: OperationContext,
    request: SequenceQueryRequest,
    operation: str,
    query: Callable[[SnapshotReadHandle, str | None], SequenceResult],
) -> ServiceResult[SequenceResult]:
    filters_digest = _filters_digest(request.filters)
    sort_binding = _filters_digest(request.sort)
    lease_result = _acquire_read(self, request.snapshot_id)
    if not lease_result.ok:
        return cast(ServiceResult[SequenceResult], lease_result)
    lease = cast(_ReadLease, lease_result.value)
    with lease as state:
        after: str | None = None
        if request.cursor is not None:
            if not _valid_text(request.cursor, MAX_ID_BYTES, trim=True):
                return _failure(_cursor_conflict(context.operation_id))
            try:
                with self._state_changed:
                    claims = self._token_codec.decode_cursor(request.cursor)
            except _TokenDecodeError:
                return _failure(_cursor_conflict(context.operation_id))
            if (
                claims.snapshot_id != request.snapshot_id
                or claims.revision_id != state.revision_id
                or claims.operation != operation
                or claims.filters_digest != filters_digest
                or claims.sort != sort_binding
                or claims.page_size != request.page_size
                or _validate_identifier(claims.position, "cursor position") is not None
            ):
                return _failure(_cursor_conflict(context.operation_id))
            after = claims.position
        try:
            result = query(state.read_handle, after)
        except _OperationFailure as failure:
            return _failure(failure.error)
        except Exception:
            return _failure(_safe_internal_error(context.operation_id))
        if not isinstance(result, SequenceResult):
            return _failure(_safe_internal_error(context.operation_id))
        raw_page = result.page
        if (
            raw_page.snapshot_id != request.snapshot_id
            or raw_page.revision_id != state.metadata.revision_id
            or raw_page.operation != operation
            or raw_page.applied_filters != request.filters
            or raw_page.applied_sort != request.sort
            or raw_page.page_size != request.page_size
            or len(raw_page.items) > request.page_size
            or (
                raw_page.next_cursor is not None
                and _validate_identifier(raw_page.next_cursor, "cursor position")
                is not None
            )
        ):
            return _failure(_safe_internal_error(context.operation_id))
        normalized = _normalize_page_items(operation, raw_page.items, request.sort)
        if isinstance(normalized, ReportError):
            return _failure(self._with_operation(normalized, context.operation_id))
        normalized_rows = cast(tuple[SequenceRow, ...], normalized)
        groups = _normalize_sequence_groups(result.groups, normalized_rows)
        if isinstance(groups, ReportError):
            return _failure(self._with_operation(groups, context.operation_id))
        if request.filters.grouping == "none" and (
            groups or any(row.group_id is not None for row in normalized_rows)
        ):
            return _failure(_safe_internal_error(context.operation_id))
        next_cursor = None
        if raw_page.next_cursor is not None:
            with self._state_changed:
                next_cursor = self._token_codec.encode_cursor(
                    _CursorClaims(
                        snapshot_id=request.snapshot_id,
                        revision_id=state.revision_id,
                        operation=operation,
                        filters_digest=filters_digest,
                        sort=sort_binding,
                        page_size=request.page_size,
                        position=raw_page.next_cursor,
                    )
                )
        return _success(
            SequenceResult(
                page=PageResult(
                    snapshot_id=request.snapshot_id,
                    revision_id=state.metadata.revision_id,
                    operation=operation,
                    items=normalized_rows,
                    applied_filters=request.filters,
                    applied_sort=request.sort,
                    page_size=request.page_size,
                    next_cursor=next_cursor,
                ),
                groups=groups,
            )
        )


def _normalize_sequence_groups(
    values: Sequence[SequenceGroup], rows: Sequence[SequenceRow]
) -> tuple[SequenceGroup, ...] | ReportError:
    groups: list[SequenceGroup] = []
    by_id: dict[str, SequenceGroup] = {}
    for group in values:
        if (
            _validate_identifier(group.group_id, "group_id") is not None
            or group.group_id in by_id
            or (
                group.parent_group_id is not None
                and _validate_identifier(group.parent_group_id, "parent_group_id")
                is not None
            )
            or isinstance(group.depth, bool)
            or not isinstance(group.depth, int)
            or group.depth < 0
            or not _valid_row_texts(group.label)
            or type(group.collapsible) is not bool
        ):
            return _safe_internal_error("")
        if group.parent_group_id is None:
            if group.depth != 0:
                return _safe_internal_error("")
        else:
            parent = by_id.get(group.parent_group_id)
            if parent is None or group.depth != parent.depth + 1:
                return _safe_internal_error("")
        by_id[group.group_id] = group
        groups.append(group)
    if any(row.group_id is not None and row.group_id not in by_id for row in rows):
        return _safe_internal_error("")
    return tuple(groups)


def _normalize_page_items(
    operation: str, items: Sequence[object], sort: object
) -> tuple[object, ...] | ReportError:
    del sort  # QueryPort owns row ordering after the service validates the sort DTO.
    normalized: list[object] = []
    for item in items:
        if operation == "list_agents" and isinstance(item, AgentRow):
            if (
                _validate_identifier(item.agent_id, "agent_id") is not None
                or (
                    item.parent_agent_id is not None
                    and _validate_identifier(item.parent_agent_id, "parent_agent_id")
                    is not None
                )
                or (
                    item.nickname is not None
                    and _validate_bounded_text(item.nickname, "agent nickname")
                    is not None
                )
                or (
                    item.role is not None
                    and _validate_bounded_text(item.role, "agent role") is not None
                )
                or not _valid_row_texts(item.state)
                or not _optional_aware(item.started_at)
                or not _optional_aware(item.ended_at)
                or not _optional_aware(item.last_activity_at)
                or not _valid_nonnegative_integer(item.turn_count)
                or not _valid_nonnegative_integer(item.event_count)
                or item.evidence not in _EVIDENCE_KINDS
            ):
                return _safe_internal_error("")
            normalized_agent = replace(
                item,
                started_at=_utc_or_none(item.started_at),
                ended_at=_utc_or_none(item.ended_at),
                last_activity_at=_utc_or_none(item.last_activity_at),
            )
            normalized.append(normalized_agent)
        elif operation == "list_turns" and isinstance(item, TurnRow):
            if (
                _validate_identifier(item.turn_id, "turn_id") is not None
                or _validate_identifier(item.agent_id, "agent_id") is not None
                or not _valid_row_texts(item.state)
                or (
                    item.summary is not None
                    and _validate_bounded_text(item.summary, "turn summary") is not None
                )
                or not _aware_datetime(item.started_at)
                or not _optional_aware(item.ended_at)
                or not _valid_nonnegative_integer(item.event_count)
                or item.evidence not in _EVIDENCE_KINDS
            ):
                return _safe_internal_error("")
            normalized_turn = replace(
                item,
                started_at=item.started_at.astimezone(timezone.utc),
                ended_at=_utc_or_none(item.ended_at),
            )
            normalized.append(normalized_turn)
        elif operation == "list_events" and isinstance(item, EventRow):
            if (
                not _EVENT_ID_PATTERN.fullmatch(item.event_id)
                or (
                    item.turn_id is not None
                    and _validate_identifier(item.turn_id, "turn_id") is not None
                )
                or (
                    item.agent_id is not None
                    and _validate_identifier(item.agent_id, "agent_id") is not None
                )
                or not _aware_datetime(item.occurred_at)
                or not _valid_row_texts(item.kind, item.summary)
                or item.evidence not in _EVIDENCE_KINDS
                or (
                    item.source_key is not None
                    and _validate_identifier(item.source_key, "source_key") is not None
                )
                or type(item.has_detail) is not bool
            ):
                return _safe_internal_error("")
            normalized_event = replace(
                item, occurred_at=item.occurred_at.astimezone(timezone.utc)
            )
            normalized.append(normalized_event)
        elif operation == "query_sequence" and isinstance(item, SequenceRow):
            if (
                _validate_identifier(item.sequence_id, "sequence_id") is not None
                or (
                    item.group_id is not None
                    and _validate_identifier(item.group_id, "group_id") is not None
                )
                or (
                    item.from_agent_id is not None
                    and _validate_identifier(item.from_agent_id, "from_agent_id")
                    is not None
                )
                or (
                    item.from_agent_label is not None
                    and _validate_bounded_text(
                        item.from_agent_label, "from agent label"
                    )
                    is not None
                )
                or (
                    item.to_agent_id is not None
                    and _validate_identifier(item.to_agent_id, "to_agent_id")
                    is not None
                )
                or (
                    item.to_agent_label is not None
                    and _validate_bounded_text(item.to_agent_label, "to agent label")
                    is not None
                )
                or not _aware_datetime(item.occurred_at)
                or not _valid_row_texts(item.kind, item.summary)
                or (
                    item.event_id is not None
                    and not _EVENT_ID_PATTERN.fullmatch(item.event_id)
                )
                or isinstance(item.repeat_count, bool)
                or not isinstance(item.repeat_count, int)
                or item.repeat_count < 1
                or type(item.reasoning_available) is not bool
                or item.evidence not in _EVIDENCE_KINDS
            ):
                return _safe_internal_error("")
            normalized_sequence = replace(
                item, occurred_at=item.occurred_at.astimezone(timezone.utc)
            )
            normalized.append(normalized_sequence)
        elif operation == "query_coordination" and isinstance(item, CoordinationRow):
            if (
                _validate_identifier(item.coordination_id, "coordination_id")
                is not None
                or (
                    item.work_item_id is not None
                    and _validate_identifier(item.work_item_id, "work_item_id")
                    is not None
                )
                or (
                    item.delegated_root_id is not None
                    and _validate_identifier(
                        item.delegated_root_id, "delegated_root_id"
                    )
                    is not None
                )
                or (
                    item.agent_id is not None
                    and _validate_identifier(item.agent_id, "agent_id") is not None
                )
                or _validate_filter_values(item.related_agent_ids, "related_agent_ids")
                is not None
                or not _aware_datetime(item.occurred_at)
                or not _valid_row_texts(item.operation, item.summary)
                or item.evidence not in _EVIDENCE_KINDS
                or (
                    item.event_id is not None
                    and not _EVENT_ID_PATTERN.fullmatch(item.event_id)
                )
            ):
                return _safe_internal_error("")
            normalized_coordination = replace(
                item,
                occurred_at=item.occurred_at.astimezone(timezone.utc),
                related_agent_ids=tuple(item.related_agent_ids),
                evidence=(
                    "inferred"
                    if "decision" in item.operation.casefold()
                    else item.evidence
                ),
            )
            normalized.append(normalized_coordination)
        else:
            return _safe_internal_error("")
    return tuple(normalized)


def _valid_row_texts(*values: str) -> bool:
    return all(
        _valid_text(value, MAX_TEXT_BYTES, trim=False)
        and not _contains_absolute_path(value)
        for value in values
    )


def _optional_aware(value: datetime | None) -> bool:
    return value is None or _aware_datetime(value)


def _valid_nonnegative_integer(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _utc_or_none(value: datetime | None) -> datetime | None:
    if value is None or not _aware_datetime(value):
        return value
    return value.astimezone(timezone.utc)


def _immutable_event_filters(filters: EventFilters) -> EventFilters:
    return replace(
        filters,
        event_ids=tuple(filters.event_ids),
        agent_ids=tuple(filters.agent_ids),
        turn_ids=tuple(filters.turn_ids),
        kinds=tuple(filters.kinds),
        from_time=_utc_or_none(filters.from_time),
        to_time=_utc_or_none(filters.to_time),
    )


def _actual_resolution_minutes(
    from_time: datetime,
    to_time: datetime,
    requested_resolution_minutes: int,
    maximum_cells: int,
    returned_rows: int,
) -> int:
    if returned_rows <= 0:
        return requested_resolution_minutes
    duration_seconds = (
        to_time.astimezone(timezone.utc) - from_time.astimezone(timezone.utc)
    ).total_seconds()
    required_total_minutes = math.ceil(
        duration_seconds * returned_rows / (maximum_cells * 60)
    )
    return max(requested_resolution_minutes, required_total_minutes)


def resolve_automation_export_mode(
    surface: AutomationSurface, requested_mode: ExportMode | None
) -> ServiceResult[ExportMode]:
    """Resolve omitted Tauri, CLI, and MCP modes to directory output."""

    if surface not in _SURFACES:
        return _failure(_invalid("The automation surface is not supported."))
    if requested_mode is None:
        return _success("directory")
    if requested_mode not in {"directory", "summary"}:
        return _failure(_invalid("The Codex export mode is not supported."))
    return _success(requested_mode)


def create_application_service(
    config: ApplicationServiceConfig,
    dependencies: ApplicationServiceDependencies,
) -> ApplicationService:
    """Construct one independent process-local application service instance."""

    _validate_config(config)
    return ApplicationService(config, dependencies)


def _validate_config(config: ApplicationServiceConfig) -> None:
    if not config.authorized_source_roots:
        raise ValueError("at least one authorized source root is required")
    for root in config.authorized_source_roots:
        if not isinstance(root, Path) or not root.is_absolute() or not root.is_dir():
            raise ValueError(
                "each authorized source root must be an absolute directory"
            )
    if not _valid_text(config.parser_version, 128, trim=True):
        raise ValueError("parser_version must be a non-empty bounded value")
    if not _valid_text(config.pricing_version, 128, trim=True):
        raise ValueError("pricing_version must be a non-empty bounded value")
    if not _LOWER_HEX_DIGEST.fullmatch(config.pricing_digest):
        raise ValueError("pricing_digest must be a lowercase SHA-256 digest")
    if not _LOWER_HEX_DIGEST.fullmatch(config.formatter_digest):
        raise ValueError("formatter_digest must be a lowercase SHA-256 digest")
    if not _valid_text(config.formatter_version, 128, trim=True):
        raise ValueError("formatter_version must be a non-empty bounded value")
    if (
        isinstance(config.max_page_size, bool)
        or not isinstance(config.max_page_size, int)
        or not 1 <= config.max_page_size <= MAX_PAGE_SIZE
    ):
        raise ValueError("max_page_size must be from 1 through 500")
    if (
        isinstance(config.default_page_size, bool)
        or not isinstance(config.default_page_size, int)
        or not 1 <= config.default_page_size <= config.max_page_size
    ):
        raise ValueError("default_page_size must be within the configured page limit")
    if config.max_heatmap_cells != MAX_HEATMAP_CELLS:
        raise ValueError("max_heatmap_cells must equal 2000 for protocol version 1")
