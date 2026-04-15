## Prompt 1: Produce Requirements Inventory

### Module

requirements-inventory

### Required Files

docs/requirements/raw-requirements.md

### Checks Files

docs/requirements/requirements-inventory.yaml

### Deterministic Validation

scripts/phase-0-deterministic-validation.py
--requirements-inventory
docs/requirements/requirements-inventory.yaml
--raw-requirements
docs/requirements/raw-requirements.md

### Generation Prompt

You are producing the phase artifact for PH-000-requirements-inventory.

Read:
- docs/requirements/raw-requirements.md

Write:
- docs/requirements/requirements-inventory.yaml

Task:
Produce the final acceptance-ready YAML requirements inventory in one file.
Use this prompt pair's built-in revise loop to correct any issues the judge
finds. Do not create draft-only or partial versions on purpose.

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
  split them into separate RI-* items while keeping each verbatim_quote exactly
  grounded in the original wording.

Output schema to satisfy:
source_document: "docs/requirements/raw-requirements.md"
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
- source_document must be exactly docs/requirements/raw-requirements.md.
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

Read:
- docs/requirements/raw-requirements.md
- docs/requirements/requirements-inventory.yaml

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

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
     requirement-bearing clauses that should have been separated.
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
