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
- If steady-state design docs already exist under `docs/design/*.md`, inspect
  those markdown files as continuity context.
- Exclude the in-run working artifact `docs/design/solution-design.yaml` and
  anything under `docs/changes/` from that continuity scan.

Module-local generator context:
Embedded directives for this step:
<Structured design directives>
{{INCLUDE:skills/structured-design/SKILL.md}}
</Structured design directives>


- Preserve the phase-2 architecture component boundaries. Do not invent, split,
  merge, or rename architecture components in this phase.
- If the architecture has one component, the solution design should keep one
  component.
- Give each component one clear ownership statement. Avoid overlapping or
  mixed responsibilities.
- Map each feature only to the components that materially realize it.
- For every component, declare `processing_functions` and `ui_surfaces`. Use
  an empty list when the component has no processing functions or UI surfaces.
- For every specified processing function, include at least one concrete
  example with both `input` and `output` values. Use `input: {}` for
  no-argument functions or commands, but still provide a concrete `output`.
- For every specified UI surface, include an `html_mockup` field containing an
  HTML fragment that shows the steady-state user interface structure and
  representative visible content.
- Declare concrete project-relative implementation files for the design in
  `implementation_files`. PH-002 architecture is conceptual and does not own
  file paths; this phase must bind each component and each PH-002
  `related_artifacts` entry to the source, README, test, script, configuration,
  or documentation paths downstream implementation must use.
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
- Use existing steady-state design docs under `docs/design/*.md` to preserve
  stable component names, ownership boundaries, and decomposition when they
  still fit the current architecture and feature spec.
- If the new request or upstream artifacts require a real boundary change,
  evolve the design deliberately instead of copying the old decomposition
  blindly.
- The current architecture and feature specification are authoritative over
  older steady-state design docs when they conflict.

Phase purpose:
- Refine the architecture into explicit component responsibilities.
- Map every FT-* feature to the components that realize it.
- Assign concrete implementation paths for components and related artifacts.
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
    processing_functions:
      - name: "function_or_operation_name"
        purpose: "What this processing function computes or transforms"
        triggered_by_features: ["FT-NNN", "..."]
        examples:
          - name: "example name"
            input: {}
            output: {}
    ui_surfaces:
      - name: "UI surface name"
        purpose: "What user-facing interaction this UI owns"
        triggered_by_features: ["FT-NNN", "..."]
        html_mockup: |
          <main>
            <h1>Representative UI heading</h1>
          </main>
implementation_files:
  - path: "relative/path/from/project/root.py"
    role: "source | test | readme | documentation | configuration | script | data | other"
    component_refs: ["CMP-NNN", "..."]
    artifact_ref: null
    features_supported: ["FT-NNN", "..."]
    purpose: "Why this file exists and what it contains"
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
  implementation_files
  interactions
- Every component must contain:
  id
  name
  responsibility
  technology
  feature_realization_map
  dependencies
  processing_functions
  ui_surfaces
- Every `processing_functions` value must be a list. Each item must contain:
  name
  purpose
  triggered_by_features
  examples
- Every processing function `examples` list must be non-empty. Each example
  must contain:
  name
  input
  output
- Every `ui_surfaces` value must be a list. Each item must contain:
  name
  purpose
  triggered_by_features
  html_mockup
- Every UI `html_mockup` must contain HTML markup. Do not describe a UI in
  prose only.
- `implementation_files` must be a list. Every item must contain:
  path
  role
  component_refs
  artifact_ref
  features_supported
  purpose
- Every component must be referenced by at least one `implementation_files`
  entry.
- Every PH-002 `related_artifacts` entry must be referenced by at least one
  `implementation_files` entry using `artifact_ref: "ART-NNN"`.
- Use `artifact_ref: null` for component source files that do not correspond
  to a PH-002 related artifact.
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
- If steady-state design docs already exist under `docs/design/*.md`, inspect
  those markdown files as continuity context.
- Exclude the in-run working artifact `docs/design/solution-design.yaml` and
  anything under `docs/changes/` from that continuity scan.

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Value and fidelity standard:
- Judge whether the solution design preserves the requested behavior carried by
  <FEATURE_SPECIFICATION> while refining <ARCHITECTURE_DESIGN> into ownership
  and interaction decisions that downstream contracts and implementation can
  use.
- A design element is valuable only if it clarifies responsibility,
  dependency, or feature realization in a way that affects contracts,
  simulations, implementation, or verification.
- Do not reward decomposition, interactions, or naming churn that looks
  elaborate but does not improve fidelity to the original request or downstream
  delivery.

Module-local judge context:
Embedded directives for this step:
<Structured review directives>
{{INCLUDE:skills/structured-review/SKILL.md}}
</Structured review directives>


- Review for responsibility overlap, weak or missing feature realization,
  missing implementation file mapping, missing processing-function examples,
  missing UI HTML mockups, invented interactions, and inconsistent
  dependencies.
- Review continuity with existing steady-state design docs when they exist.
  Flag unjustified component renames, decomposition churn, or ownership drift,
  but do not block deliberate evolution that is supported by the current
  architecture and feature spec.

Your job is to decide whether the generated solution design is phase-ready.

Review method:
- Iterate through components in CMP-* order.
- For each component, review responsibility, technology, feature_realization_map,
  dependencies, processing_functions, and ui_surfaces together.
- Then review implementation_files and confirm each component and PH-002
  related artifact has a concrete project-relative path for downstream
  implementation.
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
4. Missing implementation file mapping:
   - Flag components that have no concrete implementation file path.
   - Flag PH-002 related artifacts that have no concrete implementation file
     path in `implementation_files`.
   - Flag implementation file entries that use unknown CMP-* or ART-* refs.
5. Missing processing examples:
   - Flag any specified processing function that lacks at least one concrete
     example with both input and output values.
   - Do not flag `input: {}` for a no-argument function or command when the
     output is concrete.
6. Missing UI mockups:
   - Flag any specified UI surface whose `html_mockup` is absent, prose-only,
     or not an HTML fragment.
7. Missing interactions:
   - Flag cases where a dependency implies meaningful runtime or data flow but
     no INT-* interaction captures it.
8. Unsupported technology detail:
   - Flag technology assignments that are not at least indirectly supported by
     the stack manifest and feature specification.
9. Untraced features:
   - Flag any FT-* feature that is not materially realized by at least one
     component.

Review instructions:
- Use the deterministic validation report as authoritative for structural
  checks, implementation file mapping, processing example shape, UI HTML
  mockup shape, reference existence, dependency-to-interaction coverage, and
  feature coverage counts.
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
