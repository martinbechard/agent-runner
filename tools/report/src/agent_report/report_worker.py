# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Adapt bounded JSONL worker records to the Agent Report application service.
# Design: docs/design/components/CD-004-agent-report-worker-protocol.md

"""Versioned JSONL process adapter for the Agent Report application service."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import re
import sys
import threading
import time
import types
import typing
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Final, Literal, Protocol, TextIO, TypeAlias, TypeVar, cast, get_args, get_origin, get_type_hints

from .application_service import (
    AgentFilters,
    AgentRow,
    AgentSort,
    ApplicationService,
    ApplicationServiceConfig,
    AutomationSurface,
    CancellationToken,
    CloseSnapshotRequest,
    CloseSnapshotResult,
    CoordinationFilters,
    CoordinationQueryRequest,
    CoordinationRow,
    CoordinationSort,
    Disclosure,
    EventDetail,
    EventDetailsRequest,
    EventFilters,
    EventRow,
    EventSort,
    ExportMode,
    ExportOmission,
    ExportResult,
    ExportSnapshotRequest,
    HeatmapCell,
    HeatmapQueryRequest,
    HeatmapResult,
    HeatmapRow,
    HeatmapScale,
    ListAgentsRequest,
    ListEventsRequest,
    ListTurnsRequest,
    MetricGroup,
    MetricValue,
    OpenSnapshotRequest,
    OperationContext,
    PageResult,
    PreflightReportRequest,
    PreflightResult,
    ProgressSink,
    RefreshSnapshotRequest,
    RefreshSnapshotResult,
    ReportError,
    ReportErrorCode,
    ReportScope,
    SequenceFilters,
    SequenceGroup,
    SequenceGrouping,
    SequenceQueryRequest,
    SequenceResult,
    SequenceRow,
    SequenceSort,
    ServiceResult,
    SnapshotMetadata,
    SnapshotRequest,
    SignificantActivity,
    SummaryResult,
    TimeRange,
    TimeMeasure,
    TurnFilters,
    TurnRow,
    TurnSort,
    WarningRecord,
)


PROTOCOL_VERSION: Final[int] = 1
MAX_RECORD_BYTES: Final[int] = 1_048_576
MAX_MESSAGE_CHARS: Final[int] = 512
PROGRESS_INTERVAL_SECONDS: Final[float] = 0.050
HANDSHAKE_OPERATION_ID: Final[str] = "op_000000000000000000000000"
_MAX_U64: Final[int] = 18_446_744_073_709_551_615
_OPERATION_ID = re.compile(r"op_[0-9a-f]{24}\Z")
_OPERATION_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_VISIBLE_SNAPSHOT = re.compile(r"[!-~]{1,128}\Z")

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
OperationName = Literal[
    "preflight_report", "open_snapshot", "get_summary", "list_agents", "list_turns",
    "list_events", "query_time_range", "query_sequence", "query_coordination",
    "get_event_details", "refresh_snapshot", "export_snapshot", "close_snapshot",
]
ServiceMethodName = OperationName
ServiceRequestValue = (
    PreflightReportRequest | OpenSnapshotRequest | SnapshotRequest | ListAgentsRequest
    | ListTurnsRequest | ListEventsRequest | HeatmapQueryRequest | SequenceQueryRequest
    | CoordinationQueryRequest | EventDetailsRequest | RefreshSnapshotRequest
    | ExportSnapshotRequest | CloseSnapshotRequest
)
ServiceResultValue = (
    PreflightResult | SnapshotMetadata | SummaryResult | PageResult[AgentRow, AgentFilters, AgentSort]
    | PageResult[TurnRow, TurnFilters, TurnSort] | PageResult[EventRow, EventFilters, EventSort]
    | HeatmapResult | SequenceResult | PageResult[CoordinationRow, CoordinationFilters, CoordinationSort] | EventDetail
    | RefreshSnapshotResult | ExportResult | CloseSnapshotResult
)
PageRowValue = AgentRow | TurnRow | EventRow | SequenceRow | CoordinationRow
ResultSerializer = Callable[[ServiceResultValue], dict[str, JsonValue]]
ApplicationServiceFactory = Callable[[ApplicationServiceConfig], ApplicationService]


class WorkerProtocolError(ValueError):
    """Report one bounded protocol or service-contract rejection."""

    def __init__(self, code: str, message: str, *, operation_id: str | None = None, recoverable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.operation_id = operation_id
        self.recoverable = recoverable


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    protocol_version: int
    package_version: str
    max_in_flight: int
    max_record_bytes: int

    def __post_init__(self) -> None:
        if type(self.protocol_version) is not int or self.protocol_version != PROTOCOL_VERSION:
            raise ValueError("protocol_version must equal the supported protocol version")
        if not self.package_version or len(self.package_version) > 128:
            raise ValueError("package_version must be a non-empty bounded string")
        if type(self.max_in_flight) is not int or not 1 <= self.max_in_flight <= 64:
            raise ValueError("max_in_flight must be between 1 and 64")
        if type(self.max_record_bytes) is not int or not 256 <= self.max_record_bytes <= MAX_RECORD_BYTES:
            raise ValueError("max_record_bytes must be between 256 and MAX_RECORD_BYTES")


@dataclass(frozen=True, slots=True)
class RequestEnvelope:
    protocol_version: int
    operation_id: str
    operation: str
    snapshot_id: str | None
    arguments: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class CancelEnvelope:
    protocol_version: int
    operation_id: str
    type: Literal["cancel"] = "cancel"


@dataclass(frozen=True, slots=True)
class StructuredError:
    code: str
    message: str
    operation_id: str | None
    recoverable: bool
    current_source_revision: str | None = None
    preflight_required: bool = False
    restart_from_first_page: bool = False


@dataclass(frozen=True, slots=True)
class ProgressEnvelope:
    protocol_version: int
    operation_id: str
    type: Literal["progress"]
    operation: str
    snapshot_id: str | None
    phase: str
    completed: int
    total: int | None
    message: str


@dataclass(frozen=True, slots=True)
class ResultEnvelope:
    protocol_version: int
    operation_id: str
    type: Literal["result"]
    operation: str
    snapshot_id: str | None
    ok: Literal[True]
    result: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ErrorEnvelope:
    protocol_version: int
    operation_id: str
    type: Literal["error"]
    operation: str
    snapshot_id: str | None
    ok: Literal[False]
    error: StructuredError


@dataclass(frozen=True, slots=True)
class CancelledEnvelope:
    protocol_version: int
    operation_id: str
    type: Literal["cancelled"]
    operation: str
    snapshot_id: str | None
    ok: Literal[False]
    error: StructuredError


class MonotonicClock(Protocol):
    def now(self) -> float: ...


class _SystemClock:
    def now(self) -> float:
        return time.monotonic()


class ThreadCancellationToken(CancellationToken):
    def __init__(self, event: threading.Event) -> None:
        self._event = event

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class OperationState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    RESULT = "result"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class OperationSlot:
    request: RequestEnvelope
    cancellation_event: threading.Event
    state: OperationState
    last_observed_phase: str | None
    last_observed_completed: int
    last_observed_progress: ProgressEnvelope | None
    last_emitted_progress: ProgressEnvelope | None
    pending_progress: ProgressEnvelope | None
    next_progress_at: float
    lock: threading.Lock


@dataclass(frozen=True, slots=True)
class OperationBinding:
    request_type: type[ServiceRequestValue]
    method_name: ServiceMethodName
    result_type: type[ServiceResultValue]
    page_item_type: type[PageRowValue] | None
    serialize_result: ResultSerializer


def _default_serializer(value: ServiceResultValue) -> dict[str, JsonValue]:
    encoded = _to_json(value)
    if not isinstance(encoded, dict):
        raise _contract_error()
    return encoded


OPERATION_BINDINGS: Final[dict[OperationName, OperationBinding]] = {
    "preflight_report": OperationBinding(PreflightReportRequest, "preflight_report", PreflightResult, None, _default_serializer),
    "open_snapshot": OperationBinding(OpenSnapshotRequest, "open_snapshot", SnapshotMetadata, None, _default_serializer),
    "get_summary": OperationBinding(SnapshotRequest, "get_summary", SummaryResult, None, _default_serializer),
    "list_agents": OperationBinding(ListAgentsRequest, "list_agents", PageResult, AgentRow, _default_serializer),
    "list_turns": OperationBinding(ListTurnsRequest, "list_turns", PageResult, TurnRow, _default_serializer),
    "list_events": OperationBinding(ListEventsRequest, "list_events", PageResult, EventRow, _default_serializer),
    "query_time_range": OperationBinding(HeatmapQueryRequest, "query_time_range", HeatmapResult, None, _default_serializer),
    "query_sequence": OperationBinding(SequenceQueryRequest, "query_sequence", SequenceResult, SequenceRow, _default_serializer),
    "query_coordination": OperationBinding(CoordinationQueryRequest, "query_coordination", PageResult, CoordinationRow, _default_serializer),
    "get_event_details": OperationBinding(EventDetailsRequest, "get_event_details", EventDetail, None, _default_serializer),
    "refresh_snapshot": OperationBinding(RefreshSnapshotRequest, "refresh_snapshot", RefreshSnapshotResult, None, _default_serializer),
    "export_snapshot": OperationBinding(ExportSnapshotRequest, "export_snapshot", ExportResult, None, _default_serializer),
    "close_snapshot": OperationBinding(CloseSnapshotRequest, "close_snapshot", CloseSnapshotResult, None, _default_serializer),
}
if set(OPERATION_BINDINGS) != set(get_args(OperationName)):
    raise RuntimeError("Operation bindings do not match OperationName")


def _protocol_error(message: str, *, operation_id: str | None = None) -> WorkerProtocolError:
    return WorkerProtocolError("REPORT_WORKER_INVALID_ENVELOPE", message, operation_id=operation_id)


def _contract_error() -> WorkerProtocolError:
    return WorkerProtocolError(
        "REPORT_WORKER_SERVICE_CONTRACT",
        "The service returned an invalid result for this operation.",
        recoverable=False,
    )


def _require_object(value: object, keys: set[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise _protocol_error(f"Invalid {label} object.")
    return cast(dict[str, object], value)


def _string(value: object, label: str) -> str:
    if type(value) is not str:
        raise _protocol_error(f"Invalid {label}.")
    return value


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise _protocol_error(f"Invalid {label}.")
    return value


def _u64(value: object, label: str) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_U64:
        raise _protocol_error(f"Invalid {label}.")
    return value


def _nullable_string(value: object, label: str) -> str | None:
    return None if value is None else _string(value, label)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise _protocol_error(f"Invalid {label}.")
    return tuple(_string(item, label) for item in value)


def _datetime(value: object, label: str) -> datetime:
    text = _string(value, label)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as error:
        raise _protocol_error(f"Invalid {label}.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _protocol_error(f"Invalid {label}.")
    return parsed


def _nullable_datetime(value: object, label: str) -> datetime | None:
    return None if value is None else _datetime(value, label)


def _one_of(value: object, choices: set[str], label: str) -> str:
    selected = _string(value, label)
    if selected not in choices:
        raise _protocol_error(f"Invalid {label}.")
    return selected


def _validate_envelope_common(data: dict[str, object]) -> tuple[int, str]:
    version = _u64(data.get("protocol_version"), "protocol version")
    operation_id = _string(data.get("operation_id"), "operation ID")
    if not _OPERATION_ID.fullmatch(operation_id):
        raise _protocol_error("Invalid operation ID.")
    if version != PROTOCOL_VERSION:
        raise WorkerProtocolError(
            "REPORT_WORKER_PROTOCOL_MISMATCH", "The worker protocol version does not match.",
            operation_id=operation_id, recoverable=False,
        )
    return version, operation_id


def parse_input_line(line: bytes, *, max_record_bytes: int = MAX_RECORD_BYTES) -> RequestEnvelope | CancelEnvelope:
    if not line.endswith(b"\n") or len(line) > max_record_bytes or line.startswith(b"\xef\xbb\xbf"):
        raise WorkerProtocolError("REPORT_WORKER_INVALID_JSON", "Invalid JSONL input record.", recoverable=False)
    try:
        data = json.loads(line[:-1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkerProtocolError("REPORT_WORKER_INVALID_JSON", "Invalid JSON input.", recoverable=False) from error
    if type(data) is not dict:
        raise _protocol_error("Invalid envelope object.")
    record = cast(dict[str, object], data)
    if "type" in record:
        _validate_envelope_common(record)
        record = _require_object(record, {"protocol_version", "operation_id", "type"}, "envelope")
        version, operation_id = _validate_envelope_common(record)
        if record["type"] != "cancel":
            raise _protocol_error("Invalid envelope type.", operation_id=operation_id)
        return CancelEnvelope(version, operation_id)
    _validate_envelope_common(record)
    record = _require_object(
        record, {"protocol_version", "operation_id", "operation", "snapshot_id", "arguments"}, "envelope"
    )
    version, operation_id = _validate_envelope_common(record)
    operation = _string(record["operation"], "operation")
    if not _OPERATION_NAME.fullmatch(operation):
        raise _protocol_error("Invalid operation.", operation_id=operation_id)
    snapshot_id = _nullable_string(record["snapshot_id"], "snapshot ID")
    if snapshot_id is not None and not _VISIBLE_SNAPSHOT.fullmatch(snapshot_id):
        raise _protocol_error("Invalid snapshot ID.", operation_id=operation_id)
    if type(record["arguments"]) is not dict:
        raise _protocol_error("Invalid arguments object.", operation_id=operation_id)
    return RequestEnvelope(version, operation_id, operation, snapshot_id, cast(dict[str, JsonValue], record["arguments"]))


def encode_output_record(
    record: ProgressEnvelope | ResultEnvelope | ErrorEnvelope | CancelledEnvelope,
    *, max_record_bytes: int = MAX_RECORD_BYTES,
) -> bytes:
    _validate_dataclass(record)
    value = _to_json(record)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as error:
        raise _contract_error() from error
    if len(encoded) > max_record_bytes:
        raise WorkerProtocolError("REPORT_WORKER_RESULT_TOO_LARGE", "The operation result is too large.")
    return encoded


def _snapshot(request: RequestEnvelope, *, required: bool) -> str | None:
    if (request.snapshot_id is None) == required:
        raise _protocol_error("Invalid snapshot selector.", operation_id=request.operation_id)
    return request.snapshot_id


def _scope(value: object) -> ReportScope:
    data = _require_object(value, {"root_thread_id", "include_children", "include_collaborators"}, "arguments.scope")
    return ReportScope(_string(data["root_thread_id"], "root thread ID"), _boolean(data["include_children"], "include_children"), _boolean(data["include_collaborators"], "include_collaborators"))


def _event_filters(value: object) -> EventFilters:
    data = _require_object(
        value, {"event_ids", "agent_ids", "turn_ids", "kinds", "from_time", "to_time"},
        "arguments.filters",
    )
    return EventFilters(
        _strings(data["event_ids"], "event IDs"),
        _strings(data["agent_ids"], "agent IDs"),
        _strings(data["turn_ids"], "turn IDs"),
        _strings(data["kinds"], "kinds"),
        _nullable_datetime(data["from_time"], "from_time"),
        _nullable_datetime(data["to_time"], "to_time"),
    )


def _agent_sort(value: object) -> AgentSort:
    data = _require_object(
        value, {"key", "direction", "tie_break_key", "tie_break_direction"},
        "arguments.sort",
    )
    return AgentSort(
        cast(typing.Any, _one_of(data["key"], {"last_activity_at", "started_at", "agent_id"}, "sort key")),
        cast(typing.Any, _one_of(data["direction"], {"ascending", "descending"}, "sort direction")),
        cast(typing.Any, _one_of(data["tie_break_key"], {"agent_id"}, "sort tie-break key")),
        cast(typing.Any, _one_of(data["tie_break_direction"], {"ascending"}, "sort tie-break direction")),
    )


def _turn_sort(value: object) -> TurnSort:
    data = _require_object(
        value, {"key", "direction", "tie_break_key", "tie_break_direction"},
        "arguments.sort",
    )
    return TurnSort(
        cast(typing.Any, _one_of(data["key"], {"started_at", "ended_at", "turn_id"}, "sort key")),
        cast(typing.Any, _one_of(data["direction"], {"ascending", "descending"}, "sort direction")),
        cast(typing.Any, _one_of(data["tie_break_key"], {"turn_id"}, "sort tie-break key")),
        cast(typing.Any, _one_of(data["tie_break_direction"], {"ascending"}, "sort tie-break direction")),
    )


def _event_sort(value: object) -> EventSort:
    data = _require_object(
        value, {"key", "direction", "tie_break_key", "tie_break_direction"},
        "arguments.sort",
    )
    return EventSort(
        cast(typing.Any, _one_of(data["key"], {"occurred_at", "event_id"}, "sort key")),
        cast(typing.Any, _one_of(data["direction"], {"ascending", "descending"}, "sort direction")),
        cast(typing.Any, _one_of(data["tie_break_key"], {"event_id"}, "sort tie-break key")),
        cast(typing.Any, _one_of(data["tie_break_direction"], {"ascending"}, "sort tie-break direction")),
    )


def _sequence_sort(value: object) -> SequenceSort:
    data = _require_object(
        value, {"key", "direction", "tie_break_key", "tie_break_direction"},
        "arguments.sort",
    )
    return SequenceSort(
        cast(typing.Any, _one_of(data["key"], {"occurred_at", "sequence_id"}, "sort key")),
        cast(typing.Any, _one_of(data["direction"], {"ascending"}, "sort direction")),
        cast(typing.Any, _one_of(data["tie_break_key"], {"sequence_id"}, "sort tie-break key")),
        cast(typing.Any, _one_of(data["tie_break_direction"], {"ascending"}, "sort tie-break direction")),
    )


def _coordination_sort(value: object) -> CoordinationSort:
    data = _require_object(
        value, {"key", "direction", "tie_break_key", "tie_break_direction"},
        "arguments.sort",
    )
    return CoordinationSort(
        cast(typing.Any, _one_of(data["key"], {"occurred_at", "coordination_id"}, "sort key")),
        cast(typing.Any, _one_of(data["direction"], {"ascending"}, "sort direction")),
        cast(typing.Any, _one_of(data["tie_break_key"], {"coordination_id"}, "sort tie-break key")),
        cast(typing.Any, _one_of(data["tie_break_direction"], {"ascending"}, "sort tie-break direction")),
    )


def decode_service_request(request: RequestEnvelope) -> ServiceRequestValue:
    try:
        operation = cast(OperationName, request.operation)
        if operation not in OPERATION_BINDINGS:
            raise WorkerProtocolError("REPORT_WORKER_UNKNOWN_OPERATION", "The requested operation is not supported.", operation_id=request.operation_id)
        arguments = request.arguments
        if operation == "preflight_report":
            data = _require_object(arguments, {"scope"}, "arguments")
            _snapshot(request, required=False)
            return PreflightReportRequest(_scope(data["scope"]))
        if operation == "open_snapshot":
            data = _require_object(arguments, {"scope", "preflight_token", "source_revision"}, "arguments")
            _snapshot(request, required=False)
            return OpenSnapshotRequest(
                _scope(data["scope"]), _string(data["preflight_token"], "preflight token"),
                _string(data["source_revision"], "source revision"),
            )
        snapshot_id = cast(str, _snapshot(request, required=True))
        if operation == "get_summary":
            _require_object(arguments, set(), "arguments")
            return SnapshotRequest(snapshot_id)
        if operation == "refresh_snapshot":
            _require_object(arguments, set(), "arguments")
            return RefreshSnapshotRequest(snapshot_id)
        if operation == "close_snapshot":
            _require_object(arguments, set(), "arguments")
            return CloseSnapshotRequest(snapshot_id)
        if operation == "list_agents":
            data = _require_object(arguments, {"filters", "sort", "cursor", "page_size"}, "arguments")
            filters = _require_object(
                data["filters"], {"query", "agent_ids", "roles", "states"},
                "arguments.filters",
            )
            return ListAgentsRequest(
                snapshot_id,
                AgentFilters(
                    _string(filters["query"], "query"),
                    _strings(filters["agent_ids"], "agent IDs"),
                    _strings(filters["roles"], "roles"),
                    _strings(filters["states"], "states"),
                ),
                _agent_sort(data["sort"]), _nullable_string(data["cursor"], "cursor"),
                _u64(data["page_size"], "page_size"),
            )
        if operation == "list_turns":
            data = _require_object(arguments, {"filters", "sort", "cursor", "page_size"}, "arguments")
            filters = _require_object(
                data["filters"],
                {"turn_ids", "agent_ids", "states", "from_time", "to_time"},
                "arguments.filters",
            )
            return ListTurnsRequest(
                snapshot_id,
                TurnFilters(
                    _strings(filters["turn_ids"], "turn IDs"),
                    _strings(filters["agent_ids"], "agent IDs"),
                    _strings(filters["states"], "states"),
                    _nullable_datetime(filters["from_time"], "from_time"),
                    _nullable_datetime(filters["to_time"], "to_time"),
                ),
                _turn_sort(data["sort"]), _nullable_string(data["cursor"], "cursor"),
                _u64(data["page_size"], "page_size"),
            )
        if operation == "list_events":
            data = _require_object(arguments, {"filters", "sort", "cursor", "page_size"}, "arguments")
            return ListEventsRequest(
                snapshot_id, _event_filters(data["filters"]), _event_sort(data["sort"]),
                _nullable_string(data["cursor"], "cursor"), _u64(data["page_size"], "page_size"),
            )
        if operation == "query_time_range":
            data = _require_object(arguments, {"from_time", "to_time", "measure", "requested_resolution_minutes", "group_by", "maximum_rows"}, "arguments")
            measure = _string(data["measure"], "measure")
            if measure not in get_args(TimeMeasure):
                raise _protocol_error("Invalid measure.")
            group_by = _one_of(data["group_by"], {"agent", "event_kind", "work_item"}, "group_by")
            return HeatmapQueryRequest(
                snapshot_id, _datetime(data["from_time"], "from_time"),
                _datetime(data["to_time"], "to_time"), cast(TimeMeasure, measure),
                _u64(data["requested_resolution_minutes"], "requested_resolution_minutes"),
                cast(typing.Any, group_by), _u64(data["maximum_rows"], "maximum_rows"),
            )
        if operation == "query_sequence":
            data = _require_object(arguments, {"filters", "sort", "cursor", "page_size"}, "arguments")
            filters = _require_object(
                data["filters"],
                {"focus_agent_id", "event_filters", "grouping", "include_reasoning"},
                "arguments.filters",
            )
            grouping = _string(filters["grouping"], "grouping")
            if grouping not in get_args(SequenceGrouping):
                raise _protocol_error("Invalid grouping.")
            return SequenceQueryRequest(
                snapshot_id,
                SequenceFilters(
                    _nullable_string(filters["focus_agent_id"], "focus agent ID"),
                    _event_filters(filters["event_filters"]),
                    cast(SequenceGrouping, grouping),
                    _boolean(filters["include_reasoning"], "include_reasoning"),
                ),
                _sequence_sort(data["sort"]), _nullable_string(data["cursor"], "cursor"),
                _u64(data["page_size"], "page_size"),
            )
        if operation == "query_coordination":
            data = _require_object(arguments, {"filters", "sort", "cursor", "page_size"}, "arguments")
            filters = _require_object(data["filters"], {"work_item_id", "delegated_root_id", "agent_id", "operation", "evidence"}, "arguments.filters")
            evidence = _nullable_string(filters["evidence"], "evidence")
            if evidence is not None and evidence not in {"measured", "derived", "inferred", "unavailable", "estimated"}:
                raise _protocol_error("Invalid evidence.")
            return CoordinationQueryRequest(
                snapshot_id,
                CoordinationFilters(
                    _nullable_string(filters["work_item_id"], "work item ID"),
                    _nullable_string(filters["delegated_root_id"], "delegated root ID"),
                    _nullable_string(filters["agent_id"], "agent ID"),
                    _nullable_string(filters["operation"], "operation"),
                    cast(typing.Any, evidence),
                ),
                _coordination_sort(data["sort"]), _nullable_string(data["cursor"], "cursor"),
                _u64(data["page_size"], "page_size"),
            )
        if operation == "get_event_details":
            data = _require_object(arguments, {"event_id"}, "arguments")
            return EventDetailsRequest(snapshot_id, _string(data["event_id"], "event ID"))
        if operation == "export_snapshot":
            data = _require_object(arguments, {"surface", "target", "replace", "mode", "include_sqlite_archive"}, "arguments")
            surface = _string(data["surface"], "surface")
            mode = _nullable_string(data["mode"], "mode")
            if surface not in get_args(AutomationSurface) or (mode is not None and mode not in get_args(ExportMode)):
                raise _protocol_error("Invalid export arguments.")
            return ExportSnapshotRequest(snapshot_id, cast(AutomationSurface, surface), Path(_string(data["target"], "target")), _boolean(data["replace"], "replace"), cast(ExportMode | None, mode), _boolean(data["include_sqlite_archive"], "include_sqlite_archive"))
    except WorkerProtocolError as error:
        if error.operation_id is None:
            error.operation_id = request.operation_id
        raise
    raise WorkerProtocolError("REPORT_WORKER_UNKNOWN_OPERATION", "The requested operation is not supported.", operation_id=request.operation_id)


_PROGRESS_OPERATIONS: Final[frozenset[str]] = frozenset({"preflight_report", "open_snapshot", "refresh_snapshot", "export_snapshot"})


def dispatch_service_operation(
    service: ApplicationService,
    request: RequestEnvelope,
    *,
    cancellation: ThreadCancellationToken,
    progress: ProgressSink,
) -> ServiceResult[ServiceResultValue]:
    operation = cast(OperationName, request.operation)
    binding = OPERATION_BINDINGS.get(operation)
    if binding is None:
        raise WorkerProtocolError("REPORT_WORKER_UNKNOWN_OPERATION", "The requested operation is not supported.", operation_id=request.operation_id)
    value = decode_service_request(request)
    if type(value) is not binding.request_type:
        raise _contract_error()
    method = getattr(service, binding.method_name)
    context = OperationContext(request.protocol_version, request.operation_id)
    if operation == "close_snapshot":
        result = method(context, value)
    elif operation in _PROGRESS_OPERATIONS:
        result = method(context, value, cancellation=cancellation, progress=progress)
    else:
        result = method(context, value, cancellation=cancellation)
    return cast(ServiceResult[ServiceResultValue], result)


_ALLOWED_DATACLASSES: Final[set[type[object]]] = {
    WarningRecord, ReportScope, AgentFilters, AgentSort, TurnFilters, TurnSort,
    EventFilters, EventSort, SequenceFilters, SequenceSort, CoordinationFilters,
    CoordinationSort, MetricValue, MetricGroup, TimeRange, SignificantActivity,
    AgentRow, TurnRow, EventRow, HeatmapCell, HeatmapScale, HeatmapRow,
    SequenceRow, SequenceGroup, CoordinationRow, Disclosure, ExportOmission,
    PreflightResult, SnapshotMetadata, SummaryResult, PageResult, HeatmapResult,
    SequenceResult, EventDetail, RefreshSnapshotResult, ExportResult,
    CloseSnapshotResult, ProgressEnvelope, ResultEnvelope, ErrorEnvelope,
    CancelledEnvelope, StructuredError,
}


def _to_json(value: object) -> JsonValue:
    if value is None or type(value) in {bool, str}:
        return cast(None | bool | str, value)
    if type(value) is int:
        if not 0 <= value <= _MAX_U64:
            raise _contract_error()
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise _contract_error()
        return value
    if type(value) is datetime:
        moment = value
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise _contract_error()
        return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise _contract_error()
            result[key] = _to_json(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_to_json(item) for item in value]
    if is_dataclass(value) and type(value) in _ALLOWED_DATACLASSES:
        return {field.name: _to_json(getattr(value, field.name)) for field in fields(value)}
    raise _contract_error()


def _validate_annotation(value: object, annotation: object) -> None:
    if isinstance(annotation, TypeVar):
        return
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Literal:
        if not any(type(value) is type(choice) and value == choice for choice in arguments):
            raise _contract_error()
        return
    if origin in {types.UnionType, typing.Union}:
        for option in arguments:
            try:
                _validate_annotation(value, option)
                return
            except WorkerProtocolError:
                continue
        raise _contract_error()
    if origin in {Sequence, typing.Sequence}:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise _contract_error()
        for item in value:
            _validate_annotation(item, arguments[0])
        return
    if annotation is int:
        if type(value) is not int or not 0 <= value <= _MAX_U64:
            raise _contract_error()
        return
    if annotation is float:
        if type(value) is not float or not math.isfinite(value):
            raise _contract_error()
        return
    if annotation is Path:
        if not isinstance(value, Path):
            raise _contract_error()
        return
    if annotation in {str, bool, datetime}:
        if type(value) is not annotation:
            raise _contract_error()
        if annotation is datetime:
            moment = cast(datetime, value)
            if moment.tzinfo is None or moment.utcoffset() is None:
                raise _contract_error()
        return
    if isinstance(annotation, type) and is_dataclass(annotation):
        if type(value) is not annotation:
            raise _contract_error()
        _validate_dataclass(value)
        return


def _validate_dataclass(value: object) -> None:
    if not is_dataclass(value) or type(value) not in _ALLOWED_DATACLASSES:
        raise _contract_error()
    hints = get_type_hints(type(value))
    for field in fields(value):
        _validate_annotation(getattr(value, field.name), hints[field.name])


_PAGE_SCHEMAS: Final[dict[OperationName, tuple[type[object], type[object], type[object]]]] = {
    "list_agents": (AgentRow, AgentFilters, AgentSort),
    "list_turns": (TurnRow, TurnFilters, TurnSort),
    "list_events": (EventRow, EventFilters, EventSort),
    "query_sequence": (SequenceRow, SequenceFilters, SequenceSort),
    "query_coordination": (CoordinationRow, CoordinationFilters, CoordinationSort),
}


def _validate_page(
    page: object,
    *,
    operation: OperationName,
    row_type: type[object],
    filter_type: type[object],
    sort_type: type[object],
) -> PageResult[object, object, object]:
    if type(page) is not PageResult:
        raise _contract_error()
    typed_page = cast(PageResult[object, object, object], page)
    if (
        typed_page.operation != operation
        or type(typed_page.applied_filters) is not filter_type
        or type(typed_page.applied_sort) is not sort_type
        or not isinstance(typed_page.items, Sequence)
        or isinstance(typed_page.items, (str, bytes, bytearray))
        or any(type(item) is not row_type for item in typed_page.items)
    ):
        raise _contract_error()
    _validate_dataclass(typed_page.applied_filters)
    _validate_dataclass(typed_page.applied_sort)
    for item in typed_page.items:
        _validate_dataclass(item)
    return typed_page


def _validate_binding_value(
    operation: OperationName, binding: OperationBinding, value: ServiceResultValue
) -> None:
    if type(value) is not binding.result_type:
        raise _contract_error()
    if operation == "query_sequence":
        sequence = cast(SequenceResult, value)
        _validate_page(
            sequence.page, operation=operation, row_type=SequenceRow,
            filter_type=SequenceFilters, sort_type=SequenceSort,
        )
        if (
            not isinstance(sequence.groups, Sequence)
            or isinstance(sequence.groups, (str, bytes, bytearray))
            or any(type(group) is not SequenceGroup for group in sequence.groups)
        ):
            raise _contract_error()
    elif operation in _PAGE_SCHEMAS:
        row_type, filter_type, sort_type = _PAGE_SCHEMAS[operation]
        _validate_page(
            value, operation=operation, row_type=row_type,
            filter_type=filter_type, sort_type=sort_type,
        )


def serialize_service_value(request: RequestEnvelope, value: ServiceResultValue) -> dict[str, JsonValue]:
    operation = cast(OperationName, request.operation)
    binding = OPERATION_BINDINGS.get(operation)
    if binding is None:
        raise _contract_error()
    _validate_binding_value(operation, binding, value)
    _validate_dataclass(value)
    if type(value) is SnapshotMetadata:
        if value.protocol_version != request.protocol_version:
            raise WorkerProtocolError("REPORT_WORKER_SERVICE_CONTRACT", "The service returned a correlation mismatch.", recoverable=False)
    elif type(value) is PageResult:
        if value.snapshot_id != request.snapshot_id or value.operation != request.operation:
            raise WorkerProtocolError("REPORT_WORKER_SERVICE_CONTRACT", "The service returned a correlation mismatch.", recoverable=False)
    elif type(value) is SequenceResult:
        if value.page.snapshot_id != request.snapshot_id or value.page.operation != request.operation:
            raise WorkerProtocolError("REPORT_WORKER_SERVICE_CONTRACT", "The service returned a correlation mismatch.", recoverable=False)
    elif type(value) is RefreshSnapshotResult:
        if value.snapshot.snapshot_id != request.snapshot_id or value.snapshot.protocol_version != request.protocol_version:
            raise WorkerProtocolError("REPORT_WORKER_SERVICE_CONTRACT", "The service returned a correlation mismatch.", recoverable=False)
    elif request.operation in {
        "get_summary", "query_time_range", "get_event_details", "export_snapshot", "close_snapshot"
    } and getattr(value, "snapshot_id") != request.snapshot_id:
        raise WorkerProtocolError("REPORT_WORKER_SERVICE_CONTRACT", "The service returned a correlation mismatch.", recoverable=False)
    if type(value) is ExportResult and value.operation_id != request.operation_id:
        raise WorkerProtocolError("REPORT_WORKER_SERVICE_CONTRACT", "The service returned a correlation mismatch.", recoverable=False)
    return binding.serialize_result(value)


def _safe_message(message: object, fallback: str) -> str:
    if type(message) is not str:
        return fallback
    cleaned = "".join(character for character in message if character >= " " and character != "\x7f")
    return cleaned[:MAX_MESSAGE_CHARS] or fallback


def _structured_error(error: ReportError, operation_id: str) -> StructuredError:
    if error.operation_id != operation_id:
        raise _contract_error()
    if (
        type(error.code) is not str
        or error.code not in get_args(ReportErrorCode)
        or type(error.message) is not str
        or type(error.recoverable) is not bool
        or (error.current_source_revision is not None and type(error.current_source_revision) is not str)
        or type(error.preflight_required) is not bool
        or type(error.restart_from_first_page) is not bool
    ):
        raise _contract_error()
    return StructuredError(
        str(error.code), _safe_message(error.message, "The operation failed."), error.operation_id,
        bool(error.recoverable), error.current_source_revision, bool(error.preflight_required),
        bool(error.restart_from_first_page),
    )


class WorkerRuntime:
    """Own one service, bounded executor, and correlated operation state."""

    def __init__(
        self,
        service_factory: ApplicationServiceFactory,
        config: WorkerConfig,
        *,
        clock: MonotonicClock,
        stdin: BinaryIO,
        stdout: BinaryIO,
        stderr: TextIO,
    ) -> None:
        self._service_factory = service_factory
        self._config = config
        self._clock = clock
        self._stdin = stdin
        self._stdout = stdout
        self._stderr = stderr
        self._service: ApplicationService | None = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=config.max_in_flight, thread_name_prefix="report-worker")
        self._slots: dict[str, OperationSlot] = {}
        self._used_ids: set[str] = set()
        self._slots_lock = threading.Lock()
        self._output_lock = threading.Lock()
        self._output_failed = threading.Event()
        self._admitting = True

    def run(self) -> int:
        buffer = bytearray()
        try:
            while True:
                chunk = self._stdin.read(1)
                if not chunk:
                    if buffer:
                        self._diagnostic("worker.invalid_json", None, "REPORT_WORKER_INVALID_JSON", "The input stream ended with a partial record.")
                        return 2
                    self.shutdown(wait=True)
                    return 3 if self._output_failed.is_set() else 0
                buffer += chunk
                if len(buffer) > self._config.max_record_bytes:
                    self._diagnostic("worker.invalid_json", None, "REPORT_WORKER_INVALID_JSON", "The input record exceeded the configured limit.")
                    return 2
                if chunk != b"\n":
                    continue
                line = bytes(buffer)
                buffer.clear()
                try:
                    record = parse_input_line(line, max_record_bytes=self._config.max_record_bytes)
                    if isinstance(record, CancelEnvelope):
                        self.cancel(record)
                    elif record.operation == "worker_handshake":
                        if not self._handle_handshake(record):
                            return 2
                    elif self._service is None:
                        self._emit_rejection(record, "REPORT_WORKER_INVALID_ENVELOPE", "The worker handshake has not completed.", False)
                    else:
                        try:
                            self.submit(record)
                        except WorkerProtocolError as error:
                            self._emit_rejection(record, error.code, str(error), error.recoverable)
                            if not error.recoverable:
                                self._diagnostic("worker.protocol_failure", record.operation_id, error.code, "The worker rejected a protocol record.")
                                return 2
                except WorkerProtocolError as error:
                    if error.operation_id and _OPERATION_ID.fullmatch(error.operation_id):
                        operation, snapshot_id = _safe_input_correlation(line)
                        self._emit_uncorrelated_error(error.operation_id, operation, snapshot_id, error)
                    if not error.recoverable or error.code in {"REPORT_WORKER_INVALID_JSON", "REPORT_DUPLICATE_OPERATION"}:
                        self._diagnostic("worker.protocol_failure", error.operation_id, error.code, "The worker rejected a protocol record.")
                        return 2
        except Exception:
            if self._output_failed.is_set():
                return 3
            raise
        finally:
            self.shutdown(wait=False)

    def _handle_handshake(self, request: RequestEnvelope) -> bool:
        if self._service is not None or request.operation_id != HANDSHAKE_OPERATION_ID or request.snapshot_id is not None:
            self._emit_rejection(request, "REPORT_WORKER_INVALID_ENVELOPE", "The worker handshake is invalid.", False)
            return False
        try:
            args = _require_object(request.arguments, {"supervisor_protocol_version", "expected_package_version", "service_config"}, "handshake arguments")
            supervisor_version = _u64(args["supervisor_protocol_version"], "supervisor protocol version")
            expected_package = _string(args["expected_package_version"], "expected package version")
            service = _require_object(
                args["service_config"],
                {
                    "authorized_source_roots", "parser_version", "pricing_digest",
                    "pricing_version", "formatter_version", "formatter_digest",
                    "default_page_size", "max_page_size",
                    "max_heatmap_cells",
                },
                "service configuration",
            )
            if supervisor_version != self._config.protocol_version or expected_package != self._config.package_version:
                raise WorkerProtocolError("REPORT_WORKER_PROTOCOL_MISMATCH", "The worker protocol or package version does not match.", operation_id=request.operation_id, recoverable=False)
            roots_value = service["authorized_source_roots"]
            if type(roots_value) is not list or not roots_value:
                raise _protocol_error("Invalid authorized source roots.")
            roots = tuple(Path(_string(root, "authorized source root")) for root in roots_value)
            config = ApplicationServiceConfig(
                roots, _string(service["parser_version"], "parser version"),
                _string(service["pricing_version"], "pricing version"),
                _string(service["pricing_digest"], "pricing digest"),
                _string(service["formatter_version"], "formatter version"),
                _string(service["formatter_digest"], "formatter digest"),
                _u64(service["default_page_size"], "default page size"),
                _u64(service["max_page_size"], "max page size"),
                _u64(service["max_heatmap_cells"], "max heatmap cells"),
            )
            self._service = self._service_factory(config)
            self._write(ResultEnvelope(PROTOCOL_VERSION, request.operation_id, "result", request.operation, None, True, {"worker_protocol_version": PROTOCOL_VERSION, "worker_package_version": self._config.package_version}))
            return True
        except WorkerProtocolError as error:
            self._emit_rejection(request, error.code, str(error), False)
        except Exception:
            self._emit_rejection(request, "REPORT_WORKER_STARTUP_FAILED", "Worker startup failed.", False)
        return False

    def submit(self, request: RequestEnvelope) -> None:
        decode_service_request(request)
        if request.operation_id == HANDSHAKE_OPERATION_ID:
            raise _protocol_error("The reserved operation ID cannot be reused.", operation_id=request.operation_id)
        busy = False
        with self._slots_lock:
            if request.operation_id in self._used_ids:
                raise WorkerProtocolError("REPORT_DUPLICATE_OPERATION", "The operation ID has already been used.", operation_id=request.operation_id, recoverable=False)
            self._used_ids.add(request.operation_id)
            if not self._admitting or len(self._slots) >= self._config.max_in_flight:
                busy = True
            else:
                slot = OperationSlot(request, threading.Event(), OperationState.PENDING, None, 0, None, None, None, 0.0, threading.Lock())
                self._slots[request.operation_id] = slot
        if busy:
            self._emit_rejection(request, "REPORT_WORKER_BUSY", "The worker is at its operation limit.", True)
            return
        self._executor.submit(self._execute, slot)

    def cancel(self, request: CancelEnvelope) -> None:
        with self._slots_lock:
            slot = self._slots.get(request.operation_id)
        if slot is None:
            return
        with slot.lock:
            if slot.state in {OperationState.RESULT, OperationState.ERROR, OperationState.CANCELLED}:
                return
            slot.cancellation_event.set()
            slot.state = OperationState.CANCELLING

    def _execute(self, slot: OperationSlot) -> None:
        request = slot.request
        with slot.lock:
            if slot.state == OperationState.CANCELLING:
                self._terminal_cancelled(slot)
                return
            slot.state = OperationState.RUNNING
        try:
            if self._service is None:
                raise _contract_error()
            result = dispatch_service_operation(
                self._service, request, cancellation=ThreadCancellationToken(slot.cancellation_event),
                progress=lambda phase, completed, total, message: self._record_progress(request.operation_id, phase, completed, total, message),
            )
            if type(result) is not ServiceResult:
                raise _contract_error()
            if result.ok:
                if result.value is None or result.error is not None:
                    raise _contract_error()
                payload = serialize_service_value(request, result.value)
                envelope = ResultEnvelope(PROTOCOL_VERSION, request.operation_id, "result", request.operation, request.snapshot_id, True, payload)
                encode_output_record(envelope, max_record_bytes=self._config.max_record_bytes)
                self._terminal(slot, OperationState.RESULT, envelope)
            else:
                if result.value is not None or type(result.error) is not ReportError:
                    raise _contract_error()
                structured = _structured_error(result.error, request.operation_id)
                if structured.code == "REPORT_CANCELLED":
                    self._terminal(slot, OperationState.CANCELLED, CancelledEnvelope(PROTOCOL_VERSION, request.operation_id, "cancelled", request.operation, request.snapshot_id, False, structured))
                else:
                    self._terminal(slot, OperationState.ERROR, ErrorEnvelope(PROTOCOL_VERSION, request.operation_id, "error", request.operation, request.snapshot_id, False, structured))
        except WorkerProtocolError as error:
            structured = StructuredError(error.code, _safe_message(str(error), "The operation failed."), request.operation_id, error.recoverable)
            self._terminal(slot, OperationState.ERROR, ErrorEnvelope(PROTOCOL_VERSION, request.operation_id, "error", request.operation, request.snapshot_id, False, structured))
        except Exception:
            structured = StructuredError("REPORT_WORKER_INTERNAL", "The worker could not complete the operation.", request.operation_id, False)
            self._terminal(slot, OperationState.ERROR, ErrorEnvelope(PROTOCOL_VERSION, request.operation_id, "error", request.operation, request.snapshot_id, False, structured))

    def _terminal_cancelled(self, slot: OperationSlot) -> None:
        request = slot.request
        error = StructuredError("REPORT_CANCELLED", "The operation was cancelled.", request.operation_id, True)
        self._terminal(slot, OperationState.CANCELLED, CancelledEnvelope(PROTOCOL_VERSION, request.operation_id, "cancelled", request.operation, request.snapshot_id, False, error), lock_held=True)

    def _terminal(self, slot: OperationSlot, state: OperationState, record: ResultEnvelope | ErrorEnvelope | CancelledEnvelope, *, lock_held: bool = False) -> None:
        def finish() -> None:
            if slot.state in {OperationState.RESULT, OperationState.ERROR, OperationState.CANCELLED}:
                return
            now = self._clock.now()
            pending = slot.pending_progress if slot.pending_progress is not None and now >= slot.next_progress_at else None
            slot.pending_progress = None
            slot.state = state
            try:
                with self._output_lock:
                    if pending is not None:
                        self._write_unlocked(pending)
                    self._write_unlocked(record)
            finally:
                with self._slots_lock:
                    self._slots.pop(slot.request.operation_id, None)
        if lock_held:
            finish()
        else:
            with slot.lock:
                finish()

    def _record_progress(self, operation_id: str, phase: str, completed: int, total: int | None, message: str) -> None:
        with self._slots_lock:
            slot = self._slots.get(operation_id)
        if slot is None:
            raise _contract_error()
        with slot.lock:
            if slot.state in {OperationState.RESULT, OperationState.ERROR, OperationState.CANCELLED}:
                raise _contract_error()
            if type(phase) is not str or not _OPERATION_NAME.fullmatch(phase):
                raise _contract_error()
            if type(completed) is not int or not 0 <= completed <= _MAX_U64:
                raise _contract_error()
            if total is not None and (type(total) is not int or not completed <= total <= _MAX_U64):
                raise _contract_error()
            safe_message = _safe_message(message, "Working")
            current = ProgressEnvelope(PROTOCOL_VERSION, operation_id, "progress", slot.request.operation, slot.request.snapshot_id, phase, completed, total, safe_message)
            if phase == slot.last_observed_phase and completed < slot.last_observed_completed:
                raise _contract_error()
            if current == slot.last_observed_progress:
                return
            slot.last_observed_phase = phase
            slot.last_observed_completed = completed
            slot.last_observed_progress = current
            now = self._clock.now()
            if slot.last_emitted_progress is not None and now < slot.next_progress_at:
                slot.pending_progress = current
                return
            slot.pending_progress = None
            slot.last_emitted_progress = current
            slot.next_progress_at = now + PROGRESS_INTERVAL_SECONDS
            with self._output_lock:
                self._write_unlocked(current)

    def _emit_rejection(self, request: RequestEnvelope, code: str, message: str, recoverable: bool) -> None:
        error = StructuredError(code, _safe_message(message, "The worker rejected the operation."), request.operation_id, recoverable)
        self._write(ErrorEnvelope(PROTOCOL_VERSION, request.operation_id, "error", request.operation, request.snapshot_id, False, error))

    def _emit_uncorrelated_error(
        self,
        operation_id: str,
        operation: str,
        snapshot_id: str | None,
        error: WorkerProtocolError,
    ) -> None:
        structured = StructuredError(error.code, _safe_message(str(error), "The worker rejected the record."), operation_id, error.recoverable)
        self._write(ErrorEnvelope(PROTOCOL_VERSION, operation_id, "error", operation, snapshot_id, False, structured))

    def _write(self, record: ProgressEnvelope | ResultEnvelope | ErrorEnvelope | CancelledEnvelope) -> None:
        with self._output_lock:
            self._write_unlocked(record)

    def _write_unlocked(self, record: ProgressEnvelope | ResultEnvelope | ErrorEnvelope | CancelledEnvelope) -> None:
        try:
            self._stdout.write(encode_output_record(record, max_record_bytes=self._config.max_record_bytes))
            self._stdout.flush()
        except Exception:
            self._output_failed.set()
            raise

    def _diagnostic(self, event: str, operation_id: str | None, code: str | None, message: str) -> None:
        record = {"timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "level": "error", "event": event, "operation_id": operation_id, "code": code, "message": _safe_message(message, "Worker failure.")}
        try:
            line = json.dumps(record, separators=(",", ":"), ensure_ascii=True)
            self._stderr.write(line[:4095] + "\n")
            self._stderr.flush()
        except Exception:
            pass

    def shutdown(self, *, wait: bool) -> None:
        with self._slots_lock:
            self._admitting = False
            slots = tuple(self._slots.values())
        for slot in slots:
            self.cancel(CancelEnvelope(PROTOCOL_VERSION, slot.request.operation_id))
        self._executor.shutdown(wait=wait, cancel_futures=False)
        if wait and self._service is not None:
            close = getattr(self._service, "close", None)
            if callable(close):
                close()


def _safe_input_correlation(line: bytes) -> tuple[str, str | None]:
    """Recover only bounded routing fields from a rejected input record."""

    try:
        value = json.loads(line[:-1].decode("utf-8"))
        if type(value) is not dict:
            return "worker_protocol", None
        operation = value.get("operation")
        snapshot_id = value.get("snapshot_id")
        if type(operation) is not str or not _OPERATION_NAME.fullmatch(operation):
            operation = "worker_protocol"
        if snapshot_id is not None and (type(snapshot_id) is not str or not _VISIBLE_SNAPSHOT.fullmatch(snapshot_id)):
            snapshot_id = None
        return operation, snapshot_id
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "worker_protocol", None


def create_worker_runtime(
    config: WorkerConfig,
    *,
    stdin: BinaryIO,
    stdout: BinaryIO,
    stderr: TextIO,
    service_factory: Callable[[ApplicationServiceConfig], ApplicationService] | None = None,
) -> WorkerRuntime:
    """Create a stdio runtime with an optional composition-root service factory."""

    def missing_factory(_: ApplicationServiceConfig) -> ApplicationService:
        raise RuntimeError("The Application Service composition root is not configured.")

    return WorkerRuntime(
        service_factory or missing_factory,
        config,
        clock=_SystemClock(),
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-report worker")
    parser.add_argument("--max-in-flight", type=int, default=4)
    parser.add_argument("--protocol-version", type=int, default=PROTOCOL_VERSION)
    arguments = parser.parse_args(argv)
    try:
        from importlib.metadata import version

        package_version = version("agent-report")
        config = WorkerConfig(arguments.protocol_version, package_version, arguments.max_in_flight, MAX_RECORD_BYTES)
        runtime = create_worker_runtime(config, stdin=sys.stdin.buffer, stdout=sys.stdout.buffer, stderr=sys.stderr)
        return runtime.run()
    except (ValueError, RuntimeError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
    HeatmapCell,
    HeatmapQueryRequest,
    HeatmapResult,
    HeatmapRow,
    HeatmapScale,
