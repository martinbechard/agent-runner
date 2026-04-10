#!/usr/bin/env python3
"""Generate an HTML timeline report for a methodology-runner workspace.

Parses JSONL logs from .methodology-runner/runs/ to show:
- Per-phase wall time breakdown (selector, prompt-gen, generator, judge, cross-ref)
- Per-call drill-down: turns, thinking, tool calls, subagent spawns
- Token usage and cost per call
- Visual bars proportional to time spent

Usage:
    python scripts/run-timeline.py <workspace-path> [--output report.html]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    name: str
    input_size: int  # chars
    description: str = ""


@dataclass
class Turn:
    turn_number: int
    thinking_chars: int = 0
    text_chars: int = 0
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


@dataclass
class CallDetail:
    """Parsed from one JSONL log file (one claude invocation)."""
    duration_ms: int = 0
    duration_api_ms: int = 0
    num_turns: int = 0
    cost_usd: float = 0.0
    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    turns: list[Turn] = field(default_factory=list)
    subagent_count: int = 0
    stop_reason: str = ""
    error: str = ""


@dataclass
class Step:
    name: str
    started: datetime
    ended: datetime
    size_bytes: int = 0
    detail: CallDetail | None = None

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

    @property
    def total_cost(self) -> float:
        return sum(s.detail.cost_usd for s in self.steps if s.detail)


# ---------------------------------------------------------------------------
# JSONL log parser
# ---------------------------------------------------------------------------

def parse_log(path: Path) -> CallDetail:
    """Parse a claude JSONL stdout log into a CallDetail.

    Content blocks from the same API response share identical usage
    values. We group them into one Turn by detecting when the usage
    signature (input_tokens, output_tokens, cache_read) changes.
    """
    detail = CallDetail()
    turn_num = 0
    current_turn: Turn | None = None
    prev_usage_sig: tuple[int, int, int] | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue

        etype = obj.get("type", "")

        # Result event — final summary
        if etype == "result":
            detail.duration_ms = obj.get("duration_ms", 0)
            detail.duration_api_ms = obj.get("duration_api_ms", 0)
            detail.num_turns = obj.get("num_turns", 0)
            detail.cost_usd = obj.get("total_cost_usd", 0.0)
            detail.stop_reason = obj.get("stop_reason", "")
            usage = obj.get("usage", {})
            detail.input_tokens = usage.get("input_tokens", 0)
            detail.cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)
            detail.cache_read_tokens = usage.get("cache_read_input_tokens", 0)
            detail.output_tokens = usage.get("output_tokens", 0)
            if obj.get("is_error"):
                detail.error = str(obj.get("error", "unknown error"))

        # Assistant message — one content block per line
        elif etype == "assistant":
            msg = obj.get("message", {})
            usage = msg.get("usage", {})
            usage_sig = (
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
                usage.get("cache_read_input_tokens", 0),
            )

            # New API response = new turn
            if usage_sig != prev_usage_sig:
                if current_turn is not None:
                    detail.turns.append(current_turn)
                turn_num += 1
                current_turn = Turn(turn_number=turn_num)
                current_turn.output_tokens = usage.get("output_tokens", 0)
                current_turn.input_tokens = usage.get("input_tokens", 0)
                current_turn.cache_read_tokens = usage.get("cache_read_input_tokens", 0)
                prev_usage_sig = usage_sig

            # Accumulate content blocks into the current turn
            for block in msg.get("content", []):
                bt = block.get("type", "")
                if bt == "thinking":
                    current_turn.thinking_chars += len(block.get("thinking", ""))
                elif bt == "text":
                    current_turn.text_chars += len(block.get("text", ""))
                elif bt == "tool_use":
                    name = block.get("name", "?")
                    inp = json.dumps(block.get("input", {}))
                    current_turn.tool_calls.append(ToolCall(
                        name=name,
                        input_size=len(inp),
                    ))
                    if name == "Agent":
                        detail.subagent_count += 1

    # Flush last turn
    if current_turn is not None:
        detail.turns.append(current_turn)

    return detail


# ---------------------------------------------------------------------------
# Workspace parser
# ---------------------------------------------------------------------------

def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _file_step(name: str, start_file: Path, end_file: Path,
               log_file: Path | None = None) -> Step | None:
    if not start_file.exists() or not end_file.exists():
        return None
    detail = None
    if log_file and log_file.exists() and log_file.stat().st_size > 0:
        detail = parse_log(log_file)
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
            step = _file_step("Skill-Selector",
                              stderr if stderr.exists() else log, log, log)
            if step:
                timeline.steps.append(step)
            break

    # Prelude
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
        pg_log = None
        # The prompt generator runs via a claude call — check for its log
        pg_logs_dir = phase_dir / "prompt-runner-files" / "logs"
        if pg_logs_dir.exists():
            for lg in pg_logs_dir.rglob("*.stdout.log"):
                pg_log = lg
                break
        step = Step(
            name="Prompt generator",
            started=prev.ended,
            ended=_mtime(prompt_file),
            size_bytes=prompt_file.stat().st_size,
            detail=parse_log(pg_log) if pg_log and pg_log.stat().st_size > 0 else None,
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
                        iter_log, iter_log,
                    )
                    if step:
                        timeline.steps.append(step)

                    judge_log = iter_log.with_name(f"iter-{iter_num}-judge.stdout.log")
                    judge_stderr = iter_log.with_name(f"iter-{iter_num}-judge.stderr.log")
                    if judge_log.exists():
                        step = _file_step(
                            f"{prompt_name} / iter {iter_num} judge",
                            judge_stderr if judge_stderr.exists() else judge_log,
                            judge_log, judge_log,
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
            for i in range(10):
                if (runs_dir / f"phase-{i}").exists() and pid.startswith(f"PH-00{i}"):
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


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def _bar_color(name: str) -> str:
    nl = name.lower()
    if "generator" in nl and "prompt generator" not in nl:
        return "#4a90d9"
    if "judge" in nl:
        return "#e67e22"
    if "selector" in nl:
        return "#27ae60"
    if "prompt generator" in nl:
        return "#8e44ad"
    if "cross-ref" in nl:
        return "#c0392b"
    if "prelude" in nl:
        return "#27ae60"
    return "#95a5a6"


def _render_detail(detail: CallDetail) -> str:
    """Render the drill-down section for one call."""
    if not detail or (not detail.turns and not detail.duration_ms):
        return ""

    parts = ['<div class="detail">']

    # Summary line
    api_s = detail.duration_api_ms / 1000
    wall_s = detail.duration_ms / 1000
    overhead_s = wall_s - api_s
    overall_tok_s = detail.output_tokens / api_s if api_s > 0 else 0
    parts.append(
        f'<div class="detail-summary">'
        f'API: {api_s:.0f}s'
        f' | overhead: {overhead_s:.1f}s'
        f' | turns: {detail.num_turns}'
        f' | out: {detail.output_tokens:,} tok'
        f' | {overall_tok_s:.0f} tok/s'
        f' | cost: ${detail.cost_usd:.2f}'
    )
    if detail.subagent_count:
        parts.append(f' | <span class="warn">subagents: {detail.subagent_count}</span>')
    parts.append('</div>')

    # Token bar
    total_tok = (detail.cache_creation_tokens + detail.cache_read_tokens
                 + detail.input_tokens + detail.output_tokens) or 1
    parts.append('<div class="token-bar">')
    for label, count, color in [
        ("cache-read", detail.cache_read_tokens, "#3498db"),
        ("cache-create", detail.cache_creation_tokens, "#2ecc71"),
        ("input", detail.input_tokens, "#95a5a6"),
        ("output", detail.output_tokens, "#e74c3c"),
    ]:
        if count > 0:
            pct = count / total_tok * 100
            parts.append(
                f'<div class="tok-seg" style="width:{pct:.1f}%;background:{color}" '
                f'title="{label}: {count:,}"></div>'
            )
    parts.append('</div>')
    parts.append(
        f'<div class="token-legend">'
        f'cache-read: {detail.cache_read_tokens:,} '
        f'| cache-create: {detail.cache_creation_tokens:,} '
        f'| fresh-input: {detail.input_tokens:,} '
        f'| output: {detail.output_tokens:,}'
        f'</div>'
    )

    # Per-turn table
    if detail.turns:
        parts.append('<table class="turns">')
        parts.append(
            '<tr><th>Turn</th><th>Thinking</th><th>Text</th>'
            '<th>Out tok</th><th>Time</th><th>tok/s</th>'
            '<th>Tools</th></tr>'
        )
        # Estimate per-turn time by dividing total API time proportionally
        # by output tokens (rough but better than nothing)
        total_out = sum(t.output_tokens for t in detail.turns) or 1
        for turn in detail.turns:
            tools_str = ", ".join(
                f'{tc.name}({tc.input_size // 4}tok)'
                for tc in turn.tool_calls
            ) or "—"
            thinking_cls = ' class="big-think"' if turn.thinking_chars > 5000 else ""
            # Estimate this turn's share of API time
            turn_frac = turn.output_tokens / total_out if total_out else 0
            turn_time_s = (detail.duration_api_ms / 1000) * turn_frac
            tok_per_s = turn.output_tokens / turn_time_s if turn_time_s > 0 else 0
            parts.append(
                f'<tr>'
                f'<td>{turn.turn_number}</td>'
                f'<td{thinking_cls}>{turn.thinking_chars:,}</td>'
                f'<td>{turn.text_chars:,}</td>'
                f'<td>{turn.output_tokens:,}</td>'
                f'<td>{turn_time_s:.0f}s</td>'
                f'<td>{tok_per_s:.0f}</td>'
                f'<td class="tool-detail">{tools_str}</td>'
                f'</tr>'
            )
        parts.append('</table>')

    parts.append('</div>')
    return "\n".join(parts)


def render_html(timelines: list[PhaseTimeline], workspace: Path) -> str:
    rows = []
    grand_total = sum(t.total_seconds for t in timelines) or 1
    grand_cost = sum(t.total_cost for t in timelines)

    for tl in timelines:
        rows.append(
            f'<tr class="phase-header"><td colspan="5">'
            f'<strong>{tl.phase_id}</strong> — {tl.total_str}'
            f' — ${tl.total_cost:.2f}'
            f'</td></tr>'
        )
        for step in tl.steps:
            pct = (step.duration_seconds / grand_total * 100)
            color = _bar_color(step.name)
            size_kb = step.size_bytes / 1024
            cost_str = f"${step.detail.cost_usd:.2f}" if step.detail else ""
            detail_html = _render_detail(step.detail) if step.detail else ""
            rows.append(
                f'<tr class="step-row">'
                f'<td class="step-name">{step.name}</td>'
                f'<td class="step-time">{step.duration_str}</td>'
                f'<td class="step-cost">{cost_str}</td>'
                f'<td class="step-size">{size_kb:.0f}KB</td>'
                f'<td class="step-bar">'
                f'<div class="bar" style="width:{max(pct, 0.5):.1f}%;background:{color}">'
                f'</div></td>'
                f'</tr>'
            )
            if detail_html:
                rows.append(
                    f'<tr class="detail-row"><td colspan="5">{detail_html}</td></tr>'
                )

    grand_m, grand_s = divmod(int(grand_total), 60)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Timeline — {workspace.name}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 2em; background: #fafafa; color: #333; }}
  h1 {{ font-size: 1.4em; }}
  h2 {{ font-size: 1.1em; color: #555; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 1000px; }}
  tr.phase-header td {{ background: #eee; padding: 8px 12px; font-size: 1.05em; border-top: 2px solid #ccc; }}
  tr.step-row td {{ padding: 4px 12px; vertical-align: middle; }}
  tr.detail-row td {{ padding: 0 12px 12px 24px; }}
  .step-name {{ width: 38%; font-size: 0.9em; }}
  .step-time {{ width: 7%; text-align: right; font-family: monospace; font-size: 0.9em; }}
  .step-cost {{ width: 7%; text-align: right; font-family: monospace; font-size: 0.85em; color: #666; }}
  .step-size {{ width: 6%; text-align: right; font-family: monospace; font-size: 0.85em; color: #888; }}
  .step-bar {{ width: 32%; }}
  .bar {{ height: 18px; border-radius: 3px; min-width: 4px; }}
  .legend {{ display: flex; gap: 1.5em; margin: 1em 0; font-size: 0.85em; flex-wrap: wrap; }}
  .legend-item {{ display: flex; align-items: center; gap: 0.4em; }}
  .legend-swatch {{ width: 14px; height: 14px; border-radius: 2px; }}

  .detail {{ background: #f5f5f5; border-radius: 6px; padding: 10px 14px; font-size: 0.85em; margin-top: 4px; }}
  .detail-summary {{ margin-bottom: 6px; color: #555; }}
  .warn {{ color: #e74c3c; font-weight: bold; }}

  .token-bar {{ display: flex; height: 10px; border-radius: 3px; overflow: hidden; margin: 4px 0; max-width: 600px; }}
  .tok-seg {{ height: 100%; }}
  .token-legend {{ font-size: 0.8em; color: #777; margin-bottom: 6px; }}

  table.turns {{ width: 100%; max-width: 700px; font-size: 0.85em; margin-top: 6px; }}
  table.turns th {{ text-align: left; padding: 2px 8px; border-bottom: 1px solid #ddd; color: #666; font-weight: normal; }}
  table.turns td {{ padding: 2px 8px; }}
  .big-think {{ color: #e74c3c; font-weight: bold; }}
  .tool-detail {{ color: #888; font-size: 0.9em; }}
</style>
</head>
<body>
<h1>Methodology Runner Timeline</h1>
<h2>{workspace} — total {grand_m}m{grand_s:02d}s — ${grand_cost:.2f}</h2>
<div class="legend">
  <div class="legend-item"><div class="legend-swatch" style="background:#27ae60"></div> Selector/Prelude</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#8e44ad"></div> Prompt Generator</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#4a90d9"></div> Generator (claude)</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#e67e22"></div> Judge (claude)</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#c0392b"></div> Cross-ref</div>
</div>
<div class="legend">
  Token bar: <div class="legend-item"><div class="legend-swatch" style="background:#3498db"></div> cache-read</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#2ecc71"></div> cache-create</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#95a5a6"></div> fresh-input</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#e74c3c"></div> output</div>
</div>
<table>
{''.join(rows)}
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate timeline report for a methodology-runner workspace.")
    parser.add_argument("workspace", help="Path to the methodology-runner workspace directory.")
    parser.add_argument("--output", "-o", default=None, help="Output HTML path.")
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
