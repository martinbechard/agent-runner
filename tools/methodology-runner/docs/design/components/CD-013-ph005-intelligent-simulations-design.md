# Design: PH-005 Intelligent Simulations

## 1. Finality

This design explains how `PH-005` produces component simulation stubs.

- **GOAL: GOAL-1** Produce compile-checked component simulations
  - **SYNOPSIS:** `PH-005` turns architecture simulation targets into explicit
    language interfaces, simulation implementations, and a durable manifest at
    `docs/simulations/simulation-definitions.yaml`.
  - **BECAUSE:** Later implementation and integration-test slices need
    substitutable component stubs, not scenario-only descriptions.

## 2. Inputs And Outputs

This section names the files that the phase uses.

- **FILE: FILE-1** Architecture design
  - **SYNOPSIS:** Primary input:
    - `docs/architecture/architecture-design.yaml`
  - **BECAUSE:** The architecture declares which `CMP-*` components are real
    simulation targets.

- **FILE: FILE-2** Interface contracts
  - **SYNOPSIS:** Behavior input:
    - `docs/design/interface-contracts.yaml`
  - **BECAUSE:** Contracts describe the operations and integration behavior the
    simulated component must expose.

- **FILE: FILE-3** Feature specification
  - **SYNOPSIS:** Traceability input:
    - `docs/features/feature-specification.yaml`
  - **BECAUSE:** Simulations must still support feature intent.

- **FILE: FILE-4** Simulation manifest
  - **SYNOPSIS:** Primary manifest output:
    - `docs/simulations/simulation-definitions.yaml`
  - **BECAUSE:** Later phases need one stable index of the generated simulation
    interfaces, implementations, scenarios, and compile commands.

- **FILE: FILE-5** Simulation source files
  - **SYNOPSIS:** Interface and implementation files declared by the manifest.
  - **BECAUSE:** The phase must produce compileable stubs, not only YAML.

## 3. Technical Directives

This section states the technical directives that shape the phase.

- **RULE: RULE-1** Simulate system components
  - **SYNOPSIS:** A `SIM-*` entry targets a real `CMP-*` component with
    `simulation_target: true`.
  - **BECAUSE:** The phase exists to let large systems be built in steps by
    substituting unavailable components.

- **RULE: RULE-2** Do not simulate tests or documentation
  - **SYNOPSIS:** Documentation, verification, and test-suite components are
    consumers of simulations, not simulation targets.
  - **BECAUSE:** Simulating a test suite does not provide a substitutable system
    component for integration work.

- **RULE: RULE-3** Require explicit language interfaces
  - **SYNOPSIS:** Every simulation declares an interface language, kind, path,
    symbol, and contract references.
  - **BECAUSE:** Downstream code needs a concrete boundary for dependency
    injection, APIs, libraries, services, commands, or equivalent integrations.

- **RULE: RULE-4** Compile or check every simulation
  - **SYNOPSIS:** Every simulation declares at least one command that proves the
    interface and implementation compile or satisfy the interface.
  - **BECAUSE:** Mechanical validation should catch interface drift instead of
    relying on manual artifact review.

- **RULE: RULE-5** Match behavior sophistication to integration need
  - **SYNOPSIS:** Simple boundaries may use simple fakes, while stateful or
    multi-outcome contracts require stateful or configurable simulations.
  - **BECAUSE:** A simulation is useful only when it can exercise the consumer
    integration scenarios implied by the architecture and contracts.

- **RULE: RULE-5A** Document simulation usage
  - **SYNOPSIS:** Every simulation declares how PH-006 should use it, including
    whether it is a skeleton to fill directly or a stub, mock, fake, adapter,
    or service consumed through configuration, startup, import, command,
    dependency injection, or URL.
  - **BECAUSE:** Gradual implementation needs clear handoff instructions, not
    only generated files.

- **RULE: RULE-5B** List all generated simulation artifacts
  - **SYNOPSIS:** Every generated interface, implementation, configuration,
    fixture, README, usage document, or support file appears in the simulation's
    `artifacts` list with a `phase_6_usage` instruction.
  - **BECAUSE:** PH-006 uses that list to plan gradual integration and to know
    which simulation assets to consume, fill in, or retire.

- **RULE: RULE-9** Empty target set is a skipped phase
  - **SYNOPSIS:** If every architecture component declares
    `simulation_target: false`, PH-005 writes `simulations: []` and records the
    phase as skipped.
  - **BECAUSE:** A no-op simulation phase should not consume model iterations,
    but downstream phases still need a canonical manifest and satisfied
    predecessor status.

## 4. Workflow

This section describes the phase steps.

- **PROCESS: PROCESS-1** Select simulation targets
  - **SYNOPSIS:** Read the architecture and collect every component with
    `simulation_target: true`.
  - **BECAUSE:** Component selection belongs to the architecture, not to ad hoc
    PH-005 inference.

- **PROCESS: PROCESS-5** Skip empty target sets
  - **SYNOPSIS:** When the selected target set is empty, the runner writes the
    canonical empty manifest and records `.run-files/PH-005-intelligent-simulations/skip-reason.txt`.
  - **BECAUSE:** The harness can decide this mechanically from architecture
    metadata without asking the generator to invent non-existent simulations.

- **PROCESS: PROCESS-2** Generate interfaces and simulations
  - **SYNOPSIS:** For each target component, write an interface file, a
    simulation implementation file, and a `SIM-*` manifest entry.
  - **BECAUSE:** The manifest must point to real files that downstream work can
    import or call.

- **PROCESS: PROCESS-2A** Document usage handoff
  - **SYNOPSIS:** Add usage instructions and artifact-list entries that tell
    PH-006 how to use, configure, start, fill in, or retire the simulation.
  - **BECAUSE:** Implementation slices need explicit simulation handoff data to
    use stubs and mocks intentionally rather than rediscovering integration
    mechanics.

- **PROCESS: PROCESS-3** Validate mechanically
  - **SYNOPSIS:** `tools/methodology-runner/src/methodology_runner/phase_5_validation.py`
    checks manifest shape, target coverage, path existence, and declared
    compile commands.
  - **BECAUSE:** Interface compliance must be checked by executable commands
    where possible.

- **PROCESS: PROCESS-4** Judge semantic usefulness
  - **SYNOPSIS:** The PH-005 judge checks whether each simulation models the
    exposed behavior needed by integration consumers.
  - **BECAUSE:** A stub can compile while still being too thin for the required
    integration scenario.

## 5. Output Shape

This section states what the output file contains.

- **ENTITY: ENTITY-1** Top-level output shape
  - **SYNOPSIS:** The top-level section is:
    - `simulations`
  - **BECAUSE:** That is the manifest section consumed by later phases.

- **ENTITY: ENTITY-2** Simulation fields
  - **SYNOPSIS:** Each simulation contains:
    - `id`
    - `component_ref`
    - `simulated_component`
    - `purpose`
    - `interface`
    - `implementation`
    - `usage`
    - `artifacts`
    - `integration_scenarios`
    - `compile_commands`
    - `validation_rules`
  - **BECAUSE:** These fields connect a component target to compileable stub
    files and integration behavior.

## 6. Definition Of Good

This section states when the phase passes.

- **RULE: RULE-6** Component target coverage
  - **SYNOPSIS:** Every architecture simulation target has at least one `SIM-*`
    entry, no non-target component has a simulation, and an empty target set
    uses the canonical `simulations: []` manifest.
  - **BECAUSE:** The manifest must match the architecture boundary decisions.

- **RULE: RULE-7** Interface implementation proof
  - **SYNOPSIS:** Interface files and implementation files exist and every
    compile command exits successfully.
  - **BECAUSE:** Compile failure is direct evidence that the simulation cannot
    serve as an integration substitute.

- **RULE: RULE-8** No legacy scenario-only simulation shape
  - **SYNOPSIS:** The artifact must not use `contract_ref`, `scenario_bank`, or
    `llm_adjuster` as the primary simulation structure.
  - **BECAUSE:** That shape simulates contract scenarios rather than
    substitutable components.

- **RULE: RULE-8A** Complete PH-006 handoff
  - **SYNOPSIS:** Usage instructions and artifact entries are complete enough
    for PH-006 to consume or retire simulations without inventing a new
    integration mechanism.
  - **BECAUSE:** The value of a simulation is realized when implementation
    slices can use it for gradual integration.

## 7. Test Cases

This section lists the tests the phase design expects.

- **TEST CASE: TC-1** Compileable component simulation
  - **SYNOPSIS:** Given a Python component simulation target, confirm PH-005
    validation passes when the manifest points to an interface, a fake
    implementation, and a successful compile/import command.
  - **BECAUSE:** The validator must prove the new component-stub contract.

- **TEST CASE: TC-2** Legacy scenario shape rejection
  - **SYNOPSIS:** Confirm PH-005 validation rejects a `contract_ref` plus
    `scenario_bank` artifact that contains no component interface or
    implementation files.
  - **BECAUSE:** The old test-suite simulation shape must not remain valid.

- **TEST CASE: TC-3** Prompt contract coverage
  - **SYNOPSIS:** Confirm the PH-005 prompt requires component simulation
    targets, explicit language interfaces, source files, and compile commands.
  - **BECAUSE:** The generator must receive the same contract enforced by the
    validator.

- **TEST CASE: TC-4** Empty target skip
  - **SYNOPSIS:** Confirm the runner skips prompt-runner for PH-005 when the
    architecture has no simulation targets, writes `simulations: []`, and lets
    PH-006 predecessor checks proceed.
  - **BECAUSE:** The harness skip behavior is part of the steady-state phase
    contract.

- **TEST CASE: TC-5** Usage and artifact handoff
  - **SYNOPSIS:** Confirm PH-005 validation rejects simulations that omit
    usage instructions, documentation location, or artifact-list entries.
  - **BECAUSE:** The implementation workflow relies on this handoff for
    gradual integration.
