# CD-002 — Phase Processing Unit Schema

> Formal specification of the universal template that every phase in the
> AI-driven development methodology must instantiate. Defines the
> information model (what data flows through a phase) and the control flow
> (which agents act, in what order, under what rules).

---

## 1. Design Rationale

A Phase Processing Unit enforces three structural guarantees:

1. **Adversarial separation.** The agent that *extracts* acceptance criteria,
   the agent that *generates* the artifact, and the agent that *judges* the
   result are distinct instances. This prevents self-confirming bias.

2. **End-to-end traceability.** Every element in the output artifact traces
   back through a checklist item to a specific element in the input sources.
   Traceability is a mandatory output, not optional documentation.

3. **Bounded revision.** Revision loops re-evaluate the entire checklist on
   every pass (to catch regressions) and terminate deterministically after a
   configurable number of iterations, with a clear escalation policy.

---

## 2. YAML Schema

The schema below uses a JSON-Schema-like YAML notation. Each field includes
a `description` comment explaining its purpose.

```yaml
# ═══════════════════════════════════════════════════════════════════════
# Phase Processing Unit — Universal Template Schema
# Version: 1.0.0
# ═══════════════════════════════════════════════════════════════════════
#
# Every phase of the methodology instantiates this template once.
# The schema defines WHAT data is required; phase-specific configuration
# fills in the concrete values.

phase_processing_unit:

  # ─── METADATA ──────────────────────────────────────────────────────
  phase_id:
    type: string
    pattern: "^[A-Z][A-Z0-9_]+$"
    required: true
    description: >
      Unique identifier for this phase instance.
      Convention: uppercase with underscores.
      Examples: REQUIREMENTS_ANALYSIS, HIGH_LEVEL_DESIGN, COMPONENT_DESIGN.

  phase_name:
    type: string
    required: true
    description: >
      Human-readable display name for the phase.

  version:
    type: string
    pattern: "^\\d+\\.\\d+\\.\\d+$"
    required: true
    description: >
      Semantic version of this phase definition. Allows tooling to
      detect breaking changes when the phase template evolves.

  # ─── 1. INPUT SOURCES ─────────────────────────────────────────────
  #
  # What the phase consumes. At least one source must have role
  # "primary" — it is the main artifact being transformed.
  # Additional sources provide validation context or allow the
  # generator to trace decisions back to upstream origins.

  input_sources:
    type: array
    min_items: 1
    required: true
    description: >
      Ordered list of artifacts that feed into this phase.
    items:
      type: object
      required: [ref, role, format]
      properties:

        ref:
          type: string
          description: >
            Path or URI to the source artifact. May be a file path
            relative to the project root, a document ID, or a URL.

        role:
          type: string
          enum: [primary, validation_reference, upstream_traceability]
          description: >
            primary — the main artifact this phase transforms or
              consumes. Exactly one source must have this role.
            validation_reference — used to cross-check completeness or
              consistency (e.g., an API spec, a standard, a glossary).
            upstream_traceability — an earlier-phase artifact included
              so the generator can trace decisions back to their origin.

        format:
          type: string
          description: >
            The format of the source artifact. Informs the extraction
            agent how to parse it.
          examples: [markdown, yaml, json, openapi_spec, python_source]

        description:
          type: string
          required: false
          description: >
            Optional note explaining what this source contributes.

  external_references:
    type: array
    required: false
    description: >
      External resources (standards, API docs, existing codebases)
      that inform this phase but are not artifacts from prior phases.
    items:
      type: object
      required: [ref, description]
      properties:
        ref:
          type: string
          description: >
            URI, file path, or identifier for the external resource.
        description:
          type: string
          description: >
            What this reference provides and how agents should use it.

  # ─── 2. CHECKLIST EXTRACTION ───────────────────────────────────────
  #
  # Two-agent pipeline:
  #   (a) The extractor reads input sources and produces a raw checklist.
  #   (b) The validator audits the checklist for completeness,
  #       groundedness, and specificity.
  #
  # The checklist is the contract that the generator must satisfy
  # and the judge must evaluate against. It is produced BEFORE
  # generation begins — analogous to writing tests before code.

  checklist_extraction:
    type: object
    required: true
    properties:

      extractor:
        type: object
        required: [agent_role]
        description: >
          The agent that reads input sources and produces the raw
          checklist. Must NOT be the same agent instance that will
          generate the artifact.
        properties:
          agent_role:
            type: string
            const: checklist_extractor
          instructions:
            type: string
            required: false
            description: >
              Phase-specific guidance for the extractor, e.g.,
              "focus on behavioral requirements" or "extract data
              model constraints." Supplements the universal extraction
              logic with domain-specific emphasis.

      validator:
        type: object
        required: [agent_role, validation_checks]
        description: >
          A second agent that audits the raw checklist. Must be a
          distinct instance from the extractor.
        properties:
          agent_role:
            type: string
            const: checklist_validator
          validation_checks:
            type: array
            description: >
              The three mandatory checks the validator performs.
              These are structural — every phase applies them.
            items:
              type: object
              required: [check_id, description]
            default:
              - check_id: coverage
                description: >
                  Every requirement in the input sources is
                  represented by at least one checklist item.
              - check_id: groundedness
                description: >
                  Every checklist item traces back to a specific
                  element in the input sources. No invented
                  requirements are allowed.
              - check_id: specificity
                description: >
                  Each item is concrete enough to produce an
                  unambiguous pass/fail judgment. Vague criteria
                  like "should be good" are rejected.

      # ── Checklist item schema ──────────────────────────────────────

      checklist_item_schema:
        type: object
        required: [id, source_ref, criterion, verification_method]
        description: >
          Schema for each individual item in the checklist.
        properties:

          id:
            type: string
            pattern: "^CL-[A-Z][A-Z0-9_]+-\\d{3}$"
            description: >
              Unique identifier. Format: CL-{PHASE_ID}-{three-digit
              sequence number}.
              Example: CL-FEATURE_EXTRACTION-001

          source_ref:
            type: string
            description: >
              Pointer to the specific element in the input source that
              gives rise to this criterion. Must be precise enough to
              locate the requirement without ambiguity.
            examples:
              - "FR-001 section 'Execution Model', bullet 3"
              - "HLD-001 section 'Data Flow', lines 42-48"
              - "raw-requirements.md paragraph 2, sentence 1"

          criterion:
            type: string
            description: >
              A concrete, verifiable statement of what must be true
              for this item to pass. Must be phrased so that an
              automated or semi-automated check can determine pass
              or fail.
            examples:
              - "The feature list includes a feature named 'user-auth'
                with at least one acceptance criterion."
              - "Every raw requirement paragraph maps to at least one
                extracted feature."

          verification_method:
            type: string
            enum:
              - schema_inspection
              - behavioral_trace
              - content_match
              - coverage_query
              - manual_review
            description: >
              How this criterion will be verified during judgment.
              schema_inspection — check the artifact's structure,
                fields, or types against a specification.
              behavioral_trace — simulate or trace execution flow
                through the artifact.
              content_match — search for specific content, keywords,
                or patterns in the artifact.
              coverage_query — verify every element in set A has a
                corresponding element in set B (e.g., every
                requirement has a feature).
              manual_review — requires human judgment. Use sparingly;
                most criteria should be mechanically verifiable.

  # ─── 3. ARTIFACT GENERATION ────────────────────────────────────────
  #
  # The generator agent receives:
  #   - The input sources (section 1)
  #   - The validated checklist (section 2)
  #   - Phase-specific generation instructions
  #
  # It produces TWO outputs:
  #   (a) The phase artifact in the specified format
  #   (b) A traceability mapping linking every artifact element
  #       back to checklist items and input source elements

  artifact_generation:
    type: object
    required: true
    properties:

      generator:
        type: object
        required: [agent_role, output_format]
        description: >
          The agent that produces the phase artifact. Must be a
          separate instance from the extractor, validator, and judge.
        properties:
          agent_role:
            type: string
            const: artifact_generator
          output_format:
            type: string
            description: >
              The format the artifact must be produced in.
            examples: [markdown, yaml, typescript, python]
          generation_instructions:
            type: string
            required: false
            description: >
              Phase-specific instructions for the generator. This is
              where the unique transformation logic of each phase is
              described — e.g., "produce a structured feature list
              from raw requirements" or "decompose the system into
              components with defined interfaces."

      artifact_schema:
        type: object
        required: false
        description: >
          Structural specification for the artifact this phase
          produces. Phase-specific — each phase defines its own
          artifact structure here. When provided, the judge can
          verify structural conformance in addition to checklist
          satisfaction.

      # ── Traceability mapping schema ────────────────────────────────
      #
      # The traceability mapping is a MANDATORY output of generation,
      # not optional metadata. It provides the chain:
      #   artifact_element → checklist_item(s) → input_source_element(s)
      #
      # This chain is what allows downstream phases and human reviewers
      # to answer: "Why does this element exist? What requirement
      # demanded it?"

      traceability_mapping_schema:
        type: object
        required: true
        description: >
          Schema for the traceability mapping that accompanies every
          generated artifact.
        properties:
          entries:
            type: array
            required: true
            items:
              type: object
              required:
                - artifact_element_ref
                - checklist_item_ids
                - input_source_refs
              properties:

                artifact_element_ref:
                  type: string
                  description: >
                    Pointer to a specific element in the generated
                    artifact. Must be precise enough to locate the
                    element (e.g., section heading, field name,
                    function signature, list item index).

                checklist_item_ids:
                  type: array
                  items:
                    type: string
                    pattern: "^CL-[A-Z][A-Z0-9_]+-\\d{3}$"
                  min_items: 1
                  description: >
                    The checklist item(s) this artifact element
                    satisfies. Every artifact element must satisfy at
                    least one checklist item (no orphan elements).

                input_source_refs:
                  type: array
                  items:
                    type: string
                  min_items: 1
                  description: >
                    The input source element(s) that ultimately
                    require this artifact element. Provides end-to-end
                    traceability: source requirement -> checklist ->
                    artifact.

  # ─── 4. JUDGMENT ───────────────────────────────────────────────────
  #
  # A separate agent evaluates the artifact against EVERY checklist
  # item. The judge also flags concerns it notices that are NOT on
  # the checklist — these represent potential gaps in the input
  # sources or the extraction process.

  judgment:
    type: object
    required: true
    properties:

      judge:
        type: object
        required: [agent_role]
        description: >
          The agent that evaluates the artifact. Must NOT be the
          generator — this separation is a structural guarantee
          against self-confirming bias.
        properties:
          agent_role:
            type: string
            const: artifact_judge
          judgment_instructions:
            type: string
            required: false
            description: >
              Phase-specific instructions for the judge, e.g.,
              "pay special attention to data model completeness"
              or "verify all edge cases are addressed."

      # ── Per-item evaluation schema ─────────────────────────────────

      evaluation_schema:
        type: object
        required: true
        description: >
          Schema for the per-item evaluation the judge produces.
          Every checklist item receives exactly one evaluation entry.
        properties:
          item_evaluation:
            type: object
            required: [checklist_item_id, result]
            properties:

              checklist_item_id:
                type: string
                pattern: "^CL-[A-Z][A-Z0-9_]+-\\d{3}$"

              result:
                type: string
                enum: [pass, fail, partial]
                description: >
                  pass — criterion fully satisfied.
                  fail — criterion not satisfied.
                  partial — criterion partially satisfied; some elements
                    present but incomplete or incorrect.

              reason:
                type: string
                required_when: "result in [fail, partial]"
                description: >
                  Mandatory for fail and partial. A specific explanation
                  of what is wrong or missing. Must be actionable — the
                  generator should be able to fix the issue using only
                  this reason and the original checklist item.

              artifact_pointer:
                type: string
                required: false
                description: >
                  Points to the specific location in the artifact that
                  is deficient (for fail/partial) or that satisfies the
                  criterion (for pass, as evidence).

      # ── Verdict schema ─────────────────────────────────────────────

      verdict_schema:
        type: object
        required: [verdict]
        description: >
          The judge's overall verdict, plus any concerns not captured
          by the checklist.
        properties:

          verdict:
            type: string
            enum: [pass, revise, escalate]
            description: >
              pass — all checklist items pass; artifact is approved.
              revise — one or more items failed or are partial; return
                to the generator for revision.
              escalate — a critical uncovered concern was found, or
                max revision iterations were exhausted.

          uncovered_concerns:
            type: array
            required: false
            description: >
              Issues the judge notices that are NOT on the checklist.
              These may indicate gaps in the input sources, missing
              requirements, or emergent problems. They do NOT
              automatically block the phase — only "critical" severity
              triggers escalation.
            items:
              type: object
              required: [concern, severity]
              properties:
                concern:
                  type: string
                  description: >
                    Description of the issue. Should be specific
                    enough to act on.
                severity:
                  type: string
                  enum: [info, warning, critical]
                  description: >
                    info — worth noting; does not block the phase.
                    warning — should be addressed but does not block.
                    critical — blocks the phase; triggers escalation.

  # ─── 5. REVISION LOOP ─────────────────────────────────────────────
  #
  # If the verdict is "revise," the generator receives the annotated
  # checklist (with failure reasons) and the full artifact, and
  # produces a revised version. The judge then re-evaluates ALL items
  # — not just previously failed ones — because a revision may
  # introduce regressions.

  revision_loop:
    type: object
    required: true
    properties:

      max_iterations:
        type: integer
        minimum: 1
        default: 3
        description: >
          Maximum number of generate-then-judge cycles before the
          phase automatically escalates. Each iteration is one
          generator pass followed by one full judge pass.

      escalation_policy:
        type: string
        enum: [halt, flag_and_continue, human_review]
        default: human_review
        description: >
          What happens when max_iterations is reached without a
          passing verdict.
          halt — stop the entire pipeline immediately.
          flag_and_continue — mark the phase as failed but allow
            downstream phases to proceed. They receive the
            best-effort artifact with a warning flag.
          human_review — pause the pipeline and request human
            intervention before proceeding.

      revision_context:
        type: object
        required: false
        description: >
          Specifies what the generator receives on each revision pass.
          These are structural guarantees — the generator always gets
          the full picture, never just the diff.
        properties:
          includes:
            type: array
            items:
              type: string
            default:
              - full_artifact_from_previous_iteration
              - complete_annotated_checklist_with_results_and_reasons
              - traceability_mapping_from_previous_iteration
              - uncovered_concerns_from_judge

  # ─── 6. PHASE OUTPUT ──────────────────────────────────────────────
  #
  # The complete output bundle. Downstream phases consume this as
  # their input. The bundle always includes the artifact, the
  # evidence trail (checklist + traceability), and operational
  # metadata about how the phase executed.

  phase_output:
    type: object
    required: true
    properties:

      artifact:
        type: object
        required: [ref, format, status]
        description: >
          The approved artifact, or the best-effort artifact if the
          phase escalated with flag_and_continue policy.
        properties:
          ref:
            type: string
            description: >
              Path or URI where the artifact is stored.
          format:
            type: string
            description: >
              Format of the stored artifact.
          status:
            type: string
            enum: [approved, escalated_best_effort]
            description: >
              approved — passed all checklist items.
              escalated_best_effort — did not pass; downstream
                consumers should treat with caution.

      checklist:
        type: object
        required: [ref, items_total, items_pass, items_fail, items_partial]
        description: >
          The completed checklist with per-item evaluation results.
          Serves as the evidence record for the phase.
        properties:
          ref:
            type: string
            description: >
              Path or URI where the completed checklist is stored.
          items_total:
            type: integer
          items_pass:
            type: integer
          items_fail:
            type: integer
          items_partial:
            type: integer

      traceability_mapping:
        type: object
        required: [ref]
        description: >
          The final traceability mapping from the last successful
          (or best-effort) generation pass.
        properties:
          ref:
            type: string
            description: >
              Path or URI where the mapping is stored.

      phase_summary:
        type: object
        required: [verdict, revision_count]
        description: >
          Operational metadata about how the phase executed.
          Useful for pipeline dashboards, audit logs, and
          retrospectives.
        properties:
          verdict:
            type: string
            enum: [pass, escalated]
            description: >
              Final outcome of the phase.
          revision_count:
            type: integer
            description: >
              Number of revision cycles needed. 0 means the
              artifact passed on the first attempt.
          uncovered_concerns:
            type: array
            items:
              type: string
            description: >
              Aggregated list of uncovered concerns from all
              judgment iterations (deduplicated).
          escalation_status:
            type: string
            enum: [none, halted, flagged_continuing, awaiting_human]
            default: none
            description: >
              Current escalation state of the phase.
              none — phase passed normally.
              halted — pipeline stopped due to escalation policy.
              flagged_continuing — phase failed but downstream
                phases are proceeding with the best-effort artifact.
              awaiting_human — pipeline paused pending human review.
```

---

## 3. Agent Separation Rules

The schema enforces four distinct agent roles. These roles MUST be
instantiated as separate agent invocations — they must not share
conversation context, to prevent information leakage that would
undermine the adversarial separation guarantee.

| Role                   | Reads                                                 | Produces                         |
|------------------------|-------------------------------------------------------|----------------------------------|
| checklist_extractor    | input sources                                         | raw checklist                    |
| checklist_validator    | raw checklist, input sources                          | validated checklist (or rejection)|
| artifact_generator     | input sources, validated checklist, generation instructions | artifact + traceability mapping |
| artifact_judge         | validated checklist, artifact, traceability mapping   | evaluation + verdict             |

---

## 4. Control Flow

```
Input Sources
     |
     v
[checklist_extractor] ──> Raw Checklist
     |                         |
     |                         v
     |                [checklist_validator]
     |                     |         |
     |                  reject     approve
     |                     |         |
     |                     v         v
     |              (re-extract)  Validated Checklist
     |                               |
     +───────────────────────────────>+
                                     |
                                     v
                          [artifact_generator]
                                     |
                          Artifact + Traceability Mapping
                                     |
                                     v
                            [artifact_judge]
                              /      |      \
                           pass    revise   escalate
                            |        |         |
                            v        v         v
                        PHASE     (loop)    ESCALATION
                        OUTPUT               POLICY
```

---

## 5. Worked Example — FEATURE_EXTRACTION Phase

This minimal example shows one complete phase instance: extracting
structured features from raw requirements.

### 5.1 Phase Configuration

```yaml
phase_processing_unit:
  phase_id: FEATURE_EXTRACTION
  phase_name: "Feature Extraction from Raw Requirements"
  version: "1.0.0"

  input_sources:
    - ref: "raw-requirements.md"
      role: primary
      format: markdown
      description: >
        Unstructured requirements document written by the product
        owner. Contains paragraphs describing desired system behavior.
    - ref: "glossary.md"
      role: validation_reference
      format: markdown
      description: >
        Domain glossary defining key terms. Used to ensure extracted
        features use consistent terminology.

  external_references:
    - ref: "https://example.com/api/v2/openapi.yaml"
      description: >
        Existing API specification. Features that extend existing
        endpoints should reference them.

  checklist_extraction:
    extractor:
      agent_role: checklist_extractor
      instructions: >
        Read each paragraph of raw-requirements.md. For every
        distinct user-facing behavior or capability described,
        produce one checklist item requiring that the feature list
        includes a corresponding entry. Also produce items verifying
        that terminology matches glossary.md.
    validator:
      agent_role: checklist_validator
      validation_checks:
        - check_id: coverage
          description: >
            Every paragraph in raw-requirements.md that describes
            a behavior is represented by at least one checklist item.
        - check_id: groundedness
          description: >
            Every checklist item traces to a specific paragraph in
            raw-requirements.md or a term in glossary.md.
        - check_id: specificity
          description: >
            Each criterion can be verified by inspecting the feature
            list artifact — no subjective judgment needed.

  artifact_generation:
    generator:
      agent_role: artifact_generator
      output_format: yaml
      generation_instructions: >
        Produce a YAML feature list. Each feature has: id (FT-NNN),
        name, description, source_paragraph (which paragraph in
        raw-requirements.md it comes from), and acceptance_criteria
        (a list of testable conditions).
    artifact_schema:
      type: object
      properties:
        features:
          type: array
          items:
            type: object
            required: [id, name, description, source_paragraph, acceptance_criteria]
            properties:
              id:
                type: string
                pattern: "^FT-\\d{3}$"
              name:
                type: string
              description:
                type: string
              source_paragraph:
                type: integer
              acceptance_criteria:
                type: array
                items:
                  type: string
                min_items: 1

  judgment:
    judge:
      agent_role: artifact_judge
      judgment_instructions: >
        For each checklist item, inspect the feature list YAML to
        determine if the criterion is met. Use the traceability
        mapping to verify end-to-end coverage. Flag any features
        that appear in the artifact but have no corresponding
        checklist item (potential invented requirements from the
        generator).

  revision_loop:
    max_iterations: 2
    escalation_policy: human_review
```

### 5.2 Sample Raw Requirements Input

```markdown
The system shall allow users to upload CSV files containing transaction
data. Uploaded files must be validated for correct column headers before
processing. (paragraph 1)

Users should be able to view a dashboard showing transaction summaries
grouped by category. The dashboard must update within 5 seconds of new
data being uploaded. (paragraph 2)

The system must support exporting filtered transaction data as PDF
reports. Reports must include the date range and applied filters in
the header. (paragraph 3)
```

### 5.3 Extracted Checklist (after validation)

```yaml
checklist:
  - id: CL-FEATURE_EXTRACTION-001
    source_ref: "raw-requirements.md, paragraph 1, sentence 1"
    criterion: >
      The feature list contains a feature whose description covers
      CSV file upload for transaction data.
    verification_method: content_match

  - id: CL-FEATURE_EXTRACTION-002
    source_ref: "raw-requirements.md, paragraph 1, sentence 2"
    criterion: >
      The feature list contains a feature or acceptance criterion
      addressing column header validation before processing.
    verification_method: content_match

  - id: CL-FEATURE_EXTRACTION-003
    source_ref: "raw-requirements.md, paragraph 2, sentence 1"
    criterion: >
      The feature list contains a feature whose description covers
      a dashboard displaying transaction summaries grouped by
      category.
    verification_method: content_match

  - id: CL-FEATURE_EXTRACTION-004
    source_ref: "raw-requirements.md, paragraph 2, sentence 2"
    criterion: >
      A feature or acceptance criterion specifies that the dashboard
      updates within 5 seconds of new data upload.
    verification_method: content_match

  - id: CL-FEATURE_EXTRACTION-005
    source_ref: "raw-requirements.md, paragraph 3, sentence 1"
    criterion: >
      The feature list contains a feature covering export of filtered
      transaction data as PDF reports.
    verification_method: content_match

  - id: CL-FEATURE_EXTRACTION-006
    source_ref: "raw-requirements.md, paragraph 3, sentence 2"
    criterion: >
      A feature or acceptance criterion requires that PDF reports
      include date range and applied filters in the header.
    verification_method: content_match

  - id: CL-FEATURE_EXTRACTION-007
    source_ref: "glossary.md (general)"
    criterion: >
      All feature names and descriptions use terminology consistent
      with glossary.md. No undefined domain terms are introduced.
    verification_method: coverage_query
```

### 5.4 Generated Artifact (feature list)

```yaml
features:
  - id: FT-001
    name: csv-transaction-upload
    description: >
      Allow users to upload CSV files containing transaction data.
    source_paragraph: 1
    acceptance_criteria:
      - "System accepts CSV files via upload interface"
      - "Column headers are validated against expected schema before processing"
      - "Invalid files are rejected with a descriptive error message"

  - id: FT-002
    name: transaction-dashboard
    description: >
      Display a dashboard showing transaction summaries grouped
      by category.
    source_paragraph: 2
    acceptance_criteria:
      - "Dashboard displays transaction totals grouped by category"
      - "Dashboard updates within 5 seconds of new data upload"

  - id: FT-003
    name: pdf-report-export
    description: >
      Export filtered transaction data as PDF reports with metadata
      headers.
    source_paragraph: 3
    acceptance_criteria:
      - "Users can export filtered transaction data as PDF"
      - "PDF header includes the selected date range"
      - "PDF header includes the applied filters"
```

### 5.5 Traceability Mapping

```yaml
traceability_mapping:
  - artifact_element_ref: "FT-001 (csv-transaction-upload)"
    checklist_item_ids: [CL-FEATURE_EXTRACTION-001, CL-FEATURE_EXTRACTION-007]
    input_source_refs: ["raw-requirements.md paragraph 1 sentence 1"]

  - artifact_element_ref: "FT-001 acceptance_criteria[1] (column header validation)"
    checklist_item_ids: [CL-FEATURE_EXTRACTION-002]
    input_source_refs: ["raw-requirements.md paragraph 1 sentence 2"]

  - artifact_element_ref: "FT-002 (transaction-dashboard)"
    checklist_item_ids: [CL-FEATURE_EXTRACTION-003, CL-FEATURE_EXTRACTION-007]
    input_source_refs: ["raw-requirements.md paragraph 2 sentence 1"]

  - artifact_element_ref: "FT-002 acceptance_criteria[1] (5-second update)"
    checklist_item_ids: [CL-FEATURE_EXTRACTION-004]
    input_source_refs: ["raw-requirements.md paragraph 2 sentence 2"]

  - artifact_element_ref: "FT-003 (pdf-report-export)"
    checklist_item_ids: [CL-FEATURE_EXTRACTION-005, CL-FEATURE_EXTRACTION-007]
    input_source_refs: ["raw-requirements.md paragraph 3 sentence 1"]

  - artifact_element_ref: "FT-003 acceptance_criteria[1,2] (header metadata)"
    checklist_item_ids: [CL-FEATURE_EXTRACTION-006]
    input_source_refs: ["raw-requirements.md paragraph 3 sentence 2"]
```

### 5.6 Judgment Result

```yaml
evaluation:
  - checklist_item_id: CL-FEATURE_EXTRACTION-001
    result: pass
    artifact_pointer: "FT-001"

  - checklist_item_id: CL-FEATURE_EXTRACTION-002
    result: pass
    artifact_pointer: "FT-001 acceptance_criteria[1]"

  - checklist_item_id: CL-FEATURE_EXTRACTION-003
    result: pass
    artifact_pointer: "FT-002"

  - checklist_item_id: CL-FEATURE_EXTRACTION-004
    result: pass
    artifact_pointer: "FT-002 acceptance_criteria[1]"

  - checklist_item_id: CL-FEATURE_EXTRACTION-005
    result: pass
    artifact_pointer: "FT-003"

  - checklist_item_id: CL-FEATURE_EXTRACTION-006
    result: pass
    artifact_pointer: "FT-003 acceptance_criteria[1,2]"

  - checklist_item_id: CL-FEATURE_EXTRACTION-007
    result: pass
    reason: >
      All terms (CSV, transaction, dashboard, category, PDF, report)
      are consistent with glossary.md definitions.

verdict: pass

uncovered_concerns:
  - concern: >
      FT-001 includes an acceptance criterion about error messages
      for invalid files ("Invalid files are rejected with a
      descriptive error message") that is not explicitly stated in
      raw-requirements.md. This is reasonable behavior but was
      generated without a source requirement.
    severity: info
```

### 5.7 Phase Output

```yaml
phase_output:
  artifact:
    ref: "feature-list.yaml"
    format: yaml
    status: approved

  checklist:
    ref: "checklist-feature-extraction.yaml"
    items_total: 7
    items_pass: 7
    items_fail: 0
    items_partial: 0

  traceability_mapping:
    ref: "traceability-feature-extraction.yaml"

  phase_summary:
    verdict: pass
    revision_count: 0
    uncovered_concerns:
      - >
        FT-001 includes an acceptance criterion for error messages
        on invalid files that has no explicit source requirement
        (severity: info).
    escalation_status: none
```
