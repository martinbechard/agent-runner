# Review Checklist: STR-001 File Management Strategy

## Review Trace

- **TARGET:** `docs/strategies/STR-001-file-management-strategy.md`
- **INPUTS:**
  - User review scope: ensure methodology-runner can cover all artifacts needed by an application and support parallel agents in separate worktrees
  - User follow-up scope: ensure the example is concrete, assumption-driven, and maps relative paths to full paths
  - User design changes under review: permanent steady-state docs should be markdown outside `docs/changes/`, `docs/current/` should be removed, and the workflow should include an explicit steady-state integration step
  - User continuity change under review: later phases should inspect existing steady-state docs in the relevant folder and integrate changes into them rather than treating each run as greenfield
  - Latest user constraint: be very strict, avoid slop or vagueness, and document the latest changes in the review artifacts rather than editing more source files
  - `tools/methodology-runner/src/methodology_runner/phases.py`
  - `tools/methodology-runner/src/methodology_runner/orchestrator.py`
  - `tools/methodology-runner/src/methodology_runner/cli.py`
  - `tools/methodology-runner/src/methodology_runner/prompts/PR-023-ph001-feature-specification.md`
  - `tools/methodology-runner/src/methodology_runner/prompts/PR-024-ph002-architecture.md`
  - `tools/methodology-runner/src/methodology_runner/prompts/PR-026-ph003-solution-design.md`
  - `tools/methodology-runner/src/methodology_runner/prompts/PR-027-ph004-interface-contracts.md`
  - `tools/prompt-runner/src/prompt_runner/runner.py`
- **REVIEW-DATE:** `2026-04-20`
- **REVIEW-SCOPE:** Eighth-pass delta review focused on the latest `STR-001` revision, confirming that the cleanup-path fix remains correct and that no new ambiguity or implementation-misalignment was introduced elsewhere in the strategy
- **CHECKLISTS:**
  - `generic-structured-document-checklist.md`

## Delta Note

- The earlier implementation-alignment comments remain resolved.
- The earlier example-precision comments about fixed assumptions, explicit change IDs, and full-path expansion remain resolved.
- The pushed-back explanation about `.run-files/<phase-id>/prompt-file.md` remains accepted.
- The earlier Run 2 cleanup-path comment remains resolved.
- This pass rechecked the current `STR-001` revision and did not find any new material ambiguity or regression.

## Input Directive Trace

- **DIRECTIVE: DIR-1** Cover the material current artifact set used by methodology-runner and keep the parallel-worktree boundary accurate.
  - **STATUS:** `pass`
  - **EVIDENCE:** `STR-001-8` through `STR-001-11` still distinguish working docs, runner control state, runner execution artifacts, and separate-worktree parallelism. The strategy still surfaces the Phase 2 naming split and the `.methodology-runner` versus `.run-files` boundary.

- **DIRECTIVE: DIR-2** Distinguish current runner behavior from recommended post-run policy.
  - **STATUS:** `pass`
  - **EVIDENCE:** `STR-001-2`, `STR-001-4`, and `STR-001-13` clearly separate current implementation behavior from recommended retention and promotion policy.

- **DIRECTIVE: DIR-3** Make the example concrete and foolproof enough that readers do not invent different layouts or outcomes.
  - **STATUS:** `pass`
  - **EVIDENCE:** Run 2 step 6 now enumerates the exact removable temporary files and explicitly says not to remove the durable markdown docs under `docs/features/`, `docs/design/`, and `docs/contracts`, so the earlier cleanup ambiguity is gone.

- **DIRECTIVE: DIR-4** Make the permanent shared doc layer markdown outside `docs/changes/`, and remove `docs/current/` from the steady-state model.
  - **STATUS:** `pass`
  - **EVIDENCE:** `STR-001-13` and `STR-001-13A` now define the durable doc layer as markdown outside `docs/changes/`, state that those docs are current by default, and use subject-based paths such as `docs/features/console-display.md`, `docs/design/console-application.md`, and `docs/contracts/stdout-output.md`.

- **DIRECTIVE: DIR-5** Add an explicit integration step for folding a completed change into the shared steady-state docs.
  - **STATUS:** `pass`
  - **EVIDENCE:** `STR-001-14` now contains explicit step `8.`, and `STR-001-17` mirrors that step in both Run 1 and Run 2 with exact steady-state markdown paths.

- **DIRECTIVE: DIR-6** Ensure later runs use existing steady-state docs as continuity inputs, and make that claim compatible with the live prompt modules and runtime.
  - **STATUS:** `pass`
  - **EVIDENCE:** `STR-001-13B` says feature analysis should inspect `docs/features/*.md`, solution design should inspect `docs/design/*.md`, and interface-contract design should inspect `docs/contracts/*.md`. The live phase prompts now say the same in `PR-023`, `PR-026`, and `PR-027`, and `tools/prompt-runner/src/prompt_runner/runner.py:409-412` plus `:455-457` confirms the generator and judge can read files directly from the project root with tools, so the continuity instructions are operationally meaningful rather than decorative.

## A. Review Trace

- **CHECK: TRACE-1** Review target is identified.
  - **STATUS:** `pass`
  - **EVIDENCE:** The review trace names the exact target file `docs/strategies/STR-001-file-management-strategy.md`.

- **CHECK: TRACE-2** Review inputs are identified.
  - **STATUS:** `pass`
  - **EVIDENCE:** The review trace names the user directives, the implementation files that constrain the strategy, the continuity-related phase prompts, and the prompt-runner runtime behavior used to test the new prompt-contract claim.

- **CHECK: TRACE-3** Checklist set is identified.
  - **STATUS:** `pass`
  - **EVIDENCE:** The review trace names `generic-structured-document-checklist.md`.

## B. Input Coverage

- **CHECK: INPUT-1** All material input directives are traced.
  - **STATUS:** `pass`
  - **EVIDENCE:** The target applies the markdown steady-state doc model, explicit step-8 integration, continuity-input rules, and the remaining foolproof-example directive. The last ambiguous cleanup step now uses exact file paths instead of overlapping directory roots.

- **CHECK: INPUT-2** No material input directive is silently omitted.
  - **STATUS:** `pass`
  - **EVIDENCE:** The latest changes under review are all explicit in the target: the removal of `docs/current/`, the markdown steady-state layer, the continuity-input rule, and the explicit integration step all now appear in named sections.

- **CHECK: INPUT-3** No directive is contradicted by the target.
  - **STATUS:** `pass`
  - **EVIDENCE:** The strategy's continuity-preserving model and the Run 2 cleanup instructions are now aligned. Cleanup names only the temporary phase-working files and explicitly excludes the durable steady-state markdown docs that step 8 updates.

## C. Internal Logic

- **CHECK: LOGIC-1** Concepts are introduced before they are used.
  - **STATUS:** `pass`
  - **EVIDENCE:** The strategy introduces the steady-state markdown doc layer in `STR-001-13` and `STR-001-13A` before the example applies those paths in `STR-001-17`.

- **CHECK: LOGIC-2** The document follows a logical dependency order.
  - **STATUS:** `pass`
  - **EVIDENCE:** The document moves from current implementation behavior to recommended post-run policy and then to a fully instantiated example. The continuity rule in `STR-001-13B` also appears before the example relies on existing steady-state docs in Run 2.

- **CHECK: LOGIC-3** The document does not contain material contradictions.
  - **STATUS:** `pass`
  - **EVIDENCE:** `STR-001-13B`, `STR-001-14`, and `STR-001-17` now agree on the lifecycle: temporary YAML phase outputs are removed, while the durable markdown continuity docs remain in place and are updated in step 8.

- **CHECK: LOGIC-4** Requirements are not confused with solution choices.
  - **STATUS:** `pass`
  - **EVIDENCE:** The strategy continues to frame the markdown steady-state layer and step-8 integration as recommended policy, not as a false claim about what methodology-runner already materializes automatically.

- **CHECK: LOGIC-5** Goals are not confused with features.
  - **STATUS:** `n/a`
  - **EVIDENCE:** STR-001 is a workflow and file-management strategy, not a feature-goal breakdown.

## D. Justification Quality

- **CHECK: JUST-1** Important assertions have `BECAUSE` clauses.
  - **STATUS:** `pass`
  - **EVIDENCE:** The document does not use explicit `BECAUSE` syntax, but the important storage-policy assertions are justified directly in prose, especially in `STR-001-13`, which names the three failure modes the recommended split is intended to avoid.

- **CHECK: JUST-2** Each `BECAUSE` justifies its immediate parent.
  - **STATUS:** `n/a`
  - **EVIDENCE:** STR-001 does not use explicit `BECAUSE` clauses.

- **CHECK: JUST-3** Each `CHAIN-OF-THOUGHT` justifies the `BECAUSE` below it.
  - **STATUS:** `n/a`
  - **EVIDENCE:** STR-001 does not use explicit `CHAIN-OF-THOUGHT` clauses.

- **CHECK: JUST-4** Unsupported requirements or claims are flagged.
  - **STATUS:** `pass`
  - **EVIDENCE:** The strategy still flags the unresolved Phase 2 naming split, still distinguishes real `.run-files/<phase-id>/...` outputs from state-only prompt-file tracking, and the new continuity-input claim is now supported by the live prompt modules plus prompt-runner's file-inspection model.

## E. Terminology And Structure

- **CHECK: TERM-1** Established domain vocabulary is used where available.
  - **STATUS:** `pass`
  - **EVIDENCE:** The document uses `application worktree`, `change id`, `working artifact`, `change-specific kept artifact`, and `cumulative steady-state artifact` consistently.

- **CHECK: TERM-2** Repeated terms are stable and unambiguous.
  - **STATUS:** `pass`
  - **EVIDENCE:** The newer terminology around steady-state markdown docs, continuity inputs, and change-specific kept records is now stable and no longer mixes `docs/current/` language into the active model.

- **CHECK: TERM-3** Root-level IDs are present when structured review matters.
  - **STATUS:** `pass`
  - **EVIDENCE:** Section IDs such as `STR-001-13B`, `STR-001-14`, and `STR-001-17` remain stable review anchors.

- **CHECK: TERM-4** IDs are not overused on nested lines.
  - **STATUS:** `pass`
  - **EVIDENCE:** IDs remain at the section level and are not sprayed onto nested bullets or table rows.

## F. Document Hygiene

- **CHECK: HYGIENE-1** Section purpose lines are present.
  - **STATUS:** `pass`
  - **EVIDENCE:** The major sections continue to open with concise prose that says whether the section is describing current behavior, recommended policy, continuity rules, or the fully instantiated example.

- **CHECK: HYGIENE-2** Retired or superseded material is not mixed into active design without explanation.
  - **STATUS:** `pass`
  - **EVIDENCE:** The strategy now cleanly removes `docs/current/` from the active model and still isolates the unresolved Phase 2 naming split as an explicit caveat rather than silently mixing two path authorities.

- **CHECK: HYGIENE-3** Modifications are separated from clarifications.
  - **STATUS:** `n/a`
  - **EVIDENCE:** STR-001 does not use a modifications section.

- **CHECK: HYGIENE-4** The document stays within its intended scope.
  - **STATUS:** `pass`
  - **EVIDENCE:** The new markdown-doc and continuity-input sections remain directly about file management, retention, and repeated-run workflow, not a separate application design topic.
