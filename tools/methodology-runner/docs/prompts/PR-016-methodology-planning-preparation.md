# PR-016 — Methodology planning preparation

Reusable prompt file for turning a trusted baseline request and baseline
run evidence into run-scoped planning artifacts.

Required placeholders:

- `{{run_dir}}`
- `{{project_dir}}`

---

## Prompt 1: Write the current-focus note

```required-files
{{run_dir}}/raw-request.md
{{run_dir}}/baseline-status.json
{{project_dir}}/docs/design/high-level/HLD-003-methodology-workflow.md
{{run_dir}}/methodology-baseline-workspace/.methodology-runner/summary.txt
{{run_dir}}/methodology-baseline-workspace/timeline.html
```

```
You are writing a short current-focus note for this optimization run.

Read:

- {{run_dir}}/raw-request.md
- {{run_dir}}/baseline-status.json
- {{project_dir}}/docs/design/high-level/HLD-003-methodology-workflow.md
- {{run_dir}}/methodology-baseline-workspace/.methodology-runner/summary.txt
- {{run_dir}}/methodology-baseline-workspace/timeline.html

Write:

- {{run_dir}}/current-focus.md

Task:

Produce a concise markdown note with these sections:

1. Current Stage
2. Grounded Baseline Facts
3. Highest-Priority Bottlenecks
4. Next Experiments
5. Promotion Rule

Rules:

- Treat the raw request as the problem statement.
- Treat `baseline-status.json` as the workflow-level statement of whether the baseline is trusted.
- Proceed only if `baseline-status.json` shows a trusted baseline.
- Treat the workflow design document as the governing method.
- Use only concrete facts from the summary and timeline.
- Explain briefly why each bottleneck or next experiment follows from
  those facts.
- Do not invent timings, costs, or experiment results.
```

```
Read:

- {{run_dir}}/current-focus.md

Pass only if:

- all five required sections exist
- the note stays grounded in the request, summary, and timeline
- the bottlenecks and next experiments are reasoned from the evidence
- the note remains short and operational

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 2: Write the integration-readiness checklist

```required-files
{{run_dir}}/raw-request.md
{{run_dir}}/baseline-status.json
{{project_dir}}/docs/design/high-level/HLD-003-methodology-workflow.md
{{run_dir}}/current-focus.md
```

```
You are preparing an integration-readiness checklist for the next full
methodology run.

Read:

- {{run_dir}}/raw-request.md
- {{run_dir}}/baseline-status.json
- {{project_dir}}/docs/design/high-level/HLD-003-methodology-workflow.md
- {{run_dir}}/current-focus.md

Write:

- {{run_dir}}/integration-readiness.md

Task:

Create a markdown checklist with these sections:

1. Baseline locked
2. Step-level winners selected
3. Report instrumentation ready
4. Integration risks
5. Success criteria for the next full run

Rules:

- Phrase items as checkboxes.
- Treat the request as the problem statement the next full run must still satisfy.
- Treat `baseline-status.json` as the workflow-level statement of baseline trust.
- Treat the workflow design document as the governing method for what
  counts as readiness.
- Distinguish completed evidence from unresolved risks or unknowns.
- Do not claim step-level winners unless the source documents support them.
```

```
Read:

- {{run_dir}}/integration-readiness.md

Pass only if:

- all five sections exist
- checklist items are concrete
- the checklist distinguishes evidence from unresolved risk
- unsupported winner claims are not made

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
