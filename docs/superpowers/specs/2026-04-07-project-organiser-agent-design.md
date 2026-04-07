# Project-Organiser Agent — Design

**Date:** 2026-04-07
**Status:** Approved — ready for implementation planning
**Project:** agent-runner (greenfield)

## 1. Purpose

Create a Claude Code sub-agent named `project-organiser` whose job is to classify any new file against a living taxonomy of project artifacts and return the correct target path. The agent maintains `docs/project-taxonomy.md` as the source of truth for the project's structure and extends it autonomously when a new kind of artifact appears.

The overarching goal is to keep the repository structured so that future agentic development sessions can navigate the project without hunting — agent-friendliness is an explicit, first-class design goal.

## 2. Scope

**In scope:**

- A sub-agent definition at `.claude/agents/project-organiser.md`.
- A seeded taxonomy document at `docs/project-taxonomy.md`.
- A root-level `CLAUDE.md` that instructs main Claude to consult the agent before creating any new file.
- An empty directory skeleton (via `.gitkeep`) matching the seeded taxonomy so the layout exists on disk from day 1.
- A set of acceptance scenarios used to validate the agent after implementation.

**Out of scope:**

- `git init`, initial commit setup, `.gitignore` (handled separately).
- Any Python, TypeScript, or React source code.
- Package configs (`pyproject.toml`, `package.json`, `tsconfig.json`).
- Hooks, skills, or slash commands related to project organisation. The design explicitly uses sub-agent only.

## 3. Stack context (agent-runner)

The project will eventually contain:

- A Python command-line process.
- A TypeScript web server exposing API routes.
- A React frontend.
- Python unit tests and TypeScript unit tests for every piece of code that gets built.
- Functional requirements, technical requirements, and high-level designs (component decomposition + interaction).

## 4. Architectural decisions

Decisions locked in during brainstorming, with the reasoning behind each:

| # | Decision | Reason |
|---|---|---|
| D1 | Form factor: **sub-agent only**. No hooks, no skills, no slash commands. | User choice. Keeps the mechanism simple and debuggable. Trigger is supplied by `CLAUDE.md`. |
| D2 | Taxonomy lives in a **separate markdown file** at `docs/project-taxonomy.md`, not inside the agent definition. | Separates rules (agent) from data (taxonomy). Agent definition stays small and stable; taxonomy can grow without bloating the agent. Human-readable at a glance. |
| D3 | The taxonomy is **seeded on day 1**, not left empty. | Avoids the cold-start problem. Gives the agent a known-good baseline derived from the stack. |
| D4 | Layout is **purpose-first**, not language-first (`docs/requirements/`, `src/cli/`, `tests/cli/`, not `python/`, `typescript/`). | An agent looking for "where is the auth requirement?" should not need to know the implementation language first. Purpose is stable; language is an implementation detail. |
| D5 | Source and tests are in **separate top-level trees** (`src/`, `tests/`), with tests mirroring source paths. | Mechanical test location derivation; no ambiguity about "where does the test go?" |
| D6 | Taxonomy extension policy: **fully autonomous**. The agent invents new categories as needed and edits the taxonomy without asking. | User choice. Speed over safety, on the expectation that most extensions are obvious and the change log makes extensions auditable. |
| D7 | Invocation contract input: **content or content-description**. At least one is required. | Descriptions alone are too vague for reliable classification and ID assignment; a draft or summary of content gives the agent real signals to match against. |
| D8 | Invocation contract output: **path + rationale + taxonomy_extended flag + extension_summary**. | Rationale makes the agent auditable; surfacing taxonomy extensions keeps the user informed without blocking. |
| D9 | Agent model: **sonnet**. Tools: **Read, Glob, Grep, Edit** (no Write, no Bash). | Classification is structured pattern-matching, not generation — sonnet is the right fit. Tool set is the minimum needed; denying Write and Bash removes a whole class of accidents. |

## 5. Architecture & file layout

Three artifacts get created:

```
agent-runner/
├── CLAUDE.md                              # Trigger for main Claude (NEW)
├── .claude/
│   └── agents/
│       └── project-organiser.md           # The sub-agent (NEW)
├── docs/
│   ├── project-taxonomy.md                # Living taxonomy, seeded (NEW)
│   ├── requirements/
│   │   ├── functional/.gitkeep
│   │   └── technical/.gitkeep
│   └── design/
│       ├── high-level/.gitkeep
│       └── components/.gitkeep
├── src/
│   ├── cli/.gitkeep
│   ├── server/.gitkeep
│   └── web/.gitkeep
└── tests/
    ├── cli/.gitkeep
    ├── server/.gitkeep
    └── web/.gitkeep
```

The `.gitkeep` files ensure the skeleton exists on disk from day 1 so the taxonomy isn't describing imaginary folders.

### 5.1 Data flow for a typical invocation

```
main Claude about to create a file
  └─> reads CLAUDE.md (already in context)
      └─> invokes project-organiser sub-agent
          input: { content OR content_description }
            └─> agent reads docs/project-taxonomy.md
                └─> agent classifies → path + ID + rationale
                    └─> if taxonomy needs extension:
                        agent edits docs/project-taxonomy.md
                        (adds folder entry + change-log line)
                    └─> agent returns structured result
          output: success or error shape (see §7.3)
      └─> main Claude writes file at returned path (success shape only)
```

## 6. The agent definition (`.claude/agents/project-organiser.md`)

### 6.1 Frontmatter

```yaml
---
name: project-organiser
description: Use proactively BEFORE creating any new file in this repo. Classifies a file by its purpose against the project taxonomy, assigns the correct target path and filename (with numeric ID where applicable), and autonomously extends the taxonomy when no category fits. Input must be either the file content or a description of its content. Returns a success shape { ok: true, path, rationale, taxonomy_extended, extension_summary } or an error shape { ok: false, error_code, error_message } — see §7.3 of the design doc.
tools: Read, Glob, Grep, Edit
model: sonnet
color: blue
---
```

- `description` is front-loaded with "Use proactively BEFORE creating any new file in this repo." This is the only signal Claude Code uses to decide when to invoke a sub-agent; it must explicitly state the trigger and the contract.
- Tools: `Read` to load taxonomy and sample files; `Glob` to list folder contents when finding the next free ID; `Grep` to search for existing IDs or purpose signals; `Edit` to append to the taxonomy when extending. **No `Write`** because the agent must never create new files. **No `Bash`** because it is not needed.
- `model: sonnet` is right-sized for structured classification.

### 6.2 System prompt — six sections

1. **Role statement** — one sentence on what this agent is for.
2. **The contract** — exact input and output shapes (the two shapes defined in §7.3). Missing or malformed input must produce the error shape with an appropriate `error_code`; the agent never guesses a default folder when input is absent.
3. **The algorithm** — the 7-step classification sequence from Section 7 of this doc, spelled out as an ordered procedure the agent follows on every call.
4. **The taxonomy rules** — where the taxonomy file lives, how to parse it, how to extend it, the exact change-log line format.
5. **Hard rules** — the things the agent must never do:
   - Never create files (only edits `docs/project-taxonomy.md`).
   - Never move existing files.
   - Never ask the user for input — autonomous by design.
   - Never return a path outside the project root.
   - Never skip reading the taxonomy fresh at the start of each call.
6. **Output format** — the exact structure of the return value, with one worked example so output is machine-parseable.

**Size target:** 150–250 lines total. If it grows past that, the agent is doing too much.

## 7. Classification algorithm

On every invocation, the agent executes this sequence:

1. **Load the taxonomy.** Read `docs/project-taxonomy.md` in full. No caching — always fresh.
2. **Study the input.** Parse `content` or `content_description`. Identify **purpose signals** — not language, not format, but what role the file plays. Examples:
   - "describes what the system must do from a user's POV" → functional requirement
   - "describes a performance/security/tech constraint" → technical requirement
   - "decomposes the solution into interacting components" → high-level design
   - "tests the behavior of <something in src/>" → tests folder mirroring that source path
   - "implements a CLI command" → `src/cli/`
   - "defines an API route handler" → `src/server/`
   - "is a React component or page" → `src/web/`
3. **Match against taxonomy categories.** Walk the taxonomy top-down, most specific match wins. For tests, derive the mirror path from the source file being tested.
4. **Assign a filename.**
   - ID'd categories: generate `<PREFIX>-<NNN>-<kebab-slug>.<ext>`. The next free number is determined by a Glob of the target folder. The slug is derived from the content's subject in 3–6 words.
   - Non-ID'd categories: propose a filename from the content's primary export or subject, following the category's casing convention (snake_case for Python, kebab-case for TS, PascalCase for React components).
5. **Handle ambiguity.** If two categories could plausibly fit, pick the more specific one and record the runner-up in the rationale. Do not ask the user.
6. **Extend if nothing fits.** Invent a new category under the most appropriate parent, edit `docs/project-taxonomy.md` to add the entry, append a line to the change log, and set `taxonomy_extended = true`.
7. **Return.** Structured result — see 7.3 for the exact output shape.

### 7.1 Hard rules

- Never create files (only edits `docs/project-taxonomy.md`).
- Never move existing files — if an existing file is in the wrong place, note it in the rationale only.
- Never write the file being classified.
- Always read the taxonomy fresh; no in-memory assumptions between calls.
- Purpose beats format — a `.md` file can be a requirement, a design, or a README; classify by role.

### 7.2 Edge cases

- **Test files** mirror the path of the source file they test, even if that source file does not yet exist.
- **Shared code** (e.g. types used by both server and web) goes under `src/shared/`, which the agent creates as an extension the first time it is needed.
- **Tooling configs at the root** (`package.json`, `tsconfig.json`, `pyproject.toml`, `.gitignore`, `README.md`, `CLAUDE.md`) stay at the root; the agent returns the root path with a rationale noting "tooling config."

### 7.3 Output shape

The agent returns exactly one of two shapes.

**Success shape** (classification succeeded):

```
{
  "ok": true,
  "path": "<string>",                 // repo-relative target path including filename, e.g. "docs/requirements/functional/FR-002-run-from-yaml.md"
  "rationale": "<string>",            // 1-3 sentences: why this folder, which signals matched, the runner-up category if any
  "taxonomy_extended": <boolean>,     // true iff the agent edited docs/project-taxonomy.md during this call
  "extension_summary": "<string|null>" // null when taxonomy_extended is false; otherwise a one-line summary of what was added (matches the change-log line)
}
```

**Error shape** (input was missing or malformed, or no valid classification could be made without violating a hard rule):

```
{
  "ok": false,
  "error_code": "<string>",           // one of: "missing_input", "malformed_input", "path_escapes_root", "taxonomy_unreadable"
  "error_message": "<string>"         // human-readable explanation
}
```

The agent **must** return one of these two shapes. It must never return a bare string, never invent additional fields, and never guess when the input is missing — missing input is an error, not a reason to classify into a default folder.

## 8. `docs/project-taxonomy.md` format

The taxonomy uses structured markdown with a consistent schema per category so it is both machine-parseable and human-auditable.

### 8.1 Schema

Every category entry has these fields:

- **Purpose** — what goes here, in one sentence.
- **Signals** — phrases and patterns that indicate a file belongs in this category (this is the agent's classification oracle).
- **Filename pattern** — the exact filename shape the agent must produce.
- **Tests location** *(source categories only)* — the mirror folder where tests for files in this category live.

A top-level `Conventions` section lists ID prefixes, ID format (`<PREFIX>-<3-digit>-<kebab-slug>.md`), filename casing rules, and the test-mirroring rule.

A bottom `Change log` section receives one line per taxonomy extension, newest first, with format:

```
YYYY-MM-DD — <category added> — <one-line reason>
```

### 8.2 Seeded categories

On day 1, the taxonomy lists:

- `docs/requirements/functional/` — FR-NNN, functional requirements.
- `docs/requirements/technical/` — TR-NNN, technical / non-functional requirements.
- `docs/design/high-level/` — HLD-NNN, system-wide decomposition.
- `docs/design/components/` — CD-NNN, per-component design.
- `src/cli/` — Python CLI source, tests mirror to `tests/cli/`.
- `src/server/` — TypeScript server and routes, tests mirror to `tests/server/`.
- `src/web/` — React frontend, tests mirror to `tests/web/`.
- `tests/cli/`, `tests/server/`, `tests/web/` — mirrored test trees.
- `(project root)` — tooling config files only.

Each category has the full four-field schema populated with realistic signal lists.

## 9. `CLAUDE.md` at the project root

The trigger document. Without it the sub-agent is never invoked.

```markdown
# agent-runner

This project uses a `project-organiser` sub-agent to keep all artifacts in the
right place. The canonical taxonomy lives in `docs/project-taxonomy.md`.

## Rule: before creating any file

Before creating any new file in this repository, you MUST invoke the
`project-organiser` sub-agent. Pass it the file's content (if you have drafted
it) or a description of its intended content. Use the `path` it returns as
the target for your Write call.

Do not place files by intuition. The taxonomy is the source of truth.

## Stack

- Python command-line process (`src/cli/`, tests in `tests/cli/`)
- TypeScript web server with API routes (`src/server/`, tests in `tests/server/`)
- React frontend (`src/web/`, tests in `tests/web/`)

Every piece of source code must have accompanying unit tests. Functional
requirements, technical requirements, and high-level designs live under
`docs/` — see `docs/project-taxonomy.md` for the exact layout.
```

## 10. Validation — acceptance scenarios

The agent file is markdown config, not runtime code, so it is not unit-tested in the traditional sense. Instead, after implementation the following scenarios are run end-to-end and must each return the expected result.

| # | Input (content description) | Expected folder | Expected filename shape | Taxonomy extended? |
|---|---|---|---|---|
| 1 | "A requirement stating the CLI must accept a YAML config path" | `docs/requirements/functional/` | `FR-001-<slug>.md` | no |
| 2 | "Python 3.12 is the minimum supported version" | `docs/requirements/technical/` | `TR-001-<slug>.md` | no |
| 3 | "Diagram of how CLI, server, and frontend talk to each other" | `docs/design/high-level/` | `HLD-001-<slug>.md` | no |
| 4 | "Detailed design of the CLI runner component" | `docs/design/components/` | `CD-001-<slug>.md` | no |
| 5 | "Unit test for the YAML config loader in `src/cli/config.py`" | `tests/cli/` | `test_config.py` | no |
| 6 | "React component for the run history table" | `src/web/` | `RunHistoryTable.tsx` | no |
| 7 | "TypeScript type shared between server and web" | `src/shared/` (new) | `kebab-case.ts` | **yes** |
| 8 | "A requirement that the API must return in under 200ms" | `docs/requirements/technical/` | `TR-002-<slug>.md` | no |
| 9 | "`pyproject.toml` for the Python package" | (project root) | `pyproject.toml` | no |
| 10 | "Unit test for the POST /runs route in `src/server/routes/runs.ts`" | `tests/server/routes/` | `runs.test.ts` | yes (subfolder) |

If scenario 7 triggers a taxonomy extension with a sensible change-log line, extension logic is working end-to-end. If scenario 10 creates `tests/server/routes/` as a sibling, the mirror derivation + extension combination is working.

*The user directive "unit tests for everything we build" applies to the Python / TS / React code that will be written under this taxonomy, not to the agent definition itself.*

## 11. Deliverables

Files created by this work:

1. `.claude/agents/project-organiser.md` — the agent.
2. `docs/project-taxonomy.md` — the seeded taxonomy doc.
3. `CLAUDE.md` — the trigger instruction at project root.
4. `.gitkeep` files in each seeded folder so the skeleton exists on disk from day 1.
5. This design doc at `docs/superpowers/specs/2026-04-07-project-organiser-agent-design.md`.

## 12. Open questions

None as of 2026-04-07. All architectural decisions are locked in (see Section 4).
