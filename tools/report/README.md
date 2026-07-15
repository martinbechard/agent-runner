# report

`tools/report/` holds cross-tool reporting utilities for this repository.

Current contents:

- `scripts/run-timeline.py`
  - generates an HTML timeline report from a `prompt-runner` run directory or
    a `methodology-runner` workspace
  - reports a native Codex Desktop root rollout and its closed descendant set
    from a thread ID or rollout path
  - emits privacy-safe JSON, turn CSV, work-unit CSV, Markdown, and HTML
    companions, with reproducible source and pricing digests for sealed runs
- `tests/`
  - regression tests and fixtures for the report script

Run the timeline tool directly from the checkout:

```bash
python tools/report/scripts/run-timeline.py <path> [--output report.html]
```

Report a live Codex Desktop hierarchy without copying prompt, reasoning, raw
tool results, or final-message content into the report. `send_message` argument
summaries include a secret-redacted 50-character message preview followed by
the original character count; other message-like bodies remain count-only:

```bash
python tools/report/scripts/run-timeline.py \
  --codex-thread <root-thread-id> \
  --sessions-root ~/.codex/sessions \
  --live \
  --output codex-run.html
```

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
