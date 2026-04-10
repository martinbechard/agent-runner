# Skill Authoring Context — Lessons Learned

This file is read by each interactive skill-authoring session. It
accumulates lessons, patterns, and decisions from earlier sessions so
later sessions start with the benefit of what was learned before.

Update this file after each session with anything the NEXT session
should know. Keep entries concise and actionable.

---

## From Prompt 2: traceability-discipline skill

### AI-consumable skill format

Tested 7 variants (A through G) with adversarial child-Claude evaluation.
Key findings:

1. **Input->output transformation examples teach AI agents far better than
   prose rules.** All variants with concrete YAML before/after pairs
   outperformed rules-only variants. Lead with examples, extract rules as
   a scannable checklist afterward.

2. **source_quote (exact text) prevents hallucination better than source_refs
   (ID pointers).** Variant D (refs only) produced 4+ phantom requirements
   under adversarial pressure. Variant G (refs + quotes) produced 0 phantoms.
   The "Quote Test" is the key mechanism: if you cannot quote source text that
   justifies your element, delete the element.

3. **Structured open_assumptions with lifecycle states (open/confirmed/
   invalidated) enable downstream propagation.** Downstream test confirmed
   all 5 upstream assumptions inherited correctly as inherited_assumptions.
   Without this, assumed specifics silently become confirmed scope.

4. **Element text should stay close to the source_quote. Added specifics
   belong in open_assumptions, not in the confirmed text.** This prevents
   the agent from baking training-data defaults into requirements.

5. **Counter-examples inline with correct examples are highly effective.**
   Showing the wrong output right next to the correct output (with a comment
   explaining why it fails) teaches anti-patterns better than a separate
   anti-patterns section.

6. **Adversarial testing with "be thorough" pressure is essential.** The
   prompt "think about everything users might need - security, performance,
   accessibility" triggers phantom requirement generation. Any skill that
   constrains AI output must survive this pressure test.

### Artifact design principles

- Artifacts are consumed by the NEXT AI agent, not by humans. Design for
  machine consumption: structured YAML, explicit cross-references, self-
  contained elements.
- The RULE/BECAUSE tree format (from procedure-creation-rules.md) works
  well for AI consumption. Nested BECAUSE clauses preserve the reasoning
  chain across phase boundaries.
- Coverage checks (upstream->downstream mappings) at the end of every
  artifact make orphans and gaps self-evident.

### Assumption handling

- Assumptions are first-class data with a three-state lifecycle:
  open -> confirmed (becomes fact), open -> invalidated (triggers re-gen),
  open -> open (persists, propagates).
- The ratio of confirmed items to assumptions signals source quality.
  A 1:28 ratio from a single sentence is correct, not a failure.
- The orchestrator should detect open_assumptions (regex or structured
  scan) and trigger an assumption-verifier agent when found.
- Assumptions group by review owner (product, UX, security, architecture)
  enabling parallel stakeholder review.

### Testing methodology

- Use child Claude processes (claude -p) to test skill variants
- Test with: (a) normal prompt, (b) adversarial phantom pressure,
  (c) downstream consumption (feed output to next-phase agent)
- Compare variants on: rule recall, output quality, phantom suppression,
  assumption separation, downstream usability

