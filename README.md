# agent-runner

`agent-runner` is a toolkit for authoring agent workflows, running a
multi-phase software-delivery methodology, processing backlog items, and
reviewing recorded agent runs.

## Tools

| Tool | Purpose | Documentation |
| --- | --- | --- |
| `prompt-runner` | Parses and runs Markdown generation and judge workflows with revision loops. | [Prompt Runner](tools/prompt-runner/README.md) |
| `methodology-runner` | Composes checked-in phase prompts into a validated software-delivery pipeline. | [Methodology Runner](tools/methodology-runner/README.md) |
| `backlog-runner` | Claims backlog items, runs them through the methodology in isolated worktrees, and serializes target-branch integration. | [Backlog Runner](tools/backlog-runner/README.md) |
| `agent-report` | Builds privacy-safe offline reports and catalogs from recorded Codex, Junie, Prompt Runner, and Methodology Runner activity. It also provides a native desktop run index. | [Agent Report](tools/report/README.md) |
| `sample/hello-world` | Demonstrates the prompt and methodology flow with a compact reference project. | [Hello World sample](sample/hello-world/) |

The tools form a layered workflow:

1. `prompt-runner` executes one authored Markdown workflow.
2. `methodology-runner` uses Prompt Runner to execute and cross-check a
   sequence of methodology phases.
3. `backlog-runner` supplies claimed backlog items to Methodology Runner and
   coordinates their isolated worktrees.
4. `agent-report` reads recorded runs from these tools or supported agent
   stores and produces reviewable local reports.

Each tool is also usable independently.

## Requirements

- Python 3.11 or newer for all Python command-line tools.
- Git when a workflow creates linked or isolated worktrees.
- Rust when building Agent Report's native discovery engine from source.
- Node.js, `pnpm`, Rust, and the platform-specific Tauri prerequisites when
  developing the Agent Report desktop application.

Model backends and their authentication are configured outside this
repository. The examples below select the Codex backend.

## Install from a checkout

Create a virtual environment and install the command-line tools in editable
mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e 'tools/prompt-runner[dev]'
python -m pip install -e 'tools/methodology-runner[dev]'
python -m pip install -e 'tools/backlog-runner[dev]'
python -m pip install -e 'tools/report[dev]'
```

Agent Report requires its native engine. Build the engine before running an
editable installation:

```bash
cargo build \
  --manifest-path tools/report/Cargo.toml \
  --release \
  -p agent-report-engine
```

## Common workflows

### Validate or run a prompt workflow

Validate an authored prompt file:

```bash
prompt-runner parse \
  tools/methodology-runner/docs/prompts/PR-025-ph000-requirements-inventory.md
```

Run a prompt file against a project and a separate run directory:

```bash
prompt-runner run path/to/workflow.md \
  --project-dir /path/to/project \
  --run-dir /path/to/run
```

### Run the methodology

Run the included request through the complete methodology:

```bash
methodology-runner run \
  sample/hello-world/requests/hello-world-python-app.md \
  --workspace work/hello-world-pipeline \
  --backend codex
```

Inspect or resume the run:

```bash
methodology-runner status work/hello-world-pipeline
methodology-runner resume work/hello-world-pipeline
```

### Process a backlog

Inspect a project's backlog-runner state:

```bash
backlog-runner status --backlog-root /path/to/project
```

`backlog-runner run` starts the continuous supervisor. `backlog-runner once`
runs one bounded supervisor cycle. See the
[Backlog Runner commands](tools/backlog-runner/README.md#commands) before
starting work because the runner claims items and creates isolated worktrees.

### Generate Agent Reports

Install the current macOS Apple-silicon wheel:

```bash
python -m pip install \
  https://github.com/martinbechard/agent-runner/releases/download/agent-report-v0.6.4/agent_report-0.6.4-py3-none-macosx_11_0_arm64.whl
```

Generate one report from a supported run directory or recorded session:

```bash
agent-report <path> --output report.html
```

Build a catalog of root Codex tasks within an inclusive UTC date-and-hour
range:

```bash
agent-report \
  --codex-catalog \
  --from-date 2026-07-14T09 \
  --to-date 2026-07-17T17 \
  --output agent-reports/index.html
```

Agent Report prefers task titles saved by the Codex app and falls back to the
first genuine prompt when a saved title is unavailable. Generated HTML reports
open directly from disk. Native Codex reports include context pressure and
compactions, inferred inference-rate trends, concurrency-aware runtime states,
and exact claim-bounded work-item timing when those events are recorded.

The matching macOS desktop DMG is attached to the
[latest GitHub release](https://github.com/martinbechard/agent-runner/releases/latest).
The application is currently ad-hoc signed and is not notarized.

## Develop the Agent Report desktop application

Install the desktop dependencies and start Tauri development mode:

```bash
cd tools/report
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip install pyinstaller==6.21.0
cd desktop
pnpm install
pnpm tauri:dev
```

Build the application bundle with:

```bash
pnpm tauri:build
```

The desktop build creates and embeds its renderer sidecar. The built
application does not require Python or `agent-report` on the user's `PATH`.

## Verify a checkout

Run the Python suites:

```bash
pytest tools/prompt-runner/tests
pytest tools/methodology-runner/tests
pytest tools/backlog-runner/tests
pytest tools/report/tests
```

Run the Report Rust workspace:

```bash
cargo test --manifest-path tools/report/Cargo.toml --workspace --locked
```

Run the Report frontend checks:

```bash
cd tools/report/desktop
pnpm test
pnpm run build
```

## Repository documentation

- Tool behavior and command details live in each tool's README linked from the
  table above.
- Design, testing, and project-maintenance documents live under [`docs/`](docs/).
- The Hello World sample is a runnable reference and smoke target. Installed
  command-line tools are the primary integration surface.
