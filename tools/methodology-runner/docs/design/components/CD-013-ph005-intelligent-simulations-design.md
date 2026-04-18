# Design: PH-005 Intelligent Simulations

## 1. Finality

This design explains how `PH-005` works from start to finish.

- **GOAL: GOAL-1** Produce the simulation definitions
  - **SYNOPSIS:** `PH-005` turns the interface contracts into one
    acceptance-ready `docs/simulations/simulation-definitions.yaml` file.
  - **BECAUSE:** Later phases depend on this file.

## 2. Inputs And Outputs

This section names the files that the phase uses.

- **FILE: FILE-1** Interface contracts
  - **SYNOPSIS:** Primary input:
    - `docs/design/interface-contracts.yaml`
  - **BECAUSE:** `PH-005` produces simulations directly from the contract
    definitions.

- **FILE: FILE-2** Feature specification
  - **SYNOPSIS:** Traceability input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** The simulations must still support feature intent.

- **FILE: FILE-3** Simulation definitions
  - **SYNOPSIS:** Primary output:
    - `docs/simulations/simulation-definitions.yaml`
  - **BECAUSE:** This is the phase output.

- **FILE: FILE-4** Prompt-runner module
  - **SYNOPSIS:** `.methodology/docs/prompts/PR-028-ph005-intelligent-simulations.md`
    with:
    - embedded directive blocks for traceability and simulation review discipline
    - fixed generic prompt-runner generator and judge roles
    - fixed phase input and output paths
  - **BECAUSE:** `PH-005` uses one predefined prompt-runner module.

## 3. Technical Directives

This section states the technical directives that shape the phase
implementation.

- **RULE: RULE-1** Read the contracts and feature spec
  - **SYNOPSIS:** The phase must read `docs/design/interface-contracts.yaml`
    and `docs/features/feature-specification.yaml`.
  - **BECAUSE:** The contracts are the main source, and the feature spec keeps
    simulations tied to user-facing intent.

- **RULE: RULE-2** Use the predefined prompt module
  - **SYNOPSIS:** The phase must use
    `.methodology/docs/prompts/PR-028-ph005-intelligent-simulations.md`.
  - **BECAUSE:** `PH-005` should not build a new prompt module for each run.

- **RULE: RULE-3** Keep the phase directives inside the module
  - **SYNOPSIS:** The prompt module must contain the PH-005 simulation
    directives and embedded traceability/review guidance that the generic
    prompt-runner roles consume.
  - **BECAUSE:** The module should be self-contained.

- **RULE: RULE-4** Write one simulation definitions file
  - **SYNOPSIS:** The phase must write exactly one file at
    `docs/simulations/simulation-definitions.yaml`.
  - **BECAUSE:** Later phases need one stable input file.

## 4. Workflow

This section describes the phase steps.

- **PROCESS: PROCESS-1** Define the phase contract
  - **SYNOPSIS:** `PH-005` defines the input files, output path, simulation
    rules, judge rules, and output shape.
  - **READS:** `.methodology/src/cli/methodology_runner/phases.py`
    - **BECAUSE:** The phase registry is the source of truth.
  - **BECAUSE:** The run needs this contract before it starts.

- **PROCESS: PROCESS-2** Execute the prompts with prompt-runner
  - **SYNOPSIS:** The methodology runner runs the predefined PH-005 module
    with prompt-runner.
  - **USES:** `.methodology/src/cli/methodology_runner/orchestrator.py`
    - **BECAUSE:** The orchestrator owns the phase lifecycle and
      prompt-runner invocation.
  - **USES:** `.prompt-runner/src/cli/prompt_runner/runner.py`
    - **BECAUSE:** That module executes the generator/judge revision loop.
  - **PROMPT-MODULE: PMOD-1** PH-005 prompt-runner input file
    - **SYNOPSIS:** The PH-005 prompt-runner input file is
      `.methodology/docs/prompts/PR-028-ph005-intelligent-simulations.md`.
    - **BECAUSE:** The phase uses one fixed module shape.
    - **READS:** `docs/design/interface-contracts.yaml`
      - **BECAUSE:** That file is the main source for simulation design.
    - **READS:** `docs/features/feature-specification.yaml`
      - **BECAUSE:** That file keeps simulations tied to feature intent.
    - **AGENT:** `Generator Agent`
      - **SYNOPSIS:** Embedded generator definition in the PH-005 module.
      - **BECAUSE:** The generator setup is fixed for this phase.
      - **RULE:** Embedded PH-005 generation directives
        - **SYNOPSIS:** Keep simulations grounded in contract behavior and
          upstream feature intent through prompt-embedded traceability guidance.
        - **BECAUSE:** `PH-005` must stay traceable without runtime skill discovery.
      - **RULE:** Prompt-local simulation directives
        - **SYNOPSIS:** The module itself defines scenario coverage, contract-faithful
          assertions, and synthetic-setup limits.
        - **BECAUSE:** PH-005-specific generation behavior now lives in the
          prompt, not in a phase-only skill.
    - **AGENT:** `Judge Agent`
      - **SYNOPSIS:** Embedded judge definition in the PH-005 module.
      - **BECAUSE:** The judge setup is fixed for this phase.
      - **RULE:** Embedded PH-005 review directives
        - **BECAUSE:** The judge uses prompt-embedded traceability and review
          guidance instead of separate runtime skill loading.
      - **RULE:** Prompt-local simulation review directives
        - **SYNOPSIS:** The module itself defines the PH-005 review checks for
          weak assertions, realism defects, missing error coverage, and leakage.
        - **BECAUSE:** PH-005-specific review behavior now lives in the
          prompt, not in a phase-only skill.
    - **PROMPT-PAIR: Prompt 1**
      - **PROMPT:** `Generator`
        - **SYNOPSIS:** Reads the interface contracts and feature spec and
          writes `docs/simulations/simulation-definitions.yaml`.
        - **BECAUSE:** The generator owns artifact production.
        - **USES:** `Generator Agent`
          - **BECAUSE:** The prompt pair should use the embedded generator
            definition already declared in the prompt module.
        - **USES:** embedded PH-005 simulation directives
          - **BECAUSE:** The generator's specialized guidance is embedded in
            the prompt body.
        - **USES:** prompt-local PH-005 simulation directives
          - **BECAUSE:** The generator's phase-specific behavior is embedded
            in the module.
      - **PROMPT:** `Judge`
        - **SYNOPSIS:** Reviews contract coverage, scenario quality, error-path
          coverage, and implementation leakage.
        - **BECAUSE:** The judge decides whether the file passes or needs
          another revision.
        - **USES:** `Judge Agent`
          - **BECAUSE:** The prompt pair should use the embedded judge
            definition already declared in the prompt module.
        - **USES:** embedded PH-005 review directives
          - **BECAUSE:** The judge's specialized guidance is embedded in the
            prompt body.
        - **USES:** prompt-local PH-005 review directives
          - **BECAUSE:** The judge's phase-specific behavior is embedded in
            the module.
  - **READS:** embedded prompt-body directive blocks
    - **BECAUSE:** `PH-005` keeps its fixed specialized guidance in the module.
  - **LAUNCHES:** generator session
    - **BECAUSE:** The artifact must be produced before it can be judged.
  - **LAUNCHES:** judge session
    - **BECAUSE:** The artifact must be reviewed for phase readiness and
      either passed, revised, or escalated.
  - **RESUMES:** the same artifact path across iterations
    - **BECAUSE:** `PH-005` revises the same output file. It does not create
      draft variants.

- **PROCESS: PROCESS-3** Accept or reject the phase result
  - **SYNOPSIS:** The phase is accepted only when the prompt-runner loop passes
    and the resulting artifact is accepted as the phase output.
  - **VALIDATES:** `docs/simulations/simulation-definitions.yaml`
    - **BECAUSE:** The output file must exist before the phase can pass.
  - **USES:** `.methodology/src/cli/methodology_runner/phase_5_validation.py`
    - **BECAUSE:** `PH-005` uses deterministic checks for schema, contract
      coverage, scenario type coverage, and top-level shape.
  - **BECAUSE:** `PH-005` passes only when both the deterministic checks and
    the judge review pass.
  - **PRODUCES:** `docs/simulations/simulation-definitions.yaml`
    - **BECAUSE:** That artifact is the durable output consumed by `PH-006`.

## 5. Constraints

This section states the main limits on the phase.

- **RULE: RULE-5** No implementation leakage
  - **SYNOPSIS:** Expected outputs and validation rules must be derivable from
    contract behavior, not hidden implementation details.
  - **BECAUSE:** Simulations are a contract layer, not an implementation
    layer.

- **RULE: RULE-6** No thin scenarios
  - **SYNOPSIS:** Assertions must check meaningful response content, not only
    trivial status flags or presence checks.
  - **BECAUSE:** Later verification depends on simulations that exercise real
    semantics.

- **RULE: RULE-7** One fixed prompt module
  - **SYNOPSIS:** `PH-005` must use the predefined prompt module instead of
    building a new module per run.
  - **BECAUSE:** The module shape should stay stable.

## 6. Output Shape

This section states what the output file contains.

- **ENTITY: ENTITY-1** Top-level output shape
  - **SYNOPSIS:** The top-level section is:
    - `simulations`
  - **BECAUSE:** That is the schema required by the PH-005 phase contract.

- **ENTITY: ENTITY-2** Simulation fields
  - **SYNOPSIS:** Each simulation contains:
    - `id`
    - `contract_ref`
    - `description`
    - `scenario_bank`
    - `llm_adjuster`
    - `validation_rules`
  - **BECAUSE:** Those are the fields downstream phases rely on.

## 7. Definition Of Good

This section states when the phase passes.

- **RULE: RULE-8** Contract coverage
  - **SYNOPSIS:** Every `CTR-*` contract must have at least one matching
    `SIM-*` simulation.
  - **BECAUSE:** Later phases can only plan and build against covered
    contracts.

- **RULE: RULE-9** Scenario breadth
  - **SYNOPSIS:** Every simulation must include at least one happy path, one
    error path, and one edge case scenario.
  - **BECAUSE:** Later phases depend on broad scenario coverage.

- **RULE: RULE-10** Meaningful assertions
  - **SYNOPSIS:** Assertions must verify contract semantics, not just generic
    success flags.
  - **BECAUSE:** Later planning and verification depend on strong simulation
    signals.

- **RULE: RULE-11** Deterministic and judge checks both pass
  - **SYNOPSIS:** The phase passes only if the deterministic validator passes
    and the judge returns `VERDICT: pass`.
  - **BECAUSE:** `PH-005` needs both shape checks and content checks.

## 8. Test Cases

This section lists the tests the phase design expects.

- **TEST CASE: TC-1** Contract coverage
  - **SYNOPSIS:** Run the phase on a contract set with known `CTR-*` items and
    confirm every contract has at least one `SIM-*` simulation.
  - **BECAUSE:** The design depends on full contract coverage.

- **TEST CASE: TC-2** Embedded directive blocks
  - **SYNOPSIS:** Confirm the PH-005 module embeds the required simulation,
    traceability, and review directives directly in the prompt body.
  - **BECAUSE:** The module is supposed to be self-contained.

- **TEST CASE: TC-3** Output file path
  - **SYNOPSIS:** Run PH-005 and confirm the artifact written is
    `docs/simulations/simulation-definitions.yaml`.
  - **BECAUSE:** The phase should produce one stable output file.

- **TEST CASE: TC-4** Weak assertion rejection
  - **SYNOPSIS:** Run the phase with simulations that assert only trivial
    success flags and confirm the deterministic and judge loop rejects them.
  - **BECAUSE:** Thin simulations should not pass this phase.
