```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# Intelligent Simulation Framework — Implementable Design
# ═══════════════════════════════════════════════════════════════════════════════
#
# This document specifies the architecture, data structures, lifecycle, and
# runtime behavior of contract-enforcing simulations used in Phase 4 and
# consumed by Phase 5 of the AI-driven development pipeline.
#
# A simulation is NOT a mock or a stub. It is a contract-enforcing test double
# that validates inputs, provides deterministic responses for known scenarios,
# and uses an LLM to generate plausible responses for unknown inputs — all
# while guaranteeing schema conformance on every response.
#
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SIMULATION ARCHITECTURE
# ═══════════════════════════════════════════════════════════════════════════════
#
# Each simulation is a callable unit that stands in for a single contract
# (CTR-*) from Phase 3. It receives a request conforming to the contract's
# input type and returns a response conforming to the contract's output type
# or error type. Internally it is composed of four sub-components that execute
# in a fixed pipeline:
#
#   Request ──► [Input Validator] ──► [Scenario Matcher] ──► [Output Validator] ──► Response
#                    │                      │ no match           │
#                    │ invalid              ▼                    │ invalid
#                    ▼               [LLM Adjuster] ────────────┘
#              CONTRACT_VIOLATION         │
#              error returned             ▼
#                                  [Output Validator]
#                                        │ invalid
#                                        ▼
#                                  retry / fallback
#
# The pipeline is synchronous: each sub-component completes before the next
# begins. There is no parallelism within a single simulation invocation.
# ═══════════════════════════════════════════════════════════════════════════════

simulation_architecture:

  # ---------------------------------------------------------------------------
  # 1.1 Simulation Unit
  # ---------------------------------------------------------------------------
  # The top-level callable. One simulation unit per contract.

  simulation_unit:
    description: |
      A simulation unit wraps a single contract and exposes the same
      operation signature. It is the entry point for all simulation
      invocations. The unit maintains internal state (for stateful
      simulations) and delegates to its four sub-components.

    identity:
      simulation_id: "SIM-{three-digit-sequence}"   # e.g., SIM-001
      contract_ref: "CTR-{three-digit-sequence}"     # the contract this simulates
      operation_name: string                         # matches the contract's operation_name
      from_component: "CMP-*"                        # the caller component
      to_component: "CMP-*"                          # the component being simulated

    sub_components:
      - input_validator
      - scenario_matcher
      - llm_adjuster
      - output_validator

    state_store:
      description: |
        An in-memory key-value store scoped to this simulation instance.
        Used to model stateful behavior when the contract's preconditions
        or postconditions reference persistent state (e.g., "user exists
        after creation", "session is active"). Each scenario can declare
        state mutations (state_effects) that are applied after a
        successful response.

        The state store is reset between test runs unless the test
        explicitly opts into persistent state (for multi-step scenario
        testing).
      schema:
        entries:
          type: "map<string, any>"
          description: |
            Keys are domain-relevant identifiers (e.g., "users:{id}",
            "sessions:{token}"). Values are structured objects matching
            the contract's domain types. The state store does not enforce
            schema on values — that is the scenario author's
            responsibility.
        reset_policy: "per-test-run"   # per-test-run | per-scenario | manual

    invocation_protocol:
      description: |
        The fixed execution sequence for every invocation. No step is
        skippable.
      steps:
        - step: 1
          name: "input_validation"
          action: |
            Pass the incoming request to the Input Validator. If
            validation fails, return the CONTRACT_VIOLATION error
            immediately. Do not proceed to scenario matching.

        - step: 2
          name: "precondition_check"
          action: |
            Evaluate the contract's preconditions against the current
            state store and the input. If any precondition is violated,
            return the corresponding error from the contract's error
            type. The mapping from precondition to error code is
            declared in the simulation's precondition_error_map.

        - step: 3
          name: "scenario_matching"
          action: |
            Pass the validated input to the Scenario Matcher. If a
            matching scenario is found, use its expected_output as the
            candidate response. Proceed to step 5.

        - step: 4
          name: "llm_adjustment"
          action: |
            If no scenario matched, pass the input to the LLM Adjuster
            along with the closest partial match from the scenario bank.
            The LLM Adjuster produces a candidate response. Proceed to
            step 5.

        - step: 5
          name: "output_validation"
          action: |
            Pass the candidate response to the Output Validator. If
            validation succeeds, apply any state_effects declared by the
            matched scenario (or inferred by the LLM Adjuster), then
            return the response.

            If validation fails and the response came from the scenario
            bank (step 3), this is a configuration error — the scenario
            has an invalid expected_output. Log the error and return a
            SIMULATION_CONFIG_ERROR.

            If validation fails and the response came from the LLM
            Adjuster (step 4), invoke the LLM Adjuster's retry logic
            (see section 3 for retry and fallback behavior).

        - step: 6
          name: "invocation_logging"
          action: |
            Record the invocation in the simulation's audit log:
            timestamp, input (redacted if sensitive), response source
            (scenario bank or LLM adjuster), response, validation
            result, and wall-clock duration. This log is used for
            debugging and for simulation acceptance testing.

  # ---------------------------------------------------------------------------
  # 1.2 Input Validator
  # ---------------------------------------------------------------------------

  input_validator:
    description: |
      Validates incoming requests against the contract's input type
      definition. The validator is generated from the contract's type
      schema and is deterministic — no LLM involvement.

    responsibilities:
      - Verify that every required field is present.
      - Verify that every field's value matches its declared type.
      - Verify format constraints (email, URL, UUID, ISO date, etc.).
      - Verify range constraints (minimum, maximum, string length).
      - Verify enum membership for enumerated types.
      - Verify collection cardinality (minItems, maxItems).
      - Verify nested object structures recursively.

    validation_rule_schema:
      description: |
        Each rule tests one aspect of one field. Rules are generated
        from the contract's input type definition.
      fields:
        rule_id:
          type: string
          format: "VR-{sim-sequence}-IN-{rule-sequence}"
          example: "VR-001-IN-001"
        field_path:
          type: string
          description: "Dot-path to the field in the input object"
          example: "credentials.email"
        check_type:
          type: string
          enum:
            - required        # field must be present
            - type_match      # value type must match (string, number, boolean, object, array)
            - format          # string must match declared format
            - range           # numeric value must be within declared bounds
            - string_length   # string length must be within declared bounds
            - enum_member     # value must be one of the declared enum values
            - cardinality     # array length must be within declared bounds
            - pattern         # string must match a regex pattern
            - custom          # a custom validation function (for complex constraints)
          description: |
            The type of check to perform. Most checks are generated
            directly from the contract type definition. The "custom"
            type is used for contract preconditions that cannot be
            expressed as simple type constraints (e.g., "start_date
            must be before end_date").
        constraint:
          type: string
          description: |
            The specific constraint value. Interpretation depends on
            check_type:
              required: "true"
              type_match: "string" | "number" | "boolean" | "object" | "array"
              format: "email" | "url" | "uuid" | "iso-date" | "iso-datetime"
              range: ">=0" | "<=100" | ">=1,<=1000"
              string_length: ">=1" | "<=255" | ">=1,<=255"
              enum_member: "active|inactive|suspended"
              cardinality: ">=1" | "<=50" | ">=0,<=100"
              pattern: regex string
              custom: description of the constraint logic
        on_failure_error:
          type: string
          description: |
            The error code returned when this validation fails. Always
            CONTRACT_VIOLATION for input validation failures. The error
            response includes the rule_id and a human-readable message
            describing which field failed which check.

    error_response_format:
      description: |
        The standard error response for input validation failures.
        This is NOT one of the contract's declared error types — it is
        a simulation infrastructure error that indicates the caller
        sent a non-conforming request.
      schema:
        error_code: "CONTRACT_VIOLATION"
        violation_type: "input_validation"
        violations:
          type: "list"
          items:
            rule_id: string
            field_path: string
            check_type: string
            expected: string
            actual: string
            message: string
          example:
            - rule_id: "VR-001-IN-003"
              field_path: "credentials.email"
              check_type: "format"
              expected: "email"
              actual: "not-an-email"
              message: "Field 'credentials.email' must be a valid email address"

    generation_strategy: |
      Input validators are generated mechanically from the contract's
      input type definition. For each field in the type:
        1. If the field is marked required, emit a "required" rule.
        2. Emit a "type_match" rule for the field's base type.
        3. If the field has a format annotation, emit a "format" rule.
        4. If the field has min/max annotations, emit a "range" rule.
        5. If the field is an enum, emit an "enum_member" rule.
        6. If the field is an array with cardinality constraints, emit
           a "cardinality" rule.
        7. Recurse into nested objects.

      For contract preconditions that reference input fields (e.g.,
      "email must not be empty"), emit additional "custom" rules.

      The validator generation is a deterministic transformation — no
      LLM is needed. The output is a list of validation rules that can
      be executed as a sequence of checks.

  # ---------------------------------------------------------------------------
  # 1.3 Scenario Matcher
  # ---------------------------------------------------------------------------

  scenario_matcher:
    description: |
      Searches the scenario bank for an entry whose input pattern
      matches the incoming request. Returns the matched scenario's
      expected_output if found, or the closest partial match (for the
      LLM Adjuster) if no exact match exists.

    matching_algorithm:
      description: |
        The matcher uses a three-tier strategy, evaluated in order.
        The first tier that produces a match wins.

      tiers:
        - tier: 1
          name: "exact_match"
          description: |
            The input matches a scenario's input_pattern on every
            field, with exact value equality. This is the fastest
            path — pure hash lookup.

            For scenarios whose input_pattern contains only literal
            values (no wildcards, no ranges), the matcher pre-computes
            a hash of the canonical JSON representation of the pattern.
            At runtime, it hashes the incoming input and checks the
            hash table. O(1) lookup.
          when_to_use: |
            Most scenario bank entries use exact match. Happy-path
            scenarios with specific test data, error scenarios with
            specific invalid inputs, and edge cases with boundary
            values all use exact match.

        - tier: 2
          name: "pattern_match"
          description: |
            The input matches a scenario's input_pattern when the
            pattern contains wildcards or range constraints. Pattern
            matching is evaluated field by field:
              - Wildcard "*" matches any value for that field.
              - Range "{min}..{max}" matches numeric values in the range.
              - Regex "/{pattern}/" matches string values against the regex.
              - Type "{type}" matches any value of the given type.
              - Absent field in pattern means "any value or absent."

            Pattern scenarios are evaluated in declaration order. The
            first matching pattern wins. Scenario authors must order
            patterns from most specific to least specific to avoid
            unintended matches.

            The input must match ALL specified fields in the pattern
            (conjunction). A pattern with fewer fields than the input
            is a valid match — unspecified fields are ignored.
          when_to_use: |
            Used for scenarios that cover a class of inputs rather
            than a single input. For example, "any valid email with
            any password" for a general authentication happy-path, or
            "any numeric value outside 1..100" for range validation
            errors.

        - tier: 3
          name: "closest_match"
          description: |
            No exact or pattern match was found. The matcher computes
            a similarity score for every scenario in the bank and
            returns the highest-scoring scenario as the "closest match."
            This closest match is NOT used as the response — it is
            passed to the LLM Adjuster as context.

            Similarity scoring algorithm:
              1. For each field in the input, check if the scenario's
                 input_pattern has a value for that field.
              2. If the field exists in both and values are equal: +2 points.
              3. If the field exists in both and values differ but are
                 the same type: +1 point.
              4. If the field exists in the pattern but not in the input
                 (or vice versa): +0 points.
              5. Normalize by dividing by (2 * max_field_count) to get
                 a score between 0.0 and 1.0.

            If the highest similarity score is below 0.1, return
            "no_match" with no closest match — the input is too
            dissimilar to any scenario to be useful context.
          when_to_use: |
            This tier always runs as a fallback when tiers 1 and 2
            fail. The result is metadata for the LLM Adjuster, not a
            response to the caller.

    match_result_schema:
      match_type: "exact | pattern | closest | no_match"
      matched_scenario_id: "SCN-* or null"
      similarity_score: "number (0.0 to 1.0) — only for closest/no_match"
      response_source: "scenario_bank | llm_adjuster"

  # ---------------------------------------------------------------------------
  # 1.4 Output Validator
  # ---------------------------------------------------------------------------

  output_validator:
    description: |
      Validates the simulation's response (whether from the scenario
      bank or the LLM Adjuster) against the contract's output type or
      error type definition. Structurally identical to the Input
      Validator but operates on the response.

    responsibilities:
      - Verify that the response conforms to the contract's output type
        (for success responses) or error type (for error responses).
      - Apply the same field-level checks as the Input Validator
        (required fields, type matching, format, range, enum, etc.).
      - Verify postcondition compliance where postconditions are
        expressible as output field constraints.
      - Reject responses that are structurally valid but semantically
        inconsistent (e.g., a success response with an error code field
        populated, or an error response missing the error_code field).

    validation_rule_schema:
      description: |
        Same structure as input_validator.validation_rule_schema but
        with rule IDs prefixed VR-{sim}-OUT-{seq}.
      rule_id_format: "VR-{sim-sequence}-OUT-{rule-sequence}"

    on_failure_behavior:
      from_scenario_bank: |
        If the output validator rejects a response from the scenario
        bank, this is a configuration error in the scenario definition.
        The scenario's expected_output does not conform to the contract.
        The simulation:
          1. Logs a SIMULATION_CONFIG_ERROR with the scenario ID, the
             validation failures, and the non-conforming response.
          2. Returns a SIMULATION_CONFIG_ERROR to the caller rather
             than the invalid response.
          3. The scenario is flagged as "invalid" in the scenario bank
             and excluded from future matching until repaired.
        This should be caught during simulation acceptance testing
        (section 4.2), not at runtime.

      from_llm_adjuster: |
        If the output validator rejects a response from the LLM
        Adjuster, the adjuster's retry logic is invoked (see section 3
        for the full retry and fallback protocol).

    generation_strategy: |
      Output validators are generated mechanically from the contract's
      output type and error type definitions, using the same
      deterministic transformation as input validators. No LLM needed.

  # ---------------------------------------------------------------------------
  # 1.5 Composition Model
  # ---------------------------------------------------------------------------

  composition:
    description: |
      The four sub-components compose into a single simulation unit
      as a linear pipeline with conditional branching. The composition
      is fixed — it cannot be reconfigured per-simulation. What varies
      between simulations is the content of each sub-component (the
      validation rules, the scenario bank entries, and the LLM adjuster
      prompt context).

    data_flow:
      description: |
        request: object           — the incoming request from the caller
        validated_input: object   — request after input validation (same object, tagged valid)
        match_result: object      — scenario matcher output (match type, scenario, score)
        candidate_response: object — from scenario bank or LLM adjuster
        validated_response: object — candidate after output validation (same object, tagged valid)

      flow: |
        request
          │
          ▼
        input_validator.validate(request)
          │ pass ──────────────────────────────────────────────┐
          │ fail → return CONTRACT_VIOLATION error             │
          ▼                                                    │
        precondition_check(validated_input, state_store)       │
          │ pass ──────────────────────────────────────────────┤
          │ fail → return precondition error                   │
          ▼                                                    │
        scenario_matcher.match(validated_input)                │
          │ exact/pattern match ─► candidate = scenario.output │
          │ closest/no_match ───► llm_adjuster.generate(       │
          │                         input=validated_input,     │
          │                         closest=match_result,      │
          │                         contract=contract_def      │
          │                       ) → candidate                │
          ▼                                                    │
        output_validator.validate(candidate)                   │
          │ pass → apply state_effects                         │
          │      → log invocation                              │
          │      → return candidate as response                │
          │ fail (from scenario) → return CONFIG_ERROR         │
          │ fail (from LLM) → retry/fallback (see section 3)  │
          ▼
        response returned to caller


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SCENARIO BANK STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════════

scenario_bank:

  # ---------------------------------------------------------------------------
  # 2.1 Scenario Entry Format
  # ---------------------------------------------------------------------------

  entry_schema:
    description: |
      Each scenario is a single input-output pair with metadata. The
      scenario bank for a simulation is an ordered list of these entries.
      Ordering matters for pattern matching (tier 2): earlier patterns
      take priority over later ones.

    fields:
      scenario_id:
        type: string
        format: "SCN-{sim-sequence}-{scenario-sequence}"
        example: "SCN-001-001"
        description: |
          Unique identifier. The sim-sequence matches the parent
          simulation's sequence number. The scenario-sequence is
          three-digit, zero-padded, starting at 001.

      description:
        type: string
        description: |
          One sentence describing what this scenario exercises. Written
          for human readers debugging test failures.
        example: "Happy-path login with valid email and password"

      category:
        type: string
        enum:
          - happy-path     # normal success case for a feature
          - error          # triggers a specific error code
          - edge-case      # boundary condition (empty list, max value, etc.)
          - precondition   # tests a precondition violation
        description: |
          Categorization for coverage analysis. Each category maps to
          a minimum coverage requirement (see section 2.3).

      feature_refs:
        type: "list of string"
        description: |
          FT-* IDs of features this scenario serves. Required for
          happy-path scenarios. May be empty for error and edge-case
          scenarios that are contract-level rather than feature-level.
        example: ["FT-001"]

      contract_element_ref:
        type: string
        description: |
          Element locator pointing to the specific part of the contract
          this scenario exercises. For error scenarios, points to the
          error type variant. For edge cases, points to the edge case
          definition. For happy-path scenarios, points to the output
          type definition.
        example: "docs/design/interface-contracts.yaml#$.contracts[0].error_type.variants[2]"

      input_pattern:
        type: object
        description: |
          The input that triggers this scenario. May contain literal
          values (for exact matching) or pattern expressions (for
          pattern matching).

          Pattern expression syntax (used in field values):
            "*"               — wildcard, matches any value
            "{1..100}"        — numeric range, inclusive
            "/{regex}/"       — regex pattern for strings
            "{string}"        — matches any string value
            "{number}"        — matches any numeric value
            "{boolean}"       — matches any boolean value

          Fields not present in the pattern are ignored during matching
          (treated as wildcards). To require a field to be absent, use
          the special value "{absent}".
        example:
          credentials:
            email: "user@example.com"
            password: "correct-password"

      expected_output:
        type: object
        description: |
          The response the simulation returns when this scenario
          matches. Must conform to the contract's output type (for
          success scenarios) or error type (for error scenarios).

          This is a complete, concrete response — no patterns or
          wildcards. The output validator will check it against the
          contract schema during simulation acceptance testing.
        example:
          status: "success"
          session:
            token: "sim-token-001"
            expires_at: "2026-04-09T14:30:00Z"
            user_id: "sim-user-001"

      is_error_response:
        type: boolean
        description: |
          True if expected_output is an error response (matching the
          contract's error type). False if it is a success response
          (matching the contract's output type). The output validator
          uses this flag to select the correct schema for validation.

      precondition_state:
        type: object
        description: |
          State that must exist in the simulation's state store for
          this scenario to be valid. If this field is present and the
          required state is absent, the scenario is skipped during
          matching (it does not match). Used for multi-step scenarios
          where an earlier invocation must have set up state.

          Keys are state store keys. Values are the required values
          (exact match). Use "*" to require the key to exist with any
          value.
        example:
          "users:sim-user-001": "*"    # user must exist

      state_effects:
        type: object
        description: |
          State mutations applied to the simulation's state store after
          this scenario's response is returned. Used to model side
          effects (e.g., "createUser" adds a user to the store).

          Operations:
            set: { key: value }    — create or overwrite a key
            delete: [key]          — remove a key
        example:
          set:
            "sessions:sim-token-001":
              user_id: "sim-user-001"
              created_at: "2026-04-08T14:30:00Z"

      match_priority:
        type: integer
        description: |
          Explicit priority for ordering within the same match tier.
          Lower numbers match first. Default is 100. Scenarios with
          the same priority are evaluated in declaration order.

          Use priority < 100 for highly specific scenarios that should
          preempt more general ones. Use priority > 100 for fallback
          patterns.
        default: 100

  # ---------------------------------------------------------------------------
  # 2.2 Matching Protocol
  # ---------------------------------------------------------------------------

  matching_protocol:
    description: |
      The scenario matcher executes this protocol on every invocation.
      The protocol produces exactly one of four outcomes: exact_match,
      pattern_match, closest_match, or no_match.

    steps:
      - step: 1
        name: "exact_lookup"
        action: |
          Compute the canonical hash of the input (sorted keys, stable
          JSON serialization). Look up the hash in the exact-match
          index.

          The exact-match index is a hash map built at simulation
          startup by hashing every scenario whose input_pattern contains
          only literal values (no wildcards, no ranges, no regex).

          If a hash collision occurs (multiple scenarios with different
          precondition_state requirements hash to the same input):
          evaluate precondition_state for each and return the first
          whose preconditions are met.

          If found: return the scenario. Done.

      - step: 2
        name: "precondition_filter"
        action: |
          For all remaining scenarios (pattern-match candidates),
          filter out any whose precondition_state requirements are not
          met by the current state store. This avoids matching a
          pattern scenario whose preconditions are violated.

      - step: 3
        name: "pattern_evaluation"
        action: |
          Iterate through pattern scenarios (those with wildcards,
          ranges, or regex) in priority order (match_priority ascending,
          then declaration order).

          For each scenario, evaluate every field in its input_pattern
          against the corresponding field in the input:
            - Literal value: exact equality check
            - "*": always matches
            - "{min..max}": numeric range check (inclusive)
            - "/{regex}/": regex test on the string value
            - "{type}": typeof check
            - "{absent}": field must not be present in input

          All fields in the pattern must match (conjunction). Fields in
          the input but not in the pattern are ignored.

          Return the first matching scenario. Done.

      - step: 4
        name: "closest_computation"
        action: |
          No exact or pattern match. Compute similarity scores for all
          scenarios (including those filtered out by precondition_state
          — closest match is used for LLM context, not for direct
          response, so precondition state is informational).

          Similarity score per scenario:
            matched_fields = 0
            total_fields = max(len(input_fields), len(pattern_fields))
            for each field in input:
              if field in pattern:
                if values_equal: matched_fields += 2
                elif same_type: matched_fields += 1
            score = matched_fields / (2 * total_fields)

          Return the scenario with the highest score, or no_match if
          the highest score < 0.1.

  # ---------------------------------------------------------------------------
  # 2.3 Minimum Coverage Requirements
  # ---------------------------------------------------------------------------

  minimum_coverage:
    description: |
      A simulation is not usable until its scenario bank meets these
      minimum coverage thresholds. Coverage is checked during simulation
      acceptance testing (section 4.2).

    requirements:
      happy_path:
        description: |
          At least one happy-path scenario for every feature that uses
          this contract (every FT-* ID in the design interaction's
          features_served list).
        check: |
          For each FT-* in interaction.features_served:
            assert any(s.category == "happy-path" and FT in s.feature_refs
                       for s in scenario_bank)
        minimum_count_per_feature: 1

      error_codes:
        description: |
          At least one error scenario for every error code in the
          contract's error type.
        check: |
          For each error_variant in contract.error_type.variants:
            assert any(s.category == "error"
                       and s.expected_output.error_code == error_variant.error_code
                       for s in scenario_bank)
        minimum_count_per_error_code: 1

      edge_cases:
        description: |
          At least one edge-case scenario for every edge case listed
          in the contract.
        check: |
          For each edge_case in contract.edge_cases:
            assert any(s.category == "edge-case"
                       and s.contract_element_ref points to this edge_case
                       for s in scenario_bank)
        minimum_count_per_edge_case: 1

      precondition_violations:
        description: |
          At least one precondition scenario for every precondition
          in the contract.
        check: |
          For each precondition in contract.preconditions:
            assert any(s.category == "precondition"
                       for s in scenario_bank
                       where s tests this precondition's violation)
        minimum_count_per_precondition: 1

    total_minimum: |
      The scenario bank must have at least:
        max(5, feature_count + error_code_count + edge_case_count + precondition_count)
      scenarios. The floor of 5 ensures that even simple contracts have
      meaningful coverage.


# ═══════════════════════════════════════════════════════════════════════════════
# 3. LLM ADJUSTER SPECIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

llm_adjuster:

  # ---------------------------------------------------------------------------
  # 3.1 Purpose and Constraints
  # ---------------------------------------------------------------------------

  purpose: |
    The LLM Adjuster generates a plausible response for inputs that do
    not match any scenario in the bank. It operates under strict
    constraints: its output MUST conform to the contract's output type
    schema, and it MUST be consistent with the contract's postconditions.

    The adjuster is a fallback, not a primary response mechanism. A
    well-populated scenario bank should handle the vast majority of
    invocations. The adjuster handles novel inputs that the scenario
    author did not anticipate.

  constraints:
    - Output must parse as valid JSON/YAML matching the contract's output type.
    - Every required field in the output type must be present.
    - Every field value must conform to its declared type and constraints.
    - The output must not contradict the contract's postconditions.
    - The output must be deterministic for the same input within a single
      test run (achieved via temperature 0 or seeded randomness).
    - The adjuster must not make external calls (no network, no file
      system) — it operates purely on the contract context and the input.

  # ---------------------------------------------------------------------------
  # 3.2 Prompt Template
  # ---------------------------------------------------------------------------

  prompt_template:
    description: |
      The prompt sent to the LLM when the adjuster is invoked. It is
      assembled from the contract definition, the closest scenario, and
      the actual input. The prompt uses a structured format to minimize
      ambiguity and maximize schema compliance.

    system_message: |
      You are a simulation engine for a software component that has not
      been built yet. You generate realistic responses that conform
      EXACTLY to a specified output schema.

      ## Rules

      1. Your response must be a single JSON object conforming to the
         output schema below. Do not include any text outside the JSON.
      2. Every required field must be present with a value of the
         correct type.
      3. String fields with format constraints (email, URL, UUID,
         ISO date) must use valid values in that format.
      4. Numeric fields with range constraints must use values within
         the range.
      5. Enum fields must use one of the declared values.
      6. The response must be consistent with the postconditions listed
         below.
      7. Use realistic but obviously simulated data. Prefix generated
         IDs with "sim-" to distinguish them from real data.
      8. If the input appears to be an error case (violates a
         precondition or triggers a known error condition), generate an
         error response conforming to the error schema instead of the
         success schema. Use the error_response_schema provided below.
      9. Do not invent capabilities not described in the contract.
      10. Respond ONLY with the JSON object. No markdown fences, no
          explanations, no commentary.

    user_message_template: |
      ## Contract

      Operation: {operation_name}
      Description: {contract_description}

      ## Input Schema (for reference — this is what the caller sent)

      ```json
      {input_type_schema_json}
      ```

      ## Success Output Schema (produce a response matching this)

      ```json
      {output_type_schema_json}
      ```

      ## Error Response Schema (use if the input triggers an error)

      ```json
      {error_type_schema_json}
      ```

      ## Postconditions (your response must be consistent with these)

      {postconditions_as_numbered_list}

      ## Edge Cases (known boundary conditions and expected behavior)

      {edge_cases_as_numbered_list}

      ## Closest Matching Scenario (use as a template — adapt, do not copy)

      Input pattern:
      ```json
      {closest_scenario_input_json}
      ```

      Expected output:
      ```json
      {closest_scenario_output_json}
      ```

      Similarity to actual input: {similarity_score}

      ## Actual Input (generate a response for THIS input)

      ```json
      {actual_input_json}
      ```

      ## Response

    template_variables:
      operation_name:
        source: "contract.operation_name"
      contract_description:
        source: "contract.description"
      input_type_schema_json:
        source: "contract.input_type, serialized as JSON Schema"
      output_type_schema_json:
        source: "contract.output_type, serialized as JSON Schema"
      error_type_schema_json:
        source: "contract.error_type, serialized as JSON Schema"
      postconditions_as_numbered_list:
        source: "contract.postconditions, one per line, numbered"
      edge_cases_as_numbered_list:
        source: "contract.edge_cases, one per line with condition and expected behavior"
      closest_scenario_input_json:
        source: "closest_match.input_pattern, serialized as JSON"
        fallback: "No matching scenario found — generate from schema alone."
      closest_scenario_output_json:
        source: "closest_match.expected_output, serialized as JSON"
        fallback: "No matching scenario found — generate from schema alone."
      similarity_score:
        source: "match_result.similarity_score"
        fallback: "0.0"
      actual_input_json:
        source: "validated_input, serialized as JSON"

  # ---------------------------------------------------------------------------
  # 3.3 LLM Configuration
  # ---------------------------------------------------------------------------

  llm_configuration:
    model: "claude-sonnet-4-6"
    temperature: 0.1
    max_output_tokens: 4096
    description: |
      Low temperature (0.1) produces near-deterministic outputs while
      allowing minimal variation for novel inputs. Sonnet is preferred
      over Opus for adjuster calls because the task is constrained
      generation (filling a schema), not open-ended reasoning. The
      cost and latency difference is significant when simulations are
      invoked hundreds of times during integration testing.

      max_output_tokens is set to 4096 to accommodate large contract
      output types. For contracts with smaller output types, this can
      be reduced to improve latency.

  # ---------------------------------------------------------------------------
  # 3.4 Response Parsing
  # ---------------------------------------------------------------------------

  response_parsing:
    description: |
      The LLM's raw text output is parsed into a structured object
      before output validation.

    steps:
      - step: 1
        action: |
          Strip any markdown fences (```json ... ```) if present.
          The prompt instructs the LLM not to use fences, but some
          models include them despite instructions.

      - step: 2
        action: |
          Parse the text as JSON. If parsing fails, this is a
          "parse failure" — proceed to retry logic.

      - step: 3
        action: |
          Determine if the response is a success response or error
          response by checking for the presence of the error_code
          field. If error_code is present, validate against the error
          type schema. Otherwise, validate against the output type
          schema.

  # ---------------------------------------------------------------------------
  # 3.5 Retry and Fallback Protocol
  # ---------------------------------------------------------------------------

  retry_protocol:
    max_retries: 2
    description: |
      If the LLM produces a non-conforming output (parse failure or
      schema validation failure), the adjuster retries with
      progressively tighter constraints.

    attempts:
      - attempt: 1
        name: "initial"
        action: |
          Send the prompt template as described in section 3.2. Parse
          and validate the response.
        on_failure: "proceed to attempt 2"

      - attempt: 2
        name: "correction_retry"
        action: |
          Re-send the prompt with an additional correction message
          appended to the user message:

          "## Correction Required

          Your previous response failed validation:
          {validation_error_details}

          Please generate a new response that fixes these specific
          issues. Ensure every required field is present and every
          value conforms to the schema."

          The validation_error_details include the specific field
          paths and constraint violations from the output validator.
        on_failure: "proceed to attempt 3"

      - attempt: 3
        name: "schema_only_retry"
        action: |
          Send a simplified prompt that strips the closest-scenario
          context and focuses entirely on schema compliance:

          "Generate a JSON object conforming exactly to this schema:
          {output_type_schema_json}

          Required values:
          {field_by_field_requirements}

          The object must be valid JSON. Every required field must be
          present. Use the simplest valid value for each field."

          The field_by_field_requirements is a flat list of every
          field with its type, constraints, and an example value
          from the scenario bank.
        on_failure: "proceed to fallback"

    fallback:
      name: "closest_scenario_fallback"
      description: |
        All LLM retries have been exhausted. The adjuster falls back
        to the closest scenario's expected_output, modified minimally
        to acknowledge that the input was different.

        Fallback strategy:
        1. If a closest scenario exists (similarity > 0.1):
           Use the closest scenario's expected_output verbatim. This
           is schema-conforming by construction (validated during
           simulation acceptance testing). Log a warning that the
           response is a fallback and may not be semantically
           accurate for the given input.

        2. If no closest scenario exists (similarity <= 0.1):
           Return a SIMULATION_FALLBACK error:
           {
             "error_code": "SIMULATION_FALLBACK",
             "message": "No scenario matched and LLM adjuster failed
                         to produce a conforming response after 3
                         attempts. Input is too dissimilar to any
                         known scenario.",
             "input_hash": "{hash of the input}",
             "closest_similarity": {score}
           }
           This error is NOT a contract error type — it is a
           simulation infrastructure error. The caller should treat
           it as an indication that the scenario bank needs expansion.

      logging: |
        Every fallback event is logged at WARNING level with:
          - simulation_id
          - input (redacted if sensitive)
          - closest scenario ID and similarity score
          - LLM attempt count and failure reasons
          - fallback action taken (scenario reuse or error)

        Fallback events are aggregated in the simulation health
        report (section 5.2) to identify simulations that need
        scenario bank expansion.


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SIMULATION LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════════

simulation_lifecycle:

  # ---------------------------------------------------------------------------
  # 4.1 Generation from Contracts
  # ---------------------------------------------------------------------------

  generation:
    description: |
      Simulation generation is the process of producing a complete
      simulation unit from a contract definition. This is performed
      by the Phase 4 Artifact Generator agent, but the generation
      logic is deterministic for validators and LLM-assisted for
      scenario banks.

    process:
      - step: 1
        name: "input_validator_generation"
        action: |
          For each field in the contract's input_type:
            1. Emit a "required" rule if the field is required.
            2. Emit a "type_match" rule for the field's type.
            3. Emit format/range/enum/cardinality rules as applicable.
            4. Recurse into nested objects and array item types.

          For each precondition in the contract:
            If the precondition references an input field, emit a
            "custom" rule that checks the precondition against the
            input.

          This step is fully deterministic. No LLM needed.

      - step: 2
        name: "output_validator_generation"
        action: |
          Same process as step 1 but applied to the contract's
          output_type and error_type. Generates VR-*-OUT-* rules.

          Additionally, for each postcondition that can be expressed
          as an output field constraint (e.g., "returned user_id is
          non-empty"), emit a rule that checks it.

          Fully deterministic. No LLM needed.

      - step: 3
        name: "precondition_error_map_generation"
        action: |
          For each precondition in the contract:
            Map it to the error code that should be returned when
            the precondition is violated. The mapping is derived from
            the contract's error type — each error variant's
            description should indicate which precondition triggers it.

          If the mapping is ambiguous (a precondition does not clearly
          correspond to an error code), flag it for human review.

          Mostly deterministic; may require LLM assistance for
          ambiguous mappings.

      - step: 4
        name: "scenario_bank_generation"
        action: |
          This is the primary LLM-assisted step. The generator
          produces scenarios in four passes:

          Pass 1 — Happy-path scenarios:
            For each feature in the interaction's features_served:
              Read the feature's acceptance criteria. For each
              criterion, generate a concrete input and expected output
              that demonstrates the criterion being satisfied. The
              input uses realistic test data; the output conforms to
              the contract's output type.

          Pass 2 — Error scenarios:
            For each error variant in the contract's error_type:
              Generate an input that would trigger this error. The
              expected_output is the error response with the specific
              error_code.

          Pass 3 — Edge-case scenarios:
            For each edge_case in the contract:
              Generate an input matching the edge case's condition.
              The expected_output matches the edge case's
              expected_behavior.

          Pass 4 — Precondition violation scenarios:
            For each precondition in the contract:
              Generate an input that violates the precondition. The
              expected_output is the corresponding error from the
              precondition_error_map.

          After all passes, verify minimum coverage requirements
          (section 2.3) are met.

      - step: 5
        name: "llm_adjuster_configuration"
        action: |
          Assemble the LLM adjuster configuration:
            - Serialize the contract's input_type, output_type, and
              error_type as JSON Schema.
            - Format postconditions as a numbered list.
            - Format edge cases as a numbered list.
            - Set LLM parameters (model, temperature, max_tokens).

          Fully deterministic (template assembly). No LLM needed.

      - step: 6
        name: "assembly"
        action: |
          Combine all generated components into a simulation unit:
            - Assign SIM-* ID.
            - Attach input validator, output validator, scenario bank,
              LLM adjuster configuration, and precondition error map.
            - Initialize empty state store.
            - Write the simulation definition to the output artifact.

  # ---------------------------------------------------------------------------
  # 4.2 Simulation Acceptance Testing
  # ---------------------------------------------------------------------------

  acceptance_testing:
    description: |
      Before a simulation is deployed for integration testing, it must
      pass its own acceptance tests. These tests verify that the
      simulation behaves correctly — they are tests OF the simulation,
      not tests USING the simulation.

    test_categories:

      - category: "scenario_conformance"
        description: |
          Every scenario's expected_output is validated against the
          contract's output type (or error type). Catches configuration
          errors where a scenario was written with a non-conforming
          response.
        test_generation: |
          For each scenario in the scenario bank:
            1. Run the expected_output through the output validator.
            2. Assert validation passes.
          This is a pure validation test — no simulation invocation.

      - category: "scenario_round_trip"
        description: |
          Every scenario's input_pattern is sent to the simulation and
          the response is compared to the expected_output. Verifies
          that the simulation returns what the scenario specifies.
        test_generation: |
          For each scenario with all-literal input_pattern:
            1. Invoke the simulation with the input_pattern as input.
            2. Assert the response equals expected_output.
          For each scenario with pattern expressions:
            1. Generate a concrete input that matches the pattern.
            2. Invoke the simulation.
            3. Assert the response equals expected_output.

      - category: "input_rejection"
        description: |
          Known-invalid inputs are sent to the simulation and the
          response must be a CONTRACT_VIOLATION error with specific
          violation details.
        test_generation: |
          For each validation rule in the input validator:
            1. Construct an input that violates exactly this rule
               (all other fields are valid).
            2. Invoke the simulation.
            3. Assert CONTRACT_VIOLATION error is returned.
            4. Assert the violation details reference the correct
               rule_id and field_path.

      - category: "coverage_verification"
        description: |
          The scenario bank meets the minimum coverage requirements
          defined in section 2.3.
        test_generation: |
          Run the coverage checks from section 2.3 against the
          scenario bank. Assert all checks pass.

      - category: "llm_adjuster_smoke"
        description: |
          A novel input (not matching any scenario) is sent to the
          simulation to verify the LLM adjuster produces a
          schema-conforming response.
        test_generation: |
          1. Construct an input that is valid according to the input
             type but does not match any scenario's input_pattern.
          2. Invoke the simulation.
          3. Assert the response is NOT a CONTRACT_VIOLATION.
          4. Assert the response conforms to the output type or error
             type schema.
          Note: this test does not assert semantic correctness of the
          LLM-generated response — only schema conformance.

    acceptance_verdict:
      pass_condition: |
        All tests in all categories pass. Zero failures.
      on_failure: |
        The simulation is marked "invalid" in the registry and cannot
        be used for integration testing. The specific test failures
        are reported so the simulation definition can be corrected.

  # ---------------------------------------------------------------------------
  # 4.3 Runtime Behavior During Integration Testing
  # ---------------------------------------------------------------------------

  runtime:
    description: |
      During integration testing, simulations are invoked by the
      component under test through the same interface the real
      dependency would expose. The integration test runner composes
      the system by consulting the simulation registry to determine
      which dependencies are simulated and which are real.

    invocation_modes:

      - mode: "direct"
        description: |
          The component under test calls the simulation directly via
          a function call. The simulation is instantiated in-process.
          Used when the component and its dependency communicate via
          function calls (synchronous-request-response within the
          same process).
        setup: |
          The integration test imports the simulation module, creates
          a simulation instance from the simulation definition, and
          injects it as the dependency implementation.

      - mode: "http_server"
        description: |
          The simulation runs as a local HTTP server. The component
          under test sends HTTP requests to the simulation's endpoint.
          Used when the component communicates with its dependency via
          HTTP (REST, GraphQL).
        setup: |
          The integration test starts the simulation as a local HTTP
          server on an ephemeral port. The simulation's operation_name
          maps to a route. The component is configured to send requests
          to localhost:{port}.
        endpoint_mapping: |
          Each simulation operation maps to a POST endpoint:
            POST /sim/{operation_name}
          Request body: the operation's input type (JSON).
          Response body: the operation's output type or error type (JSON).
          HTTP status codes:
            200 — success response
            400 — CONTRACT_VIOLATION (input validation failure)
            409 — precondition violation (mapped to contract error)
            500 — SIMULATION_CONFIG_ERROR or SIMULATION_FALLBACK

      - mode: "event_emitter"
        description: |
          For asynchronous interactions, the simulation acts as an
          event consumer and producer. Used when the communication
          style is asynchronous-event or asynchronous-command.
        setup: |
          The integration test creates an in-memory event bus. The
          simulation subscribes to the event type that the component
          publishes. When an event arrives, the simulation processes
          it through its pipeline and publishes the response event.

    state_management:
      description: |
        During a test run, the simulation's state store persists across
        invocations within the same test case. This enables multi-step
        scenarios (e.g., create a user, then authenticate as that user).

        Between test cases, the state store is reset to its initial
        state (empty or a declared initial state from the test fixture).

        Test isolation is critical: no state leaks between test cases.
        The integration test framework is responsible for managing
        simulation lifecycle (create, use, reset, destroy).

    audit_logging:
      description: |
        Every simulation invocation is logged to an in-memory audit log
        that can be queried after the test run for debugging.
      log_entry_schema:
        timestamp: "ISO 8601"
        simulation_id: "SIM-*"
        operation_name: string
        input: object
        response_source: "scenario_bank | llm_adjuster | fallback | contract_violation | precondition_error"
        matched_scenario_id: "SCN-* or null"
        similarity_score: "number or null"
        response: object
        output_validation_result: "pass | fail"
        llm_attempt_count: "integer (0 if scenario bank, 1-3 if LLM)"
        duration_ms: integer

  # ---------------------------------------------------------------------------
  # 4.4 Switchover: Replacing Simulations with Real Implementations
  # ---------------------------------------------------------------------------

  switchover:
    description: |
      When a real component implementation passes its own tests (unit
      tests, contract conformance tests), its simulation is replaced
      with the real implementation for all components that depend on it.
      This switchover is managed by the orchestrator and the simulation
      registry.

    protocol:
      - step: 1
        name: "pre_switch_verification"
        action: |
          Confirm the real component has passed:
            - All unit tests (from the implementation plan)
            - All contract conformance tests (for every contract it provides)
          If any test is failing, abort the switchover.

      - step: 2
        name: "registry_update"
        action: |
          Update the simulation registry to mark the component as
          "switching" (transitional state). This prevents new test
          runs from starting while the switch is in progress.

      - step: 3
        name: "dependent_identification"
        action: |
          Query the simulation registry for all components that depend
          on the component being switched. These are components whose
          integration tests previously used the simulation (SIM-*)
          for this dependency.

      - step: 4
        name: "integration_re_test"
        action: |
          For each dependent component:
            1. Reconfigure its integration test environment to use the
               real implementation instead of the simulation.
            2. Re-run ALL integration tests for that component (not
               just the tests that use this specific dependency — a
               switchover can cause cascade effects).
            3. Record test results.

          Specifically, re-run every scenario from the simulation's
          scenario bank as an integration test against the real
          implementation. This verifies that the real implementation
          produces responses compatible with what the simulation
          provided.

      - step: 5
        name: "behavioral_comparison"
        action: |
          For each scenario in the replaced simulation's scenario bank:
            Compare the real implementation's response to the
            simulation's expected_output.

            Classification of differences:
              - Identical: no action needed.
              - Structurally equivalent (same schema, different values
                for generated fields like timestamps or IDs): acceptable.
                Log as informational.
              - Semantically different (different error code, different
                success/failure outcome, missing fields): this is a
                simulation-to-real divergence. Flag for investigation.

          Divergence thresholds:
            - Zero semantically different responses: switchover succeeds.
            - Any semantically different response: switchover is flagged.
              The specific divergences are reported. The dependent
              component's tests may need updating, or the real
              implementation may have a bug.

      - step: 6
        name: "switch_completion"
        action: |
          If step 4 and step 5 pass:
            - Update the registry to mark the component as "real".
            - Archive the simulation definition (keep it for reference
              but mark it as superseded).
            - Log the successful switchover.

          If step 4 or step 5 fails:
            - Revert the registry to "simulated".
            - Log the failure with specific test results and
              divergences.
            - The switchover does not proceed. The dependent components
              continue using the simulation until the divergence is
              resolved (either fix the real implementation or update
              the simulation/tests).

      - step: 7
        name: "cascade_check"
        action: |
          After a successful switchover, check if any other components
          are now ready for switchover (all their dependencies are
          either "real" or have passing simulations). If so, trigger
          their switchover protocol.


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SIMULATION REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

simulation_registry:

  # ---------------------------------------------------------------------------
  # 5.1 Registry Data Model
  # ---------------------------------------------------------------------------

  data_model:
    description: |
      The simulation registry is the single source of truth for the
      current state of every component's test double. The integration
      test runner queries it to compose the system for each test run.

    storage_path: "docs/simulations/simulation-registry.yaml"

    schema:
      registry_metadata:
        last_updated: "ISO 8601 timestamp"
        total_components: integer
        simulated_count: integer
        real_count: integer
        switching_count: integer

      components:
        type: "list of component state objects"
        item_schema:
          component_id:
            type: string
            format: "CMP-*"
            description: "Component ID from the solution design"

          component_name:
            type: string
            description: "Human-readable name"

          state:
            type: string
            enum:
              - simulated       # All contracts provided by this component are
                                # served by simulations. The real implementation
                                # does not exist or has not passed its tests.
              - real            # The real implementation is deployed and has
                                # passed all tests. Its simulation is archived.
              - switching       # Transitional state during switchover protocol.
                                # No new test runs should start.
              - partial         # Some contracts are real, others are simulated.
                                # Only valid for components that provide
                                # multiple contracts.
            description: |
              The current state of this component's test double.

          contracts_provided:
            type: "list of contract state objects"
            item_schema:
              contract_id:
                type: string
                format: "CTR-*"
              simulation_id:
                type: string
                format: "SIM-*"
                description: "The simulation that serves this contract"
              simulation_status:
                type: string
                enum:
                  - active       # Simulation is in use by dependent components
                  - archived     # Replaced by real implementation
                  - invalid      # Failed acceptance testing
                  - generating   # Being generated, not yet usable
              real_implementation_status:
                type: string
                enum:
                  - not_started  # No implementation exists
                  - in_progress  # Implementation underway, not yet passing
                  - passing      # All tests pass, ready for switchover
                  - deployed     # Switchover complete, simulation archived

          depends_on:
            type: "list of dependency objects"
            item_schema:
              component_id:
                type: string
                format: "CMP-*"
              contract_ids:
                type: "list of string"
                format: "CTR-*"
              resolution:
                type: string
                enum:
                  - simulated   # Using the simulation for this dependency
                  - real        # Using the real implementation
                description: |
                  How this dependency is currently resolved in the test
                  environment.

          switchover_history:
            type: "list of switchover event objects"
            item_schema:
              timestamp: "ISO 8601"
              from_state: string
              to_state: string
              trigger: string
              result: "success | failed | reverted"
              details: string

  # ---------------------------------------------------------------------------
  # 5.2 Health Report
  # ---------------------------------------------------------------------------

  health_report:
    description: |
      A periodic report generated from the registry and simulation
      audit logs that identifies simulations needing attention.

    generated_by: "orchestrator or CI pipeline"
    output_path: "docs/simulations/simulation-health-report.yaml"

    report_schema:
      report_metadata:
        generated_at: "ISO 8601"
        reporting_period: "ISO 8601 interval"

      simulation_health:
        type: "list of simulation health objects"
        item_schema:
          simulation_id: "SIM-*"
          contract_ref: "CTR-*"
          status: "active | archived | invalid"

          scenario_bank_stats:
            total_scenarios: integer
            happy_path_count: integer
            error_count: integer
            edge_case_count: integer
            precondition_count: integer
            coverage_met: boolean

          invocation_stats:
            total_invocations: integer
            scenario_bank_hits: integer
            llm_adjuster_invocations: integer
            fallback_invocations: integer
            contract_violations: integer
            hit_rate_pct: number

          health_indicators:
            - indicator: "llm_adjuster_rate"
              value: number
              threshold: 20.0
              status: "healthy | warning | critical"
              description: |
                Percentage of invocations handled by the LLM adjuster.
                If above 20%, the scenario bank needs expansion.
                If above 50%, the simulation is unreliable.

            - indicator: "fallback_rate"
              value: number
              threshold: 5.0
              status: "healthy | warning | critical"
              description: |
                Percentage of invocations that hit the fallback path
                (LLM adjuster failed). If above 5%, the simulation
                has significant blind spots.

            - indicator: "avg_latency_ms"
              value: number
              threshold: 500
              status: "healthy | warning | critical"
              description: |
                Average invocation latency. LLM adjuster calls are
                significantly slower than scenario bank hits.
                If average exceeds 500ms, tests are slowed.

          recommendations:
            type: "list of string"
            description: |
              Actionable recommendations based on health indicators.
              Examples:
                "Add scenarios for inputs similar to: {common LLM inputs}"
                "Scenario SCN-001-003 has never been matched — consider removing"
                "LLM adjuster failure rate is 12% — investigate common failure patterns"

  # ---------------------------------------------------------------------------
  # 5.3 Registry Queries
  # ---------------------------------------------------------------------------

  queries:
    description: |
      The registry exposes these queries for the integration test
      runner, the orchestrator, and human operators.

    query_definitions:

      - name: "compose_test_environment"
        description: |
          Given a component under test, return the dependency resolution
          map: for each dependency, whether to use the simulation or
          the real implementation, and the connection details.
        input:
          component_id: "CMP-*"
        output:
          dependencies:
            type: "list"
            items:
              component_id: "CMP-*"
              resolution: "simulated | real"
              simulation_id: "SIM-* (if simulated)"
              connection_details: object

      - name: "switchover_readiness"
        description: |
          Given a component, determine if it is ready for switchover:
          all its own tests pass and no other switchover is in progress
          for its dependencies.
        input:
          component_id: "CMP-*"
        output:
          ready: boolean
          blockers:
            type: "list of string"
            description: "Reasons why switchover cannot proceed"

      - name: "implementation_progress"
        description: |
          Return the overall progress of the implementation: how many
          components are real vs. simulated, and the next components
          eligible for implementation (their dependencies are all
          real or have passing simulations).
        output:
          total_components: integer
          real_components: integer
          simulated_components: integer
          switching_components: integer
          next_implementable:
            type: "list of CMP-* IDs"
            description: |
              Components whose dependencies are all either "real" or
              "simulated with active status". These are candidates for
              the next implementation step.

      - name: "simulation_dependency_graph"
        description: |
          Return the full dependency graph with simulation/real
          annotations, suitable for visualization.
        output:
          nodes:
            type: "list"
            items:
              component_id: "CMP-*"
              state: "simulated | real | switching"
          edges:
            type: "list"
            items:
              from: "CMP-*"
              to: "CMP-*"
              contract_id: "CTR-*"
              resolution: "simulated | real"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. CONCRETE IMPLEMENTATION APPROACH
# ═══════════════════════════════════════════════════════════════════════════════

implementation_approach:

  # ---------------------------------------------------------------------------
  # 6.1 Technology Stack
  # ---------------------------------------------------------------------------

  technology_stack:
    language: "TypeScript"
    runtime: "Node.js"
    rationale: |
      TypeScript matches the project's existing server-side stack.
      The type system enables compile-time enforcement of contract
      schemas. The async/await model supports both synchronous and
      asynchronous simulation invocation modes.

    dependencies:
      core:
        - package: "ajv"
          purpose: |
            JSON Schema validation for input and output validators.
            Contracts' type definitions are converted to JSON Schema,
            and ajv validates inputs/outputs at runtime. This is the
            fastest pure-JS JSON Schema validator.
        - package: "yaml"
          purpose: "Parse simulation definitions and scenario banks from YAML"
        - package: "@anthropic-ai/sdk"
          purpose: "LLM adjuster calls to Claude"

      testing:
        - package: "vitest"
          purpose: "Test framework for simulation acceptance tests and integration tests"

      http_mode:
        - package: "fastify"
          purpose: |
            HTTP server for simulations running in http_server mode.
            Lightweight, fast, schema-first (aligns with contract-first
            approach).

  # ---------------------------------------------------------------------------
  # 6.2 Module Structure
  # ---------------------------------------------------------------------------

  module_structure:
    description: |
      The simulation framework is a library consumed by the integration
      test runner. It is not a standalone service.

    modules:
      - path: "src/server/simulation/index.ts"
        exports:
          - "SimulationUnit"
          - "SimulationRegistry"
          - "createSimulationFromContract"
          - "runSimulationAcceptanceTests"

      - path: "src/server/simulation/types.ts"
        description: |
          All type definitions: SimulationDefinition, ScenarioEntry,
          ValidationRule, MatchResult, AuditLogEntry, RegistryState,
          etc. Generated from the schemas defined in this document.

      - path: "src/server/simulation/input-validator.ts"
        description: |
          InputValidator class. Takes a list of ValidationRule objects
          and a JSON Schema (compiled by ajv). Validates incoming
          requests. Returns either the validated input or a
          CONTRACT_VIOLATION error with violation details.

      - path: "src/server/simulation/output-validator.ts"
        description: |
          OutputValidator class. Same structure as InputValidator but
          operates on responses. Also validates postcondition
          compliance for postconditions expressible as output field
          constraints.

      - path: "src/server/simulation/scenario-matcher.ts"
        description: |
          ScenarioMatcher class. Builds the exact-match hash index at
          construction time. Implements the three-tier matching
          algorithm (exact, pattern, closest). Returns a MatchResult
          with the matched scenario or closest match metadata.

      - path: "src/server/simulation/llm-adjuster.ts"
        description: |
          LLMAdjuster class. Assembles the prompt from the template
          and contract context. Calls the Claude API. Parses and
          returns the response. Implements the retry protocol with
          correction messages. Falls back to closest scenario or
          SIMULATION_FALLBACK error.

      - path: "src/server/simulation/simulation-unit.ts"
        description: |
          SimulationUnit class. Composes InputValidator, ScenarioMatcher,
          LLMAdjuster, and OutputValidator. Implements the invocation
          protocol (section 1.5). Manages the state store. Logs
          invocations to the audit log.

      - path: "src/server/simulation/simulation-registry.ts"
        description: |
          SimulationRegistry class. Loads and persists registry state
          from YAML. Provides query methods (compose_test_environment,
          switchover_readiness, implementation_progress). Manages
          switchover protocol state transitions.

      - path: "src/server/simulation/http-server.ts"
        description: |
          SimulationHttpServer class. Wraps a SimulationUnit in a
          Fastify HTTP server for the http_server invocation mode.
          Maps POST /sim/{operation_name} to simulation invocations.

      - path: "src/server/simulation/generator.ts"
        description: |
          Functions for generating simulation definitions from
          contract definitions: generateInputValidator,
          generateOutputValidator, generateScenarioBank (LLM-assisted),
          generateLLMAdjusterConfig, assembleSimulation.

      - path: "src/server/simulation/acceptance-tester.ts"
        description: |
          Functions for running simulation acceptance tests:
          testScenarioConformance, testScenarioRoundTrip,
          testInputRejection, testCoverageVerification,
          testLLMAdjusterSmoke.

  # ---------------------------------------------------------------------------
  # 6.3 Key Implementation Patterns
  # ---------------------------------------------------------------------------

  implementation_patterns:

    - pattern: "Schema compilation at startup"
      description: |
        JSON Schemas for input and output types are compiled by ajv
        once at simulation construction time, not on every invocation.
        The compiled validators are reused across all invocations.
        This keeps per-invocation cost to a hash lookup (exact match)
        or a schema validation call (ajv is optimized for repeated
        validation against the same schema).

    - pattern: "Scenario bank indexing"
      description: |
        At construction time, the ScenarioMatcher partitions scenarios
        into two groups: exact-match (all-literal input patterns) and
        pattern-match (patterns with wildcards/ranges/regex).

        Exact-match scenarios are indexed by the SHA-256 hash of their
        canonical JSON input. This gives O(1) lookup for the common
        case.

        Pattern-match scenarios are stored in priority order (ascending
        match_priority, then declaration order) as a linear list.
        Pattern evaluation is O(N) where N is the number of pattern
        scenarios — acceptable because pattern scenarios are typically
        a small fraction of the bank.

    - pattern: "LLM adjuster caching"
      description: |
        The LLM adjuster maintains an in-memory cache keyed by the
        canonical hash of (contract_id, input). If the same input is
        sent multiple times (common in re-runs), the cached response
        is returned without an LLM call. The cache is scoped to the
        simulation instance lifetime and cleared on reset.

        Cache invalidation: the cache is cleared when the simulation
        definition changes (scenario bank updates, contract schema
        changes). Since simulations are recreated from definitions,
        this happens naturally when a new SimulationUnit is constructed.

    - pattern: "Audit log as ring buffer"
      description: |
        The audit log is an in-memory ring buffer with a configurable
        maximum size (default: 10000 entries). Oldest entries are
        evicted when the buffer is full. The log can be drained to a
        file for post-test analysis.

        The ring buffer prevents unbounded memory growth during long
        test runs. For short test runs (the common case), all entries
        fit in memory and are available for immediate inspection.

    - pattern: "Dependency injection for test composition"
      description: |
        The integration test runner uses the simulation registry to
        compose dependencies. Each component under test receives its
        dependencies via constructor injection (or a dependency
        container). The test runner resolves each dependency to either
        a SimulationUnit instance or a real implementation instance
        based on the registry state.

        This pattern allows the same component code to run against
        simulations during early development and against real
        implementations after switchover — the component does not
        know or care which it is talking to.

  # ---------------------------------------------------------------------------
  # 6.4 File Reference Summary
  # ---------------------------------------------------------------------------

  file_reference:
    description: |
      Summary of all files the simulation framework reads and writes.

    files:
      - path: "docs/design/interface-contracts.yaml"
        read_by: ["generator", "simulation-unit", "llm-adjuster"]
        written_by: ["Phase 3 artifact generator"]
        purpose: "Contract definitions that simulations enforce"

      - path: "docs/simulations/simulation-definitions.yaml"
        read_by: ["simulation-unit", "acceptance-tester", "registry"]
        written_by: ["Phase 4 artifact generator"]
        purpose: "Complete simulation definitions for all contracts"

      - path: "docs/simulations/simulation-registry.yaml"
        read_by: ["integration-test-runner", "orchestrator"]
        written_by: ["orchestrator", "switchover-protocol"]
        purpose: "Current state of all component test doubles"

      - path: "docs/simulations/simulation-health-report.yaml"
        read_by: ["human operator", "orchestrator"]
        written_by: ["health report generator"]
        purpose: "Periodic health metrics for simulation quality"
```