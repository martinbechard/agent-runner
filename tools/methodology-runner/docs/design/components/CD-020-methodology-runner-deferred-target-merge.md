# CD-020 -- Methodology Runner Deferred Target Merge

## 1. Purpose

- **GOAL: GOAL-1** Make methodology-runner safe for backlog-runner parallel execution.
  - **SYNOPSIS:** methodology-runner must allow many feature-branch worktrees to complete methodology execution in parallel while target-branch merging happens later in backlog-runner.
  - **BECAUSE:** A feature worktree is private to one change, but the target branch is shared across all backlog items.

- **GOAL: GOAL-2** Keep methodology-runner responsible for one change.
  - **SYNOPSIS:** methodology-runner still owns phase execution, validation, and feature-branch finalization for one change. backlog-runner owns queue scheduling and the serialized merge back to the target branch.
  - **BECAUSE:** Queue scheduling and artifact generation have different state models and should not be mixed in one runner.

- **GOAL: GOAL-3** Make finalization failures recoverable.
  - **SYNOPSIS:** methodology-runner must persist a truthful handoff state when it skips the target merge.
  - **BECAUSE:** backlog-runner needs a durable outcome before it can archive a backlog item as completed or failed.

## 2. Problem Statement

- **REQUIREMENT: REQ-1** Source-branch work can run concurrently.
  - **SYNOPSIS:** PH-000 through PH-007, final cross-reference verification, change-record preservation, steady-state document generation, cleanup, and source-branch commit can happen inside one isolated feature worktree.
  - **BECAUSE:** These operations mutate only the feature worktree assigned to one change.

- **REQUIREMENT: REQ-2** Target-branch merge must be serialized.
  - **SYNOPSIS:** Squash merge, target commit, conflict handling, and merge-result writing must run inside backlog-runner's final merge gate.
  - **BECAUSE:** Two feature branches cannot safely update the same target branch at the same time.

- **REQUIREMENT: REQ-3** Source-branch finalization must produce a merge handoff.
  - **SYNOPSIS:** The finalized feature branch must keep a tracked handoff record under docs/changes when methodology-runner skips the target merge.
  - **BECAUSE:** Cleanup removes runner-owned directories from the final source branch, so backlog-runner needs a tracked record that describes what to merge.

- **REQUIREMENT: REQ-4** The target branch must be explicit.
  - **SYNOPSIS:** methodology-runner must accept a target branch name and record the target branch and base commit in the change record.
  - **BECAUSE:** A feature branch created from the wrong starting point can pass local verification and still be invalid for the branch backlog-runner intends to merge into.

## 3. Definitions

- **ENTITY: ENTITY-1** MethodologyWorktree
  - **SYNOPSIS:** The feature-branch worktree assigned to one methodology-runner change.
  - **FIELD:** workspace_path
    - **SYNOPSIS:** Absolute path to the worktree used as methodology-runner workspace, prompt-runner run directory, source project directory, and editable worktree.
    - **BECAUSE:** All PH and source-finalization steps must operate on the same isolated directory.
  - **FIELD:** source_branch
    - **SYNOPSIS:** Git branch checked out in the worktree.
    - **BECAUSE:** Target merge uses this branch after it has been finalized.
  - **FIELD:** target_branch
    - **SYNOPSIS:** Git branch that receives the finalized change.
    - **BECAUSE:** Source and target branch names are needed for conflict checks, status output, and merge commands.
  - **FIELD:** base_commit
    - **SYNOPSIS:** Target branch commit used to create or validate the feature branch.
    - **BECAUSE:** Merge diagnostics need to know which target state the methodology work was based on.

- **ENTITY: ENTITY-2** TargetMergeHandoff
  - **SYNOPSIS:** Tracked JSON record that says a finalized feature branch is ready for backlog-runner to merge.
  - **FIELD:** change_id
    - **SYNOPSIS:** Stable change identifier used for docs/changes and branch naming.
    - **BECAUSE:** backlog-runner and methodology-runner need the same key across claim, worktree, branch, and archive state.
  - **FIELD:** source_branch
    - **SYNOPSIS:** Branch to merge into the target branch.
    - **BECAUSE:** backlog-runner must not infer the source branch from the current checkout alone.
  - **FIELD:** target_branch
    - **SYNOPSIS:** Branch that should receive the change.
    - **BECAUSE:** backlog-runner needs deterministic target routing.
  - **FIELD:** source_commit
    - **SYNOPSIS:** Finalized source branch commit.
    - **BECAUSE:** backlog-runner must merge the exact commit that passed methodology finalization.
  - **FIELD:** base_commit
    - **SYNOPSIS:** Target branch commit recorded when the source branch was prepared.
    - **BECAUSE:** Staleness warnings and conflict reports need a concrete comparison point.
  - **FIELD:** status
    - **SYNOPSIS:** target_merge_pending.
    - **BECAUSE:** backlog-runner must not infer archive status from process exit alone.

- **ENTITY: ENTITY-3** BacklogMergeResult
  - **SYNOPSIS:** Backlog-runner-owned result record written after a target merge attempt reaches a terminal outcome.
  - **FIELD:** status
    - **SYNOPSIS:** merged or merge_failed.
    - **BECAUSE:** Completed archives require proof of a successful target-branch update, while failed archives need an explicit failure reason.
  - **FIELD:** target_commit
    - **SYNOPSIS:** Commit created on the target branch for a successful merge.
    - **BECAUSE:** Operators need a durable pointer to the delivered change.
  - **FIELD:** failure_reason
    - **SYNOPSIS:** Human-readable reason for a failed merge.
    - **BECAUSE:** backlog-runner status should tell the operator what must be repaired.

## 4. Lifecycle Shape

- **MODIFICATION: MOD-1** Add a target-merge skip boundary to final lifecycle behavior.
  - **SYNOPSIS:** LC-006 finalizes and commits the feature branch, then either merges to the target branch or stops with target_merge_pending when the run uses --skip-target-merge.
  - **BECAUSE:** backlog-runner needs completed feature branches to queue for serialized merge instead of merging during worker execution.

- **PROCESS: PROCESS-1** Feature-branch finalization
  - **SYNOPSIS:** Run after all PH phases and final end-to-end verification pass.
  - **STEP:** Preserve change record artifacts under docs/changes.
    - **BECAUSE:** The target branch must retain request, analysis, execution, and verification evidence.
  - **STEP:** Archive runner state into docs/changes.
    - **BECAUSE:** Runner-owned directories are removed before the feature branch is committed.
  - **STEP:** Remove temporary phase-working artifacts and runner-owned roots.
    - **BECAUSE:** The finalized branch should contain product files and durable change records, not execution scratch space.
  - **STEP:** Write target merge handoff under docs/changes when --skip-target-merge is active.
    - **BECAUSE:** backlog-runner needs a tracked handoff record after hidden runner state has been removed.
  - **STEP:** Commit the finalized source branch.
    - **BECAUSE:** backlog-runner must merge a stable source commit.
  - **PRODUCES:** A feature branch with target_merge_pending status when --skip-target-merge is active.
  - **BECAUSE:** This state is safe for backlog-runner to queue while other feature branches continue running.

- **PROCESS: PROCESS-2** Built-in target merge
  - **SYNOPSIS:** Run only when --skip-target-merge is not set.
  - **STEP:** Find a clean target worktree.
    - **BECAUSE:** A dirty target worktree makes the merge result ambiguous.
  - **STEP:** Squash merge the finalized source commit into the target branch.
    - **BECAUSE:** Standalone methodology-runner usage should still be able to deliver one completed change.
  - **STEP:** Commit the target branch.
    - **BECAUSE:** The delivered change must have a stable target commit.
  - **PRODUCES:** A merged target branch.
  - **BECAUSE:** Existing single-change usage should not require backlog-runner.

- **PROCESS: PROCESS-3** Failure handling
  - **SYNOPSIS:** A failed built-in target merge records failure state without rewriting the completed source branch.
  - **STEP:** Abort an incomplete squash merge when possible.
    - **BECAUSE:** The target worktree should be left ready for the next controlled attempt or manual repair.
  - **STEP:** Persist merge_failed with the failing command and stderr summary when methodology-runner attempted the merge.
    - **BECAUSE:** Operators need enough evidence to repair conflicts without reopening model logs.
  - **STEP:** Keep the feature branch finalized and intact.
    - **BECAUSE:** Re-running all PH phases is unnecessary when only merge failed.

## 5. CLI Surface

- **COMMAND: CMD-1** methodology-runner run
  - **SYNOPSIS:** Executes methodology phases and feature-branch finalization.
  - **OPTION:** --skip-target-merge
    - **SYNOPSIS:** Finalize and commit the feature branch, write target_merge_pending handoff state, and do not merge the feature branch back to the target branch.
    - **BECAUSE:** backlog-runner needs methodology-runner workers to stop before mutating the shared target branch.
  - **OPTION:** target branch
    - **SYNOPSIS:** Explicit branch that receives the finalized change.
    - **BECAUSE:** Branch selection must be deterministic for backlog-runner scheduling.
  - **OPTION:** base branch
    - **SYNOPSIS:** Branch or commit used when creating the source branch.
    - **BECAUSE:** Worktree creation should not depend on whatever checkout happens to be active.
  - **PRODUCES:** A merged target branch when --skip-target-merge is absent, or target_merge_pending state when the option is present.
  - **BECAUSE:** The caller must know whether archive routing can happen immediately.

- **COMMAND: CMD-2** methodology-runner resume
  - **SYNOPSIS:** Continues phase execution, source finalization, or built-in target merge from persisted state.
  - **RULE:** If the run is target_merge_pending and the original run used --skip-target-merge, resume returns success without merging.
    - **BECAUSE:** backlog-runner owns the timing of serialized merge.
  - **RULE:** If the run failed during built-in target merge, resume can retry only when --skip-target-merge is absent.
    - **BECAUSE:** A target-branch operation should not happen by surprise during backlog-worker recovery.

- **COMMAND: CMD-3** methodology-runner status
  - **SYNOPSIS:** Reports PH phase status, feature-branch finalization status, target merge status, source branch, target branch, base commit, source commit, and target commit when available.
  - **BECAUSE:** backlog-runner status should be able to summarize one item without parsing git history.

## 6. State And Files

- **FILE: FILE-1** docs/changes/change-id/execution/target-merge-handoff.json
  - **SYNOPSIS:** Tracked source-branch handoff record written before the finalized feature branch commit.
  - **BECAUSE:** backlog-runner must know which finalized feature branch commit to merge after .methodology-runner and .run-files have been removed.

- **FILE: FILE-2** backlog-runner merge result
  - **SYNOPSIS:** Backlog-runner-owned result record for the serialized target merge.
  - **BECAUSE:** methodology-runner does not write the final merge result when --skip-target-merge is active.

- **FILE: FILE-3** .methodology-runner/state.json
  - **SYNOPSIS:** Runtime state used until source-branch finalization removes runner-owned roots.
  - **BECAUSE:** Phase execution and source finalization still need resumable hidden state before the source branch is finalized.

## 7. Git Rules

- **RULE: RULE-1** Source branch creation uses an explicit base.
  - **SYNOPSIS:** When methodology-runner creates a feature branch, it checks out from the requested base branch or base commit.
  - **BECAUSE:** The source branch must be grounded in the branch backlog-runner expects to merge into.

- **RULE: RULE-2** Target merge handoff validates the source commit.
  - **SYNOPSIS:** The source branch HEAD must match the source_commit recorded in the target merge handoff.
  - **BECAUSE:** A source branch that changed after final verification is not the reviewed change.

- **RULE: RULE-3** Built-in target merge does not mark success before the target commit exists.
  - **SYNOPSIS:** merged status is written only after the target branch commit is created.
  - **BECAUSE:** A process crash between merge and commit must not be reported as delivered.

- **RULE: RULE-4** Failed target merge does not delete source evidence.
  - **SYNOPSIS:** The finalized feature branch and target merge handoff remain available after conflicts or target failures.
  - **BECAUSE:** Operators need stable evidence to retry or manually resolve the merge.

## 8. Backlog-Runner Contract

- **REQUIREMENT: REQ-5** backlog-runner starts workers with --skip-target-merge.
  - **SYNOPSIS:** Each worker runs methodology-runner run with application repo, change id, branch name, target branch, base branch, and --skip-target-merge.
  - **BECAUSE:** Worker parallelism is safe only when workers do not merge into the shared target branch.

- **REQUIREMENT: REQ-6** backlog-runner treats target_merge_pending as worker success but item incomplete.
  - **SYNOPSIS:** A worker that reaches target_merge_pending is ready for the final merge gate but is not ready for completed archive.
  - **BECAUSE:** The backlog item is not delivered until the target branch has the merge commit.

- **REQUIREMENT: REQ-7** backlog-runner performs the merge under its supervisor merge gate.
  - **SYNOPSIS:** The supervisor merges one finalized feature branch at a time for items in target_merge_pending state.
  - **BECAUSE:** The supervisor owns queue-level ordering and archive routing.

- **REQUIREMENT: REQ-8** backlog-runner archives only after a successful merge result.
  - **SYNOPSIS:** Completed archive requires a successful backlog-runner merge result with a target commit.
  - **BECAUSE:** A finalized feature branch alone is not delivered work.

## 9. Implementation Tasks

- **TASK: TASK-1** Add --skip-target-merge and target branch fields to configuration.
  - **SYNOPSIS:** Extend the CLI parser, PipelineConfig, ProjectState, and status output.
  - **BECAUSE:** The runner must carry branch and mode decisions through every lifecycle step.

- **TASK: TASK-2** Make worktree creation target-branch aware.
  - **SYNOPSIS:** Create new source branches from the explicit base branch or base commit and record the base commit.
  - **BECAUSE:** Parallel workers need deterministic branch ancestry.

- **TASK: TASK-3** Split lifecycle automation.
  - **SYNOPSIS:** Keep feature-branch finalization separate from target merge, and make run skip the target merge when --skip-target-merge is present.
  - **BECAUSE:** backlog-runner needs to stop successful workers before shared branch mutation.

- **TASK: TASK-4** Make built-in target merge failure durable.
  - **SYNOPSIS:** Persist merge_failed with failure reason and command evidence without marking the run as delivered.
  - **BECAUSE:** A target merge failure can otherwise leave a halted result with cleaned runner state and no recoverable merge status.

- **TASK: TASK-5** Update methodology-runner documentation.
  - **SYNOPSIS:** Update the main component design and README to describe feature-branch finalization, --skip-target-merge, and the backlog-runner command contract.
  - **BECAUSE:** Users should not need to know older single-step lifecycle behavior to operate the runner.

## 10. Verification Strategy

- **REQUIREMENT: REQ-9** Tests cover source branch finalization without target merge.
  - **SYNOPSIS:** A full fake phase run with --skip-target-merge should leave the target branch unchanged and produce target merge handoff on the source branch.
  - **BECAUSE:** This is the core backlog-runner worker contract.

- **REQUIREMENT: REQ-10** Tests cover existing built-in merge success.
  - **SYNOPSIS:** A run without --skip-target-merge should merge the finalized source branch and create the target commit.
  - **BECAUSE:** backlog-runner completed archive depends on this exact terminal state.

- **REQUIREMENT: REQ-11** Tests cover concurrent source workers.
  - **SYNOPSIS:** Two source worktrees should reach target_merge_pending without modifying the target branch.
  - **BECAUSE:** This proves the safe parallel part of backlog-runner execution.

- **REQUIREMENT: REQ-12** Tests cover backlog-runner merge handoff contract.
  - **SYNOPSIS:** The handoff file should contain change id, source branch, target branch, source commit, base commit, and target_merge_pending status.
  - **BECAUSE:** backlog-runner needs this contract to perform the serialized merge itself.

- **REQUIREMENT: REQ-13** Tests cover built-in merge conflict failure recovery.
  - **SYNOPSIS:** A conflicting built-in squash merge should write merge_failed, leave the source branch intact, and avoid a false merged status.
  - **BECAUSE:** backlog-runner must route failed merge to a truthful terminal outcome.

- **REQUIREMENT: REQ-14** Tests cover status output.
  - **SYNOPSIS:** Status should expose target_merge_pending, merged, and merge_failed with branch and commit fields.
  - **BECAUSE:** Operators need one command for item-level diagnostics.

## 11. Definition Of Good

- **RULE: RULE-6** Parallel worker safety is demonstrable.
  - **SYNOPSIS:** Multiple methodology-runner workers can finish to target_merge_pending without touching the target branch.
  - **BECAUSE:** backlog-runner cannot claim safe parallelism without this property.

- **RULE: RULE-7** Target merge is retryable.
  - **SYNOPSIS:** Merge failure leaves enough tracked state to retry the merge without rerunning PH phases.
  - **BECAUSE:** Merge conflicts are target-branch delivery problems, not methodology execution problems.

- **RULE: RULE-8** Archive decisions are state-driven.
  - **SYNOPSIS:** backlog-runner can classify completed, pending, and failed items from target merge handoff and backlog-runner merge result records.
  - **BECAUSE:** Process exit codes and missing runner directories are not sufficient delivery evidence.

- **RULE: RULE-9** Standalone usage remains simple.
  - **SYNOPSIS:** The default run still supports a one-command methodology run for users who are not running backlog-runner.
  - **BECAUSE:** The deferred path should add safe orchestration without making single-change execution awkward.
