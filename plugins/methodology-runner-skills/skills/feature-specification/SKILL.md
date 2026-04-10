---
name: feature-specification
description: Group requirements into features with testable acceptance criteria and explicit dependencies
---

# Feature Specification

This skill governs the grouping and structuring discipline for PH-001
(Feature Specification). Its scope is the judgment calls that
generation_instructions do not cover: how to decide which RI-* items
belong together, how to write acceptance criteria that are binary
pass/fail, how to identify dependencies, and how to handle deferred
or excluded requirements.

Traceability mechanics -- source_refs, source_quote, coverage_check,
coverage_verdict, inherited_assumptions, and the Quote Test -- are
governed by the companion traceability-discipline skill loaded
alongside this one. This skill focuses on WHAT to group and HOW to
structure the output.


## Grouping Procedure

Walk the requirements inventory in ID order. For each RI-* item,
decide which feature it belongs to using these steps.

### Step 1: Identify the Domain Entity

What real-world object does this requirement operate on? Requirements
that create, read, update, or delete the SAME domain entity are
candidates for the same feature.

### Step 2: Check the User Flow

Does this requirement participate in the same end-to-end user flow as
other requirements already in a candidate feature? A "checkout flow"
might span cart, payment, and confirmation -- but only if they share
a transactional boundary (all succeed or all fail together).

### Step 3: Check the Actor

Different actors (end user vs. admin, human vs. system) operating on
the same entity are usually DIFFERENT features. "Users create tasks"
and "admins bulk-import tasks" share an entity but have different
acceptance criteria, error paths, and priorities.

### Step 4: Check the Feature Size

If adding this RI-* item would push the feature beyond 8 acceptance
criteria, the feature is too large. Split along the clearest
sub-boundary (e.g., separate CRUD from reporting, or read-only views
from mutations).

### Step 5: Non-Functional and Constraint Items

Non-functional requirements and constraints attach to the feature
they constrain, not to a separate feature. "Dashboard queries
complete in under 2 seconds" belongs to the Dashboard feature, not
to a standalone "Performance" feature. Exception: cross-cutting
constraints that affect ALL features (e.g., "all data encrypted at
rest") become their own feature only if they have independently
testable acceptance criteria.

### Step 6: Assumptions

Assumption items (category: assumption) do not become features.
They propagate as inherited_assumptions on every feature whose
source_refs include requirements that depend on the assumption.


## Acceptance Criteria Discipline

Every feature MUST have at least one acceptance criterion. Every
criterion MUST be binary pass/fail.

### The Testability Test

For each acceptance criterion, ask:

> "Can I write a test that returns PASS or FAIL from this criterion
> alone, without asking anyone what 'good' means?"

- **YES** -> the criterion is testable. Keep it.
- **NO** -> the criterion is vague. Rewrite it.

### Writing Concrete Criteria

Use given/when/then or condition/expected-result format:

```
VAGUE: "The system handles large datasets efficiently"
CONCRETE: "When the dataset contains 10,000 records, the query
           completes within 2 seconds"

VAGUE: "Search works well"
CONCRETE: "Searching by a supported field returns matching results;
           when no match exists, an empty list is returned"
```

### Prohibited Qualifiers

These words in an acceptance criterion signal vagueness:

| Vague qualifier | Replace with |
|----------------|-------------|
| fast, efficient, performant | specific latency or throughput bound |
| user-friendly, intuitive | specific observable behavior |
| secure, safe | specific control (encrypted, authenticated) |
| handles errors gracefully | specific error response format |
| scalable | specific capacity target |
| appropriate, reasonable | the actual value or threshold |


## Dependency Identification

A feature dependency means: feature B cannot be implemented or tested
without feature A being complete first.

### When to Declare depends_on

- **Output consumption:** B reads data that A creates.
- **Shared transactional state:** B mutates state that A owns.
- **Interface contract:** B calls an API or uses a component that A
  defines.

### When NOT to Declare depends_on

- Two features share a domain concept but neither consumes the
  other's output. They can be built in parallel.
- One feature is "nice to have" context for another but not
  structurally required.

### Cycle Prevention

Dependencies MUST form a DAG. If you detect a cycle (A depends on B
depends on A), identify which feature can function without the other
(even degraded) and remove that dependency edge.


## Out-of-Scope Discipline

Every RI-* item in the inventory MUST appear in exactly one of:
- A feature's source_refs
- The out_of_scope list with a justification

Silent omission -- an RI-* item in neither -- is the primary failure.

### Valid Justifications

- **Contradiction:** "Superseded by RI-013 which revises the target"
- **Deferral:** "Deferred to post-MVP: requires a scheduler not
  present in initial architecture"
- **Redundancy:** "Subsumed by RI-004 which states the same
  constraint with greater specificity"

### Invalid Justifications

- "Out of scope" (circular)
- "Not needed" (by whom? why?)
- "Future work" (when? what blocks it?)
- No justification at all


## TRANSFORM: Requirements -> Features

### INPUT (PH-000 artifact, abbreviated)

```yaml
items:
  - id: RI-001
    category: functional
    verbatim_quote: "Users shall create tasks with title, description, and due date"
  - id: RI-002
    category: functional
    verbatim_quote: "Users shall assign tasks to team members"
  - id: RI-003
    category: non_functional
    verbatim_quote: "The system should send email notifications when a task is assigned"
  - id: RI-004
    category: functional
    verbatim_quote: "Users shall mark tasks as complete"
  - id: RI-005
    category: functional
    verbatim_quote: "The system shall display a dashboard showing open tasks per user"
  - id: RI-006
    category: non_functional
    verbatim_quote: "Dashboard queries should complete in under 2 seconds"
  - id: RI-007
    category: assumption
    verbatim_quote: "Assuming the email server supports SMTP"
```

### CORRECT OUTPUT (grouping-relevant fields shown)

```yaml
features:
  - feature_id: FT-001
    name: "Task Lifecycle"
    source_refs: [RI-001, RI-002, RI-004]
    rationale:
      rule: "Grouped by shared domain entity and lifecycle"
      because: "All three mutate the task entity through lifecycle states"
    acceptance_criteria:
      - criterion_id: AC-001-01
        text: "Creating a task with title, description, and due date persists the task and returns a unique identifier"
        source_refs: [RI-001]
      - criterion_id: AC-001-02
        text: "Assigning a task records the assignee on the task"
        source_refs: [RI-002]
      - criterion_id: AC-001-03
        text: "Marking a task as complete changes its status and removes it from open task counts"
        source_refs: [RI-004]
    depends_on: []
    priority: must

  - feature_id: FT-002
    name: "Task Dashboard"
    source_refs: [RI-005, RI-006]
    rationale:
      rule: "Grouped by shared user flow; RI-006 constrains RI-005"
      because: "RI-005 defines the view; RI-006 defines its performance bound"
    acceptance_criteria:
      - criterion_id: AC-002-01
        text: "The dashboard displays open task count grouped by assigned user"
        source_refs: [RI-005]
      - criterion_id: AC-002-02
        text: "With 10,000 tasks, the dashboard query completes in under 2 seconds"
        source_refs: [RI-006]
    depends_on: [FT-001]
    priority: must

  - feature_id: FT-003
    name: "Assignment Notifications"
    source_refs: [RI-003]
    rationale:
      rule: "Separate feature -- different system boundary"
      because: "RI-003 crosses into an external email service, distinct from task CRUD"
    acceptance_criteria:
      - criterion_id: AC-003-01
        text: "When a task is assigned, an email is sent to the assignee with the task title"
        source_refs: [RI-003]
    depends_on: [FT-001]
    inherited_assumptions:
      - from: RI-007
        id: ASM-007
        detail: "the email server supports SMTP"
        status: open
    priority: should

out_of_scope: []
```

### What makes this correct

- RI-001, RI-002, RI-004 grouped by shared domain entity (task) and
  lifecycle. RI-003 NOT merged -- it crosses the email system
  boundary (Step 3: different actor, the email subsystem).
- RI-006 attached to FT-002 (Step 5: constraints attach to the
  feature they constrain), not a standalone "Performance" feature.
- RI-007 propagates as inherited_assumptions on FT-003 (Step 6).
- FT-002 depends_on FT-001: dashboard reads task data.
- Every AC is binary pass/fail. No vague qualifiers.

### COUNTER-EXAMPLES

```yaml
# WRONG: notification merged into task lifecycle
- feature_id: FT-001
  source_refs: [RI-001, RI-002, RI-003, RI-004]
  # RI-003 crosses the email system boundary. Mixing CRUD and
  # notification makes the feature untestable without an email server.

# WRONG: performance as standalone feature
- feature_id: FT-004
  name: "Performance Requirements"
  source_refs: [RI-006]
  # Constraints attach to the feature they constrain. A standalone
  # "Performance" feature has no testable behavior of its own.

# WRONG: vague acceptance criterion
- criterion_id: AC-001-01
  text: "Users can create tasks easily"
  # "Easily" is subjective. Fails the Testability Test.

# WRONG: orphaned requirement (appears in no feature and no out_of_scope)
features: [FT-001, FT-002]   # RI-003 missing
out_of_scope: []              # RI-003 also missing
# Silent omission. Every RI-* MUST appear somewhere.

# WRONG: circular dependency
- feature_id: FT-001
  depends_on: [FT-002]
- feature_id: FT-002
  depends_on: [FT-001]
  # Dashboard reads tasks but tasks do not need the dashboard.
  # Remove FT-001 -> FT-002.
```


## Generator Pre-Emission Checklist

1. Every RI-* appears in a feature's source_refs OR in out_of_scope
2. No feature has zero acceptance criteria
3. Every AC passes the Testability Test (binary pass/fail)
4. Every AC traces to specific RI-* items via source_refs
5. Dependencies form a DAG -- no cycles
6. Every depends_on ID resolves to an actual FT-* in the artifact
7. Every out_of_scope entry has a concrete justification
8. Assumptions propagate as inherited_assumptions, not as features
9. No feature exceeds 8 acceptance criteria
10. Traceability checks deferred to traceability-discipline
