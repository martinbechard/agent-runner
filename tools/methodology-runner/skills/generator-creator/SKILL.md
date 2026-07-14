---
type: Skill
name: generator-creator
description: "Use when writing or revising an LLM generator prompt for a methodology phase or prompt-runner generation step. Focuses on the fully rendered prompt shape: role and goal first, just-in-time context, explicit output contract, clear invention boundaries, and retry-only instructions separated from the first-pass task."
---

# Generator Creator

Use this skill when the task is to create or refine a generator / artifact-production prompt.

## Goal

Write a generator prompt that:

- starts with the generator's role and task, not a data blob
- places source context where the task actually uses it
- states the artifact path and output contract explicitly
- defines the allowed invention boundary for the phase
- makes the artifact schema and ordering literal
- keeps retry-only instructions out of the first-pass prompt
- yields a fully rendered prompt that is logical to read top to bottom

## Workflow

1. Analyze the fully rendered prompt the model will actually see.
2. Identify the phase contract, artifact path, and phase mode.
3. Structure the prompt as:
   - Goal
   - Context
   - Constraints
   - Done when
4. Put embedded content just in time:
   - use `{{INCLUDE:...}}` for pre-existing source material
   - use `{{RUNTIME_INCLUDE:...}}` only when a later step must embed a generated artifact inline
5. Define the exact output schema, ordering, and file-write obligations.
6. Define the allowed invention boundary and anti-drift rules for the phase.
7. Move revise-only instructions into a `Retry Prompt` when using prompt-runner.
8. Remove redundant or conflicting instructions.
9. Check the rendered prompt again before calling the backend.

## Rules

- Start with the generator's role and the concrete task.
- Do not start the prompt with raw source content, artifact dumps, or file narration.
- State the exact output path and whether the generator must write one file or multiple files.
- Say explicitly that the generator must produce the final acceptance-ready artifact, not a draft, notes, or a partial version.
- Say explicitly whether the phase is:
  - extraction
  - constrained elaboration
  - decomposition
  - planning
  - verification
- Define the allowed invention boundary in phase-appropriate terms.
- Define the forbidden invention or drift in phase-appropriate terms.
- Define the forbidden drift for that phase:
  - contradiction
  - unsupported scope expansion
  - unnecessary decomposition
  - overbuilding
  - draft churn
- Write the exact output schema in the prompt body, including top-level keys and required field names.
- State required key ordering whenever later deterministic validation depends on it.
- State exact-count or exact-bound preservation rules when the source contains terms like:
  - `one`
  - `exactly`
  - `only`
  - `must`
  - other hard bounds
- State the anti-overbuild rule that fits the phase, such as:
  - do not create extra components
  - do not create extra files
  - do not add extra interfaces
  - do not add extra verification obligations
- Use semantic XML-style tags around embedded content blocks.
- When content is embedded inline, refer to the content itself, not to files the model should go read.
- `Required Files` and `Checks Files` are validation metadata only. Do not rely on them to inject prompt content.
- Reserve `Include Files` for cases where front-loaded shared context is explicitly desired across the whole call.
- Keep constraints close to the action they constrain.
- Put the exact schema, key order, and file-write requirements in `Done when`.
- If the phase has deterministic validation, shape the prompt so the artifact can satisfy it directly.

## Phase Modes

Use the mode that actually matches the phase.

### Extraction mode

Use for phases like PH-000 where the artifact must stay close to source text.

- Preserve source wording exactly where the schema requires exact quotes.
- Split source statements only when the phase contract actually requires atomicity.
- Do not clarify, operationalize, or improve the source.

### Elaboration mode

Use for phases that add structure or supporting detail.

- Add only the minimum supporting detail needed for downstream phases.
- Keep the elaboration coherent with all cited upstream artifacts.
- Do not overfit into implementation detail unless the phase contract requires it.

### Planning mode

Use for implementation or verification planning phases.

- Keep the plan actionable and phase-appropriate.
- Do not prematurely write code or executable tests if the phase is still planning.

### Verification mode

Use for phases that assess an existing artifact or implementation state.

- Report what the phase contract requires, not speculative extras.
- Keep evidence and status aligned with what was actually observed.
- Do not smuggle redesign work into a verification artifact.

## Common Failure Prevention

Add the ones that actually fit the phase.

- Do not output drafts, commentary, or sidecar notes.
- Do not invent extra files.
- Do not weaken exact requirements.
- Do not silently merge distinct upstream obligations.
- Do not over-decompose trivial examples.
- Do not smuggle implementation assumptions into earlier phases.
- Do not produce text that only sounds structured; satisfy the literal schema.

## Retry Rules

- The first-pass generator prompt should not contain revise-only analysis or correction instructions.
- If the generator needs different behavior on revise iterations, use `### Retry Prompt`.
- Choose retry mode deliberately:
  - `REPLACE` when the retry prompt should fully define revision behavior
  - `PREPEND` when revision framing should come before the default correction block
  - `APPEND` when the default correction block should stay first
- Retry text must be factual and self-contained.
- Do not imply memory of a previous attempt.
- Refer only to the context that will actually be present, such as:
  - the original task
  - the current artifact
  - `<REQUIRED_CHANGES>`

## Rendered Prompt Checklist

Before accepting a generator prompt, verify that the rendered prompt satisfies all of these:

- the first non-empty lines identify the role and task
- no large embedded block appears before the task framing
- each embedded block appears in the relevant `Context` section
- the output path is explicit
- the artifact contract is easy to find
- the schema, key order, and bounds are explicit when the phase depends on them
- the invention boundary is explicit
- retry-only instructions are absent from the first-pass prompt
- there is no repeated high-level boilerplate that says less than a later concrete rule

## Output

When using this skill, produce:

- the revised generator prompt text, or
- a concrete patch to the prompt file

Do not produce a design essay unless the user asks for one.
