# Design: PH-004 Interface Contracts

## 1. Finality

This design explains how `PH-004` works from start to finish.

- **GOAL: GOAL-1** Produce the interface contracts
  - **SYNOPSIS:** `PH-004` turns the solution design into one
    acceptance-ready `docs/design/interface-contracts.yaml` file.
  - **BECAUSE:** Later phases depend on this file.

## 2. Inputs And Outputs

This section names the files that the phase uses.

- **FILE: FILE-1** Solution design
  - **SYNOPSIS:** Primary input:
    - `docs/design/solution-design.yaml`
  - **BECAUSE:** `PH-004` derives contracts from the `INT-*` interactions in
    the solution design.

- **FILE: FILE-2** Feature specification
  - **SYNOPSIS:** Traceability input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** The contracts must still support the feature acceptance
    criteria.

- **FILE: FILE-3** Interface contracts
  - **SYNOPSIS:** Primary output:
    - `docs/design/interface-contracts.yaml`
  - **BECAUSE:** This is the phase output.

- **FILE: FILE-4** Prompt-runner module
  - **SYNOPSIS:** `.methodology/docs/prompts/PR-027-ph004-interface-contracts.md`
    with:
    - embedded directive blocks for traceability and contract review discipline
    - fixed generic prompt-runner generator and judge roles
    - fixed phase input and output paths
  - **BECAUSE:** `PH-004` uses one predefined prompt-runner module.

## 3. Technical Directives

This section states the technical directives that shape the phase
implementation.

- **RULE: RULE-1** Read the solution design and feature spec
  - **SYNOPSIS:** The phase must read `docs/design/solution-design.yaml` and
    `docs/features/feature-specification.yaml`.
  - **BECAUSE:** The solution design is the main source, and the feature spec
    is used to keep contracts aligned with feature intent.

- **RULE: RULE-2** Use the predefined prompt module
  - **SYNOPSIS:** The phase must use
    `.methodology/docs/prompts/PR-027-ph004-interface-contracts.md`.
  - **BECAUSE:** `PH-004` should not build a new prompt module for each run.

- **RULE: RULE-3** Keep the phase directives inside the module
  - **SYNOPSIS:** The prompt module must contain the PH-004 contract
    directives and embedded traceability/review guidance that the generic
    prompt-runner roles consume.
  - **BECAUSE:** The module should be self-contained.

- **RULE: RULE-4** Write one interface contracts file
  - **SYNOPSIS:** The phase must write exactly one file at
    `docs/design/interface-contracts.yaml`.
  - **BECAUSE:** Later phases need one stable input file.

## 4. Workflow

This section describes the phase steps.

- **PROCESS: PROCESS-1** Define the phase contract
  - **SYNOPSIS:** `PH-004` defines the input files, output path, contract
    rules, judge rules, and output shape.
  - **READS:** `.methodology/src/cli/methodology_runner/phases.py`
    - **BECAUSE:** The phase registry is the source of truth.
  - **BECAUSE:** The run needs this contract before it starts.

- **PROCESS: PROCESS-2** Execute the prompts with prompt-runner
  - **SYNOPSIS:** The methodology runner runs the predefined PH-004 module
    with prompt-runner.
  - **USES:** `.methodology/src/cli/methodology_runner/orchestrator.py`
    - **BECAUSE:** The orchestrator owns the phase lifecycle and
      prompt-runner invocation.
  - **USES:** `.prompt-runner/src/cli/prompt_runner/runner.py`
    - **BECAUSE:** That module executes the generator/judge revision loop.
  - **PROMPT-MODULE: PMOD-1** PH-004 prompt-runner input file
    - **SYNOPSIS:** The PH-004 prompt-runner input file is
      `.methodology/docs/prompts/PR-027-ph004-interface-contracts.md`.
    - **BECAUSE:** The phase uses one fixed module shape.
    - **READS:** `docs/design/solution-design.yaml`
      - **BECAUSE:** That file is the main source for contract definitions.
    - **READS:** `docs/features/feature-specification.yaml`
      - **BECAUSE:** That file keeps contract detail aligned with feature
        intent.
    - **AGENT:** `Generator Agent`
      - **SYNOPSIS:** Embedded generator definition in the PH-004 module.
      - **BECAUSE:** The generator setup is fixed for this phase.
      - **RULE:** Embedded PH-004 generation directives
        - **SYNOPSIS:** Keep contract detail grounded in the solution design
          and feature spec through prompt-embedded traceability guidance.
        - **BECAUSE:** `PH-004` must stay traceable without runtime skill discovery.
      - **RULE:** Prompt-local contract directives
        - **SYNOPSIS:** The module itself defines contract coverage, schema
          shape, error-model rules, and behavioral-spec rules.
        - **BECAUSE:** PH-004-specific generation behavior now lives in the
          prompt, not in a phase-only skill.
    - **AGENT:** `Judge Agent`
      - **SYNOPSIS:** Embedded judge definition in the PH-004 module.
      - **BECAUSE:** The judge setup is fixed for this phase.
      - **RULE:** Embedded PH-004 review directives
        - **BECAUSE:** The judge uses prompt-embedded traceability and review
          guidance instead of separate runtime skill loading.
      - **RULE:** Prompt-local contract review directives
        - **SYNOPSIS:** The module itself defines the PH-004 review checks for
          missing coverage, type holes, error gaps, inconsistency, and weak behavioral specs.
        - **BECAUSE:** PH-004-specific review behavior now lives in the
          prompt, not in a phase-only skill.
    - **PROMPT-PAIR: Prompt 1**
      - **PROMPT:** `Generator`
        - **SYNOPSIS:** Reads the solution design and feature spec and writes
          `docs/design/interface-contracts.yaml`.
        - **BECAUSE:** The generator owns artifact production.
        - **USES:** `Generator Agent`
          - **BECAUSE:** The prompt pair should use the embedded generator
            definition already declared in the prompt module.
        - **USES:** embedded PH-004 contract directives
          - **BECAUSE:** The generator's specialized guidance is embedded in
            the prompt body.
        - **USES:** prompt-local PH-004 contract directives
          - **BECAUSE:** The generator's phase-specific behavior is embedded
            in the module.
      - **PROMPT:** `Judge`
        - **SYNOPSIS:** Reviews contract coverage, schema quality, error
          models, and behavioral specs.
        - **BECAUSE:** The judge decides whether the file passes or needs
          another revision.
        - **USES:** `Judge Agent`
          - **BECAUSE:** The prompt pair should use the embedded judge
            definition already declared in the prompt module.
        - **USES:** embedded PH-004 review directives
          - **BECAUSE:** The judge's specialized guidance is embedded in the
            prompt body.
        - **USES:** prompt-local PH-004 review directives
          - **BECAUSE:** The judge's phase-specific behavior is embedded in
            the module.
  - **READS:** embedded prompt-body directive blocks
    - **BECAUSE:** `PH-004` keeps its fixed specialized guidance in the module.
  - **LAUNCHES:** generator session
    - **BECAUSE:** The artifact must be produced before it can be judged.
  - **LAUNCHES:** judge session
    - **BECAUSE:** The artifact must be reviewed for phase readiness and
      either passed, revised, or escalated.
  - **RESUMES:** the same artifact path across iterations
    - **BECAUSE:** `PH-004` revises the same output file. It does not create
      draft variants.

- **PROCESS: PROCESS-3** Accept or reject the phase result
  - **SYNOPSIS:** The phase is accepted only when the prompt-runner loop passes
    and the resulting artifact is accepted as the phase output.
  - **VALIDATES:** `docs/design/interface-contracts.yaml`
    - **BECAUSE:** The output file must exist before the phase can pass.
  - **USES:** `.methodology/src/cli/methodology_runner/phase_4_validation.py`
    - **BECAUSE:** `PH-004` uses deterministic checks for schema, interaction
      coverage, and top-level shape.
  - **BECAUSE:** `PH-004` passes only when both the deterministic checks and
    the judge review pass.
  - **PRODUCES:** `docs/design/interface-contracts.yaml`
    - **BECAUSE:** That artifact is the durable output consumed by `PH-005`
      and `PH-006`.

## 5. Constraints

This section states the main limits on the phase.

- **RULE: RULE-5** No type holes
  - **SYNOPSIS:** Schemas must not use vague placeholders such as `object`,
    `any`, or `unknown`.
  - **BECAUSE:** Later simulations and implementation depend on explicit
    contract detail.

- **RULE: RULE-6** No unsupported operations
  - **SYNOPSIS:** The phase must not invent operations, error behaviors, or
    contract detail that no longer serves the interaction being modeled.
  - **BECAUSE:** Contracts must stay tied to real interaction needs.

- **RULE: RULE-7** One fixed prompt module
  - **SYNOPSIS:** `PH-004` must use the predefined prompt module instead of
    building a new module per run.
  - **BECAUSE:** The module shape should stay stable.

## 6. Output Shape

This section states what the output file contains.

- **ENTITY: ENTITY-1** Top-level output shape
  - **SYNOPSIS:** The top-level section is:
    - `contracts`
  - **BECAUSE:** That is the schema required by the PH-004 phase contract.

- **ENTITY: ENTITY-2** Contract fields
  - **SYNOPSIS:** Each contract contains:
    - `id`
    - `name`
    - `interaction_ref`
    - `source_component`
    - `target_component`
    - `operations`
    - `behavioral_specs`
  - **BECAUSE:** Those are the fields downstream phases rely on.

## 7. Definition Of Good

This section states when the phase passes.

- **RULE: RULE-8** Interaction coverage
  - **SYNOPSIS:** Every `INT-*` interaction must have at least one matching
    `CTR-*` contract.
  - **BECAUSE:** Later phases can only simulate and implement what the
    contracts actually cover.

- **RULE: RULE-9** Typed and behavioral completeness
  - **SYNOPSIS:** Operations must define explicit schemas, error types, and at
    least one behavioral spec with a precondition, postcondition, and
    invariant.
  - **BECAUSE:** Later simulations and implementation depend on explicit
    contract behavior.

- **RULE: RULE-10** Contract fidelity
  - **SYNOPSIS:** Contract detail must stay aligned with the upstream
    interaction and feature intent.
  - **BECAUSE:** Contracts are an elaboration layer, not a new product scope.

- **RULE: RULE-11** Deterministic and judge checks both pass
  - **SYNOPSIS:** The phase passes only if the deterministic validator passes
    and the judge returns `VERDICT: pass`.
  - **BECAUSE:** `PH-004` needs both shape checks and content checks.

## 8. Test Cases

This section lists the tests the phase design expects.

- **TEST CASE: TC-1** Interaction coverage
  - **SYNOPSIS:** Run the phase on a solution design with known `INT-*`
    interactions and confirm every interaction has at least one `CTR-*`
    contract.
  - **BECAUSE:** The design depends on full interaction coverage.

- **TEST CASE: TC-2** Embedded directive blocks
  - **SYNOPSIS:** Confirm the PH-004 module embeds the required traceability
    and review directives directly in the prompt body.
  - **BECAUSE:** The module is supposed to be self-contained.

- **TEST CASE: TC-3** Output file path
  - **SYNOPSIS:** Run PH-004 and confirm the artifact written is
    `docs/design/interface-contracts.yaml`.
  - **BECAUSE:** The phase should produce one stable output file.

- **TEST CASE: TC-4** Type-hole rejection
  - **SYNOPSIS:** Run the phase with contracts that use vague schema types and
    confirm the deterministic and judge loop rejects them.
  - **BECAUSE:** Weak contract schemas should not pass this phase.
