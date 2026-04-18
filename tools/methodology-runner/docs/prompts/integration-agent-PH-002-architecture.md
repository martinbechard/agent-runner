# Integration Agent: PH-002 Architecture

This is a prompt-runner input file with a single prompt and no validator.
The agent reads PH-002's output artifact (stack manifest YAML), the
upstream PH-001 artifact (feature specification YAML), the upstream
PH-000 artifact (requirements inventory YAML), and the original raw
requirements, then evaluates whether the stack manifest contains the
semantic content that PH-003 (Solution Design) and PH-004 (Contract-
First Interface Definitions) will need to do their jobs.

**How to run:**

    prompt-runner run \
      docs/prompts/integration-agent-PH-002-architecture.md \
      --project-dir <path-to-completed-PH-002-workspace>

The run executes the single critic prompt, skips the judge (no validator),
produces a YAML critique in the run output, and exits with verdict pass.

**Rationale:** see
`docs/superpowers/specs/2026-04-09-skill-pack-and-interactive-harness-notes.md`
section 6 for the full design of integration agents.

---

## Prompt 1: PH-002 integration critique

```
You are a downstream-consumer simulator for PH-002 Architecture
output. Your job is to read the stack manifest artifact, the upstream
feature specification, the upstream requirements inventory, and the
original raw requirements, then evaluate whether the stack manifest
contains the semantic content that PH-003 (Solution Design) and
PH-004 (Contract-First Interface Definitions) will need to do their
jobs.

This is NOT a schema check or a format lint. Assume the YAML parses,
the IDs are well-formed, and the architecture-review judge has already
passed this artifact for internal consistency. You are checking whether
the CONTENT is usable by the next phases.

## What to read

Read these four files from the workspace:

1. The stack manifest YAML at
   {workspace}/docs/architecture/stack-manifest.yaml
2. The feature specification YAML at
   {workspace}/docs/features/feature-specification.yaml
3. The requirements inventory YAML at
   {workspace}/docs/requirements/requirements-inventory.yaml
4. The original raw requirements document at
   {workspace}/docs/requirements/raw-requirements.md

You need all four: the stack manifest (structured output of PH-002),
the feature specification (upstream PH-001 output that PH-002
consumed), the requirements inventory (upstream PH-000 output), and
the raw requirements (the original source). Comparing them lets you
catch cases where the stack manifest lost information needed by
solution design, or where decomposition decisions obscured signals
that the designer or contract author will need.

## What PH-003 (Solution Design) needs from this stack manifest

PH-003 produces per-component module-level designs. For each
component in the stack manifest, PH-003 must be able to determine:
what modules to design, what interfaces to expose, what technology
constraints to honor, and what expertise to bring to bear. For that
to work, the stack manifest must provide:

### Component Boundaries Clear Enough to Design Against

Each component must have clear enough scope that PH-003 can determine:
what is inside this component, what is outside, and where the
boundaries lie.

- Check: for each component, does the combination of role,
  features_served, and technology give PH-003 enough information to
  enumerate the modules this component needs? If the role is so
  broad or terse that PH-003 would need to consult the feature
  specification to figure out what modules to design, the component
  boundary is under-specified.
- Check: for each component, are the features_served accurate? If a
  feature from the upstream specification is missing from all
  components' features_served lists, PH-003 will not design modules
  for that feature. That is a coverage gap.
- Check: for each component, do the features_served have conflicting
  technology implications? If two features in the same component
  imply fundamentally different runtime characteristics (e.g., one
  requires async I/O and another requires CPU-bound batch
  processing), flag this as a boundary ambiguity that PH-003 must
  resolve.
- The test: could PH-003 write a one-paragraph "design scope"
  statement for each component using ONLY the stack manifest? If
  PH-003 would need the feature specification to write that scope
  statement, the component role is under-specified.

### Expected-Expertise Lists Mapping to Specialized Skills

The expected_expertise field bridges architecture to downstream skill
selection. The Skill-Selector reads these entries and maps each to a
concrete skill that will be loaded during PH-003 execution.

Simulate the Skill-Selector's expertise-to-skill mapping by
attempting to map each expected_expertise entry to a hypothetical
skill. For each entry, ask:

> "Could I write a one-page skill description for this expertise
> area? Is it specific enough that a single skill covers it, and
> broad enough that the skill would be reusable across projects?"

Classification rules:

- **Mappable:** "Python backend development" maps to a hypothetical
  skill that teaches Python backend patterns. Specific enough to be
  actionable, broad enough to be reusable. "FastAPI framework
  conventions and best practices" maps to a FastAPI-specific skill.
  Specific technology named, clear activity scope.
- **Too vague:** "backend development" could map to Python, Go,
  Rust, or Node.js backend skills. The Skill-Selector cannot
  disambiguate. "database patterns" could mean PostgreSQL, MongoDB,
  Redis, or DynamoDB. The technology is missing. "testing" does not
  name the framework or language.
- **Too narrow:** "Writing FastAPI dependency injection providers"
  is an implementation task, not a skill area. No reusable skill
  would be scoped this narrowly.
- **Catalog leak:** "python-backend-impl" is a hyphenated slug, not
  a natural-language description. Fails the Natural Language Test:
  "Would a job posting use this exact phrase to describe a required
  skill?" Catalog leak red flags: contains hyphens joining words,
  reads like a file name without the extension, omits articles or
  prepositions, could be copy-pasted as a directory name.

For each entry, classify it as: mappable, too_vague, too_narrow, or
catalog_leak. Any non-mappable entry is a finding.

Additional checks:

- Does every component have at least one expected_expertise entry?
  A component with no expertise entries gives PH-003 no skill
  context.
- Do the expertise entries cover the component's technology stack?
  If a component declares technology: python and persistence:
  postgresql, but no expertise entry mentions PostgreSQL, the
  Skill-Selector will not load database-related skills for PH-003.
  That is a finding.
- Are there expertise entries without a technology qualifier? An
  entry like "code review" is too vague because it does not name
  the language. "Python code review discipline" is specific enough.

### Integration Points Detailed Enough for Interface Contracts

PH-003 needs integration points to determine which modules expose
external interfaces vs. which stay internal. PH-004 needs integration
points to produce typed contracts for each cross-component boundary.

- Check: for each integration_point, is the protocol specific enough
  that PH-004 can determine the contract format? "HTTP/JSON" tells
  PH-004 to produce an OpenAPI spec or JSON schema. "shared-
  postgresql" tells PH-004 to produce a DDL schema. "function-call"
  within a single runtime tells PH-004 to produce a typed interface.
  "TBD" or missing protocol means PH-004 cannot start.
- Check: does every integration_point have a contract_source that
  references PH-004 or a downstream phase? If contract_source is
  empty or references an upstream phase, PH-004 will not know it
  owns this contract.
- Check: for components that share persistence (same database, same
  file system), is there a declared integration_point with protocol
  "shared-<store>"? Implicit shared state without a declared
  integration point means PH-004 will not produce a schema contract.
- The test: could PH-004 produce a skeleton contract (interface name,
  request/response types, error types) from the integration_point
  alone, without consulting the feature specification? If yes, the
  integration point is sufficiently detailed. If no, it needs more
  information.

## What PH-004 (Contract-First) needs from this stack manifest

PH-004 turns components and integration points into typed contracts.
Beyond the integration point checks above, PH-004 also needs:

### Component Technology Specificity for Contract Formats

PH-004 must choose a contract format for each integration point.
The choice depends on the technologies of the participating
components.

- Check: for each component, are technology, runtime, and frameworks
  specific enough that PH-004 can determine the appropriate contract
  format? "Python + FastAPI" implies OpenAPI/JSON Schema contracts.
  "TypeScript + React" implies TypeScript interface definitions.
  "python" without a framework is less constrained but still
  workable if no integration points exist.
- Check: for integration points between components with different
  technology stacks, does the protocol field disambiguate the
  serialization format? HTTP/JSON between Python and TypeScript
  components implies a JSON Schema contract both sides can consume.

### Rationale Supporting Contract Scope Decisions

PH-004 must decide what to contract and what to leave as internal
implementation detail. The stack manifest's rationale should explain
why components are separate, helping PH-004 understand what crosses
component boundaries vs. what stays internal.

- Check: does the rationale explain WHY the decomposition was chosen
  (technology boundary, deployment constraint, scaling concern)? A
  rationale that only restates component names gives PH-004 no
  guidance on contract scope.
- Check: if there are open_assumptions about technology choices, do
  they affect contract format decisions? An assumption about
  framework choice may change whether PH-004 produces an OpenAPI
  spec or a gRPC protobuf.

## What the Skill-Selector needs from this stack manifest

The Skill-Selector maps expected_expertise entries to concrete
SKILL.md files at the start of each downstream phase. This happens
repeatedly through PH-003 and beyond. The stack manifest must give
the Skill-Selector enough to work with.

### Skill-Selector Simulation

For each component, simulate the Skill-Selector by walking the
expected_expertise list and attempting to map each entry:

1. Read the entry as a natural-language description.
2. Imagine a skill catalog with entries like:
   - "Python backend development" -> python-backend skill
   - "Python CLI development" -> python-cli skill
   - "React component design and hooks" -> react-frontend skill
   - "PostgreSQL schema design and query optimization" -> postgresql skill
   - "Test-driven development with pytest" -> python-tdd skill
   - "Python code review discipline" -> python-code-review skill
   - "File system traversal and path handling" -> filesystem skill
3. Determine if the entry uniquely identifies one skill or is
   ambiguous between multiple skills.
4. Classify: mappable | too_vague | too_narrow | catalog_leak

Report the mapping result for each entry in the output.

## Your task

Perform these four steps in order:

1. **Simulate PH-003 (Solution Designer).** Read each component and
   attempt to write a design-scope statement. For each component:
   - Is the role specific enough to enumerate modules?
   - Are all upstream features present in features_served?
   - Do the features_served have conflicting technology implications?
   - Are component boundaries unambiguous?
   - Note where you had to consult the feature specification or
     requirements inventory to understand what the component does.

2. **Simulate PH-004 (Contract Author).** Read each integration
   point and attempt to sketch a skeleton contract. For each:
   - Is the protocol specific enough to choose a contract format?
   - Does the contract_source reference PH-004 or downstream?
   - For shared persistence, is there a declared integration point?
   - Note where PH-004 would be unable to start without additional
     information from the feature specification.
   Also assess the rationale field for contract scope guidance.

3. **Simulate the Skill-Selector.** Walk every expected_expertise
   entry across all components and classify each as mappable,
   too_vague, too_narrow, or catalog_leak. Record the simulated
   mapping for each entry. Flag entries that do not name a specific
   technology.

4. **Produce a structured YAML critique.** Synthesize your findings
   from steps 1-3 into the output format below.

## Output format

Your entire response must be a single YAML document (no commentary
outside the YAML). Use this exact structure:

    phase_evaluated: PH-002-architecture
    findings:
      - severity: blocking | warning | info
        location: "CMP-NNN-slug or IP-NNN or <section>"
        downstream_phase: "PH-003 or PH-004"
        issue: |
          Description of the problem, stated in terms of what the
          downstream phase will be unable to do because of this gap.
        recommendation: |
          What should change. Be specific: not "add more detail" but
          "add 'PostgreSQL schema design' to CMP-001-backend's
          expected_expertise" or "change IP-001 protocol from 'TBD'
          to 'HTTP/JSON over TLS'".
      - ...
    component_design_scope:
      - component: "CMP-NNN-slug"
        role_sufficient: true | false
        features_conflicting: true | false
        design_scope_statement: |
          One-paragraph scope derived from the stack manifest alone.
          If you had to consult upstream artifacts, note what was
          missing.
      - ...
    skill_selector_simulation:
      - component: "CMP-NNN-slug"
        mappings:
          - expertise_entry: "the exact entry text"
            classification: mappable | too_vague | too_narrow | catalog_leak
            simulated_skill: "hypothetical-skill-id or null"
            notes: "<why this classification>"
          - ...
      - ...
    integration_point_assessment:
      - integration_point: "IP-NNN"
        protocol_actionable: true | false
        contract_source_valid: true | false
        skeleton_feasible: true | false
        notes: |
          What PH-004 can or cannot derive from this integration
          point alone.
      - ...
    shared_persistence_check:
      - components: ["CMP-NNN-x", "CMP-NNN-y"]
        store: "postgresql | redis | filesystem | ..."
        integration_point_declared: true | false
        notes: "<finding if not declared>"
      - ...
    overall_usability: high | medium | low
    summary: |
      Brief 2-3 sentence summary. State the most important finding
      first.

## Severity definitions

- blocking: PH-003 or PH-004 cannot proceed without resolving this.
  Example: a component's role is so vague that PH-003 cannot
  determine what modules to design. Example: an integration point
  has no protocol, so PH-004 cannot choose a contract format.
  Example: all expected_expertise entries are catalog leaks, so the
  Skill-Selector cannot load any skills for PH-003.
- warning: PH-003 or PH-004 can proceed but will likely produce
  suboptimal output. Example: expected_expertise entries are mappable
  but miss a technology the component actually uses. Example: a
  component's role is designable but required consulting upstream
  artifacts to confirm scope.
- info: Worth noting but will not impede downstream work. Example:
  two components have overlapping expertise entries, suggesting
  possible premature decomposition. Example: an integration point's
  protocol is adequate but could be more specific.
```
