### Module

incremental-implementation

## Prompt 1: Produce Incremental Implementation Workflow

### Required Files

docs/design/interface-contracts.yaml
docs/simulations/simulation-definitions.yaml
docs/features/feature-specification.yaml
docs/design/solution-design.yaml

### Deterministic Validation

python-module:methodology_runner.phase_6_validation
--workflow-prompt
docs/implementation/implementation-workflow.md

### Generation Prompt

As an implementation workflow author, you must write a child prompt-runner
workflow that incrementally builds the real implementation and writes it to
docs/implementation/implementation-workflow.md.

Context:
<INTERFACE_CONTRACTS>
{{INCLUDE:docs/design/interface-contracts.yaml}}
</INTERFACE_CONTRACTS>
<SIMULATION_DEFINITIONS>
{{INCLUDE:docs/simulations/simulation-definitions.yaml}}
</SIMULATION_DEFINITIONS>
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>
<SOLUTION_DESIGN>
{{INCLUDE:docs/design/solution-design.yaml}}
</SOLUTION_DESIGN>

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
- The child workflow must evaluate each child prompt only against that prompt's
  own generator text and the concrete project files it creates or updates.
  It must not rely on any parent-phase execution report such as
  `docs/implementation/implementation-run-report.yaml` as evidence for child
  prompt success or failure.
- Each child prompt must follow TDD discipline:
  1. write or tighten the test that defines the new or stricter behavior
  2. run the exact test command for that slice and record a failing result
     before the corresponding implementation change
  3. implement the smallest code change that makes that same exact test
     command pass
  4. rerun that same exact test command and record the passing result
- Keep each child prompt small enough that a failure is local and obvious.
- Do not create separate planning tables when the same information can be
  expressed directly as prompt order and prompt instructions.
- Once a child prompt chooses a concrete command string, preserve that exact
  command spelling everywhere it is reused in that prompt, in later final
  verification steps, and in the supervisor report. Do not substitute an
  equivalent command variant such as changing dotted unittest module paths into
  slash paths or replacing a targeted test command with a broader discover
  command.

Output contract:
- Write one prompt-runner markdown file at
  docs/implementation/implementation-workflow.md.
- The file must be a valid prompt-runner workflow with a file-level module.
- Use the exact canonical prompt-runner heading structure used by the
  prompt-runner parser:
  - `### Module`
  - next non-empty line exactly `implementation-workflow`
  - `## Prompt 1: ...`
  - `### Required Files` when needed
  - `### Checks Files` when needed
  - `### Generation Prompt`
  - `### Validation Prompt`
- In `### Required Files` and `### Checks Files`, write one bare relative path
  per non-empty line.
- Do not format path entries as markdown bullets or code spans. For example,
  write `docs/features/feature-specification.yaml`, not
  `- \`docs/features/feature-specification.yaml\``.
- Do not invent alternate child-workflow heading shapes such as:
  - `### Prompt`
  - `#### Slug`
  - `#### Generation Prompt`
  - `#### Validation Prompt`
- The workflow must contain at least:
  - one implementation prompt that introduces the first executable slice
  - one later implementation prompt that extends or completes the system
  - one final verification prompt that runs the full verification commands
- Each child prompt must contain both a Generation Prompt and a Validation
  Prompt.
- Each implementation child prompt must:
  - name the concrete project files it is expected to create or update
  - require the same exact relevant test command to be run before and after
    the implementation change in the same prompt
  - require an explicit generator response structure with exactly these
    section headings:
    - `## Files Created Or Updated`
    - `## Command Reports`
    - `## Slice Result Summary`
  - require every command report to preserve:
    - the exact command string as executed
    - full observed stdout
    - full observed stderr
    - exact exit code
  - stay grounded in FT-* / AC-* / CMP-* / CTR-* / SIM-* references when they
    materially affect the slice
- Each child prompt that runs commands must define a concrete response format
  that uses exactly:
  - a `## Files Created Or Updated` section listing files only
  - a `## Command Reports` section with one plain-text command-report block per
    command, not markdown headings, using these exact fields:
    - `Command: <exact command string>`
    - `Stdout:`
    - fenced code block containing the full observed stdout
    - `Stderr:`
    - fenced code block containing the full observed stderr
    - `Exit Code: <integer>`
  - a `## Slice Result Summary` section with a brief slice outcome summary
- The final verification child prompt must use the same explicit command-report
  format for its verification commands and must preserve the exact command
  strings it requires.

Required child-workflow shape:
- begin with exactly:
  - a line `### Module`
  - then the next non-empty line `implementation-workflow`
- define at least two prompt sections
- for each prompt section, include:
  - a heading exactly `## Prompt N: Title`
  - required files when they materially matter
  - checks files when the slice writes a durable artifact
  - a heading exactly `### Generation Prompt`
  - a heading exactly `### Validation Prompt`
- for each implementation child prompt, make the validation prompt review only:
  - the prompt's own generator response text
  - the files produced by that child prompt
  - the explicitly named project artifacts needed for that slice
  and explicitly exclude parent-phase supervisor artifacts such as
  `docs/implementation/implementation-run-report.yaml`
- make the last prompt the final verification step

Acceptance requirements:
- The file must be valid markdown parseable by prompt-runner.
- The file must begin with a file-level `### Module` block.
- The next non-empty line after `### Module` must be exactly
  `implementation-workflow`.
- The workflow must contain at least 2 prompts.
- Each child prompt heading must use the exact form
  `## Prompt N: Title`.
- Child prompt subsections must use the exact canonical form:
  `### Required Files`, `### Checks Files`,
  `### Generation Prompt`, and `### Validation Prompt`.
- Each `### Required Files` or `### Checks Files` section must use bare
  relative path lines only, with no markdown bullets and no backticks around
  the path values.
- At least one implementation prompt must explicitly require the test-defining
  change to be followed by a failing test run before code changes.
- At least one implementation prompt must explicitly require a failing run of
  the same exact test command before code changes and a passing rerun of that
  same exact test command after code changes.
- No child prompt may weaken that TDD rule with wording such as
  `failing or tightened-test ...`; the workflow must require a real failing run
  of the same exact command before the implementation change.
- The final prompt must explicitly run the full verification commands for the
  implemented system and preserve those exact command strings.
- The workflow must require command evidence that includes stdout, stderr, and
  exit code details rather than only pass/fail summaries.
- For any slice involving datetime or date-and-time behavior, the child prompt
  itself must explicitly require the same upstream semantic behavior. When the
  upstream artifacts require a runtime-generated current local date-and-time
  line, the child prompt must preserve that exact semantic requirement rather
  than broadening it to a generic timestamp-only output. The child prompt must
  still explicitly forbid tighter rendering assertions
  such as a literal `T`, ISO-only formatting, an exact separator, an explicit
  timezone offset, a non-`None` tzinfo requirement, or another exact
  rendering/detail requirement unless the upstream artifacts explicitly require
  them.
- Each child prompt must describe the target slice directly and must not frame
  it as moving `from the current ... behavior` unless the named upstream
  artifacts explicitly guarantee that exact baseline state.
- The workflow must not use condensed command-result bullets such as
  ``- `python3 -m unittest tests.test_cli` -> OK`` in place of the required
  `## Command Reports` structure.
- The workflow must not introduce extra markdown headings inside the response
  template under `## Command Reports`, such as `### Command Report 1`; use
  plain text labels like `Command Report 1` instead.
- The workflow must not claim a fixed baseline runtime state unless upstream
  artifacts explicitly guarantee it or the same prompt iteration captures that
  baseline directly with command evidence. Do not write child prompts that
  invent history such as `the current behavior is greeting-only` when that
  exact baseline is not proven.
- When upstream artifacts require runtime-generated datetime or timestamp
  output, the workflow must preserve that semantic contract and must not
  tighten it into a stricter rendering rule such as a required literal `T`,
  ISO-only formatting, or another exact separator/detail unless the upstream
  artifacts explicitly require that formatting.
- The workflow must stay grounded in the upstream artifacts. Do not invent
  unrelated files, frameworks, or infrastructure.
- Do not create any files other than docs/implementation/implementation-workflow.md.
- Write the full file contents to docs/implementation/implementation-workflow.md.

### Validation Prompt

Review the current child implementation workflow against
<INTERFACE_CONTRACTS>, <SIMULATION_DEFINITIONS>, <FEATURE_SPECIFICATION>, and
<SOLUTION_DESIGN>.

Context:
<INTERFACE_CONTRACTS>
{{INCLUDE:docs/design/interface-contracts.yaml}}
</INTERFACE_CONTRACTS>
<SIMULATION_DEFINITIONS>
{{INCLUDE:docs/simulations/simulation-definitions.yaml}}
</SIMULATION_DEFINITIONS>
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>
<SOLUTION_DESIGN>
{{INCLUDE:docs/design/solution-design.yaml}}
</SOLUTION_DESIGN>
<IMPLEMENTATION_WORKFLOW>
{{RUNTIME_INCLUDE:docs/implementation/implementation-workflow.md}}
</IMPLEMENTATION_WORKFLOW>

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
5. Invented baseline state:
   - Flag child prompts that claim a fixed pre-change runtime state in the
     form `from the current ... behavior` when that exact baseline is not
     guaranteed by the named upstream artifacts.
6. Upstream semantic contradiction or unsupported exclusion:
   - Flag child prompts that either:
     - broaden a required upstream behavior into something semantically weaker,
       such as replacing a required current local date-and-time line with a
       generic timestamp-only output
     - or add a downstream constraint that excludes behavior the upstream
       artifacts still allow, such as requiring a literal `T`, ISO-only
       formatting, an exact separator, an explicit timezone offset, a
       non-`None` tzinfo requirement, or another exact rendering/detail rule
       that upstream artifacts do not require.
7. Missing final verification:
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

### Deterministic Validation

python-module:methodology_runner.phase_6_validation
--workflow-prompt
docs/implementation/implementation-workflow.md
--run-report
docs/implementation/implementation-run-report.yaml
--check-run-report

### Generation Prompt

As an implementation supervisor, you must run or resume the child
implementation workflow and write a truthful execution report to
docs/implementation/implementation-run-report.yaml.

Context:
<IMPLEMENTATION_WORKFLOW>
{{INCLUDE:docs/implementation/implementation-workflow.md}}
</IMPLEMENTATION_WORKFLOW>

Use this prompt-runner command base:
`{{prompt_runner_command}}`

Current methodology backend:
`{{methodology_backend}}`

Current project worktree:
`{{run_dir}}`

Execution rules:
- The child workflow must operate on the current project worktree, not on a
  hypothetical copy.
- If `docs/implementation/implementation-run-report.yaml` already exists from a
  previous PH-006 attempt, treat it as stale supervisor output rather than as
  evidence for the child workflow. Remove it before invoking the child
  workflow, then regenerate it from the actual child-run artifacts at the end
  of this prompt.
- Always parse the child workflow first with the exact supported parse command:
  `{{prompt_runner_command}} parse docs/implementation/implementation-workflow.md`
- If the child workflow already has useful progress in this worktree, resume
  it with:
  `{{prompt_runner_command}} run docs/implementation/implementation-workflow.md --backend {{methodology_backend}} --run-dir {{run_dir}} --resume {{run_dir}} --no-project-organiser`
- Otherwise run it fresh with:
  `{{prompt_runner_command}} run docs/implementation/implementation-workflow.md --backend {{methodology_backend}} --run-dir {{run_dir}} --no-project-organiser`
- After that first invocation, inspect the resulting child summary, halt
  reason, and live project files. If the child run halted but the live
  child-workflow state has already corrected the reported blocker or the child
  history indicates the truthful next action is to resume from the halted
  prompt, resume the child workflow again before finalizing this supervisor
  report.
- Do not finalize this supervisor report from a stale halted child snapshot
  when the live child-workflow state has already moved past that blocker and
  can still be resumed truthfully.
- Do not fabricate child-run outcomes. Base the report only on artifacts the
  child run actually produced in this worktree.
- Preserve the exact command strings observed in the child run. Do not rewrite
  dotted Python module paths into slash paths, replace targeted test commands
  with broader alternatives, or collapse multiple verification commands into a
  generic summary.
- Do not narrate a pre-change baseline that is not proven by the actual
  child-run evidence. If the child workflow used retries or resume mode,
  describe only the exact commands and observed outputs captured in the child
  run rather than claiming an earlier untouched baseline state.
- The child workflow is allowed to create or update real project files such as
  source code, tests, and README content.
- The child workflow should not rely on repository-level file-placement
  instructions when running inside this workspace, because the child prompts
  are operating on fixed, already-declared project paths.
- For each recorded command, preserve enough observed output to support later
  truthful verification. Include stdout and stderr excerpts, even when one of
  them is empty.
- If the execution backend does not expose a trustworthy stdout/stderr split
  for a recorded command and only a combined observed transcript is available,
  preserve that transcript truthfully in exactly one of `stdout_excerpt` or
  `stderr_excerpt`, leave the other excerpt empty, and do not invent a split
  that the backend did not provide.
- When the upstream contract requires a runtime-generated datetime or
  timestamp, preserve that same semantic requirement in the report evidence.
  Do not upgrade it into a stricter formatting claim such as a required
  literal `T`, ISO-only rendering, an explicit timezone offset, or a
  non-`None` tzinfo requirement unless the upstream artifacts explicitly
  require that format.

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
  - command: "python3 -m unittest tests.test_cli"
    exit_code: 0
    stdout_excerpt: "Ran 1 test in 0.01s\\n\\nOK"
    stderr_excerpt: ""
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
- If the first child invocation halts but a truthful follow-up resume is
  required by the live child-workflow state, the report must reflect the
  outcome after that follow-up resume rather than preserving the stale
  intermediate halt as the final result.
- If completion_status is `completed`, every prompt_results verdict must be `pass`.
- If completion_status is `halted`, halt_reason must explain what halted.
- Each `test_commands_observed` row must preserve the exact command string as
  executed in the child run and include `stdout_excerpt` and `stderr_excerpt`
  alongside the exit code.
- A `test_commands_observed` row may preserve the full observed command
  transcript in exactly one excerpt field with the other left empty when the
  backend-observed stream split is unavailable, but it must not fabricate or
  reshuffle output between the two fields.
- If the child workflow required the same exact test command before and after a
  change, the report must preserve both of those runs with the same command
  spelling.
- If the final child prompt required specific final verification commands, the
  report must preserve those same exact command strings rather than equivalent
  substitutes.
- Do not create any files other than docs/implementation/implementation-run-report.yaml.
- Write the full file contents to docs/implementation/implementation-run-report.yaml.

### Validation Prompt

Review the current child-run report against <IMPLEMENTATION_WORKFLOW> and the
child-run artifacts already present in the worktree.

Context:
<IMPLEMENTATION_WORKFLOW>
{{INCLUDE:docs/implementation/implementation-workflow.md}}
</IMPLEMENTATION_WORKFLOW>
<IMPLEMENTATION_RUN_REPORT>
{{RUNTIME_INCLUDE:docs/implementation/implementation-run-report.yaml}}
</IMPLEMENTATION_RUN_REPORT>

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
4. Normalized command drift:
   - Flag reports that replace exact child-run command strings with equivalent
     but different commands.
5. Missing stdout/stderr evidence:
   - Flag reports that do not preserve enough stdout/stderr detail to support
     truthful later verification.
6. Misleading next action:
   - Flag `next_action` values that do not match the real child-run state.
7. Stale halted snapshot:
   - Flag reports that stop at a halted child summary even though the live
     child-workflow state or the child history shows the correct next action
     is to resume and continue from the halted prompt.

Review instructions:
- Treat this prompt as an execution-supervision layer.
- Pass only if the child run completed and the report states that accurately.
- If the child run halted but the report itself shows that the truthful next
  action is to resume and the live child-workflow state has already corrected
  the blocker, use `revise` rather than `escalate` so the generator can resume
  the child workflow and update the report.
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
