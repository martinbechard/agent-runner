#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _slugify(value: str) -> str:
    out = []
    for ch in value.lower():
        if ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    return "".join(out).strip("-")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare and launch the methodology optimization supervisor workflow.",
    )
    parser.add_argument("request_file", help="Raw request file for the campaign.")
    parser.add_argument("--backend", default="codex", choices=["claude", "codex"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--workflow-root",
        default=None,
        help="Explicit workflow root. Defaults to <project>/work/methodology-opt/<timestamp>-<slug>/",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[3]
    request_file = Path(args.request_file).resolve()
    if not request_file.exists():
        print(f"Request file not found: {request_file}", file=sys.stderr)
        return 2

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    slug = _slugify(request_file.stem)
    workflow_root = (
        Path(args.workflow_root).resolve()
        if args.workflow_root
        else repo_root / "work" / "methodology-opt" / f"{timestamp}-{slug}"
    )
    inputs_dir = workflow_root / "inputs"
    prompt_runs_dir = workflow_root / "prompt-runs"
    supervisor_run_dir = prompt_runs_dir / "supervisor"
    child_run_dir = prompt_runs_dir / "workflow"

    inputs_dir.mkdir(parents=True, exist_ok=True)
    supervisor_run_dir.mkdir(parents=True, exist_ok=True)
    child_run_dir.mkdir(parents=True, exist_ok=True)

    raw_request_copy = inputs_dir / "raw-request.md"
    shutil.copyfile(request_file, raw_request_copy)
    shutil.copyfile(request_file, child_run_dir / "raw-request.md")

    prompts_dir = repo_root / "tools" / "methodology-runner" / "docs" / "prompts"
    workflow_prompt_path = prompts_dir / "PR-019-methodology-optimization-workflow.md"
    supervisor_prompt_path = prompts_dir / "PR-020-methodology-optimization-supervisor.md"

    print(f"Workflow root:     {workflow_root}")
    print(f"Supervisor run:    {supervisor_run_dir}")
    print(f"Workflow run:      {child_run_dir}")
    print(f"Raw request copy:  {raw_request_copy}")

    if args.prepare_only:
        return 0

    cmd = [
        sys.executable,
        "-m",
        "prompt_runner",
        "run",
        str(supervisor_prompt_path),
        "--project-dir",
        str(repo_root),
        "--output-dir",
        str(supervisor_run_dir),
        "--backend",
        args.backend,
        "--var",
        f"workflow_prompt={workflow_prompt_path}",
        "--var",
        f"workflow_run_dir={child_run_dir}",
        "--var",
        f"raw_request={raw_request_copy}",
        "--no-project-organiser",
    ]
    if args.dry_run:
        cmd.append("--dry-run")

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(repo_root / "tools" / "methodology-runner" / "src"),
            str(repo_root / "tools" / "prompt-runner" / "src"),
        ]
    )
    proc = subprocess.run(cmd, cwd=repo_root, text=True, env=env)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
