# Design: PH-002 Architecture

## 1. Finality

This design explains how `PH-002` works from start to finish.

- **GOAL: GOAL-1** Produce the architecture design
  - **SYNOPSIS:** `PH-002` turns the feature specification into one
    acceptance-ready `docs/architecture/architecture-design.yaml` file.
  - **BECAUSE:** Later phases depend on this file.

## 2. Inputs And Outputs

- **FILE: FILE-1** Feature specification
  - **SYNOPSIS:** Primary input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** `PH-002` derives the architecture from the feature layer.

- **FILE: FILE-2** Architecture design
  - **SYNOPSIS:** Primary output:
    - `docs/architecture/architecture-design.yaml`
  - **BECAUSE:** This is the durable output consumed by `PH-003`.

- **FILE: FILE-3** Prompt-runner module
  - **SYNOPSIS:** `.methodology/docs/prompts/PR-024-ph002-architecture.md`
    with:
    - fixed phase input and output paths
    - embedded directive blocks for `structured-design`,
      `structured-review`, and `traceability-discipline`
    - generic prompt-runner generator and judge roles
  - **BECAUSE:** `PH-002` uses one predefined prompt module.

## 3. Technical Directives

- **RULE: RULE-1** Read the feature specification
  - **SYNOPSIS:** The phase must read `docs/features/feature-specification.yaml`.
  - **BECAUSE:** The feature spec is the upstream authority for `PH-002`.

- **RULE: RULE-2** Use the predefined prompt module
  - **SYNOPSIS:** The phase must use
    `.methodology/docs/prompts/PR-024-ph002-architecture.md`.
  - **BECAUSE:** `PH-002` should not synthesize a new module per run.

- **RULE: RULE-3** Keep the specialized directives inside the module
  - **SYNOPSIS:** The prompt module must embed the architecture-generation and
    architecture-review directives directly in the prompt body instead of
    depending on phase-specific agent types or runtime skill discovery.
  - **BECAUSE:** The module should be self-contained and replayable.

- **RULE: RULE-4** Write one architecture file
  - **SYNOPSIS:** The phase must write exactly one file at
    `docs/architecture/architecture-design.yaml`.
  - **BECAUSE:** Later phases need one stable input file.

## 4. Workflow

- **PROCESS: PROCESS-1** Define the phase contract
  - **SYNOPSIS:** `PH-002` defines the input file, output path, architecture
    directives, review rules, and output shape.
  - **READS:** `.methodology/src/cli/methodology_runner/phases.py`
    - **BECAUSE:** The phase registry is the source of truth.

- **PROCESS: PROCESS-2** Execute the prompt with prompt-runner
  - **SYNOPSIS:** The methodology runner executes the predefined PH-002
    module with prompt-runner.
  - **USES:** `.methodology/src/cli/methodology_runner/orchestrator.py`
    - **BECAUSE:** The orchestrator owns the phase lifecycle.
  - **USES:** `.prompt-runner/src/cli/prompt_runner/runner.py`
    - **BECAUSE:** That module executes the generator/judge revision loop.
  - **PROMPT-MODULE: PMOD-1** PH-002 prompt module
    - **SYNOPSIS:** The PH-002 module is
      `.methodology/docs/prompts/PR-024-ph002-architecture.md`.
    - **READS:** `docs/features/feature-specification.yaml`
      - **BECAUSE:** That file is the main source for architecture decisions.
    - **USES:** generic prompt-runner `Generator Agent`
      - **BECAUSE:** Artifact production uses the stable generator role.
    - **USES:** embedded PH-002 architecture directives
      - **BECAUSE:** Phase-local structure and boundary guidance lives in the
        prompt body.
    - **USES:** generic prompt-runner `Judge Agent`
      - **BECAUSE:** Review uses the stable judge role.
    - **USES:** embedded PH-002 architecture review directives
      - **BECAUSE:** Phase-local review guidance lives in the prompt body.
  - **RESUMES:** the same artifact path across iterations
    - **BECAUSE:** `PH-002` revises one file rather than creating drafts.

- **PROCESS: PROCESS-3** Accept or reject the phase result
  - **SYNOPSIS:** The phase is accepted only when the prompt-runner loop
    passes and the resulting artifact is accepted as the phase output.
  - **VALIDATES:** `docs/architecture/architecture-design.yaml`
    - **BECAUSE:** The output file must exist before the phase can pass.
  - **BECAUSE:** `PH-002` passes only when both the deterministic validator
    and the judge pass.

## 5. Constraints

- **RULE: RULE-5** No unsupported decomposition
  - **SYNOPSIS:** The phase must not invent modules, frameworks, persistence,
    services, or boundaries that are not justified by the feature set.
  - **BECAUSE:** `PH-002` is an architecture phase, not an infrastructure wish list.

- **RULE: RULE-6** Prefer the smallest valid architecture
  - **SYNOPSIS:** If one module can coherently serve the full functionality,
    the phase should produce one-module architecture with no fake cross-module
    interactions.
  - **BECAUSE:** Later phases need real boundaries, not decorative ones.

- **RULE: RULE-7** Keep expertise human-readable
  - **SYNOPSIS:** Architecture rationale and expertise descriptions must be
    plain-language knowledge areas, not skill IDs, slugs, or tool names.
  - **BECAUSE:** The architecture must stay decoupled from the skill catalog.

## 6. Output Shape

- **ENTITY: ENTITY-1** Top-level output shape
  - **SYNOPSIS:** The top-level sections are:
    - `finality`
    - `system_shape`
    - `boundaries_and_interactions`
    - `constraints`
    - `definition_of_good`
    - `test_cases`
  - **BECAUSE:** That is the current PH-002 architecture document shape.

- **ENTITY: ENTITY-2** System shape content
  - **SYNOPSIS:** `system_shape` identifies the architecture modules, the
    features they serve, and the technology/runtime choices that materially
    affect those boundaries.
  - **BECAUSE:** Later phases refine those declared boundaries rather than
    inventing new ones.

## 7. Definition Of Good

- **RULE: RULE-8** Feature coverage
  - **SYNOPSIS:** Every `FT-*` feature must be covered by the declared
    architecture modules.
  - **BECAUSE:** Later phases can only refine what the architecture actually serves.

- **RULE: RULE-9** Real interaction boundaries
  - **SYNOPSIS:** Every real cross-module boundary must appear under
    `boundaries_and_interactions`, and fake ones must not be introduced.
  - **BECAUSE:** Later contract design depends on accurate interaction scope.

- **RULE: RULE-10** Coherent architecture choices
  - **SYNOPSIS:** Technology, runtime, and boundary choices must fit the
    supported features and constraints.
  - **BECAUSE:** Later phases depend on a coherent architecture baseline.

- **RULE: RULE-11** Deterministic and judge checks both pass
  - **SYNOPSIS:** The phase passes only if the deterministic validator passes
    and the judge returns `VERDICT: pass`.
  - **BECAUSE:** `PH-002` needs both shape checks and content checks.

## 8. Test Cases

- **TEST CASE: TC-1** Feature coverage
  - **SYNOPSIS:** Run the phase on a feature spec with known `FT-*` items and
    confirm every feature is represented in the architecture.
  - **BECAUSE:** The design depends on full feature coverage.

- **TEST CASE: TC-2** Embedded directive blocks
  - **SYNOPSIS:** Confirm the PH-002 module embeds the required architecture,
    traceability, and review directives directly in the prompt body.
  - **BECAUSE:** The module is supposed to be self-contained.

- **TEST CASE: TC-3** Output file path
  - **SYNOPSIS:** Run PH-002 and confirm the artifact written is
    `docs/architecture/architecture-design.yaml`.
  - **BECAUSE:** The phase should produce one stable output file.
