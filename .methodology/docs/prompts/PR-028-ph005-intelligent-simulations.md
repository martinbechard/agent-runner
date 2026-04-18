### Module

intelligent-simulations

## Prompt 1: Produce Intelligent Simulations

### Required Files

docs/design/interface-contracts.yaml
docs/features/feature-specification.yaml

### Include Files

docs/design/interface-contracts.yaml
docs/features/feature-specification.yaml

### Checks Files

docs/simulations/simulation-definitions.yaml

### Deterministic Validation

.methodology/src/cli/methodology_runner/phase_5_validation.py
--contracts
docs/design/interface-contracts.yaml
--feature-spec
docs/features/feature-specification.yaml
--simulations
docs/simulations/simulation-definitions.yaml

### Generation Prompt

As a simulation designer, you must derive contract-faithful simulations from
the interface contracts and write them to
docs/simulations/simulation-definitions.yaml.

The interface contracts are provided above in <INTERFACE_CONTRACTS>.
The feature specification is provided above in <FEATURE_SPECIFICATION>.

Module-local generator context:
Embedded directives for this step:

- Create at least one meaningful simulation per contract and include happy,
  error, and edge coverage.
- Derive scenarios, expected outputs, and assertions from the contract
  surface, not from hidden implementation detail.
- Use synthetic setup only when it mirrors a declared contract condition and
  does not smuggle in internals.
- Assertions must verify meaningful contract semantics, not only status flags
  or output presence.

Phase purpose:
- Define at least one SIM-* simulation for every CTR-* contract.
- Provide happy-path, error-path, and edge-case scenarios.
- Encode explicit expected outcomes and validation rules.
- Prevent leakage of implementation-only knowledge into the simulations.

Important interpretation:
- This phase is an elaboration layer over contracts, not over implementation.
- Simulations must be derivable from contract behavior, not hidden system internals.
- You may invent concrete sample data and scenario detail if it is contract-faithful.
- Treat scenarios as contract-exercising examples, not implementation guesses.
- When a contract declares an error type or branch condition that upstream
  artifacts do not fully operationalize, you may introduce synthetic
  contract-surface setup fields to exercise that branch.
- Those synthetic setup fields must mirror the contract's own language, such as
  a declared observed process result or a declared timeout condition, and must
  not prescribe implementation internals.
- When a contract exposes meaningful request, response, error, or invariant
  fields, assertions should materially verify those semantics rather than only
  asserting a generic presence flag.
- Do not invent entrypoint filenames, module names, option syntax, or other
  invocation details unless the contract itself names them.
- Do not forbid user-facing command shapes that the contract explicitly permits;
  forbid only implementation-internal detail that is not part of the contract.

Output schema to satisfy:
simulations:
  - id: "SIM-NNN"
    contract_ref: "CTR-NNN"
    description: "What this simulation verifies"
    scenario_bank:
      - name: "scenario name"
        type: "happy_path"
        input: {}
        expected_output: {}
        assertions:
          - field: "path.to.field"
            operator: "equals"
            value: "expected"
    llm_adjuster:
      temperature: 0.0
      system_prompt_addendum: "..."
      forbidden_patterns: ["..."]
    validation_rules:
      - rule: "..."
        severity: "blocking"

Acceptance requirements:
- The file must be valid YAML parseable by a standard YAML parser.
- The top-level key must be exactly:
  simulations
- Every CTR-* contract must have at least one SIM-* simulation with a matching
  contract_ref.
- Every simulation must contain:
  id
  contract_ref
  description
  scenario_bank
  llm_adjuster
  validation_rules
- Every simulation must include at least one happy_path, one error_path, and
  one edge_case scenario.
- Every scenario must define:
  name
  type
  input
  expected_output
  assertions
- assertions must be non-empty and must check meaningful response content, not
  only trivial status flags.
- Where the contract exposes multiple meaningful fields, at least one scenario
  for that contract should assert more than a single boolean or presence flag.
- Error-path scenarios should materially cover every declared contract error
  type whenever the contract defines multiple error types.
- When a rejection or failure response contractually requires response fields to
  be blanked or normalized, assertions must verify those response-shape fields,
  not only the named error branch.
- When one declared error branch has materially distinct subconditions, include
  scenarios that exercise those distinct subconditions when they would change
  downstream verification behavior.
- expected_output and assertions must be derivable from the contract, not from
  hidden implementation details.
- For declared error branches, expected_output and assertions may also be
  derived from synthetic contract-surface setup that explicitly represents the
  declared failure condition.
- Do not create any files other than docs/simulations/simulation-definitions.yaml.
- Write the full file contents to docs/simulations/simulation-definitions.yaml.

### Validation Prompt

Review the current simulation definitions against <INTERFACE_CONTRACTS> and
<FEATURE_SPECIFICATION>.
The current artifact is provided above in <SIMULATION_DEFINITIONS>.

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Module-local judge context:

- Review for weak assertions, unrealistic scenarios, implementation leakage,
  missing error coverage, contract underuse, and unsupported synthetic setup.

Your job is to decide whether the generated simulation definitions are phase-ready.

Review method:
- Iterate through simulations in SIM-* order.
- For each simulation, review its contract_ref, scenario_bank,
  llm_adjuster, and validation_rules together.
- Within each simulation, iterate through scenarios in authored order.
- Before flagging coverage, assertions, or scenario detail as missing, check
  whether that same downstream-actionable contract meaning is already covered
  elsewhere in the simulation set.
- Only flag it as missing if the allegedly missing content would change
  downstream verification or implementation planning.

Focus your semantic review on these failure modes:

1. Validation gaps:
   - Flag scenarios whose assertions are too trivial to verify the contract's
     stated request/response/error or invariant semantics.
2. Scenario realism:
   - Flag scenarios that violate the contract's stated constraints without the
     contract itself permitting that input.
3. LLM leakage:
   - Flag expected outputs or rules that rely on implementation knowledge not
     contained in the contract.
4. Missing error coverage:
   - Flag contracts whose declared error types are not exercised by error_path scenarios.
6. Contract-underuse:
   - Flag simulation sets that only nominally cover a contract while ignoring
     important exposed fields or invariants the contract makes available.
7. Unsupported synthetic setup:
   - Flag synthetic scenario setup only when it introduces implementation
     internals or contradicts the declared contract branch it is meant to
     exercise.
5. Uncovered contracts:
   - Flag contracts that are only nominally covered but not materially exercised.

Review instructions:
- Use the deterministic validation report as authoritative for structural
  checks, contract coverage, scenario type coverage, and basic assertion presence.
- Treat this phase as an allowed elaboration layer over contracts only.
- Only ask for a change when the current simulations are wrong, contradictory,
  materially unsupported, or would materially affect downstream implementation
  planning or verification.
- Do not reject a scenario merely because it uses an abstract placeholder for a
  contract-permitted command shape when the upstream contract does not specify
  the concrete tokens.
- Do not reject a scenario merely because it uses synthetic contract-surface
  setup to exercise a declared error branch, as long as that setup mirrors the
  contract's own error condition and avoids implementation internals.
- Do not require implementation-specific filenames, module names, or option
  syntax unless the contract itself explicitly requires them.
- Do not request wording polish or alternative sample values unless the current
  choices are misleading or contract-inconsistent.
- If you find issues, cite exact SIM-* / CTR-* IDs.
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary
- Use VERDICT: pass only if the artifact is phase-ready with no material
  contract-coverage, realism, or leakage defects.
- Use VERDICT: revise if the artifact can be corrected within this same file.
- Use VERDICT: escalate only if the upstream contracts are too ambiguous to
  support stable simulations.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
