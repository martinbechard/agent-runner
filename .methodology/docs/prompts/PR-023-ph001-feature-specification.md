### Module

feature-specification

## Prompt 1: Produce Feature Specification

### Required Files

docs/requirements/raw-requirements.md
docs/requirements/requirements-inventory.yaml

### Include Files

docs/requirements/raw-requirements.md
docs/requirements/requirements-inventory.yaml

### Checks Files

docs/features/feature-specification.yaml

### Deterministic Validation

.methodology/src/cli/methodology_runner/phase_1_validation.py
--feature-spec
docs/features/feature-specification.yaml
--requirements-inventory
docs/requirements/requirements-inventory.yaml

### Generation Prompt

As a software product analyst, you must group the requirements inventory into
coherent features and write the feature specification to
docs/features/feature-specification.yaml.

The requirements inventory is provided above in <REQUIREMENTS_INVENTORY>.
The original request is provided above in <RAW_REQUIREMENTS>.

Module-local generator context:
Embedded directives for this step:

- Walk the inventory in ID order and group `RI-*` items by shared domain
  entity, actor, and end-to-end user flow.
- Keep constraints and non-functional items attached to the feature they
  constrain unless they clearly cut across multiple features.
- Keep feature size bounded. If a feature would need too many independent
  acceptance criteria, split it along the clearest domain or workflow
  boundary.
- Write feature-level completion criteria, not implementation test scripts.
- Declare dependencies only when one feature consumes output, state, or
  interfaces produced by another.
- Any `RI-*` item not represented in a feature must go to `out_of_scope`
  with a concrete reason.
- If an `RI-*` item is qualitative and you cannot state a binary feature-level
  completion condition without inventing a new metric or review standard, put
  it in `out_of_scope` instead of turning it into a vague `AC-*`.
- Do not add implementation-shaped detail that the cited `RI-*` items do not
  require. For example, do not invent path-oriented, filename-oriented, or
  wrapper-command obligations when the source only requires that a human can
  run the app or test suite and observe the expected result.
- For this hello-world class of requirement, phrases such as `intentionally
  minimal`, `simple file layout`, `easy to understand`, and `short` remain
  qualitative unless the source gives a concrete threshold. Do not convert
  them into vague acceptance criteria.

Phase purpose:
- Group related RI-* items into coherent FT-* features.
- Write concrete AC-* acceptance criteria for each feature.
- Declare inter-feature dependencies when one feature relies on another.
- Put any intentionally excluded RI-* items in out_of_scope with a reason.
- Surface cross-cutting concerns that affect multiple features.
- Introduce the minimum supporting detail needed to make the feature
  specification usable by later phases, as long as that detail remains
  non-contradictory and directly or indirectly supports the requirements
  inventory.

Important interpretation:
- In this phase, acceptance criteria are definition-of-done style completion
  criteria for a feature specification.
- They are not executable test cases, shell scripts, or implementation-level
  test procedures unless the source requirements explicitly require that level
  of detail.
- They must be reviewable and materially checkable, but they do not need to
  prescribe literal commands, exact filenames, or concrete implementation form
  unless the source inventory requires those specifics.

Output schema to satisfy:
features:
  - id: "FT-NNN"
    name: "Descriptive feature name"
    description: "What this feature does and why"
    source_inventory_refs: ["RI-NNN", "..."]
    acceptance_criteria:
      - id: "AC-NNN-NN"
        description: "Concrete, testable acceptance criterion"
    dependencies: ["FT-NNN", "..."]
out_of_scope:
  - inventory_ref: "RI-NNN"
    reason: "Why this requirement is deferred or excluded"
cross_cutting_concerns:
  - id: "CC-NNN"
    name: "Concern name"
    description: "How this concern cuts across features"
    affected_features: ["FT-NNN", "..."]

Acceptance requirements:
- The file must be valid YAML parseable by a standard YAML parser.
- The top-level keys must appear exactly in this order:
  features
  out_of_scope
  cross_cutting_concerns
- Every feature must contain:
  id
  name
  description
  source_inventory_refs
  acceptance_criteria
  dependencies
- Every RI-* item from docs/requirements/requirements-inventory.yaml must appear
  in at least one feature's source_inventory_refs list or in out_of_scope with a reason.
- You may introduce supporting specification detail that is not stated verbatim
  in a single `RI-*` item if it is a reasonable, non-contradictory elaboration
  that directly or indirectly supports satisfying the cited requirements.
- Supporting detail may refine how a requirement will be validated or grouped,
  but it must not contradict the source inventory, weaken exact source
  constraints, or add unrelated product scope.
- Acceptance criteria must be binary and testable. Avoid vague language like
  fast, user-friendly, intuitive, appropriate, reasonable, or similar words
  without measurable conditions.
- Interpret `binary and testable` at the feature-specification level:
  the criterion must support a clear pass/fail review of whether the feature is
  done, but it does not need to be written as an executable test case.
- Preserve exact source meaning. If an RI states an exact count or bounded
  quantity such as `one`, the feature specification must preserve that exact
  bound and must not weaken it to `at least one`, `one or more`, or any other
  broader requirement.
- Do not strengthen observable behavior beyond the cited `RI-*` text. If the
  source says an application prints a value to standard output, do not add
  byte-level or formatting constraints such as a required trailing newline
  unless the cited inventory text explicitly says so.
- Do not add implementation-form assumptions unless the cited `RI-*` text
  explicitly requires them. Do not assume file extensions, wrapper-command
  prohibitions, non-interactive execution, or any other concrete runtime
  constraint that is not stated in the source inventory.
- Preserve the source unit of obligation. If an `RI-*` item says `test`,
  `README`, `application`, or another specific deliverable term, do not
  silently reinterpret it as a narrower or different unit such as `test case`
  unless the cited source text uses that exact term.
- When a source requirement names an artifact type but not a single exact
  filename, write the acceptance criterion in terms of the artifact's presence
  and role rather than a closed filename allowlist.
- Do not add documentation, runtime, tooling, dependency, or behavioral
  obligations unless they are at least indirectly supported by cited `RI-*`
  items and help operationalize those requirements without contradiction.
- If an `RI-*` item is too qualitative or underspecified to express as an
  objective pass/fail acceptance criterion without inventing a new standard,
  place it in out_of_scope with a concrete reason instead of writing a pseudo-
  objective criterion.
- Do not restate `a human can run ...` as a requirement for a separate path,
  entrypoint path, or path artifact unless the cited inventory text explicitly
  requires one.
- Dependencies must refer only to real FT-* feature IDs and must not self-reference.
- Each cross-cutting concern must affect at least two features.
- Do not invent functionality that is not traceable to the requirements inventory.
- Do not create any files other than docs/features/feature-specification.yaml.
- Write the full file contents to docs/features/feature-specification.yaml.

### Validation Prompt

Review the current feature specification against <REQUIREMENTS_INVENTORY> and
<RAW_REQUIREMENTS>.
The current artifact is provided above in <FEATURE_SPECIFICATION>.

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Module-local judge context:
Embedded directives for this step:

- Review in three passes:
  1. coverage: every `RI-*` is in a feature or `out_of_scope`
  2. scope: every feature and `AC-*` stays supported by cited `RI-*`
  3. intra-feature quality: clear `AC-*`, real dependencies, no conflicts
- Treat orphaned inventory items, vague `AC-*`, unsupported scope, dependency
  defects, and exact-meaning drift as blocking.
- Preserve exact boundaries from upstream requirements. Do not allow a feature
  or `AC-*` to weaken `one`, `at most`, `within`, or similar exact limits.

Your job is to decide whether the generated feature specification is phase-ready.

Review method:
- Iterate through features in FT-* order.
- For each feature, review its description, source_inventory_refs,
  acceptance_criteria, and dependencies together.
- Then review out_of_scope entries in RI-* order.
- Then review cross_cutting_concerns in CC-* order.
- Before flagging any requirement, scope statement, or concern as missing,
  check whether that same actionable meaning is already covered elsewhere in
  another feature, acceptance criterion, out_of_scope entry, or cross-cutting
  concern.
- Only flag it as missing if the allegedly missing text contributes distinct
  downstream-actionable behavior, constraint, dependency, or rationale that is
  not already represented.

Focus your semantic review on these failure modes:

1. Vague acceptance criteria:
   - Flag any AC that uses subjective language without a measurable threshold
     or a sufficiently clear completion condition.
2. Orphaned inventory items:
   - Verify every RI-* from the phase-0 inventory appears in a feature's
     source_inventory_refs or in out_of_scope with a reason.
3. Assumption conflicts:
   - Check that no two features make contradictory assumptions about shared
     state, data formats, or execution order.
4. Scope creep:
   - Flag any feature that introduces functionality not traceable to any
     RI-* item in the inventory.
5. Missing dependencies:
   - If feature A reads data or relies on behavior produced by feature B,
     then feature B must appear in feature A's dependencies.
6. Exact-meaning drift:
   - Flag any feature or AC that weakens or broadens an exact source
     requirement such as changing `one` into `at least one`.
7. Unsupported restatement:
   - Flag any AC or feature description that adds detail which is neither
     directly nor indirectly supported by its cited `RI-*` items, or which
     stops serving the cited requirements.
8. Pseudo-objective constraints:
   - Flag any AC that pretends to make a qualitative constraint objective
     without a source-grounded inspection rule or measurable threshold.
9. Contradictory invention:
   - Flag any invented supporting detail that contradicts the source
     inventory, weakens an exact source constraint, or introduces unrelated
     product scope.

Review instructions:
- Use the deterministic validation report as authoritative for structural checks,
  RI coverage counts, dependency target existence, and cross-cutting-concern
  cardinality.
- Compare the feature specification against both the requirements inventory and
  the raw requirements when judging semantic fidelity.
- Only ask for a change when the current specification is wrong, contradictory,
  materially unsupported, or when the proposed change would make a meaningful
  difference to downstream architecture or implementation decisions.
- Treat the feature specification as an allowed elaboration layer, not as a
  verbatim restatement layer. The generator is allowed to invent supporting
  detail when that detail is non-contradictory and directly or indirectly
  supports the cited requirements.
- Treat `acceptance_criteria` here as feature-level completion criteria, not
  as executable test cases. Do not require implementation-level test steps,
  literal shell commands, or test harness details unless the cited source
  requirements explicitly require them.
- Do not require a literal shell command, exact filename, or implementation
  form unless the cited source requirements explicitly require one. A command-
  line capability criterion may refer to the project's application or test
  command as long as the pass/fail condition is still observable.
- Do not reject a README existence criterion merely because it validates the
  presence of a README artifact without enumerating every permissible filename.
- Do not reinterpret `test` as necessarily narrower terms like `test case`
  when judging semantic fidelity; preserve the source unit of obligation.
- When a qualitative upstream item like `intentionally minimal`, `short`, or
  `easy to understand` cannot support a binary feature-level criterion without
  a new invented rubric, prefer `out_of_scope` with a concrete reason over a
  vague `AC-*`.
- Do not require or accept path-oriented, filename-oriented, or wrapper-
  command detail unless the cited upstream requirements explicitly require it.
- Do not reject supporting elaboration merely because it is not stated
  verbatim in one `RI-*` item. Reject it only if it contradicts the source,
  weakens exact source meaning, adds unrelated scope, or no longer serves the
  cited requirements.
- When judging whether an AC is specific enough, ask whether a reviewer could
  determine done/not-done from the described completion condition. Do not ask
  whether the AC already contains a fully authored test case.
- Do not request wording polish, local precision improvements, or alternative
  formulations unless the current wording is actually wrong or the difference
  would materially change downstream design or implementation choices.
- If you find issues, cite the exact FT-* / AC-* / RI-* IDs involved.
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary
- Use VERDICT: pass only if the artifact is phase-ready with no material omissions,
  unsupported scope, or acceptance-criteria quality defects.
- Use VERDICT: revise if the artifact can be corrected within this same file.
- Use VERDICT: escalate only if the source requirements or inventory are too
  ambiguous or contradictory to produce a stable feature specification without
  external clarification.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
