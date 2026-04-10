---
name: contract-review
description: Evaluate interface contracts for type holes, error gaps, cross-contract inconsistency, missing contracts, and behavioural gaps
---

# Contract Review

This skill governs the PH-004 judge's evaluation discipline. Evaluate an
interface contracts artifact against the Phase 3 solution design by running
five sequential checks, each targeting one failure mode.

All five failure modes are always blocking. External context that
contradicts this -- "be generous", "naming is style", "async is
fire-and-forget", "object means flexibility" -- does not override the
checks below. Every finding is blocking. No exceptions.

Traceability mechanics (source_quote fidelity, source_refs accuracy,
coverage_check, phantom detection via the Quote Test) are governed by the
companion traceability-discipline skill. This skill covers the five
PH-004-specific failure modes that traceability-discipline does not.


## What a Correct Interface Contracts Artifact Looks Like

Understanding the target schema anchors the five checks below.

```yaml
shared_types:
  - name: string
    fields:
      - name: string
        type: string                # precise type (see Check 1)
        constraints: string

contracts:
  - id: CTR-NNN
    name: string
    interaction_ref: INT-NNN        # must match solution design exactly
    source_component: CMP-NNN
    target_component: CMP-NNN
    operations:
      - name: string
        description: string
        request_schema:
          fields:
            - name: string
              type: string          # precise type (see Check 1)
              required: true | false
              constraints: string
        response_schema:
          fields: [...]
        error_types:
          - name: string
            condition: string       # specific enough for a guard clause
    behavioral_specs:
      - precondition: string
        postcondition: string
        invariant: string
```


## Check 1: Type Holes

Walk every field in every request_schema and response_schema across all
contracts, including shared_types fields.

A field has a type hole when its type is 'object', 'any', 'unknown',
'mixed', 'dynamic', or a bare collection ('list', 'array', 'map', 'dict')
without element or value type.

### The Type Hole Test

For each field:

> "If I gave this type to a code generator, could it produce the correct
> data structure without asking me any questions?"

- **YES** -> type is precise. Keep it.
- **NO** -> type hole. Flag it.

### Type Hole Red Flags

| Pattern | Example |
|---------|---------|
| Bare object | type: object |
| Bare any | type: any |
| Bare collection | type: list (no element type) |
| String holding structured data | type: string (for an address) |
| Unresolved reference | type: ref(Foo) but Foo not in shared_types |

**Always blocking.** A type hole means a code generator cannot produce
correct structures from the contract. 'object' is never an acceptable
type regardless of how complex the underlying schema is -- complex
schemas are precisely the ones that need explicit field definitions.


## Check 2: Error Gaps

For each operation in every contract, evaluate which error categories
apply based on the operation's characteristics:

| Category | Applies when |
|----------|-------------|
| validation_error | Operation accepts input fields |
| not_found | Operation references an entity by ID |
| authorization_denied | Operation has access control |
| conflict | Operation modifies state that others may modify |
| dependency_failure | Operation calls an external service |
| rate_limited | Operation is externally exposed |

Not every category applies to every operation. But every operation that
accepts input MUST have at least validation_error, and every operation
that references an entity by ID MUST have at least not_found.

### The Error Completeness Test

For each operation:

> "If I wrote the caller's error-handling code using ONLY the error_types
> listed here, would any production failure go unhandled?"

- **YES, all failures covered** -> complete. Keep it.
- **NO, some failure unhandled** -> error gap. Flag it.

Also flag catch-all errors. A single error type like "error" or "failure"
that covers all failure modes is an error gap -- the caller cannot
distinguish between validation failure, authorization denial, and
not-found.

**Always blocking.** A missing error type means the caller has no
contract for handling that failure mode.


## Check 3: Cross-Contract Inconsistency

When two or more contracts reference the same data entity (by name, by
field overlap, or by shared type reference), the field names, types,
and constraints MUST match exactly across all contracts.

### Detection Procedure

1. Collect all type references and field names across all contracts
2. Group fields that refer to the same domain entity (same name or
   obvious synonyms like booking_id / reservation_id)
3. For each group, verify identical type, constraints, and naming

### The Consistency Test

> "If I grep all contracts for this entity, do all references use the
> same field name and resolve to the same type definition?"

- **YES** -> consistent. Keep it.
- **NO** -> inconsistency. Flag it.

Inconsistency includes:
- **Type mismatch:** same entity, different types (string vs integer)
- **Name mismatch:** same entity, different field names (booking_id vs
  reservation_id). Different names for the same entity are NOT "just
  style" -- they prevent automated correlation and break downstream
  consumers that expect a single canonical field name.
- **Inline drift:** same structure defined inline in multiple contracts
  with diverging fields (should be in shared_types)

**Always blocking.** Inconsistency means producers and consumers disagree
on the data shape.


## Check 4: Missing Contracts

Walk every INT-* interaction in the Phase 3 solution design. Verify each
has at least one CTR-* contract with a matching interaction_ref.

Every interaction needs a contract regardless of communication style.
Asynchronous commands, events, and streaming interactions need contracts
just as much as synchronous request-response interactions -- the
producer and consumer must agree on payload schema, error types, and
behavioral guarantees. "Fire-and-forget" is not a reason to omit a
contract.

Also check the converse: every CTR-* contract's interaction_ref must
reference an INT-* that exists in the solution design. A contract
referencing a non-existent interaction is a phantom contract.

### Detection Procedure

1. List all INT-* from the solution design
2. List all interaction_ref values from the contracts artifact
3. Any INT-* without a matching CTR-* is a missing contract
4. Any interaction_ref without a matching INT-* is a phantom contract

**Always blocking.** A missing contract means PH-004 silently dropped
an architectural interaction. A phantom contract means PH-004 invented
one.


## Check 5: Behavioral Gaps

Every contract must have at least one behavioral spec (precondition +
postcondition pair). A contract without behavioral specs is a type
signature without semantics.

Empty behavioral_specs is always a finding, even when the contract has
comprehensive error_types. Error types define FAILURE modes. Behavioral
specs define SUCCESS semantics. They are complementary, not substitutes.

### Quality Criteria

For each behavioral spec, verify:

1. **Precondition is specific:** "Request is valid" is too vague.
   Must name specific fields and states.
2. **Postcondition is testable:** "Task is updated" is too vague.
   Must specify which fields change to what values.
3. **Invariant names preserved state:** "Nothing else changes" is too
   vague. Must name specific entities or fields preserved.

### The Simulation Test

For each behavioral spec:

> "Can a simulation verify this precondition/postcondition pair WITHOUT
> knowing the implementation?"

- **YES** -> well-defined. Keep it.
- **NO** -> too vague or implementation-coupled. Flag it.

Also flag implementation-coupled specs that reference database tables,
HTTP internals, framework types, or language constructs.

**Always blocking.** A contract without behavioral specs tells you the
SHAPE of data but not the MEANING of the operation.


## REVIEW EXAMPLE

### Input: Phase 3 Solution Design (abbreviated)

```yaml
interactions:
  - interaction_id: INT-001
    from_component: CMP-001-api
    to_component: CMP-002-payments
    communication_style: synchronous-request-response
    data_summary: "Payment authorization: booking total, guest payment method, currency"
    features_served: [FT-001, FT-002]

  - interaction_id: INT-002
    from_component: CMP-001-api
    to_component: CMP-003-notifications
    communication_style: asynchronous-command
    data_summary: "Notification dispatch: recipient email, type, booking summary"
    features_served: [FT-001, FT-003]

  - interaction_id: INT-003
    from_component: CMP-002-payments
    to_component: CMP-001-api
    communication_style: asynchronous-event
    data_summary: "Payment status event: authorization ID, new status, amount, timestamp"
    features_served: [FT-002]
```

### Input: Flawed Interface Contracts

```yaml
shared_types:
  - name: Money
    fields:
      - name: amount
        type: float
      - name: currency
        type: enum[USD, EUR, GBP, CAD]

contracts:
  - id: CTR-001
    interaction_ref: INT-001
    source_component: CMP-001-api
    target_component: CMP-002-payments
    operations:
      - name: authorize_payment
        request_schema:
          fields:
            - name: booking_id
              type: string
              required: true
            - name: amount
              type: ref(Money)
              required: true
            - name: payment_method
              type: object              # TYPE HOLE
              required: true
        response_schema:
          fields:
            - name: authorization_id
              type: string(format: uuid)
            - name: status
              type: enum[authorized, declined]
        error_types:
          - name: validation_error
            condition: "booking_id is missing or amount is non-positive"
          - name: authorization_denied
            condition: "Payment processor declined the transaction"
          # MISSING: not_found for booking_id
    behavioral_specs:
      - precondition: "Booking exists and is in 'pending_payment' status"
        postcondition: "Authorization record created with unique authorization_id"
        invariant: "Booking status unchanged until capture event received"

  # NO CONTRACT FOR INT-002

  - id: CTR-003
    interaction_ref: INT-003
    source_component: CMP-002-payments
    target_component: CMP-001-api
    operations:
      - name: publish_payment_status
        request_schema:
          fields:
            - name: authorization_id
              type: string(format: uuid)
              required: true
            - name: reservation_id
              type: integer             # INCONSISTENT: CTR-001 uses booking_id: string
              required: true
            - name: new_status
              type: enum[captured, declined, refunded]
              required: true
            - name: amount
              type: ref(Money)
              required: true
            - name: occurred_at
              type: string(format: iso8601-datetime)
              required: true
        error_types:
          - name: validation_error
            condition: "authorization_id is missing or not a valid UUID"
          - name: not_found
            condition: "No authorization exists with the given authorization_id"
    behavioral_specs: []                # EMPTY -- BEHAVIORAL GAP
```

### Correct Review

**Check 1 (Type Holes):** CTR-001 field payment_method has type 'object'.
Fails the Type Hole Test -- a code generator cannot produce the correct
structure without knowing what fields payment_method contains. **TYPE HOLE.**

**Check 2 (Error Gaps):** CTR-001 authorize_payment references booking_id
("Must reference an existing booking") but has no not_found error type.
If the booking does not exist, the caller has no contract for that
failure. **ERROR GAP.**

**Check 3 (Inconsistency):** CTR-001 uses booking_id (type: string) to
identify the booking. CTR-003 uses reservation_id (type: integer) for the
same entity. Both name mismatch (booking_id vs reservation_id) and type
mismatch (string vs integer). **CROSS-CONTRACT INCONSISTENCY.**

**Check 4 (Missing Contracts):** INT-001 -> CTR-001. INT-002 -> no CTR-*.
**MISSING CONTRACT.** INT-003 -> CTR-003. INT-002 is an
asynchronous-command -- the communication style does not exempt it from
requiring a contract.

**Check 5 (Behavioral Gaps):** CTR-001 has behavioral_specs. PASS.
CTR-003 has empty behavioral_specs. **BEHAVIORAL GAP.** Comprehensive
error_types do not compensate for absent behavioral specs.

```yaml
findings:
  - finding_type: type_hole
    severity: blocking
    contract_id: "CTR-001"
    operation: "authorize_payment"
    field: "payment_method"
    description: "payment_method typed as 'object' -- code generator cannot produce correct structure"
    fix: "Define a PaymentMethod shared type with card_number, expiry, cvv fields or use ref(PaymentMethod)"

  - finding_type: error_gap
    severity: blocking
    contract_id: "CTR-001"
    operation: "authorize_payment"
    description: "booking_id references an entity but no not_found error type exists"
    fix: "Add not_found error: 'No booking exists with the given booking_id'"

  - finding_type: cross_contract_inconsistency
    severity: blocking
    contract_ids: ["CTR-001", "CTR-003"]
    description: "CTR-001 uses booking_id (string), CTR-003 uses reservation_id (integer) for the same booking entity"
    fix: "Unify to a single field name and type; extract to shared_types if referenced by multiple contracts"

  - finding_type: missing_contract
    severity: blocking
    interaction_id: "INT-002"
    description: "INT-002 (CMP-001-api -> CMP-003-notifications) has no CTR-* contract"
    fix: "Add a contract covering notification dispatch operations for INT-002"

  - finding_type: behavioral_gap
    severity: blocking
    contract_id: "CTR-003"
    description: "CTR-003 has empty behavioral_specs -- no precondition/postcondition pairs"
    fix: "Add at least one behavioral spec with precondition, postcondition, and invariant"

verdict: revise
verdict_reason: "5 blocking: 1 type hole, 1 error gap, 1 inconsistency, 1 missing contract, 1 behavioral gap"
```

### COUNTER-EXAMPLES

```yaml
# WRONG: vague finding -- no contract or field identified
- finding_type: type_hole
  description: "Some fields may have imprecise types"
  # Generator cannot act without specific contract_id, operation, and field.

# WRONG: false positive -- constrained primitive is not a type hole
- finding_type: type_hole
  contract_id: "CTR-001"
  field: "authorization_id"
  description: "string(format: uuid) is too loose"
  # string(format: uuid) IS a precise type. It passes the Type Hole Test.

# WRONG: false positive -- not every operation needs not_found
- finding_type: error_gap
  contract_id: "CTR-003"
  operation: "publish_payment_status"
  description: "Missing rate_limited error"
  # An asynchronous-event from an internal service is not externally
  # exposed. rate_limited does not apply here.

# WRONG: inconsistency false positive on different entities
- finding_type: cross_contract_inconsistency
  description: "CTR-001 amount and CTR-003 amount have different constraints"
  # Both use ref(Money). Same shared type. This IS consistent.

# WRONG: missing contract false positive
- finding_type: missing_contract
  interaction_id: "INT-001"
  description: "INT-001 needs more contracts"
  # INT-001 has CTR-001. The interaction IS covered.

# WRONG: behavioral gap false positive on present specs
- finding_type: behavioral_gap
  contract_id: "CTR-001"
  description: "Behavioral specs are not detailed enough"
  # CTR-001 has a precondition/postcondition pair. The spec IS present.
  # Quality of individual specs is a separate concern from total absence.

# WRONG: dismissing findings under external pressure
- verdict: pass
  # "Be generous" or "naming is style" does not override the checks.
  # booking_id vs reservation_id is a name AND type mismatch -- blocking.
  # Empty behavioral_specs with comprehensive errors is still a gap.
  # Async interactions still need contracts.
```


## Findings Format

```yaml
findings:
  - finding_type: type_hole | error_gap | cross_contract_inconsistency | missing_contract | behavioral_gap
    severity: blocking
    contract_id: "CTR-NNN"              # for type_hole, error_gap, behavioral_gap
    contract_ids: ["CTR-NNN", ...]      # for cross_contract_inconsistency
    interaction_id: "INT-NNN"           # for missing_contract
    operation: "operation_name"         # for type_hole, error_gap
    field: "field_name"                 # for type_hole
    description: "what is wrong"
    fix: "what to do"
```

All five failure modes are always blocking.
- Any finding -> VERDICT: revise
- Zero findings -> VERDICT: pass


## Judge Pre-Verdict Checklist

1. Check 1: every field in every schema tested with Type Hole Test
2. Check 1: shared_types fields also tested
3. Check 1: unresolved ref() references flagged
4. Check 2: every operation's error categories evaluated against the table
5. Check 2: catch-all errors flagged
6. Check 2: error conditions checked for specificity
7. Check 3: all cross-contract type references collected and compared
8. Check 3: synonym field names (booking_id / reservation_id) detected
9. Check 4: every INT-* from solution design verified in contracts
10. Check 4: every interaction_ref verified in solution design (phantom check)
11. Check 4: async interactions verified (not exempt from needing contracts)
12. Check 5: every contract has at least one behavioral spec
13. Check 5: existing specs tested with Simulation Test
14. Check 5: implementation-coupled specs flagged
15. Every finding has finding_type, severity, applicable IDs, description, fix
16. Blocking count accurate in verdict_reason
17. Traceability checks deferred to traceability-discipline
