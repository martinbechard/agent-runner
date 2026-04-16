# Build: AI-Driven Development Methodology Runner (v2)

This prompt-runner input file produces a methodology runner system with
the following architecture:

For each methodology phase (0 through 6):

1. Methodology runner assembles inputs (prior artifacts, phase config)
2. Methodology runner calls Claude to GENERATE a prompt-runner .md file
   that incrementally builds the phase's artifacts. Claude decides the
   decomposition — few prompts for simple phases, many for complex ones.
   Each prompt has its own verification prompt.
3. Methodology runner invokes prompt-runner on that .md file. All
   incremental work happens in a shared workspace tracked by git.
   The judge has tool access and receives a git diff.
4. When prompt-runner completes, the workspace contains the phase output.
5. Methodology runner runs cross-reference verification: traceability,
   integration with prior phases, coverage. This is a separate Claude
   call with tool access.

prompt-runner handles the generate-judge-revise loop at each increment.
The methodology runner is a thin orchestrator: phase sequencing, prompt
file generation, prompt-runner invocation, and cross-reference checks.

## Prompt 1: Solution Design

```
You are designing a Python application called "methodology-runner" that
orchestrates an AI-driven software development methodology across 7
phases (Phase 0: Requirements Inventory through Phase 6: Verification
Sweep).

ARCHITECTURE OVERVIEW

The system has two layers:

Layer 1 — methodology-runner (this system):
  Sequences phases, generates prompt-runner input files, invokes
  prompt-runner, and performs cross-reference verification.

Layer 2 — prompt-runner (existing tool, used as-is):
  Executes a .md file containing (generation, validation) prompt pairs.
  Each prompt goes through a generate-judge-revise loop with separate
  Claude sessions. The judge has tool access and receives git diffs of
  workspace changes. Approved artifacts from earlier prompts are carried
  as context to later prompts.

HOW A SINGLE PHASE EXECUTES:

  1. methodology-runner assembles the phase's inputs:
     - Prior phase artifacts (files in the workspace)
     - Phase configuration (what to produce, quality criteria, etc.)
     - The methodology's phase definition (extraction focus, generation
       instructions, judge guidance, artifact schema)

  2. methodology-runner calls Claude with these inputs and a meta-prompt:
     "Produce a prompt-runner .md file that incrementally builds this
     phase's artifacts. Decide how many prompts are needed based on
     complexity. Each prompt must have a verification prompt."

     Claude returns a .md file like:

       ## Prompt 1: Extract Requirements Checklist
       (generation prompt)
       (validation prompt)

       ## Prompt 2: Functional Requirements
       (generation prompt)
       (validation prompt)

       ## Prompt 3: Non-Functional Requirements and Constraints
       (generation prompt)
       (validation prompt)

     The number of prompts varies by phase and project complexity.

  3. methodology-runner writes the .md file to disk and invokes
     prompt-runner on it (as a subprocess or library call). prompt-runner
     executes each prompt with its generate-judge-revise loop in the
     shared workspace.

  4. When prompt-runner completes successfully, the workspace contains
     the phase's full output.

  5. methodology-runner runs cross-reference verification:
     - Traceability: does every element in this phase's output trace
       back to elements in prior phases?
     - Coverage: are all upstream elements (requirements, features, etc.)
       accounted for?
     - Consistency: do references to prior-phase elements actually exist?
     - Integration: does this phase's output integrate correctly with
       prior phases (no contradictions, no orphans, no dead ends)?

     This is a separate Claude call with tool access to inspect the
     workspace. It produces a structured pass/fail verdict with specific
     issues listed. If it fails, the methodology-runner can re-generate
     the prompt-runner file with the cross-reference issues as feedback.

WHAT YOU NEED TO DESIGN:

1. COMPONENT INVENTORY — list every Python module with its
   responsibility. The system should be small; prompt-runner does
   the heavy lifting. Expected modules:

   - models.py — dataclasses for phase config, project state,
     cross-reference results
   - phases.py — definitions for all 7 phases (inputs, outputs,
     extraction focus, generation instructions, judge guidance,
     artifact schemas, example checklist items)
   - prompt_generator.py — the module that calls Claude to produce
     a prompt-runner .md file for a given phase. Contains the
     meta-prompt template and assembles the phase context.
   - cross_reference.py — runs cross-reference verification after
     a phase completes. Calls Claude with tool access to inspect
     the workspace.
   - orchestrator.py — sequences phases, manages workspace and git,
     invokes prompt_generator then prompt-runner then cross-reference
     for each phase, handles escalation and resumption.
   - cli.py — command-line interface

2. DATA FLOW — trace how a requirements document flows through the
   system from input to final verification plan. Show the workspace
   directory structure at each stage.

3. WORKSPACE AND GIT — the shared workspace where all generators
   work. Tracked by git so the judge can see diffs. Define:
   - Initial structure
   - How the methodology-runner initializes git
   - How prompt-runner's generators write into it
   - How git commits happen (after each approved prompt? after each
     phase?)
   - How git diffs are provided to judges

4. PROMPT-RUNNER INTEGRATION — how the methodology-runner invokes
   prompt-runner. Options:
   - Subprocess: `prompt-runner run phase-N.md --project-dir ...`
   - Library: import and call run_pipeline() directly
   Design for both but recommend one. Consider: how does the
   methodology-runner know where prompt-runner wrote its artifacts?
   How does it pass the workspace path?

5. THE META-PROMPT — the template used to ask Claude to produce a
   prompt-runner .md file for a phase. This is the most critical
   piece. It must convey:
   - What the phase needs to produce (from phase config)
   - What inputs are available (files in workspace from prior phases)
   - Quality criteria (extraction focus, judge guidance)
   - The prompt-runner file format constraints (## Prompt headings,
     two code blocks per prompt, no triple backticks inside blocks)
   - That Claude should decide the decomposition (number of prompts)
     based on the complexity of what needs to be produced
   - That each generation prompt should instruct the generator to
     write files in the workspace
   - That each validation prompt should tell the judge what to verify,
     including checking the git diff for expected changes

6. CROSS-REFERENCE VERIFICATION — the prompt template and process
   for the post-phase verification call. What it checks, how it
   reports results, how failures feed back into re-generation.

7. STATE AND RESUMPTION — how project state is tracked. The system
   must support resuming from the last completed phase. Define what
   "completed" means (prompt-runner succeeded AND cross-reference
   passed).

8. INTERFACE CONTRACTS — for each module, public functions/classes
   with Python type-hinted signatures and docstrings. No
   implementations.

Format: a markdown document with the sections above. Use 4-space
indented code blocks for Python signatures (not triple-backtick fences).
Keep it concrete and implementable.
```

```
You are reviewing a solution design for a "methodology-runner" system.

Evaluate against these criteria:

ARCHITECTURE CLARITY
- Is the two-layer architecture (methodology-runner + prompt-runner)
  clearly described?
- Is the boundary between layers unambiguous — what does each layer own?
- Is there any logic that prompt-runner already handles being
  reimplemented in methodology-runner?

COMPONENT COMPLETENESS
- Is there a module for each responsibility: models, phase definitions,
  prompt generation, cross-reference verification, orchestration, CLI?
- Is the reuse of prompt-runner explicit (how it's invoked, what's
  imported vs. called as subprocess)?

DATA FLOW
- Can you trace a requirement from raw input through all 7 phases?
- At each phase, is it clear what files exist in the workspace?
- Is it clear how the prompt-runner's output becomes the next phase's
  input (it's all files in the workspace)?

WORKSPACE AND GIT
- Is git initialization defined?
- Is the commit strategy defined (when do commits happen)?
- Is it clear how judges receive git diffs?
- Is workspace isolation between phases addressed (can a phase corrupt
  prior phases' output)?

META-PROMPT QUALITY
- Is the meta-prompt template detailed enough that Claude would produce
  a valid prompt-runner .md file?
- Does it convey the prompt-runner format constraints?
- Does it instruct Claude to decide decomposition based on complexity?
- Does it tell Claude that generators should write files in workspace?
- Does it tell Claude that validation prompts should reference git diffs?

CROSS-REFERENCE VERIFICATION
- Is it clear what gets checked (traceability, coverage, consistency)?
- Is it clear how failures feed back (re-generate the prompt-runner
  file with issues as context)?
- Is this a Claude call with tool access, not just text evaluation?

STATE AND RESUMPTION
- Can the system determine which phases are complete from disk state?
- Is "complete" defined as prompt-runner pass AND cross-reference pass?
- Can it resume from a crashed state?

For each criterion: pass/fail/partial with evidence.
```

## Prompt 2: Data Models

```
Using the solution design from Prompt 1, implement the data models module.

Produce a single Python file: methodology_runner/models.py

This module defines all dataclasses and enums used across the system.
No dependencies on other methodology-runner modules. May import from
standard library only.

Required types:

ENUMS:
  - EscalationPolicy: halt, flag_and_continue, human_review
  - PhaseStatus: pending, running, prompt_runner_passed,
    cross_ref_passed, escalated, skipped
    (Note: a phase goes through running -> prompt_runner_passed ->
    cross_ref_passed. Both must pass for the phase to be complete.)
  - InputRole: primary, validation_reference, upstream_traceability

CONFIGURATION:
  - InputSourceTemplate: ref_template (str with {workspace} placeholder),
    role (InputRole), format (str), description (str)
  - PhaseConfig: phase_id, phase_name, abbreviation,
    input_source_templates (list[InputSourceTemplate]),
    extraction_focus (str), generation_instructions (str),
    judge_guidance (str), artifact_format (str),
    artifact_schema_description (str),
    checklist_examples_good (list[str]),
    checklist_examples_bad (list[str]),
    max_prompt_runner_iterations (int, default 3),
    escalation_policy (EscalationPolicy, default halt),
    expected_output_files (list[str] — paths relative to workspace
    that this phase should produce)

RUNTIME STATE:
  - CrossRefResult: passed (bool), issues (list[str]),
    traceability_gaps (list[str]), orphaned_elements (list[str]),
    coverage_summary (dict[str, float])
  - PhaseResult: phase_id (str), status (PhaseStatus),
    prompt_runner_exit_code (int or None),
    cross_ref_result (CrossRefResult or None),
    prompt_runner_file (str — path to the generated .md file),
    iteration_count (int), wall_time_seconds (float)
  - ProjectState: workspace_dir (Path), requirements_path (Path),
    phase_results (dict[str, PhaseResult]),
    started_at (str), finished_at (str or None),
    current_phase (str or None), git_initialized (bool)

SERIALIZATION:
  - Each dataclass: to_dict() -> dict and from_dict(d: dict) classmethod
  - ProjectState: save(path: Path) and load(path: Path) classmethods
    using JSON

Produce the complete Python file with all imports, docstrings, type
hints. Use frozen=True for configuration types. Ensure enum values
are valid Python (e.g. "pass_" not "pass").
```

```
You are reviewing a Python data models module for a methodology-runner.

Evaluate against these criteria:

TYPE COMPLETENESS
- All enums present: EscalationPolicy, PhaseStatus, InputRole?
- All config types: InputSourceTemplate, PhaseConfig?
- All runtime types: CrossRefResult, PhaseResult, ProjectState?
- Every field from the specification present with correct type hints?

PHASE STATUS LIFECYCLE
- Does PhaseStatus support the two-stage completion
  (prompt_runner_passed -> cross_ref_passed)?
- Can you determine from a ProjectState which phases are fully complete
  (cross_ref_passed), which partially complete (prompt_runner_passed),
  and which haven't started (pending)?

SERIALIZATION
- Does every dataclass have to_dict() and from_dict()?
- Does ProjectState have save() and load()?
- Can all types round-trip through to_dict/from_dict without loss?
- Are enums serialized as strings and deserialized back to enums?

DESIGN QUALITY
- Are configuration types frozen?
- No circular imports?
- No business logic (data only)?
- Docstrings on all classes?

For each criterion: pass/fail/partial with evidence.
```

## Prompt 3: Phase Definitions

```
Using the solution design and data models from prior prompts, implement
the phase definitions module.

Produce a single Python file: methodology_runner/phases.py

This module defines all 7 phases as PhaseConfig instances. Each phase
config provides everything the prompt generator needs to produce a
prompt-runner file, and everything the cross-reference verifier needs
to check the output.

Define these phases:

PHASE 0: REQUIREMENTS INVENTORY (PH-000, abbreviation: RI)
  Input: the user's requirements document (primary)
  Output: {workspace}/phases/PH-000/inventory.yaml
  Artifact: YAML inventory with items: id (RI-NNN), category
    (functional, non_functional, constraint, assumption),
    verbatim_quote, source_location, tags
  Extraction focus: completeness, atomicity, fidelity (no interpretation)
  Judge guidance: silent omissions, invented requirements, unsplit
    compounds, lost nuance, wrong categories
  Good checklist example: "Every paragraph in the requirements document
    that contains a shall/must/will statement has at least one
    corresponding RI-* item in the inventory"
  Bad checklist example: "Requirements are captured"

PHASE 1: FEATURE SPECIFICATION (PH-001, abbreviation: FS)
  Input: requirements inventory (primary), raw requirements
    (validation-reference)
  Output: {workspace}/phases/PH-001/features.yaml
  Artifact: YAML with features (FT-NNN), acceptance criteria
    (AC-NNN-NN), out_of_scope, cross-cutting concerns (CC-NNN)
  Extraction focus: complete RI coverage, AC quality, dependencies
  Judge guidance: vague criteria, assumption conflicts, scope creep

PHASE 2: SOLUTION DESIGN (PH-002, abbreviation: SD)
  Input: feature specification (primary), requirements inventory
    (upstream-traceability)
  Output: {workspace}/phases/PH-002/design.yaml
  Artifact: YAML with components (CMP-NNN), interactions (INT-NNN),
    feature realization map
  Extraction focus: every feature has a realization path, boundaries
    clear, all interactions identified
  Judge guidance: orphan components, god components, missing
    interactions, implicit state sharing

PHASE 3: INTERFACE CONTRACTS (PH-003, abbreviation: CI)
  Input: solution design (primary), feature specification
    (validation-reference)
  Output: {workspace}/phases/PH-003/contracts.yaml
  Artifact: YAML with contracts (CTR-NNN), operations, schemas,
    error types, behavioral specs
  Extraction focus: every interaction has a contract, schemas precise,
    error handling complete
  Judge guidance: type holes, error gaps, cross-contract inconsistency

PHASE 4: INTELLIGENT SIMULATIONS (PH-004, abbreviation: IS)
  Input: interface contracts (primary), feature specification
    (validation-reference)
  Output: {workspace}/phases/PH-004/simulations.yaml
  Artifact: YAML simulation specs: SIM-NNN, contract_ref, scenario
    bank, LLM adjuster config, validation rules
  Extraction focus: every contract has a simulation, scenarios cover
    happy/error/edge
  Judge guidance: validation gaps, scenario realism, LLM leakage

PHASE 5: IMPLEMENTATION PLAN (PH-005, abbreviation: II)
  Input: interface contracts (primary), simulation specs
    (validation-reference), feature specification (validation-reference),
    solution design (validation-reference)
  Output: {workspace}/phases/PH-005/implementation-plan.yaml
  Artifact: YAML with component build order, per-component unit test
    plan, integration test plan, simulation replacement sequence
  Extraction focus: ordering respects dependencies, tests trace to ACs,
    simulation replacement triggers re-testing
  Judge guidance: ordering violations, test sufficiency, completion gaps

PHASE 6: VERIFICATION SWEEP (PH-006, abbreviation: VS)
  Input: feature specification (primary), implementation plan
    (validation-reference), requirements inventory
    (upstream-traceability)
  Output: {workspace}/phases/PH-006/verification-plan.yaml
  Artifact: YAML with E2E tests (E2E-AREA-NNN), traceability matrix
    (RI -> FT -> AC -> E2E), coverage summary
  Extraction focus: every AC has an E2E test, chains complete from RI
    to E2E
  Judge guidance: broken chains, superficial tests, missing negative
    tests

FOR EACH PHASE provide:
  - All PhaseConfig fields fully populated
  - extraction_focus, generation_instructions, judge_guidance as
    multi-line strings with specific, actionable content
  - At least 2 good and 2 bad checklist examples
  - expected_output_files listing what the phase produces
  - input_source_templates using {workspace} placeholders

Provide module-level:
  - PHASES: list[PhaseConfig] in execution order
  - PHASE_MAP: dict[str, PhaseConfig] keyed by phase_id
  - get_phase(phase_id: str) -> PhaseConfig
  - resolve_input_sources(phase: PhaseConfig, workspace: Path)
      -> list[tuple[Path, InputRole, str]]
    (resolves templates to actual paths, returns path + role + description)

Produce the complete Python file.
```

```
You are reviewing the phase definitions module for a methodology-runner.

Evaluate against these criteria:

PHASE COMPLETENESS
- Are all 7 phases defined (PH-000 through PH-006)?
- Does each have ALL PhaseConfig fields populated?
- Are phases in PHASES list in correct order?

INPUT/OUTPUT CHAIN
- Does each phase's input_source_templates reference the correct prior
  phase's output path?
- Is Phase 0's input the user's requirements document?
- Does Phase 6 trace back to Phase 0?
- Are input roles correct?

CONTENT QUALITY
- Is extraction_focus concrete enough to guide a checklist extractor?
  (Not "extract requirements" but "every shall/must statement has a
  corresponding RI-* item")
- Are generation_instructions detailed enough for artifact format?
- Does judge_guidance list specific things to watch for?
- Are checklist examples realistic good AND bad?

OUTPUT FILES
- Does each phase's expected_output_files list the right paths?
- Are paths relative to workspace?
- Would the cross-reference verifier be able to find them?

TEMPLATE RESOLUTION
- Does resolve_input_sources correctly replace {workspace}?
- Does it handle missing files gracefully (return path even if file
  doesn't exist yet, letting the caller decide)?

For each criterion: pass/fail/partial with evidence.
```

## Prompt 4: Prompt Generator

```
Using the solution design, data models, and phase definitions from prior
prompts, implement the prompt generator module.

Produce a single Python file: methodology_runner/prompt_generator.py

This is the core module. It calls Claude to produce a prompt-runner .md
file for a given phase. The returned .md file contains however many
incremental prompts Claude decides are needed, each with a verification
prompt. When executed by prompt-runner, these prompts incrementally
build the phase's artifacts in the shared workspace.

PUBLIC INTERFACE:

    def generate_phase_prompts(
        phase: PhaseConfig,
        workspace: Path,
        model: str | None = None,
    ) -> Path:
        """Call Claude to produce a prompt-runner .md file for this phase.

        Reads the input source files from the workspace, assembles them
        with the phase configuration into a meta-prompt, calls Claude,
        writes the resulting .md file to:
            {workspace}/prompt-runner-files/{phase.phase_id}.md

        Returns the path to the written .md file.
        """

IMPLEMENTATION:

1. ASSEMBLE CONTEXT
   - Resolve the phase's input source templates to actual file paths
   - Read each input file's content
   - Assemble into a context block with headers showing path and role:

       # Input: {path} (role: {role})
       {file content}

2. BUILD THE META-PROMPT
   The meta-prompt asks Claude to produce a prompt-runner .md file. It
   must convey:

   a. The phase's purpose (from phase_name and phase_id)

   b. What the phase must produce (from generation_instructions,
      artifact_format, artifact_schema_description, expected_output_files)

   c. The input context (assembled above)

   d. Quality criteria for the generation prompts:
      - extraction_focus (for checklist-related prompts)
      - judge_guidance (for verification prompts)
      - checklist_examples_good and checklist_examples_bad

   e. PROMPT-RUNNER FORMAT RULES — critical constraints:
      - Each prompt section starts with ## Prompt N: Title
      - Each section has exactly two code blocks (triple backtick fenced)
      - First code block: generation prompt
      - Second code block: validation prompt
      - No triple backticks inside code blocks (use 4-space indent for
        code examples inside prompts)
      - Generation prompts should instruct the generator to write files
        in the current working directory (the workspace)
      - Validation prompts should tell the judge to:
        * Check the git diff for expected file changes
        * Use tool access to read and inspect created files
        * Run any applicable mechanical checks (yaml parsing, syntax
          validation, schema conformance)
        * Verify the specific quality criteria for this increment

   f. DECOMPOSITION GUIDANCE:
      - Claude should decide how many prompts are needed based on
        the complexity of the phase's output
      - A simple phase (e.g., requirements inventory for a small
        project) might need 2-3 prompts
      - A complex phase (e.g., solution design for a large system)
        might need 5-10 prompts
      - Each prompt should produce a coherent increment — not too
        small (trivial) or too large (likely to fail verification)
      - The first prompt should typically handle checklist/criteria
        extraction from the inputs
      - Subsequent prompts should incrementally build the artifact,
        with each verification checking the increment against the
        relevant criteria
      - The final prompt should consolidate and verify completeness

   g. WORKSPACE CONVENTIONS:
      - Phase output goes in {workspace}/phases/{phase_id}/
      - Generators have full tool access (Read, Write, Bash)
      - Files are tracked by git; judges see the diff

3. CALL CLAUDE
   - Use the claude CLI via subprocess (same pattern as prompt-runner's
     RealClaudeClient, or import and use it directly)
   - The meta-prompt goes as the user message
   - Use a system prompt that says: "You are producing a prompt-runner
     input file. Your entire response must be a valid prompt-runner
     markdown file and nothing else. Do not include any preamble,
     explanation, or commentary outside the file content."

4. EXTRACT AND WRITE THE .MD FILE
   - Parse Claude's response to extract the .md content
   - Validate basic structure: at least one ## Prompt heading, each
     has two code blocks
   - Write to {workspace}/prompt-runner-files/{phase.phase_id}.md
   - Return the path

ERROR HANDLING:
   - If Claude fails to produce a valid prompt-runner file (no ## Prompt
     headings, or wrong number of code blocks), retry once with
     feedback about what was wrong
   - If input source files don't exist, raise a clear error listing
     which files are missing and which phase was supposed to produce them
   - If the meta-prompt is too large (input files are huge), summarize
     the inputs rather than including full content

Also provide:

    META_PROMPT_TEMPLATE: str — the template string with placeholders

    def _assemble_input_context(
        phase: PhaseConfig, workspace: Path
    ) -> str

    def _validate_prompt_runner_file(content: str) -> list[str]
        # Returns list of issues, empty if valid

Produce the complete Python file. The meta-prompt template is the most
important part — spend the most effort on it.
```

```
You are reviewing the prompt generator module for a methodology-runner.

Evaluate against these criteria:

META-PROMPT QUALITY
- Does the meta-prompt template convey ALL of: phase purpose, what to
  produce, quality criteria, format rules, decomposition guidance,
  workspace conventions?
- Would Claude, given this meta-prompt and real input files, produce a
  valid prompt-runner .md file?
- Does it tell Claude the prompt-runner format constraints (## Prompt
  headings, exactly two code blocks, no inner triple backticks)?
- Does it tell Claude to instruct generators to write files?
- Does it tell Claude to instruct judges to use tool access and git diff?
- Does it give Claude freedom to choose the number of prompts?

INPUT ASSEMBLY
- Does _assemble_input_context read real files from disk?
- Does it handle missing files with a clear error?
- Does it include the file path and role in the assembled context?
- Does it handle large files (truncation or summarization)?

VALIDATION
- Does _validate_prompt_runner_file check for ## Prompt headings?
- Does it check for exactly two code blocks per prompt?
- Does it return specific issues (not just true/false)?

CLAUDE INVOCATION
- Is Claude called correctly (subprocess or library)?
- Is the system prompt appropriate (produce file, no commentary)?
- Is there retry logic for invalid output?

ERROR HANDLING
- Missing input files: clear error message?
- Claude failure: handled gracefully?
- Invalid .md output: retry with feedback?

For each criterion: pass/fail/partial with evidence.
```

## Prompt 5: Cross-Reference Verifier

```
Using the solution design, data models, and phase definitions from prior
prompts, implement the cross-reference verification module.

Produce a single Python file: methodology_runner/cross_reference.py

This module runs after prompt-runner has completed a phase's incremental
prompts. It verifies that the phase's output integrates correctly with
all prior phases' outputs. Unlike the per-increment judges (which check
local quality), this module checks global consistency.

PUBLIC INTERFACE:

    def verify_phase_cross_references(
        phase: PhaseConfig,
        workspace: Path,
        completed_phases: list[str],
        model: str | None = None,
    ) -> CrossRefResult:
        """Run cross-reference verification for a completed phase.

        Calls Claude with tool access to inspect the workspace. Claude
        checks traceability, coverage, consistency, and integration
        with prior phases.

        Returns a CrossRefResult with pass/fail and specific issues.
        """

    def verify_end_to_end(
        workspace: Path,
        model: str | None = None,
    ) -> CrossRefResult:
        """Run final end-to-end verification across all phases.

        Called after all 7 phases complete. Traces every requirement
        from Phase 0 through to Phase 6 and reports any broken chains
        or coverage gaps.
        """

WHAT CROSS-REFERENCE VERIFICATION CHECKS:

1. TRACEABILITY — for each element in this phase's output, can it be
   traced back to an element in a prior phase? Specifically:
   - Phase 1 features -> Phase 0 inventory items
   - Phase 2 components -> Phase 1 features
   - Phase 3 contracts -> Phase 2 interactions
   - Phase 4 simulations -> Phase 3 contracts
   - Phase 5 implementation items -> Phase 3 contracts + Phase 1 ACs
   - Phase 6 E2E tests -> Phase 1 ACs -> Phase 0 inventory items

2. COVERAGE — are all upstream elements accounted for?
   - Every RI-* item should eventually reach an E2E test (or be
     explicitly marked out of scope)
   - Every feature should have at least one component realizing it
   - Every interaction should have a contract
   - Every contract should have a simulation

3. CONSISTENCY — do cross-references actually resolve?
   - If a feature says source_inventory_refs: [RI-003], does RI-003
     exist in the inventory?
   - If a component says it realizes FT-007, does FT-007 exist?
   - Are there ID format mismatches or typos?

4. INTEGRATION — does this phase's output conflict with prior phases?
   - Does the feature spec introduce assumptions that contradict the
     requirements inventory?
   - Does the design introduce components for features that were
     marked out of scope?
   - Do contracts reference interactions that don't exist in the design?

IMPLEMENTATION:

1. Build a prompt that tells Claude:
   - Which phase just completed
   - What to check (the four categories above, specialized for this phase)
   - That it has tool access — it should Read files, parse YAML, and
     programmatically verify cross-references (not just skim and guess)
   - To produce a structured YAML result matching CrossRefResult

2. Call Claude with tool access, cwd set to the workspace

3. Parse the response into a CrossRefResult

4. For verify_end_to_end: build a prompt that asks Claude to trace
   every RI-* item through the full chain to E2E tests, reporting
   broken chains and coverage percentage

CROSS-REFERENCE PROMPT TEMPLATES:

Provide per-phase templates that specify exactly what to check for
that phase (which IDs to trace, which files to read, what constitutes
a broken reference). These should be concrete, not generic.

Also provide:

    CROSS_REF_SYSTEM_PROMPT: str — system prompt for cross-ref calls
    PHASE_CROSS_REF_CHECKS: dict[str, str] — per-phase check templates
    END_TO_END_PROMPT_TEMPLATE: str — template for final verification

    def _parse_cross_ref_result(claude_output: str) -> CrossRefResult

Produce the complete Python file.
```

```
You are reviewing the cross-reference verification module for a
methodology-runner.

Evaluate against these criteria:

CHECK COMPLETENESS
- Does it check all four categories: traceability, coverage,
  consistency, integration?
- Are checks phase-specific (not generic "check everything")?
- For each phase (1-6), is it clear which upstream elements are
  traced and which files are inspected?

TOOL ACCESS USAGE
- Does the Claude call have tool access enabled?
- Does the prompt instruct Claude to programmatically verify
  cross-references (parse YAML, check IDs) rather than just
  reading and guessing?
- Is cwd set to the workspace so Claude can access all files?

END-TO-END VERIFICATION
- Does verify_end_to_end trace RI-* items through the full chain?
- Does it produce a coverage percentage?
- Does it identify specific broken chains?

RESULT STRUCTURE
- Does CrossRefResult contain all fields: passed, issues,
  traceability_gaps, orphaned_elements, coverage_summary?
- Is the parse function robust to malformed Claude output?
- Do issues contain specific, actionable information (not just
  "traceability is incomplete")?

PHASE-SPECIFIC TEMPLATES
- Is there a template for each phase (1 through 6)?
- Does each template name the specific IDs and files to check?
- Does Phase 0 have a template (even if minimal — it has no
  upstream to cross-reference)?

FEEDBACK LOOP
- Is the CrossRefResult structured so that the orchestrator can
  pass its issues back to the prompt generator for re-generation?
- Can a human reading the result understand what went wrong and
  where?

For each criterion: pass/fail/partial with evidence.
```

## Prompt 6: Pipeline Orchestrator

```
Using all prior approved artifacts, implement the pipeline orchestrator.

Produce a single Python file: methodology_runner/orchestrator.py

This module sequences the 7 phases, manages the workspace and git,
invokes the prompt generator and prompt-runner for each phase, runs
cross-reference verification, and handles escalation and resumption.

PUBLIC INTERFACE:

    @dataclass
    class PipelineConfig:
        requirements_path: Path
        workspace_dir: Path | None = None  # None = auto-generate
        model: str | None = None
        resume: bool = False
        phases_to_run: list[str] | None = None  # None = all
        max_prompt_runner_iterations: int | None = None  # override
        escalation_policy: EscalationPolicy | None = None  # override
        max_cross_ref_retries: int = 2  # how many times to re-generate
                                         # if cross-ref fails

    @dataclass
    class PipelineResult:
        workspace_dir: Path
        phase_results: list[PhaseResult]
        halted_early: bool
        halt_reason: str | None
        end_to_end_result: CrossRefResult | None
        wall_time_seconds: float

    def run_pipeline(config: PipelineConfig) -> PipelineResult

EXECUTION FLOW FOR EACH PHASE:

    1. Check if phase is already complete (resume support)
    2. Update ProjectState: current_phase = phase_id, status = running
    3. Call prompt_generator.generate_phase_prompts() to produce the
       prompt-runner .md file
    4. Invoke prompt-runner on the .md file:
       - subprocess: prompt-runner run {md_file} --project-dir {workspace}
       - or library: parse the file, call run_pipeline with workspace
       - Pass the model, max-iterations, and workspace as arguments
    5. Check prompt-runner exit code. If failed:
       - If escalation policy is halt: stop
       - If flag_and_continue: record, proceed
       - If human_review: exit with code 2
    6. Update ProjectState: status = prompt_runner_passed
    7. Call cross_reference.verify_phase_cross_references()
    8. If cross-ref fails:
       - Re-generate the prompt-runner file with cross-ref issues as
         additional context (up to max_cross_ref_retries times)
       - Re-run prompt-runner
       - Re-check cross-references
       - If still failing after retries, apply escalation policy
    9. Update ProjectState: status = cross_ref_passed
    10. Git commit: "Phase {phase_id} completed"

WORKSPACE INITIALIZATION:

    def initialize_workspace(config: PipelineConfig) -> Path:
        """Create workspace, copy requirements, init git."""

    Structure:
        {workspace}/
            requirements/          # copy of input requirements
            phases/
                PH-000/            # each phase gets a subdirectory
                PH-001/
                ...
            prompt-runner-files/   # generated .md files
            prompt-runner-runs/    # prompt-runner's output directories
            state.json             # ProjectState
            summary.txt            # human-readable summary

    Git:
        - Initialize a git repo in the workspace
        - Initial commit with requirements and empty structure
        - Commit after each phase completes (step 10 above)
        - The git log becomes an audit trail of the entire run

RESUMPTION:

    def resume_pipeline(config: PipelineConfig) -> PipelineResult:
        """Load state.json, skip completed phases, continue."""

    - Load ProjectState from state.json
    - For each phase in order:
      - If status is cross_ref_passed: skip
      - If status is prompt_runner_passed: re-run cross-ref only
      - If status is running or pending: run from the beginning
    - Verify prior phase artifacts still exist before starting a phase

REPORTING:

    def write_summary(workspace: Path, result: PipelineResult) -> None

    Summary includes:
    - Per-phase: status, prompt count (from .md file), iteration count,
      cross-ref result, wall time
    - Overall: total phases completed, total wall time, end-to-end
      traceability coverage
    - Any escalation events or uncovered concerns

PROMPT-RUNNER INVOCATION:

To invoke prompt-runner, use subprocess:

    import subprocess
    result = subprocess.run(
        ["prompt-runner", "run", str(md_file),
         "--project-dir", str(workspace)],
        capture_output=True, text=True
    )

If prompt-runner is not on PATH, fall back to:

    result = subprocess.run(
        [sys.executable, "-m", "prompt_runner", "run", str(md_file),
         "--project-dir", str(workspace)],
        capture_output=True, text=True
    )

The workspace is both prompt-runner's working directory and the
methodology-runner's workspace. prompt-runner's generators write
files there; methodology-runner's cross-reference checks read them.

GIT OPERATIONS:

Use subprocess calls to git:
    def _git(workspace: Path, *args: str) -> str
    def _git_init(workspace: Path) -> None
    def _git_commit(workspace: Path, message: str) -> None
    def _git_diff(workspace: Path) -> str

Produce the complete Python file.
```

```
You are reviewing the pipeline orchestrator module for a
methodology-runner.

Evaluate against these criteria:

PHASE SEQUENCING
- Are all 7 phases run in order?
- Is each phase's input verified before running?
- Is ProjectState updated at each stage (running, prompt_runner_passed,
  cross_ref_passed)?
- Is state written to disk after each status change?

PROMPT-RUNNER INTEGRATION
- Is prompt-runner invoked correctly (subprocess with right args)?
- Is the workspace passed to prompt-runner?
- Is the exit code checked?
- Is there a fallback if prompt-runner is not on PATH?

CROSS-REFERENCE RETRY LOOP
- If cross-ref fails, does it re-generate the prompt-runner file
  with the issues?
- Is the retry bounded by max_cross_ref_retries?
- After retries exhausted, does it apply escalation policy?

WORKSPACE AND GIT
- Is workspace initialized with correct structure?
- Is git initialized?
- Are commits made at the right points?
- Are prior phase artifacts preserved (a phase can't corrupt them)?

RESUMPTION
- Does it load ProjectState correctly?
- Does it skip cross_ref_passed phases?
- Does it re-run cross-ref for prompt_runner_passed phases?
- Does it re-run entirely for running/pending phases?
- Does it verify prior artifacts exist?

ESCALATION
- Are all three policies implemented (halt, flag_and_continue,
  human_review)?
- Do they apply both to prompt-runner failure and cross-ref failure?

REPORTING
- Is summary updated after each phase?
- Does final summary include all specified information?

For each criterion: pass/fail/partial with evidence.
```

## Prompt 7: CLI Entry Point

```
Using all prior approved artifacts, implement the CLI entry point.

Produce three Python files:
- methodology_runner/cli.py
- methodology_runner/__init__.py
- methodology_runner/__main__.py

Separate each file with a clear header:
    # === FILE: methodology_runner/cli.py ===
    # === FILE: methodology_runner/__init__.py ===
    # === FILE: methodology_runner/__main__.py ===

CLI uses argparse. Minimal dependencies.

COMMANDS:

1. run — Execute the full methodology pipeline

   methodology-runner run <requirements-file> [options]

   Options:
     --workspace DIR         Workspace directory (default: auto from
                             timestamp + requirements filename in ./runs/)
     --model MODEL           Claude model to use
     --max-iterations N      Override max prompt-runner iterations
     --resume                Resume an existing project
     --phases PHASES         Comma-separated phase IDs to run
     --escalation-policy P   Override: halt|flag-and-continue|human-review
     --max-cross-ref-retries N  Max retries for cross-ref failures

2. status — Show project status

   methodology-runner status <workspace-dir>

   Reads state.json and prints per-phase status table.

3. resume — Resume a halted or interrupted project

   methodology-runner resume <workspace-dir> [options]

   Same options as run, but workspace-dir is required and requirements
   are already in the workspace.

IMPLEMENTATION:

    def main(argv: list[str] | None = None) -> int:
        # Returns: 0 success, 1 error, 2 human-review-needed

    def cmd_run(args) -> int:
        # Build PipelineConfig, call run_pipeline, print summary

    def cmd_status(args) -> int:
        # Load ProjectState, print formatted table

    def cmd_resume(args) -> int:
        # Build PipelineConfig with resume=True, call run_pipeline

Auto-generated workspace name:
    runs/{YYYY-MM-DDTHH-MM-SS}-{slugified-requirements-name}/

Error handling:
    - requirements file not found: clear message
    - workspace not found (for status/resume): clear message
    - prompt-runner not installed: helpful message
    - Claude CLI not found: helpful message

__init__.py: version string only
__main__.py: calls cli.main()

Produce all three files.
```

```
You are reviewing the CLI entry point for a methodology-runner.

Evaluate against these criteria:

COMMAND COMPLETENESS
- Are all 3 commands implemented (run, status, resume)?
- Does each have the specified arguments and options?
- Are defaults correct?

RUN COMMAND
- Does it build PipelineConfig correctly from args?
- Does it handle all options?
- Does it print a summary after completion?
- Correct exit codes (0, 1, 2)?

STATUS COMMAND
- Does it load and display ProjectState?
- Does it handle missing state.json?
- Is the output formatted as a readable table?

RESUME COMMAND
- Does it set resume=True in PipelineConfig?
- Does it use the workspace's existing requirements?
- Does it accept the same override options as run?

ERROR HANDLING
- Missing requirements file?
- Missing workspace (for status/resume)?
- prompt-runner not on PATH?
- Claude CLI not found?
- User-friendly messages (no raw tracebacks)?

FILE STRUCTURE
- __init__.py present?
- __main__.py calls main()?
- "python -m methodology_runner run ..." would work?

For each criterion: pass/fail/partial with evidence.
```
