# PH-007

- **PROCESS: PROCESS-1**
  - **SYNOPSIS:** `PH-007` is Verification Sweep.
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:991) defines `phase_id="PH-007-verification-sweep"`.

## Inputs

- **FILE: FILE-1**
  - **SYNOPSIS:** Primary input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** End-to-end verification is derived from features and acceptance criteria.

- **FILE: FILE-2**
  - **SYNOPSIS:** Validation-reference inputs:
    - `docs/implementation/implementation-plan.yaml`
    - `docs/design/solution-design.yaml`
    - `docs/requirements/requirements-inventory.yaml`
  - **BECAUSE:** The verification sweep must trace requirements through design and implementation planning.

## Output

- **FILE: FILE-3**
  - **SYNOPSIS:** Output:
    - `docs/verification/verification-report.yaml`
  - **BECAUSE:** [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py:1022) sets that as the phase output.

## Purpose

- **GOAL: GOAL-1**
  - **SYNOPSIS:** `PH-007` defines end-to-end tests that exercise features through concrete setup, actions, and assertions.
  - **BECAUSE:** Test specificity is a core extraction focus of the phase.

- **GOAL: GOAL-2**
  - **SYNOPSIS:** `PH-007` builds a traceability matrix from `RI-*` through `FT-*`, `AC-*`, and `E2E-*`.
  - **BECAUSE:** Chain completeness is the central verification objective of the phase.

- **GOAL: GOAL-3**
  - **SYNOPSIS:** `PH-007` summarizes overall coverage and flags uncovered requirements.
  - **BECAUSE:** Coverage gaps must be explicit, quantified, and attributable.

## Required Output Shape

- **ENTITY: ENTITY-1**
  - **SYNOPSIS:** The top-level sections are:
    - `e2e_tests`
    - `traceability_matrix`
    - `coverage_summary`
  - **BECAUSE:** That is the schema defined for `PH-007`.

- **ENTITY: ENTITY-2**
  - **SYNOPSIS:** Each E2E test contains:
    - `id`
    - `name`
    - `feature_ref`
    - `acceptance_criteria_refs`
    - `type`
    - `setup`
    - `actions`
    - `assertions`
  - **BECAUSE:** Those are the required fields for end-to-end test records.

## What Good Means

- **RULE: RULE-1**
  - **SYNOPSIS:** Every `RI-*` must trace through `FT-*` and `AC-*` to at least one `E2E-*` test.
  - **BECAUSE:** Chain completeness is the primary extraction focus of the phase.

- **RULE: RULE-2**
  - **SYNOPSIS:** E2E tests must verify business-specific outcomes, not generic “it loads” behavior.
  - **BECAUSE:** The judge guidance explicitly rejects superficial tests.

- **RULE: RULE-3**
  - **SYNOPSIS:** Features handling input or external data must have negative or boundary-path coverage.
  - **BECAUSE:** Negative coverage is explicitly required.

## Short Version

- **GOAL: GOAL-4**
  - **SYNOPSIS:** `PH-007` turns the whole methodology chain into explicit end-to-end verification and coverage accounting.
  - **BECAUSE:** It is the final proof that requirements remain traceable through all intermediate phases.
