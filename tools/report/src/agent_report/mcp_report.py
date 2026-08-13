# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Select Codex tasks and return bounded report or query results.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

"""MCP-facing task selection, report generation, and telemetry queries."""

from __future__ import annotations

import os
import json
import math
import re
import secrets
import hashlib
import shutil
import stat
import tempfile
import threading
import sys
from contextvars import ContextVar
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from enum import Enum
from pathlib import Path
from time import monotonic
from types import ModuleType
from typing import Any, Literal, cast
from urllib.parse import urlparse
from urllib.request import url2pathname
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import application_service as service_types
from . import event_cache, static_export

MAX_INLINE_BYTES = 65_536
DEFAULT_INLINE_BYTES = 65_536
DEFAULT_OUTPUT = Path(".codex/report")
REPORT_FILENAMES = {
    "html": "report.html",
    "json": "report.json",
    "turns_csv": "turns.csv",
    "work_units_csv": "work-units.csv",
    "markdown": "report.md",
}
InlineFormat = Literal["html", "markdown", "json"]
TimeRangeMeasure = Literal[
    "wall_time",
    "uncached_input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cost_usd",
]
BucketMinutes = Literal[1, 5, 15, 30, 60]
RUN_CACHE_FRESH_SECONDS = 60.0
NORMALIZATION_VERSION = "agent-report-service-v1"
_CURRENT_OPERATION_ID: ContextVar[str] = ContextVar("agent_report_operation_id")
_CURRENT_OUTPUT_ROOT: ContextVar[Path | None] = ContextVar(
    "agent_report_output_root", default=None
)
_STAGING_NAME = re.compile(r"\.agent-report-export-[0-9a-f]{32}\Z")


class _OutputAuthorizationError(ValueError):
    """Reject an MCP publication target without disclosing host path details."""


def _is_symlink_or_reparse(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _canonical_output_root(root: Path) -> Path:
    try:
        canonical = root.expanduser().resolve(strict=True)
        metadata = canonical.lstat()
    except OSError as error:
        raise _OutputAuthorizationError(
            "The authorized report output root is unavailable."
        ) from error
    if _is_symlink_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise _OutputAuthorizationError(
            "The authorized report output root is not a regular directory."
        )
    return canonical


def _authorized_output_target(
    selected: Path,
    root: Path,
    *,
    require_existing_parent: bool,
) -> tuple[Path, Path]:
    """Bind an MCP target lexically beneath a canonical symlink-free root."""

    canonical_root = _canonical_output_root(root)
    expanded = selected.expanduser()
    candidate = Path(
        os.path.abspath(
            os.fspath(expanded if expanded.is_absolute() else canonical_root / expanded)
        )
    )
    try:
        relative = candidate.relative_to(canonical_root)
    except ValueError as error:
        raise _OutputAuthorizationError(
            "The report output target is outside the authorized workspace root."
        ) from error
    current = canonical_root
    missing_seen = False
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            missing_seen = True
            continue
        except OSError as error:
            raise _OutputAuthorizationError(
                "The report output target cannot be safely validated."
            ) from error
        if missing_seen or _is_symlink_or_reparse(metadata):
            raise _OutputAuthorizationError(
                "The report output target contains a symbolic-link component."
            )
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            raise _OutputAuthorizationError(
                "A report output target ancestor is not a directory."
            )
    if require_existing_parent:
        try:
            parent_metadata = candidate.parent.lstat()
        except OSError as error:
            raise _OutputAuthorizationError(
                "The report output target requires an existing authorized parent."
            ) from error
        if _is_symlink_or_reparse(parent_metadata) or not stat.S_ISDIR(
            parent_metadata.st_mode
        ):
            raise _OutputAuthorizationError(
                "The report output target parent is not a regular directory."
            )
    return canonical_root, candidate


def _open_authorized_directory(root: Path, directory: Path) -> int | None:
    """Create and open a target directory without following path components."""

    relative = directory.relative_to(root)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    if os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd:
        directory.mkdir(parents=True, exist_ok=True)
        _authorized_output_target(directory, root, require_existing_parent=True)
        return None
    descriptor = os.open(root, directory_flags | no_follow)
    try:
        for part in relative.parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            metadata = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
            if _is_symlink_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise _OutputAuthorizationError(
                    "The report output directory contains an unsafe component."
                )
            next_descriptor = os.open(
                part, directory_flags | no_follow, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _write_authorized_file(
    directory: Path, directory_descriptor: int | None, name: str, content: str
) -> Path:
    """Write one classic artifact with a no-follow leaf check."""

    payload = content.encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    if directory_descriptor is None:
        path = directory / name
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            pass
        else:
            if _is_symlink_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
                raise _OutputAuthorizationError(
                    "A report output artifact is not a regular file."
                )
        descriptor = os.open(path, flags, 0o600)
    else:
        try:
            metadata = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if _is_symlink_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
                raise _OutputAuthorizationError(
                    "A report output artifact is not a regular file."
                )
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_descriptor)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return directory / name


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def application_service_config(
    runtime: ModuleType, roots: tuple[Path, ...]
) -> service_types.ApplicationServiceConfig:
    """Build immutable service configuration from packaged runtime resources."""

    pricing_path = Path(runtime.PRICING_FILE).resolve()
    formatter_path = Path(runtime.DEFAULT_TOOL_FORMATTER_CONFIG).resolve()
    pricing_version, pricing_digest = runtime._pricing_metadata()
    formatter = runtime._load_tool_formatter_config(formatter_path)
    return service_types.ApplicationServiceConfig(
        authorized_source_roots=roots,
        parser_version=str(runtime.CODEX_ROLLOUT_PARSER_VERSION),
        pricing_version=pricing_version or "unavailable",
        pricing_digest=pricing_digest or _digest_file(pricing_path),
        formatter_version=str(formatter.version),
        formatter_digest=_digest_file(formatter_path),
    )


@dataclass(frozen=True, slots=True)
class _NormalizedRun:
    source_revision: str
    privacy_validated: bool
    run: object
    heatmap_pricing: service_types.HeatmapPricingAuthority
    scope: service_types.ReportScope
    sources: tuple[event_cache.SourceRevision, ...]
    records: tuple[
        tuple[
            event_cache.SourceRevision, tuple[event_cache.NormalizedEventRecord, ...]
        ],
        ...,
    ]


@dataclass(frozen=True, slots=True)
class _ReadHandle:
    snapshot_id: str
    revision_id: str
    source_revision: str
    cache_snapshot_id: str
    run: object
    heatmap_pricing: service_types.HeatmapPricingAuthority
    scope: service_types.ReportScope


@dataclass(frozen=True, slots=True)
class _StagedExport:
    mode: service_types.ExportMode
    stage_id: str
    surface: service_types.AutomationSurface
    authorized_root: Path | None
    source: Path
    result: static_export.ExportResult


class _RuntimeDiscovery:
    def __init__(self, runtime: ModuleType) -> None:
        self._runtime = runtime

    def preflight(self, scope, roots, cancellation, progress):  # type: ignore[no-untyped-def]
        return self._discover(scope, roots, cancellation)

    def recheck(self, scope, roots, cancellation, progress):  # type: ignore[no-untyped-def]
        return self._discover(scope, roots, cancellation)

    def _discover(self, scope, roots, cancellation):  # type: ignore[no-untyped-def]
        candidates = sorted(
            {
                path.resolve()
                for root in roots
                for path in self._runtime._candidate_rollouts(root)
            }
        )
        if cancellation.is_cancelled():
            raise service_types.DiscoveryFailure(
                "cancelled", "Report discovery was cancelled.", True
            )
        try:
            paths, diagnostics, _parent = self._runtime._discover_rollout_paths(
                scope.root_thread_id,
                candidates,
                include_children=scope.include_children,
                include_delegations=scope.include_collaborators,
                index_path=self._runtime._default_codex_discovery_index_path(),
            )
        except ValueError as error:
            raise service_types.DiscoveryFailure(
                "not_found", "The selected report task was not found.", True
            ) from error
        sources: list[service_types.DiscoveredSource] = []
        digest = hashlib.sha256()
        for index, path in enumerate(paths):
            stat = path.stat()
            revision = hashlib.sha256(path.read_bytes()).hexdigest()
            source_key = event_cache.source_key_for_path(path)
            identity = self._runtime._rollout_identity(path)
            relationship: service_types.SourceRelationship = "root"
            if index:
                relationship = "child" if identity and identity[1] else "collaborator"
            sources.append(
                service_types.DiscoveredSource(
                    str(source_key), path, revision, stat.st_size, relationship
                )
            )
            digest.update(str(source_key).encode())
            digest.update(revision.encode())
        warnings = tuple(
            service_types.WarningRecord("REPORT_DISCOVERY_WARNING", item[:512])
            for item in diagnostics[:100]
        )
        return service_types.DiscoveredScope(
            scope,
            digest.hexdigest(),
            tuple(sources),
            len(sources),
            sum(source.byte_count for source in sources),
            sum(source.relationship == "child" for source in sources),
            sum(source.relationship == "collaborator" for source in sources),
            0,
            len(sources),
            warnings,
        )


def _aware(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _event_label(kind: str, *, tool_name: str | None = None) -> str:
    """Return a bounded label without copying transcript or path-shaped content."""

    if tool_name:
        return f"{tool_name.replace('_', ' ').title()} tool call"
    return f"{kind.replace('_', ' ').title()} event"


class _RuntimeNormalization:
    def __init__(
        self,
        runtime: ModuleType,
        *,
        seal: bool,
        allow_aborted: bool,
        title: str,
        thread_titles: Mapping[str, str],
        workers: int,
        pricing_version: str = "unavailable",
    ) -> None:
        self._runtime = runtime
        self._seal = seal
        self._allow_aborted = allow_aborted
        self._title = title
        self._thread_titles = dict(thread_titles)
        self._workers = workers
        self._pricing_version = pricing_version

    def normalize(
        self,
        discovered,
        parser_version,
        pricing_digest,
        formatter_digest,
        cancellation,
        progress,
    ):  # type: ignore[no-untyped-def]
        run = cast(
            Any,
            self._runtime.build_codex_rollout_run(
                discovered.scope.root_thread_id,
                [
                    path.parent
                    for path in (
                        source.authorized_path for source in discovered.sources
                    )
                ],
                seal=self._seal,
                allow_aborted=self._allow_aborted,
                include_children=discovered.scope.include_children,
                include_delegations=discovered.scope.include_collaborators,
                title=self._title,
                thread_titles=self._thread_titles,
                workers=self._workers,
                candidate_paths=[
                    source.authorized_path for source in discovered.sources
                ],
                discovery_index_path=self._runtime._default_codex_discovery_index_path(),
                cancelled=cancellation.is_cancelled,
            ),
        )
        source_by_path = {
            source.authorized_path: source for source in discovered.sources
        }
        grouped: dict[str, list[event_cache.NormalizedEventRecord]] = {
            source.source_key: [] for source in discovered.sources
        }
        ordinals: dict[str, int] = {
            source.source_key: 0 for source in discovered.sources
        }
        for thread in run.threads:
            for activity in thread.activities:
                source = source_by_path.get(Path(activity.source_path).resolve())
                occurred = _aware(activity.event_timestamp)
                if source is None or occurred is None:
                    continue
                ordinal = ordinals[source.source_key]
                ordinals[source.source_key] += 1
                grouped[source.source_key].append(
                    event_cache.NormalizedEventRecord(
                        ordinal,
                        occurred.astimezone(timezone.utc),
                        activity.activity_type,
                        thread.thread_id,
                        activity.turn_id,
                        None,
                        None,
                        activity.model or None,
                        None,
                        event_cache.EvidenceMethod.MEASURED,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        _event_label(activity.activity_type),
                        None,
                        None,
                        None,
                        len(activity.content),
                        None,
                        0,
                        "sanitized",
                    )
                )
            for tool in thread.tool_intervals:
                source = source_by_path.get(Path(tool.source_path).resolve())
                occurred = _aware(tool.started_at)
                if source is None or occurred is None:
                    continue
                ordinal = ordinals[source.source_key]
                ordinals[source.source_key] += 1
                grouped[source.source_key].append(
                    event_cache.NormalizedEventRecord(
                        ordinal,
                        occurred.astimezone(timezone.utc),
                        "tool",
                        thread.thread_id,
                        tool.turn_id,
                        None,
                        tool.tool_name,
                        tool.model or None,
                        "completed" if tool.completed_at else "active",
                        event_cache.EvidenceMethod.MEASURED,
                        tool.duration_ms,
                        None,
                        None,
                        None,
                        None,
                        None,
                        _event_label("tool", tool_name=tool.tool_name),
                        None,
                        None,
                        None,
                        None,
                        None,
                        0,
                        "sanitized",
                    )
                )
        cache_sources: list[event_cache.SourceRevision] = []
        records: list[
            tuple[
                event_cache.SourceRevision,
                tuple[event_cache.NormalizedEventRecord, ...],
            ]
        ] = []
        for source in discovered.sources:
            stat = source.authorized_path.stat()
            cached = event_cache.SourceRevision(
                event_cache.SourceKey(source.source_key),
                event_cache.SourceRevisionDigest(
                    hashlib.sha256(
                        f"{source.source_revision}:{NORMALIZATION_VERSION}".encode()
                    ).hexdigest()
                ),
                source.byte_count,
                stat.st_mtime_ns,
                parser_version,
                event_cache.PRIVACY_REGISTRY_VERSION,
            )
            cache_sources.append(cached)
            records.append((cached, tuple(grouped[source.source_key])))
        records.sort(key=lambda item: str(item[0].source_key))
        cache_sources = [item[0] for item in records]
        heatmap_pricing = _capture_heatmap_pricing(
            self._runtime, run, self._pricing_version, pricing_digest
        )
        return _NormalizedRun(
            discovered.source_revision,
            True,
            run,
            heatmap_pricing,
            discovered.scope,
            tuple(cache_sources),
            tuple(records),
        )


class _RepositoryAdapter:
    def __init__(
        self,
        repository: event_cache.EventRepository,
        config: service_types.ApplicationServiceConfig,
    ) -> None:
        self._repository = repository
        self._config = config
        self._runs: dict[str, tuple[str, str, object, service_types.HeatmapPricingAuthority, service_types.ReportScope]] = {}

    def known_event_count(self, source_revision: str) -> int | None:
        return None

    def reuse_or_publish(self, revision: _NormalizedRun, cancellation, progress):  # type: ignore[no-untyped-def]
        run = cast(Any, revision.run)
        for source, records in revision.records:
            self._repository.replace_source(
                source, records, cancellation_check=cancellation.is_cancelled
            )
        cache_snapshot_id = "snap_" + secrets.token_hex(12)
        binding = self._repository.publish_snapshot(
            snapshot_id=event_cache.SnapshotId(cache_snapshot_id),
            expected_active_revision=None,
            binding=event_cache.SnapshotBindingInput(
                run.root_thread_id,
                revision.scope.include_children,
                revision.scope.include_collaborators,
                self._config.parser_version,
                self._config.pricing_version,
                self._config.formatter_version,
                event_cache.PRIVACY_REGISTRY_VERSION,
                (_aware(run.observed_at) or datetime.now(timezone.utc)).astimezone(
                    timezone.utc
                ),
                event_cache.SnapshotState.SEALED
                if run.state == "sealed"
                else event_cache.SnapshotState.LIVE,
            ),
            sources=revision.sources,
            cancellation_check=cancellation.is_cancelled,
        )
        self._runs[str(binding.revision_id)] = (
            cache_snapshot_id,
            revision.source_revision,
            revision.run,
            revision.heatmap_pricing,
            revision.scope,
        )
        return service_types.PublishedRevision(
            str(binding.revision_id), revision.source_revision
        )

    def open_read(self, snapshot_id: str, revision_id: str, run: object, heatmap_pricing: service_types.HeatmapPricingAuthority) -> _ReadHandle:
        cache_snapshot_id, source_revision, published_run, published_pricing, scope = self._runs[revision_id]
        self._repository.get_snapshot(event_cache.SnapshotId(cache_snapshot_id))
        if published_run is not run or published_pricing is not heatmap_pricing:
            raise service_types.RepositoryFailure(
                "binding_conflict", "The normalized run does not match the published revision.", True
            )
        return _ReadHandle(snapshot_id, revision_id, source_revision, cache_snapshot_id, run, heatmap_pricing, scope)

    def release_read(self, handle: _ReadHandle) -> None:
        return None

    def close(self) -> None:
        self._repository.close()


class _Ids:
    def __init__(self, repository: _RepositoryAdapter) -> None:
        del repository

    def new_snapshot_id(self) -> str:
        return "snap_" + secrets.token_hex(12)

    def new_token_key(self) -> bytes:
        return secrets.token_bytes(32)


class _Clock:
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)


class _Logger:
    def info(self, event: str, fields: Mapping[str, str | int | bool | None]) -> None:
        return None

    def error(self, event: str, fields: Mapping[str, str | int | bool | None]) -> None:
        operation_id = fields.get("operation_id")
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": "error",
            "event": "worker.internal_failure",
            "operation_id": operation_id if isinstance(operation_id, str) else None,
            "code": "REPORT_WORKER_INTERNAL",
            "message": f"{event}: {dict(fields)}"[:4096],
        }
        print(json.dumps(record, separators=(",", ":"), ensure_ascii=True), file=sys.stderr, flush=True)


def _slice(
    items: list[object], after: str | None, limit: int
) -> service_types.QuerySlice[object]:
    start = int(after or "0")
    selected = items[start : start + limit]
    next_position = str(start + limit) if start + limit < len(items) else None
    return service_types.QuerySlice(tuple(selected), next_position)


def _bounded_text(value: object, limit: int = 512) -> str:
    """Return one compact privacy-safe display string within DTO limits."""

    compact = " ".join(str(value or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _bounded_json_content(value: str, maximum_bytes: int) -> str:
    """Bound a safe method description by encoded JSON string-content bytes."""

    if len(json.dumps(value, ensure_ascii=False)[1:-1].encode("utf-8")) <= maximum_bytes:
        return value
    retained = ""
    for character in value:
        candidate = retained + character
        if len(json.dumps(candidate, ensure_ascii=False)[1:-1].encode("utf-8")) > maximum_bytes:
            break
        retained = candidate
    return retained


def _capture_heatmap_pricing(
    runtime: ModuleType,
    run: object,
    pricing_version: str,
    pricing_digest: str,
) -> service_types.HeatmapPricingAuthority:
    """Evaluate classic response pricing once and freeze revision-bound lookups."""

    assessments: list[tuple[int, int, service_types.HeatmapCostAssessment]] = []
    for thread_index, thread in enumerate(getattr(run, "threads", ())):
        for response_index, response in enumerate(getattr(thread, "responses", ())):
            cost = runtime._cost_for_response(thread, response)
            status = str(getattr(cost, "status", "") or "").casefold()
            evidence_method: service_types.HeatmapEvidenceMethod = (
                "measured" if status == "recorded" else
                "estimated" if status == "estimated" else
                "derived" if status == "derived" else
                "unavailable"
            )
            raw_value = getattr(cost, "total_cost", None)
            value = (
                float(raw_value)
                if isinstance(raw_value, (int, float))
                and not isinstance(raw_value, bool)
                and math.isfinite(float(raw_value))
                and float(raw_value) >= 0
                else None
            )
            if value is None:
                evidence_method = "unavailable"
            assessments.append((
                thread_index,
                response_index,
                service_types.HeatmapCostAssessment(
                    value,
                    evidence_method,
                    _bounded_json_content(
                        str(getattr(cost, "method", "unavailable") or "unavailable"),
                        256,
                    ),
                ),
            ))
    return service_types.HeatmapPricingAuthority(
        pricing_version, pricing_digest, tuple(assessments)
    )


def _evidence_kind(value: object) -> service_types.EvidenceKind:
    """Map detailed runtime provenance onto the shared epistemic vocabulary."""

    normalized = str(value or "").casefold()
    if normalized in {"measured", "direct", "recorded", "exact"}:
        return "measured"
    if normalized == "inferred":
        return "inferred"
    if normalized in {"", "unavailable"}:
        return "unavailable"
    return "derived"


def _safe_argument_object(*values: object) -> dict[str, object]:
    """Decode only an already-sanitized tool argument summary."""

    for value in values:
        if not isinstance(value, str) or not value:
            continue
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return cast(dict[str, object], parsed)
    return {}


def _resolve_agent_id(
    target: object, source: object, threads: Mapping[str, object]
) -> str | None:
    if not isinstance(target, str) or not target.strip():
        return None
    normalized = target.strip().rstrip("/")
    if normalized in threads:
        return normalized
    if normalized in {"root", "/root"}:
        roots = [
            thread_id
            for thread_id, thread in threads.items()
            if not getattr(thread, "parent_thread_id", "")
        ]
        return roots[0] if len(roots) == 1 else None
    tail = normalized.rsplit("/", 1)[-1]
    matches = []
    for thread_id, thread in threads.items():
        names = {
            str(value).rstrip("/").rsplit("/", 1)[-1]
            for value in (
                thread_id,
                getattr(thread, "agent_path", ""),
                getattr(thread, "agent_nickname", ""),
            )
            if value
        }
        if tail in names:
            matches.append(thread_id)
    related = [
        thread_id
        for thread_id in matches
        if getattr(threads[thread_id], "parent_thread_id", "")
        == getattr(source, "thread_id", "")
        or getattr(source, "parent_thread_id", "") == thread_id
    ]
    candidates = related or matches
    return candidates[0] if len(candidates) == 1 else None


def _delegated_root_id(
    agent_id: str | None, threads: Mapping[str, object]
) -> str | None:
    current = agent_id
    visited: set[str] = set()
    while current in threads and current not in visited:
        visited.add(cast(str, current))
        parent = getattr(threads[cast(str, current)], "parent_thread_id", "")
        if not parent or parent not in threads:
            return cast(str, current)
        current = parent
    return agent_id


def _coordination_row(
    occurred_at: object,
    operation: str,
    work_item_id: str | None,
    delegated_root_id: str | None,
    agent_id: str | None,
    related_agent_ids: tuple[str, ...],
    summary: object,
    evidence: service_types.EvidenceKind,
    ordinal: object,
) -> service_types.CoordinationRow:
    occurred = _aware(occurred_at)
    if occurred is None:
        raise ValueError("coordination evidence requires a timestamp")
    seed = (
        f"{occurred.isoformat()}:{operation}:{work_item_id}:"
        f"{delegated_root_id}:{agent_id}:{ordinal}"
    )
    return service_types.CoordinationRow(
        "coord_" + hashlib.sha256(seed.encode()).hexdigest()[:24],
        occurred,
        work_item_id,
        delegated_root_id,
        agent_id,
        related_agent_ids,
        _bounded_text(operation, 128),
        _bounded_text(summary),
        evidence,
        None,
    )


class _RuntimeQueries:
    def __init__(self, repository: event_cache.EventRepository) -> None:
        self._repository = repository

    def get_summary(self, handle, snapshot, cancellation):  # type: ignore[no-untyped-def]
        run = handle.run
        root = next(
            (item for item in run.threads if item.thread_id == run.root_thread_id),
            run.threads[0],
        )
        usage = run.usage_totals
        context = run.context_summary
        inference = run.inference_summary
        claim_count = sum(
            len(getattr(thread, "work_item_claim_events", ()))
            for thread in run.threads
        )

        def metric(
            metric_id: str,
            label: str,
            value: int | float | str | None,
            unit: str | None,
            evidence: service_types.EvidenceKind,
            provenance: str,
        ) -> service_types.MetricValue:
            if isinstance(value, float):
                displayed = f"{value:.2f}".rstrip("0").rstrip(".")
            elif value is None:
                displayed = "Unavailable"
            else:
                displayed = str(value)
            return service_types.MetricValue(
                metric_id, label, value, displayed, unit, evidence, provenance, None
            )

        cost = getattr(getattr(run, "cost", None), "total_cost", None)
        cost_value = float(cost) if cost is not None else None
        model_names = {
            name
            for thread in run.threads
            for name in (getattr(thread, "model", None),)
            if name
        }
        metrics = (
            service_types.MetricGroup(
                "overview", "Overview", (
                    metric("agents", "Agents", len(run.threads), "agents", "derived", "included scope"),
                    metric("turns", "Turns", sum(len(t.turns) for t in run.threads), "turns", "measured", "rollout events"),
                    metric("wall_time", "Wall time", run.wall_time_ms, "ms", "measured", "run interval"),
                    metric("peak_concurrency", "Peak concurrency", run.peak_concurrency, "agents", "derived", "run intervals"),
                ),
            ),
            service_types.MetricGroup(
                "model", "Model usage", (
                    metric("models", "Models", len(model_names), "models", "derived", "thread metadata"),
                    metric("input_tokens", "Input tokens", usage.input_tokens, "tokens", "measured", "usage records"),
                    metric("cached_input_tokens", "Cached input tokens", usage.cached_input_tokens, "tokens", "measured", "usage records"),
                    metric("output_tokens", "Output tokens", usage.output_tokens, "tokens", "measured", "usage records"),
                    metric("recorded_cost", "Recorded cost", cost_value, "USD", "measured" if cost_value is not None else "unavailable", "pricing records"),
                ),
            ),
            service_types.MetricGroup(
                "context", "Context and compaction", (
                    metric("current_tokens", "Current context", context.current_total_tokens, "tokens", _evidence_kind(context.evidence), "context snapshots"),
                    metric("capacity", "Context capacity", context.capacity, "tokens", _evidence_kind(context.evidence), "context snapshots"),
                    metric("remaining_tokens", "Remaining context", context.remaining_tokens, "tokens", _evidence_kind(context.evidence), "context snapshots"),
                    metric("compactions", "Compactions", context.compaction_count, "compactions", _evidence_kind(context.evidence), "compaction records"),
                ),
            ),
            service_types.MetricGroup(
                "inference", "Inference", (
                    metric("calls", "Calls", inference.call_count, "calls", _evidence_kind(inference.evidence), "response usage"),
                    metric("reasoning_tokens", "Reasoning tokens", inference.reasoning_tokens, "tokens", _evidence_kind(inference.evidence), "response usage"),
                    metric("inference_time", "Inference time", inference.inference_time_ms, "ms", _evidence_kind(inference.evidence), "response intervals"),
                    metric("decode_rate", "Decode rate", inference.decode_tokens_per_second, "tokens/s", _evidence_kind(inference.evidence), "response intervals"),
                ),
            ),
            service_types.MetricGroup(
                "runtime", "Runtime", (
                    metric("agent_time", "Agent time", run.agent_time_ms, "ms", "derived", "runtime intervals"),
                    metric("active_time", "Active time", run.active_time_ms, "ms", "derived", "runtime intervals"),
                    metric("tool_time", "Tool time", run.tool_time_ms, "ms", "measured", "tool intervals"),
                    metric("critical_path", "Critical path", run.critical_path_ms, "ms", "derived", "runtime intervals"),
                ),
            ),
            service_types.MetricGroup(
                "waits", "Waits", (
                    metric("all_agents_waiting", "All agents waiting", run.all_agents_waiting_ms, "ms", "derived", "runtime intervals"),
                    metric("waiting_states", "Waiting states", sum(1 for item in run.runtime_states if "wait" in item.state), "states", "derived", "runtime state summaries"),
                ),
            ),
            service_types.MetricGroup(
                "work_items", "Work items", (
                    metric("work_units", "Work units", len(run.work_units), "work units", "derived", "turn attribution"),
                    metric("claim_segments", "Claim segments", len(run.work_item_segments), "segments", "measured", "claim records"),
                ),
            ),
            service_types.MetricGroup(
                "claims", "Claims", (
                    metric("claim_events", "Claim events", claim_count, "events", "measured", "claim records"),
                ),
            ),
            service_types.MetricGroup(
                "provenance", "Provenance", (
                    metric("sources", "Sources", len(run.source_manifest), "sources", "measured", "source manifest"),
                    metric("diagnostics", "Diagnostics", len(run.diagnostics), "diagnostics", "measured", "bounded diagnostics"),
                    metric("parser_version", "Parser version", run.parser_version, None, "measured", "snapshot metadata"),
                ),
            ),
        )
        recent = tuple(
            service_types.SignificantActivity(
                str(item.event_id),
                item.record.timestamp_utc,
                item.record.summary_text or item.record.kind,
                item.record.evidence_method.value,
            )
            for item in sorted(
                self._stored_events(
                    handle, service_types.EventFilters(), descending=True
                ),
                key=lambda value: (value.record.timestamp_utc, str(value.event_id)),
                reverse=True,
            )[:20]
        )
        range_start = _aware(run.wall_started_at)
        range_end = _aware(run.wall_ended_at)
        if range_start is None or range_end is None or range_start >= range_end:
            observed = snapshot.observation_time.astimezone(timezone.utc)
            range_start = observed - timedelta(microseconds=1)
            range_end = observed
        return service_types.SummaryResult(
            snapshot.snapshot_id,
            snapshot.revision_id,
            root.task_title or run.run_label or "Agent Report",
            root.task_title or None,
            run.state,
            snapshot.scope,
            snapshot.observation_time,
            snapshot.mode,
            service_types.TimeRange(range_start, range_end),
            metrics,
            ("normalized event cache", "Codex rollout aggregates"),
            recent,
            snapshot.warnings,
        )

    def list_agents(self, handle, filters, sort, after, limit, cancellation):  # type: ignore[no-untyped-def]
        rows = [
            service_types.AgentRow(
                item.thread_id,
                item.parent_thread_id or None,
                item.agent_nickname or None,
                item.agent_role or None,
                item.terminal_state,
                _aware(item.started_at),
                _aware(item.last_observed_at)
                if item.terminal_state != "active"
                else None,
                _aware(item.last_observed_at),
                len(item.turns),
                len(item.activities) + len(item.tool_intervals) + len(item.mcp_calls),
                "measured",
            )
            for item in handle.run.threads
            if (not filters.agent_ids or item.thread_id in filters.agent_ids)
            and (not filters.roles or item.agent_role in filters.roles)
            and (not filters.states or item.terminal_state in filters.states)
            and (
                not filters.query
                or filters.query.casefold()
                in f"{item.task_title} {item.agent_nickname} {item.agent_role}".casefold()
            )
        ]

        rows.sort(key=lambda row: row.agent_id)
        rows.sort(
            key=lambda row: getattr(row, sort.key)
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=sort.direction == "descending",
        )
        return _slice(cast(list[object], rows), after, limit)

    def list_turns(self, handle, filters, sort, after, limit, cancellation):  # type: ignore[no-untyped-def]
        rows = []
        for thread in handle.run.threads:
            for item in thread.turns:
                started = _aware(item.started_at)
                ended = _aware(item.completed_at)
                if started is None:
                    continue
                if (
                    filters.turn_ids
                    and item.turn_id not in filters.turn_ids
                    or filters.agent_ids
                    and thread.thread_id not in filters.agent_ids
                    or filters.states
                    and item.outcome not in filters.states
                ):
                    continue
                if (
                    filters.from_time
                    and (ended or started) < filters.from_time
                    or filters.to_time
                    and started >= filters.to_time
                ):
                    continue
                rows.append(
                    service_types.TurnRow(
                        item.turn_id,
                        thread.thread_id,
                        started,
                        ended,
                        item.outcome,
                        0,
                        item.activity or None,
                        "measured",
                    )
                )
        rows.sort(key=lambda row: row.turn_id)
        rows.sort(
            key=lambda row: getattr(row, sort.key)
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=sort.direction == "descending",
        )
        return _slice(cast(list[object], rows), after, limit)

    def _stored_events(self, handle, filters, *, descending=False):  # type: ignore[no-untyped-def]
        page = self._repository.query_events(
            event_cache.EventQuery(
                event_cache.SnapshotId(handle.cache_snapshot_id),
                event_cache.SnapshotRevisionId(handle.revision_id),
                event_cache.EventFilter(
                    filters.from_time,
                    filters.to_time,
                    filters.agent_ids[0] if len(filters.agent_ids) == 1 else None,
                    filters.turn_ids[0] if len(filters.turn_ids) == 1 else None,
                    None,
                    filters.kinds[0] if len(filters.kinds) == 1 else None,
                ),
                500,
                descending=descending,
            )
        )
        return [
            item
            for item in page.items
            if (not filters.event_ids or str(item.event_id) in filters.event_ids)
            and (not filters.agent_ids or item.record.agent_id in filters.agent_ids)
            and (not filters.turn_ids or item.record.turn_id in filters.turn_ids)
            and (not filters.kinds or item.record.kind in filters.kinds)
        ]

    def list_events(self, handle, filters, sort, after, limit, cancellation):  # type: ignore[no-untyped-def]
        rows = [
            service_types.EventRow(
                str(item.event_id),
                item.record.timestamp_utc,
                item.record.agent_id,
                item.record.turn_id,
                item.record.kind,
                item.record.summary_text
                or item.record.argument_summary
                or item.record.kind,
                item.record.evidence_method.value,
                str(item.source_key),
                True,
            )
            for item in self._stored_events(handle, filters)
        ]
        rows.sort(key=lambda row: row.event_id)
        rows.sort(
            key=lambda row: getattr(row, sort.key),
            reverse=sort.direction == "descending",
        )
        return _slice(cast(list[object], rows), after, limit)

    def query_snapshot_time_range(self, handle, request, cancellation):  # type: ignore[no-untyped-def]
        return service_types._query_heatmap_semantics(handle, request, cancellation)

    def query_sequence(self, handle, request, after, cancellation):  # type: ignore[no-untyped-def]
        run = handle.run
        threads = {thread.thread_id: thread for thread in run.threads}
        labels = {
            thread.thread_id: thread.agent_nickname
            or thread.task_title
            or thread.thread_id
            for thread in run.threads
        }
        raw_rows: list[service_types.SequenceRow] = []

        def add_row(
            occurred_at: object,
            kind: str,
            source: str | None,
            target: str | None,
            summary: str,
            evidence: service_types.EvidenceKind,
            ordinal: object,
            event_id: str | None = None,
            reasoning_available: bool = False,
        ) -> None:
            occurred = _aware(occurred_at)
            if occurred is None:
                return
            seed = f"{occurred.isoformat()}:{kind}:{source}:{target}:{ordinal}"
            raw_rows.append(service_types.SequenceRow(
                "seq_" + hashlib.sha256(seed.encode()).hexdigest()[:24], None,
                occurred, source, labels.get(source or ""), target,
                labels.get(target or ""), kind, _bounded_text(summary), evidence,
                event_id, 1, reasoning_available,
            ))

        for thread in run.threads:
            parent = thread.parent_thread_id or None
            if parent in threads:
                add_row(thread.started_at, "spawn", parent, thread.thread_id,
                        f"Spawned {labels[thread.thread_id]}", "derived", 0)
            for tool in thread.tool_intervals:
                kind = {"send_message": "message", "followup_task": "followup", "interrupt_agent": "interrupt"}.get(tool.tool_name)
                if kind is None:
                    continue
                arguments = _safe_argument_object(tool.argument_summary, tool.argument_content)
                target = _resolve_agent_id(arguments.get("target"), thread, threads)
                if target is None or target == thread.thread_id:
                    continue
                message = arguments.get("message")
                summary = kind.replace("_", " ").title()
                if isinstance(message, str) and message.strip():
                    summary = f"{summary}: {message}"
                add_row(tool.started_at, kind, thread.thread_id, target, summary,
                        "measured", tool.source_start_ordinal)
            if parent in threads:
                for turn in thread.turns:
                    if turn.outcome != "active" and turn.completed_at:
                        kind = turn.outcome if turn.outcome in {"aborted", "failed"} else "complete"
                        add_row(turn.completed_at, kind, thread.thread_id, parent,
                                f"Turn {turn.outcome}", "measured", turn.source_ordinal)

        if request.filters.include_reasoning:
            for item in self._stored_events(handle, request.filters.event_filters):
                if item.record.kind not in {"reasoning", "assistant"}:
                    continue
                add_row(item.record.timestamp_utc, item.record.kind,
                        item.record.agent_id, item.record.agent_id,
                        item.record.summary_text or item.record.kind,
                        item.record.evidence_method.value, item.record.source_ordinal,
                        str(item.event_id), True)

        event_filters = request.filters.event_filters
        rows = [row for row in raw_rows if (
            (request.filters.focus_agent_id is None or request.filters.focus_agent_id in {row.from_agent_id, row.to_agent_id})
            and (not event_filters.agent_ids or any(agent in event_filters.agent_ids for agent in (row.from_agent_id, row.to_agent_id) if agent))
            and (not event_filters.kinds or row.kind in event_filters.kinds)
            and (event_filters.from_time is None or row.occurred_at >= event_filters.from_time)
            and (event_filters.to_time is None or row.occurred_at < event_filters.to_time)
        )]
        rows.sort(key=lambda row: row.sequence_id)
        rows.sort(key=lambda row: row.occurred_at, reverse=request.sort.direction == "descending")
        if request.filters.grouping == "repeated_messages":
            collapsed: list[service_types.SequenceRow] = []
            for row in rows:
                if collapsed and (
                    row.kind in {"message", "followup"}
                    and (
                        collapsed[-1].from_agent_id,
                        collapsed[-1].to_agent_id,
                        collapsed[-1].kind,
                        collapsed[-1].summary,
                    )
                    == (row.from_agent_id, row.to_agent_id, row.kind, row.summary)
                ):
                    previous = collapsed[-1]
                    collapsed[-1] = service_types.SequenceRow(
                        previous.sequence_id, previous.group_id, previous.occurred_at,
                        previous.from_agent_id, previous.from_agent_label,
                        previous.to_agent_id, previous.to_agent_label, previous.kind,
                        previous.summary, previous.evidence, previous.event_id,
                        previous.repeat_count + row.repeat_count,
                        previous.reasoning_available or row.reasoning_available,
                    )
                else:
                    collapsed.append(row)
            rows = collapsed
        groups = self._sequence_groups(rows, request.filters.grouping, threads)
        sliced = _slice(cast(list[object], rows), after, request.page_size)
        page = service_types.PageResult(
            request.snapshot_id,
            handle.revision_id,
            "query_sequence",
            sliced.items,
            request.filters,
            request.sort,
            request.page_size,
            sliced.next_position,
        )
        return service_types.SequenceResult(page, groups)

    def query_coordination(self, handle, request, after, cancellation):  # type: ignore[no-untyped-def]
        run = handle.run
        rows: list[service_types.CoordinationRow] = []
        threads = {thread.thread_id: thread for thread in run.threads}
        for thread in run.threads:
            parent = thread.parent_thread_id or None
            if parent in threads:
                rows.append(_coordination_row(
                    thread.started_at, "delegate", None,
                    _delegated_root_id(parent, threads), parent, (thread.thread_id,),
                    f"Delegated {thread.task_title or thread.thread_id}", "derived", 0,
                ))
            for event in getattr(thread, "work_item_claim_events", ()):
                rows.append(_coordination_row(
                    event.event_timestamp, event.operation, event.work_item_id,
                    event.root_task_id or None, event.thread_id or thread.thread_id,
                    tuple(value for value in (event.agent,) if value and value != event.thread_id),
                    event.activity or event.disposition or event.outcome or event.operation,
                    "measured", event.source_ordinal,
                ))
            for activity in thread.activities:
                if activity.activity_type != "decision" or not activity.summary:
                    continue
                rows.append(_coordination_row(
                    activity.event_timestamp, "decision", None,
                    _delegated_root_id(thread.thread_id, threads), thread.thread_id,
                    (), activity.summary, "inferred", activity.source_ordinal,
                ))
        filters = request.filters
        rows = [row for row in rows if (
            (filters.work_item_id is None or row.work_item_id == filters.work_item_id)
            and (filters.delegated_root_id is None or row.delegated_root_id == filters.delegated_root_id)
            and (filters.agent_id is None or filters.agent_id == row.agent_id or filters.agent_id in row.related_agent_ids)
            and (filters.operation is None or row.operation == filters.operation)
            and (filters.evidence is None or row.evidence == filters.evidence)
        )]
        rows.sort(key=lambda row: row.coordination_id)
        rows.sort(key=lambda row: row.occurred_at, reverse=request.sort.direction == "descending")
        return cast(service_types.QuerySlice[service_types.CoordinationRow], _slice(cast(list[object], rows), after, request.page_size))

    @staticmethod
    def _sequence_groups(rows, grouping, threads):  # type: ignore[no-untyped-def]
        if grouping == "none":
            return ()
        group_labels: dict[str, str] = {}
        updated: list[service_types.SequenceRow] = []
        for row in rows:
            if grouping == "agent":
                key = row.from_agent_id or row.to_agent_id or "unassigned"
            elif grouping == "delegation":
                key = _delegated_root_id(row.to_agent_id or row.from_agent_id, threads) or "unassigned"
            else:
                key = f"{row.from_agent_id}:{row.to_agent_id}:{row.kind}:{row.summary}"
            group_id = "grp_" + hashlib.sha256(key.encode()).hexdigest()[:24]
            label = getattr(threads.get(key), "task_title", None) or key
            group_labels[group_id] = _bounded_text(label)
            updated.append(service_types.SequenceRow(
                row.sequence_id, group_id, row.occurred_at, row.from_agent_id,
                row.from_agent_label, row.to_agent_id, row.to_agent_label, row.kind,
                row.summary, row.evidence, row.event_id, row.repeat_count,
                row.reasoning_available,
            ))
        rows[:] = updated
        return tuple(service_types.SequenceGroup(group_id, None, 0, label, True)
                     for group_id, label in sorted(group_labels.items()))

    def get_event_details(self, handle, event_id, cancellation):  # type: ignore[no-untyped-def]
        try:
            item = self._repository.get_event(
                event_cache.SnapshotId(handle.cache_snapshot_id),
                event_cache.SnapshotRevisionId(handle.revision_id),
                event_cache.EventId(event_id),
            )
        except event_cache.CacheEventNotFoundError:
            return None
        record = item.record
        return service_types.EventDetail(
            handle.snapshot_id,
            handle.revision_id,
            event_id,
            record.timestamp_utc,
            record.kind,
            record.summary_text or record.kind,
            record.evidence_method.value,
            ("normalized event cache",),
            record.summary_text,
            tuple(
                service_types.Disclosure(label, content, False)
                for label, content in (
                    ("Arguments", record.argument_summary),
                    ("Result", record.result_preview),
                    ("Message", record.message_preview),
                )
                if content
            ),
            str(item.source_key),
        )


class _FilesystemPublication:
    def __init__(
        self,
        surface: Literal["tauri", "cli", "mcp"],
        *,
        authorized_root: Path | None = None,
    ) -> None:
        self._surface = surface
        self._authorized_root = authorized_root
        self._bindings: dict[
            str, tuple[Path, int, int, str, tuple[int, int, int] | None]
        ] = {}
        self._authorized_parents: set[Path] = set()

    def authorize(
        self, request: static_export.ExportRequest
    ) -> static_export.PublicationPlan:
        if self._authorized_root is not None:
            try:
                _root, target = _authorized_output_target(
                    request.requested_target,
                    self._authorized_root,
                    require_existing_parent=True,
                )
            except _OutputAuthorizationError as error:
                raise service_types.PublicationFailure(
                    "unauthorized_target", str(error), False
                ) from error
        else:
            target = request.requested_target.resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
        parent_metadata = target.parent.lstat()
        if _is_symlink_or_reparse(parent_metadata) or not stat.S_ISDIR(
            parent_metadata.st_mode
        ):
            raise service_types.PublicationFailure(
                "unauthorized_target",
                "The report output parent is not a regular directory.",
                False,
            )
        target_metadata: os.stat_result | None
        try:
            target_metadata = target.lstat()
        except FileNotFoundError:
            target_metadata = None
        if target_metadata is not None:
            expected_directory = request.mode is static_export.ExportMode.DIRECTORY
            valid_kind = (
                stat.S_ISDIR(target_metadata.st_mode)
                if expected_directory
                else stat.S_ISREG(target_metadata.st_mode)
            )
            if _is_symlink_or_reparse(target_metadata) or not valid_kind:
                raise service_types.PublicationFailure(
                    "unauthorized_target",
                    "The existing report output target has an incompatible type.",
                    False,
                )
            if not request.replace:
                raise service_types.PublicationFailure(
                    "replace_required",
                    "The report output target already exists and replacement was not authorized.",
                    True,
                )
            if expected_directory:
                raise service_types.PublicationFailure(
                    "write",
                    "Atomic replacement of an existing report directory is unavailable.",
                    True,
                )
        token = secrets.token_hex(16)
        staging = target.parent / f"{static_export.STAGING_PREFIX}{token}"
        os.mkdir(staging, mode=0o700)
        staging_metadata = staging.lstat()
        if (
            _is_symlink_or_reparse(staging_metadata)
            or not stat.S_ISDIR(staging_metadata.st_mode)
            or stat.S_IMODE(staging_metadata.st_mode) != 0o700
            or staging_metadata.st_dev != parent_metadata.st_dev
        ):
            self._remove_staging(staging, target.parent)
            raise service_types.PublicationFailure(
                "write", "The report staging directory failed validation.", False
            )
        self._bindings[token] = (
            target.parent,
            parent_metadata.st_dev,
            parent_metadata.st_ino,
            target.name,
            (
                target_metadata.st_dev,
                target_metadata.st_ino,
                target_metadata.st_mode,
            )
            if target_metadata is not None
            else None,
        )
        self._authorized_parents.add(target.parent)
        return static_export.PublicationPlan(
            self._surface,
            token,
            request.requested_target,
            target,
            staging,
            "file" if request.mode is static_export.ExportMode.SUMMARY else "directory",
            "atomic-file-replace"
            if request.mode is static_export.ExportMode.SUMMARY
            else "atomic-directory-rename",
            request.replace,
        )

    def publish(self, plan, staged_entry, expected_relative_paths):  # type: ignore[no-untyped-def]
        del expected_relative_paths
        target = plan.absolute_target
        self._revalidate(plan)
        staged_metadata = staged_entry.lstat()
        if _is_symlink_or_reparse(staged_metadata):
            raise service_types.PublicationFailure(
                "write", "The staged report artifact failed validation.", False
            )
        os.replace(staged_entry, target)
        self._fsync_parent(target.parent)
        self._remove_staging(plan.staging_directory, target.parent)
        self._bindings.pop(plan.authority_token, None)
        return target

    def discard(self, plan):  # type: ignore[no-untyped-def]
        binding = self._bindings.pop(plan.authority_token, None)
        if binding is not None:
            self._remove_staging(plan.staging_directory, binding[0])

    def cleanup_stale(self, *, older_than):  # type: ignore[no-untyped-def]
        removed: list[Path] = []
        cutoff = older_than.timestamp()
        for parent in tuple(self._authorized_parents):
            try:
                candidates = tuple(parent.iterdir())
            except OSError:
                continue
            for candidate in candidates:
                if not _STAGING_NAME.fullmatch(candidate.name):
                    continue
                try:
                    metadata = candidate.lstat()
                except OSError:
                    continue
                if (
                    _is_symlink_or_reparse(metadata)
                    or not stat.S_ISDIR(metadata.st_mode)
                    or metadata.st_mtime >= cutoff
                ):
                    continue
                if self._remove_staging(candidate, parent):
                    removed.append(candidate)
        return tuple(removed)

    def _revalidate(self, plan: static_export.PublicationPlan) -> None:
        target = plan.absolute_target
        binding = self._bindings.get(plan.authority_token)
        if binding is None:
            raise service_types.PublicationFailure(
                "unauthorized_target",
                "The report publication authority expired.",
                False,
            )
        parent, device, inode, name, target_identity = binding
        metadata = parent.lstat()
        if (
            _is_symlink_or_reparse(metadata)
            or metadata.st_dev != device
            or metadata.st_ino != inode
            or target.name != name
            or target.parent != parent
        ):
            raise service_types.PublicationFailure(
                "unauthorized_target",
                "The report output authority changed before publication.",
                False,
            )
        try:
            target_metadata = target.lstat()
        except FileNotFoundError:
            current_identity = None
        else:
            if _is_symlink_or_reparse(target_metadata):
                raise service_types.PublicationFailure(
                    "unauthorized_target",
                    "The report output target changed before publication.",
                    False,
                )
            current_identity = (
                target_metadata.st_dev,
                target_metadata.st_ino,
                target_metadata.st_mode,
            )
        if current_identity != target_identity:
            raise service_types.PublicationFailure(
                "unauthorized_target",
                "The report output target changed before publication.",
                False,
            )

    @staticmethod
    def _remove_staging(path: Path, parent: Path) -> bool:
        if path.parent != parent or not _STAGING_NAME.fullmatch(path.name):
            return False
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return False
        if _is_symlink_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
            return False
        shutil.rmtree(path)
        return True

    @staticmethod
    def _fsync_parent(parent: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(parent, flags | getattr(os, "O_NOFOLLOW", 0))
        except OSError:
            return
        try:
            try:
                os.fsync(descriptor)
            except OSError:
                # The target is already visible. The current publication contract
                # cannot represent a post-commit durability warning.
                pass
        finally:
            os.close(descriptor)


class _ExporterAdapter:
    def __init__(self, config: service_types.ApplicationServiceConfig) -> None:
        self._config = config

    def stage(self, handle, request, cancellation, progress):  # type: ignore[no-untyped-def]
        model = _export_model(handle.run, handle, request.snapshot_id, self._config)
        scratch = Path(tempfile.mkdtemp(prefix="agent-report-export-"))
        target = scratch / ("summary.html" if request.mode == "summary" else "report")
        exporter_request = static_export.ExportRequest(
            _CURRENT_OPERATION_ID.get(),
            request.snapshot_id,
            handle.revision_id,
            static_export.ExportMode(request.mode),
            target,
            False,
            request.include_sqlite_archive,
        )
        try:
            result = static_export.StaticExporter().export(
                model,
                exporter_request,
                _FilesystemPublication(request.surface),
                _ExportCancellation(cancellation),
            )
        except static_export.StaticExportError as error:
            shutil.rmtree(scratch, ignore_errors=True)
            raise service_types.ExportRenderFailure("render") from error
        return _StagedExport(
            request.mode,
            secrets.token_hex(16),
            request.surface,
            _CURRENT_OUTPUT_ROOT.get(),
            result.published_target,
            result,
        )


class _ExportCancellation:
    def __init__(self, cancellation: service_types.CancellationToken) -> None:
        self._cancellation = cancellation

    def raise_if_cancelled(self) -> None:
        if self._cancellation.is_cancelled():
            raise static_export.StaticExportError.from_code(
                "REPORT_CANCELLED", "Operation cancelled", operation_id="op_cancelled"
            )


class _PublisherAdapter:
    def publish(self, staged, target, replace, cancellation):  # type: ignore[no-untyped-def]
        result = staged.result
        scratch = staged.source.parent
        publication = _FilesystemPublication(
            staged.surface, authorized_root=staged.authorized_root
        )
        try:
            published = publication.publish(
                publication.authorize(
                    static_export.ExportRequest(
                        result.operation_id,
                        result.snapshot_id,
                        result.revision,
                        result.mode,
                        target,
                        replace,
                    )
                ),
                staged.source,
                (),
            )
        except (OSError, service_types.PublicationFailure) as error:
            raise service_types.PublicationFailure("write") from error
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        return service_types.ExportResult(
            result.operation_id,
            result.snapshot_id,
            result.revision,
            result.mode.value,
            published,
            result.manifest_sha256,
            result.file_count,
            result.total_byte_count,
            tuple(
                service_types.WarningRecord(item.code, item.message)
                for item in result.warnings
            ),
            tuple(
                service_types.ExportOmission(item.section, item.reason, item.recovery)
                for item in result.omissions
            ),
        )

    def discard(self, staged):  # type: ignore[no-untyped-def]
        shutil.rmtree(staged.source.parent, ignore_errors=True)


def _export_model(
    run: object,
    handle: _ReadHandle,
    snapshot_id: str,
    config: service_types.ApplicationServiceConfig,
) -> static_export.CodexExportModel:
    run = cast(Any, run)
    root = next(
        (item for item in run.threads if item.thread_id == run.root_thread_id),
        run.threads[0],
    )
    observed = _aware(run.observed_at) or datetime.now(timezone.utc)
    provenance = static_export.SnapshotProvenance(
        snapshot_id,
        handle.revision_id,
        run.root_thread_id,
        static_export.ExportScope(
            handle.scope.include_children, handle.scope.include_collaborators
        ),
        observed,
        static_export.SnapshotState.SEALED
        if run.state == "sealed"
        else static_export.SnapshotState.LIVE,
        handle.source_revision,
        config.parser_version,
        config.pricing_version,
        config.pricing_digest,
        config.formatter_version,
        config.formatter_digest,
    )
    metrics = (
        static_export.MetricExport(
            "agents",
            "Agents",
            str(len(run.threads)),
            len(run.threads),
            "agents",
            "derived",
        ),
        static_export.MetricExport(
            "wall_time",
            "Wall time",
            str(run.wall_time_ms),
            run.wall_time_ms,
            "ms",
            "measured",
        ),
    )
    summary = static_export.SummaryExport(
        root.task_title or run.run_label or "Agent Report",
        None,
        run.state,
        metrics,
        (),
        tuple(
            static_export.ExportWarningRecord("REPORT_SOURCE_WARNING", item[:512])
            for item in run.diagnostics[:100]
        ),
    )
    agents = tuple(
        static_export.AgentExportRow(
            item.thread_id,
            item.parent_thread_id or None,
            item.task_title,
            item.agent_role,
            item.model,
            item.effort,
            item.started_at,
            item.last_observed_at,
            item.terminal_state,
            len(item.turns),
            len(item.tool_intervals),
            len(item.mcp_calls),
            0,
            0,
            item.token_totals.input_tokens,
            item.token_totals.cached_input_tokens,
            item.token_totals.output_tokens,
            item.token_totals.reasoning_tokens,
            item.recorded_cost_usd,
            "estimated" if item.recorded_cost_usd is not None else "unavailable",
        )
        for item in run.threads
    )
    turns = tuple(
        static_export.TurnExportRow(
            thread.thread_id,
            item.turn_id,
            item.started_at,
            item.completed_at,
            item.duration_ms,
            item.time_to_first_token_ms,
            item.outcome,
            item.abort_reason,
            item.abort_event_timestamp,
            item.abort_initiator_thread_id,
            item.abort_initiator_agent_path,
            item.abort_initiator_turn_id,
            item.abort_initiator_relationship,
            "",
            item.abort_request_source_ordinal,
            item.phase_id,
            item.lane_id,
            item.work_unit_id,
            item.activity,
            item.attribution_confidence,
            item.usage.input_tokens,
            item.usage.cached_input_tokens,
            item.usage.uncached_input_tokens,
            item.usage.output_tokens,
            item.usage.reasoning_tokens,
            item.usage.processed_tokens,
            "source",
            item.source_ordinal,
        )
        for thread in run.threads
        for item in thread.turns
    )
    work_units = tuple(
        static_export.WorkUnitExportRow(
            item.work_unit_id,
            item.phase_id,
            item.lane_id,
            item.activity,
            tuple(item.turn_ids),
            item.allocation_method,
            item.attribution_confidence,
            item.usage.input_tokens,
            item.usage.cached_input_tokens,
            item.usage.uncached_input_tokens,
            item.usage.output_tokens,
            item.usage.reasoning_tokens,
            item.usage.processed_tokens,
            item.cost.status,
            item.cost.total_cost,
        )
        for item in run.work_units
    )
    events: list[static_export.EventExportRow] = []
    for thread in run.threads:
        for index, item in enumerate(thread.activities):
            events.append(
                static_export.EventExportRow(
                    f"evt_{hashlib.sha256(f'{thread.thread_id}:{item.source_ordinal}'.encode()).hexdigest()[:24]}",
                    thread.thread_id,
                    item.turn_id,
                    item.event_timestamp,
                    item.activity_type,
                    item.summary or item.activity_type,
                    item.summary,
                    "measured",
                    item.source_ordinal,
                )
            )
    participants = tuple(
        static_export.SequenceParticipantExport(
            item.thread_id,
            item.parent_thread_id or None,
            item.task_title or item.thread_id,
            item.agent_role,
        )
        for item in run.threads
    )
    return static_export.CodexExportModel(
        provenance,
        summary,
        agents,
        turns,
        work_units,
        tuple(events),
        (),
        participants,
        (),
    )


def create_production_application_service(
    runtime: ModuleType,
    config: service_types.ApplicationServiceConfig,
    *,
    seal: bool = False,
    allow_aborted: bool = False,
    title: str = "",
    thread_titles: Mapping[str, str] | None = None,
    workers: int = 1,
) -> service_types.ApplicationService:
    """Compose one process-local service from runtime, cache, and exporter adapters."""

    cache_path = event_cache.DEFAULT_CACHE_PATH
    repository = event_cache.EventRepository.open_or_rebuild(cache_path).repository
    repository_adapter = _RepositoryAdapter(repository, config)
    dependencies = service_types.ApplicationServiceDependencies(
        _RuntimeDiscovery(runtime),
        _RuntimeNormalization(
            runtime,
            seal=seal,
            allow_aborted=allow_aborted,
            title=title,
            thread_titles=thread_titles or {},
            workers=workers,
            pricing_version=config.pricing_version,
        ),
        repository_adapter,
        _RuntimeQueries(repository),
        _ExporterAdapter(config),
        _PublisherAdapter(),
        _Clock(),
        _Ids(repository_adapter),
        _Logger(),
    )
    return _ProductionApplicationService(config, dependencies, repository_adapter)


class _ProductionApplicationService(service_types.ApplicationService):
    """Close the cache owned by this process-local composition root."""

    def __init__(
        self,
        config: service_types.ApplicationServiceConfig,
        dependencies: service_types.ApplicationServiceDependencies,
        repository: _RepositoryAdapter,
    ) -> None:
        super().__init__(config, dependencies)
        self._production_repository = repository

    def close(self) -> None:
        try:
            super().close()
        finally:
            self._production_repository.close()


@dataclass(frozen=True)
class ReportServerConfig:
    """Validated server-owned report configuration."""

    session_roots: tuple[Path, ...]
    default_output: Path
    timezone: tzinfo
    timezone_name: str
    max_inline_bytes: int
    workspace_root: Path | None = None


@dataclass(frozen=True)
class TaskCandidate:
    """Minimal Rust-indexed task identity used by MCP selection."""

    thread_id: str
    title: str
    timestamp: datetime
    last_activity_at: datetime


def load_server_config(
    environ: Mapping[str, str] | None = None,
    *,
    local_timezone: tzinfo | None = None,
) -> ReportServerConfig:
    """Load and validate server configuration from environment variables."""

    values = os.environ if environ is None else environ
    raw_roots = values.get("AGENT_REPORT_SESSIONS_ROOTS", "").strip()
    if raw_roots:
        session_roots = tuple(
            Path(value.strip()).expanduser().resolve()
            for value in raw_roots.split(os.pathsep)
            if value.strip()
        )
    else:
        session_roots = ((Path.home() / ".codex" / "sessions").resolve(),)
    if not session_roots:
        raise RuntimeError("AGENT_REPORT_SESSIONS_ROOTS must contain at least one path")
    invalid_roots = [path for path in session_roots if not path.is_dir()]
    if invalid_roots:
        raise RuntimeError(
            "Configured Codex sessions root is unavailable: "
            + ", ".join(str(path) for path in invalid_roots)
        )

    raw_output = values.get("AGENT_REPORT_DEFAULT_OUTPUT", str(DEFAULT_OUTPUT)).strip()
    if not raw_output:
        raise RuntimeError("AGENT_REPORT_DEFAULT_OUTPUT must not be empty")
    default_output = Path(raw_output).expanduser()
    if default_output.exists() and not default_output.is_dir():
        raise RuntimeError(
            f"Configured report output is not a directory: {default_output}"
        )

    configured_timezone = values.get("AGENT_REPORT_TIMEZONE", "").strip()
    if configured_timezone:
        try:
            timezone_value = ZoneInfo(configured_timezone)
        except ZoneInfoNotFoundError as error:
            raise RuntimeError(
                f"Unknown AGENT_REPORT_TIMEZONE: {configured_timezone}"
            ) from error
        timezone_name = configured_timezone
    else:
        timezone_value = local_timezone or datetime.now().astimezone().tzinfo
        if timezone_value is None:
            raise RuntimeError("Unable to determine the server local timezone")
        timezone_name = str(timezone_value)

    raw_limit = values.get(
        "AGENT_REPORT_MAX_INLINE_BYTES", str(DEFAULT_INLINE_BYTES)
    ).strip()
    try:
        max_inline_bytes = int(raw_limit)
    except ValueError as error:
        raise RuntimeError(
            "AGENT_REPORT_MAX_INLINE_BYTES must be an integer from 1 to 65536"
        ) from error
    if not 1 <= max_inline_bytes <= MAX_INLINE_BYTES:
        raise RuntimeError("AGENT_REPORT_MAX_INLINE_BYTES must be from 1 to 65536")

    raw_workspace = values.get("AGENT_REPORT_WORKSPACE_ROOT", "").strip()
    workspace_root = (
        Path(raw_workspace).expanduser().resolve() if raw_workspace else None
    )
    if workspace_root is not None and not workspace_root.is_dir():
        raise RuntimeError(
            f"Configured report workspace root is unavailable: {workspace_root}"
        )

    return ReportServerConfig(
        session_roots=session_roots,
        default_output=default_output,
        timezone=timezone_value,
        timezone_name=timezone_name,
        max_inline_bytes=max_inline_bytes,
        workspace_root=workspace_root,
    )


def validate_startup(runtime: ModuleType, engine_path: Path) -> None:
    """Require the bundled engine and validate its versioned index protocol."""

    if not engine_path.is_file():
        raise RuntimeError(f"Bundled agent-report-engine is unavailable: {engine_path}")
    if os.name != "nt" and not os.access(engine_path, os.X_OK):
        raise RuntimeError(
            f"Bundled agent-report-engine is not executable: {engine_path}"
        )
    os.environ["AGENT_REPORT_ENGINE"] = str(engine_path)
    try:
        runtime._native_rollout_discovery([], None)
    except (OSError, RuntimeError, ValueError) as error:
        raise RuntimeError(
            f"Bundled agent-report-engine protocol validation failed: {error}"
        ) from error


def workspace_root_from_uri(uri: object) -> Path | None:
    """Convert one supported MCP file root URI into a local directory path."""

    text = str(uri or "")
    parsed = urlparse(text)
    if parsed.scheme != "file" or (parsed.netloc and parsed.netloc != "localhost"):
        return None
    path = Path(url2pathname(parsed.path)).resolve()
    return path if path.is_dir() else None


class _CallableCancellation:
    """Adapt the retained callback convention to the service cancellation port."""

    def __init__(self, cancelled: Callable[[], bool] | None) -> None:
        self._cancelled = cancelled

    def is_cancelled(self) -> bool:
        return self._cancelled is not None and self._cancelled()


def _json_value(value: object) -> object:
    """Convert service DTOs into the JSON-safe shape exposed by MCP."""

    if is_dataclass(value) and not isinstance(value, type):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


class ReportGenerator:
    """Generate MCP results through the existing authoritative report runtime."""

    def __init__(
        self,
        runtime: ModuleType,
        config: ReportServerConfig,
        *,
        application_service: service_types.ApplicationService | None = None,
        application_service_factory: (
            Callable[[], service_types.ApplicationService] | None
        ) = None,
    ) -> None:
        if application_service is not None and application_service_factory is not None:
            raise ValueError(
                "Provide either an application service or its lazy factory, not both."
            )
        self._runtime = runtime
        self._config = config
        self._run_cache: dict[
            str, tuple[object, tuple[tuple[str, int, int], ...], float]
        ] = {}
        self._discovery_cache: (
            tuple[list[TaskCandidate], list[Path], str | None, float] | None
        ) = None
        self._application_service = application_service
        self._application_service_factory = application_service_factory
        self._application_service_lock = threading.Lock()

    def close(self) -> None:
        """Release process-local snapshot and repository resources."""

        if self._application_service is not None:
            self._application_service.close()

    @staticmethod
    def _operation_context() -> service_types.OperationContext:
        context = service_types.OperationContext(
            protocol_version=service_types.PROTOCOL_VERSION,
            operation_id=f"op_{secrets.token_hex(12)}",
        )
        _CURRENT_OPERATION_ID.set(context.operation_id)
        return context

    def _service(self) -> service_types.ApplicationService:
        if self._application_service is None and self._application_service_factory:
            with self._application_service_lock:
                if self._application_service is None:
                    self._application_service = self._application_service_factory()
        if self._application_service is None:
            raise RuntimeError("The snapshot application service is unavailable")
        return self._application_service

    @staticmethod
    def _service_result(result: object) -> dict[str, object]:
        value = getattr(result, "value", None)
        error = getattr(result, "error", None)
        if error is not None:
            payload = cast(dict[str, object], _json_value(error))
            return {"ok": False, **payload}
        return {"ok": True, **cast(dict[str, object], _json_value(value))}

    def preflight_report(
        self,
        *,
        root_thread_id: str,
        include_children: bool = False,
        include_collaborators: bool = False,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Preflight one exact report scope without opening a snapshot."""

        scope = service_types.ReportScope(
            root_thread_id, include_children, include_collaborators
        )
        result = self._service().preflight_report(
            self._operation_context(),
            service_types.PreflightReportRequest(scope),
            cancellation=_CallableCancellation(cancelled),
        )
        return self._service_result(result)

    def open_snapshot(
        self,
        *,
        root_thread_id: str,
        preflight_token: str,
        source_revision: str,
        include_children: bool = False,
        include_collaborators: bool = False,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Open one coherent service snapshot from an accepted preflight."""

        scope = service_types.ReportScope(
            root_thread_id, include_children, include_collaborators
        )
        result = self._service().open_snapshot(
            self._operation_context(),
            service_types.OpenSnapshotRequest(scope, preflight_token, source_revision),
            cancellation=_CallableCancellation(cancelled),
        )
        return self._service_result(result)

    def get_summary(
        self, *, snapshot_id: str, cancelled: Callable[[], bool] | None = None
    ) -> dict[str, object]:
        """Return the shared display-ready snapshot summary."""

        result = self._service().get_summary(
            self._operation_context(),
            service_types.SnapshotRequest(snapshot_id),
            cancellation=_CallableCancellation(cancelled),
        )
        return self._service_result(result)

    def list_agents(
        self,
        *,
        snapshot_id: str,
        query: str = "",
        agent_ids: list[str] | None = None,
        roles: list[str] | None = None,
        states: list[str] | None = None,
        sort_key: service_types.AgentSortKey = "last_activity_at",
        sort_direction: service_types.SortDirection = "descending",
        cursor: str | None = None,
        page_size: int = service_types.DEFAULT_PAGE_SIZE,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Return one canonical agent page from an open snapshot."""

        request = service_types.ListAgentsRequest(
            snapshot_id,
            service_types.AgentFilters(
                query, tuple(agent_ids or ()), tuple(roles or ()), tuple(states or ())
            ),
            service_types.AgentSort(sort_key, sort_direction),
            cursor,
            page_size,
        )
        result = self._service().list_agents(
            self._operation_context(),
            request,
            cancellation=_CallableCancellation(cancelled),
        )
        return self._service_result(result)

    def list_turns(
        self,
        *,
        snapshot_id: str,
        turn_ids: list[str] | None = None,
        agent_ids: list[str] | None = None,
        states: list[str] | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        sort_key: service_types.TurnSortKey = "started_at",
        sort_direction: service_types.SortDirection = "ascending",
        cursor: str | None = None,
        page_size: int = service_types.DEFAULT_PAGE_SIZE,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Return one canonical turn page from an open snapshot."""

        try:
            parsed_from = (
                self._parse_timestamp(from_time, "from_time") if from_time else None
            )
            parsed_to = self._parse_timestamp(to_time, "to_time") if to_time else None
        except ValueError as error:
            return self._error("REPORT_INVALID_REQUEST", str(error))
        request = service_types.ListTurnsRequest(
            snapshot_id,
            service_types.TurnFilters(
                tuple(turn_ids or ()),
                tuple(agent_ids or ()),
                tuple(states or ()),
                parsed_from,
                parsed_to,
            ),
            service_types.TurnSort(sort_key, sort_direction),
            cursor,
            page_size,
        )
        result = self._service().list_turns(
            self._operation_context(),
            request,
            cancellation=_CallableCancellation(cancelled),
        )
        return self._service_result(result)

    def list_events(
        self,
        *,
        snapshot_id: str,
        event_ids: list[str] | None = None,
        agent_ids: list[str] | None = None,
        turn_ids: list[str] | None = None,
        kinds: list[str] | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        sort_key: service_types.EventSortKey = "occurred_at",
        sort_direction: service_types.SortDirection = "ascending",
        cursor: str | None = None,
        page_size: int = service_types.DEFAULT_PAGE_SIZE,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Return one canonical event page from an open snapshot."""

        try:
            parsed_from = (
                self._parse_timestamp(from_time, "from_time") if from_time else None
            )
            parsed_to = self._parse_timestamp(to_time, "to_time") if to_time else None
        except ValueError as error:
            return self._error("REPORT_INVALID_REQUEST", str(error))
        request = service_types.ListEventsRequest(
            snapshot_id,
            service_types.EventFilters(
                tuple(event_ids or ()),
                tuple(agent_ids or ()),
                tuple(turn_ids or ()),
                tuple(kinds or ()),
                parsed_from,
                parsed_to,
            ),
            service_types.EventSort(sort_key, sort_direction),
            cursor,
            page_size,
        )
        result = self._service().list_events(
            self._operation_context(),
            request,
            cancellation=_CallableCancellation(cancelled),
        )
        return self._service_result(result)

    def query_snapshot_time_range(
        self,
        *,
        snapshot_id: str,
        query_kind: service_types.HeatmapQueryKind,
        mode: service_types.HeatmapMode,
        from_time: str | None = None,
        to_time: str | None = None,
        requested_resolution_minutes: int | None = None,
        maximum_rows: int = 100,
        row_id: str | None = None,
        period_start_time: str | None = None,
        period_end_time: str | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Return one discriminated snapshot Heatmap query result."""

        try:
            if query_kind == "matrix":
                if from_time is None or to_time is None or requested_resolution_minutes is None:
                    raise ValueError("matrix queries require from_time, to_time, and requested_resolution_minutes")
                request: service_types.HeatmapSnapshotQueryRequest = service_types.HeatmapMatrixRequest(
                    snapshot_id, "matrix", self._parse_timestamp(from_time, "from_time"),
                    self._parse_timestamp(to_time, "to_time"), mode,
                    cast(service_types.HeatmapResolutionMinutes, requested_resolution_minutes), maximum_rows,
                )
            elif query_kind == "cell_evidence":
                if row_id is None or period_start_time is None or period_end_time is None:
                    raise ValueError("cell_evidence queries require row_id, period_start_time, and period_end_time")
                request = service_types.HeatmapCellEvidenceRequest(
                    snapshot_id, "cell_evidence", mode, row_id,
                    self._parse_timestamp(period_start_time, "period_start_time"),
                    self._parse_timestamp(period_end_time, "period_end_time"),
                )
            else:
                raise ValueError("query_kind must be matrix or cell_evidence")
        except ValueError as error:
            return self._error("REPORT_INVALID_REQUEST", str(error))
        result = self._service().query_snapshot_time_range(
            self._operation_context(),
            request,
            cancellation=_CallableCancellation(cancelled),
        )
        return self._service_result(result)

    def query_sequence(
        self,
        *,
        snapshot_id: str,
        focus_agent_id: str | None = None,
        event_ids: list[str] | None = None,
        agent_ids: list[str] | None = None,
        turn_ids: list[str] | None = None,
        kinds: list[str] | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        grouping: service_types.SequenceGrouping = "none",
        include_reasoning: bool = False,
        cursor: str | None = None,
        page_size: int = service_types.DEFAULT_PAGE_SIZE,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Return one canonical sequence page and its hierarchy groups."""

        try:
            parsed_from = (
                self._parse_timestamp(from_time, "from_time") if from_time else None
            )
            parsed_to = self._parse_timestamp(to_time, "to_time") if to_time else None
        except ValueError as error:
            return self._error("REPORT_INVALID_REQUEST", str(error))
        event_filters = service_types.EventFilters(
            tuple(event_ids or ()),
            tuple(agent_ids or ()),
            tuple(turn_ids or ()),
            tuple(kinds or ()),
            parsed_from,
            parsed_to,
        )
        request = service_types.SequenceQueryRequest(
            snapshot_id,
            service_types.SequenceFilters(
                focus_agent_id, event_filters, grouping, include_reasoning
            ),
            service_types.SequenceSort(),
            cursor,
            page_size,
        )
        result = self._service().query_sequence(
            self._operation_context(),
            request,
            cancellation=_CallableCancellation(cancelled),
        )
        return self._service_result(result)

    def query_coordination(
        self,
        *,
        snapshot_id: str,
        work_item_id: str | None = None,
        delegated_root_id: str | None = None,
        agent_id: str | None = None,
        operation: str | None = None,
        evidence: service_types.EvidenceKind | None = None,
        cursor: str | None = None,
        page_size: int = service_types.DEFAULT_PAGE_SIZE,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Return one canonical coordination page."""

        request = service_types.CoordinationQueryRequest(
            snapshot_id,
            service_types.CoordinationFilters(
                work_item_id, delegated_root_id, agent_id, operation, evidence
            ),
            service_types.CoordinationSort(),
            cursor,
            page_size,
        )
        result = self._service().query_coordination(
            self._operation_context(),
            request,
            cancellation=_CallableCancellation(cancelled),
        )
        return self._service_result(result)

    def get_snapshot_event_details(
        self,
        *,
        snapshot_id: str,
        event_id: str,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Return bounded detail for an event in an open snapshot."""

        result = self._service().get_event_details(
            self._operation_context(),
            service_types.EventDetailsRequest(snapshot_id, event_id),
            cancellation=_CallableCancellation(cancelled),
        )
        return self._service_result(result)

    def refresh_snapshot(
        self, *, snapshot_id: str, cancelled: Callable[[], bool] | None = None
    ) -> dict[str, object]:
        """Refresh an open snapshot while retaining the exact changed wrapper."""

        result = self._service().refresh_snapshot(
            self._operation_context(),
            service_types.RefreshSnapshotRequest(snapshot_id),
            cancellation=_CallableCancellation(cancelled),
        )
        return self._service_result(result)

    def export_snapshot(
        self,
        *,
        snapshot_id: str,
        target: str,
        replace: bool = False,
        report_mode: Literal["directory", "summary"] | None = None,
        include_sqlite_archive: bool = False,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Publish an open snapshot through the shared MCP exporter."""

        return self.export_snapshot_for_mcp(
            snapshot_id=snapshot_id,
            target=target,
            replace=replace,
            report_mode=report_mode,
            include_sqlite_archive=include_sqlite_archive,
            workspace_root=None,
            cancelled=cancelled,
        )

    def export_snapshot_for_mcp(
        self,
        *,
        snapshot_id: str,
        target: str,
        replace: bool = False,
        report_mode: Literal["directory", "summary"] | None = None,
        include_sqlite_archive: bool = False,
        workspace_root: Path | None,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Authorize one snapshot export beneath the effective MCP workspace."""

        root = workspace_root or self._config.workspace_root or Path.cwd()
        try:
            authorized_root, authorized_target = _authorized_output_target(
                Path(target), root, require_existing_parent=True
            )
        except _OutputAuthorizationError as error:
            return self._error("REPORT_INVALID_REQUEST", str(error))
        return self._export_snapshot(
            snapshot_id=snapshot_id,
            surface="mcp",
            target=str(authorized_target),
            replace=replace,
            report_mode=report_mode,
            include_sqlite_archive=include_sqlite_archive,
            authorized_root=authorized_root,
            cancelled=cancelled,
        )

    def _export_snapshot(
        self,
        *,
        snapshot_id: str,
        surface: service_types.AutomationSurface,
        target: str,
        replace: bool,
        report_mode: Literal["directory", "summary"] | None,
        include_sqlite_archive: bool = False,
        authorized_root: Path | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        token = _CURRENT_OUTPUT_ROOT.set(authorized_root)
        try:
            result = self._service().export_snapshot(
                self._operation_context(),
                service_types.ExportSnapshotRequest(
                    snapshot_id,
                    surface,
                    Path(target).expanduser().resolve(),
                    replace,
                    report_mode,
                    include_sqlite_archive,
                ),
                cancellation=_CallableCancellation(cancelled),
            )
            return self._service_result(result)
        finally:
            _CURRENT_OUTPUT_ROOT.reset(token)

    def close_snapshot(self, *, snapshot_id: str) -> dict[str, object]:
        """Close one process-local snapshot and release its read handle."""

        result = self._service().close_snapshot(
            self._operation_context(), service_types.CloseSnapshotRequest(snapshot_id)
        )
        return self._service_result(result)

    def generate_report(
        self,
        *,
        thread_id: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        name_contains: list[str] | None = None,
        output_path: str | None = None,
        return_via_mcp: bool = False,
        return_format: InlineFormat = "html",
        workspace_root: Path | None = None,
    ) -> dict[str, object]:
        """Select one task, render one snapshot, and return a structured result."""

        try:
            lower_bound, upper_bound = self._selection_range(from_time, to_time)
        except ValueError as error:
            return self._error("REPORT_INVALID_REQUEST", str(error))
        if return_format not in {"html", "markdown", "json"}:
            return self._error(
                "REPORT_INVALID_REQUEST",
                f"Unsupported inline report format: {return_format}",
            )

        try:
            candidates, candidate_paths = self._discover_candidates(thread_id=thread_id)
        except (OSError, RuntimeError, ValueError) as error:
            return self._error("REPORT_DISCOVERY_FAILED", str(error))

        selected = self._select_candidate(
            candidates,
            thread_id=thread_id,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            name_contains=name_contains or [],
        )
        if isinstance(selected, dict):
            return selected

        try:
            run = self._runtime.build_codex_rollout_run(
                selected.thread_id,
                list(self._config.session_roots),
                candidate_paths=candidate_paths,
                title=selected.title,
                discovery_index_path=self._runtime._default_codex_discovery_index_path(),
            )
            representations = {
                "html": self._runtime.render_codex_rollout_html(run),
                "json": self._runtime.codex_run_to_json(run),
                "turns_csv": self._runtime.render_codex_rollout_turn_csv(run),
                "work_units_csv": self._runtime.render_codex_rollout_work_unit_csv(run),
                "markdown": self._runtime.render_codex_rollout_markdown(run),
            }
        except (OSError, RuntimeError, ValueError) as error:
            return self._error("REPORT_GENERATION_FAILED", str(error))

        base_workspace = workspace_root or self._config.workspace_root or Path.cwd()
        try:
            authorized_root, report_directory = self._resolve_output_directory(
                output_path, base_workspace, enforce_root=True
            )
        except _OutputAuthorizationError as error:
            return self._error("REPORT_INVALID_REQUEST", str(error))
        written_files: dict[str, str] = {}
        warnings: list[dict[str, str]] = []
        try:
            written_files = self._write_bundle(
                report_directory, representations, authorized_root=authorized_root
            )
        except (OSError, _OutputAuthorizationError) as error:
            message = f"Unable to write report bundle to {report_directory}: {error}"
            if not return_via_mcp:
                return self._error("REPORT_WRITE_FAILED", message)
            warnings.append({"code": "REPORT_WRITE_FAILED", "message": message})

        range_result = {
            "from": lower_bound.isoformat(),
            "to": upper_bound.isoformat(),
            "to_exclusive": True,
        }
        if return_via_mcp:
            inline_content = representations[return_format]
            actual_bytes = len(inline_content.encode("utf-8"))
            if actual_bytes > self._config.max_inline_bytes:
                result = self._error(
                    "REPORT_TOO_LARGE_FOR_MCP",
                    f"The {return_format.upper()} report exceeds the configured MCP response limit.",
                )
                result.update(
                    {
                        "actual_bytes": actual_bytes,
                        "maximum_bytes": self._config.max_inline_bytes,
                        "written_files": written_files,
                        "warnings": warnings,
                    }
                )
                return result
            inline: dict[str, object] | None = {
                "format": return_format,
                "bytes": actual_bytes,
                "content": inline_content,
            }
        else:
            inline = None

        result: dict[str, object] = {
            "ok": True,
            "thread_id": selected.thread_id,
            "task_name": selected.title,
            "range": range_result,
            "written_files": written_files,
            "warnings": warnings,
        }
        if inline is not None:
            result["inline"] = inline
        return result

    def generate_streamlined_report(
        self,
        *,
        thread_id: str,
        output_path: str | None,
        include_children: bool,
        include_collaborators: bool,
        report_mode: Literal["directory", "summary"],
        workspace_root: Path | None,
    ) -> dict[str, object]:
        """Generate an explicit streamlined export without changing classic MCP."""

        try:
            candidates, _candidate_paths = self._discover_candidates(
                thread_id=thread_id
            )
        except (OSError, RuntimeError, ValueError) as error:
            return self._error("REPORT_DISCOVERY_FAILED", str(error))
        lower_bound, upper_bound = self._selection_range(None, None)
        selected = self._select_candidate(
            candidates,
            thread_id=thread_id,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            name_contains=[],
        )
        if isinstance(selected, dict):
            return selected

        preflight = self.preflight_report(
            root_thread_id=selected.thread_id,
            include_children=include_children,
            include_collaborators=include_collaborators,
        )
        if not preflight.get("ok"):
            return preflight
        opened = self.open_snapshot(
            root_thread_id=selected.thread_id,
            preflight_token=cast(str, preflight["preflight_token"]),
            source_revision=cast(str, preflight["source_revision"]),
            include_children=include_children,
            include_collaborators=include_collaborators,
        )
        if not opened.get("ok"):
            return opened
        snapshot_id = cast(str, opened["snapshot_id"])
        base_workspace = workspace_root or self._config.workspace_root or Path.cwd()
        _ignored_root, target = self._resolve_output_directory(
            output_path, base_workspace, enforce_root=False
        )
        mode = report_mode or "directory"
        if mode == "summary" and output_path is None:
            target = target / "report.html"
        try:
            exported = self._export_snapshot(
                snapshot_id=snapshot_id,
                surface="cli",
                target=str(target),
                replace=target.exists(),
                report_mode=mode,
            )
            if not exported.get("ok"):
                return exported
            return {
                "ok": True,
                "thread_id": selected.thread_id,
                "task_name": selected.title,
                "snapshot_id": snapshot_id,
                "revision_id": opened["revision_id"],
                "mode": mode,
                "written_files": {"report": cast(str, exported["published_target"])},
                "file_count": exported["file_count"],
                "total_byte_count": exported["total_byte_count"],
                "manifest_sha256": exported.get("manifest_sha256"),
                "warnings": exported.get("warnings", []),
                "omissions": exported.get("omissions", []),
            }
        finally:
            self.close_snapshot(snapshot_id=snapshot_id)

    def query_time_range(
        self,
        *,
        thread_id: str,
        from_time: str | None = None,
        to_time: str | None = None,
        bucket_minutes: BucketMinutes = 5,
        measure: TimeRangeMeasure = "wall_time",
        include_events: bool = False,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Return bucketed task telemetry without rendering or writing a report."""

        if not thread_id.strip():
            return self._error("REPORT_INVALID_REQUEST", "thread_id must not be empty")
        if bucket_minutes not in {1, 5, 15, 30, 60}:
            return self._error(
                "REPORT_INVALID_REQUEST",
                "bucket_minutes must be one of 1, 5, 15, 30, or 60",
            )
        if measure not in {
            "wall_time",
            "uncached_input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "cost_usd",
        }:
            return self._error(
                "REPORT_INVALID_REQUEST",
                "Unsupported time-range measure",
            )
        try:
            normalized_from = (
                self._parse_timestamp(from_time, "from_time").isoformat()
                if from_time
                else None
            )
            normalized_to = (
                self._parse_timestamp(to_time, "to_time").isoformat()
                if to_time
                else None
            )
            if normalized_from and normalized_to:
                if datetime.fromisoformat(normalized_from) >= datetime.fromisoformat(
                    normalized_to
                ):
                    raise ValueError("from_time must be earlier than to_time")
        except ValueError as error:
            return self._error("REPORT_INVALID_REQUEST", str(error))

        try:
            candidates, candidate_paths = self._discover_candidates(
                thread_id=thread_id, cancelled=cancelled
            )
        except (OSError, RuntimeError, ValueError) as error:
            return self._error("REPORT_DISCOVERY_FAILED", str(error))
        lower_bound, upper_bound = self._selection_range(None, None)
        selected = self._select_candidate(
            candidates,
            thread_id=thread_id,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            name_contains=[],
        )
        if isinstance(selected, dict):
            return selected

        try:
            run = self._get_or_build_run(
                selected.thread_id,
                candidate_paths=candidate_paths,
                title=selected.title,
                cancelled=cancelled,
            )
            query = self._runtime.query_codex_run_time_range(
                run,
                from_time=normalized_from,
                to_time=normalized_to,
                bucket_minutes=bucket_minutes,
                measure=measure,
                include_events=include_events,
            )
        except ValueError as error:
            return self._error("REPORT_INVALID_REQUEST", str(error))
        except (OSError, RuntimeError) as error:
            return self._error("REPORT_GENERATION_FAILED", str(error))
        return {
            "ok": True,
            "thread_id": selected.thread_id,
            "task_name": selected.title,
            **query,
        }

    def get_event_details(
        self,
        *,
        thread_id: str,
        event_id: str,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Resolve one query event ID through a fresh authoritative task snapshot."""

        if not thread_id.strip():
            return self._error("REPORT_INVALID_REQUEST", "thread_id must not be empty")
        if not event_id.strip():
            return self._error("REPORT_INVALID_REQUEST", "event_id must not be empty")
        if re.fullmatch(r"evt_[0-9a-f]{24}", event_id) is None:
            return self._error(
                "REPORT_INVALID_REQUEST",
                "event_id must use the evt_ prefix followed by 24 lowercase hexadecimal characters",
            )
        try:
            candidates, candidate_paths = self._discover_candidates(
                thread_id=thread_id, cancelled=cancelled
            )
        except (OSError, RuntimeError, ValueError) as error:
            return self._error("REPORT_DISCOVERY_FAILED", str(error))
        lower_bound, upper_bound = self._selection_range(None, None)
        selected = self._select_candidate(
            candidates,
            thread_id=thread_id,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            name_contains=[],
        )
        if isinstance(selected, dict):
            return selected
        try:
            run = self._get_or_build_run(
                selected.thread_id,
                candidate_paths=candidate_paths,
                title=selected.title,
                cancelled=cancelled,
            )
            event = self._runtime.get_codex_run_event_details(run, event_id)
        except (OSError, RuntimeError, ValueError) as error:
            return self._error("REPORT_GENERATION_FAILED", str(error))
        if event is None:
            return self._error(
                "REPORT_EVENT_NOT_FOUND",
                "The event ID was not found in the current task snapshot.",
            )
        return {
            "ok": True,
            "thread_id": selected.thread_id,
            "task_name": selected.title,
            "event": event,
        }

    def _selection_range(
        self, from_time: str | None, to_time: str | None
    ) -> tuple[datetime, datetime]:
        now = datetime.now(self._config.timezone)
        start_of_day = datetime.combine(now.date(), time.min, self._config.timezone)
        lower_bound = (
            self._parse_timestamp(from_time, "from_time") if from_time else start_of_day
        )
        upper_bound = (
            self._parse_timestamp(to_time, "to_time")
            if to_time
            else start_of_day + timedelta(days=1)
        )
        if lower_bound >= upper_bound:
            raise ValueError("from_time must be earlier than to_time")
        return lower_bound, upper_bound

    def _parse_timestamp(self, value: str, field_name: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{field_name} must be an ISO 8601 timestamp") from error
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=self._config.timezone)
        return parsed

    def _discover_candidates(
        self,
        *,
        thread_id: str | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> tuple[list[TaskCandidate], list[Path]]:
        cached = self._discovery_cache
        if cached is not None and monotonic() - cached[3] <= RUN_CACHE_FRESH_SECONDS:
            candidates, paths, cached_thread_id, _cached_at = cached
            if cached_thread_id is None or cached_thread_id == thread_id:
                return candidates, paths
        candidate_paths = sorted(
            {
                path.resolve()
                for root in self._config.session_roots
                for path in self._runtime._candidate_rollouts(root)
            }
        )
        discovery = self._runtime._native_rollout_discovery(
            candidate_paths,
            self._runtime._default_codex_discovery_index_path(),
        )
        candidates: list[TaskCandidate] = []
        seen: dict[str, Path] = {}
        for path, metadata in discovery.metadata.items():
            if cancelled is not None and cancelled():
                raise RuntimeError("Report operation cancelled")
            if metadata.identity is None:
                continue
            if thread_id is not None and metadata.identity[0] != thread_id:
                continue
            indexed_entry = self._runtime._read_codex_catalog_entry(
                path, path.parent.name, include_title=True
            )
            if indexed_entry is None:
                continue
            candidate = TaskCandidate(
                thread_id=metadata.identity[0],
                title=indexed_entry.task_title or metadata.task_title,
                timestamp=datetime.fromisoformat(
                    metadata.started_at.replace("Z", "+00:00")
                ),
                last_activity_at=datetime.fromtimestamp(
                    metadata.modified_at_ns / 1_000_000_000, tz=timezone.utc
                ),
            )
            previous = seen.get(candidate.thread_id)
            if previous is not None and previous != path:
                raise ValueError(
                    f"Duplicate rollout ownership for thread {candidate.thread_id}: "
                    f"{previous} and {path}"
                )
            seen[candidate.thread_id] = path
            candidates.append(candidate)
        self._discovery_cache = (candidates, candidate_paths, thread_id, monotonic())
        return candidates, candidate_paths

    def _get_or_build_run(
        self,
        thread_id: str,
        *,
        candidate_paths: list[Path],
        title: str,
        cancelled: Callable[[], bool] | None,
    ) -> object:
        if cancelled is not None and cancelled():
            raise RuntimeError("Report operation cancelled")
        cached = self._run_cache.get(thread_id)
        if cached is not None:
            run, signature, cached_at = cached
            if monotonic() - cached_at <= RUN_CACHE_FRESH_SECONDS:
                return run
            try:
                current = tuple(
                    (path, Path(path).stat().st_size, Path(path).stat().st_mtime_ns)
                    for path, _size, _mtime in signature
                )
            except OSError:
                current = ()
            if current == signature:
                return run
            self._run_cache.pop(thread_id, None)

        run = self._runtime.build_codex_rollout_run(
            thread_id,
            list(self._config.session_roots),
            candidate_paths=candidate_paths,
            title=title,
            discovery_index_path=self._runtime._default_codex_discovery_index_path(),
            cancelled=cancelled,
        )
        manifest = getattr(run, "source_manifest", None)
        if isinstance(manifest, list) and manifest:
            signature = tuple(
                (str(entry.path), int(entry.size_bytes), int(entry.modified_at_ns))
                for entry in manifest
            )
            self._run_cache[thread_id] = (run, signature, monotonic())
        return run

    def _select_candidate(
        self,
        candidates: list[TaskCandidate],
        *,
        thread_id: str | None,
        lower_bound: datetime,
        upper_bound: datetime,
        name_contains: list[str],
    ) -> TaskCandidate | dict[str, object]:
        if thread_id:
            matches = [item for item in candidates if item.thread_id == thread_id]
        else:
            queries = [query.casefold() for query in name_contains]
            matches = [
                item
                for item in candidates
                if item.timestamp.astimezone(lower_bound.tzinfo) < upper_bound
                and item.last_activity_at.astimezone(lower_bound.tzinfo) >= lower_bound
                and all(query in item.title.casefold() for query in queries)
            ]
        if not matches:
            return self._error("REPORT_NOT_FOUND", "No matching Codex task was found.")
        if len(matches) > 1:
            ordered = sorted(
                matches, key=lambda item: (item.last_activity_at, item.thread_id)
            )
            return {
                "ok": False,
                "code": "REPORT_SELECTION_AMBIGUOUS",
                "message": "More than one Codex task matches the supplied filters.",
                "matches": [
                    {
                        "thread_id": item.thread_id,
                        "title": item.title,
                        "timestamp": item.timestamp.isoformat(),
                        "last_activity_at": item.last_activity_at.isoformat(),
                    }
                    for item in ordered
                ],
            }
        return matches[0]

    def _resolve_output_directory(
        self,
        output_path: str | None,
        workspace_root: Path,
        *,
        enforce_root: bool = True,
    ) -> tuple[Path, Path]:
        selected = (
            Path(output_path).expanduser()
            if output_path is not None
            else self._config.default_output
        )
        if enforce_root:
            return _authorized_output_target(
                selected, workspace_root, require_existing_parent=False
            )
        if not selected.is_absolute():
            selected = workspace_root / selected
        return workspace_root, selected.resolve()

    def _write_bundle(
        self,
        directory: Path,
        representations: Mapping[str, str],
        *,
        authorized_root: Path,
    ) -> dict[str, str]:
        root, target = _authorized_output_target(
            directory, authorized_root, require_existing_parent=False
        )
        descriptor = _open_authorized_directory(root, target)
        try:
            paths = {
                key: _write_authorized_file(
                    target, descriptor, filename, representations[key]
                )
                for key, filename in REPORT_FILENAMES.items()
            }
            if descriptor is not None:
                os.fsync(descriptor)
        finally:
            if descriptor is not None:
                os.close(descriptor)
        return {key: str(path) for key, path in paths.items()}

    @staticmethod
    def _error(code: str, message: str) -> dict[str, object]:
        return {"ok": False, "code": code, "message": message}
