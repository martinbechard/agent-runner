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

### (project root)
- **Purpose:** Tooling configuration files that must live at the repository root by ecosystem convention.
- **Signals:** `package.json`, `tsconfig.json`, `pyproject.toml`, `.gitignore`, `README.md`, `CLAUDE.md`, `.editorconfig`, `.prettierrc`, lockfiles.
- **Filename pattern:** tool-specific, fixed names — use the exact filename the tooling expects.
- **Tests location:** n/a

## Change log

<!-- The agent appends one line per taxonomy extension here, newest at top. -->
<!-- Format: YYYY-MM-DD — <category added> — <one-line reason> -->
