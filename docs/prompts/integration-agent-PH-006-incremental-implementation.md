# Integration Agent: PH-006 Incremental Implementation

This is a prompt-runner input file with a single prompt and no validator.
The agent reads PH-006's output artifact (implementation plan YAML), the
upstream PH-005 artifact (simulations YAML), the upstream PH-004 artifact
(interface contracts YAML), the upstream PH-003 artifact (solution design
YAML), the upstream PH-002 artifact (stack manifest YAML), the upstream
PH-001 artifact (feature specification YAML), the upstream PH-000 artifact
(requirements inventory YAML), and the original raw requirements, then
evaluates whether the implementation plan contains the semantic content
that PH-007 (Verification Sweep) will need to verify the implementation
end-to-end.

**How to run:**

    prompt-runner run \
      docs/prompts/integration-agent-PH-006-incremental-implementation.md \
      --project-dir <path-to-completed-PH-006-workspace>

The run executes the single critic prompt, skips the judge (no validator),
produces a YAML critique in the run output, and exits with verdict pass.

**Rationale:** see
`docs/superpowers/specs/2026-04-09-skill-pack-and-interactive-harness-notes.md`
section 6 for the full design of integration agents.

---

## Prompt 1: PH-006 integration critique

```
You are a downstream-consumer simulator for PH-006 Incremental
Implementation output. Your job is to read the implementation plan
artifact, the upstream simulations, the upstream interface contracts,
the upstream solution design, the upstream stack manifest, the upstream
feature specification, the upstream requirements inventory, and the
original raw requirements, then evaluate whether the implementation
plan contains the semantic content that PH-007 (Verification Sweep)
will need to verify the implementation end-to-end.

This is NOT a schema check or a format lint. Assume the YAML parses,
the IDs are well-formed, and the code-review-discipline judge has
already passed this artifact for internal consistency (TDD cadence
followed, no dead code, no speculative abstractions, no readability
failures, no security footguns). You are checking whether the CONTENT
is usable by PH-007.

## What to read

Read these eight files from the workspace:

1. The implementation plan YAML at
   {workspace}/docs/implementation/implementation-plan.yaml
2. The simulations YAML at
   {workspace}/docs/simulations/simulation-definitions.yaml
3. The interface contracts YAML at
   {workspace}/docs/design/interface-contracts.yaml
4. The solution design YAML at
   {workspace}/docs/design/solution-design.yaml
5. The stack manifest YAML at
   {workspace}/docs/architecture/stack-manifest.yaml
6. The feature specification YAML at
   {workspace}/docs/features/feature-specification.yaml
7. The requirements inventory YAML at
   {workspace}/docs/requirements/requirements-inventory.yaml
8. The original raw requirements document at
   {workspace}/docs/requirements/raw-requirements.md

You need all eight: the implementation plan (structured output of
PH-006), the simulations (upstream PH-005 output that PH-006 consumed
for test doubles), the interface contracts (upstream PH-004 output),
the solution design (upstream PH-003 output), the stack manifest
(upstream PH-002 output), the feature specification (upstream PH-001
output), the requirements inventory (upstream PH-000 output), and the
raw requirements (the original source). Comparing them lets you catch
cases where the implementation plan lost information needed by the
verification sweep, or where implementation abstraction obscured
signals that PH-007 will need to verify completeness, correctness,
and traceability of the delivered system.

## What PH-007 (Verification Sweep) needs

PH-007 performs a cross-component verification sweep that confirms
the implemented system satisfies every requirement. PH-007 walks the
implementation plan and executes five verification activities:

1. **Dependency-order verification** -- confirms every component was
   built in an order consistent with its dependency graph. PH-007
   replays the build_order, verifying that at each step, every
   dependency of the component under construction is either already
   built (at a prior step) or covered by a simulation (listed in
   simulations_used). If a dependency is neither built nor simulated,
   PH-007 flags a dependency gap.

2. **Unit test verification** -- confirms every contract operation
   and every acceptance criterion has at least one unit test. PH-007
   walks the unit_test_plan and cross-references:
   - acceptance_criteria_refs against the feature specification's AC-*
   - contract_ref against the interface contracts' CTR-* operations
   - test_body_derivable against simulation scenarios from PH-005

3. **Integration test verification** -- confirms every feature flow
   from the solution design's feature_realization_map has an
   integration test exercising the full component chain. PH-007
   walks the integration_test_plan and cross-references:
   - components_involved against the solution design's CMP-*
   - contracts_exercised against the interface contracts' CTR-*
   - scenarios_from against the simulations' SIM-* and SCN-*

4. **Simulation replacement verification** -- confirms every SIM-*
   simulation from PH-005 has been replaced by a real implementation
   and that the correct integration tests were re-run after each
   replacement. PH-007 walks the simulation_replacement_sequence
   and verifies:
   - Every SIM-* from PH-005 has a replacement entry
   - replaced_at_step maps to a valid build_order step
   - integration_tests_to_rerun covers all integration tests that
     used the replaced simulation

5. **End-to-end traceability verification** -- confirms an unbroken
   chain from every requirement (RI-*) through features (FT-*),
   acceptance criteria (AC-*), contracts (CTR-*), build steps, unit
   tests, and integration tests to the delivered implementation.
   PH-007 walks the traceability chain and flags any requirement
   that cannot be traced to at least one passing test.

For PH-007 to do its job, the implementation plan must provide
sufficient content in five areas.

### Area 1: Build Order Traceable to Component Dependencies

PH-007 replays the build_order to verify that every component was
built in an order consistent with its dependencies. For each step in
the build_order, PH-007 checks:

- The component_ref maps to a CMP-* in the solution design
- The contracts_implemented list maps to CTR-* entries where the
  component is either source_component or target_component
- The simulations_used list maps to SIM-* entries whose contract_ref
  is owned by a component not yet built at this step
- No component dependency exists that is neither built at a prior
  step nor covered by a simulation in simulations_used

Build order structural requirements:

| Plan element | What PH-007 needs | What blocks PH-007 |
|---|---|---|
| component_ref | CMP-* that exists in solution design | CMP-* not in solution design or typo |
| contracts_implemented | CTR-* entries where this component is a party | CTR-* that does not reference this component |
| simulations_used | SIM-* entries for dependencies not yet built | SIM-* for a component already built (simulation should be replaced) |
| step ordering | Dependencies built before dependents | Circular or inverted dependency order |
| component coverage | Every CMP-* appears in exactly one step | Missing components or duplicate steps |

Checks:

- Check: does the build_order contain exactly one step for every
  CMP-* in the solution design? PH-007 verifies completeness by
  counting. If any CMP-* is missing, PH-007 cannot verify that
  component was built. If a CMP-* appears in multiple steps, PH-007
  cannot determine which step is the authoritative build point.
- Check: for each step, does every contract in contracts_implemented
  reference the step's component_ref as source_component or
  target_component in the interface contracts? PH-007 uses this to
  verify the component actually owns the contracts it claims to
  implement. A contract_implemented entry that references a CTR-*
  belonging to a different component is a misattribution.
- Check: for each step, does every SIM-* in simulations_used
  correspond to a component NOT yet built at prior steps? PH-007
  verifies that simulations stand in only for components that do not
  yet exist. If a SIM-* in simulations_used corresponds to a
  component already built at a prior step, the simulation should have
  been replaced -- its presence indicates the build order or
  replacement sequence is inconsistent.
- Check: for each step, walk the solution design's interaction graph
  to identify all components that the step's component_ref depends
  on. Is every dependency either (a) built at a prior step or (b)
  covered by a SIM-* in simulations_used? PH-007 uses this to verify
  dependency satisfaction. A dependency that is neither built nor
  simulated means the component under construction cannot function
  at this step.
- Check: does the build_order respect the topological sort implied
  by the interaction graph? Components with no dependencies should
  appear earliest. Components that depend on many others should
  appear latest. While alternative valid orderings exist, the order
  must be a valid topological sort of the dependency graph (ignoring
  edges covered by simulations). PH-007 flags inversions where a
  component is built before its unsimulated dependency.
- The test: could PH-007 replay the build_order from step 1 to step
  N and at each step confirm: (a) the component exists in the
  solution design, (b) all its dependencies are satisfied (built or
  simulated), (c) the contracts it claims to implement are actually
  its contracts, and (d) the simulations it uses are for components
  not yet built? If any step fails this replay, the build order is
  not verifiable.

### Area 2: Unit Test Plan Covering All Contract Operations and Acceptance Criteria

PH-007 verifies that every contract operation and every acceptance
criterion has unit test coverage. For each entry in the
unit_test_plan, PH-007 checks:

- acceptance_criteria_refs maps to actual AC-* entries in the feature
  specification
- contract_ref maps to an actual CTR-* operation in the interface
  contracts
- The test derives from a simulation scenario that exercises the
  targeted operation

Unit test plan structural requirements:

| Plan element | What PH-007 needs | What blocks PH-007 |
|---|---|---|
| acceptance_criteria_refs | AC-* IDs from feature specification | AC-* not in feature specification or phantom |
| contract_ref | CTR-* and operation name from interface contracts | CTR-* that does not exist or operation mismatch |
| test derivation | Traceable to SIM-*/SCN-* scenario | Test with no simulation provenance -- PH-007 cannot verify test case origin |
| operation coverage | Every operation in every CTR-* has at least one test | Operations with no test entry |
| criteria coverage | Every AC-* has at least one test | Acceptance criteria with no test entry |

Checks:

- Check: does every AC-* in the feature specification appear in at
  least one unit_test_plan entry's acceptance_criteria_refs? PH-007
  uses this to verify acceptance criteria coverage. An AC-* with no
  referencing test means PH-007 cannot confirm that criterion is
  satisfied by the implementation.
- Check: does every operation in every CTR-* in the interface
  contracts appear in at least one unit_test_plan entry's
  contract_ref? PH-007 uses this to verify contract operation
  coverage. A contract operation with no test means PH-007 cannot
  confirm that operation is correctly implemented.
- Check: for each unit_test_plan entry, does the test map to a
  specific SIM-*/SCN-* scenario? PH-007 traces test cases back to
  simulation scenarios to verify that test inputs and expected
  outputs derive from the validated simulation, not from ad-hoc
  invention. A test with no scenario provenance forces PH-007 to
  trust the test cases without upstream validation.
- Check: for AC-* criteria that specify error handling behavior,
  does the unit_test_plan contain at least one test with a
  contract_ref whose operation has the corresponding error_type?
  PH-007 matches criterion type to test type. An error-handling
  criterion covered only by a happy-path test does not prove the
  error behavior works.
- Check: for AC-* criteria that specify boundary behavior, does the
  unit_test_plan contain at least one test whose scenario is an
  edge_case from the simulation? PH-007 matches boundary criteria
  to edge_case scenarios. A boundary criterion covered only by a
  happy_path scenario does not prove the boundary behavior works.
- The test: could PH-007 build a coverage matrix with rows = all
  AC-* criteria and columns = unit_test_plan entries, marking each
  cell where a test references that criterion, and find no empty
  rows? Could PH-007 build a second matrix with rows = all CTR-*
  operations and columns = unit_test_plan entries, and find no empty
  rows? If either matrix has empty rows, the unit test plan has
  coverage gaps.

### Area 3: Integration Test Plan Covering All Feature Flows

PH-007 verifies that every feature flow from the solution design's
feature_realization_map has an integration test exercising the full
component chain. For each entry in the integration_test_plan, PH-007
checks:

- components_involved maps to actual CMP-* entries in the solution
  design
- contracts_exercised maps to actual CTR-* entries in the interface
  contracts
- scenarios_from maps to actual SIM-*/SCN-* entries in the
  simulations
- The test exercises the interaction sequence defined in the
  feature_realization_map

Integration test plan structural requirements:

| Plan element | What PH-007 needs | What blocks PH-007 |
|---|---|---|
| components_involved | CMP-* IDs from solution design | CMP-* not in solution design |
| contracts_exercised | CTR-* IDs from interface contracts | CTR-* not in interface contracts |
| scenarios_from | SIM-*/SCN-* IDs from simulations | SIM-* or SCN-* that does not exist |
| feature_ref | FT-* from feature specification | Feature flow with no integration test |
| interaction_sequence_coverage | All interactions in the sequence exercised | Interactions skipped or out of order |

Checks:

- Check: does every feature (FT-*) in the feature_realization_map
  have at least one integration_test_plan entry whose feature_ref
  matches? PH-007 uses this to verify feature-level test coverage.
  A feature with no integration test means PH-007 cannot verify that
  feature's cross-component behavior.
- Check: for each integration_test_plan entry, does the
  components_involved list match the components participating in the
  feature_realization_map's interaction_sequence for that feature?
  PH-007 verifies that the test exercises the correct component
  chain. If components_involved omits a component from the
  interaction sequence, the test does not exercise the full flow.
  If components_involved includes a component not in the sequence,
  the test scope is misrepresented.
- Check: for each integration_test_plan entry, does the
  contracts_exercised list include every CTR-* referenced by the
  interactions in the feature_realization_map's interaction_sequence?
  PH-007 uses this to verify that the test exercises every contract
  in the flow. A missing contract means a link in the chain is
  untested.
- Check: for each integration_test_plan entry, do the scenarios_from
  references map to SIM-*/SCN-* entries that cover the contracts
  in contracts_exercised? PH-007 verifies that integration test
  cases derive from validated simulation scenarios. A scenarios_from
  entry that references a SIM-* covering a different contract than
  the one being tested is a cross-reference error.
- Check: for features with branching flows (multiple outcomes at a
  decision point), does the integration_test_plan contain one test
  per branch? PH-007 needs branch coverage to verify that all
  feature outcomes are exercised. A branching feature with only one
  integration test leaves alternative outcomes unverified.
- Check: for each integration test, can PH-007 trace its
  scenarios_from entries back through the simulation -> contract ->
  interaction -> feature -> acceptance_criteria chain to verify
  that the test satisfies specific AC-* criteria? If the
  scenarios_from reference a SIM-* whose contract_ref leads to an
  interaction not in the test's feature flow, the traceability chain
  is broken.
- The test: could PH-007 build a coverage matrix with rows = all
  FT-* features and columns = integration_test_plan entries, marking
  each cell where a test's feature_ref matches, and find no empty
  rows? Could PH-007 then verify that each test's component chain
  and contract chain match the feature_realization_map? If any
  feature has no integration test or any test's chain is inconsistent
  with the realization map, the integration test plan has coverage
  or traceability gaps.

### Area 4: Simulation Replacement Sequence with Concrete Re-test Triggers

PH-007 verifies that every simulation from PH-005 has been replaced
by a real implementation and that the correct tests were re-run after
each replacement. For each entry in the simulation_replacement_sequence,
PH-007 checks:

- Every SIM-* from PH-005 has a replacement entry
- replaced_at_step maps to a valid build_order step
- The build_order step at replaced_at_step builds the component that
  owns the contract the simulation covers
- integration_tests_to_rerun lists every integration test that used
  the replaced simulation

Replacement sequence structural requirements:

| Plan element | What PH-007 needs | What blocks PH-007 |
|---|---|---|
| simulation_ref | SIM-* from PH-005 simulations | SIM-* not in simulations or phantom |
| replaced_at_step | Step number in build_order | Step that does not exist or does not build the owning component |
| owning component consistency | Step's component_ref owns the simulation's contract | Mismatch -- simulation replaced at wrong step |
| integration_tests_to_rerun | Integration test IDs from integration_test_plan | Test IDs that do not exist in the plan |
| re-test completeness | Every integration test that referenced this SIM-* in scenarios_from | Missing re-test entries -- tests that used the simulation but are not re-run |
| replacement completeness | Every SIM-* from PH-005 has an entry | Missing SIM-* -- simulation never formally replaced |

Checks:

- Check: does the simulation_replacement_sequence contain exactly one
  entry for every SIM-* in the PH-005 simulations? PH-007 verifies
  replacement completeness by counting. A SIM-* with no replacement
  entry means PH-007 cannot verify that simulation was replaced by
  real code. A phantom replacement entry (SIM-* not in PH-005) is a
  reference error.
- Check: for each replacement entry, does the replaced_at_step
  reference a valid step number in the build_order? PH-007 uses this
  to verify when the replacement occurred. A step number outside the
  build_order range or referencing a non-existent step is an error.
- Check: for each replacement entry, does the build_order step at
  replaced_at_step build the component that owns the target side of
  the simulation's contract? PH-007 traces: SIM-* -> contract_ref
  (CTR-*) -> target_component (from interface contracts) -> CMP-*
  -> build_order step. If the step's component_ref does not match
  the target_component, the simulation is being replaced at the
  wrong step -- the component built at that step is not the one
  the simulation was standing in for.
- Check: for each replacement entry, does integration_tests_to_rerun
  list every integration test in the integration_test_plan whose
  scenarios_from includes the replaced SIM-*? PH-007 cross-references
  the replacement's re-test list against all integration tests that
  used the simulation as a test double. If an integration test used
  SIM-NNN in its scenarios_from but is not listed in
  integration_tests_to_rerun for SIM-NNN's replacement entry, that
  test was not re-run after the simulation was replaced -- its
  results may be stale.
- Check: for each replacement entry, do the integration_tests_to_rerun
  IDs actually exist in the integration_test_plan? PH-007 validates
  reference integrity. A re-test ID that does not match any
  integration test is a phantom reference.
- Check: is the replacement order consistent with the build_order?
  If SIM-A is replaced at step 3 and SIM-B at step 5, and SIM-B
  depends on SIM-A (SIM-B's precondition references state established
  by SIM-A's postcondition), then SIM-A must be replaced before
  SIM-B. PH-007 verifies that cross-simulation dependencies are
  respected in the replacement order. An inversion means SIM-B was
  re-tested while still depending on SIM-A's simulation output
  rather than real output.
- The test: could PH-007 walk the simulation_replacement_sequence
  in replaced_at_step order and at each entry confirm: (a) the SIM-*
  exists in PH-005, (b) the step builds the correct component,
  (c) all integration tests that used this SIM-* are listed in
  integration_tests_to_rerun, (d) those test IDs exist in the
  integration_test_plan, and (e) no dependent simulation was
  replaced out of order? If any entry fails this walk, the
  replacement sequence is not verifiable.

### Area 5: End-to-End Traceability from Requirements to Tests

PH-007 performs an end-to-end traceability verification that confirms
every requirement (RI-*) can be traced through the full methodology
chain to at least one test. The traceability chain is:

    RI-* -> FT-* -> AC-* -> CTR-* -> SIM-* -> build_step ->
    unit_test (or integration_test)

For each RI-* in the requirements inventory, PH-007 follows this
chain forward. For each unit test and integration test in the
implementation plan, PH-007 follows the chain backward. Both
directions must produce consistent results.

Traceability structural requirements:

| Chain link | What PH-007 needs | What blocks PH-007 |
|---|---|---|
| RI-* -> FT-* | Feature specification's source_refs | RI-* with no feature referencing it |
| FT-* -> AC-* | Feature specification's acceptance_criteria | FT-* with no acceptance criteria |
| AC-* -> CTR-* | Unit test plan's contract_ref for tests covering AC-* | AC-* with no test referencing it |
| CTR-* -> SIM-* | Simulation's contract_ref | CTR-* with no simulation covering it |
| SIM-* -> build_step | Replacement sequence's replaced_at_step | SIM-* with no replacement entry |
| build_step -> tests | Build step's component -> unit tests and integration tests | Component with no tests |

Checks:

- Check: for each RI-* in the requirements inventory, can PH-007
  trace forward to at least one FT-* in the feature specification
  that lists this RI-* in its source_refs? This is a PH-001 artifact
  check, but PH-007 re-validates it because a broken first link
  means the entire chain fails. If no FT-* references an RI-*, that
  requirement has no feature and therefore no tests.
- Check: for each AC-* in the feature specification, can PH-007
  trace forward to at least one unit_test_plan or
  integration_test_plan entry that lists this AC-* in its
  acceptance_criteria_refs or whose scenarios_from entries trace
  back to this AC-* through the SIM-* -> CTR-* -> interaction ->
  feature chain? This is the critical coverage link. An AC-* with
  no forward trace has no test proving it works.
- Check: for each unit test and integration test in the plan, can
  PH-007 trace backward through contract_ref or scenarios_from to
  a specific AC-*, then to FT-*, then to RI-*? A test with no
  backward trace is untethered -- it tests something, but PH-007
  cannot confirm what requirement it satisfies. Untethered tests
  are not harmful, but they indicate possible phantom implementations
  (code that does not trace to any requirement).
- Check: does the implementation plan's overall structure support
  bidirectional traversal? PH-007 needs to walk forward (RI-* to
  tests) and backward (tests to RI-*) without dead ends in either
  direction. A plan that supports forward but not backward traversal
  (or vice versa) forces PH-007 to perform manual cross-referencing
  that may miss gaps.
- Check: for RI-* entries with category "functional", does the
  traceability chain reach at least one integration test? Functional
  requirements describe system behavior that typically spans
  multiple components. A functional RI-* whose chain terminates at
  a unit test but never reaches an integration test may have
  insufficient verification scope.
- The test: could PH-007 produce a traceability matrix with rows =
  all RI-* requirements and columns = all tests (unit +
  integration), marking each cell where the full chain connects
  the requirement to the test, and find no empty rows for
  functional requirements? If any functional RI-* has an empty row,
  the implementation plan has a traceability gap.

## Your task

Perform these six steps in order:

1. **Simulate dependency-order verification.** Replay the build_order
   from step 1 to step N. At each step:
   - Does the component_ref map to a CMP-* in the solution design?
   - Are all its dependencies satisfied (built at prior step or
     covered by a SIM-* in simulations_used)?
   - Do the contracts_implemented entries actually belong to this
     component?
   - Are the simulations_used entries for components not yet built?
   - Note where the build order violates the dependency graph, where
     component references are inconsistent with the solution design,
     or where simulations_used entries are stale (for already-built
     components).

2. **Simulate unit test coverage verification.** Walk the
   unit_test_plan and cross-reference against the feature
   specification and interface contracts.
   - Does every AC-* have at least one covering test?
   - Does every CTR-* operation have at least one covering test?
   - Do tests trace to specific SIM-*/SCN-* scenarios?
   - Do error-handling AC-* criteria map to error-path tests?
   - Do boundary AC-* criteria map to edge-case tests?
   - Note where coverage gaps exist, where test provenance is
     missing, or where criterion type does not match test type.

3. **Simulate integration test coverage verification.** Walk the
   integration_test_plan and cross-reference against the
   feature_realization_map and simulations.
   - Does every FT-* have at least one integration test?
   - Does each test's component chain match the feature's
     interaction sequence?
   - Does each test's contract chain match the feature's contracts?
   - Do scenarios_from entries map to the correct SIM-*/SCN-*?
   - Are branching flows covered with one test per branch?
   - Note where features lack integration tests, where component
     or contract chains are inconsistent, or where branches are
     untested.

4. **Simulate replacement sequence verification.** Walk the
   simulation_replacement_sequence and cross-reference against the
   build_order, interface contracts, and integration_test_plan.
   - Does every SIM-* from PH-005 have a replacement entry?
   - Does each replaced_at_step build the correct component?
   - Does each integration_tests_to_rerun list include all tests
     that used the replaced simulation?
   - Are cross-simulation dependencies respected in replacement
     order?
   - Note where simulations are unreplaced, where replacements
     occur at wrong steps, where re-test lists are incomplete, or
     where replacement order violates dependencies.

5. **Simulate end-to-end traceability verification.** Walk the full
   chain from RI-* to tests.
   - For each RI-*, can you trace forward to at least one test?
   - For each test, can you trace backward to at least one RI-*?
   - Are there functional RI-* entries that reach unit tests but
     not integration tests?
   - Are there tests with no backward trace (untethered)?
   - Note where the chain breaks, where bidirectional traversal
     fails, or where functional requirements lack integration
     test coverage.

6. **Produce a structured YAML critique.** Synthesize your findings
   from steps 1-5 into the output format below.

## Output format

Your entire response must be a single YAML document (no commentary
outside the YAML). Use this exact structure:

    phase_evaluated: PH-006-incremental-implementation
    findings:
      - severity: blocking | warning | info
        location: "build_step N or UT-NNN or IT-NNN or SRS-NNN or <section>"
        downstream_phase: "PH-007"
        issue: |
          Description of the problem, stated in terms of what PH-007
          will be unable to do because of this gap.
        recommendation: |
          What should change. Be specific: not "improve coverage" but
          "add a unit_test_plan entry for CTR-002 operation
          assign_task with acceptance_criteria_refs: [AC-001-03] and
          scenario derived from SIM-002 SCN-002 so PH-007 can verify
          the assignment acceptance criterion."
      - ...
    build_order_verification:
      - step: N
        component_ref: "CMP-NNN"
        component_exists_in_solution_design: true | false
        contracts_implemented:
          - contract: "CTR-NNN"
            belongs_to_component: true | false
            notes: "what PH-007 can or cannot verify"
          - ...
        simulations_used:
          - simulation: "SIM-NNN"
            component_not_yet_built: true | false
            contract_ref_valid: true | false
            notes: "what PH-007 can or cannot verify"
          - ...
        dependencies_satisfied:
          - dependency: "CMP-NNN"
            satisfied_by: "built_at_step N | simulated_by SIM-NNN | unsatisfied"
          - ...
        all_dependencies_met: true | false
        step_verifiable: true | false
        notes: |
          What PH-007 can or cannot verify at this step.
      - ...
      overall_build_order_valid: true | false
      components_missing_from_build_order: ["CMP-NNN", ...]
      components_duplicated_in_build_order: ["CMP-NNN", ...]
    unit_test_coverage:
      acceptance_criteria_coverage:
        - criterion: "AC-NNN-NN"
          feature: "FT-NNN"
          covered_by_tests: ["UT-NNN", ...]
          criterion_type: happy_path | error_handling | boundary
          test_type_matches: true | false
          scenario_provenance: "SIM-NNN/SCN-NNN or missing"
          notes: |
            What PH-007 can or cannot verify for this criterion.
        - ...
      contract_operation_coverage:
        - contract: "CTR-NNN"
          operation: "operation_name"
          covered_by_tests: ["UT-NNN", ...]
          happy_path_covered: true | false
          error_paths_covered: true | false
          error_paths_missing: ["error_type_name", ...]
          notes: |
            What PH-007 can or cannot verify for this operation.
        - ...
      uncovered_acceptance_criteria: ["AC-NNN-NN", ...]
      uncovered_contract_operations: ["CTR-NNN/operation", ...]
      tests_without_scenario_provenance: ["UT-NNN", ...]
    integration_test_coverage:
      feature_coverage:
        - feature: "FT-NNN"
          covered_by_tests: ["IT-NNN", ...]
          interaction_sequence: ["INT-NNN", ...]
          components_in_sequence: ["CMP-NNN", ...]
          test_component_chain_matches: true | false
          contracts_in_sequence: ["CTR-NNN", ...]
          test_contract_chain_matches: true | false
          scenarios_from_valid: true | false
          branch_points:
            - branch_point: "description"
              branches_covered: N
              branches_expected: N
              notes: "what branches PH-007 can or cannot verify"
            - ...
          feature_fully_tested: true | false
          notes: |
            What PH-007 can or cannot verify for this feature.
        - ...
      uncovered_features: ["FT-NNN", ...]
      tests_with_chain_mismatches: ["IT-NNN", ...]
    replacement_sequence_verification:
      - simulation: "SIM-NNN"
        contract_ref: "CTR-NNN"
        target_component: "CMP-NNN"
        replacement_entry_exists: true | false
        replaced_at_step: N
        step_builds_correct_component: true | false
        traceability_chain:
          sim_to_ctr: true | false
          ctr_to_component: true | false
          component_to_build_step: true | false
        integration_tests_using_simulation: ["IT-NNN", ...]
        integration_tests_in_rerun_list: ["IT-NNN", ...]
        rerun_list_complete: true | false
        rerun_list_has_phantom_entries: true | false
        dependent_simulations: ["SIM-NNN", ...]
        replacement_order_respects_dependencies: true | false
        replacement_verifiable: true | false
        notes: |
          What PH-007 can or cannot verify for this replacement.
      - ...
      unreplaced_simulations: ["SIM-NNN", ...]
      phantom_replacement_entries: ["SIM-NNN", ...]
      replacement_order_inversions:
        - earlier_sim: "SIM-NNN"
          later_sim: "SIM-NNN"
          dependency_direction: |
            How PH-007 detected the dependency and why the order
            is inverted.
        - ...
    end_to_end_traceability:
      requirement_forward_trace:
        - requirement: "RI-NNN"
          category: functional | non_functional | constraint
          feature_found: true | false
          feature_ref: "FT-NNN"
          acceptance_criteria_found: true | false
          criteria_refs: ["AC-NNN-NN", ...]
          unit_tests_reached: ["UT-NNN", ...]
          integration_tests_reached: ["IT-NNN", ...]
          chain_complete: true | false
          functional_has_integration_test: true | false | n/a
          notes: |
            What PH-007 can or cannot trace for this requirement.
        - ...
      test_backward_trace:
        - test: "UT-NNN or IT-NNN"
          test_type: unit | integration
          traces_to_criteria: ["AC-NNN-NN", ...]
          traces_to_features: ["FT-NNN", ...]
          traces_to_requirements: ["RI-NNN", ...]
          chain_complete: true | false
          notes: |
            What PH-007 can or cannot trace backward from this test.
        - ...
      untethered_tests: ["UT-NNN or IT-NNN", ...]
      requirements_without_tests: ["RI-NNN", ...]
      functional_requirements_without_integration_tests: ["RI-NNN", ...]
    overall_usability: high | medium | low
    summary: |
      Brief 2-3 sentence summary. State the most important finding
      first.

## Severity definitions

- blocking: PH-007 cannot proceed without resolving this. Example:
  a CMP-* from the solution design has no step in the build_order,
  so PH-007 cannot verify that component was implemented. Example:
  an AC-* acceptance criterion has no unit test or integration test
  entry, so PH-007 cannot verify that criterion is satisfied.
  Example: a SIM-* from PH-005 has no replacement entry in the
  simulation_replacement_sequence, so PH-007 cannot verify the
  simulation was replaced by real code. Example: a build_order step
  has an unsatisfied dependency (neither built nor simulated), so
  PH-007 cannot verify the component functions at that step.
  Example: a replacement entry's integration_tests_to_rerun omits
  an integration test that used the replaced simulation, so PH-007
  cannot verify the test was re-run with real code. Example: a
  functional RI-* cannot be traced through the full chain to any
  test, so PH-007 cannot verify that requirement is satisfied.
- warning: PH-007 can proceed but will likely produce imprecise or
  incomplete verification results. Example: a unit test entry
  references the correct AC-* and CTR-* but has no scenario
  provenance (no SIM-*/SCN-* reference), so PH-007 can verify
  coverage exists but cannot confirm the test case derives from
  validated simulation data. Example: an integration test covers a
  feature flow but its component chain includes one extra CMP-* not
  in the feature_realization_map's interaction sequence, so PH-007
  can verify the flow is tested but the test scope is broader than
  specified. Example: the replacement sequence replaces a SIM-* at
  the correct step but the cross-simulation dependency detection
  requires terminology inference (one postcondition says "task
  created" and the dependency's precondition says "work item
  exists"), so PH-007 can likely verify the order but may misjudge
  dependencies.
- info: Worth noting but will not impede verification. Example: the
  build_order is a valid topological sort but not the optimal one
  (fewer simulations_used would be needed with a different ordering).
  Example: an integration test covers a feature with additional
  assertions beyond what the acceptance criteria require. Example:
  the traceability chain for a non-functional RI-* terminates at
  unit tests only, which is appropriate for non-functional
  requirements that do not span components.
```
