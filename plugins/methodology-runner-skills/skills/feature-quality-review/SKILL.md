---
name: feature-quality-review
description: Evaluate feature specifications for testability, RI coverage, dependency completeness, and scope discipline
---

# Feature Quality Review

This skill governs the PH-001 judge's evaluation discipline. Review a
feature specification in three passes to find five failure modes.

Traceability mechanics (source_quote fidelity, source_refs accuracy,
coverage_check, phantom detection via the Quote Test) are governed by the
companion traceability-discipline skill. This skill covers the five
PH-001-specific failure modes that traceability-discipline does not.


## Pass 1: Coverage (Inventory -> Features)

Walk every RI-* item in the Phase 0 inventory. Verify it appears in at
least one feature's source_inventory_refs or in out_of_scope with a reason.

**Failure mode detected: Orphaned Inventory Items.**
An RI-* item in neither any feature nor out_of_scope is orphaned --
a silently dropped requirement. Always blocking.


## Pass 2: Scope (Features -> Inventory)

Walk every feature. For each:
1. Verify every source_inventory_refs ID exists in the inventory.
2. Read each AC's description. Verify its behavior traces to the
   referenced RI-* items' text.
3. When an AC uses threshold language (time, quantity, size), verify
   the AC's boundary semantics match the RI exactly. Boundary drift
   is scope creep even when the concept traces.

**Failure mode detected: Scope Creep.**
An AC whose behavior is not traceable to any RI-* item is scope creep.
The Quote Test applies: if you cannot quote upstream RI-* text justifying
the AC, it is scope creep. Always blocking.

Scope creep includes:
- **Invented behavior:** AC describes functionality absent from all RI-* items.
- **Boundary drift:** AC narrows or widens an RI threshold. "Up to X"
  (inclusive) rewritten as "more than X" (exclusive) changes which inputs
  pass. "At least X" rewritten as "exactly X" drops valid cases. The
  concept traces but the precision does not -- still scope creep.
- **Inverse inference:** AC states the negative-path outcome when the RI
  only defines the positive path (e.g., RI says "refund when cancelled
  before deadline"; AC adds "no refund after deadline").

Always blocking. Contradictions must be reconciled or recorded as
open_assumptions needing stakeholder resolution.


## Pass 3: Intra-Feature Quality

For each feature, check three things:

### 3a. Vague Acceptance Criteria

Flag any AC using subjective language without a measurable threshold:

| Vague qualifier | Requires |
|----------------|----------|
| fast, efficient, performant | specific latency or throughput bound |
| user-friendly, intuitive, easy | specific observable behavior |
| secure, safe | specific control (encrypted, authenticated) |
| handles errors gracefully | specific error response format |
| scalable | specific capacity target |
| appropriate, reasonable | the actual value or threshold |

Always blocking. A vague AC cannot be tested.

### 3b. Assumption Conflicts

For features sharing RI-* sources or dependency edges, collect all
open_assumptions, inherited_assumptions, and implicit assumptions in AC
text. Flag contradictions:
- **Format:** Feature A assumes JSON; Feature B assumes CSV for same data.
- **Ordering:** Feature A assumes it runs first; B has no dependency on A.
- **State:** Feature A assumes mutable records; B assumes immutable.

Always blocking. Contradictions must be reconciled or recorded as
open_assumptions needing stakeholder resolution.

### 3c. Missing Dependencies

If Feature A's ACs read data that Feature B's ACs produce, Feature B must
appear in Feature A's dependencies. Check for cycles -- dependencies must
form a DAG. Always blocking.


## REVIEW EXAMPLE

### Input: Phase 0 Inventory (abbreviated)

```yaml
items:
  - id: RI-001
    verbatim_quote: "Users shall create tasks with title and due date"
  - id: RI-002
    verbatim_quote: "Users shall mark tasks as complete"
  - id: RI-003
    verbatim_quote: "The system shall display a dashboard showing open tasks per user"
  - id: RI-004
    verbatim_quote: "Dashboard queries should complete in under 2 seconds"
  - id: RI-005
    verbatim_quote: "The system shall send email notifications when a task is assigned"
```

### Input: Flawed Feature Specification

```yaml
features:
  - id: FT-001
    name: "Task Management"
    source_inventory_refs: [RI-001, RI-002]
    acceptance_criteria:
      - id: AC-001-01
        description: "Creating a task persists it with title and due date"
      - id: AC-001-02
        description: "Tasks can be completed efficiently"
      - id: AC-001-03
        description: "Tasks can be archived after 90 days"
    dependencies: []

  - id: FT-002
    name: "Task Dashboard"
    source_inventory_refs: [RI-003]
    acceptance_criteria:
      - id: AC-002-01
        description: "Dashboard shows open task count per user"
    dependencies: []

out_of_scope: []
```

### Correct Review

**Pass 1 (Coverage):** RI-001 -> FT-001. RI-002 -> FT-001. RI-003 ->
FT-002. RI-004 -> nowhere. **ORPHANED.** RI-005 -> nowhere. **ORPHANED.**

**Pass 2 (Scope):** FT-001 AC-001-03 ("archived after 90 days") not
traceable to RI-001 or RI-002. **SCOPE CREEP.** FT-002 traces. PASS.

**Pass 3a (Vagueness):** AC-001-02 uses "efficiently." **VAGUE AC.**

**Pass 3b (Conflicts):** No assumption conflicts found.

**Pass 3c (Dependencies):** FT-002 reads task data produced by FT-001
but dependencies is empty. **MISSING DEPENDENCY.**

```yaml
findings:
  - finding_type: orphaned_inventory_item
    severity: blocking
    inventory_id: "RI-004"
    description: "RI-004 appears in no feature and not in out_of_scope"
    fix: "Assign to the feature it constrains or add to out_of_scope"

  - finding_type: orphaned_inventory_item
    severity: blocking
    inventory_id: "RI-005"
    description: "RI-005 appears in no feature and not in out_of_scope"
    fix: "Create a notification feature or add to out_of_scope with reason"

  - finding_type: scope_creep
    severity: blocking
    feature_id: "FT-001"
    criterion_id: "AC-001-03"
    description: "Archiving after 90 days not traceable to any RI-* item"
    fix: "Remove AC or trace to an existing RI-* item"

  - finding_type: vague_acceptance_criterion
    severity: blocking
    feature_id: "FT-001"
    criterion_id: "AC-001-02"
    description: "'efficiently' is subjective with no measurable threshold"
    fix: "Replace with concrete behavior or remove qualifier"

  - finding_type: missing_dependency
    severity: blocking
    feature_id: "FT-002"
    description: "FT-002 reads task data from FT-001 but FT-001 not in dependencies"
    fix: "Add FT-001 to FT-002's dependencies"

verdict: revise
verdict_reason: "5 blocking: 2 orphaned, 1 scope creep, 1 vague AC, 1 missing dep"
```

### COUNTER-EXAMPLES

```yaml
# WRONG: vague finding
- finding_type: orphaned_inventory_item
  description: "Some requirements may be missing"
  # No inventory_id. Generator cannot act on this.

# WRONG: false positive -- AC is justified by source
- finding_type: scope_creep
  criterion_id: "AC-001-01"
  description: "title and due date not in requirements"
  # RI-001 says "with title and due date". Read the full text.

# WRONG: dependency without data-flow basis
- finding_type: missing_dependency
  feature_id: "FT-001"
  description: "FT-001 should depend on FT-002"
  # Task management does not consume dashboard data.

# WRONG: boundary drift missed
- verdict: pass
  # RI says "up to 24 hours" (inclusive). AC says "more than 24
  # hours" (exclusive). The concept traces but the boundary shifted
  # -- the 24-hour mark changed from eligible to ineligible.
  # This is scope creep (boundary drift), not a pass.
```


## Findings Format

```yaml
findings:
  - finding_type: vague_acceptance_criterion | orphaned_inventory_item | assumption_conflict | scope_creep | missing_dependency
    severity: blocking
    feature_id: "FT-NNN"          # omit for orphaned_inventory_item
    criterion_id: "AC-NNN-NN"     # for vague_acceptance_criterion, scope_creep
    inventory_id: "RI-NNN"        # for orphaned_inventory_item only
    description: "what is wrong"
    fix: "what to do"
```

All five failure modes are always blocking.
- Any finding -> VERDICT: revise
- Zero findings -> VERDICT: pass


## Judge Pre-Verdict Checklist

1. Pass 1: every RI-* checked against features and out_of_scope
2. Pass 2: every feature's ACs validated against RI-* text; threshold
   boundaries checked for drift (inclusive vs exclusive, at-least vs exactly)
3. Pass 3a: ACs checked for vagueness using qualifiers table
4. Pass 3b: assumptions compared across features with shared sources
5. Pass 3c: dependencies checked via data-flow analysis
6. Every finding has finding_type, severity, applicable IDs, description, fix
7. Blocking count accurate in verdict_reason
8. Traceability checks deferred to traceability-discipline
