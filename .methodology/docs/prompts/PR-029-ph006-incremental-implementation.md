### Module

incremental-implementation

## Prompt 1: Produce Incremental Implementation Plan

### Required Files

docs/design/interface-contracts.yaml
docs/simulations/simulation-definitions.yaml
docs/features/feature-specification.yaml
docs/design/solution-design.yaml

### Include Files

docs/design/interface-contracts.yaml
docs/simulations/simulation-definitions.yaml
docs/features/feature-specification.yaml
docs/design/solution-design.yaml

### Checks Files

docs/implementation/implementation-plan.yaml

### Deterministic Validation

.methodology/src/cli/methodology_runner/phase_6_validation.py
--contracts
docs/design/interface-contracts.yaml
--simulations
docs/simulations/simulation-definitions.yaml
--feature-spec
docs/features/feature-specification.yaml
--solution-design
docs/design/solution-design.yaml
--implementation-plan
docs/implementation/implementation-plan.yaml

### Generation Prompt

As an implementation planner, you must build a dependency-respecting
implementation plan from the design artifacts and write it to
docs/implementation/implementation-plan.yaml.

The interface contracts are provided above in <INTERFACE_CONTRACTS>.
The simulations are provided above in <SIMULATION_DEFINITIONS>.
The feature specification is provided above in <FEATURE_SPECIFICATION>.
The solution design is provided above in <SOLUTION_DESIGN>.

Module-local generator context:
Embedded directives for this step:

- Build in dependency-respecting order unless a declared simulation bridges
  the gap temporarily.
- Plan tests so each unit or integration test materially verifies linked
  acceptance criteria or contracts, not just names them.
- Use simulations before replacement, then state exactly when each simulation
  is retired and which integration tests rerun.
- Keep sequencing detail grounded in upstream contracts, simulations,
  features, and component dependencies.

Phase purpose:
- Define a dependency-respecting build order.
- Map unit tests and integration tests to acceptance criteria and contracts.
- Specify how simulations are used before replacement.
- Define when each simulation is replaced and which tests must rerun.

Output schema to satisfy:
build_order:
  - step: 1
    component_ref: "CMP-NNN"
    rationale: "Why this component is built here"
    contracts_implemented: ["CTR-NNN", "..."]
    simulations_used: ["SIM-NNN", "..."]
unit_test_plan:
  - component_ref: "CMP-NNN"
    tests:
      - name: "test name"
        description: "What this test verifies"
        acceptance_criteria_refs: ["AC-NNN-NN", "..."]
        contract_ref: "CTR-NNN"
integration_test_plan:
  - name: "integration test name"
    components_involved: ["CMP-NNN", "..."]
    contracts_exercised: ["CTR-NNN", "..."]
    scenarios_from: ["SIM-NNN", "..."]
simulation_replacement_sequence:
  - simulation_ref: "SIM-NNN"
    replaced_at_step: 1
    integration_tests_to_rerun: ["test-name", "..."]

Acceptance requirements:
- The file must be valid YAML parseable by a standard YAML parser.
- The top-level keys must appear exactly in this order:
  build_order
  unit_test_plan
  integration_test_plan
  simulation_replacement_sequence
- Every component from docs/design/solution-design.yaml must appear in build_order.
- The build order must respect component dependencies unless a referenced
  dependency is explicitly simulated in a prior step.
- Every CTR-* contract must appear in at least one build step's contracts_implemented.
- Every AC-* from docs/features/feature-specification.yaml must appear in at
  least one unit or integration test entry.
- Every SIM-* simulation must appear in simulation_replacement_sequence.
- Every simulation replacement entry must specify which integration tests rerun.
- Do not create any files other than docs/implementation/implementation-plan.yaml.
- Write the full file contents to docs/implementation/implementation-plan.yaml.

### Validation Prompt

Review the current implementation plan against <INTERFACE_CONTRACTS>,
<SIMULATION_DEFINITIONS>, <FEATURE_SPECIFICATION>, and <SOLUTION_DESIGN>.
The current artifact is provided above in <IMPLEMENTATION_PLAN>.

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Module-local judge context:

- Review for ordering violations, thin test plans, completion gaps,
  simulation-retirement gaps, and unsupported sequencing detail.

Your job is to decide whether the generated implementation plan is phase-ready.

Review method:
- Iterate through build_order entries in step order.
- Then iterate through unit_test_plan entries by component_ref.
- Then iterate through integration_test_plan entries in authored order.
- Then iterate through simulation_replacement_sequence entries in SIM-* order.
- Before flagging a plan element as missing, check whether that same
  downstream-actionable sequencing or verification meaning is already covered
  elsewhere in the plan.
- Only flag it as missing if the allegedly missing content would change
  downstream implementation execution or verification work.

Focus your semantic review on these failure modes:

1. Ordering violations:
   - Flag build steps that require unavailable dependencies or unrealistic simulation usage.
2. Test insufficiency:
   - Flag thin test plans that nominally reference ACs or contracts without
     materially verifying them.
3. Completion gaps:
   - Flag components or contracts that are only nominally mentioned and not
     meaningfully planned.
4. Simulation retirement gaps:
   - Flag replacement steps that do not actually reconnect to the affected
     integration tests.
5. Unsupported sequencing detail:
   - Flag sequencing assumptions that are not grounded in the upstream design or contracts.

Review instructions:
- Use the deterministic validation report as authoritative for structural
  checks, dependency-order checks, and coverage counts.
- Treat this phase as a planning layer. It may add sequencing and test-planning
  detail, but it must remain grounded in the upstream artifacts.
- Only ask for a change when the current plan is wrong, contradictory,
  materially unsupported, or would materially affect downstream implementation
  execution.
- Do not request wording polish or different naming unless the current wording
  is misleading or materially consequential.
- If you find issues, cite exact CMP-* / CTR-* / SIM-* / AC-* IDs.
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary
- Use VERDICT: pass only if the artifact is phase-ready with no material
  ordering, traceability, or simulation-replacement defects.
- Use VERDICT: revise if the artifact can be corrected within this same file.
- Use VERDICT: escalate only if the upstream artifacts are too ambiguous to
  support a stable implementation plan.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
