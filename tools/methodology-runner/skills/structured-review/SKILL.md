---
name: structured-review
description: |
  Use this skill when reviewing a structured design, plan, architecture,
  rules document, prompt module, or other structured artifact against
  structured inputs or directives. It runs a checklist from a predefined
  template, saves a completed checklist, then derives structured review
  findings from the completed checklist. Use it to check internal logic,
  directive coverage, terminology order, justification quality, and whether
  asserted requirements are actually supported by the inputs. It supports a
  generic base checklist first and allows artifact-specific checklist
  supplements when available.
version: 0.1.0
---

# Structured Review

This skill is for reviewing structured artifacts in a deterministic,
inspectable way.

The review happens in two stages:

1. Complete a checklist from a predefined template.
2. Review the completed checklist and extract the important findings.

The completed checklist is the primary audit trail. The findings are a
compressed interpretation of that checklist.

## When this skill applies

Use this skill when the task is one or more of:

- Reviewing a structured design document.
- Reviewing a structured plan or work breakdown structure.
- Checking whether a document applied all structured input directives.
- Checking whether requirements or claims are supported by the inputs.
- Auditing whether a structured document is internally coherent.
- Producing a disciplined review artifact rather than free-form comments.

## Required inputs

Do not start the checklist until you know:

- the review target
- the structured input documents or directives the target is supposed to
  reflect
- the intended review scope if the user constrained it

If the inputs are not already structured, first normalize them enough that
they can be traced during review.

## Bundled references

Always load the generic base checklist:

- `references/generic-structured-document-checklist.md`

If a more specific checklist exists for the artifact type or technology,
load it in addition to the generic base checklist, not instead of it.

## Output artifacts

By default, write two files next to the review target:

- `<target-base>.review-checklist.md`
- `<target-base>.review-findings.md`

If the user specifies different output paths, use those instead.

The checklist file comes first. The findings file must be derived from the
completed checklist rather than written as an independent opinion.

## Workflow

### 1. Establish review trace

Before scoring checklist items, record:

- target artifact path
- input artifact paths
- review date
- review scope
- checklist set used

If the target uses structured-design conventions, prefer citing root-level
IDs such as `REQ-1`, `ENTITY-3`, or `TASK-7`. Otherwise cite the clearest
available headings, section names, or file-relative references.

### 2. Complete the checklist

Complete every applicable checklist item with:

- `STATUS: pass | fail | question | n/a`
- short evidence grounded in the target and the inputs
- optional note if the item is blocked or uncertain

Do not skip failed items just because they will later appear in findings.
The checklist is the full audit record.

### 3. Review directive coverage

For every structured input directive or requirement that the target was
supposed to apply:

- mark whether it is covered
- cite where it is covered
- mark it `fail` if it is missing or contradicted

Do not silently forgive omitted directives.

### 4. Review unsupported assertions

Specifically check for:

- requirements asserted by the target but not supported by the inputs
- design decisions presented as requirements
- claims that rely on implied inputs rather than actual inputs

When one of these appears, record it in the checklist and then elevate it
into findings if it materially affects correctness or reviewability.

### 4A. Review workflow-versus-skill boundaries

When the target is a component design or prompt-chain design, specifically
check whether:

- the component design explains the full workflow rather than only the final
  artifact contract
- skills are treated as compact operational artifacts rather than as the place
  where the whole component workflow is explained
- skills are nested with the prompts or processes that use them when that
  structure is available
- repeated skill usage is handled by reference rather than by duplicated full
  definitions
- a short summary section exists only when it adds real compression value

Record boundary problems in the checklist and elevate them into findings when
they weaken clarity, authority, or maintainability.

### 4AA. Review architecture-versus-component-design scope

When the target is an architecture or component design document, specifically
check whether:

- an architecture document stays focused on system shape, boundaries,
  interactions, responsibilities, and major boundary-shaping technology choices
- an architecture document avoids drifting into low-level implementation detail
  unless that detail is needed to explain a boundary or major tradeoff
- a component design document explains the chosen component or workflow in
  detail rather than silently redesigning the system boundary
- a component design document covers workflow, information flow, constraints,
  definition of good, and test or review checks when those are relevant
- the target does not mix architecture and component design concerns so
  heavily that the reader cannot tell what decisions are already fixed and
  what decisions are still local to the component or process

Record scope-blur problems in the checklist and elevate them into findings when
they weaken correctness, authority, or maintainability.

### 4B. Review writing quality and document completeness

Specifically check whether:

- the document uses plain English, short sentences, and simple words
- jargon, buzzwords, and abstract phrasing are avoided unless clearly needed
- technical terms are defined once when first introduced
- vague words such as `robust`, `seamless`, `optimize`, `leverage`, and
  `enhance` are removed or made specific
- the document stays concrete and actionable
- the document includes finality, technical directives, constraints,
  definition of good, and test cases when those sections are relevant to the
  artifact

### 4C. Review section model for component design docs

When the target is a component design document, specifically check whether:

- `Finality` is used for why the component exists
- `Technical Directives` is used for implementation-shaping technical choices
  and best-practice rules
- `Definition Of Good` is used for pass-quality or success conditions
- a top-level `Requirements` section is only present when it is genuinely the
  right model for that artifact, rather than a default carry-over
- the document does not blur finality, technical directives, and definition of
  good into one mixed section

Record writing-quality, completeness, and section-model problems in the
checklist and elevate them into findings when they weaken clarity,
reviewability, or execution.

### 4CA. Review section model for architecture docs

When the target is an architecture document, specifically check whether:

- `Finality` is used for why the architecture exists
- `System Shape` is used for the main parts of the system and their roles
- `Boundaries And Interactions` is used for real boundaries and interaction
  surfaces, or explicitly says there are none
- `Constraints` is used for architecture-shaping limits and prohibitions
- `Definition Of Good` is used for architecture pass conditions
- `Test Cases` is used only when architecture-level checks are relevant
- the document does not quietly fall back to an ordinary prose outline when it
  claims to use the `structured-design` skill
- if the target is YAML, the top-level keys stay:
  - `finality`
  - `system_shape`
  - `boundaries_and_interactions`
  - `constraints`
  - `definition_of_good`
  - `test_cases` when relevant
- if the target is YAML, semantic substitutes such as `architecture_scope`,
  `boundary_decision`, or `technology_choices` are treated as section-model
  drift unless the prompt explicitly asked for a different schema

Record architecture-section-model problems in the checklist and elevate them
into findings when they weaken clarity, reviewability, or execution.

### 4D. Review markdown-versus-YAML form

When the target is a YAML structured-design document or a markdown/YAML pair,
specifically check whether:

- markdown remains the authority unless the user explicitly asked for YAML as
  the primary form
- the YAML preserves the markdown document's real section structure
- section names stay as section keys rather than being converted into item
  names
- grouped items such as `goals`, `rules`, `processes`, `files`, or `entities`
  remain grouped in YAML
- stable IDs are preserved in the YAML entries
- the YAML avoids generic `type` fields unless the task explicitly called for
  that style
- the YAML companion is not harder to understand than the markdown authority

Record markdown/YAML mapping defects in the checklist and elevate them into
findings when they distort the source structure or make the artifact harder to
review.

### 5. Extract findings

After the checklist is complete, write the findings file.

The findings file should:

- include only important failures, risks, contradictions, and missing
  directive applications
- order findings by severity
- cite the relevant checklist item IDs
- cite the relevant target location
- say what is wrong and why it matters

If there are no material findings, say so explicitly and still keep the
completed checklist file.

## Checklist discipline

The checklist is not a formality. It is the review method.

- Do not write findings first and retrofit the checklist later.
- Do not collapse several failures into one vague checklist note.
- Do not mark an item `pass` without evidence.
- Do not mark an item `n/a` unless the item truly does not apply.
- Use `question` when the evidence is genuinely ambiguous.

## Findings format

Use this shape for the findings file:

```markdown
# Review Findings: <Target title or filename>

## Scope

- Target: `<path>`
- Inputs:
  - `<path>`
  - `<path>`
- Checklist:
  - `generic-structured-document-checklist.md`

## Findings

- **FINDING: FIND-1** <short title>
  - **SEVERITY:** critical | high | medium | low
  - **CHECKS:** `<check-id>`, `<check-id>`
  - **TARGET:** `<root-level id or heading>`
  - **SYNOPSIS:** <what is wrong>
  - **BECAUSE:** <why it matters>
```

If there are no material findings:

```markdown
# Review Findings: <Target title or filename>

## Scope

...

## Findings

No material findings.
```

## Generic review priorities

When deciding what becomes a finding, prioritize:

1. missing or contradicted input directives
2. internally inconsistent logic
3. undefined or misordered concepts that create blind spots
4. `BECAUSE` clauses that do not justify their parent
5. `CHAIN-OF-THOUGHT` clauses that do not justify the `BECAUSE`
6. requirements that are really solution choices
7. unsupported requirements or claims
8. stale or retired references mixed into active design
9. skill definitions that are detached from the prompts or processes that use
   them
10. design sections that mix finality, technical directives, and definition of
    good in a way that weakens the structure
11. low-value summary sections that repeat the document without adding useful
   compression
12. vague, abstract, or buzzword-heavy wording that hides what the target
   actually requires
13. missing finality, technical directives, constraints, definition of good,
    or test cases when they are needed for the artifact type
14. architecture documents that drift into design-level detail without need
15. component design documents that silently redesign architecture boundaries
16. YAML companions that distort the markdown structure or force a generic
    `type` schema without justification

## Self-review before returning

Check all of these:

1. The generic checklist template was loaded.
2. The completed checklist exists before findings are written.
3. Every applicable checklist item has a status and evidence.
4. Input directives were traced explicitly.
5. Unsupported requirements or claims were checked explicitly.
6. Workflow-versus-skill boundaries were checked when the target was a
   component or prompt-execution design.
7. Writing quality and document completeness were checked when relevant.
8. The design-doc section model was checked when the target was a design.
9. Findings were derived from failed or questionable checklist items.
10. Findings cite checklist IDs and target locations.
11. The review did not skip the checklist and jump straight to prose.
12. The output artifacts are concise and inspectable.
13. If there were no material findings, the checklist still exists.

## Do not

- Do not invent checklist items on the fly when the template already covers
  the issue.
- Do not treat the findings file as the primary artifact.
- Do not silently ignore missing directive coverage.
- Do not accept unsupported requirements just because they sound plausible.
- Do not collapse evidence and judgment into one vague sentence.
- Do not ignore vague wording just because the structure looks correct.
