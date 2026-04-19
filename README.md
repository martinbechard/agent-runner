# agent-runner

This repository contains two installable tools and one curated sample:

- `tools/prompt-runner/`
  - runs markdown prompt and judge workflows
- `tools/methodology-runner/`
  - orchestrates the methodology phases on top of prompt-runner
- `sample/hello-world/`
  - compact reference bundle that demonstrates the end-to-end flow

## Install

```bash
pip install -e tools/prompt-runner
pip install -e tools/methodology-runner
```

For development and tests:

```bash
pip install -e tools/prompt-runner[dev]
pip install -e tools/methodology-runner[dev]
```

## Normal User Flow

Validate a prompt file:

```bash
prompt-runner parse tools/methodology-runner/docs/prompts/PR-025-ph000-requirements-inventory.md
```

Run the methodology against a request:

```bash
methodology-runner run sample/hello-world/requests/hello-world-python-app.md \
  --workspace work/hello-world-pipeline \
  --backend codex
```

The sample is a reference workflow and smoke target. The primary
integration surface is the installed CLI tools, not the sample tree
itself.
