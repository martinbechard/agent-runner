# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Verify that one Agent Report release wheel is complete and platform-specific.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

"""Validate Agent Report wheel metadata, entry points, and native payload."""

from __future__ import annotations

import argparse
import re
import zipfile
from email.parser import BytesParser
from pathlib import Path


def _single_wheel(path: Path) -> Path:
    """Resolve one wheel file from a file or wheelhouse directory."""

    candidates = [path] if path.is_file() else sorted(path.glob("*.whl"))
    if len(candidates) != 1:
        raise ValueError(f"Expected one wheel under {path}, found {len(candidates)}")
    return candidates[0]


PLATFORM_SUFFIXES = {
    "linux-x64": "-linux_x86_64.whl",
    "macos-arm64": "-macosx_11_0_arm64.whl",
    "windows-x64": "-win_amd64.whl",
}


def verify_release_wheel(
    path: Path, expected_version: str, expected_platform: str | None = None
) -> Path:
    """Validate one platform wheel and return its resolved path."""

    wheel = _single_wheel(path).resolve()
    if not re.fullmatch(r"\d+\.\d+\.\d+", expected_version):
        raise ValueError(f"Invalid expected version: {expected_version}")
    if not wheel.name.startswith(f"agent_report_cli-{expected_version}-"):
        raise ValueError(
            f"Wheel filename does not contain version {expected_version}: {wheel.name}"
        )
    if wheel.name.endswith("-any.whl"):
        raise ValueError(f"Release wheel must be platform-specific: {wheel.name}")
    if expected_platform is not None:
        expected_suffix = PLATFORM_SUFFIXES[expected_platform]
        if not wheel.name.endswith(expected_suffix):
            raise ValueError(
                f"Wheel does not match {expected_platform}: {wheel.name}; "
                f"expected suffix {expected_suffix}"
            )

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        desktop_resources = [
            name
            for name in names
            if "/agent_report_desktop/" in name
            or "/desktop/" in name
            or name.endswith((".app", ".msi", ".dmg"))
        ]
        if desktop_resources:
            raise ValueError(
                "Standalone CLI wheel contains desktop application files: "
                + ", ".join(desktop_resources)
            )
        app_runtime_resources = [
            name
            for name in names
            if "/agent_report/" in name
            or name.endswith(("/mcp_server.py", "/report_worker.py"))
        ]
        if app_runtime_resources:
            raise ValueError(
                "Standalone CLI wheel contains app runtime files: "
                + ", ".join(app_runtime_resources)
            )
        metadata_names = [
            name for name in names if name.endswith(".dist-info/METADATA")
        ]
        wheel_metadata_names = [
            name for name in names if name.endswith(".dist-info/WHEEL")
        ]
        entry_point_names = [
            name for name in names if name.endswith(".dist-info/entry_points.txt")
        ]
        if len(metadata_names) != 1 or len(wheel_metadata_names) != 1:
            raise ValueError("Wheel must contain exactly one METADATA and WHEEL file")
        if len(entry_point_names) != 1:
            raise ValueError("Wheel must contain exactly one entry_points.txt file")

        metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        if (
            metadata["Name"] != "agent-report-cli"
            or metadata["Version"] != expected_version
        ):
            raise ValueError(
                "Wheel metadata identity mismatch: "
                f"{metadata['Name']} {metadata['Version']}"
            )
        provided_extras = {
            value.casefold() for value in (metadata.get_all("Provides-Extra") or [])
        }
        if "desktop" in provided_extras:
            raise ValueError(
                "Standalone CLI wheel must not advertise a desktop install extra"
            )
        wheel_metadata = archive.read(wheel_metadata_names[0]).decode("utf-8")
        if "Root-Is-Purelib: false" not in wheel_metadata:
            raise ValueError("Release wheel is incorrectly marked as pure Python")

        entry_points = archive.read(entry_point_names[0]).decode("utf-8")
        console_entries = {
            line.strip()
            for line in entry_points.splitlines()
            if line.strip() and not line.startswith("[")
        }
        required_entry_points = {"agent-report = agent_report_cli.cli:main"}
        if console_entries != required_entry_points:
            raise ValueError(
                "Wheel console entry points must contain only the standalone CLI: "
                + ", ".join(sorted(console_entries))
            )

        windows_wheel = "-win_" in wheel.name
        engine_name = (
            "agent-report-engine.exe" if windows_wheel else "agent-report-engine"
        )
        engine_paths = [
            name
            for name in names
            if name.endswith(f"/agent_report_cli/native/{engine_name}")
        ]
        if len(engine_paths) != 1:
            raise ValueError(
                f"Wheel must contain exactly one bundled {engine_name}, found "
                f"{len(engine_paths)}"
            )
        required_resources = (
            "/agent_report_cli/cli.py",
            "/share/agent-report/run-timeline.py",
            "/share/agent-report/token_ledger.py",
        )
        missing_resources = [
            resource
            for resource in required_resources
            if not any(name.endswith(resource) for name in names)
        ]
        if missing_resources:
            raise ValueError(
                "Wheel is missing runtime resources: " + ", ".join(missing_resources)
            )
        license_paths = [
            name for name in names if name.endswith(".dist-info/licenses/LICENSE")
        ]
        if len(license_paths) != 1:
            raise ValueError(
                "Wheel must contain exactly one MIT LICENSE file under dist-info/licenses"
            )
        license_text = archive.read(license_paths[0]).decode("utf-8")
        if not license_text.startswith("MIT License\n") or (
            "Copyright (c) 2026 Martin.Bechard@DevConsult.ca" not in license_text
        ):
            raise ValueError("Wheel MIT LICENSE content is invalid")
    return wheel


def main(argv: list[str] | None = None) -> int:
    """Run release-wheel validation from the command line."""

    parser = argparse.ArgumentParser(
        description="Verify one platform-specific Agent Report release wheel."
    )
    parser.add_argument(
        "path", type=Path, help="Wheel file or directory containing one wheel"
    )
    parser.add_argument(
        "--expected-version",
        required=True,
        help="Package version or agent-report-cli-vVERSION release tag",
    )
    parser.add_argument(
        "--expected-platform",
        choices=sorted(PLATFORM_SUFFIXES),
        help="Required release target and exact wheel platform tag",
    )
    args = parser.parse_args(argv)
    expected_version = args.expected_version.removeprefix("agent-report-cli-v")
    try:
        wheel = verify_release_wheel(
            args.path, expected_version, args.expected_platform
        )
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Agent Report wheel verification failed: {error}\n")
    print(f"Verified Agent Report release wheel: {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
