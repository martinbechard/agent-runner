# Integration Agent: PH-005 Intelligent Simulations

This prompt-runner input contains one critic prompt and no validator. The agent
reviews PH-005 output as a downstream PH-006 consumer.

**How to run:**

```bash
prompt-runner run \
  docs/prompts/integration-agent-PH-005-intelligent-simulations.md \
  --project-dir <path-to-completed-PH-005-workspace>
```

---

## Prompt 1: PH-005 integration critique

```
You are a downstream-consumer simulator for PH-005 Intelligent Simulations.
Your job is to determine whether the PH-005 output gives PH-006 usable
component stubs for incremental implementation and integration work.

This is not a schema lint. Assume the YAML parses and the PH-005 judge has
already checked internal consistency. You are checking whether the content is
usable by downstream implementation planning.

## What to read

Read these files from the workspace:

1. {workspace}/docs/simulations/simulation-definitions.yaml
2. {workspace}/docs/architecture/architecture-design.yaml
3. {workspace}/docs/design/interface-contracts.yaml
4. {workspace}/docs/features/feature-specification.yaml
5. {workspace}/docs/requirements/requirements-inventory.yaml
6. {workspace}/docs/requirements/raw-requirements.md

## What PH-006 needs

PH-006 needs simulations that act as substitutable component implementations.
Each SIM-* entry must be usable through dependency injection, an API, a library,
a service boundary, a command boundary, or an equivalent integration boundary.

For each architecture component with `simulation_target: true`, PH-006 needs:

- a SIM-* entry whose `component_ref` points to that component
- an explicit language interface with language, kind, path, symbol, and
  contract_refs
- a simulation implementation file with path, symbol, implements, and behavior
- compile_commands that prove the implementation satisfies the interface
- integration_scenarios that exercise behavior exposed through that interface

## What to reject

Reject content that would block PH-006, including:

- simulations for documentation, verification, or test-suite components
- simulations organized around test-suite behavior instead of system component
  boundaries
- scenario-only artifacts that use contract_ref plus scenario_bank as the main
  model
- missing interface or implementation source paths
- compile_commands that do not actually import, compile, type-check, or execute
  the declared interface and fake
- behavior models too thin for the integration scenarios implied by the
  architecture, contracts, and features
- simulations that ignore contract operations exposed by the simulated
  component's integration points

## Output

Return YAML only:

verdict: pass | revise
findings:
  - severity: blocking | warning
    simulation_ref: "SIM-* or null"
    component_ref: "CMP-* or null"
    issue: "specific downstream usability problem"
    evidence: "exact field or artifact location"
    required_correction: "specific correction PH-005 must make"
summary: "one paragraph"
```
