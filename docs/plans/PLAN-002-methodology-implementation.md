# Methodology Workflow Implementation Plan

## Purpose

Turn the active methodology workflow design set into working code with a
progressive test ladder, starting from a tiny hello-world request and
ending at the previously captured web app request.

## Active Design Inputs

This plan implements the current active design stack:

- `.methodology/docs/design/high-level/HLD-002-methodology-execution-architecture.md`
- `.methodology/docs/design/high-level/HLD-003-methodology-workflow.md`
- `.methodology/docs/design/components/CD-005-methodology-supervision.md`
- `.methodology/docs/design/components/CD-003-methodology-run.md`
- `.methodology/docs/design/high-level/HLD-001-methodology-prompt-optimization.md`
- `.methodology/docs/design/components/CD-004-methodology-standalone-step-harness.md`
- `.prompt-runner/docs/design/components/CD-006-prompt-runner-core.md`

Retired chronological execution log:

- `docs/plans/retired/2026-04-13-methodology-execution-log.md`

Hierarchical project plan:

- `docs/plans/PLAN-003-methodology-project.md`

## Outcome We Need

We need one workflow that can:

1. create a trusted methodology baseline run from a request
2. turn that baseline into planning artifacts
3. build and validate a standalone phase-replay harness
4. write a bounded step-lab plan
5. recover from workflow failures under supervision

## Workstreams

### 1. Prompt-Runner Core Gaps

Goal: implement the generic runner features the methodology workflow
still compensates for in prompt prose.

Status: mostly complete

Tasks:

1. `[done]` Add typed `required-files` support to prompt parsing and
   execution.
2. `[done]` Add a typed `checks-files` block for optional file
   existence checks that should be traced without spending LLM tokens.
3. `[done]` Implement native placeholder rendering in `prompt-runner`
   for built-in values such as `run_dir` and `project_dir`, with a way
   for launcher scripts to provide additional placeholder values.
4. `[in progress]` Validate durable process metadata against resume
   behavior.
   Current state: process metadata exists, but active workflow resume
   and reattach behavior still needs more end-to-end validation.

Current likely code touchpoints:

- `.prompt-runner/src/cli/prompt_runner/parser.py`
- `.prompt-runner/src/cli/prompt_runner/runner.py`
- `.prompt-runner/src/cli/prompt_runner/__main__.py`
- prompt-runner parser and runner tests

Readiness gate:

- a prompt file with `required-files` fails before any backend call when
  a required file is missing
- a prompt file with `checks-files` records optional file presence or
  absence for troubleshooting without failing the run or invoking an LLM
- the active methodology workflow can rely on that behavior instead of
  spending prompt pairs on deterministic file-existence checks

### 2. Workflow Launcher And Rendering

Goal: keep the workflow setup deterministic and campaign-local.

Status: partially complete

Tasks:

1. `[done]` Establish `scripts/run_methodology_optimization_supervisor.py` as
   the authoritative launcher.
2. `[done]` Replace launcher-side prompt rendering with native
   placeholder support in `prompt-runner`.
3. `[todo]` Add any missing campaign-level configuration plumbing needed
   by the baseline and workflow stages.
4. `[in progress]` Improve launcher output so humans can
   inspect quickly.
   Current state: the active launcher prepares a workflow root, copies
   the request, passes workflow-specific placeholder values into
   `prompt-runner`, and has been used for both the real tiny baseline
   run and the synthetic downstream planning smoke run.

Current likely code touchpoints:

- `scripts/run_methodology_optimization_supervisor.py`

Readiness gate:

- one launcher command creates a workflow root, copies the request,
  passes the required placeholder values, and launches supervision
  without manual path edits

### 3. Baseline Stage Contract

Goal: make the baseline stage expose a clear top-level completion
contract.

Status: in progress

Tasks:

1. `[in progress]` Tighten the baseline stage so it always leaves
   behind:
   - baseline workspace
   - baseline status
   - baseline note
   - summary
   - timeline
   Current state: the deterministic baseline script now owns fresh-run
   vs resume, timeline generation, and baseline-status writing logic,
   but the live tiny baseline run has not yet surfaced the workflow-level
   baseline artifacts.
2. `[in progress]` Ensure later workflow stages and the supervisor can
   judge baseline completion from workflow-level artifacts rather than
   ambiguous nested state.
   Current state: the first tiny request exposed a real
   methodology-content failure rather than an infrastructure failure,
   which was useful, but the second tiny request has only proven
   `PH-000`, not the top-level handoff.
3. `[done]` Use the baseline status JSON as the authoritative
   machine-readable workflow-level completion artifact.

Current likely code touchpoints:

- `.methodology/docs/prompts/PR-015-methodology-baseline-run.md`
- `.methodology/docs/prompts/PR-019-methodology-optimization-workflow.md`
- `scripts/run_methodology_baseline.py`

Readiness gate:

- the hello-world baseline stage completes and passes without the
  supervisor needing to infer success from partial nested progress

### 4. Planning Preparation Stage

Goal: make planning preparation read the right active sources and
produce grounded workflow-local notes.

Status: partially verified

Tasks:

1. `[in progress]` Validate the planning stage against:
   - `raw-request.md`
   - baseline summary
   - baseline timeline
   - active workflow design
   Current state: the planning module has passed on a synthetic
   downstream fixture, but it still needs proof against a fully trusted
   real tiny baseline run.
2. `[done]` Remove deterministic file-existence checks once
   runner-level preconditions exist.
3. `[done]` Define `current-focus.md` and `integration-readiness.md`
   short, evidence-based, and reusable by later stages.

Current likely code touchpoints:

- `.methodology/docs/prompts/PR-016-methodology-planning-preparation.md`

Readiness gate:

- the hello-world workflow produces both planning artifacts with facts
  grounded in the baseline outputs

### 5. Standalone Step Harness

Goal: make isolated phase replay concrete and inspectable.

Status: not started on the active tiny workflow path

Tasks:

1. `[todo]` Align the harness prompt module with the harness
   script.
2. `[todo]` Make the harness validation note reflect the actual replay
   outputs.
3. `[todo]` Decide whether the fixed input bundle remains “clone the
   baseline workspace” for now or becomes a more explicit materialized
   bundle.
4. `[todo]` Consider adding one machine-readable replay summary beyond
   `harness-metadata.json`.
   Current state: the harness prompt module and script exist, but this
   module has not yet been run on the active tiny workflow path.

Current likely code touchpoints:

- `.methodology/docs/prompts/PR-017-methodology-standalone-step-harness.md`
- `scripts/run_methodology_step_harness.py`

Readiness gate:

- one hello-world phase can be reset and replayed in a workflow-local
  harness directory and leave behind inspectable replay metadata

### 6. Step-Lab Planning

Goal: produce a bounded, testable experiment plan after the harness is
real.

Status: not started on the active tiny workflow path

Tasks:

1. `[todo]` Ground target-phase selection in baseline and harness
   evidence.
2. `[todo]` Keep the experiment matrix intentionally small.
3. `[todo]` Keep the result template blank and reusable.
   Current state: the prompt module exists and has been updated for
   runner-level `required-files`, but it has not yet been exercised
   after a real harness replay.

Current likely code touchpoints:

- `.methodology/docs/prompts/PR-018-methodology-step-lab-planning.md`

Readiness gate:

- the hello-world workflow produces a bounded experiment matrix and a
  reusable result template

### 7. Supervision And Recovery

Goal: make supervision use clear workflow-level artifacts and consistent
terminology.

Status: not started on the active tiny workflow path

Tasks:

1. `[done]` Keep the supervision prompt module aligned with the
   architecture: workflow terminology, workflow run dir, workflow
   prompt.
2. `[todo]` Ensure resume is preferred when earlier workflow stages
   passed and a later stage failed.
3. `[todo]` Decide whether supervision should continue reading multiple
   stage verdict files or whether the workflow should emit one explicit
   workflow-level completion artifact.
   Current state: the active supervision module and launcher were
   rewritten to match the execution architecture vocabulary, but
   end-to-end supervision still depends on the baseline stage proving
   its top-level contract first.

Current likely code touchpoints:

- `.methodology/docs/prompts/PR-020-methodology-optimization-supervisor.md`
- `scripts/run_methodology_optimization_supervisor.py`

Readiness gate:

- the supervisor can distinguish:
  - prompt/module defect
  - resumable workflow state
  - unrecoverable workflow failure

## Progressive Test Ladder

### Stage A. Tiny Request Fixtures

Purpose:

- validate the workflow machinery on a cheap request
- expose stage-contract bugs before the real web app request

Tasks:

1. `[done]` Create a tiny request for a hello-world Python app.
2. `[done]` Create a more atomic tiny request to reduce false failures
   in `PH-000`.

### Stage B. Direct Stage Tests

Purpose:

- isolate stage-specific failures before layering on the workflow module

Tasks:

1. `[in progress]` Run the baseline stage (`PR-015`) on the tiny
   request.
   Current state: the real atomic tiny baseline has completed
   `PH-000-requirements-inventory` and is now inside
   `PH-001-feature-specification`, but the workflow-level baseline
   artifacts are still the live gate.
2. `[done on synthetic fixture]` Run the planning stage (`PR-016`) using
   baseline outputs.
3. `[todo]` Run the harness stage (`PR-017`).
4. `[todo]` Run the step-lab planning stage (`PR-018`).

### Stage C. Workflow Module Test

Purpose:

- validate stage sequencing
- validate run-local artifact flow
- validate top-level workflow verdict behavior

Tasks:

1. `[todo]` Run the full methodology workflow module (`PR-019`) on the
   tiny request.

### Stage D. Supervision Test

Purpose:

- validate launcher rendering
- validate supervision vocabulary and resume logic
- validate workflow-level pass/revise/escalate behavior

Tasks:

1. `[todo]` Run the supervision module (`PR-020`) on the tiny request.

### Stage E. Real Request Readiness Review

Tasks:

1. `[todo]` Confirm the baseline stage has a clean top-level completion
   contract.
2. `[todo]` Confirm the planning stage is grounded in active workflow
   docs and real baseline evidence.
3. `[todo]` Confirm harness replay works at least once on the tiny
   request.
4. `[todo]` Confirm the workflow module passes or fails in an
   interpretable way.
5. `[todo]` Confirm supervision distinguishes resume from restart
   correctly.

### Stage F. Real Request

Purpose:

- establish the real trusted baseline
- prepare planning artifacts
- build the standalone harness
- prepare the first real step-lab plan

Tasks:

1. `[todo]` Run the full supervised methodology workflow on
   `docs/requests/web-prompt-runner-report.md`.

## Immediate Next Actions

1. Finish the real tiny baseline run and confirm that it writes
   `baseline-status.json` and `baseline-methodology-run.md`.
2. Run the standalone step harness on the tiny workflow path.
3. Run step-lab planning on the tiny workflow path.
4. Run the full `PR-019` workflow on the tiny request.
5. Run `PR-020` supervision on the tiny request.
6. Launch the real web app workflow only after the tiny supervised
   workflow is stable end to end.
