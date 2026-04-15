# PH-000

- **PROCESS: PROCESS-1**
  - **SYNOPSIS:** `PH-000` is Requirements Inventory.
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:66) defines `phase_id="PH-000-requirements-inventory"`.

## Inputs

- **FILE: FILE-1**
  - **SYNOPSIS:** Primary input:
    - `docs/requirements/raw-requirements.md`
  - **BECAUSE:** `PH-000` starts from the raw requirements document provided by the user.

## Output

- **FILE: FILE-2**
  - **SYNOPSIS:** Output:
    - `docs/requirements/requirements-inventory.yaml`
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:79) sets that as the phase output.

## Purpose

- **GOAL: GOAL-1**
  - **SYNOPSIS:** `PH-000` extracts every requirement-bearing statement into `RI-*` inventory items.
  - **BECAUSE:** The phase focuses on completeness, atomicity, and fidelity to the raw source.

- **GOAL: GOAL-2**
  - **SYNOPSIS:** `PH-000` classifies each extracted item by category.
  - **BECAUSE:** The output schema requires categories such as `functional`, `non_functional`, `constraint`, and `assumption`.

- **GOAL: GOAL-3**
  - **SYNOPSIS:** `PH-000` records what was explicitly deferred or left open.
  - **BECAUSE:** The schema includes `out_of_scope`, `coverage_check`, `coverage_verdict`, and `open_assumptions`.

## Required Output Shape

- **ENTITY: ENTITY-1**
  - **SYNOPSIS:** The top-level sections are:
    - `source_document`
    - `items`
    - `out_of_scope`
    - `coverage_check`
    - `coverage_verdict`
  - **BECAUSE:** That is the schema defined for `PH-000`.

- **ENTITY: ENTITY-2**
  - **SYNOPSIS:** Each inventory item contains:
    - `id`
    - `category`
    - `verbatim_quote`
    - `source_location`
    - `tags`
    - `rationale`
    - `open_assumptions`
  - **BECAUSE:** Those are the required fields for `RI-*` records.

## What Good Means

- **RULE: RULE-1**
  - **SYNOPSIS:** Every requirement-bearing statement in the raw requirements must appear as at least one `RI-*` item.
  - **BECAUSE:** Completeness is a core extraction focus of the phase.

- **RULE: RULE-2**
  - **SYNOPSIS:** Compound requirements must be split into separate `RI-*` items.
  - **BECAUSE:** Atomicity is explicitly required.

- **RULE: RULE-3**
  - **SYNOPSIS:** `verbatim_quote` must reproduce the original wording exactly.
  - **BECAUSE:** Fidelity forbids paraphrasing, summarization, or interpretation at this stage.

## Short Version

- **GOAL: GOAL-4**
  - **SYNOPSIS:** `PH-000` turns raw requirements text into a complete, atomic, and source-faithful inventory.
  - **BECAUSE:** It is the foundation for every later phase.
