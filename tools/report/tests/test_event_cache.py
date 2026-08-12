# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Verify the normalized Agent Report event cache contract.
# Design: docs/design/components/CD-003-agent-report-normalized-event-cache.md

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from agent_report.event_cache import (
    DEFAULT_MAX_BYTES,
    PRIVACY_REGISTRY_VERSION,
    CacheCancelledError,
    CacheClosedError,
    CacheCursorConflictError,
    CachePrivacyViolationError,
    CacheRevisionConflictError,
    CacheSchemaTooNewError,
    CursorBinding,
    CursorConflictReason,
    CursorOperation,
    EventCachePolicy,
    EventFilter,
    EventQuery,
    EventRepository,
    EvidenceMethod,
    NormalizedDiagnostic,
    NormalizedEventRecord,
    PurgeRequest,
    RecoveryAction,
    SnapshotBindingInput,
    SnapshotId,
    SnapshotState,
    SourceKey,
    SourceRevision,
    SourceRevisionDigest,
    source_key_for_path,
)

UTC = timezone.utc


def _source(seed: str = "a", *, mtime_ns: int = 1) -> SourceRevision:
    return SourceRevision(
        SourceKey(hashlib.sha256(f"source-{seed}".encode()).hexdigest()),
        SourceRevisionDigest(hashlib.sha256(f"revision-{seed}".encode()).hexdigest()),
        100,
        mtime_ns,
        "parser-v1",
        PRIVACY_REGISTRY_VERSION,
    )


def _record(ordinal: int = 0, *, summary: str | None = "safe") -> NormalizedEventRecord:
    return NormalizedEventRecord(
        source_ordinal=ordinal,
        timestamp_utc=datetime(2026, 8, 12, 12, 0, ordinal, tzinfo=UTC),
        kind="tool",
        agent_id="agent",
        turn_id="turn",
        work_item_id="work",
        tool_name="read",
        model="model",
        status="complete",
        evidence_method=EvidenceMethod.MEASURED,
        duration_ms=10,
        uncached_input_tokens=1,
        cached_input_tokens=2,
        output_tokens=3,
        reasoning_tokens=4,
        cost_usd=Decimal("0.0100"),
        summary_text=summary,
        argument_summary="token=[redacted]",
        result_preview="safe result",
        message_preview="safe",
        message_char_count=4,
        ciphertext_char_count=None,
        redaction_count=1,
        privacy_status="sanitized",
    )


def _binding(*, observed: int = 0, state: SnapshotState = SnapshotState.LIVE) -> SnapshotBindingInput:
    return SnapshotBindingInput(
        root_thread_id="root",
        include_children=True,
        include_collaborators=False,
        parser_version="parser-v1",
        pricing_version="pricing-v1",
        formatter_version="formatter-v1",
        privacy_version=PRIVACY_REGISTRY_VERSION,
        observation_time_utc=datetime(2026, 8, 12, 13, observed, tzinfo=UTC),
        state=state,
    )


def test_default_and_recommended_policy_are_the_accepted_production_policy() -> None:
    expected = EventCachePolicy(
        max_bytes=DEFAULT_MAX_BYTES,
        closed_snapshot_retention=None,
        cursor_retention=timedelta(days=7),
    )

    assert PRIVACY_REGISTRY_VERSION == "agent-report-privacy-v1"
    assert EventCachePolicy.default() == expected
    assert EventCachePolicy.recommended() == expected


def test_open_creates_schema_v1_with_required_pragmas(tmp_path: Path) -> None:
    cache = tmp_path / "report-events-v1.sqlite3"

    with EventRepository.open(cache) as repository:
        diagnostics = repository.diagnostics()
        connection = sqlite3.connect(cache)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
            assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            assert connection.execute("PRAGMA auto_vacuum").fetchone()[0] == 2
        finally:
            connection.close()

    assert diagnostics.schema_version == 1
    assert diagnostics.integrity_ok
    assert {
        "schema_metadata",
        "source_versions",
        "event_locators",
        "events",
        "source_diagnostics",
        "snapshot_bindings",
        "snapshot_revisions",
        "snapshot_sources",
        "cursor_locators",
    } <= tables


def test_open_result_reports_creation_then_open(tmp_path: Path) -> None:
    cache = tmp_path / "report-events-v1.sqlite3"

    first = EventRepository.open_or_rebuild(cache)
    assert first.action is RecoveryAction.CREATED
    first.repository.close()
    second = EventRepository.open_or_rebuild(cache)
    assert second.action is RecoveryAction.OPENED
    second.repository.close()


def test_open_migrates_empty_schema_v0_atomically(tmp_path: Path) -> None:
    cache = tmp_path / "report-events-v1.sqlite3"
    connection = sqlite3.connect(cache)
    connection.execute("VACUUM")
    connection.close()

    with EventRepository.open(cache) as repository:
        assert repository.diagnostics().schema_version == 1


def test_open_or_rebuild_recovers_corrupt_cache_atomically(tmp_path: Path) -> None:
    cache = tmp_path / "report-events-v1.sqlite3"
    cache.write_bytes(b"not a sqlite database")

    result = EventRepository.open_or_rebuild(cache)
    try:
        assert result.action is RecoveryAction.REBUILT_CORRUPT
        assert result.repository.diagnostics().integrity_ok
        assert not tuple(tmp_path.glob(".report-events-v1.sqlite3.rebuild-*"))
    finally:
        result.repository.close()


def test_source_snapshot_query_and_cursor_round_trip(tmp_path: Path) -> None:
    cache = tmp_path / "report-events-v1.sqlite3"
    source = _source()
    snapshot_id = SnapshotId("snap_" + "1" * 24)

    with EventRepository.open(cache) as repository:
        published = repository.replace_source(
            source,
            (_record(0), _record(1)),
            (NormalizedDiagnostic("SAFE_WARNING", 1, "safe"),),
        )
        assert not published.reused
        assert repository.replace_source(source, (_record(0), _record(1)), (NormalizedDiagnostic("SAFE_WARNING", 1, "safe"),)).reused

        snapshot = repository.publish_snapshot(
            snapshot_id=snapshot_id,
            expected_active_revision=None,
            binding=_binding(),
            sources=(source,),
        )
        reused = repository.publish_snapshot(
            snapshot_id=snapshot_id,
            expected_active_revision=snapshot.revision_id,
            binding=_binding(observed=1),
            sources=(source,),
        )
        assert reused == snapshot

        first_page = repository.query_events(
            EventQuery(snapshot_id, snapshot.revision_id, EventFilter(), 1)
        )
        assert len(first_page.items) == 1
        assert first_page.next_position is not None
        second_page = repository.query_events(
            EventQuery(
                snapshot_id,
                snapshot.revision_id,
                EventFilter(),
                1,
                after=first_page.next_position,
            )
        )
        assert len(second_page.items) == 1
        assert second_page.items[0].event_id != first_page.items[0].event_id
        assert repository.get_event(
            snapshot_id=snapshot_id,
            revision_id=snapshot.revision_id,
            event_id=first_page.items[0].event_id,
        ) == first_page.items[0]

        cursor = CursorBinding(
            snapshot_id,
            snapshot.revision_id,
            CursorOperation.LIST_EVENTS,
            "a" * 64,
            "b" * 64,
            1,
            first_page.next_position,
        )
        cursor_id = repository.save_cursor(
            cursor, accessed_at_utc=datetime(2026, 8, 12, 14, tzinfo=UTC)
        )
        assert repository.load_cursor(
            cursor_id,
            expected_snapshot_id=snapshot_id,
            expected_revision_id=snapshot.revision_id,
            expected_operation=CursorOperation.LIST_EVENTS,
            expected_filters_digest="a" * 64,
            expected_sort_digest="b" * 64,
            expected_page_size=1,
            accessed_at_utc=datetime(2026, 8, 12, 15, tzinfo=UTC),
        ) == cursor
        with pytest.raises(CacheCursorConflictError) as mismatch:
            repository.load_cursor(
                cursor_id,
                expected_snapshot_id=snapshot_id,
                expected_revision_id=snapshot.revision_id,
                expected_operation=CursorOperation.LIST_EVENTS,
                expected_filters_digest="c" * 64,
                expected_sort_digest="b" * 64,
                expected_page_size=1,
                accessed_at_utc=datetime(2026, 8, 12, 15, tzinfo=UTC),
            )
        assert mismatch.value.reason is CursorConflictReason.FILTER_MISMATCH


def test_privacy_rejection_and_cancellation_commit_nothing(tmp_path: Path) -> None:
    cache = tmp_path / "report-events-v1.sqlite3"
    source = _source()

    with EventRepository.open(cache) as repository:
        with pytest.raises(CachePrivacyViolationError):
            repository.replace_source(source, (_record(summary="api_key=visible"),))
        with pytest.raises(CacheCancelledError):
            repository.replace_source(source, (_record(),), cancellation_check=lambda: True)
        assert repository.diagnostics().source_version_count == 0


def test_publish_conflict_preserves_active_revision(tmp_path: Path) -> None:
    cache = tmp_path / "report-events-v1.sqlite3"
    source = _source()
    snapshot_id = SnapshotId("snap_" + "2" * 24)

    with EventRepository.open(cache) as repository:
        repository.replace_source(source, (_record(),))
        first = repository.publish_snapshot(
            snapshot_id=snapshot_id,
            expected_active_revision=None,
            binding=_binding(),
            sources=(source,),
        )
        with pytest.raises(CacheRevisionConflictError):
            repository.publish_snapshot(
                snapshot_id=snapshot_id,
                expected_active_revision=None,
                binding=_binding(observed=1, state=SnapshotState.SEALED),
                sources=(source,),
            )
        assert repository.get_snapshot(snapshot_id).revision_id == first.revision_id


def test_compare_sources_classifies_stale_partitions_and_binding(tmp_path: Path) -> None:
    cache = tmp_path / "report-events-v1.sqlite3"
    source = _source("a")
    added = _source("b")
    snapshot_id = SnapshotId("snap_" + "4" * 24)

    with EventRepository.open(cache) as repository:
        repository.replace_source(source, (_record(),))
        repository.publish_snapshot(
            snapshot_id=snapshot_id,
            expected_active_revision=None,
            binding=_binding(),
            sources=(source,),
        )
        changed = SourceRevision(
            source.source_key,
            SourceRevisionDigest("f" * 64),
            source.byte_count,
            source.mtime_ns + 1,
            source.parser_version,
            source.privacy_version,
        )
        comparison = repository.compare_sources(
            snapshot_id=snapshot_id,
            observed_sources=tuple(sorted((changed, added), key=lambda value: value.source_key)),
            binding=_binding(state=SnapshotState.SEALED),
        )

        assert comparison.changed == (changed,)
        assert comparison.added == (added,)
        assert comparison.removed_source_keys == ()
        assert comparison.binding_changed


def test_closed_snapshot_purge_removes_only_derived_rows(tmp_path: Path) -> None:
    cache = tmp_path / "report-events-v1.sqlite3"
    source = _source()
    snapshot_id = SnapshotId("snap_" + "3" * 24)

    with EventRepository.open(cache) as repository:
        repository.replace_source(source, (_record(),))
        repository.publish_snapshot(
            snapshot_id=snapshot_id,
            expected_active_revision=None,
            binding=_binding(),
            sources=(source,),
        )
        repository.mark_snapshot_closed(
            snapshot_id, closed_at_utc=datetime(2026, 8, 12, 16, tzinfo=UTC)
        )
        result = repository.purge(PurgeRequest(snapshot_ids=(snapshot_id,)))

        assert result.removed_snapshots == 1
        assert result.removed_snapshot_revisions == 1
        assert result.removed_source_versions == 1
        assert result.removed_events == 1
        assert repository.diagnostics().snapshot_count == 0


def test_newer_schema_is_rejected_without_rebuild(tmp_path: Path) -> None:
    cache = tmp_path / "report-events-v1.sqlite3"
    connection = sqlite3.connect(cache)
    connection.executescript(
        "CREATE TABLE schema_metadata(singleton INTEGER PRIMARY KEY,schema_version INTEGER,database_id TEXT,created_utc TEXT,migrated_utc TEXT);"
        "INSERT INTO schema_metadata VALUES(1,2,'0123456789abcdef0123456789abcdef','x','x');"
        "PRAGMA user_version=2;"
    )
    connection.close()
    before = cache.read_bytes()

    with pytest.raises(CacheSchemaTooNewError):
        EventRepository.open_or_rebuild(cache)

    assert cache.read_bytes() == before


def test_source_key_is_deterministic_and_repository_close_is_final(tmp_path: Path) -> None:
    relative = Path("folder") / ".." / "report.jsonl"
    assert source_key_for_path(relative) == source_key_for_path(relative)
    assert len(source_key_for_path(relative)) == 64

    repository = EventRepository.open(tmp_path / "cache.sqlite3")
    repository.close()
    repository.close()
    with pytest.raises(CacheClosedError):
        repository.diagnostics()


def test_remove_stale_rebuild_files_accepts_only_exact_regular_files(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "report-events-v1.sqlite3"
    exact = tmp_path / (".report-events-v1.sqlite3.rebuild-" + "a" * 32)
    quarantine = tmp_path / (
        ".report-events-v1.sqlite3.old-family-" + "b" * 32 + "-wal"
    )
    near_match = tmp_path / ("report-events-v1.sqlite3.rebuild-" + "c" * 32)
    exact.write_text("stage")
    quarantine.write_text("wal")
    near_match.write_text("keep")
    cutoff = datetime.now(UTC) + timedelta(seconds=1)

    assert EventRepository.remove_stale_rebuild_files(
        cache, older_than_utc=cutoff
    ) == 2
    assert near_match.read_text() == "keep"
