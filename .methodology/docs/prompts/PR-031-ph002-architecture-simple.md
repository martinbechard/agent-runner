## Prompt 1: PH-002 Architecture Variants [VARIANTS]

### Variant A: Current YAML prompt

#### Module

architecture

#### Required Files

docs/requirements/raw-requirements.md
docs/requirements/requirements-inventory.yaml
docs/features/feature-specification.yaml

#### Checks Files

docs/architecture/stack-manifest.yaml

#### Deterministic Validation

scripts/phase-2-deterministic-validation.py
--stack-manifest
docs/architecture/stack-manifest.yaml
--feature-spec
docs/features/feature-specification.yaml
--requirements-inventory
docs/requirements/requirements-inventory.yaml

#### Generation Prompt

You are producing the phase artifact for PH-002-architecture.

Read:
- docs/features/feature-specification.yaml
- docs/requirements/requirements-inventory.yaml
- docs/requirements/raw-requirements.md

Write:
- docs/architecture/stack-manifest.yaml

Task:
Produce the final acceptance-ready YAML architecture artifact in one file.
Use this prompt pair's built-in revise loop to correct any issues the judge
finds. Do not create draft-only or partial versions on purpose.

Module-local generator context:
- Use `structured-design` to shape the reasoning and output discipline for the
  architecture work, even though the final artifact is YAML rather than
  markdown.
- Use `traceability-discipline` to keep the architecture grounded in the
  feature specification and upstream requirements.
- Keep the decomposition as small as the features allow. Do not add extra
  components, services, frameworks, or persistence layers without a real
  boundary need.
- A single-component architecture is correct when one coherent component can
  serve the full feature set.
- Preserve explicit source constraints first. When technology is not fixed by
  the source, choose by workload fit, team fit, simplicity, and consistency.
- Every component must own a coherent responsibility boundary and serve one or
  more real features.
- Add integration points only for real cross-component boundaries.
- If there is one component or no real cross-component boundary, use
  `integration_points: []`.
- Keep `expected_expertise` human-readable and reusable. Do not write skill
  IDs, slugs, or tool names.

Phase purpose:
- Decompose the feature specification into coherent deployable or designable
  technology components.
- Declare the technology, runtime, frameworks, persistence model, and expected
  expertise for each component.
- Identify integration points only where real cross-component boundaries exist.
- Explain the decomposition choices in a rationale that downstream phases can use.

Important interpretation:
- This phase is an architecture elaboration layer, not a verbatim restatement
  layer. You may introduce supporting decomposition detail, technology choices,
  runtime choices, framework choices, persistence choices, expertise
  descriptions, and integration boundaries when they are reasonable,
  non-contradictory, and directly or indirectly support the feature
  specification and requirements inventory.
- Do not multiply components, frameworks, persistence layers, or integration
  points unless they materially help the architecture. A simple example may
  legitimately result in a single-component architecture with no integration
  points.
- `expected_expertise` entries must be human-readable descriptions of knowledge
  areas. They are not skill IDs, catalog slugs, filenames, or plugin names.

Output schema to satisfy:
components:
  - id: "CMP-NNN-<slug>"
    name: "Descriptive component name"
    role: "One-sentence role summary"
    technology: "python"
    runtime: "python3"
    frameworks: ["framework-name", "..."]
    persistence: "none"
    expected_expertise:
      - "Human-readable expertise description"
    features_served: ["FT-NNN", "..."]
integration_points:
  - id: "IP-NNN"
    between: ["CMP-NNN-a", "CMP-NNN-b"]
    protocol: "HTTP/JSON"
    contract_source: "docs/design/interface-contracts.yaml"
rationale: |
  Prose explanation of the decomposition choices.

Acceptance requirements:
- The file must be valid YAML parseable by a standard YAML parser.
- The top-level keys must appear exactly in this order:
  components
  integration_points
  rationale
- Every component must contain:
  id
  name
  role
  technology
  runtime
  frameworks
  persistence
  expected_expertise
  features_served
- Every FT-* feature from docs/features/feature-specification.yaml must appear
  in at least one component's features_served list.
- Every component must have a non-empty expected_expertise list.
- expected_expertise entries must be natural-language descriptions, not
  catalog-like slugs or skill IDs.
- Integration points are required only for real cross-component boundaries.
  If the architecture has one component or no cross-component boundaries,
  integration_points may be an empty list.
- Every integration point must reference exactly two distinct real component IDs.
- Technology, runtime, frameworks, and persistence choices may be invented when
  they are coherent with the served features and do not contradict exact source
  constraints.
- Do not introduce unnecessary frameworks, services, databases, or component
  boundaries that are not justified by the served features or explicit source
  constraints.
- Do not invent components that serve no features.
- The rationale must explain why the decomposition was chosen. Do not merely
  restate the component names.
- Do not create any files other than docs/architecture/stack-manifest.yaml.
- Use the Write tool to write the full file contents to docs/architecture/stack-manifest.yaml.

#### Validation Prompt

Read:
- docs/requirements/raw-requirements.md
- docs/requirements/requirements-inventory.yaml
- docs/features/feature-specification.yaml
- docs/architecture/stack-manifest.yaml

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Module-local judge context:
- Use `structured-review` to review the architecture against the phase
  directives and acceptance rules before deciding the verdict.
- Use `traceability-discipline` to keep the review grounded in the feature
  specification and upstream requirements.
- Review for feature coverage gaps, bad or unnecessary decomposition,
  unsupported technology invention, constraint drift, weak expertise
  articulation, and fake or missing integration boundaries.
- Reject decomposition that adds complexity without improving downstream
  design clarity.

Your job is to decide whether the generated architecture is phase-ready.
Focus your semantic review on these failure modes:

1. Feature coverage gaps:
   - Flag any architecture that materially under-specifies how a feature is
     served, even if the deterministic feature coverage count passes.
2. Unsupported or incoherent decomposition:
   - Flag component boundaries that do not make architectural sense for the
     served features, or that collapse materially different responsibilities in
     a way that would confuse downstream design.
3. Unnecessary decomposition:
   - Flag extra components, frameworks, services, persistence layers, or
     integration points that are not supported by the feature specification and
     would materially complicate downstream implementation.
4. Unsupported technology invention:
   - Flag technology, runtime, framework, or persistence choices that are not
     at least indirectly supported by the features, requirements, or explicit
     constraints.
5. Constraint drift:
   - Flag architecture choices that weaken or contradict exact source
     constraints such as Python 3, the minimal-scope expectation, or the
     prohibition on unnecessary frameworks.
6. Expertise articulation defects:
   - Flag expected_expertise entries that are too vague to guide downstream
     skill selection, too narrow to be reusable knowledge areas, or that look
     like concrete skill IDs or slugs.
7. Integration boundary defects:
   - Flag missing integration points for real cross-component boundaries, or
     integration points that describe fake or unnecessary boundaries.
8. Rationale defects:
   - Flag rationales that do not explain why the architecture was chosen or do
     not justify materially important decomposition decisions.
9. Scope creep:
   - Flag architecture that introduces product scope or infrastructure not
     traceable to the features and requirements.

Review instructions:
- Use the deterministic validation report as authoritative for structural
  checks, feature coverage, duplicate IDs, component existence checks,
  technology/framework coherence heuristics, and non-empty rationale.
- Compare the architecture against both the feature specification and the
  upstream requirements when judging semantic fidelity.
- Treat this phase as an allowed elaboration layer. The generator is allowed to
  invent architecture-supporting detail when it is non-contradictory and
  directly or indirectly supports the cited features and requirements.
- Only ask for a change when the current architecture is wrong, contradictory,
  materially unsupported, or when the proposed change would make a meaningful
  difference to downstream solution design, interface-contract definition, or
  implementation decisions.
- Do not force extra components or integration points simply because more
  decomposition is possible. If a simple architecture is coherent and materially
  sufficient, accept it.
- Do not reject an expected_expertise entry merely because you would phrase it
  differently. Reject it only if it is too vague, too narrow, or looks like a
  concrete skill ID or slug.
- Do not request wording polish, alternative naming, or different but equally
  coherent decomposition unless the current choice is actually wrong or
  materially consequential downstream.
- If you find issues, cite exact CMP-* / IP-* / FT-* / RI-* IDs.
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary
- Use VERDICT: pass only if the artifact is phase-ready with no material
  decomposition, technology-choice, expertise-articulation, or integration
  defects.
- Use VERDICT: revise if the artifact can be corrected within this same file.
- Use VERDICT: escalate only if the feature specification or requirements are
  too ambiguous or contradictory to produce a stable architecture without
  external clarification.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate

### Variant B: Simple YAML prompt

#### Module

architecture

#### Required Files

docs/requirements/raw-requirements.md
docs/requirements/requirements-inventory.yaml
docs/features/feature-specification.yaml

#### Checks Files

docs/architecture/stack-manifest.yaml

#### Deterministic Validation

scripts/phase-2-deterministic-validation.py
--stack-manifest
docs/architecture/stack-manifest.yaml
--feature-spec
docs/features/feature-specification.yaml
--requirements-inventory
docs/requirements/requirements-inventory.yaml

#### Generation Prompt

You are producing the phase artifact for PH-002-architecture.

Read:
- docs/requirements/raw-requirements.md
- docs/requirements/requirements-inventory.yaml
- docs/features/feature-specification.yaml

Write:
- docs/architecture/stack-manifest.yaml

Use `structured-design` and `traceability-discipline`.

Produce the final acceptance-ready YAML architecture artifact in one file.
Do not create notes, drafts, or side files.

This phase is a constrained elaboration phase.
You may choose technology and architecture details that are coherent with the
feature specification and requirements, but do not invent extra scope.

Keep it as small as the feature set allows.
- Use one component if one component cleanly serves the full feature set.
- Do not add frameworks, persistence, services, or integration points unless
  there is a real boundary need.
- If there is no real cross-component boundary, use `integration_points: []`.
- Keep `expected_expertise` human-readable. Do not use skill names, slugs, or
  tool IDs.

Output schema:
components:
  - id: "CMP-NNN-<slug>"
    name: "Descriptive component name"
    role: "One-sentence role summary"
    technology: "python"
    runtime: "python3"
    frameworks: ["framework-name", "..."]
    persistence: "none"
    expected_expertise:
      - "Human-readable expertise description"
    features_served: ["FT-NNN", "..."]
integration_points:
  - id: "IP-NNN"
    between: ["CMP-NNN-a", "CMP-NNN-b"]
    protocol: "HTTP/JSON"
    contract_source: "docs/design/interface-contracts.yaml"
rationale: |
  Prose explanation of the decomposition choices.

Requirements:
- Write valid YAML.
- Use exactly these top-level keys in this order:
  - components
  - integration_points
  - rationale
- Cover every FT-* feature at least once in `features_served`.
- Every component must have a non-empty `expected_expertise` list.
- Do not invent components that serve no features.
- Do not invent unnecessary frameworks, databases, services, or integration
  points.
- Make the rationale explain why the architecture was chosen.
- Write only docs/architecture/stack-manifest.yaml.

#### Validation Prompt

Read:
- docs/requirements/raw-requirements.md
- docs/requirements/requirements-inventory.yaml
- docs/features/feature-specification.yaml
- docs/architecture/stack-manifest.yaml

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not repeat them.

Use `structured-review` and `traceability-discipline`.

Decide whether the architecture is phase-ready.

Focus on material defects only:
- missing feature coverage
- unsupported or unnecessary decomposition
- unsupported technology or persistence choices
- drift from exact source constraints
- fake or missing integration boundaries
- weak `expected_expertise` entries
- rationale that does not justify the decomposition

Review rules:
- Accept a simple architecture if it is coherent and sufficient.
- Do not force extra components or integration points.
- Treat this phase as allowed elaboration, but reject unsupported scope creep.
- Cite exact CMP-* / IP-* / FT-* / RI-* IDs when you ask for changes.
- For each material correction, include:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate

### Variant C: Simple markdown prompt

#### Module

architecture

#### Required Files

docs/requirements/raw-requirements.md
docs/requirements/requirements-inventory.yaml
docs/features/feature-specification.yaml

#### Checks Files

docs/architecture/architecture-design.md

#### Generation Prompt

You are producing an architecture design variant for PH-002-architecture.

Read:
- docs/requirements/raw-requirements.md
- docs/requirements/requirements-inventory.yaml
- docs/features/feature-specification.yaml

Write:
- docs/architecture/architecture-design.md

Use the `structured-design` skill and `traceability-discipline`.

Produce one final markdown architecture document.
Do not write YAML for this variant.
Do not create notes, drafts, or side files.

This phase is a constrained elaboration phase.
You may choose technology and architecture details that are coherent with the
feature specification and requirements, but do not invent extra scope.

Keep it as small as the feature set allows.
- Use one component if one component cleanly serves the full feature set.
- Do not add frameworks, persistence, services, or integration points unless
  there is a real boundary need.
- If there is no real cross-component boundary, the document should make that
  explicit.
- Keep expertise descriptions human-readable. Do not use skill names, slugs,
  or tool IDs.
- Let the `structured-design` skill define the markdown structure and item
  model for this artifact. Do not fall back to an ordinary prose outline.
- Follow the `structured-design` skill's architecture-doc guidance.
- Start the artifact with one short structured section that summarizes how you
  are applying the `structured-design` skill to this architecture artifact.

Requirements:
- Cover every FT-* feature at least once.
- Do not invent components that serve no features.
- Do not invent unnecessary frameworks, databases, services, or integration
  points.
- Keep the architecture at architecture level. Do not drift into low-level
  implementation detail.
- Make the rationale explain why the architecture was chosen.
- Write only docs/architecture/architecture-design.md.

#### Validation Prompt

Read:
- docs/requirements/raw-requirements.md
- docs/requirements/requirements-inventory.yaml
- docs/features/feature-specification.yaml
- docs/architecture/architecture-design.md

Use the `structured-review` skill and `traceability-discipline`.

Decide whether the markdown architecture is phase-ready for this variant.

Focus on material defects only:
- missing feature coverage
- unsupported or unnecessary decomposition
- unsupported technology or persistence choices
- drift from exact source constraints
- fake or missing integration boundaries
- weak expertise descriptions
- rationale that does not justify the decomposition
- structure that does not clearly express the architecture

Review rules:
- Accept a simple architecture if it is coherent and sufficient.
- Do not force extra components or integration points.
- Treat this phase as allowed elaboration, but reject unsupported scope creep.
- Cite exact component, FT-*, and RI-* references when you ask for changes.
- Check that the artifact actually follows the `structured-design` skill rather
  than just using ordinary markdown headings.
- Check that the artifact follows the skill's architecture-doc guidance.
- Check that the artifact starts with a short structured summary of how the
  `structured-design` skill is being applied.
- For each material correction, include:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate

### Variant D: Simple YAML structured architecture prompt

#### Module

architecture

#### Required Files

docs/requirements/raw-requirements.md
docs/requirements/requirements-inventory.yaml
docs/features/feature-specification.yaml

#### Checks Files

docs/architecture/architecture-design.yaml

#### Generation Prompt

You are producing an architecture design variant for PH-002-architecture.

Read:
- docs/requirements/raw-requirements.md
- docs/requirements/requirements-inventory.yaml
- docs/features/feature-specification.yaml

Write:
- docs/architecture/architecture-design.yaml

Use the `structured-design` skill and `traceability-discipline`.

Produce one final YAML architecture document.
Do not write markdown for this variant.
Do not create notes, drafts, or side files.

This phase is a constrained elaboration phase.
You may choose technology and architecture details that are coherent with the
feature specification and requirements, but do not invent extra scope.

Keep it as small as the feature set allows.
- Use one component if one component cleanly serves the full feature set.
- Do not add frameworks, persistence, services, or integration points unless
  there is a real boundary need.
- If there is no real cross-component boundary, the document should make that
  explicit.
- Keep expertise descriptions human-readable. Do not use skill names, slugs,
  or tool IDs.
- Let the `structured-design` skill define the YAML structure and item model
  for this artifact.
- Follow the `structured-design` skill's YAML companion guidance and preserve
  the real architecture section structure.
- Start the artifact with one short structured section that summarizes how you
  are applying the `structured-design` skill to this architecture artifact.

Requirements:
- Cover every FT-* feature at least once.
- Do not invent components that serve no features.
- Do not invent unnecessary frameworks, databases, services, or integration
  points.
- Keep the architecture at architecture level. Do not drift into low-level
  implementation detail.
- Make the rationale for the architecture clear in the structured content.
- Write only docs/architecture/architecture-design.yaml.

#### Validation Prompt

Read:
- docs/requirements/raw-requirements.md
- docs/requirements/requirements-inventory.yaml
- docs/features/feature-specification.yaml
- docs/architecture/architecture-design.yaml

Use the `structured-review` skill and `traceability-discipline`.

Decide whether the architecture is phase-ready for this variant.

Focus on material defects only:
- missing feature coverage
- unsupported or unnecessary decomposition
- unsupported technology or persistence choices
- drift from exact source constraints
- fake or missing integration boundaries
- weak expertise descriptions
- structure that does not clearly express the architecture
- YAML that distorts the structured-design architecture shape

Review rules:
- Accept a simple architecture if it is coherent and sufficient.
- Do not force extra components or integration points.
- Treat this phase as allowed elaboration, but reject unsupported scope creep.
- Cite exact component, FT-*, and RI-* references when you ask for changes.
- Check that the artifact actually follows the `structured-design` skill rather
  than just flattening everything into generic YAML.
- Check that the artifact follows the skill's architecture-doc guidance.
- Check that the artifact starts with a short structured summary of how the
  `structured-design` skill is being applied.
- Check that the YAML preserves the real architecture section structure rather
  than converting section names into item names or generic `type` entries.
- For each material correction, include:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate

### Variant E: Minimal YAML wording prompt

#### Module

architecture

#### Required Files

docs/requirements/raw-requirements.md
docs/requirements/requirements-inventory.yaml
docs/features/feature-specification.yaml

#### Checks Files

docs/architecture/architecture-design.yaml

#### Generation Prompt

You are producing an architecture design variant for PH-002-architecture.

Read:
- docs/requirements/raw-requirements.md
- docs/requirements/requirements-inventory.yaml
- docs/features/feature-specification.yaml

Write:
- docs/architecture/architecture-design.yaml

Use the `structured-design` skill and `traceability-discipline`.

Produce one final YAML architecture document.
Do not create notes, drafts, or side files.

This phase is a constrained elaboration phase.
You may choose technology and architecture details that are coherent with the
feature specification and requirements, but do not invent extra scope.

Keep it as small as the feature set allows.
- Use one component if one component cleanly serves the full feature set.
- Do not add frameworks, persistence, services, or integration points unless
  there is a real boundary need.
- If there is no real cross-component boundary, the document should make that
  explicit.
- Keep expertise descriptions human-readable. Do not use skill names, slugs,
  or tool IDs.
- Let the `structured-design` skill define the structure and item model for
  this artifact.
- Follow the `structured-design` skill's companion guidance and preserve the
  real architecture section structure.
- Start the artifact with one short structured section that summarizes how you
  are applying the `structured-design` skill to this architecture artifact.

Requirements:
- Cover every FT-* feature at least once.
- Do not invent components that serve no features.
- Do not invent unnecessary frameworks, databases, services, or integration
  points.
- Keep the architecture at architecture level. Do not drift into low-level
  implementation detail.
- Make the rationale for the architecture clear in the structured content.
- Write only docs/architecture/architecture-design.yaml.

#### Validation Prompt

Read:
- docs/requirements/raw-requirements.md
- docs/requirements/requirements-inventory.yaml
- docs/features/feature-specification.yaml
- docs/architecture/architecture-design.yaml

Use the `structured-review` skill and `traceability-discipline`.

Decide whether the YAML architecture is phase-ready for this variant.

Focus on material defects only:
- missing feature coverage
- unsupported or unnecessary decomposition
- unsupported technology or persistence choices
- drift from exact source constraints
- fake or missing integration boundaries
- weak expertise descriptions
- structure that does not clearly express the architecture
- structure that distorts the `structured-design` architecture shape

Review rules:
- Accept a simple architecture if it is coherent and sufficient.
- Do not force extra components or integration points.
- Treat this phase as allowed elaboration, but reject unsupported scope creep.
- Cite exact component, FT-*, and RI-* references when you ask for changes.
- Check that the artifact actually follows the `structured-design` skill rather
  than just flattening everything into generic.
- Check that the artifact follows the skill's architecture-doc guidance.
- Check that the artifact starts with a short structured summary of how the
  `structured-design` skill is being applied.
- Check that the preserves the real architecture section structure
  rather than converting section names into item names or generic type
  entries.
- For each material correction, include:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
