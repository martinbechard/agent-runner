# report

`tools/report/` holds cross-tool reporting utilities for this repository.

Current contents:

- `rust/agent-report-core/`
  - streams Codex rollout identity, title, workspace, and delegation metadata
    through bounded native workers
  - owns stable fingerprint checks and the incremental SQLite discovery index
  - is linked directly by the desktop application
- `rust/agent-report-cli/`
  - exposes the native core through the versioned `agent-report-engine index`
    JSON standard-I/O protocol used by the Python renderer
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
  - renders an offline agent sequence view for recorded delegations,
    inter-agent messages, lifecycle controls, and native subagent endings;
    model usage keeps different reasoning-effort levels in separate groups
  - reports a native Junie session from its session directory or
    `events.jsonl` path
  - emits privacy-safe JSON, turn CSV, work-unit CSV, Markdown, and HTML
    companions, with reproducible source and pricing digests for sealed runs
- `tests/`
  - regression tests and fixtures for the report script
- `desktop/`
  - provides the Tauri run index, native progress, virtualized local search,
    privacy-bounded catalog export, and selected full-report generation

The two products share one discovery engine:

```mermaid
flowchart LR
  A[Local Codex JSONL stores] --> B[Rust discovery and SQLite index]
  B --> C[agent-report-engine protocol]
  C --> D[Python normalization and offline report renderer]
  B --> E[Tauri local run index]
  E --> D
```

Build the required native engine before running the report directly from a
source checkout:

```bash
cargo build \
  --manifest-path tools/report/Cargo.toml \
  --release \
  -p agent-report-engine
```

Run the timeline tool directly from the checkout:

```bash
python tools/report/scripts/run-timeline.py <path> [--output report.html]
```

Install the wheel attached to the GitHub release and run the same tool as an
installed command. Release wheels are platform-specific because they include
the required native engine:

```bash
python -m pip install \
  https://github.com/martinbechard/agent-runner/releases/download/agent-report-v0.8.0/agent_report-0.8.0-py3-none-macosx_11_0_arm64.whl
agent-report <path> --output report.html
```

Build a platform wheel locally with:

```bash
cd tools/report
python -m build --wheel
```

The wheel build fails if Rust cannot build `agent-report-engine`; it never
emits a Python-only package with different discovery behavior.

### GitHub Release publication

Agent Report wheels are published only through GitHub Releases. Pushing an
`agent-report-vVERSION` tag runs `.github/workflows/release-agent-report.yml`.
The tag must exactly match the version in `tools/report/pyproject.toml`.

The workflow builds and tests one platform wheel on each supported target:

- Linux x64
- Windows x64
- Apple Silicon macOS

Every build compiles the Rust parser for its runner, verifies that the wheel is
platform-specific, confirms that both report commands and all runtime resources
are present, installs the completed wheel, and runs the report regression
suite. The GitHub Release is created only after all three jobs pass. It contains
the three wheels and a `SHA256SUMS` file. Intel macOS wheels and Python-only
wheels are not published.

After synchronizing all Agent Report version files and committing the release
candidate, publish it with:

```bash
git tag agent-report-vVERSION
git push origin agent-report-vVERSION
```

## MCP server

The platform wheel also installs `mcp-agent-report`, a FastMCP stdio server
with `generate_report`, `query_time_range`, and `get_event_details` operations.
`generate_report` selects a Codex task by
exact thread ID or by an ISO 8601 half-open time range and case-insensitive task
name substrings. It writes one coherent report snapshot using these stable
filenames:

```text
report.html
report.json
turns.csv
work-units.csv
report.md
```

Without an explicit output directory, the bundle is written to
`.codex/report` under the first local workspace root advertised by the MCP
client, then the configured workspace root, then the server working directory.
`output_path` is always a directory. Set `return_via_mcp` to return one complete
HTML, Markdown, or JSON representation inline as well. Inline content is never
truncated.

`query_time_range` returns structured telemetry for one exact `thread_id`.
Use optional ISO 8601 `from_time` and `to_time` values to restrict the task
range. Offset-free values use the configured server timezone. Select a
`bucket_minutes` value of 1, 5, 15, 30, or 60. Select one of these measures:

- `wall_time`
- `uncached_input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `reasoning_tokens`
- `cost_usd`

Wall-time queries return one series for each runtime activity. Token and cost
queries return one series for each agent. Each series contains values aligned
with the top-level `buckets` array. Set `include_events` to include event
evidence from the selected range. Event responses are limited to 1,000 items.
Use `event_count` and `events_truncated` to detect when a narrower query is
required. Each event includes a deterministic opaque `event_id`.

Pass the exact `thread_id` and an `event_id` to `get_event_details`. The tool
rebuilds the current task snapshot and returns the full privacy-safe event
record. Tool events can include bounded, secret-redacted arguments and results.
Model events include usage, cost, timing, and available activity context. An ID
can become unavailable if the underlying live task changes after the range
query; repeat `query_time_range` to refresh the event IDs.

Configure server-owned paths and limits in the MCP host environment:

```json
{
  "mcpServers": {
    "mcp-agent-report": {
      "command": "/absolute/path/to/mcp-agent-report",
      "env": {
        "AGENT_REPORT_SESSIONS_ROOTS": "/Users/example/.codex/sessions",
        "AGENT_REPORT_DEFAULT_OUTPUT": ".codex/report",
        "AGENT_REPORT_WORKSPACE_ROOT": "/Users/example/workspace",
        "AGENT_REPORT_TIMEZONE": "America/Toronto",
        "AGENT_REPORT_MAX_INLINE_BYTES": "65536"
      }
    }
  }
}
```

Separate multiple session roots with the platform path separator. Omit
`AGENT_REPORT_SESSIONS_ROOTS` to use `~/.codex/sessions`; include both the
active and archived paths in the variable to search both stores. The inline
limit defaults to 65,536 UTF-8 bytes and cannot be configured above that value.
At startup, the server validates these settings and probes the bundled Rust
engine's expected discovery protocol. It never downloads or compiles an engine
during a tool call.

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

The generated HTML files open directly from disk and do not require a web
server. The timeline remains the primary view. **Sequence window** near the top
opens the separately generated `*-sequence.html` companion, so the main report
does not load or parse the large diagram payload. In the desktop application,
that link is admitted as a separate native window only when it targets the
matching local sequence companion. The sequence reads downward through recorded
delegation, spawn, message, follow-up, interrupt, child-ending events, and
available reasoning summaries. Its standalone controls provide zoom and fit,
hierarchy collapse, agent focus, event filters, and reversible grouping of
consecutive repeated messages. Long prompt-derived report headings are bounded
for display, while long task labels in report tables retain their full text
behind the shared **more** disclosure.

Each distinct plaintext reasoning fragment appears as an optional conversation
bubble on its agent lifeline. Repeated text keeps only its latest occurrence;
successive fragments remain visible in chronological order and are centered
between the surrounding communication rows. Opaque or encrypted reasoning
produces no bubble. Bubble text is compacted for oversight and stripped of
Markdown emphasis; selecting a bubble opens its longer bounded, secret-redacted
text immediately. The **Thinking** filter hides or restores bubbles without
moving or restyling the event arrows. Select an arrow endpoint or
event-ledger row to open the full, untruncated recorded event label. Solid
arrows show dispatch or control traffic, dashed return arrows show native
subagent endings, and the ledger preserves the exact chronological event rows
in accessible text.

Codex stores some native inter-agent message arguments as ciphertext. The
report does not decrypt or expose that payload. When the receiving task has a
nearby plaintext update, the arrow indicates that context is available and the
event panel labels it as the recipient's next update rather than as recovered
message text.

Some coordinators dispatch work into separate root tasks with
`<codex_delegation>` records. Add `--include-delegations` to follow those
outbound links and include each linked task's native subagent hierarchy.
Repeat `--sessions-root` when the connected graph spans the active and archived
stores:

```bash
python tools/report/scripts/run-timeline.py \
  --codex-thread <coordinator-thread-id> \
  --sessions-root ~/.codex/sessions \
  --sessions-root ~/.codex/archived_sessions \
  --include-delegations \
  --live \
  --output codex-sequence.html
```

When `--include-delegations` is used without explicit session roots, the tool
scans both default Codex stores automatically.

Single-report Codex discovery keeps a local metadata index at
`~/.codex/agent-report/rollout-discovery-v2.sqlite3`. The native index stores
only rollout identity, hierarchy, stable file fingerprints, bounded title and
workspace metadata, and delegation source IDs; it does not store transcript
content. A bounded producer-consumer pipeline streams changed files in
parallel, restores input order, and writes stable changes through one SQLite
transaction. Unchanged logs are reused, while appended, truncated, replaced,
or live-changing logs are handled individually. An unavailable engine or
index is an explicit error: there is no Python discovery fallback. Deleting
the index is safe and causes the next report to rebuild it from the source
logs.

Set `AGENT_REPORT_ENGINE` only when selecting a development or separately
installed native executable. Installed wheels configure their bundled engine
automatically.

## Desktop run index

The desktop application searches selected Codex stores locally and keeps the
large generated report out of its index webview. It virtualizes run rows,
shows native scan/cache progress, filters on bounded metadata, and exports a
compact offline index whose source paths open the corresponding local rollout
files. It reads matching task titles from Codex's local `state_5.sqlite`
database and falls back to the first genuine prompt when no saved title is
available. Optional **From** and **To** controls accept local date and time,
normalize the values to inclusive UTC boundaries for native search, and select
only rollout files whose observed activity overlaps that range. Discovery uses
the rollout filename's local timestamp as the file's creation time and filesystem
modification time as its update time, so a long-running rollout is selected
when it starts in the range, is updated in the range, or spans the complete
range. Each selected file is parsed as a whole; event history and parent/child
report context are not clipped to the range. Stable selected files continue to
reuse metadata from the incremental SQLite index without being reopened. Every
successful export opens in its own app window. The app
remembers the last export folder across launches and offers **Open last
export** without rescanning the logs. Selecting a root enables full report
generation through the renderer bundled into the desktop application. Native
command failures, renderer standard error, frontend exceptions, and panics are
written as bounded JSON Lines entries in the local Tauri app-log directory.
The **Open diagnostic log** control opens the current file directly. On macOS
it is `~/Library/Logs/ca.devconsult.agent-report/agent-report.log`; one rotated
`agent-report.previous.log` is retained beside it. The current file rotates
when it reaches 5 MiB, individual messages are bounded, and rollout transcript
bodies are not intentionally recorded.

```bash
cd tools/report
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[desktop]'
cd desktop
pnpm install
pnpm tauri:dev
```

Build the native application bundle with:

```bash
pnpm tauri:build
```

The `tauri:dev` and `tauri:build` scripts merge the sidecar bundle configuration
and first create a target-specific PyInstaller
sidecar under the ignored `src-tauri/binaries/` build directory. Tauri embeds
that executable in the application bundle. It contains the Python renderer,
its static report data, and the required native Rust engine, so running or
installing the built app does not require Python or `agent-report` on `PATH`.
Set `AGENT_REPORT_PYTHON` only to choose a different Python 3.11+ build
interpreter with PyInstaller 6.21.0. `AGENT_REPORT_COMMAND` remains an explicit
development override for the renderer process; normal app operation does not
use it.

The current ad-hoc macOS bundle disables hardened runtime. Tauri otherwise
re-signs the PyInstaller one-file sidecar with library validation, which blocks
the Python framework that the sidecar extracts at runtime. A future Developer
ID and notarized release must replace this ad-hoc profile with a separately
tested signing and entitlement strategy.

The sequence view reads task display names from Codex's local desktop catalogs
when available, and the same names identify top-level rows in the timeline.
A renamed or archived task may not remain in that catalog; use
repeatable `--thread-title THREAD_ID=TITLE` overrides to make those lifelines
match the Codex sidebar exactly:

```bash
agent-report \
  --codex-thread <coordinator-thread-id> \
  --include-delegations \
  --thread-title '<linked-thread-id>=Process Backlog Items' \
  --live \
  --output codex-sequence.html
```

Discover reportable root runs by inclusive UTC date or hour range without first
finding a thread ID. The Codex catalog scans both `~/.codex/sessions` and
`~/.codex/archived_sessions` by default and prefers task titles saved by the
Codex app. It lists each root run's bounded task title, start time, workspace,
store, thread ID, and rollout path; descendant rollouts remain part of their
root report rather than appearing as separate catalog entries:

```bash
agent-report \
  --codex-catalog \
  --from-date 2026-07-14T09 \
  --to-date 2026-07-17T17 \
  --output agent-reports/index.html
```

Date-only `YYYY-MM-DD` values remain supported. A `To` date includes that
whole UTC day, and a `To` hour includes that whole UTC hour.

Add `--generate-batch` to generate every selected report under a sibling
`reports/` directory. The catalog links down to each report and every report
links back to the catalog:

```bash
agent-report \
  --codex-catalog \
  --from-date 2026-07-14 \
  --to-date 2026-07-17 \
  --workspace-contains agent-runner \
  --generate-batch \
  --output agent-reports/index.html
```

Use `--title-contains` for a case-insensitive task-title filter and repeat
`--catalog-root PATH` to replace the default stores with caller-bounded search
roots.

The default formatter config recognizes patches, agent claims, repository
checks combined with skill-file line counts, standalone skill-file line counts,
inter-agent messages, agent lifecycle calls, and waits. Rules are evaluated in
file order. A rule may match the tool name plus a bounded regular expression,
then extract display fields from named regex groups or dotted JSON paths. Retain
the generated config with a run when an agent creates run-specific rules after
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

Junie has the parallel catalog and batch workflow. It scans
`~/.junie/sessions` for durable `events.jsonl` streams by default and accepts
the same date, title, workspace/source-path, and custom-root filters:

```bash
agent-report \
  --junie-catalog \
  --from-date 2026-07-14 \
  --to-date 2026-07-17 \
  --generate-batch \
  --output junie-reports/index.html
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
For current Codex logs it also shows direct context occupancy, headroom,
high-water use, compaction changes, per-call token dimensions, inferred model
timing and response-size-controlled rates, test/process and wait states, and
the portion of agent waiting not overlapped by productive child work. Successful
exact-ID claim acquire/release events create work-item segments with start, end,
blocked or handoff disposition, token use, inference rate, and runtime-state
time. Older logs keep their existing usage report and mark unavailable metrics
instead of inventing values. Browser-facing timestamps in these metric views
use the viewer's local timezone.
For aborted turns, it also correlates an explicit `interrupt_agent` call from
another included thread and shows compact caller, parent-relationship, caller-
turn, and abort-reason details beneath the state badge when that evidence is
available. Unmatched aborts remain unattributed.
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
