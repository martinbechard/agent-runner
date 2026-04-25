### Module

requirements-inventory

## Prompt 1: Produce Requirements Inventory

### Required Files

{{raw_requirements_path}}

### Deterministic Validation

python-module:methodology_runner.phase_0_validation
--requirements-inventory
docs/requirements/requirements-inventory.yaml
--requirements-coverage
docs/requirements/requirements-inventory-coverage.yaml
--raw-requirements
{{raw_requirements_path}}

### Generation Prompt

As a software analyst, produce the PH-000 requirements inventory from the
embedded <RAW_REQUIREMENTS>.

Goal:
- Build the acceptance-ready requirements inventory for downstream design and
  implementation work.
- Write the inventory to docs/requirements/requirements-inventory.yaml.
- Write the coverage support file to
  docs/requirements/requirements-inventory-coverage.yaml.

Context:
- Use this authoritative user request:
<RAW_REQUIREMENTS>
{{INCLUDE:raw_requirements_path}}
</RAW_REQUIREMENTS>
- This phase is an extraction phase, not an elaboration phase. Capture what
  the request requires so later phases can design and implement from it.

Constraints:
- Use only the information embedded in this prompt.
- Do not inspect the filesystem to discover additional source material.
- Do not re-read files whose contents are already embedded in this prompt.
- Only touch the filesystem when you need to create or update the required
  output artifacts.
- Walk <RAW_REQUIREMENTS> in document order. Read the whole request once, then
  process each section, paragraph, bullet, and table row in order.
- Extract every requirement-bearing statement, constraint, assumption, and
  explicit definition-of-done check.
- Treat a list item as a requirement-bearing source span when it appears under
  a requirement-bearing lead-in such as "must support", "must include",
  "must show", "must provide", "must expose", "must cover", or "must handle".
  In these cases, the lead-in supplies local context, but each listed entry is
  independently satisfiable unless the list item itself says otherwise.
- For enumerated support/include/show/cover lists, create separate RI items for
  each independently satisfiable bullet, numbered list item, table row, or
  comma-separated field in a list item when each child can use an exact
  contiguous source phrase as its verbatim_quote.
- Use only contiguous source wording in verbatim_quote. Do not concatenate
  non-adjacent bullets, skip intervening bullets inside one quote, or quote an
  entire list when the individual entries are separately satisfiable.
- When a lead-in sentence is needed to make a listed entry standalone, include
  that context in normalized_requirement and source_location rather than
  expanding verbatim_quote beyond the exact listed entry.
- For each RI item:
  - keep the exact source wording in verbatim_quote
  - write normalized_requirement as a coherent standalone software
    requirement that preserves the same meaning
  - if the source gives a reason, justification, or explanatory scope for
    that requirement, preserve it in the justification field
- Split a sentence into separate RI items only when:
  - the clauses are independently satisfiable or verifiable
  - and each child item can keep its own exact source-faithful
    verbatim_quote
- Do not split when:
  - the clauses are inseparable parts of one behavior
  - inline `or` lists describe alternative ways to satisfy one behavior
  - splitting would require rewritten, normalized, or invented child quotes
- If a sentence is semantically compound but exact child quotes do not exist,
  keep the original sentence as one RI item and let the separate coverage file
  map multiple requirement-bearing phrases to that one item.
- Category rules:
  - `shall`, `must`, `will`, `need to` usually signal `functional`
  - `should`, `ought to`, `ideally` usually signal `non_functional`
  - quantified bounds such as `within`, `at most`, `limited to`,
    `must not exceed` usually signal `constraint`
  - explicit assumption language such as `assuming`, `given that`,
    `provided that` usually signals `assumption`
- When signals conflict, prefer the more specific boundary or assumption
  pattern over the weaker general verb pattern.
- Preserve contradictions, ambiguity, and source force exactly as written.
- Do not paraphrase, summarize, clarify, operationalize, resolve, or improve
  the source.
- Do not invent supporting detail, implementation assumptions, or downstream
  structure.
- normalized_requirement may use local source context from
  <RAW_REQUIREMENTS> to become standalone, but it must not add behavior,
  scope, thresholds, actors, or constraints not supported by the request.

Done when:
- The inventory satisfies this schema:
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
- The coverage file satisfies this schema:
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
- On a retry, if cross-reference retry guidance is supplied and the two output
  artifacts already exist, you may read only those two artifacts before editing
  them. Use the retry guidance to revise the existing artifacts directly; do
  not inspect any other filesystem content.
- If the runtime does not expose a named file-write tool, use shell commands
  or the available file-edit mechanism to create the files directly.
- After writing both files, review the coverage file against
  <RAW_REQUIREMENTS>. If any requirement-bearing content is still missing,
  complete the inventory and the coverage file and review again. Repeat until
  the coverage file shows full coverage with no orphaned or invented phrases.
- End your response with:
  DIAGNOSTICS:
  - Files read from the filesystem during this turn: none | <list>
  - If you read any files from the filesystem, explain why each read was necessary.

### Validation Prompt

As the PH-000 judge, decide whether the current requirements inventory is
ready for downstream phases.

Goal:
- Determine whether the inventory faithfully captures the requirement-bearing
  content of <RAW_REQUIREMENTS> in a form later phases can safely consume.

Context:
- Judge against this authoritative request:
<RAW_REQUIREMENTS>
{{INCLUDE:raw_requirements_path}}
</RAW_REQUIREMENTS>
- The artifact under review is embedded here:
<REQUIREMENTS_INVENTORY>
{{RUNTIME_INCLUDE:docs/requirements/requirements-inventory.yaml}}
</REQUIREMENTS_INVENTORY>
- The separate coverage file is not the artifact being judged here.

Constraints:
- Use the deterministic validation report as authoritative for structural
  checks, exact quote presence, ID validity, and inventory top-level schema
  shape.
- Do not re-run or duplicate those checks manually.
- Focus on material semantic problems only.
- Do not ask for wording polish, alternate tags, or stylistic rewrites when
  the inventory is already source-faithful and phase-ready.
- Value and fidelity standard:
  - A useful inventory preserves the user's requested software obligations so
    later phases can build the right thing without reinterpreting the raw
    request.
  - Do not pass entries that are technically well-formed but collapse distinct
    obligations, dilute exact limits, or replace source intent with vague
    phrasing.
  - Do not request low-value restatement of prose that has no downstream
    actionability.
- Review in this order:
  - Iterate through the inventory item by item in RI-* order.
  - For each item, compare normalized_requirement and justification against
    verbatim_quote and the local source context in <RAW_REQUIREMENTS>.
  - For each item, answer these questions before moving on:
    - Does normalized_requirement fail to capture the original meaning?
    - Does normalized_requirement add unsupported detail or interpretation?
    - Does category materially misstate the kind of requirement?
    - Does this item omit an important clause or qualifier that belongs with it?
    - If the source text gives a reason, justification, or explanatory scope
      statement for the requirement, does the inventory preserve it in the
      justification field instead of dropping it?
  - Then review <RAW_REQUIREMENTS> section by section to catch any important
    requirement-bearing content that is still missing from the inventory
    entirely.
- Before flagging something as missing, check whether its downstream-meaningful
  content is already covered by one or more other RI items. Do not demand a
  duplicate summary or umbrella item unless it adds distinct actionable meaning.
- Only report material issues:
  - missing requirement-bearing statements, clauses, or sections
  - normalized requirements that fail to capture the original meaning
  - source-provided justification or explanatory scope that is missing from
    the item's justification field
  - normalized requirements that add unsupported detail or interpretation
  - invented requirement content or unsupported assumptions
  - wrong category when it materially changes the inventory meaning

Done when:
- If you find issues, respond using this structure:
  QUERY: What important parts of the user request are not correctly represented in the inventory?
  MISSING-ELEMENTS:
  - itemize only the important missing or wrong elements from the user request
  - cite the exact source phrase or location
  - cite the affected RI-* ids and normalized_requirement values when relevant
  REQUIRED-CHANGES:
  - state only the concrete changes the generator must make
  - say how normalized_requirement must change when the problem is meaning loss
  - say how the justification field must include missing source-provided
    justification when that is the defect
  - each item must be directly actionable
  VERDICT-BASIS:
  - briefly say why the inventory is not yet phase-ready
- Keep the response short and concrete.
- Do not explain your review process.
- Do not add design commentary.
- Do not restate the whole request.
- Use VERDICT: pass only if there are no material missing elements, no
  normalized requirements with meaning loss or unsupported added meaning, no
  missing source-provided justification that belongs with the requirement, no
  invented requirements, and no materially wrong categories.
- Use VERDICT: revise if the inventory can be corrected within this same file.
- Use VERDICT: escalate only if the raw requirements are too ambiguous or
  contradictory to produce a stable inventory without external clarification.
- End with exactly one of:
  VERDICT: pass
  VERDICT: revise
  VERDICT: escalate

### Retry Prompt [PREPEND]

You are revising an existing requirements inventory and coverage file.

Goal:
- Revise the existing requirements inventory and coverage files in place.
- Apply every required change from <REQUIRED_CHANGES> while preserving content
  that is already correct.

Context:
- The original task is below.
- The current inventory state is provided here:
<REQUIREMENTS_INVENTORY>
{{RUNTIME_INCLUDE:docs/requirements/requirements-inventory.yaml}}
</REQUIREMENTS_INVENTORY>
- The judge's required corrections are provided in <REQUIRED_CHANGES>.

Constraints:
- Do not restart from scratch unless the required changes make that necessary.
- Before applying the fixes, analyze why the previous iteration introduced the
  reported errors.
- Include:
  ERROR-ANALYSIS:
  - explain why the previous iteration likely introduced the errors
  - focus on the likely prompt or interpretation failure, not just the symptom
  - call out if you treated source text as out of scope when it should have
    been inventory content
  - call out if you over-split or under-split a source sentence
- Preserve content that already satisfies the original task unless a required
  change directly contradicts it.

Done when:
- Both required files have been updated to satisfy <REQUIRED_CHANGES>.
- The response still ends with:
  DIAGNOSTICS:
  - Files read from the filesystem during this turn: none | <list>
  - If you read any files from the filesystem, explain why each read was necessary.
