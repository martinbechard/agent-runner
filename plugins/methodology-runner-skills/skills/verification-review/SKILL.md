---
name: verification-review
description: Evaluate end-to-end verification reports for chain completeness, test specificity, negative coverage, phantom references, and coverage accuracy
---

# Verification Review

This skill governs the PH-007 judge baseline. Review
`docs/verification/verification-report.yaml` against:

1. `docs/requirements/requirements-inventory.yaml` (PH-000)
2. `docs/features/feature-specification.yaml` (PH-001)

Find only PH-007-specific judge failures. Traceability mechanics such as
quote fidelity and general reference discipline belong to the companion
`traceability-discipline` skill.

All five failure modes below are always blocking. If any finding exists,
the verdict is `revise`.


## Artifact Shape

```yaml
e2e_tests:
  - id: "E2E-AREA-NNN"
    name: "..."
    feature_ref: "FT-NNN"
    acceptance_criteria_refs: ["AC-NNN-NN", ...]
    type: "positive"  # positive | negative | boundary
    setup:
      - step: "..."
    actions:
      - step: "..."
    assertions:
      - "..."

traceability_matrix:
  - inventory_ref: "RI-NNN"
    feature_refs: ["FT-NNN", ...]
    acceptance_criteria_refs: ["AC-NNN-NN", ...]
    e2e_test_refs: ["E2E-AREA-NNN", ...]
    coverage_status: "covered"  # covered | partial | uncovered

coverage_summary:
  total_requirements: 0
  covered: 0
  partial: 0
  uncovered: 0
  coverage_percentage: 0.0
```


## Review Order

Run the checks in this order:

1. Chain completeness
2. Test specificity
3. Negative coverage
4. Phantom references
5. Coverage accuracy

Do not skip later checks because an earlier one already failed. Emit all
blocking findings you can prove from the artifact.


## Check 1: Broken Chains

Walk every row in `traceability_matrix`.

### Pass Condition

Every row must have:

- a non-empty `inventory_ref`
- at least one `feature_refs` entry
- at least one `acceptance_criteria_refs` entry
- at least one `e2e_test_refs` entry

This is the PH-007 chain:

`RI -> FT -> AC -> E2E`

### Flag When

Flag `broken_chain` when any matrix row has an empty chain segment.

Typical failures:

- `feature_refs: []`
- `acceptance_criteria_refs: []`
- `e2e_test_refs: []`
- `coverage_status: covered` on a row with any empty chain field
- `coverage_status: partial` used as a vague placeholder with no real evidence

### Why It Blocks

A broken chain means a requirement has no end-to-end verification path.
PH-007 cannot claim coverage when the chain is incomplete.


## Check 2: Superficial Tests

Walk every entry in `e2e_tests`. Read the `assertions` list as evidence,
not as decoration.

### Pass Condition

At least one assertion in the test must verify a concrete business
outcome required by the linked acceptance criteria.

Ask:

> If the implementation silently produced the wrong business result,
> would any assertion fail?

If yes, the test is specific enough.

### Flag When

Flag `superficial_assertions` when assertions are only generic liveness
or transport checks, such as:

- "page loads"
- "no errors occur"
- "response is 200"
- "output exists"
- "some rows are returned"
- "no exception is thrown"
- log-only checks

Assertions about exit status, request success, or output presence do not
count unless paired with business-specific result checks.

### Why It Blocks

A superficial E2E test can pass while the product returns the wrong
business outcome. That is false confidence, not verification.


## Check 3: Missing Negative Coverage

Walk every feature referenced by the matrix. For each feature that
accepts user input or external data, verify it has at least one linked
E2E test with `type: negative` or `type: boundary`.

Input or external data includes:

- CLI arguments or flags
- file paths or file contents
- stdin
- environment variables
- configuration
- HTTP payloads or query parameters
- upstream service responses
- form fields

### Pass Condition

For each applicable feature, at least one linked E2E test exercises
invalid, malformed, empty, missing, too-large, or otherwise out-of-range
input.

### Flag When

Flag `missing_negative_coverage` when:

- a feature that accepts input has only `type: positive` tests
- a file-based feature has no bad-path test
- a CLI feature has no missing/invalid-argument test
- a bounded input has no edge-case test
- a rejection-path AC exists but is only mapped to positive tests

Do not require negative tests for features that do not accept user input
or external data.

### Why It Blocks

PH-007 is supposed to verify end-to-end behavior, including rejection and
boundary handling. A positive-only plan leaves error paths unverified.


## Check 4: Phantom References

Resolve every referenced ID against the real upstream artifacts.

### Pass Condition

Every referenced ID must exist exactly where it claims to come from:

- `inventory_ref` values must exist in PH-000
- `feature_ref` and `feature_refs[*]` must exist in PH-001
- `acceptance_criteria_refs[*]` must exist in PH-001
- `e2e_test_refs[*]` must exist in this report's own `e2e_tests`

Also check the converse:

- every defined E2E test must appear in at least one matrix row
- every PH-000 RI must appear as a matrix `inventory_ref`

### Flag When

Flag a phantom when an ID does not resolve by exact string match.
Common cases:

- `phantom_feature_reference`
- `phantom_ac_reference`
- `phantom_inventory_reference`
- `phantom_e2e_reference`
- `orphaned_e2e_test`

Exact means exact. Do not normalize, renumber, or infer intent.

Examples of bad inference:

- padding `RI-008` because the list looks sequential
- converting `AC-002-01` into `AC-2-1`
- inventing `FT-*` because a requirement "should probably have one"
- referencing an E2E ID in the matrix that is not defined in `e2e_tests`

### Why It Blocks

A phantom reference encodes fake coverage. Once present, downstream
artifacts will trust it and propagate the error.


## Check 5: Coverage Accuracy

Verify `coverage_summary` against the actual matrix and the PH-000
inventory.

### Arithmetic Procedure

Compute:

- `matrix_total` = number of matrix rows
- `matrix_covered` = rows with `coverage_status == covered`
- `matrix_partial` = rows with `coverage_status == partial`
- `matrix_uncovered` = rows with `coverage_status == uncovered`
- `inventory_total` = number of RI-* items in PH-000

Then verify all of:

1. `coverage_summary.total_requirements == inventory_total`
2. `coverage_summary.covered == matrix_covered`
3. `coverage_summary.partial == matrix_partial`
4. `coverage_summary.uncovered == matrix_uncovered`
5. `covered + partial + uncovered == total_requirements`
6. `coverage_percentage == round(covered / total_requirements * 100, 1)`
7. the set of matrix `inventory_ref` values exactly matches the PH-000 RI set

If Check 1 found broken chains, do not treat those rows as legitimately
covered just because the matrix says `covered`. The summary must reflect
reality, not the artifact's self-report.

### Flag When

Flag `inaccurate_coverage_summary` when the counts or percentage do not
match the matrix or PH-000. Flag `missing_inventory_row` when PH-000 has
an RI with no matrix row.

Typical failures:

- `100.0` coverage with any `partial` or `uncovered` rows
- `total_requirements` matching the matrix but not PH-000
- covered count overstated by rows with broken chains
- missing RI rows hidden by an understated total

### Why It Blocks

The summary is the report's headline claim. If it is wrong, the report
misstates verification status.


## Findings Format

Use concrete, generator-actionable findings.

```yaml
findings:
  - finding_type: broken_chain | superficial_assertions | missing_negative_coverage | phantom_feature_reference | phantom_ac_reference | phantom_inventory_reference | phantom_e2e_reference | orphaned_e2e_test | inaccurate_coverage_summary | missing_inventory_row
    severity: blocking
    matrix_row: "RI-NNN"         # when the finding is tied to a matrix row
    e2e_test_id: "E2E-AREA-NNN"  # when the finding is tied to a test
    feature_id: "FT-NNN"         # when the finding is feature-level
    bad_ref: "FT-NNN"            # for phantom findings
    description: "What is wrong and how PH-007 proved it"
    fix: "Minimal corrective action"

verdict: pass | revise
verdict_reason: "N blocking: ..."
```

Rules:

- Every finding is `severity: blocking`.
- Include the narrowest useful identifier.
- State the proof, not a vague suspicion.
- State a concrete fix the generator can take.
- If any finding exists, `verdict: revise`.
- Only emit `verdict: pass` when zero findings remain.


## Review Example

```yaml
e2e_tests:
  - id: E2E-CLI-001
    feature_ref: FT-001
    acceptance_criteria_refs: [AC-001-01]
    type: positive
    assertions:
      - "Command runs without errors"

  - id: E2E-SKIP-001
    feature_ref: FT-999
    acceptance_criteria_refs: [AC-003-01]
    type: positive
    assertions:
      - "Large file is not counted"

traceability_matrix:
  - inventory_ref: RI-001
    feature_refs: [FT-001]
    acceptance_criteria_refs: [AC-001-01]
    e2e_test_refs: [E2E-CLI-001]
    coverage_status: covered

  - inventory_ref: RI-002
    feature_refs: [FT-002]
    acceptance_criteria_refs: [AC-002-01]
    e2e_test_refs: []
    coverage_status: covered

coverage_summary:
  total_requirements: 5
  covered: 5
  partial: 0
  uncovered: 0
  coverage_percentage: 100.0
```

Correct review:

```yaml
findings:
  - finding_type: superficial_assertions
    severity: blocking
    e2e_test_id: "E2E-CLI-001"
    description: "Assertions only check generic liveness and do not verify any business-specific outcome"
    fix: "Add assertions that validate the concrete result required by AC-001-01"

  - finding_type: phantom_feature_reference
    severity: blocking
    e2e_test_id: "E2E-SKIP-001"
    bad_ref: "FT-999"
    description: "feature_ref FT-999 does not exist in the PH-001 feature specification"
    fix: "Replace with the correct FT-* or remove the test"

  - finding_type: broken_chain
    severity: blocking
    matrix_row: "RI-002"
    description: "e2e_test_refs is empty, so the RI -> FT -> AC -> E2E chain is incomplete"
    fix: "Add a linked E2E test or mark the row uncovered until one exists"

  - finding_type: inaccurate_coverage_summary
    severity: blocking
    description: "coverage_summary claims 5 covered and 100.0%, but the matrix contains a broken chain and therefore does not support full coverage"
    fix: "Recompute covered/partial/uncovered from the corrected matrix"

verdict: revise
verdict_reason: "4 blocking: superficial assertions, phantom reference, broken chain, inaccurate coverage summary"
```


## Pre-Verdict Checklist

Before finalizing:

1. Every matrix row was checked for empty chain segments.
2. Every E2E test's assertions were read for business specificity.
3. Every input-handling feature was checked for negative or boundary coverage.
4. Every FT-*, AC-*, RI-*, and E2E-* reference was resolved exactly.
5. Every defined E2E test was checked for orphaning.
6. Every PH-000 RI was checked for presence in the matrix.
7. Coverage summary totals, partitions, and percentage were recomputed.
8. Every emitted finding is concrete, blocking, and actionable.
