# Design: Methodology Runner Hand-Crafted Prompt Modules

## 1. Purpose

This document defines a migration of `methodology_runner` away from
runtime-generated phase prompt files and toward checked-in hand-crafted prompt
modules stored under `.methodology/docs/prompts/`.

The goal is to make integrated methodology runs use the same canonical prompt
modules that phase-level testing already uses.

## 2. Requirements

- **REQUIREMENT: REQ-1** Use one canonical prompt source per phase
  - **SYNOPSIS:** Each methodology phase should execute one checked-in prompt
    module rather than a run-time synthesized phase prompt.
  - **BECAUSE:** The current split between synthesized phase prompts and
    maintained hand-crafted prompt modules causes drift and makes integrated
    runs fail for prompt-format reasons that phase tests do not share.

- **REQUIREMENT: REQ-2** Preserve prompt-runner include resolution
  - **SYNOPSIS:** `methodology_runner` must invoke `prompt_runner` with the
    checked-in prompt module path as `source_file`.
  - **BECAUSE:** Existing methodology prompt modules use relative
    `{{INCLUDE:...}}` references that resolve relative to the source prompt
    module path.

- **REQUIREMENT: REQ-3** Preserve run-local phase artifacts
  - **SYNOPSIS:** Each phase must still keep run-local selector outputs,
    cross-reference results, retry-guidance artifacts, and prompt-runner run
    directories under `.methodology-runner/runs/phase-N/`.
  - **BECAUSE:** Integrated runs still need stable per-phase evidence and
    resumption state.

- **REQUIREMENT: REQ-4** Preserve run-time placeholder binding
  - **SYNOPSIS:** `methodology_runner` must pass any required placeholder
    values into `prompt_runner` so checked-in prompt modules can resolve phase-
    specific paths such as `raw_requirements_path`.
  - **BECAUSE:** The checked-in prompt modules already rely on placeholders for
    some phase-specific file paths.

- **REQUIREMENT: REQ-5** Remove methodology-owned stable prelude support
  - **SYNOPSIS:** The migration must stop depending on selector-driven stable
    generator and judge prelude files in the normal phase path.
  - **BECAUSE:** Stable phase guidance belongs in the checked-in prompt module,
    not in a second runtime-authored instruction layer.

- **REQUIREMENT: REQ-6** Replace prompt regeneration with prompt-module reuse
  - **SYNOPSIS:** Cross-reference retries should re-run the same checked-in
    prompt module rather than synthesize a new prompt file.
  - **BECAUSE:** Once the checked-in prompt module is the canonical prompt
    contract, retries should not depend on a second prompt-generation system.

## 3. Information Model

- **ENTITY: ENTITY-1** `PhasePromptModule`
  - **SYNOPSIS:** The canonical checked-in prompt module for one methodology
    phase.
  - **FIELD:** `phase_id`
    - **SYNOPSIS:** One methodology phase such as
      `PH-000-requirements-inventory`.
    - **BECAUSE:** The runner needs a stable key for prompt selection.
  - **FIELD:** `prompt_module_path`
    - **SYNOPSIS:** One file under `.methodology/docs/prompts/PR-0NN-*.md`.
    - **BECAUSE:** The checked-in prompt module becomes the source of truth for
      the phase prompt contract.
  - **FIELD:** `placeholder_values`
    - **SYNOPSIS:** Optional run-time placeholder bindings such as
      `raw_requirements_path=docs/requirements/raw-requirements.md`.
    - **BECAUSE:** Prompt-runner must still render phase-specific placeholders
      at execution time.

- **ENTITY: ENTITY-2** `PhaseRunArtifacts`
  - **SYNOPSIS:** The run-local files for one phase under
    `.methodology-runner/runs/phase-N/`.
  - **FIELD:** `skill_manifest`
    - **SYNOPSIS:** Optional audit metadata only if skill selection is kept as
      tooling support outside the normal execution path.
    - **BECAUSE:** It is no longer part of the active prompt contract.
  - **FIELD:** `cross_ref_result`
    - **SYNOPSIS:** `cross-ref-result.json`.
    - **BECAUSE:** Cross-reference verification remains run-local evidence.
  - **FIELD:** `retry_guidance`
    - **SYNOPSIS:** `retry-guidance-N.txt`.
    - **BECAUSE:** Cross-reference retries still need explicit run-local
      evidence for the injected runtime delta.
  - **FIELD:** `prompt_module_reference`
    - **SYNOPSIS:** The checked-in prompt module path recorded in phase state
      and phase results.
    - **BECAUSE:** The phase should record which canonical prompt module it
      executed.

## 4. Module Design

- **MODULE: MODULE-1** `phases.py`
  - **SYNOPSIS:** Own the mapping from phase IDs to canonical checked-in prompt
    modules.
  - **BECAUSE:** Phase definitions are already the main registry for phase
    identity and phase-owned contracts.

- **MODULE: MODULE-2** `orchestrator.py`
  - **SYNOPSIS:** Select the checked-in prompt module for a phase, build
    run-time placeholder bindings, invoke prompt-runner, and manage retries.
  - **BECAUSE:** The orchestrator owns the phase lifecycle and the prompt-runner
    invocation path.

- **MODULE: MODULE-3** Legacy runtime prompt synthesis
  - **SYNOPSIS:** The normal methodology-runner phase path should not depend on
    runtime prompt synthesis.
  - **BECAUSE:** Canonical phase prompt authoring moves to checked-in prompt
    modules rather than generated phase prompt files.

## 5. Process

- **PROCESS: PROCESS-1** Resolve the canonical prompt module for each phase
  - **SYNOPSIS:** Before invoking prompt-runner, the orchestrator should resolve
    the checked-in prompt module path for the current phase.
  - **READS:** `phase_id`
    - **BECAUSE:** Prompt-module selection is phase-specific.
  - **READS:** `.methodology/docs/prompts/PR-0NN-*.md`
    - **BECAUSE:** These checked-in prompt modules become the canonical prompt
      source.
  - **VALIDATES:** prompt module exists
    - **BECAUSE:** A missing canonical prompt module is a hard phase setup
      error.

- **PROCESS: PROCESS-2** Build run-time execution context
  - **SYNOPSIS:** The orchestrator should build placeholder values and any
    retry-specific runtime guidance before invoking prompt-runner.
  - **DECIDES:** placeholder map
    - **BECAUSE:** Prompt modules may require run-time values such as the raw
      requirements path.
  - **WRITES:** `.methodology-runner/runs/phase-N/retry-guidance-N.txt`
    - **BECAUSE:** Retry feedback is a run-local execution artifact rather than
      part of the checked-in phase contract.

- **PROCESS: PROCESS-3** Invoke prompt-runner with the checked-in source file
  - **SYNOPSIS:** The orchestrator should parse and execute the checked-in
    prompt module while keeping the run-local prompt-runner output directory per
    phase.
  - **USES:** `source_file=<checked-in prompt module path>`
    - **BECAUSE:** Relative inline includes in the prompt module must resolve
      from the canonical prompt path.
  - **USES:** `source_project_dir=<workspace>`
    - **BECAUSE:** Prompt-runner should still snapshot the methodology
      workspace into the phase run directory before executing.
  - **USES:** `run_dir=.methodology-runner/runs/phase-N/prompt-runner-output-phase-N`
    - **BECAUSE:** Phase-local execution evidence should still be kept under
      the run-local phase directory.
  - **USES:** `placeholder_values`
    - **BECAUSE:** The checked-in prompt module may need run-time values.

- **PROCESS: PROCESS-4** Handle cross-reference retries without prompt
  regeneration
  - **SYNOPSIS:** If cross-reference verification fails, the orchestrator
    should reuse the same checked-in prompt module on retry.
  - **CHAIN-OF-THOUGHT:** The canonical prompt contract now lives in the
    checked-in prompt module, so retry logic should adapt execution context
    rather than synthesize a replacement prompt file.
  - **BECAUSE:** Retries should preserve the same prompt source of truth.
  - **USES:** retry-specific run-time guidance injection
    - **BECAUSE:** Cross-reference findings still need a way to influence the
      next execution attempt without reintroducing methodology-authored stable
      preludes.

## 6. Rules

- **RULE: RULE-1** Do not synthesize a normal phase prompt file at run time
  - **SYNOPSIS:** The normal integrated phase path should not call the prompt
    architect to author a prompt-runner file.
  - **BECAUSE:** That duplicate prompt-authoring path is the source of the
    current drift.

- **RULE: RULE-2** Use the same phase prompt modules in unit and integrated
  execution
  - **SYNOPSIS:** The prompt modules executed by the integrated runner should
    match the ones used by the phase harnesses for the same phase.
  - **BECAUSE:** One canonical prompt source removes prompt-format divergence
    between isolated and integrated testing.

- **RULE: RULE-3** Keep prompt-module paths stable and explicit
  - **SYNOPSIS:** Prompt-module selection should be registry-driven, not
    inferred from filenames at run time.
  - **BECAUSE:** Explicit registry mapping is easier to test and safer to
    refactor.

## 7. Migration Scope

- **MODIFICATION: MOD-1** Migrate `methodology_runner` phase execution to use
  checked-in prompt modules
  - **SYNOPSIS:** Replace runtime prompt generation in the orchestrator's normal
    phase path with canonical prompt-module selection plus run-time context
    injection.
  - **BECAUSE:** This is a migration to the maintained prompt system, not a
    backwards-compatibility layer for keeping both prompt-authoring systems
    active indefinitely.
