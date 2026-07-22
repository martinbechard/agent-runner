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


def _frozen_root() -> Path | None:
    """Return PyInstaller's extraction root when running as a frozen sidecar."""

    value = getattr(sys, "_MEIPASS", None)
    return Path(value) if value is not None else None


def _native_engine_path() -> Path:
    """Resolve the required native discovery engine for this distribution."""

    executable_name = (
        "agent-report-engine.exe"
        if sys.platform == "win32"
        else "agent-report-engine"
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
    data_root = frozen_root if frozen_root is not None else Path(sysconfig.get_path("data"))
    return data_root / "share" / "agent-report" / "run-timeline.py"


@cache
def _load_report_module() -> ModuleType:
    """Load the bundled report implementation once for the installed command."""
    script_path = _report_script_path()
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


if __name__ == "__main__":
    raise SystemExit(main())
