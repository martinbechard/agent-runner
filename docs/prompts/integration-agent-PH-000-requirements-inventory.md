# Integration Agent: PH-000 Requirements Inventory

This is a prompt-runner input file with a single prompt and no validator.
The agent reads PH-000's output artifacts (requirements inventory YAML +
raw requirements) and evaluates whether PH-001 (Feature Specification)
and PH-002 (Architecture) will be able to use them effectively.

**How to run:**

    prompt-runner run \
      docs/prompts/integration-agent-PH-000-requirements-inventory.md \
      --project-dir <path-to-completed-PH-000-workspace>

The run executes the single critic prompt, skips the judge (no validator),
produces a YAML critique in the run output, and exits with verdict pass.

**Rationale:** see
`docs/superpowers/specs/2026-04-09-skill-pack-and-interactive-harness-notes.md`
section 6 for the full design of integration agents.

---

## Prompt 1: PH-000 integration critique

```
You are a downstream-consumer simulator for PH-000 Requirements
Inventory output. Your job is to read the requirements inventory
artifact and the original raw requirements, then evaluate whether the
inventory contains the semantic content that PH-001 (Feature
Specification) and PH-002 (Architecture) will need to do their jobs.

This is NOT a schema check or a format lint. Assume the YAML parses
and the IDs are well-formed. You are checking whether the CONTENT is
usable by the next phases.

## What to read

Read these two files from the workspace:

1. The requirements inventory YAML at
   `{workspace}/docs/requirements/requirements-inventory.yaml`
2. The original raw requirements document at
   `{workspace}/docs/requirements/raw-requirements.md`

You need both: the inventory (structured output of PH-000) and the
raw requirements (the source PH-000 worked from). Comparing them lets
you catch cases where the inventory either lost information from the
source or added information not in the source.

## What PH-001 (Feature Specification) needs from this inventory

PH-001 groups RI-* items into FT-* features and attaches testable
acceptance criteria to each feature. For that to work, the inventory
must provide:

### Groupability
- Each RI-* item must have enough semantic content that a feature
  grouping agent can identify which items belong together. An item
  that says only "the system shall X" without domain context forces
  PH-001 to guess at feature boundaries.
- Check: can you identify 2-4 candidate feature groups just by
  reading the RI-* items? If items are so terse or generic that
  grouping is ambiguous, that is a finding.

### Identifiable relationships
- Related requirements must be discoverable by reading their content:
  shared domain terms, explicit cross-references in tags or rationale,
  overlapping source locations.
- Check: for each candidate feature group you identified, is the
  grouping supported by explicit signals in the inventory (shared tags,
  adjacent source locations, rationale that references the same
  concept)? Or did you have to rely on external knowledge to group
  them?

### Testable behavior content
- Requirements that will become acceptance criteria must contain
  concrete, testable behavior — not just intent.
- Check: pick 3-4 RI-* items that describe behavior. Could you write
  a pass/fail test from the verbatim_quote alone? If you would need
  to consult the raw requirements or make assumptions to define the
  test, that is a finding.

## What PH-002 (Architecture) needs from this inventory

PH-002 identifies technology components from PH-001's features (and
transitively from PH-000's requirements). For that to work:

### Recognizable technology implications
- Requirements that imply specific technology choices (storage layer,
  UI framework, integration protocol, language runtime) must be
  recognizable as such from the inventory content.
- Check: which RI-* items imply technology decisions? Are those
  implications explicit in the item's tags, rationale, or
  verbatim_quote? Or would the architect have to infer them from
  general knowledge?

### Complete and unambiguous non-functional requirements
- NFRs that constrain architecture decisions (performance targets,
  dependency restrictions, platform requirements) must be specific
  enough that the architect does not have to guess.
- Check: for each non_functional or constraint item, is the
  requirement concrete enough to make an architectural decision? If
  the item says "modern laptop" without defining what that means, or
  "under 2 seconds" without specifying the measurement method, flag
  it. Note: if the item has an open_assumption that covers the
  ambiguity, that is acceptable — the assumption mechanism is working
  as intended.

### Assumption completeness
- open_assumptions are first-class data that downstream phases inherit.
  Missing assumptions are worse than excessive ones — a missing
  assumption becomes an invisible decision.
- Check: are there RI-* items where you would need to make a decision
  to proceed with architecture, but no open_assumption exists to flag
  that decision? That is a finding.

## Your task

Perform these three steps in order:

1. **Simulate PH-001 (Feature Specification generator).** Read all
   RI-* items and attempt to group them into 2-5 candidate features.
   For each group, note:
   - Which RI-* items belong to it and why
   - Whether the grouping was clear from inventory content or required
     external inference
   - Any items that could belong to multiple groups (boundary ambiguity)
   - Any items you could not place in any group

2. **Simulate PH-002 (Architecture).** Read the inventory looking for
   technology implications and architectural constraints. Note:
   - Which items imply technology decisions and what those decisions are
   - Which NFRs are concrete enough to act on vs. which require
     clarification
   - Whether open_assumptions cover the gaps or whether new assumptions
     are needed
   - Any architectural decisions you would have to make WITHOUT
     supporting evidence in the inventory

3. **Produce a structured YAML critique.** Synthesize your findings
   from steps 1 and 2 into the output format below.

## Output format

Your entire response must be a single YAML document (no commentary
outside the YAML). Use this exact structure:

    phase_evaluated: PH-000-requirements-inventory
    findings:
      - severity: blocking | warning | info
        location: "RI-NNN or <section of raw requirements>"
        downstream_phase: "PH-001 or PH-002"
        issue: |
          Description of the problem, stated in terms of what the
          downstream phase will be unable to do because of this gap.
        recommendation: |
          What should change. Be specific: not "add more detail" but
          "split RI-003 into two items: one for the input validation
          and one for the output format" or "add an open_assumption
          to RI-012 covering the definition of 'modern laptop'".
      - ...
    feature_grouping_attempt:
      - group_name: "<candidate feature name>"
        members: ["RI-NNN", "RI-NNN", ...]
        confidence: high | medium | low
        notes: "<why this grouping, and any boundary ambiguity>"
      - ...
    ungrouped_items: ["RI-NNN", ...]
    architecture_signals:
      - item: "RI-NNN"
        implies: "<technology decision or constraint>"
        explicit: true | false
      - ...
    overall_usability: high | medium | low
    summary: |
      Brief 2-3 sentence summary. State the most important finding
      first.

## Severity definitions

- blocking: PH-001 or PH-002 cannot proceed without resolving this.
  Example: a requirement is so ambiguous that it could mean two
  completely different features.
- warning: PH-001 or PH-002 can proceed but will likely produce
  suboptimal output. Example: an NFR lacks a concrete threshold, so
  the architect will pick an arbitrary one.
- info: Worth noting but will not impede downstream work. Example:
  tags could be more consistent but the grouping is still clear.
```
