# PR-017 — Methodology standalone step harness

Reusable prompt file for designing and validating the infrastructure
that replays one methodology step in isolation from a trusted baseline
workspace.

Required placeholders:

- `{{run_dir}}`
- `{{project_dir}}`

---

## Prompt 1: Choose the first target step and define the fixed input bundle

```required-files
{{run_dir}}/current-focus.md
{{run_dir}}/integration-readiness.md
{{run_dir}}/methodology-baseline-workspace/.methodology-runner/summary.txt
{{run_dir}}/methodology-baseline-workspace/timeline.html
```

```
Read:

- {{run_dir}}/current-focus.md
- {{run_dir}}/integration-readiness.md
- {{run_dir}}/methodology-baseline-workspace/.methodology-runner/summary.txt
- {{run_dir}}/methodology-baseline-workspace/timeline.html

Write:

- {{run_dir}}/step-harness/target-step.md

Task:

Choose one methodology phase to replay first in isolation and define the
fixed input bundle that every variant for that phase must share.

Required sections:

1. Target Phase
2. Why This Phase First
3. Fixed Input Files
4. Fixed Workspace State
5. Comparison Metrics

Rules:

- Choose only one target phase.
- Base the choice on the baseline evidence, not intuition.
- The fixed input bundle must be explicit enough that another tool can
  replay the phase without guessing.
```

```
Read:

- {{run_dir}}/step-harness/target-step.md

Pass only if:

- exactly one target phase is chosen
- the phase choice is justified by baseline evidence
- the fixed input bundle is explicit
- comparison metrics include quality, time, and cost

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 2: Define the standalone harness execution path

```required-files
{{run_dir}}/step-harness/target-step.md
{{project_dir}}/scripts/run_methodology_step_harness.py
```

```
Read:

- {{run_dir}}/step-harness/target-step.md
- {{project_dir}}/scripts/run_methodology_step_harness.py

Write:

- {{run_dir}}/step-harness/harness-plan.md

Task:

Write a concrete harness plan that explains how to use
`scripts/run_methodology_step_harness.py` to replay the chosen phase in
isolation from the trusted baseline workspace.

Required sections:

1. Baseline Workspace
2. Harness Output Directory
3. Replay Command
4. Expected Outputs
5. Comparison Procedure

Rules:

- Use the existing harness script instead of inventing a new execution path.
- The replay command must name the target phase.
- Expected outputs must be concrete files or directories.
- Comparison procedure must explain how results will be compared to the baseline.
```

```
Read:

- {{run_dir}}/step-harness/harness-plan.md

Pass only if:

- all five sections exist
- the replay command is concrete
- expected outputs are inspectable
- the plan relies on the harness script rather than invented workflow

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

## Prompt 3: Validate the harness once

```required-files
{{run_dir}}/step-harness/target-step.md
{{run_dir}}/step-harness/harness-plan.md
{{run_dir}}/methodology-baseline-workspace/.methodology-runner/state.json
```

```
Read:

- {{run_dir}}/step-harness/target-step.md
- {{run_dir}}/step-harness/harness-plan.md

Extract the target phase from `target-step.md`, then run the harness
once against the trusted baseline workspace:

`PYTHONPATH=src/cli python scripts/run_methodology_step_harness.py --baseline-workspace {{run_dir}}/methodology-baseline-workspace --phase <TARGET_PHASE> --output-dir {{run_dir}}/step-harness/replay-<TARGET_PHASE> --backend codex`

After the command finishes, write:

- {{run_dir}}/step-harness/harness-validation.md

Required sections:

1. Target Phase
2. Replay Output Directory
3. Whether The Replay Completed
4. Inspectable Outputs
5. Remaining Gaps

Rules:

- Use the real harness command.
- Base the validation note only on the actual replay outputs.
- If the replay failed, record the failure accurately instead of guessing.
```

```
Read:

- {{run_dir}}/step-harness/harness-validation.md

Pass only if:

- all five sections exist
- the validation note accurately states whether the replay completed
- the listed outputs are concrete and inspectable
- any remaining harness gap is explicit

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
