### Module

solution-design

## Prompt 1: Produce Solution Design

### Required Files

docs/architecture/architecture-design.yaml
docs/features/feature-specification.yaml

### Deterministic Validation

python-module:methodology_runner.phase_3_validation
--solution-design
docs/design/solution-design.yaml
--architecture-design
docs/architecture/architecture-design.yaml
--feature-spec
docs/features/feature-specification.yaml

### Generation Prompt

As a software designer, you must refine the architecture into explicit
component responsibilities and write the solution design to
docs/design/solution-design.yaml.

Context:
<ARCHITECTURE_DESIGN>
{{INCLUDE:docs/architecture/architecture-design.yaml}}
</ARCHITECTURE_DESIGN>
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>

Module-local generator context:
Embedded directives for this step:
<Structured design directives>
{{INCLUDE:../../../../../../agent-assets/skills/structured-design/SKILL.md}}
</Structured design directives>


- Preserve the phase-2 architecture component boundaries. Do not invent, split,
  merge, or rename architecture components in this phase.
- If the architecture has one component, the solution design should keep one
  component.
- Give each component one clear ownership statement. Avoid overlapping or
  mixed responsibilities.
- Map each feature only to the components that materially realize it.
- Add interactions for every real dependency handoff that crosses component
  boundaries, including human-mediated handoffs that the architecture treats
  as real integration points.
- Do not omit an interaction merely because a human mediates it. If one
  component depends on another through documented usage, observed execution,
  or another preserved architecture linkage, represent that dependency with an
  INT-* interaction.
- If the preserved architecture has one component or no real cross-component
  flow, use `interactions: []`.
- Keep technology and runtime choices aligned with the stack manifest unless
  an upstream artifact explicitly justifies a refinement.

Phase purpose:
- Refine the architecture into explicit component responsibilities.
- Map every FT-* feature to the components that realize it.
- Declare inter-component interactions where real data or control flows cross
  component boundaries.
- Make ownership boundaries and dependencies explicit for downstream contracts.

Important interpretation:
- This phase is a constrained elaboration layer.
- You may introduce supporting design detail when it is non-contradictory and
  directly or indirectly supports the phase-2 architecture and feature spec.
- Do not multiply components or interactions unless the upstream architecture
  already contains those boundaries.
- A trivial one-component architecture should remain one component here.

Output schema to satisfy:
components:
  - id: "CMP-NNN"
    name: "Component name"
    responsibility: "What this component exclusively owns"
    technology: "implementation technology or framework"
    feature_realization_map:
      FT-NNN: "How this component contributes"
    dependencies: ["CMP-NNN", "..."]
interactions:
  - id: "INT-NNN"
    source: "CMP-NNN"
    target: "CMP-NNN"
    protocol: "sync-call"
    data_exchanged: "What flows across the boundary"
    triggered_by: "What initiates this interaction"

Acceptance requirements:
- The file must be valid YAML parseable by a standard YAML parser.
- The top-level keys must appear exactly in this order:
  components
  interactions
- Every component must contain:
  id
  name
  responsibility
  technology
  feature_realization_map
  dependencies
- Every FT-* from docs/features/feature-specification.yaml must appear in at
  least one component's feature_realization_map.
- feature_realization_map values must explain the component's contribution and
  must not be empty placeholders.
- Every dependency on another component must be justified by at least one real
  interaction, unless the dependency is purely static and non-runtime.
- A human-mediated documentation or verification handoff still counts as a
  real interaction when the architecture already defines it as an integration
  point or when downstream contracts would need that linkage made explicit.
- Every interaction must contain:
  id
  source
  target
  protocol
  data_exchanged
  triggered_by
- Allowed protocols are:
  sync-call
  async-message
  event
  shared-store
- Do not create components that serve no features.
- Do not create interactions for fake or purely rhetorical boundaries.
- Do not create any files other than docs/design/solution-design.yaml.
- Write the full file contents to docs/design/solution-design.yaml.

### Validation Prompt

Review the current solution design against <ARCHITECTURE_DESIGN> and
<FEATURE_SPECIFICATION>.

Context:
<ARCHITECTURE_DESIGN>
{{INCLUDE:docs/architecture/architecture-design.yaml}}
</ARCHITECTURE_DESIGN>
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>
<SOLUTION_DESIGN>
{{RUNTIME_INCLUDE:docs/design/solution-design.yaml}}
</SOLUTION_DESIGN>

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Module-local judge context:
Embedded directives for this step:
<Structured review directives>
{{INCLUDE:../../../../../../agent-assets/skills/structured-review/SKILL.md}}
</Structured review directives>


- Review for responsibility overlap, weak or missing feature realization,
  invented interactions, inconsistent dependencies, and implementation-detail
  leakage that belongs to a later phase.

Your job is to decide whether the generated solution design is phase-ready.

Review method:
- Iterate through components in CMP-* order.
- For each component, review responsibility, technology, feature_realization_map,
  and dependencies together.
- Then iterate through interactions in INT-* order.
- Before flagging any feature realization, interaction, or ownership boundary
  as missing, check whether that same downstream-actionable meaning is already
  covered elsewhere in the artifact.
- Only flag it as missing if the allegedly missing content would change
  downstream contracts or implementation work.

Focus your semantic review on these failure modes:

1. Orphan components:
   - Flag any component whose feature_realization_map is empty or references
     only non-existent features.
2. Unsupported or blurry ownership:
   - Flag components whose responsibility boundaries overlap so heavily that
     downstream contracts or implementation ownership would become ambiguous.
3. Unnecessary decomposition:
   - Flag components or interactions that materially complicate the design
     without improving ownership clarity or downstream implementation choices.
4. Missing interactions:
   - Flag cases where a dependency implies meaningful runtime or data flow but
     no INT-* interaction captures it.
5. Unsupported technology detail:
   - Flag technology assignments that are not at least indirectly supported by
     the stack manifest and feature specification.
6. Untraced features:
   - Flag any FT-* feature that is not materially realized by at least one
     component.

Review instructions:
- Use the deterministic validation report as authoritative for structural
  checks, reference existence, dependency-to-interaction coverage, and feature
  coverage counts.
- Treat this phase as an allowed elaboration layer.
- Only ask for a change when the current design is wrong, contradictory,
  materially unsupported, or the change would materially affect downstream
  contract design or implementation decisions.
- Do not force extra decomposition if a simpler design is coherent.
- Do not request wording polish or alternative naming unless the current choice
  is actually misleading or materially consequential.
- If you find issues, cite exact CMP-* / INT-* / FT-* IDs.
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary
- Use VERDICT: pass only if the artifact is phase-ready with no material
  ownership, decomposition, interaction, or traceability defects.
- Use VERDICT: revise if the artifact can be corrected within this same file.
- Use VERDICT: escalate only if the upstream artifacts are too ambiguous or
  contradictory to produce a stable solution design.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
