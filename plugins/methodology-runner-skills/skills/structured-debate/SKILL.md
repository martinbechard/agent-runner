---
name: structured-debate
description: Structure technical disagreements into explicit claims, objections, assumptions, concessions, and revised positions to improve reasoning quality
---

# Structured Debate

Use this skill when the task is not just to answer, but to reason through a
disagreement, challenge a proposal, address review comments, or refine a weak
argument into a stronger one.

This skill is for debate and reasoning hygiene, not persuasion theater. The
goal is to make the argument inspectable.

## When To Use It

Use this skill when one or more of these are true:

- A reviewer says the reasoning is weak, overblown, or unproven.
- Two positions disagree about architecture, tradeoffs, or feasibility.
- A rule, proposal, or conclusion needs a tighter causal chain.
- The discussion is mixing claims, objections, and design ideas together.
- You need to update your position in response to criticism without becoming
  defensive or vague.

Do not use this skill for routine factual Q&A or for writing final polished
docs that no longer contain live disagreement.

## Core Method

When responding in a debate or review exchange, explicitly separate:

1. The claim being made.
2. The objection being raised.
3. The specific part of the claim the objection defeats, weakens, or leaves
   untouched.
4. The revised claim after accounting for the objection.

If you cannot name all four, the reasoning is probably still muddled.

## Causal Formatting

This skill borrows the most useful part of `rule-writing`: explicit causal
chains.

In practice, most weak debate responses fail because they skip one of these:

- the exact claim
- the reason the claim is supposed to hold
- the reason the objection actually lands
- the narrower claim that survives

So do not just label sections. Make the causal chain explicit.

## Preferred Format

For substantial disagreements, use this shape:

```md
Claim:
<the original assertion>

- BECAUSE: <reason the speaker thinks the claim holds>
- BECAUSE: <second reason, if independent>

Objection:
<the review comment or opposing argument>

- BECAUSE: <why the objection challenges the claim>

Assessment:
<what the objection successfully proves, weakens, or leaves open>

- IMPACT: <which exact part of the claim fails, weakens, or survives>

Revised Claim:
<the strongest claim that still stands after the objection>

- BECAUSE: <why this narrower claim is still justified>
```

If the reasons are causally nested rather than parallel, show that nesting
explicitly instead of flattening them.

## Required Moves

- Quote or restate the exact claim under dispute before rebutting it.
- Identify whether the issue is:
  - factual error
  - unsupported assertion
  - missing causal link
  - ambiguity
  - contradiction
  - scope drift
  - implementation infeasibility
- State clearly whether you:
  - agree
  - partly agree
  - disagree
  - cannot yet decide
- If you revise your position, say what changed and why.
- If an objection is valid but does not fully defeat the original position,
  say exactly what survives.

## Causal Discipline

Do not claim that A proves B unless you can name the missing steps.

If the chain is weak, replace:

- "therefore this must be true"

with one of:

- "this suggests"
- "this supports"
- "this is consistent with"
- "this is necessary but not sufficient for"
- "this does not yet prove"

This is not hedging for style. It is precision about evidentiary strength.

## Concessions

A concession is useful only if it changes the structure of the argument.

Good concession:

- "Agreed that this does not prove deterministic code is superior; the real
  claim should be about having an explicit policy boundary."

Bad concession:

- "Good point, maybe you're right."

Concede specifically. Then restate the surviving position.

## Debate Failure Modes

Watch for these failures and correct them immediately:

- answering a stronger or weaker claim than the one actually challenged
- switching from "must" to "could" without admitting the change
- defending architecture by intuition alone
- repeating a conclusion after its support has been undermined
- replacing rebuttal with implementation brainstorming
- treating a useful suggestion as proof of the original claim

## Output Standard

A good debate response should let a third party answer:

- What was the original claim?
- Why was that claim supposed to hold?
- What was the criticism?
- Why did the criticism land?
- What position remains after revision?

If a third party cannot answer those four questions quickly, rewrite the
response.
