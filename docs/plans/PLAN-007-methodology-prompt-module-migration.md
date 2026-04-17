# Methodology Prompt-Module Migration Plan

**GOAL: G-1**
- **SYNOPSIS:** Make the checked-in phase prompt modules the single source of truth for phase behavior, and reduce `methodology_runner` to orchestration plus run-specific binding.
- **STATUS:** `completed`

  **PROBLEM: P-1**
  - **SYNOPSIS:** The integrated path currently layers methodology-generated preludes on top of the same prompt modules already used by the unit harnesses.
  - **BECAUSE:** This creates two instruction systems for the same phase.
  - **STATUS:** `confirmed`

  **PROBLEM: P-2**
  - **SYNOPSIS:** Most of the current prelude content is stable phase behavior, not run-specific context.
  - **BECAUSE:** Skills like traceability, generator discipline, and judge discipline are effectively phase defaults.
  - **STATUS:** `confirmed`

  **TARGET: T-1**
  - **SYNOPSIS:** The effective phase prompt should come from the checked-in prompt module plus a small runtime delta for genuinely run-specific information.
  - **STATUS:** `completed`

  **FIX: F-1**
  - **ADDRESSES:** `P-1`
  - **SYNOPSIS:** Remove methodology-owned stable generator and judge preludes from the normal execution path.
  - **STATUS:** `completed`

    **IMPLEMENTATION: I-1**
    - **SYNOPSIS:** Stop generating `generator-prelude.txt` and `judge-prelude.txt` for stable phase guidance in normal runs.
    - **STATUS:** `completed`

    **IMPLEMENTATION: I-2**
    - **SYNOPSIS:** Remove the normal-path passing of `generator_prelude` and `judge_prelude` into prompt-runner.
    - **STATUS:** `completed`

    **TEST: TST-1**
    - **SYNOPSIS:** Add tests proving stable phase behavior no longer depends on methodology-generated preludes.
    - **STATUS:** `completed`

    **BENEFIT: B-1**
    - **SYNOPSIS:** This removes one whole instruction layer from normal execution.

  **FIX: F-2**
  - **ADDRESSES:** `P-2`
  - **SYNOPSIS:** Move stable phase guidance into the checked-in phase prompt modules.
  - **STATUS:** `completed`

    **IMPLEMENTATION: I-3**
    - **SYNOPSIS:** Put stable traceability, artifact contract, generator discipline, and judge expectations directly into `PR-023` through `PR-030`.
    - **STATUS:** `completed`

    **IMPLEMENTATION: I-4**
    - **SYNOPSIS:** Use prompt-runner-native sections for includes, validation, and placeholders instead of prelude prose wherever possible.
    - **STATUS:** `completed`

    **BENEFIT: B-2**
    - **SYNOPSIS:** This makes the checked-in prompt modules the clear source of truth for phase behavior.

  **FIX: F-3**
  - **ADDRESSES:** `T-1`
  - **SYNOPSIS:** Keep only true runtime delta injection in `methodology_runner`.
  - **STATUS:** `completed`

    **IMPLEMENTATION: I-5**
    - **SYNOPSIS:** Keep runtime placeholder binding only for values that genuinely vary by workspace or run.
    - **STATUS:** `completed`

    **IMPLEMENTATION: I-6**
    - **SYNOPSIS:** Keep cross-reference retry feedback as runtime injection because it depends on observed failure in the current run.
    - **STATUS:** `completed`

    **IMPLEMENTATION: I-7**
    - **SYNOPSIS:** Keep `phase-NNN-skills.yaml` only as optional audit evidence, or remove it if that evidence is not needed.
    - **STATUS:** `completed`

    **TEST: TST-2**
    - **SYNOPSIS:** Add tests proving retry guidance is still injected at runtime after cross-reference failure.
    - **STATUS:** `completed`

  **FIX: F-4**
  - **ADDRESSES:** `G-1`, `T-1`
  - **SYNOPSIS:** Make integrated and unit execution share the same effective phase instructions.
  - **STATUS:** `completed`

    **IMPLEMENTATION: I-8**
    - **SYNOPSIS:** Ensure both unit harnesses and integrated runs execute the same checked-in prompt module.
    - **STATUS:** `completed`

    **IMPLEMENTATION: I-9**
    - **SYNOPSIS:** Limit integrated-only differences to placeholder bindings, retry feedback, and orchestration state.
    - **STATUS:** `completed`

    **TEST: TST-3**
    - **SYNOPSIS:** Add tests proving unit and integrated paths use the same checked-in prompt module as the primary instruction source.
    - **STATUS:** `completed`

    **BENEFIT: B-3**
    - **SYNOPSIS:** This reduces drift between unit-tested phase execution and integrated execution.

  **NON-CONFORMITY: N-1**
  - **RELATES-TO:** `P-1`, `P-2`
  - **SYNOPSIS:** No hard implementation non-conformity is required to justify this change.
  - **BECAUSE:** The current design is better described as conformant but obsolete relative to the improved prompt-runner format.

  **CLASSIFICATION: C-1**
  - **SYNOPSIS:** This fix is a `migration`.
  - **BECAUSE:** It updates `methodology_runner` to fit the newer prompt-runner model and removes an older execution architecture rather than supporting both models indefinitely.
