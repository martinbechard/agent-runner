# Codex Timeline Reporting Plan

## Goal

Extend the existing HTML timeline report so it works for both Claude-backed
and Codex-backed `prompt-runner` / `methodology-runner` runs.

The target is parity on:

- per-step wall time
- per-call drill-down
- tool / subagent activity
- model identification

and best-effort support for:

- token usage
- estimated or direct cost

without regressing existing Claude reports.

## Current state

The current report generator is [`scripts/run-timeline.py`](../../../scripts/run-timeline.py).
It has two layers:

1. A mostly reusable data/rendering layer:
   - `ToolCall`
   - `ToolResult`
   - `Turn`
   - `CallDetail`
   - `Step`
   - `PhaseTimeline`
   - HTML rendering and popup UI

2. A Claude-specific parser layer:
   - `parse_log()`
   - `_render_log_structured()`
   - field assumptions around Claude `stream-json`

The current parser assumes:

- JSONL event types `assistant`, `user`, `result`
- `message.content` blocks with `thinking`, `text`, `tool_use`
- `tool_result` blocks in user events
- `usage.input_tokens`, `usage.output_tokens`
- `usage.cache_creation_input_tokens`, `usage.cache_read_input_tokens`
- `total_cost_usd`, `duration_ms`, `duration_api_ms`

This is why the script can produce accurate Claude token and cost charts today.

## Findings

### 1. The HTML report is reusable; the parser is not

The script is structurally reusable, but its log parsing and structured-log
rendering are tightly coupled to Claude event names and fields.

### 2. Codex has the right integration point

Local CLI help shows:

- `codex exec --json`
- `codex exec --output-last-message`
- `codex exec --ephemeral`

This is sufficient to capture structured non-interactive logs for Codex-backed
prompt-runner calls.

### 3. Codex event schema still needs fixture capture

The official docs confirm JSON output exists, but they do not clearly document
the full event schema needed for the report.

We should not guess event names or token fields. We need a few real captured
Codex JSON logs first.

### 4. Cost support may be partial at first

If Codex JSON logs include usage fields, we can compute cost using current model
pricing.

If Codex JSON logs do not expose usage directly, we should still support the
timeline report with:

- duration
- tool activity
- turns
- final output
- model name

and render token/cost as unavailable for that backend instead of inventing
numbers.

## Constraints

### Concurrency

Another Codex agent is already working on methodology/prompt-runner skill work
and may need to modify `prompt-runner`.

To avoid conflict:

- keep the first changes isolated to `scripts/run-timeline.py`
- make the logging change in `src/cli/prompt_runner/codex_client.py` as narrow
  as possible
- avoid broader prompt-runner refactors until the Codex event shape is known

### Backward compatibility

Claude reporting must continue to work unchanged.

## Proposed architecture

### A. Split parser from renderer

Refactor `scripts/run-timeline.py` into three logical parts:

1. backend-neutral report model
2. backend-specific log parsers
3. backend-neutral HTML rendering

Planned functions:

- `detect_log_backend(path: Path) -> str`
- `parse_claude_log(path: Path) -> CallDetail`
- `parse_codex_log(path: Path) -> CallDetail`
- `render_log_structured(detail: CallDetail, raw_text: str, ...)`

### B. Add backend metadata to `CallDetail`

Add fields such as:

- `backend: str`
- `cost_available: bool`
- `usage_available: bool`

This lets the renderer avoid pretending every backend exposes the same token
model.

### C. Make Codex emit JSON logs

Update `src/cli/prompt_runner/codex_client.py` to:

- invoke `codex exec --json`
- keep writing the full JSONL stream to `.stdout.log`
- keep `--output-last-message` for the final artifact text

This change is small and reporting-driven.

### D. Make cost rendering conditional

The renderer should:

- show cost/tokens/cache bars when available
- show time/tool breakdown even when usage is unavailable
- label cache-create/read as backend-conditional, not universal

## Implementation phases

### Phase 1: Codex log capture

Scope:

- narrow update to `src/cli/prompt_runner/codex_client.py`
- no report parser changes yet

Tasks:

1. Add `--json` to Codex subprocess invocation.
2. Preserve the raw JSONL stream in the existing stdout log path.
3. Capture 2-3 tiny Codex fixture logs from:
   - one simple generator-only run
   - one generator + judge run
   - one tool-using run with file reads/writes
4. Save sanitized fixtures under `tests/fixtures/` or
   `tests/cli/prompt_runner/fixtures/`.

Exit criteria:

- real Codex JSONL fixture files exist in the repo
- we know the actual event names and token/usage fields

### Phase 2: Parser split

Scope:

- `scripts/run-timeline.py` only

Tasks:

1. Rename current `parse_log()` to `parse_claude_log()`.
2. Add backend detection for stdout logs.
3. Route existing workspace/run parsing through backend-specific parser calls.
4. Keep output identical for Claude fixtures.

Exit criteria:

- Claude report output remains stable
- parser selection is backend-aware

### Phase 3: Minimal Codex report support

Scope:

- `scripts/run-timeline.py`
- Codex fixtures/tests

Tasks:

1. Parse Codex JSONL into:
   - model
   - turns
   - timestamps / duration
   - tool calls / results
   - final output text
2. Add structured-log rendering for Codex events.
3. Render timelines even if token/cost fields are absent.

Exit criteria:

- HTML timeline works on Codex-backed runs
- drill-down popups show Codex activity coherently

### Phase 4: Usage and cost

Scope:

- `scripts/run-timeline.py`
- pricing helper module if needed

Tasks:

1. If Codex logs expose usage, map those fields into `CallDetail`.
2. If direct cost is absent, compute it from current model pricing.
3. Add backend-aware legends and summary rows.

Exit criteria:

- token/cost totals are correct when usage is available
- unavailable fields render explicitly as unavailable

## Tests

### Required

- Claude parser regression tests from existing fixtures
- Codex parser fixture tests
- one HTML smoke test that renders a Codex fixture run

### Nice to have

- golden-file HTML snapshots for one Claude and one Codex run

## File-level change scope

### Phase 1 likely files

- `src/cli/prompt_runner/codex_client.py`
- new test fixtures
- new parser tests if needed

### Phase 2-4 likely files

- `scripts/run-timeline.py`
- possibly a small helper module for pricing/backend detection

## Risks

### Risk 1: Codex JSON schema changes

Mitigation:

- parse defensively
- keep unknown-event rendering in the raw popup
- avoid hard-failing on unrecognized event types

### Risk 2: Usage fields are missing

Mitigation:

- ship time/tool parity first
- treat token/cost as optional for Codex

### Risk 3: Prompt-runner conflicts with concurrent work

Mitigation:

- keep the Codex logging change isolated and narrow
- avoid broader prompt-runner architecture edits until the other agent’s changes
  stabilize

## Recommendation

Start with **Phase 1** immediately.

That yields the decisive information: real Codex JSON fixtures. Without those,
any parser implementation would be speculative.

## References

- Codex non-interactive mode:
  https://developers.openai.com/codex/noninteractive
- Codex configuration reference:
  https://developers.openai.com/codex/config-reference
- Current Codex CLI help (`codex exec --help`) confirms:
  - `--json`
  - `--ephemeral`
  - `--output-last-message`
- Current model pricing pages for cost computation:
  - https://developers.openai.com/api/docs/models/gpt-5.2-codex
  - https://developers.openai.com/api/docs/models/gpt-5-codex
