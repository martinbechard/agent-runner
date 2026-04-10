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

## Orchestrator note

The baseline validator checks ALL phases' skills globally, not just
phases requested via --phases. Running with --phases PH-000 still halts
if PH-001+ skills are missing. For in-session verification, use
build_catalog() directly or accept the halt as informational.
