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
- **Example:** `PLAN-001-prompt-runner.md`

### docs/testing/
- **Purpose:** Implementation acceptance criteria and test plans — concrete, runnable checks that verify finished code matches a design spec. Not the design itself and not the test code; the layer in between.
- **Signals:** "AC-NN", "verification method", "run pytest and assert", "grep src/ for", acceptance criteria grouped by deliverable, traces back to a requirement or design section, companion to a `CD-NNN` or `HLD-NNN` doc.
- **Filename pattern:** `AC-NNN-<slug>.md` where NNN is 3-digit zero-padded and slug identifies the component or feature.
- **Example:** `AC-001-prompt-runner.md`

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

### docs/prompts/
- **Purpose:** Hand-authored prompt-runner input files — sequences of LLM generation prompts paired with validator prompts, consumed by the prompt-runner CLI tool to produce design docs, acceptance criteria, plans, or source code. These files drive downstream artifact generation but are not themselves design documents, requirements, acceptance criteria, or plans.
- **Signals:** `## Prompt N:` section headings, paired fenced code blocks (generation prompt + validation prompt), "max_iterations", "sent to Claude", "judge", intended to be passed as `--input` to the prompt-runner CLI, subject line references a tool or feature being built via the runner.
- **Filename pattern:** `PR-NNN-<slug>.md` where NNN is 3-digit zero-padded and slug identifies the tool or feature the prompts will produce.
- **Example:** `PR-001-methodology-runner.md`

### (project root)
- **Purpose:** Tooling configuration files that must live at the repository root by ecosystem convention.
- **Signals:** `package.json`, `tsconfig.json`, `pyproject.toml`, `.gitignore`, `README.md`, `CLAUDE.md`, `.editorconfig`, `.prettierrc`, lockfiles.
- **Filename pattern:** tool-specific, fixed names — use the exact filename the tooling expects.
- **Tests location:** n/a

## Change log

<!-- The agent appends one line per taxonomy extension here, newest at top. -->
- 2026-04-08 — docs/prompts/ added — prompt-runner input files (hand-authored LLM prompt sequences with paired validators) are inputs to a tool, not design docs, requirements, plans, or test code; a dedicated prompt-files layer is needed.
- 2026-04-08 — docs/plans/ added — TDD implementation plans (sequential task groups decomposing a design into test-first steps) are transient work documents that are neither design, requirements, nor acceptance criteria; a dedicated plan layer is needed.
- 2026-04-08 — docs/testing/ added — implementation acceptance criteria (runnable checks that the finished code matches a design) have no home in docs/design/, docs/requirements/, or tests/; a dedicated verification-spec layer is needed.
- 2026-04-08 — src/shared/ added — TypeScript types shared between server and web frontend have no home in either src/server/ or src/web/; a neutral shared layer is needed.
<!-- Format: YYYY-MM-DD — <category added> — <one-line reason> -->
