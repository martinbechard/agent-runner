# Integration Agent: PH-004 Interface Contracts

This is a prompt-runner input file with a single prompt and no validator.
The agent reads PH-004's output artifact (interface contracts YAML), the
upstream PH-003 artifact (solution design YAML), the upstream PH-002
artifact (stack manifest YAML), the upstream PH-001 artifact (feature
specification YAML), the upstream PH-000 artifact (requirements inventory
YAML), and the original raw requirements, then evaluates whether the
interface contracts contain the semantic content that PH-005 (Intelligent
Simulations) will need to produce realistic simulations.

**How to run:**

    prompt-runner run \
      docs/prompts/integration-agent-PH-004-interface-contracts.md \
      --project-dir <path-to-completed-PH-004-workspace>

The run executes the single critic prompt, skips the judge (no validator),
produces a YAML critique in the run output, and exits with verdict pass.

**Rationale:** see
`docs/superpowers/specs/2026-04-09-skill-pack-and-interactive-harness-notes.md`
section 6 for the full design of integration agents.

---

## Prompt 1: PH-004 integration critique

```
You are a downstream-consumer simulator for PH-004 Interface Contracts
output. Your job is to read the interface contracts artifact, the
upstream solution design, the upstream stack manifest, the upstream
feature specification, the upstream requirements inventory, and the
original raw requirements, then evaluate whether the interface contracts
contain the semantic content that PH-005 (Intelligent Simulations) will
need to produce realistic simulations.

This is NOT a schema check or a format lint. Assume the YAML parses,
the IDs are well-formed, and the contract-review judge has already
passed this artifact for internal consistency (no type holes, no error
gaps, no cross-contract inconsistency, no missing contracts, no
behavioral gaps). You are checking whether the CONTENT is usable by
PH-005.

## What to read

Read these six files from the workspace:

1. The interface contracts YAML at
   {workspace}/docs/design/interface-contracts.yaml
2. The solution design YAML at
   {workspace}/docs/design/solution-design.yaml
3. The stack manifest YAML at
   {workspace}/docs/architecture/stack-manifest.yaml
4. The feature specification YAML at
   {workspace}/docs/features/feature-specification.yaml
5. The requirements inventory YAML at
   {workspace}/docs/requirements/requirements-inventory.yaml
6. The original raw requirements document at
   {workspace}/docs/requirements/raw-requirements.md

You need all six: the interface contracts (structured output of PH-004),
the solution design (upstream PH-003 output that PH-004 consumed), the
stack manifest (upstream PH-002 output), the feature specification
(upstream PH-001 output), the requirements inventory (upstream PH-000
output), and the raw requirements (the original source). Comparing them
lets you catch cases where the contracts lost information needed by the
simulation author, or where contract abstraction obscured signals that
PH-005 will need to produce realistic test data and meaningful
assertions.

## What PH-005 (Intelligent Simulations) needs

PH-005 constructs simulation scenarios for every contract. Each
simulation must: generate realistic inputs that exercise the contract,
predict expected outputs for success paths, trigger each error path
with crafted inputs, assert preconditions hold before invocation,
verify postconditions hold after success, and confirm invariants are
preserved. For PH-005 to do its job, the interface contracts must
provide sufficient content in five areas.

### Area 1: Schema Precision for Realistic Input Generation

PH-005 must generate realistic test data for every field in every
request_schema. The simulation author reads each field's type,
constraints, and format annotations to construct inputs that exercise
meaningful code paths -- not random data that happens to parse.

Type precision requirements for simulation:

| Type form | What PH-005 can generate | What PH-005 cannot generate |
|-----------|-------------------------|---------------------------|
| string(format: uuid) | A valid UUID string | -- |
| string(format: email) | A valid email address | -- |
| string(min_length: 1, max_length: 200) | Strings at boundary lengths (1, 200) and typical lengths | -- |
| enum[open, assigned, completed] | One value per scenario; exhaustive coverage | -- |
| integer(min: 1, max: 100) | Boundary values (1, 100), mid-range, and out-of-range | -- |
| string | Any string, no meaningful boundaries to test | Boundary values, format violations |
| ref(TaskSummary) | A populated struct if TaskSummary fields are precise | Fields if TaskSummary has type holes |

Checks:

- Check: for each field in every request_schema, does the type carry
  enough precision that PH-005 can derive BOTH a valid value AND a
  boundary/invalid value? string(format: uuid) lets PH-005 generate
  both a valid UUID and a malformed string. Bare string does not --
  PH-005 cannot determine what constitutes "invalid" without knowing
  the format. The contract-review judge ensures no bare 'object' or
  'any' exists, but a bare 'string' on a field that holds structured
  data (e.g., a date, a phone number, a postal code) is a precision
  gap for simulation even though it passes the Type Hole Test.
- Check: for each field with constraints, are the constraints
  expressed as machine-parseable bounds (min, max, min_length,
  max_length, pattern, allowed values) rather than prose? A
  constraint that says "Must be a valid identifier" is not actionable
  for a data generator. A constraint that says "string(pattern:
  ^[A-Z]{2}-[0-9]{4}$)" is directly usable.
- Check: for optional fields, does the constraint text specify the
  default behavior when the field is absent? PH-005 must generate
  scenarios both WITH and WITHOUT optional fields. If the behavior
  when an optional field is omitted is unspecified, PH-005 cannot
  predict the expected output for the "field absent" scenario.
- Check: for fields typed as enum[...], is the enum exhaustive? If
  the enum represents a status lifecycle (e.g., open -> assigned ->
  completed -> archived), PH-005 needs every valid value to generate
  scenarios that exercise each state transition. A partial enum
  forces PH-005 to guess missing values.
- The test: for each request_schema, could PH-005 write a data
  generator function that produces: one valid input, one input at
  each boundary, and one invalid input per field? If PH-005 would
  need to consult the solution design, feature specification, or raw
  requirements to determine what constitutes "valid" or "boundary"
  for a field, the schema is under-constrained for simulation.

### Area 2: Response Schema Completeness for Output Prediction

PH-005 must predict the expected output for each simulation scenario.
After sending a crafted input, the simulation asserts that the
response matches expected field values. For output prediction to work,
response_schemas must be precise enough that PH-005 can construct an
expected response from the input and the behavioral spec.

Checks:

- Check: for each field in every response_schema, is the type
  precise enough that PH-005 can predict its value given a known
  input? If the request sends a task_id and the response returns a
  ref(TaskSummary), PH-005 needs TaskSummary's fields to be fully
  typed so it can predict which fields are echoed from the request,
  which are server-generated (e.g., created_at), and which are
  derived from state.
- Check: for server-generated fields (IDs, timestamps, computed
  values), does the type or constraint indicate HOW the value is
  generated? A response field "notification_id: string(format: uuid)"
  tells PH-005 the value is server-generated and unpredictable --
  the simulation should assert existence and format, not exact value.
  A response field "status: enum[queued, rejected]" tells PH-005 the
  value depends on business logic -- the simulation should assert
  the correct status given the input. If the contract does not
  distinguish generated fields from deterministic fields, PH-005
  cannot write correct assertions.
- Check: for list-typed response fields, do the constraints indicate
  expected cardinality? If an operation returns
  "tasks: list[ref(TaskSummary)]", PH-005 needs to know: is the list
  empty when no tasks match? Is there a maximum length? Does ordering
  matter? Without cardinality hints, PH-005 cannot assert whether an
  empty list is a correct response or an error symptom.
- Check: do response schemas reference the SAME shared types as
  request schemas where data flows through? If the request sends a
  ref(TaskInput) and the response returns a ref(TaskSummary), and
  TaskSummary includes fields from TaskInput (e.g., title, assignee),
  PH-005 can assert that response.title == request.title. If request
  and response use different inline definitions for the same entity,
  PH-005 cannot construct flow-through assertions.
- The test: for each operation, could PH-005 write a response
  assertion function that checks: (a) server-generated fields exist
  with correct format, (b) echoed fields match the request,
  (c) derived fields match expected business logic? If PH-005 cannot
  distinguish these three categories from the contract alone, the
  response schema is insufficient for output prediction.

### Area 3: Error Type Specificity for Error-Path Scenario Construction

PH-005 must build a simulation scenario for EVERY error_type in every
operation. Each error-path scenario consists of: an input crafted to
trigger exactly that error, and an assertion that the correct error
type is returned (not a different error). For this to work, each
error_type's condition must be expressible as an input configuration.

Checks:

- Check: for each error_type, can PH-005 construct an input that
  triggers THIS error and ONLY this error? The condition must be
  specific enough that PH-005 can craft the triggering input. A
  condition that says "task_id is missing or not a valid UUID" tells
  PH-005 exactly two scenarios: omit task_id, or send a malformed
  task_id. A condition that says "input is invalid" does not tell
  PH-005 WHICH field to make invalid or HOW.
- Check: for each error_type, can PH-005 distinguish this error
  from every OTHER error on the same operation? If two error_types
  have overlapping conditions (e.g., "invalid input" and "missing
  required field"), PH-005 cannot predict which error a given input
  will trigger. Each error condition must identify a non-overlapping
  trigger.
- Check: for error_types that depend on system state (not_found,
  conflict, authorization_denied), does the condition specify WHAT
  state triggers the error? "No task exists with the given task_id"
  tells PH-005 to set up a scenario where the task does not exist.
  "Resource not found" does not tell PH-005 WHICH resource or HOW
  to ensure its absence.
- Check: for error_types that involve external dependencies
  (dependency_failure), does the condition name the dependency and
  the failure mode? "Email service returned non-success status or
  timed out" tells PH-005 to simulate two external failure modes.
  "External service unavailable" does not tell PH-005 which service
  or what constitutes "unavailable."
- The test: for each operation, could PH-005 write one test scenario
  per error_type where (a) the input is crafted to trigger exactly
  that error, (b) the scenario description explains WHY this input
  triggers this error and not another, and (c) the assertion checks
  for the specific error name? If PH-005 cannot construct
  non-overlapping triggers from the conditions alone, the error
  types are under-specified for simulation.

### Area 4: Behavioral Spec Actionability for Assertion Construction

PH-005 must translate each behavioral spec into simulation assertions:
set up the precondition, invoke the operation, then verify the
postcondition and invariant. For this to work, behavioral specs must
be expressed in terms that a simulation can observe and verify.

Precondition actionability:

- A precondition is actionable when PH-005 can SET UP the required
  state before invoking the operation. "Task exists and is in 'open'
  status" tells PH-005 to create a task with status 'open' before
  calling the operation. "Request is valid" does not tell PH-005
  what state to construct.
- Check: for each precondition, can PH-005 derive a setup step? The
  precondition must name specific entities, states, or relationships
  that PH-005 can establish. If the precondition references an entity
  type defined in shared_types, PH-005 can construct an instance. If
  the precondition references an entity not defined anywhere in the
  contracts, PH-005 cannot set it up.
- Check: for preconditions that reference prior operations (e.g.,
  "Task has been created via CTR-001"), does the referenced contract
  exist and does its postcondition establish the state this
  precondition requires? PH-005 chains operations by matching
  postconditions to preconditions. A broken chain means PH-005
  cannot construct a multi-step scenario.

Postcondition verifiability:

- A postcondition is verifiable when PH-005 can ASSERT its truth
  after the operation completes. "Task status is 'assigned' and
  assignee matches the request" tells PH-005 to check two specific
  fields. "Task is updated" does not tell PH-005 what to check.
- Check: for each postcondition, can PH-005 derive an assertion?
  The postcondition must name specific fields and expected values
  (or value constraints). If the postcondition says "notification_id
  is a valid UUID," PH-005 can assert format. If the postcondition
  says "record is created," PH-005 cannot determine what fields to
  check.
- Check: for postconditions that produce observable side effects
  (e.g., "audit event is recorded"), does the contract define HOW
  PH-005 can observe the effect? If the audit event is observable
  through another contract (e.g., a query operation), the
  observation path must be traceable. If the side effect is
  mentioned but no contract provides read access to it, PH-005
  cannot verify it.

Invariant checkability:

- An invariant is checkable when PH-005 can read the preserved state
  BEFORE the operation, invoke the operation, then read the same
  state AFTER and assert equality. "Task title and description are
  unchanged" tells PH-005 to snapshot two specific fields. "System
  stable" does not tell PH-005 what to snapshot.
- Check: for each invariant, does it name specific fields or entities
  that PH-005 can read through a contract operation? If the invariant
  says "other tasks in the project are unchanged," PH-005 needs a
  list-tasks operation to read task state before and after. If no
  such operation exists in any contract, the invariant is
  unverifiable.

The test: for each behavioral spec, could PH-005 write a three-phase
test: (1) setup phase establishing the precondition using contract
operations, (2) invocation phase calling the operation under test,
(3) verification phase asserting the postcondition and invariant
using contract operations? If any phase requires information not
present in the contracts, the behavioral spec is insufficient for
simulation.

### Area 5: Cross-Contract Composability for Multi-Step Scenarios

PH-005 must construct multi-step simulation scenarios that exercise
entire feature flows. These scenarios chain multiple contracts in the
order defined by the feature_realization_map from the solution design.
For chaining to work, one contract's output must be composable as
another contract's input.

Checks:

- Check: for each feature in the solution design's
  feature_realization_map, walk the interaction_sequence. For each
  consecutive pair (INT-A, INT-B), does INT-A's contract produce
  output fields that INT-B's contract accepts as input? If INT-A's
  response returns a task_id and INT-B's request requires a task_id,
  the types and field names MUST match exactly. If INT-A returns
  "id: string(format: uuid)" and INT-B expects "task_id: string",
  PH-005 cannot automatically wire them together without a mapping
  layer.
- Check: for each consecutive pair, do the shared type references
  align? If INT-A's response uses ref(TaskSummary) and INT-B's
  request uses ref(TaskInput), and these are different shared types
  with overlapping but non-identical fields, PH-005 must know which
  fields to extract from the summary to populate the input. If no
  contract or shared type definition documents this mapping, PH-005
  must invent it.
- Check: do the behavioral specs form consistent chains? If CTR-A's
  postcondition says "Task exists in 'assigned' status" and CTR-B's
  precondition says "Task exists in 'open' status," the chain is
  inconsistent -- CTR-A's success creates a state that violates
  CTR-B's precondition. PH-005 cannot build a scenario that
  satisfies both.
- Check: for features with conditional flows (branching based on
  error or status), do the error_types and response enums provide
  enough information for PH-005 to determine which branch to take?
  If a status enum has values [approved, rejected] and the feature
  flow branches at that point, PH-005 needs one scenario per branch.
  If the enum is partial or the branching conditions are not
  specified, PH-005 cannot construct complete flow coverage.
- The test: for each feature in the feature_realization_map, could
  PH-005 write an end-to-end scenario that: creates initial state,
  calls each contract in sequence, passes output from one as input
  to the next, and asserts the final postcondition matches the
  feature's expected outcome? If any step requires data that the
  previous step's contract does not produce, or if precondition/
  postcondition chains are inconsistent, the contracts are not
  composable for simulation.

## Your task

Perform these six steps in order:

1. **Simulate input data generation.** For each operation in every
   contract, attempt to construct a valid input, a boundary input,
   and an invalid input for each field in the request_schema.
   - Can you determine valid values from the type and constraints?
   - Can you identify boundary values from min/max/length/pattern?
   - Can you construct invalid values that test specific violations?
   - Note where you had to consult the solution design, feature
     specification, requirements inventory, or raw requirements to
     determine what constitutes "valid" or "boundary" for a field.

2. **Simulate output prediction.** For each operation, given a known
   valid input, attempt to predict the expected response.
   - Can you distinguish server-generated fields from deterministic
     fields from echo-through fields?
   - Can you predict the value of each response field?
   - Note where response schemas are too imprecise for assertion
     construction.

3. **Simulate error-path scenario construction.** For each error_type
   in every operation, attempt to construct a triggering input.
   - Can you craft an input that triggers ONLY this error?
   - Can you distinguish this error's trigger from every other
     error's trigger on the same operation?
   - Note where error conditions are too vague or overlapping for
     scenario construction.

4. **Simulate behavioral assertion construction.** For each behavioral
   spec in every contract:
   - Can you derive a setup step from the precondition?
   - Can you derive an assertion from the postcondition?
   - Can you derive a snapshot-and-compare from the invariant?
   - Note where behavioral specs reference unobservable state or
     undefined entities.

5. **Simulate multi-step scenario construction.** For each feature in
   the feature_realization_map, attempt to chain the contracts in
   sequence.
   - Can you wire output fields to input fields across consecutive
     contracts?
   - Do precondition/postcondition chains form a consistent sequence?
   - Note where composability breaks.

6. **Produce a structured YAML critique.** Synthesize your findings
   from steps 1-5 into the output format below.

## Output format

Your entire response must be a single YAML document (no commentary
outside the YAML). Use this exact structure:

    phase_evaluated: PH-004-interface-contracts
    findings:
      - severity: blocking | warning | info
        location: "CTR-NNN or TYP-NNN or <section>"
        downstream_phase: "PH-005"
        issue: |
          Description of the problem, stated in terms of what PH-005
          will be unable to do because of this gap.
        recommendation: |
          What should change. Be specific: not "add more detail" but
          "change CTR-001 field task_name from type 'string' to type
          'string(min_length: 1, max_length: 200)' so PH-005 can
          generate boundary-length inputs."
      - ...
    input_generation_feasibility:
      - contract: "CTR-NNN"
        operation: "operation_name"
        fields:
          - field: "field_name"
            type_as_declared: "the declared type"
            valid_value_derivable: true | false
            boundary_value_derivable: true | false
            invalid_value_derivable: true | false
            notes: |
              What PH-005 can or cannot generate for this field.
          - ...
        overall_generatable: true | false
      - ...
    output_prediction_feasibility:
      - contract: "CTR-NNN"
        operation: "operation_name"
        response_fields:
          - field: "field_name"
            category: generated | deterministic | echo | derived
            predictable: true | false
            notes: |
              What PH-005 can or cannot predict for this field.
          - ...
        assertion_constructable: true | false
      - ...
    error_path_feasibility:
      - contract: "CTR-NNN"
        operation: "operation_name"
        error_scenarios:
          - error_name: "the error type name"
            trigger_craftable: true | false
            distinguishable: true | false
            state_setup_required: true | false
            state_setup_possible: true | false
            notes: |
              What PH-005 can or cannot construct for this error path.
          - ...
        full_error_coverage: true | false
      - ...
    behavioral_assertion_feasibility:
      - contract: "CTR-NNN"
        behavioral_specs:
          - spec_index: N
            precondition_setupable: true | false
            postcondition_assertable: true | false
            invariant_checkable: true | false
            observation_contracts: ["CTR-NNN", ...]
            notes: |
              What PH-005 can or cannot verify for this spec.
          - ...
        simulation_testable: true | false
      - ...
    multi_step_scenario_feasibility:
      - feature: "FT-NNN"
        interaction_sequence: ["INT-NNN", "INT-NNN", ...]
        contract_chain: ["CTR-NNN", "CTR-NNN", ...]
        steps:
          - from_contract: "CTR-NNN"
            to_contract: "CTR-NNN"
            output_to_input_wirable: true | false
            precondition_chain_consistent: true | false
            field_mappings:
              - from_field: "response.field_name"
                to_field: "request.field_name"
                type_match: true | false
            notes: |
              What PH-005 can or cannot wire between these steps.
          - ...
        end_to_end_constructable: true | false
        branch_coverage:
          - branch_point: "CTR-NNN response field or error"
            branch_values: ["value1", "value2", ...]
            scenarios_per_branch: N
            notes: "what branches PH-005 can or cannot exercise"
          - ...
      - ...
    shared_type_simulation_readiness:
      - type_name: "TypeName"
        fields_fully_constrained: true | false
        instantiable: true | false
        under_constrained_fields:
          - field: "field_name"
            issue: "what constraint is missing"
          - ...
        notes: |
          What PH-005 can or cannot do with this shared type.
      - ...
    overall_usability: high | medium | low
    summary: |
      Brief 2-3 sentence summary. State the most important finding
      first.

## Severity definitions

- blocking: PH-005 cannot proceed without resolving this. Example:
  a request_schema field has a bare 'string' type for what is clearly
  a structured value (date, phone number, postal code), so PH-005
  cannot generate valid vs. invalid inputs. Example: an error_type's
  condition says "input is invalid" without naming which field or
  what constitutes invalid, so PH-005 cannot craft a triggering
  input. Example: a precondition references an entity type not
  defined in any shared_type or contract, so PH-005 cannot set up
  the required state. Example: consecutive contracts in a feature
  flow have a type mismatch on the field that chains them (one
  returns string, the other expects integer), so PH-005 cannot wire
  the scenario.
- warning: PH-005 can proceed but will likely produce imprecise or
  incomplete simulations. Example: a field has a constrained type
  but no explicit min/max, so PH-005 can generate valid inputs but
  cannot test boundaries. Example: a postcondition says "record is
  created" without naming specific fields, so PH-005 can assert
  existence but not field correctness. Example: an invariant says
  "other records unchanged" without naming which records, so PH-005
  can write a general assertion but not a targeted one.
- info: Worth noting but will not impede simulation construction.
  Example: a constraint uses prose ("must be a valid email") instead
  of a format annotation, but the intent is still clear enough for
  data generation. Example: the interaction_sequence in the feature
  realization map is obvious from the contracts' behavioral specs,
  making the explicit sequence redundant but not harmful.
```
