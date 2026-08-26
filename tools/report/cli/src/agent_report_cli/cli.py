# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Launch only the bundled standalone Agent Report CLI runtime.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

"""Minimal console entry point for the CLI-only wheel."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import sysconfig
from types import ModuleType


def _native_engine_path() -> Path:
    """Return the platform engine bundled inside the CLI wheel."""

    executable = "agent-report-engine.exe" if sys.platform == "win32" else "agent-report-engine"
    return Path(__file__).resolve().parent / "native" / executable


def _report_script_path() -> Path:
    """Return the report runtime installed as wheel data."""

    return Path(sysconfig.get_path("data")) / "share" / "agent-report" / "run-timeline.py"


def _load_report_module() -> ModuleType:
    """Load the bundled report implementation without app-only modules."""

    script_path = _report_script_path()
    spec = importlib.util.spec_from_file_location("_agent_report_cli_runtime", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load bundled report implementation: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    """Run the standalone Agent Report command."""

    os.environ.setdefault("AGENT_REPORT_ENGINE", str(_native_engine_path()))
    runtime = _load_report_module()
    return runtime.main(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
