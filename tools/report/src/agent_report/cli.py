# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Launch the bundled agent execution report implementation.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

"""Console entry point for the agent-report wheel."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
import sysconfig
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Literal, cast


def _frozen_root() -> Path | None:
    """Return PyInstaller's extraction root when running as a frozen sidecar."""

    value = getattr(sys, "_MEIPASS", None)
    return Path(value) if value is not None else None


def _native_engine_path() -> Path:
    """Resolve the required native discovery engine for this distribution."""

    executable_name = (
        "agent-report-engine.exe" if sys.platform == "win32" else "agent-report-engine"
    )
    frozen_root = _frozen_root()
    if frozen_root is not None:
        return frozen_root / "agent_report" / "native" / executable_name
    return Path(__file__).resolve().parent / "native" / executable_name


def _configure_bundled_engine() -> None:
    """Point the reporter at the platform engine carried by the installed wheel."""

    engine_path = str(_native_engine_path())
    if _frozen_root() is not None:
        os.environ["AGENT_REPORT_ENGINE"] = engine_path
    else:
        os.environ.setdefault("AGENT_REPORT_ENGINE", engine_path)


def _report_script_path() -> Path:
    """Resolve report data from either a frozen sidecar or an installed wheel."""

    frozen_root = _frozen_root()
    data_root = (
        frozen_root if frozen_root is not None else Path(sysconfig.get_path("data"))
    )
    return data_root / "share" / "agent-report" / "run-timeline.py"


@cache
def _load_report_module() -> ModuleType:
    """Load the bundled report implementation once for the installed command."""
    script_path = _report_script_path()
    spec = importlib.util.spec_from_file_location("_agent_report_runtime", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load bundled report implementation: {script_path}"
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    """Run the bundled report CLI.

    Args:
        argv: Command arguments without the executable name, or ``None`` to
            read them from the current process.

    Returns:
        Zero when the report is written successfully, or one for a handled
        input, discovery, parsing, or sealing failure. Argument-contract
        violations are reported by ``argparse`` through ``SystemExit``.

    Raises:
        RuntimeError: The installed wheel does not contain its report script.
    """
    _configure_bundled_engine()
    arguments = list(sys.argv[1:] if argv is None else argv)
    runtime = _load_report_module()
    if arguments and arguments[0] == "--agent-report-worker":
        from importlib.metadata import version

        from . import report_worker
        from .mcp_report import create_production_application_service

        worker_arguments = arguments[1:]
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--max-in-flight", type=int, default=4)
        parser.add_argument(
            "--protocol-version", type=int, default=report_worker.PROTOCOL_VERSION
        )
        parsed, _unknown = parser.parse_known_args(worker_arguments)
        config = report_worker.WorkerConfig(
            parsed.protocol_version,
            version("agent-report"),
            parsed.max_in_flight,
            report_worker.MAX_RECORD_BYTES,
        )

        def service_factory(service_config):
            return create_production_application_service(runtime, service_config)

        worker = report_worker.create_worker_runtime(
            config,
            stdin=sys.stdin.buffer,
            stdout=sys.stdout.buffer,
            stderr=sys.stderr,
            service_factory=service_factory,
        )
        return worker.run()

    selection = _parse_codex_automation(arguments, runtime)
    if selection is None:
        return runtime.main(arguments)
    return _run_codex_automation(runtime, selection)


@dataclass(frozen=True, slots=True)
class _CodexAutomation:
    thread_id: str
    roots: tuple[Path, ...]
    output: Path
    report_mode: str | None
    include_children: bool
    include_collaborators: bool
    seal: bool
    seal_aborted: bool
    title: str
    thread_titles: tuple[str, ...]
    formatter_config: str | None
    workers: int
    companion_outputs: tuple[tuple[str, Path], ...]


def _parse_codex_automation(
    arguments: list[str], runtime: ModuleType
) -> _CodexAutomation | None:
    """Recognize a single Codex report while leaving compatibility backends intact."""

    if (
        "--report-mode" not in arguments
        or "--codex-catalog" in arguments
        or "--junie-catalog" in arguments
    ):
        return None
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("path", nargs="?")
    parser.add_argument("--codex-thread")
    parser.add_argument("--sessions-root", action="append", default=[])
    parser.add_argument("--output", "-o")
    parser.add_argument("--report-mode", choices=("directory", "summary"), default=None)
    parser.add_argument("--include-children", action="store_true")
    parser.add_argument("--include-delegations", action="store_true")
    state = parser.add_mutually_exclusive_group()
    state.add_argument("--seal", action="store_true")
    parser.add_argument("--seal-aborted", action="store_true")
    state.add_argument("--live", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--title")
    parser.add_argument("--thread-title", action="append", default=[])
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--formatter-config")
    parser.add_argument("--json-output")
    parser.add_argument("--turn-csv-output")
    parser.add_argument("--work-unit-csv-output")
    parser.add_argument("--markdown-output")
    parsed, unknown = parser.parse_known_args(arguments)
    if unknown:
        return None
    path = Path(parsed.path).expanduser().resolve() if parsed.path else None
    if parsed.codex_thread:
        thread_id = parsed.codex_thread
        roots = tuple(
            Path(value).expanduser().resolve() for value in parsed.sessions_root
        ) or ((Path.home() / ".codex" / "sessions").resolve(),)
    elif path is not None and runtime._is_native_codex_rollout(path):
        identity = runtime._rollout_identity(path)
        if identity is None:
            return None
        thread_id = identity[0]
        roots = tuple(
            Path(value).expanduser().resolve() for value in parsed.sessions_root
        ) or (runtime._sessions_root_for_rollout(path).resolve(),)
    else:
        return None
    if not 1 <= parsed.workers <= 64:
        raise SystemExit("agent-report: error: --workers must be between 1 and 64")
    if parsed.seal_aborted and not parsed.seal:
        raise SystemExit("agent-report: error: --seal-aborted requires --seal")
    for value in parsed.thread_title:
        thread_id_value, separator, display_title = value.partition("=")
        if not separator or not thread_id_value.strip() or not display_title.strip():
            raise SystemExit(
                "agent-report: error: --thread-title must use THREAD_ID=TITLE with both values present"
            )
    output = (
        Path(parsed.output).expanduser().resolve()
        if parsed.output
        else (
            Path.cwd()
            / (
                f"{thread_id}-summary.html"
                if parsed.report_mode == "summary"
                else thread_id
            )
        ).resolve()
    )
    return _CodexAutomation(
        thread_id,
        roots,
        output,
        parsed.report_mode,
        parsed.include_children,
        parsed.include_delegations,
        parsed.seal,
        parsed.seal_aborted,
        parsed.title or "",
        tuple(parsed.thread_title),
        parsed.formatter_config,
        parsed.workers,
        tuple(
            (role, Path(value).expanduser().resolve())
            for role, value in (
                ("json", parsed.json_output),
                ("turns_csv", parsed.turn_csv_output),
                ("work_units_csv", parsed.work_unit_csv_output),
                ("markdown", parsed.markdown_output),
            )
            if value
        ),
    )


def _run_codex_automation(runtime: ModuleType, selection: _CodexAutomation) -> int:
    """Generate a Codex artifact through the shared service and exporter."""

    from .mcp_report import (
        ReportGenerator,
        ReportServerConfig,
        application_service_config,
        create_production_application_service,
    )

    service_config = application_service_config(runtime, selection.roots)
    thread_titles = {
        thread_id.strip(): display_title.strip()
        for value in selection.thread_titles
        for thread_id, _separator, display_title in (value.partition("="),)
    }
    if selection.formatter_config:
        try:
            runtime._load_tool_formatter_config(selection.formatter_config)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
    service = create_production_application_service(
        runtime,
        service_config,
        seal=selection.seal,
        allow_aborted=selection.seal_aborted,
        title=selection.title,
        thread_titles=thread_titles,
        workers=selection.workers,
    )
    config = ReportServerConfig(
        selection.roots,
        selection.output,
        datetime.now().astimezone().tzinfo or timezone.utc,
        str(datetime.now().astimezone().tzinfo or timezone.utc),
        65_536,
    )
    generator = ReportGenerator(runtime, config, application_service=service)
    try:
        result = generator.generate_streamlined_report(
            thread_id=selection.thread_id,
            output_path=str(selection.output),
            report_mode=cast(Literal["directory", "summary"], selection.report_mode),
            include_children=selection.include_children,
            include_collaborators=selection.include_collaborators,
            workspace_root=None,
        )
        if result.get("ok") and selection.companion_outputs:
            export_root = selection.output
            temporary_root: Path | None = None
            if selection.report_mode == "summary":
                temporary_root = Path(
                    tempfile.mkdtemp(prefix="agent-report-cli-formats-")
                )
                companion_result = generator.generate_streamlined_report(
                    thread_id=selection.thread_id,
                    output_path=str(temporary_root / "report"),
                    report_mode="directory",
                    include_children=selection.include_children,
                    include_collaborators=selection.include_collaborators,
                    workspace_root=None,
                )
                if not companion_result.get("ok"):
                    result = companion_result
                export_root = temporary_root / "report"
            try:
                if result.get("ok"):
                    filenames = {
                        "json": "report.json",
                        "turns_csv": "turns.csv",
                        "work_units_csv": "work-units.csv",
                        "markdown": "report.md",
                    }
                    for role, destination in selection.companion_outputs:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(export_root / filenames[role], destination)
            except OSError as error:
                print(
                    f"Unable to write report companion output: {error}", file=sys.stderr
                )
                return 1
            finally:
                if temporary_root is not None:
                    shutil.rmtree(temporary_root, ignore_errors=True)
    finally:
        generator.close()
    if not result.get("ok"):
        print(str(result.get("message", "Report generation failed.")), file=sys.stderr)
        return 1
    label = (
        "summary report" if selection.report_mode == "summary" else "report directory"
    )
    print(f"Codex {label} written to {selection.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
