# Design: PH-000 Prompt Purpose, Coverage, And Convergence

This design explains what the PH-000 prompt pair is supposed to accomplish at
the current stage of the methodology runner, with emphasis on the purpose of
the inventory artifact, the purpose of the coverage structures, and the role
of the generator and judge in converging on a phase-ready result.

## 1. Finality

- **GOAL: GOAL-1** Convert a raw request into a source-grounded inventory
  - **SYNOPSIS:** PH-000 must take the raw user request and convert it into a
    structured inventory of requirement-bearing content.
  - **BECAUSE:** Later phases should build from an explicit inventory of what
    the source actually says, not from fresh free-form rereads of the request.

- **GOAL: GOAL-2** Make the source coverage explicit
  - **SYNOPSIS:** PH-000 must make it visible which parts of the raw request
    are represented in the inventory and which are not.
  - **BECAUSE:** Extraction quality cannot be judged reliably if omissions,
    orphans, and invented material stay implicit.

- **GOAL: GOAL-3** Produce one phase-ready canonical artifact
  - **SYNOPSIS:** The phase must converge on one
    `docs/requirements/requirements-inventory.yaml` artifact.
  - **BECAUSE:** Downstream phases need one stable source of truth.

## 2. Phase-Specific Purpose

- **PROCESS: PROCESS-1** What PH-000 is for
  - **SYNOPSIS:** PH-000 is an extraction phase, not a design phase and not a
    specification-writing phase.
  - **BECAUSE:** Its job is to preserve and structure source meaning before
    later phases elaborate, group, design, or implement anything.

- **RULE: RULE-1** Preserve source force and wording
  - **SYNOPSIS:** PH-000 must preserve the source wording exactly in
    `verbatim_quote` and must preserve the source force such as obligation,
    preference, bound, or assumption.
  - **BECAUSE:** Later phases need to know not just what topic exists, but how
    strongly and in what form the source expressed it.

- **RULE: RULE-2** Create reviewable inventory boundaries
  - **SYNOPSIS:** PH-000 must turn the source into reviewable `RI-*` items with
    stable boundaries.
  - **BECAUSE:** Later phases cannot reason cleanly about requirements if one
    inventory item mixes several independently meaningful clauses.

- **RULE: RULE-3** Do not elaborate beyond the source
  - **SYNOPSIS:** PH-000 must not add implementation detail, hidden
    assumptions, design structure, or test design that is not explicitly in
    the raw request.
  - **BECAUSE:** The value of PH-000 is that it creates a disciplined
    extraction layer before any later interpretation.

## 3. What The Prompting Must Accomplish

- **PROCESS: PROCESS-2** Generator purpose
  - **SYNOPSIS:** The generator prompt must cause the model to do five
    phase-specific things:
    - identify requirement-bearing content in the raw request
    - split that content into reviewable RI items when justified
    - preserve exact source quotes
    - classify each item by kind
    - produce explicit source-coverage bookkeeping
  - **BECAUSE:** Those are the actual PH-000 deliverables, not generic prompt
    execution mechanics.
  - **RULE:** Identify requirement-bearing content in the raw request
    - **SYNOPSIS:** The generator must first determine which parts of the raw
      request carry obligation, preference, bound, assumption, or explicit
      definition-of-done meaning.
    - **CHAIN-OF-THOUGHT:** PH-000 can only inventory what it first recognizes
      as requirement-bearing source content.
    - **BECAUSE:** If the generator misses that first identification step, the
      later inventory, categorization, and coverage work will all be incomplete.
  - **RULE:** Split content into reviewable RI items when justified
    - **SYNOPSIS:** The generator must create separate RI items when the source
      contains independently meaningful clauses that can be represented without
      paraphrase.
    - **CHAIN-OF-THOUGHT:** PH-000 is trying to create stable inventory
      boundaries that later phases and reviewers can reason about directly.
    - **BECAUSE:** Without justified splitting, the inventory either merges too
      much meaning into one item or invents unnatural child items that the
      source never stated cleanly.
  - **RULE:** Preserve exact source quotes
    - **SYNOPSIS:** The generator must keep the original source wording in each
      `verbatim_quote`.
    - **CHAIN-OF-THOUGHT:** The inventory is supposed to be an extraction
      product, so each item must remain auditable against the real request.
    - **BECAUSE:** Exact quotes are what prevent PH-000 from quietly drifting
      into paraphrase, normalization, or invented wording.
  - **RULE:** Classify each item by kind
    - **SYNOPSIS:** The generator must classify each extracted item as
      functional, non-functional, constraint, or assumption.
    - **CHAIN-OF-THOUGHT:** Later phases do not only need the source text; they
      also need to know what role that text plays in the requirement set.
    - **BECAUSE:** Without explicit categorization, downstream phases would
      have to reinterpret the raw quotes again instead of building from a
      normalized extraction layer.
  - **RULE:** Produce explicit source-coverage bookkeeping
    - **SYNOPSIS:** The generator must produce a separate coverage support file
      that records `coverage_check` and `coverage_verdict`.
    - **CHAIN-OF-THOUGHT:** The model needs an explicit self-check against the
      raw request so it can look for missing source content after drafting the
      inventory.
    - **BECAUSE:** The separate coverage file is supposed to help the
      generator detect omissions and complete the inventory before the judge
      reviews the real artifact.

- **PROCESS: PROCESS-3** Judge purpose
  - **SYNOPSIS:** The judge prompt must decide whether the current inventory is
    phase-ready as an extraction artifact.
  - **BECAUSE:** The judge is not reviewing prose quality; it is checking
    whether the inventory faithfully and adequately represents the request.

- **RULE: RULE-4** The prompt pair must align on one extraction contract
  - **SYNOPSIS:** The generator and judge must share one clear definition of:
    - what counts as requirement-bearing content
    - when content must be split into multiple RI items
    - what each category means
    - what the coverage structures must prove
  - **BECAUSE:** PH-000 will not converge if the generator and judge are
    working from different hidden contracts.

## 4. Why The Inventory Exists

- **ENTITY: ENTITY-1** Requirements inventory
  - **SYNOPSIS:** The requirements inventory is the structured extraction
    product of PH-000.
  - **BECAUSE:** Later phases need a disciplined, inspectable map of what the
    raw request contains.

  - **FIELD:** `items`
    - **SYNOPSIS:** The `items` list is the inventory proper.
    - **BECAUSE:** Each `RI-*` item is one reviewable unit of extracted source
      meaning.

  - **FIELD:** `category`
    - **SYNOPSIS:** `category` tells later phases whether the source statement
      is functional, non-functional, a constraint, or an assumption.
    - **BECAUSE:** Downstream planning and design need these distinctions, and
      PH-000 is the first place they become explicit.

  - **FIELD:** `verbatim_quote`
    - **SYNOPSIS:** `verbatim_quote` preserves the exact source wording for the
      inventory item.
    - **BECAUSE:** Exact quote preservation is what keeps the inventory tied to
      the real request rather than to model paraphrase.

  - **FIELD:** `normalized_requirement`
    - **SYNOPSIS:** `normalized_requirement` restates the same requirement
      meaning as a coherent standalone software requirement.
    - **BECAUSE:** Later phases need a downstream-ready requirement statement,
      not only a raw quoted fragment.

  - **FIELD:** `rationale`
    - **SYNOPSIS:** `rationale` records why the extraction boundary was drawn
      that way.
    - **BECAUSE:** Splitting and categorization decisions need to be reviewable
      rather than left implicit.

## 5. Why The Coverage Information Exists

- **ENTITY: ENTITY-2** `coverage_check`
  - **SYNOPSIS:** `coverage_check` is an explicit mapping from requirement-
    bearing source phrases to the `RI-*` items that represent them.
  - **BECAUSE:** The inventory alone does not prove that every important part
    of the source was covered.

  - **RULE:** Keep coverage out of the inventory artifact
    - **SYNOPSIS:** `coverage_check` should live in a separate PH-000 coverage
      support file rather than inside `requirements-inventory.yaml`.
    - **BECAUSE:** The inventory is the real downstream artifact, while the
      coverage bookkeeping exists to help the generator review completeness.

  - **FIELD:** phrase key
    - **SYNOPSIS:** Each key identifies one source phrase or source-level
      requirement-bearing unit that PH-000 says it covered.
    - **BECAUSE:** Coverage must be expressed in terms of the source, not only
      in terms of the generated inventory.

  - **FIELD:** `["RI-NNN", "..."]`
    - **SYNOPSIS:** The value lists which inventory items cover that source
      phrase.
    - **BECAUSE:** One source phrase may map to one or more RI items, and one
      RI item may cover more than one source phrase when exact splitting is not
      possible without paraphrase.

  - **FIELD:** `status`
    - **SYNOPSIS:** `status` gives a compact human-readable summary of the
      coverage state.
    - **BECAUSE:** Reviewers need a quick coverage snapshot in addition to the
      detailed phrase map.

- **ENTITY: ENTITY-3** `coverage_verdict`
  - **SYNOPSIS:** `coverage_verdict` is the numeric summary of source coverage.
  - **BECAUSE:** Deterministic validation and later inspection need explicit
    counts, not only a free-form status string.

  - **FIELD:** `total_upstream_phrases`
    - **SYNOPSIS:** Count of source phrases that PH-000 expected to cover.
    - **BECAUSE:** Coverage must be measured against an explicit universe.

  - **FIELD:** `covered`
    - **SYNOPSIS:** Count of source phrases that were mapped to at least one
      valid RI item.
    - **BECAUSE:** The phase needs an explicit completeness measure.

  - **FIELD:** `orphaned`
    - **SYNOPSIS:** Count of source phrases that were not mapped to any valid
      RI item.
    - **BECAUSE:** Orphans are the direct signal for omission.

  - **FIELD:** `verdict`
    - **SYNOPSIS:** High-level pass/fail status of the coverage accounting.
    - **BECAUSE:** The coverage bookkeeping itself needs a single visible
      outcome.

- **RULE: RULE-5** Coverage structures exist to catch omissions and invention
  - **SYNOPSIS:** The purpose of `coverage_check` and `coverage_verdict` is to
    surface:
    - missing source content
    - unsupported coverage claims
    - invented phrases that do not exist in the source
  - **BECAUSE:** These are the main extraction failures PH-000 is supposed to
    make visible before downstream phases begin.

- **RULE: RULE-6** Coverage is primarily a generator self-check
  - **SYNOPSIS:** The separate coverage file should help the generator ask
    "what from the source is still missing from the inventory?"
  - **BECAUSE:** LLM extraction has a blind spot for silent omissions, and the
    coverage file is meant to expose that gap before judge review.

- **RULE: RULE-7** Coverage is not a downstream traceability substitute
  - **SYNOPSIS:** PH-000 coverage structures prove source-to-inventory
    completeness; they are not the same as later phase-to-phase traceability.
  - **BECAUSE:** Their purpose is narrower: they answer "did we capture the raw
    request?" rather than "did later designs implement the inventory?"

## 6. Generator Execution Contract

- **PROCESS: PROCESS-4** Generator iteration 1
  - **SYNOPSIS:** On the first iteration, the generator must produce the first
    complete candidate inventory from the raw request.
  - **READS:** `docs/requirements/raw-requirements.md`
    - **BECAUSE:** The source request is the only authoritative upstream input
      for PH-000.
  - **WRITES:** `docs/requirements/requirements-inventory.yaml`
    - **BECAUSE:** The phase output is a file artifact, not only a text reply.

- **PROCESS: PROCESS-5** Generator iteration N+1
  - **SYNOPSIS:** On a revise iteration, the generator must update the same
    inventory artifact using the current artifact state plus the judge's
    required changes.
  - **READS:** current inventory artifact
    - **BECAUSE:** Revision must build on the actual artifact, not regenerate
      blindly.
  - **READS:** judge required changes
    - **BECAUSE:** The purpose of the revise loop is to apply concrete judge
      feedback.
  - **WRITES:** the same inventory artifact path
    - **BECAUSE:** PH-000 converges by revising one canonical artifact.

- **RULE: RULE-7** The generator must prove coverage, not just emit items
  - **SYNOPSIS:** After writing the inventory and the coverage file, the
    generator must review the coverage and fill any detected gaps before
    finishing the iteration.
  - **BECAUSE:** The point of the coverage file is to help the generator catch
    missing requirement-bearing content before handing the inventory to the judge.

## 7. Judge Execution Contract

- **PROCESS: PROCESS-6** Judge review
  - **SYNOPSIS:** The judge must review the inventory as an extraction
    artifact, not as a polished specification.
  - **BECAUSE:** PH-000 is about faithfulness and completeness, not style.

- **RULE: RULE-8** The judge must focus on the real inventory artifact
  - **SYNOPSIS:** The judge should review `requirements-inventory.yaml` rather
    than the separate coverage support file.
  - **BECAUSE:** The inventory is the true PH-000 artifact that later phases
    consume, while the coverage file is only a generator support mechanism.

- **RULE: RULE-9** The judge must focus on four PH-000 defects
  - **SYNOPSIS:** The judge should focus on:
    - missing requirement-bearing content
    - meaning drift from the source
    - invented or unsupported content
    - materially wrong extraction boundaries or categories
  - **BECAUSE:** Those are the defects that make an extraction inventory unfit
    for downstream use.

- **RULE: RULE-10** The judge must state concrete missing or wrong elements
  - **SYNOPSIS:** On `revise`, the judge must itemize the important source
    elements that are still missing or wrongly represented.
  - **BECAUSE:** The generator needs concrete correction targets in order to
    converge.

- **RULE: RULE-11** The judge must not rely on coverage bookkeeping to avoid inventory review
  - **SYNOPSIS:** The judge should not treat the separate coverage file as a
    substitute for reading and validating the real inventory content.
  - **BECAUSE:** A plausible-looking coverage file can still coexist with a
    weak or incomplete inventory.

## 8. Convergence Contract

- **RULE: RULE-12** Revise means "correct this same artifact"
  - **SYNOPSIS:** A `revise` verdict means the next generator iteration must
    modify the same inventory artifact, not restart from scratch.
  - **BECAUSE:** The phase should converge by correction and evidence
    accumulation.

- **RULE: RULE-13** Escalate means "stop with the latest evidence intact"
  - **SYNOPSIS:** If the iteration budget is exhausted, the latest artifact,
    prompt inputs, prompt outputs, and judge outputs must remain available.
  - **BECAUSE:** Non-convergence diagnosis depends on the real last state.

- **RULE: RULE-14** Non-convergence at this stage means the extraction contract is still weak
  - **SYNOPSIS:** If PH-000 reaches `revise` twice and escalates, the likely
    problem is not the existence of the revise loop but weakness or mismatch in
    the generator and judge extraction contract.
  - **BECAUSE:** The runtime can already execute the loop; the remaining gap is
    whether the prompt pair agrees on what a good PH-000 artifact is.

## 9. Definition Of Good

- **RULE: RULE-15** A good PH-000 artifact proves source-grounded completeness
  - **SYNOPSIS:** PH-000 is good only when:
    - the inventory file exists
    - each RI item is source-faithful
    - category and boundary choices are reviewable
    - the separate coverage support file shows that the raw request was fully represented
    - both deterministic validation and the judge pass
  - **BECAUSE:** The whole point of PH-000 is to create a trustworthy
    extraction layer for the rest of the methodology.
