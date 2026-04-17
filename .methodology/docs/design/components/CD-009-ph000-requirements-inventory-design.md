# Design: PH-000 Requirements Inventory

## 1. Finality

This design explains how `PH-000` works from start to finish.

- **GOAL: GOAL-1** Produce the requirements inventory
  - **SYNOPSIS:** `PH-000` turns the raw requirements into one
    acceptance-ready `docs/requirements/requirements-inventory.yaml` file.
  - **BECAUSE:** Later phases depend on this file.

## 2. Inputs And Outputs

This section names the files that the phase uses.

- **FILE: FILE-1** Raw requirements
  - **SYNOPSIS:** Primary input:
    - `{{raw_requirements_path}}`
  - **BECAUSE:** The input path comes from the request. The design should not
    hardcode one source path.

- **FILE: FILE-2** Requirements inventory
  - **SYNOPSIS:** Primary output:
    - `docs/requirements/requirements-inventory.yaml`
  - **BECAUSE:** This is the phase output.

- **FILE: FILE-3** Prompt-runner module
  - **SYNOPSIS:** `.methodology/docs/prompts/PR-025-ph000-requirements-inventory.md`
    with:
    - embedded generator agent definition
    - embedded judge agent definition
    - request-specific placeholders such as `{{raw_requirements_path}}`
  - **BECAUSE:** PH-000 uses one predefined prompt-runner module. The module
    contains the agent setup. The request fills in the placeholders.

## 3. Technical Directives

This section states the technical directives that shape the phase
implementation.

- **RULE: RULE-1** Read the raw requirements from a placeholder path
  - **SYNOPSIS:** The phase must read the source document from
    `{{raw_requirements_path}}`.
  - **BECAUSE:** The input path is request-specific.

- **RULE: RULE-2** Use the predefined prompt module
  - **SYNOPSIS:** The phase must use
    `.methodology/docs/prompts/PR-025-ph000-requirements-inventory.md`.
  - **BECAUSE:** PH-000 should not build a new prompt module for each run.

- **RULE: RULE-3** Keep the generator and judge setup inside the module
  - **SYNOPSIS:** The prompt module must contain the `Generator Agent` and
    `Judge Agent` definitions, the shared traceability skill reference, and
    the PH-000-specific extraction and review rules.
  - **BECAUSE:** The module should be self-contained.

- **RULE: RULE-4** Write one inventory file
  - **SYNOPSIS:** The phase must write exactly one file at
    `docs/requirements/requirements-inventory.yaml`.
  - **BECAUSE:** Later phases need one stable input file.

## 4. Workflow

This section describes the phase steps.

- **PROCESS: PROCESS-1** Define the phase contract
  - **SYNOPSIS:** `PH-000` defines the input path, output path, extraction
    rules, judge rules, and output shape.
  - **READS:** `.methodology/src/cli/methodology_runner/phases.py`
    - **BECAUSE:** The phase registry is the source of truth.
  - **BECAUSE:** The run needs this contract before it starts.

- **PROCESS: PROCESS-2** Execute the prompts with prompt-runner
  - **SYNOPSIS:** The methodology runner fills in the request placeholders in
    the predefined PH-000 module, then runs that module with prompt-runner.
  - **USES:** `.methodology/src/cli/methodology_runner/orchestrator.py`
    - **BECAUSE:** The orchestrator owns the phase lifecycle and
      prompt-runner invocation.
  - **USES:** `.prompt-runner/src/cli/prompt_runner/runner.py`
    - **BECAUSE:** That module executes the generator/judge revision loop.
  - **PROMPT-MODULE: PMOD-1** PH-000 prompt-runner input file
    - **SYNOPSIS:** The PH-000 prompt-runner input file is
      `.methodology/docs/prompts/PR-025-ph000-requirements-inventory.md`,
      executed as a checked-in prompt module with run-time placeholder values.
    - **BECAUSE:** The phase should keep one fixed module shape and only fill
      in request values.
    - **READS:** `{{raw_requirements_path}}`
      - **BECAUSE:** The source path is a request value.
    - **AGENT:** `Generator Agent`
      - **SYNOPSIS:** Embedded generator definition in the PH-000 module.
      - **BECAUSE:** The generator setup is fixed for this phase.
      - **SKILLS:** `traceability-discipline`
        - **SYNOPSIS:** Enforce exact quotes, source locations, coverage
          mapping, and assumption handling.
        - **BECAUSE:** PH-000 must stay close to the source text.
      - **RULE:** Prompt-local extraction directives
        - **SYNOPSIS:** The module itself defines the PH-000 extraction walk,
          split conditions, category rules, and anti-invention rules.
        - **BECAUSE:** PH-000-specific extraction behavior now lives in the
          prompt, not in a phase-only skill.
    - **AGENT:** `Judge Agent`
      - **SYNOPSIS:** Embedded judge definition in the PH-000 module.
      - **BECAUSE:** The judge setup is fixed for this phase.
      - **SKILLS:** `traceability-discipline`
        - **BECAUSE:** The judge also needs the same quote and source rules.
      - **RULE:** Prompt-local review directives
        - **SYNOPSIS:** The module itself defines the PH-000 review passes,
          blocking defect types, and precedence between quote fidelity and
          splitting.
        - **BECAUSE:** PH-000-specific review behavior now lives in the
          prompt, not in a phase-only skill.
    - **PROMPT-PAIR: Prompt 1**
      - **PROMPT:** `Generator`
        - **SYNOPSIS:** Reads `{{raw_requirements_path}}` and
          writes `docs/requirements/requirements-inventory.yaml`.
        - **BECAUSE:** The generator owns artifact production.
        - **USES:** `Generator Agent`
          - **BECAUSE:** The prompt pair should use the embedded generator
            definition already declared in the prompt module.
        - **USES:** `traceability-discipline`
          - **BECAUSE:** The generator needs the traceability discipline
            already defined under the generator agent definition.
        - **USES:** prompt-local PH-000 extraction directives
          - **BECAUSE:** The generator's phase-specific behavior is embedded
            in the module.
      - **PROMPT:** `Judge`
        - **SYNOPSIS:** Reviews omissions, invention, unsplit compounds,
          category drift, traceability defects, and structural defects.
        - **BECAUSE:** The judge decides whether the file passes or needs
          another revision.
        - **USES:** `Judge Agent`
          - **BECAUSE:** The prompt pair should use the embedded judge
            definition already declared in the prompt module.
        - **USES:** `traceability-discipline`
          - **BECAUSE:** The judge needs the traceability discipline already
            defined under the judge agent definition.
        - **USES:** prompt-local PH-000 review directives
          - **BECAUSE:** The judge's phase-specific behavior is embedded in
            the module.
  - **READS:** embedded prompt-file agent definitions
    - **BECAUSE:** PH-000 keeps its fixed generator and judge setup in the
      module.
  - **READS:** instantiated request-specific placeholders
    - **BECAUSE:** The run must resolve values such as
      `{{raw_requirements_path}}` before executing the generator and judge
      prompts.
  - **LAUNCHES:** generator session
    - **BECAUSE:** The artifact must be produced before it can be judged.
  - **LAUNCHES:** judge session
    - **BECAUSE:** The artifact must be reviewed for phase readiness and either
      passed, revised, or escalated.
  - **RESUMES:** the same artifact path across iterations
    - **BECAUSE:** PH-000 revises the same output file. It does not create
      draft variants.
- **PROCESS: PROCESS-3** Accept or reject the phase result
  - **SYNOPSIS:** The phase is accepted only when the prompt-runner loop passes
    and the resulting artifact is accepted as the phase output.
  - **VALIDATES:** `docs/requirements/requirements-inventory.yaml`
    - **BECAUSE:** The output file must exist before the phase can pass.
  - **USES:** `.methodology/src/cli/methodology_runner/phase_0_validation.py`
    - **BECAUSE:** PH-000 uses deterministic checks for schema, IDs, coverage
      bookkeeping, and exact-quote presence.
  - **BECAUSE:** PH-000 passes only when both the deterministic checks and the
    judge review pass.
  - **PRODUCES:** `docs/requirements/requirements-inventory.yaml`
    - **BECAUSE:** That artifact is the durable output consumed by `PH-001` and
      later cross-reference checks.

## 5. Constraints

This section states the main limits on the phase.

- **RULE: RULE-5** No invention
  - **SYNOPSIS:** The phase must not add details that are not in the source.
  - **BECAUSE:** PH-000 is an extraction phase.

- **RULE: RULE-6** No paraphrase
  - **SYNOPSIS:** `verbatim_quote` must keep the source wording exactly.
  - **BECAUSE:** Later phases need exact traceability.

- **RULE: RULE-7** One fixed prompt module
  - **SYNOPSIS:** PH-000 must use the predefined prompt module instead of
    building a new module per run.
  - **BECAUSE:** The module shape should stay stable.

## 6. Output Shape

This section states what the output file contains.

- **ENTITY: ENTITY-1** Top-level output shape
  - **SYNOPSIS:** The top-level sections are:
    - `source_document`
    - `items`
    - `out_of_scope`
    - `coverage_check`
    - `coverage_verdict`
  - **BECAUSE:** That is the schema required by the PH-000 phase contract.

- **ENTITY: ENTITY-2** Inventory item fields
  - **SYNOPSIS:** Each `RI-*` item contains:
    - `id`
    - `category`
    - `verbatim_quote`
    - `source_location`
    - `tags`
    - `rationale`
    - `open_assumptions`
  - **BECAUSE:** Those are the fields the downstream phases and validations
    rely on.

## 7. Definition Of Good

This section states when the phase passes.

- **RULE: RULE-8** Completeness
  - **SYNOPSIS:** Every requirement-bearing statement in the raw requirements
    must appear as at least one `RI-*` item.
  - **BECAUSE:** Later phases can only trace and group what PH-000 actually
    inventories.

- **RULE: RULE-9** Atomicity
  - **SYNOPSIS:** Compound requirements must be split into separate `RI-*`
    items when they contain independently satisfiable requirement-bearing
    clauses.
  - **BECAUSE:** Later phases need inventory items with stable, reviewable
    boundaries.

- **RULE: RULE-10** Output file only
  - **SYNOPSIS:** The phase passes only if it writes exactly one
    `docs/requirements/requirements-inventory.yaml` file for the artifact.
  - **BECAUSE:** Later phases need one stable file.

- **RULE: RULE-11** Deterministic and judge checks both pass
  - **SYNOPSIS:** The phase passes only if the deterministic validator passes
    and the judge returns `VERDICT: pass`.
  - **BECAUSE:** PH-000 needs both shape checks and content checks.

## 8. Test Cases

This section lists the tests the phase design expects.

- **TEST CASE: TC-1** Placeholder input path
  - **SYNOPSIS:** Instantiate the module with a non-default
    `{{raw_requirements_path}}` and confirm the generator reads that path.
  - **BECAUSE:** The design now depends on templated input paths.

- **TEST CASE: TC-2** Embedded agent definitions
  - **SYNOPSIS:** Confirm the PH-000 module contains both `Generator Agent`
    and `Judge Agent`, the shared `traceability-discipline` skill, and the
    PH-000-specific prompt-local directives.
  - **BECAUSE:** The module is supposed to be self-contained.

- **TEST CASE: TC-3** One-file output
  - **SYNOPSIS:** Run PH-000 and confirm the artifact written is
    `docs/requirements/requirements-inventory.yaml`.
  - **BECAUSE:** The phase should produce one stable output file.

- **TEST CASE: TC-4** Deterministic validation
  - **SYNOPSIS:** Run the phase with a malformed inventory and confirm
    `.methodology/src/cli/methodology_runner/phase_0_validation.py` fails it.
  - **BECAUSE:** Shape errors should fail before semantic acceptance.

- **TEST CASE: TC-5** Judge revise loop
  - **SYNOPSIS:** Run the phase with an inventory that omits a requirement and
    confirm the judge asks for revision instead of passing it.
  - **BECAUSE:** PH-000 must catch content omissions.
