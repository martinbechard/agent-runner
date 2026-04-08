# prompt-runner — input file format

*How to write a markdown file that the prompt-runner tool will accept. This guide is for people (and AIs) producing input files, not for people running the CLI.*

## What this tool does

prompt-runner is a small Python CLI that takes a markdown file of prompt/validator pairs, runs each prompt through Claude, runs the matching validator in a separate session, and iterates on revision feedback. It runs any markdown file that matches the format described below — it has no knowledge of any specific prompt content.

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

Any number in the heading is ignored — the runner assigns each prompt a 1-based index based on its position in the file. If you want prompts to run in a specific order, put them in the file in that order.

## The two code blocks

Between a prompt heading and the next prompt heading (or end of file), the parser expects **exactly two fenced code blocks**, in this order:

1. The **generation prompt** — the body of the first code block.
2. The **validation prompt** — the body of the second code block.

The order determines the role. The parser does not look at sub-headings like *### 1.1 Generation Prompt* — you can use those for readability, or not use them at all. You can put any prose, sub-headings, or notes between the two code blocks; only the code blocks are extracted.

Each code block is delimited by a line of exactly three backticks. You may add a language tag to the opening line (for example, *text* or *markdown*) — it is ignored.

## What NOT to do

- **Do not** include a third code block inside a prompt section. If your prompt body needs a code example, indent the example four spaces instead of wrapping it in triple backticks.
- **Do not** nest triple-backtick blocks inside a prompt body. v1 does not support this — the parser would see the inner backticks as the end of the outer block. Workaround: indent the inner example four spaces.
- **Do not** put your own VERDICT-format instruction in the validation prompt. The runner automatically appends an instruction telling the judge to end its response with *VERDICT: pass*, *VERDICT: revise*, or *VERDICT: escalate*. If your validation prompt prescribes a different verdict format, the two instructions will conflict.
- **Do not** rely on the number you write in the heading being preserved. The runner uses the prompt's position in the file.

## What the runner does with your prompts

- The first prompt's generator is invoked with the generation prompt body as-is.
- Each subsequent prompt's generator is invoked with every prior approved artifact prepended as context, followed by the generation prompt body.
- Each prompt's judge is invoked in a **separate Claude session** with the validation prompt body, followed by the artifact the generator just produced, followed by the VERDICT instruction.
- If the judge returns *VERDICT: revise*, the generator is resumed with the judge's feedback and produces a revised artifact. The judge is then resumed to re-evaluate. Up to *--max-iterations* (default 3).
- If the judge returns *VERDICT: escalate* or the iteration cap is reached, the pipeline halts and the remaining prompts are skipped.

Generator and judge **never** share a Claude session — they are always separate processes with separate session IDs.

## Writing good validation prompts

Your validation prompt is what the judge sees on every iteration. When the generator needs to revise, the only feedback it gets is whatever the judge wrote. Good validation prompts:

- List specific, checkable criteria (not "be thorough" or "use good judgement").
- Ask the judge to point at specific parts of the artifact that fail (line numbers, section names).
- Explain what a "revise" feedback should contain — the generator will act on it verbatim.

## Parser error IDs

If the parser rejects your file, it prints one of these error IDs and a friendly repair instruction:

- **E-NO-BLOCKS** — a prompt heading was found but no code blocks followed before the next heading or end of file.
- **E-MISSING-VALIDATION** — the generation prompt was found but no validation prompt followed.
- **E-UNCLOSED-GENERATION** — the generation prompt's code block was opened but never closed.
- **E-UNCLOSED-VALIDATION** — the validation prompt's code block was opened but never closed.
- **E-EXTRA-BLOCK** — more than two code blocks were found inside a single prompt section.

## Running the tool

Once your file is ready:

```bash
prompt-runner parse your-file.md
```

verifies that the parser accepts it. Then:

```bash
prompt-runner run your-file.md
```

executes the full pipeline. See *prompt-runner run --help* for options.

## Known limitations (v1)

- Code blocks inside prompt bodies must not use triple backticks — indent them instead.
- All prompts run sequentially; no parallelism.
- On failure, the only escalation policy is *halt* — the runner does not automatically re-route to a prior phase.
- Interrupted runs cannot be resumed; re-run the tool from the beginning.
