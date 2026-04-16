# Design: PH-001 Feature Specification

## 1. Finality

This design explains how `PH-001` works from start to finish.

- **GOAL: GOAL-1** Produce the feature specification
  - **SYNOPSIS:** `PH-001` turns the requirements inventory into one
    acceptance-ready `docs/features/feature-specification.yaml` file.
  - **BECAUSE:** Later phases depend on this file.

## 2. Inputs And Outputs

This section names the files that the phase uses.

- **FILE: FILE-1** Requirements inventory
  - **SYNOPSIS:** Primary input:
    - `docs/requirements/requirements-inventory.yaml`
  - **BECAUSE:** `PH-001` groups `RI-*` items into `FT-*` features.

- **FILE: FILE-2** Raw requirements
  - **SYNOPSIS:** Validation-reference input:
    - `docs/requirements/raw-requirements.md`
  - **BECAUSE:** The phase checks that feature grouping stays faithful to the
    original request.

- **FILE: FILE-3** Feature specification
  - **SYNOPSIS:** Primary output:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** This is the phase output.

- **FILE: FILE-4** Prompt-runner module
  - **SYNOPSIS:** `.methodology/docs/prompts/PR-023-ph001-feature-specification.md`
    with:
    - embedded generator agent definition
    - embedded judge agent definition
    - fixed phase input and output paths
  - **BECAUSE:** `PH-001` uses one predefined prompt-runner module.

## 3. Technical Directives

This section states the technical directives that shape the phase
implementation.

- **RULE: RULE-1** Read the inventory and raw requirements
  - **SYNOPSIS:** The phase must read
    `docs/requirements/requirements-inventory.yaml` and
    `docs/requirements/raw-requirements.md`.
  - **BECAUSE:** The inventory is the main source, and the raw requirements
    are used to catch drift.

- **RULE: RULE-2** Use the predefined prompt module
  - **SYNOPSIS:** The phase must use
    `.methodology/docs/prompts/PR-023-ph001-feature-specification.md`.
  - **BECAUSE:** `PH-001` should not build a new prompt module for each run.

- **RULE: RULE-3** Keep the generator and judge setup inside the module
  - **SYNOPSIS:** The prompt module must contain the `Generator Agent` and
    `Judge Agent` definitions, the shared traceability skill reference, and
    the PH-001-specific grouping and review rules.
  - **BECAUSE:** The module should be self-contained.

- **RULE: RULE-4** Write one feature specification file
  - **SYNOPSIS:** The phase must write exactly one file at
    `docs/features/feature-specification.yaml`.
  - **BECAUSE:** Later phases need one stable input file.

## 4. Workflow

This section describes the phase steps.

- **PROCESS: PROCESS-1** Define the phase contract
  - **SYNOPSIS:** `PH-001` defines the input files, output path, feature
    grouping rules, judge rules, and output shape.
  - **READS:** `.methodology/src/cli/methodology_runner/phases.py`
    - **BECAUSE:** The phase registry is the source of truth.
  - **BECAUSE:** The run needs this contract before it starts.

- **PROCESS: PROCESS-2** Execute the prompts with prompt-runner
  - **SYNOPSIS:** The methodology runner runs the predefined PH-001 module
    with prompt-runner.
  - **USES:** `.methodology/src/cli/methodology_runner/orchestrator.py`
    - **BECAUSE:** The orchestrator owns the phase lifecycle and
      prompt-runner invocation.
  - **USES:** `.prompt-runner/src/cli/prompt_runner/runner.py`
    - **BECAUSE:** That module executes the generator/judge revision loop.
  - **PROMPT-MODULE: PMOD-1** PH-001 prompt-runner input file
    - **SYNOPSIS:** The PH-001 prompt-runner input file is
      `.methodology/docs/prompts/PR-023-ph001-feature-specification.md`.
    - **BECAUSE:** The phase uses one fixed module shape.
    - **READS:** `docs/requirements/requirements-inventory.yaml`
      - **BECAUSE:** That file is the main source for feature grouping.
    - **READS:** `docs/requirements/raw-requirements.md`
      - **BECAUSE:** That file is used to check semantic fidelity.
    - **AGENT:** `Generator Agent`
      - **SYNOPSIS:** Embedded generator definition in the PH-001 module.
      - **BECAUSE:** The generator setup is fixed for this phase.
      - **SKILLS:** `traceability-discipline`
        - **SYNOPSIS:** Preserve source meaning, keep coverage explicit, and
          keep every `RI-*` item traceable.
        - **BECAUSE:** `PH-001` must stay grounded in the source inventory.
      - **RULE:** Prompt-local feature grouping directives
        - **SYNOPSIS:** The module itself defines how to group `RI-*` items
          into `FT-*` features, write `AC-*` items, and declare dependencies
          or `out_of_scope` entries.
        - **BECAUSE:** PH-001-specific grouping behavior now lives in the
          prompt, not in a phase-only skill.
    - **AGENT:** `Judge Agent`
      - **SYNOPSIS:** Embedded judge definition in the PH-001 module.
      - **BECAUSE:** The judge setup is fixed for this phase.
      - **SKILLS:** `traceability-discipline`
        - **BECAUSE:** The judge also needs the same traceability rules.
      - **RULE:** Prompt-local feature review directives
        - **SYNOPSIS:** The module itself defines the PH-001 review passes for
          coverage, scope, vague criteria, dependency defects, and exact-meaning drift.
        - **BECAUSE:** PH-001-specific review behavior now lives in the
          prompt, not in a phase-only skill.
    - **PROMPT-PAIR: Prompt 1**
      - **PROMPT:** `Generator`
        - **SYNOPSIS:** Reads the requirements inventory and raw requirements
          and writes `docs/features/feature-specification.yaml`.
        - **BECAUSE:** The generator owns artifact production.
        - **USES:** `Generator Agent`
          - **BECAUSE:** The prompt pair should use the embedded generator
            definition already declared in the prompt module.
        - **USES:** `traceability-discipline`
          - **BECAUSE:** The generator needs the traceability discipline
            already defined under the generator agent definition.
        - **USES:** prompt-local PH-001 grouping directives
          - **BECAUSE:** The generator's phase-specific behavior is embedded
            in the module.
      - **PROMPT:** `Judge`
        - **SYNOPSIS:** Reviews vague `AC-*` items, orphaned `RI-*` items,
          unsupported feature invention, dependency defects, and drift from the
          source requirements.
        - **BECAUSE:** The judge decides whether the file passes or needs
          another revision.
        - **USES:** `Judge Agent`
          - **BECAUSE:** The prompt pair should use the embedded judge
            definition already declared in the prompt module.
        - **USES:** `traceability-discipline`
          - **BECAUSE:** The judge needs the traceability discipline already
            defined under the judge agent definition.
        - **USES:** prompt-local PH-001 review directives
          - **BECAUSE:** The judge's phase-specific behavior is embedded in
            the module.
  - **READS:** embedded prompt-file agent definitions
    - **BECAUSE:** `PH-001` keeps its fixed generator and judge setup in the
      module.
  - **LAUNCHES:** generator session
    - **BECAUSE:** The artifact must be produced before it can be judged.
  - **LAUNCHES:** judge session
    - **BECAUSE:** The artifact must be reviewed for phase readiness and
      either passed, revised, or escalated.
  - **RESUMES:** the same artifact path across iterations
    - **BECAUSE:** `PH-001` revises the same output file. It does not create
      draft variants.

- **PROCESS: PROCESS-3** Accept or reject the phase result
  - **SYNOPSIS:** The phase is accepted only when the prompt-runner loop passes
    and the resulting artifact is accepted as the phase output.
  - **VALIDATES:** `docs/features/feature-specification.yaml`
    - **BECAUSE:** The output file must exist before the phase can pass.
  - **USES:** `scripts/phase-1-deterministic-validation.py`
    - **BECAUSE:** `PH-001` uses deterministic checks for schema, feature
      coverage, dependency references, and top-level shape.
  - **BECAUSE:** `PH-001` passes only when both the deterministic checks and
    the judge review pass.
  - **PRODUCES:** `docs/features/feature-specification.yaml`
    - **BECAUSE:** That artifact is the durable output consumed by `PH-002`
      and later phases.

## 5. Constraints

This section states the main limits on the phase.

- **RULE: RULE-5** No unsupported scope creep
  - **SYNOPSIS:** The phase must not invent features that are not traceable to
    the requirements inventory.
  - **BECAUSE:** `PH-001` is a grouping and clarification phase, not a product
    expansion phase.

- **RULE: RULE-6** No vague acceptance criteria
  - **SYNOPSIS:** `AC-*` entries must be concrete and reviewable at the
    feature level.
  - **BECAUSE:** Later phases need clear completion conditions.

- **RULE: RULE-7** One fixed prompt module
  - **SYNOPSIS:** `PH-001` must use the predefined prompt module instead of
    building a new module per run.
  - **BECAUSE:** The module shape should stay stable.

## 6. Output Shape

This section states what the output file contains.

- **ENTITY: ENTITY-1** Top-level output shape
  - **SYNOPSIS:** The top-level sections are:
    - `features`
    - `out_of_scope`
    - `cross_cutting_concerns`
  - **BECAUSE:** That is the schema required by the PH-001 phase contract.

- **ENTITY: ENTITY-2** Feature fields
  - **SYNOPSIS:** Each feature contains:
    - `id`
    - `name`
    - `description`
    - `source_inventory_refs`
    - `acceptance_criteria`
    - `dependencies`
  - **BECAUSE:** Those are the fields downstream phases rely on.

## 7. Definition Of Good

This section states when the phase passes.

- **RULE: RULE-8** Inventory coverage
  - **SYNOPSIS:** Every `RI-*` item must appear in at least one feature's
    `source_inventory_refs` list or in `out_of_scope` with a reason.
  - **BECAUSE:** The phase must preserve full inventory coverage.

- **RULE: RULE-9** Testable feature criteria
  - **SYNOPSIS:** Every `AC-*` item must be specific enough to support a clear
    pass or fail review.
  - **BECAUSE:** Downstream design and verification depend on concrete feature
    obligations.

- **RULE: RULE-10** Dependency correctness
  - **SYNOPSIS:** Feature dependencies must refer only to real `FT-*` IDs and
    must reflect real sequencing or data dependencies.
  - **BECAUSE:** Later phases depend on these relations.

- **RULE: RULE-11** Deterministic and judge checks both pass
  - **SYNOPSIS:** The phase passes only if the deterministic validator passes
    and the judge returns `VERDICT: pass`.
  - **BECAUSE:** `PH-001` needs both shape checks and content checks.

## 8. Test Cases

This section lists the tests the phase design expects.

- **TEST CASE: TC-1** Inventory coverage
  - **SYNOPSIS:** Run the phase on an inventory with known `RI-*` items and
    confirm every item is either referenced by a feature or listed in
    `out_of_scope`.
  - **BECAUSE:** The design depends on full `RI-*` coverage.

- **TEST CASE: TC-2** Embedded agent definitions
  - **SYNOPSIS:** Confirm the PH-001 module contains both `Generator Agent`
    and `Judge Agent` with their fixed `SKILLS`.
  - **BECAUSE:** The module is supposed to be self-contained.

- **TEST CASE: TC-3** Output file path
  - **SYNOPSIS:** Run PH-001 and confirm the artifact written is
    `docs/features/feature-specification.yaml`.
  - **BECAUSE:** The phase should produce one stable output file.

- **TEST CASE: TC-4** Vague acceptance criteria rejection
  - **SYNOPSIS:** Run the phase with a feature spec that uses vague acceptance
    language and confirm the deterministic and judge loop rejects it.
  - **BECAUSE:** Weak feature criteria should not pass this phase.
