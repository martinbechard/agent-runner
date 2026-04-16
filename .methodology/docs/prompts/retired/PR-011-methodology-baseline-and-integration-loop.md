# PR-011 — Methodology baseline and integration loop

High-level prompt-runner file for autonomous methodology-runner
optimization work. This is not the detailed step-lab. It is the
integration-level guide: establish a strong baseline, summarize the
results, and later rerun with selected optimizations.

Required placeholders:

- `{{run_dir}}`
- `{{project_dir}}`

Expected usage:

```
prompt-runner run docs/prompts/PR-011-methodology-baseline-and-integration-loop.md \
  --project-dir /Users/martinbechard/dev/agent-runner
```

The operator or agent should ensure the target request file and any
candidate experiment artifacts already exist before using this file.

---

## Prompt 1: Validate optimization context

```
Read these files and confirm they exist and are non-empty:

1. {{run_dir}}/raw-request.md
2. {{project_dir}}/docs/plans/2026-04-12-methodology-optimization-loop.md

If `{{run_dir}}/summary.txt` exists, also read it and use it as supporting
context. If it does not exist, state that no prior run summary is
available yet.

Then respond with:

- whether the required files are present
- one short sentence on what the current optimization objective is

If any required file is missing, say exactly which one is missing.
```

```
Check the response.

Pass if:
- the required files are confirmed present
- the objective is correctly stated as methodology-runner optimization

Revise if:
- any file is missing
- the objective is misstated

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 2: Baseline or integration planning note

```
You are writing a short planning note for the current stage of the
methodology optimization loop.

Use the same validated context established in Prompt 1.

Required context:

- {{project_dir}}/docs/plans/2026-04-12-methodology-optimization-loop.md
- {{run_dir}}/raw-request.md

If present, also read:

- {{run_dir}}/summary.txt

Write:

- {{run_dir}}/current-focus.md

Task:

Produce a concise markdown note with these sections:

1. Current Stage
2. Baseline Facts
3. Highest-Priority Bottlenecks
4. Next Experiments
5. Promotion Rule

Rules:

- Use only concrete facts that appear in the source documents.
- Treat the request file as the statement of what this run is trying to
  achieve.
- Treat the optimization loop document as the method and decision
  process for this run.
- When a conclusion depends on a fact, say why briefly.
- Do not invent timings, costs, or experiment results.
- Keep the note short and operational.

Write the full file to
{{run_dir}}/current-focus.md.
```

```
Read the planning note and check:

- it has all five required sections
- it stays grounded in the source documents
- it is operational rather than essay-like

If yes: VERDICT: pass
If sections are missing or it invents facts: VERDICT: revise

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 3: Integration readiness checklist

```
You are preparing an integration readiness checklist for the next
end-to-end methodology run.

Use the same validated context established in Prompt 1, plus the
planning note created in Prompt 2.

Required context:

- {{project_dir}}/docs/plans/2026-04-12-methodology-optimization-loop.md
- {{run_dir}}/raw-request.md
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
- Keep the checklist concrete.
- Treat the request file as the problem statement the next full run
  must still satisfy.
- Treat the optimization loop document as the governing method for what
  counts as readiness.
- Do not claim a step-level winner exists unless the source documents
  already support it.

Write the full file.
```

```
Read the checklist and verify:

- all five sections exist
- checklist items are concrete
- unsupported claims are not made

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
