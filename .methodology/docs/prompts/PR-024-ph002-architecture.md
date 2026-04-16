## Prompt 1: Produce Architecture

### Module

architecture

### Required Files

docs/requirements/raw-requirements.md
docs/requirements/requirements-inventory.yaml
docs/features/feature-specification.yaml

### Checks Files

docs/architecture/stack-manifest.yaml

### Deterministic Validation

scripts/phase-2-deterministic-validation.py
--stack-manifest
docs/architecture/stack-manifest.yaml
--feature-spec
docs/features/feature-specification.yaml
--requirements-inventory
docs/requirements/requirements-inventory.yaml

### Generation Prompt

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

### Validation Prompt

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
