# PR-018 — Methodology step-lab planning

Reusable prompt file for selecting bounded methodology-step variants
once a standalone step harness exists.

Required placeholders:

- `{{run_dir}}`
- `{{project_dir}}`

---

## Prompt 1: Confirm the first isolated optimization target

```required-files
{{run_dir}}/step-harness/target-step.md
{{run_dir}}/step-harness/harness-validation.md
{{run_dir}}/methodology-baseline-workspace/timeline.html
```

```
Read:

- {{run_dir}}/step-harness/target-step.md
- {{run_dir}}/step-harness/harness-validation.md
- {{run_dir}}/methodology-baseline-workspace/timeline.html

Respond with:

- the first target phase for isolated optimization
- the top three variant dimensions worth testing for that phase
- one short sentence for why each dimension matters

Rules:

- Keep the target phase fixed to the validated harness target unless the
  validation note proves that target is unusable.
- Base variant dimensions on observed cost, time, quality pressure, or
  prompt complexity.
- Avoid cross-product explosion.
```

```
Pass only if:

- one target phase is named
- exactly three variant dimensions are listed
- each reason is grounded in baseline or harness evidence

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 2: Write the bounded step-lab experiment matrix

```required-files
{{run_dir}}/current-focus.md
{{run_dir}}/step-harness/target-step.md
{{run_dir}}/step-harness/harness-validation.md
```

```
Read:

- {{run_dir}}/current-focus.md
- {{run_dir}}/step-harness/target-step.md
- {{run_dir}}/step-harness/harness-validation.md

Write:

- {{run_dir}}/step-lab-experiment-matrix.md

Task:

Produce a markdown matrix with these sections:

1. Fixed Baseline Inputs
2. Target Phase
3. Variant Dimensions
4. Candidate Variants
5. Evaluation Metrics
6. Promotion Criteria

Rules:

- Keep the matrix intentionally small.
- Group candidate variants by phase.
- Include quality, time, and cost in the evaluation metrics.
- Promotion criteria must reject quality regressions before cost or time wins.
```

```
Read:

- {{run_dir}}/step-lab-experiment-matrix.md

Pass only if:

- all six sections exist
- the matrix is bounded rather than combinatorial
- quality gating is explicit

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 3: Write the step-lab result template

```required-files
{{run_dir}}/step-lab-experiment-matrix.md
```

```
Read:

- {{run_dir}}/step-lab-experiment-matrix.md

Write:

- {{run_dir}}/step-lab-result-template.md

Task:

Create a reusable markdown result template with these sections:

1. Variant Identity
2. Fixed Inputs
3. Observed Quality Result
4. Time Result
5. Cost Result
6. Verdict
7. Notes On Failure Modes

Rules:

- Make it easy to compare variants side by side later.
- Keep it blank and reusable.
- Do not fill in actual results.
```

```
Read:

- {{run_dir}}/step-lab-result-template.md

Pass only if:

- all seven sections exist
- the template is blank and reusable
- it supports later comparison

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
