# Build: AI-Driven Development Methodology Runner

This prompt-runner input file produces a complete methodology runner system.
When executed, it generates Python code for a tool that takes a requirements
document as input and runs it through the full 7-phase AI-driven development
pipeline (Phase 0: Requirements Inventory through Phase 6: Verification Sweep),
with separate agents for checklist extraction, validation, generation, and
judgment at each phase.

The generated system reuses the Claude CLI client from prompt-runner and
follows the methodology defined in the AI-Driven Development Methodology
artifacts (Phase Processing Unit schema, Phase Definitions, Agent Role
Specifications, Traceability Infrastructure, Simulation Framework, and
Orchestration design).

## Prompt 1: Solution Design

### 1.1 Generation Prompt

```
You are designing a Python application called "methodology-runner" that
implements an AI-driven software development methodology. The system takes
a requirements document as input and runs it through 7 phases (Phase 0
through Phase 6), producing a complete system design ready for
implementation.

CONTEXT: WHAT THE METHODOLOGY IS

The methodology has 7 phases, each following a uniform "Phase Processing Unit"
pattern:

  Phase 0: Requirements Inventory — extract every idea from raw requirements
  Phase 1: Feature Specification — organize into structured features
  Phase 2: Solution Design — architecture, components, interactions
  Phase 3: Contract-First Interface Definitions — formal schemas for boundaries
  Phase 4: Intelligent Simulations — LLM-powered test doubles per contract
  Phase 5: Incremental Implementation — component-by-component with integration
  Phase 6: Verification Sweep — end-to-end acceptance tests

Each phase follows the Phase Processing Unit pattern:
  1. Checklist Extraction — a dedicated agent reads inputs and produces
     acceptance criteria
  2. Checklist Validation — a separate agent checks the checklist for
     completeness, grounding, and specificity
  3. Artifact Generation — a generator agent produces the phase artifact
     and a traceability mapping
  4. Judgment — a separate judge agent evaluates every checklist item
  5. Revision Loop — if verdict is "revise", generator revises and judge
     re-evaluates ALL items. Bounded by max_iterations.
  6. Phase Output — approved artifact, completed checklist, traceability

The checklist validation is itself a sub-loop (extract -> validate -> revise
checklist if needed), bounded by max_validation_iterations.

CONTEXT: EXISTING CODE TO REUSE

There is an existing "prompt-runner" tool with these reusable components:

  claude_client.py — ClaudeClient protocol, RealClaudeClient (subprocess
    wrapper for the claude CLI with streaming output), ClaudeCall and
    ClaudeResponse dataclasses, ClaudeInvocationError, and a
    NON_INTERACTIVE_SYSTEM_PROMPT constant.

  verdict.py — Verdict enum (PASS, REVISE, ESCALATE), parse_verdict()
    function that extracts VERDICT lines from judge output.

These can be imported directly. The runner.py and parser.py from
prompt-runner are NOT reused — the methodology-runner has its own
orchestration logic.

YOUR TASK

Produce a solution design document that covers:

1. COMPONENT INVENTORY — list every Python module the system needs, with
   its responsibility (one sentence each). Group into packages.

2. DATA FLOW — describe how data flows from the user's requirements document
   through all 7 phases to the final verification plan. Show what each
   agent receives and produces at each step.

3. AGENT CALL ARCHITECTURE — how the system invokes Claude for each agent
   role. Key decisions:
   - Each agent role (extractor, validator, generator, judge) gets its own
     Claude session (separate context, no cross-contamination).
   - The system prompt for each role is assembled from a base role template
     plus phase-specific configuration (extraction focus, generation
     instructions, judge guidance, etc.).
   - The traceability validator runs between phases, not within them.

4. STATE MANAGEMENT — how project state is persisted between phases.
   The system must support resuming from the last completed phase if
   interrupted. Define the directory structure for a project run.

5. TRACEABILITY — how traceability links are stored (YAML files per phase),
   how they are validated (completeness, consistency, coverage), and how
   agents query them.

6. CONFIGURATION — what the user can configure: max iterations per phase,
   escalation policies, model selection, which phases to run.

7. INTERFACE CONTRACTS between components — for each module, define its
   public functions/classes with signatures and brief docstrings. Use
   Python type hints. Do NOT write implementations — just the interface.

Format: a markdown document with the sections above. Use 4-space indented
code for Python signatures (no triple-backtick fences). Keep it concrete
and implementable — another developer (or AI) should be able to implement
each module from this design alone.
```

### 1.2 Validation Prompt

```
You are reviewing a solution design for a "methodology-runner" system that
implements an AI-driven development methodology with 7 phases.

Evaluate against these criteria:

COMPONENT COMPLETENESS
- Is there a module for data models (dataclasses)?
- Is there a module for agent prompt templates?
- Is there a module for phase definitions (all 7 phases)?
- Is there a module for traceability storage and validation?
- Is there a module for running a single phase (the Phase Processing Unit)?
- Is there a module for the pipeline orchestrator?
- Is there a module for CLI / entry point?
- Is the reuse of claude_client.py and verdict.py from prompt-runner explicit?

DATA FLOW CORRECTNESS
- Can you trace the path of a single requirement from raw input through
  all 7 phases?
- At each phase, are the inputs clearly specified (which prior artifacts)?
- Does the checklist extraction agent receive only input sources, not
  the generated artifact?
- Does the judge agent receive the checklist and artifact but NOT the
  generation instructions?
- Are generator and judge always in separate sessions?

AGENT ROLE SEPARATION
- Are all four roles (extractor, validator, generator, judge) identified
  as separate Claude sessions?
- Is the traceability validator identified as a distinct check?
- Is there any pathway where one role could influence another's domain?

STATE AND RESUMABILITY
- Is the project directory structure defined?
- Can the system determine which phases are complete from disk state?
- Is checkpointing defined (what gets written when)?

INTERFACE QUALITY
- Do the public interfaces have type hints?
- Are return types specified?
- Could you implement each module from the interface alone?
- Are there any circular dependencies between modules?

For each criterion: status (pass/fail/partial), evidence, and if not pass,
what specifically needs to change.

Flag any uncovered concerns.
```

## Prompt 2: Data Models

### 2.1 Generation Prompt

```
Using the solution design from Prompt 1, implement the data models module.

Produce a single Python file: methodology_runner/models.py

This module defines all dataclasses and enums used across the system.
It has NO dependencies on other methodology-runner modules (it may import
from standard library and from the prompt-runner verdict module).

Required types (from the solution design):

1. Enums:
   - EscalationPolicy: halt, flag_and_continue, human_review
   - PhaseStatus: pending, running, passed, escalated, skipped
   - ChecklistItemStatus: pass_, fail, partial (note: "pass" is reserved)
   - VerificationMethod: schema_inspection, behavioral_trace, content_match,
     coverage_query, manual_review
   - InputRole: primary, validation_reference, upstream_traceability

2. Configuration dataclasses:
   - InputSource: ref (path), role, format, description
   - PhaseConfig: phase_id, phase_name, abbreviation, input_source_templates
     (list of InputSource patterns with {project_dir} placeholders),
     extraction_focus (str), generation_instructions (str),
     judge_guidance (str), artifact_format (str), artifact_schema_description
     (str), max_iterations (int), max_validation_iterations (int),
     escalation_policy, checklist_examples (good and bad)

3. Runtime dataclasses:
   - ChecklistItem: id, source_ref, criterion, verification_method
   - Checklist: items (list of ChecklistItem), phase_id
   - TraceabilityEntry: artifact_element_ref, checklist_item_ids (list),
     input_source_refs (list)
   - TraceabilityMapping: entries (list of TraceabilityEntry), phase_id
   - ChecklistEvaluation: checklist_item_id, result (ChecklistItemStatus),
     evidence (str), reason (str), artifact_location (str)
   - UncoveredConcern: id, concern (str), severity (str),
     artifact_location (str)
   - JudgmentResult: evaluations (list), uncovered_concerns (list),
     verdict (Verdict)
   - IterationRecord: iteration (int), verdict (Verdict),
     passed_count (int), failed_count (int), partial_count (int)
   - PhaseResult: phase_id, status (PhaseStatus), artifact_path (str),
     checklist_path (str), traceability_path (str),
     iterations (list of IterationRecord), final_verdict (Verdict or None)
   - ProjectState: project_dir (Path), requirements_path (Path),
     phase_results (dict mapping phase_id to PhaseResult),
     started_at (str), current_phase (str or None)

4. Serialization:
   - Each dataclass should have a to_dict() method returning a plain dict
   - Include a module-level function for loading ProjectState from a
     JSON file and saving it

Keep the module focused: data definitions and serialization only, no
business logic. Use frozen=True for configuration types, regular
dataclasses for mutable runtime types.

Produce the complete Python file with all imports, docstrings, and type
hints.
```

### 2.2 Validation Prompt

```
You are reviewing a Python data models module for a methodology-runner
system.

Evaluate against these criteria:

TYPE COMPLETENESS
- Are all types listed in the prompt present (all enums, config types,
  runtime types)?
- Does each dataclass have all the fields specified?
- Are type hints present on every field?
- Is Verdict imported from the prompt-runner verdict module?

SERIALIZATION
- Does every dataclass have a to_dict() method?
- Are there load/save functions for ProjectState?
- Can all types round-trip through to_dict() and back?

DESIGN QUALITY
- Are configuration types frozen?
- Are there no circular imports?
- Is there no business logic (only data definitions and serialization)?
- Are docstrings present on every class?
- Do enum values use valid Python identifiers (not "pass")?

USABILITY
- Can PhaseConfig's input_source_templates be resolved with a project
  directory to produce actual InputSource paths?
- Is ProjectState sufficient to determine which phases have completed
  and what the current state is?
- Can you reconstruct the full project history from ProjectState?

For each criterion: pass/fail/partial with evidence.
```

## Prompt 3: Agent Prompt Templates

### 3.1 Generation Prompt

```
Using the solution design and data models from prior prompts, implement the
agent prompt templates module.

Produce a single Python file: methodology_runner/agent_prompts.py

This module contains string templates for each agent role's system prompt,
plus functions that assemble a complete prompt for a specific phase by
combining the role template with phase-specific configuration.

AGENT ROLES AND THEIR TEMPLATES:

1. CHECKLIST EXTRACTOR
   Base template covers:
   - Identity: "You are the Checklist Extractor agent..."
   - Boundaries: reads inputs, produces checklist, does NOT generate artifacts
   - Output format: YAML with checklist_items list (id, source_ref, criterion,
     verification_method)
   - Element locator grammar: / (heading), $. (dot-path), L (line range),
     @ (named anchor)
   - Quality standards: good criteria are concrete, observable, binary;
     bad criteria are vague, subjective, compound
   - Must NOT soften requirements, resolve ambiguities, or invent requirements
   - Handling validation feedback: revise specific items based on failed_check,
     problematic_item_ids, uncovered_input_refs

   Phase-specific insertion points:
   - {extraction_focus} — what to look for in this phase
   - {phase_id}, {phase_name}, {abbreviation}
   - {artifact_schema_description} — what the artifact will look like
   - {checklist_examples} — good/bad examples for this phase

2. CHECKLIST VALIDATOR
   Base template covers:
   - Identity: "You are the Checklist Validator agent..."
   - Boundaries: validates checklists, does NOT extract or generate
   - Three ordered checks:
     a. Grounding (order 1): every item traces to an input source element
     b. Coverage (order 2): every requirement in inputs has a checklist item
     c. Specificity (order 3): items are precise enough for pass/fail
   - After grounding removes items, coverage must re-run
   - Output format: YAML with validation_result (passed: bool,
     failed_check, problematic_item_ids, uncovered_input_refs,
     specificity_notes)

   Phase-specific insertion points:
   - {phase_id}, {phase_name}
   - {input_source_descriptions} — what the input sources contain

3. ARTIFACT GENERATOR
   Base template covers:
   - Identity: "You are the Artifact Generator agent..."
   - Boundaries: produces artifact + traceability mapping, does NOT
     modify checklist
   - Must address every checklist item
   - Traceability mapping format: list of (artifact_element_ref,
     checklist_item_ids, input_source_refs)
   - Output structure: artifact content first, then a YAML section
     headed "# TRACEABILITY MAPPING" with the mapping
   - On revision: receives full prior artifact + judge feedback,
     must fix failures without regressing passes

   Phase-specific insertion points:
   - {generation_instructions} — what to produce for this phase
   - {artifact_format}, {artifact_schema_description}
   - {phase_id}, {phase_name}

4. JUDGE
   Base template covers:
   - Identity: "You are the Judge agent..."
   - Boundaries: evaluates artifact against checklist, does NOT modify
     artifact or checklist
   - Must independently verify traceability claims
   - Evaluates EVERY checklist item on EVERY iteration (catches regressions)
   - Output format: YAML with evaluations (per item: checklist_item_id,
     result, evidence, reason, artifact_location), uncovered_concerns
     (id, concern, severity, artifact_location), verdict
   - Verdict rules: all pass -> pass, any fail/partial -> revise
   - Must provide actionable feedback on failures
   - artifact_location: MUST be non-empty for pass/partial; for fail,
     non-empty when defect exists, empty only when element is missing

   Phase-specific insertion points:
   - {judge_guidance} — phase-specific quality concerns
   - {phase_id}, {phase_name}

5. TRACEABILITY VALIDATOR
   Base template covers:
   - Identity: "You are the Traceability Validator agent..."
   - Runs between phases, not within them
   - Checks: completeness (every element in phase N links to phase N-1),
     consistency (all referenced IDs exist), coverage (percentage report),
     orphan detection, dead-end detection
   - Output format: YAML with validation_result (passed: bool,
     orphaned_elements, dead_ends, broken_references, coverage_summary)

FUNCTIONS TO IMPLEMENT:

    def build_extractor_prompt(phase: PhaseConfig, input_paths: dict[str, str]) -> str
    def build_validator_prompt(phase: PhaseConfig, input_descriptions: list[str]) -> str
    def build_generator_prompt(phase: PhaseConfig, checklist: str) -> str
    def build_judge_prompt(phase: PhaseConfig) -> str
    def build_traceability_validator_prompt(phase_ids: list[str]) -> str

    def build_extractor_revision_message(validation_feedback: str) -> str
    def build_generator_revision_message(judge_feedback: str) -> str
    def build_judge_revision_message(revised_artifact: str) -> str

Each build_*_prompt function returns the complete system+user prompt for
that agent's first invocation. The revision message functions return the
follow-up message for subsequent iterations.

IMPORTANT: The VERDICT instruction ("End your response with VERDICT: pass,
VERDICT: revise, or VERDICT: escalate") must be appended to judge and
validator prompts. Use a constant for this, similar to prompt-runner's
VERDICT_INSTRUCTION.

Produce the complete Python file. Use multi-line strings for templates.
Use str.format() or Template substitution for insertion points. Include
all imports and docstrings.
```

### 3.2 Validation Prompt

```
You are reviewing the agent prompt templates module for a methodology-runner.

Evaluate against these criteria:

ROLE COVERAGE
- Are all 5 roles implemented (extractor, validator, generator, judge,
  traceability validator)?
- Does each role template clearly state the agent's identity and boundaries?
- Does each template specify the exact output format?
- Does each template include explicit "do NOT" instructions?

SEPARATION ENFORCEMENT
- Does the extractor template forbid artifact generation?
- Does the generator template forbid checklist modification?
- Does the judge template forbid artifact modification?
- Does the validator template forbid extraction or generation?

PHASE PARAMETERIZATION
- Does each build_*_prompt function accept a PhaseConfig?
- Are all insertion points from the design populated from PhaseConfig fields?
- Would two different phases produce meaningfully different prompts?

VERDICT HANDLING
- Is VERDICT instruction appended to judge and validator prompts?
- Is the instruction consistent with prompt-runner's format?

REVISION SUPPORT
- Is there a revision message function for each role that revises
  (extractor and generator)?
- Does the judge revision message include anti-anchoring language
  (telling the judge to re-evaluate everything, not anchor to prior)?
- Does the generator revision message tell it to preserve passing items?

OUTPUT FORMAT CLARITY
- Could a naive LLM follow the output format instructions to produce
  parseable YAML?
- Are field names and structures specified precisely?
- Are examples included in the templates?

For each criterion: pass/fail/partial with evidence.
```

## Prompt 4: Phase Definitions

### 4.1 Generation Prompt

```
Using the solution design, data models, and agent prompt templates from
prior prompts, implement the phase definitions module.

Produce a single Python file: methodology_runner/phases.py

This module defines all 7 phases as PhaseConfig instances. Each phase is
a complete configuration that, when passed to the agent prompt template
functions, produces the correct prompts for that phase's agents.

Define these phases:

PHASE 0: REQUIREMENTS INVENTORY (PH-000, abbreviation: RI)
  Purpose: Extract every distinct idea, constraint, assumption from raw
  requirements into a flat enumerated inventory.
  Input: the user's requirements document(s) (primary)
  Artifact: YAML inventory with items having: id (RI-NNN), category
    (functional, non_functional, constraint, assumption),
    verbatim_quote, source_location, tags (ambiguity, conflict, etc.)
  Extraction focus: completeness (every idea captured), atomicity
    (compounds split), fidelity (no interpretation, ambiguity preserved)
  Judge guidance: watch for silent omissions, invented requirements,
    unsplit compounds, lost nuance, wrong categories

PHASE 1: FEATURE SPECIFICATION (PH-001, abbreviation: FS)
  Purpose: Organize inventory items into structured features with
  acceptance criteria.
  Input: requirements inventory (primary), raw requirements
    (validation-reference)
  Artifact: YAML feature list with features (FT-NNN), acceptance criteria
    (AC-NNN-NN), out_of_scope section, cross-cutting concerns (CC-NNN)
  Extraction focus: complete RI coverage, quality of acceptance criteria,
    dependency identification
  Judge guidance: vague criteria, assumption conflicts, scope creep,
    unjustified exclusions

PHASE 2: SOLUTION DESIGN (PH-002, abbreviation: SD)
  Purpose: Define system architecture — components, responsibilities,
  interactions.
  Input: feature specification (primary), requirements inventory
    (upstream-traceability)
  Artifact: YAML with components (CMP-NNN), interactions (INT-NNN),
    feature realization map (which components realize which features)
  Extraction focus: every feature has a realization path, component
    boundaries are clear, all interactions identified
  Judge guidance: orphan components, god components, missing interactions,
    implicit state sharing, assumption drift

PHASE 3: CONTRACT-FIRST INTERFACE DEFINITIONS (PH-003, abbreviation: CI)
  Purpose: Formal schemas for every component boundary.
  Input: solution design (primary), feature specification
    (validation-reference)
  Artifact: YAML with contracts (CTR-NNN), operations (OP-NNN),
    input/output schemas, error types, behavioral specs
  Extraction focus: every interaction has a contract, schemas are precise,
    error handling complete
  Judge guidance: type holes, error gaps, cross-contract inconsistency,
    missing idempotency

PHASE 4: INTELLIGENT SIMULATIONS (PH-004, abbreviation: IS)
  Purpose: LLM-powered test doubles for each contract.
  Input: interface contracts (primary), feature specification
    (validation-reference)
  Artifact: YAML simulation specifications with: simulation ID (SIM-NNN),
    contract_ref, scenario bank (happy/error/edge), LLM adjuster config,
    validation rules
  Extraction focus: every contract has a simulation, scenarios cover
    happy/error/edge, LLM adjuster is schema-constrained
  Judge guidance: validation gaps, scenario realism, LLM leakage,
    error cascade blindness

PHASE 5: INCREMENTAL IMPLEMENTATION (PH-005, abbreviation: II)
  Purpose: Implementation plan — component ordering, unit tests,
  integration tests.
  Input: interface contracts (primary), simulation specs
    (validation-reference), feature specification (validation-reference),
    solution design (validation-reference)
  Artifact: YAML implementation plan with: component build order
    (dependency-graph-derived), per-component unit test plan
    (UT-CMP-NNN), integration test plan (IT-CMP-NNN), simulation
    replacement sequence
  Extraction focus: ordering respects dependencies, tests trace to
    acceptance criteria, simulation replacement triggers re-testing
  Judge guidance: ordering violations, test sufficiency, completion
    criteria gaps

PHASE 6: VERIFICATION SWEEP (PH-006, abbreviation: VS)
  Purpose: End-to-end acceptance test specifications.
  Input: feature specification (primary), implementation plan
    (validation-reference), requirements inventory (upstream-traceability)
  Artifact: YAML verification plan with: E2E tests (E2E-AREA-NNN),
    traceability matrix (RI -> FT -> AC -> E2E), coverage summary
  Extraction focus: every AC has an E2E test, traceability chains are
    complete from RI to E2E
  Judge guidance: broken chains, superficial tests, missing negative
    tests, silent coverage gaps

FOR EACH PHASE, provide:
  - phase_id, phase_name, abbreviation
  - input_source_templates (using {project_dir} as placeholder for the
    project directory path)
  - extraction_focus (multi-line string)
  - generation_instructions (multi-line string)
  - judge_guidance (multi-line string)
  - artifact_format and artifact_schema_description
  - checklist_examples with good and bad examples (at least 2 each)
  - max_iterations (default 3), max_validation_iterations (default 3)
  - escalation_policy (default halt)

Also provide:
  - PHASES: a list of all PhaseConfig instances in execution order
  - get_phase(phase_id: str) -> PhaseConfig
  - get_phase_input_sources(phase: PhaseConfig, project_dir: Path)
      -> list[InputSource] — resolves templates to actual paths

Produce the complete Python file.
```

### 4.2 Validation Prompt

```
You are reviewing the phase definitions module for a methodology-runner.

Evaluate against these criteria:

PHASE COMPLETENESS
- Are all 7 phases defined (PH-000 through PH-006)?
- Does each phase have ALL required PhaseConfig fields populated?
- Are the phases in PHASES list in correct execution order?

INPUT/OUTPUT CHAIN
- Does each phase's input_source_templates reference the correct prior
  phase's output artifact path?
- Is Phase 0's input the user's requirements document?
- Does Phase 6 trace back to Phase 0 (requirements inventory as
  upstream-traceability)?
- Are input roles correct (primary, validation-reference,
  upstream-traceability)?

CONTENT QUALITY
- Is extraction_focus specific enough to guide a checklist extractor?
  (Not vague like "extract requirements" but concrete like "every FR-*
  identifier must map to a checklist item")
- Are generation_instructions detailed enough to produce the right
  artifact format?
- Does judge_guidance list specific things to watch for?
- Do checklist_examples include realistic good AND bad examples?

ARTIFACT FORMAT CONSISTENCY
- Does each phase's artifact_schema_description define the YAML structure
  the generator should produce?
- Are ID formats specified for each phase's elements?
- Are the ID formats consistent with what traceability expects?

TRACEABILITY
- Can you trace a hypothetical requirement through all 7 phases using
  the defined input_source_templates and artifact paths?
- At each phase transition, is the prior phase's artifact available
  as an input source?

For each criterion: pass/fail/partial with evidence.
```

## Prompt 5: Traceability Engine

### 5.1 Generation Prompt

```
Using the solution design, data models, and phase definitions from prior
prompts, implement the traceability engine module.

Produce a single Python file: methodology_runner/traceability.py

This module handles storage, validation, and querying of traceability
links across phases. Traceability links connect elements in each phase's
artifact back through checklist items to input source elements, forming
chains from Phase 6 all the way back to Phase 0.

STORAGE:

Traceability data is stored in YAML files, one per phase, in the project
directory under a traceability/ subdirectory:

    {project_dir}/traceability/phase-{N}-links.yaml

Each file contains a list of TraceabilityEntry objects (from models.py).

Functions:
    def save_phase_traceability(
        project_dir: Path,
        phase_id: str,
        mapping: TraceabilityMapping
    ) -> Path

    def load_phase_traceability(
        project_dir: Path,
        phase_id: str
    ) -> TraceabilityMapping | None

PARSING:

The generator produces traceability mappings as a YAML block within its
output, after a "# TRACEABILITY MAPPING" header. The engine must extract
this from the raw generator output.

    def extract_traceability_from_output(
        generator_output: str,
        phase_id: str
    ) -> TraceabilityMapping

VALIDATION:

These functions check the integrity of traceability data. They return
structured results suitable for reporting.

    @dataclass
    class TraceabilityValidationResult:
        passed: bool
        orphaned_elements: list[str]    # artifact elements with no upstream link
        dead_ends: list[str]            # upstream elements with no downstream
        broken_references: list[str]    # IDs that don't exist
        coverage_by_phase: dict[str, float]  # phase_id -> percentage covered
        issues: list[str]              # human-readable issue descriptions

    def validate_phase_traceability(
        project_dir: Path,
        phase_id: str,
        artifact_content: str,
        checklist: Checklist
    ) -> TraceabilityValidationResult

    def validate_cross_phase_traceability(
        project_dir: Path,
        completed_phases: list[str]
    ) -> TraceabilityValidationResult

QUERYING:

    def trace_forward(
        project_dir: Path,
        element_id: str
    ) -> dict[str, list[str]]
    # Returns {phase_id: [element_ids]} for all downstream elements

    def trace_backward(
        project_dir: Path,
        element_id: str
    ) -> dict[str, list[str]]
    # Returns {phase_id: [element_ids]} for all upstream elements

    def coverage_report(
        project_dir: Path,
        completed_phases: list[str]
    ) -> str
    # Returns a human-readable coverage report

IMPLEMENTATION NOTES:
- Use PyYAML for YAML parsing/writing (import yaml)
- Element IDs follow the convention from phase definitions:
  RI-NNN, FT-NNN, CMP-NNN, CTR-NNN, SIM-NNN, etc.
- For trace_forward and trace_backward, walk the per-phase link files
  and follow the chains
- The validate functions should catch: missing files, malformed YAML,
  ID references that don't exist in the artifact, gaps in the chain

Produce the complete Python file with all imports, docstrings, error
handling, and type hints.
```

### 5.2 Validation Prompt

```
You are reviewing the traceability engine module for a methodology-runner.

Evaluate against these criteria:

FUNCTION COMPLETENESS
- Are all functions from the specification implemented: save, load,
  extract, validate (phase and cross-phase), trace_forward,
  trace_backward, coverage_report?
- Is TraceabilityValidationResult defined with all fields?

STORAGE CORRECTNESS
- Does save write YAML to the correct path?
- Does load handle missing files gracefully (returns None, not crash)?
- Is the YAML format consistent with TraceabilityMapping.to_dict()?

PARSING ROBUSTNESS
- Does extract_traceability_from_output handle the case where the
  generator output has no TRACEABILITY MAPPING section?
- Does it handle malformed YAML in the mapping section?
- Does it correctly split the artifact content from the traceability
  section?

VALIDATION THOROUGHNESS
- Does validate_phase_traceability check for orphaned elements?
- Does it check for broken references (IDs that don't exist)?
- Does validate_cross_phase_traceability check chains across phases?
- Do validation functions return structured results, not just booleans?

QUERY CORRECTNESS
- Does trace_forward walk the chain from early phases to later phases?
- Does trace_backward walk from later phases to earlier phases?
- Do they handle elements that appear in multiple phases?
- Do they handle missing traceability files for intermediate phases?

ERROR HANDLING
- Are file I/O errors handled?
- Are YAML parse errors handled?
- Do functions fail gracefully rather than crashing the pipeline?

For each criterion: pass/fail/partial with evidence.
```

## Prompt 6: Phase Runner

### 6.1 Generation Prompt

```
Using all prior approved artifacts (solution design, data models, agent
prompts, phase definitions, traceability engine), implement the phase
runner module.

Produce a single Python file: methodology_runner/phase_runner.py

This is the core engine that executes a single phase through the full
Phase Processing Unit pattern. It is called by the pipeline orchestrator
for each phase.

THE PHASE PROCESSING UNIT EXECUTION FLOW:

    1. CHECKLIST EXTRACTION
       a. Build extractor prompt using phase config and input source paths
       b. Call Claude in a new session with the extractor system prompt
       c. Parse the YAML checklist from the response
       d. Enter checklist validation sub-loop:
          i.   Build validator prompt
          ii.  Call Claude in a new session with the validator prompt +
               the checklist
          iii. Parse the validation result
          iv.  If validation passes, proceed to step 2
          v.   If validation fails, build revision message with feedback,
               resume the extractor session, parse revised checklist,
               re-validate
          vi.  If max_validation_iterations reached, apply escalation policy
       e. Result: a validated Checklist object

    2. ARTIFACT GENERATION
       a. Build generator prompt using phase config + validated checklist
       b. Assemble input context: read all input source files and include
          their content
       c. Call Claude in a new session with the generator prompt + inputs
       d. Parse the response to separate artifact content from traceability
          mapping (using traceability.extract_traceability_from_output)
       e. Enter judgment loop:
          i.   Build judge prompt using phase config
          ii.  Call Claude in a new session with judge prompt + checklist
               + artifact
          iii. Parse the judgment result (evaluations, concerns, verdict)
          iv.  If verdict is pass, proceed to step 3
          v.   If verdict is revise, build revision message with judge
               feedback, resume the generator session, re-extract
               traceability, resume the judge session with revised
               artifact + anti-anchoring clause
          vi.  If max_iterations reached, apply escalation policy
       f. Result: approved artifact + traceability mapping + judgment

    3. PHASE OUTPUT
       a. Write the artifact to {project_dir}/phases/{phase_id}/artifact.yaml
       b. Write the checklist to {project_dir}/phases/{phase_id}/checklist.yaml
       c. Save traceability via traceability.save_phase_traceability()
       d. Write the judgment (evaluations + concerns) to
          {project_dir}/phases/{phase_id}/judgment.yaml
       e. Return a PhaseResult

KEY IMPLEMENTATION DETAILS:

Session management:
- Each agent role gets a unique session ID per phase per run:
  "{role}-{phase_id}-{run_id}" hashed through uuid5
- Extractor session is reused across validation iterations (resume)
- Generator session is reused across judgment iterations (resume)
- Validator gets a new session each validation iteration
- Judge gets its session reused across judgment iterations (resume)

Claude calls:
- Import and use ClaudeClient, ClaudeCall, ClaudeResponse from
  prompt_runner.claude_client
- Import Verdict, parse_verdict from prompt_runner.verdict
- Use the NON_INTERACTIVE_SYSTEM_PROMPT for all calls
- Append role-specific system prompt content using --append-system-prompt

Input assembly:
- For each input source in the phase config, resolve the path using
  the project directory, read the file content, and include it in the
  prompt with a clear header showing the file path and role

Error handling:
- ClaudeInvocationError: persist partial output, return escalated result
- YAML parse errors on agent outputs: retry once with a "your output was
  not valid YAML, please fix" message; if still invalid, escalate
- File not found for input sources: report which file is missing and
  escalate

Logging:
- Write all agent inputs and outputs to
  {project_dir}/phases/{phase_id}/logs/

PUBLIC INTERFACE:

    def run_phase(
        phase: PhaseConfig,
        project_dir: Path,
        run_id: str,
        client: ClaudeClient,
        model: str | None = None
    ) -> PhaseResult

Produce the complete Python file. This is the most complex module —
take care with the control flow, error handling, and session management.
```

### 6.2 Validation Prompt

```
You are reviewing the phase runner module for a methodology-runner.

Evaluate against these criteria:

CONTROL FLOW CORRECTNESS
- Trace the happy path: extract checklist -> validate (pass) -> generate
  artifact -> judge (pass) -> write outputs. Does it work?
- Trace a revision path: extract -> validate (fail) -> re-extract ->
  validate (pass) -> generate -> judge (fail) -> revise -> judge (pass).
  Does it work?
- Trace an escalation path: generate -> judge (fail) -> revise -> judge
  (fail) -> revise -> judge (fail) -> max iterations -> escalate.
  Does it work?

SESSION MANAGEMENT
- Does each role get its own session ID?
- Is the extractor session reused (resumed) across validation iterations?
- Is the generator session reused across judgment iterations?
- Are generator and judge always in separate sessions?
- Are session IDs deterministic (same inputs produce same IDs)?

AGENT PROMPT ASSEMBLY
- Are the build_*_prompt functions from agent_prompts.py used correctly?
- Is input source content read from disk and included in generator prompts?
- Is the validated checklist included in generator and judge prompts?
- Is the VERDICT instruction appended to judge prompts?
- Do revision messages include anti-anchoring for the judge?

OUTPUT PERSISTENCE
- Is the artifact written to the correct path?
- Is the checklist written?
- Is the traceability mapping saved via the traceability engine?
- Is the judgment written?
- Are logs written for every agent call?

ERROR HANDLING
- Is ClaudeInvocationError caught and partial output persisted?
- Are YAML parse errors handled with a retry?
- Are missing input files detected before calling Claude?
- Does the function return a meaningful PhaseResult on escalation?

INTERFACE COMPLIANCE
- Does run_phase match the signature from the solution design?
- Does it return a PhaseResult with all fields populated?
- Does it use ClaudeClient (not subprocess directly)?

For each criterion: pass/fail/partial with evidence.
```

## Prompt 7: Pipeline Orchestrator

### 7.1 Generation Prompt

```
Using all prior approved artifacts, implement the pipeline orchestrator
module.

Produce a single Python file: methodology_runner/orchestrator.py

This module sequences the 7 phases, manages project state, handles
escalation, and produces reports. It calls phase_runner.run_phase()
for each phase.

RESPONSIBILITIES:

1. PROJECT INITIALIZATION
   - Create the project directory structure:
       {project_dir}/
         requirements/        — copy of input requirements
         phases/
           PH-000-requirements-inventory/
           PH-001-feature-specification/
           ...
         traceability/
         state.json           — ProjectState
         summary.txt          — human-readable summary
   - Initialize ProjectState with all phases as "pending"
   - Copy the requirements document into requirements/

2. PHASE SEQUENCING
   - Run phases in order: PH-000 through PH-006
   - Before each phase, verify that all input sources exist (prior
     phases' artifacts are present)
   - After each phase, update ProjectState and write it to disk
   - After each phase, run cross-phase traceability validation using
     traceability.validate_cross_phase_traceability()

3. ESCALATION HANDLING
   - If a phase returns PhaseStatus.escalated:
     - If escalation_policy is halt: stop the pipeline, write summary
     - If escalation_policy is flag_and_continue: record the flag,
       continue to next phase (the escalated artifact is used as-is)
     - If escalation_policy is human_review: write state, print message,
       exit with special return code
   - If cross-phase traceability validation fails: log the issues but
     do not halt (traceability gaps are warnings, not blockers)

4. RESUMPTION
   - On startup, check if state.json exists in the project directory
   - If it does, load it and determine which phases are complete
   - Skip completed phases (their artifacts are already on disk)
   - Resume from the first phase with status "pending" or "running"
   - A phase with status "running" is treated as incomplete (crashed
     mid-phase) and is re-run from scratch

5. REPORTING
   - After each phase, update summary.txt with:
     - Phase name, status, iteration count, duration
   - After all phases complete (or pipeline halts), write final summary:
     - Overall status, total duration, per-phase results
     - Traceability coverage statistics
     - List of uncovered concerns from all phases
     - List of escalation events

PUBLIC INTERFACE:

    @dataclass
    class PipelineConfig:
        requirements_path: Path
        project_dir: Path
        model: str | None = None
        resume: bool = False
        phases_to_run: list[str] | None = None  # None means all
        # Per-phase overrides (if not set, use PhaseConfig defaults):
        max_iterations: int | None = None
        escalation_policy: EscalationPolicy | None = None

    @dataclass
    class PipelineResult:
        project_dir: Path
        phase_results: list[PhaseResult]
        halted_early: bool
        halt_reason: str | None
        traceability_report: str
        wall_time: str

    def run_pipeline(
        config: PipelineConfig,
        client: ClaudeClient
    ) -> PipelineResult

Also provide:

    def load_or_create_project(config: PipelineConfig) -> ProjectState
    def write_summary(project_dir: Path, result: PipelineResult) -> None

Produce the complete Python file.
```

### 7.2 Validation Prompt

```
You are reviewing the pipeline orchestrator module for a methodology-runner.

Evaluate against these criteria:

PHASE SEQUENCING
- Are all 7 phases run in order (PH-000 through PH-006)?
- Is each phase's input verified before it runs?
- Is ProjectState updated after each phase?
- Is state written to disk after each phase (crash safety)?

RESUMPTION
- If state.json exists with PH-000 passed and PH-001 passed, does the
  orchestrator skip those two phases and start at PH-002?
- If a phase has status "running" (crashed), is it re-run?
- Does resumption verify that prior artifacts still exist on disk?

ESCALATION
- Is each escalation policy (halt, flag_and_continue, human_review)
  implemented?
- Does halt stop the pipeline and write a summary?
- Does flag_and_continue record the flag and proceed?
- Does human_review exit with a special code?

TRACEABILITY INTEGRATION
- Is cross-phase traceability validation run after each phase?
- Are traceability warnings logged but not treated as blockers?
- Is a final traceability coverage report included in PipelineResult?

REPORTING
- Is summary.txt updated after each phase (not just at the end)?
- Does the final summary include per-phase iteration counts?
- Does it include uncovered concerns from all phases?
- Does it include traceability coverage statistics?

STATE MANAGEMENT
- Is ProjectState serialized to state.json correctly?
- Does load_or_create_project handle both new and existing projects?
- Is the requirements document copied into the project directory?

INTERFACE
- Does run_pipeline match the specified signature?
- Does PipelineConfig allow per-phase overrides?
- Does PipelineResult contain all specified fields?

For each criterion: pass/fail/partial with evidence.
```

## Prompt 8: CLI Entry Point

### 8.1 Generation Prompt

```
Using all prior approved artifacts, implement the CLI entry point.

Produce a single Python file: methodology_runner/cli.py

This is the command-line interface for the methodology runner. It uses
argparse (not click or typer) to keep dependencies minimal.

COMMANDS:

1. run — Execute the full methodology pipeline

   methodology-runner run <requirements-file> [options]

   Arguments:
     requirements-file    Path to the requirements document (markdown,
                          text, or any format)

   Options:
     --project-dir DIR    Project directory (default: auto-generated
                          from timestamp and requirements filename in
                          ./runs/)
     --model MODEL        Claude model to use (default: system default)
     --max-iterations N   Override max iterations for all phases
                          (default: use per-phase config)
     --resume             Resume an existing project from where it
                          left off
     --phases PHASES      Comma-separated phase IDs to run (e.g.,
                          "PH-000,PH-001,PH-002"). Default: all.
     --escalation-policy  Override escalation policy for all phases
                          (halt|flag-and-continue|human-review)
     --dry-run            Show what would be done without calling Claude

2. status — Show the status of a project

   methodology-runner status <project-dir>

   Reads state.json and prints:
   - Project directory, requirements file, started time
   - Per-phase status table (phase name, status, iterations, verdict)
   - Current phase (if pipeline is in progress or halted)
   - Halt reason (if any)

3. trace — Query traceability for a project

   methodology-runner trace <project-dir> <element-id> [--direction forward|backward]

   Prints the traceability chain for the given element. Default direction
   is forward (from requirements toward tests).

4. coverage — Show traceability coverage report

   methodology-runner coverage <project-dir>

   Prints the coverage report from traceability.coverage_report().

IMPLEMENTATION:

    def main(argv: list[str] | None = None) -> int:
        # Returns exit code: 0 success, 1 error, 2 human-review-needed

    def cmd_run(args: argparse.Namespace) -> int:
        # Build PipelineConfig from args
        # Create RealClaudeClient
        # Call orchestrator.run_pipeline()
        # Print summary
        # Return exit code

    def cmd_status(args: argparse.Namespace) -> int:
        # Load ProjectState from state.json
        # Print formatted status

    def cmd_trace(args: argparse.Namespace) -> int:
        # Call traceability.trace_forward or trace_backward
        # Print formatted chain

    def cmd_coverage(args: argparse.Namespace) -> int:
        # Call traceability.coverage_report
        # Print report

Also create:

    methodology_runner/__init__.py — empty or with version string
    methodology_runner/__main__.py — just calls cli.main()

Include the auto-generated project directory naming:
  runs/{timestamp}-{slugified-requirements-filename}/

The RealClaudeClient import should be from prompt_runner.claude_client.
If the user doesn't have prompt-runner installed, print a helpful error
message explaining how to install it or where to get claude_client.py.

Produce all three files (cli.py, __init__.py, __main__.py) separated
by clear headers in your output.
```

### 8.2 Validation Prompt

```
You are reviewing the CLI entry point for a methodology-runner.

Evaluate against these criteria:

COMMAND COMPLETENESS
- Are all 4 commands implemented (run, status, trace, coverage)?
- Does each command have the specified arguments and options?
- Are defaults correct (auto-generated project dir, all phases, etc.)?

RUN COMMAND
- Does it build PipelineConfig correctly from argparse args?
- Does it handle --resume by setting config.resume = True?
- Does it handle --phases by parsing the comma-separated list?
- Does it handle --dry-run?
- Does it create RealClaudeClient and pass it to run_pipeline?
- Does it print the summary after completion?
- Does it return the correct exit code (0, 1, or 2)?

STATUS COMMAND
- Does it load ProjectState from the project directory?
- Does it handle the case where state.json doesn't exist?
- Does it print a formatted table of phase statuses?

TRACE AND COVERAGE COMMANDS
- Does trace call the right traceability function based on --direction?
- Does coverage print the report?
- Do they handle missing traceability files gracefully?

ERROR HANDLING
- Does it catch ClaudeBinaryNotFound and print a helpful message?
- Does it handle missing requirements file?
- Does it handle invalid project directory?
- Are error messages user-friendly (not raw tracebacks)?

FILE STRUCTURE
- Is __init__.py present?
- Is __main__.py present and does it call cli.main()?
- Would "python -m methodology_runner run ..." work?

For each criterion: pass/fail/partial with evidence.
```
