# CD-001 -- Backlog Runner

## 1. Purpose

- **GOAL: GOAL-1** Execute backlog items through methodology-runner with bounded parallelism.
  - **SYNOPSIS:** backlog-runner scans typed backlog folders, claims runnable items, launches methodology-runner workers, supervises worker state, merges finalized feature branches under one merge gate, and archives each item by terminal outcome.
  - **BECAUSE:** methodology-runner owns one change, while backlog-runner owns queue throughput and shared target-branch safety.

- **GOAL: GOAL-2** Keep queue behavior explicit and recoverable.
  - **SYNOPSIS:** Every claimed item has durable state, logs, worker results, merge results, and an archive decision.
  - **BECAUSE:** The runner must not infer completion from missing errors, missing processes, or partial output.

- **GOAL: GOAL-3** Preserve methodology-runner as the implementation engine.
  - **SYNOPSIS:** backlog-runner does not generate methodology phase artifacts, perform cross-reference validation, or run prompt-runner directly.
  - **BECAUSE:** Reusing methodology-runner keeps backlog-runner focused on orchestration instead of duplicating phase logic.

## 2. Scope

- **RULE: RULE-1** backlog-runner owns queue-level orchestration only.
  - **SYNOPSIS:** It scans, claims, schedules, launches, monitors, reaps, merges, archives, and reports.
  - **BECAUSE:** Phase authoring, phase validation, final verification, and feature-branch finalization belong to methodology-runner.

- **RULE: RULE-2** backlog-runner merges feature branches itself.
  - **SYNOPSIS:** It calls methodology-runner with --skip-target-merge and later performs one target-branch merge at a time under its own merge gate.
  - **BECAUSE:** The target branch is shared across all backlog items and must not be mutated by parallel workers.

- **RULE: RULE-3** backlog-runner does not process intake folders in the first implementation.
  - **SYNOPSIS:** docs/new-workitem, docs/new-workitem-processed, and docs/new-workitem-rejected remain visible but are not dispatched.
  - **BECAUSE:** Intake classification is a separate workflow and should not block the worker supervisor.

- **RULE: RULE-4** backlog-runner avoids hidden success states.
  - **SYNOPSIS:** Completed archive requires a successful worker result and a successful target merge result.
  - **BECAUSE:** Operators use completed archive as evidence that the item was delivered.

## 3. Runtime Entities

- **ENTITY: ENTITY-1** BacklogRoot
  - **SYNOPSIS:** Directory that contains backlog folders and backlog-runner state.
  - **FIELD:** active_folders
    - **SYNOPSIS:** docs/feature-backlog, docs/defect-backlog, docs/analysis-backlog, and docs/investigation-backlog when present.
    - **BECAUSE:** Folder location provides item type and queue priority.
  - **FIELD:** holding_folder
    - **SYNOPSIS:** docs/holding.
    - **BECAUSE:** Held items are visible to humans but blocked from automatic dispatch.
  - **FIELD:** completed_archive
    - **SYNOPSIS:** docs/completed-backlog grouped by item type.
    - **BECAUSE:** Completed items must leave active queues.
  - **FIELD:** failed_archive
    - **SYNOPSIS:** docs/failed-backlog grouped by item type.
    - **BECAUSE:** Failed items must remain visible without being redispatched as fresh work.

- **ENTITY: ENTITY-2** RunnerStateRoot
  - **SYNOPSIS:** backlog-runner-owned state directory under .backlog-runner.
  - **FIELD:** state_file
    - **SYNOPSIS:** .backlog-runner/state.json.
    - **BECAUSE:** Status and resume need durable queue state.
  - **FIELD:** supervisor_lock
    - **SYNOPSIS:** .backlog-runner/run.lock.
    - **BECAUSE:** One supervisor should own claims, worker reaping, merge decisions, and archives for a BacklogRoot.
  - **FIELD:** claims_dir
    - **SYNOPSIS:** .backlog-runner/claims.
    - **BECAUSE:** Atomic claim files prevent duplicate workers for the same item.
  - **FIELD:** results_dir
    - **SYNOPSIS:** .backlog-runner/results.
    - **BECAUSE:** Worker and merge outcomes must survive supervisor crashes.
  - **FIELD:** logs_dir
    - **SYNOPSIS:** .backlog-runner/logs.
    - **BECAUSE:** Operators need per-item stdout and stderr without opening worktrees.
  - **FIELD:** stop_file
    - **SYNOPSIS:** .backlog-runner/stop.
    - **BECAUSE:** A stop marker prevents new dispatch without killing active workers.

- **ENTITY: ENTITY-3** BacklogItem
  - **SYNOPSIS:** One markdown file discovered in an active backlog folder.
  - **FIELD:** item_type
    - **SYNOPSIS:** feature, defect, analysis, or investigation.
    - **BECAUSE:** Item type controls priority and archive path.
  - **FIELD:** slug
    - **SYNOPSIS:** Stable identifier derived from the filename stem.
    - **BECAUSE:** Claims, state records, branch names, worktree names, and logs need one shared key.
  - **FIELD:** source_path
    - **SYNOPSIS:** Path to the active markdown file.
    - **BECAUSE:** Worker launch and archive movement both need the original item.
  - **FIELD:** dependencies
    - **SYNOPSIS:** Optional list of backlog slugs parsed from the item.
    - **BECAUSE:** Items with unmet dependencies should not be dispatched.

- **ENTITY: ENTITY-4** BacklogItemRecord
  - **SYNOPSIS:** Durable state entry for one known backlog item.
  - **FIELD:** status
    - **SYNOPSIS:** queued, claimed, running, target_merge_pending, completed, failed, blocked, or abandoned.
    - **BECAUSE:** Status must distinguish active work, merge-ready work, and terminal outcomes.
  - **FIELD:** claim_id
    - **SYNOPSIS:** Identifier of the active claim file.
    - **BECAUSE:** Resume and cleanup need to connect state to claim ownership.
  - **FIELD:** change_id
    - **SYNOPSIS:** Stable identifier passed to methodology-runner.
    - **BECAUSE:** methodology-runner branch names and change records need the same durable name.
  - **FIELD:** branch_name
    - **SYNOPSIS:** Feature branch used for the methodology run.
    - **BECAUSE:** The final merge gate must know which branch to merge.
  - **FIELD:** workspace_path
    - **SYNOPSIS:** Application worktree path assigned to the item.
    - **BECAUSE:** Resume, status, worker recovery, and merge handoff loading need the worktree path.
  - **FIELD:** worker_result_path
    - **SYNOPSIS:** Result JSON written when the methodology worker reaches a terminal state.
    - **BECAUSE:** Reaping should read a durable result instead of trusting a process exit code alone.
  - **FIELD:** merge_result_path
    - **SYNOPSIS:** Result JSON written by backlog-runner after target merge attempt.
    - **BECAUSE:** Archive routing depends on explicit merge outcome.

- **ENTITY: ENTITY-5** WorkerResult
  - **SYNOPSIS:** Durable result from one methodology-runner subprocess.
  - **FIELD:** outcome
    - **SYNOPSIS:** target_merge_pending, failed, crashed, blocked, or incomplete.
    - **BECAUSE:** The supervisor needs one terminal classification for reaping.
  - **FIELD:** exit_code
    - **SYNOPSIS:** Process exit code from methodology-runner.
    - **BECAUSE:** Exit code is useful evidence but not enough for success.
  - **FIELD:** handoff_path
    - **SYNOPSIS:** Path to docs/changes/change-id/execution/target-merge-handoff.json in the feature worktree.
    - **BECAUSE:** A worker is merge-ready only when the handoff exists and matches expected branch metadata.
  - **FIELD:** error_summary
    - **SYNOPSIS:** Short failure text when the worker did not reach target_merge_pending.
    - **BECAUSE:** Status output should explain failed work without requiring log inspection.

- **ENTITY: ENTITY-6** MergeResult
  - **SYNOPSIS:** Durable backlog-runner result for one target-branch merge.
  - **FIELD:** outcome
    - **SYNOPSIS:** merged or merge_failed.
    - **BECAUSE:** Archive routing needs a separate merge outcome after worker completion.
  - **FIELD:** target_branch
    - **SYNOPSIS:** Branch that received or rejected the feature branch.
    - **BECAUSE:** Operators need to know where delivery was attempted.
  - **FIELD:** source_branch
    - **SYNOPSIS:** Finalized feature branch that was merged or failed.
    - **BECAUSE:** Retry and diagnosis need the exact source branch.
  - **FIELD:** source_commit
    - **SYNOPSIS:** Feature branch commit recorded in the methodology handoff.
    - **BECAUSE:** backlog-runner must merge the verified commit, not a later branch mutation.
  - **FIELD:** target_commit
    - **SYNOPSIS:** Target branch commit created by a successful merge.
    - **BECAUSE:** Completed archive should point to delivered history.
  - **FIELD:** failure_reason
    - **SYNOPSIS:** Human-readable reason for merge failure.
    - **BECAUSE:** Failed archive should preserve the action needed for repair.

## 4. Modules

- **MODULE: MODULE-1** cli.py
  - **SYNOPSIS:** Parses commands and delegates to the supervisor, status, resume, and stop services.
  - **CONTAINS:** run, once, status, resume, stop.
  - **BECAUSE:** Users need one stable command-line entrypoint.

- **MODULE: MODULE-2** models.py
  - **SYNOPSIS:** Defines serializable dataclasses and enums for item, claim, worker, merge, and supervisor state.
  - **CONTAINS:** BacklogItem, BacklogItemRecord, ClaimRecord, WorkerResult, MergeResult, BacklogState.
  - **BECAUSE:** CLI, scheduler, worker supervision, merge gate, and tests need one shared model layer.

- **MODULE: MODULE-3** paths.py
  - **SYNOPSIS:** Resolves BacklogRoot folders, RunnerStateRoot files, archive paths, log paths, result paths, and worktree paths.
  - **BECAUSE:** Path decisions should be deterministic and testable without duplicating string assembly.

- **MODULE: MODULE-4** scanner.py
  - **SYNOPSIS:** Discovers active backlog markdown files, parses slugs and dependencies, and reports invalid items.
  - **BECAUSE:** Scheduling must start from a truthful inventory of runnable and blocked work.

- **MODULE: MODULE-5** claims.py
  - **SYNOPSIS:** Creates, reads, validates, and releases atomic claim files.
  - **BECAUSE:** Duplicate claims are the highest-risk queue corruption bug.

- **MODULE: MODULE-6** scheduler.py
  - **SYNOPSIS:** Chooses which queued items to dispatch within worker limits and dependency constraints.
  - **BECAUSE:** Worker count, folder priority, existing claims, held items, and completed dependencies must be applied in one place.

- **MODULE: MODULE-7** worker.py
  - **SYNOPSIS:** Builds and runs one methodology-runner subprocess for a claimed item.
  - **USES:** --application-repo, --change-id, --branch-name, --target-branch, --base-branch, and --skip-target-merge.
  - **BECAUSE:** The worker boundary should be a normal methodology-runner command instead of library coupling.

- **MODULE: MODULE-8** supervisor.py
  - **SYNOPSIS:** Owns the main loop, process table, state persistence, stop behavior, reaping, and merge queue dispatch.
  - **BECAUSE:** One process must coordinate queue mutation and worker lifecycle decisions.

- **MODULE: MODULE-9** merge_gate.py
  - **SYNOPSIS:** Performs one target-branch merge at a time for items in target_merge_pending.
  - **READS:** target-merge-handoff.json from the finalized feature worktree.
  - **WRITES:** MergeResult under .backlog-runner/results.
  - **BECAUSE:** Shared target-branch mutation belongs in a serialized gate.

- **MODULE: MODULE-10** archive.py
  - **SYNOPSIS:** Moves backlog items to completed or failed archive folders after terminal outcomes.
  - **BECAUSE:** Archive movement is the operator-facing completion record and must be consistent with merge state.

- **MODULE: MODULE-11** git_ops.py
  - **SYNOPSIS:** Wraps git operations used by worktree validation, target branch cleanliness checks, squash merge, commit creation, and archive commits.
  - **BECAUSE:** Git failures need consistent error handling and test doubles.

- **MODULE: MODULE-12** status.py
  - **SYNOPSIS:** Produces human-readable and machine-readable status from state, claims, workers, results, invalid items, and stop state.
  - **BECAUSE:** Operators need a single inspection surface while long runs are active.

## 5. Commands

- **COMMAND: CMD-1** backlog-runner run
  - **SYNOPSIS:** Starts the long-running supervisor loop.
  - **READS:** Active backlog folders, state file, claims, stop file, and worker results.
  - **WRITES:** State file, claim files, logs, results, archive moves, and status summaries.
  - **USES:** max workers, backlog root, application repo, target branch, base branch, backend, model, and polling interval.
  - **BECAUSE:** Operators need one command to keep the queue moving until stopped.

- **COMMAND: CMD-2** backlog-runner once
  - **SYNOPSIS:** Runs one bounded supervisor cycle and exits after dispatched workers and eligible merges complete.
  - **BECAUSE:** CI and local smoke tests need bounded execution.

- **COMMAND: CMD-3** backlog-runner status
  - **SYNOPSIS:** Prints queued, blocked, claimed, running, target_merge_pending, completed, failed, invalid, and stopped states.
  - **BECAUSE:** Status must not require opening runner JSON by hand.

- **COMMAND: CMD-4** backlog-runner resume
  - **SYNOPSIS:** Reconciles claims, worker processes, worker results, merge results, and archive state after interruption.
  - **BECAUSE:** Long model-driven work can be interrupted by process exits, machine restarts, or quota failures.

- **COMMAND: CMD-5** backlog-runner stop
  - **SYNOPSIS:** Writes a stop marker that prevents new worker dispatch while allowing active workers and merge operations to reach a safe boundary.
  - **BECAUSE:** Killing active workers can leave partial methodology-runner state.

## 6. Supervisor Workflow

- **PROCESS: PROCESS-1** Startup reconciliation
  - **SYNOPSIS:** Acquire supervisor lock, load state, scan claim files, detect stale processes, read completed worker results, and rebuild runnable queues.
  - **BECAUSE:** Restarting the supervisor should preserve work instead of duplicating or abandoning it.

- **PROCESS: PROCESS-2** Queue scan
  - **SYNOPSIS:** Read active folders, classify items by folder, derive slug and item type, parse dependencies, and record invalid files.
  - **BECAUSE:** Scheduler decisions must be based on visible backlog files and explicit blocking reasons.

- **PROCESS: PROCESS-3** Claim creation
  - **SYNOPSIS:** Create one claim file with exclusive creation before dispatching a worker.
  - **BECAUSE:** Atomic creation prevents duplicate workers even if the supervisor restarts during dispatch.

- **PROCESS: PROCESS-4** Worker launch
  - **SYNOPSIS:** Start methodology-runner for one claimed item with isolated worktree options and --skip-target-merge.
  - **PRODUCES:** Per-item stdout log, stderr log, process id, and running state.
  - **BECAUSE:** Methodology execution can run in parallel only when every worker has its own feature worktree and skips the shared target merge.

- **PROCESS: PROCESS-5** Worker reaping
  - **SYNOPSIS:** Poll active workers, classify exited workers, validate target merge handoff, and move successful workers to target_merge_pending.
  - **BECAUSE:** A zero exit code without a valid handoff is not enough to merge or archive.

- **PROCESS: PROCESS-6** Final merge gate
  - **SYNOPSIS:** Select one target_merge_pending item, validate handoff, validate target branch cleanliness, squash merge source commit, include archive movement when BacklogRoot and ApplicationRepo share the target worktree, commit target branch, and write MergeResult.
  - **BECAUSE:** Target branch mutation and archive movement must be serialized to avoid racing with other completed feature branches.

- **PROCESS: PROCESS-7** Archive routing
  - **SYNOPSIS:** Move successfully merged items to completed archive and failed or incomplete items to failed archive.
  - **BECAUSE:** Active backlog folders should contain only work that can still be dispatched.

- **PROCESS: PROCESS-8** Stop handling
  - **SYNOPSIS:** When stop file exists, stop claiming new work, keep reaping active workers, finish an in-progress merge, and exit when no active worker remains.
  - **BECAUSE:** Graceful shutdown preserves recovery state.

## 7. Merge Gate Rules

- **RULE: RULE-5** Merge input must come from methodology-runner handoff.
  - **SYNOPSIS:** backlog-runner reads target-merge-handoff.json and verifies change id, source branch, target branch, source commit, and target_merge_pending status.
  - **BECAUSE:** The merge gate must merge the finalized and verified feature branch commit.

- **RULE: RULE-6** Target branch must be clean before merge.
  - **SYNOPSIS:** The target worktree must have no unstaged, staged, or untracked changes unless they are the planned archive movement after a successful squash merge.
  - **BECAUSE:** A dirty target branch can mix unrelated work into the delivery commit.

- **RULE: RULE-7** Merge success requires a target commit.
  - **SYNOPSIS:** backlog-runner writes merged only after the target branch commit exists and includes the expected source changes.
  - **BECAUSE:** A staged squash merge without a commit is not delivered work.

- **RULE: RULE-8** Merge failure leaves the feature branch intact.
  - **SYNOPSIS:** Conflicts, dirty target state, handoff mismatch, or commit failure mark merge_failed and preserve the finalized feature branch.
  - **BECAUSE:** Operators need to retry or repair the merge without rerunning methodology phases.

- **RULE: RULE-9** Archive movement follows merge outcome.
  - **SYNOPSIS:** Completed archive happens only after merged; failed archive happens after failed, crashed, abandoned, or merge_failed terminal states.
  - **BECAUSE:** Archive location is the durable queue status.

## 8. Same Repository Rule

- **REQUIREMENT: REQ-1** Backlog state must not dirty the application checkout used for worktree creation.
  - **SYNOPSIS:** .backlog-runner should be ignored or outside the application repo when BacklogRoot and ApplicationRepo are the same repository.
  - **BECAUSE:** methodology-runner refuses to create feature worktrees from a dirty application checkout.

- **REQUIREMENT: REQ-2** Archive moves in the target repo are serialized.
  - **SYNOPSIS:** If backlog folders are tracked in the target branch, backlog-runner performs archive movement inside the final merge gate after the squash merge is staged and before the target commit is created.
  - **BECAUSE:** The delivered commit can include both the code change and the queue-state move without racing another item.

- **REQUIREMENT: REQ-3** Separate BacklogRoot archives after merge result.
  - **SYNOPSIS:** If BacklogRoot is not the ApplicationRepo target worktree, backlog-runner records the target merge result first and then moves the backlog item in BacklogRoot.
  - **BECAUSE:** Separate repositories need separate consistency boundaries.

## 9. Failure Semantics

- **RULE: RULE-10** Missing worker result is not success.
  - **SYNOPSIS:** If a worker exits without a valid WorkerResult, classify the item as crashed or incomplete.
  - **BECAUSE:** Missing output is a recovery signal, not delivery evidence.

- **RULE: RULE-11** Invalid backlog item is not silently skipped.
  - **SYNOPSIS:** Invalid filename, unreadable file, or malformed dependency metadata appears in status output.
  - **BECAUSE:** Silent skips hide work from the operator.

- **RULE: RULE-12** Blocked item remains active.
  - **SYNOPSIS:** Items with unmet dependencies stay in their active folder and are marked blocked in state.
  - **BECAUSE:** A blocked item is not failed and should become runnable when dependencies complete.

- **RULE: RULE-13** Merge failure does not release delivery evidence.
  - **SYNOPSIS:** The claim, worker result, handoff, feature worktree, and logs remain available after merge_failed.
  - **BECAUSE:** The operator needs evidence to resolve the target branch conflict.

## 10. Verification Strategy

- **REQUIREMENT: REQ-4** Tests cover scanning and classification.
  - **SYNOPSIS:** Unit tests prove active, held, completed, failed, invalid, and blocked items are classified correctly.
  - **BECAUSE:** Scheduling correctness starts with accurate queue inventory.

- **REQUIREMENT: REQ-5** Tests cover atomic claims.
  - **SYNOPSIS:** Unit tests prove two claim attempts for the same slug cannot both succeed.
  - **BECAUSE:** Duplicate workers can corrupt branches and archives.

- **REQUIREMENT: REQ-6** Tests cover worker command construction.
  - **SYNOPSIS:** Unit tests prove methodology-runner is launched with --skip-target-merge, stable change id, explicit branch name, target branch, and base branch.
  - **BECAUSE:** Worker parallel safety depends on the exact methodology-runner boundary.

- **REQUIREMENT: REQ-7** Tests cover worker reaping.
  - **SYNOPSIS:** Unit tests prove zero exit with missing handoff is not success, and valid handoff becomes target_merge_pending.
  - **BECAUSE:** Merge-ready state must be based on explicit handoff evidence.

- **REQUIREMENT: REQ-8** Tests cover final merge gate.
  - **SYNOPSIS:** Integration tests with temporary git repositories prove one finalized feature branch is squash merged, committed, recorded, and archived.
  - **BECAUSE:** The merge gate is the shared-resource boundary.

- **REQUIREMENT: REQ-9** Tests cover merge failure.
  - **SYNOPSIS:** Integration tests prove conflicts produce merge_failed, leave the feature branch intact, and avoid completed archive.
  - **BECAUSE:** Failed delivery must not be mistaken for completed work.

- **REQUIREMENT: REQ-10** Tests cover resume.
  - **SYNOPSIS:** Tests prove claimed, running, target_merge_pending, merge_failed, completed, and failed states reconcile correctly after restart.
  - **BECAUSE:** The runner is expected to survive long-running interruptions.

## 11. Definition Of Good

- **RULE: RULE-14** Parallel methodology work is safe.
  - **SYNOPSIS:** Multiple workers can run methodology-runner at once without modifying the target branch.
  - **BECAUSE:** backlog-runner only gets throughput when shared branch mutation is deferred.

- **RULE: RULE-15** Target branch mutation is serialized.
  - **SYNOPSIS:** Only the final merge gate may update the target branch.
  - **BECAUSE:** Branch history should be deterministic and inspectable.

- **RULE: RULE-16** Archive state matches delivery state.
  - **SYNOPSIS:** Completed archive means target merge succeeded, and failed archive means worker or merge ended in a non-success terminal state.
  - **BECAUSE:** Operators rely on folders as the human-facing queue truth.

- **RULE: RULE-17** Recovery does not require guessing.
  - **SYNOPSIS:** State files, claim files, worker results, merge results, logs, and handoff files identify the next safe action.
  - **BECAUSE:** Long-running queue execution will be interrupted in normal local use.
