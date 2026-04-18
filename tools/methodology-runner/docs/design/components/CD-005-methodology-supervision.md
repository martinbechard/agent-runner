# Design: Methodology Supervision And Recovery

## 1. Requirements

This section defines the supervisory layer that keeps the optimization workflow progressing when workflow runs fail or escalate.

- **REQUIREMENT: REQ-1** Supervise optimization workflow completion
  - **SYNOPSIS:** A top-level supervisor SHOULD run the optimization workflow, inspect its outcome, and decide whether to pass, revise, resume, or restart.
    - **BECAUSE:** The optimization workflow is long-running and failure-prone enough that it benefits from a dedicated recovery layer.

- **REQUIREMENT: REQ-2** Distinguish workflow-module defects from workflow-state defects
  - **SYNOPSIS:** The supervisor MUST tell the difference between a bad optimization workflow prompt definition and an incomplete optimization workflow run that should simply be resumed.
    - **BECAUSE:** Rewriting the workflow module when the real issue is late-stage workflow state wastes time and destroys good partial progress.

- **REQUIREMENT: REQ-3** Prefer resume over restart
  - **SYNOPSIS:** The supervisor SHOULD resume late-stage workflow failures when the existing workflow artifacts are still usable.
    - **BECAUSE:** Restarting from scratch discards already-passed work and obscures the real failure point.

- **REQUIREMENT: REQ-4** Persist supervisory state
  - **SYNOPSIS:** The supervisor MUST keep a run summary that records what happened in the last workflow attempt and what the next retry should do.
    - **BECAUSE:** Later retries need a stable handoff instead of reconstructing prior failures from memory.

## 2. Information Model

This section defines the main supervision concepts.

- **ENTITY: ENTITY-1** `OptimizationWorkflowAttempt`
  - **SYNOPSIS:** One supervised execution attempt of the optimization workflow.
  - **FIELD:** `workflow_prompt`
    - **SYNOPSIS:** Optimization workflow prompt file and placeholder context used by the attempt.
    - **BECAUSE:** The supervisor must know which workflow definition it executed or considered revising.
  - **FIELD:** `workflow_run_dir`
    - **SYNOPSIS:** `<workflow-root>/prompt-runs/workflow/`
    - **BECAUSE:** Resume and evaluation depend on the workflow run record.
  - **FIELD:** `workflow_manifest`
    - **SYNOPSIS:** Workflow manifest written by the optimization workflow runner.
    - **BECAUSE:** The supervisor reads one manifest to determine whether the workflow halted or completed.
  - **FIELD:** `passed_stage_verdicts`
    - **SYNOPSIS:** Stage verdict files that already passed in the workflow run.
    - **BECAUSE:** Resume decisions depend on how far the workflow progressed.

- **ENTITY: ENTITY-2** `SupervisorReport`
  - **SYNOPSIS:** Persisted report summarizing the latest supervised workflow attempt.
  - **FIELD:** `workflow_run_path`
    - **SYNOPSIS:** Path to the optimization workflow run that was evaluated.
    - **BECAUSE:** Later retries need to know which workflow run they are inspecting.
  - **FIELD:** `passed_stages`
    - **SYNOPSIS:** Workflow stages that already passed.
    - **BECAUSE:** Resume decisions depend on how far the workflow progressed.
  - **FIELD:** `next_action`
    - **SYNOPSIS:** Whether the next attempt should revise the workflow module, resume the workflow, or restart the workflow.
    - **BECAUSE:** The supervisor exists to make that decision explicit.
  - **FIELD:** `execution_mode`
    - **SYNOPSIS:** Whether the last attempt used fresh-run or resume mode.
    - **BECAUSE:** Recovery logic depends on whether the supervisor already tried to reuse the existing workflow state.

## 3. Prompt Module

This section defines the prompt module that supervises the optimization workflow. The descriptive module name is the concept; the filename is only the current implementation reference.

- **PROMPT-MODULE: PMOD-1** `Supervision module`
  - **SYNOPSIS:** Prompt-definition file that reviews optimization workflow failures, decides whether the workflow prompt needs editing, then runs or resumes the workflow and records the result.
  - **FIELD:** `current_file`
    - **SYNOPSIS:** `docs/prompts/PR-020-methodology-optimization-supervisor.md`
    - **BECAUSE:** This is the current file that implements the supervision module.
  - **SUPPORTS:** Supervise optimization workflow completion
    - **BECAUSE:** This module owns the supervisory control loop around the optimization workflow.
  - **SUPPORTS:** Distinguish workflow-module defects from workflow-state defects
    - **BECAUSE:** The module has one pair for workflow-file revision decisions and one pair for execution-and-judgment of the workflow run.
  - **SUPPORTS:** Prefer resume over restart
    - **BECAUSE:** The execution pair chooses between fresh-run and resume mode based on the existing workflow state.
  - **SUPPORTS:** Persist supervisory state
    - **BECAUSE:** The execution pair writes the supervisor report after each workflow attempt.
  - **PROMPT-PAIR:** `Review whether the optimization workflow file really needs editing`
    - **SYNOPSIS:** Pair whose generator reviews the latest workflow failure evidence and whose judge decides whether the optimization workflow prompt file truly needs revision.
    - **PROMPT:** `Generator`
      - **SYNOPSIS:** Reads the optimization workflow prompt file and any existing workflow-stage verdicts, then proposes whether the workflow definition itself needs editing.
      - **BECAUSE:** The supervisor must inspect evidence before deciding whether it is facing a prompt defect or only a workflow-state defect.
    - **PROMPT:** `Judge`
      - **SYNOPSIS:** Decides whether the evidence really points to a defect in the optimization workflow prompt file rather than to an incomplete workflow run.
      - **BECAUSE:** Prompt edits should happen only when the evidence supports prompt revision.
  - **PROMPT-PAIR:** `Run or resume the optimization workflow`
    - **SYNOPSIS:** Pair whose generator runs or resumes the optimization workflow and whose judge decides whether the resulting workflow state is good enough to pass supervision.
    - **PROMPT:** `Generator`
      - **SYNOPSIS:** Starts or resumes `prompt-runner` on the optimization workflow prompt file, then writes the supervisor report for that attempt.
      - **BECAUSE:** The supervisor needs one execution prompt that also records the resulting workflow state.
    - **PROMPT:** `Judge`
      - **SYNOPSIS:** Reads the workflow manifest, workflow-stage verdict files, and supervisor report, then either passes supervision or sends corrective feedback.
      - **BECAUSE:** Supervision must judge the real workflow outputs, not only the execution attempt itself.

## 4. Gaps

This section records the remaining supervisory-design issues.

- **GAP:** Prompt-level supervision still carries too much runtime policy
  - **SYNOPSIS:** Resume, restart, and execution-control rules still live partly in prompt prose instead of in explicit runtime features.
    - **BECAUSE:** The supervisor prompt currently compensates for missing runner-level controls.

- **GAP:** Workflow success is still inferred from multiple stage verdict files plus the supervisor report
  - **SYNOPSIS:** The supervision module still checks several workflow-stage verdict files and the workflow manifest instead of reading one explicit workflow-level completion artifact.
    - **BECAUSE:** Supervision will become simpler once the optimization workflow exposes one direct completion contract.
