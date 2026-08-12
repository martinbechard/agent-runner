# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Verify the shared report application service contract.
# Design: docs/design/components/CD-002-agent-report-application-service.md

"""Contract tests for the process-local report application service."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any, cast

import pytest

from agent_report.application_service import (
    ActivityItem,
    AgentFilters,
    AgentRow,
    AutomationSurface,
    ApplicationServiceConfig,
    ApplicationServiceDependencies,
    CloseSnapshotRequest,
    CoordinationQueryRequest,
    CoordinationRow,
    DiscoveredScope,
    DiscoveredSource,
    DiscoveryFailure,
    EventDetail,
    EventDetailsRequest,
    EventFilters,
    EventRow,
    ExportResult,
    ExportMode,
    ExportRenderFailure,
    ExportSnapshotRequest,
    ListAgentsRequest,
    ListEventsRequest,
    ListTurnsRequest,
    MetricValue,
    InfrastructureFailure,
    NormalizationFailure,
    OpenSnapshotRequest,
    OperationContext,
    PreflightReportRequest,
    PublicationFailure,
    PublishedRevision,
    QueryFailure,
    QuerySlice,
    RefreshSnapshotRequest,
    ReportScope,
    RepositoryFailure,
    SequenceQueryRequest,
    SequenceRow,
    SnapshotRequest,
    SummaryResult,
    TimeBucket,
    TimeRangeQueryRequest,
    TimeSeriesResult,
    TurnFilters,
    TurnRow,
    resolve_automation_export_mode,
    create_application_service,
    _map_dependency_failure,
)


class _UnusedDependency:
    """Fail if invalid configuration reaches any injected dependency."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"dependency access was not expected: {name}")


class ManualCancellationToken:
    """Allow a test to request cancellation at an exact boundary."""

    def __init__(self, cancelled: bool = False) -> None:
        self.cancelled = cancelled

    def is_cancelled(self) -> bool:
        return self.cancelled


class RecordingProgressSink:
    """Record progress callbacks without interpreting transport envelopes."""

    def __init__(self) -> None:
        self.records: list[tuple[str, int, int | None, str]] = []

    def __call__(
        self, phase: str, completed: int, total: int | None, message: str
    ) -> None:
        self.records.append((phase, completed, total, message))


class FakeClock:
    """Return one deterministic UTC observation time."""

    def __init__(self) -> None:
        self.value = datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc)

    def now_utc(self) -> datetime:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class FakeIdFactory:
    """Return deterministic process-local snapshot IDs and an integrity key."""

    def __init__(self, prefix: str = "snapshot") -> None:
        self.prefix = prefix
        self.count = 0

    def new_snapshot_id(self) -> str:
        self.count += 1
        return f"{self.prefix}-{self.count}"

    def new_token_key(self) -> bytes:
        return (self.prefix.encode("utf-8") + b"-integrity-key-000000000000")[:32]


class RecordingLogger:
    """Record only the bounded fields supplied by the service."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, object]]] = []

    def info(self, event: str, fields: dict[str, object]) -> None:
        self.records.append(("info", event, dict(fields)))

    def error(self, event: str, fields: dict[str, object]) -> None:
        self.records.append(("error", event, dict(fields)))


@dataclass(frozen=True)
class _NormalizedRevision:
    source_revision: str
    privacy_validated: bool = True


@dataclass(frozen=True)
class _ReadHandle:
    revision_id: str
    source_revision: str


@dataclass(frozen=True)
class _StagedExport:
    mode: ExportMode
    stage_id: str = "stage-1"


def _discovered(
    root: Path, scope: ReportScope, revision: str = "source-1"
) -> DiscoveredScope:
    source = root / "rollout.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    return DiscoveredScope(
        scope=scope,
        source_revision=revision,
        sources=(
            DiscoveredSource(
                source_key="source-1",
                authorized_path=source.resolve(),
                source_revision=revision,
                byte_count=3,
                relationship="root",
            ),
        ),
        log_count=1,
        total_bytes=3,
        child_count=int(scope.include_children),
        collaborator_count=int(scope.include_collaborators),
        cached_file_count=1,
        changed_file_count=0,
        warnings=(),
    )


class FakeDiscoveryPort:
    """Return deterministic discovery data and expose preflight and recheck calls."""

    def __init__(self, result: DiscoveredScope) -> None:
        self.result = result
        self.recheck_result = result
        self.preflight_calls = 0
        self.recheck_calls = 0

    def preflight(self, *_args: object) -> DiscoveredScope:
        self.preflight_calls += 1
        return self.result

    def recheck(self, *_args: object) -> DiscoveredScope:
        self.recheck_calls += 1
        return self.recheck_result


class FakeNormalizationPort:
    """Return one observable privacy-valid normalized revision."""

    def __init__(self) -> None:
        self.calls = 0
        self.failure: BaseException | None = None
        self.privacy_validated = True

    def normalize(
        self, discovered: DiscoveredScope, *_args: object
    ) -> _NormalizedRevision:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return _NormalizedRevision(
            discovered.source_revision, privacy_validated=self.privacy_validated
        )


class FakeEventRepositoryPort:
    """Model atomic publication and exact read-handle release counts."""

    def __init__(self) -> None:
        self.known_count: int | None = 7
        self.publish_calls = 0
        self.open_calls = 0
        self.released: list[_ReadHandle] = []
        self.failure: BaseException | None = None
        self.release_failure: BaseException | None = None

    def known_event_count(self, _source_revision: str) -> int | None:
        return self.known_count

    def reuse_or_publish(
        self, revision: _NormalizedRevision, *_args: object
    ) -> PublishedRevision:
        self.publish_calls += 1
        if self.failure is not None:
            raise self.failure
        return PublishedRevision(
            revision_id=f"revision-{self.publish_calls}",
            source_revision=revision.source_revision,
        )

    def open_read(self, revision_id: str) -> _ReadHandle:
        self.open_calls += 1
        source_revision = "source-1" if revision_id == "revision-1" else "source-2"
        return _ReadHandle(revision_id, source_revision)

    def release_read(self, handle: _ReadHandle) -> None:
        self.released.append(handle)
        if self.release_failure is not None:
            raise self.release_failure


class FakeQueryPort:
    """Return bounded query DTOs and optionally hold a read call for race tests."""

    def __init__(self) -> None:
        self.snapshot_id = "snapshot-1"
        self.entered: threading.Event | None = None
        self.resume: threading.Event | None = None
        self.failure: BaseException | None = None
        self.detail_factory: Callable[[str], EventDetail | None] | None = None

    def _hold_or_fail(self) -> None:
        if self.entered is not None:
            self.entered.set()
        if self.resume is not None:
            assert self.resume.wait(timeout=5)
        if self.failure is not None:
            raise self.failure

    def get_summary(
        self, _handle: _ReadHandle, snapshot: Any, _cancellation: object
    ) -> SummaryResult:
        self._hold_or_fail()
        return SummaryResult(
            snapshot_id=snapshot.snapshot_id,
            goal="Verify the shared service",
            state="running",
            scope=ReportScope(snapshot.root_thread_id),
            metrics=(MetricValue("events", 1, "count", "measured", "normalized"),),
            provenance=("normalized",),
            warnings=(),
            recent_activity=(
                ActivityItem(
                    "evt_000000000000000000000001",
                    datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
                    "message",
                    "One bounded event",
                    "measured",
                ),
            ),
        )

    def list_agents(
        self,
        _handle: _ReadHandle,
        _filters: AgentFilters,
        after: str | None,
        _limit: int,
        _cancellation: object,
    ) -> QuerySlice[AgentRow]:
        self._hold_or_fail()
        return QuerySlice(
            items=(
                AgentRow(
                    "agent-1",
                    None,
                    "worker",
                    "running",
                    datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
                    None,
                    "measured",
                ),
            ),
            next_position=None if after else "agent-1",
        )

    def list_turns(
        self,
        _handle: _ReadHandle,
        _filters: TurnFilters,
        _after: str | None,
        _limit: int,
        _cancellation: object,
    ) -> QuerySlice[TurnRow]:
        self._hold_or_fail()
        return QuerySlice(
            items=(
                TurnRow(
                    "turn-1",
                    "agent-1",
                    datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
                    None,
                    "complete",
                    1,
                    "measured",
                ),
            ),
            next_position=None if _after else "turn-1",
        )

    def list_events(
        self,
        _handle: _ReadHandle,
        _filters: EventFilters,
        _after: str | None,
        _limit: int,
        _cancellation: object,
    ) -> QuerySlice[EventRow]:
        self._hold_or_fail()
        return QuerySlice(
            items=(
                EventRow(
                    "evt_000000000000000000000001",
                    "turn-1",
                    "agent-1",
                    datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
                    "message",
                    "One event",
                    "measured",
                ),
            ),
            next_position=None,
        )

    def query_time_range(
        self,
        _handle: _ReadHandle,
        request: TimeRangeQueryRequest,
        actual: int,
        _cancellation: object,
    ) -> TimeSeriesResult:
        self._hold_or_fail()
        return TimeSeriesResult(
            snapshot_id=request.snapshot_id,
            measure=request.measure,
            requested_resolution_minutes=request.requested_resolution_minutes,
            actual_resolution_minutes=actual,
            from_time=request.from_time,
            to_time=request.to_time,
            buckets=(TimeBucket(request.from_time, request.to_time, 1, "measured"),),
            provenance=("normalized",),
        )

    def query_sequence(
        self,
        _handle: _ReadHandle,
        request: SequenceQueryRequest,
        _after: str | None,
        _cancellation: object,
    ) -> QuerySlice[SequenceRow]:
        self._hold_or_fail()
        return QuerySlice(
            items=(
                SequenceRow(
                    "sequence-1",
                    datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
                    "agent-1",
                    "agent-2",
                    "delegation",
                    "Delegated",
                    1,
                    "measured",
                ),
            ),
            next_position=None if _after else "sequence-1",
        )

    def query_coordination(
        self,
        _handle: _ReadHandle,
        request: CoordinationQueryRequest,
        _after: str | None,
        _cancellation: object,
    ) -> QuerySlice[CoordinationRow]:
        self._hold_or_fail()
        return QuerySlice(
            items=(
                CoordinationRow(
                    "coordination-1",
                    datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
                    "work-1",
                    ("agent-1",),
                    "decision from prose",
                    "Selected",
                    "derived",
                ),
            ),
            next_position=None,
        )

    def get_event_details(
        self, _handle: _ReadHandle, event_id: str, _cancellation: object
    ) -> EventDetail | None:
        self._hold_or_fail()
        if self.detail_factory is not None:
            return self.detail_factory(event_id)
        if event_id.endswith("0"):
            return None
        return EventDetail(
            snapshot_id=self.snapshot_id,
            event_id=event_id,
            occurred_at=datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
            kind="message",
            summary="One event",
            bounded_arguments="{}",
            bounded_result="{}",
            evidence="measured",
            provenance=("normalized",),
            redactions=(),
        )


class FakeExportRendererPort:
    """Record resolved export requests without owning publication."""

    def __init__(self) -> None:
        self.requests: list[Any] = []
        self.entered: threading.Event | None = None
        self.resume: threading.Event | None = None

    def stage(
        self, _handle: _ReadHandle, request: Any, *_args: object
    ) -> _StagedExport:
        self.requests.append(request)
        if self.entered is not None:
            self.entered.set()
        if self.resume is not None:
            assert self.resume.wait(timeout=5)
        return _StagedExport(request.mode)


class FakePublicationPort:
    """Record atomic publication and cleanup attempts."""

    def __init__(self) -> None:
        self.published: list[tuple[_StagedExport, Path, bool]] = []
        self.discarded: list[_StagedExport] = []
        self.failure: BaseException | None = None
        self.discard_failure: BaseException | None = None

    def publish(
        self, staged: _StagedExport, target: Path, replace: bool, _cancellation: object
    ) -> ExportResult:
        if self.failure is not None:
            raise self.failure
        self.published.append((staged, target, replace))
        return ExportResult(staged.mode, target, "manifest-1", (), ())

    def discard(self, staged: _StagedExport) -> None:
        self.discarded.append(staged)
        if self.discard_failure is not None:
            raise self.discard_failure


@dataclass
class _ServiceFixture:
    service: Any
    discovery: FakeDiscoveryPort
    normalization: FakeNormalizationPort
    repository: FakeEventRepositoryPort
    queries: FakeQueryPort
    exporter: FakeExportRendererPort
    publisher: FakePublicationPort
    clock: FakeClock


def _service_fixture(tmp_path: Path, *, prefix: str = "snapshot") -> _ServiceFixture:
    tmp_path.mkdir(parents=True, exist_ok=True)
    scope = ReportScope("thread-1")
    discovery = FakeDiscoveryPort(_discovered(tmp_path, scope))
    normalization = FakeNormalizationPort()
    repository = FakeEventRepositoryPort()
    queries = FakeQueryPort()
    exporter = FakeExportRendererPort()
    publisher = FakePublicationPort()
    clock = FakeClock()
    service = create_application_service(
        ApplicationServiceConfig(
            authorized_source_roots=(tmp_path.resolve(),),
            parser_version="parser-1",
            pricing_digest="a" * 64,
            formatter_digest="b" * 64,
        ),
        ApplicationServiceDependencies(
            discovery=discovery,
            normalization=normalization,
            repository=repository,
            queries=queries,
            exporter=exporter,
            publisher=publisher,
            clock=clock,
            ids=FakeIdFactory(prefix),
            logger=RecordingLogger(),
        ),
    )
    return _ServiceFixture(
        service,
        discovery,
        normalization,
        repository,
        queries,
        exporter,
        publisher,
        clock,
    )


def _open_snapshot(fixture: _ServiceFixture) -> str:
    cancellation = ManualCancellationToken()
    preflight = fixture.service.preflight_report(
        OperationContext(1, "preflight"),
        PreflightReportRequest(ReportScope("thread-1")),
        cancellation=cancellation,
    )
    assert preflight.ok is True
    opened = fixture.service.open_snapshot(
        OperationContext(1, "open"),
        OpenSnapshotRequest(ReportScope("thread-1"), preflight.value.preflight_token),
        cancellation=cancellation,
    )
    assert opened.ok is True
    fixture.queries.snapshot_id = opened.value.snapshot_id
    return opened.value.snapshot_id


def _unused_dependencies() -> ApplicationServiceDependencies:
    dependency = _UnusedDependency()
    return ApplicationServiceDependencies(
        discovery=dependency,
        normalization=dependency,
        repository=dependency,
        queries=dependency,
        exporter=dependency,
        publisher=dependency,
        clock=dependency,
        ids=dependency,
        logger=dependency,
    )


def test_factory_rejects_invalid_configuration_before_dependency_work(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="authorized source root"):
        create_application_service(
            ApplicationServiceConfig(
                authorized_source_roots=(tmp_path / "missing",),
                parser_version="parser-1",
                pricing_digest="a" * 64,
                formatter_digest="b" * 64,
            ),
            _unused_dependencies(),
        )


@pytest.mark.parametrize("surface", ["tauri", "cli", "mcp"])
def test_tauri_cli_and_mcp_omitted_export_mode_resolves_to_directory(
    surface: AutomationSurface,
) -> None:
    result = resolve_automation_export_mode(surface, None)

    assert result.ok is True
    assert result.value == "directory"
    assert result.error is None


def test_summary_export_requires_explicit_mode() -> None:
    result = resolve_automation_export_mode("mcp", "summary")

    assert result.ok is True
    assert result.value == "summary"


def test_unsupported_codex_export_mode_is_rejected_before_rendering() -> None:
    result = resolve_automation_export_mode("mcp", cast(Any, "legacy-full"))

    assert result.ok is False
    assert result.value is None
    assert result.error is not None
    assert result.error.code == "REPORT_INVALID_REQUEST"


def test_preflight_defaults_to_root_only_and_keeps_relationship_flags_independent(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    scopes = (
        ReportScope("thread-1"),
        ReportScope("thread-1", include_children=True),
        ReportScope("thread-1", include_collaborators=True),
        ReportScope("thread-1", include_children=True, include_collaborators=True),
    )
    results = []
    for index, scope in enumerate(scopes):
        fixture.discovery.result = _discovered(tmp_path, scope)
        results.append(
            fixture.service.preflight_report(
                OperationContext(1, f"preflight-{index}"),
                PreflightReportRequest(scope),
                cancellation=ManualCancellationToken(),
            )
        )

    assert ReportScope("thread-1") == ReportScope(
        "thread-1", include_children=False, include_collaborators=False
    )
    assert {
        (result.value.include_children, result.value.include_collaborators)
        for result in results
    } == {(False, False), (True, False), (False, True), (True, True)}


def test_process_local_composition_has_no_shared_mutable_state(tmp_path: Path) -> None:
    first = _service_fixture(tmp_path / "first", prefix="first")
    second = _service_fixture(tmp_path / "second", prefix="second")
    first_snapshot = _open_snapshot(first)

    result = second.service.get_summary(
        OperationContext(1, "summary"),
        SnapshotRequest(first_snapshot),
        cancellation=ManualCancellationToken(),
    )

    assert result.error is not None
    assert result.error.code == "REPORT_SNAPSHOT_NOT_FOUND"
    assert second.repository.open_calls == 0


def test_preflight_returns_bounded_counts_without_snapshot_mutation(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)

    result = fixture.service.preflight_report(
        OperationContext(1, "preflight"),
        PreflightReportRequest(ReportScope("thread-1")),
        cancellation=ManualCancellationToken(),
    )

    assert result.ok is True
    assert result.value.log_count == 1
    assert result.value.known_event_count == 7
    assert fixture.normalization.calls == 0
    assert fixture.repository.publish_calls == 0
    assert fixture.repository.open_calls == 0


def test_preflight_cancellation_returns_no_token_or_snapshot(tmp_path: Path) -> None:
    fixture = _service_fixture(tmp_path)

    result = fixture.service.preflight_report(
        OperationContext(1, "preflight"),
        PreflightReportRequest(ReportScope("thread-1")),
        cancellation=ManualCancellationToken(cancelled=True),
    )

    assert result.error is not None
    assert result.error.code == "REPORT_CANCELLED"
    assert fixture.discovery.preflight_calls == 0
    assert fixture.repository.open_calls == 0


def test_preflight_token_is_short_and_unknown_tokens_are_rejected(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    preflight = fixture.service.preflight_report(
        OperationContext(1, "preflight"),
        PreflightReportRequest(ReportScope("thread-1")),
        cancellation=ManualCancellationToken(),
    )

    unknown = fixture.service.open_snapshot(
        OperationContext(1, "open-unknown"),
        OpenSnapshotRequest(ReportScope("thread-1"), "x" * 43),
        cancellation=ManualCancellationToken(),
    )

    assert len(preflight.value.preflight_token.encode("utf-8")) <= 256
    assert unknown.error.code == "REPORT_SCOPE_CONFLICT"
    assert unknown.error.preflight_required is True
    assert fixture.discovery.recheck_calls == 0


def test_preflight_token_expires_before_snapshot_work(tmp_path: Path) -> None:
    fixture = _service_fixture(tmp_path)
    preflight = fixture.service.preflight_report(
        OperationContext(1, "preflight"),
        PreflightReportRequest(ReportScope("thread-1")),
        cancellation=ManualCancellationToken(),
    )
    fixture.clock.advance(seconds=301)

    expired = fixture.service.open_snapshot(
        OperationContext(1, "open-expired"),
        OpenSnapshotRequest(ReportScope("thread-1"), preflight.value.preflight_token),
        cancellation=ManualCancellationToken(),
    )

    assert expired.error.code == "REPORT_SCOPE_CONFLICT"
    assert expired.error.preflight_required is True
    assert fixture.discovery.recheck_calls == 0
    assert fixture.normalization.calls == 0


def test_preflight_token_is_consumed_and_cannot_be_reused(tmp_path: Path) -> None:
    fixture = _service_fixture(tmp_path)
    preflight = fixture.service.preflight_report(
        OperationContext(1, "preflight"),
        PreflightReportRequest(ReportScope("thread-1")),
        cancellation=ManualCancellationToken(),
    )
    request = OpenSnapshotRequest(
        ReportScope("thread-1"), preflight.value.preflight_token
    )

    first = fixture.service.open_snapshot(
        OperationContext(1, "open-first"),
        request,
        cancellation=ManualCancellationToken(),
    )
    reused = fixture.service.open_snapshot(
        OperationContext(1, "open-reused"),
        request,
        cancellation=ManualCancellationToken(),
    )

    assert first.ok is True
    assert reused.error.code == "REPORT_SCOPE_CONFLICT"
    assert reused.error.preflight_required is True
    assert fixture.discovery.recheck_calls == 1


def test_open_snapshot_rejects_changed_source_revision_with_scope_conflict(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    preflight = fixture.service.preflight_report(
        OperationContext(1, "preflight"),
        PreflightReportRequest(ReportScope("thread-1")),
        cancellation=ManualCancellationToken(),
    )
    fixture.discovery.recheck_result = _discovered(
        tmp_path, ReportScope("thread-1"), "source-2"
    )

    result = fixture.service.open_snapshot(
        OperationContext(1, "open"),
        OpenSnapshotRequest(ReportScope("thread-1"), preflight.value.preflight_token),
        cancellation=ManualCancellationToken(),
    )

    assert result.error is not None
    assert result.error.code == "REPORT_SCOPE_CONFLICT"
    assert result.error.current_source_revision == "source-2"
    assert result.error.preflight_required is True
    assert fixture.normalization.calls == 0
    assert fixture.repository.publish_calls == 0


def test_open_snapshot_publishes_state_only_after_repository_commit(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)

    summary = fixture.service.get_summary(
        OperationContext(1, "summary"),
        SnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )

    assert fixture.repository.publish_calls == 1
    assert fixture.repository.open_calls == 1
    assert summary.ok is True
    assert summary.value.snapshot_id == snapshot_id


def test_open_snapshot_privacy_failure_publishes_no_revision_or_snapshot(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    fixture.normalization.privacy_validated = False
    preflight = fixture.service.preflight_report(
        OperationContext(1, "preflight"),
        PreflightReportRequest(ReportScope("thread-1")),
        cancellation=ManualCancellationToken(),
    )

    result = fixture.service.open_snapshot(
        OperationContext(1, "open"),
        OpenSnapshotRequest(ReportScope("thread-1"), preflight.value.preflight_token),
        cancellation=ManualCancellationToken(),
    )

    assert result.error.code == "REPORT_PRIVACY_FAILED"
    assert fixture.repository.publish_calls == 0
    assert fixture.repository.open_calls == 0


def test_get_summary_is_bounded_sanitized_and_read_only(tmp_path: Path) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)

    result = fixture.service.get_summary(
        OperationContext(1, "summary"),
        SnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )

    assert result.ok is True
    assert isinstance(result.value.metrics, tuple)
    assert isinstance(result.value.provenance, tuple)
    assert isinstance(result.value.recent_activity, tuple)
    assert fixture.repository.publish_calls == 1
    assert fixture.repository.released == []


def test_list_agents_enforces_page_bounds_and_canonical_order(tmp_path: Path) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)

    invalid = fixture.service.list_agents(
        OperationContext(1, "agents-invalid"),
        ListAgentsRequest(snapshot_id, page_size=501),
        cancellation=ManualCancellationToken(),
    )
    valid = fixture.service.list_agents(
        OperationContext(1, "agents"),
        ListAgentsRequest(snapshot_id, page_size=1),
        cancellation=ManualCancellationToken(),
    )

    assert invalid.error is not None
    assert invalid.error.code == "REPORT_INVALID_REQUEST"
    assert valid.ok is True
    assert valid.value.applied_sort == "agent.started_at, agent.agent_id"
    assert isinstance(valid.value.items, tuple)
    assert len(valid.value.next_cursor.encode("utf-8")) <= 256


def test_list_turns_cursor_binds_snapshot_revision_filters_sort_and_page_size(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    first = fixture.service.list_turns(
        OperationContext(1, "turns-first"),
        ListTurnsRequest(
            snapshot_id, filters=TurnFilters(states=("complete",)), page_size=1
        ),
        cancellation=ManualCancellationToken(),
    )

    conflict = fixture.service.list_turns(
        OperationContext(1, "turns-next"),
        ListTurnsRequest(
            snapshot_id,
            filters=TurnFilters(states=("running",)),
            cursor=first.value.next_cursor,
            page_size=1,
        ),
        cancellation=ManualCancellationToken(),
    )

    assert first.value.next_cursor is not None
    assert conflict.error is not None
    assert conflict.error.code == "REPORT_CURSOR_CONFLICT"
    assert conflict.error.restart_from_first_page is True


def test_list_events_rejects_cross_operation_and_cross_snapshot_cursors(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path / "first")
    snapshot_id = _open_snapshot(fixture)
    agents = fixture.service.list_agents(
        OperationContext(1, "agents"),
        ListAgentsRequest(snapshot_id, page_size=1),
        cancellation=ManualCancellationToken(),
    )

    cross_operation = fixture.service.list_events(
        OperationContext(1, "events"),
        ListEventsRequest(snapshot_id, cursor=agents.value.next_cursor, page_size=1),
        cancellation=ManualCancellationToken(),
    )
    second = _service_fixture(tmp_path / "second", prefix="second")
    second_snapshot = _open_snapshot(second)
    cross_snapshot = second.service.list_agents(
        OperationContext(1, "agents-second"),
        ListAgentsRequest(
            second_snapshot, cursor=agents.value.next_cursor, page_size=1
        ),
        cancellation=ManualCancellationToken(),
    )

    assert cross_operation.error.code == "REPORT_CURSOR_CONFLICT"
    assert cross_snapshot.error.code == "REPORT_CURSOR_CONFLICT"


def test_query_time_range_coarsens_to_at_most_two_thousand_buckets(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)

    result = fixture.service.query_time_range(
        OperationContext(1, "time"),
        TimeRangeQueryRequest(
            snapshot_id,
            start,
            start + timedelta(minutes=4_001),
            "wall_time",
            1,
        ),
        cancellation=ManualCancellationToken(),
    )

    assert result.ok is True
    assert result.value.requested_resolution_minutes == 1
    assert result.value.actual_resolution_minutes == 3
    assert len(result.value.buckets) <= 2_000


def test_query_sequence_binds_focus_filters_grouping_and_cursor(tmp_path: Path) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    first = fixture.service.query_sequence(
        OperationContext(1, "sequence-first"),
        SequenceQueryRequest(snapshot_id, focus_agent_id="agent-1", page_size=1),
        cancellation=ManualCancellationToken(),
    )

    conflict = fixture.service.query_sequence(
        OperationContext(1, "sequence-next"),
        SequenceQueryRequest(
            snapshot_id,
            focus_agent_id="agent-2",
            cursor=first.value.next_cursor,
            page_size=1,
        ),
        cancellation=ManualCancellationToken(),
    )

    assert first.value.next_cursor is not None
    assert conflict.error.code == "REPORT_CURSOR_CONFLICT"


def test_query_coordination_labels_prose_derived_decisions_as_inferred(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)

    result = fixture.service.query_coordination(
        OperationContext(1, "coordination"),
        CoordinationQueryRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )

    assert result.ok is True
    assert result.value.items[0].evidence == "inferred"
    assert isinstance(result.value.items[0].agent_ids, tuple)


def test_get_event_details_not_found_preserves_open_snapshot(tmp_path: Path) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)

    missing = fixture.service.get_event_details(
        OperationContext(1, "detail"),
        EventDetailsRequest(snapshot_id, "evt_000000000000000000000000"),
        cancellation=ManualCancellationToken(),
    )
    summary = fixture.service.get_summary(
        OperationContext(1, "summary"),
        SnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )

    assert missing.error.code == "REPORT_EVENT_NOT_FOUND"
    assert summary.ok is True


def test_get_event_details_is_lazy_bounded_redacted_and_path_free(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)

    def oversized(event_id: str) -> EventDetail:
        return EventDetail(
            snapshot_id=snapshot_id,
            event_id=event_id,
            occurred_at=datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
            kind="message",
            summary="One event",
            bounded_arguments="x" * 16_385,
            bounded_result="{}",
            evidence="measured",
            provenance=("normalized",),
            redactions=(),
        )

    fixture.queries.detail_factory = oversized
    result = fixture.service.get_event_details(
        OperationContext(1, "detail"),
        EventDetailsRequest(snapshot_id, "evt_000000000000000000000001"),
        cancellation=ManualCancellationToken(),
    )

    assert result.ok is True
    assert result.value.bounded_arguments is None
    assert "omitted" in result.value.redactions[-1]


def test_refresh_unchanged_returns_existing_binding_without_normalization(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)

    result = fixture.service.refresh_snapshot(
        OperationContext(1, "refresh"),
        RefreshSnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )

    assert result.ok is True
    assert result.value.changed is False
    assert fixture.normalization.calls == 1
    assert fixture.repository.publish_calls == 1


def test_refresh_swaps_binding_only_after_new_revision_commit(tmp_path: Path) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    fixture.discovery.recheck_result = _discovered(
        tmp_path, ReportScope("thread-1"), "source-2"
    )

    result = fixture.service.refresh_snapshot(
        OperationContext(1, "refresh"),
        RefreshSnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )

    assert result.ok is True
    assert result.value.changed is True
    assert result.value.snapshot.source_revision == "source-2"
    assert fixture.repository.publish_calls == 2
    assert [handle.revision_id for handle in fixture.repository.released] == [
        "revision-1"
    ]


def test_refresh_failure_or_cancellation_preserves_last_coherent_binding(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    fixture.discovery.recheck_result = _discovered(
        tmp_path, ReportScope("thread-1"), "source-2"
    )
    fixture.normalization.failure = NormalizationFailure(
        "parse", "The changed revision could not be normalized.", True
    )

    failed = fixture.service.refresh_snapshot(
        OperationContext(1, "refresh"),
        RefreshSnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )
    fixture.normalization.failure = None
    summary = fixture.service.get_summary(
        OperationContext(1, "summary"),
        SnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )

    assert failed.error.code == "REPORT_GENERATION_FAILED"
    assert summary.ok is True
    assert fixture.repository.publish_calls == 1
    assert fixture.repository.released == []


def test_export_validates_mode_specific_options_before_rendering(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)

    result = fixture.service.export_snapshot(
        OperationContext(1, "export"),
        ExportSnapshotRequest(
            snapshot_id,
            "mcp",
            (tmp_path / "summary.html").resolve(),
            False,
            mode="summary",
            include_sqlite_archive=True,
        ),
        cancellation=ManualCancellationToken(),
    )

    assert result.error.code == "REPORT_INVALID_REQUEST"
    assert fixture.exporter.requests == []
    assert fixture.publisher.published == []


def test_export_reports_success_only_after_atomic_publication(tmp_path: Path) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    target = (tmp_path / "bundle").resolve()

    result = fixture.service.export_snapshot(
        OperationContext(1, "export"),
        ExportSnapshotRequest(snapshot_id, "cli", target, False),
        cancellation=ManualCancellationToken(),
    )

    assert result.ok is True
    assert result.value.mode == "directory"
    assert result.value.published_target == target
    assert fixture.exporter.requests[0].mode == "directory"
    assert fixture.publisher.published[0][1] == target


def test_export_failure_or_cancellation_preserves_prior_target_and_snapshot(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    fixture.publisher.failure = PublicationFailure(
        "write", "safe publication failure", True
    )

    failed = fixture.service.export_snapshot(
        OperationContext(1, "export"),
        ExportSnapshotRequest(
            snapshot_id, "mcp", (tmp_path / "bundle").resolve(), False
        ),
        cancellation=ManualCancellationToken(),
    )
    summary = fixture.service.get_summary(
        OperationContext(1, "summary"),
        SnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )

    assert failed.error is not None
    assert fixture.publisher.published == []
    assert len(fixture.publisher.discarded) == 1
    assert summary.ok is True


def test_concurrent_snapshot_mutation_returns_snapshot_conflict_without_waiting(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    fixture.exporter.entered = threading.Event()
    fixture.exporter.resume = threading.Event()
    thread = threading.Thread(
        target=lambda: fixture.service.export_snapshot(
            OperationContext(1, "export"),
            ExportSnapshotRequest(
                snapshot_id, "mcp", (tmp_path / "bundle").resolve(), False
            ),
            cancellation=ManualCancellationToken(),
        )
    )
    thread.start()
    assert fixture.exporter.entered.wait(timeout=5)

    result = fixture.service.refresh_snapshot(
        OperationContext(1, "refresh"),
        RefreshSnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )
    fixture.exporter.resume.set()
    thread.join(timeout=5)

    assert result.error.code == "REPORT_SNAPSHOT_CONFLICT"
    assert fixture.discovery.recheck_calls == 1


def test_close_snapshot_is_idempotent_for_unknown_well_formed_id(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)

    result = fixture.service.close_snapshot(
        OperationContext(1, "close"), CloseSnapshotRequest("snapshot-unknown")
    )

    assert result.ok is True
    assert result.value.closed is False


def test_close_snapshot_releases_handle_without_purging_derived_data(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)

    result = fixture.service.close_snapshot(
        OperationContext(1, "close"), CloseSnapshotRequest(snapshot_id)
    )

    assert result.value.closed is True
    assert fixture.repository.publish_calls == 1
    assert len(fixture.repository.released) == 1


def test_close_snapshot_retry_releases_handle_once_after_reader_finishes(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    fixture.queries.entered = threading.Event()
    fixture.queries.resume = threading.Event()
    result_box: list[object] = []

    thread = threading.Thread(
        target=lambda: result_box.append(
            fixture.service.get_summary(
                OperationContext(1, "summary"),
                SnapshotRequest(snapshot_id),
                cancellation=ManualCancellationToken(),
            )
        )
    )
    thread.start()
    assert fixture.queries.entered.wait(timeout=5)
    conflict = fixture.service.close_snapshot(
        OperationContext(1, "close-conflict"), CloseSnapshotRequest(snapshot_id)
    )
    fixture.queries.resume.set()
    thread.join(timeout=5)
    closed = fixture.service.close_snapshot(
        OperationContext(1, "close-retry"), CloseSnapshotRequest(snapshot_id)
    )

    assert conflict.error.code == "REPORT_SNAPSHOT_CONFLICT"
    assert result_box[0].ok is True
    assert closed.value.closed is True
    assert len(fixture.repository.released) == 1


def test_active_reader_rejects_refresh_and_export_without_side_effects(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    fixture.queries.entered = threading.Event()
    fixture.queries.resume = threading.Event()
    thread = threading.Thread(
        target=lambda: fixture.service.get_summary(
            OperationContext(1, "summary"),
            SnapshotRequest(snapshot_id),
            cancellation=ManualCancellationToken(),
        )
    )
    thread.start()
    assert fixture.queries.entered.wait(timeout=5)

    refresh = fixture.service.refresh_snapshot(
        OperationContext(1, "refresh"),
        RefreshSnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )
    export = fixture.service.export_snapshot(
        OperationContext(1, "export"),
        ExportSnapshotRequest(
            snapshot_id, "mcp", (tmp_path / "bundle").resolve(), False
        ),
        cancellation=ManualCancellationToken(),
    )
    fixture.queries.resume.set()
    thread.join(timeout=5)

    assert refresh.error.code == "REPORT_SNAPSHOT_CONFLICT"
    assert export.error.code == "REPORT_SNAPSHOT_CONFLICT"
    assert fixture.discovery.recheck_calls == 1  # open only
    assert fixture.exporter.requests == []


def test_every_typed_dependency_failure_maps_exhaustively_and_safely() -> None:
    cases = (
        (DiscoveryFailure("not_found", "safe", True), "REPORT_NOT_FOUND"),
        (DiscoveryFailure("invalid_root", "safe", True), "REPORT_INVALID_REQUEST"),
        (DiscoveryFailure("protocol", "safe", True), "REPORT_DISCOVERY_FAILED"),
        (DiscoveryFailure("read", "safe", True), "REPORT_DISCOVERY_FAILED"),
        (DiscoveryFailure("cancelled", "safe", True), "REPORT_CANCELLED"),
        (
            NormalizationFailure("source_conflict", "safe", True),
            "REPORT_SCOPE_CONFLICT",
        ),
        (NormalizationFailure("parse", "safe", True), "REPORT_GENERATION_FAILED"),
        (NormalizationFailure("privacy", "safe", False), "REPORT_PRIVACY_FAILED"),
        (NormalizationFailure("cancelled", "safe", True), "REPORT_CANCELLED"),
        (RepositoryFailure("schema_newer", "safe", True), "REPORT_SNAPSHOT_CONFLICT"),
        (
            RepositoryFailure("binding_conflict", "safe", True),
            "REPORT_SNAPSHOT_CONFLICT",
        ),
        (RepositoryFailure("read", "safe", True), "REPORT_GENERATION_FAILED"),
        (RepositoryFailure("publish", "safe", True), "REPORT_GENERATION_FAILED"),
        (RepositoryFailure("cancelled", "safe", True), "REPORT_CANCELLED"),
        (QueryFailure("invalid_request", "safe", True), "REPORT_INVALID_REQUEST"),
        (QueryFailure("event_not_found", "safe", True), "REPORT_EVENT_NOT_FOUND"),
        (QueryFailure("read", "safe", True), "REPORT_GENERATION_FAILED"),
        (QueryFailure("privacy", "safe", False), "REPORT_PRIVACY_FAILED"),
        (QueryFailure("cancelled", "safe", True), "REPORT_CANCELLED"),
        (
            ExportRenderFailure("invalid_request", "safe", True),
            "REPORT_INVALID_REQUEST",
        ),
        (ExportRenderFailure("privacy", "safe", False), "REPORT_PRIVACY_FAILED"),
        (ExportRenderFailure("render", "safe", True), "REPORT_EXPORT_FAILED"),
        (ExportRenderFailure("cancelled", "safe", True), "REPORT_CANCELLED"),
        (
            PublicationFailure("unauthorized_target", "safe", True),
            "REPORT_INVALID_REQUEST",
        ),
        (
            PublicationFailure("replace_required", "safe", True),
            "REPORT_INVALID_REQUEST",
        ),
        (PublicationFailure("write", "safe", True), "REPORT_WRITE_FAILED"),
        (PublicationFailure("cancelled", "safe", True), "REPORT_CANCELLED"),
        (InfrastructureFailure("clock", "safe"), "REPORT_INTERNAL_ERROR"),
        (InfrastructureFailure("id_factory", "safe"), "REPORT_INTERNAL_ERROR"),
        (InfrastructureFailure("logging", "safe"), "REPORT_INTERNAL_ERROR"),
    )

    mapped = tuple(
        _map_dependency_failure("operation-1", failure) for failure, _ in cases
    )

    assert tuple(error.code for error in mapped) == tuple(
        expected for _, expected in cases
    )
    assert all(error.message == "safe" for error in mapped)
    assert all(error.operation_id == "operation-1" for error in mapped)


def test_cleanup_failure_never_replaces_primary_error_or_discloses_path(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    fixture.publisher.failure = PublicationFailure(
        "write", "The authorized target could not be written.", True
    )
    fixture.publisher.discard_failure = PublicationFailure(
        "write", "private staging path /private/stage", False
    )

    result = fixture.service.export_snapshot(
        OperationContext(1, "export"),
        ExportSnapshotRequest(
            snapshot_id, "mcp", (tmp_path / "bundle").resolve(), False
        ),
        cancellation=ManualCancellationToken(),
    )

    assert result.error.code == "REPORT_WRITE_FAILED"
    assert result.error.message == "The authorized target could not be written."
    assert "/private/stage" not in result.error.message


def test_structured_errors_never_disclose_source_cache_staging_or_raw_content(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    fixture.queries.failure = ValueError(
        "raw transcript at /private/cache/state.sqlite"
    )

    result = fixture.service.get_summary(
        OperationContext(1, "summary"),
        SnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )

    assert result.error.code == "REPORT_INTERNAL_ERROR"
    assert result.error.message == "The report operation failed unexpectedly."
    assert "private" not in result.error.message


def test_service_close_rejects_new_leases_waits_for_active_work_and_releases_once(
    tmp_path: Path,
) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)
    fixture.queries.entered = threading.Event()
    fixture.queries.resume = threading.Event()
    query_thread = threading.Thread(
        target=lambda: fixture.service.get_summary(
            OperationContext(1, "summary-active"),
            SnapshotRequest(snapshot_id),
            cancellation=ManualCancellationToken(),
        )
    )
    query_thread.start()
    assert fixture.queries.entered.wait(timeout=5)
    close_thread = threading.Thread(target=fixture.service.close)
    close_thread.start()
    with fixture.service._state_changed:
        assert fixture.service._state_changed.wait_for(
            lambda: fixture.service._closed, timeout=5
        )

    rejected = fixture.service.get_summary(
        OperationContext(1, "summary-new"),
        SnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )
    assert close_thread.is_alive()
    fixture.queries.resume.set()
    query_thread.join(timeout=5)
    close_thread.join(timeout=5)

    assert rejected.error.code == "REPORT_SNAPSHOT_CONFLICT"
    assert len(fixture.repository.released) == 1


def test_close_stops_new_work_and_releases_all_handles(tmp_path: Path) -> None:
    fixture = _service_fixture(tmp_path)
    snapshot_id = _open_snapshot(fixture)

    fixture.service.close()
    result = fixture.service.get_summary(
        OperationContext(1, "summary"),
        SnapshotRequest(snapshot_id),
        cancellation=ManualCancellationToken(),
    )

    assert result.error.code == "REPORT_SNAPSHOT_CONFLICT"
    assert result.error.recoverable is False
    assert len(fixture.repository.released) == 1
