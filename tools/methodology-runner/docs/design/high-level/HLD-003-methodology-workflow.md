# Design: Methodology Workflow

## 1. Requirements

This section defines the active methodology workflow that establishes a trusted baseline run, prepares planning artifacts, builds the standalone replay harness, and then prepares bounded step-lab optimization work.

- **REQUIREMENT: REQ-1** Establish one trusted baseline run
  - **SYNOPSIS:** The workflow MUST run the full methodology-runner sequence end to end with the best available model mix until it produces a usable baseline run record.
    - **BECAUSE:** Step-level optimization is meaningless unless every variant is compared against one accepted reference run.

- **REQUIREMENT: REQ-2** Isolate step-level optimization from the baseline
  - **SYNOPSIS:** The workflow MUST optimize individual methodology steps against the fixed inputs and evidence from the trusted baseline run rather than by rerunning the whole system for every variant.
    - **BECAUSE:** Full-system combinatorial testing is too expensive and hides which step caused an improvement or regression.

- **REQUIREMENT: REQ-3** Optimize one step at a time
  - **SYNOPSIS:** A step-lab SHOULD vary one methodology step at a time while holding the upstream baseline inputs fixed.
    - **BECAUSE:** Isolating one step gives causal attribution for quality, time, and cost changes.

- **REQUIREMENT: REQ-4** Preserve baseline evidence for later step labs
  - **SYNOPSIS:** The workflow MUST keep the baseline run's report artifacts, summaries, and accepted outputs available to later optimization prompts.
    - **BECAUSE:** Later step labs should reason from the same evidence set instead of reconstructing context from memory or chat history.

- **REQUIREMENT: REQ-5** Build standalone step-testing infrastructure before step optimization
  - **SYNOPSIS:** The workflow MUST design and implement infrastructure for running one methodology step in isolation against fixed baseline-derived inputs before it starts comparing per-step variants.
    - **BECAUSE:** Step-level optimization is not trustworthy until the system can replay one step with controlled inputs and capture comparable outputs, timing, and cost.

- **REQUIREMENT: REQ-6** Produce planning outputs before experimentation
  - **SYNOPSIS:** The workflow SHOULD first produce a current-focus note and an integration-readiness checklist before it launches step-lab experiments.
    - **BECAUSE:** The team needs explicit planning and acceptance criteria before running bounded step optimizations.

- **REQUIREMENT: REQ-7** Keep active workflow state campaign-local
  - **SYNOPSIS:** The workflow MUST keep its prompt-runner state under one workflow-local run directory and keep its baseline and variant methodology runs under the same exercise-local root.
    - **BECAUSE:** The execution architecture depends on one exercise-local root that contains both workflow control state and the methodology runs it manages.

## 2. Information Model

This section defines the main workflow concepts that sit above the generic runner.

- **ENTITY: ENTITY-1** `BaselineMethodologyRun`
  - **SYNOPSIS:** Full accepted methodology-runner execution used as the reference point for later experiments.
  - **FIELD:** `baseline_run_dir`
    - **SYNOPSIS:** `<exercise-dir>/runs/baseline/`
    - **BECAUSE:** Later step labs need one stable evidence source.
  - **FIELD:** `baseline_request`
    - **SYNOPSIS:** Raw request used for the baseline run.
    - **BECAUSE:** Step labs must optimize against the same underlying request.
  - **FIELD:** `baseline_summary`
    - **SYNOPSIS:** Compact summary of the accepted baseline run.
    - **BECAUSE:** Later prompts need a short evidence handoff as well as the full report.
  - **FIELD:** `baseline_timeline`
    - **SYNOPSIS:** Detailed timing, token, and cost report for the accepted baseline run.
    - **BECAUSE:** Step selection and cost reasoning depend on the baseline report.

- **ENTITY: ENTITY-2** `PlanningPreparationArtifacts`
  - **SYNOPSIS:** Run-local planning outputs produced after the baseline stage and before harness or step-lab work.
  - **FIELD:** `current_focus`
    - **SYNOPSIS:** Current-focus note for the optimization workflow.
    - **BECAUSE:** The workflow needs one short note that states the current stage, bottlenecks, and next experiments.
  - **FIELD:** `integration_readiness`
    - **SYNOPSIS:** Integration-readiness checklist for the next full methodology run.
    - **BECAUSE:** The workflow needs one readiness artifact that separates completed evidence from unresolved risks.

- **ENTITY: ENTITY-3** `MethodologyStepLab`
  - **SYNOPSIS:** One bounded optimization experiment for a single methodology step.
  - **FIELD:** `target_step`
    - **SYNOPSIS:** One methodology step chosen for isolated optimization.
    - **BECAUSE:** The lab needs a single causal target.
  - **FIELD:** `fixed_inputs`
    - **SYNOPSIS:** Baseline-derived artifacts and inputs held constant during the experiment.
    - **BECAUSE:** The lab only makes sense if the upstream context stays fixed.
  - **FIELD:** `variants`
    - **SYNOPSIS:** Small set of alternative models, prompts, or decompositions for the target step.
    - **BECAUSE:** The purpose of the lab is to compare a bounded set of alternatives.

- **ENTITY: ENTITY-4** `StandaloneStepHarness`
  - **SYNOPSIS:** Infrastructure that replays one methodology step in isolation using fixed baseline-derived inputs and captures comparable outputs and metrics.
  - **FIELD:** `target_step`
    - **SYNOPSIS:** Methodology step the harness is able to replay independently.
    - **BECAUSE:** The harness must know which phase or prompt is under isolated test.
  - **FIELD:** `fixed_input_bundle`
    - **SYNOPSIS:** Frozen set of baseline-derived files and state required to rerun the target step reproducibly.
    - **BECAUSE:** Fair comparison depends on feeding each variant the same upstream context.
  - **FIELD:** `captured_metrics`
    - **SYNOPSIS:** Comparable outputs such as verdict, artifact quality notes, wall time, token usage, and estimated cost.
    - **BECAUSE:** The harness exists to make per-step comparisons meaningful.

- **ENTITY: ENTITY-5** `StepOptimizationPlan`
  - **SYNOPSIS:** Planning artifact that selects target steps, variant dimensions, and comparison metrics.
  - **FIELD:** `target_steps`
    - **SYNOPSIS:** Steps chosen for optimization first.
    - **BECAUSE:** The workflow needs an explicit prioritization order.
  - **FIELD:** `evaluation_metrics`
    - **SYNOPSIS:** Quality, time, and cost criteria used to compare variants.
    - **BECAUSE:** Step-lab output must be judged against one consistent rubric.

- **ENTITY: ENTITY-6** `MethodologyWorkflowRun`
  - **SYNOPSIS:** One campaign-local prompt-runner workflow run that owns the baseline stage, planning stage, harness stage, and step-lab planning stage.
  - **FIELD:** `exercise_dir`
    - **SYNOPSIS:** `<exercise-dir>/`
    - **BECAUSE:** The workflow run belongs to one optimization exercise that also contains the baseline and variant methodology runs.
  - **FIELD:** `run_dir`
    - **SYNOPSIS:** `<exercise-dir>/prompt-runs/workflow/`
    - **BECAUSE:** The execution architecture keeps all workflow-local artifacts under one stable run directory.
  - **FIELD:** `raw_request`
    - **SYNOPSIS:** `<exercise-dir>/inputs/raw-request.md`
    - **BECAUSE:** Every stage in the workflow must stay tied to the copied campaign request.
  - **FIELD:** `baseline_run`
    - **SYNOPSIS:** The accepted baseline methodology run in `<exercise-dir>/runs/baseline/`.
    - **BECAUSE:** Later workflow stages depend on one trusted baseline reference.
  - **FIELD:** `planning_artifacts`
    - **SYNOPSIS:** Current-focus and integration-readiness outputs created by this workflow.
    - **BECAUSE:** The workflow produces planning artifacts before harness and step-lab work.
  - **FIELD:** `step_harness`
    - **SYNOPSIS:** Standalone step harness artifacts and replay outputs owned by this workflow.
    - **BECAUSE:** The harness is created and validated inside the same workflow run that owns the baseline.
  - **FIELD:** `step_lab_plan`
    - **SYNOPSIS:** Experiment matrix and reusable result template created by this workflow.
    - **BECAUSE:** The workflow culminates in a bounded optimization plan for later experiments.

## 3. Workflow Modules

This section defines the methodology-specific prompt modules above generic prompt-runner. The descriptive module name is primary; the filename is only an implementation reference.

- **PROMPT-MODULE: PMOD-1** `Methodology workflow module`
  - **SYNOPSIS:** Prompt-definition file that sequences the four active workflow stages: baseline run, planning preparation, standalone step harness, and step-lab planning.
  - **FIELD:** `current_file`
    - **SYNOPSIS:** `docs/prompts/PR-019-methodology-optimization-workflow.md`
    - **BECAUSE:** This is the current file that implements the methodology workflow module.
  - **SUPPORTS:** Establish one trusted baseline run
    - **BECAUSE:** The methodology workflow module owns the stage that creates the accepted reference run.
  - **SUPPORTS:** Produce planning outputs before experimentation
    - **BECAUSE:** The methodology workflow module owns the stage ordering that puts planning before isolated step experiments.
  - **SUPPORTS:** Build standalone step-testing infrastructure before step optimization
    - **BECAUSE:** The methodology workflow module owns the stage ordering that requires harness creation before step labs.
  - **SUPPORTS:** Optimize one step at a time
    - **BECAUSE:** The methodology workflow module owns the stage that produces the bounded step-lab plan.
  - **PROMPT-PAIR:** `Complete the trusted baseline run`
    - **SYNOPSIS:** Pair that runs the baseline run module and checks whether the workflow now has one accepted baseline run record.
    - **PROMPT:** `Generator`
      - **SYNOPSIS:** Launches or resumes the baseline run module and records the resulting workflow-level state.
      - **BECAUSE:** The methodology workflow needs one generator prompt that performs the baseline stage and surfaces its result at the workflow level.
    - **PROMPT:** `Judge`
      - **SYNOPSIS:** Decides whether the workflow now has the baseline artifacts required for planning preparation.
      - **BECAUSE:** The workflow must not move to planning until the baseline stage is complete enough to trust.
  - **PROMPT-PAIR:** `Complete the planning preparation outputs`
    - **SYNOPSIS:** Pair that runs the planning preparation module and checks whether the workflow now has the current-focus note and the integration-readiness checklist.
    - **PROMPT:** `Generator`
      - **SYNOPSIS:** Runs the planning preparation module against the trusted baseline evidence and records the resulting planning-artifact state.
      - **BECAUSE:** The methodology workflow needs one generator prompt that turns baseline evidence into bounded planning artifacts.
    - **PROMPT:** `Judge`
      - **SYNOPSIS:** Decides whether the planning artifacts are complete enough for harness construction.
      - **BECAUSE:** The workflow must not move to harness work until the planning artifacts exist and are usable.
  - **PROMPT-PAIR:** `Complete the standalone step harness outputs`
    - **SYNOPSIS:** Pair that runs the standalone step harness module and checks whether the workflow now has a usable isolated replay harness.
    - **PROMPT:** `Generator`
      - **SYNOPSIS:** Runs the harness module to choose a target step, define the replay path, and validate one replay.
      - **BECAUSE:** The methodology workflow needs one generator prompt that turns baseline evidence and planning artifacts into a concrete replay harness.
    - **PROMPT:** `Judge`
      - **SYNOPSIS:** Decides whether the harness artifacts and replay evidence are good enough for step-lab planning.
      - **BECAUSE:** The workflow must not start step-lab planning until isolated replay is available.
  - **PROMPT-PAIR:** `Complete the step-lab planning outputs`
    - **SYNOPSIS:** Pair that runs the step-lab planning module and checks whether the workflow now has the experiment matrix and result template.
    - **PROMPT:** `Generator`
      - **SYNOPSIS:** Uses the harness outputs and planning artifacts to produce the bounded experiment matrix and reusable result template.
      - **BECAUSE:** The methodology workflow needs one generator prompt that turns harness readiness into a concrete step-lab plan.
    - **PROMPT:** `Judge`
      - **SYNOPSIS:** Decides whether the experiment matrix and result template are ready for later isolated optimization work.
      - **BECAUSE:** The workflow should not claim step-lab readiness until both planning artifacts exist and are usable.

- **PROMPT-MODULE: PMOD-2** `Baseline run module`
  - **SYNOPSIS:** Prompt-definition file that runs the full methodology-runner sequence until it produces or repairs a usable baseline run.
  - **FIELD:** `current_file`
    - **SYNOPSIS:** `docs/prompts/PR-015-methodology-baseline-run.md`
    - **BECAUSE:** This is the current file that implements the baseline module.
  - **SUPPORTS:** Establish one trusted baseline run
    - **BECAUSE:** This module owns the full accepted reference run.
  - **DEPENDS-ON:** `docs/design/components/CD-003-methodology-run.md`
    - **BECAUSE:** The baseline module runs a generic methodology run whose detailed run structure lives in its own document.
  - **DEPENDS-ON:** `docs/design/high-level/HLD-001-methodology-prompt-optimization.md`
    - **BECAUSE:** The baseline module also assigns the `baseline` role inside the larger optimization exercise.

- **PROMPT-MODULE: PMOD-3** `Planning preparation module`
  - **SYNOPSIS:** Prompt-definition file that turns the baseline request, workflow design, and baseline evidence into a current-focus note and an integration-readiness checklist.
  - **FIELD:** `current_file`
    - **SYNOPSIS:** `docs/prompts/PR-016-methodology-planning-preparation.md`
    - **BECAUSE:** This is the current file that implements the planning-preparation module.
  - **SUPPORTS:** Produce planning outputs before experimentation
    - **BECAUSE:** This module prepares the planning artifacts that bound later experiments.
  - **PROMPT-PAIR:** `Write the current-focus note`
    - **SYNOPSIS:** Pair that uses runner-level required files plus the request, workflow design, summary, and timeline to write the current-focus note.
  - **PROMPT-PAIR:** `Write the integration-readiness checklist`
    - **SYNOPSIS:** Pair that uses runner-level required files plus the request, workflow design, baseline status, and current-focus note to write the reintegration-readiness checklist.

- **PROMPT-MODULE: PMOD-4** `Standalone step harness module`
  - **SYNOPSIS:** Prompt-definition file that designs and implements the infrastructure needed to replay one methodology step in isolation from a trusted baseline run.
  - **FIELD:** `current_file`
    - **SYNOPSIS:** `docs/prompts/PR-017-methodology-standalone-step-harness.md`
    - **BECAUSE:** This is the current file that implements the harness module.
  - **SUPPORTS:** Build standalone step-testing infrastructure before step optimization
    - **BECAUSE:** This module creates the harness that later step-lab variants depend on.
  - **DEPENDS-ON:** `docs/design/components/CD-004-methodology-standalone-step-harness.md`
    - **BECAUSE:** The harness module coordinates prompt logic and a concrete replay script, so its detailed design lives in its own document.

- **PROMPT-MODULE: PMOD-5** `Step-lab planning module`
  - **SYNOPSIS:** Prompt-definition file that uses the baseline evidence and planning outputs to choose which methodology steps should be optimized first and how they should be compared.
  - **FIELD:** `current_file`
    - **SYNOPSIS:** `docs/prompts/PR-018-methodology-step-lab-planning.md`
    - **BECAUSE:** This is the current file that implements the step-lab planning module.
  - **SUPPORTS:** Optimize one step at a time
    - **BECAUSE:** This module formalizes bounded step selection and comparison logic.
  - **DEPENDS-ON:** `Standalone step harness module`
    - **BECAUSE:** Per-step optimization should start only after one target step can be replayed and measured in isolation.
  - **PROMPT-PAIR:** `Confirm the first isolated optimization target`
    - **SYNOPSIS:** Pair that confirms the initial target phase and the first three variant dimensions worth testing.
  - **PROMPT-PAIR:** `Write the bounded step-lab experiment matrix`
    - **SYNOPSIS:** Pair that produces the bounded experiment matrix used for later isolated optimization work.
  - **PROMPT-PAIR:** `Write the step-lab result template`
    - **SYNOPSIS:** Pair that produces the reusable blank result template used to compare later variants.

## 4. Gaps

This section records the remaining workflow-design issues after the split architecture.

- **GAP:** The baseline stage does not yet surface top-level completion clearly enough
  - **SYNOPSIS:** The live run showed that nested methodology progress can advance inside the baseline run while the top-level workflow still fails to produce the baseline-stage completion artifacts that the supervision layer expects.
    - **BECAUSE:** The workflow architecture depends on top-level stage completion, not just nested methodology progress.

- **GAP:** The fixed-input bundle is still more implicit than explicit
  - **SYNOPSIS:** The standalone step harness concept is defined, but the current workflow still relies heavily on the preserved baseline run's worktree instead of a sharply materialized fixed-input bundle artifact.
    - **BECAUSE:** Per-step optimization is clearest when the frozen upstream inputs are explicit and inspectable.
