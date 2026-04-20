---
name: structured-design
description: |
  Use this skill when you need to write or revise a structured design,
  architecture, prompt-chain document, or plan using explicit item types such
  as GOAL, SUBGOAL, TASK, REQUIREMENT, ENTITY, MODULE, PROCESS, SCRIPT,
  COMMAND, PROMPT-MODULE, PROMPT-PAIR, FILE, RULE, and MODIFICATION. Use
  SYNOPSIS for the item's role, BECAUSE to justify the exact parent assertion,
  and CHAIN-OF-THOUGHT only as the bridge from the parent item to that
  BECAUSE. Use embedded IDs on root-level items when review or
  cross-reference matters. This skill returns markdown text only.
version: 0.7.0
---

# Structured Design

Write structured markdown using explicit item types and nested assertion lines.

## When To Use

Use this skill for:

- design documents
- architecture notes
- prompt-chain descriptions
- implementation structure writeups
- work breakdown structures
- execution plans
- design clarification passes

Use it for both architecture and design documents, but keep those two scopes
distinct.

## Core Model

The format has two layers:

1. Root-level items
2. Nested assertions about those items

Root-level items state what exists, what must exist, or what must be done.
Nested assertions state what is true about that item.

## Architecture Versus Component Design

Use `architecture` for system shape and boundary decisions.

Architecture should cover:

- the main parts of the system
- the boundaries between those parts
- how those parts interact
- the responsibilities of each part
- major technology choices when they affect boundaries or interaction shape
- why this decomposition is the right one

Architecture should answer:

- what are the main parts
- where are the real boundaries
- how do those parts connect
- why is this system split the right split

When choosing the architecture shape:

- use one component if one component cleanly serves the full functionality
- do not add frameworks, persistence, services, or integration points unless
  there is a real boundary need
- if there is no real cross-component boundary, make that explicit
- keep expertise descriptions human-readable and do not use skill names,
  slugs, or tool IDs

Architecture should not drift into low-level implementation detail unless that
detail is needed to explain a boundary or a major tradeoff.

Use `component design` for how one chosen part or one chosen workflow should
work after the architecture is already chosen.

Component design should cover:

- the full workflow of the component or process
- the information it reads, writes, and transforms
- the rules and constraints it must follow
- the prompts, files, commands, or modules it uses when relevant
- the definition of good for the artifact or process
- the test cases or review checks that show the design is sound

Component design should answer:

- how this chosen part works
- what it reads and writes
- what steps it follows
- what rules it must obey
- how we know it is good

Component design should assume the architecture is already chosen. It should
not quietly redesign the system boundary unless the task is explicitly to
revise the architecture.

## Root-Level Item Types

Use the smallest set that fits:

- `REQUIREMENT`
- `GOAL`
- `SUBGOAL`
- `TASK`
- `ENTITY`
- `MODULE`
- `CLASS`
- `FUNCTION`
- `SCRIPT`
- `PROCESS`
- `COMMAND`
- `PROMPT-MODULE`
- `FILE`
- `RULE`
- `MODIFICATION`

Use nested items when needed:

- `FIELD`
- `PROMPT-PAIR`
- `PROMPT`

Do not create new kinds unless the existing ones are clearly insufficient.

## Assertion Lines

Prefer only the lines that add information:

- `SYNOPSIS`
- `CHAIN-OF-THOUGHT`
- `BECAUSE`
- `CONTAINS`
- `IMPORTS`
- `USES`
- `CALLS`
- `INVOKES`
- `REQUIRES-FILE`
- `CHECKS-FILE`
- `READS`
- `WRITES`
- `PRODUCES`
- `VALIDATES`
- `LAUNCHES`
- `RESUMES`
- `DEPENDS-ON`
- `STATUS`
- `GAP`
- `SUPPORTS`

## Required Discipline

- `SYNOPSIS` states the item's role.
- `BECAUSE` must justify its immediate parent line only.
- `CHAIN-OF-THOUGHT` exists only to explain how the immediate parent leads to
  the `BECAUSE` directly below it.
- Omit `CHAIN-OF-THOUGHT` when the `BECAUSE` is already clear.
- If a `BECAUSE` really justifies a different line, move it.
- If two assertions need different reasons, split them.
- Use plain English, short sentences, and simple words.
- Avoid jargon, buzzwords, and abstract phrasing.
- Keep the document concrete and actionable.
- Include finality, technical directives, constraints, definition of good, and
  test cases when they are part of the artifact being written.
- If a technical term is necessary, define it once.
- After drafting, revise the document to remove vague phrases like `robust`,
  `seamless`, `optimize`, `leverage`, and `enhance` unless they are necessary
  and specific.
- Write structured design in markdown by default.
- Only switch to YAML when the user explicitly asks for YAML or when the task
  clearly requires a YAML companion.
- When writing YAML, preserve the document's real structure rather than forcing
  a generic `type` field everywhere.

## Root-Level IDs

Use embedded IDs only on root-level review objects.

Examples:

- `**REQUIREMENT: REQ-1** ...`
- `**GOAL: GOAL-1** ...`
- `**TASK: TASK-4** ...`
- `**ENTITY: ENTITY-2** ...`
- `**MODULE: MODULE-3** ...`
- `**PROCESS: PROCESS-2** ...`
- `**COMMAND: CMD-1** ...`
- `**SCRIPT: SCRIPT-1** ...`
- `**PROMPT-MODULE: PMOD-1** ...`
- `**FILE: FILE-1** ...`
- `**RULE: RULE-1** ...`
- `**MODIFICATION: MOD-1** ...`

Rules:

- IDs must be unique within the document.
- IDs should stay stable across revisions.
- Do not renumber everything after insertions.
- Do not reuse retired IDs.
- Do not add IDs to nested assertions or nested fields by default.

## Vocabulary

- Prefer established domain terms when they already exist.
- Example: use `worktree` rather than inventing `working tree` if the design
  is specifically about Git.
- Define important shorthand before using it.
- If a term is not defined, use the full entity name instead.

## Grouping Rules

- If a statement is about a more specific item, nest it under that item.
- Do not leave item-specific statements at a broader sibling level.
- If a contained item is already defined as a nested block, do not also add a
  redundant sibling `CONTAINS` line that repeats the same fact.
- If a skill exists to support one prompt or one execution step, nest that
  skill under the prompt or process that uses it rather than creating a
  separate top-level skills catalog.
- If the same skill is used in multiple places, define it once at the first
  relevant use site and reference that definition from later use sites rather
  than repeating the full definition.

## Markdown And YAML

Markdown is the default form for structured design because it is easier to
read, explain, and justify.

YAML is optional and should usually be treated as a companion form, not the
primary authoring form, unless the user explicitly asks for YAML.

When converting markdown structured design to YAML:

- preserve section boundaries as top-level keys
- preserve item groups such as `goals`, `rules`, `processes`, `files`, or
  `entities`
- keep stable item IDs inside each entry
- do not turn section names into item names
- do not introduce a generic `type` field unless the task explicitly calls for
  that style
- for architecture YAML, keep the real architecture section names as the
  top-level keys
- for component design YAML, keep the real component design section names as
  the top-level keys

Preferred mapping pattern:

Markdown:

```markdown
## Finality

- **GOAL: GOAL-1** Produce the architecture stack manifest
  - **SYNOPSIS:** `PH-002` turns the feature specification into one
    acceptance-ready `docs/architecture/stack-manifest.yaml` file.
  - **BECAUSE:** Later phases depend on this file.
```

YAML:

```yaml
finality:
  goals:
    - id: "GOAL-1"
      name: "Produce the architecture stack manifest"
      synopsis: "`PH-002` turns the feature specification into one acceptance-ready `docs/architecture/stack-manifest.yaml` file."
      because: "Later phases depend on this file."
```

Another example:

Markdown:

```markdown
## Technical Directives

- **RULE: RULE-4** Write one stack manifest file
  - **SYNOPSIS:** The phase must write exactly one file at
    `docs/architecture/stack-manifest.yaml`.
  - **BECAUSE:** Later phases need one stable input file.
```

YAML:

```yaml
technical_directives:
  rules:
    - id: "RULE-4"
      name: "Write one stack manifest file"
      synopsis: "The phase must write exactly one file at `docs/architecture/stack-manifest.yaml`."
      because: "Later phases need one stable input file."
```

If the YAML form becomes harder to read than the markdown source, keep the
markdown as the authority.

Architecture YAML example:

```yaml
finality:
  goals:
    - id: "GOAL-1"
      name: "Define the system shape"
      synopsis: "This architecture defines the smallest system split that can serve the required features."
      because: "Later component designs must inherit a stable system boundary."

system_shape:
  modules:
    - id: "MODULE-1"
      name: "CLI application"
      synopsis: "The single runtime unit serves the required user-visible behavior."
      because: "The feature set does not justify a multi-component split."

boundaries_and_interactions:
  rules:
    - id: "RULE-1"
      name: "No extra runtime boundary"
      synopsis: "The architecture keeps one runtime component and makes the lack of cross-component boundaries explicit."
      because: "The source does not justify services, queues, persistence, or integrations."

constraints:
  rules:
    - id: "RULE-2"
      name: "Respect source constraints"
      synopsis: "The architecture must not add unsupported frameworks or other scope."
      because: "Architecture may elaborate, but it may not invent."

definition_of_good:
  rules:
    - id: "RULE-3"
      name: "Architecture is phase-ready"
      synopsis: "Every feature is served, every boundary is justified, and the system split stays minimal."
      because: "A passing architecture must be both complete and restrained."

test_cases:
  tasks:
    - id: "TASK-1"
      name: "Review feature coverage"
      synopsis: "Check that each feature is served by the declared system shape."
      because: "Coverage gaps make the architecture unusable downstream."
```

Do not replace these architecture section keys with semantic synonyms such as
`architecture_scope`, `boundary_decision`, or `technology_choices` unless the
user explicitly asks for a different schema.

Examples:

- If a statement is about one `FUNCTION`, nest it under that `FUNCTION`, not
  under the enclosing `MODULE`.
- If a statement is about one `PROMPT-PAIR`, nest it under that
  `PROMPT-PAIR`, not under the enclosing `PROMPT-MODULE`.

## Planning Rules

For plans:

- use `GOAL` for the overall outcome
- use `SUBGOAL` for dependency-ordered chunks
- use `TASK` for concrete actions
- keep goals separate from code structure unless the code structure is itself
  the planning target

Distinguish:

- goal requirements: why the system exists
- feature requirements: what makes it usable, robust, or inspectable

## Prompt Rules

- `PROMPT-MODULE` is a reusable prompt-definition file.
- `PROMPT-PAIR` is one generator/judge pair inside that file.
- A `PROMPT-PAIR` may contain nested `PROMPT: Generator` and
  `PROMPT: Judge`.
- If a prompt depends on one or more skills, place those skill definitions or
  references under the prompt, prompt-pair, or process that actually uses
  them.
- For prompt files, prefer describing instructions the prompt contains rather
  than pretending the prompt file is a runtime function.
- Use `REQUIRES-FILE` for hard file preconditions.
- Use `CHECKS-FILE` for non-fatal file existence checks.

## Component Design Rules

- A component design should explain the whole workflow of the component, not
  just the final artifact contract.
- A component design should include full justifications for the workflow,
  responsibilities, and acceptance boundaries.
- Skill files are different: they should be optimized for efficient loading by
  an agent and should not be used as the place where the whole component
  workflow is explained.
- Do not add a separate `SKILLS` section by default when the skills are really
  part of prompt execution or a specific process step.
- Prefer nesting each skill with the prompt, prompt-pair, or process that uses
  it.
- If a short summary section repeats the document without adding real
  compression value, omit it.
- If a skill is specific to exactly one methodology phase, name it with a
  `phNNN-` prefix such as `ph000-requirements-extraction`.
- If a skill is intended to be shared across phases or artifact types, keep a
  generic name such as `traceability-discipline`.

## Recommended Section Order

For architecture docs, use this section model by default:

1. Finality
2. System Shape
3. Boundaries And Interactions
4. Constraints
5. Definition Of Good
6. Test Cases

For architecture YAML, use these exact top-level keys unless the user
explicitly asks for a different schema:

- `finality`
- `system_shape`
- `boundaries_and_interactions`
- `constraints`
- `definition_of_good`
- `test_cases`

For component design docs, use this section model by default:

1. Finality
2. Technical Directives
3. Information Model
4. Structure or Execution
5. Constraints
6. Definition Of Good
7. Test Cases

When the design includes prompt execution, describe skills inside
Coordination or Execution where they are actually used.

For plan docs, default to:

1. Goal Hierarchy
2. Dependencies
3. Gaps or Risks
4. Modifications

## Minimal Skeletons

### Design

```markdown
# Design: <Topic>

## 1. Finality

One-line purpose of this section.

- **GOAL: GOAL-1** <name>
  - **SYNOPSIS:** <why the component exists>
  - **BECAUSE:** <why it matters>

## 2. Technical Directives

One-line purpose of this section.

- **RULE: RULE-1** <name>
  - **SYNOPSIS:** <technical directive or implementation-shaping rule>
  - **BECAUSE:** <why this is the right technical direction>

## 3. Information Model

One-line purpose of this section.

- **ENTITY: ENTITY-1** <name>
  - **SYNOPSIS:** <overall concept>
  - **FIELD:** <field>
    - **SYNOPSIS:** <meaning>
    - **BECAUSE:** <why it exists>

## 3. Structure

One-line purpose of this section.

- **MODULE: MODULE-1** <name>
  - **SYNOPSIS:** <role>
  - **USES:** <dependency>
    - **BECAUSE:** <why>

## 4. Modifications

One-line purpose of this section.

- **MODIFICATION: MOD-1** <change>
  - **SYNOPSIS:** <change to apply>
  - **BECAUSE:** <why it is a real design change>
  - **STATUS:** proposed | in-progress | applied
```

### Plan

```markdown
# Plan: <Topic>

## 1. Goal Hierarchy

One-line purpose of this section.

- **GOAL: GOAL-1** <outcome>
  - **CHAIN-OF-THOUGHT:** <bridge to the reason below>
  - **BECAUSE:** <why this goal matters>
  - **SUBGOAL: SUBG-1** <chunk>
    - **BECAUSE:** <why this subgoal matters>
  - **TASK: TASK-1** <action>
    - **STATUS:** todo | in progress | done | blocked
    - **BECAUSE:** <why this task matters>
```

## Formatting Rules

- Use markdown nested bullets with two spaces per level.
- Use one concern per assertion line.
- Start each section with one plain sentence explaining why it exists.
- Keep the output as markdown only.
- Do not add conversational preamble or trailing commentary.
- Do not use ASCII tree art.

## Pass Sequence

When refining a document over multiple passes:

1. Structure pass
2. Justification pass
3. Justification-quality pass
4. Modification pass

## Self-Review

Check all of these before returning:

1. The section order is logical.
2. Every important item has a `SYNOPSIS`.
3. Important assertions have `BECAUSE` where needed.
4. Every `BECAUSE` justifies its immediate parent.
5. Any `CHAIN-OF-THOUGHT` bridges the parent line to the `BECAUSE`.
6. Item-specific details are nested under the right item.
7. Prompt details use `PROMPT-MODULE` and `PROMPT-PAIR` correctly.
8. Root-level IDs are used only when review or cross-reference matters.
9. IDs are not added to every nested property.
10. Gaps are stated explicitly rather than guessed away.

## Do Not

- Do not write files.
- Do not choose filenames.
- Do not mix unrelated assertions under one `BECAUSE`.
- Do not use `CHAIN-OF-THOUGHT` as a second synopsis.
- Do not leave item-specific details at the wrong level.
- Do not let requirements collapse into solution choices unless the document
  explicitly says they are design decisions.
