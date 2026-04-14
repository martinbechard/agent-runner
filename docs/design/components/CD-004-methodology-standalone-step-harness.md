# Design: Methodology Standalone Step Harness

## 1. Requirements

This section defines what the standalone step harness must achieve before the workflow starts step-level optimization.

- **REQUIREMENT: REQ-1** Select one initial target step from baseline evidence
  - **SYNOPSIS:** The harness stage MUST choose one methodology phase to replay first and justify that choice from baseline evidence.
    - **BECAUSE:** Step-level optimization only has causal clarity when one target phase is fixed first.

- **REQUIREMENT: REQ-2** Define an explicit fixed input bundle
  - **SYNOPSIS:** The harness stage MUST describe the baseline-derived files and worktree state that every replay of the target phase will share.
    - **BECAUSE:** Variant comparison only means something if upstream inputs stay fixed.

- **REQUIREMENT: REQ-3** Use one deterministic replay path
  - **SYNOPSIS:** The harness stage MUST use one concrete script-driven replay path instead of inventing phase-replay logic in prompt prose.
    - **BECAUSE:** Step replay needs deterministic filesystem and CLI behavior.

- **REQUIREMENT: REQ-4** Validate the harness with one real replay
  - **SYNOPSIS:** The harness stage MUST run the replay path once against the trusted baseline run's worktree and record what happened.
    - **BECAUSE:** The workflow should not plan isolated step labs around an untested harness.

- **REQUIREMENT: REQ-5** Leave behind inspectable harness artifacts
  - **SYNOPSIS:** The harness stage MUST produce a target-step specification, a harness plan, and a harness validation note under one run-local harness root.
    - **BECAUSE:** Later planning and experimentation need durable harness artifacts rather than remembered intent.

## 2. Information Model

This section defines the run-local artifacts and concepts owned by the harness stage.

- **ENTITY: ENTITY-1** `TargetStepSpec`
  - **SYNOPSIS:** Run-local note that names the first target phase and the fixed input bundle for isolated replay.
  - **FIELD:** `path`
    - **SYNOPSIS:** `{{run_dir}}/step-harness/target-step.md`
    - **BECAUSE:** The workflow needs one durable artifact that states which phase is being optimized first.
  - **FIELD:** `target_phase`
    - **SYNOPSIS:** One methodology phase selected for the first isolated replay.
    - **BECAUSE:** The harness must focus on one phase at a time.
  - **FIELD:** `fixed_input_files`
    - **SYNOPSIS:** Explicit list of baseline-derived files every replay should treat as fixed.
    - **BECAUSE:** Variant comparison depends on a common upstream file set.
  - **FIELD:** `fixed_worktree_state`
    - **SYNOPSIS:** Baseline worktree conditions that must remain stable across replays.
    - **BECAUSE:** The replay must preserve the relevant upstream worktree state as well as the file list.
  - **FIELD:** `comparison_metrics`
    - **SYNOPSIS:** Quality, time, and cost signals the harness will preserve for later comparison.
    - **BECAUSE:** The harness exists to support comparable later experiments.

- **ENTITY: ENTITY-2** `HarnessPlan`
  - **SYNOPSIS:** Run-local note that explains how the harness script will replay the chosen target phase.
  - **FIELD:** `path`
    - **SYNOPSIS:** `{{run_dir}}/step-harness/harness-plan.md`
    - **BECAUSE:** The workflow needs a concrete replay plan that later prompts and operators can inspect.
  - **FIELD:** `replay_command`
    - **SYNOPSIS:** Concrete command that invokes the harness script for the chosen target phase.
    - **BECAUSE:** The replay path must be executable without guesswork.
  - **FIELD:** `expected_outputs`
    - **SYNOPSIS:** Concrete files or directories the replay should leave behind.
    - **BECAUSE:** The validation step needs known outputs to inspect.
  - **FIELD:** `comparison_procedure`
    - **SYNOPSIS:** Explanation of how replay outputs will be compared against the baseline.
    - **BECAUSE:** Later step labs need a stable comparison method.

- **ENTITY: ENTITY-3** `HarnessValidation`
  - **SYNOPSIS:** Run-local note that records what happened when the harness replay was run once for real.
  - **FIELD:** `path`
    - **SYNOPSIS:** `{{run_dir}}/step-harness/harness-validation.md`
    - **BECAUSE:** The workflow needs one durable validation note before step-lab planning starts.
  - **FIELD:** `replay_output_dir`
    - **SYNOPSIS:** Run-local directory used for the concrete harness replay.
    - **BECAUSE:** Later prompts need to inspect the replay location directly.
  - **FIELD:** `completion_status`
    - **SYNOPSIS:** Whether the replay completed successfully enough to trust the harness.
    - **BECAUSE:** Step-lab planning depends on whether isolated replay is real or still blocked.
  - **FIELD:** `remaining_gaps`
    - **SYNOPSIS:** Concrete unresolved harness issues after the replay attempt.
    - **BECAUSE:** Later work should continue from explicit harness gaps rather than vague suspicion.

- **ENTITY: ENTITY-4** `HarnessReplay`
  - **SYNOPSIS:** One concrete replay of a target methodology phase under the standalone harness.
  - **FIELD:** `baseline_run_dir`
    - **SYNOPSIS:** Run directory of the trusted baseline methodology run used for replay.
    - **BECAUSE:** The harness must know which baseline run supplies the evidence and worktree it will replay from.
  - **FIELD:** `baseline_worktree`
    - **SYNOPSIS:** Worktree cloned from the trusted baseline run.
    - **BECAUSE:** Replay starts from the trusted baseline run's worktree.
  - **FIELD:** `phase`
    - **SYNOPSIS:** Target methodology phase passed to the harness script.
    - **BECAUSE:** Reset and resume must agree on which phase is under test.
  - **FIELD:** `output_dir`
    - **SYNOPSIS:** `{{run_dir}}/step-harness/replay-<TARGET_PHASE>`
    - **BECAUSE:** Each replay needs one inspectable run-local directory.
  - **FIELD:** `metadata_file`
    - **SYNOPSIS:** `{{run_dir}}/step-harness/replay-<TARGET_PHASE>/harness-metadata.json`
    - **BECAUSE:** The replay needs a durable command and result record.

## 3. Prompt Module

This section defines the prompt module that chooses, plans, and validates the harness.

- **PROMPT-MODULE: PMOD-1** `Standalone step harness module`
  - **SYNOPSIS:** Prompt-definition file that chooses one initial target phase, defines the replay path, and validates the harness once.
  - **FIELD:** `current_file`
    - **SYNOPSIS:** `docs/prompts/PR-017-methodology-standalone-step-harness.md`
    - **BECAUSE:** This is the current file that implements the harness stage.
  - **SUPPORTS:** Select one initial target step from baseline evidence
    - **BECAUSE:** The module chooses the first replay target from the accepted baseline evidence.
  - **SUPPORTS:** Define an explicit fixed input bundle
    - **BECAUSE:** The module writes the target-step specification that states the fixed replay inputs.
  - **SUPPORTS:** Use one deterministic replay path
    - **BECAUSE:** The module routes replay through the repo harness script.
  - **SUPPORTS:** Validate the harness with one real replay
    - **BECAUSE:** The module runs one actual replay and records the result.
  - **PROMPT-PAIR:** `Choose the first target step and define the fixed input bundle`
    - **SYNOPSIS:** Pair whose generator chooses one target phase and writes the fixed input bundle, and whose judge checks whether that choice is explicit enough for later replay.
    - **PROMPT:** `Generator`
      - **SYNOPSIS:** Reads the planning artifacts and baseline evidence, then writes `target-step.md` with one target phase, fixed inputs, fixed worktree state, and comparison metrics.
      - **READS:** `{{run_dir}}/current-focus.md`
        - **BECAUSE:** Target-step selection should follow the current optimization focus rather than start from scratch.
      - **READS:** `{{run_dir}}/integration-readiness.md`
        - **BECAUSE:** The harness choice should respect the workflow's readiness constraints and risks.
      - **READS:** `{{baseline_run_dir}}/worktree/.methodology-runner/summary.txt`
        - **BECAUSE:** The target phase choice should be grounded in baseline evidence.
      - **READS:** `{{baseline_run_dir}}/worktree/timeline.html`
        - **BECAUSE:** Baseline timing and cost data help justify which phase to optimize first.
      - **WRITES:** `{{run_dir}}/step-harness/target-step.md`
        - **BECAUSE:** Later harness steps need one explicit target-step artifact.
    - **PROMPT:** `Judge`
      - **SYNOPSIS:** Checks that exactly one target phase was selected, that the choice is evidence-based, and that the fixed input bundle is explicit.
      - **READS:** `{{run_dir}}/step-harness/target-step.md`
        - **BECAUSE:** The judge evaluates the target-step specification directly.
      - **VALIDATES:** target phase choice and fixed input bundle
        - **BECAUSE:** Later replay steps must not proceed from a vague or unstable target definition.
  - **PROMPT-PAIR:** `Define the standalone harness execution path`
    - **SYNOPSIS:** Pair whose generator turns the target-step specification into a concrete replay plan and whose judge checks that the plan is actually executable.
    - **PROMPT:** `Generator`
      - **SYNOPSIS:** Reads `target-step.md` and the harness script, then writes `harness-plan.md` with the replay command, expected outputs, and comparison procedure.
      - **READS:** `{{run_dir}}/step-harness/target-step.md`
        - **BECAUSE:** The replay plan must be derived from the chosen target phase and fixed input bundle.
      - **READS:** `{{project_dir}}/scripts/run_methodology_step_harness.py`
        - **BECAUSE:** The plan must use the real harness implementation instead of inventing another path.
      - **WRITES:** `{{run_dir}}/step-harness/harness-plan.md`
        - **BECAUSE:** The validation step needs one explicit replay plan artifact.
    - **PROMPT:** `Judge`
      - **SYNOPSIS:** Checks that the replay command is concrete, the outputs are inspectable, and the plan uses the harness script rather than an invented workflow.
      - **READS:** `{{run_dir}}/step-harness/harness-plan.md`
        - **BECAUSE:** The judge validates the written replay plan directly.
      - **VALIDATES:** replay command and expected outputs
        - **BECAUSE:** Harness validation depends on one concrete plan.
  - **PROMPT-PAIR:** `Validate the harness once`
    - **SYNOPSIS:** Pair whose generator runs the harness once for real and whose judge checks whether the validation note matches the actual replay outputs.
    - **PROMPT:** `Generator`
      - **SYNOPSIS:** Extracts the target phase, invokes the harness script against the trusted baseline run's worktree, then writes `harness-validation.md`.
      - **READS:** `{{run_dir}}/step-harness/target-step.md`
        - **BECAUSE:** The generator must know which phase to replay.
      - **READS:** `{{run_dir}}/step-harness/harness-plan.md`
        - **BECAUSE:** The validation step should follow the planned replay path rather than improvise.
      - **INVOKES:** `python scripts/run_methodology_step_harness.py ...`
        - **BECAUSE:** Harness validation must exercise the real replay implementation.
      - **WRITES:** `{{run_dir}}/step-harness/harness-validation.md`
        - **BECAUSE:** Later step-lab planning depends on one explicit validation artifact.
    - **PROMPT:** `Judge`
      - **SYNOPSIS:** Checks that the validation note accurately states whether the replay completed and identifies concrete outputs and remaining gaps.
      - **READS:** `{{run_dir}}/step-harness/harness-validation.md`
        - **BECAUSE:** The judge must validate the harness result from the written note.
      - **VALIDATES:** replay outcome and remaining gaps
        - **BECAUSE:** Step-lab planning should rely only on accurately reported harness status.

## 4. Script Structure

This section defines the concrete harness implementation used by the prompt module.

- **SCRIPT: SCRIPT-1** `scripts/run_methodology_step_harness.py`
  - **SYNOPSIS:** Repo script that clones the trusted baseline run's worktree, resets one phase, reruns only that phase, and records the replay metadata.
  - **READS:** baseline run worktree path
    - **BECAUSE:** The replay starts by cloning the trusted baseline run's worktree.
  - **READS:** target phase
    - **BECAUSE:** Reset and resume both need the same phase identifier.
  - **WRITES:** replay output directory
    - **BECAUSE:** Each replay needs one inspectable directory holding the replay worktree.
  - **WRITES:** `harness-metadata.json`
    - **BECAUSE:** The script should leave behind the executed commands and their results.
  - **INVOKES:** `python -m methodology_runner reset ...`
    - **BECAUSE:** The replay must clear the target phase state before rerunning it.
  - **INVOKES:** `python -m methodology_runner resume ... --phases <phase>`
    - **BECAUSE:** The replay must rerun only the selected target phase rather than the whole methodology flow.

## 5. Gaps

This section records the remaining design and implementation gaps in the harness stage.

- **GAP:** The fixed input bundle is still described more sharply than it is materialized
  - **SYNOPSIS:** The prompt module writes an explicit fixed-input specification, but the current harness script still clones the full baseline run's worktree rather than materializing a narrower frozen input bundle artifact.
    - **BECAUSE:** The current implementation is workable, but the replay boundary is clearer when the frozen inputs are explicit on disk.

- **GAP:** Harness comparison is still mostly note-driven
  - **SYNOPSIS:** The harness script records commands and return codes, but later comparison still depends largely on markdown notes rather than one structured comparison artifact.
    - **BECAUSE:** Step-lab planning and later variant comparison would be easier if replay outputs and metrics were summarized in one machine-readable form.
