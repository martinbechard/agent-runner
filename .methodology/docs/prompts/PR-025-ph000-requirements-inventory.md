### Module

requirements-inventory

## Prompt 1: Produce Requirements Inventory

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
--requirements-coverage
docs/requirements/requirements-inventory-coverage.yaml
--raw-requirements
{{raw_requirements_path}}

### Generation Prompt

As a software analyst, you must decompose the following RAW_REQUIREMENTS according to the rules below.

Write the requirements inventory to docs/requirements/requirements-inventory.yaml.
Write the coverage support file to docs/requirements/requirements-inventory-coverage.yaml.

The raw request is provided above in <RAW_REQUIREMENTS>.
The current inventory artifact is provided above in <REQUIREMENTS_INVENTORY>.

IMPORTANT: Use the information provided in this prompt only to perform your work.
Do not inspect the filesystem to discover additional source material. Do not
re-read files whose contents are already embedded in this prompt. Only touch
the filesystem when you need to create or update the required output artifact.

Module-local generator context:
Embedded directives for this step:

- Walk the source in document order. Read the whole document once, then
  process each section, paragraph, bullet, and table row in order.
- Extract every requirement-bearing statement, constraint, assumption, and
  explicit definition-of-done check.
- For each RI item, keep the exact source quote and also write a normalized
  software requirement that captures the same meaning in coherent standalone
  requirement language.
- If the source text gives a reason, justification, or explanatory scope for
  the requirement, record it in a dedicated justification field on that same
  inventory item.
- Split a sentence into separate RI items only when:
  - the clauses are independently satisfiable or verifiable
  - and each child item can keep its own exact source-faithful
    verbatim_quote
- Do not split when:
  - the clauses are inseparable parts of one behavior
  - `or` lists options inside one capability
  - splitting would require rewritten, normalized, or invented child quotes
- If a sentence is semantically compound but exact child quotes do not exist,
  keep the original sentence as one RI item and let the separate coverage file
  map multiple requirement-bearing phrases to that one item.
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
- Reformulate each item into a coherent normalized_requirement that preserves
  the same meaning for downstream software design work.
- Preserve any source-provided reason, justification, or explanatory scope in
  a dedicated justification field on the same item.
- Classify each item as functional, non_functional, constraint, or assumption.
- Record any explicit deferrals in out_of_scope.
- Maintain a separate coverage file so you can check whether anything from the
  source is still missing from the inventory.

Important interpretation:
- This phase is an extraction layer, not an elaboration layer.
- Do not paraphrase, summarize, clarify, operationalize, or improve the source.
- Do not invent supporting detail, implementation assumptions, or downstream
  structure.
- normalized_requirement must make the requirement coherent and standalone for
  downstream phases, but it must not add behavior, scope, thresholds, actors,
  or constraints that are not supported by the source wording and its local
  context.
- When a sentence contains multiple independent requirement-bearing clauses,
  split them into separate RI-* items only when each resulting item can keep
  its own exact source-faithful verbatim_quote. If splitting would require
  rewritten or invented child quotes, keep the original sentence as one RI
  item and let the separate coverage file map multiple source phrases to that
  one item.

Inventory output schema to satisfy:
source_document: "<source document path>"
items:
  - id: "RI-NNN"
    category: "functional"
    verbatim_quote: "Exact source wording"
    normalized_requirement: "Coherent standalone software requirement"
    justification: "Source-provided reason or explanatory scope, or empty string if none"
    source_location: "Section > paragraph or bullet identifier"
    tags: ["keyword", "..."]
    rationale:
      rule: "Extraction rule name"
      because: "Why this is a separate item"
    open_assumptions: []
out_of_scope:
  - inventory_ref: "RI-NNN"
    reason: "Why this item is explicitly deferred"

Coverage output schema to satisfy:
source_document: "<source document path>"
inventory_document: "docs/requirements/requirements-inventory.yaml"
coverage_check:
  "Phrase from source": ["RI-NNN", "..."]
  status: "N/N requirement-bearing phrases covered, 0 orphans, 0 invented"
coverage_verdict:
  total_upstream_phrases: 0
  covered: 0
  orphaned: 0
  invented: 0
  verdict: "PASS"

Acceptance requirements:
- The file must be valid YAML parseable by a standard YAML parser.
- The top-level keys must appear exactly in this order:
  source_document
  items
  out_of_scope
- source_document must be exactly {{raw_requirements_path}}.
- Every item must contain:
  id
  category
  verbatim_quote
  normalized_requirement
  justification
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
- normalized_requirement must restate the same requirement meaning as a
  coherent standalone software requirement without adding unsupported detail.
- justification must preserve any source-provided reason, justification, or
  explanatory scope that belongs with the requirement. Use an empty string
  when the source provides none.
- source_location must identify where the quote came from using the source's
  visible section structure and paragraph or bullet position.
- tags must be a non-empty list of short domain keywords.
- rationale must contain:
  rule
  because
- open_assumptions must always be present. Use an empty list when none exist.
- Write the full file contents to docs/requirements/requirements-inventory.yaml.
- Write the full coverage bookkeeping to docs/requirements/requirements-inventory-coverage.yaml.
- The coverage file must use exactly these top-level keys in this order:
  source_document
  inventory_document
  coverage_check
  coverage_verdict
- The coverage file's source_document must be exactly {{raw_requirements_path}}.
- The coverage file's inventory_document must be exactly docs/requirements/requirements-inventory.yaml.
- Every requirement-bearing phrase in the source must appear in the coverage file's coverage_check.
- Every coverage_check value must list one or more real RI-* ids from the inventory that cover the phrase.
- coverage_verdict must summarize the actual counts and use PASS only when
  there are no orphaned phrases and no invented phrases.
- Do not create any files other than:
  docs/requirements/requirements-inventory.yaml
  docs/requirements/requirements-inventory-coverage.yaml
- If the runtime does not expose a named file-write tool, use shell commands
  or the available file-edit mechanism to create the files directly.

Review step:
After writing the inventory and the coverage file, review the coverage file to
check whether any requirement-bearing source content is still missing. If
anything is missing, complete the inventory and the coverage file and review
again. Repeat until the coverage file shows full coverage with no orphaned or
invented phrases.

If this is a revise iteration, also analyze why the previous iteration
introduced the judge-reported errors before you apply the fixes. Include that
analysis in your response under:

ERROR-ANALYSIS:
- explain why the previous iteration likely introduced the errors
- focus on the likely prompt or interpretation failure, not just the symptom
- call out if you treated source text as out of scope when it should have been
  inventory content
- call out if you over-split or under-split a source sentence

End your response with this diagnostic block:

ERROR-ANALYSIS:
- omit this block on iteration 1
- include it on revise iterations

DIAGNOSTICS:
- Files read from the filesystem during this turn: none | <list>
- If you read any files from the filesystem, explain why each read was necessary.

### Validation Prompt

Review the current requirements inventory artifact against the authoritative
user request in <RAW_REQUIREMENTS>.
The current inventory artifact is provided above in <REQUIREMENTS_INVENTORY>.

Your job is to decide whether the generated requirements inventory is phase-ready.

Use the deterministic validation report as authoritative for structural checks,
exact quote presence, ID validity, and inventory top-level schema shape. Do
not re-run or duplicate those checks manually. Do not review the separate
coverage file. Focus on the real inventory artifact only.

Review method:
- Iterate through the inventory item by item in RI-* order.
- For each item, compare normalized_requirement against verbatim_quote and the
  local source context in <RAW_REQUIREMENTS>.
- For each item, answer these questions before moving on:
  - Does normalized_requirement fail to capture the original meaning?
  - Does normalized_requirement add unsupported detail or interpretation?
  - Does category materially misstate the kind of requirement?
  - Does this item omit an important clause or qualifier that belongs with it?
  - If the source text gives a reason, justification, or explanatory scope
    statement for the requirement, does the inventory preserve it in the
    item's justification field instead of dropping it?
- Then review the raw request section by section to catch any important
  requirement-bearing content that is still missing from the inventory
  entirely.

Focus on the important content from the user request that is missing,
materially distorted, or unsupported in the inventory.

Only report material issues:
- missing requirement-bearing statements, clauses, or sections
- normalized requirements that fail to capture the original meaning
- source-provided justification or explanatory scope that is missing from the
  inventory item's justification field
- normalized requirements that add unsupported detail or interpretation
- invented requirement content or unsupported assumptions
- wrong category when it materially changes the inventory meaning

Do not ask for wording polish, alternate tags, or stylistic rewrites when the
inventory is already source-faithful and phase-ready.

If you find issues, respond using this structured explanation format:

QUERY: What important parts of the user request are not correctly represented in the inventory?

MISSING-ELEMENTS:
- itemize only the important missing or wrong elements from the user request
- cite the exact source phrase or location
- cite the affected RI-* ids and normalized_requirement values when relevant

REQUIRED-CHANGES:
- state only the concrete changes the generator must make
- say how the normalized_requirement must change when the problem is meaning loss
- say how the justification field must include missing source-provided
  justification when that is the defect
- each item must be directly actionable

VERDICT-BASIS:
- briefly say why the inventory is not yet phase-ready

Keep the response short and concrete. Do not explain your review process. Do
not add design commentary. Do not restate the whole request.

Use VERDICT: pass only if there are no material missing elements, no normalized
requirements with meaning loss or unsupported added meaning, no missing
source-provided justification that belongs with the requirement, no invented
requirements, and no materially wrong categories.
Use VERDICT: revise if the inventory can be corrected within this same file.
Use VERDICT: escalate only if the raw requirements are too ambiguous or
contradictory to produce a stable inventory without external clarification.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
