#!/usr/bin/env python3
# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Modified with AI assistance.
# Responsibility: Generate privacy-safe cross-tool, Codex, and Junie execution reports and report catalogs.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

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
  - A Junie session directory (contains events.jsonl)
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import getpass
import hashlib
import io
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import yaml
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from copy import deepcopy
from functools import lru_cache
from urllib.parse import quote


ProgressCallback = Callable[[int, str, str], None]
WorkerProgressCallback = Callable[[int, str, str, str], None]
ItemProgressCallback = Callable[[int, int, str, str, str | None], None]


def _current_worker_id() -> str:
    """Return a stable one-based label for the current bounded worker."""

    suffix = threading.current_thread().name.rsplit("_", 1)[-1]
    return str(int(suffix) + 1) if suffix.isdigit() else "1"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POPUP_TRUNCATE_CHARS = 20_000_000  # 20 MB
MIN_BAR_PCT = 0.5
REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKOUT_PRICING_FILE = REPO_ROOT / "docs" / "reference" / "openai-model-pricing.json"
_INSTALLED_DATA_ROOT = Path(__file__).resolve().parent
PRICING_FILE = (
    _CHECKOUT_PRICING_FILE
    if _CHECKOUT_PRICING_FILE.is_file()
    else _INSTALLED_DATA_ROOT / "openai-model-pricing.json"
)
_CHECKOUT_FORMATTER_CONFIG = REPO_ROOT / "tools" / "report" / "tool-formatters.json"
DEFAULT_TOOL_FORMATTER_CONFIG = (
    _CHECKOUT_FORMATTER_CONFIG
    if _CHECKOUT_FORMATTER_CONFIG.is_file()
    else _INSTALLED_DATA_ROOT / "tool-formatters.json"
)
PRICING_RATE_KEYS = ("input_per_million", "cached_input_per_million", "output_per_million")
CODEX_CREDIT_RATE_KEYS = (
    "codex_credits_input_per_million",
    "codex_credits_cached_input_per_million",
    "codex_credits_output_per_million",
)
CODEX_ROLLOUT_FORMAT = "codex-rollout-metrics/v1"
CODEX_ROLLOUT_PARSER_VERSION = "1.20.0"
NATIVE_DISCOVERY_PROTOCOL_VERSION = 1
AGENT_EXECUTION_METRICS_TITLE = "Agent Execution Metrics"
COPYRIGHT_NOTICE = "© 2026 Martin.Bechard@DevConsult.ca · MIT License"
CODEX_TOOL_ARGUMENT_SUMMARY_CHARS = 500
CODEX_MESSAGE_PREVIEW_CHARS = 50
TOOL_RESULT_PREVIEW_CHARS = 200
TOOL_ARGUMENT_CLAMP_CHARS = 320
TOOL_ARGUMENT_RAW_CHARS = 20_000
TOOL_RESULT_RAW_CHARS = 20_000
JUNIE_SESSION_FORMAT = "junie-session-metrics/v1"
JUNIE_SESSION_PARSER_VERSION = "1.7.0"


def _with_copyright_footer(document: str) -> str:
    """Add the visible standalone-report copyright footer once."""

    if COPYRIGHT_NOTICE in document:
        return document
    footer = (
        '<footer class="agent-report-copyright" '
        'style="margin:2rem 1rem .75rem;padding-top:.75rem;border-top:1px solid '
        'currentColor;opacity:.62;text-align:center;font:10px/1.4 '
        'ui-monospace,SFMono-Regular,Menlo,monospace">'
        f"{COPYRIGHT_NOTICE}</footer>"
    )
    if "</body>" not in document:
        return document + footer
    return document.replace("</body>", footer + "</body>", 1)
CODEX_CONTENT_ARGUMENT_KEYS = frozenset(
    {
        "body",
        "chars",
        "content",
        "input",
        "message",
        "output",
        "payload",
        "prompt",
        "result",
        "text",
    }
)
_SKILL_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._:-])(?P<name>[A-Za-z0-9][A-Za-z0-9._:-]*)/SKILL\.md\b"
)
_VERDICT_PREFIX_CHARS = "#>*_`~-"
_REVIEW_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
_UPDATE_PLAN_ITEM_PATTERN = re.compile(
    r"\{\s*[\"']?step[\"']?\s*:\s*\"(?P<step>(?:\\.|[^\"\\])*)\"\s*,\s*"
    r"[\"']?status[\"']?\s*:\s*\"(?P<status>completed|in_progress|pending)\"\s*\}"
)
_CODEX_DELEGATION_BLOCK_PATTERN = re.compile(
    r"<codex_delegation\b[^>]*>(?P<body>.*?)</codex_delegation>",
    re.IGNORECASE | re.DOTALL,
)
_CODEX_DELEGATION_LINE_PATTERN = re.compile(
    r"(?:<|\\u003c)codex_delegation",
    re.IGNORECASE,
)
_CODEX_DELEGATION_SOURCE_PATTERN = re.compile(
    r"<source_thread_id>\s*(?P<source>[A-Za-z0-9][A-Za-z0-9._:/-]*)\s*"
    r"</source_thread_id>",
    re.IGNORECASE,
)
_CODEX_DELEGATION_INPUT_PATTERN = re.compile(
    r"<input>\s*(?P<input>.*?)(?:\s*</input>|\s*$)",
    re.IGNORECASE | re.DOTALL,
)


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
        return _fmt_duration(self.duration_seconds)


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
        return _fmt_duration(self.total_seconds)

    @property
    def total_cost(self) -> float:
        return sum(s.detail.cost_usd for s in self.steps if s.detail)


@dataclass
class ForkSection:
    """A fork point with its variants, each containing their own steps."""
    fork_index: int
    fork_title: str
    variants: dict[str, list[Step]]  # variant_name -> steps
    variant_titles: dict[str, str] = field(default_factory=dict)
    selector_steps: list[Step] = field(default_factory=list)
    selected_variant: str = ""
    selector_rationale: str = ""


@dataclass
class ComparisonManifest:
    title: str
    mode: str
    runs: list[tuple[str, Path]]


@dataclass
class ReportDocument:
    """Backend-neutral render input for legacy timelines or one native-agent run."""

    run_title: str
    workspace: Path
    timelines: list[PhaseTimeline] = field(default_factory=list)
    shared_steps: list[Step] = field(default_factory=list)
    fork_sections: list[ForkSection] = field(default_factory=list)
    nav_links: list[tuple[str, str]] = field(default_factory=list)
    codex_run: CodexRunMetrics | None = None


@dataclass
class UsageTotals:
    """Exclusive token counters with cache and reasoning subset semantics."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_create_input_tokens: int = 0
    uncached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    processed_tokens: int = 0

    def __add__(self, other: UsageTotals) -> UsageTotals:
        """Add disjoint usage accounting units without changing subset semantics."""
        return UsageTotals(
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            cache_create_input_tokens=(
                self.cache_create_input_tokens + other.cache_create_input_tokens
            ),
            uncached_input_tokens=self.uncached_input_tokens + other.uncached_input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            processed_tokens=self.processed_tokens + other.processed_tokens,
        )

    def subtract(self, previous: UsageTotals) -> UsageTotals:
        """Return an exclusive cumulative delta from an earlier snapshot."""
        return UsageTotals(
            input_tokens=self.input_tokens - previous.input_tokens,
            cached_input_tokens=self.cached_input_tokens - previous.cached_input_tokens,
            cache_create_input_tokens=(
                self.cache_create_input_tokens - previous.cache_create_input_tokens
            ),
            uncached_input_tokens=self.uncached_input_tokens - previous.uncached_input_tokens,
            output_tokens=self.output_tokens - previous.output_tokens,
            reasoning_tokens=self.reasoning_tokens - previous.reasoning_tokens,
            processed_tokens=self.processed_tokens - previous.processed_tokens,
        )

    @property
    def direct_input_tokens(self) -> int:
        """Return uncached input excluding tokens written to a provider cache."""

        return max(0, self.uncached_input_tokens - self.cache_create_input_tokens)

    def is_monotonic_from(self, previous: UsageTotals) -> bool:
        """Return whether every cumulative counter is at least its prior value."""
        return all(
            current >= earlier
            for current, earlier in zip(
                asdict(self).values(),
                asdict(previous).values(),
            )
        )


@dataclass
class ResponseUsage:
    """One positive exclusive response delta with source provenance."""

    event_timestamp: str
    usage: UsageTotals
    turn_id: str | None
    source_path: str
    source_ordinal: int
    model: str = ""
    effort: str = ""
    recorded_cost_usd: float | None = None
    derivation_method: str = "cumulative-delta"
    attribution_confidence: str = "exact"
    started_at: str = ""
    first_output_at: str = ""
    last_output_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0
    ttft_ms: int | None = None
    decode_time_ms: int | None = None
    queue_time_ms: int | None = None
    timing_confidence: str = "unavailable"
    timing_method: str = "unavailable"
    context_input_tokens: int = 0
    context_cached_input_tokens: int = 0
    context_total_tokens: int = 0
    context_capacity: int = 0
    context_occupancy_percent: float | None = None
    reported_usage: UsageTotals = field(default_factory=UsageTotals)


@dataclass(frozen=True)
class _TokenFundingEvent:
    """Token-summary funding telemetry attached to one source event."""

    event_timestamp: str
    source_path: str
    source_ordinal: int
    usage: UsageTotals = field(default_factory=UsageTotals)
    model: str = ""
    plan_type: str = ""
    funding_source: str = "subscription"
    subscription_used_percent: float | None = None
    credit_balance: float | None = None
    has_credits: bool | None = None


@dataclass
class ContextSnapshot:
    """Direct per-call context telemetry without retaining request content."""

    event_timestamp: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    capacity: int
    remaining_tokens: int
    occupancy_percent: float
    cached_input_percent: float
    source_path: str
    source_ordinal: int
    is_compaction_marker: bool = False
    derivation_method: str = "direct-last-token-usage"


@dataclass
class ContextCompaction:
    """One recorded or inferred context-size reduction."""

    event_timestamp: str
    before_total_tokens: int
    after_total_tokens: int
    capacity: int
    window_number: int | None
    window_id: str
    source_path: str
    source_ordinal: int
    recorded: bool = False
    derivation_method: str = "recorded-compaction-event"


@dataclass
class ContextSummary:
    """Current and maximum context usage for the selected root thread."""

    average_total_tokens: int = 0
    average_percent: float | None = None
    current_total_tokens: int = 0
    current_input_tokens: int = 0
    current_cached_input_tokens: int = 0
    capacity: int = 0
    remaining_tokens: int = 0
    occupancy_percent: float | None = None
    cached_input_percent: float | None = None
    high_water_tokens: int = 0
    high_water_percent: float | None = None
    compaction_count: int = 0
    last_observed_at: str = ""
    evidence: str = "unavailable"


@dataclass
class ContextTrendBucket:
    """One fixed-width context-growth bucket for the selected root thread."""

    started_at: str
    snapshot_count: int
    first_total_tokens: int
    last_total_tokens: int
    low_total_tokens: int
    high_total_tokens: int
    capacity: int
    compaction_count: int


@dataclass
class InferenceSummary:
    """Size-aware aggregate over calls with explicit timing confidence."""

    call_count: int = 0
    measured_call_count: int = 0
    decode_measured_call_count: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    inference_time_ms: int = 0
    decode_time_ms: int = 0
    end_to_end_tokens_per_second: float | None = None
    decode_tokens_per_second: float | None = None
    median_ttft_ms: float | None = None
    p50_call_tokens_per_second: float | None = None
    p90_call_tokens_per_second: float | None = None
    evidence: str = "unavailable"


@dataclass
class InferenceTrendBucket:
    """One fixed-width inference-rate bucket."""

    started_at: str
    call_count: int
    output_tokens: int
    inference_time_ms: int
    tokens_per_second: float | None


@dataclass
class InferenceSizeBand:
    """Inference rate for comparable response-size calls."""

    label: str
    call_count: int
    output_tokens: int
    inference_time_ms: int
    weighted_tokens_per_second: float | None
    median_call_tokens_per_second: float | None


@dataclass
class RuntimeStateInterval:
    """One mutually exclusive per-thread runtime-state interval."""

    thread_id: str
    turn_id: str | None
    state: str
    started_at: str
    completed_at: str
    duration_ms: int
    derivation_method: str
    attribution_confidence: str
    detail: str = ""


@dataclass
class RuntimeStateSummary:
    """Agent-time and concurrency-aware wall-time for one runtime state."""

    state: str
    interval_count: int
    agent_time_ms: int
    run_time_ms: int
    direct_interval_count: int
    inferred_interval_count: int


@dataclass
class WorkItemClaimEvent:
    """Bounded exact-ID lifecycle evidence from a successful claim tool call."""

    operation: str
    event_timestamp: str
    work_item_id: str
    claim_id: str
    activity: str
    disposition: str
    blocker_reference: str
    agent: str
    root_task_id: str
    outcome: str
    thread_id: str
    source_path: str
    source_ordinal: int
    transport: str


@dataclass
class WorkItemSegment:
    """One exact claim-bounded work or update activity segment."""

    work_item_id: str
    claim_id: str
    activity: str
    disposition: str
    blocker_reference: str
    agent: str
    thread_id: str
    started_at: str
    ended_at: str
    duration_ms: int
    open: bool
    usage: UsageTotals
    inference: InferenceSummary
    runtime_state_ms: dict[str, int]
    attribution_confidence: str = "exact"


@dataclass
class AgentTurn:
    """One task interval and the response usage attributable to it."""

    thread_id: str
    turn_id: str
    started_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0
    time_to_first_token_ms: int | None = None
    outcome: str = "active"
    abort_reason: str = ""
    abort_event_timestamp: str = ""
    abort_initiator_thread_id: str = ""
    abort_initiator_agent_path: str = ""
    abort_initiator_turn_id: str = ""
    abort_initiator_relationship: str = ""
    abort_request_source_path: str = ""
    abort_request_source_ordinal: int = 0
    usage: UsageTotals = field(default_factory=UsageTotals)
    skills_used: list[str] = field(default_factory=list)
    mcp_skills_loaded: list[str] = field(default_factory=list)
    bash_skills_loaded: list[str] = field(default_factory=list)
    mcp_call_count: int = 0
    run_id: str = ""
    phase_id: str = ""
    lane_id: str = ""
    work_unit_id: str = ""
    activity: str = ""
    attribution_confidence: str = "unattributed"
    attribution_reason: str = "no explicit or reliable work identifier"
    source_path: str = ""
    source_ordinal: int = 0


@dataclass
class AgentActivity:
    """One non-tool narrative event retained for a turn drilldown."""

    thread_id: str
    turn_id: str | None
    activity_type: str
    event_timestamp: str
    source_path: str
    source_ordinal: int
    summary: str = ""
    content: str = ""
    model: str = ""


@dataclass
class ToolInterval:
    """A tool timing record with sanitized arguments and optional result content."""

    thread_id: str
    turn_id: str | None
    tool_name: str
    started_at: str
    completed_at: str
    duration_ms: int
    derivation_method: str
    attribution_confidence: str
    argument_summary: str
    source_path: str
    source_start_ordinal: int
    source_end_ordinal: int
    argument_content: str = ""
    result_summary: str = ""
    result_content: str = ""
    model: str = ""


@dataclass(frozen=True)
class AgentSequenceEvent:
    """One privacy-safe coordination or lifecycle edge between report agents."""

    event_timestamp: str
    kind: str
    source_thread_id: str
    target_thread_id: str
    label: str
    detail: str = ""
    source_ordinal: int = 0


@dataclass(frozen=True)
class AgentSequenceThought:
    """One privacy-safe reasoning summary placed on an agent lifeline."""

    event_timestamp: str
    thread_id: str
    detail: str
    source_ordinal: int = 0


@dataclass
class McpCallInterval:
    """One completed native MCP invocation retained for reporting.

    The recorded duration measures MCP execution after approval; it does not
    include Guardian or user-review latency. Arguments and results are stored
    only after the report's bounded redaction and special-formatting rules run.
    """

    thread_id: str
    turn_id: str | None
    call_id: str
    server_name: str
    tool_name: str
    started_at: str
    completed_at: str
    duration_ms: int
    argument_summary: str
    result_summary: str
    result_content: str
    succeeded: bool
    source_path: str
    source_ordinal: int
    skills_loaded: list[str] = field(default_factory=list)
    argument_content: str = ""
    model: str = ""


@dataclass(frozen=True)
class ToolFormatterField:
    name: str
    json_path: str = ""
    regex: re.Pattern[str] | None = None
    group: str = ""
    transform: str = "identity"


@dataclass(frozen=True)
class ToolFormatterRule:
    rule_id: str
    tool_name: str
    arguments_regex: re.Pattern[str] | None
    fields: tuple[ToolFormatterField, ...]
    parts: tuple[str, ...]
    separator: str = " · "


@dataclass(frozen=True)
class ToolFormatterConfig:
    version: int
    rules: tuple[ToolFormatterRule, ...]
    source_path: str = ""


@dataclass(frozen=True)
class FormattedToolArgument:
    summary: str
    rule_id: str


@dataclass
class CodexThreadMetrics:
    """Normalized metrics for one native agent accounting boundary."""

    thread_id: str
    parent_thread_id: str = ""
    thread_name: str = ""
    task_title: str = ""
    agent_path: str = ""
    agent_role: str = ""
    agent_nickname: str = ""
    model: str = ""
    effort: str = ""
    plan_type: str = ""
    recorded_cost_usd: float | None = None
    started_at: str = ""
    last_observed_at: str = ""
    token_totals: UsageTotals = field(default_factory=UsageTotals)
    unattributed_usage: UsageTotals = field(default_factory=UsageTotals)
    responses: list[ResponseUsage] = field(default_factory=list)
    turns: list[AgentTurn] = field(default_factory=list)
    activities: list[AgentActivity] = field(default_factory=list)
    tool_intervals: list[ToolInterval] = field(default_factory=list)
    mcp_calls: list[McpCallInterval] = field(default_factory=list)
    context_snapshots: list[ContextSnapshot] = field(default_factory=list)
    compactions: list[ContextCompaction] = field(default_factory=list)
    work_item_claim_events: list[WorkItemClaimEvent] = field(default_factory=list)
    skills_used: list[str] = field(default_factory=list)
    mcp_skills_loaded: list[str] = field(default_factory=list)
    bash_skills_loaded: list[str] = field(default_factory=list)
    terminal_state: str = "indeterminate"
    source_path: str = ""
    diagnostics: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _AgentCatalogEntry:
    """Minimal local metadata used to select one reportable agent log."""

    run_id: str
    parent_thread_id: str
    started_at: datetime
    task_title: str
    workspace: str
    source_path: Path
    source_store: str


@dataclass
class SourceManifestEntry:
    """Identity and optional immutable digest for one source rollout."""

    thread_id: str
    path: str
    size_bytes: int
    modified_at_ns: int
    sha256: str = ""


@dataclass
class CostAssessment:
    """Recorded or estimated monetary status without implying a Codex charge."""

    status: str
    currency: str = "USD"
    pricing_model: str = ""
    pricing_version: str = ""
    pricing_digest: str = ""
    input_cost: float | None = None
    cached_input_cost: float | None = None
    output_cost: float | None = None
    total_cost: float | None = None
    method: str = "unavailable"


@dataclass
class WorkUnitMetrics:
    """Turn-owned semantic aggregation with explicit attribution confidence."""

    work_unit_id: str
    phase_id: str
    lane_id: str
    activity: str
    turn_ids: list[str]
    usage: UsageTotals
    allocation_method: str
    attribution_confidence: str
    cost: CostAssessment


@dataclass
class PhaseLaneMetrics:
    """A concurrency-aware phase and lane aggregation of owned turns."""

    phase_id: str
    lane_id: str
    work_unit_ids: list[str]
    turn_ids: list[str]
    wall_started_at: str
    wall_ended_at: str
    wall_time_ms: int
    active_time_ms: int
    agent_time_ms: int
    usage: UsageTotals
    confidence_counts: dict[str, int]
    cost: CostAssessment


@dataclass
class CodexParentContext:
    """One non-aggregated parent reference for a delegated report root."""

    thread_id: str
    task_title: str
    source_path: str


@dataclass
class CodexRunMetrics:
    """A normalized native-agent run with auditable execution aggregates."""

    run_id: str
    root_thread_id: str
    state: str
    observed_at: str
    wall_started_at: str
    wall_ended_at: str
    wall_time_ms: int
    agent_time_ms: int
    active_time_ms: int
    tool_time_ms: int
    critical_path_ms: int
    critical_path_method: str
    peak_concurrency: int
    usage_totals: UsageTotals
    threads: list[CodexThreadMetrics]
    work_units: list[WorkUnitMetrics]
    phase_lanes: list[PhaseLaneMetrics]
    cost: CostAssessment
    source_manifest: list[SourceManifestEntry]
    diagnostics: list[str]
    parser_version: str = CODEX_ROLLOUT_PARSER_VERSION
    format_version: str = CODEX_ROLLOUT_FORMAT
    pricing_version: str = ""
    pricing_digest: str = ""
    runtime: str = "Codex"
    run_label: str = ""
    parent_context: CodexParentContext | None = None
    context_summary: ContextSummary = field(default_factory=ContextSummary)
    inference_summary: InferenceSummary = field(default_factory=InferenceSummary)
    inference_trends: list[InferenceTrendBucket] = field(default_factory=list)
    inference_size_bands: list[InferenceSizeBand] = field(default_factory=list)
    context_trends: list[ContextTrendBucket] = field(default_factory=list)
    runtime_intervals: list[RuntimeStateInterval] = field(default_factory=list)
    runtime_states: list[RuntimeStateSummary] = field(default_factory=list)
    all_agents_waiting_ms: int = 0
    work_item_segments: list[WorkItemSegment] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Native Codex Desktop rollout parser and aggregation
# ---------------------------------------------------------------------------


def _usage_from_snapshot(snapshot: object) -> UsageTotals | None:
    if not isinstance(snapshot, dict):
        return None
    values: dict[str, int] = {}
    for key in (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    ):
        raw = snapshot.get(key, 0)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            return None
        values[key] = raw
    input_tokens = values["input_tokens"]
    cached_tokens = min(input_tokens, values["cached_input_tokens"])
    output_tokens = values["output_tokens"]
    reasoning_tokens = min(output_tokens, values["reasoning_output_tokens"])
    return UsageTotals(
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        uncached_input_tokens=input_tokens - cached_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        processed_tokens=input_tokens + output_tokens,
    )


def _usage_is_zero(usage: UsageTotals) -> bool:
    return usage.processed_tokens == 0


def _usage_nonnegative_difference(current: UsageTotals, previous: UsageTotals) -> UsageTotals:
    if not current.is_monotonic_from(previous):
        return UsageTotals()
    return current.subtract(previous)


def _nonnegative_int(value: object) -> int | None:
    """Return a direct non-negative integer without accepting booleans."""

    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def _context_snapshot(
    usage: object,
    capacity_value: object,
    *,
    timestamp: str,
    path: Path,
    ordinal: int,
) -> ContextSnapshot | None:
    """Normalize direct last-call context counters when the full shape is valid."""

    if not isinstance(usage, dict):
        return None
    capacity = _nonnegative_int(capacity_value)
    input_tokens = _nonnegative_int(usage.get("input_tokens", 0))
    cached_tokens = _nonnegative_int(usage.get("cached_input_tokens", 0))
    output_tokens = _nonnegative_int(usage.get("output_tokens", 0))
    reasoning_tokens = _nonnegative_int(usage.get("reasoning_output_tokens", 0))
    total_tokens = _nonnegative_int(usage.get("total_tokens"))
    if None in {
        capacity,
        input_tokens,
        cached_tokens,
        output_tokens,
        reasoning_tokens,
        total_tokens,
    }:
        return None
    assert capacity is not None
    assert input_tokens is not None
    assert cached_tokens is not None
    assert output_tokens is not None
    assert reasoning_tokens is not None
    assert total_tokens is not None
    cached_tokens = min(cached_tokens, input_tokens)
    reasoning_tokens = min(reasoning_tokens, output_tokens)
    occupancy = total_tokens / capacity * 100 if capacity else 0.0
    cached_share = cached_tokens / input_tokens * 100 if input_tokens else 0.0
    is_marker = (
        total_tokens > 0
        and input_tokens == 0
        and output_tokens == 0
        and reasoning_tokens == 0
    )
    return ContextSnapshot(
        event_timestamp=_normalize_timestamp(timestamp),
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
        capacity=capacity,
        remaining_tokens=max(0, capacity - total_tokens),
        occupancy_percent=occupancy,
        cached_input_percent=cached_share,
        source_path=str(path),
        source_ordinal=ordinal,
        is_compaction_marker=is_marker,
    )


def _bounded_claim_value(value: object) -> str:
    """Retain only the canonical bounded scalar allowed by the claim contract."""

    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or "\n" in text or "\r" in text or len(text) > 200:
        return ""
    return text


def _claim_result(result: object) -> dict[str, object]:
    """Return the claim result object from a native MCP result envelope."""

    structured = _mcp_structured_result(result)
    nested = structured.get("result")
    return nested if isinstance(nested, dict) else structured


def _work_item_claim_event_from_mcp(
    *,
    thread_id: str,
    timestamp: str,
    path: Path,
    ordinal: int,
    server_name: str,
    tool_name: str,
    arguments: object,
    result: object,
) -> WorkItemClaimEvent | None:
    """Extract successful exact-ID acquire/release evidence without payload text."""

    normalized_tool = tool_name.casefold().replace("-", "_")
    if normalized_tool not in {"claim_acquire", "claim_release"}:
        return None
    if not isinstance(arguments, dict):
        return None
    result_fields = _claim_result(result)
    outcome = _bounded_claim_value(result_fields.get("outcome"))
    operation = "acquire" if normalized_tool == "claim_acquire" else "release"
    if operation == "acquire" and not outcome.endswith("ACQUIRED"):
        return None
    if operation == "release" and outcome != "RELEASED":
        return None
    work_item_id = _bounded_claim_value(
        result_fields.get("work_item_id") or arguments.get("work_item_id")
    )
    claim_id = _bounded_claim_value(
        result_fields.get("claim_id") or arguments.get("claim_id")
    )
    activity = _bounded_claim_value(
        result_fields.get("activity") or arguments.get("activity")
    )
    disposition = _bounded_claim_value(
        result_fields.get("disposition") or arguments.get("disposition")
    )
    if not work_item_id or not claim_id:
        return None
    if operation == "acquire" and activity not in {"work", "update"}:
        return None
    if operation == "release" and disposition not in {"done", "blocked", "handoff"}:
        return None
    return WorkItemClaimEvent(
        operation=operation,
        event_timestamp=_normalize_timestamp(timestamp),
        work_item_id=work_item_id,
        claim_id=claim_id,
        activity=activity,
        disposition=disposition,
        blocker_reference=_bounded_claim_value(
            result_fields.get("blocker_reference")
            or arguments.get("blocker_reference")
        ),
        agent=_bounded_claim_value(
            result_fields.get("agent") or arguments.get("agent")
        ),
        root_task_id=_bounded_claim_value(
            result_fields.get("root_task_id") or arguments.get("root_task_id")
        ),
        outcome=outcome,
        thread_id=thread_id,
        source_path=str(path),
        source_ordinal=ordinal,
        transport=f"mcp:{server_name}",
    )


def _parse_jsonl_append_safe(path: Path) -> tuple[list[tuple[int, dict[str, object]]], list[str]]:
    records: list[tuple[int, dict[str, object]]] = []
    diagnostics: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [], [f"unreadable rollout {path}: {exc}"]
    lines = raw.splitlines()
    for ordinal, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            if ordinal == len(lines):
                diagnostics.append(f"incomplete final JSONL line at {path}:{ordinal}")
            else:
                diagnostics.append(f"malformed JSONL record at {path}:{ordinal}")
            continue
        if isinstance(value, dict):
            records.append((ordinal, value))
        else:
            diagnostics.append(f"non-object JSONL record at {path}:{ordinal}")
    return records, diagnostics


def _spawn_metadata(payload: dict[str, object]) -> tuple[str, str, str]:
    source = payload.get("source")
    if not isinstance(source, dict):
        return "", "", ""
    subagent = source.get("subagent")
    if not isinstance(subagent, dict):
        return "", "", ""
    thread_spawn = subagent.get("thread_spawn")
    if not isinstance(thread_spawn, dict):
        return "", "", ""
    return (
        str(thread_spawn.get("parent_thread_id") or ""),
        str(thread_spawn.get("agent_path") or ""),
        str(thread_spawn.get("agent_nickname") or ""),
    )


def _spawn_agent_role(payload: dict[str, object]) -> str:
    role = payload.get("agent_role")
    source = payload.get("source")
    if not role and isinstance(source, dict):
        subagent = source.get("subagent")
        thread_spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
        if isinstance(thread_spawn, dict):
            role = thread_spawn.get("agent_role")
    return str(role or "")


def _recorded_rollout_identity(
    record: dict[str, object],
) -> tuple[str, str, str, str] | None:
    if record.get("type") != "session_meta":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None
    thread_id = str(payload.get("id") or payload.get("session_id") or "")
    if not thread_id:
        return None
    parent_thread_id, agent_path, agent_nickname = _spawn_metadata(payload)
    return thread_id, parent_thread_id, agent_path, agent_nickname


def _rollout_identity(path: Path) -> tuple[str, str, str, str] | None:
    """Stream until one rollout identity is found instead of parsing the file."""

    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                identity = _recorded_rollout_identity(record)
                if identity is not None:
                    return identity
    except OSError:
        return None
    return None


def _codex_delegation_values(content: str) -> list[tuple[str, str, str]]:
    """Return delegation sources plus preview and full bounded, redacted input."""

    values: list[tuple[str, str, str]] = []
    for block_match in _CODEX_DELEGATION_BLOCK_PATTERN.finditer(content):
        body = block_match.group("body")
        source_match = _CODEX_DELEGATION_SOURCE_PATTERN.search(body)
        if source_match is None:
            continue
        input_match = _CODEX_DELEGATION_INPUT_PATTERN.search(body)
        input_text = input_match.group("input").strip() if input_match else ""
        preview = _message_argument_preview(input_text) if input_text else ""
        detail = _tool_argument_content(input_text) if input_text else ""
        values.append((source_match.group("source"), preview, detail))
    return values


def _metadata_value(payload: dict[str, object], context: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if value is None or value == "":
        value = context.get(key)
    return str(value) if value is not None else ""


def _turn_attribution(
    payload: dict[str, object],
    context: dict[str, object],
    *,
    agent_path: str,
    agent_nickname: str,
) -> tuple[dict[str, str], str, str]:
    fields = {
        key: _metadata_value(payload, context, key)
        for key in ("run_id", "phase_id", "lane_id", "work_unit_id", "activity")
    }
    if any(fields.values()):
        return fields, "exact", "explicit task or turn metadata"
    inferred = (agent_path.rsplit("/", 1)[-1] if agent_path else "") or agent_nickname
    if inferred:
        fields["work_unit_id"] = inferred
        return fields, "inferred", "spawn-time agent identity"
    return fields, "unattributed", "no explicit or reliable work identifier"


def _extract_tool_wall_time_ms(output: object) -> int | None:
    value = output
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    raw = value.get("wall_time_seconds")
    if not isinstance(raw, (int, float)) or isinstance(raw, bool) or raw < 0:
        return None
    return round(float(raw) * 1000)


def _is_sensitive_argument_key(key: str) -> bool:
    normalized = key.strip().lstrip("-").lower().replace("-", "_")
    if normalized in {
        "api_key",
        "client_secret",
        "private_key",
        "access_token",
        "refresh_token",
    }:
        return True
    return any(
        part in {
            "authorization",
            "cookie",
            "credential",
            "credentials",
            "passwd",
            "password",
            "secret",
            "token",
        }
        for part in normalized.split("_")
    )


def _argument_content_size(value: object) -> int:
    if isinstance(value, str):
        return len(value)
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _sanitize_structured_argument(key: str, value: object) -> object:
    normalized_key = key.strip().lower().replace("-", "_")
    if _is_sensitive_argument_key(normalized_key):
        return "[redacted]"
    if normalized_key in CODEX_CONTENT_ARGUMENT_KEYS:
        return f"[{_argument_content_size(value):,} chars]"
    if isinstance(value, dict):
        return {
            str(child_key): _sanitize_structured_argument(str(child_key), child_value)
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_structured_argument("", child) for child in value]
    return value


def _truncate_argument_summary(summary: str) -> str:
    if len(summary) <= CODEX_TOOL_ARGUMENT_SUMMARY_CHARS:
        return summary
    return summary[: CODEX_TOOL_ARGUMENT_SUMMARY_CHARS - 3].rstrip() + "..."


def _redact_unstructured_text(value: str) -> str:
    """Redact common credential forms while preserving the source layout."""

    def redact_assignment(match: re.Match[str]) -> str:
        key = match.group("key")
        if not _is_sensitive_argument_key(key):
            return match.group(0)
        return f"{key}{match.group('separator')}[redacted]"

    summary = re.sub(
        r"(?P<key>[A-Za-z_][A-Za-z0-9_-]*)(?P<separator>\s*=\s*)"
        r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s]+)",
        redact_assignment,
        value,
    )

    def redact_mapping_value(match: re.Match[str]) -> str:
        key = match.group("key")
        if not _is_sensitive_argument_key(key):
            return match.group(0)
        raw_value = match.group("value")
        quote = raw_value[0] if raw_value[:1] in {'"', "'"} else ""
        return f"{key}{match.group('separator')}{quote}[redacted]{quote}"

    summary = re.sub(
        r"(?P<key>[A-Za-z_][A-Za-z0-9_-]*)(?P<separator>\s*:\s*)"
        r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,}]+)",
        redact_mapping_value,
        summary,
    )
    summary = re.sub(
        r"(?i)(?P<prefix>\b(?:authorization|bearer)\s*[:=]?\s+)(?P<value>\S+)",
        lambda match: f"{match.group('prefix')}[redacted]",
        summary,
    )
    summary = re.sub(
        r"(?i)(?P<prefix>--(?:api-key|client-secret|private-key|access-token|"
        r"refresh-token|token|secret|password|passwd|authorization|cookie|credential)"
        r"(?:=|\s+))(?P<value>\"[^\"]*\"|'[^']*'|\S+)",
        lambda match: f"{match.group('prefix')}[redacted]",
        summary,
    )
    return summary


def _sanitize_unstructured_argument(value: str) -> str:
    summary = _redact_unstructured_text(value)
    return _truncate_argument_summary(" ".join(summary.split()) or "—")


def _tool_argument_content(value: str) -> str:
    """Return bounded, secret-redacted source arguments for local disclosure."""

    content = _redact_unstructured_text(value)
    if len(content) <= TOOL_ARGUMENT_RAW_CHARS:
        return content
    omitted = len(content) - TOOL_ARGUMENT_RAW_CHARS
    return content[:TOOL_ARGUMENT_RAW_CHARS] + f"\n… [{omitted:,} chars omitted]"


def _tool_argument_payload_content(payload: dict[str, object]) -> str:
    """Return bounded, secret-redacted source arguments from a tool event."""

    value = payload.get("arguments")
    if value is None:
        value = payload.get("input")
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        try:
            structured = json.loads(value)
        except json.JSONDecodeError:
            return _tool_argument_content(value)
    else:
        structured = value
    if isinstance(structured, (dict, list)):
        value = json.dumps(
            _sanitize_structured_argument("", structured),
            ensure_ascii=False,
            indent=2,
        )
    return _tool_argument_content(str(value))


def _sanitize_result_value(value: object) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, child in value.items():
            rendered_key = str(key)
            normalized_key = rendered_key.strip().lower().replace("-", "_")
            if _is_sensitive_argument_key(normalized_key):
                sanitized[rendered_key] = "[redacted]"
            elif normalized_key in CODEX_CONTENT_ARGUMENT_KEYS:
                sanitized[rendered_key] = f"[{_argument_content_size(child):,} chars]"
            else:
                sanitized[rendered_key] = _sanitize_result_value(child)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_result_value(child) for child in value]
    return value


def _tool_result_content(value: object) -> str:
    """Return bounded, secret-redacted tool output for local report disclosure."""

    structured = value
    if isinstance(value, str):
        try:
            structured = json.loads(value)
        except json.JSONDecodeError:
            content = _redact_unstructured_text(value)
        else:
            content = json.dumps(
                _sanitize_result_value(structured),
                ensure_ascii=False,
                indent=2,
            )
    elif isinstance(value, (dict, list)):
        content = json.dumps(
            _sanitize_result_value(value),
            ensure_ascii=False,
            indent=2,
        )
    elif value is None:
        return ""
    else:
        content = str(value)
    if len(content) <= TOOL_RESULT_RAW_CHARS:
        return content
    omitted = len(content) - TOOL_RESULT_RAW_CHARS
    return content[:TOOL_RESULT_RAW_CHARS] + f"\n… [{omitted:,} chars omitted]"


def _tool_result_summary(content: str) -> str:
    if not content:
        return ""
    compact = " ".join(content.split())
    preview = compact[:TOOL_RESULT_PREVIEW_CHARS].rstrip()
    ellipsis = "…" if len(compact) > TOOL_RESULT_PREVIEW_CHARS else ""
    return f"{preview}{ellipsis} [{len(content):,} chars]"


def _looks_like_encrypted_message(value: str) -> bool:
    return (
        len(value) >= 80
        and value.startswith("gAAAAA")
        and re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value) is not None
    )


def _message_argument_preview(value: str) -> str:
    if _looks_like_encrypted_message(value):
        return f"[encrypted message, {len(value):,} chars]"
    sanitized = _sanitize_unstructured_argument(value)
    preview = sanitized[:CODEX_MESSAGE_PREVIEW_CHARS].rstrip()
    ellipsis = "…" if len(value) > CODEX_MESSAGE_PREVIEW_CHARS else ""
    return f"{preview}{ellipsis} [{len(value):,} chars]"


def _tool_argument_summary(payload: dict[str, object]) -> str:
    value = payload.get("arguments")
    if value is None:
        value = payload.get("input")
    if value is None or value == "":
        return "—"
    if isinstance(value, str):
        try:
            structured = json.loads(value)
        except json.JSONDecodeError:
            return _sanitize_unstructured_argument(value)
    else:
        structured = value
    if not isinstance(structured, (dict, list)):
        return _sanitize_unstructured_argument(str(structured))
    sanitized = _sanitize_structured_argument("", structured)
    if (
        payload.get("name") == "send_message"
        and isinstance(structured, dict)
        and isinstance(structured.get("message"), str)
        and isinstance(sanitized, dict)
    ):
        sanitized["message"] = _message_argument_preview(structured["message"])
    return _truncate_argument_summary(
        json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _skill_names_from_value(value: object) -> set[str]:
    """Return skill directory names explicitly referenced by tool arguments."""

    if value is None:
        return set()
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(value)
    return {match.group("name") for match in _SKILL_PATH_PATTERN.finditer(text)}


def _is_bash_skill_loader(
    tool_name: str,
    arguments: object,
    input_value: object,
) -> bool:
    """Return whether a tool call represents the report's shell-loading path."""

    normalized = tool_name.casefold().replace(":", ".")
    if normalized in {"exec", "exec_command", "shell", "terminal"}:
        return True
    if normalized != "functions.exec":
        return False
    source = arguments if arguments is not None else input_value
    if not isinstance(source, str):
        try:
            source = json.dumps(source, ensure_ascii=False)
        except (TypeError, ValueError):
            source = str(source)
    return "exec_command" in source


def _mcp_agent_ops_skill_names(tool_name: str, arguments: object) -> set[str]:
    """Extract skill identities loaded through mcp-agent-ops skill tools."""

    if not isinstance(arguments, dict):
        return set()
    if tool_name == "skill_load":
        names = arguments.get("names")
        return (
            {str(name) for name in names if str(name)}
            if isinstance(names, list)
            else set()
        )
    if tool_name in {"skill_read", "skill_read_resource"}:
        name = arguments.get("name")
        return {str(name)} if name else set()
    if tool_name == "skill_resource_load":
        requests = arguments.get("requests")
        if not isinstance(requests, list):
            return set()
        return {
            str(request.get("skill_name"))
            for request in requests
            if isinstance(request, dict) and request.get("skill_name")
        }
    return set()


def _compact_values(values: list[str], *, limit: int = 8) -> str:
    """Render a bounded inventory for one compact MCP argument summary."""

    visible = values[:limit]
    summary = " · ".join(visible) if visible else "—"
    omitted = len(values) - len(visible)
    return f"{summary} · +{omitted} more" if omitted else summary


def _path_basename(value: object) -> str:
    """Return a compact path label without exposing its full parent path."""

    text = str(value or "")
    return Path(text).name or text or "—"


def _mcp_agent_ops_argument_summary(tool_name: str, arguments: object) -> str | None:
    """Format mcp-agent-ops arguments around their operator-facing identity."""

    if not isinstance(arguments, dict):
        return None
    if tool_name == "skill_load":
        names = arguments.get("names")
        values = [str(name) for name in names] if isinstance(names, list) else []
        return f"skills: {_compact_values(values)}"
    if tool_name in {"skill_read", "skill_read_resource"}:
        name = str(arguments.get("name") or "—")
        resource = str(arguments.get("resource_path") or "")
        return f"skill: {name}" + (f" · resource: {resource}" if resource else "")
    if tool_name == "skill_resource_load":
        requests = arguments.get("requests")
        values = []
        if isinstance(requests, list):
            for request in requests:
                if not isinstance(request, dict):
                    continue
                skill_name = str(request.get("skill_name") or "—")
                resource_path = str(request.get("resource_path") or "—")
                values.append(f"{skill_name}:{resource_path}")
        return f"resources: {_compact_values(values)}"
    if tool_name in {"skill_list", "skill_refresh"}:
        return "skill catalog"
    if tool_name == "skill_validate":
        paths = arguments.get("paths")
        count = len(paths) if isinstance(paths, list) else 0
        return f"skill paths: {count:,}"
    if tool_name.startswith("claim_"):
        parts = [f"repository: {_path_basename(arguments.get('repository'))}"]
        if arguments.get("claim_id"):
            parts.append(f"claim: {arguments['claim_id']}")
        if arguments.get("work_item_id"):
            parts.append(f"work item: {arguments['work_item_id']}")
        if arguments.get("activity"):
            parts.append(f"activity: {arguments['activity']}")
        if arguments.get("disposition"):
            parts.append(f"disposition: {arguments['disposition']}")
        if arguments.get("blocker_reference"):
            parts.append(f"blocker: {arguments['blocker_reference']}")
        for key in ("files", "trees", "resources"):
            values = arguments.get(key)
            if isinstance(values, list) and values:
                parts.append(f"{key}: {len(values):,}")
        return " · ".join(parts)
    if tool_name in {"verify_yaml", "verify_markdown_links"}:
        paths = arguments.get("paths")
        count = len(paths) if isinstance(paths, list) else 0
        root = arguments.get("repository_root") or arguments.get("repository")
        return f"repository: {_path_basename(root)} · paths: {count:,}"
    if tool_name == "detect_technology_skills":
        scopes = arguments.get("scopes")
        count = len(scopes) if isinstance(scopes, list) else 0
        return (
            f"project: {_path_basename(arguments.get('project_root'))} · "
            f"scopes: {count:,}"
        )
    return None


def _mcp_duration_ms(payload: dict[str, object]) -> int:
    """Convert a native MCP duration object into rounded milliseconds."""

    duration = payload.get("duration")
    if not isinstance(duration, dict):
        return 0
    seconds = duration.get("secs", 0)
    nanoseconds = duration.get("nanos", 0)
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        seconds = 0
    if not isinstance(nanoseconds, (int, float)) or isinstance(nanoseconds, bool):
        nanoseconds = 0
    return max(0, round(float(seconds) * 1000 + float(nanoseconds) / 1_000_000))


def _timestamp_before(timestamp: str, milliseconds: int) -> str:
    """Derive an MCP start timestamp from its recorded end and duration."""

    completed = _parse_iso_datetime(timestamp)
    if completed is None:
        return timestamp
    return (
        (completed - timedelta(milliseconds=milliseconds))
        .astimezone(timezone.utc)
        .isoformat()
    )


def _mcp_structured_result(result: object) -> dict[str, object]:
    """Return the structured content nested in one successful MCP result."""

    if not isinstance(result, dict):
        return {}
    success = result.get("Ok")
    if not isinstance(success, dict):
        return {}
    structured = success.get("structuredContent")
    if structured is None:
        structured = success.get("structured_content")
    return structured if isinstance(structured, dict) else {}


def _mcp_result_summary(
    server_name: str,
    tool_name: str,
    result: object,
) -> tuple[bool, str]:
    """Summarize MCP success without expanding large returned content."""

    succeeded = isinstance(result, dict) and "Ok" in result
    status = "OK" if succeeded else "Error"
    structured = _mcp_structured_result(result)
    if server_name != "mcp-agent-ops" or not structured:
        return succeeded, status
    if tool_name.startswith("skill_"):
        skills = structured.get("skills")
        errors = structured.get("errors")
        revision = structured.get("catalog_revision") or structured.get("revision")
        parts = [status]
        if isinstance(skills, list):
            parts.append(f"{len(skills):,} skills")
        if isinstance(errors, list):
            parts.append(f"{len(errors):,} errors")
        if revision:
            parts.append(f"revision {str(revision)[:8]}")
        return succeeded, " · ".join(parts)
    if tool_name.startswith("claim_"):
        nested = structured.get("result")
        outcome = nested.get("outcome") if isinstance(nested, dict) else None
        exit_code = structured.get("exit_code")
        parts = [str(outcome or status)]
        if isinstance(exit_code, int):
            parts.append(f"exit {exit_code}")
        return succeeded, " · ".join(parts)
    findings = structured.get("findings")
    if isinstance(findings, list):
        return succeeded, f"{status} · {len(findings):,} findings"
    return succeeded, status


def _compile_formatter_regex(pattern: str, *, context: str) -> re.Pattern[str]:
    if len(pattern) > 500:
        raise ValueError(f"{context} exceeds 500 characters")
    if any(token in pattern for token in ("(?=", "(?!", "(?<=", "(?<!", "(?(")):
        raise ValueError(f"{context} uses an unsupported regex construct")
    if re.search(r"\\[1-9]", pattern):
        raise ValueError(f"{context} uses an unsupported regex backreference")
    if re.search(r"\((?:[^()]|\\.)*[+*](?:[^()]|\\.)*\)[+*{]", pattern):
        raise ValueError(f"{context} uses a nested regex quantifier")
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid {context}: {exc}") from exc


def _parse_tool_formatter_config(
    data: object,
    *,
    source_path: str = "",
) -> ToolFormatterConfig:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Tool formatter config must be an object with version 1")
    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list):
        raise ValueError("Tool formatter config rules must be a list")
    rules: list[ToolFormatterRule] = []
    seen_ids: set[str] = set()
    for rule_index, raw_rule in enumerate(raw_rules, start=1):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"Tool formatter rule {rule_index} must be an object")
        rule_id = str(raw_rule.get("id") or "").strip()
        if not rule_id or rule_id in seen_ids:
            raise ValueError(f"Tool formatter rule {rule_index} has a missing or duplicate id")
        seen_ids.add(rule_id)
        match = raw_rule.get("match")
        if not isinstance(match, dict) or not str(match.get("tool") or "").strip():
            raise ValueError(f"Tool formatter rule {rule_id} must match a tool")
        tool_name = str(match["tool"]).strip()
        arguments_pattern = match.get("arguments_regex")
        arguments_regex = (
            _compile_formatter_regex(
                str(arguments_pattern),
                context=f"arguments regex for rule {rule_id}",
            )
            if arguments_pattern is not None
            else None
        )
        raw_fields = raw_rule.get("fields", [])
        if not isinstance(raw_fields, list):
            raise ValueError(f"Tool formatter rule {rule_id} fields must be a list")
        fields: list[ToolFormatterField] = []
        field_names: set[str] = set()
        for field_index, raw_field in enumerate(raw_fields, start=1):
            if not isinstance(raw_field, dict):
                raise ValueError(f"Field {field_index} in rule {rule_id} must be an object")
            name = str(raw_field.get("name") or "").strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or name in field_names:
                raise ValueError(f"Rule {rule_id} has an invalid or duplicate field name")
            field_names.add(name)
            json_path = str(raw_field.get("json_path") or "").strip()
            field_pattern = raw_field.get("regex")
            if bool(json_path) == (field_pattern is not None):
                raise ValueError(
                    f"Field {name} in rule {rule_id} needs exactly one of json_path or regex"
                )
            field_regex = (
                _compile_formatter_regex(
                    str(field_pattern),
                    context=f"field regex {name} for rule {rule_id}",
                )
                if field_pattern is not None
                else None
            )
            transform = str(raw_field.get("transform") or "identity")
            if transform not in {"identity", "basename"}:
                raise ValueError(f"Field {name} in rule {rule_id} has an invalid transform")
            fields.append(
                ToolFormatterField(
                    name=name,
                    json_path=json_path,
                    regex=field_regex,
                    group=str(raw_field.get("group") or name),
                    transform=transform,
                )
            )
        display = raw_rule.get("display")
        raw_parts = display.get("parts") if isinstance(display, dict) else None
        if not isinstance(raw_parts, list) or not raw_parts or not all(
            isinstance(part, str) for part in raw_parts
        ):
            raise ValueError(f"Tool formatter rule {rule_id} needs display parts")
        placeholders = {
            placeholder
            for part in raw_parts
            for placeholder in re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", part)
        }
        unknown_placeholders = placeholders - field_names
        if unknown_placeholders:
            raise ValueError(
                f"Tool formatter rule {rule_id} uses unknown fields: "
                + ", ".join(sorted(unknown_placeholders))
            )
        rules.append(
            ToolFormatterRule(
                rule_id=rule_id,
                tool_name=tool_name,
                arguments_regex=arguments_regex,
                fields=tuple(fields),
                parts=tuple(raw_parts),
                separator=str(display.get("separator") or " · "),
            )
        )
    return ToolFormatterConfig(version=1, rules=tuple(rules), source_path=source_path)


def _load_tool_formatter_config(path: Path | str | None = None) -> ToolFormatterConfig:
    config_path = Path(path or DEFAULT_TOOL_FORMATTER_CONFIG).resolve()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Tool formatter config not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid tool formatter JSON at {config_path}: {exc}") from exc
    return _parse_tool_formatter_config(data, source_path=str(config_path))


def _formatter_json_value(value: object, path: str) -> object | None:
    current = value
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def _formatter_field_value(
    field: ToolFormatterField,
    argument_summary: str,
    structured: object | None,
) -> str:
    value: object | None
    if field.json_path:
        value = _formatter_json_value(structured, field.json_path)
    else:
        match = field.regex.search(argument_summary) if field.regex is not None else None
        if match is None:
            value = None
        else:
            try:
                value = match.group(field.group)
            except (IndexError, KeyError):
                value = None
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        rendered = str(value)
    if field.transform == "basename":
        rendered = Path(rendered).name
    return rendered


def _format_tool_argument(
    tool_name: str,
    argument_summary: str,
    config: ToolFormatterConfig,
) -> FormattedToolArgument | None:
    try:
        structured: object | None = json.loads(argument_summary)
    except json.JSONDecodeError:
        structured = None
    for rule in config.rules:
        if rule.tool_name != tool_name:
            continue
        if rule.arguments_regex is not None and not rule.arguments_regex.search(argument_summary):
            continue
        values = {
            field.name: _formatter_field_value(field, argument_summary, structured)
            for field in rule.fields
        }
        rendered_parts = []
        for part in rule.parts:
            rendered = re.sub(
                r"{([A-Za-z_][A-Za-z0-9_]*)}",
                lambda match: values.get(match.group(1), ""),
                part,
            ).strip()
            if rendered:
                rendered_parts.append(rendered)
        if rendered_parts:
            return FormattedToolArgument(
                summary=rule.separator.join(rendered_parts),
                rule_id=rule.rule_id,
            )
    return None


def _render_tool_argument(
    tool: ToolInterval,
    config: ToolFormatterConfig,
) -> str:
    raw_source = tool.argument_content or tool.argument_summary
    plan_items = _update_plan_items(raw_source)
    if plan_items:
        return (
            _render_update_plan(plan_items)
            + '<details class="tool-argument-raw"><summary>raw</summary>'
            + f'<code class="tool-arguments">{_escape_html(raw_source)}</code></details>'
        )

    formatted = _format_tool_argument(tool.tool_name, tool.argument_summary, config)
    if formatted is None:
        preview_html = (
            f'<code class="tool-arguments">{_escape_html(tool.argument_summary)}</code>'
        )
        full_html = f'<code class="tool-arguments">{_escape_html(raw_source)}</code>'
        return _clamped_argument_html(preview_html, full_html, raw_source)
    raw = _escape_html(raw_source)
    raw_label = "raw source command (redacted)" if tool.argument_content else "raw"
    formatted_summary = _escape_html(formatted.summary)
    full_html = (
        f'<div class="tool-argument-formatted">{formatted_summary}</div>'
        f'<details class="tool-argument-raw"><summary>{raw_label}</summary>'
        f'<code class="tool-arguments">{raw}</code></details>'
    )
    return full_html


def _update_plan_items(source: str) -> list[tuple[str, str]]:
    """Extract display-safe update-plan steps from a recorded tool wrapper."""

    if "tools.update_plan" not in source:
        return []
    items: list[tuple[str, str]] = []
    for match in _UPDATE_PLAN_ITEM_PATTERN.finditer(source):
        encoded_step = match.group("step")
        try:
            step = json.loads(f'"{encoded_step}"')
        except json.JSONDecodeError:
            step = encoded_step.replace(r'\"', '"').replace(r"\n", " ")
        items.append((str(step), match.group("status")))
    return items


def _plan_status_html(status: str) -> str:
    status_class = {
        "completed": " state-complete",
        "in_progress": " state-active",
    }.get(status, "")
    return (
        f'<span class="state{status_class}">'
        f"{_escape_html(status.replace('_', ' '))}</span>"
    )


def _render_update_plan(items: list[tuple[str, str]]) -> str:
    rendered_items = "".join(
        '<li class="tool-plan-item">'
        f'<span class="tool-plan-step">{_escape_html(step)}</span> '
        f"{_plan_status_html(status)}</li>"
        for step, status in items
    )
    return f'<ul class="tool-plan">{rendered_items}</ul>'


def _clamped_argument_html(
    preview_html: str,
    full_html: str,
    source: str,
) -> str:
    """Clamp long argument cells while retaining their complete bounded content."""

    if len(source) <= TOOL_ARGUMENT_CLAMP_CHARS and source.count("\n") < 5:
        return full_html
    return (
        '<details class="clamped-disclosure tool-argument-disclosure">'
        f'<summary><span class="clamped-preview">{preview_html}</span>'
        '<span class="clamped-toggle clamped-more">more</span></summary>'
        f'<div class="clamped-full">{full_html}'
        '<button type="button" class="clamped-toggle clamped-less">less</button>'
        "</div></details>"
    )


def _render_tool_result(tool: ToolInterval) -> str:
    if not tool.result_summary:
        return "—"
    summary = _escape_html(tool.result_summary)
    if not tool.result_content:
        return f'<div class="tool-result-summary">{summary}</div>'
    return (
        f'<div class="tool-result-summary">{summary}</div>'
        '<details class="tool-result-raw"><summary>raw result</summary>'
        f'<pre>{_escape_html(tool.result_content)}</pre></details>'
    )


def _render_mcp_argument(call: McpCallInterval) -> str:
    """Render a specially formatted MCP argument with optional raw disclosure."""

    summary = _escape_html(call.argument_summary)
    raw_source = call.argument_content or call.argument_summary
    if not call.argument_content:
        argument_html = f'<code class="tool-arguments">{summary}</code>'
        return _clamped_argument_html(argument_html, argument_html, raw_source)
    full_html = (
        f'<div class="tool-argument-formatted">{summary}</div>'
        '<details class="tool-argument-raw"><summary>raw</summary>'
        f'<code class="tool-arguments">{_escape_html(call.argument_content)}</code>'
        "</details>"
    )
    return _clamped_argument_html(
        f'<span class="tool-argument-formatted">{summary}</span>',
        full_html,
        raw_source,
    )


def _render_mcp_result(call: McpCallInterval) -> str:
    """Render an MCP result summary without expanding large returned payloads."""

    if not call.result_summary:
        return "—"
    summary = _escape_html(call.result_summary)
    if not call.result_content:
        return f'<div class="tool-result-summary">{summary}</div>'
    return (
        f'<div class="tool-result-summary">{summary}</div>'
        '<details class="tool-result-raw"><summary>raw result</summary>'
        f'<pre>{_escape_html(call.result_content)}</pre></details>'
    )


def _event_turn_id(payload: dict[str, object], active_turns: dict[str, AgentTurn]) -> str | None:
    metadata = payload.get("internal_chat_message_metadata_passthrough")
    if isinstance(metadata, dict) and metadata.get("turn_id"):
        return str(metadata["turn_id"])
    if len(active_turns) == 1:
        return next(iter(active_turns))
    return None


def _response_item_fragments(payload: dict[str, object], field: str) -> list[str]:
    """Return each plaintext fragment recorded for one response item."""

    value = payload.get(field)
    if not isinstance(value, list):
        return []
    fragments = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            fragments.append(text)
    return fragments


def _response_item_text(payload: dict[str, object], field: str) -> str:
    """Return the combined plaintext recorded for one response item."""

    fragments = _response_item_fragments(payload, field)
    return "\n".join(fragments)


def _genuine_user_request(content: str) -> str:
    """Return human-authored request text without known Codex host envelopes."""

    normalized = content.strip()
    request_marker = "## My request for Codex:"
    if request_marker in normalized:
        normalized = normalized.partition(request_marker)[2].strip()
    for _ in range(3):
        decoded = _decode_html_entities(normalized)
        if decoded != normalized:
            normalized = decoded.strip()
            continue
        delegation = _CODEX_DELEGATION_BLOCK_PATTERN.fullmatch(normalized)
        if delegation is not None:
            delegation_input = _CODEX_DELEGATION_INPUT_PATTERN.search(
                delegation.group("body")
            )
            if delegation_input is not None:
                normalized = delegation_input.group("input").strip()
                continue
        break
    host_prefixes = (
        "<recommended_plugins>",
        "# AGENTS.md instructions for ",
        "<environment_context>",
        '<in-app-browser-context source="ambient-ui-state">',
    )
    if normalized.startswith(host_prefixes):
        return ""
    if normalized.casefold().startswith("<codex_delegation"):
        return ""
    return normalized


def _initial_delegation_source(content: str) -> str:
    """Return the sender of a task-defining delegation envelope, when present."""

    normalized = content.strip()
    request_marker = "## My request for Codex:"
    if request_marker in normalized:
        normalized = normalized.partition(request_marker)[2].strip()
    for _ in range(3):
        decoded = _decode_html_entities(normalized)
        if decoded == normalized:
            break
        normalized = decoded.strip()
    delegation = _CODEX_DELEGATION_BLOCK_PATTERN.fullmatch(normalized)
    if delegation is None or not _genuine_user_request(normalized):
        return ""
    source = _CODEX_DELEGATION_SOURCE_PATTERN.search(delegation.group("body"))
    return source.group("source") if source is not None else ""


def _decode_html_entities(value: str) -> str:
    """Decode the bounded entity forms used by serialized Codex envelopes."""

    entity_pattern = re.compile(
        r"&(?P<entity>lt|gt|amp|quot|apos|#\d+|#x[0-9a-f]+);",
        re.IGNORECASE,
    )
    named = {"lt": "<", "gt": ">", "amp": "&", "quot": '"', "apos": "'"}

    def replace(match: re.Match[str]) -> str:
        entity = match.group("entity")
        lowered = entity.casefold()
        if lowered in named:
            return named[lowered]
        try:
            codepoint = int(entity[2:], 16) if lowered.startswith("#x") else int(entity[1:])
            return chr(codepoint) if 0 <= codepoint <= 0x10FFFF else match.group(0)
        except (ValueError, OverflowError):
            return match.group(0)

    return entity_pattern.sub(replace, value)


def _url_query(values: dict[str, str]) -> str:
    """Encode a small UTF-8 query without adding a frozen-runtime dependency."""

    def encode(value: str) -> str:
        return "".join(
            chr(byte)
            if (
                ord("a") <= byte <= ord("z")
                or ord("A") <= byte <= ord("Z")
                or ord("0") <= byte <= ord("9")
                or byte in b"-._~"
            )
            else f"%{byte:02X}"
            for byte in value.encode("utf-8")
        )

    return "&".join(f"{encode(key)}={encode(value)}" for key, value in values.items())


def _derived_task_title(activities: list[AgentActivity]) -> str:
    """Derive a bounded task title from the first genuine recorded user request."""

    for activity in activities:
        if (
            activity.activity_type != "input"
            or not activity.summary.startswith("User input")
        ):
            continue
        request = _genuine_user_request(activity.content)
        if not request:
            continue
        title = re.sub(r"\b[A-Z][A-Z0-9_]*\s*=\s*\[redacted\]", "", request)
        title = re.sub(r"\s+", " ", title).strip()
        title = re.sub(
            r"^(?:please\s+|can you\s+|could you\s+|would you\s+)",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.split(r"[.!?](?:\s|$)", title, maxsplit=1)[0].strip()
        words = title.split()
        title = " ".join(words[:10]).rstrip(" ,:;-.")
        title = re.sub(r"\s+(?:and|for|from|to|using|with)$", "", title, flags=re.IGNORECASE)
        if title:
            return title[0].upper() + title[1:]
    return ""


def _report_title(task_title: str) -> str:
    """Normalize one task title for report display without duplicating the suffix."""

    normalized = re.sub(r"\s+", " ", task_title).strip().rstrip(". ")
    if not normalized:
        return ""
    suffix = " Agent Report"
    if normalized.casefold() == suffix.strip().casefold():
        return ""
    if normalized.casefold().endswith(suffix.casefold()):
        normalized = normalized[: -len(suffix)].rstrip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] == '"':
        normalized = normalized[1:-1].strip()
    if not normalized:
        return ""
    return f'"{normalized}" Agent Report'


def _compact_display_text(value: str, limit: int) -> str:
    """Return one whitespace-normalized label bounded at a useful word edge."""

    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    boundary = compact.rfind(" ", 0, max(1, limit))
    if boundary < max(1, limit // 2):
        boundary = max(1, limit - 1)
    return compact[:boundary].rstrip(" ,:;-.") + "…"


def _compact_report_title(report_title: str, limit: int = 96) -> str:
    """Bound a visible report heading while retaining its canonical suffix."""

    normalized = " ".join(report_title.split())
    match = re.fullmatch(r'"(?P<title>.*)" Agent Report', normalized)
    if not match:
        return _compact_display_text(normalized, limit)
    suffix_chars = len('"" Agent Report')
    compact_title = _compact_display_text(
        match.group("title"),
        max(1, limit - suffix_chars),
    )
    return f'"{compact_title}" Agent Report'


def _normalized_codex_thread_title(value: object) -> str:
    """Normalize a local Codex title and unwrap saved delegation envelopes."""

    title = re.sub(r"\s+", " ", str(value or "")).strip()
    if _CODEX_DELEGATION_LINE_PATTERN.search(title):
        return _catalog_task_title(title)
    return title


def _local_codex_thread_title_rows(thread_ids: set[str]) -> list[tuple[str, object]]:
    """Read raw local Codex task-title rows in source-precedence order."""

    if not thread_ids:
        return []
    placeholders = ",".join("?" for _ in thread_ids)
    ordered_ids = sorted(thread_ids)
    sources = (
        (
            Path.home() / ".codex" / "sqlite" / "codex-dev.db",
            (
                "SELECT thread_id, display_title FROM local_thread_catalog "
                f"WHERE missing_candidate = 0 AND thread_id IN ({placeholders}) "
                "ORDER BY observation_sequence DESC"
            ),
        ),
        (
            Path.home() / ".codex" / "state_5.sqlite",
            f"SELECT id, title FROM threads WHERE id IN ({placeholders})",
        ),
    )
    rows: list[tuple[str, object]] = []
    for database, query in sources:
        if not database.is_file():
            continue
        try:
            connection = sqlite3.connect(
                f"{database.resolve().as_uri()}?mode=ro",
                uri=True,
                timeout=0.2,
            )
            try:
                source_rows = connection.execute(query, ordered_ids).fetchall()
            finally:
                connection.close()
        except (OSError, sqlite3.Error):
            continue
        rows.extend(source_rows)
    return rows


def _local_codex_thread_titles(thread_ids: set[str]) -> dict[str, str]:
    """Read Codex's local task titles without requiring the Codex service."""

    titles: dict[str, str] = {}
    for thread_id, raw_title in _local_codex_thread_title_rows(thread_ids):
        title = _normalized_codex_thread_title(raw_title)
        if title:
            titles.setdefault(str(thread_id), title)
    return titles


def _local_codex_delegation_parents(thread_ids: set[str]) -> dict[str, str]:
    """Return parent IDs preserved in local delegated-task title envelopes."""

    parents: dict[str, str] = {}
    for thread_id, raw_title in _local_codex_thread_title_rows(thread_ids):
        parent_thread_id = _initial_delegation_source(str(raw_title or ""))
        if parent_thread_id:
            parents.setdefault(str(thread_id), parent_thread_id)
    return parents


def _append_codex_activity(
    activities: list[AgentActivity],
    *,
    thread_id: str,
    turn_id: str | None,
    activity_type: str,
    timestamp: str,
    path: Path,
    ordinal: int,
    summary: str,
    raw_text: str = "",
    model: str = "",
) -> None:
    """Append one bounded, secret-redacted native Codex narrative event."""

    activities.append(
        AgentActivity(
            thread_id=thread_id,
            turn_id=turn_id,
            activity_type=activity_type,
            event_timestamp=timestamp,
            source_path=str(path),
            source_ordinal=ordinal,
            summary=summary,
            content=_tool_argument_content(raw_text) if raw_text else "",
            model=model,
        )
    )


def _terminal_turn_outcome(
    event_type: str,
    turn_id: str,
    final_outputs: list[str],
    *,
    agent_path: str,
    agent_nickname: str,
    final_message: object,
) -> str:
    final_outputs = list(final_outputs)
    if isinstance(final_message, str) and final_message.strip():
        final_outputs.append(final_message)

    def starts_with_word(candidate: str, word: str) -> bool:
        return candidate.startswith(word) and (
            len(candidate) == len(word)
            or not (candidate[len(word)].isalnum() or candidate[len(word)] == "_")
        )

    def is_failed_verdict(line: str) -> bool:
        candidate = line.lstrip().lstrip(_VERDICT_PREFIX_CHARS).lstrip().upper()
        return starts_with_word(candidate, "FAIL")

    def is_review_finding(line: str) -> bool:
        candidate = line.lstrip()
        if candidate.startswith(("- ", "* ")):
            candidate = candidate[2:].lstrip()
        else:
            marker = re.match(r"\d+[.)][ \t]+", candidate)
            if marker is None:
                return False
            candidate = candidate[marker.end() :].lstrip()
        candidate = candidate.removeprefix("**").upper()
        return any(starts_with_word(candidate, severity) for severity in _REVIEW_SEVERITIES)

    lines = (line for output in final_outputs for line in output.splitlines())
    if any(is_failed_verdict(line) for line in lines):
        return "failed"
    agent_identity = f"{agent_path} {agent_nickname}".casefold()
    if "review" in agent_identity and any(
        is_review_finding(line)
        for output in final_outputs
        for line in output.splitlines()
    ):
        return "failed"
    return "complete" if event_type == "task_complete" else "aborted"


def _token_funding_telemetry(
    rate_limits: object,
) -> tuple[str, str, float | None, float | None, bool | None]:
    """Normalize one token event's plan, funding source, and quota values."""
    if not isinstance(rate_limits, dict):
        return "", "unknown", None, None, None
    raw_plan_type = rate_limits.get("plan_type")
    plan_type = str(raw_plan_type).strip() if raw_plan_type else ""
    primary = rate_limits.get("primary")
    raw_used_percent = (
        primary.get("used_percent") if isinstance(primary, dict) else None
    )
    try:
        used_percent = (
            float(raw_used_percent) if raw_used_percent is not None else None
        )
    except (TypeError, ValueError):
        used_percent = None
    credits = rate_limits.get("credits")
    raw_has_credits = credits.get("has_credits") if isinstance(credits, dict) else None
    has_credits = raw_has_credits if isinstance(raw_has_credits, bool) else None
    raw_balance = credits.get("balance") if isinstance(credits, dict) else None
    try:
        credit_balance = float(raw_balance) if raw_balance is not None else None
    except (TypeError, ValueError):
        credit_balance = None
    funding_source = "credits" if has_credits is True else "subscription"
    return plan_type, funding_source, used_percent, credit_balance, has_credits


def parse_codex_rollout(
    path: Path,
    *,
    cancelled: Callable[[], bool] | None = None,
    token_funding_events: list[_TokenFundingEvent] | None = None,
) -> CodexThreadMetrics:
    """Parse one native Codex Desktop rollout with bounded local disclosures.

    The returned counters belong only to this thread. Cumulative token events
    become exclusive response deltas; duplicate snapshots and a partial final
    JSONL record are tolerated and surfaced through diagnostics. Plaintext input,
    reasoning summaries, tool results, and output are bounded and secret-redacted;
    encrypted reasoning content remains opaque.
    """
    path = path.resolve()
    records, diagnostics = _parse_jsonl_append_safe(path)
    thread_id = ""
    parent_thread_id = ""
    thread_name = ""
    task_title = ""
    agent_path = ""
    agent_role = ""
    agent_nickname = ""
    model = ""
    current_effort = ""
    efforts: list[str] = []
    plan_type = ""
    timestamps: list[str] = []
    contexts: dict[str, dict[str, object]] = {}
    active_turns: dict[str, AgentTurn] = {}
    turns_by_id: dict[str, AgentTurn] = {}
    turns: list[AgentTurn] = []
    responses: list[ResponseUsage] = []
    activities: list[AgentActivity] = []
    final_outputs_by_turn: dict[str, list[str]] = {}
    output_turn_ids: set[str] = set()
    tools: list[ToolInterval] = []
    mcp_calls: list[McpCallInterval] = []
    context_snapshots: list[ContextSnapshot] = []
    compactions: list[ContextCompaction] = []
    work_item_claim_events: list[WorkItemClaimEvent] = []
    skills_used: set[str] = set()
    mcp_skills_loaded: set[str] = set()
    bash_skills_loaded: set[str] = set()
    pending_tools: dict[str, tuple[str, str, str | None, int, str, str, str]] = {}
    previous_usage = UsageTotals()
    recorded_cost_usd: float | None = None
    saw_usage = False
    spawn_boundary_seen = False
    task_request_seen = False
    infer_parent_from_delegation = False
    unknown_event_counts: dict[str, int] = {}
    model_ready_at = ""
    pending_model_started_at = ""
    pending_model_output_timestamps: list[str] = []
    funding_event_start = len(token_funding_events) if token_funding_events is not None else 0

    def note_model_output(raw_timestamp: str) -> None:
        """Track observable model fragments without retaining their content."""

        nonlocal pending_model_started_at
        normalized = _normalize_timestamp(raw_timestamp)
        if not normalized:
            return
        if not pending_model_output_timestamps:
            pending_model_started_at = model_ready_at or normalized
        pending_model_output_timestamps.append(normalized)

    for ordinal, record in records:
        if cancelled is not None and cancelled():
            raise RuntimeError("Report operation cancelled")
        timestamp = str(record.get("timestamp") or "")
        if timestamp:
            timestamps.append(timestamp)
        record_type = str(record.get("type") or "")
        payload = record.get("payload")
        if not isinstance(payload, dict):
            unknown_event_counts[record_type or "missing-type"] = (
                unknown_event_counts.get(record_type or "missing-type", 0) + 1
            )
            continue

        if record_type == "session_meta":
            candidate_id = str(payload.get("id") or payload.get("session_id") or "")
            if candidate_id and not thread_id:
                thread_id = candidate_id
                task_title = next(
                    (
                        str(payload[key]).strip()
                        for key in ("task_title", "thread_title", "title")
                        if isinstance(payload.get(key), str) and str(payload[key]).strip()
                    ),
                    "",
                )
                task_request_seen = bool(task_title)
                parent_thread_id, agent_path, agent_nickname = _spawn_metadata(payload)
                infer_parent_from_delegation = (
                    payload.get("thread_source") == "subagent"
                    or payload.get("source") == "subagent"
                )
                thread_name = (
                    agent_path.rstrip("/").rsplit("/", 1)[-1]
                    if agent_path
                    else ("root" if not parent_thread_id else "")
                )
                agent_role = _spawn_agent_role(payload)
            elif candidate_id and candidate_id != thread_id:
                diagnostics.append(
                    f"replayed session_meta ignored at {path}:{ordinal}: {candidate_id}"
                )
            continue

        if record_type == "turn_context":
            turn_id = str(payload.get("turn_id") or "")
            if turn_id:
                contexts[turn_id] = payload
                existing_turn = turns_by_id.get(turn_id)
                if existing_turn is not None:
                    fields, confidence, reason = _turn_attribution(
                        {},
                        payload,
                        agent_path=agent_path,
                        agent_nickname=agent_nickname,
                    )
                    if confidence == "exact":
                        existing_turn.run_id = fields["run_id"]
                        existing_turn.phase_id = fields["phase_id"]
                        existing_turn.lane_id = fields["lane_id"]
                        existing_turn.work_unit_id = fields["work_unit_id"]
                        existing_turn.activity = fields["activity"]
                        existing_turn.attribution_confidence = confidence
                        existing_turn.attribution_reason = reason
            if payload.get("model"):
                model = str(payload["model"])
            effort = str(payload.get("effort") or "").strip()
            if effort and effort not in efforts:
                efforts.append(effort)
            if effort:
                current_effort = effort
            continue

        if record_type == "compacted":
            previous_context = next(
                (
                    snapshot
                    for snapshot in reversed(context_snapshots)
                    if not snapshot.is_compaction_marker
                ),
                None,
            )
            window_number = payload.get("window_number")
            compactions.append(
                ContextCompaction(
                    event_timestamp=_normalize_timestamp(timestamp),
                    before_total_tokens=(
                        previous_context.total_tokens if previous_context else 0
                    ),
                    after_total_tokens=0,
                    capacity=(previous_context.capacity if previous_context else 0),
                    window_number=(
                        window_number
                        if isinstance(window_number, int)
                        and not isinstance(window_number, bool)
                        else None
                    ),
                    window_id=_bounded_claim_value(payload.get("window_id")),
                    source_path=str(path),
                    source_ordinal=ordinal,
                )
            )
            pending_model_started_at = ""
            pending_model_output_timestamps.clear()
            continue

        if record_type == "event_msg":
            event_type = str(payload.get("type") or "")
            if event_type == "task_started":
                turn_id = str(payload.get("turn_id") or f"unmatched-start-{ordinal}")
                if turn_id in active_turns or turn_id in turns_by_id:
                    diagnostics.append(f"repeated task_started for {turn_id} at {path}:{ordinal}")
                    continue
                context = contexts.get(turn_id, {})
                fields, confidence, reason = _turn_attribution(
                    payload,
                    context,
                    agent_path=agent_path,
                    agent_nickname=agent_nickname,
                )
                turn = AgentTurn(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    started_at=_normalize_timestamp(payload.get("started_at"), timestamp),
                    run_id=fields["run_id"],
                    phase_id=fields["phase_id"],
                    lane_id=fields["lane_id"],
                    work_unit_id=fields["work_unit_id"],
                    activity=fields["activity"],
                    attribution_confidence=confidence,
                    attribution_reason=reason,
                    source_path=str(path),
                    source_ordinal=ordinal,
                )
                active_turns[turn_id] = turn
                turns_by_id[turn_id] = turn
                turns.append(turn)
                model_ready_at = turn.started_at or _normalize_timestamp(timestamp)
                pending_model_started_at = ""
                pending_model_output_timestamps.clear()
                continue

            if event_type == "context_compacted":
                if compactions:
                    compactions[-1].recorded = True
                model_ready_at = _normalize_timestamp(timestamp)
                pending_model_started_at = ""
                pending_model_output_timestamps.clear()
                continue

            if event_type == "user_message":
                model_ready_at = _normalize_timestamp(timestamp)
                continue

            if event_type == "token_count":
                info = payload.get("info")
                total_snapshot = info.get("total_token_usage") if isinstance(info, dict) else None
                last_snapshot = info.get("last_token_usage") if isinstance(info, dict) else None
                context = _context_snapshot(
                    last_snapshot,
                    info.get("model_context_window") if isinstance(info, dict) else None,
                    timestamp=timestamp,
                    path=path,
                    ordinal=ordinal,
                )
                if context is not None:
                    previous_context = context_snapshots[-1] if context_snapshots else None
                    context_snapshots.append(context)
                    if context.is_compaction_marker:
                        pending_compaction = next(
                            (
                                item
                                for item in reversed(compactions)
                                if item.after_total_tokens == 0
                            ),
                            None,
                        )
                        if pending_compaction is not None:
                            pending_compaction.after_total_tokens = context.total_tokens
                            pending_compaction.capacity = context.capacity
                        pending_model_started_at = ""
                        pending_model_output_timestamps.clear()
                    elif (
                        previous_context is not None
                        and not previous_context.is_compaction_marker
                        and previous_context.total_tokens > context.total_tokens
                        and previous_context.total_tokens - context.total_tokens
                        >= max(1_000, round(previous_context.total_tokens * 0.1))
                    ):
                        compactions.append(
                            ContextCompaction(
                                event_timestamp=context.event_timestamp,
                                before_total_tokens=previous_context.total_tokens,
                                after_total_tokens=context.total_tokens,
                                capacity=context.capacity,
                                window_number=None,
                                window_id="",
                                source_path=str(path),
                                source_ordinal=ordinal,
                                recorded=False,
                                derivation_method="inferred-context-drop",
                            )
                        )
                current_usage = _usage_from_snapshot(total_snapshot)
                rate_limits = payload.get("rate_limits")
                (
                    event_plan_type,
                    funding_source,
                    subscription_used_percent,
                    credit_balance,
                    has_credits,
                ) = _token_funding_telemetry(rate_limits)
                if event_plan_type:
                    plan_type = event_plan_type

                def record_token_funding(usage: UsageTotals | None = None) -> None:
                    if token_funding_events is None:
                        return
                    token_funding_events.append(
                        _TokenFundingEvent(
                            event_timestamp=_normalize_timestamp(timestamp),
                            source_path=str(path),
                            source_ordinal=ordinal,
                            usage=usage or UsageTotals(),
                            model=model,
                            plan_type=event_plan_type or plan_type,
                            funding_source=funding_source,
                            subscription_used_percent=subscription_used_percent,
                            credit_balance=credit_balance,
                            has_credits=has_credits,
                        )
                    )

                if current_usage is None:
                    record_token_funding()
                    diagnostics.append(f"invalid token_count at {path}:{ordinal}")
                    continue
                if context is not None and context.is_compaction_marker:
                    record_token_funding()
                    continue
                direct_cost = info.get("total_cost_usd") if isinstance(info, dict) else None
                if isinstance(direct_cost, (int, float)) and not isinstance(direct_cost, bool):
                    recorded_cost_usd = float(direct_cost)
                if saw_usage and current_usage == previous_usage:
                    record_token_funding()
                    continue
                if saw_usage and not current_usage.is_monotonic_from(previous_usage):
                    diagnostics.append(f"cumulative token counter reset at {path}:{ordinal}")
                    previous_usage = UsageTotals()
                delta = current_usage.subtract(previous_usage)
                record_token_funding(delta)
                if not _usage_is_zero(delta):
                    turn_id = next(iter(active_turns)) if len(active_turns) == 1 else None
                    confidence = "exact" if turn_id else "unattributed"
                    first_output_at = (
                        min(pending_model_output_timestamps)
                        if pending_model_output_timestamps
                        else ""
                    )
                    last_output_at = (
                        max(pending_model_output_timestamps)
                        if pending_model_output_timestamps
                        else ""
                    )
                    timing_available = bool(
                        pending_model_started_at and first_output_at and last_output_at
                    )
                    duration_ms = (
                        _interval_ms(pending_model_started_at, last_output_at)
                        if timing_available
                        else 0
                    )
                    ttft_ms = (
                        _interval_ms(pending_model_started_at, first_output_at)
                        if timing_available
                        else None
                    )
                    decode_time_ms = (
                        _interval_ms(first_output_at, last_output_at)
                        if timing_available
                        else None
                    )
                    response = ResponseUsage(
                        event_timestamp=timestamp,
                        usage=delta,
                        turn_id=turn_id,
                        source_path=str(path),
                        source_ordinal=ordinal,
                        model=model,
                        effort=current_effort,
                        attribution_confidence=confidence,
                        started_at=(pending_model_started_at if timing_available else ""),
                        first_output_at=first_output_at,
                        last_output_at=last_output_at,
                        completed_at=_normalize_timestamp(timestamp),
                        duration_ms=duration_ms,
                        ttft_ms=ttft_ms,
                        decode_time_ms=decode_time_ms,
                        timing_confidence="inferred" if timing_available else "unavailable",
                        timing_method=(
                            "ready-boundary-to-recorded-output-fragments"
                            if timing_available
                            else "unavailable"
                        ),
                        context_input_tokens=context.input_tokens if context else 0,
                        context_cached_input_tokens=(
                            context.cached_input_tokens if context else 0
                        ),
                        context_total_tokens=context.total_tokens if context else 0,
                        context_capacity=context.capacity if context else 0,
                        context_occupancy_percent=(
                            context.occupancy_percent if context else None
                        ),
                        reported_usage=(
                            _usage_from_snapshot(last_snapshot) or UsageTotals()
                        ),
                    )
                    responses.append(response)
                    if turn_id and turn_id in turns_by_id:
                        turns_by_id[turn_id].usage = turns_by_id[turn_id].usage + delta
                    pending_model_started_at = ""
                    pending_model_output_timestamps.clear()
                previous_usage = current_usage
                saw_usage = True
                continue

            if event_type == "mcp_tool_call_end":
                invocation = payload.get("invocation")
                if not isinstance(invocation, dict):
                    diagnostics.append(f"invalid mcp_tool_call_end at {path}:{ordinal}")
                    continue
                server_name = str(invocation.get("server") or "unknown")
                tool_name = str(invocation.get("tool") or "unknown")
                arguments = invocation.get("arguments")
                raw_argument_summary = _tool_argument_summary({"arguments": arguments})
                formatted_argument_summary = (
                    _mcp_agent_ops_argument_summary(tool_name, arguments)
                    if server_name == "mcp-agent-ops" or tool_name.startswith("claim_")
                    else None
                )
                argument_summary = formatted_argument_summary or raw_argument_summary
                duration_ms = _mcp_duration_ms(payload)
                completed_at = _normalize_timestamp(timestamp)
                turn_id = _event_turn_id(payload, active_turns)
                loaded_skills = (
                    _mcp_agent_ops_skill_names(tool_name, arguments)
                    if server_name == "mcp-agent-ops"
                    else set()
                )
                skills_used.update(loaded_skills)
                mcp_skills_loaded.update(loaded_skills)
                if turn_id and turn_id in turns_by_id:
                    turn = turns_by_id[turn_id]
                    turn.skills_used = sorted(
                        set(turn.skills_used) | loaded_skills,
                        key=str.casefold,
                    )
                    turn.mcp_skills_loaded = sorted(
                        set(turn.mcp_skills_loaded) | loaded_skills,
                        key=str.casefold,
                    )
                    turn.mcp_call_count += 1
                result = payload.get("result")
                succeeded, result_summary = _mcp_result_summary(
                    server_name,
                    tool_name,
                    result,
                )
                mcp_calls.append(
                    McpCallInterval(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        call_id=str(payload.get("call_id") or ""),
                        server_name=server_name,
                        tool_name=tool_name,
                        started_at=_timestamp_before(completed_at, duration_ms),
                        completed_at=completed_at,
                        duration_ms=duration_ms,
                        argument_summary=argument_summary,
                        argument_content=(
                            raw_argument_summary
                            if not tool_name.startswith("claim_")
                            and formatted_argument_summary
                            and formatted_argument_summary != raw_argument_summary
                            else ""
                        ),
                        result_summary=result_summary,
                        result_content=(
                            "" if tool_name.startswith("claim_") else _tool_result_content(result)
                        ),
                        succeeded=succeeded,
                        source_path=str(path),
                        source_ordinal=ordinal,
                        skills_loaded=sorted(loaded_skills, key=str.casefold),
                        model=model,
                    )
                )
                claim_event = _work_item_claim_event_from_mcp(
                    thread_id=thread_id,
                    timestamp=timestamp,
                    path=path,
                    ordinal=ordinal,
                    server_name=server_name,
                    tool_name=tool_name,
                    arguments=arguments,
                    result=result,
                )
                if claim_event is not None:
                    work_item_claim_events.append(claim_event)
                model_ready_at = completed_at
                continue

            if event_type in {"task_complete", "turn_aborted"}:
                turn_id = str(payload.get("turn_id") or "")
                turn = active_turns.pop(turn_id, None)
                if turn is None:
                    if turn_id in turns_by_id:
                        diagnostics.append(f"replayed terminal event for {turn_id} at {path}:{ordinal}")
                        continue
                    fields, confidence, reason = _turn_attribution(
                        payload,
                        contexts.get(turn_id, {}),
                        agent_path=agent_path,
                        agent_nickname=agent_nickname,
                    )
                    turn = AgentTurn(
                        thread_id=thread_id,
                        turn_id=turn_id or f"unmatched-terminal-{ordinal}",
                        run_id=fields["run_id"],
                        phase_id=fields["phase_id"],
                        lane_id=fields["lane_id"],
                        work_unit_id=fields["work_unit_id"],
                        activity=fields["activity"],
                        attribution_confidence="bounded" if confidence == "exact" else confidence,
                        attribution_reason=f"terminal event without start; {reason}",
                        source_path=str(path),
                        source_ordinal=ordinal,
                    )
                    turns_by_id[turn.turn_id] = turn
                    turns.append(turn)
                turn.completed_at = _normalize_timestamp(payload.get("completed_at"), timestamp)
                duration = payload.get("duration_ms", 0)
                turn.duration_ms = int(duration) if isinstance(duration, (int, float)) else 0
                ttft = payload.get("time_to_first_token_ms")
                turn.time_to_first_token_ms = int(ttft) if isinstance(ttft, (int, float)) else None
                final_message = payload.get("last_agent_message")
                turn.outcome = _terminal_turn_outcome(
                    event_type,
                    turn.turn_id,
                    final_outputs_by_turn.get(turn.turn_id, []),
                    agent_path=agent_path,
                    agent_nickname=agent_nickname,
                    final_message=final_message,
                )
                if event_type == "turn_aborted":
                    turn.abort_reason = str(payload.get("reason") or "")
                    turn.abort_event_timestamp = _normalize_timestamp(timestamp)
                has_recorded_output = turn.turn_id in output_turn_ids
                if (
                    isinstance(final_message, str)
                    and final_message.strip()
                    and not has_recorded_output
                ):
                    _append_codex_activity(
                        activities,
                        thread_id=thread_id,
                        turn_id=turn.turn_id,
                        activity_type="output",
                        timestamp=turn.completed_at,
                        path=path,
                        ordinal=ordinal,
                        summary=f"Final answer · {len(final_message):,} characters",
                        raw_text=final_message,
                        model=model,
                    )
                continue

            if event_type not in {"agent_status", "user_message", "rate_limit_event"}:
                unknown_event_counts[event_type or "missing-event-type"] = (
                    unknown_event_counts.get(event_type or "missing-event-type", 0) + 1
                )
            continue

        if record_type == "inter_agent_communication_metadata":
            if (
                payload.get("trigger_turn") is True
                and parent_thread_id
                and not spawn_boundary_seen
            ):
                spawn_boundary_seen = True
                if len(active_turns) > 1:
                    retained = max(active_turns.values(), key=lambda turn: turn.source_ordinal)
                    active_turns = {retained.turn_id: retained}
                replayed_turn_ids = set(turns_by_id) - set(active_turns)
                if replayed_turn_ids:
                    diagnostics.append(
                        "ignored replayed parent trigger turn(s): "
                        + ", ".join(sorted(replayed_turn_ids))
                    )
                turns = list(active_turns.values())
                turns_by_id = {turn.turn_id: turn for turn in turns}
                if not _usage_is_zero(previous_usage):
                    diagnostics.append(
                        "excluded inherited cumulative token baseline: "
                        f"{previous_usage.processed_tokens} processed tokens"
                    )
                responses.clear()
                if token_funding_events is not None:
                    del token_funding_events[funding_event_start:]
                activities.clear()
                final_outputs_by_turn.clear()
                output_turn_ids.clear()
                tools.clear()
                mcp_calls.clear()
                context_snapshots.clear()
                compactions.clear()
                work_item_claim_events.clear()
                skills_used.clear()
                mcp_skills_loaded.clear()
                bash_skills_loaded.clear()
                pending_tools.clear()
                model_ready_at = _normalize_timestamp(timestamp)
                pending_model_started_at = ""
                pending_model_output_timestamps.clear()
                for turn in turns:
                    turn.usage = UsageTotals()
                    turn.skills_used.clear()
                    turn.mcp_skills_loaded.clear()
                    turn.bash_skills_loaded.clear()
                    turn.mcp_call_count = 0
            continue

        if record_type == "response_item":
            item_type = str(payload.get("type") or "")
            turn_id = _event_turn_id(payload, active_turns)
            if item_type == "message":
                role = str(payload.get("role") or "")
                raw_text = _response_item_text(payload, "content")
                if raw_text and role == "user":
                    model_ready_at = _normalize_timestamp(timestamp)
                    request = _genuine_user_request(raw_text)
                    if request and not task_request_seen:
                        task_request_seen = True
                        inferred_parent = _initial_delegation_source(raw_text)
                        if (
                            infer_parent_from_delegation
                            and not parent_thread_id
                            and inferred_parent
                            and inferred_parent != thread_id
                        ):
                            parent_thread_id = inferred_parent
                            thread_name = ""
                    _append_codex_activity(
                        activities,
                        thread_id=thread_id,
                        turn_id=turn_id,
                        activity_type="input",
                        timestamp=timestamp,
                        path=path,
                        ordinal=ordinal,
                        summary=f"User input · {len(raw_text):,} characters",
                        raw_text=raw_text,
                    )
                elif raw_text and role == "assistant":
                    note_model_output(timestamp)
                    phase = str(payload.get("phase") or "")
                    label = "Final answer" if phase == "final_answer" else "Assistant output"
                    _append_codex_activity(
                        activities,
                        thread_id=thread_id,
                        turn_id=turn_id,
                        activity_type="output",
                        timestamp=timestamp,
                        path=path,
                        ordinal=ordinal,
                        summary=f"{label} · {len(raw_text):,} characters",
                        raw_text=raw_text,
                        model=model,
                    )
                    if turn_id:
                        output_turn_ids.add(turn_id)
                        if phase == "final_answer":
                            final_outputs_by_turn.setdefault(turn_id, []).append(
                                _tool_argument_content(raw_text)
                            )
            elif item_type == "agent_message":
                raw_text = _response_item_text(payload, "content")
                author = str(payload.get("author") or "")
                recipient = str(payload.get("recipient") or "")
                if raw_text and agent_path and recipient == agent_path:
                    model_ready_at = _normalize_timestamp(timestamp)
                    _append_codex_activity(
                        activities,
                        thread_id=thread_id,
                        turn_id=turn_id,
                        activity_type="input",
                        timestamp=timestamp,
                        path=path,
                        ordinal=ordinal,
                        summary=f"Delegated input from {author or 'parent'} · {len(raw_text):,} characters",
                        raw_text=raw_text,
                    )
                elif raw_text and agent_path and author == agent_path:
                    note_model_output(timestamp)
                    _append_codex_activity(
                        activities,
                        thread_id=thread_id,
                        turn_id=turn_id,
                        activity_type="output",
                        timestamp=timestamp,
                        path=path,
                        ordinal=ordinal,
                        summary=f"Agent output to {recipient or 'parent'} · {len(raw_text):,} characters",
                        raw_text=raw_text,
                        model=model,
                    )
            elif item_type == "reasoning":
                note_model_output(timestamp)
                raw_fragments = _response_item_fragments(payload, "summary")
                encrypted_content = payload.get("encrypted_content")
                if raw_fragments:
                    for fragment in raw_fragments:
                        _append_codex_activity(
                            activities,
                            thread_id=thread_id,
                            turn_id=turn_id,
                            activity_type="reasoning",
                            timestamp=timestamp,
                            path=path,
                            ordinal=ordinal,
                            summary=(
                                f"Reasoning summary · {len(fragment):,} characters"
                            ),
                            raw_text=fragment,
                            model=model,
                        )
                else:
                    if isinstance(encrypted_content, str) and encrypted_content:
                        summary = (
                            f"Encrypted reasoning · {len(encrypted_content):,} characters; "
                            "plaintext unavailable"
                        )
                    else:
                        summary = "Reasoning event · no plaintext summary recorded"
                    _append_codex_activity(
                        activities,
                        thread_id=thread_id,
                        turn_id=turn_id,
                        activity_type="reasoning",
                        timestamp=timestamp,
                        path=path,
                        ordinal=ordinal,
                        summary=summary,
                        model=model,
                    )
            elif item_type in {"function_call", "custom_tool_call"}:
                note_model_output(timestamp)
                call_id = str(payload.get("call_id") or payload.get("id") or "")
                if call_id:
                    tool_name = str(
                        payload.get("name") or payload.get("namespace") or "unknown"
                    )
                    tool_skills = _skill_names_from_value(payload.get("arguments"))
                    tool_skills.update(_skill_names_from_value(payload.get("input")))
                    skills_used.update(tool_skills)
                    bash_skill_load = _is_bash_skill_loader(
                        tool_name,
                        payload.get("arguments"),
                        payload.get("input"),
                    )
                    if bash_skill_load:
                        bash_skills_loaded.update(tool_skills)
                    turn_id = _event_turn_id(payload, active_turns)
                    if turn_id and turn_id in turns_by_id:
                        turn = turns_by_id[turn_id]
                        turn.skills_used = sorted(
                            set(turn.skills_used) | tool_skills,
                            key=str.casefold,
                        )
                        if bash_skill_load:
                            turn.bash_skills_loaded = sorted(
                                set(turn.bash_skills_loaded) | tool_skills,
                                key=str.casefold,
                            )
                    pending_tools[call_id] = (
                        tool_name,
                        timestamp,
                        turn_id,
                        ordinal,
                        _tool_argument_summary(payload),
                        _tool_argument_payload_content(payload),
                        model,
                    )
            elif item_type in {"function_call_output", "custom_tool_call_output"}:
                call_id = str(payload.get("call_id") or "")
                pending = pending_tools.pop(call_id, None)
                if pending:
                    (
                        tool_name,
                        started_at,
                        turn_id,
                        start_ordinal,
                        argument_summary,
                        argument_content,
                        tool_model,
                    ) = pending
                    raw_output = payload.get("output")
                    reported_ms = _extract_tool_wall_time_ms(raw_output)
                    result_content = _tool_result_content(raw_output)
                    elapsed_ms = _interval_ms(started_at, timestamp)
                    duration_ms = reported_ms if reported_ms is not None else elapsed_ms
                    tools.append(
                        ToolInterval(
                            thread_id=thread_id,
                            turn_id=turn_id,
                            tool_name=tool_name,
                            started_at=started_at,
                            completed_at=timestamp,
                            duration_ms=max(0, duration_ms),
                            derivation_method=(
                                "tool-reported-wall-time"
                                if reported_ms is not None
                                else "matched-event-interval"
                            ),
                            attribution_confidence="exact" if reported_ms is not None else "bounded",
                            argument_summary=argument_summary,
                            argument_content=argument_content,
                            source_path=str(path),
                            source_start_ordinal=start_ordinal,
                            source_end_ordinal=ordinal,
                            result_summary=_tool_result_summary(result_content),
                            result_content=result_content,
                            model=tool_model,
                        )
                    )
                model_ready_at = _normalize_timestamp(timestamp)
            elif item_type == "tool_search_call":
                note_model_output(timestamp)
            elif item_type == "tool_search_output":
                model_ready_at = _normalize_timestamp(timestamp)
            continue

        if record_type != "world_state":
            unknown_event_counts[record_type or "missing-type"] = (
                unknown_event_counts.get(record_type or "missing-type", 0) + 1
            )

    if not thread_id:
        raise ValueError(f"No usable session_meta identity found in {path}")
    for turn in active_turns.values():
        turn.outcome = "active"
    for key, count in sorted(unknown_event_counts.items()):
        diagnostics.append(f"unknown event type {key}: {count}")
    owned_usage = UsageTotals()
    for response in responses:
        owned_usage = owned_usage + response.usage
    turn_usage = UsageTotals()
    for turn in turns:
        turn_usage = turn_usage + turn.usage
    unattributed = _usage_nonnegative_difference(owned_usage, turn_usage)
    if turn_usage.processed_tokens > owned_usage.processed_tokens:
        diagnostics.append("turn usage exceeds owned response deltas")
    if turns and all(not turn.phase_id and not turn.lane_id for turn in turns):
        diagnostics.append(
            f"phase and lane metadata unavailable for {len(turns)} owned turn(s)"
        )
    if active_turns:
        terminal_state = "active"
    elif turns:
        terminal_state = turns[-1].outcome
    else:
        terminal_state = "indeterminate"
    return CodexThreadMetrics(
        thread_id=thread_id,
        parent_thread_id=parent_thread_id,
        thread_name=thread_name,
        task_title=task_title,
        agent_path=agent_path,
        agent_role=agent_role,
        agent_nickname=agent_nickname,
        model=model,
        effort=(
            efforts[0]
            if len(efforts) == 1
            else f"mixed ({', '.join(efforts)})" if efforts else ""
        ),
        plan_type=plan_type,
        recorded_cost_usd=recorded_cost_usd,
        started_at=min(timestamps) if timestamps else "",
        last_observed_at=max(timestamps) if timestamps else "",
        token_totals=owned_usage,
        unattributed_usage=unattributed,
        responses=responses,
        turns=turns,
        activities=activities,
        tool_intervals=tools,
        mcp_calls=mcp_calls,
        context_snapshots=context_snapshots,
        compactions=compactions,
        work_item_claim_events=work_item_claim_events,
        skills_used=sorted(skills_used, key=str.casefold),
        mcp_skills_loaded=sorted(mcp_skills_loaded, key=str.casefold),
        bash_skills_loaded=sorted(bash_skills_loaded, key=str.casefold),
        terminal_state=terminal_state,
        source_path=str(path),
        diagnostics=diagnostics,
    )


def _interval_ms(started_at: str, completed_at: str) -> int:
    start = _parse_iso_datetime(started_at)
    end = _parse_iso_datetime(completed_at)
    if start is None or end is None:
        return 0
    return max(0, round((end - start).total_seconds() * 1000))


def _candidate_rollouts(sessions_root: Path) -> list[Path]:
    if sessions_root.is_file():
        return [sessions_root.resolve()]
    if not sessions_root.exists():
        return []
    return sorted(path.resolve() for path in sessions_root.rglob("*.jsonl") if path.is_file())


@dataclass(frozen=True)
class _RolloutDiscoveryMetadata:
    identity: tuple[str, str, str, str] | None
    delegation_source_ids: frozenset[str]
    task_title: str
    started_at: str
    modified_at_ns: int


@dataclass(frozen=True)
class _RolloutParentContext:
    thread_id: str
    source_path: Path
    task_title: str


@dataclass(frozen=True)
class _NativeRolloutDiscovery:
    metadata: dict[Path, _RolloutDiscoveryMetadata]
    stats: dict[str, int]


def _native_discovery_engine_path() -> Path:
    """Resolve the one required native engine without selecting another implementation."""

    executable_name = "agent-report-engine.exe" if sys.platform == "win32" else "agent-report-engine"
    configured = os.environ.get("AGENT_REPORT_ENGINE", "").strip()
    if configured:
        configured_path = Path(configured)
        if configured_path.is_file():
            return configured_path
        raise RuntimeError(
            "Configured native discovery engine does not exist: "
            f"{configured_path}"
        )
    candidates = [
        REPO_ROOT / "tools" / "report" / "target" / "release" / executable_name,
        REPO_ROOT / "tools" / "report" / "target" / "debug" / executable_name,
        Path(sys.executable).resolve().parent / executable_name,
    ]
    on_path = shutil.which(executable_name)
    if on_path:
        candidates.append(Path(on_path))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    locations = ", ".join(str(candidate) for candidate in candidates) or executable_name
    raise RuntimeError(
        "Required native discovery engine was not found. Build or install "
        f"agent-report-engine, or set AGENT_REPORT_ENGINE. Checked: {locations}"
    )


def _native_rollout_discovery(
    candidate_paths: list[Path],
    index_path: Path | None,
) -> _NativeRolloutDiscovery:
    """Run the versioned native discovery protocol and validate its bounded response."""

    engine_path = _native_discovery_engine_path()
    request = {
        "version": NATIVE_DISCOVERY_PROTOCOL_VERSION,
        "paths": [str(path) for path in candidate_paths],
        "index_path": str(index_path) if index_path is not None else None,
        "workers": None,
    }
    try:
        completed = subprocess.run(
            [str(engine_path), "index"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise RuntimeError(
            f"Unable to start required native discovery engine {engine_path}: {error}"
        ) from error
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip() or f"exit status {completed.returncode}"
        raise RuntimeError(f"Required native discovery engine failed: {diagnostic}")
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Required native discovery engine returned invalid JSON: "
            f"{error}"
        ) from error
    if not isinstance(response, dict):
        raise RuntimeError("Required native discovery engine returned a non-object response")
    if response.get("version") != NATIVE_DISCOVERY_PROTOCOL_VERSION:
        raise RuntimeError(
            "Required native discovery engine returned unsupported protocol version "
            f"{response.get('version')!r}"
        )
    entries = response.get("entries")
    if not isinstance(entries, list) or len(entries) != len(candidate_paths):
        raise RuntimeError(
            "Required native discovery engine returned an incomplete candidate set"
        )
    metadata: dict[Path, _RolloutDiscoveryMetadata] = {}
    for expected_path, entry in zip(candidate_paths, entries, strict=True):
        if not isinstance(entry, dict) or entry.get("path") != str(expected_path):
            raise RuntimeError(
                "Required native discovery engine changed candidate ordering or paths"
            )
        raw_identity = entry.get("identity")
        identity = None
        if raw_identity is not None:
            if not isinstance(raw_identity, dict):
                raise RuntimeError("Required native discovery engine returned invalid identity")
            identity_values = tuple(
                raw_identity.get(key)
                for key in (
                    "thread_id",
                    "parent_thread_id",
                    "agent_path",
                    "agent_nickname",
                )
            )
            if not all(isinstance(value, str) for value in identity_values):
                raise RuntimeError("Required native discovery engine returned invalid identity")
            identity = identity_values
        raw_sources = entry.get("delegation_source_ids")
        if not isinstance(raw_sources, list) or not all(
            isinstance(source, str) for source in raw_sources
        ):
            raise RuntimeError(
                "Required native discovery engine returned invalid delegation sources"
            )
        task_title = entry.get("task_title")
        if not isinstance(task_title, str):
            raise RuntimeError("Required native discovery engine returned invalid task title")
        started_at = entry.get("started_at")
        modified_at_ns = entry.get("modified_at_ns")
        if not isinstance(started_at, str) or type(modified_at_ns) is not int:
            raise RuntimeError("Required native discovery engine returned invalid activity span")
        metadata[expected_path] = _RolloutDiscoveryMetadata(
            identity=identity,
            delegation_source_ids=frozenset(raw_sources),
            task_title=task_title,
            started_at=started_at,
            modified_at_ns=modified_at_ns,
        )
    raw_stats = response.get("stats")
    required_stats = (
        "candidate_files",
        "scanned_files",
        "cached_files",
        "unstable_files",
        "unreadable_files",
        "elapsed_ms",
        "workers",
    )
    if not isinstance(raw_stats, dict) or not all(
        type(raw_stats.get(key)) is int and raw_stats[key] >= 0
        for key in required_stats
    ):
        raise RuntimeError("Required native discovery engine returned invalid statistics")
    return _NativeRolloutDiscovery(
        metadata=metadata,
        stats={key: raw_stats[key] for key in required_stats},
    )


def _rollout_discovery_metadata(
    candidate_paths: list[Path],
    index_path: Path | None,
) -> dict[Path, _RolloutDiscoveryMetadata]:
    """Return metadata from the required native discovery and index engine."""

    return _native_rollout_discovery(candidate_paths, index_path).metadata


def _discover_rollout_paths(
    root_thread_id: str,
    candidate_paths: list[Path],
    *,
    include_children: bool = True,
    include_delegations: bool = False,
    index_path: Path | None = None,
) -> tuple[list[Path], list[str], _RolloutParentContext | None]:
    identities: dict[str, tuple[Path, str]] = {}
    children: dict[str, list[str]] = {}
    delegation_targets: dict[str, set[str]] = {}
    diagnostics: list[str] = []
    metadata_by_path = _rollout_discovery_metadata(candidate_paths, index_path)
    for path, metadata in metadata_by_path.items():
        identity = metadata.identity
        if identity is None:
            continue
        thread_id, parent_thread_id, _, _ = identity
        if thread_id in identities and identities[thread_id][0] != path:
            raise ValueError(
                f"Duplicate rollout ownership for thread {thread_id}: "
                f"{identities[thread_id][0]} and {path}"
            )
        identities[thread_id] = (path, parent_thread_id)
        if parent_thread_id:
            children.setdefault(parent_thread_id, []).append(thread_id)
    if root_thread_id not in identities:
        raise ValueError(f"Codex root thread not found: {root_thread_id}")
    root_path, root_parent_thread_id = identities[root_thread_id]
    if not root_parent_thread_id:
        root_entry = _read_codex_catalog_entry(root_path, "codex")
        inferred_parent_thread_id = (
            root_entry.parent_thread_id if root_entry is not None else ""
        )
        if not inferred_parent_thread_id:
            inferred_parent_thread_id = _local_codex_delegation_parents(
                {root_thread_id}
            ).get(root_thread_id, "")
        if inferred_parent_thread_id in identities:
            identities[root_thread_id] = (root_path, inferred_parent_thread_id)
            children.setdefault(inferred_parent_thread_id, []).append(root_thread_id)
    if include_delegations:
        for target_thread_id, (path, target_parent_thread_id) in identities.items():
            for source_thread_id in metadata_by_path[path].delegation_source_ids:
                source_identity = identities.get(source_thread_id)
                if (
                    source_identity is not None
                    and source_thread_id != target_thread_id
                    and target_parent_thread_id != source_thread_id
                    and source_identity[1] != target_thread_id
                ):
                    delegation_targets.setdefault(source_thread_id, set()).add(
                        target_thread_id
                    )

    validated: set[str] = set()

    def validate_hierarchy(thread_id: str, active: set[str]) -> None:
        if thread_id in active:
            raise ValueError(f"Cycle detected in Codex thread hierarchy at {thread_id}")
        if thread_id in validated:
            return
        active.add(thread_id)
        if include_children:
            for child_thread_id in children.get(thread_id, []):
                validate_hierarchy(child_thread_id, active)
        active.remove(thread_id)
        validated.add(thread_id)

    ordered_ids: list[str] = []
    queue = [root_thread_id]
    included: set[str] = set()
    while queue:
        thread_id = queue.pop(0)
        if thread_id in included:
            continue
        validate_hierarchy(thread_id, set())
        included.add(thread_id)
        ordered_ids.append(thread_id)
        if include_children:
            queue.extend(sorted(children.get(thread_id, [])))
        if include_delegations:
            queue.extend(sorted(delegation_targets.get(thread_id, set())))
    for thread_id in ordered_ids:
        parent_thread_id = identities[thread_id][1]
        if thread_id != root_thread_id and parent_thread_id not in included:
            diagnostics.append(f"missing included parent {parent_thread_id} for {thread_id}")
    parent_context = None
    parent_thread_id = identities[root_thread_id][1]
    if parent_thread_id and parent_thread_id in identities:
        parent_path = identities[parent_thread_id][0]
        parent_context = _RolloutParentContext(
            thread_id=parent_thread_id,
            source_path=parent_path,
            task_title=metadata_by_path[parent_path].task_title,
        )
    return (
        [identities[thread_id][0] for thread_id in ordered_ids],
        diagnostics,
        parent_context,
    )


def _pricing_metadata() -> tuple[str, str]:
    try:
        raw_bytes = PRICING_FILE.read_bytes()
        raw = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError):
        return "", ""
    version = str(raw.get("_updated_at") or "") if isinstance(raw, dict) else ""
    return version, hashlib.sha256(raw_bytes).hexdigest()


def _cost_for_usage(
    usage: UsageTotals,
    model_usage: dict[str, UsageTotals],
    *,
    plan_types: set[str],
) -> CostAssessment:
    pricing_version, pricing_digest = _pricing_metadata()
    if usage.processed_tokens == 0:
        return CostAssessment(
            status="unavailable",
            pricing_version=pricing_version,
            pricing_digest=pricing_digest,
            method="no token usage",
        )
    pricing = _load_pricing_table()
    unsupported = sorted(model for model in model_usage if not pricing.get(_normalize_model_name(model)))
    if not model_usage or unsupported:
        status = "subscription-no-charge-data" if plan_types else "unavailable"
        return CostAssessment(
            status=status,
            pricing_model=", ".join(sorted(model_usage)),
            pricing_version=pricing_version,
            pricing_digest=pricing_digest,
            method=(
                "subscription telemetry has no monetary charge data"
                if status == "subscription-no-charge-data"
                else "model pricing unavailable"
            ),
        )
    input_cost = 0.0
    cached_cost = 0.0
    output_cost = 0.0
    for model, model_tokens in model_usage.items():
        rates = pricing[_normalize_model_name(model)]
        input_cost += model_tokens.uncached_input_tokens * rates["input_per_million"] / 1_000_000
        cached_cost += model_tokens.cached_input_tokens * rates["cached_input_per_million"] / 1_000_000
        output_cost += model_tokens.output_tokens * rates["output_per_million"] / 1_000_000
    return CostAssessment(
        status="estimated",
        pricing_model=", ".join(sorted(model_usage)),
        pricing_version=pricing_version,
        pricing_digest=pricing_digest,
        input_cost=input_cost,
        cached_input_cost=cached_cost,
        output_cost=output_cost,
        total_cost=input_cost + cached_cost + output_cost,
        method="API-equivalent token-price estimate; not an actual charge",
    )


def _cost_for_thread_usage(
    thread: CodexThreadMetrics,
    usage: UsageTotals,
) -> CostAssessment:
    """Price or proportionally allocate one thread-owned usage bucket."""
    if thread.recorded_cost_usd is not None and thread.token_totals.processed_tokens:
        ratio = min(
            1.0,
            max(0.0, usage.processed_tokens / thread.token_totals.processed_tokens),
        )
        return CostAssessment(
            status="recorded",
            total_cost=thread.recorded_cost_usd * ratio,
            method="proportional allocation of recorded thread cost",
        )
    model_usage = {thread.model: usage} if thread.model else {}
    plan_types = {thread.plan_type} if thread.plan_type else set()
    return _cost_for_usage(usage, model_usage, plan_types=plan_types)


def _cost_for_response(
    thread: CodexThreadMetrics,
    response: ResponseUsage,
) -> CostAssessment:
    """Return the monetary cost owned by one recorded model response."""

    if response.recorded_cost_usd is not None:
        return CostAssessment(
            status="recorded",
            total_cost=response.recorded_cost_usd,
            method="recorded response cost",
        )
    response_model = response.model or (
        thread.model if not thread.model.startswith("mixed (") else ""
    )
    model_usage = {response_model: response.usage} if response_model else {}
    plan_types = {thread.plan_type} if thread.plan_type else set()
    return _cost_for_usage(response.usage, model_usage, plan_types=plan_types)


def _cost_for_turn(
    thread: CodexThreadMetrics,
    turn: AgentTurn,
) -> CostAssessment:
    """Return direct response cost for a task span when fully available."""

    owned_responses = [
        response for response in thread.responses if response.turn_id == turn.turn_id
    ]
    if owned_responses and all(
        response.recorded_cost_usd is not None for response in owned_responses
    ):
        return CostAssessment(
            status="recorded",
            total_cost=sum(response.recorded_cost_usd or 0.0 for response in owned_responses),
            method="sum of task-owned response costs",
        )
    return _cost_for_thread_usage(thread, turn.usage)


def _models_for_turn(thread: CodexThreadMetrics, turn_id: str) -> list[str]:
    """Return turn model names in first-observed order."""

    return list(
        dict.fromkeys(
            response.model
            for response in thread.responses
            if response.turn_id == turn_id and response.model
        )
    )


def _models_before_source(
    thread: CodexThreadMetrics,
    *,
    turn_id: str | None,
    source_path: str,
    source_ordinal: int,
) -> list[str]:
    """Return models from the latest response preceding one source event."""

    candidates = [
        response
        for response in thread.responses
        if response.turn_id == turn_id
        and response.source_path == source_path
        and response.source_ordinal < source_ordinal
        and response.model
    ]
    if not candidates:
        return []
    latest_ordinal = max(response.source_ordinal for response in candidates)
    return list(
        dict.fromkeys(
            response.model
            for response in candidates
            if response.source_ordinal == latest_ordinal
        )
    )


def _render_model_names(models: list[str], *, attributed: bool = False) -> str:
    if not models:
        return "—"
    title = (
        ' title="Attributed from the latest preceding model response in this task span"'
        if attributed
        else ""
    )
    return (
        f'<code class="model-name"{title}>'
        + "<br>".join(_escape_html(model) for model in models)
        + "</code>"
    )


def _render_turn_model_metric(thread: CodexThreadMetrics, turn_id: str) -> str:
    models = _models_for_turn(thread, turn_id)
    if not models:
        return _escape_html(thread.model or "—")
    if len(models) == 1:
        return _escape_html(models[0])
    return (
        f'mixed ({len(models)} models)'
        f'<span class="metric-detail">{" · ".join(_escape_html(model) for model in models)}</span>'
    )


def _is_empty_delegated_continuation(activity: AgentActivity) -> bool:
    """Identify content-free inter-agent MESSAGE envelopes in a turn."""

    if (
        activity.activity_type != "input"
        or not activity.summary.startswith("Delegated input from ")
    ):
        return False
    lines = activity.content.splitlines()
    message_type = next(
        (
            line.partition(":")[2].strip()
            for line in lines
            if line.startswith("Message Type:")
        ),
        "",
    )
    payload_index = next(
        (index for index, line in enumerate(lines) if line.startswith("Payload:")),
        None,
    )
    if message_type != "MESSAGE" or payload_index is None:
        return False
    inline_payload = lines[payload_index].partition(":")[2].strip()
    remaining_payload = "\n".join(lines[payload_index + 1 :]).strip()
    return not inline_payload and not remaining_payload


def _render_activity_detail(activity: AgentActivity, *, raw_label: str) -> str:
    summary = _escape_html(activity.summary or "—")
    if not activity.content:
        return f'<div class="activity-summary">{summary}</div>'
    return (
        f'<div class="activity-summary">{summary}</div>'
        f'<details class="activity-raw"><summary>{raw_label}</summary>'
        f'<pre>{_escape_html(activity.content)}</pre></details>'
    )


def _model_response_activity_groups(
    responses: list[ResponseUsage],
    response_index: int,
    activities: list[AgentActivity],
) -> tuple[list[AgentActivity], list[AgentActivity]]:
    """Return recorded prompt and result fragments for one model response."""

    response = responses[response_index]
    previous_ordinal = (
        responses[response_index - 1].source_ordinal if response_index else -1
    )
    next_ordinal = (
        responses[response_index + 1].source_ordinal
        if response_index + 1 < len(responses)
        else float("inf")
    )
    same_source = [
        activity
        for activity in activities
        if activity.source_path == response.source_path
    ]
    prompt_activities = [
        activity
        for activity in same_source
        if activity.activity_type == "input"
        and previous_ordinal < activity.source_ordinal < response.source_ordinal
    ]
    if response.derivation_method == "Junie response metadata":
        result_activities = [
            activity
            for activity in same_source
            if activity.activity_type in {"reasoning", "output"}
            and response.source_ordinal < activity.source_ordinal < next_ordinal
        ]
    else:
        result_activities = [
            activity
            for activity in same_source
            if activity.activity_type in {"reasoning", "output"}
            and previous_ordinal < activity.source_ordinal < response.source_ordinal
        ]
        if response_index + 1 == len(responses):
            result_activities.extend(
                activity
                for activity in same_source
                if activity.activity_type == "output"
                and activity.source_ordinal > response.source_ordinal
            )
    return prompt_activities, sorted(
        result_activities,
        key=lambda activity: activity.source_ordinal,
    )


def _render_model_activity_disclosure(
    activities: list[AgentActivity],
    *,
    raw_label: str,
) -> str:
    """Render bounded recorded fragments inside one model invocation cell."""

    if not activities:
        return ""
    labels = {
        "input": "prompt",
        "reasoning": "thinking",
        "output": "response",
    }
    fragments = []
    counts: Counter[str] = Counter()
    for activity in activities:
        label = labels.get(activity.activity_type, activity.activity_type)
        counts[label] += 1
        body = activity.content or activity.summary
        fragments.append(f"[{label}]\n{body}")
    summary = " · ".join(
        f"{count:,} {label} fragment{'s' if count != 1 else ''}"
        for label, count in counts.items()
    )
    content = _tool_argument_content("\n\n".join(fragments))
    return (
        f'<div class="activity-summary">{_escape_html(summary)}</div>'
        f'<details class="activity-raw"><summary>{raw_label}</summary>'
        f'<pre>{_escape_html(content)}</pre></details>'
    )


def _time_metrics(
    threads: list[CodexThreadMetrics],
) -> tuple[str, str, int, int, int, int, int]:
    observed_starts = [
        value
        for value in (_parse_iso_datetime(thread.started_at) for thread in threads)
        if value is not None
    ]
    observed_ends = [
        value
        for value in (_parse_iso_datetime(thread.last_observed_at) for thread in threads)
        if value is not None
    ]
    wall_start = min(observed_starts) if observed_starts else None
    wall_end = max(observed_ends) if observed_ends else None
    wall_ms = (
        max(0, round((wall_end - wall_start).total_seconds() * 1000))
        if wall_start and wall_end
        else 0
    )
    intervals: list[tuple[datetime, datetime]] = []
    agent_time_ms = 0
    tool_time_ms = 0
    for thread in threads:
        agent_time_ms += sum(turn.duration_ms for turn in thread.turns)
        tool_time_ms += sum(tool.duration_ms for tool in thread.tool_intervals)
        tool_time_ms += sum(call.duration_ms for call in thread.mcp_calls)
        for turn in thread.turns:
            start = _parse_iso_datetime(turn.started_at)
            end = _parse_iso_datetime(turn.completed_at)
            if start is not None and end is not None and end >= start:
                intervals.append((start, end))
    active_time_ms = 0
    if intervals:
        merged_start, merged_end = sorted(intervals)[0]
        for start, end in sorted(intervals)[1:]:
            if start <= merged_end:
                merged_end = max(merged_end, end)
            else:
                active_time_ms += round((merged_end - merged_start).total_seconds() * 1000)
                merged_start, merged_end = start, end
        active_time_ms += round((merged_end - merged_start).total_seconds() * 1000)
    points: list[tuple[datetime, int]] = []
    for start, end in intervals:
        points.append((start, 1))
        points.append((end, -1))
    concurrent = 0
    peak = 0
    for _, delta in sorted(points, key=lambda item: (item[0], item[1])):
        concurrent += delta
        peak = max(peak, concurrent)
    return (
        wall_start.isoformat() if wall_start else "",
        wall_end.isoformat() if wall_end else "",
        wall_ms,
        agent_time_ms,
        active_time_ms,
        tool_time_ms,
        peak,
    )


def _percentile(values: list[float], quantile: float) -> float | None:
    """Return a linearly interpolated percentile for a bounded numeric list."""

    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * min(1.0, max(0.0, quantile))
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _inference_call_usage(response: ResponseUsage) -> UsageTotals:
    """Prefer direct last-call counters while retaining older-log fallback."""

    return (
        response.reported_usage
        if not _usage_is_zero(response.reported_usage)
        else response.usage
    )


def _inference_summary(responses: list[ResponseUsage]) -> InferenceSummary:
    """Aggregate only inference intervals supported by recorded boundaries."""

    output_tokens = sum(_inference_call_usage(response).output_tokens for response in responses)
    reasoning_tokens = sum(
        _inference_call_usage(response).reasoning_tokens for response in responses
    )
    measured = [response for response in responses if response.duration_ms > 0]
    decoded = [
        response
        for response in measured
        if response.decode_time_ms is not None and response.decode_time_ms > 0
    ]
    inference_ms = sum(response.duration_ms for response in measured)
    decode_ms = sum(response.decode_time_ms or 0 for response in decoded)
    measured_output = sum(_inference_call_usage(response).output_tokens for response in measured)
    decoded_output = sum(_inference_call_usage(response).output_tokens for response in decoded)
    call_rates = [
        _inference_call_usage(response).output_tokens / (response.duration_ms / 1000)
        for response in measured
    ]
    ttfts = [
        float(response.ttft_ms)
        for response in measured
        if response.ttft_ms is not None
    ]
    return InferenceSummary(
        call_count=len(responses),
        measured_call_count=len(measured),
        decode_measured_call_count=len(decoded),
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        inference_time_ms=inference_ms,
        decode_time_ms=decode_ms,
        end_to_end_tokens_per_second=(
            measured_output / (inference_ms / 1000) if inference_ms else None
        ),
        decode_tokens_per_second=(
            decoded_output / (decode_ms / 1000) if decode_ms else None
        ),
        median_ttft_ms=_percentile(ttfts, 0.5),
        p50_call_tokens_per_second=_percentile(call_rates, 0.5),
        p90_call_tokens_per_second=_percentile(call_rates, 0.9),
        evidence=(
            "inferred-recorded-boundaries" if measured else "unavailable"
        ),
    )


def _inference_trends(
    responses: list[ResponseUsage],
    *,
    bucket_minutes: int = 15,
) -> list[InferenceTrendBucket]:
    """Return stable fixed-width localizable inference-rate buckets."""

    bucket_seconds = bucket_minutes * 60
    grouped: dict[datetime, list[ResponseUsage]] = {}
    for response in responses:
        timestamp = _parse_iso_datetime(
            response.last_output_at or response.event_timestamp
        )
        if timestamp is None:
            continue
        epoch = int(timestamp.timestamp())
        bucket = datetime.fromtimestamp(
            epoch - epoch % bucket_seconds,
            tz=timezone.utc,
        )
        grouped.setdefault(bucket, []).append(response)
    trends = []
    for started_at, members in sorted(grouped.items()):
        measured = [member for member in members if member.duration_ms > 0]
        inference_ms = sum(member.duration_ms for member in measured)
        output_tokens = sum(_inference_call_usage(member).output_tokens for member in measured)
        trends.append(
            InferenceTrendBucket(
                started_at=started_at.isoformat(),
                call_count=len(members),
                output_tokens=sum(
                    _inference_call_usage(member).output_tokens for member in members
                ),
                inference_time_ms=inference_ms,
                tokens_per_second=(
                    output_tokens / (inference_ms / 1000) if inference_ms else None
                ),
            )
        )
    return trends


def _inference_size_bands(responses: list[ResponseUsage]) -> list[InferenceSizeBand]:
    """Group measured calls by output size to expose size-controlled variation."""

    definitions = (
        ("<128", 0, 127),
        ("128–255", 128, 255),
        ("256–511", 256, 511),
        ("512–999", 512, 999),
        ("1,000+", 1_000, None),
    )
    results = []
    for label, minimum, maximum in definitions:
        members = [
            response
            for response in responses
            if response.duration_ms > 0
            and _inference_call_usage(response).output_tokens >= minimum
            and (
                maximum is None
                or _inference_call_usage(response).output_tokens <= maximum
            )
        ]
        if not members:
            continue
        inference_ms = sum(response.duration_ms for response in members)
        output_tokens = sum(
            _inference_call_usage(response).output_tokens for response in members
        )
        call_rates = [
            _inference_call_usage(response).output_tokens
            / (response.duration_ms / 1000)
            for response in members
        ]
        results.append(
            InferenceSizeBand(
                label=label,
                call_count=len(members),
                output_tokens=output_tokens,
                inference_time_ms=inference_ms,
                weighted_tokens_per_second=(
                    output_tokens / (inference_ms / 1000) if inference_ms else None
                ),
                median_call_tokens_per_second=_percentile(call_rates, 0.5),
            )
        )
    return results


def _context_summary(root_thread: CodexThreadMetrics) -> ContextSummary:
    """Summarize the selected root's direct context snapshots."""

    if not root_thread.context_snapshots:
        return ContextSummary()
    current = root_thread.context_snapshots[-1]
    average_total_tokens = round(
        sum(snapshot.total_tokens for snapshot in root_thread.context_snapshots)
        / len(root_thread.context_snapshots)
    )
    observed_percentages = [
        snapshot.occupancy_percent
        for snapshot in root_thread.context_snapshots
        if snapshot.occupancy_percent is not None
    ]
    high_water = max(
        root_thread.context_snapshots,
        key=lambda snapshot: snapshot.total_tokens,
    )
    direct_compactions = sum(
        1 for compaction in root_thread.compactions if compaction.recorded
    )
    evidence = (
        "direct"
        if direct_compactions == len(root_thread.compactions)
        else "mixed-direct-and-inferred"
    )
    return ContextSummary(
        average_total_tokens=average_total_tokens,
        average_percent=(
            sum(observed_percentages) / len(observed_percentages)
            if observed_percentages
            else None
        ),
        current_total_tokens=current.total_tokens,
        current_input_tokens=current.input_tokens,
        current_cached_input_tokens=current.cached_input_tokens,
        capacity=current.capacity,
        remaining_tokens=current.remaining_tokens,
        occupancy_percent=current.occupancy_percent,
        cached_input_percent=current.cached_input_percent,
        high_water_tokens=high_water.total_tokens,
        high_water_percent=high_water.occupancy_percent,
        compaction_count=len(root_thread.compactions),
        last_observed_at=current.event_timestamp,
        evidence=evidence,
    )


def _context_trends(
    root_thread: CodexThreadMetrics,
    *,
    bucket_minutes: int = 15,
) -> list[ContextTrendBucket]:
    """Summarize root context growth and compactions without payload retention."""

    bucket_seconds = bucket_minutes * 60
    grouped: dict[datetime, list[ContextSnapshot]] = {}
    for snapshot in root_thread.context_snapshots:
        timestamp = _parse_iso_datetime(snapshot.event_timestamp)
        if timestamp is None:
            continue
        epoch = int(timestamp.timestamp())
        bucket = datetime.fromtimestamp(
            epoch - epoch % bucket_seconds,
            tz=timezone.utc,
        )
        grouped.setdefault(bucket, []).append(snapshot)
    compaction_times = [
        _parse_iso_datetime(compaction.event_timestamp)
        for compaction in root_thread.compactions
    ]
    results = []
    for started_at, snapshots in sorted(grouped.items()):
        ended_at = started_at + timedelta(seconds=bucket_seconds)
        totals = [snapshot.total_tokens for snapshot in snapshots]
        maximum = max(snapshots, key=lambda snapshot: snapshot.total_tokens)
        results.append(
            ContextTrendBucket(
                started_at=started_at.isoformat(),
                snapshot_count=len(snapshots),
                first_total_tokens=snapshots[0].total_tokens,
                last_total_tokens=snapshots[-1].total_tokens,
                low_total_tokens=min(totals),
                high_total_tokens=max(totals),
                capacity=maximum.capacity,
                compaction_count=sum(
                    timestamp is not None and started_at <= timestamp < ended_at
                    for timestamp in compaction_times
                ),
            )
        )
    return results


def _runtime_tool_state(tool_name: str, argument_summary: str) -> str:
    """Classify only high-signal wait and test/process tool intervals."""

    normalized = tool_name.casefold().replace(":", ".")
    leaf = normalized.rsplit(".", 1)[-1]
    if leaf in {"wait_agent", "wait_threads"}:
        return "agent_wait"
    if leaf in {"write_stdin", "wait"}:
        return "test_process"
    if leaf in {"request_user_input", "request_plugin_install"} or "approval" in leaf:
        return "approval_infrastructure"
    if leaf in {"exec", "exec_command", "shell", "terminal"} and re.search(
        r"(?i)(?:^|[^a-z])(test|pytest|vitest|jest|build|verify|lint|check)(?:[^a-z]|$)",
        argument_summary,
    ):
        return "test_process"
    return "tool_execution"


def _thread_runtime_role(thread: CodexThreadMetrics) -> str:
    """Return a whole-turn infrastructure role when directly identified."""

    identity = " ".join(
        (
            thread.agent_role,
            thread.agent_path,
            thread.thread_name,
            thread.task_title,
        )
    ).casefold()
    if "watchdog" in identity:
        return "watchdog"
    if "approval" in identity or "guardian" in identity:
        return "approval_infrastructure"
    return ""


def _interval_overlap_ms(
    left_start: str,
    left_end: str,
    right_start: str,
    right_end: str,
) -> int:
    """Return the overlap of two ISO intervals in milliseconds."""

    starts = (_parse_iso_datetime(left_start), _parse_iso_datetime(right_start))
    ends = (_parse_iso_datetime(left_end), _parse_iso_datetime(right_end))
    if any(value is None for value in (*starts, *ends)):
        return 0
    start = max(value for value in starts if value is not None)
    end = min(value for value in ends if value is not None)
    return max(0, round((end - start).total_seconds() * 1000))


def _response_effort(thread: CodexThreadMetrics, response: ResponseUsage) -> str:
    """Return direct response effort or a uniform thread-level fallback."""

    return response.effort or (
        thread.effort
        if thread.effort and not thread.effort.startswith("mixed (")
        else ""
    )


def _runtime_intervals_for_thread(
    thread: CodexThreadMetrics,
    *,
    include_user_pauses: bool,
) -> list[RuntimeStateInterval]:
    """Partition recorded turns into mutually exclusive runtime states."""

    role_state = _thread_runtime_role(thread)
    candidates_by_turn: dict[
        str | None, list[tuple[datetime, datetime, str, str, str, str]]
    ] = {}

    def add_candidate(
        turn_id: str | None,
        started_at: str,
        completed_at: str,
        state: str,
        method: str,
        confidence: str,
        detail: str,
    ) -> None:
        start = _parse_iso_datetime(started_at)
        end = _parse_iso_datetime(completed_at)
        if start is not None and end is not None and end > start:
            candidates_by_turn.setdefault(turn_id, []).append(
                (start, end, state, method, confidence, detail)
            )

    for response in thread.responses:
        if response.started_at and response.last_output_at and response.duration_ms > 0:
            response_detail = response.model
            response_effort = _response_effort(thread, response)
            if response_effort:
                effort_detail = f"effort {response_effort}"
                response_detail = (
                    f"{response_detail} · {effort_detail}"
                    if response_detail
                    else effort_detail
                )
            add_candidate(
                response.turn_id,
                response.started_at,
                response.last_output_at,
                "model_inference",
                response.timing_method,
                response.timing_confidence,
                response_detail,
            )
    for tool in thread.tool_intervals:
        add_candidate(
            tool.turn_id,
            tool.started_at,
            tool.completed_at,
            _runtime_tool_state(tool.tool_name, tool.argument_summary),
            tool.derivation_method,
            tool.attribution_confidence,
            tool.tool_name,
        )
    for call in thread.mcp_calls:
        add_candidate(
            call.turn_id,
            call.started_at,
            call.completed_at,
            _runtime_tool_state(call.tool_name, call.argument_summary),
            "mcp-recorded-duration",
            "exact",
            f"{call.server_name}.{call.tool_name}",
        )
    priority = {
        "agent_wait": 60,
        "test_process": 50,
        "approval_infrastructure": 45,
        "tool_execution": 40,
        "model_inference": 30,
    }
    intervals: list[RuntimeStateInterval] = []
    sorted_turns = sorted(
        thread.turns,
        key=lambda turn: _parse_iso_datetime(turn.started_at) or datetime.min.replace(tzinfo=timezone.utc),
    )
    for turn in sorted_turns:
        turn_start = _parse_iso_datetime(turn.started_at)
        turn_end = _parse_iso_datetime(turn.completed_at or thread.last_observed_at)
        if turn_start is None or turn_end is None or turn_end <= turn_start:
            continue
        if role_state:
            intervals.append(
                RuntimeStateInterval(
                    thread_id=thread.thread_id,
                    turn_id=turn.turn_id,
                    state=role_state,
                    started_at=turn_start.isoformat(),
                    completed_at=turn_end.isoformat(),
                    duration_ms=round((turn_end - turn_start).total_seconds() * 1000),
                    derivation_method="recorded-agent-role-turn",
                    attribution_confidence="exact",
                    detail=thread.agent_role or thread.agent_path or thread.thread_name,
                )
            )
            continue
        clipped: list[tuple[datetime, datetime, str, str, str, str]] = []
        boundaries = {turn_start, turn_end}
        turn_candidates = candidates_by_turn.get(turn.turn_id, [])
        if None in candidates_by_turn:
            turn_candidates = turn_candidates + candidates_by_turn[None]
        for start, end, state, method, confidence, detail in turn_candidates:
            start = max(turn_start, start)
            end = min(turn_end, end)
            if end <= start:
                continue
            clipped.append((start, end, state, method, confidence, detail))
            boundaries.update((start, end))
        ordered = sorted(boundaries)
        for start, end in zip(ordered, ordered[1:]):
            if end <= start:
                continue
            active = [
                candidate
                for candidate in clipped
                if candidate[0] < end and candidate[1] > start
            ]
            if active:
                selected = max(active, key=lambda item: priority.get(item[2], 0))
                state, method, confidence, detail = selected[2:]
            else:
                state = "unattributed"
                method = "turn-remainder"
                confidence = "inferred"
                detail = ""
            duration_ms = round((end - start).total_seconds() * 1000)
            if (
                intervals
                and intervals[-1].thread_id == thread.thread_id
                and intervals[-1].turn_id == turn.turn_id
                and intervals[-1].state == state
                and intervals[-1].completed_at == start.isoformat()
                and intervals[-1].detail == detail
            ):
                intervals[-1].completed_at = end.isoformat()
                intervals[-1].duration_ms += duration_ms
            else:
                intervals.append(
                    RuntimeStateInterval(
                        thread_id=thread.thread_id,
                        turn_id=turn.turn_id,
                        state=state,
                        started_at=start.isoformat(),
                        completed_at=end.isoformat(),
                        duration_ms=duration_ms,
                        derivation_method=method,
                        attribution_confidence=confidence,
                        detail=detail,
                    )
                )
    if include_user_pauses:
        for earlier, later in zip(sorted_turns, sorted_turns[1:]):
            start = _parse_iso_datetime(earlier.completed_at)
            end = _parse_iso_datetime(later.started_at)
            if start is None or end is None or end <= start:
                continue
            intervals.append(
                RuntimeStateInterval(
                    thread_id=thread.thread_id,
                    turn_id=None,
                    state="user_pause",
                    started_at=start.isoformat(),
                    completed_at=end.isoformat(),
                    duration_ms=round((end - start).total_seconds() * 1000),
                    derivation_method="between-recorded-turns",
                    attribution_confidence="exact",
                )
            )
    return sorted(
        intervals,
        key=lambda interval: (
            _parse_iso_datetime(interval.started_at)
            or datetime.min.replace(tzinfo=timezone.utc),
            interval.thread_id,
        ),
    )


def _union_interval_ms(intervals: list[tuple[datetime, datetime]]) -> int:
    """Return concurrency-aware union duration for datetime intervals."""

    valid = sorted((start, end) for start, end in intervals if end > start)
    if not valid:
        return 0
    merged_start, merged_end = valid[0]
    duration_ms = 0
    for start, end in valid[1:]:
        if start <= merged_end:
            merged_end = max(merged_end, end)
        else:
            duration_ms += round((merged_end - merged_start).total_seconds() * 1000)
            merged_start, merged_end = start, end
    return duration_ms + round((merged_end - merged_start).total_seconds() * 1000)


def _runtime_state_metrics(
    threads: list[CodexThreadMetrics],
    *,
    root_thread_id: str,
) -> tuple[list[RuntimeStateInterval], list[RuntimeStateSummary], int]:
    """Aggregate runtime states and isolate waits with no productive peer."""

    intervals = [
        interval
        for thread in threads
        for interval in _runtime_intervals_for_thread(
            thread,
            include_user_pauses=thread.thread_id == root_thread_id,
        )
    ]
    summaries = []
    for state in sorted({interval.state for interval in intervals}):
        members = [interval for interval in intervals if interval.state == state]
        wall_intervals = []
        for member in members:
            start = _parse_iso_datetime(member.started_at)
            end = _parse_iso_datetime(member.completed_at)
            if start is not None and end is not None:
                wall_intervals.append((start, end))
        summaries.append(
            RuntimeStateSummary(
                state=state,
                interval_count=len(members),
                agent_time_ms=sum(member.duration_ms for member in members),
                run_time_ms=_union_interval_ms(wall_intervals),
                direct_interval_count=sum(
                    member.attribution_confidence == "exact" for member in members
                ),
                inferred_interval_count=sum(
                    member.attribution_confidence != "exact" for member in members
                ),
            )
        )
    waiting_slices: list[tuple[datetime, datetime]] = []
    productive_by_thread: dict[str, list[tuple[datetime, datetime]]] = {}
    for interval in intervals:
        if interval.state in {"agent_wait", "user_pause"}:
            continue
        start = _parse_iso_datetime(interval.started_at)
        end = _parse_iso_datetime(interval.completed_at)
        if start is not None and end is not None:
            productive_by_thread.setdefault(interval.thread_id, []).append((start, end))
    for thread_id, members in productive_by_thread.items():
        merged: list[tuple[datetime, datetime]] = []
        for start, end in sorted(members):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        productive_by_thread[thread_id] = merged
    for waiting in (item for item in intervals if item.state == "agent_wait"):
        waiting_start = _parse_iso_datetime(waiting.started_at)
        waiting_end = _parse_iso_datetime(waiting.completed_at)
        if waiting_start is None or waiting_end is None:
            continue
        boundaries = {waiting_start, waiting_end}
        peers: list[tuple[datetime, datetime]] = []
        for active_thread_id, active_intervals in productive_by_thread.items():
            if active_thread_id == waiting.thread_id:
                continue
            starts = [item[0] for item in active_intervals]
            first = max(0, bisect_right(starts, waiting_start) - 1)
            for active_start, active_end in active_intervals[first:]:
                if active_start >= waiting_end:
                    break
                start = max(waiting_start, active_start)
                end = min(waiting_end, active_end)
                if end > start:
                    peers.append((start, end))
                    boundaries.update((start, end))
        ordered = sorted(boundaries)
        for start, end in zip(ordered, ordered[1:]):
            if not any(peer_start < end and peer_end > start for peer_start, peer_end in peers):
                waiting_slices.append((start, end))
    return intervals, summaries, _union_interval_ms(waiting_slices)


def _work_item_segments(
    threads: list[CodexThreadMetrics],
    runtime_intervals: list[RuntimeStateInterval],
    *,
    observed_at: str,
) -> list[WorkItemSegment]:
    """Pair exact claim events and allocate call/runtime metrics by interval."""

    events = sorted(
        (
            event
            for thread in threads
            for event in thread.work_item_claim_events
        ),
        key=lambda event: (
            _parse_iso_datetime(event.event_timestamp)
            or datetime.min.replace(tzinfo=timezone.utc),
            event.source_ordinal,
        ),
    )
    open_events: dict[tuple[str, str], WorkItemClaimEvent] = {}
    pairs: list[tuple[WorkItemClaimEvent, WorkItemClaimEvent | None]] = []
    for event in events:
        key = (event.thread_id, event.claim_id)
        if event.operation == "acquire":
            open_events[key] = event
        elif event.operation == "release":
            acquired = open_events.pop(key, None)
            if acquired is not None and acquired.work_item_id == event.work_item_id:
                pairs.append((acquired, event))
    pairs.extend((event, None) for event in open_events.values())
    responses = [response for thread in threads for response in thread.responses]
    segments = []
    for acquired, released in sorted(
        pairs,
        key=lambda pair: _parse_iso_datetime(pair[0].event_timestamp)
        or datetime.min.replace(tzinfo=timezone.utc),
    ):
        ended_at = released.event_timestamp if released is not None else observed_at
        selected_responses = []
        for response in responses:
            point = response.last_output_at or response.event_timestamp
            if _interval_overlap_ms(
                acquired.event_timestamp,
                ended_at,
                point,
                point,
            ):
                selected_responses.append(response)
                continue
            point_time = _parse_iso_datetime(point)
            start_time = _parse_iso_datetime(acquired.event_timestamp)
            end_time = _parse_iso_datetime(ended_at)
            if (
                point_time is not None
                and start_time is not None
                and end_time is not None
                and start_time <= point_time <= end_time
            ):
                selected_responses.append(response)
        usage = UsageTotals()
        for response in selected_responses:
            usage = usage + response.usage
        runtime_state_ms: dict[str, int] = {}
        for interval in runtime_intervals:
            overlap_ms = _interval_overlap_ms(
                acquired.event_timestamp,
                ended_at,
                interval.started_at,
                interval.completed_at,
            )
            if overlap_ms:
                runtime_state_ms[interval.state] = (
                    runtime_state_ms.get(interval.state, 0) + overlap_ms
                )
        segments.append(
            WorkItemSegment(
                work_item_id=acquired.work_item_id,
                claim_id=acquired.claim_id,
                activity=acquired.activity,
                disposition=(released.disposition if released else "open"),
                blocker_reference=(released.blocker_reference if released else ""),
                agent=acquired.agent,
                thread_id=acquired.thread_id,
                started_at=acquired.event_timestamp,
                ended_at=ended_at,
                duration_ms=_interval_ms(acquired.event_timestamp, ended_at),
                open=released is None,
                usage=usage,
                inference=_inference_summary(selected_responses),
                runtime_state_ms=dict(sorted(runtime_state_ms.items())),
            )
        )
    return segments


def _aggregate_work_units(
    threads: list[CodexThreadMetrics],
) -> list[WorkUnitMetrics]:
    grouped: dict[str, list[tuple[AgentTurn, CodexThreadMetrics]]] = {}
    for thread in threads:
        for turn in thread.turns:
            work_unit_id = turn.work_unit_id or "unattributed"
            grouped.setdefault(work_unit_id, []).append((turn, thread))
    results: list[WorkUnitMetrics] = []
    confidence_order = {"exact": 0, "bounded": 1, "inferred": 2, "unattributed": 3}
    for work_unit_id, members in sorted(grouped.items()):
        usage = UsageTotals()
        model_usage: dict[str, UsageTotals] = {}
        plan_types: set[str] = set()
        for turn, thread in members:
            usage = usage + turn.usage
            if thread.model:
                model_usage[thread.model] = model_usage.get(thread.model, UsageTotals()) + turn.usage
            if thread.plan_type:
                plan_types.add(thread.plan_type)
        worst_confidence = max(
            (turn.attribution_confidence for turn, _ in members),
            key=lambda item: confidence_order.get(item, 4),
        )
        first = members[0][0]
        results.append(
            WorkUnitMetrics(
                work_unit_id=work_unit_id,
                phase_id=first.phase_id,
                lane_id=first.lane_id,
                activity=first.activity,
                turn_ids=[turn.turn_id for turn, _ in members],
                usage=usage,
                allocation_method=(
                    "explicit-turn-ownership"
                    if worst_confidence == "exact"
                    else "inferred-turn-ownership"
                    if worst_confidence == "inferred"
                    else "unattributed"
                ),
                attribution_confidence=worst_confidence,
                cost=_cost_for_usage(usage, model_usage, plan_types=plan_types),
            )
        )
    unattributed_usage = UsageTotals()
    unattributed_model_usage: dict[str, UsageTotals] = {}
    unattributed_plan_types: set[str] = set()
    for thread in threads:
        unattributed_usage = unattributed_usage + thread.unattributed_usage
        if thread.model:
            unattributed_model_usage[thread.model] = (
                unattributed_model_usage.get(thread.model, UsageTotals())
                + thread.unattributed_usage
            )
        if thread.plan_type:
            unattributed_plan_types.add(thread.plan_type)
    if not _usage_is_zero(unattributed_usage):
        existing = next(
            (unit for unit in results if unit.work_unit_id == "unattributed"),
            None,
        )
        if existing is None:
            results.append(
                WorkUnitMetrics(
                    work_unit_id="unattributed",
                    phase_id="unattributed",
                    lane_id="unattributed",
                    activity="",
                    turn_ids=[],
                    usage=unattributed_usage,
                    allocation_method="unattributed-response-usage",
                    attribution_confidence="unattributed",
                    cost=_cost_for_usage(
                        unattributed_usage,
                        unattributed_model_usage,
                        plan_types=unattributed_plan_types,
                    ),
                )
            )
        else:
            existing.usage = existing.usage + unattributed_usage
            existing.phase_id = "unattributed"
            existing.lane_id = "unattributed"
            existing.allocation_method = "unattributed-response-usage"
            existing.attribution_confidence = "unattributed"
            existing.cost = _cost_for_usage(
                existing.usage,
                unattributed_model_usage,
                plan_types=unattributed_plan_types,
            )
    results.sort(key=lambda unit: unit.work_unit_id)
    return results


def _aggregate_phase_lanes(
    threads: list[CodexThreadMetrics],
) -> list[PhaseLaneMetrics]:
    grouped: dict[tuple[str, str], list[tuple[AgentTurn, CodexThreadMetrics]]] = {}
    for thread in threads:
        for turn in thread.turns:
            key = (turn.phase_id or "unattributed", turn.lane_id or "unattributed")
            grouped.setdefault(key, []).append((turn, thread))
    results: list[PhaseLaneMetrics] = []
    for (phase_id, lane_id), members in sorted(grouped.items()):
        usage = UsageTotals()
        model_usage: dict[str, UsageTotals] = {}
        plan_types: set[str] = set()
        intervals: list[tuple[datetime, datetime]] = []
        confidence_counts: dict[str, int] = {}
        for turn, thread in members:
            usage = usage + turn.usage
            if thread.model:
                model_usage[thread.model] = model_usage.get(thread.model, UsageTotals()) + turn.usage
            if thread.plan_type:
                plan_types.add(thread.plan_type)
            confidence_counts[turn.attribution_confidence] = (
                confidence_counts.get(turn.attribution_confidence, 0) + 1
            )
            start = _parse_iso_datetime(turn.started_at)
            end = _parse_iso_datetime(turn.completed_at)
            if start is not None and end is not None and end >= start:
                intervals.append((start, end))
        wall_start = min((start for start, _ in intervals), default=None)
        wall_end = max((end for _, end in intervals), default=None)
        wall_time_ms = (
            round((wall_end - wall_start).total_seconds() * 1000)
            if wall_start is not None and wall_end is not None
            else 0
        )
        active_time_ms = 0
        if intervals:
            merged_start, merged_end = sorted(intervals)[0]
            for start, end in sorted(intervals)[1:]:
                if start <= merged_end:
                    merged_end = max(merged_end, end)
                else:
                    active_time_ms += round((merged_end - merged_start).total_seconds() * 1000)
                    merged_start, merged_end = start, end
            active_time_ms += round((merged_end - merged_start).total_seconds() * 1000)
        results.append(
            PhaseLaneMetrics(
                phase_id=phase_id,
                lane_id=lane_id,
                work_unit_ids=sorted(
                    {turn.work_unit_id or "unattributed" for turn, _ in members}
                ),
                turn_ids=[turn.turn_id for turn, _ in members],
                wall_started_at=wall_start.isoformat() if wall_start else "",
                wall_ended_at=wall_end.isoformat() if wall_end else "",
                wall_time_ms=wall_time_ms,
                active_time_ms=active_time_ms,
                agent_time_ms=sum(turn.duration_ms for turn, _ in members),
                usage=usage,
                confidence_counts=dict(sorted(confidence_counts.items())),
                cost=_cost_for_usage(usage, model_usage, plan_types=plan_types),
            )
        )
    unattributed_usage = UsageTotals()
    unattributed_model_usage: dict[str, UsageTotals] = {}
    unattributed_plan_types: set[str] = set()
    unattributed_threads = 0
    for thread in threads:
        if _usage_is_zero(thread.unattributed_usage):
            continue
        unattributed_threads += 1
        unattributed_usage = unattributed_usage + thread.unattributed_usage
        if thread.model:
            unattributed_model_usage[thread.model] = (
                unattributed_model_usage.get(thread.model, UsageTotals())
                + thread.unattributed_usage
            )
        if thread.plan_type:
            unattributed_plan_types.add(thread.plan_type)
    if not _usage_is_zero(unattributed_usage):
        existing = next(
            (
                phase
                for phase in results
                if phase.phase_id == "unattributed" and phase.lane_id == "unattributed"
            ),
            None,
        )
        if existing is None:
            results.append(
                PhaseLaneMetrics(
                    phase_id="unattributed",
                    lane_id="unattributed",
                    work_unit_ids=["unattributed"],
                    turn_ids=[],
                    wall_started_at="",
                    wall_ended_at="",
                    wall_time_ms=0,
                    active_time_ms=0,
                    agent_time_ms=0,
                    usage=unattributed_usage,
                    confidence_counts={"unattributed": unattributed_threads},
                    cost=_cost_for_usage(
                        unattributed_usage,
                        unattributed_model_usage,
                        plan_types=unattributed_plan_types,
                    ),
                )
            )
        else:
            existing.usage = existing.usage + unattributed_usage
            existing.work_unit_ids = sorted(set(existing.work_unit_ids) | {"unattributed"})
            existing.confidence_counts["unattributed"] = (
                existing.confidence_counts.get("unattributed", 0) + unattributed_threads
            )
            existing.cost = _cost_for_usage(
                existing.usage,
                unattributed_model_usage,
                plan_types=unattributed_plan_types,
            )
    results.sort(key=lambda phase: (phase.phase_id, phase.lane_id))
    return results


def _run_cost_assessment(
    threads: list[CodexThreadMetrics],
    usage_totals: UsageTotals,
    model_usage: dict[str, UsageTotals],
    plan_types: set[str],
) -> CostAssessment:
    used_threads = [thread for thread in threads if thread.token_totals.processed_tokens > 0]
    if used_threads and all(thread.recorded_cost_usd is not None for thread in used_threads):
        total = sum(thread.recorded_cost_usd or 0.0 for thread in used_threads)
        return CostAssessment(
            status="recorded",
            total_cost=total,
            method="direct source monetary telemetry",
        )
    return _cost_for_usage(usage_totals, model_usage, plan_types=plan_types)


def _manifest_entry(thread: CodexThreadMetrics, *, sealed: bool) -> SourceManifestEntry:
    path = Path(thread.source_path)
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if sealed else ""
    return SourceManifestEntry(
        thread_id=thread.thread_id,
        path=str(path),
        size_bytes=stat.st_size,
        modified_at_ns=stat.st_mtime_ns,
        sha256=digest,
    )


def _interrupt_agent_target(tool: ToolInterval) -> str:
    """Return the explicit target path from one interrupt_agent call."""

    if tool.tool_name != "interrupt_agent":
        return ""
    try:
        arguments = json.loads(tool.argument_summary)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(arguments, dict):
        return ""
    target = arguments.get("target")
    return str(target) if isinstance(target, str) else ""


def _record_explicit_interrupt_provenance(threads: list[CodexThreadMetrics]) -> None:
    """Attach an interrupt_agent caller to the aborted turn it stopped."""

    targets = {
        thread.agent_path: thread
        for thread in threads
        if thread.agent_path
    }
    for initiator in threads:
        for tool in initiator.tool_intervals:
            target = targets.get(_interrupt_agent_target(tool))
            if target is None:
                continue
            interrupt_started = _parse_iso_datetime(tool.started_at)
            interrupt_completed = _parse_iso_datetime(tool.completed_at)
            if interrupt_started is None or interrupt_completed is None:
                continue
            candidates = []
            for turn in target.turns:
                aborted_at = _parse_iso_datetime(
                    turn.abort_event_timestamp or turn.completed_at
                )
                if (
                    turn.abort_event_timestamp
                    and aborted_at is not None
                    and interrupt_started <= aborted_at <= interrupt_completed
                ):
                    candidates.append((aborted_at, turn))
            if not candidates:
                continue
            _, turn = min(
                candidates,
                key=lambda item: abs((item[0] - interrupt_started).total_seconds()),
            )
            turn.abort_initiator_thread_id = initiator.thread_id
            turn.abort_initiator_agent_path = (
                initiator.agent_path
                or ("/root" if not initiator.parent_thread_id else initiator.thread_id)
            )
            turn.abort_initiator_turn_id = tool.turn_id or ""
            turn.abort_initiator_relationship = (
                "parent" if target.parent_thread_id == initiator.thread_id else "agent"
            )
            turn.abort_request_source_path = tool.source_path
            turn.abort_request_source_ordinal = tool.source_start_ordinal


def build_codex_rollout_run(
    root_thread_id: str,
    sessions_root: Path | list[Path],
    *,
    seal: bool = False,
    allow_aborted: bool = False,
    include_children: bool = True,
    include_delegations: bool = False,
    observed_at: datetime | None = None,
    candidate_paths: list[Path] | None = None,
    title: str = "",
    thread_titles: dict[str, str] | None = None,
    discovery_index_path: Path | None = None,
    cancelled: Callable[[], bool] | None = None,
    progress: ProgressCallback | None = None,
    worker_progress: WorkerProgressCallback | None = None,
    item_progress: ItemProgressCallback | None = None,
    workers: int = 1,
) -> CodexRunMetrics:
    """Discover, parse, reconcile, and aggregate one native Codex subtree.

    `sessions_root` bounds discovery. Sealing requires a stable candidate set
    and terminal included threads, then records source and pricing digests.
    """
    session_roots = (
        [sessions_root.resolve()]
        if isinstance(sessions_root, Path)
        else [Path(root).resolve() for root in sessions_root]
    )
    if not session_roots:
        raise ValueError("At least one Codex sessions root is required")
    candidates = (
        [path.resolve() for path in candidate_paths]
        if candidate_paths
        else sorted(
            {
                path
                for session_root in session_roots
                for path in _candidate_rollouts(session_root)
            }
        )
    )
    if not candidates:
        raise ValueError(f"No Codex rollout files found under {sessions_root}")
    if progress is not None:
        progress(
            15,
            "Indexing candidate threads",
            f"Found {len(candidates):,} rollout files in the selected stores.",
        )
    initial_files = set(candidates)
    initial_stats = {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in candidates}
    included_paths, diagnostics, discovered_parent = _discover_rollout_paths(
        root_thread_id,
        candidates,
        include_children=include_children,
        include_delegations=include_delegations,
        index_path=discovery_index_path,
    )
    if progress is not None:
        progress(
            25,
            "Resolving related threads",
            f"Selected {len(included_paths):,} thread logs for this report.",
        )
    thread_slots: list[CodexThreadMetrics | None] = [None] * len(included_paths)
    worker_count = min(max(1, workers), max(1, len(included_paths)))
    completed_count = 0
    progress_lock = threading.Lock()

    def record_parsed_item() -> None:
        nonlocal completed_count
        with progress_lock:
            completed_count += 1
            if item_progress is not None:
                item_progress(
                    completed_count,
                    len(included_paths),
                    "Parsing thread logs",
                    f"Completed {completed_count:,} of {len(included_paths):,} thread logs.",
                    None,
                )
            elif progress is not None:
                completed = 25 + round(
                    completed_count / max(1, len(included_paths)) * 40
                )
                progress(
                    completed,
                    "Parsing thread logs",
                    f"Completed {completed_count:,} of {len(included_paths):,} thread logs.",
                )

    def parse_parcel(parcel: list[tuple[int, Path]]) -> list[tuple[int, CodexThreadMetrics]]:
        worker = _current_worker_id()
        parsed_items = []
        for parcel_index, (index, path) in enumerate(parcel, start=1):
            if item_progress is not None:
                item_progress(
                    parcel_index,
                    len(parcel),
                    "Parsing thread logs",
                    path.name,
                    worker,
                )
            elif worker_progress is not None:
                worker_progress(25, "Parsing thread logs", path.name, worker)
            parsed_items.append((index, parse_codex_rollout(path, cancelled=cancelled)))
            record_parsed_item()
        return parsed_items

    if item_progress is not None:
        item_progress(
            0,
            len(included_paths),
            "Parsing thread logs",
            f"Preparing {len(included_paths):,} thread logs.",
            None,
        )
    if worker_count == 1:
        for index, parsed in parse_parcel(list(enumerate(included_paths))):
            thread_slots[index] = parsed
    else:
        indexed_paths = list(enumerate(included_paths))
        parcels = [indexed_paths[offset::worker_count] for offset in range(worker_count)]
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="agent-report-worker",
        ) as executor:
            futures = [executor.submit(parse_parcel, parcel) for parcel in parcels]
            for future in as_completed(futures):
                for index, parsed in future.result():
                    thread_slots[index] = parsed
    threads = [thread for thread in thread_slots if thread is not None]
    if progress is not None:
        progress(65, "Resolving thread titles", "Matching parsed threads to Codex task titles.")
    title_thread_ids = {thread.thread_id for thread in threads}
    if discovered_parent is not None:
        title_thread_ids.add(discovered_parent.thread_id)
    resolved_thread_titles = _local_codex_thread_titles(title_thread_ids)
    resolved_thread_titles.update(
        {
            str(thread_id).strip(): _normalized_codex_thread_title(value)
            for thread_id, value in (thread_titles or {}).items()
            if str(thread_id).strip() and _normalized_codex_thread_title(value)
        }
    )
    for thread in threads:
        if thread.thread_id in resolved_thread_titles:
            thread.task_title = resolved_thread_titles[thread.thread_id]
    _record_explicit_interrupt_provenance(threads)
    if progress is not None:
        progress(70, "Aggregating run metrics", "Combining timing, usage, context, and runtime state.")
    if seal:
        final_candidates = set(
            candidate_paths
            or {
                path
                for session_root in session_roots
                for path in _candidate_rollouts(session_root)
            }
        )
        if final_candidates != initial_files:
            raise ValueError("Cannot seal while the Codex rollout file set is changing")
        changed = [
            path
            for path in candidates
            if initial_stats[path] != (path.stat().st_size, path.stat().st_mtime_ns)
        ]
        if changed:
            raise ValueError(f"Cannot seal changing Codex rollout source: {changed[0]}")
        invalid_states = {
            thread.terminal_state
            for thread in threads
            if thread.terminal_state not in {"complete", "failed"}
            and not (allow_aborted and thread.terminal_state == "aborted")
        }
        if invalid_states:
            states = ", ".join(sorted(invalid_states))
            raise ValueError(f"Cannot seal active or indeterminate Codex run: {states}")
    usage_totals = UsageTotals()
    model_usage: dict[str, UsageTotals] = {}
    plan_types: set[str] = set()
    for thread in threads:
        usage_totals = usage_totals + thread.token_totals
        if thread.model:
            model_usage[thread.model] = model_usage.get(thread.model, UsageTotals()) + thread.token_totals
        if thread.plan_type:
            plan_types.add(thread.plan_type)
        diagnostics.extend(f"{thread.thread_id}: {item}" for item in thread.diagnostics)
    run_states = {thread.terminal_state for thread in threads}
    root_state = next(
        thread.terminal_state for thread in threads if thread.thread_id == root_thread_id
    )
    if "active" in run_states or "indeterminate" in run_states:
        state = "live"
    elif root_state == "failed":
        state = "failed"
    elif root_state == "aborted":
        state = "aborted"
    elif "failed" in run_states and "aborted" in run_states:
        state = "complete-with-failed-and-aborted-children"
    elif "failed" in run_states:
        state = "complete-with-failed-children"
    elif "aborted" in run_states:
        state = "complete-with-aborted-children"
    else:
        state = "complete"
    if seal:
        state = "sealed"
    wall_start, wall_end, wall_ms, agent_ms, active_ms, tool_ms, peak = _time_metrics(threads)
    cost = _run_cost_assessment(threads, usage_totals, model_usage, plan_types)
    pricing_version, pricing_digest = _pricing_metadata()
    observed = observed_at or datetime.now(timezone.utc)
    root_thread = next(
        thread for thread in threads if thread.thread_id == root_thread_id
    )
    all_responses = [response for thread in threads for response in thread.responses]
    runtime_intervals, runtime_states, all_agents_waiting_ms = _runtime_state_metrics(
        threads,
        root_thread_id=root_thread_id,
    )
    observed_timestamp = observed.astimezone(timezone.utc).isoformat()
    work_item_segments = _work_item_segments(
        threads,
        runtime_intervals,
        observed_at=observed_timestamp,
    )
    parent_context = None
    if discovered_parent is not None:
        parent_title = (
            resolved_thread_titles.get(discovered_parent.thread_id)
            or discovered_parent.task_title
        )
        if not parent_title:
            parent_entry = _read_codex_catalog_entry(
                discovered_parent.source_path,
                "codex",
            )
            if parent_entry is not None:
                parent_title = parent_entry.task_title
        parent_title = _catalog_task_title(parent_title) or parent_title
        parent_context = CodexParentContext(
            thread_id=discovered_parent.thread_id,
            task_title=parent_title,
            source_path=str(discovered_parent.source_path.resolve()),
        )
    run_label = _report_title(
        title or root_thread.task_title or _derived_task_title(root_thread.activities)
    )
    return CodexRunMetrics(
        run_id=root_thread_id,
        root_thread_id=root_thread_id,
        state=state,
        observed_at=observed_timestamp,
        wall_started_at=wall_start,
        wall_ended_at=wall_end,
        wall_time_ms=wall_ms,
        agent_time_ms=agent_ms,
        active_time_ms=active_ms,
        tool_time_ms=tool_ms,
        critical_path_ms=wall_ms,
        critical_path_method="inferred-observed-wall-interval",
        peak_concurrency=peak,
        usage_totals=usage_totals,
        threads=threads,
        work_units=_aggregate_work_units(threads),
        phase_lanes=_aggregate_phase_lanes(threads),
        cost=cost,
        source_manifest=[_manifest_entry(thread, sealed=seal) for thread in threads],
        diagnostics=sorted(set(diagnostics)),
        pricing_version=pricing_version,
        pricing_digest=pricing_digest if seal else "",
        run_label=run_label,
        parent_context=parent_context,
        context_summary=_context_summary(root_thread),
        inference_summary=_inference_summary(all_responses),
        inference_trends=_inference_trends(all_responses),
        inference_size_bands=_inference_size_bands(all_responses),
        context_trends=_context_trends(root_thread),
        runtime_intervals=runtime_intervals,
        runtime_states=runtime_states,
        all_agents_waiting_ms=all_agents_waiting_ms,
        work_item_segments=work_item_segments,
    )


def codex_run_to_json(run: CodexRunMetrics) -> str:
    """Serialize `run` deterministically without transcript content.

    The returned JSON ends with one newline and is suitable as a sealed source
    manifest when `run.state` is `sealed`.
    """
    return json.dumps(asdict(run), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def reprocess_sealed_codex_run(manifest_path: Path) -> CodexRunMetrics:
    """Validate `manifest_path` and reproduce its normalized metrics.

    Source, parser, or pricing digest drift raises `ValueError`; callers never
    receive silently revised historical estimates.
    """
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("format_version") != CODEX_ROLLOUT_FORMAT or data.get("state") != "sealed":
        raise ValueError(f"Not a sealed Codex rollout metrics manifest: {manifest_path}")
    sources = data.get("source_manifest")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Sealed Codex manifest has no source files")
    if data.get("parser_version") != CODEX_ROLLOUT_PARSER_VERSION:
        raise ValueError(
            "Sealed Codex parser version is unavailable: "
            f"{data.get('parser_version')}"
        )
    _, current_pricing_digest = _pricing_metadata()
    if data.get("pricing_digest") != current_pricing_digest:
        raise ValueError("Sealed Codex pricing registry digest mismatch")
    paths: list[Path] = []
    for item in sources:
        if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
            raise ValueError("Sealed Codex manifest has incomplete source provenance")
        path = Path(str(item["path"])).resolve()
        if not path.exists():
            raise ValueError(f"Sealed Codex source not found: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"Sealed Codex source digest mismatch: {path}")
        paths.append(path)
    observed_at = _parse_iso_datetime(str(data.get("observed_at") or ""))
    return build_codex_rollout_run(
        str(data["root_thread_id"]),
        paths[0].parent,
        seal=True,
        allow_aborted=any(
            isinstance(thread, dict) and thread.get("terminal_state") == "aborted"
            for thread in data.get("threads", [])
        ),
        observed_at=observed_at,
        candidate_paths=paths,
        include_delegations=True,
        title=str(data.get("run_label") or ""),
        thread_titles={
            str(thread.get("thread_id") or ""): str(thread.get("task_title") or "")
            for thread in data.get("threads", [])
            if isinstance(thread, dict)
            and thread.get("thread_id")
            and thread.get("task_title")
        },
    )


def _csv_text(rows: list[list[object]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue()


def render_codex_rollout_turn_csv(run: CodexRunMetrics) -> str:
    """Render content-free turn metrics from `run` as newline-terminated CSV."""
    rows: list[list[object]] = [[
        "thread_id", "turn_id", "started_at", "completed_at", "duration_ms",
        "time_to_first_token_ms", "outcome", "abort_reason",
        "abort_event_timestamp",
        "abort_initiator_thread_id", "abort_initiator_agent_path",
        "abort_initiator_turn_id", "abort_initiator_relationship",
        "abort_request_source_path", "abort_request_source_ordinal",
        "phase_id", "lane_id", "work_unit_id", "activity",
        "attribution_confidence", "input_tokens",
        "cached_input_tokens", "uncached_input_tokens", "output_tokens",
        "reasoning_tokens", "processed_tokens", "source_path", "source_ordinal",
    ]]
    for thread in run.threads:
        for turn in thread.turns:
            rows.append([
                thread.thread_id, turn.turn_id, turn.started_at, turn.completed_at,
                turn.duration_ms, turn.time_to_first_token_ms, turn.outcome,
                turn.abort_reason, turn.abort_event_timestamp,
                turn.abort_initiator_thread_id,
                turn.abort_initiator_agent_path, turn.abort_initiator_turn_id,
                turn.abort_initiator_relationship, turn.abort_request_source_path,
                turn.abort_request_source_ordinal,
                turn.phase_id, turn.lane_id, turn.work_unit_id, turn.activity,
                turn.attribution_confidence, turn.usage.input_tokens,
                turn.usage.cached_input_tokens, turn.usage.uncached_input_tokens,
                turn.usage.output_tokens, turn.usage.reasoning_tokens,
                turn.usage.processed_tokens, turn.source_path, turn.source_ordinal,
            ])
    return _csv_text(rows)


def render_codex_rollout_work_unit_csv(run: CodexRunMetrics) -> str:
    """Render work-unit usage and cost status from `run` as CSV."""
    rows: list[list[object]] = [[
        "work_unit_id", "phase_id", "lane_id", "activity", "turn_ids",
        "allocation_method", "attribution_confidence", "input_tokens",
        "cached_input_tokens", "uncached_input_tokens", "output_tokens",
        "reasoning_tokens", "processed_tokens", "cost_status", "estimated_usd",
    ]]
    for unit in run.work_units:
        rows.append([
            unit.work_unit_id, unit.phase_id, unit.lane_id, unit.activity,
            " ".join(unit.turn_ids), unit.allocation_method,
            unit.attribution_confidence, unit.usage.input_tokens,
            unit.usage.cached_input_tokens, unit.usage.uncached_input_tokens,
            unit.usage.output_tokens, unit.usage.reasoning_tokens,
            unit.usage.processed_tokens, unit.cost.status,
            "" if unit.cost.total_cost is None else f"{unit.cost.total_cost:.8f}",
        ])
    return _csv_text(rows)


def _format_ms(milliseconds: int) -> str:
    return _fmt_duration(milliseconds / 1000)


def _format_compact_count(value: int) -> str:
    """Format large table counts with one decimal and a stable unit suffix."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:,.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:,.1f}K"
    return f"{value:,}"


def _cost_summary(cost: CostAssessment) -> str:
    if cost.status == "estimated" and cost.total_cost is not None:
        return (
            f"API-equivalent estimate: ${cost.total_cost:.2f} USD "
            "(estimate, not an actual charge or invoice)"
        )
    if cost.status == "subscription-no-charge-data":
        return "Subscription usage; no monetary charge telemetry available"
    if cost.status == "recorded" and cost.total_cost is not None:
        return f"Recorded cost: ${cost.total_cost:.2f} USD"
    return "Cost unavailable"


def _compact_cost_summary(cost: CostAssessment) -> str:
    """Format repeated table cells without restating the report disclaimer."""
    if cost.status == "estimated" and cost.total_cost is not None:
        return f"${cost.total_cost:.2f}"
    if cost.status == "recorded" and cost.total_cost is not None:
        return f"${cost.total_cost:.2f}"
    if cost.status == "subscription-no-charge-data":
        return "subscription"
    return "—"


def _format_detail_ms(milliseconds: int | None) -> str:
    if milliseconds is None:
        return "—"
    if milliseconds < 1000:
        return f"{milliseconds}ms"
    return _format_ms(milliseconds)


def _render_abort_provenance_detail(turn: AgentTurn) -> str:
    if not (
        turn.abort_event_timestamp
        or turn.abort_reason
        or turn.abort_initiator_agent_path
    ):
        return ""
    if turn.abort_initiator_agent_path:
        relationship = turn.abort_initiator_relationship or "agent"
        initiator_name = turn.abort_initiator_agent_path.rstrip("/").rsplit("/", 1)[-1]
        value = f"{relationship.capitalize()} interrupt · {initiator_name}"
        detail = (
            f"turn {turn.abort_initiator_turn_id}"
            if turn.abort_initiator_turn_id
            else "interrupt_agent"
        )
        if turn.abort_reason:
            detail += f" · {turn.abort_reason}"
        title = f' title="{_escape_html(turn.abort_initiator_agent_path)}"'
    else:
        value = "Interrupt source not recorded"
        detail = turn.abort_reason or "No explicit interrupt_agent caller matched"
        title = ""
    return (
        f'<span class="metric-detail turn-state-detail"{title}>'
        f'{_escape_html(value)}</span>'
        f'<span class="turn-state-source">{_escape_html(detail)}</span>'
    )


def _tool_activity_summary(tools: list[ToolInterval]) -> tuple[str, str]:
    if not tools:
        return "—", "0 calls · 0s"
    counts = Counter(tool.tool_name for tool in tools)
    names = ", ".join(
        f"{name} × {count}"
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )
    call_label = "call" if len(tools) == 1 else "calls"
    duration = _format_detail_ms(sum(tool.duration_ms for tool in tools))
    return names, f"{len(tools):,} {call_label} · {duration}"


def _mcp_activity_summary(calls: list[McpCallInterval]) -> tuple[str, str]:
    """Summarize MCP server/tool usage separately from outer Codex tools."""

    if not calls:
        return "—", "0 calls · 0ms"
    counts = Counter(f"{call.server_name} → {call.tool_name}" for call in calls)
    names = ", ".join(
        f"{name} × {count}"
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )
    call_label = "call" if len(calls) == 1 else "calls"
    duration = _format_detail_ms(sum(call.duration_ms for call in calls))
    return names, f"{len(calls):,} {call_label} · {duration} recorded execution"


def _timestamp_offset_label(run: CodexRunMetrics, timestamp: str) -> str:
    run_start = _parse_iso_datetime(run.wall_started_at)
    event_time = _parse_iso_datetime(timestamp)
    if run_start is None or event_time is None:
        return "T+—"
    seconds = max(0, (event_time - run_start).total_seconds())
    return f"T+{_fmt_duration(seconds)}"


def _turn_offset_label(run: CodexRunMetrics, turn: AgentTurn) -> str:
    return _timestamp_offset_label(run, turn.started_at)


def _timeline_style(run: CodexRunMetrics, started_at: str, ended_at: str) -> str:
    run_start = _parse_iso_datetime(run.wall_started_at)
    start = _parse_iso_datetime(started_at)
    end = _parse_iso_datetime(ended_at)
    if run_start is None or start is None or end is None or run.wall_time_ms <= 0:
        return "left:0%;width:0.5%"
    total_seconds = run.wall_time_ms / 1000
    left = min(100.0, max(0.0, (start - run_start).total_seconds() / total_seconds * 100))
    width = max(0.5, (end - start).total_seconds() / total_seconds * 100)
    width = min(100.0 - left, width)
    return f"left:{left:.3f}%;width:{width:.3f}%"


def _agent_assignment(thread: CodexThreadMetrics) -> str:
    if thread.thread_name:
        return thread.thread_name
    if thread.agent_path:
        return thread.agent_path.rstrip("/").rsplit("/", 1)[-1]
    return thread.agent_nickname or "root"


def _agent_assignment_label(thread: CodexThreadMetrics) -> str:
    assignment = (
        thread.task_title
        if not thread.parent_thread_id and thread.task_title
        else thread.thread_name
    )
    if not assignment and thread.agent_path:
        assignment = thread.agent_path.rstrip("/").rsplit("/", 1)[-1]
    if not assignment:
        assignment = "—" if thread.parent_thread_id else "root"
    agent_role = thread.agent_role or ("default" if thread.parent_thread_id else "main")
    label = f"Thread: {assignment} · Agent: {agent_role}"
    if thread.agent_nickname:
        return f"{label} ({thread.agent_nickname})"
    return label


def _heatmap_agent_label(thread: CodexThreadMetrics) -> str:
    """Return a concise agent identity without embedding its assignment prompt."""

    role = thread.agent_role or ("default" if thread.parent_thread_id else "main")
    name = thread.agent_nickname
    if not name and thread.parent_thread_id:
        name = _agent_assignment(thread)
    if name and name not in {role, "root"}:
        return f"{role} ({name})"
    return role


def _compact_agent_assignment_label(
    thread: CodexThreadMetrics,
    assignment_limit: int = 72,
) -> str:
    """Bound only the assignment portion while preserving the agent identity."""

    label = _agent_assignment_label(thread)
    prefix = "Thread: "
    separator = " · Agent: "
    if not label.startswith(prefix) or separator not in label:
        return _compact_display_text(label, assignment_limit)
    assignment, agent = label[len(prefix) :].split(separator, 1)
    return (
        f"{prefix}{_compact_display_text(assignment, assignment_limit)}"
        f"{separator}{agent}"
    )


def _agent_inventory_threads(
    run: CodexRunMetrics,
) -> list[tuple[CodexThreadMetrics, int]]:
    """Return agents in parent-first order with selected-run nesting depth."""

    selected_ids = {thread.thread_id for thread in run.threads}
    children: dict[str, list[CodexThreadMetrics]] = {}
    roots: list[CodexThreadMetrics] = []
    for thread in run.threads:
        if thread.parent_thread_id in selected_ids:
            children.setdefault(thread.parent_thread_id, []).append(thread)
        else:
            roots.append(thread)

    ordered: list[tuple[CodexThreadMetrics, int]] = []
    visited: set[str] = set()

    def visit(thread: CodexThreadMetrics, depth: int) -> None:
        if thread.thread_id in visited:
            return
        visited.add(thread.thread_id)
        ordered.append((thread, depth))
        for child in children.get(thread.thread_id, []):
            visit(child, depth + 1)

    for root in roots:
        visit(root, 0)
    for thread in run.threads:
        visit(thread, 0)
    return ordered


def _native_root_thread_id(
    thread_id: str,
    threads_by_id: dict[str, CodexThreadMetrics],
) -> str:
    """Return the native rollout root that owns one included thread."""

    current_id = thread_id
    seen: set[str] = set()
    while current_id not in seen:
        seen.add(current_id)
        current = threads_by_id.get(current_id)
        if current is None or current.parent_thread_id not in threads_by_id:
            return current_id
        current_id = current.parent_thread_id
    return thread_id


def _resolve_sequence_target(
    target: str,
    source: CodexThreadMetrics,
    threads_by_id: dict[str, CodexThreadMetrics],
) -> CodexThreadMetrics | None:
    """Resolve canonical and relative collaboration targets within one report."""

    normalized = target.strip().rstrip("/")
    if not normalized:
        return None
    direct = threads_by_id.get(normalized)
    if direct is not None:
        return direct
    source_root_id = _native_root_thread_id(source.thread_id, threads_by_id)
    if normalized in {"root", "/root"}:
        return threads_by_id.get(source_root_id)
    target_name = normalized.rsplit("/", 1)[-1]
    candidates: list[CodexThreadMetrics] = []
    for thread in threads_by_id.values():
        agent_path = thread.agent_path.rstrip("/")
        names = {
            value
            for value in (
                agent_path,
                agent_path.rsplit("/", 1)[-1] if agent_path else "",
                thread.thread_name,
                _agent_assignment(thread),
            )
            if value
        }
        if normalized in names or target_name in names:
            candidates.append(thread)
    same_root = [
        thread
        for thread in candidates
        if _native_root_thread_id(thread.thread_id, threads_by_id) == source_root_id
    ]
    candidates = same_root or candidates
    if len(candidates) == 1:
        return candidates[0]
    related = [
        thread
        for thread in candidates
        if thread.parent_thread_id == source.thread_id
        or source.parent_thread_id == thread.thread_id
    ]
    return related[0] if len(related) == 1 else None


def _sequence_tool_arguments(tool: ToolInterval) -> dict[str, object]:
    """Return the first usable sanitized argument object for a tool interval."""

    for value in (tool.argument_summary, tool.argument_content):
        if not value or value == "—":
            continue
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _sequence_event_sort_key(event: AgentSequenceEvent) -> tuple[datetime, int, str]:
    timestamp = _parse_iso_datetime(event.event_timestamp)
    if timestamp is None:
        timestamp = datetime.min.replace(tzinfo=timezone.utc)
    return timestamp, event.source_ordinal, event.kind


def _sequence_thought_sort_key(
    thought: AgentSequenceThought,
) -> tuple[datetime, int, str]:
    timestamp = _parse_iso_datetime(thought.event_timestamp)
    if timestamp is None:
        timestamp = datetime.min.replace(tzinfo=timezone.utc)
    return timestamp, thought.source_ordinal, thought.thread_id


def _sequence_plain_text(value: str) -> str:
    """Remove lightweight Markdown emphasis from one displayed thought."""

    plain = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", value)
    plain = plain.replace("**", "").replace("__", "")
    return " ".join(plain.split())


def _codex_sequence_thoughts(
    run: CodexRunMetrics,
    _events: list[AgentSequenceEvent],
) -> list[AgentSequenceThought]:
    """Return privacy-safe plaintext or opaque reasoning markers in timeline order."""

    latest_by_fragment: dict[tuple[str, str, int], AgentSequenceThought] = {}
    for thread in run.threads:
        for activity in thread.activities:
            if activity.activity_type != "reasoning":
                continue
            detail = (
                _sequence_plain_text(activity.content)
                if activity.content
                else "Internal reasoning (content unavailable)"
            )
            if not detail:
                continue
            thought = AgentSequenceThought(
                event_timestamp=activity.event_timestamp,
                thread_id=thread.thread_id,
                detail=detail,
                source_ordinal=activity.source_ordinal,
            )
            deduplication_ordinal = 0 if activity.content else activity.source_ordinal
            latest_by_fragment[
                (thread.thread_id, detail.casefold(), deduplication_ordinal)
            ] = thought

    return sorted(latest_by_fragment.values(), key=_sequence_thought_sort_key)


def _codex_sequence_events(run: CodexRunMetrics) -> list[AgentSequenceEvent]:
    """Normalize recorded coordination and native child endings for the diagram."""

    threads_by_id = {thread.thread_id: thread for thread in run.threads}
    events: list[AgentSequenceEvent] = []
    for target in run.threads:
        for activity in target.activities:
            if activity.activity_type != "input" or not activity.content:
                continue
            for source_thread_id, preview, detail in _codex_delegation_values(
                activity.content
            ):
                if source_thread_id not in threads_by_id or source_thread_id == target.thread_id:
                    continue
                label = "delegate" + (f" · {preview}" if preview else "")
                events.append(
                    AgentSequenceEvent(
                        event_timestamp=activity.event_timestamp,
                        kind="delegation",
                        source_thread_id=source_thread_id,
                        target_thread_id=target.thread_id,
                        label=label,
                        detail="delegate" + (f" · {detail}" if detail else ""),
                        source_ordinal=activity.source_ordinal,
                    )
                )
    for child in run.threads:
        if child.parent_thread_id not in threads_by_id:
            continue
        events.append(
            AgentSequenceEvent(
                event_timestamp=child.started_at,
                kind="spawn",
                source_thread_id=child.parent_thread_id,
                target_thread_id=child.thread_id,
                label=f"spawn · {_agent_assignment(child)}",
            )
        )
    tool_kinds = {
        "send_message": ("message", "message"),
        "followup_task": ("followup", "follow up"),
        "interrupt_agent": ("interrupt", "interrupt"),
    }
    for source in run.threads:
        for tool in source.tool_intervals:
            kind_and_label = tool_kinds.get(tool.tool_name)
            if kind_and_label is None:
                continue
            arguments = _sequence_tool_arguments(tool)
            target_value = arguments.get("target")
            target = _resolve_sequence_target(
                str(target_value) if isinstance(target_value, str) else "",
                source,
                threads_by_id,
            )
            if target is None or target.thread_id == source.thread_id:
                continue
            kind, action = kind_and_label
            message = arguments.get("message")
            label = action
            if isinstance(message, str) and message.strip():
                label += f" · {message.strip()}"
            events.append(
                AgentSequenceEvent(
                    event_timestamp=tool.started_at,
                    kind=kind,
                    source_thread_id=source.thread_id,
                    target_thread_id=target.thread_id,
                    label=label,
                    source_ordinal=tool.source_start_ordinal,
                )
            )
    for child in run.threads:
        if child.parent_thread_id not in threads_by_id:
            continue
        for turn in child.turns:
            if turn.outcome == "active" or not turn.completed_at:
                continue
            kind = turn.outcome if turn.outcome in {"aborted", "failed"} else "complete"
            events.append(
                AgentSequenceEvent(
                    event_timestamp=turn.completed_at,
                    kind=kind,
                    source_thread_id=child.thread_id,
                    target_thread_id=child.parent_thread_id,
                    label=f"turn {turn.outcome}",
                    source_ordinal=turn.source_ordinal,
                )
            )
    return sorted(events, key=_sequence_event_sort_key)


def _usage_bounded_by(usage: UsageTotals, limit: UsageTotals) -> UsageTotals:
    """Bound one usage allocation to the counters that remain available."""

    return UsageTotals(
        input_tokens=min(usage.input_tokens, limit.input_tokens),
        cached_input_tokens=min(
            usage.cached_input_tokens, limit.cached_input_tokens
        ),
        cache_create_input_tokens=min(
            usage.cache_create_input_tokens, limit.cache_create_input_tokens
        ),
        uncached_input_tokens=min(
            usage.uncached_input_tokens, limit.uncached_input_tokens
        ),
        output_tokens=min(usage.output_tokens, limit.output_tokens),
        reasoning_tokens=min(usage.reasoning_tokens, limit.reasoning_tokens),
        processed_tokens=min(usage.processed_tokens, limit.processed_tokens),
    )


def _reports_cache_write_tokens(run: CodexRunMetrics) -> bool:
    """Return whether the runtime telemetry distinguishes cache writes."""

    return run.runtime.casefold() == "junie"


def _model_usage_by_agent(
    run: CodexRunMetrics,
) -> dict[tuple[str, str], dict[str, UsageTotals]]:
    """Return reconciled model-and-effort usage by contributing agent thread."""

    model_usage: dict[tuple[str, str], dict[str, UsageTotals]] = {}
    for thread in run.threads:
        remaining = thread.token_totals
        fallback_model = (
            thread.model
            if thread.model and not thread.model.startswith("mixed (")
            else "Unknown model"
        )
        for response in sorted(thread.responses, key=lambda item: item.source_ordinal):
            allocated = _usage_bounded_by(response.usage, remaining)
            if _usage_is_zero(allocated):
                continue
            model = response.model or fallback_model
            effort = response.effort or (
                thread.effort
                if thread.effort and not thread.effort.startswith("mixed (")
                else ""
            )
            agents = model_usage.setdefault((model, effort), {})
            agents[thread.thread_id] = (
                agents.get(thread.thread_id, UsageTotals()) + allocated
            )
            remaining = remaining.subtract(allocated)
        if not _usage_is_zero(remaining):
            fallback_effort = (
                thread.effort
                if thread.effort and not thread.effort.startswith("mixed (")
                else ""
            )
            agents = model_usage.setdefault((fallback_model, fallback_effort), {})
            agents[thread.thread_id] = (
                agents.get(thread.thread_id, UsageTotals()) + remaining
            )
    return model_usage


def _render_model_usage_section(run: CodexRunMetrics) -> str:
    """Render expandable model totals with contributing agents as children."""

    show_cache_write = _reports_cache_write_tokens(run)
    model_usage = _model_usage_by_agent(run)
    inventory = _agent_inventory_threads(run)
    threads = {thread.thread_id: thread for thread in run.threads}
    inventory_order = {
        thread.thread_id: index for index, (thread, _) in enumerate(inventory)
    }
    run_total = run.usage_totals.processed_tokens or 1
    groups: list[tuple[str, str, UsageTotals, dict[str, UsageTotals]]] = []
    for (model, effort), agents in model_usage.items():
        total = UsageTotals()
        for usage in agents.values():
            total = total + usage
        groups.append((model, effort, total, agents))
    groups.sort(
        key=lambda item: (
            -item[2].processed_tokens,
            item[0].casefold(),
            item[1].casefold(),
        )
    )

    rendered_groups = []
    for model, effort, total, agents in groups:
        agent_rows = []
        for thread_id, usage in sorted(
            agents.items(),
            key=lambda item: (
                inventory_order.get(item[0], len(inventory_order)),
                item[0],
            ),
        ):
            model_share = (
                usage.processed_tokens / total.processed_tokens * 100
                if total.processed_tokens
                else 0
            )
            thread = threads[thread_id]
            cache_write_cell = (
                f'<td>{usage.cache_create_input_tokens:,}</td>'
                if show_cache_write
                else ""
            )
            agent_rows.append(
                '<tr class="model-usage-agent-row">'
                f'<td>{_clamped_agent_title_html(thread)}</td>'
                f'<td>{usage.direct_input_tokens:,}</td>'
                f'<td>{usage.cached_input_tokens:,}</td>'
                f'{cache_write_cell}'
                f'<td>{usage.output_tokens:,}</td>'
                f'<td>{usage.reasoning_tokens:,}</td>'
                f'<td>{usage.processed_tokens:,}</td>'
                f'<td>{model_share:.1f}%</td>'
                "</tr>"
            )
        effort_html = (
            f' · <span class="model-effort">effort {_escape_html(effort)}</span>'
            if effort
            else ""
        )
        agent_label = "agent" if len(agents) == 1 else "agents"
        run_share = total.processed_tokens / run_total * 100
        rendered_groups.append(
            '<details class="model-usage-group">'
            '<summary><span class="model-usage-toggle-icon" aria-hidden="true"></span>'
            '<span class="model-usage-parent">'
            '<span class="model-identity">'
            f'<code class="model-name">{_escape_html(model)}</code>{effort_html}</span>'
            f'<span class="model-usage-total">{total.processed_tokens:,} processed tokens · '
            f'{len(agents):,} {agent_label} · {run_share:.1f}% of run</span>'
            "</span></summary>"
            '<div class="table-scroll"><table class="model-usage-table">'
            "<thead><tr><th>Agent</th><th>Fresh Input</th><th>Cache read</th>"
            f'{"<th>Cache write</th>" if show_cache_write else ""}'
            "<th>Output</th><th>Reasoning</th>"
            "<th>Processed</th><th>Model share</th></tr></thead>"
            f"<tbody>{''.join(agent_rows)}</tbody></table></div>"
            "</details>"
        )
    if not rendered_groups:
        rendered_groups.append(
            '<p class="execution-note">No model usage was recorded.</p>'
        )
    usage_note = (
        "Fresh input excludes cache reads and cache writes."
        if show_cache_write
        else (
            "Fresh input excludes cache reads. Codex telemetry does not report "
            "cache-write tokens, so that column is omitted."
        )
    )
    return (
        '<section id="model-usage">'
        '<div class="agents-heading"><h2>Usage by model</h2></div>'
        '<p class="execution-note">Each model and effort combination is a separate '
        'group. Expand a group to see the agents that contributed to its total. '
        f'{usage_note}</p>'
        f'<div class="model-usage-groups">{"".join(rendered_groups)}</div>'
        "</section>"
    )


def _inventory_text(values: list[str]) -> str:
    """Render compact agent-inventory values without implying missing evidence."""

    return " · ".join(values) if values else "—"


def _clamped_inventory_html(
    text: str,
    item_count: int,
    context_class: str,
) -> str:
    """Render long inventory text as a reusable five-line disclosure."""

    inventory_text = _escape_html(text)
    if item_count <= 5:
        return inventory_text
    return (
        f'<details class="clamped-disclosure {context_class}">'
        '<summary><span class="clamped-preview">'
        f"{inventory_text}</span>"
        '<span class="clamped-toggle clamped-more">more</span>'
        "</summary>"
        f'<div class="clamped-full">{inventory_text}'
        '<button type="button" class="clamped-toggle clamped-less">less</button>'
        "</div>"
        "</details>"
    )


def _clamped_agent_title_html(thread: CodexThreadMetrics) -> str:
    """Render a long table assignment behind the shared more/less disclosure."""

    full_label = _agent_assignment_label(thread)
    compact_label = _compact_agent_assignment_label(thread)
    if compact_label == full_label:
        return f"<strong>{_escape_html(full_label)}</strong>"
    return (
        '<details class="clamped-disclosure agent-title-disclosure">'
        '<summary><span class="clamped-preview"><strong>'
        f"{_escape_html(compact_label)}</strong></span>"
        '<span class="clamped-toggle clamped-more">more</span></summary>'
        '<div class="clamped-full"><strong>'
        f"{_escape_html(full_label)}</strong>"
        '<button type="button" class="clamped-toggle clamped-less">less</button>'
        "</div></details>"
    )


def _agent_skills_html(values: list[str]) -> str:
    """Render agent skills using the shared inventory disclosure."""

    return _clamped_inventory_html(
        _inventory_text(values),
        len(values),
        "agent-skills-disclosure",
    )


def render_codex_rollout_markdown(run: CodexRunMetrics) -> str:
    """Render a privacy-safe Markdown summary with execution detail."""
    turn_count = sum(len(thread.turns) for thread in run.threads)
    unique_turn_count = len(
        {turn.turn_id for thread in run.threads for turn in thread.turns}
    )
    response_count = sum(len(thread.responses) for thread in run.threads)
    tool_count = sum(len(thread.tool_intervals) for thread in run.threads)
    mcp_call_count = sum(len(thread.mcp_calls) for thread in run.threads)
    is_junie = run.runtime.lower() == "junie"
    show_cache_write = _reports_cache_write_tokens(run)
    turn_column_label = "Task spans" if is_junie else "Turns"
    cached_share = (
        run.usage_totals.cached_input_tokens / run.usage_totals.input_tokens * 100
        if run.usage_totals.input_tokens
        else 0
    )
    report_title = (
        run.run_label
        if run.runtime.casefold() == "codex" and run.run_label
        else AGENT_EXECUTION_METRICS_TITLE
    )
    lines = [
        f"# {report_title}",
        "",
        f"- Runtime: `{run.runtime}`",
        f"- Run: `{run.root_thread_id}`",
        f"- State: `{run.state}`",
        f"- Observed at: `{run.observed_at}`",
        f"- Threads: {len(run.threads)}",
        *(
            [
                f"- User tasks: {unique_turn_count}",
                f"- Agent task spans: {turn_count}",
                f"- Model responses: {response_count}",
            ]
            if is_junie
            else [f"- Turns: {turn_count}", f"- Model responses: {response_count}"]
        ),
        f"- Matched tool calls: {tool_count}",
        f"- MCP calls: {mcp_call_count}",
        f"- Processed tokens: {run.usage_totals.processed_tokens:,}",
        f"- Cached input share: {cached_share:.1f}%",
        f"- Wall time: {_format_ms(run.wall_time_ms)}",
        f"- Agent time: {_format_ms(run.agent_time_ms)}",
        f"- Active interval union: {_format_ms(run.active_time_ms)}",
        f"- Peak concurrency: {run.peak_concurrency}",
        f"- Cost: {_cost_summary(run.cost)}",
    ]
    if run.context_summary.capacity:
        context = run.context_summary
        lines.extend(
            [
                "",
                "## Context usage",
                "",
                f"- Current: {context.current_total_tokens:,} / {context.capacity:,} ({context.occupancy_percent:.1f}%)",
                f"- Current input: {context.current_input_tokens:,} ({context.current_cached_input_tokens:,} cached)",
                f"- Remaining: {context.remaining_tokens:,}",
                f"- Max: {context.high_water_tokens:,} ({context.high_water_percent:.1f}%)",
                f"- Compactions: {context.compaction_count:,}",
                f"- Evidence: `{context.evidence}`",
            ]
        )
    if run.inference_summary.call_count:
        inference = run.inference_summary
        lines.extend(
            [
                "",
                "## Inference rate",
                "",
                f"- Measured calls: {inference.measured_call_count:,} / {inference.call_count:,}",
                f"- End-to-end: {_format_tokens_per_second(inference.end_to_end_tokens_per_second)}",
                f"- Output span: {_format_tokens_per_second(inference.decode_tokens_per_second)}",
                f"- Median TTFT: {_format_detail_ms(round(inference.median_ttft_ms)) if inference.median_ttft_ms is not None else '—'}",
                f"- Call-rate percentiles: P50 {_format_tokens_per_second(inference.p50_call_tokens_per_second)}, P90 {_format_tokens_per_second(inference.p90_call_tokens_per_second)}",
                f"- Evidence: `{inference.evidence}`",
            ]
        )
    if run.runtime_states:
        lines.extend(
            [
                "",
                "## Runtime activity",
                "",
                f"- All agents waiting: {_format_ms(run.all_agents_waiting_ms)}",
                "",
                "| State | Agent time | Wall time | Intervals |",
                "|---|---:|---:|---:|",
            ]
        )
        for summary in run.runtime_states:
            lines.append(
                f"| {summary.state.replace('_', ' ')} | {_format_ms(summary.agent_time_ms)} | "
                f"{_format_ms(summary.run_time_ms)} | {summary.interval_count:,} |"
            )
    if run.work_item_segments:
        lines.extend(
            [
                "",
                "## Work items",
                "",
                "| Work item | Activity | Started | Ended | Duration | Outcome | Processed |",
                "|---|---|---|---|---:|---|---:|",
            ]
        )
        for segment in run.work_item_segments:
            outcome = segment.disposition
            if segment.blocker_reference:
                outcome += f" ({segment.blocker_reference})"
            lines.append(
                f"| `{segment.work_item_id}` | {segment.activity} | {segment.started_at} | "
                f"{segment.ended_at} | {_format_ms(segment.duration_ms)} | {outcome} | "
                f"{segment.usage.processed_tokens:,} |"
            )
    if run.runtime.lower() == "codex":
        lines.extend(
            [
                "",
                "## Model pricing",
                "",
                "Rates are per 1M tokens in input / cached input / output order. USD is API-equivalent. Long-context and fast-mode multipliers are not inferred from aggregate telemetry.",
                "",
                "| Provider | Model | API USD / 1M tokens | Note |",
                "|---|---|---:|---|",
            ]
        )
        for model, prices in _pricing_reference_rows():
            lines.append(
                f"| {prices.get('provider', '-')} | {prices.get('display_name', model)} | "
                f"{_rate_triplet(prices, PRICING_RATE_KEYS, '$')} | "
                f"{prices.get('pricing_note', '')} |"
            )
    if not show_cache_write:
        lines.extend(
            [
                "",
                "Codex telemetry does not report cache-write tokens, so that column is omitted.",
            ]
        )
    headers = [
        "Assignment",
        "Skills used",
        turn_column_label,
        "Tools",
        "Agent time",
        "Fresh Input",
        "Cache read",
    ]
    if show_cache_write:
        headers.append("Cache write")
    headers.extend(["Output", "Reasoning", "Processed"])
    alignments = ["---", "---", *("---:" for _ in headers[2:])]
    lines.extend(
        [
            "",
            f"| {' | '.join(headers)} |",
            f"|{'|'.join(alignments)}|",
        ]
    )
    for thread, depth in _agent_inventory_threads(run):
        agent_time_ms = sum(turn.duration_ms for turn in thread.turns)
        assignment_label = f'{"↳ " * depth}{_agent_assignment_label(thread)}'
        values = [
            assignment_label,
            _inventory_text(thread.skills_used),
            str(len(thread.turns)),
            str(len(thread.tool_intervals)),
            _format_ms(agent_time_ms),
            str(thread.token_totals.direct_input_tokens),
            str(thread.token_totals.cached_input_tokens),
        ]
        if show_cache_write:
            values.append(str(thread.token_totals.cache_create_input_tokens))
        values.extend(
            [
                str(thread.token_totals.output_tokens),
                str(thread.token_totals.reasoning_tokens),
                str(thread.token_totals.processed_tokens),
            ]
        )
        lines.append(f"| {' | '.join(values)} |")
    return "\n".join(lines) + "\n"


def _sequence_compact_text(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(1, limit - 1)].rstrip() + "…"


def _sequence_chat_lines(value: str, line_limit: int = 28) -> list[str]:
    """Return at most two bounded lines that fit inside a sequence chat bubble."""

    compact = " ".join(value.split())
    if len(compact) <= line_limit:
        return [compact]
    split_at = compact.rfind(" ", 0, line_limit + 1)
    if split_at <= 0:
        split_at = line_limit
    first = compact[:split_at].rstrip()
    remainder = compact[split_at:].lstrip()
    return [first, _sequence_compact_text(remainder, line_limit)]


def _sequence_participant_name(
    run: CodexRunMetrics,
    thread: CodexThreadMetrics,
) -> str:
    """Return a compact human-facing lifeline name without losing identity."""

    if thread.parent_thread_id:
        return _agent_assignment(thread)
    if thread.thread_id == run.root_thread_id and run.run_label:
        match = re.fullmatch(r'"(?P<title>.*)" Agent Report', run.run_label)
        return match.group("title") if match else run.run_label
    if thread.task_title:
        return thread.task_title
    for activity in thread.activities:
        if activity.activity_type != "input":
            continue
        delegations = _codex_delegation_values(activity.content)
        if not delegations:
            continue
        preview = re.sub(r"\s+\[[0-9,]+ chars\]$", "", delegations[0][1])
        if preview:
            return preview
    derived = _derived_task_title(thread.activities)
    if derived and not derived.startswith("<codex_delegation>"):
        return derived
    return f"root {thread.thread_id[:8]}"


def _sequence_context_action(event: AgentSequenceEvent) -> str:
    """Return the nearby-context arrow label supported for one event."""

    if event.kind == "spawn":
        return "spawn"
    if (
        event.kind in {"message", "followup"}
        and "[encrypted message," in event.label
    ):
        return "encrypted message"
    return ""


def _sequence_recipient_update(
    run: CodexRunMetrics,
    event: AgentSequenceEvent,
) -> AgentActivity | None:
    """Return the target's next nearby plaintext update for a context event."""

    if not _sequence_context_action(event):
        return None
    event_time = _parse_iso_datetime(event.event_timestamp)
    if event_time is None:
        return None
    target = next(
        (
            thread
            for thread in run.threads
            if thread.thread_id == event.target_thread_id
        ),
        None,
    )
    if target is None:
        return None
    candidates: list[tuple[datetime, int, AgentActivity]] = []
    for activity in target.activities:
        if activity.activity_type != "output" or not activity.content:
            continue
        activity_time = _parse_iso_datetime(activity.event_timestamp)
        if activity_time is None or activity_time < event_time:
            continue
        if activity_time - event_time > timedelta(minutes=15):
            continue
        candidates.append((activity_time, activity.source_ordinal, activity))
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item[0], item[1]))[2]


def _sequence_sender_update(
    run: CodexRunMetrics,
    event: AgentSequenceEvent,
) -> AgentActivity | None:
    """Return the source's preceding nearby plaintext update for a context event."""

    if not _sequence_context_action(event):
        return None
    event_time = _parse_iso_datetime(event.event_timestamp)
    if event_time is None:
        return None
    source = next(
        (
            thread
            for thread in run.threads
            if thread.thread_id == event.source_thread_id
        ),
        None,
    )
    if source is None:
        return None
    candidates: list[tuple[datetime, int, AgentActivity]] = []
    for activity in source.activities:
        if activity.activity_type != "output" or not activity.content:
            continue
        activity_time = _parse_iso_datetime(activity.event_timestamp)
        if activity_time is None or activity_time > event_time:
            continue
        if (
            activity_time == event_time
            and activity.source_ordinal >= event.source_ordinal
        ):
            continue
        if event_time - activity_time > timedelta(minutes=15):
            continue
        candidates.append((activity_time, activity.source_ordinal, activity))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def _sequence_visible_event_label(
    event: AgentSequenceEvent,
    recipient_update: AgentActivity | None,
) -> str:
    """Keep opaque traffic understandable without claiming ciphertext recovery."""

    if "[encrypted message," not in event.label:
        return event.label
    action = "follow up" if event.kind == "followup" else "message"
    suffix = "recipient update" if recipient_update else "encrypted"
    return f"{action} · {suffix}"


def _sequence_event_category(kind: str) -> str:
    """Map native event kinds to the five user-facing filter categories."""

    if kind in {"spawn", "message"}:
        return "message"
    if kind in {"complete", "aborted", "failed"}:
        return "complete"
    return kind


def _sequence_repeat_metadata(
    events: list[AgentSequenceEvent],
    visible_labels: list[str],
) -> list[tuple[int, int]]:
    """Return zero-based position and size for consecutive repeated messages."""

    metadata = [(0, 1) for _ in events]
    cursor = 0
    while cursor < len(events):
        event = events[cursor]
        if event.kind not in {"message", "followup"}:
            cursor += 1
            continue
        key = (
            event.kind,
            event.source_thread_id,
            event.target_thread_id,
            visible_labels[cursor],
        )
        end = cursor + 1
        while end < len(events):
            candidate = events[end]
            candidate_key = (
                candidate.kind,
                candidate.source_thread_id,
                candidate.target_thread_id,
                visible_labels[end],
            )
            if candidate_key != key:
                break
            end += 1
        count = end - cursor
        for index in range(cursor, end):
            metadata[index] = (index - cursor, count)
        cursor = end
    return metadata


def _render_codex_sequence_section(run: CodexRunMetrics) -> str:
    """Render one offline SVG sequence view plus an exact text event ledger."""

    if run.runtime.casefold() != "codex":
        return ""
    inventory = _agent_inventory_threads(run)
    participants = [thread for thread, _ in inventory]
    events = _codex_sequence_events(run)
    thoughts = _codex_sequence_thoughts(run, events)
    heading = (
        '<section id="agent-sequence" class="sequence-group-repeats" '
        'aria-labelledby="agent-sequence-title">'
        '<div class="agents-heading"><h2 id="agent-sequence-title">Agent sequence</h2>'
        '<details class="agent-info"><summary aria-label="About Agent sequence">ⓘ</summary>'
        '<div class="agent-note-popover" role="note">'
        "Rows are chronological recorded coordination events, not duration-scaled activity. "
        "Solid arrows are delegation or control messages; dashed return arrows mark native "
        "subagent turn endings. Conversation bubbles select explanatory plaintext "
        "reasoning summaries and use the same bounded, secret-redacted text as the "
        "turn details; opaque reasoning appears only as a content-unavailable marker."
        "</div></details></div>"
        '<p class="execution-note">Read downward to follow who dispatched, resumed, interrupted, '
        "or completed work. Select an agent to focus it; use the +/− control beside a parent "
        "to collapse its descendants.</p>"
    )
    if not participants or (not events and not thoughts):
        return (
            heading
            + '<div class="sequence-empty">No inter-agent coordination, child-ending events, '
            "or reasoning summaries were recorded in this report scope.</div></section>"
        )
    controls = (
        '<div class="sequence-controls" aria-label="Agent sequence view controls">'
        '<div class="sequence-control-group" role="group" aria-label="Zoom">'
        '<button type="button" data-sequence-zoom-out aria-label="Zoom out">−</button>'
        '<output data-sequence-zoom-value aria-live="polite">100%</output>'
        '<button type="button" data-sequence-zoom-in aria-label="Zoom in">+</button>'
        '<button type="button" data-sequence-fit>Fit</button></div>'
        '<div class="sequence-control-group" role="group" aria-label="Hierarchy">'
        '<button type="button" data-sequence-collapse-all>Collapse all</button>'
        '<button type="button" data-sequence-expand-all>Expand all</button></div>'
        '<button type="button" data-sequence-clear-focus disabled>Clear focus</button>'
        '<button type="button" data-sequence-group-repeats aria-pressed="true">'
        'Group repeats</button>'
        '<button type="button" data-sequence-reset>Reset view</button>'
        '<fieldset class="sequence-filter-fieldset"><legend>Events</legend>'
        '<label><input type="checkbox" data-sequence-event-filter="delegation" checked>'
        'Delegation</label>'
        '<label><input type="checkbox" data-sequence-event-filter="message" checked>'
        'Message / spawn</label>'
        '<label><input type="checkbox" data-sequence-event-filter="followup" checked>'
        'Follow-up</label>'
        '<label><input type="checkbox" data-sequence-event-filter="interrupt" checked>'
        'Interrupt</label>'
        '<label><input type="checkbox" data-sequence-event-filter="complete" checked>'
        'Turn end</label>'
        '<label><input type="checkbox" data-sequence-event-filter="thinking" checked>'
        'Thinking</label></fieldset>'
        '<output class="sequence-view-status" data-sequence-view-status '
        f'data-sequence-thinking-count="{len(thoughts)}" aria-live="polite">'
        f'{len(participants):,} {"agent" if len(participants) == 1 else "agents"} · '
        f'{len(events):,} {"event" if len(events) == 1 else "events"} · '
        f'{len(thoughts):,} {"thought" if len(thoughts) == 1 else "thoughts"}</output>'
        '</div><p class="sequence-inspect-detail" data-sequence-inspect-detail '
        'aria-live="polite">Hover or focus an agent title for its full name; '
        'select a thinking bubble for its full text.</p>'
        '<p class="sequence-filter-empty" data-sequence-empty hidden>'
        'No events or thinking summaries match the current sequence view.</p>'
    )
    participant_gap = 220
    side_padding = 110
    participant_header_height = 82
    event_height = 64
    footer_height = 30
    width = max(760, side_padding * 2 + participant_gap * (len(participants) - 1))
    event_row_indexes = {index: index for index in range(len(events))}
    event_keys = [_sequence_event_sort_key(event)[:2] for event in events]
    thought_row_indexes = {
        index: bisect_right(event_keys, _sequence_thought_sort_key(thought)[:2])
        for index, thought in enumerate(thoughts)
    }
    minimum_timestamp = datetime.min.replace(tzinfo=timezone.utc)
    timeline_rows = [
        (
            _parse_iso_datetime(event.event_timestamp) or minimum_timestamp,
            event.source_ordinal,
            1,
            index,
            "event",
        )
        for index, event in enumerate(events)
    ] + [
        (
            _parse_iso_datetime(thought.event_timestamp) or minimum_timestamp,
            thought.source_ordinal,
            0,
            index,
            "thought",
        )
        for index, thought in enumerate(thoughts)
    ]
    timeline_rows.sort()
    event_sequence_orders = {
        item_index: order
        for order, (*_, item_index, item_kind) in enumerate(timeline_rows)
        if item_kind == "event"
    }
    thought_sequence_orders = {
        item_index: order
        for order, (*_, item_index, item_kind) in enumerate(timeline_rows)
        if item_kind == "thought"
    }
    height = event_height * len(timeline_rows) + footer_height
    x_by_thread_id = {
        thread.thread_id: side_padding + index * participant_gap
        for index, thread in enumerate(participants)
    }
    name_by_thread_id = {
        thread.thread_id: _sequence_participant_name(run, thread)
        for thread in participants
    }
    parent_ids_with_children = {
        thread.parent_thread_id
        for thread in participants
        if thread.parent_thread_id in x_by_thread_id
    }
    marker_colors = {
        "delegation": ("teal", "#00695c"),
        "spawn": ("blue", "#2563a6"),
        "message": ("blue", "#2563a6"),
        "followup": ("purple", "#6d4c8e"),
        "interrupt": ("red", "#b3261e"),
        "complete": ("green", "#24733b"),
        "aborted": ("red", "#b3261e"),
        "failed": ("red", "#b3261e"),
    }
    marker_defs = "".join(
        '<marker id="sequence-arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"></path></marker>'.format(
            name=name,
            color=color,
        )
        for name, color in {
            marker_name: marker_color
            for marker_name, marker_color in marker_colors.values()
        }.items()
    )
    participant_svg = []
    for thread, depth in inventory:
        x = x_by_thread_id[thread.thread_id]
        full_name = name_by_thread_id[thread.thread_id]
        visible_name = _sequence_compact_text(full_name, 24)
        agent_role = thread.agent_role or ("default" if thread.parent_thread_id else "main")
        identity = thread.thread_id
        if len(identity) > 15:
            identity = f"{identity[:8]}…{identity[-4:]}"
        detail = f"{agent_role} · {identity}"
        if thread.agent_nickname:
            detail = f"{thread.agent_nickname} · {detail}"
        hierarchy_toggle = ""
        if thread.thread_id in parent_ids_with_children:
            hierarchy_toggle = (
                '<g class="sequence-hierarchy-toggle" role="button" tabindex="0" '
                'aria-label="Collapse descendants of {name}" aria-expanded="true">'
                '<circle cx="100" cy="37" r="9"></circle>'
                '<text x="100" y="41" text-anchor="middle">−</text></g>'
            ).format(name=_escape_html(full_name))
        participant_svg.append(
            '<g class="sequence-participant" data-depth="{depth}" '
            'data-thread-id="{thread_id}" data-parent-thread-id="{parent_id}" '
            'data-participant-name="{full_name}" data-sequence-x="{x}" '
            'transform="translate({x} 0)">'
            '<g class="sequence-focus-target" role="button" tabindex="0" '
            'aria-pressed="false" aria-label="Focus on {aria}">'
            '<rect x="-88" y="10" width="176" height="54" rx="5"></rect>'
            '<text x="0" y="32" text-anchor="middle">'
            '<tspan class="sequence-participant-name" x="0">{name}</tspan>'
            '<tspan class="sequence-participant-detail" x="0" dy="18">{detail}</tspan>'
            "</text></g>{hierarchy_toggle}</g>".format(
                depth=depth,
                thread_id=_escape_html(thread.thread_id),
                parent_id=_escape_html(thread.parent_thread_id),
                full_name=_escape_html(full_name),
                x=x,
                aria=_escape_html(f"{full_name} · {detail}"),
                name=_escape_html(visible_name),
                detail=_escape_html(_sequence_compact_text(detail, 28)),
                hierarchy_toggle=hierarchy_toggle,
            )
        )
    lifeline_svg = "".join(
        '<line class="sequence-lifeline" data-thread-id="{thread_id}" '
        'x1="{x}" y1="0" x2="{x}" '
        'y2="{end_y}"></line>'.format(
            thread_id=_escape_html(thread.thread_id),
            x=x_by_thread_id[thread.thread_id],
            end_y=height - 16,
        )
        for thread in participants
    )
    event_svg = []
    thought_svg = []
    ledger_rows = []
    event_overlays = []
    thought_overlays = []
    return_kinds = {"complete", "aborted", "failed"}
    event_contexts = []
    for event in events:
        sender_update = _sequence_sender_update(run, event)
        recipient_update = _sequence_recipient_update(run, event)
        display_label = _sequence_visible_event_label(event, recipient_update)
        event_contexts.append((sender_update, recipient_update, display_label))
    repeat_metadata = _sequence_repeat_metadata(
        events,
        [display_label for _, _, display_label in event_contexts],
    )
    for index, (event, context, repetition) in enumerate(
        zip(events, event_contexts, repeat_metadata, strict=True)
    ):
        row_index = event_row_indexes[index]
        sequence_order = event_sequence_orders[index]
        y = sequence_order * event_height + 34
        source_x = x_by_thread_id[event.source_thread_id]
        target_x = x_by_thread_id[event.target_thread_id]
        marker_name, color = marker_colors[event.kind]
        line_length = abs(target_x - source_x)
        label_limit = max(14, min(48, line_length // 7))
        sender_update, recipient_update, display_label = context
        repeat_index, repeat_count = repetition
        visible_label = _sequence_compact_text(display_label, label_limit)
        source_name = name_by_thread_id[event.source_thread_id]
        target_name = name_by_thread_id[event.target_thread_id]
        offset = _timestamp_offset_label(run, event.event_timestamp)
        event_description = (
            f"{offset}: {source_name} to {target_name} · {event.label}"
        )
        detail_id = f"sequence-event-{index + 1}"
        category = _sequence_event_category(event.kind)
        repeat_count_html = (
            f'<tspan class="sequence-repeat-count" dx="4">×{repeat_count}</tspan>'
            if repeat_count > 1
            else ""
        )
        repeat_aria = (
            f" · {repeat_count} consecutive repeated events grouped"
            if repeat_count > 1 and repeat_index == 0
            else ""
        )
        dash = ' stroke-dasharray="6 4"' if event.kind in return_kinds else ""
        event_svg.append(
            '<a class="sequence-event-link" href="#{detail_id}" tabindex="0" '
            'role="listitem" aria-label="{aria}" data-event-index="{event_index}" '
            'data-source-thread-id="{source_id}" data-target-thread-id="{target_id}" '
            'data-event-category="{category}" data-row-index="{row_index}" '
            'data-sequence-order="{sequence_order}" data-base-y="{y}" '
            'data-repeat-count="{repeat_count}" data-repeat-index="{repeat_index}">'
            '<g class="sequence-event sequence-event-{kind}">'
            '<rect class="sequence-event-band" x="0" y="{band_y}" width="{width}" height="44"></rect>'
            '<text class="sequence-offset" x="12" y="{text_y}">{offset}</text>'
            '<line class="sequence-line" x1="{source_x}" y1="{y}" x2="{target_x}" y2="{y}" '
            'stroke="{color}" marker-end="url(#sequence-arrow-{marker})"{dash}></line>'
            '<circle class="sequence-source-dot" cx="{source_x}" cy="{y}" r="3" fill="{color}"></circle>'
            '<line class="sequence-event-hit" x1="{source_x}" y1="{y}" '
            'x2="{target_x}" y2="{y}"></line>'
            '<text class="sequence-event-label" x="{label_x}" y="{label_y}" '
            'text-anchor="middle">{label}{repeat_count_html}</text>'
            "</g></a>".format(
                detail_id=detail_id,
                kind=event.kind,
                aria=_escape_html(event_description + repeat_aria),
                event_index=index,
                source_id=_escape_html(event.source_thread_id),
                target_id=_escape_html(event.target_thread_id),
                category=category,
                row_index=row_index,
                sequence_order=sequence_order,
                repeat_count=repeat_count,
                repeat_index=repeat_index,
                band_y=y - 20,
                width=width,
                text_y=y + 4,
                offset=_escape_html(offset),
                source_x=source_x,
                target_x=target_x,
                y=y,
                color=color,
                marker=marker_name,
                dash=dash,
                label_x=(source_x + target_x) / 2,
                label_y=y - 8,
                label=_escape_html(visible_label),
                repeat_count_html=repeat_count_html,
            )
        )
        ledger_repeat_count = (
            '<span class="sequence-ledger-repeat-count"> · ×{count} grouped</span>'.format(
                count=repeat_count
            )
            if repeat_count > 1
            else ""
        )
        ledger_rows.append(
            '<li data-event-index="{event_index}" data-source-thread-id="{source_id}" '
            'data-target-thread-id="{target_id}" data-event-category="{category}" '
            'data-repeat-count="{repeat_count}" data-repeat-index="{repeat_index}">'
            '<a class="sequence-ledger-link" href="#{detail_id}">'
            '<time>{offset}</time><strong>{source}</strong><span aria-hidden="true">→</span>'
            '<strong>{target}</strong><span>{label}</span>{repeat_count_html}</a></li>'.format(
                detail_id=detail_id,
                event_index=index,
                source_id=_escape_html(event.source_thread_id),
                target_id=_escape_html(event.target_thread_id),
                category=category,
                repeat_count=repeat_count,
                repeat_index=repeat_index,
                offset=_escape_html(offset),
                source=_escape_html(source_name),
                target=_escape_html(target_name),
                label=_escape_html(event.label),
                repeat_count_html=ledger_repeat_count,
            )
        )
        opaque_message_note = (
            '<p class="execution-note">The original message is encrypted in the '
            'offline rollout, so its plaintext is unavailable to this report.</p>'
            if "[encrypted message," in event.label
            else ""
        )
        sender_update_html = ""
        if sender_update is not None:
            sender_offset = _timestamp_offset_label(
                run,
                sender_update.event_timestamp,
            )
            if event.kind == "spawn":
                sender_update_html = (
                    "<h3>Parent's preceding recorded update</h3>"
                    '<p class="execution-note">This parent update was recorded at '
                    f"{_escape_html(sender_offset)} before the spawn.</p>"
                )
            else:
                sender_update_html = (
                    "<h3>Sender's preceding recorded update</h3>"
                    '<p class="execution-note">Sender updates are context, not recovered '
                    'message plaintext. This update was recorded at '
                    f"{_escape_html(sender_offset)}.</p>"
                )
            sender_update_html += (
                '<pre class="sequence-sender-update" tabindex="0">'
                f"{_escape_html(sender_update.content)}</pre>"
            )
        context_arrow_html = ""
        if sender_update is not None and recipient_update is not None:
            context_action = _sequence_context_action(event)
            context_action_name = (
                "Spawn" if context_action == "spawn" else "Encrypted message"
            )
            context_arrow_html = (
                '<div class="sequence-context-arrow" role="img" '
                'aria-label="{action_name} from {source} to {target}">'
                '<span class="sequence-context-party">{source}</span>'
                '<span class="sequence-context-direction" aria-hidden="true">'
                '<span class="sequence-context-line"></span>'
                '<span class="sequence-context-message">{action}</span>'
                '<span class="sequence-context-arrowhead">→</span></span>'
                '<span class="sequence-context-party sequence-context-target">{target}</span>'
                "</div>"
            ).format(
                action_name=context_action_name,
                action=_escape_html(context_action),
                source=_escape_html(source_name),
                target=_escape_html(target_name),
            )
        recipient_update_html = ""
        if recipient_update is not None:
            update_offset = _timestamp_offset_label(
                run,
                recipient_update.event_timestamp,
            )
            if event.kind == "spawn":
                recipient_update_html = (
                    "<h3>Spawned agent's next recorded update</h3>"
                    '<p class="execution-note">This spawned-agent update was recorded at '
                    f"{_escape_html(update_offset)} after the spawn.</p>"
                )
            else:
                recipient_update_html = (
                    "<h3>Recipient's next recorded update</h3>"
                    '<p class="execution-note">Recipient updates are context, not recovered '
                    'message plaintext. This update was recorded at '
                    f"{_escape_html(update_offset)}.</p>"
                )
            recipient_update_html += (
                '<pre class="sequence-recipient-update" tabindex="0">'
                f"{_escape_html(recipient_update.content)}</pre>"
            )
        event_overlays.append(
            '<section id="{detail_id}" class="tool-call-overlay sequence-event-overlay" '
            'role="dialog" aria-modal="true" aria-labelledby="{detail_id}-title">'
            '<div class="tool-call-panel sequence-event-panel">'
            '<div class="tool-call-header"><h2 id="{detail_id}-title">Sequence event</h2>'
            '<a class="tool-call-close" href="#agent-sequence">Close</a></div>'
            '<div class="metrics sequence-event-metrics">'
            '<div class="metric"><div class="label">Offset</div><div class="value">{offset}</div></div>'
            '<div class="metric"><div class="label">Type</div><div class="value">{kind}</div></div>'
            '<div class="metric"><div class="label">From</div><div class="value">{source}</div></div>'
            '<div class="metric"><div class="label">To</div><div class="value">{target}</div></div>'
            '</div><h3>Recorded event</h3>'
            '<pre class="sequence-event-full" tabindex="0">{detail}</pre>'
            '{opaque_note}{sender_update}{context_arrow}{recipient_update}'
            '</div></section>'.format(
                detail_id=detail_id,
                offset=_escape_html(offset),
                kind=_escape_html(event.kind),
                source=_escape_html(source_name),
                target=_escape_html(target_name),
                detail=_escape_html(event.detail or event.label),
                opaque_note=opaque_message_note,
                sender_update=sender_update_html,
                context_arrow=context_arrow_html,
                recipient_update=recipient_update_html,
            )
        )
    for index, thought in enumerate(thoughts):
        row_index = thought_row_indexes[index]
        sequence_order = thought_sequence_orders[index]
        y = sequence_order * event_height + 34
        x = x_by_thread_id[thought.thread_id]
        offset = _timestamp_offset_label(run, thought.event_timestamp)
        participant_name = name_by_thread_id[thought.thread_id]
        full_detail = _sequence_compact_text(thought.detail, 1_200)
        visible_lines = _sequence_chat_lines(thought.detail)
        line_ys = [4] if len(visible_lines) == 1 else [-3, 11]
        visible_text = "".join(
            '<tspan class="sequence-thinking-line" x="{x}" y="{y}">{line}</tspan>'.format(
                x=0,
                y=line_y,
                line=_escape_html(line),
            )
            for line, line_y in zip(visible_lines, line_ys, strict=True)
        )
        detail_id = f"sequence-thought-{index + 1}"
        thought_svg.append(
            '<a class="sequence-conversation-link" href="#{detail_id}" tabindex="0" '
            'role="listitem" aria-label="{aria}">'
            '<g class="sequence-conversation-bubble" '
            'data-thought-index="{thought_index}" data-thread-id="{thread_id}" '
            'data-row-index="{row_index}" data-sequence-order="{sequence_order}" '
            'data-base-y="{y}" '
            'transform="translate({x} {y})">'
            '<text class="sequence-thinking-offset" x="0" y="-25" '
            'text-anchor="middle">{offset}</text>'
            '<rect x="-98" y="-18" width="196" height="40" rx="10"></rect>'
            '<path class="sequence-conversation-tail" d="M -8 22 L 0 30 L 8 22 Z"></path>'
            '<text class="sequence-thinking-text" x="{text_x}" '
            'text-anchor="middle">{visible_text}</text></g></a>'.format(
                detail_id=detail_id,
                thought_index=index,
                thread_id=_escape_html(thought.thread_id),
                row_index=row_index,
                sequence_order=sequence_order,
                y=y,
                x=x,
                aria=_escape_html(
                    f"{offset}: {participant_name} thinking: {full_detail}"
                ),
                offset=_escape_html(offset),
                text_x=0,
                visible_text=visible_text,
            )
        )
        thought_overlays.append(
            '<section id="{detail_id}" class="tool-call-overlay sequence-thought-overlay" '
            'role="dialog" aria-modal="true" aria-labelledby="{detail_id}-title">'
            '<div class="tool-call-panel sequence-event-panel">'
            '<div class="tool-call-header"><h2 id="{detail_id}-title">Thinking</h2>'
            '<a class="tool-call-close" href="#agent-sequence">Close</a></div>'
            '<div class="metrics sequence-thought-metrics">'
            '<div class="metric"><div class="label">Offset</div>'
            '<div class="value">{offset}</div></div>'
            '<div class="metric"><div class="label">Agent</div>'
            '<div class="value">{participant}</div></div></div>'
            '<pre class="sequence-thought-full">{detail}</pre>'
            '</div></section>'.format(
                detail_id=detail_id,
                offset=_escape_html(offset),
                participant=_escape_html(participant_name),
                detail=_escape_html(full_detail),
            )
        )
    legend = (
        '<div class="sequence-legend" aria-label="Sequence event legend">'
        '<span><i class="legend-line legend-delegation"></i>delegation</span>'
        '<span><i class="legend-line legend-message"></i>message / spawn</span>'
        '<span><i class="legend-line legend-followup"></i>follow-up</span>'
        '<span><i class="legend-line legend-interrupt"></i>interrupt</span>'
        '<span><i class="legend-line legend-complete"></i>turn end</span>'
        '<span><i class="legend-conversation-bubble"></i>thinking</span>'
        "</div>"
    )
    diagram = (
        '<div class="sequence-scroll" tabindex="0" aria-label="Scrollable agent sequence diagram">'
        f'<div class="sequence-canvas" style="width:{width}px" '
        f'data-participant-gap="{participant_gap}" data-side-padding="{side_padding}" '
        f'data-header-height="{participant_header_height}" data-event-height="{event_height}" '
        f'data-footer-height="{footer_height}">'
        '<div class="sequence-sticky-header">'
        f'{legend}<svg class="sequence-participant-header" role="img" '
        f'aria-label="{len(participants)} agent lifelines" viewBox="0 0 {width} '
        f'{participant_header_height}" width="{width}" height="{participant_header_height}">'
        f"{''.join(participant_svg)}</svg></div>"
        '<svg class="agent-sequence-diagram" role="list" '
        'aria-labelledby="agent-sequence-title agent-sequence-description" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        f'<desc id="agent-sequence-description" data-sequence-description>'
        f'{len(events)} recorded events and {len(thoughts)} thinking summaries across '
        f"{len(participants)} agent lifelines.</desc>"
        f"<defs>{marker_defs}</defs>{lifeline_svg}{''.join(thought_svg)}"
        f"{''.join(event_svg)}</svg></div></div>"
    )
    ledger = (
        '<details class="sequence-ledger"><summary data-sequence-ledger-summary>'
        'Event ledger · '
        f"{len(events):,} recorded events</summary><ol>{''.join(ledger_rows)}</ol></details>"
    )
    return (
        heading
        + controls
        + diagram
        + ledger
        + "".join(event_overlays)
        + "".join(thought_overlays)
        + "</section>"
    )


def _local_time_html(timestamp: str) -> str:
    """Render an ISO fallback that the offline report localizes in-place."""

    normalized = _normalize_timestamp(timestamp)
    return (
        f'<time class="local-timestamp" datetime="{_escape_html_attribute(normalized)}">'
        f"{_escape_html(normalized or '—')}</time>"
    )


def _format_tokens_per_second(value: float | None) -> str:
    """Render one inference rate without implying unavailable precision."""

    return f"{value:.2f} tok/s" if value is not None else "—"


def _render_trend_table_chart(
    view_id: str,
    label: str,
    table_html: str,
    chart_payload: dict[str, object],
) -> str:
    """Render an accessible table/chart switch backed by offline chart data."""

    payload = json.dumps(
        chart_payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    safe_id = _escape_html_attribute(view_id)
    safe_label = _escape_html_attribute(label)
    return (
        f'<div class="trend-view" data-trend-view data-view-id="{safe_id}">'
        f'<div class="trend-view-switch" role="group" aria-label="{safe_label} view">'
        f'<button type="button" data-trend-mode="table" aria-controls="{safe_id}-table" '
        'aria-pressed="true">Table</button>'
        f'<button type="button" data-trend-mode="chart" aria-controls="{safe_id}-chart" '
        'aria-pressed="false">Chart</button></div>'
        f'<div id="{safe_id}-table" data-trend-panel="table">{table_html}</div>'
        f'<div id="{safe_id}-chart" class="trend-chart-panel" data-trend-panel="chart" hidden>'
        f'<svg class="trend-chart" data-trend-chart role="img" aria-label="{safe_label} chart" '
        'viewBox="0 0 1000 360" preserveAspectRatio="xMidYMid meet"></svg>'
        '<div class="trend-chart-legend" data-trend-legend></div>'
        '<p class="trend-chart-empty" data-trend-empty hidden></p></div>'
        f'<script type="application/json" data-trend-data>{payload}</script></div>'
    )


def _render_context_metrics(run: CodexRunMetrics) -> str:
    """Render current and maximum context measurements compactly."""

    summary = run.context_summary
    if summary.capacity <= 0 or summary.occupancy_percent is None:
        return ""
    rows = []
    for thread in run.threads:
        if not thread.context_snapshots:
            continue
        current = thread.context_snapshots[-1]
        high_water = max(
            thread.context_snapshots,
            key=lambda snapshot: snapshot.total_tokens,
        )
        rows.append(
            "<tr>"
            f"<td>{_clamped_agent_title_html(thread)}</td>"
            f"<td>{current.total_tokens:,} / {current.capacity:,} ({current.occupancy_percent:.1f}%)</td>"
            f"<td>{current.remaining_tokens:,}</td>"
            f"<td>{high_water.total_tokens:,} ({high_water.occupancy_percent:.1f}%)</td>"
            f"<td>{len(thread.compactions):,}</td>"
            f"<td>{_local_time_html(current.event_timestamp)}</td>"
            "</tr>"
        )
    trend_rows = "".join(
        "<tr>"
        f"<td>{_local_time_html(bucket.started_at)}</td>"
        f"<td>{bucket.first_total_tokens:,}</td>"
        f"<td>{bucket.last_total_tokens:,}</td>"
        f"<td>{bucket.high_total_tokens:,}</td>"
        f"<td>{f'{bucket.high_total_tokens / bucket.capacity * 100:.1f}%' if bucket.capacity > 0 else '—'}</td>"
        f"<td>{bucket.compaction_count:,}</td></tr>"
        for bucket in run.context_trends
    )
    root_thread = next(
        thread for thread in run.threads if thread.thread_id == run.root_thread_id
    )
    compaction_rows = "".join(
        "<tr>"
        f"<td>{_local_time_html(compaction.event_timestamp)}</td>"
        f"<td>{compaction.before_total_tokens:,}</td>"
        f"<td>{compaction.after_total_tokens:,}</td>"
        f"<td>{_escape_html('direct' if compaction.recorded else 'inferred')}</td></tr>"
        for compaction in root_thread.compactions
    )
    compaction_table = (
        '<div class="table-scroll compact-table"><table><thead><tr>'
        '<th>Compacted</th><th>Before</th><th>After</th><th>Evidence</th>'
        f"</tr></thead><tbody>{compaction_rows}</tbody></table></div>"
        if compaction_rows
        else ""
    )
    growth_table = (
        '<div class="table-scroll"><table><thead><tr><th>Local time</th><th>First</th>'
        '<th>Last</th><th>Max</th><th>Context window</th><th>Compactions</th></tr></thead>'
        f"<tbody>{trend_rows}</tbody></table></div>{compaction_table}"
    )
    context_points = [
        {
            "timestamp": _normalize_timestamp(bucket.started_at),
            "last": bucket.last_total_tokens,
            "high": bucket.high_total_tokens,
            "capacity": bucket.capacity,
        }
        for bucket in run.context_trends
    ]
    context_chart = _render_trend_table_chart(
        "context-growth-view",
        "Context evolution",
        growth_table,
        {
            "title": "Context evolution",
            "description": "Context tokens over local time with compaction events marked in orange.",
            "axis_label": "Context tokens",
            "value_format": "tokens",
            "series": [
                {
                    "label": "Context used",
                    "color": "#2563a6",
                    "values": [
                        {"timestamp": point["timestamp"], "value": point["last"]}
                        for point in context_points
                    ],
                },
                {
                    "label": "Bucket high",
                    "color": "#78909c",
                    "dash": "5 5",
                    "values": [
                        {"timestamp": point["timestamp"], "value": point["high"]}
                        for point in context_points
                    ],
                },
                {
                    "label": "Context window",
                    "color": "#455a64",
                    "dash": "10 6",
                    "values": [
                        {"timestamp": point["timestamp"], "value": point["capacity"]}
                        for point in context_points
                    ],
                },
            ],
            "markers": [
                {
                    "timestamp": _normalize_timestamp(compaction.event_timestamp),
                    "label": "Compaction",
                    "before": compaction.before_total_tokens,
                    "after": compaction.after_total_tokens,
                }
                for compaction in root_thread.compactions
            ],
            "empty_message": "No context-growth measurements are available.",
        },
    )
    return (
        '<section id="context-usage" class="metric-view">'
        '<div class="agents-heading"><h2>Context usage</h2></div>'
        '<div class="metrics compact-metrics">'
        '<div class="metric"><div class="label">Average</div>'
        f'<div class="value">{summary.average_total_tokens:,}</div>'
        f'<span class="metric-detail">{summary.average_percent:.1f}%</span></div>'
        '<div class="metric"><div class="label">Max</div>'
        f'<div class="value">{summary.high_water_tokens:,}</div>'
        f'<span class="metric-detail">{summary.high_water_percent:.1f}%</span></div>'
        '<div class="metric"><div class="label">Compactions</div>'
        f'<div class="value">{summary.compaction_count:,}</div></div></div>'
        '<details class="metric-details"><summary>Per-agent context</summary>'
        '<div class="table-scroll"><table><thead><tr><th>Agent</th><th>Current</th>'
        '<th>Remaining tokens</th><th>Max</th><th>Compactions</th><th>Updated</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div></details>"
        '<details class="metric-details"><summary>Context evolution</summary>'
        f"{context_chart}"
        "</details></section>"
    )


def _render_inference_metrics(run: CodexRunMetrics) -> str:
    """Render call timing and size-aware rate trends without claiming decoder telemetry."""

    summary = run.inference_summary
    if summary.call_count == 0:
        return ""
    trend_rows = "".join(
        "<tr>"
        f"<td>{_local_time_html(bucket.started_at)}</td>"
        f"<td>{bucket.call_count:,}</td>"
        f"<td>{bucket.output_tokens:,}</td>"
        f"<td>{_format_ms(bucket.inference_time_ms)}</td>"
        f"<td>{_escape_html(_format_tokens_per_second(bucket.tokens_per_second))}</td>"
        "</tr>"
        for bucket in run.inference_trends
    )
    median_ttft = (
        _format_detail_ms(round(summary.median_ttft_ms))
        if summary.median_ttft_ms is not None
        else "—"
    )
    percentile_text = (
        f"P50 {_format_tokens_per_second(summary.p50_call_tokens_per_second)} · "
        f"P90 {_format_tokens_per_second(summary.p90_call_tokens_per_second)}"
    )
    size_rows = "".join(
        "<tr>"
        f"<td>{_escape_html(band.label)}</td>"
        f"<td>{band.call_count:,}</td>"
        f"<td>{band.output_tokens:,}</td>"
        f"<td>{_escape_html(_format_tokens_per_second(band.weighted_tokens_per_second))}</td>"
        f"<td>{_escape_html(_format_tokens_per_second(band.median_call_tokens_per_second))}</td></tr>"
        for band in run.inference_size_bands
    )
    inference_table = (
        '<div class="table-scroll"><table><thead><tr><th>Local time</th><th>Calls</th>'
        '<th>Output</th><th>Inference</th><th>Rate</th></tr></thead>'
        f"<tbody>{trend_rows}</tbody></table></div>"
    )
    inference_chart = _render_trend_table_chart(
        "inference-trend-view",
        "Inference rate over time",
        inference_table,
        {
            "title": "Inference rate over time",
            "description": "Measured output-token inference rate by 15-minute period in local time.",
            "axis_label": "Tokens per second",
            "value_format": "rate",
            "series": [
                {
                    "label": "Inference rate",
                    "color": "#2563a6",
                    "values": [
                        {
                            "timestamp": _normalize_timestamp(bucket.started_at),
                            "value": bucket.tokens_per_second,
                        }
                        for bucket in run.inference_trends
                    ],
                }
            ],
            "markers": [],
            "empty_message": "No measured inference-rate data are available.",
        },
    )
    return (
        '<section id="inference-rate" class="metric-view">'
        '<div class="agents-heading"><h2>Inference rate</h2></div>'
        '<div class="metrics compact-metrics">'
        '<div class="metric"><div class="label">End to end</div>'
        f'<div class="value">{_escape_html(_format_tokens_per_second(summary.end_to_end_tokens_per_second))}</div></div>'
        '<div class="metric"><div class="label">Output span</div>'
        f'<div class="value">{_escape_html(_format_tokens_per_second(summary.decode_tokens_per_second))}</div></div>'
        '<div class="metric"><div class="label">Median TTFT</div>'
        f'<div class="value">{_escape_html(median_ttft)}</div></div>'
        '<div class="metric"><div class="label">Measured calls</div>'
        f'<div class="value">{summary.measured_call_count:,} / {summary.call_count:,}</div></div></div>'
        f'<details class="metric-details"><summary>15-minute trend · {_escape_html(percentile_text)}</summary>'
        f"{inference_chart}</details>"
        '<details class="metric-details"><summary>Response-size bands</summary>'
        '<div class="table-scroll"><table><thead><tr><th>Output tokens</th><th>Calls</th>'
        '<th>Output</th><th>Weighted rate</th><th>Median call rate</th></tr></thead>'
        f"<tbody>{size_rows}</tbody></table></div></details></section>"
    )


def _render_runtime_metrics(run: CodexRunMetrics) -> str:
    """Render state durations while keeping summed agent time separate from wall time."""

    if not run.runtime_states:
        return ""
    labels = {
        "model_inference": "Model inference",
        "tool_execution": "Tool execution",
        "test_process": "Build / Test",
        "agent_wait": "Waiting for agent",
        "user_pause": "User pause",
        "watchdog": "Watchdog",
        "approval_infrastructure": "Approval / infrastructure",
        "unattributed": "Unattributed",
    }
    preferred = list(labels)
    by_state = {summary.state: summary for summary in run.runtime_states}
    rows = []
    for state in preferred + sorted(set(by_state) - set(preferred)):
        summary = by_state.get(state)
        if summary is None:
            continue
        evidence = (
            "direct"
            if summary.inferred_interval_count == 0
            else "mixed"
            if summary.direct_interval_count
            else "inferred"
        )
        rows.append(
            "<tr>"
            f"<td>{_escape_html(labels.get(state, state.replace('_', ' ').title()))}</td>"
            f"<td>{_format_ms(summary.agent_time_ms)}</td>"
            f"<td>{_format_ms(summary.run_time_ms)}</td>"
            f"<td>{summary.interval_count:,}</td>"
            f"<td>{_escape_html(evidence)}</td></tr>"
        )
    return (
        '<section id="runtime-activity" class="metric-view">'
        '<div class="agents-heading"><h2>Runtime activity</h2></div>'
        '<div class="metrics compact-metrics">'
        '<div class="metric"><div class="label">All agents waiting</div>'
        f'<div class="value">{_format_ms(run.all_agents_waiting_ms)}</div></div>'
        '<div class="metric"><div class="label">Inference</div>'
        f'<div class="value">{_format_ms(by_state.get("model_inference", RuntimeStateSummary("", 0, 0, 0, 0, 0)).run_time_ms)}</div></div>'
        '<div class="metric"><div class="label">Build / Test</div>'
        f'<div class="value">{_format_ms(by_state.get("test_process", RuntimeStateSummary("", 0, 0, 0, 0, 0)).run_time_ms)}</div></div></div>'
        '<details class="metric-details"><summary>State breakdown</summary>'
        '<div class="table-scroll"><table><thead><tr><th>State</th><th>Agent time</th>'
        '<th>Wall time</th><th>Intervals</th><th>Evidence</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div></details></section>"
    )


def _render_work_item_metrics(run: CodexRunMetrics) -> str:
    """Render exact claim-bounded work-item segments and their measured usage."""

    if not run.work_item_segments:
        return ""
    rows = []
    for segment in run.work_item_segments:
        disposition = segment.disposition
        if segment.blocker_reference:
            disposition += f" · {segment.blocker_reference}"
        rows.append(
            "<tr>"
            f"<td><code>{_escape_html(segment.work_item_id)}</code></td>"
            f"<td>{_escape_html(segment.activity)}</td>"
            f"<td>{_local_time_html(segment.started_at)}</td>"
            f"<td>{_local_time_html(segment.ended_at)}</td>"
            f"<td>{_format_ms(segment.duration_ms)}</td>"
            f"<td>{_escape_html(disposition)}</td>"
            f"<td>{segment.usage.processed_tokens:,}</td>"
            f"<td>{_escape_html(_format_tokens_per_second(segment.inference.end_to_end_tokens_per_second))}</td>"
            "</tr>"
        )
    return (
        '<section id="work-item-metrics" class="metric-view">'
        '<div class="agents-heading"><h2>Work items</h2>'
        '<span class="evidence-badge">Exact claim events</span></div>'
        '<div class="table-scroll"><table><thead><tr><th>Work item</th><th>Activity</th>'
        '<th>Started</th><th>Ended</th><th>Duration</th><th>Outcome</th>'
        '<th>Processed</th><th>Inference rate</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div></section>"
    )


_TREND_CHART_CSS = """
.trend-view { margin-top:9px; }
.trend-view-switch { display:inline-flex; padding:2px; background:#eef3f6; border:1px solid #cfd8dc; border-radius:6px; }
.trend-view-switch button { min-height:30px; padding:4px 12px; color:#546e7a; background:transparent; border:0; border-radius:4px; cursor:pointer; font:700 .78em var(--font-ui); }
.trend-view-switch button[aria-pressed="true"] { color:#0d47a1; background:#fff; box-shadow:0 1px 3px rgba(38,50,56,.16); }
.trend-view-switch button:focus-visible { outline:2px solid #2563a6; outline-offset:2px; }
.trend-chart-panel { min-height:260px; margin-top:8px; overflow:auto; background:#fff; border:1px solid #d7e0e5; border-radius:6px; }
.trend-chart { display:block; width:100%; min-width:720px; height:auto; }
.trend-chart-grid { stroke:#e1e6ea; stroke-width:1; }
.trend-chart-axis { stroke:#90a4ae; stroke-width:1.25; }
.trend-chart-label { fill:#607d8b; font:12px var(--font-ui); }
.trend-chart-axis-title { fill:#455a64; font:700 12px var(--font-ui); letter-spacing:.02em; }
.trend-chart-line { fill:none; stroke-width:3; stroke-linecap:round; stroke-linejoin:round; }
.trend-chart-point { stroke:#fff; stroke-width:2; }
.trend-chart-marker { stroke:#e87523; stroke-width:2; stroke-dasharray:4 4; }
.trend-chart-marker-symbol { fill:#e87523; stroke:#fff; stroke-width:1.5; }
.trend-chart-legend { display:flex; flex-wrap:wrap; gap:8px 16px; padding:0 16px 13px; color:#546e7a; font-size:.78em; }
.trend-chart-legend span { display:inline-flex; align-items:center; gap:6px; }
.trend-chart-swatch { width:20px; height:3px; background:var(--trend-color); }
.trend-chart-swatch.is-dashed { height:0; background:none; border-top:2px dashed var(--trend-color); }
.trend-chart-swatch.is-marker { width:8px; height:8px; background:#e87523; transform:rotate(45deg); }
.trend-chart-empty { margin:0; padding:24px; color:#607d8b; }
@media (max-width:760px) { .trend-chart-panel { min-height:220px; } }
"""


_TREND_CHART_SCRIPT = r"""
function initializeTrendView(view) {
  var dataElement = view.querySelector("[data-trend-data]");
  var svg = view.querySelector("[data-trend-chart]");
  var legend = view.querySelector("[data-trend-legend]");
  var emptyState = view.querySelector("[data-trend-empty]");
  var buttons = Array.from(view.querySelectorAll("[data-trend-mode]"));
  var panels = Array.from(view.querySelectorAll("[data-trend-panel]"));
  if (!dataElement || !svg || !legend || !emptyState || !buttons.length) return;

  var data;
  try { data = JSON.parse(dataElement.textContent); }
  catch (error) { data = { series:[], markers:[], empty_message:"Chart data could not be loaded." }; }
  var rendered = false;
  var namespace = "http://www.w3.org/2000/svg";
  var localTime = new Intl.DateTimeFormat(undefined, {
    month:"short", day:"numeric", hour:"2-digit", minute:"2-digit"
  });

  function node(name, attributes, content) {
    var element = document.createElementNS(namespace, name);
    Object.keys(attributes || {}).forEach(function(key) {
      element.setAttribute(key, String(attributes[key]));
    });
    if (content !== undefined) element.textContent = content;
    return element;
  }
  function timestamp(value) {
    var result = new Date(value).getTime();
    return Number.isFinite(result) ? result : null;
  }
  function numeric(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  }
  function compact(value) {
    if (value >= 1000000000) return (value / 1000000000).toFixed(1).replace(/\.0$/, "") + "B";
    if (value >= 1000000) return (value / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
    if (value >= 1000) return (value / 1000).toFixed(1).replace(/\.0$/, "") + "K";
    return Math.round(value).toLocaleString();
  }
  function valueLabel(value) {
    if (data.value_format === "rate") return value.toFixed(2) + " tok/s";
    return Math.round(value).toLocaleString() + " tokens";
  }
  function axisValue(value) {
    if (data.value_format === "rate") return value.toFixed(value < 10 ? 1 : 0);
    return compact(value);
  }
  function appendTitle(element, text) {
    element.appendChild(node("title", {}, text));
  }
  function renderLegend() {
    legend.replaceChildren();
    (data.series || []).forEach(function(series) {
      var item = document.createElement("span");
      var swatch = document.createElement("i");
      swatch.className = "trend-chart-swatch" + (series.dash ? " is-dashed" : "");
      swatch.style.setProperty("--trend-color", series.color || "#2563a6");
      item.appendChild(swatch);
      item.appendChild(document.createTextNode(series.label));
      legend.appendChild(item);
    });
    if ((data.markers || []).length) {
      var markerItem = document.createElement("span");
      var markerSwatch = document.createElement("i");
      markerSwatch.className = "trend-chart-swatch is-marker";
      markerItem.appendChild(markerSwatch);
      markerItem.appendChild(document.createTextNode("Compaction"));
      legend.appendChild(markerItem);
    }
  }
  function renderChart() {
    if (rendered) return;
    rendered = true;
    var series = data.series || [];
    var markers = data.markers || [];
    var points = [];
    series.forEach(function(item) {
      (item.values || []).forEach(function(point) {
        var time = timestamp(point.timestamp);
        var value = numeric(point.value);
        if (time !== null && value !== null) points.push({ time:time, value:value });
      });
    });
    var markerValues = [];
    markers.forEach(function(marker) {
      [numeric(marker.before), numeric(marker.after)].forEach(function(value) {
        if (value !== null) markerValues.push(value);
      });
    });
    svg.replaceChildren();
    svg.appendChild(node("title", {}, data.title || "Trend chart"));
    svg.appendChild(node("desc", {}, data.description || "Time-series chart."));
    renderLegend();
    if (!points.length) {
      emptyState.hidden = false;
      emptyState.textContent = data.empty_message || "No chart data are available.";
      svg.setAttribute("hidden", "");
      legend.hidden = true;
      return;
    }
    emptyState.hidden = true;
    svg.removeAttribute("hidden");
    legend.hidden = false;

    var width = 1000;
    var height = 360;
    var margin = { top:28, right:26, bottom:58, left:78 };
    var plotWidth = width - margin.left - margin.right;
    var plotHeight = height - margin.top - margin.bottom;
    var times = points.map(function(point) { return point.time; }).concat(
      markers.map(function(marker) { return timestamp(marker.timestamp); }).filter(function(value) { return value !== null; })
    );
    var minimumTime = Math.min.apply(null, times);
    var maximumTime = Math.max.apply(null, times);
    if (minimumTime === maximumTime) {
      minimumTime -= 30 * 60 * 1000;
      maximumTime += 30 * 60 * 1000;
    }
    var maximumValue = Math.max.apply(null, points.map(function(point) { return point.value; }).concat(markerValues, [1]));
    var yMaximum = maximumValue * 1.08;
    function x(time) { return margin.left + (time - minimumTime) / (maximumTime - minimumTime) * plotWidth; }
    function y(value) { return margin.top + plotHeight - value / yMaximum * plotHeight; }

    for (var index = 0; index <= 4; index += 1) {
      var yValue = yMaximum * index / 4;
      var yPosition = y(yValue);
      svg.appendChild(node("line", { x1:margin.left, y1:yPosition, x2:width - margin.right, y2:yPosition, class:"trend-chart-grid" }));
      svg.appendChild(node("text", { x:margin.left - 10, y:yPosition + 4, "text-anchor":"end", class:"trend-chart-label" }, axisValue(yValue)));
    }
    for (var tick = 0; tick <= 4; tick += 1) {
      var tickTime = minimumTime + (maximumTime - minimumTime) * tick / 4;
      var tickX = x(tickTime);
      svg.appendChild(node("line", { x1:tickX, y1:margin.top, x2:tickX, y2:margin.top + plotHeight, class:"trend-chart-grid" }));
      svg.appendChild(node("text", { x:tickX, y:height - 25, "text-anchor":"middle", class:"trend-chart-label" }, localTime.format(new Date(tickTime))));
    }
    svg.appendChild(node("line", { x1:margin.left, y1:margin.top + plotHeight, x2:width - margin.right, y2:margin.top + plotHeight, class:"trend-chart-axis" }));
    svg.appendChild(node("line", { x1:margin.left, y1:margin.top, x2:margin.left, y2:margin.top + plotHeight, class:"trend-chart-axis" }));
    svg.appendChild(node("text", { x:18, y:margin.top + plotHeight / 2, transform:"rotate(-90 18 " + (margin.top + plotHeight / 2) + ")", "text-anchor":"middle", class:"trend-chart-axis-title" }, data.axis_label || "Value"));
    svg.appendChild(node("text", { x:margin.left + plotWidth / 2, y:height - 5, "text-anchor":"middle", class:"trend-chart-axis-title" }, "Local time"));

    markers.forEach(function(marker) {
      var markerTime = timestamp(marker.timestamp);
      if (markerTime === null) return;
      var markerX = x(markerTime);
      var line = node("line", { x1:markerX, y1:margin.top, x2:markerX, y2:margin.top + plotHeight, class:"trend-chart-marker" });
      appendTitle(line, marker.label + " · " + localTime.format(new Date(markerTime)) + " · " + compact(marker.before || 0) + " → " + compact(marker.after || 0) + " tokens");
      svg.appendChild(line);
      var symbol = node("polygon", { points:(markerX - 6) + "," + (margin.top + 1) + " " + (markerX + 6) + "," + (margin.top + 1) + " " + markerX + "," + (margin.top + 12), class:"trend-chart-marker-symbol" });
      appendTitle(symbol, marker.label + " at " + localTime.format(new Date(markerTime)));
      svg.appendChild(symbol);
    });

    series.forEach(function(item) {
      var pathParts = [];
      var connected = false;
      (item.values || []).forEach(function(point) {
        var pointTime = timestamp(point.timestamp);
        var pointValue = numeric(point.value);
        if (pointTime === null || pointValue === null) {
          connected = false;
          return;
        }
        pathParts.push((connected ? "L" : "M") + x(pointTime).toFixed(2) + " " + y(pointValue).toFixed(2));
        connected = true;
      });
      if (pathParts.length) {
        svg.appendChild(node("path", {
          d:pathParts.join(" "), class:"trend-chart-line", stroke:item.color || "#2563a6",
          "stroke-dasharray":item.dash || ""
        }));
      }
      (item.values || []).forEach(function(point) {
        var pointTime = timestamp(point.timestamp);
        var pointValue = numeric(point.value);
        if (pointTime === null || pointValue === null) return;
        var circle = node("circle", { cx:x(pointTime), cy:y(pointValue), r:4.5, fill:item.color || "#2563a6", class:"trend-chart-point" });
        appendTitle(circle, item.label + " · " + localTime.format(new Date(pointTime)) + " · " + valueLabel(pointValue));
        svg.appendChild(circle);
      });
    });
  }
  function setMode(mode) {
    buttons.forEach(function(button) {
      button.setAttribute("aria-pressed", button.dataset.trendMode === mode ? "true" : "false");
    });
    panels.forEach(function(panel) { panel.hidden = panel.dataset.trendPanel !== mode; });
    if (mode === "chart") renderChart();
  }
  buttons.forEach(function(button) {
    button.addEventListener("click", function() { setMode(button.dataset.trendMode); });
  });
}
"""


_EXECUTION_HEATMAP_CSS = """
.heatmap-controls { display:flex; flex-wrap:wrap; align-items:end; gap:10px 16px; margin:10px 0; }
.heatmap-control { display:grid; gap:4px; color:#455a64; font-size:.8em; font-weight:700; }
.heatmap-control select { min-height:34px; padding:5px 28px 5px 8px; color:#263238; background:#fff; border:1px solid #90a4ae; border-radius:5px; font:inherit; }
.heatmap-granularity { display:flex; gap:4px; margin:0; padding:0; border:0; }
.heatmap-granularity legend { margin-bottom:4px; color:#455a64; font-size:.8em; font-weight:700; }
.heatmap-granularity button { min-height:34px; padding:5px 10px; color:#455a64; background:#fff; border:1px solid #90a4ae; border-radius:5px; cursor:pointer; font:600 .8em var(--font-ui); }
.heatmap-granularity button[aria-pressed="true"] { color:#0d47a1; background:#e3f2fd; border-color:#2563a6; }
.heatmap-control select:focus-visible, .heatmap-granularity button:focus-visible, .heatmap-cell:focus-visible { outline:2px solid #2563a6; outline-offset:2px; }
.heatmap-scroll-frame { display:grid; grid-template-columns:36px minmax(0,1fr) 36px; align-items:center; gap:6px; margin-top:8px; }
.heatmap-scroll { min-width:0; overflow:auto; scrollbar-width:none; background:#fff; border:1px solid #d7e0e5; border-radius:6px; }
.heatmap-scroll::-webkit-scrollbar { display:none; }
.heatmap-scroll-button { width:36px; height:48px; padding:0; color:#2563a6; background:#fff; border:1px solid #90a4ae; border-radius:6px; cursor:pointer; font:700 1.3em var(--font-ui); }
.heatmap-scroll-button:hover:not(:disabled) { color:#0d47a1; border-color:#2563a6; }
.heatmap-scroll-button:focus-visible { outline:2px solid #2563a6; outline-offset:2px; }
.heatmap-scroll-button:disabled { opacity:.35; cursor:default; }
.heatmap-grid { display:grid; width:max-content; min-width:100%; align-items:stretch; }
.heatmap-corner, .heatmap-column, .heatmap-row-label { position:sticky; z-index:2; box-sizing:border-box; padding:7px 8px; color:#455a64; background:#f5f7f8; border-right:1px solid #d7e0e5; border-bottom:1px solid #d7e0e5; font-size:.76em; font-weight:700; }
.heatmap-corner, .heatmap-row-label { left:0; }
.heatmap-corner { z-index:4; }
.heatmap-column { top:0; z-index:3; min-width:72px; text-align:center; font-family:var(--font-code); }
.heatmap-row-label { display:flex; align-items:center; min-width:170px; max-width:220px; white-space:normal; }
.heatmap-cell { --heatmap-color:198,40,40; --heatmap-accent:#8e1b16; min-width:72px; min-height:48px; padding:5px 4px; color:#263238; background:rgba(var(--heatmap-color),var(--heatmap-alpha,.06)); border:0; border-right:1px solid rgba(144,164,174,.45); border-bottom:1px solid rgba(144,164,174,.45); cursor:pointer; font:600 .72em var(--font-code); }
.heatmap-cell.is-context { white-space:pre-line; line-height:1.25; }
.heatmap-cell.is-inactive { --heatmap-color:37,99,166; --heatmap-accent:#0d47a1; }
.heatmap-cell.is-cost { --heatmap-color:31,122,69; --heatmap-accent:#176b3a; }
.heatmap-cell:hover { box-shadow:inset 0 0 0 2px var(--heatmap-accent); }
.heatmap-cell[aria-pressed="true"] { box-shadow:inset 0 0 0 3px var(--heatmap-accent); }
.heatmap-empty { padding:16px; color:#607d8b; }
.heatmap-status { margin-left:auto; color:#546e7a; font-family:var(--font-code); font-size:.78em; }
.heatmap-drilldown-frame { display:grid; grid-template-columns:36px minmax(0,1fr) 36px; align-items:center; gap:6px; margin-top:10px; }
.heatmap-drilldown { min-width:0; padding:12px 14px; background:#fff; border:1px solid #cfd8dc; border-radius:6px; }
.heatmap-drilldown h3 { margin:0 0 4px; color:#263238; }
.heatmap-drilldown-summary { margin:0; color:#455a64; font-size:.86em; }
.heatmap-drilldown-path { display:flex; flex-wrap:wrap; align-items:center; gap:5px; margin-top:9px; color:#607d8b; font-size:.78em; }
.heatmap-drilldown-path button { padding:3px 6px; color:#2563a6; background:#fff; border:1px solid #90a4ae; border-radius:4px; cursor:pointer; font:600 1em var(--font-ui); }
.heatmap-drilldown-path button:focus-visible { outline:2px solid #2563a6; outline-offset:2px; }
.heatmap-event-list { max-height:38vh; margin:10px 0 0; padding-left:24px; overflow:auto; }
.heatmap-event-list li { display:flex; align-items:baseline; gap:10px; margin:5px 0; color:#455a64; font-size:.8em; line-height:1.4; }
.heatmap-event-copy { min-width:0; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
.heatmap-event-turn-link { flex:0 0 auto; color:#2563a6; font-weight:700; text-decoration:none; }
.heatmap-event-turn-link:hover { text-decoration:underline; }
.heatmap-event-turn-link:focus-visible { outline:2px solid #2563a6; outline-offset:2px; }
.heatmap-event-list code { color:#263238; }
@media (max-width:700px) { .heatmap-status { width:100%; margin-left:0; } .heatmap-scroll-frame, .heatmap-drilldown-frame { grid-template-columns:32px minmax(0,1fr) 32px; gap:4px; } .heatmap-scroll-button { width:32px; } .heatmap-row-label { min-width:140px; } }
"""


_EXECUTION_HEATMAP_SCRIPT = r"""
function initializeExecutionHeatmap(section) {
  var dataElement = section.querySelector("#execution-heatmap-data");
  var grid = section.querySelector("[data-heatmap-grid]");
  var heatmapScroll = section.querySelector(".heatmap-scroll");
  var scrollButtons = Array.from(section.querySelectorAll("[data-heatmap-scroll]"));
  var emptyState = section.querySelector("[data-heatmap-empty]");
  var metricSelect = section.querySelector("#heatmap-metric");
  var minuteButtons = Array.from(section.querySelectorAll("[data-heatmap-minutes]"));
  var status = section.querySelector("[data-heatmap-status]");
  var drilldownTitle = section.querySelector("#heatmap-drilldown-title");
  var drilldownSummary = section.querySelector("[data-heatmap-drilldown-summary]");
  var drilldownPath = section.querySelector("[data-heatmap-drilldown-path]");
  var drilldownStepButtons = Array.from(section.querySelectorAll("[data-heatmap-drilldown-step]"));
  var eventList = section.querySelector("[data-heatmap-event-list]");
  if (!dataElement || !grid || !heatmapScroll || !metricSelect) return;

  var data;
  try { data = JSON.parse(dataElement.textContent); }
  catch (error) {
    emptyState.hidden = false;
    emptyState.textContent = "Heatmap data could not be loaded.";
    return;
  }
  var selectedMinutes = 5;
  var drilldownMinutes = [1440, 360, 60, 30, 15, 5, 1];
  var selectedCell = null;
  var selectedCellViewportOffset = null;
  var pendingCellSelection = null;
  var currentDrilldown = null;
  var stateLabels = new Map(data.states.map(function(state) { return [state.id, state.label]; }));
  var agentLabels = new Map(data.agents.map(function(agent) { return [agent.id, agent.label]; }));
  var tokenRows = [
    { id:"uncached_input_tokens", label:"Uncached input" },
    { id:"cached_input_tokens", label:"Cached input" },
    { id:"reasoning_tokens", label:"Reasoning" },
    { id:"output_tokens", label:"Output" },
    { id:"tool_calls", label:"Tool calls", format:"count" },
    { id:"average_context_tokens", source:"context_tokens", label:"Context size (avg)", aggregation:"average", format:"context" },
    { id:"maximum_context_tokens", source:"context_tokens", label:"Context size (max)", aggregation:"maximum", format:"context" },
    { id:"cost_usd", label:"Cost", format:"currency" }
  ];
  var modelRows = data.models.concat([{ id:"cost_usd", label:"Cost", format:"currency" }]);
  var timeFormatter = new Intl.DateTimeFormat(undefined, { hour:"2-digit", minute:"2-digit" });
  var fullTimeFormatter = new Intl.DateTimeFormat(undefined, { dateStyle:"medium", timeStyle:"medium" });

  function timestamp(value) { return new Date(value).getTime(); }
  function compact(value) {
    if (value >= 1000000000) return (value / 1000000000).toFixed(value >= 10000000000 ? 0 : 1) + "B";
    if (value >= 1000000) return (value / 1000000).toFixed(value >= 10000000 ? 0 : 1) + "M";
    if (value >= 1000) return (value / 1000).toFixed(value >= 10000 ? 0 : 1) + "K";
    return Math.round(value).toLocaleString();
  }
  function rangeLabel(bucket) {
    return timeFormatter.format(new Date(bucket.start)) + "–" + timeFormatter.format(new Date(bucket.end));
  }
  function duration(value) {
    if (value < 1000) return Math.round(value) + "ms";
    if (value < 60000) return (value / 1000).toFixed(value < 10000 ? 1 : 0) + "s";
    var minutes = Math.floor(value / 60000);
    var seconds = Math.round((value % 60000) / 1000);
    return minutes + "m " + seconds + "s";
  }
  function currency(value) {
    if (value === 0) return "$0.00";
    if (value < .01) return "$" + value.toFixed(4);
    return "$" + value.toFixed(2);
  }
  function responseValue(response, metric, row) {
    return row.id === "cost_usd" ? response.cost_usd : response.usage[row.source || row.id];
  }
  function formatValue(metric, value, row) {
    if (metric === "wall_time") return duration(value);
    if (row && row.format === "currency") return currency(value);
    if (row && row.format === "context") {
      var percent = data.context_capacity ? Math.round(value / data.context_capacity * 100) : 0;
      return percent + "%\n" + compact(value);
    }
    return compact(value);
  }
  function buckets() {
    var width = selectedMinutes * 60000;
    var runStart = timestamp(data.started_at);
    var runEnd = timestamp(data.ended_at);
    var first = Math.floor(runStart / width) * width;
    var values = [];
    for (var start = first; start < runEnd; start += width) {
      values.push({ start:start, end:start + width });
    }
    return values;
  }
  function responseTime(response) {
    return timestamp(response.completed_at || response.ended_at || response.started_at);
  }
  function updateHeatmapScrollButtons() {
    var atStart = heatmapScroll.scrollLeft <= 1;
    var atEnd = heatmapScroll.scrollLeft + heatmapScroll.clientWidth >= heatmapScroll.scrollWidth - 1;
    scrollButtons.forEach(function(button) {
      button.disabled = button.dataset.heatmapScroll === "left" ? atStart : atEnd;
    });
  }
  function rows(metric) {
    if (metric === "wall_time") {
      return data.states.map(function(state) { return { id:state.id, label:state.label }; });
    }
    if (metric === "tokens") return tokenRows;
    if (metric === "models") return modelRows;
    return data.agents.map(function(agent) { return { id:agent.id, label:agent.label }; });
  }
  function cellValue(metric, row, bucket) {
    if (metric === "wall_time") {
      var segments = data.intervals.filter(function(interval) {
        return interval.state === row.id && timestamp(interval.ended_at) > bucket.start && timestamp(interval.started_at) < bucket.end;
      }).map(function(interval) {
        return [Math.max(timestamp(interval.started_at), bucket.start), Math.min(timestamp(interval.ended_at), bucket.end)];
      }).sort(function(left, right) { return left[0] - right[0]; });
      if (!segments.length) return 0;
      var total = 0;
      var mergedStart = segments[0][0];
      var mergedEnd = segments[0][1];
      segments.slice(1).forEach(function(segment) {
        if (segment[0] <= mergedEnd) mergedEnd = Math.max(mergedEnd, segment[1]);
        else {
          total += mergedEnd - mergedStart;
          mergedStart = segment[0];
          mergedEnd = segment[1];
        }
      });
      return total + mergedEnd - mergedStart;
    }
    if (row.id === "tool_calls") {
      return data.tools.filter(function(tool) {
        var occurredAt = timestamp(tool.completed_at || tool.started_at);
        return occurredAt >= bucket.start && occurredAt < bucket.end;
      }).length;
    }
    var values = data.responses.filter(function(response) {
      var occurredAt = responseTime(response);
      var matchesRow = metric === "tokens" || (metric === "models" && (row.id === "cost_usd" || response.model_id === row.id)) || response.thread_id === row.id;
      return matchesRow && occurredAt >= bucket.start && occurredAt < bucket.end;
    }).map(function(response) {
      return metric === "models" ? (row.id === "cost_usd" ? response.cost_usd : response.usage.processed_tokens) : responseValue(response, metric, row);
    });
    if (row.format === "context") values = values.filter(function(value) { return value > 0; });
    if (row.aggregation === "average") {
      return values.length ? values.reduce(function(total, value) { return total + value; }, 0) / values.length : 0;
    }
    if (row.aggregation === "maximum") {
      return values.reduce(function(largest, value) { return Math.max(largest, value); }, 0);
    }
    return values.reduce(function(total, value) { return total + value; }, 0);
  }
  function matchingEvents(metric, row, bucket) {
    if (metric === "wall_time") {
      return data.intervals.filter(function(interval) {
        return interval.state === row.id && timestamp(interval.ended_at) > bucket.start && timestamp(interval.started_at) < bucket.end;
      }).map(function(interval) {
        return {
          started_at:interval.started_at,
          label:interval.detail || stateLabels.get(interval.state) || interval.state,
          detail:duration(interval.duration_ms) + (interval.preview ? " · " + interval.preview : ""),
          turn_target:interval.turn_target,
          event_target:interval.event_target
        };
      });
    }
    if (row.id === "tool_calls") {
      return data.tools.filter(function(tool) {
        var occurredAt = timestamp(tool.completed_at || tool.started_at);
        return occurredAt >= bucket.start && occurredAt < bucket.end;
      }).map(function(tool) {
        return {
          started_at:tool.started_at,
          label:tool.tool_name,
          detail:duration(tool.duration_ms) + (tool.preview ? " · " + tool.preview : ""),
          turn_target:tool.turn_target,
          event_target:tool.event_target
        };
      });
    }
    return data.responses.filter(function(response) {
      var occurredAt = responseTime(response);
      var matchesRow = metric === "tokens" || (metric === "models" && (row.id === "cost_usd" || response.model_id === row.id)) || response.thread_id === row.id;
      return matchesRow && occurredAt >= bucket.start && occurredAt < bucket.end;
    }).map(function(response) {
      var modelLabel = response.model || "Model response";
      if (response.effort) modelLabel += " · effort " + response.effort;
      if (metric === "tokens") modelLabel = (agentLabels.get(response.thread_id) || response.thread_id) + " · " + modelLabel;
      return {
        started_at:response.completed_at || response.started_at,
        label:modelLabel + " · " + formatValue(metric, metric === "models" ? (row.id === "cost_usd" ? response.cost_usd : response.usage.processed_tokens) : responseValue(response, metric, row), row).replaceAll("\n", " · ") + " " + (metric === "models" && row.id !== "cost_usd" ? "processed tokens" : row.label.toLowerCase()),
        detail:duration(response.duration_ms) + (response.preview ? " · " + response.preview : ""),
        turn_target:response.turn_target,
        event_target:response.event_target
      };
    });
  }
  function alignedBucket(value, minutes) {
    var width = minutes * 60000;
    var start = Math.floor(value / width) * width;
    return { start:start, end:start + width };
  }
  function visibleBucket(value, minutes) {
    return alignedBucket(Math.max(value, timestamp(data.started_at)), minutes);
  }
  function trailItem(metric, row, minutes, bucket) {
    return { bucket:bucket, minutes:minutes, value:cellValue(metric, row, bucket) };
  }
  function selectionTrail(metric, row, minutes, bucket, existingTrail) {
    if (!existingTrail || !existingTrail.length) return [trailItem(metric, row, minutes, bucket)];
    var existingIndex = existingTrail.findIndex(function(item) { return item.minutes === minutes; });
    if (existingIndex >= 0) {
      var restored = existingTrail.slice(0, existingIndex + 1);
      restored[existingIndex] = trailItem(metric, row, minutes, bucket);
      return restored;
    }
    var current = existingTrail[existingTrail.length - 1];
    var currentIndex = drilldownMinutes.indexOf(current.minutes);
    var targetIndex = drilldownMinutes.indexOf(minutes);
    if (targetIndex > currentIndex) {
      var extended = existingTrail.slice();
      drilldownMinutes.slice(currentIndex + 1, targetIndex + 1).forEach(function(levelMinutes) {
        extended.push(trailItem(metric, row, levelMinutes, visibleBucket(bucket.start, levelMinutes)));
      });
      return extended;
    }
    return [trailItem(metric, row, minutes, bucket)];
  }
  function setMinuteControl(minutes) {
    selectedMinutes = minutes;
    minuteButtons.forEach(function(button) {
      button.setAttribute("aria-pressed", Number(button.dataset.heatmapMinutes) === minutes ? "true" : "false");
    });
  }
  function selectDrilldown(metric, row, trail) {
    currentDrilldown = { metric:metric, row:row, trail:trail };
    setMinuteControl(trail[trail.length - 1].minutes);
    render();
  }
  function updateDrilldownStepButtons() {
    drilldownStepButtons.forEach(function(button) {
      if (!currentDrilldown) {
        button.disabled = true;
        return;
      }
      var current = currentDrilldown.trail[currentDrilldown.trail.length - 1];
      var direction = Number(button.dataset.heatmapDrilldownStep);
      var shiftedStart = current.bucket.start + direction * current.minutes * 60000;
      var shiftedEnd = current.bucket.end + direction * current.minutes * 60000;
      button.disabled = shiftedEnd <= timestamp(data.started_at) || shiftedStart >= timestamp(data.ended_at);
    });
  }
  function shiftDrilldown(direction) {
    if (!currentDrilldown) return;
    var current = currentDrilldown.trail[currentDrilldown.trail.length - 1];
    var shifted = {
      start:current.bucket.start + direction * current.minutes * 60000,
      end:current.bucket.end + direction * current.minutes * 60000
    };
    if (shifted.end <= timestamp(data.started_at) || shifted.start >= timestamp(data.ended_at)) return;
    var shiftedTrail = currentDrilldown.trail.map(function(item, index, trail) {
      var bucket = index === trail.length - 1 ? shifted : alignedBucket(shifted.start, item.minutes);
      return trailItem(currentDrilldown.metric, currentDrilldown.row, item.minutes, bucket);
    });
    selectDrilldown(
      currentDrilldown.metric,
      currentDrilldown.row,
      shiftedTrail
    );
  }
  function stepBack() {
    if (!currentDrilldown) return;
    var trail = currentDrilldown.trail;
    if (trail.length > 1) {
      selectDrilldown(currentDrilldown.metric, currentDrilldown.row, trail.slice(0, -1));
      return;
    }
    var current = trail[0];
    var currentIndex = drilldownMinutes.indexOf(current.minutes);
    if (currentIndex <= 0) return;
    var largerMinutes = drilldownMinutes[currentIndex - 1];
    var largerBucket = alignedBucket(current.bucket.start, largerMinutes);
    selectDrilldown(
      currentDrilldown.metric,
      currentDrilldown.row,
      [trailItem(currentDrilldown.metric, currentDrilldown.row, largerMinutes, largerBucket)]
    );
  }
  function renderDrilldownPath(metric, row, trail) {
    drilldownPath.replaceChildren();
    trail.forEach(function(item, index) {
      if (index) drilldownPath.appendChild(document.createTextNode("›"));
      var label = item.minutes + " min · " + rangeLabel(item.bucket);
      if (index === trail.length - 1) {
        var current = document.createElement("strong");
        current.textContent = label;
        drilldownPath.appendChild(current);
        return;
      }
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.setAttribute("aria-label", "Return to " + label);
      button.addEventListener("click", function() {
        selectDrilldown(metric, row, trail.slice(0, index + 1));
      });
      drilldownPath.appendChild(button);
    });
  }
  function renderEvents(metric, row, bucket) {
    eventList.hidden = false;
    var events = matchingEvents(metric, row, bucket).sort(function(left, right) {
      return timestamp(left.started_at) - timestamp(right.started_at);
    });
    if (!events.length) {
      var empty = document.createElement("li");
      empty.textContent = "No recorded evidence in this cell.";
      eventList.appendChild(empty);
      return;
    }
    events.slice(0, 100).forEach(function(event) {
      var item = document.createElement("li");
      var copy = document.createElement("span");
      copy.className = "heatmap-event-copy";
      var time = document.createElement("code");
      time.textContent = timeFormatter.format(new Date(event.started_at));
      copy.append(time, document.createTextNode(" · " + event.label + " · " + event.detail));
      item.appendChild(copy);
      if (event.turn_target) {
        var turnLink = document.createElement("a");
        turnLink.className = "heatmap-event-turn-link";
        turnLink.href = "#" + event.turn_target;
        turnLink.textContent = "View in turn";
        turnLink.dataset.turnDetailLink = "";
        turnLink.dataset.returnTarget = "#execution-heatmap";
        if (event.event_target) turnLink.dataset.turnEventTarget = event.event_target;
        item.appendChild(turnLink);
      }
      eventList.appendChild(item);
    });
    if (events.length > 100) {
      var remainder = document.createElement("li");
      remainder.textContent = (events.length - 100).toLocaleString() + " additional events omitted from this view.";
      eventList.appendChild(remainder);
    }
  }
  function renderDrilldownLevel(metric, row, trail) {
    currentDrilldown = { metric:metric, row:row, trail:trail };
    updateDrilldownStepButtons();
    var current = trail[trail.length - 1];
    var metricLabel = metric === "tokens" || metric === "models" ? row.label : metricSelect.options[metricSelect.selectedIndex].text;
    drilldownTitle.textContent = row.label + " · " + rangeLabel(current.bucket);
    drilldownSummary.textContent = metricLabel + ": " + formatValue(metric, current.value, row) + ". Events in this period are listed below.";
    renderDrilldownPath(metric, row, trail);
    eventList.replaceChildren();
    renderEvents(metric, row, current.bucket);
  }
  function selectCell(metric, row, bucket, sourceCell) {
    selectedCellViewportOffset = sourceCell.getBoundingClientRect().left - heatmapScroll.getBoundingClientRect().left;
    var existingTrail = currentDrilldown && currentDrilldown.metric === metric && currentDrilldown.row.id === row.id
      ? currentDrilldown.trail
      : [];
    selectDrilldown(metric, row, selectionTrail(metric, row, selectedMinutes, bucket, existingTrail));
  }
  function drillIntoCell(metric, row, bucket, sourceCell) {
    selectedCellViewportOffset = sourceCell.getBoundingClientRect().left - heatmapScroll.getBoundingClientRect().left;
    var existingTrail = currentDrilldown && currentDrilldown.metric === metric && currentDrilldown.row.id === row.id
      ? currentDrilldown.trail
      : [];
    var trail = selectionTrail(metric, row, selectedMinutes, bucket, existingTrail);
    var currentIndex = drilldownMinutes.indexOf(selectedMinutes);
    var smallerMinutes = drilldownMinutes[currentIndex + 1];
    if (smallerMinutes) {
      trail = selectionTrail(metric, row, smallerMinutes, visibleBucket(bucket.start, smallerMinutes), trail);
    }
    selectDrilldown(metric, row, trail);
  }
  function render() {
    var metric = metricSelect.value;
    var bucketValues = buckets();
    var rowValues = rows(metric);
    var matrix = rowValues.map(function(row) {
      return bucketValues.map(function(bucket) { return cellValue(metric, row, bucket); });
    });
    selectedCell = null;
    grid.replaceChildren();
    grid.style.gridTemplateColumns = "minmax(170px,220px) repeat(" + bucketValues.length + ",minmax(72px,1fr))";
    var corner = document.createElement("div");
    corner.className = "heatmap-corner";
    corner.textContent = "Periods";
    grid.appendChild(corner);
    bucketValues.forEach(function(bucket) {
      var heading = document.createElement("div");
      heading.className = "heatmap-column";
      heading.textContent = timeFormatter.format(new Date(bucket.start));
      heading.title = fullTimeFormatter.format(new Date(bucket.start));
      grid.appendChild(heading);
    });
    rowValues.forEach(function(row, rowIndex) {
      var rowMaximum = matrix[rowIndex].reduce(function(largest, value) { return Math.max(largest, value); }, 0);
      var scaleMaximum = row.format === "context" ? data.context_capacity : rowMaximum;
      var label = document.createElement("div");
      label.className = "heatmap-row-label";
      label.textContent = row.label;
      grid.appendChild(label);
      bucketValues.forEach(function(bucket, bucketIndex) {
        var value = matrix[rowIndex][bucketIndex];
        var intensity = scaleMaximum ? Math.min(1, value / scaleMaximum) : 0;
        var cell = document.createElement("button");
        cell.type = "button";
        cell.className = "heatmap-cell" + (metric === "wall_time" && row.id === "user_pause" ? " is-inactive" : "") + (row.format === "context" ? " is-context" : "") + (row.id === "cost_usd" ? " is-cost" : "");
        cell.style.setProperty("--heatmap-alpha", String(.05 + intensity * .5));
        var isSelected = currentDrilldown
          && currentDrilldown.metric === metric
          && currentDrilldown.row.id === row.id
          && currentDrilldown.trail[currentDrilldown.trail.length - 1].bucket.start === bucket.start;
        cell.setAttribute("aria-pressed", isSelected ? "true" : "false");
        cell.textContent = formatValue(metric, value, row);
        cell.setAttribute("aria-label", row.label + ", " + fullTimeFormatter.format(new Date(bucket.start)) + ", " + metricSelect.options[metricSelect.selectedIndex].text + " " + cell.textContent.replaceAll("\n", ", "));
        cell.addEventListener("click", function() {
          clearTimeout(pendingCellSelection);
          pendingCellSelection = setTimeout(function() { selectCell(metric, row, bucket, cell); }, 300);
        });
        cell.addEventListener("dblclick", function() {
          clearTimeout(pendingCellSelection);
          pendingCellSelection = null;
          drillIntoCell(metric, row, bucket, cell);
        });
        if (isSelected) selectedCell = cell;
        grid.appendChild(cell);
      });
    });
    emptyState.hidden = rowValues.length > 0 && bucketValues.length > 0;
    grid.hidden = !emptyState.hidden;
    if (currentDrilldown && currentDrilldown.metric === metric) {
      renderDrilldownLevel(metric, currentDrilldown.row, currentDrilldown.trail);
    } else {
      selectedCell = null;
      currentDrilldown = null;
      updateDrilldownStepButtons();
      drilldownTitle.textContent = "Select a heatmap cell";
      drilldownSummary.textContent = "Choose a cell to inspect its events.";
      drilldownPath.replaceChildren();
      eventList.replaceChildren();
      eventList.hidden = true;
    }
    status.textContent = bucketValues.length + " periods";
    requestAnimationFrame(function() {
      if (selectedCell && selectedCellViewportOffset !== null) {
        var currentOffset = selectedCell.getBoundingClientRect().left - heatmapScroll.getBoundingClientRect().left;
        heatmapScroll.scrollLeft += currentOffset - selectedCellViewportOffset;
        selectedCellViewportOffset = null;
      } else if (selectedCell) {
        selectedCell.scrollIntoView({ block:"nearest", inline:"nearest" });
      }
      updateHeatmapScrollButtons();
    });
  }
  metricSelect.addEventListener("change", function() {
    currentDrilldown = null;
    render();
  });
  minuteButtons.forEach(function(button) {
    button.addEventListener("click", function() {
      var minutes = Number(button.dataset.heatmapMinutes);
      if (!currentDrilldown) {
        setMinuteControl(minutes);
        render();
        return;
      }
      var current = currentDrilldown.trail[currentDrilldown.trail.length - 1];
      var bucket = visibleBucket(current.bucket.start, minutes);
      var trail = selectionTrail(currentDrilldown.metric, currentDrilldown.row, minutes, bucket, currentDrilldown.trail);
      selectDrilldown(currentDrilldown.metric, currentDrilldown.row, trail);
    });
  });
  scrollButtons.forEach(function(button) {
    button.addEventListener("click", function() {
      var direction = button.dataset.heatmapScroll === "left" ? -1 : 1;
      var column = grid.querySelector(".heatmap-column");
      var bucketWidth = column ? column.getBoundingClientRect().width : 72;
      heatmapScroll.scrollBy({ left:direction * bucketWidth, behavior:"smooth" });
    });
  });
  drilldownStepButtons.forEach(function(button) {
    button.addEventListener("click", function() {
      shiftDrilldown(Number(button.dataset.heatmapDrilldownStep));
    });
  });
  grid.addEventListener("contextmenu", function(event) {
    if (!event.target.closest(".heatmap-cell")) return;
    event.preventDefault();
    stepBack();
  });
  heatmapScroll.addEventListener("scroll", updateHeatmapScrollButtons, { passive:true });
  render();
}
"""


def _tool_activity_preview(tool_name: str, detail: str, limit: int = 150) -> str:
    """Return a concise heatmap preview for one tool invocation."""

    marker = "tools.exec_command("
    if tool_name == "exec" and marker in detail:
        parameters = detail.split(marker, 1)[1]
        parameters = parameters.split("); text(", 1)[0]
        return _compact_display_text(f"Execute {parameters}", limit)
    return _compact_display_text(f"{tool_name}: {detail}", limit)


def _response_activity_preview(
    thread: CodexThreadMetrics,
    response: ResponseUsage,
    limit: int = 150,
) -> str:
    """Return bounded sanitized narrative or initiated-tool context for a response."""

    started_at = _parse_iso_datetime(response.started_at)
    ended_at = _parse_iso_datetime(response.last_output_at or response.completed_at)
    matched_reasoning = False
    if started_at is not None and ended_at is not None:
        activities = sorted(
            thread.activities,
            key=lambda activity: (
                _parse_iso_datetime(activity.event_timestamp)
                or datetime.min.replace(tzinfo=timezone.utc),
                activity.source_ordinal,
            ),
        )
        for activity in activities:
            if activity.activity_type not in {"reasoning", "output"}:
                continue
            if response.turn_id and activity.turn_id != response.turn_id:
                continue
            occurred_at = _parse_iso_datetime(activity.event_timestamp)
            if occurred_at is None or occurred_at < started_at or occurred_at > ended_at:
                continue
            matched_reasoning = matched_reasoning or activity.activity_type == "reasoning"
            preview = _compact_display_text(activity.content, limit)
            if preview:
                return preview

    response_end = _parse_iso_datetime(response.last_output_at)
    if response_end is not None:
        initiated_tools: list[tuple[datetime, str]] = []
        for tool in thread.tool_intervals:
            tool_start = _parse_iso_datetime(tool.started_at)
            if tool_start is None or abs((tool_start - response_end).total_seconds()) > 1:
                continue
            if response.turn_id and tool.turn_id != response.turn_id:
                continue
            detail = tool.argument_summary or tool.result_summary or tool.tool_name
            initiated_tools.append(
                (tool_start, _tool_activity_preview(tool.tool_name, detail, limit))
            )
        for call in thread.mcp_calls:
            call_start = _parse_iso_datetime(call.started_at)
            if call_start is None or abs((call_start - response_end).total_seconds()) > 1:
                continue
            if response.turn_id and call.turn_id != response.turn_id:
                continue
            name = f"{call.server_name}.{call.tool_name}"
            detail = call.argument_summary or call.result_summary or name
            initiated_tools.append((call_start, f"{name}: {detail}"))
        if initiated_tools:
            return _compact_display_text(
                min(initiated_tools, key=lambda item: item[0])[1],
                limit,
            )

    return "Internal reasoning (content unavailable)" if matched_reasoning else ""


def _response_activity_previews(
    thread: CodexThreadMetrics,
    limit: int = 150,
) -> dict[int, str]:
    """Build all response previews from one reusable chronological thread index."""

    activity_rows = []
    for activity in thread.activities:
        if activity.activity_type not in {"reasoning", "output"}:
            continue
        occurred_at = _parse_iso_datetime(activity.event_timestamp)
        if occurred_at is not None:
            activity_rows.append((occurred_at, activity.source_ordinal, activity))
    activity_rows.sort(key=lambda item: (item[0], item[1]))
    activities_by_turn: dict[str | None, list[tuple[datetime, int, AgentActivity]]] = {}
    for row in activity_rows:
        activities_by_turn.setdefault(row[2].turn_id, []).append(row)

    tool_rows: list[tuple[datetime, str | None, str]] = []
    for tool in thread.tool_intervals:
        started_at = _parse_iso_datetime(tool.started_at)
        if started_at is None:
            continue
        detail = tool.argument_summary or tool.result_summary or tool.tool_name
        tool_rows.append(
            (started_at, tool.turn_id, _tool_activity_preview(tool.tool_name, detail, limit))
        )
    for call in thread.mcp_calls:
        started_at = _parse_iso_datetime(call.started_at)
        if started_at is None:
            continue
        name = f"{call.server_name}.{call.tool_name}"
        detail = call.argument_summary or call.result_summary or name
        tool_rows.append((started_at, call.turn_id, f"{name}: {detail}"))
    tool_rows.sort(key=lambda item: item[0])
    tools_by_turn: dict[str | None, list[tuple[datetime, str | None, str]]] = {}
    for row in tool_rows:
        tools_by_turn.setdefault(row[1], []).append(row)

    previews: dict[int, str] = {}
    one_second = timedelta(seconds=1)
    for response in thread.responses:
        started_at = _parse_iso_datetime(response.started_at)
        ended_at = _parse_iso_datetime(response.last_output_at or response.completed_at)
        matched_reasoning = False
        if started_at is not None and ended_at is not None:
            candidates = (
                activities_by_turn.get(response.turn_id, [])
                if response.turn_id
                else activity_rows
            )
            candidate_times = [item[0] for item in candidates]
            start_index = bisect_left(candidate_times, started_at)
            end_index = bisect_right(candidate_times, ended_at)
            for _, _, activity in candidates[start_index:end_index]:
                matched_reasoning = matched_reasoning or activity.activity_type == "reasoning"
                preview = _compact_display_text(activity.content, limit)
                if preview:
                    previews[id(response)] = preview
                    break
        if id(response) in previews:
            continue
        response_end = _parse_iso_datetime(response.last_output_at)
        if response_end is not None:
            candidates = (
                tools_by_turn.get(response.turn_id, [])
                if response.turn_id
                else tool_rows
            )
            candidate_times = [item[0] for item in candidates]
            start_index = bisect_left(candidate_times, response_end - one_second)
            end_index = bisect_right(candidate_times, response_end + one_second)
            if start_index < end_index:
                previews[id(response)] = _compact_display_text(
                    candidates[start_index][2],
                    limit,
                )
                continue
        previews[id(response)] = (
            "Internal reasoning (content unavailable)" if matched_reasoning else ""
        )
    return previews


def _runtime_interval_preview(
    thread: CodexThreadMetrics,
    interval: RuntimeStateInterval,
    limit: int = 150,
) -> str:
    """Return bounded sanitized context for one heatmap runtime interval."""

    if interval.state == "model_inference":
        responses = [
            response
            for response in thread.responses
            if response.started_at
            and (response.last_output_at or response.completed_at)
            and _interval_overlap_ms(
                interval.started_at,
                interval.completed_at,
                response.started_at,
                response.last_output_at or response.completed_at,
            )
            > 0
        ]
        if responses:
            response = max(
                responses,
                key=lambda item: _interval_overlap_ms(
                    interval.started_at,
                    interval.completed_at,
                    item.started_at,
                    item.last_output_at or item.completed_at,
                ),
            )
            return _response_activity_preview(thread, response, limit)

    tools: list[tuple[int, str]] = []
    for tool in thread.tool_intervals:
        overlap = _interval_overlap_ms(
            interval.started_at,
            interval.completed_at,
            tool.started_at,
            tool.completed_at,
        )
        if overlap:
            detail = tool.argument_summary or tool.result_summary or tool.tool_name
            tools.append((overlap, _tool_activity_preview(tool.tool_name, detail, limit)))
    for call in thread.mcp_calls:
        overlap = _interval_overlap_ms(
            interval.started_at,
            interval.completed_at,
            call.started_at,
            call.completed_at,
        )
        if overlap:
            name = f"{call.server_name}.{call.tool_name}"
            detail = call.argument_summary or call.result_summary or name
            tools.append((overlap, f"{name}: {detail}"))
    return (
        _compact_display_text(max(tools, key=lambda item: item[0])[1], limit)
        if tools
        else ""
    )


def _overlap_sweep(
    intervals: list[tuple[int, RuntimeStateInterval, datetime, datetime]],
    events: list[tuple[datetime, datetime, object]],
) -> dict[int, object]:
    """Select the greatest-overlap event per interval without rescanning all events."""

    ordered_events = sorted(events, key=lambda item: item[0])
    if not ordered_events:
        return {}
    starts = [event[0] for event in ordered_events]
    prefix_latest_end: list[int] = []
    prefix_end_values: list[datetime] = []
    latest_index = 0
    for index, (_, event_end, _) in enumerate(ordered_events):
        if index == 0 or event_end > ordered_events[latest_index][1]:
            latest_index = index
        prefix_latest_end.append(latest_index)
        prefix_end_values.append(ordered_events[latest_index][1])

    tree_size = 1
    while tree_size < len(ordered_events):
        tree_size *= 2
    max_end_tree: list[datetime | None] = [None] * (tree_size * 2)
    for index, (_, event_end, _) in enumerate(ordered_events):
        max_end_tree[tree_size + index] = event_end
    for node in range(tree_size - 1, 0, -1):
        children = [value for value in max_end_tree[node * 2 : node * 2 + 2] if value]
        max_end_tree[node] = max(children) if children else None

    def first_ending_at_or_after(
        query_start: int,
        query_end: int,
        threshold: datetime,
        node: int = 1,
        node_start: int = 0,
        node_end: int | None = None,
    ) -> int | None:
        node_end = tree_size if node_end is None else node_end
        node_max = max_end_tree[node]
        if (
            node_end <= query_start
            or node_start >= query_end
            or node_max is None
            or node_max < threshold
        ):
            return None
        if node_end - node_start == 1:
            return node_start
        midpoint = (node_start + node_end) // 2
        left = first_ending_at_or_after(
            query_start,
            query_end,
            threshold,
            node * 2,
            node_start,
            midpoint,
        )
        return (
            left
            if left is not None
            else first_ending_at_or_after(
                query_start,
                query_end,
                threshold,
                node * 2 + 1,
                midpoint,
                node_end,
            )
        )

    duration_tree: list[tuple[timedelta, int, object] | None] = [None] * (
        tree_size * 2
    )

    def add_duration(index: int) -> None:
        event_start, event_end, value = ordered_events[index]
        node = tree_size + index
        duration_tree[node] = (event_end - event_start, -index, value)
        node //= 2
        while node:
            children = [value for value in duration_tree[node * 2 : node * 2 + 2] if value]
            duration_tree[node] = max(children, key=lambda item: item[:2]) if children else None
            node //= 2

    def longest_duration(query_start: int, query_end: int) -> tuple[timedelta, int, object] | None:
        left = tree_size + query_start
        right = tree_size + query_end
        best: tuple[timedelta, int, object] | None = None
        while left < right:
            if left % 2:
                candidate = duration_tree[left]
                if candidate is not None and (
                    best is None or candidate[:2] > best[:2]
                ):
                    best = candidate
                left += 1
            if right % 2:
                right -= 1
                candidate = duration_tree[right]
                if candidate is not None and (
                    best is None or candidate[:2] > best[:2]
                ):
                    best = candidate
            left //= 2
            right //= 2
        return best

    matches: dict[int, object] = {}
    events_by_end = sorted(range(len(ordered_events)), key=lambda index: ordered_events[index][1])
    end_cursor = 0
    for interval_index, _, interval_start, interval_end in sorted(
        intervals, key=lambda item: item[3]
    ):
        while (
            end_cursor < len(events_by_end)
            and ordered_events[events_by_end[end_cursor]][1] < interval_end
        ):
            add_duration(events_by_end[end_cursor])
            end_cursor += 1
        overlapping: list[tuple[timedelta, int, object]] = []
        before_or_at = bisect_right(starts, interval_start) - 1
        if before_or_at >= 0:
            latest_before = prefix_latest_end[before_or_at]
            if ordered_events[latest_before][1] >= interval_end:
                first_containing = bisect_left(
                    prefix_end_values,
                    interval_end,
                    0,
                    before_or_at + 1,
                )
                candidate = ordered_events[prefix_latest_end[first_containing]]
            else:
                first_containing = latest_before
            candidate = ordered_events[first_containing]
            if candidate[1] > interval_start:
                overlapping.append(
                    (
                        min(interval_end, candidate[1]) - interval_start,
                        -first_containing,
                        candidate[2],
                    )
                )
        inside_start = before_or_at + 1
        inside_end = bisect_left(starts, interval_end)
        spanning_index = first_ending_at_or_after(
            inside_start,
            inside_end,
            interval_end,
        )
        if spanning_index is not None:
            event_start, _, value = ordered_events[spanning_index]
            overlapping.append(
                (interval_end - event_start, -spanning_index, value)
            )
        contained = longest_duration(inside_start, inside_end)
        if contained is not None:
            overlapping.append(contained)
        if overlapping:
            matches[interval_index] = max(
                overlapping,
                key=lambda item: item[:2],
            )[2]
    return matches


def _runtime_thread_interval_previews(
    thread_index: int,
    thread_total: int,
    thread: CodexThreadMetrics,
    intervals: list[tuple[int, RuntimeStateInterval, datetime, datetime]],
    worker_progress: WorkerProgressCallback | None,
) -> dict[int, str]:
    worker = _current_worker_id()
    if worker_progress is not None:
        worker_progress(
            93,
            "Heatmap drilldown previews",
            f"Agent {thread_index:,} of {thread_total:,}: indexing events.",
            worker,
        )
    responses: list[tuple[datetime, datetime, object]] = []
    for response in thread.responses:
        started_at = _parse_iso_datetime(response.started_at)
        completed_at = _parse_iso_datetime(response.last_output_at or response.completed_at)
        if started_at is not None and completed_at is not None:
            responses.append((started_at, completed_at, response))
    tools: list[tuple[datetime, datetime, object]] = []
    for tool in thread.tool_intervals:
        started_at = _parse_iso_datetime(tool.started_at)
        completed_at = _parse_iso_datetime(tool.completed_at)
        if started_at is None or completed_at is None:
            continue
        detail = tool.argument_summary or tool.result_summary or tool.tool_name
        tools.append(
            (started_at, completed_at, _tool_activity_preview(tool.tool_name, detail))
        )
    for call in thread.mcp_calls:
        started_at = _parse_iso_datetime(call.started_at)
        completed_at = _parse_iso_datetime(call.completed_at)
        if started_at is None or completed_at is None:
            continue
        name = f"{call.server_name}.{call.tool_name}"
        detail = call.argument_summary or call.result_summary or name
        tools.append((started_at, completed_at, f"{name}: {detail}"))

    if worker_progress is not None:
        worker_progress(
            93,
            "Heatmap drilldown previews",
            f"Agent {thread_index:,} of {thread_total:,}: preparing response previews.",
            worker,
        )
    response_previews = _response_activity_previews(thread)
    if worker_progress is not None:
        worker_progress(
            93,
            "Heatmap drilldown previews",
            f"Agent {thread_index:,} of {thread_total:,}: matching periods.",
            worker,
        )
    inference_intervals = [item for item in intervals if item[1].state == "model_inference"]
    response_matches = _overlap_sweep(inference_intervals, responses)
    tool_matches = _overlap_sweep(intervals, tools)
    previews: dict[int, str] = {}
    for interval_index, _, _, _ in intervals:
        response = response_matches.get(interval_index)
        if isinstance(response, ResponseUsage):
            previews[interval_index] = response_previews.get(id(response), "")
            continue
        tool_preview = tool_matches.get(interval_index)
        if isinstance(tool_preview, str):
            previews[interval_index] = _compact_display_text(tool_preview, 150)
    if worker_progress is not None:
        worker_progress(
            93,
            "Heatmap drilldown previews",
            f"Agent {thread_index:,} of {thread_total:,}: {len(intervals):,} periods complete.",
            worker,
        )
    return previews


def _runtime_interval_previews(
    run: CodexRunMetrics,
    progress: ProgressCallback | None = None,
    worker_progress: WorkerProgressCallback | None = None,
    workers: int = 1,
) -> dict[int, str]:
    """Build heatmap previews using bounded per-agent overlap sweeps."""

    intervals_by_thread: dict[
        str, list[tuple[int, RuntimeStateInterval, datetime, datetime]]
    ] = {}
    for interval_index, interval in enumerate(run.runtime_intervals):
        if progress is not None and (
            interval_index == 0
            or interval_index + 1 == len(run.runtime_intervals)
            or interval_index % max(1, len(run.runtime_intervals) // 100) == 0
        ):
            progress(
                93,
                "Indexing heatmap intervals",
                f"Interval {interval_index + 1:,} of {len(run.runtime_intervals):,}.",
            )
        started_at = _parse_iso_datetime(interval.started_at)
        completed_at = _parse_iso_datetime(interval.completed_at)
        if started_at is None or completed_at is None:
            continue
        intervals_by_thread.setdefault(interval.thread_id, []).append(
            (interval_index, interval, started_at, completed_at)
        )

    threads_by_id = {thread.thread_id: thread for thread in run.threads}
    interval_threads = [
        (thread_id, intervals)
        for thread_id, intervals in intervals_by_thread.items()
        if thread_id in threads_by_id
    ]
    previews: dict[int, str] = {}
    worker_count = min(max(1, workers), max(1, len(interval_threads)))
    if worker_count == 1:
        for thread_index, (thread_id, intervals) in enumerate(interval_threads, start=1):
            previews.update(
                _runtime_thread_interval_previews(
                    thread_index,
                    len(interval_threads),
                    threads_by_id[thread_id],
                    intervals,
                    worker_progress,
                )
            )
            if progress is not None:
                progress(
                    93,
                    "Building heatmap drilldown previews",
                    f"Completed agent {thread_index:,} of {len(interval_threads):,}.",
                )
    else:
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="agent-report-worker",
        ) as executor:
            futures = [
                executor.submit(
                    _runtime_thread_interval_previews,
                    thread_index,
                    len(interval_threads),
                    threads_by_id[thread_id],
                    intervals,
                    worker_progress,
                )
                for thread_index, (thread_id, intervals) in enumerate(
                    interval_threads, start=1
                )
            ]
            for completed_count, future in enumerate(as_completed(futures), start=1):
                previews.update(future.result())
                if progress is not None:
                    progress(
                        93,
                        "Building heatmap drilldown previews",
                        f"Completed {completed_count:,} of {len(interval_threads):,} agents.",
                    )
    return previews


def _time_range_event_id(kind: str, *parts: object) -> str:
    """Return one deterministic opaque event identifier for a task snapshot."""

    identity = json.dumps([kind, *parts], ensure_ascii=False, separators=(",", ":"))
    return "evt_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _runtime_interval_event_id(
    interval: RuntimeStateInterval, interval_index: int
) -> str:
    return _time_range_event_id(
        "runtime_interval",
        interval_index,
        interval.thread_id,
        interval.turn_id,
        interval.state,
        interval.started_at,
        interval.completed_at,
    )


def _response_event_id(thread: CodexThreadMetrics, response: ResponseUsage) -> str:
    return _time_range_event_id(
        "model_response",
        thread.thread_id,
        response.turn_id,
        response.started_at,
        response.completed_at,
        response.source_path,
        response.source_ordinal,
    )


def _tool_event_id(thread: CodexThreadMetrics, tool: ToolInterval) -> str:
    return _time_range_event_id(
        "tool_call",
        thread.thread_id,
        tool.turn_id,
        tool.started_at,
        tool.completed_at,
        tool.source_path,
        tool.source_start_ordinal,
    )


def _mcp_event_id(thread: CodexThreadMetrics, call: McpCallInterval) -> str:
    return _time_range_event_id(
        "mcp_call",
        thread.thread_id,
        call.turn_id,
        call.started_at,
        call.completed_at,
        call.source_path,
        call.source_ordinal,
    )


def _turn_detail_targets(run: CodexRunMetrics) -> dict[tuple[str, str], str]:
    """Return stable turn-popup IDs shared by the timeline and heatmap."""

    return {
        (thread.thread_id, turn.turn_id): (
            f"turn-tool-call-list-{thread_index}-{turn_index}"
        )
        for thread_index, thread in enumerate(run.threads, start=1)
        for turn_index, turn in enumerate(thread.turns, start=1)
    }


def _runtime_interval_event_target(
    thread: CodexThreadMetrics | None,
    interval: RuntimeStateInterval,
) -> str:
    """Return the closest concrete turn-row target for one runtime interval."""

    if thread is None or not interval.turn_id:
        return ""
    candidates: list[tuple[int, str]] = []
    if interval.state == "model_inference":
        for response in thread.responses:
            if response.turn_id != interval.turn_id:
                continue
            overlap = _interval_overlap_ms(
                interval.started_at,
                interval.completed_at,
                response.started_at,
                response.last_output_at or response.completed_at,
            )
            if overlap:
                candidates.append((overlap, _response_event_id(thread, response)))
    else:
        for tool in thread.tool_intervals:
            if tool.turn_id != interval.turn_id:
                continue
            overlap = _interval_overlap_ms(
                interval.started_at,
                interval.completed_at,
                tool.started_at,
                tool.completed_at,
            )
            if overlap:
                candidates.append((overlap, _tool_event_id(thread, tool)))
        for call in thread.mcp_calls:
            if call.turn_id != interval.turn_id:
                continue
            overlap = _interval_overlap_ms(
                interval.started_at,
                interval.completed_at,
                call.started_at,
                call.completed_at,
            )
            if overlap:
                candidates.append((overlap, _mcp_event_id(thread, call)))
    return max(candidates, default=(0, ""), key=lambda item: item[0])[1]


def _execution_heatmap_payload(
    run: CodexRunMetrics,
    *,
    include_previews: bool = True,
    progress: ProgressCallback | None = None,
    worker_progress: WorkerProgressCallback | None = None,
    workers: int = 1,
) -> dict[str, object]:
    """Return bounded runtime and response evidence for the offline heatmap."""

    state_labels = {
        "model_inference": "Model inference",
        "tool_execution": "Tool execution",
        "test_process": "Build / Test",
        "agent_wait": "Waiting for agent",
        "user_pause": "User pause",
        "watchdog": "Watchdog",
        "approval_infrastructure": "Approval / infrastructure",
        "unattributed": "Unattributed",
    }
    present_states = {interval.state for interval in run.runtime_intervals}
    states = [
        {"id": state, "label": label}
        for state, label in state_labels.items()
        if state in present_states
    ]
    states.extend(
        {"id": state, "label": state.replace("_", " ").title()}
        for state in sorted(present_states - set(state_labels))
    )
    agents = [
        {"id": thread.thread_id, "label": _heatmap_agent_label(thread)}
        for thread in run.threads
    ]
    threads_by_id = {thread.thread_id: thread for thread in run.threads}
    turn_targets = _turn_detail_targets(run)
    intervals = []
    interval_previews = (
        _runtime_interval_previews(
            run,
            progress=progress,
            worker_progress=worker_progress,
            workers=workers,
        )
        if include_previews
        else {}
    )
    for interval_index, interval in enumerate(run.runtime_intervals):
        if progress is not None and (
            interval_index == 0
            or interval_index + 1 == len(run.runtime_intervals)
            or interval_index % max(1, len(run.runtime_intervals) // 100) == 0
        ):
            progress(
                93,
                "Serializing heatmap intervals",
                f"Interval {interval_index + 1:,} of {len(run.runtime_intervals):,}.",
            )
        if not interval.started_at or not interval.completed_at:
            continue
        thread = threads_by_id.get(interval.thread_id)
        intervals.append(
            {
                "event_id": _runtime_interval_event_id(interval, interval_index),
                "state": interval.state,
                "thread_id": interval.thread_id,
                "turn_id": interval.turn_id or "",
                "turn_target": turn_targets.get(
                    (interval.thread_id, interval.turn_id or ""), ""
                ),
                "event_target": _runtime_interval_event_target(thread, interval),
                "started_at": interval.started_at,
                "ended_at": interval.completed_at,
                "duration_ms": interval.duration_ms,
                "confidence": interval.attribution_confidence,
                "detail": _compact_display_text(interval.detail, 160),
                "preview": interval_previews.get(interval_index, ""),
            }
        )
    models = []
    model_ids: set[str] = set()
    responses = []
    for thread_index, thread in enumerate(run.threads, start=1):
        if progress is not None and (
            thread_index == 1
            or thread_index == len(run.threads)
            or thread_index % max(1, len(run.threads) // 100) == 0
        ):
            progress(
                94,
                "Serializing heatmap responses",
                f"Agent {thread_index:,} of {len(run.threads):,}.",
            )
        response_previews = (
            _response_activity_previews(thread) if include_previews else {}
        )
        fallback_model = (
            thread.model
            if thread.model and not thread.model.startswith("mixed (")
            else "Unknown model"
        )
        for response in thread.responses:
            usage = _inference_call_usage(response)
            response_cost = _cost_for_response(thread, response)
            response_effort = _response_effort(thread, response)
            response_model = response.model or fallback_model
            model_identity = json.dumps(
                [response_model, response_effort],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            model_id = "model_" + hashlib.sha256(
                model_identity.encode("utf-8")
            ).hexdigest()[:16]
            if model_id not in model_ids:
                model_ids.add(model_id)
                models.append(
                    {
                        "id": model_id,
                        "label": response_model
                        + (f" · effort {response_effort}" if response_effort else ""),
                    }
                )
            responses.append(
                {
                    "event_id": _response_event_id(thread, response),
                    "thread_id": thread.thread_id,
                    "turn_id": response.turn_id or "",
                    "turn_target": turn_targets.get(
                        (thread.thread_id, response.turn_id or ""), ""
                    ),
                    "event_target": _response_event_id(thread, response),
                    "model": response_model,
                    "model_id": model_id,
                    "effort": response_effort,
                    "started_at": response.started_at or response.event_timestamp,
                    "completed_at": response.completed_at or response.event_timestamp,
                    "duration_ms": response.duration_ms,
                    "confidence": response.timing_confidence,
                    "cost_usd": response_cost.total_cost or 0,
                    "preview": response_previews.get(id(response), ""),
                    "usage": {
                        "uncached_input_tokens": usage.direct_input_tokens,
                        "cached_input_tokens": usage.cached_input_tokens,
                        "output_tokens": max(
                            0, usage.output_tokens - usage.reasoning_tokens
                        ),
                        "reasoning_tokens": usage.reasoning_tokens,
                        "processed_tokens": usage.processed_tokens,
                        "context_tokens": response.context_total_tokens,
                    },
                }
            )
    tools = [
        {
            "thread_id": thread.thread_id,
            "turn_id": tool.turn_id or "",
            "turn_target": turn_targets.get(
                (thread.thread_id, tool.turn_id or ""), ""
            ),
            "event_target": _tool_event_id(thread, tool),
            "tool_name": tool.tool_name,
            "started_at": tool.started_at,
            "completed_at": tool.completed_at,
            "duration_ms": tool.duration_ms,
            "preview": (
                _tool_activity_preview(
                    tool.tool_name,
                    tool.argument_summary or tool.result_summary or tool.tool_name,
                )
                if include_previews
                else ""
            ),
        }
        for thread in run.threads
        for tool in thread.tool_intervals
        if tool.started_at and tool.completed_at
    ]
    return {
        "started_at": run.wall_started_at,
        "ended_at": run.wall_ended_at,
        "context_capacity": max(
            (
                response.context_capacity
                for thread in run.threads
                for response in thread.responses
            ),
            default=run.context_summary.capacity,
        ),
        "states": states,
        "agents": agents,
        "models": models,
        "intervals": intervals,
        "responses": responses,
        "tools": tools,
    }


_TIME_RANGE_MEASURES = {
    "wall_time": ("Wall time", "milliseconds"),
    "uncached_input_tokens": ("Uncached input", "tokens"),
    "cached_input_tokens": ("Cached input", "tokens"),
    "output_tokens": ("Output", "tokens"),
    "reasoning_tokens": ("Reasoning", "tokens"),
    "cost_usd": ("Cost", "USD"),
}
_TIME_RANGE_BUCKET_MINUTES = {1, 5, 15, 30, 60}
_TIME_RANGE_EVENT_LIMIT = 1_000
_EVENT_ACTIVITY_LIMIT = 10
_EVENT_ACTIVITY_TEXT_LIMIT = 1_000


def query_codex_run_time_range(
    run: CodexRunMetrics,
    *,
    from_time: str | None = None,
    to_time: str | None = None,
    bucket_minutes: int = 5,
    measure: str = "wall_time",
    include_events: bool = False,
) -> dict[str, object]:
    """Return bucketed execution metrics and optional bounded event evidence."""

    if bucket_minutes not in _TIME_RANGE_BUCKET_MINUTES:
        raise ValueError("bucket_minutes must be one of 1, 5, 15, 30, or 60")
    if measure not in _TIME_RANGE_MEASURES:
        raise ValueError(
            "measure must be wall_time, uncached_input_tokens, "
            "cached_input_tokens, output_tokens, reasoning_tokens, or cost_usd"
        )
    run_start = _parse_iso_datetime(run.wall_started_at)
    run_end = _parse_iso_datetime(run.wall_ended_at)
    if run_start is None or run_end is None or run_start >= run_end:
        raise ValueError("task runtime range is unavailable")
    query_start = _parse_iso_datetime(from_time) if from_time else run_start
    query_end = _parse_iso_datetime(to_time) if to_time else run_end
    if query_start is None:
        raise ValueError("from_time must be an ISO 8601 timestamp")
    if query_end is None:
        raise ValueError("to_time must be an ISO 8601 timestamp")
    if query_start >= query_end:
        raise ValueError("from_time must be earlier than to_time")
    requested_start = query_start
    requested_end = query_end
    query_start = max(query_start, run_start)
    query_end = min(query_end, run_end)
    if query_start >= query_end:
        raise ValueError("requested time range does not overlap the task runtime")

    if measure == "wall_time":
        payload = _execution_heatmap_payload(run, include_previews=include_events)
    else:
        agents = [
            {"id": thread.thread_id, "label": _heatmap_agent_label(thread)}
            for thread in run.threads
        ]
        responses: list[dict[str, object]] = []
        for thread in run.threads:
            response_previews = (
                _response_activity_previews(thread) if include_events else {}
            )
            fallback_model = (
                thread.model
                if thread.model and not thread.model.startswith("mixed (")
                else "Unknown model"
            )
            for response in thread.responses:
                usage = _inference_call_usage(response)
                response_effort = _response_effort(thread, response)
                responses.append(
                    {
                        "event_id": (
                            _response_event_id(thread, response)
                            if include_events
                            else ""
                        ),
                        "thread_id": thread.thread_id,
                        "turn_id": response.turn_id or "",
                        "model": response.model or fallback_model,
                        "effort": response_effort,
                        "started_at": response.started_at or response.event_timestamp,
                        "completed_at": response.completed_at or response.event_timestamp,
                        "duration_ms": response.duration_ms,
                        "cost_usd": (
                            _cost_for_response(thread, response).total_cost or 0
                            if measure == "cost_usd"
                            else 0
                        ),
                        "preview": (
                            response_previews.get(id(response), "")
                        ),
                        "usage": {
                            "uncached_input_tokens": usage.direct_input_tokens,
                            "cached_input_tokens": usage.cached_input_tokens,
                            "output_tokens": max(
                                0, usage.output_tokens - usage.reasoning_tokens
                            ),
                            "reasoning_tokens": usage.reasoning_tokens,
                        },
                    }
                )
        payload = {"agents": agents, "responses": responses}
    bucket_width = timedelta(minutes=bucket_minutes)
    buckets: list[tuple[datetime, datetime]] = []
    bucket_start = query_start
    while bucket_start < query_end:
        bucket_end = min(query_end, bucket_start + bucket_width)
        buckets.append((bucket_start, bucket_end))
        bucket_start = bucket_end

    if measure == "wall_time":
        rows = [
            {"id": state["id"], "label": state["label"], "kind": "activity"}
            for state in payload["states"]
        ]
    else:
        rows = [
            {"id": agent["id"], "label": agent["label"], "kind": "agent"}
            for agent in payload["agents"]
        ]

    def interval_value(row_id: str, start: datetime, end: datetime) -> int:
        segments: list[tuple[datetime, datetime]] = []
        for interval in payload["intervals"]:
            if interval["state"] != row_id:
                continue
            interval_start = _parse_iso_datetime(interval["started_at"])
            interval_end = _parse_iso_datetime(interval["ended_at"])
            if interval_start is None or interval_end is None:
                continue
            overlap_start = max(start, interval_start)
            overlap_end = min(end, interval_end)
            if overlap_start < overlap_end:
                segments.append((overlap_start, overlap_end))
        if not segments:
            return 0
        segments.sort()
        merged: list[tuple[datetime, datetime]] = [segments[0]]
        for segment_start, segment_end in segments[1:]:
            previous_start, previous_end = merged[-1]
            if segment_start <= previous_end:
                merged[-1] = (previous_start, max(previous_end, segment_end))
            else:
                merged.append((segment_start, segment_end))
        return round(sum((end - start).total_seconds() * 1000 for start, end in merged))

    def response_time(response: dict[str, object]) -> datetime | None:
        return _parse_iso_datetime(
            str(response.get("completed_at") or response.get("started_at") or "")
        )

    def response_value(response: dict[str, object]) -> int | float:
        if measure == "cost_usd":
            return float(response["cost_usd"])
        return int(response["usage"][measure])

    series = []
    for row in rows:
        values = []
        for start, end in buckets:
            if measure == "wall_time":
                values.append(interval_value(str(row["id"]), start, end))
            else:
                values.append(
                    sum(
                        response_value(response)
                        for response in payload["responses"]
                        if response["thread_id"] == row["id"]
                        and (occurred_at := response_time(response)) is not None
                        and start <= occurred_at < end
                    )
                )
        series.append({**row, "values": values})

    label, unit = _TIME_RANGE_MEASURES[measure]
    result: dict[str, object] = {
        "measure": {"id": measure, "label": label, "unit": unit},
        "bucket_minutes": bucket_minutes,
        "range": {
            "from": query_start.isoformat(),
            "to": query_end.isoformat(),
            "to_exclusive": True,
        },
        "requested_range": {
            "from": requested_start.isoformat(),
            "to": requested_end.isoformat(),
            "to_exclusive": True,
        },
        "run_range": {
            "from": run.wall_started_at,
            "to": run.wall_ended_at,
            "to_exclusive": True,
        },
        "buckets": [
            {"from": start.isoformat(), "to": end.isoformat()} for start, end in buckets
        ],
        "series": series,
    }
    if not include_events:
        return result

    events: list[dict[str, object]] = []
    if measure == "wall_time":
        labels = {str(row["id"]): str(row["label"]) for row in rows}
        for interval in payload["intervals"]:
            interval_start = _parse_iso_datetime(interval["started_at"])
            interval_end = _parse_iso_datetime(interval["ended_at"])
            if interval_start is None or interval_end is None:
                continue
            overlap_start = max(query_start, interval_start)
            overlap_end = min(query_end, interval_end)
            if overlap_start >= overlap_end:
                continue
            events.append(
                {
                    "event_id": interval["event_id"],
                    "series_id": interval["state"],
                    "series_label": labels.get(interval["state"], interval["state"]),
                    "measure": measure,
                    "value": round((overlap_end - overlap_start).total_seconds() * 1000),
                    "started_at": overlap_start.isoformat(),
                    "ended_at": overlap_end.isoformat(),
                    "thread_id": interval["thread_id"],
                    "turn_id": interval["turn_id"],
                    "label": interval["detail"] or labels.get(interval["state"], interval["state"]),
                    "preview": interval["preview"],
                }
            )
    else:
        labels = {str(row["id"]): str(row["label"]) for row in rows}
        for response in payload["responses"]:
            occurred_at = response_time(response)
            if occurred_at is None or not query_start <= occurred_at < query_end:
                continue
            model_label = response["model"] or "Model response"
            if response["effort"]:
                model_label += f" · effort {response['effort']}"
            events.append(
                {
                    "event_id": response["event_id"],
                    "series_id": response["thread_id"],
                    "series_label": labels.get(response["thread_id"], response["thread_id"]),
                    "measure": measure,
                    "value": response_value(response),
                    "occurred_at": occurred_at.isoformat(),
                    "started_at": response["started_at"],
                    "completed_at": response["completed_at"],
                    "duration_ms": response["duration_ms"],
                    "turn_id": response["turn_id"],
                    "label": model_label,
                    "preview": response["preview"],
                }
            )
    events.sort(key=lambda event: str(event.get("started_at") or event.get("occurred_at")))
    result["event_count"] = len(events)
    result["events_truncated"] = len(events) > _TIME_RANGE_EVENT_LIMIT
    result["events"] = events[:_TIME_RANGE_EVENT_LIMIT]
    return result


def _event_activities(
    thread: CodexThreadMetrics,
    turn_id: str | None,
    started_at: str,
    ended_at: str,
) -> list[dict[str, object]]:
    """Return bounded privacy-safe narrative context inside one event."""

    start = _parse_iso_datetime(started_at)
    end = _parse_iso_datetime(ended_at)
    if start is None or end is None:
        return []
    activities = []
    for activity in thread.activities:
        occurred_at = _parse_iso_datetime(activity.event_timestamp)
        if occurred_at is None or occurred_at < start or occurred_at > end:
            continue
        if turn_id and activity.turn_id != turn_id:
            continue
        activities.append(
            {
                "type": activity.activity_type,
                "occurred_at": activity.event_timestamp,
                "summary": _compact_display_text(activity.summary, _EVENT_ACTIVITY_TEXT_LIMIT),
                "content": _compact_display_text(activity.content, _EVENT_ACTIVITY_TEXT_LIMIT),
                "model": activity.model,
            }
        )
    return activities[:_EVENT_ACTIVITY_LIMIT]


def _event_tool_context(
    thread: CodexThreadMetrics,
    started_at: str,
    ended_at: str,
) -> dict[str, object] | None:
    """Return the strongest overlapping privacy-safe tool record."""

    candidates: list[tuple[int, str, ToolInterval | McpCallInterval]] = []
    for tool in thread.tool_intervals:
        overlap = _interval_overlap_ms(
            started_at, ended_at, tool.started_at, tool.completed_at
        )
        if overlap:
            candidates.append((overlap, "tool", tool))
    for call in thread.mcp_calls:
        overlap = _interval_overlap_ms(
            started_at, ended_at, call.started_at, call.completed_at
        )
        if overlap:
            candidates.append((overlap, "mcp", call))
    if not candidates:
        return None
    _, kind, record = max(candidates, key=lambda item: item[0])
    if kind == "tool" and isinstance(record, ToolInterval):
        return {
            "kind": "tool",
            "tool_name": record.tool_name,
            "started_at": record.started_at,
            "ended_at": record.completed_at,
            "duration_ms": record.duration_ms,
            "argument_summary": record.argument_summary,
            "argument_content": record.argument_content,
            "result_summary": record.result_summary,
            "result_content": record.result_content,
            "model": record.model,
        }
    if isinstance(record, McpCallInterval):
        return {
            "kind": "mcp",
            "server_name": record.server_name,
            "tool_name": record.tool_name,
            "call_id": record.call_id,
            "started_at": record.started_at,
            "ended_at": record.completed_at,
            "duration_ms": record.duration_ms,
            "succeeded": record.succeeded,
            "argument_summary": record.argument_summary,
            "argument_content": record.argument_content,
            "result_summary": record.result_summary,
            "result_content": record.result_content,
            "model": record.model,
        }
    return None


def get_codex_run_event_details(
    run: CodexRunMetrics, event_id: str
) -> dict[str, object] | None:
    """Resolve one opaque event ID to its full privacy-safe task context."""

    payload = _execution_heatmap_payload(run)
    threads = {thread.thread_id: thread for thread in run.threads}
    normalized_intervals = {
        interval["event_id"]: interval for interval in payload["intervals"]
    }
    for interval_index, interval in enumerate(run.runtime_intervals):
        if _runtime_interval_event_id(interval, interval_index) != event_id:
            continue
        normalized = normalized_intervals[event_id]
        thread = threads.get(interval.thread_id)
        details: dict[str, object] = {
            "event_id": event_id,
            "kind": "runtime_interval",
            "state": interval.state,
            "thread_id": interval.thread_id,
            "turn_id": interval.turn_id or "",
            "started_at": interval.started_at,
            "ended_at": interval.completed_at,
            "duration_ms": interval.duration_ms,
            "detail": interval.detail,
            "preview": normalized["preview"],
            "derivation_method": interval.derivation_method,
            "attribution_confidence": interval.attribution_confidence,
        }
        if thread is not None:
            details["activities"] = _event_activities(
                thread,
                interval.turn_id,
                interval.started_at,
                interval.completed_at,
            )
            tool_context = _event_tool_context(
                thread, interval.started_at, interval.completed_at
            )
            if tool_context is not None:
                details["tool_context"] = tool_context
        return details

    normalized_responses = {
        response["event_id"]: response for response in payload["responses"]
    }
    for thread in run.threads:
        for response in thread.responses:
            if _response_event_id(thread, response) != event_id:
                continue
            normalized = normalized_responses[event_id]
            return {
                "event_id": event_id,
                "kind": "model_response",
                "thread_id": thread.thread_id,
                "turn_id": response.turn_id or "",
                "started_at": normalized["started_at"],
                "completed_at": normalized["completed_at"],
                "duration_ms": response.duration_ms,
                "model": response.model,
                "effort": normalized["effort"],
                "usage": normalized["usage"],
                "cost_usd": normalized["cost_usd"],
                "preview": normalized["preview"],
                "timing_method": response.timing_method,
                "timing_confidence": response.timing_confidence,
                "activities": _event_activities(
                    thread,
                    response.turn_id,
                    str(normalized["started_at"]),
                    str(normalized["completed_at"]),
                ),
            }
    return None


def _render_execution_heatmap(
    run: CodexRunMetrics,
    progress: ProgressCallback | None = None,
    worker_progress: WorkerProgressCallback | None = None,
    workers: int = 1,
) -> str:
    """Render controls and bounded data for an offline execution heatmap."""

    if not run.runtime_intervals:
        return ""
    heatmap_data = _execution_heatmap_payload(
        run,
        progress=progress,
        worker_progress=worker_progress,
        workers=workers,
    )
    if progress is not None:
        progress(
            95,
            "Encoding heatmap data",
            "Encoding period measures and drilldown events as offline JSON.",
        )
    payload = json.dumps(
        heatmap_data,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    return (
        '<section id="execution-heatmap" class="metric-view">'
        '<div class="agents-heading"><h2>Execution heatmap</h2></div>'
        '<p class="execution-note">Compare time or response-attributed tokens across the run. '
        'Single-click a cell to inspect its events. Double-click to drill down; right-click to step back.</p>'
        '<div class="heatmap-controls">'
        '<div class="heatmap-control"><label for="heatmap-metric">Measure</label>'
        '<select id="heatmap-metric">'
        '<option value="wall_time">Wall time</option>'
        '<option value="tokens" selected>Tokens</option>'
        '<option value="models">Models</option>'
        '</select></div>'
        '<fieldset class="heatmap-granularity"><legend>Period</legend>'
        '<button type="button" data-heatmap-minutes="1">1 min</button>'
        '<button type="button" data-heatmap-minutes="5" aria-pressed="true">5 min</button>'
        '<button type="button" data-heatmap-minutes="15">15 min</button>'
        '<button type="button" data-heatmap-minutes="30">30 min</button>'
        '<button type="button" data-heatmap-minutes="60">1 hour</button>'
        '<button type="button" data-heatmap-minutes="360">6 hours</button>'
        '<button type="button" data-heatmap-minutes="1440">1 day</button>'
        '</fieldset><output class="heatmap-status" data-heatmap-status></output></div>'
        '<p class="execution-note">Cost follows the report\'s recorded or API-equivalent estimate method.</p>'
        '<div class="heatmap-scroll-frame">'
        '<button type="button" class="heatmap-scroll-button" data-heatmap-scroll="left" aria-label="Scroll heatmap left">←</button>'
        '<div class="heatmap-scroll" tabindex="0" aria-label="Scrollable execution heatmap">'
        '<div class="heatmap-grid" data-heatmap-grid></div>'
        '<p class="heatmap-empty" data-heatmap-empty hidden>No heatmap evidence is available.</p>'
        '</div><button type="button" class="heatmap-scroll-button" data-heatmap-scroll="right" aria-label="Scroll heatmap right">→</button>'
        '</div><div class="heatmap-drilldown-frame">'
        '<button type="button" class="heatmap-scroll-button" data-heatmap-drilldown-step="-1" aria-label="Previous drilldown period" disabled>←</button>'
        '<div class="heatmap-drilldown">'
        '<h3 id="heatmap-drilldown-title">Select a heatmap cell</h3>'
        '<p class="heatmap-drilldown-summary" data-heatmap-drilldown-summary aria-live="polite">'
        'Choose a cell to inspect its events.</p>'
        '<nav class="heatmap-drilldown-path" data-heatmap-drilldown-path aria-label="Drilldown path"></nav>'
        '<ol class="heatmap-event-list" data-heatmap-event-list></ol></div>'
        '<button type="button" class="heatmap-scroll-button" data-heatmap-drilldown-step="1" aria-label="Next drilldown period" disabled>→</button></div>'
        f'<script type="application/json" id="execution-heatmap-data">{payload}</script>'
        '</section>'
    )


def render_codex_rollout_html(
    run: CodexRunMetrics,
    formatter_config: ToolFormatterConfig | None = None,
    *,
    nav_links: list[tuple[str, str]] | None = None,
    page_title: str | None = None,
    page_subtitle: str = "",
    page_action_links: list[tuple[str, str]] | None = None,
    progress: ProgressCallback | None = None,
    worker_progress: WorkerProgressCallback | None = None,
    workers: int = 1,
) -> str:
    """Render execution detail with optional navigation to an owning catalog."""
    if progress is not None:
        progress(80, "Rendering report summary", "Preparing headline metrics and agent inventory.")
    formatter_config = formatter_config or _load_tool_formatter_config()
    nav_html = ""
    if nav_links:
        nav_html = '<nav class="report-nav" aria-label="Breadcrumb">' + " › ".join(
            f'<a href="{_escape_html(href)}">{_escape_html(label)}</a>'
            for label, href in nav_links
        ) + "</nav>"
    turn_count = sum(len(thread.turns) for thread in run.threads)
    unique_turn_count = len(
        {turn.turn_id for thread in run.threads for turn in thread.turns}
    )
    response_count = sum(len(thread.responses) for thread in run.threads)
    tool_count = sum(len(thread.tool_intervals) for thread in run.threads)
    mcp_call_count = sum(len(thread.mcp_calls) for thread in run.threads)
    is_junie = run.runtime.lower() == "junie"
    show_cache_write = _reports_cache_write_tokens(run)
    turn_singular = "task span" if is_junie else "turn"
    turn_plural = "task spans" if is_junie else "turns"
    turn_column_label = "Task spans" if is_junie else "Turns"
    agent_activity_heading = (
        f'{turn_column_label}<br><span class="column-detail">(Tools)</span>'
        if is_junie
        else f'{turn_column_label}<br><span class="column-detail">(Tools/MCP)</span>'
    )
    agent_time_heading = (
        'Agent time<br><span class="column-detail">(Cost)</span>'
    )
    turn_activity_label = "Task span activity" if is_junie else "Turn activity"
    turn_id_label = "Task ID" if is_junie else "Turn"
    activity_metric_cards = (
        f'<div class="metric"><div class="label">User tasks</div><div class="value">{unique_turn_count:,}</div></div>'
        f'<div class="metric"><div class="label">Agent task spans</div><div class="value">{turn_count:,}</div></div>'
        f'<div class="metric"><div class="label">Model responses</div><div class="value">{response_count:,}</div></div>'
        if is_junie
        else (
            f'<div class="metric"><div class="label">Turns</div><div class="value">{turn_count:,}</div></div>'
            f'<div class="metric"><div class="label">Model responses</div><div class="value">{response_count:,}</div></div>'
        )
    )
    mcp_metric_card = (
        ""
        if is_junie
        else (
            '<div class="metric"><div class="label">MCP calls</div>'
            f'<div class="value">{mcp_call_count:,}</div></div>'
        )
    )
    composition_total = run.usage_totals.processed_tokens or 1
    visible_output_tokens = max(
        0, run.usage_totals.output_tokens - run.usage_totals.reasoning_tokens
    )
    fresh_width = run.usage_totals.direct_input_tokens / composition_total * 100
    cached_width = run.usage_totals.cached_input_tokens / composition_total * 100
    cache_write_width = (
        run.usage_totals.cache_create_input_tokens / composition_total * 100
    )
    output_width = visible_output_tokens / composition_total * 100
    reasoning_width = run.usage_totals.reasoning_tokens / composition_total * 100
    output_segment = (
        '<span class="token-segment output" '
        f'style="width:{output_width:.3f}%"></span>'
        if visible_output_tokens
        else ""
    )
    reasoning_segment = (
        '<span class="token-segment reasoning" '
        f'style="width:{reasoning_width:.3f}%"></span>'
        if run.usage_totals.reasoning_tokens
        else ""
    )
    cache_write_segment = (
        '<span class="token-segment cache-write" '
        f'style="width:{cache_write_width:.3f}%"></span>'
        if show_cache_write and run.usage_totals.cache_create_input_tokens
        else ""
    )
    cache_write_legend = (
        ' · <span class="composition-cache-write">Cache write '
        f'{run.usage_totals.cache_create_input_tokens:,}</span>'
        if show_cache_write
        else ""
    )
    agent_rows: list[tuple[str, str]] = []
    agent_detail_ids: dict[str, str] = {}
    inventory_threads = _agent_inventory_threads(run)
    for agent_index, (thread, agent_depth) in enumerate(inventory_threads, start=1):
        if progress is not None and (
            agent_index == 1
            or agent_index == len(inventory_threads)
            or agent_index % max(1, len(inventory_threads) // 100) == 0
        ):
            progress(
                80 + round(agent_index / max(1, len(inventory_threads)) * 3),
                "Rendering agent inventory",
                f"Agent {agent_index:,} of {len(inventory_threads):,}.",
            )
        agent_detail_id = f"agent-detail-{agent_index}"
        agent_detail_ids[thread.thread_id] = agent_detail_id
        agent_time_ms = sum(turn.duration_ms for turn in thread.turns)
        agent_cost = _cost_for_thread_usage(thread, thread.token_totals)
        run_share = thread.token_totals.processed_tokens / composition_total * 100
        skills_used_html = _agent_skills_html(thread.skills_used)
        activity_detail = (
            f"({len(thread.tool_intervals):,})"
            if is_junie
            else f"({len(thread.tool_intervals):,}/{len(thread.mcp_calls):,})"
        )
        hierarchy_label = (
            "Top-level assignment."
            if agent_depth == 0
            else f"Nested assignment, depth {agent_depth}."
        )
        agent_timeline_intervals = [
            (turn.started_at, turn.completed_at or thread.last_observed_at)
            for turn in thread.turns
            if turn.started_at
        ]
        if not agent_timeline_intervals:
            agent_timeline_intervals = [(thread.started_at, thread.last_observed_at)]
        agent_timeline_bars = "".join(
            '<span class="timeline-bar agent-timeline-bar" '
            f'style="{_timeline_style(run, started_at, ended_at)}"></span>'
            for started_at, ended_at in agent_timeline_intervals
        )
        timeline_label = (
            f"{_agent_assignment_label(thread)} turn activity · "
            f"{_timestamp_offset_label(run, agent_timeline_intervals[0][0])}"
        )
        effort_html = (
            f' · <span class="effort-level">effort {_escape_html(thread.effort)}</span>'
            if thread.effort
            else ""
        )
        model_metadata = (
            '<span class="agent-model-metadata">'
            f'<code class="model-name">{_escape_html(thread.model or "—")}</code>'
            f"{effort_html}</span>"
        )
        agent_title_html = _clamped_agent_title_html(thread)
        agent_rows.append((
            thread.thread_id,
            f'<tr class="agent-summary-row" data-agent-detail="{agent_detail_id}">'
            f'<td class="agent-assignment-cell" data-depth="{agent_depth}" style="--agent-depth:{agent_depth}">'
            f'<span class="visually-hidden">{hierarchy_label}</span>'
            '<div class="agent-assignment-line">'
            '<button type="button" class="agent-row-toggle" aria-expanded="false" '
            f'aria-controls="{agent_detail_id}" aria-label="Toggle details for {_escape_html_attribute(_agent_assignment_label(thread))}">'
            '<span class="agent-row-toggle-icon" aria-hidden="true"></span></button>'
            '<div class="agent-assignment">'
            '<div class="agent-assignment-heading">'
            f"{agent_title_html}"
            f'<span class="state state-{_escape_html(thread.terminal_state)}">{_escape_html(thread.terminal_state)}</span>'
            f"{model_metadata}</div></div></div></td>"
            f'<td class="agent-skills-cell">{skills_used_html}</td>'
            '<td class="agent-activity-cell">'
            f'<span class="cell-primary">{len(thread.turns):,}</span>'
            f'<span class="cell-secondary">{activity_detail}</span></td>'
            '<td class="agent-time-cell">'
            f'<span class="cell-primary">{_format_ms(agent_time_ms)}</span>'
            f'<span class="cell-secondary">({_escape_html(_compact_cost_summary(agent_cost))})</span></td>'
            '<td class="agent-processed-cell">'
            f'<span class="cell-primary">{_format_compact_count(thread.token_totals.processed_tokens)}</span>'
            f'<span class="cell-secondary">({run_share:.1f}%)</span></td>'
            '<td class="agent-timeline-cell">'
            '<span class="timeline-track agent-timeline-track" role="img" '
            f'aria-label="{_escape_html(timeline_label)}">'
            f"{agent_timeline_bars}"
            "</span></td>"
            "</tr>",
        ))
    if progress is not None:
        progress(83, "Rendering agent details", "Building expandable agent and turn tables.")
    thread_details: dict[str, str] = {}
    tool_call_overlays = []
    turn_detail_overlays = []
    for thread_index, thread in enumerate(run.threads, start=1):
        if progress is not None and (
            thread_index == 1
            or thread_index == len(run.threads)
            or thread_index % max(1, len(run.threads) // 100) == 0
        ):
            progress(
                83 + round(thread_index / max(1, len(run.threads)) * 4),
                "Rendering agent and turn tables",
                f"Agent {thread_index:,} of {len(run.threads):,}.",
            )
        tool_call_overlay_id = f"turn-tool-call-list-{thread_index}"
        agent_assignment = _agent_assignment(thread)
        work_units = {turn.work_unit_id or "unattributed" for turn in thread.turns}
        show_work_unit = len(work_units) > 1
        show_activity = any(turn.activity for turn in thread.turns)
        turn_rows = []
        thread_tool_rows = []
        for turn_index, turn in enumerate(thread.turns, start=1):
            tools = [tool for tool in thread.tool_intervals if tool.turn_id == turn.turn_id]
            mcp_calls = [call for call in thread.mcp_calls if call.turn_id == turn.turn_id]
            tool_names, tool_total = _tool_activity_summary(tools)
            mcp_names, mcp_total = _mcp_activity_summary(mcp_calls)
            turn_cost = _cost_for_turn(thread, turn)
            turn_detail_overlay_id = f"{tool_call_overlay_id}-{turn_index}"
            turn_link = (
                f'<a class="drilldown-link" href="#{turn_detail_overlay_id}" '
                'data-turn-detail-link data-return-target="#timeline">'
                f"<code>{_escape_html(turn.turn_id)}</code></a>"
            )
            turn_state_badge = (
                f'<span class="state state-{_escape_html(turn.outcome)}">'
                f'{_escape_html(turn.outcome)}</span>'
            )
            thread_tool_rows.append(
                '<tr class="turn-tool-row">'
                f"<td>{turn_link}</td>"
                f"<td>{_turn_offset_label(run, turn)}</td>"
                f"<td>{_format_detail_ms(turn.duration_ms)}</td>"
                f"<td>{turn_state_badge}</td>"
                f"<td>{len(tools):,}</td>"
                f'<td title="{_escape_html(tool_total)}">{_escape_html(tool_names)}</td>'
                f"<td>{_escape_html(_compact_cost_summary(turn_cost))}</td>"
                "</tr>"
            )
            turn_responses = sorted(
                (response for response in thread.responses if response.turn_id == turn.turn_id),
                key=lambda response: response.source_ordinal,
            )
            turn_activities = sorted(
                (
                    activity
                    for activity in thread.activities
                    if activity.turn_id == turn.turn_id
                    and not _is_empty_delegated_continuation(activity)
                ),
                key=lambda activity: activity.source_ordinal,
            )
            detail_rows: list[tuple[float, int, str]] = []
            input_activities = [
                activity for activity in turn_activities if activity.activity_type == "input"
            ]
            if input_activities:
                input_arguments = "".join(
                    _render_activity_detail(activity, raw_label="raw input")
                    for activity in input_activities
                )
                input_ordinal = float(input_activities[0].source_ordinal)
                input_timestamp = input_activities[0].event_timestamp
                input_model = turn_responses[0].model if turn_responses else ""
                detail_rows.append(
                    (
                        input_ordinal,
                        0,
                        '<tr class="turn-detail-lifecycle-row turn-detail-input-row">'
                        '<td>—</td>'
                        f'<td>{_timestamp_offset_label(run, input_timestamp)}</td>'
                        '<td>—</td>'
                        f'<td>{_render_model_names([input_model] if input_model else [])}</td>'
                        '<td><span class="activity-name">input</span></td>'
                        f'<td>{input_arguments}</td>'
                        '<td>—</td>'
                        "</tr>",
                    )
                )
            for response_index, response in enumerate(turn_responses):
                response_cost = _cost_for_response(thread, response)
                call_usage = _inference_call_usage(response)
                response_cost_label = (
                    f"${response_cost.total_cost:.2f}"
                    if response_cost.total_cost is not None
                    else "—"
                )
                prompt_fragments, result_fragments = _model_response_activity_groups(
                    turn_responses,
                    response_index,
                    turn_activities,
                )
                cache_write_summary = (
                    f' · {call_usage.cache_create_input_tokens:,} cache-write'
                    if show_cache_write
                    else ""
                )
                model_arguments = (
                    f'<div class="activity-summary">{call_usage.direct_input_tokens:,} fresh-input · '
                    f'{call_usage.cached_input_tokens:,} cache-read'
                    f'{cache_write_summary}</div>'
                    + _render_model_activity_disclosure(
                        prompt_fragments,
                        raw_label="raw arguments",
                    )
                )
                response_rate = (
                    call_usage.output_tokens / (response.duration_ms / 1000)
                    if response.duration_ms
                    else None
                )
                timing_summary = (
                    f'{_format_detail_ms(response.duration_ms)} inference · '
                    f'{_format_detail_ms(response.ttft_ms) if response.ttft_ms is not None else "—"} TTFT · '
                    f'{_format_tokens_per_second(response_rate)} · {response.timing_confidence}'
                    if response.duration_ms
                    else "Inference timing unavailable"
                )
                context_summary = (
                    f' · context {response.context_total_tokens:,} / {response.context_capacity:,} '
                    f'({response.context_occupancy_percent:.1f}%)'
                    if response.context_capacity
                    and response.context_occupancy_percent is not None
                    else ""
                )
                model_result = (
                    f'<div class="activity-summary">{call_usage.output_tokens:,} output · '
                    f'{call_usage.reasoning_tokens:,} reasoning</div>'
                    f'<div class="activity-summary inference-call-summary">{_escape_html(timing_summary + context_summary)}</div>'
                    + _render_model_activity_disclosure(
                        result_fragments,
                        raw_label="raw result",
                    )
                )
                detail_rows.append(
                    (
                        float(response.source_ordinal),
                        0,
                        '<tr class="turn-detail-lifecycle-row turn-detail-model-row">'
                        f'<td>M{response_index + 1}</td>'
                        f'<td>{_timestamp_offset_label(run, response.event_timestamp)}</td>'
                        f'<td>{response_cost_label}</td>'
                        f'<td>{_render_model_names([response.model] if response.model else [])}</td>'
                        '<td><span class="activity-name">model</span>'
                        f'<span id="{_response_event_id(thread, response)}" '
                        'class="turn-event-anchor"></span></td>'
                        f'<td>{model_arguments}</td>'
                        f'<td>{model_result}</td>'
                        "</tr>",
                    )
                )
            reasoning_index = 0
            for activity in turn_activities:
                if activity.activity_type != "reasoning":
                    continue
                reasoning_index += 1
                activity_models = (
                    [activity.model]
                    if activity.model
                    else _models_before_source(
                        thread,
                        turn_id=turn.turn_id,
                        source_path=activity.source_path,
                        source_ordinal=activity.source_ordinal,
                    )
                )
                detail_rows.append(
                    (
                        float(activity.source_ordinal),
                        1,
                        '<tr class="turn-detail-lifecycle-row turn-detail-reasoning-row">'
                        f'<td>R{reasoning_index}</td>'
                        f'<td>{_timestamp_offset_label(run, activity.event_timestamp)}</td>'
                        '<td>—</td>'
                        f'<td>{_render_model_names(activity_models, attributed=not bool(activity.model))}</td>'
                        '<td><span class="activity-name">reasoning</span></td>'
                        '<td>—</td>'
                        f'<td>{_render_activity_detail(activity, raw_label="raw reasoning")}</td>'
                        "</tr>",
                    )
                )
            if not reasoning_index and turn.usage.reasoning_tokens:
                detail_rows.append(
                    (
                        (float(turn_responses[0].source_ordinal) - 0.25)
                        if turn_responses
                        else float(turn.source_ordinal),
                        1,
                        '<tr class="turn-detail-lifecycle-row turn-detail-reasoning-row">'
                        '<td>R1</td>'
                        f'<td>{_timestamp_offset_label(run, turn.started_at)}</td>'
                        '<td>—</td><td>—</td>'
                        '<td><span class="activity-name">reasoning</span></td>'
                        '<td>—</td>'
                        f'<td><div class="activity-summary">{turn.usage.reasoning_tokens:,} recorded reasoning tokens</div></td>'
                        "</tr>",
                    )
                )
            for tool_index, tool in enumerate(tools, start=1):
                tool_models = (
                    [tool.model]
                    if tool.model
                    else _models_before_source(
                        thread,
                        turn_id=turn.turn_id,
                        source_path=tool.source_path,
                        source_ordinal=tool.source_start_ordinal,
                    )
                )
                detail_rows.append(
                    (
                        float(tool.source_start_ordinal),
                        2,
                        '<tr class="turn-detail-tool-row">'
                        f"<td>{tool_index}</td>"
                        f"<td>{_timestamp_offset_label(run, tool.started_at)}</td>"
                        '<td>—</td>'
                        f'<td>{_render_model_names(tool_models, attributed=not bool(tool.model))}</td>'
                        f'<td><code class="tool-name">{_escape_html(tool.tool_name)}</code>'
                        f'<span id="{_tool_event_id(thread, tool)}" '
                        'class="turn-event-anchor"></span></td>'
                        f"<td>{_render_tool_argument(tool, formatter_config)}</td>"
                        f"<td>{_render_tool_result(tool)}</td>"
                        "</tr>",
                    )
                )
            for mcp_index, call in enumerate(mcp_calls, start=1):
                call_models = (
                    [call.model]
                    if call.model
                    else _models_before_source(
                        thread,
                        turn_id=turn.turn_id,
                        source_path=call.source_path,
                        source_ordinal=call.source_ordinal,
                    )
                )
                mcp_name = f"{call.server_name} → {call.tool_name}"
                detail_rows.append(
                    (
                        float(call.source_ordinal),
                        2,
                        '<tr class="turn-detail-tool-row turn-detail-mcp-row">'
                        f"<td>M{mcp_index}</td>"
                        f"<td>{_timestamp_offset_label(run, call.started_at)}</td>"
                        '<td>—</td>'
                        f'<td>{_render_model_names(call_models, attributed=not bool(call.model))}</td>'
                        f'<td><code class="tool-name mcp-tool-name">{_escape_html(mcp_name)}</code>'
                        f'<span id="{_mcp_event_id(thread, call)}" '
                        'class="turn-event-anchor"></span></td>'
                        f"<td>{_render_mcp_argument(call)}</td>"
                        f"<td>{_render_mcp_result(call)}</td>"
                        "</tr>",
                    )
                )
            final_ordinal = max(
                [float(turn.source_ordinal)]
                + [float(response.source_ordinal) for response in turn_responses]
                + [float(activity.source_ordinal) for activity in turn_activities]
                + [float(tool.source_end_ordinal) for tool in tools]
                + [float(call.source_ordinal) for call in mcp_calls]
            ) + 1
            output_activities = [
                activity for activity in turn_activities if activity.activity_type == "output"
            ]
            output_detail = (
                _render_activity_detail(output_activities[-1], raw_label="raw output")
                if output_activities
                else '<div class="activity-summary">No plaintext output recorded</div>'
            )
            detail_rows.append(
                (
                    final_ordinal,
                    3,
                    '<tr class="turn-detail-lifecycle-row turn-detail-output-row">'
                    '<td>—</td>'
                    f'<td>{_timestamp_offset_label(run, turn.completed_at)}</td>'
                    '<td>—</td><td>—</td>'
                    '<td><span class="activity-name">output</span></td>'
                    '<td><div class="activity-summary">Output generation aggregate</div>'
                    f'{output_detail}</td>'
                    f'<td><div class="activity-summary">{turn.usage.output_tokens:,} model-output tokens '
                    f'across {len(turn_responses):,} responses</div></td>'
                    "</tr>",
                )
            )
            turn_detail_tool_rows = "".join(
                row for _, _, row in sorted(detail_rows, key=lambda item: (item[0], item[1]))
            )
            mcp_skills = _inventory_text(turn.mcp_skills_loaded)
            bash_skills = _inventory_text(turn.bash_skills_loaded)
            mcp_calls_html = _clamped_inventory_html(
                mcp_names,
                len(mcp_calls),
                "turn-mcp-calls-disclosure",
            )
            mcp_skills_html = _clamped_inventory_html(
                mcp_skills,
                len(turn.mcp_skills_loaded),
                "turn-mcp-skills-disclosure",
            )
            bash_skills_html = _clamped_inventory_html(
                bash_skills,
                len(turn.bash_skills_loaded),
                "turn-bash-skills-disclosure",
            )
            abort_provenance_detail = _render_abort_provenance_detail(turn)
            turn_detail_overlays.append(
                f'<section id="{turn_detail_overlay_id}" class="tool-call-overlay turn-detail-overlay" role="dialog" aria-modal="true" aria-labelledby="{turn_detail_overlay_id}-title">'
                '<div class="tool-call-panel turn-detail-panel">'
                '<div class="tool-call-header">'
                f'<h2 id="{turn_detail_overlay_id}-title">{_escape_html(agent_assignment)} — {turn_singular.capitalize()} {_escape_html(turn.turn_id)}</h2>'
                '<a class="tool-call-close" href="#timeline">close</a>'
                "</div>"
                '<div class="metrics turn-detail-metrics">'
                f'<div class="metric"><div class="label">Start T+</div><div class="value">{_turn_offset_label(run, turn).removeprefix("T+")}</div></div>'
                f'<div class="metric"><div class="label">Duration</div><div class="value">{_format_detail_ms(turn.duration_ms)}</div></div>'
                f'<div class="metric turn-state-metric"><div class="label">State</div><div class="value"><span class="state state-{_escape_html(turn.outcome)}">{_escape_html(turn.outcome)}</span></div>{abort_provenance_detail}</div>'
                f'<div class="metric"><div class="label">Processed tokens</div><div class="value">{turn.usage.processed_tokens:,}</div></div>'
                f'<div class="metric"><div class="label">Model</div><div class="value">{_render_turn_model_metric(thread, turn.turn_id)}</div></div>'
                f'<div class="metric"><div class="label">Cost estimate</div><div class="value">{_escape_html(_compact_cost_summary(turn_cost))}</div></div>'
                '<div class="metric turn-mcp-count-metric"><div class="label">MCP calls</div>'
                f'<div class="value">{turn.mcp_call_count:,}</div>'
                f'<div class="metric-detail">{mcp_calls_html}</div>'
                f'<span class="turn-state-source">{_escape_html(mcp_total)}</span></div>'
                '<div class="metric turn-mcp-skills-metric"><div class="label">Skills via MCP</div>'
                f'<div class="value">{len(turn.mcp_skills_loaded):,}</div>'
                f'<div class="metric-detail">{mcp_skills_html}</div></div>'
                '<div class="metric turn-bash-skills-metric"><div class="label">Skills via Bash</div>'
                f'<div class="value">{len(turn.bash_skills_loaded):,}</div>'
                f'<div class="metric-detail">{bash_skills_html}</div></div>'
                '<div class="metric turn-tools-metric"><div class="label">Tools used</div>'
                f'<div class="value">{_escape_html(tool_names)}</div>'
                f'<span class="metric-detail">{_escape_html(tool_total)}</span></div>'
                "</div>"
                '<div class="table-scroll"><table class="turn-detail-table">'
                '<colgroup><col class="turn-detail-index-column">'
                '<col class="turn-detail-offset-column">'
                '<col class="turn-detail-cost-column">'
                '<col class="turn-detail-model-column">'
                '<col class="turn-detail-activity-column">'
                '<col class="turn-detail-arguments-column">'
                '<col class="turn-detail-result-column">'
                '</colgroup>'
                '<thead><tr><th>#</th><th>T+</th>'
                '<th title="Cost of the model response on this row; tool execution has no separately recorded model cost">Cost</th>'
                '<th>Model</th><th>Activity</th><th>Arguments</th><th>Result</th>'
                '</tr></thead>'
                f"<tbody>{turn_detail_tool_rows}</tbody></table></div>"
                "</div>"
                "</section>"
            )
            work_unit_cell = (
                f"<td>{_escape_html(turn.work_unit_id or 'unattributed')}</td>"
                if show_work_unit
                else ""
            )
            activity_cell = (
                f"<td>{_escape_html(turn.activity)}</td>" if show_activity else ""
            )
            timeline_label = (
                f"{turn_singular.capitalize()} {_turn_offset_label(run, turn)} · "
                f"{_format_detail_ms(turn.duration_ms)}"
            )
            timeline_end = turn.completed_at or thread.last_observed_at
            timeline_cell = (
                '<td class="turn-timeline-cell">'
                '<span class="timeline-track turn-timeline-track" role="img" '
                f'aria-label="{_escape_html(timeline_label)}">'
                '<span class="timeline-bar turn-timeline-bar" '
                f'style="{_timeline_style(run, turn.started_at, timeline_end)}"></span>'
                "</span></td>"
            )
            cache_write_cell = (
                f"<td>{turn.usage.cache_create_input_tokens:,}</td>"
                if show_cache_write
                else ""
            )
            turn_activity_detail = (
                f"({len(tools):,})"
                if is_junie
                else f"({len(tools):,}/{len(mcp_calls):,})"
            )
            turn_activity_cell = (
                '<td class="turn-activity-cell">'
                '<span class="cell-primary">1</span>'
                f'<span class="cell-secondary">{turn_activity_detail}</span></td>'
            )
            turn_time_cell = (
                '<td class="turn-time-cell">'
                f'<span class="cell-primary">{_format_detail_ms(turn.duration_ms)}</span>'
                f'<span class="cell-secondary">({_escape_html(_compact_cost_summary(turn_cost))})</span></td>'
            )
            turn_rows.append(
                "<tr>"
                f"<td>{turn_link} {turn_state_badge}</td>"
                f"<td>{_turn_offset_label(run, turn)}</td>"
                f"{work_unit_cell}"
                f"{activity_cell}"
                f"{turn_activity_cell}"
                f"{turn_time_cell}"
                f"<td>{turn.usage.direct_input_tokens:,}</td>"
                f"<td>{turn.usage.cached_input_tokens:,}</td>"
                f"{cache_write_cell}"
                f"<td>{turn.usage.output_tokens:,}</td>"
                f"<td>{turn.usage.reasoning_tokens:,}</td>"
                f"{timeline_cell}"
                "</tr>"
            )
        turn_column_count = (
            9 + int(show_cache_write) + int(show_work_unit) + int(show_activity)
        )
        turn_rows_html = "".join(turn_rows) or (
            f'<tr><td colspan="{turn_column_count}">No {turn_plural} recorded</td></tr>'
        )
        optional_headers = (
            ("<th>Work unit</th>" if show_work_unit else "")
            + ("<th>Activity</th>" if show_activity else "")
        )
        thread_tool_rows_html = "".join(thread_tool_rows) or (
            f'<tr><td colspan="7">No {turn_plural} recorded</td></tr>'
        )
        tool_call_overlays.append(
            f'<section id="{tool_call_overlay_id}" class="tool-call-overlay agent-tool-call-overlay" role="dialog" aria-modal="true" aria-labelledby="{tool_call_overlay_id}-title">'
            '<div class="tool-call-panel">'
            '<div class="tool-call-header">'
            f'<h2 id="{tool_call_overlay_id}-title">{_escape_html(agent_assignment)} — {turn_plural} and tool calls</h2>'
            '<a class="tool-call-close" href="#timeline">close</a>'
            "</div>"
            f'<p class="execution-note">Select a {turn_singular} to see its timing, attribution, tokens, and ordered privacy-safe tool-call sequence.</p>'
            f'<div class="table-scroll"><table><thead><tr><th>{turn_id_label}</th><th>T+</th><th>Duration</th><th>State</th><th>Calls</th><th>Tools</th><th>Cost estimate</th></tr></thead>'
            f"<tbody>{thread_tool_rows_html}</tbody></table></div>"
            "</div>"
            "</section>"
        )
        agent_detail_id = agent_detail_ids[thread.thread_id]
        thread_details[thread.thread_id] = (
            f'<tr id="{agent_detail_id}" class="agent-expanded-row" hidden>'
            '<td colspan="6">'
            f"<h3>{turn_activity_label}</h3>"
            '<div class="table-scroll"><table class="turn-table"><thead><tr>'
            f"<th>{turn_id_label}</th><th>T+</th>{optional_headers}"
            f"<th>{agent_activity_heading}</th><th>{agent_time_heading}</th>"
            "<th>Fresh Input</th><th>Cache read</th>"
            f'{"<th>Cache write</th>" if show_cache_write else ""}'
            '<th>Output</th><th>Reasoning</th><th class="turn-timeline-header">Timeline</th>'
            f"</tr></thead><tbody>{turn_rows_html}</tbody></table></div>"
            "</td></tr>"
        )
    agent_rows_html = "".join(
        summary_row + thread_details.get(thread_id, "")
        for thread_id, summary_row in agent_rows
    )
    if progress is not None:
        progress(87, "Rendering usage details", "Preparing pricing, token, and model summaries.")
    pricing_rows = []
    for model, prices in _pricing_reference_rows():
        pricing_rows.append(
            "<tr>"
            f"<td>{_escape_html(str(prices.get('provider', '—')))}</td>"
            f"<td><strong>{_escape_html(str(prices.get('display_name', model)))}</strong><br><code>{_escape_html(model)}</code></td>"
            f"<td>{_escape_html(_rate_triplet(prices, PRICING_RATE_KEYS, '$'))}</td>"
            f"<td>{_escape_html(str(prices.get('pricing_note', '')) or '—')}</td>"
            "</tr>"
        )
    pricing_registry = _load_pricing_registry()
    pricing_version = str(pricing_registry.get("_updated_at", ""))
    openai_source = str(pricing_registry.get("_source", ""))
    anthropic_source = str(pricing_registry.get("_anthropic_source", ""))
    is_codex = run.runtime.lower() == "codex"
    is_junie_ide = run.critical_path_method.startswith("Junie IDE")
    pricing_link = (
        '<p class="execution-note"><a class="drilldown-link" href="#model-pricing" '
        'target="_blank" rel="noopener">Open model pricing</a>.</p>'
        if is_codex
        else ""
    )
    pricing_overlay = (
        f'<section id="model-pricing" class="model-pricing-overlay" role="dialog" aria-modal="true" aria-labelledby="model-pricing-title">'
        '<div class="model-pricing-panel">'
        '<div class="model-pricing-header"><h2 id="model-pricing-title">Model pricing</h2><span class="execution-note">Close this tab to return to the report.</span></div>'
        f'<p class="execution-note">Rates updated {_escape_html(pricing_version)} and shown per 1M tokens in input / cached input / output order. API USD estimates are comparison values, not subscription invoices. Long-context and fast-mode multipliers are not inferred from aggregate telemetry. Sources: <a href="{_escape_html(openai_source)}">OpenAI API</a> and <a href="{_escape_html(anthropic_source)}">Anthropic API</a>.</p>'
        '<div class="table-scroll"><table class="pricing-table"><thead><tr><th>Provider</th><th>Model</th><th>API USD / 1M tokens<br>input / cached / output</th><th>Note</th></tr></thead>'
        f"<tbody>{''.join(pricing_rows)}</tbody></table></div></div></section>"
        if is_codex
        else ""
    )
    agent_note = (
        "Agent rows follow the recorded assignment hierarchy. Each identity separates the thread name, resolved agent type, and optional runtime nickname. Main identifies the root agent; default is Codex's built-in role when a spawn omits agent_type; any other value is the explicitly selected role. Nested rows are indented under their parent assignment. Skills are listed only when a SKILL.md reference appears in recorded tool arguments."
        if is_codex
        else (
            "This Junie IDE chain contains one main agent. User tasks are the durable "
            "task records in the selected chain; model responses are de-duplicated "
            "assistant-request usage records. The main agent has no custom-agent type. Skills are listed when Junie recorded an "
            "agent_skill_read_doc tool use."
        )
        if is_junie_ide
        else (
            "Thread names come from Junie's AgentTaskNameUpdatedEvent when available; custom-agent names are shown separately as agent types. Nested rows are indented under their parent assignment. "
            "User tasks count unique TaskStartedEvent IDs; task spans count each participating agent once per task, so delegated work appears in both the parent and custom-agent rows. "
            "Model responses count LlmResponseMetadataEvent records. Skills are listed only when a SKILL.md reference appears in recorded tool arguments."
        )
    )
    execution_note = (
        "Bars share a common run-wide time axis and show each agent's active turns and each turn's observed span. Agent and turn costs use each agent's recorded model and the linked pricing table."
        if is_codex
        else (
            "Bars share a common run-wide time axis and show the Junie IDE task spans "
            "using task creation times and durable step completion timestamps. Task "
            "costs come directly from Junie; response costs within each task are "
            "allocated by processed-token share."
        )
        if is_junie_ide
        else "Bars share a common run-wide time axis and show each agent and task span's observed span from Junie's timestamped session events. Costs are recorded by Junie and allocated to agent task spans by processed-token share."
    )
    full_report_title = page_title or (
        run.run_label
        if run.runtime.casefold() == "codex" and run.run_label
        else AGENT_EXECUTION_METRICS_TITLE
    )
    report_title = _compact_report_title(full_report_title)
    report_title_attribute = (
        f' title="{_escape_html_attribute(full_report_title)}"'
        if report_title != full_report_title
        else ""
    )
    page_actions_html = ""
    if page_action_links:
        page_actions_html = " · " + " · ".join(
            f'<a href="{_escape_html(href)}">{_escape_html(label)}</a>'
            for label, href in page_action_links
        )
    run_label_html = (
        '<p class="run-label"><strong>Thread Title:</strong> '
        f'&quot;{_escape_html(page_subtitle)}&quot;{page_actions_html}</p>'
        if page_subtitle
        else (
            f'<p class="run-label">{_escape_html(run.run_label)}</p>'
            if run.run_label and run.run_label != full_report_title
            else ""
        )
    )
    if progress is not None:
        progress(89, "Rendering model usage", "Building model and token usage sections.")
    model_usage_html = _render_model_usage_section(run)
    if progress is not None:
        progress(90, "Rendering context usage", "Building context growth and compaction sections.")
    context_metrics_html = _render_context_metrics(run)
    if progress is not None:
        progress(91, "Rendering inference metrics", "Building inference timing and throughput sections.")
    inference_metrics_html = _render_inference_metrics(run)
    if progress is not None:
        progress(92, "Rendering runtime metrics", "Building runtime state and work-item sections.")
    runtime_metrics_html = _render_runtime_metrics(run)
    work_item_metrics_html = _render_work_item_metrics(run)
    if progress is not None:
        progress(93, "Rendering execution heatmap", "Serializing period measures and drilldown events.")
    execution_heatmap_html = _render_execution_heatmap(
        run,
        progress=progress,
        worker_progress=worker_progress,
        workers=workers,
    )
    if progress is not None:
        progress(96, "Rendering sequence diagram", "Building thread messages, delegations, and lifecycle events.")
    sequence_html = _render_codex_sequence_section(run)
    sequence_document_html = (
        f"<!-- agent-sequence:start -->{sequence_html}<!-- agent-sequence:end -->"
        if sequence_html
        else ""
    )
    view_links = []
    if execution_heatmap_html:
        view_links.append('<a href="#execution-heatmap">Heatmap</a>')
    view_links.append('<a href="#timeline">Timeline</a>')
    if sequence_html:
        view_links.append(
            '<a href="?view=sequence#agent-sequence" target="_blank" rel="noopener" '
            'data-sequence-window>Sequence window</a>'
        )
    view_nav_html = (
        '<nav class="view-nav" aria-label="Report views"><span>Views</span>'
        + "".join(view_links)
        + "</nav>"
    )
    parent_context_html = ""
    if run.parent_context is not None:
        parent_title = run.parent_context.task_title or run.parent_context.thread_id
        visible_parent_title = _compact_display_text(parent_title, 120)
        parent_report_url = "agent-report://view-parent-report?" + _url_query(
            {
                "thread_id": run.parent_context.thread_id,
                "title": parent_title,
                "source_path": run.parent_context.source_path,
            }
        )
        parent_context_html = (
            '<aside class="parent-context" aria-label="Parent task">'
            '<div class="parent-context-copy">'
            '<span class="parent-context-label">Parent task</span>'
            f'<strong title="{_escape_html_attribute(parent_title)}">'
            f'{_escape_html(visible_parent_title)}</strong>'
            f'<code>{_escape_html(run.parent_context.thread_id)}</code>'
            "</div>"
            '<a class="parent-report-button" role="button" '
            f'href="{_escape_html_attribute(parent_report_url)}">View parent report</a>'
            "</aside>"
        )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{_escape_html(report_title)}</title>
<style>
:root {{ --font-ui:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; --font-code:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace; --token-cached:#3498db; --token-cache-write:#2ecc71; --token-fresh:#95a5a6; --token-output:#e74c3c; --token-reasoning:#8e44ad; --sequence-rail:#b0bec5; --sequence-delegation:#00695c; --sequence-message:#2563a6; --sequence-followup:#6d4c8e; --sequence-interrupt:#b3261e; --sequence-complete:#24733b; --sequence-thinking:#8e44ad; }}
body {{ font-family:var(--font-ui); margin: 2em; color: #263238; background:#fafbfc; }}
body.sequence-only {{ margin:16px; overflow:hidden; }}
body.sequence-only > :not(#agent-sequence) {{ display:none; }}
body.sequence-only #agent-sequence {{ display:flex; height:calc(100vh - 32px); min-height:0; flex-direction:column; }}
body.sequence-only #agent-sequence > .agents-heading {{ flex:0 0 auto; margin-top:0; }}
body.sequence-only #agent-sequence > .execution-note,
body.sequence-only #agent-sequence > .sequence-controls,
body.sequence-only #agent-sequence > .sequence-ledger {{ flex:0 0 auto; }}
body.sequence-only .sequence-scroll {{ flex:1 1 auto; min-height:0; max-height:none; }}
body.sequence-only .sequence-ledger[open] {{ max-height:35vh; overflow:auto; }}
h1 {{ margin-bottom:.25em; }}
h2 {{ margin-top:30px; }}
h3 {{ margin:14px 0 6px; font-size:.95em; color:#546e7a; }}
.report-nav {{ margin:0 0 14px; }}
.report-nav a {{ color:#2563a6; font-weight:600; text-decoration:none; }}
.report-nav a:hover {{ text-decoration:underline; }}
.view-nav {{ display:flex; align-items:center; gap:6px; margin:12px 0 18px; }}
.view-nav span {{ margin-right:2px; color:#607d8b; font-size:.78em; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }}
.view-nav a {{ padding:5px 10px; color:#2563a6; background:#fff; border:1px solid #cfd8dc; border-radius:999px; font-size:.86em; font-weight:600; text-decoration:none; }}
.view-nav a:hover {{ border-color:#2563a6; }}
.view-nav a:focus-visible, .sequence-scroll:focus-visible, .sequence-event-link:focus-visible {{ outline:2px solid #2563a6; outline-offset:2px; }}
.parent-context {{ display:flex; align-items:center; justify-content:space-between; gap:18px; margin:0 0 18px; padding:12px 14px; background:#eef4f8; border:1px solid #b8cad5; border-radius:7px; }}
.parent-context-copy {{ display:grid; min-width:0; gap:3px; }}
.parent-context-label {{ color:#546e7a; font-size:.72em; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }}
.parent-context strong {{ overflow-wrap:anywhere; }}
.parent-context code {{ color:#607d8b; }}
.parent-report-button {{ flex:0 0 auto; padding:7px 11px; color:#fff; background:#2563a6; border:1px solid #2563a6; border-radius:5px; font-size:.86em; font-weight:700; text-decoration:none; }}
.parent-report-button:hover {{ background:#174f85; border-color:#174f85; }}
.parent-report-button:focus-visible {{ outline:2px solid #2563a6; outline-offset:2px; }}
.visually-hidden {{ position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }}
.metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; }}
.metric {{ background:#fff; border:1px solid #e1e6ea; border-radius:6px; padding:12px; }}
.label {{ color:#666; font-size:.82em; }}
.value {{ font-size:1.2em; font-weight:600; margin-top:3px; }}
.metric-detail {{ display:block; margin-top:4px; color:#607d8b; font-size:.68em; font-weight:400; line-height:1.35; overflow-wrap:anywhere; }}
.metric-view {{ margin-top:28px; }}
.metric-view .agents-heading {{ margin-top:0; gap:9px; }}
.compact-metrics {{ grid-template-columns:repeat(auto-fit,minmax(145px,1fr)); margin-top:10px; }}
.compact-metrics .metric {{ padding:10px 11px; }}
.evidence-badge {{ padding:3px 7px; color:#455a64; background:#eef4f8; border:1px solid #c5d3dc; border-radius:999px; font-size:.7em; font-weight:700; }}
.metric-details {{ margin-top:8px; }}
.metric-details > summary {{ width:max-content; color:#2563a6; cursor:pointer; font-size:.84em; font-weight:700; }}
.metric-details .table-scroll {{ margin-top:8px; max-height:42vh; }}
.local-timestamp {{ font-variant-numeric:tabular-nums; }}
.turn-state-detail {{ font-size:.66em; line-height:1.25; }}
.turn-state-source {{ display:block; margin-top:2px; color:#78909c; font-size:.58em; font-weight:400; line-height:1.2; overflow-wrap:anywhere; }}
table {{ border-collapse:collapse; width:100%; margin:10px 0; background:#fff; }}
th,td {{ border-bottom:1px solid #e1e6ea; padding:7px; text-align:left; white-space:nowrap; }}
th {{ color:#546e7a; font-size:.8em; background:#f5f7f8; position:sticky; top:0; }}
td {{ font-size:.85em; }}
.table-scroll {{ overflow:auto; max-height:65vh; border:1px solid #e1e6ea; border-radius:5px; }}
.token-composition {{ display:flex; height:18px; overflow:hidden; border-radius:5px; background:#e8edf0; max-width:900px; }}
.token-segment {{ min-width:1px; }}
.fresh {{ background:var(--token-fresh); }} .cached {{ background:var(--token-cached); }} .cache-write {{ background:var(--token-cache-write); }} .output {{ background:var(--token-output); }} .reasoning {{ background:var(--token-reasoning); }}
.composition-legend {{ color:#607d8b; font-size:.85em; margin-top:7px; }}
.composition-fresh {{ color:var(--token-fresh); }} .composition-cached {{ color:var(--token-cached); }} .composition-cache-write {{ color:var(--token-cache-write); }} .composition-output {{ color:var(--token-output); }} .composition-reasoning {{ color:var(--token-reasoning); }}
.model-usage-groups {{ display:grid; gap:8px; }}
.model-usage-group {{ overflow:hidden; border:1px solid #e1e6ea; border-radius:6px; background:#fff; }}
.model-usage-group > summary {{ display:flex; align-items:center; gap:8px; padding:11px 13px; color:#455a64; cursor:pointer; list-style:none; }}
.model-usage-group > summary::-webkit-details-marker {{ display:none; }}
.model-usage-group[open] > summary {{ border-bottom:1px solid #e1e6ea; }}
.model-usage-parent {{ display:flex; flex:1 1 auto; align-items:baseline; justify-content:space-between; gap:18px; min-width:0; }}
.model-identity {{ display:flex; align-items:baseline; gap:4px; }}
.model-effort, .model-usage-total {{ color:#607d8b; font-size:.85em; }}
.model-usage-total {{ text-align:right; }}
.model-usage-group .table-scroll {{ max-height:45vh; border:0; border-radius:0; }}
.model-usage-table {{ min-width:940px; margin:0; }}
.model-usage-table th:first-child, .model-usage-table td:first-child {{ white-space:normal; }}
.agent-table {{ table-layout:fixed; min-width:1200px; }}
.agent-table .agent-assignment-column {{ width:30%; }}
.agent-table .agent-skills-column {{ width:15%; }}
.agent-table .agent-count-column {{ width:10%; }}
.agent-table .agent-time-column {{ width:10%; }}
.agent-table .agent-processed-column {{ width:10%; }}
.agent-table .agent-timeline-column {{ width:25%; }}
.agent-table th {{ white-space:normal; }}
.agent-table td {{ vertical-align:top; }}
.agent-table .agent-assignment-cell, .agent-table .agent-skills-cell {{ white-space:normal; overflow-wrap:anywhere; line-height:1.4; }}
.agent-table .agent-skills-cell {{ font-size:.7em; }}
.clamped-disclosure > summary {{ list-style:none; cursor:pointer; }}
.clamped-disclosure > summary::-webkit-details-marker {{ display:none; }}
.clamped-preview {{ display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:5; overflow:hidden; }}
.clamped-toggle {{ display:inline-block; margin-top:2px; padding:0; border:0; color:#2563a6; background:none; cursor:pointer; font:inherit; text-decoration:underline; }}
.clamped-disclosure[open] > summary {{ display:none; }}
.clamped-full {{ margin-top:0; }}
.clamped-less {{ display:block; margin-top:3px; }}
.agent-title-disclosure {{ min-width:0; max-width:100%; }}
.agent-title-disclosure .clamped-preview {{ -webkit-line-clamp:3; }}
.agent-assignment-line {{ display:flex; align-items:flex-start; gap:8px; }}
.agent-assignment-heading {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
.agent-assignment-heading .state {{ flex:0 0 auto; }}
.agent-model-metadata {{ white-space:nowrap; }}
.agent-model-metadata .model-name {{ font-size:.82em; }}
.effort-level {{ color:#607d8b; font-size:.82em; }}
.agent-row-toggle, .model-usage-toggle-icon {{ box-sizing:border-box; flex:0 0 auto; width:20px; height:20px; margin-top:1px; padding:0; border:1px solid #90a4ae; border-radius:50%; color:#455a64; background:#fff; cursor:pointer; font:700 14px/18px var(--font-ui); text-align:center; }}
.agent-row-toggle-icon::before {{ content:"+"; }}
.agent-row-toggle[aria-expanded="true"] .agent-row-toggle-icon::before {{ content:"−"; }}
.model-usage-toggle-icon::before {{ content:"+"; }}
.model-usage-group[open] > summary .model-usage-toggle-icon::before {{ content:"−"; }}
.agent-row-toggle:focus-visible {{ outline:2px solid #2563a6; outline-offset:2px; }}
.column-detail {{ color:#78909c; font-size:.78em; font-weight:400; }}
.cell-primary, .cell-secondary {{ display:block; }}
.cell-secondary {{ margin-top:2px; color:#607d8b; font-size:.86em; }}
.agent-table .agent-timeline-track {{ width:100%; min-width:220px; }}
.agent-assignment-cell {{ --agent-indent:calc(var(--agent-depth) * 20px); padding-left:calc(7px + var(--agent-indent)); background:linear-gradient(to right,#0d47a1 0 var(--agent-indent),transparent var(--agent-indent)); }}
.agents-heading {{ position:relative; display:flex; align-items:center; margin-top:30px; }}
.agents-heading h2 {{ margin:0; }}
.agent-info {{ position:static; margin-left:8px; }}
.agent-info > summary {{ list-style:none; color:#2563a6; cursor:pointer; font-size:1.15em; line-height:1; }}
.agent-info > summary::-webkit-details-marker {{ display:none; }}
.agent-note-popover {{ position:absolute; z-index:20; top:calc(100% + 8px); right:0; box-sizing:border-box; width:min(620px,calc(100vw - 4em)); padding:12px 14px; color:#455a64; background:#fff; border:1px solid #cfd8dc; border-radius:6px; box-shadow:0 8px 24px rgba(38,50,56,.18); font-size:.88em; font-weight:400; line-height:1.45; }}
.execution-note {{ color:#607d8b; font-size:.88em; }}
#agent-sequence {{ display:none; scroll-margin-top:12px; }}
.sequence-controls {{ display:flex; flex-wrap:wrap; align-items:center; gap:7px 10px; margin:2px 0 10px; color:#455a64; font-size:.8em; }}
.sequence-control-group {{ display:inline-flex; align-items:center; gap:5px; }}
.sequence-controls button {{ min-height:30px; padding:4px 9px; color:#455a64; background:#fff; border:1px solid #90a4ae; border-radius:5px; cursor:pointer; font:600 1em var(--font-ui); }}
.sequence-controls button:hover {{ color:#0d47a1; border-color:#2563a6; }}
.sequence-controls button:focus-visible {{ outline:2px solid #2563a6; outline-offset:2px; }}
.sequence-controls button:disabled {{ color:#90a4ae; background:#f5f7f8; border-color:#cfd8dc; cursor:not-allowed; }}
.sequence-controls button[aria-pressed="true"] {{ color:#0d47a1; background:#e3f2fd; border-color:#2563a6; }}
.sequence-controls output[data-sequence-zoom-value] {{ min-width:42px; color:#263238; text-align:center; font-family:var(--font-code); }}
.sequence-filter-fieldset {{ display:flex; flex-wrap:wrap; align-items:center; gap:5px 9px; min-width:0; margin:0; padding:4px 8px 5px; border:1px solid #cfd8dc; border-radius:5px; }}
.sequence-filter-fieldset legend {{ padding:0 4px; color:#546e7a; font-weight:600; }}
.sequence-filter-fieldset label {{ display:inline-flex; align-items:center; gap:4px; white-space:nowrap; }}
.sequence-filter-fieldset input {{ accent-color:#2563a6; }}
.sequence-view-status {{ margin-left:auto; color:#546e7a; font-family:var(--font-code); }}
.sequence-inspect-detail {{ box-sizing:border-box; min-height:2.8em; max-height:2.8em; margin:0 0 8px; overflow:auto; color:#455a64; font-size:.84em; line-height:1.4; }}
.sequence-filter-empty {{ margin:0 0 8px; padding:8px 10px; color:#455a64; background:#fff8e1; border:1px solid #ffe082; border-radius:5px; font-size:.84em; }}
.sequence-hidden {{ display:none; }}
.sequence-empty {{ padding:18px; color:#607d8b; background:#fff; border:1px solid #e1e6ea; border-radius:6px; }}
.sequence-legend {{ position:sticky; left:0; display:flex; width:max-content; flex-wrap:wrap; gap:8px 16px; box-sizing:border-box; margin:0; padding:8px 12px 2px; color:#546e7a; background:#fff; font-size:.78em; }}
.sequence-legend span {{ display:inline-flex; align-items:center; gap:6px; }}
.legend-line {{ display:inline-block; width:24px; height:0; border-top:2px solid currentColor; }}
.legend-delegation {{ color:var(--sequence-delegation); }}
.legend-message {{ color:var(--sequence-message); }}
.legend-followup {{ color:var(--sequence-followup); }}
.legend-interrupt {{ color:var(--sequence-interrupt); }}
.legend-complete {{ color:var(--sequence-complete); border-top-style:dashed; }}
.legend-conversation-bubble {{ position:relative; display:inline-block; width:22px; height:12px; box-sizing:border-box; background:#f3e5f5; border:1px solid var(--sequence-thinking); border-radius:4px; }}
.legend-conversation-bubble::after {{ position:absolute; top:3px; left:-5px; width:0; height:0; border-top:3px solid transparent; border-right:5px solid var(--sequence-thinking); border-bottom:3px solid transparent; content:""; }}
.sequence-scroll {{ position:relative; max-height:72vh; overflow:auto; margin:0 0 10px; background:#fff; border:1px solid #d7e0e5; border-radius:6px; }}
.sequence-canvas {{ min-width:100%; background:#fff; }}
.sequence-sticky-header {{ position:sticky; top:0; z-index:5; background:#fff; border-bottom:1px solid #d7e0e5; box-shadow:0 3px 8px rgba(38,50,56,.08); }}
.sequence-participant-header {{ display:block; background:#fff; }}
.agent-sequence-diagram {{ display:block; background:#fff; }}
.sequence-participant rect {{ fill:#f5f7f8; stroke:#90a4ae; stroke-width:1; }}
.sequence-participant[data-depth="0"] rect {{ fill:#eef4f8; stroke:#607d8b; }}
.sequence-focus-target {{ cursor:pointer; }}
.sequence-focus-target:focus-visible, .sequence-hierarchy-toggle:focus-visible {{ outline:none; }}
.sequence-focus-target:focus-visible rect, .sequence-focus-target[aria-pressed="true"] rect {{ fill:#e3f2fd; stroke:#2563a6; stroke-width:2; }}
.sequence-hierarchy-toggle {{ cursor:pointer; }}
.sequence-hierarchy-toggle circle {{ fill:#fff; stroke:#607d8b; stroke-width:1; }}
.sequence-hierarchy-toggle:focus-visible circle {{ stroke:#2563a6; stroke-width:2; }}
.sequence-hierarchy-toggle text {{ font-size:13px; font-weight:700; }}
.sequence-participant text {{ fill:#263238; font-family:var(--font-ui); }}
.sequence-participant-name {{ font-size:12px; font-weight:700; }}
.sequence-participant-detail {{ fill:#607d8b; font-family:var(--font-code); font-size:9px; }}
.sequence-lifeline {{ stroke:var(--sequence-rail); stroke-width:1; stroke-dasharray:4 5; }}
.sequence-event-band {{ fill:transparent; }}
.sequence-line {{ stroke-width:2; }}
.sequence-event-link .sequence-event > * {{ pointer-events:none; }}
.sequence-event-link .sequence-event > .sequence-event-hit {{ pointer-events:stroke; fill:none; stroke:transparent; stroke-width:24px; stroke-linecap:round; cursor:pointer; }}
.sequence-event-link:has(.sequence-event-hit:hover) .sequence-line,
.sequence-event-link:focus-visible .sequence-line {{ stroke-width:3; }}
.sequence-offset {{ fill:#78909c; font-family:var(--font-code); font-size:9px; }}
.sequence-event-label {{ fill:#263238; stroke:#fff; stroke-width:5px; paint-order:stroke; font-family:var(--font-ui); font-size:10px; font-weight:600; }}
.sequence-conversation-bubble {{ cursor:pointer; }}
.sequence-conversation-bubble rect,
.sequence-conversation-tail {{ fill:#f3e5f5; stroke:var(--sequence-thinking); stroke-width:1; stroke-linejoin:round; }}
.sequence-conversation-link:focus-visible .sequence-conversation-bubble rect {{ stroke-width:2; }}
.sequence-thinking-text {{ fill:#4a235a; font-family:var(--font-ui); font-size:10px; font-weight:400; }}
.sequence-thinking-offset {{ fill:#546e7a; font-family:var(--font-code); font-size:9px; }}
.sequence-repeat-count, .sequence-ledger-repeat-count {{ display:none; }}
.sequence-group-repeats .sequence-repeat-count, .sequence-group-repeats .sequence-ledger-repeat-count {{ display:inline; }}
.sequence-group-repeats .sequence-event-link[data-repeat-index]:not([data-repeat-index="0"]),
.sequence-group-repeats .sequence-ledger li[data-repeat-index]:not([data-repeat-index="0"]) {{ display:none; }}
.sequence-ledger {{ margin-top:10px; background:#fff; border:1px solid #e1e6ea; border-radius:6px; }}
.sequence-ledger > summary {{ padding:10px 12px; color:#455a64; cursor:pointer; font-size:.86em; font-weight:600; }}
.sequence-ledger ol {{ margin:0; padding:0 18px 12px 44px; }}
.sequence-ledger li {{ padding:5px 0; color:#455a64; font-size:.8em; line-height:1.4; }}
.sequence-ledger-link {{ color:inherit; text-decoration:none; }}
.sequence-ledger-link:hover, .sequence-ledger-link:focus-visible {{ color:#2563a6; text-decoration:underline; }}
.sequence-ledger-link > * {{ margin-right:7px; }}
.sequence-ledger time {{ color:#78909c; font-family:var(--font-code); }}
.sequence-ledger li span:last-child {{ color:#607d8b; }}
.tool-call-panel.sequence-event-panel {{ width:min(920px,94vw); overflow:auto; }}
.sequence-event-metrics {{ grid-template-columns:repeat(4,minmax(0,1fr)); }}
.sequence-event-metrics .value {{ overflow-wrap:anywhere; font-size:.92em; }}
.sequence-event-full {{ max-height:7.5em; margin:4px 0 12px; padding:10px 12px; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; color:#263238; background:#f5f7f8; border:1px solid #d7e0e5; border-radius:5px; font-family:var(--font-ui); font-size:.9em; line-height:1.5; }}
.sequence-event-full:focus-visible {{ outline:2px solid #2563a6; outline-offset:2px; }}
.sequence-thought-metrics {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
.sequence-thought-full {{ margin:12px 0 0; padding:12px; white-space:pre-wrap; overflow-wrap:anywhere; color:#263238; background:#f5f7f8; border:1px solid #d7e0e5; border-radius:5px; font-family:var(--font-ui); font-size:.9em; font-weight:400; line-height:1.5; }}
.sequence-sender-update, .sequence-recipient-update {{ max-height:22vh; margin:4px 0 0; padding:12px; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; background:#f5f7f8; border:1px solid #d7e0e5; border-radius:5px; font-family:var(--font-ui); font-size:.88em; line-height:1.5; }}
.sequence-sender-update:focus-visible, .sequence-recipient-update:focus-visible {{ outline:2px solid #2563a6; outline-offset:2px; }}
.sequence-context-arrow {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(150px,1fr) minmax(0,1fr); align-items:center; gap:10px; margin:14px 0; color:#455a64; font-size:.78em; font-weight:600; }}
.sequence-context-party {{ overflow-wrap:anywhere; }}
.sequence-context-target {{ text-align:right; }}
.sequence-context-direction {{ display:flex; min-width:0; align-items:center; gap:6px; color:#2563a6; white-space:nowrap; }}
.sequence-context-line {{ min-width:18px; flex:1 1 auto; border-top:2px solid currentColor; }}
.sequence-context-arrowhead {{ font-size:1.4em; line-height:1; }}
.tool-name {{ font-family:var(--font-code); font-size:.9em; font-weight:400; }}
.model-name {{ font-family:var(--font-code); font-size:.84em; font-weight:400; line-height:1.35; white-space:normal; overflow-wrap:anywhere; }}
.activity-name {{ font-family:var(--font-ui); font-size:.92em; font-weight:600; color:#455a64; }}
.activity-summary {{ font-family:var(--font-ui); font-size:1em; font-weight:400; line-height:1.35; color:#263238; white-space:normal; overflow-wrap:anywhere; }}
.activity-raw {{ margin-top:4px; }}
.activity-raw summary {{ color:#b23a2b; cursor:pointer; font-size:.84em; }}
.activity-raw pre {{ max-width:720px; max-height:360px; margin:5px 0 0; padding:8px; overflow:auto; font-family:var(--font-code); font-size:.9em; font-weight:400; line-height:1.35; white-space:pre-wrap; overflow-wrap:anywhere; background:#f5f7f8; border-radius:4px; }}
.tool-arguments {{ display:block; max-width:720px; font-family:var(--font-code); font-size:.9em; font-weight:400; line-height:1.35; white-space:normal; overflow-wrap:anywhere; }}
.tool-argument-formatted {{ font-family:var(--font-ui); font-size:1em; font-weight:400; line-height:1.35; color:#263238; white-space:normal; overflow-wrap:anywhere; }}
.tool-plan {{ margin:0; padding-left:1.25em; font-family:var(--font-ui); white-space:normal; }}
.tool-plan-item {{ margin:0 0 5px; line-height:1.35; }}
.tool-plan .state {{ margin-left:5px; white-space:nowrap; }}
.tool-argument-raw {{ margin-top:4px; }}
.tool-argument-raw summary {{ color:#b23a2b; cursor:pointer; font-size:.84em; }}
.tool-argument-raw[open] .tool-arguments {{ margin-top:5px; }}
.tool-result-summary {{ max-width:420px; font-family:var(--font-ui); font-size:1em; font-weight:400; line-height:1.35; color:#263238; white-space:normal; overflow-wrap:anywhere; }}
.tool-result-raw {{ margin-top:4px; }}
.tool-result-raw summary {{ color:#b23a2b; cursor:pointer; font-size:.84em; }}
.tool-result-raw pre {{ max-width:720px; max-height:360px; margin:5px 0 0; padding:8px; overflow:auto; font-family:var(--font-code); font-size:.9em; font-weight:400; line-height:1.35; white-space:pre-wrap; overflow-wrap:anywhere; background:#f5f7f8; border-radius:4px; }}
.drilldown-link {{ color:#2563a6; font-weight:600; text-decoration:none; }}
.drilldown-link:hover {{ text-decoration:underline; }}
.agent-summary-row {{ cursor:pointer; }}
.agent-summary-row.is-expanded > td {{ border-bottom:0; background-color:#f7f9fa; }}
.agent-expanded-row > td {{ padding:0 13px 13px; white-space:normal; background:#f7f9fa; }}
.agent-expanded-row h3 {{ margin-left:13px; margin-right:13px; }}
.agent-expanded-row .table-scroll {{ max-height:none; margin:0 -13px; }}
.timeline-track {{ position:relative; display:block; height:12px; background:#e8edf0; border-radius:3px; min-width:180px; }}
.timeline-bar {{ position:absolute; top:0; bottom:0; background:#4a90d9; border-radius:3px; }}
.turn-table .turn-timeline-header, .turn-table .turn-timeline-cell {{ width:25%; min-width:220px; }}
.turn-table .turn-timeline-track {{ width:100%; min-width:220px; }}
.state {{ display:inline-block; border-radius:10px; padding:2px 7px; background:#eceff1; font-size:.82em; }}
.state-complete, .state-sealed {{ background:#e6f4ea; color:#24733b; }}
.state-aborted, .state-failed {{ background:#fdecea; color:#b3261e; }}
.state-active, .state-live {{ background:#fff3cd; color:#7a5b00; }}
.model-pricing-overlay {{ display:none; position:fixed; inset:0; z-index:1000; padding:4vh 3vw; box-sizing:border-box; background:#fafbfc; }}
.model-pricing-overlay:target {{ display:flex; }}
.model-pricing-panel {{ width:min(1200px,94vw); max-height:92vh; margin:auto; padding:0 16px 16px; overflow:hidden; background:#fafbfc; }}
.model-pricing-header {{ display:flex; justify-content:space-between; align-items:center; gap:20px; padding:14px 2px 4px; }}
.model-pricing-header h2 {{ margin:0; }}
.model-pricing-panel .table-scroll {{ max-height:calc(92vh - 110px); }}
.tool-call-overlay {{ display:none; position:fixed; inset:0; z-index:1000; padding:4vh 3vw; box-sizing:border-box; background:rgba(25,35,45,.62); }}
.tool-call-overlay:target {{ display:flex; }}
.tool-call-panel {{ display:flex; flex-direction:column; box-sizing:border-box; width:min(1500px,94vw); max-height:92vh; margin:auto; padding:0 16px 16px; overflow:hidden; background:#fafbfc; border-radius:8px; box-shadow:0 12px 45px rgba(0,0,0,.35); }}
.turn-detail-panel {{ width:min(1500px,94vw); }}
.turn-detail-metrics {{ grid-template-columns:repeat(6,minmax(0,1fr)); }}
.turn-mcp-count-metric, .turn-mcp-skills-metric, .turn-bash-skills-metric {{ grid-column:span 2; }}
.turn-tools-metric {{ grid-column:span 6; }}
.tool-call-header {{ display:flex; justify-content:space-between; align-items:center; gap:20px; padding:14px 2px 4px; }}
.tool-call-header h2 {{ margin:0; }}
.tool-call-close {{ color:#b3261e; font-weight:600; text-decoration:none; }}
.tool-call-panel .table-scroll {{ flex:1 1 auto; min-height:0; max-height:none; }}
.turn-detail-table {{ min-width:900px; margin:0; table-layout:fixed; }}
.turn-detail-table th, .turn-detail-table td {{ vertical-align:top; white-space:normal; }}
.turn-detail-event-highlight > td {{ background:#fff4e5; box-shadow:inset 3px 0 0 #e87523; }}
.turn-detail-table tr:focus {{ outline:2px solid #e87523; outline-offset:-2px; }}
.turn-event-anchor {{ display:none; }}
.turn-detail-table .turn-detail-index-column {{ width:4%; }}
.turn-detail-table .turn-detail-offset-column {{ width:7%; }}
.turn-detail-table .turn-detail-cost-column {{ width:7%; }}
.turn-detail-table .turn-detail-model-column {{ width:14%; }}
.turn-detail-table .turn-detail-activity-column {{ width:9%; }}
.turn-detail-table .turn-detail-arguments-column,
.turn-detail-table .turn-detail-result-column {{ width:29.5%; }}
.turn-detail-table .tool-arguments,
.turn-detail-table .tool-result-summary {{ max-width:none; }}
code {{ font-family:var(--font-code); font-size:.9em; }}
{_TREND_CHART_CSS}
{_EXECUTION_HEATMAP_CSS}
@media (max-width:900px) {{ .turn-detail-metrics {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .turn-mcp-count-metric, .turn-mcp-skills-metric, .turn-bash-skills-metric, .turn-tools-metric {{ grid-column:1 / -1; }} }}
</style></head><body>
{nav_html}
<h1{report_title_attribute}>{_escape_html(report_title)}</h1>
{run_label_html}
<p>{_escape_html(run.runtime)} run <code>{_escape_html(run.root_thread_id)}</code> · state <strong>{_escape_html(run.state)}</strong> · observed {_local_time_html(run.observed_at)} · {_escape_html(_cost_summary(run.cost))}.</p>
{view_nav_html}
{parent_context_html}
<div class="metrics">
<div class="metric"><div class="label">Processed tokens</div><div class="value">{_format_compact_count(run.usage_totals.processed_tokens)}</div></div>
<div class="metric"><div class="label">Agents used</div><div class="value">{len(run.threads):,}</div></div>
{activity_metric_cards}
<div class="metric"><div class="label">Matched tool calls</div><div class="value">{tool_count:,}</div></div>
{mcp_metric_card}
<div class="metric"><div class="label">Wall time</div><div class="value">{_format_ms(run.wall_time_ms)}</div></div>
<div class="metric"><div class="label">Tool time</div><div class="value">{_format_ms(run.tool_time_ms)}</div></div>
<div class="metric"><div class="label">Peak concurrency</div><div class="value">{run.peak_concurrency}</div></div>
</div>
<h2>Token composition</h2>
<div class="token-composition" title="Processed token composition">
<span class="token-segment fresh" style="width:{fresh_width:.3f}%"></span>
<span class="token-segment cached" style="width:{cached_width:.3f}%"></span>
{cache_write_segment}
{output_segment}
{reasoning_segment}
</div>
<div class="composition-legend"><span class="composition-fresh">Fresh input {run.usage_totals.direct_input_tokens:,}</span> · <span class="composition-cached">Cache read {run.usage_totals.cached_input_tokens:,}</span>{cache_write_legend} · <span class="composition-output">output {visible_output_tokens:,}</span> · <span class="composition-reasoning">reasoning {run.usage_totals.reasoning_tokens:,}</span></div>
{pricing_link}
{model_usage_html}
{context_metrics_html}
{inference_metrics_html}
{runtime_metrics_html}
{execution_heatmap_html}
{work_item_metrics_html}
<div id="timeline" class="agents-heading"><h2>Timeline</h2><details class="agent-info"><summary aria-label="About Timeline">ⓘ</summary><div class="agent-note-popover" role="note">{_escape_html(agent_note)}</div></details></div>
<p class="execution-note">{_escape_html(execution_note)} Expand an agent for {turn_singular}, token, cost, and tool-call detail.</p>
<div class="table-scroll"><table class="agent-table"><colgroup><col class="agent-assignment-column"><col class="agent-skills-column"><col class="agent-count-column"><col class="agent-time-column"><col class="agent-processed-column"><col class="agent-timeline-column"></colgroup><thead><tr><th>Assignment</th><th>Skills used</th><th>{agent_activity_heading}</th><th>{agent_time_heading}</th><th>Processed</th><th class="agent-timeline-header">Timeline</th></tr></thead><tbody>{agent_rows_html}</tbody></table></div>
{sequence_document_html}
{pricing_overlay}
{''.join(tool_call_overlays)}
{''.join(turn_detail_overlays)}
<script>
var localTimestampFormatter = new Intl.DateTimeFormat(undefined, {{
  dateStyle: "medium",
  timeStyle: "short"
}});
document.querySelectorAll("time.local-timestamp").forEach(function(element) {{
  var timestamp = new Date(element.dateTime);
  if (!Number.isNaN(timestamp.getTime())) {{
    element.textContent = localTimestampFormatter.format(timestamp);
    element.title = element.dateTime;
  }}
}});
var sequenceOnly =
  document.body.classList.contains("sequence-only") ||
  new URLSearchParams(window.location.search).get("view") === "sequence";
if (sequenceOnly) {{
  document.body.classList.add("sequence-only");
  document.title = "Agent sequence · " + document.title;
}}
document.querySelectorAll("[data-sequence-window]").forEach(function(link) {{
  link.addEventListener("click", function(event) {{
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    var width = Math.max(720, Math.floor(window.screen.availWidth * 0.92));
    var height = Math.max(600, Math.floor(window.screen.availHeight * 0.92));
    var popup = window.open(
      link.href,
      "_blank",
      "popup=yes,width=" + width + ",height=" + height +
        ",resizable=yes,scrollbars=yes"
    );
    if (popup) {{
      event.preventDefault();
      popup.opener = null;
    }}
  }});
}});
function initializeAgentSequence(section) {{
  var scroll = section.querySelector(".sequence-scroll");
  var canvas = section.querySelector(".sequence-canvas");
  var participantHeader = section.querySelector(".sequence-participant-header");
  var diagram = section.querySelector(".agent-sequence-diagram");
  if (!scroll || !canvas || !participantHeader || !diagram) return;

  var participants = Array.from(section.querySelectorAll(".sequence-participant"));
  var lifelines = Array.from(section.querySelectorAll(".sequence-lifeline"));
  var eventLinks = Array.from(diagram.querySelectorAll(".sequence-event-link"));
  var thoughtNodes = Array.from(
    diagram.querySelectorAll(".sequence-conversation-bubble")
  );
  var thoughtLinks = thoughtNodes.map(function(node) {{
    return node.closest(".sequence-conversation-link");
  }});
  var ledgerRows = Array.from(section.querySelectorAll(".sequence-ledger li[data-event-index]"));
  var participantGap = Number(canvas.dataset.participantGap);
  var sidePadding = Number(canvas.dataset.sidePadding);
  var headerHeight = Number(canvas.dataset.headerHeight);
  var eventHeight = Number(canvas.dataset.eventHeight);
  var footerHeight = Number(canvas.dataset.footerHeight);
  var minZoom = 0.1;
  var maxZoom = 2;
  var zoom = 1;
  var baseWidth = 760;
  var baseHeight = footerHeight;
  var collapsedThreadIds = new Set();
  var focusedThreadId = "";
  var groupRepeats = true;
  var firstVisibleActivity = null;
  var parentByThreadId = new Map();
  var participantByThreadId = new Map();
  var lifelineByThreadId = new Map();
  var ledgerByEventIndex = new Map();

  participants.forEach(function(participant) {{
    participantByThreadId.set(participant.dataset.threadId, participant);
    parentByThreadId.set(
      participant.dataset.threadId,
      participant.dataset.parentThreadId || ""
    );
  }});
  lifelines.forEach(function(lifeline) {{
    lifelineByThreadId.set(lifeline.dataset.threadId, lifeline);
  }});
  ledgerRows.forEach(function(row) {{
    ledgerByEventIndex.set(row.dataset.eventIndex, row);
  }});
  var events = eventLinks.map(function(element) {{
    return {{
      element: element,
      group: element.querySelector(".sequence-event"),
      line: element.querySelector(".sequence-line"),
      dot: element.querySelector(".sequence-source-dot"),
      hit: element.querySelector(".sequence-event-hit"),
      label: element.querySelector(".sequence-event-label"),
      band: element.querySelector(".sequence-event-band"),
      sourceId: element.dataset.sourceThreadId,
      targetId: element.dataset.targetThreadId,
      category: element.dataset.eventCategory,
      rowIndex: Number(element.dataset.rowIndex),
      sequenceOrder: Number(element.dataset.sequenceOrder),
      baseY: Number(element.dataset.baseY),
      repeatCount: Number(element.dataset.repeatCount),
      repeatIndex: Number(element.dataset.repeatIndex),
      ledger: ledgerByEventIndex.get(element.dataset.eventIndex)
    }};
  }});
  var thoughts = thoughtNodes.map(function(element) {{
    return {{
      element: element,
      rect: element.querySelector("rect"),
      tail: element.querySelector(".sequence-conversation-tail"),
      text: element.querySelector(".sequence-thinking-text"),
      textLines: Array.from(element.querySelectorAll(".sequence-thinking-line")),
      threadId: element.dataset.threadId,
      rowIndex: Number(element.dataset.rowIndex),
      sequenceOrder: Number(element.dataset.sequenceOrder),
      baseY: Number(element.dataset.baseY)
    }};
  }});

  var zoomOutButton = section.querySelector("[data-sequence-zoom-out]");
  var zoomInButton = section.querySelector("[data-sequence-zoom-in]");
  var zoomValue = section.querySelector("[data-sequence-zoom-value]");
  var fitButton = section.querySelector("[data-sequence-fit]");
  var collapseAllButton = section.querySelector("[data-sequence-collapse-all]");
  var expandAllButton = section.querySelector("[data-sequence-expand-all]");
  var clearFocusButton = section.querySelector("[data-sequence-clear-focus]");
  var groupRepeatsButton = section.querySelector("[data-sequence-group-repeats]");
  var resetButton = section.querySelector("[data-sequence-reset]");
  var filterInputs = Array.from(section.querySelectorAll("[data-sequence-event-filter]"));
  var viewStatus = section.querySelector("[data-sequence-view-status]");
  var emptyState = section.querySelector("[data-sequence-empty]");
  var ledgerSummary = section.querySelector("[data-sequence-ledger-summary]");
  var description = section.querySelector("[data-sequence-description]");
  var inspectDetail = section.querySelector("[data-sequence-inspect-detail]");
  var inspectDefault = inspectDetail.textContent;

  function showInspectDetail(value) {{ inspectDetail.textContent = value; }}
  function clearInspectDetail() {{ inspectDetail.textContent = inspectDefault; }}

  function updateZoomControls() {{
    zoomValue.textContent = Math.round(zoom * 100) + "%";
    zoomOutButton.disabled = zoom <= minZoom;
    zoomInButton.disabled = zoom >= maxZoom;
  }}

  function applyDimensions() {{
    var scaledWidth = Math.round(baseWidth * zoom);
    var scaledHeaderHeight = Math.round(headerHeight * zoom);
    var scaledHeight = Math.round(baseHeight * zoom);
    canvas.style.width = scaledWidth + "px";
    participantHeader.setAttribute("viewBox", "0 0 " + baseWidth + " " + headerHeight);
    participantHeader.setAttribute("width", String(scaledWidth));
    participantHeader.setAttribute("height", String(scaledHeaderHeight));
    diagram.setAttribute("viewBox", "0 0 " + baseWidth + " " + baseHeight);
    diagram.setAttribute("width", String(scaledWidth));
    diagram.setAttribute("height", String(scaledHeight));
    updateZoomControls();
  }}

  function setZoom(nextZoom) {{
    zoom = Math.max(minZoom, Math.min(maxZoom, nextZoom));
    applyDimensions();
  }}

  function fitSequence() {{
    var availableWidth = Math.max(320, scroll.clientWidth - 2);
    setZoom(Math.min(1, availableWidth / baseWidth));
    scroll.scrollLeft = 0;
  }}

  function revealFirstActivity() {{
    if (!firstVisibleActivity) return;
    var activityRect = firstVisibleActivity.getBoundingClientRect();
    var scrollRect = scroll.getBoundingClientRect();
    var activityCenter = (activityRect.left + activityRect.right) / 2;
    var scrollCenter = (scrollRect.left + scrollRect.right) / 2;
    var centeredLeft = scroll.scrollLeft + activityCenter - scrollCenter;
    var maxLeft = Math.max(0, scroll.scrollWidth - scroll.clientWidth);
    scroll.scrollLeft = Math.max(0, Math.min(maxLeft, Math.round(centeredLeft)));
    scroll.scrollTop = 0;
  }}

  function hiddenByCollapsedAncestor(threadId) {{
    var parentId = parentByThreadId.get(threadId) || "";
    var visited = new Set();
    while (parentId && !visited.has(parentId)) {{
      if (collapsedThreadIds.has(parentId)) return true;
      visited.add(parentId);
      parentId = parentByThreadId.get(parentId) || "";
    }}
    return false;
  }}

  function focusThreadIds() {{
    if (!focusedThreadId) return null;
    var ids = new Set([focusedThreadId]);
    events.forEach(function(event) {{
      if (event.sourceId === focusedThreadId) ids.add(event.targetId);
      if (event.targetId === focusedThreadId) ids.add(event.sourceId);
    }});
    return ids;
  }}

  function updateParticipantControl(participant) {{
    var threadId = participant.dataset.threadId;
    var focusTarget = participant.querySelector(".sequence-focus-target");
    var hierarchyToggle = participant.querySelector(".sequence-hierarchy-toggle");
    focusTarget.setAttribute(
      "aria-pressed",
      threadId === focusedThreadId ? "true" : "false"
    );
    if (!hierarchyToggle) return;
    var collapsed = collapsedThreadIds.has(threadId);
    hierarchyToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    hierarchyToggle.setAttribute(
      "aria-label",
      (collapsed ? "Expand" : "Collapse") +
        " descendants of " + participant.dataset.participantName
    );
    hierarchyToggle.querySelector("text").textContent = collapsed ? "+" : "−";
  }}

  function layoutSequence() {{
    var focusIds = focusThreadIds();
    var visibleParticipants = participants.filter(function(participant) {{
      var threadId = participant.dataset.threadId;
      if (focusIds && !focusIds.has(threadId)) return false;
      if (threadId === focusedThreadId) return true;
      return !hiddenByCollapsedAncestor(threadId);
    }});
    var visibleThreadIds = new Set(
      visibleParticipants.map(function(participant) {{ return participant.dataset.threadId; }})
    );
    var xByThreadId = new Map();
    visibleParticipants.forEach(function(participant, index) {{
      var threadId = participant.dataset.threadId;
      var x = sidePadding + index * participantGap;
      xByThreadId.set(threadId, x);
      participant.setAttribute("transform", "translate(" + x + " 0)");
    }});
    participants.forEach(function(participant) {{
      var visible = visibleThreadIds.has(participant.dataset.threadId);
      participant.classList.toggle("sequence-hidden", !visible);
      updateParticipantControl(participant);
    }});

    baseWidth = Math.max(
      760,
      sidePadding * 2 + participantGap * Math.max(0, visibleParticipants.length - 1)
    );
    var enabledCategories = new Set(
      filterInputs.filter(function(input) {{ return input.checked; }}).map(
        function(input) {{ return input.dataset.sequenceEventFilter; }}
      )
    );
    var visibleEvents = [];
    events.forEach(function(event) {{
      var visible =
        enabledCategories.has(event.category) &&
        visibleThreadIds.has(event.sourceId) &&
        visibleThreadIds.has(event.targetId) &&
        (!focusedThreadId ||
          event.sourceId === focusedThreadId ||
          event.targetId === focusedThreadId) &&
        (!groupRepeats || event.repeatIndex === 0);
      event.element.classList.toggle("sequence-hidden", !visible);
      if (event.ledger) event.ledger.classList.toggle("sequence-hidden", !visible);
      if (visible) visibleEvents.push(event);
    }});
    var visibleThoughts = [];
    thoughts.forEach(function(thought) {{
      var visible =
        enabledCategories.has("thinking") &&
        visibleThreadIds.has(thought.threadId);
      thought.element.classList.toggle("sequence-hidden", !visible);
      if (visible) visibleThoughts.push(thought);
    }});
    var visibleTimelineRows = visibleEvents.map(function(event) {{
      return {{ sequenceOrder: event.sequenceOrder, event: event }};
    }}).concat(visibleThoughts.map(function(thought) {{
      return {{ sequenceOrder: thought.sequenceOrder, thought: thought }};
    }}));
    visibleTimelineRows.sort(function(left, right) {{
      return left.sequenceOrder - right.sequenceOrder;
    }});

    firstVisibleActivity = null;
    if (visibleTimelineRows.length) {{
      var firstEntry = visibleTimelineRows[0];
      firstVisibleActivity = firstEntry.event
        ? firstEntry.event.element
        : firstEntry.thought.element;
    }}

    baseHeight = eventHeight * visibleTimelineRows.length + footerHeight;
    visibleTimelineRows.forEach(function(entry, index) {{
      var y = index * eventHeight + 34;
      if (entry.event) {{
        var event = entry.event;
        var sourceX = xByThreadId.get(event.sourceId);
        var targetX = xByThreadId.get(event.targetId);
        event.group.setAttribute("transform", "translate(0 " + (y - event.baseY) + ")");
        event.line.setAttribute("x1", String(sourceX));
        event.line.setAttribute("x2", String(targetX));
        event.dot.setAttribute("cx", String(sourceX));
        event.hit.setAttribute("cx", String(targetX));
        event.label.setAttribute("x", String((sourceX + targetX) / 2));
        event.band.setAttribute("width", String(baseWidth));
        return;
      }}
      var thought = entry.thought;
      var thoughtX = xByThreadId.get(thought.threadId);
      thought.rect.setAttribute("x", "-98");
      thought.tail.setAttribute("d", "M -8 22 L 0 30 L 8 22 Z");
      thought.text.setAttribute("x", "0");
      thought.textLines.forEach(function(line) {{
        line.setAttribute("x", "0");
      }});
      thought.element.setAttribute(
        "transform",
        "translate(" + thoughtX + " " + y + ")"
      );
    }});
    lifelines.forEach(function(lifeline) {{
      var threadId = lifeline.dataset.threadId;
      var visible = visibleThreadIds.has(threadId);
      lifeline.classList.toggle("sequence-hidden", !visible);
      if (!visible) return;
      var x = xByThreadId.get(threadId);
      lifeline.setAttribute("x1", String(x));
      lifeline.setAttribute("x2", String(x));
      lifeline.setAttribute("y2", String(Math.max(14, baseHeight - 16)));
    }});

    section.classList.toggle("sequence-group-repeats", groupRepeats);
    groupRepeatsButton.setAttribute("aria-pressed", groupRepeats ? "true" : "false");
    clearFocusButton.disabled = !focusedThreadId;
    emptyState.hidden = visibleTimelineRows.length !== 0;
    var statusText = visibleParticipants.length + " of " + participants.length +
      (participants.length === 1 ? " agent · " : " agents · ") +
      visibleEvents.length + " of " + events.length +
      (events.length === 1 ? " event · " : " events · ") +
      visibleThoughts.length + " of " + thoughts.length +
      (thoughts.length === 1 ? " thought" : " thoughts");
    if (focusedThreadId && participantByThreadId.has(focusedThreadId)) {{
      statusText = "Focus: " +
        participantByThreadId.get(focusedThreadId).dataset.participantName + " · " +
        statusText;
    }}
    viewStatus.textContent = statusText;
    participantHeader.setAttribute("aria-label", statusText);
    description.textContent = visibleEvents.length + " visible events and " +
      visibleThoughts.length + " visible thinking summaries across " +
      visibleParticipants.length + " visible agent lifelines.";
    ledgerSummary.textContent = visibleEvents.length === events.length
      ? "Event ledger · " + events.length.toLocaleString() + " recorded events"
      : "Event ledger · " + visibleEvents.length.toLocaleString() + " of " +
        events.length.toLocaleString() + " visible events";
    applyDimensions();
  }}

  function activateWithKeyboard(element, action) {{
    element.addEventListener("keydown", function(event) {{
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      action();
    }});
  }}

  participants.forEach(function(participant) {{
    var threadId = participant.dataset.threadId;
    var focusTarget = participant.querySelector(".sequence-focus-target");
    var selectFocus = function() {{
      focusedThreadId = focusedThreadId === threadId ? "" : threadId;
      layoutSequence();
      scroll.scrollLeft = 0;
    }};
    focusTarget.addEventListener("click", selectFocus);
    activateWithKeyboard(focusTarget, selectFocus);
    focusTarget.addEventListener("pointerenter", function() {{
      showInspectDetail(participant.dataset.participantName);
    }});
    focusTarget.addEventListener("pointerleave", clearInspectDetail);
    focusTarget.addEventListener("focus", function() {{
      showInspectDetail(participant.dataset.participantName);
    }});
    focusTarget.addEventListener("blur", clearInspectDetail);
    var hierarchyToggle = participant.querySelector(".sequence-hierarchy-toggle");
    if (!hierarchyToggle) return;
    var toggleHierarchy = function() {{
      if (collapsedThreadIds.has(threadId)) collapsedThreadIds.delete(threadId);
      else collapsedThreadIds.add(threadId);
      layoutSequence();
    }};
    hierarchyToggle.addEventListener("click", toggleHierarchy);
    activateWithKeyboard(hierarchyToggle, toggleHierarchy);
  }});

  thoughtLinks.forEach(function(link) {{
    if (!link) return;
    var showThought = function() {{
      showInspectDetail(link.getAttribute("aria-label") || "Thinking detail");
    }};
    link.addEventListener("pointerenter", showThought);
    link.addEventListener("pointerleave", clearInspectDetail);
    link.addEventListener("focus", showThought);
    link.addEventListener("blur", clearInspectDetail);
  }});

  zoomOutButton.addEventListener("click", function() {{ setZoom(zoom - 0.15); }});
  zoomInButton.addEventListener("click", function() {{ setZoom(zoom + 0.15); }});
  fitButton.addEventListener("click", fitSequence);
  collapseAllButton.addEventListener("click", function() {{
    participants.forEach(function(participant) {{
      if (participant.querySelector(".sequence-hierarchy-toggle")) {{
        collapsedThreadIds.add(participant.dataset.threadId);
      }}
    }});
    layoutSequence();
    scroll.scrollLeft = 0;
  }});
  expandAllButton.addEventListener("click", function() {{
    collapsedThreadIds.clear();
    layoutSequence();
  }});
  clearFocusButton.addEventListener("click", function() {{
    focusedThreadId = "";
    layoutSequence();
  }});
  groupRepeatsButton.addEventListener("click", function() {{
    groupRepeats = !groupRepeats;
    layoutSequence();
  }});
  resetButton.addEventListener("click", function() {{
    collapsedThreadIds.clear();
    focusedThreadId = "";
    groupRepeats = true;
    filterInputs.forEach(function(input) {{ input.checked = true; }});
    zoom = 1;
    layoutSequence();
    revealFirstActivity();
  }});
  filterInputs.forEach(function(input) {{
    input.addEventListener("change", layoutSequence);
  }});
  layoutSequence();
  requestAnimationFrame(revealFirstActivity);
}}
var sequenceSection = document.getElementById("agent-sequence");
if (sequenceOnly && sequenceSection) initializeAgentSequence(sequenceSection);
document.querySelectorAll(".agent-summary-row").forEach(function(row) {{
  var button = row.querySelector(".agent-row-toggle");
  var detail = document.getElementById(row.dataset.agentDetail);
  if (!button || !detail) return;
  function toggleAgentDetail() {{
    var expanded = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", expanded ? "false" : "true");
    detail.hidden = expanded;
    row.classList.toggle("is-expanded", !expanded);
  }}
  button.addEventListener("click", function(event) {{
    event.stopPropagation();
    toggleAgentDetail();
  }});
  row.addEventListener("click", function(event) {{
    if (event.target.closest("a, button, details, summary")) return;
    toggleAgentDetail();
  }});
}});
document.querySelectorAll(".clamped-less").forEach(function(button) {{
  button.addEventListener("click", function(event) {{
    event.stopPropagation();
    var disclosure = button.closest(".clamped-disclosure");
    if (disclosure) disclosure.open = false;
  }});
}});
document.addEventListener("click", function(event) {{
  var link = event.target.closest("[data-turn-detail-link]");
  if (!link) return;
  var targetId = (link.getAttribute("href") || "").replace(/^#/, "");
  var overlay = document.getElementById(targetId);
  if (!overlay) return;
  var closeLink = overlay.querySelector(".tool-call-close");
  if (closeLink) closeLink.setAttribute("href", link.dataset.returnTarget || "#timeline");
  requestAnimationFrame(function() {{
    document.querySelectorAll(".turn-detail-event-highlight").forEach(function(row) {{
      row.classList.remove("turn-detail-event-highlight");
    }});
    if (!link.dataset.turnEventTarget) return;
    var eventTarget = document.getElementById(link.dataset.turnEventTarget);
    var eventRow = eventTarget ? eventTarget.closest("tr") : null;
    if (!eventRow || !overlay.contains(eventRow)) return;
    eventRow.classList.add("turn-detail-event-highlight");
    eventRow.setAttribute("tabindex", "-1");
    eventRow.scrollIntoView({{ block:"center", inline:"nearest" }});
    eventRow.focus({{ preventScroll:true }});
  }});
}});
{_TREND_CHART_SCRIPT}
document.querySelectorAll("[data-trend-view]").forEach(initializeTrendView);
{_EXECUTION_HEATMAP_SCRIPT}
var executionHeatmap = document.getElementById("execution-heatmap");
if (executionHeatmap && !sequenceOnly) initializeExecutionHeatmap(executionHeatmap);
</script>
</body></html>"""


@dataclass(frozen=True)
class _TokenSummaryRow:
    path: Path
    user_id: str
    started_at: datetime
    last_activity_at: datetime
    usage: UsageTotals
    cost: CostAssessment
    plan_labels: tuple[str, ...] = ()
    subscription_usage: UsageTotals = field(default_factory=UsageTotals)
    subscription_cost: CostAssessment = field(
        default_factory=lambda: CostAssessment(status="unavailable")
    )
    credit_usage: UsageTotals = field(default_factory=UsageTotals)
    credit_cost: CostAssessment = field(
        default_factory=lambda: CostAssessment(status="unavailable")
    )
    allocated_credits_used: float = 0.0
    funding_events: tuple[_TokenFundingEvent, ...] = ()


_TOKEN_SUMMARY_DETAIL_COLUMNS = (
    "user_id", "folder", "filename", "started_at", "last_activity_at",
    "plan", "sub_start", "sub_end", "sub_remaining", "credits_start",
    "credits_end", "credits_used", "credits_remaining", "sub_tokens",
    "sub_est_usd", "credit_tokens", "credit_est_usd", "input_tokens",
    "input_est_usd", "cached_input_tokens", "cached_input_est_usd",
    "uncached_input_tokens", "output_tokens", "output_est_usd",
    "reasoning_tokens", "processed_tokens", "total_est_usd",
)
_TOKEN_SUMMARY_GROUP_COLUMNS = (
    "user_id", "folder", "plan", "sub_tokens", "sub_est_usd",
    "sub_remaining", "credit_tokens", "credit_est_usd", "credits_used",
    "credits_remaining", "total_tokens", "total_est_usd",
)


def _load_token_summary_config(path: Path) -> dict[str, object]:
    """Load one bounded token-summary YAML mapping."""
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read token summary config {path}: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError("Token summary config must contain a YAML mapping")
    allowed = {
        "mode", "directories", "from", "to", "csv", "html", "threads",
    }
    unknown = sorted(str(key) for key in loaded if key not in allowed)
    if unknown:
        raise ValueError(f"Unknown token summary config field(s): {', '.join(unknown)}")
    return loaded


def _token_summary_datetime(value: object, field_name: str) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    local_match = re.fullmatch(
        r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?",
        text,
    )
    if local_match is not None:
        try:
            local_value = datetime.strptime(
                text.replace("T", " "),
                "%Y-%m-%d %H:%M" if " " in text.replace("T", " ") else "%Y-%m-%d",
            )
        except ValueError:
            local_value = None
        if local_value is not None:
            return local_value.astimezone(timezone.utc)
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        raise ValueError(
            f"{field_name} must be a local YYYY-MM-DD date with an optional "
            "HH:mm time, or an ISO 8601 timestamp with an offset"
        )
    return parsed.astimezone(timezone.utc)


def _token_summary_default_range(
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return the UI's default local-day From and To (exclusive) values."""
    local_now = now or datetime.now().astimezone()
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight, local_midnight + timedelta(days=1)


def _token_summary_rows(
    directories: list[Path],
    *,
    from_time: datetime,
    to_time: datetime,
    emit_progress: bool = False,
) -> list[_TokenSummaryRow]:
    """Parse each unique Codex rollout overlapping the selected UI range."""
    candidates: set[Path] = set()
    for directory in directories:
        if not directory.is_dir():
            raise ValueError(f"Token summary directory not found: {directory}")
        candidates.update(
            path.resolve() for path in directory.rglob("*.jsonl") if path.is_file()
        )
    selected_candidates: list[tuple[Path, datetime]] = []
    for path in sorted(candidates):
        last_activity_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if last_activity_at < from_time:
            continue
        if _rollout_identity(path) is None:
            continue
        selected_candidates.append((path, last_activity_at))
    rows: list[_TokenSummaryRow] = []
    for index, (path, last_activity_at) in enumerate(selected_candidates, start=1):
        if emit_progress:
            print(
                f"Reading {index:,} of {len(selected_candidates):,}: {path.name}",
                file=sys.stderr,
                flush=True,
            )
        funding_events: list[_TokenFundingEvent] = []
        thread = parse_codex_rollout(path, token_funding_events=funding_events)
        funding_events = [
            event
            for event in funding_events
            if (
                (event_time := _parse_iso_datetime(event.event_timestamp)) is not None
                and from_time <= event_time.astimezone(timezone.utc) < to_time
            )
        ]
        usage, cost = _token_summary_usage_cost(funding_events)
        if usage.processed_tokens == 0:
            continue
        started_at = _parse_iso_datetime(thread.started_at) or last_activity_at
        started_at = started_at.astimezone(timezone.utc)
        if started_at >= to_time:
            continue
        try:
            user_id = path.owner()
        except (KeyError, NotImplementedError, OSError):
            user_id = getpass.getuser()
        rows.append(
            _TokenSummaryRow(
                path=path,
                user_id=user_id,
                started_at=started_at,
                last_activity_at=last_activity_at,
                usage=usage,
                cost=cost,
                funding_events=tuple(funding_events),
            )
        )
    rows_by_user: dict[str, list[_TokenSummaryRow]] = {}
    for row in rows:
        rows_by_user.setdefault(row.user_id, []).append(row)
    classified_events: list[_TokenFundingEvent] = []
    for user_rows in rows_by_user.values():
        classified_events.extend(
            _token_summary_classify_events(
                [event for row in user_rows for event in row.funding_events]
            )
        )
    events_by_path: dict[str, list[_TokenFundingEvent]] = {}
    for event in classified_events:
        events_by_path.setdefault(event.source_path, []).append(event)
    classified_rows: list[_TokenSummaryRow] = []
    for row in rows:
        row_events = events_by_path.get(str(row.path), [])
        funding = _token_summary_funding(row_events)
        classified_rows.append(
            replace(
                row,
                plan_labels=funding["plan_labels"],
                subscription_usage=funding["subscription_usage"],
                subscription_cost=funding["subscription_cost"],
                credit_usage=funding["credit_usage"],
                credit_cost=funding["credit_cost"],
                funding_events=tuple(row_events),
            )
        )
    allocated_rows: list[_TokenSummaryRow] = []
    for user_id in rows_by_user:
        matching = [row for row in classified_rows if row.user_id == user_id]
        allocated_rows.extend(_token_summary_allocate_credits(matching))
    return sorted(allocated_rows, key=lambda row: str(row.path))


def _cost_value(value: float | None) -> object:
    return f"{0.0 if value is None else value:.8f}"


def _token_summary_classify_events(
    events: list[_TokenFundingEvent],
) -> list[_TokenFundingEvent]:
    """Classify usage inside the observed account credit interval."""
    ordered = sorted(
        events,
        key=lambda item: (item.event_timestamp, item.source_path, item.source_ordinal),
    )
    positive_indices = [
        index
        for index, event in enumerate(ordered)
        if event.has_credits is True
        and event.credit_balance is not None
        and event.credit_balance > 0
    ]
    if not positive_indices:
        return [replace(event, funding_source="subscription") for event in ordered]
    start_index = positive_indices[0]
    last_positive_index = positive_indices[-1]
    end_index = next(
        (
            index
            for index in range(last_positive_index + 1, len(ordered))
            if ordered[index].has_credits is False
            and ordered[index].credit_balance is not None
            and ordered[index].credit_balance <= 0
        ),
        len(ordered) - 1,
    )
    classified: list[_TokenFundingEvent] = []
    for index, event in enumerate(ordered):
        subscription_available = (
            event.subscription_used_percent is not None
            and event.subscription_used_percent < 100
        )
        source = (
            "credits"
            if start_index <= index <= end_index and not subscription_available
            else "subscription"
        )
        classified.append(replace(event, funding_source=source))
    return classified


def _token_summary_usage_cost(
    events: list[_TokenFundingEvent],
) -> tuple[UsageTotals, CostAssessment]:
    """Return one non-overlapping usage total and its model-aware estimate."""
    usage = UsageTotals()
    model_usage: dict[str, UsageTotals] = {}
    plan_types: set[str] = set()
    for event in events:
        usage += event.usage
        if event.model and not _usage_is_zero(event.usage):
            model_usage[event.model] = (
                model_usage.get(event.model, UsageTotals()) + event.usage
            )
        if event.plan_type:
            plan_types.add(event.plan_type)
    return usage, _cost_for_usage(usage, model_usage, plan_types=plan_types)


def _token_summary_allocate_credits(
    rows: list[_TokenSummaryRow],
) -> list[_TokenSummaryRow]:
    """Allocate observed account burn using model-aware token-cost weights."""
    events = [event for row in rows for event in row.funding_events]
    *_, observed_burn = _token_summary_limit_values(events)
    burn = observed_burn or 0.0
    eligible = [row for row in rows if row.credit_usage.processed_tokens > 0]
    weights = [row.credit_cost.total_cost or 0.0 for row in eligible]
    if eligible and sum(weights) <= 0:
        weights = [float(row.credit_usage.processed_tokens) for row in eligible]
    total_weight = sum(weights)
    allocations: dict[Path, float] = {}
    allocated = 0.0
    for index, (row, weight) in enumerate(zip(eligible, weights, strict=True)):
        share = (
            round(burn - allocated, 8)
            if index == len(eligible) - 1
            else round(burn * weight / total_weight, 8)
        )
        allocations[row.path] = share
        allocated += share
    return [
        replace(row, allocated_credits_used=allocations.get(row.path, 0.0))
        for row in rows
    ]


def _token_summary_funding(
    events: list[_TokenFundingEvent],
) -> dict[str, object]:
    usages = {source: UsageTotals() for source in ("subscription", "credits")}
    model_usages: dict[str, dict[str, UsageTotals]] = {
        "subscription": {},
        "credits": {},
    }
    plan_types: set[str] = set()
    for event in sorted(
        events,
        key=lambda item: (item.event_timestamp, item.source_path, item.source_ordinal),
    ):
        if event.plan_type:
            plan_types.add(event.plan_type)
        if _usage_is_zero(event.usage):
            continue
        source = event.funding_source
        if source not in usages:
            source = "subscription"
        usages[source] = usages[source] + event.usage
        if source in model_usages and event.model:
            models = model_usages[source]
            models[event.model] = models.get(event.model, UsageTotals()) + event.usage
    labels = sorted(plan_types, key=str.casefold)
    if not _usage_is_zero(usages["credits"]):
        labels.append("credits")
    return {
        "plan_labels": tuple(labels),
        "subscription_usage": usages["subscription"],
        "subscription_cost": _cost_for_usage(
            usages["subscription"],
            model_usages["subscription"],
            plan_types=plan_types,
        ),
        "credit_usage": usages["credits"],
        "credit_cost": _cost_for_usage(
            usages["credits"],
            model_usages["credits"],
            plan_types=plan_types,
        ),
    }


def _token_summary_limit_values(
    events: list[_TokenFundingEvent],
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """Return observed subscription endpoints and a stale-safe credit burn-down."""
    ordered = sorted(
        events,
        key=lambda item: (item.event_timestamp, item.source_path, item.source_ordinal),
    )
    subscription = [
        event.subscription_used_percent
        for event in ordered
        if event.subscription_used_percent is not None
    ]
    balances = [
        (index, event.credit_balance)
        for index, event in enumerate(ordered)
        if event.credit_balance is not None
    ]
    credits_start: float | None = None
    credits_end: float | None = None
    credits_used: float | None = None
    if balances:
        peak_index, credits_start = max(balances, key=lambda item: item[1])
        credits_end = min(
            balance for index, balance in balances if index >= peak_index
        )
        credits_used = max(0.0, credits_start - credits_end)
    return (
        subscription[0] if subscription else None,
        max(subscription) if subscription else None,
        credits_start,
        credits_end,
        credits_used,
    )


def _sum_cost(rows: list[_TokenSummaryRow], attribute: str) -> float | None:
    values = [
        getattr(getattr(row, attribute), "total_cost")
        for row in rows
        if getattr(getattr(row, attribute), "total_cost") is not None
    ]
    return sum(values) if values else None


def _token_summary_rollup(rows: list[_TokenSummaryRow]) -> dict[str, object]:
    usage = UsageTotals()
    subscription_usage = UsageTotals()
    credit_usage = UsageTotals()
    label_set: set[str] = set()
    events: list[_TokenFundingEvent] = []
    for row in rows:
        usage += row.usage
        subscription_usage += row.subscription_usage
        credit_usage += row.credit_usage
        events.extend(row.funding_events)
        label_set.update(row.plan_labels)
    labels = sorted(label_set.difference({"credits"}), key=str.casefold)
    if "credits" in label_set:
        labels.append("credits")
    subscription_start, subscription_end, credits_start, credits_end, _ = (
        _token_summary_limit_values(events)
    )
    subscription_remaining = (
        None if subscription_end is None else max(0.0, 100.0 - subscription_end)
    )
    allocated_credits_used = sum(row.allocated_credits_used for row in rows)
    return {
        "plan": ", ".join(labels),
        "sub_start": _cost_value(subscription_start),
        "sub_end": _cost_value(subscription_end),
        "sub_remaining": _cost_value(subscription_remaining),
        "credits_start": _cost_value(credits_start),
        "credits_end": _cost_value(credits_end),
        "credits_used": _cost_value(allocated_credits_used),
        "credits_remaining": _cost_value(credits_end),
        "sub_tokens": subscription_usage.processed_tokens,
        "sub_est_usd": _cost_value(_sum_cost(rows, "subscription_cost")),
        "credit_tokens": credit_usage.processed_tokens,
        "credit_est_usd": _cost_value(_sum_cost(rows, "credit_cost")),
        "total_tokens": usage.processed_tokens,
        "total_est_usd": _cost_value(_sum_cost(rows, "cost")),
    }


def _token_summary_detail_values(row: _TokenSummaryRow) -> list[object]:
    usage = row.usage
    cost = row.cost
    rollup = _token_summary_rollup([row])
    return [
        row.user_id, str(row.path.parent), row.path.name,
        _token_summary_local_datetime(row.started_at),
        _token_summary_local_datetime(row.last_activity_at),
        rollup["plan"], rollup["sub_start"], rollup["sub_end"],
        rollup["sub_remaining"], rollup["credits_start"],
        rollup["credits_end"], rollup["credits_used"],
        rollup["credits_remaining"], rollup["sub_tokens"],
        rollup["sub_est_usd"], rollup["credit_tokens"],
        rollup["credit_est_usd"], usage.input_tokens, _cost_value(cost.input_cost),
        usage.cached_input_tokens, _cost_value(cost.cached_input_cost),
        usage.uncached_input_tokens, usage.output_tokens,
        _cost_value(cost.output_cost), usage.reasoning_tokens,
        usage.processed_tokens, _cost_value(cost.total_cost),
    ]


def _token_summary_local_datetime(
    value: datetime, local_timezone: tzinfo | None = None
) -> str:
    """Format a timestamp in local time using the desktop UI's date-time form."""
    return value.astimezone(local_timezone).strftime("%Y-%m-%d %H:%M")


def _token_summary_groups(
    rows: list[_TokenSummaryRow],
) -> list[tuple[tuple[str, str], list[_TokenSummaryRow]]]:
    """Group token-summary rows exactly as the default terminal report does."""
    groups: dict[tuple[str, str], list[_TokenSummaryRow]] = {}
    for row in rows:
        key = (row.user_id, str(row.path.parent))
        groups.setdefault(key, []).append(row)
    return sorted(groups.items())


def _token_summary_group_values(rows: list[_TokenSummaryRow]) -> list[list[object]]:
    values: list[list[object]] = []
    for (user_id, folder), group_rows in _token_summary_groups(rows):
        rollup = _token_summary_rollup(group_rows)
        values.append(
            [user_id, folder]
            + [rollup[column] for column in _TOKEN_SUMMARY_GROUP_COLUMNS[2:]]
        )
    return values


def _token_summary_output(
    rows: list[_TokenSummaryRow], *, details: bool
) -> tuple[tuple[str, ...], list[list[object]]]:
    if details:
        return (
            _TOKEN_SUMMARY_DETAIL_COLUMNS,
            [_token_summary_detail_values(row) for row in rows],
        )
    return _TOKEN_SUMMARY_GROUP_COLUMNS, _token_summary_group_values(rows)


def _write_token_summary_csv(
    rows: list[_TokenSummaryRow], destination: str, *, details: bool
) -> None:
    handle = (
        sys.stdout
        if destination == "-"
        else Path(destination).open("w", encoding="utf-8", newline="")
    )
    try:
        writer = csv.writer(handle, lineterminator="\n")
        columns, values = _token_summary_output(rows, details=details)
        writer.writerow(columns)
        writer.writerows(values)
    finally:
        if handle is not sys.stdout:
            handle.close()


def _token_summary_model_rollup(
    rows: list[_TokenSummaryRow],
) -> list[tuple[str, UsageTotals, CostAssessment]]:
    """Return model-aware usage and price totals for the selected events."""
    usages: dict[str, UsageTotals] = {}
    plan_types: dict[str, set[str]] = {}
    for row in rows:
        for event in row.funding_events:
            if _usage_is_zero(event.usage):
                continue
            model = event.model or "unknown"
            usages[model] = usages.get(model, UsageTotals()) + event.usage
            if event.plan_type:
                plan_types.setdefault(model, set()).add(event.plan_type)
    result: list[tuple[str, UsageTotals, CostAssessment]] = []
    for model in sorted(usages, key=str.casefold):
        usage = usages[model]
        model_usage = {} if model == "unknown" else {model: usage}
        result.append(
            (
                model,
                usage,
                _cost_for_usage(
                    usage,
                    model_usage,
                    plan_types=plan_types.get(model, set()),
                ),
            )
        )
    return result


def _token_summary_html_currency(value: object) -> str:
    return f"${float(value):,.2f}"


def _token_summary_html_credits(value: object) -> str:
    """Format credit units as whole numbers without implying currency cents."""
    return f"{float(value):,.0f}"


def _token_summary_html_cell(value: object) -> str:
    return _escape_html(str(value))


@lru_cache(maxsize=1)
def _load_token_ledger_engine():
    """Load the bundled audit-grade token ledger engine beside this script."""
    module_path = Path(__file__).resolve().with_name("token_ledger.py")
    spec = importlib.util.spec_from_file_location("_agent_report_token_ledger", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load bundled token ledger engine: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _token_summary_source_range(row: dict[str, str]) -> tuple[int, int] | None:
    source_range = row.get("_source_range", "")
    match = re.search(r"raw lines (\d+)(?:[–-](\d+))?", source_range)
    if match is not None:
        return int(match.group(1)), int(match.group(2) or match.group(1))
    source_line = row.get("_source_line", "")
    if source_line.isdigit():
        ordinal = int(source_line)
        return ordinal, ordinal
    return None


def _token_summary_local_ledger_time(value: str) -> str:
    prefix = "before " if value.startswith("before ") else ""
    parsed = _parse_iso_datetime(value.removeprefix("before "))
    if parsed is None:
        return value
    return prefix + parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _render_token_summary_ledger_html(
    row: _TokenSummaryRow,
    *,
    from_time: datetime,
    to_time: datetime,
    report_filename: str,
    threads_filename: str,
    raw_path: Path,
    thread_title: str,
    ledger_csv_path: Path,
) -> str:
    """Render the audit-grade execution-cycle ledger for one thread."""
    engine = _load_token_ledger_engine()
    headers, ledger_rows = engine.build_ledger_from_rollout(
        row.path,
        ledger_csv_path,
        pricing_path=PRICING_FILE,
    )
    funding_headers = list(engine.TOKEN_SUMMARY_FUNDING_HEADERS)
    model_index = headers.index("model") + 1
    headers = headers[:model_index] + funding_headers + headers[model_index:]
    selected_events = sorted(
        row.funding_events,
        key=lambda event: (event.source_ordinal, event.event_timestamp),
    )
    enriched_rows: list[dict[str, str]] = []
    for ledger_row in ledger_rows:
        source_range = _token_summary_source_range(ledger_row)
        matching_events = []
        if source_range is not None:
            matching_events = [
                event
                for event in selected_events
                if source_range[0] <= event.source_ordinal <= source_range[1]
            ]
        funding_event = matching_events[-1] if matching_events else None
        measured_row = ledger_row.get("total_tokens", "") != ""
        timestamp = _parse_iso_datetime(ledger_row.get("time_utc", ""))
        if measured_row and funding_event is None:
            continue
        if not measured_row and timestamp is not None:
            if not (from_time <= timestamp < to_time):
                continue
        if funding_event is not None:
            ledger_row["model"] = funding_event.model or ledger_row.get("model", "")
            ledger_row["plan"] = funding_event.plan_type or "not observed"
            ledger_row["funding"] = funding_event.funding_source
            ledger_row["sub_remaining"] = (
                "not observed"
                if funding_event.subscription_used_percent is None
                else f"{max(0.0, 100.0 - funding_event.subscription_used_percent):g}%"
            )
            ledger_row["credits_available"] = (
                "not observed"
                if funding_event.has_credits is None
                else "yes" if funding_event.has_credits else "no"
            )
            ledger_row["credits_remaining"] = (
                "not observed"
                if funding_event.credit_balance is None
                else f"{funding_event.credit_balance:g}"
            )
        ledger_row["time_utc"] = _token_summary_local_ledger_time(
            ledger_row.get("time_utc", "")
        )
        source_line = ledger_row.get("_source_line", "")
        if source_line:
            ledger_row["_source_href"] = f"{raw_path.name}#L{source_line}"
        enriched_rows.append(ledger_row)
    for index, ledger_row in enumerate(enriched_rows):
        ledger_row["row"] = str(index)
    engine.write_csv_atomically(ledger_csv_path, headers, enriched_rows)
    return engine.render_html(
        headers,
        enriched_rows,
        title="Thread Token Usage",
        source_name=row.path.name,
        source_href=raw_path.name,
        subtitle_label="Thread Title",
        subtitle_value=thread_title,
        explanation_html="",
        explanation_name=None,
        nav_links=(
            ("Overall Usage", f"../{report_filename}"),
            ("Threads in Folder", threads_filename),
        ),
        local_time=True,
    )


def _render_token_summary_html(
    rows: list[_TokenSummaryRow],
    *,
    from_time: datetime,
    to_time: datetime,
    directories: list[Path],
    group_links: dict[tuple[str, str], str] | None = None,
    all_threads_link: str | None = None,
) -> str:
    """Render one self-contained verification-oriented token usage report."""
    rollup = _token_summary_rollup(rows)
    total_tokens = int(rollup["total_tokens"])
    sub_tokens = int(rollup["sub_tokens"])
    credit_tokens = int(rollup["credit_tokens"])
    credits_used = float(rollup["credits_used"])
    credits_remaining = float(rollup["credits_remaining"])
    total_estimate = float(rollup["total_est_usd"])
    sub_estimate = float(rollup["sub_est_usd"])
    credit_estimate = float(rollup["credit_est_usd"])
    usage_per_credit = credit_estimate / credits_used if credits_used > 0 else 0.0
    sub_share = 100.0 * sub_tokens / total_tokens if total_tokens else 0.0
    credit_share = 100.0 * credit_tokens / total_tokens if total_tokens else 0.0
    local_from = _token_summary_local_datetime(from_time)
    local_to = _token_summary_local_datetime(to_time)

    model_rows: list[str] = []
    for model, usage, cost in _token_summary_model_rollup(rows):
        model_rows.append(
            "<tr>"
            f"<th scope=\"row\">{_token_summary_html_cell(model)}</th>"
            f"<td>{usage.input_tokens:,}</td>"
            f"<td>{usage.cached_input_tokens:,}</td>"
            f"<td>{usage.uncached_input_tokens:,}</td>"
            f"<td>{usage.output_tokens:,}</td>"
            f"<td>{usage.reasoning_tokens:,}</td>"
            f"<td>{usage.processed_tokens:,}</td>"
            f"<td>{_token_summary_html_currency(cost.total_cost or 0)}</td>"
            "</tr>"
        )
    if not model_rows:
        model_rows.append(
            '<tr><td colspan="8" class="empty">No token usage was found in this range.</td></tr>'
        )

    group_rows_html: list[str] = []
    for key, group_rows in _token_summary_groups(rows):
        user_id, folder = key
        group_rollup = _token_summary_rollup(group_rows)
        group_started_at = min(row.started_at for row in group_rows)
        group_last_activity_at = max(row.last_activity_at for row in group_rows)
        thread_count = len(group_rows)
        thread_word = "Thread" if thread_count == 1 else "Threads"
        group_href = group_links.get(key) if group_links is not None else None
        thread_cell = (
            f'<a href="{_escape_html_attribute(quote(group_href, safe="/:%"))}">'
            f"View {thread_count:,} {thread_word}</a>"
            if group_href is not None
            else f"{thread_count:,} {thread_word}"
        )
        search_value = f"{user_id} {group_rollup['plan']} {folder}".casefold()
        group_rows_html.append(
            f'<tr data-search="{_escape_html_attribute(search_value)}">'
            f'<td class="nowrap">{_token_summary_html_cell(_token_summary_local_datetime(group_started_at))}</td>'
            f'<td class="nowrap">{_token_summary_html_cell(_token_summary_local_datetime(group_last_activity_at))}</td>'
            f"<td>{_token_summary_html_cell(user_id)}</td>"
            f"<td>{thread_cell}</td>"
            f"<td>{_token_summary_html_cell(group_rollup['plan'])}</td>"
            f"<td>{int(group_rollup['sub_tokens']):,}</td>"
            f"<td>{_token_summary_html_currency(group_rollup['sub_est_usd'])}</td>"
            f"<td>{float(group_rollup['sub_remaining']):,.2f}%</td>"
            f"<td>{int(group_rollup['credit_tokens']):,}</td>"
            f"<td>{_token_summary_html_currency(group_rollup['credit_est_usd'])}</td>"
            f"<td>{_token_summary_html_credits(group_rollup['credits_used'])}</td>"
            f"<td>{_token_summary_html_credits(group_rollup['credits_remaining'])}</td>"
            f"<td>{int(group_rollup['total_tokens']):,}</td>"
            f"<td>{_token_summary_html_currency(group_rollup['total_est_usd'])}</td>"
            f'<td class="folder-path">{_token_summary_html_cell(folder)}</td>'
            "</tr>"
        )
    if not group_rows_html:
        group_rows_html.append(
            '<tr><td colspan="15" class="empty">No usage-bearing folders matched this range.</td></tr>'
        )

    thread_count = len(rows)
    thread_word = "thread" if thread_count == 1 else "threads"
    if all_threads_link is not None:
        receipt_link = (
            f'<a href="{_escape_html_attribute(quote(all_threads_link, safe="/:%"))}">'
            f"View {thread_count:,} {thread_word.title()}</a>"
        )
    else:
        folder_count = len(_token_summary_groups(rows))
        folder_word = "Folder" if folder_count == 1 else "Folders"
        receipt_link = (
            f'<a href="#folder-table">View {folder_count:,} {folder_word}</a>'
        )
    thread_section = f"""<section class="section">
<div class="section-head"><div><div class="label">Folder summary</div><h2>Usage by folder</h2></div><label><span class="label">Filter rows</span><br><input id="folder-filter" class="search" type="search" placeholder="User, plan, or folder…"></label></div>
<div class="table-wrap"><table id="folder-table"><thead><tr><th>Started</th><th>Last activity</th><th>User</th><th aria-label="Thread links"></th><th>Plan</th><th>Sub tokens</th><th>Sub estimate</th><th>Sub remaining</th><th>Credit tokens</th><th>Credit estimate</th><th>Credits used</th><th>Credits remaining</th><th>Total tokens</th><th>Total estimate</th><th>Folder</th></tr></thead><tbody>{''.join(group_rows_html)}</tbody></table></div>
</section>"""

    source_items = "".join(
        f"<li>{_token_summary_html_cell(directory)}</li>" for directory in directories
    )
    plan = _token_summary_html_cell(rollup["plan"] or "not observed")
    generation_time = _token_summary_local_datetime(datetime.now(timezone.utc))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Token Usage Report</title>
<style>
:root{{--ink:#14202b;--muted:#63717d;--paper:#f3f6f6;--sheet:#fff;--line:#d9e1e3;--sub:#33658a;--credit:#d97736;--quiet:#e8eef0;--focus:#1167a8}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 "Avenir Next",Avenir,"Segoe UI",sans-serif}}
a{{color:#155f8c;text-decoration-thickness:1px;text-underline-offset:3px}}
a:focus-visible,input:focus-visible{{outline:3px solid var(--focus);outline-offset:3px}}
.page{{max-width:1540px;margin:auto;padding:42px 32px 64px}}
.eyebrow,.label,thead,.utility{{font:700 11px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.09em;text-transform:uppercase}}
.eyebrow{{color:var(--credit)}}
h1{{max-width:900px;margin:8px 0 10px;font:600 clamp(38px,6vw,76px)/.98 "Iowan Old Style","Palatino Linotype",Georgia,serif;letter-spacing:-.035em}}
.range{{margin:0;color:var(--muted);font-size:17px}}
.receipt{{display:grid;grid-template-columns:minmax(0,1.4fr) repeat(2,minmax(220px,.5fr));gap:28px;margin:34px 0;padding:26px;background:var(--sheet);border:1px solid var(--line);box-shadow:0 12px 40px rgba(20,32,43,.07)}}
.receipt-total strong{{display:block;font:600 clamp(42px,7vw,82px)/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:-.07em}}
.receipt-total span{{color:var(--muted)}}
.estimate,.credit-usage{{align-self:stretch;border-left:1px solid var(--line);padding-left:28px}}
.estimate strong,.credit-usage strong{{display:block;font:600 32px/1.1 ui-monospace,SFMono-Regular,Menlo,monospace}}
.estimate span,.credit-usage span{{color:var(--muted)}}
.funding{{margin:28px 0 36px}}
.funding-head{{display:flex;justify-content:space-between;gap:20px;align-items:end}}
.funding-head h2,.section-head h2{{margin:4px 0 0;font:600 27px/1.15 "Iowan Old Style","Palatino Linotype",Georgia,serif}}
.rail{{display:flex;height:22px;margin:14px 0 12px;background:var(--quiet);border:1px solid var(--line);overflow:hidden}}
.rail-sub{{width:{sub_share:.6f}%;background:var(--sub)}}
.rail-credit{{width:{credit_share:.6f}%;background:var(--credit)}}
.funding-values{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
.funding-values article{{padding:16px 18px;background:var(--sheet);border-top:4px solid var(--sub)}}
.funding-values article:last-child{{border-color:var(--credit)}}
.funding-values strong{{display:block;font:600 25px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace}}
.funding-values p{{margin:5px 0 0;color:var(--muted)}}
.credit-equivalent{{margin-top:14px;padding:14px 18px;background:#fff6ee;border-left:4px solid var(--credit)}}
.section{{margin-top:38px}}
.section-head{{display:flex;justify-content:space-between;gap:24px;align-items:end;margin-bottom:13px}}
.table-wrap{{overflow:auto;background:var(--sheet);border:1px solid var(--line)}}
table{{width:100%;border-collapse:collapse;white-space:nowrap;font-variant-numeric:tabular-nums}}
th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:right}}
thead th{{position:sticky;top:0;z-index:1;background:#e9eff1;color:#46545f}}
tbody th,#folder-table td:nth-child(-n+5){{text-align:left}}
#folder-table th:last-child,#folder-table td:last-child{{text-align:left}}
tbody tr:hover{{background:#f7fafb}}
.nowrap{{white-space:nowrap}}.empty{{padding:30px;text-align:center;color:var(--muted)}}
.search{{width:min(360px,100%);padding:10px 12px;border:1px solid #aebbc1;background:var(--sheet);color:var(--ink);font:inherit}}
.notes{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.notes article{{padding:22px;background:var(--sheet);border:1px solid var(--line)}}
.notes h3{{margin-top:0;font:600 20px/1.2 "Iowan Old Style","Palatino Linotype",Georgia,serif}}
.notes li{{margin:.55em 0}}
.sources{{overflow-wrap:anywhere}}
footer{{margin-top:38px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted)}}
@media(max-width:960px){{.receipt{{grid-template-columns:1fr 1fr}}.receipt-total{{grid-column:1/-1}}}}
@media(max-width:760px){{.page{{padding:28px 16px 48px}}.receipt,.notes{{grid-template-columns:1fr}}.receipt-total{{grid-column:auto}}.estimate,.credit-usage{{border-left:0;border-top:1px solid var(--line);padding:18px 0 0}}.funding-values{{grid-template-columns:1fr}}.section-head{{display:block}}.search{{margin-top:12px}}}}
@media(prefers-reduced-motion:no-preference){{tbody tr{{transition:background-color .16s ease}}}}
@media print{{body{{background:#fff}}.page{{max-width:none;padding:0}}.receipt{{box-shadow:none}}.search{{display:none}}.table-wrap{{overflow:visible}}thead th{{position:static}}}}
</style>
</head>
<body>
<main class="page">
<header>
<div class="eyebrow">Agent Report · usage receipt</div>
<h1>Token Usage Report</h1>
<p class="range">{_token_summary_html_cell(local_from)} inclusive → {_token_summary_html_cell(local_to)} exclusive · local time</p>
</header>
<section class="receipt" aria-label="Usage total">
<div class="receipt-total"><div class="label">Processed tokens</div><strong>{total_tokens:,}</strong><span>{receipt_link} · plan: {plan}</span></div>
<div class="estimate"><div class="label">API-equivalent estimate</div><strong>{_token_summary_html_currency(total_estimate)}</strong><span>Estimated from token counts - not an actual charged amount</span></div>
<div class="credit-usage"><div class="label">Credit usage</div><strong>{_token_summary_html_credits(credits_used)}</strong><span>Observed credits consumed</span></div>
</section>
<section class="funding">
<div class="funding-head"><div><div class="label">Funding split</div><h2>Where the usage came from</h2></div><div class="utility">{sub_share:.2f}% sub · {credit_share:.2f}% credits</div></div>
<div class="rail" role="img" aria-label="Subscription {sub_share:.2f} percent; credits {credit_share:.2f} percent"><span class="rail-sub"></span><span class="rail-credit"></span></div>
<div class="funding-values">
<article><div class="label">Subscription</div><strong>{sub_tokens:,} tokens</strong><p>{_token_summary_html_currency(sub_estimate)} API-equivalent · {float(rollup['sub_remaining']):,.2f}% remaining</p></article>
<article><div class="label">Purchased credits</div><strong>{credit_tokens:,} tokens</strong><p>{_token_summary_html_currency(credit_estimate)} API-equivalent · {_token_summary_html_credits(credits_used)} used · {_token_summary_html_credits(credits_remaining)} remaining</p></article>
</div>
<div class="credit-equivalent"><strong>USD-equivalent usage per credit: {_token_summary_html_currency(usage_per_credit)}</strong> USD-equivalent usage divided by credits consumed—not the purchase price or an actual charged amount.</div>
</section>
<section class="section">
<div class="section-head"><div><div class="label">Model mix</div><h2>Cost by logged model</h2></div></div>
<div class="table-wrap"><table><thead><tr><th>Model</th><th>Input</th><th>Cached input</th><th>Uncached input</th><th>Output</th><th>Reasoning</th><th>Processed</th><th>Estimate</th></tr></thead><tbody>{''.join(model_rows)}</tbody></table></div>
</section>
{thread_section}
<section class="section notes">
<article><div class="label">Counting contract</div><h3>How totals are built</h3><ul><li>Only token events inside the selected local range count.</li><li>Processed tokens equal input plus output.</li><li>Cached input is already included in input tokens.</li><li>Reasoning tokens are already included in output tokens and are not added again.</li></ul></article>
<article><div class="label">Cost contract</div><h3>What the dollar estimate means</h3><ul><li>Each event uses its logged model and the Agent Report pricing card.</li><li>Uncached input, cached input, and output use separate rates.</li><li>Subscription and credit usage keep the same API-equivalent estimate.</li><li>Observed credit burn is tracked separately and allocated to files by model-aware estimated cost weight.</li></ul></article>
</section>
<section class="section sources"><div class="label">Scanned directories</div><ul>{source_items}</ul></section>
<footer>Generated {_token_summary_html_cell(generation_time)} local time · Agent Report · all amounts shown as USD are API-equivalent estimates.</footer>
</main>
<script>
const filter=document.getElementById('folder-filter');
filter?.addEventListener('input',()=>{{const query=filter.value.trim().toLocaleLowerCase();document.querySelectorAll('#folder-table tbody tr[data-search]').forEach(row=>{{row.hidden=!row.dataset.search.includes(query)}})}});
</script>
</body>
</html>"""


def _token_summary_thread_stem(row: _TokenSummaryRow) -> str:
    """Return a filesystem-safe, collision-resistant name for one thread."""
    basename = re.sub(r"[^A-Za-z0-9._-]+", "-", row.path.stem).strip("-.")
    digest = hashlib.sha256(str(row.path).encode("utf-8")).hexdigest()[:10]
    return f"{basename or 'thread'}-{digest}"


def _token_summary_group_stem(key: tuple[str, str]) -> str:
    """Return a stable page name for one user-and-folder summary group."""
    user_id, folder = key
    basename = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(folder).name).strip("-.")
    digest = hashlib.sha256(f"{user_id}\0{folder}".encode("utf-8")).hexdigest()[:10]
    return f"{basename or 'folder'}-{digest}"


def _render_token_summary_group_html(
    rows: list[_TokenSummaryRow],
    *,
    report_filename: str,
    detail_links: dict[Path, str],
    event_links: dict[Path, str],
    thread_titles: dict[Path, str],
    page_title: str = "Threads in Folder",
    eyebrow: str = "Agent Report · folder detail",
    folder_label: str | None = None,
) -> str:
    """Render a thread list with optional folder context."""
    thread_rows: list[str] = []
    for row in rows:
        detail = dict(
            zip(
                _TOKEN_SUMMARY_DETAIL_COLUMNS,
                _token_summary_detail_values(row),
                strict=True,
            )
        )
        models = ", ".join(
            sorted(
                {event.model for event in row.funding_events if event.model},
                key=str.casefold,
            )
        ) or "unknown"
        usage_href = detail_links[row.path]
        events_href = event_links[row.path]
        thread_title = thread_titles.get(row.path, "Untitled thread")
        compact_title = _compact_display_text(thread_title, 52)
        title_attribute = (
            f' title="{_escape_html_attribute(thread_title)}"'
            if compact_title != thread_title
            else ""
        )
        search_value = (
            f"{row.user_id} {thread_title} {detail['plan']} {models}".casefold()
        )
        thread_rows.append(
            f'<tr data-search="{_escape_html_attribute(search_value)}">'
            f'<td class="nowrap">{_token_summary_html_cell(detail["started_at"])}</td>'
            f'<td class="nowrap">{_token_summary_html_cell(detail["last_activity_at"])}</td>'
            f"<td>{_token_summary_html_cell(row.user_id)}</td>"
            f'<td{title_attribute}>{_token_summary_html_cell(compact_title)}</td>'
            f'<td><a href="{_escape_html_attribute(quote(usage_href))}">View Usage</a></td>'
            f'<td><a href="{_escape_html_attribute(quote(events_href))}">View Events</a></td>'
            f"<td>{_token_summary_html_cell(detail['plan'])}</td>"
            f"<td>{_token_summary_html_cell(models)}</td>"
            f"<td>{int(detail['sub_tokens']):,}</td>"
            f"<td>{int(detail['credit_tokens']):,}</td>"
            f"<td>{_token_summary_html_credits(detail['credits_used'])}</td>"
            f"<td>{int(detail['input_tokens']):,}</td>"
            f"<td>{int(detail['cached_input_tokens']):,}</td>"
            f"<td>{int(detail['uncached_input_tokens']):,}</td>"
            f"<td>{int(detail['output_tokens']):,}</td>"
            f"<td>{int(detail['reasoning_tokens']):,}</td>"
            f"<td>{int(detail['processed_tokens']):,}</td>"
            f"<td>{_token_summary_html_currency(detail['total_est_usd'])}</td>"
            "</tr>"
        )
    rollup = _token_summary_rollup(rows)
    thread_count = len(rows)
    thread_word = "thread" if thread_count == 1 else "threads"
    folder_context = (
        '<p class="folder-context"><span class="label">Folder</span> '
        f"{_token_summary_html_cell(folder_label)}</p>"
        if folder_label is not None
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_token_summary_html_cell(page_title)}</title>
<style>
:root{{--ink:#14202b;--muted:#63717d;--paper:#f3f6f6;--sheet:#fff;--line:#d9e1e3;--accent:#d97736;--focus:#1167a8}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 "Avenir Next",Avenir,"Segoe UI",sans-serif}}a{{color:#155f8c;text-underline-offset:3px}}a:focus-visible,input:focus-visible{{outline:3px solid var(--focus);outline-offset:3px}}
.page{{max-width:1540px;margin:auto;padding:36px 28px 60px}}.nav a{{font-weight:700}}.eyebrow,thead,.label{{font:700 11px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.09em;text-transform:uppercase}}.eyebrow{{margin-top:26px;color:var(--accent)}}
h1{{margin:7px 0 8px;font:600 clamp(36px,6vw,68px)/1 "Iowan Old Style","Palatino Linotype",Georgia,serif;letter-spacing:-.035em}}.folder-context{{margin:10px 0 4px;color:var(--muted);overflow-wrap:anywhere}}.folder-context .label{{margin-right:7px;color:var(--ink)}}.summary{{color:var(--muted);font-size:17px}}.section-head{{display:flex;justify-content:space-between;gap:24px;align-items:end;margin:30px 0 13px}}.section-head h2{{margin:4px 0 0;font:600 27px/1.15 "Iowan Old Style","Palatino Linotype",Georgia,serif}}
.search{{width:min(360px,100%);padding:10px 12px;border:1px solid #aebbc1;background:var(--sheet);color:var(--ink);font:inherit}}.table-wrap{{overflow:auto;background:var(--sheet);border:1px solid var(--line)}}table{{width:100%;border-collapse:collapse;white-space:nowrap;font-variant-numeric:tabular-nums}}th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:right}}thead th{{position:sticky;top:0;background:#e9eff1;color:#46545f}}td:nth-child(-n+8),th:nth-child(-n+8){{text-align:left}}tbody tr:hover{{background:#f7fafb}}
@media(max-width:720px){{.page{{padding:24px 14px 44px}}.section-head{{display:block}}.search{{margin-top:12px}}}}@media print{{body{{background:#fff}}.page{{max-width:none;padding:0}}.search{{display:none}}thead th{{position:static}}}}
</style></head><body><main class="page">
<nav class="nav" aria-label="Breadcrumb"><a href="../{_escape_html_attribute(quote(report_filename))}">Overall Usage</a></nav>
<div class="eyebrow">{_token_summary_html_cell(eyebrow)}</div><h1>{_token_summary_html_cell(page_title)}</h1>
{folder_context}
<p class="summary">{thread_count:,} {thread_word} · {int(rollup['total_tokens']):,} processed tokens · {_token_summary_html_currency(rollup['total_est_usd'])} API-equivalent estimate</p>
<section><div class="section-head"><div><div class="label">Thread summary</div><h2>Usage by thread</h2></div><label><span class="label">Filter rows</span><br><input id="thread-filter" class="search" type="search" placeholder="User, model, plan…"></label></div>
<div class="table-wrap"><table id="thread-table"><thead><tr><th>Started</th><th>Last activity</th><th>User</th><th>Title</th><th aria-label="Usage links"></th><th aria-label="Event links"></th><th>Plan</th><th>Model</th><th>Sub tokens</th><th>Credit tokens</th><th>Credits used</th><th>Input</th><th>Cached input</th><th>Uncached input</th><th>Output</th><th>Reasoning</th><th>Processed</th><th>Estimate</th></tr></thead><tbody>{''.join(thread_rows)}</tbody></table></div></section>
</main><script>const filter=document.getElementById('thread-filter');filter?.addEventListener('input',()=>{{const query=filter.value.trim().toLocaleLowerCase();document.querySelectorAll('#thread-table tbody tr[data-search]').forEach(row=>{{row.hidden=!row.dataset.search.includes(query)}})}});</script></body></html>"""


def _render_token_summary_thread_html(
    row: _TokenSummaryRow,
    *,
    from_time: datetime,
    to_time: datetime,
    report_filename: str,
    threads_filename: str,
    raw_filename: str,
    steps_filename: str,
) -> str:
    """Render an event-level token ledger for one source thread."""
    event_rows: list[str] = []
    for event in sorted(
        row.funding_events,
        key=lambda item: (item.event_timestamp, item.source_ordinal),
    ):
        timestamp = _parse_iso_datetime(event.event_timestamp)
        local_timestamp = (
            _token_summary_local_datetime(timestamp)
            if timestamp is not None
            else event.event_timestamp
        )
        _, event_cost = _token_summary_usage_cost([event])
        usage = event.usage
        sub_used = (
            "not observed"
            if event.subscription_used_percent is None
            else f"{event.subscription_used_percent:,.2f}%"
        )
        credit_balance = (
            "not observed"
            if event.credit_balance is None
            else _token_summary_html_credits(event.credit_balance)
        )
        credit_available = (
            "not observed"
            if event.has_credits is None
            else "yes" if event.has_credits else "no"
        )
        line_href = f"{quote(raw_filename)}#line-{event.source_ordinal}"
        event_rows.append(
            "<tr>"
            f'<td class="nowrap">{_token_summary_html_cell(local_timestamp)}</td>'
            f'<td><a href="{_escape_html_attribute(line_href)}">{event.source_ordinal:,}</a></td>'
            f"<td>{_token_summary_html_cell(event.model or 'unknown')}</td>"
            f"<td>{_token_summary_html_cell(event.plan_type or 'not observed')}</td>"
            f"<td>{_token_summary_html_cell(event.funding_source)}</td>"
            f"<td>{_token_summary_html_cell(sub_used)}</td>"
            f"<td>{_token_summary_html_cell(credit_available)}</td>"
            f"<td>{_token_summary_html_cell(credit_balance)}</td>"
            f"<td>{usage.input_tokens:,}</td>"
            f"<td>{usage.cached_input_tokens:,}</td>"
            f"<td>{usage.uncached_input_tokens:,}</td>"
            f"<td>{usage.output_tokens:,}</td>"
            f"<td>{usage.reasoning_tokens:,}</td>"
            f"<td>{usage.processed_tokens:,}</td>"
            f"<td>{_token_summary_html_currency(event_cost.total_cost or 0)}</td>"
            "</tr>"
        )
    if not event_rows:
        event_rows.append(
            '<tr><td colspan="15" class="empty">No token events matched this range.</td></tr>'
        )
    rollup = _token_summary_rollup([row])
    local_from = _token_summary_local_datetime(from_time)
    local_to = _token_summary_local_datetime(to_time)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Thread Token Usage</title>
<style>
:root{{--ink:#14202b;--muted:#63717d;--paper:#f3f6f6;--sheet:#fff;--line:#d9e1e3;--accent:#d97736;--focus:#1167a8}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 "Avenir Next",Avenir,"Segoe UI",sans-serif}}
a{{color:#155f8c;text-underline-offset:3px}}a:focus-visible{{outline:3px solid var(--focus);outline-offset:3px}}
.page{{max-width:1540px;margin:auto;padding:36px 28px 60px}}.nav{{display:flex;gap:18px;align-items:center}}.nav a{{font-weight:700}}.eyebrow,thead,.label{{font:700 11px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.09em;text-transform:uppercase}}
.eyebrow{{margin-top:26px;color:var(--accent)}}h1{{margin:7px 0 8px;font:600 clamp(36px,6vw,68px)/1 "Iowan Old Style","Palatino Linotype",Georgia,serif;letter-spacing:-.035em}}
.source,.range,.note{{color:var(--muted);overflow-wrap:anywhere}}.summary{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:28px 0}}
.summary article{{padding:18px;background:var(--sheet);border-top:4px solid var(--accent)}}.summary strong{{display:block;font:600 25px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace}}
h2{{margin:32px 0 12px;font:600 27px/1.2 "Iowan Old Style","Palatino Linotype",Georgia,serif}}.table-wrap{{overflow:auto;background:var(--sheet);border:1px solid var(--line)}}
table{{width:100%;border-collapse:collapse;white-space:nowrap;font-variant-numeric:tabular-nums}}th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:right}}thead th{{position:sticky;top:0;background:#e9eff1;color:#46545f}}td:nth-child(-n+5),th:nth-child(-n+5){{text-align:left}}tbody tr:hover{{background:#f7fafb}}.empty{{padding:30px;text-align:center;color:var(--muted)}}
@media(max-width:720px){{.page{{padding:24px 14px 44px}}.summary{{grid-template-columns:1fr}}}}@media print{{body{{background:#fff}}.page{{max-width:none;padding:0}}thead th{{position:static}}}}
</style></head><body><main class="page">
<nav class="nav" aria-label="Breadcrumb"><a href="../{_escape_html_attribute(quote(report_filename))}">Overall Usage</a> › <a href="{_escape_html_attribute(quote(threads_filename))}">Threads in Folder</a></nav>
<div class="eyebrow">Agent Report · thread detail</div><h1>Thread Token Usage</h1>
<p class="source">{_token_summary_html_cell(row.path)}</p><p class="range">{_token_summary_html_cell(local_from)} inclusive → {_token_summary_html_cell(local_to)} exclusive · local time</p>
<section class="summary" aria-label="Thread totals"><article><div class="label">Processed tokens</div><strong>{row.usage.processed_tokens:,}</strong></article><article><div class="label">API-equivalent estimate</div><strong>{_token_summary_html_currency(row.cost.total_cost or 0)}</strong></article><article><div class="label">Allocated credit usage</div><strong>{_token_summary_html_credits(rollup['credits_used'])}</strong></article></section>
<h2>Token event ledger</h2><p class="note">Each row is one recorded token event in the selected period. Zero-token rows preserve funding telemetry but do not add to the totals. Source-line links open an escaped local copy of the JSONL record.</p>
<div class="table-wrap"><table><thead><tr><th>Local time</th><th>Source line</th><th>Model</th><th>Plan</th><th>Funding</th><th>Sub used</th><th>Credits available</th><th>Credits remaining</th><th>Input</th><th>Cached input</th><th>Uncached input</th><th>Output</th><th>Reasoning</th><th>Processed</th><th>Estimate</th></tr></thead><tbody>{''.join(event_rows)}</tbody></table></div>
</main></body></html>"""


def _render_token_summary_raw_html(row: _TokenSummaryRow) -> str:
    """Render an escaped, line-addressable copy of one local JSONL source."""
    raw_lines = row.path.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = "".join(
        f'<div class="line" id="line-{ordinal}"><a href="#line-{ordinal}">{ordinal:,}</a><code>{_escape_html_attribute(line)}</code></div>'
        for ordinal, line in enumerate(raw_lines, start=1)
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Raw Source Log</title>
<style>:root{{--ink:#dce7ec;--muted:#8295a1;--bg:#10181d;--line:#26363f;--link:#75c7f0}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace}}header{{position:sticky;top:0;z-index:1;padding:14px 20px;background:#152229;border-bottom:1px solid var(--line)}}h1{{display:inline;margin:0 14px 0 0;font-size:15px}}header span{{color:var(--muted)}}.line{{display:grid;grid-template-columns:72px max-content;border-bottom:1px solid rgba(38,54,63,.45)}}.line:target{{background:#3b3220}}.line>a{{padding:3px 12px;color:var(--link);text-align:right;text-decoration:none;border-right:1px solid var(--line)}}code{{padding:3px 12px;white-space:pre}}@media print{{header{{position:static}}}}</style></head>
<body><header><h1>Raw Source Log</h1><span>{_token_summary_html_cell(row.path)} · privacy-sensitive local copy</span></header><main>{lines}</main></body></html>"""


def _write_token_summary_html(
    rows: list[_TokenSummaryRow],
    destination: Path,
    *,
    from_time: datetime,
    to_time: datetime,
    directories: list[Path],
    threads: bool = False,
    emit_progress: bool = False,
) -> None:
    group_links: dict[tuple[str, str], str] | None = None
    if threads:
        thread_directory = destination.parent / f"{destination.stem}-threads"
        thread_directory.mkdir(parents=True, exist_ok=True)
        all_threads_page_name = "index.html"
        grouped_rows = _token_summary_groups(rows)
        group_page_names = {
            key: f"{_token_summary_group_stem(key)}-threads.html"
            for key, _group_rows in grouped_rows
        }
        row_group_keys = {
            row.path: key for key, group_rows in grouped_rows for row in group_rows
        }
        detail_links: dict[Path, str] = {}
        event_links: dict[Path, str] = {}
        thread_titles: dict[Path, str] = {}
        for index, row in enumerate(rows, start=1):
            if emit_progress:
                print(
                    f"Generating {index:,} of {len(rows):,}: {row.path.name}",
                    file=sys.stderr,
                    flush=True,
                )
            stem = _token_summary_thread_stem(row)
            detail_path = thread_directory / f"{stem}-token-detail.html"
            ledger_csv_path = thread_directory / f"{stem}-token-detail.csv"
            raw_path = thread_directory / f"{stem}-raw.html"
            steps_path = thread_directory / f"{stem}-steps.html"
            group_page_name = group_page_names[row_group_keys[row.path]]
            identity = _rollout_identity(row.path)
            if identity is None:
                raise ValueError(f"No Codex thread identity found in {row.path}")
            steps_run = build_codex_rollout_run(
                identity[0],
                row.path.parent,
                include_children=False,
                candidate_paths=[row.path],
            )
            root_thread = next(
                thread
                for thread in steps_run.threads
                if thread.thread_id == steps_run.root_thread_id
            )
            thread_title = (
                root_thread.task_title
                or _derived_task_title(root_thread.activities)
                or "Untitled thread"
            )
            thread_titles[row.path] = thread_title
            _write_codex_outputs(
                steps_run,
                steps_path,
                nav_links=[
                    ("Overall Usage", f"../{destination.name}"),
                    ("Threads in Folder", group_page_name),
                ],
                page_title="Thread Events",
                page_subtitle=thread_title,
                page_action_links=[("Log file", raw_path.name)],
            )
            raw_path.write_text(
                _with_copyright_footer(
                    _load_token_ledger_engine().render_raw_rollout_html(row.path)
                ),
                encoding="utf-8",
            )
            detail_path.write_text(
                _with_copyright_footer(
                    _render_token_summary_ledger_html(
                        row,
                        from_time=from_time,
                        to_time=to_time,
                        report_filename=destination.name,
                        threads_filename=group_page_name,
                        raw_path=raw_path,
                        thread_title=thread_title,
                        ledger_csv_path=ledger_csv_path,
                    )
                ),
                encoding="utf-8",
            )
            detail_links[row.path] = detail_path.name
            event_links[row.path] = steps_path.name
        (thread_directory / all_threads_page_name).write_text(
            _with_copyright_footer(
                _render_token_summary_group_html(
                    rows,
                    report_filename=destination.name,
                    detail_links=detail_links,
                    event_links=event_links,
                    thread_titles=thread_titles,
                    page_title="All Threads",
                    eyebrow="Agent Report · thread index",
                )
            ),
            encoding="utf-8",
        )
        for key, group_rows in grouped_rows:
            group_path = thread_directory / group_page_names[key]
            group_path.write_text(
                _with_copyright_footer(
                    _render_token_summary_group_html(
                        group_rows,
                        report_filename=destination.name,
                        detail_links=detail_links,
                        event_links=event_links,
                        thread_titles=thread_titles,
                        folder_label=key[1],
                    )
                ),
                encoding="utf-8",
            )
        relative_thread_directory = thread_directory.relative_to(destination.parent)
        group_links = {
            key: (relative_thread_directory / page_name).as_posix()
            for key, page_name in group_page_names.items()
        }
        all_threads_link = (
            relative_thread_directory / all_threads_page_name
        ).as_posix()
    else:
        all_threads_link = None
    destination.write_text(
        _with_copyright_footer(
            _render_token_summary_html(
                rows,
                from_time=from_time,
                to_time=to_time,
                directories=directories,
                group_links=group_links,
                all_threads_link=all_threads_link,
            )
        ),
        encoding="utf-8",
    )


def _token_summary_display_value(column: str, value: object) -> str:
    """Format one terminal-table value without changing CSV serialization."""
    if value == "":
        return ""
    if column.endswith("_usd"):
        return f"${float(value):,.2f}"
    if column in {"sub_start", "sub_end", "sub_remaining"}:
        return f"{float(value):,.2f}%"
    if column.endswith("_tokens") or column == "total_tokens":
        return f"{int(value):,}"
    if column in {
        "credits_start", "credits_end", "credits_used", "credits_remaining"
    }:
        return f"{float(value):,.2f}"
    return str(value)


def _token_summary_total_values(
    rows: list[_TokenSummaryRow], *, details: bool
) -> list[object]:
    columns = _TOKEN_SUMMARY_DETAIL_COLUMNS if details else _TOKEN_SUMMARY_GROUP_COLUMNS
    rollup = _token_summary_rollup(rows)
    values: dict[str, object] = {"user_id": "TOTAL", **rollup}
    if details:
        usage = UsageTotals()
        for row in rows:
            usage += row.usage
        costs = [row.cost for row in rows]

        def component(name: str) -> object:
            known = [getattr(cost, name) for cost in costs if getattr(cost, name) is not None]
            return _cost_value(sum(known) if known else None)

        values.update(
            {
                "input_tokens": usage.input_tokens,
                "input_est_usd": component("input_cost"),
                "cached_input_tokens": usage.cached_input_tokens,
                "cached_input_est_usd": component("cached_input_cost"),
                "uncached_input_tokens": usage.uncached_input_tokens,
                "output_tokens": usage.output_tokens,
                "output_est_usd": component("output_cost"),
                "reasoning_tokens": usage.reasoning_tokens,
                "processed_tokens": usage.processed_tokens,
            }
        )
    return [values.get(column, "") for column in columns]


def _print_token_summary(rows: list[_TokenSummaryRow], *, details: bool) -> None:
    columns, values = _token_summary_output(rows, details=details)
    total_values = _token_summary_total_values(rows, details=details)
    all_values = [
        list(columns),
        *[
            [
                _token_summary_display_value(columns[index], value)
                for index, value in enumerate(row)
            ]
            for row in values
        ],
        [
            _token_summary_display_value(columns[index], value)
            for index, value in enumerate(total_values)
        ],
    ]
    widths = [
        max(len(str(row[index])) for row in all_values)
        for index in range(len(columns))
    ]
    for row_index, row in enumerate(all_values):
        rendered = []
        for index, value in enumerate(row):
            text = str(value)
            left_aligned = columns[index] in {
                "user_id", "folder", "filename", "started_at",
                "last_activity_at", "plan",
            }
            rendered.append(
                text.ljust(widths[index]) if left_aligned else text.rjust(widths[index])
            )
        print("  ".join(rendered).rstrip())
        if row_index == 0:
            print("  ".join("-" * width for width in widths))


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
def _load_pricing_registry() -> dict[str, object]:
    try:
        raw = json.loads(PRICING_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


@lru_cache(maxsize=1)
def _load_pricing_table() -> dict[str, dict[str, float]]:
    raw = _load_pricing_registry()
    models = raw.get("models", {})
    if not isinstance(models, dict):
        return {}
    table: dict[str, dict[str, float]] = {}
    for model, prices in models.items():
        rate_row = _coerce_pricing_rates(prices)
        if rate_row is not None:
            model_key = model.lower()
            table[model_key] = rate_row
            if isinstance(prices, dict):
                aliases = prices.get("aliases", [])
                if isinstance(aliases, list):
                    for alias in aliases:
                        if isinstance(alias, str) and alias.strip():
                            table[alias.strip().lower()] = rate_row
    return table


def _coerce_pricing_rates(prices: object) -> dict[str, float] | None:
    """Return numeric token rates only when a model has complete pricing."""
    if not isinstance(prices, dict):
        return None
    rate_row: dict[str, float] = {}
    for key in PRICING_RATE_KEYS:
        value = prices.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        rate_row[key] = float(value)
    credit_values = [prices.get(key) for key in CODEX_CREDIT_RATE_KEYS]
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in credit_values):
        for key, value in zip(CODEX_CREDIT_RATE_KEYS, credit_values):
            rate_row[key] = float(value)
    return rate_row


def _pricing_reference_rows() -> list[tuple[str, dict[str, object]]]:
    """Return canonical display rows from the versioned pricing registry."""
    models = _load_pricing_registry().get("models", {})
    if not isinstance(models, dict):
        return []
    rows = [
        (model, prices)
        for model, prices in models.items()
        if isinstance(model, str)
        and isinstance(prices, dict)
        and _coerce_pricing_rates(prices) is not None
    ]
    return sorted(
        rows,
        key=lambda item: (
            str(item[1].get("provider", "")),
            str(item[1].get("display_name", item[0])),
        ),
    )


def _rate_triplet(prices: dict[str, object], keys: tuple[str, str, str], prefix: str = "") -> str:
    values = [prices.get(key) for key in keys]
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        return "—"
    return " / ".join(f"{prefix}{float(value):g}" for value in values)


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


def _parse_iso_datetime(raw: object) -> datetime | None:
    if raw is None or raw == "" or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        if abs(value) >= 100_000_000_000:
            value /= 1000
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(raw).strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return _parse_iso_datetime(float(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _normalize_timestamp(raw: object, fallback: object = "") -> str:
    parsed = _parse_iso_datetime(raw)
    if parsed is None:
        parsed = _parse_iso_datetime(fallback)
    if parsed is not None:
        return parsed.astimezone(timezone.utc).isoformat()
    return str(raw or fallback or "")


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
    seen_judge_logs: set[Path] = set()
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
            seen_judge_logs.add(judge_log.resolve())
            step = _file_step(
                f"{step_prefix} / iter {iter_num} judge",
                judge_stderr if judge_stderr.exists() else judge_log,
                judge_log,
                judge_log,
            )
            if step:
                steps.append(step)

    for judge_log in sorted(module_dir.glob("prompt-*.iter-*-judge.stdout.log")):
        resolved = judge_log.resolve()
        if resolved in seen_judge_logs:
            continue
        match = re.match(r"^(prompt-\d+)\.iter-(\d+)-judge\.stdout\.log$", judge_log.name)
        if not match:
            continue
        prompt_id = match.group(1)
        iter_num = match.group(2)
        prompt_name = prompt_names.get(prompt_id, prompt_id)
        step_prefix = f"{prefix}{prompt_name}" if prefix else prompt_name
        judge_stderr = judge_log.with_name(f"{prompt_id}.iter-{iter_num}-judge.stderr.log")
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


def _module_run_started_at(module_dir: Path) -> datetime | None:
    manifest_path = module_dir.parent / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _parse_iso_datetime(manifest.get("started_at"))


def _normalize_variant_key(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if slug.startswith("variant-"):
        return slug
    return f"variant-{slug}" if slug else "variant"


def _parse_selection_rationale(selector_decision_path: Path) -> str:
    try:
        content = selector_decision_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(r"^RATIONALE:\s*(.+?)\s*$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _parse_selection_forks_from_module_dir(
    module_dir: Path,
) -> tuple[list[ForkSection], set[str]]:
    prompt_names = _prompt_name_map_from_module_dir(module_dir)
    fork_sections: list[ForkSection] = []
    consumed_prompt_ids: set[str] = set()

    for selection_dir in sorted(module_dir.glob("prompt-*.selection")):
        if not selection_dir.is_dir():
            continue
        match = re.match(r"^(prompt-\d+)\.selection$", selection_dir.name)
        if not match:
            continue
        prompt_id = match.group(1)
        consumed_prompt_ids.add(prompt_id)

        try:
            fork_index = int(prompt_id.split("-")[1])
        except (IndexError, ValueError):
            fork_index = 0
        fork_title = prompt_names.get(prompt_id, prompt_id)

        selector_steps = [
            step for step in _parse_prompt_module_dir(module_dir)
            if step.name.startswith(fork_title) and "judge" in step.name.lower()
        ]
        if selector_steps:
            _normalize_step_sequence(
                selector_steps,
                start_anchor=_module_run_started_at(module_dir),
            )

        selected_variant_path = module_dir / f"{prompt_id}.selected-variant.txt"
        selected_variant = ""
        if selected_variant_path.exists():
            try:
                selected_variant = selected_variant_path.read_text(encoding="utf-8").strip()
            except OSError:
                selected_variant = ""

        selector_decision_path = module_dir / f"{prompt_id}.selector-decision.md"
        selector_rationale = (
            _parse_selection_rationale(selector_decision_path)
            if selector_decision_path.exists()
            else ""
        )

        variants: dict[str, list[Step]] = {}
        variant_titles: dict[str, str] = {}
        variants_dir = selection_dir / "variants"
        if variants_dir.exists():
            for variant_dir in sorted(variants_dir.iterdir()):
                if not variant_dir.is_dir():
                    continue
                result_path = variant_dir / "result.json"
                variant_name = variant_dir.name
                variant_title = variant_dir.name
                if result_path.exists():
                    try:
                        result = json.loads(result_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        result = {}
                    variant_name = str(result.get("variant_name") or variant_name)
                    variant_title = str(result.get("variant_title") or variant_name)

                variant_key = _normalize_variant_key(variant_name)
                workspace_run_files = variant_dir / "workspace" / ".run-files"
                child_modules = [
                    child for child in sorted(workspace_run_files.iterdir())
                    if child.is_dir()
                    and child.name != "backend-state"
                    and child.name != "history"
                    and (child / "module.log").exists()
                ] if workspace_run_files.exists() else []
                if not child_modules:
                    continue
                child_module = child_modules[0]
                variant_steps = _parse_prompt_module_dir(child_module)
                if not variant_steps:
                    continue
                _normalize_step_sequence(
                    variant_steps,
                    start_anchor=_module_run_started_at(child_module),
                )
                variants[variant_key] = variant_steps
                variant_titles[variant_key] = variant_title

        if variants or selector_steps:
            fork_sections.append(
                ForkSection(
                    fork_index=fork_index,
                    fork_title=fork_title,
                    variants=variants,
                    variant_titles=variant_titles,
                    selector_steps=selector_steps,
                    selected_variant=selected_variant,
                    selector_rationale=selector_rationale,
                )
            )

    return fork_sections, consumed_prompt_ids


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

    if (
        any(run_dir.glob("prompt-*.iter-*-generator.stdout.log"))
        or any(run_dir.glob("prompt-*.iter-*-judge.stdout.log"))
    ):
        shared_steps = _parse_prompt_module_dir(run_dir)
        fork_sections, consumed_prompt_ids = _parse_selection_forks_from_module_dir(run_dir)
        if consumed_prompt_ids:
            shared_steps = [
                step for step in shared_steps
                if not any(step.name.startswith(prompt_id) for prompt_id in consumed_prompt_ids)
            ]
        if shared_steps:
            _normalize_step_sequence(shared_steps, start_anchor=_module_run_started_at(run_dir))
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


# ---------------------------------------------------------------------------
# Native Junie session parser
# ---------------------------------------------------------------------------

def _junie_events_path(path: Path) -> Path:
    return path / "events.jsonl" if path.is_dir() else path


def _is_native_junie_session(path: Path) -> bool:
    events_path = _junie_events_path(path)
    if events_path.name != "events.jsonl" or not events_path.is_file():
        return False
    try:
        with events_path.open(encoding="utf-8", errors="replace") as handle:
            checked = 0
            for line in handle:
                if not line.strip():
                    continue
                checked += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return False
                if isinstance(record, dict) and record.get("kind") in {
                    "UserPromptEvent",
                    "SessionA2uxEvent",
                    "TaskStartedEvent",
                }:
                    return True
                if checked >= 20:
                    break
    except OSError:
        return False
    return False


def _junie_usage(value: object) -> UsageTotals | None:
    if not isinstance(value, dict):
        return None
    counters: dict[str, int] = {}
    for key in ("inputTokens", "cacheInputTokens", "cacheCreateTokens", "outputTokens"):
        raw = value.get(key, 0)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            return None
        counters[key] = raw
    cached = counters["cacheInputTokens"]
    cache_create = counters["cacheCreateTokens"]
    uncached = counters["inputTokens"] + cache_create
    output = counters["outputTokens"]
    return UsageTotals(
        input_tokens=cached + uncached,
        cached_input_tokens=cached,
        cache_create_input_tokens=cache_create,
        uncached_input_tokens=uncached,
        output_tokens=output,
        reasoning_tokens=0,
        processed_tokens=cached + uncached + output,
    )


def _junie_ide_chain_paths(path: Path) -> tuple[Path, Path] | None:
    """Return the Junie IDE chain manifest and task directory for `path`."""

    if path.is_file() and path.suffix.lower() == ".json":
        chain_dir = path.with_suffix("")
        manifest = path
    elif path.is_dir():
        chain_dir = path
        manifest = path.with_suffix(".json")
    else:
        return None
    if (
        not manifest.is_file()
        or not chain_dir.is_dir()
        or not any(chain_dir.glob("task-*.json"))
    ):
        return None
    return manifest, chain_dir


def _is_native_junie_ide_chain(path: Path) -> bool:
    resolved = _junie_ide_chain_paths(path)
    if resolved is None:
        return False
    manifest, _ = resolved
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(value, dict)
        and manifest.stem.startswith("chain-")
        and "created" in value
        and "state" in value
    )


def _junie_ide_usage(value: object) -> UsageTotals | None:
    if not isinstance(value, dict):
        return None
    counters: dict[str, int] = {}
    for key in (
        "inputTokens",
        "cacheInputTokens",
        "cacheCreateInputTokens",
        "outputTokens",
        "reasoningTokens",
    ):
        raw = value.get(key, 0)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            return None
        counters[key] = raw
    fresh = counters["inputTokens"]
    cached = counters["cacheInputTokens"]
    cache_create = counters["cacheCreateInputTokens"]
    output = counters["outputTokens"]
    return UsageTotals(
        input_tokens=fresh + cached + cache_create,
        cached_input_tokens=cached,
        cache_create_input_tokens=cache_create,
        uncached_input_tokens=fresh + cache_create,
        output_tokens=output,
        reasoning_tokens=counters["reasoningTokens"],
        processed_tokens=fresh + cached + cache_create + output,
    )


def _junie_ide_observation_id(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    request = value.get("assistantRequest")
    if not isinstance(request, dict):
        return ""
    return str(request.get("answerChoiceId") or "")


def _junie_ide_task_index(path: Path) -> int:
    match = re.fullmatch(r"task-(\d+)\.json", path.name)
    return int(match.group(1)) if match else sys.maxsize


def _junie_ide_step_index(path: Path) -> int:
    match = re.fullmatch(r"step-(\d+)\.json", path.name)
    return int(match.group(1)) if match else sys.maxsize


def _junie_ide_file_timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _junie_ide_project_name(chain_dir: Path) -> str:
    for ancestor in chain_dir.parents:
        if ancestor.parent.name == "projects":
            return re.sub(r"\.[0-9a-f]{8}$", "", ancestor.name)
    return ""


def _junie_ide_tool_name(step_type: str, command: str) -> str:
    if step_type == "Terminal":
        return "exec"
    if step_type == "Edit":
        return "apply_patch"
    if step_type == "AskQuestion":
        return "ask_question"
    normalized = command.strip().lower()
    if normalized.startswith("open "):
        return "read"
    if normalized.startswith("search "):
        return "search"
    return re.split(r"\s+", normalized, maxsplit=1)[0] or "tool"


def parse_junie_ide_chain(path: Path) -> CodexRunMetrics:
    """Normalize a durable Junie IDE issue chain without reading session env data."""

    resolved = _junie_ide_chain_paths(path)
    if resolved is None:
        raise ValueError(f"No native Junie IDE task chain found at {path}")
    manifest_path, chain_dir = resolved
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read Junie IDE chain manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"Invalid Junie IDE chain manifest at {manifest_path}")

    raw_chain_id = manifest.get("id")
    if isinstance(raw_chain_id, dict):
        chain_id = str(raw_chain_id.get("id") or raw_chain_id.get("index") or chain_dir.name)
    else:
        chain_id = str(raw_chain_id or chain_dir.name)
    run_label = " · ".join(
        item
        for item in (
            _junie_ide_project_name(chain_dir),
            str(manifest.get("name") or ""),
        )
        if item
    )
    task_paths = sorted(chain_dir.glob("task-*.json"), key=_junie_ide_task_index)
    diagnostics = [
        "Junie IDE model response timestamps are unavailable; responses are shown "
        "at task completion.",
        "Junie IDE step completion times use durable file modification timestamps "
        "normalized to step order.",
    ]
    turns: list[AgentTurn] = []
    responses: list[ResponseUsage] = []
    activities: list[AgentActivity] = []
    tools: list[ToolInterval] = []
    skills_used: set[str] = set()
    models: Counter[str] = Counter()
    recorded_cost = 0.0
    has_complete_cost = True
    source_manifest: list[SourceManifestEntry] = []
    all_tasks_complete = bool(task_paths)

    for task_path in task_paths:
        try:
            task = json.loads(task_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            diagnostics.append(f"unreadable Junie IDE task {task_path}: {exc}")
            all_tasks_complete = False
            continue
        if not isinstance(task, dict):
            diagnostics.append(f"non-object Junie IDE task {task_path}")
            all_tasks_complete = False
            continue
        task_index = _junie_ide_task_index(task_path)
        task_id = f"task-{task_index}"
        source_base = task_index * 1_000_000
        started_at = _normalize_timestamp(task.get("created"))
        completed_at = _junie_ide_file_timestamp(task_path)
        final_state = task.get("finalAgentState")
        final_state = final_state if isinstance(final_state, dict) else {}
        is_finished = final_state.get("isFinished") is True
        all_tasks_complete = all_tasks_complete and is_finished
        model = str(final_state.get("modelAndApiVersion") or "unknown")
        models[model] += 1

        raw_cost = task.get("cost")
        task_cost = (
            float(raw_cost)
            if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool)
            else None
        )
        if task_cost is None:
            has_complete_cost = False
        else:
            recorded_cost += task_cost

        previous_info = task.get("previousTasksInfo")
        previous_state = (
            previous_info.get("agentState") if isinstance(previous_info, dict) else None
        )
        previous_observations = (
            previous_state.get("observations") if isinstance(previous_state, dict) else []
        )
        previous_ids = {
            _junie_ide_observation_id(item)
            for item in previous_observations
            if _junie_ide_observation_id(item)
        } if isinstance(previous_observations, list) else set()
        final_observations = final_state.get("observations")
        current_response_data: list[tuple[int, str, UsageTotals, dict[str, object]]] = []
        task_skills: set[str] = set()
        if isinstance(final_observations, list):
            for observation_index, observation in enumerate(final_observations):
                response_id = _junie_ide_observation_id(observation)
                if (
                    not response_id
                    or response_id in previous_ids
                    or not isinstance(observation, dict)
                ):
                    continue
                request = observation.get("assistantRequest")
                if not isinstance(request, dict):
                    continue
                usage = _junie_ide_usage(request.get("usage"))
                if usage is None:
                    diagnostics.append(
                        f"invalid Junie IDE response usage in {task_path.name} "
                        f"observation {observation_index}"
                    )
                    continue
                current_response_data.append((observation_index, response_id, usage, request))
                tool_uses = request.get("toolUses")
                if isinstance(tool_uses, list):
                    for tool_use in tool_uses:
                        if not isinstance(tool_use, dict):
                            continue
                        tool_call_id = tool_use.get("toolCallId")
                        if (
                            not isinstance(tool_call_id, dict)
                            or tool_call_id.get("name") != "agent_skill_read_doc"
                        ):
                            continue
                        tool_input = tool_use.get("input")
                        raw_input = (
                            tool_input.get("rawJsonObject")
                            if isinstance(tool_input, dict)
                            else None
                        )
                        if isinstance(raw_input, dict) and raw_input.get("name"):
                            skill_name = str(raw_input["name"])
                            skills_used.add(skill_name)
                            task_skills.add(skill_name)
        task_processed = sum(item[2].processed_tokens for item in current_response_data)
        task_usage = UsageTotals()
        for observation_index, _, usage, _ in current_response_data:
            response_cost = (
                task_cost * usage.processed_tokens / task_processed
                if task_cost is not None and task_processed
                else None
            )
            responses.append(
                ResponseUsage(
                    event_timestamp=completed_at,
                    usage=usage,
                    turn_id=task_id,
                    source_path=str(task_path),
                    source_ordinal=source_base + 100_000 + observation_index,
                    model=model,
                    recorded_cost_usd=response_cost,
                    derivation_method="Junie task cost allocated by processed-token share",
                    attribution_confidence="exact",
                )
            )
            task_usage = task_usage + usage

        context = task.get("context")
        description = context.get("description") if isinstance(context, dict) else ""
        prompt_content = _tool_argument_content(description) if isinstance(description, str) else ""
        if prompt_content:
            activities.append(
                AgentActivity(
                    thread_id=chain_id,
                    turn_id=task_id,
                    activity_type="input",
                    event_timestamp=started_at,
                    source_path=str(task_path),
                    source_ordinal=source_base,
                    summary=f"Initial prompt · {len(prompt_content):,} characters",
                    content=prompt_content,
                    model=model,
                )
            )

        step_paths = sorted(
            (chain_dir / task_id / "steps").glob("step-*.json"),
            key=_junie_ide_step_index,
        )
        previous_step_at = started_at
        for step_path in step_paths:
            try:
                step = json.loads(step_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                diagnostics.append(f"unreadable Junie IDE step {step_path}: {exc}")
                continue
            if not isinstance(step, dict):
                continue
            step_index = _junie_ide_step_index(step_path)
            ordinal = source_base + step_index + 1
            raw_step_at = _junie_ide_file_timestamp(step_path)
            previous_dt = _parse_iso_datetime(previous_step_at)
            raw_step_dt = _parse_iso_datetime(raw_step_at)
            step_at = (
                max(previous_dt, raw_step_dt).isoformat()
                if previous_dt is not None and raw_step_dt is not None
                else raw_step_at
            )
            step_type = str(step.get("type") or "")
            command = str(step.get("command") or "")
            description = str(step.get("description") or "")
            if step_type == "Info" and command.strip().lower() == "thinking":
                content = _tool_argument_content(description)
                if content:
                    activities.append(
                        AgentActivity(
                            thread_id=chain_id,
                            turn_id=task_id,
                            activity_type="reasoning",
                            event_timestamp=step_at,
                            source_path=str(step_path),
                            source_ordinal=ordinal,
                            summary=_sanitize_unstructured_argument(description),
                            content=content,
                            model=model,
                        )
                    )
            elif step_type in {"ChatResponse", "Report"}:
                content = _tool_argument_content(description)
                if content:
                    activities.append(
                        AgentActivity(
                            thread_id=chain_id,
                            turn_id=task_id,
                            activity_type="output",
                            event_timestamp=step_at,
                            source_path=str(step_path),
                            source_ordinal=ordinal,
                            summary=_sanitize_unstructured_argument(command or description),
                            content=content,
                            model=model,
                        )
                    )
            elif step_type in {"Terminal", "Edit", "AskQuestion"} or (
                step_type == "Info" and command.strip()
            ):
                tool_name = _junie_ide_tool_name(step_type, command)
                argument_content = _tool_argument_content(command or description)
                result_content = _tool_result_content(description)
                tools.append(
                    ToolInterval(
                        thread_id=chain_id,
                        turn_id=task_id,
                        tool_name=tool_name,
                        started_at=previous_step_at,
                        completed_at=step_at,
                        duration_ms=_interval_ms(previous_step_at, step_at),
                        derivation_method="Junie IDE preceding-step bound",
                        attribution_confidence="bounded",
                        argument_summary=_sanitize_unstructured_argument(command or description),
                        source_path=str(step_path),
                        source_start_ordinal=max(source_base, ordinal - 1),
                        source_end_ordinal=ordinal,
                        argument_content=argument_content,
                        result_summary=_tool_result_summary(result_content),
                        result_content=result_content,
                        model=model,
                    )
                )
            previous_step_at = step_at
            step_stat = step_path.stat()
            source_manifest.append(
                SourceManifestEntry(
                    thread_id=chain_id,
                    path=str(step_path),
                    size_bytes=step_stat.st_size,
                    modified_at_ns=step_stat.st_mtime_ns,
                )
            )

        turns.append(
            AgentTurn(
                thread_id=chain_id,
                turn_id=task_id,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=_interval_ms(started_at, completed_at),
                outcome="complete" if is_finished else "active",
                usage=task_usage,
                skills_used=sorted(task_skills, key=str.casefold),
                run_id=chain_id,
                work_unit_id="main",
                attribution_confidence="exact",
                attribution_reason="Junie IDE task ownership",
                source_path=str(task_path),
                source_ordinal=source_base,
            )
        )
        task_stat = task_path.stat()
        source_manifest.append(
            SourceManifestEntry(
                thread_id=chain_id,
                path=str(task_path),
                size_bytes=task_stat.st_size,
                modified_at_ns=task_stat.st_mtime_ns,
            )
        )

    if not turns:
        raise ValueError(f"Junie IDE task chain has no readable tasks: {chain_dir}")
    token_totals = UsageTotals()
    for response in responses:
        token_totals = token_totals + response.usage
    if len(models) == 1:
        model_label = next(iter(models))
    else:
        model_label = f"mixed ({len(models)} models)" if models else ""
    thread = CodexThreadMetrics(
        thread_id=chain_id,
        thread_name="main",
        agent_path="/main",
        model=model_label,
        recorded_cost_usd=recorded_cost if has_complete_cost else None,
        started_at=min(turn.started_at for turn in turns),
        last_observed_at=max(turn.completed_at for turn in turns),
        token_totals=token_totals,
        responses=sorted(responses, key=lambda item: item.source_ordinal),
        turns=turns,
        activities=sorted(activities, key=lambda item: item.source_ordinal),
        tool_intervals=sorted(tools, key=lambda item: item.source_start_ordinal),
        skills_used=sorted(skills_used, key=str.casefold),
        terminal_state="complete" if all_tasks_complete else "active",
        source_path=str(manifest_path),
    )
    wall_start, wall_end, wall_ms, agent_ms, active_ms, tool_ms, peak = _time_metrics([thread])
    manifest_stat = manifest_path.stat()
    source_manifest.insert(
        0,
        SourceManifestEntry(
            thread_id=chain_id,
            path=str(manifest_path),
            size_bytes=manifest_stat.st_size,
            modified_at_ns=manifest_stat.st_mtime_ns,
        ),
    )
    return CodexRunMetrics(
        run_id=chain_id,
        root_thread_id=chain_id,
        state="complete" if all_tasks_complete else "live",
        observed_at=wall_end,
        wall_started_at=wall_start,
        wall_ended_at=wall_end,
        wall_time_ms=wall_ms,
        agent_time_ms=agent_ms,
        active_time_ms=active_ms,
        tool_time_ms=tool_ms,
        critical_path_ms=wall_ms,
        critical_path_method="Junie IDE observed task-chain interval",
        peak_concurrency=peak,
        usage_totals=token_totals,
        threads=[thread],
        work_units=_aggregate_work_units([thread]),
        phase_lanes=_aggregate_phase_lanes([thread]),
        cost=CostAssessment(
            status="recorded" if has_complete_cost else "unavailable",
            total_cost=recorded_cost if has_complete_cost else None,
            method=(
                "Junie IDE task cost"
                if has_complete_cost
                else "incomplete Junie IDE task cost metadata"
            ),
        ),
        source_manifest=source_manifest,
        diagnostics=sorted(set(diagnostics)),
        parser_version=JUNIE_SESSION_PARSER_VERSION,
        format_version=JUNIE_SESSION_FORMAT,
        runtime="Junie",
        run_label=run_label,
    )


def _junie_shell_write_paths(command: str) -> list[str]:
    paths: list[str] = []
    active_heredoc = ""
    declaration = re.compile(
        r"(?:^|&&|;)\s*cat\s*>>?\s*"
        r"(?P<path>\"[^\"]+\"|'[^']+'|[^\s;&|<>]+)\s*"
        r"<<-?\s*(?:\"(?P<double>[A-Za-z_][A-Za-z0-9_]*)\"|"
        r"'(?P<single>[A-Za-z_][A-Za-z0-9_]*)'|"
        r"(?P<plain>[A-Za-z_][A-Za-z0-9_]*))"
    )
    for line in command.splitlines():
        if active_heredoc:
            if line.strip() == active_heredoc:
                active_heredoc = ""
            continue
        match = declaration.search(line)
        if match is None:
            continue
        path = match.group("path").strip("\"'")
        if path not in paths:
            paths.append(path)
        active_heredoc = (
            match.group("double") or match.group("single") or match.group("plain")
        )
    return paths


def _junie_tool_payload(
    agent_event: dict[str, object],
) -> tuple[str, str, str, object] | None:
    kind = str(agent_event.get("kind") or "")
    if kind == "TerminalBlockUpdatedEvent":
        command = str(agent_event.get("command") or "—")
        written_paths = _junie_shell_write_paths(command)
        if written_paths:
            file_label = "file" if len(written_paths) == 1 else "files"
            return (
                "write_files",
                _tool_argument_summary(
                    {
                        "input": {
                            "operation": f"Write {len(written_paths)} {file_label}",
                            "files": written_paths,
                        }
                    }
                ),
                _tool_argument_content(command),
                agent_event.get("output") or agent_event.get("presentableOutput") or "",
            )
        return (
            "exec",
            _sanitize_unstructured_argument(command),
            _tool_argument_content(command),
            agent_event.get("output") or agent_event.get("presentableOutput") or "",
        )
    if kind == "ToolBlockUpdatedEvent":
        tool_name = str(agent_event.get("toolType") or "tool").lower()
        argument = agent_event.get("text") or agent_event.get("details") or "—"
        return (
            tool_name,
            _sanitize_unstructured_argument(str(argument)),
            "",
            agent_event.get("details") or "",
        )
    if kind == "ViewFilesBlockUpdatedEvent":
        files = agent_event.get("files")
        paths = [
            str(item.get("relativePath"))
            for item in files
            if isinstance(item, dict) and item.get("relativePath")
        ] if isinstance(files, list) else []
        return (
            "read",
            _tool_argument_summary({"input": {"files": paths}}),
            "",
            agent_event.get("details") or "",
        )
    if kind == "FileChangesBlockUpdatedEvent":
        changes = agent_event.get("changes")
        paths = [
            str(item.get("afterRelativePath") or item.get("beforeRelativePath"))
            for item in changes
            if isinstance(item, dict)
            and (item.get("afterRelativePath") or item.get("beforeRelativePath"))
        ] if isinstance(changes, list) else []
        return (
            "apply_patch",
            _tool_argument_summary({"input": {"files": paths}}),
            "",
            agent_event.get("details") or "",
        )
    return None


def parse_junie_session(path: Path) -> CodexRunMetrics:
    """Normalize one Junie session for native execution reporting.

    `path` may be a session directory or its `events.jsonl`. The parser reads
    the append-only stream without modifying it, returns task, agent, usage,
    cost, tool, and bounded result metrics, and raises `ValueError` when the
    source lacks recognizable Junie events or agent identities.
    """

    events_path = _junie_events_path(path).resolve()
    records, diagnostics = _parse_jsonl_append_safe(events_path)
    if not records or not any(
        record.get("kind") in {"UserPromptEvent", "SessionA2uxEvent", "TaskStartedEvent"}
        for _, record in records[:20]
    ):
        raise ValueError(f"No native Junie session events found at {events_path}")

    session_id = events_path.parent.name
    all_timestamps = [
        _normalize_timestamp(record.get("timestampMs"))
        for _, record in records
        if _parse_iso_datetime(record.get("timestampMs")) is not None
    ]
    tasks: dict[str, dict[str, object]] = {}
    task_order: list[str] = []
    current_task_id = ""
    last_task_id = ""
    pending_prompt_at = ""
    pending_prompt_ordinal = 0
    pending_prompt_content = ""
    agent_meta: dict[str, dict[str, str]] = {}
    agent_task_names: dict[str, str] = {}
    custom_agent_ids_by_name: dict[str, str] = {}
    for _, record in records:
        event = record.get("event")
        agent_event = event.get("agentEvent") if isinstance(event, dict) else None
        raw_agent = agent_event.get("agent") if isinstance(agent_event, dict) else None
        if not isinstance(raw_agent, dict) or raw_agent.get("kind") != "CustomAgent":
            continue
        custom_id = str(raw_agent.get("id") or "")
        custom_name = str(raw_agent.get("name") or custom_id)
        if custom_id:
            custom_agent_ids_by_name[custom_name] = custom_id
            agent_meta[custom_id] = {"kind": "CustomAgent", "name": custom_name}
    active_custom_models: dict[str, str] = {}
    agent_events: dict[str, list[tuple[int, str, str, dict[str, object]]]] = {}
    tool_updates: dict[
        tuple[str, str, str],
        list[tuple[int, str, str, dict[str, object]]],
    ] = {}
    activity_updates: dict[
        tuple[str, str, str],
        list[tuple[int, str, str, dict[str, object]]],
    ] = {}
    responses: dict[str, list[ResponseUsage]] = {}
    models: dict[str, Counter[str]] = {}
    recorded_costs: dict[str, float] = {}
    for ordinal, record in records:
        timestamp = _normalize_timestamp(record.get("timestampMs"))
        kind = str(record.get("kind") or "")
        if kind == "UserPromptEvent":
            pending_prompt_at = timestamp
            pending_prompt_ordinal = ordinal
            raw_prompt = record.get("presentablePrompt") or record.get("prompt") or ""
            pending_prompt_content = (
                _tool_argument_content(raw_prompt) if isinstance(raw_prompt, str) else ""
            )
            continue
        if kind == "TaskStartedEvent":
            current_task_id = str(record.get("taskId") or f"task-{len(task_order) + 1}")
            last_task_id = current_task_id
            task_order.append(current_task_id)
            tasks[current_task_id] = {
                "started_at": pending_prompt_at or timestamp,
                "completed_at": "",
                "outcome": "active",
                "source_ordinal": ordinal,
                "prompt_at": pending_prompt_at or timestamp,
                "prompt_ordinal": pending_prompt_ordinal or ordinal,
                "prompt_content": pending_prompt_content,
            }
            pending_prompt_at = ""
            pending_prompt_ordinal = 0
            pending_prompt_content = ""
            continue
        if kind == "TaskState":
            if current_task_id and current_task_id in tasks:
                state = str(record.get("state") or "indeterminate").lower()
                tasks[current_task_id]["completed_at"] = timestamp
                tasks[current_task_id]["outcome"] = "complete" if state == "completed" else state
            current_task_id = ""
            continue
        if kind != "SessionA2uxEvent":
            continue
        event = record.get("event")
        agent_event = event.get("agentEvent") if isinstance(event, dict) else None
        if not isinstance(agent_event, dict):
            continue
        raw_agent = agent_event.get("agent")
        if not isinstance(raw_agent, dict):
            diagnostics.append(f"Junie agent event without agent identity at line {ordinal}")
            continue
        raw_agent_id = str(raw_agent.get("id") or "")
        if not raw_agent_id:
            diagnostics.append(f"Junie agent event without agent id at line {ordinal}")
            continue
        agent_id = raw_agent_id
        event_kind = str(agent_event.get("kind") or "")
        if event_kind == "AgentTaskNameUpdatedEvent":
            task_name = str(agent_event.get("name") or "")
            if task_name:
                agent_task_names[agent_id] = task_name
        if event_kind == "CustomAgentBlockUpdatedEvent":
            custom_name = str(agent_event.get("name") or "")
            custom_model = str(agent_event.get("model") or "")
            if custom_name and custom_model:
                active_custom_models[custom_model] = custom_name
        if event_kind == "LlmResponseMetadataEvent" and raw_agent.get("kind") == "MainAgent":
            usage_list = agent_event.get("modelUsage")
            usage_models = {
                str(item.get("model") or "")
                for item in usage_list
                if isinstance(item, dict)
            } if isinstance(usage_list, list) else set()
            custom_names = {
                active_custom_models[model]
                for model in usage_models
                if model in active_custom_models
            }
            if len(custom_names) == 1:
                custom_name = next(iter(custom_names))
                agent_id = custom_agent_ids_by_name.get(custom_name, raw_agent_id)
        if agent_id == raw_agent_id:
            agent_meta[agent_id] = {
                "kind": str(raw_agent.get("kind") or "UnknownAgent"),
                "name": str(raw_agent.get("name") or agent_id),
            }
        turn_id = current_task_id or last_task_id
        agent_events.setdefault(agent_id, []).append((ordinal, timestamp, turn_id, agent_event))

        payload = _junie_tool_payload(agent_event)
        step_id = str(agent_event.get("stepId") or "")
        if payload is not None and step_id:
            key = (agent_id, step_id, str(agent_event.get("kind") or ""))
            tool_updates.setdefault(key, []).append((ordinal, timestamp, turn_id, agent_event))
        if event_kind == "AgentThoughtBlockUpdatedEvent" and step_id:
            key = (agent_id, step_id, event_kind)
            activity_updates.setdefault(key, []).append(
                (ordinal, timestamp, turn_id, agent_event)
            )

        if event_kind != "LlmResponseMetadataEvent":
            if (
                event_kind == "CustomAgentBlockUpdatedEvent"
                and agent_event.get("status") == "FINISHED"
            ):
                active_custom_models.pop(str(agent_event.get("model") or ""), None)
            continue
        usage_list = agent_event.get("modelUsage")
        if not isinstance(usage_list, list):
            diagnostics.append(f"invalid Junie model usage list at line {ordinal}")
            continue
        for model_usage in usage_list:
            usage = _junie_usage(model_usage)
            if usage is None or not isinstance(model_usage, dict):
                diagnostics.append(f"invalid Junie model usage at line {ordinal}")
                continue
            raw_cost = model_usage.get("cost")
            response_cost = (
                float(raw_cost)
                if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool)
                else None
            )
            response = ResponseUsage(
                event_timestamp=timestamp,
                usage=usage,
                turn_id=turn_id or None,
                source_path=str(events_path),
                source_ordinal=ordinal,
                model=str(model_usage.get("model") or "unknown"),
                recorded_cost_usd=response_cost,
                derivation_method="Junie response metadata",
                attribution_confidence="exact" if turn_id else "unattributed",
            )
            responses.setdefault(agent_id, []).append(response)
            model = str(model_usage.get("model") or "unknown")
            models.setdefault(agent_id, Counter())[model] += 1
            if response_cost is not None:
                recorded_costs[agent_id] = recorded_costs.get(agent_id, 0.0) + response_cost

    if not agent_events:
        raise ValueError(f"Junie session has no agent events: {events_path}")
    main_agent_id = next(
        (agent_id for agent_id, meta in agent_meta.items() if meta["kind"] == "MainAgent"),
        next(iter(agent_events)),
    )
    all_tasks_complete = bool(tasks) and all(
        task.get("outcome") == "complete" for task in tasks.values()
    )
    threads: list[CodexThreadMetrics] = []
    for agent_id in sorted(
        agent_events,
        key=lambda candidate: (candidate != main_agent_id, agent_meta[candidate]["name"]),
    ):
        events = agent_events[agent_id]
        meta = agent_meta[agent_id]
        by_turn: dict[str, list[tuple[int, str, dict[str, object]]]] = {}
        for ordinal, timestamp, turn_id, agent_event in events:
            if turn_id:
                by_turn.setdefault(turn_id, []).append((ordinal, timestamp, agent_event))
        agent_responses = responses.get(agent_id, [])
        turns: list[AgentTurn] = []
        for turn_id in task_order:
            activity = by_turn.get(turn_id, [])
            owned_responses = [item for item in agent_responses if item.turn_id == turn_id]
            if not activity and not owned_responses:
                continue
            task = tasks[turn_id]
            if meta["kind"] == "MainAgent":
                started_at = str(task.get("started_at") or activity[0][1])
                completed_at = str(task.get("completed_at") or activity[-1][1])
                outcome = str(task.get("outcome") or "active")
            else:
                started_at = min(item[1] for item in activity)
                completed_at = max(item[1] for item in activity)
                outcome = "complete" if all_tasks_complete else "active"
            turn_usage = UsageTotals()
            for response in owned_responses:
                turn_usage = turn_usage + response.usage
            turns.append(
                AgentTurn(
                    thread_id=agent_id,
                    turn_id=turn_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=_interval_ms(started_at, completed_at),
                    time_to_first_token_ms=None,
                    outcome=outcome,
                    usage=turn_usage,
                    run_id=session_id,
                    work_unit_id=meta["name"],
                    attribution_confidence="exact",
                    attribution_reason="Junie task and agent identity",
                    source_path=str(events_path),
                    source_ordinal=int(task.get("source_ordinal") or activity[0][0]),
                )
            )

        tools: list[ToolInterval] = []
        skills_used: set[str] = set()
        turns_by_id = {turn.turn_id: turn for turn in turns}
        for (owner_id, _, _), versions in tool_updates.items():
            if owner_id != agent_id:
                continue
            versions.sort(key=lambda item: item[0])
            start_ordinal, started_at, start_turn_id, _ = versions[0]
            end_ordinal, completed_at, end_turn_id, final_event = versions[-1]
            payload = _junie_tool_payload(final_event)
            if payload is None:
                continue
            tool_name, argument_summary, argument_content, raw_result = payload
            tool_skills = _skill_names_from_value(argument_summary)
            tool_skills.update(_skill_names_from_value(argument_content))
            skills_used.update(tool_skills)
            tool_turn_id = end_turn_id or start_turn_id or None
            if tool_turn_id and tool_turn_id in turns_by_id:
                turn = turns_by_id[tool_turn_id]
                turn.skills_used = sorted(
                    set(turn.skills_used) | tool_skills,
                    key=str.casefold,
                )
            result_content = _tool_result_content(raw_result)
            tools.append(
                ToolInterval(
                    thread_id=agent_id,
                    turn_id=tool_turn_id,
                    tool_name=tool_name,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=_interval_ms(started_at, completed_at),
                    derivation_method="Junie block update interval",
                    attribution_confidence="bounded",
                    argument_summary=argument_summary,
                    source_path=str(events_path),
                    source_start_ordinal=start_ordinal,
                    source_end_ordinal=end_ordinal,
                    argument_content=argument_content,
                    result_summary=_tool_result_summary(result_content),
                    result_content=result_content,
                )
            )

        activities: list[AgentActivity] = []
        for turn in turns:
            task = tasks[turn.turn_id]
            prompt_content = str(task.get("prompt_content") or "")
            if not prompt_content:
                continue
            activities.append(
                AgentActivity(
                    thread_id=agent_id,
                    turn_id=turn.turn_id,
                    activity_type="input",
                    event_timestamp=str(task.get("prompt_at") or task.get("started_at") or ""),
                    source_path=str(events_path),
                    source_ordinal=int(task.get("prompt_ordinal") or task.get("source_ordinal") or 0),
                    summary=f"Initial prompt · {len(prompt_content):,} characters",
                    content=prompt_content,
                )
            )
        for (owner_id, _, _), versions in activity_updates.items():
            if owner_id != agent_id:
                continue
            ordinal, timestamp, turn_id, final_event = sorted(versions, key=lambda item: item[0])[-1]
            raw_text = final_event.get("text")
            if not isinstance(raw_text, str) or not raw_text.strip():
                continue
            content = _tool_argument_content(raw_text)
            activities.append(
                AgentActivity(
                    thread_id=agent_id,
                    turn_id=turn_id or None,
                    activity_type="reasoning",
                    event_timestamp=timestamp,
                    source_path=str(events_path),
                    source_ordinal=ordinal,
                    summary=_sanitize_unstructured_argument(raw_text),
                    content=content,
                )
            )

        token_totals = UsageTotals()
        for response in agent_responses:
            token_totals = token_totals + response.usage
        model_counts = models.get(agent_id, Counter())
        if not model_counts:
            model_label = ""
        elif len(model_counts) == 1:
            model_label = next(iter(model_counts))
        else:
            model_label = f"mixed ({len(model_counts)} models)"
        thread_diagnostics = []
        if len(model_counts) > 1:
            thread_diagnostics.append("models: " + ", ".join(sorted(model_counts)))
        event_times = [item[1] for item in events]
        thread_started = min(event_times)
        thread_ended = max(event_times)
        if agent_id == main_agent_id and all_timestamps:
            thread_started = min(all_timestamps)
            thread_ended = max(all_timestamps)
        threads.append(
            CodexThreadMetrics(
                thread_id=agent_id,
                parent_thread_id="" if agent_id == main_agent_id else main_agent_id,
                thread_name=(
                    agent_task_names.get(agent_id)
                    or ("main" if agent_id == main_agent_id else meta["name"])
                ),
                agent_path=(
                    "/main" if agent_id == main_agent_id else f"/main/{meta['name']}"
                ),
                agent_role=meta["name"] if meta["kind"] == "CustomAgent" else "",
                model=model_label,
                recorded_cost_usd=recorded_costs.get(agent_id),
                started_at=thread_started,
                last_observed_at=thread_ended,
                token_totals=token_totals,
                responses=agent_responses,
                turns=turns,
                activities=sorted(activities, key=lambda item: item.source_ordinal),
                tool_intervals=sorted(tools, key=lambda tool: tool.source_start_ordinal),
                skills_used=sorted(skills_used, key=str.casefold),
                terminal_state="complete" if all_tasks_complete else "active",
                source_path=str(events_path),
                diagnostics=thread_diagnostics,
            )
        )

    usage_totals = UsageTotals()
    for thread in threads:
        usage_totals = usage_totals + thread.token_totals
        diagnostics.extend(f"{_agent_assignment(thread)}: {item}" for item in thread.diagnostics)
    wall_start, wall_end, wall_ms, agent_ms, active_ms, tool_ms, peak = _time_metrics(threads)
    used_threads = [thread for thread in threads if thread.token_totals.processed_tokens]
    has_complete_cost = bool(used_threads) and all(
        thread.recorded_cost_usd is not None for thread in used_threads
    )
    total_cost = (
        sum(thread.recorded_cost_usd or 0.0 for thread in used_threads)
        if has_complete_cost
        else None
    )
    stat = events_path.stat()
    return CodexRunMetrics(
        run_id=session_id,
        root_thread_id=session_id,
        state="complete" if all_tasks_complete else "live",
        observed_at=max(all_timestamps) if all_timestamps else "",
        wall_started_at=wall_start,
        wall_ended_at=wall_end,
        wall_time_ms=wall_ms,
        agent_time_ms=agent_ms,
        active_time_ms=active_ms,
        tool_time_ms=tool_ms,
        critical_path_ms=wall_ms,
        critical_path_method="Junie observed session interval",
        peak_concurrency=peak,
        usage_totals=usage_totals,
        threads=threads,
        work_units=_aggregate_work_units(threads),
        phase_lanes=_aggregate_phase_lanes(threads),
        cost=CostAssessment(
            status="recorded" if has_complete_cost else "unavailable",
            total_cost=total_cost,
            method=(
                "Junie response metadata"
                if has_complete_cost
                else "incomplete Junie cost metadata"
            ),
        ),
        source_manifest=[
            SourceManifestEntry(
                thread_id=session_id,
                path=str(events_path),
                size_bytes=stat.st_size,
                modified_at_ns=stat.st_mtime_ns,
            )
        ],
        diagnostics=sorted(set(diagnostics)),
        parser_version=JUNIE_SESSION_PARSER_VERSION,
        format_version=JUNIE_SESSION_FORMAT,
        runtime="Junie",
    )


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


def _is_native_codex_rollout(path: Path) -> bool:
    return path.is_file() and _rollout_identity(path) is not None


def _sessions_root_for_rollout(path: Path) -> Path:
    for parent in path.resolve().parents:
        if parent.name == "sessions":
            return parent
    return path.resolve().parent


def _is_sealed_codex_manifest(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() != ".json":
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(data, dict)
        and data.get("format_version") == CODEX_ROLLOUT_FORMAT
        and data.get("state") == "sealed"
    )


class SealedCodexRunAdapter(BaseReportAdapter):
    """Reproduce a native Codex report from an immutable source manifest."""

    @staticmethod
    def matches(path: Path) -> bool:
        return _is_sealed_codex_manifest(path)

    @staticmethod
    def build(path: Path) -> ReportDocument:
        run = reprocess_sealed_codex_run(path)
        return ReportDocument(
            run_title=AGENT_EXECUTION_METRICS_TITLE,
            workspace=path,
            codex_run=run,
        )


class NativeCodexRolloutAdapter(BaseReportAdapter):
    """Build a native Codex subtree report from a selected rollout path."""

    @staticmethod
    def matches(path: Path) -> bool:
        return _is_native_codex_rollout(path)

    @staticmethod
    def build(path: Path) -> ReportDocument:
        identity = _rollout_identity(path)
        if identity is None:
            raise ValueError(f"No Codex thread identity found in {path}")
        run = build_codex_rollout_run(identity[0], _sessions_root_for_rollout(path))
        return ReportDocument(
            run_title=AGENT_EXECUTION_METRICS_TITLE,
            workspace=path,
            codex_run=run,
        )


class NativeJunieSessionAdapter(BaseReportAdapter):
    """Build an execution report from Junie's durable session event stream."""

    @staticmethod
    def matches(path: Path) -> bool:
        return _is_native_junie_session(path)

    @staticmethod
    def build(path: Path) -> ReportDocument:
        return ReportDocument(
            run_title=AGENT_EXECUTION_METRICS_TITLE,
            workspace=path,
            codex_run=parse_junie_session(path),
        )


class NativeJunieIdeChainAdapter(BaseReportAdapter):
    """Build an execution report from Junie IDE's durable issue-chain cache."""

    @staticmethod
    def matches(path: Path) -> bool:
        return _is_native_junie_ide_chain(path)

    @staticmethod
    def build(path: Path) -> ReportDocument:
        return ReportDocument(
            run_title=AGENT_EXECUTION_METRICS_TITLE,
            workspace=path,
            codex_run=parse_junie_ide_chain(path),
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
    SealedCodexRunAdapter,
    NativeCodexRolloutAdapter,
    NativeJunieSessionAdapter,
    NativeJunieIdeChainAdapter,
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
        f"Expected a native Codex rollout, native Junie session or IDE task chain, comparison manifest, "
        f"methodology workspace with .methodology-runner/state.json, or prompt-runner run/module directory."
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


def _escape_html_attribute(text: str) -> str:
    """Escape text for a double-quoted HTML attribute."""

    return _escape_html(text).replace('"', "&quot;").replace("'", "&#x27;")


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
    group_ids: tuple[str, ...] = (),
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
        if group_ids:
            row_attrs += f' data-groups="{" ".join(group_ids)}"'
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
            if group_ids:
                detail_attrs += f' data-groups="{" ".join(group_ids)}"'
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
            m = re.search(r'VERDICT:\s*(pass|revise|escalate|select)', step.detail.output_text, re.IGNORECASE)
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
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}h{m:02d}m{s:02d}s"
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
    fork_group_id = f"fork-{fork.fork_index:02d}"
    fork_toggle_id = f"{fork_group_id}-toggle"
    selected_note = ""
    if fork.selected_variant:
        selected_note = f' <span class="variant-metrics">selected={fork.selected_variant}'
        if fork.selector_rationale:
            selected_note += f" | {fork.selector_rationale}"
        selected_note += "</span>"

    # --- Fork header ---
    rows.append(
        f'<tr class="fork-header is-collapsible" onclick="toggleGroup(\'{fork_group_id}\', \'{fork_toggle_id}\')"><td colspan="8">'
        f'<span class="fork-toggle is-open" id="{fork_toggle_id}" aria-hidden="true">▾</span>'
        f'<strong>Fork {fork.fork_index}: {fork.fork_title}</strong>'
        f'{selected_note}'
        f'</td></tr>'
    )

    if fork.selector_steps:
        selector_group_id = f"{fork_group_id}-selector"
        selector_toggle_id = f"{selector_group_id}-toggle"
        dur = _steps_duration_seconds(fork.selector_steps)
        dur_str = _fmt_duration(dur)
        cost = _steps_cost(fork.selector_steps)
        turns = _steps_turns(fork.selector_steps)
        out_tok = _steps_output_tokens(fork.selector_steps)
        verdict = _steps_verdict(fork.selector_steps)
        verdict_cls = "verdict-pass" if verdict == "pass" else (
            "verdict-fail" if verdict in ("fail", "revise", "escalate") else ""
        )
        rows.append(
            f'<tr class="variant-header selector-header is-collapsible" data-groups="{fork_group_id}" onclick="toggleGroup(\'{selector_group_id}\', \'{selector_toggle_id}\');event.stopPropagation()"><td colspan="8">'
            f'<span class="variant-toggle is-open" id="{selector_toggle_id}" aria-hidden="true">▾</span>'
            f'<strong>Selector</strong>'
            f' <span class="variant-metrics">'
            f'{turns} turns'
            f' | Output: {out_tok:,}'
            f' | {dur_str}'
            f' | ${cost:.2f}'
            f' | <span class="{verdict_cls}">{verdict}</span>'
            f'</span>'
            f'</td></tr>'
        )
        step_counter = _render_steps_rows(
            fork.selector_steps,
            grand_total,
            step_counter,
            rows,
            popups,
            report_started_at,
            row_class="selector-step",
            group_ids=(fork_group_id, selector_group_id),
        )

    # --- Per-variant detail sections ---
    variant_names = sorted(fork.variants.keys())

    for vname in variant_names:
        vsteps = fork.variants[vname]
        label = vname.replace("variant-", "").upper()
        title = fork.variant_titles.get(vname, "").strip()
        heading = f"Variant {label}"
        if title and title.lower() != label.lower():
            heading += f": {title}"
        if fork.selected_variant and _normalize_variant_key(fork.selected_variant) == vname:
            heading += " (selected)"
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
        variant_group_id = f"{fork_group_id}-{variant_css}"
        variant_toggle_id = f"{variant_group_id}-toggle"
        rows.append(
            f'<tr class="variant-header {variant_cls} is-collapsible" data-groups="{fork_group_id}" onclick="toggleGroup(\'{variant_group_id}\', \'{variant_toggle_id}\');event.stopPropagation()"><td colspan="8">'
            f'<span class="variant-toggle is-open" id="{variant_toggle_id}" aria-hidden="true">▾</span>'
            f'<strong>{heading}</strong>'
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
            group_ids=(fork_group_id, variant_group_id),
        )

    return step_counter


# ---------------------------------------------------------------------------
# HTML renderer (top-level)
# ---------------------------------------------------------------------------

def render_html(
    document: ReportDocument,
    formatter_config: ToolFormatterConfig | None = None,
) -> str:
    """Render a backend-neutral report document as a complete HTML page."""
    if document.codex_run is not None:
        return render_codex_rollout_html(document.codex_run, formatter_config)
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
                group_ids=(phase_group_id,), group_hidden=True,
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
  .fork-toggle {{
    display: inline-block; width: 1.1em; margin-right: 6px; color: #2c5e8f;
    transition: transform 0.12s ease;
  }}
  .fork-toggle.is-open {{ transform: rotate(90deg); }}
  .variant-toggle {{
    display: inline-block; width: 1.1em; margin-right: 6px; color: #666;
    transition: transform 0.12s ease;
  }}
  .variant-toggle.is-open {{ transform: rotate(90deg); }}
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
  tr.fork-header.is-collapsible {{ cursor: pointer; }}
  tr.fork-header.is-collapsible:hover td {{ background: #cfe1f1; }}
  .verdict-pass {{ color: #27ae60; font-weight: bold; }}
  .verdict-fail {{ color: #e74c3c; font-weight: bold; }}
  tr.variant-header td {{
    background: #f0f4f8; padding: 8px 12px 8px 24px; font-size: 0.95em;
    border-top: 2px solid #b0c8e0; color: #444;
  }}
  tr.variant-header.is-collapsible {{ cursor: pointer; }}
  tr.variant-header.is-collapsible:hover td {{ background: #e8eef5; }}
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
function groupIsOpen(groupId) {{
  var toggle = document.getElementById(groupId + '-toggle');
  if (!toggle) return true;
  return toggle.classList.contains('is-open');
}}
function rowGroups(row) {{
  var raw = row.getAttribute('data-groups');
  if (!raw) return [];
  return raw.split(/\\s+/).filter(Boolean);
}}
function shouldRowBeVisible(row) {{
  var groups = rowGroups(row);
  for (var i = 0; i < groups.length; i++) {{
    if (!groupIsOpen(groups[i])) return false;
  }}
  if (row.classList.contains('detail-row')) {{
    return row.dataset.open === '1';
  }}
  return true;
}}
function refreshGroupVisibility() {{
  document.querySelectorAll('tr[data-groups]').forEach(function(row) {{
    row.style.display = shouldRowBeVisible(row) ? 'table-row' : 'none';
  }});
}}
function toggleGroup(groupId, toggleId) {{
  var toggle = document.getElementById(toggleId);
  if (toggle) {{
    if (toggle.classList.contains('is-open')) toggle.classList.remove('is-open');
    else toggle.classList.add('is-open');
  }}
  refreshGroupVisibility();
}}
function toggleStepDetail(rowId, toggleId) {{
  var row = document.getElementById(rowId);
  if (!row) return;
  var toggle = document.getElementById(toggleId);
  var isOpen = row.style.display !== 'none';
  if (isOpen) {{
    row.dataset.open = '0';
    if (toggle) toggle.classList.remove('is-open');
  }} else {{
    row.dataset.open = '1';
    if (toggle) toggle.classList.add('is-open');
  }}
  refreshGroupVisibility();
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
  refreshGroupVisibility();
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
<h2>{workspace} — total {_fmt_duration(grand_total)} — ${grand_cost:.2f}</h2>
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


def _default_codex_discovery_index_path() -> Path:
    return Path.home() / ".codex" / "agent-report" / "rollout-discovery-v2.sqlite3"


def _emit_report_progress(
    completed: int,
    label: str,
    detail: str,
    worker: str | None = None,
) -> None:
    """Emit one machine-readable desktop progress event on stderr."""

    event = {
        "completed": completed,
        "total": 100,
        "label": label,
        "detail": detail,
        "worker": worker,
    }
    payload = json.dumps(event, separators=(",", ":"))
    print(f"AGENT_REPORT_PROGRESS {payload}", file=sys.stderr, flush=True)


def _emit_report_item_progress(
    item_completed: int,
    item_total: int,
    label: str,
    detail: str,
    worker: str | None = None,
) -> None:
    """Emit report progress with an item counter scoped to the parent or worker."""

    completed = 25 + round(item_completed / max(1, item_total) * 40)
    event = {
        "completed": completed,
        "total": 100,
        "itemCompleted": item_completed,
        "itemTotal": item_total,
        "label": label,
        "detail": detail,
        "worker": worker,
    }
    payload = json.dumps(event, separators=(",", ":"))
    print(f"AGENT_REPORT_PROGRESS {payload}", file=sys.stderr, flush=True)


def _child_output_path(parent_output: Path, slug: str) -> Path:
    suffix = parent_output.suffix or ".html"
    return parent_output.with_name(f"{parent_output.stem}-{slug}{suffix}")


def _split_codex_sequence_document(
    full_html: str,
    sequence_filename: str,
) -> tuple[str, str] | None:
    """Split one rendered report into lean main and sequence documents."""

    start_marker = "<!-- agent-sequence:start -->"
    end_marker = "<!-- agent-sequence:end -->"
    start = full_html.find(start_marker)
    end = full_html.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0:
        return None
    sequence_section = full_html[start + len(start_marker) : end]
    main_html = full_html[:start] + full_html[end + len(end_marker) :]
    main_html = main_html.replace(
        'href="?view=sequence#agent-sequence"',
        'href="{filename}?view=sequence#agent-sequence"'.format(
            filename=_escape_html_attribute(quote(sequence_filename, safe=""))
        ),
        1,
    )
    head_end = full_html.find("</head>")
    script_start = full_html.find("<script>\n")
    if head_end < 0 or script_start < 0:
        return None
    head = full_html[: head_end + len("</head>")]
    sequence_html = (
        head
        + '<body class="sequence-only">'
        + sequence_section
        + full_html[script_start:]
    )
    return main_html, sequence_html


def _write_codex_outputs(
    run: CodexRunMetrics,
    html_output: Path,
    *,
    formatter_config: ToolFormatterConfig | None = None,
    nav_links: list[tuple[str, str]] | None = None,
    page_title: str | None = None,
    page_subtitle: str = "",
    page_action_links: list[tuple[str, str]] | None = None,
    json_output: Path | None = None,
    turn_csv_output: Path | None = None,
    work_unit_csv_output: Path | None = None,
    markdown_output: Path | None = None,
    emit_progress: bool = False,
    workers: int = 1,
) -> None:
    html_output.parent.mkdir(parents=True, exist_ok=True)
    if emit_progress:
        _emit_report_progress(
            80,
            "Rendering report",
            "Building heatmaps, timelines, tables, and the sequence view.",
        )
    rendered_html = render_codex_rollout_html(
        run,
        formatter_config,
        nav_links=nav_links,
        page_title=page_title,
        page_subtitle=page_subtitle,
        page_action_links=page_action_links,
        progress=_emit_report_progress if emit_progress else None,
        worker_progress=_emit_report_progress if emit_progress else None,
        workers=workers,
    )
    sequence_output = _child_output_path(html_output, "sequence")
    if emit_progress:
        _emit_report_progress(
            97,
            "Preparing report files",
            "Separating the sequence view from the main report.",
        )
    split_documents = _split_codex_sequence_document(
        rendered_html,
        sequence_output.name,
    )
    if emit_progress:
        _emit_report_progress(
            99,
            "Writing report files",
            "Saving the main report and its companion files.",
        )
    if split_documents is None:
        html_output.write_text(
            _with_copyright_footer(rendered_html), encoding="utf-8"
        )
    else:
        main_html, sequence_html = split_documents
        html_output.write_text(
            _with_copyright_footer(main_html), encoding="utf-8"
        )
        sequence_output.write_text(
            _with_copyright_footer(sequence_html), encoding="utf-8"
        )
    companions = (
        (json_output, codex_run_to_json(run)),
        (turn_csv_output, render_codex_rollout_turn_csv(run)),
        (work_unit_csv_output, render_codex_rollout_work_unit_csv(run)),
        (markdown_output, render_codex_rollout_markdown(run)),
    )
    for path, content in companions:
        if path is None:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _catalog_task_title(request: str) -> str:
    """Derive the same bounded, redacted title used by a generated report."""

    redacted = _redact_unstructured_text(request)
    activity = AgentActivity(
        thread_id="",
        turn_id=None,
        activity_type="input",
        event_timestamp="",
        source_path="",
        source_ordinal=0,
        summary="User input",
        content=redacted,
    )
    return _derived_task_title([activity])


def _read_codex_catalog_entry(
    path: Path,
    source_store: str,
    *,
    include_title: bool = True,
) -> _AgentCatalogEntry | None:
    """Read only the metadata and first genuine request needed by the catalog."""

    thread_id = ""
    parent_thread_id = ""
    started_at: datetime | None = None
    task_title = ""
    workspace = ""
    infer_parent_from_delegation = False
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for record_count, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                record_timestamp = _parse_iso_datetime(record.get("timestamp"))
                if record_timestamp is not None and started_at is None:
                    started_at = record_timestamp
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                if record.get("type") == "session_meta" and not thread_id:
                    thread_id = str(payload.get("id") or payload.get("session_id") or "")
                    parent_thread_id, _, _ = _spawn_metadata(payload)
                    infer_parent_from_delegation = (
                        payload.get("thread_source") == "subagent"
                        or payload.get("source") == "subagent"
                    )
                    recorded_title = next(
                        (
                            str(payload[key]).strip()
                            for key in ("task_title", "thread_title", "title")
                            if isinstance(payload.get(key), str)
                            and str(payload[key]).strip()
                        ),
                        "",
                    )
                    task_title = (
                        _catalog_task_title(recorded_title) if recorded_title else ""
                    )
                    workspace = str(payload.get("cwd") or payload.get("workspace") or "")
                    if task_title or not include_title:
                        break
                    continue
                if (
                    thread_id
                    and not task_title
                    and record.get("type") == "response_item"
                    and payload.get("type") == "message"
                    and payload.get("role") == "user"
                ):
                    raw_request = _response_item_text(payload, "content")
                    task_title = _catalog_task_title(raw_request)
                    if task_title:
                        if infer_parent_from_delegation and not parent_thread_id:
                            inferred_parent = _initial_delegation_source(raw_request)
                            if inferred_parent and inferred_parent != thread_id:
                                parent_thread_id = inferred_parent
                        break
                if thread_id and record_count >= 200:
                    break
    except OSError:
        return None
    if not thread_id:
        return None
    return _AgentCatalogEntry(
        run_id=thread_id,
        parent_thread_id=parent_thread_id,
        started_at=started_at or _mtime(path),
        task_title=task_title,
        workspace=workspace,
        source_path=path.resolve(),
        source_store=source_store,
    )


def _catalog_path_date(path: Path) -> str:
    """Return the calendar date encoded in a native log filename when present."""

    codex_match = re.search(r"rollout-(\d{4}-\d{2}-\d{2})T", path.name)
    if codex_match:
        return codex_match.group(1)
    junie_match = re.search(r"session-(\d{2})(\d{2})(\d{2})-", str(path))
    if junie_match:
        return f"20{junie_match.group(1)}-{junie_match.group(2)}-{junie_match.group(3)}"
    return ""


def _catalog_path_matches_dates(path: Path, from_date: str, to_date: str) -> bool:
    """Use an encoded path date as a cheap prefilter before opening a log."""

    path_date = _catalog_path_date(path)
    if not path_date:
        return True
    earliest_path_date = (
        (_parse_catalog_date(from_date, end_of_day=False) - timedelta(days=1))
        .date()
        .isoformat()
        if from_date
        else ""
    )
    latest_path_date = (
        _parse_catalog_date(to_date, end_of_day=True).date().isoformat()
        if to_date
        else ""
    )
    if earliest_path_date and path_date < earliest_path_date:
        return False
    if latest_path_date and path_date > latest_path_date:
        return False
    return True


def _index_codex_catalog(
    roots: list[Path],
    *,
    from_date: str = "",
    to_date: str = "",
    include_all_identities: bool = False,
) -> dict[str, _AgentCatalogEntry]:
    """Index reportable Codex rollouts across active and archived stores."""

    entries: dict[str, _AgentCatalogEntry] = {}
    for root in roots:
        source_store = root.name or str(root)
        for path in _candidate_rollouts(root):
            in_date_range = _catalog_path_matches_dates(path, from_date, to_date)
            if not in_date_range and not include_all_identities:
                continue
            entry = _read_codex_catalog_entry(
                path,
                source_store,
                include_title=in_date_range,
            )
            if entry is None:
                continue
            existing = entries.get(entry.run_id)
            if existing is not None and existing.source_path != entry.source_path:
                raise ValueError(
                    f"Duplicate rollout ownership for thread {entry.run_id}: "
                    f"{existing.source_path} and {entry.source_path}"
                )
            entries[entry.run_id] = entry
    return entries


def _read_junie_catalog_entry(path: Path, source_store: str) -> _AgentCatalogEntry | None:
    """Read one Junie event stream's session identity, date, and prompt title."""

    if not _is_native_junie_session(path):
        return None
    started_at: datetime | None = None
    task_title = ""
    workspace = ""
    events_path = _junie_events_path(path).resolve()
    try:
        with events_path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                timestamp = _parse_iso_datetime(record.get("timestampMs"))
                if timestamp is not None and started_at is None:
                    started_at = timestamp
                workspace = workspace or str(
                    record.get("cwd")
                    or record.get("workspace")
                    or record.get("projectPath")
                    or ""
                )
                if record.get("kind") == "UserPromptEvent":
                    raw_prompt = record.get("presentablePrompt") or record.get("prompt")
                    if isinstance(raw_prompt, str):
                        task_title = _catalog_task_title(raw_prompt)
                    if task_title:
                        break
    except OSError:
        return None
    return _AgentCatalogEntry(
        run_id=events_path.parent.name,
        parent_thread_id="",
        started_at=started_at or _mtime(events_path),
        task_title=task_title,
        workspace=workspace,
        source_path=events_path,
        source_store=source_store,
    )


def _index_junie_catalog(
    roots: list[Path],
    *,
    from_date: str = "",
    to_date: str = "",
) -> dict[str, _AgentCatalogEntry]:
    """Index reportable Junie session event streams under caller-bounded roots."""

    entries: dict[str, _AgentCatalogEntry] = {}
    for root in roots:
        candidates = (
            [root]
            if root.is_file()
            else sorted(root.rglob("events.jsonl"))
            if root.exists()
            else []
        )
        for path in candidates:
            if not _catalog_path_matches_dates(path, from_date, to_date):
                continue
            entry = _read_junie_catalog_entry(path, root.name or str(root))
            if entry is None:
                continue
            existing = entries.get(entry.run_id)
            if existing is not None and existing.source_path != entry.source_path:
                raise ValueError(
                    f"Duplicate Junie session ownership for {entry.run_id}: "
                    f"{existing.source_path} and {entry.source_path}"
                )
            entries[entry.run_id] = entry
    return entries


def _parse_catalog_date(raw: str, *, end_of_day: bool) -> datetime:
    """Parse an inclusive UTC catalog date or hour boundary."""

    parsed = None
    increment = timedelta()
    for pattern, upper_increment in (
        ("%Y-%m-%d", timedelta(days=1)),
        ("%Y-%m-%dT%H", timedelta(hours=1)),
        ("%Y-%m-%dT%H:%M", timedelta(hours=1)),
    ):
        try:
            candidate = datetime.strptime(raw, pattern).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if pattern.endswith("%M") and candidate.minute != 0:
            continue
        parsed = candidate
        increment = upper_increment
        break
    if parsed is None:
        raise ValueError(
            f"Invalid catalog date/hour {raw!r}; expected YYYY-MM-DD or YYYY-MM-DDTHH"
        )
    return parsed + increment if end_of_day else parsed


def _select_catalog_entries(
    entries: list[_AgentCatalogEntry],
    *,
    from_date: str = "",
    to_date: str = "",
    title_contains: str = "",
    workspace_contains: str = "",
) -> list[_AgentCatalogEntry]:
    """Apply inclusive UTC date and case-insensitive text filters."""

    lower_bound = _parse_catalog_date(from_date, end_of_day=False) if from_date else None
    upper_bound = _parse_catalog_date(to_date, end_of_day=True) if to_date else None
    if lower_bound and upper_bound and lower_bound >= upper_bound:
        raise ValueError("--from-date must not be after --to-date")
    title_query = title_contains.casefold()
    workspace_query = workspace_contains.casefold()
    selected = []
    for entry in entries:
        started_at = entry.started_at.astimezone(timezone.utc)
        if lower_bound is not None and started_at < lower_bound:
            continue
        if upper_bound is not None and started_at >= upper_bound:
            continue
        if title_query and title_query not in entry.task_title.casefold():
            continue
        workspace_haystack = f"{entry.workspace}\n{entry.source_path}".casefold()
        if workspace_query and workspace_query not in workspace_haystack:
            continue
        selected.append(entry)
    return sorted(selected, key=lambda item: (item.started_at, item.run_id), reverse=True)


def _codex_hierarchy_paths(
    root_thread_id: str,
    entries: dict[str, _AgentCatalogEntry],
) -> list[Path]:
    """Return one selected Codex root and all recursively indexed descendants."""

    children: dict[str, list[str]] = {}
    for entry in entries.values():
        if entry.parent_thread_id:
            children.setdefault(entry.parent_thread_id, []).append(entry.run_id)
    queue = [root_thread_id]
    selected: list[Path] = []
    seen: set[str] = set()
    while queue:
        thread_id = queue.pop(0)
        if thread_id in seen:
            raise ValueError(f"Cycle detected in Codex thread hierarchy at {thread_id}")
        seen.add(thread_id)
        entry = entries.get(thread_id)
        if entry is None:
            continue
        selected.append(entry.source_path)
        queue.extend(sorted(children.get(thread_id, [])))
    return selected


def _catalog_report_filename(run_id: str) -> str:
    """Return a stable HTML filename for one locally recorded run identifier."""

    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", run_id).strip("-.") or "run"
    return f"{safe_id}.html"


def _render_agent_catalog_html(
    runtime: str,
    entries: list[_AgentCatalogEntry],
    report_hrefs: dict[str, str],
    *,
    from_date: str = "",
    to_date: str = "",
) -> str:
    """Render a local HTML index of reportable logs and generated child reports."""

    rows = []
    for entry in entries:
        report = "available"
        if entry.run_id in report_hrefs:
            report = (
                f'<a href="{_escape_html(report_hrefs[entry.run_id])}">open report</a>'
            )
        rows.append(
            "<tr>"
            f"<td>{_escape_html(entry.started_at.astimezone(timezone.utc).isoformat())}</td>"
            f"<td>{_escape_html(entry.task_title or '(title unavailable)')}</td>"
            f"<td><code>{_escape_html(entry.run_id)}</code></td>"
            f"<td>{_escape_html(entry.workspace or '—')}</td>"
            f"<td>{_escape_html(entry.source_store)}</td>"
            f"<td><code>{_escape_html(str(entry.source_path))}</code></td>"
            f"<td>{report}</td>"
            "</tr>"
        )
    range_label = "all dates"
    if from_date or to_date:
        range_label = f"{from_date or 'earliest'} through {to_date or 'latest'} UTC"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Available {runtime} Agent Reports</title>
<style>
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:2em; color:#263238; background:#fafbfc; }}
h1 {{ margin-bottom:.25em; }}
p {{ color:#607d8b; }}
.table-scroll {{ overflow:auto; border:1px solid #e1e6ea; border-radius:6px; }}
table {{ border-collapse:collapse; width:100%; background:#fff; }}
th,td {{ padding:8px; border-bottom:1px solid #e1e6ea; text-align:left; vertical-align:top; }}
th {{ color:#546e7a; font-size:.82em; background:#f5f7f8; }}
td {{ font-size:.86em; }}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; overflow-wrap:anywhere; }}
a {{ color:#2563a6; font-weight:600; text-decoration:none; }}
</style></head><body>
<h1>Available {runtime} Agent Reports</h1>
<p>{len(entries):,} root run(s) selected for {_escape_html(range_label)}. Dates use the first recorded event and are inclusive.</p>
<div class="table-scroll"><table><thead><tr><th>Started (UTC)</th><th>Task</th><th>Run ID</th><th>Workspace</th><th>Store</th><th>Log</th><th>Report</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
</body></html>"""


def main(argv: list[str] | None = None) -> int:
    """Run the report CLI with optional explicit `argv`.

    Writes caller-selected report artifacts and returns zero on success or one
    for input, discovery, parsing, and sealing failures. Argument-contract
    violations are handled by `argparse`.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Generate timeline reports for methodology-runner, prompt-runner, "
            "comparison manifests, native Codex hierarchies, or Junie sessions."
        )
    )
    parser.add_argument("path", nargs="?", help="Path to analyze (workspace, run, rollout, or manifest).")
    parser.add_argument("--config", help="YAML configuration file. CLI values override it.")
    parser.add_argument(
        "--token-summary", action="store_true",
        help="Summarize Codex logs active in the range and print a rollup total.",
    )
    parser.add_argument(
        "--scan-directory", action="append", default=[],
        help=(
            "Directory to scan recursively for token summary logs; repeat as needed. "
            "Defaults to the active and archived Codex stores."
        ),
    )
    parser.add_argument(
        "--from", dest="from_time",
        help="Inclusive local From value: YYYY-MM-DD with optional HH:mm.",
    )
    parser.add_argument(
        "--to", dest="to_time",
        help="Exclusive local To value: YYYY-MM-DD with optional HH:mm.",
    )
    parser.add_argument(
        "--csv", nargs="?", const="-",
        help="Write row-only token summary CSV to PATH, or stdout when PATH is omitted.",
    )
    parser.add_argument(
        "--output", "-o", "--html", default=None,
        help="Output HTML path; --html is an alias.",
    )
    parser.add_argument(
        "--threads", action="store_true",
        help=(
            "Show one row per thread in text and CSV output; for HTML, add "
            "per-thread token ledgers and escaped raw-source pages."
        ),
    )
    parser.add_argument("--codex-thread", help="Root Codex Desktop thread ID to report.")
    parser.add_argument(
        "--progress",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of bounded worker threads to use for independent report work (1-64).",
    )
    catalog_group = parser.add_mutually_exclusive_group()
    catalog_group.add_argument(
        "--codex-catalog",
        action="store_true",
        help="Generate an HTML catalog of reportable root Codex rollouts.",
    )
    catalog_group.add_argument(
        "--junie-catalog",
        action="store_true",
        help="Generate an HTML catalog of reportable Junie sessions.",
    )
    parser.add_argument(
        "--catalog-root",
        action="append",
        default=[],
        help="Catalog search root; repeat to scan multiple active or archived stores.",
    )
    parser.add_argument(
        "--from-date",
        help="Inclusive catalog start date or hour in UTC (YYYY-MM-DD or YYYY-MM-DDTHH).",
    )
    parser.add_argument(
        "--to-date",
        help="Inclusive catalog end date or hour in UTC (YYYY-MM-DD or YYYY-MM-DDTHH).",
    )
    parser.add_argument(
        "--title-contains",
        default="",
        help="Keep catalog entries whose bounded task title contains this text.",
    )
    parser.add_argument(
        "--workspace-contains",
        default="",
        help="Keep catalog entries whose workspace or source path contains this text.",
    )
    parser.add_argument(
        "--generate-batch",
        action="store_true",
        help="Generate every selected catalog report and link it back to the catalog.",
    )
    parser.add_argument(
        "--title",
        help=(
            "Explicit task title. Takes precedence over recorded metadata and the "
            "first genuine user request."
        ),
    )
    parser.add_argument(
        "--thread-title",
        action="append",
        default=[],
        metavar="THREAD_ID=TITLE",
        help=(
            "Override one task display name used by timeline and sequence views; "
            "repeat for linked or archived tasks whose Codex sidebar title is "
            "unavailable locally."
        ),
    )
    parser.add_argument(
        "--sessions-root",
        action="append",
        default=[],
        help=(
            "Bounded Codex sessions root; repeat to combine active and archived "
            "stores. Defaults to ~/.codex/sessions."
        ),
    )
    parser.add_argument(
        "--include-children",
        action="store_true",
        help="Include native spawned descendants of each selected task.",
    )
    parser.add_argument(
        "--include-delegations",
        action="store_true",
        help=(
            "Follow outbound <codex_delegation> thread links and include linked "
            "non-child tasks."
        ),
    )
    state_group = parser.add_mutually_exclusive_group()
    state_group.add_argument("--live", action="store_true", help="Render an append-safe live snapshot.")
    state_group.add_argument("--seal", action="store_true", help="Seal stable terminal telemetry with digests.")
    parser.add_argument(
        "--seal-aborted",
        action="store_true",
        help="Allow explicitly aborted threads when sealing.",
    )
    parser.add_argument("--json-output", help="Normalized JSON output path.")
    parser.add_argument("--turn-csv-output", help="Turn-oriented CSV output path.")
    parser.add_argument("--work-unit-csv-output", help="Work-unit cost CSV output path.")
    parser.add_argument("--markdown-output", help="Compact Markdown output path.")
    parser.add_argument(
        "--formatter-config",
        help=(
            "JSON tool-argument formatter config. Defaults to "
            "tools/report/tool-formatters.json."
        ),
    )
    args = parser.parse_args(argv)

    token_config: dict[str, object] = {}
    config_path: Path | None = None
    if args.config:
        config_path = Path(args.config).expanduser().resolve()
        try:
            token_config = _load_token_summary_config(config_path)
        except ValueError as exc:
            parser.error(str(exc))
    config_mode = token_config.get("mode")
    if config_mode not in (None, "token-summary"):
        parser.error("config mode must be token-summary")
    token_summary_mode = args.token_summary or config_mode == "token-summary"
    if token_summary_mode:
        if args.path or args.codex_thread or args.codex_catalog or args.junie_catalog:
            parser.error("token summary cannot be combined with report or catalog selection")
        configured_directories = token_config.get("directories", [])
        if not isinstance(configured_directories, list) or not all(
            isinstance(value, str) and value.strip() for value in configured_directories
        ):
            parser.error("config directories must be a list of non-empty paths")
        configured_threads = token_config.get("threads", False)
        if not isinstance(configured_threads, bool):
            parser.error("config threads must be true or false")
        include_threads = args.threads or configured_threads
        base = config_path.parent if config_path is not None else Path.cwd()
        using_default_directories = not args.scan_directory and not configured_directories
        raw_directories = args.scan_directory or configured_directories or [
            Path.home() / ".codex" / "sessions",
            Path.home() / ".codex" / "archived_sessions",
        ]
        directories = [
            (
                Path(value).expanduser()
                if Path(value).expanduser().is_absolute()
                else base / value
            ).resolve()
            for value in raw_directories
        ]
        if using_default_directories:
            directories = [directory for directory in directories if directory.is_dir()]
        try:
            default_from, default_to = _token_summary_default_range()
            from_time = _token_summary_datetime(
                args.from_time
                if args.from_time is not None
                else token_config.get("from"),
                "From",
            )
            to_time = _token_summary_datetime(
                args.to_time
                if args.to_time is not None
                else token_config.get("to"),
                "To",
            )
            from_time = from_time or default_from
            to_time = to_time or default_to
            if from_time >= to_time:
                raise ValueError("From date and time must be before To date and time")
            rows = _token_summary_rows(
                directories,
                from_time=from_time,
                to_time=to_time,
                emit_progress=True,
            )
            csv_destination = (
                args.csv if args.csv is not None else token_config.get("csv")
            )
            if csv_destination is not None and not isinstance(csv_destination, str):
                raise ValueError("config csv must be a path string")
            html_destination = (
                args.output if args.output is not None else token_config.get("html")
            )
            if html_destination is not None and (
                not isinstance(html_destination, str) or not html_destination.strip()
            ):
                raise ValueError("config html must be a non-empty path string")
            if isinstance(csv_destination, str):
                if csv_destination != "-":
                    csv_path = Path(csv_destination).expanduser()
                    csv_destination = str(
                        (csv_path if csv_path.is_absolute() else base / csv_path).resolve()
                    )
                    Path(csv_destination).parent.mkdir(parents=True, exist_ok=True)
                _write_token_summary_csv(
                    rows, csv_destination, details=include_threads
                )
            if isinstance(html_destination, str):
                html_path = Path(html_destination).expanduser()
                html_path = (
                    html_path if html_path.is_absolute() else base / html_path
                ).resolve()
                html_path.parent.mkdir(parents=True, exist_ok=True)
                _write_token_summary_html(
                    rows,
                    html_path,
                    from_time=from_time,
                    to_time=to_time,
                    directories=directories,
                    threads=include_threads,
                    emit_progress=True,
                )
            if csv_destination is None and html_destination is None:
                _print_token_summary(rows, details=include_threads)
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if args.threads:
        parser.error("--threads requires --token-summary")

    catalog_mode = args.codex_catalog or args.junie_catalog
    if not args.path and not args.codex_thread and not catalog_mode:
        parser.error("provide a path, --codex-thread, --codex-catalog, or --junie-catalog")
    if args.path and args.codex_thread:
        parser.error("path and --codex-thread are mutually exclusive")
    if catalog_mode and (args.path or args.codex_thread):
        parser.error("catalog modes cannot be combined with a path or --codex-thread")
    if args.generate_batch and not catalog_mode:
        parser.error("--generate-batch requires --codex-catalog or --junie-catalog")
    if args.include_delegations and catalog_mode:
        parser.error("--include-delegations requires a single Codex report")
    if not catalog_mode and any(
        (
            args.catalog_root,
            args.from_date,
            args.to_date,
            args.title_contains,
            args.workspace_contains,
        )
    ):
        parser.error("catalog filters require --codex-catalog or --junie-catalog")
    if args.seal_aborted and not args.seal:
        parser.error("--seal-aborted requires --seal")

    formatter_config = None
    if args.formatter_config:
        try:
            formatter_config = _load_tool_formatter_config(args.formatter_config)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if catalog_mode:
        if args.live or args.seal or args.seal_aborted:
            parser.error("catalog modes do not support live or sealing flags")
        if any(
            (
                args.json_output,
                args.turn_csv_output,
                args.work_unit_csv_output,
                args.markdown_output,
                args.title,
                args.thread_title,
                args.sessions_root,
            )
        ):
            parser.error(
                "catalog modes use --catalog-root and do not support single-report output flags"
            )
        if args.catalog_root:
            catalog_roots = [Path(value).expanduser().resolve() for value in args.catalog_root]
        elif args.codex_catalog:
            catalog_roots = [
                Path.home() / ".codex" / "sessions",
                Path.home() / ".codex" / "archived_sessions",
            ]
        else:
            catalog_roots = [Path.home() / ".junie" / "sessions"]
        try:
            if args.codex_catalog:
                catalog_index = _index_codex_catalog(
                    catalog_roots,
                    from_date=args.from_date or "",
                    to_date=args.to_date or "",
                    include_all_identities=args.generate_batch,
                )
                local_titles = _local_codex_thread_titles(set(catalog_index))
                for thread_id, task_title in local_titles.items():
                    catalog_index[thread_id] = replace(
                        catalog_index[thread_id],
                        task_title=task_title,
                    )
                catalog_candidates = [
                    entry
                    for entry in catalog_index.values()
                    if not entry.parent_thread_id
                ]
                runtime = "Codex"
            else:
                catalog_index = _index_junie_catalog(
                    catalog_roots,
                    from_date=args.from_date or "",
                    to_date=args.to_date or "",
                )
                catalog_candidates = list(catalog_index.values())
                runtime = "Junie"
            selected = _select_catalog_entries(
                catalog_candidates,
                from_date=args.from_date or "",
                to_date=args.to_date or "",
                title_contains=args.title_contains,
                workspace_contains=args.workspace_contains,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        output = (
            Path(args.output).expanduser().resolve()
            if args.output
            else Path.cwd() / f"{runtime.lower()}-agent-report-catalog.html"
        )
        report_hrefs: dict[str, str] = {}
        if args.generate_batch:
            reports_dir = output.parent / "reports"
            for entry in selected:
                report_filename = _catalog_report_filename(entry.run_id)
                report_output = reports_dir / report_filename
                try:
                    if args.codex_catalog:
                        run = build_codex_rollout_run(
                            entry.run_id,
                            entry.source_path.parent,
                            include_children=args.include_children,
                            candidate_paths=_codex_hierarchy_paths(
                                entry.run_id, catalog_index
                            ),
                        )
                    else:
                        run = parse_junie_session(entry.source_path)
                        run.run_label = _report_title(entry.task_title)
                except ValueError as exc:
                    print(f"Cannot generate {entry.run_id}: {exc}", file=sys.stderr)
                    return 1
                _write_codex_outputs(
                    run,
                    report_output,
                    formatter_config=formatter_config,
                    nav_links=[("All reports", f"../{output.name}")],
                )
                report_hrefs[entry.run_id] = (
                    Path("reports") / report_filename
                ).as_posix()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            _with_copyright_footer(
                _render_agent_catalog_html(
                    runtime,
                    selected,
                    report_hrefs,
                    from_date=args.from_date or "",
                    to_date=args.to_date or "",
                )
            ),
            encoding="utf-8",
        )
        print(f"{runtime} report catalog written to {output} ({len(selected)} run(s))")
        if args.generate_batch:
            print(f"Generated {len(report_hrefs)} linked report(s) under {output.parent / 'reports'}")
        return 0

    if not 1 <= args.workers <= 64:
        parser.error("--workers must be between 1 and 64")

    input_path = Path(args.path).resolve() if args.path else None
    if input_path is not None and not input_path.exists():
        print(f"Path not found: {input_path}", file=sys.stderr)
        return 1

    native_rollout_path = input_path if input_path and _is_native_codex_rollout(input_path) else None
    thread_titles: dict[str, str] = {}
    for value in args.thread_title:
        thread_id, separator, display_title = value.partition("=")
        if not separator or not thread_id.strip() or not display_title.strip():
            parser.error("--thread-title must use THREAD_ID=TITLE with both values present")
        thread_titles[thread_id.strip()] = display_title.strip()
    if args.include_delegations and not (args.codex_thread or native_rollout_path):
        parser.error("--include-delegations requires --codex-thread or a Codex rollout path")
    if args.include_children and not (
        args.codex_thread
        or native_rollout_path
        or (args.codex_catalog and args.generate_batch)
    ):
        parser.error(
            "--include-children requires a Codex report or Codex batch generation"
        )
    if thread_titles and not (args.codex_thread or native_rollout_path):
        parser.error("--thread-title requires --codex-thread or a Codex rollout path")
    if args.codex_thread or native_rollout_path is not None:
        if args.progress:
            _emit_report_progress(0, "Starting report generation", "Preparing the renderer process.")
        if args.codex_thread:
            root_thread_id = args.codex_thread
            if args.sessions_root:
                session_roots = [
                    Path(value).expanduser().resolve()
                    for value in args.sessions_root
                ]
            elif args.include_delegations:
                session_roots = [
                    Path.home() / ".codex" / "sessions",
                    Path.home() / ".codex" / "archived_sessions",
                ]
            else:
                session_roots = [Path.home() / ".codex" / "sessions"]
        else:
            identity = _rollout_identity(native_rollout_path)
            if identity is None:
                print(f"No Codex thread identity found in {native_rollout_path}", file=sys.stderr)
                return 1
            root_thread_id = identity[0]
            if args.sessions_root:
                session_roots = [
                    Path(value).expanduser().resolve()
                    for value in args.sessions_root
                ]
            else:
                primary_root = _sessions_root_for_rollout(native_rollout_path)
                session_roots = [primary_root]
                if args.include_delegations and primary_root.name in {
                    "sessions",
                    "archived_sessions",
                }:
                    sibling_name = (
                        "archived_sessions"
                        if primary_root.name == "sessions"
                        else "sessions"
                    )
                    session_roots.append(primary_root.parent / sibling_name)
        output = Path(args.output).resolve() if args.output else (Path.cwd() / f"{root_thread_id}-timeline.html")
        if args.progress:
            _emit_report_progress(10, "Discovering related threads", "Finding the selected thread and requested related logs.")
        try:
            run = build_codex_rollout_run(
                root_thread_id,
                session_roots,
                seal=args.seal,
                allow_aborted=args.seal_aborted,
                include_children=args.include_children,
                include_delegations=args.include_delegations,
                title=args.title or "",
                thread_titles=thread_titles,
                discovery_index_path=_default_codex_discovery_index_path(),
                progress=_emit_report_progress if args.progress else None,
                worker_progress=_emit_report_progress if args.progress else None,
                item_progress=_emit_report_item_progress if args.progress else None,
                workers=args.workers,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if args.progress:
            _emit_report_progress(75, "Analyzing recorded events", "Aggregating timing, tokens, models, context, and cost.")
        json_output = Path(args.json_output).resolve() if args.json_output else None
        turn_csv_output = Path(args.turn_csv_output).resolve() if args.turn_csv_output else None
        work_unit_csv_output = Path(args.work_unit_csv_output).resolve() if args.work_unit_csv_output else None
        markdown_output = Path(args.markdown_output).resolve() if args.markdown_output else None
        if args.seal:
            json_output = json_output or output.with_suffix(".json")
            turn_csv_output = turn_csv_output or output.with_suffix(".turns.csv")
            work_unit_csv_output = work_unit_csv_output or output.with_suffix(".work-units.csv")
            markdown_output = markdown_output or output.with_suffix(".md")
        _write_codex_outputs(
            run,
            output,
            formatter_config=formatter_config,
            json_output=json_output,
            turn_csv_output=turn_csv_output,
            work_unit_csv_output=work_unit_csv_output,
            markdown_output=markdown_output,
            emit_progress=args.progress,
            workers=args.workers,
        )
        if args.progress:
            _emit_report_progress(100, "Report complete", "The report is ready to open.")
        print(f"Codex rollout report written to {output}")
        sequence_output = _child_output_path(output, "sequence")
        if sequence_output.exists():
            print(f"Codex sequence report written to {sequence_output}")
        return 0

    assert input_path is not None
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

    if document.codex_run is not None:
        run = document.codex_run
        if args.seal and run.runtime.lower() != "codex":
            print("Sealing is not supported for native Junie sessions", file=sys.stderr)
            return 1
        _write_codex_outputs(
            run,
            output,
            formatter_config=formatter_config,
            json_output=Path(args.json_output).resolve() if args.json_output else None,
            turn_csv_output=(
                Path(args.turn_csv_output).resolve() if args.turn_csv_output else None
            ),
            work_unit_csv_output=(
                Path(args.work_unit_csv_output).resolve()
                if args.work_unit_csv_output
                else None
            ),
            markdown_output=(
                Path(args.markdown_output).resolve() if args.markdown_output else None
            ),
        )
        print(f"{run.runtime} execution report written to {output}")
        return 0

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

            output.write_text(
                _with_copyright_footer(render_html(document, formatter_config)),
                encoding="utf-8",
            )
            child_output.write_text(
                _with_copyright_footer(
                    render_html(child_document, formatter_config)
                ),
                encoding="utf-8",
            )
            print(f"Timeline written to {output}")
            print(f"Nested timeline written to {child_output}")
            return 0

    html = render_html(document, formatter_config)
    output.write_text(_with_copyright_footer(html), encoding="utf-8")
    print(f"Timeline written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
