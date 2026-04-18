---
name: artifact-generator
description: Use when writing or revising an LLM generator prompt for a methodology phase or prompt-runner generation step. Defines the phase contract, exact output schema, allowed invention boundary, and generator-side discipline so the artifact is phase-ready before judging.
---

# Artifact Generator

Use this skill when the task is to create or refine a generator / artifact-production prompt.

## Goal

Write a generator prompt that:

- produces the exact phase artifact at the correct path
- makes the phase contract explicit
- defines what invention, elaboration, or decomposition is allowed
- enforces the exact output schema and ordering
- avoids draft churn, overbuilding, and source-contract drift

## Workflow

1. Identify the phase contract.
2. State the required inputs and output path.
3. State whether the phase is extraction, elaboration, decomposition, planning, or verification.
4. Define the exact output schema and required field ordering.
5. Define the allowed invention boundary for this phase.
6. Add the phase-specific anti-drift rules that keep the generator from overbuilding or weakening the source contract.

## Rules

- Start by telling the generator exactly which files to read and exactly which file to write.
- Say explicitly that the generator must produce the final acceptance-ready artifact, not a draft, notes, or partial version.
- State the phase purpose in a short list so the generator knows what transformation it is performing.
- Define whether the phase is:
  - pure extraction
  - constrained elaboration
  - decomposition
  - planning
  - verification
- If the phase is extraction, explicitly forbid paraphrase, interpretation, and invention.
- If the phase is an elaboration layer, explicitly state what kinds of invention are allowed:
  - non-contradictory
  - directly or indirectly supportive of cited upstream artifacts
  - not unrelated scope
  - not weakening exact source constraints
- If the phase is an elaboration layer, explicitly state what kinds of invention are forbidden:
  - contradiction
  - exact-meaning drift
  - unsupported scope expansion
  - unnecessary decomposition or infrastructure
  - elaboration that no longer serves the upstream contract
- Write the exact output schema in the prompt body, including top-level keys and required field names.
- State required key ordering whenever later deterministic validation depends on it.
- State any exact-count or exact-bound preservation rules when the source contains terms like `one`, `exactly`, `only`, `must`, or other hard bounds.
- State any important anti-overbuild rule that fits the phase, such as:
  - do not create extra components
  - do not create extra files
  - do not add extra interfaces
  - do not add extra verification obligations
- If the phase must write only one artifact file, say so explicitly.
- If deterministic validation exists downstream, shape the generator prompt so the artifact can satisfy it directly rather than relying on later correction.

## Phase Modes

Use the mode that actually matches the phase.

### Extraction mode

Use for phases like PH-000 where the artifact must stay close to source text.

- Preserve source wording exactly where the schema requires exact quotes.
- Split compound source statements when the phase contract requires atomicity.
- Do not clarify, operationalize, or improve the source.

### Elaboration mode

Use for phases like PH-001 and PH-002 where the artifact must add structure or supporting detail.

- Add only the minimum supporting detail needed for downstream phases.
- Keep the elaboration coherent with all cited upstream artifacts.
- Do not overfit into implementation details unless the phase contract requires them.

### Planning mode

Use for downstream implementation or verification planning phases.

- Keep the plan actionable and phase-appropriate.
- Do not prematurely write code or executable tests if the phase is still design/planning.

## Common Failure Prevention

Add the ones that actually fit the phase.

- Do not output drafts, commentary, or sidecar notes.
- Do not invent extra files.
- Do not weaken exact requirements.
- Do not silently merge distinct upstream obligations.
- Do not over-decompose trivial examples.
- Do not smuggle implementation assumptions into earlier phases.
- Do not produce text that only sounds structured; satisfy the literal schema.

## Output

When using this skill, produce:

- the revised generator prompt text, or
- a concrete patch to the prompt file

Do not produce a design essay unless the user asks for one.
