

```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# Phase Processing Unit — Universal Schema Definition
# ═══════════════════════════════════════════════════════════════════════════════
#
# Every phase in the AI-driven software development methodology instantiates
# this schema exactly once. The schema enforces a separation of concerns:
#   - Checklist extraction is performed by an agent that does NOT generate.
#   - Artifact generation is performed by an agent that does NOT judge.
#   - Judgment is performed by an agent that did NOT generate.
#
# This three-agent separation prevents the generator from grading its own work
# and prevents the judge from inventing requirements not grounded in inputs.
#
# Inter-phase ordering and dependency resolution are the responsibility of the
# pipeline orchestrator, not this schema. This schema defines a single phase
# in isolation. The orchestrator determines execution order, parallelism, and
# dependency satisfaction using the input_sources declarations and the
# phase_output paths to build a directed acyclic graph of phases.
# ═══════════════════════════════════════════════════════════════════════════════


# ---------------------------------------------------------------------------
# Element Locator Grammar
# ---------------------------------------------------------------------------
#
# All fields that reference elements within documents (source_ref,
# artifact_element_ref, artifact_location, input_source_refs entries)
# use a uniform locator syntax:
#
#   {file_path}#{locator}
#
# The locator portion uses one of four discriminated formats, identified
# by prefix:
#
#   Prefix     Format                  Example                          Use when
#   ────────   ──────────────────────  ───────────────────────────────  ────────────────────
#   /          Heading path            requirements.md#/Section/Sub     Markdown documents
#   $.         JSON pointer (dot)      spec.yaml#$.features[0].name    YAML/JSON structures
#   L          Line range              module.py#L14-L27               Source code, plain text
#   @          Named anchor/ID         requirements.md#@FR-001         Any doc with stable IDs
#
# Range syntax: append `..` to extend across siblings or elements.
#   @FR-001..@FR-005   — the span of anchors FR-001 through FR-005
#   L14..L27           — equivalent to L14-L27 (alternate form)
#
# When a locator targets the entire file, omit the # fragment:
#   requirements.md    — refers to the whole document
#
# Implementations MUST parse the prefix character(s) to select the
# appropriate resolution strategy. Locators without a recognized prefix
# are invalid and MUST cause a validation error.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Top-level Phase Processing Unit
# ---------------------------------------------------------------------------
phase_processing_unit:

  # Unique identifier for the phase within the methodology pipeline.
  # Convention: PH-{sequential_number}-{kebab-case-name}
  phase_id: "PH-000-example"

  # Human-readable name shown in dashboards and logs.
  phase_name: "Example Phase"

  # Semantic version of this phase definition. Bumped when the phase's
  # instructions, checklist strategy, or output format change.
  version: "1.0.0"

  # =========================================================================
  # 1. INPUT SOURCES
  # =========================================================================
  #
  # Declares every artifact this phase reads. A phase MUST NOT read artifacts
  # that are not listed here — this makes dependency graphs auditable.
  #
  # Roles:
  #   primary              — the main artifact being transformed or refined
  #   validation-reference — used to cross-check but not directly transformed
  #   upstream-traceability — provides lineage context from earlier phases
  #
  # External references capture standards, API specs, or codebases that
  # exist outside the pipeline but constrain the phase's output.
  #
  # Each artifact entry carries an optional content_hash for staleness
  # detection. The phase runner SHOULD compute the hash at execution time
  # and compare it to the declared value. A mismatch indicates the input
  # changed after the phase was configured, and the runner SHOULD halt
  # or re-extract the checklist depending on pipeline policy.
  # =========================================================================
  input_sources:

    artifacts:
      # At least one artifact is required. The list is ordered by role
      # priority: primary sources first.
      - ref: "path/to/artifact"              # File path to the artifact
        role: "primary"                      # primary | validation-reference | upstream-traceability
        format: "markdown"                   # markdown | yaml | json | typescript | python | other
        description: "Brief description of what this source provides"
        content_hash: ""                     # Optional. SHA-256 hex digest of file content at
                                             # configuration time. Empty string means no hash
                                             # was captured; the runner skips staleness check.
        version: ""                          # Optional. Semantic version or git ref of the
                                             # artifact. Empty string means unversioned.

    external_references:
      # Zero or more. These are not pipeline artifacts — they are stable
      # external documents the phase needs to consult.
      - ref: "https://example.com/api-spec"
        kind: "api-specification"            # api-specification | coding-standard | existing-codebase | regulatory | other
        description: "Why this external source is needed"

  # =========================================================================
  # 2. CHECKLIST EXTRACTION
  # =========================================================================
  #
  # A dedicated extractor agent reads the input sources and produces a flat
  # list of acceptance criteria. Each item is:
  #   - grounded in a specific element of an input source (using locator syntax)
  #   - concrete enough to yield a binary or ternary (pass/partial/fail) result
  #   - tagged with the verification method the judge should use
  #
  # After extraction, a separate validator agent checks three invariants:
  #   (a) coverage  — every requirement in inputs maps to >= 1 checklist item
  #   (b) grounding — every checklist item traces to an input source element
  #   (c) specificity — items are precise enough for pass/fail judgment
  #
  # If the validator finds violations, the checklist is revised before
  # artifact generation begins. This sub-loop has its own termination
  # guarantee (max_validation_iterations and validation_escalation_policy).
  # =========================================================================
  checklist_extraction:

    extractor_agent: "checklist-extractor"    # Agent identifier (not the generator)

    # Instructions scoped to this phase that tell the extractor what kinds
    # of criteria to look for. Generic extraction logic lives in the agent;
    # phase-specific focus areas are declared here.
    extraction_focus: |
      Describe what aspects of the input sources the extractor should
      prioritise when deriving checklist items for this specific phase.

    checklist_items:
      # Each item follows this structure exactly.
      - id: "CL-{phase}-{sequence}"          # Example: CL-REQ-001

        # Points to the specific section, sentence, or element in an input
        # source that necessitates this criterion. MUST use the element
        # locator grammar defined above (prefix-discriminated).
        # Examples:
        #   docs/requirements/raw-requirements.md#@FR-001
        #   docs/requirements/raw-requirements.md#@FR-001..@FR-005
        #   docs/features/feature-list.yaml#$.features[0].name
        #   src/auth/handler.ts#L14-L27
        source_ref: "path/to/artifact#@element-id"

        # The criterion itself. Must be a declarative statement that can
        # be evaluated as true or false against the generated artifact.
        # Bad:  "Requirements should be covered"
        # Good: "Every functional requirement in FR-* has a corresponding
        #        feature in the feature list with matching ID suffix"
        criterion: "Concrete, verifiable statement"

        # How the judge should verify this item.
        #   schema_inspection  — check structural/schema conformance
        #   behavioral_trace   — trace a scenario through the artifact
        #   content_match      — look for specific content or patterns
        #   coverage_query     — verify completeness / coverage metrics
        #   manual_review      — requires human judgment (use sparingly)
        verification_method: "content_match"

    # -----------------------------------------------------------------------
    # Checklist Validation (performed by a second agent)
    # -----------------------------------------------------------------------
    #
    # The validation sub-loop ensures the checklist is sound before artifact
    # generation begins. The three checks run in a defined order:
    #
    #   1. grounding  — remove items not traceable to inputs
    #   2. coverage   — verify all input requirements are represented
    #   3. specificity — ensure items support pass/fail judgment
    #
    # After grounding removes items, coverage MUST re-run because removals
    # may create gaps. The full sequence (grounding → coverage → specificity)
    # repeats until all three checks pass or max_validation_iterations is
    # reached.
    #
    # Feedback from validator to extractor on each cycle includes:
    #   - The check that failed (grounding, coverage, or specificity)
    #   - The specific checklist item IDs that are problematic
    #   - For coverage failures: the input source element(s) not covered
    #   - For specificity failures: which items are too vague and why
    # -----------------------------------------------------------------------
    validation:
      validator_agent: "checklist-validator"  # Must differ from extractor and generator

      # Maximum number of extractor-validator cycles before escalation.
      # Prevents unbounded looping when extractor and validator cannot
      # converge on a sound checklist.
      max_validation_iterations: 3           # Default; override per phase

      # What happens when max_validation_iterations is exhausted.
      #   halt               — pipeline stops; no checklist produced
      #   flag-and-continue  — use best-effort checklist with warning flag
      #   human-review       — park checklist for human inspection
      validation_escalation_policy: "halt"   # halt | flag-and-continue | human-review

      # The feedback payload sent from validator to extractor on each
      # failed validation cycle. This structure is produced by the
      # validator, consumed by the extractor.
      validation_feedback:
        failed_check: ""                     # grounding | coverage | specificity
        problematic_item_ids: []             # List of CL-* IDs that failed the check
        uncovered_input_refs: []             # For coverage failures: locator refs to
                                             # input elements missing checklist items
        specificity_notes: []                # For specificity failures: per-item
                                             # explanations of why the criterion is
                                             # too vague to produce pass/fail judgment

      checks:
        # Checks execute in this order. After grounding removals,
        # coverage re-runs automatically.

        grounding:
          order: 1
          description: >
            Every checklist item has a source_ref that resolves to an
            actual element in the input sources. No invented requirements.
          failure_action: "remove_ungrounded_items_then_recheck_coverage"

        coverage:
          order: 2
          description: >
            Every requirement-level element in every primary and
            validation-reference input source is addressed by at least
            one checklist item.
          failure_action: "return_to_extractor"

        specificity:
          order: 3
          description: >
            Each criterion is concrete enough that two independent judges
            would reach the same pass/fail conclusion given the same artifact.
          failure_action: "return_to_extractor"

  # =========================================================================
  # 3. ARTIFACT GENERATION
  # =========================================================================
  #
  # The generator agent receives three things:
  #   (a) the input sources (read-only context)
  #   (b) the validated checklist (acceptance contract)
  #   (c) phase-specific generation instructions (declared below)
  #
  # It produces two outputs:
  #   (a) the phase artifact in the specified format
  #   (b) a traceability mapping connecting every artifact element back to
  #       the checklist items and input sources it satisfies
  #
  # The traceability mapping is not optional — it is a first-class output.
  # However, the judge MUST independently verify each traceability claim
  # rather than trusting the generator's self-reported mapping. The mapping
  # serves as a starting point for the judge's evaluation, not as proof
  # of satisfaction. See §4 JUDGMENT for the verification requirement.
  # =========================================================================
  artifact_generation:

    generator_agent: "artifact-generator"     # Must differ from judge

    # The file format the generated artifact must conform to.
    output_format: "markdown"                 # markdown | yaml | json | typescript | python | other

    # The file path where the artifact will be written. This is the
    # single source of truth for the artifact location — the same value
    # appears in phase_output.artifact.path by derivation, not by
    # redundant declaration.
    output_path: "path/to/generated/artifact"

    # Phase-specific schema or structure definition for the artifact.
    # This allows traceability mapping refs (artifact_element_ref) to
    # be validated programmatically against a known structure.
    #
    # For structured formats (yaml, json), this should be a JSON Schema
    # or equivalent structural definition. For markdown, this should
    # define the expected heading hierarchy and named anchors. For code,
    # this should define the expected exports, classes, or functions.
    #
    # The artifact_element_id_format field specifies which locator prefix
    # is canonical for referencing elements in this artifact's
    # traceability mapping.
    artifact_schema:
      description: |
        Describe the expected structure of the generated artifact.
        For YAML/JSON: provide field names and types.
        For markdown: provide heading hierarchy and anchor IDs.
        For code: provide expected exports and signatures.
      artifact_element_id_format: "$."       # $. (dot-path) | / (heading) | @ (anchor) | L (line)

    # Phase-specific instructions for the generator. These describe WHAT
    # to produce, not HOW to satisfy individual checklist items (the
    # checklist itself handles that).
    generation_instructions: |
      Describe the structure, conventions, and content expectations
      for the artifact this phase produces.

    # -------------------------------------------------------------------
    # Traceability Mapping
    # -------------------------------------------------------------------
    # Every discrete element in the generated artifact must appear as a
    # key in this mapping. An element with no checklist mapping is
    # either unjustified (should be removed) or reveals a checklist gap
    # (should trigger checklist revision).
    #
    # Direction of links:
    #   artifact_element → checklist_items → input_source_refs
    #
    # This creates a two-hop chain from output back to original input,
    # making it possible to answer:
    #   "Why does the artifact contain X?" → checklist said so → input required it
    #   "Is input requirement Y addressed?" → follow the chain forward
    #
    # IMPORTANT: The generator produces this mapping as a claim. The judge
    # independently verifies each claim during evaluation. See §4.
    #
    # All artifact_element_ref values MUST use the locator prefix declared
    # in artifact_schema.artifact_element_id_format for consistency.
    # -------------------------------------------------------------------
    traceability_mapping:
      - artifact_element_ref: "artifact#$.element.path"
        checklist_item_ids:
          - "CL-{phase}-{sequence}"
        input_source_refs:
          - "path/to/artifact#@element-id"

  # =========================================================================
  # 4. JUDGMENT
  # =========================================================================
  #
  # A separate agent evaluates the artifact against every checklist item.
  # The judge receives: the checklist, the artifact, and the traceability
  # mapping. It does NOT receive the generation instructions — it judges
  # against the checklist contract, not against how the generator was told
  # to work.
  #
  # The judge MUST independently verify each traceability claim made by
  # the generator. The traceability mapping is treated as a set of
  # assertions to be confirmed or refuted, not as trusted evidence.
  # For each traceability entry, the judge checks that the referenced
  # artifact element actually satisfies the linked checklist items.
  # Unverified or incorrect traceability claims are noted in the
  # evaluation's reason field.
  #
  # For each item the judge assigns: pass, fail, or partial.
  #   - pass:    criterion fully satisfied, evidence cited.
  #              artifact_location MUST be non-empty (points to evidence).
  #   - partial: criterion partly met, specific gap described.
  #              artifact_location MUST be non-empty (points to the
  #              partial evidence and/or the location of the gap).
  #   - fail:    criterion not met. artifact_location SHOULD be non-empty
  #              when the failure is a defect in existing content. It MAY
  #              be empty only when the failure is a missing element (the
  #              element does not exist in the artifact at all). When
  #              empty, the reason field MUST explain what is missing.
  #
  # The judge also surfaces UNCOVERED CONCERNS — problems it notices that
  # are not represented in the checklist. These do not affect the verdict
  # directly but are recorded for human review and may inform checklist
  # updates in future iterations of the methodology. Each concern carries
  # a unique ID for tracking and deduplication.
  #
  # Verdict semantics:
  #   pass    — ALL checklist items have result "pass"
  #   revise  — one or more items are "fail" or "partial"
  #   escalate — used only when the revision loop is exhausted
  #
  # Note on partial results: any "partial" is treated as non-passing for
  # the overall verdict. This strict treatment is intentional — it
  # prevents the pipeline from propagating partly-satisfied requirements
  # to downstream phases where the gap compounds. If a phase needs
  # tolerance for partial satisfaction, it should decompose the criterion
  # into finer-grained checklist items where each sub-item can fully pass.
  # =========================================================================
  judgment:

    judge_agent: "artifact-judge"             # Must differ from generator

    evaluations:
      - checklist_item_id: "CL-{phase}-{sequence}"
        result: "pass"                        # pass | fail | partial
        evidence: "What in the artifact demonstrates satisfaction"
        reason: ""                            # Required for fail/partial; empty for pass
        artifact_location: ""                 # MUST be non-empty for pass/partial.
                                              # For fail: non-empty when defect exists in
                                              # artifact; empty only when element is missing
                                              # entirely (reason must explain what is missing).
                                              # Uses element locator grammar.

    uncovered_concerns:
      # Issues the judge noticed that are NOT on the checklist.
      # These do not block the verdict but are preserved in output.
      # Each concern has a unique ID for tracking and deduplication
      # across iterations.
      - id: "UC-{phase}-{sequence}"           # Example: UC-FE-001
        concern: "Description of the issue"
        severity: "low"                       # low | medium | high
        artifact_location: "Where in the artifact this was observed"

    # The judge's overall verdict.
    #   pass     — all checklist items pass (partials count as non-pass)
    #   revise   — one or more items failed or are partial; generator should retry
    #   escalate — used only when the revision loop is exhausted
    verdict: "pass"                           # pass | revise | escalate

  # =========================================================================
  # 5. REVISION LOOP
  # =========================================================================
  #
  # When the verdict is "revise", the generator receives:
  #   (a) the full artifact (not a diff — the complete current state)
  #   (b) the completed checklist with all evaluations and failure reasons
  #
  # Critical rule: the judge re-evaluates ALL checklist items on each
  # iteration, not just the ones that previously failed. This catches
  # regressions where fixing one item breaks another.
  #
  # The loop terminates when:
  #   - The judge returns verdict "pass", OR
  #   - max_iterations is reached, at which point the escalation_policy
  #     determines what happens next.
  # =========================================================================
  revision_loop:

    max_iterations: 3                         # Default; override per phase as needed

    # What happens when max_iterations is exhausted without a pass.
    #   halt               — pipeline stops; no output produced
    #   flag-and-continue  — output is emitted with a warning flag; downstream
    #                        phases see the flag and can decide how to proceed
    #   human-review       — output is parked for human inspection before
    #                        the pipeline continues
    escalation_policy: "halt"                 # halt | flag-and-continue | human-review

    # Tracks the history of each iteration for auditability.
    iteration_log:
      - iteration: 1                          # 1-based sequence number
        timestamp: ""                         # ISO 8601 datetime (e.g., 2026-04-08T14:30:00Z)
                                              # Recorded by the pipeline runner at the start
                                              # of each judge evaluation cycle.
        verdict: "revise"                     # pass | revise
        failed_item_count: 0
        partial_item_count: 0
        passed_item_count: 0
        duration_seconds: 0                   # Wall-clock seconds for this iteration
                                              # (generation + judgment combined).
                                              # Recorded by the pipeline runner.

  # =========================================================================
  # 6. PHASE OUTPUT
  # =========================================================================
  #
  # The complete output bundle of a phase. Downstream phases reference the
  # artifact via its path; the checklist and traceability mapping travel
  # alongside for auditability.
  #
  # Nothing is discarded — even failed iterations are preserved in the
  # iteration_log so that methodology refinement can study failure patterns.
  #
  # The artifact path is derived from artifact_generation.output_path
  # (single source of truth). It is repeated here for consumption by
  # downstream phases and the pipeline orchestrator, but implementations
  # MUST enforce that phase_output.artifact.path ==
  # artifact_generation.output_path. A mismatch is a configuration error.
  # =========================================================================
  phase_output:

    # The approved artifact (or the best-effort artifact if escalated
    # with flag-and-continue).
    artifact:
      path: "path/to/generated/artifact"      # MUST equal artifact_generation.output_path
      format: "markdown"
      status: "approved"                      # approved | escalated

    # The final evaluated checklist with evidence for every item.
    completed_checklist:
      path: "path/to/completed-checklist.yaml"

    # The traceability mapping connecting artifact → checklist → inputs.
    traceability_mapping:
      path: "path/to/traceability-mapping.yaml"

    # Summary statistics for dashboards and pipeline orchestration.
    phase_summary:
      total_iterations: 1
      final_verdict: "pass"                   # pass | escalate
      checklist_item_count: 0
      passed_count: 0
      failed_count: 0
      partial_count: 0
      uncovered_concern_count: 0
      escalation_status: "none"               # none | flagged | halted | human-review-pending


# ═══════════════════════════════════════════════════════════════════════════════
# WORKED EXAMPLE
# ═══════════════════════════════════════════════════════════════════════════════
#
# Phase: Extract features from raw requirements
#
# Scenario: A product owner has written a raw requirements document in
# markdown. This phase extracts a structured feature list with acceptance
# criteria, ensuring every stated requirement is captured.
# ═══════════════════════════════════════════════════════════════════════════════

worked_example:

  phase_processing_unit:

    phase_id: "PH-002-feature-extraction"
    phase_name: "Feature Extraction from Raw Requirements"
    version: "1.0.0"

    # -------------------------------------------------------------------
    # 1. INPUT SOURCES
    # -------------------------------------------------------------------
    input_sources:
      artifacts:
        - ref: "docs/requirements/raw-requirements.md"
          role: "primary"
          format: "markdown"
          description: >
            Free-form requirements document written by the product owner.
            Contains functional requirements (FR-001 through FR-005),
            non-functional requirements (NFR-001 through NFR-002),
            and constraints (CON-001).
          content_hash: "a1b2c3d4e5f6789012345678abcdef0123456789abcdef0123456789abcdef01"
          version: "1.2.0"

        - ref: "docs/requirements/stakeholder-interview-notes.md"
          role: "validation-reference"
          format: "markdown"
          description: >
            Interview transcripts that provide context and rationale
            for the raw requirements. Used to disambiguate, not as
            a primary source of requirements.
          content_hash: "b2c3d4e5f6789012345678abcdef0123456789abcdef0123456789abcdef0123"
          version: ""

      external_references:
        - ref: "https://company.example.com/design-system/v3"
          kind: "coding-standard"
          description: >
            The design system that constrains UI-related features.
            Feature extraction should flag features that imply UI
            elements not present in the design system.

    # -------------------------------------------------------------------
    # 2. CHECKLIST EXTRACTION
    # -------------------------------------------------------------------
    checklist_extraction:

      extractor_agent: "checklist-extractor"

      extraction_focus: |
        Focus on: (a) every FR-*, NFR-*, and CON-* identifier in the raw
        requirements must map to at least one checklist item; (b) implicit
        requirements revealed by cross-referencing with interview notes;
        (c) completeness of acceptance criteria for each feature.

      checklist_items:
        - id: "CL-FE-001"
          source_ref: "docs/requirements/raw-requirements.md#@FR-001"
          criterion: >
            The feature list contains a feature whose description
            covers the user login capability described in FR-001,
            including email and OAuth login methods.
          verification_method: "content_match"

        - id: "CL-FE-002"
          source_ref: "docs/requirements/raw-requirements.md#@FR-002"
          criterion: >
            The feature list contains a feature for the dashboard
            described in FR-002 with sub-features for each of the
            three widget types specified (activity feed, metrics
            summary, quick actions).
          verification_method: "content_match"

        - id: "CL-FE-003"
          source_ref: "docs/requirements/raw-requirements.md#@NFR-001"
          criterion: >
            At least one feature or cross-cutting concern in the
            feature list addresses the 200ms p95 response time
            requirement from NFR-001, with a measurable acceptance
            criterion referencing the specific latency target.
          verification_method: "content_match"

        - id: "CL-FE-004"
          source_ref: "docs/requirements/raw-requirements.md#@FR-001..@FR-005"
          criterion: >
            Every FR-* identifier (FR-001 through FR-005) in the raw
            requirements is referenced by at least one feature in the
            feature list. No FR-* is left unaddressed.
          verification_method: "coverage_query"

        - id: "CL-FE-005"
          source_ref: "docs/requirements/raw-requirements.md#@CON-001"
          criterion: >
            The feature list includes a constraint annotation or
            cross-cutting concern that captures CON-001 (PostgreSQL
            as the only permitted data store).
          verification_method: "content_match"

        - id: "CL-FE-006"
          source_ref: "docs/requirements/raw-requirements.md"
          criterion: >
            Each feature in the feature list has at least one
            acceptance criterion that is specific enough to write
            a test case against (no vague criteria like "works well"
            or "is fast").
          verification_method: "schema_inspection"

      validation:
        validator_agent: "checklist-validator"

        max_validation_iterations: 3
        validation_escalation_policy: "halt"

        validation_feedback:
          failed_check: ""
          problematic_item_ids: []
          uncovered_input_refs: []
          specificity_notes: []

        checks:
          grounding:
            order: 1
            description: >
              Every checklist item has a source_ref that resolves to an
              actual element in the raw requirements document or
              interview notes. No invented requirements.
            failure_action: "remove_ungrounded_items_then_recheck_coverage"

          coverage:
            order: 2
            description: >
              All eight requirement identifiers (FR-001 through FR-005,
              NFR-001, NFR-002, CON-001) have at least one checklist item.
            failure_action: "return_to_extractor"

          specificity:
            order: 3
            description: >
              Each criterion names what to look for and where,
              not just "requirement is addressed".
            failure_action: "return_to_extractor"

    # -------------------------------------------------------------------
    # 3. ARTIFACT GENERATION
    # -------------------------------------------------------------------
    artifact_generation:

      generator_agent: "feature-extractor-generator"
      output_format: "yaml"
      output_path: "docs/features/feature-list.yaml"

      artifact_schema:
        description: |
          Top-level keys:
            features: list of feature objects
            cross_cutting_concerns: list of concern objects

          Feature object fields:
            feature_id: string (FT-{sequence})
            name: string
            description: string (one paragraph)
            source_requirements: list of string (FR-*/NFR-*/CON-* IDs)
            acceptance_criteria: list of string (testable statements)
            sub_features: optional list of feature objects

          Concern object fields:
            concern_id: string (CC-{sequence})
            name: string
            description: string
            source_requirements: list of string
            acceptance_criteria: list of string
        artifact_element_id_format: "$."

      generation_instructions: |
        Produce a structured feature list in YAML. Each feature must have:
          - feature_id: FT-{sequence}
          - name: short descriptive name
          - description: one-paragraph explanation
          - source_requirements: list of FR-*/NFR-*/CON-* IDs this covers
          - acceptance_criteria: list of testable statements
          - sub_features: optional nested features for complex capabilities

        Cross-cutting concerns (performance, data store constraints) should
        appear as a separate section with the same structure.

      traceability_mapping:
        - artifact_element_ref: "docs/features/feature-list.yaml#$.features[0]"
          checklist_item_ids: ["CL-FE-001", "CL-FE-004", "CL-FE-006"]
          input_source_refs:
            - "docs/requirements/raw-requirements.md#@FR-001"

        - artifact_element_ref: "docs/features/feature-list.yaml#$.features[1]"
          checklist_item_ids: ["CL-FE-002", "CL-FE-004", "CL-FE-006"]
          input_source_refs:
            - "docs/requirements/raw-requirements.md#@FR-002"

        - artifact_element_ref: "docs/features/feature-list.yaml#$.cross_cutting_concerns[0]"
          checklist_item_ids: ["CL-FE-003"]
          input_source_refs:
            - "docs/requirements/raw-requirements.md#@NFR-001"

        - artifact_element_ref: "docs/features/feature-list.yaml#$.cross_cutting_concerns[1]"
          checklist_item_ids: ["CL-FE-005"]
          input_source_refs:
            - "docs/requirements/raw-requirements.md#@CON-001"

    # -------------------------------------------------------------------
    # 4. JUDGMENT
    # -------------------------------------------------------------------
    judgment:

      judge_agent: "feature-extraction-judge"

      evaluations:
        - checklist_item_id: "CL-FE-001"
          result: "pass"
          evidence: >
            FT-001 (User Authentication) covers email login and OAuth
            with Google/GitHub as specified in FR-001. Acceptance criteria
            include specific OAuth provider list and session duration.
          reason: ""
          artifact_location: "docs/features/feature-list.yaml#$.features[0]"

        - checklist_item_id: "CL-FE-002"
          result: "partial"
          evidence: >
            FT-002 (Dashboard) lists activity feed and metrics summary
            sub-features, but the quick actions widget is missing.
          reason: >
            FR-002 specifies three widget types: activity feed, metrics
            summary, and quick actions. Only two of three are present.
          artifact_location: "docs/features/feature-list.yaml#$.features[1].sub_features"

        - checklist_item_id: "CL-FE-003"
          result: "pass"
          evidence: >
            Cross-cutting performance concern references 200ms p95
            and names specific measurement methodology (percentile
            measured at the load-balancer over 5-minute windows).
          reason: ""
          artifact_location: "docs/features/feature-list.yaml#$.cross_cutting_concerns[0]"

        - checklist_item_id: "CL-FE-004"
          result: "fail"
          evidence: ""
          reason: >
            FR-004 (notification preferences) has no corresponding
            feature. Only FR-001, FR-002, FR-003, and FR-005 are covered.
            The feature list is missing an entry whose source_requirements
            includes FR-004.
          artifact_location: ""

        - checklist_item_id: "CL-FE-005"
          result: "pass"
          evidence: >
            Cross-cutting data-store constraint lists PostgreSQL
            as sole permitted store, matching CON-001.
          reason: ""
          artifact_location: "docs/features/feature-list.yaml#$.cross_cutting_concerns[1]"

        - checklist_item_id: "CL-FE-006"
          result: "pass"
          evidence: >
            All features include acceptance criteria with specific
            conditions (e.g., "login completes in under 2 seconds",
            "dashboard loads 30 days of data by default").
          reason: ""
          artifact_location: "docs/features/feature-list.yaml#$.features"

      uncovered_concerns:
        - id: "UC-FE-001"
          concern: >
            The raw requirements mention "audit logging" in passing (in the
            paragraph before FR-003) but it is not captured as a separate
            requirement or feature. This may be an implicit requirement
            that the product owner should clarify.
          severity: "medium"
          artifact_location: "docs/requirements/raw-requirements.md#/Section-3"

      verdict: "revise"

    # -------------------------------------------------------------------
    # 5. REVISION LOOP
    # -------------------------------------------------------------------
    revision_loop:

      max_iterations: 3
      escalation_policy: "halt"

      iteration_log:
        - iteration: 1
          timestamp: "2026-04-08T14:30:00Z"
          verdict: "revise"
          failed_item_count: 1            # CL-FE-004
          partial_item_count: 1           # CL-FE-002
          passed_item_count: 4
          duration_seconds: 45

        # After revision: generator adds FT-004 (Notification Preferences)
        # and adds quick-actions sub-feature to FT-002.
        - iteration: 2
          timestamp: "2026-04-08T14:31:12Z"
          verdict: "pass"
          failed_item_count: 0
          partial_item_count: 0
          passed_item_count: 6
          duration_seconds: 38

    # -------------------------------------------------------------------
    # 6. PHASE OUTPUT
    # -------------------------------------------------------------------
    phase_output:

      artifact:
        path: "docs/features/feature-list.yaml"   # Equals artifact_generation.output_path
        format: "yaml"
        status: "approved"

      completed_checklist:
        path: "docs/features/feature-extraction-checklist.yaml"

      traceability_mapping:
        path: "docs/features/feature-extraction-traceability.yaml"

      phase_summary:
        total_iterations: 2
        final_verdict: "pass"
        checklist_item_count: 6
        passed_count: 6
        failed_count: 0
        partial_count: 0
        uncovered_concern_count: 1
        escalation_status: "none"
```