# PR-014 — Methodology autopilot supervisor

This prompt-runner file supervises the child autopilot scaffold in
`{{CHILD_PROMPT}}`.

It is intentionally higher level:

- Prompt 1 tightens the child scaffold if needed.
- Prompt 2 runs the child scaffold in a clean workspace/output area.
- The judge checks whether the child run completed or escalated.
- If the child run escalated, the supervisor revises and retries.

Expected usage:

```
PYTHONPATH=src/cli python -m prompt_runner run \
  docs/prompts/PR-014-methodology-autopilot-supervisor.md \
  --project-dir /Users/martinbechard/dev/agent-runner \
  --backend codex
```

---

## Prompt 1: Tighten the child autopilot scaffold

```
Your task is to inspect the latest child-run failure evidence and
decide whether `{{CHILD_PROMPT}}` actually
needs another edit.

Read:

- {{CHILD_PROMPT}}
- {{EVIDENCE_RUN}}/prompt-03-prepare-the-next-autonomous-execution-note/iter-01-judge.md
- {{EVIDENCE_RUN}}/prompt-03-prepare-the-next-autonomous-execution-note/iter-02-generator.md
- {{EVIDENCE_RUN}}/prompt-03-prepare-the-next-autonomous-execution-note/iter-02-judge.md

Write:

- {{CHILD_PROMPT}}

Task:

Only revise the child scaffold if the latest evidence shows a real flaw
in PR-013 itself.

If a PR-013 edit is needed:

- Explicitly forbid inventing temp paths, workspace paths, seed input
  files, runner commands, or generated artifact locations unless those
  exact details are already present in the source documents or on disk.
- Require unknown execution details to remain under
  `Blocking unknowns`.
- Require concrete references to come only from files actually read by
  the prompt.
- Keep the existing overall structure of PR-013 intact.

If no PR-013 edit is needed:

- Leave `{{CHILD_PROMPT}}` unchanged.
- Respond with a short note stating that no scaffold edit was required
  and why.

Rules:

- Edit the actual file, not a copy.
- Do not change `{{CHILD_PROMPT}}` just to restate rules that are already present.
- Do not weaken the completion criteria.
- Keep the prompt short and operational.

When finished, respond with a short note stating either:
- what was tightened, or
- why no change was required.
```

```
Read:

- {{CHILD_PROMPT}}
- {{EVIDENCE_RUN}}/prompt-03-prepare-the-next-autonomous-execution-note/iter-01-judge.md
- {{EVIDENCE_RUN}}/prompt-03-prepare-the-next-autonomous-execution-note/iter-02-judge.md

Judge whether Prompt 1 actually addressed the failure mode.

Pass only if:

- either:
  - the child scaffold was correctly improved to address a real PR-013
    flaw shown by the evidence, or
  - the generator correctly left PR-013 unchanged because the current
    failure is outside PR-013
- the prompt still preserves the original completion intent

If anything is still weak, say exactly what is missing.

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 2: Run the child autopilot scaffold in isolation

```
You are supervising a child prompt-runner run.

Read:

- {{CHILD_PROMPT}}
- {{project_dir}}/docs/plans/2026-04-12-pr013-supervisor-last-run.md

Child run locations:

- workspace: `{{CHILD_WORKSPACE}}`
- output: `{{CHILD_OUTPUT}}`

Decision rule before running anything:

1. Inspect the existing child run state if those paths already exist.
2. If the existing child run already contains passed earlier prompts and
   the known failure is in a later prompt, preserve the workspace/output
   and resume the child run instead of recreating it.
3. Only do a clean restart if one of these is true:
   - there is no existing child run
   - the existing child run is too incomplete to resume usefully
   - Prompt 1 changed in a way that invalidates earlier child outputs
   - the previous child workspace/output is corrupted or unreadable

Execution rules:

- Prefer resume over restart when the previous failure was late.
- If resuming, use the real existing child run/output path rather than
  inventing a new one.
- If restarting clean, remove any prior supervisor child workspace/output,
  recreate them, copy the repository into the supervised workspace using
  rsync while excluding generated or recursive directories, then launch
  the child run.
- If restarting clean, exclude:
  - `.git/`
  - `runs/`
  - `tmp/`
  - `.venv/`
  - `.pytest_cache/`
  - `__pycache__/`

Child run command:

- fresh run:
  `PYTHONPATH=src/cli python -m prompt_runner run {{CHILD_PROMPT}} --project-dir {{CHILD_WORKSPACE}} --output-dir {{CHILD_OUTPUT}} --backend codex`
- resume run:
  `PYTHONPATH=src/cli python -m prompt_runner run {{CHILD_PROMPT}} --project-dir {{CHILD_WORKSPACE}} --output-dir {{CHILD_OUTPUT}} --backend codex --resume {{CHILD_OUTPUT}}`

After the command finishes, write a short markdown report to:

- {{project_dir}}/docs/plans/2026-04-12-pr013-supervisor-last-run.md

The report must include:

1. child run path
2. whether it finished or halted
3. which prompts passed
4. whether any prompt escalated
5. the most useful next action
6. whether this attempt used fresh-run or resume mode

Rules:

- Use the real shell command, not a hypothetical summary.
- Base the report only on artifacts produced by the child run.
- If the child run halts, record the halt accurately.
- Say explicitly why you chose resume or restart.
```

```
Read:

- {{project_dir}}/docs/plans/2026-04-12-pr013-supervisor-last-run.md
- {{CHILD_OUTPUT}}/manifest.json

If present, also inspect:

- `{{CHILD_OUTPUT}}/prompt-01-complete-pr-011-outputs/final-verdict.txt`
- `{{CHILD_OUTPUT}}/prompt-02-complete-pr-012-outputs/final-verdict.txt`
- `{{CHILD_OUTPUT}}/prompt-03-prepare-the-next-autonomous-execution-note/final-verdict.txt`

Judge whether the child run succeeded.

Pass only if:

- the child run completed without halt
- prompt 1 passed
- prompt 2 passed
- prompt 3 passed
- the supervisor report states that accurately

If the child run halted or any prompt escalated, revise and say exactly
what failed so the next generator can tighten PR-013 again.

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
