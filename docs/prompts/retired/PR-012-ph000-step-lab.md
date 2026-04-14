# PR-012 — PH-000 step lab

Focused prompt-runner file for designing and evaluating `PH-000`
step-level experiments without drifting into full end-to-end
combinatorial search.

Required placeholders:

- `{{run_dir}}`
- `{{project_dir}}`

Expected usage:

```
prompt-runner run docs/prompts/PR-012-ph000-step-lab.md \
  --project-dir /Users/martinbechard/dev/agent-runner
```

This file is for experiment design and analysis scaffolding, not for
running methodology-runner itself.

---

## Prompt 1: Confirm PH-000 bottleneck facts

```
Read:

1. {{project_dir}}/docs/plans/2026-04-12-methodology-optimization-loop.md
2. {{run_dir}}/timeline.html

If `{{run_dir}}/summary.txt` exists, also read it as supporting context.

Respond with:

- the top three PH-000 steps worth optimizing first
- one sentence each explaining why

Rules:

- Base the answer on observed cost, timing, or both
- Do not include local orchestration-only steps unless the report
  supports that choice
```

```
Check the response.

Pass if:
- exactly three steps are listed
- each reason is grounded in cost or timing

Revise otherwise.

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 2: Design a bounded PH-000 experiment matrix

```
You are designing a small experiment matrix for PH-000 optimization.

Read:

- {{project_dir}}/docs/plans/2026-04-12-methodology-optimization-loop.md
- {{project_dir}}/docs/plans/2026-04-12-methodology-current-focus.md

If present, also read:

- {{run_dir}}/summary.txt

Write:

- {{project_dir}}/docs/plans/2026-04-12-ph000-experiment-matrix.md

Task:

Produce a markdown matrix with these sections:

1. Fixed baseline
2. Target steps
3. Variant dimensions
4. Candidate variants
5. Evaluation metrics
6. Promotion criteria

Rules:

- Keep the matrix intentionally small.
- Avoid cross-product explosion.
- Candidate variants should be grouped by step.
- Include quality, time, and cost in evaluation metrics.
- Promotion criteria must reject quality regressions before cost/time
  wins are considered.

Write the full file.
```

```
Review the experiment matrix.

Pass if:
- it is bounded rather than combinatorial
- it includes all six required sections
- quality gating is explicit

Revise otherwise.

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 3: Define the PH-000 experiment result template

```
You are creating a reusable result template for PH-000 step labs.

Read:

- {{project_dir}}/docs/plans/2026-04-12-ph000-experiment-matrix.md

Write:

- {{project_dir}}/docs/plans/2026-04-12-ph000-result-template.md

Task:

Create a markdown template with these sections:

1. Variant identity
2. Fixed inputs
3. Observed quality result
4. Time result
5. Cost result
6. Verdict
7. Notes on failure modes

Rules:

- Make it easy to compare variants side by side later.
- Keep the template generic enough to reuse across PH-000 step tests.
- Do not fill in actual results; this is a blank template.

Write the full file.
```

```
Review the result template.

Pass if:
- all seven sections exist
- it is blank and reusable
- it supports later comparison

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
