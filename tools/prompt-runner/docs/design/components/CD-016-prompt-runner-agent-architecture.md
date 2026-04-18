# Design: Prompt-Runner Agent Architecture

## 1. Finality

This section defines why the component exists.

- **GOAL: GOAL-1** Execute prompt-defined workflows through agent roles
  - **SYNOPSIS:** `prompt-runner` exists to execute prompt modules through
    generator and judge agents rather than through one undifferentiated model
    call stream.
  - **BECAUSE:** Separate agent roles let the runner assign distinct
    responsibilities to production and review within one workflow.

- **GOAL: GOAL-2** Encapsulate step context and expertise inside each agent call
  - **SYNOPSIS:** `prompt-runner` should package the relevant instructions for a
    prompt step into the generator or judge call that executes that step.
  - **BECAUSE:** The runner needs each agent call to carry the right local
    context and specialized guidance without leaking unrelated workflow state.

## 2. Technical Directives

This section defines the technical directives used to build the component well.

- **GOAL: GOAL-3** Keep agent roles generic
  - **SYNOPSIS:** `prompt-runner` should define stable generic execution roles
    rather than phase-local or step-local agent variants.
  - **CHAIN-OF-THOUGHT:** Reusability depends on keeping the agent identities
    stable while allowing the instructions they receive to vary.
  - **BECAUSE:** Generic agent roles keep the runner reusable across many
    prompt modules.

- **GOAL: GOAL-4** Put specialization in runtime inputs, not in agent identity
  - **SYNOPSIS:** The generator and judge agents should be specialized by the
    prompt body, embedded directive blocks, and any supplied agent properties,
    not by phase-specific agent designs or runtime skill auto-loading.
  - **BECAUSE:** The same generator/judge operating model should work across
    many workflows as long as the runtime instructions are explicit.

## 3. Information Model

- **ENTITY: ENTITY-1** `Generator Agent`
  - **SYNOPSIS:** Generic artifact-producing agent role used by prompt-runner
    for one prompt pair.
  - **FIELD:** `task_prompt`
    - **SYNOPSIS:** The generation prompt body for the current prompt pair.
    - **BECAUSE:** The generator needs the concrete task it is meant to carry
      out for this step.
  - **FIELD:** `generator_prelude`
    - **SYNOPSIS:** Optional prepended runtime guidance supplied for the
      current run.
    - **BECAUSE:** Prompt-runner needs one way to package specialized guidance
      into the generator's local context.
  - **FIELD:** `agent_properties`
    - **SYNOPSIS:** Optional agent configuration resolved for this generator
      call from the prompt file or run configuration.
    - **BECAUSE:** Prompt-runner should let prompt files carry their own
      execution-local agent context when that context belongs with the prompt.
  - **FIELD:** `run_worktree`
    - **SYNOPSIS:** The editable project tree that the generator reads and
      writes during the run.
    - **BECAUSE:** Artifact production only makes sense relative to one
      concrete project tree.

- **ENTITY: ENTITY-2** `Judge Agent`
  - **SYNOPSIS:** Generic review and verdict agent role used by prompt-runner
    for one prompt pair.
  - **FIELD:** `task_prompt`
    - **SYNOPSIS:** The validation prompt body for the current prompt pair.
    - **BECAUSE:** The judge needs the concrete review task for this step.
  - **FIELD:** `judge_prelude`
    - **SYNOPSIS:** Optional prepended runtime guidance supplied for the
      current run.
    - **BECAUSE:** Prompt-runner needs one way to package specialized review
      guidance into the judge's local context.
  - **FIELD:** `agent_properties`
    - **SYNOPSIS:** Optional agent configuration resolved for this judge call
      from the prompt file or run configuration.
    - **BECAUSE:** Prompt-runner should let prompt files carry their own
      execution-local review context when that context belongs with the prompt.
  - **FIELD:** `verdict_contract`
    - **SYNOPSIS:** The required prompt-runner verdict protocol: pass, revise,
      or escalate.
    - **BECAUSE:** The runner needs a stable control protocol independent of
      prompt content.

- **ENTITY: ENTITY-3** `Runtime Contract`
  - **SYNOPSIS:** The actual instructions the prompt-runner agents consume for
    one call.
  - **FIELD:** `prompt_body`
    - **SYNOPSIS:** The current generation or validation prompt text.
    - **BECAUSE:** The current prompt pair defines the step-specific task.
  - **FIELD:** `embedded_directives`
    - **SYNOPSIS:** Inline guidance blocks or prompt-body includes rendered
      directly into the prompt text before the agent call.
    - **BECAUSE:** Prompt modules now carry specialized instruction content
      directly instead of relying on the agent to discover runtime skills.
  - **FIELD:** `prelude_text`
    - **SYNOPSIS:** Optional opaque text prepended by prompt-runner before the
      prompt body.
    - **BECAUSE:** Prompt-runner needs one generic way to package specialized
      guidance into every generator or judge call.
  - **FIELD:** `agent_properties`
    - **SYNOPSIS:** Optional per-role properties resolved before the call is
      assembled, including embedded prompt-file properties when present.
    - **BECAUSE:** A prompt module should be able to carry self-contained agent
      setup instead of relying only on out-of-band runner flags.
  - **FIELD:** `deterministic_validation_result`
    - **SYNOPSIS:** Optional deterministic check output available to the judge
      path for the current iteration.
    - **BECAUSE:** Some review input is better supplied by deterministic code
      than re-derived by the model.

- **ENTITY: ENTITY-4** `Agent Properties`
  - **SYNOPSIS:** Structured optional properties that influence how
    prompt-runner assembles one generator or judge call.
  - **FIELD:** `prelude`
    - **SYNOPSIS:** Optional opaque text block to prepend before the prompt
      body.
    - **BECAUSE:** Prelude text is the current generic mechanism for packing
      specialized guidance into an agent call.
  - **FIELD:** `property_source`
    - **SYNOPSIS:** Whether the effective properties came from the prompt file,
      the run configuration, or a merge of both.
    - **BECAUSE:** Prompt-runner should preserve where the assembled call
      context came from.

- **ENTITY: ENTITY-5** `Prompt-Level Agent Properties`
  - **SYNOPSIS:** Optional agent properties declared inside the prompt file for
    one prompt pair or variant-local prompt pair.
  - **FIELD:** `generator_properties`
    - **SYNOPSIS:** Optional embedded properties for the generator call.
    - **BECAUSE:** The prompt author may want the generator context to travel
      with the prompt module itself.
  - **FIELD:** `judge_properties`
    - **SYNOPSIS:** Optional embedded properties for the judge call.
    - **BECAUSE:** The prompt author may want the judge context to travel with
      the prompt module itself.

## 4. Agent Workflow

- **PROCESS: PROCESS-1** Build one generator call
  - **SYNOPSIS:** Prompt-runner constructs the generator message from optional
    prelude text followed by the generation prompt body.
  - **READS:** `RunConfig.generator_prelude`
    - **BECAUSE:** The run may supply specialized generator guidance for the
      current workflow.
  - **READS:** prompt-file generator agent properties when present
    - **BECAUSE:** The prompt module should be able to carry its own generator
      context when that makes the file more self-contained.
  - **READS:** `PromptPair.generation_prompt`
    - **BECAUSE:** The current prompt pair supplies the actual task.
  - **RULE:** prompt-file properties win over run-level defaults when both are present
    - **BECAUSE:** Embedded prompt properties are the most local and
      intentional specification of how that prompt pair should run.
  - **BECAUSE:** Prompt-runner should own message assembly, not the semantics
    of the guidance it is assembling.

- **PROCESS: PROCESS-2** Run the generic generator agent
  - **SYNOPSIS:** The generator agent reads the assembled runtime contract and
    produces or revises artifacts in the project tree for the run.
  - **USES:** `Generator Agent`
    - **BECAUSE:** Artifact production is a distinct execution role from
      judging or orchestration.
  - **WRITES:** project files in the run worktree
    - **BECAUSE:** The generator's purpose is to change the artifact state for
      the current workflow.

- **PROCESS: PROCESS-3** Run deterministic validation when declared
  - **SYNOPSIS:** Prompt-runner executes any declared deterministic validation
    command after generator completion and before judging.
  - **BECAUSE:** Deterministic checks belong to the runner when they do not
    require model judgment.

- **PROCESS: PROCESS-4** Build one judge call
  - **SYNOPSIS:** Prompt-runner constructs the judge message from optional
    prelude text, optional deterministic validation output, the validation
    prompt body, and the verdict contract.
  - **READS:** `RunConfig.judge_prelude`
    - **BECAUSE:** The run may supply specialized judge guidance for the
      current workflow.
  - **READS:** prompt-file judge agent properties when present
    - **BECAUSE:** The prompt module should be able to carry its own judge
      context when that makes the file more self-contained.
  - **READS:** `PromptPair.validation_prompt`
    - **BECAUSE:** The current prompt pair supplies the actual review task.
  - **RULE:** prompt-file properties win over run-level defaults when both are present
    - **BECAUSE:** Embedded prompt properties are the most local and
      intentional specification of how that prompt pair should run.
  - **BECAUSE:** The runner must keep the pass/revise/escalate protocol stable
    even when prompt content changes.

- **PROCESS: PROCESS-5** Run the generic judge agent
  - **SYNOPSIS:** The judge agent reviews the current artifact state and
    returns a prompt-runner verdict.
  - **USES:** `Judge Agent`
    - **BECAUSE:** Review and verdict production are a distinct execution role
      from generation.

- **PROCESS: PROCESS-6** Iterate or advance
  - **SYNOPSIS:** Prompt-runner uses the judge verdict to pass, revise, or
    escalate the current prompt pair.
  - **BECAUSE:** Revision control is generic runner behavior, not a
    phase-specific agent behavior.

## 5. Boundaries

- **RULE: RULE-1** Prompt-runner defines only the generator and judge roles it executes
  - **SYNOPSIS:** The generic prompt-runner agent architecture should describe
    only the `Generator Agent` and `Judge Agent` roles that prompt-runner
    actually assembles and runs.
  - **BECAUSE:** The design should stay within prompt-runner's own execution
    boundary.

- **RULE: RULE-2** Prompt-runner is skill-agnostic
  - **SYNOPSIS:** Prompt-runner must treat prelude text as opaque runtime input
    and must not interpret skill identities or skill semantics itself.
  - **BECAUSE:** The runner should stay focused on assembling and executing
    agent calls, not on understanding the content of specialized guidance.

- **RULE: RULE-2B** Embedded directives outrank agent-side skill discovery
  - **SYNOPSIS:** Generator and judge agents should treat directive text
    embedded in the prompt body as the authoritative local guidance and should
    not proactively load runtime skills unless the prompt explicitly asks for
    that.
  - **BECAUSE:** The prompt module should be self-contained and replayable
    without depending on separate skill availability.

- **RULE: RULE-2A** Prompt files may embed agent properties
  - **SYNOPSIS:** When a prompt file declares generator or judge agent
    properties, prompt-runner should use them as the effective local properties
    for that prompt pair.
  - **BECAUSE:** Embedding agent properties in the prompt file makes the
    module more self-contained and reduces dependence on command-line-only
    assembly.

- **RULE: RULE-3** Do not create per-step generator or judge agents by default
  - **SYNOPSIS:** A workflow step should normally reuse the generic generator
    and judge agents rather than defining step-local agent types.
  - **BECAUSE:** Step-specific behavior is already carried by the prompt pair,
    optional deterministic validation, and any resolved agent properties.

- **RULE: RULE-4** Runtime specialization enters through the assembled call
  - **SYNOPSIS:** If a run needs specialized behavior, that specialization
    should enter through the runtime contract for the call.
  - **BECAUSE:** That keeps the agent design stable while allowing the
    workflow-level instructions to vary.

- **RULE: RULE-5** Command-line agent properties are defaults, not the only source
  - **SYNOPSIS:** Run-level flags such as generator and judge preludes should
    remain available, but they should serve as fallback or default properties
    when the prompt file does not supply more local ones.
  - **BECAUSE:** The runner should support both self-contained prompt modules
    and external run-time injection.

- **MODIFICATION: MOD-1** Put the agent-role explanation in the prompt-runner
  design corpus
  - **SYNOPSIS:** The generic generator and judge agent model should live in
    the prompt-runner design corpus rather than being left implicit.
  - **BECAUSE:** These are execution roles of the runner itself and should be
    documented where the runner is defined.
