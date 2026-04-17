# Design: PH-007 Verification Sweep

## 1. Finality

This design explains how `PH-007` works from start to finish.

- **GOAL: GOAL-1** Produce the verification report
  - **SYNOPSIS:** `PH-007` turns the upstream methodology artifacts into one
    acceptance-ready `docs/verification/verification-report.yaml` file.
  - **BECAUSE:** This file is the final verification artifact for the chain.

## 2. Inputs And Outputs

This section names the files that the phase uses.

- **FILE: FILE-1** Feature specification
  - **SYNOPSIS:** Primary input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** End-to-end verification is derived from features and
    acceptance criteria.

- **FILE: FILE-2** Implementation plan
  - **SYNOPSIS:** Planning input:
    - `docs/implementation/implementation-plan.yaml`
  - **BECAUSE:** The verification sweep must reflect the planned build and
    test work.

- **FILE: FILE-3** Solution design
  - **SYNOPSIS:** Design input:
    - `docs/design/solution-design.yaml`
  - **BECAUSE:** The verification sweep must trace through the design layer.

- **FILE: FILE-4** Requirements inventory
  - **SYNOPSIS:** Traceability input:
    - `docs/requirements/requirements-inventory.yaml`
  - **BECAUSE:** The final report must trace back to the original `RI-*`
    items.

- **FILE: FILE-5** Verification report
  - **SYNOPSIS:** Primary output:
    - `docs/verification/verification-report.yaml`
  - **BECAUSE:** This is the phase output.

- **FILE: FILE-6** Prompt-runner module
  - **SYNOPSIS:** `.methodology/docs/prompts/PR-030-ph007-verification-sweep.md`
    with:
    - embedded directive blocks for traceability and verification-review discipline
    - fixed generic prompt-runner generator and judge roles
    - fixed phase input and output paths
  - **BECAUSE:** `PH-007` uses one predefined prompt-runner module.

## 3. Technical Directives

This section states the technical directives that shape the phase
implementation.

- **RULE: RULE-1** Read the verification inputs
  - **SYNOPSIS:** The phase must read
    `docs/features/feature-specification.yaml`,
    `docs/implementation/implementation-plan.yaml`,
    `docs/design/solution-design.yaml`, and
    `docs/requirements/requirements-inventory.yaml`.
  - **BECAUSE:** The feature spec is the main source, and the other files keep
    the final report tied to planning, design, and original requirements.

- **RULE: RULE-2** Use the predefined prompt module
  - **SYNOPSIS:** The phase must use
    `.methodology/docs/prompts/PR-030-ph007-verification-sweep.md`.
  - **BECAUSE:** `PH-007` should not build a new prompt module for each run.

- **RULE: RULE-3** Keep the phase directives inside the module
  - **SYNOPSIS:** The prompt module must contain the PH-007 verification
    directives and embedded traceability/review guidance that the generic
    prompt-runner roles consume.
  - **BECAUSE:** The module should be self-contained.

- **RULE: RULE-4** Write one verification report file
  - **SYNOPSIS:** The phase must write exactly one file at
    `docs/verification/verification-report.yaml`.
  - **BECAUSE:** The methodology ends with one stable verification report.

## 4. Workflow

This section describes the phase steps.

- **PROCESS: PROCESS-1** Define the phase contract
  - **SYNOPSIS:** `PH-007` defines the input files, output path, verification
    rules, judge rules, and output shape.
  - **READS:** `.methodology/src/cli/methodology_runner/phases.py`
    - **BECAUSE:** The phase registry is the source of truth.
  - **BECAUSE:** The run needs this contract before it starts.

- **PROCESS: PROCESS-2** Execute the prompts with prompt-runner
  - **SYNOPSIS:** The methodology runner runs the predefined PH-007 module
    with prompt-runner.
  - **USES:** `.methodology/src/cli/methodology_runner/orchestrator.py`
    - **BECAUSE:** The orchestrator owns the phase lifecycle and
      prompt-runner invocation.
  - **USES:** `.prompt-runner/src/cli/prompt_runner/runner.py`
    - **BECAUSE:** That module executes the generator/judge revision loop.
  - **PROMPT-MODULE: PMOD-1** PH-007 prompt-runner input file
    - **SYNOPSIS:** The PH-007 prompt-runner input file is
      `.methodology/docs/prompts/PR-030-ph007-verification-sweep.md`.
    - **BECAUSE:** The phase uses one fixed module shape.
    - **READS:** `docs/features/feature-specification.yaml`
      - **BECAUSE:** That file is the main source for end-to-end verification
        scope.
    - **READS:** `docs/implementation/implementation-plan.yaml`
      - **BECAUSE:** That file keeps the report tied to planned implementation
        and tests.
    - **READS:** `docs/design/solution-design.yaml`
      - **BECAUSE:** That file keeps the traceability chain grounded in the
        design layer.
    - **READS:** `docs/requirements/requirements-inventory.yaml`
      - **BECAUSE:** That file keeps the report tied to the original `RI-*`
        items.
    - **AGENT:** `Generator Agent`
      - **SYNOPSIS:** Embedded generator definition in the PH-007 module.
      - **BECAUSE:** The generator setup is fixed for this phase.
      - **RULE:** Embedded PH-007 generation directives
        - **SYNOPSIS:** Keep every verification claim tied to real upstream
          artifacts through prompt-embedded traceability guidance.
        - **BECAUSE:** `PH-007` must stay traceable without runtime skill discovery.
      - **RULE:** Prompt-local verification directives
        - **SYNOPSIS:** The module itself defines chain completeness, E2E
          specificity, and honest coverage accounting.
        - **BECAUSE:** PH-007-specific generation behavior now lives in the
          prompt, not in a phase-only skill.
    - **AGENT:** `Judge Agent`
      - **SYNOPSIS:** Embedded judge definition in the PH-007 module.
      - **BECAUSE:** The judge setup is fixed for this phase.
      - **RULE:** Embedded PH-007 review directives
        - **BECAUSE:** The judge uses prompt-embedded traceability and review
          guidance instead of separate runtime skill loading.
      - **RULE:** Prompt-local verification review directives
        - **SYNOPSIS:** The module itself defines the PH-007 review checks for
          broken chains, superficial tests, missing negative coverage, and misleading claims.
        - **BECAUSE:** PH-007-specific review behavior now lives in the
          prompt, not in a phase-only skill.
    - **PROMPT-PAIR: Prompt 1**
      - **PROMPT:** `Generator`
        - **SYNOPSIS:** Reads the feature, implementation, solution design,
          and requirements artifacts and writes
          `docs/verification/verification-report.yaml`.
        - **BECAUSE:** The generator owns artifact production.
        - **USES:** `Generator Agent`
          - **BECAUSE:** The prompt pair should use the embedded generator
            definition already declared in the prompt module.
        - **USES:** embedded PH-007 verification directives
          - **BECAUSE:** The generator's specialized guidance is embedded in
            the prompt body.
        - **USES:** prompt-local PH-007 verification directives
          - **BECAUSE:** The generator's phase-specific behavior is embedded
            in the module.
      - **PROMPT:** `Judge`
        - **SYNOPSIS:** Reviews chain completeness, E2E specificity, negative
          coverage, and coverage accounting.
        - **BECAUSE:** The judge decides whether the file passes or needs
          another revision.
        - **USES:** `Judge Agent`
          - **BECAUSE:** The prompt pair should use the embedded judge
            definition already declared in the prompt module.
        - **USES:** embedded PH-007 review directives
          - **BECAUSE:** The judge's specialized guidance is embedded in the
            prompt body.
        - **USES:** prompt-local PH-007 review directives
          - **BECAUSE:** The judge's phase-specific behavior is embedded in
            the module.
  - **READS:** embedded prompt-body directive blocks
    - **BECAUSE:** `PH-007` keeps its fixed specialized guidance in the module.
  - **LAUNCHES:** generator session
    - **BECAUSE:** The artifact must be produced before it can be judged.
  - **LAUNCHES:** judge session
    - **BECAUSE:** The artifact must be reviewed for phase readiness and
      either passed, revised, or escalated.
  - **RESUMES:** the same artifact path across iterations
    - **BECAUSE:** `PH-007` revises the same output file. It does not create
      draft variants.

- **PROCESS: PROCESS-3** Accept or reject the phase result
  - **SYNOPSIS:** The phase is accepted only when the prompt-runner loop passes
    and the resulting artifact is accepted as the phase output.
  - **VALIDATES:** `docs/verification/verification-report.yaml`
    - **BECAUSE:** The output file must exist before the phase can pass.
  - **USES:** `scripts/phase-7-deterministic-validation.py`
    - **BECAUSE:** `PH-007` uses deterministic checks for schema, reference
      existence, coverage counts, and top-level shape.
  - **BECAUSE:** `PH-007` passes only when both the deterministic checks and
    the judge review pass.
  - **PRODUCES:** `docs/verification/verification-report.yaml`
    - **BECAUSE:** That artifact is the final durable output of the
      methodology chain.

## 5. Constraints

This section states the main limits on the phase.

- **RULE: RULE-5** No fake completeness
  - **SYNOPSIS:** The phase must not fabricate full coverage when the upstream
    artifacts only support partial or uncovered status.
  - **BECAUSE:** The final report must be honest about real gaps.

- **RULE: RULE-6** No superficial end-to-end tests
  - **SYNOPSIS:** E2E tests must verify feature-specific outcomes, not generic
    “it works” behavior.
  - **BECAUSE:** The final report must prove real verification value.

- **RULE: RULE-7** One fixed prompt module
  - **SYNOPSIS:** `PH-007` must use the predefined prompt module instead of
    building a new module per run.
  - **BECAUSE:** The module shape should stay stable.

## 6. Output Shape

This section states what the output file contains.

- **ENTITY: ENTITY-1** Top-level output shape
  - **SYNOPSIS:** The top-level sections are:
    - `e2e_tests`
    - `traceability_matrix`
    - `coverage_summary`
  - **BECAUSE:** That is the schema required by the PH-007 phase contract.

- **ENTITY: ENTITY-2** E2E test fields
  - **SYNOPSIS:** Each E2E test contains:
    - `id`
    - `name`
    - `feature_ref`
    - `acceptance_criteria_refs`
    - `type`
    - `setup`
    - `actions`
    - `assertions`
  - **BECAUSE:** Those are the fields the final verification artifact relies
    on.

## 7. Definition Of Good

This section states when the phase passes.

- **RULE: RULE-8** Full traceability accounting
  - **SYNOPSIS:** Every `RI-*` item must appear in the `traceability_matrix`
    with an honest `coverage_status`.
  - **BECAUSE:** The final report must account for the whole requirement set.

- **RULE: RULE-9** Concrete E2E verification
  - **SYNOPSIS:** E2E tests must connect real `FT-*` and `AC-*` references to
    concrete setup, actions, and assertions.
  - **BECAUSE:** The final report depends on reviewable end-to-end tests.

- **RULE: RULE-10** Honest coverage summary
  - **SYNOPSIS:** `coverage_summary` counts must match the matrix and must not
    overstate coverage.
  - **BECAUSE:** The final report must provide trustworthy coverage numbers.

- **RULE: RULE-11** Deterministic and judge checks both pass
  - **SYNOPSIS:** The phase passes only if the deterministic validator passes
    and the judge returns `VERDICT: pass`.
  - **BECAUSE:** `PH-007` needs both shape checks and content checks.

## 8. Test Cases

This section lists the tests the phase design expects.

- **TEST CASE: TC-1** Full traceability accounting
  - **SYNOPSIS:** Run the phase on a known `RI-*` inventory and confirm every
    requirement appears in the matrix with a matching coverage status.
  - **BECAUSE:** The design depends on full accounting of the requirement set.

- **TEST CASE: TC-2** Embedded directive blocks
  - **SYNOPSIS:** Confirm the PH-007 module embeds the required verification,
    traceability, and review directives directly in the prompt body.
  - **BECAUSE:** The module is supposed to be self-contained.

- **TEST CASE: TC-3** Output file path
  - **SYNOPSIS:** Run PH-007 and confirm the artifact written is
    `docs/verification/verification-report.yaml`.
  - **BECAUSE:** The phase should produce one stable output file.

- **TEST CASE: TC-4** Misleading coverage rejection
  - **SYNOPSIS:** Run the phase with a report that overstates coverage and
    confirm the deterministic and judge loop rejects it.
  - **BECAUSE:** Misleading final coverage claims should not pass this phase.
