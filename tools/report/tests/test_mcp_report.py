# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Verify MCP report selection, output, inline, and startup contracts.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from agent_report import application_service as service_types
from agent_report import mcp_report as report_module
from agent_report import static_export
from agent_report.mcp_report import (
    ReportGenerator,
    ReportServerConfig,
    load_server_config,
    validate_startup,
    workspace_root_from_uri,
)


class FakeRuntime:
    """Small observable substitute for the existing report runtime boundary."""

    def __init__(self, entries: list[tuple[str, str, datetime, Path]]) -> None:
        self.entries = entries
        self.build_calls = 0
        self.catalog_reads = 0
        self.protocol_calls: list[tuple[list[Path], Path | None]] = []

    def _candidate_rollouts(self, root: Path) -> list[Path]:
        return [entry[3] for entry in self.entries if root in entry[3].parents]

    def _default_codex_discovery_index_path(self) -> Path:
        return Path("/tmp/report-index.sqlite3")

    def _native_rollout_discovery(
        self, paths: list[Path], index_path: Path | None
    ) -> SimpleNamespace:
        self.protocol_calls.append((paths, index_path))
        by_path = {entry[3]: entry for entry in self.entries}
        return SimpleNamespace(
            metadata={
                path: SimpleNamespace(
                    identity=(by_path[path][0], "", "", ""),
                    task_title=by_path[path][1],
                    started_at=by_path[path][2].isoformat(),
                    modified_at_ns=path.stat().st_mtime_ns,
                )
                for path in paths
            }
        )

    def _read_codex_catalog_entry(
        self, path: Path, _source_store: str, *, include_title: bool
    ) -> SimpleNamespace:
        assert include_title is True
        self.catalog_reads += 1
        entry = next(entry for entry in self.entries if entry[3] == path)
        return SimpleNamespace(started_at=entry[2], task_title=entry[1])

    def build_codex_rollout_run(self, thread_id: str, *_args, **_kwargs) -> str:
        self.build_calls += 1
        return thread_id

    def render_codex_rollout_html(self, run: str) -> str:
        return f"<html>{run}</html>"

    def codex_run_to_json(self, run: str) -> str:
        return f'{{"thread_id":"{run}"}}'

    def render_codex_rollout_turn_csv(self, run: str) -> str:
        return f"thread_id\n{run}\n"

    def render_codex_rollout_work_unit_csv(self, run: str) -> str:
        return f"thread_id,work\n{run},one\n"

    def render_codex_rollout_markdown(self, run: str) -> str:
        return f"# {run}\n"

    def query_codex_run_time_range(self, run: str, **kwargs) -> dict[str, object]:
        return {"runtime_run": run, **kwargs}

    def get_codex_run_event_details(
        self, run: str, event_id: str
    ) -> dict[str, object] | None:
        if event_id == "evt_000000000000000000000000":
            return None
        return {"event_id": event_id, "runtime_run": run, "detail": "safe"}


def _config(
    sessions_root: Path,
    output: Path,
    *,
    max_inline_bytes: int = 65_536,
) -> ReportServerConfig:
    return ReportServerConfig(
        session_roots=(sessions_root,),
        default_output=output,
        timezone=timezone.utc,
        timezone_name="UTC",
        max_inline_bytes=max_inline_bytes,
    )


def _entry(
    root: Path,
    thread_id: str,
    title: str,
    timestamp: str,
    *,
    last_activity: str | None = None,
) -> tuple[str, str, datetime, Path]:
    path = root / f"{thread_id}.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    started_at = datetime.fromisoformat(timestamp)
    activity_at = datetime.fromisoformat(last_activity) if last_activity else started_at
    activity_ns = int(activity_at.timestamp() * 1_000_000_000)
    os.utime(path, ns=(activity_ns, activity_ns))
    return thread_id, title, started_at, path.resolve()


def test_load_server_config_rejects_oversized_inline_limit(tmp_path: Path) -> None:
    """Fail startup instead of accepting a response limit above 64 KiB."""

    with pytest.raises(RuntimeError, match="1 to 65536"):
        load_server_config(
            {
                "AGENT_REPORT_SESSIONS_ROOTS": str(tmp_path),
                "AGENT_REPORT_MAX_INLINE_BYTES": "65537",
            },
            local_timezone=timezone.utc,
        )


def test_exact_thread_selection_ignores_date_and_name_filters(tmp_path: Path) -> None:
    """An exact task ID remains authoritative over optional search filters."""

    entry = _entry(tmp_path, "thread-1", "Exact task", "2026-08-09T12:00:00+00:00")
    runtime = FakeRuntime([entry])
    generator = ReportGenerator(runtime, _config(tmp_path, Path(".codex/report")))

    result = generator.generate_report(
        thread_id="thread-1",
        from_time="2026-08-10T00:00:00Z",
        to_time="2026-08-11T00:00:00Z",
        name_contains=["does not match"],
        workspace_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["thread_id"] == "thread-1"
    assert runtime.build_calls == 1


def test_time_range_query_builds_one_task_and_returns_structured_data(
    tmp_path: Path,
) -> None:
    entry = _entry(tmp_path, "thread-1", "Query task", "2026-08-10T12:00:00+00:00")
    runtime = FakeRuntime([entry])
    generator = ReportGenerator(runtime, _config(tmp_path, Path("bundle")))

    result = generator.query_time_range(
        thread_id="thread-1",
        from_time="2026-08-10T12:05:00Z",
        to_time="2026-08-10T12:35:00Z",
        bucket_minutes=5,
        measure="output_tokens",
        include_events=True,
    )

    assert result["ok"] is True
    assert result["thread_id"] == "thread-1"
    assert result["task_name"] == "Query task"
    assert result["runtime_run"] == "thread-1"
    assert result["bucket_minutes"] == 5
    assert result["measure"] == "output_tokens"
    assert result["include_events"] is True
    assert runtime.build_calls == 1


def test_exact_time_range_query_only_reads_selected_catalog_entry(
    tmp_path: Path,
) -> None:
    entries = [
        _entry(
            tmp_path,
            f"thread-{index}",
            f"Task {index}",
            "2026-08-10T12:00:00+00:00",
        )
        for index in range(100)
    ]
    runtime = FakeRuntime(entries)
    generator = ReportGenerator(runtime, _config(tmp_path, Path("bundle")))

    result = generator.query_time_range(thread_id="thread-73")

    assert result["ok"] is True
    assert runtime.catalog_reads == 1


def test_repeated_time_range_query_reuses_fresh_task_snapshot(tmp_path: Path) -> None:
    entry = _entry(tmp_path, "thread-1", "Query task", "2026-08-10T12:00:00+00:00")

    class CacheRuntime(FakeRuntime):
        def build_codex_rollout_run(self, thread_id: str, *_args, **_kwargs) -> object:
            self.build_calls += 1
            stat = entry[3].stat()
            return SimpleNamespace(
                thread_id=thread_id,
                source_manifest=[
                    SimpleNamespace(
                        path=str(entry[3]),
                        size_bytes=stat.st_size,
                        modified_at_ns=stat.st_mtime_ns,
                    )
                ],
            )

    runtime = CacheRuntime([entry])
    generator = ReportGenerator(runtime, _config(tmp_path, Path("bundle")))

    first = generator.query_time_range(thread_id="thread-1", bucket_minutes=15)
    second = generator.query_time_range(thread_id="thread-1", bucket_minutes=5)

    assert first["ok"] is True
    assert second["ok"] is True
    assert runtime.build_calls == 1
    assert runtime.catalog_reads == 1


def test_cancelled_time_range_query_stops_before_catalog_reads(tmp_path: Path) -> None:
    entry = _entry(tmp_path, "thread-1", "Query task", "2026-08-10T12:00:00+00:00")
    runtime = FakeRuntime([entry])
    generator = ReportGenerator(runtime, _config(tmp_path, Path("bundle")))

    result = generator.query_time_range(thread_id="thread-1", cancelled=lambda: True)

    assert result["code"] == "REPORT_DISCOVERY_FAILED"
    assert runtime.catalog_reads == 0
    assert runtime.build_calls == 0


def test_time_range_query_rejects_unsupported_bucket_before_build(
    tmp_path: Path,
) -> None:
    entry = _entry(tmp_path, "thread-1", "Query task", "2026-08-10T12:00:00+00:00")
    runtime = FakeRuntime([entry])
    generator = ReportGenerator(runtime, _config(tmp_path, Path("bundle")))

    result = generator.query_time_range(thread_id="thread-1", bucket_minutes=2)

    assert result["code"] == "REPORT_INVALID_REQUEST"
    assert runtime.build_calls == 0


def test_event_detail_query_returns_one_authoritative_event(tmp_path: Path) -> None:
    entry = _entry(tmp_path, "thread-1", "Query task", "2026-08-10T12:00:00+00:00")
    runtime = FakeRuntime([entry])
    generator = ReportGenerator(runtime, _config(tmp_path, Path("bundle")))

    result = generator.get_event_details(
        thread_id="thread-1", event_id="evt_1234567890abcdef12345678"
    )
    missing = generator.get_event_details(
        thread_id="thread-1", event_id="evt_000000000000000000000000"
    )

    assert result == {
        "ok": True,
        "thread_id": "thread-1",
        "task_name": "Query task",
        "event": {
            "event_id": "evt_1234567890abcdef12345678",
            "runtime_run": "thread-1",
            "detail": "safe",
        },
    }
    assert missing["code"] == "REPORT_EVENT_NOT_FOUND"
    assert runtime.build_calls == 2


def test_event_detail_rejects_malformed_id_before_build(tmp_path: Path) -> None:
    entry = _entry(tmp_path, "thread-1", "Query task", "2026-08-10T12:00:00+00:00")
    runtime = FakeRuntime([entry])
    generator = ReportGenerator(runtime, _config(tmp_path, Path("bundle")))

    result = generator.get_event_details(thread_id="thread-1", event_id="bad")

    assert result["code"] == "REPORT_INVALID_REQUEST"
    assert runtime.build_calls == 0


def test_filtered_selection_is_start_inclusive_end_exclusive_and_all_names_match(
    tmp_path: Path,
) -> None:
    """Apply the specified half-open interval and AND title matching."""

    entries = [
        _entry(
            tmp_path, "start", "Create Document Outline", "2026-08-10T00:00:00+00:00"
        ),
        _entry(tmp_path, "end", "Create Document Outline", "2026-08-11T00:00:00+00:00"),
        _entry(tmp_path, "partial", "Create Outline", "2026-08-10T01:00:00+00:00"),
    ]
    generator = ReportGenerator(
        FakeRuntime(entries), _config(tmp_path, Path(".codex/report"))
    )

    result = generator.generate_report(
        from_time="2026-08-10T00:00:00Z",
        to_time="2026-08-11T00:00:00Z",
        name_contains=["CREATE", "document"],
        workspace_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["thread_id"] == "start"


def test_filtered_selection_includes_task_active_during_range(tmp_path: Path) -> None:
    entry = _entry(
        tmp_path,
        "active",
        "Long-running task",
        "2026-08-09T20:00:00+00:00",
        last_activity="2026-08-10T12:30:00+00:00",
    )
    generator = ReportGenerator(
        FakeRuntime([entry]), _config(tmp_path, Path(".codex/report"))
    )

    result = generator.generate_report(
        from_time="2026-08-10T12:00:00Z",
        to_time="2026-08-10T13:00:00Z",
        workspace_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["thread_id"] == "active"


def test_filtered_selection_returns_structured_ambiguity(tmp_path: Path) -> None:
    """Return every matching identity instead of making an arbitrary choice."""

    entries = [
        _entry(tmp_path, "one", "Report task", "2026-08-10T01:00:00+00:00"),
        _entry(tmp_path, "two", "Report task", "2026-08-10T02:00:00+00:00"),
    ]
    generator = ReportGenerator(
        FakeRuntime(entries), _config(tmp_path, Path(".codex/report"))
    )

    result = generator.generate_report(
        from_time="2026-08-10T00:00:00Z",
        to_time="2026-08-11T00:00:00Z",
        name_contains=["report"],
        workspace_root=tmp_path,
    )

    assert result["code"] == "REPORT_SELECTION_AMBIGUOUS"
    assert [match["thread_id"] for match in result["matches"]] == ["one", "two"]


def test_naive_filter_timestamps_use_configured_server_timezone(
    tmp_path: Path,
) -> None:
    """Interpret offset-free ISO input in the configured local timezone."""

    entry = _entry(tmp_path, "local", "Local task", "2026-08-10T04:30:00+00:00")
    config = ReportServerConfig(
        session_roots=(tmp_path,),
        default_output=Path("bundle"),
        timezone=ZoneInfo("America/Toronto"),
        timezone_name="America/Toronto",
        max_inline_bytes=65_536,
    )
    generator = ReportGenerator(FakeRuntime([entry]), config)

    result = generator.generate_report(
        from_time="2026-08-10T00:00:00",
        to_time="2026-08-10T01:00:00",
        workspace_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["thread_id"] == "local"


def test_selection_uses_existing_redacted_catalog_title(tmp_path: Path) -> None:
    """Do not expose the native index's raw task title in MCP results."""

    entry = _entry(
        tmp_path, "thread-1", "Raw API_TOKEN=secret", "2026-08-10T12:00:00+00:00"
    )
    runtime = FakeRuntime([entry])

    def redacted_entry(
        path: Path, _source_store: str, *, include_title: bool
    ) -> SimpleNamespace:
        assert path == entry[3]
        assert include_title is True
        return SimpleNamespace(
            started_at=entry[2], task_title="Raw API_TOKEN=[REDACTED]"
        )

    runtime._read_codex_catalog_entry = redacted_entry
    generator = ReportGenerator(runtime, _config(tmp_path, Path("bundle")))

    result = generator.generate_report(thread_id="thread-1", workspace_root=tmp_path)

    assert result["task_name"] == "Raw API_TOKEN=[REDACTED]"


def test_one_snapshot_writes_the_complete_stable_bundle(tmp_path: Path) -> None:
    """Render every representation from one build and use stable filenames."""

    entry = _entry(tmp_path, "thread-1", "Bundle task", "2026-08-10T12:00:00+00:00")
    runtime = FakeRuntime([entry])
    generator = ReportGenerator(runtime, _config(tmp_path, Path(".codex/report")))

    result = generator.generate_report(
        thread_id="thread-1",
        output_path="custom-report",
        workspace_root=tmp_path,
    )

    assert result["ok"] is True
    assert runtime.build_calls == 1
    assert {Path(path).name for path in result["written_files"].values()} == {
        "report.html",
        "report.json",
        "turns.csv",
        "work-units.csv",
        "report.md",
    }


def test_classic_generation_does_not_use_injected_snapshot_service(
    tmp_path: Path,
) -> None:
    """Keep classic generation independent from the additive snapshot API."""

    entry = _entry(tmp_path, "thread-1", "Classic task", "2026-08-10T12:00:00+00:00")
    runtime = FakeRuntime([entry])

    class Service:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(
                f"classic generation called snapshot service method {name}"
            )

        def close(self) -> None:
            pass

    generator = ReportGenerator(
        runtime,
        _config(tmp_path, Path("classic")),
        application_service=Service(),  # type: ignore[arg-type]
    )

    result = generator.generate_report(thread_id="thread-1", workspace_root=tmp_path)

    assert result["ok"] is True
    assert runtime.build_calls == 1
    assert {Path(path).name for path in result["written_files"].values()} == {
        "report.html",
        "report.json",
        "turns.csv",
        "work-units.csv",
        "report.md",
    }


def test_oversized_inline_report_is_not_truncated_and_keeps_written_paths(
    tmp_path: Path,
) -> None:
    """Reject the complete selected representation after writing the bundle."""

    entry = _entry(tmp_path, "thread-1", "Large task", "2026-08-10T12:00:00+00:00")
    generator = ReportGenerator(
        FakeRuntime([entry]), _config(tmp_path, Path("bundle"), max_inline_bytes=8)
    )

    result = generator.generate_report(
        thread_id="thread-1", return_via_mcp=True, workspace_root=tmp_path
    )

    assert result["code"] == "REPORT_TOO_LARGE_FOR_MCP"
    assert result["actual_bytes"] > result["maximum_bytes"]
    assert "inline" not in result
    assert Path(result["written_files"]["html"]).is_file()


def test_inline_delivery_survives_filesystem_failure(tmp_path: Path) -> None:
    """Return complete inline content with a structured write warning."""

    entry = _entry(tmp_path, "thread-1", "Inline task", "2026-08-10T12:00:00+00:00")
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    generator = ReportGenerator(FakeRuntime([entry]), _config(tmp_path, Path("bundle")))

    result = generator.generate_report(
        thread_id="thread-1",
        output_path=str(blocked),
        return_via_mcp=True,
        return_format="markdown",
        workspace_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["inline"]["format"] == "markdown"
    assert result["warnings"][0]["code"] == "REPORT_WRITE_FAILED"


def test_filesystem_failure_is_fatal_without_inline_delivery(tmp_path: Path) -> None:
    """Require a complete filesystem bundle when inline delivery is disabled."""

    entry = _entry(tmp_path, "thread-1", "Write task", "2026-08-10T12:00:00+00:00")
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    generator = ReportGenerator(FakeRuntime([entry]), _config(tmp_path, Path("bundle")))

    result = generator.generate_report(
        thread_id="thread-1", output_path=str(blocked), workspace_root=tmp_path
    )

    assert result["code"] == "REPORT_WRITE_FAILED"


@pytest.mark.parametrize("output_path", ["../escape", "/tmp/outside-agent-report"])
def test_classic_report_rejects_output_outside_authorized_workspace(
    tmp_path: Path, output_path: str
) -> None:
    """Reject lexical traversal and absolute targets outside the MCP workspace."""

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry = _entry(tmp_path, "thread-1", "Secure task", "2026-08-10T12:00:00+00:00")
    generator = ReportGenerator(FakeRuntime([entry]), _config(tmp_path, Path("bundle")))

    result = generator.generate_report(
        thread_id="thread-1", output_path=output_path, workspace_root=workspace
    )

    assert result["code"] == "REPORT_INVALID_REQUEST"


def test_classic_report_rejects_symlink_ancestor_and_leaf(
    tmp_path: Path,
) -> None:
    """Never follow a symlink component while publishing the classic bundle."""

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "linked").symlink_to(outside, target_is_directory=True)
    entry = _entry(tmp_path, "thread-1", "Secure task", "2026-08-10T12:00:00+00:00")
    generator = ReportGenerator(FakeRuntime([entry]), _config(tmp_path, Path("bundle")))

    ancestor = generator.generate_report(
        thread_id="thread-1", output_path="linked/report", workspace_root=workspace
    )
    report = workspace / "report"
    report.mkdir()
    protected = outside / "protected.html"
    protected.write_text("unchanged", encoding="utf-8")
    (report / "report.html").symlink_to(protected)
    leaf = generator.generate_report(
        thread_id="thread-1", output_path="report", workspace_root=workspace
    )

    assert ancestor["code"] == "REPORT_INVALID_REQUEST"
    assert leaf["code"] == "REPORT_WRITE_FAILED"
    assert protected.read_text(encoding="utf-8") == "unchanged"


def test_snapshot_export_rejects_outside_and_symlink_targets_before_service(
    tmp_path: Path,
) -> None:
    """Apply the same MCP workspace authority before snapshot export dispatch."""

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "linked").symlink_to(outside, target_is_directory=True)

    class Service:
        def export_snapshot(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("unauthorized target reached the application service")

        def close(self) -> None:
            pass

    generator = ReportGenerator(
        FakeRuntime([]),
        _config(tmp_path, Path("bundle")),
        application_service=Service(),  # type: ignore[arg-type]
    )

    outside_result = generator.export_snapshot_for_mcp(
        snapshot_id="snap_1234567890abcdef12345678",
        target=str(outside / "report"),
        workspace_root=workspace,
    )
    symlink_result = generator.export_snapshot_for_mcp(
        snapshot_id="snap_1234567890abcdef12345678",
        target="linked/report",
        workspace_root=workspace,
    )

    assert outside_result["code"] == "REPORT_INVALID_REQUEST"
    assert symlink_result["code"] == "REPORT_INVALID_REQUEST"


def test_classic_generation_does_not_initialize_lazy_snapshot_service(
    tmp_path: Path,
) -> None:
    """Keep classic MCP generation available when the cache cannot initialize."""

    entry = _entry(tmp_path, "thread-1", "Classic task", "2026-08-10T12:00:00+00:00")

    def unavailable_service() -> service_types.ApplicationService:
        raise OSError("cache is unwritable")

    generator = ReportGenerator(
        FakeRuntime([entry]),
        _config(tmp_path, Path("bundle")),
        application_service_factory=unavailable_service,
    )

    result = generator.generate_report(thread_id="thread-1", workspace_root=tmp_path)

    assert result["ok"] is True


def _publication_request(
    target: Path,
    mode: static_export.ExportMode = static_export.ExportMode.SUMMARY,
    *,
    replace_target: bool = False,
) -> static_export.ExportRequest:
    return static_export.ExportRequest(
        "op_1234567890abcdef12345678",
        "snap_1234567890abcdef12345678",
        "revision",
        mode,
        target,
        replace_target,
    )


def test_publication_staging_is_exact_private_and_same_device(tmp_path: Path) -> None:
    publication = report_module._FilesystemPublication("mcp", authorized_root=tmp_path)

    plan = publication.authorize(_publication_request(tmp_path / "summary.html"))

    metadata = plan.staging_directory.lstat()
    assert report_module._STAGING_NAME.fullmatch(plan.staging_directory.name)
    assert stat.S_IMODE(metadata.st_mode) == 0o700
    assert metadata.st_dev == tmp_path.lstat().st_dev
    publication.discard(plan)


def test_summary_replace_is_one_atomic_replace_without_backup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "summary.html"
    target.write_text("old", encoding="utf-8")
    publication = report_module._FilesystemPublication("mcp", authorized_root=tmp_path)
    plan = publication.authorize(_publication_request(target, replace_target=True))
    staged = plan.staging_directory / "summary.html"
    staged.write_text("new", encoding="utf-8")
    calls: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def observed_replace(source, destination):  # type: ignore[no-untyped-def]
        calls.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(report_module.os, "replace", observed_replace)

    assert publication.publish(plan, staged, ()) == target
    assert calls == [(staged, target)]
    assert target.read_text(encoding="utf-8") == "new"
    assert not any("backup" in path.name for path in tmp_path.iterdir())


def test_existing_directory_replace_is_rejected_before_staging(tmp_path: Path) -> None:
    target = tmp_path / "report"
    target.mkdir()
    publication = report_module._FilesystemPublication("mcp", authorized_root=tmp_path)

    with pytest.raises(service_types.PublicationFailure, match="Atomic replacement"):
        publication.authorize(
            _publication_request(
                target,
                static_export.ExportMode.DIRECTORY,
                replace_target=True,
            )
        )

    assert not any(
        report_module._STAGING_NAME.fullmatch(path.name) for path in tmp_path.iterdir()
    )


def test_publication_revalidation_rejects_target_swap(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "summary.html"
    publication = report_module._FilesystemPublication("mcp", authorized_root=tmp_path)
    plan = publication.authorize(_publication_request(target))
    staged = plan.staging_directory / "summary.html"
    staged.write_text("new", encoding="utf-8")
    target.symlink_to(outside / "escaped.html")

    with pytest.raises(service_types.PublicationFailure, match="changed"):
        publication.publish(plan, staged, ())

    assert not (outside / "escaped.html").exists()
    target.unlink()
    publication.discard(plan)


def test_stale_cleanup_removes_only_exact_old_owned_staging(
    tmp_path: Path,
) -> None:
    publication = report_module._FilesystemPublication("mcp", authorized_root=tmp_path)
    plan = publication.authorize(_publication_request(tmp_path / "summary.html"))
    publication.discard(plan)
    old = tmp_path / f"{static_export.STAGING_PREFIX}{'a' * 32}"
    old.mkdir(mode=0o700)
    malformed = tmp_path / f"{static_export.STAGING_PREFIX}not-owned"
    malformed.mkdir()
    fresh = tmp_path / f"{static_export.STAGING_PREFIX}{'b' * 32}"
    fresh.mkdir(mode=0o700)
    staging_file = tmp_path / f"{static_export.STAGING_PREFIX}{'c' * 32}"
    staging_file.write_text("keep", encoding="utf-8")
    legacy_backup = tmp_path / ".summary.html.backup-abcdef123456"
    legacy_backup.write_text("keep", encoding="utf-8")
    old_timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    os.utime(old, (old_timestamp, old_timestamp))

    removed = publication.cleanup_stale(
        older_than=datetime(2026, 2, 1, tzinfo=timezone.utc)
    )

    assert removed == (old,)
    assert not old.exists()
    assert malformed.exists() and fresh.exists() and staging_file.exists()
    assert legacy_backup.exists()


def test_startup_validation_forces_and_probes_bundled_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Use the packaged executable and invoke the expected empty index protocol."""

    engine = tmp_path / "agent-report-engine"
    engine.write_text("binary", encoding="utf-8")
    engine.chmod(0o755)
    runtime = FakeRuntime([])
    monkeypatch.setenv("AGENT_REPORT_ENGINE", "/tmp/external-engine")

    validate_startup(runtime, engine)

    assert os.environ["AGENT_REPORT_ENGINE"] == str(engine)
    assert runtime.protocol_calls == [([], None)]


def test_workspace_root_accepts_only_existing_local_file_uris(tmp_path: Path) -> None:
    """Do not treat remote or non-file client roots as local workspaces."""

    assert workspace_root_from_uri(tmp_path.as_uri()) == tmp_path.resolve()
    assert workspace_root_from_uri("https://example.com/workspace") is None
    assert workspace_root_from_uri("file://remote-host/workspace") is None


def test_snapshot_adapter_uses_crypto_operation_and_exact_open_binding(
    tmp_path: Path,
) -> None:
    """Map MCP fields to the reconciled service DTO without changing names."""

    captured: dict[str, object] = {}

    class Service:
        def open_snapshot(self, context, request, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(context=context, request=request, **kwargs)
            return service_types.ServiceResult(
                True,
                service_types.SnapshotMetadata(
                    service_types.PROTOCOL_VERSION,
                    "snap_1234567890abcdef12345678",
                    "a" * 64,
                    "thread-1",
                    True,
                    False,
                    "b" * 64,
                    "parser-v1",
                    "c" * 64,
                    "d" * 64,
                    datetime(2026, 8, 12, tzinfo=timezone.utc),
                    "sealed",
                    (),
                ),
            )

        def close(self) -> None:
            pass

    generator = ReportGenerator(
        FakeRuntime([]),
        _config(tmp_path, Path("bundle")),
        application_service=Service(),  # type: ignore[arg-type]
    )

    result = generator.open_snapshot(
        root_thread_id="thread-1",
        preflight_token="token",
        source_revision="b" * 64,
        include_children=True,
    )

    context = captured["context"]
    request = captured["request"]
    assert isinstance(context, service_types.OperationContext)
    assert context.operation_id.startswith("op_")
    assert len(context.operation_id) == 27
    assert isinstance(request, service_types.OpenSnapshotRequest)
    assert request.source_revision == "b" * 64
    assert request.scope.include_children is True
    assert result["ok"] is True
    assert result["revision_id"] == "a" * 64
    assert result["observation_time"] == "2026-08-12T00:00:00+00:00"


def test_snapshot_adapter_preserves_structured_service_error(tmp_path: Path) -> None:
    """Return service error fields directly instead of parsing exception text."""

    class Service:
        def get_summary(self, context, request, **kwargs):  # type: ignore[no-untyped-def]
            return service_types.ServiceResult(
                False,
                error=service_types.ReportError(
                    "REPORT_SNAPSHOT_NOT_FOUND",
                    "The report snapshot was not found.",
                    True,
                    context.operation_id,
                ),
            )

        def close(self) -> None:
            pass

    generator = ReportGenerator(
        FakeRuntime([]),
        _config(tmp_path, Path("bundle")),
        application_service=Service(),  # type: ignore[arg-type]
    )

    result = generator.get_summary(snapshot_id="snap_1234567890abcdef12345678")

    assert result["ok"] is False
    assert result["code"] == "REPORT_SNAPSHOT_NOT_FOUND"
    assert str(result["operation_id"]).startswith("op_")


def test_runtime_discovery_returns_typed_not_found_failure(tmp_path: Path) -> None:
    """Construct the complete DiscoveryFailure expected by the service boundary."""

    class Runtime:
        @staticmethod
        def _candidate_rollouts(root: Path) -> list[Path]:
            return []

        @staticmethod
        def _default_codex_discovery_index_path() -> Path:
            return tmp_path / "index.sqlite3"

        @staticmethod
        def _discover_rollout_paths(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise ValueError("missing")

    class Cancellation:
        @staticmethod
        def is_cancelled() -> bool:
            return False

    discovery = report_module._RuntimeDiscovery(Runtime())  # type: ignore[arg-type]
    with pytest.raises(service_types.DiscoveryFailure) as captured:
        discovery.preflight(
            service_types.ReportScope("missing-thread", False, False),
            (tmp_path,),
            Cancellation(),
            None,
        )
    assert captured.value.kind == "not_found"
    assert captured.value.safe_message == "The selected report task was not found."
    assert captured.value.recoverable is True


@pytest.mark.parametrize(
    ("include_children", "include_collaborators", "expected"),
    [
        (False, False, (("root", "root"),)),
        (True, False, (("root", "root"), ("child", "child"))),
        (False, True, (("root", "root"), ("peer", "collaborator"))),
        (True, True, (("root", "root"), ("child", "child"), ("peer", "collaborator"))),
    ],
)
def test_runtime_discovery_matches_packaged_signature_and_independent_scope(
    tmp_path: Path,
    include_children: bool,
    include_collaborators: bool,
    expected: tuple[tuple[str, str], ...],
) -> None:
    paths = {name: tmp_path / f"{name}.jsonl" for name in ("root", "child", "peer")}
    for name, path in paths.items():
        path.write_text(name, encoding="utf-8")
    identities = {
        paths["root"]: ("root", "", "", "codex"),
        paths["child"]: ("child", "root", "", "codex"),
        paths["peer"]: ("peer", "outside", "", "codex"),
    }

    class PackagedRuntime:
        @staticmethod
        def _candidate_rollouts(_root: Path) -> list[Path]:
            return list(paths.values())

        @staticmethod
        def _default_codex_discovery_index_path() -> Path:
            return tmp_path / "index.sqlite3"

        @staticmethod
        def _discover_rollout_paths(
            root_thread_id: str,
            candidate_paths: list[Path],
            *,
            include_delegations: bool = False,
            index_path: Path | None = None,
        ) -> tuple[list[Path], list[str], None]:
            assert root_thread_id == "root" and index_path is not None
            selected = [paths["root"], paths["child"]]
            if include_delegations:
                selected.append(paths["peer"])
            return selected, [], None

        @staticmethod
        def _rollout_identity(path: Path) -> tuple[str, str, str, str]:
            return identities[path]

    result = report_module._RuntimeDiscovery(PackagedRuntime()).preflight(  # type: ignore[arg-type]
        service_types.ReportScope("root", include_children, include_collaborators),
        (tmp_path,),
        SimpleNamespace(is_cancelled=lambda: False),
        None,
    )

    assert tuple((source.authorized_path.stem, source.relationship) for source in result.sources) == expected
    assert result.child_count == sum(relationship == "child" for _, relationship in expected)
    assert result.collaborator_count == sum(relationship == "collaborator" for _, relationship in expected)


def test_runtime_normalization_calls_packaged_builder_without_include_children(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "root.jsonl"
    source_path.write_text("{}\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    class PackagedRuntime:
        @staticmethod
        def _default_codex_discovery_index_path() -> Path:
            return tmp_path / "index.sqlite3"

        @staticmethod
        def build_codex_rollout_run(
            root_thread_id: str,
            sessions_root: list[Path],
            *,
            seal: bool = False,
            allow_aborted: bool = False,
            include_delegations: bool = False,
            observed_at: datetime | None = None,
            candidate_paths: list[Path] | None = None,
            title: str = "",
            thread_titles: dict[str, str] | None = None,
            discovery_index_path: Path | None = None,
            cancelled=None,
            progress=None,
            worker_progress=None,
            workers: int = 1,
        ) -> object:
            calls.append({"root": root_thread_id, "delegations": include_delegations, "paths": candidate_paths or []})
            return SimpleNamespace(threads=(), observed_at="2026-08-13T12:00:00Z", state="live", root_thread_id="root")

        @staticmethod
        def _cost_for_response(_thread: object, _response: object) -> object:
            raise AssertionError("no responses")

    source = service_types.DiscoveredSource(
        "source-1", source_path, "source-revision", source_path.stat().st_size, "root"
    )
    discovered = service_types.DiscoveredScope(
        service_types.ReportScope("root", False, True), "source-revision", (source,),
        1, source.byte_count, 0, 0, 0, 1, (),
    )
    normalization = report_module._RuntimeNormalization(  # type: ignore[arg-type]
        PackagedRuntime(), seal=False, allow_aborted=False, title="", thread_titles={}, workers=1,
        pricing_version="pricing-v1",
    )

    result = normalization.normalize(
        discovered, "parser-v1", "a" * 64, "b" * 64,
        SimpleNamespace(is_cancelled=lambda: False), None,
    )

    assert calls == [{"root": "root", "delegations": True, "paths": [source_path]}]
    assert result.run.root_thread_id == "root"


def _runtime_query_run() -> SimpleNamespace:
    usage = SimpleNamespace(
        input_tokens=120,
        cached_input_tokens=40,
        uncached_input_tokens=80,
        output_tokens=30,
        reasoning_tokens=10,
        processed_tokens=150,
    )
    root = SimpleNamespace(
        thread_id="agent-root",
        parent_thread_id="",
        agent_nickname="Root",
        agent_role="orchestrator",
        agent_path="/root",
        task_title="Deliver the report",
        model="gpt-5",
        started_at="2026-08-12T12:00:00Z",
        last_observed_at="2026-08-12T12:10:00Z",
        terminal_state="active",
        turns=[],
        activities=[],
        tool_intervals=[
            SimpleNamespace(
                tool_name="send_message",
                started_at="2026-08-12T12:02:00Z",
                argument_summary='{"target":"agent-child","message":"Review ready"}',
                argument_content="",
                source_start_ordinal=2,
            )
        ],
        mcp_calls=[],
        model_name="gpt-5",
        token_totals=usage,
        recorded_cost_usd=Decimal("1.25"),
        context_snapshots=[],
        compactions=[],
        work_item_claim_events=[
            SimpleNamespace(
                operation="claim",
                event_timestamp="2026-08-12T12:03:00Z",
                work_item_id="work-1",
                claim_id="claim-1",
                activity="Implement query semantics",
                disposition="active",
                blocker_reference="",
                agent="agent-root",
                root_task_id="root-task-1",
                outcome="accepted",
                thread_id="agent-root",
                source_ordinal=3,
                transport="mcp",
            )
        ],
    )
    child = SimpleNamespace(
        thread_id="agent-child",
        parent_thread_id="agent-root",
        agent_nickname="Reviewer",
        agent_role="reviewer",
        agent_path="/root/reviewer",
        task_title="Review report",
        model="gpt-5-mini",
        started_at="2026-08-12T12:01:00Z",
        last_observed_at="2026-08-12T12:08:00Z",
        terminal_state="complete",
        turns=[SimpleNamespace(outcome="complete", completed_at="2026-08-12T12:08:00Z", source_ordinal=8)],
        activities=[],
        tool_intervals=[],
        mcp_calls=[],
        token_totals=usage,
        recorded_cost_usd=Decimal("0.25"),
        context_snapshots=[],
        compactions=[],
        work_item_claim_events=[],
    )
    return SimpleNamespace(
        root_thread_id="agent-root",
        run_label="Agent Report",
        state="live",
        observed_at="2026-08-12T12:10:00Z",
        wall_started_at="2026-08-12T12:00:00Z",
        wall_ended_at="2026-08-12T12:10:00Z",
        wall_time_ms=600_000,
        agent_time_ms=900_000,
        active_time_ms=500_000,
        tool_time_ms=20_000,
        critical_path_ms=550_000,
        peak_concurrency=2,
        usage_totals=usage,
        threads=[root, child],
        work_units=[SimpleNamespace(work_unit_id="work-1")],
        work_item_segments=[SimpleNamespace(work_item_id="work-1")],
        phase_lanes=[],
        cost=SimpleNamespace(total_cost=Decimal("1.50"), status="recorded"),
        diagnostics=[],
        parser_version="parser-v1",
        source_manifest=[SimpleNamespace(path="private", size_bytes=1)],
        context_summary=SimpleNamespace(
            current_total_tokens=90,
            capacity=200,
            remaining_tokens=110,
            occupancy_percent=45.0,
            compaction_count=1,
            evidence="measured",
        ),
        inference_summary=SimpleNamespace(
            call_count=2,
            output_tokens=30,
            reasoning_tokens=10,
            inference_time_ms=4_000,
            decode_tokens_per_second=7.5,
            evidence="measured",
        ),
        runtime_states=[SimpleNamespace(state="working", agent_time_ms=500_000, run_time_ms=400_000)],
        all_agents_waiting_ms=50_000,
    )


class _RuntimeQueryRepository:
    def query_events(self, _query):  # type: ignore[no-untyped-def]
        return SimpleNamespace(items=())


def _runtime_query_handle() -> SimpleNamespace:
    return SimpleNamespace(
        run=_runtime_query_run(),
        heatmap_pricing=service_types.HeatmapPricingAuthority("pricing-v1", "a" * 64, ()),
        cache_snapshot_id="cache-snapshot",
        snapshot_id="snap_1234567890abcdef12345678",
        revision_id="revision-1",
    )


def test_read_handle_binds_public_snapshot_and_revision_immutably() -> None:
    run = _runtime_query_run()
    handle = report_module._ReadHandle(
        "snapshot-public", "revision-1", "source-1", "snapshot-cache", run,
        service_types.HeatmapPricingAuthority("pricing-v1", "a" * 64, ()),
        service_types.ReportScope("agent-root")
    )

    assert handle.snapshot_id == "snapshot-public"
    assert handle.run is run
    with pytest.raises(AttributeError):
        handle.snapshot_id = "changed"


def test_runtime_heatmap_query_is_a_thin_delegate_to_shared_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    calls: list[tuple[object, object, object]] = []
    monkeypatch.setattr(
        service_types,
        "_query_heatmap_semantics",
        lambda handle, request, cancellation: calls.append((handle, request, cancellation)) or sentinel,
    )
    queries = report_module._RuntimeQueries(_RuntimeQueryRepository())  # type: ignore[arg-type]
    handle, request, cancellation = object(), object(), object()

    assert queries.query_snapshot_time_range(handle, request, cancellation) is sentinel
    assert calls == [(handle, request, cancellation)]


def test_normalization_freezes_classic_pricing_once_against_later_global_mutation() -> None:
    calls: list[tuple[object, object]] = []
    price = {"value": 0.125, "status": "estimated"}

    class Runtime:
        @staticmethod
        def _cost_for_response(thread: object, response: object) -> object:
            calls.append((thread, response))
            return SimpleNamespace(
                total_cost=price["value"],
                status=price["status"],
                method='API "equivalent"\\estimate',
            )

    first, second = object(), object()
    thread = SimpleNamespace(responses=(first, second))
    authority = report_module._capture_heatmap_pricing(  # type: ignore[arg-type]
        Runtime(), SimpleNamespace(threads=(thread,)), "pricing-v1", "a" * 64
    )
    price.update(value=99.0, status="recorded")

    assert calls == [(thread, first), (thread, second)]
    assert authority.lookup(0, 0) == service_types.HeatmapCostAssessment(
        0.125, "estimated", 'API "equivalent"\\estimate'
    )
    assert authority.lookup(0, 1).value_usd == 0.125  # type: ignore[union-attr]
    assert authority.pricing_version == "pricing-v1"
    assert authority.pricing_digest == "a" * 64


def test_runtime_summary_exposes_every_fr03_metric_group_from_normalized_run() -> None:
    queries = report_module._RuntimeQueries(_RuntimeQueryRepository())  # type: ignore[arg-type]
    snapshot = SimpleNamespace(
        snapshot_id="snap_1234567890abcdef12345678",
        revision_id="revision-1",
        scope=service_types.ReportScope("agent-root", True, False),
        observation_time=datetime(2026, 8, 12, 12, 10, tzinfo=timezone.utc),
        mode="live",
        warnings=(),
    )

    result = queries.get_summary(_runtime_query_handle(), snapshot, None)

    assert tuple(group.group_id for group in result.metric_groups) == (
        "overview", "model", "context", "inference", "runtime", "waits",
        "work_items", "claims", "provenance",
    )
    assert next(group for group in result.metric_groups if group.group_id == "claims").metrics[0].value == 1
    assert all("private" not in metric.formatted_value for group in result.metric_groups for metric in group.metrics)


def test_runtime_summary_uses_observation_bound_for_empty_run_without_wall_times() -> None:
    queries = report_module._RuntimeQueries(_RuntimeQueryRepository())  # type: ignore[arg-type]
    handle = _runtime_query_handle()
    handle.run.wall_started_at = ""
    handle.run.wall_ended_at = ""
    handle.run.threads[0].started_at = ""
    handle.run.threads[0].last_observed_at = ""
    handle.run.threads[1].started_at = ""
    handle.run.threads[1].last_observed_at = ""
    snapshot = SimpleNamespace(
        snapshot_id="snap_1234567890abcdef12345678",
        revision_id="revision-1",
        scope=service_types.ReportScope("agent-root", True, False),
        observation_time=datetime(2026, 8, 12, 12, 10, tzinfo=timezone.utc),
        mode="live",
        warnings=(),
    )

    result = queries.get_summary(handle, snapshot, None)

    assert result.time_range == service_types.TimeRange(
        datetime(2026, 8, 12, 12, 9, 59, 999999, tzinfo=timezone.utc),
        datetime(2026, 8, 12, 12, 10, tzinfo=timezone.utc),
    )


def test_runtime_sequence_uses_normalized_relationship_and_message_evidence() -> None:
    queries = report_module._RuntimeQueries(_RuntimeQueryRepository())  # type: ignore[arg-type]
    request = service_types.SequenceQueryRequest(
        "snap_1234567890abcdef12345678",
        filters=service_types.SequenceFilters(grouping="delegation"),
    )

    result = queries.query_sequence(_runtime_query_handle(), request, None, None)

    assert [(row.kind, row.from_agent_id, row.to_agent_id) for row in result.page.items] == [
        ("spawn", "agent-root", "agent-child"),
        ("message", "agent-root", "agent-child"),
        ("complete", "agent-child", "agent-root"),
    ]
    assert result.groups
    assert all(row.group_id == result.groups[0].group_id for row in result.page.items)


def test_runtime_sequence_collapses_repeated_messages_with_exact_repeat_count() -> None:
    queries = report_module._RuntimeQueries(_RuntimeQueryRepository())  # type: ignore[arg-type]
    handle = _runtime_query_handle()
    duplicate = SimpleNamespace(**vars(handle.run.threads[0].tool_intervals[0]))
    duplicate.started_at = "2026-08-12T12:02:30Z"
    duplicate.source_start_ordinal = 4
    handle.run.threads[0].tool_intervals.append(duplicate)
    request = service_types.SequenceQueryRequest(
        "snap_1234567890abcdef12345678",
        filters=service_types.SequenceFilters(grouping="repeated_messages"),
    )

    result = queries.query_sequence(handle, request, None, None)

    messages = [row for row in result.page.items if row.kind == "message"]
    assert len(messages) == 1
    assert messages[0].repeat_count == 2


def test_runtime_coordination_returns_filtered_claim_and_delegation_evidence() -> None:
    queries = report_module._RuntimeQueries(_RuntimeQueryRepository())  # type: ignore[arg-type]
    request = service_types.CoordinationQueryRequest(
        "snap_1234567890abcdef12345678",
        filters=service_types.CoordinationFilters(work_item_id="work-1", evidence="measured"),
    )

    result = queries.query_coordination(_runtime_query_handle(), request, None, None)

    assert len(result.items) == 1
    assert result.items[0].operation == "claim"
    assert result.items[0].work_item_id == "work-1"
    assert result.items[0].delegated_root_id == "root-task-1"
    assert result.items[0].evidence == "measured"
