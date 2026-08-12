# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Persist privacy-bounded normalized Agent Report event revisions.
# Design: docs/design/components/CD-003-agent-report-normalized-event-cache.md

"""Disposable, privacy-bounded normalized event persistence for Agent Report."""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import struct
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Final, NewType, Self
from uuid import uuid4

SnapshotId = NewType("SnapshotId", str)
SnapshotRevisionId = NewType("SnapshotRevisionId", str)
SourceKey = NewType("SourceKey", str)
SourceRevisionDigest = NewType("SourceRevisionDigest", str)
EventId = NewType("EventId", str)
CursorLocatorId = NewType("CursorLocatorId", str)
CancellationCheck = Callable[[], bool]
CursorScalar = str | int | float | bool | None

DEFAULT_CACHE_PATH: Final[Path] = (
    Path.home() / ".codex" / "agent-report" / "report-events-v1.sqlite3"
)
LATEST_SCHEMA_VERSION: Final = 1
DEFAULT_BUSY_TIMEOUT_MS: Final = 5_000
DEFAULT_MAX_BYTES: Final = 5_368_709_120
PRIVACY_REGISTRY_VERSION: Final = "agent-report-privacy-v1"
REDACTION_MARKER: Final = "[redacted]"
NEVER_CANCELLED: Final[CancellationCheck] = lambda: False

_ID_64 = re.compile(r"[0-9a-f]{64}\Z")
_SNAPSHOT_ID = re.compile(r"snap_[0-9a-f]{24}\Z")
_REVISION_ID = re.compile(r"srev_[0-9a-f]{24}\Z")
_DIAGNOSTIC_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")
_ASSIGNMENT = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_-]*)(?P<separator>\s*=\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s]+)"
)
_MAPPING = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_-]*)(?P<separator>\s*:\s*)"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,}]+)"
)
_AUTHORIZATION = re.compile(
    r"(?i)(?P<prefix>\b(?:authorization|bearer)\s*[:=]?\s+)(?P<value>\S+)"
)
_FLAG = re.compile(
    r"(?i)(?P<prefix>--(?:api-key|client-secret|private-key|access-token|"
    r"refresh-token|token|secret|password|passwd|authorization|cookie|credential)"
    r"(?:=|\s+))(?P<value>\"[^\"]*\"|'[^']*'|\S+)"
)
_CIPHER = re.compile(r"[A-Za-z0-9_-]+={0,2}\Z")
_SENSITIVE_EXACT = {
    "api_key",
    "client_secret",
    "private_key",
    "access_token",
    "refresh_token",
}
_SENSITIVE_COMPONENTS = {
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "passwd",
    "password",
    "secret",
    "token",
}


class SnapshotState(StrEnum):
    LIVE = "live"
    SEALED = "sealed"


class EvidenceMethod(StrEnum):
    MEASURED = "measured"
    DERIVED = "derived"
    INFERRED = "inferred"
    UNAVAILABLE = "unavailable"
    ESTIMATED = "estimated"


class CursorOperation(StrEnum):
    LIST_AGENTS = "list_agents"
    LIST_TURNS = "list_turns"
    LIST_EVENTS = "list_events"
    QUERY_SEQUENCE = "query_sequence"
    QUERY_COORDINATION = "query_coordination"


class CursorConflictReason(StrEnum):
    NOT_FOUND = "not_found"
    SNAPSHOT_MISMATCH = "snapshot_mismatch"
    REVISION_MISMATCH = "revision_mismatch"
    OPERATION_MISMATCH = "operation_mismatch"
    FILTER_MISMATCH = "filter_mismatch"
    SORT_MISMATCH = "sort_mismatch"
    PAGE_SIZE_MISMATCH = "page_size_mismatch"


class RecoveryAction(StrEnum):
    OPENED = "opened"
    CREATED = "created"
    REBUILT_CORRUPT = "rebuilt_corrupt"


class PublicationPhase(StrEnum):
    BEFORE_REPLACE = "before_replace"
    REPLACED_NOT_DURABLE = "replaced_not_durable"
    REOPEN_VERIFICATION = "reopen_verification"


class PurgeReason(StrEnum):
    OPERATOR = "operator"
    RETENTION = "retention"
    QUOTA = "quota"
    RECOVERY = "recovery"


@dataclass(frozen=True, slots=True)
class EventCachePolicy:
    max_bytes: int | None
    closed_snapshot_retention: timedelta | None
    cursor_retention: timedelta

    @classmethod
    def default(cls) -> Self:
        return cls(DEFAULT_MAX_BYTES, None, timedelta(days=7))

    @classmethod
    def recommended(cls) -> Self:
        return cls.default()


@dataclass(frozen=True, slots=True)
class SourceRevision:
    source_key: SourceKey
    revision_digest: SourceRevisionDigest
    byte_count: int
    mtime_ns: int
    parser_version: str
    privacy_version: str


@dataclass(frozen=True, slots=True)
class NormalizedEventRecord:
    source_ordinal: int
    timestamp_utc: datetime
    kind: str
    agent_id: str | None
    turn_id: str | None
    work_item_id: str | None
    tool_name: str | None
    model: str | None
    status: str | None
    evidence_method: EvidenceMethod
    duration_ms: int | None
    uncached_input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    cost_usd: Decimal | None
    summary_text: str | None
    argument_summary: str | None
    result_preview: str | None
    message_preview: str | None
    message_char_count: int | None
    ciphertext_char_count: int | None
    redaction_count: int
    privacy_status: str


@dataclass(frozen=True, slots=True)
class NormalizedDiagnostic:
    code: str
    count: int
    safe_message: str | None


@dataclass(frozen=True, slots=True)
class SourcePublishResult:
    source: SourceRevision
    event_count: int
    diagnostic_count: int
    reused: bool


@dataclass(frozen=True, slots=True)
class SnapshotBindingInput:
    root_thread_id: str
    include_children: bool
    include_collaborators: bool
    parser_version: str
    pricing_version: str
    formatter_version: str
    privacy_version: str
    observation_time_utc: datetime
    state: SnapshotState


@dataclass(frozen=True, slots=True)
class SnapshotBinding:
    snapshot_id: SnapshotId
    revision_id: SnapshotRevisionId
    root_thread_id: str
    include_children: bool
    include_collaborators: bool
    source_set_digest: str
    scope_digest: str
    parser_version: str
    pricing_version: str
    formatter_version: str
    privacy_version: str
    observation_time_utc: datetime
    state: SnapshotState
    source_count: int


@dataclass(frozen=True, slots=True)
class StaleSourceSet:
    reusable: tuple[SourceRevision, ...]
    changed: tuple[SourceRevision, ...]
    added: tuple[SourceRevision, ...]
    removed_source_keys: tuple[SourceKey, ...]
    binding_changed: bool


@dataclass(frozen=True, slots=True)
class EventFilter:
    from_time_utc: datetime | None = None
    to_time_utc: datetime | None = None
    agent_id: str | None = None
    turn_id: str | None = None
    work_item_id: str | None = None
    kind: str | None = None


@dataclass(frozen=True, slots=True)
class EventQuery:
    snapshot_id: SnapshotId
    revision_id: SnapshotRevisionId
    filters: EventFilter
    page_size: int
    after: tuple[CursorScalar, ...] | None = None
    descending: bool = False


@dataclass(frozen=True, slots=True)
class StoredEvent:
    event_id: EventId
    source_key: SourceKey
    source_revision: SourceRevisionDigest
    record: NormalizedEventRecord


@dataclass(frozen=True, slots=True)
class EventPage:
    snapshot_id: SnapshotId
    revision_id: SnapshotRevisionId
    items: tuple[StoredEvent, ...]
    next_position: tuple[CursorScalar, ...] | None


@dataclass(frozen=True, slots=True)
class CursorBinding:
    snapshot_id: SnapshotId
    revision_id: SnapshotRevisionId
    operation: CursorOperation
    filters_digest: str
    sort_digest: str
    page_size: int
    position: tuple[CursorScalar, ...]


@dataclass(frozen=True, slots=True)
class PurgeRequest:
    snapshot_ids: tuple[SnapshotId, ...] = ()
    closed_before_utc: datetime | None = None
    cursor_accessed_before_utc: datetime | None = None
    reason: PurgeReason = PurgeReason.OPERATOR


@dataclass(frozen=True, slots=True)
class PurgeResult:
    removed_snapshots: int
    removed_snapshot_revisions: int
    removed_source_versions: int
    removed_events: int
    removed_cursors: int
    live_bytes_before: int
    live_bytes_after: int


@dataclass(frozen=True, slots=True)
class QuotaResult:
    enabled: bool
    limit_bytes: int | None
    live_bytes_before: int
    live_bytes_after: int
    evicted_snapshot_ids: tuple[SnapshotId, ...]


@dataclass(frozen=True, slots=True)
class CacheDiagnostics:
    schema_version: int
    database_id: str
    allocated_bytes: int
    live_bytes: int
    wal_bytes: int
    snapshot_count: int
    closed_snapshot_count: int
    source_version_count: int
    event_count: int
    cursor_count: int
    stale_rebuild_file_count: int
    integrity_ok: bool


@dataclass(frozen=True, slots=True)
class OpenResult:
    repository: EventRepository
    action: RecoveryAction


class EventCacheError(Exception):
    code = "REPORT_CACHE_ERROR"


class CacheValidationError(EventCacheError):
    code = "REPORT_INVALID_REQUEST"

    def __init__(self, field: str, rule: str) -> None:
        self.field, self.rule = field, rule
        super().__init__(f"Invalid {field}: {rule}")


class CachePrivacyViolationError(EventCacheError):
    code = "REPORT_PRIVACY_VIOLATION"

    def __init__(self, field: str, rule: str) -> None:
        self.field, self.rule = field, rule
        super().__init__(f"Privacy validation failed for {field}: {rule}")


class CacheSchemaTooNewError(EventCacheError):
    code = "REPORT_CACHE_SCHEMA_TOO_NEW"

    def __init__(self, found_version: int, supported_version: int) -> None:
        self.found_version, self.supported_version = found_version, supported_version
        super().__init__("The event cache schema is newer than this application supports")


class CacheSchemaUnsupportedError(EventCacheError):
    code = "REPORT_CACHE_SCHEMA_UNSUPPORTED"

    def __init__(self, found_version: int, reason: str) -> None:
        self.found_version, self.reason = found_version, reason
        super().__init__(f"Unsupported event cache schema: {reason}")


class CacheMigrationError(EventCacheError):
    code = "REPORT_CACHE_MIGRATION_FAILED"

    def __init__(self, from_version: int, to_version: int) -> None:
        self.from_version, self.to_version = from_version, to_version
        super().__init__(f"Event cache migration {from_version} to {to_version} failed")


class CacheCorruptError(EventCacheError):
    code = "REPORT_CACHE_CORRUPT"

    def __init__(self, check: str) -> None:
        self.check = check
        super().__init__(f"Event cache failed integrity check: {check}")


class CacheBusyError(EventCacheError):
    code = "REPORT_CACHE_BUSY"

    def __init__(self, timeout_ms: int) -> None:
        self.timeout_ms = timeout_ms
        super().__init__("Event cache is busy")


class CacheCancelledError(EventCacheError):
    code = "REPORT_CANCELLED"

    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(f"Event cache operation cancelled: {operation}")


class CacheClosedError(EventCacheError):
    code = "REPORT_CACHE_CLOSED"

    def __init__(self) -> None:
        super().__init__("Event cache is closed")


class CacheSnapshotNotFoundError(EventCacheError):
    code = "REPORT_SNAPSHOT_NOT_FOUND"

    def __init__(self, snapshot_id: SnapshotId) -> None:
        self.snapshot_id = snapshot_id
        super().__init__("Snapshot was not found")


class CacheRevisionConflictError(EventCacheError):
    code = "REPORT_SNAPSHOT_CONFLICT"

    def __init__(self, snapshot_id: SnapshotId, expected: SnapshotRevisionId | None, actual: SnapshotRevisionId | None) -> None:
        self.snapshot_id, self.expected, self.actual = snapshot_id, expected, actual
        super().__init__("Snapshot revision is stale")


class CacheCursorConflictError(EventCacheError):
    code = "REPORT_CURSOR_CONFLICT"

    def __init__(self, cursor_id: CursorLocatorId, reason: CursorConflictReason) -> None:
        self.cursor_id, self.reason = cursor_id, reason
        super().__init__(f"Cursor cannot be resumed: {reason.value}")


class CacheEventNotFoundError(EventCacheError):
    code = "REPORT_EVENT_NOT_FOUND"

    def __init__(self, event_id: EventId) -> None:
        self.event_id = event_id
        super().__init__("Event was not found")


class CacheIdentityCollisionError(EventCacheError):
    code = "REPORT_CACHE_IDENTITY_COLLISION"

    def __init__(self, identity_kind: str, identifier: str) -> None:
        self.identity_kind, self.identifier = identity_kind, identifier
        super().__init__(f"Deterministic {identity_kind} identity collision")


class CacheQuotaExceededError(EventCacheError):
    code = "REPORT_CACHE_QUOTA_EXCEEDED"

    def __init__(self, limit_bytes: int, live_bytes: int, protected_snapshot_count: int) -> None:
        self.limit_bytes = limit_bytes
        self.live_bytes = live_bytes
        self.protected_snapshot_count = protected_snapshot_count
        super().__init__("Event cache quota cannot be met while protected data is open")


class CachePublicationError(EventCacheError):
    code = "REPORT_CACHE_PUBLICATION_FAILED"

    def __init__(self, database_id: str, phase: PublicationPhase) -> None:
        self.database_id, self.phase = database_id, phase
        super().__init__("Event cache replacement failed before publication")


class CacheDurabilityError(EventCacheError):
    code = "REPORT_CACHE_DURABILITY_UNCERTAIN"

    def __init__(self, database_id: str, phase: PublicationPhase) -> None:
        self.database_id, self.phase = database_id, phase
        super().__init__("Published event cache durability is uncertain")


class CachePublicationVerificationError(EventCacheError):
    code = "REPORT_CACHE_PUBLICATION_INVALID"

    def __init__(self, database_id: str, phase: PublicationPhase) -> None:
        self.database_id, self.phase = database_id, phase
        super().__init__("Published event cache did not pass verification")


class CacheIoError(EventCacheError):
    code = "REPORT_CACHE_IO_ERROR"

    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(f"Event cache I/O failed during {operation}")


_SCHEMA_SQL = """
CREATE TABLE schema_metadata (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version INTEGER NOT NULL CHECK(schema_version>=1),
 database_id TEXT NOT NULL CHECK(length(database_id)=32), created_utc TEXT NOT NULL,
 migrated_utc TEXT NOT NULL) STRICT;
CREATE TABLE source_versions (
 source_key TEXT NOT NULL CHECK(length(source_key)=64), revision_digest TEXT NOT NULL CHECK(length(revision_digest)=64),
 parser_version TEXT NOT NULL, privacy_version TEXT NOT NULL, byte_count INTEGER NOT NULL CHECK(byte_count>=0),
 mtime_ns INTEGER NOT NULL CHECK(mtime_ns>=0), normalized_utc TEXT NOT NULL, last_accessed_utc TEXT NOT NULL,
 event_count INTEGER NOT NULL CHECK(event_count>=0), diagnostic_count INTEGER NOT NULL CHECK(diagnostic_count>=0),
 PRIMARY KEY(source_key,revision_digest,parser_version,privacy_version)) STRICT;
CREATE TABLE event_locators (
 event_id TEXT PRIMARY KEY CHECK(length(event_id)=28), source_key TEXT NOT NULL, revision_digest TEXT NOT NULL,
 parser_version TEXT NOT NULL, privacy_version TEXT NOT NULL, source_ordinal INTEGER NOT NULL CHECK(source_ordinal>=0),
 kind TEXT NOT NULL, locator_digest TEXT NOT NULL CHECK(length(locator_digest)=64),
 UNIQUE(source_key,revision_digest,parser_version,privacy_version,source_ordinal),
 FOREIGN KEY(source_key,revision_digest,parser_version,privacy_version)
 REFERENCES source_versions(source_key,revision_digest,parser_version,privacy_version) ON DELETE CASCADE) STRICT;
CREATE TABLE events (
 event_id TEXT PRIMARY KEY, timestamp_utc TEXT NOT NULL, agent_id TEXT, turn_id TEXT, work_item_id TEXT,
 tool_name TEXT, model TEXT, status TEXT, evidence_method TEXT NOT NULL CHECK(evidence_method IN ('measured','derived','inferred','unavailable','estimated')),
 duration_ms INTEGER CHECK(duration_ms IS NULL OR duration_ms>=0), uncached_input_tokens INTEGER CHECK(uncached_input_tokens IS NULL OR uncached_input_tokens>=0),
 cached_input_tokens INTEGER CHECK(cached_input_tokens IS NULL OR cached_input_tokens>=0), output_tokens INTEGER CHECK(output_tokens IS NULL OR output_tokens>=0),
 reasoning_tokens INTEGER CHECK(reasoning_tokens IS NULL OR reasoning_tokens>=0), cost_usd TEXT,
 summary_text TEXT CHECK(summary_text IS NULL OR length(summary_text)<=1024), argument_summary TEXT CHECK(argument_summary IS NULL OR length(argument_summary)<=4096),
 result_preview TEXT CHECK(result_preview IS NULL OR length(result_preview)<=4096), message_preview TEXT CHECK(message_preview IS NULL OR length(message_preview)<=50),
 message_char_count INTEGER CHECK(message_char_count IS NULL OR message_char_count>=0), ciphertext_char_count INTEGER CHECK(ciphertext_char_count IS NULL OR ciphertext_char_count>=0),
 redaction_count INTEGER NOT NULL CHECK(redaction_count>=0), privacy_status TEXT NOT NULL CHECK(privacy_status='sanitized'),
 record_digest TEXT NOT NULL CHECK(length(record_digest)=64), FOREIGN KEY(event_id) REFERENCES event_locators(event_id) ON DELETE CASCADE) STRICT;
CREATE TABLE source_diagnostics (
 source_key TEXT NOT NULL, revision_digest TEXT NOT NULL, parser_version TEXT NOT NULL, privacy_version TEXT NOT NULL,
 code TEXT NOT NULL, count INTEGER NOT NULL CHECK(count>0), safe_message TEXT CHECK(safe_message IS NULL OR length(safe_message)<=512),
 PRIMARY KEY(source_key,revision_digest,parser_version,privacy_version,code),
 FOREIGN KEY(source_key,revision_digest,parser_version,privacy_version)
 REFERENCES source_versions(source_key,revision_digest,parser_version,privacy_version) ON DELETE CASCADE) STRICT;
CREATE TABLE snapshot_bindings (
 snapshot_id TEXT PRIMARY KEY CHECK(length(snapshot_id)=29), root_thread_id TEXT NOT NULL,
 include_children INTEGER NOT NULL CHECK(include_children IN (0,1)), include_collaborators INTEGER NOT NULL CHECK(include_collaborators IN (0,1)),
 active_revision_id TEXT, created_utc TEXT NOT NULL, last_accessed_utc TEXT NOT NULL, closed_utc TEXT) STRICT;
CREATE TABLE snapshot_revisions (
 revision_id TEXT PRIMARY KEY CHECK(length(revision_id)=29), snapshot_id TEXT NOT NULL,
 source_set_digest TEXT NOT NULL CHECK(length(source_set_digest)=64), scope_digest TEXT NOT NULL CHECK(length(scope_digest)=64),
 parser_version TEXT NOT NULL, pricing_version TEXT NOT NULL, formatter_version TEXT NOT NULL, privacy_version TEXT NOT NULL,
 observation_utc TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('live','sealed')), published_utc TEXT NOT NULL,
 source_count INTEGER NOT NULL CHECK(source_count>=0),
 UNIQUE(snapshot_id,source_set_digest,scope_digest,parser_version,pricing_version,formatter_version,privacy_version,observation_utc,state),
 FOREIGN KEY(snapshot_id) REFERENCES snapshot_bindings(snapshot_id) ON DELETE CASCADE) STRICT;
CREATE TABLE snapshot_sources (
 revision_id TEXT NOT NULL, source_order INTEGER NOT NULL CHECK(source_order>=0), source_key TEXT NOT NULL,
 revision_digest TEXT NOT NULL, parser_version TEXT NOT NULL, privacy_version TEXT NOT NULL,
 PRIMARY KEY(revision_id,source_order), UNIQUE(revision_id,source_key),
 FOREIGN KEY(revision_id) REFERENCES snapshot_revisions(revision_id) ON DELETE CASCADE,
 FOREIGN KEY(source_key,revision_digest,parser_version,privacy_version)
 REFERENCES source_versions(source_key,revision_digest,parser_version,privacy_version) ON DELETE RESTRICT) STRICT;
CREATE TABLE cursor_locators (
 cursor_id TEXT PRIMARY KEY CHECK(length(cursor_id)=64), snapshot_id TEXT NOT NULL, revision_id TEXT NOT NULL,
 operation TEXT NOT NULL CHECK(operation IN ('list_agents','list_turns','list_events','query_sequence','query_coordination')),
 filters_digest TEXT NOT NULL CHECK(length(filters_digest)=64), sort_digest TEXT NOT NULL CHECK(length(sort_digest)=64),
 page_size INTEGER NOT NULL CHECK(page_size BETWEEN 1 AND 500), position_json TEXT NOT NULL CHECK(length(position_json)<=2048),
 created_utc TEXT NOT NULL, last_accessed_utc TEXT NOT NULL,
 FOREIGN KEY(snapshot_id) REFERENCES snapshot_bindings(snapshot_id) ON DELETE CASCADE,
 FOREIGN KEY(revision_id) REFERENCES snapshot_revisions(revision_id) ON DELETE CASCADE) STRICT;
CREATE TRIGGER snapshot_active_revision_guard BEFORE UPDATE OF active_revision_id ON snapshot_bindings
WHEN NEW.active_revision_id IS NOT NULL BEGIN
 SELECT RAISE(ABORT,'active revision does not belong to snapshot') WHERE NOT EXISTS
 (SELECT 1 FROM snapshot_revisions WHERE revision_id=NEW.active_revision_id AND snapshot_id=NEW.snapshot_id);
END;
CREATE INDEX events_timestamp_index ON events(timestamp_utc,event_id);
CREATE INDEX events_agent_index ON events(agent_id,timestamp_utc,event_id);
CREATE INDEX events_turn_index ON events(turn_id,timestamp_utc,event_id);
CREATE INDEX events_work_item_index ON events(work_item_id,timestamp_utc,event_id);
CREATE INDEX event_locator_source_index ON event_locators(source_key,revision_digest,parser_version,privacy_version,source_ordinal);
CREATE INDEX snapshot_source_lookup_index ON snapshot_sources(source_key,revision_digest,parser_version,privacy_version,revision_id);
CREATE INDEX snapshot_access_index ON snapshot_bindings(closed_utc,last_accessed_utc,snapshot_id);
CREATE INDEX cursor_access_index ON cursor_locators(last_accessed_utc,cursor_id);
"""
MIGRATIONS: Final[Mapping[int, tuple[str, ...]]] = {0: (_SCHEMA_SQL,)}


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CacheValidationError(field, "must be timezone-aware")
    return value.astimezone(timezone.utc)


def _utc_text(value: datetime, field: str = "datetime") -> str:
    return _utc(value, field).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _validate_text(value: str, field: str, maximum: int, *, nonempty: bool = False) -> None:
    if not isinstance(value, str) or (nonempty and not value) or len(value) > maximum:
        raise CacheValidationError(field, f"must contain {'1 through ' if nonempty else 'at most '}{maximum} characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise CacheValidationError(field, "contains a forbidden control character")


def _encode_value(value: object, depth: int = 0) -> tuple[int, bytes]:
    if value is None:
        return 0, b""
    if isinstance(value, StrEnum):
        value = value.value
    if isinstance(value, str):
        return 1, unicodedata.normalize("NFC", value).encode()
    if isinstance(value, bool):
        return 2, b"\x01" if value else b"\x00"
    if isinstance(value, int):
        return 3, str(value).encode("ascii")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CacheValidationError("digest", "decimal must be finite")
        normalized = format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")
        if not normalized or Decimal(value) == 0:
            normalized = "0"
        return 4, normalized.encode("ascii")
    if isinstance(value, datetime):
        return 5, _utc_text(value).encode("ascii")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CacheValidationError("digest", "float must be finite")
        return 6, struct.pack("!d", value)
    if isinstance(value, Mapping):
        raise CacheValidationError("digest", "mappings are not canonical values")
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        if depth >= 2:
            raise CacheValidationError("digest", "sequences may nest only once")
        encoded = bytearray(struct.pack("!I", len(value)))
        for item in value:
            tag, item_bytes = _encode_value(item, depth + 1)
            encoded.extend(bytes((tag,)))
            encoded.extend(struct.pack("!Q", len(item_bytes)))
            encoded.extend(item_bytes)
        return 7, bytes(encoded)
    raise CacheValidationError("digest", "unsupported canonical value")


def _canonical(domain: str, named_values: Sequence[tuple[str, object]]) -> bytes:
    output = bytearray(b"agent-report-cache-c14n-v1\x00")
    domain_bytes = domain.encode("utf-8")
    output.extend(b"\x01" + struct.pack("!Q", len(domain_bytes)) + domain_bytes)
    for name, value in named_values:
        name_bytes = name.encode("ascii")
        tag, value_bytes = _encode_value(value)
        output.extend(struct.pack("!H", len(name_bytes)) + name_bytes + bytes((tag,)))
        output.extend(struct.pack("!Q", len(value_bytes)) + value_bytes)
    return bytes(output)


def _sha(domain: str, values: Sequence[tuple[str, object]]) -> str:
    return hashlib.sha256(_canonical(domain, values)).hexdigest()


def _blake(domain: str, values: Sequence[tuple[str, object]]) -> str:
    return hashlib.blake2s(_canonical(domain, values), digest_size=32).hexdigest()


def source_key_for_path(path: Path) -> SourceKey:
    normalized = os.path.abspath(os.fspath(path))
    if os.name == "nt":
        normalized = os.path.normcase(normalized)
    normalized = unicodedata.normalize("NFC", normalized.replace("\\", "/"))
    return SourceKey(_sha("source-key-v1", (("normalized_absolute_path", normalized),)))


def _record_digest(record: NormalizedEventRecord) -> str:
    return _sha("normalized-record-v1", tuple((field.name, getattr(record, field.name)) for field in fields(record)))


def _source_set_digest(sources: Sequence[SourceRevision]) -> str:
    values = tuple(tuple(getattr(source, name) for name in (
        "source_key", "revision_digest", "byte_count", "mtime_ns", "parser_version", "privacy_version"
    )) for source in sources)
    return _sha("source-set-v1", (("sources", values),))


def _scope_digest(binding: SnapshotBindingInput) -> str:
    return _sha("scope-v1", (("root_thread_id", binding.root_thread_id), ("include_children", binding.include_children), ("include_collaborators", binding.include_collaborators)))


def _revision_digest(snapshot_id: SnapshotId, binding: SnapshotBindingInput, source_digest: str, scope_digest: str) -> str:
    return _blake("snapshot-revision-v1", (
        ("snapshot_id", snapshot_id), ("root_thread_id", binding.root_thread_id),
        ("include_children", binding.include_children), ("include_collaborators", binding.include_collaborators),
        ("source_set_digest", source_digest), ("scope_digest", scope_digest),
        ("parser_version", binding.parser_version), ("pricing_version", binding.pricing_version),
        ("formatter_version", binding.formatter_version), ("privacy_version", binding.privacy_version),
        ("observation_time_utc", binding.observation_time_utc), ("state", binding.state),
    ))


def _event_digest(source: SourceRevision, record: NormalizedEventRecord) -> str:
    return _blake("event-locator-v1", (
        ("source_key", source.source_key), ("revision_digest", source.revision_digest),
        ("parser_version", source.parser_version), ("privacy_version", source.privacy_version),
        ("source_ordinal", record.source_ordinal), ("kind", record.kind),
    ))


def _cursor_digest(binding: CursorBinding) -> str:
    return _blake("cursor-locator-v1", tuple((name, getattr(binding, name)) for name in (
        "snapshot_id", "revision_id", "operation", "filters_digest", "sort_digest", "page_size", "position"
    )))


class _CacheFileLock:
    """Hold the platform-native lock that coordinates a SQLite file family."""

    def __init__(self, path: Path, *, exclusive: bool, timeout_ms: int, cancellation_check: CancellationCheck) -> None:
        self.path = path
        self.exclusive = exclusive
        self.timeout_ms = timeout_ms
        self.cancellation_check = cancellation_check
        self._fd: int | None = None
        self._handle: int | None = None

    def acquire(self) -> None:
        deadline = time.monotonic() + self.timeout_ms / 1000
        if os.name == "nt":
            self._acquire_windows(deadline)
        else:
            self._acquire_posix(deadline)

    def _acquire_posix(self, deadline: float) -> None:
        import fcntl

        try:
            fd = os.open(
                self.path,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise CacheIoError("open lock file")
            self._fd = fd
            operation = (fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB
            while True:
                self._check_wait(deadline)
                try:
                    fcntl.flock(fd, operation)
                    return
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EAGAIN):
                        raise CacheIoError("acquire lock") from error
                self._wait(deadline)
        except BaseException:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            raise

    def _acquire_windows(self, deadline: float) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetFileAttributesW.restype = wintypes.DWORD
        attributes = kernel32.GetFileAttributesW(str(self.path))
        invalid_attributes = 0xFFFFFFFF
        reparse_or_directory = 0x400 | 0x10
        if attributes != invalid_attributes and attributes & reparse_or_directory:
            raise CacheIoError("open lock file")
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        handle = kernel32.CreateFileW(
            str(self.path), 0xC0000000, 0x3, None, 4, 0x80, None
        )
        if handle == ctypes.c_void_p(-1).value:
            raise CacheIoError("open lock file")
        self._handle = int(handle)

        class Overlapped(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE),
            ]

        self._overlapped = Overlapped()  # type: ignore[attr-defined]
        kernel32.LockFileEx.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(Overlapped),
        ]
        kernel32.LockFileEx.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        flags = 0x1 | (0x2 if self.exclusive else 0)
        try:
            while True:
                self._check_wait(deadline)
                if kernel32.LockFileEx(handle, flags, 0, 1, 0, ctypes.byref(self._overlapped)):
                    return
                if ctypes.get_last_error() != 33:
                    raise CacheIoError("acquire lock")
                self._wait(deadline)
        except BaseException:
            kernel32.CloseHandle(handle)
            self._handle = None
            raise

    def _check_wait(self, deadline: float) -> None:
        if self.cancellation_check():
            raise CacheCancelledError("lock acquisition")
        if time.monotonic() >= deadline:
            raise CacheBusyError(self.timeout_ms)

    @staticmethod
    def _wait(deadline: float) -> None:
        time.sleep(min(0.010, max(0.0, deadline - time.monotonic())))

    def release(self) -> None:
        if os.name == "nt" and self._handle is not None:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle, self._handle = self._handle, None
            overlapped_type = type(self._overlapped)  # type: ignore[attr-defined]
            kernel32.UnlockFileEx.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(overlapped_type),
            ]
            kernel32.UnlockFileEx.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            unlocked = kernel32.UnlockFileEx(handle, 0, 1, 0, ctypes.byref(self._overlapped))  # type: ignore[attr-defined]
            closed = kernel32.CloseHandle(handle)
            if not unlocked or not closed:
                raise CacheIoError("release lock")
        elif self._fd is not None:
            import fcntl

            fd, self._fd = self._fd, None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError as error:
                raise CacheIoError("release lock") from error
            finally:
                os.close(fd)

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


@dataclass(frozen=True, slots=True)
class _Inspection:
    exists: bool
    version: int
    database_id: str | None
    corrupt: bool = False


def _inspect_database(path: Path) -> _Inspection:
    if not path.exists() or path.stat().st_size == 0:
        return _Inspection(False, 0, None)
    uri = f"{path.as_uri()}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        try:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > LATEST_SCHEMA_VERSION:
                raise CacheSchemaTooNewError(version, LATEST_SCHEMA_VERSION)
            metadata_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_metadata'"
            ).fetchone()
            if not metadata_exists:
                if version == 0:
                    objects = connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1"
                    ).fetchone()
                    if objects is None:
                        return _Inspection(False, 0, None)
                    raise CacheSchemaUnsupportedError(0, "nonempty schema version 0")
                raise CacheSchemaUnsupportedError(version, "schema metadata is absent")
            metadata = connection.execute(
                "SELECT schema_version,database_id FROM schema_metadata WHERE singleton=1"
            ).fetchone()
            if metadata is None:
                raise CacheCorruptError("schema metadata singleton")
            metadata_version, database_id = int(metadata[0]), str(metadata[1])
            if metadata_version > LATEST_SCHEMA_VERSION:
                raise CacheSchemaTooNewError(metadata_version, LATEST_SCHEMA_VERSION)
            if metadata_version != version:
                raise CacheCorruptError("schema version agreement")
            if version != LATEST_SCHEMA_VERSION:
                raise CacheSchemaUnsupportedError(version, "no migration path")
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise CacheCorruptError("quick_check")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise CacheCorruptError("foreign_key_check")
            return _Inspection(True, version, database_id)
        finally:
            connection.close()
    except (CacheSchemaTooNewError, CacheSchemaUnsupportedError, CacheCorruptError):
        raise
    except (OSError, sqlite3.DatabaseError) as error:
        raise CacheCorruptError("immutable open") from error


def _configure_connection(path: Path, timeout_ms: int) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(path, timeout=timeout_ms / 1000, isolation_level=None)
        connection.row_factory = sqlite3.Row
        if connection.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() != "wal":
            raise CacheIoError("enable WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(f"PRAGMA busy_timeout={timeout_ms}")
        connection.execute("PRAGMA temp_store=MEMORY")
        return connection
    except sqlite3.OperationalError as error:
        if "connection" in locals():
            connection.close()
        if "locked" in str(error).lower() or "busy" in str(error).lower():
            raise CacheBusyError(timeout_ms) from error
        raise CacheIoError("configure database") from error
    except (OSError, sqlite3.DatabaseError) as error:
        if "connection" in locals():
            connection.close()
        raise CacheIoError("configure database") from error


def _create_schema(path: Path, *, delete_journal: bool = False) -> str:
    database_id = uuid4().hex
    timestamp = _utc_text(datetime.now(timezone.utc))
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        if os.name != "nt":
            os.chmod(path, 0o600)
        connection.execute("PRAGMA auto_vacuum=INCREMENTAL")
        connection.execute(f"PRAGMA journal_mode={'DELETE' if delete_journal else 'WAL'}")
        connection.execute("PRAGMA synchronous=FULL")
        try:
            connection.executescript("BEGIN EXCLUSIVE;" + "".join(MIGRATIONS[0]))
            connection.execute(
                "INSERT INTO schema_metadata VALUES(1,?,?,?,?)",
                (LATEST_SCHEMA_VERSION, database_id, timestamp, timestamp),
            )
            connection.execute(f"PRAGMA user_version={LATEST_SCHEMA_VERSION}")
            connection.execute("COMMIT")
        except BaseException as error:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise CacheMigrationError(0, LATEST_SCHEMA_VERSION) from error
        if not delete_journal:
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint and checkpoint[0] != 0:
                raise CacheBusyError(DEFAULT_BUSY_TIMEOUT_MS)
    finally:
        connection.close()
    return database_id


def _validate_policy(policy: EventCachePolicy) -> None:
    if not isinstance(policy, EventCachePolicy):
        raise CacheValidationError("policy", "must be an EventCachePolicy")
    if policy.max_bytes is not None and (
        isinstance(policy.max_bytes, bool)
        or not isinstance(policy.max_bytes, int)
        or policy.max_bytes < 16 * 1024 * 1024
    ):
        raise CacheValidationError("policy.max_bytes", "must be at least 16 MiB")
    if policy.closed_snapshot_retention is not None and (
        not isinstance(policy.closed_snapshot_retention, timedelta)
        or policy.closed_snapshot_retention < timedelta(0)
    ):
        raise CacheValidationError("policy.closed_snapshot_retention", "must be nonnegative")
    if not isinstance(policy.cursor_retention, timedelta) or policy.cursor_retention < timedelta(0):
        raise CacheValidationError("policy.cursor_retention", "must be nonnegative")


def _validate_timeout(timeout_ms: int) -> None:
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or not 1 <= timeout_ms <= 60_000:
        raise CacheValidationError("busy_timeout_ms", "must be from 1 through 60000")


class EventRepository:
    """Own one configured SQLite connection and its shared family lock."""

    def __init__(self, path: Path, connection: sqlite3.Connection, lock: _CacheFileLock, policy: EventCachePolicy, busy_timeout_ms: int) -> None:
        self._path = path
        self._connection: sqlite3.Connection | None = connection
        self._lock: _CacheFileLock | None = lock
        self._policy = policy
        self._busy_timeout_ms = busy_timeout_ms

    @classmethod
    def open(
        cls,
        cache_path: Path,
        *,
        policy: EventCachePolicy | None = None,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        cancellation_check: CancellationCheck = NEVER_CANCELLED,
    ) -> Self:
        repository, _ = cls._open(cache_path, policy, busy_timeout_ms, cancellation_check)
        return repository

    @classmethod
    def _open(
        cls,
        cache_path: Path,
        policy: EventCachePolicy | None,
        busy_timeout_ms: int,
        cancellation_check: CancellationCheck,
    ) -> tuple[Self, RecoveryAction]:
        _validate_timeout(busy_timeout_ms)
        selected_policy = EventCachePolicy.default() if policy is None else policy
        _validate_policy(selected_policy)
        path = Path(os.path.abspath(os.fspath(cache_path)))
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as error:
            raise CacheIoError("create cache directory") from error
        lock_path = path.with_name(path.name + ".lock")
        shared = _CacheFileLock(lock_path, exclusive=False, timeout_ms=busy_timeout_ms, cancellation_check=cancellation_check)
        shared.acquire()
        created = False
        try:
            inspection = _inspect_database(path)
            if not inspection.exists:
                shared.release()
                exclusive = _CacheFileLock(lock_path, exclusive=True, timeout_ms=busy_timeout_ms, cancellation_check=cancellation_check)
                with exclusive:
                    inspection = _inspect_database(path)
                    if not inspection.exists:
                        _create_schema(path)
                        created = True
                        _inspect_database(path)
                shared = _CacheFileLock(lock_path, exclusive=False, timeout_ms=busy_timeout_ms, cancellation_check=cancellation_check)
                shared.acquire()
                _inspect_database(path)
            connection = _configure_connection(path, busy_timeout_ms)
            return cls(path, connection, shared, selected_policy, busy_timeout_ms), (RecoveryAction.CREATED if created else RecoveryAction.OPENED)
        except BaseException:
            shared.release()
            raise

    @classmethod
    def open_or_rebuild(
        cls,
        cache_path: Path,
        *,
        policy: EventCachePolicy | None = None,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        cancellation_check: CancellationCheck = NEVER_CANCELLED,
    ) -> OpenResult:
        try:
            repository, action = cls._open(cache_path, policy, busy_timeout_ms, cancellation_check)
            return OpenResult(repository, action)
        except CacheCorruptError:
            cls.rebuild_empty(
                cache_path, policy=policy, busy_timeout_ms=busy_timeout_ms,
                cancellation_check=cancellation_check,
            )
            repository, _ = cls._open(cache_path, policy, busy_timeout_ms, cancellation_check)
            return OpenResult(repository, RecoveryAction.REBUILT_CORRUPT)

    @classmethod
    def rebuild_empty(
        cls,
        cache_path: Path,
        *,
        policy: EventCachePolicy | None = None,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        cancellation_check: CancellationCheck = NEVER_CANCELLED,
    ) -> None:
        _validate_timeout(busy_timeout_ms)
        selected_policy = EventCachePolicy.default() if policy is None else policy
        _validate_policy(selected_policy)
        path = Path(os.path.abspath(os.fspath(cache_path)))
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock = _CacheFileLock(path.with_name(path.name + ".lock"), exclusive=True, timeout_ms=busy_timeout_ms, cancellation_check=cancellation_check)
        with lock:
            old_id = "unknown"
            corrupt = False
            try:
                inspection = _inspect_database(path)
                old_id = inspection.database_id or "missing"
            except CacheCorruptError:
                corrupt = True
            # Unsupported and newer schema errors intentionally escape before staging.
            cls._check_cancel(cancellation_check, "rebuild staging")
            operation_id = uuid4().hex
            stage = path.with_name(f".{path.name}.rebuild-{operation_id}")
            try:
                try:
                    new_id = _create_schema(stage, delete_journal=True)
                    cls._fsync_file(stage)
                    verified = _inspect_database(stage)
                except CacheCancelledError:
                    raise
                except EventCacheError as error:
                    raise CachePublicationError(old_id, PublicationPhase.BEFORE_REPLACE) from error
                except OSError as error:
                    raise CachePublicationError(old_id, PublicationPhase.BEFORE_REPLACE) from error
                if verified.database_id != new_id or stage.with_name(stage.name + "-wal").exists() or stage.with_name(stage.name + "-shm").exists():
                    raise CachePublicationError(old_id, PublicationPhase.BEFORE_REPLACE)
                cls._check_cancel(cancellation_check, "rebuild publication")
                # From this point publication is intentionally noncancellable.
                if path.exists() and not corrupt:
                    try:
                        old = sqlite3.connect(path, timeout=busy_timeout_ms / 1000, isolation_level=None)
                        result = old.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                        old.close()
                        if result and result[0] != 0:
                            raise CachePublicationError(old_id, PublicationPhase.BEFORE_REPLACE)
                        cls._fsync_file(path)
                    except CachePublicationError:
                        raise
                    except (OSError, sqlite3.Error) as error:
                        raise CachePublicationError(old_id, PublicationPhase.BEFORE_REPLACE) from error
                for suffix in ("-wal", "-shm"):
                    sidecar = path.with_name(path.name + suffix)
                    if sidecar.exists():
                        quarantine = path.with_name(f".{path.name}.old-family-{operation_id}{suffix}")
                        try:
                            cls._replace_file(sidecar, quarantine)
                            cls._fsync_directory(path.parent)
                        except OSError as error:
                            raise CachePublicationError(old_id, PublicationPhase.BEFORE_REPLACE) from error
                try:
                    cls._replace_file(stage, path)
                except OSError as error:
                    observed = cls._safe_database_id(path)
                    if observed == new_id:
                        raise CacheDurabilityError(new_id, PublicationPhase.REPLACED_NOT_DURABLE) from error
                    if observed not in (old_id, None) and not corrupt:
                        raise CachePublicationVerificationError(observed or "unknown", PublicationPhase.REOPEN_VERIFICATION) from error
                    raise CachePublicationError(old_id, PublicationPhase.BEFORE_REPLACE) from error
                if os.name != "nt":
                    try:
                        cls._fsync_directory(path.parent)
                    except OSError as error:
                        raise CacheDurabilityError(new_id, PublicationPhase.REPLACED_NOT_DURABLE) from error
                try:
                    visible = _inspect_database(path)
                    if visible.database_id != new_id:
                        raise CachePublicationVerificationError(visible.database_id or "unknown", PublicationPhase.REOPEN_VERIFICATION)
                    if path.with_name(path.name + "-wal").exists() or path.with_name(path.name + "-shm").exists():
                        raise CachePublicationVerificationError(new_id, PublicationPhase.REOPEN_VERIFICATION)
                except CachePublicationVerificationError:
                    raise
                except EventCacheError as error:
                    raise CachePublicationVerificationError(cls._safe_database_id(path) or new_id, PublicationPhase.REOPEN_VERIFICATION) from error
            finally:
                try:
                    if stage.exists():
                        stage.unlink()
                except OSError:
                    pass

    @staticmethod
    def _replace_file(source: Path, target: Path) -> None:
        if os.name != "nt":
            os.replace(source, target)
            return
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.MoveFileExW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD
        ]
        kernel32.MoveFileExW.restype = wintypes.BOOL
        if not kernel32.MoveFileExW(str(source), str(target), 0x1 | 0x8):
            raise OSError(ctypes.get_last_error(), "MoveFileExW failed")

    @staticmethod
    def _fsync_file(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _safe_database_id(path: Path) -> str | None:
        try:
            return _inspect_database(path).database_id
        except EventCacheError:
            return None

    def close(self) -> None:
        connection, self._connection = self._connection, None
        lock, self._lock = self._lock, None
        if connection is not None:
            connection.close()
        if lock is not None:
            lock.release()

    def __enter__(self) -> Self:
        self._require_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _require_open(self) -> sqlite3.Connection:
        if self._connection is None:
            raise CacheClosedError()
        return self._connection

    @staticmethod
    def _check_cancel(check: CancellationCheck, operation: str) -> None:
        if check():
            raise CacheCancelledError(operation)

    @contextmanager
    def _transaction(self, mode: str = "DEFERRED", *, cancellation_check: CancellationCheck = NEVER_CANCELLED, operation: str = "transaction"):
        connection = self._require_open()
        self._check_cancel(cancellation_check, operation)
        connection.set_progress_handler(lambda: 1 if cancellation_check() else 0, 1_000)
        try:
            connection.execute(f"BEGIN {mode}")
            yield connection
            self._check_cancel(cancellation_check, operation)
            connection.execute("COMMIT")
        except sqlite3.OperationalError as error:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            if cancellation_check() or "interrupt" in str(error).lower():
                raise CacheCancelledError(operation) from error
            if "locked" in str(error).lower() or "busy" in str(error).lower():
                raise CacheBusyError(self._busy_timeout_ms) from error
            raise CacheIoError(operation) from error
        except sqlite3.DatabaseError as error:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise CacheIoError(operation) from error
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.set_progress_handler(None, 0)

    @staticmethod
    def _validate_source(source: SourceRevision) -> None:
        if not _ID_64.fullmatch(source.source_key):
            raise CacheValidationError("source.source_key", "must be 64 lowercase hexadecimal characters")
        if not _ID_64.fullmatch(source.revision_digest):
            raise CacheValidationError("source.revision_digest", "must be 64 lowercase hexadecimal characters")
        if isinstance(source.byte_count, bool) or not isinstance(source.byte_count, int) or source.byte_count < 0:
            raise CacheValidationError("source.byte_count", "must be nonnegative")
        if isinstance(source.mtime_ns, bool) or not isinstance(source.mtime_ns, int) or source.mtime_ns < 0:
            raise CacheValidationError("source.mtime_ns", "must be nonnegative")
        _validate_text(source.parser_version, "source.parser_version", 128, nonempty=True)
        if source.privacy_version != PRIVACY_REGISTRY_VERSION:
            raise CachePrivacyViolationError("source.privacy_version", "unsupported privacy registry version")

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        normalized = key.lstrip("-").replace("-", "_").lower()
        return normalized in _SENSITIVE_EXACT or bool(set(normalized.split("_")) & _SENSITIVE_COMPONENTS)

    @staticmethod
    def _is_redacted(value: str) -> bool:
        unquoted = value
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            unquoted = value[1:-1]
        return unquoted == REDACTION_MARKER

    @classmethod
    def _validate_display(cls, value: str | None, field: str, maximum: int) -> None:
        if value is None:
            return
        if not isinstance(value, str) or len(value) > maximum:
            raise CacheValidationError(field, f"must contain at most {maximum} characters")
        if any((ord(char) < 32 and char not in "\t\n") or ord(char) == 127 for char in value):
            raise CacheValidationError(field, "contains a forbidden control character")
        for expression, rule in ((_ASSIGNMENT, "assignment secret"), (_MAPPING, "mapping secret")):
            for match in expression.finditer(value):
                if cls._is_sensitive_key(match.group("key")) and not cls._is_redacted(match.group("value")):
                    raise CachePrivacyViolationError(field, rule)
        for expression, rule in ((_AUTHORIZATION, "authorization secret"), (_FLAG, "flag secret")):
            for match in expression.finditer(value):
                if not cls._is_redacted(match.group("value")):
                    raise CachePrivacyViolationError(field, rule)
        for token in re.findall(r"\S+", value):
            if len(token) >= 80 and token.startswith("gAAAAA") and _CIPHER.fullmatch(token):
                raise CachePrivacyViolationError(field, "ciphertext body")

    @classmethod
    def _validate_record(cls, record: NormalizedEventRecord) -> None:
        if record.privacy_status != "sanitized":
            raise CachePrivacyViolationError("record.privacy_status", "must be sanitized")
        if isinstance(record.source_ordinal, bool) or not isinstance(record.source_ordinal, int) or record.source_ordinal < 0:
            raise CacheValidationError("record.source_ordinal", "must be nonnegative")
        _utc(record.timestamp_utc, "record.timestamp_utc")
        _validate_text(record.kind, "record.kind", 128, nonempty=True)
        for name in ("agent_id", "turn_id", "work_item_id", "tool_name", "model", "status"):
            value = getattr(record, name)
            if value is not None:
                _validate_text(value, f"record.{name}", 512)
        if not isinstance(record.evidence_method, EvidenceMethod):
            raise CacheValidationError("record.evidence_method", "unsupported value")
        for name in (
            "duration_ms", "uncached_input_tokens", "cached_input_tokens", "output_tokens",
            "reasoning_tokens", "message_char_count", "ciphertext_char_count", "redaction_count",
        ):
            value = getattr(record, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise CacheValidationError(f"record.{name}", "must be nonnegative")
        if record.cost_usd is not None and (
            not isinstance(record.cost_usd, Decimal)
            or not record.cost_usd.is_finite()
            or record.cost_usd < 0
        ):
            raise CacheValidationError("record.cost_usd", "must be a finite nonnegative decimal")
        for name, maximum in (
            ("summary_text", 1024), ("argument_summary", 4096), ("result_preview", 4096),
            ("message_preview", 50),
        ):
            cls._validate_display(getattr(record, name), f"record.{name}", maximum)
        if record.message_preview is not None and record.message_char_count is not None and len(record.message_preview) > record.message_char_count:
            raise CacheValidationError("record.message_preview", "cannot exceed message_char_count")
    @classmethod
    def _validate_diagnostic(cls, diagnostic: NormalizedDiagnostic) -> None:
        if not _DIAGNOSTIC_CODE.fullmatch(diagnostic.code):
            raise CacheValidationError("diagnostic.code", "must be an uppercase diagnostic identifier")
        if isinstance(diagnostic.count, bool) or diagnostic.count <= 0:
            raise CacheValidationError("diagnostic.count", "must be positive")
        cls._validate_display(diagnostic.safe_message, "diagnostic.safe_message", 512)

    @staticmethod
    def _validate_binding(binding: SnapshotBindingInput) -> None:
        _validate_text(binding.root_thread_id, "binding.root_thread_id", 512, nonempty=True)
        for name in ("parser_version", "pricing_version", "formatter_version"):
            _validate_text(getattr(binding, name), f"binding.{name}", 128, nonempty=True)
        if binding.privacy_version != PRIVACY_REGISTRY_VERSION:
            raise CachePrivacyViolationError("binding.privacy_version", "unsupported privacy registry version")
        _utc(binding.observation_time_utc, "binding.observation_time_utc")
        if not isinstance(binding.include_children, bool) or not isinstance(binding.include_collaborators, bool):
            raise CacheValidationError("binding scope", "relationship flags must be booleans")
        if not isinstance(binding.state, SnapshotState):
            raise CacheValidationError("binding.state", "unsupported state")

    @staticmethod
    def _validate_sources(sources: Sequence[SourceRevision]) -> None:
        keys = [source.source_key for source in sources]
        if keys != sorted(keys) or len(set(keys)) != len(keys):
            raise CacheValidationError("sources", "must have unique source keys in ascending order")
        for source in sources:
            EventRepository._validate_source(source)

    def compare_sources(
        self,
        *,
        snapshot_id: SnapshotId | None,
        observed_sources: Sequence[SourceRevision],
        binding: SnapshotBindingInput,
    ) -> StaleSourceSet:
        connection = self._require_open()
        self._validate_binding(binding)
        self._validate_sources(observed_sources)
        active_sources: dict[str, SourceRevision] = {}
        active_binding: SnapshotBinding | None = None
        if snapshot_id is not None:
            snapshot_row = connection.execute(
                "SELECT * FROM snapshot_bindings WHERE snapshot_id=?", (snapshot_id,)
            ).fetchone()
            if snapshot_row is None or snapshot_row["active_revision_id"] is None:
                raise CacheSnapshotNotFoundError(snapshot_id)
            active_binding = self._snapshot_from_revision(
                connection, snapshot_row, snapshot_row["active_revision_id"]
            )
            rows = connection.execute(
                "SELECT sv.* FROM snapshot_bindings sb JOIN snapshot_sources ss ON ss.revision_id=sb.active_revision_id "
                "JOIN source_versions sv ON (sv.source_key,sv.revision_digest,sv.parser_version,sv.privacy_version)="
                "(ss.source_key,ss.revision_digest,ss.parser_version,ss.privacy_version) WHERE sb.snapshot_id=? ORDER BY ss.source_order",
                (snapshot_id,),
            ).fetchall()
            active_sources = {row["source_key"]: self._source_from_row(row) for row in rows}
        reusable: list[SourceRevision] = []
        changed: list[SourceRevision] = []
        added: list[SourceRevision] = []
        for source in observed_sources:
            ready = connection.execute(
                "SELECT 1 FROM source_versions WHERE source_key=? AND revision_digest=? AND parser_version=? AND privacy_version=? AND byte_count=? AND mtime_ns=?",
                (source.source_key, source.revision_digest, source.parser_version, source.privacy_version, source.byte_count, source.mtime_ns),
            ).fetchone()
            if ready:
                reusable.append(source)
            elif connection.execute("SELECT 1 FROM source_versions WHERE source_key=? LIMIT 1", (source.source_key,)).fetchone():
                changed.append(source)
            else:
                added.append(source)
        observed_keys = {source.source_key for source in observed_sources}
        removed = tuple(SourceKey(key) for key in active_sources if key not in observed_keys)
        source_digest = _source_set_digest(observed_sources)
        scope_digest = _scope_digest(binding)
        binding_changed = active_binding is None or any((
            active_binding.source_set_digest != source_digest,
            active_binding.scope_digest != scope_digest,
            active_binding.parser_version != binding.parser_version,
            active_binding.pricing_version != binding.pricing_version,
            active_binding.formatter_version != binding.formatter_version,
            active_binding.privacy_version != binding.privacy_version,
            active_binding.state != binding.state,
        ))
        return StaleSourceSet(tuple(reusable), tuple(changed), tuple(added), removed, binding_changed)

    def replace_source(
        self,
        source: SourceRevision,
        records: Iterable[NormalizedEventRecord],
        diagnostics: Iterable[NormalizedDiagnostic] = (),
        *,
        cancellation_check: CancellationCheck = NEVER_CANCELLED,
    ) -> SourcePublishResult:
        self._require_open()
        self._validate_source(source)
        record_values = tuple(records)
        diagnostic_values = tuple(diagnostics)
        for record in record_values:
            self._validate_record(record)
        for diagnostic in diagnostic_values:
            self._validate_diagnostic(diagnostic)
        if len({diagnostic.code for diagnostic in diagnostic_values}) != len(diagnostic_values):
            raise CacheValidationError("diagnostics.code", "must be unique within a source revision")
        if len({record.source_ordinal for record in record_values}) != len(record_values):
            raise CacheValidationError("records.source_ordinal", "must be unique within a source revision")
        event_values: list[tuple[str, str, NormalizedEventRecord]] = []
        seen_ids: dict[str, str] = {}
        for record in record_values:
            locator_digest = _event_digest(source, record)
            event_id = "evt_" + locator_digest[:24]
            if event_id in seen_ids and seen_ids[event_id] != locator_digest:
                raise CacheIdentityCollisionError("event", event_id)
            seen_ids[event_id] = locator_digest
            event_values.append((event_id, locator_digest, record))
        connection = self._require_open()
        exact = connection.execute(
            "SELECT byte_count,mtime_ns,event_count,diagnostic_count FROM source_versions WHERE source_key=? AND revision_digest=? AND parser_version=? AND privacy_version=?",
            (source.source_key, source.revision_digest, source.parser_version, source.privacy_version),
        ).fetchone()
        if exact is not None:
            stored_digests = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT e.record_digest FROM event_locators el JOIN events e ON e.event_id=el.event_id "
                    "WHERE el.source_key=? AND el.revision_digest=? AND el.parser_version=? AND el.privacy_version=? ORDER BY el.source_ordinal",
                    (source.source_key, source.revision_digest, source.parser_version, source.privacy_version),
                )
            )
            supplied_digests = tuple(_record_digest(record) for record in sorted(record_values, key=lambda value: value.source_ordinal))
            stored_diagnostics = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT code,count,safe_message FROM source_diagnostics WHERE source_key=? AND revision_digest=? AND parser_version=? AND privacy_version=? ORDER BY code",
                    (source.source_key, source.revision_digest, source.parser_version, source.privacy_version),
                )
            )
            supplied_diagnostics = tuple(sorted((value.code, value.count, value.safe_message) for value in diagnostic_values))
            if (
                exact[0] != source.byte_count
                or exact[1] != source.mtime_ns
                or exact[2] != len(record_values)
                or exact[3] != len(diagnostic_values)
                or stored_digests != supplied_digests
                or stored_diagnostics != supplied_diagnostics
            ):
                raise CacheIdentityCollisionError("source version", source.revision_digest)
            return SourcePublishResult(source, exact[2], exact[3], True)
        now = _utc_text(datetime.now(timezone.utc))
        with self._transaction("IMMEDIATE", cancellation_check=cancellation_check, operation="replace source") as transaction:
            transaction.execute(
                "INSERT INTO source_versions VALUES(?,?,?,?,?,?,?,?,?,?)",
                (source.source_key, source.revision_digest, source.parser_version, source.privacy_version,
                 source.byte_count, source.mtime_ns, now, now, len(record_values), len(diagnostic_values)),
            )
            for offset in range(0, len(event_values), 256):
                self._check_cancel(cancellation_check, "replace source")
                for event_id, locator_digest, record in event_values[offset:offset + 256]:
                    collision = transaction.execute("SELECT locator_digest FROM event_locators WHERE event_id=?", (event_id,)).fetchone()
                    if collision is not None and collision[0] != locator_digest:
                        raise CacheIdentityCollisionError("event", event_id)
                    transaction.execute(
                        "INSERT INTO event_locators VALUES(?,?,?,?,?,?,?,?)",
                        (event_id, source.source_key, source.revision_digest, source.parser_version,
                         source.privacy_version, record.source_ordinal, record.kind, locator_digest),
                    )
                    transaction.execute(
                        "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (event_id, _utc_text(record.timestamp_utc), record.agent_id, record.turn_id,
                         record.work_item_id, record.tool_name, record.model, record.status,
                         record.evidence_method.value, record.duration_ms, record.uncached_input_tokens,
                         record.cached_input_tokens, record.output_tokens, record.reasoning_tokens,
                         None if record.cost_usd is None else _encode_value(record.cost_usd)[1].decode("ascii"),
                         record.summary_text, record.argument_summary, record.result_preview, record.message_preview,
                         record.message_char_count, record.ciphertext_char_count, record.redaction_count,
                         record.privacy_status, _record_digest(record)),
                    )
            for offset in range(0, len(diagnostic_values), 256):
                self._check_cancel(cancellation_check, "replace source")
                transaction.executemany(
                    "INSERT INTO source_diagnostics VALUES(?,?,?,?,?,?,?)",
                    [(source.source_key, source.revision_digest, source.parser_version, source.privacy_version,
                      diagnostic.code, diagnostic.count, diagnostic.safe_message)
                     for diagnostic in diagnostic_values[offset:offset + 256]],
                )
            counts = transaction.execute(
                "SELECT (SELECT count(*) FROM event_locators WHERE source_key=? AND revision_digest=? AND parser_version=? AND privacy_version=?),"
                "(SELECT count(*) FROM source_diagnostics WHERE source_key=? AND revision_digest=? AND parser_version=? AND privacy_version=?)",
                (source.source_key, source.revision_digest, source.parser_version, source.privacy_version,
                 source.source_key, source.revision_digest, source.parser_version, source.privacy_version),
            ).fetchone()
            if tuple(counts) != (len(record_values), len(diagnostic_values)):
                raise CacheIdentityCollisionError("source count", source.revision_digest)
        return SourcePublishResult(source, len(record_values), len(diagnostic_values), False)

    @staticmethod
    def _source_from_row(row: sqlite3.Row) -> SourceRevision:
        return SourceRevision(
            SourceKey(row["source_key"]), SourceRevisionDigest(row["revision_digest"]),
            row["byte_count"], row["mtime_ns"], row["parser_version"], row["privacy_version"],
        )

    def publish_snapshot(
        self,
        *,
        snapshot_id: SnapshotId,
        expected_active_revision: SnapshotRevisionId | None,
        binding: SnapshotBindingInput,
        sources: Sequence[SourceRevision],
        cancellation_check: CancellationCheck = NEVER_CANCELLED,
    ) -> SnapshotBinding:
        self._require_open()
        if not _SNAPSHOT_ID.fullmatch(snapshot_id):
            raise CacheValidationError("snapshot_id", "must match snap_ plus 24 lowercase hexadecimal characters")
        if expected_active_revision is not None and not _REVISION_ID.fullmatch(expected_active_revision):
            raise CacheValidationError("expected_active_revision", "invalid revision identifier")
        self._validate_binding(binding)
        self._validate_sources(sources)
        if any(source.parser_version != binding.parser_version for source in sources):
            raise CacheValidationError("sources.parser_version", "must match the snapshot binding")
        if any(source.privacy_version != binding.privacy_version for source in sources):
            raise CacheValidationError("sources.privacy_version", "must match the snapshot binding")
        connection = self._require_open()
        existing = connection.execute("SELECT * FROM snapshot_bindings WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        if existing is not None and (
            existing["root_thread_id"] != binding.root_thread_id
            or bool(existing["include_children"]) != binding.include_children
            or bool(existing["include_collaborators"]) != binding.include_collaborators
        ):
            raise CacheValidationError("snapshot_id", "cannot change root thread or relationship scope")
        source_digest = _source_set_digest(sources)
        scope_digest = _scope_digest(binding)
        if existing is not None and existing["active_revision_id"] is not None:
            if existing["active_revision_id"] != expected_active_revision:
                raise CacheRevisionConflictError(
                    snapshot_id,
                    expected_active_revision,
                    SnapshotRevisionId(existing["active_revision_id"]),
                )
            active = self._snapshot_from_revision(connection, existing, existing["active_revision_id"])
            if (
                active.source_set_digest == source_digest
                and active.scope_digest == scope_digest
                and active.parser_version == binding.parser_version
                and active.pricing_version == binding.pricing_version
                and active.formatter_version == binding.formatter_version
                and active.privacy_version == binding.privacy_version
                and active.state == binding.state
            ):
                return active
        full_digest = _revision_digest(snapshot_id, binding, source_digest, scope_digest)
        revision_id = SnapshotRevisionId("srev_" + full_digest[:24])
        now = _utc_text(datetime.now(timezone.utc))
        observation = _utc_text(binding.observation_time_utc, "binding.observation_time_utc")
        with self._transaction("IMMEDIATE", cancellation_check=cancellation_check, operation="publish snapshot") as transaction:
            for source in sources:
                if transaction.execute(
                    "SELECT 1 FROM source_versions WHERE source_key=? AND revision_digest=? AND parser_version=? AND privacy_version=? AND byte_count=? AND mtime_ns=?",
                    (source.source_key, source.revision_digest, source.parser_version, source.privacy_version,
                     source.byte_count, source.mtime_ns),
                ).fetchone() is None:
                    raise CacheValidationError("sources", "references an unpublished source version")
            current = transaction.execute("SELECT * FROM snapshot_bindings WHERE snapshot_id=?", (snapshot_id,)).fetchone()
            actual = None if current is None else current["active_revision_id"]
            if actual != expected_active_revision:
                raise CacheRevisionConflictError(snapshot_id, expected_active_revision, SnapshotRevisionId(actual) if actual else None)
            if current is None:
                transaction.execute(
                    "INSERT INTO snapshot_bindings VALUES(?,?,?,?,?,?,?,NULL)",
                    (snapshot_id, binding.root_thread_id, int(binding.include_children), int(binding.include_collaborators), None, now, now),
                )
            collision = transaction.execute("SELECT * FROM snapshot_revisions WHERE revision_id=?", (revision_id,)).fetchone()
            if collision is not None:
                canonical_same = all((
                    collision["snapshot_id"] == snapshot_id,
                    collision["source_set_digest"] == source_digest,
                    collision["scope_digest"] == scope_digest,
                    collision["parser_version"] == binding.parser_version,
                    collision["pricing_version"] == binding.pricing_version,
                    collision["formatter_version"] == binding.formatter_version,
                    collision["privacy_version"] == binding.privacy_version,
                    collision["observation_utc"] == observation,
                    collision["state"] == binding.state.value,
                ))
                if not canonical_same:
                    raise CacheIdentityCollisionError("snapshot revision", revision_id)
            else:
                transaction.execute(
                    "INSERT INTO snapshot_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (revision_id, snapshot_id, source_digest, scope_digest, binding.parser_version,
                     binding.pricing_version, binding.formatter_version, binding.privacy_version,
                     observation, binding.state.value, now, len(sources)),
                )
                transaction.executemany(
                    "INSERT INTO snapshot_sources VALUES(?,?,?,?,?,?)",
                    [(revision_id, index, source.source_key, source.revision_digest,
                      source.parser_version, source.privacy_version) for index, source in enumerate(sources)],
                )
            self._check_cancel(cancellation_check, "publish snapshot")
            if expected_active_revision is None:
                cursor = transaction.execute(
                    "UPDATE snapshot_bindings SET active_revision_id=?,last_accessed_utc=?,closed_utc=NULL WHERE snapshot_id=? AND active_revision_id IS NULL",
                    (revision_id, now, snapshot_id),
                )
            else:
                cursor = transaction.execute(
                    "UPDATE snapshot_bindings SET active_revision_id=?,last_accessed_utc=?,closed_utc=NULL WHERE snapshot_id=? AND active_revision_id=?",
                    (revision_id, now, snapshot_id, expected_active_revision),
                )
            if cursor.rowcount != 1:
                latest = transaction.execute("SELECT active_revision_id FROM snapshot_bindings WHERE snapshot_id=?", (snapshot_id,)).fetchone()
                raise CacheRevisionConflictError(snapshot_id, expected_active_revision, SnapshotRevisionId(latest[0]) if latest and latest[0] else None)
        return SnapshotBinding(
            snapshot_id, revision_id, binding.root_thread_id, binding.include_children,
            binding.include_collaborators, source_digest, scope_digest, binding.parser_version,
            binding.pricing_version, binding.formatter_version, binding.privacy_version,
            _utc(binding.observation_time_utc, "binding.observation_time_utc"), binding.state, len(sources),
        )

    @staticmethod
    def _snapshot_from_revision(connection: sqlite3.Connection, binding_row: sqlite3.Row, revision_id: str) -> SnapshotBinding:
        revision = connection.execute("SELECT * FROM snapshot_revisions WHERE revision_id=?", (revision_id,)).fetchone()
        if revision is None:
            raise CacheCorruptError("active snapshot revision")
        return SnapshotBinding(
            SnapshotId(binding_row["snapshot_id"]), SnapshotRevisionId(revision["revision_id"]),
            binding_row["root_thread_id"], bool(binding_row["include_children"]),
            bool(binding_row["include_collaborators"]), revision["source_set_digest"],
            revision["scope_digest"], revision["parser_version"], revision["pricing_version"],
            revision["formatter_version"], revision["privacy_version"],
            _parse_utc(revision["observation_utc"]), SnapshotState(revision["state"]), revision["source_count"],
        )

    def get_snapshot(self, snapshot_id: SnapshotId) -> SnapshotBinding:
        connection = self._require_open()
        if not _SNAPSHOT_ID.fullmatch(snapshot_id):
            raise CacheValidationError("snapshot_id", "invalid identifier")
        with self._transaction("DEFERRED", operation="get snapshot") as transaction:
            row = transaction.execute("SELECT * FROM snapshot_bindings WHERE snapshot_id=?", (snapshot_id,)).fetchone()
            if row is None or row["active_revision_id"] is None:
                raise CacheSnapshotNotFoundError(snapshot_id)
            result = self._snapshot_from_revision(transaction, row, row["active_revision_id"])
        self._touch_snapshot(snapshot_id)
        return result

    def _touch_snapshot(self, snapshot_id: SnapshotId) -> None:
        """Update LRU metadata without turning a coherent WAL read into a failure."""
        try:
            with self._transaction("IMMEDIATE", operation="touch snapshot") as transaction:
                transaction.execute(
                    "UPDATE snapshot_bindings SET last_accessed_utc=? WHERE snapshot_id=?",
                    (_utc_text(datetime.now(timezone.utc)), snapshot_id),
                )
        except CacheBusyError:
            # Access metadata is advisory; the already-complete coherent read wins.
            return

    @staticmethod
    def _validate_query(query: EventQuery) -> None:
        if not _SNAPSHOT_ID.fullmatch(query.snapshot_id):
            raise CacheValidationError("query.snapshot_id", "invalid identifier")
        if not _REVISION_ID.fullmatch(query.revision_id):
            raise CacheValidationError("query.revision_id", "invalid identifier")
        if isinstance(query.page_size, bool) or not 1 <= query.page_size <= 500:
            raise CacheValidationError("query.page_size", "must be from 1 through 500")
        filters = query.filters
        if filters.from_time_utc is not None:
            _utc(filters.from_time_utc, "query.filters.from_time_utc")
        if filters.to_time_utc is not None:
            _utc(filters.to_time_utc, "query.filters.to_time_utc")
        if filters.from_time_utc is not None and filters.to_time_utc is not None and filters.to_time_utc <= filters.from_time_utc:
            raise CacheValidationError("query.filters", "to_time_utc must be later than from_time_utc")
        for name in ("agent_id", "turn_id", "work_item_id", "kind"):
            value = getattr(filters, name)
            if value is not None:
                _validate_text(value, f"query.filters.{name}", 512 if name != "kind" else 128)
        if query.after is not None:
            if len(query.after) != 4:
                raise CacheValidationError("query.after", "event position must have four values")
            EventRepository._validate_position(query.after)
            timestamp_value, source_key, source_ordinal, event_id = query.after
            if (
                not isinstance(timestamp_value, str)
                or not isinstance(source_key, str)
                or not _ID_64.fullmatch(source_key)
                or isinstance(source_ordinal, bool)
                or not isinstance(source_ordinal, int)
                or source_ordinal < 0
                or not isinstance(event_id, str)
                or not re.fullmatch(r"evt_[0-9a-f]{24}", event_id)
            ):
                raise CacheValidationError("query.after", "must contain the four-field event sort position")
            try:
                _parse_utc(timestamp_value)
            except ValueError as error:
                raise CacheValidationError("query.after", "timestamp must use canonical UTC encoding") from error

    @staticmethod
    def _validate_position(position: tuple[CursorScalar, ...]) -> None:
        if not 1 <= len(position) <= 8:
            raise CacheValidationError("position", "must have one through eight values")
        for value in position:
            if isinstance(value, str) and len(value) > 256:
                raise CacheValidationError("position", "string value exceeds 256 characters")
            if isinstance(value, float) and not math.isfinite(value):
                raise CacheValidationError("position", "float value must be finite")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise CacheValidationError("position", "contains a non-scalar value")

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> NormalizedEventRecord:
        return NormalizedEventRecord(
            source_ordinal=row["source_ordinal"], timestamp_utc=_parse_utc(row["timestamp_utc"]),
            kind=row["kind"], agent_id=row["agent_id"], turn_id=row["turn_id"],
            work_item_id=row["work_item_id"], tool_name=row["tool_name"], model=row["model"],
            status=row["status"], evidence_method=EvidenceMethod(row["evidence_method"]),
            duration_ms=row["duration_ms"], uncached_input_tokens=row["uncached_input_tokens"],
            cached_input_tokens=row["cached_input_tokens"], output_tokens=row["output_tokens"],
            reasoning_tokens=row["reasoning_tokens"], cost_usd=Decimal(row["cost_usd"]) if row["cost_usd"] is not None else None,
            summary_text=row["summary_text"], argument_summary=row["argument_summary"],
            result_preview=row["result_preview"], message_preview=row["message_preview"],
            message_char_count=row["message_char_count"], ciphertext_char_count=row["ciphertext_char_count"],
            redaction_count=row["redaction_count"], privacy_status=row["privacy_status"],
        )

    @classmethod
    def _stored_event_from_row(cls, row: sqlite3.Row) -> StoredEvent:
        return StoredEvent(
            EventId(row["event_id"]), SourceKey(row["source_key"]),
            SourceRevisionDigest(row["revision_digest"]), cls._record_from_row(row),
        )

    def query_events(
        self,
        query: EventQuery,
        *,
        cancellation_check: CancellationCheck = NEVER_CANCELLED,
    ) -> EventPage:
        self._require_open()
        self._validate_query(query)
        clauses = ["ss.revision_id=?"]
        parameters: list[object] = [query.revision_id]
        filters = query.filters
        for sql, value in (
            ("e.timestamp_utc>=?", None if filters.from_time_utc is None else _utc_text(filters.from_time_utc)),
            ("e.timestamp_utc<?", None if filters.to_time_utc is None else _utc_text(filters.to_time_utc)),
            ("e.agent_id=?", filters.agent_id), ("e.turn_id=?", filters.turn_id),
            ("e.work_item_id=?", filters.work_item_id), ("el.kind=?", filters.kind),
        ):
            if value is not None:
                clauses.append(sql)
                parameters.append(value)
        if query.after is not None:
            comparator = "<" if query.descending else ">"
            clauses.append(f"(e.timestamp_utc,el.source_key,el.source_ordinal,el.event_id){comparator}(?,?,?,?)")
            parameters.extend(query.after)
        direction = "DESC" if query.descending else "ASC"
        parameters.append(query.page_size + 1)
        sql = (
            "SELECT el.event_id,el.source_key,el.revision_digest,el.source_ordinal,el.kind,e.* "
            "FROM snapshot_sources ss JOIN event_locators el ON (el.source_key,el.revision_digest,el.parser_version,el.privacy_version)="
            "(ss.source_key,ss.revision_digest,ss.parser_version,ss.privacy_version) JOIN events e ON e.event_id=el.event_id "
            f"WHERE {' AND '.join(clauses)} ORDER BY e.timestamp_utc {direction},el.source_key {direction},"
            f"el.source_ordinal {direction},el.event_id {direction} LIMIT ?"
        )
        with self._transaction("DEFERRED", cancellation_check=cancellation_check, operation="query events") as transaction:
            snapshot = transaction.execute("SELECT active_revision_id FROM snapshot_bindings WHERE snapshot_id=?", (query.snapshot_id,)).fetchone()
            if snapshot is None:
                raise CacheSnapshotNotFoundError(query.snapshot_id)
            if snapshot[0] != query.revision_id:
                raise CacheRevisionConflictError(query.snapshot_id, query.revision_id, SnapshotRevisionId(snapshot[0]) if snapshot[0] else None)
            rows = transaction.execute(sql, parameters).fetchall()
            page_rows = rows[:query.page_size]
            items = tuple(self._stored_event_from_row(row) for row in page_rows)
            next_position = None
            if len(rows) > query.page_size and page_rows:
                last = page_rows[-1]
                next_position = (last["timestamp_utc"], last["source_key"], last["source_ordinal"], last["event_id"])
        self._touch_snapshot(query.snapshot_id)
        return EventPage(query.snapshot_id, query.revision_id, items, next_position)

    def get_event(
        self,
        *,
        snapshot_id: SnapshotId,
        revision_id: SnapshotRevisionId,
        event_id: EventId,
    ) -> StoredEvent:
        self._require_open()
        if not _SNAPSHOT_ID.fullmatch(snapshot_id) or not _REVISION_ID.fullmatch(revision_id):
            raise CacheValidationError("snapshot revision", "invalid identifier")
        if not re.fullmatch(r"evt_[0-9a-f]{24}", event_id):
            raise CacheValidationError("event_id", "invalid identifier")
        with self._transaction("DEFERRED", operation="get event") as transaction:
            snapshot = transaction.execute("SELECT active_revision_id FROM snapshot_bindings WHERE snapshot_id=?", (snapshot_id,)).fetchone()
            if snapshot is None:
                raise CacheSnapshotNotFoundError(snapshot_id)
            if snapshot[0] != revision_id:
                raise CacheRevisionConflictError(snapshot_id, revision_id, SnapshotRevisionId(snapshot[0]) if snapshot[0] else None)
            row = transaction.execute(
                "SELECT el.event_id,el.source_key,el.revision_digest,el.source_ordinal,el.kind,e.* FROM snapshot_sources ss "
                "JOIN event_locators el ON (el.source_key,el.revision_digest,el.parser_version,el.privacy_version)="
                "(ss.source_key,ss.revision_digest,ss.parser_version,ss.privacy_version) JOIN events e ON e.event_id=el.event_id "
                "WHERE ss.revision_id=? AND el.event_id=?",
                (revision_id, event_id),
            ).fetchone()
            if row is None:
                raise CacheEventNotFoundError(event_id)
            result = self._stored_event_from_row(row)
        self._touch_snapshot(snapshot_id)
        return result

    def save_cursor(self, binding: CursorBinding, *, accessed_at_utc: datetime) -> CursorLocatorId:
        self._require_open()
        self._validate_cursor_binding(binding)
        accessed = _utc_text(accessed_at_utc, "accessed_at_utc")
        cursor_id = CursorLocatorId(_cursor_digest(binding))
        position_json = json.dumps(binding.position, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with self._transaction("IMMEDIATE", operation="save cursor") as transaction:
            snapshot = transaction.execute("SELECT active_revision_id FROM snapshot_bindings WHERE snapshot_id=?", (binding.snapshot_id,)).fetchone()
            if snapshot is None:
                raise CacheSnapshotNotFoundError(binding.snapshot_id)
            if snapshot[0] != binding.revision_id:
                raise CacheRevisionConflictError(binding.snapshot_id, binding.revision_id, SnapshotRevisionId(snapshot[0]) if snapshot[0] else None)
            existing = transaction.execute("SELECT * FROM cursor_locators WHERE cursor_id=?", (cursor_id,)).fetchone()
            if existing is not None and any((
                existing["snapshot_id"] != binding.snapshot_id, existing["revision_id"] != binding.revision_id,
                existing["operation"] != binding.operation.value, existing["filters_digest"] != binding.filters_digest,
                existing["sort_digest"] != binding.sort_digest, existing["page_size"] != binding.page_size,
                existing["position_json"] != position_json,
            )):
                raise CacheIdentityCollisionError("cursor", cursor_id)
            transaction.execute(
                "INSERT INTO cursor_locators VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(cursor_id) DO UPDATE SET last_accessed_utc=excluded.last_accessed_utc",
                (cursor_id, binding.snapshot_id, binding.revision_id, binding.operation.value,
                 binding.filters_digest, binding.sort_digest, binding.page_size, position_json, accessed, accessed),
            )
        return cursor_id

    @staticmethod
    def _validate_cursor_binding(binding: CursorBinding) -> None:
        if not _SNAPSHOT_ID.fullmatch(binding.snapshot_id) or not _REVISION_ID.fullmatch(binding.revision_id):
            raise CacheValidationError("cursor binding", "invalid snapshot or revision identifier")
        if not _ID_64.fullmatch(binding.filters_digest) or not _ID_64.fullmatch(binding.sort_digest):
            raise CacheValidationError("cursor binding", "filter and sort digests must be 64 lowercase hexadecimal characters")
        if not isinstance(binding.operation, CursorOperation):
            raise CacheValidationError("cursor.operation", "unsupported operation")
        if isinstance(binding.page_size, bool) or not 1 <= binding.page_size <= 500:
            raise CacheValidationError("cursor.page_size", "must be from 1 through 500")
        EventRepository._validate_position(binding.position)
        try:
            encoded = json.dumps(binding.position, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise CacheValidationError("cursor.position", "must use canonical JSON scalars") from error
        if len(encoded) > 2048:
            raise CacheValidationError("cursor.position", "canonical JSON exceeds 2048 characters")

    def load_cursor(
        self,
        cursor_id: CursorLocatorId,
        *,
        expected_snapshot_id: SnapshotId,
        expected_revision_id: SnapshotRevisionId,
        expected_operation: CursorOperation,
        expected_filters_digest: str,
        expected_sort_digest: str,
        expected_page_size: int,
        accessed_at_utc: datetime,
    ) -> CursorBinding:
        connection = self._require_open()
        accessed = _utc_text(accessed_at_utc, "accessed_at_utc")
        if not _ID_64.fullmatch(cursor_id):
            raise CacheValidationError("cursor_id", "must be 64 lowercase hexadecimal characters")
        if not _SNAPSHOT_ID.fullmatch(expected_snapshot_id) or not _REVISION_ID.fullmatch(expected_revision_id):
            raise CacheValidationError("cursor expectation", "invalid snapshot or revision identifier")
        if not isinstance(expected_operation, CursorOperation):
            raise CacheValidationError("expected_operation", "unsupported operation")
        if not _ID_64.fullmatch(expected_filters_digest) or not _ID_64.fullmatch(expected_sort_digest):
            raise CacheValidationError("cursor expectation", "filter and sort digests must be 64 lowercase hexadecimal characters")
        if isinstance(expected_page_size, bool) or not isinstance(expected_page_size, int) or not 1 <= expected_page_size <= 500:
            raise CacheValidationError("expected_page_size", "must be from 1 through 500")
        row = connection.execute("SELECT * FROM cursor_locators WHERE cursor_id=?", (cursor_id,)).fetchone()
        if row is None:
            raise CacheCursorConflictError(cursor_id, CursorConflictReason.NOT_FOUND)
        comparisons = (
            (row["snapshot_id"], expected_snapshot_id, CursorConflictReason.SNAPSHOT_MISMATCH),
            (row["revision_id"], expected_revision_id, CursorConflictReason.REVISION_MISMATCH),
            (row["operation"], expected_operation.value, CursorConflictReason.OPERATION_MISMATCH),
            (row["filters_digest"], expected_filters_digest, CursorConflictReason.FILTER_MISMATCH),
            (row["sort_digest"], expected_sort_digest, CursorConflictReason.SORT_MISMATCH),
            (row["page_size"], expected_page_size, CursorConflictReason.PAGE_SIZE_MISMATCH),
        )
        for actual, expected, reason in comparisons:
            if actual != expected:
                raise CacheCursorConflictError(cursor_id, reason)
        position = tuple(json.loads(row["position_json"]))
        binding = CursorBinding(expected_snapshot_id, expected_revision_id, expected_operation, expected_filters_digest, expected_sort_digest, expected_page_size, position)
        self._validate_cursor_binding(binding)
        with self._transaction("IMMEDIATE", operation="load cursor") as transaction:
            transaction.execute("UPDATE cursor_locators SET last_accessed_utc=? WHERE cursor_id=?", (accessed, cursor_id))
        return binding

    def mark_snapshot_closed(self, snapshot_id: SnapshotId, *, closed_at_utc: datetime) -> None:
        self._require_open()
        if not _SNAPSHOT_ID.fullmatch(snapshot_id):
            raise CacheValidationError("snapshot_id", "invalid identifier")
        closed = _utc_text(closed_at_utc, "closed_at_utc")
        with self._transaction("IMMEDIATE", operation="close snapshot") as transaction:
            cursor = transaction.execute(
                "UPDATE snapshot_bindings SET closed_utc=?,last_accessed_utc=CASE WHEN last_accessed_utc>? THEN last_accessed_utc ELSE ? END WHERE snapshot_id=?",
                (closed, closed, closed, snapshot_id),
            )
            if cursor.rowcount == 0:
                raise CacheSnapshotNotFoundError(snapshot_id)

    @staticmethod
    def _live_bytes(connection: sqlite3.Connection) -> int:
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        return (page_count - freelist_count) * page_size

    def purge(
        self,
        request: PurgeRequest,
        *,
        protected_snapshot_ids: Sequence[SnapshotId] = (),
        cancellation_check: CancellationCheck = NEVER_CANCELLED,
    ) -> PurgeResult:
        self._require_open()
        if not isinstance(request, PurgeRequest):
            raise CacheValidationError("purge", "must be a PurgeRequest")
        if not isinstance(request.reason, PurgeReason):
            raise CacheValidationError("purge.reason", "unsupported reason")
        if not request.snapshot_ids and request.closed_before_utc is None and request.cursor_accessed_before_utc is None:
            raise CacheValidationError("purge", "must provide at least one selector")
        if len(set(request.snapshot_ids)) != len(request.snapshot_ids):
            raise CacheValidationError("purge.snapshot_ids", "must not contain duplicates")
        if len(set(protected_snapshot_ids)) != len(protected_snapshot_ids):
            raise CacheValidationError("protected_snapshot_ids", "must not contain duplicates")
        for snapshot_id in (*request.snapshot_ids, *protected_snapshot_ids):
            if not _SNAPSHOT_ID.fullmatch(snapshot_id):
                raise CacheValidationError("snapshot_id", "invalid identifier")
        closed_cutoff = None if request.closed_before_utc is None else _utc_text(request.closed_before_utc, "closed_before_utc")
        cursor_cutoff = None if request.cursor_accessed_before_utc is None else _utc_text(request.cursor_accessed_before_utc, "cursor_accessed_before_utc")
        protected = set(protected_snapshot_ids)
        with self._transaction("IMMEDIATE", cancellation_check=cancellation_check, operation="purge") as transaction:
            before = self._live_bytes(transaction)
            selected: set[str] = set()
            for snapshot_id in request.snapshot_ids:
                row = transaction.execute("SELECT closed_utc FROM snapshot_bindings WHERE snapshot_id=?", (snapshot_id,)).fetchone()
                if row is None or row[0] is None or snapshot_id in protected:
                    raise CacheValidationError("purge.snapshot_ids", "each named snapshot must be closed, present, and unprotected")
                selected.add(snapshot_id)
            if closed_cutoff is not None:
                parameters: list[object] = [closed_cutoff]
                sql = "SELECT snapshot_id FROM snapshot_bindings WHERE closed_utc IS NOT NULL AND closed_utc<=?"
                if protected:
                    sql += f" AND snapshot_id NOT IN ({','.join('?' for _ in protected)})"
                    parameters.extend(sorted(protected))
                for row in transaction.execute(sql, parameters):
                    selected.add(row[0])
            independent_cursors: set[str] = set()
            if cursor_cutoff is not None:
                independent_cursors = {row[0] for row in transaction.execute("SELECT cursor_id FROM cursor_locators WHERE last_accessed_utc<=?", (cursor_cutoff,))}
            self._check_cancel(cancellation_check, "purge")
            revision_ids: set[str] = set()
            cascaded_cursors: set[str] = set()
            if selected:
                placeholders = ",".join("?" for _ in selected)
                ordered = sorted(selected)
                revision_ids = {row[0] for row in transaction.execute(f"SELECT revision_id FROM snapshot_revisions WHERE snapshot_id IN ({placeholders})", ordered)}
                cascaded_cursors = {row[0] for row in transaction.execute(f"SELECT cursor_id FROM cursor_locators WHERE snapshot_id IN ({placeholders})", ordered)}
            all_cursors = independent_cursors | cascaded_cursors
            if independent_cursors:
                for batch_start in range(0, len(independent_cursors), 256):
                    self._check_cancel(cancellation_check, "purge")
                    batch = sorted(independent_cursors)[batch_start:batch_start + 256]
                    transaction.execute(f"DELETE FROM cursor_locators WHERE cursor_id IN ({','.join('?' for _ in batch)})", batch)
            if selected:
                self._check_cancel(cancellation_check, "purge")
                ordered = sorted(selected)
                transaction.execute(f"DELETE FROM snapshot_bindings WHERE snapshot_id IN ({','.join('?' for _ in ordered)})", ordered)
            source_rows = transaction.execute(
                "SELECT source_key,revision_digest,parser_version,privacy_version,event_count FROM source_versions sv "
                "WHERE NOT EXISTS(SELECT 1 FROM snapshot_sources ss WHERE (ss.source_key,ss.revision_digest,ss.parser_version,ss.privacy_version)="
                "(sv.source_key,sv.revision_digest,sv.parser_version,sv.privacy_version))"
            ).fetchall()
            removed_events = sum(row[4] for row in source_rows)
            self._check_cancel(cancellation_check, "purge")
            transaction.execute(
                "DELETE FROM source_versions WHERE NOT EXISTS(SELECT 1 FROM snapshot_sources ss WHERE (ss.source_key,ss.revision_digest,ss.parser_version,ss.privacy_version)="
                "(source_versions.source_key,source_versions.revision_digest,source_versions.parser_version,source_versions.privacy_version))"
            )
            after = self._live_bytes(transaction)
        return PurgeResult(len(selected), len(revision_ids), len(source_rows), removed_events, len(all_cursors), before, after)

    def apply_retention(
        self,
        *,
        now_utc: datetime,
        protected_snapshot_ids: Sequence[SnapshotId] = (),
        cancellation_check: CancellationCheck = NEVER_CANCELLED,
    ) -> PurgeResult:
        now = _utc(now_utc, "now_utc")
        return self.purge(
            PurgeRequest(
                closed_before_utc=None if self._policy.closed_snapshot_retention is None else now - self._policy.closed_snapshot_retention,
                cursor_accessed_before_utc=now - self._policy.cursor_retention,
                reason=PurgeReason.RETENTION,
            ),
            protected_snapshot_ids=protected_snapshot_ids,
            cancellation_check=cancellation_check,
        )

    def enforce_quota(
        self,
        *,
        protected_snapshot_ids: Sequence[SnapshotId] = (),
        cancellation_check: CancellationCheck = NEVER_CANCELLED,
    ) -> QuotaResult:
        self._require_open()
        if len(set(protected_snapshot_ids)) != len(protected_snapshot_ids):
            raise CacheValidationError("protected_snapshot_ids", "must not contain duplicates")
        limit = self._policy.max_bytes
        connection = self._require_open()
        if limit is None:
            before = self._live_bytes(connection)
            return QuotaResult(False, None, before, before, ())
        protected = set(protected_snapshot_ids)
        with self._transaction("IMMEDIATE", cancellation_check=cancellation_check, operation="enforce quota") as transaction:
            before = self._live_bytes(transaction)
            if before <= limit:
                return QuotaResult(True, limit, before, before, ())
            candidates = transaction.execute(
                "SELECT snapshot_id FROM snapshot_bindings WHERE closed_utc IS NOT NULL ORDER BY last_accessed_utc,snapshot_id"
            ).fetchall()
            evicted: list[SnapshotId] = []
            current = self._live_bytes(transaction)
            for row in candidates:
                snapshot_id = SnapshotId(row[0])
                if snapshot_id in protected:
                    continue
                self._check_cancel(cancellation_check, "enforce quota")
                transaction.execute("DELETE FROM snapshot_bindings WHERE snapshot_id=?", (snapshot_id,))
                transaction.execute(
                    "DELETE FROM source_versions WHERE NOT EXISTS(SELECT 1 FROM snapshot_sources ss WHERE (ss.source_key,ss.revision_digest,ss.parser_version,ss.privacy_version)="
                    "(source_versions.source_key,source_versions.revision_digest,source_versions.parser_version,source_versions.privacy_version))"
                )
                evicted.append(snapshot_id)
                current = self._live_bytes(transaction)
                if current <= limit:
                    break
            if current > limit:
                remaining_open = {
                    SnapshotId(row[0])
                    for row in transaction.execute(
                        "SELECT snapshot_id FROM snapshot_bindings WHERE closed_utc IS NULL"
                    )
                }
                raise CacheQuotaExceededError(
                    limit, current, len(remaining_open | protected)
                )
        return QuotaResult(True, limit, before, current, tuple(evicted))

    def compact(self, *, cancellation_check: CancellationCheck = NEVER_CANCELLED) -> None:
        connection = self._require_open()
        self._check_cancel(cancellation_check, "compact")
        connection.set_progress_handler(lambda: 1 if cancellation_check() else 0, 1_000)
        try:
            checkpoint = connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            if checkpoint and checkpoint[0] != 0:
                raise CacheBusyError(self._busy_timeout_ms)
            free_pages = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
            if free_pages:
                connection.execute(f"PRAGMA incremental_vacuum({free_pages})")
            self._check_cancel(cancellation_check, "compact")
        except sqlite3.OperationalError as error:
            if cancellation_check() or "interrupt" in str(error).lower():
                raise CacheCancelledError("compact") from error
            raise CacheIoError("compact") from error
        finally:
            connection.set_progress_handler(None, 0)

    @classmethod
    def remove_stale_rebuild_files(
        cls,
        cache_path: Path,
        *,
        older_than_utc: datetime,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        cancellation_check: CancellationCheck = NEVER_CANCELLED,
    ) -> int:
        _validate_timeout(busy_timeout_ms)
        cutoff = _utc(older_than_utc, "older_than_utc")
        cls._check_cancel(cancellation_check, "remove stale rebuild files")
        path = Path(os.path.abspath(os.fspath(cache_path)))
        parent = path.parent.resolve()
        pattern = re.compile(
            rf"(?:\.{re.escape(path.name)}\.rebuild-[0-9a-f]{{32}}|"
            rf"\.{re.escape(path.name)}\.old-family-[0-9a-f]{{32}}-(?:wal|shm))\Z"
        )
        lock = _CacheFileLock(path.with_name(path.name + ".lock"), exclusive=True, timeout_ms=busy_timeout_ms, cancellation_check=cancellation_check)
        with lock:
            candidates: list[tuple[int, str, Path]] = []
            try:
                entries = tuple(parent.iterdir())
            except OSError as error:
                raise CacheIoError("list stale rebuild files") from error
            for candidate in entries:
                if not pattern.fullmatch(candidate.name):
                    continue
                try:
                    metadata = candidate.lstat()
                except FileNotFoundError:
                    continue
                except OSError as error:
                    raise CacheIoError("inspect stale rebuild file") from error
                if not stat.S_ISREG(metadata.st_mode) or candidate.parent.resolve() != parent:
                    continue
                modified = datetime.fromtimestamp(metadata.st_mtime_ns / 1_000_000_000, timezone.utc)
                if modified <= cutoff:
                    candidates.append((metadata.st_mtime_ns, candidate.name, candidate))
            selected = sorted(candidates)[:1024]
            cls._check_cancel(cancellation_check, "remove stale rebuild files")
            removed = 0
            for _, _, candidate in selected:
                try:
                    candidate.unlink()
                    removed += 1
                except FileNotFoundError:
                    continue
                except OSError as error:
                    internal = RuntimeError(f"completed_deletions={removed}")
                    internal.__cause__ = error
                    raise CacheIoError("delete stale rebuild file") from internal
            return removed

    def diagnostics(self) -> CacheDiagnostics:
        connection = self._require_open()
        metadata = connection.execute("SELECT schema_version,database_id FROM schema_metadata WHERE singleton=1").fetchone()
        page_live = self._live_bytes(connection)
        wal_path = self._path.with_name(self._path.name + "-wal")
        shm_path = self._path.with_name(self._path.name + "-shm")
        def regular_size(path: Path) -> int:
            try:
                value = path.stat()
                return value.st_size if stat.S_ISREG(value.st_mode) else 0
            except FileNotFoundError:
                return 0

        wal_bytes = regular_size(wal_path)
        allocated = regular_size(self._path) + wal_bytes + regular_size(shm_path)
        counts = connection.execute(
            "SELECT (SELECT count(*) FROM snapshot_bindings),"
            "(SELECT count(*) FROM snapshot_bindings WHERE closed_utc IS NOT NULL),"
            "(SELECT count(*) FROM source_versions),(SELECT count(*) FROM events),"
            "(SELECT count(*) FROM cursor_locators)"
        ).fetchone()
        integrity_ok = connection.execute("PRAGMA quick_check").fetchone()[0] == "ok" and connection.execute("PRAGMA foreign_key_check").fetchone() is None
        return CacheDiagnostics(
            metadata[0], metadata[1], allocated, page_live, wal_bytes,
            counts[0], counts[1], counts[2], counts[3], counts[4],
            self._stale_rebuild_count(self._path), integrity_ok,
        )

    @staticmethod
    def _stale_rebuild_count(path: Path) -> int:
        pattern = re.compile(
            rf"(?:\.{re.escape(path.name)}\.rebuild-[0-9a-f]{{32}}|"
            rf"\.{re.escape(path.name)}\.old-family-[0-9a-f]{{32}}-(?:wal|shm))\Z"
        )
        count = 0
        try:
            for candidate in path.parent.iterdir():
                try:
                    if pattern.fullmatch(candidate.name) and stat.S_ISREG(candidate.lstat().st_mode):
                        count += 1
                except FileNotFoundError:
                    continue
        except FileNotFoundError:
            return 0
        return count


__all__ = [
    "DEFAULT_BUSY_TIMEOUT_MS", "DEFAULT_CACHE_PATH", "DEFAULT_MAX_BYTES",
    "LATEST_SCHEMA_VERSION", "MIGRATIONS", "NEVER_CANCELLED",
    "PRIVACY_REGISTRY_VERSION", "REDACTION_MARKER", "CacheBusyError",
    "CacheCancelledError", "CacheClosedError", "CacheCorruptError",
    "CacheCursorConflictError", "CacheDiagnostics", "CacheDurabilityError",
    "CacheEventNotFoundError", "CacheIdentityCollisionError", "CacheIoError",
    "CacheMigrationError", "CachePrivacyViolationError", "CachePublicationError",
    "CachePublicationVerificationError", "CacheQuotaExceededError",
    "CacheRevisionConflictError", "CacheSchemaTooNewError",
    "CacheSchemaUnsupportedError", "CacheSnapshotNotFoundError",
    "CacheValidationError", "CursorBinding", "CursorConflictReason",
    "CursorLocatorId", "CursorOperation", "EventCacheError", "EventCachePolicy",
    "EventFilter", "EventId", "EventPage", "EventQuery", "EventRepository",
    "EvidenceMethod", "NormalizedDiagnostic", "NormalizedEventRecord",
    "OpenResult", "PublicationPhase", "PurgeReason", "PurgeRequest",
    "PurgeResult", "QuotaResult", "RecoveryAction", "SnapshotBinding",
    "SnapshotBindingInput", "SnapshotId", "SnapshotRevisionId", "SnapshotState",
    "SourceKey", "SourcePublishResult", "SourceRevision", "SourceRevisionDigest",
    "StaleSourceSet", "StoredEvent", "source_key_for_path",
]
