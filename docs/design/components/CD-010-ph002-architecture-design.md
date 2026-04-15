# PH-002

- **PROCESS: PROCESS-1**
  - **SYNOPSIS:** `PH-002` is Architecture.
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:327) defines `phase_id="PH-002-architecture"`.

## Inputs

- **FILE: FILE-1**
  - **SYNOPSIS:** Primary input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** `PH-002` decomposes the feature specification into technology components.

- **FILE: FILE-2**
  - **SYNOPSIS:** Upstream-traceability input:
    - `docs/requirements/requirements-inventory.yaml`
  - **BECAUSE:** The architecture keeps traceability back to the original requirements inventory.

## Output

- **FILE: FILE-3**
  - **SYNOPSIS:** Output:
    - `docs/architecture/stack-manifest.yaml`
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:351) sets that as the phase output.

## Purpose

- **GOAL: GOAL-1**
  - **SYNOPSIS:** `PH-002` decomposes features into deployable technology components.
  - **BECAUSE:** The phase must assign features to components with coherent technology choices.

- **GOAL: GOAL-2**
  - **SYNOPSIS:** `PH-002` declares the expertise needed to build each component.
  - **BECAUSE:** Each component must carry `expected_expertise` as human-readable descriptions.

- **GOAL: GOAL-3**
  - **SYNOPSIS:** `PH-002` identifies the integration points between components.
  - **BECAUSE:** Cross-component data flows must be captured explicitly for later design phases.

## Required Output Shape

- **ENTITY: ENTITY-1**
  - **SYNOPSIS:** The top-level sections are:
    - `components`
    - `integration_points`
    - `rationale`
  - **BECAUSE:** That is the schema defined for `PH-002`.

- **ENTITY: ENTITY-2**
  - **SYNOPSIS:** Each component contains:
    - `id`
    - `name`
    - `role`
    - `technology`
    - `runtime`
    - `frameworks`
    - `persistence`
    - `expected_expertise`
    - `features_served`
  - **BECAUSE:** Those are the required fields for architecture components.

## What Good Means

- **RULE: RULE-1**
  - **SYNOPSIS:** Every `FT-*` feature must be served by at least one component.
  - **BECAUSE:** Feature coverage is a core extraction focus of the phase.

- **RULE: RULE-2**
  - **SYNOPSIS:** `expected_expertise` must be free-text descriptions, not concrete skill IDs.
  - **BECAUSE:** The architecture phase must remain decoupled from the skill catalog.

- **RULE: RULE-3**
  - **SYNOPSIS:** Every implied cross-component data flow must be represented as an integration point.
  - **BECAUSE:** Integration completeness is required for downstream design work.

## Short Version

- **GOAL: GOAL-4**
  - **SYNOPSIS:** `PH-002` turns features into a technology/component decomposition with explicit integration boundaries.
  - **BECAUSE:** It is the bridge from feature semantics to implementation structure.
