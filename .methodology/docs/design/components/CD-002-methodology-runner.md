# CD-002 -- Methodology Runner

*Component design for the Python CLI that orchestrates the methodology phases by executing checked-in prompt modules through prompt-runner.*

## 1. Purpose

`methodology_runner` is the orchestration layer for the methodology pipeline.
It owns:

- phase sequencing
- workspace initialization and resume
- per-phase skill selection and prelude creation
- prompt-runner invocation
- cross-reference verification
- state persistence and summaries

It does **not** synthesize phase prompt files at run time. The canonical prompt
contracts live as checked-in prompt modules under
`.methodology/docs/prompts/`, and each `PhaseConfig` points to the module it
uses.

## 2. Scope

### In scope

- Sequencing the configured phases in dependency order
- Running either all phases or a caller-selected subset
- Initializing and locking a shared workspace
- Persisting run state in `.methodology-runner/state.json`
- Writing phase-local execution artifacts under `.methodology-runner/runs/`
- Invoking prompt-runner with checked-in prompt modules, preludes, validators,
  and placeholder values
- Running phase and end-to-end cross-reference verification
- Supporting retry after cross-reference failure by augmenting phase preludes

### Out of scope

- Runtime prompt synthesis
- Parallel phase execution
- UI or service interfaces beyond the CLI
- Rewriting methodology artifacts directly outside prompt-runner execution

## 3. Components

Source code lives under `.methodology/src/cli/methodology_runner/`. The active
component set is:

- `models.py`
  Carries `PhaseConfig`, project state, phase state, and result structures.
- `phases.py`
  Defines the phase registry, predecessor relationships, artifact paths, and
  canonical `prompt_module_path` for each phase.
- `orchestrator.py`
  Drives the phase lifecycle: workspace setup, selector/prelude generation,
  prompt-runner invocation, cross-reference verification, retry handling, and
  state updates.
- `skill_selector.py`
  Chooses generator and judge skills for a phase and materializes the per-phase
  skill manifest.
- `prelude.py`
  Builds generator and judge prelude text from the selected skills.
- `cross_reference.py`
  Verifies phase outputs and end-to-end traceability.
- `artifact_summarizer.py`
  Produces backend-assisted artifact summaries where needed by the selector and
  verification flows.
- `cli.py`
  Provides `run`, `resume`, `status`, and `reset`.

## 4. Execution Model

For each phase, the orchestrator:

1. validates predecessor completion and required input artifacts
2. resolves the checked-in prompt module from `PhaseConfig.prompt_module_path`
3. builds or reuses `phase-NNN-skills.yaml`
4. writes `generator-prelude.txt` and `judge-prelude.txt`
5. invokes prompt-runner against the checked-in prompt module
6. runs cross-reference verification against the phase output
7. if verification fails and retries remain, writes retry preludes with
   guidance and re-runs the same prompt module
8. persists updated phase state and writes summary information

The prompt contract is stable and versioned in the repository, while the
run-local artifacts remain execution-specific.

## 5. Workspace Layout

A methodology run uses one shared workspace for all phases:

```text
<workspace>/
  docs/
    requirements/raw-requirements.md
    requirements/requirements-inventory.yaml
    features/feature-specification.yaml
    architecture/stack-manifest.yaml
    design/solution-design.yaml
    design/interface-contracts.yaml
    simulations/simulation-definitions.yaml
    implementation/implementation-plan.yaml
    verification/verification-report.yaml
  .methodology-runner/
    state.json
    summary.txt
    run.lock
    runs/
      phase-0/
        phase-000-skills.yaml
        generator-prelude.txt
        judge-prelude.txt
        cross-ref-result.json
        prompt-runner-output-phase-0/
      ...
```

The prompt module itself stays checked in under `.methodology/docs/prompts/`
and is referenced from state; it is not copied into `runs/phase-N/` as a new
run-local prompt copy.

## 6. Retry Model

If prompt-runner succeeds but cross-reference verification fails:

1. the phase output is discarded
2. the orchestrator writes retry-specific prelude files containing the
   verification guidance
3. prompt-runner is re-invoked on the same checked-in prompt module

This keeps the prompt contract fixed while making the retry reason explicit in
the run artifacts.

## 7. Design Rules

- The checked-in prompt modules are the canonical phase prompt source.
- `PhaseConfig.prompt_module_path` must be populated for every runnable phase.
- Run-local artifacts should capture execution evidence, not duplicate prompt
  authorship.
- Tests should assert public runner behavior, not obsolete internal prompt
  generation details.
