"""Phase definitions for the seven methodology phases (PH-000 through PH-006).

This module is a pure data registry.  Each phase is a frozen PhaseConfig
instance containing everything the prompt generator needs to produce a
prompt-runner file and everything the cross-reference verifier needs to
check the output.

Output paths align with CD-002 Section 4.5 workspace layout::

    docs/requirements/requirements-inventory.yaml   # Phase 0
    docs/features/feature-specification.yaml        # Phase 1
    docs/design/solution-design.yaml                # Phase 2
    docs/design/interface-contracts.yaml            # Phase 3
    docs/simulations/simulation-definitions.yaml    # Phase 4
    docs/implementation/implementation-plan.yaml    # Phase 5
    docs/verification/verification-report.yaml      # Phase 6

Public API
----------
PHASES : list[PhaseConfig]
    All seven phases in execution order (Phase 0 first, Phase 6 last).
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
_OUTPUT_PHASE_1 = "docs/features/feature-specification.yaml"
_OUTPUT_PHASE_2 = "docs/design/solution-design.yaml"
_OUTPUT_PHASE_3 = "docs/design/interface-contracts.yaml"
_OUTPUT_PHASE_4 = "docs/simulations/simulation-definitions.yaml"
_OUTPUT_PHASE_5 = "docs/implementation/implementation-plan.yaml"
_OUTPUT_PHASE_6 = "docs/verification/verification-report.yaml"


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
    expected_output_files=[_OUTPUT_PHASE_0],
    extraction_focus=(
        "Completeness: every requirement-bearing statement in the source\n"
        "document must appear as an inventory item.  Atomicity: compound\n"
        "requirements (those containing 'and', 'or', or multiple independent\n"
        "clauses) must be split into separate RI-* items.  Fidelity: the\n"
        "verbatim_quote field must reproduce the original text exactly --\n"
        "no paraphrasing, summarisation, or interpretation."
    ),
    generation_instructions=(
        "Read the raw requirements document and produce a YAML inventory\n"
        "file at the designated output path.\n"
        "\n"
        "Each item has these fields:\n"
        "  - id: RI-NNN (zero-padded three-digit sequential number)\n"
        "  - category: one of functional, non_functional, constraint,\n"
        "    assumption\n"
        "  - verbatim_quote: the exact text from the source document\n"
        "  - source_location: section heading or paragraph identifier\n"
        "  - tags: list of domain keywords for cross-referencing\n"
        "\n"
        "Scan every section, paragraph, table row, and list item.  Any\n"
        "statement containing shall, must, will, should, or an imperative\n"
        "verb describing system behaviour is a requirement.  Assumptions\n"
        "and constraints that bound the solution space are also inventory\n"
        "items.\n"
        "\n"
        "When a paragraph contains multiple independent requirements,\n"
        "split them into separate items.  Preserve the original wording\n"
        "in verbatim_quote -- do not rewrite, summarise, or interpret."
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
        "3. Unsplit compounds: look for items whose verbatim_quote contains\n"
        "   'and' or 'or' joining independent clauses that describe\n"
        "   distinct behaviours.  Flag as needing decomposition.\n"
        "4. Lost nuance: check that category assignments match the language\n"
        "   strength (shall/must -> functional, should -> non_functional,\n"
        "   given/assuming -> assumption, within/limited-to -> constraint).\n"
        "5. Wrong categories: verify constraints vs. assumptions vs.\n"
        "   functional vs. non_functional.\n"
        "\n"
        "The inventory MUST be valid YAML parseable by a standard YAML\n"
        "parser.  All id values must follow the RI-NNN pattern and be\n"
        "unique across the file."
    ),
    artifact_format="yaml",
    artifact_schema_description=(
        "items:\n"
        "  - id: \"RI-NNN\"           # zero-padded three-digit sequential ID\n"
        "    category: \"functional\"  # functional | non_functional | constraint | assumption\n"
        "    verbatim_quote: \"...\"   # exact text from source document\n"
        "    source_location: \"...\"  # section heading or paragraph identifier\n"
        "    tags: [\"tag1\", \"tag2\"]  # domain keywords for cross-referencing"
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
)

# ---------------------------------------------------------------------------
# Phase 2: Solution Design
# ---------------------------------------------------------------------------

_PHASE_2 = PhaseConfig(
    phase_id="PH-002-solution-design",
    phase_name="Solution Design",
    phase_number=2,
    abbreviation="SD",
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
                "verification"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_2,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_2],
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
)

# ---------------------------------------------------------------------------
# Phase 3: Interface Contracts
# ---------------------------------------------------------------------------

_PHASE_3 = PhaseConfig(
    phase_id="PH-003-interface-contracts",
    phase_name="Interface Contracts",
    phase_number=3,
    abbreviation="CI",
    predecessors=["PH-002-solution-design"],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_2),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Solution design with components and interactions from Phase 2",
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
    output_artifact_path=_OUTPUT_PHASE_3,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_3],
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
)

# ---------------------------------------------------------------------------
# Phase 4: Intelligent Simulations
# ---------------------------------------------------------------------------

_PHASE_4 = PhaseConfig(
    phase_id="PH-004-intelligent-simulations",
    phase_name="Intelligent Simulations",
    phase_number=4,
    abbreviation="IS",
    predecessors=["PH-003-interface-contracts"],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_3),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Interface contracts from Phase 3",
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
    output_artifact_path=_OUTPUT_PHASE_4,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_4],
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
)

# ---------------------------------------------------------------------------
# Phase 5: Implementation Plan
# ---------------------------------------------------------------------------

_PHASE_5 = PhaseConfig(
    phase_id="PH-005-implementation-plan",
    phase_name="Implementation Plan",
    phase_number=5,
    abbreviation="II",
    predecessors=[
        "PH-003-interface-contracts",
        "PH-004-intelligent-simulations",
    ],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_3),
            role=InputRole.PRIMARY,
            format="yaml",
            description="Interface contracts that define what to build",
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_4),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Simulation specs for validating that the implementation "
                "plan accounts for simulation replacement"
            ),
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Feature specification for validating that unit tests "
                "trace to acceptance criteria"
            ),
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_2),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Solution design for validating that build order "
                "respects component dependencies"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_5,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_5],
    extraction_focus=(
        "Ordering correctness: the component build order must respect\n"
        "the dependency graph from the solution design -- no component\n"
        "is built before its dependencies.  Test traceability: every\n"
        "unit test traces to at least one AC-* acceptance criterion.\n"
        "Simulation replacement: for each SIM-* simulation, the plan\n"
        "specifies when it gets replaced by a real implementation and\n"
        "which integration tests must re-run after replacement."
    ),
    generation_instructions=(
        "Read the interface contracts, simulation specs, feature spec,\n"
        "and solution design.  Produce an implementation plan YAML.\n"
        "\n"
        "build_order:\n"
        "  - step: 1\n"
        "    component_ref: CMP-NNN\n"
        "    rationale: why this component is built at this position\n"
        "    contracts_implemented: [CTR-NNN, ...]\n"
        "    simulations_used: [SIM-NNN, ...]  # sims used as test doubles\n"
        "\n"
        "unit_test_plan:\n"
        "  - component_ref: CMP-NNN\n"
        "    tests:\n"
        "      - name: test name\n"
        "        description: what the test verifies\n"
        "        acceptance_criteria_refs: [AC-NNN-NN, ...]\n"
        "        contract_ref: CTR-NNN  # which contract operation is tested\n"
        "\n"
        "integration_test_plan:\n"
        "  - name: integration test name\n"
        "    components_involved: [CMP-NNN, ...]\n"
        "    contracts_exercised: [CTR-NNN, ...]\n"
        "    scenarios_from: [SIM-NNN, ...]  # scenarios to reuse\n"
        "\n"
        "simulation_replacement_sequence:\n"
        "  - simulation_ref: SIM-NNN\n"
        "    replaced_at_step: N  # build_order step when real impl is ready\n"
        "    integration_tests_to_rerun: [test-name, ...]\n"
        "\n"
        "Build order must proceed from leaf components (no dependencies)\n"
        "to composite ones.  At each step, simulations stand in for\n"
        "components not yet built."
    ),
    judge_guidance=(
        "Check for these failure modes:\n"
        "\n"
        "1. Ordering violations: verify that no build_order step references\n"
        "   a component whose dependencies have not yet been built or\n"
        "   simulated in a prior step.\n"
        "2. Test sufficiency: every AC-* acceptance criterion from Phase 1\n"
        "   must appear in at least one unit test's acceptance_criteria_refs\n"
        "   or one integration test's scenario coverage.\n"
        "3. Completion gaps: every CMP-* component from Phase 2 must appear\n"
        "   in the build_order.  Every CTR-* contract from Phase 3 must\n"
        "   appear in at least one build step's contracts_implemented.\n"
        "4. Simulation orphans: every SIM-* from Phase 4 must appear in\n"
        "   the simulation_replacement_sequence with a concrete replaced_at_step.\n"
        "5. Missing re-test triggers: when a simulation is replaced by a\n"
        "   real implementation, all integration tests that previously\n"
        "   used that simulation must be listed in integration_tests_to_rerun."
    ),
    artifact_format="yaml",
    artifact_schema_description=(
        "build_order:\n"
        "  - step: 1\n"
        "    component_ref: \"CMP-NNN\"\n"
        "    rationale: \"...\"\n"
        "    contracts_implemented: [\"CTR-NNN\", ...]\n"
        "    simulations_used: [\"SIM-NNN\", ...]\n"
        "\n"
        "unit_test_plan:\n"
        "  - component_ref: \"CMP-NNN\"\n"
        "    tests:\n"
        "      - name: \"...\"\n"
        "        description: \"...\"\n"
        "        acceptance_criteria_refs: [\"AC-NNN-NN\", ...]\n"
        "        contract_ref: \"CTR-NNN\"\n"
        "\n"
        "integration_test_plan:\n"
        "  - name: \"...\"\n"
        "    components_involved: [\"CMP-NNN\", ...]\n"
        "    contracts_exercised: [\"CTR-NNN\", ...]\n"
        "    scenarios_from: [\"SIM-NNN\", ...]\n"
        "\n"
        "simulation_replacement_sequence:\n"
        "  - simulation_ref: \"SIM-NNN\"\n"
        "    replaced_at_step: 1\n"
        "    integration_tests_to_rerun: [\"...\"]"
    ),
    checklist_examples_good=[
        (
            "No build_order step references a component whose "
            "dependencies (from Phase 2 design) appear at a later step "
            "without a simulation standing in"
        ),
        (
            "Every AC-* acceptance criterion from Phase 1 is referenced "
            "by at least one unit test or integration test in the plan"
        ),
    ],
    checklist_examples_bad=[
        "The implementation plan covers all components",
        "Tests are planned",
    ],
)

# ---------------------------------------------------------------------------
# Phase 6: Verification Sweep
# ---------------------------------------------------------------------------

_PHASE_6 = PhaseConfig(
    phase_id="PH-006-verification-sweep",
    phase_name="Verification Sweep",
    phase_number=6,
    abbreviation="VS",
    predecessors=["PH-005-implementation-plan"],
    input_source_templates=[
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_1),
            role=InputRole.PRIMARY,
            format="yaml",
            description=(
                "Feature specification with acceptance criteria -- the "
                "primary source for E2E test derivation"
            ),
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_5),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Implementation plan for validating that E2E tests "
                "align with the build and integration test plan"
            ),
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_2),
            role=InputRole.VALIDATION_REFERENCE,
            format="yaml",
            description=(
                "Solution design for validating that E2E tests cover "
                "component interaction paths and realization maps"
            ),
        ),
        InputSourceTemplate(
            ref_template=_tpl(_OUTPUT_PHASE_0),
            role=InputRole.UPSTREAM_TRACEABILITY,
            format="yaml",
            description=(
                "Requirements inventory for end-to-end traceability "
                "from RI through FT, AC, to E2E"
            ),
        ),
    ],
    output_artifact_path=_OUTPUT_PHASE_6,
    output_format="yaml",
    expected_output_files=[_OUTPUT_PHASE_6],
    extraction_focus=(
        "Chain completeness: every RI-* requirement traces through FT-*\n"
        "features and AC-* acceptance criteria to at least one E2E-*\n"
        "test.  No broken chains.  Test specificity: every E2E test\n"
        "defines concrete setup, action, and assertion steps -- not\n"
        "abstract descriptions.  Negative coverage: critical features\n"
        "must have E2E tests for both the success path and at least one\n"
        "failure/boundary path."
    ),
    generation_instructions=(
        "Read the feature specification, implementation plan, solution\n"
        "design, and requirements inventory.  Produce a verification\n"
        "plan YAML.\n"
        "\n"
        "e2e_tests:\n"
        "  - id: E2E-AREA-NNN  # AREA is a short domain tag\n"
        "    name: descriptive test name\n"
        "    feature_ref: FT-NNN\n"
        "    acceptance_criteria_refs: [AC-NNN-NN, ...]\n"
        "    type: positive | negative | boundary\n"
        "    setup:\n"
        "      - step: description of precondition setup\n"
        "    actions:\n"
        "      - step: description of user or system action\n"
        "    assertions:\n"
        "      - description of what to verify after the actions\n"
        "\n"
        "traceability_matrix:\n"
        "  - inventory_ref: RI-NNN\n"
        "    feature_refs: [FT-NNN, ...]\n"
        "    acceptance_criteria_refs: [AC-NNN-NN, ...]\n"
        "    e2e_test_refs: [E2E-AREA-NNN, ...]\n"
        "    coverage_status: covered | partial | uncovered\n"
        "\n"
        "coverage_summary:\n"
        "  total_requirements: N\n"
        "  covered: N\n"
        "  partial: N\n"
        "  uncovered: N\n"
        "  coverage_percentage: NN.N\n"
        "\n"
        "Use the solution design to verify that E2E tests exercise the\n"
        "component interaction paths from the feature_realization_map.\n"
        "Every chain in the traceability matrix must reach from RI-*\n"
        "through FT-* and AC-* to at least one E2E-* test.  Gaps must\n"
        "be marked as 'uncovered' with a reason."
    ),
    judge_guidance=(
        "Check for these failure modes:\n"
        "\n"
        "1. Broken chains: verify every row in the traceability_matrix has\n"
        "   non-empty feature_refs, acceptance_criteria_refs, AND\n"
        "   e2e_test_refs.  Flag any row where the chain is incomplete.\n"
        "2. Superficial tests: flag E2E tests whose assertions list\n"
        "   contains only generic checks ('page loads', 'no errors')\n"
        "   without verifying business-specific outcomes.\n"
        "3. Missing negative tests: for each feature that handles user\n"
        "   input or external data, verify there is at least one E2E\n"
        "   test of type 'negative' or 'boundary'.\n"
        "4. Phantom references: every FT-NNN, AC-NNN-NN, and RI-NNN\n"
        "   referenced in the matrix must actually exist in the Phase 0\n"
        "   and Phase 1 artifacts.\n"
        "5. Coverage accuracy: verify that coverage_summary numbers match\n"
        "   the actual counts in the traceability_matrix."
    ),
    artifact_format="yaml",
    artifact_schema_description=(
        "e2e_tests:\n"
        "  - id: \"E2E-AREA-NNN\"  # AREA is a short domain tag\n"
        "    name: \"...\"\n"
        "    feature_ref: \"FT-NNN\"\n"
        "    acceptance_criteria_refs: [\"AC-NNN-NN\", ...]\n"
        "    type: \"positive\"  # positive | negative | boundary\n"
        "    setup:\n"
        "      - step: \"...\"\n"
        "    actions:\n"
        "      - step: \"...\"\n"
        "    assertions:\n"
        "      - \"...\"\n"
        "\n"
        "traceability_matrix:\n"
        "  - inventory_ref: \"RI-NNN\"\n"
        "    feature_refs: [\"FT-NNN\", ...]\n"
        "    acceptance_criteria_refs: [\"AC-NNN-NN\", ...]\n"
        "    e2e_test_refs: [\"E2E-AREA-NNN\", ...]\n"
        "    coverage_status: \"covered\"  # covered | partial | uncovered\n"
        "\n"
        "coverage_summary:\n"
        "  total_requirements: 0\n"
        "  covered: 0\n"
        "  partial: 0\n"
        "  uncovered: 0\n"
        "  coverage_percentage: 0.0"
    ),
    checklist_examples_good=[
        (
            "Every row in the traceability_matrix has a complete chain: "
            "non-empty inventory_ref, feature_refs, acceptance_criteria_refs, "
            "and e2e_test_refs -- no broken links"
        ),
        (
            "Every feature that accepts user input or external data has "
            "at least one E2E test of type 'negative' or 'boundary' "
            "that verifies rejection of invalid inputs"
        ),
    ],
    checklist_examples_bad=[
        "Verification covers the requirements",
        "E2E tests exist",
    ],
)


# ---------------------------------------------------------------------------
# Module-level registries
# ---------------------------------------------------------------------------

PHASES: list[PhaseConfig] = [
    _PHASE_0,
    _PHASE_1,
    _PHASE_2,
    _PHASE_3,
    _PHASE_4,
    _PHASE_5,
    _PHASE_6,
]
"""All seven phases in execution order (Phase 0 first, Phase 6 last)."""

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
