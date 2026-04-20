# Strategy: File Management For Methodology Runs

## STR-001-1 Purpose

Define:

- the path forms the current methodology prompt modules actually use
- the current live file layout used by `methodology-runner`
- the boundary between steady-state application files, change-specific kept
  records, and runner-managed intermediate state
- the recommended post-run handling for repeated feature and fix work on the
  same application

## STR-001-2 Scope

This document separates two things that must not be conflated:

1. Current implementation behavior in the checked-in runner and prompt modules.
2. Recommended after-run promotion and retention policy for application work.

It is a file-management strategy, not a claim that every recommended path is
already implemented by the runner.

## STR-001-3 Definitions

- `application repo`
  - the git repository that owns the application's permanent history
- `application project directory`
  - an operator's primary checkout of the application repo, if one exists
  - this is a workflow concept outside the current methodology-runner internal
    model
- `application worktree`
  - the concrete directory used for one methodology run
  - current methodology-runner calls this the `workspace`
  - current orchestrator passes this same path to prompt-runner as
    `run_dir`, `source_project_dir`, and `worktree_dir`
  - the application worktree may be the project directory itself or a separate
    git worktree of the same application repo
- `change id`
  - a unique identifier for one feature, fix, or enhancement
- `working artifact`
  - a file written at its temporary in-run path inside the application
    worktree
- `change-specific kept artifact`
  - a file retained because it captures the reasoning, execution record, or
    verification record for one specific change
- `cumulative steady-state artifact`
  - a file retained because it describes the current application state across
    completed changes
- `runner control state`
  - live files needed to coordinate, inspect, or resume the current run
- `runner execution artifact`
  - generated logs, summaries, histories, and other evidence produced by the
    runner during execution

## STR-001-4 Current Execution Model

- Current methodology-runner uses one `application worktree` per run.
- Inside the current implementation, that one directory is used as:
  - the methodology workspace
  - the prompt-runner `run_dir`
  - the prompt-runner `source_project_dir`
  - the prompt-runner `worktree_dir`
- The current implementation does not internally maintain a separate persistent
  application project directory plus a second execution worktree.
- If an operator wants that split, it must currently be provided externally by
  using git worktrees around methodology-runner.

## STR-001-5 Current Prompt Module Path Forms

The checked-in methodology prompt modules currently use these path forms
directly:

| Raw Form In Prompt Modules | Meaning In Current Implementation |
|---|---|
| `docs/...` | Working methodology and application-support docs inside the application worktree |
| `../../../skills/...` | Bundled methodology skill files resolved relative to the prompt file location |
| `{{run_dir}}` | The current application worktree path |

The current prompt modules do not directly reference `.run-files/...` or
`.methodology-runner/...` paths.

## STR-001-6 Current Prompt Path Root Classes

| Row | Path Class | Raw Prefix In Prompt Modules | In-Run Root Template |
|---:|---|---|---|
| 1 | Methodology bundled skill files | `../../../skills/` | `~/dev/agent-runner/tools/methodology-runner/skills/` |
| 2 | Working docs in the application worktree | `docs/` | `<application worktree>/docs/` |

## STR-001-7 Current Prompt Path Mapping Rules

| Rule ID | Root Row | Target Regex | Replace With Template |
|---|---:|---|---|
| `MAP-001` | 1 | `^\\.\\./\\.\\./\\.\\./skills/(.+)$` | `~/dev/agent-runner/tools/methodology-runner/skills/$1` |
| `MAP-002` | 2 | `^docs/(.+)$` | `<application worktree>/docs/$1` |

## STR-001-8 Current Prompt Paths

| Raw Path | In-Run Path Template | Root Row | Current Role | Current Status | Recommended Post-Run Handling |
|---|---|---:|---|---|---|
| `../../../skills/structured-design/SKILL.md` | `~/dev/agent-runner/tools/methodology-runner/skills/structured-design/SKILL.md` | 1 | Bundled methodology reference resource | Active and consistent | Keep in tool repo |
| `../../../skills/structured-review/SKILL.md` | `~/dev/agent-runner/tools/methodology-runner/skills/structured-review/SKILL.md` | 1 | Bundled methodology reference resource | Active and consistent | Keep in tool repo |
| `docs/requirements/raw-requirements.md` | `<application worktree>/docs/requirements/raw-requirements.md` | 2 | Source input copied into the run worktree | Active and consistent | Keep a change-specific copy under `docs/changes/<change-id>/request/` if the request itself should remain part of repo history |
| `docs/requirements/requirements-inventory.yaml` | `<application worktree>/docs/requirements/requirements-inventory.yaml` | 2 | PH-000 working artifact | Active and consistent | Keep a change-specific copy under `docs/changes/<change-id>/analysis/` |
| `docs/requirements/requirements-inventory-coverage.yaml` | `<application worktree>/docs/requirements/requirements-inventory-coverage.yaml` | 2 | PH-000 coverage support artifact | Active and consistent | Keep a change-specific copy under `docs/changes/<change-id>/analysis/` if coverage evidence should be preserved |
| `docs/features/feature-specification.yaml` | `<application worktree>/docs/features/feature-specification.yaml` | 2 | PH-001 working artifact | Active and consistent | Keep a change-specific copy under `docs/changes/<change-id>/analysis/` and integrate the durable feature view into a subject-based markdown doc under `docs/features/` using the `structured-design` skill |
| `docs/architecture/architecture-design.yaml` | `<application worktree>/docs/architecture/architecture-design.yaml` | 2 | PH-002 prompt output and PH-003 prompt input in the current prompt corpus | Active in prompt modules but inconsistent with the phase registry and validators | Do not treat as the single authoritative Phase 2 path; reconcile the naming split before standardizing persistent promotion |
| `docs/architecture/stack-manifest.yaml` | `<application worktree>/docs/architecture/stack-manifest.yaml` | 2 | Phase 2 output in `phases.py`, cross-reference, and phase-2 validation | Active in registry, cross-reference, and validation but not yet aligned with PH-002 / PH-003 prompt modules | Do not treat as the single authoritative Phase 2 path until the prompt corpus is aligned |
| `docs/design/solution-design.yaml` | `<application worktree>/docs/design/solution-design.yaml` | 2 | PH-003 working artifact | Active and consistent apart from the upstream Phase 2 naming split | Keep a change-specific copy under `docs/changes/<change-id>/analysis/` and integrate the durable design view into a subject-based markdown doc under `docs/design/` using the `structured-design` skill |
| `docs/design/interface-contracts.yaml` | `<application worktree>/docs/design/interface-contracts.yaml` | 2 | PH-004 working artifact | Active and consistent | Keep a change-specific copy under `docs/changes/<change-id>/analysis/` and integrate the durable interface view into a subject-based markdown doc under `docs/contracts/` using the `structured-design` skill |
| `docs/simulations/simulation-definitions.yaml` | `<application worktree>/docs/simulations/simulation-definitions.yaml` | 2 | PH-005 working artifact | Active and consistent | Keep a change-specific copy under `docs/changes/<change-id>/analysis/`; promote only if the application keeps a durable human-readable testing or verification doc outside `docs/changes/` |
| `docs/implementation/implementation-workflow.md` | `<application worktree>/docs/implementation/implementation-workflow.md` | 2 | PH-006 working artifact used to drive the child prompt-runner | Active and consistent | Keep a change-specific copy under `docs/changes/<change-id>/execution/` |
| `docs/implementation/implementation-run-report.yaml` | `<application worktree>/docs/implementation/implementation-run-report.yaml` | 2 | PH-006 execution record | Active and consistent | Keep a change-specific copy under `docs/changes/<change-id>/execution/` |
| `docs/verification/verification-report.yaml` | `<application worktree>/docs/verification/verification-report.yaml` | 2 | PH-007 verification record | Active and consistent | Keep a change-specific copy under `docs/changes/<change-id>/verification/` |

## STR-001-9 Current Runner-Managed Roots

| Row | Root | In-Run Root Template | Current Contents | Current Lifecycle | Recommended Post-Run Handling |
|---:|---|---|---|---|---|
| 3 | Methodology control state root | `<application worktree>/.methodology-runner/` | `run.lock`, `state.json`, `process.log` | Live runner control state during and after the run | Archive or discard after the run; do not treat as canonical application state |
| 4 | Shared execution artifact root | `<application worktree>/.run-files/` | phase-scoped methodology artifacts, prompt-runner histories, module logs, generated summaries, execution evidence | Live runner execution artifacts during and after the run | Archive or discard after the run; do not treat as canonical application state |

## STR-001-10 Current Runner-Managed Paths

| Path | In-Run Path Template | Root Row | Current Role | Current Status | Recommended Post-Run Handling |
|---|---|---:|---|---|---|
| `.methodology-runner/run.lock` | `<application worktree>/.methodology-runner/run.lock` | 3 | Per-worktree concurrency lock | Active and authoritative | Remove when the run is not active; do not promote into permanent application docs |
| `.methodology-runner/state.json` | `<application worktree>/.methodology-runner/state.json` | 3 | Live methodology phase state used by status and resume | Active and authoritative | Archive only if historical run state is needed; otherwise discard |
| `.methodology-runner/process.log` | `<application worktree>/.methodology-runner/process.log` | 3 | Methodology-runner process log | Active and authoritative | Archive only if debugging evidence is needed; otherwise discard |
| `.run-files/methodology-runner/summary.txt` | `<application worktree>/.run-files/methodology-runner/summary.txt` | 4 | Human-readable methodology summary | Active and authoritative | Archive with run evidence if needed; otherwise discard |
| `.run-files/<phase-id>/cross-ref-result.json` | `<application worktree>/.run-files/<phase-id>/cross-ref-result.json` | 4 | Phase-scoped cross-reference result | Active and authoritative | Archive with run evidence if needed; otherwise discard |
| `.run-files/<phase-id>/retry-guidance-N.txt` | `<application worktree>/.run-files/<phase-id>/retry-guidance-N.txt` | 4 | Phase-scoped retry guidance written between cross-reference attempts | Active and authoritative | Archive with run evidence if needed; otherwise discard |
| `.run-files/<module>/...` | `<application worktree>/.run-files/<module>/...` | 4 | Prompt-runner histories, logs, and module execution evidence | Active and authoritative | Archive with run evidence if needed; otherwise discard |

The current CLI still contains cleanup logic that refers to
`.methodology-runner/runs/phase-N/`, but the live orchestrator writes
phase-scoped methodology artifacts under `.run-files/<phase-id>/`.

The current orchestrator records the resolved prompt module path in
`.methodology-runner/state.json` as `prompt_file`, but it does not currently
materialize a phase-local `.run-files/<phase-id>/prompt-file.md`.

This distinction matters because the earlier review language grouped
`prompt-file.md` together with the real phase-local outputs. The strategy now
follows the code instead:

- `.run-files/<phase-id>/cross-ref-result.json` and
  `.run-files/<phase-id>/retry-guidance-N.txt` are current orchestrator outputs
- `.run-files/<phase-id>/prompt-file.md` is not currently a dependable
  orchestrator output
- the resolved prompt module path currently lives in
  `.methodology-runner/state.json`

## STR-001-11 Parallel Worktree Safety

Stable working filenames are safe for parallel runs only because each run uses
its own `application worktree`.

The real current concurrency boundary is:

- one `.methodology-runner/run.lock` per application worktree
- one `.methodology-runner/state.json` per application worktree
- one `.methodology-runner/process.log` per application worktree
- one `.run-files/<phase-id>/...` tree per phase per application worktree
- one `.run-files/...` tree per application worktree

Implications:

- two runs in different application worktrees do not share these files
- two runs in the same application worktree compete for the same
  `.methodology-runner/run.lock`
- the current implementation therefore supports parallelism across separate
  worktrees, not concurrent runs inside one worktree

## STR-001-12 Steady-State Application Tree

These are canonical application files, not change dossiers and not runner state:

- `src/...`
- `tests/...`
- project config files
- assets
- migrations
- any other steady-state application subtree

Rule:

- keep these files at their canonical paths inside the application worktree
  during the run
- review and commit them through normal git workflow after the run
- do not give them unique per-change filenames

Examples:

| Working Path In Application Worktree | Persistent Path In Application Repo | Handling |
|---|---|---|
| `src/...` | `src/...` | Commit through git as the new product state |
| `tests/...` | `tests/...` | Commit through git as the new test state |
| `package.json`, `pyproject.toml`, config files | same canonical path | Commit through git as the new configuration state |
| `assets/...`, `migrations/...`, similar subtrees | same canonical path | Commit through git as the new steady-state project content |

## STR-001-13 Recommended Post-Run Promotion Policy

After a successful run, treat the working paths inside `docs/` as temporary
phase-artifact names, not automatically as the final persistent names.

Recommended split:

- `docs/changes/<change-id>/...`
  - keep change-specific reasoning, execution, and verification records here
- steady-state markdown docs outside `docs/changes/`
  - these files are current by default because they live in the canonical docs
    tree
  - write them in markdown using the `structured-design` skill
  - name them by stable subject, not by methodology phase
  - examples:
    - `docs/features/<capability-or-workflow>.md`
    - `docs/design/<component-or-boundary>.md`
    - `docs/contracts/<interface-or-protocol>.md`
- `src/...`, `tests/...`, configs, assets, migrations
  - keep these at their canonical steady-state paths and integrate them through
    git
- `.methodology-runner/...` and `.run-files/...`
  - treat these as runner-managed intermediate state and execution evidence,
    not as canonical application artifacts

This split avoids three different failure modes:

1. losing per-change reasoning because a later run overwrites it
2. treating temporary phase YAML filenames as if they were the durable
   application docs
3. polluting the permanent repo tree with runner control state and raw run logs

## STR-001-13A Steady-State Doc Naming And Decomposition Rules

Permanent docs outside `docs/changes/` should follow these rules:

- use markdown, not methodology phase YAML, for the human-facing steady-state
  doc layer
- write or update those markdown docs with the `structured-design` skill
- choose filenames by stable subject:
  - feature docs by user-visible capability or workflow
  - design docs by component, ownership boundary, or subsystem
  - contract docs by interface boundary, protocol, or payload family
- avoid generic phase names such as `feature-specification`,
  `solution-design`, and `interface-contracts` for permanent docs
- keep one file only while the subject changes together; split when two
  subjects can evolve independently
- prefer stable kebab-case slugs that can survive multiple changes without
  rename churn

For a small application, one doc per layer can be enough if the names are
still subject-based. Example steady-state paths:

- `docs/features/console-display.md`
- `docs/design/console-application.md`
- `docs/contracts/stdout-output.md`

## STR-001-13B Continuity Inputs For Later Runs

When steady-state markdown docs already exist outside `docs/changes/`, later
runs should use the relevant folder as continuity context during phase authoring.

Rules:

- the current raw request and current phase prerequisite artifacts remain
  authoritative when they conflict with older steady-state docs
- existing steady-state docs are continuity inputs, not override inputs
- continuity review should preserve stable naming, decomposition, and boundary
  choices when the new request does not require them to change
- continuity review should be layer-specific:
  - feature analysis should inspect existing docs under `docs/features/*.md`
  - solution design should inspect existing docs under `docs/design/*.md`
  - interface-contract design should inspect existing docs under
    `docs/contracts/*.md`
- exclude `docs/changes/...` from this continuity context because change records
  are historical evidence, not the current steady-state view
- exclude the current in-run phase artifact itself from the continuity scan when
  that artifact lives in the same folder as the steady-state docs

Prompt-contract implication:

- the relevant phase prompt should explicitly tell the model to inspect the
  corresponding steady-state doc folder when such docs exist in the workspace
- the phase should reuse stable current-state names and decomposition unless
  the new request or upstream artifacts justify a deliberate change

## STR-001-14 Git Integration Model

Recommended workflow:

1. Create one git branch or git worktree for one change.
2. Run methodology-runner in that application worktree.
3. Let the run update canonical steady-state code, test, and config paths in place:
   - `src/...`
   - `tests/...`
   - config files
4. Promote any change-specific kept records into:
   - `docs/changes/<change-id>/...`
5. Archive or discard:
   - `.methodology-runner/...`
   - `.run-files/...`
6. Remove the temporary phase-working files at their in-run names after their
   kept contents have been preserved under `docs/changes/<change-id>/...`.
7. Review the resulting application state and promoted change record set.
8. Integrate the change into the common steady-state markdown docs outside
   `docs/changes/` by writing or updating the subject-based docs with the
   `structured-design` skill:
   - `docs/features/<capability-or-workflow>.md`
   - `docs/design/<component-or-boundary>.md`
   - `docs/contracts/<interface-or-protocol>.md`
   During this step, inspect any existing steady-state docs in those folders
   and integrate the new change into them rather than rewriting the current
   view from scratch.
9. Review and commit the combined worktree changes.
10. Merge the worktree branch back into the application repo history.

## STR-001-15 Runtime Placeholders And Code References

| Reference | Current Meaning |
|---|---|
| `{{run_dir}}` | Path of the current application worktree |
| `{{project_dir}}` | In current methodology-runner execution, the same path as `{{run_dir}}` |
| `python-module:methodology_runner.phase_0_validation` ... `phase_7_validation` | Tool code references for deterministic validators |
| `{{prompt_runner_command}}` | Command used to invoke prompt-runner |

## STR-001-16 Main Point

- Current methodology-runner execution is centered on one application
  worktree, not on a built-in split between a persistent project directory and
  a second execution worktree.
- Current prompt modules directly reference:
  - `docs/...`
  - prompt-file-relative bundled skills under `../../../skills/...`
  - `{{run_dir}}`
- Current runner-managed live state is split across:
  - `.methodology-runner/...` for live control state
  - `.run-files/...` for execution artifacts and summaries
- Stable working filenames are safe during a run because each run should have
  its own application worktree.
- The naming problem starts only when files are kept permanently after the run.
- The durable split should be:
  - canonical steady-state application files at their normal paths
  - change-specific kept records under `docs/changes/<change-id>/...`
  - common steady-state markdown docs at subject-based paths outside
    `docs/changes/`
  - runner-managed state and logs kept out of the canonical repo tree
- The current Phase 2 artifact naming is not yet fully reconciled:
  - prompt modules still use `docs/architecture/architecture-design.yaml`
  - the phase registry, cross-reference logic, and validator use
    `docs/architecture/stack-manifest.yaml`
  - the strategy must surface that split until the codebase is aligned

## STR-001-17 Example: Two Consecutive Runs

This example shows the same application evolving through two separate
methodology runs:

1. a greenfield run that creates a minimal Hello World application
2. a second run that enhances that application to also display the current
   date and time

The point of the example is to show which files are:

- working in-run files
- runner-managed intermediate files
- committed steady-state application files
- committed change-specific records

### Fixed Assumptions

This worked example uses one explicit filesystem layout and does not vary it:

| Item | Concrete Value |
|---|---|
| Methodology tool repo | `/Users/martinbechard/dev/agent-runner` |
| Application repo main checkout | `/Users/martinbechard/dev/hello-clock` |
| Run 1 change ID | `change-001` |
| Run 1 branch name | `change-001-hello-world` |
| Run 1 application worktree directory | `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world` |
| Run 2 change ID | `change-002` |
| Run 2 branch name | `change-002-add-datetime` |
| Run 2 application worktree directory | `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime` |
| Run 1 source requirements file | `/Users/martinbechard/dev/agent-runner/sample/hello-world/requests/hello-world-python-app.md` |
| Run 2 source requirements file | `/Users/martinbechard/dev/hello-clock-change-requests/change-002-add-datetime.md` |
| Phase 2 file chosen for this example | `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/architecture/architecture-design.yaml` for Run 1 and `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/architecture/architecture-design.yaml` for Run 2 |
| Concrete phase ID used for runner-state examples | `PH-000-requirements-inventory` |
| Concrete prompt-runner module used for runner-state examples | `requirements-inventory` |
| Cross-reference retries in this example | none |
| Common steady-state doc authoring method | markdown files written or updated with the `structured-design` skill |
| Common steady-state markdown docs retained in this example | exactly `/Users/martinbechard/dev/hello-clock/docs/features/console-display.md`, `/Users/martinbechard/dev/hello-clock/docs/design/console-application.md`, and `/Users/martinbechard/dev/hello-clock/docs/contracts/stdout-output.md` after both runs |

This example intentionally fixes the Phase 2 path to
`architecture-design.yaml`. The repo-wide naming split with
`stack-manifest.yaml` is still real, but it is not varied inside this worked
example.

### Concrete Path Expansions Used In This Example

This table instantiates the abstract path forms from `STR-001-6`,
`STR-001-8`, and `STR-001-10` into one concrete example.

| Generic Form | Run 1 Concrete Path | Run 2 Concrete Path |
|---|---|---|
| `../../../skills/structured-design/SKILL.md` | `/Users/martinbechard/dev/agent-runner/tools/methodology-runner/skills/structured-design/SKILL.md` | `/Users/martinbechard/dev/agent-runner/tools/methodology-runner/skills/structured-design/SKILL.md` |
| `../../../skills/structured-review/SKILL.md` | `/Users/martinbechard/dev/agent-runner/tools/methodology-runner/skills/structured-review/SKILL.md` | `/Users/martinbechard/dev/agent-runner/tools/methodology-runner/skills/structured-review/SKILL.md` |
| `docs/requirements/raw-requirements.md` | `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/requirements/raw-requirements.md` | `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/requirements/raw-requirements.md` |
| `docs/features/feature-specification.yaml` | `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/features/feature-specification.yaml` | `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/features/feature-specification.yaml` |
| `docs/architecture/architecture-design.yaml` | `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/architecture/architecture-design.yaml` | `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/architecture/architecture-design.yaml` |
| `docs/features/<capability-or-workflow>.md` | `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/features/console-display.md` | `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/features/console-display.md` |
| `docs/design/<component-or-boundary>.md` | `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/design/console-application.md` | `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/design/console-application.md` |
| `docs/contracts/<interface-or-protocol>.md` | `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/contracts/stdout-output.md` | `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/contracts/stdout-output.md` |
| `.methodology-runner/state.json` | `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.methodology-runner/state.json` | `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.methodology-runner/state.json` |
| `.run-files/methodology-runner/summary.txt` | `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.run-files/methodology-runner/summary.txt` | `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.run-files/methodology-runner/summary.txt` |
| `.run-files/PH-000-requirements-inventory/cross-ref-result.json` | `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.run-files/PH-000-requirements-inventory/cross-ref-result.json` | `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.run-files/PH-000-requirements-inventory/cross-ref-result.json` |
| `.run-files/PH-000-requirements-inventory/retry-guidance-1.txt` | not created in Run 1 because this example fixes the retry count at zero | not created in Run 2 because this example fixes the retry count at zero |
| `.run-files/requirements-inventory/summary.txt` | `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.run-files/requirements-inventory/summary.txt` | `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.run-files/requirements-inventory/summary.txt` |

### Run 1: Greenfield Hello World

#### Starting Point

The application repo main checkout is:

- `/Users/martinbechard/dev/hello-clock`

Its history contains only an initial empty commit on `main`. Before the run,
the repo has no committed application files, no committed `docs/changes/`,
and no committed `/Users/martinbechard/dev/hello-clock/docs/features/console-display.md`,
`/Users/martinbechard/dev/hello-clock/docs/design/console-application.md`, or
`/Users/martinbechard/dev/hello-clock/docs/contracts/stdout-output.md`.

The operator creates the Run 1 worktree with:

```bash
git -C /Users/martinbechard/dev/hello-clock \
  worktree add /Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world \
  -b change-001-hello-world
```

The resulting Run 1 application worktree is:

- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world`

The source request file is:

- `/Users/martinbechard/dev/agent-runner/sample/hello-world/requests/hello-world-python-app.md`

#### File Operations During Run 1

The operator runs methodology-runner against the Run 1 worktree:

```bash
methodology-runner run \
  /Users/martinbechard/dev/agent-runner/sample/hello-world/requests/hello-world-python-app.md \
  --workspace /Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world
```

During the run, methodology-runner creates the working phase files at these
exact paths:

- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/requirements/raw-requirements.md`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/requirements/requirements-inventory.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/requirements/requirements-inventory-coverage.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/features/feature-specification.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/architecture/architecture-design.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/design/solution-design.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/design/interface-contracts.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/simulations/simulation-definitions.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/implementation/implementation-workflow.md`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/implementation/implementation-run-report.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/verification/verification-report.yaml`

The same run creates the steady-state application files in place at:

- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/app.py`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/README.md`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/tests/test_app.py`

The same run also creates runner-managed intermediate files at:

- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.methodology-runner/run.lock`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.methodology-runner/state.json`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.methodology-runner/process.log`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.run-files/methodology-runner/summary.txt`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.run-files/PH-000-requirements-inventory/cross-ref-result.json`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.run-files/requirements-inventory/summary.txt`

No retry-guidance file is created in Run 1 because this example fixes the
retry count at zero.

#### Git Operations During Run 1

The git operations for Run 1 are:

1. Start from a clean worktree at:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world`
2. Let methodology-runner create and modify files in place.
3. Review the resulting steady-state application files:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/app.py`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/README.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/tests/test_app.py`
4. Promote the kept change-specific records into concrete permanent paths:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/changes/change-001/request/raw-requirements.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/changes/change-001/analysis/requirements-inventory.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/changes/change-001/analysis/requirements-inventory-coverage.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/changes/change-001/analysis/feature-specification.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/changes/change-001/analysis/architecture-design.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/changes/change-001/analysis/solution-design.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/changes/change-001/analysis/interface-contracts.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/changes/change-001/analysis/simulation-definitions.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/changes/change-001/execution/implementation-workflow.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/changes/change-001/execution/implementation-run-report.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/changes/change-001/verification/verification-report.yaml`
5. Archive or discard the runner-managed state:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.methodology-runner/`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.run-files/`
6. Remove the temporary working phase files at their in-run names because
   their kept contents now exist under `docs/changes/`.
7. Review the resulting application state and promoted change record set.
8. Integrate the change into the common steady-state markdown docs with the
   `structured-design` skill at these exact paths:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/features/console-display.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/design/console-application.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/docs/contracts/stdout-output.md`
9. Commit the kept files on `change-001-hello-world`.
10. Merge `change-001-hello-world` back into `main`.

After the merge, the application repo at
`/Users/martinbechard/dev/hello-clock` contains these committed files:

- `/Users/martinbechard/dev/hello-clock/app.py`
- `/Users/martinbechard/dev/hello-clock/README.md`
- `/Users/martinbechard/dev/hello-clock/tests/test_app.py`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/request/raw-requirements.md`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/requirements-inventory.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/requirements-inventory-coverage.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/feature-specification.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/architecture-design.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/solution-design.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/interface-contracts.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/simulation-definitions.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/execution/implementation-workflow.md`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/execution/implementation-run-report.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/verification/verification-report.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/features/console-display.md`
- `/Users/martinbechard/dev/hello-clock/docs/design/console-application.md`
- `/Users/martinbechard/dev/hello-clock/docs/contracts/stdout-output.md`

### Run 2: Add Current Date And Time

#### Starting Point

Run 2 starts from the already committed state in the application repo main
checkout at:

- `/Users/martinbechard/dev/hello-clock`

Before Run 2 begins, this repo already contains:

- `/Users/martinbechard/dev/hello-clock/app.py`
- `/Users/martinbechard/dev/hello-clock/README.md`
- `/Users/martinbechard/dev/hello-clock/tests/test_app.py`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/request/raw-requirements.md`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/requirements-inventory.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/requirements-inventory-coverage.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/feature-specification.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/architecture-design.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/solution-design.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/interface-contracts.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/simulation-definitions.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/execution/implementation-workflow.md`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/execution/implementation-run-report.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/verification/verification-report.yaml`
- `/Users/martinbechard/dev/hello-clock/docs/features/console-display.md`
- `/Users/martinbechard/dev/hello-clock/docs/design/console-application.md`
- `/Users/martinbechard/dev/hello-clock/docs/contracts/stdout-output.md`

The operator creates the Run 2 worktree with:

```bash
git -C /Users/martinbechard/dev/hello-clock \
  worktree add /Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime \
  -b change-002-add-datetime
```

The resulting Run 2 application worktree is:

- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime`

The Run 2 source request file is:

- `/Users/martinbechard/dev/hello-clock-change-requests/change-002-add-datetime.md`

#### File Operations During Run 2

The operator runs methodology-runner against the Run 2 worktree:

```bash
methodology-runner run \
  /Users/martinbechard/dev/hello-clock-change-requests/change-002-add-datetime.md \
  --workspace /Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime
```

During the run, methodology-runner again creates the working phase files at
these exact paths:

- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/requirements/raw-requirements.md`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/requirements/requirements-inventory.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/requirements/requirements-inventory-coverage.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/features/feature-specification.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/architecture/architecture-design.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/design/solution-design.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/design/interface-contracts.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/simulations/simulation-definitions.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/implementation/implementation-workflow.md`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/implementation/implementation-run-report.yaml`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/verification/verification-report.yaml`

The same run modifies the canonical application files in place at:

- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/app.py`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/README.md`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/tests/test_app.py`

The same run again creates runner-managed intermediate files at:

- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.methodology-runner/run.lock`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.methodology-runner/state.json`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.methodology-runner/process.log`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.run-files/methodology-runner/summary.txt`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.run-files/PH-000-requirements-inventory/cross-ref-result.json`
- `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.run-files/requirements-inventory/summary.txt`

No retry-guidance file is created in Run 2 because this example fixes the
retry count at zero.

#### Git Operations During Run 2

The git operations for Run 2 are:

1. Start from the Run 1 committed state in the new worktree at:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime`
2. Let methodology-runner modify the steady-state application files in place:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/app.py`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/README.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/tests/test_app.py`
3. Let methodology-runner create fresh working phase files again under:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/`
4. Promote the kept records into concrete permanent paths:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/changes/change-002/request/raw-requirements.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/changes/change-002/analysis/requirements-inventory.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/changes/change-002/analysis/requirements-inventory-coverage.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/changes/change-002/analysis/feature-specification.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/changes/change-002/analysis/architecture-design.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/changes/change-002/analysis/solution-design.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/changes/change-002/analysis/interface-contracts.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/changes/change-002/analysis/simulation-definitions.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/changes/change-002/execution/implementation-workflow.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/changes/change-002/execution/implementation-run-report.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/changes/change-002/verification/verification-report.yaml`
5. Archive or discard:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.methodology-runner/`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.run-files/`
6. Remove only these temporary phase-working files:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/requirements/raw-requirements.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/requirements/requirements-inventory.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/requirements/requirements-inventory-coverage.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/features/feature-specification.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/architecture/architecture-design.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/design/solution-design.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/design/interface-contracts.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/simulations/simulation-definitions.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/implementation/implementation-workflow.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/implementation/implementation-run-report.yaml`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/verification/verification-report.yaml`
   Do not remove these steady-state markdown docs:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/features/console-display.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/design/console-application.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/contracts/stdout-output.md`
7. Review the resulting application state and promoted change record set.
8. Integrate the change into the common steady-state markdown docs with the
   `structured-design` skill at these exact paths:
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/features/console-display.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/design/console-application.md`
   - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/docs/contracts/stdout-output.md`
9. Commit the kept files on `change-002-add-datetime`.
10. Merge `change-002-add-datetime` back into `main`.

After the merge, the application repo at
`/Users/martinbechard/dev/hello-clock` contains:

- updated steady-state files:
  - `/Users/martinbechard/dev/hello-clock/app.py`
  - `/Users/martinbechard/dev/hello-clock/README.md`
  - `/Users/martinbechard/dev/hello-clock/tests/test_app.py`
- preserved Run 1 history:
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/request/raw-requirements.md`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/requirements-inventory.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/requirements-inventory-coverage.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/feature-specification.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/architecture-design.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/solution-design.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/interface-contracts.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/analysis/simulation-definitions.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/execution/implementation-workflow.md`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/execution/implementation-run-report.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/verification/verification-report.yaml`
- new Run 2 history:
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-002/request/raw-requirements.md`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-002/analysis/requirements-inventory.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-002/analysis/requirements-inventory-coverage.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-002/analysis/feature-specification.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-002/analysis/architecture-design.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-002/analysis/solution-design.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-002/analysis/interface-contracts.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-002/analysis/simulation-definitions.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-002/execution/implementation-workflow.md`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-002/execution/implementation-run-report.yaml`
  - `/Users/martinbechard/dev/hello-clock/docs/changes/change-002/verification/verification-report.yaml`
- updated common steady-state markdown docs at:
  - `/Users/martinbechard/dev/hello-clock/docs/features/console-display.md`
  - `/Users/martinbechard/dev/hello-clock/docs/design/console-application.md`
  - `/Users/martinbechard/dev/hello-clock/docs/contracts/stdout-output.md`

### Example Conclusion

After both runs, one reader following this example should end up with exactly
this interpretation:

- the methodology tool repo remains at:
  - `/Users/martinbechard/dev/agent-runner`
- the permanent application repo remains at:
  - `/Users/martinbechard/dev/hello-clock`
- Run 1 intermediate state existed only in:
  - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.methodology-runner/`
  - `/Users/martinbechard/dev/hello-clock-worktrees/change-001-hello-world/.run-files/`
- Run 2 intermediate state existed only in:
  - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.methodology-runner/`
  - `/Users/martinbechard/dev/hello-clock-worktrees/change-002-add-datetime/.run-files/`
- the permanent repo keeps:
  - steady-state files at canonical paths such as
    `/Users/martinbechard/dev/hello-clock/app.py`,
    `/Users/martinbechard/dev/hello-clock/README.md`, and
    `/Users/martinbechard/dev/hello-clock/tests/test_app.py`
  - change-specific history at concrete unique paths under
    `/Users/martinbechard/dev/hello-clock/docs/changes/change-001/` and
    `/Users/martinbechard/dev/hello-clock/docs/changes/change-002/`
  - common steady-state markdown docs at these exact paths:
    `/Users/martinbechard/dev/hello-clock/docs/features/console-display.md`,
    `/Users/martinbechard/dev/hello-clock/docs/design/console-application.md`, and
    `/Users/martinbechard/dev/hello-clock/docs/contracts/stdout-output.md`

That is the file-management strategy in concrete form:

- reuse stable working filenames only inside isolated application worktrees
- commit steady-state product files at their canonical paths
- commit change-specific reasoning at unique concrete paths under
  `docs/changes/`
- archive or discard `.methodology-runner/` and `.run-files/` after each run

## STR-001-18 Code Migration Plan

The strategy above is partly implemented and partly still operational policy.
The code migration should proceed in this order:

1. Prompt-owned reference roots
   - Replace repo-relative prompt includes such as `../../../skills/...` with
     prompt-facing root paths such as `skills/...`.
   - Add prompt-runner path-prefix mapping support so the runner can resolve
     those prompt-facing roots to concrete tool-owned directories at runtime.
   - Status:
     implemented for methodology-runner bundled skill includes.

2. Phase-path alignment
   - Remove phase-level naming splits where the prompt corpus, phase registry,
     cross-reference templates, and deterministic validators disagree about the
     same working artifact path.
   - Status:
     Phase 2 aligned to `docs/architecture/architecture-design.yaml`.

3. Continuity-aware phase authoring
   - Update the phase prompts that should build on steady-state markdown docs
     to inspect the relevant continuity folders and exclude `docs/changes/...`
     from that scan.
   - Status:
     implemented for PH-001, PH-003, and PH-004.

4. Runner-state consolidation
   - Keep documenting the current split between `.methodology-runner/...` and
     `.run-files/...` until the code is deliberately migrated.
   - When migrated, move methodology control state that should remain live into
     one stable location and update status/resume/reset logic accordingly.
   - Status:
     not yet migrated; current code still uses the split layout.

5. Post-run promotion support
   - Add explicit code support for promoting change-specific kept records from
     working phase paths into `docs/changes/<change-id>/...`.
   - Add explicit code support or documented tooling for updating the durable
     steady-state markdown docs outside `docs/changes/`.
   - Status:
     not yet automated in methodology-runner.

6. Cleanup and archive support
   - Add an explicit cleanup/archive step or command that removes only the
     temporary working phase files and archives or discards runner-managed
     intermediate state after the kept artifacts have been promoted.
   - Status:
     not yet automated in methodology-runner.

7. Installed-package support
   - Ensure bundled prompt resources remain resolvable when methodology-runner
     is used outside the source checkout, not just from an editable repo clone.
   - Status:
     source-tree and editable-install use is supported by the current
     path-mapping model; non-editable package-distribution support still needs
     a deliberate packaging pass.
