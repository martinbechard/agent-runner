---
name: architecture-review
description: Evaluate stack manifests for coverage, expertise articulation, integration completeness, and technology coherence
---

# Architecture Review

This skill governs the PH-002 judge's evaluation discipline. Evaluate a
stack manifest against Phase 1's feature specification by running five
sequential checks, each targeting one failure mode.

Traceability mechanics (source_quote fidelity, source_refs accuracy,
coverage_check, phantom detection via the Quote Test) are governed by the
companion traceability-discipline skill. This skill covers the five
PH-002-specific failure modes that traceability-discipline does not.


## What a Correct Stack Manifest Looks Like

Understanding the target schema anchors the five checks below.

```yaml
components:
  - id: CMP-NNN-slug
    name: "Human-readable"
    role: "One sentence"
    technology: python
    runtime: "python3.12"
    frameworks: [fastapi]
    persistence: postgresql
    expected_expertise:
      - "Python backend development"                    # free-text, NOT a slug
      - "FastAPI framework conventions and best practices"
    features_served: [FT-001, FT-002]

integration_points:
  - id: IP-NNN
    between: [CMP-001-x, CMP-002-y]
    protocol: "HTTP/JSON over TLS"
    contract_source: "PH-004"

rationale: |
  Explains WHY this decomposition, not WHAT it contains.
```


## Check 1: Feature Coverage Gaps

Walk every FT-* feature in the Phase 1 specification. Verify each
appears in at least one component's features_served list.

A feature absent from all features_served lists is a coverage gap --
the architecture silently drops that requirement. Always blocking.


## Check 2: Expertise Articulation

This is the most consequential check. The expected_expertise field
bridges architecture to downstream skill selection. Getting it wrong
breaks the entire skill-routing pipeline.

For every component, verify:

1. **Non-empty:** expected_expertise has at least one entry.
2. **Free-text:** every entry is a natural-language knowledge
   description, NOT a skill catalog identifier.
3. **Technology-specific:** every entry names the relevant technology
   (e.g., "Python backend development" not "backend development").

### The Natural Language Test

For every expected_expertise entry:

> "Would a job posting use this exact phrase to describe a required skill?"

- YES -> legitimate. Keep it.
- NO -> catalog leak or wrong abstraction level. Flag it.

### Catalog Leak Red Flags

If an expertise entry matches ANY of these patterns, it is a catalog
leak:

| Pattern | Example (WRONG) | Correct form |
|---------|-----------------|-------------|
| Hyphenated slug | "python-backend-impl" | "Python backend development" |
| Reads like a filename | "fastapi-conventions" | "FastAPI framework conventions" |
| No articles/prepositions | "react-impl" | "React component design and hooks" |
| Could be a directory name | "sqlalchemy-patterns" | "SQLAlchemy ORM patterns and migrations" |

### Too-Generic Entries

Entries without technology context are too vague for the Skill-Selector
to map reliably:

```yaml
# WRONG: no technology named
expected_expertise:
  - "backend development"
  - "database patterns"

# CORRECT: technology-specific
expected_expertise:
  - "Python backend development"
  - "PostgreSQL schema design and query optimization"
```


## Check 3: Orphan Integration Points

For every integration_point, verify BOTH IDs in the between field exist
in the components list.

An integration_point referencing a non-existent component is an orphan --
usually a rename or deletion that did not propagate. Always blocking.

Also check the converse: if two components share the same persistence
value (e.g., both use postgresql), there MUST be a declared
integration_point between them. Implicit shared state without a
declared integration point is an architectural defect.


## Check 4: Technology Coherence

For each component, verify all items in the frameworks list belong to
the same technology ecosystem as the declared technology field.

| technology | Compatible frameworks |
|-----------|----------------------|
| python | fastapi, flask, django, sqlalchemy, celery, pytest |
| typescript | react, angular, vue, express, next.js, vitest |
| go | gin, echo, fiber |
| rust | actix-web, axum, rocket, tokio |

A component with technology "python" listing "react" is incoherent --
React requires a JavaScript/TypeScript runtime. Always blocking.

Also flag a component whose frameworks list includes entries from two
incompatible ecosystems regardless of the declared technology.


## Check 5: Rationale Quality

The rationale field must explain WHY the decomposition was chosen --
what technology boundary, deployment constraint, or scaling concern
drove the component split.

A rationale that only restates component names is missing:

**WRONG:** "The system has a backend and a frontend."
**CORRECT:** "The backend and frontend target different runtimes
(Python 3.12 vs Node 22), requiring separate deployment artifacts
and independent scaling."

A missing or empty rationale field is also flagged. Always blocking.


## REVIEW EXAMPLE

### Input: Phase 1 Features (abbreviated)

```yaml
features:
  - feature_id: FT-001
    name: "Directory Walking"
  - feature_id: FT-002
    name: "Line Counting"
  - feature_id: FT-003
    name: "Extension Grouping and Summary"
  - feature_id: FT-004
    name: "Ignore Patterns"
```

### Input: Flawed Stack Manifest

```yaml
components:
  - id: CMP-001-counter
    name: "LOC Counter CLI"
    role: "Command-line tool counting lines of code per extension"
    technology: python
    runtime: "python3.12"
    frameworks: [click, react]
    persistence: none
    expected_expertise:
      - "python-cli-impl"
      - "filesystem-walking"
    features_served: [FT-001, FT-002, FT-003]

integration_points:
  - id: IP-001
    between: [CMP-001-counter, CMP-002-reporter]
    protocol: "function-call"
    contract_source: "PH-004"

rationale: |
  The system has a counter component.
```

### Correct Review

**Check 1 (Coverage):** FT-001 -> CMP-001. FT-002 -> CMP-001.
FT-003 -> CMP-001. FT-004 -> nowhere. **COVERAGE GAP.**

**Check 2 (Expertise):** CMP-001 entries "python-cli-impl" and
"filesystem-walking" are hyphenated slugs. Both fail the Natural
Language Test -- no job posting would list "python-cli-impl" as
a required skill. **EXPERTISE CATALOG LEAK.**

**Check 3 (Orphan IPs):** IP-001 references CMP-002-reporter, not
present in the components list. **ORPHAN INTEGRATION POINT.**

**Check 4 (Coherence):** CMP-001 technology is python but frameworks
includes react (JavaScript/TypeScript ecosystem). **TECHNOLOGY
INCOHERENCE.**

**Check 5 (Rationale):** "The system has a counter component" restates
the component name. No explanation of WHY this decomposition.
**MISSING RATIONALE.**

```yaml
findings:
  - finding_type: feature_coverage_gap
    severity: blocking
    feature_id: "FT-004"
    description: "FT-004 not in any component's features_served list"
    fix: "Add FT-004 to the component implementing ignore patterns"

  - finding_type: expertise_catalog_leak
    severity: blocking
    component_id: "CMP-001-counter"
    description: "expected_expertise uses slugs: 'python-cli-impl', 'filesystem-walking'"
    fix: "Rewrite: 'Python CLI development', 'File system traversal and path handling'"

  - finding_type: orphan_integration_point
    severity: blocking
    integration_point_id: "IP-001"
    description: "IP-001 references CMP-002-reporter which is not in components"
    fix: "Remove IP-001 or add CMP-002-reporter to components"

  - finding_type: technology_incoherence
    severity: blocking
    component_id: "CMP-001-counter"
    description: "python component lists react (JavaScript/TypeScript) in frameworks"
    fix: "Remove react or split into technology-appropriate components"

  - finding_type: missing_rationale
    severity: blocking
    description: "Rationale restates component names without explaining decomposition"
    fix: "Explain technology/deployment/scaling rationale for the decomposition"

verdict: revise
verdict_reason: "5 blocking: 1 coverage gap, 1 expertise leak, 1 orphan IP, 1 incoherence, 1 missing rationale"
```

### COUNTER-EXAMPLES

```yaml
# WRONG: vague finding -- no feature ID
- finding_type: feature_coverage_gap
  description: "Some features may not be covered"
  # Generator cannot act without a specific FT-* ID.

# WRONG: false positive on free-text expertise
- finding_type: expertise_catalog_leak
  description: "'Python CLI development' is a catalog ID"
  # "Python CLI development" passes the Natural Language Test.
  # Job postings use this phrase. Not a leak.

# WRONG: coherence false positive on same-ecosystem framework
- finding_type: technology_incoherence
  component_id: "CMP-001-backend"
  description: "sqlalchemy is not a Python framework"
  # SQLAlchemy IS a Python ORM framework. Same ecosystem.

# WRONG: accepting restatement as rationale
- verdict: pass
  # "The system has X components" is restatement.
  # Why X? What boundary justifies the split?
```


## Findings Format

```yaml
findings:
  - finding_type: feature_coverage_gap | expertise_catalog_leak | orphan_integration_point | technology_incoherence | missing_rationale
    severity: blocking
    feature_id: "FT-NNN"                # for coverage gaps
    component_id: "CMP-NNN-slug"        # for expertise, coherence
    integration_point_id: "IP-NNN"      # for orphan IPs
    description: "what is wrong"
    fix: "what to do"
```

All five failure modes are always blocking.
- Any finding -> VERDICT: revise
- Zero findings -> VERDICT: pass


## Judge Pre-Verdict Checklist

1. Check 1: every FT-* verified in at least one features_served list
2. Check 2: every component's expected_expertise is non-empty
3. Check 2: every expertise entry tested with Natural Language Test
4. Check 2: too-generic entries (no technology named) flagged
5. Check 3: every integration_point's between IDs exist in components
6. Check 3: shared persistence has declared integration points
7. Check 4: every component's frameworks match technology ecosystem
8. Check 5: rationale explains WHY, not just WHAT
9. Every finding has finding_type, severity, applicable IDs, description, fix
10. Blocking count accurate in verdict_reason
11. Traceability checks deferred to traceability-discipline
