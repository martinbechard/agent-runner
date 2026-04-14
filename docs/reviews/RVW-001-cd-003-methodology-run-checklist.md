# Review Checklist: CD-003 Methodology Run

## Scope

- Target: `docs/design/components/CD-003-methodology-run.md`
- Inputs:
  - `src/cli/methodology_runner/cli.py`
  - `src/cli/methodology_runner/orchestrator.py`
  - `src/cli/methodology_runner/models.py`
  - `src/cli/methodology_runner/phases.py`
  - recent design directives applied in this session:
    - support full-run and selected-phase execution
    - selected phases use methodology order
    - generated per-phase prompts must be explicit in the design
- Review date: `2026-04-13`
- Review scope: selected-phase execution, phase prompt generation, and alignment with the current implementation
- Checklist set:
  - `generic-structured-document-checklist.md`

## A. Review Trace

- **CHECK: TRACE-1** Review target is identified.
  - **STATUS:** pass
  - **EVIDENCE:** The target file is named explicitly in Scope.

- **CHECK: TRACE-2** Review inputs are identified.
  - **STATUS:** pass
  - **EVIDENCE:** The implementation files and the session directives being checked are listed in Scope.

- **CHECK: TRACE-3** Checklist set is identified.
  - **STATUS:** pass
  - **EVIDENCE:** The generic checklist is named explicitly in Scope.

## B. Input Coverage

- **CHECK: INPUT-1** All material input directives are traced.
  - **STATUS:** pass
  - **EVIDENCE:** `REQ-6`, `PROCESS-1`, `ENTITY-6`, and `PROCESS-3` cover the directives about selected-phase execution, methodology-order normalization, and explicit prompt generation.

- **CHECK: INPUT-2** No material input directive is silently omitted.
  - **STATUS:** pass
  - **EVIDENCE:** The design now covers:
    - full-run vs selected-phase execution
    - methodology-order execution for selected phases
    - explicit per-phase `prompt-file.md`, prelude files, and skill manifest paths

- **CHECK: INPUT-3** No directive is contradicted by the target.
  - **STATUS:** pass
  - **EVIDENCE:** The prior contradictions were removed:
    - `ENTITY-1` no longer calls every run a full execution
    - per-phase prompt generation is now placed inside the methodology-runner execution flow rather than before the top-level command starts

## C. Internal Logic

- **CHECK: LOGIC-1** Concepts are introduced before they are used.
  - **STATUS:** pass
  - **EVIDENCE:** `execution_scope`, `selected_phase_ids`, and `PhaseRunArtifacts` are defined in the information model before they are used in the process section.

- **CHECK: LOGIC-2** The document follows a logical dependency order.
  - **STATUS:** pass
  - **EVIDENCE:** The process now reads as:
    - determine scope
    - determine run mode
    - start `methodology_runner`
    - generate per-phase prompt artifacts inside that execution
    - generate timeline
    - evaluate completion

- **CHECK: LOGIC-3** The document does not contain material contradictions.
  - **STATUS:** pass
  - **EVIDENCE:** The selected-phase model in `REQ-6`, `ENTITY-1`, `ENTITY-3`, and `PROCESS-1` is consistent with the implementation in `cli.py`, `orchestrator.py`, and `models.py`.

- **CHECK: LOGIC-4** Requirements are not confused with solution choices.
  - **STATUS:** pass
  - **EVIDENCE:** `REQ-6` states the need to support both full and selected execution. The specific response, such as methodology-order normalization, is expressed under `PROCESS-1` rules rather than as a requirement.

- **CHECK: LOGIC-5** Goals are not confused with features.
  - **STATUS:** pass
  - **EVIDENCE:** The design stays focused on the run component contract and does not mix in optimization-workflow goals or usability features.

## D. Justification Quality

- **CHECK: JUST-1** Important assertions have `BECAUSE` clauses.
  - **STATUS:** pass
  - **EVIDENCE:** The important requirements, entities, and processes added in this pass all include `BECAUSE` clauses.

- **CHECK: JUST-2** Each `BECAUSE` justifies its immediate parent.
  - **STATUS:** pass
  - **EVIDENCE:** Spot checks on `REQ-6`, `ENTITY-6`, `PROCESS-1`, and `PROCESS-3` show the reasons attached to the exact parent assertion rather than nearby items.

- **CHECK: JUST-3** Each `CHAIN-OF-THOUGHT` justifies the `BECAUSE` below it.
  - **STATUS:** pass
  - **EVIDENCE:** The new `CHAIN-OF-THOUGHT` clauses explain:
    - why selected phases must still follow methodology order
    - why generated prompt artifacts are an internal methodology-runner step

- **CHECK: JUST-4** Unsupported requirements or claims are flagged.
  - **STATUS:** pass
  - **EVIDENCE:** The claims about selected-phase execution, ordering, and prompt generation are all supported by the current implementation in `cli.py`, `orchestrator.py`, `models.py`, and `phases.py`.

## E. Terminology And Structure

- **CHECK: TERM-1** Established domain vocabulary is used where available.
  - **STATUS:** pass
  - **EVIDENCE:** The design consistently uses `worktree`, `phase`, `prompt-file.md`, and `selected phases`.

- **CHECK: TERM-2** Repeated terms are stable and unambiguous.
  - **STATUS:** pass
  - **EVIDENCE:** `execution_scope`, `selected_phase_ids`, `worktree`, and `phase_run_dir` are used consistently through the document.

- **CHECK: TERM-3** Root-level IDs are present when structured review matters.
  - **STATUS:** pass
  - **EVIDENCE:** Root-level `REQUIREMENT`, `ENTITY`, `PROCESS`, `COMMAND`, and `MODIFICATION` items use embedded IDs.

- **CHECK: TERM-4** IDs are not overused on nested lines.
  - **STATUS:** pass
  - **EVIDENCE:** Nested `FIELD`, `RULE`, `SYNOPSIS`, `BECAUSE`, and `CHAIN-OF-THOUGHT` lines are not separately ID’d.

## F. Document Hygiene

- **CHECK: HYGIENE-1** Section purpose lines are present.
  - **STATUS:** pass
  - **EVIDENCE:** Each major section begins with a short sentence explaining its purpose.

- **CHECK: HYGIENE-2** Retired or superseded material is not mixed into active design without explanation.
  - **STATUS:** pass
  - **EVIDENCE:** The design stays on the current methodology-run component and does not mix in retired baseline-only or old workflow terminology.

- **CHECK: HYGIENE-3** Modifications are separated from clarifications.
  - **STATUS:** pass
  - **EVIDENCE:** The document keeps implementation drift in the `Modifications` section rather than mixing it into the main design logic.

- **CHECK: HYGIENE-4** The document stays within its intended scope.
  - **STATUS:** pass
  - **EVIDENCE:** The document explains the methodology-run component itself. It does not drift into optimization-campaign organization or phase-specific review details beyond the generic per-phase artifact model.
