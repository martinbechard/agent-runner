# Project Taxonomy

> This document is maintained by the `project-organiser` sub-agent.
> It defines where every kind of artifact lives in this project.
> The agent reads this on every invocation and may append to it.
> Humans may also read and edit it directly — keep the schema consistent.

## Conventions

- **ID prefixes:** FR (functional requirement), TR (technical requirement), HLD (high-level design), CD (component design)
- **ID format:** `<PREFIX>-<NNN>-<kebab-slug>.md` where NNN is 3-digit zero-padded (e.g. `FR-001-...`, `HLD-042-...`)
- **Filename casing:**
  - Python modules: `snake_case.py`
  - TypeScript modules (server, shared utilities): `kebab-case.ts`
  - React components: `PascalCase.tsx`
  - React non-component modules (hooks, utils): `kebab-case.ts`
  - Test files: `test_<module>.py` (Python), `<module>.test.ts(x)` (TS / React)
- **Tests mirror source:** a test for `src/<area>/path/to/file.ext` lives at `tests/<area>/path/to/<test-file>` using the conventions above.

## Categories

### docs/requirements/functional/
- **Purpose:** What the system must do, from a user's point of view.
- **Signals:** "the system shall", "the user can", "given/when/then", use cases, user stories, UI behaviour description, observable outputs.
- **Filename pattern:** `FR-NNN-<slug>.md`
- **Example:** `FR-001-run-agent-from-yaml.md`

### docs/requirements/technical/
- **Purpose:** Constraints, non-functional requirements, technology choices, performance targets, security and compliance rules.
- **Signals:** "must support", "latency under", "runs on Python 3.12", "encrypted at rest", deployment constraint, dependency choice, throughput target.
- **Filename pattern:** `TR-NNN-<slug>.md`
- **Example:** `TR-001-python-version.md`

### docs/design/high-level/
- **Purpose:** System-wide decomposition — the components that make up the system and how they interact.
- **Signals:** component diagram, sequence diagram, "the CLI talks to the server via", system overview, end-to-end data flow, three-tier description.
- **Filename pattern:** `HLD-NNN-<slug>.md`
- **Example:** `HLD-001-system-overview.md`

### docs/design/components/
- **Purpose:** Detailed design of a single component — its internal data model, exposed API, and invariants.
- **Signals:** "this module exposes", single-component internals, "the X component", scoped data model, internal class/function decomposition.
- **Filename pattern:** `CD-NNN-<slug>.md`
- **Example:** `CD-001-cli-runner.md`

### src/cli/
- **Purpose:** Python command-line process source code.
- **Signals:** `argparse`, `click`, `typer`, `if __name__ == "__main__"`, Python `def main()`, console_scripts entry point.
- **Filename pattern:** `snake_case.py`
- **Tests location:** `tests/cli/` — mirror path, `test_<module>.py`.

### scripts/
- **Purpose:** Repository-local operational scripts and workflow helpers that are run directly from the checkout rather than installed as product CLI entry points. These scripts orchestrate development tasks, reports, or local workflow automation for this repository.
- **Signals:** shebang-based Python or shell helper, invoked as `python scripts/...` or `./scripts/...`, repository-maintenance utility, local workflow launcher, report generator, one-off operational helper that belongs to this repo but is not a shipped `src/cli/` command.
- **Filename pattern:** `snake_case.py` for Python, `kebab-case.sh` for shell.
- **Tests location:** `tests/cli/` — `test_<script_basename>.py` for Python helpers.

### src/server/
- **Purpose:** TypeScript web server and API route handlers.
- **Signals:** Express / Fastify / Hono routes, HTTP handler functions, `req` / `res` types, `app.get` / `app.post`, API middleware, request validation schemas.
- **Filename pattern:** `kebab-case.ts`
- **Tests location:** `tests/server/` — mirror path, `<module>.test.ts`.

### src/web/
- **Purpose:** React frontend — components, pages, hooks, client-side state.
- **Signals:** JSX / TSX syntax, React hooks (`useState`, `useEffect`, `useMemo`), component exports, `export default function`, page-level routing.
- **Filename pattern:** `PascalCase.tsx` for components and pages, `kebab-case.ts` for non-component modules (hooks, utilities).
- **Tests location:** `tests/web/` — mirror path, `<module>.test.tsx`.

### src/shared/
- **Purpose:** TypeScript types, interfaces, and constants that are consumed by both the server and the web frontend and must not live in either alone.
- **Signals:** type or interface shared across `src/server/` and `src/web/`, API contract types, shared enums, cross-boundary DTOs, "both the server and the frontend need to agree on".
- **Filename pattern:** `kebab-case.ts`
- **Tests location:** `tests/shared/` — mirror path, `<module>.test.ts`.

### docs/plans/
- **Purpose:** Transient, TDD-style implementation plans — sequential task groups that decompose a finished design into bite-sized, test-first steps. Not a design document (no decisions), not a requirements document, and not acceptance criteria. Historical value once implementation is complete.
- **Signals:** "task group", "write failing test", "run pytest", "step-N deliverable", references a companion `CD-NNN` or `HLD-NNN` doc, implementation order section, TDD cadence (failing test → minimal implementation → commit).
- **Filename pattern:** `PLAN-NNN-<slug>.md` where NNN is 3-digit zero-padded and slug identifies the component or feature being implemented.
- **Example:** `docs/plans/retired/PLAN-001-prompt-runner.md`

### docs/reviews/
- **Purpose:** Structured review outputs such as completed review checklists, findings documents, and other review artifacts derived from an explicit review process. These are not design authorities, not implementation plans, and not acceptance-criteria specs; they record the result of reviewing another artifact.
- **Signals:** "review checklist", "review findings", "structured review", "issues found", "coverage check", "internal logic review", paired checklist/findings documents derived from a design, plan, prompt, or other structured artifact.
- **Filename pattern:** `RVW-NNN-<slug>.md` where NNN is 3-digit zero-padded and slug identifies the reviewed artifact plus the review output type.
- **Example:** `RVW-001-active-design-stack-checklist.md`

### docs/testing/
- **Purpose:** Implementation acceptance criteria and test plans — concrete, runnable checks that verify finished code matches a design spec. Not the design itself and not the test code; the layer in between.
- **Signals:** "AC-NN", "verification method", "run pytest and assert", "grep src/ for", acceptance criteria grouped by deliverable, traces back to a requirement or design section, companion to a `CD-NNN` or `HLD-NNN` doc.
- **Filename pattern:** `AC-NNN-<slug>.md` where NNN is 3-digit zero-padded and slug identifies the component or feature.
- **Example:** `AC-001-prompt-runner.md`

### tests/fixtures/
- **Purpose:** Static input files used by interactive or automated methodology-runner sessions during skill authoring and verification. These are not unit-test source files and do not mirror any `src/` module; they are realistic-but-minimal data files consumed as `--input` or equivalent arguments to CLI tools under development.
- **Signals:** "test fixture", "used by methodology-runner run", "skill-authoring session", "tiny requirements", "sample input", not a `def test_` file, not a `describe(` block, referenced from a `docs/prompts/PR-NNN-*.md` file as the concrete input to a runner session.
- **Filename pattern:** `<topic-slug>.<ext>` in kebab-case, where ext matches the fixture format (e.g. `tiny-requirements.md`, `sample-config.yaml`).
- **Tests location:** n/a — these files are themselves fixtures, not code under test.

### tests/cli/
- **Purpose:** Python unit tests mirroring `src/cli/`.
- **Signals:** `def test_`, `pytest`, fixtures importing from `src/cli/`.
- **Filename pattern:** `test_<module>.py`
- **Mirrors:** `src/cli/`

### tests/server/
- **Purpose:** TypeScript unit tests mirroring `src/server/`.
- **Signals:** `describe(`, `it(`, `test(`, imports from `src/server/`, supertest / fetch mocks.
- **Filename pattern:** `<module>.test.ts`
- **Mirrors:** `src/server/`

### tests/web/
- **Purpose:** React component / hook tests mirroring `src/web/`.
- **Signals:** React Testing Library, `render(`, `screen.getBy`, imports from `src/web/`, hook test wrappers.
- **Filename pattern:** `<module>.test.tsx`
- **Mirrors:** `src/web/`

### docs/methodology/
- **Purpose:** Canonical reference specifications for the AI-driven software development methodology — the standing corpus that AI pipeline agents (generators, judges, orchestrators) consult when executing the methodology on real projects. These documents define phases, agent roles, data models, and control flow for the methodology itself, not for any specific codebase that uses it. They are produced by prompt-runner runs and evolve as the methodology evolves.
- **Signals:** "AI-Driven Development Pipeline", "Phase Processing Unit", "agent role", "checklist extractor", "judge", "orchestrator", "simulation framework", "traceability infrastructure", "phase sequencing", YAML spec of pipeline phases or agent system prompts, audience is AI agents not human developers of a specific tool, not a design of agent-runner components.
- **Filename pattern:** `M-NNN-<slug>.md` where NNN is 3-digit zero-padded and slug identifies the methodology element (e.g. `phase-definitions`, `agent-role-specifications`, `orchestration`).
- **Example:** `M-001-phase-processing-unit-schema.md`

### docs/prompts/
- **Purpose:** Hand-authored prompt-runner input files — sequences of LLM generation prompts paired with validator prompts, consumed by the prompt-runner CLI tool to produce design docs, acceptance criteria, plans, or source code. These files drive downstream artifact generation but are not themselves design documents, requirements, acceptance criteria, or plans.
- **Signals:** `## Prompt N:` section headings, paired fenced code blocks (generation prompt + validation prompt), "max_iterations", "sent to Claude", "judge", intended to be passed as `--input` to the prompt-runner CLI, subject line references a tool or feature being built via the runner.
- **Filename pattern:** `PR-NNN-<slug>.md` where NNN is 3-digit zero-padded and slug identifies the tool or feature the prompts will produce.
- **Example:** `PR-001-methodology-runner.md`

### .prompt-runner/runs/<run-id>/
- **Purpose:** Generated, run-scoped prompt-runner artifacts produced during one execution of a prompt sequence. This directory holds per-run YAML or markdown outputs such as inventories, traceability maps, correction files, checklists, and similar intermediate or final artifacts tied to a single run ID.
- **Signals:** `.prompt-runner/runs/`, timestamped run directory, "requirements-inventory", "traceability", "checklist", "corrections", phase output consumed by a later step in the same run, generated artifact that should remain attached to one concrete prompt-runner execution rather than promoted into `docs/`.
- **Filename pattern:** descriptive fixed-name artifacts in kebab-case with `.yaml` or `.md` extensions as required by the run protocol (for example `requirements-inventory.yaml`, `requirements-inventory-traceability.yaml`, `requirements-inventory-checklist.yaml`).
- **Tests location:** n/a — run artifacts are generated outputs, not source files under direct test.

### docs/superpowers/plans/
- **Purpose:** TDD-style implementation plans produced by the `superpowers:writing-plans` skill. Each plan is derived from a companion spec in `docs/superpowers/specs/` and decomposes a proposed enhancement into ordered, bite-sized, test-first tasks with exact file paths, code blocks, and commands. These are not design documents, not requirements, not acceptance-criteria files, and not generic `docs/plans/` entries — they live alongside their source spec in the superpowers layer.
- **Signals:** output of `superpowers:writing-plans` skill, "derived from spec at docs/superpowers/specs/", TDD cadence (failing test → minimal implementation → commit), "task group", "write failing test", "run pytest", references a dated spec file, dated filename with a topic slug, ordered implementation tasks.
- **Filename pattern:** `YYYY-MM-DD-<topic-slug>.md` where YYYY-MM-DD is the session date and topic-slug is a kebab-case description of the feature being implemented.
- **Example:** `2026-04-07-project-organiser-agent.md`

### docs/superpowers/specs/
- **Purpose:** Design specifications produced by brainstorming or ideation sessions (e.g. the `superpowers:brainstorming` skill). These are pre-implementation specs that describe a proposed enhancement, mechanism, or distribution model and are intended for human review before an implementation plan is derived from them. They are not design docs in the `docs/design/` sense (they have not yet been approved into the component design canon), not requirements, not plans, and not prompt files.
- **Signals:** output of a `superpowers:brainstorming` skill run, "design spec", "brainstorming session", describes a proposed feature or enhancement that cuts across multiple existing components, "reviewed by the human before implementation", "input to a subsequent writing-plans step", dated filename with a topic slug, not yet assigned a CD-NNN or HLD-NNN number.
- **Filename pattern:** `YYYY-MM-DD-<topic-slug>-design.md` where YYYY-MM-DD is the session date and topic-slug is a kebab-case description of the subject.
- **Example:** `2026-04-07-project-organiser-agent-design.md`

### plugins/<plugin-name>/.claude-plugin/
- **Purpose:** Claude Code plugin manifest directory. Contains the `plugin.json` file that declares the plugin's identity (name, version, description, author) and any other Claude Code plugin metadata files required by the plugin convention. This is the machine-readable registration layer of a plugin package.
- **Signals:** `plugin.json`, `name` / `version` / `description` / `author` fields, `.claude-plugin` directory name, "plugin manifest", "Claude Code plugin", "skill pack manifest", fixed filename required by the Claude Code plugin runtime.
- **Filename pattern:** `plugin.json` (fixed name); any additional Claude Code plugin metadata files use the exact names the runtime expects.
- **Tests location:** n/a — manifest files are configuration, not runnable source code.

### plugins/<plugin-name>/skills/<skill-name>/
- **Purpose:** Individual skill definitions inside a Claude Code plugin package. Each skill is a named subdirectory containing a `SKILL.md` file that specifies the skill's purpose, universal rules, inputs, outputs, and any phase-specific guidance consumed by the methodology-runner when executing that skill. The filename is fixed by the methodology-runner plugin convention.
- **Signals:** "skill definition", "universal rules", "traceability rules", "phase must follow", "every artifact element traces", "methodology phase", SKILL.md, "methodology-runner skill", "skill pack entry", fixed path derived from the plugin name and the skill's identity, audience is AI pipeline agents.
- **Filename pattern:** `SKILL.md` (fixed name required by the methodology-runner plugin convention).
- **Tests location:** n/a — skill definition files are declarative specifications, not runnable source code.

### plugins/<plugin-name>/skills/<skill-name>/agents/
- **Purpose:** Product-facing metadata for an individual skill, such as `agents/openai.yaml`, used by Codex or related tooling to render skill lists, chips, and invocation defaults. This complements the skill's `SKILL.md` but is not itself the skill definition.
- **Signals:** `agents/openai.yaml`, "display_name", "short_description", "default_prompt", UI skill metadata, product-facing skill manifest, metadata generated from a skill definition.
- **Filename pattern:** fixed product-specific filenames inside `agents/`, currently `openai.yaml`.
- **Tests location:** n/a — agent metadata files are declarative configuration, not runnable source code.

### plugins/<plugin-name>/docs/
- **Purpose:** Supplementary reference documents scoped to a single plugin — authoring guides, lessons-learned files, pattern catalogues, and any other human- or AI-readable guidance that belongs to the plugin but is not a skill definition, a plugin manifest, or the plugin README. Consumed by subsequent skill-authoring sessions or by AI pipeline agents writing new skills for that plugin.
- **Signals:** "lessons learned", "authoring guide", "patterns that work well for AI", "skill authoring patterns", "adversarial testing results", "do not repeat these experiments", "best practices for skill writing", scoped to one plugin, not a SKILL.md, not a README, not a plugin.json, not a docs/methodology/ spec.
- **Filename pattern:** `kebab-case.md` — descriptive slug matching the document's subject (e.g. `skill-authoring-lessons-learned.md`, `ai-consumption-patterns.md`).
- **Tests location:** n/a — these are reference documents, not runnable source code.

### plugins/<plugin-name>/
- **Purpose:** Self-contained Claude Code sub-agent plugin packages. Each subdirectory is a single named plugin that bundles a README, a companion spec or prompt file, and any supporting assets the plugin needs. The README is the human-facing entry point; the spec or prompt file is the machine-facing definition consumed by the methodology-runner or prompt-runner.
- **Signals:** "Claude Code plugin", "skill pack", "methodology-runner-skills", "sub-agent plugin", `plugins/` directory, companion spec reference, list of skills with one-line roles, "point at a companion spec", fixed plugin directory name determined by the plugin's identity.
- **Filename pattern:** `README.md` for the human-readable description; companion spec follows the `docs/prompts/` or `docs/methodology/` naming convention for the spec file itself.
- **Tests location:** n/a — plugin directories are documentation and configuration, not runnable source code.

### work/
- **Purpose:** Temporary human- or agent-created working directories used for short-lived scratch artifacts, intermediate prompt drafts, and exploratory files that are intentionally not canonical reference material. This is the staging area for transient work before artifacts are either promoted into a canonical home or discarded.
- **Signals:** "temporary working folder", "scratch space", "draft prompts", "intermediate artifacts", "throwaway workspace", "not reference material", "working area for a specific run or experiment".
- **Filename pattern:** top-level subdirectory per task or experiment using `kebab-case/`; files inside should use the naming convention appropriate to their eventual artifact type when possible.
- **Tests location:** n/a — temporary working directories are not canonical test locations.

### (project root)
- **Purpose:** Tooling configuration files and agent instruction files that must live at the repository root by ecosystem convention.
- **Signals:** `package.json`, `tsconfig.json`, `pyproject.toml`, `.gitignore`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `.editorconfig`, `.prettierrc`, lockfiles.
- **Filename pattern:** tool-specific, fixed names — use the exact filename the tooling expects.
- **Tests location:** n/a

## Change log

<!-- The agent appends one line per taxonomy extension here, newest at top. -->
- 2026-04-15 — plugins/<plugin-name>/skills/<skill-name>/agents/ added — skill UI metadata such as `agents/openai.yaml` is distinct from the skill definition and needs its own category under each skill folder.
- 2026-04-14 — .prompt-runner/runs/<run-id>/ added — run-scoped generated prompt-runner artifacts need a canonical home distinct from reference docs and temporary scratch work.
- 2026-04-14 — work/ added — temporary working directories and scratch artifacts should not live under docs/ because docs/ is reserved for reference material.
- 2026-04-14 — docs/reviews/ added — structured review outputs are not designs or plans and need a dedicated review-artifacts layer.
- 2026-04-13 — scripts/ added — repository-local operational scripts and workflow helpers already exist in the repo and need an explicit taxonomy home distinct from shipped src/cli commands.
- 2026-04-09 — plugins/<plugin-name>/docs/ added — plugin-level supplementary reference documents (authoring guides, lessons-learned, pattern catalogues) are not SKILL.md files, not plugin manifests, and not plugin READMEs; they need a dedicated docs/ layer scoped to the plugin.
- 2026-04-09 — plugins/<plugin-name>/skills/<skill-name>/ added — individual skill definition files (SKILL.md) inside a plugin's skills/ subdirectory are a distinct layer from the plugin root README and the plugin manifest; they need their own taxonomy entry covering the fixed SKILL.md filename convention.
- 2026-04-09 — plugins/<plugin-name>/.claude-plugin/ added — Claude Code plugin manifest directory (plugin.json with name/version/description/author) is a distinct machine-readable registration layer inside a plugin package and needs its own taxonomy entry separate from the human-readable plugin root.
- 2026-04-09 — plugins/<plugin-name>/ added — Claude Code plugin packages (README + companion spec) have no home in docs/, src/, or tests/; a dedicated top-level plugins layer is needed.
- 2026-04-09 — tests/fixtures/ added — static input fixtures for methodology-runner skill-authoring sessions are not unit-test source files and do not mirror any src/ module; they need a dedicated fixtures layer inside tests/.
- 2026-04-09 — docs/superpowers/plans/ added — TDD implementation plans produced by the superpowers:writing-plans skill are derived from superpowers/specs/ companions and belong in the same superpowers layer, distinct from docs/plans/ which holds generic component plans.
- 2026-04-09 — docs/superpowers/specs/ added — pre-implementation design specs produced by brainstorming skill runs are not yet approved into the component design canon and need a dedicated staging layer distinct from docs/design/, docs/requirements/, docs/plans/, and docs/prompts/.
- 2026-04-08 — docs/methodology/ added — AI-driven development methodology reference corpus (phase specs, agent role prompts, traceability model, simulation framework, orchestration) is not a design of agent-runner components, not a requirement, not a plan, and not a prompt file; a dedicated methodology corpus layer is needed.
- 2026-04-08 — docs/prompts/ added — prompt-runner input files (hand-authored LLM prompt sequences with paired validators) are inputs to a tool, not design docs, requirements, plans, or test code; a dedicated prompt-files layer is needed.
- 2026-04-08 — docs/plans/ added — TDD implementation plans (sequential task groups decomposing a design into test-first steps) are transient work documents that are neither design, requirements, nor acceptance criteria; a dedicated plan layer is needed.
- 2026-04-08 — docs/testing/ added — implementation acceptance criteria (runnable checks that the finished code matches a design) have no home in docs/design/, docs/requirements/, or tests/; a dedicated verification-spec layer is needed.
- 2026-04-08 — src/shared/ added — TypeScript types shared between server and web frontend have no home in either src/server/ or src/web/; a neutral shared layer is needed.
<!-- Format: YYYY-MM-DD — <category added> — <one-line reason> -->
