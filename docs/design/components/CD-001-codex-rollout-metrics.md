# Component Design: Native Agent Execution Metrics

## 1. Finality

This section defines the outcome and boundary of native Codex and Junie execution reporting.

- **GOAL: GOAL-1** Report resource use for a complete Codex Desktop run
  - **SYNOPSIS:** Extend the cross-tool reporter so a root Codex rollout and every descendant agent thread can be summarized by response, turn, thread, work unit, phase, and complete run.
  - **BECAUSE:** A parent thread does not include the model-token usage of its child threads, so the complete cost of a multi-agent run requires explicit hierarchy traversal and aggregation.

- **GOAL: GOAL-2** Preserve exact measurements separately from estimates
  - **SYNOPSIS:** Report recorded token counters and task durations as measured values while labeling inferred phase attribution, tool duration, critical-path duration, and model cost with their confidence and method.
  - **BECAUSE:** Interrupted, resumed, compacted, and reused threads can make semantic allocation less precise than raw thread totals.

- **GOAL: GOAL-3** Reuse the existing report product
  - **SYNOPSIS:** Add native Codex rollout and Junie session ingestion to `tools/report/scripts/run-timeline.py`, its backend-neutral report model, HTML renderer, pricing registry, fixtures, and regression suite.
  - **BECAUSE:** The repository already owns cross-tool timeline reporting and should not create a competing parser, cost model, or user interface.

- **GOAL: GOAL-4** Report durable Junie sessions without parsing terminal presentation
  - **SYNOPSIS:** Detect Junie `events.jsonl` session streams, reconstruct task and custom-agent boundaries, distinguish user tasks from per-agent task spans and model responses, collapse repeated block updates, recognize terminal heredoc file writes, and aggregate recorded model usage and cost.
  - **BECAUSE:** The rendered Junie transcript omits timestamps, full results, and accounting metadata that remain available in the durable session event stream.

- **REQUIREMENT: REQ-1** Support live and sealed reports
  - **SYNOPSIS:** A live report records an observation timestamp and incomplete work; a sealed report fixes the discovered thread set, terminal states, source digests, metrics, and report artifacts for an archived run.
  - **BECAUSE:** Operators need progress visibility during long runs and reproducible evidence after a run finishes.

- **REQUIREMENT: REQ-2** Avoid content collection by default
  - **SYNOPSIS:** The default report reads structural metadata, counters, timestamps, agent paths, tool identifiers, compact tool-argument summaries, and bounded tool-result previews. It redacts secret-shaped values, replaces message-like bodies with character counts except for a secret-redacted 50-character `send_message` preview, replaces recognized encrypted message tokens with an encrypted-message length placeholder, truncates long summaries, and does not copy prompts, reasoning text, unredacted tool payloads, source code, or final document bodies into metrics outputs. Presentation rules operate only on sanitized summaries; collapsed raw disclosures contain bounded redacted content rather than the original payload.
  - **BECAUSE:** Tool names alone do not explain activity, but rollout files can contain private project material and credentials that are unnecessary for usage accounting.

- **RULE: RULE-1** Do not present estimated API-equivalent cost as an actual Codex charge
  - **SYNOPSIS:** Monetary output must distinguish direct recorded cost, model-price estimate, subscription usage with no monetary telemetry, and unavailable cost.
  - **BECAUSE:** Codex Desktop rollout telemetry records token usage, plan type, and rate-limit state but may not record an actual dollar charge or a public price for the active model.

## 2. Technical Directives

These directives shape parsing, aggregation, attribution, and reporting behavior.

- **RULE: RULE-2** Treat each rollout file as one usage-accounting boundary
  - **SYNOPSIS:** The final cumulative `total_token_usage` in one rollout belongs only to that thread; descendant totals must be discovered through `parent_thread_id` and added exactly once.
  - **BECAUSE:** The parent spends tokens processing child messages but does not roll the child model calls into its own cumulative counter.

- **RULE: RULE-3** Use cumulative deltas for response-level usage
  - **SYNOPSIS:** For every distinct monotonic `token_count` snapshot, subtract the preceding snapshot in the same thread to obtain the usage of the newly recorded model response; ignore unchanged duplicate snapshots.
  - **BECAUSE:** `last_token_usage` can be repeated at task boundaries, while cumulative changes provide an exclusive accounting sequence.

- **RULE: RULE-4** Keep cached input as a subset of input
  - **SYNOPSIS:** Compute uncached input as `input_tokens - cached_input_tokens`; calculate total processed tokens as `input_tokens + output_tokens`; treat reasoning tokens as a reported subset of output rather than adding them again.
  - **BECAUSE:** Adding cached input or reasoning output to their parent counters would overstate usage.

- **RULE: RULE-5** Traverse a closed descendant set
  - **SYNOPSIS:** Starting from a selected root thread ID, recursively include sessions whose `parent_thread_id` points to any included session, reject cycles, and exclude siblings and unrelated top-level sessions.
  - **BECAUSE:** Date-based or directory-wide summation can mix concurrent projects and double-count unrelated work.

- **RULE: RULE-6** Preserve raw provenance for every derived metric
  - **SYNOPSIS:** Every response, turn, thread, work-unit, phase, and run record must retain the source rollout path, thread ID, event positions or timestamps, derivation method, and attribution confidence.
  - **BECAUSE:** A report must be auditable when logs are compacted, duplicated, malformed, or still changing.

- **RULE: RULE-7** Prefer explicit work identifiers over text inference
  - **SYNOPSIS:** Future assignments should carry `run_id`, `phase_id`, `lane_id`, `work_unit_id`, and `activity`; legacy logs may infer these values from agent paths and bounded status labels but must mark the result as inferred.
  - **BECAUSE:** Reused agents keep their original `agent_path`, so a thread named for setup may later perform module, architecture, or functional-specification work.

- **RULE: RULE-8** Separate elapsed time from consumed agent time
  - **SYNOPSIS:** Report run wall time, summed agent-turn time, active-interval union, tool time, time to first token, and critical-path time as different metrics.
  - **BECAUSE:** Parallel agents make summed task duration larger than elapsed wall time, and neither number alone describes concurrency.

- **RULE: RULE-9** Make live parsing append-safe
  - **SYNOPSIS:** Tolerate an incomplete final JSONL line, repeated `session_meta`, unchanged token snapshots, active turns without completion, and files that appear while discovery is running.
  - **BECAUSE:** A live report reads logs that Codex is still appending and may discover newly spawned descendants between scans.

- **RULE: RULE-10** Seal immutable evidence before archival pruning
  - **SYNOPSIS:** A sealed report must record source file identifiers, sizes, modification times, digests, parser version, pricing-table version, observation interval, and terminal-state assessment before source runs are pruned.
  - **BECAUSE:** Later comparison requires proof of which telemetry produced the archived metrics.

## 3. Information Model

This model retains exact source measurements and progressively aggregated views.

- **ENTITY: ENTITY-1** Run
  - **SYNOPSIS:** The selected root rollout and its recursively discovered descendants.
  - **FIELD:** `run_id`
    - **SYNOPSIS:** Stable caller-supplied identifier or root thread ID.
  - **FIELD:** `root_thread_id`
    - **SYNOPSIS:** Session ID that anchors descendant discovery.
  - **FIELD:** `state`
    - **SYNOPSIS:** `live`, `complete`, `aborted`, `blocked`, or `sealed`.
  - **FIELD:** `observed_at`
    - **SYNOPSIS:** Timestamp through which the live metrics are known.
  - **FIELD:** `wall_interval`
    - **SYNOPSIS:** Earliest included run event through the latest included event.
  - **FIELD:** `source_manifest`
    - **SYNOPSIS:** Rollout file paths and optional immutable source digests.

- **ENTITY: ENTITY-2** Thread
  - **SYNOPSIS:** One Codex session and its local usage-accounting boundary.
  - **FIELD:** `thread_id`
    - **SYNOPSIS:** Value from the first usable `session_meta.payload.id`.
  - **FIELD:** `parent_thread_id`
    - **SYNOPSIS:** Direct parent used to construct the run hierarchy.
  - **FIELD:** `agent_path`
    - **SYNOPSIS:** Spawn-time role path from `source.subagent.thread_spawn.agent_path`, when present.
  - **FIELD:** `agent_nickname`
    - **SYNOPSIS:** Optional display name from spawn metadata.
  - **FIELD:** `started_at` and `last_observed_at`
    - **SYNOPSIS:** File/event observation bounds for the thread.
  - **FIELD:** `token_totals`
    - **SYNOPSIS:** Final local input, cached input, uncached input, output, reasoning, and total processed tokens.
  - **FIELD:** `terminal_state`
    - **SYNOPSIS:** Complete, aborted, active, or indeterminate based on task events and latest activity.

- **ENTITY: ENTITY-3** Model response usage
  - **SYNOPSIS:** The smallest exclusive token-accounting unit derived from one positive cumulative counter change.
  - **FIELD:** `event_timestamp`
    - **SYNOPSIS:** Timestamp of the cumulative token snapshot.
  - **FIELD:** `usage_delta`
    - **SYNOPSIS:** Input, cached input, uncached input, output, reasoning, and total-token differences from the preceding distinct snapshot.
  - **FIELD:** `model`
    - **SYNOPSIS:** Closest applicable turn or thread model identifier.
  - **FIELD:** `turn_id`
    - **SYNOPSIS:** Exact active turn when unambiguous; otherwise null with reduced confidence.
  - **FIELD:** `source_position`
    - **SYNOPSIS:** Rollout path and line or event ordinal.

- **ENTITY: ENTITY-4** Agent turn
  - **SYNOPSIS:** Work bounded by `task_started` and matching `task_complete` or `turn_aborted` events.
  - **FIELD:** `turn_id`
    - **SYNOPSIS:** Stable task event identifier.
  - **FIELD:** `started_at`, `completed_at`, and `duration_ms`
    - **SYNOPSIS:** Recorded task timing rather than a duration inferred from file modification time.
  - **FIELD:** `time_to_first_token_ms`
    - **SYNOPSIS:** Recorded completion metric when available.
  - **FIELD:** `outcome`
    - **SYNOPSIS:** Complete, aborted, active, or unmatched.
  - **FIELD:** `usage`
    - **SYNOPSIS:** Exclusive response deltas attributed to this turn.
  - **FIELD:** `attribution_confidence`
    - **SYNOPSIS:** `exact`, `bounded`, `inferred`, or `unattributed` with a reason.

- **ENTITY: ENTITY-5** Work unit
  - **SYNOPSIS:** A module, document, review, correction, verification task, or named batch such as `M-011` or `M-011–M-015`.
  - **FIELD:** `work_unit_id`
    - **SYNOPSIS:** Explicit stable identifier when supplied; otherwise an inferred label with provenance.
  - **FIELD:** `activity`
    - **SYNOPSIS:** Author, review, correct, integrate, verify, orchestrate, or other caller-defined activity.
  - **FIELD:** `turn_ids`
    - **SYNOPSIS:** Turns whose exclusive metrics roll into the work unit.
  - **FIELD:** `allocation_method`
    - **SYNOPSIS:** Exact one-turn ownership, explicit multi-turn mapping, equal batch split, size-weighted estimate, activity-weighted estimate, or unavailable.

- **ENTITY: ENTITY-6** Phase and lane
  - **SYNOPSIS:** Caller-defined aggregation boundaries such as configuration, Pass 0 inventory, module design, HLD, architecture, functional specifications, wiki integration, reconstruction, and verification.
  - **FIELD:** `phase_id` and `lane_id`
    - **SYNOPSIS:** Stable identifiers supplied by orchestration metadata or inferred with confidence.
  - **FIELD:** `work_unit_ids`
    - **SYNOPSIS:** Units included exactly once in this aggregation.
  - **FIELD:** `wall_interval`, `active_interval_union`, and `agent_time`
    - **SYNOPSIS:** Distinct concurrency-aware time views.
  - **FIELD:** `usage_totals`
    - **SYNOPSIS:** Sum of exclusive work-unit metrics.

- **ENTITY: ENTITY-7** Cost assessment
  - **SYNOPSIS:** Monetary status plus an optional API-equivalent USD estimate for one aggregation unit.
  - **FIELD:** `status`
    - **SYNOPSIS:** `recorded`, `estimated`, `subscription-no-charge-data`, or `unavailable`.
  - **FIELD:** `pricing_model` and `pricing_version`
    - **SYNOPSIS:** Exact model key and pricing-registry version used for an estimate.
  - **FIELD:** `input_cost`, `cached_input_cost`, and `output_cost`
    - **SYNOPSIS:** Separately calculated components; reasoning is not charged twice when it is included in output.
  - **FIELD:** `total_cost`
    - **SYNOPSIS:** Sum of available cost components with currency and estimate label.
  - **RULE:** Reports do not derive or display Codex credit estimates because rollout telemetry does not establish a run-specific credit charge or balance.

## 4. Structure And Execution

The component extends the existing reporter with a native rollout source adapter and hierarchical aggregation pipeline.

```mermaid
flowchart LR
  A[Codex root or Junie session path] --> B[Source detection]
  B --> C[Native runtime parser]
  C --> D[Exclusive response usage]
  C --> E[Turns and tool intervals]
  D --> F[Thread totals]
  E --> G[Work-unit attribution]
  F --> H[Run hierarchy aggregation]
  G --> H
  H --> I[Pricing assessment]
  H --> J[Time and concurrency assessment]
  I --> K[JSON, CSV, Markdown, and HTML reports]
  J --> K
```

- **MODULE: MODULE-1** Codex rollout source adapter
  - **SYNOPSIS:** Detect and parse native Codex Desktop rollout JSONL without changing the existing prompt-runner Codex parser.
  - **READS:** `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` or caller-supplied session roots.
  - **PRODUCES:** Normalized session metadata, response usage events, task events, tool call/result intervals, model context, and parse diagnostics.
  - **VALIDATES:** JSON shape by feature detection rather than assuming every Codex version exposes every field.

- **MODULE: MODULE-2** Session hierarchy resolver
  - **SYNOPSIS:** Index sessions by ID, connect parent and child sessions, and return the closed descendant set for one selected root.
  - **CHECKS-FILE:** First usable `session_meta` record in each candidate rollout.
  - **VALIDATES:** Unique session ownership, missing parents, duplicate IDs, cycles, unreadable files, and unrelated siblings.
  - **PRODUCES:** Ordered thread nodes plus hierarchy diagnostics.

- **MODULE: MODULE-2A** Junie session source adapter
  - **SYNOPSIS:** Detect a Junie session directory or `events.jsonl`, map sequential task boundaries, and reconstruct main/custom-agent ownership from recorded agent identities and custom-agent model intervals.
  - **READS:** `~/.junie/sessions/session-*/events.jsonl` or a caller-supplied equivalent path.
  - **PRODUCES:** Normalized agent threads, unique user tasks, per-agent task spans, response usage, recorded costs, deduplicated tool intervals, terminal heredoc write targets, bounded result previews, and parser diagnostics.
  - **VALIDATES:** Required event shapes, task completion, agent identity, model-usage counters, repeated `stepId` updates, heredoc boundaries, and incomplete live streams.

- **MODULE: MODULE-3** Usage normalizer
  - **SYNOPSIS:** Convert cumulative token snapshots into exclusive response deltas and reconcile them with final thread totals.
  - **VALIDATES:** Monotonic counters, duplicate snapshots, counter resets, negative deltas, missing categories, and final-sum equality.
  - **PRODUCES:** Exact per-response and per-thread usage plus an unattributed remainder when reconciliation cannot be exact.

- **MODULE: MODULE-4** Turn and work-unit attribution engine
  - **SYNOPSIS:** Associate exclusive response deltas and task timing with turns, then map turns to explicit or inferred work units.
  - **USES:** Event order, task IDs, turn context, assignment metadata, bounded completion labels, and agent paths.
  - **VALIDATES:** Overlapping active turns, repeated starts, missing completions, abort/resume sequences, compacted history, and stale agent names.
  - **PRODUCES:** Attribution records with confidence and explanation; it never silently forces ambiguous usage into a named module.

- **MODULE: MODULE-5** Time and concurrency calculator
  - **SYNOPSIS:** Produce distinct elapsed, consumed, tool, and concurrency-aware time measures.
  - **USES:** Task payload timestamps and durations, rollout timestamps, tool-reported `wall_time_seconds`, and matched call/result timestamps.
  - **PRODUCES:** Run wall time, summed agent time, interval-union active time, peak concurrency, time to first token, tool time, and best-evidence critical path.
  - **GAP:** A dependency-accurate critical path is unavailable when logs do not identify the work-unit handoff that unblocked downstream work; report observed elapsed time and mark the critical path inferred in that case.

- **MODULE: MODULE-6** Cost assessor
  - **SYNOPSIS:** Reuse `docs/reference/openai-model-pricing.json` for optional API-equivalent USD and Codex credit estimates while preserving unavailable actual-charge status.
  - **READS:** Normalized model IDs and aliases, token categories, provider pricing entries, Codex credit entries, pricing effective date, and any direct cost field a source exposes.
  - **PRODUCES:** Component and total USD estimates, optional credit estimates, formula, model mapping, currency, and pricing version.
  - **GAP:** Internal or subscription-only model identifiers may have no supported price; those rows remain unavailable rather than being mapped to a convenient public model.

- **MODULE: MODULE-7** Report integration
  - **SYNOPSIS:** Feed normalized metrics into the existing timeline report model and renderer while adding hierarchy and confidence views.
  - **PRODUCES:** Interactive HTML with a new-tab model-rate reference and nested per-agent and per-turn tool-call drilldowns, machine-readable JSON, turn-oriented CSV, work-unit cost CSV, and compact Markdown summary with the same rates.
  - **SUPPORTS:** Live refresh and sealed archive generation from the same normalized data model.

- **PROCESS: PROCESS-1** Discover and parse a run
  - **SYNOPSIS:** Resolve the selected root, index candidate rollout files, traverse descendants, parse each file once, and record all parse gaps.
  - **VALIDATES:** The root exists and every included thread is connected to it.
  - **PRODUCES:** A normalized live run snapshot.

- **PROCESS: PROCESS-2** Reconcile usage
  - **SYNOPSIS:** Derive response deltas, sum them to thread totals, sum each included thread once to the run total, and expose any remainder.
  - **VALIDATES:** `run total = sum(final local thread totals)` and `thread total = response deltas + explicit unattributed remainder`.
  - **BECAUSE:** These equalities prevent parent/child rollup assumptions and duplicated token events from inflating totals.

- **PROCESS: PROCESS-3** Attribute semantic work
  - **SYNOPSIS:** Apply explicit identifiers first, then exact turn ownership, then bounded inference; leave unresolved work unattributed.
  - **PRODUCES:** Phase, lane, work-unit, and activity summaries with confidence distribution.
  - **BECAUSE:** An incomplete semantic breakdown is more trustworthy than a complete-looking allocation built from stale thread names.

- **PROCESS: PROCESS-4** Calculate optional cost
  - **SYNOPSIS:** Multiply uncached input, cached input, and output by matching per-million USD and Codex-credit rates when supported; prefer direct cost if the source records it.
  - **PRODUCES:** Recorded or estimated USD, optional credit consumption, and explicit subscription or unavailable states at turn, agent, work-unit, phase, and run levels.

- **PROCESS: PROCESS-5** Seal a completed report
  - **SYNOPSIS:** Re-scan until the descendant set and source sizes are stable, reject active or indeterminate threads unless the caller explicitly seals an aborted run, write source digests and report artifacts, then mark the snapshot sealed.
  - **BECAUSE:** A live snapshot can change after it is rendered and is not sufficient archival evidence.

- **COMMAND: CMD-1** Extend the timeline reporter CLI
  - **SYNOPSIS:** Add a native rollout input form such as `--codex-thread THREAD_ID` with optional `--sessions-root`, `--live`, `--seal`, and machine-output flags while preserving existing path-based prompt-runner and methodology-runner behavior.
  - **PRODUCES:** The same HTML report entry point plus optional JSON, CSV, and Markdown companions.

- **FILE: FILE-1** Component design authority
  - **SYNOPSIS:** `docs/design/components/CD-001-codex-rollout-metrics.md` defines the ingestion and aggregation contract.

- **FILE: FILE-2** Existing reporter implementation
  - **SYNOPSIS:** `tools/report/scripts/run-timeline.py` remains the reporting implementation and CLI entry point.

- **FILE: FILE-3** Reporter regression suite
  - **SYNOPSIS:** `tools/report/tests/test_run_timeline.py` and sanitized fixtures verify existing and native-rollout inputs.

- **FILE: FILE-4** Pricing registry
  - **SYNOPSIS:** `docs/reference/openai-model-pricing.json` supplies versioned estimate rates without implying an actual Codex subscription charge.

- **FILE: FILE-5** Prior reporting plan
  - **SYNOPSIS:** `docs/superpowers/plans/2026-04-11-codex-timeline-reporting.md` records the earlier prompt-runner Codex integration and remains historical context rather than the authority for native Desktop rollout hierarchy.

## 5. Constraints

These constraints prevent inaccurate accounting and unsafe report artifacts.

- **RULE: RULE-11** Maintain backward compatibility
  - **SYNOPSIS:** Existing Claude, prompt-runner Codex, and methodology-runner reports and fixtures must retain their current behavior unless a separately approved schema migration changes them.
  - **BECAUSE:** Native Desktop rollout support is an additional source adapter, not a replacement for established run formats.

- **RULE: RULE-12** Never double-count hierarchy or category subsets
  - **SYNOPSIS:** Include each thread once, cached input only inside input, reasoning only inside output, each response delta once, and each work unit once per requested aggregation.
  - **BECAUSE:** Hierarchical and subset counters are the primary sources of convincing but incorrect totals.

- **RULE: RULE-13** Keep raw logs outside reports by default
  - **SYNOPSIS:** Store source paths and digests rather than embedding rollout JSONL; redact or hash optional labels when privacy mode is selected.
  - **BECAUSE:** Reports are likely to be shared more broadly than the source project and agent transcripts.

- **RULE: RULE-14** Bound source discovery
  - **SYNOPSIS:** Search only configured session roots and dates needed to resolve the selected hierarchy; do not scan unrelated home-directory content.
  - **BECAUSE:** Session roots may contain many concurrent projects and sensitive conversations.

- **RULE: RULE-15** Surface schema drift
  - **SYNOPSIS:** Unknown event types are counted and retained in diagnostics; missing optional fields degrade features; missing identity or usage fields fail only the affected accounting boundary.
  - **BECAUSE:** Codex rollout telemetry is a runtime format that may change independently of this repository.

- **RULE: RULE-16** Distinguish measured, derived, inferred, and unavailable values
  - **SYNOPSIS:** Every output field carries or inherits a provenance class, and user-facing totals show the share of usage that lacks exact semantic attribution.
  - **BECAUSE:** Consumers need to know which comparisons can support optimization decisions.

- **RULE: RULE-17** Do not split batch cost into modules without an allocation declaration
  - **SYNOPSIS:** A five-module turn remains one batch unless explicit work-unit events identify module boundaries; optional equal, document-size, or activity-weighted splits are labeled estimates.
  - **BECAUSE:** File count or output size alone does not reveal how much model reasoning each module required.

- **RULE: RULE-18** Use immutable pricing inputs for sealed reports
  - **SYNOPSIS:** A sealed estimate records the selected pricing entry and digest rather than silently changing when the shared registry is updated.
  - **BECAUSE:** Historical costs must remain reproducible.

## 6. Definition Of Good

These conditions define an acceptable implementation and report.

- **REQUIREMENT: REQ-3** Exact subtree accounting
  - **SYNOPSIS:** The report identifies the selected root and every reachable descendant, excludes unrelated sessions, and reconciles the run total to the sum of local thread totals with no unexplained duplication.
  - **BECAUSE:** The complete multi-agent run is the primary reporting boundary.

- **REQUIREMENT: REQ-4** Useful finest-grain evidence
  - **SYNOPSIS:** Users can inspect response deltas, agent turns, individual matched tool calls, threads, work units, phases, and the whole run, with provenance and confidence at every level.
  - **BECAUSE:** Aggregate totals alone do not reveal which work consumed resources.

- **REQUIREMENT: REQ-5** Honest time reporting
  - **SYNOPSIS:** The report displays wall time and summed agent time together, explains concurrency, and does not label either one as the other.
  - **DISPLAYS:** Human-readable durations below one hour use minutes and seconds; durations of one hour or more use hours, minutes, and seconds.
  - **BECAUSE:** A run can consume many agent-hours while finishing in a shorter elapsed interval.

- **REQUIREMENT: REQ-6** Honest cost reporting
  - **SYNOPSIS:** Direct cost, API-equivalent USD, Codex credit estimates, subscription usage, and unavailable pricing are visually and structurally distinct.
  - **DISPLAYS:** Human-readable cost values use two decimal places; the execution timeline shows each turn estimate and the owning agent total calculated with that agent's model; repeated table cells show compact values while the estimate disclaimer appears once at run level.
  - **BECAUSE:** Token telemetry is sufficient for some estimates but not proof of an actual charge.

- **REQUIREMENT: REQ-7** Live report stability
  - **SYNOPSIS:** Repeated live scans are idempotent for unchanged events, append new events once, show active work, and never require a complete final JSONL line.
  - **BECAUSE:** Long-running multi-agent tasks need trustworthy progress snapshots.

- **REQUIREMENT: REQ-8** Sealed report reproducibility
  - **SYNOPSIS:** Reprocessing the sealed source manifest with the recorded parser and pricing versions yields the same normalized metrics and cost estimate.
  - **BECAUSE:** Archived runs must remain comparable after tooling changes.

- **REQUIREMENT: REQ-9** Current-run validation target
  - **SYNOPSIS:** A fixture modeled on the observed run-02 hierarchy must prove that a parent total smaller than the sum of child totals produces a larger subtree total without treating the parent as a rollup.
  - **BECAUSE:** The observed live run demonstrated this exact accounting boundary and provides a concrete regression case.

- **REQUIREMENT: REQ-10** Configurable tool-argument presentation
  - **SYNOPSIS:** The HTML renderer evaluates ordered, versioned formatter rules against sanitized tool-argument summaries, displays the first matching human-readable summary, and retains a collapsed sanitized `raw` disclosure. A caller may supply a run-specific config with `--formatter-config`.
  - **BECAUSE:** Claims, patches, messages, waits, and agent lifecycle calls repeat recognizable structures that are easier to scan when reduced to their meaningful fields, while a config lets an agent describe new run-specific patterns without changing parser code.

## 7. Test Cases

These cases verify parsing, accounting, attribution, concurrency, privacy, and compatibility.

- **TASK: TEST-1** Parse one completed thread
  - **SYNOPSIS:** Load a sanitized rollout with cumulative usage and one completed task.
  - **VALIDATES:** Exact response deltas, final thread total, duration, time to first token, and terminal state.

- **TASK: TEST-2** Aggregate a parent and multiple descendants
  - **SYNOPSIS:** Build a root with direct and nested children plus an unrelated sibling.
  - **VALIDATES:** Recursive inclusion, sibling exclusion, each-thread-once accounting, and subtree total equality.

- **TASK: TEST-3** Reject parent rollup assumptions
  - **SYNOPSIS:** Use a parent total lower than the combined child totals.
  - **VALIDATES:** The report adds the parent and children instead of selecting the parent or subtracting descendants from it.

- **TASK: TEST-4** Reconcile cached and reasoning subsets
  - **SYNOPSIS:** Provide input with a cached subset and output with a reasoning subset.
  - **VALIDATES:** Correct uncached input, total processed tokens, and no subset double-counting.

- **TASK: TEST-5** Ignore duplicate token snapshots
  - **SYNOPSIS:** Repeat unchanged cumulative and `last_token_usage` events around task completion.
  - **VALIDATES:** One exclusive response delta and unchanged final total.

- **TASK: TEST-6** Handle compaction and repeated metadata
  - **SYNOPSIS:** Include repeated `session_meta`, `turn_context`, compacted markers, and replayed fork history.
  - **VALIDATES:** Stable thread identity, no duplicate historical task accounting, and preserved diagnostics.

- **TASK: TEST-7** Handle interrupted and resumed work
  - **SYNOPSIS:** Include overlapping starts, an abort, a follow-up turn, and one stale unmatched start.
  - **VALIDATES:** Exact thread total, bounded turn attribution, explicit unattributed remainder, and no forced semantic allocation.

- **TASK: TEST-8** Handle reused agent threads
  - **SYNOPSIS:** Reuse a setup-named agent for module and functional work with explicit work-unit identifiers.
  - **VALIDATES:** Phase allocation follows explicit identifiers rather than stale `agent_path`.

- **TASK: TEST-9** Estimate supported model cost
  - **SYNOPSIS:** Map uncached input, cached input, and output to versioned provider and Codex rate-card entries.
  - **VALIDATES:** Component calculations, per-million conversion, currency, credit estimate, estimate labels, per-turn and per-agent execution-timeline totals, pricing table rendering, and pricing digest.

- **TASK: TEST-10** Refuse unsupported model pricing
  - **SYNOPSIS:** Use an internal model identifier absent from the registry and a Pro subscription rate-limit record with null credits.
  - **VALIDATES:** Token and time reporting continue while monetary status remains unavailable or subscription-no-charge-data.

- **TASK: TEST-11** Distinguish wall and agent time
  - **SYNOPSIS:** Run two overlapping child task intervals under one parent.
  - **VALIDATES:** Wall interval, interval union, peak concurrency, and summed agent time are all different and correctly labeled.

- **TASK: TEST-12** Parse a changing live file
  - **SYNOPSIS:** Read a fixture ending in partial JSON, append completion and a newly spawned child, then rescan.
  - **VALIDATES:** Append safety, idempotency, active-state reporting, and descendant discovery.

- **TASK: TEST-13** Seal and reproduce a report
  - **SYNOPSIS:** Seal a stable completed hierarchy, record source and pricing digests, and regenerate from the sealed manifest.
  - **VALIDATES:** Byte-stable normalized metrics and equal rendered totals.

- **TASK: TEST-14** Preserve existing report backends
  - **SYNOPSIS:** Run the complete existing report fixture suite after native rollout support is added.
  - **VALIDATES:** Claude, prompt-runner Codex, and methodology-runner behavior remains compatible.

- **TASK: TEST-15** Enforce privacy defaults
  - **SYNOPSIS:** Include sensitive prompt, reasoning, tool payload, final-message text, and a secret-shaped `send_message` assignment in test inputs.
  - **VALIDATES:** Default JSON, CSV, Markdown, and HTML outputs contain metrics, provenance, useful redacted tool-argument summaries, and only bounded redacted tool results; `send_message` exposes only its redacted 50-character preview and original character count, while recognized encrypted messages expose only an encrypted-message length placeholder.

- **TASK: TEST-16** Open agent and turn tool-call drilldowns
  - **SYNOPSIS:** Expand an agent in the execution timeline, open its turn list, and select one turn for a focused view of that turn's metrics, attribution, and ordered tool calls.
  - **VALIDATES:** The agent assignment appears in the agent overlay title without a redundant table column; turn links work from both the agent overlay and execution table; the turn overlay shows identity, timing, state, token count, work attribution, each tool call's run-relative offset, name, redacted argument summary, and bounded result preview. Recognized calls use the configured summary plus collapsed sanitized argument and result disclosures. The normal matched-event timing bound is silent and exceptional timing provenance is called out.

- **TASK: TEST-17** Parse a native Junie session
  - **SYNOPSIS:** Build a synthetic session with a main agent, custom agent, repeated terminal updates, file reads, terminal heredoc writes, per-model token metadata, recorded cost, and secret-shaped command output.
  - **VALIDATES:** The adapter detects the session, assigns custom-agent model usage correctly, collapses tool updates by `stepId`, separates one user task from two agent task spans, exposes created file paths without treating heredoc body examples as commands, reports recorded cost, preserves task completion, and excludes the secret value from HTML.

## 8. Proposed Modifications

This section records the implementation surfaces implied by the design without claiming they are already applied.

- **MODIFICATION: MOD-1** Add native rollout parsing to the report tool
  - **SYNOPSIS:** Introduce backend detection, session discovery, normalized rollout parsing, and hierarchy aggregation behind the existing report CLI.
  - **STATUS:** proposed

- **MODIFICATION: MOD-2** Add hierarchy and attribution views
  - **SYNOPSIS:** Extend the report model and renderer with parent/child threads, confidence, unattributed usage, phase/lane/work-unit summaries, and concurrency-aware time.
  - **STATUS:** proposed

- **MODIFICATION: MOD-3** Add machine-readable companions
  - **SYNOPSIS:** Emit normalized JSON, turn timeline CSV, work-unit allocation CSV, and Markdown summary alongside HTML when requested.
  - **STATUS:** proposed

- **MODIFICATION: MOD-4** Add sealed-run evidence
  - **SYNOPSIS:** Record rollout and pricing source manifests with digests and parser version for archived reports.
  - **STATUS:** proposed

- **MODIFICATION: MOD-5** Add sanitized native-rollout fixtures
  - **SYNOPSIS:** Cover hierarchy, cumulative token semantics, duplicate events, compaction, interruption, active logs, reused threads, pricing gaps, concurrency, and privacy.
  - **STATUS:** proposed
