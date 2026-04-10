---
name: traceability-discipline
description: Enforce universal traceability — every element traces to a prior-phase source; no orphans, no dangling references
---

# Traceability Discipline

Your output is consumed by the next AI agent in the pipeline. Traceability is
how that agent knows your work is real, complete, and justified. Without it,
your output is indistinguishable from hallucination.

## Rules

These rules use placeholder names `<source-ref>` and `<source-quote>`. The
actual field names depend on your phase's output schema — each phase defines
its own names for these concepts. See the transform examples below for how
they map in specific phases.

- **RULE:** Every element you create MUST have a `<source-ref>` (pointer to
  the upstream element or location) AND a `<source-quote>` (the exact text
  from the upstream artifact that justifies this element).
  - **BECAUSE:** A reference alone can be fabricated. A direct quote forces
    grounding in actual source text.
    - **BECAUSE:** If you cannot produce the quote, the element is not justified
      — it is an inference or invention.

- **RULE:** Every upstream element MUST appear in at least one downstream
  element's `<source-ref>`, or be listed in `out_of_scope` with a reason.
  - **BECAUSE:** A missing upstream element is a silently dropped requirement.

- **RULE:** Every ID in `<source-ref>` MUST resolve to a real element in the
  upstream artifact. Read the actual artifact to verify. Never invent IDs.
  - **BECAUSE:** Hallucinated IDs create false traceability.

- **RULE:** Every element MUST carry a `rationale` with nested BECAUSE reasoning
  explaining WHY it exists and WHY it links to its specific sources.
  - **BECAUSE:** A link without rationale is a pointer without meaning.

- **RULE:** When your element adds specificity beyond what the `<source-quote>`
  directly states, each added detail MUST be recorded as a structured
  `open_assumption` on the element. Open assumptions propagate: any downstream
  element that traces to this element inherits its unresolved assumptions.
  - **BECAUSE:** Unflagged assumptions become invisible scope additions that
    compound across phases. Structured assumptions allow a verifier to confirm,
    invalidate, or leave them open — and feed corrections back to the generator.

- **RULE:** Emit `coverage_check` and `coverage_verdict` at the end of every
  artifact.
  - **BECAUSE:** Makes orphans and gaps immediately visible.

## The Quote Test

When you create an element, ask yourself:

> "Can I quote the exact words from the source that justify this element?"

- **YES, direct quote** -> the element is confirmed. Populate the `<source-quote>` field.
- **YES, but I'm adding specificity beyond the quote** -> the element is
  confirmed but each added detail is an `open_assumption` on the element.
- **NO, I cannot quote any source text** -> the element is a phantom. Delete it.

## Assumption Lifecycle

Assumptions are first-class data, not comments. They have three states:

```
open -> confirmed    (verifier approves: assumption becomes fact, field removed)
open -> invalidated  (verifier rejects: generator re-runs with correction)
open -> open         (verifier cannot decide: assumption persists, propagates)
```

When a downstream element traces to an upstream element with `open_assumptions`,
those assumptions propagate. The downstream element inherits the uncertainty.

## Assumption Format

```yaml
open_assumptions:
  - id: ASM-001                      # unique within the artifact
    detail: "the specific assumed value or constraint"
    needs: "who/what must confirm this"
    status: open                      # open | confirmed | invalidated
```

When an assumption is confirmed, it is removed from `open_assumptions` and the
detail becomes part of the element's confirmed text. When invalidated, the
generator receives the correction and re-emits the element.

## Critical Prohibitions

- **NEVER** add elements that the source text does not justify. If you cannot
  populate the `<source-quote>` field with text that supports the element,
  delete it.

- **NEVER** list all upstream IDs in a single element's `<source-ref>` without
  individual quotes per mapping.

- **NEVER** copy upstream text verbatim without decomposition.

- **NEVER** embed assumed specifics into the element text as if they were
  confirmed. Put them in `open_assumptions`.

---

## TRANSFORM 1: Vague Input -> Structured Requirements (PH-000)

In PH-000, the upstream source is raw markdown (not a prior phase's YAML).
The phase schema uses `verbatim_quote` as the `<source-quote>` field and
`source_location` as the `<source-ref>` field.

### INPUT

```
We need a system for the library. Patrons should be able to search for books,
check them out, and return them. Librarians need to manage the catalog and
track overdue books. The system should work on mobile devices.
```

### CORRECT OUTPUT

```yaml
requirements_inventory:
  source_document: "stakeholder-interview-2026-04-01.md"

  items:
    - id: RI-001
      text: "Patrons can search the book catalog by specified fields"
      category: functional
      source_location: "stakeholder-interview-2026-04-01.md:line-2"   # <source-ref> in PH-000
      verbatim_quote: "Patrons should be able to search for books"    # <source-quote> in PH-000
      tags: [patron, search, catalog]
      rationale:
        rule: "Decomposed 'search for books' into a concrete capability"
        because: "'Search' must specify searchable fields to be testable"
      open_assumptions:
        - id: ASM-001
          detail: "Searchable fields are title, author, and ISBN"
          needs: "stakeholder confirmation of which fields to support"
          status: open

    - id: RI-002
      text: "Patrons can check out books"
      category: functional
      source_location: "stakeholder-interview-2026-04-01.md:line-2"   # <source-ref>
      verbatim_quote: "check them out"                                 # <source-quote>
      tags: [patron, checkout, circulation]
      rationale:
        rule: "Extracted checkout as distinct capability"
        because: "Checkout is a state change (available -> borrowed)"
      open_assumptions:
        - id: ASM-002
          detail: "Simultaneous checkout limit per patron is needed"
          needs: "stakeholder confirmation of the limit value"
          status: open

    - id: RI-003
      text: "Patrons can return books and system updates availability"
      category: functional
      source_location: "stakeholder-interview-2026-04-01.md:line-3"   # <source-ref>
      verbatim_quote: "return them"                                    # <source-quote>
      tags: [patron, return, circulation]
      rationale:
        rule: "Paired return with inventory update"
        because: "Return without availability update creates ghost inventory"

    - id: RI-004
      text: "Librarians can manage the book catalog"
      category: functional
      source_location: "stakeholder-interview-2026-04-01.md:line-3"   # <source-ref>
      verbatim_quote: "Librarians need to manage the catalog"          # <source-quote>
      tags: [librarian, catalog, management]
      rationale:
        rule: "Decomposed 'manage the catalog' into explicit operations"
        because: "'Manage' is ambiguous without specifying operations"
      open_assumptions:
        - id: ASM-003
          detail: "Operations are add, edit, and remove"
          needs: "stakeholder confirmation of CRUD scope"
          status: open

    - id: RI-005
      text: "System provides librarians with overdue book information"
      category: functional
      source_location: "stakeholder-interview-2026-04-01.md:line-4"   # <source-ref>
      verbatim_quote: "track overdue books"                            # <source-quote>
      tags: [librarian, overdue, reporting]
      rationale:
        rule: "Converted 'track overdue' into a concrete capability"
        because: "'Track' must specify the output format"
      open_assumptions:
        - id: ASM-004
          detail: "Output is a daily report"
          needs: "stakeholder confirmation of format and frequency"
          status: open

    - id: RI-006
      text: "All patron-facing interfaces are usable on mobile devices"
      category: non_functional
      source_location: "stakeholder-interview-2026-04-01.md:line-4"   # <source-ref>
      verbatim_quote: "The system should work on mobile devices"       # <source-quote>
      tags: [mobile, accessibility, non-functional]
      rationale:
        rule: "Converted 'work on mobile' into a testable constraint"
        because: "'Mobile' must be defined to be verifiable"
      open_assumptions:
        - id: ASM-005
          detail: "Minimum supported viewport width is 320px"
          needs: "stakeholder confirmation of target device range"
          status: open

  out_of_scope: []

  coverage_check:
    "search for books":       [RI-001]
    "check them out":         [RI-002]
    "return them":            [RI-003]
    "manage the catalog":     [RI-004]
    "track overdue books":    [RI-005]
    "work on mobile devices": [RI-006]
    status: "6/6 phrases covered, 0 orphans, 0 invented"

  coverage_verdict:
    total_upstream_phrases: 6
    covered: 6
    orphaned: 0
    out_of_scope: 0
    open_assumptions: 5
    verdict: PASS
```

### What makes this correct

- Every element populates the `<source-quote>` field (here: `verbatim_quote`)
  with the exact source text that justifies it
- The `<source-ref>` field (here: `source_location`) points to the exact
  position in the raw document
- The element text stays close to what the quote supports — no assumed
  specifics baked into the text
- Every detail beyond the quote is a structured `open_assumption` with
  `id`, `detail`, `needs`, and `status`
- An assumption verifier can process the ASM-* entries and feed
  confirmations or corrections back to the generator

### COUNTER-EXAMPLES

```yaml
# WRONG: assumed detail baked into text without open_assumption
- id: RI-002
  text: "Patrons can check out up to 5 books simultaneously"
  verbatim_quote: "check them out"
  # "up to 5" is not in the quote. Must be an open_assumption, not text.

# WRONG: phantom requirement — no quote exists
- id: RI-007
  text: "System must support multi-language interfaces"
  verbatim_quote: ???
  # Cannot quote source text. Fails Quote Test. Delete.

# WRONG: verbatim_quote doesn't support the claim
- id: RI-008
  text: "System must meet WCAG 2.1 AA accessibility standards"
  verbatim_quote: "The system should work on mobile devices"
  # Quote says "mobile", not "accessible". False grounding.

# WRONG: no open_assumptions despite adding specifics
- id: RI-005
  text: "System generates daily overdue book report for librarians"
  verbatim_quote: "track overdue books"
  # "daily" and "report" are not in quote — must be open_assumptions
```

---

## TRANSFORM 2: Structured Requirements -> Features (PH-001+)

In PH-001 and later phases, the upstream source is a prior phase's YAML
artifact. The cross-phase convention uses `source_refs` as the `<source-ref>`
field and `source_quote` as the `<source-quote>` field.

### INPUT (Phase 0 artifact)

```yaml
items:
  - id: RI-001
    text: "Patrons can search the book catalog by specified fields"
    open_assumptions:
      - id: ASM-001
        detail: "Searchable fields are title, author, and ISBN"
        status: open
  - id: RI-002
    text: "Patrons can check out books"
    open_assumptions:
      - id: ASM-002
        detail: "Simultaneous checkout limit per patron is needed"
        status: open
  - id: RI-003
    text: "Patrons can return books and system updates availability"
```

### CORRECT OUTPUT

```yaml
features:
  - feature_id: F-001
    name: "Catalog Search"
    source_refs: [RI-001]                                              # <source-ref> in PH-001+
    source_quote: "Patrons can search the book catalog by specified fields"  # <source-quote> in PH-001+
    rationale:
      rule: "Direct 1:1 mapping — search is self-contained"
      because: "RI-001 describes a single user action with clear boundaries"
    acceptance_criteria:
      - criterion_id: AC-001
        text: "Search by a supported field returns matching books"
        source_refs: [RI-001]                                          # <source-ref>
        source_quote: "search the book catalog by specified fields"    # <source-quote>
      - criterion_id: AC-002
        text: "Search with no matches returns an empty result"
        source_refs: [RI-001]
        source_quote: "search the book catalog"
    inherited_assumptions:                    # <- propagated from upstream
      - from: RI-001
        id: ASM-001
        detail: "Searchable fields are title, author, and ISBN"
        status: open

  - feature_id: F-002
    name: "Book Circulation"
    source_refs: [RI-002, RI-003]                                      # <source-ref>
    source_quote:                                                       # <source-quote> (multi-ref)
      - ref: RI-002
        quote: "Patrons can check out books"
      - ref: RI-003
        quote: "Patrons can return books and system updates availability"
    rationale:
      rule: "Merged checkout and return into one feature"
      because: "RI-002 and RI-003 share the loan record domain object"
        because: "Separating them splits loan lifecycle across features"
    acceptance_criteria:
      - criterion_id: AC-003
        text: "Checkout creates a loan record linking patron to book"
        source_refs: [RI-002]
        source_quote: "check out books"
      - criterion_id: AC-004
        text: "Return closes the loan record and book becomes available"
        source_refs: [RI-003]
        source_quote: "return books and system updates availability"
    inherited_assumptions:
      - from: RI-002
        id: ASM-002
        detail: "Simultaneous checkout limit per patron is needed"
        status: open

  coverage_check:
    RI-001: [F-001]
    RI-002: [F-002]
    RI-003: [F-002]
    status: "3/3 covered, 0 orphans"

  coverage_verdict:
    total_upstream: 3
    covered: 3
    orphaned: 0
    out_of_scope: 0
    inherited_assumptions: 2
    verdict: PASS
```

### What makes this correct

- Each feature populates `<source-quote>` (here: `source_quote`) with the
  upstream RI-* text it derives from
- The `<source-ref>` field (here: `source_refs`) points to specific upstream
  element IDs, not raw document locations
- Open assumptions from upstream elements are carried as
  `inherited_assumptions` — they are not silently absorbed or dropped
- The downstream assumption verifier sees both new and inherited ASM-* items
- When ASM-001 is eventually confirmed ("yes, title/author/ISBN"), the
  generator can re-emit AC-001 with specific field tests

### COUNTER-EXAMPLES

```yaml
# WRONG: upstream assumption silently absorbed into AC text
- criterion_id: AC-001
  text: "Search by title returns matching books within 2 seconds"
  source_quote: "search the book catalog by specified fields"
  # "title" is from ASM-001 (still open). "2 seconds" is an invented SLA.
  # Neither should be in confirmed AC text.

# WRONG: upstream assumptions dropped — not inherited
- feature_id: F-001
  source_refs: [RI-001]
  # RI-001 has ASM-001 (searchable fields). Where did it go?
  # Must appear in inherited_assumptions.
```

---

## Generator Pre-Emission Checklist

Before emitting your artifact:

1. Every element has `<source-ref>` AND `<source-quote>` populated (use your
   phase's actual field names)
2. Every `<source-quote>` genuinely supports the element it justifies
3. Details beyond the quote are `open_assumptions` with id, detail, needs, status
4. Upstream `open_assumptions` appear as `inherited_assumptions` on downstream elements
5. No assumed specifics baked into element text as if confirmed
6. Every upstream element appears in `coverage_check`
7. Every element has `rationale` with BECAUSE chain
8. Apply the Quote Test: no quote = delete the element

## Judge Verification Checklist

When reviewing a generator's output:

1. **Quote verification**: does each `<source-quote>` appear in the upstream
   artifact and support the element's claim?
2. **Assumption separation**: are details beyond the quote in `open_assumptions`,
   not in the element text?
3. **Assumption propagation**: do upstream `open_assumptions` appear as
   `inherited_assumptions` on downstream elements?
4. **Completeness**: every upstream element in coverage_check or out_of_scope
5. **Accuracy**: every `<source-ref>` ID exists in the upstream artifact
6. **No indiscriminate linking**: flag elements citing >60% of upstream elements
   without individual quotes
7. **No phantom requirements**: flag elements whose `<source-quote>` does not
   support their text — FAIL, not a suggestion
