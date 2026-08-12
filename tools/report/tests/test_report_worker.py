# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Verify the bounded Agent Report Python worker protocol adapter.
# Design: docs/design/components/CD-004-agent-report-worker-protocol.md

from __future__ import annotations

import io
import json
import threading
import time
from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import cast, get_args

import pytest

from agent_report.application_service import (
    ActivityItem,
    AgentFilters,
    AgentRow,
    CloseSnapshotRequest,
    CloseSnapshotResult,
    CoordinationQueryRequest,
    CoordinationRow,
    EventDetail,
    EventDetailsRequest,
    EventFilters,
    EventRow,
    ExportResult,
    ExportSnapshotRequest,
    ListAgentsRequest,
    ListEventsRequest,
    ListTurnsRequest,
    MetricValue,
    OpenSnapshotRequest,
    PageResult,
    PreflightReportRequest,
    PreflightResult,
    RefreshSnapshotRequest,
    RefreshSnapshotResult,
    ReportError,
    ReportScope,
    SequenceQueryRequest,
    SequenceRow,
    ServiceResult,
    SnapshotMetadata,
    SnapshotRequest,
    SummaryResult,
    TimeRangeQueryRequest,
    TimeBucket,
    TimeSeriesResult,
    TurnFilters,
    TurnRow,
    WarningRecord,
)
from agent_report.report_worker import (
    OPERATION_BINDINGS,
    PROTOCOL_VERSION,
    CancelEnvelope,
    OperationName,
    RequestEnvelope,
    ThreadCancellationToken,
    WorkerConfig,
    WorkerProtocolError,
    WorkerRuntime,
    decode_service_request,
    dispatch_service_operation,
    parse_input_line,
    serialize_service_value,
)


OPERATION_ID = "op_0123456789abcdef01234567"
SNAPSHOT_ID = "snap_0123456789abcdef01234567"
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def request(operation: str, arguments: dict[str, object], snapshot_id: str | None = SNAPSHOT_ID) -> RequestEnvelope:
    return RequestEnvelope(PROTOCOL_VERSION, OPERATION_ID, operation, snapshot_id, arguments)  # type: ignore[arg-type]


def operation_requests() -> dict[str, RequestEnvelope]:
    scope = {"root_thread_id": "root", "include_children": True, "include_collaborators": False}
    event_filters: dict[str, object] = {
        "event_ids": [], "agent_ids": [], "turn_ids": [], "kinds": [],
        "from_time": None, "to_time": None,
    }
    return {
        "preflight_report": request("preflight_report", {"scope": scope}, None),
        "open_snapshot": request("open_snapshot", {"scope": scope, "preflight_token": "token"}, None),
        "get_summary": request("get_summary", {}),
        "list_agents": request("list_agents", {"filters": {"agent_ids": [], "roles": [], "states": []}, "cursor": None, "page_size": 25}),
        "list_turns": request("list_turns", {"filters": {"turn_ids": [], "agent_ids": [], "states": [], "from_time": None, "to_time": None}, "cursor": None, "page_size": 25}),
        "list_events": request("list_events", {"filters": event_filters, "cursor": None, "page_size": 25}),
        "query_time_range": request("query_time_range", {"from_time": "2026-08-12T12:00:00Z", "to_time": "2026-08-12T13:00:00Z", "measure": "wall_time", "requested_resolution_minutes": 5}),
        "query_sequence": request("query_sequence", {"focus_agent_id": None, "filters": event_filters, "grouping": "none", "cursor": None, "page_size": 25}),
        "query_coordination": request("query_coordination", {"work_item_ids": [], "agent_ids": [], "cursor": None, "page_size": 25}),
        "get_event_details": request("get_event_details", {"event_id": "evt_0123456789abcdef01234567"}),
        "refresh_snapshot": request("refresh_snapshot", {}),
        "export_snapshot": request("export_snapshot", {"surface": "tauri", "target": "/tmp/report", "replace": False, "mode": None, "include_sqlite_archive": False}),
        "close_snapshot": request("close_snapshot", {}),
    }


def test_parse_input_line_accepts_request_and_cancel_and_rejects_unknown_fields() -> None:
    encoded = json.dumps({
        "protocol_version": 1, "operation_id": OPERATION_ID, "operation": "get_summary",
        "snapshot_id": SNAPSHOT_ID, "arguments": {},
    }).encode() + b"\n"
    assert parse_input_line(encoded) == request("get_summary", {})
    cancel = json.dumps({"protocol_version": 1, "operation_id": OPERATION_ID, "type": "cancel"}).encode() + b"\n"
    assert parse_input_line(cancel) == CancelEnvelope(1, OPERATION_ID)
    with pytest.raises(WorkerProtocolError, match="envelope"):
        parse_input_line(encoded[:-2] + b',"extra":1}\n')
    with pytest.raises(WorkerProtocolError, match="JSON"):
        parse_input_line(b"not-json\n")


def test_operation_bindings_are_exhaustive_and_decoders_construct_exact_types() -> None:
    expected = {
        "preflight_report": PreflightReportRequest, "open_snapshot": OpenSnapshotRequest,
        "get_summary": SnapshotRequest, "list_agents": ListAgentsRequest,
        "list_turns": ListTurnsRequest, "list_events": ListEventsRequest,
        "query_time_range": TimeRangeQueryRequest, "query_sequence": SequenceQueryRequest,
        "query_coordination": CoordinationQueryRequest, "get_event_details": EventDetailsRequest,
        "refresh_snapshot": RefreshSnapshotRequest, "export_snapshot": ExportSnapshotRequest,
        "close_snapshot": CloseSnapshotRequest,
    }
    assert set(OPERATION_BINDINGS) == set(get_args(OperationName)) == set(expected)
    for name, envelope in operation_requests().items():
        assert type(decode_service_request(envelope)) is expected[name]
        assert OPERATION_BINDINGS[name].request_type is expected[name]  # type: ignore[index]
        assert OPERATION_BINDINGS[name].method_name == name  # type: ignore[index]


def test_decoder_rejects_unknown_nested_fields_and_snapshot_mismatch() -> None:
    value = operation_requests()["list_agents"]
    cast(dict[str, object], value.arguments["filters"])["secret_path"] = "/private/value"
    with pytest.raises(WorkerProtocolError, match="arguments"):
        decode_service_request(value)
    with pytest.raises(WorkerProtocolError, match="snapshot"):
        decode_service_request(request("get_summary", {}, None))


def test_dispatch_calls_exact_method_with_context_and_supported_keywords() -> None:
    calls: list[tuple[object, ...]] = []

    class Service:
        def get_summary(self, context: object, value: object, **keywords: object) -> ServiceResult[SummaryResult]:
            calls.append((context, value, keywords))
            return ServiceResult(False, error=ReportError("REPORT_NOT_FOUND", "Missing.", True, OPERATION_ID))

    result = dispatch_service_operation(
        Service(),  # type: ignore[arg-type]
        operation_requests()["get_summary"],
        cancellation=ThreadCancellationToken(__import__("threading").Event()),
        progress=lambda *_: None,
    )
    assert not result.ok
    context, value, keywords = calls[0]
    assert vars(context) if hasattr(context, "__dict__") else context.operation_id == OPERATION_ID  # type: ignore[attr-defined]
    assert type(value) is SnapshotRequest
    assert set(cast(dict[str, object], keywords)) == {"cancellation"}


def test_each_wire_operation_calls_only_its_exact_named_service_method() -> None:
    calls: list[tuple[str, object, object, dict[str, object]]] = []

    class Service:
        def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
            def invoke(context: object, value: object, **keywords: object) -> ServiceResult[object]:
                calls.append((name, context, value, keywords))
                return ServiceResult(False, error=ReportError("REPORT_NOT_FOUND", "Missing.", True, OPERATION_ID))
            return invoke

    for name, envelope in operation_requests().items():
        dispatch_service_operation(
            Service(),  # type: ignore[arg-type]
            envelope,
            cancellation=ThreadCancellationToken(threading.Event()),
            progress=lambda *_: None,
        )
        method, context, value, keywords = calls[-1]
        assert method == name
        assert context.operation_id == OPERATION_ID  # type: ignore[attr-defined]
        assert type(value) is OPERATION_BINDINGS[name].request_type  # type: ignore[index]
        expected = set() if name == "close_snapshot" else {"cancellation"}
        if name in {"preflight_report", "open_snapshot", "refresh_snapshot", "export_snapshot"}:
            expected.add("progress")
        assert set(keywords) == expected


def test_serializer_rejects_wrong_result_and_correlation_before_traversal() -> None:
    envelope = operation_requests()["list_agents"]
    wrong = PageResult(SNAPSHOT_ID, "list_agents", [TurnRow("turn", "agent", NOW, None, "done", 1, "measured")], "d", "agent_id", 25, None)
    with pytest.raises(WorkerProtocolError, match="invalid result"):
        serialize_service_value(envelope, wrong)  # type: ignore[arg-type]
    right_row = AgentRow("agent", None, "worker", "done", NOW, None, "measured")
    mismatch = PageResult("other", "list_agents", [right_row], "d", "agent_id", 25, None)
    with pytest.raises(WorkerProtocolError, match="correlation"):
        serialize_service_value(envelope, mismatch)


def test_serializer_is_deterministic_and_privacy_preserving() -> None:
    value = PreflightResult("opaque", "root", True, False, "rev", 1, 2, 3, 4, 5, 6, None, [WarningRecord("WARN", "Safe")])
    serialized = serialize_service_value(operation_requests()["preflight_report"], value)
    assert list(serialized) == [
        "preflight_token", "root_thread_id", "include_children", "include_collaborators",
        "source_revision", "log_count", "total_bytes", "child_count", "collaborator_count",
        "cached_file_count", "changed_file_count", "known_event_count", "warnings",
    ]
    assert serialized["warnings"] == [{"code": "WARN", "message": "Safe"}]


def test_every_operation_serializes_its_exact_cd002_result_schema() -> None:
    snapshot = SnapshotMetadata(1, SNAPSHOT_ID, "root", True, False, "rev", "parser", "pricing", "formatter", NOW, "live", [])
    page_values = {
        "list_agents": PageResult(SNAPSHOT_ID, "list_agents", [AgentRow("agent", None, "worker", "done", NOW, None, "measured")], "d", "agent_id", 25, None),
        "list_turns": PageResult(SNAPSHOT_ID, "list_turns", [TurnRow("turn", "agent", NOW, None, "done", 1, "measured")], "d", "started_at", 25, None),
        "list_events": PageResult(SNAPSHOT_ID, "list_events", [EventRow("evt_0123456789abcdef01234567", None, "agent", NOW, "message", "Safe", "measured")], "d", "occurred_at", 25, None),
        "query_sequence": PageResult(SNAPSHOT_ID, "query_sequence", [SequenceRow("sequence", NOW, "agent", None, "delegation", "Safe", 1, "derived")], "d", "occurred_at", 25, None),
        "query_coordination": PageResult(SNAPSHOT_ID, "query_coordination", [CoordinationRow("coordination", NOW, None, ["agent"], "claim", "Safe", "derived")], "d", "occurred_at", 25, None),
    }
    values: dict[str, object] = {
        "preflight_report": PreflightResult("opaque", "root", True, False, "rev", 1, 2, 3, 4, 5, 6, None, []),
        "open_snapshot": snapshot,
        "get_summary": SummaryResult(SNAPSHOT_ID, None, "ready", ReportScope("root"), [MetricValue("events", 1, "count", "measured", "events")], ["events"], [], [ActivityItem("evt_0123456789abcdef01234567", NOW, "message", "Safe", "measured")]),
        **page_values,
        "query_time_range": TimeSeriesResult(SNAPSHOT_ID, "wall_time", 5, 5, NOW, NOW, [TimeBucket(NOW, NOW, 1.5, "measured")], ["events"]),
        "get_event_details": EventDetail(SNAPSHOT_ID, "evt_0123456789abcdef01234567", NOW, "message", "Safe", None, None, "measured", ["events"], []),
        "refresh_snapshot": RefreshSnapshotResult(False, snapshot),
        "export_snapshot": ExportResult("directory", Path("/tmp/report"), None, [], []),
        "close_snapshot": CloseSnapshotResult(SNAPSHOT_ID, True),
    }
    assert set(values) == set(operation_requests())
    for operation, value in values.items():
        encoded = serialize_service_value(operation_requests()[operation], value)  # type: ignore[arg-type]
        assert list(encoded) == [field.name for field in fields(value)]  # type: ignore[arg-type]


def test_serializer_rejects_wrong_nested_type_nonfinite_naive_and_bool_integer() -> None:
    envelope = operation_requests()["preflight_report"]
    invalid_values = [
        PreflightResult("opaque", "root", True, False, "rev", True, 2, 3, 4, 5, 6, None, []),
        PreflightResult("opaque", "root", True, False, "rev", 1, 2, 3, 4, 5, 6, None, ["warning"]),  # type: ignore[list-item]
    ]
    for value in invalid_values:
        with pytest.raises(WorkerProtocolError, match="invalid result"):
            serialize_service_value(envelope, value)  # type: ignore[arg-type]

    time_value = TimeSeriesResult(SNAPSHOT_ID, "wall_time", 5, 5, NOW.replace(tzinfo=None), NOW, [], [])
    with pytest.raises(WorkerProtocolError, match="invalid result"):
        serialize_service_value(operation_requests()["query_time_range"], time_value)


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value


def runtime_for(
    service: object,
    *,
    clock: Clock | None = None,
    max_record_bytes: int = 1_048_576,
    max_in_flight: int = 4,
) -> tuple[WorkerRuntime, io.BytesIO]:
    output = io.BytesIO()
    runtime = WorkerRuntime(
        lambda _: service,  # type: ignore[arg-type,return-value]
        WorkerConfig(1, "0.10.2", max_in_flight, max_record_bytes),
        clock=clock or Clock(), stdin=io.BytesIO(), stdout=output, stderr=io.StringIO(),
    )
    runtime._service = service  # type: ignore[assignment,attr-defined]
    return runtime, output


def wait_for_records(output: io.BytesIO, count: int) -> list[dict[str, object]]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        if len(records) >= count:
            return records
        time.sleep(0.005)
    raise AssertionError(f"Expected {count} records, got {output.getvalue()!r}")


def handshake_record(*, protocol: int = 1, package: str = "0.10.2") -> dict[str, object]:
    return {
        "protocol_version": protocol,
        "operation_id": "op_000000000000000000000000",
        "operation": "worker_handshake",
        "snapshot_id": None,
        "arguments": {
            "supervisor_protocol_version": protocol,
            "expected_package_version": package,
            "service_config": {
                "authorized_source_roots": ["/tmp"], "parser_version": "p",
                "pricing_digest": "pricing", "formatter_digest": "formatter",
                "default_page_size": 100, "max_page_size": 500, "max_time_buckets": 2000,
            },
        },
    }


def test_progress_is_monotonic_bounded_coalesced_and_terminal_does_not_bypass_interval() -> None:
    clock = Clock()

    class Service:
        def preflight_report(self, context, value, *, cancellation, progress):  # type: ignore[no-untyped-def]
            progress("scan", 0, 10, "Starting")
            clock.value = 0.020
            progress("scan", 1, 10, "One")
            progress("scan", 2, 10, "Two")
            clock.value = 0.049
            return ServiceResult(False, error=ReportError("REPORT_NOT_FOUND", "Missing.", True, context.operation_id))

    runtime, output = runtime_for(Service(), clock=clock)
    runtime.submit(operation_requests()["preflight_report"])
    records = wait_for_records(output, 2)
    assert [record["type"] for record in records] == ["progress", "error"]
    assert records[0]["completed"] == 0

    with pytest.raises(WorkerProtocolError, match="invalid result"):
        runtime._record_progress(OPERATION_ID, "scan", -1, 10, "Invalid")  # type: ignore[attr-defined]
    runtime.shutdown(wait=True)


def test_progress_emits_at_fifty_milliseconds_and_coalesces_latest_observation() -> None:
    clock = Clock()

    class Service:
        def preflight_report(self, context, value, *, cancellation, progress):  # type: ignore[no-untyped-def]
            progress("scan", 0, 10, "Zero")
            clock.value = 0.010
            progress("scan", 1, 10, "One")
            clock.value = 0.050
            progress("scan", 2, 10, "Two")
            return ServiceResult(False, error=ReportError("REPORT_NOT_FOUND", "Missing.", True, context.operation_id))

    runtime, output = runtime_for(Service(), clock=clock)
    runtime.submit(operation_requests()["preflight_report"])
    records = wait_for_records(output, 3)
    assert [(record["type"], record.get("completed")) for record in records] == [
        ("progress", 0), ("progress", 2), ("error", None)
    ]
    runtime.shutdown(wait=True)


def test_cancel_sets_only_selected_operation_and_service_errors_remain_correlated() -> None:
    started = [threading.Event(), threading.Event()]
    release = threading.Event()
    tokens: list[ThreadCancellationToken] = []

    class Service:
        def get_summary(self, context, value, *, cancellation):  # type: ignore[no-untyped-def]
            index = len(tokens)
            tokens.append(cancellation)
            started[index].set()
            release.wait(2)
            code = "REPORT_CANCELLED" if cancellation.is_cancelled() else "REPORT_NOT_FOUND"
            return ServiceResult(False, error=ReportError(code, "Safe failure.", True, context.operation_id))

    runtime, output = runtime_for(Service())
    first = operation_requests()["get_summary"]
    second = replace(first, operation_id="op_aaaaaaaaaaaaaaaaaaaaaaaa")
    runtime.submit(first)
    runtime.submit(second)
    assert started[0].wait(1) and started[1].wait(1)
    runtime.cancel(CancelEnvelope(1, first.operation_id))
    assert tokens[0].is_cancelled()
    assert not tokens[1].is_cancelled()
    release.set()
    records = wait_for_records(output, 2)
    by_id = {record["operation_id"]: record for record in records}
    assert by_id[first.operation_id]["type"] == "cancelled"
    assert by_id[second.operation_id]["type"] == "error"
    runtime.shutdown(wait=True)


def test_wrong_result_and_oversized_result_become_one_bounded_contract_error() -> None:
    class WrongService:
        def get_summary(self, context, value, *, cancellation):  # type: ignore[no-untyped-def]
            return ServiceResult(True, value=CloseSnapshotResult(SNAPSHOT_ID, True))

    runtime, output = runtime_for(WrongService())
    runtime.submit(operation_requests()["get_summary"])
    records = wait_for_records(output, 1)
    assert records[0]["type"] == "error"
    assert records[0]["error"]["code"] == "REPORT_WORKER_SERVICE_CONTRACT"  # type: ignore[index]
    runtime.shutdown(wait=True)

    class LargeService:
        def preflight_report(self, context, value, *, cancellation, progress):  # type: ignore[no-untyped-def]
            return ServiceResult(True, value=PreflightResult("x" * 2_000, "root", False, False, "rev", 1, 1, 0, 0, 0, 0, None, []))

    runtime, output = runtime_for(LargeService(), max_record_bytes=512)
    runtime.submit(operation_requests()["preflight_report"])
    records = wait_for_records(output, 1)
    assert len(records) == 1
    assert records[0]["error"]["code"] == "REPORT_WORKER_RESULT_TOO_LARGE"  # type: ignore[index]
    runtime.shutdown(wait=True)


def test_capacity_rejects_ordinary_work_but_cancel_remains_available() -> None:
    started = threading.Event()
    release = threading.Event()

    class Service:
        def get_summary(self, context, value, *, cancellation):  # type: ignore[no-untyped-def]
            started.set()
            release.wait(2)
            code = "REPORT_CANCELLED" if cancellation.is_cancelled() else "REPORT_NOT_FOUND"
            return ServiceResult(False, error=ReportError(code, "Safe.", True, context.operation_id))

    runtime, output = runtime_for(Service(), max_in_flight=1)
    first = operation_requests()["get_summary"]
    second = replace(first, operation_id="op_bbbbbbbbbbbbbbbbbbbbbbbb")
    runtime.submit(first)
    assert started.wait(1)
    runtime.submit(second)
    busy = wait_for_records(output, 1)[0]
    assert busy["operation_id"] == second.operation_id
    assert busy["error"]["code"] == "REPORT_WORKER_BUSY"  # type: ignore[index]
    runtime.cancel(CancelEnvelope(1, first.operation_id))
    release.set()
    records = wait_for_records(output, 2)
    assert records[-1]["type"] == "cancelled"
    runtime.shutdown(wait=True)


def test_result_can_win_after_cancellation_and_duplicate_id_is_never_reused() -> None:
    started = threading.Event()
    release = threading.Event()

    class Service:
        def get_summary(self, context, value, *, cancellation):  # type: ignore[no-untyped-def]
            started.set()
            release.wait(2)
            return ServiceResult(True, value=SummaryResult(SNAPSHOT_ID, None, "ready", ReportScope("root"), [], [], [], []))

    runtime, output = runtime_for(Service())
    envelope = operation_requests()["get_summary"]
    runtime.submit(envelope)
    assert started.wait(1)
    runtime.cancel(CancelEnvelope(1, envelope.operation_id))
    release.set()
    assert wait_for_records(output, 1)[0]["type"] == "result"
    with pytest.raises(WorkerProtocolError, match="already been used"):
        runtime.submit(envelope)
    runtime.shutdown(wait=True)


def test_handshake_mismatch_partial_eof_and_output_failure_have_fatal_exit_codes() -> None:
    factory_calls: list[object] = []
    output = io.BytesIO()
    mismatched = handshake_record(package="different")
    runtime = WorkerRuntime(
        lambda config: factory_calls.append(config),  # type: ignore[arg-type,return-value]
        WorkerConfig(1, "0.10.2", 1, 1_048_576), clock=Clock(),
        stdin=io.BytesIO(json.dumps(mismatched).encode() + b"\n"),
        stdout=output, stderr=io.StringIO(),
    )
    assert runtime.run() == 2
    assert factory_calls == []
    assert json.loads(output.getvalue())["error"]["code"] == "REPORT_WORKER_PROTOCOL_MISMATCH"

    runtime = WorkerRuntime(
        lambda _: object(),  # type: ignore[arg-type,return-value]
        WorkerConfig(1, "0.10.2", 1, 1_048_576), clock=Clock(),
        stdin=io.BytesIO(b'{"protocol_version":1'), stdout=io.BytesIO(), stderr=io.StringIO(),
    )
    assert runtime.run() == 2

    class BrokenOutput(io.BytesIO):
        def write(self, value: bytes) -> int:  # type: ignore[override]
            raise OSError("closed")

    runtime = WorkerRuntime(
        lambda _: object(),  # type: ignore[arg-type,return-value]
        WorkerConfig(1, "0.10.2", 1, 1_048_576), clock=Clock(),
        stdin=io.BytesIO(json.dumps(handshake_record()).encode() + b"\n"),
        stdout=BrokenOutput(), stderr=io.StringIO(),
    )
    assert runtime.run() == 3


def test_runtime_handshake_constructs_one_service_and_keeps_stdout_jsonl_only() -> None:
    handshake = {
        "protocol_version": 1,
        "operation_id": "op_000000000000000000000000",
        "operation": "worker_handshake",
        "snapshot_id": None,
        "arguments": {
            "supervisor_protocol_version": 1,
            "expected_package_version": "0.10.2",
            "service_config": {
                "authorized_source_roots": ["/tmp"], "parser_version": "p",
                "pricing_digest": "pricing", "formatter_digest": "formatter",
                "default_page_size": 100, "max_page_size": 500, "max_time_buckets": 2000,
            },
        },
    }
    stdin = io.BytesIO(json.dumps(handshake).encode() + b"\n")
    stdout = io.BytesIO()
    services: list[object] = []

    def factory(config: object) -> object:
        services.append(config)
        return object()

    runtime = WorkerRuntime(
        factory,  # type: ignore[arg-type]
        WorkerConfig(1, "0.10.2", 2, 1_048_576),
        clock=Clock(), stdin=stdin, stdout=stdout, stderr=io.StringIO(),
    )
    assert runtime.run() == 0
    assert len(services) == 1
    records = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert records == [{
        "protocol_version": 1, "operation_id": "op_000000000000000000000000",
        "type": "result", "operation": "worker_handshake", "snapshot_id": None,
        "ok": True, "result": {"worker_protocol_version": 1, "worker_package_version": "0.10.2"},
    }]
