#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay one methodology-runner phase in isolation by cloning a "
            "baseline workspace, resetting the target phase, and resuming only "
            "that phase."
        )
    )
    parser.add_argument("--baseline-workspace", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--backend", default="codex", choices=["claude", "codex"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[3]
    baseline_workspace = Path(args.baseline_workspace).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    if not baseline_workspace.exists():
        print(f"Baseline workspace not found: {baseline_workspace}", file=sys.stderr)
        return 2

    metadata_path = output_dir / "harness-metadata.json"
    metadata: dict[str, object] = {
        "baseline_workspace": str(baseline_workspace),
        "phase": args.phase,
        "output_dir": str(output_dir),
        "backend": args.backend,
        "model": args.model,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "steps": [],
    }

    reset_cmd = [
        sys.executable,
        "-m",
        "methodology_runner",
        "reset",
        str(output_dir),
        "--phase",
        args.phase,
    ]
    resume_cmd = [
        sys.executable,
        "-m",
        "methodology_runner",
        "resume",
        str(output_dir),
        "--backend",
        args.backend,
        "--phases",
        args.phase,
    ]
    if args.model:
        resume_cmd.extend(["--model", args.model])

    if args.dry_run:
        metadata["steps"] = [
            {"name": "copytree", "from": str(baseline_workspace), "to": str(output_dir)},
            {"name": "reset", "argv": reset_cmd},
            {"name": "resume", "argv": resume_cmd},
        ]
        output_dir.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"[dry-run] would clone {baseline_workspace} -> {output_dir}")
        print("[dry-run] would run:")
        print("  " + " ".join(reset_cmd))
        print("  " + " ".join(resume_cmd))
        return 0

    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.copytree(baseline_workspace, output_dir)

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(repo_root / "tools" / "methodology-runner" / "src"),
            str(repo_root / "tools" / "prompt-runner" / "src"),
        ]
    )
    reset_proc = subprocess.run(
        reset_cmd,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    metadata["steps"].append(
        {
            "name": "reset",
            "argv": reset_cmd,
            "returncode": reset_proc.returncode,
            "stdout": reset_proc.stdout,
            "stderr": reset_proc.stderr,
        }
    )
    if reset_proc.returncode != 0:
        output_dir.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        sys.stderr.write(reset_proc.stderr)
        return reset_proc.returncode

    resume_proc = subprocess.run(
        resume_cmd,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    metadata["steps"].append(
        {
            "name": "resume",
            "argv": resume_cmd,
            "returncode": resume_proc.returncode,
            "stdout": resume_proc.stdout,
            "stderr": resume_proc.stderr,
        }
    )
    metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    sys.stdout.write(reset_proc.stdout)
    sys.stdout.write(resume_proc.stdout)
    sys.stderr.write(reset_proc.stderr)
    sys.stderr.write(resume_proc.stderr)
    return resume_proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
