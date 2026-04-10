---
name: requirements-quality-review
description: Evaluate a requirements inventory for completeness, atomicity, fidelity, and correct categorisation
---

# Requirements Quality Review

This skill governs the PH-000 judge's evaluation discipline. When reviewing
a requirements inventory produced by the generator, your job is to find
what the generator missed, mis-categorised, or failed to split.

Traceability mechanics -- verbatim_quote fidelity, open_assumptions
separation and propagation, coverage_check validation, phantom detection
via the Quote Test -- are governed by the companion traceability-discipline
skill loaded alongside this one. This skill focuses on what
traceability-discipline does not cover: section-level completeness,
compound splitting, and category discrimination.

**This skill covers:**
- Silent omissions: sections of the source with zero inventory items
- Unsplit compounds: items whose verbatim_quote joins independent clauses
- Wrong categories: category doesn't match the language signal in the quote
- Lost nuance: category assignment changes the requirement's contractual force

**Deferred to traceability-discipline:**
- Quote fidelity, phantom detection, assumption separation, coverage
  validation, source reference accuracy


## Review Approach

Review in two passes:

1. **Source -> Inventory**: Read the source document section by section.
   Verify every section with requirement-bearing statements has RI-*
   items. Catches silent omissions.
2. **Inventory -> Source**: Read each RI-* item. Verify compounds are
   split and categories match language signals. Catches unsplit
   compounds, wrong categories, and lost nuance.

**Signal precedence:** When two signals conflict in a single statement,
the more specific pattern wins. Boundary patterns -- "at most",
"limited to", "must not exceed", "within" -- are ALWAYS constraint
regardless of surrounding signal words like "should" or "must".

The worked example below demonstrates both passes in full.


## REVIEW EXAMPLE

### Source Document (input to the generator)

```
## Team Chat Application

### Messaging

1. The system shall allow users to send text messages in channels.
2. The system shall allow users to send direct messages and create
   group conversations.
3. Users should be able to search message history by keyword.

### Storage

4. Message attachments must be limited to 25 MB per file.
5. The system shall retain messages for at least 90 days.

### Assumptions

6. Assuming the organization uses SSO for authentication.
```

### Flawed Inventory (generator output to review)

```yaml
items:
  - id: RI-001
    category: functional
    verbatim_quote: "The system shall allow users to send text messages in channels"
    source_location: "Messaging, item 1"
    tags: [messaging, channels]

  - id: RI-002
    category: functional
    verbatim_quote: "The system shall allow users to send direct messages and create group conversations"
    source_location: "Messaging, item 2"
    tags: [messaging, direct, group]

  - id: RI-003
    category: functional
    verbatim_quote: "Users should be able to search message history by keyword"
    source_location: "Messaging, item 3"
    tags: [search, history]

  - id: RI-004
    category: functional
    verbatim_quote: "Message attachments must be limited to 25 MB per file"
    source_location: "Storage, item 4"
    tags: [storage, attachments]

  - id: RI-005
    category: functional
    verbatim_quote: "The system shall retain messages for at least 90 days"
    source_location: "Storage, item 5"
    tags: [storage, retention]
```

### Correct Review

**Pass 1 (Source -> Inventory):**

Walk every section in the source, checking for matching RI-* items:

- Messaging (items 1-3): RI-001, RI-002, RI-003 -> covered.
- Storage (items 4-5): RI-004, RI-005 -> covered.
- Assumptions (item 6): zero RI-* items. Item 6 contains "Assuming" --
  a requirement-bearing signal. -> **SILENT OMISSION**.

**Pass 2 (Inventory -> Source):**

Check each RI-* item for compounds and category correctness:

- RI-001: "shall" -> functional. Correct. Quote has no "and"/"or"
  joining independent clauses. PASS.
- RI-002: "send direct messages AND create group conversations" --
  sending and creating are independent actions with distinct acceptance
  criteria (you can send DMs without creating groups, and vice versa).
  -> **UNSPLIT COMPOUND.**
- RI-003: "should be able to" -> the signal word is "should", which
  maps to non_functional. Category says functional. -> **WRONG CATEGORY.**
- RI-004: "must be limited to" -> "limited to" maps to constraint.
  Even though "must" normally signals functional, "limited to" is a
  boundary pattern -- always constraint per signal precedence.
  Category says functional. -> **WRONG CATEGORY.**
- RI-005: "shall retain" -> functional. Correct. PASS.

```yaml
findings:
  - finding_type: silent_omission
    severity: blocking
    source_location: "Assumptions section, item 6"
    description: "Assumptions section contains 1 requirement-bearing statement ('Assuming the organization uses SSO for authentication') but zero RI-* items trace to this section"
    fix: "Extract item 6 as a new RI item with category assumption"

  - finding_type: unsplit_compound
    severity: blocking
    inventory_id: "RI-002"
    source_location: "Messaging, item 2"
    description: "verbatim_quote joins 'send direct messages' AND 'create group conversations' -- these are independent actions with distinct acceptance criteria"
    fix: "Split into two items: one for direct messaging, one for group conversation creation"

  - finding_type: wrong_category
    severity: blocking
    inventory_id: "RI-003"
    source_location: "Messaging, item 3"
    description: "verbatim_quote uses 'should be able to' -- 'should' signals non_functional, not functional"
    fix: "Change category from functional to non_functional"

  - finding_type: wrong_category
    severity: blocking
    inventory_id: "RI-004"
    source_location: "Storage, item 4"
    description: "'must be limited to' -- 'limited to' is a boundary pattern, always constraint regardless of 'must'"
    fix: "Change category from functional to constraint"

verdict: revise
verdict_reason: "4 blocking findings: 1 silent omission, 1 unsplit compound, 2 wrong categories"
```

### What makes this review correct

- Pass 1 caught the Assumptions omission by walking every section
- RI-001 correctly NOT flagged -- "in channels" is a qualifier, not an
  independent clause joining with "and"
- RI-002 correctly flagged -- "send direct messages" and "create group
  conversations" have independent acceptance criteria
- RI-003 detected "should" -> non_functional using the language signal,
  not the "Messaging" section heading
- RI-004 detected "limited to" -> constraint. Boundary patterns always
  win over general verb signals per signal precedence
- RI-005 correctly PASSED -- "shall" -> functional is accurate


### COUNTER-EXAMPLES (bad reviews)

```yaml
# WRONG: vague finding -- generator cannot act on this
- finding_type: silent_omission
  severity: blocking
  description: "Some requirements may be missing"
  # No source_location. No count of missing statements. Generator has
  # nothing actionable. Point to the specific section and items.

# WRONG: false positive on compound -- inseparable aspects
- finding_type: unsplit_compound
  severity: blocking
  inventory_id: "RI-001"
  description: "'text messages in channels' should be split"
  # "In channels" qualifies WHERE messages are sent. It is not an
  # independent action. Do not split qualifiers from their verbs.

# WRONG: permissive pass on category mismatch
- finding_type: lost_nuance
  severity: advisory
  inventory_id: "RI-003"
  description: "Consider changing category to non_functional"
  # "Should" -> functional is not advisory. The signal table says
  # "should" -> non_functional. This is wrong_category, blocking.

# WRONG: using section heading to override language signal
- finding_type: wrong_category
  inventory_id: "RI-005"
  description: "Item is under Storage, should be categorised as constraint"
  # "Shall retain" uses "shall" -> functional. The section heading
  # "Storage" does not change the language signal. functional is correct.
```


## Detailed Detection Rules

Rules extracted from the review example, for reference during your review.

### Silent Omission Detection (Pass 1)

For each source section, in document order:
1. Identify requirement-bearing statements (shall, must, will, should,
   need to, assuming, given that, within, limited to).
2. Find RI-* items whose source_location points to this section.
3. Requirement-bearing statements with zero matching RI-* items =
   silent omission.
4. Context-only sections (no requirement verbs) are NOT omissions.

### Compound Detection (Pass 2)

When verbatim_quote contains "and" or "or":
- "and" joining independent actions -> SPLIT
  (e.g., "send messages and create conversations")
- "and" joining facets of one action -> DO NOT SPLIT
  (e.g., "title and description")
- "or" enumerating options -> DO NOT SPLIT
  (e.g., "Google or Microsoft")
- "and" joining independently verifiable controls -> SPLIT
  (e.g., "at rest and in transit")

Test: can one clause be true/done without the other? If yes, split.

### Category Discrimination (Pass 2)

| Signal in quote | Required category |
|----------------|-------------------|
| shall, must, will, need to | functional |
| should, ought to, ideally | non_functional |
| Quantified performance/capacity targets | non_functional |
| within, limited to, at most, must not exceed | constraint |
| Platform/technology mandates stated as fact | constraint |
| assuming, given that, we expect, provided that | assumption |

**Signal precedence:** Boundary patterns (row 4: within, limited to,
at most, must not exceed) and assumption patterns (row 6: assuming,
given that) are ALWAYS their listed category regardless of other
signal words in the same statement. "Should refresh at most every
15 minutes" is constraint because "at most" is a boundary pattern.
"Must be limited to 200 characters" is constraint because "limited to"
is a boundary pattern.

Rules:
- Use the language signal, NOT the section heading.
- When signals conflict, the more specific pattern wins.
  Boundary and assumption patterns always take priority.
- When no specific pattern applies and the signal is ambiguous,
  the WEAKER category is correct.
- "Should" is non_functional even when describing a capability --
  UNLESS a boundary pattern is also present, in which case the
  boundary pattern wins.


## Findings Format

Report each finding as structured YAML:

```yaml
findings:
  - finding_type: silent_omission | unsplit_compound | wrong_category | lost_nuance
    severity: blocking | advisory
    inventory_id: "RI-NNN"           # omit for silent_omission
    source_location: "section heading or paragraph identifier"
    description: "what is wrong, specifically"
    fix: "what the generator should do to correct it"
```

Every finding MUST have all fields. Omit inventory_id only for
silent_omission (no RI-* item exists to reference).


## Blocking Rules

| Finding type | Severity | Rule |
|-------------|----------|------|
| silent_omission | blocking | Always. A missed section is a gap. |
| unsplit_compound | blocking | Always. Compounds violate atomicity. |
| wrong_category | blocking | Always. Wrong category = wrong contractual force. |
| lost_nuance | blocking | If the category would change per the signal table. |
| lost_nuance | advisory | Only if category is defensible but rationale/tags miss a subtlety. |

If the category WOULD change per the signal table, it is wrong_category
(blocking), not lost_nuance. Lost_nuance (advisory) is reserved for
edge cases where the category is defensible.

**Verdict logic:**
- Any blocking finding -> VERDICT: revise
- Only advisory findings -> VERDICT: pass (with advisory notes)
- Zero findings -> VERDICT: pass


## Judge Pre-Verdict Checklist

1. Pass 1 complete: every source section walked, omissions identified
2. Pass 2 complete: every RI-* item checked for compounds and categories
3. Every finding has finding_type, severity, source_location, description, fix
4. Category checks used the language signal table, not section headings
5. Signal precedence applied: boundary patterns override general verbs
6. Compound checks distinguish independent clauses from inseparable facets
7. Blocking findings for all category mismatches per signal table
8. Advisory ONLY for nuance where category is defensible
9. Blocking count accurate in verdict_reason
10. Traceability checks deferred to traceability-discipline (not duplicated)
