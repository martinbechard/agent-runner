# prompt-runner — input file format

*How to write a markdown file that the prompt-runner tool will accept. This guide is for people (and AIs) producing input files, not for people running the CLI.*

## What this tool does

prompt-runner is a small Python CLI that takes a markdown file of prompt/validator pairs, runs each prompt through a configured coding-agent CLI, runs the matching validator in a separate session, and iterates on revision feedback. It runs any markdown file that matches the format described below — it has no knowledge of any specific prompt content.

## Required file structure

Your file must contain one or more prompt sections of this shape:

```markdown
## Prompt 1: Your Title Here

Whatever prose or sub-headings you like (or none at all).

   (code block 1: the generation prompt)

More optional prose.

   (code block 2: the validation prompt)
```

(In the real file the two code blocks would each be wrapped in triple-backtick lines, not the parenthetical placeholders shown above.)

See *tests/cli/prompt_runner/fixtures/readme-example.md* for a minimal, parseable example.

## The heading rule

Every prompt section starts with a level-2 heading whose first word is *Prompt*. All of the following are accepted:

- *## Prompt 1: First Thing*
- *## Prompt: First Thing*
- *## Prompt First Thing*
- *## Prompt 3 — Agent Roles*
- *## Prompt* (the prompt will be listed as "(untitled)")

To mark a prompt for interactive execution, append *[interactive]* (case-insensitive) at the very end of the heading:

- *## Prompt 1: Author tdd skill [interactive]*

The marker is stripped from the displayed title and exposed as the `interactive` field on the parsed `PromptPair`. It has no effect on parsing — the runner uses it to decide whether to pause for human input before running the generation step.

You may also add heading directives:

- *[MODEL:...]*
- *[EFFORT:...]*

Examples:

- *## Prompt 1: Extract facts [MODEL:gpt-5.4-mini]*
- *## Prompt 2: Judge structure [MODEL:gpt-5.4] [EFFORT:high]*

These directives are stripped from the displayed title and exposed on the parsed prompt as `model_override` and `effort_override`.

Any number in the heading is ignored — the runner assigns each prompt a 1-based index based on its position in the file. If you want prompts to run in a specific order, put them in the file in that order.

## Variant forks

You may mark a prompt heading with *[VARIANTS]* to replace that prompt with multiple alternative prompt definitions that will be run as separate branches.

Shape:

```markdown
## Prompt 2: Audit [VARIANTS]

### Variant A: Long checklist

```
generator for variant A
```

```
validator for variant A
```

### Variant B: Short checklist

```
generator for variant B
```

```
validator for variant B
```
```

Rules:

- Each variant subsection must start with *### Variant <name>: <title>*.
- Each variant contains one or more prompt pairs using the same one-or-two-code-block rule as normal prompts.
- *[interactive]* and *[VARIANTS]* cannot appear on the same heading.
- A variant fork replaces that prompt position with alternative branches; later prompts in the file are appended after each branch.

## The code blocks

Between a prompt heading and the next prompt heading (or end of file), the parser reads one or two fenced code blocks:

1. The **generation prompt** — the body of the first code block (required).
2. The **validation prompt** — the body of the second code block (optional).

If only one code block is present, the prompt is accepted as *validator-less*: the parsed `PromptPair` has `validation_prompt=""` and `validation_line=0`. The runner skips the judge step for such prompts.

The order determines the role. The parser does not look at sub-headings like *### 1.1 Generation Prompt* — you can use those for readability, or not use them at all. You can put any prose, sub-headings, or notes between the two code blocks; only the code blocks are extracted.

Each code block is delimited by a line of exactly three backticks. You may add a language tag to the opening line (for example, *text* or *markdown*) — it is ignored.

### Optional `required-files`, `checks-files`, and `deterministic-validation` blocks

Before the generation prompt, you may add one typed code block named
`required-files`, one typed code block named `checks-files`, and one
typed code block named `deterministic-validation`:

````markdown
## Prompt 1: Needs inputs

```required-files
docs/request.md
tmp/context.json
```

```checks-files
tmp/summary.txt
tmp/previous-report.html
```

```deterministic-validation
scripts/validate_feature_spec.py
--feature-spec
docs/features/feature-specification.yaml
--requirements-inventory
docs/requirements/requirements-inventory.yaml
```

```
generator body
```

```
validator body
```
````

Each non-empty line inside that block is treated as a path that must
exist before the runner will make any backend call for that prompt. If a
path is relative, it is resolved against the runner workspace.

Each non-empty line inside `checks-files` is also treated as a path, but
the runner only records whether it exists in
`<prompt-dir>/checks-files.json`; it does not fail the prompt and it
does not invoke an LLM to perform the check.

Each non-empty line inside `deterministic-validation` becomes one argv
element for a Python script invocation. prompt-runner runs that script
after the generator has written files and before the judge runs. The
script's stdout, stderr, return code, and process metadata are written
to the prompt logs and injected into the judge prompt as deterministic
validation context.

Exit code conventions for deterministic validation:

- `0`: deterministic checks passed
- `1`: deterministic checks failed, but the judge should use the report
  to drive revision
- `>1`: deterministic validation itself failed, so prompt-runner halts

### Placeholder rendering

prompt-runner resolves built-in placeholders directly inside prompt
bodies and typed file blocks:

- `{{run_dir}}`
- `{{project_dir}}`

You can also pass extra placeholder values on the CLI:

```bash
prompt-runner run your-file.md --var workflow_prompt=/tmp/workflow.md --var raw_request=/tmp/request.md
```

If any placeholder remains unresolved when a prompt is about to run, the
runner halts before making a backend call.

## What NOT to do

- **Do not** include a third code block inside a prompt section. If your prompt body needs a code example, indent the example four spaces instead of wrapping it in triple backticks.
- **Do not** nest triple-backtick blocks inside a prompt body. v1 does not support this — the parser would see the inner backticks as the end of the outer block. Workaround: indent the inner example four spaces.
- **Do not** put your own VERDICT-format instruction in the validation prompt. The runner automatically appends an instruction telling the judge to end its response with *VERDICT: pass*, *VERDICT: revise*, or *VERDICT: escalate*. If your validation prompt prescribes a different verdict format, the two instructions will conflict.
- **Do not** rely on the number you write in the heading being preserved. The runner uses the prompt's position in the file.

## What the runner does with your prompts

- The first prompt's generator is invoked with the generation prompt body as-is.
- Each subsequent prompt's generator is invoked with every prior approved artifact prepended as context, followed by the generation prompt body.
- Each prompt's judge is invoked in a **separate backend session** with the validation prompt body, followed by the artifact the generator just produced, followed by the VERDICT instruction.
- If the judge returns *VERDICT: revise*, the generator is resumed with the judge's feedback and produces a revised artifact. The judge is then resumed to re-evaluate. Up to *--max-iterations* (default 3).
- If the judge returns *VERDICT: escalate* or the iteration cap is reached, the pipeline halts and the remaining prompts are skipped.

Generator and judge **never** share a backend session — they are always separate processes with separate session IDs.

## Writing good validation prompts

Your validation prompt is what the judge sees on every iteration. When the generator needs to revise, the only feedback it gets is whatever the judge wrote. Good validation prompts:

- List specific, checkable criteria (not "be thorough" or "use good judgement").
- Ask the judge to point at specific parts of the artifact that fail (line numbers, section names).
- Explain what a "revise" feedback should contain — the generator will act on it verbatim.

## Parser error IDs

If the parser rejects your file, it prints one of these error IDs and a friendly repair instruction:

- **E-NO-BLOCKS** — a prompt heading was found but no code blocks followed before the next heading or end of file.
- **E-MISSING-VALIDATION** — reserved; no longer raised (single-fence prompts are accepted as validator-less).
- **E-UNCLOSED-REQUIRED-FILES** — the optional `required-files` block was opened but never closed.
- **E-UNCLOSED-CHECKS-FILES** — the optional `checks-files` block was opened but never closed.
- **E-UNCLOSED-DETERMINISTIC-VALIDATION** — the optional `deterministic-validation` block was opened but never closed.
- **E-UNCLOSED-GENERATION** — the generation prompt's code block was opened but never closed.
- **E-UNCLOSED-VALIDATION** — the validation prompt's code block was opened but never closed.
- **E-EXTRA-BLOCK** — more than two code blocks were found inside a single prompt section.

## Running the tool

prompt-runner also supports a repo-level config file named
`prompt-runner.toml` (or `.prompt-runner.toml`). The runner searches
upward from the input file location and uses the nearest config it
finds.

Example:

```toml
[run]
backend = "codex"
```

CLI flags still win over config values, so `--backend claude` overrides
`[run].backend = "codex"` for a single invocation.

Once your file is ready:

```bash
prompt-runner parse your-file.md
```

verifies that the parser accepts it. Then:

```bash
prompt-runner run your-file.md
```

executes the full pipeline. See *prompt-runner run --help* for options.

Current runs can also be resumed:

```bash
prompt-runner run your-file.md --resume auto
```

or:

```bash
prompt-runner run your-file.md --resume path/to/existing-run-dir
```

By default, runs are written under:

```text
<project>/.prompt-runner/runs/<timestamp>-<prompt-stem>/
```

where `<project>` is `--project-dir` if provided, otherwise the current working directory.

## Known limitations (v1)

- Code blocks inside prompt bodies must not use triple backticks — indent them instead.
- On failure, the only escalation policy is *halt* — the runner does not automatically re-route to a prior phase.
- Nested variant forks are not yet fully supported in serialized tail prompts.
