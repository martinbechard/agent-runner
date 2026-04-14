# PR-020 — Methodology optimization supervisor

This prompt-runner file supervises the methodology optimization
workflow in `{{workflow_prompt}}`.

---

## Prompt 1: Tighten the optimization workflow only if the evidence shows a real prompt defect

```
Your task is to inspect the latest workflow-run evidence, if any exists,
and decide whether `{{workflow_prompt}}` actually needs another edit.

Read:

- {{workflow_prompt}}

If these files exist, also read them:

- {{workflow_run_dir}}/prompt-01-complete-the-trusted-baseline-run/final-verdict.txt
- {{workflow_run_dir}}/prompt-02-complete-the-planning-preparation-outputs/final-verdict.txt
- {{workflow_run_dir}}/prompt-03-complete-the-standalone-step-harness-outputs/final-verdict.txt
- {{workflow_run_dir}}/prompt-04-complete-the-step-lab-planning-outputs/final-verdict.txt

Write:

- {{workflow_prompt}}

Task:

Only revise the optimization workflow if the latest evidence shows a
real flaw in the workflow prompt instructions themselves.

If no prompt edit is needed:

- leave `{{workflow_prompt}}` unchanged
- respond briefly saying why no change was required

Rules:

- Edit the actual workflow prompt file, not a copy.
- Do not change the workflow prompt just to restate rules that are already present.
- Keep the workflow prompt short and operational.
```

```
Read:

- {{workflow_prompt}}

Pass only if:

- either the workflow prompt was correctly improved to address a real prompt defect, or
- it was correctly left unchanged because the current failure is outside the prompt text

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 2: Run or resume the optimization workflow

```
You are supervising an optimization workflow prompt-runner run.

Read:

- {{workflow_prompt}}

Optimization workflow run locations:

- project dir: `{{project_dir}}`
- run dir: `{{workflow_run_dir}}`

Decision rule:

1. If the workflow run directory already contains passed earlier prompts and a later
   prompt failed, resume the workflow run instead of restarting it.
2. Only do a clean restart if there is no usable workflow run or the workflow
   prompt changed in a way that invalidates earlier workflow outputs.

Execution rules:

- Prefer resume over restart when the previous failure was late.
- If restarting clean, remove the old child output directory, recreate it,
  and copy `{{raw_request}}` to `{{workflow_run_dir}}/raw-request.md`.

Workflow run command:

- fresh run:
  `PYTHONPATH=src/cli python -m prompt_runner run {{workflow_prompt}} --project-dir {{project_dir}} --output-dir {{workflow_run_dir}} --backend codex --no-project-organiser`
- resume run:
  `PYTHONPATH=src/cli python -m prompt_runner run {{workflow_prompt}} --project-dir {{project_dir}} --output-dir {{workflow_run_dir}} --backend codex --resume {{workflow_run_dir}} --no-project-organiser`

After the command finishes, write:

- {{run_dir}}/supervisor-last-run.md

The report must include:

1. workflow run path
2. whether it finished or halted
3. which prompts passed
4. whether any prompt escalated
5. the most useful next action
6. whether this attempt used fresh-run or resume mode
```

```
Read:

- {{run_dir}}/supervisor-last-run.md
- {{workflow_run_dir}}/manifest.json

If present, also inspect:

- {{workflow_run_dir}}/baseline-status.json
- {{workflow_run_dir}}/prompt-01-complete-the-trusted-baseline-run/final-verdict.txt
- {{workflow_run_dir}}/prompt-02-complete-the-planning-preparation-outputs/final-verdict.txt
- {{workflow_run_dir}}/prompt-03-complete-the-standalone-step-harness-outputs/final-verdict.txt
- {{workflow_run_dir}}/prompt-04-complete-the-step-lab-planning-outputs/final-verdict.txt

Pass only if:

- the workflow run completed without halt
- prompt 1 passed
- prompt 2 passed
- prompt 3 passed
- prompt 4 passed
- the supervisor report states that accurately

If the workflow run halted or any prompt escalated, revise and say exactly
what failed.

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
