# Design: Methodology Run

## 1. Requirements

This section defines the structure and artifacts required for one
methodology run, without assuming whether the run will later be called a
baseline run or a variant run.

- **REQUIREMENT: REQ-1** Keep project-scoped inputs separate from run-local
  artifacts
  - **SYNOPSIS:** A methodology run MUST distinguish `project_dir` from
    `run_dir`.
    - **CHAIN-OF-THOUGHT:** A methodology run reads code, prompts, and
      scripts from the project, but it also creates mutable worktree
      state and run-local outputs. If those two scopes are blurred, the
      run becomes harder to inspect and easier to corrupt.
    - **BECAUSE:** Project-level code and reference files should not be
      mixed with one run's mutable worktree and outputs.

- **REQUIREMENT: REQ-2** Isolate mutable project edits during a run
  - **SYNOPSIS:** A methodology run MUST support working on project
    artifacts in an isolated manner while the run is in progress.
    - **CHAIN-OF-THOUGHT:** The run needs to inspect and modify
      project-derived files, but those in-progress edits should not
      mutate the main project tree directly. Isolation lets the run
      progress safely and keeps the resulting changes reviewable before
      they are applied back to the project.
    - **BECAUSE:** In-progress project edits need to remain isolated
      until the run has produced a result worth reviewing or applying.

- **REQUIREMENT: REQ-3** Support fresh execution and resume within the same
  run directory
  - **SYNOPSIS:** A methodology run SHOULD support both fresh execution
    and resume without changing `run_dir`.
    - **CHAIN-OF-THOUGHT:** A run may stop and continue multiple times
      before it becomes useful to a caller. Reusing the same `run_dir`
      preserves progress, artifacts, and diagnosis in one place.
    - **BECAUSE:** Resume preserves useful progress and makes failures
      inspectable in one place.

- **REQUIREMENT: REQ-4** Produce workflow-level run artifacts
  - **SYNOPSIS:** A methodology run MUST write one machine-readable run
    status artifact and one human-readable run note artifact under
    `run_dir`.
    - **CHAIN-OF-THOUGHT:** Higher-level consumers should not have to
      open nested worktree files just to know whether the run is usable
      or blocked. A top-level status artifact and note give both machines
      and humans one direct entrypoint.
    - **BECAUSE:** Higher-level workflows and humans both need a
      top-level description of the run that does not require reading the
      entire nested worktree directly.

- **REQUIREMENT: REQ-5** Produce inspectable methodology evidence
  - **SYNOPSIS:** A methodology run MUST preserve the raw request copy,
    methodology summary, and timeline report under stable paths.
    - **CHAIN-OF-THOUGHT:** Later consumers need to know what request
      produced the run, what the run concluded, and what detailed timing
    and token evidence support that conclusion. Those files together
      are the minimum stable evidence set.
    - **BECAUSE:** Later consumers of the run need both compact and
      detailed evidence.

- **REQUIREMENT: REQ-6** Support full-run and selected-phase execution
  - **SYNOPSIS:** A methodology run MUST support either executing the
    full methodology phase sequence or executing a caller-selected phase
    subset from the command line.
    - **CHAIN-OF-THOUGHT:** The same component is used both for a full
      methodology pass and for focused work such as manual PH-000 review
      or later targeted reruns. The run therefore needs one explicit
      execution-scope model instead of assuming that every invocation
      always means "run everything."
    - **BECAUSE:** Callers need to run either the full phase sequence or
      a selected subset without switching to a different component.

## 2. Information Model

This section defines the generic artifacts and paths for one
methodology run.

- **ENTITY: ENTITY-1** `MethodologyRun`
  - **SYNOPSIS:** One methodology-runner execution context represented
    by one `run_dir`.
  - **FIELD:** `project_dir`
    - **SYNOPSIS:** Repository root containing scripts, prompt modules,
      and other project-scoped files.
    - **BECAUSE:** The run needs a stable reference to project-scoped
      code and documents.
  - **FIELD:** `run_dir`
    - **SYNOPSIS:** Run-local directory that contains exactly one
      methodology run and its run-local files.
    - **CHAIN-OF-THOUGHT:** All mutable and inspectable per-run state
      belongs to one run, so the design needs one top-level directory
      that contains it.
    - **BECAUSE:** The run needs one stable root for all mutable and
      inspectable per-run state.
  - **FIELD:** `raw_request`
    - **SYNOPSIS:** `{{run_dir}}/raw-request.md`
    - **BECAUSE:** The run should use a copied request file that stays
      stable for the life of the run.
  - **FIELD:** `execution_scope`
    - **SYNOPSIS:** Either `all-phases` or `selected-phases`.
    - **CHAIN-OF-THOUGHT:** The run component can be invoked for the
      whole methodology or for a bounded subset. That distinction is a
      first-class property of the run, not an incidental command-line
      detail.
    - **BECAUSE:** The run needs to record whether it is executing the
      full phase sequence or a caller-selected subset.
  - **FIELD:** `selected_phase_ids`
    - **SYNOPSIS:** Ordered list of selected phase IDs when
      `execution_scope` is `selected-phases`; otherwise `null`.
    - **BECAUSE:** The run needs to preserve exactly which phases the
      caller asked it to execute.
  - **FIELD:** `worktree_dir`
    - **SYNOPSIS:** `{{run_dir}}/worktree`, the nested git
      worktree used by `methodology_runner` inside the run.
    - **CHAIN-OF-THOUGHT:** The run record lives at the top of
      `run_dir`, but the files that `methodology_runner` edits should
      live in one contained git worktree that can later be compared
      or applied back to the project.
    - **BECAUSE:** The nested `methodology_runner` worktree must
      stay local to the run.
  - **FIELD:** `status_file`
    - **SYNOPSIS:** `{{run_dir}}/methodology-run-status.json`
    - **CHAIN-OF-THOUGHT:** A caller needs a structured artifact it can
      parse without reading nested worktree files or markdown prose.
    - **BECAUSE:** The run needs one machine-readable top-level status
      artifact.
  - **FIELD:** `note_file`
    - **SYNOPSIS:** `{{run_dir}}/methodology-run.md`
    - **BECAUSE:** The run needs one human-readable top-level note
      artifact.

- **ENTITY: ENTITY-2** `MethodologyWorktree`
  - **SYNOPSIS:** The nested `methodology_runner` git worktree owned by one
    methodology run.
  - **FIELD:** `state_file`
    - **SYNOPSIS:** `{{run_dir}}/worktree/.methodology-runner/state.json`
    - **BECAUSE:** Resume and completion decisions depend on the nested
      methodology state.
  - **FIELD:** `summary_file`
    - **SYNOPSIS:** `{{run_dir}}/worktree/.methodology-runner/summary.txt`
    - **BECAUSE:** Later consumers need a compact summary of the run.
  - **FIELD:** `timeline_file`
    - **SYNOPSIS:** `{{run_dir}}/worktree/timeline.html`
    - **BECAUSE:** Later consumers need detailed timing, token, and cost
      evidence.

- **ENTITY: ENTITY-6** `PhaseRunArtifacts`
  - **SYNOPSIS:** The generated prompt and support files for one
    selected methodology phase inside one methodology run.
  - **FIELD:** `phase_run_dir`
    - **SYNOPSIS:** `{{run_dir}}/worktree/.methodology-runner/runs/phase-N`
      for the concrete phase number.
    - **CHAIN-OF-THOUGHT:** Each selected phase generates its own
      prompt-runner input and support files. Those artifacts should live
      under one stable per-phase directory rather than being scattered
      across the worktree.
    - **BECAUSE:** Each selected phase needs one stable directory for
      its generated prompt and support artifacts.
  - **FIELD:** `prompt_file`
    - **SYNOPSIS:** `{{phase_run_dir}}/prompt-file.md`
    - **BECAUSE:** `prompt_runner` executes a generated prompt file for
      each selected phase.
  - **FIELD:** `generator_prelude`
    - **SYNOPSIS:** `{{phase_run_dir}}/generator-prelude.txt`
    - **BECAUSE:** The generator prompt is preceded by phase-selected
      skill instructions.
  - **FIELD:** `judge_prelude`
    - **SYNOPSIS:** `{{phase_run_dir}}/judge-prelude.txt`
    - **BECAUSE:** The judge prompt is preceded by phase-selected skill
      instructions.
  - **FIELD:** `skill_manifest`
    - **SYNOPSIS:** `{{phase_run_dir}}/phase-NNN-skills.yaml`
    - **BECAUSE:** The phase should preserve the concrete generator and
      judge skill selection it executed.
  - **FIELD:** `deterministic_validation_helper`
    - **SYNOPSIS:** Optional helper script such as `{{phase_run_dir}}/phase-1-deterministic-validation.py`
    - **BECAUSE:** Some phases can supply deterministic validation logic that prompt-runner should execute once per iteration instead of forcing the model to recreate the same checks with ad hoc Bash and Python calls.

- **ENTITY: ENTITY-3** `MethodologyRunStatus`
  - **SYNOPSIS:** Machine-readable top-level status file for one
    methodology run.
  - **FIELD:** `run_mode`
    - **SYNOPSIS:** `missing-request`, `fresh-run`, `corrupt-worktree`,
      `reuse-complete`, or `resume`.
    - **BECAUSE:** Later diagnosis depends on knowing how the run
      reached its current state.
  - **FIELD:** `execution_scope`
    - **SYNOPSIS:** `all-phases` or `selected-phases`.
    - **BECAUSE:** Later diagnosis depends on knowing whether the run
      attempted the full methodology or a selected subset.
  - **FIELD:** `selected_phase_ids`
    - **SYNOPSIS:** Ordered list of phase IDs when the caller selected a
      subset; otherwise `null`.
    - **BECAUSE:** Later consumers need to know which phases this run
      was actually supposed to execute.
  - **FIELD:** `completion_state`
    - **SYNOPSIS:** Whether the run is complete enough for a caller to
      consume.
    - **CHAIN-OF-THOUGHT:** A run can exist without yet being usable by
      another component. The status file therefore needs one explicit
      field that answers the consumer-facing question directly.
    - **BECAUSE:** A generic run should report completion without
      assuming a baseline-specific role.
  - **FIELD:** `methodology_returncode`
    - **SYNOPSIS:** Return code from the nested `methodology_runner`
      command when one was invoked.
    - **BECAUSE:** The top-level status should preserve whether the
      nested run command itself succeeded.
  - **FIELD:** `timeline_returncode`
    - **SYNOPSIS:** Return code from the timeline generation command
      when one was invoked.
    - **BECAUSE:** The top-level status should preserve whether the
      detailed report was generated successfully.
  - **FIELD:** `worktree_exists`
    - **SYNOPSIS:** Whether `worktree_dir` exists.
    - **BECAUSE:** Resume and completion decisions change depending on
      whether the worktree exists at all.
  - **FIELD:** `state_exists`
    - **SYNOPSIS:** Whether the nested state file exists.
    - **BECAUSE:** A worktree with no state file cannot be resumed
      safely.
  - **FIELD:** `summary_exists`
    - **SYNOPSIS:** Whether the nested summary file exists.
    - **BECAUSE:** A usable run requires the summary file.
  - **FIELD:** `timeline_exists`
    - **SYNOPSIS:** Whether the timeline report exists.
    - **BECAUSE:** A usable run requires the timeline report.
  - **FIELD:** `current_phase`
    - **SYNOPSIS:** Current methodology phase when the run is still
      incomplete.
    - **BECAUSE:** Completion depends on whether the nested run still
      has an active phase.
  - **FIELD:** `finished_at`
    - **SYNOPSIS:** Nested methodology completion timestamp.
    - **BECAUSE:** Completion depends on whether the nested run has
      actually finished.
  - **FIELD:** `phase_statuses`
    - **SYNOPSIS:** Mapping from methodology phase id to phase status.
    - **BECAUSE:** Later diagnosis needs the full phase-state picture,
      not only one summary flag.
  - **FIELD:** `blocking_phase`
    - **SYNOPSIS:** First methodology phase that still blocks run
      completion when the run is incomplete.
    - **CHAIN-OF-THOUGHT:** An incomplete run may have many phase
      statuses, but resume and diagnosis usually need one immediate
      blocker rather than the whole list first.
    - **BECAUSE:** Resume and repair decisions need one explicit
      statement of the current blocking point.
  - **FIELD:** `next_consumer_fact`
    - **SYNOPSIS:** Most important fact that the next consumer of the
      run should know.
    - **BECAUSE:** Higher-level workflows need one short handoff in
      addition to raw status fields.

- **ENTITY: ENTITY-4** `MethodologyRunNote`
  - **SYNOPSIS:** Human-readable top-level note for one methodology run.
  - **FIELD:** `completion_state`
    - **SYNOPSIS:** Human-readable statement of whether the run is
      complete enough for the next consumer.
    - **BECAUSE:** Humans need the top-level answer without reading JSON
      fields first.
  - **FIELD:** `run_mode`
    - **SYNOPSIS:** Human-readable statement of how the run reached its
      current state.
    - **BECAUSE:** Humans need to know whether the run was started
      fresh, resumed, reused, or failed before starting.
  - **FIELD:** `execution_scope`
    - **SYNOPSIS:** Human-readable statement of whether the run targeted
      all phases or a selected subset.
    - **BECAUSE:** Humans need to know the intended phase scope before
      interpreting completion.
  - **FIELD:** `next_consumer_fact`
    - **SYNOPSIS:** Most important handoff fact for the next consumer of
      the run.
    - **BECAUSE:** Higher-level workflows should receive one compact
      takeaway from the run.

- **ENTITY: ENTITY-5** `MethodologyEvidenceBundle`
  - **SYNOPSIS:** Minimal set of stable files later consumers read from
    a methodology run.
  - **FIELD:** `raw_request`
    - **SYNOPSIS:** Copied request file.
    - **BECAUSE:** Later consumers must stay tied to the same request
      that produced the run.
  - **FIELD:** `summary_file`
    - **SYNOPSIS:** Nested methodology summary file.
    - **BECAUSE:** Later consumers need a compact evidence handoff.
  - **FIELD:** `timeline_file`
    - **SYNOPSIS:** Nested methodology timeline report.
    - **BECAUSE:** Later consumers need detailed run evidence.
  - **FIELD:** `status_file`
    - **SYNOPSIS:** Top-level machine-readable run status file.
    - **BECAUSE:** Later consumers need one structured top-level run
      record.
  - **FIELD:** `note_file`
    - **SYNOPSIS:** Top-level human-readable run note file.
    - **BECAUSE:** Later consumers need one compact top-level summary
      for humans.

## 3. Methodology Run Process

This section defines the generic deterministic process for one
methodology run.

### Step 1: Determine execution scope

- **PROCESS: PROCESS-1** `Determine execution scope`
  - **SYNOPSIS:** Decide whether this invocation should execute all
    methodology phases or only a caller-selected phase subset.
  - **CHAIN-OF-THOUGHT:** The command-line contract already permits a
    phase list through `--phases`. That changes the meaning of the run:
    some invocations are full methodology runs, while others are bounded
    phase runs for focused validation or repair. The design therefore
    needs an explicit step that resolves the requested scope before the
    nested methodology command is chosen.
  - **READS:** command-line `--phases`
    - **BECAUSE:** A provided phase list is the caller's explicit scope
      request.
  - **DECIDES:** `all-phases`
    - **BECAUSE:** Absence of `--phases` means the run should execute
      the full methodology sequence.
  - **DECIDES:** `selected-phases`
    - **BECAUSE:** Presence of `--phases` means the run should execute
      only the named phase subset.
  - **RULE:** selected phases use methodology order
    - **SYNOPSIS:** When a phase subset is provided, the run should
      validate the phase IDs, deduplicate them, and execute them in the
      canonical methodology order.
    - **CHAIN-OF-THOUGHT:** Phase selection narrows the execution scope,
      but the methodology still has one authoritative phase order. If a
      caller passes selected phases out of order, preserving that order
      only creates avoidable predecessor failures.
    - **BECAUSE:** Selected-phase mode should honor the chosen subset
      without letting caller order violate the methodology sequence.
  - **RULE:** selected phases must still satisfy predecessor rules
    - **SYNOPSIS:** Selecting a later phase does not bypass predecessor
      artifact and completion checks.
    - **CHAIN-OF-THOUGHT:** A selected subset changes what the run tries
      to execute, but it does not change the methodology's dependency
      graph. A caller may ask to run only PH-003, yet PH-003 still
      depends on earlier completed artifacts.
    - **BECAUSE:** Selected-phase mode narrows execution scope but must
      not violate phase dependencies.

### Step 2: Determine run mode

- **PROCESS: PROCESS-2** `Determine run mode`
  - **SYNOPSIS:** Decide whether the run should fail immediately, start
    fresh, reuse a completed worktree, mark the worktree corrupt, or
    resume an incomplete run.
  - **CHAIN-OF-THOUGHT:** The same run directory can represent several
    situations: no request, no worktree, a corrupt worktree, a complete
    worktree, or an incomplete usable worktree. The run
    needs one explicit classification before later commands can be chosen
    safely.
  - **READS:** `{{run_dir}}/raw-request.md`
    - **BECAUSE:** The run cannot start without the copied request.
  - **READS:** `{{run_dir}}/worktree`
    - **BECAUSE:** The presence or absence of the worktree determines
      whether the run can reuse or resume prior state.
  - **READS:** `{{run_dir}}/worktree/.methodology-runner/state.json`
    - **BECAUSE:** Resume and completion decisions depend on the saved
      methodology state.
  - **DECIDES:** `missing-request`
    - **BECAUSE:** A missing copied request means the run cannot even
      start.
  - **DECIDES:** `fresh-run`
    - **BECAUSE:** No existing worktree means the run must create one
      from scratch.
  - **DECIDES:** `corrupt-worktree`
    - **BECAUSE:** A worktree with no state file cannot be resumed
      safely.
  - **DECIDES:** `reuse-complete`
    - **BECAUSE:** A worktree that is already complete should not be
      rerun.
  - **DECIDES:** `resume`
    - **BECAUSE:** An incomplete but usable worktree should preserve
      progress and continue from the current blocking point.

### Step 3: Run or resume methodology_runner

- **COMMAND: CMD-1** `python -m methodology_runner run`
  - **SYNOPSIS:** Creates a fresh methodology worktree from the copied
    request when `run_mode` is `fresh-run`.
  - **CHAIN-OF-THOUGHT:** A fresh run is only appropriate when there is
    no usable prior worktree. In that case the copied request becomes
    the sole starting point for the nested run.
  - **USES:** `{{run_dir}}/raw-request.md`
    - **BECAUSE:** The full methodology run must start from the copied
      request.
  - **USES:** optional `--phases <phase-id,...>`
    - **BECAUSE:** A fresh run may target either the full phase sequence
      or a caller-selected phase subset.
  - **WRITES:** `{{run_dir}}/worktree`
    - **BECAUSE:** The nested methodology worktree must live under the
      run directory.

- **COMMAND: CMD-2** `python -m methodology_runner resume`
  - **SYNOPSIS:** Continues a halted methodology worktree when
    `run_mode` is `resume`.
  - **CHAIN-OF-THOUGHT:** Resume is only meaningful when saved worktree
    state already exists and is still safe to continue. The command acts
    on that saved worktree rather than recreating it.
  - **USES:** `{{run_dir}}/worktree`
    - **BECAUSE:** Resume must act on the saved worktree rather than
      create a new one.
  - **USES:** optional `--phases <phase-id,...>`
    - **BECAUSE:** Resume may continue the whole methodology or only the
      caller-selected phase subset.

### Step 4: Generate per-phase prompt artifacts inside methodology_runner

- **PROCESS: PROCESS-3** `Generate per-phase prompt artifacts`
  - **SYNOPSIS:** While executing the selected phase sequence, the
    methodology run should select the phase skills, write the phase
    skill manifest and prelude files, then generate the concrete
    `prompt-file.md` that `prompt_runner` will execute for that phase.
  - **CHAIN-OF-THOUGHT:** The methodology run does not execute
    hand-authored prompt files directly for its phases. Instead, after
    the top-level `run` or `resume` command starts, it derives a
    concrete prompt from the phase config, the selected skills, the
    current worktree, and completed predecessor artifacts. That
    generation step is therefore an internal first-class part of the
    methodology-run component.
  - **READS:** selected `PhaseConfig`
    - **BECAUSE:** Prompt generation depends on the chosen phase's
      input, output, and validation contract.
  - **READS:** completed predecessor artifacts in `worktree`
    - **BECAUSE:** Later phases generate prompts using the artifacts
      produced by their completed predecessors.
  - **WRITES:** `{{run_dir}}/worktree/.methodology-runner/runs/phase-N/phase-NNN-skills.yaml`
    - **BECAUSE:** The run should preserve the concrete skill selection
      for the phase.
  - **WRITES:** `{{run_dir}}/worktree/.methodology-runner/runs/phase-N/generator-prelude.txt`
    - **BECAUSE:** The generated prompt contract is paired with
      generator-side skill instructions.
  - **WRITES:** `{{run_dir}}/worktree/.methodology-runner/runs/phase-N/judge-prelude.txt`
    - **BECAUSE:** The generated prompt contract is paired with
      judge-side skill instructions.
  - **WRITES:** `{{run_dir}}/worktree/.methodology-runner/runs/phase-N/prompt-file.md`
    - **BECAUSE:** `prompt_runner` executes one generated prompt file
      per selected phase.
  - **WRITES:** optional `{{run_dir}}/worktree/.methodology-runner/runs/phase-N/phase-*-deterministic-validation.py`
    - **BECAUSE:** A phase-local deterministic validator should live beside the generated prompt so prompt-runner can execute it with a stable path inside the run.
  - **USES:** `src/cli/methodology_runner/skill_selector.py`
    - **BECAUSE:** The phase skill manifest and prelude files are built
      from the selector's output.
  - **USES:** `src/cli/methodology_runner/prompt_generator.py`
    - **BECAUSE:** The generated `prompt-file.md` is owned by the prompt
      generator.
  - **USES:** optional phase validator modules such as `src/cli/methodology_runner/phase_1_validation.py`
    - **BECAUSE:** The prompt generator may stage a reusable deterministic validator for phases whose structural checks do not require an LLM.

### Step 5: Generate the run timeline

- **SCRIPT: SCRIPT-1** `scripts/run-timeline.py`
  - **SYNOPSIS:** Generates `timeline.html` from the current methodology
    worktree whenever the worktree exists.
  - **CHAIN-OF-THOUGHT:** The summary is compact but not enough for
    later cost, timing, and step-selection decisions. The run therefore
    needs one richer report derived from the actual worktree outputs.
  - **USES:** `{{run_dir}}/worktree`
    - **BECAUSE:** The timeline is derived from the actual worktree
      outputs.
  - **WRITES:** `{{run_dir}}/worktree/timeline.html`
    - **BECAUSE:** Later consumers depend on a detailed run report.

### Step 6: Evaluate completion and write top-level artifacts

- **PROCESS: PROCESS-4** `Evaluate run completion`
  - **SYNOPSIS:** Re-read the current methodology worktree state,
    compute whether the run is complete enough for a caller to consume,
    and write the top-level run artifacts.
  - **CHAIN-OF-THOUGHT:** Run mode alone does not tell us whether the
    run is actually usable. Completion depends on the nested state, the
    existence of summary and timeline artifacts, and the phase statuses,
    so the process must re-evaluate those facts after execution.
  - **READS:** `{{run_dir}}/worktree/.methodology-runner/state.json`
    - **BECAUSE:** Completion depends on the real nested methodology
      state.
  - **READS:** `{{run_dir}}/worktree/.methodology-runner/summary.txt`
    - **BECAUSE:** A usable run requires the methodology summary file.
  - **READS:** `{{run_dir}}/worktree/timeline.html`
    - **BECAUSE:** A usable run requires the timeline report.
  - **RULE:** completion is relative to execution scope
    - **SYNOPSIS:** A run is complete only relative to the scope it was
      asked to execute: all phases for `all-phases`, or the selected
      phase subset plus their required predecessors for
      `selected-phases`.
    - **CHAIN-OF-THOUGHT:** A selected PH-000-only run should not be
      judged by the same completion expectation as a full PH-000 to
      PH-007 run. The completion rule must therefore be evaluated
      against the scope chosen in Step 1.
    - **BECAUSE:** Completion must be interpreted against the run's
      intended phase scope, not always against the full methodology.
  - **RULE:** complete methodology run
    - **SYNOPSIS:** A run is complete only when state exists, phases
      exist, `current_phase` is `null`, `finished_at` exists, summary
      exists, timeline exists, and every phase status is `completed` or
      `skipped`.
    - **CHAIN-OF-THOUGHT:** A run should be consumable only after the
      nested methodology execution is actually finished and its evidence
      artifacts are present. The rule therefore combines nested state
      completion with evidence-file existence.
    - **BECAUSE:** Later consumers should read one explicit completion
      rule rather than infer completion from partial progress.
  - **WRITES:** `{{run_dir}}/methodology-run-status.json`
    - **BECAUSE:** The run needs one machine-readable top-level status
      artifact.
  - **WRITES:** `{{run_dir}}/methodology-run.md`
    - **BECAUSE:** The run needs one human-readable top-level note
      artifact.
  - **RETURNS:** `0`
    - **BECAUSE:** Exit code `0` means the run is complete enough for a
      caller to consume.
  - **RETURNS:** `1`
    - **BECAUSE:** Exit code `1` means the process completed but the run
      is still incomplete.
  - **RETURNS:** `2`
    - **BECAUSE:** Exit code `2` means the run directory is missing the
      required copied request.

## 4. Modifications

This section records how the current implementation still differs from
the generic methodology-run design above.

- **MODIFICATION: MOD-1** The current implementation uses baseline-specific
  names for the script and top-level artifacts.
  - **SYNOPSIS:** Current names include:
    - `scripts/run_methodology_baseline.py`
    - `baseline-status.json`
    - `baseline-methodology-run.md`
    - `methodology-baseline-workspace`
  - **CHAIN-OF-THOUGHT:** The current code path was first built to
    produce the accepted reference run, so the file and script names
    reflect that role even though the underlying run structure is more
    generic and is better described as a nested git worktree.
  - **BECAUSE:** The current implementation was introduced through the
    baseline workflow first, so the names still reflect that role rather
    than the generic methodology-run concept.

- **MODIFICATION: MOD-2** The current prompt-runner wrapper is still
  baseline-specific.
  - **SYNOPSIS:** The current prompt module is
    `docs/prompts/PR-015-methodology-baseline-run.md`.
  - **BECAUSE:** The active workflow currently calls the generic
    methodology-run process only in the baseline role.
