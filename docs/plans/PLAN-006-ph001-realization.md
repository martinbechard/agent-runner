# PH-001 Realization Plan

- **GOAL: GOAL-1**
  - **SYNOPSIS:** Realize the `PH-001-feature-specification` phase so it can run end-to-end from the actual methodology contracts.
  - **BECAUSE:** The phase is defined in the methodology, but the current local rebuilt `PH-000` harness and the real `PH-001` validator do not yet align cleanly.
  - **STATUS:** `completed`

## Scope

- **PROCESS: PROCESS-1**
  - **SYNOPSIS:** `PH-001` must consume the real phase-0 output and produce the real phase-1 output.
  - **BECAUSE:** The operative phase definition says `PH-001` reads `docs/requirements/requirements-inventory.yaml` and writes `docs/features/feature-specification.yaml`.
  - **STATUS:** `confirmed`

- **FILE: FILE-1**
  - **SYNOPSIS:** Required upstream input:
    - `docs/requirements/requirements-inventory.yaml`
    - `docs/requirements/raw-requirements.md`
  - **BECAUSE:** `PH-001` groups `RI-*` items into features and uses the raw requirements as a validation reference.
  - **STATUS:** `confirmed`

- **FILE: FILE-2**
  - **SYNOPSIS:** Required downstream output:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** That is the declared methodology artifact for phase 1.
  - **STATUS:** `confirmed`

## Workstream 1: Align Contracts

- **GOAL: GOAL-2**
  - **SYNOPSIS:** Align the phase-0 and phase-1 artifact contracts before building the prompt flow.
  - **BECAUSE:** The current real `PH-001` validator expects a different phase-0 schema than the rebuilt local `PH-000` harness emits.
  - **STATUS:** `completed`

- **TASK: TASK-1**
  - **SYNOPSIS:** Compare the real `PH-000` schema in `src/cli/methodology_runner/phases.py` with the rebuilt local `PH-000` schema in `work/`.
  - **BECAUSE:** We need one authoritative upstream contract for `PH-001`.
  - **STATUS:** `completed`

- **TASK: TASK-2**
  - **SYNOPSIS:** Choose the authoritative schema for phase 0 input to `PH-001`.
  - **BECAUSE:** Without one source of truth, prompt generation and deterministic validation will keep diverging.
  - **STATUS:** `completed`

- **TASK: TASK-3**
  - **SYNOPSIS:** Update `phase_1_validation.py` or the phase-0 producer so both sides use the same key names and structure.
  - **BECAUSE:** Deterministic validation cannot be trusted if it reads the wrong upstream schema.
  - **STATUS:** `completed`

- **DONE-WHEN: DONE-1**
  - **SYNOPSIS:** `phase_1_validation.py` reads the exact same phase-0 schema that the chosen `PH-000` flow produces.
  - **BECAUSE:** That is the minimum contract needed before prompt work is meaningful.
  - **STATUS:** `completed`

## Workstream 2: Define PH-001 Generation Prompt

- **GOAL: GOAL-3**
  - **SYNOPSIS:** Create a generator prompt that faithfully implements the real `PH-001` phase definition.
  - **BECAUSE:** The phase needs a prompt-runner generation step that maps inventory items into features, ACs, dependencies, out-of-scope entries, and cross-cutting concerns.
  - **STATUS:** `completed`

- **TASK: TASK-4**
  - **SYNOPSIS:** Create a prompt-runner file for `PH-001` generation with the exact real phase inputs and output path.
  - **BECAUSE:** The generator must write the methodology artifact at `docs/features/feature-specification.yaml`.
  - **STATUS:** `completed`

- **TASK: TASK-5**
  - **SYNOPSIS:** Encode the required top-level output shape:
    - `features`
    - `out_of_scope`
    - `cross_cutting_concerns`
  - **BECAUSE:** The phase definition and deterministic validator both expect that exact structure.
  - **STATUS:** `completed`

- **TASK: TASK-6**
  - **SYNOPSIS:** Encode feature requirements:
    - `FT-*` IDs
    - `source_inventory_refs`
    - `AC-*` acceptance criteria
    - `dependencies`
  - **BECAUSE:** These are the minimum semantic units `PH-002` and `PH-003` depend on.
  - **STATUS:** `completed`

- **TASK: TASK-7**
  - **SYNOPSIS:** Explicitly instruct the generator to ensure every `RI-*` is either mapped to a feature or listed in `out_of_scope` with a reason.
  - **BECAUSE:** Complete RI coverage is one of the core guarantees of `PH-001`.
  - **STATUS:** `completed`

- **DONE-WHEN: DONE-2**
  - **SYNOPSIS:** The generator prompt can produce a feature specification YAML that matches the real phase schema and covers all `RI-*` items.
  - **BECAUSE:** That is the core artifact responsibility of `PH-001`.
  - **STATUS:** `completed`

## Workstream 3: Wire Deterministic Validation

- **GOAL: GOAL-4**
  - **SYNOPSIS:** Reuse the deterministic `PH-001` validator as the mechanical check in the prompt pair.
  - **BECAUSE:** The repo already contains a validator for structural and traceability checks that do not need LLM judgment.
  - **STATUS:** `completed`

- **FILE: FILE-3**
  - **SYNOPSIS:** Deterministic validator:
    - `src/cli/methodology_runner/phase_1_validation.py`
  - **BECAUSE:** This script already checks top-level keys, required fields, RI coverage, dependency sanity, and cross-cutting-concern breadth.
  - **STATUS:** `confirmed`

- **TASK: TASK-8**
  - **SYNOPSIS:** Define the validator invocation contract for prompt-runner.
  - **BECAUSE:** The validation prompt must know exactly how to run the deterministic step and where to read its result.
  - **STATUS:** `completed`

- **TASK: TASK-9**
  - **SYNOPSIS:** Decide the report format the validation prompt will read.
  - **BECAUSE:** The validator currently emits JSON; the prompt must either consume that directly or there must be a small wrapper that normalizes it.
  - **STATUS:** `completed`

- **TASK: TASK-10**
  - **SYNOPSIS:** Ensure the deterministic validator checks only what is truly mechanical.
  - **BECAUSE:** The semantic validator should not be forced to duplicate deterministic checks, and the deterministic layer should not pretend to resolve semantic grouping quality.
  - **STATUS:** `completed`

- **DONE-WHEN: DONE-3**
  - **SYNOPSIS:** The prompt-runner validation step can run the deterministic validator and interpret its verdict without guessing.
  - **BECAUSE:** This is the mechanical half of the phase’s pass/revise loop.
  - **STATUS:** `completed`

## Workstream 4: Define Semantic Validation Prompt

- **GOAL: GOAL-5**
  - **SYNOPSIS:** Add a semantic validation prompt that enforces the real `PH-001` judge guidance.
  - **BECAUSE:** The methodology phase definition includes failure modes that deterministic checks cannot catch.
  - **STATUS:** `completed`

- **TASK: TASK-11**
  - **SYNOPSIS:** Encode the real semantic failure modes:
    - vague acceptance criteria
    - orphaned inventory items
    - assumption conflicts
    - scope creep
    - missing dependencies
  - **BECAUSE:** These are the actual `judge_guidance` items in the phase definition.
  - **STATUS:** `completed`

- **TASK: TASK-12**
  - **SYNOPSIS:** Define the validation outputs for the prompt pair.
  - **BECAUSE:** The phase needs a stable pass/revise artifact or verdict, not free-form commentary.
  - **STATUS:** `completed`

- **TASK: TASK-13**
  - **SYNOPSIS:** Require concrete revision feedback when the verdict is `revise`.
  - **BECAUSE:** Downstream iteration only works if the generator can apply specific corrections rather than vague criticism.
  - **STATUS:** `completed`

- **DONE-WHEN: DONE-4**
  - **SYNOPSIS:** The semantic validator can reject a structurally valid feature spec for real methodology reasons and explain exactly what to fix.
  - **BECAUSE:** That is the judgment role of the second half of the phase.
  - **STATUS:** `completed`

## Workstream 5: Build The Prompt Pair

- **GOAL: GOAL-6**
  - **SYNOPSIS:** Package the generator and validator as one prompt-runner pair for `PH-001`.
  - **BECAUSE:** This phase should run the same way the rebuilt `PH-000` harness now runs: generate, then validate, then pass or revise.
  - **STATUS:** `completed`

- **TASK: TASK-14**
  - **SYNOPSIS:** Create the `PH-001` prompt-runner input file with:
    - `### Generation Prompt`
    - `### Validation Prompt`
  - **BECAUSE:** That is the cleanest way to express the full phase contract in prompt-runner.
  - **STATUS:** `completed`

- **TASK: TASK-15**
  - **SYNOPSIS:** Use the real methodology file paths rather than `work/` scratch paths.
  - **BECAUSE:** `PH-001` is a real methodology phase, not an ad hoc harness.
  - **STATUS:** `completed`

- **TASK: TASK-16**
  - **SYNOPSIS:** Add one launcher script for `PH-001`.
  - **BECAUSE:** The repo should have one obvious entrypoint per real phase, not multiple overlapping helpers.
  - **STATUS:** `completed`

- **DONE-WHEN: DONE-5**
  - **SYNOPSIS:** There is one prompt-runner file and one launcher that execute the full `PH-001` phase.
  - **BECAUSE:** That keeps the flow stable and avoids the naming/script chaos we just cleaned up for `PH-000`.
  - **STATUS:** `completed`

## Workstream 6: Verify With Hello World

- **GOAL: GOAL-7**
  - **SYNOPSIS:** Prove the phase works on the Hello World example before generalizing further.
  - **BECAUSE:** A small concrete example is the cheapest way to verify the contract end-to-end.
  - **STATUS:** `completed`

- **TASK: TASK-17**
  - **SYNOPSIS:** Produce a valid phase-0 artifact using the chosen authoritative contract.
  - **BECAUSE:** `PH-001` cannot be tested without a real upstream inventory.
  - **STATUS:** `completed`

- **TASK: TASK-18**
  - **SYNOPSIS:** Run the full `PH-001` pair on Hello World.
  - **BECAUSE:** This verifies the generator, deterministic validator, semantic validator, and runner plumbing together.
  - **STATUS:** `completed`

- **TASK: TASK-19**
  - **SYNOPSIS:** Inject one deliberate `PH-001` failure and confirm the validator catches it.
  - **BECAUSE:** A negative test proves the revision loop is real, not just a happy-path pass.
  - **STATUS:** `completed`

- **DONE-WHEN: DONE-6**
  - **SYNOPSIS:** `PH-001` passes on the good artifact and revises on the bad artifact with concrete feedback.
  - **BECAUSE:** That is the minimum proof that the phase is realized correctly.
  - **STATUS:** `completed`

## Recommended Execution Order

- **PROCESS: PROCESS-2**
  - **SYNOPSIS:** Implement in this order:
    1. Align phase-0/phase-1 schema
    2. Finalize deterministic validator contract
    3. Write generation prompt
    4. Write semantic validation prompt
    5. Package as prompt pair
    6. Add launcher
    7. Run positive and negative tests
  - **BECAUSE:** Prompting before contract alignment will produce more drift and rework.
  - **STATUS:** `confirmed`

## Tracking

- **RULE: RULE-1**
  - **SYNOPSIS:** Status values used in this plan are:
    - `pending`
    - `in_progress`
    - `confirmed`
    - `completed`
    - `blocked`
  - **BECAUSE:** The plan is intended to be executed directly and needs stable tracking labels.

- **GOAL: GOAL-8**
  - **SYNOPSIS:** Current execution focus has been completed through Workstream 6 verification.
  - **BECAUSE:** The phase now has a clean passing run and a verified negative case.
  - **STATUS:** `completed`

## Bottom Line

- **GOAL: GOAL-9**
  - **SYNOPSIS:** Realizing `PH-001` means building one real methodology prompt pair on top of one stable upstream `PH-000` contract.
  - **BECAUSE:** Once the contract is stable, the rest is straightforward: generate the feature spec, validate it mechanically and semantically, and iterate until pass.
  - **STATUS:** `completed`
