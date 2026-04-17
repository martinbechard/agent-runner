## Prompt 1: Produce Requirements Inventory

### Module

requirements-inventory

### Required Files

{{raw_requirements_path}}

### Include Files

{{raw_requirements_path}}

### Checks Files

docs/requirements/requirements-inventory.yaml

### Deterministic Validation

.methodology/src/cli/methodology_runner/phase_0_validation.py
--requirements-inventory
docs/requirements/requirements-inventory.yaml
--raw-requirements
{{raw_requirements_path}}

### Generation Prompt

You are producing the phase artifact for PH-000-requirements-inventory.

Use the following as the primary source input:
<Source input>
{{INCLUDE:raw_requirements_path}}
</Source input>

Write:
- docs/requirements/requirements-inventory.yaml

Task:
Produce the final acceptance-ready YAML requirements inventory in one file.
Use this prompt pair's built-in revise loop to correct any issues the judge
finds. Do not create draft-only or partial versions on purpose.

Module-local generator context:
Embedded directives for this step:
<Traceability directives>
{{INCLUDE:../../skills/traceability-discipline/SKILL.md}}
</Traceability directives>

- Walk the source in document order. Read the whole document once, then
  process each section, paragraph, bullet, and table row in order.
- Extract every requirement-bearing statement, constraint, assumption, and
  explicit definition-of-done check.
- Split a sentence into separate RI items only when:
  - the clauses are independently satisfiable or verifiable
  - and each child item can keep its own exact source-faithful
    verbatim_quote
- Do not split when:
  - the clauses are inseparable parts of one behavior
  - `or` lists options inside one capability
  - splitting would require rewritten, normalized, or invented child quotes
- If a sentence is semantically compound but exact child quotes do not exist,
  keep the original sentence as one RI item and let coverage_check map
  multiple requirement-bearing phrases to that one item.
- Category rules:
  - `shall`, `must`, `will`, `need to` usually signal `functional`
  - `should`, `ought to`, `ideally` usually signal `non_functional`
  - quantified bounds such as `within`, `at most`, `limited to`, `must not exceed`
    signal `constraint`
  - explicit assumption language such as `assuming`, `given that`, `provided that`
    signals `assumption`
- When signals conflict, prefer the more specific boundary or assumption
  pattern over the weaker general verb pattern.
- Preserve contradictions, ambiguity, and source force exactly as written.
- Do not resolve, improve, or operationalize the source.

Phase purpose:
- Extract every requirement-bearing statement into RI-* inventory items.
- Split compound requirements into atomic items.
- Preserve the source wording exactly in verbatim_quote.
- Classify each item as functional, non_functional, constraint, or assumption.
- Record any explicit deferrals in out_of_scope.
- Make source coverage explicit in coverage_check and coverage_verdict.

Important interpretation:
- This phase is an extraction layer, not an elaboration layer.
- Do not paraphrase, summarize, clarify, operationalize, or improve the source.
- Do not invent supporting detail, implementation assumptions, or downstream
  structure.
- When a sentence contains multiple independent requirement-bearing clauses,
  split them into separate RI-* items only when each resulting item can keep
  its own exact source-faithful verbatim_quote. If splitting would require
  rewritten or invented child quotes, keep the original sentence as one RI
  item and let coverage_check map multiple source phrases to that one item.

Output schema to satisfy:
source_document: "{{raw_requirements_path}}"
items:
  - id: "RI-NNN"
    category: "functional"
    verbatim_quote: "Exact source wording"
    source_location: "Section > paragraph or bullet identifier"
    tags: ["keyword", "..."]
    rationale:
      rule: "Extraction rule name"
      because: "Why this is a separate item"
    open_assumptions: []
out_of_scope:
  - inventory_ref: "RI-NNN"
    reason: "Why this item is explicitly deferred"
coverage_check:
  "Phrase from source": ["RI-NNN", "..."]
  status: "N/N requirement-bearing phrases covered, 0 orphans, 0 invented"
coverage_verdict:
  total_upstream_phrases: 0
  covered: 0
  orphaned: 0
  out_of_scope: 0
  open_assumptions: 0
  verdict: "PASS"

Acceptance requirements:
- The file must be valid YAML parseable by a standard YAML parser.
- The top-level keys must appear exactly in this order:
  source_document
  items
  out_of_scope
  coverage_check
  coverage_verdict
- source_document must be exactly {{raw_requirements_path}}.
- Every item must contain:
  id
  category
  verbatim_quote
  source_location
  tags
  rationale
  open_assumptions
- All ids must be unique and use the RI-NNN format.
- category must be one of:
  functional
  non_functional
  constraint
  assumption
- verbatim_quote must reproduce source wording exactly, with no paraphrase.
- source_location must identify where the quote came from using the source's
  visible section structure and paragraph or bullet position.
- tags must be a non-empty list of short domain keywords.
- rationale must contain:
  rule
  because
- open_assumptions must always be present. Use an empty list when none exist.
- Every requirement-bearing phrase in the source must appear in coverage_check.
- Every coverage_check value must list one or more real RI-* ids that cover the
  phrase.
- coverage_verdict must summarize the actual counts and use PASS only when
  there are no orphaned phrases and no invented items.
- Do not create any files other than docs/requirements/requirements-inventory.yaml.
- Use the Write tool to write the full file contents to docs/requirements/requirements-inventory.yaml.

### Validation Prompt

Use the following as the primary review input:
<Source input>
{{INCLUDE:raw_requirements_path}}
</Source input>

Read:
- docs/requirements/requirements-inventory.yaml

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Module-local judge context:
Embedded directives for this step:
<Traceability directives>
{{INCLUDE:../../skills/traceability-discipline/SKILL.md}}
</Traceability directives>

- Review in two passes:
  1. Source to inventory: walk the source section by section and check that
     every requirement-bearing section or bullet is represented.
  2. Inventory to source: inspect each RI item for wrong category, lost
     nuance, unsupported assumptions, and unsplit compounds that could be
     split without breaking exact quote fidelity.
- Treat these as blocking defects:
  - silent omission of a requirement-bearing statement, clause, or section
  - invented requirement or invented quote content
  - unsplit compound only when each child could keep its own exact quote
  - wrong category for the source language signal
  - lost nuance that changes scope, force, or specificity
  - unsupported assumptions that add concrete specifics not implied upstream
- Quote fidelity outranks splitting. If a split would require rewritten child
  quotes, do not require the split.
- Use exact RI ids and exact source locations in findings.

Your job is to decide whether the generated requirements inventory is phase-ready.
Focus your semantic review on these failure modes:

1. Silent omissions:
   - Flag any requirement-bearing source statement or clause that is not
     represented by at least one RI-* item, even if coverage bookkeeping looks
     superficially complete.
2. Invented requirements:
   - Flag any item whose verbatim_quote, implication, or category introduces a
     requirement not actually supported by the source text.
3. Unsplit compounds:
   - Flag any RI-* item that still contains multiple independent
     requirement-bearing clauses that should have been separated, but only when
     each resulting child item could still carry its own exact source-faithful
     verbatim_quote.
4. Lost nuance:
   - Flag extractions that change the source's force, modality, scope, or
     specificity even if the wording looks similar.
5. Wrong categories:
   - Flag items whose category does not match the actual source language and
     function in the document.
6. Unsupported assumptions:
   - Flag any open_assumptions entry that smuggles in concrete specifics rather
     than recording a real uncertainty already implied by the source.

Review instructions:
- Use the deterministic validation report as authoritative for structural
  checks, exact-quote presence, ID validity, coverage bookkeeping, and top-level
- schema shape.
- This phase is not an invention or elaboration layer. Judge fidelity very
  strictly.
- Quote fidelity outranks splitting. Do not require decomposition into
  separate RI items when the source does not provide exact source-faithful
  child quotes for the decomposed clauses.
- Only ask for a change when the inventory is wrong, incomplete, non-atomic,
  materially misclassified, or materially unsupported by the source.
- Do not ask for wording polish, alternate tags, or stylistic rewrites when the
  extraction is already source-faithful and phase-ready.
- If you find issues, cite exact RI-* ids and the exact source phrase or
  location involved.
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary
- Use VERDICT: pass only if the artifact is phase-ready with no material
  omissions, inventions, unsplit compounds, or category defects.
- Use VERDICT: revise if the artifact can be corrected within this same file.
- Use VERDICT: escalate only if the raw requirements are too ambiguous or
  contradictory to produce a stable inventory without external clarification.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
