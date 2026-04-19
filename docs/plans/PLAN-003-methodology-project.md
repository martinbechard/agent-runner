# Methodology Project Plan

## Purpose

This plan describes the goals, subgoals, and tasks for getting the
methodology workflow ready for the real web-app request.

## Goal 1: Prove the workflow on a tiny request

- **GOAL:** Prove the methodology workflow on a tiny hello-world request.
  - **CHAIN-OF-THOUGHT:** The workflow still has open questions in the
    baseline handoff, planning handoff, harness, and supervision. A
    tiny request lets us exercise those workflow mechanics without
    paying the cost of the real request first.
  - **BECAUSE:** We need one small, cheap request that lets us debug the
    workflow before spending time and tokens on the real web-app
    request.

### Subgoal 1.1: Finish the baseline-stage contract

- **SUBGOAL:** Finish the baseline stage on the tiny request.
  - **CHAIN-OF-THOUGHT:** The planning stage reads baseline artifacts,
    the harness depends on planning outputs, and the end-to-end tiny
    workflow depends on both. If the baseline stage is not trustworthy,
    the rest of the tiny path is blocked.
  - **BECAUSE:** Every later stage depends on one trusted baseline run.
- **TASK:** Finish the atomic tiny baseline run.
  - **STATUS:** `in progress`
  - **CHAIN-OF-THOUGHT:** The planning stage needs trusted baseline
    artifacts, the harness stage needs planning outputs, and the
    supervised tiny workflow depends on both. Until the tiny baseline
    finishes cleanly, all downstream proof work is blocked.
  - **BECAUSE:** Until the tiny baseline finishes and writes its
    workflow-level artifacts, the later stages cannot be validated on
    the real tiny path.
- **TASK:** Confirm that the tiny baseline writes `baseline-status.json`.
  - **STATUS:** `in progress`
  - **CHAIN-OF-THOUGHT:** The workflow runner and supervision runner
    need one deterministic artifact they can read directly. A JSON
    status file is the simplest machine-readable contract for that.
  - **BECAUSE:** The workflow needs one machine-readable baseline
    completion artifact.
- **TASK:** Confirm that the tiny baseline writes `baseline-methodology-run.md`.
  - **STATUS:** `in progress`
  - **CHAIN-OF-THOUGHT:** Machine-readable state is enough for control
    flow, but humans still need a compact note that explains what the
    baseline run produced and why it passed or failed.
  - **BECAUSE:** The workflow needs one human-readable baseline note.
- **TASK:** Fix the baseline handoff if `methodology-runner` advances but
  the workflow-level artifacts do not appear.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** `methodology-runner` can make nested progress
    inside its own workspace, but the workflow and supervision layers
    only see workflow-level artifacts. If that handoff is missing,
    higher layers cannot judge the run correctly.
  - **BECAUSE:** Nested progress is not enough for the workflow or
    supervisor to judge success safely.

### Subgoal 1.2: Prove planning preparation

- **SUBGOAL:** Prove planning preparation against trusted tiny-baseline
  evidence.
  - **CHAIN-OF-THOUGHT:** The planning stage is supposed to summarize
    what the trusted baseline showed and decide what to do next. That
    only has value if the source evidence is the real tiny baseline, not
    an artificial stand-in.
  - **BECAUSE:** The planning stage should be grounded in real baseline
    outputs, not only in a synthetic fixture.
- **TASK:** Use the synthetic `PR-016` planning-preparation pass as a
  reference proof.
  - **STATUS:** `done`
  - **CHAIN-OF-THOUGHT:** The synthetic fixture does not prove the whole
    workflow, but it does prove that the planning module can read the
    expected files and produce the expected planning outputs.
  - **BECAUSE:** It already showed that the planning module works on
    prepared downstream inputs.
- **TASK:** Re-run `PR-016` against the real tiny baseline after the
  baseline handoff is proven.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** The synthetic pass removed prompt-level doubt,
    but it did not prove that the planning stage consumes the real
    workflow artifacts correctly. A real tiny-baseline run closes that
    remaining gap.
  - **BECAUSE:** This is the first real validation of planning in the
    actual workflow.

### Subgoal 1.3: Prove the standalone step harness

- **SUBGOAL:** Prove isolated phase replay on the tiny path.
  - **CHAIN-OF-THOUGHT:** Step optimization means changing one step
    while holding the rest of the workflow fixed. That only works if we
    can replay one phase in isolation against known inputs.
  - **BECAUSE:** Step optimization only makes sense if one methodology
    phase can be replayed in isolation.
- **TASK:** Run `PR-017` on the active tiny workflow path.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** The harness script and prompt module exist,
    but they have not yet been proven in the real tiny campaign
    structure. We need one actual tiny-path run before relying on the
    harness for step optimization.
  - **BECAUSE:** The harness has not yet been exercised in the active
    tiny workflow.
- **TASK:** Confirm that the harness leaves behind replay metadata and
  usable validation notes.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** A replay is only useful if we can later see
    what was replayed, what inputs were used, and whether the replay was
    good enough to trust.
  - **BECAUSE:** The replay must be inspectable after it runs.

### Subgoal 1.4: Prove step-lab planning

- **SUBGOAL:** Prove bounded step-lab planning on the tiny path.
  - **CHAIN-OF-THOUGHT:** Once the harness works, the next risk is
    trying too many models, prompts, and decompositions at once. The
    step-lab planner should keep the next experiments small and
    testable.
  - **BECAUSE:** We need a small experiment plan before comparing models
    or prompt variants.
- **TASK:** Run `PR-018` after the harness pass.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** The step-lab planner needs the target-step and
    replay evidence produced by the harness. Without those inputs, it
    would be guessing.
  - **BECAUSE:** The step-lab planner depends on harness outputs.
- **TASK:** Confirm that the experiment matrix is small and the result
  template is reusable.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** The point of the step lab is controlled
    comparison, not a large search space. A bounded matrix and reusable
    template keep the work comparable and affordable.
  - **BECAUSE:** The workflow should avoid combinatorial explosion.

## Goal 2: Prove the tiny workflow end to end

- **GOAL:** Prove that the workflow stages and supervision behave
  correctly together.
  - **CHAIN-OF-THOUGHT:** Individual stages can work in isolation while
    still failing when their artifacts are handed to the next stage or
    when supervision tries to interpret their state. We need one full
    tiny path to validate those joins.
  - **BECAUSE:** Individual stages passing is not enough if artifact
    handoff or supervision still breaks.

### Subgoal 2.1: Prove workflow sequencing

- **SUBGOAL:** Prove that the workflow stages run in order and pass
  artifacts forward correctly.
  - **CHAIN-OF-THOUGHT:** The workflow runner exists to connect the
    baseline, planning, harness, and step-lab stages into one process.
    If those stages do not hand artifacts forward correctly, the module
    is not yet doing its job.
  - **BECAUSE:** The workflow should behave as one coherent process, not
    as unrelated prompt passes.
- **TASK:** Run `PR-019` on the tiny request.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** `PR-019` is the prompt module that sequences
    the four workflow stages, so this run is the direct test of workflow
    ordering and stage handoff.
  - **BECAUSE:** This is the main workflow module that sequences the
    baseline, planning, harness, and step-lab stages.
- **TASK:** Confirm that baseline, planning, harness, and step-lab
  stages pass artifacts forward correctly.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** Each stage consumes artifacts from the stage
    before it. If those artifacts are missing, stale, or written in the
    wrong place, the sequence breaks even if each stage works alone.
  - **BECAUSE:** Each later stage depends on outputs created by the
    earlier stages.

### Subgoal 2.2: Prove supervision and recovery

- **SUBGOAL:** Prove that supervision can recover from normal workflow
  failures.
  - **CHAIN-OF-THOUGHT:** The supervision runner is only useful if it
    can tell the difference between resume, retry, and hard failure. If
    it cannot, it will either throw away progress or keep looping.
  - **BECAUSE:** A supervised workflow only helps if it can distinguish
    resume, retry, and hard failure.
- **TASK:** Run `PR-020` on the tiny request.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** `PR-020` is the supervision module that wraps
    the optimization workflow, so this run is the direct test of
    supervision behavior on the tiny path.
  - **BECAUSE:** This is the supervision module that starts, resumes,
    and judges the optimization workflow.
- **TASK:** Confirm that supervision distinguishes resume, restart, and
  unrecoverable failure.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** Resume should preserve good progress, restart
    should only happen when earlier outputs are invalid, and hard
    failure should stop instead of looping. If those cases are mixed
    together, supervision becomes destructive or confusing.
  - **BECAUSE:** The supervision loop should not throw away good
    progress or loop blindly.

## Goal 3: Harden the generic workflow infrastructure

- **GOAL:** Align the generic `prompt_runner` and launcher behavior with
  what the methodology workflow needs.
  - **CHAIN-OF-THOUGHT:** The methodology workflow should spend model
    tokens on reasoning, not on deterministic preconditions or string
    substitution. That means the generic runner and launcher have to own
    those deterministic responsibilities.
  - **BECAUSE:** The methodology workflow should rely on reusable runner
    features rather than prompt-level workarounds.

### Subgoal 3.1: Finish generic `prompt_runner` support

- **SUBGOAL:** Finish the reusable runner features the methodology
  workflow depends on.
  - **CHAIN-OF-THOUGHT:** File checks, placeholder rendering, and resume
    behavior are generic workflow concerns. Putting them in
    `prompt_runner` reduces prompt complexity and avoids wasting tokens.
  - **BECAUSE:** Deterministic runner behavior reduces wasted tokens and
    simplifies prompt modules.
- **TASK:** Add `required-files` support.
  - **STATUS:** `done`
  - **CHAIN-OF-THOUGHT:** Required file existence is a deterministic
    precondition, so the runner can reject missing files before any
    backend call is made.
  - **BECAUSE:** Required file checks now fail before any backend call.
- **TASK:** Add typed `checks-files` support for optional
  file-existence tracing without LLM use.
  - **STATUS:** `done`
  - **CHAIN-OF-THOUGHT:** Optional files do not need to block execution,
    but they do need to be visible for troubleshooting. The runner can
    record that state directly.
  - **BECAUSE:** Optional file checks now produce trace data without
    spending tokens.
- **TASK:** Implement native placeholder rendering in `prompt_runner`
  for built-in values plus launcher-supplied extra values.
  - **STATUS:** `done`
  - **CHAIN-OF-THOUGHT:** Placeholder substitution is deterministic and
    tied to runner state such as `run_dir` and `project_dir`. The runner
    is the right component to resolve that state consistently.
  - **BECAUSE:** Parameter substitution now lives in `prompt_runner`
    instead of in launcher-side prompt rewriting.
- **TASK:** Validate resume and reattach behavior against real workflow
  runs.
  - **STATUS:** `in progress`
  - **CHAIN-OF-THOUGHT:** PID metadata and saved run state are necessary
    building blocks, but they only matter if actual workflow runs can be
    resumed and inspected correctly.
  - **BECAUSE:** Process metadata exists, but real recovery behavior
    still needs more proof.

### Subgoal 3.2: Keep launcher behavior deterministic and campaign-local

- **SUBGOAL:** Keep the optimization campaign launcher simple and
  inspectable.
  - **CHAIN-OF-THOUGHT:** The launcher creates the workflow root, copies
    the request, and passes placeholder values. If that setup is opaque
    or scattered, the whole campaign becomes harder to inspect and
    reproduce.
  - **BECAUSE:** The launcher should set up a campaign cleanly without
    hiding important workflow state.
- **TASK:** Use the optimization supervisor launcher as the
  authoritative entrypoint.
  - **STATUS:** `done`
  - **CHAIN-OF-THOUGHT:** One stable entrypoint reduces ambiguity about
    which command should be used to start a campaign.
  - **BECAUSE:** One stable launcher command reduces operator confusion.
- **TASK:** Improve launcher output for quick human inspection.
  - **STATUS:** `in progress`
  - **CHAIN-OF-THOUGHT:** Operators need to see the workflow root, the
    request copy, and the prompt-run directories immediately so they can
    understand what the launcher just created.
  - **BECAUSE:** Operators should be able to see the workflow root,
    request copy, and prompt-run locations immediately.
- **TASK:** Centralize any remaining campaign-level configuration that
  still lives in scripts.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** If campaign assumptions are spread across
    multiple scripts, small changes become easy to miss and hard to
    audit.
  - **BECAUSE:** Campaign setup should not be spread across multiple ad
    hoc script assumptions.

## Goal 4: Run the real web-app workflow

- **GOAL:** Run the full supervised methodology workflow on the real
  web-app request.
  - **CHAIN-OF-THOUGHT:** The tiny workflow is only a proving ground.
    The real objective is to create a trusted baseline for the
    previously captured web-app request and then use that baseline for
    step-level optimization.
  - **BECAUSE:** The real web-app request is the actual target for
    baseline creation and later step-level optimization.

### Subgoal 4.1: Declare readiness for the real request

- **SUBGOAL:** Declare readiness only after the tiny workflow is stable
  enough to trust.
  - **CHAIN-OF-THOUGHT:** If the tiny workflow is still unclear or
    unstable, the real request will mix infrastructure debugging with
    expensive real work. The tiny path should absorb that risk first.
  - **BECAUSE:** The real request should not be the first place where
    workflow structure and supervision are tested.
- **TASK:** Confirm that the tiny baseline handoff is reliable.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** The baseline handoff is the first dependency
    for every downstream stage, so it is the first readiness gate for
    the real request too.
  - **BECAUSE:** The baseline handoff is the current critical
    dependency.
- **TASK:** Confirm that planning is grounded in real tiny-baseline
  evidence.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** Planning should summarize what the real tiny
    baseline produced, not what a synthetic fixture approximated.
  - **BECAUSE:** The planning stage should not depend on synthetic
    stand-ins once the real tiny baseline exists.
- **TASK:** Confirm that the harness works once on the tiny path.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** Step-level optimization on the real request
    assumes that isolated replay already works. The tiny path should
    prove that first.
  - **BECAUSE:** Real isolated replay proof should exist before step
    optimization starts.
- **TASK:** Confirm that the full tiny workflow is interpretable.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** We need to understand what happened at each
    stage, why it passed or failed, and where artifacts were written.
    Otherwise the real workflow will be too hard to trust.
  - **BECAUSE:** We should understand the tiny workflow behavior before
    running the real request.
- **TASK:** Confirm that supervision behaves correctly on the tiny
  workflow.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** Supervision errors can waste time by restarting
    good work or hiding the real failure mode, so they should be proven
    on the tiny path first.
  - **BECAUSE:** The supervision loop should be proven before the real
    request depends on it.

### Subgoal 4.2: Execute the real request

- **SUBGOAL:** Run the real web-app workflow and prepare for real step
  optimization.
  - **CHAIN-OF-THOUGHT:** Once the tiny workflow is trustworthy, the
    next job is to create one trusted real baseline and then use that
    fixed baseline as the input to real step-level experiments.
  - **BECAUSE:** The trusted real baseline is the input for real
    step-level model and prompt experiments.
- **TASK:** Run the full supervised workflow on
  `.archive/docs/requests/web-prompt-runner-report.md`.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** The supervised workflow is the mechanism that
    creates the real baseline and its associated planning and harness
    artifacts.
  - **BECAUSE:** This creates the trusted real baseline run.
- **TASK:** Use the resulting real baseline to start the first real
  step-lab experiments.
  - **STATUS:** `todo`
  - **CHAIN-OF-THOUGHT:** Real step-lab experiments are only meaningful
    if they all start from one fixed trusted baseline, so that model and
    prompt differences can be compared fairly.
  - **BECAUSE:** The real step-lab work depends on fixed inputs from the
    trusted real baseline.

## Critical Path

- **PATH:** baseline handoff -> real tiny planning run -> tiny harness
  -> tiny step-lab -> tiny supervised workflow -> real web-app workflow
  - **CHAIN-OF-THOUGHT:** The baseline handoff produces the first trusted
    artifacts, planning consumes those artifacts, the harness consumes
    planning outputs, the step lab depends on the harness, the tiny
    supervised workflow proves the full chain, and only then is the real
    workflow ready to run.
  - **BECAUSE:** Each item depends on artifacts produced by the item
    before it.
