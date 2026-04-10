---
name: solution-design-review
description: Evaluate solution designs for orphan components, god components, missing interactions, implicit state sharing, and untraced features
---

# Solution Design Review

This skill governs the PH-003 judge's evaluation discipline. Review a
solution design artifact against the Phase 1 feature specification and
Phase 2 stack manifest by building an index, then running five sequential
checks, each targeting one failure mode.

Traceability mechanics (source_quote fidelity, source_refs accuracy,
coverage_check, phantom detection via the Quote Test) are governed by the
companion traceability-discipline skill. This skill covers the five
PH-003-specific failure modes that traceability-discipline does not.


## What a Correct Solution Design Looks Like

Understanding the target schema anchors the five checks below.

```yaml
components:
  - component_id: CMP-NNN
    name: string
    description: string
    responsibilities:
      - string                    # 1-7 concrete verb-phrases
    technology_constraints: []

interactions:
  - interaction_id: INT-NNN
    from_component: CMP-NNN      # initiator
    to_component: CMP-NNN        # receiver (different from initiator)
    communication_style: synchronous-request-response | asynchronous-event | asynchronous-command | streaming | shared-state
    data_summary: string          # WHAT flows, domain terms only
    features_served: [FT-NNN]

feature_realization_map:
  - feature_id: FT-NNN
    participating_components: [CMP-NNN]
    interaction_sequence: [INT-NNN]
    notes: string

external_dependencies:
  - dependency_id: EXT-NNN
    name: string
    description: string
    features_dependent: [FT-NNN]
    assumption_refs: []
```


## Step 0: Build Index

Before running any check, enumerate every element. This prevents
accidentally skipping components, features, or interactions.

1. List all CMP-* from the components section
2. List all FT-NNN from the Phase 1 feature specification
3. List all INT-* from the interactions section
4. For each CMP-*, collect which FT-NNN features it participates in
   (via feature_realization_map entries)
5. For each CMP-*, extract domain nouns from responsibilities
6. For each INT-*, note the two connected components and the domain
   nouns in data_summary

Work from the index for all subsequent checks. Do NOT re-read the
artifact mid-check -- the index is the source of truth for element
enumeration.


## Check 1: Orphan Components

Walk every CMP-* in the index. For each component, check its feature
participation list from Step 0.

A component is orphaned when:
- It appears in ZERO feature_realization_map entries, OR
- Every feature_realization_map entry that references it uses a FT-NNN
  that does not exist in the Phase 1 feature specification

An orphan component has no reason to exist in the design. It was either
left behind after a revision or was invented without a feature driver.

**Always blocking.** A component without feature justification cannot
be implemented, tested, or validated.


## Check 2: God Components

Using the index, count the total number of distinct FT-NNN features in
Phase 1. For each CMP-*, count how many distinct features it participates
in.

**The 60% Rule:** If a component participates in more than 60% of all
features, it is a god component. It likely conflates multiple concerns
and needs decomposition.

| Total features | 60% threshold | God if participates in |
|---------------|--------------|----------------------|
| 3 | 1.8 | 2 or more |
| 5 | 3.0 | 4 or more |
| 8 | 4.8 | 5 or more |
| 10 | 6.0 | 7 or more |

Round UP: if the threshold is 1.8, a component participating in 2
features is a god component.

**Always blocking.** A god component indicates the architecture failed
to separate concerns. The fix is a PH-002 revision to split the
component, not a PH-003 workaround.

### WRONG: False Positive Below Threshold

```yaml
# 10 features, CMP-001-gateway participates in 5 (50%).
# 50% < 60%. Not a god component.
# A gateway legitimately touches many features -- only flag at >60%.
```


## Check 3: Missing Interactions

For every pair of components that co-participate in the same
feature_realization_map entry (both in participating_components for the
same FT-NNN), verify there is at least one INT-* interaction between
them in either direction.

Also check: if any component lists another in its dependencies, there
must be at least one INT-* interaction between them.

**A co-participation or dependency edge without a declared interaction
is a missing interaction.** The design claims the components collaborate
but does not specify HOW.

**Always blocking.** Without a declared interaction, the interface
contract (PH-004) cannot be written.

### Detection Procedure

1. Build a set of all component pairs that co-participate in any feature
2. Build a set of all component pairs connected by dependency edges
3. Union these two sets
4. For each pair, search the index for an INT-* connecting those two
   components (in either direction)
5. Any pair without a matching INT-* is a missing interaction


## Check 4: Implicit State Sharing

Using the domain nouns from the index (Step 0), identify cases where
two components both reference the same data entity but no INT-* between
them transfers or synchronizes that entity.

### Structural vs. Incidental Sharing

Not every shared domain noun is implicit state sharing. Two components
might both mention "users" in their responsibilities without either one
reading or writing user data that the other component needs.

**The Structural Sharing Test:**

> "Does component A need data that component B produces or owns
> (or vice versa) in order to fulfill its responsibilities?"

- **YES** -> structural sharing. There must be a declared INT-* or
  external_dependency through which that data flows.
- **NO** -> incidental. Both components happen to reference the same
  domain concept but do not exchange data for it. Not a finding.

### CORRECT: Structural Sharing Flagged

```yaml
# CMP-001 responsibility: "Persists order lifecycle state changes"
# CMP-002 responsibility: "Queries order history for reporting"
# CMP-002 NEEDS order data that CMP-001 PRODUCES.
# No INT-* between them transfers order data.
# -> IMPLICIT STATE SHARING. Flag it.
```

### CORRECT: Incidental Sharing NOT Flagged

```yaml
# CMP-001 responsibility: "Validates guest eligibility for bookings"
# CMP-002 responsibility: "Ranks search results by relevance and price"
# Both mention "guests" in context, but CMP-002 does not need
# guest eligibility data from CMP-001, nor does CMP-001 need
# search ranking data from CMP-002.
# -> Incidental. Do NOT flag.
```

### WRONG: Flagging Incidental Sharing

```yaml
# CMP-002-search: "Matches guest search criteria"
# CMP-003-payments: "Authorizes payment holds against guest payment methods"
# Both mention "guest" but search criteria (guest count, dates) and
# payment methods are completely different data entities that happen
# to belong to the same domain actor.
# CMP-002-search does NOT need payment method data from CMP-003-payments.
# -> Incidental. This is a FALSE POSITIVE.
```

**Always blocking when structural.** Either declare an explicit
interaction for the shared data, or add an external_dependency that
both components access through declared interactions.

### Detection Procedure

1. For each component pair, find domain nouns in common (from index)
2. For each shared noun, apply the Structural Sharing Test
3. For structural matches, verify an INT-* exists between them whose
   data_summary references that data entity
4. If no such INT-* exists, flag as implicit state sharing


## Check 5: Untraced Features

Walk every FT-NNN from the Phase 1 feature specification (using the
index). Verify each appears in at least one feature_realization_map
entry.

A feature absent from all feature_realization_map entries is untraced --
the design silently drops that requirement. This is the feature-level
analog of Check 1's component-level orphan.

**Always blocking.** An untraced feature has no design path from
requirement to implementation.


## REVIEW EXAMPLE

### Input: Phase 1 Features (abbreviated)

```yaml
features:
  - feature_id: FT-001
    name: "Task Creation"
  - feature_id: FT-002
    name: "Task Assignment"
  - feature_id: FT-003
    name: "Task Dashboard"
  - feature_id: FT-004
    name: "Email Notifications"
  - feature_id: FT-005
    name: "Task Archival"
```

### Input: Flawed Solution Design

```yaml
components:
  - component_id: CMP-001-api
    name: "Task API"
    responsibilities:
      - "Validates incoming task requests against domain rules"
      - "Persists task lifecycle state changes to the data store"
      - "Queries and aggregates task data for dashboard views"
      - "Dispatches assignment notifications"
      - "Generates archival reports"

  - component_id: CMP-002-worker
    name: "Background Worker"
    responsibilities:
      - "Processes scheduled archival of completed tasks"
      - "Queries task completion data for archival decisions"

  - component_id: CMP-003-audit
    name: "Audit Logger"
    responsibilities:
      - "Records all task state transitions for compliance"

interactions:
  - interaction_id: INT-001
    from_component: CMP-001-api
    to_component: CMP-002-worker
    communication_style: asynchronous-command
    data_summary: "Archival request: task IDs and retention policy"
    features_served: [FT-005]

feature_realization_map:
  - feature_id: FT-001
    participating_components: [CMP-001-api]
    interaction_sequence: []
  - feature_id: FT-002
    participating_components: [CMP-001-api]
    interaction_sequence: []
  - feature_id: FT-003
    participating_components: [CMP-001-api]
    interaction_sequence: []
  - feature_id: FT-005
    participating_components: [CMP-001-api, CMP-002-worker]
    interaction_sequence: [INT-001]
```

### Correct Review

**Index:**
- Components: CMP-001-api, CMP-002-worker, CMP-003-audit
- Phase 1 features: FT-001 through FT-005 (5 total)
- Interactions: INT-001 (CMP-001-api -> CMP-002-worker)
- Participation: CMP-001-api in FT-001,FT-002,FT-003,FT-005 (4). CMP-002-worker in FT-005 (1). CMP-003-audit in none (0).
- Domain nouns: CMP-001-api: task, dashboard, notifications, archival. CMP-002-worker: task, archival. CMP-003-audit: task.

**Check 1 (Orphan Components):** CMP-001-api -> 4 features. Present.
CMP-002-worker -> 1 feature. Present. CMP-003-audit -> 0 features.
**ORPHAN COMPONENT.**

**Check 2 (God Components):** 5 features total. 60% threshold = 3.
CMP-001-api participates in 4 features (80%). **GOD COMPONENT.**

**Check 3 (Missing Interactions):** FT-005 pair {CMP-001-api,
CMP-002-worker}: INT-001 exists. PASS. No other co-participations.

**Check 4 (Implicit State Sharing):** CMP-001-api "Persists task
lifecycle state changes." CMP-002-worker "Queries task completion data
for archival decisions." CMP-002-worker NEEDS task completion data that
CMP-001-api PRODUCES. Structural Sharing Test: YES. INT-001 data_summary
says "Archival request: task IDs and retention policy" -- this transfers
archival requests, NOT task completion data. **IMPLICIT STATE SHARING.**

CMP-003-audit "Records all task state transitions." This component
shares "task" with CMP-001-api, but CMP-003-audit is already flagged
as an orphan with no feature justification. The implicit sharing is
moot -- the orphan finding takes precedence. Do NOT double-flag
unless the component has feature justification.

**Check 5 (Untraced Features):** FT-001 -> present. FT-002 -> present.
FT-003 -> present. FT-004 -> nowhere. **UNTRACED FEATURE.** FT-005 ->
present.

```yaml
findings:
  - finding_type: orphan_component
    severity: blocking
    component_id: "CMP-003-audit"
    description: "CMP-003-audit appears in no feature_realization_map entry"
    fix: "Map to a feature or remove the component"

  - finding_type: god_component
    severity: blocking
    component_id: "CMP-001-api"
    description: "CMP-001-api participates in 4 of 5 features (80%), exceeds 60% threshold"
    fix: "Escalate to PH-002 for component decomposition"

  - finding_type: implicit_state_sharing
    severity: blocking
    component_ids: ["CMP-001-api", "CMP-002-worker"]
    shared_entity: "task completion data"
    description: "CMP-002-worker reads task completion data but no interaction supplies it; INT-001 only carries archival requests"
    fix: "Add an interaction for CMP-002-worker to query task completion data from CMP-001-api, or declare an external dependency for the shared data store"

  - finding_type: untraced_feature
    severity: blocking
    feature_id: "FT-004"
    description: "FT-004 (Email Notifications) absent from all feature_realization_map entries"
    fix: "Add FT-004 realization entry with participating components and interactions"

verdict: revise
verdict_reason: "4 blocking: 1 orphan component, 1 god component, 1 implicit state sharing, 1 untraced feature"
```

### What makes this review correct

- **Index built first:** all components, features, interactions enumerated
  before any check ran
- **Orphan detected by participation count:** CMP-003-audit has 0 features
- **God computed correctly:** 4/5 = 80% > 60% with threshold at 3
- **Missing interaction check passed:** the only co-participating pair
  (CMP-001-api, CMP-002-worker) has INT-001
- **Implicit sharing distinguished structural from incidental:**
  CMP-002-worker genuinely needs task completion data that CMP-001-api
  produces. CMP-003-audit shares "task" incidentally but is already
  orphaned -- double-flagging avoided.
- **Untraced detected:** FT-004 absent from all entries

### COUNTER-EXAMPLES

```yaml
# WRONG: vague finding -- no component ID
- finding_type: orphan_component
  description: "Some components may not be needed"
  # Generator cannot act without a specific CMP-* ID.

# WRONG: false positive on god component below threshold
- finding_type: god_component
  component_id: "CMP-002-worker"
  description: "CMP-002-worker participates in too many features"
  # CMP-002-worker participates in 1 of 5 features (20%).
  # Well below 60%. Not a god component.

# WRONG: missing interaction false positive when interaction exists
- finding_type: missing_interaction
  description: "CMP-001-api and CMP-002-worker have no interaction"
  # INT-001 connects them. Read the interactions list.

# WRONG: flagging incidental noun sharing as implicit state sharing
- finding_type: implicit_state_sharing
  component_ids: ["CMP-001-api", "CMP-003-audit"]
  shared_entity: "task"
  description: "Both reference tasks"
  # CMP-003-audit is orphaned (no feature justification).
  # Even if it weren't, both mentioning "task" does not mean they
  # need each other's task data. Apply the Structural Sharing Test.

# WRONG: ignoring implicit state sharing
- verdict: pass
  # CMP-002-worker reads task completion data with no declared
  # source interaction. This is implicit state sharing, not a pass.

# WRONG: untraced feature false positive
- finding_type: untraced_feature
  feature_id: "FT-001"
  description: "FT-001 not fully realized"
  # FT-001 has a feature_realization_map entry. It IS traced.
  # Quality of realization is a different concern.
```


## Findings Format

```yaml
findings:
  - finding_type: orphan_component | god_component | missing_interaction | implicit_state_sharing | untraced_feature
    severity: blocking
    component_id: "CMP-NNN"            # for orphan, god
    component_ids: ["CMP-NNN", ...]    # for missing interaction, implicit state sharing
    feature_id: "FT-NNN"              # for untraced feature
    shared_entity: "domain noun"       # for implicit state sharing
    description: "what is wrong"
    fix: "what to do"
```

All five failure modes are always blocking.
- Any finding -> VERDICT: revise
- Zero findings -> VERDICT: pass


## Judge Pre-Verdict Checklist

1. Step 0: index built -- all CMP, FT, INT enumerated with participation and domain nouns
2. Check 1: every CMP-* verified in at least one feature_realization_map entry
3. Check 1: every referenced FT-NNN verified to exist in Phase 1
4. Check 2: participation percentages computed against Phase 1 feature count
5. Check 2: 60% threshold applied with round-up
6. Check 3: all co-participating component pairs have a declared INT-*
7. Check 3: all dependency edges have a declared INT-*
8. Check 4: Structural Sharing Test applied -- incidental sharing not flagged
9. Check 4: structural shared nouns without connecting INT-* flagged
10. Check 5: every FT-NNN from Phase 1 verified in feature_realization_map
11. Every finding has finding_type, severity, applicable IDs, description, fix
12. Blocking count accurate in verdict_reason
13. Traceability checks deferred to traceability-discipline
