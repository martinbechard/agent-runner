### Module

verification-sweep

## Prompt 1: Produce Verification Sweep

### Required Files

docs/features/feature-specification.yaml
docs/implementation/implementation-plan.yaml
docs/design/solution-design.yaml
docs/requirements/requirements-inventory.yaml

### Include Files

docs/features/feature-specification.yaml
docs/implementation/implementation-plan.yaml
docs/design/solution-design.yaml
docs/requirements/requirements-inventory.yaml

### Checks Files

docs/verification/verification-report.yaml

### Deterministic Validation

.methodology/src/cli/methodology_runner/phase_7_validation.py
--feature-spec
docs/features/feature-specification.yaml
--implementation-plan
docs/implementation/implementation-plan.yaml
--solution-design
docs/design/solution-design.yaml
--requirements-inventory
docs/requirements/requirements-inventory.yaml
--verification-report
docs/verification/verification-report.yaml

### Generation Prompt

You are producing the phase artifact for PH-007-verification-sweep.

Use the included upstream file contents as the primary source input:
- docs/features/feature-specification.yaml
- docs/implementation/implementation-plan.yaml
- docs/design/solution-design.yaml
- docs/requirements/requirements-inventory.yaml

Write:
- docs/verification/verification-report.yaml

Task:
Produce the final acceptance-ready YAML verification sweep in one file.
Use this prompt pair's built-in revise loop to correct any issues the judge
finds. Do not create draft-only or partial versions on purpose.

Module-local generator context:
Embedded directives for this step:

- Build an honest chain from `RI-*` through `FT-*` and `AC-*` to `E2E-*`.
- Write end-to-end tests that are concrete enough to review: real setup,
  actions, and feature-specific assertions.
- Add negative or boundary coverage where the feature or input shape requires
  it.
- Mark rows partial or uncovered when the upstream artifacts do not support a
  complete chain. Do not fake completeness.

Phase purpose:
- Define concrete end-to-end tests.
- Build a traceability matrix from RI-* through FT-* and AC-* to E2E-*.
- Summarize overall coverage and explicit remaining gaps.

Important interpretation:
- This phase is a verification-planning layer.
- E2E tests must be concrete enough to review, but they are still plans rather
  than executable code.
- If upstream artifacts intentionally leave a requirement uncovered, record that
  honestly in coverage_status rather than fabricating a complete chain.

Output schema to satisfy:
e2e_tests:
  - id: "E2E-AREA-NNN"
    name: "Descriptive test name"
    feature_ref: "FT-NNN"
    acceptance_criteria_refs: ["AC-NNN-NN", "..."]
    type: "positive"
    setup:
      - step: "Precondition"
    actions:
      - step: "Action"
    assertions:
      - "What must be true"
traceability_matrix:
  - inventory_ref: "RI-NNN"
    feature_refs: ["FT-NNN", "..."]
    acceptance_criteria_refs: ["AC-NNN-NN", "..."]
    e2e_test_refs: ["E2E-AREA-NNN", "..."]
    coverage_status: "covered"
coverage_summary:
  total_requirements: 0
  covered: 0
  partial: 0
  uncovered: 0
  coverage_percentage: 0.0

Acceptance requirements:
- The file must be valid YAML parseable by a standard YAML parser.
- The top-level keys must appear exactly in this order:
  e2e_tests
  traceability_matrix
  coverage_summary
- Every E2E test must contain:
  id
  name
  feature_ref
  acceptance_criteria_refs
  type
  setup
  actions
  assertions
- type must be one of:
  positive
  negative
  boundary
- Every RI-* from docs/requirements/requirements-inventory.yaml must appear in
  traceability_matrix.
- coverage_status must be one of:
  covered
  partial
  uncovered
- coverage_summary counts must match the actual matrix counts.
- Do not create any files other than docs/verification/verification-report.yaml.
- Write the full file contents to docs/verification/verification-report.yaml.

### Validation Prompt

Use the included upstream file contents as the primary review input:
- docs/features/feature-specification.yaml
- docs/implementation/implementation-plan.yaml
- docs/design/solution-design.yaml
- docs/requirements/requirements-inventory.yaml

Read:
- docs/verification/verification-report.yaml

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Module-local judge context:

- Review for broken chains, superficial tests, missing negative or boundary
  coverage, phantom references, and misleading coverage claims.

Your job is to decide whether the generated verification sweep is phase-ready.
Focus your semantic review on these failure modes:

1. Broken chains:
   - Flag RI rows that claim coverage but do not materially connect through the
     referenced features, acceptance criteria, and E2E tests.
2. Superficial tests:
   - Flag E2E tests that only assert generic success and do not verify
     feature-specific outcomes.
3. Missing negative or boundary coverage:
   - Flag features that materially need non-happy-path coverage but do not have it.
4. Phantom references:
   - Flag references that technically exist but are semantically unrelated to
     the row or test they are used to justify.
5. Misleading coverage claims:
   - Flag rows or summaries that overstate coverage rather than honestly marking
     partial or uncovered status.

Review instructions:
- Use the deterministic validation report as authoritative for structural
  checks, reference existence, matrix row coverage, and summary counts.
- Treat this phase as a verification-planning layer.
- Only ask for a change when the current report is wrong, contradictory,
  materially unsupported, or materially misstates coverage.
- Do not force fake completeness. If a requirement is genuinely partial or
  uncovered given upstream artifacts, partial or uncovered may be correct.
- Do not request wording polish or alternate test names unless the current
  wording is misleading or materially consequential.
- If you find issues, cite exact RI-* / FT-* / AC-* / E2E-* IDs.
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary
- Use VERDICT: pass only if the artifact is phase-ready with no material
  traceability, specificity, or coverage-accounting defects.
- Use VERDICT: revise if the artifact can be corrected within this same file.
- Use VERDICT: escalate only if the upstream artifacts are too ambiguous or
  contradictory to produce a stable verification sweep.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
