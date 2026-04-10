#!/usr/bin/env python3
"""Generate an HTML timeline report for a methodology-runner workspace.

Parses file modification timestamps from the .methodology-runner/runs/
directory to reconstruct the execution timeline, showing how long each
step (selector, prompt-generator, generator calls, judge calls,
cross-ref) took.

Usage:
    python scripts/run-timeline.py <workspace-path> [--output report.html]

If --output is omitted, writes to <workspace>/.methodology-runner/timeline.html
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Step:
    name: str
    started: datetime
    ended: datetime
    size_bytes: int = 0
    detail: str = ""

    @property
    def duration_seconds(self) -> float:
        return (self.ended - self.started).total_seconds()

    @property
    def duration_str(self) -> str:
        s = int(self.duration_seconds)
        if s < 60:
            return f"{s}s"
        m, s = divmod(s, 60)
        return f"{m}m{s:02d}s"


@dataclass
class PhaseTimeline:
    phase_id: str
    phase_number: int
    steps: list[Step] = field(default_factory=list)

    @property
    def total_seconds(self) -> float:
        if not self.steps:
            return 0
        return (self.steps[-1].ended - self.steps[0].started).total_seconds()

    @property
    def total_str(self) -> str:
        s = int(self.total_seconds)
        m, s = divmod(s, 60)
        return f"{m}m{s:02d}s"


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _file_step(name: str, start_file: Path, end_file: Path, detail: str = "") -> Step | None:
    if not start_file.exists() or not end_file.exists():
        return None
    return Step(
        name=name,
        started=_mtime(start_file),
        ended=_mtime(end_file),
        size_bytes=end_file.stat().st_size,
        detail=detail,
    )


def parse_phase(runs_dir: Path, phase_num: int, phase_id: str) -> PhaseTimeline | None:
    phase_dir = runs_dir / f"phase-{phase_num}"
    if not phase_dir.exists():
        return None

    timeline = PhaseTimeline(phase_id=phase_id, phase_number=phase_num)

    # Selector
    selector_logs = runs_dir / "selector-logs"
    if selector_logs.exists():
        for log in sorted(selector_logs.glob(f"selector-{phase_id}-*.stdout.log")):
            stderr = log.with_suffix("").with_suffix(".stderr.log")
            step = _file_step("Skill-Selector", stderr if stderr.exists() else log, log)
            if step:
                timeline.steps.append(step)
            break

    # Skills yaml
    skills_yaml = phase_dir / f"phase-{phase_num:03d}-skills.yaml"
    prelude = phase_dir / "generator-prelude.txt"
    if skills_yaml.exists() and prelude.exists():
        step = _file_step("Prelude build", skills_yaml, prelude)
        if step:
            timeline.steps.append(step)

    # Prompt generator
    prompt_file = phase_dir / "prompt-file.md"
    if prompt_file.exists() and timeline.steps:
        prev = timeline.steps[-1]
        step = Step(
            name="Prompt generator",
            started=prev.ended,
            ended=_mtime(prompt_file),
            size_bytes=prompt_file.stat().st_size,
        )
        if step.duration_seconds > 0:
            timeline.steps.append(step)

    # Prompt-runner iterations
    pr_dir = phase_dir / "prompt-runner-output"
    if pr_dir.exists():
        logs_dir = pr_dir / "logs"
        if logs_dir.exists():
            for prompt_dir in sorted(logs_dir.iterdir()):
                if not prompt_dir.is_dir():
                    continue
                prompt_name = prompt_dir.name
                for iter_log in sorted(prompt_dir.glob("iter-*-generator.stdout.log")):
                    iter_num = iter_log.name.split("-")[1]
                    stderr = iter_log.with_name(f"iter-{iter_num}-generator.stderr.log")
                    step = _file_step(
                        f"{prompt_name} / iter {iter_num} generator",
                        stderr if stderr.exists() else iter_log,
                        iter_log,
                    )
                    if step:
                        timeline.steps.append(step)

                    judge_log = iter_log.with_name(f"iter-{iter_num}-judge.stdout.log")
                    judge_stderr = iter_log.with_name(f"iter-{iter_num}-judge.stderr.log")
                    if judge_log.exists():
                        step = _file_step(
                            f"{prompt_name} / iter {iter_num} judge",
                            judge_stderr if judge_stderr.exists() else judge_log,
                            judge_log,
                        )
                        if step:
                            timeline.steps.append(step)

    # Cross-ref
    xref = phase_dir / "cross-ref-result.json"
    if xref.exists() and timeline.steps:
        prev = timeline.steps[-1]
        step = Step(
            name="Cross-reference verification",
            started=prev.ended,
            ended=_mtime(xref),
            size_bytes=xref.stat().st_size,
        )
        if step.duration_seconds > 0:
            timeline.steps.append(step)

    return timeline if timeline.steps else None


def parse_workspace(workspace: Path) -> list[PhaseTimeline]:
    runs_dir = workspace / ".methodology-runner" / "runs"
    if not runs_dir.exists():
        return []

    state_path = workspace / ".methodology-runner" / "state.json"
    phases_map: dict[int, str] = {}
    if state_path.exists():
        state = json.loads(state_path.read_text())
        for p in state.get("phases", []):
            pid = p["phase_id"]
            # Extract phase number from the directory name convention
            for i in range(10):
                if (runs_dir / f"phase-{i}").exists():
                    # Match by checking if the phase_id starts with PH-00{i}
                    if pid.startswith(f"PH-00{i}"):
                        phases_map[i] = pid

    timelines = []
    for phase_dir in sorted(runs_dir.glob("phase-*")):
        if not phase_dir.is_dir():
            continue
        try:
            num = int(phase_dir.name.split("-")[1])
        except (IndexError, ValueError):
            continue
        phase_id = phases_map.get(num, f"PH-{num:03d}")
        tl = parse_phase(runs_dir, num, phase_id)
        if tl:
            timelines.append(tl)
    return timelines


def _bar_color(name: str) -> str:
    if "generator" in name.lower() and "prompt generator" not in name.lower():
        return "#4a90d9"
    if "judge" in name.lower():
        return "#e67e22"
    if "selector" in name.lower():
        return "#27ae60"
    if "prompt generator" in name.lower():
        return "#8e44ad"
    if "cross-ref" in name.lower():
        return "#c0392b"
    if "prelude" in name.lower():
        return "#27ae60"
    return "#95a5a6"


def render_html(timelines: list[PhaseTimeline], workspace: Path) -> str:
    rows = []
    grand_total = sum(t.total_seconds for t in timelines)

    for tl in timelines:
        rows.append(f'<tr class="phase-header"><td colspan="4">'
                     f'<strong>{tl.phase_id}</strong> — {tl.total_str}'
                     f'</td></tr>')
        for step in tl.steps:
            pct = (step.duration_seconds / grand_total * 100) if grand_total > 0 else 0
            color = _bar_color(step.name)
            size_kb = step.size_bytes / 1024
            rows.append(
                f'<tr>'
                f'<td class="step-name">{step.name}</td>'
                f'<td class="step-time">{step.duration_str}</td>'
                f'<td class="step-size">{size_kb:.0f}KB</td>'
                f'<td class="step-bar">'
                f'<div class="bar" style="width:{max(pct, 0.5):.1f}%;background:{color}">'
                f'</div></td>'
                f'</tr>'
            )

    grand_str = f"{int(grand_total // 60)}m{int(grand_total % 60):02d}s"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Methodology Runner Timeline — {workspace.name}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 2em; background: #fafafa; }}
  h1 {{ font-size: 1.4em; }}
  h2 {{ font-size: 1.1em; color: #555; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 900px; }}
  tr.phase-header td {{ background: #eee; padding: 8px 12px; font-size: 1.05em; border-top: 2px solid #ccc; }}
  td {{ padding: 4px 12px; vertical-align: middle; }}
  .step-name {{ width: 45%; font-size: 0.9em; }}
  .step-time {{ width: 8%; text-align: right; font-family: monospace; font-size: 0.9em; }}
  .step-size {{ width: 7%; text-align: right; font-family: monospace; font-size: 0.85em; color: #888; }}
  .step-bar {{ width: 40%; }}
  .bar {{ height: 18px; border-radius: 3px; min-width: 4px; }}
  .legend {{ display: flex; gap: 1.5em; margin: 1em 0; font-size: 0.85em; }}
  .legend-item {{ display: flex; align-items: center; gap: 0.4em; }}
  .legend-swatch {{ width: 14px; height: 14px; border-radius: 2px; }}
</style>
</head>
<body>
<h1>Methodology Runner Timeline</h1>
<h2>{workspace} — total {grand_str}</h2>
<div class="legend">
  <div class="legend-item"><div class="legend-swatch" style="background:#27ae60"></div> Selector/Prelude</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#8e44ad"></div> Prompt Generator</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#4a90d9"></div> Generator (claude)</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#e67e22"></div> Judge (claude)</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#c0392b"></div> Cross-ref</div>
</div>
<table>
{''.join(rows)}
</table>
</body>
</html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate timeline report for a methodology-runner workspace.")
    parser.add_argument("workspace", help="Path to the methodology-runner workspace directory.")
    parser.add_argument("--output", "-o", default=None, help="Output HTML path (default: <workspace>/.methodology-runner/timeline.html)")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    if not workspace.exists():
        print(f"Workspace not found: {workspace}", file=sys.stderr)
        return 1

    timelines = parse_workspace(workspace)
    if not timelines:
        print(f"No phase data found in {workspace}", file=sys.stderr)
        return 1

    html = render_html(timelines, workspace)
    output = Path(args.output) if args.output else workspace / ".methodology-runner" / "timeline.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"Timeline written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
