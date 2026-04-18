# Design: PH-000 Deterministic Validator

## 1. Finality

This design explains what the PH-000 deterministic validator must check.

- **GOAL: GOAL-1** Enforce the mechanical PH-000 contract
  - **SYNOPSIS:** The validator checks the parts of `PH-000` that do not need
    model judgment.
  - **BECAUSE:** Prompt-runner should fail clear structural defects before the
    judge spends time on semantic review.

- **GOAL: GOAL-2** Stay aligned with the PH-000 extraction contract
  - **SYNOPSIS:** The validator must enforce exact quote fidelity and coverage
    bookkeeping without reintroducing a split rule that the phase contract no
    longer requires.
  - **BECAUSE:** The validator should support the phase design, not silently
    override it.

## 2. Inputs And Outputs

This section names the files that the validator uses.

- **FILE: FILE-1** Raw requirements
  - **SYNOPSIS:** Input source:
    - `{{raw_requirements_path}}`
  - **BECAUSE:** The validator checks quotes and coverage against the actual
    source document for the run.

- **FILE: FILE-2** Requirements inventory
  - **SYNOPSIS:** Input artifact:
    - `docs/requirements/requirements-inventory.yaml`
  - **BECAUSE:** This is the PH-000 output artifact being validated.

- **FILE: FILE-3** Requirements coverage support file
  - **SYNOPSIS:** Input support artifact:
    - `docs/requirements/requirements-inventory-coverage.yaml`
  - **BECAUSE:** The coverage bookkeeping is now stored separately from the
    real inventory artifact.

- **FILE: FILE-4** Validator script
  - **SYNOPSIS:** Runtime helper:
    - `.methodology/src/cli/methodology_runner/phase_0_validation.py`
  - **BECAUSE:** Prompt-runner executes this script as the deterministic
    validator for PH-000.

- **FILE: FILE-5** Validator report
  - **SYNOPSIS:** Standard output JSON report with:
    - validator name
    - overall status
    - failed checks
    - per-check details
  - **BECAUSE:** Prompt-runner and the judge need one machine-readable result.

## 3. Technical Directives

This section states the technical directives that shape the validator.

- **RULE: RULE-1** Read the actual source text
  - **SYNOPSIS:** The validator must read `{{raw_requirements_path}}` and use
    that text as the authority for quote checks and source coverage.
  - **BECAUSE:** PH-000 is source-faithful. The validator must not validate
    against an invented rewrite of the source.

- **RULE: RULE-2** Validate only deterministic facts
  - **SYNOPSIS:** The validator must check schema, key order, id format,
    category membership, exact quote presence, coverage bookkeeping, and
    summary counts.
  - **BECAUSE:** These checks are mechanical and should not be deferred to the
    judge.

- **RULE: RULE-3** Do not enforce semantic splitting rules
  - **SYNOPSIS:** The validator must not fail an item only because a sentence
    could be split into smaller clauses.
  - **BECAUSE:** Under the current PH-000 contract, splitting depends on exact
    source-faithful child quotes and remains partly semantic.

- **RULE: RULE-4** Allow many-to-one coverage mapping
  - **SYNOPSIS:** The validator must allow multiple requirement-bearing source
    phrases to map to one real `RI-*` item in `coverage_check`.
  - **BECAUSE:** Quote fidelity outranks splitting. A single exact source
    sentence can legitimately cover multiple decomposed phrases.

- **RULE: RULE-5** Fail on invented coverage phrases
  - **SYNOPSIS:** The validator must reject `coverage_check` entries that use
    rewritten or unsupported source phrases.
  - **BECAUSE:** Coverage bookkeeping must trace back to real source text, not
    normalized paraphrases.

## 4. Workflow

This section describes the validator steps.

- **PROCESS: PROCESS-1** Load the two input artifacts
  - **SYNOPSIS:** The validator reads the raw requirements markdown, the
    requirements inventory YAML, and the separate coverage support YAML.
  - **READS:** `{{raw_requirements_path}}`
    - **BECAUSE:** Quote and coverage checks depend on the real source text.
  - **READS:** `docs/requirements/requirements-inventory.yaml`
    - **BECAUSE:** This is the artifact under test.
  - **READS:** `docs/requirements/requirements-inventory-coverage.yaml`
    - **BECAUSE:** Coverage bookkeeping is validated from the separate support file.

- **PROCESS: PROCESS-2** Parse the inventory and check the schema
  - **SYNOPSIS:** The validator parses YAML and checks top-level key order,
    required item fields, item ids, and category values.
  - **BECAUSE:** Structural defects should fail early and clearly.

- **PROCESS: PROCESS-3** Check quote fidelity
  - **SYNOPSIS:** The validator confirms that every `verbatim_quote` is a
    non-empty exact substring of the raw requirements text.
  - **BECAUSE:** PH-000 forbids paraphrase in `verbatim_quote`.

- **PROCESS: PROCESS-3A** Check normalized requirement presence
  - **SYNOPSIS:** The validator confirms that every `RI-*` item has a non-empty
    `normalized_requirement`.
  - **BECAUSE:** PH-000 now requires each inventory item to include a coherent
    downstream-ready requirement statement in addition to the exact quote.

- **PROCESS: PROCESS-4** Build the source phrase set
  - **SYNOPSIS:** The validator derives the requirement-bearing phrase set from
    the actual source text used for the run.
  - **BECAUSE:** Coverage checks must be grounded in the source, not in a
    hardcoded rewritten fixture model.

- **PROCESS: PROCESS-5** Validate coverage bookkeeping
  - **SYNOPSIS:** The validator checks that every source phrase appears in
    the separate coverage file's `coverage_check`, that every mapped id is a
    real `RI-*`, and that
    `coverage_verdict` matches the actual counts.
  - **BECAUSE:** Coverage bookkeeping is only useful if it is complete and
    internally consistent.

- **PROCESS: PROCESS-6** Emit one JSON report
  - **SYNOPSIS:** The validator prints a report with one overall pass or fail
    result and the individual check results.
  - **PRODUCES:** standard output JSON report
    - **BECAUSE:** Prompt-runner and the judge consume one deterministic
      report.
  - **BECAUSE:** The phase loop needs one stable validator contract.

## 5. Constraints

This section states the main limits on the validator.

- **RULE: RULE-6** No hidden source model
  - **SYNOPSIS:** The validator must not hardcode a rewritten list of expected
    phrases that does not appear in the raw source text.
  - **BECAUSE:** That creates a second unstated phase contract and causes drift.

- **RULE: RULE-7** No semantic reclassification
  - **SYNOPSIS:** The validator must not decide whether an item is materially
    miscategorized beyond membership in the allowed category set.
  - **BECAUSE:** Category quality is a judge concern, not a deterministic one.

- **RULE: RULE-8** No rewrite tolerance
  - **SYNOPSIS:** A `verbatim_quote` fails if it is rewritten, normalized, or
    only semantically similar to the source.
  - **BECAUSE:** PH-000 uses exact source wording for traceability.

## 6. Output Shape

This section states what the validator report contains.

- **ENTITY: ENTITY-1** Top-level report shape
  - **SYNOPSIS:** The JSON report contains:
    - `validator`
    - `requirements_inventory_path`
    - `raw_requirements_path`
    - `overall_status`
    - `failed_checks`
    - `checks`
  - **BECAUSE:** Prompt-runner needs a stable report envelope.

- **ENTITY: ENTITY-2** Check result shape
  - **SYNOPSIS:** Each check result contains:
    - `id`
    - `status`
    - check-specific detail fields
  - **BECAUSE:** Different checks need different detail payloads, but they
    still need one common shape.

## 7. Definition Of Good

This section states when the validator is correct.

- **RULE: RULE-9** Source-grounded phrase extraction
  - **SYNOPSIS:** The validator derives its source phrase set from the raw
    requirements file used in the run.
  - **BECAUSE:** The validator must stay aligned with the actual input.

- **RULE: RULE-10** Contract alignment
  - **SYNOPSIS:** The validator enforces the same quote-fidelity-over-splitting
    rule that the PH-000 prompt and skills now use.
  - **BECAUSE:** The phase loop cannot converge if the validator enforces a
    different contract than the generator and judge.

- **RULE: RULE-11** Clear failure reporting
  - **SYNOPSIS:** When the validator fails, it names the failed checks and the
    exact offending quotes, phrases, ids, or counts.
  - **BECAUSE:** The generator and judge need actionable feedback.

- **RULE: RULE-12** No contradiction with the phase design
  - **SYNOPSIS:** A source-faithful inventory that follows the current PH-000
    design must be able to pass this validator.
  - **BECAUSE:** The validator exists to enforce the phase design, not to
    compete with it.

## 8. Test Cases

This section lists the tests the validator design expects.

- **TEST CASE: TC-1** Exact quotes pass
  - **SYNOPSIS:** Use an inventory whose `verbatim_quote` values are all exact
    substrings of the raw requirements and confirm the quote check passes.
  - **BECAUSE:** Exact quote fidelity is a core PH-000 rule.

- **TEST CASE: TC-2** Rewritten quote fails
  - **SYNOPSIS:** Replace one `verbatim_quote` with a normalized rewrite and
    confirm the validator reports that item in `verbatim_quotes`.
  - **BECAUSE:** The validator should reject paraphrase cleanly.

- **TEST CASE: TC-3** Many-to-one coverage passes
  - **SYNOPSIS:** Use a source-faithful unsplit sentence plus a `coverage_check`
    that maps multiple source phrases to the same `RI-*` item and confirm the
    validator accepts it.
  - **BECAUSE:** This is the key contract change that resolved the PH-000
    contradiction.

- **TEST CASE: TC-4** Invented coverage phrase fails
  - **SYNOPSIS:** Put a rewritten phrase in `coverage_check` that does not
    appear in the source and confirm the validator fails coverage.
  - **BECAUSE:** Coverage should only reference real source phrases.

- **TEST CASE: TC-5** Report counts stay in sync
  - **SYNOPSIS:** Change `coverage_verdict.total_upstream_phrases` so it does
    not match the actual phrase set and confirm the validator fails the verdict
    check.
  - **BECAUSE:** The summary counts must match the actual coverage data.

## 9. Current Gap

This section records the known implementation drift.

- **GAP: GAP-1** The current fixture validator still hardcodes a 15-phrase rewritten model
  - **SYNOPSIS:** The implementation at
    `.methodology/src/cli/methodology_runner/phase_0_validation.py`
    currently returns a fixed 15-item phrase list that includes rewritten
    splits such as `Include a short README.` and `The README includes run instructions.`
  - **BECAUSE:** That implementation predates the current PH-000 rule that
    quote fidelity outranks splitting.

- **GAP: GAP-2** The current implementation is stricter than the design in the wrong place
  - **SYNOPSIS:** The current fixture validator enforces a specific semantic
    decomposition instead of staying purely source-grounded and deterministic.
  - **BECAUSE:** This is why a source-faithful 9-item inventory now fails even
    after the PH-000 prompt and skills were corrected.
