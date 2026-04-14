#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


TRUSTED_PHASE_STATUSES = {"completed", "skipped"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _phase_status_map(state: dict | None) -> dict[str, str]:
    if not state:
        return {}
    phases = state.get("phases") or []
    return {
        phase.get("phase_id", f"phase-{idx}"): phase.get("status", "unknown")
        for idx, phase in enumerate(phases)
    }


def _blocking_phase(state: dict | None) -> str | None:
    if not state:
        return None
    phases = state.get("phases") or []
    for phase in phases:
        if phase.get("status") not in TRUSTED_PHASE_STATUSES:
            return phase.get("phase_id")
    return None


def _is_trusted_baseline(state: dict | None, *, summary_exists: bool, timeline_exists: bool) -> bool:
    if not state:
        return False
    phases = state.get("phases") or []
    if not phases:
        return False
    if state.get("current_phase") is not None:
        return False
    if not state.get("finished_at"):
        return False
    if not summary_exists or not timeline_exists:
        return False
    return all(phase.get("status") in TRUSTED_PHASE_STATUSES for phase in phases)


def _next_planning_fact(
    *,
    trusted: bool,
    state: dict | None,
    summary_exists: bool,
    timeline_exists: bool,
    workspace_exists: bool,
) -> str:
    if trusted:
        return (
            "The baseline completed cleanly; use the baseline summary and timeline "
            "as the accepted evidence bundle for planning and step selection."
        )
    if not workspace_exists:
        return "No baseline workspace exists yet."
    if state is None:
        return "The baseline workspace exists, but .methodology-runner/state.json is missing."
    if not summary_exists:
        return "The methodology workspace exists, but the baseline summary file is still missing."
    if not timeline_exists:
        return "The methodology workspace exists, but the timeline report is still missing."
    blocking = _blocking_phase(state)
    if blocking:
        return f"The baseline is still blocked in {blocking}."
    return "The baseline is incomplete even though no single blocking phase was identified."


def _build_note(payload: dict) -> str:
    lines = [
        "# Baseline Methodology Run",
        "",
        f"- Raw request path: `{payload['raw_request_path']}`",
        f"- Baseline workspace path: `{payload['baseline_workspace_path']}`",
        f"- Baseline status path: `{payload['baseline_status_path']}`",
        f"- Trusted baseline: `{str(payload['trusted']).lower()}`",
        f"- Summary path: `{payload['summary_path']}`",
        f"- Timeline path: `{payload['timeline_path']}`",
        f"- Baseline command mode: `{payload['baseline_mode']}`",
        f"- Methodology return code: `{payload['methodology_returncode']}`",
        f"- Timeline return code: `{payload['timeline_returncode']}`",
    ]
    if payload.get("blocking_phase"):
        lines.append(f"- Blocking phase: `{payload['blocking_phase']}`")
    lines.extend(
        [
            "",
            "## Most Important Next Fact",
            "",
            payload["next_planning_fact"],
            "",
        ]
    )
    return "\n".join(lines)


def _run_subprocess(cmd: list[str], cwd: Path, env: dict[str, str]) -> int:
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, check=False)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create or repair one trusted methodology baseline workspace, then "
            "write workflow-level baseline status artifacts."
        )
    )
    parser.add_argument("--run-dir", required=True, help="Workflow run directory.")
    parser.add_argument("--backend", default="codex", choices=["claude", "codex"])
    parser.add_argument("--model", default="gpt-5.4")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    run_dir = Path(args.run_dir).resolve()
    raw_request_path = run_dir / "raw-request.md"
    workspace = run_dir / "methodology-baseline-workspace"
    state_path = workspace / ".methodology-runner" / "state.json"
    summary_path = workspace / ".methodology-runner" / "summary.txt"
    timeline_path = workspace / "timeline.html"
    note_path = run_dir / "baseline-methodology-run.md"
    status_path = run_dir / "baseline-status.json"

    run_dir.mkdir(parents=True, exist_ok=True)

    if not raw_request_path.exists():
        payload = {
            "run_dir": str(run_dir),
            "raw_request_path": str(raw_request_path),
            "baseline_workspace_path": str(workspace),
            "baseline_note_path": str(note_path),
            "baseline_status_path": str(status_path),
            "summary_path": str(summary_path),
            "timeline_path": str(timeline_path),
            "baseline_mode": "missing-request",
            "methodology_returncode": None,
            "timeline_returncode": None,
            "trusted": False,
            "workspace_exists": workspace.exists(),
            "state_exists": state_path.exists(),
            "summary_exists": summary_path.exists(),
            "timeline_exists": timeline_path.exists(),
            "current_phase": None,
            "finished_at": None,
            "phase_statuses": {},
            "blocking_phase": None,
            "next_planning_fact": "The workflow run directory is missing raw-request.md.",
            "started_at": _now_iso(),
            "finished_at_iso": _now_iso(),
        }
        _write_json(status_path, payload)
        note_path.write_text(_build_note(payload), encoding="utf-8")
        return 2

    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"src/cli{os.pathsep}{existing_pythonpath}" if existing_pythonpath else "src/cli"

    workspace_exists = workspace.exists()
    state = _load_json(state_path)
    summary_exists = summary_path.exists()
    timeline_exists = timeline_path.exists()
    trusted_before = _is_trusted_baseline(
        state, summary_exists=summary_exists, timeline_exists=timeline_exists
    )

    methodology_returncode: int | None = None
    if not workspace_exists:
        mode = "fresh-run"
        cmd = [
            sys.executable,
            "-m",
            "methodology_runner",
            "run",
            str(raw_request_path),
            "--workspace",
            str(workspace),
            "--backend",
            args.backend,
        ]
        if args.model:
            cmd.extend(["--model", args.model])
        methodology_returncode = _run_subprocess(cmd, cwd=repo_root, env=env)
    elif state is None:
        mode = "corrupt-workspace"
    elif trusted_before:
        mode = "reuse-complete"
    else:
        mode = "resume"
        cmd = [
            sys.executable,
            "-m",
            "methodology_runner",
            "resume",
            str(workspace),
            "--backend",
            args.backend,
        ]
        if args.model:
            cmd.extend(["--model", args.model])
        methodology_returncode = _run_subprocess(cmd, cwd=repo_root, env=env)

    timeline_returncode: int | None = None
    if workspace.exists():
        timeline_cmd = [
            sys.executable,
            str(repo_root / "scripts" / "run-timeline.py"),
            str(workspace),
        ]
        timeline_returncode = _run_subprocess(timeline_cmd, cwd=repo_root, env=env)

    state = _load_json(state_path)
    summary_exists = summary_path.exists()
    timeline_exists = timeline_path.exists()
    trusted = _is_trusted_baseline(
        state, summary_exists=summary_exists, timeline_exists=timeline_exists
    )

    payload = {
        "run_dir": str(run_dir),
        "raw_request_path": str(raw_request_path),
        "baseline_workspace_path": str(workspace),
        "baseline_note_path": str(note_path),
        "baseline_status_path": str(status_path),
        "summary_path": str(summary_path),
        "timeline_path": str(timeline_path),
        "baseline_mode": mode,
        "methodology_returncode": methodology_returncode,
        "timeline_returncode": timeline_returncode,
        "trusted": trusted,
        "workspace_exists": workspace.exists(),
        "state_exists": state is not None,
        "summary_exists": summary_exists,
        "timeline_exists": timeline_exists,
        "current_phase": state.get("current_phase") if state else None,
        "finished_at": state.get("finished_at") if state else None,
        "phase_statuses": _phase_status_map(state),
        "blocking_phase": _blocking_phase(state),
        "next_planning_fact": _next_planning_fact(
            trusted=trusted,
            state=state,
            summary_exists=summary_exists,
            timeline_exists=timeline_exists,
            workspace_exists=workspace.exists(),
        ),
        "started_at": _now_iso(),
        "finished_at_iso": _now_iso(),
    }
    _write_json(status_path, payload)
    note_path.write_text(_build_note(payload), encoding="utf-8")

    return 0 if trusted else 1


if __name__ == "__main__":
    raise SystemExit(main())
