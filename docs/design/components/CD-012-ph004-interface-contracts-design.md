# PH-004

- **PROCESS: PROCESS-1**
  - **SYNOPSIS:** `PH-004` is Interface Contracts.
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:573) defines `phase_id="PH-004-interface-contracts"`.

## Inputs

- **FILE: FILE-1**
  - **SYNOPSIS:** Primary input:
    - `docs/design/solution-design.yaml`
  - **BECAUSE:** `PH-004` derives contracts from the `INT-*` interactions in the solution design.

- **FILE: FILE-2**
  - **SYNOPSIS:** Validation-reference input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** The contracts must still cover the feature acceptance criteria.

## Output

- **FILE: FILE-3**
  - **SYNOPSIS:** Output:
    - `docs/design/interface-contracts.yaml`
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:597) sets that as the phase output.

## Purpose

- **GOAL: GOAL-1**
  - **SYNOPSIS:** `PH-004` defines concrete contracts for each inter-component interaction.
  - **BECAUSE:** Every `INT-*` interaction must have at least one matching `CTR-*` contract.

- **GOAL: GOAL-2**
  - **SYNOPSIS:** `PH-004` fully specifies request and response schemas.
  - **BECAUSE:** The phase forbids vague placeholders like `object`, `any`, or `unknown`.

- **GOAL: GOAL-3**
  - **SYNOPSIS:** `PH-004` defines explicit error types and behavioral specs.
  - **BECAUSE:** Downstream simulation and implementation phases need named failures and pre/postconditions.

## Required Output Shape

- **ENTITY: ENTITY-1**
  - **SYNOPSIS:** The top-level section is:
    - `contracts`
  - **BECAUSE:** That is the schema defined for `PH-004`.

- **ENTITY: ENTITY-2**
  - **SYNOPSIS:** Each contract contains:
    - `id`
    - `name`
    - `interaction_ref`
    - `source_component`
    - `target_component`
    - `operations`
    - `behavioral_specs`
  - **BECAUSE:** Those are the required fields for contract records.

## What Good Means

- **RULE: RULE-1**
  - **SYNOPSIS:** Every `INT-*` interaction must have at least one `CTR-*` contract.
  - **BECAUSE:** Interaction coverage is the primary extraction focus of the phase.

- **RULE: RULE-2**
  - **SYNOPSIS:** Request and response schemas must be fully typed and constrained.
  - **BECAUSE:** Schema precision is required for simulation and implementation.

- **RULE: RULE-3**
  - **SYNOPSIS:** Each operation must name its failure modes and at least one verifiable behavioral pre/postcondition pair.
  - **BECAUSE:** Error completeness and behavioral completeness are required downstream.

## Short Version

- **GOAL: GOAL-4**
  - **SYNOPSIS:** `PH-004` turns interaction flows into explicit, typed, behaviorally testable contracts.
  - **BECAUSE:** It is the handoff from design to simulation and implementation planning.
