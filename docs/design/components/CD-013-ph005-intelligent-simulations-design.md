# PH-005

- **PROCESS: PROCESS-1**
  - **SYNOPSIS:** `PH-005` is Intelligent Simulations.
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:706) defines `phase_id="PH-005-intelligent-simulations"`.

## Inputs

- **FILE: FILE-1**
  - **SYNOPSIS:** Primary input:
    - `docs/design/interface-contracts.yaml`
  - **BECAUSE:** `PH-005` produces simulations directly from the contract definitions.

- **FILE: FILE-2**
  - **SYNOPSIS:** Validation-reference input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** The simulations must still cover feature acceptance criteria and contract intent.

## Output

- **FILE: FILE-3**
  - **SYNOPSIS:** Output:
    - `docs/simulations/simulation-definitions.yaml`
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:730) sets that as the phase output.

## Purpose

- **GOAL: GOAL-1**
  - **SYNOPSIS:** `PH-005` defines at least one `SIM-*` simulation for each `CTR-*` contract.
  - **BECAUSE:** Contract coverage is the primary extraction focus of the phase.

- **GOAL: GOAL-2**
  - **SYNOPSIS:** `PH-005` supplies happy-path, error-path, and edge-case scenarios.
  - **BECAUSE:** Scenario breadth is explicitly required.

- **GOAL: GOAL-3**
  - **SYNOPSIS:** `PH-005` encodes concrete expected outcomes and assertions.
  - **BECAUSE:** Simulation outputs must be mechanically verifiable and not rely on hidden implementation knowledge.

## Required Output Shape

- **ENTITY: ENTITY-1**
  - **SYNOPSIS:** The top-level section is:
    - `simulations`
  - **BECAUSE:** That is the schema defined for `PH-005`.

- **ENTITY: ENTITY-2**
  - **SYNOPSIS:** Each simulation contains:
    - `id`
    - `contract_ref`
    - `description`
    - `scenario_bank`
    - `llm_adjuster`
    - `validation_rules`
  - **BECAUSE:** Those are the required fields for simulation records.

## What Good Means

- **RULE: RULE-1**
  - **SYNOPSIS:** Every `CTR-*` contract must have at least one matching `SIM-*` simulation.
  - **BECAUSE:** Contract coverage is the core extraction focus.

- **RULE: RULE-2**
  - **SYNOPSIS:** Every simulation must include success, failure, and boundary scenarios.
  - **BECAUSE:** Scenario breadth is required for realistic verification.

- **RULE: RULE-3**
  - **SYNOPSIS:** Expected outputs must be derivable from the contract, not from hidden implementation details.
  - **BECAUSE:** The phase explicitly forbids LLM leakage of implementation knowledge.

## Short Version

- **GOAL: GOAL-4**
  - **SYNOPSIS:** `PH-005` turns typed contracts into executable simulation scenarios with explicit assertions.
  - **BECAUSE:** It creates the test-double layer used before real implementations exist.
