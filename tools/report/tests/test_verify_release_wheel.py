# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Verify release-wheel completeness checks and native-engine enforcement.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "verify_release_wheel.py"
SPEC = importlib.util.spec_from_file_location("verify_release_wheel", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write_wheel(path: Path, *, include_engine: bool = True) -> None:
    """Write the smallest representative platform wheel fixture."""

    prefix = "agent_report-0.7.0.data/purelib"
    dist_info = "agent_report-0.7.0.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{dist_info}/METADATA",
            "Metadata-Version: 2.4\nName: agent-report\nVersion: 0.7.0\n",
        )
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: py3-none-linux_x86_64\n",
        )
        archive.writestr(
            f"{dist_info}/entry_points.txt",
            "[console_scripts]\n"
            "agent-report = agent_report.cli:main\n"
            "agent-report-mcp = agent_report.mcp_server:main\n",
        )
        archive.writestr(f"{prefix}/agent_report/mcp_report.py", "")
        archive.writestr(f"{prefix}/agent_report/mcp_server.py", "")
        archive.writestr(
            "agent_report-0.7.0.data/data/share/agent-report/run-timeline.py", ""
        )
        if include_engine:
            archive.writestr(
                f"{prefix}/agent_report/native/agent-report-engine", b"bin"
            )


def test_accepts_complete_platform_wheel(tmp_path: Path) -> None:
    """Accept a versioned wheel that contains both MCP and native runtimes."""

    wheel = tmp_path / "agent_report-0.7.0-py3-none-linux_x86_64.whl"
    _write_wheel(wheel)

    assert MODULE.verify_release_wheel(tmp_path, "0.7.0") == wheel.resolve()


def test_rejects_wheel_without_platform_engine(tmp_path: Path) -> None:
    """Prevent publication of a Python-only wheel that cannot index rollouts."""

    wheel = tmp_path / "agent_report-0.7.0-py3-none-linux_x86_64.whl"
    _write_wheel(wheel, include_engine=False)

    with pytest.raises(ValueError, match="bundled agent-report-engine"):
        MODULE.verify_release_wheel(wheel, "0.7.0")


def test_rejects_universal_macos_wheel_for_arm64_release(tmp_path: Path) -> None:
    """Do not advertise Intel support when the bundled parser is ARM-only."""

    wheel = tmp_path / "agent_report-0.7.0-py3-none-macosx_10_9_universal2.whl"
    _write_wheel(wheel)

    with pytest.raises(ValueError, match="does not match macos-arm64"):
        MODULE.verify_release_wheel(wheel, "0.7.0", "macos-arm64")
