# CD-002 -- Methodology Runner

*Component design for the Python CLI that orchestrates the methodology phases by executing checked-in prompt modules through prompt-runner.*

## 1. Purpose

`methodology_runner` is the orchestration layer for the methodology pipeline.
It owns:

- phase sequencing
- workspace initialization and resume
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
- Invoking prompt-runner with checked-in prompt modules, validators, runtime
  guidance, and placeholder values
- Running phase and end-to-end cross-reference verification
- Supporting retry after cross-reference failure by injecting retry guidance

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
  Drives the phase lifecycle: workspace setup, prompt-module execution,
  prompt-runner invocation, cross-reference verification, retry handling, and
  state updates.
- `cross_reference.py`
  Verifies phase outputs and end-to-end traceability.
- `cli.py`
  Provides `run`, `resume`, `status`, and `reset`.

## 4. Execution Model

For each phase, the orchestrator:

1. validates predecessor completion and required input artifacts
2. resolves the checked-in prompt module from `PhaseConfig.prompt_module_path`
3. invokes prompt-runner against the checked-in prompt module
4. runs cross-reference verification against the phase output
5. if verification fails and retries remain, writes a retry-guidance artifact
   and re-runs the same prompt module with runtime guidance injected
6. persists updated phase state and writes summary information

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
        cross-ref-result.json
        retry-guidance-1.txt
        prompt-runner-output-phase-0/
      ...
```

The prompt module itself stays checked in under `.methodology/docs/prompts/`
and is referenced from state; it is not copied into `runs/phase-N/` as a new
run-local prompt copy.

## 6. Retry Model

If prompt-runner succeeds but cross-reference verification fails:

1. the phase output remains in place at its canonical workspace path
2. the orchestrator writes a retry-guidance artifact containing the
   verification guidance
3. prompt-runner is re-invoked on the same checked-in prompt module with that
   guidance injected as runtime delta

This keeps the prompt contract fixed while making the retry reason explicit in
the run artifacts and lets the next iteration revise the same artifact rather
than restarting from a cleaned workspace.

## 7. Design Rules

- The checked-in prompt modules are the canonical phase prompt source.
- `PhaseConfig.prompt_module_path` must be populated for every runnable phase.
- Run-local artifacts should capture execution evidence, not duplicate prompt
  authorship.
- Cleanup is opt-in. Normal run and resume preserve artifacts even on
  escalation or retry; explicit cleanup is requested only through isolated
  phase execution with `--reset`.
- Tests should assert public runner behavior, not obsolete internal prompt
  generation details.
