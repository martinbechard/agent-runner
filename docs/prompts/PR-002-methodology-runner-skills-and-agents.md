# PR-002 — methodology-runner-skills and integration agents

This is a prompt-runner input file. Each prompt is an **interactive**
session that pair-programs with Claude to author one skill or one
integration agent for the skill-driven methodology-runner. There are no
validator prompts — the human IS the validator in each session, and each
session includes an in-session verification step that spawns
`methodology-runner` against `tests/fixtures/tiny-requirements.md` to
confirm the newly-authored skill works end-to-end.

**How to run:**

```
prompt-runner run docs/prompts/PR-002-methodology-runner-skills-and-agents.md
```

Each prompt spawns `claude` interactively. Type `/exit` or Ctrl-C when
the work is done and committed; prompt-runner resumes with the next
prompt. If the session crashes or you need to stop partway through, use
`--resume <run-dir>` to continue from where you left off.

**Dependency order:** phases are built bottom-up (PH-000 first, then
PH-001, etc.), because each phase's verification depends on that phase's
baseline skills being present. Integration agents for phase N are
authored AFTER phase N's skills are done, because they need phase N
output to test against.

**Spec reference:** the 18 baseline skills, their per-phase roles, and
the expected expertise patterns are defined in
`docs/superpowers/specs/2026-04-09-skill-driven-methodology-runner-design.md`
section 11. The methodology phases themselves are defined in
`docs/methodology/M-002-phase-definitions.md`.

---

## Prompt 1: Plugin scaffold [interactive]

```
You are helping me set up the methodology-runner-skills companion plugin
directory structure so that subsequent prompts in this run can author
skills into a consistent location.

## What to create

A directory tree at `plugins/methodology-runner-skills/` under the repo
root:

    plugins/methodology-runner-skills/
      .claude-plugin/
        plugin.json
      README.md
      skills/                   (empty for now; populated by later prompts)

The `plugin.json` should declare:

- name: "methodology-runner-skills"
- version: "0.1.0"
- description: "Baseline skill pack for the AI-driven development
  methodology — 18 tech-agnostic skills covering all 8 phases of
  methodology-runner."
- author: Martin Bechard
- Any other fields the Claude Code plugin manifest schema requires
  (look these up via the plugin-dev skill if unsure; don't invent
  fields that aren't supported).

The `README.md` should briefly describe the plugin, list the 18
skills with one-line roles, and point at the companion spec
(docs/superpowers/specs/2026-04-09-skill-driven-methodology-runner-design.md).
Keep it under 100 lines.

## How runtime discovery works (no symlinks)

methodology-runner's skill catalog discovery walks
`<cwd>/plugins/*/skills/**/SKILL.md` as a discovery source. This
means as long as you run `methodology-runner run ...` from the repo
root (where `plugins/methodology-runner-skills/skills/` exists),
skills are discovered automatically. No symlinks, no environment
variables, no per-machine setup.

Verify by listing the structure:

    ls plugins/methodology-runner-skills/.claude-plugin/plugin.json
    ls plugins/methodology-runner-skills/README.md

## Commit

    git add plugins/methodology-runner-skills/
    git commit -m "feat(skills): scaffold methodology-runner-skills plugin"

## When you're done

Tell me the commit hash, then type /exit.
```

---

## Prompt 2: Author traceability-discipline skill [interactive]

```
You are helping me author the `traceability-discipline` SKILL.md file.

## Role of this skill

`traceability-discipline` is the single most-used skill in the pack:
every methodology phase (PH-000 through PH-007) lists it as a baseline
for both generator AND judge. It enforces the cross-cutting rule that
every artifact element must trace to an element in a prior phase, and
that no element is introduced without a source.

See spec section 11 for the role: "universal traceability rules; every
artifact element must trace to a prior-phase element; no orphans, no
dangling references."

## Target file

    plugins/methodology-runner-skills/skills/traceability-discipline/SKILL.md

The file must start with valid YAML frontmatter:

    ---
    name: traceability-discipline
    description: Enforce universal traceability — every element traces to a prior-phase source; no orphans, no dangling references
    ---

Followed by a substantive body (aim for 150-300 lines) that covers:

1. What traceability means in this methodology, with forward and
   backward link semantics.
2. The three cardinal rules the skill enforces:
   - No element in phase N without a source reference to phase N-1 (or
     earlier).
   - No element in phase N-1 that has zero references FROM phase N
     (unless explicitly marked "out of scope" with a reason).
   - No invented or hallucinated IDs — every reference must resolve to a
     real element.
3. How to verify traceability during GENERATION (what the generator
   should check before emitting an artifact).
4. How to verify traceability during JUDGING (what the judge should
   check when reading a generator's output).
5. Concrete examples of good and bad traceability, drawn from the
   phase-to-phase handoffs described in M-002.
6. Anti-patterns — subtle ways traceability can rot (e.g., copying
   requirement IDs into a feature without actually mapping the feature
   to them, or "traceability by listing all upstream IDs indiscriminately").

## Authoring approach

Use the `superpowers:skill-creator` skill to walk through the authoring
process. Ask me questions about level of specificity, whether to
include code snippets, and how detailed the examples should be. I'll
pair-program with you.

## In-session verification

When we're satisfied with the SKILL.md, verify it works end-to-end:

# (run from repo root so cwd-plugin discovery finds the skills)

1. Run methodology-runner against the tiny requirements fixture, but
   only for phase 0 (the only phase whose baseline we'll have complete
   after this skill — actually, phase 0 needs THREE skills, so this
   verification may halt at baseline-validation time. That's expected
   and informative: the halt message should list the missing baselines
   as a clear actionable error). Run:

       mkdir -p /tmp/test-ph000-workspace
       methodology-runner run \
         tests/fixtures/tiny-requirements.md \
         --workspace /tmp/test-ph000-workspace \
         --phases PH-000-requirements-inventory

2. Expected outcome: the run halts during baseline validation with a
   message naming the two still-missing baseline skills
   (`requirements-extraction` and `requirements-quality-review`). That
   halt confirms:
   - The skill catalog discovered `traceability-discipline`
   - skills-baselines.yaml validation is running
   - Our newly-authored skill is correctly seen by the discovery layer

If the halt message does NOT mention `traceability-discipline` as
missing, the skill is loaded correctly. If it DOES mention it as
missing, the skill's YAML frontmatter or file location is wrong —
iterate.

## Commit

    git add plugins/methodology-runner-skills/skills/traceability-discipline/
    git commit -m "feat(skills): add traceability-discipline skill"

## When you're done

Type /exit. Prompt 3 will author the next PH-000 baseline.
```

---

## Prompt 3: Author requirements-extraction skill [interactive]

```
You are helping me author the `requirements-extraction` SKILL.md file.

## Role of this skill

`requirements-extraction` is the PH-000 generator baseline. PH-000 is
the Requirements Inventory phase — its job is to extract every distinct
idea, constraint, assumption, and requirement from raw source documents
WITHOUT inference, improvement, or paraphrasing. This is extractive
work, not elicitation. The skill exists to enforce that discipline:
fidelity-first extraction from existing documents.

See spec section 11: "PH-000 baseline; extracting requirements from
existing documents fidelity-first, without inference or improvement."

## Target file

    plugins/methodology-runner-skills/skills/requirements-extraction/SKILL.md

Frontmatter:

    ---
    name: requirements-extraction
    description: Extract requirements from source documents fidelity-first — no inference, no paraphrasing, no improvement
    ---

Body should cover (100-250 lines):

1. The fidelity principle: the extractor reproduces source text
   verbatim in verbatim_quote fields. It does not rewrite, summarize,
   interpret, or "improve" the text. Ambiguity is preserved, not
   resolved.
2. How to walk a source document systematically (section by section,
   paragraph by paragraph, including tables, lists, and inline prose)
   to avoid silent omissions.
3. Atomicity: splitting compound statements (those containing "and",
   "or", or multiple independent clauses) into separate inventory
   items.
4. Category discrimination: functional vs. non_functional vs.
   constraint vs. assumption. With concrete language patterns that
   signal each (e.g., "shall/must" → functional, "should" →
   non_functional, "within/limited-to" → constraint, "assuming" →
   assumption).
5. Anti-patterns: silent omission, invention (adding requirements the
   source didn't state), paraphrasing that loses nuance, collapsing
   contradictions into a single "averaged" statement.
6. What the generated YAML inventory should look like — point at the
   schema in phases.py or the example output in
   tests/cli/methodology_runner/ fixtures for the exact structure.

## Authoring approach

`superpowers:skill-creator`. Ask questions.

## In-session verification

With `traceability-discipline` from prompt 2 and `requirements-extraction`
now authored, only `requirements-quality-review` is missing from the
PH-000 baseline. Run:

    methodology-runner run \
      tests/fixtures/tiny-requirements.md \
      --workspace /tmp/test-ph000-workspace-2 \
      --phases PH-000-requirements-inventory

Expected: halt at baseline validation with ONE missing skill
(`requirements-quality-review`). That confirms the new skill is
discovered.

## Commit

    git add plugins/methodology-runner-skills/skills/requirements-extraction/
    git commit -m "feat(skills): add requirements-extraction skill"

## When you're done

Type /exit.
```

---

## Prompt 4: Author requirements-quality-review skill [interactive]

```
You are helping me author the `requirements-quality-review` SKILL.md file.

## Role of this skill

`requirements-quality-review` is the PH-000 judge baseline. The PH-000
judge's job is to read the generator's requirements inventory and flag
failure modes: silent omissions (sections the generator didn't cover),
invented items (quotes that can't be located in the source), unsplit
compounds, lost nuance, and wrong category assignments. This skill
packages that evaluation discipline.

See spec section 11: "PH-000 judge baseline; what makes a requirements
inventory complete, atomic, and unambiguous."

## Target file

    plugins/methodology-runner-skills/skills/requirements-quality-review/SKILL.md

Frontmatter:

    ---
    name: requirements-quality-review
    description: Evaluate a requirements inventory for completeness, atomicity, fidelity, and correct categorisation
    ---

Body (100-250 lines) should cover:

1. The five failure modes to detect (match the judge_guidance in
   phases.py for PH-000):
   - Silent omissions
   - Invented requirements
   - Unsplit compounds
   - Lost nuance
   - Wrong categories
2. How to detect each by READING the inventory against the source
   document (not by running assertions — this is evaluation by another
   LLM, not automated verification).
3. What a high-quality inventory item looks like (verbatim quote
   matching source exactly, category matching language strength, tags
   supporting cross-referencing).
4. What feedback to produce when issues are found — specific, actionable,
   pointing at line numbers in the source document and IDs in the
   inventory.

## Authoring approach

`superpowers:skill-creator`. Ask questions.

## In-session verification

Now ALL three PH-000 baselines are present. Run the full phase:

    methodology-runner run \
      tests/fixtures/tiny-requirements.md \
      --workspace /tmp/test-ph000-workspace-3 \
      --phases PH-000-requirements-inventory

Expected outcome:
- The skill catalog discovers all 3 PH-000 baseline skills
- The Skill-Selector runs and produces phase-000-skills.yaml
- The prelude files are written (generator-prelude.txt, judge-prelude.txt)
- prompt-runner spawns the generator, which produces a requirements
  inventory YAML
- The judge reviews it and either passes or requests revisions
- Cross-reference verification runs
- The phase completes (or halts with a specific, diagnosable reason)

This is the first full phase verification. Read the output carefully:

- Is the generator actually USING the skills (look for evidence in the
  generator's output that it's applying fidelity discipline)?
- Is the judge's feedback specific and grounded in the skill's framing?
- Does the cross-ref verifier pass?

If the phase completes successfully, PH-000 is "done" for our purposes.
If not, note specifically what failed and iterate on the SKILL.md of
whichever skill looks most relevant to the failure.

## Commit

    git add plugins/methodology-runner-skills/skills/requirements-quality-review/
    git commit -m "feat(skills): add requirements-quality-review skill"

## When you're done

Type /exit. Prompt 5 will author the PH-000 integration agent.
```

---

## Prompt 5: Author PH-000 integration agent [interactive]

```
You are helping me author an integration agent for PH-000 Requirements
Inventory. This is NOT a skill file — it is a prompt-runner input file
that runs a Claude call simulating what downstream phases (PH-001
Feature Specification, PH-002 Architecture) would need from PH-000's
output.

## Background

See `docs/superpowers/specs/2026-04-09-skill-pack-and-interactive-harness-notes.md`
section 6 for the full rationale. The short version: after PH-000 runs
for real, we want an agent that READS the requirements inventory
output and evaluates whether PH-001 and later phases will actually be
able to use it. This catches "technically passes the judge but
semantically unusable" bugs.

## Target file

    docs/prompts/integration-agent-PH-000-requirements-inventory.md

This file is a prompt-runner input with a SINGLE prompt, validator-less:

    ## Prompt 1: PH-000 integration critique

    ```
    You are a downstream-consumer simulator for PH-000 Requirements
    Inventory output. Your job is to read the requirements inventory
    artifact and evaluate whether it contains the semantic content that
    PH-001 (Feature Specification) and PH-002 (Architecture) will need
    to do their jobs — beyond just "does the YAML parse" or "does it
    pass formal cross-ref checks".

    ## What to read

    - The requirements inventory YAML at
      `{workspace}/docs/requirements/requirements-inventory.yaml`
    - The original raw requirements document at
      `{workspace}/docs/requirements/raw-requirements.md`

    ## What PH-001 and PH-002 need from this

    PH-001 (Feature Specification) needs to group RI-* items into
    FT-* features with testable acceptance criteria. For that to work:
    - Each RI-* item must have enough semantic content that grouping is
      possible (not just "the system shall X" without context)
    - Related requirements must be identifiable by reading their content
      (shared domain terms, explicit cross-references, etc.)
    - Acceptance-criteria-bearing requirements must contain the concrete
      behavior PH-001 can transform into testable criteria

    PH-002 (Architecture) needs to identify technology components
    from the features (in PH-001 first, transitively from PH-000). For
    that to work:
    - Requirements that imply specific technology choices (storage,
      UI, integration) must be recognizable
    - Non-functional requirements that constrain the architecture
      (latency, footprint, dependencies) must be complete and unambiguous

    ## Your task

    1. Pretend to be the PH-001 generator. Try to mentally group the
       RI-* items into candidate features. Note any ambiguities or
       gaps.
    2. Pretend to be the PH-002 architect. Try to identify candidate
       components from the requirements. Note any technology decisions
       you'd have to guess at.
    3. Produce a structured YAML critique.

    ## Output format

    Your entire response must be a single YAML document with this shape:

        phase_evaluated: PH-000-requirements-inventory
        findings:
          - severity: blocking | warning | info
            location: RI-NNN or <section of raw requirements>
            issue: |
              Description of the problem, in terms of what a downstream
              phase will be unable to do because of it.
            recommendation: |
              What should change (be specific — not "add more detail"
              but "split RI-003 into two items: one for the input
              validation and one for the output format").
          - ...
        overall_usability: high | medium | low
        summary: |
          Brief 2-3 sentence summary.
    ```

Note the file has only ONE fenced block (the generator mission) and NO
validator. That requires the prompt-runner extension from our previous
work (optional validator).

## Authoring approach

Walk through the rationale for each section of the critic prompt with
me. We want the critic to be specific about what PH-001 and PH-002
need, not just "evaluate this holistically". The more concrete the
questions the critic asks, the more actionable its output.

## In-session verification

Once the file is written, run it against a completed PH-000 workspace:

    prompt-runner run \
      docs/prompts/integration-agent-PH-000-requirements-inventory.md \
      --workspace /tmp/test-ph000-workspace-3

(This workspace is the one created in prompt 4 where PH-000 completed
successfully. If that workspace is gone, re-run PH-000 first or pick a
different completed workspace.)

The run should:
- Execute the single critic prompt
- Skip the judge (validator-less)
- Produce a YAML critique in the run output
- Exit cleanly with verdict pass

Read the critique. Is it specific? Does it say things you couldn't have
derived from just looking at the PH-000 judge's feedback? If yes,
commit and move on. If not, iterate on the critic prompt.

## Commit

    git add docs/prompts/integration-agent-PH-000-requirements-inventory.md
    git commit -m "feat(prompts): add PH-000 integration agent"

## When you're done

Type /exit.
```

---

## Prompt 6: Author feature-specification skill [interactive]

```
You are helping me author the `feature-specification` SKILL.md file.

## Role of this skill

PH-001 generator baseline. PH-001 groups RI-* items from the inventory
into FT-* features with testable acceptance criteria, identifies
dependencies between features, and marks any requirements as
explicitly out-of-scope with a reason.

See spec section 11: "PH-001 baseline; grouping requirements into
features, writing acceptance criteria, identifying dependencies."

## Target file

    plugins/methodology-runner-skills/skills/feature-specification/SKILL.md

Frontmatter:

    ---
    name: feature-specification
    description: Group requirements into features with testable acceptance criteria and explicit dependencies
    ---

Body (100-250 lines) covers:

1. Grouping discipline — how to decide which RI-* items belong to the
   same feature (shared domain entity, shared user flow, transactional
   boundary, etc.).
2. Acceptance criteria writing — how to produce criteria that are
   binary pass/fail, free of vague qualifiers ("fast",
   "user-friendly"), and testable without subjective judgment.
3. Dependency identification — when feature A must appear before
   feature B because B consumes A's outputs, or when they share
   transactional state.
4. Out-of-scope discipline — requirements that are deferred or
   excluded must be listed explicitly with a reason, not silently
   dropped.
5. Anti-patterns — orphan requirements (RI-* items that appear in no
   feature and no out-of-scope list), vague ACs, dependency cycles.

## Authoring approach

`superpowers:skill-creator`. Ask questions about specific edge cases
you're unsure how to describe.

## In-session verification

Run PH-000 + PH-001 in sequence against the tiny fixture:

    mkdir -p /tmp/test-ph001-workspace
    methodology-runner run \
      tests/fixtures/tiny-requirements.md \
      --workspace /tmp/test-ph001-workspace \
      --phases PH-000-requirements-inventory,PH-001-feature-specification

Expected: halt at PH-001 baseline validation because
`feature-quality-review` is still missing. Confirms
`feature-specification` is loaded correctly.

## Commit

    git add plugins/methodology-runner-skills/skills/feature-specification/
    git commit -m "feat(skills): add feature-specification skill"

## When you're done

Type /exit.
```

---

## Prompt 7: Author feature-quality-review skill [interactive]

```
You are helping me author the `feature-quality-review` SKILL.md file.

## Role of this skill

PH-001 judge baseline. The PH-001 judge evaluates feature
specifications for: vague acceptance criteria, orphaned inventory
items, assumption conflicts between features, scope creep beyond the
inventory, and missing feature dependencies.

See spec section 11: "PH-001 judge baseline; evaluating features for
testability and completeness."

## Target file

    plugins/methodology-runner-skills/skills/feature-quality-review/SKILL.md

Frontmatter:

    ---
    name: feature-quality-review
    description: Evaluate feature specifications for testability, RI coverage, dependency completeness, and scope discipline
    ---

Body (100-250 lines) mirrors the five failure modes from the PH-001
judge_guidance in phases.py, adds concrete detection methods for each,
and describes what good judge feedback looks like.

## Authoring approach

`superpowers:skill-creator`. Reuse the patterns from the PH-000 judge
skill (prompt 4) where applicable.

## In-session verification

Run PH-000 + PH-001 fully:

    mkdir -p /tmp/test-ph001-workspace-2
    methodology-runner run \
      tests/fixtures/tiny-requirements.md \
      --workspace /tmp/test-ph001-workspace-2 \
      --phases PH-000-requirements-inventory,PH-001-feature-specification

Both phases should complete successfully — producing a requirements
inventory, a feature specification, cross-reference verification, and
phase commits. If either halts, read the failure and iterate.

## Commit

    git add plugins/methodology-runner-skills/skills/feature-quality-review/
    git commit -m "feat(skills): add feature-quality-review skill"

## When you're done

Type /exit.
```

---

## Prompt 8: Author PH-001 integration agent [interactive]

```
You are helping me author the PH-001 integration agent at
`docs/prompts/integration-agent-PH-001-feature-specification.md`.

Same pattern as the PH-000 integration agent (prompt 5), but focused
on what PH-002 (Architecture) and PH-003 (Solution Design) will need
from the feature specification:

- PH-002 needs to decompose into components. For that it needs:
  - Features that imply technology choices (clear enough to infer
    candidate stacks)
  - Non-functional requirements that bound architecture choices
  - Enough semantic content that cross-feature concerns (auth, logging,
    persistence) can be identified as cross_cutting_concerns
- PH-003 needs to produce per-component design. For that it needs:
  - Feature boundaries clear enough to map to component boundaries
  - Acceptance criteria specific enough to drive module-level design

The critic pretends to be the PH-002 architect and the PH-003 designer
in sequence and produces a structured YAML critique with the same
schema as the PH-000 critic.

## In-session verification

Run against a completed PH-001 workspace (e.g.,
/tmp/test-ph001-workspace-2 from prompt 7):

    prompt-runner run \
      docs/prompts/integration-agent-PH-001-feature-specification.md \
      --workspace /tmp/test-ph001-workspace-2

## Commit

    git add docs/prompts/integration-agent-PH-001-feature-specification.md
    git commit -m "feat(prompts): add PH-001 integration agent"

## When you're done

Type /exit.
```

---

## Prompt 9: Author architecture-decomposition skill [interactive]

```
You are helping me author the `architecture-decomposition` SKILL.md file.

## Role of this skill

PH-002 generator baseline. PH-002 Architecture is the phase that takes
a feature specification and decomposes it into technology components
with expected expertise descriptions. This skill packages the
discipline of architectural decomposition: identifying component
boundaries, choosing integration protocols, and articulating expertise
without naming concrete skill IDs.

See spec section 5 (the entire PH-002 Architecture phase design) and
section 11 entry: "PH-002 baseline; splitting an enhancement into
components, choosing boundaries, identifying integration points."

CRITICAL: the skill must reinforce that `expected_expertise` is
free-text descriptions of knowledge areas (e.g., "Python backend
development with FastAPI"), NOT concrete Claude Code skill IDs (e.g.,
"python-backend-impl"). This decoupling is essential — see spec section
5 "Why expertise descriptions instead of skill IDs".

## Target file

    plugins/methodology-runner-skills/skills/architecture-decomposition/SKILL.md

Frontmatter:

    ---
    name: architecture-decomposition
    description: Decompose features into technology components with free-text expertise descriptions and explicit integration points
    ---

Body covers: component boundary discipline, integration point
identification, technology coherence within a component, the
expertise-as-free-text rule with examples, anti-patterns (god
components, implicit state sharing, expertise lists that leak
skill-catalog terms).

## Authoring approach

`superpowers:skill-creator`. This one is subtler than the earlier
skills — the expertise-as-free-text rule is load-bearing for the
whole skill-routing design. Make sure the examples in the skill are
unambiguous about which form is correct.

## In-session verification

Run PH-000 through PH-002:

    mkdir -p /tmp/test-ph002-workspace
    methodology-runner run \
      tests/fixtures/tiny-requirements.md \
      --workspace /tmp/test-ph002-workspace \
      --phases PH-000-requirements-inventory,PH-001-feature-specification,PH-002-architecture

Expected: halt at PH-002 baseline validation because two more PH-002
skills are still missing (`tech-stack-catalog`, `architecture-review`).

## Commit

    git add plugins/methodology-runner-skills/skills/architecture-decomposition/
    git commit -m "feat(skills): add architecture-decomposition skill"

## When you're done

Type /exit.
```

---

## Prompt 10: Author tech-stack-catalog skill [interactive]

```
You are helping me author the `tech-stack-catalog` SKILL.md file.

## Role of this skill

PH-002 generator baseline. Complements `architecture-decomposition` by
providing a high-level awareness of candidate technology stacks so the
architect can make informed choices without deep specialization in any
one stack.

See spec section 11: "PH-002 baseline; high-level awareness of
candidate technology stacks (Python backend, Node backend, TypeScript
frontend, Rust, Go) without deep specialization in any one."

The skill is NOT a tutorial on any specific stack — it's a shallow
catalog with selection criteria. Deep per-stack knowledge is the job
of tech-specific skills (python-backend-impl etc.) that will be
authored in a FUTURE skill-pack version, not this v1.

## Target file

    plugins/methodology-runner-skills/skills/tech-stack-catalog/SKILL.md

Frontmatter:

    ---
    name: tech-stack-catalog
    description: High-level catalog of candidate technology stacks with shallow per-stack properties and selection criteria
    ---

Body covers candidate stacks (Python backend, Node backend, TypeScript
frontend, Go backend, Rust systems, maybe mobile stacks briefly), each
with a 3-5 sentence summary of what it's good for, what it's bad at,
and when to pick it. Ends with selection heuristics for common feature
patterns (REST API + web UI, CLI tool, background worker, etc.).

## Authoring approach

`superpowers:skill-creator`. Be deliberately shallow per stack — the
goal is to enable CHOOSING a stack, not to teach how to USE it.

## In-session verification

Same command as prompt 9, now expected to halt only on
`architecture-review`.

## Commit

    git add plugins/methodology-runner-skills/skills/tech-stack-catalog/
    git commit -m "feat(skills): add tech-stack-catalog skill"

## When you're done

Type /exit.
```

---

## Prompt 11: Author architecture-review skill [interactive]

```
You are helping me author the `architecture-review` SKILL.md file.

## Role of this skill

PH-002 judge baseline. Evaluates stack manifests for feature coverage,
expertise articulation (free-text not skill IDs), integration point
completeness, technology coherence, and decomposition rationale.

See spec section 11 and the `judge_guidance` block in phases.py for
the PH-002 Architecture phase.

## Target file

    plugins/methodology-runner-skills/skills/architecture-review/SKILL.md

Frontmatter:

    ---
    name: architecture-review
    description: Evaluate stack manifests for coverage, expertise articulation, integration completeness, and technology coherence
    ---

Body (100-250 lines) covers the five failure modes from
`phases.py::_PHASE_2_ARCHITECTURE.judge_guidance` with detection
techniques for each. Emphasize the expertise-as-free-text check: flag
any component whose `expected_expertise` list looks like concrete skill
IDs rather than free-text descriptions.

## Authoring approach

`superpowers:skill-creator`. Same pattern as earlier judge skills.

## In-session verification

Now PH-000 through PH-002 should all run:

    mkdir -p /tmp/test-ph002-workspace-full
    methodology-runner run \
      tests/fixtures/tiny-requirements.md \
      --workspace /tmp/test-ph002-workspace-full \
      --phases PH-000-requirements-inventory,PH-001-feature-specification,PH-002-architecture

Expected: all three phases complete. PH-002 produces a stack manifest
with non-empty expected_expertise lists (free-text, not skill IDs).

## Commit

    git add plugins/methodology-runner-skills/skills/architecture-review/
    git commit -m "feat(skills): add architecture-review skill"

## When you're done

Type /exit.
```

---

## Prompt 12: Author PH-002 integration agent [interactive]

```
You are helping me author the PH-002 integration agent at
`docs/prompts/integration-agent-PH-002-architecture.md`.

Same pattern as the PH-000 and PH-001 critics. Focus: what PH-003
(Solution Design) and downstream phases will need from the stack
manifest.

- PH-003 needs to produce per-component design. For that it needs:
  - Component boundaries clear enough to design against
  - Expected-expertise lists that map cleanly to specialized skills
    (the critic can simulate running the Skill-Selector against the
    manifest and flag expertise strings that are too vague)
  - Integration points with enough detail to drive interface contracts
- PH-004 (Contract-First) needs to turn components + integration
  points into typed contracts
- The stack manifest should give the Skill-Selector enough to work
  with for later phases

The critic should simulate the Skill-Selector's expertise-to-skill
mapping as one of its checks — pretending to map each expected_expertise
entry to a hypothetical skill and flagging entries too vague to map.

## Target file

    docs/prompts/integration-agent-PH-002-architecture.md

Same single-fenced format, same critique YAML schema as earlier.

## In-session verification

Run against /tmp/test-ph002-workspace-full from prompt 11.

## Commit and exit

    git add docs/prompts/integration-agent-PH-002-architecture.md
    git commit -m "feat(prompts): add PH-002 integration agent"
```

---

## Prompt 13: Author solution-design-patterns skill [interactive]

```
You are helping me author the `solution-design-patterns` SKILL.md file.

## Role of this skill

PH-003 generator baseline. Tech-agnostic design discipline for
producing per-component solution designs: separation of concerns,
interface design, dependency boundaries, error handling patterns.
Complements stack-specific skills that the Skill-Selector adds per
component via the expected_expertise mapping.

See spec section 11: "PH-003 baseline; tech-agnostic design discipline
(separation of concerns, interface design, dependency boundaries,
error handling)."

## Target file

    plugins/methodology-runner-skills/skills/solution-design-patterns/SKILL.md

Frontmatter:

    ---
    name: solution-design-patterns
    description: Tech-agnostic solution-design discipline — separation of concerns, interface design, dependency boundaries, error handling
    ---

Body (150-300 lines) covers the core discipline without assuming a
specific technology. The skill is explicit that STACK-SPECIFIC design
patterns come from other skills added by the Skill-Selector mapping
stack-manifest expected_expertise — this one is the floor, not the
ceiling.

## Authoring approach

`superpowers:skill-creator`. The subtlety here is staying
tech-agnostic while still being substantive.

## In-session verification

Run PH-000 through PH-003:

    mkdir -p /tmp/test-ph003-workspace
    methodology-runner run \
      tests/fixtures/tiny-requirements.md \
      --workspace /tmp/test-ph003-workspace \
      --phases PH-000-requirements-inventory,PH-001-feature-specification,PH-002-architecture,PH-003-solution-design

Expected: halt at PH-003 baseline validation because
`solution-design-review` is still missing.

## Commit

    git add plugins/methodology-runner-skills/skills/solution-design-patterns/
    git commit -m "feat(skills): add solution-design-patterns skill"

## When you're done

Type /exit.
```

---

## Prompt 14: Author solution-design-review skill [interactive]

```
You are helping me author the `solution-design-review` SKILL.md file.

## Role of this skill

PH-003 judge baseline. Evaluates solution designs for modularity,
testability, clarity, and orphan/god components.

See spec section 11 and phases.py judge_guidance for PH-003.

## Target file

    plugins/methodology-runner-skills/skills/solution-design-review/SKILL.md

Frontmatter:

    ---
    name: solution-design-review
    description: Evaluate solution designs for orphan components, god components, missing interactions, implicit state sharing, and untraced features
    ---

Body mirrors the five failure modes from phases.py::_PHASE_3.judge_guidance.

## Authoring approach

`superpowers:skill-creator`.

## In-session verification

Run PH-000 through PH-003 fully. All phases should complete.

## Commit

    git add plugins/methodology-runner-skills/skills/solution-design-review/
    git commit -m "feat(skills): add solution-design-review skill"

## When you're done

Type /exit.
```

---

## Prompt 15: Author PH-003 integration agent [interactive]

```
Author `docs/prompts/integration-agent-PH-003-solution-design.md`.

Focus: what PH-004 (Contract-First Interfaces) needs from the solution
design. Component boundaries clear enough to define contracts;
interaction protocols explicit enough to type; error cases hinted at.

Same structure as earlier integration agents. Run against a completed
PH-003 workspace. Commit and exit.
```

---

## Prompt 16: Author contract-first-design skill [interactive]

```
You are helping me author the `contract-first-design` SKILL.md file.

## Role of this skill

PH-004 generator baseline. Contract-first design means defining every
interface (types, operations, error modes, behavioral specs) BEFORE
implementing anything. The skill enforces: every interaction between
components has a typed contract, every operation has precise request
and response schemas, every error case is named.

See spec section 11: "PH-004 baseline; writing interface contracts
before implementations; schema-first approaches."

## Target file

    plugins/methodology-runner-skills/skills/contract-first-design/SKILL.md

Frontmatter:

    ---
    name: contract-first-design
    description: Define typed interface contracts with precise schemas, exhaustive error modes, and behavioral specs before any implementation
    ---

Body (150-300 lines) covers:

1. Schema precision — no `object` / `any` / `unknown` types; every
   field named and typed.
2. Error completeness — every operation has named error types with
   trigger conditions.
3. Behavioral specs — preconditions, postconditions, invariants.
4. Cross-contract consistency — shared data structures have matching
   fields across contracts.
5. Anti-patterns — type holes, error gaps, hidden preconditions.

## Authoring approach

`superpowers:skill-creator`.

## In-session verification

Run PH-000 through PH-004:

    mkdir -p /tmp/test-ph004-workspace
    methodology-runner run \
      tests/fixtures/tiny-requirements.md \
      --workspace /tmp/test-ph004-workspace \
      --phases PH-000-requirements-inventory,PH-001-feature-specification,PH-002-architecture,PH-003-solution-design,PH-004-interface-contracts

Expected: halt because `contract-review` missing.

## Commit

    git add plugins/methodology-runner-skills/skills/contract-first-design/
    git commit -m "feat(skills): add contract-first-design skill"
```

---

## Prompt 17: Author contract-review skill [interactive]

```
You are helping me author the `contract-review` SKILL.md file.

## Role of this skill

PH-004 judge baseline. Evaluates interface contracts for type
completeness, error coverage, cross-contract consistency, behavioral
spec completeness, and missing contracts.

See spec section 11 and phases.py judge_guidance for PH-004.

## Target file

    plugins/methodology-runner-skills/skills/contract-review/SKILL.md

Frontmatter:

    ---
    name: contract-review
    description: Evaluate interface contracts for type holes, error gaps, cross-contract inconsistency, missing contracts, and behavioural gaps
    ---

Body mirrors the five failure modes from phases.py::_PHASE_4.judge_guidance.

## Authoring approach

`superpowers:skill-creator`.

## In-session verification

Run PH-000 through PH-004 fully.

## Commit

    git add plugins/methodology-runner-skills/skills/contract-review/
    git commit -m "feat(skills): add contract-review skill"
```

---

## Prompt 18: Author PH-004 integration agent [interactive]

```
Author `docs/prompts/integration-agent-PH-004-interface-contracts.md`.

Focus: what PH-005 (Intelligent Simulations) needs from the contracts.
Precise enough schemas that simulations can produce realistic inputs
and expected outputs. Error types named so error-path scenarios can be
built. Behavioral specs exist so pre/postconditions can be asserted.

Same pattern. Run against completed PH-004 workspace. Commit and exit.
```

---

## Prompt 19: Author simulation-framework skill [interactive]

```
You are helping me author the `simulation-framework` SKILL.md file.

## Role of this skill

PH-005 generator baseline. The simulation phase writes executable
scenarios that exercise every contract BEFORE any implementation
exists, allowing integration tests to run against simulations and then
be re-run against real implementations once they're built.

See spec section 11: "PH-005 baseline; writing simulations that
exercise contracts before implementations exist."

## Target file

    plugins/methodology-runner-skills/skills/simulation-framework/SKILL.md

Frontmatter:

    ---
    name: simulation-framework
    description: Write executable simulations that exercise contracts with happy-path, error-path, and edge-case scenarios — usable as test doubles before implementations exist
    ---

Body covers:

1. Contract coverage — every operation has at least one scenario.
2. Scenario breadth — happy path, error path per error type, edge cases.
3. Input/output realism — inputs are concrete values matching contract
   schemas; expected outputs are derivable from the contract alone
   (NOT from implementation details).
4. LLM leakage prevention — simulations must not encode knowledge only
   the real service would have (no internal IDs, no timestamps).
5. Replaceability — simulations are test doubles that get swapped out
   for real implementations later, so they must be written with
   integration tests in mind.

## Authoring approach

`superpowers:skill-creator`.

## In-session verification

Run through PH-005. Expect halt on `simulation-review`.

## Commit

    git add plugins/methodology-runner-skills/skills/simulation-framework/
    git commit -m "feat(skills): add simulation-framework skill"
```

---

## Prompt 20: Author simulation-review skill [interactive]

```
You are helping me author the `simulation-review` SKILL.md file.

## Role of this skill

PH-005 judge baseline. Evaluates simulations for validation depth,
scenario realism, LLM leakage, error coverage, and contract coverage.

See spec section 11 and phases.py judge_guidance for PH-005.

## Target file

    plugins/methodology-runner-skills/skills/simulation-review/SKILL.md

Frontmatter:

    ---
    name: simulation-review
    description: Evaluate simulations for assertion depth, input realism, LLM leakage, error coverage, and contract coverage
    ---

Body mirrors the five failure modes.

## In-session verification

Run PH-000 through PH-005 fully.

## Commit

    git add plugins/methodology-runner-skills/skills/simulation-review/
    git commit -m "feat(skills): add simulation-review skill"
```

---

## Prompt 21: Author PH-005 integration agent [interactive]

```
Author `docs/prompts/integration-agent-PH-005-intelligent-simulations.md`.

Focus: what PH-006 (Incremental Implementation) needs from the
simulations. Simulations that can be run as test doubles in unit tests.
Scenarios that translate directly into integration test cases.
Simulation-replacement sequence hints.

Same pattern. Commit and exit.
```

---

## Prompt 22: Author tdd skill [interactive]

```
You are helping me author the `tdd` SKILL.md file.

## Role of this skill

PH-006 generator baseline. Test-driven development discipline:
red/green/refactor cadence, writing the failing test first, minimal
implementation to pass, refactoring under a green bar.

See spec section 11: "test-driven development discipline; red/green/
refactor; writing failing tests first; refactoring under a green bar."

## Target file

    plugins/methodology-runner-skills/skills/tdd/SKILL.md

Frontmatter:

    ---
    name: tdd
    description: Test-driven development discipline — red/green/refactor, failing test first, minimal implementation to pass, refactoring under a green bar
    ---

Body (150-300 lines) covers:

1. The red-green-refactor cycle with concrete examples.
2. What counts as a "failing test" (must fail for the RIGHT reason —
   the absence of the behavior, not a typo).
3. Minimal implementation discipline (just enough to turn the test
   green, no more).
4. Refactoring under a green bar (bar stays green throughout
   refactoring; if it goes red, revert and go smaller).
5. Anti-patterns: writing tests after code, skipping the red step,
   refactoring with a red bar, writing tests that test the
   implementation rather than the behavior.

## Authoring approach

`superpowers:skill-creator`. There's already a `superpowers:test-driven-development`
skill you can reference as a starting point — read it, then adapt for
this pack's voice and tie it into the methodology's other skills
(notably `code-review-discipline` and `traceability-discipline`).

## In-session verification

Run through PH-006. Expect halt on `code-review-discipline`.

## Commit

    git add plugins/methodology-runner-skills/skills/tdd/
    git commit -m "feat(skills): add tdd skill"
```

---

## Prompt 23: Author code-review-discipline skill [interactive]

```
You are helping me author the `code-review-discipline` SKILL.md file.

## Role of this skill

PH-006 judge baseline. Universal code review principles that apply
regardless of language: readability, testability, no dead code, no
speculative abstractions, appropriate error handling, no security
footguns.

See spec section 11: "PH-006 judge baseline; universal code review
principles (readability, testability, no dead code, no speculative
abstractions)."

## Target file

    plugins/methodology-runner-skills/skills/code-review-discipline/SKILL.md

Frontmatter:

    ---
    name: code-review-discipline
    description: Universal code review principles — readability, testability, no dead code, no speculative abstractions, appropriate error handling
    ---

Body (150-300 lines) covers the universal review criteria without
assuming a specific language. Per-language review skills come from the
expected_expertise mapping for specific components, not from this one.

## Authoring approach

`superpowers:skill-creator`.

## In-session verification

Run PH-000 through PH-006 fully. This is a big test — all six phases
should complete.

## Commit

    git add plugins/methodology-runner-skills/skills/code-review-discipline/
    git commit -m "feat(skills): add code-review-discipline skill"
```

---

## Prompt 24: Author PH-006 integration agent [interactive]

```
Author `docs/prompts/integration-agent-PH-006-incremental-implementation.md`.

Focus: what PH-007 (Verification Sweep) needs from the implementation
plan. Build order traceable to component dependencies. Unit and
integration test plan that covers all features. Simulation replacement
sequence with concrete re-test triggers.

Same pattern. Commit and exit.
```

---

## Prompt 25: Author cross-component-verification skill [interactive]

```
You are helping me author the `cross-component-verification` SKILL.md file.

## Role of this skill

PH-007 generator baseline. The final verification phase produces an
end-to-end test plan tracing every requirement through features,
acceptance criteria, and E2E tests. This skill enforces chain
completeness (no broken traceability links), test specificity (concrete
assertions), and negative coverage (boundary and failure-path tests).

See spec section 11: "PH-007 baseline; verifying that
independently-developed components integrate correctly at the contract
boundaries."

## Target file

    plugins/methodology-runner-skills/skills/cross-component-verification/SKILL.md

Frontmatter:

    ---
    name: cross-component-verification
    description: End-to-end verification discipline — chain completeness from RI to E2E, concrete assertions, negative coverage at component boundaries
    ---

Body (100-250 lines) covers: traceability chain verification, E2E
test specificity (no generic "page loads" assertions), negative test
coverage for any feature that accepts input, and coverage summary
accuracy.

## Authoring approach

`superpowers:skill-creator`.

## In-session verification

Run all 8 phases. Expect halt on `verification-review`.

## Commit

    git add plugins/methodology-runner-skills/skills/cross-component-verification/
    git commit -m "feat(skills): add cross-component-verification skill"
```

---

## Prompt 26: Author verification-review skill [interactive]

```
You are helping me author the `verification-review` SKILL.md file.

## Role of this skill

PH-007 judge baseline. Evaluates verification reports for broken
traceability chains, superficial tests, missing negative tests, phantom
references, and coverage-summary accuracy.

See spec section 11 and phases.py judge_guidance for PH-007.

## Target file

    plugins/methodology-runner-skills/skills/verification-review/SKILL.md

Frontmatter:

    ---
    name: verification-review
    description: Evaluate end-to-end verification reports for chain completeness, test specificity, negative coverage, phantom references, and coverage accuracy
    ---

Body mirrors the five failure modes from phases.py::_PHASE_7.judge_guidance.

## Authoring approach

`superpowers:skill-creator`.

## In-session verification

THE BIG ONE. Run all 8 phases end-to-end against the tiny requirements
fixture:

    mkdir -p /tmp/test-full-pipeline
    methodology-runner run \
      tests/fixtures/tiny-requirements.md \
      --workspace /tmp/test-full-pipeline

(No --phases flag means all phases run.) Every phase must complete
successfully. The run should produce:

- docs/requirements/requirements-inventory.yaml (PH-000)
- docs/features/feature-specification.yaml (PH-001)
- docs/architecture/stack-manifest.yaml (PH-002)
- docs/design/solution-design.yaml (PH-003)
- docs/design/interface-contracts.yaml (PH-004)
- docs/simulations/simulation-definitions.yaml (PH-005)
- docs/implementation/implementation-plan.yaml (PH-006)
- docs/verification/verification-report.yaml (PH-007)
- 8 phase-NNN-skills.yaml manifests
- 8 generator-prelude.txt and judge-prelude.txt files
- End-to-end cross-reference verification

This is the victory lap. If it works, the skill pack is ready to
distribute.

## Commit

    git add plugins/methodology-runner-skills/skills/verification-review/
    git commit -m "feat(skills): add verification-review skill"
```

---

## Prompt 27: Full pipeline smoke test and release notes [interactive]

```
You are helping me wrap up the skill pack authoring work by running a
full end-to-end smoke test against the tiny requirements fixture and
documenting the release readiness.

## Tasks

1. Run the full pipeline against the tiny requirements one more time,
   this time in a fresh workspace to confirm reproducibility:

       mkdir -p /tmp/test-release-smoke
       methodology-runner run \
         tests/fixtures/tiny-requirements.md \
         --workspace /tmp/test-release-smoke

   All 8 phases must complete.

2. Spot-check a few of the generated artifacts for sanity (not for
   correctness — just for "did the methodology actually use the skills
   we authored"):
   - Inspect the generator-prelude.txt for at least 3 different phases
     and confirm each references the expected skills.
   - Inspect one of the phase-NNN-skills.yaml manifests and confirm the
     Skill-Selector emitted reasonable choices.
   - Read the final verification report and see if the traceability
     chain is complete.

3. Update `plugins/methodology-runner-skills/README.md` with:
   - A note that all 18 v1 skills are now present
   - The full list of 18 skills with one-line roles
   - A quick-start showing how to run from the repo root (cwd-based
     discovery — no symlinks, no env vars)
   - A pointer to the spec doc

4. Write a brief release-notes section at the end of
   docs/superpowers/specs/2026-04-09-skill-pack-and-interactive-harness-notes.md
   listing:
   - What was built (18 skills, 7 integration agents, plugin scaffold,
     prompt-runner extensions)
   - What still needs to happen (PyPI publishing, plugin library
     publishing, any skills that proved too shallow and need revision)
   - Any open bugs or rough edges discovered during authoring

5. Commit the README and release notes updates:

       git add plugins/methodology-runner-skills/README.md \
               docs/superpowers/specs/2026-04-09-skill-pack-and-interactive-harness-notes.md
       git commit -m "docs(skills): v1 skill pack complete — release notes"

## When you're done

Tell me the commit hash and any open issues you flagged in the
release notes, then type /exit. Congratulations — the methodology is
ready to drive real work.
```
