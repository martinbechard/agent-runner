# Review Findings: STR-001 File Management Strategy Lifecycle Unification

## Scope

- **Target:** `docs/strategies/STR-001-file-management-strategy.md`
- **Inputs:**
  - User concern: the strategy now reads as confused because multiple list families overlap
  - User directive: add review comments indicating how the lists can be unified into a single process
  - `tools/methodology-runner/docs/M-002-phase-definitions.yaml`
  - `tools/methodology-runner/src/methodology_runner/phases.py`
- **Checklist:**
  - `RVW-007-str-001-file-management-strategy-lifecycle-unification-checklist.md`

## Delta Note

- Earlier review passes accepted the file-promotion split, continuity-input rules, and the concrete worked example.
- This pass reopens the strategy on one narrower issue: the document now has too many overlapping process-shaped lists, so readers can no longer tell which lifecycle is authoritative without synthesizing it themselves.

## Findings

### High

- **FND-1: `STR-001` lacks one authoritative lifecycle, so the reader has to merge several competing list families by hand.**
  - **Evidence:** `STR-001-13` defines a post-run split, `STR-001-13A` and `STR-001-13B` add stage-shaping rules, `STR-001-14` introduces a ten-step workflow, and `STR-001-17` repeats the workflow again as Run 1 and Run 2 git-operation lists.
  - **Impact:** This is the direct source of the current confusion. A reader can plausibly ask whether step 8 is a new methodology phase, whether "post-run" includes pre-run work, or whether the example supersedes the abstract workflow.
  - **Review comment:** Replace the overlapping list model with one canonical section such as `Single Change Lifecycle`. Make that section the only numbered end-to-end process in the document.
  - **Suggested unified process:**
    1. Prepare one change branch or worktree.
    2. Run the methodology sub-process in that worktree.
       Note: explicitly expand this step as `PH-000` through `PH-007`.
    3. Preserve change-specific records under `docs/changes/<change-id>/...`.
    4. Remove or archive runner-owned state and temporary phase-working files.
    5. Update steady-state subject docs outside `docs/changes/` using the continuity rules.
    6. Review the resulting application state and documentation set.
    7. Commit and merge.
  - **Restructure guidance:** Keep `STR-001-13A` and `STR-001-13B` as rule subsections under stage 5 instead of separate process-shaped sections. Keep `STR-001-14` only if it becomes this canonical lifecycle. Otherwise remove it as a second workflow.

### Medium

- **FND-2: The methodology phases are not explicitly nested inside the broader repo lifecycle.**
  - **Evidence:** `STR-001-14` step 2 says "Run methodology-runner" but does not expand that step into the eight methodology phases defined elsewhere by the tool. Later numbered steps continue after that point, which makes them easy to misread as additional methodology steps.
  - **Impact:** Readers can mistake repo-integration steps for extra methodology phases or confuse the methodology with the larger operational workflow around it.
  - **Review comment:** Under the canonical lifecycle's run stage, add one explicit expansion such as: `Methodology sub-process: PH-000 Requirements Inventory -> PH-001 Feature Specification -> PH-002 Architecture -> PH-003 Solution Design -> PH-004 Interface Contracts -> PH-005 Intelligent Simulations -> PH-006 Incremental Implementation -> PH-007 Verification Sweep`.

### Medium

- **FND-3: The worked example currently behaves like a second source of lifecycle truth instead of a trace of the main one.**
  - **Evidence:** `STR-001-17` restates the lifecycle as `Git Operations During Run 1` and `Git Operations During Run 2` with their own numbered steps, but those steps are not explicitly keyed back to `STR-001-14`.
  - **Impact:** The example increases confidence in the filesystem details, but it decreases confidence in the process model because the reader must compare and align two separate workflows manually.
  - **Review comment:** Keep the example, but convert it into a traced instantiation of the canonical lifecycle. Each run section should say which lifecycle step it is demonstrating, or the example should drop the duplicate numbering and focus only on concrete path instantiation and run-specific differences.
