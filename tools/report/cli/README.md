# Agent Report CLI

Agent Report CLI creates token-usage reports from local Codex JSONL logs. This
package is independent from the Agent Report Tauri app. The wheel contains only
the `agent-report` launcher, report renderers and data, and the native discovery
engine for its target operating system.

Python 3.11 or newer is required. Download the wheel for your operating system
from the matching GitHub release.

## Install

On Apple Silicon macOS 11 or newer:

```bash
python3 -m pip install \
  ./agent_report_cli-1.0.0-py3-none-macosx_11_0_arm64.whl
```

On 64-bit Windows:

```powershell
py -m pip install `
  .\agent_report_cli-1.0.0-py3-none-win_amd64.whl
```

Confirm the installation:

```bash
agent-report --help
```

## Text Output

The default report scans `~/.codex/sessions` and
`~/.codex/archived_sessions`. It groups usage by folder for local midnight
today through local midnight tomorrow:

```bash
agent-report --token-summary
```

Set a local date range. **From** is inclusive and **To** is exclusive:

```bash
agent-report --token-summary \
  --from 2026-08-16 \
  --to 2026-08-19
```

Each date can include local 24-hour time:

```bash
agent-report --token-summary \
  --from "2026-08-18 09:15" \
  --to "2026-08-18 22:04"
```

Repeat `--scan-directory` to select one or more folders:

```bash
agent-report --token-summary \
  --scan-directory ~/.codex/sessions \
  --scan-directory /Volumes/archive/codex-sessions
```

Add `--threads` for one detailed row per thread:

```bash
agent-report --token-summary \
  --from 2026-08-16 \
  --to 2026-08-19 \
  --threads
```

## CSV Output

Write CSV rows without a rollup row:

```bash
agent-report --token-summary \
  --from 2026-08-16 \
  --to 2026-08-19 \
  --csv token-usage.csv
```

Combine `--csv` with `--threads` for one row per thread. Use `--csv` without a
path to write CSV to standard output.

## HTML Output

Create a self-contained folder-level report:

```bash
agent-report --token-summary \
  --from 2026-08-16 \
  --to 2026-08-19 \
  --html token-usage.html
```

Add `--threads` to create folder, thread, event-ledger, step, raw-log, and
ledger-CSV drill-down files beside the main report:

```bash
agent-report --token-summary \
  --from 2026-08-16 \
  --to 2026-08-19 \
  --html token-usage.html \
  --threads
```

## YAML Configuration

Store repeatable options in a YAML file:

```yaml
mode: token-summary
directories:
  - ~/.codex/sessions
  - ~/.codex/archived_sessions
from: 2026-08-16
to: 2026-08-19
csv: token-usage.csv
html: token-usage.html
threads: true
```

Run the configuration:

```bash
agent-report --config token-summary.yaml
```

Relative paths are resolved from the YAML file's directory. Explicit
command-line options override their YAML equivalents.

Agent Report CLI is distributed under the [MIT License](LICENSE).
