# agent-runner

This project uses a dedicated file-placement mechanism to keep artifacts in the
right place. The canonical taxonomy lives in `docs/project-taxonomy.md`.

## Rule: before creating any file

Before creating **any** new file in this repository, you MUST invoke the
repository's file-placement helper. Prefer the dedicated custom agent when the
runtime supports it. Otherwise use the repo-local placement skill or consult
`docs/project-taxonomy.md` directly. Pass the helper the file's content (if you
have drafted it) or a description of its intended content. Use the resulting
path as the target for your Write call.

Do not place files by intuition. The taxonomy is the source of truth.

### Parsing the sub-agent response

The `project-organiser` sub-agent is instructed to return a single fenced
JSON code block. In practice, Claude Code sub-agents cannot be constrained
to strict output formats via system prompt alone (see
[Claude Code sub-agents docs](https://code.claude.com/docs/en/sub-agents.md)
— no `output_format` / `json_schema` frontmatter is supported), so the
sub-agent may emit 1-3 sentences of narration before the JSON fence.

**How to parse:** extract the first ```json ... ``` fenced code block from
the sub-agent's response and ignore everything outside the fence. Do not
try `JSON.parse` on the whole response — it will fail on the preamble.

The placement helper should return either a success shape with
`ok: true, path, rationale, taxonomy_extended, extension_summary` or an
error shape with `ok: false, error_code, error_message`. Act on the
`path` only when `ok` is true.

Do not rely on an external `claude` CLI wrapper for file placement. Use the
current runtime's native custom-agent path, the repo-local placement skill, or
the taxonomy directly.

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
