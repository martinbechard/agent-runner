# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Build the required native discovery engine into a platform-specific agent-report wheel.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

"""Setuptools commands for the mixed Python and Rust agent-report package."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

from setuptools import setup
from setuptools.command.bdist_wheel import bdist_wheel
from setuptools.command.build_py import build_py


REPORT_ROOT = Path(__file__).resolve().parent
ENGINE_NAME = "agent-report-engine.exe" if sys.platform == "win32" else "agent-report-engine"


class BuildWithNativeEngine(build_py):
    """Compile and copy the mandatory Rust engine into the Python package tree."""

    def run(self) -> None:
        cargo = os.environ.get("CARGO", "cargo")
        command = [
            cargo,
            "build",
            "--locked",
            "--release",
            "--manifest-path",
            str(REPORT_ROOT / "Cargo.toml"),
            "-p",
            "agent-report-engine",
        ]
        subprocess.run(command, cwd=REPORT_ROOT, check=True)
        super().run()
        target_root = Path(os.environ.get("CARGO_TARGET_DIR", REPORT_ROOT / "target"))
        source = target_root / "release" / ENGINE_NAME
        if not source.is_file():
            raise RuntimeError(f"Native report engine build did not produce {source}")
        destination = Path(self.build_lib) / "agent_report" / "native" / ENGINE_NAME
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


class PlatformWheel(bdist_wheel):
    """Tag the wheel as platform-specific because it contains a native executable."""

    def finalize_options(self) -> None:
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self) -> tuple[str, str, str]:
        _, _, platform = super().get_tag()
        if sys.platform == "darwin" and platform.endswith(
            ("_arm64", "_universal2")
        ):
            platform = "macosx_11_0_arm64"
        return "py3", "none", platform


setup(
    cmdclass={
        "build_py": BuildWithNativeEngine,
        "bdist_wheel": PlatformWheel,
    }
)
