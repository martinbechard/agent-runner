# Web-Based Prompt-Runner Report Utility

We want a web-based version of the prompt-runner report utility.

Right now the report flow is CLI-oriented. We want something that is easier
to open in a browser, navigate, and share with people who do not want to read
raw terminal logs or filesystem artifacts directly.

## Rough Goal

Create a browser-facing report experience for prompt-runner runs.

The result should make it easy to inspect what happened in a run, including
high-level outcome, per-prompt progress, iterations, verdicts, and useful
artifacts or logs.

## What We Probably Want

- A generated report that can be viewed in a web browser.
- A clearer summary than the current terminal/log-oriented output.
- Navigation across prompts, iterations, generator output, judge output, and
  final outcomes.
- Visibility into failures, retries, escalations, and halt reasons.
- A layout that works for both small runs and larger multi-prompt runs.
- Something that feels practical for local development first.

## Constraints And Preferences

- Prefer something simple to run locally.
- Avoid unnecessary infrastructure.
- The report should help debugging, not just present a polished summary.
- It should be possible to understand a failed run quickly.
- The design should preserve traceability back to the underlying run files.
- Do not assume the report only needs to be a static page if a more interactive
  approach would clearly be better.

## Non-Goals For The First Pass

- We do not need a hosted multi-user system yet.
- We do not need authentication, accounts, or collaboration features.
- We do not need to solve every visualization idea in v1.

## Success Shape

At the end, we want a credible first version of a browser-based report utility
for prompt-runner that is useful enough to replace opening a pile of run files
by hand.
