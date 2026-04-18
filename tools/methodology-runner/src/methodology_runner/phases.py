"""Phase definitions for the eight methodology phases (PH-000 through PH-007).

This module is a pure data registry.  Each phase is a frozen PhaseConfig
instance containing everything the prompt generator needs to produce a
prompt-runner file and everything the cross-reference verifier needs to
check the output.

Output paths align with CD-002 Section 4.5 workspace layout::

    docs/requirements/requirements-inventory.yaml   # Phase 0
    docs/features/feature-specification.yaml        # Phase 1
    docs/architecture/stack-manifest.yaml           # Phase 2 (NEW)
    docs/design/solution-design.yaml                # Phase 3
    docs/design/interface-contracts.yaml            # Phase 4
    docs/simulations/simulation-definitions.yaml    # Phase 5
    docs/implementation/implementation-workflow.md  # Phase 6 primary
    docs/implementation/implementation-run-report.yaml  # Phase 6 support
    docs/verification/verification-report.yaml      # Phase 7

Public API
----------
PHASES : list[PhaseConfig]
    All eight phases in execution order (Phase 0 first, Phase 7 last).
PHASE_MAP : dict[str, PhaseConfig]
    Lookup by phase_id.
get_phase(phase_id) -> PhaseConfig
    Lookup with ValueError on miss.
resolve_input_sources(phase, workspace)
    Resolve {workspace} templates to concrete (Path, InputRole, str) tuples.
"""
from __future__ import annotations

from pathlib import Path

from .models import (
    InputRole,
    InputSourceTemplate,
    PhaseConfig,
)

# ---------------------------------------------------------------------------
# Shared input/output path templates (CD-002 Section 4.5)
# ---------------------------------------------------------------------------

_RAW_REQUIREMENTS_TEMPLATE = "{workspace}/docs/requirements/raw-requirements.md"

_OUTPUT_PHASE_0 = "docs/requirements/requirements-inventory.yaml"
_OUTPUT_PHASE_0_COVERAGE = "docs/requirements/requirements-inventory-coverage.yaml"
_OUTPUT_PHASE_1 = "docs/features/feature-specification.yaml"
_OUTPUT_PHASE_2 = "docs/architecture/stack-manifest.yaml"
_OUTPUT_PHASE_3 = "docs/design/solution-design.yaml"
_OUTPUT_PHASE_4 = "docs/design/interface-contracts.yaml"
_OUTPUT_PHASE_5 = "docs/simulations/simulation-definitions.yaml"
_OUTPUT_PHASE_6 = "docs/implementation/implementation-workflow.md"
_OUTPUT_PHASE_6_REPORT = "docs/implementation/implementation-run-report.yaml"
_OUTPUT_PHASE_7 = "docs/verification/verification-report.yaml"

_PROMPT_PHASE_0 = "tools/methodology-runner/docs/prompts/PR-025-ph000-requirements-inventory.md"
_PROMPT_PHASE_1 = "tools/methodology-runner/docs/prompts/PR-023-ph001-feature-specification.md"
_PROMPT_PHASE_2 = "tools/methodology-runner/docs/prompts/PR-024-ph002-architecture.md"
_PROMPT_PHASE_3 = "tools/methodology-runner/docs/prompts/PR-026-ph003-solution-design.md"
_PROMPT_PHASE_4 = "tools/methodology-runner/docs/prompts/PR-027-ph004-interface-contracts.md"
_PROMPT_PHASE_5 = "tools/methodology-runner/docs/prompts/PR-028-ph005-intelligent-simulations.md"
_PROMPT_PHASE_6 = "tools/methodology-runner/docs/prompts/PR-029-ph006-incremental-implementation.md"
_PROMPT_PHASE_7 = "tools/methodology-runner/docs/prompts/PR-030-ph007-verification-sweep.md"


def _tpl(relative_path: str) -> str:
    """Build a ``{workspace}/...`` template from a workspace-relative path."""
    return "{workspace}/" + relative_path


# ---------------------------------------------------------------------------
# Phase 0: Requirements Inventory
# ---------------------------------------------------------------------------

_PHASE_0 = PhaseConfig(
    phase_id="PH-000-requirements-inventory",
    phase_name="Requirements Inventory",
    phase_number=0,
    abbreviation="RI",
    predecessors=[],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_RAW_REQUIREMENTS_TEMPLATE,
            role=InputRole.PRIMARY,
            format="markdown",
            description="Raw requirements document provided by the user",
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_0,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_0, _OUTPUT_PHASE_0_COVERAGE],
    extraction_focus=(
        "Completeness: every requirement-bearing statement in the source\n"
        "document must appear as an inventory item.  Atomicity: compound\n"
        "requirements (those containing 'and', 'or', or multiple independent\n"
        "clauses) must be split into separate RI-* items.  Fidelity: the\n"
        "verbatim_quote field must reproduce the original text exactly.\n"
        "Normalization: each item must also include a normalized_requirement\n"
        "that captures the same meaning as a coherent standalone software\n"
        "requirement without adding unsupported detail."
    ),
    generation_instructions=(
        "Read the raw requirements document and produce a YAML inventory\n"
        "file at the designated output path.\n"
        "\n"
        "The top-level structure is:\n"
        "  source_document: path/to/raw-requirements.md\n"
        "  items: [...]          # the inventory items\n"
        "  out_of_scope: [...]   # requirements explicitly deferred\n"
        "\n"
        "Also write a separate coverage support file at\n"
        "docs/requirements/requirements-inventory-coverage.yaml with:\n"
        "  source_document: path/to/raw-requirements.md\n"
        "  inventory_document: docs/requirements/requirements-inventory.yaml\n"
        "  coverage_check: {...} # maps source phrases to RI-* IDs\n"
        "  coverage_verdict: ... # summary counts + PASS/FAIL\n"
        "\n"
        "Each item has these fields:\n"
        "  - id: RI-NNN (zero-padded three-digit sequential number)\n"
        "  - category: one of functional, non_functional, constraint,\n"
        "    assumption\n"
        "  - verbatim_quote: the exact text from the source document\n"
        "  - normalized_requirement: the same requirement restated as a\n"
        "    coherent standalone software requirement\n"
        "  - source_location: section heading or paragraph identifier\n"
        "  - tags: list of domain keywords for cross-referencing\n"
        "  - rationale: WHY this was extracted as a separate item\n"
        "    (rule + because chain)\n"
        "  - open_assumptions: any specifics you infer beyond the quote\n"
        "    (each with id, detail, needs, status)\n"
        "\n"
        "Scan every section, paragraph, table row, and list item.  Any\n"
        "statement containing shall, must, will, should, or an imperative\n"
        "verb describing system behaviour is a requirement.  Assumptions\n"
        "and constraints that bound the solution space are also inventory\n"
        "items.\n"
        "\n"
        "When a paragraph contains multiple independent requirements,\n"
        "split them into separate items.  Preserve the original wording\n"
        "in verbatim_quote, and use normalized_requirement only to restate\n"
        "that same meaning more coherently for downstream phases."
    ),
    judge_guidance=(
        "Check for these failure modes in priority order:\n"
        "\n"
        "1. Silent omissions: compare every section of the raw requirements\n"
        "   document against the inventory.  Flag any section that has zero\n"
        "   corresponding RI-* items.\n"
        "2. Invented requirements: verify each verbatim_quote appears in\n"
        "   the source document.  Flag any item whose quote cannot be\n"
        "   located in the original text.\n"
        "3. Meaning loss or drift: verify each normalized_requirement still\n"
        "   captures the original source meaning without dropping important\n"
        "   qualifiers or adding unsupported detail.\n"
        "4. Unsplit compounds: look for items whose verbatim_quote contains\n"
        "   'and' or 'or' joining independent clauses that describe\n"
        "   distinct behaviours.  Flag as needing decomposition.\n"
        "5. Lost nuance: check that category assignments match the language\n"
        "   strength (shall/must -> functional, should -> non_functional,\n"
        "   given/assuming -> assumption, within/limited-to -> constraint).\n"
        "6. Wrong categories: verify constraints vs. assumptions vs.\n"
        "   functional vs. non_functional.\n"
        "\n"
        "The inventory MUST be valid YAML parseable by a standard YAML\n"
        "parser.  All id values must follow the RI-NNN pattern and be\n"
        "unique across the file."
    ),
    artifact_format="yaml",
    artifact_schema_description=(
        "source_document: \"path/to/raw-requirements.md\"\n"
        "\n"
        "items:\n"
        "  - id: \"RI-NNN\"           # zero-padded three-digit sequential ID\n"
        "    category: \"functional\"  # functional | non_functional | constraint | assumption\n"
        "    verbatim_quote: \"...\"   # exact text from source document (no paraphrasing)\n"
        "    normalized_requirement: \"...\"  # coherent standalone requirement with same meaning\n"
        "    source_location: \"...\"  # section heading or paragraph identifier\n"
        "    tags: [\"tag1\", \"tag2\"]  # domain keywords for cross-referencing\n"
        "    rationale:               # WHY this was extracted as a separate item\n"
        "      rule: \"...\"           # the extraction rule applied\n"
        "      because: \"...\"        # the reasoning chain\n"
        "    open_assumptions:        # specifics beyond the quote (if any)\n"
        "      - id: \"ASM-NNN\"\n"
        "        detail: \"...\"       # the assumed value or constraint\n"
        "        needs: \"...\"        # who/what must confirm this\n"
        "        status: \"open\"      # open | confirmed | invalidated\n"
        "\n"
        "out_of_scope:               # requirements explicitly deferred\n"
        "  - inventory_ref: \"RI-NNN\"\n"
        "    reason: \"...\"\n"
        "\n"
        "Separate coverage support file:\n"
        "source_document: \"path/to/raw-requirements.md\"\n"
        "inventory_document: \"docs/requirements/requirements-inventory.yaml\"\n"
        "coverage_check:             # maps source phrases to RI-* IDs\n"
        "  \"phrase from source\": [\"RI-NNN\", ...]\n"
        "  status: \"N/N phrases covered, 0 orphans, 0 invented\"\n"
        "\n"
        "coverage_verdict:\n"
        "  total_upstream_phrases: 0\n"
        "  covered: 0\n"
        "  orphaned: 0\n"
        "  invented: 0\n"
        "  verdict: \"PASS\"          # PASS | FAIL"
    ),
    checklist_examples_good=[
        (
            "Every paragraph in the requirements document that contains "
            "a shall/must/will statement has at least one corresponding "
            "RI-* item in the inventory"
        ),
        (
            "Each RI-* item's verbatim_quote field contains text that "
            "can be located verbatim in the source document without "
            "modification"
        ),
    ],
    checklist_examples_bad=[
        "Requirements are captured",
        "The inventory is complete",
    ],
    prompt_module_path=_PROMPT_PHASE_0,
)

# ---------------------------------------------------------------------------
# Phase 1: Feature Specification
# ---------------------------------------------------------------------------

_PHASE_1 = PhaseConfig(
    phase_id="PH-001-feature-specification",
    phase_name="Feature Specification",
    phase_number=1,
    abbreviation="FS",
    predecessors=["PH-000-requirements-inventory"],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_0),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Requirements inventory produced by Phase 0",
        ),
        InputSourceTemplate(
            ref_template=_RAW_REQUIREMENTS_TEMPLATE,
            role=InputRole.VALIDATION_REFERENCE,
            format="markdown",
            description=(
                "Raw requirements document for validating that features "
                "trace back to the original source"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_1,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_1],
    extraction_focus=(
        "Complete RI coverage: every RI-* item in the inventory must map\n"
        "to at least one feature or be explicitly listed in out_of_scope\n"
        "with a justification.  Acceptance criteria quality: each AC must\n"
        "be testable, specific, and free of ambiguous qualifiers (e.g.,\n"
        "'fast', 'user-friendly', 'appropriate').  Dependency identification:\n"
        "features that share data, sequencing constraints, or transactional\n"
        "boundaries must declare their inter-feature dependencies."
    ),
    generation_instructions=(
        "Read the requirements inventory and produce a feature specification\n"
        "YAML file.  The file contains these top-level sections:\n"
        "\n"
        "features:\n"
        "  - id: FT-NNN\n"
        "    name: descriptive feature name\n"
        "    description: what this feature does and why\n"
        "    source_inventory_refs: [RI-NNN, ...]  # traceability\n"
        "    acceptance_criteria:\n"
        "      - id: AC-NNN-NN\n"
        "        description: testable criterion\n"
        "    dependencies: [FT-NNN, ...]  # features this depends on\n"
        "\n"
        "out_of_scope:\n"
        "  - inventory_ref: RI-NNN\n"
        "    reason: why this requirement is deferred or excluded\n"
        "\n"
        "cross_cutting_concerns:\n"
        "  - id: CC-NNN\n"
        "    name: concern name (e.g., logging, authentication)\n"
        "    description: how it cuts across features\n"
        "    affected_features: [FT-NNN, ...]\n"
        "\n"
        "Group related RI items into coherent features.  Write acceptance\n"
        "criteria that are binary pass/fail -- a tester must be able to\n"
        "determine the verdict without subjective judgment."
    ),
    judge_guidance=(
        "Check for these failure modes:\n"
        "\n"
        "1. Vague acceptance criteria: flag any AC that uses subjective\n"
        "   language (fast, intuitive, appropriate, reasonable, etc.)\n"
        "   without a measurable threshold or concrete test procedure.\n"
        "2. Orphaned inventory items: verify every RI-NNN from the Phase 0\n"
        "   inventory appears in at least one feature's source_inventory_refs\n"
        "   or in out_of_scope with a reason.\n"
        "3. Assumption conflicts: check that no two features make\n"
        "   contradictory assumptions about shared state, data formats,\n"
        "   or execution order.\n"
        "4. Scope creep: flag features that introduce functionality not\n"
        "   traceable to any inventory item.\n"
        "5. Missing dependencies: if feature A reads data that feature B\n"
        "   produces, feature B must appear in feature A's dependencies."
    ),
    artifact_format="yaml",
    artifact_schema_description=(
        "features:\n"
        "  - id: \"FT-NNN\"\n"
        "    name: \"...\"\n"
        "    description: \"...\"\n"
        "    source_inventory_refs: [\"RI-NNN\", ...]\n"
        "    acceptance_criteria:\n"
        "      - id: \"AC-NNN-NN\"\n"
        "        description: \"...\"\n"
        "    dependencies: [\"FT-NNN\", ...]\n"
        "\n"
        "out_of_scope:\n"
        "  - inventory_ref: \"RI-NNN\"\n"
        "    reason: \"...\"\n"
        "\n"
        "cross_cutting_concerns:\n"
        "  - id: \"CC-NNN\"\n"
        "    name: \"...\"\n"
        "    description: \"...\"\n"
        "    affected_features: [\"FT-NNN\", ...]"
    ),
    checklist_examples_good=[
        (
            "Every RI-* item in the Phase 0 inventory appears in at "
            "least one feature's source_inventory_refs list or in the "
            "out_of_scope section with a stated reason"
        ),
        (
            "Each acceptance criterion uses measurable language and can "
            "be verified with a concrete test -- no 'should be fast' or "
            "'user-friendly' without quantified thresholds"
        ),
    ],
    checklist_examples_bad=[
        "Features cover the requirements",
        "Acceptance criteria are defined",
    ],
    prompt_module_path=_PROMPT_PHASE_1,
)

# ---------------------------------------------------------------------------
# Phase 2: Architecture
# ---------------------------------------------------------------------------

_PHASE_2_ARCHITECTURE = PhaseConfig(
    phase_id="PH-002-architecture",
    phase_name="Architecture",
    phase_number=2,
    abbreviation="AR",
    predecessors=["PH-001-feature-specification"],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Feature specification produced by Phase 1",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_0),
            role=InputRole.UPSTREAM_TRACEABILITY,
            format="yaml",
            description=(
                "Requirements inventory for upstream traceability "
                "of expected_expertise choices"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_2,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_2],
    extraction_focus=(
        "Component completeness: every feature from the feature spec\n"
        "must be served by at least one declared component.  Technology\n"
        "coherence: each component has a single named technology and a\n"
        "coherent frameworks list.  Expertise articulation: each\n"
        "component declares a non-empty expected_expertise list of\n"
        "free-text descriptions of the knowledge needed to build it.\n"
        "Integration completeness: every cross-component data flow\n"
        "implied by the features is captured as a named integration\n"
        "point."
    ),
    generation_instructions=(
        "Read the feature specification and produce a stack manifest YAML\n"
        "file.  The file decomposes the enhancement into technology\n"
        "components and declares what knowledge each component needs.\n"
        "\n"
        "components:\n"
        "  - id: CMP-NNN-<slug>\n"
        "    name: descriptive component name\n"
        "    role: one-sentence role summary\n"
        "    technology: e.g. python, typescript, go, rust\n"
        "    runtime: e.g. python3.12, node22, go1.22\n"
        "    frameworks: [name1, name2]\n"
        "    persistence: e.g. postgresql, sqlite, none\n"
        "    expected_expertise:\n"
        "      - \"Free-text description of knowledge this component needs\"\n"
        "      - \"Additional knowledge area\"\n"
        "    features_served: [FT-NNN, ...]\n"
        "\n"
        "integration_points:\n"
        "  - id: IP-NNN\n"
        "    between: [CMP-NNN-a, CMP-NNN-b]\n"
        "    protocol: e.g. HTTP/JSON over TLS\n"
        "    contract_source: where the contract will be defined\n"
        "\n"
        "rationale: |\n"
        "  Prose explanation of the decomposition choices.\n"
        "\n"
        "The expected_expertise field MUST use free-text, human-readable\n"
        "descriptions (not concrete skill IDs).  A later Skill-Selector\n"
        "agent maps each description to concrete skills from a catalog;\n"
        "the architect phase is decoupled from the skill catalog so that\n"
        "architecture outputs are portable across skill pack versions."
    ),
    judge_guidance=(
        "Check for these failure modes:\n"
        "\n"
        "1. Feature coverage gaps: every FT-* feature from Phase 1 must\n"
        "   appear in at least one component's features_served list.\n"
        "2. Expertise articulation: every component must have a non-empty\n"
        "   expected_expertise list of free-text descriptions.  Flag any\n"
        "   component whose expertise list looks like concrete skill IDs\n"
        "   (e.g., 'python-backend-impl') rather than descriptions\n"
        "   (e.g., 'Python backend development').\n"
        "3. Orphan integration points: every integration_point must\n"
        "   reference two components both present in the components list.\n"
        "4. Technology coherence: flag components whose frameworks list\n"
        "   includes items from incompatible ecosystems (e.g., python\n"
        "   technology with a react framework entry).\n"
        "5. Missing rationale: the rationale field must explain the\n"
        "   decomposition, not merely restate the component names."
    ),
    artifact_format="yaml",
    artifact_schema_description=(
        "components:\n"
        "  - id: \"CMP-NNN-<slug>\"\n"
        "    name: \"...\"\n"
        "    role: \"...\"\n"
        "    technology: \"...\"\n"
        "    runtime: \"...\"\n"
        "    frameworks: [\"...\"]\n"
        "    persistence: \"...\"\n"
        "    expected_expertise: [\"...\", \"...\"]\n"
        "    features_served: [\"FT-NNN\", ...]\n"
        "\n"
        "integration_points:\n"
        "  - id: \"IP-NNN\"\n"
        "    between: [\"CMP-NNN-a\", \"CMP-NNN-b\"]\n"
        "    protocol: \"...\"\n"
        "    contract_source: \"...\"\n"
        "\n"
        "rationale: |\n"
        "  ..."
    ),
    checklist_examples_good=[
        (
            "Every FT-* feature from Phase 1 appears in the features_served "
            "list of at least one component in the stack manifest"
        ),
        (
            "Every component has a non-empty expected_expertise list where "
            "entries are free-text descriptions of required knowledge, not "
            "concrete skill IDs"
        ),
    ],
    checklist_examples_bad=[
        "The architecture is reasonable",
        "Technologies are chosen",
    ],
    prompt_module_path=_PROMPT_PHASE_2,
)

# ---------------------------------------------------------------------------
# Phase 3: Solution Design
# ---------------------------------------------------------------------------

_PHASE_3 = PhaseConfig(
    phase_id="PH-003-solution-design",
    phase_name="Solution Design",
    phase_number=3,
    abbreviation="SD",
    predecessors=["PH-002-architecture"],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_2),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Stack manifest produced by Phase 2 Architecture",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.UPSTREAM_TRACEABILITY,
            format="yaml",
            description=(
                "Feature specification for upstream traceability "
                "verification"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_3,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_3],
    extraction_focus=(
        "Feature realization: every FT-* feature must appear in at least\n"
        "one component's feature_realization_map.  Boundary clarity: each\n"
        "component has a well-defined responsibility boundary -- no two\n"
        "components own the same data entity or operation.  Interaction\n"
        "completeness: every data flow between components is captured as\n"
        "a named INT-* interaction with an explicit protocol."
    ),
    generation_instructions=(
        "Read the feature specification and produce a solution design YAML.\n"
        "\n"
        "components:\n"
        "  - id: CMP-NNN\n"
        "    name: component name\n"
        "    responsibility: what this component exclusively owns\n"
        "    technology: implementation technology or framework\n"
        "    feature_realization_map:\n"
        "      FT-NNN: how this component contributes to the feature\n"
        "    dependencies: [CMP-NNN, ...]\n"
        "\n"
        "interactions:\n"
        "  - id: INT-NNN\n"
        "    source: CMP-NNN\n"
        "    target: CMP-NNN\n"
        "    protocol: sync-call | async-message | event | shared-store\n"
        "    data_exchanged: description of data flowing between components\n"
        "    triggered_by: what initiates this interaction\n"
        "\n"
        "Design for separation of concerns.  Each component should have a\n"
        "single primary responsibility.  Interactions capture all data\n"
        "flows -- if component A needs data owned by component B, there\n"
        "must be an INT-* interaction.  Map every feature to the components\n"
        "that collaborate to deliver it via feature_realization_map."
    ),
    judge_guidance=(
        "Check for these failure modes:\n"
        "\n"
        "1. Orphan components: flag any CMP-* whose feature_realization_map\n"
        "   is empty or references only non-existent features.\n"
        "2. God components: flag any component that participates in more\n"
        "   than 60% of all features -- it likely needs decomposition.\n"
        "3. Missing interactions: if CMP-A lists CMP-B in its dependencies,\n"
        "   there must be at least one INT-* interaction between them.\n"
        "4. Implicit state sharing: flag cases where two components appear\n"
        "   to read or write the same data entity without an explicit\n"
        "   INT-* interaction.\n"
        "5. Untraced features: every FT-NNN from Phase 1 must appear in\n"
        "   at least one component's feature_realization_map."
    ),
    artifact_format="yaml",
    artifact_schema_description=(
        "components:\n"
        "  - id: \"CMP-NNN\"\n"
        "    name: \"...\"\n"
        "    responsibility: \"...\"\n"
        "    technology: \"...\"\n"
        "    feature_realization_map:\n"
        "      \"FT-NNN\": \"...\"\n"
        "    dependencies: [\"CMP-NNN\", ...]\n"
        "\n"
        "interactions:\n"
        "  - id: \"INT-NNN\"\n"
        "    source: \"CMP-NNN\"\n"
        "    target: \"CMP-NNN\"\n"
        "    protocol: \"sync-call\"  # sync-call | async-message | event | shared-store\n"
        "    data_exchanged: \"...\"\n"
        "    triggered_by: \"...\""
    ),
    checklist_examples_good=[
        (
            "Every FT-* feature from Phase 1 appears in at least one "
            "component's feature_realization_map with a description of "
            "how the component contributes to delivering it"
        ),
        (
            "Every dependency edge between components has a corresponding "
            "INT-* interaction specifying the protocol and data exchanged"
        ),
    ],
    checklist_examples_bad=[
        "Components are well-designed",
        "The architecture is sound",
    ],
    prompt_module_path=_PROMPT_PHASE_3,
)

# ---------------------------------------------------------------------------
# Phase 4: Interface Contracts
# ---------------------------------------------------------------------------

_PHASE_4 = PhaseConfig(
    phase_id="PH-004-interface-contracts",
    phase_name="Interface Contracts",
    phase_number=4,
    abbreviation="CI",
    predecessors=["PH-003-solution-design"],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_3),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Solution design with components and interactions from Phase 3",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Feature specification for validating that contracts "
                "cover all acceptance criteria"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_4,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_4],
    extraction_focus=(
        "Interaction coverage: every INT-* interaction from the solution\n"
        "design must have a corresponding CTR-* contract.  Schema precision:\n"
        "every operation's request and response types are fully specified\n"
        "with field names, types, and constraints -- no 'object' or 'any'\n"
        "placeholders.  Error completeness: every operation defines its\n"
        "error types and the conditions that trigger them."
    ),
    generation_instructions=(
        "Read the solution design and produce an interface contracts YAML.\n"
        "\n"
        "contracts:\n"
        "  - id: CTR-NNN\n"
        "    name: contract name\n"
        "    interaction_ref: INT-NNN  # which design interaction this covers\n"
        "    source_component: CMP-NNN\n"
        "    target_component: CMP-NNN\n"
        "    operations:\n"
        "      - name: operation name\n"
        "        description: what this operation does\n"
        "        request_schema:\n"
        "          fields:\n"
        "            - name: field_name\n"
        "              type: string | int | bool | list[T] | object-ref\n"
        "              required: true | false\n"
        "              constraints: \"...\"\n"
        "        response_schema:\n"
        "          fields: [...]  # same structure as request\n"
        "        error_types:\n"
        "          - name: error name\n"
        "            condition: when this error occurs\n"
        "            http_status: NNN  # if applicable\n"
        "    behavioral_specs:\n"
        "      - precondition: what must be true before invocation\n"
        "        postcondition: what is guaranteed after success\n"
        "        invariant: what remains unchanged\n"
        "\n"
        "Each INT-* interaction must have at least one contract.  Complex\n"
        "interactions may have multiple contracts (e.g., one per operation\n"
        "or per data flow direction).  Be exhaustive with error types --\n"
        "every failure mode the caller might encounter must be named."
    ),
    judge_guidance=(
        "Check for these failure modes:\n"
        "\n"
        "1. Type holes: flag any schema field with type 'object', 'any',\n"
        "   or 'unknown' -- all types must be fully specified or reference\n"
        "   a named schema.\n"
        "2. Error gaps: for each operation, verify that at least validation\n"
        "   error, not-found, and authorization-denied error types exist\n"
        "   where applicable.\n"
        "3. Cross-contract inconsistency: if two contracts reference the\n"
        "   same data structure, the field names and types must match.\n"
        "4. Missing contracts: verify every INT-* from the solution design\n"
        "   has at least one CTR-* with a matching interaction_ref.\n"
        "5. Behavioural gaps: each contract should have at least one\n"
        "   pre/postcondition pair that a simulation can verify."
    ),
    artifact_format="yaml",
    artifact_schema_description=(
        "contracts:\n"
        "  - id: \"CTR-NNN\"\n"
        "    name: \"...\"\n"
        "    interaction_ref: \"INT-NNN\"\n"
        "    source_component: \"CMP-NNN\"\n"
        "    target_component: \"CMP-NNN\"\n"
        "    operations:\n"
        "      - name: \"...\"\n"
        "        description: \"...\"\n"
        "        request_schema:\n"
        "          fields:\n"
        "            - name: \"...\"\n"
        "              type: \"...\"\n"
        "              required: true\n"
        "              constraints: \"...\"\n"
        "        response_schema:\n"
        "          fields: [...]  # same structure\n"
        "        error_types:\n"
        "          - name: \"...\"\n"
        "            condition: \"...\"\n"
        "            http_status: NNN\n"
        "    behavioral_specs:\n"
        "      - precondition: \"...\"\n"
        "        postcondition: \"...\"\n"
        "        invariant: \"...\""
    ),
    checklist_examples_good=[
        (
            "Every INT-* interaction in the Phase 2 solution design has "
            "at least one CTR-* contract with a matching interaction_ref"
        ),
        (
            "Every operation in every contract defines at least a "
            "validation-error and a not-found error type with the "
            "conditions that trigger them"
        ),
    ],
    checklist_examples_bad=[
        "Contracts are defined for all interfaces",
        "Error handling is present",
    ],
    prompt_module_path=_PROMPT_PHASE_4,
)

# ---------------------------------------------------------------------------
# Phase 5: Intelligent Simulations
# ---------------------------------------------------------------------------

_PHASE_5 = PhaseConfig(
    phase_id="PH-005-intelligent-simulations",
    phase_name="Intelligent Simulations",
    phase_number=5,
    abbreviation="IS",
    predecessors=["PH-004-interface-contracts"],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_4),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Interface contracts from Phase 4",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Feature specification for validating that simulations "
                "cover all acceptance criteria"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_5,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_5],
    extraction_focus=(
        "Contract coverage: every CTR-* contract must have at least one\n"
        "SIM-* simulation.  Scenario breadth: each simulation must include\n"
        "happy-path, error-path, and edge-case scenarios.  Validation\n"
        "precision: every scenario must define concrete expected outcomes\n"
        "that can be mechanically verified.  LLM leakage prevention:\n"
        "simulations must not embed knowledge that only the real service\n"
        "would have -- they verify the contract, not the implementation."
    ),
    generation_instructions=(
        "Read the interface contracts and produce a simulation specs YAML.\n"
        "\n"
        "simulations:\n"
        "  - id: SIM-NNN\n"
        "    contract_ref: CTR-NNN\n"
        "    description: what this simulation verifies\n"
        "    scenario_bank:\n"
        "      - name: scenario name\n"
        "        type: happy_path | error_path | edge_case\n"
        "        input: concrete input data matching the contract schema\n"
        "        expected_output: concrete expected response\n"
        "        assertions:\n"
        "          - field: path.to.field\n"
        "            operator: equals | contains | matches | greater_than\n"
        "            value: expected value\n"
        "    llm_adjuster:\n"
        "      temperature: 0.0-1.0\n"
        "      system_prompt_addendum: extra instructions for LLM-based sim\n"
        "      forbidden_patterns: [\"...\"]  # strings the sim must not emit\n"
        "    validation_rules:\n"
        "      - rule: description of what to validate\n"
        "        severity: blocking | warning\n"
        "\n"
        "For each contract, produce at least three scenarios: one happy\n"
        "path that exercises the primary success flow, one error path that\n"
        "triggers each defined error type, and one edge case that tests\n"
        "boundary conditions (empty inputs, maximum sizes, concurrent\n"
        "access patterns)."
    ),
    judge_guidance=(
        "Check for these failure modes:\n"
        "\n"
        "1. Validation gaps: flag any scenario whose assertions list is\n"
        "   empty or contains only trivial checks (e.g., 'status equals\n"
        "   200' without checking the response body).\n"
        "2. Scenario realism: flag scenarios with input data that could\n"
        "   never occur given the contract's constraints (e.g., negative\n"
        "   counts when the schema specifies unsigned integers).\n"
        "3. LLM leakage: flag simulations where the expected_output\n"
        "   contains implementation details not derivable from the\n"
        "   contract alone (e.g., internal database IDs, timestamps).\n"
        "4. Missing error coverage: for each contract operation's error\n"
        "   types, verify there is at least one error_path scenario that\n"
        "   triggers it.\n"
        "5. Uncovered contracts: every CTR-NNN from Phase 3 must have at\n"
        "   least one SIM-* with a matching contract_ref."
    ),
    artifact_format="yaml",
    artifact_schema_description=(
        "simulations:\n"
        "  - id: \"SIM-NNN\"\n"
        "    contract_ref: \"CTR-NNN\"\n"
        "    description: \"...\"\n"
        "    scenario_bank:\n"
        "      - name: \"...\"\n"
        "        type: \"happy_path\"  # happy_path | error_path | edge_case\n"
        "        input: { ... }  # concrete data matching contract schema\n"
        "        expected_output: { ... }\n"
        "        assertions:\n"
        "          - field: \"path.to.field\"\n"
        "            operator: \"equals\"  # equals | contains | matches | greater_than\n"
        "            value: \"...\"\n"
        "    llm_adjuster:\n"
        "      temperature: 0.0\n"
        "      system_prompt_addendum: \"...\"\n"
        "      forbidden_patterns: [\"...\"]\n"
        "    validation_rules:\n"
        "      - rule: \"...\"\n"
        "        severity: \"blocking\"  # blocking | warning"
    ),
    checklist_examples_good=[
        (
            "Every CTR-* contract in Phase 3 has at least one SIM-* "
            "simulation, and each simulation has at least one happy-path, "
            "one error-path, and one edge-case scenario"
        ),
        (
            "Every scenario's assertions list contains at least one check "
            "on the response body content, not just the status code or "
            "top-level success flag"
        ),
    ],
    checklist_examples_bad=[
        "Simulations exist for the contracts",
        "Test scenarios are realistic",
    ],
    prompt_module_path=_PROMPT_PHASE_5,
)

# ---------------------------------------------------------------------------
# Phase 6: Incremental Implementation
# ---------------------------------------------------------------------------

_PHASE_6 = PhaseConfig(
    phase_id="PH-006-incremental-implementation",
    phase_name="Incremental Implementation",
    phase_number=6,
    abbreviation="II",
    predecessors=[
        "PH-004-interface-contracts",
        "PH-005-intelligent-simulations",
    ],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_3),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Solution design that defines the implementation target",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_4),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description="Interface contracts that define the required behavior",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_5),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Simulation specs for validating that the workflow uses "
                "small test-first slices and retires simulations with real checks"
            ),
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Feature specification for validating that the child workflow "
                "covers feature acceptance criteria incrementally"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_6,
    output_format="markdown",
    expected_output_files=[_OUTPUT_PHASE_6, _OUTPUT_PHASE_6_REPORT],
    extraction_focus=(
        "Executable implementation workflow: the primary artifact must be a\n"
        "prompt-runner module whose prompts build the real project in small\n"
        "TDD increments, not another planning spec. Workflow truthfulness:\n"
        "the support report must state what the child workflow actually did,\n"
        "which files changed, which test commands ran, and whether the child\n"
        "workflow completed or halted. Final verification readiness: the\n"
        "workflow must end with a final verification prompt so Phase 7 can\n"
        "verify the finished implementation instead of a plan."
    ),
    generation_instructions=(
        "Read the solution design, feature specification, interface\n"
        "contracts, and simulation definitions.\n"
        "\n"
        "Produce two artifacts across the phase's prompt sequence:\n"
        "1. docs/implementation/implementation-workflow.md\n"
        "   - a prompt-runner module with granular prompts that incrementally\n"
        "     build the real implementation using a TDD cadence\n"
        "   - each prompt should take a small slice, write or tighten tests\n"
        "     first, implement only enough code to pass, then preserve the\n"
        "     resulting project state for the next prompt\n"
        "   - the last child prompt must perform final verification of the\n"
        "     assembled implementation\n"
        "2. docs/implementation/implementation-run-report.yaml\n"
        "   - a truthful report written by the supervising prompt after the\n"
        "     child workflow has been run or resumed\n"
        "\n"
        "The primary artifact is the workflow prompt file, not a YAML\n"
        "implementation plan. The workflow must be executable by prompt-runner\n"
        "and should create real project files such as source code, tests, and\n"
        "README content inside the current worktree."
    ),
    judge_guidance=(
        "Check the two PH-006 artifacts for these failure modes:\n"
        "\n"
        "1. Non-executable workflow: the workflow file is prose about\n"
        "   implementation rather than a runnable prompt-runner module.\n"
        "2. Broken TDD cadence: child prompts implement large batches of work\n"
        "   without test-first steps or without re-running the relevant tests.\n"
        "3. Overlarge slices: a single child prompt attempts to implement too\n"
        "   much of the solution at once instead of building incrementally.\n"
        "4. Traceability gaps: the workflow ignores required features,\n"
        "   contracts, or simulation-backed behaviors from prior phases.\n"
        "5. Missing final verification: the child workflow does not end with\n"
        "   a final verification step over the built implementation.\n"
        "6. False run reporting: the support report claims files, commands, or\n"
        "   completion states not grounded in the actual child run."
    ),
    artifact_format="markdown",
    artifact_schema_description=(
        "Primary artifact:\n"
        "  docs/implementation/implementation-workflow.md\n"
        "  - prompt-runner markdown module\n"
        "  - file-level `### Module` slug: implementation-workflow\n"
        "  - at least two prompts\n"
        "  - each prompt advances the real implementation through a small,\n"
        "    test-first slice\n"
        "  - final child prompt performs final verification\n"
        "\n"
        "Support artifact:\n"
        "  docs/implementation/implementation-run-report.yaml\n"
        "  child_prompt_path: \"docs/implementation/implementation-workflow.md\"\n"
        "  child_run_dir: \"/abs/or/relative/worktree/path\"\n"
        "  execution_mode: \"fresh\"  # fresh | resume\n"
        "  completion_status: \"completed\"  # completed | halted\n"
        "  halt_reason: \"\"\n"
        "  prompt_results:\n"
        "    - prompt_index: 1\n"
        "      title: \"Prompt title\"\n"
        "      verdict: \"pass\"\n"
        "      iterations: 1\n"
        "  files_changed: [\"relative/path\", ...]\n"
        "  test_commands_observed:\n"
        "    - command: \"pytest -q\"\n"
        "      exit_code: 0\n"
        "  next_action: \"none\""
    ),
    checklist_examples_good=[
        (
            "The workflow file contains a small sequence of runnable child "
            "prompts that introduce tests first, then implementation, and "
            "ends with a final verification prompt"
        ),
        (
            "The run report names only files and test commands that the child "
            "workflow actually produced or observed in the current worktree"
        ),
    ],
    checklist_examples_bad=[
        "The implementation approach seems reasonable",
        "The report mentions the child run",
    ],
    prompt_module_path=_PROMPT_PHASE_6,
)

# ---------------------------------------------------------------------------
# Phase 7: Verification Sweep
# ---------------------------------------------------------------------------

_PHASE_7 = PhaseConfig(
    phase_id="PH-007-verification-sweep",
    phase_name="Verification Sweep",
    phase_number=7,
    abbreviation="VS",
    predecessors=["PH-006-incremental-implementation"],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_0),
            role=InputRole.PRIMARY,
            format="yaml",
            description=(
                "Requirements inventory whose RI-* items must be verified "
                "against the finished implementation"
            ),
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Feature specification for validating feature coverage and "
                "mapping requirement results back to FT-* items"
            ),
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_6),
            role=InputRole.VALIDATION_REFERENCE,
            format="markdown",
            description=(
                "Implementation workflow prompt used to understand what the "
                "child prompts were supposed to build and verify"
            ),
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_6_REPORT),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Implementation run report containing the child execution "
                "evidence that final verification must cross-check"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_7,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_7],
    extraction_focus=(
        "Truthful final verification: every requirement result must be grounded\n"
        "in actual implementation evidence and actual verification commands.\n"
        "Coverage clarity: the report must account for every RI-* item as\n"
        "satisfied, partial, or unsatisfied without inflating support.\n"
        "Implementation alignment: the verification evidence must be consistent\n"
        "with the child workflow and child run report instead of inventing a\n"
        "cleaner outcome than the implementation really achieved."
    ),
    generation_instructions=(
        "Read the requirements inventory, feature specification,\n"
        "implementation workflow, and implementation run report. Produce a\n"
        "final verification report YAML at docs/verification/verification-report.yaml.\n"
        "\n"
        "verification_commands:\n"
        "  - command: pytest -q\n"
        "    exit_code: 0\n"
        "    purpose: explain what this verifies\n"
        "    evidence: what file, output, or requirement result it supports\n"
        "\n"
        "requirement_results:\n"
        "  - inventory_ref: RI-NNN\n"
        "    feature_refs: [FT-NNN, ...]\n"
        "    status: satisfied | partial | unsatisfied\n"
        "    evidence:\n"
        "      files: [relative/path, ...]\n"
        "      commands: [pytest -q, ...]\n"
        "      notes: concise explanation of why this status is justified\n"
        "\n"
        "coverage_summary:\n"
        "  total_requirements: N\n"
        "  satisfied: N\n"
        "  partial: N\n"
        "  unsatisfied: N\n"
        "\n"
        "Account for every RI-* item exactly once. Do not invent implementation\n"
        "success that the child run report does not support."
    ),
    judge_guidance=(
        "Check for these failure modes:\n"
        "\n"
        "1. Phantom satisfaction: the report marks a requirement satisfied\n"
        "   without enough file or command evidence.\n"
        "2. Ignored child-run outcome: the report treats the implementation\n"
        "   as complete even though the run report or workflow shows gaps.\n"
        "3. Thin evidence: requirement rows cite vague notes but no concrete\n"
        "   files or commands when concrete evidence should exist.\n"
        "4. Coverage overstatement: coverage_summary inflates satisfied or\n"
        "   partial counts beyond what the requirement rows support.\n"
        "5. Unsupported feature links: feature_refs cite FT-* items whose\n"
        "   meaning is not actually reflected in the evidence."
    ),
    artifact_format="yaml",
    artifact_schema_description=(
        "verification_commands:\n"
        "  - command: \"pytest -q\"\n"
        "    exit_code: 0\n"
        "    purpose: \"...\"\n"
        "    evidence: \"...\"\n"
        "\n"
        "requirement_results:\n"
        "  - inventory_ref: \"RI-NNN\"\n"
        "    feature_refs: [\"FT-NNN\", ...]\n"
        "    status: \"satisfied\"  # satisfied | partial | unsatisfied\n"
        "    evidence:\n"
        "      files: [\"relative/path\", ...]\n"
        "      commands: [\"pytest -q\", ...]\n"
        "      notes: \"...\"\n"
        "\n"
        "coverage_summary:\n"
        "  total_requirements: 0\n"
        "  satisfied: 0\n"
        "  partial: 0\n"
        "  unsatisfied: 0"
    ),
    checklist_examples_good=[
        (
            "Every RI-* item appears exactly once in requirement_results and "
            "rows marked satisfied cite concrete file or command evidence"
        ),
        (
            "verification_commands are a subset of the commands that the "
            "implementation child run actually observed"
        ),
    ],
    checklist_examples_bad=[
        "The final verification seems thorough",
        "The report references implementation evidence",
    ],
    prompt_module_path=_PROMPT_PHASE_7,
)


# ---------------------------------------------------------------------------
# Module-level registries
# ---------------------------------------------------------------------------

PHASES: list[PhaseConfig] = [
    _PHASE_0,
    _PHASE_1,
    _PHASE_2_ARCHITECTURE,
    _PHASE_3,
    _PHASE_4,
    _PHASE_5,
    _PHASE_6,
    _PHASE_7,
]
"""All eight phases in execution order (Phase 0 first, Phase 7 last)."""

PHASE_MAP: dict[str, PhaseConfig] = {phase.phase_id: phase for phase in PHASES}
"""Lookup PhaseConfig by phase_id."""


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def get_phase(phase_id: str) -> PhaseConfig:
    """Return the PhaseConfig for *phase_id*.

    Raises :class:`ValueError` if the phase_id is not recognised.
    """
    try:
        return PHASE_MAP[phase_id]
    except KeyError:
        valid = ", ".join(PHASE_MAP)
        raise ValueError(
            f"Unknown phase_id {phase_id!r}.  Valid IDs: {valid}"
        ) from None


def normalize_phase_selection(phase_ids: list[str]) -> list[str]:
    """Validate, deduplicate, and sort selected phase IDs by methodology order.

    The caller may provide a subset in any order. The methodology runner
    executes that subset in the canonical phase order defined by ``PHASES``.
    """
    requested = {get_phase(phase_id).phase_id for phase_id in phase_ids}
    return [phase.phase_id for phase in PHASES if phase.phase_id in requested]


def resolve_input_sources(
    phase: PhaseConfig,
    workspace: Path,
) -> list[tuple[Path, InputRole, str]]:
    """Resolve input-source templates to concrete paths.

    Replaces ``{workspace}`` in each template's *ref_template* with
    the actual *workspace* path and returns a list of
    ``(resolved_path, role, description)`` tuples.
    """
    results: list[tuple[Path, InputRole, str]] = []
    workspace_str = str(workspace)
    for template in phase.input_source_templates:
        resolved = template.ref_template.replace("{workspace}", workspace_str)
        results.append((Path(resolved), template.role, template.description))
    return results
