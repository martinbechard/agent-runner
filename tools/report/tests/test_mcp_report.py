# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Verify MCP report selection, output, inline, and startup contracts.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
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
                )
                for path in paths
            }
        )

    def _read_codex_catalog_entry(
        self, path: Path, _source_store: str, *, include_title: bool
    ) -> SimpleNamespace:
        assert include_title is True
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
) -> tuple[str, str, datetime, Path]:
    path = root / f"{thread_id}.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    return thread_id, title, datetime.fromisoformat(timestamp), path.resolve()


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
