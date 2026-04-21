# Review Checklist: STR-001 File Management Strategy Lifecycle Unification

## Review Trace

- **TARGET:** `docs/strategies/STR-001-file-management-strategy.md`
- **INPUTS:**
  - User concern: the strategy currently reads as confused because multiple list families overlap and the lifecycle boundary is unclear
  - User directive: add review comments indicating how the lists can be unified into a single process
  - `tools/methodology-runner/docs/M-002-phase-definitions.yaml`
  - `tools/methodology-runner/src/methodology_runner/phases.py`
- **REVIEW-DATE:** `2026-04-20`
- **REVIEW-SCOPE:** Focused review of lifecycle clarity, list overlap, and whether `STR-001` presents one authoritative process that cleanly nests the methodology phases inside the larger worktree and git workflow
- **CHECKLISTS:**
  - `generic-structured-document-checklist.md`

## Delta Note

- Earlier review passes accepted the file-promotion model, continuity-input model, and example concreteness changes.
- This pass reopens `STR-001` on a narrower question: whether the document now presents too many overlapping lifecycle lists for a reader to reconstruct one authoritative process without guesswork.

## Input Directive Trace

- **DIRECTIVE: DIR-1** Keep the methodology phase pipeline distinct from the surrounding repository and git workflow.
  - **STATUS:** `fail`
  - **EVIDENCE:** `STR-001-2` says the document separates runner behavior from recommended after-run policy, but the actionable lifecycle is then spread across `STR-001-13`, `STR-001-13B`, `STR-001-14`, and `STR-001-17` without one explicit nesting model that says "the methodology phases live inside this broader workflow."

- **DIRECTIVE: DIR-2** Present one authoritative process rather than several partially overlapping lists.
  - **STATUS:** `fail`
  - **EVIDENCE:** The target currently uses at least four process-shaped list families: the post-run split in `STR-001-13`, the continuity rules in `STR-001-13B`, the ten-step workflow in `STR-001-14`, and the repeated Run 1 / Run 2 git-operation lists in `STR-001-17`.

- **DIRECTIVE: DIR-3** Make clear where the eight methodology phases sit relative to preparation, promotion, cleanup, and git finalization.
  - **STATUS:** `fail`
  - **EVIDENCE:** `STR-001-14` step 2 says "Run methodology-runner" but does not expand that step into `PH-000` through `PH-007`, even though the strategy later introduces additional numbered steps. That omission makes the outer lifecycle easy to misread as an extension of the methodology itself.

- **DIRECTIVE: DIR-4** Preserve the steady-state naming and continuity rules, but express them as stage-specific rules inside one lifecycle instead of as rival workflows.
  - **STATUS:** `fail`
  - **EVIDENCE:** `STR-001-13A` and `STR-001-13B` contain stage-shaping rules for durable-doc integration and later-run continuity, but they are not attached to one canonical lifecycle stage. A reader has to infer that these rules belong to the same process later described in `STR-001-14` step 8.

- **DIRECTIVE: DIR-5** Keep the worked example subordinate to the normative workflow rather than letting it become a second source of truth.
  - **STATUS:** `fail`
  - **EVIDENCE:** `STR-001-17` mirrors the lifecycle again as "Git Operations During Run 1" and "Git Operations During Run 2" without explicitly saying those steps are instantiations of `STR-001-14`. The example therefore competes with the abstract workflow instead of tracing it.

## A. Review Trace

- **CHECK: TRACE-1** Review target is identified.
  - **STATUS:** `pass`
  - **EVIDENCE:** The review trace names the exact target file `docs/strategies/STR-001-file-management-strategy.md`.

- **CHECK: TRACE-2** Review inputs are identified.
  - **STATUS:** `pass`
  - **EVIDENCE:** The review trace names the user concern, the requested review direction, and the methodology phase authorities that define the actual pipeline shape.

- **CHECK: TRACE-3** Checklist set is identified.
  - **STATUS:** `pass`
  - **EVIDENCE:** The review trace names `generic-structured-document-checklist.md`.

## B. Input Coverage

- **CHECK: INPUT-1** All material input directives are traced.
  - **STATUS:** `fail`
  - **EVIDENCE:** The target traces the file-retention and continuity rules, but it does not trace the bigger lifecycle question into one authoritative process model. The relevant rules remain scattered across separate sections.

- **CHECK: INPUT-2** No material input directive is silently omitted.
  - **STATUS:** `fail`
  - **EVIDENCE:** The need for one canonical lifecycle is not addressed directly anywhere in the target. The document implies that readers can synthesize one, but it never names which list is the authority.

- **CHECK: INPUT-3** No directive is contradicted by the target.
  - **STATUS:** `fail`
  - **EVIDENCE:** The current structure undermines the intended distinction between methodology and post-run handling because the file uses overlapping numbered lists whose boundaries are not explicitly nested or ranked.

## C. Internal Logic

- **CHECK: LOGIC-1** Concepts are introduced before they are used.
  - **STATUS:** `pass`
  - **EVIDENCE:** The document defines worktree, working artifact, change-specific kept artifact, cumulative steady-state artifact, runner control state, and runner execution artifact before the later sections rely on those terms.

- **CHECK: LOGIC-2** The document follows a logical dependency order.
  - **STATUS:** `fail`
  - **EVIDENCE:** The reader must manually merge `STR-001-13`, `STR-001-13A`, `STR-001-13B`, `STR-001-14`, and `STR-001-17` to reconstruct one lifecycle. The dependency order exists implicitly, but the document does not present it as one linear process.

- **CHECK: LOGIC-3** The document does not contain material contradictions.
  - **STATUS:** `fail`
  - **EVIDENCE:** `STR-001-13` frames one list as post-run promotion policy, while `STR-001-14` presents a broader ten-step lifecycle beginning before the run, and `STR-001-17` restates that lifecycle again per run. These are not factually incompatible, but they are structurally contradictory because each can be read as the main process.

- **CHECK: LOGIC-4** Requirements are not confused with solution choices.
  - **STATUS:** `pass`
  - **EVIDENCE:** The target still distinguishes current behavior from recommended policy and does not present the proposed durable doc model as if it were already implemented by the runner.

- **CHECK: LOGIC-5** Goals are not confused with features.
  - **STATUS:** `n/a`
  - **EVIDENCE:** STR-001 is a strategy and lifecycle document, not a feature breakdown.

## D. Justification Quality

- **CHECK: JUST-1** Important assertions have `BECAUSE` clauses.
  - **STATUS:** `fail`
  - **EVIDENCE:** The document justifies the retention split in `STR-001-13`, but it does not justify why the lifecycle itself is expressed through multiple overlapping list forms instead of one canonical process plus supporting derived views.

- **CHECK: JUST-2** Each `BECAUSE` justifies its immediate parent.
  - **STATUS:** `n/a`
  - **EVIDENCE:** STR-001 does not use explicit `BECAUSE` clauses.

- **CHECK: JUST-3** Each `CHAIN-OF-THOUGHT` justifies the `BECAUSE` below it.
  - **STATUS:** `n/a`
  - **EVIDENCE:** STR-001 does not use explicit `CHAIN-OF-THOUGHT` clauses.

- **CHECK: JUST-4** Unsupported requirements or claims are flagged.
  - **STATUS:** `fail`
  - **EVIDENCE:** The target behaves as though one lifecycle can be inferred from the assembled sections, but that claim is not made explicit and is not supported by one authoritative section that a reader can follow without synthesis work.

## E. Terminology And Structure

- **CHECK: TERM-1** Established domain vocabulary is used where available.
  - **STATUS:** `pass`
  - **EVIDENCE:** The document uses `application worktree`, `change id`, `working artifact`, `change-specific kept artifact`, `cumulative steady-state artifact`, and runner-state terms consistently.

- **CHECK: TERM-2** Repeated terms are stable and unambiguous.
  - **STATUS:** `fail`
  - **EVIDENCE:** The document uses `Recommended Post-Run Promotion Policy`, `Git Integration Model`, and `Git Operations During Run N` as overlapping process labels without explicitly ranking them as policy, canonical workflow, and example trace.

- **CHECK: TERM-3** Root-level IDs are present when structured review matters.
  - **STATUS:** `pass`
  - **EVIDENCE:** Stable anchors such as `STR-001-13`, `STR-001-13B`, `STR-001-14`, and `STR-001-17` support precise review references.

- **CHECK: TERM-4** IDs are not overused on nested lines.
  - **STATUS:** `pass`
  - **EVIDENCE:** IDs remain at the section level.

## F. Document Hygiene

- **CHECK: HYGIENE-1** Section purpose lines are present.
  - **STATUS:** `pass`
  - **EVIDENCE:** The major sections still open with enough prose to describe whether they cover current behavior, recommended policy, or the worked example.

- **CHECK: HYGIENE-2** Retired or superseded material is not mixed into active design without explanation.
  - **STATUS:** `pass`
  - **EVIDENCE:** The target continues to isolate the unresolved Phase 2 naming split and does not silently reintroduce the retired `docs/current/` model.

- **CHECK: HYGIENE-3** Modifications are separated from clarifications.
  - **STATUS:** `n/a`
  - **EVIDENCE:** STR-001 does not use a modifications section.

- **CHECK: HYGIENE-4** The document stays within its intended scope.
  - **STATUS:** `fail`
  - **EVIDENCE:** The target remains on the file-management topic, but it expresses the same lifecycle repeatedly at different abstraction levels instead of keeping one normative process and using the other sections only to define rules or examples. That weakens reviewability and makes the scope harder to follow.
