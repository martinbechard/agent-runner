# methodology-runner

`methodology-runner` orchestrates the methodology phases over a project
workspace. It selects the checked-in phase prompt modules, runs them
through `prompt-runner`, applies deterministic validation, and performs
cross-reference checks between phases.

## Install

Install `prompt-runner` first, then `methodology-runner`:

```bash
pip install -e tools/prompt-runner
pip install -e tools/methodology-runner
```

For test dependencies:

```bash
pip install -e tools/prompt-runner[dev]
pip install -e tools/methodology-runner[dev]
```

## Main Commands

Run a full pipeline:

```bash
methodology-runner run sample/hello-world/requests/hello-world-python-app.md \
  --workspace work/hello-world-pipeline \
  --backend codex
```

Run one phase only:

```bash
methodology-runner run sample/hello-world/requests/hello-world-python-app.md \
  --workspace work/hello-world-ph000 \
  --backend codex \
  --phases PH-000-requirements-inventory
```

Resume a halted run:

```bash
methodology-runner resume work/hello-world-pipeline
```

Inspect run status:

```bash
methodology-runner status work/hello-world-pipeline
```

## Delivery Expectations

The full pipeline is tuned for changes to existing software. `PH-006`
authors and runs an implementation workflow that must deliver code, tests,
and project files in the target workspace. Generated implementation prompts
must require project-local code best practices, meaningful file-level,
type-level, and function-level comments or docstrings where appropriate,
steady-state documentation, and application README setup and operation
guidance.

`PH-007` treats those expectations as part of final verification. When code,
documentation, or README files changed, the verification report should account
for the delivered quality of those files instead of only reporting that a
behavioral test passed.

## Sample

The reference sample lives under `sample/hello-world/`.

- `sample/hello-world/requests/` holds the raw request
- `sample/hello-world/fixtures/` holds curated per-phase workspaces

The sample is a runnable reference bundle, not the main integration
surface. The intended user path is to install the tools and point them
at another project workspace.
