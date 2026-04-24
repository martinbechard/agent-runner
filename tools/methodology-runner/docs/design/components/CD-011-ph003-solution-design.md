# Design: PH-003 Solution Design

## 1. Finality

This design explains how `PH-003` works from start to finish.

- **GOAL: GOAL-1** Produce the solution design
  - **SYNOPSIS:** `PH-003` turns the architecture design into one
    acceptance-ready `docs/design/solution-design.yaml` file.
  - **BECAUSE:** Later phases depend on this file.

## 2. Inputs And Outputs

- **FILE: FILE-1** Architecture design
  - **SYNOPSIS:** Primary input:
    - `docs/architecture/architecture-design.yaml`
  - **BECAUSE:** `PH-003` refines the chosen architecture into component-level
    ownership and interaction design.

- **FILE: FILE-2** Feature specification
  - **SYNOPSIS:** Traceability input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** The solution design must still trace back to feature intent.

- **FILE: FILE-3** Solution design
  - **SYNOPSIS:** Primary output:
    - `docs/design/solution-design.yaml`
  - **BECAUSE:** This is the phase output.

- **FILE: FILE-4** Prompt-runner module
  - **SYNOPSIS:** `tools/methodology-runner/src/methodology_runner/prompts/PR-026-ph003-solution-design.md`
    with:
    - embedded directive blocks for design and review discipline
    - fixed generic prompt-runner generator and judge roles
    - fixed phase input and output paths
  - **BECAUSE:** `PH-003` uses one predefined prompt-runner module.

## 3. Technical Directives

- **RULE: RULE-1** Read the architecture and feature inputs
  - **SYNOPSIS:** The phase must read
    `docs/architecture/architecture-design.yaml` and
    `docs/features/feature-specification.yaml`.
  - **BECAUSE:** The architecture design is the main source, and the feature
    spec keeps the design traceable.

- **RULE: RULE-2** Use the predefined prompt module
  - **SYNOPSIS:** The phase must use
    `tools/methodology-runner/src/methodology_runner/prompts/PR-026-ph003-solution-design.md`.
  - **BECAUSE:** `PH-003` should not build a new prompt module for each run.

- **RULE: RULE-3** Keep the phase directives inside the module
  - **SYNOPSIS:** The prompt module must contain the PH-003 solution-design
    directives and embedded traceability, structured-design, and
    structured-review guidance blocks that the generic prompt-runner roles
    consume.
  - **BECAUSE:** The module should be self-contained and replayable.

- **RULE: RULE-4** Write one solution design file
  - **SYNOPSIS:** The phase must write exactly one file at
    `docs/design/solution-design.yaml`.
  - **BECAUSE:** Later phases need one stable input file.

## 4. Workflow

- **PROCESS: PROCESS-1** Define the phase contract
  - **SYNOPSIS:** `PH-003` defines the input files, output path,
    responsibility rules, interaction rules, review rules, and output shape.
  - **READS:** `tools/methodology-runner/src/methodology_runner/phases.py`
    - **BECAUSE:** The phase registry is the source of truth.

- **PROCESS: PROCESS-2** Execute the prompt with prompt-runner
  - **SYNOPSIS:** The methodology runner runs the predefined PH-003 module
    with prompt-runner.
  - **USES:** `tools/methodology-runner/src/methodology_runner/orchestrator.py`
    - **BECAUSE:** The orchestrator owns the phase lifecycle.
  - **USES:** `tools/prompt-runner/src/prompt_runner/runner.py`
    - **BECAUSE:** That module executes the generator/judge revision loop.
  - **PROMPT-MODULE: PMOD-1** PH-003 prompt module
    - **SYNOPSIS:** The PH-003 prompt module is
      `tools/methodology-runner/src/methodology_runner/prompts/PR-026-ph003-solution-design.md`.
    - **READS:** `docs/architecture/architecture-design.yaml`
      - **BECAUSE:** That file is the main source for ownership and
        interaction design.
    - **READS:** `docs/features/feature-specification.yaml`
      - **BECAUSE:** That file keeps responsibilities traceable to feature intent.
    - **RULE:** Just-in-time source embedding
      - **SYNOPSIS:** The generator and judge embed `docs/architecture/architecture-design.yaml` and `docs/features/feature-specification.yaml` inline in `Context` with `{{INCLUDE:...}}`.
      - **BECAUSE:** The prompt should present architecture and feature sources where the design task uses them, not as a preamble.
    - **USES:** generic prompt-runner `Generator Agent`
      - **BECAUSE:** Artifact production uses the stable generator role.
    - **USES:** embedded PH-003 solution-design directives
      - **BECAUSE:** Phase-local ownership and interaction guidance lives in
        the prompt body.
    - **USES:** generic prompt-runner `Judge Agent`
      - **BECAUSE:** Review uses the stable judge role.
    - **USES:** embedded PH-003 review directives
      - **BECAUSE:** Phase-local review guidance lives in the prompt body.
    - **RULE:** Just-in-time artifact embedding
      - **SYNOPSIS:** The judge embeds the current solution design inline in `Context` with `{{RUNTIME_INCLUDE:docs/design/solution-design.yaml}}`.
      - **BECAUSE:** The artifact under review should appear where the review instructions compare it to architecture and feature intent.
  - **RESUMES:** the same artifact path across iterations
    - **BECAUSE:** `PH-003` revises one file rather than creating drafts.

- **PROCESS: PROCESS-3** Accept or reject the phase result
  - **SYNOPSIS:** The phase is accepted only when the prompt-runner loop
    passes and the resulting artifact is accepted as the phase output.
  - **VALIDATES:** `docs/design/solution-design.yaml`
    - **BECAUSE:** The output file must exist before the phase can pass.
  - **USES:** `tools/methodology-runner/src/methodology_runner/phase_3_validation.py`
    - **BECAUSE:** `PH-003` uses deterministic checks for schema, feature
      coverage, dependency references, and interaction shape.
  - **BECAUSE:** `PH-003` passes only when both the deterministic checks and
    the judge review pass.

## 5. Constraints

- **RULE: RULE-5** No blurry ownership
  - **SYNOPSIS:** Components must have clear, non-overlapping responsibility
    boundaries.
  - **BECAUSE:** Later contract and implementation work depends on clear ownership.

- **RULE: RULE-6** Preserve architecture boundaries
  - **SYNOPSIS:** The phase must keep the module boundary already chosen in
    `docs/architecture/architecture-design.yaml`. It must not split one
    upstream module into multiple downstream modules or merge distinct
    upstream modules.
  - **BECAUSE:** PH-003 refines the chosen architecture. It does not redesign it.

- **RULE: RULE-7** No fake interactions
  - **SYNOPSIS:** The phase must not create interactions for rhetorical or
    unnecessary boundaries.
  - **BECAUSE:** Later contract design depends on real interaction scope.

- **RULE: RULE-7A** Processing functions need examples
  - **SYNOPSIS:** Every specified processing function includes at least one
    concrete example with both `input` and `output` values.
  - **BECAUSE:** Later contract and implementation phases need concrete
    behavior examples, not only abstract operation names.

- **RULE: RULE-7B** UI surfaces need HTML mockups
  - **SYNOPSIS:** Every specified UI surface includes an `html_mockup` HTML
    fragment that shows representative structure and visible content.
  - **BECAUSE:** UI implementation needs a concrete target that can be carried
    into contracts and implementation slices.

## 6. Output Shape

- **ENTITY: ENTITY-1** Top-level output shape
  - **SYNOPSIS:** The top-level sections are:
    - `components`
    - `interactions`
  - **BECAUSE:** That is the schema required by the PH-003 phase contract.

- **ENTITY: ENTITY-2** Component fields
  - **SYNOPSIS:** Each component contains:
    - `id`
    - `name`
    - `responsibility`
    - `technology`
    - `feature_realization_map`
    - `dependencies`
    - `processing_functions`
    - `ui_surfaces`
  - **BECAUSE:** Those are the fields downstream phases rely on.

## 7. Definition Of Good

- **RULE: RULE-8** Feature realization coverage
  - **SYNOPSIS:** Every `FT-*` feature must appear in at least one component's
    `feature_realization_map`.
  - **BECAUSE:** Later phases depend on explicit feature realization.

- **RULE: RULE-9** Real interaction coverage
  - **SYNOPSIS:** Every dependency that implies meaningful runtime or data flow
    must have an explicit `INT-*` interaction.
  - **BECAUSE:** Later contract design depends on complete interaction scope.

- **RULE: RULE-9A** Human-mediated architecture handoffs still require interactions
  - **SYNOPSIS:** When the preserved architecture defines a documentation-to-runtime handoff, verification-to-runtime handoff, or other human-mediated linkage as a real integration point, the solution design must keep an explicit `INT-*` interaction for it.
  - **BECAUSE:** Downstream contracts and implementation work still need that dependency to be explicit, even when a human rather than a program mediates the handoff.

- **RULE: RULE-10** Clear component boundaries
  - **SYNOPSIS:** Components must express real ownership boundaries that would
    help downstream contracts and implementation.
  - **BECAUSE:** Later phases depend on a clear component split.

- **RULE: RULE-10A** Concrete function and UI elaboration
  - **SYNOPSIS:** Processing functions include example cases, and UI surfaces
    include HTML mockups whenever they are declared.
  - **BECAUSE:** These concrete examples improve downstream fidelity without
    changing architecture boundaries.

- **RULE: RULE-11** Deterministic and judge checks both pass
  - **SYNOPSIS:** The phase passes only if the deterministic validator passes
    and the judge returns `VERDICT: pass`.
  - **BECAUSE:** `PH-003` needs both shape checks and content checks.

## 8. Test Cases

- **TEST CASE: TC-1** Feature realization coverage
  - **SYNOPSIS:** Run the phase on a feature spec with known `FT-*` items and
    confirm every feature appears in a `feature_realization_map`.
  - **BECAUSE:** The design depends on full feature realization coverage.

- **TEST CASE: TC-2** Architecture-boundary preservation
  - **SYNOPSIS:** Run the phase on a one-module architecture and confirm the
    solution design does not invent extra components or fake interactions.
  - **BECAUSE:** The phase must refine the architecture, not redesign it.

- **TEST CASE: TC-3** Processing and UI concreteness
  - **SYNOPSIS:** Validate that declared processing functions require
    input/output examples and declared UI surfaces require HTML mockups.
  - **BECAUSE:** The added fields should be mechanically enforced instead of
    relying only on semantic review.
