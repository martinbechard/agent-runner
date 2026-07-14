---
type: Skill
name: judge-creation
description: Use when writing or revising an LLM judge prompt for a methodology phase or prompt-runner validation step. Focuses on the fully rendered prompt shape, just-in-time context, material downstream defects, authoritative deterministic checks, and concrete revise feedback without wording-polish churn.
---

# Judge Creation

Use this skill when the task is to create or refine a judge / validation prompt.

## Goal

Write a judge prompt that:

- starts with the judge's role and review task, not a context dump
- places source and artifact context where the review uses it
- catches real semantic defects
- does not relitigate mechanical checks already handled elsewhere
- allows source-faithful elaboration when the phase is supposed to invent supporting detail
- asks for changes only when they are actually wrong or materially consequential
- rejects only defects that would weaken downstream architecture, design, implementation, or verification work
- produces revise feedback that a generator can act on directly

## Workflow

1. Analyze the fully rendered judge prompt the model will actually see.
2. Identify the phase contract and the artifact units the next phase will consume.
3. Separate mechanical checks from semantic checks.
4. Structure the prompt as:
   - Goal
   - Context
   - Constraints
   - Done when
5. Place source and artifact content just in time:
   - use `{{INCLUDE:...}}` for pre-existing source material
   - use `{{RUNTIME_INCLUDE:...}}` for generated artifacts that must appear inside `Context`
6. Define the semantic failure modes the judge should catch.
7. Add materiality and duplicate-coverage rules.
8. Require concrete corrective feedback with cited artifact IDs.

## Rules

- Start with the judge's role and review task.
- Do not start the prompt with artifact dumps, source dumps, or generic "included files" narration.
- When content is embedded inline, refer to the embedded content, not to files the judge should go read.
- `Required Files` and `Checks Files` are validation metadata only. Do not rely on them to inject prompt content.
- Reserve `Include Files` for cases where front-loaded shared context is explicitly desired.
- Tell the judge which mechanical report is authoritative.
- If deterministic validation already ran, explicitly say the judge must trust that report for structural and count-based checks and must not duplicate them manually.
- Tell the judge to review the artifact in the same unit structure that downstream phases will consume.
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
- Tell the judge to test the semantic dimensions that matter downstream:
  - missing required meaning
  - unsupported added meaning
  - dropped qualifier or scope boundary
  - dropped justification when it changes downstream design, scope, or tests
  - category or classification errors that change downstream treatment
- Explicitly forbid wording-polish churn:
  - do not request wording polish, minor precision tweaks, or alternate phrasing unless the current wording is actually wrong or materially consequential
- Tell the judge not to require a separate item for a summary or umbrella statement if its actionable meaning is already fully covered by one or more other artifact units.
- Before flagging anything as missing, require the judge to check whether that meaning is already covered elsewhere in the artifact.
  - If the meaning is already covered by one or more other units, do not flag it as missing unless the allegedly missing text contributes distinct downstream-actionable scope, constraint, behavior, or rationale.
- If the artifact is generated earlier in the same prompt cycle, embed it inline in `Context` with `{{RUNTIME_INCLUDE:...}}` so the judge sees it where the review instructions expect it.
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
- dropped qualifier or scope boundary
- dropped downstream-relevant justification
- false missing-content claim caused by already-covered meaning
- pseudo-objective constraints
- contradictory invention

## Corrective Feedback Format

When the judge finds a material issue, it should emit corrective guidance in this form:

- `RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT ...`
  - `BECAUSE: ...`

Use imperative, specific changes. Avoid generic complaints like "be clearer" or "be more precise."

## Rendered Prompt Checklist

Before accepting a judge prompt, verify that the rendered prompt satisfies all of these:

- the first non-empty lines identify the judge role and review task
- no large embedded source or artifact block appears before that framing
- source material appears inside the relevant `Context` section
- the artifact under review appears inside the relevant `Context` section
- deterministic validation is clearly marked as authoritative when present
- review order and material defect criteria are easy to find
- the prompt does not demand duplicate summary items when the meaning is already covered elsewhere

## Output

When using this skill, produce:

- the revised judge prompt text, or
- a concrete patch to the prompt file

Do not produce a design essay unless the user asks for one.
