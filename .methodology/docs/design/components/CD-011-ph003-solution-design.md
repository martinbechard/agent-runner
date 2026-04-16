# Design: PH-003 Solution Design

## 1. Finality

This design explains how `PH-003` works from start to finish.

- **GOAL: GOAL-1** Produce the solution design
  - **SYNOPSIS:** `PH-003` turns the architecture stack manifest into one
    acceptance-ready `docs/design/solution-design.yaml` file.
  - **BECAUSE:** Later phases depend on this file.

## 2. Inputs And Outputs

This section names the files that the phase uses.

- **FILE: FILE-1** Stack manifest
  - **SYNOPSIS:** Primary input:
    - `docs/architecture/stack-manifest.yaml`
  - **BECAUSE:** `PH-003` refines the architecture into per-component design.

- **FILE: FILE-2** Feature specification
  - **SYNOPSIS:** Traceability input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** The solution design must still trace back to feature intent.

- **FILE: FILE-3** Solution design
  - **SYNOPSIS:** Primary output:
    - `docs/design/solution-design.yaml`
  - **BECAUSE:** This is the phase output.

- **FILE: FILE-4** Prompt-runner module
  - **SYNOPSIS:** `.methodology/docs/prompts/PR-026-ph003-solution-design.md`
    with:
    - embedded generator agent definition
    - embedded judge agent definition
    - fixed phase input and output paths
  - **BECAUSE:** `PH-003` uses one predefined prompt-runner module.

## 3. Technical Directives

This section states the technical directives that shape the phase
implementation.

- **RULE: RULE-1** Read the architecture and feature inputs
  - **SYNOPSIS:** The phase must read `docs/architecture/stack-manifest.yaml`
    and `docs/features/feature-specification.yaml`.
  - **BECAUSE:** The stack manifest is the main source, and the feature spec
    is used to keep the design traceable.

- **RULE: RULE-2** Use the predefined prompt module
  - **SYNOPSIS:** The phase must use
    `.methodology/docs/prompts/PR-026-ph003-solution-design.md`.
  - **BECAUSE:** `PH-003` should not build a new prompt module for each run.

- **RULE: RULE-3** Keep the generator and judge setup inside the module
  - **SYNOPSIS:** The prompt module must contain the `Generator Agent` and
    `Judge Agent` definitions, the shared traceability skill reference, and
    the PH-003-specific design rules.
  - **BECAUSE:** The module should be self-contained.

- **RULE: RULE-4** Write one solution design file
  - **SYNOPSIS:** The phase must write exactly one file at
    `docs/design/solution-design.yaml`.
  - **BECAUSE:** Later phases need one stable input file.

## 4. Workflow

This section describes the phase steps.

- **PROCESS: PROCESS-1** Define the phase contract
  - **SYNOPSIS:** `PH-003` defines the input files, output path,
    responsibility rules, interaction rules, judge rules, and output shape.
  - **READS:** `.methodology/src/cli/methodology_runner/phases.py`
    - **BECAUSE:** The phase registry is the source of truth.
  - **BECAUSE:** The run needs this contract before it starts.

- **PROCESS: PROCESS-2** Execute the prompts with prompt-runner
  - **SYNOPSIS:** The methodology runner runs the predefined PH-003 module
    with prompt-runner.
  - **USES:** `.methodology/src/cli/methodology_runner/orchestrator.py`
    - **BECAUSE:** The orchestrator owns the phase lifecycle and
      prompt-runner invocation.
  - **USES:** `.prompt-runner/src/cli/prompt_runner/runner.py`
    - **BECAUSE:** That module executes the generator/judge revision loop.
  - **PROMPT-MODULE: PMOD-1** PH-003 prompt-runner input file
    - **SYNOPSIS:** The PH-003 prompt-runner input file is
      `.methodology/docs/prompts/PR-026-ph003-solution-design.md`.
    - **BECAUSE:** The phase uses one fixed module shape.
    - **READS:** `docs/architecture/stack-manifest.yaml`
      - **BECAUSE:** That file is the main source for solution design.
    - **READS:** `docs/features/feature-specification.yaml`
      - **BECAUSE:** That file keeps component responsibilities traceable to
        feature intent.
    - **AGENT:** `Generator Agent`
      - **SYNOPSIS:** Embedded generator definition in the PH-003 module.
      - **BECAUSE:** The generator setup is fixed for this phase.
      - **SKILLS:** `traceability-discipline`
        - **SYNOPSIS:** Keep responsibilities and interactions grounded in the
          stack manifest and feature spec.
        - **BECAUSE:** `PH-003` must stay traceable.
      - **RULE:** Prompt-local solution-design directives
        - **SYNOPSIS:** The module itself defines ownership boundaries,
          feature-realization rules, and interaction rules.
        - **BECAUSE:** PH-003-specific generation behavior now lives in the
          prompt, not in a phase-only skill.
    - **AGENT:** `Judge Agent`
      - **SYNOPSIS:** Embedded judge definition in the PH-003 module.
      - **BECAUSE:** The judge setup is fixed for this phase.
      - **SKILLS:** `traceability-discipline`
        - **BECAUSE:** The judge also needs the same traceability rules.
      - **RULE:** Prompt-local solution-design review directives
        - **SYNOPSIS:** The module itself defines the PH-003 review checks for
          ownership overlap, weak realization maps, invented interactions, and traceability defects.
        - **BECAUSE:** PH-003-specific review behavior now lives in the
          prompt, not in a phase-only skill.
    - **PROMPT-PAIR: Prompt 1**
      - **PROMPT:** `Generator`
        - **SYNOPSIS:** Reads the stack manifest and feature specification and
          writes `docs/design/solution-design.yaml`.
        - **BECAUSE:** The generator owns artifact production.
        - **USES:** `Generator Agent`
          - **BECAUSE:** The prompt pair should use the embedded generator
            definition already declared in the prompt module.
        - **USES:** `traceability-discipline`
          - **BECAUSE:** The generator needs the traceability discipline
            already defined under the generator agent definition.
        - **USES:** prompt-local PH-003 design directives
          - **BECAUSE:** The generator's phase-specific behavior is embedded
            in the module.
      - **PROMPT:** `Judge`
        - **SYNOPSIS:** Reviews ownership boundaries, interaction coverage,
          unsupported decomposition, and feature traceability.
        - **BECAUSE:** The judge decides whether the file passes or needs
          another revision.
        - **USES:** `Judge Agent`
          - **BECAUSE:** The prompt pair should use the embedded judge
            definition already declared in the prompt module.
        - **USES:** `traceability-discipline`
          - **BECAUSE:** The judge needs the traceability discipline already
            defined under the judge agent definition.
        - **USES:** prompt-local PH-003 review directives
          - **BECAUSE:** The judge's phase-specific behavior is embedded in
            the module.
  - **READS:** embedded prompt-file agent definitions
    - **BECAUSE:** `PH-003` keeps its fixed generator and judge setup in the
      module.
  - **LAUNCHES:** generator session
    - **BECAUSE:** The artifact must be produced before it can be judged.
  - **LAUNCHES:** judge session
    - **BECAUSE:** The artifact must be reviewed for phase readiness and
      either passed, revised, or escalated.
  - **RESUMES:** the same artifact path across iterations
    - **BECAUSE:** `PH-003` revises the same output file. It does not create
      draft variants.

- **PROCESS: PROCESS-3** Accept or reject the phase result
  - **SYNOPSIS:** The phase is accepted only when the prompt-runner loop passes
    and the resulting artifact is accepted as the phase output.
  - **VALIDATES:** `docs/design/solution-design.yaml`
    - **BECAUSE:** The output file must exist before the phase can pass.
  - **USES:** `scripts/phase-3-deterministic-validation.py`
    - **BECAUSE:** `PH-003` uses deterministic checks for schema, feature
      coverage, dependency references, and interaction shape.
  - **BECAUSE:** `PH-003` passes only when both the deterministic checks and
    the judge review pass.
  - **PRODUCES:** `docs/design/solution-design.yaml`
    - **BECAUSE:** That artifact is the durable output consumed by `PH-004`
      and later phases.

## 5. Constraints

This section states the main limits on the phase.

- **RULE: RULE-5** No blurry ownership
  - **SYNOPSIS:** Components must have clear, non-overlapping responsibility
    boundaries.
  - **BECAUSE:** Later contract and implementation work depends on clear
    ownership.

- **RULE: RULE-5A** Preserve architecture boundaries
  - **SYNOPSIS:** The phase must keep the component boundary already chosen in
    `docs/architecture/stack-manifest.yaml`. It must not split one upstream
    component into multiple downstream components or merge distinct upstream
    components.
  - **BECAUSE:** PH-003 refines ownership inside the chosen architecture. It
    does not redesign the architecture.

- **RULE: RULE-6** No fake interactions
  - **SYNOPSIS:** The phase must not create interactions for rhetorical or
    unnecessary boundaries.
  - **BECAUSE:** Later contract design depends on real interaction scope.

- **RULE: RULE-6A** Empty interactions are valid
  - **SYNOPSIS:** A phase result with `interactions: []` is correct when the
    preserved architecture has one component or no real cross-component flow.
  - **BECAUSE:** PH-004 should receive only real interaction boundaries.

- **RULE: RULE-7** One fixed prompt module
  - **SYNOPSIS:** `PH-003` must use the predefined prompt module instead of
    building a new module per run.
  - **BECAUSE:** The module shape should stay stable.

## 6. Output Shape

This section states what the output file contains.

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
  - **BECAUSE:** Those are the fields downstream phases rely on.

## 7. Definition Of Good

This section states when the phase passes.

- **RULE: RULE-8** Feature realization coverage
  - **SYNOPSIS:** Every `FT-*` feature must appear in at least one component's
    `feature_realization_map`.
  - **BECAUSE:** Later phases depend on explicit feature realization.

- **RULE: RULE-9** Real interaction coverage
  - **SYNOPSIS:** Every dependency that implies meaningful runtime or data flow
    must have an explicit `INT-*` interaction.
  - **BECAUSE:** Later contract design depends on complete interaction scope.

- **RULE: RULE-10** Clear component boundaries
  - **SYNOPSIS:** Components must express real ownership boundaries that would
    help downstream contracts and implementation.
  - **BECAUSE:** Later phases depend on a clear component split.

- **RULE: RULE-10A** No internal decomposition pressure
  - **SYNOPSIS:** The phase should not create extra internal components merely
    to make the solution design look richer.
  - **BECAUSE:** Artificial decomposition weakens traceability and creates fake
    contract work in later phases.

- **RULE: RULE-11** Deterministic and judge checks both pass
  - **SYNOPSIS:** The phase passes only if the deterministic validator passes
    and the judge returns `VERDICT: pass`.
  - **BECAUSE:** `PH-003` needs both shape checks and content checks.

## 8. Test Cases

This section lists the tests the phase design expects.

- **TEST CASE: TC-1** Feature realization coverage
  - **SYNOPSIS:** Run the phase on a feature spec with known `FT-*` items and
    confirm every feature appears in a `feature_realization_map`.
  - **BECAUSE:** The design depends on full feature realization coverage.

- **TEST CASE: TC-2** Embedded agent definitions
  - **SYNOPSIS:** Confirm the PH-003 module contains both `Generator Agent`
    and `Judge Agent` with their fixed `SKILLS`.
  - **BECAUSE:** The module is supposed to be self-contained.

- **TEST CASE: TC-3** Output file path
  - **SYNOPSIS:** Run PH-003 and confirm the artifact written is
    `docs/design/solution-design.yaml`.
  - **BECAUSE:** The phase should produce one stable output file.

- **TEST CASE: TC-4** Missing interaction rejection
  - **SYNOPSIS:** Run the phase with a dependency that implies data flow but no
    matching `INT-*` interaction and confirm the deterministic and judge loop
    rejects it.
  - **BECAUSE:** Missing real interactions should not pass this phase.
