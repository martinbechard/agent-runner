# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Verify renderer resource resolution for installed and frozen agent-report commands.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent_report import cli


def test_report_script_path_uses_pyinstaller_bundle(
    monkeypatch, tmp_path: Path
) -> None:
    """Resolve report data from PyInstaller's extraction directory when frozen."""
    monkeypatch.setattr(cli.sys, "_MEIPASS", str(tmp_path), raising=False)

    assert cli._report_script_path() == (
        tmp_path / "share" / "agent-report" / "run-timeline.py"
    )


def test_report_script_path_uses_wheel_data_outside_frozen_runtime(
    monkeypatch, tmp_path: Path
) -> None:
    """Keep installed-wheel data resolution unchanged outside a frozen executable."""
    monkeypatch.delattr(cli.sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(cli.sysconfig, "get_path", lambda _name: str(tmp_path))

    assert cli._report_script_path() == (
        tmp_path / "share" / "agent-report" / "run-timeline.py"
    )


def test_native_engine_path_uses_pyinstaller_bundle(
    monkeypatch, tmp_path: Path
) -> None:
    """Resolve the required native engine from the frozen sidecar payload."""
    monkeypatch.setattr(cli.sys, "_MEIPASS", str(tmp_path), raising=False)

    executable_name = (
        "agent-report-engine.exe"
        if cli.sys.platform == "win32"
        else "agent-report-engine"
    )
    assert cli._native_engine_path() == (
        tmp_path / "agent_report" / "native" / executable_name
    )


def test_frozen_sidecar_always_uses_its_bundled_engine(
    monkeypatch, tmp_path: Path
) -> None:
    """Prevent an inherited development override from breaking the app bundle."""
    monkeypatch.setattr(cli.sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setenv("AGENT_REPORT_ENGINE", "/tmp/stale-development-engine")

    cli._configure_bundled_engine()

    assert cli.os.environ["AGENT_REPORT_ENGINE"] == str(cli._native_engine_path())


def test_non_codex_backend_keeps_the_existing_runtime_entrypoint(
    monkeypatch, tmp_path: Path
) -> None:
    """Leave non-Codex report adapters on the established compatibility runtime."""

    calls: list[list[str]] = []
    runtime = SimpleNamespace(
        main=lambda arguments: calls.append(arguments) or 7,
        _is_native_codex_rollout=lambda _path: False,
    )
    monkeypatch.setattr(cli, "_configure_bundled_engine", lambda: None)
    monkeypatch.setattr(cli, "_load_report_module", lambda: runtime)

    result = cli.main([str(tmp_path), "--output", str(tmp_path / "report.html")])

    assert result == 7
    assert calls == [[str(tmp_path), "--output", str(tmp_path / "report.html")]]


def test_worker_subcommand_composes_the_injected_application_service(
    monkeypatch,
) -> None:
    """Launch the packaged JSONL worker with its production service factory seam."""

    from agent_report import report_worker

    captured: dict[str, object] = {}
    runtime = SimpleNamespace()

    class Worker:
        def run(self) -> int:
            return 9

    def create(config, **kwargs):  # type: ignore[no-untyped-def]
        captured["config"] = config
        captured.update(kwargs)
        return Worker()

    monkeypatch.setattr(cli, "_configure_bundled_engine", lambda: None)
    monkeypatch.setattr(cli, "_load_report_module", lambda: runtime)
    monkeypatch.setattr(report_worker, "create_worker_runtime", create)

    result = cli.main(["worker", "--max-in-flight", "6", "--protocol-version", "1"])

    assert result == 9
    config = captured["config"]
    assert isinstance(config, report_worker.WorkerConfig)
    assert config.max_in_flight == 6
    assert config.protocol_version == 1
    assert callable(captured["service_factory"])


def test_codex_automation_requires_explicit_streamlined_mode(
    tmp_path: Path,
) -> None:
    """Keep the existing no-mode Codex command on the classic renderer."""

    runtime = SimpleNamespace(_is_native_codex_rollout=lambda _path: False)

    selection = cli._parse_codex_automation(
        [
            "--codex-thread",
            "thread-1",
            "--sessions-root",
            str(tmp_path),
            "--include-children",
            "--include-delegations",
        ],
        runtime,
    )

    assert selection is None

    selection = cli._parse_codex_automation(
        [
            "--codex-thread",
            "thread-1",
            "--sessions-root",
            str(tmp_path),
            "--report-mode",
            "directory",
            "--include-children",
            "--include-delegations",
        ],
        runtime,
    )

    assert selection is not None
    assert selection.report_mode == "directory"
    assert selection.output.name == "thread-1"
    assert selection.include_children is True
    assert selection.include_collaborators is True


def test_codex_command_without_report_mode_keeps_classic_runtime(
    monkeypatch, tmp_path: Path
) -> None:
    """Delegate an omitted-mode Codex command to the classic renderer unchanged."""

    arguments = [
        "--codex-thread",
        "thread-1",
        "--sessions-root",
        str(tmp_path),
        "--output",
        str(tmp_path / "report.html"),
    ]
    calls: list[list[str]] = []
    runtime = SimpleNamespace(main=lambda received: calls.append(received) or 0)
    monkeypatch.setattr(cli, "_configure_bundled_engine", lambda: None)
    monkeypatch.setattr(cli, "_load_report_module", lambda: runtime)

    assert cli.main(arguments) == 0
    assert calls == [arguments]
