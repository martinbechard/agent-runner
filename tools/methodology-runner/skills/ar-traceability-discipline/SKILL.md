---
name: ar-traceability-discipline
description: Preserve source coverage and downstream justification across methodology phases without changing the authoritative artifact schema. Use when generating or judging a phase artifact from upstream requirements, features, architecture, design, contracts, simulations, implementation evidence, or verification evidence.
metadata:
  category: development-practice
---

# Traceability Discipline

Keep every material downstream claim connected to real upstream evidence while
respecting the current phase's output contract.

This is an agent-runner-specific runtime skill. It is intentionally distinct
from any portable or user-scope traceability skill because methodology-runner
phase schemas and deterministic validators own the concrete evidence fields.

## Contract Boundary

- Treat the phase prompt and its output schema as authoritative.
- Use only the traceability fields and identifiers defined by that schema.
- Do not add generic `source_quote`, `open_assumptions`, `coverage_check`,
  `coverage_verdict`, or rationale fields unless the phase schema requires them.
- Do not force one phase's traceability representation onto another phase.
- Preserve exact bounds, qualifiers, exclusions, and prohibitions from upstream
  evidence even when the downstream phase is allowed to elaborate.

## Generator Workflow

1. Identify the upstream units, constraints, and identifiers that the phase must
   preserve.
2. Map each material downstream unit to the strongest available upstream
   evidence using the current schema's fields.
3. Cover every required upstream unit through the schema's supported coverage
   mechanism, or record an allowed exclusion when the schema provides one.
4. Keep supported elaboration distinguishable from upstream facts. Do not turn
   an implementation choice into a source requirement.
5. Before returning, verify that every emitted reference resolves, required
   upstream coverage is complete, and no unsupported claim was introduced.

## Judge Workflow

1. Use deterministic validation as authoritative for reference syntax, schema,
   counts, and coverage checks that it already performs.
2. Review semantic traceability: confirm that cited upstream evidence actually
   supports the downstream claim and that important qualifiers were preserved.
3. Check for omitted upstream obligations, invented references, unsupported
   scope, indiscriminate linking, and elaboration presented as sourced fact.
4. Before reporting a gap, check whether the same downstream-actionable meaning
   is already covered elsewhere in the artifact.
5. Request correction only when the traceability defect is material to later
   design, implementation, operation, or verification.

## Rules

- Never invent an upstream identifier or cite an identifier that does not
  resolve.
- Never attach every upstream identifier to an element merely to make it appear
  covered.
- Do not require verbatim quotations when the phase schema uses identifier-based
  traceability or another evidence form.
- Do not require per-element rationale or artifact-level coverage objects when
  the phase schema does not define them.
- Do not reject allowed, non-contradictory elaboration solely because it is not
  a verbatim upstream statement.
- Do reject elaboration that contradicts, weakens, or expands the upstream
  contract without support.

## Result

Generators return the phase artifact in its exact required schema. Judges return
the required verdict with concise, evidence-backed corrections for material
traceability defects only.
