# Component Simulation Framework

This document specifies the Phase 5 simulation model used by the methodology
runner.

Phase 5 creates compile-checked component simulations. A simulation is a
substitutable fake, stub, adapter, in-memory service, command implementation, or
library implementation for a real architecture component. It is consumed through
the same dependency boundary that later code will use for the real component.

Phase 5 does not simulate test suites. A test may use a simulation to focus on
integration points, but the simulation target is the service or library being
substituted, not the test harness.

## Inputs

Phase 5 reads:

- `docs/architecture/architecture-design.yaml`
- `docs/design/interface-contracts.yaml`
- `docs/features/feature-specification.yaml`

The architecture identifies simulation targets with `simulation_target: true`
and declares the integration boundary with `simulation_boundary`. Interface
contracts describe the operations exposed across those boundaries. Feature
specifications keep the behavior grounded in product intent.

## Outputs

Phase 5 writes:

- `docs/simulations/simulation-definitions.yaml`
- the interface files referenced by the manifest
- the implementation files referenced by the manifest

When the architecture declares no simulation targets, Phase 5 writes the empty
manifest `simulations: []` and does not create interface or implementation
files.

The manifest has this shape:

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
      contract_refs: ["CTR-NNN"]
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
        state_model: "none | in-memory | configurable"
        error_modes: []
    compile_commands:
      - "command that verifies the interface and implementation compile"
    validation_rules:
      - rule: "Mechanical or semantic rule for this simulation"
        severity: "blocking"
```

## Target Selection

Every `CMP-*` component with `simulation_target: true` must have at least one
`SIM-*` entry. Components with `simulation_target: false` must not receive a
simulation.

When every architecture component declares `simulation_target: false`, the
methodology runner records Phase 5 as skipped after writing
`docs/simulations/simulation-definitions.yaml` with `simulations: []`. That
skipped status satisfies downstream predecessor checks.

Documentation, verification, and test-suite components are not simulation
targets. Those components can consume simulations, but they do not constitute
the substituted service.

## Interface Contract

Every simulation declares an explicit language interface:

- `language` names the implementation language.
- `kind` names the interface mechanism.
- `path` points to the interface source file.
- `symbol` names the interface type, protocol, adapter, API, or command.
- `contract_refs` lists the `CTR-*` contracts whose behavior is exposed.

The implementation declares:

- `path` for the simulation source file.
- `symbol` for the fake or stub implementation.
- `implements` matching the interface `symbol`.
- `behavior` describing the state and behavior modeled by the simulation.

The implementation source must import, extend, implement, conform to, or
otherwise bind to the declared interface in a way that the compile or
interface-check command verifies.

## Usage Handoff

Every simulation documents how downstream implementation should use it.

Skeleton simulations point to the source reference PH-006 should fill out or
replace directly. Stubs, mocks, fakes, adapters, and services describe the
configuration, startup steps, import path, dependency-injection binding,
command, or URL that consumers should use.

The `artifacts` list is the authoritative handoff to PH-006. It lists every
generated simulation file and explains how the implementation workflow should
consume, configure, fill in, or retire each file during gradual implementation
and gradual integration.

Usage documentation lives in the generated artifacts themselves as inline
comments or docstrings, or in a README/usage file listed in `artifacts`.

## Behavior Model

The simulation behavior must be as sophisticated as the integration scenario
requires.

Simple boundaries can use stateless fakes. Stateful integrations need in-memory
state. Consumers that need to exercise error handling need configurable error
modes. A simulation is insufficient when it compiles but cannot exercise the
consumer behavior implied by the architecture and interface contracts.

## Mechanical Validation

Each simulation provides `compile_commands` that run from the project root and
exit successfully. Statically typed projects should use the project compiler or
type checker. Dynamic projects should use the strongest available project-local
command that imports the interface and fake implementation and exercises the
exposed members.

The Phase 5 deterministic validator checks:

- manifest top-level shape
- empty-manifest validity when there are no architecture simulation targets
- architecture target coverage
- required fields
- absence of the legacy contract-scenario shape
- component target validity
- interface and implementation consistency
- usage instructions and documentation shape
- declared simulation artifact list shape
- path existence for declared source files
- compile command exit status
- feature context availability

## Traceability

Traceability flows through both component and contract references:

- `CMP-*` to `SIM-*` through `component_ref`
- `CTR-*` to `SIM-*` through `interface.contract_refs`
- `SIM-*` to `SCN-*` through `integration_scenarios`

This keeps simulations tied to real architecture components while preserving the
contract behavior that downstream implementation and integration tests need.
