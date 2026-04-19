# Plan: Tiny Baseline Run

## Purpose

This plan defines the smallest real baseline run we need before the rest
of the methodology workflow can continue.

## Scope

- **GOAL:** Produce one trusted baseline workspace for the hello-world
  Python request.
  - **CHAIN-OF-THOUGHT:** The planning stage reads baseline artifacts,
    the harness depends on planning outputs, and the later workflow
    stages depend on both. If the smallest real baseline is not
    trustworthy, every later stage is blocked or misgrounded.
  - **BECAUSE:** Planning preparation, standalone replay, and step-lab
    planning all depend on one accepted baseline.

- **NON-GOAL:** Prove the full supervised methodology workflow.
  - **CHAIN-OF-THOUGHT:** The current blocker is the baseline-stage
    handoff. Adding later workflow concerns here would blur the first
    failure boundary and make the next repair less clear.
  - **BECAUSE:** This plan is only for the baseline stage and its direct
    handoff artifacts.

## Fixed Inputs

- **INPUT:** `sample/hello-world/requests/hello-world-python-app.md`
  - **CHAIN-OF-THOUGHT:** The point of this run is to test workflow
    mechanics cheaply. A tiny request gives real methodology behavior
    without the cost and ambiguity of the web-app request.
  - **BECAUSE:** The tiny baseline run must stay tied to one stable
    request.

- **INPUT:** `scripts/run_methodology_baseline.py`
  - **CHAIN-OF-THOUGHT:** The baseline stage needs one deterministic
    entrypoint that owns fresh-run vs resume and writes workflow-level
    artifacts. That responsibility already belongs to this script.
  - **BECAUSE:** This script owns fresh-run vs resume and the
    workflow-level baseline artifacts.

- **INPUT:** `.methodology/docs/design/components/CD-003-methodology-run.md`
  - **CHAIN-OF-THOUGHT:** The tiny baseline run is not a one-off local
    experiment. It is supposed to prove the generic methodology-run
    structure and artifacts under a real request.
  - **BECAUSE:** The tiny baseline run should satisfy the active
    methodology-run design, not an ad hoc local convention.

- **INPUT:** `.methodology/docs/design/high-level/HLD-001-methodology-prompt-optimization.md`
  - **CHAIN-OF-THOUGHT:** The tiny baseline run is the first designated
    `baseline` run in a later set of baseline-plus-variant runs, so its
    directory and artifacts should fit that larger organization.
  - **BECAUSE:** The tiny baseline run should also satisfy the active
    run-set design, not just the generic single-run design.

## Decision Path

- **DECISION:** Use the hello-world request instead of the web-app
  request first.
  - **BECAUSE:** The smaller request reduces cost and latency while we
    prove the baseline-stage contract.

- **DECISION:** Treat this as a baseline-stage plan, not a full workflow
  plan.
  - **BECAUSE:** The current blocker is the baseline handoff, and later
    stages should not hide that problem.

- **DECISION:** Use `scripts/run_methodology_baseline.py` as the entry
  point.
  - **BECAUSE:** That script owns fresh-run vs resume and the
    workflow-level baseline artifacts.

- **DECISION:** Judge success from workflow-level artifacts, not from
  partial nested methodology progress.
  - **BECAUSE:** The optimization workflow and supervision process need
    one explicit top-level completion contract.

- **DECISION:** Prefer resume over restart when the tiny baseline
  workspace is still usable.
  - **BECAUSE:** Resume preserves evidence about the real blocking point
    and avoids wasting prior work.

## Success Criteria

- **SUCCESS:** `baseline-status.json` exists and says the baseline is
  trusted.
  - **CHAIN-OF-THOUGHT:** The workflow runner and supervision runner
    need one deterministic artifact they can read directly. A status
    file is the simplest machine-readable statement of baseline trust.
  - **BECAUSE:** Later workflow stages need one machine-readable trust
    decision.

- **SUCCESS:** `baseline-methodology-run.md` exists and summarizes the
  baseline result.
  - **CHAIN-OF-THOUGHT:** Machine-readable state is enough for control
    flow, but humans still need one compact note that explains what the
    baseline run produced and why it is trusted or blocked.
  - **BECAUSE:** The workflow and supervision layers need one human-
    readable top-level baseline note.

- **SUCCESS:** the baseline workspace contains:
  - `.methodology-runner/summary.txt`
  - `timeline.html`
  - **CHAIN-OF-THOUGHT:** Planning and step selection depend on both a
    compact summary and detailed timing evidence. If either file is
    missing, the baseline is not yet ready for downstream use.
  - **BECAUSE:** Planning and later step selection depend on both a
    compact summary and a detailed timeline.

## Work Breakdown

### 1. Prepare the tiny baseline run directory

- **TASK:** Create one isolated workflow run directory for the tiny
  request.
  - **CHAIN-OF-THOUGHT:** The baseline artifacts, baseline workspace,
    and later planning outputs all need one stable location that belongs
    to this tiny run alone.
  - **BECAUSE:** The baseline artifacts and workspace need one stable
    home.

- **TASK:** Copy the hello-world request into `raw-request.md` under
  that run directory.
  - **CHAIN-OF-THOUGHT:** Later stages should read the same request that
    the baseline run used. A copied request file prevents drift between
    source inputs and workflow-local artifacts.
  - **BECAUSE:** The baseline run must read the copied campaign request,
    not a drifting source file.

- **TASK:** Decide whether the run starts fresh or resumes an existing
  tiny baseline directory.
  - **CHAIN-OF-THOUGHT:** Resume preserves useful progress and exposes
    the real blocking point, but a corrupted workspace can mislead later
    decisions. The run needs an explicit fork between reuse and reset.
  - **BECAUSE:** Resume should preserve useful work, while a corrupted
    or misleading run should be replaced.

### 2. Run the baseline stage

- **TASK:** Invoke `scripts/run_methodology_baseline.py --run-dir <...>`
  on the tiny run directory.
  - **CHAIN-OF-THOUGHT:** The optimization workflow should not infer
    trust from nested methodology state directly. The baseline script is
    the component that translates nested execution into workflow-level
    artifacts.
  - **BECAUSE:** The deterministic baseline script is the component that
    translates nested methodology progress into workflow-level artifacts.

- **TASK:** Let the baseline script create or resume
  `methodology-baseline-workspace/`.
  - **CHAIN-OF-THOUGHT:** The methodology workspace is the real baseline
    substrate. If its location changes from run to run, later stages
    cannot consume it predictably.
  - **BECAUSE:** The trusted baseline must live in one predictable
    workspace directory.

- **TASK:** Let the baseline script write:
  - `baseline-status.json`
  - `baseline-methodology-run.md`
  - **CHAIN-OF-THOUGHT:** The workflow and supervision layers judge
    workflow-level artifacts, not raw nested process progress. These two
    files are the handoff point between those layers.
  - **BECAUSE:** The optimization workflow does not judge raw nested
    methodology state directly.

### 3. Validate the baseline outputs

- **TASK:** Check whether `baseline-status.json` says the baseline is
  trusted.
  - **CHAIN-OF-THOUGHT:** The first question is not whether nested
    methodology work happened, but whether the baseline stage reached a
    workflow-level trusted state.
  - **BECAUSE:** This is the direct workflow-level answer to whether the
    stage passed.

- **TASK:** Check whether `baseline-methodology-run.md` exists and
  matches the current baseline state.
  - **CHAIN-OF-THOUGHT:** The status file drives control flow, but the
    note must agree with it so a human can inspect the same state
    without reverse-engineering JSON fields.
  - **BECAUSE:** The human-readable baseline note should agree with the
    machine-readable status.

- **TASK:** Check whether the baseline workspace contains:
  - `.methodology-runner/summary.txt`
  - `timeline.html`
  - **CHAIN-OF-THOUGHT:** The workflow should only hand off a baseline
    when the summary and timeline are both present, because those are
    the downstream evidence sources for planning and step selection.
  - **BECAUSE:** The next stage should not start without the baseline
    evidence bundle.

### 4. Repair or resume if the baseline is not yet trusted

- **TASK:** Read `blocking_phase` from `baseline-status.json` when the
  baseline is incomplete.
  - **CHAIN-OF-THOUGHT:** If the baseline is not yet trusted, the next
    decision should be based on one explicit blocking point rather than
    a guess from scattered files.
  - **BECAUSE:** Repair decisions should be based on one explicit
    blocking point.

- **TASK:** Resume the same tiny baseline workspace when the existing
  workspace is still usable.
  - **CHAIN-OF-THOUGHT:** Good partial progress is evidence. If the same
    workspace can continue safely, resuming preserves that evidence and
    reaches the actual blocker faster.
  - **BECAUSE:** Restarting hides the real blocking point and wastes
    prior progress.

- **TASK:** Restart only if the tiny baseline workspace is corrupted or
  misleading.
  - **CHAIN-OF-THOUGHT:** Resume is only valuable when the saved state
    is trustworthy. Carrying a bad workspace forward creates false
    signals and makes later diagnosis worse.
  - **BECAUSE:** A bad workspace should not be carried forward just to
    preserve motion.

### 5. Hand off to planning preparation

- **TASK:** Record the trusted tiny run directory as the input to the
  planning-preparation stage.
  - **CHAIN-OF-THOUGHT:** Once the baseline is trusted, the next stage
    should consume that exact run directory instead of any synthetic or
    stale fixture.
  - **BECAUSE:** `PR-016` should consume the real tiny baseline outputs,
    not a synthetic fixture.

- **TASK:** Use the trusted tiny baseline artifacts as the only approved
  planning inputs for the next stage.
  - **CHAIN-OF-THOUGHT:** Planning is only meaningful if it summarizes
    what the accepted baseline actually showed. Mixing in other sources
    would weaken that handoff.
  - **BECAUSE:** The planning stage is only meaningful if it is grounded
    in the accepted baseline run.

## Immediate Next Action

- **TASK:** Run one new tiny baseline attempt and stop only after the
  workflow-level baseline artifacts either exist or clearly fail again.
  - **CHAIN-OF-THOUGHT:** The baseline handoff is the first dependency
    for the rest of the workflow. The next useful action is therefore a
    run that ends with either a trusted handoff or a clearer failure.
  - **BECAUSE:** The baseline handoff is the current critical path for
    the whole methodology workflow.
