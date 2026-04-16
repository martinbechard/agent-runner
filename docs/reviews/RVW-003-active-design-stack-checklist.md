# Review Checklist: Active Methodology Design Stack

## Review Trace

- **TARGET:** Active design authorities under `docs/plans/`:
  - `README.md`
  - `.prompt-runner/docs/design/components/CD-006-prompt-runner-core.md`
  - `CD-003-methodology-run.md`
  - `HLD-001-methodology-prompt-optimization.md`
  - `CD-004-methodology-standalone-step-harness.md`
  - `HLD-003-methodology-workflow.md`
  - `CD-005-methodology-supervision.md`
  - `HLD-002-methodology-execution-architecture.md`
- **INPUTS:**
  - `/Users/martinbechard/dev/agent-assets/skills/structured-design/SKILL.md`
  - `docs/design/README.md`
  - Cross-document consistency across the active design authorities listed above
- **REVIEW-DATE:** `2026-04-13`
- **REVIEW-SCOPE:** Active design authorities only, not implementation plans or execution logs
- **CHECKLISTS:**
  - `generic-structured-document-checklist.md`

## A. Review Trace

- **CHECK: TRACE-1** Review target is identified.
  - **STATUS:** `pass`
  - **EVIDENCE:** The target list names the exact active design authority files under `docs/plans/`.

- **CHECK: TRACE-2** Review inputs are identified.
  - **STATUS:** `pass`
  - **EVIDENCE:** The review names the governing structured-design skill, the relationship map in `docs/design/README.md`, and the active design stack itself as the cross-document input set.

- **CHECK: TRACE-3** Checklist set is identified.
  - **STATUS:** `pass`
  - **EVIDENCE:** The review trace names `generic-structured-document-checklist.md`.

## B. Input Coverage

- **CHECK: INPUT-1** All material input directives are traced.
  - **STATUS:** `pass`
  - **EVIDENCE:** The stack applies the main active directives: root-level IDs across the design files and `README.md`; `worktree` terminology in `methodology-run-design.md`; separation of generic run structure from baseline/variant organization via `methodology-run-design.md` and `methodology-prompt-optimization-design.md`; and exercise-root alignment across `methodology-prompt-optimization-design.md`, `methodology-workflow-design.md`, and `methodology-execution-architecture.md`.

- **CHECK: INPUT-2** No material input directive is silently omitted.
  - **STATUS:** `pass`
  - **EVIDENCE:** The active relationship map in `README.md` covers the full design stack from `FILE-1` through `FILE-7`, and the design files now reflect that split without falling back to the retired autopilot chain.

- **CHECK: INPUT-3** No directive is contradicted by the target.
  - **STATUS:** `pass`
  - **EVIDENCE:** `methodology-run-design.md` keeps generic run structure free of baseline role semantics; `methodology-prompt-optimization-design.md` owns baseline/variant organization; and `methodology-execution-architecture.md` now places prompt-runner state under `<exercise-root>/prompt-runs/` and methodology runs under `<exercise-root>/runs/` instead of mixing them.

## C. Internal Logic

- **CHECK: LOGIC-1** Concepts are introduced before they are used.
  - **STATUS:** `pass`
  - **EVIDENCE:** `README.md` introduces the dependency order with `FILE-1` through `FILE-7`; `methodology-workflow-design.md` defines `BaselineMethodologyRun` before later stage references; and `methodology-standalone-step-harness-design.md` now defines the baseline run path in `ENTITY-4` before using `{{baseline_run_dir}}` in prompt-module reads.

- **CHECK: LOGIC-2** The document follows a logical dependency order.
  - **STATUS:** `pass`
  - **EVIDENCE:** The active order is coherent: generic `prompt_runner` design -> generic methodology run -> methodology prompt optimization -> standalone harness -> workflow -> supervision -> execution architecture.

- **CHECK: LOGIC-3** The document does not contain material contradictions.
  - **STATUS:** `pass`
  - **EVIDENCE:** The workflow and execution architecture now agree that the baseline methodology run lives in `<exercise-root>/runs/baseline/`, while the workflow prompt-runner state lives in `<exercise-root>/prompt-runs/workflow/`.

- **CHECK: LOGIC-4** Requirements are not confused with solution choices.
  - **STATUS:** `pass`
  - **EVIDENCE:** `methodology-run-design.md` states the requirement to isolate mutable edits in `REQ-2`, while the nested `worktree_dir` is modeled later as the design response; `prompt-runner-core-design.md` likewise separates runner requirements from module structure.

- **CHECK: LOGIC-5** Goals are not confused with features.
  - **STATUS:** `pass`
  - **EVIDENCE:** `prompt-runner-core-design.md` separates core workflow execution from operational robustness and operational usability instead of presenting all items as equal product goals.

## D. Justification Quality

- **CHECK: JUST-1** Important assertions have `BECAUSE` clauses.
  - **STATUS:** `pass`
  - **EVIDENCE:** Root requirements, key fields, dependencies, and gaps in the active design authorities consistently include `BECAUSE` clauses, for example `REQ-2` through `REQ-5` in `methodology-run-design.md` and `RULE-1` through `RULE-3` in `methodology-execution-architecture.md`.

- **CHECK: JUST-2** Each `BECAUSE` justifies its immediate parent.
  - **STATUS:** `pass`
  - **EVIDENCE:** The earlier misattachments around run-count and baseline placement are no longer present; for example `BaselineRunDir.path` in `methodology-execution-architecture.md` is now justified by the baseline needing its own exercise-local directory instead of a prompt-runner subdirectory.

- **CHECK: JUST-3** Each `CHAIN-OF-THOUGHT` justifies the `BECAUSE` below it.
  - **STATUS:** `pass`
  - **EVIDENCE:** `REQ-2` in `methodology-run-design.md` and `REQ-5` in `methodology-prompt-optimization-design.md` use `CHAIN-OF-THOUGHT` as a reasoning bridge to the `BECAUSE`, not as a second synopsis.

- **CHECK: JUST-4** Unsupported requirements or claims are flagged.
  - **STATUS:** `pass`
  - **EVIDENCE:** Implementation drift is surfaced explicitly rather than smuggled into the design as settled fact, for example `MOD-1` and `MOD-2` in `methodology-run-design.md` and the explicit gaps in `methodology-workflow-design.md` and `methodology-execution-architecture.md`.

## E. Terminology And Structure

- **CHECK: TERM-1** Established domain vocabulary is used where available.
  - **STATUS:** `pass`
  - **EVIDENCE:** The methodology-specific docs now use `worktree` in `methodology-run-design.md` and `methodology-prompt-optimization-design.md`, while `prompt-runner-core-design.md` keeps the more general `workspace_dir` only for the generic runner where a git worktree is not assumed.

- **CHECK: TERM-2** Repeated terms are stable and unambiguous.
  - **STATUS:** `pass`
  - **EVIDENCE:** The stack now keeps `exercise-root`, `prompt-runs`, `runs/baseline`, `runs/variants`, `MethodologyRun`, and `BaselineMethodologyRun` distinct instead of reusing `workflow` or `baseline worktree` for several different levels.

- **CHECK: TERM-3** Root-level IDs are present when structured review matters.
  - **STATUS:** `pass`
  - **EVIDENCE:** The active design files and `README.md` use embedded IDs such as `REQ-2`, `ENTITY-1`, `PMOD-1`, `PROCESS-3`, and `FILE-7`.

- **CHECK: TERM-4** IDs are not overused on nested lines.
  - **STATUS:** `pass`
  - **EVIDENCE:** Nested `FIELD`, `BECAUSE`, `CHAIN-OF-THOUGHT`, and `PROMPT` lines remain unnumbered, so the IDs stay limited to root-level review objects.

## F. Document Hygiene

- **CHECK: HYGIENE-1** Section purpose lines are present.
  - **STATUS:** `pass`
  - **EVIDENCE:** Each active design authority begins sections with short purpose sentences such as “This section defines...” or “This section explains...”.

- **CHECK: HYGIENE-2** Retired or superseded material is not mixed into active design without explanation.
  - **STATUS:** `pass`
  - **EVIDENCE:** `README.md` keeps the active stack separate and `RULE-8` sends superseded material to `docs/plans/retired/`.

- **CHECK: HYGIENE-3** Modifications are separated from clarifications.
  - **STATUS:** `pass`
  - **EVIDENCE:** `methodology-run-design.md` uses explicit `MOD-1` and `MOD-2` for genuine implementation drift, while other active designs keep target-state decisions in the main body and implementation drift in explicit `GAP` sections instead of mixing wording cleanups with design changes.

- **CHECK: HYGIENE-4** The document stays within its intended scope.
  - **STATUS:** `pass`
  - **EVIDENCE:** `methodology-run-design.md` stays generic to one run, `methodology-prompt-optimization-design.md` owns baseline/variant organization, `methodology-workflow-design.md` owns stage ordering, `methodology-supervision-design.md` owns recovery logic, and `methodology-execution-architecture.md` owns the runtime call chain and filesystem layout.
