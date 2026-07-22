# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Verify renderer resource resolution for installed and frozen agent-report commands.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

from __future__ import annotations

from pathlib import Path

from agent_report import cli


def test_report_script_path_uses_pyinstaller_bundle(monkeypatch, tmp_path: Path) -> None:
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
