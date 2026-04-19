# Tool Packaging And Sample Distribution Plan

## Purpose

This plan reorganizes the work into the order we would actually execute
it.

The target shape is:

- `tools/prompt-runner/` as a real installable tool
- `tools/methodology-runner/` as a real installable tool
- `sample/hello-world/` as a compact reference bundle
- `project/` as the promotion target for real implementation output

It also keeps a clean fallback option:

- if the current repo still leaks too much internal coupling after the
  packaging work, create a new user-facing repo under `~/dev/` and move
  only the clean product surfaces there

## GOAL: GOAL-1
- **SYNOPSIS:** Use an install-first product model.
- **BECAUSE:** Users should be able to install the tools and point them
  at their own work without relying on this repo's internal layout.

### RULE: RULE-1
- **SYNOPSIS:** The main user path is installed tools, not source-tree
  execution.
- **BECAUSE:** Installed commands are the real user contract.

### RULE: RULE-2
- **SYNOPSIS:** The sample is a reference workflow, not the main product
  interface.
- **BECAUSE:** Users should not have to reverse-engineer usage from the
  example bundle.

### RULE: RULE-3
- **SYNOPSIS:** Source-tree execution remains a contributor path.
- **BECAUSE:** Contributors and users have different needs.

### ANSWER
- **SYNOPSIS:** Start with in-place cleanup and packaging in this repo.
- **BECAUSE:** The current top-level split is already close to the right
  shape. A second repo is only worth it if packaging still exposes too
  much hidden coupling after the cleanup work is done.

## GOAL: GOAL-2
- **SYNOPSIS:** Stabilize `tools/prompt-runner/` first.
- **BECAUSE:** It is the smaller tool and it is the dependency boundary
  that methodology-runner sits on top of.

### SUBGOAL: SUBGOAL-1
- **SYNOPSIS:** Make prompt-runner installable and runnable on its own.
- **BECAUSE:** Methodology-runner should depend on a stable tool
  boundary, not on an in-repo implementation detail.

#### TASK: TASK-1
- **SYNOPSIS:** Add or finalize `pyproject.toml` and console entry
  points for `tools/prompt-runner/`.
- **STATUS:** `todo`

#### TASK: TASK-2
- **SYNOPSIS:** Remove remaining repo-root-specific assumptions from
  prompt-runner imports, docs, tests, and examples.
- **STATUS:** `todo`

#### TASK: TASK-3
- **SYNOPSIS:** Verify `pip install -e tools/prompt-runner` and run the
  prompt-runner test suite from that installed context.
- **STATUS:** `todo`

#### TASK: TASK-4
- **SYNOPSIS:** Run one end-to-end prompt-runner smoke against
  `sample/hello-world/` from the installed tool.
- **STATUS:** `todo`

## GOAL: GOAL-3
- **SYNOPSIS:** Stabilize `tools/methodology-runner/` second.
- **BECAUSE:** It depends on prompt-runner and has broader orchestration
  and path-resolution concerns.

### SUBGOAL: SUBGOAL-2
- **SYNOPSIS:** Make methodology-runner installable and usable against
  an external project directory.
- **BECAUSE:** Users should be able to run the methodology from the
  tool, not from this repo's source tree.

#### TASK: TASK-5
- **SYNOPSIS:** Add or finalize `pyproject.toml` and console entry
  points for `tools/methodology-runner/`.
- **STATUS:** `todo`

#### TASK: TASK-6
- **SYNOPSIS:** Replace remaining repo-internal path assumptions with
  tool-owned relative paths or explicit user-supplied paths.
- **STATUS:** `todo`

#### TASK: TASK-7
- **SYNOPSIS:** Verify `pip install -e tools/methodology-runner` with
  prompt-runner installed as a dependency or sibling editable package.
- **STATUS:** `todo`

#### TASK: TASK-8
- **SYNOPSIS:** Run PH-000 through PH-007 against
  `sample/hello-world/fixtures/...` from installed tooling.
- **STATUS:** `todo`

## GOAL: GOAL-4
- **SYNOPSIS:** Tighten the sample boundary.
- **BECAUSE:** The sample should stay small, coherent, and clearly
  secondary to the tools.

### SUBGOAL: SUBGOAL-3
- **SYNOPSIS:** Keep `sample/hello-world/` as one self-contained
  reference bundle.
- **BECAUSE:** One good sample is more useful than several drifting
  examples.

#### TASK: TASK-9
- **SYNOPSIS:** Keep only one curated example under
  `sample/hello-world/` unless a second example proves a distinct user
  path or capability.
- **STATUS:** `todo`

#### TASK: TASK-10
- **SYNOPSIS:** Remove or archive obsolete example assets that are no
  longer part of the supported sample path.
- **STATUS:** `todo`

#### TASK: TASK-11
- **SYNOPSIS:** Add one short sample README that explains:
  - what the sample contains
  - which command to run first
  - which outputs are expected
- **STATUS:** `todo`

## GOAL: GOAL-5
- **SYNOPSIS:** Clean the root layout so the public structure matches
  the product model.
- **BECAUSE:** Even packaged tools will look unfinished if the root of
  the repo still contains old run trees and stray scratch directories.

### SUBGOAL: SUBGOAL-4
- **SYNOPSIS:** Remove or relocate root clutter that is not part of the
  intended product surface.
- **BECAUSE:** The root should expose only meaningful top-level areas.

#### TASK: TASK-12
- **SYNOPSIS:** Move or archive historical generated directories such as
  `runs/`, `tmp/`, and `relative/`.
- **STATUS:** `todo`

#### TASK: TASK-13
- **SYNOPSIS:** Decide whether `plugins/` remains a real root category
  or should be removed because it is currently unused.
- **STATUS:** `todo`

#### TASK: TASK-14
- **SYNOPSIS:** Re-evaluate root `scripts/` and `tests/` and keep them
  only if they are truly repo-wide rather than tool-owned.
- **STATUS:** `todo`

## GOAL: GOAL-6
- **SYNOPSIS:** Publish a simple user-facing setup story.
- **BECAUSE:** The structure is only useful if users can understand how
  to consume it.

### SUBGOAL: SUBGOAL-5
- **SYNOPSIS:** Document the normal external-user flow.
- **BECAUSE:** The migration should reduce tribal knowledge, not move it
  around.

#### TASK: TASK-15
- **SYNOPSIS:** Add or update root documentation that explains:
  - what `prompt-runner` does
  - what `methodology-runner` does
  - how to install both
  - how to run them against another project
  - where `sample/hello-world/` fits
- **STATUS:** `todo`

#### TASK: TASK-16
- **SYNOPSIS:** Make external usage docs prefer installed-tool commands
  over `PYTHONPATH=... python -m ...`.
- **STATUS:** `todo`

## GOAL: GOAL-7
- **SYNOPSIS:** Keep a clean fallback path to a new repo.
- **BECAUSE:** If the current repo remains too coupled after the
  packaging work, a fresh repo is the cleaner user-facing boundary.

### SUBGOAL: SUBGOAL-6
- **SYNOPSIS:** Define the cutover trigger and the fallback move set.
- **BECAUSE:** The new-repo option should be ready, not improvised.

#### RULE: RULE-4
- **SYNOPSIS:** Create a new repo under `~/dev/` only if the installed
  tools still depend on internal repo context after TASK-1 through
  TASK-16.
- **BECAUSE:** A second repo adds maintenance cost and should only be
  justified by a real boundary problem.

#### TASK: TASK-17
- **SYNOPSIS:** If the cutover is needed, create a new repo and import
  only:
  - `tools/prompt-runner/`
  - `tools/methodology-runner/`
  - `sample/hello-world/`
  - minimal repo-level docs
- **STATUS:** `todo`

#### TASK: TASK-18
- **SYNOPSIS:** Leave the current repo as the development and history
  repo if that separation remains useful.
- **STATUS:** `todo`

## GOAL: GOAL-8
- **SYNOPSIS:** Define completion criteria.
- **BECAUSE:** The migration should stop at a clear, testable point.

### SUBGOAL: SUBGOAL-7
- **SYNOPSIS:** The structure is done when these checks pass.
- **BECAUSE:** These conditions prove the repo now matches the intended
  product model.

#### TASK: TASK-19
- **SYNOPSIS:** Both tools install cleanly from their tool folders.
- **STATUS:** `todo`

#### TASK: TASK-20
- **SYNOPSIS:** Both tool test suites pass from installed-tool
  contexts.
- **STATUS:** `todo`

#### TASK: TASK-21
- **SYNOPSIS:** The sample runs end to end without hidden dependence on
  obsolete root folders.
- **STATUS:** `todo`

#### TASK: TASK-22
- **SYNOPSIS:** The root layout is reduced to intentional top-level
  areas: `tools/`, `sample/`, `project/`, `docs/`, `work/`, `.archive/`,
  and only truly repo-wide support folders.
- **STATUS:** `todo`

#### TASK: TASK-23
- **SYNOPSIS:** A new user can understand the product model from the
  repo README and the two tool READMEs without reading old plans or
  internal notes.
- **STATUS:** `todo`
