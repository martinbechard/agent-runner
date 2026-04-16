# CD-002 -- Methodology Runner

*Component design for a Python CLI tool that orchestrates an AI-driven software development methodology across seven phases, using prompt-runner (CD-001) as its execution engine.*

## 1. Purpose

The methodology-runner is a thin orchestration layer that sequences seven methodology phases (PH-000 through PH-006), generates prompt-runner input files for each phase, invokes prompt-runner to execute them, and runs cross-reference verification after each phase completes.

The system has two layers:

- **Layer 1 (this system):** phase sequencing, prompt-file generation, cross-reference verification, state management, and resumption.
- **Layer 2 (prompt-runner, CD-001):** executes generation/validation prompt pairs with a generate-judge-revise loop. Used as-is.

The methodology-runner is *content-aware* in one sense -- it carries the phase definitions from M-002 -- but *generation-agnostic*: it never writes methodology artifacts itself. It asks Claude to produce a prompt-runner input file, then delegates all artifact generation and judgment to prompt-runner.

## 2. Scope

### In scope

- Reading the methodology corpus (M-001 through M-006) as structured configuration.
- Sequencing phases according to the dependency DAG in M-002/M-006.
- Calling Claude to produce a prompt-runner .md file for each phase (the meta-prompt).
- Invoking prompt-runner on the generated .md file.
- Running cross-reference verification after each phase completes.
- Feeding cross-reference failures back into prompt-file re-generation.
- Tracking project state and supporting resumption from the last completed phase.
- A CLI interface for running, resuming, and inspecting projects.

### Out of scope

- Modifying prompt-runner (used as a black box).
- Parallel phase execution (the DAG is mostly linear; sequential is sufficient for v1).
- A web UI, API, or any interface beyond the CLI.
- Human-in-the-loop review workflows (v1 halts on escalation).

## 3. Component Inventory

Source code lives under *src/cli/methodology_runner/*. Tests mirror under *tests/cli/methodology_runner/*.

    src/cli/methodology_runner/
      __init__.py
      __main__.py          # python -m methodology_runner entry point
      models.py            # dataclasses for phase config, project state, cross-ref results
      phases.py            # definitions for all 7 phases
      prompt_generator.py  # calls Claude to produce a prompt-runner .md file
      cross_reference.py   # post-phase verification via Claude with tool access
      orchestrator.py      # sequences phases, manages workspace and git
      cli.py               # argparse CLI interface

    tests/cli/methodology_runner/
      __init__.py
      test_models.py
      test_phases.py
      test_prompt_generator.py
      test_cross_reference.py
      test_orchestrator.py
      test_cli.py
      fixtures/
        sample-project-state.yaml
        sample-cross-ref-result.yaml

### Module responsibilities

**models.py** -- Dataclasses that carry data between modules. No business logic. Contains: PhaseConfig (what a phase needs to do), ProjectState (where the project is in the pipeline), CrossReferenceResult (structured pass/fail from verification), PhaseResult (outcome of one phase execution), WorkspaceLayout (paths within the workspace).

**phases.py** -- The Python representation of the seven phases from M-002. Each phase is a PhaseConfig instance containing: phase ID, phase name, input artifact paths, output artifact path, extraction focus text, generation instructions text, judge guidance text, artifact schema description, example checklist items, and the list of predecessor phase IDs. This module is a data registry -- it builds and returns a list of PhaseConfig objects, one per phase.

**prompt_generator.py** -- Takes a PhaseConfig and the current workspace state, assembles the meta-prompt (Section 5), stages any phase-local deterministic validation helpers, calls Claude, and returns the generated prompt-runner .md file content. This is the most critical module: it bridges the methodology corpus with prompt-runner's input format.

**cross_reference.py** -- Takes a PhaseConfig and the workspace path, assembles a verification prompt (Section 6), calls Claude with tool access to inspect workspace files, and returns a CrossReferenceResult with pass/fail verdict and specific issues.

**orchestrator.py** -- The main control loop. For each phase in dependency order: checks preconditions, calls prompt_generator, writes the .md file, invokes prompt-runner (subprocess or library), runs cross_reference, handles failures (re-generation with feedback, escalation), updates project state, and commits to git. Handles resumption by reading ProjectState and skipping completed phases.

**cli.py / __main__.py** -- Command-line interface with subcommands: *run* (execute all phases from the beginning or resume point), *status* (show project state), and *reset* (clear state for a specific phase to force re-execution).

## 4. Data Flow

This section traces a requirements document through the full pipeline.

### 4.1 Initial state

The user provides a raw requirements document and invokes the methodology-runner.

    project-workspace/
      docs/requirements/raw-requirements.md    # user-provided input
      .git/                                     # initialized by methodology-runner

### 4.2 Phase 0: Requirements Inventory

1. **orchestrator** reads ProjectState, sees Phase 0 is pending.
2. **orchestrator** calls **prompt_generator** with Phase 0's PhaseConfig.
3. **prompt_generator** assembles the meta-prompt:
   - Phase 0 config (extraction focus, generation instructions, artifact schema)
   - Available workspace files: raw-requirements.md
   - Prompt-runner format constraints
4. **prompt_generator** calls Claude, receives a .md file with N prompt pairs.
5. **orchestrator** writes the .md file to the runs directory.
6. **orchestrator** invokes prompt-runner on the .md file. prompt-runner's generators write into the workspace; its judges verify via git diffs.
7. prompt-runner completes. Workspace now contains:

        project-workspace/
          docs/requirements/raw-requirements.md
          docs/requirements/requirements-inventory.yaml
          .git/

8. **orchestrator** calls **cross_reference** for Phase 0.
9. **cross_reference** calls Claude with tool access. Claude reads the inventory and raw requirements, verifies completeness and fidelity, returns a CrossReferenceResult.
10. If cross-reference passes: **orchestrator** updates ProjectState to mark Phase 0 completed, commits to git.
11. If cross-reference fails: **orchestrator** feeds the failure issues back to **prompt_generator** as additional context, re-generates the .md file, and re-runs prompt-runner (up to a configurable retry limit).

### 4.3 Phase 1 through Phase 5

Each phase follows the same pattern as Phase 0. The workspace accumulates:

    After Phase 1 (Feature Specification):
      docs/features/feature-specification.yaml

    After Phase 2 (Solution Design):
      docs/design/solution-design.yaml

    After Phase 3 (Contract-First Interfaces):
      docs/design/interface-contracts.yaml

    After Phase 4 (Intelligent Simulations):
      docs/simulations/simulation-definitions.yaml

    After Phase 5 (Incremental Implementation):
      docs/implementation/implementation-plan.yaml

### 4.4 Phase 6: Verification Sweep

Phase 6 reads artifacts from Phases 0, 1, 2, and 5. It produces:

    docs/verification/verification-report.yaml

The cross-reference check for Phase 6 is especially thorough: it verifies end-to-end traceability from raw requirements through inventory, features, design, contracts, simulations, implementation plan, and the verification report itself.

### 4.5 Final workspace state

    project-workspace/
      docs/requirements/
        raw-requirements.md                      # original input
        requirements-inventory.yaml              # Phase 0 output
      docs/features/
        feature-specification.yaml               # Phase 1 output
      docs/design/
        solution-design.yaml                     # Phase 2 output
        interface-contracts.yaml                 # Phase 3 output
      docs/simulations/
        simulation-definitions.yaml              # Phase 4 output
      docs/implementation/
        implementation-plan.yaml                 # Phase 5 output
      docs/verification/
        verification-report.yaml                 # Phase 6 output
      .methodology-runner/
        project-state.yaml                       # state tracking
        runs/
          phase-0/
            prompt-file.md                       # generated prompt-runner input
            cross-ref-result.yaml                # verification result
          phase-1/
            ...
          ...
      .git/

## 5. Workspace and Git

### 5.1 Initialization

When the methodology-runner starts a new project, it:

1. Verifies the workspace directory exists and contains at least one file in docs/requirements/ (the raw requirements).
2. Initializes git if not already initialized (git init).
3. Creates the .methodology-runner/ directory for state and run artifacts.
4. Makes an initial commit with the raw requirements and .methodology-runner skeleton.

### 5.2 Git commit strategy

Commits happen at two granularities:

- **prompt-runner level:** prompt-runner's generators write files into the workspace. The methodology-runner does NOT commit after each prompt-runner prompt -- prompt-runner's judges already see diffs via the Claude CLI's built-in tool access. The workspace is a live working tree during prompt-runner execution.
- **phase level:** after prompt-runner completes AND cross-reference verification passes, the orchestrator stages all new/modified files and creates a commit:

      git add -A
      git commit -m "Phase N: {phase_name} -- completed"

  This means each phase produces exactly one commit (or zero, if the phase fails and is not re-attempted). The commit message includes the phase ID and name for easy navigation.

### 5.3 How generators write into the workspace

prompt-runner is invoked with --project-dir pointing to the workspace root. The workspace_dir parameter on prompt-runner's run_pipeline sets the cwd for all Claude subprocess calls. Generators write files using the Write tool relative to that cwd. This is identical to how prompt-runner already works (see CD-001 Section 9).

### 5.4 How judges see diffs

The Claude CLI provides tool access to the judges. Judges can run git diff, Read files, and use Bash to inspect the workspace. The methodology-runner does not need to manage diffs explicitly -- prompt-runner and the Claude CLI handle this.

### 5.5 Cross-reference verification and git

The cross-reference verification call (Section 6) runs AFTER prompt-runner completes but BEFORE the phase commit. This means the cross-reference agent sees uncommitted changes in the workspace. If cross-reference fails and re-generation is needed, the orchestrator can discard the failed attempt's files before re-running prompt-runner.

## 6. Prompt-Runner Integration

### 6.1 Invocation method

The methodology-runner invokes prompt-runner as a **library call** (recommended) with subprocess as a fallback.

**Library call (recommended):**

    from prompt_runner.runner import run_pipeline, RunConfig
    from prompt_runner.parser import parse_file
    from prompt_runner.claude_client import RealClaudeClient

    pairs = parse_file(prompt_file_path)
    config = RunConfig(max_iterations=3, model=model)
    client = RealClaudeClient()
    result = run_pipeline(
        pairs=pairs,
        run_dir=run_dir,
        config=config,
        claude_client=client,
        source_file=prompt_file_path,
        workspace_dir=workspace_dir,
    )

Library call is preferred because:
- No subprocess overhead for the outer invocation.
- Direct access to PipelineResult with per-prompt details (PromptResult, IterationResult, final verdicts).
- No need to parse stdout/stderr to determine success.
- The ClaudeClient protocol allows injection of test doubles.

**Subprocess fallback:**

    python -m prompt_runner run {prompt_file} \
      --output-dir {run_dir} \
      --max-iterations 3 \
      --model {model}

The subprocess approach is simpler operationally but loses structured result data. The exit code conveys only: 0 (success), 1 (escalation halt), 2 (parse error), 3 (runtime error).

### 6.2 How the methodology-runner knows what prompt-runner produced

After run_pipeline returns, the methodology-runner knows the phase's expected output path from PhaseConfig.output_artifact_path. It verifies the file exists and is non-empty. It does not need to parse prompt-runner's output to discover what was written -- the phase definition declares the expected artifact path.

Additionally, each PromptResult in the PipelineResult carries a created_files list (relative paths of files added/modified by that prompt's generator). The methodology-runner can use this for detailed logging but does not need it for correctness.

### 6.3 Passing the workspace path

The workspace_dir parameter on run_pipeline sets the working directory for all Claude subprocess calls. The methodology-runner passes its own workspace root as this parameter.

### 6.4 Run directory layout

Each phase execution creates a run directory under .methodology-runner/runs/:

    .methodology-runner/runs/phase-0/
      prompt-file.md           # the generated prompt-runner input
      prompt-runner-output/    # prompt-runner's own run directory
        manifest.json
        logs/
          prompt-01-.../
          prompt-02-.../
        summary.txt
      cross-ref-result.yaml    # cross-reference verification result

## 7. The Meta-Prompt

The meta-prompt is the template used to ask Claude to produce a prompt-runner .md file for a given phase. It is the most critical piece of the system: it bridges the structured methodology corpus with prompt-runner's input format.

### 7.1 Template structure

The meta-prompt is assembled by prompt_generator.py from these components:

    SECTION 1: Role and task framing
    SECTION 2: Phase configuration (from PhaseConfig)
    SECTION 3: Available workspace files (ls of relevant directories)
    SECTION 4: Prior phase artifacts summary
    SECTION 5: Prompt-runner format constraints
    SECTION 6: Decomposition guidance
    SECTION 7: Cross-reference feedback (only on re-generation after failure)

### 7.2 Template content

    SECTION 1 -- ROLE AND TASK

    You are a prompt architect for an AI-driven software development
    pipeline. Your job is to produce a prompt-runner input file (.md)
    that, when executed by prompt-runner, will produce the artifacts
    for one phase of the methodology.

    prompt-runner executes each prompt pair sequentially. For each pair,
    a generator Claude session produces an artifact and a separate judge
    Claude session evaluates it. The judge can request revisions up to
    3 times. Prior approved artifacts are carried as context to later
    prompts.

    You must produce a complete .md file. Do not produce the artifacts
    themselves -- produce the prompts that will instruct another Claude
    to produce them.

    ---

    SECTION 2 -- PHASE CONFIGURATION

    Phase: {phase_id} -- {phase_name}

    Purpose:
    {phase_purpose}

    Input artifacts (files that exist in the workspace and can be read
    by generators):
    {for each input artifact:}
      - {path} (role: {role})
        {description}

    Output artifact:
      - Path: {output_artifact_path}
      - Format: {output_format}

    Extraction focus (what the phase's checklist should verify):
    {extraction_focus}

    Generation instructions (what the artifact should contain):
    {generation_instructions}

    Artifact schema:
    {artifact_schema_description}

    Judge guidance (what the judge should specifically look for):
    {judge_guidance}

    Example checklist items (to calibrate quality expectations):
    {example_checklist_items}

    ---

    SECTION 3 -- WORKSPACE STATE

    The following files currently exist in the workspace:
    {tree listing of relevant workspace directories}

    Generators can Read any of these files. They write new files using
    the Write tool. The workspace root is the generators' cwd.

    ---

    SECTION 4 -- PRIOR PHASE CONTEXT

    The following phases have already completed:
    {for each completed phase:}
      Phase {id}: {name}
        Output: {artifact_path}
        Status: completed

    The artifacts from these phases are available in the workspace.
    Your prompts should instruct generators to Read them as needed.

    ---

    SECTION 5 -- PROMPT-RUNNER FORMAT CONSTRAINTS

    Your output must be a valid prompt-runner input file. The format is:

    1. The file contains one or more prompt sections.
    2. Each section starts with a level-2 heading:
       ## Prompt N: Descriptive Title
    3. Each section contains exactly two fenced code blocks (triple
       backticks). The first is the generation prompt, the second is
       the validation prompt.
    4. CRITICAL: prompt bodies must NOT contain triple-backtick fences
       inside them. If a prompt needs to show code examples, use
       4-space indentation or describe the code in prose.
    5. Prose, notes, and explanations may appear between the heading
       and first fence, between the fences, and after the second fence
       -- but they are ignored by prompt-runner.

    Example structure:

    ## Prompt 1: Extract Requirements Checklist

    Generation prompt -- instructs the generator what to produce.

    ```
    Read docs/requirements/raw-requirements.md and extract...
    Write the result to docs/requirements/requirements-inventory.yaml...
    ```

    Validation prompt -- tells the judge what to verify.

    ```
    Evaluate the requirements inventory against these criteria:
    1. Every section of raw-requirements.md has at least one...
    ...
    End with VERDICT: pass, VERDICT: revise, or VERDICT: escalate.
    ```

    ---

    SECTION 6 -- DECOMPOSITION GUIDANCE

    Decide how many prompts are needed based on the complexity of what
    this phase must produce. Guidelines:

    - Simple phases (Phase 0: flat extraction): 2-3 prompts.
    - Medium phases (Phase 1-2: structuring and design): 3-5 prompts.
    - Complex phases (Phase 3-5: contracts, simulations, implementation):
      4-7 prompts.

    Each prompt should produce a coherent, self-contained increment.
    Later prompts build on earlier ones. Common decomposition patterns:

    - Extract-then-structure: first prompt extracts raw data, second
      organizes it, third fills in details.
    - Section-by-section: one prompt per major section of the output
      artifact.
    - Scaffold-then-populate: first prompt creates the skeleton with
      IDs and structure, subsequent prompts fill in content.

    Each generation prompt must instruct the generator to write files
    in the workspace using the Write tool. Tell it exactly which file
    path to write to.

    Each validation prompt must tell the judge what to verify. Include:
    - Specific checklist criteria (derived from the extraction focus).
    - Instructions to Read the generated file and check structure.
    - Instructions to verify traceability to input artifacts.
    - The verdict instruction: end with VERDICT: pass/revise/escalate.

    ---

    SECTION 7 -- CROSS-REFERENCE FEEDBACK (conditional)

    [Only included when re-generating after a cross-reference failure]

    The previous execution of this phase's prompts completed, but
    cross-reference verification found the following issues:

    {for each issue:}
      - Category: {traceability|coverage|consistency|integration}
        Description: {issue_description}
        Affected elements: {element_ids}

    Your revised prompt file must address these issues. Specifically:
    {targeted guidance based on failure categories}

### 7.3 Key design decisions

**Why Claude generates the prompt file instead of the methodology-runner assembling it directly:** The number of prompts and their decomposition depends on project complexity, which varies per project. A template-based approach would produce rigid, one-size-fits-all prompt files. Claude can assess the complexity of the inputs and decide whether a phase needs 2 prompts or 7.

**Why the meta-prompt includes example checklist items:** Calibration. Without examples, Claude tends to produce either overly vague or overly granular checklist criteria. The examples from M-002 set the quality bar.

**Why the format constraints are explicit and detailed:** prompt-runner's parser is strict about the two-fenced-blocks-per-section invariant. A misformatted file causes a parse error before any work happens. The meta-prompt must prevent this failure mode.

## 8. Cross-Reference Verification

After prompt-runner completes a phase, the methodology-runner runs a separate verification step that checks the phase's output against all prior phases' outputs.

### 8.1 What it checks

Four categories of verification, checked in order:

**Traceability** -- Does every element in this phase's output trace back to elements in prior phases?
- Phase 0 output elements trace to raw requirements (via source_location and verbatim_quote).
- Phase 1 features trace to Phase 0 inventory items (via source_inventory_refs).
- Phase 2 components trace to Phase 1 features (via feature_realization_map).
- Phase 3 contracts trace to Phase 2 interactions.
- Phase 4 simulations trace to Phase 3 contracts.
- Phase 5 implementation units trace to Phase 3 contracts and Phase 4 simulations.
- Phase 6 verification items trace to Phase 0 and Phase 1 elements.

**Coverage** -- Are all upstream elements accounted for?
- Every RI-* in the inventory appears in at least one Phase 1 feature or is explicitly out-of-scope.
- Every feature appears in at least one Phase 2 component's realization map.
- Every interaction appears in at least one Phase 3 contract.
- And so on through the chain.

**Consistency** -- Do references actually resolve?
- If a feature claims source_inventory_refs: [RI-003, RI-007], both RI-003 and RI-007 must exist in the inventory.
- If a component claims to participate in FT-002, FT-002 must exist in the feature specification.
- No dangling references anywhere in the chain.

**Integration** -- Do cross-phase artifacts cohere?
- No contradictions between what a feature says and what its design components do.
- No orphan components (components not referenced by any feature).
- No dead-end interactions (interactions not used by any contract).

### 8.2 Verification prompt template

    You are a cross-reference verification agent for an AI-driven
    software development pipeline. Your job is to verify that the
    output of Phase {phase_id} ({phase_name}) is correctly integrated
    with all prior phase outputs.

    ## Files to inspect

    Current phase output:
      {output_artifact_path}

    Prior phase outputs:
    {for each prior phase:}
      Phase {id} ({name}): {artifact_path}

    ## Verification checks

    Perform these checks in order. For each check, report every issue
    found -- do not stop at the first failure.

    ### 1. Traceability
    {phase-specific traceability instructions}

    ### 2. Coverage
    {phase-specific coverage instructions}

    ### 3. Consistency
    {phase-specific consistency instructions}

    ### 4. Integration
    {phase-specific integration instructions}

    ## Output format

    Produce a YAML document with this structure:

        verdict: "pass" or "fail"
        checks:
          traceability:
            status: "pass" or "fail"
            issues: []
          coverage:
            status: "pass" or "fail"
            issues: []
          consistency:
            status: "pass" or "fail"
            issues: []
          integration:
            status: "pass" or "fail"
            issues: []

    Each issue must have:
      - category: which check found it
      - description: what is wrong
      - affected_elements: list of element IDs involved
      - severity: "blocking" or "warning"

    The overall verdict is "pass" only if all four checks pass (no
    blocking issues). Warning-severity issues do not block the verdict.

    Read the files using the Read tool. Use Grep to search for specific
    element IDs. Do not hallucinate file contents -- always read them.

### 8.3 Failure handling

When cross-reference verification fails:

1. The orchestrator increments a re-generation counter for the current phase.
2. If the counter is below MAX_CROSS_REF_RETRIES (default: 2), the orchestrator calls prompt_generator again, this time including the cross-reference issues in Section 7 of the meta-prompt.
3. prompt-runner is re-invoked on the new .md file. Before re-invocation, the orchestrator reverts workspace changes from the failed attempt (git checkout -- on the phase's output files).
4. If the counter reaches MAX_CROSS_REF_RETRIES, the orchestrator halts with an escalation message identifying the unresolved cross-reference issues.

## 9. State and Resumption

### 9.1 Project state file

State is tracked in .methodology-runner/project-state.yaml:

    project:
      name: "{project_name}"
      workspace_dir: "{absolute_path}"
      started_at: "{ISO 8601}"
      model: "{claude_model}"

    phases:
      - phase_id: "PH-000-requirements-inventory"
        status: "completed"          # pending | in_progress | completed | failed | escalated
        started_at: "2026-04-08T10:00:00Z"
        completed_at: "2026-04-08T10:15:00Z"
        prompt_file: ".methodology-runner/runs/phase-0/prompt-file.md"
        cross_ref_result: ".methodology-runner/runs/phase-0/cross-ref-result.yaml"
        cross_ref_retries: 0
        git_commit: "abc1234"

      - phase_id: "PH-001-feature-specification"
        status: "pending"
        started_at: null
        completed_at: null
        prompt_file: null
        cross_ref_result: null
        cross_ref_retries: 0
        git_commit: null

      ...

### 9.2 Status transitions

    pending --> in_progress      # orchestrator starts the phase
    in_progress --> completed    # prompt-runner succeeded AND cross-ref passed
    in_progress --> failed       # prompt-runner escalated or cross-ref exhausted retries
    in_progress --> escalated    # max retries reached, halting
    failed --> in_progress       # user explicitly retries via CLI

### 9.3 Resumption logic

When the user runs the methodology-runner on an existing project:

1. Read project-state.yaml.
2. Find the first phase whose status is not "completed".
3. If that phase is "in_progress" or "failed", reset it to "pending" (discard partial work).
4. Begin execution from that phase.

A phase is "completed" only when:
- prompt-runner returned exit code 0 (or PipelineResult.halted_early is False).
- Cross-reference verification returned verdict "pass".
- The git commit for the phase exists.

### 9.4 State file updates

The state file is written atomically (write to a temp file, then rename) after every status transition. This prevents corruption if the process is killed mid-write.

## 10. Interface Contracts

### 10.1 models.py

    @dataclass(frozen=True)
    class ArtifactRef:
        """Reference to an input or output artifact."""
        path: str
        role: str          # "primary" | "validation-reference" | "upstream-traceability"
        format: str        # "markdown" | "yaml" | "json"
        description: str

    @dataclass(frozen=True)
    class PhaseConfig:
        """Complete configuration for one methodology phase."""
        phase_id: str                    # e.g. "PH-000-requirements-inventory"
        phase_name: str                  # e.g. "Requirements Inventory"
        phase_number: int                # 0-6
        predecessors: list[str]          # phase_ids this phase depends on
        input_artifacts: list[ArtifactRef]
        output_artifact_path: str        # e.g. "docs/requirements/requirements-inventory.yaml"
        output_format: str               # e.g. "yaml"
        extraction_focus: str            # multi-line text from M-002
        generation_instructions: str     # multi-line text from M-002
        judge_guidance: str              # multi-line text from M-002
        artifact_schema_description: str # multi-line text from M-002
        example_checklist_items: list[str]  # sample criteria from M-002

    class PhaseStatus(Enum):
        """Lifecycle status of a phase within a project."""
        PENDING = "pending"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        FAILED = "failed"
        ESCALATED = "escalated"

    @dataclass
    class PhaseState:
        """Mutable state for one phase within a project run."""
        phase_id: str
        status: PhaseStatus
        started_at: datetime | None
        completed_at: datetime | None
        prompt_file: str | None
        cross_ref_result_path: str | None
        cross_ref_retries: int
        git_commit: str | None

    @dataclass
    class ProjectState:
        """Full project state, persisted to project-state.yaml."""
        project_name: str
        workspace_dir: Path
        started_at: datetime
        model: str | None
        phases: list[PhaseState]

    @dataclass(frozen=True)
    class CrossRefIssue:
        """A single cross-reference verification issue."""
        category: str          # "traceability" | "coverage" | "consistency" | "integration"
        description: str
        affected_elements: list[str]
        severity: str          # "blocking" | "warning"

    @dataclass(frozen=True)
    class CrossRefCheckResult:
        """Result of one verification check category."""
        status: str            # "pass" | "fail"
        issues: list[CrossRefIssue]

    @dataclass(frozen=True)
    class CrossReferenceResult:
        """Complete cross-reference verification result for a phase."""
        verdict: str           # "pass" | "fail"
        traceability: CrossRefCheckResult
        coverage: CrossRefCheckResult
        consistency: CrossRefCheckResult
        integration: CrossRefCheckResult

    @dataclass(frozen=True)
    class PhaseResult:
        """Outcome of executing one phase (prompt-runner + cross-ref)."""
        phase_id: str
        prompt_runner_success: bool
        cross_ref_result: CrossReferenceResult | None
        prompt_file_path: Path
        run_dir: Path
        error_message: str | None

### 10.2 phases.py

    def load_phase_configs() -> list[PhaseConfig]:
        """Return PhaseConfig for all seven methodology phases.

        Phase definitions are derived from the methodology corpus
        (M-002). The returned list is in dependency order (Phase 0
        first, Phase 6 last).
        """
        ...

    def get_phase_config(phase_id: str) -> PhaseConfig:
        """Return the PhaseConfig for a specific phase.

        Raises ValueError if phase_id is not recognized.
        """
        ...

    def get_execution_order(
        phases: list[PhaseConfig],
    ) -> list[PhaseConfig]:
        """Return phases in topological order based on predecessors.

        Raises ValueError if the dependency graph contains a cycle.
        """
        ...

### 10.3 prompt_generator.py

    @dataclass(frozen=True)
    class PromptGenerationContext:
        """Everything needed to generate a prompt-runner input file."""
        phase_config: PhaseConfig
        workspace_dir: Path
        completed_phases: list[PhaseState]
        cross_ref_feedback: CrossReferenceResult | None  # None on first attempt

    def generate_prompt_file(
        context: PromptGenerationContext,
        claude_client: ClaudeClient,
        output_path: Path,
        model: str | None = None,
    ) -> Path:
        """Call Claude to produce a prompt-runner .md file for a phase.

        Assembles the meta-prompt from the context, calls Claude, writes
        the result to output_path, and returns the path. Raises
        PromptGenerationError if Claude fails or the output does not
        parse as a valid prompt-runner input file.
        """
        ...

        # For phases with reusable deterministic checks, stage a phase-local
        # helper beside output_path before assembling the meta-prompt. For
        # PH-001 this is phase-1-deterministic-validation.py, which checks
        # schema, RI coverage, dependency targets, and cross-cutting-concern
        # cardinality so the LLM judge can focus on semantic issues.

    def assemble_meta_prompt(
        context: PromptGenerationContext,
    ) -> str:
        """Build the meta-prompt string from context.

        Exposed for testing. The prompt_generator calls this internally;
        tests can call it directly to inspect the assembled prompt
        without invoking Claude.
        """
        ...

        # When a deterministic helper is available, the meta-prompt should
        # expose the exact `deterministic-validation` block the architect is
        # expected to include in the generated prompt-runner file.

    class PromptGenerationError(Exception):
        """Raised when prompt file generation fails."""

        def __init__(self, phase_id: str, reason: str) -> None:
            super().__init__(f"Phase {phase_id}: {reason}")
            self.phase_id = phase_id
            self.reason = reason

### 10.4 cross_reference.py

    def verify_cross_references(
        phase_config: PhaseConfig,
        workspace_dir: Path,
        completed_phases: list[PhaseState],
        claude_client: ClaudeClient,
        output_path: Path,
        model: str | None = None,
    ) -> CrossReferenceResult:
        """Run cross-reference verification for a completed phase.

        Calls Claude with tool access to inspect workspace files.
        Writes the structured result to output_path and returns it.
        Raises CrossReferenceError if Claude fails to produce a
        parseable result.
        """
        ...

    def assemble_verification_prompt(
        phase_config: PhaseConfig,
        workspace_dir: Path,
        completed_phases: list[PhaseState],
    ) -> str:
        """Build the verification prompt string.

        Exposed for testing.
        """
        ...

    class CrossReferenceError(Exception):
        """Raised when verification call fails or returns unparseable output."""

        def __init__(self, phase_id: str, reason: str) -> None:
            super().__init__(f"Cross-ref verification for {phase_id}: {reason}")
            self.phase_id = phase_id
            self.reason = reason

### 10.5 orchestrator.py

    MAX_CROSS_REF_RETRIES = 2

    @dataclass(frozen=True)
    class OrchestratorConfig:
        """Configuration for a methodology-runner execution."""
        workspace_dir: Path
        project_name: str
        model: str | None
        max_prompt_runner_iterations: int    # passed to prompt-runner's RunConfig
        max_cross_ref_retries: int           # default: MAX_CROSS_REF_RETRIES
        resume: bool                         # if True, resume from last completed phase

    @dataclass(frozen=True)
    class OrchestratorResult:
        """Outcome of a full or partial methodology run."""
        phase_results: list[PhaseResult]
        completed_all: bool
        halted_at_phase: str | None
        halt_reason: str | None

    def run_methodology(
        config: OrchestratorConfig,
        claude_client: ClaudeClient,
    ) -> OrchestratorResult:
        """Execute the methodology pipeline.

        Sequences phases in dependency order, generates prompt files,
        invokes prompt-runner, runs cross-reference verification, and
        manages state. If config.resume is True, skips already-completed
        phases.

        Returns an OrchestratorResult summarizing what happened.
        """
        ...

    def load_project_state(workspace_dir: Path) -> ProjectState | None:
        """Load project state from disk. Returns None if no state file exists."""
        ...

    def save_project_state(state: ProjectState) -> None:
        """Atomically write project state to disk."""
        ...

    def initialize_project(
        workspace_dir: Path,
        project_name: str,
        model: str | None,
    ) -> ProjectState:
        """Initialize a new project: create .methodology-runner/, init git,
        make initial commit, return a fresh ProjectState with all phases pending.
        """
        ...

### 10.6 cli.py

    def main(argv: list[str] | None = None) -> int:
        """CLI entry point. Subcommands:

        run <workspace-dir>
          --project-name NAME        Project name for state tracking
          --model MODEL              Claude model to use
          --max-iterations N         Max prompt-runner iterations per prompt (default: 3)
          --max-cross-ref-retries N  Max cross-ref re-generation attempts (default: 2)
          --resume                   Resume from last completed phase
          --phase N                  Run only phase N (debug)

        status <workspace-dir>
          Show the current project state.

        reset <workspace-dir> --phase N
          Reset phase N to pending status. Also resets all downstream phases.

        Returns 0 on success, 1 on escalation/halt, 2 on usage error.
        """
        ...

---

## 11. Skill-driven per-phase selection

This section documents how methodology-runner specializes each phase's
knowledge for the technology stack being developed, without coupling
the methodology text itself to any specific language or framework.

### 11.1 Skill catalog discovery

At the start of every `run_pipeline` invocation (before any phase
executes), the orchestrator calls `skill_catalog.build_catalog()` to
walk the active discovery locations in priority order:

1. `<workspace>/.claude/skills/**/SKILL.md` — project-local skills
2. `<cwd>/.methodology/skills/**/SKILL.md` — repo-local methodology skills
3. `~/.claude/skills/**/SKILL.md` — user-global skills
4. `~/.claude/plugins/*/skills/**/SKILL.md` — plugin-installed skills

Each SKILL.md is parsed for YAML frontmatter (`name` and
`description`) and registered in an in-memory catalog keyed by skill
ID.  Higher-priority locations shadow lower ones; overrides are
logged.

If the resulting catalog is empty, the orchestrator halts with an
actionable error before any phase runs (failure mode 7).

### 11.2 Baseline skills configuration

The file `.methodology/docs/skills-baselines.yaml` declares the
non-negotiable skills per phase.  It is read at run start by
`baseline_config.load_baseline_config()` and validated against the
catalog by `baseline_config.validate_against_catalog()`.  Any baseline
skill ID that is not in the catalog is a critical halt (failure mode
9).

This file is intentionally data, not code: adding or removing a
baseline skill is a one-line edit and takes effect on the next run.

### 11.3 Skill-Selector agent (per-phase)

Before each phase's meta-prompt runs, the orchestrator invokes the
Skill-Selector via `skill_selector.invoke_skill_selector()`.  The
selector is a single Claude call with four inputs:

- The phase definition (from `PhaseConfig`)
- The baseline skills for this phase (from `skills-baselines.yaml`)
- The compact catalog (ID + description only, not full SKILL.md bodies)
- Prior phase artifacts (small ones in full; large ones summarized
  and cached by `artifact_summarizer.ArtifactSummaryProvider`)
- The stack manifest, if it exists (from PH-002 Architecture)

The selector emits a YAML document which is parsed, validated
(failure modes 1-6), and persisted to the phase's run directory as
`phase-NNN-skills.yaml`.  The file is committed to the workspace git
repo along with the phase's output artifact.

**Locking:** the manifest is locked across cross-reference retries
within a single run.  A retry regenerates the prompt-runner .md file
but reuses the locked skill manifest and prelude.  On `resume`, the
user can pass `--rerun-selector` to force a new selector invocation
for the halted phase.

### 11.4 Prelude construction (dual mode)

`prelude.build_prelude()` converts a `PhaseSkillManifest` into two
text blocks (generator and judge) using one of two designs:

- **`skill-tool` mode** (primary): the prelude instructs the agent to
  invoke the Claude Code Skill tool by name for each selected skill.
  The agent loads SKILL.md content just-in-time.  Depends on the
  Skill tool being available inside nested `claude --print`
  subprocess calls.
- **`inline` mode** (fallback): the prelude embeds the full SKILL.md
  body (minus frontmatter) of every selected skill, delimited by
  section markers.  Larger preludes but zero dependency on the Skill
  tool.

The default mode is set by `constants.SKILL_LOADING_MODE`.  Phase 0
the current PH-000 deterministic validator lives in `phase_0_validation.py`
in the deployment environment and records its verdict in
`runs/phase-0-validation/validation-report.md`.

Both prelude texts are written to the phase's run directory as
`generator-prelude.txt` and `judge-prelude.txt` and passed to
prompt-runner via two new CLI flags.

### 11.5 Prompt-runner prelude flags

`prompt-runner run` accepts two new optional flags:

- `--generator-prelude PATH` — file whose contents are prepended to
  every generator Claude message in the run
- `--judge-prelude PATH` — symmetric for judge messages

Prelude content is read once at startup and cached for the duration.
prompt-runner does not parse, interpret, or modify the content; it
treats it as opaque text so the tool remains skill-agnostic and
usable outside methodology-runner.

The orchestrator passes prelude file paths into `_invoke_prompt_runner`,
which threads them into the library call via `RunConfig.generator_prelude`
and `RunConfig.judge_prelude`, or into the subprocess call via the CLI
flags.

### 11.6 Per-phase execution flow

```
┌──────────────────────────────────────────────────────────────────┐
│ _run_single_phase (per-phase)                                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Mark phase RUNNING                                           │
│  2. Invoke Skill-Selector                                        │
│       - skip if phase-NNN-skills.yaml exists and not             │
│         --rerun-selector                                         │
│       - validate catalog membership + baseline coverage          │
│       - any failure = critical halt                              │
│  3. Build generator-prelude.txt and judge-prelude.txt            │
│  4. Generate phase-NNN-prompts.md via existing meta-prompt       │
│                                                                  │
│  ┌─ cross-reference retry loop (max N=2) ──────────────────┐     │
│  │                                                         │     │
│  │  5. Invoke prompt-runner with prelude file paths        │     │
│  │  6. Cross-reference verification                        │     │
│  │     - pass  → exit loop, go to step 7                   │     │
│  │     - fail  → if retries remaining:                     │     │
│  │                 re-generate prompt file with cross-ref  │     │
│  │                 feedback; skill manifest stays LOCKED   │     │
│  │                 back to step 5                          │     │
│  │               if retries exhausted:                     │     │
│  │                 critical halt (failure mode 11)         │     │
│  │                                                         │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  7. Commit all phase artifacts including phase-NNN-skills.yaml,  │
│     generator-prelude.txt, judge-prelude.txt                     │
│  8. Mark phase COMPLETED                                         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 11.7 Phase 0 validation (release gate)

Before first use of `skill-tool` mode, Phase 0 validation must be
run: `python -m methodology_runner.phase_0_validation --help`.

The script creates a temporary test skill under `~/.claude/skills/`,
invokes `claude --print` with an instruction to load it via the
Skill tool, and inspects the response for a distinctive sentinel
string.  If found, `skill-tool` mode is verified and the report is
committed as a release gate.  If not, the fallback `inline` mode is
used.

Failure mode 14: methodology-runner refuses to start in `skill-tool`
mode unless `runs/phase-0-validation/validation-report.md` exists and
records a successful outcome.
