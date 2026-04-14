# Plan: PH-000 Granular Test

## 0. Source Authorities And Inputs

This section links the main design and implementation inputs that
justify this plan.

- **FILE: FILE-1** `docs/design/components/CD-003-methodology-run.md`
  - **SYNOPSIS:** Primary design authority for one methodology run,
    including selected-phase execution, per-phase prompt generation, and
    phase-run artifact paths.
  - **BECAUSE:** The PH-000 test plan depends on the active methodology-run
    design authority first.

- **FILE: FILE-2** `docs/design/components/CD-007-ph000-step-1-review.md`
  - **SYNOPSIS:** Supplemental execution note for the PH-000 manual
    step-1 path.
  - **BECAUSE:** This file captures PH-000-specific observations and
    review notes, but it is not the primary design authority.

- **FILE: FILE-3** `docs/design/components/CD-006-prompt-runner-core.md`
  - **SYNOPSIS:** Generic `prompt_runner` design.
  - **BECAUSE:** PH-000 prompt parsing and revise-loop behavior depend on
    the generic prompt-runner component.

- **FILE: FILE-4** `docs/design/README.md`
  - **SYNOPSIS:** Design relationship index for the active design stack.
  - **BECAUSE:** This file shows where PH-000 testing fits relative to the
    other active methodology designs.

- **FILE: FILE-5** `src/cli/methodology_runner/prompt_generator.py`
  - **SYNOPSIS:** Current PH-000 prompt generation implementation,
    including the deterministic Codex PH-000 template.
  - **BECAUSE:** The current PH-000 prompt contract is implemented here,
    so the plan must distinguish reviewed source behavior from rerun
    evidence on disk.

## 1. Goal Hierarchy

This section breaks PH-000 testing into the smallest useful checkpoints and ties each task to the design items that justify it.

- **GOAL: GOAL-1** Prove that `PH-000-requirements-inventory` works correctly before running later methodology steps.
  - **CHAIN-OF-THOUGHT:** `PH-000` is the first native methodology phase and produces the first structured artifact. If step 1 is unclear or unstable, later methodology phases inherit that uncertainty.
  - **BECAUSE:** Step 1 is the entry artifact for the rest of the methodology.
  - **SUPPORTS:** `REQ-6` and `PROCESS-3` in `docs/design/components/CD-003-methodology-run.md`
    - **BECAUSE:** The active design authority defines selected-phase execution and per-phase prompt generation for PH-000.

- **SUBGOAL: SUBG-1** Prove the deterministic setup path.
  - **CHAIN-OF-THOUGHT:** The workspace setup, phase selection, prompt generation, and prompt parsing are all deterministic. Those should be verified before paying for a live model run.
  - **BECAUSE:** We should verify the non-LLM machinery before paying for a live run.
  - **SUPPORTS:** `PROCESS-1`, `PROCESS-2`, `PROCESS-3`, and `PROCESS-4` in `CD-007-ph000-step-1-review.md`
    - **BECAUSE:** Those process items define the deterministic PH-000 setup and execution path.
  - **SUPPORTS:** `REQ-3` and `REQ-4` in `CD-003-methodology-run.md`
    - **BECAUSE:** The generic methodology-run design requires stable run-local artifacts and resumable state.
  - **TASK: TASK-1** Review the PH-000 phase definition in `src/cli/methodology_runner/phases.py`.
    - **STATUS:** `done`
    - **BECAUSE:** The phase config defines the intended inputs, outputs, and predecessor model.
    - **SUPPORTS:** `GOAL-1` and `PROCESS-1` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** The review note says a correct manual run starts the native phase engine with the PH-000 phase definition.
  - **TASK: TASK-2** Review the PH-000 execution path in `cli.py`, `orchestrator.py`, and `prompt_generator.py`.
    - **STATUS:** `done`
    - **BECAUSE:** We need to confirm that the real code path matches the PH-000 design.
    - **SUPPORTS:** `PROCESS-1` through `PROCESS-5` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** Those items define the actual PH-000 execution sequence this task is validating.
  - **TASK: TASK-3** Review the selected PH-000 skills.
    - **STATUS:** `done`
    - **BECAUSE:** The stable prompt contract now depends on the skills for the phase-specific method.
    - **SUPPORTS:** `PROCESS-2` and `PROCESS-3` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** Those items say skill selection and skill-driven behavior are part of the PH-000 path.

- **SUBGOAL: SUBG-2** Generate and prove the PH-000 prompt contract without a live model run.
  - **CHAIN-OF-THOUGHT:** `prompt_runner` does not execute the phase definition directly. `methodology_runner.prompt_generator` first has to materialize `prompt-file.md`, and that generated file is the exact artifact that `prompt_runner` executes. Generating, inspecting, and parsing that file is the cheapest way to confirm the stable prompt contract before a live run.
  - **BECAUSE:** The generated prompt file is the exact artifact `prompt_runner` executes, so prompt generation itself must be tested explicitly.
  - **SUPPORTS:** `PROCESS-3` and `PROCESS-4` in `CD-007-ph000-step-1-review.md`
    - **BECAUSE:** Those process items define prompt-file generation and prompt-runner execution.
  - **SUPPORTS:** `REQ-4` and `REQ-5` in `CD-003-methodology-run.md`
    - **BECAUSE:** The run design requires inspectable top-level and nested evidence artifacts.
  - **TASK: TASK-4** Generate the PH-000 prompt file for the tiny hello-world request.
    - **STATUS:** `todo`
    - **CHAIN-OF-THOUGHT:** The hardcoded template in `prompt_generator.py` is only the source contract. The real PH-000 run still has to materialize `prompt-file.md` in the run artifacts alongside the selected preludes, and that generated file is what `prompt_runner` will parse and run.
    - **BECAUSE:** We need to inspect the real generated prompt artifact, not just the source template.
    - **SUPPORTS:** `PROCESS-3` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** That process item says the phase must materialize `prompt-file.md` before prompt execution can begin.
  - **TASK: TASK-5** Inspect `generator-prelude.txt`, `judge-prelude.txt`, and `prompt-file.md`.
    - **STATUS:** `todo`
    - **BECAUSE:** This confirms the contract-vs-skill split is actually what the runner will execute.
    - **SUPPORTS:** `PROCESS-2` and `PROCESS-3` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** Those process items define the generated preludes and prompt file as the PH-000 execution inputs.
  - **TASK: TASK-6** Parse `prompt-file.md` with `prompt_runner parse`.
    - **STATUS:** `todo`
    - **BECAUSE:** The generated file must be structurally valid before any model call.
    - **SUPPORTS:** `PROCESS-4` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** That process item says the generated prompt file must parse before execution.
    - **SUPPORTS:** `FILE-3`
      - **BECAUSE:** Generic `prompt_runner` parsing behavior belongs to the prompt-runner core design.
  - **TASK: TASK-7** Confirm there is exactly one PH-000 prompt pair and that it reads and writes the right files.
    - **STATUS:** `done`
    - **BECAUSE:** We intentionally collapsed the redundant staged prompt pairs.
    - **SUPPORTS:** `PMOD-1` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** The PH-000 review note now defines one prompt pair with one generator and one judge.
    - **SUPPORTS:** `FILE-5`
      - **BECAUSE:** The current deterministic PH-000 prompt template now has one prompt pair in source.

- **SUBGOAL: SUBG-3** Prove the pre-run workspace setup.
  - **CHAIN-OF-THOUGHT:** Before evaluating model behavior, we need to see that a fresh run directory and worktree are initialized correctly and that the phase-local artifacts appear under stable paths.
  - **BECAUSE:** Step 1 should fail fast on setup problems, not during prompt execution.
  - **SUPPORTS:** `REQ-1`, `REQ-2`, and `REQ-3` in `CD-003-methodology-run.md`
    - **BECAUSE:** The run design requires a clean separation of `project_dir`, `run_dir`, and the nested worktree, plus resumable state in one run directory.
  - **SUPPORTS:** `PROCESS-1` and `PROCESS-2` in `CD-007-ph000-step-1-review.md`
    - **BECAUSE:** Those items define the setup and skill-selection artifacts that should appear before the live run proceeds far.
  - **TASK: TASK-8** Run `methodology_runner` for PH-000 in a fresh tiny worktree and stop after setup artifacts appear.
    - **STATUS:** `todo`
    - **BECAUSE:** We want to confirm worktree creation, raw request copy, state initialization, skill manifest creation, and prompt-file generation.
    - **SUPPORTS:** `PROCESS-1`, `PROCESS-2`, and `PROCESS-3` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** Those process items enumerate the exact setup artifacts to inspect.
  - **TASK: TASK-9** Inspect `.methodology-runner/state.json`, `phase-000-skills.yaml`, `generator-prelude.txt`, `judge-prelude.txt`, and `prompt-file.md`.
    - **STATUS:** `todo`
    - **BECAUSE:** These are the granular phase-setup artifacts for step 1.
    - **SUPPORTS:** `PROCESS-1`, `PROCESS-2`, and `PROCESS-3` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** Those design items define each of these files as part of the PH-000 setup path.

- **SUBGOAL: SUBG-4** Prove one live PH-000 run.
  - **CHAIN-OF-THOUGHT:** Once the deterministic setup path is proven, we still need one real run to see whether the selected skills, one prompt pair, and the revise loop converge on an acceptable inventory artifact.
  - **BECAUSE:** Eventually we need to verify that the real model path can produce the artifact.
  - **SUPPORTS:** `PROCESS-4` and `PROCESS-5` in `CD-007-ph000-step-1-review.md`
    - **BECAUSE:** Those process items define prompt execution and phase acceptance.
  - **SUPPORTS:** `REQ-5` in `CD-003-methodology-run.md`
    - **BECAUSE:** The run should preserve inspectable evidence such as summary and timeline artifacts alongside the produced output.
  - **TASK: TASK-10** Run PH-000 only on the tiny hello-world request.
    - **STATUS:** `todo`
    - **BECAUSE:** This is the smallest live end-to-end proof of step 1.
    - **SUPPORTS:** `RULE-1` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** That rule says direct step-1 review should use the native methodology phase path.
  - **TASK: TASK-11** Review the prompt-runner iteration artifacts under the phase run directory.
    - **STATUS:** `todo`
    - **BECAUSE:** We need to see whether the judge feedback is sensible and whether the revise loop converges.
    - **SUPPORTS:** `PROCESS-4` and `PMOD-1` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** The phase run directory captures the real generator/judge loop for the one PH-000 prompt pair.
  - **TASK: TASK-12** Review the produced `docs/requirements/requirements-inventory.yaml`.
    - **STATUS:** `todo`
    - **BECAUSE:** The phase only succeeds if the artifact itself is correct, not just if the runner stops.
    - **SUPPORTS:** `GOAL-1`, `PMOD-1`, and `PROCESS-5` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** Those items define the artifact and the acceptance boundary for step 1.
  - **TASK: TASK-13** Review the methodology phase result and any cross-reference result.
    - **STATUS:** `todo`
    - **BECAUSE:** PH-000 acceptance is owned by `methodology_runner`, not only by `prompt_runner`.
    - **SUPPORTS:** `PROCESS-5` in `CD-007-ph000-step-1-review.md`
      - **BECAUSE:** That process item says the methodology phase records the final outcome after prompt execution.

## 2. Dependencies

This section makes the test order explicit.

- **TASK: TASK-14** Generate and inspect the PH-000 prompt artifacts before starting another live run.
  - **STATUS:** `todo`
  - **DEPENDS-ON:** `TASK-1`
    - **BECAUSE:** The phase definition should be understood before we inspect generated prompt artifacts.
  - **DEPENDS-ON:** `TASK-2`
    - **BECAUSE:** The code path should be understood before we inspect the files it emits.
  - **DEPENDS-ON:** `TASK-3`
    - **BECAUSE:** The skills explain how the generated prompt is expected to behave.
  - **SUPPORTS:** `SUBG-2`
    - **BECAUSE:** This is the cheapest checkpoint that directly proves the prompt contract and preludes.

- **TASK: TASK-15** Start one fresh PH-000 tiny run only after the deterministic prompt artifacts look correct.
  - **STATUS:** `todo`
  - **DEPENDS-ON:** `TASK-4`
    - **BECAUSE:** We want to inspect the real generated prompt before the live run.
  - **DEPENDS-ON:** `TASK-5`
    - **BECAUSE:** We want to inspect the real generated preludes before the live run.
  - **DEPENDS-ON:** `TASK-6`
    - **BECAUSE:** We should not start a live run with a malformed prompt file.
  - **DEPENDS-ON:** `TASK-7`
    - **BECAUSE:** We should confirm the intended one-prompt-pair structure before paying for execution.
  - **SUPPORTS:** `SUBG-3` and `SUBG-4`
    - **BECAUSE:** The live run is meaningful only after the deterministic checkpoints pass.

## 3. Immediate Next Step

This section states the cheapest next action.

- **TASK: TASK-16** Run `TASK-4` through `TASK-7` and save the inspected artifacts for review.
  - **STATUS:** `in progress`
  - **BECAUSE:** This is the cheapest granular checkpoint and the fastest way to confirm the current PH-000 design is really what step 1 will execute.
  - **SUPPORTS:** `SUBG-2`
    - **BECAUSE:** Those tasks directly prove the generated prompt contract without requiring a live model run.

## 4. Update Note

This section records why several live-run tasks remain open even though
PH-000 has already been exercised before.

- **RULE: RULE-1** Treat older PH-000 run artifacts as stale if they predate the current one-prompt-pair PH-000 contract.
  - **SYNOPSIS:** Existing artifacts under `runs/2026-04-13-manual-ph000-hello-world-atomic/`
    were produced before the current PH-000 prompt contract was fully
    simplified and aligned.
  - **CHAIN-OF-THOUGHT:** The source review and prompt-template cleanup
    are current, but the old workspace on disk still reflects an earlier
    prompt structure. The remaining artifact-generation and live-run
    tasks therefore need a fresh rerun against the current code, not a
    reinterpretation of stale evidence.
  - **BECAUSE:** Source review is done, but fresh generated artifacts and
    live-run evidence still need to be regenerated from the current PH-000 implementation.
