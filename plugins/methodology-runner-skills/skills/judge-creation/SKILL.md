---
name: judge-creation
description: Use when writing or revising an LLM judge prompt for a methodology phase or prompt-runner validation step. Applies the lessons learned from PH-001 so the judge focuses on material defects, respects allowed elaboration, distinguishes definition-of-done criteria from test cases, and produces concrete revise feedback without looping on wording polish.
---

# Judge Creation

Use this skill when the task is to create or refine a judge / validation prompt.

## Goal

Write a judge prompt that:

- catches real semantic defects
- does not relitigate mechanical checks already handled elsewhere
- allows source-faithful elaboration when the phase is supposed to invent supporting detail
- asks for changes only when they are actually wrong or materially consequential
- produces revise feedback that a generator can act on directly

## Workflow

1. Identify the phase contract.
2. Separate mechanical checks from semantic checks.
3. State what kinds of invention or elaboration are allowed.
4. Define the semantic failure modes the judge should catch.
5. Add threshold rules so the judge does not churn on minor wording.
6. Require concrete corrective feedback with cited artifact IDs.

## Rules

- Start by telling the judge which files to read and which mechanical report is authoritative.
- If deterministic validation already ran, explicitly say the judge must trust that report for structural and count-based checks and must not duplicate them manually.
- Treat later-phase artifacts as elaboration layers when that phase is supposed to add supporting detail. Do not force verbatim restatement unless the phase contract requires it.
- If the phase artifact contains acceptance criteria, clarify whether they are:
  - definition-of-done criteria
  - executable test cases
  - or something else
- If they are not test cases, say so explicitly. This avoids the judge over-demanding literal commands, filenames, or harness details.
- Tell the judge what kinds of invention are allowed:
  - non-contradictory
  - directly or indirectly supportive of cited requirements
  - not unrelated scope
  - not weakening exact source constraints
- Tell the judge what kinds of invention are forbidden:
  - contradiction
  - exact-meaning drift
  - unsupported scope expansion
  - elaboration that no longer serves the cited requirements
- Add a materiality threshold:
  - only request a change if the artifact is wrong, contradictory, materially unsupported, or the change would materially affect downstream architecture or implementation
- Explicitly forbid wording-polish churn:
  - do not request wording polish, minor precision tweaks, or alternate phrasing unless the current wording is actually wrong or materially consequential
- Require the judge to cite exact IDs when available, such as:
  - `FT-*`
  - `AC-*`
  - `RI-*`
  - file paths

## Recommended Failure Modes

Use only the ones that actually fit the phase.

- vague completion criteria
- orphaned upstream inputs
- assumption conflicts
- scope creep
- missing dependencies
- exact-meaning drift
- unsupported restatement
- pseudo-objective constraints
- contradictory invention

## Corrective Feedback Format

When the judge finds a material issue, it should emit corrective guidance in this form:

- `RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT ...`
  - `BECAUSE: ...`

Use imperative, specific changes. Avoid generic complaints like "be clearer" or "be more precise."

## PH-001 Lessons To Reuse

These lessons came from the feature-specification phase and should be reused when applicable:

- Say explicitly whether acceptance criteria are feature-level completion criteria rather than test cases.
- Tell the judge that elaboration is allowed when it supports the cited requirements and does not contradict them.
- Tell the judge not to demand literal shell commands, exact filenames, or implementation form unless the source actually requires them.
- Tell the judge not to reject an artifact just because the phrasing differs from a verbatim source quote.
- Tell the judge to ask for change only when the issue is real or materially affects downstream architecture or implementation.
- Keep the judge focused on semantic readiness, not stylistic preference.

## Output

When using this skill, produce:

- the revised judge prompt text, or
- a concrete patch to the prompt file

Do not produce a design essay unless the user asks for one.
