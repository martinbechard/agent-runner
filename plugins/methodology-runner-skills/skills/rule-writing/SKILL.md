---
name: rule-writing
description: Format review guidance and rules using explicit RULE:/BECAUSE: structure so feedback is checkable and causally justified
---

# Rule-writing

Use this skill when your job is not just to say that something is wrong, but to
state what rule was violated or what rule the next revision should follow.

This is especially useful for judge feedback in methodology-runner because the
generator needs correction guidance that is:

- explicit
- actionable
- grounded
- easy to trace back to the critique

## Core Format

When you need to express corrective guidance, prefer this shape:

```md
- RULE: <what the generator MUST / MUST NOT / SHOULD / SHOULD NOT do>
  - BECAUSE: <why this is required>
    - BECAUSE: <deeper causal reason when needed>
```

Use exactly one RFC-2119 keyword in each rule:

- MUST
- MUST NOT
- SHOULD
- SHOULD NOT
- MAY

## When Reviewing Generator Output

If the generator artifact is weak, do not stop at "missing coverage" or "bad
atomicity". Convert that into a usable rule for the next pass.

Good:

```md
- RULE: Every requirement-bearing bullet in `raw-requirements.md` MUST map to at
  least one RI-* item in `coverage_check`.
  - BECAUSE: The phase artifact is supposed to provide end-to-end traceability
    from source text to inventory entries.
```

Bad:

```md
Coverage is weak.
```

## Scope Discipline

Use rules for normative correction, not for general commentary.

- If you are identifying a disagreement or assessing whether a criticism lands,
  combine this skill with `structured-debate`.
- If you are telling the generator what must change next, use RULE:/BECAUSE:
  format.

## Output Standard

A good correction block should let the next generator answer:

- What exactly must change?
- Why does it need to change?
- How narrow or broad is the instruction?

If the next generator could misread the instruction as vague commentary, rewrite
it as a rule.
