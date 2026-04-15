# prompt-runner input format

This guide is for people and agents authoring prompt files for `prompt-runner`.

## What this tool does

`prompt-runner` reads a markdown workflow, executes each generation prompt with a configured backend, optionally executes a matching validation prompt in a separate session, and iterates on revision feedback.

## Related References

Use these together:

- `src/cli/prompt_runner/README.md`: authoring guide and file-format reference
- `docs/design/components/CD-001-prompt-runner.md`: implementation contract and parser model
- `docs/testing/AC-001-prompt-runner.md`: acceptance criteria and verification targets
- `tests/cli/prompt_runner/fixtures/readme-example.md`: minimal valid example prompt file

## Run Model

`prompt-runner` treats the run directory as the editable worktree for the run.

- Permanent project artifacts are written at their real project-relative paths inside `--run-dir`.
- Runner-owned temporary and forensic files live under `--run-dir/.run-files/`.
- Runner-owned files are grouped per module under `--run-dir/.run-files/<module-slug>/`.
- Each module directory contains one consolidated `module.log` plus the module's prompt-result files.
- If `--run-dir` points at a fresh directory and `--project-dir` is set, prompt-runner initialises the run worktree as a linked Git worktree when the source project is Git-backed; otherwise it falls back to copying the source project tree into `--run-dir`.
- If `--run-dir` points at the project root, prompt-runner ensures `.run-files/` is listed in `.gitignore`.

## Required file structure

Each prompt starts with a level-2 heading whose first word is `Prompt`.

```markdown
## Prompt 1: Your Title Here

### Generation Prompt

Write the generation task here.

### Validation Prompt

Write the validation task here.
```

The generation subsection is required. The validation subsection is optional.

See `tests/cli/prompt_runner/fixtures/readme-example.md` for a minimal parseable example.

## Prompt headings

All of these forms are accepted:

- `## Prompt 1: First Thing`
- `## Prompt: First Thing`
- `## Prompt First Thing`
- `## Prompt 3 — Agent Roles`
- `## Prompt`

Any number in the heading is ignored. Prompt-runner uses the prompt's position in the file.

Append `[interactive]` at the end of the prompt heading to mark a prompt for interactive execution:

- `## Prompt 1: Author tdd skill [interactive]`

You may also add heading directives:

- `[MODEL:...]`
- `[EFFORT:...]`

Examples:

- `## Prompt 1: Extract facts [MODEL:gpt-5.4-mini]`
- `## Prompt 2: Judge structure [MODEL:gpt-5.4] [EFFORT:high]`

`[interactive]` and `[VARIANTS]` cannot appear on the same heading.

## Prompt subsections

Normal prompts use `###` subsections. Allowed subsection headings are:

- `### Module`
- `### Required Files`
- `### Checks Files`
- `### Deterministic Validation`
- `### Generation Prompt`
- `### Validation Prompt`

Rules:

- `### Generation Prompt` is required.
- `### Validation Prompt` is optional.
- `### Module`, `### Required Files`, `### Checks Files`, and `### Deterministic Validation`, if present, must appear before `### Generation Prompt`.
- Each subsection may appear at most once per prompt.
- Prompt bodies may contain deeper headings such as `####` or `#####`; only the exact reserved subsection level is structural.

## Variants

Add `[VARIANTS]` to a prompt heading to replace that prompt with variant branches.

```markdown
## Prompt 2: Audit [VARIANTS]

### Variant A: Long checklist

#### Generation Prompt

generator for variant A

#### Validation Prompt

validator for variant A

### Variant B: Short checklist

#### Generation Prompt

generator for variant B

#### Validation Prompt

validator for variant B
```

Rules:

- Each variant starts with `### Variant <name>: <title>`.
- Prompt subsections inside variants use `####` instead of `###`.
- A variant may contain multiple prompt pairs by repeating `#### Generation Prompt` and optional `#### Validation Prompt`.
- Standalone `[MODEL:...]` and `[EFFORT:...]` lines between variant pairs update the defaults for the next pair in that variant only.

## Optional metadata subsections

### Module

Optional stable slug for runner-owned files under `.run-files/<module-slug>/`.

- Use this when prompt titles are long or likely to change.
- If omitted, prompt-runner falls back to a slug derived from the prompt title.
- This affects only runner-owned bookkeeping paths, not the artifact output paths inside the run worktree.

### Required Files

Each non-empty line is treated as a path that must exist before the generator runs.

### Checks Files

Each non-empty line is treated as a path whose existence should be recorded without failing the prompt.
The results are appended to the module's `module.log`; prompt-runner does not create a separate checks file.

### Deterministic Validation

Each non-empty line becomes one argv element for a Python script invocation that runs after generation and before the judge.

Exit code conventions for deterministic validation:

- `0`: checks passed
- `1`: checks failed, but the judge should drive revision
- `>1`: deterministic validation itself failed, so prompt-runner halts

## Placeholder rendering

Prompt-runner resolves placeholders inside prompt bodies and metadata sections:

- `{{run_dir}}`
- `{{project_dir}}`

Both resolve to the run worktree root. `run_dir` is the concrete run location; `project_dir` remains available as a compatibility alias for prompts that still use the older name.

You can also pass extra values on the CLI:

```bash
prompt-runner run your-file.md --var workflow_prompt=/tmp/workflow.md --var raw_request=/tmp/request.md
```

If any placeholder remains unresolved when a prompt is about to run, the runner halts before making a backend call.

## What not to do

- Do not omit `### Generation Prompt` or `#### Generation Prompt`.
- Do not invent other subsection headings at the reserved structural level.
- Do not place `Required Files`, `Checks Files`, or `Deterministic Validation` after the generation subsection.
- Do not put your own verdict-format instruction in the validation prompt; prompt-runner appends its own verdict instruction.

## Parser error IDs

- `E-NO-GENERATION` — a prompt or variant pair has no generation subsection.
- `E-BAD-SECTION-ORDER` — a subsection appears in the wrong order.
- `E-DUPLICATE-SECTION` — a subsection appears more than once in one prompt pair.
- `E-UNKNOWN-SUBSECTION` — an unrecognized reserved-level subsection heading was found.
- `E-NO-VARIANTS` — a `[VARIANTS]` prompt contains no `### Variant ...` subsections.

## Running the tool

Validate the file:

```bash
prompt-runner parse your-file.md
```

Run the workflow:

```bash
prompt-runner run your-file.md
```

Use a specific run directory:

```bash
prompt-runner run your-file.md --run-dir /tmp/my-run
```

Initialise a new run worktree from an existing project tree:

```bash
prompt-runner run your-file.md --project-dir /path/to/project --run-dir /tmp/my-run
```

Resume the latest run for the same source file:

```bash
prompt-runner run your-file.md --resume auto
```
