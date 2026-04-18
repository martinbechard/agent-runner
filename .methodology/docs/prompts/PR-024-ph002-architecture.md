### Module

architecture

## Prompt 1: Produce Architecture

### Required Files

docs/features/feature-specification.yaml

### Include Files

docs/features/feature-specification.yaml

### Checks Files

docs/architecture/architecture-design.yaml

### Generation Prompt

As a software architect, you must turn the feature specification into a
coherent architecture document and write it to
docs/architecture/architecture-design.yaml.

The feature specification is provided above in <FEATURE_SPECIFICATION>.

This phase is a constrained elaboration phase.
You may choose technology and architecture details that are coherent with the
feature specification and requirements, but do not invent extra scope.

Keep it as small as the feature set allows.
<Structured design directives>
{{INCLUDE:../../../../agent-assets/skills/structured-design/SKILL.md}}
</Structured design directives>

Requirements:

- Cover every FT-* feature at least once.
- Prefer `FT-*` and `RI-*` traceability for architecture claims.
- Use `AC-*` traceability only when a needed claim is not supported by a
  broader `FT-*` or `RI-*` statement.
- Do not invent components that serve no features.
- Do not invent unnecessary frameworks, databases, services, or integration
  points.
- Keep the architecture at architecture level. Do not drift into low-level
  implementation detail.
- Make the rationale for the architecture clear in the structured content.
- Write only docs/architecture/architecture-design.yaml.

### Validation Prompt

Review the current architecture artifact against <FEATURE_SPECIFICATION>.
The current artifact is provided above in <ARCHITECTURE_DESIGN>.

Decide whether the YAML architecture is phase-ready.

Review method:
- Iterate through the authored architecture units in order.
- Review each architecture unit for supported feature coverage, justified
  boundaries, and downstream usefulness.
- Before flagging a feature, boundary, or rationale as missing, check whether
  that same actionable meaning is already covered elsewhere in the
  architecture.
- Only flag it as missing if the allegedly missing content would change
  downstream design, contracts, implementation, or verification.

Focus on material defects only:
- missing feature coverage
- unsupported or unnecessary decomposition
- unsupported technology or persistence choices
- drift from exact source constraints
- fake or missing integration boundaries
- weak expertise descriptions
- structure that does not clearly express the architecture
- structure that distorts the `structured-design` architecture shape

Review rules:
<Structured review directives>
{{INCLUDE:../../../../agent-assets/skills/structured-review/SKILL.md}}
</Structured review directives>


- Accept a simple architecture if it is coherent and sufficient.
- Do not force extra components or integration points.
- Treat this phase as allowed elaboration, but reject unsupported scope creep.
- Cite exact component, FT-*, and RI-* references when you ask for changes.
- Treat unnecessary `AC-*` dependence as a traceability quality defect when the
  same claim should have been grounded in `FT-*` source text.
- Check that the artifact actually follows the `structured-design` skill rather
  than just flattening everything into generic.
- Check that the artifact follows the skill's architecture-doc guidance.
- Check that the artifact preserves the real architecture section structure
  rather than converting section names into item names or generic type
  entries.
- For each material correction, include:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
