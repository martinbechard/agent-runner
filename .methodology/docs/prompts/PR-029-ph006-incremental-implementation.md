### Module

incremental-implementation

## Prompt 1: Produce Incremental Implementation Workflow

### Required Files

docs/design/interface-contracts.yaml
docs/simulations/simulation-definitions.yaml
docs/features/feature-specification.yaml
docs/design/solution-design.yaml

### Include Files

docs/design/interface-contracts.yaml
docs/simulations/simulation-definitions.yaml
docs/features/feature-specification.yaml
docs/design/solution-design.yaml

### Checks Files

docs/implementation/implementation-workflow.md

### Deterministic Validation

.methodology/src/cli/methodology_runner/phase_6_validation.py
--workflow-prompt
docs/implementation/implementation-workflow.md

### Generation Prompt

As an implementation workflow author, you must write a child prompt-runner
workflow that incrementally builds the real implementation and writes it to
docs/implementation/implementation-workflow.md.

The interface contracts are provided above in <INTERFACE_CONTRACTS>.
The simulations are provided above in <SIMULATION_DEFINITIONS>.
The feature specification is provided above in <FEATURE_SPECIFICATION>.
The solution design is provided above in <SOLUTION_DESIGN>.

Phase purpose:
- Turn the approved design into a granular implementation workflow.
- Break the implementation into prompt-runner prompts that each build one
  small TDD slice.
- Require each slice to write or update real project files and run the
  relevant tests before moving on.
- End with a final child-workflow prompt that runs the full verification
  commands for the implemented system.

Important implementation discipline:
- This phase is planning the implementation workflow, not writing another
  abstract specification layer.
- The child workflow must produce real code, tests, and project files in the
  project worktree.
- Each child prompt must follow TDD discipline:
  1. write or tighten a failing test when a new behavior is introduced
  2. implement the smallest code change that makes that test pass
  3. run the relevant tests and record the result in the prompt output
- Keep each child prompt small enough that a failure is local and obvious.
- Do not create separate planning tables when the same information can be
  expressed directly as prompt order and prompt instructions.

Output contract:
- Write one prompt-runner markdown file at
  docs/implementation/implementation-workflow.md.
- The file must be a valid prompt-runner workflow with a file-level module.
- The workflow must contain at least:
  - one implementation prompt that introduces the first executable slice
  - one later implementation prompt that extends or completes the system
  - one final verification prompt that runs the full verification commands
- Each child prompt must contain both a Generation Prompt and a Validation
  Prompt.
- Each implementation child prompt must:
  - name the concrete project files it is expected to create or update
  - require relevant tests to be run in the same prompt
  - stay grounded in FT-* / AC-* / CMP-* / CTR-* / SIM-* references when they
    materially affect the slice

Required child-workflow shape:
- begin with a file-level module block whose slug is
  `implementation-workflow`
- define at least two prompt sections
- for each prompt section, include:
  - required files when they materially matter
  - checks files when the slice writes a durable artifact
  - a generation prompt
  - a validation prompt
- make the last prompt the final verification step

Acceptance requirements:
- The file must be valid markdown parseable by prompt-runner.
- The file must begin with a file-level `### Module` block.
- The module slug must be `implementation-workflow`.
- The workflow must contain at least 2 prompts.
- At least one implementation prompt must explicitly require a failing or
  tightened test before code changes.
- At least one implementation prompt must explicitly run tests after code
  changes.
- The final prompt must explicitly run the full verification commands for the
  implemented system.
- The workflow must stay grounded in the upstream artifacts. Do not invent
  unrelated files, frameworks, or infrastructure.
- Do not create any files other than docs/implementation/implementation-workflow.md.
- Write the full file contents to docs/implementation/implementation-workflow.md.

### Validation Prompt

Review the current child implementation workflow against
<INTERFACE_CONTRACTS>, <SIMULATION_DEFINITIONS>, <FEATURE_SPECIFICATION>, and
<SOLUTION_DESIGN>. The current artifact is provided above in
<IMPLEMENTATION_WORKFLOW>.

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Your job is to decide whether the child implementation workflow is phase-ready.

Review method:
- Iterate through the child prompts in authored order.
- For each prompt, review whether it defines one concrete implementation slice
  that would materially advance the system.
- Before flagging a slice, test, or verification step as missing, check
  whether that same downstream-actionable implementation meaning is already
  covered by another child prompt in the workflow.
- Only flag it as missing if the allegedly missing content would change the
  actual implementation work, testing cadence, or final verification outcome.

Focus your semantic review on these failure modes:

1. Non-executable workflow:
   - Flag child prompts that only describe work abstractly and do not direct
     real file edits or real test execution.
2. Broken TDD cadence:
   - Flag child prompts that add code without first adding or tightening the
     test that defines the new behavior.
3. Overlarge slices:
   - Flag prompts that bundle too much unrelated implementation work into one
     step.
4. Traceability gaps:
   - Flag child prompts whose implementation work is not materially grounded in
     the upstream FT-* / AC-* / CMP-* / CTR-* / SIM-* artifacts.
5. Missing final verification:
   - Flag workflows that do not end with a prompt that runs the full
     verification commands against the completed implementation.

Review instructions:
- Treat this phase as workflow authoring for real implementation, not as a
  place to demand more planning prose.
- Only ask for a change when the current workflow is wrong, contradictory,
  materially unsupported, or would materially weaken downstream implementation
  execution.
- Do not request wording polish or alternative prompt titles unless the
  current wording is misleading or materially consequential.
- If you find issues, cite exact FT-* / AC-* / CMP-* / CTR-* / SIM-* IDs when
  available.
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary
- Use VERDICT: pass only if the workflow is ready to be executed by a child
  prompt-runner run.
- Use VERDICT: revise if the workflow can be corrected within this same file.
- Use VERDICT: escalate only if the upstream artifacts are too ambiguous to
  support a stable implementation workflow.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate

## Prompt 2: Run The Child Implementation Workflow

### Required Files

docs/implementation/implementation-workflow.md

### Include Files

docs/implementation/implementation-workflow.md

### Checks Files

docs/implementation/implementation-run-report.yaml

### Deterministic Validation

.methodology/src/cli/methodology_runner/phase_6_validation.py
--workflow-prompt
docs/implementation/implementation-workflow.md
--run-report
docs/implementation/implementation-run-report.yaml
--check-run-report

### Generation Prompt

As an implementation supervisor, you must run or resume the child
implementation workflow and write a truthful execution report to
docs/implementation/implementation-run-report.yaml.

The child workflow prompt is provided above in <IMPLEMENTATION_WORKFLOW>.

Use this prompt-runner command base:
`{{prompt_runner_command}}`

Current project worktree:
`{{run_dir}}`

Execution rules:
- The child workflow must operate on the current project worktree, not on a
  hypothetical copy.
- If the child workflow already has useful progress in this worktree, resume
  it with:
  `{{prompt_runner_command}} run docs/implementation/implementation-workflow.md --run-dir {{run_dir}} --resume {{run_dir}}`
- Otherwise run it fresh with:
  `{{prompt_runner_command}} run docs/implementation/implementation-workflow.md --run-dir {{run_dir}}`
- Always parse the child workflow first:
  `{{prompt_runner_command}} parse docs/implementation/implementation-workflow.md`
- Do not fabricate child-run outcomes. Base the report only on artifacts the
  child run actually produced in this worktree.
- The child workflow is allowed to create or update real project files such as
  source code, tests, and README content.

Execution report schema:
```yaml
child_prompt_path: "docs/implementation/implementation-workflow.md"
child_run_dir: "{{run_dir}}"
execution_mode: "fresh"
completion_status: "completed"
halt_reason: ""
prompt_results:
  - prompt_index: 1
    title: "Prompt title"
    verdict: "pass"
    iterations: 1
files_changed:
  - "relative/path"
test_commands_observed:
  - command: "pytest -q"
    exit_code: 0
next_action: "none"
```

Acceptance requirements:
- The file must be valid YAML parseable by a standard YAML parser.
- The top-level keys must appear exactly in this order:
  child_prompt_path
  child_run_dir
  execution_mode
  completion_status
  halt_reason
  prompt_results
  files_changed
  test_commands_observed
  next_action
- execution_mode must be one of:
  fresh
  resume
- completion_status must be one of:
  completed
  halted
- The report must reflect the actual child run outcome in this worktree.
- If completion_status is `completed`, every prompt_results verdict must be `pass`.
- If completion_status is `halted`, halt_reason must explain what halted.
- Do not create any files other than docs/implementation/implementation-run-report.yaml.
- Write the full file contents to docs/implementation/implementation-run-report.yaml.

### Validation Prompt

Review the current child-run report against <IMPLEMENTATION_WORKFLOW> and the
child-run artifacts already present in the worktree. The current artifact is
provided above in <IMPLEMENTATION_RUN_REPORT>.

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Your job is to decide whether the child implementation workflow has been run
successfully and reported truthfully.

Review method:
- Iterate through prompt_results in prompt_index order.
- Then review files_changed in authored order.
- Then review test_commands_observed in authored order.
- Before flagging a missing report item, check whether the same execution
  meaning is already captured elsewhere in the report.
- Only flag it as missing if the allegedly missing content would change the
  truthfulness of the child-run outcome or the usefulness of the report for
  final verification.

Focus your semantic review on these failure modes:

1. False completion:
   - Flag reports that claim completion even though the child workflow halted
     or left prompts unpassed.
2. Invented evidence:
   - Flag reported files or test commands that are not grounded in the actual
     child-run artifacts.
3. Missing execution evidence:
   - Flag reports that hide materially relevant changed files or test commands.
4. Misleading next action:
   - Flag `next_action` values that do not match the real child-run state.

Review instructions:
- Treat this prompt as an execution-supervision layer.
- Pass only if the child run completed and the report states that accurately.
- If the child run halted, do not pretend success. Escalate unless the report
- itself is merely inaccurate.
- Do not request wording polish or alternate phrasing unless the current
  wording is misleading or materially consequential.
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
