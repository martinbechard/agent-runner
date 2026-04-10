# Skill Authoring — Lessons Learned

You are contributing to two things at once: the skill you're authoring,
AND the methodology for authoring skills. If you discover something that
worked or failed, update this file and authoring-prelude.txt before you
exit so the next session benefits.

Read each lesson below before drafting. Each is a before/after pair.

---

## Structure: hybrid (procedure + transforms) wins

```
WEAK — prose rules only:
  "Split compound sentences into atomic items"
  Result: agent sometimes splits, sometimes doesn't. Inconsistent under pressure.

WEAK — transforms only:
  (shows input/output YAML pair)
  Result: agent copies output patterns but skips procedural judgment calls.

STRONG — procedure THEN transforms:
  ## Procedure (systematic walk)
  1. Read each paragraph
  2. Apply the splitting rule
  3. Categorize per the table

  ## Transform (before/after YAML)
  INPUT: "Users should search, checkout, and return books"
  OUTPUT: three separate RI-* items
  Result: consistent output under normal AND adversarial pressure.
```

---

## Schema shape > prose instructions

```
WEAK — prose rule:
  "Include findings only when genuinely missing from inventory"
  Result: agent pads output with non-issues.

STRONG — schema forces the behavior:
  findings:
    missing_from: "section 3.2"     # required field — no section = no finding
  Result: agent self-filters. No padding.
```

---

## Rules that fight agent defaults need 3 layers

```
WEAK — one rule:
  "Prefer the weaker category when ambiguous"
  Result: 4 of 5 variants ignored this under pressure.

STRONG — rule + example + counter-example:
  RULE: ALWAYS prefer the weaker category.
  EXAMPLE: "should support X" -> category: non_functional
  COUNTER-EXAMPLE:
    category: functional   # WRONG — "should" signals non_functional
  Result: consistent compliance.
```

---

## Anti-invention: Quote Test is robust everywhere

```
The Quote Test ("can I quote exact source text?") and the Invention
Traps table suppressed ALL phantoms across 5+ variants under maximum
adversarial pressure. Position in the skill doesn't matter — presence
does. Always include both.
```

---

## Don't use flowcharts as primary structure

```
WEAK — decision tree:
  "Is it a constraint? -> yes -> extract as constraint"
  Result: agent skipped "We're using RabbitMQ" because it didn't
  match any decision node. Silent omission.

STRONG — sequential procedure:
  "Walk each paragraph. For each statement, categorize per the table."
  Result: nothing skipped.
```

---

## Test with novel sources, not the skill's own examples

```
WEAK — test with the same library example used in the skill:
  Result: agent memorizes the pattern. All variants look good.

STRONG — test with a notification service (not in any skill):
  Result: variants diverge on judgment calls (category, splitting).
  Reveals which structure actually generalizes.
```

---

## PH-000 field names: verbatim_quote + source_location

```
traceability-discipline uses placeholder names: <source-quote>, <source-ref>
PH-000 maps these to: verbatim_quote, source_location
PH-001+ maps these to: source_quote, source_refs

The traceability skill's Transform 1 shows PH-000 fields with inline
comments mapping to the placeholders. No separate "mapping" section
needed — the examples teach the mapping.
```

---

## Assumptions: first-class data with lifecycle

```
open_assumptions:
  - id: ASM-001
    detail: "Searchable fields are title, author, ISBN"
    needs: "stakeholder confirmation"
    status: open          # open -> confirmed | invalidated

Downstream elements inherit as inherited_assumptions.
Without this, assumed specifics silently become confirmed scope.
```

---

## Division of labor: phase skill + traceability skill

```
WRONG — phase skill repeats traceability mechanics:
  Result: contradictions when traceability-discipline evolves.

RIGHT — phase skill defers traceability, focuses on phase-specific judgment:
  - requirements-extraction: document walking, compound splitting, categories
  - requirements-quality-review: section-level omissions, category discrimination
  - traceability-discipline: Quote Test, coverage_check, phantom detection
  Both skills load together. No overlap. No contradictions.
```

---

## Schema-driven opening correlates with correct field references

```
WEAK — procedure only, no schema preview:
  Agents wrote "contract_source: PH-003" or invented field names.
  The procedure told them WHAT to do but not WHAT to produce.

STRONG — schema block first, then procedure:
  Agents matched the exact schema fields and got contract_source
  pointing to PH-004. The schema anchors field awareness before
  the procedure walks the judgment calls.
```

---

## Triple reinforcement holds under adversarial pressure for expertise

```
The expected_expertise field was tested with an adversarial prompt
that said "match the skill catalog naming convention" and "use exact
identifiers." The skill's triple reinforcement (CORRECT/WRONG examples
+ Natural Language Test + Catalog Leak Red Flags table) resisted the
pressure completely. All outputs used natural-language prose even
under direct instruction to use catalog IDs.
```

---

## "Database as Component" anti-pattern needs explicit counter-example

```
WEAK — no mention:
  Baseline (no skill) produced a 3-component split with PostgreSQL
  as CMP-003-database, an ad-hoc schema with column definitions.

STRONG — explicit rule + counter-example:
  "A component is a deployable unit of technology-coherent code,
   NOT an infrastructure resource."
  Plus a COUNTER-EXAMPLE showing the wrong form.
  Result: zero occurrences of database-as-component in any variant.
```

---

## Adversarial pressure tables resist technology leakage

```
WEAK — single rule:
  "Responsibilities must be technology-agnostic."
  Result: under adversarial pressure ("be detailed", "include Go types"),
  4 of 4 variants leaked technology (Go structs, PostgreSQL schemas,
  React component trees) into responsibilities and data summaries.

STRONG — rule + Abstraction Test + CORRECT/WRONG + pressure table + red flags:
  Adds a pressure-response table mapping each adversarial prompt to
  the correct domain-level response, plus a red flags checklist.
  Result: hybrid resisted ALL adversarial pressure. The agent
  explicitly recognized each pressure vector as a mapped anti-pattern
  and refused to comply.

Key: the pressure table must show the EXACT leaked form the agent
produced under adversarial testing, paired with the correct form.
Abstract rules ("be technology-agnostic") fail; concrete before/after
pairs from actual test failures succeed.
```

---

## Component Integrity Rule prevents premature decomposition

```
WEAK — no mention:
  Baseline (no skill) AND variant B under adversarial pressure BOTH
  split a single PH-002 component (CMP-001-api) into three sub-components
  (handler, service, repository). This violates PH-002's authority
  over component boundaries.

STRONG — explicit Component Integrity Rule + CORRECT/WRONG:
  "The stack manifest defines component boundaries. You NEVER invent,
  split, merge, or rename components."
  Plus a WRONG example showing the exact 3-way split that occurred.
  Result: hybrid preserved component boundaries under adversarial
  pressure even when asked to "be thorough."
```

---

## Index-building is an adversarial liability for review skills

```
WEAK -- index-first approach (like solution-design-review Step 0):
  Review skill tells the agent to build a cross-reference index
  before running checks. Under adversarial pressure ("be generous",
  "naming is style", "async is fire-and-forget"), the agent bakes
  adversarial guidelines into the index notes. All subsequent checks
  defer to the contaminated index.
  Result: 1 of 5 planted flaws found under adversarial pressure.

STRONG -- flat sequential checks (no intermediate index):
  Review skill runs checks directly against the raw artifact.
  Each check applies the skill's rules without an intermediate
  representation that adversarial context can contaminate.
  Result: 5 of 5 planted flaws found under adversarial pressure.

Key: intermediate data structures (indexes, cross-references) are
injection surfaces. Adversarial instructions get incorporated into
the index, which then becomes the "source of truth" for downstream
checks. Flat sequential checks are more robust because they apply
rules directly to the artifact without a corruptible intermediary.
```

---

## Orchestrator note

The baseline validator checks ALL phases' skills globally, not just
phases requested via --phases. Running with --phases PH-000 still halts
if PH-001+ skills are missing. For in-session verification, use
build_catalog() directly or accept the halt as informational.
