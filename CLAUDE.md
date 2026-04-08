# agent-runner

This project uses a `project-organiser` sub-agent to keep all artifacts in the
right place. The canonical taxonomy lives in `docs/project-taxonomy.md`.

## Rule: before creating any file

Before creating **any** new file in this repository, you MUST invoke the
`project-organiser` sub-agent (via the Agent tool, `subagent_type: project-organiser`).
Pass it the file's content (if you have drafted it) or a description of its
intended content. Use the `path` it returns as the target for your Write call.

Do not place files by intuition. The taxonomy is the source of truth.

## Stack

- **Python command-line process** — source in `src/cli/`, tests in `tests/cli/`
- **TypeScript web server with API routes** — source in `src/server/`, tests in `tests/server/`
- **React frontend** — source in `src/web/`, tests in `tests/web/`

Every piece of source code must have accompanying unit tests.

Functional requirements, technical requirements, and high-level designs live
under `docs/` — see `docs/project-taxonomy.md` for the exact layout.

## Project organisation philosophy

The repository layout is **purpose-first**, not language-first. When you are
looking for "where does the auth requirement live?", you should not need to
know the implementation language first. Folders are named after the role the
files inside them play; language is an implementation detail of files inside
`src/<component>/`.
