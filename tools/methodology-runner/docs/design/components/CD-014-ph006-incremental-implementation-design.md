# Design: PH-006 Incremental Implementation

## 1. Finality

This design explains how `PH-006` works from start to finish.

- **GOAL: GOAL-1** Produce an executable implementation workflow and its run report
  - **SYNOPSIS:** `PH-006` turns the approved solution into:
    - `docs/implementation/implementation-workflow.md`
    - `docs/implementation/implementation-run-report.yaml`
  - **BECAUSE:** This phase no longer writes another planning artifact. It authors a child prompt-runner workflow, runs that workflow against the real project worktree, and records what happened.

## 2. Inputs And Outputs

This section names the files that the phase uses.

- **FILE: FILE-1** Solution design
  - **SYNOPSIS:** Primary input:
    - `docs/design/solution-design.yaml`
  - **BECAUSE:** The implementation workflow must be grounded in the approved system shape.

- **FILE: FILE-2** Interface contracts
  - **SYNOPSIS:** Validation reference:
    - `docs/design/interface-contracts.yaml`
  - **BECAUSE:** The workflow must implement real contract behavior, not generic code slices.

- **FILE: FILE-3** Simulation definitions
  - **SYNOPSIS:** Validation reference:
    - `docs/simulations/simulation-definitions.yaml`
  - **BECAUSE:** The workflow must know which temporary simulations exist and when real implementation can replace them.

- **FILE: FILE-4** Feature specification
  - **SYNOPSIS:** Validation reference:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** The workflow must keep implementation slices tied to real `FT-*` and `AC-*` meaning.

- **FILE: FILE-5** Implementation workflow
  - **SYNOPSIS:** Primary output:
    - `docs/implementation/implementation-workflow.md`
  - **BECAUSE:** This is the child prompt-runner module that performs the real implementation work.

- **FILE: FILE-6** Implementation run report
  - **SYNOPSIS:** Secondary output:
    - `docs/implementation/implementation-run-report.yaml`
  - **BECAUSE:** Later phases need truthful evidence of what the child workflow actually did.

- **FILE: FILE-7** Prompt-runner module
  - **SYNOPSIS:** `tools/methodology-runner/src/methodology_runner/prompts/PR-029-ph006-incremental-implementation.md`
  - **BECAUSE:** `PH-006` uses one predefined phase module. That module authors the child workflow first, then runs it.

## 3. Technical Directives

This section states the technical directives that shape the phase.

- **RULE: RULE-1** Use the predefined prompt module
  - **SYNOPSIS:** The phase must use `tools/methodology-runner/src/methodology_runner/prompts/PR-029-ph006-incremental-implementation.md`.
  - **BECAUSE:** The PH-006 flow is fixed: author workflow, validate workflow, run child workflow, report truthfully.

- **RULE: RULE-2** Author a child workflow, not another planning spec
  - **SYNOPSIS:** Prompt 1 must write a valid child prompt-runner file at `docs/implementation/implementation-workflow.md`.
  - **BECAUSE:** The purpose of PH-006 is to start implementation through controlled prompt slices, not to add another abstract planning layer.

- **RULE: RULE-3** The child workflow must be TDD-oriented
  - **SYNOPSIS:** Each implementation child prompt must:
    - define one small implementation slice
    - require a failing or tightened test when new behavior is introduced
    - require the relevant tests to run after the code change
  - **BECAUSE:** This phase is supposed to guide real incremental implementation, not batch a large untested code dump.

- **RULE: RULE-4** The child workflow must target the real project worktree
  - **SYNOPSIS:** Prompt 2 must run or resume the child workflow against the current `run_dir`.
  - **BECAUSE:** The workflow is supposed to create real code, tests, and supporting project files in the workspace being built.

- **RULE: RULE-4A** Child prompts that run commands must report them explicitly
  - **SYNOPSIS:** Any child prompt that runs tests or verification commands must require a fixed generator response section that lists the commands run and the observed outcome for each one.
  - **BECAUSE:** The child prompt judges intentionally validate against the child prompt's own generator response text plus the concrete files, so command execution evidence has to be explicit in that response.

- **RULE: RULE-5** The child workflow must end with final verification
  - **SYNOPSIS:** The last child prompt must run the full verification commands for the implemented system.
  - **BECAUSE:** PH-006 is not complete when code exists. It is complete when the workflow has driven the build to a verifiable end state.

- **RULE: RULE-6** The run report must be truthful
  - **SYNOPSIS:** Prompt 2 must write only evidence that the child run actually produced.
  - **BECAUSE:** PH-007 depends on this report as implementation evidence. Fabricated completion or invented command history would corrupt final verification.

## 4. Workflow

This section describes the phase steps.

- **PROCESS: PROCESS-1** Define the phase contract
  - **SYNOPSIS:** `PH-006` defines the input files, output files, placeholder values, workflow requirements, and run-report schema.
  - **READS:** `tools/methodology-runner/src/methodology_runner/phases.py`
    - **BECAUSE:** The phase registry is the source of truth for artifact paths and validation references.
  - **READS:** `tools/methodology-runner/src/methodology_runner/orchestrator.py`
    - **BECAUSE:** The orchestrator injects `prompt_runner_command` and other runtime values used by Prompt 2.

- **PROCESS: PROCESS-2** Author the child implementation workflow
  - **SYNOPSIS:** Prompt 1 writes `docs/implementation/implementation-workflow.md`.
  - **USES:** `tools/methodology-runner/src/methodology_runner/prompts/PR-029-ph006-incremental-implementation.md`
    - **BECAUSE:** The prompt module contains the phase-specific generator and judge rules.
  - **PROMPT-MODULE: PMOD-1** PH-006 phase module
    - **SYNOPSIS:** The PH-006 phase module has two prompt pairs.
    - **BECAUSE:** The phase first needs a workflow artifact, then an execution report.
    - **PROMPT-PAIR: Prompt 1**
      - **PROMPT:** `Generator`
        - **SYNOPSIS:** Writes the child workflow file.
        - **READS:** `docs/design/solution-design.yaml`
          - **BECAUSE:** The implementation slices must respect the approved system structure.
        - **READS:** `docs/design/interface-contracts.yaml`
          - **BECAUSE:** The workflow must implement concrete contract behavior.
        - **READS:** `docs/simulations/simulation-definitions.yaml`
          - **BECAUSE:** The workflow must know what temporary simulations exist and when they can be replaced.
        - **READS:** `docs/features/feature-specification.yaml`
          - **BECAUSE:** The workflow must ground implementation slices in feature and acceptance-criterion meaning.
        - **RULE:** Just-in-time source embedding
          - **SYNOPSIS:** Prompt 1 embeds the approved design, contracts, simulations, and feature specification inline in `Context` with `{{INCLUDE:...}}`.
          - **BECAUSE:** The workflow-authoring prompt should begin with its task and then present the upstream inputs where it uses them.
      - **PROMPT:** `Judge`
        - **SYNOPSIS:** Reviews the workflow for executability, TDD cadence, slice size, traceability, and final-verification coverage.
        - **BECAUSE:** The workflow must be phase-ready before any child run starts.
        - **RULE:** Just-in-time artifact embedding
          - **SYNOPSIS:** Prompt 1's judge embeds the current child workflow inline in `Context` with `{{RUNTIME_INCLUDE:docs/implementation/implementation-workflow.md}}`.
          - **BECAUSE:** The workflow under review should appear where the judge compares it to the upstream design inputs.

- **PROCESS: PROCESS-3** Deterministically validate the child workflow
  - **SYNOPSIS:** The phase validates that the workflow file exists, parses, has a file-level module, and contains the required TDD and final-verification structure.
  - **USES:** `tools/methodology-runner/src/methodology_runner/phase_6_validation.py`
    - **BECAUSE:** Mechanical workflow checks should not be left to the LLM judge.

- **PROCESS: PROCESS-4** Run or resume the child workflow
  - **SYNOPSIS:** Prompt 2 parses the child workflow, runs or resumes it with child `prompt_runner`, and records what happened in `docs/implementation/implementation-run-report.yaml`.
  - **INVOKES:** `{{prompt_runner_command}}`
    - **BECAUSE:** The child workflow is itself a prompt-runner module.
  - **RULE:** Disable project-organiser injection for the child run
    - **SYNOPSIS:** Prompt 2 should invoke the child workflow with `--no-project-organiser`.
    - **BECAUSE:** The child prompts operate on fixed, already-declared workspace paths rather than classifying new files against the repository taxonomy.
  - **LAUNCHES:** child prompt-runner execution
    - **BECAUSE:** The authored workflow has to be executed against the project worktree to create real implementation artifacts.
  - **WRITES:** `docs/implementation/implementation-run-report.yaml`
    - **BECAUSE:** Later verification needs a truthful summary of child prompt outcomes, changed files, and observed test commands.
  - **RULE:** Mixed include timing for Prompt 2
    - **SYNOPSIS:** Prompt 2 embeds `docs/implementation/implementation-workflow.md` inline with `{{INCLUDE:...}}`, and its judge embeds `docs/implementation/implementation-run-report.yaml` inline with `{{RUNTIME_INCLUDE:...}}`.
    - **BECAUSE:** The child workflow exists before Prompt 2 starts, but the run report does not exist until Prompt 2's generator writes it.

- **PROCESS: PROCESS-5** Accept or reject the phase result
  - **SYNOPSIS:** The phase passes only when:
    - the child workflow file is valid
    - the child run report is valid
    - the prompt-runner judge(s) pass
  - **VALIDATES:** `docs/implementation/implementation-workflow.md`
    - **BECAUSE:** The workflow is a durable phase artifact.
  - **VALIDATES:** `docs/implementation/implementation-run-report.yaml`
    - **BECAUSE:** The run report is the other durable phase artifact.
  - **USES:** `tools/methodology-runner/src/methodology_runner/phase_6_validation.py`
    - **BECAUSE:** Deterministic validation checks workflow shape and report truthfulness constraints that should not drift.

## 5. Constraints

This section states the main limits on the phase.

- **RULE: RULE-7** No abstract planning drift
  - **SYNOPSIS:** The child workflow must not degrade into another implementation-plan artifact.
  - **BECAUSE:** PH-006 is supposed to start real implementation work.

- **RULE: RULE-8** No fake child-run completion
  - **SYNOPSIS:** The run report must not claim completed status, passed prompts, changed files, or observed test commands that the child run did not produce.
  - **BECAUSE:** PH-007 depends on PH-006 evidence.

- **RULE: RULE-9** One fixed phase module
  - **SYNOPSIS:** PH-006 must use the checked-in phase module rather than inventing a new outer module per run.
  - **BECAUSE:** The outer phase contract should stay stable.

## 6. Output Shape

This section states what the phase produces.

- **ENTITY: ENTITY-1** Child workflow structure
  - **SYNOPSIS:** `docs/implementation/implementation-workflow.md` must:
    - begin with a file-level `### Module`
    - use the slug `implementation-workflow`
    - contain at least two child prompts
    - include a final child prompt that runs full verification commands
  - **BECAUSE:** The workflow has to be executable by child prompt-runner and complete enough to finish the implementation pass.

- **ENTITY: ENTITY-2** Run report structure
  - **SYNOPSIS:** `docs/implementation/implementation-run-report.yaml` contains:
    - `child_prompt_path`
    - `child_run_dir`
    - `execution_mode`
    - `completion_status`
    - `halt_reason`
    - `prompt_results`
    - `files_changed`
    - `test_commands_observed`
    - `next_action`
  - **BECAUSE:** PH-007 needs those fields to understand what was implemented and how trustworthy the current workspace state is.

## 7. Definition Of Good

This section states when the phase passes.

- **RULE: RULE-10** Executable workflow
  - **SYNOPSIS:** The workflow parses cleanly and each child prompt defines a real implementation slice or the final verification step.
  - **BECAUSE:** PH-006 is only useful if the authored workflow can actually run.

- **RULE: RULE-11** TDD slice discipline
  - **SYNOPSIS:** At least one child implementation prompt explicitly tightens or adds a test before code changes, and implementation prompts run the relevant tests after the edit.
  - **BECAUSE:** The workflow is supposed to guide incremental TDD implementation.

- **RULE: RULE-12** Truthful run report
  - **SYNOPSIS:** The run report agrees with the child `.run-files/implementation-workflow/summary.txt` and observed child-run artifacts.
  - **BECAUSE:** Later verification cannot rely on guessed execution history.

- **RULE: RULE-13** Deterministic and judge checks both pass
  - **SYNOPSIS:** The phase passes only if deterministic validation passes and the outer phase module judge returns `VERDICT: pass`.
  - **BECAUSE:** Both mechanical correctness and semantic correctness matter.

## 8. Test Cases

This section lists the tests the design expects.

- **TEST CASE: TC-1** Workflow parseability
  - **SYNOPSIS:** Generate a child workflow and confirm prompt-runner can parse it as a file-level module with the expected slug.
  - **BECAUSE:** The workflow is useless if the child runner cannot parse it.

- **TEST CASE: TC-2** Completed child run
  - **SYNOPSIS:** Run a child workflow to completion and confirm the run report records completed status, prompt verdicts, changed files, and observed test commands truthfully.
  - **BECAUSE:** A successful child run is the normal PH-006 happy path.

- **TEST CASE: TC-3** Halted child run
  - **SYNOPSIS:** Validate that a halted child run produces a run report with non-empty `halt_reason` and does not claim full completion.
  - **BECAUSE:** Failure reporting must be truthful too.
