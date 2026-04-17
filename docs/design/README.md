# Design Relationships

## 1. Purpose

This document identifies the active design authorities, the scope each
one owns, and the dependency order between them.

- **RULE: RULE-0** `CD-*` files are design specifications, not implementation artifacts.
  - **SYNOPSIS:** Component design documents define how component parts need to
    be built and which workflow, responsibilities, and acceptance boundaries
    the implementation must satisfy.
  - **BECAUSE:** The methodology needs a clear distinction between design
    authority and the code or prompt artifacts that realize that design.

- **RULE: RULE-0A** Supporting prompts, skills, and Python files are implementation/code artifacts.
  - **SYNOPSIS:** Prompt-runner input files, skill files, and Python modules are
    code-like operational artifacts that implement or execute the behavior
    described by the design specs.
  - **BECAUSE:** They are the mechanisms used to realize the design, not the
    design authority itself.

- **RULE: RULE-0B** Additional spec types may exist beyond `CD-*`, but this document starts by distinguishing component design specs from their supporting code artifacts.
  - **BECAUSE:** The design stack will likely grow more spec layers over time,
    but the first necessary boundary is between component design authority and
    implementation artifacts.

## 2. Active Design Stack

This section lists the active design documents in the order they should
usually be read.

- **FILE: FILE-1** `.prompt-runner/docs/design/components/CD-006-prompt-runner-core.md`
  - **SYNOPSIS:** Generic `prompt_runner` design.
  - **BECAUSE:** Every methodology-specific design depends on the
    generic runner capabilities and concepts first.

- **FILE: FILE-2** `CD-003-methodology-run.md`
  - **SYNOPSIS:** Generic structure of one `MethodologyRun`, including
    `run_dir`, `worktree_dir`, top-level run artifacts, and deterministic
    run completion logic.
  - **DEPENDS-ON:** `FILE-1`
    - **BECAUSE:** Methodology orchestration uses `prompt_runner` and its
      surrounding runtime concepts.

- **FILE: FILE-3** `HLD-001-methodology-prompt-optimization.md`
  - **SYNOPSIS:** Optimization-exercise design that organizes one
    baseline run plus later variant runs derived from it.
  - **DEPENDS-ON:** `FILE-2`
    - **BECAUSE:** Baseline and variant runs are both specialized uses
      of the generic `MethodologyRun`.

- **FILE: FILE-4** `CD-004-methodology-standalone-step-harness.md`
  - **SYNOPSIS:** Design for replaying one methodology step in isolation
    from a trusted baseline run.
  - **DEPENDS-ON:** `FILE-2`
    - **BECAUSE:** The harness reuses one methodology run's worktree and
      artifacts.
  - **DEPENDS-ON:** `FILE-3`
    - **BECAUSE:** The harness assumes a baseline run that later variant
      work can compare against.

- **FILE: FILE-5** `HLD-003-methodology-workflow.md`
  - **SYNOPSIS:** Prompt-driven workflow that establishes the baseline
    run, produces planning artifacts, validates the harness, and prepares
    bounded step-lab work.
  - **DEPENDS-ON:** `FILE-2`
    - **BECAUSE:** The workflow must know what one methodology run is
      and what artifacts it produces.
  - **DEPENDS-ON:** `FILE-3`
    - **BECAUSE:** The workflow assigns the baseline role and prepares
      later variant-oriented optimization work.
  - **DEPENDS-ON:** `FILE-4`
    - **BECAUSE:** The workflow includes the standalone step harness as
      one of its core stages.

- **FILE: FILE-6** `CD-005-methodology-supervision.md`
  - **SYNOPSIS:** Supervisory layer that retries, resumes, or restarts
    the methodology workflow when needed.
  - **DEPENDS-ON:** `FILE-5`
    - **BECAUSE:** Supervision exists to control the methodology
      workflow, not to replace it.

- **FILE: FILE-7** `HLD-002-methodology-execution-architecture.md`
  - **SYNOPSIS:** Runtime process view that explains how the launcher,
    supervision runner, workflow runner, methodology runner, and harness
    process fit together.
  - **DEPENDS-ON:** `FILE-1`
    - **BECAUSE:** The runtime architecture includes `prompt_runner` as
      one of its main substrates.
  - **DEPENDS-ON:** `FILE-3`
    - **BECAUSE:** The runtime architecture includes the exercise-root
      layout that contains the baseline and later variant run
      directories.
  - **DEPENDS-ON:** `FILE-5`
    - **BECAUSE:** The runtime architecture needs the workflow stages
      before it can explain which process runs them.
  - **DEPENDS-ON:** `FILE-6`
    - **BECAUSE:** The runtime architecture includes the supervision
      layer as one of its main processes.

## 3. Scope Boundaries

This section clarifies which document should answer which kind of
question.

- **RULE: RULE-1** Read `.prompt-runner/docs/design/components/CD-006-prompt-runner-core.md` for generic runner questions.
  - **BECAUSE:** Generic runner behavior should not be redefined in the
    methodology-specific documents.

- **RULE: RULE-2** Read `CD-003-methodology-run.md` for questions about one run.
  - **BECAUSE:** The generic run document is the authority for `run_dir`,
    `worktree_dir`, run-level artifacts, and run completion logic.

- **RULE: RULE-3** Read `HLD-001-methodology-prompt-optimization.md` for questions about baseline and variant organization.
  - **BECAUSE:** The optimization document is the authority for how one
    exercise groups the baseline run and later variants.

- **RULE: RULE-4** Read `CD-004-methodology-standalone-step-harness.md` for isolated replay questions.
  - **BECAUSE:** The harness design is the authority for one-step replay
    and replay artifacts.

- **RULE: RULE-5** Read `HLD-003-methodology-workflow.md` for stage-ordering questions.
  - **BECAUSE:** The workflow design is the authority for the sequence
    baseline -> planning -> harness -> step-lab planning.

- **RULE: RULE-6** Read `CD-005-methodology-supervision.md` for retry and resume questions above the workflow.
  - **BECAUSE:** The supervision design is the authority for
    workflow-level recovery behavior.

- **RULE: RULE-7** Read `HLD-002-methodology-execution-architecture.md` for process and filesystem questions across the whole runtime.
  - **BECAUSE:** The architecture document is the authority for launcher
    behavior, long-running processes, and the runtime call chain.

## 4. Active Plans

This section lists the active plans that track implementation or
execution rather than defining the design authorities above.

- **FILE: FILE-8** `docs/plans/PLAN-002-methodology-implementation.md`
  - **SYNOPSIS:** Implementation workstreams and validation ladder for
    bringing code into line with the active design stack.

- **FILE: FILE-9** `docs/plans/PLAN-003-methodology-project.md`
  - **SYNOPSIS:** Goal hierarchy and work breakdown structure for the
    methodology effort.

- **FILE: FILE-10** `docs/plans/PLAN-004-tiny-baseline-run.md`
  - **SYNOPSIS:** Focused execution plan for proving the tiny baseline
    run and its handoff artifacts.

## 5. Retired Material

This section explains where superseded material lives.

- **RULE: RULE-8** Historical or superseded material lives under `docs/plans/retired/`.
  - **BECAUSE:** Active design authorities should not be mixed with
    retired plans or stale design chains.

- **RULE: RULE-9** Structured review outputs live under `docs/reviews/`.
  - **BECAUSE:** Review artifacts are not design authorities or implementation plans and should not be mixed into those layers.
