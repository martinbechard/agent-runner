# Methodology Optimization Loop

Purpose: provide a stable, on-disk operating plan for autonomous
methodology-runner optimization work, so progress can continue even if
chat context compresses.

## Objective

Optimize methodology-runner execution for Codex using disciplined
experiments, not ad hoc prompt churn.

Primary goals:

- preserve artifact quality
- reduce wall time
- reduce cost
- keep orchestration simple enough to maintain

Secondary goals:

- improve observability and reporting
- leave behind reusable experiment infrastructure

## Constraints

- The work should stay CLI-native first.
- Prompt-runner and methodology-runner are the primary execution surfaces.
- Experiments should prefer deterministic workspace setup and explicit
  manifests over conversational instructions.
- Quality regressions are not acceptable merely because a run is cheaper.

## Optimization Strategy

The loop has four stages.

### Stage 1: Strong Baseline

Run one strong baseline configuration end to end.

Purpose:

- establish a quality reference
- capture timing, tokens, and cost by step
- identify the genuinely expensive or slow steps

Expected artifact outputs:

- run workspace
- timeline report
- concise findings note

### Stage 2: Step Labs

Optimize one expensive step at a time in isolation.

Only vary a small number of dimensions for that step:

- model
- prompt wording
- step decomposition
- context size or prelude load

Everything else stays fixed.

Purpose:

- avoid combinatorial explosion
- preserve causal clarity
- find local winners quickly

### Stage 3: Integration Run

Promote the best local winners into a second full methodology run.

Purpose:

- test whether local wins survive integration
- measure real end-to-end cost and latency
- catch interaction effects between steps

### Stage 4: Targeted Interaction Tests

Only if the integration run diverges materially from the local lab
predictions, run targeted follow-up tests.

Examples:

- model handoff penalties
- context accumulation effects
- prompt count tradeoffs
- cache sensitivity

## Decision Rule

Choose configurations using this order:

1. reject quality regressions
2. among acceptable variants, prefer lower wall time
3. then prefer lower cost
4. then prefer lower orchestration complexity

This is intentionally conservative. Cheap-but-fragile variants should
not win.

## Immediate Focus

Use current report data to prioritize:

1. `PH-000` prompt 2 generator
2. `PH-000` prompt 2 judge
3. `PH-000` prompt 1 generator only if still needed

Do not spend optimization effort on local orchestration steps like:

- prelude build
- deterministic prompt-file generation

Those are not the current bottlenecks.

## Operating Artifacts

This optimization effort should keep these durable artifacts current:

- this runbook
- one prompt file for baseline/integration runs
- one prompt file for step-lab experiments
- one evolving findings note with concrete conclusions

## Near-Term Deliverables

1. Build a small experiment manifest format for step-level variants.
2. Add a CLI-native runner that executes a variant set against one fixed
   step and workspace.
3. Extend reporting and comparison output enough to rank variants by
   quality, time, and cost.
4. Run `PH-000` step labs.
5. Run an integration pass with the selected winners.

## Anti-Patterns

Avoid these failure modes:

- testing all model combinations across all steps at once
- changing prompts and models simultaneously without a fixed baseline
- treating cache artifacts as if they were stable truths
- overfitting to one cheap run
- chasing cosmetic report improvements instead of experimental clarity

## Working Principle

The right abstraction is not a full prompt-optimization framework yet.
The right abstraction is a disciplined experiment loop over CLI calls,
with enough persistence that the work can continue across context
compression and operator handoff.
