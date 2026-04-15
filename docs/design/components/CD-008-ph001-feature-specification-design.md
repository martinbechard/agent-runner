# PH-001

- **PROCESS: PROCESS-1**
  - **SYNOPSIS:** `PH-001` is Feature Specification.
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:203) defines `phase_id="PH-001-feature-specification"`.

## Inputs

- **FILE: FILE-1**
  - **SYNOPSIS:** Primary input:
    - `docs/requirements/requirements-inventory.yaml`
  - **BECAUSE:** `PH-001` consumes the requirements inventory produced by `PH-000`.

- **FILE: FILE-2**
  - **SYNOPSIS:** Validation-reference input:
    - `docs/requirements/raw-requirements.md`
  - **BECAUSE:** The raw requirements are used to verify that feature grouping still traces back to the original request.

## Output

- **FILE: FILE-3**
  - **SYNOPSIS:** Output:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:229) sets that as the phase output.

## Purpose

- **GOAL: GOAL-1**
  - **SYNOPSIS:** `PH-001` turns `RI-*` inventory items into grouped `FT-*` features.
  - **BECAUSE:** The phase definition says to group related inventory items into coherent features.

- **GOAL: GOAL-2**
  - **SYNOPSIS:** `PH-001` defines acceptance criteria for those features.
  - **BECAUSE:** Each feature must carry `AC-*` acceptance criteria that are concrete and testable.

- **GOAL: GOAL-3**
  - **SYNOPSIS:** `PH-001` declares feature dependencies.
  - **BECAUSE:** Downstream phases need to know which features rely on others.

- **GOAL: GOAL-4**
  - **SYNOPSIS:** `PH-001` identifies out-of-scope inventory items.
  - **BECAUSE:** Every `RI-*` item must either map to a feature or be explicitly excluded with a reason.

- **GOAL: GOAL-5**
  - **SYNOPSIS:** `PH-001` identifies cross-cutting concerns.
  - **BECAUSE:** Concerns like logging, authentication, persistence, or error handling may affect multiple features and need to be surfaced for later phases.

## Required Output Shape

- **ENTITY: ENTITY-1**
  - **SYNOPSIS:** The top-level sections are:
    - `features`
    - `out_of_scope`
    - `cross_cutting_concerns`
  - **BECAUSE:** That is the schema defined for `PH-001`.

- **ENTITY: ENTITY-2**
  - **SYNOPSIS:** Each feature contains:
    - `id`
    - `name`
    - `description`
    - `source_inventory_refs`
    - `acceptance_criteria`
    - `dependencies`
  - **BECAUSE:** Those are the required fields for feature records.

## What Good Means

- **RULE: RULE-1**
  - **SYNOPSIS:** Every `RI-*` item must be covered by at least one feature or explicitly listed in `out_of_scope`.
  - **BECAUSE:** The phase's extraction focus requires complete inventory coverage.

- **RULE: RULE-2**
  - **SYNOPSIS:** Acceptance criteria must be specific and testable.
  - **BECAUSE:** The phase definition explicitly rejects vague criteria like “fast” or “user-friendly” without measurable thresholds.

- **RULE: RULE-3**
  - **SYNOPSIS:** Dependencies between features must be declared when features share sequencing, data, or transactional boundaries.
  - **BECAUSE:** Downstream architecture and design phases depend on these relationships.

## Short Version

- **GOAL: GOAL-6**
  - **SYNOPSIS:** `PH-001` takes the requirements inventory and turns it into a structured feature specification.
  - **BECAUSE:** It is the bridge between raw extracted requirements (`RI-*`) and later design/architecture work (`FT-*`, `AC-*`, dependencies, cross-cutting concerns).
