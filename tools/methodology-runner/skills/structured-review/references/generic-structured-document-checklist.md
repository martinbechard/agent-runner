# Generic Structured Document Checklist

Use this checklist for any structured design, plan, architecture,
workflow, or rules document review.

Complete each check with:

- `STATUS: pass | fail | question | n/a`
- `EVIDENCE:`
- `NOTE:` only when needed

## A. Review Trace

- **CHECK: TRACE-1** Review target is identified.
  - **EXPECTATION:** The checklist names the exact target file or
    artifact under review.

- **CHECK: TRACE-2** Review inputs are identified.
  - **EXPECTATION:** The checklist names the structured inputs or
    directives the target is supposed to reflect.

- **CHECK: TRACE-3** Checklist set is identified.
  - **EXPECTATION:** The checklist states that the generic checklist was
    used and lists any supplementary checklist.

## B. Input Coverage

- **CHECK: INPUT-1** All material input directives are traced.
  - **EXPECTATION:** The checklist records where each important input
    directive was applied or that it was not applied.

- **CHECK: INPUT-2** No material input directive is silently omitted.
  - **EXPECTATION:** Missing directive applications are marked as
    failures or open questions, not ignored.

- **CHECK: INPUT-3** No directive is contradicted by the target.
  - **EXPECTATION:** The target does not directly conflict with a stated
    input directive.

## C. Internal Logic

- **CHECK: LOGIC-1** Concepts are introduced before they are used.
  - **EXPECTATION:** The document does not rely on undefined or
    misordered design-specific concepts.

- **CHECK: LOGIC-2** The document follows a logical dependency order.
  - **EXPECTATION:** Later sections reason from already-established
    concepts, artifacts, or processes.

- **CHECK: LOGIC-3** The document does not contain material contradictions.
  - **EXPECTATION:** Different sections do not assert incompatible
    claims about the same thing.

- **CHECK: LOGIC-4** Requirements are not confused with solution choices.
  - **EXPECTATION:** Requirements state what is needed; design items
    state how the design responds.

- **CHECK: LOGIC-5** Goals are not confused with features.
  - **EXPECTATION:** Core goals and supporting usability or robustness
    features are distinguished where relevant.

## D. Justification Quality

- **CHECK: JUST-1** Important assertions have `BECAUSE` clauses.
  - **EXPECTATION:** Important requirements, dependencies, containment
    lines, and gaps are justified.

- **CHECK: JUST-2** Each `BECAUSE` justifies its immediate parent.
  - **EXPECTATION:** The reason is attached to the correct assertion and
    does not actually belong to a sibling or ancestor line.

- **CHECK: JUST-3** Each `CHAIN-OF-THOUGHT` justifies the `BECAUSE` below it.
  - **EXPECTATION:** The `CHAIN-OF-THOUGHT` is a reasoning bridge, not a
    second synopsis.

- **CHECK: JUST-4** Unsupported requirements or claims are flagged.
  - **EXPECTATION:** Assertions that are not justified by the inputs are
    marked as failures or questions.

## E. Terminology And Structure

- **CHECK: TERM-1** Established domain vocabulary is used where available.
  - **EXPECTATION:** The document uses standard terms such as
    `worktree` when that is the correct domain term.

- **CHECK: TERM-2** Repeated terms are stable and unambiguous.
  - **EXPECTATION:** The same concept is not renamed repeatedly without
    explanation.

- **CHECK: TERM-3** Root-level IDs are present when structured review matters.
  - **EXPECTATION:** Root review objects have stable embedded IDs when
    the document is being reviewed or cross-referenced.

- **CHECK: TERM-4** IDs are not overused on nested lines.
  - **EXPECTATION:** IDs are limited to root-level review objects rather
    than every nested property.

## F. Document Hygiene

- **CHECK: HYGIENE-1** Section purpose lines are present.
  - **EXPECTATION:** Each section begins with a short sentence
    explaining why it exists.

- **CHECK: HYGIENE-2** Retired or superseded material is not mixed into active design without explanation.
  - **EXPECTATION:** Stale references are isolated, retired, or clearly
    marked.

- **CHECK: HYGIENE-3** Modifications are separated from clarifications.
  - **EXPECTATION:** Real design changes are listed as modifications,
    while wording cleanups stay out of that section.

- **CHECK: HYGIENE-4** The document stays within its intended scope.
  - **EXPECTATION:** The artifact does not drift into unrelated concerns
    that belong in another design or plan.
