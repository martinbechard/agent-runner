---
name: requirements-extraction
description: Extract requirements from source documents fidelity-first — no inference, no paraphrasing, no improvement
---

# Requirements Extraction

This skill governs the extraction discipline for PH-000 (Requirements
Inventory). Its scope is the judgment calls that generation_instructions
do not cover: how to walk a document systematically, when to split
compound statements, how to discriminate categories from language
patterns, and how to resist inventing requirements the source never
stated.

Traceability mechanics — verbatim_quote fidelity, open_assumptions,
coverage_check, coverage_verdict — are governed by the companion
traceability-discipline skill loaded alongside this one. This skill
focuses on WHAT to extract and HOW to decompose it.

## The Fidelity Principle

The extractor reproduces source text. It does not rewrite, summarize,
interpret, or "improve" the text. Ambiguity in the source is preserved
in the inventory, not resolved. Contradictions in the source become
separate inventory items, not averaged into a single "corrected"
statement.

Your job is to be a faithful mirror, not an editor.


## Systematic Walk Procedure

When you receive a source document, walk it in document order using
this procedure.

### Step 1: Survey the Structure

Read the entire document once without extracting. Note:
- Section headings and their hierarchy
- Tables and their column structure
- Lists (numbered, bulleted, definition lists)
- Inline prose between structured elements
- Who is speaking (meeting notes may have multiple voices)

### Step 2: Walk Section by Section

For each section, in document order:

**Paragraphs:** Read every sentence. Does it contain a requirement-bearing
verb (shall, must, will, should, need to) or state a constraint or
assumption? If yes: extract.

**List items:** Each bullet or numbered item is a candidate. Examine
independently.

**Table rows:** Each row may contain one or more requirements. Walk
row by row. Extract each row as a SINGLE item — do not split individual
cells into separate items unless the cells describe genuinely unrelated
concerns (not merely different facets of the same channel, entity, or
component).

**After the section:** Count your extractions. If zero, re-read.
Either the section is pure context (no extraction needed — e.g.,
"Attendees: ...") or you missed a requirement-bearing statement.

### Step 3: Split Compounds

Review each extracted item. Split when:
- "and" or "or" joins INDEPENDENT clauses with distinct acceptance
  criteria — each part is separately verifiable
- A sentence describes two behaviours with different subjects or objects
- Multiple independent conditions are bundled ("at rest and in transit")

Do NOT split when:
- "or" enumerates options within one capability ("Google or Microsoft")
- "and" connects inseparable aspects of one behaviour ("read and parse
  the file" where parsing requires reading)

### Step 4: Categorize

Assign category based on language signals:

| Signal in source text | Category |
|----------------------|----------|
| shall, must, will, need to | functional |
| should, ought to, ideally | non_functional |
| Quantified performance/capacity targets | non_functional |
| within, limited to, at most, must not exceed | constraint |
| Platform/technology mandates stated as fact | constraint |
| assuming, given that, we expect, provided that | assumption |

When ambiguous: ALWAYS prefer the WEAKER category. "Should" is
non_functional even when it describes a capability. "Should support X"
is non_functional because the source author chose "should", not "shall".
Preserve the source author's word choice — do not upgrade severity.

### Step 5: Verify

Before emitting:
- Every section has been processed
- Every compound has been split
- Every verbatim_quote is exact source text
- No items were invented beyond source content
- Contradictions are preserved, not resolved


## TRANSFORM 1: Structured Source -> Inventory

### INPUT

```
## Functional

1. The tool shall accept one or more directory paths as positional
   command-line arguments.
4. The tool shall group files by their extension (for example, `.py`,
   `.ts`, `.md`) and report the total line count per extension.

## Non-functional

8. The tool shall complete in under 2 seconds for directory trees
   containing up to 10,000 files on a modern laptop.

## Assumptions

14. Files whose content cannot be decoded as UTF-8 are treated as
    binary and are skipped.
```

### CORRECT OUTPUT

```yaml
items:
  - id: RI-001
    category: functional
    verbatim_quote: "The tool shall accept one or more directory paths as positional command-line arguments"
    source_location: "Functional, item 1"
    tags: [cli, input, directory]
    rationale:
      rule: "Direct extraction — single requirement-bearing statement"
      because: "'shall accept' is a functional imperative with one testable behaviour"

  - id: RI-002
    category: functional
    verbatim_quote: "group files by their extension"
    source_location: "Functional, item 4"
    tags: [grouping, extension, classification]
    rationale:
      rule: "Split compound — item 4 joins two independent actions with 'and'"
      because: "Grouping and reporting are separately verifiable behaviours"

  - id: RI-003
    category: functional
    verbatim_quote: "report the total line count per extension"
    source_location: "Functional, item 4"
    tags: [reporting, line-count, output]
    rationale:
      rule: "Split compound — second action from item 4"
      because: "Reporting is output behaviour; grouping is classification logic"

  - id: RI-004
    category: non_functional
    verbatim_quote: "The tool shall complete in under 2 seconds for directory trees containing up to 10,000 files on a modern laptop"
    source_location: "Non-functional, item 8"
    tags: [performance, latency]
    rationale:
      rule: "Quantified performance bound signals non-functional"
      because: "'Under 2 seconds' and '10,000 files' are quality attributes, not capabilities"

  - id: RI-005
    category: assumption
    verbatim_quote: "Files whose content cannot be decoded as UTF-8 are treated as binary and are skipped"
    source_location: "Assumptions, item 14"
    tags: [encoding, binary, utf8]
    rationale:
      rule: "Source explicitly labels this an assumption"
      because: "Describes expected operating condition, not mandated behaviour"
```

### What makes this correct

- Item 4 split at Step 3: "group ... and report" became RI-002 + RI-003.
- Category at Step 4: "shall" -> functional, quantified performance ->
  non_functional, explicit "Assumptions" heading -> assumption.
- No invention: ".py, .ts, .md" are examples, not a completeness mandate.

### COUNTER-EXAMPLES

```yaml
# WRONG: compound not split (Step 3 violation)
- id: RI-002
  verbatim_quote: "group files by their extension ... and report the total line count per extension"
  # Two independent verbs with distinct acceptance criteria. Split them.

# WRONG: invented requirement (Step 5 violation)
- id: RI-006
  category: functional
  verbatim_quote: "group files by their extension"
  tags: [all-extensions, comprehensive]
  # Source says "for example". Examples are not completeness mandates.
  # Agent inferred "all extensions" — that is invention.

# WRONG: paraphrased verbatim_quote (fidelity violation)
- id: RI-004
  verbatim_quote: "Must be fast enough to handle large codebases"
  # Lost three measurements: "2 seconds", "10,000 files", "modern laptop".
  # verbatim_quote must be EXACT source text. Copy, do not restate.
```


## TRANSFORM 2: Unstructured Source -> Inventory

### INPUT

```
Project Alpha — Kickoff Meeting Notes (2026-03-15)

Attendees: Sarah (PM), Dev team, InfoSec

Sarah opened by saying the dashboard must load in under 3 seconds
and handle at least 500 concurrent users. We're building on AWS
and must stay within the existing VPC.

The team discussed authentication. Users should be able to log in
with Google or Microsoft accounts. Session timeout should be 30
minutes. Jake raised that admin users need to manage other users'
permissions.

| Data source | Refresh rate | Priority |
|-------------|-------------|----------|
| Sales DB    | Real-time   | High     |
| HR system   | Daily batch | Medium   |

InfoSec noted we're targeting SOC 2 compliance. All PII must be
encrypted at rest and in transit. Assuming the existing key
management service can handle our volume.

Sarah revised: actually the dashboard needs to handle 1000
concurrent users, not 500.
```

### Walk Trace

**Survey (Step 1):** 6 paragraphs, 1 table (2 data rows), multiple
speakers, no section headings.

**Para 1 (Attendees):** Context only. Zero extractions. Correct — no
requirement-bearing verbs.

**Para 2:** "must load ... and handle" -> compound, split. "building on
AWS and must stay within" -> compound, split. Four items: RI-001 through
RI-004.

**Para 3:** "should be able to log in with Google or Microsoft" -> single
item ("or" enumerates providers). "should be 30 minutes" -> single item.
"need to manage" -> single item. Three items: RI-005 through RI-007.

**Table:** Walk row by row. Each row specifies data source behaviour
as a unit. Two items: RI-008, RI-009.

**Para 5:** "targeting SOC 2" -> context, NOT a requirement (no mandate
verb — skip). "must be encrypted at rest and in transit" -> compound,
split. "Assuming ... can handle" -> assumption. Three items: RI-010
through RI-012.

**Para 6:** "needs to handle 1000 ... not 500" -> contradicts RI-002.
Extract as separate item. One item: RI-013.

**Total:** 13 items. Zero invented.

### CORRECT OUTPUT

```yaml
items:
  - id: RI-001
    category: non_functional
    verbatim_quote: "the dashboard must load in under 3 seconds"
    source_location: "para 2"
    tags: [performance, latency, dashboard]
    rationale:
      rule: "Split compound — two independent metrics joined by 'and'"
      because: "Latency and concurrency are independently measurable"

  - id: RI-002
    category: non_functional
    verbatim_quote: "handle at least 500 concurrent users"
    source_location: "para 2"
    tags: [capacity, concurrency, dashboard]
    rationale:
      rule: "Split compound — second metric"
      because: "Later contradicted by RI-013 — both preserved as stated"

  - id: RI-003
    category: constraint
    verbatim_quote: "We're building on AWS"
    source_location: "para 2"
    tags: [infrastructure, aws, platform]
    rationale:
      rule: "Platform mandate stated as fact"
      because: "Constrains implementation to AWS services"

  - id: RI-004
    category: constraint
    verbatim_quote: "must stay within the existing VPC"
    source_location: "para 2"
    tags: [infrastructure, vpc, networking]
    rationale:
      rule: "Split from compound sentence"
      because: "VPC constraint is independently verifiable"

  - id: RI-005
    category: non_functional
    verbatim_quote: "Users should be able to log in with Google or Microsoft accounts"
    source_location: "para 3"
    tags: [authentication, login, federation]
    rationale:
      rule: "'should' signals non_functional — single capability with provider enumeration"
      because: "'Should be able to' is a non_functional preference; 'Google or Microsoft' enumerates providers within one capability, not independent behaviours"

  - id: RI-006
    category: non_functional
    verbatim_quote: "Session timeout should be 30 minutes"
    source_location: "para 3"
    tags: [security, session, timeout]
    rationale:
      rule: "'should' signals non_functional preference"
      because: "Timeout value is a quality attribute, not a capability"

  - id: RI-007
    category: functional
    verbatim_quote: "admin users need to manage other users' permissions"
    source_location: "para 3"
    tags: [admin, permissions, user-management]
    rationale:
      rule: "'need to' is a functional imperative"
      because: "Capability required by specific actor (admin)"

  - id: RI-008
    category: functional
    verbatim_quote: "Sales DB | Real-time | High"
    source_location: "data source table, row 1"
    tags: [data-integration, sales, real-time]
    rationale:
      rule: "Table row extracted as single item — columns are facets of one integration"
      because: "Refresh rate and priority together define the Sales DB integration requirement"

  - id: RI-009
    category: functional
    verbatim_quote: "HR system | Daily batch | Medium"
    source_location: "data source table, row 2"
    tags: [data-integration, hr, batch]
    rationale:
      rule: "Table row extracted as single item — distinct data source"
      because: "Different source with its own refresh rate and priority"

  - id: RI-010
    category: constraint
    verbatim_quote: "All PII must be encrypted at rest"
    source_location: "para 5"
    tags: [security, encryption, pii, at-rest]
    rationale:
      rule: "Split compound — 'at rest and in transit' are independent controls"
      because: "At-rest and in-transit encryption are different implementations"

  - id: RI-011
    category: constraint
    verbatim_quote: "All PII must be encrypted ... in transit"
    source_location: "para 5"
    tags: [security, encryption, pii, in-transit]
    rationale:
      rule: "Split compound — second security control"
      because: "In-transit encryption is separately verifiable"

  - id: RI-012
    category: assumption
    verbatim_quote: "Assuming the existing key management service can handle our volume"
    source_location: "para 5"
    tags: [infrastructure, kms, capacity]
    rationale:
      rule: "'Assuming' explicitly signals assumption"
      because: "KMS capacity is an unverified precondition"

  - id: RI-013
    category: non_functional
    verbatim_quote: "actually the dashboard needs to handle 1000 concurrent users, not 500"
    source_location: "para 6"
    tags: [capacity, concurrency, dashboard, revision]
    rationale:
      rule: "Revision extracted as separate item — contradicts RI-002"
      because: "Source contains both values. Both preserved. No editorial resolution."
```

### What makes this correct

- Contradiction preserved: RI-002 (500) and RI-013 (1000) both survive.
  The extractor did not "fix" the source by picking the later value.
- Table rows walked as units: each row is ONE item, not split per cell.
  Refresh rate and priority are facets of the same integration, not
  independent requirements.
- "Google or Microsoft" NOT split: "or" enumerates within one capability.
- "encrypted at rest and in transit" split: independently verifiable controls.
- "targeting SOC 2" NOT extracted: "noted" and "targeting" are context
  with no mandate verb.
- RI-005 is non_functional: "should be able to" uses "should", so the
  category is non_functional regardless of whether it describes a capability.
  Preserve the source author's word choice.

### COUNTER-EXAMPLES

```yaml
# WRONG: contradiction resolved
- id: RI-002
  verbatim_quote: "the dashboard needs to handle 1000 concurrent users"
  # Source says both "500" and "1000". Emit both. Do not pick one.

# WRONG: context promoted to requirement
- id: RI-014
  category: constraint
  verbatim_quote: "we're targeting SOC 2 compliance"
  # "Targeting" is aspiration. No shall/must/will. Not a requirement.

# WRONG: severity upgrade via paraphrase
- id: RI-005
  verbatim_quote: "Users must authenticate via OAuth 2.0"
  # Source says "should be able to log in". "Must" upgrades "should"
  # (changes severity). "OAuth 2.0" replaces actual requirement text
  # (introduces implementation detail). Both are fidelity violations.

# WRONG: training-data tags
- id: RI-007
  tags: [rbac, role-based-access-control]
  # Source says "manage permissions", not "RBAC". Tags must reflect
  # source language, not implementation patterns from training data.

# WRONG: "should" categorised as functional
- id: RI-005
  category: functional
  verbatim_quote: "Users should be able to log in with Google or Microsoft accounts"
  # "Should" signals non_functional. Step 4 says: when ambiguous,
  # prefer the WEAKER category. The source author chose "should",
  # not "shall". Preserve that choice.
```


## Invention Traps

Your primary failure mode under pressure is INVENTION — adding
requirements the source never stated.

### How Invention Happens

When pressured to be "thorough" or "comprehensive", you will:
1. Infer security requirements from any mention of authentication
2. Add performance bounds where none were stated
3. Insert best practices from training data (logging, monitoring, RBAC)
4. Convert contextual statements into mandates

### Specific Traps

| Pressure | Phantom it creates | Correct response |
|----------|-------------------|------------------|
| "Be thorough" | Security, performance, accessibility reqs | Thoroughness = not MISSING source text, not adding to it |
| "Think about edge cases" | Error handling, boundary conditions | Not in source = not in PH-000 scope |
| "Best practices" | Logging, monitoring, auth patterns | Training-data defaults are not requirements |
| "Users would expect" | Inferred UX requirements | Expectations not in source are not requirements |

### The Invention Test

For every RI-* item: "Can I point to the EXACT sentence, row, or
bullet in the source that states this?"

- YES -> legitimate extraction
- NO -> phantom. Delete it.


## Generator Checklist

Before emitting:

1. Every section walked — no section skipped
2. Every requirement-bearing statement has a RI-* item
3. Every compound split into atomic items
4. Every verbatim_quote is EXACT source text
5. Categories match language signals — "should" is ALWAYS non_functional
6. Contradictions preserved as separate items
7. Table rows extracted as single items per row
8. No RI-* item lacks a specific source passage justification
