# Design: PH-000 Manual Step-1 Review

## 1. Goal

This explains what should happen when we manually run step 1 of the
methodology.

- **GOAL: GOAL-1** Execute `PH-000-requirements-inventory` correctly
  - **SYNOPSIS:** A manual step-1 run SHOULD turn the tiny hello-world request
    into `docs/requirements/requirements-inventory.yaml`.
  - **CHAIN-OF-THOUGHT:** Step 1 is not the optimization workflow and not
    baseline orchestration; it is the first native methodology phase. So
    the explanation should follow the real phase engine that reads the raw
    request, generates the PH-000 prompt file, runs prompt-runner, and
    records phase completion.
  - **BECAUSE:** We need to understand the actual PH-000 execution path before
    trying to judge or optimize it.

## 2. Execution Path

This follows the real sequence for a direct manual PH-000 run.

- **PROCESS: PROCESS-1** Start the methodology phase run
  - **SYNOPSIS:** `methodology_runner.cli` starts a methodology run for
    `PH-000-requirements-inventory` in a fresh worktree.
  - **MODULE:** `src/cli/methodology_runner/cli.py`
    - **USES:** `cmd_run`
      - **BECAUSE:** This is the CLI entrypoint for a direct manual PH-000
        run.
  - **WRITES:** methodology worktree and `.methodology-runner/state.json`
    - **BECAUSE:** The phase needs a real methodology workspace before it can
      generate prompts or artifacts.
  - **GAP:** The startup path is noisier than it should be
    - **SYNOPSIS:** The CLI emits skill-catalog warnings from unrelated
      system skills before the phase-specific flow is visible.
    - **BECAUSE:** Step-1 startup should be easier to read during manual
      review.

- **PROCESS: PROCESS-2** Select the PH-000 skills
  - **SYNOPSIS:** `methodology_runner.orchestrator` runs the phase skill
    selector before generating the PH-000 prompt file.
  - **MODULE:** `src/cli/methodology_runner/orchestrator.py`
    - **USES:** `run_selector_and_build_prelude`
      - **BECAUSE:** The phase chooses generator and judge skills before
        prompt execution.
  - **MODULE:** `src/cli/methodology_runner/skill_selector.py`
    - **WRITES:** `phase-000-skills.yaml`
      - **BECAUSE:** The selected PH-000 skills need a durable manifest.
    - **WRITES:** `generator-prelude.txt`
      - **BECAUSE:** The generator call needs explicit skill-loading
        instructions.
    - **WRITES:** `judge-prelude.txt`
      - **BECAUSE:** The judge call needs its own skill-loading
        instructions.
  - **PROMPT: PROMPT-1** Skill-selector prompt
    - **SYNOPSIS:** Chooses which skills the PH-000 generator and judge
      should load.
    - **USES:** `plugins/methodology-runner-skills/skills/requirements-extraction/SKILL.md`
      - **BECAUSE:** PH-000 generation is primarily a fidelity-first
        extraction task.
    - **USES:** `plugins/methodology-runner-skills/skills/requirements-quality-review/SKILL.md`
      - **BECAUSE:** PH-000 judgment is primarily a completeness,
        atomicity, and fidelity review task.
    - **USES:** `traceability-discipline`
      - **BECAUSE:** Both the generator and judge need traceability rules
        for quotes, coverage, and source linkage.
  - **GAP:** Early phase progress is too opaque
    - **SYNOPSIS:** While the selector is running, the methodology state
      still looks mostly pending and there is little visible phase-local
      progress.
    - **BECAUSE:** Manual step review is harder when the first active sub-step
      is not clearly surfaced.

- **PROCESS: PROCESS-3** Generate the PH-000 prompt-runner file
  - **SYNOPSIS:** `methodology_runner.prompt_generator` creates the prompt file
    that `prompt_runner` will execute for PH-000.
  - **MODULE:** `src/cli/methodology_runner/prompt_generator.py`
    - **USES:** `generate_prompt_file`
      - **BECAUSE:** The phase must materialize a prompt-runner file before
        prompt execution can begin.
    - **WRITES:** `prompt-file.md`
      - **BECAUSE:** `prompt_runner` runs prompt files, not phase configs
        directly.
  - **PROMPT-MODULE: PMOD-1** Generated PH-000 prompt file
    - **SYNOPSIS:** For Codex, the PH-000 prompt file body currently comes
      from the hardcoded `_PH000_CODEX_TEMPLATE`.
    - **CHAIN-OF-THOUGHT:** PH-000 still needs one explicit prompt contract so
      the phase knows which files to read and write, what artifact shape to
      produce, and what acceptance boundary the judge must enforce. That
      contract should stay stable while the selected skills adapt how the
      generator and judge perform the work.
    - **BECAUSE:** The PH-000 prompt should define the stable artifact
      contract, while the selected skills should provide the phase-specific
      extraction and review discipline.
    - **PROMPT-PAIR:** Produce Requirements Inventory
      - **PROMPT:** `Generator`
        - **SYNOPSIS:** Reads `docs/requirements/raw-requirements.md` and
          writes the final acceptance-ready `requirements-inventory.yaml`.
        - **CHAIN-OF-THOUGHT:** The generator only needs a stable statement of
          the input file, output file, artifact schema, and revise-loop
          boundary. The selected generator skills should carry the extraction,
          decomposition, and traceability method.
        - **BECAUSE:** PH-000 produces one artifact, so the generator prompt
          should stay focused on the artifact contract and let the loaded
          skills adapt how the work is done.
      - **PROMPT:** `Judge`
        - **SYNOPSIS:** Checks omissions, invented requirements,
          compounds, categories, and YAML structure.
        - **CHAIN-OF-THOUGHT:** The judge still needs a stable acceptance
          contract for file structure and phase readiness, but the selected
          judge skills should supply the detailed review discipline and
          corrective reasoning.
        - **BECAUSE:** The judge should drive all refinement through the
          built-in revise loop while using the loaded skills for the detailed
          PH-000 review method.
  - **GAP:** The PH-000 template still contains some phase-specific policy
    - **SYNOPSIS:** The prompt contract is now narrower, but the hardcoded
      `_PH000_CODEX_TEMPLATE` still carries some extraction and review policy
      that overlaps with the selected skills.
    - **BECAUSE:** PH-000 prompt maintenance will stay harder than necessary
      until the prompt body is reduced to a cleaner artifact contract.

- **PROCESS: PROCESS-4** Execute the PH-000 prompt file through `prompt_runner`
  - **SYNOPSIS:** `methodology_runner.orchestrator` invokes `prompt_runner` and
    passes the PH-000 generator and judge preludes into that run.
  - **MODULE:** `src/cli/methodology_runner/orchestrator.py`
    - **USES:** `_invoke_prompt_runner_library`
      - **BECAUSE:** The preferred execution path is the in-process
        `prompt_runner` library call.
    - **USES:** `_invoke_prompt_runner_subprocess`
      - **BECAUSE:** The subprocess path is the fallback, not the primary
        path.
  - **MODULE:** `src/cli/prompt_runner/__main__.py`
    - **BECAUSE:** This is the CLI boundary when prompt-runner is used as a
      command.
  - **MODULE:** `src/cli/prompt_runner/parser.py`
    - **BECAUSE:** The generated prompt file must parse into prompt pairs
      before execution.
  - **MODULE:** `src/cli/prompt_runner/runner.py`
    - **BECAUSE:** This module executes the generator/judge revision loop.
  - **GAP:** None blocking for PH-000 in `prompt_runner`
    - **SYNOPSIS:** `required-files`, `checks-files`, live startup output, and
      placeholder rendering are present on the actual prompt-runner path.
    - **BECAUSE:** The prompt-runner features needed for step review are
      implemented.

- **PROCESS: PROCESS-5** Accept or reject the phase result
  - **SYNOPSIS:** After prompt-runner finishes, the methodology phase should
    verify the output and record PH-000 as completed, failed, or escalated.
  - **MODULE:** `src/cli/methodology_runner/orchestrator.py`
    - **USES:** `_run_single_phase`
      - **BECAUSE:** This is the phase-level owner of prompt generation,
        prompt execution, and later validation.
  - **READS:** `docs/requirements/requirements-inventory.yaml`
    - **BECAUSE:** PH-000 acceptance depends on the produced inventory
      artifact.
  - **WRITES:** phase result into methodology state
    - **BECAUSE:** Later methodology phases depend on the recorded PH-000
      outcome.

## 3. Scope Boundary

This clarifies what is and is not part of direct step-1 review.

- **RULE: RULE-1** Direct PH-000 review should use the native methodology phase
  path
  - **SYNOPSIS:** A manual step-1 review SHOULD exercise `methodology_runner`
    for `PH-000-requirements-inventory`, not the higher-level methodology
    optimization workflow.
  - **BECAUSE:** Using the optimization prompts would test the wrong layer.

- **GAP:** The higher-level methodology optimization prompts are still design-
  drifted
  - **SYNOPSIS:** `docs/prompts/PR-015-methodology-baseline-run.md` through
    `docs/prompts/PR-020-methodology-optimization-supervisor.md` still encode the
    older baseline-specific directory model.
  - **BECAUSE:** Those prompt modules need a separate alignment pass, but they
    are not part of the direct PH-000 execution path.
