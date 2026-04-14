from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "run_methodology_baseline.py"
    spec = importlib.util.spec_from_file_location("run_methodology_baseline", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_state(path: Path, *, current_phase: str | None, finished_at: str | None, phase_statuses: list[tuple[str, str]]) -> None:
    payload = {
        "current_phase": current_phase,
        "finished_at": finished_at,
        "phases": [
            {"phase_id": phase_id, "status": status}
            for phase_id, status in phase_statuses
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_fresh_run_writes_trusted_baseline_artifacts(tmp_path, monkeypatch):
    module = _load_module()
    run_dir = tmp_path / "workflow"
    raw_request = run_dir / "raw-request.md"
    raw_request.parent.mkdir(parents=True)
    raw_request.write_text("# hello\n", encoding="utf-8")

    workspace = run_dir / "methodology-baseline-workspace"
    summary_path = workspace / ".methodology-runner" / "summary.txt"
    state_path = workspace / ".methodology-runner" / "state.json"
    timeline_path = workspace / "timeline.html"
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None, env=None, text=None, check=None):
        calls.append(list(cmd))
        if cmd[:3] == [sys.executable, "-m", "methodology_runner"]:
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text("summary", encoding="utf-8")
            _write_state(
                state_path,
                current_phase=None,
                finished_at="2026-04-13T01:20:00Z",
                phase_statuses=[
                    ("PH-000", "completed"),
                    ("PH-001", "completed"),
                ],
            )
            return subprocess.CompletedProcess(cmd, 0)
        if "run-timeline.py" in str(cmd[1]):
            timeline_path.write_text("<html></html>", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0)
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    rc = module.main(["--run-dir", str(run_dir), "--backend", "codex", "--model", "gpt-5.4"])

    assert rc == 0
    assert calls[0][:4] == [sys.executable, "-m", "methodology_runner", "run"]
    status = json.loads((run_dir / "baseline-status.json").read_text(encoding="utf-8"))
    assert status["trusted"] is True
    assert status["baseline_mode"] == "fresh-run"
    assert status["summary_exists"] is True
    assert status["timeline_exists"] is True
    note = (run_dir / "baseline-methodology-run.md").read_text(encoding="utf-8")
    assert "Trusted baseline: `true`" in note


def test_resume_writes_untrusted_status_when_phase_still_running(tmp_path, monkeypatch):
    module = _load_module()
    run_dir = tmp_path / "workflow"
    raw_request = run_dir / "raw-request.md"
    raw_request.parent.mkdir(parents=True)
    raw_request.write_text("# hello\n", encoding="utf-8")

    workspace = run_dir / "methodology-baseline-workspace"
    summary_path = workspace / ".methodology-runner" / "summary.txt"
    state_path = workspace / ".methodology-runner" / "state.json"
    timeline_path = workspace / "timeline.html"
    workspace.mkdir(parents=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("partial summary", encoding="utf-8")
    _write_state(
        state_path,
        current_phase="PH-002",
        finished_at=None,
        phase_statuses=[
            ("PH-000", "completed"),
            ("PH-001", "completed"),
            ("PH-002", "running"),
        ],
    )

    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None, env=None, text=None, check=None):
        calls.append(list(cmd))
        if cmd[:3] == [sys.executable, "-m", "methodology_runner"]:
            return subprocess.CompletedProcess(cmd, 1)
        if "run-timeline.py" in str(cmd[1]):
            timeline_path.write_text("<html></html>", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0)
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    rc = module.main(["--run-dir", str(run_dir)])

    assert rc == 1
    assert calls[0][:4] == [sys.executable, "-m", "methodology_runner", "resume"]
    status = json.loads((run_dir / "baseline-status.json").read_text(encoding="utf-8"))
    assert status["trusted"] is False
    assert status["baseline_mode"] == "resume"
    assert status["blocking_phase"] == "PH-002"
    assert "still blocked in PH-002" in status["next_planning_fact"]


def test_reuse_complete_skips_methodology_when_existing_workspace_is_trusted(tmp_path, monkeypatch):
    module = _load_module()
    run_dir = tmp_path / "workflow"
    raw_request = run_dir / "raw-request.md"
    raw_request.parent.mkdir(parents=True)
    raw_request.write_text("# hello\n", encoding="utf-8")

    workspace = run_dir / "methodology-baseline-workspace"
    summary_path = workspace / ".methodology-runner" / "summary.txt"
    state_path = workspace / ".methodology-runner" / "state.json"
    timeline_path = workspace / "timeline.html"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("done", encoding="utf-8")
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline_path.write_text("<html>done</html>", encoding="utf-8")
    _write_state(
        state_path,
        current_phase=None,
        finished_at="2026-04-13T01:20:00Z",
        phase_statuses=[
            ("PH-000", "completed"),
            ("PH-001", "completed"),
        ],
    )

    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None, env=None, text=None, check=None):
        calls.append(list(cmd))
        if "run-timeline.py" in str(cmd[1]):
            timeline_path.write_text("<html>refreshed</html>", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0)
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    rc = module.main(["--run-dir", str(run_dir)])

    assert rc == 0
    assert len(calls) == 1
    assert "run-timeline.py" in str(calls[0][1])
    status = json.loads((run_dir / "baseline-status.json").read_text(encoding="utf-8"))
    assert status["trusted"] is True
    assert status["baseline_mode"] == "reuse-complete"
