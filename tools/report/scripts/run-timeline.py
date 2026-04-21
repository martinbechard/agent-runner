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
    python tools/report/scripts/run-timeline.py <path> [--output report.html]

The path can be:
  - A methodology-runner workspace (contains .methodology-runner/runs/)
  - A prompt-runner run directory (contains logs/ and/or manifest.json)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from copy import deepcopy
from functools import lru_cache


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POPUP_TRUNCATE_CHARS = 20_000_000  # 20 MB
MIN_BAR_PCT = 0.5
REPO_ROOT = Path(__file__).resolve().parents[3]
PRICING_FILE = REPO_ROOT / "docs" / "reference" / "openai-model-pricing.json"


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
class ToolResult:
    """A tool result that arrived between turns."""
    tool_name: str
    tool_fname: str
    result_size: int
    timestamp: str = ""


@dataclass
class Turn:
    turn_number: int
    thinking_chars: int = 0
    text_chars: int = 0
    thinking_content: str = ""
    text_content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results_before: list[ToolResult] = field(default_factory=list)
    """Tool results received BEFORE this turn (the user events that
    preceded this assistant response)."""
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
    """Parsed from one JSONL log file (one backend invocation)."""
    backend: str = "claude"
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
    cost_estimated: bool = False


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
    lifecycle_phase_id: str = ""
    steps: list[Step] = field(default_factory=list)
    drilldown_links: list[tuple[str, str]] = field(default_factory=list)

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


@dataclass
class ComparisonManifest:
    title: str
    mode: str
    runs: list[tuple[str, Path]]


@dataclass
class ReportDocument:
    run_title: str
    workspace: Path
    timelines: list[PhaseTimeline] = field(default_factory=list)
    shared_steps: list[Step] = field(default_factory=list)
    fork_sections: list[ForkSection] = field(default_factory=list)
    nav_links: list[tuple[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# JSONL log parsers
# ---------------------------------------------------------------------------

def detect_log_backend(path: Path) -> str:
    """Best-effort backend detection for a stdout JSONL log."""
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            etype = obj.get("type", "")
            if etype in {"thread.started", "turn.started", "item.started", "item.completed", "turn.completed"}:
                return "codex"
            if etype in {"assistant", "user", "result", "system", "rate_limit_event"}:
                return "claude"
    except OSError:
        pass
    return "claude"


def parse_claude_log(path: Path) -> CallDetail:
    """Parse a claude JSONL stdout log into a CallDetail.

    Content blocks from the same API response share identical usage
    values. We group them into one Turn by detecting when the usage
    signature (input_tokens, output_tokens, cache_read) changes.
    """
    detail = CallDetail(backend="claude")
    turn_num = 0
    current_turn: Turn | None = None
    prev_usage_sig: tuple[int, int, int] | None = None
    last_was_assistant = False
    # Map tool_use_id -> ToolCall so we can attach result sizes
    pending_tools: dict[str, ToolCall] = {}
    # Map tool_use_id -> (name, fname) for matching results to calls
    tool_id_to_name: dict[str, tuple[str, str]] = {}
    # Buffer tool results to attach to the next turn
    pending_results: list[ToolResult] = []
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
        if not isinstance(obj, dict):
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
                current_turn.tool_results_before = list(pending_results)
                pending_results.clear()
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
                    think_text = block.get("thinking", "")
                    current_turn.thinking_chars += len(think_text)
                    current_turn.thinking_content += think_text
                elif bt == "text":
                    txt = block.get("text", "")
                    current_turn.text_chars += len(txt)
                    current_turn.text_content += txt
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
                        fpath = block.get("input", {}).get("file_path", "") or block.get("input", {}).get("path", "") or ""
                        fname = fpath.split("/")[-1] if fpath else ""
                        tool_id_to_name[tool_id] = (name, fname)
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
                    # Buffer for attaching to the next turn
                    tname, tfname = tool_id_to_name.get(tool_id, ("?", ""))
                    pending_results.append(ToolResult(
                        tool_name=tname,
                        tool_fname=tfname,
                        result_size=result_len,
                        timestamp=ts,
                    ))
            last_was_assistant = False

        else:
            last_was_assistant = False

    # Flush last turn
    if current_turn is not None:
        detail.turns.append(current_turn)

    return detail


def parse_codex_log(path: Path) -> CallDetail:
    """Parse a Codex JSONL stdout log into a CallDetail.

    Codex non-interactive JSON uses thread/turn/item events rather than the
    Claude assistant/user/result schema.
    """
    detail = CallDetail(backend="codex")
    current_turn: Turn | None = None
    turn_num = 0
    need_new_turn = True

    def _ensure_turn() -> Turn:
        nonlocal current_turn, turn_num, need_new_turn
        if current_turn is None or need_new_turn:
            if current_turn is not None:
                detail.turns.append(current_turn)
            turn_num += 1
            current_turn = Turn(turn_number=turn_num)
            need_new_turn = False
        return current_turn

    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue

        etype = obj.get("type", "")
        if etype == "turn.started":
            continue

        if etype == "turn.completed":
            usage = obj.get("usage", {})
            detail.input_tokens = usage.get("input_tokens", 0)
            detail.cache_read_tokens = usage.get("cached_input_tokens", 0)
            detail.output_tokens = usage.get("output_tokens", 0)
            if current_turn is not None:
                current_turn.input_tokens = detail.input_tokens
                current_turn.cache_read_tokens = detail.cache_read_tokens
                current_turn.output_tokens = detail.output_tokens
            continue

        if etype not in {"item.completed", "item.started"}:
            continue
        item = obj.get("item", {})
        itype = item.get("type", "")

        if etype == "item.completed" and itype == "agent_message":
            text = item.get("text", "")
            current_turn = _ensure_turn()
            current_turn.text_chars += len(text)
            current_turn.text_content += text
            detail.output_text += text
            continue

        if etype == "item.completed" and itype == "command_execution":
            command = item.get("command", "")
            output = item.get("aggregated_output", "")
            tc = ToolCall(
                name="Bash",
                input_size=len(command),
                result_size=len(output),
                input_json=json.dumps({"command": command}),
                result_content=output,
                tool_use_id=item.get("id", ""),
            )
            current_turn = _ensure_turn()
            current_turn.tool_calls.append(tc)
            need_new_turn = True
            continue

        if etype == "item.completed" and itype == "collab_tool_call":
            tool = item.get("tool", "?")
            prompt = item.get("prompt") or ""
            result_content = json.dumps(item.get("agents_states", {}))
            tc = ToolCall(
                name=tool,
                input_size=len(prompt),
                result_size=len(result_content),
                input_json=json.dumps({"tool": tool, "prompt": prompt}),
                result_content=result_content,
                tool_use_id=item.get("id", ""),
            )
            if tool == "spawn_agent":
                detail.subagent_count += 1
            current_turn = _ensure_turn()
            current_turn.tool_calls.append(tc)
            need_new_turn = True
            continue

        if etype == "item.completed" and itype == "file_change":
            changes = item.get("changes", [])
            content = json.dumps(changes)
            tc = ToolCall(
                name="FileChange",
                input_size=len(content),
                result_size=len(content),
                input_json=content,
                result_content=content,
                tool_use_id=item.get("id", ""),
            )
            current_turn = _ensure_turn()
            current_turn.tool_calls.append(tc)
            need_new_turn = True

    if current_turn is not None:
        detail.turns.append(current_turn)
    detail.num_turns = len(detail.turns)

    return detail


def parse_log(path: Path) -> CallDetail:
    backend = detect_log_backend(path)
    if backend == "codex":
        detail = parse_codex_log(path)
    else:
        detail = parse_claude_log(path)
    detail = _apply_log_metadata(detail, path)
    return _finalize_detail(detail)


@lru_cache(maxsize=1)
def _load_pricing_table() -> dict[str, dict[str, float]]:
    try:
        raw = json.loads(PRICING_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    models = raw.get("models", {})
    if not isinstance(models, dict):
        return {}
    table: dict[str, dict[str, float]] = {}
    for model, prices in models.items():
        if isinstance(prices, dict):
            table[model.lower()] = prices
    return table


def _normalize_model_name(model: str) -> str:
    return (model or "").strip().lower()


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _fresh_input_tokens(detail: CallDetail) -> int:
    """Return non-cached input tokens for display."""
    if detail.input_tokens > 0:
        return max(0, detail.input_tokens - detail.cache_read_tokens)
    return _estimate_tokens(detail.prompt_text)


def _estimate_cost_usd(detail: CallDetail) -> tuple[float, bool]:
    if detail.cost_usd > 0:
        return detail.cost_usd, False
    model = _normalize_model_name(detail.model)
    if not model:
        return 0.0, False
    prices = _load_pricing_table().get(model)
    if not prices:
        return 0.0, False
    fresh_input_tokens = _fresh_input_tokens(detail)
    cost = (
        fresh_input_tokens * prices.get("input_per_million", 0.0)
        + detail.cache_read_tokens * prices.get("cached_input_per_million", 0.0)
        + detail.output_tokens * prices.get("output_per_million", 0.0)
    ) / 1_000_000
    return cost, True


def _finalize_detail(detail: CallDetail) -> CallDetail:
    detail.cost_usd, detail.cost_estimated = _estimate_cost_usd(detail)
    return detail


def _apply_log_metadata(detail: CallDetail, log_path: Path) -> CallDetail:
    meta = _load_log_metadata(log_path)
    model = meta.get("model")
    backend = meta.get("backend")
    if isinstance(model, str) and model.strip() and not detail.model:
        detail.model = model.strip()
    if isinstance(backend, str) and backend.strip():
        detail.backend = backend.strip()
    return detail


# ---------------------------------------------------------------------------
# Shared step-building helpers
# ---------------------------------------------------------------------------

def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _parse_iso_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_log_metadata(log_path: Path) -> dict[str, object]:
    meta_path = log_path.with_suffix(".meta.json")
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _read_top_level_toml_string(path: Path, key: str) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    pattern = re.compile(rf'^{re.escape(key)}\s*=\s*["\']([^"\']+)["\']\s*$', re.MULTILINE)
    match = pattern.search(content)
    return match.group(1).strip() if match else ""


def _resolve_codex_model_for_step(step_name: str, workspace_root: Path) -> str:
    lower = step_name.lower()
    agent_name = ""
    if "judge" in lower:
        agent_name = "prompt-runner-judge"
    elif "generator" in lower:
        agent_name = "prompt-runner-generator"

    if agent_name:
        for root in (workspace_root, REPO_ROOT, Path.home()):
            agent_path = root / ".codex" / "agents" / f"{agent_name}.toml"
            if agent_path.exists():
                model = _read_top_level_toml_string(agent_path, "model")
                if model:
                    return model

    for root in (workspace_root, REPO_ROOT, Path.home()):
        config_path = root / ".codex" / "config.toml"
        if config_path.exists():
            model = _read_top_level_toml_string(config_path, "model")
            if model:
                return model

    return ""


def _apply_codex_model_fallback(steps: list[Step], workspace_root: Path) -> None:
    for step in steps:
        detail = step.detail
        if detail is None or detail.backend != "codex" or detail.model:
            continue
        inferred = _resolve_codex_model_for_step(step.name, workspace_root)
        if inferred:
            detail.model = inferred
            _finalize_detail(detail)


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


def _normalize_step_sequence(
    steps: list[Step],
    *,
    start_anchor: datetime | None = None,
) -> None:
    """Make step timing sequential and monotonic.

    Many artifacts are written quickly enough that their mtimes collapse to the
    same second. For reporting, the more reliable model is:
    - start at the known run/phase start when available
    - each step starts when the previous one ended
    - each step ends at its own completion marker, clamped monotically
    """
    if not steps:
        return
    cursor = start_anchor or steps[0].started
    for step in steps:
        completed_at = step.ended
        if completed_at < cursor:
            completed_at = cursor
        step.started = cursor
        step.ended = completed_at
        cursor = completed_at


def _prompt_name_map_from_module_dir(module_dir: Path) -> dict[str, str]:
    import re

    names: dict[str, str] = {}
    for verdict in sorted(module_dir.glob("prompt-*.final-verdict.txt")):
        match = re.match(r"^(prompt-\d+)(?:-(.+))?\.final-verdict\.txt$", verdict.name)
        if not match:
            continue
        prompt_id = match.group(1)
        suffix = match.group(2) or ""
        names[prompt_id] = f"{prompt_id}-{suffix}" if suffix else prompt_id
    return names


def _backfill_prompts_from_history(module_dir: Path, steps: list[Step]) -> None:
    import re

    history_dir = module_dir / "history"
    if not history_dir.exists():
        return

    for step in steps:
        if not step.detail or step.detail.prompt_text:
            continue
        match = re.search(r"(prompt-\d+).*/ iter (\d+)", step.name)
        if not match:
            continue
        prompt_id = match.group(1)
        iter_num = match.group(2)
        prompt_history_dir = history_dir / prompt_id
        if not prompt_history_dir.exists():
            continue
        filename = (
            f"iter-{iter_num}-validation-prompt.md"
            if "judge" in step.name.lower()
            else f"iter-{iter_num}-prompt.md"
        )
        prompt_path = prompt_history_dir / filename
        try:
            step.detail.prompt_text = prompt_path.read_text(encoding="utf-8")
        except OSError:
            continue


def _parse_prompt_module_dir(
    module_dir: Path,
    *,
    prefix: str = "",
) -> list[Step]:
    import re

    steps: list[Step] = []
    prompt_names = _prompt_name_map_from_module_dir(module_dir)
    generator_logs = sorted(module_dir.glob("prompt-*.iter-*-generator.stdout.log"))
    for iter_log in generator_logs:
        match = re.match(r"^(prompt-\d+)\.iter-(\d+)-generator\.stdout\.log$", iter_log.name)
        if not match:
            continue
        prompt_id = match.group(1)
        iter_num = match.group(2)
        prompt_name = prompt_names.get(prompt_id, prompt_id)
        step_prefix = f"{prefix}{prompt_name}" if prefix else prompt_name

        stderr = iter_log.with_name(f"{prompt_id}.iter-{iter_num}-generator.stderr.log")
        step = _file_step(
            f"{step_prefix} / iter {iter_num} generator",
            stderr if stderr.exists() else iter_log,
            iter_log,
            iter_log,
        )
        if step:
            steps.append(step)

        det_stdout = iter_log.with_name(f"{prompt_id}.iter-{iter_num}-deterministic-validation.stdout.log")
        det_stderr = iter_log.with_name(f"{prompt_id}.iter-{iter_num}-deterministic-validation.stderr.log")
        det_proc = iter_log.with_name(f"{prompt_id}.iter-{iter_num}-deterministic-validation.proc.json")
        if det_stdout.exists():
            steps.append(
                Step(
                    name=f"{step_prefix} / iter {iter_num} deterministic validation",
                    started=_mtime(det_stderr if det_stderr.exists() else det_stdout),
                    ended=_mtime(det_proc if det_proc.exists() else det_stdout),
                    size_bytes=(det_proc if det_proc.exists() else det_stdout).stat().st_size,
                    log_path=det_stdout,
                )
            )

        judge_log = iter_log.with_name(f"{prompt_id}.iter-{iter_num}-judge.stdout.log")
        judge_stderr = iter_log.with_name(f"{prompt_id}.iter-{iter_num}-judge.stderr.log")
        if judge_log.exists():
            step = _file_step(
                f"{step_prefix} / iter {iter_num} judge",
                judge_stderr if judge_stderr.exists() else judge_log,
                judge_log,
                judge_log,
            )
            if step:
                steps.append(step)

    _backfill_prompts_from_history(module_dir, steps)
    _apply_codex_model_fallback(steps, module_dir.parent.parent)
    return steps


# ---------------------------------------------------------------------------
# Methodology-runner workspace parser
# ---------------------------------------------------------------------------

def parse_phase(
    runs_dir: Path,
    phase_num: int,
    phase_id: str,
    *,
    phase_started_at: datetime | None = None,
) -> PhaseTimeline | None:
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

    # Prompt-runner iterations. The orchestrator suffixes the directory
    # with the phase number to keep claude session IDs unique across
    # phases, so match any prompt-runner-output* child and prefer the
    # phase-specific one if present.
    pr_dir = next(
        (d for d in sorted(phase_dir.glob("prompt-runner-output-phase-*"))
         if d.is_dir()),
        phase_dir / "prompt-runner-output",
    )
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

    if timeline.steps:
        _normalize_step_sequence(timeline.steps, start_anchor=phase_started_at)
        return timeline
    return None


def _backfill_prompts_from_file(timeline: PhaseTimeline, prompt_file: Path) -> None:
    """For generator/judge steps missing prompt_text, extract it from the
    phase's prompt-runner .md file by matching the prompt slug in the step name."""
    import re
    try:
        content = prompt_file.read_text(encoding="utf-8")
    except OSError:
        return

    def _normalize_prompt_slug(text: str) -> str:
        slug = re.sub(r"\[model:[^\]]+\]", "", text, flags=re.IGNORECASE)
        slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")
        slug = re.sub(r"^-*prompt-\d+-", "", slug)
        slug = re.sub(r"-+(generator|judge)$", "", slug)
        return slug

    def _extract_section_model(text: str) -> str:
        m = re.search(r"\[MODEL:([^\]]+)\]", text, flags=re.IGNORECASE)
        return m.group(1).strip() if m else ""

    # Parse prompt sections: ## Prompt N: <title> followed by code blocks
    sections: dict[str, tuple[str, str]] = {}
    current_slug = ""
    current_lines: list[str] = []
    for line in content.splitlines():
        m = re.match(r"^## Prompt\s+\d+", line)
        if m:
            if current_slug and current_lines:
                section_text = "\n".join(current_lines)
                sections[current_slug] = (section_text, _extract_section_model(section_text))
            # Build a slug from the heading to match step names
            slug = _normalize_prompt_slug(line)
            current_slug = slug
            current_lines = [line]
        elif current_slug:
            current_lines.append(line)
    if current_slug and current_lines:
        section_text = "\n".join(current_lines)
        sections[current_slug] = (section_text, _extract_section_model(section_text))

    for step in timeline.steps:
        if step.detail and not step.detail.prompt_text:
            # Try to match step name slug to a section
            step_slug = re.sub(r"\s*/\s*iter.*$", "", step.name)
            step_slug = _normalize_prompt_slug(step_slug)
            is_judge = "judge" in step.name.lower()
            for section_slug, (section_text, section_model) in sections.items():
                matched = (
                    (section_slug and section_slug in step_slug) or
                    (step_slug and step_slug in section_slug)
                )
                if matched:
                    gen, val = _split_prompt_fences(section_text)
                    step.detail.prompt_text = val if is_judge else gen
                    if section_model and not step.detail.model:
                        step.detail.model = section_model
                        _finalize_detail(step.detail)
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

    def _normalize_prompt_slug(text: str) -> str:
        slug = re.sub(r"\[model:[^\]]+\]", "", text, flags=re.IGNORECASE)
        slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")
        slug = re.sub(r"^-*prompt-\d+-", "", slug)
        slug = re.sub(r"-+(generator|judge)$", "", slug)
        return slug

    def _extract_section_model(text: str) -> str:
        m = re.search(r"\[MODEL:([^\]]+)\]", text, flags=re.IGNORECASE)
        return m.group(1).strip() if m else ""

    sections: dict[str, tuple[str, str]] = {}
    current_slug = ""
    current_lines: list[str] = []
    for line in content.splitlines():
        m = re.match(r"^## Prompt\s+\d+", line)
        if m:
            if current_slug and current_lines:
                section_text = "\n".join(current_lines)
                sections[current_slug] = (section_text, _extract_section_model(section_text))
            slug = _normalize_prompt_slug(line)
            current_slug = slug
            current_lines = [line]
        elif current_slug:
            current_lines.append(line)
    if current_slug and current_lines:
        section_text = "\n".join(current_lines)
        sections[current_slug] = (section_text, _extract_section_model(section_text))

    for step in steps:
        if step.detail and not step.detail.prompt_text:
            step_slug = re.sub(r"\s*/\s*iter.*$", "", step.name)
            step_slug = _normalize_prompt_slug(step_slug)
            is_judge = "judge" in step.name.lower()
            for section_slug, (section_text, section_model) in sections.items():
                matched = (
                    (section_slug and section_slug in step_slug) or
                    (step_slug and step_slug in section_slug)
                )
                if matched:
                    gen, val = _split_prompt_fences(section_text)
                    step.detail.prompt_text = val if is_judge else gen
                    if section_model and not step.detail.model:
                        step.detail.model = section_model
                        _finalize_detail(step.detail)
                    break


def parse_workspace(workspace: Path) -> list[PhaseTimeline]:
    state_path = workspace / ".methodology-runner" / "state.json"
    run_files_dir = workspace / ".run-files"
    if state_path.exists() and run_files_dir.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        lifecycle_phase_id = ""
        for lifecycle_phase in state.get("lifecycle_phases", []):
            if lifecycle_phase.get("phase_id") == "LC-001-methodology-execution":
                lifecycle_phase_id = "LC-001-methodology-execution"
                break
        timelines: list[PhaseTimeline] = []
        for phase_meta in state.get("phases", []):
            phase_id = phase_meta.get("phase_id", "")
            if not phase_id.startswith("PH-"):
                continue
            try:
                phase_number = int(phase_id[3:6])
            except (IndexError, ValueError):
                continue

            module_slug = phase_id.split("-", 2)[2]
            module_dir = run_files_dir / module_slug
            steps = _parse_prompt_module_dir(module_dir) if module_dir.exists() else []

            cross_ref_result_path = phase_meta.get("cross_ref_result_path")
            if cross_ref_result_path:
                xref = Path(cross_ref_result_path)
                if xref.exists() and steps:
                    prev = steps[-1]
                    step = Step(
                        name="Cross-reference verification",
                        started=prev.ended,
                        ended=_mtime(xref),
                        size_bytes=xref.stat().st_size,
                    )
                    if step.duration_seconds > 0:
                        steps.append(step)

            if not steps:
                continue

            _normalize_step_sequence(
                steps,
                start_anchor=_parse_iso_datetime(phase_meta.get("started_at")),
            )
            timelines.append(
                PhaseTimeline(
                    phase_id=phase_id,
                    phase_number=phase_number,
                    lifecycle_phase_id=lifecycle_phase_id,
                    steps=steps,
                )
            )
        if timelines:
            return timelines

    runs_dir = workspace / ".methodology-runner" / "runs"
    if not runs_dir.exists():
        return []

    phases_map: dict[int, str] = {}
    phase_started_map: dict[int, datetime] = {}
    if state_path.exists():
        state = json.loads(state_path.read_text())
        for p in state.get("phases", []):
            pid = p["phase_id"]
            for i in range(10):
                if (runs_dir / f"phase-{i}").exists() and pid.startswith(f"PH-00{i}"):
                    phases_map[i] = pid
                    started_at = _parse_iso_datetime(p.get("started_at"))
                    if started_at is not None:
                        phase_started_map[i] = started_at

    timelines = []
    for phase_dir in sorted(runs_dir.glob("phase-*")):
        if not phase_dir.is_dir():
            continue
        try:
            num = int(phase_dir.name.split("-")[1])
        except (IndexError, ValueError):
            continue
        phase_id = phases_map.get(num, f"PH-{num:03d}")
        tl = parse_phase(
            runs_dir,
            num,
            phase_id,
            phase_started_at=phase_started_map.get(num),
        )
        if tl:
            timelines.append(tl)
    return timelines


def _read_yaml_scalar_field(path: Path, field_name: str) -> str:
    import re

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    pattern = re.compile(rf"^{re.escape(field_name)}:\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(content)
    if not match:
        return ""
    value = match.group(1).strip()
    if value in {"", "null", "none", "None"}:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    return value


def discover_ph006_child_report(workspace: Path) -> tuple[str, Path] | None:
    run_report = workspace / "docs" / "implementation" / "implementation-run-report.yaml"
    if not run_report.exists():
        return None
    child_prompt_path = _read_yaml_scalar_field(run_report, "child_prompt_path")
    if not child_prompt_path:
        return None
    module_slug = Path(child_prompt_path).stem
    module_dir = workspace / ".run-files" / module_slug
    if not module_dir.exists():
        return None
    return module_slug, module_dir


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
    run_started_at: datetime | None = None

    if any(run_dir.glob("prompt-*.iter-*-generator.stdout.log")):
        shared_steps = _parse_prompt_module_dir(run_dir)
        if shared_steps:
            _normalize_step_sequence(shared_steps)
        return shared_steps, fork_sections

    # Shared pre-fork steps from top-level logs/
    top_logs = run_dir / "logs"
    shared_steps = _parse_prompt_log_dir(top_logs)
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists() and shared_steps:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        run_started_at = _parse_iso_datetime(manifest.get("started_at"))
        manifest_model = ((manifest.get("config") or {}).get("model") or "").strip()
        source_file = manifest.get("source_file")
        if source_file:
            source_path = Path(source_file)
            if source_path.exists():
                _backfill_prompts_from_file(
                    PhaseTimeline(phase_id="prompt-runner", phase_number=0, steps=shared_steps),
                    source_path,
                )
        if manifest_model:
            for step in shared_steps:
                if step.detail and not step.detail.model:
                    step.detail.model = manifest_model
                    _finalize_detail(step.detail)
    if shared_steps:
        _normalize_step_sequence(shared_steps, start_anchor=run_started_at)

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
                _normalize_step_sequence(variant_steps)
                variants[variant_name] = variant_steps

        if variants:
            fork_sections.append(ForkSection(
                fork_index=fork_index,
                fork_title=fork_title,
                variants=variants,
            ))

    return shared_steps, fork_sections


def _step_signature(step: Step) -> tuple[str, str, str]:
    detail = step.detail
    return (
        step.name,
        detail.prompt_text if detail else "",
        "judge" if "judge" in step.name.lower() else "generator",
    )


def _common_prefix_length(step_lists: list[list[Step]]) -> int:
    if not step_lists or any(not steps for steps in step_lists):
        return 0
    limit = min(len(steps) for steps in step_lists)
    idx = 0
    while idx < limit:
        sig = _step_signature(step_lists[0][idx])
        if any(_step_signature(steps[idx]) != sig for steps in step_lists[1:]):
            break
        idx += 1
    return idx


def load_comparison_manifest(path: Path) -> ComparisonManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    title = data.get("title", "Prompt Runner Comparison")
    mode = data.get("mode", "comparison")
    raw_runs = data.get("runs", [])
    runs: list[tuple[str, Path]] = []
    for item in raw_runs:
        if not isinstance(item, dict):
            continue
        label = item.get("label") or item.get("name") or "variant"
        run_path = item.get("path")
        if not run_path:
            continue
        p = Path(run_path)
        if not p.is_absolute():
            candidate = (path.parent / p).resolve()
            p = candidate if candidate.exists() else p.resolve()
        runs.append((label, p))
    return ComparisonManifest(title=title, mode=mode, runs=runs)


def parse_comparison_manifest(path: Path) -> tuple[list[Step], list[ForkSection], str]:
    manifest = load_comparison_manifest(path)
    if not manifest.runs:
        return [], [], manifest.title

    variant_steps: dict[str, list[Step]] = {}
    step_lists: list[list[Step]] = []
    for label, run_path in manifest.runs:
        if not run_path.exists():
            raise ValueError(f"comparison manifest run path not found: {run_path}")
        shared_steps, fork_sections = parse_prompt_runner_run(run_path)
        if fork_sections:
            # Keep this simple: synthetic comparison mode expects full runs,
            # not existing fork reports nested inside another comparison.
            raise ValueError(
                f"comparison manifest does not support nested fork runs: {run_path}"
            )
        copied = deepcopy(shared_steps)
        variant_name = f"variant-{label.lower().replace(' ', '-').replace('_', '-')}"
        variant_steps[variant_name] = copied
        step_lists.append(copied)

    if manifest.mode == "diagnostic":
        return [], [ForkSection(fork_index=1, fork_title=manifest.title, variants=variant_steps)], manifest.title

    prefix_len = _common_prefix_length(step_lists)
    shared_prefix = deepcopy(step_lists[0][:prefix_len]) if prefix_len > 0 else []
    trimmed_variants = {
        vname: steps[prefix_len:]
        for vname, steps in variant_steps.items()
    }
    return shared_prefix, [ForkSection(fork_index=1, fork_title=manifest.title, variants=trimmed_variants)], manifest.title


class BaseReportAdapter:
    """Converts a source path into a normalized report document."""

    @staticmethod
    def matches(path: Path) -> bool:
        raise NotImplementedError

    @staticmethod
    def build(path: Path) -> ReportDocument:
        raise NotImplementedError


class MethodologyWorkspaceAdapter(BaseReportAdapter):
    @staticmethod
    def matches(path: Path) -> bool:
        return path.is_dir() and (
            (path / ".methodology-runner" / "state.json").exists()
            or (path / ".methodology-runner" / "runs").exists()
        )

    @staticmethod
    def build(path: Path) -> ReportDocument:
        timelines = parse_workspace(path)
        if not timelines:
            raise ValueError(f"No phase data found in {path}")
        return ReportDocument(
            run_title="Methodology Runner Timeline",
            workspace=path,
            timelines=timelines,
        )


class PromptRunnerRunAdapter(BaseReportAdapter):
    @staticmethod
    def matches(path: Path) -> bool:
        return path.is_dir() and (
            (path / "logs").exists()
            or (path / "manifest.json").exists()
            or (path / "module.log").exists()
            or any(path.glob("prompt-*.iter-*-generator.stdout.log"))
        )

    @staticmethod
    def build(path: Path) -> ReportDocument:
        shared_steps, fork_sections = parse_prompt_runner_run(path)
        if not shared_steps and not fork_sections:
            raise ValueError(f"No prompt-runner data found in {path}")
        return ReportDocument(
            run_title="Prompt Runner Timeline",
            workspace=path,
            shared_steps=shared_steps,
            fork_sections=fork_sections,
        )


class ComparisonManifestAdapter(BaseReportAdapter):
    @staticmethod
    def matches(path: Path) -> bool:
        return path.is_file()

    @staticmethod
    def build(path: Path) -> ReportDocument:
        shared_steps, fork_sections, title = parse_comparison_manifest(path)
        if not shared_steps and not fork_sections:
            raise ValueError(f"No comparison data found in {path}")
        return ReportDocument(
            run_title=title,
            workspace=path,
            shared_steps=shared_steps,
            fork_sections=fork_sections,
        )


ADAPTERS: list[type[BaseReportAdapter]] = [
    ComparisonManifestAdapter,
    MethodologyWorkspaceAdapter,
    PromptRunnerRunAdapter,
]


def load_report_document(path: Path) -> ReportDocument:
    for adapter in ADAPTERS:
        if adapter.matches(path):
            return adapter.build(path)
    raise ValueError(
        f"Cannot detect input type for {path}.\n"
        f"Expected a comparison manifest file, a methodology workspace with .methodology-runner/state.json, "
        f"or a prompt-runner run/module directory."
    )


# ---------------------------------------------------------------------------
# HTML renderer helpers
# ---------------------------------------------------------------------------

def _model_abbrev(model: str) -> str:
    """Return the model name as-is, or ? if empty."""
    return model if model else "?"


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
    uid = f"pc-{popup_id}"
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
        f'<div class="view-formatted">{formatted_html}</div>'
        f'<div class="view-raw" style="display:none">{raw_html}</div>'
        f'</div>'
    )


def _popup_toolbar(uid: str) -> str:
    """Toolbar HTML for a popup — placed in the popup-header."""
    return (
        f'<span class="popup-controls">'
        f'<button class="toggle-btn" onclick="toggleView(\'{uid}\')">raw</button>'
        f'<label class="pretty-label" style="display:none">'
        f'<input type="checkbox" class="pretty-json-cb" '
        f'onchange="togglePrettyJson(\'{uid}\')"> pretty JSON</label>'
        f'</span>'
    )


def _render_log_structured(
    log_path: Path,
    popup_id: str,
    prompt_text: str = "",
    detail: CallDetail | None = None,
    step_duration_seconds: float = 0.0,
) -> str:
    """Render a JSONL log file as structured HTML with per-record formatting."""
    if detect_log_backend(log_path) == "codex":
        return _render_codex_log_structured(
            log_path,
            popup_id,
            prompt_text=prompt_text,
            detail=detail,
            step_duration_seconds=step_duration_seconds,
        )

    import json as _jlog

    uid = f"pc-{popup_id}"
    items: list[str] = []

    parsed_detail = detail or parse_log(log_path)
    inferred_turns = _infer_turn_durations(parsed_detail, step_duration_seconds or parsed_detail.duration_ms / 1000)
    turn_offsets: list[int] = []
    elapsed = 0.0
    for dur in inferred_turns:
        turn_offsets.append(int(elapsed))
        elapsed += dur

    # Show Turn 1 + initial prompt (passed via --print, not in the JSONL)
    if prompt_text:
        log_turn_num = 1
        preview = _escape_html(prompt_text[:300]).replace("\n", " ")
        turn_label = "── Turn 1 ──"
        if turn_offsets:
            turn_label = f'── Turn 1 — T+{_fmt_elapsed_padded(turn_offsets[0])} ──'
        items.append(
            f'<div class="log-turn-divider">{turn_label}</div>'
        )
        items.append(
            f'<div class="log-user-prompt">'
            f'<span class="log-type">PROMPT</span> '
            f'<span class="log-dim">{len(prompt_text):,}</span> '
            f'{preview}{"…" if len(prompt_text) > 300 else ""}'
            f'</div>'
        )
    pending_log_tools: dict[str, tuple[str, str]] = {}  # tool_use_id -> (name, fname)
    # Turn tracking for dividers
    log_turn_num = 0
    log_prev_usage_sig: tuple | None = None
    log_last_was_assistant = False

    try:
        raw_text = log_path.read_text(encoding="utf-8", errors="replace")
        lines = raw_text.splitlines()
    except OSError:
        return '<pre>(cannot read log)</pre>'

    parsed_any = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = _jlog.loads(line)
        except (ValueError, TypeError):
            items.append(f'<div class="log-unknown">{_escape_html(line[:500])}</div>')
            continue
        if not isinstance(obj, dict):
            items.append(f'<div class="log-unknown">{_escape_html(line[:500])}</div>')
            continue
        parsed_any = True

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
                f'session={sid} '
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
                    f'<span class="log-dim">({len(output):,})</span>'
                    f'</div>'
                )

        elif t == "assistant":
            msg = obj.get("message", {})
            usage = msg.get("usage", {})
            usage_sig = (
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
                usage.get("cache_read_input_tokens", 0),
            )
            is_new_turn = usage_sig != log_prev_usage_sig or not log_last_was_assistant
            if is_new_turn:
                log_turn_num += 1
                log_prev_usage_sig = usage_sig
                turn_label = f'── Turn {log_turn_num} ──'
                if log_turn_num - 1 < len(turn_offsets):
                    turn_label = f'── Turn {log_turn_num} — T+{_fmt_elapsed_padded(turn_offsets[log_turn_num - 1])} ──'
                items.append(
                    f'<div class="log-turn-divider">'
                    f'{turn_label}'
                    f'</div>'
                )
            log_last_was_assistant = True
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
                        f'<span class="log-dim">{len(text):,}</span> '
                        f'{preview}…'
                        f'</div>'
                    )
                elif bt == "text":
                    text = block.get("text", "")
                    preview = _escape_html(text[:200]).replace("\n", " ")
                    items.append(
                        f'<div class="log-text">'
                        f'<span class="log-type">TEXT</span> '
                        f'<span class="log-dim">{len(text):,}</span> '
                        f'{preview}{"…" if len(text) > 200 else ""}'
                        f'</div>'
                    )
                elif bt == "tool_use":
                    name = block.get("name", "?")
                    tool_id = block.get("id", "")
                    inp = block.get("input", {})
                    fpath = inp.get("file_path", "") or inp.get("path", "") or inp.get("pattern", "") or inp.get("command", "")[:60]
                    fname = fpath.split("/")[-1] if fpath else ""
                    inp_size = len(_jlog.dumps(inp))
                    # Track for matching tool_result later
                    if tool_id:
                        pending_log_tools[tool_id] = (name, fname)
                    items.append(
                        f'<div class="log-tool">'
                        f'<span class="log-type">→TOOL</span> '
                        f'<strong>{_escape_html(name)}</strong>'
                        f'{"(" + _escape_html(fname) + ")" if fname else ""} '
                        f'<span class="log-dim">{inp_size:,}</span>'
                        f'</div>'
                    )

        elif t == "user":
            log_last_was_assistant = False
            ts = obj.get("timestamp", "")
            msg = obj.get("message", {})
            for block in msg.get("content", []):
                bt = block.get("type", "?")
                if bt == "tool_result":
                    content = str(block.get("content", ""))
                    tool_use_id = block.get("tool_use_id", "")
                    tool_name, tool_fname = pending_log_tools.get(tool_use_id, ("?", ""))
                    tool_label = f'<strong>{_escape_html(tool_name)}</strong>'
                    if tool_fname:
                        tool_label += f'({_escape_html(tool_fname)})'
                    preview = _escape_html(content[:150]).replace("\n", " ")
                    items.append(
                        f'<div class="log-result">'
                        f'<span class="log-type">←TOOL</span> '
                        f'{tool_label} '
                        f'<span class="log-dim">{len(content):,}</span> '
                        f'{preview}{"…" if len(content) > 150 else ""}'
                        f'{"  <span class=log-ts>" + ts[-12:] + "</span>" if ts else ""}'
                        f'</div>'
                    )
                elif bt == "text":
                    text = block.get("text", "")
                    items.append(
                        f'<div class="log-text">'
                        f'<span class="log-type">USER</span> '
                        f'<span class="log-dim">{len(text):,}</span>'
                        f'</div>'
                    )

        elif t == "rate_limit_event":
            log_last_was_assistant = False
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

    if not parsed_any:
        formatted = f'<pre class="popup-formatted">{_format_block(raw_text[:POPUP_TRUNCATE_CHARS])}</pre>'
        raw_html = f'<pre class="popup-raw">{_escape_html(raw_text[:POPUP_TRUNCATE_CHARS])}</pre>'
        return (
            f'<div id="{uid}" class="popup-dual">'
            f'<div class="view-formatted">{formatted}</div>'
            f'<div class="view-raw" style="display:none">{raw_html}</div>'
            f'</div>'
        )

    formatted = "\n".join(items)
    raw_html = f'<pre class="popup-raw">{_escape_html(raw_text[:POPUP_TRUNCATE_CHARS])}</pre>'

    return (
        f'<div id="{uid}" class="popup-dual">'
        f'<div class="view-formatted"><div class="log-structured">{formatted}</div></div>'
        f'<div class="view-raw" style="display:none">{raw_html}</div>'
        f'</div>'
    )


def _render_codex_log_structured(
    log_path: Path,
    popup_id: str,
    prompt_text: str = "",
    detail: CallDetail | None = None,
    step_duration_seconds: float = 0.0,
) -> str:
    """Render a Codex JSONL log file as structured HTML."""
    import json as _jlog

    uid = f"pc-{popup_id}"
    items: list[str] = []
    parsed_detail = detail or parse_log(log_path)
    inferred_turns = _infer_turn_durations(parsed_detail, step_duration_seconds or parsed_detail.duration_ms / 1000)
    turn_offsets: list[int] = []
    elapsed = 0.0
    for dur in inferred_turns:
        turn_offsets.append(int(elapsed))
        elapsed += dur

    turn_num = 0
    need_new_turn = True

    if prompt_text:
        turn_num = 1
        need_new_turn = False
        preview = _escape_html(prompt_text[:300]).replace("\n", " ")
        turn_label = "── Turn 1 ──"
        if turn_offsets:
            turn_label = f'── Turn 1 — T+{_fmt_elapsed_padded(turn_offsets[0])} ──'
        items.append(
            f'<div class="log-turn-divider">{turn_label}</div>'
            f'<div class="log-user-prompt">'
            f'<span class="log-type">PROMPT</span> '
            f'<span class="log-dim">{len(prompt_text):,}</span> '
            f'{preview}{"…" if len(prompt_text) > 300 else ""}'
            f'</div>'
        )

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

        etype = obj.get("type", "?")
        if etype == "thread.started":
            items.append(
                f'<div class="log-system"><span class="log-type">THREAD</span> '
                f'{_escape_html(obj.get("thread_id", "?"))}</div>'
            )
        elif etype == "turn.started":
            continue
        elif etype in {"item.started", "item.completed"}:
            item = obj.get("item", {})
            itype = item.get("type", "?")
            prefix = "▶" if etype == "item.started" else "✓"
            if etype == "item.completed" and itype in {
                "agent_message", "command_execution", "collab_tool_call", "file_change",
            }:
                if need_new_turn:
                    turn_num += 1
                    turn_label = f'── Turn {turn_num} ──'
                    if turn_num - 1 < len(turn_offsets):
                        turn_label = f'── Turn {turn_num} — T+{_fmt_elapsed_padded(turn_offsets[turn_num - 1])} ──'
                    items.append(f'<div class="log-turn-divider">{turn_label}</div>')
                    need_new_turn = False
            if itype == "agent_message":
                text = item.get("text", "")
                preview = _escape_html(text[:200]).replace("\n", " ")
                items.append(
                    f'<div class="log-text"><span class="log-type">MSG{prefix}</span> '
                    f'<span class="log-dim">{len(text):,}</span> '
                    f'{preview}{"…" if len(text) > 200 else ""}</div>'
                )
            elif itype == "command_execution":
                cmd = item.get("command", "")
                output = item.get("aggregated_output", "")
                preview = _escape_html(cmd[:120]).replace("\n", " ")
                items.append(
                    f'<div class="log-tool"><span class="log-type">CMD{prefix}</span> '
                    f'<strong>{preview}</strong> '
                    f'<span class="log-dim">out={len(output):,}</span></div>'
                )
                if etype == "item.completed":
                    need_new_turn = True
            elif itype == "collab_tool_call":
                tool = item.get("tool", "?")
                prompt = item.get("prompt") or ""
                items.append(
                    f'<div class="log-tool"><span class="log-type">AGT{prefix}</span> '
                    f'<strong>{_escape_html(tool)}</strong> '
                    f'<span class="log-dim">{len(prompt):,}</span></div>'
                )
                if etype == "item.completed":
                    need_new_turn = True
            elif itype == "file_change":
                changes = item.get("changes", [])
                items.append(
                    f'<div class="log-result"><span class="log-type">FILE{prefix}</span> '
                    f'{len(changes)} change(s)</div>'
                )
                if etype == "item.completed":
                    need_new_turn = True
            else:
                items.append(
                    f'<div class="log-unknown"><span class="log-type">{_escape_html(etype)}</span> '
                    f'{_escape_html(itype)}</div>'
                )
        elif etype == "turn.completed":
            usage = obj.get("usage", {})
            items.append(
                f'<div class="log-result-final"><span class="log-type">DONE</span> '
                f'in={usage.get("input_tokens", 0):,} | '
                f'cached={usage.get("cached_input_tokens", 0):,} | '
                f'out={usage.get("output_tokens", 0):,}</div>'
            )
        else:
            items.append(
                f'<div class="log-unknown"><span class="log-type">{_escape_html(etype)}</span></div>'
            )

    formatted = "\n".join(items)
    raw_html = f'<pre class="popup-raw">{_escape_html(raw_text[:POPUP_TRUNCATE_CHARS])}</pre>'
    return (
        f'<div id="{uid}" class="popup-dual">'
        f'<div class="view-formatted"><div class="log-structured">{formatted}</div></div>'
        f'<div class="view-raw" style="display:none">{raw_html}</div>'
        f'</div>'
    )


def _tool_file_path(tc: ToolCall) -> str:
    """Extract a file path from a Read/Write/Glob tool call's input JSON."""
    try:
        import json as _j
        inp = _j.loads(tc.input_json)
        if isinstance(inp, dict):
            return (
                inp.get("file_path", "")
                or inp.get("path", "")
                or inp.get("pattern", "")
                or inp.get("command", "")[:80]
            )
        if isinstance(inp, list):
            for item in inp:
                if isinstance(item, dict):
                    path = item.get("path", "")
                    if path:
                        return path
            return ""
        return ""
    except (ValueError, TypeError):
        return ""


def _turn_cell_link(chars: int, content: str, popup_id: str, popups: list | None) -> str:
    """Render a turn table cell value. If content is non-empty, make it a clickable link to a popup."""
    if not chars:
        return "0"
    if not content or popups is None:
        return f"{chars:,}"
    popups.append(
        f'<div id="{popup_id}" class="popup">'
        f'<div class="popup-header">'
        f'<strong>{popup_id.split("-")[-1].title()} ({chars:,})</strong>'
        f'{_popup_toolbar(f"pc-{popup_id}")}'
        f'<a href="#" onclick="hidePopup(\'{popup_id}\');return false">close</a>'
        f'</div>'
        f'<div class="popup-body">'
        f'{_popup_content(popup_id, content)}'
        f'</div></div>'
    )
    return f'<a href="#" onclick="showPopup(\'{popup_id}\');return false">{chars:,}</a>'


def _render_detail(
    detail: CallDetail,
    *,
    step_id: str = "",
    popups: list | None = None,
    step_duration_seconds: float = 0.0,
) -> str:
    """Render the drill-down section for one call."""
    if not detail or (not detail.turns and not detail.duration_ms):
        return ""

    parts = ['<div class="detail">']

    # Summary line
    api_s = detail.duration_api_ms / 1000
    measured_wall_s = detail.duration_ms / 1000
    wall_s = measured_wall_s if measured_wall_s > 0 else step_duration_seconds
    overhead_s = wall_s - api_s if api_s > 0 and wall_s > 0 else 0
    rate_basis_s = api_s if api_s > 0 else wall_s
    overall_tok_s = detail.output_tokens / rate_basis_s if rate_basis_s > 0 else 0
    model_abbr = _model_abbrev(detail.model)
    if model_abbr == "?":
        model_abbr = detail.backend.upper()
    fresh_input_tokens = _fresh_input_tokens(detail)
    parts.append(
        f'<div class="detail-summary">'
        f'{model_abbr}'
        f' | wall: {_fmt_duration(wall_s) if wall_s > 0 else "—"}'
        f' | API: {_fmt_duration(api_s) if api_s > 0 else "—"}'
        f' | overhead: {f"{overhead_s:.1f}s" if api_s > 0 and wall_s > 0 else "—"}'
        f' | turns: {len(detail.turns)}'
        f' | output: {detail.output_tokens:,} tok'
        f' | {overall_tok_s:.0f} tok/s'
        f' | cost: ${detail.cost_usd:.2f}'
    )
    if detail.subagent_count:
        parts.append(f' | <span class="warn">subagents: {detail.subagent_count}</span>')
    parts.append('</div>')

    # Token bar
    total_tok = (
        detail.cache_creation_tokens
        + detail.cache_read_tokens
        + fresh_input_tokens
        + detail.output_tokens
    ) or 1
    parts.append('<div class="token-bar">')
    for label, count, color in [
        ("cache-read", detail.cache_read_tokens, "#3498db"),
        ("cache-create", detail.cache_creation_tokens, "#2ecc71"),
        ("input", fresh_input_tokens, "#95a5a6"),
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
        f'<span style="color:#3498db">cache-read: {detail.cache_read_tokens:,}</span>'
        f' | <span style="color:#2ecc71">cache-create: {detail.cache_creation_tokens:,}</span>'
        f' | <span style="color:#95a5a6">fresh-input: {fresh_input_tokens:,}</span>'
        f' | <span style="color:#e74c3c">output: {detail.output_tokens:,}</span>'
        f'</div>'
    )

    # Per-turn table
    if detail.turns:
        parts.append('<table class="turns">')
        parts.append(
            '<tr><th>Turn</th><th>Think</th><th>Text</th>'
            '<th>Output</th><th>Time</th><th>tok/s</th>'
            '<th>Cost</th><th>Tools</th></tr>'
        )
        tool_popup_counter = 0
        # Pre-compute estimated tokens per turn, then scale so they
        # sum to the real output_tokens from the result event.
        raw_est = [
            (t.thinking_chars + t.text_chars + t.tool_write_chars) // 4
            for t in detail.turns
        ]
        raw_total = sum(raw_est) or 1
        real_total = detail.output_tokens or raw_total
        scale = real_total / raw_total
        all_est = [round(e * scale) for e in raw_est]
        total_est_for_cost = sum(all_est) or 1

        # Distribute unmeasured turn time from the total API time.
        # Turns with timestamps get their measured duration. Turns without
        # get a share of the remaining time proportional to their output.
        measured_time = sum(
            t.duration_seconds for t in detail.turns if t.duration_seconds > 0
        )
        time_budget = api_s if api_s > 0 else wall_s
        remaining_time = max(0, time_budget - measured_time)
        unmeasured_est = sum(
            all_est[i] for i, t in enumerate(detail.turns) if t.duration_seconds <= 0
        ) or 1
        inferred_dur: list[float] = []
        for i, t in enumerate(detail.turns):
            if t.duration_seconds > 0:
                inferred_dur.append(t.duration_seconds)
            else:
                inferred_dur.append(remaining_time * all_est[i] / unmeasured_est)

        for turn_idx, turn in enumerate(detail.turns):
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
                            popup_lines.append(f"--- Input ({tc.input_size:,}) ---\n{display_input}\n")
                        if tc.result_content:
                            popup_lines.append(f"--- Result ({tc.result_size:,}) ---\n{tc.result_content[:POPUP_TRUNCATE_CHARS]}\n")
                    else:
                        popup_lines.append(f"Input: {tc.input_size:,} chars | Result: {tc.result_size:,}")
                    dual_uid = f"pc-{popup_id}"
                    popups.append(
                        f'<div id="{popup_id}" class="popup">'
                        f'<div class="popup-header">'
                        f'<strong>{tc.name}: {_escape_html(short_path)}</strong>'
                        f'{_popup_toolbar(dual_uid)}'
                        f'<a href="#" onclick="hidePopup(\'{popup_id}\');return false">close</a>'
                        f'</div>'
                        f'<div class="popup-body">'
                        f'{_popup_content(popup_id, chr(10).join(popup_lines))}'
                        f'</div></div>'
                    )
                else:
                    tool_parts.append(label)
            tools_str = ", ".join(tool_parts) or "—"
            thinking_cls = ' class="big-think"' if turn.thinking_chars > 5000 else ""
            est_tok = all_est[turn_idx]
            dur = inferred_dur[turn_idx]
            is_inferred = turn.duration_seconds <= 0 and dur > 0
            if dur < 1 and dur > 0:
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
                f'<td{thinking_cls}>{_turn_cell_link(turn.thinking_chars, turn.thinking_content, f"{step_id}-t{turn.turn_number}-think", popups)}</td>'
                f'<td>{_turn_cell_link(turn.text_chars, turn.text_content, f"{step_id}-t{turn.turn_number}-text", popups)}</td>'
                f'<td>{est_tok:,}</td>'
                f'<td>{dur_str}</td>'
                f'<td>{tok_s_str}</td>'
                f'<td>${detail.cost_usd * est_tok / total_est_for_cost:.2f}</td>'
                f'<td class="tool-detail">{tools_str}</td>'
                f'</tr>'
            )
        # Totals row
        tot_think = sum(t.thinking_chars for t in detail.turns)
        tot_text = sum(t.text_chars for t in detail.turns)
        tot_est = sum(all_est)
        total_tok_s_str = f"{overall_tok_s:.0f}" if time_budget > 0 else "—"
        parts.append(
            f'<tr style="border-top:1px solid #ccc;font-weight:bold">'
            f'<td>Total</td>'
            f'<td>{tot_think:,}</td>'
            f'<td>{tot_text:,}</td>'
            f'<td>{tot_est:,}</td>'
            f'<td>{_fmt_duration(time_budget) if time_budget > 0 else "—"}</td>'
            f'<td>{total_tok_s_str}</td>'
            f'<td>${detail.cost_usd:.2f}</td>'
            f'<td></td>'
            f'</tr>'
        )
        parts.append('</table>')

    parts.append('</div>')
    return "\n".join(parts)


def _infer_turn_durations(detail: CallDetail, total_duration_seconds: float) -> list[float]:
    if not detail.turns:
        return []
    raw_est = [
        (t.thinking_chars + t.text_chars + t.tool_write_chars) // 4
        for t in detail.turns
    ]
    raw_total = sum(raw_est) or 1
    real_total = detail.output_tokens or raw_total
    scale = real_total / raw_total
    all_est = [round(e * scale) for e in raw_est]
    measured_time = sum(t.duration_seconds for t in detail.turns if t.duration_seconds > 0)
    remaining_time = max(0, total_duration_seconds - measured_time)
    unmeasured_est = sum(
        all_est[i] for i, t in enumerate(detail.turns) if t.duration_seconds <= 0
    ) or 1
    inferred: list[float] = []
    for i, turn in enumerate(detail.turns):
        if turn.duration_seconds > 0:
            inferred.append(turn.duration_seconds)
        else:
            inferred.append(remaining_time * all_est[i] / unmeasured_est)
    return inferred


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
    report_started_at: datetime,
    row_class: str = "",
    group_id: str | None = None,
    group_hidden: bool = False,
) -> int:
    """Render step rows into rows/popups lists, returns updated step_counter."""
    for step in steps:
        step_counter += 1
        step_id = f"step-{step_counter}"
        pct = (step.duration_seconds / grand_total * 100)
        color = _bar_color(step.name)
        size_kb = step.size_bytes / 1024
        cost_str = f"${step.detail.cost_usd:.2f}" if step.detail else ""
        detail_html = _render_detail(
            step.detail,
            step_id=step_id,
            popups=popups,
            step_duration_seconds=step.duration_seconds,
        ) if step.detail else ""
        has_detail = bool(detail_html)
        detail_row_id = f"{step_id}-detail"
        toggle_id = f"{step_id}-toggle"
        elapsed_str = _fmt_elapsed_padded((step.started - report_started_at).total_seconds())
        start_str = _fmt_clock(step.started)

        # Step name with popup links if we have prompt/output
        has_prompt = step.detail and step.detail.prompt_text
        has_output = step.detail and step.detail.output_text
        has_log = step.log_path and step.log_path.exists() and step.log_path.stat().st_size > 0
        name_html = (
            f'<span class="step-toggle" id="{toggle_id}" aria-hidden="true">▸</span>{step.name}'
            if has_detail
            else step.name
        )
        links = []
        if has_prompt:
            links.append(f'<a href="#" onclick="event.stopPropagation();showPopup(\'{step_id}-prompt\');return false">prompt</a>')
        if has_output:
            links.append(f'<a href="#" onclick="event.stopPropagation();showPopup(\'{step_id}-output\');return false">output</a>')
        if has_log:
            links.append(f'<a href="#" onclick="event.stopPropagation();showPopup(\'{step_id}-log\');return false">log</a>')
        links_html = f'<span class="popup-links">{" | ".join(links)}</span>' if links else "—"

        tr_cls = f"step-row {row_class}".strip()
        if has_detail:
            tr_cls = f"{tr_cls} is-collapsible".strip()
            row_attrs = (
                f' class="{tr_cls}"'
                f' onclick="toggleStepDetail(\'{detail_row_id}\', \'{toggle_id}\')"'
                f' data-detail-id="{detail_row_id}"'
            )
        else:
            row_attrs = f' class="{tr_cls}"'
        if group_id:
            row_attrs += f' data-group="{group_id}"'
        if group_hidden:
            row_attrs += ' style="display:none"'
        rows.append(
            f'<tr{row_attrs}>'
            f'<td class="step-elapsed">{elapsed_str}</td>'
            f'<td class="step-start">{start_str}</td>'
            f'<td class="step-name">{name_html}</td>'
            f'<td class="step-time">{step.duration_str}</td>'
            f'<td class="step-cost">{cost_str}</td>'
            f'<td class="step-size">{size_kb:.0f}KB</td>'
            f'<td class="step-links">{links_html}</td>'
            f'<td class="step-bar">'
            f'<div class="bar" style="width:{max(pct, MIN_BAR_PCT):.1f}%;background:{color}">'
            f'</div></td>'
            f'</tr>'
        )
        if detail_html:
            det_cls = f"detail-row {row_class}".strip()
            detail_attrs = (
                f' id="{detail_row_id}"'
                f' class="{det_cls}"'
                f' style="display:none"'
                f' data-open="0"'
            )
            if group_id:
                detail_attrs += f' data-group="{group_id}"'
            rows.append(
                f'<tr{detail_attrs}><td colspan="8">{detail_html}</td></tr>'
            )

        # Build popup divs
        if has_prompt:
            p_uid = f'pc-{step_id}-prompt-content'
            popups.append(
                f'<div id="{step_id}-prompt" class="popup">'
                f'<div class="popup-header">'
                f'<strong>{step.name} — Prompt</strong>'
                f'{_popup_toolbar(p_uid)}'
                f'<a href="#" onclick="hidePopup(\'{step_id}-prompt\');return false">close</a>'
                f'</div>'
                f'<div class="popup-body">'
                f'{_popup_content(step_id + "-prompt-content", step.detail.prompt_text)}'
                f'</div></div>'
            )
        if has_output:
            o_uid = f'pc-{step_id}-output-content'
            popups.append(
                f'<div id="{step_id}-output" class="popup">'
                f'<div class="popup-header">'
                f'<strong>{step.name} — Output</strong>'
                f'{_popup_toolbar(o_uid)}'
                f'<a href="#" onclick="hidePopup(\'{step_id}-output\');return false">close</a>'
                f'</div>'
                f'<div class="popup-body">'
                f'{_popup_content(step_id + "-output-content", step.detail.output_text)}'
                f'</div></div>'
            )
        if has_log:
            l_uid = f'pc-{step_id}-log'
            popups.append(
                f'<div id="{step_id}-log" class="popup">'
                f'<div class="popup-header">'
                f'<strong>{step.name} — Log</strong>'
                f'{_popup_toolbar(l_uid)}'
                f'<a href="#" onclick="hidePopup(\'{step_id}-log\');return false">close</a>'
                f'</div>'
                f'<div class="popup-body">'
                f'{_render_log_structured(step.log_path, step_id + "-log", prompt_text=step.detail.prompt_text if step.detail else "", detail=step.detail, step_duration_seconds=step.duration_seconds)}'
                f'</div></div>'
            )
    return step_counter


def _steps_cost(steps: list[Step]) -> float:
    return sum(s.detail.cost_usd for s in steps if s.detail)


def _steps_turns(steps: list[Step]) -> int:
    return sum(len(s.detail.turns) for s in steps if s.detail)


def _steps_output_tokens(steps: list[Step]) -> int:
    return sum(s.detail.output_tokens for s in steps if s.detail)


def _steps_duration_seconds(steps: list[Step]) -> float:
    if not steps:
        return 0.0
    return sum(s.duration_seconds for s in steps)


def _steps_verdict(steps: list[Step]) -> str:
    """Return the judge's VERDICT (pass/revise/escalate) from the last judge step's output."""
    import re
    for step in reversed(steps):
        if step.detail and "judge" in step.name.lower() and step.detail.output_text:
            m = re.search(r'VERDICT:\s*(pass|revise|escalate)', step.detail.output_text, re.IGNORECASE)
            if m:
                return m.group(1).lower()
    return "—"


def _fmt_duration(seconds: float) -> str:
    if 0 < seconds < 1:
        return "<1s"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    return f"{m}m{s:02d}s"


def _fmt_elapsed_padded(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s:04d}s"


def _fmt_clock(dt: datetime) -> str:
    return dt.astimezone().strftime("%H:%M:%S")


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
    report_started_at: datetime,
) -> int:
    """Render a fork section: comparison table + per-variant detail."""

    # --- Fork header ---
    rows.append(
        f'<tr class="fork-header"><td colspan="8">'
        f'<strong>Fork {fork.fork_index}: {fork.fork_title}</strong>'
        f'</td></tr>'
    )

    # --- Per-variant detail sections ---
    variant_names = sorted(fork.variants.keys())

    for vname in variant_names:
        vsteps = fork.variants[vname]
        label = vname.replace("variant-", "").upper()
        dur = _steps_duration_seconds(vsteps)
        dur_str = _fmt_duration(dur)
        cost = _steps_cost(vsteps)
        turns = _steps_turns(vsteps)
        out_tok = _steps_output_tokens(vsteps)
        verdict = _steps_verdict(vsteps)
        verdict_cls = "verdict-pass" if verdict == "pass" else (
            "verdict-fail" if verdict in ("fail", "revise", "escalate") else ""
        )

        # Aggregate Think and Text across all steps
        tot_think = sum(
            sum(t.thinking_chars for t in s.detail.turns)
            for s in vsteps if s.detail
        )
        tot_text = sum(
            sum(t.text_chars for t in s.detail.turns)
            for s in vsteps if s.detail
        )
        tok_s = out_tok / dur if dur > 0 else 0

        variant_css = "".join(c if c.isalnum() else "-" for c in vname.lower()).strip("-")
        variant_cls = f"in-variant variant-{variant_css}"
        rows.append(
            f'<tr class="variant-header {variant_cls}"><td colspan="8">'
            f'<strong>Variant {label}</strong>'
            f' <span class="variant-metrics">'
            f'{turns} turns'
            f' | Think: {tot_think:,}'
            f' | Text: {tot_text:,}'
            f' | Output: {out_tok:,}'
            f' | {dur_str}'
            f' | {tok_s:.0f} tok/s'
            f' | ${cost:.2f}'
            f' | <span class="{verdict_cls}">{verdict}</span>'
            f'</span>'
            f'</td></tr>'
        )

        step_counter = _render_steps_rows(
            vsteps, grand_total, step_counter, rows, popups, report_started_at,
            row_class=variant_cls,
        )

    return step_counter


# ---------------------------------------------------------------------------
# HTML renderer (top-level)
# ---------------------------------------------------------------------------

def render_html(
    document: ReportDocument,
) -> str:
    timelines = document.timelines
    workspace = document.workspace
    shared_steps = document.shared_steps
    fork_sections = document.fork_sections
    run_title = document.run_title
    rows: list[str] = []
    popups: list[str] = []
    step_counter = 0
    all_details: list[CallDetail] = []

    # Compute grand_total across all content for proportional bars
    if timelines:
        grand_total = sum(t.total_seconds for t in timelines) or 1
        grand_cost = sum(t.total_cost for t in timelines)
        all_details = [step.detail for tl in timelines for step in tl.steps if step.detail]
        report_started_at = min(
            (step.started for tl in timelines for step in tl.steps),
            default=datetime.now(timezone.utc),
        )
    else:
        all_steps: list[Step] = list(shared_steps or [])
        for fork in (fork_sections or []):
            for vsteps in fork.variants.values():
                all_steps.extend(vsteps)
        grand_total = sum(s.duration_seconds for s in all_steps) or 1
        grand_cost = sum(s.detail.cost_usd for s in all_steps if s.detail)
        all_details = [s.detail for s in all_steps if s.detail]
        report_started_at = min(
            (step.started for step in all_steps),
            default=datetime.now(timezone.utc),
        )
    has_estimated_cost = any(detail.cost_estimated for detail in all_details)
    nav_html = ""
    if document.nav_links:
        nav_html = '<div class="nav-links">' + " | ".join(
            f'<a href="{_escape_html(href)}">{_escape_html(label)}</a>'
            for label, href in document.nav_links
        ) + '</div>'

    if timelines:
        # Methodology-runner mode: phase-grouped flat table
        for tl in timelines:
            drilldown_html = ""
            if tl.drilldown_links:
                links = " | ".join(
                    f'<a href="{_escape_html(href)}">{_escape_html(label)}</a>'
                    for label, href in tl.drilldown_links
                )
                drilldown_html = f' <span class="phase-links">{links}</span>'
            phase_group_id = f"phase-{tl.phase_number:03d}"
            phase_toggle_id = f"{phase_group_id}-toggle"
            rows.append(
                f'<tr class="phase-header is-collapsible" onclick="toggleGroup(\'{phase_group_id}\', \'{phase_toggle_id}\')"><td colspan="8">'
                f'<span class="phase-toggle" id="{phase_toggle_id}" aria-hidden="true">▸</span>'
                f'<strong>{_escape_html(tl.lifecycle_phase_id + " > ") if tl.lifecycle_phase_id else ""}{_escape_html(tl.phase_id)}</strong> — {tl.total_str}'
                f' — ${tl.total_cost:.2f}'
                f'{drilldown_html}'
                f'</td></tr>'
            )
            step_counter = _render_steps_rows(
                tl.steps, grand_total, step_counter, rows, popups, report_started_at,
                group_id=phase_group_id, group_hidden=True,
            )
    else:
        # Prompt-runner mode: steps and fork sections interleaved
        if shared_steps:
            step_counter = _render_steps_rows(
                shared_steps, grand_total, step_counter, rows, popups, report_started_at
            )

        for fork in (fork_sections or []):
            step_counter = _render_fork_section(
                fork, grand_total, step_counter, rows, popups, report_started_at
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
  .nav-links {{ margin: 0 0 16px; font-size: 0.92em; }}
  .nav-links a, .phase-links a {{ color: #4a90d9; text-decoration: none; }}
  .nav-links a:hover, .phase-links a:hover {{ text-decoration: underline; }}
  .phase-links {{ font-size: 0.9em; margin-left: 12px; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 1400px; }}
  thead th {{
    position: sticky; top: 0; background: #fafafa; z-index: 2;
    text-align: left; padding: 6px 12px; border-bottom: 2px solid #ddd;
    font-size: 0.85em; color: #666;
  }}
  tr.phase-header td {{ background: #eee; padding: 8px 12px; font-size: 1.05em; border-top: 2px solid #ccc; }}
  tr.phase-header.is-collapsible {{ cursor: pointer; }}
  tr.phase-header.is-collapsible:hover td {{ background: #e7edf4; }}
  tr.step-row td {{ padding: 4px 12px; vertical-align: middle; }}
  tr.detail-row td {{ padding: 0 12px 12px 24px; }}
  tr.step-row.is-collapsible {{ cursor: pointer; }}
  tr.step-row.is-collapsible:hover td {{ background: #f3f7fb; }}
  .step-elapsed {{ width: 6%; text-align: right; font-family: monospace; font-size: 0.85em; color: #666; }}
  .step-start {{ width: 7%; text-align: right; font-family: monospace; font-size: 0.85em; color: #666; }}
  .step-name {{ width: 30%; font-size: 0.9em; }}
  .step-toggle {{
    display: inline-block; width: 1.1em; margin-right: 4px; color: #666;
    transition: transform 0.12s ease;
  }}
  .step-toggle.is-open {{ transform: rotate(90deg); }}
  .phase-toggle {{
    display: inline-block; width: 1.1em; margin-right: 6px; color: #555;
    transition: transform 0.12s ease;
  }}
  .phase-toggle.is-open {{ transform: rotate(90deg); }}
  .step-time {{ width: 7%; text-align: right; font-family: monospace; font-size: 0.9em; }}
  .step-cost {{ width: 7%; text-align: right; font-family: monospace; font-size: 0.85em; color: #666; }}
  .step-size {{ width: 6%; text-align: right; font-family: monospace; font-size: 0.85em; color: #888; }}
  .step-links {{ width: 11%; font-size: 0.82em; color: #4a90d9; }}
  .step-bar {{ width: 26%; }}
  .bar {{ height: 18px; border-radius: 3px; min-width: 4px; }}

  .detail {{ background: #f5f5f5; border-radius: 6px; padding: 10px 14px; font-size: 0.85em; margin-top: 4px; }}
  .detail-summary {{ margin-bottom: 6px; color: #555; font-family: monospace; }}
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
  .verdict-pass {{ color: #27ae60; font-weight: bold; }}
  .verdict-fail {{ color: #e74c3c; font-weight: bold; }}
  tr.variant-header td {{
    background: #f0f4f8; padding: 8px 12px 8px 24px; font-size: 0.95em;
    border-top: 2px solid #b0c8e0; color: #444;
  }}
  .variant-metrics {{
    font-size: 0.85em; color: #555; font-family: monospace;
  }}
  tr.in-variant td:first-child {{
    border-left: 4px solid #b0c8e0; padding-left: 20px;
  }}
  tr.variant-variant-a td:first-child {{ border-left-color: #4a90d9; }}
  tr.variant-variant-b td:first-child {{ border-left-color: #e67e22; }}

  .popup {{
    display: none; position: fixed; top: 5%; left: 10%; width: 80%; max-height: 85%;
    background: #fff; border: 1px solid #ccc; border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.25); z-index: 1000;
    overflow: hidden; display: none; flex-direction: column;
  }}
  .popup-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 16px; border-bottom: 1px solid #eee; background: #f8f8f8;
    border-radius: 8px 8px 0 0; flex-shrink: 0;
  }}
  .popup-header a {{ color: #e74c3c; text-decoration: none; font-size: 0.9em; }}
  .popup-body {{
    overflow: auto; flex: 1; min-height: 0;
  }}
  .popup pre {{
    padding: 12px 16px; margin: 0; font-size: 0.8em; white-space: pre-wrap;
    word-wrap: break-word; line-height: 1.4;
  }}
  .popup-dual {{ position: relative; }}
  .popup-controls {{
    display: flex; gap: 8px; align-items: center; margin: 0 12px;
  }}
  .pretty-label {{
    font-size: 0.75em; color: #666; cursor: pointer; user-select: none;
  }}
  .jv-fold {{ display: inline; }}
  .jv-fold summary {{ display: inline; cursor: pointer; list-style: none; }}
  .jv-fold summary::-webkit-details-marker {{ display: none; }}
  .jv-fold[open] > summary .jv-dim {{ display: none; }}
  .jv-fold:not([open]) > summary::after {{ content: ' … }}'; color: #999; }}
  .jv-key {{ color: #2980b9; }}
  .jv-str {{ color: #27ae60; }}
  .jv-num {{ color: #e67e22; }}
  .jv-bool {{ color: #8e44ad; }}
  .jv-null {{ color: #999; font-style: italic; }}
  .jv-brace {{ color: #555; font-weight: bold; }}
  .jv-dim {{ color: #999; font-size: 0.9em; }}
  hr.jv-sep {{ border: none; border-top: 1px solid #eee; margin: 4px 0; }}
  .toggle-btn {{
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
  .log-user-prompt .log-type {{ background: #fff9c4; color: #f57f17; }}
  .log-ts {{ color: #888; font-size: 0.85em; }}
  .log-turn-divider {{
    color: #888; font-size: 0.85em; font-weight: bold; padding: 6px 0 2px;
    border-top: 1px solid #ddd; margin-top: 4px;
  }}
</style>
<script>
function showPopup(id) {{
  document.getElementById(id).style.display = 'flex';
}}
function hidePopup(id) {{
  document.getElementById(id).style.display = 'none';
}}
function toggleGroup(groupId, toggleId) {{
  var rows = document.querySelectorAll('[data-group="' + groupId + '"]');
  if (!rows.length) return;
  var willOpen = true;
  for (var i = 0; i < rows.length; i++) {{
    var row = rows[i];
    if (!row.classList.contains('detail-row')) {{
      willOpen = row.style.display === 'none';
      break;
    }}
  }}
  rows.forEach(function(row) {{
    if (willOpen) {{
      if (row.classList.contains('detail-row')) {{
        row.style.display = row.dataset.open === '1' ? 'table-row' : 'none';
      }} else {{
        row.style.display = 'table-row';
      }}
    }} else {{
      row.style.display = 'none';
    }}
  }});
  var toggle = document.getElementById(toggleId);
  if (toggle) {{
    if (willOpen) toggle.classList.add('is-open');
    else toggle.classList.remove('is-open');
  }}
}}
function toggleStepDetail(rowId, toggleId) {{
  var row = document.getElementById(rowId);
  if (!row) return;
  var toggle = document.getElementById(toggleId);
  var isOpen = row.style.display !== 'none';
  if (isOpen) {{
    row.style.display = 'none';
    row.dataset.open = '0';
    if (toggle) toggle.classList.remove('is-open');
  }} else {{
    row.style.display = 'table-row';
    row.dataset.open = '1';
    if (toggle) toggle.classList.add('is-open');
  }}
}}
function toggleView(uid) {{
  var el = document.getElementById(uid);
  if (!el) return;
  var fmt = el.querySelector('.view-formatted');
  var raw = el.querySelector('.view-raw');
  // Button is in the header, find it via the popup ancestor
  var popup = el.closest('.popup') || el.closest('.popup-body') || el.parentElement;
  var btn = popup.querySelector('.toggle-btn[onclick*="' + uid + '"]') || popup.querySelector('.toggle-btn');
  var prettyLabel = popup.querySelector('.pretty-label');
  if (raw.style.display === 'none') {{
    raw.style.display = 'block';
    fmt.style.display = 'none';
    if (btn) btn.textContent = 'formatted';
    if (prettyLabel) prettyLabel.style.display = 'inline';
  }} else {{
    raw.style.display = 'none';
    fmt.style.display = 'block';
    if (btn) btn.textContent = 'raw';
    if (prettyLabel) prettyLabel.style.display = 'none';
  }}
}}
function jsonToTree(val, key, depth) {{
  var indent = '  '.repeat(depth);
  if (val === null) return '<span class="jv-null">null</span>';
  if (typeof val === 'boolean') return '<span class="jv-bool">' + val + '</span>';
  if (typeof val === 'number') return '<span class="jv-num">' + val + '</span>';
  if (typeof val === 'string') {{
    var escaped = val.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    if (escaped.length > 120) {{
      return '<span class="jv-str">"' + escaped.substring(0, 120) + '…"</span> <span class="jv-dim">(' + val.length + ')</span>';
    }}
    return '<span class="jv-str">"' + escaped + '"</span>';
  }}
  if (Array.isArray(val)) {{
    if (val.length === 0) return '<span class="jv-brace">[]</span>';
    var items = val.map(function(v, i) {{
      return indent + '  ' + jsonToTree(v, i, depth + 1);
    }});
    var preview = val.length + ' items';
    return '<details class="jv-fold"><summary><span class="jv-brace">[</span> <span class="jv-dim">' + preview + '</span></summary>' +
      items.join(',\\n') + '\\n' + indent + '<span class="jv-brace">]</span></details>';
  }}
  if (typeof val === 'object') {{
    var keys = Object.keys(val);
    if (keys.length === 0) return '<span class="jv-brace">{{}}</span>';
    var entries = keys.map(function(k) {{
      return indent + '  <span class="jv-key">"' + k + '"</span>: ' + jsonToTree(val[k], k, depth + 1);
    }});
    var preview = keys.slice(0, 3).join(', ') + (keys.length > 3 ? ', …' : '');
    var open = depth < 2 ? ' open' : '';
    return '<details class="jv-fold"' + open + '><summary><span class="jv-brace">{{</span> <span class="jv-dim">' + preview + '</span></summary>' +
      entries.join(',\\n') + '\\n' + indent + '<span class="jv-brace">}}</span></details>';
  }}
  return String(val);
}}
function togglePrettyJson(uid) {{
  var el = document.getElementById(uid);
  if (!el) {{
    // Toolbar is in header — find the popup-dual via the popup ancestor
    var popup = document.querySelector('.popup-dual');
    // Try all popup-duals
    document.querySelectorAll('.popup-dual').forEach(function(d) {{
      if (d.id === uid) el = d;
    }});
    if (!el) return;
  }}
  var rawPre = el.querySelector('.view-raw pre') || el.querySelector('.popup-raw');
  if (!rawPre) return;
  if (rawPre.dataset.original === undefined) {{
    rawPre.dataset.original = rawPre.innerHTML;
  }}
  // Find checkbox — might be in the header (parent popup)
  var popup = el.closest('.popup');
  var cb = popup ? popup.querySelector('.pretty-json-cb') : el.querySelector('.pretty-json-cb');
  var checked = cb && cb.checked;
  // Save preference
  try {{ localStorage.setItem('prettyJson', checked ? '1' : '0'); }} catch(e) {{}}
  if (checked) {{
    var text = rawPre.dataset.originalText || rawPre.textContent;
    if (!rawPre.dataset.originalText) rawPre.dataset.originalText = text;
    var lines = text.split('\\n');
    var result = [];
    for (var i = 0; i < lines.length; i++) {{
      var line = lines[i].trim();
      if (!line) continue;
      try {{
        var obj = JSON.parse(line);
        result.push(jsonToTree(obj, '', 0));
      }} catch(e) {{
        result.push(line.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'));
      }}
    }}
    rawPre.innerHTML = result.join('\\n<hr class="jv-sep">\\n');
  }} else {{
    rawPre.innerHTML = rawPre.dataset.original;
  }}
}}
// Restore pretty-JSON preference on load
document.addEventListener('DOMContentLoaded', function() {{
  try {{
    var pref = localStorage.getItem('prettyJson');
    if (pref === '1') {{
      document.querySelectorAll('.pretty-json-cb').forEach(function(cb) {{
        cb.checked = true;
      }});
    }}
  }} catch(e) {{}}
}});
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
{nav_html}
<table>
<thead>
<tr>
<th>T+</th>
<th>Start</th>
<th>Step</th>
<th>Time</th>
<th>Cost</th>
<th>Size</th>
<th>Links</th>
<th></th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
{'<div style="margin:12px 0 0;color:#666;font-size:0.9em">Pricing note: when the backend log does not provide direct cost, this report estimates cost from local model pricing metadata in docs/reference/openai-model-pricing.json and the token counts available for the call.</div>' if has_estimated_cost else ''}
{''.join(popups)}
</body>
</html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _child_output_path(parent_output: Path, slug: str) -> Path:
    suffix = parent_output.suffix or ".html"
    return parent_output.with_name(f"{parent_output.stem}-{slug}{suffix}")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate timeline report for a methodology-runner workspace, prompt-runner run directory, or comparison manifest."
    )
    parser.add_argument("path", help="Path to analyze (workspace or run directory).")
    parser.add_argument("--output", "-o", default=None, help="Output HTML path.")
    args = parser.parse_args(argv)

    input_path = Path(args.path).resolve()
    if not input_path.exists():
        print(f"Path not found: {input_path}", file=sys.stderr)
        return 1

    default_output = (
        input_path.with_suffix(".html")
        if input_path.is_file()
        else input_path / "timeline.html"
    )
    output = Path(args.output) if args.output else default_output

    try:
        document = load_report_document(input_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    if MethodologyWorkspaceAdapter.matches(input_path):
        nested = discover_ph006_child_report(input_path)
        if nested is not None:
            child_slug, child_run_dir = nested
            child_output = _child_output_path(output, child_slug)
            rel_child = child_output.name
            rel_parent = output.name

            for tl in document.timelines:
                if tl.phase_id == "PH-006-incremental-implementation":
                    tl.drilldown_links.append(("drill down", rel_child))
                    break

            child_document = load_report_document(child_run_dir)
            child_document.run_title = f"{child_slug.replace('-', ' ').title()} Timeline"
            child_document.nav_links.append(("bubble up", rel_parent))

            output.write_text(render_html(document), encoding="utf-8")
            child_output.write_text(render_html(child_document), encoding="utf-8")
            print(f"Timeline written to {output}")
            print(f"Nested timeline written to {child_output}")
            return 0

    html = render_html(document)
    output.write_text(html, encoding="utf-8")
    print(f"Timeline written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
