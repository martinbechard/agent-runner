# Repository Structure Reorganization Plan

## Purpose

This plan describes how to separate the repository into three explicit
products:

- `tools/prompt-runner/`
- `tools/methodology-runner/`
- `project/`

It also keeps `work/` as the transient run area and limits root `docs/`
to repository-level material only.

## Goal 1: Establish the target topology

- **GOAL:** Make the repository layout match the real product boundaries.
  - **CHAIN-OF-THOUGHT:** `prompt-runner`, `methodology-runner`, and the
    software being built are different products with different source,
    tests, docs, and runtime artifacts. A shared mixed layout hides
    those boundaries and makes ownership unclear.
  - **BECAUSE:** The repository should make it obvious which files
    belong to the prompt tool, which belong to the methodology engine,
    and which belong to the actual built software.

### Subgoal 1.1: Define the top-level homes

- **SUBGOAL:** Adopt one canonical top-level home per major concern.
  - **BECAUSE:** The migration needs a stable target before any files
    move.
- **TASK:** Reserve `tools/prompt-runner/` for all prompt-runner-owned
  code, tests, docs, example prompt files, and tool-local scripts.
  - **STATUS:** `todo`
- **TASK:** Reserve `tools/methodology-runner/` for all
  methodology-runner-owned code, tests, fixtures, prompts, design docs,
  and skills.
  - **STATUS:** `todo`
- **TASK:** Reserve `project/` for the actual implementation produced by
  the methodology workflow.
  - **STATUS:** `todo`
- **TASK:** Keep `work/` as the git-ignored home for generated runs,
  experiment workspaces, and forensic execution artifacts.
  - **STATUS:** `todo`
- **TASK:** Keep root `docs/` for repository-level documents only.
  - **STATUS:** `todo`

### Subgoal 1.2: Define what should stop living at the root

- **SUBGOAL:** Remove the current hidden-tool and mixed-ownership
  layout.
  - **BECAUSE:** The migration is not complete if the old layout remains
    the implicit source of truth.
- **TASK:** Retire `.prompt-runner/` as the long-term home of the
  prompt-runner product.
  - **STATUS:** `todo`
- **TASK:** Retire `.methodology/` as the long-term home of the
  methodology-runner product.
  - **STATUS:** `todo`
- **TASK:** Stop treating `tests/fixtures/` as a general holding area
  for methodology fixtures after they are migrated into the
  methodology-runner product tree.
  - **STATUS:** `todo`
- **TASK:** Move tool-specific root `scripts/` entries into the owning
  tool tree, leaving only repo-wide scripts at the root.
  - **STATUS:** `todo`

## Goal 2: Relocate prompt-runner into its own product tree

- **GOAL:** Move prompt-runner into an explicit non-hidden tool home.
  - **BECAUSE:** Prompt-runner is a first-class tool and should not look
    like an internal dot-directory.

### Subgoal 2.1: Move prompt-runner source and tests

- **SUBGOAL:** Mirror the prompt-runner product structure under
  `tools/prompt-runner/`.
  - **BECAUSE:** Source, tests, docs, and scripts should stay together.
- **TASK:** Move `.prompt-runner/src/cli/prompt_runner/` to
  `tools/prompt-runner/src/prompt_runner/`.
  - **STATUS:** `todo`
- **TASK:** Move `.prompt-runner/tests/cli/prompt_runner/` to
  `tools/prompt-runner/tests/`.
  - **STATUS:** `todo`
- **TASK:** Move `.prompt-runner/README.md` to
  `tools/prompt-runner/README.md`.
  - **STATUS:** `todo`
- **TASK:** Move `.prompt-runner/docs/` to
  `tools/prompt-runner/docs/`.
  - **STATUS:** `todo`
- **TASK:** Move any prompt-runner-local plan or workflow reference
  files into `tools/prompt-runner/docs/` or
  `tools/prompt-runner/workflows/` based on purpose.
  - **STATUS:** `todo`

### Subgoal 2.2: Cut prompt-runner references over

- **SUBGOAL:** Update all references to the new prompt-runner home.
  - **BECAUSE:** Moving files without fixing import, command, and doc
    references will break the tool.
- **TASK:** Update Python import roots, `PYTHONPATH` examples, and test
  commands to use `tools/prompt-runner/src/`.
  - **STATUS:** `todo`
- **TASK:** Update docs, scripts, and methodology references that point
  at `.prompt-runner/...`.
  - **STATUS:** `todo`
- **TASK:** Keep run artifacts in workspace-local `.run-files/`, not
  under the tool source tree.
  - **STATUS:** `todo`

## Goal 3: Relocate methodology-runner into its own product tree

- **GOAL:** Move methodology-runner into an explicit non-hidden tool
  home.
  - **BECAUSE:** The methodology system is also a first-class product,
    not a dot-directory sidecar.

### Subgoal 3.1: Move methodology source, prompts, and design docs

- **SUBGOAL:** Place all methodology-owned runtime and reference files
  under `tools/methodology-runner/`.
  - **BECAUSE:** The methodology product owns its prompts, validators,
    and design canon.
- **TASK:** Move `.methodology/src/cli/methodology_runner/` to
  `tools/methodology-runner/src/methodology_runner/`.
  - **STATUS:** `todo`
- **TASK:** Move `.methodology/docs/prompts/` to
  `tools/methodology-runner/docs/prompts/`.
  - **STATUS:** `todo`
- **TASK:** Move `.methodology/docs/design/` to
  `tools/methodology-runner/docs/design/`.
  - **STATUS:** `todo`
- **TASK:** Move `.methodology/docs/M-*.md` and
  `.methodology/docs/M-*.yaml` to `tools/methodology-runner/docs/`.
  - **STATUS:** `todo`
- **TASK:** Move `.methodology/skills/` to
  `tools/methodology-runner/skills/`.
  - **STATUS:** `todo`

### Subgoal 3.2: Move methodology tests, fixtures, and scripts

- **SUBGOAL:** Stop splitting methodology-owned verification assets
  across the root tree.
  - **BECAUSE:** Tool ownership should be visible from the path alone.
- **TASK:** Move `.methodology/tests/cli/methodology_runner/` to
  `tools/methodology-runner/tests/`.
  - **STATUS:** `todo`
- **TASK:** Move methodology-only fixtures from `tests/fixtures/` to
  `tools/methodology-runner/fixtures/`.
  - **STATUS:** `todo`
- **TASK:** Move methodology-only root scripts to
  `tools/methodology-runner/scripts/`.
  - **STATUS:** `todo`
- **TASK:** Leave only genuinely repo-wide tests or scripts at the root.
  - **STATUS:** `todo`

### Subgoal 3.3: Cut methodology references over

- **SUBGOAL:** Update all execution paths to the new methodology home.
  - **BECAUSE:** The move is only valid if prompt-runner, scripts, and
    tests can still invoke methodology-runner correctly.
- **TASK:** Update imports, launcher commands, and `PYTHONPATH`
  examples to use `tools/methodology-runner/src/`.
  - **STATUS:** `todo`
- **TASK:** Update references in docs, scripts, fixtures, and prompts
  that currently point at `.methodology/...`.
  - **STATUS:** `todo`
- **TASK:** Keep methodology run control state workspace-local under
  `.methodology-runner/` or an equivalent run-state directory, not under
  the tool source tree.
  - **STATUS:** `todo`

## Goal 4: Create a clean home for the actual built software

- **GOAL:** Separate generated or promoted application code from the
  methodology infrastructure.
  - **BECAUSE:** The thing being built should not live inside the tools
    that build it.

### Subgoal 4.1: Define `project/` as the canonical product tree

- **SUBGOAL:** Give final promoted software one obvious location.
  - **BECAUSE:** Generated code currently lands in `work/` workspaces
    and needs an explicit promotion target.
- **TASK:** Create `project/src/`, `project/tests/`, `project/docs/`,
  and `project/scripts/` as the default product layout.
  - **STATUS:** `todo`
- **TASK:** Define promotion rules from `work/<run>/...` into
  `project/` once a methodology run is accepted.
  - **STATUS:** `todo`
- **TASK:** Keep generated workspace code in `work/` until a deliberate
  promotion step copies it into `project/`.
  - **STATUS:** `todo`

### Subgoal 4.2: Keep project verification separate from tool verification

- **SUBGOAL:** Prevent the product test suite from being confused with
  tool tests.
  - **BECAUSE:** Methodology tests verify the engine; project tests
  verify the built software.
- **TASK:** Keep `project/tests/` for app tests only.
  - **STATUS:** `todo`
- **TASK:** Keep `tools/prompt-runner/tests/` and
  `tools/methodology-runner/tests/` for tool tests only.
  - **STATUS:** `todo`
- **TASK:** Reserve root `tests/` only for repo-wide integration checks
  if a real cross-product need remains after the migration.
  - **STATUS:** `todo`

## Goal 5: Update taxonomy, docs, and tooling around the new boundaries

- **GOAL:** Make the new layout self-describing and operationally
  stable.
  - **BECAUSE:** A path migration is incomplete if the repo rules and
  tooling still describe the old layout.

### Subgoal 5.1: Update the taxonomy and root guidance

- **SUBGOAL:** Reflect the new product split in repository guidance.
  - **BECAUSE:** New files should be placed correctly after the
  migration, not by tribal memory.
- **TASK:** Add taxonomy entries for `tools/prompt-runner/`,
  `tools/methodology-runner/`, their `src/`, `tests/`, `docs/`,
  `fixtures/`, and `scripts/` subtrees.
  - **STATUS:** `todo`
- **TASK:** Update `AGENTS.md` and any repo-level setup docs to describe
  the new product split once the move is real.
  - **STATUS:** `todo`
- **TASK:** Decide whether root `docs/plans/` remains repo-level only or
  whether tool-local plans should move under each tool's `docs/`.
  - **STATUS:** `todo`

### Subgoal 5.2: Update packaging and automation

- **SUBGOAL:** Keep commands, tests, and CI working after the moves.
  - **BECAUSE:** The reorganization should reduce confusion, not create
  a broken tree.
- **TASK:** Update any packaging metadata, editable-install paths, and
  invocation wrappers to point at `tools/prompt-runner/` and
  `tools/methodology-runner/`.
  - **STATUS:** `todo`
- **TASK:** Update any CI or local test commands that assume the current
  dot-directory layout.
  - **STATUS:** `todo`
- **TASK:** Add one repo-level smoke test that imports both tools from
  their new homes and runs a minimal prompt/methodology path.
  - **STATUS:** `todo`

## Goal 6: Execute the migration in bounded slices

- **GOAL:** Perform the reorganization without losing the ability to run
  tests or reason about failures.
  - **BECAUSE:** A full-tree move is risky if it happens in one opaque
  change.

### Subgoal 6.1: Migrate in product-first slices

- **SUBGOAL:** Break the migration into small, reviewable commits.
  - **BECAUSE:** That keeps failures local and keeps `git blame`
  meaningful.
- **TASK:** Slice 1: update taxonomy and repo-level guidance for the new
  target structure.
  - **STATUS:** `todo`
- **TASK:** Slice 2: move prompt-runner and repair its imports, tests,
  and docs.
  - **STATUS:** `todo`
- **TASK:** Slice 3: move methodology-runner and repair its imports,
  prompts, tests, fixtures, and scripts.
  - **STATUS:** `todo`
- **TASK:** Slice 4: introduce `project/` and document the promotion
  path from accepted `work/` runs.
  - **STATUS:** `todo`
- **TASK:** Slice 5: clean up any now-empty root folders and obsolete
  references.
  - **STATUS:** `todo`

### Subgoal 6.2: Define migration verification

- **SUBGOAL:** Prove that the new structure is operationally sound.
  - **BECAUSE:** The migration is successful only if both tools and the
  workflow still run.
- **TASK:** Run the prompt-runner unit suite from its new home.
  - **STATUS:** `todo`
- **TASK:** Run the methodology-runner unit suite from its new home.
  - **STATUS:** `todo`
- **TASK:** Parse all checked-in methodology prompt modules through the
  relocated prompt-runner.
  - **STATUS:** `todo`
- **TASK:** Run at least one PH-000 through PH-007 methodology path
  after the move.
  - **STATUS:** `todo`
- **TASK:** Run one PH-006 child-workflow implementation path and one
  PH-007 final verification path after the move.
  - **STATUS:** `todo`
- **TASK:** Confirm that accepted implementation outputs can be promoted
  from `work/` into `project/` without touching tool-owned paths.
  - **STATUS:** `todo`

## Goal 7: Define the end state clearly

- **GOAL:** Make the end state unambiguous before any file moves start.
  - **BECAUSE:** A migration without a crisp definition of done tends to
  leave old and new layouts mixed together.

### Subgoal 7.1: State the definition of done

- **SUBGOAL:** Finish with one clear repository contract.
  - **BECAUSE:** Reviewers need a concrete way to say the reorganization
  is complete.
- **TASK:** The migration is done when prompt-runner lives entirely
  under `tools/prompt-runner/`.
  - **STATUS:** `todo`
- **TASK:** The migration is done when methodology-runner lives entirely
  under `tools/methodology-runner/`.
  - **STATUS:** `todo`
- **TASK:** The migration is done when accepted built software has one
  canonical home under `project/`.
  - **STATUS:** `todo`
- **TASK:** The migration is done when `work/` contains only transient
  run artifacts and promoted code no longer depends on that tree.
  - **STATUS:** `todo`
- **TASK:** The migration is done when root `docs/`, `tests/`, and
  `scripts/` contain only repository-wide material that truly belongs at
  the root.
  - **STATUS:** `todo`
