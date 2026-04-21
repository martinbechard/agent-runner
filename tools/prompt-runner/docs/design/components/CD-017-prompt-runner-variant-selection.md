# CD-017 - Prompt Runner Variant Selection

**GOAL: GOAL-1** `Selection fork that continues the parent run`
- **SYNOPSIS:** Prompt-runner SHALL support a fork mode where each variant runs its own generator and judge work, a selector judge chooses one variant, and the parent run then continues with the selected result.
  - **BECAUSE:** The current fork model runs each variant as a full child run with the remaining tail prompts appended, so there is no point where the system can compare multiple candidate results and then continue from only one of them.

**REQUIREMENT: REQ-1** `Backward-compatible fork semantics`
- **SYNOPSIS:** The existing `[VARIANTS]` behavior SHALL remain valid and unchanged, and selection-aware behavior SHALL require an explicit new marker.
  - **BECAUSE:** Existing prompt modules already depend on the current branch-and-stop fork semantics and must not silently change meaning.

**REQUIREMENT: REQ-2** `Parallel variant creation by default`
- **SYNOPSIS:** Selection forks SHALL launch variant workers in parallel by default and SHALL continue to honor the existing sequential fallback switch.
  - **BECAUSE:** The main cost of variant exploration is the independent generator and judge work inside each candidate branch, so the feature only has practical value if those branches can still run concurrently.

**ENTITY: ENTITY-1** `SelectionForkPoint`
- **SYNOPSIS:** One prompt-file item that owns multiple candidate variants plus one selector judge step.
- **FIELD:** `index`
  - **SYNOPSIS:** Positional prompt number in the parent workflow.
  - **BECAUSE:** The parent run still needs one stable prompt identity for status, summaries, resume, and reporting.
- **FIELD:** `title`
  - **SYNOPSIS:** Human-facing prompt title.
  - **BECAUSE:** Selection forks should appear in logs and reports the same way normal prompts do.
- **FIELD:** `variants`
  - **SYNOPSIS:** Ordered list of named variant prompt sequences.
  - **BECAUSE:** The runner must know each candidate branch it has to execute before selection.
- **FIELD:** `selector_prompt`
  - **SYNOPSIS:** Judge prompt that compares finished variants and chooses one or escalates.
  - **BECAUSE:** Selection is a separate decision step after variant generation, not part of any one variant.
- **FIELD:** `selector_retry_prompt`
  - **SYNOPSIS:** Optional correction-only retry text used when the selector output is malformed or references an invalid variant.
  - **BECAUSE:** Selector retries should fix selection-output defects without rerunning all variants.
- **FIELD:** `selection_include_files`
  - **SYNOPSIS:** Optional list of relative file paths whose per-variant contents should be embedded into the selector dossier.
  - **BECAUSE:** A selector that chooses among UI or code variants often needs the actual changed files, not only a short textual summary.

**ENTITY: ENTITY-2** `VariantCandidateResult`
- **SYNOPSIS:** Durable result record for one finished selection variant.
- **FIELD:** `variant_name`
  - **SYNOPSIS:** Stable authored variant identifier such as `A`, `B`, or `bold-layout`.
  - **BECAUSE:** The selector output must reference one deterministic name.
- **FIELD:** `exit_code`
  - **SYNOPSIS:** Child variant runner process exit status.
  - **BECAUSE:** The parent selector must know whether the variant finished cleanly.
- **FIELD:** `final_verdict`
  - **SYNOPSIS:** Final pass, revise, or escalate result from the variant-local judge loop.
  - **BECAUSE:** A variant that never reached pass should not be treated as a clean winner by default.
- **FIELD:** `workspace_root`
  - **SYNOPSIS:** Root of the isolated child worktree for that variant.
  - **BECAUSE:** The selected variant must later be promoted from one concrete workspace state.
- **FIELD:** `changed_paths`
  - **SYNOPSIS:** Deterministic list of project-relative files added, modified, or deleted by the variant compared with the pre-fork baseline.
  - **BECAUSE:** Promotion into the parent worktree must be driven by a reproducible change set rather than by ad hoc file copying.
- **FIELD:** `summary_path`
  - **SYNOPSIS:** Path to the child run summary for that variant.
  - **BECAUSE:** The selector prompt needs a compact description of what each variant claimed to produce.

**ENTITY: ENTITY-3** `SelectorDecision`
- **SYNOPSIS:** Parsed and validated outcome of the selector judge.
- **FIELD:** `verdict`
  - **SYNOPSIS:** Either `select` or `escalate`.
  - **BECAUSE:** The parent run must either continue with one chosen variant or stop at the fork.
- **FIELD:** `selected_variant`
  - **SYNOPSIS:** Authored variant name when `verdict` is `select`.
  - **BECAUSE:** Promotion requires one exact source workspace.
- **FIELD:** `rationale`
  - **SYNOPSIS:** Free-text explanation captured from the selector output.
  - **BECAUSE:** Humans need to understand why one variant won.

**PROCESS: PROCESS-1** `Prompt authoring contract`
- **SYNOPSIS:** Selection forks extend the current variant syntax with an explicit selector section while leaving old `[VARIANTS]` prompts unchanged.
- **CONTAINS:** `## Prompt N: Title [VARIANTS] [SELECT]`
  - **BECAUSE:** The new marker makes selection behavior explicit and preserves backward compatibility.
- **CONTAINS:** `### Variant <name>: <title>`
  - **BECAUSE:** Variant sections remain the authored branches the runner executes independently.
- **CONTAINS:** `#### Generation Prompt`
  - **BECAUSE:** Each variant still uses the normal generator step.
- **CONTAINS:** `#### Validation Prompt`
  - **BECAUSE:** Each variant still needs its own judge loop before selection.
- **CONTAINS:** `### Selection Include Files`
  - **BECAUSE:** The selector may need exact file contents from each variant without forcing the author to embed entire worktrees.
- **CONTAINS:** `### Selector Prompt`
  - **BECAUSE:** The selector is a separate judge call owned by the fork itself.
- **CONTAINS:** `### Selector Retry Prompt`
  - **BECAUSE:** Invalid selector outputs should be repairable without rerunning variant generation.

**PROCESS: PROCESS-2** `Selection fork execution`
- **SYNOPSIS:** The parent run pauses at the fork, executes each variant locally, selects one result, promotes it into the parent worktree, and then resumes the tail prompts.
- **CONTAINS:** `Capture parent baseline`
  - **SYNOPSIS:** Before launching variants, the runner records one baseline manifest for the parent worktree, excluding runner-owned paths and existing snapshot exclusions.
  - **BECAUSE:** Every variant starts from the same state, so promotion must compare each variant against a shared baseline.
- **CONTAINS:** `Create prompt-local staging area`
  - **SYNOPSIS:** The runner creates `.run-files/<module>/prompt-<NN>.selection/` as the canonical staging root for the selection step.
  - **BECAUSE:** The fork needs one durable place for variant metadata, selector inputs, and promotion records before any winner is applied.
- **CONTAINS:** `Launch variant workers`
  - **SYNOPSIS:** Each variant runs in its own isolated child worktree and child prompt-runner process, but the child synthetic prompt contains only that variant's prompt pairs and never the downstream tail prompts.
  - **BECAUSE:** The selection gate only works if all variants stop at the same comparison point instead of each running ahead into later workflow steps.
- **CONTAINS:** `Collect candidate results`
  - **SYNOPSIS:** After each child finishes, the parent records summary text, final verdict, exit status, and a deterministic changed-path manifest for that variant.
  - **BECAUSE:** The selector should reason over normalized candidate records rather than raw child process logs alone.
- **CONTAINS:** `Build selector dossier`
  - **SYNOPSIS:** The runner assembles a selector context bundle that includes per-variant metadata, summaries, changed paths, and any files listed in `Selection Include Files`.
  - **BECAUSE:** The selector needs comparable evidence across variants and should not have to rediscover that structure with shell commands.
- **CONTAINS:** `Run selector judge`
  - **SYNOPSIS:** The selector backend call runs only after all selected variants have completed.
  - **BECAUSE:** The selector is a comparison step over the finished candidate set, not a concurrent branch worker.
- **CONTAINS:** `Validate selector output`
  - **SYNOPSIS:** The runner deterministically parses the selector response and accepts only `VERDICT: select` plus a valid `SELECTED_VARIANT`, or `VERDICT: escalate`.
  - **BECAUSE:** The promotion step cannot proceed on ambiguous free-form text.
- **CONTAINS:** `Promote selected change set`
  - **SYNOPSIS:** When the selector chooses a winner, the runner applies the selected variant's add, modify, and delete operations into the parent worktree using the variant-to-baseline diff.
  - **BECAUSE:** The parent run should continue from the chosen workspace state without copying unrelated runner artifacts or sibling variant changes.
- **CONTAINS:** `Resume parent tail`
  - **SYNOPSIS:** After promotion succeeds, `run_pipeline` continues with the prompt items that follow the selection fork.
  - **BECAUSE:** The feature exists to rejoin the main workflow after selection.

**PROCESS: PROCESS-3** `Selector output contract`
- **SYNOPSIS:** The selector judge uses one minimal deterministic response shape that prompt-runner validates without another LLM.
- **CONTAINS:** `VERDICT: select`
  - **BECAUSE:** The happy path must name one winning variant.
- **CONTAINS:** `SELECTED_VARIANT: <name>`
  - **BECAUSE:** Promotion needs one exact authored variant identifier.
- **CONTAINS:** `RATIONALE: ...`
  - **BECAUSE:** Humans need a concise explanation in the durable selection record.
- **CONTAINS:** `VERDICT: escalate`
  - **BECAUSE:** The selector needs a safe failure path when no candidate is acceptable.

**RULE: RULE-1** `Selector may only choose a valid finished variant`
- **SYNOPSIS:** A `select` decision is valid only when the named variant exists in the completed candidate set and its child run finished successfully with a final judge verdict of `pass`.
  - **BECAUSE:** Continuing from a failed or nonexistent branch would make the downstream workflow state incoherent.

**RULE: RULE-2** `Variant workers stay isolated until selection`
- **SYNOPSIS:** No selection variant may write directly into the parent worktree before the selector decision has been validated.
  - **BECAUSE:** The parent run needs a clean pre-fork state so the selected change set can be promoted deterministically.

**RULE: RULE-3** `Selector input is runner-assembled, not shell-discovered`
- **SYNOPSIS:** The runner SHALL build a normalized selector dossier and inject it into the selector prompt instead of expecting the selector to inspect sibling variant folders manually.
  - **BECAUSE:** Selection quality and repeatability improve when each candidate is presented through the same deterministic evidence structure.

**RULE: RULE-4** `Promotion is diff-based and one-way`
- **SYNOPSIS:** Promotion copies only the selected variant's project-file additions and modifications into the parent worktree and applies the selected variant's deletions there; it never merges multiple variants together.
  - **BECAUSE:** The semantic contract of the selector is to choose one candidate branch, not to synthesize a hybrid output from several branches.

**RULE: RULE-5** `Selection staging remains durable after promotion`
- **SYNOPSIS:** The full `.selection/` staging tree SHALL remain on disk after the winner is promoted.
  - **BECAUSE:** Operators still need the losing variants, selector dossier, and decision record for forensics and review.

**RULE: RULE-6** `Selection resumes by stage, not by full rerun`
- **SYNOPSIS:** Resume logic SHALL treat variant execution, selector execution, and promotion as separate durable stages inside one selection fork.
  - **BECAUSE:** A long-running fork should not need to rerun completed variants just because the process stopped after candidate collection or during promotion.

**FILE: FILE-1** `Selection staging layout`
- **SYNOPSIS:** Each selection fork owns one prompt-local staging tree plus one canonical post-selection record.
- **PRODUCES:** `.run-files/<module>/prompt-<NN>.selection/`
- **CONTAINS:** `baseline-manifest.json`
  - **BECAUSE:** Promotion needs one deterministic pre-fork file inventory.
- **CONTAINS:** `variants/<variant-name>/result.json`
  - **BECAUSE:** Each candidate needs one normalized machine-readable record.
- **CONTAINS:** `variants/<variant-name>/changed-paths.txt`
  - **BECAUSE:** Human review and promotion both need the selected file list.
- **CONTAINS:** `variants/<variant-name>/workspace/`
  - **BECAUSE:** Each candidate branch needs its own isolated editable tree.
- **CONTAINS:** `selector/selector-prompt.md`
  - **BECAUSE:** The exact rendered selector input must be inspectable after the run.
- **CONTAINS:** `selector/selector-response.md`
  - **BECAUSE:** The selector output itself is part of the durable record.
- **CONTAINS:** `selector/decision.json`
  - **BECAUSE:** Promotion and resume need one parsed decision file.
- **CONTAINS:** `selection-summary.md`
  - **BECAUSE:** Humans need one concise overview of all candidate outcomes and the winning variant.
- **PRODUCES:** `.run-files/<module>/prompt-<NN>/`
- **CONTAINS:** `selected-variant.txt`
  - **BECAUSE:** The canonical prompt artifact should state which branch won.
- **CONTAINS:** `selected-change-manifest.json`
  - **BECAUSE:** Downstream debugging needs the exact promoted change set that entered the parent run.
- **CONTAINS:** `selector-decision.md`
  - **BECAUSE:** The canonical prompt artifact should preserve the human-readable selection rationale after promotion.

**PROCESS: PROCESS-4** `Resume and status model`
- **SYNOPSIS:** Selection forks need explicit stage tracking inside the parent run state.
- **CONTAINS:** `variant_execution`
  - **SYNOPSIS:** One stage where zero or more variant workers may still be pending.
  - **BECAUSE:** The parent must know whether it can skip directly to selector execution on resume.
- **CONTAINS:** `selector_execution`
  - **SYNOPSIS:** One stage where all variants are complete and the selector decision may still be missing or invalid.
  - **BECAUSE:** The selector is a separate durable boundary.
- **CONTAINS:** `promotion`
  - **SYNOPSIS:** One stage where a valid decision exists but the selected change set may not yet have been applied to the parent worktree.
  - **BECAUSE:** Promotion should be rerunnable without replaying model work.
- **CONTAINS:** `continued`
  - **SYNOPSIS:** Terminal stage for the selection fork once the winner is promoted and the parent pipeline has moved on.
  - **BECAUSE:** Resume and reporting need to know the selection gate is complete.

**MODIFICATION: MOD-1** `Parser model changes`
- **SYNOPSIS:** The parser SHALL add a new selection-fork item type or extend `ForkPoint` with explicit selection fields while preserving the current plain fork item for legacy `[VARIANTS]` prompts.
- **DEPENDS-ON:** `REQ-1`
  - **BECAUSE:** Backward compatibility requires the parser to distinguish old forks from selection-aware forks.

**MODIFICATION: MOD-2** `Runner orchestration changes`
- **SYNOPSIS:** `run_pipeline` SHALL replace the current branch-and-stop behavior for selection forks with a three-part sub-process: run variants, run selector, promote winner, then continue.
- **DEPENDS-ON:** `PROCESS-2`
  - **BECAUSE:** The new feature is primarily an execution-model change inside the main runner loop.

**MODIFICATION: MOD-3** `Child variant launch changes`
- **SYNOPSIS:** The synthetic prompt written for a selection variant SHALL contain only that variant's prompt pairs and SHALL omit `items_after`.
- **DEPENDS-ON:** `PROCESS-2`
  - **BECAUSE:** The child branch must stop at the selection point instead of running the tail workflow.

**MODIFICATION: MOD-4** `Selector dossier builder`
- **SYNOPSIS:** The runner SHALL add deterministic code that assembles selector metadata, changed-path manifests, and optional file payloads before the selector backend call.
- **DEPENDS-ON:** `RULE-3`
  - **BECAUSE:** The selector should compare normalized candidate evidence, not ad hoc shell-discovered state.

**MODIFICATION: MOD-5** `Promotion engine`
- **SYNOPSIS:** The runner SHALL add deterministic promotion logic that copies the selected variant's filesystem diff into the parent worktree and records the promoted manifest.
- **DEPENDS-ON:** `RULE-4`
  - **BECAUSE:** The selected branch must become the new parent state before downstream prompts run.

**MODIFICATION: MOD-6** `Status, summary, and reporting`
- **SYNOPSIS:** CLI status and run reports SHALL show the selection fork as one parent prompt with child variant results plus one selector decision.
- **DEPENDS-ON:** `PROCESS-4`
  - **BECAUSE:** Operators need to see whether a selection fork is still generating variants, waiting on the selector, or already promoted.

**PROCESS: PROCESS-5** `Verification scope`
- **SYNOPSIS:** The implementation should not ship without parser, runner, resume, and promotion coverage for the new selection fork shape.
- **CONTAINS:** `Parser accepts [VARIANTS] [SELECT] and selector sections`
  - **BECAUSE:** The new authored syntax is the public input contract.
- **CONTAINS:** `Legacy [VARIANTS] still uses current branch-and-stop behavior`
  - **BECAUSE:** Backward compatibility is a hard requirement.
- **CONTAINS:** `Selection child synthetic prompts exclude downstream tail prompts`
  - **BECAUSE:** That is the core behavioral change.
- **CONTAINS:** `Parallel selection variants run concurrently unless variant_sequential is true`
  - **BECAUSE:** Parallelism is one of the main user-facing benefits.
- **CONTAINS:** `Selector receives normalized dossier and can choose a passing variant`
  - **BECAUSE:** The selector step must be demonstrably functional.
- **CONTAINS:** `Invalid selector outputs retry without rerunning completed variants`
  - **BECAUSE:** Selector repair must be cheap and stage-local.
- **CONTAINS:** `Winner promotion updates the parent worktree and downstream prompt sees the promoted files`
  - **BECAUSE:** The parent continuation behavior is the product outcome the feature exists to enable.
- **CONTAINS:** `Resume after partial variant completion, post-selector interruption, and post-decision pre-promotion interruption`
  - **BECAUSE:** Long-running variant forks are not practical without stage-aware recovery.
