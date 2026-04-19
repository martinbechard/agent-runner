# Hello World Sample

This sample is the compact reference bundle for the repository.

It contains:

- `requests/hello-world-python-app.md`
  - the raw request
- `fixtures/ph000-hello-world-workspace` through
  `fixtures/ph007-hello-world-workspace`
  - curated per-phase workspaces that show the expected artifact chain

## First Commands

Validate the phase prompt file:

```bash
prompt-runner parse tools/methodology-runner/docs/prompts/PR-025-ph000-requirements-inventory.md
```

Run the full methodology pipeline:

```bash
methodology-runner run sample/hello-world/requests/hello-world-python-app.md \
  --workspace work/hello-world-pipeline \
  --backend codex
```

## Expected Outputs

A successful full run writes the phase artifacts under the chosen
workspace, including:

- `docs/requirements/requirements-inventory.yaml`
- `docs/features/feature-specification.yaml`
- `docs/architecture/stack-manifest.yaml`
- `docs/design/solution-design.yaml`
- `docs/design/interface-contracts.yaml`
- `docs/simulations/simulation-definitions.yaml`
- `docs/implementation/implementation-workflow.md`
- `docs/implementation/implementation-run-report.yaml`
- `docs/verification/verification-report.yaml`
