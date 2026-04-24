### Module

intelligent-simulations

## Prompt 1: Produce Intelligent Simulations

### Required Files

docs/architecture/architecture-design.yaml
docs/design/interface-contracts.yaml
docs/features/feature-specification.yaml

### Deterministic Validation

python-module:methodology_runner.phase_5_validation
--architecture
docs/architecture/architecture-design.yaml
--contracts
docs/design/interface-contracts.yaml
--feature-spec
docs/features/feature-specification.yaml
--simulations
docs/simulations/simulation-definitions.yaml

### Generation Prompt

As a simulation designer, you must create compile-checked component simulation
stubs for the architecture and write their manifest to
docs/simulations/simulation-definitions.yaml.

Context:
<ARCHITECTURE_DESIGN>
{{INCLUDE:docs/architecture/architecture-design.yaml}}
</ARCHITECTURE_DESIGN>
<INTERFACE_CONTRACTS>
{{INCLUDE:docs/design/interface-contracts.yaml}}
</INTERFACE_CONTRACTS>
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>

Module-local generator context:
Embedded directives for this step:

- This phase simulates system components, not test suites.
- A simulation is a compileable fake, stub, adapter, or in-memory service for a
  real architecture component that another component can consume through a
  dependency injection, API, library, service, command, or equivalent boundary.
- Do not create simulations for documentation, verification, or test-suite
  components. Those components may later use simulations to focus integration
  tests, but they are not themselves the simulated service.
- For every architecture component with `simulation_target: true`, create at
  least one SIM-* simulation. Do not create SIM-* entries for components whose
  `simulation_target` is false.
- If no architecture component has `simulation_target: true`, write
  docs/simulations/simulation-definitions.yaml with exactly `simulations: []`
  and do not create simulation source files.
- Every simulation must include an explicit language interface and simulation
  implementation. The implementation must compile against or otherwise satisfy
  that interface using commands declared in the manifest.
- Every simulation must document how downstream work should use it. Skeletons
  must name the direct source reference to fill or replace; stubs, mocks,
  fakes, adapters, and services must name the import, dependency-injection
  binding, configuration key, command, or URL that consumers should use.
- Every simulation must list every created simulation artifact, including
  interface files, implementation files, configuration files, fixtures,
  README/usage files, or other generated support files. That artifact list is
  the handoff used by PH-006 for gradual implementation and gradual
  integration.
- Usage documentation must live in a generated artifact as inline comments or
  docstrings, or in a README/usage file listed in the manifest. The manifest
  must point to that documentation location.
- The simulation code must model the functionality exposed through the interface
  at the level needed for integration scenarios. Simple stateless fakes are
  acceptable for simple boundaries; stateful fakes, configurable errors, or
  richer behavior are required when the integration point needs them.

Phase purpose:
- Turn architecture component boundaries into concrete simulation stubs.
- Make each simulated component consumable by later implementation and
  integration-test slices.
- Use compile or interface-check commands to mechanically prove that the
  simulation code conforms to its declared interface.
- Preserve contract and feature traceability without generating scenario-only
  YAML that cannot be compiled.

Important interpretation:
- Architecture is the authority for which components are eligible for
  simulation.
- Interface contracts describe the operations the simulated component must
  support, but a SIM-* entry targets a `CMP-*` component, not a `CTR-*`
  contract by itself.
- A simulation manifest is not enough. The referenced interface and simulation
  source files must exist on disk.
- Choose the language, interface kind, and compile/check command from the
  component technology and project conventions already present in the upstream
  artifacts. Do not invent frameworks or toolchains that the project does not
  otherwise need.
- If the project language is statically typed, use the project compiler or type
  checker. If the project language is dynamic, use the strongest available
  standard or project-local command that imports the interface and fake and
  exercises the exposed members.
- If no reliable compile or interface-check command can be defined for a
  required simulation target, do not fake compliance. Escalate in the judge
  loop by making that gap explicit in the artifact and validation response.
- Tests can be described as downstream consumers of simulations, but this phase
  must not output a simulation whose `component_ref` is a verification or
  test-suite component.
- Keep generated source files under `docs/simulations/` only when they are
  explanatory examples. Prefer a real source-like location such as
  `simulations/`, `tests/simulations/`, or the project-local equivalent when
  the files are meant to compile.

Output schema to satisfy:
```yaml
simulations:
  - id: "SIM-NNN"
    component_ref: "CMP-NNN"
    simulated_component: "Component name"
    purpose: "Why this component needs a simulation for integration work"
    interface:
      language: "python | typescript | ..."
      kind: "Protocol | abstract_base_class | TypeScript interface | API adapter | ..."
      path: "relative/path/to/interface/source"
      symbol: "InterfaceName"
      contract_refs: ["CTR-NNN", "..."]
    implementation:
      path: "relative/path/to/simulation/source"
      symbol: "FakeOrStubName"
      implements: "InterfaceName"
      behavior: "State and behavior modeled by this simulation"
    usage:
      mode: "skeleton | stub | mock | fake | adapter | service"
      instructions: "How downstream code should import, call, configure, start, or replace this simulation"
      integration_reference: "Import path, dependency injection binding, config key, command, or URL"
      configuration: {}
      startup: []
      retirement: "How PH-006 should replace or keep this simulation during gradual integration"
      documentation:
        location: "inline_comments | readme"
        path: "relative/path/to/file/with/usage/documentation"
    artifacts:
      - path: "relative/path/to/generated/artifact"
        role: "interface | implementation | configuration | fixture | readme | usage_documentation | other"
        description: "What this artifact contains"
        phase_6_usage: "How the PH-006 workflow should use or retire this artifact"
    integration_scenarios:
      - id: "SCN-NNN"
        name: "Scenario name"
        exposed_functionality: "Interface behavior exercised by consumers"
        inputs: {}
        outputs: {}
        state_model: "none | in-memory | configurable | ..."
        error_modes: []
    compile_commands:
      - "command that verifies the interface and implementation compile"
    validation_rules:
      - rule: "Mechanical or semantic rule for this simulation"
        severity: "blocking"
```

Acceptance requirements:
- The manifest file must be valid YAML parseable by a standard YAML parser.
- The top-level key must be exactly:
  simulations
- Every architecture component with `simulation_target: true` must have at
  least one SIM-* entry with a matching `component_ref`.
- If the architecture has no simulation targets, the correct manifest is
  `simulations: []` and no interface or implementation files are required.
- No SIM-* entry may target a component whose `simulation_target` is false.
- No SIM-* entry may target documentation, verification, or test-suite
  components.
- Every simulation must define:
  id
  component_ref
  simulated_component
  purpose
  interface
  implementation
  usage
  artifacts
  integration_scenarios
  compile_commands
  validation_rules
- Every `interface` must define:
  language
  kind
  path
  symbol
  contract_refs
- Every `implementation` must define:
  path
  symbol
  implements
  behavior
- Every `usage` must define:
  mode
  instructions
  integration_reference
  configuration
  startup
  retirement
  documentation
- Every `usage.documentation` must define:
  location
  path
- Every `artifacts` list must be non-empty and must include every interface,
  implementation, configuration, fixture, README, usage-documentation, or
  support file created by this phase for the simulation.
- Every artifact entry must define:
  path
  role
  description
  phase_6_usage
- The interface and implementation paths must also appear in the simulation's
  `artifacts` list.
- The `usage.documentation.path` must exist and must appear in the simulation's
  `artifacts` list.
- Every `integration_scenarios` list must be non-empty and must describe
  functionality exposed through the explicit interface.
- Every `compile_commands` list must be non-empty. Each command must be
  executable from the project root and must exit 0.
- Interface and implementation paths named in the manifest must exist on disk.
- Every path named in `usage.documentation` or `artifacts` must exist on disk.
- The generated implementation source must import, implement, extend, conform
  to, or otherwise explicitly bind to the declared interface in a way the
  compile/check command verifies.
- Do not output the legacy contract-scenario schema with `contract_ref`,
  `scenario_bank`, `llm_adjuster`, or assertion-only scenario banks as the
  primary simulation shape.
- Create or update only docs/simulations/simulation-definitions.yaml and the
  simulation files declared in that manifest's `artifacts` lists.
- If a README, configuration, fixture, or usage file is needed to document or
  operate a simulation, it must be listed in the manifest and may be created by
  this phase.
- Write the full manifest to docs/simulations/simulation-definitions.yaml.

### Validation Prompt

Review the current component simulation definitions against
<ARCHITECTURE_DESIGN>, <INTERFACE_CONTRACTS>, and <FEATURE_SPECIFICATION>.

Context:
<ARCHITECTURE_DESIGN>
{{INCLUDE:docs/architecture/architecture-design.yaml}}
</ARCHITECTURE_DESIGN>
<INTERFACE_CONTRACTS>
{{INCLUDE:docs/design/interface-contracts.yaml}}
</INTERFACE_CONTRACTS>
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>
<SIMULATION_DEFINITIONS>
{{RUNTIME_INCLUDE:docs/simulations/simulation-definitions.yaml}}
</SIMULATION_DEFINITIONS>

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Value and fidelity standard:
- Judge whether the simulations preserve the requested behavior carried by the
  architecture, contracts, and feature spec while providing substitutable
  component stubs for incremental delivery.
- A simulation is valuable only if downstream code can consume it through the
  declared interface and exercise behavior that matters to integration of the
  requested software.
- Do not reward compileable but behaviorless fakes, scenario catalogs that are
  not usable as component substitutes, or sophisticated simulations that drift
  beyond the upstream request.

Module-local judge context:

- Review for wrong simulation targets, missing language interfaces,
  non-compileable stubs, undocumented usage, incomplete artifact handoffs,
  insufficient behavior models, implementation leakage, and missing component
  coverage.

Your job is to decide whether the generated component simulations are
phase-ready.

Review method:
- Iterate through architecture components in CMP-* order.
- Identify the components with `simulation_target: true`.
- For each simulation target, verify that a SIM-* entry supplies an explicit
  language interface, implementation source, compile/check command, and
  integration scenarios for the component's exposed behavior.
- Within each SIM-* entry, review the interface and implementation together.
- Only flag a missing behavior if it would change downstream implementation or
  integration-test planning.

Focus your semantic review on these failure modes:

1. Wrong target:
   - Flag simulations that target documentation, verification, or test-suite
     components.
   - Flag simulations organized around test-suite behavior instead of a system
     component boundary.
2. Missing interface:
   - Flag any simulation without an explicit language interface source path,
     symbol, and implementation binding.
3. Weak mechanical proof:
   - Flag compile/check commands that are absent, irrelevant, or incapable of
     checking the interface and simulation implementation.
4. Missing usage handoff:
   - Flag simulations that do not explain how PH-006 should import, configure,
     start, call, or replace the simulation.
   - Flag skeletons whose direct source reference is unclear, and flag stubs,
     mocks, fakes, adapters, or services whose configuration, URL, command, or
     dependency-injection binding is unclear.
5. Incomplete artifact list:
   - Flag missing interface, implementation, configuration, fixture, README, or
     usage-documentation files from the manifest artifact list when downstream
     implementation would need them for gradual integration.
6. Behavior gaps:
   - Flag simulations whose behavior model is too thin for the integration
     scenarios implied by the architecture and contracts.
7. Contract underuse:
   - Flag simulations that ignore contract operations attached to the simulated
     component's integration points.
8. Unsupported toolchain:
   - Flag source files or commands that invent dependencies, frameworks, or
     language tooling not justified by the upstream artifacts.

Review instructions:
- Use the deterministic validation report as authoritative for manifest shape,
  target coverage, usage/artifact-list field presence, path existence, and
  command exit codes.
- Treat this phase as an allowed elaboration layer over architecture and
  contracts, but only for simulation stubs and their interfaces.
- Do not ask for scenario-only YAML when compileable code is required.
- Do not require implementation-specific business internals beyond the public
  interface and contract behavior needed for integration.
- Accept a minimal in-memory fake when the component boundary is simple and the
  contracts do not require richer behavior.
- Require stateful or configurable behavior when consumers need to exercise
  multiple outcomes, errors, or edge cases through the same interface.
- If you find issues, cite exact SIM-* and CMP-* IDs.
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary
- Use VERDICT: pass only if the artifact is phase-ready with no material target,
  interface, compile, behavior, or traceability defects.
- Use VERDICT: revise if the artifact can be corrected in the manifest or
  declared simulation files.
- Use VERDICT: escalate only if upstream architecture or contracts do not define
  enough component-boundary information to create compile-checked simulations.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
