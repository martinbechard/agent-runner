#!/usr/bin/env python3
# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Adapted from the verified token-ledger implementation.
# Responsibility: Render audit-grade token and cost ledgers from Codex rollouts.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

"""Render a raw Codex rollout as a standalone token and cost ledger."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence


NUMBER = re.compile(r"^\$?[+-]?(?:\d[\d,]*)(?:\.\d+)?$")
_CHECKOUT_PRICING_FILE = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "reference"
    / "openai-model-pricing.json"
)
_BUNDLED_PRICING_FILE = Path(__file__).resolve().with_name(
    "openai-model-pricing.json"
)
AGENT_REPORT_PRICING_FILE = (
    _CHECKOUT_PRICING_FILE
    if _CHECKOUT_PRICING_FILE.is_file()
    else _BUNDLED_PRICING_FILE
)
SKILL_PATH = re.compile(
    r"skills/(?P<name>[A-Za-z0-9][A-Za-z0-9_.:-]*)/SKILL\.md\b"
)
SKILL_ACTION = re.compile(
    r"\b(?:use|using|load|loading|loaded|read|reading)\b"
    r"(?P<phrase>[^.!?\n]{0,180}?)\bskills?\b",
    re.IGNORECASE,
)
SKILLS_REPORT_FILE = "skills_report.csv"
COPYRIGHT_NOTICE = "© 2026 Martin.Bechard@DevConsult.ca · MIT License"


def copyright_footer_html() -> str:
    """Return the visible footer shared by standalone ledger pages."""

    return (
        '<footer class="agent-report-copyright" '
        'style="margin:2rem 1rem .75rem;padding-top:.75rem;border-top:1px solid '
        'currentColor;opacity:.62;text-align:center;font:10px/1.4 '
        'ui-monospace,SFMono-Regular,Menlo,monospace">'
        f"{COPYRIGHT_NOTICE}</footer>"
    )

LEDGER_HEADERS = [
    "row",
    "time_utc",
    "event",
    "model",
    "evidence_summary",
    "skills",
    "included_in_snapshot",
    "evidence_type",
    "previous_call_total_tokens",
    "cache_read_tokens",
    "previous_cumulative_cache_read_tokens",
    "cumulative_cache_read_tokens",
    "uncached_old_history_tokens_inferred",
    "input_tokens",
    "uncached_new_tokens_inferred",
    "total_uncached_input_tokens",
    "reasoning_tokens",
    "visible_output_tokens_derived",
    "output_tokens",
    "total_tokens",
    "previous_cumulative_total_tokens",
    "cumulative_total_tokens",
    "system_total_tokens",
    "cache_write_tokens",
    "previous_cumulative_cache_write_tokens",
    "cumulative_cache_write_tokens",
    "total_cost_usd",
    "previous_cumulative_cost_usd",
    "cumulative_cost_usd",
    "model_input_equivalent_tokens",
    "previous_cumulative_model_input_equivalent_tokens",
    "cumulative_model_input_equivalent_tokens",
    "sol_input_equivalent_tokens",
    "previous_cumulative_sol_input_equivalent_tokens",
    "cumulative_sol_input_equivalent_tokens",
    "previous_cumulative_cache_activity_tokens",
    "cumulative_cache_activity_tokens",
    "notes",
]

DISPLAY_LABELS = {
    "row": "Row",
    "time_utc": "UTC time",
    "event": "Event",
    "model": "Model",
    "evidence_summary": "Event evidence",
    "skills": "Skills",
    "included_in_snapshot": "Included in snapshot",
    "evidence_type": "Evidence type",
    "previous_call_total_tokens": "Previous call total (previous_call_total_tokens)",
    "cache_read_tokens": "Cache read (input_tokens_details.cached_tokens)",
    "input_tokens": "Request input (input_tokens)",
    "uncached_old_history_tokens_inferred": "Uncached old history (uncached_old_history_tokens_inferred)",
    "uncached_new_tokens_inferred": "Uncached new input (uncached_new_tokens_inferred)",
    "total_uncached_input_tokens": "Total uncached input (total_uncached_input_tokens)",
    "reasoning_tokens": "Reasoning (output_tokens_details.reasoning_tokens)",
    "output_tokens": "Total output (output_tokens)",
    "visible_output_tokens_derived": "Visible output (visible_output_tokens_derived)",
    "total_tokens": "Total tokens this call (total_tokens)",
    "system_total_tokens": "System total tokens",
    "cache_write_tokens": "Cache write (input_tokens_details.cache_write_tokens)",
    "previous_cumulative_total_tokens": "Previous cumulative total tokens (previous_cumulative_total_tokens)",
    "cumulative_total_tokens": "Cumulative total tokens (cumulative_total_tokens)",
    "previous_cumulative_cache_read_tokens": "Previous cumulative cache reads (previous_cumulative_cache_read_tokens)",
    "cumulative_cache_read_tokens": "Cumulative cache reads (cumulative_cache_read_tokens)",
    "previous_cumulative_cache_write_tokens": "Previous cumulative cache writes (previous_cumulative_cache_write_tokens)",
    "cumulative_cache_write_tokens": "Cumulative cache writes (cumulative_cache_write_tokens)",
    "total_cost_usd": "Total cost (USD)",
    "previous_cumulative_cost_usd": "Previous cumulative cost (USD)",
    "cumulative_cost_usd": "Cumulative cost (USD)",
    "model_input_equivalent_tokens": "Model input-equivalent tokens",
    "previous_cumulative_model_input_equivalent_tokens": "Previous cumulative model input-equivalent tokens",
    "cumulative_model_input_equivalent_tokens": "Cumulative model input-equivalent tokens",
    "sol_input_equivalent_tokens": "Sol input-equivalent tokens",
    "previous_cumulative_sol_input_equivalent_tokens": "Previous cumulative Sol input-equivalent tokens",
    "cumulative_sol_input_equivalent_tokens": "Cumulative Sol input-equivalent tokens",
    "previous_cumulative_cache_activity_tokens": "Previous cumulative cache activity (previous_cumulative_cache_activity_tokens)",
    "cumulative_cache_activity_tokens": "Cumulative cache activity (cumulative_cache_activity_tokens)",
    "notes": "Notes",
}

COLUMN_DEFINITIONS = {
    "row": "Chronological row number. Row 0 is an explicitly unknown event before the selected trace.",
    "time_utc": "Event timestamp in UTC, or a bounded description when the exact time is unknown.",
    "event": "Short name of the runtime event.",
    "model": "Raw turn_context.model applied to this call. Cost rates are selected by this value.",
    "evidence_summary": "What the source log directly says about the event. Character counts are raw evidence, not token counts and not inputs to token arithmetic.",
    "skills": "Skill evidence extracted from the rollout by regular expressions. Labels mean: requested = user explicitly mentions a skill name; announced = assistant explicitly states intended skill use; load call = custom_tool_call loads or reads SKILL.md content; load result = tool output confirming that load. When available, skill names include estimated token size from skills_report.csv.",
    "included_in_snapshot": "The token snapshot that accounts for a model-produced event or whose request consumes an input event. Tool results skip the immediately following delayed usage record and map to the next model request. 'Not separate' means duplicate telemetry.",
    "evidence_type": "Observed, derived by arithmetic, inferred under unchanged-context continuity, or unknown.",
    "previous_call_total_tokens": "Raw last_token_usage.total_tokens from the preceding distinct call. It is a source operand for the uncached-history calculations.",
    "cache_read_tokens": "Raw last_token_usage.cached_input_tokens: request input tokens read from the prompt cache.",
    "input_tokens": "Raw last_token_usage.input_tokens. This source value is the complete current request input, including cached and uncached tokens; it is not calculated by this report.",
    "uncached_old_history_tokens_inferred": "Derived as Previous call total minus Cache read when consecutive snapshots permit that comparison.",
    "uncached_new_tokens_inferred": "Derived as Request input minus Previous call total. On the first snapshot, it is Request input minus Cache read because no preceding call is present.",
    "total_uncached_input_tokens": "Derived as Uncached old history plus Uncached new input when both are available. On the first snapshot, it equals Uncached new input.",
    "reasoning_tokens": "Raw last_token_usage.reasoning_output_tokens: the portion of output used for reasoning.",
    "output_tokens": "Raw last_token_usage.output_tokens: all output tokens, including reasoning output tokens.",
    "visible_output_tokens_derived": "visible_output_tokens_derived equals output_tokens subtract output_tokens_details.reasoning_tokens.",
    "total_tokens": "Raw last_token_usage.total_tokens: last_token_usage.input_tokens plus last_token_usage.output_tokens.",
    "system_total_tokens": "System total_token_usage.total_tokens, with the inherited parent baseline subtracted for a forked rollout. Compare it with Cumulative total tokens, which independently sums this thread's calls.",
    "cache_write_tokens": "Raw last_token_usage.cache_write_input_tokens: input tokens written to the prompt cache by this call.",
    "previous_cumulative_total_tokens": "The preceding calculated Cumulative total tokens value; retained only as a hidden calculation operand.",
    "cumulative_total_tokens": "Running sum of Total tokens this call across distinct calls; repeated token_count telemetry with an unchanged system counter is not added again.",
    "previous_cumulative_cache_read_tokens": "The preceding raw total_token_usage.cached_input_tokens value; retained only as a hidden calculation operand.",
    "cumulative_cache_read_tokens": "System total_token_usage.cached_input_tokens across this thread, with the inherited parent baseline subtracted for a forked rollout.",
    "previous_cumulative_cache_write_tokens": "The preceding raw total_token_usage.cache_write_input_tokens value; retained only as a hidden calculation operand.",
    "cumulative_cache_write_tokens": "System total_token_usage.cache_write_input_tokens across this thread, with the inherited parent baseline subtracted for a forked rollout.",
    "total_cost_usd": "Estimated input cost plus output cost for this distinct call. Codex does not charge for cache writes.",
    "previous_cumulative_cost_usd": "The preceding calculated cumulative cost; retained only as a hidden calculation operand.",
    "cumulative_cost_usd": "Running API-equivalent estimated cost across distinct calls in this thread. It is not an actual subscription charge.",
    "model_input_equivalent_tokens": "Total estimated call cost divided by the active model's uncached-input price per token. This converts cached input and output into same-model uncached-input-token cost units.",
    "previous_cumulative_model_input_equivalent_tokens": "The preceding cumulative model input-equivalent value; retained only as a hidden calculation operand.",
    "cumulative_model_input_equivalent_tokens": "Running sum of Model input-equivalent tokens across distinct calls.",
    "sol_input_equivalent_tokens": "Total estimated call cost divided by GPT-5.6 Sol's uncached-input price per token from the same Agent Report cost card. This provides one cross-model comparison unit.",
    "previous_cumulative_sol_input_equivalent_tokens": "The preceding cumulative Sol input-equivalent value; retained only as a hidden calculation operand.",
    "cumulative_sol_input_equivalent_tokens": "Running sum of Sol input-equivalent tokens across distinct calls.",
    "previous_cumulative_cache_activity_tokens": "Cache reads plus cache writes before this snapshot.",
    "cumulative_cache_activity_tokens": "Cache reads plus cache writes across measured calls. This is activity, not live cache storage size.",
    "notes": "Caveats that apply to the row, especially unknown cache provenance or continuity assumptions.",
}

CALCULATION_SPECS = {
    "uncached_old_history_tokens_inferred": (
        "previous_call_total_tokens",
        "subtract",
        "cache_read_tokens",
    ),
    "uncached_new_tokens_inferred": (
        "input_tokens",
        "subtract",
        "previous_call_total_tokens",
    ),
    "total_uncached_input_tokens": ("uncached_old_history_tokens_inferred", "plus", "uncached_new_tokens_inferred"),
    "output_tokens": ("reasoning_tokens", "plus", "visible_output_tokens_derived"),
    "total_tokens": ("input_tokens", "plus", "output_tokens"),
    "cumulative_total_tokens": (
        "previous_cumulative_total_tokens",
        "plus",
        "total_tokens",
    ),
    "cumulative_cache_read_tokens": (
        "previous_cumulative_cache_read_tokens",
        "plus",
        "cache_read_tokens",
    ),
    "cumulative_cache_write_tokens": (
        "previous_cumulative_cache_write_tokens",
        "plus",
        "cache_write_tokens",
    ),
    "cumulative_cache_activity_tokens": (
        "previous_cumulative_cache_activity_tokens",
        "plus",
        "cache_read_tokens",
        "plus",
        "cache_write_tokens",
    ),
    "cumulative_cost_usd": (
        "previous_cumulative_cost_usd",
        "plus",
        "total_cost_usd",
    ),
    "cumulative_model_input_equivalent_tokens": (
        "previous_cumulative_model_input_equivalent_tokens",
        "plus",
        "model_input_equivalent_tokens",
    ),
    "cumulative_sol_input_equivalent_tokens": (
        "previous_cumulative_sol_input_equivalent_tokens",
        "plus",
        "sol_input_equivalent_tokens",
    ),
}

FIELD_RELATIONSHIP_TREE = """Token and cost fields
├── Request input [raw]
│   ├── Cache read [raw subset]
│   │   └── Cumulative cache reads = preceding cumulative + Cache read
│   └── Total uncached input = Uncached old history + Uncached new input
│       ├── Uncached old history = Previous call total − Cache read
│       │   └── Previous call total [raw from preceding call]
│       └── Uncached new input = Request input − Previous call total
├── Total output [raw]
│   ├── Reasoning [raw subset]
│   └── Visible output = Total output − Reasoning
├── Total tokens this call = Request input + Total output
│   ├── Cumulative total tokens = preceding cumulative + Total tokens this call
│   └── System total tokens [system counter; parent baseline removed for forks]
├── Cache write [raw]
│   └── Cumulative cache writes = preceding cumulative + Cache write
└── Estimated cost [Agent Report model cost card]
    ├── Cached read cost = Cache read × model cached-input rate
    ├── Input cost = Total uncached input × model input rate + Cached read cost
    ├── Output cost = Total output × model output rate
    ├── Total cost = Input cost + Output cost
    │   ├── Model input-equivalent tokens = Total cost ÷ model input rate
    │   └── Sol input-equivalent tokens = Total cost ÷ Sol input rate
    └── Cumulative cost = preceding cumulative + Total cost"""

TOKEN_SUMMARY_FUNDING_HEADERS = (
    "plan",
    "funding",
    "sub_remaining",
    "credits_available",
    "credits_remaining",
)
DISPLAY_LABELS.update(
    {
        "plan": "Plan",
        "funding": "Funding",
        "sub_remaining": "Sub remaining",
        "credits_available": "Credits available",
        "credits_remaining": "Credits remaining",
    }
)
COLUMN_DEFINITIONS.update(
    {
        "plan": "Codex plan_type telemetry attached to the token snapshot.",
        "funding": "Funding classification for this call: subscription or purchased credits.",
        "sub_remaining": "Subscription capacity remaining when this call was recorded.",
        "credits_available": "Whether Codex reported purchased credits as available.",
        "credits_remaining": "Observed purchased-credit balance attached to this call.",
    }
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path, help="Source CSV file")
    parser.add_argument("output_html", type=Path, help="Generated HTML file")
    parser.add_argument(
        "--explanation",
        type=Path,
        help="Structured-explanation Markdown rendered before the table",
    )
    parser.add_argument(
        "--title",
        default="Root Task Token Ledger",
        help="Page title displayed above the table",
    )
    parser.add_argument(
        "--rollout",
        type=Path,
        help="Rollout JSONL used to extract skill-loading evidence",
    )
    parser.add_argument(
        "--from-rollout",
        type=Path,
        help=(
            "Build the source CSV from a raw rollout JSONL before rendering; "
            "the input_csv positional argument becomes the generated CSV path"
        ),
    )
    parser.add_argument(
        "--write-enriched-csv",
        action="store_true",
        help="Write the regex-derived Skills column back to the input CSV",
    )
    return parser.parse_args(argv)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames
        if not headers:
            raise ValueError(f"CSV has no header row: {path}")
        if len(headers) != len(set(headers)):
            raise ValueError(f"CSV contains duplicate column names: {path}")

        rows = list(reader)
        for line_number, row in enumerate(rows, start=2):
            if None in row:
                raise ValueError(
                    f"CSV row {line_number} has more values than the header: {path}"
                )
    return headers, rows


def content_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(
            block.get("text", "")
            for block in value
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    return ""


def read_rollout(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"Rollout line {line_number} is not a JSON object: {path}")
        record["_source_line"] = line_number
        records.append(record)
    return records


def empty_ledger_row() -> dict[str, str]:
    return {header: "" for header in LEDGER_HEADERS}


def payload_for(record: dict[str, object]) -> dict[str, object]:
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else {}


def tool_input(payload: dict[str, object]) -> str:
    for field in ("input", "arguments"):
        value = payload.get(field)
        if isinstance(value, str):
            return value
    return ""


def describe_tool_call(name: str, arguments: str, skill_names: list[str]) -> str:
    argument_chars = len(arguments)
    actions: list[str] = []
    nested_tools = list(
        dict.fromkeys(re.findall(r"\btools\.([A-Za-z0-9_]+)\s*\(", arguments))
    )
    if "ALL_TOOLS" in arguments and "apply_patch" not in nested_tools:
        actions.append("enumerate runtime capabilities")
    if skill_names:
        actions.append(f"read skill: {'; '.join(skill_names)}")
    path_matches = re.findall(
        r"(?:^|[\s'\"])(/?(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+)",
        arguments,
    )
    if (
        path_matches
        and not skill_names
        and re.search(r"\b(?:sed|head|tail|rg|grep|jq|find)\b", arguments)
    ):
        shown = "; ".join(dict.fromkeys(path_matches[:4]))
        actions.append(f"read files: {shown}")
    if nested_tools:
        actions.append(f"nested operations: {'; '.join(nested_tools)}")
    if not actions:
        actions.append(f"raw {name or 'tool'} arguments")
    return f"{argument_chars:,} argument chars: {' | '.join(actions)}"


def event_from_record(
    record: dict[str, object],
    call_details: dict[str, tuple[str, str, list[str]]],
) -> tuple[str, str, str] | None:
    record_type = str(record.get("type", ""))
    payload = payload_for(record)
    payload_type = str(payload.get("type", ""))

    if record_type == "session_meta":
        return "Session metadata", "Root task and rollout identity", ""
    if record_type == "world_state":
        return "World-state snapshot", "Runtime state", ""
    if record_type == "turn_context":
        return "Turn boundary", "Turn context", ""

    if record_type == "event_msg":
        labels = {
            "thread_settings_applied": ("Task settings applied", "Runtime settings"),
            "task_started": ("Task started", "Task execution begins"),
            "task_complete": ("Task completed", "Task execution completed"),
            "turn_aborted": ("Turn aborted", "Runtime reports an aborted turn"),
            "context_compacted": ("Context compaction", "Runtime compacted prior context"),
            "sub_agent_activity": ("Subagent activity telemetry", "Runtime notification"),
        }
        label = labels.get(payload_type)
        if label:
            return (*label, "")
        payload_chars = len(json.dumps(payload, ensure_ascii=False))
        return (
            f"{payload_type or 'event'} telemetry",
            f"{payload_chars:,} chars: raw event_msg payload",
            "",
        )

    if record_type != "response_item":
        payload_chars = len(json.dumps(payload, ensure_ascii=False))
        return (
            record_type or "Raw log record",
            f"{payload_chars:,} chars: raw {record_type or 'unknown'} payload",
            "",
        )

    if payload_type == "message":
        role = str(payload.get("role", ""))
        text_value = content_text(payload.get("content", []))
        evidence = f"{len(text_value):,} chars: {role or 'unknown'} message content"
        labels = {
            "developer": "Developer instructions",
            "user": "User message",
            "assistant": "Assistant message",
        }
        return labels.get(role, "Message"), evidence, ""

    if payload_type == "reasoning":
        encrypted = payload.get("encrypted_content")
        summary = content_text(payload.get("summary", []))
        if isinstance(encrypted, str):
            evidence = f"{len(encrypted):,} encrypted reasoning chars; plaintext unavailable"
        elif summary:
            evidence = f"{len(summary):,} chars: reasoning summary"
        else:
            evidence = "Reasoning event; plaintext unavailable"
        return "Inference reasoning", evidence, ""

    if payload_type in {"custom_tool_call", "function_call"}:
        name = str(payload.get("name", ""))
        arguments = tool_input(payload)
        skills = skill_names_from_paths(arguments)
        event = "Exec call" if name == "exec" else f"{name or 'Tool'} call"
        skill_evidence = f"load call: {'; '.join(skills)}" if skills else ""
        return event, describe_tool_call(name, arguments, skills), skill_evidence

    if payload_type in {"custom_tool_call_output", "function_call_output"}:
        call_id = str(payload.get("call_id", ""))
        name, arguments, skills = call_details.get(call_id, ("", "", []))
        result_text = content_text(payload.get("output", ""))
        if "ALL_TOOLS" in arguments:
            description = "capability and tool-schema listing"
        elif skills:
            description = f"skill content: {'; '.join(skills)}"
        else:
            description = f"raw {name or 'tool'} result"
        event = "Exec result" if name == "exec" else f"{name or 'Tool'} result"
        skill_evidence = f"load result: {'; '.join(skills)}" if skills else ""
        return event, f"{len(result_text):,} chars: {description}", skill_evidence

    payload_chars = len(json.dumps(payload, ensure_ascii=False))
    return (
        f"{payload_type or 'response'} response item",
        f"{payload_chars:,} chars: raw response_item payload",
        "",
    )


def active_rollout_records(
    records: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], tuple[int, int, int]]:
    """Exclude replayed parent history and return its cumulative counter baseline."""
    session = next(
        (record for record in records if record.get("type") == "session_meta"),
        None,
    )
    if not session:
        return list(records), (0, 0, 0)
    metadata = payload_for(session)
    if not metadata.get("parent_thread_id"):
        return list(records), (0, 0, 0)

    child_prefix = str(metadata.get("id", "")).split("-", 1)[0]
    child_start = next(
        (
            index
            for index, record in enumerate(records)
            if record.get("type") == "event_msg"
            and payload_for(record).get("type") == "task_started"
            and str(payload_for(record).get("turn_id", "")).startswith(child_prefix)
        ),
        None,
    )
    if child_start is None:
        return list(records), (0, 0, 0)

    inherited_usage = [
        payload_for(record).get("info", {}).get("total_token_usage", {})
        for record in records[:child_start]
        if record.get("type") == "event_msg"
        and payload_for(record).get("type") == "token_count"
    ]
    last_usage = inherited_usage[-1] if inherited_usage else {}
    baseline = (
        int(last_usage.get("total_tokens", 0)),
        int(last_usage.get("cached_input_tokens", 0)),
        int(last_usage.get("cache_write_input_tokens", 0)),
    )
    return list(records[child_start:]), baseline


def format_usd(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.000001'))}"


def load_agent_report_pricing(
    pricing_path: Path = AGENT_REPORT_PRICING_FILE,
) -> tuple[str, dict[str, dict[str, Decimal]]]:
    """Load complete API token rates from Agent Report's model cost card."""
    try:
        registry = json.loads(pricing_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot load Agent Report pricing card: {pricing_path}") from error
    models = registry.get("models")
    if not isinstance(models, dict):
        raise ValueError(f"Agent Report pricing card has no models object: {pricing_path}")
    rates: dict[str, dict[str, Decimal]] = {}
    keys = ("input_per_million", "cached_input_per_million", "output_per_million")
    for model, values in models.items():
        if not isinstance(model, str) or not isinstance(values, dict):
            continue
        if not all(isinstance(values.get(key), (int, float)) for key in keys):
            continue
        row = {key: Decimal(str(values[key])) / Decimal("1000000") for key in keys}
        rates[model.lower()] = row
        aliases = values.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str):
                    rates[alias.lower()] = row
    return str(registry.get("_updated_at", "unknown")), rates


def rollout_model(records: Sequence[dict[str, object]]) -> str:
    """Return the first model declared by an active raw-log turn context."""
    for record in records:
        if record.get("type") != "turn_context":
            continue
        model = payload_for(record).get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()
    return ""


def build_ledger_from_rollout(
    rollout_path: Path,
    base_csv: Path,
    pricing_path: Path = AGENT_REPORT_PRICING_FILE,
) -> tuple[list[str], list[dict[str, str]]]:
    records, inherited_baseline = active_rollout_records(read_rollout(rollout_path))
    pricing_version, pricing_table = load_agent_report_pricing(pricing_path)
    model = rollout_model(records)
    sol_rates = pricing_table.get("gpt-5.6-sol")
    call_details: dict[str, tuple[str, str, list[str]]] = {}
    for record in records:
        payload = payload_for(record)
        if payload.get("type") not in {"custom_tool_call", "function_call"}:
            continue
        call_id = str(payload.get("call_id", ""))
        arguments = tool_input(payload)
        call_details[call_id] = (
            str(payload.get("name", "")),
            arguments,
            skill_names_from_paths(arguments),
        )

    rows: list[dict[str, str]] = []
    previous_context = 0
    previous_cumulative_total = 0
    previous_system_total = 0
    previous_cumulative_cache_read = 0
    previous_cumulative_cache_write = 0
    cumulative_cost = Decimal("0")
    cumulative_model_input_equivalent = 0
    cumulative_sol_input_equivalent = 0
    snapshot_number = 0

    token_records = [
        record
        for record in records
        if record.get("type") == "event_msg"
        and payload_for(record).get("type") == "token_count"
    ]
    first_usage = (
        payload_for(token_records[0]).get("info", {}) if token_records else {}
    )
    if isinstance(first_usage, dict):
        first_last = first_usage.get("last_token_usage", {})
        if isinstance(first_last, dict) and int(first_last.get("cached_input_tokens", 0)):
            row = empty_ledger_row()
            row.update(
                {
                    "time_utc": f"before {records[0].get('timestamp', '')}",
                    "event": "Unknown prior external cache creation",
                    "evidence_summary": (
                        "Logically required by the first observed cache read; "
                        "absent from current rollout"
                    ),
                    "included_in_snapshot": "outside selected trace",
                    "evidence_type": "unknown required predecessor",
                    "previous_call_total_tokens": "0",
                    "previous_cumulative_total_tokens": "0",
                    "cumulative_total_tokens": "0",
                    "previous_cumulative_cache_read_tokens": "0",
                    "cumulative_cache_read_tokens": "0",
                    "previous_cumulative_cache_write_tokens": "0",
                    "cumulative_cache_write_tokens": "0",
                    "previous_cumulative_cache_activity_tokens": "0",
                    "cumulative_cache_activity_tokens": "0",
                    "notes": (
                        "A cache entry must predate a cache read, but its creating "
                        "request, time, and write size are unknown."
                    ),
                }
            )
            rows.append(row)

    for record in records:
        payload = payload_for(record)
        if record.get("type") == "turn_context":
            declared_model = payload.get("model")
            if isinstance(declared_model, str) and declared_model.strip():
                model = declared_model.strip()
        if record.get("type") == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info", {})
            if not isinstance(info, dict):
                continue
            usage = info.get("last_token_usage", {})
            cumulative = info.get("total_token_usage", {})
            if not isinstance(usage, dict) or not isinstance(cumulative, dict):
                continue
            snapshot_number += 1
            input_tokens = int(usage.get("input_tokens", 0))
            cache_read = int(usage.get("cached_input_tokens", 0))
            cache_write = int(usage.get("cache_write_input_tokens", 0))
            output_tokens = int(usage.get("output_tokens", 0))
            reasoning_tokens = int(usage.get("reasoning_output_tokens", 0))
            total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens))
            system_total = int(cumulative.get("total_tokens", 0)) - inherited_baseline[0]
            distinct_call = system_total != previous_system_total
            cumulative_total = previous_cumulative_total + (
                total_tokens if distinct_call else 0
            )
            cumulative_cache_read = (
                int(cumulative.get("cached_input_tokens", 0))
                - inherited_baseline[1]
            )
            cumulative_cache_write = int(
                cumulative.get("cache_write_input_tokens", 0)
            ) - inherited_baseline[2]
            rate_limits = payload.get("rate_limits", {})
            primary_limit = (
                rate_limits.get("primary", {})
                if isinstance(rate_limits, dict)
                else {}
            )
            used_percent = (
                primary_limit.get("used_percent")
                if isinstance(primary_limit, dict)
                else None
            )
            budget_remaining = (
                max(0.0, 100.0 - float(used_percent))
                if isinstance(used_percent, (int, float))
                else None
            )
            row = empty_ledger_row()
            uncached_total = input_tokens - cache_read
            model_rates = pricing_table.get(model.lower())
            if model_rates is None:
                cached_read_cost = output_cost = input_cost = Decimal("0")
            else:
                cached_read_cost = (
                    Decimal(cache_read) * model_rates["cached_input_per_million"]
                    if distinct_call else Decimal("0")
                )
                output_cost = (
                    Decimal(output_tokens) * model_rates["output_per_million"]
                    if distinct_call else Decimal("0")
                )
                input_cost = (
                    Decimal(uncached_total) * model_rates["input_per_million"]
                    + cached_read_cost if distinct_call else Decimal("0")
                )
            total_cost = input_cost + output_cost
            model_input_equivalent = (
                total_cost / model_rates["input_per_million"]
                if model_rates is not None and model_rates["input_per_million"]
                else Decimal("0")
            )
            sol_input_equivalent = (
                total_cost / sol_rates["input_per_million"]
                if sol_rates is not None and sol_rates["input_per_million"]
                else Decimal("0")
            )
            model_input_equivalent_tokens = round(model_input_equivalent)
            sol_input_equivalent_tokens = round(sol_input_equivalent)
            previous_cumulative_cost = cumulative_cost
            cumulative_cost += total_cost
            previous_cumulative_model_input_equivalent = cumulative_model_input_equivalent
            cumulative_model_input_equivalent += model_input_equivalent_tokens
            previous_cumulative_sol_input_equivalent = cumulative_sol_input_equivalent
            cumulative_sol_input_equivalent += sol_input_equivalent_tokens
            if previous_context:
                uncached_old = previous_context - cache_read
                uncached_new = input_tokens - previous_context
                evidence_type = "observed plus continuity inference"
            else:
                uncached_old = None
                uncached_new = uncached_total
                evidence_type = "observed plus derived"
            row.update(
                {
                    "_source_line": str(record.get("_source_line", "")),
                    "_raw_payload_type": str(payload.get("type", "")),
                    "_budget_remaining": (
                        ""
                        if budget_remaining is None
                        else f"{budget_remaining:g}"
                    ),
                    "time_utc": str(record.get("timestamp", "")),
                    "event": f"Token snapshot {snapshot_number}",
                    "model": model,
                    "_pricing_version": pricing_version,
                    "evidence_summary": (
                        f"{input_tokens:,} input + {output_tokens:,} output; "
                        f"{reasoning_tokens:,} reasoning separate"
                    ),
                    "evidence_type": evidence_type,
                    "previous_call_total_tokens": str(previous_context),
                    "cache_read_tokens": str(cache_read),
                    "input_tokens": str(input_tokens),
                    "uncached_old_history_tokens_inferred": (
                        "" if uncached_old is None else str(uncached_old)
                    ),
                    "uncached_new_tokens_inferred": str(uncached_new),
                    "total_uncached_input_tokens": str(uncached_total),
                    "reasoning_tokens": str(reasoning_tokens),
                    "output_tokens": str(output_tokens),
                    "visible_output_tokens_derived": str(
                        output_tokens - reasoning_tokens
                    ),
                    "total_tokens": str(total_tokens),
                    "cache_write_tokens": str(cache_write),
                    "previous_cumulative_total_tokens": str(
                        previous_cumulative_total
                    ),
                    "cumulative_total_tokens": str(cumulative_total),
                    "system_total_tokens": str(system_total),
                    "previous_cumulative_cache_read_tokens": str(
                        previous_cumulative_cache_read
                    ),
                    "cumulative_cache_read_tokens": str(cumulative_cache_read),
                    "previous_cumulative_cache_write_tokens": str(
                        previous_cumulative_cache_write
                    ),
                    "cumulative_cache_write_tokens": str(cumulative_cache_write),
                    "total_cost_usd": format_usd(total_cost),
                    "previous_cumulative_cost_usd": format_usd(
                        previous_cumulative_cost
                    ),
                    "cumulative_cost_usd": format_usd(cumulative_cost),
                    "model_input_equivalent_tokens": str(model_input_equivalent_tokens),
                    "previous_cumulative_model_input_equivalent_tokens": str(
                        previous_cumulative_model_input_equivalent
                    ),
                    "cumulative_model_input_equivalent_tokens": str(
                        cumulative_model_input_equivalent
                    ),
                    "sol_input_equivalent_tokens": str(sol_input_equivalent_tokens),
                    "previous_cumulative_sol_input_equivalent_tokens": str(
                        previous_cumulative_sol_input_equivalent
                    ),
                    "cumulative_sol_input_equivalent_tokens": str(
                        cumulative_sol_input_equivalent
                    ),
                    "previous_cumulative_cache_activity_tokens": str(
                        previous_cumulative_cache_read
                        + previous_cumulative_cache_write
                    ),
                    "cumulative_cache_activity_tokens": str(
                        cumulative_cache_read + cumulative_cache_write
                    ),
                    "notes": (
                        "Reasoning is a subset of output_tokens and is already "
                        "included in total_tokens; do not add it again."
                    ),
                }
            )
            rows.append(row)
            previous_context = total_tokens
            previous_cumulative_total = cumulative_total
            previous_system_total = system_total
            previous_cumulative_cache_read = cumulative_cache_read
            previous_cumulative_cache_write = cumulative_cache_write
            continue

        described = event_from_record(record, call_details)
        if not described:
            continue
        event, evidence, skills = described
        row = empty_ledger_row()
        row.update(
            {
                "_source_line": str(record.get("_source_line", "")),
                "_raw_payload_type": str(payload.get("type", "")),
                "time_utc": str(record.get("timestamp", "")),
                "event": event,
                "model": model,
                "_pricing_version": pricing_version,
                "evidence_summary": evidence,
                "skills": skills,
                "evidence_type": "observed event",
                "previous_call_total_tokens": str(previous_context),
                "system_total_tokens": "",
                "previous_cumulative_total_tokens": str(previous_cumulative_total),
                "cumulative_total_tokens": str(previous_cumulative_total),
                "previous_cumulative_cache_read_tokens": str(
                    previous_cumulative_cache_read
                ),
                "cumulative_cache_read_tokens": str(previous_cumulative_cache_read),
                "previous_cumulative_cache_write_tokens": str(
                    previous_cumulative_cache_write
                ),
                "cumulative_cache_write_tokens": str(previous_cumulative_cache_write),
                "previous_cumulative_cost_usd": format_usd(cumulative_cost),
                "cumulative_cost_usd": format_usd(cumulative_cost),
                "previous_cumulative_model_input_equivalent_tokens": str(
                    cumulative_model_input_equivalent
                ),
                "cumulative_model_input_equivalent_tokens": str(
                    cumulative_model_input_equivalent
                ),
                "previous_cumulative_sol_input_equivalent_tokens": str(
                    cumulative_sol_input_equivalent
                ),
                "cumulative_sol_input_equivalent_tokens": str(
                    cumulative_sol_input_equivalent
                ),
                "previous_cumulative_cache_activity_tokens": str(
                    previous_cumulative_cache_read + previous_cumulative_cache_write
                ),
                "cumulative_cache_activity_tokens": str(
                    previous_cumulative_cache_read + previous_cumulative_cache_write
                ),
            }
        )
        rows.append(row)

    for index, row in enumerate(rows):
        row["row"] = str(index)
    snapshot_indexes = [
        index
        for index, row in enumerate(rows)
        if row["event"].startswith("Token snapshot ")
    ]
    for index, row in enumerate(rows):
        if row["included_in_snapshot"]:
            continue
        if row["event"].startswith("Token snapshot "):
            row["included_in_snapshot"] = row["row"]
            continue
        if row.get("_raw_payload_type") in {"agent_message", "user_message"}:
            row["included_in_snapshot"] = "not separate"
            continue
        later_snapshots = [position for position in snapshot_indexes if position > index]
        delay = 1 if row.get("_raw_payload_type") in {
            "custom_tool_call_output",
            "function_call_output",
        } else 0
        if len(later_snapshots) > delay:
            row["included_in_snapshot"] = rows[later_snapshots[delay]]["row"]
        else:
            row["included_in_snapshot"] = "after final snapshot"

    skill_token_sizes = load_skill_token_sizes(find_skills_report_path(base_csv))
    if skill_token_sizes:
        for row in rows:
            if not row["skills"]:
                continue
            label, _, names_text = row["skills"].partition(": ")
            names = [name for name in names_text.split("; ") if name]
            row["skills"] = (
                f"{label}: {'; '.join(annotate_skill_tokens(names, skill_token_sizes))}"
            )
    return list(LEDGER_HEADERS), collapse_rows_by_snapshot(rows)


def concise_pattern_part(row: dict[str, str]) -> str | None:
    event = row["event"]
    if row.get("_raw_payload_type") in {"agent_message", "user_message"}:
        return None
    if event in {
        "Session metadata",
        "Task settings applied",
        "Task started",
        "Developer instructions",
        "User message",
        "World-state snapshot",
        "Turn boundary",
    }:
        return "context setup"
    if event == "Inference reasoning" or event == "agent_reasoning telemetry":
        return "reasoning"
    if event == "Assistant message" or event == "agent_message response item":
        return "assistant message"
    if event.endswith(" call"):
        detail = row["evidence_summary"].partition(": ")[2]
        return f"{event} ({detail})" if detail else event
    if event.endswith(" result"):
        detail = row["evidence_summary"].partition(": ")[2]
        return f"{event} ({detail})" if detail else event
    if event == "patch_apply_end telemetry":
        return "patch applied"
    if event == "Subagent activity telemetry":
        return "subagent activity"
    if event == "inter_agent_communication_metadata":
        return "inter-agent message"
    if event in {"Task completed", "Turn aborted"}:
        return event.lower()
    return event


def collapse_rows_by_snapshot(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    source_rows = [
        row
        for row in rows
        if row["event"] != "Unknown prior external cache creation"
    ]
    groups: list[list[dict[str, str]]] = []
    pending: list[dict[str, str]] = []
    for row in source_rows:
        pending.append(row)
        if row["event"].startswith("Token snapshot "):
            groups.append(pending)
            pending = []
    if pending:
        groups.append(pending)

    collapsed: list[dict[str, str]] = []
    previous_snapshot: dict[str, str] | None = None
    for group in groups:
        snapshot = next(
            (row for row in reversed(group) if row["event"].startswith("Token snapshot ")),
            None,
        )
        measured = snapshot is not None
        base = dict(snapshot or group[-1])
        components: list[str] = []
        for row in group:
            if row is snapshot:
                continue
            component = concise_pattern_part(row)
            if component and (not components or components[-1] != component):
                components.append(component)

        calls = [
            row["event"][:-5].replace("_", " ").title()
            for row in group
            if row["event"].endswith(" call")
        ]
        if not measured:
            event = "Unmeasured trailing events"
        elif (
            not components
            and previous_snapshot is not None
            and snapshot["cumulative_total_tokens"]
            == previous_snapshot["cumulative_total_tokens"]
        ):
            event = "Duplicate token snapshot"
            components = ["duplicate usage telemetry"]
        elif calls:
            event = f"{' + '.join(dict.fromkeys(calls))} cycle"
        elif "reasoning" in components:
            event = "Reasoning cycle"
        elif "assistant message" in components:
            event = "Assistant response"
        else:
            event = "Context cycle"

        source_lines = [
            int(row["_source_line"])
            for row in group
            if row.get("_source_line", "").isdigit()
        ]
        raw_range = (
            f"raw lines {min(source_lines)}–{max(source_lines)}"
            if source_lines
            else "raw line unavailable"
        )
        evidence = " → ".join(components) if components else event.lower()
        budget = snapshot.get("_budget_remaining", "") if snapshot else ""

        skill_values: list[str] = []
        for row in group:
            prefix = "load result: "
            if not row["skills"].startswith(prefix):
                continue
            for skill in row["skills"][len(prefix) :].split("; "):
                if skill and skill not in skill_values:
                    skill_values.append(skill)
        base.update(
            {
                "_source_line": str(min(source_lines)) if source_lines else "",
                "_source_range": raw_range,
                "_usage": f"{budget}% remaining" if budget else "",
                "event": event,
                "evidence_summary": evidence,
                "skills": "; ".join(skill_values),
                "included_in_snapshot": "" if measured else "after final snapshot",
                "evidence_type": (
                    snapshot["evidence_type"] if snapshot else "observed event"
                ),
            }
        )
        collapsed.append(base)
        if snapshot:
            previous_snapshot = snapshot

    for index, row in enumerate(collapsed):
        row["row"] = str(index)
        if row["included_in_snapshot"] != "after final snapshot":
            row["included_in_snapshot"] = row["row"]
    return collapsed


def load_skill_token_sizes(report_path: Path) -> dict[str, int]:
    if not report_path.exists():
        return {}
    with report_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        skills: dict[str, int] = {}
        for row in reader:
            path = row.get("path", "")
            if not path:
                continue
            token_value = row.get("tokens", "")
            if not token_value:
                continue
            try:
                token_count = int(token_value)
            except ValueError:
                continue
            skill_name = Path(path).name if not Path(path).is_dir() else ""
            if not skill_name:
                skill_name = Path(path).parent.name
            if skill_name == "SKILL.md":
                skill_name = Path(path).parent.name
            if skill_name:
                skills[skill_name] = token_count
        return skills


def find_skills_report_path(base_csv: Path) -> Path:
    for parent in (base_csv.parent, *base_csv.parent.parents):
        candidate = parent / SKILLS_REPORT_FILE
        if candidate.exists():
            return candidate
    return base_csv.parent.parent.parent / SKILLS_REPORT_FILE


def annotate_skill_tokens(
    names: list[str], skill_token_sizes: dict[str, int]
) -> list[str]:
    formatted: list[str] = []
    for name in names:
        token_size = skill_token_sizes.get(name)
        if token_size is None:
            formatted.append(name)
        else:
            formatted.append(f"{name} ({token_size})")
    return formatted


def skill_names_from_paths(text: str) -> list[str]:
    return list(dict.fromkeys(match.group("name") for match in SKILL_PATH.finditer(text)))


def skill_names_from_action(text: str, known_names: set[str]) -> list[str]:
    aliases: dict[str, str | None] = {}
    for name in known_names:
        alias = name.rsplit("-", 1)[-1]
        aliases[alias] = name if alias not in aliases else None

    mentions: list[tuple[int, str]] = []
    for action in SKILL_ACTION.finditer(text):
        phrase = action.group(0)
        phrase_start = action.start()
        for name in known_names:
            match = re.search(
                rf"(?<![A-Za-z0-9_.:-]){re.escape(name)}(?![A-Za-z0-9_.:-])",
                phrase,
                re.IGNORECASE,
            )
            if match:
                mentions.append((phrase_start + match.start(), name))
        for alias, name in aliases.items():
            if name is None:
                continue
            match = re.search(
                rf"(?<![A-Za-z0-9_.:-]){re.escape(alias)}(?![A-Za-z0-9_.:-])",
                phrase,
                re.IGNORECASE,
            )
            if match:
                mentions.append((phrase_start + match.start(), name))

    ordered: list[str] = []
    for _, name in sorted(mentions):
        if name not in ordered:
            ordered.append(name)
    return ordered


def enrich_skill_evidence(
    headers: list[str],
    rows: list[dict[str, str]],
    rollout_path: Path,
    base_csv: Path,
) -> tuple[list[str], list[dict[str, str]]]:
    records = [
        json.loads(line)
        for line in rollout_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    skill_token_sizes = load_skill_token_sizes(
        find_skills_report_path(base_csv)
    )
    response_items = [
        record
        for record in records
        if record.get("type") == "response_item"
        and isinstance(record.get("payload"), dict)
    ]

    call_skills: dict[str, list[str]] = {}
    known_names: set[str] = set()
    for record in response_items:
        payload = record["payload"]
        if payload.get("type") != "custom_tool_call":
            continue
        names = skill_names_from_paths(content_text(payload.get("input", "")))
        if names:
            call_skills[str(payload.get("call_id", ""))] = names
            known_names.update(names)

    evidence: dict[tuple[str, str], list[str]] = {}
    for record in response_items:
        timestamp = str(record.get("timestamp", ""))
        payload = record["payload"]
        payload_type = payload.get("type")
        role = payload.get("role")
        names: list[str] = []
        event = ""
        label = ""

        if payload_type == "custom_tool_call":
            names = call_skills.get(str(payload.get("call_id", "")), [])
            event, label = "Exec call", "load call"
        elif payload_type == "custom_tool_call_output":
            names = call_skills.get(str(payload.get("call_id", "")), [])
            event, label = "Exec result", "load result"
        elif payload_type == "message" and role in {"user", "assistant"}:
            text = content_text(payload.get("content", []))
            names = skill_names_from_action(text, known_names)
            if role == "user":
                event, label = "Automation request", "requested"
            else:
                event, label = "Assistant message", "announced"

        if names:
            value = (
                f"{label}: {'; '.join(annotate_skill_tokens(names, skill_token_sizes))}"
            )
            evidence.setdefault((timestamp, event), []).append(value)

    skills_index = headers.index("evidence_summary") + 1
    enriched_headers = [header for header in headers if header != "skills"]
    enriched_headers.insert(skills_index, "skills")
    for row in rows:
        values = evidence.get((row.get("time_utc", ""), row.get("event", "")), [])
        row["skills"] = " | ".join(dict.fromkeys(values))
    return enriched_headers, rows


def write_csv_atomically(
    path: Path, headers: Sequence[str], rows: Sequence[dict[str, str]]
) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows({header: row.get(header, "") for header in headers} for row in rows)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def display_name(header: str) -> str:
    return DISPLAY_LABELS.get(header, header.replace("_", " ").strip().title())


def cell_class(value: str) -> str:
    return "numeric" if value and NUMBER.fullmatch(value.strip()) else "text"


def readable_display_name(header: str) -> str:
    """Return the human label without its parenthesized data field name."""
    return display_name(header).partition(" (")[0]


def display_headers(headers: Sequence[str]) -> list[str]:
    omitted = {
        "cumulative_cache_activity_tokens",
        "notes",
        "included_in_snapshot",
        "evidence_type",
    }
    return [
        header
        for header in headers
        if (not header.startswith("previous_") or header == "previous_call_total_tokens")
        and header not in omitted
    ]


def calculation_parts(header: str, row: dict[str, str]) -> tuple[str, ...] | None:
    spec = CALCULATION_SPECS.get(header)
    if header == "uncached_new_tokens_inferred" and not row.get(
        "uncached_old_history_tokens_inferred"
    ):
        spec = None
    if not spec:
        return None
    parts = tuple(row.get(part, part) if part in row else part for part in spec)
    return parts if all(parts) else None


def render_cell(header: str, row: dict[str, str]) -> str:
    value = row.get(header, "")
    rendered_value = html.escape(value)
    if header == "time_utc" and row.get("_source_href"):
        href = html.escape(row["_source_href"], quote=True)
        source_line = html.escape(row.get("_source_line", ""))
        rendered_value = (
            f'<a href="{href}" title="Open raw rollout line {source_line}">'
            f"{rendered_value}</a>"
        )
    if header == "time_utc" and row.get("_source_range"):
        rendered_value += (
            '<small class="source-range">'
            f"{html.escape(row['_source_range'])}"
            "</small>"
        )
    if header == "time_utc" and row.get("_usage"):
        rendered_value += (
            '<small class="usage-inline">Usage: '
            f"{html.escape(row['_usage'])}"
            "</small>"
        )
    parts = calculation_parts(header, row)
    if value and parts:
        calculation_lines = [
            f'<span class="calculation-line">{html.escape(parts[0])}</span>'
        ]
        operator_symbols = {"subtract": "-", "plus": "+"}
        for operator, operand in zip(parts[1::2], parts[2::2]):
            symbol = operator_symbols.get(operator, operator)
            calculation_lines.append(
                '<span class="calculation-line">'
                f"{html.escape(symbol)} {html.escape(operand)}"
                "</span>"
            )
        rendered_value += (
            '<small class="cell-calculation">'
            f"{''.join(calculation_lines)}"
            "</small>"
        )
    return f'<td class="{cell_class(value)}">{rendered_value}</td>'


def render_raw_rollout_html(path: Path) -> str:
    rendered_lines = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        rendered_lines.append(
            f'<span class="source-line" id="L{line_number}">'
            f'<a class="line-number" href="#L{line_number}">{line_number}</a>'
            f"{html.escape(line)}</span>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Raw rollout · {html.escape(path.name)}</title>
  <style>
    :root {{ color-scheme: light dark; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    body {{ margin: 0; background: Canvas; color: CanvasText; }}
    pre {{ margin: 0; padding: .75rem 0; overflow: visible; white-space: pre; }}
    .source-line {{ display: block; min-height: 1.35em; padding-right: 1rem; }}
    .source-line:target {{ background: color-mix(in srgb, #f5c542 28%, Canvas); }}
    .line-number {{
      position: sticky;
      left: 0;
      display: inline-block;
      width: 5rem;
      margin-right: .75rem;
      padding-right: .75rem;
      color: GrayText;
      background: Canvas;
      text-align: right;
      text-decoration: none;
      user-select: none;
    }}
  </style>
</head>
<body>
  <pre>{''.join(rendered_lines)}</pre>
  {copyright_footer_html()}
</body>
</html>
"""


def render_structured_explanation(markdown: str) -> str:
    """Render the constrained structured-explanation Markdown used by this report."""
    output: list[str] = []
    item_open = False
    code_lines: list[str] | None = None
    item_pattern = re.compile(
        r"^\*\*(QUERY|SUB-QUERY|FACT|HYPOTHESIS|UNKNOWN|ANSWER): ([A-Z]+-\d+)\*\*$"
    )
    synopsis_pattern = re.compile(r"^- \*\*SYNOPSIS:\*\* (.+)$")

    for line in markdown.splitlines():
        if line == "```text":
            code_lines = []
            continue
        if line == "```" and code_lines is not None:
            output.append(f"<pre>{html.escape(chr(10).join(code_lines))}</pre>")
            code_lines = None
            continue
        if code_lines is not None:
            code_lines.append(line)
            continue

        if line.startswith("# "):
            output.append(f"<h2>{html.escape(line[2:])}</h2>")
            continue

        item_match = item_pattern.fullmatch(line)
        if item_match:
            if item_open:
                output.append("</section>")
            kind, identifier = item_match.groups()
            css_kind = kind.lower().replace("-", "_")
            output.append(
                f'<section class="ste-item ste-{css_kind}">'
                f"<h3><span>{html.escape(kind)}</span> {html.escape(identifier)}</h3>"
            )
            item_open = True
            continue

        synopsis_match = synopsis_pattern.fullmatch(line)
        if synopsis_match:
            output.append(
                f"<p><strong>Synopsis:</strong> {html.escape(synopsis_match.group(1))}</p>"
            )
            continue

        if line:
            output.append(f"<p>{html.escape(line)}</p>")

    if code_lines is not None:
        raise ValueError("Structured explanation has an unclosed text code fence")
    if item_open:
        output.append("</section>")
    return "".join(output)


def render_html(
    headers: Sequence[str],
    rows: Sequence[dict[str, str]],
    *,
    title: str,
    source_name: str,
    explanation_html: str,
    explanation_name: str | None,
    nav_links: Sequence[tuple[str, str]] = (),
    local_time: bool = False,
) -> str:
    reordered_headers = display_headers(headers)

    def compact_label(header: str) -> str:
        if local_time and header == "time_utc":
            return "Local time"
        return readable_display_name(header)

    def full_label(header: str) -> str:
        if local_time and header == "time_utc":
            return "Local time"
        return display_name(header)

    def definition(header: str) -> str:
        if local_time and header == "time_utc":
            return "Event timestamp converted to the computer's local time."
        return COLUMN_DEFINITIONS.get(header, header)

    head_cells = "".join(
        f'<th scope="col" title="{html.escape(definition(header))}">'
        f'<span class="field-name" '
        f'data-compact="{html.escape(compact_label(header), quote=True)}" '
        f'data-full="{html.escape(full_label(header), quote=True)}">{html.escape(compact_label(header))}'
        '</span>'
        f"</th>"
        for header in reordered_headers
    )
    definitions = "".join(
        f"<dt>{html.escape(full_label(header))}</dt>"
        f"<dd>{html.escape(definition(header))}</dd>"
        for header in reordered_headers
    )
    body_rows = []
    for row in rows:
        cells = "".join(render_cell(header, row) for header in reordered_headers)
        body_rows.append(f"<tr>{cells}</tr>")

    explanation_source = (
        f" · explanation: {html.escape(explanation_name)}" if explanation_name else ""
    )
    pricing_versions = sorted({row.get("_pricing_version", "") for row in rows} - {""})
    models = sorted({row.get("model", "") for row in rows} - {""})
    pricing_summary = (
        " · Agent Report pricing card "
        + html.escape(", ".join(pricing_versions))
        + " · model: "
        + html.escape(", ".join(models) or "not recorded")
        if pricing_versions
        else ""
    )
    nav = ""
    if nav_links:
        nav = '<nav class="ledger-nav">' + "".join(
            f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'
            for label, href in nav_links
        ) + "</nav>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#14202b; --muted:#63717d; --paper:#f3f6f6; --sheet:#fff; --line:#d9e1e3; --accent:#d97736; --focus:#1167a8; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.5 "Avenir Next", Avenir, "Segoe UI", sans-serif; }}
    .page {{ max-width: 1800px; margin: auto; padding: 36px 28px 60px; }}
    a {{ color:#155f8c; text-underline-offset:3px; }}
    a:focus-visible, summary:focus-visible, input:focus-visible {{ outline:3px solid var(--focus); outline-offset:3px; }}
    .ledger-nav {{ display: flex; flex-wrap: wrap; gap: 1.15rem; margin: 0 0 26px; }}
    .ledger-nav a {{ font-weight: 700; }}
    .ledger-header {{ margin-bottom: 28px; }}
    .eyebrow {{ color:var(--accent); font:700 11px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:.09em; text-transform:uppercase; }}
    h1 {{ margin:7px 0 10px; font:600 clamp(36px,6vw,68px)/1 "Iowan Old Style","Palatino Linotype",Georgia,serif; letter-spacing:-.035em; }}
    h2 {{ margin: 1.2rem 0 .7rem; font:600 24px/1.2 "Iowan Old Style","Palatino Linotype",Georgia,serif; }}
    .meta {{ max-width: 110rem; margin: 0; color: var(--muted); font-size: .94rem; }}
    .structured-explanation {{ max-width: 78rem; }}
    .ste-item {{ margin: .55rem 0; padding: .55rem .75rem; border-left: .3rem solid #728096; background: color-mix(in srgb, CanvasText 4%, Canvas); }}
    .ste-item h3 {{ margin: 0 0 .3rem; font-size: .95rem; }}
    .ste-item h3 span {{ display: inline-block; min-width: 7.5rem; color: #4e8cff; }}
    .ste-item p {{ margin: .25rem 0; line-height: 1.45; }}
    .ste-query {{ border-left-color: #8b5cf6; }}
    .ste-sub_query {{ border-left-color: #3b82f6; }}
    .ste-fact {{ border-left-color: #22c55e; }}
    .ste-hypothesis {{ border-left-color: #f59e0b; }}
    .ste-unknown {{ border-left-color: #ef4444; }}
    .ste-answer {{ border-left-color: #06b6d4; }}
    pre {{ overflow: auto; padding: .7rem; border-radius: .4rem; background: #172033; color: #f5f7fb; line-height: 1.35; font-variant-numeric: tabular-nums; }}
    details {{ margin: 0 0 .8rem; border: 1px solid var(--line); border-radius: .5rem; padding: .7rem .85rem; background:var(--sheet); }}
    summary {{ cursor: pointer; font-weight: 700; }}
    dl {{ display: grid; grid-template-columns: minmax(12rem, 20rem) 1fr; gap: .3rem .8rem; margin: .7rem 0 0; font-size: .86rem; }}
    dt {{ font-weight: 700; }}
    dd {{ margin: 0; }}
    .table-scroll {{
      height: 68vh;
      min-height: 16rem;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: .5rem;
      background: var(--sheet);
    }}
    table {{ border-collapse: separate; border-spacing: 0; min-width: 100%; font-size: .82rem; }}
    th, td {{
      padding: .45rem .55rem;
      border-right: 1px solid color-mix(in srgb, CanvasText 15%, transparent);
      border-bottom: 1px solid color-mix(in srgb, CanvasText 15%, transparent);
      vertical-align: top;
      white-space: nowrap;
    }}
    thead th {{
      position: sticky;
      top: 0;
      z-index: 10;
      max-width: 18rem;
      white-space: normal;
      background: #243247;
      color: #fff;
      text-align: left;
      box-shadow: 0 1px 0 rgba(255,255,255,.22);
    }}
    tbody tr:nth-child(even) td {{ background:#f7f9fa; }}
    tbody tr:hover td {{ background:#edf5f8; }}
    td.numeric {{ text-align: right; font-variant-numeric: tabular-nums; }}
    td.text {{ max-width: 34rem; white-space: normal; min-width: 0; }}
    .field-name-toggle {{ margin: .5rem 0 .45rem; }}
    .field-name {{ display: inline; }}
    .cell-calculation {{ display: block; width: max-content; margin: .2rem 0 0 auto; color: GrayText; font-size: .72rem; white-space: nowrap; }}
    .calculation-line {{ display: block; text-align: right; font-variant-numeric: tabular-nums; }}
    .source-range {{ display: block; margin-top: .18rem; color: GrayText; font-size: .72rem; white-space: nowrap; }}
    .usage-inline {{ display: block; margin-top: .18rem; color: GrayText; font-size: .72rem; white-space: nowrap; }}
    @media(max-width:720px) {{ .page {{ padding:24px 14px 44px; }} }}
    @media print {{ body {{ background:#fff; }} .page {{ max-width:none; padding:0; }} .ledger-nav {{ display:none; }} }}
  </style>
</head>
<body>
<main class="page">
  {nav}
  <header class="ledger-header">
    <div class="eyebrow">Agent Report · thread ledger</div>
    <h1>{html.escape(title)}</h1>
    <p class="meta">{len(rows)} rows · source: {html.escape(source_name)}{explanation_source}{pricing_summary} · API-equivalent estimates, not actual charges · headers remain visible while rows scroll</p>
  </header>
  <article class="structured-explanation" id="explanation">{explanation_html}</article>
  <details id="definitions">
    <summary>Column definitions and formulas</summary>
    <h3>Field relationships</h3>
    <pre class="field-relationships" aria-label="Hierarchy of token fields and their calculation inputs">{html.escape(FIELD_RELATIONSHIP_TREE)}</pre>
    <dl>{definitions}</dl>
  </details>
  <div class="field-name-toggle">
    <label><input type="checkbox" id="toggle-field-names"> Include field names</label>
  </div>
  <div class="table-scroll" id="ledger" role="region" aria-label="Scrollable token ledger" tabindex="0">
    <table>
      <thead><tr>{head_cells}</tr></thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>
  </div>
  <script>
    (function() {{
      const checkbox = document.getElementById("toggle-field-names");
      const fieldNames = document.querySelectorAll('.field-name');

      const applyFieldNameVisibility = () => {{
        const includeFieldNames = checkbox && checkbox.checked;
        fieldNames.forEach((element) => {{
          element.textContent = includeFieldNames
            ? element.getAttribute('data-full') || ''
            : element.getAttribute('data-compact') || '';
        }});
      }};

      if (checkbox) {{
        applyFieldNameVisibility();
        checkbox.addEventListener('change', applyFieldNameVisibility);
      }}
    }})();
  </script>
  {copyright_footer_html()}
</main>
</body>
</html>
"""


def write_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.from_rollout and args.rollout:
        raise ValueError("--from-rollout and --rollout are mutually exclusive")
    if args.write_enriched_csv and not args.rollout:
        raise ValueError("--write-enriched-csv requires --rollout")
    if args.from_rollout:
        headers, rows = build_ledger_from_rollout(args.from_rollout, args.input_csv)
        write_csv_atomically(args.input_csv, headers, rows)
        raw_output = args.output_html.with_name(
            f"{args.output_html.stem}-raw.html"
        )
        write_atomically(raw_output, render_raw_rollout_html(args.from_rollout))
        for row in rows:
            source_line = row.get("_source_line", "")
            if source_line:
                row["_source_href"] = f"{raw_output.name}#L{source_line}"
    else:
        headers, rows = read_csv(args.input_csv)
    if args.rollout:
        headers, rows = enrich_skill_evidence(headers, rows, args.rollout, args.input_csv)
        if args.write_enriched_csv:
            write_csv_atomically(args.input_csv, headers, rows)
    explanation_html = ""
    explanation_name = None
    if args.explanation:
        explanation_html = render_structured_explanation(
            args.explanation.read_text(encoding="utf-8")
        )
        explanation_name = args.explanation.name
    document = render_html(
        headers,
        rows,
        title=args.title,
        source_name=args.input_csv.name,
        explanation_html=explanation_html,
        explanation_name=explanation_name,
    )
    write_atomically(args.output_html, document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
