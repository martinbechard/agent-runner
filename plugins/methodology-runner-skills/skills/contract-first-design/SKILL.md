---
name: contract-first-design
description: Define typed interface contracts with precise schemas, exhaustive error modes, and behavioral specs before any implementation
---

# Contract-First Design

This skill governs the contract-writing discipline for PH-004
(Interface Contracts). Its scope is the judgment calls that
generation_instructions do not cover: how to derive operations from
interaction data summaries, how to type every schema field precisely,
how to enumerate error modes exhaustively, and how to specify
behavioral contracts that simulations can verify.

This skill is the FLOOR, not the ceiling. Stack-specific contract
idioms -- HTTP status codes, gRPC status mappings, message broker
headers -- come from companion skills loaded by the Skill-Selector
based on the component's expected_expertise entries. This skill
ensures every contract addresses the four universal disciplines
regardless of technology.

Traceability mechanics -- source_refs, source_quote, coverage_check,
coverage_verdict, inherited_assumptions, and the Quote Test -- are
governed by the companion traceability-discipline skill loaded
alongside this one. This skill focuses on HOW to write contracts and
WHAT to declare in the interface contracts artifact.


## Output Schema: interface-contracts.yaml

Understanding the target schema drives every judgment call below.

```yaml
shared_types:
  - name: string                    # reusable named structure
    fields:
      - name: string
        type: string                # precise type (see Type Precision below)
        constraints: string

contracts:
  - id: CTR-NNN
    name: string                    # human-readable contract name
    interaction_ref: INT-NNN        # from solution design -- never invent
    source_component: CMP-NNN      # initiator
    target_component: CMP-NNN      # receiver
    operations:
      - name: string               # verb-phrase: what this operation does
        description: string         # one sentence purpose
        request_schema:
          fields:
            - name: string          # exact field name
              type: string          # precise type (see Type Precision below)
              required: true | false
              constraints: string   # value bounds, format, allowed values
        response_schema:
          fields: [...]             # same structure as request
        error_types:
          - name: string            # named error category
            condition: string       # WHEN this error triggers
            http_status: NNN        # if applicable (omit for non-HTTP)
    behavioral_specs:
      - precondition: string        # what must be true before invocation
        postcondition: string       # what is guaranteed after success
        invariant: string           # what remains unchanged
```


## Interaction Integrity Rule

**The solution design from PH-003 defines the interaction boundaries.
This skill writes contracts WITHIN those boundaries. You NEVER invent,
merge, or remove interactions.**

Your failure mode under pressure is inventing interactions when
someone says "this is missing" or "add a contract for X." If an
interaction is missing, the fix is a PH-003 revision, not a PH-004
invention. PH-004 has no authority to create new interactions.

The interaction_ref values in the contracts MUST match the INT-* IDs
from the solution design exactly. If PH-003 declared INT-001 between
CMP-001 and CMP-002, the contracts reference INT-001 with exactly
those source and target components.

### CORRECT

```yaml
# PH-003 declared INT-001: CMP-001-api -> CMP-002-worker
contracts:
  - id: CTR-001
    interaction_ref: INT-001
    source_component: CMP-001-api
    target_component: CMP-002-worker
```

### WRONG: Inventing an Interaction

```yaml
# PH-003 has no INT-005. This contract is INVENTED.
contracts:
  - id: CTR-005
    interaction_ref: INT-005       # DOES NOT EXIST in solution design
    source_component: CMP-001-api
    target_component: CMP-003-cache
# Internal communication (caching, logging) is not an architectural
# interaction. PH-004 has no authority to create new interactions.
```

| Pressure | Response |
|----------|----------|
| "This interaction is missing, add it" | Escalate to PH-003 revision. PH-004 covers existing interactions only. |
| "Add a contract for real-time queries" | If no INT-* exists for it, it cannot have a contract. Raise as a finding. |
| "Be thorough and cover everything" | Thoroughness means complete coverage of DECLARED interactions, not inventing new ones. |


## Type Precision Discipline

This is the single most important discipline in this skill and the
one most likely to fail under pressure.

### The Rule

**Every field in every request_schema and response_schema must have a
precise type. No field may use 'object', 'any', 'unknown', 'mixed',
'dynamic', or 'map' as its type.**

Allowed type forms:

| Type form | Example | When to use |
|-----------|---------|-------------|
| Primitive | string, integer, boolean, float | Single scalar values |
| Constrained primitive | string(format: email), integer(min: 1, max: 100) | Scalars with value restrictions |
| Enum | enum[pending, active, completed] | Fixed set of string values |
| Named reference | ref(TaskSummary) | Reusable structure defined in shared_types |
| List of typed elements | list[ref(TaskSummary)] | Ordered collection |
| Optional wrapper | optional[string] | Field that may be absent |
| Map with typed values | map[string, ref(Permission)] | Key-value pairs with known value type |

### The Type Hole Test

For each field in every schema, ask:

> "If I gave this type to a code generator, could it produce the
> correct data structure without asking me any questions?"

- **YES** -> type is precise enough. Keep it.
- **NO** -> type hole. Refine it.

### CORRECT

```yaml
request_schema:
  fields:
    - name: task_id
      type: string(format: uuid)
      required: true
      constraints: "Must reference an existing task"
    - name: assignee_email
      type: string(format: email)
      required: true
      constraints: "Must be a registered user email"
    - name: priority
      type: enum[low, medium, high, critical]
      required: false
      constraints: "Defaults to medium if omitted"
```

### WRONG: Type Holes

```yaml
request_schema:
  fields:
    - name: task_id
      type: string              # HOLE: no format constraint
      required: true
    - name: metadata
      type: object              # HOLE: what fields does it have?
      required: false
    - name: options
      type: any                 # HOLE: completely unspecified
      required: false
    - name: tags
      type: list                # HOLE: list of what?
      required: false
# Every field above fails the Type Hole Test. A code generator
# cannot produce correct structures from these types.
```

### How Type Holes Happen

Your primary failure mode under pressure is writing vague types when
asked to "move quickly" or "keep it simple." Simplicity means fewer
fields, NOT vaguer types. Every field that exists must be fully typed.

| Pressure | Hole form | Correct form |
|----------|----------|-------------|
| "Keep it simple" | type: object | type: ref(TaskFilter) with fields defined |
| "Don't over-specify" | type: any | type: enum[draft, published, archived] |
| "Be flexible" | type: map | type: map[string, ref(Permission)] |
| "Just use string" | type: string (for structured data) | type: ref(Address) with street, city, postal_code |
| "Skip the details" | type: list | type: list[ref(LineItem)] |

### Type Hole Red Flags

If a schema field matches ANY of these patterns, it is a type hole:

- Type is 'object', 'any', 'unknown', 'mixed', or 'dynamic'
- Type is 'list' or 'array' without element type
- Type is 'map' or 'dict' without value type
- Type is 'string' but the field holds structured data
- Type references a name not defined in shared_types

**All of these mean: refine the type.**


## Error Completeness Discipline

### The Rule

**Every operation must define ALL error categories that the caller
could encounter. Missing an error type means the caller has no
contract for handling that failure.**

### Minimum Error Categories Per Operation

For each operation, evaluate which of these categories apply:

| Category | Applies when | Example |
|----------|-------------|---------|
| **validation_error** | Operation accepts input | "Required field 'task_id' missing" |
| **not_found** | Operation references an entity by ID | "Task with given ID does not exist" |
| **authorization_denied** | Operation has access control | "Caller lacks permission to reassign" |
| **conflict** | Operation modifies state that others may modify | "Task already assigned to another user" |
| **dependency_failure** | Operation calls an external service | "Email service unavailable" |
| **rate_limited** | Operation is externally exposed | "Too many requests, retry after N seconds" |

Not every category applies to every operation. A read-only query has
no conflict error. An internal-only operation has no rate_limited
error. But every operation that accepts input MUST have at least
validation_error, and every operation that references an entity MUST
have at least not_found.

### The Error Completeness Test

For each operation, ask:

> "If I wrote the caller's error-handling code using ONLY the
> error_types listed here, would any production failure go unhandled?"

- **YES, all failures covered** -> error types are complete. Keep them.
- **NO, some failure unhandled** -> error gap. Add the missing type.

### CORRECT

```yaml
operations:
  - name: assign_task
    error_types:
      - name: validation_error
        condition: "task_id is missing, malformed, or assignee_email is not a valid email"
      - name: not_found
        condition: "No task exists with the given task_id"
      - name: authorization_denied
        condition: "Caller does not have 'assign' permission on the task's project"
      - name: conflict
        condition: "Task is already assigned and reassignment is not enabled"
```

### WRONG: Error Gaps

```yaml
operations:
  - name: assign_task
    error_types:
      - name: error
        condition: "Something went wrong"
# ONE catch-all error. The caller cannot distinguish validation
# failure from authorization denial from not-found.
# Every error type must be specific and actionable.
```

### Error Description Discipline

Error conditions must be specific enough that a developer can write
the guard clause. "Invalid input" is not a condition. "task_id is
missing or not a valid UUID format" is a condition.

| Vague (WRONG) | Specific (CORRECT) |
|--------------|-------------------|
| "Invalid input" | "task_id is missing, malformed, or not a valid UUID" |
| "Server error" | "Email service returned non-success status or timed out" |
| "Not allowed" | "Caller lacks 'assign' permission on the task's project" |
| "Already exists" | "A task with the same title already exists in this project" |


## Behavioral Specs Discipline

### The Rule

**Every contract must have at least one behavioral spec (precondition
+ postcondition pair). A contract without behavioral specs is a type
signature without semantics -- it tells you the SHAPE of data but not
the MEANING of the operation.**

### How to Write Behavioral Specs

A behavioral spec has three parts:

1. **Precondition:** What must be true BEFORE the operation executes.
   The caller is responsible for ensuring this. If the precondition is
   violated, the operation's behavior is undefined (or returns a
   validation_error).

2. **Postcondition:** What is GUARANTEED to be true AFTER successful
   execution. The implementation is responsible for ensuring this. A
   postcondition is a testable assertion.

3. **Invariant:** What remains UNCHANGED by the operation. Invariants
   constrain the operation's side effects. If an operation assigns a
   task, the invariant might be "task title and description are
   unchanged."

### The Simulation Test

For each behavioral spec, ask:

> "Can a simulation verify this precondition/postcondition pair
> WITHOUT knowing the implementation?"

- **YES** -> behavioral spec is well-defined. Keep it.
- **NO** -> too vague or implementation-coupled. Rewrite.

### CORRECT

```yaml
behavioral_specs:
  - precondition: "Task exists and is in 'open' status"
    postcondition: "Task status is 'assigned' and assignee matches the request"
    invariant: "Task title, description, and due date are unchanged"
  - precondition: "Caller has 'assign' permission on the task's project"
    postcondition: "Assignment audit event is recorded with caller identity and timestamp"
    invariant: "Other tasks in the project are unchanged"
```

### WRONG: Vague or Implementation-Coupled Specs

```yaml
behavioral_specs:
  - precondition: "Request is valid"
    postcondition: "Task is updated"
    invariant: "Nothing else changes"
# Every field is too vague for a simulation to verify.
# "Request is valid" -- which fields, what validity?
# "Task is updated" -- which fields, to what values?
# "Nothing else changes" -- what specifically is preserved?

  - precondition: "Database connection is open and transaction started"
    postcondition: "Row inserted into tasks table with status column = 'assigned'"
    invariant: "Connection pool size unchanged"
# Implementation-coupled. References database internals.
# Rewrite in domain terms.
```


## Cross-Contract Consistency Discipline

### The Rule

**When two or more contracts reference the same data structure (by
name or by field overlap), the field names, types, and constraints
MUST match exactly across all contracts.**

### Shared Types

Any data structure referenced by more than one contract MUST be
declared in a shared_types section at the top of the contracts
artifact. Inline definitions that repeat the same structure create
drift risk.

```yaml
shared_types:
  - name: TaskSummary
    fields:
      - name: task_id
        type: string(format: uuid)
      - name: title
        type: string(max_length: 200)
      - name: status
        type: enum[open, assigned, completed, archived]
      - name: assignee_email
        type: optional[string(format: email)]
```

### The Consistency Test

For each shared type reference, ask:

> "If I grep all contracts for this type name, do all references
> resolve to the same field definitions?"

- **YES** -> consistent. Keep it.
- **NO** -> drift. Consolidate into shared_types.

### CORRECT

```yaml
# Both contracts reference ref(TaskSummary) -- same definition.
contracts:
  - id: CTR-001
    operations:
      - name: get_task
        response_schema:
          fields:
            - name: task
              type: ref(TaskSummary)
  - id: CTR-002
    operations:
      - name: list_tasks
        response_schema:
          fields:
            - name: tasks
              type: list[ref(TaskSummary)]
```

### WRONG: Inconsistent Inline Definitions

```yaml
# CTR-001 defines task_id as string, CTR-002 defines it as integer.
# Both represent the same entity. This is inconsistent.
contracts:
  - id: CTR-001
    operations:
      - name: get_task
        response_schema:
          fields:
            - name: task_id
              type: string
            - name: title
              type: string
  - id: CTR-002
    operations:
      - name: list_tasks
        response_schema:
          fields:
            - name: task_id
              type: integer          # INCONSISTENT with CTR-001
            - name: task_title       # INCONSISTENT field name
              type: string
# task_id has different types. title vs task_title are different names
# for the same field. Extract to shared_types and reference by name.
```


## Contract Writing Procedure

For each INT-* interaction in the solution design, walk these steps
in order. Do NOT skip steps. Do NOT jump to a later interaction
before finishing the current one.

### Step 1: Map Interaction to Contract Shell

Read the interaction's from_component, to_component,
communication_style, and data_summary. Create a CTR-* entry with:
- interaction_ref matching the INT-* ID exactly
- source_component and target_component matching exactly
- name derived from the interaction's purpose (not the ID)

### Step 2: Extract Operations from Data Summary

The data_summary describes WHAT data flows. Derive one or more
operations from it:
- A synchronous-request-response interaction typically has one
  primary operation (e.g., "get_task", "assign_task")
- A complex interaction may have multiple operations (e.g.,
  "create_order" and "cancel_order" on the same contract)
- An asynchronous-command interaction has a "submit" operation
  and possibly a "status" query operation
- An asynchronous-event interaction has a "publish" operation
  describing the event payload

Each operation gets a verb-phrase name and a one-sentence description.

### Step 3: Type Every Field (Type Precision)

For each operation:
1. Define request_schema fields from the data_summary's input
2. Define response_schema fields from the data_summary's output
3. Apply the Type Hole Test to every field
4. Extract any repeated structures to shared_types

### Step 4: Enumerate Error Types (Error Completeness)

For each operation:
1. Walk the minimum error categories table
2. For each applicable category, write a specific condition
3. Apply the Error Completeness Test
4. Ensure conditions are specific enough for guard clauses

### Step 5: Write Behavioral Specs

For the contract as a whole:
1. Write at least one precondition/postcondition pair
2. Identify invariants (what the operation does NOT change)
3. Apply the Simulation Test to each spec
4. Ensure specs use domain language, not implementation terms

### Step 6: Verify Cross-Contract Consistency

After all contracts are drafted:
1. Collect all type references across all contracts
2. Verify each shared type has a single definition in shared_types
3. Apply the Consistency Test
4. Fix any field name or type mismatches


## TRANSFORM: Solution Design Interaction -> Interface Contract

### INPUT (PH-003 artifact, abbreviated)

```yaml
interactions:
  - interaction_id: INT-001
    from_component: CMP-001-api
    to_component: CMP-002-notifications
    communication_style: asynchronous-command
    data_summary: "Notification payload: recipient email, subject line, message body, and optional attachment references"
    features_served: [FT-003]
```

### CORRECT OUTPUT

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

### WRONG OUTPUT (same input)

```yaml
contracts:
  - id: CTR-001
    interaction_ref: INT-001
    source_component: CMP-001-api
    target_component: CMP-002-notifications
    operations:
      - name: send_notification
        request_schema:
          fields:
            - name: payload
              type: object           # TYPE HOLE: what fields?
        response_schema:
          fields:
            - name: result
              type: any              # TYPE HOLE: what shape?
        error_types:
          - name: error
            condition: "Failed"      # CATCH-ALL: not actionable
    behavioral_specs:
      - precondition: "Valid request"        # VAGUE: which fields?
        postcondition: "Notification sent"   # VAGUE: what state change?
        invariant: "System stable"           # VAGUE: what is preserved?
# Every dimension fails:
# - Type holes: payload is 'object', result is 'any'
# - Error gap: single catch-all, no validation/not_found/rate_limited
# - Behavioral specs too vague for simulation to verify
# - No shared_types, no constraints, no format annotations
```

### What makes the CORRECT output correct

- **Interaction Integrity:** CTR-001 references INT-001 with matching
  components. No invented interactions.
- **Type Precision:** Every field has a constrained type. No 'object',
  'any', or bare 'list'. AttachmentReference extracted to shared_types.
- **Error Completeness:** Three error categories appropriate for an
  externally-triggered asynchronous command. Conditions are specific
  enough for guard clauses.
- **Behavioral Specs:** Two pre/postcondition pairs, both verifiable
  by simulation without knowing implementation. Invariants specify
  what does NOT change.
- **Domain Language:** No technology-specific types (no HTTP status
  codes, no framework types, no database constructs).


## Anti-Patterns

### Type Hole
A schema field typed as 'object', 'any', 'unknown', or bare
collection. A code generator cannot produce correct structures. Refine
every field to a precise type or a named ref().

### Error Gap
An operation with fewer error types than the minimum categories table
requires. Missing an error type means the caller has no contract for
that failure mode. Walk the table for every operation.

### Hidden Precondition
A behavioral spec that assumes something not stated in the
precondition. If an operation requires the caller to authenticate
first, that is a precondition, not an implicit assumption. State it.

### Phantom Contract
A contract whose interaction_ref does not match any INT-* in the
solution design. PH-004 covers existing interactions only -- it has
no authority to create new ones. If an interaction is genuinely
missing, escalate to PH-003 revision.

### Drift
Two contracts define the same data structure with different field
names or types. Extract to shared_types. One definition, many
references.

### Catch-All Error
A single error type like "error" or "failure" that covers all failure
modes. The caller cannot distinguish between validation failure,
authorization denial, and not-found. Every error type must be specific
and actionable.

### Implementation-Coupled Spec
A behavioral spec that references database tables, HTTP status codes,
framework types, or language constructs. Rewrite in domain terms.
Simulations must verify behavior without knowing the implementation.


## Generator Pre-Emission Checklist

1. Every INT-* from the solution design has at least one CTR-* contract
2. No contracts reference an interaction_ref not in the solution design
3. Every source_component and target_component match the solution design
4. Every schema field has a precise type (no object/any/unknown/list/map)
5. Every schema field passes the Type Hole Test
6. Shared structures extracted to shared_types with ref() references
7. Every operation has error_types covering all applicable categories
8. Every error condition is specific enough for a guard clause
9. Every contract has at least one behavioral spec
10. Every precondition is explicitly stated (no hidden preconditions)
11. Every postcondition is testable by simulation without implementation
12. Every invariant names specific state that is preserved
13. Cross-contract type references resolve to the same shared_types entry
14. All descriptions use domain language, not technology-specific terms
15. Traceability checks deferred to traceability-discipline
