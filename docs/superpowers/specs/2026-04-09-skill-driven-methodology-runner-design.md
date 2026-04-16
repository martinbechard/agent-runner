# Skill-Driven Methodology Runner — Design Specification

**Status:** Draft — awaiting human review before implementation plan
**Date:** 2026-04-09
**Source:** Brainstorming session, 2026-04-09
**Related components:** methodology-runner (CD-002), prompt-runner (CD-001), methodology (M-001..M-006)

---

## 1. Context

The methodology-runner component (designed in CD-002, implemented under .methodology/src/cli/methodology_runner/) orchestrates an AI-driven software development pipeline across the phases defined in M-002. Each phase produces artifacts that feed downstream phases; each generator call runs inside a generate-judge-revise loop handled by prompt-runner.

The current implementation has no explicit awareness of technology-specific knowledge. When the methodology generates prompts for the implementation phase, it cannot load specialized knowledge about Python backend conventions, TypeScript frontend patterns, pytest discipline, or any other language- or framework-specific best practices. Every prompt is written from scratch in the PR-NNN input files, which produces four concrete problems:

1. **Technology framing gets hand-coded into each prompt, inconsistently.** The PR-001 run built methodology-runner itself in Python, and the string "Python" appears 17 times across the prompt file with different phrasings, different levels of detail, and occasional gaps where the generator had to guess at conventions.
2. **Technology-agnostic phases are mixed with technology-specific ones.** Requirements, features, architecture, and verification should in principle work identically for any stack. Design, implementation, and testing need deep language-specific knowledge. The current PR file format does not distinguish these.
3. **Adding a new technology requires editing every PR-NNN file** rather than registering new skills once.
4. **Methodology-wide quality rules** (TDD discipline, traceability, code review) must be re-stated in every prompt.

Claude Code provides a skill mechanism that solves exactly this problem. Skills are YAML-fronted markdown files loaded into the current conversation context on demand; they inject specialized knowledge without spawning sub-agents (which would lose context) and without consuming context space until needed. But methodology-runner does not currently load skills, and the methodology documents (M-001 through M-006) do not describe a skill-routing mechanism.

A second, related gap: the current phase chain in M-002 is

```
PH-000 Requirements Inventory
  → PH-001 Feature Specification
    → PH-002 Solution Design
      → PH-003 Contract-First Interfaces
        → PH-004 Intelligent Simulations
        → PH-005 Incremental Implementation
          → PH-006 Verification Sweep
```

There is no phase between Feature Specification and Solution Design whose job is to decompose the enhancement into technology components. Solution Design is asked to both choose the stack (HTTP API + web frontend + database) and design within it (class diagrams, data models, control flow), conflating two concerns that operate at different levels of abstraction. This conflation also removes the natural pivot point for skill routing: there is no artifact that declares "component CMP-001 is a Python backend" for downstream phases to consume.

## 2. Goals

This specification introduces a skill-routing mechanism for methodology-runner that is:

- **Role-agnostic at the methodology layer.** The methodology continues to speak in terms of artifact-builder and artifact-verifier (from M-003). Specialization happens at the skill layer, not the role layer.
- **Adaptive across phases.** Decisions made in later phases can introduce skills that earlier phases could not anticipate (example: a design phase that chooses Celery for async processing adds a celery-patterns skill that was not in the architecture phase's baseline).
- **Deterministic within a single run.** Once a phase's skill set is chosen, it is locked and materialized as a workspace artifact. The same run does not produce drifting skill lists across iterations of the same phase.
- **Fully auditable.** Every skill-selection decision is a workspace file with a human-readable rationale. Troubleshooting a bad prompt does not require re-running the selector; the decision and its reasoning are grep-able and editable.
- **Failure-transparent.** No silent fallbacks or warnings. Any failure in an essential quality mechanism halts the pipeline with state preserved for human examination and correction.
- **Distributable.** The tool and its baseline skill pack are installable via idiomatic mechanisms (pip/pipx for the Python CLI, Claude Code plugin library for the skill pack) without forcing users into a single non-idiomatic packaging.

## 3. Non-goals

- **Replacing the existing prompt-runner contract.** prompt-runner remains a generic, skill-agnostic driver. Its only new feature is a prelude-prepending mechanism.
- **Introducing technology-specific role documents in M-003.** The six generic roles (checklist-extractor, checklist-validator, artifact-generator, artifact-judge, traceability-validator, pipeline-orchestrator) remain as-is.
- **Dynamic runtime skill installation.** If a required skill is not discoverable on disk at run time, methodology-runner halts rather than attempting to fetch or install it.
- **Parallel per-component phase execution.** PH-006 implementing CMP-001 and CMP-002 in parallel is out of scope.
- **Mid-phase skill re-selection.** The selector runs once per phase and its output is locked. A future spec may revisit this if mid-phase surprises prove common.
- **Per-prompt skill selection** (running the selector for every individual generator call within a phase) is explicitly rejected.

## 4. Design overview

The design introduces four coordinated changes across three layers of the system:

### At the methodology layer (M-002)

- A new phase **PH-002 Architecture** is inserted between Feature Specification and Solution Design. Existing phases PH-002 through PH-006 renumber to PH-003 through PH-007.
- The new phase's primary output is a **stack manifest** artifact that decomposes the enhancement into components and declares the technology, frameworks, and expected expertise (as free-text descriptions, not skill IDs) for each.

### At the methodology-runner layer

- A new **Skill-Selector agent** runs once at the start of every phase, reading the phase definition, baseline skill configuration, discovered skill catalog, and all prior phase artifacts, and emitting a phase-NNN-skills.yaml file that declares the generator and judge skill sets for that phase with a rationale.
- A new **skill catalog discovery** mechanism walks the standard Claude Code skill locations at the start of every run and builds an in-memory catalog from SKILL.md frontmatter.
- A new **baseline skills configuration** file (.methodology/docs/skills-baselines.yaml) declares the non-negotiable skills per phase and is read at run time so baselines can be evolved without code changes.
- The orchestrator composes the generator and judge preludes from the selector's output and passes them to prompt-runner via new flags.

### At the prompt-runner layer

- Two new optional command-line flags, --generator-prelude and --judge-prelude, each pointing at a text file whose contents are prepended to every generator or judge Claude call within the run. prompt-runner remains unaware of skills as a concept.

### At the distribution layer

- methodology-runner is published to PyPI and installed via pipx install methodology-runner.
- A companion Claude Code plugin methodology-runner-skills is published to the plugin library and installed via /plugin install methodology-runner-skills. It contains the baseline skill pack (TDD, traceability-discipline, architecture-decomposition, tech-stack-catalog, python-backend-impl, python-code-review, typescript-frontend-impl, react-impl, and so on).
- Users can supplement the baseline pack with project-local skills under .claude/skills/ or user-global skills under ~/.claude/skills/. Auto-discovery picks up all three locations transparently.

### Per-phase execution flow

```
┌──────────────────────────────────────────────────────────────────┐
│ methodology-runner: per-phase loop                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Load baseline skills for this phase from skills-baselines.yaml│
│  2. Walk .claude/skills/ locations, build catalog from SKILL.md  │
│  3. Invoke Skill-Selector (single Claude call):                  │
│       inputs:  phase definition, baseline list, compact catalog, │
│                prior workspace artifacts (summarized if large),  │
│                stack manifest if it exists                       │
│       output:  phase-NNN-skills.yaml (committed before use)      │
│  4. Validate selector output:                                    │
│       - parseable YAML                                           │
│       - required fields present                                  │
│       - all skill IDs exist in catalog                           │
│       - baseline skills all present with source: baseline        │
│       - every non-baseline skill has non-empty rationale         │
│       → any failure is a critical halt                           │
│  5. Build generator_prelude.txt and judge_prelude.txt from       │
│     the selector's output                                        │
│  6. Generate phase-NNN-prompts.md via the existing meta-prompt   │
│     mechanism                                                    │
│                                                                  │
│  ┌─ cross-reference retry loop (up to N=2 retries) ────────┐     │
│  │                                                         │     │
│  │  7. Invoke prompt-runner with --generator-prelude and   │     │
│  │     --judge-prelude flags                               │     │
│  │  8. Cross-reference verification                        │     │
│  │     - pass  → exit loop, go to step 9                   │     │
│  │     - fail  → if retries remaining:                     │     │
│  │                 re-generate phase-NNN-prompts.md with   │     │
│  │                 cross-ref issues as feedback;           │     │
│  │                 skill manifest stays LOCKED (no         │     │
│  │                 selector re-run by default);            │     │
│  │                 back to step 7                          │     │
│  │               if retries exhausted:                     │     │
│  │                 critical halt (failure mode 11)         │     │
│  │                                                         │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  9. Commit phase artifacts including phase-NNN-skills.yaml       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## 5. New methodology phase: PH-002 Architecture

### Purpose

Decompose the enhancement into technology components, declaring for each its role, technology stack, candidate frameworks, and the expertise required to build it (expressed as free-text descriptions). This phase does not design the components in detail (that is Solution Design's job in the renumbered PH-003). It produces the bridge artifact that turns a feature specification into a technology-aware plan without coupling itself to the runner's skill catalog.

### Inputs

- PH-001 Feature Specification artifact (features.yaml or equivalent)
- PH-000 Requirements Inventory artifact (for cross-reference)
- External references declared in the phase config (optional technology catalog documents)

### Primary output: stack-manifest.yaml

```yaml
# stack-manifest.yaml — produced by PH-002 Architecture

components:
  - id: CMP-001-backend
    name: "HTTP API server"
    role: "Exposes the REST API backing the admin dashboard and the public mobile app"
    technology: python
    runtime: "python3.12"
    frameworks:
      - fastapi
      - sqlalchemy
    persistence: postgresql
    expected_expertise:
      - "Python backend development"
      - "FastAPI framework conventions and best practices"
      - "SQLAlchemy ORM patterns and migrations"
      - "Test-driven development with pytest"
      - "Python code review discipline"
    features_served:
      - FT-001
      - FT-002
      - FT-007

  - id: CMP-002-admin-ui
    name: "Admin dashboard frontend"
    role: "React SPA consumed by internal operators for content moderation"
    technology: typescript
    runtime: "node22"
    frameworks:
      - react
      - vite
      - tanstack-query
    expected_expertise:
      - "TypeScript frontend development"
      - "React component design and hooks"
      - "Accessibility review and WCAG compliance"
      - "Test-driven development with vitest"
    features_served:
      - FT-003
      - FT-004

integration_points:
  - id: IP-001
    between: [CMP-001-backend, CMP-002-admin-ui]
    protocol: "HTTP/JSON over TLS"
    contract_source: "OpenAPI document produced in PH-004"

rationale: |
  The feature specification calls for a browser-based admin interface over
  a persistent data store. Splitting into a Python backend (justified by
  team familiarity and existing auth infrastructure per requirement RI-017)
  and a React frontend (justified by FR-012's accessibility mandate, which
  rules out server-rendered approaches) gives us the cleanest decomposition.
```

### Baseline skills for PH-002 itself

PH-002 is a technology-agnostic phase whose job is to *choose* a technology, so it loads skills that support that choice rather than skills for a specific stack:

- tech-stack-catalog — high-level awareness of candidate technologies (Python backend, Node backend, TypeScript frontend, Rust, Go, etc.)
- architecture-decomposition — patterns for splitting enhancements into components
- traceability-discipline — universal

These are declared in skills-baselines.yaml; the Skill-Selector may add more based on the feature specification (for example, if the features strongly suggest a mobile app, the selector may add a mobile-architecture-catalog skill).

### Downstream consumption

Every phase from PH-003 onward reads stack-manifest.yaml as an input source. The Skill-Selector for those phases reads each component's expected_expertise list and maps each free-text expertise description to concrete skill IDs from the discovered skill catalog (by matching expertise descriptions against skill descriptions). The selector may also add skills beyond what the expertise list implies when later phase decisions reveal new needs (for example, a design phase introducing Celery adds celery-patterns regardless of whether async processing was listed as expected expertise).

### Why expertise descriptions instead of skill IDs

The expected_expertise field deliberately uses free-text human-readable descriptions rather than concrete Claude Code skill IDs. This decouples the architecture phase from the skill catalog: the architect agent can reason about "what kind of knowledge will this component need" without knowing which SKILL.md files are installed on the runner's machine or whether the catalog uses names like python-backend-impl or py-backend-v2. The architect is an expert in decomposition and technology choice, not in skill-naming conventions.

The Skill-Selector has the catalog as one of its inputs and is responsible for mapping each expertise string to one or more concrete skill IDs. Matching an expertise like "FastAPI framework conventions and best practices" to a catalog entry described as "Conventions for building FastAPI applications" is a trivial judgment call — exactly the kind of task the selector is designed for. The mapping is documented in the selector's output rationale, so every expertise-to-skill link is auditable.

This also makes the stack manifest portable across skill pack versions: the same architecture output can drive skill selection against different catalogs (for example, if two teams use the same methodology with different skill pack snapshots, or if the skill pack is renamed without touching the architecture output).

### Renumbering impact

Existing phases are renumbered as follows:

| Old ID | New ID | Name |
|---|---|---|
| PH-002 | PH-003 | Solution Design |
| PH-003 | PH-004 | Contract-First Interface Definitions |
| PH-004 | PH-005 | Intelligent Simulations |
| PH-005 | PH-006 | Incremental Implementation |
| PH-006 | PH-007 | Verification Sweep |

All M-002 phase documents, all CD-002 references to phase IDs, all phases.py code constants, and all existing workspace state.json files produced by prior runs must be updated or migrated. Because the project is greenfield with no users beyond the author (per CLAUDE.md development philosophy), existing run artifacts can be discarded rather than migrated.

## 6. Skill-Selector agent

### Purpose

Decide which skills the artifact-builder and artifact-verifier should load for this phase, producing an auditable workspace artifact that drives the phase's prelude construction.

### Invocation point

Exactly once per phase, before the phase's meta-prompt (prompt-generator) runs. The selector's output is read by the orchestrator to build prelude text files, and by the phase itself for rationale context.

### Inputs

The selector receives, via its Claude call prompt:

1. **Phase definition** — the full M-002 entry for the current phase: purpose, input sources, output schema, quality criteria.
2. **Baseline skill list for this phase** — read from skills-baselines.yaml, passed explicitly as "these skills MUST appear in your output with source: baseline".
3. **Discovered skill catalog (compact form)** — the list of available skill IDs with their one-line descriptions only. Not the full SKILL.md content. Each entry is approximately 100-200 bytes, so a catalog of 100 skills fits in roughly 10-20 KB of prompt text. See the context-budget section for the two-pass rationale.
4. **Prior phase artifacts** — every file in the workspace from previous phases. Small artifacts (less than ~5 KB each) are passed in full. Larger artifacts are passed as a file path plus a short AI-generated summary (1-2 paragraphs) produced by a separate summarization call the first time the artifact is referenced. Summaries are cached in the workspace as phase-NNN-summary.md so subsequent selectors reuse them.
5. **Stack manifest** — if it exists yet (from PH-002 or later). Passed in full; it is small and load-bearing, and the selector must read the expected_expertise list to build skill mappings.

### Output: phase-NNN-skills.yaml

```yaml
# phase-006-skills.yaml — produced by Skill-Selector for PH-006

phase_id: PH-006
selector_run_at: 2026-04-09T10:42:17Z
selector_model: claude-opus-4-6

generator_skills:
  - id: tdd
    source: baseline
    rationale: "Baseline for all implementation phases per skills-baselines.yaml"
  - id: traceability-discipline
    source: baseline
    rationale: "Baseline for every phase"
  - id: python-backend-impl
    source: expertise-mapping
    mapped_from: "Python backend development"
    rationale: "Stack manifest CMP-001-backend lists this expertise. Catalog entry python-backend-impl (description: 'Conventions for Python backend services') is a direct match."
  - id: fastapi-conventions
    source: expertise-mapping
    mapped_from: "FastAPI framework conventions and best practices"
    rationale: "Catalog entry fastapi-conventions (description: 'FastAPI application patterns, dependency injection, and routing') matches the expertise exactly."
  - id: sqlalchemy-patterns
    source: expertise-mapping
    mapped_from: "SQLAlchemy ORM patterns and migrations"
    rationale: "Catalog entry sqlalchemy-patterns matches; note the catalog does not have a separate 'migrations' skill, so migration knowledge is assumed to be part of this one skill."
  - id: celery-patterns
    source: selector-judgment
    rationale: |
      PH-003 Solution Design (solution-design.md, section 4.2) chose Celery
      for background job processing of image thumbnails. Celery was NOT
      listed in the stack manifest's expected_expertise because the
      architect did not foresee the async requirement. The design phase
      surfaced it. Catalog entry celery-patterns exists and is loaded.

judge_skills:
  - id: traceability-discipline
    source: baseline
  - id: python-code-review
    source: expertise-mapping
    mapped_from: "Python code review discipline"
    rationale: "Direct catalog match."
  - id: pytest-coverage-review
    source: selector-judgment
    rationale: |
      PH-003 set a coverage target of 85% per critical path. Loading this
      skill so the judge knows to verify the coverage claim rather than
      accept it on faith. Not in expected_expertise but implied by the
      design's explicit coverage target.

overall_rationale: |
  PH-006 is an implementation phase for CMP-001-backend (Python/FastAPI).
  Baseline (tdd, traceability-discipline) is universal. The stack manifest
  provided five expertise descriptions; four mapped cleanly to catalog
  entries (python-backend-impl, fastapi-conventions, sqlalchemy-patterns,
  python-code-review), and one (Test-driven development with pytest) was
  covered by the baseline tdd skill. The Solution Design output (PH-003)
  revealed a Celery-based async job pattern not present in the expertise
  list, prompting addition of celery-patterns via selector judgment. The
  judge gets a mirrored but narrower skill set focused on review criteria
  and coverage verification.
```

### System prompt (sketch)

The selector's system prompt (concrete text to be refined during implementation) should enforce:

- **Role clarity:** "You are a Skill-Selector for the AI-Driven Development Methodology pipeline. Your sole job is to choose which skills the generator and judge should load for phase N. You do not generate artifacts, you do not evaluate artifacts, and you do not modify any prior work."
- **Input framing:** "You will receive the phase definition, a list of baseline skills that MUST appear in your output unchanged, the catalog of available skills with descriptions, and summaries of all prior phase artifacts."
- **Output contract:** "Produce a YAML document with exactly these top-level keys: phase_id, selector_run_at, selector_model, generator_skills, judge_skills, overall_rationale. Every entry in generator_skills and judge_skills must have id, source, and rationale fields. Every id must exist in the catalog. Every baseline skill must appear with source: baseline."
- **Judgment framing:** "Baseline skills are the methodology's non-negotiable floor. The stack manifest's expected_expertise list is strong evidence but not prescriptive — your job is to map each expertise description to one or more concrete skill IDs from the catalog, using skill descriptions as the matching target. Record every mapping in the 'mapped_from' field. Additional choices beyond the expertise list should be grounded in specific decisions visible in prior phase artifacts — cite them by file path and section in the rationale."
- **Anti-hallucination:** "Never invent a skill ID. If the catalog does not contain a skill you feel is needed, say so in overall_rationale but do not include it in the lists."

### Granularity and locking

The selector runs **once per phase**. Its output is committed to the workspace before the phase runs. Mid-phase iterations of prompt-runner's revise loop do not trigger selector re-runs; they use the locked phase-NNN-skills.yaml. If a phase is retried as a whole (because cross-reference verification failed), the orchestrator may choose to re-run the selector or reuse the prior output — decided by an orchestrator config flag (default: reuse, to preserve determinism within a single enhancement run).

## 7. Skill catalog discovery

### Mechanism

At the start of every methodology-runner run (before any phase executes), walk the following paths in order and collect every SKILL.md file:

1. **Project-local skills:** workspace/.claude/skills/**/SKILL.md — highest priority.
2. **User-global skills:** ~/.claude/skills/**/SKILL.md — second priority.
3. **Plugin-installed skills:** ~/.claude/plugins/*/skills/**/SKILL.md — lowest priority.

For each SKILL.md, parse the YAML frontmatter and extract:

- **id** — from the name field, or derived from the parent directory name if absent.
- **description** — from the description field (required; missing description = skill is skipped with a warning).
- **source_path** — the absolute path to the SKILL.md file (for diagnostics).
- **source_location** — one of project, user, plugin (for priority resolution).

Build an in-memory dict keyed by skill ID. If the same ID appears in multiple locations, higher-priority wins (project beats user beats plugin). Log every override loudly — a project-local skill shadowing a plugin skill is a legitimate operation but must be visible in the run log.

### No static catalog file

The skill catalog is never persisted to disk as a standalone file. Keeping the catalog synthetic and rebuilt per run eliminates a whole class of drift bugs (catalog out of sync with what Claude Code actually has installed). The SKILL.md files on disk are the single source of truth.

### Validation at build time

Every discovered entry is validated:

- YAML frontmatter must parse.
- name or directory must yield a valid ID (lowercase, kebab-case, no spaces).
- description must be non-empty.
- Required fields for the SKILL.md format must be present per Claude Code spec.

Invalid entries are skipped with a loud warning. If zero valid entries are discovered, that is a critical halt: see failure mode 7 in the error handling section.

## 8. Baseline skills configuration

### File location and schema

```yaml
# .methodology/docs/skills-baselines.yaml
#
# Non-negotiable skills per methodology phase. The Skill-Selector treats
# these as required floor and may add more skills on top based on stack
# manifest hints and judgments about prior phase artifacts.
#
# Changing this file does not require a code change or a release. The
# methodology-runner reads it fresh at the start of every run.

version: 1

phases:
  PH-000:
    description: "Requirements Inventory — purely extractive, tech-agnostic"
    generator_baseline:
      - requirements-extraction
      - traceability-discipline
    judge_baseline:
      - requirements-quality-review
      - traceability-discipline
    # Note: PH-000 is about extracting requirements from existing documents,
    # not eliciting them from stakeholders. The skill is named accordingly.

  PH-001:
    description: "Feature Specification — structuring requirements into features"
    generator_baseline:
      - feature-specification
      - traceability-discipline
    judge_baseline:
      - feature-quality-review
      - traceability-discipline

  PH-002:
    description: "Architecture — decompose into tech components"
    generator_baseline:
      - tech-stack-catalog
      - architecture-decomposition
      - traceability-discipline
    judge_baseline:
      - architecture-review
      - traceability-discipline

  PH-003:
    description: "Solution Design — per-component design"
    generator_baseline:
      - solution-design-patterns
      - traceability-discipline
    judge_baseline:
      - solution-design-review
      - traceability-discipline
    # solution-design-patterns gives the generator baseline design discipline
    # (separation of concerns, interface design, dependency boundaries) that
    # is independent of tech stack. Per-component language-specific design
    # skills are added by the selector by mapping expected_expertise from
    # the stack manifest.

  PH-004:
    description: "Contract-First Interface Definitions"
    generator_baseline:
      - contract-first-design
      - traceability-discipline
    judge_baseline:
      - contract-review
      - traceability-discipline

  PH-005:
    description: "Intelligent Simulations"
    generator_baseline:
      - simulation-framework
      - traceability-discipline
    judge_baseline:
      - simulation-review
      - traceability-discipline

  PH-006:
    description: "Incremental Implementation"
    generator_baseline:
      - tdd
      - traceability-discipline
    judge_baseline:
      - code-review-discipline
      - traceability-discipline
    # Per-component impl skills added by selector from stack manifest

  PH-007:
    description: "Verification Sweep"
    generator_baseline:
      - cross-component-verification
      - traceability-discipline
    judge_baseline:
      - verification-review
      - traceability-discipline
```

### Evolution

This file is intended to be edited by hand as the methodology evolves. Adding a phase-wide quality rule (for example, "every implementation phase must now include accessibility-review for frontend components") is a one-line edit. No code changes, no release. The file is read at the start of every run; the change takes effect on the next invocation.

### Validation at load time

The orchestrator validates skills-baselines.yaml against the discovered catalog at run start (before any phase executes). Every baseline ID must exist in the catalog. If any baseline is missing from the catalog, that is a critical halt — fail fast rather than discovering the problem mid-run.

## 8A. Context budget management

Loading skills and prior artifacts into Claude calls is not free. A naive implementation that passes every skill's full SKILL.md content plus every prior artifact's full text into every generator call will blow the context budget on non-trivial enhancements. This section defines the strategies the implementation must use to keep context bounded.

### Three sources of context pressure

1. **The skill catalog**, passed to the Skill-Selector once per phase. A large project may have 50-100+ skills discovered across project, user, and plugin locations. If each full SKILL.md is several KB, a naive catalog dump would be hundreds of KB.
2. **Prior phase artifacts**, passed to the Skill-Selector and referenced by the generator. Over the course of a 7-phase run, these accumulate. By phase PH-006 there are artifacts from PH-000 through PH-005 that may all be relevant, plus the cross-reference verdicts from each.
3. **Loaded skill content**, consumed by the generator and judge. If the selector picks 6 skills for a phase and each skill is several KB, the generator call starts out with tens of KB of skill content before it has seen the prompt-pair at all.

### Strategy for the skill catalog (two-pass)

The selector receives a **compact catalog**: only the skill ID, the one-line description, and the source path. No SKILL.md body content. This form is approximately 100-200 bytes per skill, so a 100-skill catalog fits in 10-20 KB of prompt text — well within budget for a small selector call.

Full SKILL.md content is loaded only by the generator and judge, and only for skills the selector chose. The loading mechanism is the Skill tool (primary design) or inline prelude content (fallback design); see section 9.

This is a classic two-pass pattern: pass 1 uses compact metadata to select, pass 2 loads full content only for the selected subset.

### Strategy for prior artifacts

The selector receives artifacts according to a size threshold:

- **Small artifacts** (under ARTIFACT_FULL_CONTENT_THRESHOLD bytes, implementation default 5000): passed in full.
- **Large artifacts**: passed as a file path plus a pre-generated summary (1-2 paragraphs). Summaries are produced by a separate summarization Claude call the first time an artifact crosses the threshold, then cached in the workspace as phase-NNN-artifact-summary.md. Subsequent phases reuse the cached summary.

Cross-reference verdicts from prior phases are always passed in full regardless of size — they are typically small and load-bearing for the selector's judgment about remaining work.

If the selector decides it needs to see the full content of a large artifact, it can say so in its rationale with the string "REQUEST_FULL_ARTIFACT: <path>" and the orchestrator will re-invoke the selector with that artifact's full content substituted in. This is an escape hatch for cases where the summary is too lossy. It counts as a second selector invocation and is logged.

### Strategy for loaded skill content

The number of skills the selector picks for any single phase is capped at MAX_SKILLS_PER_PHASE (implementation default 8). If the selector wants to load more than 8, it must prioritize and document the trade-off in the overall_rationale. This cap protects the generator's context budget from well-intentioned but excessive skill loading.

The primary design (see section 9) assumes Claude Code's Skill tool loads skill content progressively — the generator invokes Skill(skill_id) and the content is loaded into context at that moment, not before. This means the nominal prelude size is small (just the list of skill IDs to load) even if the total skill content is large. The fallback design inlines all skill content into the prelude text, which is more expensive and makes the MAX_SKILLS_PER_PHASE cap more consequential.

### Configurable thresholds

All three thresholds live as named constants in the methodology-runner Python code (per CLAUDE.md guidance against literal constants):

```python
# .methodology/src/cli/methodology_runner/constants.py (new file)

ARTIFACT_FULL_CONTENT_THRESHOLD = 5000   # bytes
MAX_SKILLS_PER_PHASE = 8
MAX_CATALOG_SIZE_WARNING = 100           # skills; log warning but don't halt
```

These can be tuned based on observed usage. They are not user-configurable via CLI flags in v1 to keep the surface area small. If the defaults prove wrong in practice, promoting them to CLI flags is a trivial follow-up.

## 9. Prompt-runner prelude feature

### New command-line flags

prompt-runner run gains two new optional flags:

```
--generator-prelude PATH    Text file whose contents are prepended to
                            every generator Claude call in this run.
                            If omitted, no prelude is prepended.

--judge-prelude PATH        Text file whose contents are prepended to
                            every judge Claude call in this run. If
                            omitted, no prelude is prepended.
```

### Behavior

- Prelude content is read once, at run start, and cached for the duration.
- For every generator call, the prelude text is prepended to the prompt-pair's generation prompt with a single blank line separator.
- For every judge call (including revise-loop iterations), the prelude text is prepended to the judge message with a single blank line separator.
- Preludes apply to all prompts in the run uniformly. There is no per-prompt prelude selection within a single prompt-runner invocation (if per-phase differentiation is needed, that is methodology-runner's job: it runs prompt-runner once per phase with the appropriate preludes).

### Skill-agnostic contract

prompt-runner does not interpret, parse, or understand the prelude content. It is opaque text. This keeps prompt-runner fully skill-agnostic and usable in interactive contexts (a human can write their own preludes for any purpose, not just skill loading).

### Prelude content format (two designs, pending validation)

The prelude content's format depends on a technical assumption that must be validated before implementation: **does the Skill tool work inside nested claude --print subprocess invocations?** prompt-runner spawns generator and judge Claude calls via claude --print subprocesses; if those subprocesses have access to the same Skill tool mechanism as an interactive Claude Code session, the primary design below is correct. If they do not, the fallback design must be used instead.

This assumption is called out explicitly as **Phase 0 validation** in the implementation impact section (14). The spec commits to the behavior — "the generator and judge load specialized knowledge named by the selector" — without committing to the wire format, so either design is acceptable.

#### Primary design: instruct the agent to invoke skills by name

```
# Phase 006 — Generator Prelude

Before you begin the task below, invoke the following Claude Code skills
in the order listed. Each skill must be invoked via the Skill tool with
its exact ID.

Skills to load:
- tdd
- traceability-discipline
- python-backend-impl
- fastapi-conventions
- sqlalchemy-patterns
- celery-patterns

Rationale for this skill set (for your awareness):
PH-006 implements CMP-001-backend (Python/FastAPI). The celery-patterns
skill was added because Solution Design (PH-003) section 4.2 chose
Celery for background job processing.

After you have loaded these skills, proceed with the task below.

---
```

The triple-dash separator delimits the prelude from the prompt-pair's generation prompt. prompt-runner simply concatenates; the generator Claude call sees one continuous message. The agent is expected to invoke the Skill tool for each skill ID, which loads the skill content into its context just-in-time.

**Assumption:** claude --print subprocesses have the Skill tool available and skill discovery works the same way as in interactive sessions. Validated in Phase 0.

#### Fallback design: inline skill content in the prelude

If Phase 0 validation shows that the Skill tool is not available or does not work reliably in nested claude --print calls, methodology-runner inlines the full SKILL.md content of each selected skill into the prelude, delimited by clear section markers:

```
# Phase 006 — Generator Prelude (Inline Skill Content)

The following specialized knowledge applies to this task. Read and apply
every section before beginning the task below.

═══════════════════════════════════════════════════════════
Skill: tdd
Source: ~/.claude/.methodology/skills/tdd/SKILL.md
═══════════════════════════════════════════════════════════

[full SKILL.md content here, minus the YAML frontmatter]

═══════════════════════════════════════════════════════════
Skill: python-backend-impl
Source: ~/.claude/.methodology/skills/python-backend-impl/SKILL.md
═══════════════════════════════════════════════════════════

[full SKILL.md content here, minus the YAML frontmatter]

... (one section per skill) ...

═══════════════════════════════════════════════════════════
End of skill content
═══════════════════════════════════════════════════════════

Rationale for this skill set (for your awareness):
PH-006 implements CMP-001-backend (Python/FastAPI). The celery-patterns
skill was added because Solution Design (PH-003) section 4.2 chose
Celery for background job processing.

After you have applied this knowledge, proceed with the task below.

---
```

The fallback design is token-heavier (all skill content is passed upfront rather than lazily loaded) but has zero dependency on the Skill tool being available in the subprocess. The MAX_SKILLS_PER_PHASE cap from section 8A is particularly important under the fallback design because it directly bounds the prelude size.

#### Which design the implementation uses

Phase 0 validation runs before any substantial implementation work. It creates a minimal test skill (test-marker) in ~/.claude/skills/ with distinctive content, runs claude --print with a prompt that instructs the agent to invoke Skill("test-marker"), and inspects the response for the distinctive content. If the response shows the skill content was loaded, the primary design is used. Otherwise, the fallback design is used, and the selector's MAX_SKILLS_PER_PHASE is reinforced as a hard cap.

The methodology-runner orchestrator contains a single switch (SKILL_LOADING_MODE) whose default is "skill-tool" (primary) and can be set to "inline" (fallback). Phase 0 validation decides which mode is the default for the release. Changing modes later is a single-line code change — both code paths exist in parallel in the implementation.

### Backward compatibility

Both flags are optional. Existing prompt-runner invocations without the flags behave identically to the current implementation. Interactive users and PR-NNN prompt files that do not go through methodology-runner are unaffected.

## 10. Generic role preservation

M-003 defines six generic roles: checklist-extractor, checklist-validator, artifact-generator, artifact-judge, traceability-validator, pipeline-orchestrator. This design does not add any new roles.

The Skill-Selector is a new agent, but it is not a new role in the M-003 sense. It does not produce or evaluate methodology artifacts; it produces a routing artifact that directs how the existing roles execute. It lives in methodology-runner's implementation (a Python module calling Claude once per phase), not in M-003. A future version of M-003 may document it for completeness, but that is a documentation change, not a role addition.

The key property this preserves: when someone reads M-003 to understand the methodology, they see six generic, technology-agnostic roles. When they want to understand *how a specific phase's generator acquires Python-specific knowledge*, they follow the skill-selection flow: skills-baselines.yaml → Skill-Selector → phase-NNN-skills.yaml → prelude → Claude call. The methodology text itself never mentions Python.

## 11. Distribution and packaging

### methodology-runner (Python CLI)

- Published to PyPI as methodology-runner.
- Installed via pipx install methodology-runner (preferred) or pip install methodology-runner in a virtualenv.
- Depends on the claude CLI being available on PATH (existing requirement, unchanged).
- Does NOT bundle any skills in the Python package. Skills are discovered from the filesystem at run time.

### methodology-runner-skills (Claude Code plugin)

- Published to the Claude Code plugin library.
- Installed via /plugin install methodology-runner-skills from any Claude Code session.
- Each skill is a full SKILL.md file with YAML frontmatter, body content, and optionally reference files under a skill-local folder.
- Installs to ~/.claude/.methodology/skills/** where methodology-runner's auto-discovery finds it.
- Independently versioned from methodology-runner — skills evolve faster than the tool itself.

Because every baseline skill declared in skills-baselines.yaml is validated at run start against the discovered catalog (failure mode 9 in section 12), the plugin MUST ship with a full SKILL.md file for every baseline skill referenced by the default baseline config. Missing one is a critical halt at run start.

#### V1 ships-with skill list (tech-agnostic core)

These skills are the minimum viable skill pack for the first release. They are all tech-agnostic or universal, which means they have the highest reusability and the lowest risk of becoming obsolete as new technologies are added. Each is listed as a concrete SKILL.md authoring work item in section 14.

1. **tdd** — test-driven development discipline; red/green/refactor; writing failing tests first; refactoring under a green bar.
2. **traceability-discipline** — universal traceability rules; every artifact element must trace to a prior-phase element; no orphans, no dangling references.
3. **requirements-extraction** — PH-000 baseline; extracting requirements from existing documents fidelity-first, without inference or improvement.
4. **requirements-quality-review** — PH-000 judge baseline; what makes a requirements inventory complete, atomic, and unambiguous.
5. **feature-specification** — PH-001 baseline; grouping requirements into features, writing acceptance criteria, identifying dependencies.
6. **feature-quality-review** — PH-001 judge baseline; evaluating features for testability and completeness.
7. **architecture-decomposition** — PH-002 baseline; splitting an enhancement into components, choosing boundaries, identifying integration points.
8. **tech-stack-catalog** — PH-002 baseline; high-level awareness of candidate technology stacks (Python backend, Node backend, TypeScript frontend, Rust, Go) without deep specialization in any one.
9. **architecture-review** — PH-002 judge baseline; evaluating stack manifests for coherence, feasibility, and alignment with feature requirements.
10. **solution-design-patterns** — PH-003 baseline; tech-agnostic design discipline (separation of concerns, interface design, dependency boundaries, error handling).
11. **solution-design-review** — PH-003 judge baseline; evaluating designs for modularity, testability, and clarity.
12. **contract-first-design** — PH-004 baseline; writing interface contracts before implementations; schema-first approaches.
13. **contract-review** — PH-004 judge baseline; evaluating contracts for completeness and consistency.
14. **simulation-framework** — PH-005 baseline; writing simulations that exercise contracts before implementations exist.
15. **simulation-review** — PH-005 judge baseline; evaluating simulations for coverage and realism.
16. **code-review-discipline** — PH-006 judge baseline; universal code review principles (readability, testability, no dead code, no speculative abstractions).
17. **cross-component-verification** — PH-007 baseline; verifying that independently-developed components integrate correctly at the contract boundaries.
18. **verification-review** — PH-007 judge baseline; evaluating cross-component verification completeness.

**V1 skill count: 18 tech-agnostic skills.** Each requires a substantive SKILL.md (estimated 100-300 lines of real content, not just a name and a two-line description).

#### Planned (post-v1) tech-specific skills

These are NOT required for v1 but are anticipated additions once the tech-agnostic core is working. They can be authored incrementally and published as minor releases of the skill pack. Until a tech-specific skill exists, its absence is expected to produce a reasonable warning path: the selector omits it, the generator proceeds with tech-agnostic knowledge only, and the judge flags any quality gap that would have been caught by the missing skill.

- python-backend-impl, fastapi-conventions, sqlalchemy-patterns, pytest-tdd, python-code-review, pytest-coverage-review (Python backend stack)
- typescript-frontend-impl, react-component-design, react-impl, accessibility-review, vitest-tdd, typescript-code-review (TypeScript/React frontend stack)
- nodejs-backend-impl, express-conventions, nestjs-conventions (Node backend stack)
- celery-patterns, bullmq-patterns (async job processing)
- postgresql-schema-design, sqlite-patterns (database)
- Additional language-specific packs (Rust, Go) as needed

Because the catalog is built by auto-discovery, adding a tech-specific skill post-v1 requires only writing the SKILL.md file and publishing a new skill-pack version. No change to methodology-runner code. No change to methodology documents. The selector picks it up on the next run.

### User-contributed skills

Users can add their own skills in two places:

- **Project-local** (workspace/.claude/skills/) — applies only to runs in that workspace. Good for project-specific conventions.
- **User-global** (~/.claude/skills/) — applies to all runs on that user's machine. Good for personal preferences.

Both are discovered automatically. No registration or catalog edit required.

### First-run experience

On first invocation of methodology-runner run, the orchestrator:

1. Walks discovery paths, builds the catalog.
2. If zero skills are discovered, prints a prominent actionable error:

   ```
   methodology-runner: no Claude Code skills discovered.
   
   The Skill-Selector agent cannot run without a skill catalog.
   
   Install the baseline skill pack with:
     /plugin install methodology-runner-skills
   
   Or place your own SKILL.md files under .claude/skills/ in this
   project, or under ~/.claude/skills/ for your user.
   ```
   and exits with a non-zero code. This is failure mode 7 in the error handling section.
3. Otherwise, proceeds normally.

## 12. Error handling and halt semantics

### Guiding principle

**No silent failures for essential quality elements.** Any failure in a mechanism that protects methodology quality halts the pipeline immediately with full state preservation. Transient failures in non-essential paths may be retried a bounded number of times before escalating to a halt.

### Failure mode matrix

| # | Failure mode | Location | Classification | Recovery |
|---|---|---|---|---|
| 1 | Selector Claude call returns non-zero exit or network error | Skill-Selector invocation | Retry up to N=2, then critical halt | Examine ~/.claude/logs and re-run |
| 2 | Selector output is not parseable YAML | Skill-Selector output validation | Critical halt | Edit phase-NNN-skills.yaml by hand, resume |
| 3 | Selector output missing required top-level fields (generator_skills, judge_skills, overall_rationale, phase_id, selector_run_at) | Skill-Selector output validation | Critical halt | Edit phase-NNN-skills.yaml, resume |
| 4 | Selector picks a skill ID not in the catalog | Skill-Selector output validation | Critical halt | Either install the missing skill or edit phase-NNN-skills.yaml to remove it, resume |
| 5 | Selector omits one or more baseline skills declared in skills-baselines.yaml for this phase | Skill-Selector output validation | Critical halt | Edit phase-NNN-skills.yaml to add the baseline, resume; or update skills-baselines.yaml if the baseline was wrong |
| 6 | Selector returns empty skill lists for a phase with no declared baseline | Skill-Selector output validation | Allowed, logged loudly | Legitimate outcome for tech-agnostic phases that genuinely need no specialized skills |
| 7 | Skill catalog is empty after walking all discovery paths | Catalog build at run start | Critical halt, before any phase runs | Install baseline plugin or place SKILL.md files in discovery paths |
| 8 | Cannot write phase-NNN-skills.yaml to workspace (disk full, permissions) | Selector output persistence | Critical halt | Fix disk/permissions, resume |
| 9 | Baseline skill declared in skills-baselines.yaml does not exist in the discovered catalog | Baseline validation at run start | Critical halt, before any phase runs | Either install the missing skill or remove it from skills-baselines.yaml |
| 10 | Two skills with the same ID discovered in multiple locations | Catalog build | Allowed, logged; higher priority wins | Visible in run log; correct the unwanted skill if it was a mistake |
| 11 | Cross-reference verification fails and retry budget exhausted (default N=2 retries) | Per-phase cross-ref retry loop | Critical halt | Examine cross-ref verdict, decide whether to hand-edit the phase's artifacts, re-run the phase with --rerun-selector to get a different skill set, or accept the failure and escalate per the phase's escalation policy |
| 12 | Cross-reference verification fails, retries remaining | Per-phase cross-ref retry loop | Recoverable — regenerate phase-NNN-prompts.md with cross-ref issues as feedback, re-invoke prompt-runner, skill manifest stays locked unless user passes --rerun-selector | Automatic (no human intervention) |
| 13 | Prior-artifact summarization Claude call fails (when an artifact exceeds ARTIFACT_FULL_CONTENT_THRESHOLD and a summary has not yet been cached) | Summarization subroutine inside Skill-Selector invocation | Retry up to N=2, then critical halt | Same recovery as failure mode 1; the uncached summary can also be written by hand if the Claude call is unreachable |
| 14 | Phase 0 validation (Skill tool availability in nested claude --print) has not been run before release | Implementation / release gate | Critical halt at methodology-runner startup if SKILL_LOADING_MODE is "skill-tool" but Phase 0 validation artifact is absent | Run the Phase 0 validation script (see section 14) and commit its output before re-running |

### State preservation on critical halt

Every critical halt leaves the workspace in a state where:

- The workspace is a git repository with at most one uncommitted change (the in-progress phase-NNN-skills.yaml if the halt was during selector output persistence).
- The run directory (under runs/) contains all logs, all intermediate artifacts, and a halt-reason.txt file describing the failure mode and the recovery steps.
- The methodology-runner state.json records the halted phase and the halt reason so that a resume command can pick up from the same point.

### Resume semantics

A user who examines a halted run and corrects the issue (by hand-editing phase-NNN-skills.yaml, installing a missing skill, or fixing disk problems) can resume with:

```
methodology-runner resume <workspace_dir>
```

On resume, the orchestrator:

1. Reads state.json to determine which phase halted.
2. If phase-NNN-skills.yaml exists and is valid, skips selector re-invocation and uses the existing file. This is the default behavior and preserves deterministic semantics.
3. If the user passes --rerun-selector, the orchestrator re-invokes the selector, overwriting phase-NNN-skills.yaml.
4. Continues from the phase's next unfinished step.

## 13. Data schemas summary

All schemas shown inline in the sections above. Centralized list for implementation reference:

- **stack-manifest.yaml** (section 5) — produced by PH-002, consumed by PH-003 onward and by the Skill-Selector.
- **phase-NNN-skills.yaml** (section 6) — produced by the Skill-Selector once per phase, consumed by the orchestrator to build preludes.
- **skills-baselines.yaml** (section 8) — authored by hand, checked into .methodology/docs/, read by the orchestrator at run start.
- **generator-prelude.txt / judge-prelude.txt** (section 9) — produced by the orchestrator per phase, consumed by prompt-runner via CLI flags.

Catalog entries (built in memory, not persisted) have shape: id, description, source_path, source_location.

## 14. Implementation impact summary

### Phase 0: validation (must run before any other implementation work)

A single experiment that determines which prelude design (primary or fallback) the implementation uses. Produces a committed artifact under runs/phase-0-validation/ with the raw claude --print output and a one-line verdict.

- **Validation script**: a standalone bash or Python script that (a) creates a temporary test skill test-marker-YYYYMMDD under ~/.claude/skills/ with a distinctive body string, (b) runs claude --print with a prompt instructing the agent to invoke Skill("test-marker-YYYYMMDD") and emit the distinctive string, (c) checks for the distinctive string in the output, (d) removes the temporary skill, (e) writes a validation-report.md with the result.
- **Outcome A** (distinctive string found): the primary prelude design is usable. SKILL_LOADING_MODE defaults to "skill-tool" in the implementation.
- **Outcome B** (distinctive string not found): the fallback prelude design must be used. SKILL_LOADING_MODE defaults to "inline" in the implementation.
- The validation-report.md is checked into the repo as a release gate. Failure mode 14 in section 12 halts methodology-runner startup if SKILL_LOADING_MODE is "skill-tool" and no validation report exists.

### New Python source files

- .methodology/docs/skills-baselines.yaml — baseline configuration (new data file).
- .methodology/src/cli/methodology_runner/constants.py — MAX_SKILLS_PER_PHASE, ARTIFACT_FULL_CONTENT_THRESHOLD, MAX_CATALOG_SIZE_WARNING, SKILL_LOADING_MODE, MAX_CROSS_REF_RETRIES.
- .methodology/src/cli/methodology_runner/skill_catalog.py — catalog discovery and validation (walks three discovery paths, parses SKILL.md frontmatter, returns list of SkillCatalogEntry).
- .methodology/src/cli/methodology_runner/skill_selector.py — Skill-Selector agent invocation (assembles selector prompt, invokes claude CLI, parses YAML output, validates, returns PhaseSkillManifest).
- .methodology/src/cli/methodology_runner/artifact_summarizer.py — on-demand summarization of large prior artifacts with caching.
- .methodology/src/cli/methodology_runner/prelude.py — prelude text construction from selector output (both primary and fallback modes).
- .methodology/src/cli/methodology_runner/phase_0_validation.py — the Phase 0 validation script mentioned above.

### New test files

- .methodology/tests/cli/methodology_runner/test_skill_catalog.py — discovery walking, frontmatter parsing, duplicate resolution, validation errors.
- .methodology/tests/cli/methodology_runner/test_skill_selector.py — selector invocation (mocked claude client), output parsing, output validation, failure modes 1-5.
- .methodology/tests/cli/methodology_runner/test_artifact_summarizer.py — size threshold, summary caching, REQUEST_FULL_ARTIFACT escape hatch.
- .methodology/tests/cli/methodology_runner/test_prelude.py — prelude construction in both modes, skill count cap.
- .methodology/tests/cli/methodology_runner/test_cross_ref_retry.py — retry loop, max retries, locked skill manifest across retries.

### Modified source files

- .methodology/docs/M-002-phase-definitions.md — insert PH-002 Architecture phase definition, renumber downstream phases PH-002..PH-006 to PH-003..PH-007, update the dependency graph, update all cross-references.
- .methodology/docs/design/components/CD-002-methodology-runner.md — add skill-selection flow to the design, document the new per-phase loop including cross-ref retry, document the two prelude modes.
- .methodology/src/cli/methodology_runner/orchestrator.py — integrate catalog discovery, selector invocation, prelude construction, cross-reference retry loop, and the per-phase state transitions they imply.
- .methodology/src/cli/methodology_runner/phases.py — update phase enumeration with new PH-002 and renumbered successors; no longer hardcode phase names.
- .methodology/src/cli/methodology_runner/models.py — add SkillCatalogEntry, PhaseSkillManifest, BaselineSkillConfig, PreludeSpec dataclasses.
- .methodology/src/cli/methodology_runner/cli.py — add --rerun-selector flag to the resume command.
- .methodology/src/cli/methodology_runner/prompt_generator.py — update to consume the phase skill manifest when building the meta-prompt.
- .prompt-runner/src/cli/prompt_runner/__main__.py — add --generator-prelude and --judge-prelude flags to the run subcommand (verified in _build_parser() at line 128).
- .prompt-runner/src/cli/prompt_runner/runner.py — accept prelude file paths, read once at startup, prepend content to generator and judge messages.
- .prompt-runner/tests/cli/prompt_runner/ — extend existing tests for the prelude feature (empty prelude backward compat, both preludes set, prelude content preserved across revise loop).
- .methodology/tests/cli/methodology_runner/test_orchestrator.py — update for new per-phase flow including retry loop.
- .methodology/tests/cli/methodology_runner/test_cli.py — update for --rerun-selector flag.

### SKILL.md authoring (companion plugin methodology-runner-skills)

Every V1 baseline skill from section 11 requires a substantive SKILL.md file. Each skill is a work item. These are not trivial — each is a real knowledge artifact with conventions, examples, and anti-patterns. Estimated size: 100-300 lines of real content per skill.

- methodology-runner-skills/skills/tdd/SKILL.md
- methodology-runner-skills/skills/traceability-discipline/SKILL.md
- methodology-runner-skills/skills/requirements-extraction/SKILL.md
- methodology-runner-skills/skills/requirements-quality-review/SKILL.md
- methodology-runner-skills/skills/feature-specification/SKILL.md
- methodology-runner-skills/skills/feature-quality-review/SKILL.md
- methodology-runner-skills/skills/architecture-decomposition/SKILL.md
- methodology-runner-skills/skills/tech-stack-catalog/SKILL.md
- methodology-runner-skills/skills/architecture-review/SKILL.md
- methodology-runner-skills/skills/solution-design-patterns/SKILL.md
- methodology-runner-skills/skills/solution-design-review/SKILL.md
- methodology-runner-skills/skills/contract-first-design/SKILL.md
- methodology-runner-skills/skills/contract-review/SKILL.md
- methodology-runner-skills/skills/simulation-framework/SKILL.md
- methodology-runner-skills/skills/simulation-review/SKILL.md
- methodology-runner-skills/skills/code-review-discipline/SKILL.md
- methodology-runner-skills/skills/cross-component-verification/SKILL.md
- methodology-runner-skills/skills/verification-review/SKILL.md

**Plus the plugin manifest:**

- methodology-runner-skills/.claude-plugin/plugin.json — Claude Code plugin manifest declaring the skill pack.
- methodology-runner-skills/README.md — plugin-level documentation.

**Total v1 authoring work: 18 SKILL.md files + 2 plugin metadata files = 20 new documents in the companion plugin.** This is the largest single chunk of work in the implementation and should be planned accordingly. These files may be authored in parallel with the Python code changes above, since they do not depend on each other.

### Deleted files

None. The existing phase enumeration is replaced, not extended, but the files are modified in place. Existing workspace state.json files produced by prior runs cannot be resumed after the renumbering (old PH-002 is now PH-003, etc.) — since the project is greenfield with no users beyond the author, these are discarded rather than migrated.

## 15. Deferred / out of scope

- **Mid-phase skill re-selection** — the selector runs once per phase. If a mid-phase surprise reveals a missing skill, the user notices it at cross-reference verification time and the fix is to edit phase-NNN-skills.yaml by hand and resume, or to retry the phase. A future spec may revisit automatic re-selection if this proves common.
- **Per-prompt skill selection** — explicitly rejected. The selector's cost and non-determinism would multiply linearly with the number of prompts per phase.
- **Parallel per-component phase execution** — PH-006 implementing multiple components in parallel (or PH-005 simulating them in parallel) is a potential optimization but out of scope. The orchestrator currently processes phases sequentially; introducing parallelism is a separate design.
- **Dynamic skill installation** — if a required skill is not on disk, methodology-runner halts. It does not attempt to pip install, plugin install, or download any skill at run time.
- **Skill versioning and dependency resolution** — the catalog treats skills as flat IDs with no version or dependency metadata. If two skills conflict (for example, react-impl and solid-impl both declaring themselves as "the" frontend skill), the selector is expected to pick one based on the stack manifest. A version/dependency model is out of scope.
- **Interactive mode for Skill-Selector** — the selector always runs as a non-interactive Claude call. It does not prompt the human for clarification even when the prior artifacts are ambiguous; instead, it makes a best-effort choice and documents its reasoning in the rationale field.
- **Skill marketplace or registry beyond the Claude Code plugin library** — using the existing plugin library is sufficient. No custom registry.

## 16. Open questions for reviewer

None at the time of writing. The brainstorming session resolved the key decision points: Option A for selector granularity (once per phase, locked), baseline skills as configuration (not hardcoded), Option 1 for distribution (Python package + companion plugin with auto-discovery), and full halt-on-failure for all essential mechanisms.

If the reviewer identifies additional questions during review, add them here as numbered items and the author will revise before proceeding to the implementation plan step.

## 17. Next step

On approval of this spec, the next step is to invoke the superpowers:writing-plans skill to produce an implementation plan derived from section 14 (Implementation impact summary). The implementation plan will decompose the changes into ordered, independently verifiable steps suitable for execution via subagent-driven development or in the current session.
