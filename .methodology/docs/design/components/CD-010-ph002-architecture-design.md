# Design: PH-002 Architecture

## 1. Finality

This design explains how `PH-002` works from start to finish.

- **GOAL: GOAL-1** Produce the architecture stack manifest
  - **SYNOPSIS:** `PH-002` turns the feature specification into one
    acceptance-ready `docs/architecture/stack-manifest.yaml` file.
  - **BECAUSE:** Later phases depend on this file.

## 2. Inputs And Outputs

This section names the files that the phase uses.

- **FILE: FILE-1** Feature specification
  - **SYNOPSIS:** Primary input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** `PH-002` decomposes features into architecture components.

- **FILE: FILE-2** Requirements inventory
  - **SYNOPSIS:** Traceability input:
    - `docs/requirements/requirements-inventory.yaml`
  - **BECAUSE:** The architecture must still trace back to the original
    inventory.

- **FILE: FILE-3** Raw requirements
  - **SYNOPSIS:** Validation-reference input:
    - `docs/requirements/raw-requirements.md`
  - **BECAUSE:** The phase checks that architecture choices do not drift from
    explicit source constraints.

- **FILE: FILE-4** Stack manifest
  - **SYNOPSIS:** Primary output:
    - `docs/architecture/stack-manifest.yaml`
  - **BECAUSE:** This is the phase output.

- **FILE: FILE-5** Prompt-runner module
  - **SYNOPSIS:** `.methodology/docs/prompts/PR-024-ph002-architecture.md`
    with:
    - embedded generator agent definition
    - embedded judge agent definition
    - fixed phase input and output paths
  - **BECAUSE:** `PH-002` uses one predefined prompt-runner module.

## 3. Technical Directives

This section states the technical directives that shape the phase
implementation.

- **RULE: RULE-1** Read the feature spec and traceability inputs
  - **SYNOPSIS:** The phase must read
    `docs/features/feature-specification.yaml`,
    `docs/requirements/requirements-inventory.yaml`, and
    `docs/requirements/raw-requirements.md`.
  - **BECAUSE:** The feature spec is the main source, and the upstream files
    are used to keep the architecture grounded.

- **RULE: RULE-2** Use the predefined prompt module
  - **SYNOPSIS:** The phase must use
    `.methodology/docs/prompts/PR-024-ph002-architecture.md`.
  - **BECAUSE:** `PH-002` should not build a new prompt module for each run.

- **RULE: RULE-3** Keep the generator and judge setup inside the module
  - **SYNOPSIS:** The prompt module must contain the `Generator Agent` and
    `Judge Agent` definitions, the shared traceability skill reference, and
    the PH-002-specific architecture rules.
  - **BECAUSE:** The module should be self-contained.

- **RULE: RULE-4** Write one stack manifest file
  - **SYNOPSIS:** The phase must write exactly one file at
    `docs/architecture/stack-manifest.yaml`.
  - **BECAUSE:** Later phases need one stable input file.

## 4. Workflow

This section describes the phase steps.

- **PROCESS: PROCESS-1** Define the phase contract
  - **SYNOPSIS:** `PH-002` defines the input files, output path,
    decomposition rules, judge rules, and output shape.
  - **READS:** `.methodology/src/cli/methodology_runner/phases.py`
    - **BECAUSE:** The phase registry is the source of truth.
  - **BECAUSE:** The run needs this contract before it starts.

- **PROCESS: PROCESS-2** Execute the prompts with prompt-runner
  - **SYNOPSIS:** The methodology runner runs the predefined PH-002 module
    with prompt-runner.
  - **USES:** `.methodology/src/cli/methodology_runner/orchestrator.py`
    - **BECAUSE:** The orchestrator owns the phase lifecycle and
      prompt-runner invocation.
  - **USES:** `.prompt-runner/src/cli/prompt_runner/runner.py`
    - **BECAUSE:** That module executes the generator/judge revision loop.
  - **PROMPT-MODULE: PMOD-1** PH-002 prompt-runner input file
    - **SYNOPSIS:** The PH-002 prompt-runner input file is
      `.methodology/docs/prompts/PR-024-ph002-architecture.md`.
    - **BECAUSE:** The phase uses one fixed module shape.
    - **READS:** `docs/features/feature-specification.yaml`
      - **BECAUSE:** That file is the main source for architecture decisions.
    - **READS:** `docs/requirements/requirements-inventory.yaml`
      - **BECAUSE:** That file keeps feature decomposition traceable.
    - **READS:** `docs/requirements/raw-requirements.md`
      - **BECAUSE:** That file keeps exact source constraints visible.
    - **AGENT:** `Generator Agent`
      - **SYNOPSIS:** Embedded generator definition in the PH-002 module.
      - **BECAUSE:** The generator setup is fixed for this phase.
      - **SKILLS:** `traceability-discipline`
        - **SYNOPSIS:** Keep architecture choices grounded in the upstream
          feature and requirement artifacts.
        - **BECAUSE:** `PH-002` must stay traceable.
      - **RULE:** Prompt-local architecture directives
        - **SYNOPSIS:** The module itself defines decomposition discipline,
          technology-choice rules, real integration boundaries, and expertise
          wording.
        - **BECAUSE:** PH-002-specific generation behavior now lives in the
          prompt, not in phase-only skills.
    - **AGENT:** `Judge Agent`
      - **SYNOPSIS:** Embedded judge definition in the PH-002 module.
      - **BECAUSE:** The judge setup is fixed for this phase.
      - **SKILLS:** `traceability-discipline`
        - **BECAUSE:** The judge also needs the same traceability rules.
      - **RULE:** Prompt-local architecture review directives
        - **SYNOPSIS:** The module itself defines the PH-002 review checks for
          coverage gaps, bad decomposition, unsupported invention, and boundary defects.
        - **BECAUSE:** PH-002-specific review behavior now lives in the
          prompt, not in a phase-only skill.
    - **PROMPT-PAIR: Prompt 1**
      - **PROMPT:** `Generator`
        - **SYNOPSIS:** Reads the feature specification and upstream
          traceability inputs and writes `docs/architecture/stack-manifest.yaml`.
        - **BECAUSE:** The generator owns artifact production.
        - **USES:** `Generator Agent`
          - **BECAUSE:** The prompt pair should use the embedded generator
            definition already declared in the prompt module.
        - **USES:** `traceability-discipline`
          - **BECAUSE:** The generator needs the traceability discipline
            already defined under the generator agent definition.
        - **USES:** prompt-local PH-002 architecture directives
          - **BECAUSE:** The generator's phase-specific behavior is embedded
            in the module.
      - **PROMPT:** `Judge`
        - **SYNOPSIS:** Reviews feature coverage, decomposition quality,
          technology choices, expertise articulation, and integration
          boundaries.
        - **BECAUSE:** The judge decides whether the file passes or needs
          another revision.
        - **USES:** `Judge Agent`
          - **BECAUSE:** The prompt pair should use the embedded judge
            definition already declared in the prompt module.
        - **USES:** `traceability-discipline`
          - **BECAUSE:** The judge needs the traceability discipline already
            defined under the judge agent definition.
        - **USES:** prompt-local PH-002 architecture review directives
          - **BECAUSE:** The judge's phase-specific behavior is embedded in
            the module.
  - **READS:** embedded prompt-file agent definitions
    - **BECAUSE:** `PH-002` keeps its fixed generator and judge setup in the
      module.
  - **LAUNCHES:** generator session
    - **BECAUSE:** The artifact must be produced before it can be judged.
  - **LAUNCHES:** judge session
    - **BECAUSE:** The artifact must be reviewed for phase readiness and
      either passed, revised, or escalated.
  - **RESUMES:** the same artifact path across iterations
    - **BECAUSE:** `PH-002` revises the same output file. It does not create
      draft variants.

- **PROCESS: PROCESS-3** Accept or reject the phase result
  - **SYNOPSIS:** The phase is accepted only when the prompt-runner loop passes
    and the resulting artifact is accepted as the phase output.
  - **VALIDATES:** `docs/architecture/stack-manifest.yaml`
    - **BECAUSE:** The output file must exist before the phase can pass.
  - **USES:** `scripts/phase-2-deterministic-validation.py`
    - **BECAUSE:** `PH-002` uses deterministic checks for schema, feature
      coverage, integration references, and top-level shape.
  - **BECAUSE:** `PH-002` passes only when both the deterministic checks and
    the judge review pass.
  - **PRODUCES:** `docs/architecture/stack-manifest.yaml`
    - **BECAUSE:** That artifact is the durable output consumed by `PH-003`
      and later phases.

## 5. Constraints

This section states the main limits on the phase.

- **RULE: RULE-5** No unsupported decomposition
  - **SYNOPSIS:** The phase must not invent components, frameworks, services,
    or persistence layers that are not justified by the served features or
    source constraints.
  - **BECAUSE:** `PH-002` is an architecture phase, not an infrastructure wish
    list.

- **RULE: RULE-5A** Prefer the smallest valid architecture
  - **SYNOPSIS:** If one component can coherently serve the feature set, the
    phase should produce one component and an empty `integration_points` list.
  - **BECAUSE:** Later phases need a true architecture boundary, not a richer
    shape than the source justifies.

- **RULE: RULE-6** Keep expertise human-readable
  - **SYNOPSIS:** `expected_expertise` entries must be plain-language
    knowledge areas, not skill IDs, slugs, or plugin names.
  - **BECAUSE:** The architecture must stay decoupled from the skill catalog.

- **RULE: RULE-7** One fixed prompt module
  - **SYNOPSIS:** `PH-002` must use the predefined prompt module instead of
    building a new module per run.
  - **BECAUSE:** The module shape should stay stable.

## 6. Output Shape

This section states what the output file contains.

- **ENTITY: ENTITY-1** Top-level output shape
  - **SYNOPSIS:** The top-level sections are:
    - `components`
    - `integration_points`
    - `rationale`
  - **BECAUSE:** That is the schema required by the PH-002 phase contract.

- **ENTITY: ENTITY-2** Component fields
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
  - **BECAUSE:** Those are the fields downstream phases rely on.

## 7. Definition Of Good

This section states when the phase passes.

- **RULE: RULE-8** Feature coverage
  - **SYNOPSIS:** Every `FT-*` feature must be served by at least one
    component.
  - **BECAUSE:** Later phases can only refine what the architecture actually
    serves.

- **RULE: RULE-9** Real integration boundaries
  - **SYNOPSIS:** Every real cross-component boundary must appear as an
    integration point, and fake boundaries must not be introduced.
  - **BECAUSE:** Later contract design depends on accurate integration scope.

- **RULE: RULE-9A** Empty integration scope is valid
  - **SYNOPSIS:** A phase result with `integration_points: []` is correct when
    the chosen architecture has one component or no real cross-component
    boundary.
  - **BECAUSE:** PH-004 should receive an honest boundary picture, even when
    that picture is empty.

- **RULE: RULE-10** Coherent architecture choices
  - **SYNOPSIS:** Technology, runtime, framework, persistence, and expertise
    choices must fit the served features and source constraints.
  - **BECAUSE:** Later phases depend on a coherent architecture baseline.

- **RULE: RULE-11** Deterministic and judge checks both pass
  - **SYNOPSIS:** The phase passes only if the deterministic validator passes
    and the judge returns `VERDICT: pass`.
  - **BECAUSE:** `PH-002` needs both shape checks and content checks.

## 8. Test Cases

This section lists the tests the phase design expects.

- **TEST CASE: TC-1** Feature coverage
  - **SYNOPSIS:** Run the phase on a feature spec with known `FT-*` items and
    confirm every feature appears in `features_served`.
  - **BECAUSE:** The design depends on full feature coverage.

- **TEST CASE: TC-2** Embedded agent definitions
  - **SYNOPSIS:** Confirm the PH-002 module contains both `Generator Agent`
    and `Judge Agent` with their fixed `SKILLS`.
  - **BECAUSE:** The module is supposed to be self-contained.

- **TEST CASE: TC-3** Output file path
  - **SYNOPSIS:** Run PH-002 and confirm the artifact written is
    `docs/architecture/stack-manifest.yaml`.
  - **BECAUSE:** The phase should produce one stable output file.

- **TEST CASE: TC-4** Unsupported architecture rejection
  - **SYNOPSIS:** Run the phase with an architecture that adds unjustified
    components or frameworks and confirm the deterministic and judge loop
    rejects it.
  - **BECAUSE:** Unsupported architecture choices should not pass this phase.
