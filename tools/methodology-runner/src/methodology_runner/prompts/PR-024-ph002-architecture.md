### Module

architecture

## Prompt 1: Produce Architecture

### Required Files

docs/features/feature-specification.yaml
docs/requirements/requirements-inventory.yaml

### Deterministic Validation

python-module:methodology_runner.phase_2_validation
--architecture-design
docs/architecture/architecture-design.yaml
--feature-spec
docs/features/feature-specification.yaml
--requirements-inventory
docs/requirements/requirements-inventory.yaml

### Generation Prompt

As a software architect, you must turn the feature specification into a
coherent architecture document and write it to
docs/architecture/architecture-design.yaml.

Context:
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>
<REQUIREMENTS_INVENTORY>
{{INCLUDE:docs/requirements/requirements-inventory.yaml}}
</REQUIREMENTS_INVENTORY>

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

- Cover every FT-* feature at least once through `components` for
  runtime/product behavior or through `related_artifacts` for README,
  documentation, test, verification, and report deliverables.
- Prefer `FT-*` and `RI-*` traceability for architecture claims.
- Use `AC-*` traceability only when a needed claim is not supported by a
  broader `FT-*` or `RI-*` statement.
- System components are code-bearing units: applications, services, libraries,
  UI modules, adapters, providers, command-line entry points, or similar
  implementation units that downstream phases can design, simulate, build, and
  verify. The `components` list is only for these code/system units.
- Related artifacts are non-component deliverables such as README files,
  design documents, runbooks, automated tests, test suites, verification
  scripts, or reports. Put those in `related_artifacts`, not in `components`.
- A README for the overall system is a system-level related artifact. It may
  document one or more components, but it is not itself a component.
- Keep related artifacts conceptual in PH-002. Name the kind of artifact and
  the components/features it supports, but do not assign concrete file or
  directory paths here. PH-003 solution design owns project-relative paths for
  source modules, README files, tests, scripts, and other deliverable files.
- Features that require README content, documentation, automated tests, or
  verification commands are covered by a matching `related_artifacts` entry.
  Component coverage is only required when a real code/system component
  directly owns the behavior being documented or verified.
- Every component must include at least one conceptual example that names a
  scenario, the expected outcome, and the FT-* feature refs it illustrates.
- Every integration point must include at least one conceptual example flow
  that names the scenario, expected outcome, and FT-* feature refs it
  illustrates. If there are no real cross-component interactions, use
  `integration_points: []` and do not invent one for the sake of an example.
- Do not invent components that serve no features.
- Do not invent unnecessary frameworks, databases, services, or integration
  points.
- Treat README files, documentation, automated tests, test suites, and
  verification scripts as deliverables or responsibilities of the implemented
  system unless the request explicitly asks for a runtime documentation service,
  verification service, or test-service component. Do not create architecture
  components just to represent those support artifacts.
- Break the system into components that can be built and tested separately when
  there is a real dependency, API, library, service, or other integration
  boundary. Do not split a single coherent component only to create a simulation.
- A single local or deployable application can still have multiple architecture
  components when it contains real browser-to-server, server-to-library,
  adapter-to-provider, dependency-injection, API route, package/module,
  command, or service boundaries that help downstream phases design, simulate,
  build, or integration-test the system in stages. Only collapse to one
  component when there is no meaningful internal or external implementation
  boundary.
- Mark only real provider components as simulation targets. Documentation,
  verification, and test-suite components are not simulation targets, although
  they may later consume simulations in integration tests.
- Mark a component `simulation_target: true` only when another real runtime or
  implementation component in this architecture consumes that provider through a
  dependency-injection, API, library, service, command, or equivalent
  integration boundary. Human instructions, README content, and automated tests
  do not by themselves justify simulating the provider.
- For a truly single-component application with no meaningful internal or
  external provider, service, library, API, dependency-injection, command, or
  module boundary, use one component with `simulation_target: false`,
  `simulation_boundary: "none"`, and no integration points.
- Keep the architecture at architecture level. Do not drift into low-level
  implementation detail.
- Make the rationale for the architecture clear in the structured content.
- Use the exact PH-002 architecture schema:
  - top-level keys exactly `components`, `related_artifacts`,
    `integration_points`, `rationale`
  - component IDs must use `CMP-NNN`
  - related artifact IDs must use `ART-NNN`
  - component feature coverage must be expressed in `features_served`
  - related artifact feature coverage must be expressed in `features_served`
  - every component must declare `simulation_target` and `simulation_boundary`
  - every component must include an `examples` list with at least one
    conceptual behavior example
  - integration point IDs must use `IP-NNN`
  - each integration point `between` list must name exactly two distinct
    `CMP-NNN` components
  - each integration point must include an `examples` list with at least one
    conceptual flow example
- Do not use `MODULE-*`, `system_shape.modules`, `supports`,
  `boundaries_and_interactions.integration_points`, `finality`,
  `definition_of_good`, or `test_cases` as substitutes for the PH-002 schema.
- Write only docs/architecture/architecture-design.yaml.

Output schema to satisfy:
```yaml
components:
  - id: "CMP-NNN"
    name: "Component name"
    role: "runtime | service | library | adapter | provider | cli | ui"
    technology: "Python | TypeScript | ..."
    runtime: "Runtime or none"
    frameworks: []
    persistence: "none | ..."
    expected_expertise: ["Plain-language expertise area", "..."]
    features_served: ["FT-NNN", "..."]
    simulation_target: false
    simulation_boundary: "none | dependency-injection | API | library | service | command"
    examples:
      - name: "Example name"
        scenario: "Concrete scenario this component handles"
        expected_outcome: "Observable outcome at architecture level"
        feature_refs: ["FT-NNN", "..."]
related_artifacts:
  - id: "ART-NNN"
    name: "Artifact name"
    artifact_type: "readme | design-doc | runbook | automated-test | test-suite | verification-script | report"
    scope: "system | component"
    related_components: ["CMP-NNN", "..."]
    features_served: ["FT-NNN", "..."]
integration_points:
  - id: "IP-NNN"
    between: ["CMP-NNN", "CMP-NNN"]
    protocol: "sync-call | api-call | library-call | service-call | command | shared-store | ..."
    contract_source: "FT-NNN / RI-NNN source for the interaction"
    examples:
      - name: "Example interaction"
        scenario: "Concrete scenario that crosses this boundary"
        expected_outcome: "Observable outcome of the interaction"
        feature_refs: ["FT-NNN", "..."]
rationale: "Why this component decomposition is the smallest coherent architecture for the feature set."
```

### Validation Prompt

Review the current architecture artifact against <FEATURE_SPECIFICATION>.

Context:
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>
<REQUIREMENTS_INVENTORY>
{{INCLUDE:docs/requirements/requirements-inventory.yaml}}
</REQUIREMENTS_INVENTORY>
<ARCHITECTURE_DESIGN>
{{RUNTIME_INCLUDE:docs/architecture/architecture-design.yaml}}
</ARCHITECTURE_DESIGN>

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

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
- missing component examples or integration-point examples that would make the
  architecture too abstract for downstream design
- weak expertise descriptions
- missing PH-002 schema fields
- missing simulation target classification
- simulation targets assigned to documentation, verification, or test-suite
  components instead of real provider components
- support artifacts such as README files, documentation, tests, or verification
  scripts modeled as architecture components when the request only asks for
  those artifacts as deliverables
- simulation targets that are justified only by README, human-instruction,
  documentation, test, or verification consumers rather than by another real
  runtime or implementation component
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
- Do not reject internal code boundaries solely because the requested software
  is one local or deployable application. Browser/server, API, library,
  package/module, dependency-injection, command, and service boundaries are
  valid when they provide downstream design, simulation, build, or
  integration-test value.
- Check that the artifact follows the exact PH-002 architecture schema:
  top-level `components`, `related_artifacts`, `integration_points`, and
  `rationale`.
- Reject artifacts that use `MODULE-*` entries, `supports` lists, or
  structured-design sections such as `system_shape`, `finality`,
  `definition_of_good`, or `test_cases` as substitutes for `CMP-*`
  components with `features_served`.
- Reject any component without `expected_expertise`, or any integration point
  whose `between` list does not contain exactly two distinct `CMP-*`
  component IDs.
- Reject any component without at least one conceptual example containing
  `name`, `scenario`, `expected_outcome`, and `feature_refs`.
- Reject any integration point without at least one conceptual flow example
  containing `name`, `scenario`, `expected_outcome`, and `feature_refs`.
- Reject any component missing `simulation_target` or `simulation_boundary`.
- Reject `simulation_target: true` for documentation, verification, or test-suite
  components. A simulation target must be a component that exposes behavior to
  another component through dependency injection, an API, a library boundary, a
  service boundary, a command boundary, or an equivalent real integration point.
  The provider may be internal to the same local or deployable application.
- Reject `simulation_target: true` when the only consumers are humans,
  documentation, README guidance, tests, or verification artifacts.
- Reject architecture components whose only purpose is a README, documentation
  file, automated test, test suite, or verification script unless the source
  request explicitly asks for that artifact to be a runtime service or
  independently implemented system component.
- Reject missing `related_artifacts` coverage for requested README,
  documentation, automated test, test-suite, verification-script, or report
  deliverables.
- Do not reject support-artifact features solely because they are absent from
  `components[*].features_served`; related artifact coverage is their PH-002
  ownership path unless a real code/system component directly owns the behavior
  being documented or verified.
- Reject `related_artifacts` entries that assign concrete file or directory
  paths. Architecture is conceptual; PH-003 solution design assigns paths.
- Reject `related_artifacts` entries that reference unknown `CMP-*` components
  or unsupported `FT-*` features.
- For each material correction, include:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
