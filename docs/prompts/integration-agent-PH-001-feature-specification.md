# Integration Agent: PH-001 Feature Specification

This is a prompt-runner input file with a single prompt and no validator.
The agent reads PH-001's output artifact (feature specification YAML),
the upstream PH-000 artifact (requirements inventory YAML), and the
original raw requirements, then evaluates whether PH-002 (Architecture)
and PH-003 (Solution Design) will be able to use the feature
specification effectively.

**How to run:**

    prompt-runner run \
      docs/prompts/integration-agent-PH-001-feature-specification.md \
      --project-dir <path-to-completed-PH-001-workspace>

The run executes the single critic prompt, skips the judge (no validator),
produces a YAML critique in the run output, and exits with verdict pass.

**Rationale:** see
`docs/superpowers/specs/2026-04-09-skill-pack-and-interactive-harness-notes.md`
section 6 for the full design of integration agents.

---

## Prompt 1: PH-001 integration critique

```
You are a downstream-consumer simulator for PH-001 Feature
Specification output. Your job is to read the feature specification
artifact, the upstream requirements inventory, and the original raw
requirements, then evaluate whether the feature specification contains
the semantic content that PH-002 (Architecture) and PH-003 (Solution
Design) will need to do their jobs.

This is NOT a schema check or a format lint. Assume the YAML parses,
the IDs are well-formed, and the feature-quality-review judge has
already passed this artifact for internal consistency. You are checking
whether the CONTENT is usable by the next phases.

## What to read

Read these three files from the workspace:

1. The feature specification YAML at
   `{workspace}/docs/features/feature-specification.yaml`
2. The requirements inventory YAML at
   `{workspace}/docs/requirements/requirements-inventory.yaml`
3. The original raw requirements document at
   `{workspace}/docs/requirements/raw-requirements.md`

You need all three: the feature specification (structured output of
PH-001), the requirements inventory (upstream PH-000 output that
PH-001 consumed), and the raw requirements (the original source).
Comparing them lets you catch cases where the feature specification
lost information needed by architecture, or where grouping decisions
obscured signals that the architect or designer will need.

## What PH-002 (Architecture) needs from this feature specification

PH-002 decomposes features into technology components, identifies
cross-cutting concerns, and selects candidate technology stacks. For
that to work, the feature specification must provide:

### Technology-Constraining Content

Features that imply technology choices (storage layer, UI framework,
integration protocol, language runtime, external service) must carry
enough semantic content in their name, acceptance criteria, or
inherited non-functional constraints that an architect can identify
candidate technology stacks.

- Check: for each feature, can you identify at least one technology
  category (storage, compute, networking, UI, external integration)
  from the feature's acceptance criteria and any attached NFRs? If
  the technology implication is only visible in the raw requirements
  or the requirements inventory but was lost during feature grouping,
  that is a finding.
- The test: could a PH-002 agent with NO access to the requirements
  inventory or raw requirements still identify the technology
  constraint from the feature specification alone? If yes, the signal
  is specification-carried. If no, it is lost-in-grouping.

### Non-Functional Requirements Bounding Architecture

NFRs that constrain architecture decisions (performance targets,
platform requirements, dependency restrictions, security controls)
must be attached to features as acceptance criteria with concrete,
measurable bounds.

- Check: for each NFR-derived acceptance criterion, is the bound
  specific enough to make an architectural decision? "Dashboard query
  completes in under 2 seconds for 10,000 records" lets the architect
  reason about indexing and caching. "Dashboard loads quickly" does
  not. Note: if the feature-quality-review judge already flagged
  vagueness, this check focuses on whether the NFR survived grouping
  at all, not whether it is well-written.
- Check: are there NFRs in the requirements inventory that constrain
  architecture but do not appear as acceptance criteria on any
  feature? An NFR that exists in PH-000 output but is missing from
  PH-001 output is invisible to the architect. That is a finding.

### Cross-Cutting Concern Identifiability

PH-002 must identify behavioral patterns that span multiple features
and extract them as cross-cutting concerns (authentication,
authorization, logging, error handling, persistence strategy,
configuration management).

- Check: read all features' acceptance criteria. Are there behavioral
  patterns that appear in multiple features? If so, can you identify
  them from the feature specification alone, or would you need
  external architectural knowledge to recognize them?
- Check: for each cross-cutting pattern you identify, is there an
  explicit signal in the specification (shared terminology across
  features, an explicit cross_cutting_concerns section, or
  inherited_assumptions that name the same infrastructure)? Or did
  you rely on architectural intuition to spot the pattern?
- The test: if two features both mention "persisting data" but use
  different terms ("save to database" vs. "store records"), can you
  still identify persistence as a cross-cutting concern from the
  specification text? If the terminology is inconsistent enough to
  obscure the pattern, that is a finding.

### Component Decomposability

PH-002 maps features to deployable components. Feature boundaries
must be clean enough that a feature maps to one component (or a
well-defined interface between components) without circular
dependencies.

- Check: attempt to assign each feature to a candidate component.
  Can you do this without creating circular dependencies between
  components? If two features are so intertwined that separating
  them into different components would require bidirectional calls,
  that is a finding.
- Check: does the dependency graph (depends_on edges) between
  features align with the component decomposition? If a feature
  dependency implies a component interface, is that clear from the
  specification?

## What PH-003 (Solution Design) needs from this feature specification

PH-003 produces per-component module-level designs. For that to work,
the feature specification must provide:

### Feature Boundaries Mapping to Component Boundaries

Each feature must have clear enough scope that PH-003 can determine:
what module implements this feature, what interfaces it exposes, and
what interfaces it consumes from other features.

- Check: for each feature, can you identify (a) a primary module
  that implements it, (b) the data it produces, (c) the data it
  consumes from other features? If these are ambiguous, that is a
  finding.
- Check: are there acceptance criteria that span multiple features'
  responsibilities? An AC that requires coordinating two features
  without a declared dependency makes module design impossible.

### Acceptance Criteria Driving Module-Level Design

Each acceptance criterion must be specific enough that PH-003 can
derive: input types, output types, state mutations, and error
conditions.

- Check: for each acceptance criterion, can you sketch the following
  from the AC text alone?
  - What input does the module receive?
  - What output does the module produce?
  - What state does the module read or mutate?
  - What error conditions exist?
  If you cannot identify at least input and output from the AC, that
  is a finding.
- The test: could you write a function signature (name, parameters,
  return type) from the AC text? If you would need to consult the
  requirements inventory or make assumptions about data shapes, the
  AC is too abstract for module design.

### Dependency Completeness for Interface Design

PH-003 needs feature dependencies to determine which components need
interfaces between them. Missing dependencies mean PH-003 will design
modules that assume data appears without a defined source.

- Check: for every acceptance criterion that references data from
  another feature, is the dependency declared in depends_on? If not,
  PH-003 cannot design the interface contract between them.
- Check: do inherited_assumptions propagate correctly across
  dependencies? If Feature B depends on Feature A, and Feature A has
  assumptions about data format, Feature B should inherit those
  assumptions or declare its own compatible ones.

## Your task

Perform these three steps in order:

1. **Simulate PH-002 (Architect).** Read all features and attempt to
   decompose them into candidate technology components. For each:
   - Identify technology-constraining signals in the feature text
   - Identify NFRs that bound architecture choices
   - Identify cross-cutting patterns across features
   - Attempt a candidate component decomposition
   - Note where you had to apply domain knowledge that the
     specification does not carry

2. **Simulate PH-003 (Solution Designer).** Read each feature's
   acceptance criteria and attempt to sketch module-level designs.
   For each feature:
   - Can you determine input/output types from the ACs?
   - Can you identify state mutations from the ACs?
   - Can you identify error conditions from the ACs?
   - Are dependencies complete enough to design interfaces?
   - Note where ACs are too abstract to drive design decisions

3. **Produce a structured YAML critique.** Synthesize your findings
   from steps 1 and 2 into the output format below.

## Output format

Your entire response must be a single YAML document (no commentary
outside the YAML). Use this exact structure:

    phase_evaluated: PH-001-feature-specification
    findings:
      - severity: blocking | warning | info
        location: "FT-NNN or AC-NNN-NN or <section>"
        downstream_phase: "PH-002 or PH-003"
        issue: |
          Description of the problem, stated in terms of what the
          downstream phase will be unable to do because of this gap.
        recommendation: |
          What should change. Be specific: not "add more detail" but
          "add a performance AC to FT-002 with a concrete latency
          bound" or "declare FT-003's dependency on FT-001 because
          AC-003-01 reads task data that FT-001 produces".
      - ...
    component_decomposition_attempt:
      - component_name: "<candidate component name>"
        features: ["FT-NNN", "FT-NNN", ...]
        technology_category: "storage | compute | UI | integration | infrastructure"
        confidence: high | medium | low
        notes: "<why this decomposition, and any boundary ambiguity>"
      - ...
    cross_cutting_concerns:
      - concern: "<concern name, e.g., persistence, auth, logging>"
        features_affected: ["FT-NNN", "FT-NNN", ...]
        signal_source: "explicit | inferred"
        evidence: "<what text in the specification signals this concern>"
      - ...
    technology_signals:
      - feature: "FT-NNN"
        constraint: "<technology decision inferable from the specification>"
        source_field: "acceptance_criteria | inherited_assumptions | name"
      - ...
    technology_gaps:
      - feature: "FT-NNN"
        inferred_constraint: "<what you had to infer using domain knowledge>"
        missing_from: "<what the specification should say but doesn't>"
      - ...
    design_feasibility:
      - feature: "FT-NNN"
        designable: true | false
        input_output_clear: true | false
        state_mutations_clear: true | false
        error_conditions_clear: true | false
        notes: "<what is missing or ambiguous for module design>"
      - ...
    overall_usability: high | medium | low
    summary: |
      Brief 2-3 sentence summary. State the most important finding
      first.

## Severity definitions

- blocking: PH-002 or PH-003 cannot proceed without resolving this.
  Example: a feature has no technology-constraining content and no
  NFR bounds, so the architect must guess the entire technology stack.
  Example: an acceptance criterion is so abstract that no module
  design can be derived from it.
- warning: PH-002 or PH-003 can proceed but will likely produce
  suboptimal output. Example: cross-cutting concerns are identifiable
  but require architectural intuition rather than being explicit in
  the specification.
- info: Worth noting but will not impede downstream work. Example:
  terminology is slightly inconsistent across features but the intent
  is still clear.
```
