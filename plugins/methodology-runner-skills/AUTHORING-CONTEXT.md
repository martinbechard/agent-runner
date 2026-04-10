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


## From Prompt 3: requirements-extraction skill

### Structural variant testing

Tested 5 structural variants (A through E) plus 1 hybrid (BA) with
adversarial child-Claude evaluation. Source: Sonnet model under maximum
phantom pressure ("be thorough, think about security, monitoring,
accessibility, edge cases, best practices"). Key findings:

1. **Procedure-first structure improves category discrimination.** Variant
   B (procedure -> transforms -> traps) was the only pure variant that
   correctly applied "should -> non_functional" in all tests. The systematic
   walk procedure primes the agent to consult the category table BEFORE
   pattern-matching from examples. Transforms alone are not enough to teach
   judgment rules — the procedure provides the scaffolding.

2. **Explicit table row guidance is mandatory.** Without an explicit
   instruction ("extract each row as a SINGLE item — do not split individual
   cells"), 3 of 5 variants over-split table rows into per-cell items. The
   skill's own Transform 2 showed rows as single items, but examples alone
   were not enough. An explicit procedural rule was needed.

3. **Hybrid structures outperform pure variants on consistency.** The BA
   hybrid (B's procedure + A's transforms) produced identical output under
   adversarial and normal pressure. Neither pure A nor pure B achieved this.
   The procedure provides systematic discipline; the transforms provide
   pattern recognition. Both are needed, and their interaction is
   super-additive.

4. **Counter-examples for specific miscategorizations are highly effective.**
   Adding a counter-example showing "should" incorrectly categorised as
   "functional" (with explanation pointing to the category rule) was the key
   addition that made the hybrid consistently categorise correctly where pure
   A failed under pressure. One targeted counter-example outperformed general
   rules.

5. **Anti-invention discipline is robust across all structural arrangements.**
   Zero phantoms across all 5 variants + hybrid under maximum adversarial
   pressure. The Invention Test ("can I point to the EXACT sentence?") and
   the Invention Traps table are the load-bearing elements. Their position in
   the document does not matter — what matters is their presence.

6. **Decision-tree structure (Variant D) caused a silent omission.** D was
   the only variant to miss a legitimate requirement (RabbitMQ constraint).
   Rigid flowchart structures may cause agents to skip statements that do not
   cleanly pattern-match to the decision nodes. Avoid flowcharts as the
   primary organisational structure for extraction skills.

7. **"Prefer the weaker category" needs triple reinforcement.** Stating the
   rule once was insufficient (4 of 5 variants ignored it under pressure).
   The hybrid reinforced it with: (a) explicit ALWAYS emphasis in the
   procedure, (b) a worked example in the Transform 2 commentary, AND (c) a
   counter-example showing the wrong categorisation. All three were needed
   for consistent compliance. General principle: rules that require agents
   to resist their defaults need rule + example + counter-example, not just
   one of the three.

8. **Test with a novel source, not the skill's own examples.** The
   notification service test source was entirely different from both skill
   examples (LOC counter and Project Alpha). This tested generalisation, not
   memorisation. All variants generalised well on extraction and invention
   resistance, but diverged on judgment calls (categories, splitting
   granularity), revealing the structural differences that matter.

### Orchestrator note

The baseline validator (validate_against_catalog) checks ALL phases'
skills globally, not just the phases requested via --phases. Running
with --phases PH-000 still halts if PH-001+ skills are missing. This
is current behaviour, not a bug in the skill. The verification for
skill discovery should use build_catalog() directly, not the full
pipeline.

