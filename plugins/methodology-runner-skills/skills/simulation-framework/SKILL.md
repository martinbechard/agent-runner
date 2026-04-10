---
name: simulation-framework
description: Write executable simulations that exercise contracts with happy-path, error-path, and edge-case scenarios — usable as test doubles before implementations exist
---

# Simulation Framework

This skill governs the simulation-writing discipline for PH-005
(Simulations). Its scope is the judgment calls that
generation_instructions do not cover: how to derive scenarios from
contracts, how to ensure inputs are realistic without leaking
implementation details, how to classify expected outputs by
derivability, and how to structure simulations as replaceable test
doubles.

This skill is the FLOOR, not the ceiling. Stack-specific simulation
idioms -- pytest fixtures, Jest mocks, Go table-driven tests,
integration harness conventions -- come from companion skills loaded
by the Skill-Selector based on the component's expected_expertise
entries. This skill ensures every simulation addresses the four
universal disciplines regardless of technology.

Traceability mechanics -- source_refs, source_quote, coverage_check,
coverage_verdict, inherited_assumptions, and the Quote Test -- are
governed by the companion traceability-discipline skill loaded
alongside this one. This skill focuses on HOW to write simulations
and WHAT to declare in the simulations artifact.


## Output Schema: simulations.yaml

Understanding the target schema drives every judgment call below.

```yaml
simulation_metadata:
  source_contracts: string         # path to interface-contracts.yaml
  simulation_date: string          # ISO 8601
  total_contract_count: integer
  total_scenario_count: integer

simulations:
  - simulation_id: SIM-NNN
    contract_ref: CTR-NNN           # from interface contracts -- never invent
    operation_ref: string           # operation name within the contract
    scenarios:
      - scenario_id: SCN-NNN
        name: string                # human-readable scenario name
        category: happy_path | error_path | edge_case
        description: string         # one sentence: what this scenario exercises
        leakage_check: boolean      # true = every value derivable from contract only

        setup:                      # precondition establishment
          precondition: string      # from behavioral_specs -- quote it
          state: {}                 # concrete key-value pairs satisfying precondition

        invocation:                 # the request under test
          request: {}               # concrete field values matching request_schema

        expected_outcome:
          response: {}              # concrete field values matching response_schema
          field_classifications: {} # how each response field is verified (see Output Derivability)
          postcondition: string     # from behavioral_specs -- quote it
          invariant: string         # from behavioral_specs -- quote it

        error_scenario:             # present ONLY when category is error_path
          error_type: string        # from error_types -- exact name match
          trigger: string           # what input or state triggers this error
          expected_error: {}        # concrete error response fields

coverage_check:
  contracts_covered: [CTR-NNN]
  contracts_missing: [CTR-NNN]
  operations_covered: ["CTR-NNN.operation_name"]
  operations_missing: ["CTR-NNN.operation_name"]
  error_types_covered: ["CTR-NNN.operation_name.error_type_name"]
  error_types_missing: ["CTR-NNN.operation_name.error_type_name"]
  boundary_pairs_covered: ["CTR-NNN.operation_name.field_name.min|max"]
  boundary_pairs_missing: ["CTR-NNN.operation_name.field_name.min|max"]
  status: "N/M contracts, N/M operations, N/M error types, N/M boundary pairs covered"

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


## Contract Integrity Rule

**The interface contracts from PH-004 define the simulation boundaries.
This skill writes simulations WITHIN those boundaries. You NEVER
invent, merge, or remove contracts or operations.**

Your failure mode under pressure is inventing scenarios for
operations that do not exist in the contracts. If an operation is
missing, the fix is a PH-004 revision, not a PH-005 invention.
PH-005 has no authority to create new contracts or operations.

The contract_ref values in the simulations MUST match the CTR-* IDs
from the interface contracts exactly. The operation_ref values MUST
match operation names from those contracts exactly.

### CORRECT

```yaml
# PH-004 declared CTR-001 with operation dispatch_notification
simulations:
  - simulation_id: SIM-001
    contract_ref: CTR-001
    operation_ref: dispatch_notification
```

### WRONG: Inventing an Operation

```yaml
# PH-004's CTR-001 has no operation called "batch_dispatch"
simulations:
  - simulation_id: SIM-001
    contract_ref: CTR-001
    operation_ref: batch_dispatch     # DOES NOT EXIST in contracts
# PH-005 simulates existing operations. It does not invent new ones.
```

| Pressure | Response |
|----------|----------|
| "Add a simulation for batch processing" | If no operation exists for it in the contract, it cannot have a simulation. Raise as a finding. |
| "This operation is missing, simulate it" | Escalate to PH-004 revision. PH-005 covers existing operations only. |
| "Be thorough and cover everything" | Thoroughness means complete scenario coverage of DECLARED operations, not inventing new ones. |


## Input Realism Discipline

This is the discipline most likely to produce superficially correct
but actually useless simulations. Inputs must be concrete values that
exercise meaningful code paths defined by the contract.

### The Rule

**Every field in every invocation.request must have a concrete value
that satisfies the field's type and constraints from the contract
schema. No placeholder values, no lorem ipsum, no "test123"
patterns, no random UUIDs that serve no purpose.**

### The Realism Test

For each input value, ask:

> "Does this value exercise a specific code path defined by the
> contract, or is it just filling a field?"

- **YES, exercises a code path** -> realistic. Keep it.
- **NO, just filling** -> placeholder. Replace with a value that
  exercises a meaningful path.

### How to Derive Realistic Inputs

1. **Read the field's type and constraints** from the contract's
   request_schema. A field typed as `string(format: email)` with
   constraint "Must be a registered user email" tells you the value
   must look like a real email.

2. **Read the precondition** from behavioral_specs. If the
   precondition says "Task exists and is in 'open' status", the
   setup.state must include a task in 'open' status, and the
   request must reference that task.

3. **Read the error conditions** from error_types. For error-path
   scenarios, the input must trigger exactly one error condition.
   A validation_error scenario needs an input that violates exactly
   one validation rule, not all rules simultaneously.

### CORRECT

```yaml
invocation:
  request:
    recipient_email: "jane.doe@example.com"
    subject: "Task Assignment: Review Q4 Report"
    body: "You have been assigned to review the Q4 financial report. Due date: 2026-05-15."
    attachments:
      - attachment_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        filename: "q4-report.pdf"
        mime_type: "application/pdf"
```

### WRONG: Placeholder Values

```yaml
invocation:
  request:
    recipient_email: "test@test.com"         # PLACEHOLDER: not realistic
    subject: "test"                           # PLACEHOLDER: exercises nothing
    body: "Lorem ipsum dolor sit amet"        # PLACEHOLDER: meaningless content
    attachments:
      - attachment_id: "12345"               # WRONG TYPE: not a UUID
        filename: "file.txt"                  # PLACEHOLDER: generic
        mime_type: "text"                     # WRONG FORMAT: not a valid MIME type
# Every value is either a placeholder pattern or violates the contract
# schema. None exercise meaningful code paths.
```

### Placeholder Red Flags

If an input value matches ANY of these patterns, it is a placeholder:

- Contains "test", "foo", "bar", "example123", or "placeholder"
- Uses "Lorem ipsum" or similar filler text
- Is a sequential number that serves no domain purpose (1, 2, 3)
- Is an empty string for a required field
- Violates the type constraints in the contract schema
- Uses "aaa", "xxx", or other repetitive characters
- Uses UUIDs that are all zeros or all the same digit

**All of these mean: replace with a domain-realistic value.**

| Pressure | Leaked form | Correct form |
|----------|------------|-------------|
| "Keep it simple" | subject: "test" | subject: "Task Assignment: Review Q4 Report" |
| "Don't overthink inputs" | body: "Lorem ipsum" | body: "You have been assigned to review the Q4 financial report." |
| "Just use any value" | recipient_email: "a@b.com" | recipient_email: "jane.doe@example.com" |
| "Use minimal data" | attachment_id: "1" | attachment_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890" |


## Output Derivability Discipline

Expected outputs must be predictable from the contract alone. This
discipline prevents the single most dangerous failure mode: simulations
that encode knowledge only the real implementation would have.

### The Rule

**Every field in every expected_outcome.response must be classified
into one of three categories. The classification determines HOW to
assert on the field.**

### The Three Output Categories

| Category | Definition | Assertion style | Example |
|----------|-----------|----------------|---------|
| **echo** | Value matches a field in the request | Assert exact equality | request.task_id == response.task_id |
| **server_generated** | Value is created by the server at runtime | Assert format and existence only | response.created_at is ISO8601, response.notification_id is UUID |
| **derived** | Value follows from behavioral spec logic | Assert the specific value per the spec | If precondition is status='open' and postcondition says status='assigned', assert response.status == 'assigned' |

### The Derivability Test

For each expected output field, ask:

> "Can I predict this value from the contract (request schema +
> behavioral specs) without knowing ANY implementation detail?"

- **YES, from the request** -> category: echo
- **YES, from the behavioral spec** -> category: derived
- **NO, only format is predictable** -> category: server_generated
- **NO, not predictable at all** -> the field violates derivability.
  It should not have a concrete expected value. Assert existence only.

### CORRECT

```yaml
expected_outcome:
  response:
    notification_id: "ANY_UUID"
    status: "queued"
    queued_at: "ANY_ISO8601"
  field_classifications:
    notification_id: server_generated   # assert: is valid UUID format
    status: derived                     # assert: equals "queued" per postcondition
    queued_at: server_generated         # assert: is valid ISO8601 datetime
  postcondition: "A notification record exists with status 'queued' and a unique notification_id"
  invariant: "Existing queued notifications for the same recipient are unaffected"
```

### WRONG: Leaked Implementation Details

```yaml
expected_outcome:
  response:
    notification_id: "550e8400-e29b-41d4-a716-446655440000"  # LEAKED: specific UUID
    status: "queued"
    queued_at: "2026-04-10T14:30:00Z"                        # LEAKED: specific timestamp
    internal_queue_position: 42                               # LEAKED: implementation detail
  field_classifications: {}                                   # MISSING: no classifications
# notification_id is server_generated -- you cannot know the specific UUID.
# queued_at is server_generated -- you cannot know the specific time.
# internal_queue_position does not exist in the contract schema.
# Missing field_classifications means the test cannot be written correctly.
```

### WRONG: Asserting Exact Values on Server-Generated Fields

```yaml
# Even if you use "reasonable" values, asserting exact equality on
# server-generated fields makes the simulation brittle and encodes
# knowledge the simulation cannot have.
expected_outcome:
  response:
    notification_id: "550e8400-e29b-41d4-a716-446655440000"
  field_classifications:
    notification_id: server_generated
# Classification says server_generated but response field has a specific
# value. Contradictory. Use "ANY_UUID" or equivalent placeholder that
# signals format-only assertion.
```


## LLM Leakage Prevention Discipline

This is the single most important discipline in this skill and the
one most likely to fail under pressure.

LLMs will invent implementation details and embed them in simulations
as if they were contract-derivable facts. The simulation then encodes
expectations that only the real service could satisfy, making it
useless as a test double.

### The Rule

**Every value in every simulation must be derivable from the contract
alone. If a value requires knowledge of the implementation (database
sequences, internal IDs, specific timestamps, service internals,
queue positions, retry counts), it is leaked knowledge.**

### The Contract-Only Test

For each value in the simulation (setup, invocation, expected_outcome),
ask:

> "Can I justify this value by pointing to a specific field, type,
> constraint, or behavioral spec in the contract?"

- **YES, I can point to the contract** -> legitimate. Keep it.
- **NO, I inferred it from how I imagine the service works** -> leaked.
  Remove it or replace with a format-only assertion.

### Leakage Self-Check

After generating each scenario, perform this cross-cutting
verification before moving to the next scenario:

1. Walk every field in setup.state -- can each key-value pair be
   traced to a behavioral_spec precondition or a schema constraint?
2. Walk every field in invocation.request -- does each value satisfy
   the request_schema type and constraints without importing
   implementation knowledge?
3. Walk every field in expected_outcome.response -- is the field
   in the response_schema? Is the assertion type (exact, format,
   membership) matched to the contract's guarantee level?
4. If the scenario has an error_scenario -- does the error_type
   name exist verbatim in the contract's error_types? Does the
   trigger match the declared condition?

If any check fails, the scenario's leakage_check field MUST be false.
A scenario with leakage_check: false is defective and must be
rewritten before emission.

The leakage_check field is a boolean that the generator MUST assert
for every scenario. Setting leakage_check: true is a declaration
that every value in the scenario has been verified against the
contract. This is not a rubber stamp -- it is an auditable assertion.

### Leakage Categories

| Category | What gets leaked | Example | Fix |
|----------|-----------------|---------|-----|
| **Internal IDs** | Database auto-increment, sequence numbers | notification_id: 42 | notification_id: "ANY_UUID" (server_generated) |
| **Timestamps** | Specific datetime values for server-generated fields | created_at: "2026-04-10T14:30:00Z" | created_at: "ANY_ISO8601" (server_generated) |
| **Queue internals** | Position, priority, routing keys | queue_position: 3 | Remove field (not in contract schema) |
| **Error messages** | Implementation-specific error text | message: "UNIQUE constraint failed" | message: assert non-empty string only |
| **Response headers** | HTTP headers, correlation IDs not in schema | X-Request-Id: "abc" | Remove (not in contract schema) |
| **State details** | Internal state machine transitions | internal_state: "PENDING_ACK" | Remove (not in contract schema) |
| **Retry behavior** | Retry counts, backoff intervals | retry_count: 0 | Remove (not in contract schema) |
| **Schema extras** | Fields present in response but not in response_schema | audit_log_id: "xyz" | Remove (not in contract schema) |

### Leakage Red Flags

If a simulation value matches ANY of these patterns, it is leaked:

- The field does not exist in the contract's response_schema
- The value is a specific UUID, timestamp, or sequence number for a
  server_generated field
- The value references database internals (table names, column names,
  constraint names)
- The value contains implementation-specific error text
- The value assumes a specific internal state not described in
  behavioral_specs
- The value references infrastructure concepts (queues, caches,
  connection pools)

**All of these mean: remove the field or convert to format-only assertion.**

### How Leakage Happens

Your primary failure mode under pressure is writing "realistic"
simulations by imagining what the real service would do and encoding
those imagined behaviors. The more detailed and "helpful" you try to
be, the more you leak.

| Pressure | Leaked form | Correct form |
|----------|------------|-------------|
| "Be realistic" | notification_id: "550e8400-..." | notification_id: "ANY_UUID" |
| "Show what the response looks like" | queued_at: "2026-04-10T14:30:00Z" | queued_at: "ANY_ISO8601" |
| "Be detailed" | internal_queue_position: 42 | (remove -- not in schema) |
| "Be thorough" | error.message: "UNIQUE constraint failed: notifications.recipient_email" | error.error_type: "conflict" (from contract) |
| "Show the full response" | X-Correlation-Id: "corr-123" | (remove -- not in schema) |
| "Include all fields" | retry_after_seconds: 30 | (remove -- not in schema unless contract specifies) |


## Replaceability Discipline

Every simulation scenario is a test double. It runs today against the
simulation and tomorrow against the real implementation. The scenario
structure must support this swap without rewriting the test.

### The Rule

**Every scenario has three parts: setup (establish precondition),
invocation (send request), assertion (verify postcondition +
invariant). The simulation provides the behavior; the test provides
the assertion. When the real implementation replaces the simulation,
only the behavior source changes -- the assertions remain identical.**

### The Replaceability Test

For each scenario, ask:

> "If I replaced the simulation with the real implementation and ran
> this scenario, would the assertions still be valid?"

- **YES** -> replaceable. Keep it.
- **NO** -> the scenario encodes simulation-specific behavior. Fix it.

### What Makes a Scenario Replaceable

1. **Setup uses domain concepts, not mock configuration.** The setup
   says "a task exists in 'open' status" not "mock.returnValue({status: 'open'})".
   The simulation establishes this via its test double; the real
   implementation establishes it via actual setup calls.

2. **Assertions use postcondition language, not response-shape checks.**
   The assertion says "task status is 'assigned'" not "response body
   contains JSON with key 'status'". Postcondition assertions survive
   implementation changes; shape assertions break on serialization changes.

3. **Server-generated fields use format assertions, not value equality.**
   The assertion says "notification_id is a valid UUID" not
   "notification_id equals '550e8400-...'". The simulation and the real
   implementation will produce different UUIDs.

### CORRECT

```yaml
setup:
  precondition: "Recipient email corresponds to an active registered user"
  state:
    registered_users:
      - email: "jane.doe@example.com"
        status: "active"

invocation:
  request:
    recipient_email: "jane.doe@example.com"
    subject: "Task Assignment: Review Q4 Report"
    body: "You have been assigned to review the Q4 financial report."

expected_outcome:
  response:
    notification_id: "ANY_UUID"
    status: "queued"
    queued_at: "ANY_ISO8601"
  field_classifications:
    notification_id: server_generated
    status: derived
    queued_at: server_generated
  postcondition: "A notification record exists with status 'queued' and a unique notification_id"
  invariant: "Existing queued notifications for the same recipient are unaffected"
```

### WRONG: Simulation-Specific Setup

```yaml
setup:
  mock_config:
    notification_service:
      return_value:
        id: "550e8400-e29b-41d4-a716-446655440000"
        status: "queued"
# This setup configures a mock, not a precondition. It cannot run
# against the real implementation. Use domain-level state instead.
```

### WRONG: Implementation-Coupled Assertions

```yaml
expected_outcome:
  response:
    notification_id: "550e8400-e29b-41d4-a716-446655440000"
  assertions:
    - "response.headers['Content-Type'] == 'application/json'"
    - "database.notifications.count() == 1"
    - "mock.notification_service.called_once()"
# HTTP headers, database queries, and mock assertions are all
# implementation-coupled. None survive replacement with a real implementation.
```


## Scenario Generation Procedure

For each CTR-* contract in the interface contracts artifact, walk
these steps in order. Do NOT skip steps. Do NOT jump to a later
contract before finishing the current one.


### Step 1: Map Contract to Simulation Shell

Read the contract's id, name, source_component, and target_component.
Create a SIM-* entry with:
- contract_ref matching the CTR-* ID exactly
- operation_ref matching each operation name exactly

One SIM-* entry per contract. Multiple scenarios within each SIM-*
entry.


### Step 2: Generate Happy-Path Scenarios

For each operation in the contract:

1. Read the request_schema and identify all required fields
2. Read the behavioral_specs for precondition/postcondition pairs
3. Construct a setup.state that satisfies the precondition
4. Construct an invocation.request with concrete values for every
   required field, satisfying all type constraints
5. Construct an expected_outcome.response with:
   - Echo fields: exact values from the request
   - Server-generated fields: format-only placeholders (ANY_UUID, ANY_ISO8601)
   - Derived fields: values per the postcondition logic
6. Classify every response field in field_classifications
7. Quote the postcondition and invariant from the behavioral spec
8. Set leakage_check: true only after verifying every value against
   the Leakage Self-Check

**Every operation MUST have at least one happy-path scenario.**

Apply the four tests at each step:
- Realism Test on every input value (Step 4)
- Derivability Test on every output value (Step 5)
- Contract-Only Test on every value (Steps 3-5)
- Replaceability Test on the complete scenario (Step 7)


### Step 3: Generate Error-Path Scenarios

For each operation, for each error_type in the contract:

1. Read the error_type's name and condition
2. Construct a setup.state and invocation.request that triggers
   EXACTLY this error condition and no other
3. Populate error_scenario with:
   - error_type: exact name from the contract
   - trigger: the specific condition being triggered
   - expected_error: concrete error response fields
4. Set leakage_check: true only after verifying the Leakage Self-Check

**The Single-Error Principle:** Each error-path scenario must trigger
exactly one error condition. Do NOT combine multiple error conditions
into one scenario. A validation_error scenario tests one validation
rule, not all validation rules simultaneously.

### CORRECT: Single Error Triggered

```yaml
- scenario_id: SCN-003
  name: "dispatch_notification fails with missing recipient"
  category: error_path
  description: "Triggers validation_error when recipient_email is omitted"
  leakage_check: true
  setup:
    precondition: "N/A -- validation occurs before precondition check"
    state: {}
  invocation:
    request:
      subject: "Task Assignment: Review Q4 Report"
      body: "You have been assigned to review the Q4 financial report."
      # recipient_email deliberately omitted to trigger validation_error
  error_scenario:
    error_type: validation_error
    trigger: "recipient_email is missing"
    expected_error:
      error_type: "validation_error"
      field: "recipient_email"
      reason: "required field missing"
```

### WRONG: Multiple Errors Combined

```yaml
- scenario_id: SCN-003
  name: "dispatch_notification fails with invalid input"
  category: error_path
  invocation:
    request:
      # recipient_email missing AND subject empty AND body exceeds limit
      subject: ""
      body: "(10001 characters of text...)"
  error_scenario:
    error_type: validation_error
    trigger: "multiple validation failures"
# Three errors at once. Which one does the implementation report first?
# The test becomes order-dependent and untestable.
# Write three separate scenarios, each triggering one error.
```


### Step 4: Generate Edge-Case Scenarios with Boundary Extraction

For each operation, derive edge cases systematically from the
contract's type constraints and behavioral specs. This step uses
the Boundary Extraction sub-discipline to ensure complete coverage.

Edge cases are distinct from error paths. An edge case is a valid
input at the boundary of the contract's constraints. An error path
is an invalid input that triggers a defined error.

#### Boundary Extraction Sub-Discipline

Walk every field in the operation's request_schema. For each field,
examine its type annotation and constraints. Extract boundary pairs
using the rules below. This is a mechanical extraction, not a
creative exercise -- every boundary pair maps to a specific
constraint in the contract.

**Numeric and length bounds (min/max/min_length/max_length):**

For each constraint with numeric bounds, generate:

| Constraint | Valid boundary scenario | Valid boundary scenario | Invalid boundary scenario |
|------------|----------------------|----------------------|--------------------------|
| min_length: N | Value with exactly N characters (valid) | -- | Value with N-1 characters (error, if N > 0) |
| max_length: N | Value with exactly N characters (valid) | -- | Value with N+1 characters (error) |
| min: N | Value exactly equal to N (valid) | -- | Value equal to N-1 (error) |
| max: N | Value exactly equal to N (valid) | -- | Value equal to N+1 (error) |
| min: N, max: M | Value exactly equal to N (valid) | Value exactly equal to M (valid) | Value N-1 (error), Value M+1 (error) |
| min_length: N, max_length: M | Value of exactly N chars (valid) | Value of exactly M chars (valid) | Value of N-1 chars (error), Value of M+1 chars (error) |
| Maximum K items | List with exactly K items (valid) | -- | List with K+1 items (error) |

Note: Invalid boundary scenarios (just below minimum or just above
maximum) may overlap with error-path scenarios from Step 3 when the
boundary violation triggers a declared error_type. When overlap
occurs, the error-path scenario from Step 3 covers the invalid
boundary -- do not duplicate it. Record the coverage linkage in
the coverage_check.

**Enum fields (exhaustive coverage):**

For each enum-typed field in the response_schema or request_schema:
- The happy-path scenario covers one enum value
- Generate one additional edge-case scenario per remaining enum value

For response_schema enums (e.g., status: enum[queued, rejected]):
each enum value represents a different code path that multi-step
scenarios must branch on. These are not optional edge cases -- they
are required for branch coverage.

**Optional fields (presence/absence):**

For each field marked as optional or with type optional[...]:
- One scenario with the field present and populated with valid values
- One scenario with the field absent (omitted from the request)

If the happy-path scenario already covers the "present" case, only
the "absent" scenario is needed as an edge case.

**Format variations (secondary priority):**

For fields with format constraints, consider valid but unusual
format instances:
- format: email -> plus-addressing (user+tag@example.com)
- format: uuid -> valid UUID at version boundary

Format variations are lower priority than numeric boundaries, enum
coverage, and optional field coverage. Include them when they
exercise distinct code paths, not for completeness sake.

#### Boundary Extraction Worked Example

Given this request_schema:

```yaml
fields:
  - name: subject
    type: string(min_length: 1, max_length: 200)
  - name: body
    type: string(min_length: 1, max_length: 10000)
  - name: attachments
    type: optional[list[ref(AttachmentReference)]]
    constraints: "Maximum 10 attachments per notification"
```

And this response_schema:

```yaml
fields:
  - name: status
    type: enum[queued, rejected]
```

The boundary extraction produces:

```
subject min_length: 1
  -> EC: subject with exactly 1 character (valid)
  -> Error overlap: subject with 0 characters = empty string (triggers validation_error from Step 3)

subject max_length: 200
  -> EC: subject with exactly 200 characters (valid)
  -> Error overlap: subject with 201 characters (triggers validation_error from Step 3)

body min_length: 1
  -> EC: body with exactly 1 character (valid)
  -> Error overlap: body with 0 characters = empty string (triggers validation_error from Step 3)

body max_length: 10000
  -> EC: body with exactly 10000 characters (valid)
  -> Error overlap: body with 10001 characters (triggers validation_error from Step 3)

attachments Maximum 10
  -> EC: list with exactly 10 attachments (valid)
  -> Error overlap: list with 11 attachments (triggers validation_error from Step 3)

attachments optional
  -> EC: attachments field absent (valid, tests absent optional path)
  -> Happy-path already covers the present case

status enum[queued, rejected]
  -> Happy-path covers "queued"
  -> EC: scenario where status is "rejected" (exercises alternate enum path)
```

This extraction produces 7 edge-case scenarios (some invalid
boundaries overlap with error-path scenarios and are not duplicated).

#### Rules for Edge-Case Generation

- Edge cases come FROM constraints, not from imagination. If a
  field has no constraint with a boundary condition, it has no
  edge case for that field.
- Do NOT generate edge cases for "what if the server is slow" or
  "what if the database is down." Those are infrastructure concerns,
  not contract-level scenarios.
- Every edge-case scenario must cite the specific constraint it
  exercises in its description.
- Set leakage_check: true only after verifying the Leakage Self-Check.

### CORRECT: Boundary Value Edge Case

```yaml
- scenario_id: SCN-005
  name: "dispatch_notification with maximum attachments"
  category: edge_case
  description: "Exercises the upper bound of attachments list (10 per contract constraint)"
  leakage_check: true
  setup:
    precondition: "Recipient email corresponds to an active registered user"
    state:
      registered_users:
        - email: "jane.doe@example.com"
          status: "active"
  invocation:
    request:
      recipient_email: "jane.doe@example.com"
      subject: "Quarterly Reports Package"
      body: "Attached are all 10 quarterly report documents."
      attachments:
        - attachment_id: "a1000001-0000-0000-0000-000000000001"
          filename: "report-q1-2024.pdf"
          mime_type: "application/pdf"
        - attachment_id: "a1000001-0000-0000-0000-000000000002"
          filename: "report-q2-2024.pdf"
          mime_type: "application/pdf"
        # ... (8 more, each with distinct realistic values)
        - attachment_id: "a1000001-0000-0000-0000-00000000000a"
          filename: "report-q2-2026.pdf"
          mime_type: "application/pdf"
  expected_outcome:
    response:
      notification_id: "ANY_UUID"
      status: "queued"
      queued_at: "ANY_ISO8601"
    field_classifications:
      notification_id: server_generated
      status: derived
      queued_at: server_generated
    postcondition: "Notification record includes all attachment references"
    invariant: "Referenced attachment files remain in their original storage location"
```


### Step 5: Verify Coverage

After all scenarios are generated:

1. Walk every CTR-* in the interface contracts. Verify each has a
   SIM-* entry.
2. Walk every operation in every CTR-*. Verify each has at least one
   happy-path scenario.
3. Walk every error_type in every operation. Verify each has at least
   one error-path scenario.
4. Walk every field constraint with numeric bounds. Verify each has
   at least one valid-boundary edge-case scenario. Verify the
   invalid-boundary case is covered (either by an edge-case scenario
   or by an error-path scenario from Step 3).
5. Walk every enum-typed response field. Verify each enum value is
   exercised by at least one scenario.
6. Walk every optional field. Verify both the present and absent
   cases are covered.
7. Populate coverage_check and coverage_verdict, including
   boundary_pairs_covered and boundary_pairs_missing.

If any contract, operation, error type, or boundary pair is
uncovered, add the missing scenarios before emitting the artifact.

### Coverage Arithmetic

The minimum scenario count for a contract is:

```
minimum_scenarios = (
    1 (happy path per operation)
  + count(error_types)
  + count(constraints with min bound) (valid boundary)
  + count(constraints with max bound) (valid boundary)
  + count(optional_fields) (absent case, if present case covered by happy path)
  + count(enum_values) - 1 (happy path already covers one)
)
```

Note: Invalid boundary scenarios that overlap with error-path
scenarios from Step 3 are not double-counted. The error-path
scenario provides the coverage.

If your scenario count is below this minimum, you have gaps.


## Multi-Step Scenarios

After all contracts have individual scenarios (Steps 1-5), build
multi-step scenarios from the feature_realization_map.

For each feature in the feature_realization_map:

1. Read the interaction_sequence (list of INT-* IDs in order)
2. Map each INT-* to its CTR-* contract (via interaction_ref)
3. For each CTR-*, select the happy-path scenario
4. Wire output fields from step N to input fields of step N+1:
   - For each output field of step N, check if any input field of
     step N+1 has the same name or a matching type
   - Record the wiring as from_field -> to_field pairs
5. Verify the precondition/postcondition chain:
   - Step N's postcondition must establish step N+1's precondition
   - If not, the feature realization has a gap -- raise as a finding
6. **Generate branch scenarios for enum-valued response fields:**
   - If step N returns an enum field (e.g., status: enum[queued, rejected]),
     create a branch scenario for each non-happy-path enum value
   - The branch scenario follows the alternate path through the
     remaining steps
   - Branch coverage is required, not optional -- every enum value
     that would change the flow must have a branch scenario

### CORRECT

```yaml
multi_step_scenarios:
  - multi_step_id: MS-003-01
    feature_ref: FT-003
    description: "Task assignment triggers notification dispatch and confirmation"
    steps:
      - step_number: 1
        contract_ref: CTR-001
        operation: dispatch_notification
        scenario_ref: SIM-001-HH-01
        wiring:
          - from_field: notification_id
            to_field: notification_id
    branch_scenarios:
      - branch_id: MS-003-01-BR-01
        branch_on: "status == 'rejected'"
        steps:
          - step_number: 1
            contract_ref: CTR-001
            operation: dispatch_notification
            scenario_ref: SIM-001-EC-07
            wiring: []
        # When status is 'rejected', no downstream step consumes the
        # notification_id. The branch terminates here.
```

### WRONG: Missing Branch Coverage

```yaml
multi_step_scenarios:
  - multi_step_id: MS-003-01
    steps:
      - step_number: 1
        contract_ref: CTR-001
        operation: dispatch_notification
        scenario_ref: SIM-001-HH-01
    branch_scenarios: []
# dispatch_notification returns enum[queued, rejected]. The happy path
# assumes 'queued'. Where is the branch for 'rejected'? Missing branch
# coverage means the alternate flow is untested.
```

### WRONG: Duplicated Scenario Instead of Reference

```yaml
multi_step_scenarios:
  - multi_step_id: MS-003-01
    steps:
      - step_number: 1
        contract_ref: CTR-001
        operation: dispatch_notification
        inputs:
          - field: recipient_email
            value: "alice@example.com"
# Duplicated the entire scenario instead of using scenario_ref.
# Multi-step scenarios reference single-operation scenarios, they
# do not redefine them.
```


## TRANSFORM: Interface Contract -> Simulation Scenarios

### INPUT (PH-004 artifact, abbreviated)

```yaml
shared_types:
  - name: AttachmentReference
    fields:
      - name: attachment_id
        type: string(format: uuid)
      - name: filename
        type: string(max_length: 255)
      - name: mime_type
        type: string(pattern: "^[a-z]+/[a-z0-9.+-]+$")

contracts:
  - id: CTR-001
    name: "Notification Dispatch"
    interaction_ref: INT-001
    source_component: CMP-001-api
    target_component: CMP-002-notifications
    operations:
      - name: dispatch_notification
        description: "Submit a notification for asynchronous delivery"
        request_schema:
          fields:
            - name: recipient_email
              type: string(format: email)
              required: true
              constraints: "Must be a registered user email address"
            - name: subject
              type: string(min_length: 1, max_length: 200)
              required: true
              constraints: "Non-empty, plain text only"
            - name: body
              type: string(min_length: 1, max_length: 10000)
              required: true
              constraints: "Supports plain text; no executable content"
            - name: attachments
              type: optional[list[ref(AttachmentReference)]]
              required: false
              constraints: "Maximum 10 attachments per notification"
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
            condition: "recipient_email is missing or not a valid email format, subject is empty or exceeds 200 characters, body is empty or exceeds 10000 characters, or attachments exceed maximum count"
          - name: not_found
            condition: "recipient_email does not match any registered user"
          - name: rate_limited
            condition: "Caller has exceeded the notification dispatch rate for this recipient within the throttle window"
    behavioral_specs:
      - precondition: "Recipient email corresponds to an active registered user"
        postcondition: "A notification record exists with status 'queued' and a unique notification_id; delivery will be attempted asynchronously"
        invariant: "Existing queued notifications for the same recipient are unaffected"
      - precondition: "Attachments list contains only references to previously uploaded files"
        postcondition: "Notification record includes all attachment references; files are not copied or moved"
        invariant: "Referenced attachment files remain in their original storage location"
```

### CORRECT OUTPUT

```yaml
simulation_metadata:
  source_contracts: "interface-contracts.yaml"
  simulation_date: "2026-04-10"
  total_contract_count: 1
  total_scenario_count: 9

simulations:
  - simulation_id: SIM-001
    contract_ref: CTR-001
    operation_ref: dispatch_notification
    scenarios:
      # --- HAPPY PATH ---
      - scenario_id: SCN-001
        name: "successful notification dispatch with no attachments"
        category: happy_path
        description: "Exercises the primary success path for a plain notification"
        leakage_check: true

        setup:
          precondition: "Recipient email corresponds to an active registered user"
          state:
            registered_users:
              - email: "jane.doe@example.com"
                status: "active"

        invocation:
          request:
            recipient_email: "jane.doe@example.com"
            subject: "Task Assignment: Review Q4 Report"
            body: "You have been assigned to review the Q4 financial report. Due date: 2026-05-15."

        expected_outcome:
          response:
            notification_id: "ANY_UUID"
            status: "queued"
            queued_at: "ANY_ISO8601"
          field_classifications:
            notification_id: server_generated
            status: derived
            queued_at: server_generated
          postcondition: "A notification record exists with status 'queued' and a unique notification_id; delivery will be attempted asynchronously"
          invariant: "Existing queued notifications for the same recipient are unaffected"

      - scenario_id: SCN-002
        name: "successful notification dispatch with attachments"
        category: happy_path
        description: "Exercises the success path with attachment references"
        leakage_check: true

        setup:
          precondition: "Attachments list contains only references to previously uploaded files"
          state:
            registered_users:
              - email: "carlos.reyes@example.com"
                status: "active"
            uploaded_files:
              - attachment_id: "d4e5f6a7-b8c9-0d1e-2f3a-4b5c6d7e8f90"
                filename: "project-plan.pdf"
                mime_type: "application/pdf"

        invocation:
          request:
            recipient_email: "carlos.reyes@example.com"
            subject: "Project Kickoff Materials"
            body: "Please review the attached project plan before our Monday meeting."
            attachments:
              - attachment_id: "d4e5f6a7-b8c9-0d1e-2f3a-4b5c6d7e8f90"
                filename: "project-plan.pdf"
                mime_type: "application/pdf"

        expected_outcome:
          response:
            notification_id: "ANY_UUID"
            status: "queued"
            queued_at: "ANY_ISO8601"
          field_classifications:
            notification_id: server_generated
            status: derived
            queued_at: server_generated
          postcondition: "Notification record includes all attachment references; files are not copied or moved"
          invariant: "Referenced attachment files remain in their original storage location"

      # --- ERROR PATHS ---
      - scenario_id: SCN-003
        name: "dispatch fails when recipient_email is missing"
        category: error_path
        description: "Triggers validation_error by omitting the required recipient_email field"
        leakage_check: true

        setup:
          precondition: "N/A -- validation occurs before precondition check"
          state: {}

        invocation:
          request:
            subject: "Task Assignment: Review Q4 Report"
            body: "You have been assigned to review the Q4 financial report."
            # recipient_email deliberately omitted

        expected_outcome:
          response: {}
          field_classifications: {}
          postcondition: "N/A -- operation does not succeed"
          invariant: "No notification record created; system state unchanged"

        error_scenario:
          error_type: validation_error
          trigger: "recipient_email is missing"
          expected_error:
            error_type: "validation_error"
            field: "recipient_email"

      - scenario_id: SCN-004
        name: "dispatch fails when recipient is not a registered user"
        category: error_path
        description: "Triggers not_found when the email does not match any registered user"
        leakage_check: true

        setup:
          precondition: "No registered user has the given email"
          state:
            registered_users:
              - email: "jane.doe@example.com"
                status: "active"

        invocation:
          request:
            recipient_email: "unknown.person@example.com"
            subject: "Welcome Aboard"
            body: "Your account has been created successfully."

        expected_outcome:
          response: {}
          field_classifications: {}
          postcondition: "N/A -- operation does not succeed"
          invariant: "No notification record created; system state unchanged"

        error_scenario:
          error_type: not_found
          trigger: "recipient_email does not match any registered user"
          expected_error:
            error_type: "not_found"
            field: "recipient_email"

      - scenario_id: SCN-005
        name: "dispatch fails when rate limit exceeded"
        category: error_path
        description: "Triggers rate_limited when the caller exceeds the dispatch rate for this recipient"
        leakage_check: true

        setup:
          precondition: "Caller has already dispatched at the maximum rate for this recipient"
          state:
            registered_users:
              - email: "jane.doe@example.com"
                status: "active"
            rate_limit_state:
              recipient: "jane.doe@example.com"
              window_status: "exhausted"

        invocation:
          request:
            recipient_email: "jane.doe@example.com"
            subject: "Another Notification"
            body: "This notification exceeds the throttle window limit."

        expected_outcome:
          response: {}
          field_classifications: {}
          postcondition: "N/A -- operation does not succeed"
          invariant: "No new notification record created; existing records unchanged"

        error_scenario:
          error_type: rate_limited
          trigger: "Caller has exceeded the notification dispatch rate for this recipient within the throttle window"
          expected_error:
            error_type: "rate_limited"

      # --- EDGE CASES (from Boundary Extraction) ---
      - scenario_id: SCN-006
        name: "dispatch with subject at maximum length boundary"
        category: edge_case
        description: "Exercises the upper bound of subject length (200 characters per max_length constraint)"
        leakage_check: true

        setup:
          precondition: "Recipient email corresponds to an active registered user"
          state:
            registered_users:
              - email: "jane.doe@example.com"
                status: "active"

        invocation:
          request:
            recipient_email: "jane.doe@example.com"
            subject: "Quarterly Financial Performance Review and Budget Allocation Summary for Department Operations Including Capital Expenditure Forecasts and Revenue Projections for the Upcoming Fiscal Year Two Thousand"
            body: "Please review the attached summary at your earliest convenience."

        expected_outcome:
          response:
            notification_id: "ANY_UUID"
            status: "queued"
            queued_at: "ANY_ISO8601"
          field_classifications:
            notification_id: server_generated
            status: derived
            queued_at: server_generated
          postcondition: "A notification record exists with status 'queued' and a unique notification_id; delivery will be attempted asynchronously"
          invariant: "Existing queued notifications for the same recipient are unaffected"

      - scenario_id: SCN-007
        name: "dispatch with subject at minimum length boundary"
        category: edge_case
        description: "Exercises the lower bound of subject length (1 character per min_length constraint)"
        leakage_check: true

        setup:
          precondition: "Recipient email corresponds to an active registered user"
          state:
            registered_users:
              - email: "jane.doe@example.com"
                status: "active"

        invocation:
          request:
            recipient_email: "jane.doe@example.com"
            subject: "R"
            body: "This notification has a single-character subject to test the minimum boundary."

        expected_outcome:
          response:
            notification_id: "ANY_UUID"
            status: "queued"
            queued_at: "ANY_ISO8601"
          field_classifications:
            notification_id: server_generated
            status: derived
            queued_at: server_generated
          postcondition: "A notification record exists with status 'queued' and a unique notification_id; delivery will be attempted asynchronously"
          invariant: "Existing queued notifications for the same recipient are unaffected"

      - scenario_id: SCN-008
        name: "dispatch with empty attachments list"
        category: edge_case
        description: "Exercises the optional attachments field with an explicit empty list"
        leakage_check: true

        setup:
          precondition: "Recipient email corresponds to an active registered user"
          state:
            registered_users:
              - email: "jane.doe@example.com"
                status: "active"

        invocation:
          request:
            recipient_email: "jane.doe@example.com"
            subject: "Weekly Status Update"
            body: "No attachments this week. All deliverables are on track."
            attachments: []

        expected_outcome:
          response:
            notification_id: "ANY_UUID"
            status: "queued"
            queued_at: "ANY_ISO8601"
          field_classifications:
            notification_id: server_generated
            status: derived
            queued_at: server_generated
          postcondition: "A notification record exists with status 'queued' and a unique notification_id; delivery will be attempted asynchronously"
          invariant: "Existing queued notifications for the same recipient are unaffected"

      - scenario_id: SCN-009
        name: "dispatch with response status 'rejected'"
        category: edge_case
        description: "Exercises the non-happy-path enum value for status: enum[queued, rejected]"
        leakage_check: true

        setup:
          precondition: "Recipient email corresponds to an active registered user but server-side conditions cause rejection"
          state:
            registered_users:
              - email: "jane.doe@example.com"
                status: "active"

        invocation:
          request:
            recipient_email: "jane.doe@example.com"
            subject: "Notification That May Be Rejected"
            body: "This notification exercises the rejected status path."

        expected_outcome:
          response:
            notification_id: "ANY_UUID"
            status: "rejected"
            queued_at: "ANY_ISO8601"
          field_classifications:
            notification_id: server_generated
            status: derived
            queued_at: server_generated
          postcondition: "Notification record exists with status 'rejected'; no delivery attempt"
          invariant: "Existing queued notifications for the same recipient are unaffected"

coverage_check:
  contracts_covered: [CTR-001]
  contracts_missing: []
  operations_covered: ["CTR-001.dispatch_notification"]
  operations_missing: []
  error_types_covered:
    - "CTR-001.dispatch_notification.validation_error"
    - "CTR-001.dispatch_notification.not_found"
    - "CTR-001.dispatch_notification.rate_limited"
  error_types_missing: []
  boundary_pairs_covered:
    - "CTR-001.dispatch_notification.subject.max_length_200_valid"
    - "CTR-001.dispatch_notification.subject.min_length_1_valid"
    - "CTR-001.dispatch_notification.attachments.absent_optional"
    - "CTR-001.dispatch_notification.status.enum_rejected"
  boundary_pairs_missing: []
  status: "1/1 contracts, 1/1 operations, 3/3 error types, 4/4 boundary pairs covered"

coverage_verdict:
  total_contracts: 1
  covered_contracts: 1
  total_operations: 1
  covered_operations: 1
  total_error_types: 3
  covered_error_types: 3
  total_boundary_pairs: 4
  covered_boundary_pairs: 4
  total_scenarios: 9
  verdict: PASS
```

### WRONG OUTPUT (same input)

```yaml
simulations:
  - simulation_id: SIM-001
    contract_ref: CTR-001
    operation_ref: dispatch_notification
    scenarios:
      - scenario_id: SCN-001
        name: "test dispatch"
        category: happy_path
        setup:
          state: {}                          # MISSING: no precondition established
        invocation:
          request:
            recipient_email: "test@test.com" # PLACEHOLDER: not realistic
            subject: "test"                  # PLACEHOLDER: exercises nothing
            body: "test body"                # PLACEHOLDER: meaningless
        expected_outcome:
          response:
            notification_id: "550e8400-e29b-41d4-a716-446655440000"  # LEAKED: specific UUID
            status: "queued"
            queued_at: "2026-04-10T14:30:00Z"                        # LEAKED: specific timestamp
            queue_position: 1                                         # LEAKED: not in schema
            delivery_method: "smtp"                                   # LEAKED: not in schema
          field_classifications: {}          # MISSING: no classifications
          postcondition: "Notification sent"  # VAGUE: not from behavioral spec
      # NO ERROR-PATH SCENARIOS
      # NO EDGE-CASE SCENARIOS
      # NO BOUNDARY EXTRACTION
      # NO COVERAGE CHECK

# Every dimension fails:
# - Input realism: placeholder values throughout
# - Output derivability: specific values for server_generated fields
# - LLM leakage: queue_position and delivery_method are not in schema
# - Replaceability: no precondition setup, no invariant check
# - Coverage: missing error-path scenarios for 3 error types
# - Coverage: missing boundary-pair edge-case scenarios
# - Coverage: no coverage_check or coverage_verdict
# - Leakage check: no leakage_check field on any scenario
```

### What makes the CORRECT output correct

- **Contract Integrity:** SIM-001 references CTR-001 with exact
  operation name. No invented contracts or operations.
- **Happy Paths:** Two scenarios covering the main success paths
  (with and without attachments), both with full setup, invocation,
  and expected outcome.
- **Error Paths:** One scenario per error_type (validation_error,
  not_found, rate_limited). Each triggers exactly one error condition.
- **Boundary Extraction:** Systematic edge cases from constraint
  boundaries -- subject max_length, subject min_length, absent
  optional attachments, and rejected enum value. Every edge case
  cites the specific constraint it exercises.
- **Input Realism:** All values are domain-realistic. No placeholders,
  no "test" patterns, no Lorem ipsum.
- **Output Derivability:** Every response field is classified. Server-
  generated fields use format-only placeholders (ANY_UUID, ANY_ISO8601).
  Derived fields have specific values from behavioral specs.
- **LLM Leakage:** No fields beyond the contract schema. No specific
  UUIDs or timestamps for server-generated fields. No implementation
  internals. Every scenario has leakage_check: true.
- **Replaceability:** Every scenario has setup (precondition), invocation
  (request), and assertion (postcondition + invariant). All domain-level,
  no mock configuration.
- **Coverage:** All contracts, operations, error types, and boundary
  pairs covered. Coverage check and verdict present with boundary pair
  tracking.


## Anti-Patterns

### Placeholder Infestation
Input values are "test", "foo", "123", or "Lorem ipsum" instead of
domain-realistic values. Every value must exercise a meaningful code
path. Apply the Realism Test.

### Leaked Oracle
Expected output contains specific UUIDs, timestamps, or sequence
numbers for server-generated fields. The simulation cannot know these
values. Use format-only assertions (ANY_UUID, ANY_ISO8601). Apply the
Contract-Only Test.

### Schema Phantom
Response fields or error fields that do not exist in the contract's
response_schema or error_types. The simulation invents fields the
contract never declared. Every field must trace to the contract. Apply
the Contract-Only Test.

### Combined Error Scenario
An error-path scenario that triggers multiple error conditions
simultaneously. Which error does the implementation report? The test
becomes order-dependent. One error condition per scenario. Apply the
Single-Error Principle.

### Missing Error Coverage
An error_type declared in the contract has no corresponding error-path
scenario. The error handling path is untested. Walk every error_type
and generate a scenario for each.

### Missing Boundary Coverage
A field with numeric constraints (min_length, max_length, min, max,
maximum count) has no edge-case scenario at its boundary value. The
boundary extraction sub-discipline was skipped or incomplete. Walk
every field constraint and verify boundary pairs exist.

### Boundary Drift
An edge-case scenario that claims to test a boundary but uses a
value that is not at the exact boundary. If max_length is 200, the
edge-case value must be exactly 200 characters, not 199 or 201.

### Vague Postcondition
A postcondition written as "operation succeeds" or "notification sent"
instead of quoting the behavioral spec. Postconditions must be the
exact text from the contract's behavioral_specs.

### Mock-Coupled Setup
Setup configuration that references mock frameworks, stub returns, or
test double configuration instead of domain-level preconditions. The
setup must describe domain state, not test infrastructure. Apply the
Replaceability Test.

### Orphan Simulation
A SIM-* entry whose contract_ref does not match any CTR-* in the
interface contracts. PH-005 simulates existing contracts only -- it
has no authority to create new ones. Apply the Contract Integrity Rule.

### Missing Classification
Response fields without entries in field_classifications. Without
classification, the test author cannot know whether to assert exact
equality (echo, derived) or format-only (server_generated). Every
response field must be classified.

### Missing Branch Coverage
A multi-step scenario where an enum-valued response field has only
one path exercised. If step N returns status: enum[queued, rejected]
and only the "queued" path has a multi-step scenario, the "rejected"
branch is untested. Every non-happy-path enum value must have a
branch scenario.

### Rubber-Stamped Leakage Check
A scenario with leakage_check: true but containing values that fail
the Leakage Self-Check (fields not in schema, specific server-generated
values, implementation-coupled assertions). The leakage_check boolean
is an auditable assertion, not a rubber stamp. If any value cannot be
traced to the contract, leakage_check must be false and the scenario
must be rewritten.


## Scope Boundary: This Skill vs. Stack-Specific Skills

This skill covers WHAT to simulate at the technology-agnostic level.
It does NOT cover:

- Test framework setup (pytest fixtures, Jest describe blocks, Go
  test functions)
- Mock/stub/fake library usage (unittest.mock, testdouble, gomock)
- Integration test harness configuration (docker-compose, testcontainers)
- Database seeding strategies (factory patterns, fixture files)
- Serialization format of request/response (JSON, protobuf, msgpack)
- HTTP client configuration (requests, fetch, net/http)
- Assertion library syntax (assertEqual, expect().toBe(), assert.Equal)

Stack-specific skills ADD to this floor. They are loaded by the
Skill-Selector based on expected_expertise entries and provide the
technology-appropriate test idioms for each component.


## Generator Pre-Emission Checklist

1. Every CTR-* from the interface contracts has at least one SIM-* simulation
2. No simulations reference a contract_ref not in the interface contracts
3. Every operation in every contract has at least one happy-path scenario
4. Every error_type in every operation has at least one error-path scenario
5. Each error-path scenario triggers exactly one error condition (Single-Error Principle)
6. Boundary Extraction completed for every field with numeric/length constraints
7. Every constraint with min bound has a valid-boundary edge-case scenario
8. Every constraint with max bound has a valid-boundary edge-case scenario
9. Invalid boundaries are covered (by edge-case or error-path scenario -- no gaps)
10. Every enum-typed response field has scenarios covering all enum values
11. Every optional field has both present and absent coverage
12. Every input value passes the Realism Test (no placeholders)
13. Every output field has a field_classifications entry
14. Echo fields assert exact equality with request values
15. Server-generated fields use format-only placeholders (ANY_UUID, ANY_ISO8601)
16. Derived fields assert specific values from behavioral specs
17. No response fields beyond what the contract's response_schema declares
18. No implementation-specific values (database sequences, specific timestamps, queue internals)
19. Every scenario has setup (precondition), invocation (request), and expected_outcome (postcondition + invariant)
20. Setup uses domain-level state, not mock configuration
21. Postconditions quote the behavioral spec text, not paraphrased summaries
22. Every scenario has leakage_check: true with verified contract-only derivability
23. Multi-step scenarios include branch scenarios for every non-happy-path enum value
24. Multi-step wiring explicitly maps output fields to input fields
25. coverage_check and coverage_verdict are populated and accurate, including boundary pairs
26. Traceability checks deferred to traceability-discipline
