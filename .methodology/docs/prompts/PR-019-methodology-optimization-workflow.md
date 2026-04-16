# PR-019 — Methodology optimization workflow

Use this prompt-runner file to execute the methodology optimization
workflow stages in order from one trusted baseline run through step-lab
planning.

Required placeholders:

- `{{run_dir}}`
- `{{project_dir}}`

---

## Prompt 1: Complete the trusted baseline run

```
Your task is to fully complete the work described by
docs/prompts/PR-015-methodology-baseline-run.md.

Do not merely summarize that file. Carry out the work it describes
inside the repository until the baseline workspace and baseline note are
substantively complete.

Read:

- docs/prompts/PR-015-methodology-baseline-run.md
- {{run_dir}}/raw-request.md

Required outputs to create or update:

- {{run_dir}}/methodology-baseline-workspace
- {{run_dir}}/baseline-status.json
- {{run_dir}}/baseline-methodology-run.md

Rules:

- Treat PR-015 as the operational contract for this step.
- Use the real baseline runner script described by PR-015.
- If the baseline is incomplete, repair and rerun rather than stopping at analysis.
- Do not claim the baseline is trusted unless the run completed and the note states that accurately.
```

```
Read:

- docs/prompts/PR-015-methodology-baseline-run.md
- {{run_dir}}/baseline-status.json
- {{run_dir}}/baseline-methodology-run.md
- {{run_dir}}/methodology-baseline-workspace/.methodology-runner/summary.txt
- {{run_dir}}/methodology-baseline-workspace/timeline.html

Pass only if:

- the baseline status file exists
- the baseline status file reports a trusted baseline accurately
- the baseline note exists
- the methodology baseline workspace exists
- the summary exists
- the timeline exists
- the outputs satisfy PR-015

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 2: Complete the planning-preparation outputs

```
Your task is to fully complete the work described by
docs/prompts/PR-016-methodology-planning-preparation.md.

Read:

- docs/prompts/PR-016-methodology-planning-preparation.md
- {{run_dir}}/raw-request.md
- {{run_dir}}/baseline-methodology-run.md

Required outputs to create or update:

- {{run_dir}}/current-focus.md
- {{run_dir}}/integration-readiness.md

Rules:

- Treat PR-016 as the operational contract for this step.
- Ground all claims in the request and baseline evidence.
- If an output exists but is weak, improve it.
```

```
Read:

- docs/prompts/PR-016-methodology-planning-preparation.md
- {{run_dir}}/current-focus.md
- {{run_dir}}/integration-readiness.md

Pass only if:

- both required files exist
- both are substantively populated
- both satisfy PR-016

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 3: Complete the standalone step-harness outputs

```
Your task is to fully complete the work described by
docs/prompts/PR-017-methodology-standalone-step-harness.md.

Read:

- docs/prompts/PR-017-methodology-standalone-step-harness.md
- {{run_dir}}/current-focus.md
- {{run_dir}}/integration-readiness.md

Required outputs to create or update:

- {{run_dir}}/step-harness/target-step.md
- {{run_dir}}/step-harness/harness-plan.md
- {{run_dir}}/step-harness/harness-validation.md

Rules:

- Treat PR-017 as the operational contract for this step.
- Use the real step harness script when validating the harness.
- Keep the harness outputs concrete and inspectable.
```

```
Read:

- docs/prompts/PR-017-methodology-standalone-step-harness.md
- {{run_dir}}/step-harness/target-step.md
- {{run_dir}}/step-harness/harness-plan.md
- {{run_dir}}/step-harness/harness-validation.md

Pass only if:

- all three required files exist
- they are substantively populated
- they satisfy PR-017

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 4: Complete the step-lab planning outputs

```
Your task is to fully complete the work described by
docs/prompts/PR-018-methodology-step-lab-planning.md.

Read:

- docs/prompts/PR-018-methodology-step-lab-planning.md
- {{run_dir}}/step-harness/target-step.md
- {{run_dir}}/step-harness/harness-validation.md
- {{run_dir}}/current-focus.md

Required outputs to create or update:

- {{run_dir}}/step-lab-experiment-matrix.md
- {{run_dir}}/step-lab-result-template.md

Rules:

- Treat PR-018 as the operational contract for this step.
- Keep the matrix bounded.
- Keep the result template blank and reusable.
```

```
Read:

- docs/prompts/PR-018-methodology-step-lab-planning.md
- {{run_dir}}/step-lab-experiment-matrix.md
- {{run_dir}}/step-lab-result-template.md

Pass only if:

- both required files exist
- both are substantively populated
- they satisfy PR-018

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
