# Design: Methodology Prompt Optimization

## 1. Requirements

This section defines how one optimization exercise should organize a
baseline run and the variant runs derived from it.

- **REQUIREMENT: REQ-1** Keep one exercise-local root
  - **SYNOPSIS:** One optimization exercise MUST have one root
    directory that contains the request copy, the baseline run, the
    variant runs, and later comparison artifacts.
    - **CHAIN-OF-THOUGHT:** The optimization work spans more than one
      run, so there needs to be one directory above the runs
      themselves. Without that root, the baseline, variants, and
      comparisons would scatter across unrelated locations.
    - **BECAUSE:** The full set of related runs should stay together on
      disk.

- **REQUIREMENT: REQ-2** Keep one distinguished baseline run
  - **SYNOPSIS:** One run in the set MUST be designated `baseline`.
    - **CHAIN-OF-THOUGHT:** Variants are not meaningful on their own;
      they exist to be compared against one accepted reference. The
      optimization exercise therefore needs one designated run that all
      variants inherit from and compare against.
    - **BECAUSE:** Later variant runs need one accepted reference run to
      compare against.

- **REQUIREMENT: REQ-3** Derive variants from the baseline run
  - **SYNOPSIS:** Every variant run MUST record which baseline run it
    was initialized from.
    - **CHAIN-OF-THOUGHT:** A variant's value comes from what changed
      relative to a known reference. That provenance is only reliable if
      the variant explicitly records which baseline it inherited from.
    - **BECAUSE:** Variant comparison only makes sense if provenance is
      explicit.

- **REQUIREMENT: REQ-4** Never share writable mutable state between runs
  - **SYNOPSIS:** A variant run MUST have its own private writable
    methodology worktree.
    - **CHAIN-OF-THOUGHT:** A variant may run buggy code or mutate the
      worktree in unexpected ways. If that mutable state were shared,
      one bad variant could silently damage the baseline or another
      variant.
    - **BECAUSE:** A bug or mutation in one variant must not corrupt the
      baseline or another variant.

- **REQUIREMENT: REQ-5** Allow reuse of immutable baseline artifacts
  - **SYNOPSIS:** A variant run MAY reuse immutable baseline artifacts
    by copying or linking them, but linked artifacts MUST be read-only
    after the baseline is sealed.
    - **CHAIN-OF-THOUGHT:** Some inherited files are pure evidence and
    do not need private writable copies. Reusing them is efficient, but
    only if the baseline has already been frozen and any linked files
    cannot be mutated through a variant.
    - **BECAUSE:** Immutable evidence can be reused efficiently, but it
      must not be writable through a variant run.

- **REQUIREMENT: REQ-6** Record the materialization policy of each variant
  - **SYNOPSIS:** Variant initialization MUST record which inherited
    artifacts were copied and which were linked.
    - **BECAUSE:** Debugging and reproducibility depend on knowing how a
      variant was materialized from its baseline.

## 2. Information Model

This section defines the main concepts in one exercise that contains a
baseline run and later variants.

- **ENTITY: ENTITY-1** `MethodologyPromptOptimization`
  - **SYNOPSIS:** One optimization exercise containing one baseline run
    and zero or more variant runs.
  - **FIELD:** `project_dir`
    - **SYNOPSIS:** Repository root containing code and prompt modules.
    - **BECAUSE:** The optimization exercise still belongs to one project.
  - **FIELD:** `exercise_dir`
    - **SYNOPSIS:** Exercise-local root directory.
    - **CHAIN-OF-THOUGHT:** The optimization exercise needs a container
      above the baseline and variants so it can also hold shared inputs
      and later comparisons.
    - **BECAUSE:** The optimization exercise needs one stable home on disk.
  - **FIELD:** `raw_request`
    - **SYNOPSIS:** Copied request file shared by the exercise.
    - **BECAUSE:** All runs in the set should stay tied to the same
      request.
  - **FIELD:** `prompt_runs_dir`
    - **SYNOPSIS:** Parent directory for the supervision and workflow
      prompt-runner runs that orchestrate the optimization exercise.
    - **BECAUSE:** Prompt-runner control state should stay inside the
      same exercise root as the methodology runs it manages.
  - **FIELD:** `baseline_run_dir`
    - **SYNOPSIS:** The run directory designated as `baseline`.
    - **BECAUSE:** The set needs one explicit reference run.
  - **FIELD:** `variants_dir`
    - **SYNOPSIS:** Parent directory containing all variant run
      directories.
    - **BECAUSE:** Variants should be grouped under one predictable
      root.
  - **FIELD:** `comparisons_dir`
    - **SYNOPSIS:** Parent directory for result summaries or comparison
      tables derived from the baseline and variants.
    - **BECAUSE:** The exercise needs one place for cross-run outputs.

- **ENTITY: ENTITY-2** `BaselineRun`
  - **SYNOPSIS:** The designated reference run in one methodology
    prompt optimization exercise.
  - **CONTAINS:** `MethodologyRun`
    - **BECAUSE:** The baseline is still one methodology run with the
      generic run structure.
  - **FIELD:** `sealed`
    - **SYNOPSIS:** Whether the baseline run has been frozen for use by
      variants.
    - **CHAIN-OF-THOUGHT:** Variants can only safely inherit linked
      immutable artifacts once the baseline is considered finished and
      no longer mutable in ways that would change those artifacts.
    - **BECAUSE:** Variants should only inherit from a baseline whose
      immutable artifacts can no longer change accidentally.
  - **FIELD:** `approved_evidence_bundle`
    - **SYNOPSIS:** Baseline artifacts approved for reuse by variants.
    - **BECAUSE:** Variants should inherit from a clearly defined subset
      of baseline artifacts.

- **ENTITY: ENTITY-3** `VariantRun`
  - **SYNOPSIS:** A methodology run initialized from the baseline run
    for one isolated comparison.
  - **CONTAINS:** `MethodologyRun`
    - **BECAUSE:** A variant is still one methodology run with the
      generic run structure.
  - **FIELD:** `variant_id`
    - **SYNOPSIS:** Stable identifier for the variant run directory.
    - **BECAUSE:** The optimization exercise needs predictable variant
      names.
  - **FIELD:** `derived_from`
    - **SYNOPSIS:** Path or id of the baseline run this variant was
      initialized from.
    - **BECAUSE:** Variant provenance must be explicit.
  - **FIELD:** `variant_spec`
    - **SYNOPSIS:** File describing what differs from the baseline for
      this variant.
    - **BECAUSE:** Later comparison depends on knowing what changed.
  - **FIELD:** `materialization_manifest`
    - **SYNOPSIS:** File recording which inherited artifacts were copied
      and which were linked.
    - **CHAIN-OF-THOUGHT:** When a variant behaves unexpectedly, we need
      to know whether it had a private copy of an artifact or shared a
      read-only inherited artifact. That distinction belongs in a
      durable manifest.
    - **BECAUSE:** The initialization policy must remain inspectable.

- **ENTITY: ENTITY-4** `VariantInitialization`
  - **SYNOPSIS:** Deterministic procedure that creates a new variant run
    directory from a sealed baseline run.
  - **FIELD:** `immutable_artifacts`
    - **SYNOPSIS:** Baseline artifacts safe to copy or link into the
      variant.
    - **BECAUSE:** Small immutable files do not need a private writable
      copy.
  - **FIELD:** `mutable_worktree`
    - **SYNOPSIS:** Private writable methodology worktree for the
      variant.
    - **BECAUSE:** Mutable state must never be shared writable with the
      baseline.
  - **FIELD:** `materialization_mode`
    - **SYNOPSIS:** Copy-first or link-for-immutable-artifacts.
    - **BECAUSE:** The exercise may need different tradeoffs between
      safety and disk usage.

## 3. Filesystem Layout

This section defines the directory layout for one methodology prompt
optimization exercise.

- **ENTITY: ENTITY-5** `ExerciseDir`
  - **SYNOPSIS:** Root directory for one optimization exercise.
  - **FIELD:** `path`
    - **SYNOPSIS:** `<project>/.prompt-runner/workflows/methodology-opt/<exercise-id>/`
    - **BECAUSE:** The exercise needs one stable root under the project.
  - **FIELD:** `inputs_dir`
    - **SYNOPSIS:** `<exercise-dir>/inputs/`
    - **BECAUSE:** The copied raw request should live in one stable
      place for the whole exercise.
  - **FIELD:** `prompt_runs_dir`
    - **SYNOPSIS:** `<exercise-dir>/prompt-runs/`
    - **BECAUSE:** The supervision and workflow prompt-runner runs
      should stay under the same exercise root as the baseline and
      variants.
  - **FIELD:** `runs_dir`
    - **SYNOPSIS:** `<exercise-dir>/runs/`
    - **BECAUSE:** Baseline and variant run directories should share one
      predictable parent.
  - **FIELD:** `comparisons_dir`
    - **SYNOPSIS:** `<exercise-dir>/comparisons/`
    - **BECAUSE:** Cross-run comparison outputs need one stable home.

- **ENTITY: ENTITY-6** `BaselineRunDir`
  - **SYNOPSIS:** Run directory named `baseline`.
  - **FIELD:** `path`
    - **SYNOPSIS:** `<exercise-dir>/runs/baseline/`
    - **BECAUSE:** The reference run should have the simplest and most
      stable name in the set.

- **ENTITY: ENTITY-7** `VariantRunDir`
  - **SYNOPSIS:** Run directory for one named variant.
  - **FIELD:** `path`
    - **SYNOPSIS:** `<exercise-dir>/runs/variants/<variant-id>/`
    - **BECAUSE:** Variant runs should be grouped separately from the
      baseline and named by their comparison intent.

## 4. Optimization Process

This section defines how one baseline run and later variant runs should
be created and related.

### Step 1: Create the exercise root

- **PROCESS: PROCESS-1** `Create exercise root`
  - **SYNOPSIS:** Create the exercise directory, copy the raw request,
    and prepare the baseline run directory.
  - **CHAIN-OF-THOUGHT:** The optimization exercise begins before any
    specific run starts. Shared inputs and the designated baseline
    location need to exist first so later steps inherit from a stable
    structure.
  - **WRITES:** `<exercise-dir>/inputs/raw-request.md`
    - **BECAUSE:** All runs in the set should share one copied request.
  - **WRITES:** `<exercise-dir>/runs/baseline/`
    - **BECAUSE:** The baseline run needs a dedicated run directory
      before any variant exists.

### Step 2: Create the baseline run

- **PROCESS: PROCESS-2** `Create baseline run`
  - **SYNOPSIS:** Execute one generic methodology run in
    `<exercise-dir>/runs/baseline/`.
  - **CHAIN-OF-THOUGHT:** The baseline is not a different execution
    engine; it is the first generic methodology run given the reference
    role inside the optimization exercise.
  - **READS:** `<exercise-dir>/inputs/raw-request.md`
    - **BECAUSE:** The baseline run should start from the shared
      exercise request source.
  - **USES:** `MethodologyRun`
    - **BECAUSE:** The baseline is just one methodology run plus a
      reference role.
  - **WRITES:** `<exercise-dir>/runs/baseline/raw-request.md`
    - **BECAUSE:** The generic methodology run structure requires a
      run-local request file under its own `run_dir`.
  - **WRITES:** baseline run artifacts
    - **BECAUSE:** Later variants depend on the baseline's worktree and
      evidence bundle.

### Step 3: Seal the baseline run

- **PROCESS: PROCESS-3** `Seal baseline run`
  - **SYNOPSIS:** Mark the baseline run as approved for variant
    inheritance and make any linked immutable artifacts read-only.
  - **CHAIN-OF-THOUGHT:** A finished baseline is not automatically safe
    to inherit from. The exercise needs one explicit sealing moment when
    the reusable baseline artifacts are frozen.
  - **USES:** baseline approved evidence bundle
    - **BECAUSE:** Only explicit immutable artifacts should be eligible
      for linking into variants.
  - **WRITES:** baseline seal artifact or metadata
    - **BECAUSE:** Variant initialization should only run from an
      explicit sealed baseline.

### Step 4: Initialize a variant run from the baseline

- **PROCESS: PROCESS-4** `Initialize variant run`
  - **SYNOPSIS:** Create one variant run directory from the sealed
    baseline run by copying mutable state and copying or linking
    immutable inherited artifacts.
  - **CHAIN-OF-THOUGHT:** Variant creation is its own deterministic
    operation. It must start from the sealed baseline, split mutable
    state from immutable evidence, and record exactly how the variant
    was materialized.
  - **READS:** `<exercise-dir>/runs/baseline/`
    - **BECAUSE:** The variant must inherit from the designated
      reference run.
  - **READS:** `<exercise-dir>/inputs/raw-request.md`
    - **BECAUSE:** The variant should stay tied to the same exercise
      request as the baseline.
  - **WRITES:** `<exercise-dir>/runs/variants/<variant-id>/`
    - **BECAUSE:** Each variant needs its own run-local root.
  - **WRITES:** `<exercise-dir>/runs/variants/<variant-id>/raw-request.md`
    - **BECAUSE:** The generic methodology run structure requires a
      run-local request file inside the variant run directory.
  - **COPIES:** mutable methodology worktree
    - **BECAUSE:** The variant must have a private writable worktree.
  - **COPIES-OR-LINKS:** immutable baseline evidence
    - **BECAUSE:** Small immutable artifacts can be reused efficiently
      once the baseline is sealed.
  - **WRITES:** `variant-spec.md`
    - **BECAUSE:** The variant must record what it intends to change.
  - **WRITES:** `materialization-manifest.json`
    - **BECAUSE:** The variant must record which inherited artifacts
      were copied and which were linked.

### Step 5: Run and compare variants

- **PROCESS: PROCESS-5** `Run variant`
  - **SYNOPSIS:** Execute the variant run in its own run directory.
  - **CHAIN-OF-THOUGHT:** Once a variant has its own private run
    directory and worktree, it can execute independently without
    risking the baseline or sibling variants.
  - **BECAUSE:** Comparison requires each variant to remain isolated
    from the baseline and from other variants.

- **PROCESS: PROCESS-6** `Compare baseline and variants`
  - **SYNOPSIS:** Read the baseline run and the finished variant runs to
    produce cross-run comparison outputs.
  - **CHAIN-OF-THOUGHT:** The optimization exercise exists to compare
    the reference run against controlled alternatives. The cross-run
    comparison step is what turns isolated runs into an optimization
    result.
  - **BECAUSE:** The point of the optimization exercise is comparison,
    not just isolated execution.

## 5. Planned Code

This section records the code components the optimization design needs.

- **SCRIPT: SCRIPT-1** `scripts/init_methodology_variant_run.py`
  - **SYNOPSIS:** Planned helper that creates one variant run directory
    from a sealed baseline run.
  - **READS:** baseline run directory
    - **BECAUSE:** The variant must inherit from the reference run.
  - **WRITES:** variant run directory
    - **BECAUSE:** The initializer owns deterministic variant
      materialization.
  - **WRITES:** materialization manifest
    - **BECAUSE:** The initializer should record how the variant was
      constructed.

## 6. Gaps

This section records the remaining gaps between the desired run-set
design and the current implementation.

- **GAP:** The current implementation does not yet have a dedicated
  variant-run initializer
  - **SYNOPSIS:** Variant creation is still implicit in workflow and
    harness logic rather than owned by one deterministic script.
    - **CHAIN-OF-THOUGHT:** The design assumes a clear boundary between
      baseline creation and variant initialization, but current code
      still spreads parts of variant setup across other components.
    - **BECAUSE:** The optimization design needs one component that
      creates safe variant directories from a sealed baseline.

- **GAP:** The current implementation still uses baseline-specific names
  instead of generic run names plus run-set roles
  - **SYNOPSIS:** Current names such as `baseline-status.json`,
    `baseline-methodology-run.md`, and
    `methodology-baseline-workspace/` reflect the baseline role rather
    than the generic run structure and its nested git worktree.
    - **BECAUSE:** The current implementation grew from the baseline
      path first.
