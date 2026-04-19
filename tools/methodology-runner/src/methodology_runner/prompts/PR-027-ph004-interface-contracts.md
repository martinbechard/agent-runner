### Module

interface-contracts

## Prompt 1: Produce Interface Contracts

### Required Files

docs/design/solution-design.yaml
docs/features/feature-specification.yaml

### Deterministic Validation

python-module:methodology_runner.phase_4_validation
--solution-design
docs/design/solution-design.yaml
--feature-spec
docs/features/feature-specification.yaml
--contracts
docs/design/interface-contracts.yaml

### Generation Prompt

As an interface designer, you must turn the solution design interactions into
concrete contracts and write them to docs/design/interface-contracts.yaml.

Context:
<SOLUTION_DESIGN>
{{INCLUDE:docs/design/solution-design.yaml}}
</SOLUTION_DESIGN>
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>

Module-local generator context:
Embedded directives for this step:

- Write one or more concrete contracts for every real upstream interaction.
- Define request, response, and error schemas tightly enough that simulation
  and implementation can proceed without filling obvious type holes.
- Make behavioral expectations explicit with preconditions, postconditions,
  and invariants.
- Keep contract language at the interface boundary. Do not prescribe hidden
  implementation internals.

Phase purpose:
- Define explicit contracts for each INT-* interaction.
- Specify concrete operations, request and response schemas, and error types.
- Provide behavioral specs that simulations and implementation can verify.

Important interpretation:
- This phase is an elaboration layer.
- You may invent contract detail when it is non-contradictory and directly or
  indirectly supports the solution design and feature spec.
- Do not leave type holes or vague placeholders.
- Do not introduce operations or error behaviors that no longer serve the
  interaction being modeled.

Output schema to satisfy:
contracts:
  - id: "CTR-NNN"
    name: "Contract name"
    interaction_ref: "INT-NNN"
    source_component: "CMP-NNN"
    target_component: "CMP-NNN"
    operations:
      - name: "operation name"
        description: "What this operation does"
        request_schema:
          fields:
            - name: "field_name"
              type: "string"
              required: true
              constraints: "..."
        response_schema:
          fields: []
        error_types:
          - name: "error_name"
            condition: "When this occurs"
            http_status: 400
    behavioral_specs:
      - precondition: "..."
        postcondition: "..."
        invariant: "..."

Acceptance requirements:
- The file must be valid YAML parseable by a standard YAML parser.
- The top-level key must be exactly:
  contracts
- Every INT-* interaction in docs/design/solution-design.yaml must have at
  least one CTR-* contract with a matching interaction_ref.
- Every contract must contain:
  id
  name
  interaction_ref
  source_component
  target_component
  operations
  behavioral_specs
- Every operation must contain:
  name
  description
  request_schema
  response_schema
  error_types
- request_schema.fields and response_schema.fields must be explicit field lists.
- Do not use type holes such as object, any, or unknown.
- Every operation must define at least one error type unless the interaction is
  truly infallible and the contract makes that obvious.
- Every contract must contain at least one behavioral_specs entry with:
  precondition
  postcondition
  invariant
- Do not create any files other than docs/design/interface-contracts.yaml.
- Write the full file contents to docs/design/interface-contracts.yaml.

### Validation Prompt

Review the current interface contracts against <SOLUTION_DESIGN> and
<FEATURE_SPECIFICATION>.

Context:
<SOLUTION_DESIGN>
{{INCLUDE:docs/design/solution-design.yaml}}
</SOLUTION_DESIGN>
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>
<INTERFACE_CONTRACTS>
{{RUNTIME_INCLUDE:docs/design/interface-contracts.yaml}}
</INTERFACE_CONTRACTS>

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Module-local judge context:

- Review for missing contracts, type holes, weak or missing error models,
  cross-contract inconsistency, and behavioral specs too weak to drive
  simulation.

Your job is to decide whether the generated interface contracts are phase-ready.

Review method:
- Iterate through contracts in CTR-* order.
- For each contract, review interaction_ref, component refs, operations,
  schemas, error_types, and behavioral_specs together.
- Within each contract, iterate through operations in authored order.
- Before flagging a contract, operation, schema field, or behavioral rule as
  missing, check whether that same downstream-actionable meaning is already
  covered elsewhere in the contract set.
- Only flag it as missing if the allegedly missing content would change
  downstream simulations or implementation.

Focus your semantic review on these failure modes:

1. Type holes:
   - Flag vague schemas or placeholders that would block simulation or
     implementation.
2. Missing contracts:
   - Flag any interaction that is still materially uncovered even if a thin
     placeholder contract exists.
3. Error gaps:
   - Flag operations whose likely failure modes are omitted in a way that would
     materially affect downstream simulation or implementation.
4. Cross-contract inconsistency:
   - Flag materially inconsistent schemas for the same conceptual payload.
5. Behavioral gaps:
   - Flag contracts whose behavioral specs are too weak to support simulation.

Review instructions:
- Use the deterministic validation report as authoritative for structural
  checks, interaction coverage, and schema-hole detection.
- Treat this phase as an allowed elaboration layer.
- Only ask for a change when the current contract set is wrong, contradictory,
  materially unsupported, or would materially affect downstream simulation or
  implementation.
- Do not request wording polish or alternate field names unless the current
  choice is actually misleading or inconsistent.
- If you find issues, cite exact CTR-* / INT-* / CMP-* / FT-* IDs.
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary
- Use VERDICT: pass only if the artifact is phase-ready with no material
  coverage, schema, error-model, or behavioral-spec defects.
- Use VERDICT: revise if the artifact can be corrected within this same file.
- Use VERDICT: escalate only if the upstream artifacts are too ambiguous or
  contradictory to produce stable contracts.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
