# Prompt-Runner Agent Docs Change Plan

## 1. Goal

- **GOAL: GOAL-1** Make the agent model easy to locate and consistent with the
  actual execution boundary.
  - **BECAUSE:** The current docs mix generic runner roles with
    methodology-specific roles and make it harder to see what the agents
    actually consume at run time.

## 2. Canonical Changes

- **MODIFICATION: MOD-1** Update
  [CD-006-prompt-runner-core.md](/Users/martinbechard/dev/agent-runner/docs/design/components/CD-006-prompt-runner-core.md)
  - **SYNOPSIS:** Add a new section that defines the generic `Generator Agent`,
    `Judge Agent`, `Runtime Contract`, and prompt-level agent properties.
  - **BECAUSE:** `CD-006` is the best place for the generic execution model of
    prompt-runner.
  - **ADD:** A concise agent-model section covering:
    - generator role
    - judge role
    - prompt body + resolved agent properties as the runtime contract
    - verdict protocol as generic runner behavior
    - prompt-file agent properties as a self-contained specialization path
    - precedence: prompt-file properties override run-level defaults
    - no per-step agents by default

- **MODIFICATION: MOD-2** Update
  [CD-001-prompt-runner.md](/Users/martinbechard/dev/agent-runner/docs/design/components/CD-001-prompt-runner.md)
  - **SYNOPSIS:** Extend the input contract so a prompt pair may declare
    generator and judge agent properties directly in the prompt file.
  - **BECAUSE:** `CD-001` currently describes input format well but does not
    support self-contained prompt modules carrying their own agent setup.
  - **ADD:** New prompt-file structure and parsing rules for:
    - prompt-level generator agent properties
    - prompt-level judge agent properties
    - allowed embedded prelude text
    - precedence over `--generator-prelude` and `--judge-prelude`
  - **ADD:** One short execution-model note:
    - prompt-runner owns call assembly
    - embedded agent properties and CLI-supplied properties are both opaque
      inputs
    - prompt-runner remains skill-agnostic

- **MODIFICATION: MOD-3** Update
  [CD-002-methodology-runner.md](/Users/martinbechard/dev/agent-runner/docs/design/components/CD-002-methodology-runner.md)
  - **SYNOPSIS:** Make the `Skill Selector Agent` explicit as a
    methodology-runner role and explain that skill selection is broader than
    prefix construction.
  - **BECAUSE:** The current docs show selector flow, but not clearly enough as
    an agent role with a specific responsibility boundary.
  - **ADD:** A section or subsection covering:
    - `Skill Selector Agent`
    - inputs: phase definition, baseline config, prior artifacts, stack
      manifest, compact skill catalog
    - outputs: locked `phase-NNN-skills.yaml`
    - materialization: embedded prompt-file agent properties or
      `generator-prelude.txt` and `judge-prelude.txt` when using run-level
      injection
    - reason: choose, validate, and lock specialization before prompt-runner
      executes

- **MODIFICATION: MOD-4** Update
  [CD-009-ph000-requirements-inventory-design.md](/Users/martinbechard/dev/agent-runner/docs/design/components/CD-009-ph000-requirements-inventory-design.md)
  - **SYNOPSIS:** Reference the shared generic prompt-runner generator/judge
    agents instead of implicitly treating the PH-000 prompt roles as their own
    agent designs.
  - **BECAUSE:** PH-000 should only carry its specialized prompt and skill
    behavior, not redefine shared runner roles.
  - **CHANGE:** In the workflow section:
    - `Prompt: Generator` uses the shared `Generator Agent`
    - `Prompt: Judge` uses the shared `Judge Agent`
    - keep PH-000-specific skills and prompt behavior nested locally

- **MODIFICATION: MOD-5** Update
  [M-003-agent-role-specifications.md](/Users/martinbechard/dev/agent-runner/docs/methodology/M-003-agent-role-specifications.md)
  - **SYNOPSIS:** Reduce the file to a methodology-level index or overview
    instead of using it as the main home for every detailed agent definition.
  - **BECAUSE:** The current monolithic role document is too hard to navigate
    and mixes ownership boundaries.
  - **CHANGE:** Keep only:
    - short methodology agent overview
    - links to the canonical shared agent designs
    - links to any methodology-specific agent designs
  - **REMOVE:** Large embedded full role definitions once their canonical homes
    exist elsewhere.

## 3. Ordering

- **PROCESS: PROCESS-1** Update `CD-006` first
  - **BECAUSE:** The shared prompt-runner agent model should exist before other
    docs reference it.

- **PROCESS: PROCESS-2** Update `CD-002` second
  - **BECAUSE:** The methodology selector role should then be documented
    against the already-defined prompt-runner boundary.

- **PROCESS: PROCESS-3** Update `CD-009` third
  - **BECAUSE:** The PH-000 design should point at the new shared agent
    definitions instead of carrying implied local ones.

- **PROCESS: PROCESS-4** Shrink `M-003` last
  - **BECAUSE:** The index can only be simplified safely after the canonical
    replacement locations exist.

## 4. Guardrails

- **RULE: RULE-1** Do not move the selector into prompt-runner docs
  - **BECAUSE:** The selector does not run inside prompt-runner and should not
    be documented as a prompt-runner role.

- **RULE: RULE-2** Do not introduce phase-local generator or judge agent docs
  by default
  - **BECAUSE:** Phase specialization should remain in prompt files and skills
    unless a phase truly changes the operating model.

- **RULE: RULE-3** Distinguish design-time and run-time clearly
  - **SYNOPSIS:** The docs should say that agents consume runtime inputs, not
    the full design corpus.
  - **BECAUSE:** The earlier confusion came from blurring human design
    authority with the actual runtime contract.

- **RULE: RULE-4** Preserve prompt-runner skill agnosticism
  - **SYNOPSIS:** The prompt-runner docs should describe embedded agent
    properties as opaque runtime inputs rather than as runner-understood skill
    semantics.
  - **BECAUSE:** Self-contained prompt files should not turn prompt-runner into
    a skill-aware orchestrator.
