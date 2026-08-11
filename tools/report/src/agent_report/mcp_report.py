# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Select Codex tasks and return bounded report or query results.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

"""MCP-facing task selection, report generation, and telemetry queries."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from time import monotonic
from types import ModuleType
from typing import Literal
from urllib.parse import urlparse
from urllib.request import url2pathname
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


class ReportGenerator:
    """Generate MCP results through the existing authoritative report runtime."""

    def __init__(self, runtime: ModuleType, config: ReportServerConfig) -> None:
        self._runtime = runtime
        self._config = config
        self._run_cache: dict[
            str, tuple[object, tuple[tuple[str, int, int], ...], float]
        ] = {}
        self._discovery_cache: (
            tuple[list[TaskCandidate], list[Path], str | None, float] | None
        ) = None

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

        base_workspace = (
            workspace_root or self._config.workspace_root or Path.cwd().resolve()
        )
        report_directory = self._resolve_output_directory(output_path, base_workspace)
        written_files: dict[str, str] = {}
        warnings: list[dict[str, str]] = []
        try:
            written_files = self._write_bundle(report_directory, representations)
        except OSError as error:
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
                timestamp=datetime.fromisoformat(metadata.started_at.replace("Z", "+00:00")),
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
        self, output_path: str | None, workspace_root: Path
    ) -> Path:
        selected = (
            Path(output_path).expanduser()
            if output_path is not None
            else self._config.default_output
        )
        if not selected.is_absolute():
            selected = workspace_root / selected
        return selected.resolve()

    def _write_bundle(
        self, directory: Path, representations: Mapping[str, str]
    ) -> dict[str, str]:
        directory.mkdir(parents=True, exist_ok=True)
        paths = {
            key: directory / filename for key, filename in REPORT_FILENAMES.items()
        }
        for key, path in paths.items():
            path.write_text(representations[key], encoding="utf-8")
        return {key: str(path.resolve()) for key, path in paths.items()}

    @staticmethod
    def _error(code: str, message: str) -> dict[str, object]:
        return {"ok": False, "code": code, "message": message}
