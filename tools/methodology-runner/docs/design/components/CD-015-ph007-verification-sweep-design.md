# Design: PH-007 Verification Sweep

## 1. Finality

This design explains how `PH-007` works from start to finish.

- **GOAL: GOAL-1** Produce the final verification report
  - **SYNOPSIS:** `PH-007` turns the implemented workspace and the PH-006 execution evidence into one acceptance-ready `docs/verification/verification-report.yaml` file.
  - **BECAUSE:** This is the final truthfulness check for the methodology chain.

## 2. Inputs And Outputs

This section names the files that the phase uses.

- **FILE: FILE-1** Requirements inventory
  - **SYNOPSIS:** Primary input:
    - `docs/requirements/requirements-inventory.yaml`
  - **BECAUSE:** Final verification is requirement-by-requirement.

- **FILE: FILE-2** Feature specification
  - **SYNOPSIS:** Validation reference:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** Feature links help explain how implemented behavior relates back to requirements.

- **FILE: FILE-3** Implementation workflow
  - **SYNOPSIS:** Validation reference:
    - `docs/implementation/implementation-workflow.md`
  - **BECAUSE:** Final verification must know what the child implementation workflow was supposed to do and whether it contained final verification commands.

- **FILE: FILE-4** Implementation run report
  - **SYNOPSIS:** Primary execution-evidence input:
    - `docs/implementation/implementation-run-report.yaml`
  - **BECAUSE:** This report names the changed files, observed test commands, and completion state of the child run.

- **FILE: FILE-5** Verification report
  - **SYNOPSIS:** Primary output:
    - `docs/verification/verification-report.yaml`
  - **BECAUSE:** This is the durable output consumed as the final verification artifact.

- **FILE: FILE-6** Prompt-runner module
  - **SYNOPSIS:** `tools/methodology-runner/src/methodology_runner/prompts/PR-030-ph007-verification-sweep.md`
  - **BECAUSE:** `PH-007` uses one predefined phase module for final verification.

## 3. Technical Directives

This section states the technical directives that shape the phase.

- **RULE: RULE-1** Use the predefined prompt module
  - **SYNOPSIS:** The phase must use `tools/methodology-runner/src/methodology_runner/prompts/PR-030-ph007-verification-sweep.md`.
  - **BECAUSE:** The final-verification contract should stay stable across runs.

- **RULE: RULE-2** Verify the real implemented workspace
  - **SYNOPSIS:** The generator must inspect real files and real verification evidence from the current workspace.
  - **BECAUSE:** PH-007 is not a hypothetical test plan. It is a report about what is actually implemented now.

- **RULE: RULE-3** Use child-run evidence as the primary execution record
  - **SYNOPSIS:** The generator must use `docs/implementation/implementation-run-report.yaml` as the authoritative source for:
    - whether the child run completed
    - which files were changed
    - which commands were already observed
  - **BECAUSE:** PH-006 is the implementation phase. PH-007 should build on that evidence rather than inventing a new execution history.

- **RULE: RULE-4** Permit low-cost re-verification when needed
  - **SYNOPSIS:** The generator may rerun low-cost verification commands to confirm current behavior.
  - **BECAUSE:** Final verification sometimes needs direct confirmation of the present workspace state.

- **RULE: RULE-5** Require truthful requirement status
  - **SYNOPSIS:** Every `RI-*` must be marked:
    - `satisfied`
    - `partial`
    - `unsatisfied`
  - **BECAUSE:** The final report must honestly state what the implementation evidence supports.

- **RULE: RULE-6** Do not award satisfaction on subjective inference
  - **SYNOPSIS:** A requirement must not be marked `satisfied` when the evidence is only stylistic, interpretive, or indirectly suggestive.
  - **BECAUSE:** Final verification has to rely on concrete evidence, not hopeful reading of qualitative phrases.

- **RULE: RULE-6A** Verification may add compatible operational specificity
  - **SYNOPSIS:** PH-007 may use concrete verification commands and implementation-aware checks, but it must not treat a requirement as unsatisfied merely because the implementation is more or less specifically rendered than a downstream preference unless that detail is required by approved upstream artifacts or changes the requirement's meaning.
  - **BECAUSE:** Final verification has to assess the real implemented workspace, which often requires concrete checks; the defect is contradiction with upstream intent, not the mere presence of extra downstream detail.

## 4. Workflow

This section describes the phase steps.

- **PROCESS: PROCESS-1** Define the phase contract
  - **SYNOPSIS:** `PH-007` defines the input files, output file, evidence rules, review rules, and output schema.
  - **READS:** `tools/methodology-runner/src/methodology_runner/phases.py`
    - **BECAUSE:** The phase registry is the source of truth for input and output paths.

- **PROCESS: PROCESS-2** Execute the verification module
  - **SYNOPSIS:** The methodology runner runs the predefined PH-007 module with prompt-runner.
  - **USES:** `tools/methodology-runner/src/methodology_runner/orchestrator.py`
    - **BECAUSE:** The orchestrator owns the phase lifecycle.
  - **USES:** `tools/prompt-runner/src/prompt_runner/runner.py`
    - **BECAUSE:** That module executes the generator/judge revision loop.
  - **PROMPT-MODULE: PMOD-1** PH-007 phase module
    - **SYNOPSIS:** The PH-007 module has one prompt pair.
    - **BECAUSE:** The phase writes one verification artifact and judges it directly.
    - **PROMPT-PAIR: Prompt 1**
      - **PROMPT:** `Generator`
        - **SYNOPSIS:** Performs final verification and writes `docs/verification/verification-report.yaml`.
        - **READS:** `docs/requirements/requirements-inventory.yaml`
          - **BECAUSE:** Every requirement must be assessed individually.
        - **READS:** `docs/features/feature-specification.yaml`
          - **BECAUSE:** Feature links help explain implementation coverage where they exist.
        - **READS:** `docs/implementation/implementation-workflow.md`
          - **BECAUSE:** The final verification phase must know the structure and intent of the child implementation workflow.
        - **READS:** `docs/implementation/implementation-run-report.yaml`
          - **BECAUSE:** The run report is the primary execution-evidence source.
        - **RULE:** Just-in-time source embedding
          - **SYNOPSIS:** The generator and judge embed the requirements inventory, feature specification, implementation workflow, and implementation run report inline in `Context` with `{{INCLUDE:...}}`.
          - **BECAUSE:** Final verification should begin with the verification task and then present the upstream evidence where that task uses it.
      - **PROMPT:** `Judge`
        - **SYNOPSIS:** Reviews the report for truthfulness, evidence quality, honest coverage, unsupported satisfaction claims, and contradiction with upstream-approved semantics.
        - **BECAUSE:** The final report must not overstate what was actually verified.
        - **RULE:** Just-in-time artifact embedding
          - **SYNOPSIS:** The judge embeds the current verification report inline in `Context` with `{{RUNTIME_INCLUDE:docs/verification/verification-report.yaml}}`.
          - **BECAUSE:** The report under review should appear where the judge compares it to the upstream evidence set.

- **PROCESS: PROCESS-3** Deterministically validate the report
  - **SYNOPSIS:** The phase checks the top-level report shape, RI coverage, and command-evidence consistency.
  - **USES:** `tools/methodology-runner/src/methodology_runner/phase_7_validation.py`
    - **BECAUSE:** Mechanical report checks should stay deterministic.

- **PROCESS: PROCESS-4** Accept or reject the phase result
  - **SYNOPSIS:** The phase passes only when:
    - the verification report exists
    - deterministic validation passes
    - the judge returns `VERDICT: pass`
  - **VALIDATES:** `docs/verification/verification-report.yaml`
    - **BECAUSE:** This is the durable phase output.

## 5. Constraints

This section states the main limits on the phase.

- **RULE: RULE-7** No phantom satisfaction
  - **SYNOPSIS:** A row must not say `satisfied` unless materially relevant files or commands support that claim.
  - **BECAUSE:** Unsupported success claims break the integrity of final verification.

- **RULE: RULE-8** No ignored child-run failures
  - **SYNOPSIS:** A halted or incomplete child run must not be reported as if the implementation completed normally.
  - **BECAUSE:** PH-007 depends on PH-006 run truthfulness.

- **RULE: RULE-9** No contradiction with observed evidence
  - **SYNOPSIS:** Evidence notes must not contradict exact command outputs, test assertions, or file contents.
  - **BECAUSE:** Final verification is only useful if it agrees with the actual workspace evidence.

- **RULE: RULE-9A** No contradiction with upstream-approved behavior
  - **SYNOPSIS:** Verification may rely on more concrete checks than upstream artifacts, but it must not fail or downgrade behavior that still satisfies the approved upstream requirement meaning.
  - **BECAUSE:** The verification phase should preserve approved intent while still using practical concrete checks against the implemented workspace.

## 6. Output Shape

This section states what the output file contains.

- **ENTITY: ENTITY-1** Top-level report shape
  - **SYNOPSIS:** The top-level keys are:
    - `verification_commands`
    - `requirement_results`
    - `coverage_summary`
  - **BECAUSE:** That is the required PH-007 report schema.

- **ENTITY: ENTITY-2** Verification command entry
  - **SYNOPSIS:** Each `verification_commands` entry contains:
    - `command`
    - `exit_code`
    - `purpose`
    - `evidence`
  - **BECAUSE:** The report needs concrete command-level verification evidence.

- **ENTITY: ENTITY-3** Requirement result entry
  - **SYNOPSIS:** Each `requirement_results` entry contains:
    - `inventory_ref`
    - `feature_refs`
    - `status`
    - `evidence.files`
    - `evidence.commands`
    - `evidence.notes`
  - **BECAUSE:** PH-007 is requirement-centered and evidence-centered.

- **ENTITY: ENTITY-4** Coverage summary
  - **SYNOPSIS:** `coverage_summary` contains:
    - `total_requirements`
    - `satisfied`
    - `partial`
    - `unsatisfied`
    - `satisfaction_percentage`
  - **BECAUSE:** The report needs an honest aggregate view after row-by-row verification.

## 7. Definition Of Good

This section states when the phase passes.

- **RULE: RULE-10** Full RI coverage
  - **SYNOPSIS:** Every `RI-*` appears exactly once in `requirement_results`.
  - **BECAUSE:** Final verification must account for the whole inventory.

- **RULE: RULE-11** Truthful evidence
  - **SYNOPSIS:** Every row's status is materially supported by file evidence, command evidence, or both.
  - **BECAUSE:** The report is supposed to describe reality, not intention.

- **RULE: RULE-12** Honest partial status
  - **SYNOPSIS:** If the evidence supports only part of a requirement, the row must say `partial` rather than force `satisfied`.
  - **BECAUSE:** Overstated success is worse than explicit incompleteness.

- **RULE: RULE-13** Deterministic and judge checks both pass
  - **SYNOPSIS:** The phase passes only if deterministic validation passes and the judge returns `VERDICT: pass`.
  - **BECAUSE:** The report needs both mechanical and semantic verification.

## 8. Test Cases

This section lists the tests the design expects.

- **TEST CASE: TC-1** Requirement coverage
  - **SYNOPSIS:** Confirm every `RI-*` in the inventory appears in the final report.
  - **BECAUSE:** Final verification must cover the whole inventory.

- **TEST CASE: TC-2** Subjective-satisfaction rejection
  - **SYNOPSIS:** Present a report that marks a qualitative requirement `satisfied` without concrete evidence and confirm the judge rejects it.
  - **BECAUSE:** PH-007 must not pass unsupported satisfaction claims.

- **TEST CASE: TC-3** Command-evidence consistency
  - **SYNOPSIS:** Present a report whose evidence notes contradict the observed commands and confirm the phase rejects it.
  - **BECAUSE:** Evidence contradictions should not survive final verification.
