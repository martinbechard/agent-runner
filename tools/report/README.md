# report

`tools/report/` holds cross-tool reporting utilities for this repository.

Current contents:

- `tool-formatters.json`
  - defines first-match formatting rules for recurring native Codex tool
    argument patterns
  - extracts display fields from sanitized JSON summaries or bounded regular
    expressions without changing the underlying privacy filter
- `scripts/run-timeline.py`
  - generates an HTML timeline report from a `prompt-runner` run directory or
    a `methodology-runner` workspace
  - reports a native Codex Desktop root rollout and its closed descendant set
    from a thread ID or rollout path
  - reports a native Junie session from its session directory or
    `events.jsonl` path
  - emits privacy-safe JSON, turn CSV, work-unit CSV, Markdown, and HTML
    companions, with reproducible source and pricing digests for sealed runs
- `tests/`
  - regression tests and fixtures for the report script

Run the timeline tool directly from the checkout:

```bash
python tools/report/scripts/run-timeline.py <path> [--output report.html]
```

Report a live Codex Desktop hierarchy with lifecycle rows for input ingestion,
model usage, available reasoning summaries, tool execution, and output
generation. Plaintext input, reasoning summaries, and assistant output use
bounded, secret-redacted raw disclosures. Encrypted reasoning is identified by
size but remains opaque. Tool results use bounded previews and a collapsed,
secret-redacted raw disclosure. `send_message` argument
summaries include a secret-redacted 50-character message preview followed by
the original character count. Recognized encrypted message tokens are replaced
with an `[encrypted message, N chars]` placeholder instead of previewing
ciphertext; other message-like bodies remain count-only.
Matched tool calls show a concise formatted summary and a collapsed `raw`
disclosure containing the unformatted, sanitized argument summary:

```bash
python tools/report/scripts/run-timeline.py \
  --codex-thread <root-thread-id> \
  --sessions-root ~/.codex/sessions \
  --live \
  --output codex-run.html
```

The default formatter config recognizes patches, agent claims, inter-agent
messages, agent lifecycle calls, and waits. Rules are evaluated in file order.
A rule may match the tool name plus a bounded regular expression, then extract
display fields from named regex groups or dotted JSON paths. Retain the
generated config with a run when an agent creates run-specific rules after
analyzing its sanitized argument summaries:

```bash
python tools/report/scripts/run-timeline.py \
  --codex-thread <root-thread-id> \
  --sessions-root ~/.codex/sessions \
  --live \
  --formatter-config path/to/tool-formatters.json \
  --output codex-run.html
```

Formatter configs affect HTML presentation only. They never receive unsanitized
payloads. Result previews and disclosures pass through the separate result
redactor and size boundary.

Report a Junie session directly from its durable event stream:

```bash
python tools/report/scripts/run-timeline.py \
  ~/.junie/sessions/session-YYMMDD-HHMMSS-ID \
  --output junie-run.html
```

Junie reports collapse repeated block updates by `stepId`, reconstruct the main
and custom-agent hierarchy, associate events with task boundaries, preserve
terminal success and failure states, and aggregate Junie's per-response token
and cost metadata. The summary distinguishes unique user tasks, per-agent task
spans, and model responses; delegated tasks therefore count once as a user task
but once for every participating agent. Terminal heredoc writes such as
`cat > docs/wiki/index.md` are identified as `write_files` activity with the
created paths instead of being buried inside a truncated shell command.
Terminal output and other available results use the same bounded, redacted
preview and raw-disclosure treatment as Codex tool results.
Junie does not record a model API time-to-first-token measurement, so that
field remains unavailable rather than being inferred from unrelated events.

Seal a stable completed hierarchy. Sealing writes HTML plus normalized JSON,
turn CSV, work-unit CSV, and Markdown files using the output stem:

```bash
python tools/report/scripts/run-timeline.py \
  --codex-thread <root-thread-id> \
  --sessions-root ~/.codex/sessions \
  --seal \
  --output codex-run.html
```

Use `--seal-aborted` only when an aborted run is intentionally the archival
boundary. A sealed JSON companion can later be passed as `<path>` to validate
its source digests and reproduce the normalized report.

Native Codex reports normalize both ISO and Unix-epoch turn timestamps. Spawned
rollouts replay a cumulative parent prefix; the parser excludes that prefix at
the first child trigger boundary so descendant totals contain only usage owned
by the selected hierarchy. Unowned response deltas remain visible in an
`unattributed` work unit and phase so every aggregate reconciles to the run
total.

The native HTML report reuses the methodology timeline's drill-down approach
without copying transcript content. It includes token composition, observed
thread bars, an agent inventory derived from recorded assignment paths and
runtime nicknames, expandable per-turn duration and time-to-first-token rows,
input/cache/output/reasoning counters, and tool-name/count/duration summaries.
The Markdown companion includes matching agent and work-unit breakdowns.

When explicit work-unit metadata is absent, the report uses the final semantic
segment of the agent path and marks the result as inferred. Phase and lane stay
`unattributed` when the rollout did not record them. A completed root with one
or more aborted descendants is reported as `complete-with-aborted-children`,
distinct from an aborted root.

Cost labels distinguish API-equivalent estimates from actual charges. If a
Codex subscription model has no supported price, token and time metrics remain
available while monetary status is reported as unavailable or subscription
usage without charge telemetry.

Run its tests:

```bash
pytest -q tools/report/tests/test_run_timeline.py
```
