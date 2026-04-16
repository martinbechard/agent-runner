# PR-013 — Methodology optimization autopilot

Use this prompt-runner file when the goal is to let the agent keep
making structured optimization progress with minimal human supervision.

This file does not attempt to optimize methodology-runner directly in
one step. Instead, it forces completion of the planning and experiment
design layers first, in sequence, with judge-enforced completion gates.

Required placeholders:

- `{{run_dir}}`
- `{{project_dir}}`

Expected usage:

```
prompt-runner run docs/prompts/PR-013-methodology-autopilot.md \
  --project-dir /Users/martinbechard/dev/agent-runner
```

---

## Prompt 1: Complete PR-011 outputs

```
Your task is to fully complete the work described by
docs/prompts/PR-011-methodology-baseline-and-integration-loop.md.

Do not merely summarize that file. Carry out the work it describes
inside the repository until the required output files exist and are
substantively complete.

Read:

- docs/prompts/PR-011-methodology-baseline-and-integration-loop.md
- {{project_dir}}/docs/plans/2026-04-12-methodology-optimization-loop.md

Required outputs to create or update:

- {{run_dir}}/current-focus.md
- {{run_dir}}/integration-readiness.md

Rules:

- Treat PR-011 as the operational contract for this step.
- Do not stop after analysis; write the files.
- Keep the outputs concise and operational.
- Ground all claims in the source documents.
- If one output already exists but is weak or incomplete, improve it.

When finished, respond briefly with what files were completed.
```

```
Read:

- docs/prompts/PR-011-methodology-baseline-and-integration-loop.md
- {{run_dir}}/current-focus.md
- {{run_dir}}/integration-readiness.md

Judge whether Prompt 1 is actually complete.

Pass only if:

- both required files exist
- both are substantively populated
- both follow the structure required by PR-011
- neither file invents unsupported results

If anything is missing or weak, specify exactly what is incomplete.

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 2: Complete PR-012 outputs

```
Your task is to fully complete the work described by
docs/prompts/PR-012-ph000-step-lab.md.

Do not merely summarize that file. Carry out the work it describes
inside the repository until the required output files exist and are
substantively complete.

Read:

- docs/prompts/PR-012-ph000-step-lab.md
- {{project_dir}}/docs/plans/2026-04-12-methodology-optimization-loop.md
- {{run_dir}}/timeline.html
- {{run_dir}}/current-focus.md

If present, also read:

- {{run_dir}}/summary.txt

Required outputs to create or update:

- {{project_dir}}/docs/plans/2026-04-12-ph000-experiment-matrix.md
- {{project_dir}}/docs/plans/2026-04-12-ph000-result-template.md

Rules:

- Treat PR-012 as the operational contract for this step.
- Keep the matrix bounded and non-combinatorial.
- Make quality gating explicit.
- Do not fabricate experiment results.
- If a file already exists but is incomplete, improve it.

When finished, respond briefly with what files were completed.
```

```
Read:

- docs/prompts/PR-012-ph000-step-lab.md
- {{project_dir}}/docs/plans/2026-04-12-ph000-experiment-matrix.md
- {{project_dir}}/docs/plans/2026-04-12-ph000-result-template.md

Judge whether Prompt 2 is actually complete.

Pass only if:

- both required files exist
- both are substantively populated
- the experiment matrix is bounded rather than combinatorial
- the result template is reusable and blank
- the outputs follow PR-012 rather than drifting into generic prose

If anything is missing or weak, specify exactly what is incomplete.

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 3: Prepare the next autonomous execution note

```
Read:

- docs/prompts/PR-012-ph000-step-lab.md
- {{run_dir}}/current-focus.md
- {{run_dir}}/integration-readiness.md
- {{project_dir}}/docs/plans/2026-04-12-ph000-experiment-matrix.md
- {{project_dir}}/docs/plans/2026-04-12-ph000-result-template.md
- {{run_dir}}/timeline.html

If present, also read:

- {{run_dir}}/summary.txt
- src/cli/methodology_runner/prompt_generator.py
- .methodology/docs/skills-baselines.yaml
- docs/prompts/PR-003-audit-variant-test.md

Write:

- {{project_dir}}/docs/plans/2026-04-12-next-autonomous-actions.md

Task:

Create a concise operational note for the next autonomous work session.

Required sections:

1. Ready-to-run experiments
2. Required inputs
3. Blocking unknowns
4. Success criteria
5. Stop conditions

Rules:

- Keep it short and execution-oriented.
- Prefer commands, concrete files, and explicit decisions.
- Do not claim that an experiment already passed unless a source file
  explicitly supports that claim.
- Do not invent temp paths, workspace paths, seed input files, runner
  commands, or generated artifact locations unless those exact details
  are present in the files read for this prompt.
- If an execution detail is unknown from the files read for this prompt,
  put it under `Blocking unknowns` rather than guessing.
- Only cite concrete references that come directly from files actually
  read by this prompt.
```

```
Read:

- docs/prompts/PR-012-ph000-step-lab.md
- {{run_dir}}/timeline.html

If present, also read:

- {{run_dir}}/summary.txt
- src/cli/methodology_runner/prompt_generator.py
- .methodology/docs/skills-baselines.yaml
- docs/prompts/PR-003-audit-variant-test.md
- {{project_dir}}/docs/plans/2026-04-12-next-autonomous-actions.md

Judge whether the note is operationally useful.

Pass only if:

- all five required sections exist
- the note is concrete enough that a later agent can continue without
  chat context
- when the files read for this prompt provide them, the note includes
  the concrete prompt path or phase artifact path, fixed PH-000 input
  bundle path, runner command or explicitly named missing command,
  and validator or rubric reference needed for the next step
- any execution detail still unknown from the files read for this prompt
  is placed under `Blocking unknowns` rather than guessed
- unsupported claims are not made

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
