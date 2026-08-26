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


def _write_wheel(
    path: Path,
    *,
    include_engine: bool = True,
    include_launcher: bool = True,
    include_token_ledger: bool = True,
    include_license: bool = True,
    include_desktop: bool = False,
    include_desktop_extra: bool = False,
    include_app_runtime: bool = False,
    include_secondary_command: bool = False,
    windows_license_line_endings: bool = False,
) -> None:
    """Write the smallest representative platform wheel fixture."""

    prefix = "agent_report_cli-1.0.0.data/purelib"
    dist_info = "agent_report_cli-1.0.0.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{dist_info}/METADATA",
            "Metadata-Version: 2.4\nName: agent-report-cli\nVersion: 1.0.0\n"
            + ("Provides-Extra: desktop\n" if include_desktop_extra else ""),
        )
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: py3-none-linux_x86_64\n",
        )
        archive.writestr(
            f"{dist_info}/entry_points.txt",
            "[console_scripts]\nagent-report = agent_report_cli.cli:main\n"
            + (
                "mcp-agent-report = agent_report.mcp_server:main\n"
                if include_secondary_command
                else ""
            ),
        )
        if include_launcher:
            archive.writestr(f"{prefix}/agent_report_cli/cli.py", "")
        archive.writestr(
            "agent_report_cli-1.0.0.data/data/share/agent-report/run-timeline.py", ""
        )
        if include_token_ledger:
            archive.writestr(
                "agent_report_cli-1.0.0.data/data/share/agent-report/token_ledger.py", ""
            )
        if include_engine:
            archive.writestr(
                f"{prefix}/agent_report_cli/native/agent-report-engine", b"bin"
            )
        if include_license:
            license_text = (
                "MIT License\n\nCopyright (c) 2026 "
                "Martin.Bechard@DevConsult.ca\n"
            )
            if windows_license_line_endings:
                license_text = license_text.replace("\n", "\r\n")
            archive.writestr(
                f"{dist_info}/licenses/LICENSE",
                license_text,
            )
        if include_desktop:
            archive.writestr(
                f"{prefix}/agent_report_desktop/app.js", "desktop application"
            )
        if include_app_runtime:
            archive.writestr(f"{prefix}/agent_report/report_worker.py", "app worker")


def test_accepts_complete_platform_wheel(tmp_path: Path) -> None:
    """Accept a versioned wheel that contains only the CLI runtime."""

    wheel = tmp_path / "agent_report_cli-1.0.0-py3-none-linux_x86_64.whl"
    _write_wheel(wheel)

    assert MODULE.verify_release_wheel(tmp_path, "1.0.0") == wheel.resolve()


def test_accepts_windows_license_line_endings(tmp_path: Path) -> None:
    """Treat CRLF as equivalent legal text in wheels built on Windows."""

    wheel = tmp_path / "agent_report_cli-1.0.0-py3-none-linux_x86_64.whl"
    _write_wheel(wheel, windows_license_line_endings=True)

    assert MODULE.verify_release_wheel(wheel, "1.0.0") == wheel.resolve()


def test_rejects_wheel_without_platform_engine(tmp_path: Path) -> None:
    """Prevent publication of a Python-only wheel that cannot index rollouts."""

    wheel = tmp_path / "agent_report_cli-1.0.0-py3-none-linux_x86_64.whl"
    _write_wheel(wheel, include_engine=False)

    with pytest.raises(ValueError, match="bundled agent-report-engine"):
        MODULE.verify_release_wheel(wheel, "1.0.0")


def test_rejects_wheel_without_standalone_launcher(tmp_path: Path) -> None:
    """Require the minimal standalone command launcher."""

    wheel = tmp_path / "agent_report_cli-1.0.0-py3-none-linux_x86_64.whl"
    _write_wheel(wheel, include_launcher=False)

    with pytest.raises(ValueError, match="agent_report_cli/cli.py"):
        MODULE.verify_release_wheel(wheel, "1.0.0")


def test_rejects_wheel_without_token_ledger_runtime(tmp_path: Path) -> None:
    """Require the drilldown renderer used by token-summary HTML reports."""

    wheel = tmp_path / "agent_report_cli-1.0.0-py3-none-linux_x86_64.whl"
    _write_wheel(wheel, include_token_ledger=False)

    with pytest.raises(ValueError, match="token_ledger.py"):
        MODULE.verify_release_wheel(wheel, "1.0.0")


def test_rejects_wheel_without_mit_license(tmp_path: Path) -> None:
    """Require the standalone distribution to carry its legal grant."""

    wheel = tmp_path / "agent_report_cli-1.0.0-py3-none-linux_x86_64.whl"
    _write_wheel(wheel, include_license=False)

    with pytest.raises(ValueError, match="MIT LICENSE"):
        MODULE.verify_release_wheel(wheel, "1.0.0")


def test_rejects_wheel_containing_desktop_application_files(tmp_path: Path) -> None:
    """Keep the standalone CLI wheel independent from the unfinished app."""

    wheel = tmp_path / "agent_report_cli-1.0.0-py3-none-linux_x86_64.whl"
    _write_wheel(wheel, include_desktop=True)

    with pytest.raises(ValueError, match="desktop application files"):
        MODULE.verify_release_wheel(wheel, "1.0.0")


def test_rejects_wheel_advertising_desktop_install_extra(tmp_path: Path) -> None:
    """Do not offer the Tauri app through the standalone CLI package."""

    wheel = tmp_path / "agent_report_cli-1.0.0-py3-none-linux_x86_64.whl"
    _write_wheel(wheel, include_desktop_extra=True)

    with pytest.raises(ValueError, match="desktop install extra"):
        MODULE.verify_release_wheel(wheel, "1.0.0")


def test_rejects_wheel_containing_app_runtime_code(tmp_path: Path) -> None:
    """Exclude the Python worker used only by the Tauri application."""

    wheel = tmp_path / "agent_report_cli-1.0.0-py3-none-linux_x86_64.whl"
    _write_wheel(wheel, include_app_runtime=True)

    with pytest.raises(ValueError, match="app runtime files"):
        MODULE.verify_release_wheel(wheel, "1.0.0")


def test_rejects_wheel_containing_a_second_console_command(tmp_path: Path) -> None:
    """Publish only the agent-report console entry point."""

    wheel = tmp_path / "agent_report_cli-1.0.0-py3-none-linux_x86_64.whl"
    _write_wheel(wheel, include_secondary_command=True)

    with pytest.raises(ValueError, match="only the standalone CLI"):
        MODULE.verify_release_wheel(wheel, "1.0.0")


def test_rejects_universal_macos_wheel_for_arm64_release(tmp_path: Path) -> None:
    """Do not advertise Intel support when the bundled parser is ARM-only."""

    wheel = tmp_path / "agent_report_cli-1.0.0-py3-none-macosx_10_9_universal2.whl"
    _write_wheel(wheel)

    with pytest.raises(ValueError, match="does not match macos-arm64"):
        MODULE.verify_release_wheel(wheel, "1.0.0", "macos-arm64")
