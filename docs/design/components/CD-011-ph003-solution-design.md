# PH-003

- **PROCESS: PROCESS-1**
  - **SYNOPSIS:** `PH-003` is Solution Design.
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:458) defines `phase_id="PH-003-solution-design"`.

## Inputs

- **FILE: FILE-1**
  - **SYNOPSIS:** Primary input:
    - `docs/architecture/stack-manifest.yaml`
  - **BECAUSE:** `PH-003` refines the architecture into per-component responsibilities and interactions.

- **FILE: FILE-2**
  - **SYNOPSIS:** Upstream-traceability input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** The design must still trace back to feature-level intent.

## Output

- **FILE: FILE-3**
  - **SYNOPSIS:** Output:
    - `docs/design/solution-design.yaml`
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:482) sets that as the phase output.

## Purpose

- **GOAL: GOAL-1**
  - **SYNOPSIS:** `PH-003` maps each feature to the components that realize it.
  - **BECAUSE:** Every `FT-*` feature must appear in at least one `feature_realization_map`.

- **GOAL: GOAL-2**
  - **SYNOPSIS:** `PH-003` defines clear component responsibility boundaries.
  - **BECAUSE:** No two components should implicitly own the same entity or operation.

- **GOAL: GOAL-3**
  - **SYNOPSIS:** `PH-003` captures the interactions between components.
  - **BECAUSE:** All data flows between components must be explicit.

## Required Output Shape

- **ENTITY: ENTITY-1**
  - **SYNOPSIS:** The top-level sections are:
    - `components`
    - `interactions`
  - **BECAUSE:** That is the schema defined for `PH-003`.

- **ENTITY: ENTITY-2**
  - **SYNOPSIS:** Each component contains:
    - `id`
    - `name`
    - `responsibility`
    - `technology`
    - `feature_realization_map`
    - `dependencies`
  - **BECAUSE:** Those are the required fields for solution-design components.

## What Good Means

- **RULE: RULE-1**
  - **SYNOPSIS:** Every `FT-*` feature must appear in at least one component's `feature_realization_map`.
  - **BECAUSE:** Feature realization is a core extraction focus of the phase.

- **RULE: RULE-2**
  - **SYNOPSIS:** Components must have well-defined and non-overlapping ownership boundaries.
  - **BECAUSE:** Boundary clarity is necessary for later contracts and implementation.

- **RULE: RULE-3**
  - **SYNOPSIS:** Every inter-component dependency that moves data must have an explicit `INT-*` interaction.
  - **BECAUSE:** Interaction completeness is required for downstream contract design.

## Short Version

- **GOAL: GOAL-4**
  - **SYNOPSIS:** `PH-003` turns architectural components into explicit responsibilities and interaction flows.
  - **BECAUSE:** It is the direct precursor to interface contracts.
