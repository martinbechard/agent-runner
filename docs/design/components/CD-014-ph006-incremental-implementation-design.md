# PH-006

- **PROCESS: PROCESS-1**
  - **SYNOPSIS:** `PH-006` is Incremental Implementation.
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:834) defines `phase_id="PH-006-incremental-implementation"`.

## Inputs

- **FILE: FILE-1**
  - **SYNOPSIS:** Primary input:
    - `docs/design/interface-contracts.yaml`
  - **BECAUSE:** `PH-006` plans what to build from the contract layer.

- **FILE: FILE-2**
  - **SYNOPSIS:** Validation-reference inputs:
    - `docs/simulations/simulation-definitions.yaml`
    - `docs/features/feature-specification.yaml`
    - `docs/design/solution-design.yaml`
  - **BECAUSE:** The implementation plan must respect simulations, feature acceptance criteria, and component dependencies.

## Output

- **FILE: FILE-3**
  - **SYNOPSIS:** Output:
    - `docs/implementation/implementation-plan.yaml`
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:865) sets that as the phase output.

## Purpose

- **GOAL: GOAL-1**
  - **SYNOPSIS:** `PH-006` defines a dependency-respecting build order.
  - **BECAUSE:** Components must not be built before their prerequisites are available or simulated.

- **GOAL: GOAL-2**
  - **SYNOPSIS:** `PH-006` maps tests to acceptance criteria and contracts.
  - **BECAUSE:** Unit and integration plans must remain traceable to the feature specification and interface contracts.

- **GOAL: GOAL-3**
  - **SYNOPSIS:** `PH-006` plans when simulations get replaced by real implementations.
  - **BECAUSE:** Simulation replacement and retest sequencing are explicit responsibilities of the phase.

## Required Output Shape

- **ENTITY: ENTITY-1**
  - **SYNOPSIS:** The top-level sections are:
    - `build_order`
    - `unit_test_plan`
    - `integration_test_plan`
    - `simulation_replacement_sequence`
  - **BECAUSE:** That is the schema defined for `PH-006`.

- **ENTITY: ENTITY-2**
  - **SYNOPSIS:** Build steps must contain:
    - `step`
    - `component_ref`
    - `rationale`
    - `contracts_implemented`
    - `simulations_used`
  - **BECAUSE:** Those are the required fields for the build-order plan.

## What Good Means

- **RULE: RULE-1**
  - **SYNOPSIS:** The build order must respect component dependencies from the solution design.
  - **BECAUSE:** Ordering correctness is the primary extraction focus.

- **RULE: RULE-2**
  - **SYNOPSIS:** Every `AC-*` must appear in unit-test or integration-test coverage.
  - **BECAUSE:** Test traceability is explicitly required.

- **RULE: RULE-3**
  - **SYNOPSIS:** Every `SIM-*` must have a concrete replacement step and retest plan.
  - **BECAUSE:** Simulation replacement is one of the phase's core responsibilities.

## Short Version

- **GOAL: GOAL-4**
  - **SYNOPSIS:** `PH-006` turns contracts and simulations into an executable build-and-test sequence.
  - **BECAUSE:** It is the phase that makes implementation order, test scope, and simulation retirement explicit.
