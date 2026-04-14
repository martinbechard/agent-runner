# Design: Prompt Runner Core

## 1. Requirements

This section defines the generic product goals of `prompt-runner` itself.

- **REQUIREMENT: REQ-1** Core workflow execution
  - **SYNOPSIS:** Prompt-runner MUST execute a prompt-defined workflow as an ordered sequence of generator and judge steps.
    - **BECAUSE:** The core purpose of the tool is to turn a prompt file into executable workflow control rather than a single model call.
  - **REQUIREMENT:** Sequential artifact flow
    - **SYNOPSIS:** The runner MUST preserve prompt artifacts and verdicts so later prompts can build on earlier results.
      - **BECAUSE:** Prompt workflows only make sense if earlier outputs remain available and inspectable.
  - **REQUIREMENT:** Judge-mediated revision
    - **SYNOPSIS:** The runner SHOULD support revise, pass, and escalate control flow for each prompt pair.
      - **BECAUSE:** Feedback loops are part of the product purpose, not an optional add-on.

- **REQUIREMENT: REQ-2** Reusable prompt definitions
  - **SYNOPSIS:** Prompt files SHOULD remain reusable across runs, with run-specific state supplied through existing runtime concepts such as `run_dir` and `project_dir`.
    - **BECAUSE:** Requiring per-run prompt rewrites would defeat the value of prompt-runner as a reusable execution substrate.
  - **REQUIREMENT:** Native placeholder rendering
    - **SYNOPSIS:** Prompt-runner SHOULD resolve built-in placeholders such as `run_dir` and `project_dir` itself and SHOULD accept caller-supplied values for additional placeholders.
      - **BECAUSE:** Parameter substitution belongs in deterministic runner logic, not in prompt prose or one-off launcher rendering.
  - **REQUIREMENT:** Deterministic validation hooks
    - **SYNOPSIS:** Prompt-runner SHOULD support an optional deterministic validation script between the generator and judge steps.
      - **BECAUSE:** Structural and traceability checks that do not require an LLM should run once in deterministic code instead of being rediscovered through repeated Bash and Python snippets inside model sessions.

- **REQUIREMENT: REQ-3** Operational robustness
  - **SYNOPSIS:** The runner SHOULD provide containment, traceability, and recovery mechanisms that keep long-running and nested workflows practical.
    - **BECAUSE:** The core workflow is not usable if runs recurse into each other, disappear, or cannot be resumed or inspected.
  - **REQUIREMENT:** Stable run containment
    - **SYNOPSIS:** Default run output MUST live under `<project>/.prompt-runner/runs`.
      - **BECAUSE:** Mixed root-level run output leads to recursive snapshotting and path explosion.
  - **REQUIREMENT:** Child-process traceability
    - **SYNOPSIS:** Spawned backend calls and child prompt-runner processes MUST leave durable PID metadata on disk.
      - **BECAUSE:** Resume, wait, tail, and kill behavior depend on durable process identity.

- **REQUIREMENT: REQ-4** Operational usability
  - **SYNOPSIS:** The runner SHOULD give humans enough feedback to understand whether it launched and what it is doing.
    - **BECAUSE:** Silent or opaque runs cause duplicate launches and mistaken assumptions about whether the process is alive.
  - **REQUIREMENT:** Startup visibility
    - **SYNOPSIS:** A normal run MUST print an immediate startup line.
      - **BECAUSE:** Operators need confirmation before any backend work starts.
  - **REQUIREMENT:** Live progress visibility
    - **SYNOPSIS:** A normal run SHOULD print terse progress lines for run start, prompt start, generator start/done, judge start/done, verdict, and completion or halt.
      - **BECAUSE:** Long-running workflows are hard to trust or debug without visible progress.

## 2. Information Model

This section defines the main generic concepts in prompt-runner.

- **ENTITY: ENTITY-1** `Run`
  - **SYNOPSIS:** One end-to-end prompt-runner execution.
  - **FIELD:** `source_file`
    - **SYNOPSIS:** Root prompt file executed by the run.
    - **BECAUSE:** The run needs one authoritative workflow definition.
  - **FIELD:** `run_dir`
    - **SYNOPSIS:** Runner-owned directory holding manifests, summaries, logs, prompt outputs, and snapshots.
    - **BECAUSE:** The run needs a durable execution record.
  - **FIELD:** `project_dir`
    - **SYNOPSIS:** Intended project tree for the run.
    - **BECAUSE:** The runner needs to know which repository tree the workflow acts on.
  - **FIELD:** `workspace_dir`
    - **SYNOPSIS:** Concrete editable working tree used by backend subprocesses.
    - **BECAUSE:** The editable tree may be the project itself or a copied workspace.
  - **FIELD:** `config`
    - **SYNOPSIS:** Backend, model, iteration, and resume settings.
    - **BECAUSE:** One consistent configuration must drive the whole run.

- **ENTITY: ENTITY-2** `PromptPair`
  - **SYNOPSIS:** One generator/judge unit parsed from a prompt file.
  - **FIELD:** `generation_prompt`
    - **SYNOPSIS:** Generator task body.
    - **BECAUSE:** The runner must know what to send to the generator.
  - **FIELD:** `validation_prompt`
    - **SYNOPSIS:** Judge task body.
    - **BECAUSE:** The runner must know what validation text drives pass, revise, or escalate.
  - **FIELD:** `required_files`
    - **SYNOPSIS:** Optional typed block listing files that must exist before the generator executes.
    - **BECAUSE:** Deterministic preconditions should be validated by the runner rather than by an LLM.
  - **FIELD:** `checks_files`
    - **SYNOPSIS:** Optional typed block listing files whose presence should be traced without failing the prompt.
    - **BECAUSE:** Optional file checks should be recorded by the runner without wasting LLM tokens.
  - **FIELD:** `deterministic_validation`
    - **SYNOPSIS:** Optional typed block listing the argv elements for a Python validation script that runs after the generator and before the judge.
    - **BECAUSE:** Prompt authors need one stable way to stage deterministic checks and feed the result to the judge without asking the model to rebuild that logic ad hoc.

- **ENTITY: ENTITY-3** `PromptModule`
  - **SYNOPSIS:** Reusable prompt-definition file intended to be run by prompt-runner.
  - **FIELD:** `prompt_pairs`
    - **SYNOPSIS:** Ordered prompt pairs contained in the file.
    - **BECAUSE:** Prompt-runner executes a structured sequence, not one flat prompt body.
  - **FIELD:** `placeholder_usage`
    - **SYNOPSIS:** Whether the file contains placeholders that prompt-runner resolves at run time.
    - **BECAUSE:** Some prompt modules require run-specific values while still remaining reusable files.

- **ENTITY: ENTITY-4** `PlaceholderContext`
  - **SYNOPSIS:** Mapping of placeholder names to concrete values used when prompt-runner renders a reusable prompt module for one run.
  - **FIELD:** `built_in_values`
    - **SYNOPSIS:** Runner-known values such as `run_dir` and `project_dir`.
    - **BECAUSE:** The runner can derive some placeholder values directly from its own runtime state.
  - **FIELD:** `caller_values`
    - **SYNOPSIS:** Extra placeholder values provided by the launcher or other caller.
    - **BECAUSE:** Some workflow-specific placeholders depend on campaign setup outside the generic runner.

- **ENTITY: ENTITY-5** `PromptResult`
  - **SYNOPSIS:** Persisted outcome of one executed prompt.
  - **FIELD:** `iterations`
    - **SYNOPSIS:** Generator/judge attempts for the prompt.
    - **BECAUSE:** Revision loops must remain inspectable.
  - **FIELD:** `final_verdict`
    - **SYNOPSIS:** Final pass, revise, or escalate outcome.
    - **BECAUSE:** Later control flow depends on the verdict.

- **ENTITY: ENTITY-7** `DeterministicValidationResult`
  - **SYNOPSIS:** One captured deterministic validation run for one generator iteration.
  - **FIELD:** `command`
    - **SYNOPSIS:** Full argv used to execute the validator.
    - **BECAUSE:** Operators need to know exactly what deterministic check ran.
  - **FIELD:** `returncode`
    - **SYNOPSIS:** Validation script exit status.
    - **BECAUSE:** The runner needs a stable distinction between passed checks, failed checks, and validator execution errors.
  - **FIELD:** `stdout_log`
    - **SYNOPSIS:** Captured validator stdout log path.
    - **BECAUSE:** The judge and later operators need a durable record of the deterministic findings.
  - **FIELD:** `stderr_log`
    - **SYNOPSIS:** Captured validator stderr log path.
    - **BECAUSE:** Deterministic validator failures need explicit diagnosis.

- **ENTITY: ENTITY-6** `SpawnedProcess`
  - **SYNOPSIS:** Durable metadata record for a launched backend or child runner process.
  - **FIELD:** `pid`
    - **SYNOPSIS:** OS process identifier.
    - **BECAUSE:** Process recovery requires a live PID.
  - **FIELD:** `argv`
    - **SYNOPSIS:** Original command arguments.
    - **BECAUSE:** PID alone is not enough to verify identity.
  - **FIELD:** `status`
    - **SYNOPSIS:** Persisted running or completed state.
    - **BECAUSE:** Recovery logic must distinguish live from finished children.

## 3. Code Structure

This section maps the generic model onto the implementation modules.

- **MODULE: MODULE-1** `src/cli/prompt_runner/__main__.py`
  - **SYNOPSIS:** CLI entrypoint for parsing and running prompt files.
  - **IMPORTS:** `prompt_runner.parser`
    - **BECAUSE:** The CLI needs parsed prompt objects before execution.
  - **IMPORTS:** `prompt_runner.runner`
    - **BECAUSE:** Execution orchestration lives in the runner module.
  - **WRITES:** startup and halt banners
    - **BECAUSE:** CLI visibility is a core usability requirement.

- **MODULE: MODULE-2** `src/cli/prompt_runner/parser.py`
  - **SYNOPSIS:** Parses markdown prompt files into prompt pairs and fork points.
  - **CONTAINS:** `PromptPair`
    - **BECAUSE:** Parsed prompt units need a normalized in-memory representation.
  - **CONTAINS:** `ForkPoint`
    - **BECAUSE:** Variant branches are a distinct execution shape.

- **MODULE: MODULE-3** `src/cli/prompt_runner/runner.py`
  - **SYNOPSIS:** Core pipeline orchestration for prompts, revisions, halts, variants, snapshots, and summaries.
  - **CONTAINS:** `run_prompt`
    - **BECAUSE:** One prompt pair needs a reusable generator/judge control loop.
  - **CONTAINS:** `run_pipeline`
    - **BECAUSE:** Top-level sequencing and final state writing need one owner.
  - **CONTAINS:** `_run_deterministic_validation`
    - **BECAUSE:** Deterministic validation needs one runner-owned execution point between generator completion and judge start.
  - **CONTAINS:** `_emit_progress`
    - **BECAUSE:** Live progress is part of the generic runner experience.
  - **WRITES:** `manifest.json`
    - **BECAUSE:** Each run needs a durable execution record.
  - **WRITES:** `summary.txt`
    - **BECAUSE:** Each run needs a compact human-readable summary.

- **MODULE: MODULE-4** `src/cli/prompt_runner/client_factory.py`
  - **SYNOPSIS:** Maps configured backend names to backend client implementations.
  - **USES:** `prompt_runner.claude_client`
    - **BECAUSE:** Claude is one supported backend adapter.
  - **USES:** `prompt_runner.codex_client`
    - **BECAUSE:** Codex is one supported backend adapter.

- **MODULE: MODULE-5** `src/cli/prompt_runner/process_tracking.py`
  - **SYNOPSIS:** Minimal persistence layer for spawned process metadata.
  - **WRITES:** `*.proc.json`
    - **BECAUSE:** Recovery and monitoring need durable process records.

## 4. Gaps

This section captures remaining generic runner issues.

- **GAP:** Reattach and tail behavior is incomplete
  - **SYNOPSIS:** Process metadata exists, but the CLI still cannot fully reattach to or tail an in-flight child automatically.
    - **BECAUSE:** Process tracking was implemented before full recovery commands.
