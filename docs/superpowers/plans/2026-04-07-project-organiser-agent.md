# Project-Organiser Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Claude Code sub-agent named `project-organiser` that classifies any new file against a living taxonomy and returns the correct target path, plus all the supporting scaffolding (taxonomy doc, directory skeleton, root `CLAUDE.md` trigger) needed to make it work from day 1.

**Architecture:** A single Claude Code sub-agent (no hooks, no skills, no slash commands) lives at `.claude/agents/project-organiser.md` and is invoked by main Claude before any file creation. Its rules live in the agent file; its data lives in `docs/project-taxonomy.md` (a separate human-readable doc the agent reads on every call and may edit). A root `CLAUDE.md` instructs main Claude to consult the agent. The taxonomy is **seeded** on day 1 with categories derived from the agent-runner stack (Python CLI, TS server, React frontend, mirrored test trees, requirements/design folders) so the agent has a known-good baseline. Extension is fully autonomous — when no category fits, the agent invents one and appends a change-log line.

**Tech Stack:** Markdown, YAML frontmatter, git. No runtime code in this plan — every artifact is config.

**Reference spec:** `docs/superpowers/specs/2026-04-07-project-organiser-agent-design.md`

---

## File Structure

Files this plan creates (4 file types, all under `/Users/martinbechard/dev/agent-runner/`):

| Path | Purpose | Created in |
|---|---|---|
| `CLAUDE.md` | Trigger instruction for main Claude — single load-bearing doc that makes the agent get invoked | Task 5 |
| `.claude/agents/project-organiser.md` | The sub-agent definition (frontmatter + system prompt) | Task 4 |
| `docs/project-taxonomy.md` | Seeded taxonomy doc — the agent's source of truth and the only file it edits | Task 3 |
| `.gitkeep` × 10 | Placeholder files inside each seeded folder so the directory skeleton exists on disk | Task 2 |
| `docs/superpowers/specs/2026-04-07-project-organiser-agent-design.md` | (already on disk from brainstorming) — committed in Task 1 | Task 1 |
| `docs/superpowers/plans/2026-04-07-project-organiser-agent.md` | This plan — committed in Task 1 | Task 1 |

Folders that get created (each contains a `.gitkeep`):

```
docs/requirements/functional/
docs/requirements/technical/
docs/design/high-level/
docs/design/components/
src/cli/
src/server/
src/web/
tests/cli/
tests/server/
tests/web/
```

---

## Task 1: Initialize git and commit existing design + plan docs

**Files:**
- Modify: (project root) — `git init`
- Commit: `docs/superpowers/specs/2026-04-07-project-organiser-agent-design.md`
- Commit: `docs/superpowers/plans/2026-04-07-project-organiser-agent.md`

**Why first:** The project is currently not a git repo. We need git before we can commit anything. The design doc and this plan already exist on disk from the brainstorming phase — they need a home in version control before we start adding more files.

- [ ] **Step 1: Initialize the repository**

```bash
cd /Users/martinbechard/dev/agent-runner && git init
```

Expected output:
```
Initialized empty Git repository in /Users/martinbechard/dev/agent-runner/.git/
```

- [ ] **Step 2: Verify initial state**

```bash
cd /Users/martinbechard/dev/agent-runner && git status
```

Expected: working tree shows two untracked files under `docs/superpowers/specs/` and `docs/superpowers/plans/`.

- [ ] **Step 3: Stage the design doc and plan**

```bash
cd /Users/martinbechard/dev/agent-runner && git add docs/superpowers/specs/2026-04-07-project-organiser-agent-design.md docs/superpowers/plans/2026-04-07-project-organiser-agent.md
```

- [ ] **Step 4: Create the initial commit**

```bash
cd /Users/martinbechard/dev/agent-runner && git commit -m "$(cat <<'EOF'
chore: initial commit — project-organiser design and plan

Brings the brainstorming spec and the implementation plan under version
control. No other code yet.
EOF
)"
```

Expected output: a commit summary with 2 files changed, no warnings or errors.

- [ ] **Step 5: Verify the commit landed**

```bash
cd /Users/martinbechard/dev/agent-runner && git log --oneline
```

Expected: one line, the initial commit.

---

## Task 2: Create the directory skeleton with `.gitkeep` files

**Files:**
- Create: `docs/requirements/functional/.gitkeep`
- Create: `docs/requirements/technical/.gitkeep`
- Create: `docs/design/high-level/.gitkeep`
- Create: `docs/design/components/.gitkeep`
- Create: `src/cli/.gitkeep`
- Create: `src/server/.gitkeep`
- Create: `src/web/.gitkeep`
- Create: `tests/cli/.gitkeep`
- Create: `tests/server/.gitkeep`
- Create: `tests/web/.gitkeep`

**Why this task:** The taxonomy doc (Task 3) describes folders. Those folders need to exist on disk so that (a) the layout is real from day 1, and (b) the agent's `Glob` calls in classification step 4 actually find a folder to enumerate. Empty directories are not tracked by git, hence `.gitkeep`.

- [ ] **Step 1: Create all 10 folders in one shot**

```bash
cd /Users/martinbechard/dev/agent-runner && mkdir -p \
  docs/requirements/functional \
  docs/requirements/technical \
  docs/design/high-level \
  docs/design/components \
  src/cli \
  src/server \
  src/web \
  tests/cli \
  tests/server \
  tests/web
```

- [ ] **Step 2: Drop a `.gitkeep` in each folder**

Use the Write tool to create each file with empty content. Do this for all 10 paths:

- `docs/requirements/functional/.gitkeep`
- `docs/requirements/technical/.gitkeep`
- `docs/design/high-level/.gitkeep`
- `docs/design/components/.gitkeep`
- `src/cli/.gitkeep`
- `src/server/.gitkeep`
- `src/web/.gitkeep`
- `tests/cli/.gitkeep`
- `tests/server/.gitkeep`
- `tests/web/.gitkeep`

Each file is empty (zero bytes is fine, but Write may require a newline — write a single newline character if so).

- [ ] **Step 3: Verify the layout**

```bash
cd /Users/martinbechard/dev/agent-runner && find docs src tests -type f -name .gitkeep | sort
```

Expected output (exactly 10 lines):
```
docs/design/components/.gitkeep
docs/design/high-level/.gitkeep
docs/requirements/functional/.gitkeep
docs/requirements/technical/.gitkeep
src/cli/.gitkeep
src/server/.gitkeep
src/web/.gitkeep
tests/cli/.gitkeep
tests/server/.gitkeep
tests/web/.gitkeep
```

- [ ] **Step 4: Commit the skeleton**

```bash
cd /Users/martinbechard/dev/agent-runner && git add docs/requirements docs/design src tests && git commit -m "$(cat <<'EOF'
chore: scaffold directory skeleton from taxonomy

Creates the 10 folders the seeded taxonomy will reference, with .gitkeep
files so they exist on disk before the taxonomy doc lands.
EOF
)"
```

Expected: a commit with 10 files changed.

---

## Task 3: Write the seeded taxonomy doc (`docs/project-taxonomy.md`)

**Files:**
- Create: `docs/project-taxonomy.md`

**Why this task:** This is the agent's source of truth. It must exist before the agent file (Task 4) is written, because the agent's algorithm (step 1) reads it on every call. Seeding it on day 1 — rather than leaving it empty — was decision D3 in the spec; it avoids the cold-start problem.

The doc has three structural sections in this order:
1. **Conventions** at the top (ID prefixes, casing rules, mirroring rule)
2. **Categories** (one `### <path>` heading per category, each with the same four-field schema)
3. **Change log** at the bottom (append-only, newest at top, starts empty)

- [ ] **Step 1: Write the file**

Create `docs/project-taxonomy.md` with the following exact content:

````markdown
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
````

- [ ] **Step 2: Verify the file landed**

Read the file back with the Read tool. Confirm:
- Frontmatter-free (this is a doc, not a Claude artifact).
- Has a `## Conventions` section.
- Has 11 `### ` category headings (10 folders + `(project root)`).
- Has a `## Change log` section at the bottom (empty body except the comments).

- [ ] **Step 3: Commit**

```bash
cd /Users/martinbechard/dev/agent-runner && git add docs/project-taxonomy.md && git commit -m "$(cat <<'EOF'
docs: seed project taxonomy

Adds the day-1 taxonomy that the project-organiser sub-agent will read on
every invocation. Eleven categories, the four-field schema (Purpose,
Signals, Filename pattern, Tests location), and an empty change log.
EOF
)"
```

---

## Task 4: Write the project-organiser agent definition (`.claude/agents/project-organiser.md`)

**Files:**
- Create: `.claude/agents/project-organiser.md`

**Why this task:** This is the agent itself. It depends on the taxonomy doc (Task 3) existing because the algorithm reads it on step 1. The agent file is the largest single artifact in this plan — it has YAML frontmatter and a structured system prompt with six sections. The full content goes below; do not paraphrase it.

- [ ] **Step 1: Create the `.claude/agents/` folder**

```bash
cd /Users/martinbechard/dev/agent-runner && mkdir -p .claude/agents
```

- [ ] **Step 2: Write the agent file**

Create `.claude/agents/project-organiser.md` with this exact content:

````markdown
---
name: project-organiser
description: Use proactively BEFORE creating any new file in this repo. Classifies a file by its purpose against the project taxonomy, assigns the correct target path and filename (with numeric ID where applicable), and autonomously extends the taxonomy when no category fits. Input must be either the file content or a description of its content. Returns a success shape { ok: true, path, rationale, taxonomy_extended, extension_summary } or an error shape { ok: false, error_code, error_message }.
tools: Read, Glob, Grep, Edit
model: sonnet
color: blue
---

# Role

You are the `project-organiser` sub-agent for the `agent-runner` project. Your single job is to decide where any new file should go, based on the living taxonomy at `docs/project-taxonomy.md`. You are the source of truth for project structure. You never create files yourself, never move files, never ask the user a question. You read, classify, optionally extend the taxonomy, and return a structured result.

# The Contract

## Input

You will be invoked with a prompt that contains one or both of:
- `content` — the full text of the file to be created
- `content_description` — a narrative of what the file will contain

At least one must be present. If both are absent or empty, return the error shape with `error_code: "missing_input"`. If the input is present but unparseable (binary blob, malformed structure), return `error_code: "malformed_input"`.

## Output

Return exactly one of these two shapes, as a single fenced JSON block, and nothing else. No preamble. No commentary outside the JSON.

**Success shape:**

```json
{
  "ok": true,
  "path": "docs/requirements/functional/FR-002-run-from-yaml.md",
  "rationale": "Functional requirement: describes user-visible CLI behaviour. Runner-up docs/requirements/technical rejected because the content describes WHAT the user sees, not a non-functional constraint. Next free FR number: 002.",
  "taxonomy_extended": false,
  "extension_summary": null
}
```

**Error shape:**

```json
{
  "ok": false,
  "error_code": "missing_input",
  "error_message": "Neither content nor content_description was provided in the invocation prompt."
}
```

Valid `error_code` values:
- `missing_input` — neither content nor content_description was supplied.
- `malformed_input` — input was present but unparseable.
- `path_escapes_root` — classification produced a path that would escape the project root.
- `taxonomy_unreadable` — `docs/project-taxonomy.md` could not be read or parsed.

# The Algorithm

On every invocation, execute these seven steps **in order**:

## Step 1 — Load the taxonomy

Read `docs/project-taxonomy.md` in full using the Read tool. Never skip this step. Never rely on memory from a previous call. If the file cannot be read, return error shape with `taxonomy_unreadable` and stop.

## Step 2 — Study the input

Parse the `content` or `content_description` from the prompt. Identify **purpose signals** — what role the file plays in the project, not what language it is written in. Examples of signals you will commonly see:

- "the system shall", "the user can", user story, use case → functional requirement
- "must support", "latency under", "runs on", "encrypted" → technical requirement
- component diagram, "X talks to Y via", system overview → high-level design
- "this module exposes", single-component internals → component design
- `argparse`, `click`, `typer`, `if __name__ == "__main__"` → `src/cli/`
- Express / Fastify / Hono route, HTTP handler, `app.get` / `app.post` → `src/server/`
- JSX / TSX, React hook, component export → `src/web/`
- `def test_`, `describe(`, `it(`, fixtures importing from `src/...` → mirrored test folder

## Step 3 — Match against taxonomy categories

Walk the taxonomy top-down. The most specific match wins. For test files, **derive the mirror path** from the source file under test (e.g. a test for `src/cli/config.py` goes to `tests/cli/test_config.py`; a test for `src/server/routes/runs.ts` goes to `tests/server/routes/runs.test.ts`).

If two categories plausibly fit, pick the more specific one and record the runner-up in the rationale. Do not stop to ask.

## Step 4 — Assign a filename

For **ID'd categories** (FR, TR, HLD, CD):
1. Use the Glob tool to list existing `.md` files in the target folder.
2. Parse the highest existing ID number from the filenames (e.g. from `FR-007-foo.md`, extract 7).
3. Next free number = highest + 1, zero-padded to 3 digits.
4. Generate a kebab-slug from the content's subject in 3–6 words.
5. Final filename: `<PREFIX>-<NNN>-<slug>.md`.
6. If the folder is empty, the next free number is `001`.

For **non-ID'd categories** (source, tests):
- Derive a filename from the content's primary export, class name, function name, or subject.
- Apply the casing convention from the taxonomy's Conventions section: `snake_case.py` for Python, `kebab-case.ts` for TS modules, `PascalCase.tsx` for React components.
- For test files, the filename is mechanical: take the source filename and apply the test-file convention from the taxonomy.

## Step 5 — Handle ambiguity without asking

You are autonomous. Never ask the user for clarification. When two categories fit, pick the more specific one and note the runner-up in the rationale. When the slug could go several ways, pick the clearest one and move on.

## Step 6 — Extend the taxonomy if nothing fits

If no existing category is a sensible home for the file:

1. Invent a new category under the most appropriate parent folder.
2. Use the Edit tool to add a new `### <path>` entry to `docs/project-taxonomy.md`, in the Categories section, in the alphabetically appropriate position. Use the same four-field schema (Purpose, Signals, Filename pattern, Tests location if applicable) as existing entries.
3. Append a line to the `## Change log` section at the bottom of the taxonomy doc. **New lines go at the top of the change log (newest first).** Format:
   `- YYYY-MM-DD — <category added> — <one-line reason>`
4. Set `taxonomy_extended = true` in your response.
5. Set `extension_summary` to the same line you appended to the change log (without the leading `- `).

## Step 7 — Return the structured result

Output **only** the JSON block defined in The Contract above. No surrounding text. Main Claude parses your output programmatically.

# Taxonomy Rules

- The taxonomy file is `docs/project-taxonomy.md`. It is the **only** file you may edit.
- Parse it as markdown. Each category is introduced by a level-3 heading (`### <path>`), followed by bullets for Purpose, Signals, Filename pattern, and optionally Tests location.
- When extending, **match the exact format of existing entries**. Do not invent new fields. Do not change existing entries.
- The Conventions section at the top defines ID prefixes and casing rules — always consult it before assigning filenames.
- The Change log section at the bottom is **append-only** (newest line at the top of the section body). Never rewrite history. Never reorder existing change-log lines.

# Hard Rules — you must NEVER violate these

1. **Never create new files.** You have Read, Glob, Grep, and Edit. You do NOT have Write. Your only side effect is editing `docs/project-taxonomy.md`.
2. **Never move, rename, or delete existing files.** If an existing file appears to be in the wrong place, note it in your rationale — do not act on it.
3. **Never write the file being classified.** Return the path only. Main Claude will write the file.
4. **Never ask the user a question.** You are autonomous by design.
5. **Never return a path outside the project root.** If classification would produce an escape path, return error `path_escapes_root` and stop.
6. **Always read the taxonomy fresh** at the start of each call. No in-memory assumptions between calls.
7. **Purpose beats format.** A `.md` file can be a requirement, a design, a README, or notes. Classify by role, not by extension.
8. **Output only the JSON block.** No preamble, no commentary outside the JSON code fence.

# Worked Example

**Invocation prompt (input):**

> content_description: "A functional requirement saying the CLI must accept a YAML config path via a --config flag and fail fast with a clear error if the file is missing."

**Your work (this is internal — do not output it):**

1. Read `docs/project-taxonomy.md`. Taxonomy loaded.
2. Signals identified: "functional requirement", "the CLI must accept", "--config flag", user-facing CLI behaviour. Matches `docs/requirements/functional/`.
3. Most specific match: `docs/requirements/functional/`. Runner-up: `docs/requirements/technical/` — rejected because the content describes user-facing behaviour, not a non-functional constraint.
4. ID'd category. Glob `docs/requirements/functional/*.md` → empty folder → next free ID is `001`. Slug from subject: `run-from-yaml-config`. Filename: `FR-001-run-from-yaml-config.md`.
5. No further ambiguity.
6. No extension needed.
7. Return:

**Your output (this is what you actually emit):**

```json
{
  "ok": true,
  "path": "docs/requirements/functional/FR-001-run-from-yaml-config.md",
  "rationale": "Functional requirement: describes user-visible CLI behaviour ('the CLI must accept', '--config flag', 'fail fast with a clear error'). Runner-up docs/requirements/technical rejected because this is user-facing behaviour, not a non-functional constraint. Next free FR number: 001 (folder empty).",
  "taxonomy_extended": false,
  "extension_summary": null
}
```

# Final Reminder

Output only the JSON block. Nothing before, nothing after. Main Claude parses your output programmatically — any commentary outside the JSON breaks the contract.
````

- [ ] **Step 3: Verify the file**

Read the file back with the Read tool. Confirm:
- The frontmatter is valid YAML (starts with `---`, ends with `---`, has `name`, `description`, `tools`, `model`, `color`).
- The body has six numbered sections (Role, The Contract, The Algorithm, Taxonomy Rules, Hard Rules, Worked Example) plus a Final Reminder.
- The total line count is roughly 150–250 lines.

```bash
cd /Users/martinbechard/dev/agent-runner && wc -l .claude/agents/project-organiser.md
```

Expected: a number between 150 and 260 inclusive. If it is far outside this range, the agent file is doing too much or too little — investigate before committing.

- [ ] **Step 4: Commit**

```bash
cd /Users/martinbechard/dev/agent-runner && git add .claude/agents/project-organiser.md && git commit -m "$(cat <<'EOF'
feat: add project-organiser sub-agent

The agent classifies any new file against docs/project-taxonomy.md and
returns a structured JSON result with the target path, rationale, and any
taxonomy extensions made. Tools limited to Read, Glob, Grep, Edit — no
Write, no Bash. Sonnet model.
EOF
)"
```

---

## Task 5: Write the root `CLAUDE.md` trigger

**Files:**
- Create: `CLAUDE.md`

**Why this task:** Without `CLAUDE.md`, main Claude has no reason to invoke the project-organiser sub-agent. This is the single load-bearing piece of the whole design — no trigger, no agent. It must be at the project root because that's where Claude Code automatically loads it.

- [ ] **Step 1: Write the file**

Create `/Users/martinbechard/dev/agent-runner/CLAUDE.md` with this exact content:

````markdown
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
````

- [ ] **Step 2: Commit**

```bash
cd /Users/martinbechard/dev/agent-runner && git add CLAUDE.md && git commit -m "$(cat <<'EOF'
feat: add root CLAUDE.md with project-organiser trigger

Tells main Claude to invoke the project-organiser sub-agent before creating
any new file in this repo. Without this trigger the sub-agent is never
consulted.
EOF
)"
```

---

## Task 6: Run acceptance scenarios against the agent

**Files:**
- No files modified (read-only validation pass).

**Why this task:** The agent file is markdown config, not runtime code, so we cannot unit-test it in the traditional sense. Instead we run the 10 acceptance scenarios from §10 of the design spec by invoking the agent and verifying its output.

**Important caveat:** Claude Code loads sub-agents from `.claude/agents/` at session start. If the agent was created mid-session, the current session may not yet have it registered as an invokable `subagent_type`. If the Agent tool with `subagent_type: project-organiser` is not available in this session, do not skip validation — instead **start a fresh Claude Code session in this directory and run the scenarios there**, marking this task complete only after all 10 pass.

The 10 scenarios are listed in §10 of `docs/superpowers/specs/2026-04-07-project-organiser-agent-design.md`. For each one, invoke the agent and check the result.

- [ ] **Step 1: Confirm the agent is invokable in the current session**

Try a smoke test invocation: dispatch the `project-organiser` sub-agent via the Agent tool with a trivial input and check whether it returns any JSON.

If the Agent tool reports "unknown subagent_type" or similar, **stop, ask the user to start a fresh Claude Code session, and resume from Step 2 in that session.**

If the agent responds, proceed to Step 2.

- [ ] **Step 2: Run scenario 1**

Input (`content_description`): "A requirement stating the CLI must accept a YAML config path."

Expected:
- `ok`: `true`
- `path` starts with `docs/requirements/functional/FR-001-` and ends with `.md`
- `taxonomy_extended`: `false`
- `extension_summary`: `null`

If the agent returns something different, capture the actual output, file the discrepancy, and pause before continuing.

- [ ] **Step 3: Run scenario 2**

Input: "Python 3.12 is the minimum supported version."

Expected: `path` starts with `docs/requirements/technical/TR-001-`, no extension.

- [ ] **Step 4: Run scenario 3**

Input: "Diagram of how CLI, server, and frontend talk to each other."

Expected: `path` starts with `docs/design/high-level/HLD-001-`, no extension.

- [ ] **Step 5: Run scenario 4**

Input: "Detailed design of the CLI runner component."

Expected: `path` starts with `docs/design/components/CD-001-`, no extension.

- [ ] **Step 6: Run scenario 5**

Input: "Unit test for the YAML config loader in `src/cli/config.py`."

Expected: `path` is `tests/cli/test_config.py`, no extension.

- [ ] **Step 7: Run scenario 6**

Input: "React component for the run history table."

Expected: `path` is `src/web/RunHistoryTable.tsx`, no extension. (Note: if the agent decides to extend with `src/web/components/`, that is also acceptable — record it as an observation but do not flag it as a failure since extension is autonomous by design.)

- [ ] **Step 8: Run scenario 7 — extension test**

Input: "TypeScript type shared between server and web."

Expected:
- `path` starts with `src/shared/`
- `taxonomy_extended`: `true`
- `extension_summary` is non-null and mentions `src/shared/`

Then verify that `docs/project-taxonomy.md` was actually edited:

```bash
cd /Users/martinbechard/dev/agent-runner && git diff docs/project-taxonomy.md | head -40
```

You should see a new `### src/shared/` category and a new line in the change log. If neither change appears, the extension logic is broken — investigate before continuing.

- [ ] **Step 9: Run scenario 8**

Input: "A requirement that the API must return in under 200ms."

Expected: `path` starts with `docs/requirements/technical/TR-002-` (note: 002, because TR-001 was assigned in scenario 2).

This scenario validates that the agent re-reads the taxonomy fresh and increments IDs across calls. **Important:** scenario 2 returned a path but did not actually create a file. So the next free ID is still 001 unless the file was actually written. If main Claude has not been writing files between scenarios, expect `TR-001-` here, not `TR-002-`. Adjust expectation based on whether intermediate writes happened. The point of this scenario is to confirm the agent uses the *current state of the folder*, not in-memory counters.

- [ ] **Step 10: Run scenario 9**

Input: "`pyproject.toml` for the Python package."

Expected: `path` is `pyproject.toml` (project root), rationale mentions "tooling config."

- [ ] **Step 11: Run scenario 10 — nested test mirror**

Input: "Unit test for the POST /runs route in `src/server/routes/runs.ts`."

Expected:
- `path` is `tests/server/routes/runs.test.ts`
- `taxonomy_extended` may be `true` if the agent extended the taxonomy to formally register `tests/server/routes/`, or `false` if it derived the path purely mechanically from the mirror rule. Either is acceptable — record which one happened.

- [ ] **Step 12: Roll back any taxonomy edits made during validation**

Validation should not leave permanent edits in the taxonomy doc. If scenarios 7 or 11 caused real edits to `docs/project-taxonomy.md`, decide whether to keep them (if they are sensible) or roll them back:

```bash
cd /Users/martinbechard/dev/agent-runner && git diff docs/project-taxonomy.md
```

If you want to keep the agent's extensions as part of day-1 state (recommended — they prove the system works end-to-end), commit them:

```bash
cd /Users/martinbechard/dev/agent-runner && git add docs/project-taxonomy.md && git commit -m "$(cat <<'EOF'
docs(taxonomy): record extensions made during day-1 validation

The project-organiser agent extended the taxonomy during acceptance
validation. Keeping these extensions as part of the seeded baseline.
EOF
)"
```

If you want to discard them (rare — only if the extensions were obviously wrong), restore the file:

```bash
cd /Users/martinbechard/dev/agent-runner && git checkout docs/project-taxonomy.md
```

- [ ] **Step 13: Final state check**

```bash
cd /Users/martinbechard/dev/agent-runner && git log --oneline && git status
```

Expected:
- 5 or 6 commits in `git log` (Tasks 1–5, plus optionally Task 6's validation extensions).
- `git status` shows a clean working tree.

If both checks pass, the implementation is complete and validated.

---

## Self-Review Checklist (run after writing the plan, before handing it back)

1. **Spec coverage** — every section of the design spec has a corresponding task:
   - §1 Purpose → covered by Tasks 3, 4, 5 (the three artifacts implementing it)
   - §2 Scope → respected (no out-of-scope items added)
   - §3 Stack context → encoded in the taxonomy seed (Task 3)
   - §4 Architectural decisions → all 9 decisions implemented (D1 sub-agent only → Task 4; D2 separate taxonomy → Task 3; D3 seeded → Task 3 content; D4 purpose-first → Task 2 layout; D5 src/tests split → Task 2 layout; D6 autonomous extension → Task 4 algorithm step 6; D7 input contract → Task 4 contract section; D8 output contract → Task 4 contract section; D9 model/tools → Task 4 frontmatter)
   - §5 Architecture → Tasks 2, 3, 4, 5 produce all listed files
   - §6 Agent definition → Task 4
   - §7 Classification algorithm → Task 4 system prompt sections "The Algorithm" and "Hard Rules"
   - §7.3 Output shape → Task 4 system prompt "The Contract"
   - §8 Taxonomy format → Task 3
   - §9 CLAUDE.md → Task 5
   - §10 Validation scenarios → Task 6
   - §11 Deliverables → all 5 listed deliverables produced

2. **Placeholder scan** — no TBDs, TODOs, "fill in later", or vague handwaves. Each step has either a complete code block or a complete command.

3. **Type consistency** — the JSON shapes used in Task 4's "Worked Example" match the shapes defined in "The Contract" earlier in the same file. Field names (`ok`, `path`, `rationale`, `taxonomy_extended`, `extension_summary`, `error_code`, `error_message`) are identical across all references.
