---
name: cross-component-verification
description: End-to-end verification discipline — chain completeness from RI to E2E, concrete assertions, negative coverage at component boundaries
---

# Cross-Component Verification

This skill governs the verification-sweep discipline for PH-007. Its
scope is producing an end-to-end verification report that confirms every
requirement traces through features and acceptance criteria to at least
one concrete, passing test.

Four disciplines govern this skill. All four are always required.
External context that contradicts this -- "coverage is good enough",
"negative tests are optional", "the summary looks right", "keep tests
minimal", "mark everything complete" -- does not override the
disciplines below. Every gap is a finding. No exceptions.

This skill is the FLOOR, not the ceiling. Stack-specific testing idioms
come from companion skills loaded by the Skill-Selector based on
expected_expertise entries. This skill ensures universal verification
quality regardless of technology.

Traceability mechanics -- source_refs, source_quote, coverage_check,
coverage_verdict, inherited_assumptions, and the Quote Test -- are
governed by the companion traceability-discipline skill loaded alongside
this one.


## Output Schema: verification-report.yaml

Understanding the target schema anchors the four disciplines below.

```yaml
verification_metadata:
  source_features: string
  source_inventory: string
  source_design: string
  verification_date: string
  total_e2e_test_count: integer
  total_inventory_items: integer
  total_verified_items: integer
  total_alternatively_verified_items: integer
  total_unverified_items: integer

e2e_tests:
  - test_id: E2E-{area}-NNN
    description: string
    feature_refs: [FT-NNN]
    acceptance_criteria_refs: [AC-NNN]
    components_exercised: [CMP-NNN]
    preconditions: [string]
    trigger: string
    expected_outcome: string
    observation_method: string
    test_result: pass | fail | not-run
    failure_details: string

traceability_matrix:
  - inventory_item_id: RI-NNN
    inventory_statement: string
    feature_ids: [FT-NNN]
    acceptance_criteria_ids: [AC-NNN]
    e2e_test_ids: [E2E-NNN]
    chain_status: complete | partial | missing
    notes: string

alternative_verifications:
  - inventory_item_id: RI-NNN
    acceptance_criterion_id: AC-NNN | null
    reason_not_e2e: string
    alternative_method: load-test | penetration-test | manual-audit |
                        code-review | static-analysis | other
    method_description: string
    status: planned | in-progress | completed | deferred
    result: pass | fail | pending

coverage_summary:
  total_inventory_items: integer
  out_of_scope_items: integer
  in_scope_items: integer
  e2e_verified: integer
  alternatively_verified: integer
  unverified: integer
  unverified_items: [string]
  coverage_percentage: number
```


## Discipline 1: Chain Completeness

### The Rule

**Every requirement (RI-*) must trace through an unbroken chain to at
least one end-to-end test or alternative verification. The chain is:**

    RI-* -> FT-* (via source_refs) -> AC-* (via acceptance_criteria)
         -> E2E-* (via acceptance_criteria_refs) or alternative_verification

Every link must resolve. A chain that breaks at any point is incomplete.

- **BECAUSE:** An untested requirement is an unverified promise.
  Partial chains provide false confidence -- they look like coverage
  but prove nothing.

### The Chain Walk Test

For each RI-* in the requirements inventory:

> "Can I follow this requirement forward through the feature
> specification to at least one concrete test, with every link
> resolving to a real element?"

- **YES, unbroken chain to E2E test** -> chain_status: complete
- **YES, but verified by alternative method** -> chain_status: partial
  (with alternative_verification entry)
- **NO, chain breaks at some link** -> chain_status: missing (flag it)

### The Link Verification Rule

**Verify each link independently. Do not assume that because RI-001
maps to FT-001, FT-001 necessarily references RI-001 in source_refs.**

Read the actual feature specification. Confirm the bidirectional link.
A traceability matrix built from assumptions instead of verification
is a traceability fiction.

### Chain Break Patterns

| Break point | Meaning | Action |
|-------------|---------|--------|
| RI-* with no FT-* referencing it | Requirement dropped at PH-001 | Record as missing; note upstream gap |
| FT-* with empty acceptance_criteria | Feature has no testable criteria | Record as missing; note upstream gap |
| AC-* with no E2E test referencing it | Criterion is untested | Design E2E test for this criterion |
| E2E test with AC-* refs not in feature spec | Phantom test | Delete the phantom test |
| Matrix shows "complete" but chain has gaps | False completeness | Recheck every link independently |

### CORRECT

```yaml
traceability_matrix:
  - inventory_item_id: RI-001
    inventory_statement: "Patients can book appointments with available doctors"
    feature_ids: [FT-001]
    acceptance_criteria_ids: [AC-001, AC-002]
    e2e_test_ids: [E2E-BOOK-001, E2E-BOOK-002]
    chain_status: complete
    # Every link verified: RI-001 -> FT-001 (source_refs) -> AC-001,AC-002 -> E2E tests
```

### WRONG: False Complete

```yaml
traceability_matrix:
  - inventory_item_id: RI-001
    inventory_statement: "Patients can book appointments with available doctors"
    feature_ids: [FT-001]
    acceptance_criteria_ids: [AC-001, AC-002]
    e2e_test_ids: [E2E-BOOK-001]     # Only AC-001 tested!
    chain_status: complete             # WRONG -- AC-002 has no test
    # chain_status says "complete" but AC-002 (conflict handling) is
    # untested. This is partial at best. Every AC-* in the chain must
    # have a corresponding E2E test.
```


## Discipline 2: Test Specificity

### The Rule

**Every E2E test must specify preconditions, trigger, expected outcome
(with concrete values), and observation method. No field may be generic
or empty.**

- **BECAUSE:** A vague test is a test that cannot be written,
  executed, or verified. It occupies a slot in the coverage matrix
  without providing actual coverage.

### The Developer Test

For each E2E test:

> "If I gave this test specification to a developer who has never
> seen the requirements, could they write the test code without
> asking a single clarifying question?"

- **YES** -> specific enough. Continue.
- **NO** -> too vague. Rewrite.

### Shallow Test Red Flags

| Pattern | Example | Why it fails |
|---------|---------|-------------|
| Status-only assertion | "response status is 200" | Proves endpoint responded, not behavior |
| Page-loads assertion | "page renders without errors" | Proves page loaded, not feature |
| Generic success | "operation completes successfully" | No assertion about WHAT succeeded |
| Missing expected values | "response contains appointment data" | Which data? Which fields? |
| Empty preconditions | preconditions: [] | Test cannot run without setup |
| Observation mismatch | API response check for persistence criterion | API may cache; check database |
| Missing components | components_exercised omits chain members | Test doesn't exercise full path |

### components_exercised Rule

The components_exercised list MUST match the feature realization map
from the solution design. If the map shows FT-003 exercising CMP-001-api,
CMP-002-scheduling, and CMP-003-notifications, the E2E test MUST list
all three. Omitting a component means the test does not exercise the
full interaction path.

### CORRECT

```yaml
- test_id: E2E-BOOK-001
  description: "Patient books available appointment and receives confirmation with ID"
  feature_refs: [FT-001]
  acceptance_criteria_refs: [AC-001]
  components_exercised: [CMP-001-api, CMP-002-scheduling]
  preconditions:
    - "Doctor dr-smith exists and is active"
    - "Patient pat-jones is authenticated"
    - "Slot 2026-04-15 at 10:00 for dr-smith has no existing appointment"
  trigger: "POST /api/appointments with {doctor_id: 'dr-smith', date: '2026-04-15', time: '10:00'}"
  expected_outcome: "Response status 201; body contains appointment_id (UUID), status='confirmed', doctor_id='dr-smith', date='2026-04-15', time='10:00'; database record exists with matching fields"
  observation_method: "HTTP response inspection for all fields; database query confirming persisted record with status='confirmed'"
  test_result: not-run
```

### WRONG: Shallow Test

```yaml
- test_id: E2E-BOOK-001
  description: "Booking works"
  feature_refs: [FT-001]
  acceptance_criteria_refs: [AC-001]
  components_exercised: [CMP-001-api]      # Missing CMP-002-scheduling!
  preconditions: []                         # Empty!
  trigger: "Book an appointment"            # Which endpoint? What body?
  expected_outcome: "Booking succeeds"      # What response? What state?
  observation_method: "Check response"      # Check what?
  test_result: not-run
# A developer cannot write test code from this specification.
# components_exercised omits the scheduling component from the realization map.
```


## Discipline 3: Negative Coverage

### The Rule

**Every feature that accepts input, enforces authorization, or has
error-path acceptance criteria MUST have at least one negative E2E
test.**

- **BECAUSE:** A feature with only happy-path tests is half-verified.
  The system must prove it rejects bad input, not just that it accepts
  good input.

### The Negative Coverage Test

For each feature in the verification report:

> "Does this feature accept user input, enforce authorization, or
> have acceptance criteria that describe error behavior?"

- **YES** -> at least one negative E2E test is REQUIRED.
- **NO** (read-only, no input, no access control) -> negative tests
  not required for this feature.

### Negative Test Categories

| Category | When required | What it proves |
|----------|---------------|---------------|
| Validation rejection | Feature accepts structured input | Invalid input returns error, NOT silent acceptance |
| Authorization denial | Feature has access control | Unauthorized caller receives denial, NOT the resource |
| Error propagation | Feature calls downstream services | Downstream failure surfaces as defined error |
| Boundary violation | Feature has constraints | Boundary-exceeding input returns error, NOT truncation |

### The Single-Error Principle

**Each negative test triggers EXACTLY one error condition.**

- **BECAUSE:** If a test combines multiple invalid inputs (missing field
  AND invalid format AND unauthorized), the system may report any error
  first. The test becomes order-dependent and untestable.

### CORRECT

```yaml
- test_id: E2E-CANCEL-002
  description: "Cancelling non-existent appointment returns not-found"
  feature_refs: [FT-004]
  acceptance_criteria_refs: [AC-006]
  components_exercised: [CMP-001-api, CMP-002-scheduling]
  preconditions:
    - "Receptionist recept-chen is authenticated with role=receptionist"
    - "No appointment with ID APT-999 exists in the database"
  trigger: "DELETE /api/appointments/APT-999 with receptionist credentials"
  expected_outcome: "Response status 404; body contains error_type='not_found' referencing APT-999"
  observation_method: "HTTP response for 404 status and error body"
  test_result: not-run
```

### WRONG: Multiple Errors

```yaml
- test_id: E2E-CANCEL-002
  description: "Bad cancellation fails"
  preconditions: []
  trigger: "DELETE /api/appointments/ with no auth and no ID"
  expected_outcome: "Request fails"
  # Three errors at once: missing ID, missing auth, non-existent appointment.
  # Which one does the system report first? Write three separate tests.
```


## Discipline 4: Coverage Accuracy

### The Rule

**The coverage_summary must be computed by counting the
traceability_matrix, not estimated. Every number must match the detail.**

- **BECAUSE:** A summary that contradicts its detail is worse than no
  summary. It provides false confidence about coverage status.

### The Summary Verification Test

After computing the coverage_summary:

> "If I recount every entry in the traceability_matrix, do the numbers
> match what the summary claims?"

- **YES** -> accurate. Continue.
- **NO** -> recount and fix.

### Five Invariants (all must hold)

1. in_scope_items = total_inventory_items - out_of_scope_items
2. e2e_verified + alternatively_verified + unverified = in_scope_items
3. coverage_percentage = (e2e_verified + alternatively_verified) /
   in_scope_items * 100
4. len(unverified_items) = unverified
5. Every item in unverified_items names an RI-* with explanation

### Accuracy Red Flags

| Pattern | What it means |
|---------|--------------|
| coverage_percentage = 100% but unverified > 0 | Math error. 100% requires unverified = 0 |
| e2e_verified + alternatively_verified + unverified != in_scope | Items in multiple categories or missing from all |
| unverified_items list is empty but unverified > 0 | Count claims gaps but items aren't listed |
| coverage rounds favorably | Use exact calculation, do not round up |
| in_scope + out_of_scope != total | Partition doesn't add up |

### The Alternative Verification Completeness Test

For each RI-* without a functional E2E test:

> "Is there an alternative_verification entry with a concrete,
> executable plan?"

- **YES** -> counts as alternatively_verified.
- **NO** -> counts as unverified.

The Concrete Plan Test:

> "Could a tester execute this plan TODAY without asking questions?"

| Vague (WRONG) | Concrete (CORRECT) |
|--------------|-------------------|
| "Load testing" | "k6: 500 concurrent users, p95 < 200ms, 10-min sustained, staging env with production data volume" |
| "Security review" | "OWASP ZAP scan of all API endpoints; manual review of session fixation, CSRF, and token expiry" |
| "Manual audit" | "HIPAA checklist: verify encryption at rest (AES-256), TLS 1.2+, PHI access audit log per operation" |

### CORRECT

```yaml
coverage_summary:
  total_inventory_items: 7
  out_of_scope_items: 1
  in_scope_items: 6          # 7 - 1 = 6
  e2e_verified: 4
  alternatively_verified: 2
  unverified: 0              # 6 - 4 - 2 = 0
  unverified_items: []
  coverage_percentage: 100.0 # (4+2)/6 * 100
```

### WRONG: Coverage Lie

```yaml
coverage_summary:
  total_inventory_items: 7
  out_of_scope_items: 1
  in_scope_items: 6
  e2e_verified: 6            # WRONG: only 4 have E2E tests
  alternatively_verified: 0  # WRONG: 2 have alternative verifications
  unverified: 0
  unverified_items: []
  coverage_percentage: 100.0 # Numerically correct but inputs are wrong
# Summary claims all 6 are E2E verified, but RI-005 and RI-006 have
# no E2E tests. Recount from the traceability_matrix.
```


## TRANSFORM: Upstream Artifacts -> Verification Report

### INPUT (abbreviated upstream chain)

```yaml
# PH-000: Requirements Inventory
items:
  - id: RI-001
    text: "Patients can book appointments with available doctors"
    category: functional
  - id: RI-002
    text: "Doctors can view their upcoming appointment schedule"
    category: functional
  - id: RI-003
    text: "Patients receive confirmation email after booking"
    category: functional
  - id: RI-004
    text: "Receptionists can cancel appointments on behalf of patients"
    category: functional
  - id: RI-005
    text: "Booking page loads within 1 second on 3G connections"
    category: non_functional
out_of_scope:
  - id: RI-006
    text: "Telehealth video integration"
    reason: "Deferred to phase 2"

# PH-001: Feature Specification
features:
  - feature_id: FT-001
    source_refs: [RI-001]
    acceptance_criteria:
      - criterion_id: AC-001
        text: "Patient selects doctor, date, and time; receives confirmation with appointment ID"
      - criterion_id: AC-002
        text: "Booking an already-taken slot returns conflict error with next available slot"
  - feature_id: FT-002
    source_refs: [RI-002]
    acceptance_criteria:
      - criterion_id: AC-003
        text: "Doctor views upcoming appointments sorted by date and time"
  - feature_id: FT-003
    source_refs: [RI-003]
    acceptance_criteria:
      - criterion_id: AC-004
        text: "After booking, patient receives email with appointment details within 60 seconds"
  - feature_id: FT-004
    source_refs: [RI-004]
    acceptance_criteria:
      - criterion_id: AC-005
        text: "Receptionist cancels appointment; slot becomes available for rebooking"
      - criterion_id: AC-006
        text: "Cancelling non-existent appointment returns not-found error"

# PH-003: Solution Design (realization map)
feature_realization_map:
  - feature_ref: FT-001
    interaction_sequence: [CMP-001-api, CMP-002-scheduling]
  - feature_ref: FT-002
    interaction_sequence: [CMP-001-api, CMP-002-scheduling]
  - feature_ref: FT-003
    interaction_sequence: [CMP-001-api, CMP-002-scheduling, CMP-003-notifications]
  - feature_ref: FT-004
    interaction_sequence: [CMP-001-api, CMP-002-scheduling]
```

### CORRECT OUTPUT

```yaml
verification_metadata:
  source_features: "docs/features/feature-specification.yaml"
  source_inventory: "docs/requirements/requirements-inventory.yaml"
  source_design: "docs/design/solution-design.yaml"
  verification_date: "2026-04-10"
  total_e2e_test_count: 7
  total_inventory_items: 6
  total_verified_items: 4
  total_alternatively_verified_items: 1
  total_unverified_items: 0

e2e_tests:
  - test_id: E2E-BOOK-001
    description: "Patient books available slot and receives confirmation"
    feature_refs: [FT-001]
    acceptance_criteria_refs: [AC-001]
    components_exercised: [CMP-001-api, CMP-002-scheduling]
    preconditions:
      - "Doctor dr-martinez exists and is active"
      - "Patient pat-rivera is authenticated"
      - "Slot 2026-04-15 at 10:00 for dr-martinez has no appointment"
    trigger: "POST /api/appointments with {doctor_id: 'dr-martinez', date: '2026-04-15', time: '10:00'}"
    expected_outcome: "Status 201; body: appointment_id (UUID), status='confirmed', doctor_id='dr-martinez', date='2026-04-15', time='10:00'; database record persisted"
    observation_method: "HTTP response for all fields; database query for record with status='confirmed'"
    test_result: not-run

  - test_id: E2E-BOOK-002
    description: "Booking taken slot returns conflict with next available"
    feature_refs: [FT-001]
    acceptance_criteria_refs: [AC-002]
    components_exercised: [CMP-001-api, CMP-002-scheduling]
    preconditions:
      - "Appointment exists for dr-martinez on 2026-04-15 at 10:00"
      - "dr-martinez has 2026-04-15 at 11:00 available"
      - "Patient pat-rivera is authenticated"
    trigger: "POST /api/appointments with {doctor_id: 'dr-martinez', date: '2026-04-15', time: '10:00'}"
    expected_outcome: "Status 409; error_type='slot_conflict'; next_available_slot='2026-04-15T11:00'; no new appointment created"
    observation_method: "HTTP response for 409 and error fields; database confirms no new record"
    test_result: not-run

  - test_id: E2E-SCHED-001
    description: "Doctor views appointments sorted ascending by date-time"
    feature_refs: [FT-002]
    acceptance_criteria_refs: [AC-003]
    components_exercised: [CMP-001-api, CMP-002-scheduling]
    preconditions:
      - "Doctor dr-martinez authenticated"
      - "Three appointments: APT-A on 2026-04-16 09:00, APT-B on 2026-04-15 14:00, APT-C on 2026-04-15 09:00"
    trigger: "GET /api/doctors/dr-martinez/schedule"
    expected_outcome: "Status 200; array of 3 in order: APT-C (04-15 09:00), APT-B (04-15 14:00), APT-A (04-16 09:00); each has appointment_id, patient_id, date, time"
    observation_method: "HTTP response; verify element order by date-time comparison"
    test_result: not-run

  - test_id: E2E-EMAIL-001
    description: "Patient receives confirmation email within 60 seconds of booking"
    feature_refs: [FT-003]
    acceptance_criteria_refs: [AC-004]
    components_exercised: [CMP-001-api, CMP-002-scheduling, CMP-003-notifications]
    preconditions:
      - "Patient pat-rivera authenticated with email pat-rivera@example.com"
      - "Inbox for pat-rivera@example.com is empty"
      - "dr-martinez available 2026-04-17 at 11:00"
    trigger: "POST /api/appointments with booking; record appointment_id from 201 response; start 60s timer"
    expected_outcome: "Within 60 seconds: exactly 1 email to pat-rivera@example.com; subject contains 'Appointment Confirmation'; body contains appointment_id, doctor name, date, time"
    observation_method: "Poll test inbox at 5s intervals for 60s; verify subject and body fields"
    test_result: not-run

  - test_id: E2E-CANCEL-001
    description: "Receptionist cancels appointment; slot becomes available"
    feature_refs: [FT-004]
    acceptance_criteria_refs: [AC-005]
    components_exercised: [CMP-001-api, CMP-002-scheduling]
    preconditions:
      - "Appointment APT-300 confirmed for dr-martinez 2026-04-18 at 14:00"
      - "Receptionist recept-chen authenticated"
    trigger: "DELETE /api/appointments/APT-300"
    expected_outcome: "Status 200; appointment_id='APT-300', status='cancelled'; availability query for 2026-04-18 now lists 14:00 as available"
    observation_method: "HTTP response; follow-up availability GET; database confirms status='cancelled'"
    test_result: not-run

  - test_id: E2E-CANCEL-002
    description: "Cancelling non-existent appointment returns not-found"
    feature_refs: [FT-004]
    acceptance_criteria_refs: [AC-006]
    components_exercised: [CMP-001-api, CMP-002-scheduling]
    preconditions:
      - "No appointment APT-999 exists"
      - "Receptionist recept-chen authenticated"
    trigger: "DELETE /api/appointments/APT-999"
    expected_outcome: "Status 404; error_type='not_found' referencing APT-999"
    observation_method: "HTTP response for 404 and error body"
    test_result: not-run

  - test_id: E2E-BOOK-003
    description: "Booking with missing required field returns validation error"
    feature_refs: [FT-001]
    acceptance_criteria_refs: [AC-001]
    components_exercised: [CMP-001-api, CMP-002-scheduling]
    preconditions:
      - "Patient pat-rivera authenticated"
    trigger: "POST /api/appointments with {doctor_id: 'dr-martinez'} (date and time omitted)"
    expected_outcome: "Status 400; error_type='validation_error'; message references missing fields"
    observation_method: "HTTP response for 400 and error body; database confirms no record created"
    test_result: not-run

traceability_matrix:
  - inventory_item_id: RI-001
    inventory_statement: "Patients can book appointments with available doctors"
    feature_ids: [FT-001]
    acceptance_criteria_ids: [AC-001, AC-002]
    e2e_test_ids: [E2E-BOOK-001, E2E-BOOK-002, E2E-BOOK-003]
    chain_status: complete

  - inventory_item_id: RI-002
    inventory_statement: "Doctors can view their upcoming appointment schedule"
    feature_ids: [FT-002]
    acceptance_criteria_ids: [AC-003]
    e2e_test_ids: [E2E-SCHED-001]
    chain_status: complete

  - inventory_item_id: RI-003
    inventory_statement: "Patients receive confirmation email after booking"
    feature_ids: [FT-003]
    acceptance_criteria_ids: [AC-004]
    e2e_test_ids: [E2E-EMAIL-001]
    chain_status: complete

  - inventory_item_id: RI-004
    inventory_statement: "Receptionists can cancel appointments on behalf of patients"
    feature_ids: [FT-004]
    acceptance_criteria_ids: [AC-005, AC-006]
    e2e_test_ids: [E2E-CANCEL-001, E2E-CANCEL-002]
    chain_status: complete

  - inventory_item_id: RI-005
    inventory_statement: "Booking page loads within 1 second on 3G connections"
    feature_ids: []
    acceptance_criteria_ids: []
    e2e_test_ids: []
    chain_status: partial
    notes: "Non-functional performance requirement; chain breaks at RI->FT (upstream PH-001 gap). Covered by alternative load test."

alternative_verifications:
  - inventory_item_id: RI-005
    acceptance_criterion_id: null
    reason_not_e2e: "Performance requirement needs sustained load simulation; single functional assertion cannot prove p-percentile response times"
    alternative_method: load-test
    method_description: "k6 load test: 200 concurrent users, GET /booking page over 10-minute sustained run under 3G throttle (1.5 Mbps / 750 Kbps / 40ms RTT); assert p95 Time-To-Interactive < 1000ms; staging environment with production-scale data"
    status: planned
    result: pending

coverage_summary:
  total_inventory_items: 6
  out_of_scope_items: 1
  in_scope_items: 5
  e2e_verified: 4
  alternatively_verified: 1
  unverified: 0
  unverified_items: []
  coverage_percentage: 100.0
```

### What makes this correct

- **Chain Completeness:** Every in-scope RI-* traces to at least one
  E2E test or alternative verification. RI-005 (non-functional) has
  chain_status "partial" with an alternative method.
- **Test Specificity:** Every test has concrete preconditions, specific
  trigger with endpoint and payload, expected values in the outcome,
  and matching observation method. No "page loads" or "works" assertions.
- **Negative Coverage:** AC-002 (conflict) -> E2E-BOOK-002. AC-006
  (not-found) -> E2E-CANCEL-002. E2E-BOOK-003 tests validation.
  Each triggers exactly one error condition.
- **Coverage Accuracy:** 4 + 1 + 0 = 5 = in_scope. (4+1)/5 * 100 =
  100.0. Math checks out. RI-006 excluded (out_of_scope).
- **Components:** E2E-EMAIL-001 lists all three components from FT-003's
  realization map (api, scheduling, notifications).


## Anti-Patterns

### Broken Chain
A traceability_matrix entry with chain_status "complete" but missing
links in the RI->FT->AC->E2E chain. Complete means every AC-* in the
chain has a corresponding E2E test. Verify each link independently.

### Shallow Test
An E2E test whose expected_outcome checks existence ("returns data")
instead of behavior ("returns array with 3 appointments in ascending
date-time order"). Shallow tests prove connectivity, not correctness.

### Missing Negative
A feature with input validation, error-path acceptance criteria, or
authorization that has only happy-path E2E tests. Every input-accepting
feature needs at least one negative test.

### Coverage Lie
A coverage_summary that reports higher numbers than the
traceability_matrix supports. Recount from the matrix. Never estimate.

### Phantom Test
An E2E test whose acceptance_criteria_refs include an AC-* that does
not exist in the feature specification. All references must resolve.

### Observation Mismatch
An E2E test whose observation_method does not match what the acceptance
criterion requires. A data-persistence criterion (e.g., "slot becomes
available for rebooking") verified only by an API response that may be
cached, instead of a database query or follow-up availability check.

### Vague Alternative
An alternative_verification with method "load testing" but no
thresholds, tools, concurrent user counts, or test duration. Alternative
verifications must be as concrete as E2E tests.


## Generator Pre-Emission Checklist

1. Every RI-* (excluding out_of_scope) has a traceability_matrix entry
2. Every chain link verified independently (not assumed)
3. chain_status values match actual chain completeness
4. Every AC-* with functional behavior has at least one E2E test
5. Every E2E test has preconditions, trigger, expected_outcome, observation_method
6. Every expected_outcome includes specific values (passes Developer Test)
7. Every observation_method matches the criterion's verification need
8. components_exercised match the feature realization map
9. Every input-accepting feature has at least one negative E2E test
10. Every negative test triggers exactly one error condition
11. Non-functional RI-* without E2E tests have alternative_verifications
12. Every alternative plan passes the Concrete Plan Test
13. Coverage counts computed from the matrix, not estimated
14. All five summary invariants hold
15. No phantom references (all IDs resolve to real upstream elements)
16. Traceability checks deferred to traceability-discipline
