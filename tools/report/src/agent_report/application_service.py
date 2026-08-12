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
MAX_TIME_BUCKETS: Final[int] = 2_000
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
_SURFACES: Final[frozenset[str]] = frozenset({"tauri", "cli", "mcp"})
_EVENT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"evt_[0-9a-f]{24}\Z")
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


@dataclass(frozen=True, slots=True)
class SnapshotRequest:
    """Select one open process-local snapshot."""

    snapshot_id: str


@dataclass(frozen=True, slots=True)
class AgentFilters:
    """Restrict agent rows by stable identifiers, roles, and states."""

    agent_ids: Sequence[str] = ()
    roles: Sequence[str] = ()
    states: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class TurnFilters:
    """Restrict turn rows by identifiers, states, agents, and an optional range."""

    turn_ids: Sequence[str] = ()
    agent_ids: Sequence[str] = ()
    states: Sequence[str] = ()
    from_time: datetime | None = None
    to_time: datetime | None = None


@dataclass(frozen=True, slots=True)
class EventFilters:
    """Restrict event rows by identifiers, kinds, agents, turns, and time."""

    event_ids: Sequence[str] = ()
    agent_ids: Sequence[str] = ()
    turn_ids: Sequence[str] = ()
    kinds: Sequence[str] = ()
    from_time: datetime | None = None
    to_time: datetime | None = None


@dataclass(frozen=True, slots=True)
class ListAgentsRequest:
    """Request one stable page of agents."""

    snapshot_id: str
    filters: AgentFilters = AgentFilters()
    cursor: str | None = None
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class ListTurnsRequest:
    """Request one stable page of turns."""

    snapshot_id: str
    filters: TurnFilters = TurnFilters()
    cursor: str | None = None
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class ListEventsRequest:
    """Request one stable page of events."""

    snapshot_id: str
    filters: EventFilters = EventFilters()
    cursor: str | None = None
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class TimeRangeQueryRequest:
    """Request one bounded time series for a supported measure."""

    snapshot_id: str
    from_time: datetime
    to_time: datetime
    measure: TimeMeasure
    requested_resolution_minutes: int


@dataclass(frozen=True, slots=True)
class SequenceQueryRequest:
    """Request one stable page of delegation and communication sequence rows."""

    snapshot_id: str
    focus_agent_id: str | None = None
    filters: EventFilters = EventFilters()
    grouping: SequenceGrouping = "none"
    cursor: str | None = None
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class CoordinationQueryRequest:
    """Request one stable page of evidence-derived coordination rows."""

    snapshot_id: str
    work_item_ids: Sequence[str] = ()
    agent_ids: Sequence[str] = ()
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
    root_thread_id: str
    include_children: bool
    include_collaborators: bool
    source_revision: str
    parser_version: str
    pricing_digest: str
    formatter_digest: str
    observation_time: datetime
    mode: SnapshotMode
    warnings: Sequence[WarningRecord]


@dataclass(frozen=True, slots=True)
class MetricValue:
    """Expose one metric with its unit, evidence label, and provenance."""

    name: str
    value: int | float | str | None
    unit: str | None
    evidence: EvidenceKind
    provenance: str


@dataclass(frozen=True, slots=True)
class ActivityItem:
    """Describe one recent significant report event."""

    event_id: str
    occurred_at: datetime
    kind: str
    summary: str
    evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class SummaryResult:
    """Return bounded snapshot state, metrics, provenance, and recent activity."""

    snapshot_id: str
    goal: str | None
    state: str
    scope: ReportScope
    metrics: Sequence[MetricValue]
    provenance: Sequence[str]
    warnings: Sequence[WarningRecord]
    recent_activity: Sequence[ActivityItem]


@dataclass(frozen=True, slots=True)
class AgentRow:
    """Represent one agent in canonical list order."""

    agent_id: str
    parent_agent_id: str | None
    role: str
    state: str
    started_at: datetime | None
    ended_at: datetime | None
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
    evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class EventRow:
    """Represent one bounded event in canonical list order."""

    event_id: str
    turn_id: str | None
    agent_id: str | None
    occurred_at: datetime
    kind: str
    summary: str
    evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class TimeBucket:
    """Represent one bounded interval and measured or derived value."""

    from_time: datetime
    to_time: datetime
    value: int | float | None
    evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class SequenceRow:
    """Represent one delegation or communication sequence item."""

    sequence_id: str
    occurred_at: datetime
    source_agent_id: str | None
    target_agent_id: str | None
    kind: str
    summary: str
    repeated_count: int
    evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class CoordinationRow:
    """Represent one evidence-labeled coordination action."""

    coordination_id: str
    occurred_at: datetime
    work_item_id: str | None
    agent_ids: Sequence[str]
    action: str
    summary: str
    evidence: EvidenceKind


@dataclass(frozen=True, slots=True)
class EventDetail:
    """Return bounded, redacted detail for one snapshot event."""

    snapshot_id: str
    event_id: str
    occurred_at: datetime
    kind: str
    summary: str
    bounded_arguments: str | None
    bounded_result: str | None
    evidence: EvidenceKind
    provenance: Sequence[str]
    redactions: Sequence[str]


@dataclass(frozen=True, slots=True)
class PageResult(Generic[T]):
    """Return one immutable stable page and its opaque continuation cursor."""

    snapshot_id: str
    operation: str
    items: Sequence[T]
    applied_filters_digest: str
    applied_sort: str
    page_size: int
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class TimeSeriesResult:
    """Return a bounded time series with requested and actual resolution."""

    snapshot_id: str
    measure: TimeMeasure
    requested_resolution_minutes: int
    actual_resolution_minutes: int
    from_time: datetime
    to_time: datetime
    buckets: Sequence[TimeBucket]
    provenance: Sequence[str]


@dataclass(frozen=True, slots=True)
class RefreshSnapshotResult:
    """Return whether refresh published a changed coherent binding."""

    changed: bool
    snapshot: SnapshotMetadata


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Describe a completed atomic export publication."""

    mode: ExportMode
    published_target: Path
    manifest_id: str | None
    warnings: Sequence[WarningRecord]
    omissions: Sequence[str]


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
        after: str | None,
        limit: int,
        cancellation: CancellationToken,
    ) -> QuerySlice[EventRow]:
        """Return one canonical event slice."""

        ...

    def query_time_range(
        self,
        handle: SnapshotReadHandle,
        request: TimeRangeQueryRequest,
        actual_resolution_minutes: int,
        cancellation: CancellationToken,
    ) -> TimeSeriesResult:
        """Return one bounded time-series result."""

        ...

    def query_sequence(
        self,
        handle: SnapshotReadHandle,
        request: SequenceQueryRequest,
        after: str | None,
        cancellation: CancellationToken,
    ) -> QuerySlice[SequenceRow]:
        """Return one bounded sequence slice."""

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
    pricing_digest: str
    formatter_digest: str
    default_page_size: int = DEFAULT_PAGE_SIZE
    max_page_size: int = MAX_PAGE_SIZE
    max_time_buckets: int = MAX_TIME_BUCKETS


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
    pricing_digest: str
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
    if not _valid_text(context.operation_id, MAX_ID_BYTES, trim=True):
        return _invalid("operation_id must be a non-empty bounded identifier.")
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
                pricing_digest=self._config.pricing_digest,
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
            or claims.parser_version != self._config.parser_version
            or claims.pricing_digest != self._config.pricing_digest
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
            if discovered.source_revision != claims.source_revision:
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
                root_thread_id=request.scope.root_thread_id,
                include_children=request.scope.include_children,
                include_collaborators=request.scope.include_collaborators,
                source_revision=published.source_revision,
                parser_version=self._config.parser_version,
                pricing_digest=self._config.pricing_digest,
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
    ) -> ServiceResult[PageResult[AgentRow]]:
        """Return one stable agent page bound to all filters and page options."""

        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None:
            error = self._validate_agent_filters(request.filters)
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
                    after,
                    request.page_size,
                    cancellation,
                ),
            )

        return _query_page(
            self,
            request,
            "list_agents",
            "agent.started_at, agent.agent_id",
            query,
        )

    def list_turns(
        self,
        context: OperationContext,
        request: ListTurnsRequest,
        *,
        cancellation: CancellationToken,
    ) -> ServiceResult[PageResult[TurnRow]]:
        """Return one stable turn page bound to all filters and page options."""

        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None:
            error = self._validate_turn_filters(request.filters)
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
                    after,
                    request.page_size,
                    cancellation,
                ),
            )

        return _query_page(
            self,
            request,
            "list_turns",
            "turn.started_at, turn.turn_id",
            query,
        )

    def list_events(
        self,
        context: OperationContext,
        request: ListEventsRequest,
        *,
        cancellation: CancellationToken,
    ) -> ServiceResult[PageResult[EventRow]]:
        """Return one stable bounded event page bound to all selectors."""

        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None:
            error = self._validate_event_filters(request.filters)
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
                    after,
                    request.page_size,
                    cancellation,
                ),
            )

        return _query_page(
            self,
            request,
            "list_events",
            "event.occurred_at, event.event_id",
            query,
        )

    def query_time_range(
        self,
        context: OperationContext,
        request: TimeRangeQueryRequest,
        *,
        cancellation: CancellationToken,
    ) -> ServiceResult[TimeSeriesResult]:
        """Return at most 2,000 buckets at the smallest valid coarser resolution."""

        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None:
            error = _validate_range(request.from_time, request.to_time)
        if error is None and request.measure not in _TIME_MEASURES:
            error = _invalid("The requested time-series measure is not supported.")
        if error is None and (
            isinstance(request.requested_resolution_minutes, bool)
            or not isinstance(request.requested_resolution_minutes, int)
            or request.requested_resolution_minutes <= 0
        ):
            error = _invalid("requested_resolution_minutes must be positive.")
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))
        actual_resolution = _actual_resolution_minutes(
            request.from_time,
            request.to_time,
            request.requested_resolution_minutes,
            self._config.max_time_buckets,
        )
        lease_result = _acquire_read(self, request.snapshot_id)
        if not lease_result.ok:
            return cast(ServiceResult[TimeSeriesResult], lease_result)
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
            except _OperationFailure as failure:
                return _failure(failure.error)
            validation = self._validate_time_series(
                result, request, actual_resolution, state.metadata
            )
            if validation is not None:
                return _failure(self._with_operation(validation, context.operation_id))
            return _success(
                replace(
                    result,
                    from_time=result.from_time.astimezone(timezone.utc),
                    to_time=result.to_time.astimezone(timezone.utc),
                    buckets=tuple(
                        replace(
                            bucket,
                            from_time=bucket.from_time.astimezone(timezone.utc),
                            to_time=bucket.to_time.astimezone(timezone.utc),
                        )
                        for bucket in result.buckets
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
    ) -> ServiceResult[PageResult[SequenceRow]]:
        """Return one stable bounded delegation or communication sequence page."""

        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None and request.focus_agent_id is not None:
            error = _validate_identifier(request.focus_agent_id, "focus_agent_id")
        if error is None:
            error = self._validate_event_filters(request.filters)
        if error is None and request.grouping not in _GROUPINGS:
            error = _invalid("The sequence grouping is not supported.")
        if error is None:
            error = _validate_page(request.page_size, self._config.max_page_size)
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))

        def query(
            handle: SnapshotReadHandle, after: str | None
        ) -> QuerySlice[SequenceRow]:
            return self._run_query_call(
                context,
                "query_sequence",
                cancellation,
                lambda: self._dependencies.queries.query_sequence(
                    handle, request, after, cancellation
                ),
            )

        return _query_page(
            self,
            request,
            "query_sequence",
            "sequence.occurred_at, sequence.sequence_id",
            query,
        )

    def query_coordination(
        self,
        context: OperationContext,
        request: CoordinationQueryRequest,
        *,
        cancellation: CancellationToken,
    ) -> ServiceResult[PageResult[CoordinationRow]]:
        """Return one stable bounded coordination page with explicit evidence labels."""

        error = self._common_snapshot_gate(context, request.snapshot_id)
        if error is None:
            error = _validate_filter_values(request.work_item_ids, "work_item_ids")
        if error is None:
            error = _validate_filter_values(request.agent_ids, "agent_ids")
        if error is None:
            error = _validate_page(request.page_size, self._config.max_page_size)
        if error is not None:
            return _failure(self._with_operation(error, context.operation_id))

        def query(
            handle: SnapshotReadHandle, after: str | None
        ) -> QuerySlice[CoordinationRow]:
            result = self._run_query_call(
                context,
                "query_coordination",
                cancellation,
                lambda: self._dependencies.queries.query_coordination(
                    handle, request, after, cancellation
                ),
            )
            return QuerySlice(
                items=tuple(
                    replace(row, evidence="inferred")
                    if "decision" in row.action.casefold()
                    else row
                    for row in result.items
                ),
                next_position=result.next_position,
            )

        return _query_page(
            self,
            request,
            "query_coordination",
            "coordination.occurred_at, coordination.coordination_id",
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
                validation = self._validate_export_result(result, resolved)
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
                            tuple[str, ...],
                            _bounded_strings(result.omissions, MAX_PROVENANCE_ITEMS),
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
        if result.snapshot_id != metadata.snapshot_id or result.scope != ReportScope(
            metadata.root_thread_id,
            metadata.include_children,
            metadata.include_collaborators,
        ):
            return _safe_internal_error("")
        for label, value in (("goal", result.goal), ("state", result.state)):
            error = _validate_bounded_text(value, label)
            if error is not None:
                return error
        if len(result.metrics) > MAX_FILTER_VALUES:
            return _safe_internal_error("")
        metrics: list[MetricValue] = []
        for metric in result.metrics:
            if metric.evidence not in _EVIDENCE_KINDS:
                return _safe_internal_error("")
            for label, value in (
                ("metric name", metric.name),
                ("metric unit", metric.unit),
                ("metric provenance", metric.provenance),
                (
                    "metric value",
                    metric.value if isinstance(metric.value, str) else None,
                ),
            ):
                error = _validate_bounded_text(value, label)
                if error is not None:
                    return error
            metrics.append(metric)
        provenance = _bounded_strings(result.provenance, MAX_PROVENANCE_ITEMS)
        warnings = _bounded_warnings(result.warnings)
        if provenance is None or warnings is None:
            return ReportError(
                code="REPORT_PRIVACY_FAILED",
                message="The report summary failed privacy validation.",
                recoverable=False,
            )
        if len(result.recent_activity) > MAX_RECENT_ACTIVITY:
            return _safe_internal_error("")
        activities: list[ActivityItem] = []
        for item in result.recent_activity:
            if (
                _validate_identifier(item.event_id, "event_id") is not None
                or not _aware_datetime(item.occurred_at)
                or item.evidence not in _EVIDENCE_KINDS
            ):
                return _safe_internal_error("")
            for label, value in (
                ("activity kind", item.kind),
                ("activity summary", item.summary),
            ):
                error = _validate_bounded_text(value, label)
                if error is not None:
                    return error
            activities.append(
                replace(item, occurred_at=item.occurred_at.astimezone(timezone.utc))
            )
        return replace(
            result,
            metrics=tuple(metrics),
            provenance=provenance,
            warnings=warnings,
            recent_activity=tuple(activities),
        )

    def _validate_time_series(
        self,
        result: TimeSeriesResult,
        request: TimeRangeQueryRequest,
        actual_resolution: int,
        metadata: SnapshotMetadata,
    ) -> ReportError | None:
        if (
            result.snapshot_id != metadata.snapshot_id
            or result.measure != request.measure
            or result.requested_resolution_minutes
            != request.requested_resolution_minutes
            or result.actual_resolution_minutes != actual_resolution
            or not _aware_datetime(result.from_time)
            or not _aware_datetime(result.to_time)
            or result.from_time.astimezone(timezone.utc)
            != request.from_time.astimezone(timezone.utc)
            or result.to_time.astimezone(timezone.utc)
            != request.to_time.astimezone(timezone.utc)
            or len(result.buckets) > self._config.max_time_buckets
        ):
            return _safe_internal_error("")
        previous_to: datetime | None = None
        for bucket in result.buckets:
            if (
                not _aware_datetime(bucket.from_time)
                or not _aware_datetime(bucket.to_time)
                or bucket.from_time >= bucket.to_time
                or bucket.evidence not in _EVIDENCE_KINDS
                or (previous_to is not None and bucket.from_time < previous_to)
            ):
                return _safe_internal_error("")
            previous_to = bucket.to_time
        if _bounded_strings(result.provenance, MAX_PROVENANCE_ITEMS) is None:
            return ReportError(
                code="REPORT_PRIVACY_FAILED",
                message="The time-series provenance failed privacy validation.",
                recoverable=False,
            )
        return None

    def _normalize_event_detail(
        self, detail: EventDetail, snapshot_id: str, event_id: str
    ) -> EventDetail | ReportError:
        if (
            detail.snapshot_id != snapshot_id
            or detail.event_id != event_id
            or not _aware_datetime(detail.occurred_at)
            or detail.evidence not in _EVIDENCE_KINDS
        ):
            return _safe_internal_error("")
        for label, value in (
            ("event kind", detail.kind),
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
        redactions = list(detail.redactions)
        bounded_arguments = detail.bounded_arguments
        bounded_result = detail.bounded_result
        for detail_label, detail_value in (
            ("bounded_arguments", bounded_arguments),
            ("bounded_result", bounded_result),
        ):
            if detail_value is not None and _contains_absolute_path(detail_value):
                return ReportError(
                    code="REPORT_PRIVACY_FAILED",
                    message="The event detail failed privacy validation.",
                    recoverable=False,
                )
            if (
                detail_value is not None
                and len(detail_value.encode("utf-8")) > MAX_DETAIL_FIELD_BYTES
            ):
                redactions.append(
                    f"{detail_label} omitted because it exceeded the detail limit."
                )
                if detail_label == "bounded_arguments":
                    bounded_arguments = None
                else:
                    bounded_result = None
        bounded_redactions = _bounded_strings(redactions, MAX_PROVENANCE_ITEMS)
        if bounded_redactions is None:
            return ReportError(
                code="REPORT_PRIVACY_FAILED",
                message="The event redactions failed privacy validation.",
                recoverable=False,
            )
        return replace(
            detail,
            occurred_at=detail.occurred_at.astimezone(timezone.utc),
            bounded_arguments=bounded_arguments,
            bounded_result=bounded_result,
            provenance=provenance,
            redactions=bounded_redactions,
        )

    @staticmethod
    def _validate_export_result(
        result: ExportResult, request: ResolvedExportRequest
    ) -> ReportError | None:
        if (
            result.mode != request.mode
            or result.published_target != request.target
            or not result.published_target.is_absolute()
            or (
                result.manifest_id is not None
                and _validate_identifier(result.manifest_id, "manifest_id") is not None
            )
        ):
            return _safe_internal_error("")
        if (
            _bounded_warnings(result.warnings) is None
            or _bounded_strings(result.omissions, MAX_PROVENANCE_ITEMS) is None
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
    request: (
        ListAgentsRequest
        | ListTurnsRequest
        | ListEventsRequest
        | SequenceQueryRequest
        | CoordinationQueryRequest
    ),
    operation: str,
    sort: str,
    query: Callable[[SnapshotReadHandle, str | None], QuerySlice[T]],
) -> ServiceResult[PageResult[T]]:
    digest = _filters_digest(_page_filter_value(request))
    lease_result = _acquire_read(self, request.snapshot_id)
    if not lease_result.ok:
        return cast(ServiceResult[PageResult[T]], lease_result)
    lease = cast(_ReadLease, lease_result.value)
    with lease as state:
        after: str | None = None
        if request.cursor is not None:
            if not _valid_text(request.cursor, MAX_ID_BYTES, trim=True):
                return _failure(_cursor_conflict())
            try:
                with self._state_changed:
                    claims = self._token_codec.decode_cursor(request.cursor)
            except _TokenDecodeError:
                return _failure(_cursor_conflict())
            if (
                claims
                != _CursorClaims(
                    snapshot_id=request.snapshot_id,
                    revision_id=state.revision_id,
                    operation=operation,
                    filters_digest=digest,
                    sort=sort,
                    page_size=request.page_size,
                    position=claims.position,
                )
                or _validate_identifier(claims.position, "cursor position") is not None
            ):
                return _failure(_cursor_conflict())
            after = claims.position
        try:
            query_slice = query(state.read_handle, after)
        except _OperationFailure as failure:
            return _failure(failure.error)
        except Exception:
            return _failure(_safe_internal_error(""))
        if (
            not isinstance(query_slice, QuerySlice)
            or len(query_slice.items) > request.page_size
            or (
                query_slice.next_position is not None
                and _validate_identifier(query_slice.next_position, "cursor position")
                is not None
            )
        ):
            return _failure(_safe_internal_error(""))
        normalized = _normalize_page_items(operation, query_slice.items)
        if isinstance(normalized, ReportError):
            return _failure(normalized)
        next_cursor = None
        if query_slice.next_position is not None:
            with self._state_changed:
                next_cursor = self._token_codec.encode_cursor(
                    _CursorClaims(
                        snapshot_id=request.snapshot_id,
                        revision_id=state.revision_id,
                        operation=operation,
                        filters_digest=digest,
                        sort=sort,
                        page_size=request.page_size,
                        position=query_slice.next_position,
                    )
                )
        return _success(
            PageResult(
                snapshot_id=request.snapshot_id,
                operation=operation,
                items=cast(tuple[T, ...], normalized),
                applied_filters_digest=digest,
                applied_sort=sort,
                page_size=request.page_size,
                next_cursor=next_cursor,
            )
        )


def _page_filter_value(
    request: (
        ListAgentsRequest
        | ListTurnsRequest
        | ListEventsRequest
        | SequenceQueryRequest
        | CoordinationQueryRequest
    ),
) -> object:
    if isinstance(request, (ListAgentsRequest, ListTurnsRequest, ListEventsRequest)):
        return request.filters
    if isinstance(request, SequenceQueryRequest):
        return {
            "focus_agent_id": request.focus_agent_id,
            "filters": request.filters,
            "grouping": request.grouping,
        }
    return {
        "work_item_ids": request.work_item_ids,
        "agent_ids": request.agent_ids,
    }


def _normalize_page_items(
    operation: str, items: Sequence[object]
) -> tuple[object, ...] | ReportError:
    normalized: list[object] = []
    sort_keys: list[tuple[object, str]] = []
    for item in items:
        if operation == "list_agents" and isinstance(item, AgentRow):
            if (
                _validate_identifier(item.agent_id, "agent_id") is not None
                or (
                    item.parent_agent_id is not None
                    and _validate_identifier(item.parent_agent_id, "parent_agent_id")
                    is not None
                )
                or not _valid_row_texts(item.role, item.state)
                or not _optional_aware(item.started_at)
                or not _optional_aware(item.ended_at)
                or item.evidence not in _EVIDENCE_KINDS
            ):
                return _safe_internal_error("")
            normalized_agent = replace(
                item,
                started_at=_utc_or_none(item.started_at),
                ended_at=_utc_or_none(item.ended_at),
            )
            sort_keys.append(
                (
                    normalized_agent.started_at
                    or datetime.min.replace(tzinfo=timezone.utc),
                    item.agent_id,
                )
            )
            normalized.append(normalized_agent)
        elif operation == "list_turns" and isinstance(item, TurnRow):
            if (
                _validate_identifier(item.turn_id, "turn_id") is not None
                or _validate_identifier(item.agent_id, "agent_id") is not None
                or not _valid_row_texts(item.state)
                or not _aware_datetime(item.started_at)
                or not _optional_aware(item.ended_at)
                or isinstance(item.event_count, bool)
                or not isinstance(item.event_count, int)
                or item.event_count < 0
                or item.evidence not in _EVIDENCE_KINDS
            ):
                return _safe_internal_error("")
            normalized_turn = replace(
                item,
                started_at=item.started_at.astimezone(timezone.utc),
                ended_at=_utc_or_none(item.ended_at),
            )
            sort_keys.append((normalized_turn.started_at, item.turn_id))
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
            ):
                return _safe_internal_error("")
            normalized_event = replace(
                item, occurred_at=item.occurred_at.astimezone(timezone.utc)
            )
            sort_keys.append((normalized_event.occurred_at, item.event_id))
            normalized.append(normalized_event)
        elif operation == "query_sequence" and isinstance(item, SequenceRow):
            if (
                _validate_identifier(item.sequence_id, "sequence_id") is not None
                or (
                    item.source_agent_id is not None
                    and _validate_identifier(item.source_agent_id, "source_agent_id")
                    is not None
                )
                or (
                    item.target_agent_id is not None
                    and _validate_identifier(item.target_agent_id, "target_agent_id")
                    is not None
                )
                or not _aware_datetime(item.occurred_at)
                or not _valid_row_texts(item.kind, item.summary)
                or isinstance(item.repeated_count, bool)
                or not isinstance(item.repeated_count, int)
                or item.repeated_count < 1
                or item.evidence not in _EVIDENCE_KINDS
            ):
                return _safe_internal_error("")
            normalized_sequence = replace(
                item, occurred_at=item.occurred_at.astimezone(timezone.utc)
            )
            sort_keys.append((normalized_sequence.occurred_at, item.sequence_id))
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
                or _validate_filter_values(item.agent_ids, "agent_ids") is not None
                or not _aware_datetime(item.occurred_at)
                or not _valid_row_texts(item.action, item.summary)
                or item.evidence not in _EVIDENCE_KINDS
            ):
                return _safe_internal_error("")
            normalized_coordination = replace(
                item,
                occurred_at=item.occurred_at.astimezone(timezone.utc),
                agent_ids=tuple(item.agent_ids),
            )
            sort_keys.append(
                (normalized_coordination.occurred_at, item.coordination_id)
            )
            normalized.append(normalized_coordination)
        else:
            return _safe_internal_error("")
    if sort_keys != sorted(sort_keys):
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


def _utc_or_none(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc) if value is not None else None


def _actual_resolution_minutes(
    from_time: datetime,
    to_time: datetime,
    requested_resolution_minutes: int,
    maximum_buckets: int,
) -> int:
    duration_seconds = (
        to_time.astimezone(timezone.utc) - from_time.astimezone(timezone.utc)
    ).total_seconds()
    requested_buckets = math.ceil(
        duration_seconds / (requested_resolution_minutes * 60)
    )
    multiplier = max(1, math.ceil(requested_buckets / maximum_buckets))
    return requested_resolution_minutes * multiplier


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
    if not _LOWER_HEX_DIGEST.fullmatch(config.pricing_digest):
        raise ValueError("pricing_digest must be a lowercase SHA-256 digest")
    if not _LOWER_HEX_DIGEST.fullmatch(config.formatter_digest):
        raise ValueError("formatter_digest must be a lowercase SHA-256 digest")
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
    if config.max_time_buckets != MAX_TIME_BUCKETS:
        raise ValueError("max_time_buckets must equal 2000 for protocol version 1")
