#!/usr/bin/env python3
"""Generate an HTML timeline report for a methodology-runner workspace or
a prompt-runner run directory (with or without variant forks).

Parses JSONL logs to show:
- Per-phase/prompt wall time breakdown
- Per-call drill-down: turns, thinking, tool calls, subagent spawns
- Token usage and cost per call
- Visual bars proportional to time spent
- Fork comparison tables with delta rows when variants are present

Usage:
    python scripts/run-timeline.py <path> [--output report.html]

The path can be:
  - A methodology-runner workspace (contains .methodology-runner/runs/)
  - A prompt-runner run directory (contains logs/ and/or manifest.json)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POPUP_TRUNCATE_CHARS = 20_000_000  # 20 MB
MIN_BAR_PCT = 0.5


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    name: str
    input_size: int  # chars — LLM output (tool_use input JSON)
    result_size: int = 0  # chars — tool response (tool_result content)
    input_json: str = ""  # raw tool_use input JSON (for file path extraction)
    result_content: str = ""  # raw tool_result content (for popup display)
    tool_use_id: str = ""  # for matching tool_use to tool_result


@dataclass
class Turn:
    turn_number: int
    thinking_chars: int = 0
    text_chars: int = 0
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    start_ts: str = ""  # ISO timestamp from preceding user event
    end_ts: str = ""    # ISO timestamp from following user event

    @property
    def duration_seconds(self) -> float:
        if not self.start_ts or not self.end_ts:
            return 0
        from datetime import datetime, timezone
        try:
            t0 = datetime.fromisoformat(self.start_ts.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(self.end_ts.replace("Z", "+00:00"))
            return (t1 - t0).total_seconds()
        except (ValueError, TypeError):
            return 0

    @property
    def tool_write_chars(self) -> int:
        """Total chars the LLM sent TO tools (tool_use input)."""
        return sum(tc.input_size for tc in self.tool_calls)

    @property
    def tool_read_chars(self) -> int:
        """Total chars received FROM tools (tool_result content)."""
        return sum(tc.result_size for tc in self.tool_calls)


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
    model: str = ""
    prompt_text: str = ""   # initial user message content
    output_text: str = ""   # concatenated assistant text blocks


@dataclass
class Step:
    name: str
    started: datetime
    ended: datetime
    size_bytes: int = 0
    detail: CallDetail | None = None
    log_path: Path | None = None  # path to the .stdout.log JSONL file

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


@dataclass
class ForkSection:
    """A fork point with its variants, each containing their own steps."""
    fork_index: int
    fork_title: str
    variants: dict[str, list[Step]]  # variant_name -> steps


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
    last_was_assistant = False
    # Map tool_use_id -> ToolCall so we can attach result sizes
    pending_tools: dict[str, ToolCall] = {}
    # Track the last user-event timestamp for turn timing
    last_user_ts: str = ""

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
            last_was_assistant = False

        # Assistant message — one content block per line
        elif etype == "assistant":
            msg = obj.get("message", {})
            if not detail.model and "model" in msg:
                detail.model = msg["model"]
            usage = msg.get("usage", {})
            usage_sig = (
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
                usage.get("cache_read_input_tokens", 0),
            )

            # New turn if: usage changed OR there was a non-assistant
            # line in between (consecutive check)
            is_new_turn = (
                usage_sig != prev_usage_sig or not last_was_assistant
            )
            if is_new_turn:
                if current_turn is not None:
                    detail.turns.append(current_turn)
                turn_num += 1
                current_turn = Turn(turn_number=turn_num)
                current_turn.output_tokens = usage.get("output_tokens", 0)
                current_turn.input_tokens = usage.get("input_tokens", 0)
                current_turn.cache_read_tokens = usage.get("cache_read_input_tokens", 0)
                current_turn.start_ts = last_user_ts
                prev_usage_sig = usage_sig
            last_was_assistant = True

            # Accumulate content blocks into the current turn
            for block in msg.get("content", []):
                bt = block.get("type", "")
                if bt == "thinking":
                    current_turn.thinking_chars += len(block.get("thinking", ""))
                elif bt == "text":
                    txt = block.get("text", "")
                    current_turn.text_chars += len(txt)
                    detail.output_text += txt
                elif bt == "tool_use":
                    name = block.get("name", "?")
                    inp = json.dumps(block.get("input", {}))
                    tool_id = block.get("id", "")
                    tc = ToolCall(
                        name=name,
                        input_size=len(inp),
                        input_json=inp,
                        tool_use_id=tool_id,
                    )
                    current_turn.tool_calls.append(tc)
                    if tool_id:
                        pending_tools[tool_id] = tc
                    if name == "Agent":
                        detail.subagent_count += 1

        # User message — look for tool_result blocks and capture timestamp
        elif etype == "user":
            ts = obj.get("timestamp", "")
            if ts and current_turn is not None and not current_turn.end_ts:
                current_turn.end_ts = ts
            if ts:
                last_user_ts = ts
            msg = obj.get("message", {})
            # Capture the initial prompt (first user text content)
            if not detail.prompt_text:
                for block in msg.get("content", []):
                    if block.get("type") == "text":
                        detail.prompt_text = block.get("text", "")
                        break
            for block in msg.get("content", []):
                if block.get("type") == "tool_result":
                    tool_id = block.get("tool_use_id", "")
                    content = block.get("content", "")
                    content_str = str(content)
                    result_len = len(content_str)
                    tc = pending_tools.get(tool_id)
                    if tc is not None:
                        tc.result_size = result_len
                        tc.result_content = content_str
            last_was_assistant = False

        else:
            last_was_assistant = False

    # Flush last turn
    if current_turn is not None:
        detail.turns.append(current_turn)

    return detail


# ---------------------------------------------------------------------------
# Shared step-building helpers
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
        log_path=log_file,
    )


# ---------------------------------------------------------------------------
# Methodology-runner workspace parser
# ---------------------------------------------------------------------------

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

    # Backfill missing prompts from the phase's prompt-file.md
    prompt_file = phase_dir / "prompt-file.md"
    if prompt_file.exists():
        _backfill_prompts_from_file(timeline, prompt_file)

    return timeline if timeline.steps else None


def _backfill_prompts_from_file(timeline: PhaseTimeline, prompt_file: Path) -> None:
    """For generator/judge steps missing prompt_text, extract it from the
    phase's prompt-runner .md file by matching the prompt slug in the step name."""
    import re
    try:
        content = prompt_file.read_text(encoding="utf-8")
    except OSError:
        return

    # Parse prompt sections: ## Prompt N: <title> followed by code blocks
    sections: dict[str, str] = {}
    current_slug = ""
    current_lines: list[str] = []
    for line in content.splitlines():
        m = re.match(r"^## Prompt\s+\d+", line)
        if m:
            if current_slug and current_lines:
                sections[current_slug] = "\n".join(current_lines)
            # Build a slug from the heading to match step names
            slug = re.sub(r"[^a-z0-9]+", "-", line.lower()).strip("-")
            # Remove the "prompt-NN-" prefix to get the descriptive part
            slug = re.sub(r"^-*prompt-\d+-", "", slug)
            current_slug = slug
            current_lines = [line]
        elif current_slug:
            current_lines.append(line)
    if current_slug and current_lines:
        sections[current_slug] = "\n".join(current_lines)

    for step in timeline.steps:
        if step.detail and not step.detail.prompt_text:
            # Try to match step name slug to a section
            step_slug = re.sub(r"\s*/\s*iter.*$", "", step.name)
            step_slug = re.sub(r"[^a-z0-9]+", "-", step_slug.lower()).strip("-")
            is_judge = "judge" in step.name.lower()
            for section_slug, section_text in sections.items():
                matched = (
                    (section_slug and section_slug in step_slug) or
                    (step_slug and step_slug in section_slug)
                )
                if matched:
                    gen, val = _split_prompt_fences(section_text)
                    step.detail.prompt_text = val if is_judge else gen
                    break


def _split_prompt_fences(text: str) -> tuple[str, str]:
    """Split a prompt section into (generation_prompt, validation_prompt).

    The section text from a synthetic-prompt.md has a heading, then two
    code-fenced blocks. Extract the content inside each fence.
    Returns (gen, val) where val may be empty if there's only one fence.
    """
    import re
    fences = re.findall(r'```[^\n]*\n(.*?)```', text, re.DOTALL)
    gen = fences[0].strip() if len(fences) >= 1 else text
    val = fences[1].strip() if len(fences) >= 2 else ""
    return gen, val


def _backfill_prompts_from_synthetic(steps: list[Step], synth_path: Path) -> None:
    """Backfill missing prompt_text from a synthetic-prompt.md file.

    The synthetic file contains the variant's prompts + tail prompts.
    Parse sections and match by slug like _backfill_prompts_from_file.
    """
    import re
    try:
        content = synth_path.read_text(encoding="utf-8")
    except OSError:
        return

    sections: dict[str, str] = {}
    current_slug = ""
    current_lines: list[str] = []
    for line in content.splitlines():
        m = re.match(r"^## Prompt\s+\d+", line)
        if m:
            if current_slug and current_lines:
                sections[current_slug] = "\n".join(current_lines)
            slug = re.sub(r"[^a-z0-9]+", "-", line.lower()).strip("-")
            slug = re.sub(r"^-*prompt-\d+-", "", slug)
            current_slug = slug
            current_lines = [line]
        elif current_slug:
            current_lines.append(line)
    if current_slug and current_lines:
        sections[current_slug] = "\n".join(current_lines)

    for step in steps:
        if step.detail and not step.detail.prompt_text:
            step_slug = re.sub(r"\s*/\s*iter.*$", "", step.name)
            step_slug = re.sub(r"[^a-z0-9]+", "-", step_slug.lower()).strip("-")
            is_judge = "judge" in step.name.lower()
            for section_slug, section_text in sections.items():
                matched = (
                    (section_slug and section_slug in step_slug) or
                    (step_slug and step_slug in section_slug)
                )
                if matched:
                    gen, val = _split_prompt_fences(section_text)
                    step.detail.prompt_text = val if is_judge else gen
                    break


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
# Prompt-runner run directory parser
# ---------------------------------------------------------------------------

def _parse_prompt_log_dir(logs_dir: Path, prefix: str = "") -> list[Step]:
    """Parse all prompt-*/iter-* logs under a logs/ directory into Steps."""
    steps: list[Step] = []
    if not logs_dir.exists():
        return steps
    for prompt_dir in sorted(logs_dir.iterdir()):
        if not prompt_dir.is_dir():
            continue
        prompt_name = (prefix + prompt_dir.name) if prefix else prompt_dir.name
        for iter_log in sorted(prompt_dir.glob("iter-*-generator.stdout.log")):
            iter_num = iter_log.name.split("-")[1]
            stderr = iter_log.with_name(f"iter-{iter_num}-generator.stderr.log")
            step = _file_step(
                f"{prompt_name} / iter {iter_num} generator",
                stderr if stderr.exists() else iter_log,
                iter_log, iter_log,
            )
            if step:
                steps.append(step)

            judge_log = iter_log.with_name(f"iter-{iter_num}-judge.stdout.log")
            judge_stderr = iter_log.with_name(f"iter-{iter_num}-judge.stderr.log")
            if judge_log.exists():
                step = _file_step(
                    f"{prompt_name} / iter {iter_num} judge",
                    judge_stderr if judge_stderr.exists() else judge_log,
                    judge_log, judge_log,
                )
                if step:
                    steps.append(step)
    return steps


def parse_prompt_runner_run(run_dir: Path) -> tuple[list[Step], list[ForkSection]]:
    """Parse a prompt-runner run directory into shared steps and fork sections."""
    shared_steps: list[Step] = []
    fork_sections: list[ForkSection] = []

    # Shared pre-fork steps from top-level logs/
    top_logs = run_dir / "logs"
    shared_steps = _parse_prompt_log_dir(top_logs)

    # Fork sections from fork-*/ directories
    for fork_dir in sorted(run_dir.iterdir()):
        if not fork_dir.is_dir() or not fork_dir.name.startswith("fork-"):
            continue

        # Extract fork index and title from directory name (e.g. "fork-02-audit-the-requirements-inventory")
        parts = fork_dir.name.split("-", 2)
        try:
            fork_index = int(parts[1])
        except (IndexError, ValueError):
            fork_index = 0
        fork_title = parts[2].replace("-", " ").title() if len(parts) > 2 else fork_dir.name

        variants: dict[str, list[Step]] = {}

        # Each variant-*/ directory contains run-*/logs/
        for variant_dir in sorted(fork_dir.iterdir()):
            if not variant_dir.is_dir() or not variant_dir.name.startswith("variant-"):
                continue
            variant_name = variant_dir.name  # e.g. "variant-a"

            # Find the run-*/ subdirectory
            variant_steps: list[Step] = []
            for run_subdir in sorted(variant_dir.iterdir()):
                if not run_subdir.is_dir() or not run_subdir.name.startswith("run-"):
                    continue
                variant_logs = run_subdir / "logs"
                variant_steps.extend(_parse_prompt_log_dir(variant_logs))

            # Backfill prompts from synthetic-prompt.md if steps lack prompt_text
            for run_subdir in sorted(variant_dir.iterdir()):
                if not run_subdir.is_dir() or not run_subdir.name.startswith("run-"):
                    continue
                # Try synthetic-prompt.md in the variant dir (sibling of run-*)
                synth = variant_dir / "synthetic-prompt.md"
                if synth.exists():
                    _backfill_prompts_from_synthetic(variant_steps, synth)
                break

            if variant_steps:
                variants[variant_name] = variant_steps

        if variants:
            fork_sections.append(ForkSection(
                fork_index=fork_index,
                fork_title=fork_title,
                variants=variants,
            ))

    return shared_steps, fork_sections


# ---------------------------------------------------------------------------
# HTML renderer helpers
# ---------------------------------------------------------------------------

def _model_abbrev(model: str) -> str:
    """Shorten model name to a letter: o=opus, s=sonnet, h=haiku."""
    m = model.lower()
    if "opus" in m:
        return "o"
    if "sonnet" in m:
        return "s"
    if "haiku" in m:
        return "h"
    return model[:10] if model else "?"


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


_POPUP_COUNTER = [0]


def _format_block(text: str) -> str:
    """Auto-detect content type and return formatted HTML."""
    import re
    stripped = text.strip()
    if not stripped:
        return _escape_html(text)

    # JSON
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            import json as _j2
            parsed = _j2.loads(stripped)
            pretty = _j2.dumps(parsed, indent=2, ensure_ascii=False)
            return _escape_html(pretty[:POPUP_TRUNCATE_CHARS])
        except (ValueError, TypeError):
            pass

    # YAML — detect by common patterns
    lines = stripped.splitlines()
    yaml_signals = sum(1 for l in lines[:20] if (
        re.match(r'^\s*[\w_-]+\s*:', l) or
        l.strip().startswith("- ") or
        l.strip() == "---"
    ))
    if yaml_signals >= 3 or (yaml_signals >= 1 and len(lines) <= 5):
        out = []
        for line in _escape_html(text).splitlines():
            if re.match(r'^(\s*)(\S.*?):', line):
                m = re.match(r'^(\s*)(\S.*?)(:.*)', line)
                if m:
                    out.append(f'{m.group(1)}<span style="color:#2980b9;font-weight:bold">{m.group(2)}</span>{m.group(3)}')
                    continue
            if line.strip().startswith("- "):
                out.append(f'<span style="color:#27ae60">{line}</span>')
                continue
            out.append(line)
        return chr(10).join(out)

    # Markdown — detect by headers, bold, lists
    md_signals = sum(1 for l in lines[:30] if (
        l.startswith("#") or
        l.startswith("- ") or
        l.startswith("* ") or
        "**" in l
    ))
    if md_signals >= 2:
        md = _escape_html(text)
        md = re.sub(r'^(#{1,4}) (.+)$',
                    r'<span style="color:#8e44ad;font-weight:bold">\1 \2</span>',
                    md, flags=re.MULTILINE)
        md = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', md)
        md = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', md)
        md = re.sub(r'^(\s*[-*] )(.+)$',
                    r'<span style="color:#27ae60">\1</span>\2',
                    md, flags=re.MULTILINE)
        return md

    # Plain text
    return _escape_html(text)


def _popup_content(popup_id: str, text: str) -> str:
    """Render a popup content area with formatted/raw toggle.

    Splits on '--- Section ---' markers and formats each section
    independently. Auto-detects JSON, YAML, and Markdown.
    """
    import re
    _POPUP_COUNTER[0] += 1
    uid = f"pcontent-{_POPUP_COUNTER[0]}"
    truncated = _truncate(text)
    raw_html = f'<pre class="popup-raw">{_escape_html(truncated)}</pre>'

    # Split on section markers (--- Label ---) and format each part
    section_re = re.compile(r'^(---\s*.+?\s*---)$', re.MULTILINE)
    parts = section_re.split(truncated)

    formatted_parts = []
    has_formatting = False
    for part in parts:
        if section_re.match(part.strip()):
            # Section header — render as a styled divider
            formatted_parts.append(
                f'<span style="color:#666;font-weight:bold">{_escape_html(part)}</span>'
            )
        else:
            formatted = _format_block(part)
            if formatted != _escape_html(part):
                has_formatting = True
            formatted_parts.append(formatted)

    if not has_formatting:
        # Nothing was formatted differently from raw — try the whole text
        whole_formatted = _format_block(truncated)
        if whole_formatted != _escape_html(truncated):
            has_formatting = True
            formatted_parts = [whole_formatted]

    if not has_formatting:
        return raw_html

    formatted_html = f'<pre class="popup-formatted">{chr(10).join(formatted_parts) if len(formatted_parts) > 1 else formatted_parts[0]}</pre>'

    return (
        f'<div id="{uid}" class="popup-dual">'
        f'<button class="toggle-btn" onclick="toggleView(\'{uid}\')">raw</button>'
        f'<div class="view-formatted">{formatted_html}</div>'
        f'<div class="view-raw" style="display:none">{raw_html}</div>'
        f'</div>'
    )


def _render_log_structured(log_path: Path, popup_id: str) -> str:
    """Render a JSONL log file as structured HTML with per-record formatting."""
    import json as _jlog

    uid = f"pcontent-{popup_id}"
    items: list[str] = []

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return '<pre>(cannot read log)</pre>'

    raw_text = log_path.read_text(encoding="utf-8", errors="replace")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = _jlog.loads(line)
        except (ValueError, TypeError):
            items.append(f'<div class="log-unknown">{_escape_html(line[:500])}</div>')
            continue

        t = obj.get("type", "?")
        st = obj.get("subtype", "")
        key = f"{t}/{st}" if st else t

        if t == "system" and st == "init":
            model = obj.get("model", "?")
            sid = obj.get("session_id", "?")
            cwd = obj.get("cwd", "?")
            tools = obj.get("tools", [])
            items.append(
                f'<div class="log-system">'
                f'<span class="log-type">INIT</span> '
                f'model=<strong>{_escape_html(model)}</strong> '
                f'session={sid}… '
                f'cwd={_escape_html(str(cwd)[-40:])} '
                f'tools={len(tools)}'
                f'</div>'
            )

        elif t == "system" and "hook" in st:
            hook = obj.get("hook_name", "?")
            event = obj.get("hook_event", "?")
            if st == "hook_started":
                items.append(
                    f'<div class="log-system">'
                    f'<span class="log-type">HOOK▶</span> {_escape_html(hook)}'
                    f'</div>'
                )
            else:
                output = obj.get("output", "")
                preview = _escape_html(output[:200]).replace("\n", " ")
                items.append(
                    f'<div class="log-system">'
                    f'<span class="log-type">HOOK✓</span> {_escape_html(hook)} '
                    f'<span class="log-dim">({len(output):,}ch)</span>'
                    f'</div>'
                )

        elif t == "assistant":
            msg = obj.get("message", {})
            model = msg.get("model", "")
            usage = msg.get("usage", {})
            out_tok = usage.get("output_tokens", "?")
            cache = usage.get("cache_read_input_tokens", 0)
            for block in msg.get("content", []):
                bt = block.get("type", "?")
                if bt == "thinking":
                    text = block.get("thinking", "")
                    preview = _escape_html(text[:150]).replace("\n", " ")
                    items.append(
                        f'<div class="log-thinking">'
                        f'<span class="log-type">THINK</span> '
                        f'<span class="log-dim">{len(text):,}ch</span> '
                        f'{preview}…'
                        f'</div>'
                    )
                elif bt == "text":
                    text = block.get("text", "")
                    preview = _escape_html(text[:200]).replace("\n", " ")
                    items.append(
                        f'<div class="log-text">'
                        f'<span class="log-type">TEXT</span> '
                        f'<span class="log-dim">{len(text):,}ch</span> '
                        f'{preview}{"…" if len(text) > 200 else ""}'
                        f'</div>'
                    )
                elif bt == "tool_use":
                    name = block.get("name", "?")
                    inp = block.get("input", {})
                    fpath = inp.get("file_path", "") or inp.get("path", "") or inp.get("pattern", "") or inp.get("command", "")[:60]
                    fname = fpath.split("/")[-1] if fpath else ""
                    inp_size = len(_jlog.dumps(inp))
                    items.append(
                        f'<div class="log-tool">'
                        f'<span class="log-type">TOOL→</span> '
                        f'<strong>{_escape_html(name)}</strong>'
                        f'{"(" + _escape_html(fname) + ")" if fname else ""} '
                        f'<span class="log-dim">{inp_size:,}ch</span>'
                        f'</div>'
                    )

        elif t == "user":
            ts = obj.get("timestamp", "")
            msg = obj.get("message", {})
            for block in msg.get("content", []):
                bt = block.get("type", "?")
                if bt == "tool_result":
                    content = str(block.get("content", ""))
                    preview = _escape_html(content[:150]).replace("\n", " ")
                    items.append(
                        f'<div class="log-result">'
                        f'<span class="log-type">→TOOL</span> '
                        f'<span class="log-dim">{len(content):,}ch</span> '
                        f'{preview}{"…" if len(content) > 150 else ""}'
                        f'{"  <span class=log-ts>" + ts[-12:] + "</span>" if ts else ""}'
                        f'</div>'
                    )
                elif bt == "text":
                    text = block.get("text", "")
                    items.append(
                        f'<div class="log-text">'
                        f'<span class="log-type">USER</span> '
                        f'<span class="log-dim">{len(text):,}ch</span>'
                        f'</div>'
                    )

        elif t == "rate_limit_event":
            items.append(
                f'<div class="log-system">'
                f'<span class="log-type">RATE</span> rate limit event'
                f'</div>'
            )

        elif "result" in t:
            dur = obj.get("duration_ms", 0) / 1000
            cost = obj.get("total_cost_usd", 0)
            turns = obj.get("num_turns", 0)
            stop = obj.get("stop_reason", "?")
            u = obj.get("usage", {})
            out_tok = u.get("output_tokens", 0)
            cache_read = u.get("cache_read_input_tokens", 0)
            cache_create = u.get("cache_creation_input_tokens", 0)
            is_err = obj.get("is_error", False)
            cls = "log-error" if is_err else "log-result-final"
            errors = obj.get("errors", [])
            items.append(
                f'<div class="{cls}">'
                f'<span class="log-type">{"ERROR" if is_err else "DONE"}</span> '
                f'{dur:.0f}s | ${cost:.2f} | {turns} turns | '
                f'out={out_tok:,} | cache-read={cache_read:,} | '
                f'cache-create={cache_create:,} | stop={stop}'
                f'{"<br>Errors: " + _escape_html("; ".join(errors)) if errors else ""}'
                f'</div>'
            )
        else:
            items.append(
                f'<div class="log-unknown">'
                f'<span class="log-type">{_escape_html(key)}</span> '
                f'<span class="log-dim">{len(line):,}B</span>'
                f'</div>'
            )

    formatted = "\n".join(items)
    raw_html = f'<pre class="popup-raw">{_escape_html(raw_text[:POPUP_TRUNCATE_CHARS])}</pre>'

    return (
        f'<div id="{uid}" class="popup-dual">'
        f'<button class="toggle-btn" onclick="toggleView(\'{uid}\')">raw</button>'
        f'<div class="view-formatted"><div class="log-structured">{formatted}</div></div>'
        f'<div class="view-raw" style="display:none">{raw_html}</div>'
        f'</div>'
    )


def _tool_file_path(tc: ToolCall) -> str:
    """Extract a file path from a Read/Write/Glob tool call's input JSON."""
    try:
        import json as _j
        inp = _j.loads(tc.input_json)
        return inp.get("file_path", "") or inp.get("path", "") or inp.get("pattern", "") or inp.get("command", "")[:80]
    except (ValueError, TypeError):
        return ""


def _render_detail(detail: CallDetail, step_id: str = "", popups: list | None = None) -> str:
    """Render the drill-down section for one call."""
    if not detail or (not detail.turns and not detail.duration_ms):
        return ""

    parts = ['<div class="detail">']

    # Summary line
    api_s = detail.duration_api_ms / 1000
    wall_s = detail.duration_ms / 1000
    overhead_s = wall_s - api_s
    overall_tok_s = detail.output_tokens / api_s if api_s > 0 else 0
    model_abbr = _model_abbrev(detail.model)
    parts.append(
        f'<div class="detail-summary">'
        f'{model_abbr}'
        f' | API: {api_s:.0f}s'
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
            '<tr><th>Turn</th><th>Think</th><th>Text</th>'
            '<th>Output</th><th>Time</th><th>tok/s</th>'
            '<th>Tools</th></tr>'
        )
        tool_popup_counter = 0
        for turn in detail.turns:
            tool_parts = []
            for tc in turn.tool_calls:
                file_path = _tool_file_path(tc)
                filename = file_path.split("/")[-1] if file_path else ""
                if filename and tc.name in ("Read", "Write", "Edit"):
                    label = f'{tc.name}({filename} {tc.input_size:,}→/→{tc.result_size:,})'
                else:
                    label = f'{tc.name}({tc.input_size:,}→/→{tc.result_size:,})'
                # Add popup link if there's meaningful content
                has_content = (tc.input_json and tc.input_size > 10) or tc.result_content
                if has_content and step_id and popups is not None:
                    tool_popup_counter += 1
                    popup_id = f"{step_id}-tool-{tool_popup_counter}"
                    short_path = file_path.split("/")[-1] if file_path else tc.name
                    link = f'<a href="#" onclick="showPopup(\'{popup_id}\');return false">{label}</a>'
                    tool_parts.append(link)
                    # Build popup content: input + result
                    popup_lines = []
                    if file_path:
                        popup_lines.append(f"Path: {file_path}\n")
                    if tc.name in ("Read", "Write", "Edit", "Bash", "Grep", "Glob"):
                        if tc.input_json:
                            # For Write/Edit: extract and unescape the content
                            # field so it renders as formatted YAML/JSON/etc
                            # instead of a JSON blob with \n escapes.
                            display_input = tc.input_json[:POPUP_TRUNCATE_CHARS]
                            if tc.name in ("Write", "Edit") and tc.input_json:
                                try:
                                    import json as _jtool
                                    inp_obj = _jtool.loads(tc.input_json)
                                    file_content = inp_obj.get("content", "")
                                    if file_content:
                                        other_fields = {k: v for k, v in inp_obj.items() if k != "content"}
                                        header = _jtool.dumps(other_fields, indent=2)
                                        display_input = f"{header}\n\n--- File content ---\n{file_content[:POPUP_TRUNCATE_CHARS]}"
                                except (ValueError, TypeError):
                                    pass
                            popup_lines.append(f"--- Input ({tc.input_size:,} chars) ---\n{display_input}\n")
                        if tc.result_content:
                            popup_lines.append(f"--- Result ({tc.result_size:,} chars) ---\n{tc.result_content[:POPUP_TRUNCATE_CHARS]}\n")
                    else:
                        popup_lines.append(f"Input: {tc.input_size:,} chars | Result: {tc.result_size:,} chars")
                    popups.append(
                        f'<div id="{popup_id}" class="popup">'
                        f'<div class="popup-header">'
                        f'<strong>{tc.name}: {_escape_html(short_path)}</strong>'
                        f'<a href="#" onclick="hidePopup(\'{popup_id}\');return false">close</a>'
                        f'</div>'
                        f'{_popup_content(popup_id, chr(10).join(popup_lines))}'
                        f'</div>'
                    )
                else:
                    tool_parts.append(label)
            tools_str = ", ".join(tool_parts) or "—"
            thinking_cls = ' class="big-think"' if turn.thinking_chars > 5000 else ""
            est_tok = (turn.thinking_chars + turn.text_chars + turn.tool_write_chars) // 4
            dur = turn.duration_seconds
            if dur < 1 and dur > 0:
                # Sub-second turn: clamp tok/s to output estimate
                tok_s = est_tok
            elif dur > 0:
                tok_s = est_tok / dur
            else:
                tok_s = 0
            dur_str = f"{dur:.0f}s" if dur > 0 else "—"
            tok_s_str = f"{tok_s:.0f}" if dur > 0 else "—"
            parts.append(
                f'<tr>'
                f'<td>{turn.turn_number}</td>'
                f'<td{thinking_cls}>{turn.thinking_chars:,}</td>'
                f'<td>{turn.text_chars:,}</td>'
                f'<td>{est_tok:,}</td>'
                f'<td>{dur_str}</td>'
                f'<td>{tok_s_str}</td>'
                f'<td class="tool-detail">{tools_str}</td>'
                f'</tr>'
            )
        # Totals row
        tot_think = sum(t.thinking_chars for t in detail.turns)
        tot_text = sum(t.text_chars for t in detail.turns)
        tot_est = sum(
            (t.thinking_chars + t.text_chars + t.tool_write_chars) // 4
            for t in detail.turns
        )
        parts.append(
            f'<tr style="border-top:1px solid #ccc;font-weight:bold">'
            f'<td>Total</td>'
            f'<td>{tot_think:,}</td>'
            f'<td>{tot_text:,}</td>'
            f'<td>{tot_est:,}</td>'
            f'<td>{api_s:.0f}s</td>'
            f'<td>{overall_tok_s:.0f}</td>'
            f'<td></td>'
            f'</tr>'
        )
        parts.append('</table>')

    parts.append('</div>')
    return "\n".join(parts)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _truncate(text: str, limit: int = POPUP_TRUNCATE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... (truncated at {limit:,} chars, full: {len(text):,})"


def _render_steps_rows(
    steps: list[Step],
    grand_total: float,
    step_counter: int,
    rows: list[str],
    popups: list[str],
) -> int:
    """Render step rows into rows/popups lists, returns updated step_counter."""
    for step in steps:
        step_counter += 1
        step_id = f"step-{step_counter}"
        pct = (step.duration_seconds / grand_total * 100)
        color = _bar_color(step.name)
        size_kb = step.size_bytes / 1024
        cost_str = f"${step.detail.cost_usd:.2f}" if step.detail else ""
        detail_html = _render_detail(step.detail, step_id=step_id, popups=popups) if step.detail else ""

        # Step name with popup links if we have prompt/output
        has_prompt = step.detail and step.detail.prompt_text
        has_output = step.detail and step.detail.output_text
        has_log = step.log_path and step.log_path.exists() and step.log_path.stat().st_size > 0
        name_html = step.name
        links = []
        if has_prompt:
            links.append(f'<a href="#" onclick="showPopup(\'{step_id}-prompt\');return false">prompt</a>')
        if has_output:
            links.append(f'<a href="#" onclick="showPopup(\'{step_id}-output\');return false">output</a>')
        if has_log:
            links.append(f'<a href="#" onclick="showPopup(\'{step_id}-log\');return false">log</a>')
        if links:
            name_html += f' <span class="popup-links">[{" | ".join(links)}]</span>'

        rows.append(
            f'<tr class="step-row">'
            f'<td class="step-name">{name_html}</td>'
            f'<td class="step-time">{step.duration_str}</td>'
            f'<td class="step-cost">{cost_str}</td>'
            f'<td class="step-size">{size_kb:.0f}KB</td>'
            f'<td class="step-bar">'
            f'<div class="bar" style="width:{max(pct, MIN_BAR_PCT):.1f}%;background:{color}">'
            f'</div></td>'
            f'</tr>'
        )
        if detail_html:
            rows.append(
                f'<tr class="detail-row"><td colspan="5">{detail_html}</td></tr>'
            )

        # Build popup divs
        if has_prompt:
            popups.append(
                f'<div id="{step_id}-prompt" class="popup">'
                f'<div class="popup-header">'
                f'<strong>{step.name} — Prompt</strong>'
                f'<a href="#" onclick="hidePopup(\'{step_id}-prompt\');return false">close</a>'
                f'</div>'
                f'{_popup_content(step_id + "-prompt-content", step.detail.prompt_text)}'
                f'</div>'
            )
        if has_output:
            popups.append(
                f'<div id="{step_id}-output" class="popup">'
                f'<div class="popup-header">'
                f'<strong>{step.name} — Output</strong>'
                f'<a href="#" onclick="hidePopup(\'{step_id}-output\');return false">close</a>'
                f'</div>'
                f'{_popup_content(step_id + "-output-content", step.detail.output_text)}'
                f'</div>'
            )
        if has_log:
            popups.append(
                f'<div id="{step_id}-log" class="popup">'
                f'<div class="popup-header">'
                f'<strong>{step.name} — Log</strong>'
                f'<a href="#" onclick="hidePopup(\'{step_id}-log\');return false">close</a>'
                f'</div>'
                f'{_render_log_structured(step.log_path, step_id + "-log")}'
                f'</div>'
            )
    return step_counter


def _steps_cost(steps: list[Step]) -> float:
    return sum(s.detail.cost_usd for s in steps if s.detail)


def _steps_turns(steps: list[Step]) -> int:
    return sum(s.detail.num_turns for s in steps if s.detail)


def _steps_output_tokens(steps: list[Step]) -> int:
    return sum(s.detail.output_tokens for s in steps if s.detail)


def _steps_duration_seconds(steps: list[Step]) -> float:
    if not steps:
        return 0.0
    return sum(s.duration_seconds for s in steps)


def _steps_verdict(steps: list[Step]) -> str:
    """Return the last non-empty stop_reason from judge steps."""
    for step in reversed(steps):
        if step.detail and "judge" in step.name.lower() and step.detail.stop_reason:
            return step.detail.stop_reason
    return ""


def _fmt_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    return f"{m}m{s:02d}s"


def _pct_delta(a: float, b: float) -> str:
    """Format percentage change from a to b, with sign."""
    if a == 0:
        return "N/A"
    delta = (b - a) / a * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.0f}%"


def _delta_color(a: float, b: float, lower_is_better: bool = True) -> str:
    """Return green if b is better than a, red if worse."""
    if a == 0:
        return "#555"
    improved = b < a if lower_is_better else b > a
    return "#27ae60" if improved else "#e74c3c"


def _render_fork_section(
    fork: ForkSection,
    grand_total: float,
    step_counter: int,
    rows: list[str],
    popups: list[str],
) -> int:
    """Render a fork section: comparison table + per-variant detail."""

    # --- Fork header ---
    rows.append(
        f'<tr class="fork-header"><td colspan="5">'
        f'<strong>Fork {fork.fork_index}: {fork.fork_title}</strong>'
        f'</td></tr>'
    )

    # --- Comparison summary table ---
    variant_names = sorted(fork.variants.keys())

    # Gather per-variant metrics
    variant_metrics: list[dict] = []
    for vname in variant_names:
        vsteps = fork.variants[vname]
        dur = _steps_duration_seconds(vsteps)
        cost = _steps_cost(vsteps)
        turns = _steps_turns(vsteps)
        out_tok = _steps_output_tokens(vsteps)
        verdict = _steps_verdict(vsteps)
        label = vname.replace("variant-", "").upper()
        variant_metrics.append({
            "name": vname,
            "label": label,
            "dur": dur,
            "cost": cost,
            "turns": turns,
            "out_tok": out_tok,
            "verdict": verdict,
        })

    # Build comparison table HTML
    rows.append('<tr class="fork-comparison"><td colspan="5"><div class="fork-table-wrap">')
    rows.append('<table class="fork-compare">')
    rows.append(
        '<tr>'
        '<th>Variant</th>'
        '<th>Time</th>'
        '<th>Cost</th>'
        '<th>Turns</th>'
        '<th>Output tok</th>'
        '<th>Verdict</th>'
        '</tr>'
    )

    for m in variant_metrics:
        verdict_cls = ' class="verdict-pass"' if m["verdict"] == "pass" else (
            ' class="verdict-fail"' if m["verdict"] in ("fail", "error") else ""
        )
        rows.append(
            f'<tr>'
            f'<td><strong>{m["label"]}</strong></td>'
            f'<td>{_fmt_duration(m["dur"])}</td>'
            f'<td>${m["cost"]:.2f}</td>'
            f'<td>{m["turns"]}</td>'
            f'<td>{m["out_tok"]:,}</td>'
            f'<td{verdict_cls}>{m["verdict"] or "—"}</td>'
            f'</tr>'
        )

    # Delta row (second vs first)
    if len(variant_metrics) >= 2:
        a = variant_metrics[0]
        b = variant_metrics[1]
        b_label = b["label"]
        rows.append(
            f'<tr class="delta-row">'
            f'<td>Δ ({b_label} vs {a["label"]})</td>'
            f'<td style="color:{_delta_color(a["dur"], b["dur"])}">'
            f'{_pct_delta(a["dur"], b["dur"])}</td>'
            f'<td style="color:{_delta_color(a["cost"], b["cost"])}">'
            f'{_pct_delta(a["cost"], b["cost"])}</td>'
            f'<td style="color:{_delta_color(float(a["turns"]), float(b["turns"]))}">'
            f'{_pct_delta(float(a["turns"]), float(b["turns"]))}</td>'
            f'<td style="color:{_delta_color(float(a["out_tok"]), float(b["out_tok"]))}">'
            f'{_pct_delta(float(a["out_tok"]), float(b["out_tok"]))}</td>'
            f'<td></td>'
            f'</tr>'
        )

    rows.append('</table></div></td></tr>')

    # --- Per-variant detail sections ---
    for vname in variant_names:
        vsteps = fork.variants[vname]
        label = vname.replace("variant-", "").upper()
        dur_str = _fmt_duration(_steps_duration_seconds(vsteps))
        cost = _steps_cost(vsteps)

        rows.append(
            f'<tr class="variant-header"><td colspan="5">'
            f'Variant {label} — {dur_str} — ${cost:.2f}'
            f'</td></tr>'
        )

        step_counter = _render_steps_rows(vsteps, grand_total, step_counter, rows, popups)

    return step_counter


# ---------------------------------------------------------------------------
# HTML renderer (top-level)
# ---------------------------------------------------------------------------

def render_html(
    timelines: list[PhaseTimeline],
    workspace: Path,
    shared_steps: list[Step] | None = None,
    fork_sections: list[ForkSection] | None = None,
    run_title: str = "Timeline",
) -> str:
    rows: list[str] = []
    popups: list[str] = []
    step_counter = 0

    # Compute grand_total across all content for proportional bars
    if timelines:
        grand_total = sum(t.total_seconds for t in timelines) or 1
        grand_cost = sum(t.total_cost for t in timelines)
    else:
        all_steps: list[Step] = list(shared_steps or [])
        for fork in (fork_sections or []):
            for vsteps in fork.variants.values():
                all_steps.extend(vsteps)
        grand_total = sum(s.duration_seconds for s in all_steps) or 1
        grand_cost = sum(s.detail.cost_usd for s in all_steps if s.detail)

    if timelines:
        # Methodology-runner mode: phase-grouped flat table
        for tl in timelines:
            rows.append(
                f'<tr class="phase-header"><td colspan="5">'
                f'<strong>{tl.phase_id}</strong> — {tl.total_str}'
                f' — ${tl.total_cost:.2f}'
                f'</td></tr>'
            )
            step_counter = _render_steps_rows(
                tl.steps, grand_total, step_counter, rows, popups
            )
    else:
        # Prompt-runner mode: shared steps then fork sections
        if shared_steps:
            shared_dur = _fmt_duration(sum(s.duration_seconds for s in shared_steps))
            shared_cost = _steps_cost(shared_steps)
            rows.append(
                f'<tr class="phase-header"><td colspan="5">'
                f'<strong>Shared Pre-Fork Steps</strong>'
                f' — {shared_dur}'
                f' — ${shared_cost:.2f}'
                f'</td></tr>'
            )
            step_counter = _render_steps_rows(
                shared_steps, grand_total, step_counter, rows, popups
            )

        for fork in (fork_sections or []):
            step_counter = _render_fork_section(
                fork, grand_total, step_counter, rows, popups
            )

    grand_m, grand_s = divmod(int(grand_total), 60)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{run_title} — {workspace.name}</title>
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

  .popup-links {{ font-size: 0.8em; }}
  .popup-links a {{ color: #4a90d9; text-decoration: none; }}
  .popup-links a:hover {{ text-decoration: underline; }}

  /* Fork/variant styles */
  tr.fork-header td {{
    background: #d8e8f5; padding: 8px 12px; font-size: 1.05em;
    border-top: 3px solid #4a90d9;
  }}
  tr.fork-comparison td {{ padding: 8px 12px 12px 12px; }}
  .fork-table-wrap {{ overflow-x: auto; }}
  table.fork-compare {{
    width: auto; min-width: 500px; max-width: 700px;
    border: 1px solid #ccc; border-radius: 4px; font-size: 0.9em;
  }}
  table.fork-compare th {{
    background: #f0f0f0; padding: 6px 12px; text-align: left;
    border-bottom: 1px solid #ccc; font-weight: normal; color: #555;
  }}
  table.fork-compare td {{ padding: 5px 12px; border-bottom: 1px solid #eee; }}
  tr.delta-row td {{
    background: #f8f8f0; font-style: italic; border-top: 1px solid #bbb;
  }}
  .verdict-pass {{ color: #27ae60; font-weight: bold; }}
  .verdict-fail {{ color: #e74c3c; font-weight: bold; }}
  tr.variant-header td {{
    background: #f0f4f8; padding: 6px 12px 6px 24px; font-size: 0.95em;
    border-top: 1px solid #b0c8e0; color: #444;
  }}
  tr.variant-io td {{ padding: 0 12px 8px 24px; }}
  .variant-io-wrap {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .variant-block {{
    flex: 1; min-width: 300px; max-height: 400px; overflow: auto;
    border: 1px solid #ddd; border-radius: 6px; background: #fafafa;
  }}
  .variant-block summary {{
    padding: 6px 12px; cursor: pointer; font-size: 0.85em;
    font-weight: bold; color: #555; background: #f0f0f0;
    border-bottom: 1px solid #ddd;
  }}
  .variant-block pre {{ max-height: 350px; overflow: auto; margin: 0; }}

  .popup {{
    display: none; position: fixed; top: 5%; left: 10%; width: 80%; max-height: 85%;
    background: #fff; border: 1px solid #ccc; border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.25); z-index: 1000; overflow: auto;
  }}
  .popup-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 16px; border-bottom: 1px solid #eee; background: #f8f8f8;
    border-radius: 8px 8px 0 0; position: sticky; top: 0;
  }}
  .popup-header a {{ color: #e74c3c; text-decoration: none; font-size: 0.9em; }}
  .popup pre {{
    padding: 12px 16px; margin: 0; font-size: 0.8em; white-space: pre-wrap;
    word-wrap: break-word; line-height: 1.4;
  }}
  .popup-dual {{ position: relative; }}
  .toggle-btn {{
    position: absolute; top: 4px; right: 8px; z-index: 1;
    padding: 2px 10px; font-size: 0.75em; cursor: pointer;
    background: #e0e0e0; border: 1px solid #ccc; border-radius: 3px;
  }}
  .toggle-btn:hover {{ background: #d0d0d0; }}
  .popup-formatted code {{ background: #eee; padding: 1px 4px; border-radius: 2px; }}

  .log-structured {{ padding: 8px 12px; font-size: 0.82em; font-family: monospace; line-height: 1.6; }}
  .log-structured div {{ padding: 2px 0; border-bottom: 1px solid #f0f0f0; }}
  .log-type {{
    display: inline-block; width: 50px; font-weight: bold; font-size: 0.85em;
    text-align: center; border-radius: 3px; padding: 0 4px; margin-right: 6px;
  }}
  .log-system .log-type {{ background: #e8f5e9; color: #2e7d32; }}
  .log-thinking .log-type {{ background: #fff3e0; color: #e65100; }}
  .log-text .log-type {{ background: #e3f2fd; color: #1565c0; }}
  .log-tool .log-type {{ background: #f3e5f5; color: #7b1fa2; }}
  .log-result .log-type {{ background: #fce4ec; color: #c62828; }}
  .log-result-final .log-type {{ background: #e8f5e9; color: #2e7d32; font-size: 1em; }}
  .log-result-final {{ font-weight: bold; padding: 4px 0; border-top: 2px solid #ccc; }}
  .log-error .log-type {{ background: #ffcdd2; color: #b71c1c; }}
  .log-error {{ color: #b71c1c; font-weight: bold; }}
  .log-unknown .log-type {{ background: #eee; color: #666; }}
  .log-dim {{ color: #999; font-size: 0.9em; }}
  .log-ts {{ color: #888; font-size: 0.85em; }}
</style>
<script>
function showPopup(id) {{
  document.getElementById(id).style.display = 'block';
}}
function hidePopup(id) {{
  document.getElementById(id).style.display = 'none';
}}
function toggleView(uid) {{
  var el = document.getElementById(uid);
  var fmt = el.querySelector('.view-formatted');
  var raw = el.querySelector('.view-raw');
  var btn = el.querySelector('.toggle-btn');
  if (raw.style.display === 'none') {{
    raw.style.display = 'block';
    fmt.style.display = 'none';
    btn.textContent = 'formatted';
  }} else {{
    raw.style.display = 'none';
    fmt.style.display = 'block';
    btn.textContent = 'raw';
  }}
}}
document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') {{
    document.querySelectorAll('.popup').forEach(function(p) {{ p.style.display = 'none'; }});
  }}
}});
</script>
</head>
<body>
<h1>{run_title}</h1>
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
{''.join(popups)}
</body>
</html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate timeline report for a methodology-runner workspace or prompt-runner run directory."
    )
    parser.add_argument("path", help="Path to analyze (workspace or run directory).")
    parser.add_argument("--output", "-o", default=None, help="Output HTML path.")
    args = parser.parse_args(argv)

    input_path = Path(args.path).resolve()
    if not input_path.exists():
        print(f"Path not found: {input_path}", file=sys.stderr)
        return 1

    default_output = input_path / "timeline.html"
    output = Path(args.output) if args.output else default_output

    # Auto-detect mode
    methodology_runs = input_path / ".methodology-runner" / "runs"
    prompt_runner_logs = input_path / "logs"
    prompt_runner_manifest = input_path / "manifest.json"

    if methodology_runs.exists():
        # Methodology-runner mode
        timelines = parse_workspace(input_path)
        if not timelines:
            print(f"No phase data found in {input_path}", file=sys.stderr)
            return 1
        html = render_html(
            timelines=timelines,
            workspace=input_path,
            run_title="Methodology Runner Timeline",
        )
    elif prompt_runner_logs.exists() or prompt_runner_manifest.exists():
        # Prompt-runner run directory mode
        shared_steps, fork_sections = parse_prompt_runner_run(input_path)
        if not shared_steps and not fork_sections:
            print(f"No prompt-runner data found in {input_path}", file=sys.stderr)
            return 1
        html = render_html(
            timelines=[],
            workspace=input_path,
            shared_steps=shared_steps,
            fork_sections=fork_sections,
            run_title="Prompt Runner Timeline",
        )
    else:
        print(
            f"Cannot detect input type for {input_path}.\n"
            f"Expected either .methodology-runner/runs/ or logs/ / manifest.json",
            file=sys.stderr,
        )
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"Timeline written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
