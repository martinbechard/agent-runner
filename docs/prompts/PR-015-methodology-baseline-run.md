# PR-015 — Methodology baseline run

Reusable prompt file for establishing one trusted full methodology-runner
baseline run that later planning and step labs can depend on.

Required placeholders:

- `{{run_dir}}`
- `{{project_dir}}`

---

## Prompt 1: Establish or repair the trusted baseline run

```required-files
{{run_dir}}/raw-request.md
```

```
Your task is to establish a trusted full methodology-runner baseline run
from the raw request at `{{run_dir}}/raw-request.md`.

Use these paths:

- baseline workspace: `{{run_dir}}/methodology-baseline-workspace`
- baseline note: `{{run_dir}}/baseline-methodology-run.md`
- baseline status: `{{run_dir}}/baseline-status.json`
- baseline timeline: `{{run_dir}}/methodology-baseline-workspace/timeline.html`
- baseline summary: `{{run_dir}}/methodology-baseline-workspace/.methodology-runner/summary.txt`

Rules:

- Run this deterministic baseline command first:
  `PYTHONPATH=src/cli python scripts/run_methodology_baseline.py --run-dir {{run_dir}} --backend codex --model gpt-5.4`
- That script is responsible for:
  - choosing fresh run vs resume
  - running or resuming methodology-runner
  - generating the timeline report
  - writing `{{run_dir}}/baseline-status.json`
  - writing `{{run_dir}}/baseline-methodology-run.md`
- If the script returns non-zero, inspect `{{run_dir}}/baseline-status.json`
  and `{{run_dir}}/baseline-methodology-run.md` before deciding whether any
  concrete local repair is needed.

- Use the real shell commands.
- Prefer grounded repair over speculative edits.
- Do not claim the baseline is trusted unless `baseline-status.json`
  reports `"trusted": true`.
```

```
Read:

- {{run_dir}}/baseline-status.json
- {{run_dir}}/baseline-methodology-run.md
- {{run_dir}}/methodology-baseline-workspace/.methodology-runner/state.json
- {{run_dir}}/methodology-baseline-workspace/.methodology-runner/summary.txt
- {{run_dir}}/methodology-baseline-workspace/timeline.html

Pass only if:

- `baseline-status.json` exists
- `baseline-status.json` reports a trusted baseline accurately
- the baseline workspace exists
- the methodology-runner run completed without halt
- the summary file exists
- the timeline file exists
- the baseline note states those facts accurately

If anything is missing or incomplete, specify exactly what still blocks
trusting the baseline.

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
