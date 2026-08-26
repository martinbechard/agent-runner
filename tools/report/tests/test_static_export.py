# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Verify the shared Codex static exporter contract.
# Design: docs/design/components/CD-006-agent-report-static-export.md

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import ast
import hashlib
import inspect
import json
import os
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit
from urllib.request import urlopen

import pytest

from agent_report import static_export as export_module
from agent_report.static_export import (
    DEFAULT_SUMMARY_MAX_BYTES,
    MANIFEST_VERSION,
    STAGING_PREFIX,
    AgentExportRow,
    CodexExportModel,
    EventExportRow,
    ExportManifest,
    ExportMode,
    ExportRequest,
    ExportScope,
    ExportState,
    ExportWarningRecord,
    HeatmapCellExport,
    ManifestFile,
    MetricExport,
    PublicationPlan,
    SequenceEventExport,
    SequenceParticipantExport,
    SnapshotProvenance,
    SnapshotState,
    StaticExportError,
    StaticExporter,
    SummaryExport,
    TurnExportRow,
    WorkUnitExportRow,
)


SHA = "a" * 64


class NeverCancelled:
    def raise_if_cancelled(self) -> None:
        pass


class CancelAt:
    def __init__(self, checkpoint: int) -> None:
        self.checkpoint = checkpoint
        self.calls = 0

    def raise_if_cancelled(self) -> None:
        self.calls += 1
        if self.calls == self.checkpoint:
            raise RuntimeError("cancelled by test")


class RecordingPublication:
    def __init__(
        self,
        parent: Path,
        *,
        adapter_name: str = "cli",
        unsupported_exchange: bool = False,
        fail_publish: bool = False,
    ) -> None:
        self.parent = parent
        self.adapter_name = adapter_name
        self.unsupported_exchange = unsupported_exchange
        self.fail_publish = fail_publish
        self.authorize_calls = 0
        self.publish_calls = 0
        self.discard_calls = 0
        self.cleanup_before: datetime | None = None
        self.plan: PublicationPlan | None = None
        self.inventory: tuple[PurePosixPath, ...] = ()
        self.staged_bytes: dict[str, bytes] = {}

    def authorize(self, request: ExportRequest) -> PublicationPlan:
        self.authorize_calls += 1
        target = request.requested_target.absolute()
        target_kind = "file" if request.mode is ExportMode.SUMMARY else "directory"
        if target.exists() and not request.replace:
            raise _error("REPORT_OUTPUT_EXISTS", request)
        if target_kind == "directory" and target.exists():
            if self.unsupported_exchange:
                raise _error("REPORT_ATOMIC_REPLACE_UNSUPPORTED", request)
            strategy = "atomic-directory-exchange"
        elif target_kind == "directory":
            strategy = "atomic-directory-rename"
        else:
            strategy = "atomic-file-replace"
        staging = self.parent / f"{STAGING_PREFIX}{request.operation_id}"
        staging.mkdir()
        self.plan = PublicationPlan(
            adapter_name=self.adapter_name,  # type: ignore[arg-type]
            authority_token="authority-token",
            requested_target=request.requested_target,
            absolute_target=target,
            staging_directory=staging,
            target_kind=target_kind,  # type: ignore[arg-type]
            commit_strategy=strategy,  # type: ignore[arg-type]
            replace=request.replace,
        )
        return self.plan

    def publish(
        self,
        plan: PublicationPlan,
        staged_entry: Path,
        expected_relative_paths: tuple[PurePosixPath, ...],
    ) -> Path:
        self.publish_calls += 1
        self.inventory = expected_relative_paths
        if staged_entry.is_dir():
            self.staged_bytes = {
                path.relative_to(staged_entry).as_posix(): path.read_bytes()
                for path in staged_entry.rglob("*")
                if path.is_file()
            }
        else:
            self.staged_bytes = {plan.absolute_target.name: staged_entry.read_bytes()}
        if self.fail_publish:
            raise RuntimeError("simulated commit failure")
        if plan.absolute_target.exists() and plan.absolute_target.is_dir():
            old = plan.absolute_target.with_name(plan.absolute_target.name + ".old")
            os.replace(plan.absolute_target, old)
            os.replace(staged_entry, plan.absolute_target)
            for path in sorted(old.rglob("*"), reverse=True):
                path.rmdir() if path.is_dir() else path.unlink()
            old.rmdir()
        else:
            os.replace(staged_entry, plan.absolute_target)
        return plan.absolute_target

    def discard(self, plan: PublicationPlan) -> None:
        self.discard_calls += 1
        if plan.staging_directory.exists():
            for path in sorted(plan.staging_directory.rglob("*"), reverse=True):
                path.rmdir() if path.is_dir() else path.unlink()
            plan.staging_directory.rmdir()

    def cleanup_stale(self, *, older_than: datetime) -> tuple[Path, ...]:
        self.cleanup_before = older_than
        return (self.parent / f"{STAGING_PREFIX}old",)


class RecordingArchiveWriter:
    def __init__(self) -> None:
        self.provenance: SnapshotProvenance | None = None

    def write_archive(
        self,
        destination: Path,
        provenance: SnapshotProvenance,
        cancellation: NeverCancelled,
    ) -> None:
        cancellation.raise_if_cancelled()
        self.provenance = provenance
        destination.write_bytes(b"SQLite format 3\x00privacy-bounded-test")


def _error(code: str, request: ExportRequest) -> StaticExportError:
    return StaticExportError.from_code(
        code,
        "test adapter rejection",
        operation_id=request.operation_id,
        target=str(request.requested_target),
    )


def make_model(
    *,
    state: SnapshotState = SnapshotState.SEALED,
    activity_count: int = 2,
    agent_count: int = 2,
    turn_count: int = 2,
    event_count: int = 2,
    title: str = "Privacy-safe task <title>",
) -> CodexExportModel:
    provenance = SnapshotProvenance(
        snapshot_id="snapshot-1",
        revision="revision-1",
        root_thread_id="thread-root",
        scope=ExportScope(include_children=True, include_collaborators=False),
        observed_at=datetime(2026, 8, 12, 15, 0, 4, tzinfo=UTC),
        state=state,
        source_digest=SHA,
        parser_version="parser-1",
        pricing_version="pricing-1",
        pricing_digest=SHA,
        formatter_version="formatter-1",
        formatter_digest=SHA,
    )
    metrics = (
        MetricExport("turns", "Turns", str(turn_count), turn_count, "turns", "measured"),
        MetricExport("cost", "Estimated cost", "$0.25", 0.25, "USD", "estimated"),
    )
    summary = SummaryExport(
        title=title,
        goal="Keep ciphertext opaque: ENC[opaque]",
        run_state="completed",
        metrics=metrics,
        recent_activity=tuple(f"activity-{index}: inferred" for index in range(activity_count)),
        warnings=(
            ExportWarningRecord("REPORT_SOURCE_WARNING", "sanitized warning"),
            ExportWarningRecord("REPORT_SOURCE_WARNING", "sanitized warning"),
        ),
    )
    agents = tuple(
        AgentExportRow(
            thread_id=f"thread-{index}",
            parent_thread_id="thread-root" if index else None,
            task_title=f"agent task {index}",
            agent_role="worker",
            model="gpt-test",
            effort="medium",
            started_at="2026-08-12T15:00:00Z",
            last_observed_at="2026-08-12T15:00:04Z",
            terminal_state="completed",
            turn_count=1,
            tool_count=2,
            mcp_call_count=1,
            wall_time_ms=1000,
            agent_time_ms=800,
            input_tokens=100,
            cached_input_tokens=50,
            output_tokens=25,
            reasoning_tokens=10,
            estimated_cost_usd=0.25,
            cost_evidence="estimated",
        )
        for index in range(agent_count)
    )
    turns = tuple(
        TurnExportRow(
            thread_id="thread-root",
            turn_id=f"turn-{index:04d}",
            started_at="2026-08-12T15:00:00Z",
            completed_at="2026-08-12T15:00:01Z",
            duration_ms=1000,
            time_to_first_token_ms=100,
            outcome="completed",
            abort_reason="",
            abort_event_timestamp="",
            abort_initiator_thread_id="",
            abort_initiator_agent_path="",
            abort_initiator_turn_id="",
            abort_initiator_relationship="",
            abort_request_source_path="",
            abort_request_source_ordinal=0,
            phase_id="phase-1",
            lane_id="lane-1",
            work_unit_id="work-1",
            activity="coding",
            attribution_confidence="measured",
            input_tokens=100,
            cached_input_tokens=50,
            uncached_input_tokens=50,
            output_tokens=25,
            reasoning_tokens=10,
            processed_tokens=135,
            source_path="sanitized-source",
            source_ordinal=index,
        )
        for index in range(turn_count)
    )
    work_units = (
        WorkUnitExportRow(
            work_unit_id="work-1",
            phase_id="phase-1",
            lane_id="lane-1",
            activity="coding",
            turn_ids=tuple(row.turn_id for row in turns),
            allocation_method="direct",
            attribution_confidence="derived",
            input_tokens=200,
            cached_input_tokens=100,
            uncached_input_tokens=100,
            output_tokens=50,
            reasoning_tokens=20,
            processed_tokens=270,
            cost_status="estimated",
            estimated_usd=0.25,
        ),
    )
    events = tuple(
        EventExportRow(
            event_id=f"event-{index:04d}",
            thread_id="thread-root",
            turn_id=turns[index % len(turns)].turn_id if turns else None,
            timestamp="2026-08-12T15:00:01Z",
            kind="tool",
            label=f"event {index}",
            summary="bounded event detail",
            evidence="measured",
            source_ordinal=index,
        )
        for index in range(event_count)
    )
    return CodexExportModel(
        provenance=provenance,
        summary=summary,
        agents=agents,
        turns=turns,
        work_units=work_units,
        events=events,
        heatmap_cells=(
            HeatmapCellExport(
                "thread-root",
                "2026-08-12T15:00:00Z",
                "2026-08-12T15:05:00Z",
                "active_ms",
                1000,
                "1.0 s",
                "derived",
            ),
        ),
        sequence_participants=(
            SequenceParticipantExport("thread-root", None, "Root", "orchestrator"),
        ),
        sequence_events=(
            SequenceEventExport(
                1,
                "event-0000",
                "2026-08-12T15:00:01Z",
                "message",
                "thread-root",
                None,
                "Started",
                "sanitized detail",
                "measured",
            ),
        ),
    )


def make_request(target: Path, mode: ExportMode = ExportMode.DIRECTORY, **changes: object) -> ExportRequest:
    values = {
        "operation_id": "operation-1",
        "snapshot_id": "snapshot-1",
        "revision": "revision-1",
        "mode": mode,
        "requested_target": target,
        "replace": False,
    }
    values.update(changes)
    return ExportRequest(**values)  # type: ignore[arg-type]


def export_to(tmp_path: Path, *, model: CodexExportModel | None = None, mode: ExportMode = ExportMode.DIRECTORY, **request_changes: object):
    target = tmp_path / ("summary.html" if mode is ExportMode.SUMMARY else "report")
    request = make_request(target, mode, **request_changes)
    publication = RecordingPublication(tmp_path)
    result = StaticExporter().export(model or make_model(), request, publication, NeverCancelled())
    return target, result, publication


def test_export_summary_is_self_contained_and_at_most_two_mibibytes(tmp_path: Path) -> None:
    target, result, _ = export_to(tmp_path, mode=ExportMode.SUMMARY)
    payload = target.read_bytes()
    text = payload.decode("utf-8")
    assert len(payload) <= DEFAULT_SUMMARY_MAX_BYTES
    assert "<style>" in text and "<script>" in text
    assert "snapshot-1" in text and "sealed" in text and "Estimated cost" in text
    assert text.count(SHA) >= 3
    assert not re.search(r"(?:https?:)?//|\bfetch\s*\(|XMLHttpRequest|serviceWorker", text, re.I)
    assert result.manifest_sha256 is None


def test_export_summary_result_reports_one_file_and_exact_total_byte_count(tmp_path: Path) -> None:
    target, result, _ = export_to(tmp_path, mode=ExportMode.SUMMARY)

    assert result.file_count == 1
    assert result.total_byte_count == len(target.read_bytes())


def test_export_summary_omits_sections_in_stable_priority_and_lists_each_omission(tmp_path: Path) -> None:
    model = make_model(activity_count=5_000, agent_count=1_000)
    target, result, _ = export_to(
        tmp_path,
        model=model,
        mode=ExportMode.SUMMARY,
        summary_max_bytes=65_536,
    )
    text = target.read_text(encoding="utf-8")
    assert len(target.read_bytes()) <= 65_536
    assert result.omissions
    assert tuple(item.section for item in result.omissions) == tuple(
        name for name in export_module.SUMMARY_OMISSION_PRIORITY if name in {item.section for item in result.omissions}
    )
    for omission in result.omissions:
        assert omission.section in text and omission.recovery in text


def test_export_summary_fails_when_required_shell_cannot_fit(tmp_path: Path) -> None:
    model = make_model(title="x" * 80_000, activity_count=0, agent_count=0)
    publication = RecordingPublication(tmp_path)
    with pytest.raises(StaticExportError) as caught:
        StaticExporter().export(
            model,
            make_request(tmp_path / "summary.html", ExportMode.SUMMARY, summary_max_bytes=65_536),
            publication,
            NeverCancelled(),
        )
    assert caught.value.error.code == "REPORT_SUMMARY_CAP_TOO_SMALL"
    assert publication.publish_calls == 0 and publication.discard_calls == 1


def test_export_directory_matches_manifest_version_one_file_contract(tmp_path: Path) -> None:
    target, _, _ = export_to(tmp_path)
    files = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
    assert files == {
        "index.html", "manifest.json", "report.json", "report.md", "turns.csv",
        "work-units.csv", "assets/report.css", "assets/report.js",
        "pages/agents/page-0001.html", "pages/turns/page-0001.html",
        "pages/events/page-0001.html", "pages/heatmap/overview.html",
        "sequence/index.html",
    }


def test_export_directory_creates_consecutive_bounded_collection_pages(tmp_path: Path) -> None:
    model = make_model(agent_count=0, turn_count=3, event_count=0)
    target, _, _ = export_to(tmp_path, model=model, page_size=2)
    assert sorted(path.name for path in (target / "pages/turns").iterdir()) == ["page-0001.html", "page-0002.html"]
    assert "No agents" in (target / "pages/agents/page-0001.html").read_text()
    assert "No events" in (target / "pages/events/page-0001.html").read_text()
    with pytest.raises(StaticExportError) as caught:
        export_module._page_count(10_000, 1, "operation-1")
    assert caught.value.error.code == "REPORT_EXPORT_TOO_MANY_PAGES"


def test_export_directory_manifest_is_canonical_and_every_payload_digest_matches(tmp_path: Path) -> None:
    target, result, _ = export_to(tmp_path)
    raw = (target / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert raw == (json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode()
    assert [item["path"] for item in manifest["files"]] == sorted(item["path"] for item in manifest["files"])
    for item in manifest["files"]:
        payload = (target / item["path"]).read_bytes()
        assert item["byte_count"] == len(payload)
        assert item["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result.manifest_sha256 == hashlib.sha256(raw).hexdigest()


def test_export_directory_result_reports_exact_file_and_total_byte_counts(tmp_path: Path) -> None:
    target, result, _ = export_to(tmp_path)
    published_files = tuple(path for path in target.rglob("*") if path.is_file())

    assert result.file_count == len(published_files)
    assert result.total_byte_count == sum(len(path.read_bytes()) for path in published_files)


def test_export_warnings_and_errors_are_structured_records(tmp_path: Path) -> None:
    target, result, _ = export_to(tmp_path)
    warning = ExportWarningRecord("REPORT_SOURCE_WARNING", "sanitized warning")

    assert result.warnings == (warning,)
    assert result.omissions == ()
    assert json.loads((target / "manifest.json").read_text())["warnings"] == [
        {"code": warning.code, "message": warning.message}
    ]

    error = StaticExportError.from_code(
        "REPORT_TOO_LARGE_FOR_MCP",
        "The complete export exceeds the MCP response limit.",
        operation_id="operation-1",
        actual_bytes=20,
        maximum_bytes=10,
        written_files=("summary.html",),
        warnings=(warning,),
    ).error
    assert error.code == "REPORT_TOO_LARGE_FOR_MCP"
    assert error.actual_bytes == 20 and error.maximum_bytes == 10
    assert error.written_files == ("summary.html",)
    assert error.warnings == (warning,)

    model = make_model()
    invalid_model = replace(
        model,
        summary=replace(model.summary, warnings=("unstructured",)),  # type: ignore[arg-type]
    )
    publication = RecordingPublication(tmp_path)
    with pytest.raises(StaticExportError) as caught:
        StaticExporter().export(
            invalid_model,
            make_request(tmp_path / "invalid-report"),
            publication,
            NeverCancelled(),
        )
    assert caught.value.error.code == "REPORT_INVALID_REQUEST"
    assert publication.authorize_calls == 0


def test_export_directory_opens_from_file_url_with_network_disabled(tmp_path: Path) -> None:
    target, _, _ = export_to(tmp_path)
    index = urlopen((target / "index.html").as_uri()).read().decode()  # noqa: S310 - file URI only
    assert "Privacy-safe task" in index
    assert "© 2026 Martin.Bechard@DevConsult.ca · MIT License" in index
    for relative in ("pages/agents/page-0001.html", "pages/heatmap/overview.html", "sequence/index.html"):
        assert "<h1" in urlopen((target / relative).as_uri()).read().decode()  # noqa: S310 - file URI only


def test_export_directory_startup_uses_no_fetch_xhr_module_service_worker_or_sqlite_wasm(tmp_path: Path) -> None:
    target, _, _ = export_to(tmp_path)
    startup = "\n".join(path.read_text() for path in target.rglob("*") if path.suffix in {".html", ".js"})
    assert not re.search(r"\bfetch\s*\(|XMLHttpRequest|type=[\"']module|serviceWorker|sqlite.{0,8}wasm|https?://", startup, re.I)


def test_export_directory_includes_current_json_csv_and_markdown_representations(tmp_path: Path) -> None:
    target, _, _ = export_to(tmp_path)
    report = json.loads((target / "report.json").read_text())
    assert report["provenance"]["snapshot_id"] == "snapshot-1"
    assert report["turns"][0]["processed_tokens"] == 135
    assert (target / "turns.csv").read_text().splitlines()[0].split(",")[-2:] == ["source_path", "source_ordinal"]
    assert "turn_ids" in (target / "work-units.csv").read_text().splitlines()[0]
    markdown = (target / "report.md").read_text()
    assert "# Privacy-safe task <title>" in markdown and "Evidence: `estimated`" in markdown


def test_export_directory_optional_sqlite_uses_archive_writer_for_exact_snapshot(tmp_path: Path) -> None:
    writer = RecordingArchiveWriter()
    target = tmp_path / "report"
    publication = RecordingPublication(tmp_path)
    result = StaticExporter(writer).export(
        make_model(), make_request(target, include_sqlite=True), publication, NeverCancelled()
    )
    assert writer.provenance == make_model().provenance
    assert (target / "report.sqlite").read_bytes().startswith(b"SQLite format 3")
    assert (target / "report.sqlite").is_file()
    assert result.file_count == sum(1 for path in target.rglob("*") if path.is_file())


@pytest.mark.parametrize(
    ("field", "value", "requested_field", "supplied_field"),
    [("snapshot_id", "other", "requested_snapshot_id", "supplied_snapshot_id"),
     ("revision", "other", "requested_revision", "supplied_revision")],
)
def test_snapshot_binding_mismatch(field: str, value: str, requested_field: str, supplied_field: str, tmp_path: Path) -> None:
    publication = RecordingPublication(tmp_path)
    request = make_request(tmp_path / "report", **{field: value})
    with pytest.raises(StaticExportError) as caught:
        StaticExporter().export(make_model(), request, publication, NeverCancelled())
    assert caught.value.error.code == "REPORT_SNAPSHOT_CONFLICT"
    assert getattr(caught.value.error, requested_field) == value
    assert getattr(caught.value.error, supplied_field) == getattr(make_model().provenance, field)
    assert publication.authorize_calls == 0


def test_export_rejects_snapshot_id_mismatch_before_authorization(tmp_path: Path) -> None:
    test_snapshot_binding_mismatch("snapshot_id", "other", "requested_snapshot_id", "supplied_snapshot_id", tmp_path)


def test_export_rejects_revision_mismatch_before_authorization(tmp_path: Path) -> None:
    test_snapshot_binding_mismatch("revision", "other", "requested_revision", "supplied_revision", tmp_path)


def test_cli_automation_and_mcp_generation_default_to_directory(tmp_path: Path) -> None:
    for surface in ("cli", "mcp", "tauri"):
        target = tmp_path / surface
        request = make_request(target)
        publication = RecordingPublication(tmp_path, adapter_name=surface)
        result = StaticExporter().export(make_model(), request, publication, NeverCancelled())
        assert result.mode is ExportMode.DIRECTORY and target.is_dir()


def test_summary_requires_explicit_mode() -> None:
    assert inspect.signature(ExportRequest).parameters["mode"].default is inspect.Parameter.empty
    assert ExportMode.SUMMARY.value == "summary"


def test_mcp_query_operations_never_invoke_static_export() -> None:
    assert not hasattr(StaticExporter, "query_time_range")
    assert not hasattr(StaticExporter, "get_event_details")


@pytest.mark.parametrize("mode", ["legacy", "html", "full", "LEGACY", ""])
def test_export_rejects_legacy_html_and_full_mode_aliases(mode: str, tmp_path: Path) -> None:
    publication = RecordingPublication(tmp_path)
    request = replace(make_request(tmp_path / "report"), mode=mode)  # type: ignore[arg-type]
    with pytest.raises(StaticExportError) as caught:
        StaticExporter().export(make_model(), request, publication, NeverCancelled())
    assert caught.value.error.code == "REPORT_INVALID_REQUEST"
    assert publication.authorize_calls == 0


def test_codex_export_path_does_not_call_retired_run_timeline_renderers() -> None:
    source = inspect.getsource(export_module)
    for retired in ("render_codex_rollout_html", "_split_codex_sequence_document", "_write_codex_outputs"):
        assert retired not in source


def test_private_renderers_accept_only_exact_exporter_owned_types() -> None:
    assert inspect.signature(export_module._render_summary).parameters["model"].annotation == "CodexExportModel"
    assert inspect.signature(export_module._render_turns_csv).parameters["rows"].annotation == "tuple[TurnExportRow, ...]"
    assert "Any" not in export_module.__dict__ and "Mapping" not in export_module.__dict__ and "Sequence" not in export_module.__dict__


def test_export_progress_uses_exact_export_progress_mapping(tmp_path: Path) -> None:
    progress = []
    publication = RecordingPublication(tmp_path)
    StaticExporter().export(
        make_model(), make_request(tmp_path / "report"), publication, NeverCancelled(), progress.append
    )
    assert [(item.state, item.completed) for item in progress] == [
        (ExportState.VALIDATING, 0), (ExportState.STAGING, 5),
        (ExportState.RENDERING, 10), (ExportState.RENDERING, 15),
        (ExportState.RENDERING, 35), (ExportState.RENDERING, 55),
        (ExportState.RENDERING, 80), (ExportState.VERIFYING, 90),
        (ExportState.PUBLISHING, 95), (ExportState.PUBLISHED, 100),
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {"operation_id": ""}, {"page_size": 0}, {"page_size": 501},
        {"summary_max_bytes": 65_535}, {"summary_max_bytes": 2_097_153},
        {"include_sqlite": True, "mode": ExportMode.SUMMARY},
    ],
)
def test_export_rejects_invalid_mode_option_combinations_before_staging(changes: dict[str, object], tmp_path: Path) -> None:
    publication = RecordingPublication(tmp_path)
    request = make_request(tmp_path / "report")
    request = replace(request, **changes)
    with pytest.raises(StaticExportError) as caught:
        StaticExporter().export(make_model(), request, publication, NeverCancelled())
    assert caught.value.error.code == "REPORT_INVALID_REQUEST"
    assert publication.authorize_calls == 0


def test_tauri_cli_and_mcp_publication_adapters_receive_identical_staged_bytes(tmp_path: Path) -> None:
    captures = []
    for surface in ("tauri", "cli", "mcp"):
        parent = tmp_path / surface
        parent.mkdir()
        publication = RecordingPublication(parent, adapter_name=surface)
        StaticExporter().export(make_model(), make_request(parent / "report"), publication, NeverCancelled())
        captures.append(publication.staged_bytes)
    assert captures[0] == captures[1] == captures[2]


def test_publication_adapter_rejects_unauthorized_changed_or_unconfirmed_target(tmp_path: Path) -> None:
    target = tmp_path / "report"
    target.mkdir()
    publication = RecordingPublication(tmp_path)
    with pytest.raises(StaticExportError) as caught:
        StaticExporter().export(make_model(), make_request(target), publication, NeverCancelled())
    assert caught.value.error.code == "REPORT_OUTPUT_EXISTS"
    assert publication.publish_calls == 0


def test_cancel_at_each_render_checkpoint_discards_staging_and_preserves_target(tmp_path: Path) -> None:
    for checkpoint in range(1, 7):
        parent = tmp_path / str(checkpoint)
        parent.mkdir()
        target = parent / "summary.html"
        target.write_text("old")
        publication = RecordingPublication(parent)
        with pytest.raises(StaticExportError) as caught:
            StaticExporter().export(
                make_model(), make_request(target, ExportMode.SUMMARY, replace=True), publication, CancelAt(checkpoint)
            )
        assert caught.value.error.code == "REPORT_EXPORT_CANCELLED"
        assert target.read_text() == "old"
        assert publication.discard_calls == (1 if publication.plan is not None else 0)


def test_summary_publication_uses_one_atomic_same_parent_file_replace(tmp_path: Path) -> None:
    target = tmp_path / "summary.html"
    target.write_text("old")
    publication = RecordingPublication(tmp_path)
    StaticExporter().export(
        make_model(), make_request(target, ExportMode.SUMMARY, replace=True), publication, NeverCancelled()
    )
    assert publication.plan is not None
    assert publication.plan.commit_strategy == "atomic-file-replace"
    assert publication.plan.staging_directory.parent == target.parent
    assert publication.publish_calls == 1


def test_new_directory_publication_uses_one_atomic_same_parent_rename(tmp_path: Path) -> None:
    _, _, publication = export_to(tmp_path)
    assert publication.plan is not None
    assert publication.plan.commit_strategy == "atomic-directory-rename"
    assert publication.publish_calls == 1


def test_existing_directory_replacement_uses_one_atomic_exchange(tmp_path: Path) -> None:
    target = tmp_path / "report"
    target.mkdir()
    (target / "old").write_text("complete old")
    publication = RecordingPublication(tmp_path)
    StaticExporter().export(make_model(), make_request(target, replace=True), publication, NeverCancelled())
    assert publication.plan is not None
    assert publication.plan.commit_strategy == "atomic-directory-exchange"
    assert publication.publish_calls == 1 and (target / "manifest.json").exists()


def test_existing_directory_replacement_fails_when_atomic_exchange_is_unavailable(tmp_path: Path) -> None:
    target = tmp_path / "report"
    target.mkdir()
    (target / "old").write_text("complete old")
    publication = RecordingPublication(tmp_path, unsupported_exchange=True)
    with pytest.raises(StaticExportError) as caught:
        StaticExporter().export(make_model(), make_request(target, replace=True), publication, NeverCancelled())
    assert caught.value.error.code == "REPORT_ATOMIC_REPLACE_UNSUPPORTED"
    assert (target / "old").read_text() == "complete old"
    assert publication.publish_calls == 0


def test_atomic_publication_failure_preserves_prior_visible_target_state(tmp_path: Path) -> None:
    target = tmp_path / "summary.html"
    target.write_text("complete old")
    publication = RecordingPublication(tmp_path, fail_publish=True)
    with pytest.raises(StaticExportError) as caught:
        StaticExporter().export(
            make_model(), make_request(target, ExportMode.SUMMARY, replace=True), publication, NeverCancelled()
        )
    assert caught.value.error.code == "REPORT_EXPORT_PUBLICATION_FAILED"
    assert target.read_text() == "complete old"


def test_cancellation_is_deferred_after_publication_critical_section_starts(tmp_path: Path) -> None:
    target = tmp_path / "summary.html"
    publication = RecordingPublication(tmp_path)
    cancellation = CancelAt(7)
    result = StaticExporter().export(
        make_model(), make_request(target, ExportMode.SUMMARY), publication, cancellation
    )
    assert result.published_target == target.absolute()
    assert cancellation.calls == 6


def test_cleanup_stale_staging_removes_only_owned_prefix_after_fixed_age(tmp_path: Path) -> None:
    publication = RecordingPublication(tmp_path)
    now = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)
    removed = StaticExporter().cleanup_stale_staging(publication, now=now)
    assert publication.cleanup_before == now - timedelta(seconds=86_400)
    assert removed == (tmp_path / f"{STAGING_PREFIX}old",)


def test_export_rejects_absolute_parent_or_symlink_escape_in_manifest_paths(tmp_path: Path) -> None:
    root = tmp_path / "stage"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("outside")
    (root / "link").symlink_to(outside)
    manifest = ExportManifest(
        1, "snapshot-1", "revision-1", "thread-root", True, False,
        "2026-08-12T15:00:04Z", "sealed", SHA, "parser-1", "pricing-1", SHA,
        "formatter-1", SHA,
        (ManifestFile(PurePosixPath("link"), "data-json", len(outside.read_bytes()), hashlib.sha256(outside.read_bytes()).hexdigest()),),
        (), (),
    )
    with pytest.raises(StaticExportError) as caught:
        export_module._verify_staged_directory(root, manifest)
    assert caught.value.error.code == "REPORT_EXPORT_INTEGRITY_FAILED"
    for unsafe in (PurePosixPath("/absolute"), PurePosixPath("../outside")):
        unsafe_manifest = replace(manifest, files=(replace(manifest.files[0], path=unsafe),))
        with pytest.raises(StaticExportError) as unsafe_error:
            export_module._verify_staged_directory(root, unsafe_manifest)
        assert unsafe_error.value.error.code == "REPORT_EXPORT_INTEGRITY_FAILED"


def test_export_rejects_missing_extra_or_digest_mismatched_staged_file(tmp_path: Path) -> None:
    root = tmp_path / "stage"
    root.mkdir()
    (root / "payload").write_bytes(b"actual")
    manifest = ExportManifest(
        1, "snapshot-1", "revision-1", "thread-root", True, False,
        "2026-08-12T15:00:04Z", "sealed", SHA, "parser-1", "pricing-1", SHA,
        "formatter-1", SHA,
        (ManifestFile(PurePosixPath("payload"), "data-json", 6, "0" * 64),), (), (),
    )
    with pytest.raises(StaticExportError) as caught:
        export_module._verify_staged_directory(root, manifest)
    assert caught.value.error.code == "REPORT_EXPORT_INTEGRITY_FAILED"


def test_export_preserves_privacy_ciphertext_epistemic_labels_and_sealed_provenance(tmp_path: Path) -> None:
    target, _, _ = export_to(tmp_path)
    report = (target / "report.json").read_text()
    assert "ENC[opaque]" in report
    assert '"evidence": "estimated"' in report
    assert '"state": "sealed"' in report
    assert str(tmp_path) not in report


def test_live_export_records_observation_and_warning_without_claiming_sealed_state(tmp_path: Path) -> None:
    target, result, _ = export_to(tmp_path, model=make_model(state=SnapshotState.LIVE))
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["snapshot_state"] == "live"
    assert manifest["observed_at"] == "2026-08-12T15:00:04Z"
    assert result.warnings == (
        ExportWarningRecord("REPORT_SOURCE_WARNING", "sanitized warning"),
    )
    index = (target / "index.html").read_text()
    assert "sanitized warning" in index and "state live" in index


def test_static_export_has_no_dependency_on_tauri_fastmcp_rust_discovery_or_live_cache_path() -> None:
    source = inspect.getsource(export_module).casefold()
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "fastmcp" not in imported_roots
    for forbidden in ("agent-report-core", "report-events-v1.sqlite3", "run-timeline"):
        assert forbidden not in source
