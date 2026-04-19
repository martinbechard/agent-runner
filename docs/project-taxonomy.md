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

## Top-Level Folder Principles

- **Repo-level files** live in the repository root and shared top-level areas
  such as `docs/`, `scripts/`, and `tests/` when they describe or exercise the
  repository itself rather than the built project.
- **Project files** live under `project/` when they are the actual promoted
  implementation, tests, docs, or support scripts produced by the tools.
- **Prompt-runner files** live under `tools/prompt-runner/`.
- **Methodology files** live under `tools/methodology-runner/`.
- **Sample files** live under `sample/`.
- **Rule:** When a file exists only to support prompt-runner execution, keep it
  under `tools/prompt-runner/` rather than mixing it with project files.
- **Rule:** When a file exists only to support methodology-runner execution,
  keep it under `tools/methodology-runner/` rather than mixing it with project
  files.
- **Rule:** When a file is a curated example bundle or runnable repository
  sample, keep it under `sample/` so the request, fixtures, and helper assets
  stay together.
- **Rule:** Project outputs produced by a phase stay under `project/` once they
  are promoted into the canonical implementation tree, unless the file is
  runner-owned state or tooling support data.

## Categories

### project/README.md
- **Purpose:** Human-facing guide for the canonical implementation tree that the
  methodology eventually produces or promotes into.
- **Signals:** promotion target overview, "this is where the real built project
  lives", implementation-tree orientation, explanation of `project/src`,
  `project/tests`, `project/docs`, or `project/scripts`.
- **Filename pattern:** `README.md`.
- **Example:** `project/README.md`

### project/src/
- **Purpose:** Canonical source tree for the built project. Use this path when
  the file is real implementation code rather than tool code, sample material,
  or repo-level support code.
- **Signals:** application modules, product runtime code, implementation output
  promoted from methodology runs, code imported by the built project itself.
- **Filename pattern:** use the language-appropriate conventions for the
  project being built.
- **Tests location:** `project/tests/` — mirror path when the project language
  supports mirrored tests.

### project/tests/
- **Purpose:** Canonical test tree for the built project. Use this path when
  the file verifies the promoted implementation rather than the tools
  themselves.
- **Signals:** project unit tests, integration tests for promoted code, tests
  that run against `project/src/`, delivered verification code for the built
  system.
- **Filename pattern:** use the language-appropriate project test convention.
- **Mirrors:** `project/src/`

### project/docs/
- **Purpose:** Canonical project-specific documentation for the promoted
  implementation, distinct from repo-level documentation in the root `docs/`
  tree.
- **Signals:** built-project README companions, app usage docs, product-facing
  documentation, operational docs for the promoted project rather than for the
  tools or the repository itself.
- **Filename pattern:** descriptive markdown or other doc filenames matching the
  built project's conventions.

### project/scripts/
- **Purpose:** Canonical support scripts for the promoted project. Use this path
  when a script exists to run, build, verify, or maintain the built project
  rather than the repository tooling.
- **Signals:** project-local helper scripts, run/build/test wrappers for the
  promoted implementation, app maintenance scripts.
- **Filename pattern:** `snake_case.py` for Python or `kebab-case.sh` for shell,
  following the built project's language conventions.

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
- **Filename pattern:** `CD-NNN-<slug>.md` for canonical markdown component designs; `CD-NNN-<slug>.yaml` for explicit YAML structured-design companions when the task specifically calls for the same component design in YAML form.
- **Example:** `CD-001-cli-runner.md`

### tools/prompt-runner/
- **Purpose:** Package root for the prompt-runner tool itself. Use this path for tool-level packaging files such as `pyproject.toml`, the tool README, and other root files that define how prompt-runner is installed and presented as a product.
- **Signals:** prompt-runner package metadata, prompt-runner distribution root, tool-level install instructions, console entry point definition, prompt-runner product README.
- **Filename pattern:** fixed tool-root filenames such as `pyproject.toml` and `README.md`.
- **Example:** `tools/prompt-runner/pyproject.toml`

### tools/prompt-runner/docs/design/components/
- **Purpose:** Canonical design documents for prompt-runner itself. Use this mirrored design path when a component design belongs to prompt-runner rather than to the main project tree or to methodology-runner.
- **Signals:** prompt-runner parser model, prompt-runner runtime contract, prompt-runner agent model, prompt-runner CLI execution design, design authority for prompt-runner internals rather than for the main project or the methodology layer.
- **Filename pattern:** preserve the existing component-design filename such as `CD-NNN-<slug>.md`.
- **Example:** `tools/prompt-runner/docs/design/components/CD-001-prompt-runner.md`

### tools/prompt-runner/README.md
- **Purpose:** Human- and agent-facing guide for prompt-runner itself. Use this path for prompt-runner-specific usage, authoring, and file-format guidance that belongs to prompt-runner rather than to the main project or to methodology-runner.
- **Signals:** "prompt-runner input format", authoring guide for prompt modules, prompt-runner usage notes, prompt-runner-specific examples, references for prompt-runner users.
- **Filename pattern:** `README.md`.
- **Example:** `tools/prompt-runner/README.md`

### tools/prompt-runner/docs/testing/
- **Purpose:** Acceptance criteria and verification specs for prompt-runner itself.
- **Signals:** prompt-runner implementation acceptance criteria, verification targets for prompt-runner behavior, checks tied to prompt-runner design docs.
- **Filename pattern:** preserve the existing acceptance-criteria filename such as `AC-NNN-<slug>.md`.
- **Example:** `tools/prompt-runner/docs/testing/AC-001-prompt-runner.md`

### tools/prompt-runner/docs/plans/
- **Purpose:** Prompt-runner-specific implementation plans and historical planning artifacts. Use this mirrored plan path when the plan belongs to prompt-runner rather than to the main project or to methodology-runner.
- **Signals:** prompt-runner implementation plan, prompt-runner historical plan, prompt-runner-specific task breakdown, retired prompt-runner plan.
- **Filename pattern:** preserve the existing plan filename under the matching subpath, such as `PLAN-NNN-<slug>.md` or dated retired plan names.
- **Example:** `tools/prompt-runner/docs/plans/retired/PLAN-001-prompt-runner.md`

### tools/prompt-runner/src/
- **Purpose:** Prompt-runner Python source code. Use this mirrored source path when the code belongs to prompt-runner rather than to the main project tree or to methodology-runner.
- **Signals:** prompt-runner CLI entry point, parser, runner loop, agent clients, prompt-runner config, prompt-runner package code imported as `prompt_runner`.
- **Filename pattern:** `snake_case.py` for modules and fixed Python package files such as `__init__.py` and `__main__.py`.
- **Tests location:** `tools/prompt-runner/tests/` — mirror path, `test_<module>.py`.
- **Example:** `tools/prompt-runner/src/prompt_runner/runner.py`

### tools/prompt-runner/tests/
- **Purpose:** Prompt-runner Python tests and fixtures. Use this mirrored test path when the tests exercise prompt-runner code rather than the main project tree or methodology-runner.
- **Signals:** prompt-runner parser tests, runner tests, prompt-runner CLI tests, fixtures imported only by prompt-runner tests.
- **Filename pattern:** `test_<module>.py`; fixtures keep descriptive filenames in subfolders such as `fixtures/`.
- **Mirrors:** `tools/prompt-runner/src/`

### tools/methodology-runner/
- **Purpose:** Package root for the methodology-runner tool itself. Use this path for tool-level packaging files such as `pyproject.toml`, the tool README, and other root files that define how methodology-runner is installed and presented as a product.
- **Signals:** methodology-runner package metadata, methodology-runner distribution root, tool-level install instructions, console entry point definition, methodology-runner product README.
- **Filename pattern:** fixed tool-root filenames such as `pyproject.toml` and `README.md`.
- **Example:** `tools/methodology-runner/pyproject.toml`

### tools/methodology-runner/docs/design/high-level/
- **Purpose:** High-level design documents for the methodology layer itself. Use this mirrored design path when the document describes methodology-wide structure, workflow, or execution architecture rather than the main project or prompt-runner.
- **Signals:** methodology-wide architecture, methodology workflow, phase-to-phase flow, optimization workflow, execution architecture for the methodology layer.
- **Filename pattern:** preserve the existing high-level-design filename such as `HLD-NNN-<slug>.md`.
- **Example:** `tools/methodology-runner/docs/design/high-level/HLD-002-methodology-execution-architecture.md`

### tools/methodology-runner/docs/design/components/
- **Purpose:** Canonical component designs for methodology-runner and phase-specific methodology components. Use this mirrored design path when the document describes methodology-runner internals, a methodology support component, or a phase design.
- **Signals:** methodology-runner component internals, phase design authority, methodology supervision design, standalone phase harness design, per-phase methodology component design.
- **Filename pattern:** preserve the existing component-design filename such as `CD-NNN-<slug>.md`.
- **Example:** `tools/methodology-runner/docs/design/components/CD-009-ph000-requirements-inventory-design.md`

### tools/methodology-runner/docs/prompts/
- **Purpose:** Canonical prompt modules and related prompt-runner input files owned by the methodology layer. Use this mirrored prompt path when the prompt exists to run a methodology phase, methodology workflow, or methodology experiment rather than to document prompt-runner itself.
- **Signals:** phase prompt module, methodology workflow prompt, hello-world methodology prompt, integration-agent prompt for methodology phases, methodology prompt README, retired methodology prompt.
- **Filename pattern:** preserve the existing prompt filename such as `PR-NNN-<slug>.md`, `integration-agent-PH-NNN-<slug>.md`, or `README.md`.
- **Example:** `tools/methodology-runner/docs/prompts/PR-025-ph000-requirements-inventory.md`

### tools/methodology-runner/src/
- **Purpose:** Methodology-runner Python source code. Use this mirrored source path when the code belongs to methodology-runner rather than to the main project tree or to prompt-runner.
- **Signals:** methodology-runner CLI entry point, orchestrator, phase registry, prompt-module selection, skill discovery, cross-reference logic, package code imported as `methodology_runner`.
- **Filename pattern:** `snake_case.py` for modules and fixed Python package files such as `__init__.py` and `__main__.py`.
- **Tests location:** `tools/methodology-runner/tests/` — mirror path, `test_<module>.py`.
- **Example:** `tools/methodology-runner/src/methodology_runner/orchestrator.py`

### tools/methodology-runner/src/methodology_runner/prompts/
- **Purpose:** Packaged runtime copies of methodology phase prompt modules. Use this path when a prompt must ship inside the installed `methodology_runner` package so the CLI can resolve it outside the source checkout.
- **Signals:** bundled phase prompt resources, packaged `PR-NNN-*.md` files, runtime prompt corpus for installed methodology-runner.
- **Filename pattern:** preserve the existing methodology prompt filename such as `PR-NNN-<slug>.md`.
- **Tests location:** `tools/methodology-runner/tests/` — add resource-consistency checks there when needed.
- **Example:** `tools/methodology-runner/src/methodology_runner/prompts/PR-025-ph000-requirements-inventory.md`

### tools/methodology-runner/tests/
- **Purpose:** Methodology-runner Python tests. Use this mirrored test path when the tests exercise methodology-runner code rather than the main project tree or prompt-runner.
- **Signals:** methodology-runner CLI tests, orchestrator tests, phase tests, skill catalog tests, cross-reference tests, imports from `methodology_runner`.
- **Filename pattern:** `test_<module>.py`.
- **Mirrors:** `tools/methodology-runner/src/`

### tools/methodology-runner/skills/
- **Purpose:** Methodology-owned skill-pack files that support methodology-runner execution and skill authoring. Use this path for methodology skill pack overview files and shared authoring guidance that belong to the methodology layer rather than to a generic plugin package.
- **Signals:** methodology skill pack README, methodology skill authoring context, methodology skill authoring prelude, shared guidance for the methodology skill set.
- **Filename pattern:** fixed support filenames such as `README.md`, `AUTHORING-CONTEXT.md`, or `authoring-prelude.txt`.
- **Example:** `tools/methodology-runner/skills/README.md`

### tools/methodology-runner/skills/<skill-name>/
- **Purpose:** Canonical methodology skill definitions used by methodology-runner. Each skill lives in its own directory with a `SKILL.md` file and belongs to the methodology layer rather than to a repo-local plugin wrapper.
- **Signals:** methodology skill definition, `SKILL.md`, phase-local or shared methodology discipline, skill loaded by methodology-runner, audience is methodology generator or judge agents.
- **Filename pattern:** `SKILL.md` inside `tools/methodology-runner/skills/<skill-name>/`.
- **Example:** `tools/methodology-runner/skills/traceability-discipline/SKILL.md`

### .codex/agents/
- **Purpose:** Repository-local Codex custom agent definitions. Use this path for TOML agent files that define reusable Codex agents for this repository and are meant to be registered into the user's Codex agent directory.
- **Signals:** Codex custom agent, `name =`, `description =`, `developer_instructions =`, `.toml` agent definition, reusable repo-local agent role, file meant to be linked or copied into `~/.codex/agents/`.
- **Filename pattern:** `kebab-case.toml`.
- **Example:** `.codex/agents/prompt-runner-generator.toml`

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
- **Purpose:** Transient implementation and migration plans — staged work plans that decompose an approved design, restructuring effort, or bounded migration into concrete execution steps. These are not design authorities, not requirements documents, and not acceptance-criteria specs. Historical value once the work is complete.
- **Signals:** "task group", "migration plan", "reorganization plan", "write failing test", "run pytest", "step-N deliverable", references a companion `CD-NNN` or `HLD-NNN` doc, implementation order section, cutover section, staged path moves, TDD cadence (failing test → minimal implementation → commit) when the plan is code-oriented.
- **Filename pattern:** `PLAN-NNN-<slug>.md` where NNN is 3-digit zero-padded and slug identifies the component or feature being implemented.
- **Example:** `docs/plans/PLAN-004-tiny-baseline-run.md`

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
- **Signals:** "test fixture", "used by methodology-runner run", "skill-authoring session", "tiny requirements", "sample input", not a `def test_` file, not a `describe(` block, referenced from a `tools/methodology-runner/docs/prompts/PR-NNN-*.md` file as the concrete input to a runner session.
- **Filename pattern:** `<topic-slug>.<ext>` in kebab-case, where ext matches the fixture format (e.g. `tiny-requirements.md`, `sample-config.yaml`).
- **Tests location:** n/a — these files are themselves fixtures, not code under test.

### sample/
- **Purpose:** Curated example bundles that demonstrate a coherent repository workflow or runnable scenario. Keep the example request, example fixtures, and any other sample-specific assets together under one sample subtree instead of scattering them across project docs and tool-owned folders.
- **Signals:** "hello world example", "demo workspace", "tutorial sample", "reference scenario", example-only request plus matching phase workspaces, assets retained so humans and agents can inspect or run one consistent example end to end.
- **Filename pattern:** use `sample/<sample-slug>/...`; beneath that sample root, preserve stable descriptive names such as `requests/hello-world-python-app.md` or `fixtures/ph000-hello-world-workspace/`.
- **Tests location:** n/a — sample bundles are curated reference assets, not test source files.

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

### tools/methodology-runner/docs/
- **Purpose:** Canonical reference specifications for the AI-driven software development methodology. This is the standing corpus that methodology-runner and related AI pipeline agents consult when executing the methodology on real projects. These documents define phases, agent roles, data models, and control flow for the methodology itself, not for any specific codebase that uses it.
- **Signals:** "AI-Driven Development Pipeline", "Phase Processing Unit", "agent role", "checklist extractor", "judge", "orchestrator", "simulation framework", "traceability infrastructure", "phase sequencing", YAML spec of pipeline phases or agent system prompts, audience is AI agents not human developers of a specific tool, not a design of agent-runner components.
- **Filename pattern:** `M-NNN-<slug>.md` or fixed supporting filenames such as `skills-baselines.yaml`.
- **Example:** `tools/methodology-runner/docs/M-001-phase-processing-unit-schema.md`

### .run-files/
- **Purpose:** Generated, run-scoped prompt-runner and methodology-runner artifacts produced inside a concrete worktree execution. This directory holds logs, prompt histories, summaries, and other runner-owned forensic data that should stay attached to that one run rather than being promoted into the canonical project tree.
- **Signals:** `.run-files/`, module-scoped runner output, execution logs, prompt history, runner summary, per-run bookkeeping, generated forensic evidence for one concrete run.
- **Filename pattern:** preserve runner-owned filenames and subdirectories such as `summary.txt`, `module.log`, `history/`, or tool-specific subdirectories like `.run-files/methodology-runner/`.
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
- **Signals:** "lessons learned", "authoring guide", "patterns that work well for AI", "skill authoring patterns", "adversarial testing results", "do not repeat these experiments", "best practices for skill writing", scoped to one plugin, not a SKILL.md, not a README, not a plugin.json, not a .methodology/docs/ spec.
- **Filename pattern:** `kebab-case.md` — descriptive slug matching the document's subject (e.g. `skill-authoring-lessons-learned.md`, `ai-consumption-patterns.md`).
- **Tests location:** n/a — these are reference documents, not runnable source code.

### plugins/<plugin-name>/
- **Purpose:** Self-contained Claude Code sub-agent plugin packages. Each subdirectory is a single named plugin that bundles a README, a companion spec or prompt file, and any supporting assets the plugin needs. The README is the human-facing entry point; the spec or prompt file is the machine-facing definition consumed by the methodology-runner or prompt-runner.
- **Signals:** "Claude Code plugin", "skill pack", "methodology-runner-skills", "sub-agent plugin", `plugins/` directory, companion spec reference, list of skills with one-line roles, "point at a companion spec", fixed plugin directory name determined by the plugin's identity.
- **Filename pattern:** `README.md` for the human-readable description; companion spec follows the `.methodology/docs/` naming convention for the spec file itself.
- **Tests location:** n/a — plugin directories are documentation and configuration, not runnable source code.

### work/
- **Purpose:** Temporary human- or agent-created working directories used for short-lived scratch artifacts, intermediate prompt drafts, and exploratory files that are intentionally not canonical reference material. This is the staging area for transient work before artifacts are either promoted into a canonical home or discarded.
- **Signals:** "temporary working folder", "scratch space", "draft prompts", "intermediate artifacts", "throwaway workspace", "not reference material", "working area for a specific run or experiment".
- **Filename pattern:** top-level subdirectory per task or experiment using `kebab-case/`; files inside should use the naming convention appropriate to their eventual artifact type when possible.
- **Tests location:** n/a — temporary working directories are not canonical test locations.

### .archive/
- **Purpose:** Git-ignored archive storage for superseded or intentionally retained historical artifacts that should not remain in the active project tree. Archive paths mirror the live project path beneath `.archive/` so the original location stays obvious.
- **Signals:** "archived version", "superseded doc", "retained old copy", "historical variant to keep but not keep active", archived workflow-run tree, retained generated evidence, explicit instruction to archive a file or directory instead of deleting it.
- **Filename pattern:** preserve the original relative path under `.archive/`; for example `docs/design/components/CD-009-...md` becomes `.archive/docs/design/components/CD-009-...md`, and `tools/prompt-runner/workflows/...` becomes `.archive/tools/prompt-runner/workflows/...`.
- **Tests location:** n/a — archived files and directories are retained history, not active artifacts.

### (project root)
- **Purpose:** Tooling configuration files and agent instruction files that must live at the repository root by ecosystem convention.
- **Signals:** `package.json`, `tsconfig.json`, `pyproject.toml`, `.gitignore`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `.editorconfig`, `.prettierrc`, lockfiles.
- **Filename pattern:** tool-specific, fixed names — use the exact filename the tooling expects.
- **Tests location:** n/a

## Change log

<!-- The agent appends one line per taxonomy extension here, newest at top. -->
- 2026-04-18 — sample/ added — curated example bundles such as Hello World need one self-contained home instead of being split across docs and methodology fixtures.
- 2026-04-18 — docs/plans/ extended — existing PLAN files already include migration and repo-change plans, so the taxonomy must explicitly allow staged reorganization and migration plans rather than only TDD implementation plans.
- 2026-04-15 — .codex/agents/ added — repository-local Codex custom agents need a canonical home separate from the older Claude-specific agent folder.
- 2026-04-18 — .archive/ broadened — archived historical directories such as generated workflow-run trees may also move into mirrored paths under `.archive/`.
- 2026-04-15 — .archive/ added — archived documents should leave the active tree and move into a git-ignored mirrored archive path under `.archive/`.
- 2026-04-15 — docs/design/components/ extended — YAML structured-design companions for existing component designs need a canonical home alongside the markdown authority when explicitly requested.
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
- 2026-04-08 — .methodology/docs/ added — AI-driven development methodology reference corpus (phase specs, agent role prompts, traceability model, simulation framework, orchestration) is not a design of agent-runner components, not a requirement, not a plan, and not a prompt file; a dedicated methodology corpus layer is needed.
- 2026-04-08 — docs/prompts/ added — prompt-runner input files (hand-authored LLM prompt sequences with paired validators) are inputs to a tool, not design docs, requirements, plans, or test code; a dedicated prompt-files layer is needed.
- 2026-04-08 — docs/plans/ added — TDD implementation plans (sequential task groups decomposing a design into test-first steps) are transient work documents that are neither design, requirements, nor acceptance criteria; a dedicated plan layer is needed.
- 2026-04-08 — docs/testing/ added — implementation acceptance criteria (runnable checks that the finished code matches a design) have no home in docs/design/, docs/requirements/, or tests/; a dedicated verification-spec layer is needed.
- 2026-04-08 — src/shared/ added — TypeScript types shared between server and web frontend have no home in either src/server/ or src/web/; a neutral shared layer is needed.
<!-- Format: YYYY-MM-DD — <category added> — <one-line reason> -->
