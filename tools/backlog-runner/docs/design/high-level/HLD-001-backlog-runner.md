# HLD-001 -- Backlog Runner

## 1. Purpose

- **GOAL: GOAL-1** Run multiple backlog items through methodology-runner without reimplementing methodology-runner.
  - **SYNOPSIS:** backlog-runner is an independent Python CLI under tools/backlog-runner that scans backlog folders, claims runnable work items, starts isolated methodology-runner executions, tracks their status, and archives each item by terminal outcome.
  - **BECAUSE:** methodology-runner already owns the phase methodology for one change, while backlog-runner should own queue throughput and worker supervision across many changes.

- **GOAL: GOAL-2** Preserve the useful backlog-folder model from the obsolete Claude app without using its implementation.
  - **SYNOPSIS:** The old app is only requirements evidence for folder semantics, claiming, completion archives, failed archives, and operator status. No old Python package code, LangGraph node code, Claude wrapper code, or dashboard code is reused.
  - **BECAUSE:** The old app is obsolete and malfunctioning, but its queue lifecycle exposed real operational requirements that the new runner still needs to satisfy.

## 2. Source Evidence

- **ENTITY: ENTITY-1** Implement skill evidence
  - **SYNOPSIS:** The obsolete implement skill defines YAML plan execution, task status files, parallel execution, dependency checks, and stop semaphores.
  - **SUPPORTS:** backlog-runner needs durable state, explicit terminal statuses, worker monitoring, dependency awareness, and graceful stop behavior.
  - **BECAUSE:** These are workflow requirements, not source-code implementation details.

- **ENTITY: ENTITY-2** Backlog folder evidence
  - **SYNOPSIS:** The obsolete app used active folders such as docs/feature-backlog and docs/defect-backlog, intake folders such as docs/new-workitem, manual-review folders such as docs/holding, archive folders such as docs/completed-backlog, and worker evidence folders for per-item logs and outputs.
  - **SUPPORTS:** backlog-runner should treat each folder as an explicit lifecycle state instead of inferring success from missing errors.
  - **BECAUSE:** Several documented failures in the old app came from silent fallbacks and ambiguous terminal states.

- **ENTITY: ENTITY-3** Current methodology-runner evidence
  - **SYNOPSIS:** methodology-runner owns one change execution, writes state under the application worktree, locks one workspace, and can create an application git worktree when given an application repository.
  - **SUPPORTS:** backlog-runner must give each item its own methodology workspace and must not run two methodology-runner instances against the same workspace.
  - **BECAUSE:** methodology-runner is intentionally single-change orchestration, not a queue supervisor.

## 3. Scope

- **RULE: RULE-1** backlog-runner owns only queue-level orchestration.
  - **SYNOPSIS:** It scans, claims, dispatches, monitors, resumes, archives, and reports backlog item runs.
  - **BECAUSE:** Phase artifact generation, cross-reference checks, implementation workflow execution, and final verification belong to methodology-runner and prompt-runner.

- **RULE: RULE-2** backlog-runner is a sibling tool, not a methodology-runner submodule.
  - **SYNOPSIS:** The package root is tools/backlog-runner, parallel to tools/prompt-runner and tools/methodology-runner.
  - **BECAUSE:** Queue supervision has a different lifecycle, CLI surface, state model, and test suite from a single methodology run.

- **RULE: RULE-3** The first implementation should not include Slack, RAG, dashboards, or LLM intake.
  - **SYNOPSIS:** The MVP reads already-authored markdown backlog items and can leave docs/new-workitem processing as a later component.
  - **BECAUSE:** The core risk is safe concurrent methodology execution; adding intake and UI before that is stable would reproduce the old app's broad failure surface.

## 4. Folder Model

- **ENTITY: ENTITY-4** BacklogRoot
  - **SYNOPSIS:** The repository or directory that contains user-facing backlog folders and backlog-runner state.
  - **FIELD:** active backlog folders
    - **SYNOPSIS:** docs/feature-backlog, docs/defect-backlog, and optional configured folders for analyses and investigations.
    - **BECAUSE:** The old system scanned typed active queues, and item type is safer when derived from the folder than from a filename prefix.
  - **FIELD:** manual holding folder
    - **SYNOPSIS:** docs/holding.
    - **BECAUSE:** Items here are visible to operators but not automatically dispatched.
  - **FIELD:** intake folders
    - **SYNOPSIS:** docs/new-workitem, docs/new-workitem-processed, and docs/new-workitem-rejected.
    - **BECAUSE:** They are useful future intake states, but MVP backlog-runner should not process them unless an intake component is explicitly added.
  - **FIELD:** completed archive folders
    - **SYNOPSIS:** docs/completed-backlog/features, docs/completed-backlog/defects, docs/completed-backlog/analyses, and docs/completed-backlog/investigations.
    - **BECAUSE:** Completed items must leave the active queue so scans do not repeatedly rediscover them.
  - **FIELD:** failed archive folders
    - **SYNOPSIS:** docs/failed-backlog/features, docs/failed-backlog/defects, docs/failed-backlog/analyses, and docs/failed-backlog/investigations.
    - **BECAUSE:** Failed or incomplete work must not be hidden inside the successful completion archive.

- **ENTITY: ENTITY-5** RunnerStateRoot
  - **SYNOPSIS:** The backlog-runner-owned state directory under .backlog-runner in the BacklogRoot.
  - **FIELD:** state file
    - **SYNOPSIS:** .backlog-runner/state.json.
    - **BECAUSE:** Resume and status commands need durable knowledge of claims, workers, workspaces, outcomes, and archive decisions.
  - **FIELD:** supervisor lock
    - **SYNOPSIS:** .backlog-runner/run.lock.
    - **BECAUSE:** Only one backlog-runner supervisor should claim and archive items for a BacklogRoot at a time.
  - **FIELD:** claims directory
    - **SYNOPSIS:** .backlog-runner/claims.
    - **BECAUSE:** Atomic claim records avoid duplicate workers while keeping active backlog files readable in their original folders.
  - **FIELD:** worker results directory
    - **SYNOPSIS:** .backlog-runner/results.
    - **BECAUSE:** Each methodology-runner subprocess needs a durable terminal result that the supervisor can reap after crashes or restarts.
  - **FIELD:** logs directory
    - **SYNOPSIS:** .backlog-runner/logs.
    - **BECAUSE:** Operators need per-item stdout and stderr without opening nested methodology-runner state first.

- **RULE: RULE-4** Claim records are runner state, not backlog items.
  - **SYNOPSIS:** backlog-runner should claim by exclusive creation of a claim record, not by moving the active markdown item into a claimed folder.
  - **BECAUSE:** methodology-runner requires a clean application repository before creating a worktree, and moving tracked backlog files at claim time can dirty that repository.

- **RULE: RULE-5** Archive moves are serialized and explicit.
  - **SYNOPSIS:** Moving an active item to completed or failed archive folders happens only after a terminal worker outcome and under the supervisor lock.
  - **BECAUSE:** Archive moves are user-visible history and must never happen because a worker returned an ambiguous or missing result.

## 5. Runtime Architecture

- **PROCESS: PROCESS-1** Supervisor loop
  - **SYNOPSIS:** Long-running backlog-runner command that owns scanning, claiming, worker spawning, reaping, archive routing, and budget or stop handling.
  - **READS:** BacklogRoot active backlog folders and .backlog-runner/state.json.
  - **WRITES:** claim records, worker result records, per-item logs, archive moves, and status summaries.
  - **LAUNCHES:** Methodology worker subprocesses.
  - **BECAUSE:** One parent process must have the global view needed to prevent duplicate claims and enforce concurrency limits.

- **PROCESS: PROCESS-2** Methodology worker subprocess
  - **SYNOPSIS:** One child process that runs methodology-runner for exactly one claimed backlog item.
  - **USES:** The claimed markdown item as the requirements file.
  - **USES:** One isolated application worktree for that item.
  - **PRODUCES:** Methodology-runner state, phase artifacts, prompt-runner histories, final verification evidence, and a worker result JSON.
  - **BECAUSE:** methodology-runner remains the unit of execution for one change.

- **PROCESS: PROCESS-3** Final merge gate
  - **SYNOPSIS:** A serialized phase that merges completed feature branches into the target branch and then archives the backlog item.
  - **DEPENDS-ON:** A successful methodology run that reached final verification without unresolved escalation.
  - **BECAUSE:** The target branch is a shared resource even when the methodology phases run in parallel worktrees.

- **RULE: RULE-6** Worker concurrency is bounded by configured worker count and available clean worktrees.
  - **SYNOPSIS:** max-workers controls how many methodology workers can run at once.
  - **BECAUSE:** Parallel LLM runs consume API quota, local CPU, git worktree space, and operator attention.

- **RULE: RULE-7** The same backlog item cannot have two active claims.
  - **SYNOPSIS:** A claim key is computed from item type and slug, and claim creation must be atomic.
  - **BECAUSE:** Duplicate methodology runs for the same item can produce conflicting branches and duplicate archive records.

- **RULE: RULE-8** The same application workspace cannot be assigned to two workers.
  - **SYNOPSIS:** Workspace paths are derived from a stable change id and checked against state before launch.
  - **BECAUSE:** methodology-runner already locks one workspace, and backlog-runner should avoid starting a doomed duplicate process.

## 6. Methodology-Runner Interface

- **COMMAND: CMD-1** Start one item
  - **SYNOPSIS:** backlog-runner starts methodology-runner with a requirements file, application repository, stable change id, branch name, target branch, backend, model, max-iteration settings, and --skip-target-merge.
  - **BECAUSE:** These inputs are enough for methodology-runner to create or reuse the item worktree and run the phase methodology.

- **REQUIREMENT: REQ-1** methodology-runner needs a target-merge skip option for true parallel backlog execution.
  - **SYNOPSIS:** backlog-runner can safely run PH-000 through PH-007 concurrently when methodology-runner is called with --skip-target-merge, and backlog-runner later performs the target-branch merge under its own merge lock.
  - **BECAUSE:** Current methodology-runner final lifecycle merges the completed change into the target branch inside the same run, and two workers doing that at the same time can race on the target branch.

- **RULE: RULE-9** Until target-merge skipping exists, backlog-runner must not claim full parallel safety.
  - **SYNOPSIS:** The implementation must either serialize whole methodology-runner processes or call methodology-runner with --skip-target-merge and merge feature branches itself under one backlog-runner merge gate.
  - **BECAUSE:** Running multiple full lifecycle processes unchanged can fail at target merge or leave unclear archive outcomes.

- **PROCESS: PROCESS-4** Deferred target merge flow
  - **SYNOPSIS:** A worker runs methodology phases and preserves final verification evidence, then stops before target-branch merge; backlog-runner later merges the finalized feature branch under a lock.
  - **BECAUSE:** This preserves phase parallelism while making the shared branch update deterministic.

## 7. Scheduling Rules

- **RULE: RULE-10** Scan priority favors unfinished claimed work before new work.
  - **SYNOPSIS:** On startup, backlog-runner first reconciles existing claims, then resumes workers with recoverable workspaces, then scans active backlog folders for new claims.
  - **BECAUSE:** Resuming existing work avoids an unbounded pileup of half-finished changes.

- **RULE: RULE-11** Folder priority is configurable, with defects before features by default.
  - **SYNOPSIS:** The default priority order is defects, features, investigations, analyses when those folders exist.
  - **BECAUSE:** Defects usually represent broken behavior and should be dispatched before feature expansion unless the operator configures otherwise.

- **RULE: RULE-12** Backlog dependencies block dispatch.
  - **SYNOPSIS:** If a backlog item declares a Dependencies section with backlog slugs, backlog-runner should dispatch it only when those slugs are archived as completed.
  - **BECAUSE:** The old implement skill surfaced dependency checks, and methodology-runner should not start from unmet functional prerequisites.

- **RULE: RULE-13** Invalid backlog filenames are warnings, not silent skips.
  - **SYNOPSIS:** Files in active backlog folders that cannot be converted into a stable slug are reported in status output and logs.
  - **BECAUSE:** The obsolete app had a documented failure mode where strict slug patterns silently ignored valid work.

- **RULE: RULE-14** Stop requests are graceful.
  - **SYNOPSIS:** backlog-runner accepts a stop command or stop file that prevents new worker dispatch while allowing active workers to finish or reach a resumable state.
  - **BECAUSE:** Killing child processes mid-methodology run can leave partial runner state that needs recovery logic.

## 8. Item State Model

- **ENTITY: ENTITY-6** BacklogItemRecord
  - **SYNOPSIS:** Durable state for one item known to backlog-runner.
  - **FIELD:** item_type
    - **SYNOPSIS:** feature, defect, analysis, or investigation.
    - **BECAUSE:** Archive routing and queue priority depend on type.
  - **FIELD:** slug
    - **SYNOPSIS:** Stable identifier derived from the markdown filename stem.
    - **BECAUSE:** Claims, workspaces, branch names, logs, and archive records need the same key.
  - **FIELD:** source_path
    - **SYNOPSIS:** Original active backlog markdown path.
    - **BECAUSE:** Archive routing and operator status need the source item.
  - **FIELD:** status
    - **SYNOPSIS:** queued, claimed, running, target_merge_pending, completed, failed, blocked, or abandoned.
    - **BECAUSE:** Operators need unambiguous state that does not collapse incomplete work into success.
  - **FIELD:** change_id
    - **SYNOPSIS:** Stable change identifier passed to methodology-runner.
    - **BECAUSE:** methodology-runner branch names, change records, and final merge handoff need one durable name.
  - **FIELD:** workspace_path
    - **SYNOPSIS:** Application worktree path assigned to this item.
    - **BECAUSE:** Resume, status, and cleanup need to find methodology-runner state.
  - **FIELD:** process_id
    - **SYNOPSIS:** Active child process id when the worker is running.
    - **BECAUSE:** Reaping and status commands need to distinguish running from stale state.
  - **FIELD:** outcome
    - **SYNOPSIS:** success, failed, incomplete, blocked, crashed, or merge_failed.
    - **BECAUSE:** Archive routing should be based on explicit terminal classification.

- **RULE: RULE-15** Missing worker results are not success.
  - **SYNOPSIS:** If a subprocess exits without a result file, the item is classified as crashed or resumable, never completed.
  - **BECAUSE:** The old app documented silent-success bugs caused by treating empty or unreadable state as done.

- **RULE: RULE-16** Failed and incomplete outcomes go to failed archives.
  - **SYNOPSIS:** Only a completed methodology run with successful target merge is archived under docs/completed-backlog.
  - **BECAUSE:** Operators use the completed archive as evidence that the item was delivered.

## 9. CLI Surface

- **COMMAND: CMD-2** backlog-runner run
  - **SYNOPSIS:** Starts the supervisor loop for a BacklogRoot and ApplicationRepo.
  - **USES:** options for backlog root, application repo, backend, model, max workers, polling interval, dry run, once, and budget cap.
  - **BECAUSE:** The operator needs one command to start continuous backlog processing.

- **COMMAND: CMD-3** backlog-runner once
  - **SYNOPSIS:** Claims and runs up to the configured worker count once, then exits after those workers reach terminal or resumable state.
  - **BECAUSE:** CI and smoke testing need bounded execution.

- **COMMAND: CMD-4** backlog-runner status
  - **SYNOPSIS:** Prints active claims, running workers, blocked items, recent outcomes, and invalid backlog files.
  - **BECAUSE:** Operators need visibility without opening every workspace.

- **COMMAND: CMD-5** backlog-runner resume
  - **SYNOPSIS:** Reconciles state after interruption and resumes claimed items whose methodology workspaces can continue.
  - **BECAUSE:** Long LLM runs can be interrupted by quota, crashes, or local restarts.

- **COMMAND: CMD-6** backlog-runner stop
  - **SYNOPSIS:** Requests graceful supervisor shutdown by writing a stop marker or signaling the running supervisor.
  - **BECAUSE:** Operators need a safe way to stop dispatch without corrupting worker state.

## 10. Verification Strategy

- **REQUIREMENT: REQ-2** Unit tests cover claim atomicity.
  - **SYNOPSIS:** Tests must prove two claim attempts for the same type and slug cannot both succeed.
  - **BECAUSE:** Duplicate claims are the highest-risk queue corruption bug.

- **REQUIREMENT: REQ-3** Unit tests cover scheduler filtering.
  - **SYNOPSIS:** Tests must prove completed, failed, held, blocked, invalid, and already-claimed items are not dispatched as fresh work.
  - **BECAUSE:** The runner must not rediscover inactive lifecycle states.

- **REQUIREMENT: REQ-4** Unit tests cover archive classification.
  - **SYNOPSIS:** Tests must prove success moves to completed archives and every non-success terminal outcome moves to failed archives.
  - **BECAUSE:** Archive directories are the operator's durable outcome record.

- **REQUIREMENT: REQ-5** Integration tests cover worker launch commands without running real LLM calls.
  - **SYNOPSIS:** Tests should use a fake methodology-runner executable that writes state, sleeps, exits with controlled codes, and emits result files.
  - **BECAUSE:** backlog-runner orchestration needs deterministic tests independent of model availability.

- **REQUIREMENT: REQ-6** Smoke tests cover real methodology-runner wiring on a tiny sample only when explicitly enabled.
  - **SYNOPSIS:** A slow optional test can run one sample backlog item through methodology-runner with max workers set to one.
  - **BECAUSE:** Full methodology execution is expensive and environment-sensitive, but the command boundary still needs periodic proof.

## 11. Open Design Decisions

- **GAP: GAP-1** The exact target-merge skip CLI on methodology-runner is not implemented yet.
  - **SYNOPSIS:** backlog-runner needs methodology-runner to support --skip-target-merge so the worker stops after verified feature-branch finalization and leaves target-branch merging to the supervisor.
  - **BECAUSE:** Without this split, true safe parallelism is blocked by methodology-runner's current in-process final merge.

- **GAP: GAP-2** Same-repository backlog and application operation needs a cleanliness rule.
  - **SYNOPSIS:** If BacklogRoot and ApplicationRepo are the same checkout, backlog-runner state must be ignored or outside git, and archive moves must be committed only at safe serialized points.
  - **BECAUSE:** methodology-runner refuses to create application worktrees from a dirty application checkout.

- **GAP: GAP-3** Intake processing is intentionally excluded from the MVP.
  - **SYNOPSIS:** docs/new-workitem can be supported later by a separate intake component that creates typed backlog markdown files.
  - **BECAUSE:** Intake classification requires its own quality gates and should not be coupled to the worker supervisor.
