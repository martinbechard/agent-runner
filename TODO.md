# TODO

## PH-002

- Main script:
  - `./scripts/run-phase-2-architecture.sh`
- Prompt:
  - `/.methodology/docs/prompts/PR-024-ph002-architecture.md`
- Variant prompt work:
  - `/.methodology/docs/prompts/PR-031-ph002-architecture-simple.md`
- Fixture workspace:
  - `/tests/fixtures/ph002-hello-world-workspace`
- Inputs:
  - `/tests/fixtures/ph002-hello-world-workspace/docs/requirements/raw-requirements.md`
  - `/tests/fixtures/ph002-hello-world-workspace/docs/requirements/requirements-inventory.yaml`
  - `/tests/fixtures/ph002-hello-world-workspace/docs/features/feature-specification.yaml`
- Deterministic validator:
  - `/tests/fixtures/ph002-hello-world-workspace/scripts/phase-2-deterministic-validation.py`
- Main output:
  - `/work/ph002-architecture-run/docs/architecture/stack-manifest.yaml`

### Test commands

- Baseline PH-002 run:
  - `./scripts/run-phase-2-architecture.sh`
- Parse the variant module:
  - `PYTHONPATH=.prompt-runner/src/cli python -m prompt_runner parse .methodology/docs/prompts/PR-031-ph002-architecture-simple.md`
- Run one PH-002 variant:
  - `PYTHONPATH=.prompt-runner/src/cli python -m prompt_runner run .methodology/docs/prompts/PR-031-ph002-architecture-simple.md --only 1 --variant <A|B|C|D|E> --project-dir tests/fixtures/ph002-hello-world-workspace --run-dir work/ph002-variant-run`

## PH-003

- Main script:
  - `./scripts/run-phase-3-solution-design.sh`
- Prompt:
  - `/.methodology/docs/prompts/PR-026-ph003-solution-design.md`
- Fixture workspace:
  - `/tests/fixtures/ph003-hello-world-workspace`
- Inputs:
  - `/tests/fixtures/ph003-hello-world-workspace/docs/architecture/stack-manifest.yaml`
  - `/tests/fixtures/ph003-hello-world-workspace/docs/features/feature-specification.yaml`
- Deterministic validator:
  - `/tests/fixtures/ph003-hello-world-workspace/scripts/phase-3-deterministic-validation.py`
- Main output:
  - `/work/ph003-solution-design-run/docs/design/solution-design.yaml`

### Test commands

- Baseline PH-003 run:
  - `./scripts/run-phase-3-solution-design.sh`
- Run PH-003 after chaining from PH-002:
  - copy `/work/ph002-architecture-run/docs/architecture/stack-manifest.yaml`
  - into `/tests/fixtures/ph003-hello-world-workspace/docs/architecture/stack-manifest.yaml`
  - then run `./scripts/run-phase-3-solution-design.sh`

## Current focus

- Re-test PH-002 variant `E` after the prompt and validator alignment.
- Confirm the PH-002 variant run closes cleanly and writes summary/verdict files.
- If PH-002 variant `E` passes cleanly, chain its architecture output into PH-003.
- Re-test PH-003 with `structured-design` and `structured-review` active in the prompt.
