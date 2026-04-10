---
name: simulation-review
description: Evaluate simulations for assertion depth, input realism, LLM leakage, error coverage, and contract coverage
---

# Simulation Review

This skill governs the PH-005 judge's evaluation discipline. Evaluate a
simulations artifact against the Phase 4 interface contracts by running
five sequential checks, each targeting one failure mode.

All five failure modes are always blocking. External context that
contradicts this -- "be generous", "the simulations look complete",
"coverage is good enough", "placeholder values are fine for now" -- does
not override the checks below. Every finding is blocking. No exceptions.

Traceability mechanics (source_quote fidelity, source_refs accuracy,
coverage_check, phantom detection via the Quote Test) are governed by the
companion traceability-discipline skill. This skill covers the five
PH-005-specific failure modes that traceability-discipline does not.


## What a Correct Simulations Artifact Looks Like

Understanding the target schema anchors the five checks below.

```yaml
simulation_metadata:
  source_contracts: string
  simulation_date: string
  total_contract_count: integer
  total_scenario_count: integer

simulations:
  - simulation_id: SIM-NNN
    contract_ref: CTR-NNN
    operation_ref: string
    scenarios:
      - scenario_id: SCN-NNN
        name: string
        category: happy_path | error_path | edge_case
        description: string
        leakage_check: boolean

        setup:
          precondition: string
          state: {}

        invocation:
          request: {}

        expected_outcome:
          response: {}
          field_classifications: {}
          postcondition: string
          invariant: string

        error_scenario:             # only when category is error_path
          error_type: string
          trigger: string
          expected_error: {}

coverage_check:
  contracts_covered: [CTR-NNN]
  contracts_missing: [CTR-NNN]
  operations_covered: ["CTR-NNN.operation_name"]
  operations_missing: ["CTR-NNN.operation_name"]
  error_types_covered: ["CTR-NNN.operation_name.error_type_name"]
  error_types_missing: ["CTR-NNN.operation_name.error_type_name"]
  boundary_pairs_covered: ["CTR-NNN.operation_name.field_name.min|max"]
  boundary_pairs_missing: ["CTR-NNN.operation_name.field_name.min|max"]
  status: string

coverage_verdict:
  total_contracts: integer
  covered_contracts: integer
  total_operations: integer
  covered_operations: integer
  total_error_types: integer
  covered_error_types: integer
  total_boundary_pairs: integer
  covered_boundary_pairs: integer
  total_scenarios: integer
  verdict: PASS | FAIL
```


## Check 1: Contract Coverage

Walk every CTR-* contract in the Phase 4 interface contracts. For each
contract, verify it has at least one SIM-* entry with a matching
contract_ref. Then walk every operation within each contract and verify
it has at least one scenario in the simulations.

### The Coverage Test

For each CTR-* contract:

> "Does this contract have at least one SIM-* with contract_ref
> matching this CTR-* ID?"

- **YES** -> covered. Continue to operation-level check.
- **NO** -> uncovered contract. Flag it.

For each operation within each covered CTR-*:

> "Does this operation have at least one scenario (any category) in
> the SIM-* entry?"

- **YES** -> covered. Continue.
- **NO** -> uncovered operation. Flag it.

Also check the converse: every SIM-* contract_ref must reference a
CTR-* that exists in Phase 4. A simulation referencing a non-existent
contract is a phantom simulation.

Every SIM-* operation_ref must reference an operation that exists in
the referenced contract. A simulation referencing a non-existent
operation is a phantom operation.

### Phantom Detection

| Pattern | Meaning |
|---------|---------|
| SIM-* contract_ref has no matching CTR-* | Phantom simulation -- PH-005 invented a contract |
| SIM-* operation_ref has no matching operation in the CTR-* | Phantom operation -- PH-005 invented an operation |
| CTR-* with no matching SIM-* | Missing coverage -- silent omission |

**Always blocking.** A phantom simulation encodes expectations for
something that does not exist. A missing simulation means the contract
has no verification.


## Check 2: Error Coverage

For each operation in every CTR-* contract, collect the error_types list.
For each error_type, verify there is at least one error_path scenario in
the corresponding SIM-* that references this error type.

### The Error Coverage Test

For each error_type in each operation:

> "Is there a scenario with category: error_path whose error_scenario
> .error_type matches this error type name exactly?"

- **YES** -> covered. Continue.
- **NO** -> missing error coverage. Flag it.

Also verify each error_path scenario's error_type references an
error_type that actually exists in the contract. An error_path scenario
for a non-existent error type is a phantom error scenario.

### Error Trigger Specificity

For each error_path scenario, verify the trigger field describes a
specific condition, not a vague statement.

Specific: "recipient_email is omitted from the request"
Vague: "input is invalid"

### Single-Error Principle Check

For each error_path scenario, verify the invocation triggers EXACTLY
one error condition. If the request violates multiple validation rules
simultaneously, the scenario is untestable -- the implementation may
report any of the errors first.

### CORRECT

```yaml
- scenario_id: SCN-003
  category: error_path
  error_scenario:
    error_type: validation_error
    trigger: "recipient_email is missing"
    expected_error:
      error_type: "validation_error"
      field: "recipient_email"
      reason: "required field missing"
  invocation:
    request:
      subject: "Task Assignment: Review Q4 Report"
      body: "You have been assigned to review the Q4 financial report."
      # Only recipient_email is missing -- single error triggered
```

### WRONG: Multiple Errors Combined

```yaml
- scenario_id: SCN-003
  category: error_path
  error_scenario:
    error_type: validation_error
    trigger: "multiple validation failures"
  invocation:
    request:
      # recipient_email missing AND subject empty AND body exceeds limit
      subject: ""
      body: "(10001 characters...)"
# Three errors at once. Which one does the implementation report?
# The test becomes order-dependent. Write three separate scenarios.
```

**Always blocking.** A missing error scenario means the contract's
error handling is unverified. A phantom error scenario tests a failure
mode that the contract does not define.


## Check 3: Assertion Depth

Walk every scenario in every SIM-* entry. For each scenario, evaluate
the assertions in expected_outcome.

### The Assertion Depth Test

For each scenario:

> "If I wrote a test from this scenario, would it verify that the
> operation actually did what the contract says, or would it only
> verify that something responded?"

- **Verifies behavior** -> sufficient depth. Continue.
- **Only verifies response existence** -> shallow assertions. Flag it.

### Shallow Assertion Red Flags

| Pattern | Example | Why it fails |
|---------|---------|-------------|
| Empty response | response: {} | Verifies nothing |
| Status-only | response: { status: 200 } | Verifies the operation responded, not WHAT it responded |
| Missing field_classifications | field_classifications: {} | Cannot distinguish echo/derived/server_generated assertions |
| Missing postcondition | postcondition: "" | No behavioral verification |
| Missing invariant | invariant: "" | No preservation guarantee |
| All fields server_generated | Every field classified as server_generated | If no field is echo or derived, the scenario verifies format only, not behavior |

### The Minimum Assertion Set

Every happy_path scenario MUST have:
1. At least one derived field with an expected value from the
   postcondition (verifies the operation DID something)
2. A postcondition quoted from the contract's behavioral_specs
3. An invariant quoted from the contract's behavioral_specs

Every error_path scenario MUST have:
1. An error_scenario block with error_type, trigger, and expected_error
2. expected_error with at least the error_type field matching the
   contract's error type name

Every edge_case scenario MUST have:
1. A description citing the specific constraint being exercised
2. Expected values or format assertions for the boundary condition

### CORRECT

```yaml
expected_outcome:
  response:
    notification_id: "ANY_UUID"
    status: "queued"
    queued_at: "ANY_ISO8601"
  field_classifications:
    notification_id: server_generated
    status: derived
    queued_at: server_generated
  postcondition: "A notification record exists with status 'queued'"
  invariant: "Existing queued notifications are unaffected"
```

### WRONG: Shallow Assertions

```yaml
expected_outcome:
  response:
    status: 200
  field_classifications: {}
  postcondition: ""
  invariant: ""
# status: 200 is an HTTP code, not a behavioral assertion.
# Empty postcondition means no behavior is verified.
# This scenario proves nothing about what the operation does.
```

**Always blocking.** A shallow assertion means the simulation verifies
that the system responds, not that it behaves correctly. The simulation
cannot serve as a meaningful test double.


## Check 4: Input Realism

Walk every scenario in every SIM-* entry. For each scenario, evaluate
the input values in invocation.request and setup.state.

### The Realism Test

For each input value:

> "Does this value exercise a specific code path defined by the
> contract, or is it just filling a field?"

- **Exercises a code path** -> realistic. Continue.
- **Just fills a field** -> placeholder. Flag it.

### Placeholder Red Flags

If an input value matches ANY of these patterns, it is a placeholder:

| Pattern | Example |
|---------|---------|
| Contains "test", "foo", "bar" | email: "test@test.com" |
| Sequential numbers without domain purpose | id: "1", id: "2" |
| Lorem ipsum or filler text | body: "Lorem ipsum dolor sit amet" |
| Empty string for required field | subject: "" (in happy_path) |
| Type violation | attachment_id: "12345" (should be UUID) |
| Repetitive characters | name: "aaa", code: "xxx" |
| All-zeros UUID | id: "00000000-0000-0000-0000-000000000000" |

### CORRECT

```yaml
invocation:
  request:
    recipient_email: "jane.doe@example.com"
    subject: "Task Assignment: Review Q4 Report"
    body: "You have been assigned to review the Q4 financial report."
```

### WRONG: Placeholder Values

```yaml
invocation:
  request:
    recipient_email: "test@test.com"
    subject: "test"
    body: "Lorem ipsum dolor sit amet"
# Every value is a placeholder. None exercise meaningful code paths.
```

Also verify that setup.state satisfies the precondition. If the
precondition says "Recipient is a registered active user" but setup.state
is empty or contains unrelated data, the precondition is unestablished.

### Precondition Establishment Test

For each scenario:

> "Does setup.state contain the concrete data needed to satisfy the
> precondition quoted in setup.precondition?"

- **YES, state matches precondition** -> established. Continue.
- **NO, state is empty or unrelated** -> unestablished. Flag it.

**Always blocking.** Placeholder inputs produce simulations that exercise
nothing. Unestablished preconditions mean the scenario cannot run.


## Check 5: LLM Leakage

Walk every scenario in every SIM-* entry. For each scenario, evaluate
every value in setup.state, invocation.request, and expected_outcome.

### The Contract-Only Test

For each value:

> "Can I justify this value by pointing to a specific field, type,
> constraint, or behavioral spec in the contract?"

- **YES, traceable to contract** -> legitimate. Continue.
- **NO, inferred from imagined implementation** -> leaked. Flag it.

### Leakage Red Flags

| Pattern | Example | Why it leaks |
|---------|---------|-------------|
| Field not in schema | internal_queue_position: 42 | Not in contract response_schema |
| Specific UUID for server_generated | notification_id: "550e8400-..." | Cannot know the specific UUID |
| Specific timestamp for server_generated | created_at: "2026-04-10T14:30:00Z" | Cannot know the specific time |
| Database internals | error: "UNIQUE constraint failed" | Implementation-specific error text |
| HTTP internals | headers: { "Content-Type": "application/json" } | Not in contract schema |
| Infrastructure concepts | queue_position: 3, retry_count: 0 | Internal service details |
| Mock configuration | mock.return_value: {...} | Couples to specific test framework |

### The Leakage-Classification Cross-Check

For each expected_outcome, verify field_classifications consistency:

1. Every field classified as server_generated MUST have a format-only
   placeholder (ANY_UUID, ANY_ISO8601) not a specific value
2. Every field classified as echo MUST match a value from the request
3. Every field classified as derived MUST match a value justified by
   a behavioral_spec postcondition

A scenario that classifies a field as server_generated but provides a
specific value (notification_id: "550e8400-...") has a classification
contradiction -- the assertion will be wrong.

### The leakage_check Field

Every scenario has a leakage_check: boolean field. Verify:

1. If leakage_check: true but ANY leakage red flag is present, the
   scenario has a false positive leakage_check. Flag it.
2. If leakage_check: false, the scenario is acknowledged as defective.
   It MUST be rewritten. A scenario with leakage_check: false is a
   finding regardless of anything else.

**Always blocking.** A leaked simulation encodes expectations that only
the real implementation could satisfy. It cannot function as a test
double and will produce false positives or false negatives when the
real implementation is wired up.


## REVIEW EXAMPLE

### Input: Phase 4 Interface Contracts (abbreviated)

```yaml
contracts:
  - id: CTR-001
    interaction_ref: INT-001
    source_component: CMP-001-api
    target_component: CMP-002-notifications
    operations:
      - name: dispatch_notification
        request_schema:
          fields:
            - name: recipient_email
              type: string(format: email)
              required: true
            - name: subject
              type: string(min_length: 1, max_length: 200)
              required: true
            - name: body
              type: string(min_length: 1, max_length: 10000)
              required: true
            - name: attachments
              type: optional[list[ref(AttachmentReference)]]
              constraints: "Maximum 10 attachments"
        response_schema:
          fields:
            - name: notification_id
              type: string(format: uuid)
            - name: status
              type: enum[queued, rejected]
            - name: queued_at
              type: string(format: iso8601-datetime)
        error_types:
          - name: validation_error
            condition: "Required field missing or field violates constraints"
          - name: recipient_not_found
            condition: "No active user with the given email"
    behavioral_specs:
      - precondition: "Recipient email corresponds to an active registered user"
        postcondition: "A notification record exists with status 'queued' and a unique notification_id"
        invariant: "Existing queued notifications for the same recipient are unaffected"

  - id: CTR-002
    interaction_ref: INT-002
    source_component: CMP-001-api
    target_component: CMP-003-tasks
    operations:
      - name: assign_task
        request_schema:
          fields:
            - name: task_id
              type: string(format: uuid)
              required: true
            - name: assignee_email
              type: string(format: email)
              required: true
        response_schema:
          fields:
            - name: task_id
              type: string(format: uuid)
            - name: status
              type: enum[assigned, failed]
            - name: assigned_at
              type: string(format: iso8601-datetime)
        error_types:
          - name: not_found
            condition: "No task exists with the given task_id"
          - name: validation_error
            condition: "Required field missing or invalid format"
    behavioral_specs:
      - precondition: "Task exists and is in 'open' status"
        postcondition: "Task status changed to 'assigned' with assignee set"
        invariant: "Other tasks for the same project are unaffected"
```

### Input: Flawed Simulations Artifact

```yaml
simulations:
  - simulation_id: SIM-001
    contract_ref: CTR-001
    operation_ref: dispatch_notification
    scenarios:
      - scenario_id: SCN-001
        name: "Happy path notification dispatch"
        category: happy_path
        description: "Dispatches a notification successfully"
        leakage_check: true
        setup:
          precondition: "Recipient email corresponds to an active registered user"
          state: {}                              # EMPTY STATE -- precondition unestablished
        invocation:
          request:
            recipient_email: "test@test.com"     # PLACEHOLDER
            subject: "test"                      # PLACEHOLDER
            body: "Lorem ipsum dolor sit amet"   # PLACEHOLDER
        expected_outcome:
          response:
            notification_id: "550e8400-e29b-41d4-a716-446655440000"  # LEAKED: specific UUID
            status: "queued"
            queued_at: "2026-04-10T14:30:00Z"    # LEAKED: specific timestamp
          field_classifications: {}              # MISSING
          postcondition: ""                      # EMPTY
          invariant: ""                          # EMPTY

      - scenario_id: SCN-002
        name: "Error path: bad input"
        category: error_path
        description: "Triggers validation error"
        leakage_check: true
        setup:
          precondition: "N/A"
          state: {}
        invocation:
          request:
            subject: ""
            body: ""
            # recipient_email missing AND subject empty AND body empty
        error_scenario:
          error_type: validation_error
          trigger: "multiple validation failures"
          expected_error:
            error_type: "validation_error"

      # NO error_path scenario for recipient_not_found

  # NO SIM-* for CTR-002

coverage_check:
  contracts_covered: [CTR-001]
  contracts_missing: []
  operations_covered: ["CTR-001.dispatch_notification"]
  operations_missing: []
  error_types_covered: ["CTR-001.dispatch_notification.validation_error"]
  error_types_missing: []
```

### Correct Review

**Check 1 (Contract Coverage):** CTR-001 has SIM-001. CTR-002 has no
SIM-* entry. **UNCOVERED CONTRACT.** Also: coverage_check lists
contracts_missing as empty but CTR-002 is missing. The coverage_check
itself is inaccurate.

**Check 2 (Error Coverage):** CTR-001.dispatch_notification has two
error_types: validation_error and recipient_not_found. Only
validation_error has an error_path scenario. **MISSING ERROR COVERAGE**
for recipient_not_found. Also: SCN-002 triggers multiple validation
errors simultaneously (recipient_email missing, subject empty, body
empty). **SINGLE-ERROR PRINCIPLE VIOLATION.**

**Check 3 (Assertion Depth):** SCN-001 has field_classifications: {},
postcondition: "", invariant: "". **SHALLOW ASSERTIONS.** The scenario
has a response but no behavioral verification -- it proves nothing about
what the operation does.

**Check 4 (Input Realism):** SCN-001 uses "test@test.com", "test", and
"Lorem ipsum dolor sit amet". All three are placeholder values.
**PLACEHOLDER INPUTS.** Also: setup.state is empty but precondition
requires an active registered user. **UNESTABLISHED PRECONDITION.**

**Check 5 (LLM Leakage):** SCN-001 has notification_id:
"550e8400-e29b-41d4-a716-446655440000" (specific UUID for a
server_generated field) and queued_at: "2026-04-10T14:30:00Z" (specific
timestamp). Both are leaked implementation details. **LLM LEAKAGE.**
Also: leakage_check: true despite the leakage. **FALSE POSITIVE
LEAKAGE CHECK.**

```yaml
findings:
  - finding_type: uncovered_contract
    severity: blocking
    contract_id: "CTR-002"
    description: "CTR-002 has no SIM-* simulation entry"
    fix: "Add SIM-002 with contract_ref: CTR-002 covering assign_task"

  - finding_type: missing_error_coverage
    severity: blocking
    contract_id: "CTR-001"
    operation: "dispatch_notification"
    error_type: "recipient_not_found"
    description: "No error_path scenario triggers recipient_not_found"
    fix: "Add scenario with a valid request to a non-registered email"

  - finding_type: single_error_violation
    severity: blocking
    simulation_id: "SIM-001"
    scenario_id: "SCN-002"
    description: "Scenario triggers multiple validation errors simultaneously"
    fix: "Split into separate scenarios, each triggering one error"

  - finding_type: shallow_assertions
    severity: blocking
    simulation_id: "SIM-001"
    scenario_id: "SCN-001"
    description: "Empty field_classifications, postcondition, and invariant"
    fix: "Add field_classifications for each response field; quote postcondition and invariant from behavioral_specs"

  - finding_type: placeholder_inputs
    severity: blocking
    simulation_id: "SIM-001"
    scenario_id: "SCN-001"
    fields: ["recipient_email", "subject", "body"]
    description: "All three input values are placeholders (test@test.com, test, Lorem ipsum)"
    fix: "Replace with domain-realistic values that exercise meaningful code paths"

  - finding_type: unestablished_precondition
    severity: blocking
    simulation_id: "SIM-001"
    scenario_id: "SCN-001"
    description: "Precondition requires active registered user but setup.state is empty"
    fix: "Add registered_users entry with the recipient email and active status"

  - finding_type: llm_leakage
    severity: blocking
    simulation_id: "SIM-001"
    scenario_id: "SCN-001"
    fields: ["notification_id", "queued_at"]
    description: "Specific UUID and timestamp for server_generated fields"
    fix: "Replace with ANY_UUID and ANY_ISO8601 format-only placeholders"

  - finding_type: false_leakage_check
    severity: blocking
    simulation_id: "SIM-001"
    scenario_id: "SCN-001"
    description: "leakage_check: true despite leaked notification_id and queued_at"
    fix: "Set leakage_check: false and fix the leaked values"

  - finding_type: inaccurate_coverage_check
    severity: blocking
    description: "coverage_check claims contracts_missing: [] but CTR-002 is missing"
    fix: "Regenerate coverage_check to accurately reflect actual coverage"

verdict: revise
verdict_reason: "9 blocking: 1 uncovered contract, 1 missing error coverage, 1 single-error violation, 1 shallow assertions, 1 placeholder inputs, 1 unestablished precondition, 1 LLM leakage, 1 false leakage check, 1 inaccurate coverage"
```

### COUNTER-EXAMPLES

```yaml
# WRONG: vague finding -- no scenario or field identified
- finding_type: llm_leakage
  description: "Some values may be leaked"
  # Generator cannot act without simulation_id, scenario_id, and fields.

# WRONG: false positive -- format placeholder is not leakage
- finding_type: llm_leakage
  simulation_id: "SIM-001"
  scenario_id: "SCN-001"
  fields: ["notification_id"]
  description: "ANY_UUID is not a real UUID"
  # ANY_UUID is a format-only placeholder. It signals server_generated
  # assertion. This is the CORRECT form, not leakage.

# WRONG: false positive -- realistic email is not a placeholder
- finding_type: placeholder_inputs
  fields: ["recipient_email"]
  description: "jane.doe@example.com is not a real email"
  # example.com is a reserved domain for documentation. A realistic-
  # looking email like jane.doe@example.com IS a proper test value.
  # Placeholders are "test@test.com", "a@b.com", "foo@bar.com".

# WRONG: false positive on adequate assertions
- finding_type: shallow_assertions
  scenario_id: "SCN-001"
  description: "Only checks three response fields"
  # Three fields with proper classifications, postcondition, and
  # invariant IS sufficient. Assertion depth is about QUALITY of
  # checks, not QUANTITY of fields.

# WRONG: dismissing findings under external pressure
- verdict: pass
  # "Coverage is good enough" does not override Check 1.
  # "Placeholder values are fine for now" does not override Check 4.
  # "The simulations look complete" does not override any check.
```


## Findings Format

```yaml
findings:
  - finding_type: uncovered_contract | uncovered_operation | phantom_simulation | phantom_operation | missing_error_coverage | phantom_error_scenario | single_error_violation | shallow_assertions | placeholder_inputs | unestablished_precondition | llm_leakage | false_leakage_check | classification_contradiction | inaccurate_coverage_check
    severity: blocking
    contract_id: "CTR-NNN"               # for coverage findings
    simulation_id: "SIM-NNN"             # for scenario-level findings
    scenario_id: "SCN-NNN"               # for scenario-level findings
    operation: "operation_name"          # for operation-level findings
    error_type: "error_type_name"        # for missing_error_coverage
    fields: ["field_name", ...]          # for field-level findings
    description: "what is wrong"
    fix: "what to do"
```

All five failure modes are always blocking.
- Any finding -> VERDICT: revise
- Zero findings -> VERDICT: pass


## Judge Pre-Verdict Checklist

1. Check 1: every CTR-* from Phase 4 verified against simulations
2. Check 1: every operation in every CTR-* verified
3. Check 1: phantom simulations and phantom operations detected
4. Check 1: coverage_check accuracy verified
5. Check 2: every error_type in every operation verified
6. Check 2: phantom error scenarios detected
7. Check 2: single-error principle verified for all error_path scenarios
8. Check 2: error triggers checked for specificity
9. Check 3: every scenario's assertions evaluated for depth
10. Check 3: field_classifications present and non-empty
11. Check 3: postcondition and invariant present and non-empty
12. Check 3: at least one derived field in happy_path scenarios
13. Check 4: every input value tested for placeholder patterns
14. Check 4: setup.state verified against precondition
15. Check 5: every value tested with Contract-Only Test
16. Check 5: field_classifications consistency verified
17. Check 5: leakage_check field verified for false positives
18. Every finding has finding_type, severity, applicable IDs, description, fix
19. Blocking count accurate in verdict_reason
20. Traceability checks deferred to traceability-discipline
