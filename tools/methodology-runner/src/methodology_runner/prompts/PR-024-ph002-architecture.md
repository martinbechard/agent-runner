### Module

architecture

## Prompt 1: Produce Architecture

### Required Files

docs/features/feature-specification.yaml

### Generation Prompt

As a software architect, you must turn the feature specification into a
coherent architecture document and write it to
docs/architecture/architecture-design.yaml.

Context:
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>

This phase is a constrained elaboration phase.
You may choose technology and architecture details that are coherent with the
feature specification and requirements, but do not invent extra scope.

Keep it as small as the feature set allows.
The output schema below is authoritative. The structured-design directives are
only supporting guidance for clear rationale and decomposition; do not emit the
structured-design architecture shape when it conflicts with this phase schema.
<Structured design directives>
{{INCLUDE:skills/structured-design/SKILL.md}}
</Structured design directives>

Requirements:

- Cover every FT-* feature at least once.
- Prefer `FT-*` and `RI-*` traceability for architecture claims.
- Use `AC-*` traceability only when a needed claim is not supported by a
  broader `FT-*` or `RI-*` statement.
- Do not invent components that serve no features.
- Do not invent unnecessary frameworks, databases, services, or integration
  points.
- Break the system into components that can be built and tested separately when
  there is a real dependency, API, library, service, or other integration
  boundary. Do not split a single coherent component only to create a simulation.
- Mark only real provider components as simulation targets. Documentation,
  verification, and test-suite components are not simulation targets, although
  they may later consume simulations in integration tests.
- Keep the architecture at architecture level. Do not drift into low-level
  implementation detail.
- Make the rationale for the architecture clear in the structured content.
- Use the exact PH-002 architecture schema:
  - top-level keys exactly `components`, `integration_points`, `rationale`
  - component IDs must use `CMP-NNN`
  - component feature coverage must be expressed in `features_served`
  - every component must declare `simulation_target` and `simulation_boundary`
  - integration point IDs must use `IP-NNN`
  - each integration point `between` list must name exactly two distinct
    `CMP-NNN` components
- Do not use `MODULE-*`, `system_shape.modules`, `supports`,
  `boundaries_and_interactions.integration_points`, `finality`,
  `definition_of_good`, or `test_cases` as substitutes for the PH-002 schema.
- Write only docs/architecture/architecture-design.yaml.

Output schema to satisfy:
```yaml
components:
  - id: "CMP-NNN"
    name: "Component name"
    role: "runtime | documentation | verification | ..."
    technology: "Python | Markdown | ..."
    runtime: "Runtime or none"
    frameworks: []
    persistence: "none | ..."
    expected_expertise: ["Plain-language expertise area", "..."]
    features_served: ["FT-NNN", "..."]
    simulation_target: true
    simulation_boundary: "dependency-injection | API | library | service | command | none"
  integration_points:
    - id: "IP-NNN"
      between: ["CMP-NNN", "CMP-NNN"]
      protocol: "sync-call | shared-store | human-instruction | ..."
      contract_source: "FT-NNN / RI-NNN source for the interaction"
rationale: "Why this component decomposition is the smallest coherent architecture for the feature set."
```

### Validation Prompt

Review the current architecture artifact against <FEATURE_SPECIFICATION>.

Context:
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>
<ARCHITECTURE_DESIGN>
{{RUNTIME_INCLUDE:docs/architecture/architecture-design.yaml}}
</ARCHITECTURE_DESIGN>

Decide whether the YAML architecture is phase-ready.

Value and fidelity standard:
- Judge whether the architecture makes the smallest useful set of component and
  boundary decisions needed to deliver the requested software represented by
  <FEATURE_SPECIFICATION>.
- The architecture is valuable only when its components, integration points,
  and simulation-target classifications improve downstream contracts,
  simulations, implementation, or verification.
- Do not reward schema-shaped architecture that invents unnecessary structure,
  hides a real integration boundary, or preserves the original request only as
  superficial traceability labels.

Review method:
- Iterate through the authored architecture units in order.
- Review each architecture unit for supported feature coverage, justified
  boundaries, and downstream usefulness.
- Before flagging a feature, boundary, or rationale as missing, check whether
  that same actionable meaning is already covered elsewhere in the
  architecture.
- Only flag it as missing if the allegedly missing content would change
  downstream design, contracts, implementation, or verification.

Focus on material defects only:
- missing feature coverage
- unsupported or unnecessary decomposition
- unsupported technology or persistence choices
- drift from exact source constraints
- fake or missing integration boundaries
- weak expertise descriptions
- missing PH-002 schema fields
- missing simulation target classification
- simulation targets assigned to documentation, verification, or test-suite
  components instead of real provider components
- structure that does not clearly express the architecture in the required
  PH-002 schema
- structure that incorrectly emits structured-design item types instead of the
  required PH-002 schema

Review rules:
<Structured review directives>
{{INCLUDE:skills/structured-review/SKILL.md}}
</Structured review directives>


- Accept a simple architecture if it is coherent and sufficient.
- Do not force extra components or integration points.
- Treat this phase as allowed elaboration, but reject unsupported scope creep.
- Cite exact component, FT-*, and RI-* references when you ask for changes.
- Treat unnecessary `AC-*` dependence as a traceability quality defect when the
  same claim should have been grounded in `FT-*` source text.
- Check that the artifact follows the exact PH-002 architecture schema:
  top-level `components`, `integration_points`, and `rationale`.
- Reject artifacts that use `MODULE-*` entries, `supports` lists, or
  structured-design sections such as `system_shape`, `finality`,
  `definition_of_good`, or `test_cases` as substitutes for `CMP-*`
  components with `features_served`.
- Reject any component without `expected_expertise`, or any integration point
  whose `between` list does not contain exactly two distinct `CMP-*`
  component IDs.
- Reject any component missing `simulation_target` or `simulation_boundary`.
- Reject `simulation_target: true` for documentation, verification, or test-suite
  components. A simulation target must be a component that exposes behavior to
  another component through dependency injection, an API, a library boundary, a
  service boundary, a command boundary, or an equivalent real integration point.
- For each material correction, include:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
