# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Launch the bundled agent execution report implementation.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

"""Console entry point for the agent-report wheel."""

from __future__ import annotations

import importlib.util
import os
import sys
import sysconfig
from functools import cache
from pathlib import Path
from types import ModuleType


def _configure_bundled_engine() -> None:
    """Point the reporter at the platform engine carried by the installed wheel."""

    executable_name = "agent-report-engine.exe" if sys.platform == "win32" else "agent-report-engine"
    engine_path = Path(__file__).resolve().parent / "native" / executable_name
    os.environ.setdefault("AGENT_REPORT_ENGINE", str(engine_path))


@cache
def _load_report_module() -> ModuleType:
    """Load the bundled report implementation once for the installed command."""
    script_path = (
        Path(sysconfig.get_path("data"))
        / "share"
        / "agent-report"
        / "run-timeline.py"
    )
    spec = importlib.util.spec_from_file_location("_agent_report_runtime", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load bundled report implementation: {script_path}")

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
    return _load_report_module().main(argv)
