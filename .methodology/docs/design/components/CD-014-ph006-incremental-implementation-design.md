# Design: PH-006 Incremental Implementation

## 1. Finality

This design explains how `PH-006` works from start to finish.

- **GOAL: GOAL-1** Produce the implementation plan
  - **SYNOPSIS:** `PH-006` turns the design and simulation artifacts into one
    acceptance-ready `docs/implementation/implementation-plan.yaml` file.
  - **BECAUSE:** Later phases depend on this file.

## 2. Inputs And Outputs

This section names the files that the phase uses.

- **FILE: FILE-1** Interface contracts
  - **SYNOPSIS:** Primary input:
    - `docs/design/interface-contracts.yaml`
  - **BECAUSE:** `PH-006` plans what to build from the contract layer.

- **FILE: FILE-2** Simulation definitions
  - **SYNOPSIS:** Planning input:
    - `docs/simulations/simulation-definitions.yaml`
  - **BECAUSE:** The plan must account for simulations before replacement.

- **FILE: FILE-3** Feature specification
  - **SYNOPSIS:** Traceability input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** The plan must keep tests tied to feature acceptance criteria.

- **FILE: FILE-4** Solution design
  - **SYNOPSIS:** Dependency input:
    - `docs/design/solution-design.yaml`
  - **BECAUSE:** The build order must respect component dependencies.

- **FILE: FILE-5** Implementation plan
  - **SYNOPSIS:** Primary output:
    - `docs/implementation/implementation-plan.yaml`
  - **BECAUSE:** This is the phase output.

- **FILE: FILE-6** Prompt-runner module
  - **SYNOPSIS:** `.methodology/docs/prompts/PR-029-ph006-incremental-implementation.md`
    with:
    - embedded directive blocks for traceability and implementation-plan review discipline
    - fixed generic prompt-runner generator and judge roles
    - fixed phase input and output paths
  - **BECAUSE:** `PH-006` uses one predefined prompt-runner module.

## 3. Technical Directives

This section states the technical directives that shape the phase
implementation.

- **RULE: RULE-1** Read the planning inputs
  - **SYNOPSIS:** The phase must read
    `docs/design/interface-contracts.yaml`,
    `docs/simulations/simulation-definitions.yaml`,
    `docs/features/feature-specification.yaml`, and
    `docs/design/solution-design.yaml`.
  - **BECAUSE:** The contracts are the main source, and the other files keep
    the plan tied to simulations, features, and dependencies.

- **RULE: RULE-2** Use the predefined prompt module
  - **SYNOPSIS:** The phase must use
    `.methodology/docs/prompts/PR-029-ph006-incremental-implementation.md`.
  - **BECAUSE:** `PH-006` should not build a new prompt module for each run.

- **RULE: RULE-3** Keep the phase directives inside the module
  - **SYNOPSIS:** The prompt module must contain the PH-006 planning
    directives and embedded traceability/review guidance that the generic
    prompt-runner roles consume.
  - **BECAUSE:** The module should be self-contained.

- **RULE: RULE-4** Write one implementation plan file
  - **SYNOPSIS:** The phase must write exactly one file at
    `docs/implementation/implementation-plan.yaml`.
  - **BECAUSE:** Later verification depends on one stable plan file.

## 4. Workflow

This section describes the phase steps.

- **PROCESS: PROCESS-1** Define the phase contract
  - **SYNOPSIS:** `PH-006` defines the input files, output path, planning
    rules, judge rules, and output shape.
  - **READS:** `.methodology/src/cli/methodology_runner/phases.py`
    - **BECAUSE:** The phase registry is the source of truth.
  - **BECAUSE:** The run needs this contract before it starts.

- **PROCESS: PROCESS-2** Execute the prompts with prompt-runner
  - **SYNOPSIS:** The methodology runner runs the predefined PH-006 module
    with prompt-runner.
  - **USES:** `.methodology/src/cli/methodology_runner/orchestrator.py`
    - **BECAUSE:** The orchestrator owns the phase lifecycle and
      prompt-runner invocation.
  - **USES:** `.prompt-runner/src/cli/prompt_runner/runner.py`
    - **BECAUSE:** That module executes the generator/judge revision loop.
  - **PROMPT-MODULE: PMOD-1** PH-006 prompt-runner input file
    - **SYNOPSIS:** The PH-006 prompt-runner input file is
      `.methodology/docs/prompts/PR-029-ph006-incremental-implementation.md`.
    - **BECAUSE:** The phase uses one fixed module shape.
    - **READS:** `docs/design/interface-contracts.yaml`
      - **BECAUSE:** That file is the main source for planning build steps.
    - **READS:** `docs/simulations/simulation-definitions.yaml`
      - **BECAUSE:** That file defines the available simulations and
        replacement needs.
    - **READS:** `docs/features/feature-specification.yaml`
      - **BECAUSE:** That file keeps tests tied to feature completion.
    - **READS:** `docs/design/solution-design.yaml`
      - **BECAUSE:** That file supplies component dependencies.
    - **AGENT:** `Generator Agent`
      - **SYNOPSIS:** Embedded generator definition in the PH-006 module.
      - **BECAUSE:** The generator setup is fixed for this phase.
      - **RULE:** Embedded PH-006 generation directives
        - **SYNOPSIS:** Keep build steps, tests, and simulation replacement
          tied to the upstream artifacts through prompt-embedded traceability guidance.
        - **BECAUSE:** `PH-006` must stay traceable without runtime skill discovery.
      - **RULE:** Prompt-local implementation-plan directives
        - **SYNOPSIS:** The module itself defines build order, test-planning,
          and simulation-retirement rules.
        - **BECAUSE:** PH-006-specific generation behavior now lives in the
          prompt, not in a phase-only skill.
    - **AGENT:** `Judge Agent`
      - **SYNOPSIS:** Embedded judge definition in the PH-006 module.
      - **BECAUSE:** The judge setup is fixed for this phase.
      - **RULE:** Embedded PH-006 review directives
        - **BECAUSE:** The judge uses prompt-embedded traceability and review
          guidance instead of separate runtime skill loading.
      - **RULE:** Prompt-local implementation-plan review directives
        - **SYNOPSIS:** The module itself defines the PH-006 review checks for
          ordering, thin tests, completion gaps, and replacement defects.
        - **BECAUSE:** PH-006-specific review behavior now lives in the
          prompt, not in a phase-only skill.
    - **PROMPT-PAIR: Prompt 1**
      - **PROMPT:** `Generator`
        - **SYNOPSIS:** Reads the contract, simulation, feature, and solution
          design artifacts and writes
          `docs/implementation/implementation-plan.yaml`.
        - **BECAUSE:** The generator owns artifact production.
        - **USES:** `Generator Agent`
          - **BECAUSE:** The prompt pair should use the embedded generator
            definition already declared in the prompt module.
        - **USES:** embedded PH-006 planning directives
          - **BECAUSE:** The generator's specialized guidance is embedded in
            the prompt body.
        - **USES:** prompt-local PH-006 planning directives
          - **BECAUSE:** The generator's phase-specific behavior is embedded
            in the module.
      - **PROMPT:** `Judge`
        - **SYNOPSIS:** Reviews ordering, test coverage, completion planning,
          and simulation replacement logic.
        - **BECAUSE:** The judge decides whether the file passes or needs
          another revision.
        - **USES:** `Judge Agent`
          - **BECAUSE:** The prompt pair should use the embedded judge
            definition already declared in the prompt module.
        - **USES:** embedded PH-006 review directives
          - **BECAUSE:** The judge's specialized guidance is embedded in the
            prompt body.
        - **USES:** prompt-local PH-006 review directives
          - **BECAUSE:** The judge's phase-specific behavior is embedded in
            the module.
  - **READS:** embedded prompt-body directive blocks
    - **BECAUSE:** `PH-006` keeps its fixed specialized guidance in the module.
  - **LAUNCHES:** generator session
    - **BECAUSE:** The artifact must be produced before it can be judged.
  - **LAUNCHES:** judge session
    - **BECAUSE:** The artifact must be reviewed for phase readiness and
      either passed, revised, or escalated.
  - **RESUMES:** the same artifact path across iterations
    - **BECAUSE:** `PH-006` revises the same output file. It does not create
      draft variants.

- **PROCESS: PROCESS-3** Accept or reject the phase result
  - **SYNOPSIS:** The phase is accepted only when the prompt-runner loop passes
    and the resulting artifact is accepted as the phase output.
  - **VALIDATES:** `docs/implementation/implementation-plan.yaml`
    - **BECAUSE:** The output file must exist before the phase can pass.
  - **USES:** `.methodology/src/cli/methodology_runner/phase_6_validation.py`
    - **BECAUSE:** `PH-006` uses deterministic checks for schema, dependency
      order, coverage counts, and top-level shape.
  - **BECAUSE:** `PH-006` passes only when both the deterministic checks and
    the judge review pass.
  - **PRODUCES:** `docs/implementation/implementation-plan.yaml`
    - **BECAUSE:** That artifact is the durable output consumed by `PH-007`.

## 5. Constraints

This section states the main limits on the phase.

- **RULE: RULE-5** No broken build order
  - **SYNOPSIS:** The build order must not place components after work that
    already depends on them, unless a simulation explicitly bridges that gap.
  - **BECAUSE:** Later execution depends on a realistic build sequence.

- **RULE: RULE-6** No thin test planning
  - **SYNOPSIS:** Unit and integration test plans must do more than name
    artifacts. They must show what each test verifies.
  - **BECAUSE:** Later verification depends on meaningful planned tests.

- **RULE: RULE-7** One fixed prompt module
  - **SYNOPSIS:** `PH-006` must use the predefined prompt module instead of
    building a new module per run.
  - **BECAUSE:** The module shape should stay stable.

## 6. Output Shape

This section states what the output file contains.

- **ENTITY: ENTITY-1** Top-level output shape
  - **SYNOPSIS:** The top-level sections are:
    - `build_order`
    - `unit_test_plan`
    - `integration_test_plan`
    - `simulation_replacement_sequence`
  - **BECAUSE:** That is the schema required by the PH-006 phase contract.

- **ENTITY: ENTITY-2** Build step fields
  - **SYNOPSIS:** Each build step contains:
    - `step`
    - `component_ref`
    - `rationale`
    - `contracts_implemented`
    - `simulations_used`
  - **BECAUSE:** Those are the fields downstream phases rely on.

## 7. Definition Of Good

This section states when the phase passes.

- **RULE: RULE-8** Dependency-respecting order
  - **SYNOPSIS:** The build order must respect component dependencies unless a
    referenced dependency is explicitly simulated in a prior step.
  - **BECAUSE:** Later implementation depends on a coherent build sequence.

- **RULE: RULE-9** Test traceability
  - **SYNOPSIS:** Every `AC-*` must appear in at least one unit or integration
    test entry, and every `CTR-*` contract must appear in at least one build
    step.
  - **BECAUSE:** Later verification depends on traceable planned tests.

- **RULE: RULE-10** Simulation replacement coverage
  - **SYNOPSIS:** Every `SIM-*` simulation must appear in the replacement
    sequence with the affected integration tests to rerun.
  - **BECAUSE:** Later execution depends on clear simulation retirement steps.

- **RULE: RULE-11** Deterministic and judge checks both pass
  - **SYNOPSIS:** The phase passes only if the deterministic validator passes
    and the judge returns `VERDICT: pass`.
  - **BECAUSE:** `PH-006` needs both shape checks and content checks.

## 8. Test Cases

This section lists the tests the phase design expects.

- **TEST CASE: TC-1** Dependency-respecting order
  - **SYNOPSIS:** Run the phase on a solution design with known dependencies
    and confirm the build order respects them or names an explicit simulation
    bridge.
  - **BECAUSE:** The design depends on a realistic build sequence.

- **TEST CASE: TC-2** Embedded directive blocks
  - **SYNOPSIS:** Confirm the PH-006 module embeds the required planning,
    traceability, and review directives directly in the prompt body.
  - **BECAUSE:** The module is supposed to be self-contained.

- **TEST CASE: TC-3** Output file path
  - **SYNOPSIS:** Run PH-006 and confirm the artifact written is
    `docs/implementation/implementation-plan.yaml`.
  - **BECAUSE:** The phase should produce one stable output file.

- **TEST CASE: TC-4** Missing rerun rejection
  - **SYNOPSIS:** Run the phase with a simulation replacement step that names
    no integration tests to rerun and confirm the deterministic and judge loop
    rejects it.
  - **BECAUSE:** Thin simulation retirement plans should not pass this phase.
