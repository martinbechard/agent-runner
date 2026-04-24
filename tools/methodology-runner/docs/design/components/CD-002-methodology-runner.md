# CD-002 -- Methodology Runner

*Component design for the Python CLI that executes the checked-in methodology
prompt modules, validates each phase, and finalizes a change back into the
application repository.*

## 1. Purpose

- **GOAL: GOAL-1** Execute one methodology change from prepared application worktree to finalized integrated change.
  - **SYNOPSIS:** `methodology_runner` owns the end-to-end control flow for one change once the caller has chosen the application worktree, request file, backend, and phase scope.
  - **BECAUSE:** The system needs one orchestration component that sequences PH-000 through PH-007, preserves evidence, finalizes durable docs, and integrates the result back through git.

## 2. Scope

- **RULE: RULE-1** `methodology_runner` uses checked-in prompt modules instead of synthesizing phase prompts at runtime.
  - **SYNOPSIS:** Each `PhaseConfig` points to one canonical prompt module under `tools/methodology-runner/src/methodology_runner/prompts/`.
  - **BECAUSE:** The phase contract must stay reviewable, versioned, and testable in the repository.

- **RULE: RULE-2** `methodology_runner` owns orchestration, not free-form artifact authoring.
  - **SYNOPSIS:** It initializes the application worktree, invokes `prompt_runner`, performs cross-reference validation, persists state, manages retries, and automates lifecycle finalization.
  - **BECAUSE:** Artifact authoring belongs inside the checked-in prompt modules and their validators, while orchestration belongs in one Python control layer.

- **RULE: RULE-3** The active design must describe current code behavior even when longer-term strategy documents propose later migrations.
  - **SYNOPSIS:** This document describes the live implementation in `models.py`, `phases.py`, `orchestrator.py`, `cross_reference.py`, and `cli.py`.
  - **BECAUSE:** Readers need one accurate source of truth for how the runner behaves today.

- **RULE: RULE-4** Cross-phase review uses compatibility, not a ban on added specificity.
  - **SYNOPSIS:** Downstream phases may add practical implementation and verification constraints as the solution becomes concrete, but they must not contradict upstream approved requirements or exclude behavior that upstream artifacts explicitly require.
  - **BECAUSE:** The methodology has to converge on an executable solution, so downstream artifacts are expected to become more specific; the defect is contradiction or unsupported exclusion, not specificity by itself.

## 3. Definitions

- **ENTITY: ENTITY-1** `ApplicationWorktree`
  - **SYNOPSIS:** The concrete directory that `methodology_runner` edits during one run.
  - **BECAUSE:** All in-run artifact paths, git operations, prompt-runner calls, and finalization steps are rooted in one mutable application worktree.
  - **FIELD:** `root_path`
    - **SYNOPSIS:** The configured `workspace_dir`, which also becomes `prompt_runner`'s `run_dir`, `source_project_dir`, and `worktree_dir`.
    - **BECAUSE:** The current implementation runs directly in the application worktree rather than in a nested worktree directory.

- **ENTITY: ENTITY-2** `ProjectState`
  - **SYNOPSIS:** Persisted methodology control state stored at `.methodology-runner/state.json`.
  - **BECAUSE:** Resume, status, selected-phase execution, lifecycle progression, and phase recovery all depend on durable state between invocations.
  - **FIELD:** `phases`
    - **SYNOPSIS:** One `PhaseState` for each PH-000 through PH-007 phase.
    - **BECAUSE:** The runner must know which phase is pending, running, completed, failed, or escalated.
  - **FIELD:** `lifecycle_phases`
    - **SYNOPSIS:** One outer lifecycle state for LC-000 through LC-006.
    - **BECAUSE:** The runner now automates the post-methodology lifecycle and must track that work explicitly.
  - **FIELD:** `current_phase`
    - **SYNOPSIS:** The currently active PH-* phase when methodology execution is in progress.
    - **BECAUSE:** Status and resume need to expose the nested methodology position.
  - **FIELD:** `current_lifecycle_phase_id`
    - **SYNOPSIS:** The currently active LC-* lifecycle phase when the run is inside outer lifecycle automation.
    - **BECAUSE:** Resume and diagnostics must distinguish methodology execution from post-methodology finalization.
  - **FIELD:** `change_id`
    - **SYNOPSIS:** The change slug used for `docs/changes/<change-id>/...`.
    - **BECAUSE:** Preserved records and durable docs need a stable change namespace.

- **ENTITY: ENTITY-3** `PhaseRunDirectory`
  - **SYNOPSIS:** The methodology-owned per-phase artifact directory under `.run-files/<phase-id>/`.
  - **BECAUSE:** Cross-reference evidence and retry guidance must stay grouped by methodology phase.
  - **FIELD:** `cross_ref_result`
    - **SYNOPSIS:** `.run-files/<phase-id>/cross-ref-result.json`
    - **BECAUSE:** The phase verdict and traceability issues must be inspectable without reopening the model call.
  - **FIELD:** `retry_guidance`
    - **SYNOPSIS:** `.run-files/<phase-id>/retry-guidance-N.txt`
    - **BECAUSE:** Retry-specific runtime guidance must be preserved as run evidence.

- **ENTITY: ENTITY-4** `ChangeRecord`
  - **SYNOPSIS:** The preserved per-change record rooted at `docs/changes/<change-id>/`.
  - **BECAUSE:** The final integrated repository should retain change-specific reasoning and execution evidence after temporary in-run files are removed.
  - **FIELD:** `request_root`
    - **SYNOPSIS:** `docs/changes/<change-id>/request/`
    - **BECAUSE:** The copied input request must remain attached to the change.
  - **FIELD:** `analysis_root`
    - **SYNOPSIS:** `docs/changes/<change-id>/analysis/`
    - **BECAUSE:** The phase-working YAML artifacts are preserved here before temporary working paths are cleaned.
  - **FIELD:** `execution_root`
    - **SYNOPSIS:** `docs/changes/<change-id>/execution/`
    - **BECAUSE:** Implementation workflow artifacts and preserved runner state must survive final cleanup.
  - **FIELD:** `verification_root`
    - **SYNOPSIS:** `docs/changes/<change-id>/verification/`
    - **BECAUSE:** The final verification report belongs to the permanent change record.

## 4. Filesystem Model

- **FILE: FILE-1** `.methodology-runner/state.json`
  - **SYNOPSIS:** Durable control-state file for methodology and lifecycle progression.
  - **BECAUSE:** Resume, status, reset, and post-run preservation all read this file.

- **FILE: FILE-2** `.methodology-runner/run.lock`
  - **SYNOPSIS:** Exclusive workspace lock file guarded with `fcntl.flock`.
  - **BECAUSE:** Two runner instances must not mutate the same application worktree concurrently.

- **FILE: FILE-3** `.methodology-runner/process.log`
  - **SYNOPSIS:** Methodology-runner process log.
  - **BECAUSE:** The orchestrator needs one debug log outside the prompt-runner histories.

- **FILE: FILE-4** `.run-files/methodology-runner/summary.txt`
  - **SYNOPSIS:** Human-readable pipeline summary rewritten after each phase and at final completion.
  - **BECAUSE:** Users need one compact status artifact during and after execution.

- **FILE: FILE-5** `.run-files/<phase-id>/`
  - **SYNOPSIS:** Methodology-owned phase evidence directory for cross-reference results and retry guidance.
  - **BECAUSE:** Phase-level validation artifacts should not be mixed with prompt-runner's own histories.

- **FILE: FILE-6** `.run-files/<prompt-runner-run-id>/`
  - **SYNOPSIS:** Prompt-runner's own execution directory for the invoked prompt module.
  - **BECAUSE:** The nested runner persists histories, stdout logs, manifests, summaries, and other execution details under its own run id.

- **FILE: FILE-7** `docs/changes/<change-id>/`
  - **SYNOPSIS:** Permanent preserved change record written during LC-002 and LC-003.
  - **BECAUSE:** The final repository should keep change-specific reasoning and execution evidence after temporary working files are removed.

- **FILE: FILE-8** `docs/features/<project>-capabilities.md`
  - **SYNOPSIS:** Durable steady-state markdown derived from the preserved feature specification.
  - **BECAUSE:** Final integrated docs should describe current product state rather than temporary phase-working YAML.

- **FILE: FILE-9** `docs/design/<project>-design.md`
  - **SYNOPSIS:** Durable steady-state markdown derived from the preserved solution design.
  - **BECAUSE:** The final repo should keep a readable current-state design document after the temporary YAML is removed.

- **FILE: FILE-10** `docs/contracts/<project>-contracts.md`
  - **SYNOPSIS:** Durable steady-state markdown derived from the preserved interface contracts.
  - **BECAUSE:** The final repo should keep current contract documentation after temporary phase-working YAML is removed.

## 5. Module Responsibilities

- **MODULE: MODULE-1** `models.py`
  - **SYNOPSIS:** Defines the runner's durable enums and dataclasses.
  - **CONTAINS:** `PhaseStatus`, `EscalationPolicy`, `LifecyclePhaseDefinition`, `PhaseConfig`, `PhaseState`, `PhaseResult`, `ProjectState`
  - **BECAUSE:** The runner needs one serialization-safe model layer shared by CLI, orchestrator, and tests.

- **MODULE: MODULE-2** `phases.py`
  - **SYNOPSIS:** Declares the authoritative PH-000 through PH-007 phase registry.
  - **CONTAINS:** predecessor graph, input-source templates, output paths, expected output files, escalation defaults, and prompt module paths
  - **BECAUSE:** The runner needs one static registry that tells orchestration which artifact each phase reads, writes, and validates.

- **MODULE: MODULE-3** `orchestrator.py`
  - **SYNOPSIS:** Executes the methodology and outer lifecycle.
  - **USES:** workspace initialization, git helpers, prompt-runner invocation, cross-reference verification, summary writing, lifecycle automation, and final integration
  - **BECAUSE:** The full run behavior belongs in one orchestrator instead of being split across the CLI.

- **MODULE: MODULE-4** `cross_reference.py`
  - **SYNOPSIS:** Verifies per-phase and end-to-end consistency after prompt-runner produces artifacts.
  - **BECAUSE:** The methodology requires a second layer of traceability checks beyond the prompt module's internal judge and deterministic validator.
  - **RULE:** Compatibility-focused review
    - **SYNOPSIS:** Cross-reference should reject contradiction, fabricated evidence, and unsupported exclusion of upstream-required behavior, but it should not fail an artifact merely because downstream implementation or verification became more concrete.
    - **BECAUSE:** The methodology is supposed to narrow toward a practical solution over time while preserving upstream intent.

- **MODULE: MODULE-5** `cli.py`
  - **SYNOPSIS:** Exposes `run`, `resume`, `status`, and `reset`.
  - **BECAUSE:** Users need a stable command-line entrypoint for fresh runs, recovery, and inspection.

## 6. Prompt-Runner Integration

- **RULE: RULE-4** Each methodology phase invokes `prompt_runner` in-process through its library API.
  - **SYNOPSIS:** `orchestrator.py` parses the checked-in prompt module, builds a `RunConfig`, and calls `prompt_runner.runner.run_pipeline(...)`.
  - **BECAUSE:** The live integration uses the library path rather than shelling out to the CLI for normal phase execution.

- **RULE: RULE-5** The application worktree is passed to `prompt_runner` as the run directory and worktree.
  - **SYNOPSIS:** `run_dir=workspace`, `source_project_dir=workspace`, and `worktree_dir=workspace`.
  - **BECAUSE:** The current implementation edits the application worktree directly and relies on git worktree isolation at the repository level, not on a nested prompt-runner worktree.

- **RULE: RULE-6** Methodology phases may inject placeholder values and path mappings into prompt-runner.
  - **SYNOPSIS:** Examples include `raw_requirements_path`, `prompt_runner_command`, `methodology_backend`, and the `skills/` prefix mapping to bundled methodology-runner skills.
  - **BECAUSE:** Prompt modules need stable references to runtime-specific values without hardcoding repo-relative paths into the prompt body.

## 7. Step-By-Step Execution

- **PROCESS: PROCESS-1** Fresh run execution
  - **SYNOPSIS:** End-to-end control flow for `methodology-runner run <requirements-file>`.
  - **STEP 1:** Resolve the application worktree path.
    - **SYNOPSIS:** Use the explicit `--workspace` path when provided; otherwise derive one from the request filename.
    - **BECAUSE:** The runner needs one concrete application worktree before any file or git operation can begin.
  - **STEP 2:** Initialize the application worktree.
    - **SYNOPSIS:** Create required directories, copy the request to `docs/requirements/raw-requirements.md` when needed, and initialize git if the worktree is not already a git repository.
    - **BECAUSE:** The methodology phases assume the application worktree already contains the copied request and can record commits.
  - **STEP 3:** Acquire `.methodology-runner/run.lock`.
    - **BECAUSE:** The runner must prevent concurrent mutation of the same application worktree.
  - **STEP 4:** Load or create `ProjectState`.
    - **SYNOPSIS:** Fresh runs create default phase state; resume runs load the existing serialized state.
    - **BECAUSE:** The rest of the pipeline relies on persisted phase and lifecycle state.
  - **STEP 5:** Mark LC-000 complete and LC-001 in progress.
    - **BECAUSE:** The outer lifecycle must show that methodology execution has started.
  - **STEP 6:** Determine the execution scope.
    - **SYNOPSIS:** Choose all phases or the caller-selected subset after normalizing phase IDs.
    - **BECAUSE:** The runner supports both full execution and focused reruns.
  - **STEP 7:** Execute each selected phase in dependency order with `_run_single_phase(...)`.
    - **BECAUSE:** The methodology depends on strict predecessor ordering between PH-000 and PH-007.
  - **STEP 8:** Rewrite `.run-files/methodology-runner/summary.txt` after each phase.
    - **BECAUSE:** Users need a current summary while a long run is still active.
  - **STEP 9:** If all PH-* phases complete or are explicitly skipped, run end-to-end cross-reference verification.
    - **BECAUSE:** The methodology requires one final consistency check across the whole artifact chain.
  - **STEP 10:** Finalize LC-001 and, when the full methodology is complete, automate LC-002 through LC-006.
    - **BECAUSE:** A fully successful run should now finish as an integrated change instead of stopping at phase completion.

- **PROCESS: PROCESS-2** One phase execution
  - **SYNOPSIS:** `_run_single_phase(...)` owns the complete execution of one PH-* phase.
  - **STEP 1:** Create `.run-files/<phase-id>/`.
    - **BECAUSE:** Cross-reference results and retry guidance need one stable phase-owned directory.
  - **STEP 2:** Resolve the checked-in prompt module from `PhaseConfig.prompt_module_path`.
    - **BECAUSE:** The phase contract is stored in the repository, not generated on the fly.
  - **STEP 3:** Verify predecessor phase status and predecessor output existence.
    - **BECAUSE:** A completed status without the actual upstream artifact is not enough to start a downstream phase safely.
  - **STEP 4:** For PH-005, skip prompt-runner when architecture declares no simulation targets, write `simulations: []`, and mark the phase `skipped`.
    - **BECAUSE:** The runner can mechanically identify that no component simulations are needed while still providing the downstream manifest artifact.
  - **STEP 5:** Mark the phase `running`, persist state, and invoke `prompt_runner`.
    - **BECAUSE:** The runner must expose in-progress state before the nested model call starts.
  - **STEP 6:** If prompt-runner halts, map the configured escalation policy to `failed` or `escalated` and stop the phase.
    - **BECAUSE:** The runner distinguishes hard stop from human-review escalation, but both are visible in phase state.
  - **STEP 7:** If prompt-runner succeeds, mark the phase `prompt_runner_passed` and run phase cross-reference verification.
    - **BECAUSE:** Prompt success is necessary but not sufficient; the phase output must also satisfy methodology traceability checks.
  - **STEP 8:** On cross-reference failure, write `.run-files/<phase-id>/cross-ref-result.json` and optional `retry-guidance-N.txt`, then rerun the same prompt module with runtime retry guidance injected.
    - **BECAUSE:** Retries should revise the same canonical prompt contract rather than switch to a new generated prompt file.
  - **STEP 9:** When cross-reference passes, mark the phase `cross_ref_passed`, commit the worktree, then mark the phase `completed`.
    - **BECAUSE:** The methodology records one git checkpoint per successful phase before the next phase starts.

- **PROCESS: PROCESS-3** Resume execution
  - **SYNOPSIS:** `methodology-runner resume <workspace>` continues from the saved `ProjectState`.
  - **STEP 1:** Reload `ProjectState` from `.methodology-runner/state.json`.
  - **STEP 2:** If a selected phase is already `prompt_runner_passed`, rerun only cross-reference for that phase.
  - **STEP 3:** Skip phases that are already completed or explicitly skipped in the chosen execution scope.
  - **STEP 4:** If the methodology already finished and the current lifecycle phase is LC-002 through LC-006, resume lifecycle automation from that outer phase.
  - **BECAUSE:** Recovery must preserve completed work and resume from the narrowest safe boundary.

- **PROCESS: PROCESS-4** Post-methodology lifecycle automation
  - **SYNOPSIS:** `_automate_completed_lifecycle(...)` executes LC-002 through LC-006 when all PH-* phases are complete and no halt occurred.
  - **STEP 1:** `LC-002 Change-Record Preservation`
    - **SYNOPSIS:** Copy the in-run request, analysis YAML artifacts, implementation workflow/report artifacts, and verification report into `docs/changes/<change-id>/...`.
    - **BECAUSE:** The final repository should preserve the change-specific reasoning before temporary working paths are cleaned.
  - **STEP 2:** `LC-003 Runner-State Archival`
    - **SYNOPSIS:** Copy `.methodology-runner/state.json` and `.run-files/methodology-runner/summary.txt` into `docs/changes/<change-id>/execution/`.
    - **BECAUSE:** Final cleanup removes runner-owned roots, so durable copies must be made first.
  - **STEP 3:** `LC-004 Temporary-Artifact Cleanup`
    - **SYNOPSIS:** Delete the temporary phase-working files at their in-run canonical paths under `docs/requirements/`, `docs/features/`, `docs/architecture/`, `docs/design/`, `docs/simulations/`, `docs/implementation/`, and `docs/verification/`.
    - **BECAUSE:** Those YAML and working report paths are intermediate execution surfaces, not the final durable documentation layout.
  - **STEP 4:** `LC-005 Steady-State Integration`
    - **SYNOPSIS:** Generate current-state markdown docs under `docs/features/`, `docs/design/`, and `docs/contracts/` from the preserved analysis artifacts.
    - **BECAUSE:** The final integrated repository should keep durable readable docs instead of temporary phase-working YAML.
  - **STEP 5:** `LC-006 Final Review And History Integration`
    - **SYNOPSIS:** Remove runner-owned roots from the source worktree, write `docs/changes/<change-id>/execution/final-lifecycle-state.json`, commit the finalized change branch, and integrate it into the target branch worktree.
    - **BECAUSE:** A successful unattended run must end as a finalized repository change, not as a half-clean worktree waiting for manual promotion.

## 8. Git Behavior

- **RULE: RULE-7** Successful methodology phases attempt one commit per completed PH-* phase.
  - **SYNOPSIS:** `_git_commit(...)` stages all worktree changes and records a phase completion commit after cross-reference passes.
  - **BECAUSE:** Phase-level commits make phase progression inspectable and recoverable.

- **RULE: RULE-8** Final lifecycle integration commits and merges the finalized change.
  - **SYNOPSIS:** `LC-006` commits the finalized source branch state, finds a clean worktree for `main` or `master` when present, performs `git merge --squash <source-branch>`, and commits `Apply <change-id>` on the target branch.
  - **BECAUSE:** The intended unattended end state is a cleaned integrated change on the target branch, not only a completed feature worktree.

- **RULE: RULE-9** Selected-phase or incomplete runs do not perform lifecycle automation.
  - **SYNOPSIS:** LC-002 through LC-006 run only when all PH-* phases are complete and the pipeline did not halt early.
  - **BECAUSE:** Partial execution should not preserve, clean, or merge half-finished methodology outputs into the application repository.

## 9. CLI Behavior

- **COMMAND: CMD-1** `methodology-runner run`
  - **SYNOPSIS:** Starts a fresh methodology execution or reuses an explicit application worktree.
  - **BECAUSE:** Users need one entrypoint for a new change.

- **COMMAND: CMD-2** `methodology-runner resume`
  - **SYNOPSIS:** Continues a halted methodology or lifecycle run from persisted state.
  - **BECAUSE:** Long model-driven executions must be restartable.

- **COMMAND: CMD-3** `methodology-runner status`
  - **SYNOPSIS:** Reports phase state, lifecycle state, completion time, and pending manual phases.
  - **BECAUSE:** Users need inspectable state without opening JSON by hand.

- **COMMAND: CMD-4** `methodology-runner reset`
  - **SYNOPSIS:** Resets one selected phase and its downstream dependents back to `pending`, optionally deleting downstream outputs.
  - **BECAUSE:** Focused repair work sometimes requires rerunning one phase chain from a known clean point.

## 10. Obsolescence Boundary

- **RULE: RULE-10** The older nested `run_dir/worktree/.methodology-runner/runs/phase-N` model is obsolete for the live methodology-runner.
  - **SYNOPSIS:** The current implementation runs directly in the application worktree, stores control state in `.methodology-runner/`, stores methodology phase artifacts in `.run-files/<phase-id>/`, and stores prompt-runner histories in `.run-files/<prompt-runner-run-id>/`.
  - **BECAUSE:** The archived one-run model no longer describes the code paths that `methodology_runner` executes today.
