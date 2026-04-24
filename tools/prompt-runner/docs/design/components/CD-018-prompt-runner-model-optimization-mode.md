# CD-018 - Prompt Runner Model Optimization Mode

**GOAL: GOAL-1** `Prompt-runner can optimize model settings for one prompt file`
- **SYNOPSIS:** `prompt-runner` SHALL provide an `optimize` mode that takes one existing prompt-runner file plus a list of candidate model and thinking-duration settings, obtains a trusted baseline run, synthesizes a selection-based optimization workflow, executes it, and emits a new prompt-runner file with the winning settings applied per optimizable prompt.
  - **BECAUSE:** The requested enhancement is a repeatable runner feature, not a one-off manual experiment, and the output needs to become a normal prompt-runner file again when the search is complete.

**REQUIREMENT: REQ-1** `Optimization is a separate CLI mode`
- **SYNOPSIS:** Model optimization SHALL live behind `prompt-runner optimize` rather than changing the meaning of `prompt-runner run`.
  - **BECAUSE:** Normal execution and optimization are different control flows, and existing prompt files must keep their current behavior.

**REQUIREMENT: REQ-2** `A trusted baseline exists before optimization starts`
- **SYNOPSIS:** The optimize command SHALL either reuse one existing successful baseline run named on the command line or launch a fresh baseline run of the unmodified source prompt file before it synthesizes the optimization workflow.
  - **BECAUSE:** Optimization needs one accepted reference run so the exercise has a known-good starting point and a before-and-after benchmark.
- **CHECKS-FILE:** baseline run manifest source digest, backend, and completion status
  - **BECAUSE:** Reusing the wrong run would make later comparisons and emitted settings misleading.

**REQUIREMENT: REQ-3** `Candidate settings reuse the existing model and effort contract`
- **SYNOPSIS:** The search space SHALL be expressed as repeatable candidate settings containing `model` plus optional `effort`, where the user's “thinking duration” maps directly onto prompt-runner's existing `[EFFORT:...]` concept.
  - **BECAUSE:** Prompt-runner already has one stable per-prompt execution contract for model and effort, so the optimizer should reuse it instead of inventing a parallel vocabulary.

**REQUIREMENT: REQ-3B** `Optimization search space is configuration-driven`
- **SYNOPSIS:** Prompt-runner SHALL load model-optimization defaults from `prompt-runner.toml`, using separate configuration entries for duration definitions, model definitions, and named optimization profiles.
  - **BECAUSE:** The set of candidate models and sensible durations will evolve over time, and that policy should be editable without changing code or repeatedly restating long CLI candidate lists.

**REQUIREMENT: REQ-3C** `Durations are validated per model`
- **SYNOPSIS:** The optimizer SHALL validate every selected duration name against the chosen model's allowed duration set and SHALL fail fast when a profile or CLI override asks for a duration that the model does not support.
  - **BECAUSE:** Different model families expose different reasoning-effort surfaces, so the optimizer must not generate invalid combinations.

**REQUIREMENT: REQ-4** `Optimization output is an ordinary prompt-runner file`
- **SYNOPSIS:** After the optimization run succeeds, prompt-runner SHALL emit a derived prompt file that preserves the original prompt bodies and metadata but materializes the chosen `[MODEL:...]` and `[EFFORT:...]` directives on each optimized prompt heading.
  - **BECAUSE:** The result should be runnable through ordinary `prompt-runner run` without requiring the optimization harness again.

**REQUIREMENT: REQ-5** `Optimization decisions favor convergence before efficiency`
- **SYNOPSIS:** Candidate comparison SHALL rank settings by acceptable convergence before speed or token use: `pass` beats `revise` beats `escalate`; within passing candidates the runner prefers fewer iterations, then lower prompt wall time, then lower total tokens.
  - **BECAUSE:** A faster or cheaper setting is only valuable if it can still finish the prompt acceptably.

**COMMAND: CMD-1** `Optimize one prompt file`
- **SYNOPSIS:** The entry point SHALL be `prompt-runner optimize <file>` with optional `--profile <name>`, repeatable `--candidate <model>[:<effort>]`, optional `--baseline-run <run-dir>`, and optional `--exercise-dir <dir>`.
- **READS:** `prompt-runner.toml` optimization config when present
  - **BECAUSE:** The optimize command should prefer repo-local defaults for model and duration policy.
- **CONTAINS:** `--profile`
  - **SYNOPSIS:** Name of one configured optimization profile such as `quick`, `balanced`, or `deep`.
  - **BECAUSE:** Most optimization runs should choose a curated candidate set rather than spelling out every model-duration pair on the command line.
- **CONTAINS:** `--candidate`
  - **SYNOPSIS:** One candidate model-setting pair that supplements or overrides the configured profile.
  - **BECAUSE:** The config file should handle normal cases, but operators still need a targeted override path for experiments.
- **CONTAINS:** `--baseline-run`
  - **SYNOPSIS:** Existing successful run directory for the unmodified source file.
  - **BECAUSE:** The user explicitly wants optimization to reuse a prior run when available.
- **CONTAINS:** `--exercise-dir`
  - **SYNOPSIS:** Explicit root directory for the optimization exercise.
  - **BECAUSE:** The optimize flow owns more than one run and needs one stable container for its derived artifacts.

**ENTITY: ENTITY-1A** `OptimizationCatalog`
- **SYNOPSIS:** Configuration-owned catalog of durations, models, and named profiles used by `prompt-runner optimize`.
- **FIELD:** `durations`
  - **SYNOPSIS:** Mapping from stable duration names such as `low`, `medium`, `high`, and `xhigh` to concrete effort settings.
  - **BECAUSE:** Duration names should be reusable across models and profiles.
- **FIELD:** `duration_aliases`
  - **SYNOPSIS:** Compatibility aliases such as `max -> xhigh`.
  - **BECAUSE:** Existing local terminology should remain accepted even when the canonical stored name differs.
- **FIELD:** `models`
  - **SYNOPSIS:** Named model records containing model id plus allowed and recommended durations.
  - **BECAUSE:** Sensible effort choices depend on the model rather than on one global list.
- **FIELD:** `profiles`
  - **SYNOPSIS:** Named optimization profiles that expand to an ordered set of model-duration candidates.
  - **BECAUSE:** Most runs should choose from a small curated search space instead of a raw cartesian product.
- **FIELD:** `default_profile`
  - **SYNOPSIS:** Profile name used when the user does not supply `--profile` or `--candidate`.
  - **BECAUSE:** The common case should run with one stable recommended search set.

**ENTITY: ENTITY-1B** `DurationDefinition`
- **SYNOPSIS:** One named optimization duration defined in config.
- **FIELD:** `name`
  - **SYNOPSIS:** Stable symbolic key such as `low`, `medium`, `high`, or `xhigh`.
  - **BECAUSE:** Profiles and models should reference durations by one shared name.
- **FIELD:** `effort`
  - **SYNOPSIS:** Concrete prompt-runner effort string emitted onto candidate prompts.
  - **BECAUSE:** The optimizer ultimately drives the existing `[EFFORT:...]` contract.
- **FIELD:** `rank`
  - **SYNOPSIS:** Monotonic ordering hint used when presenting or sorting durations.
  - **BECAUSE:** Config should carry one deterministic low-to-high ordering without hardcoding it elsewhere.
- **FIELD:** `experimental`
  - **SYNOPSIS:** Whether the duration should be excluded from conservative default profiles.
  - **BECAUSE:** Very expensive efforts such as `xhigh` should remain possible without becoming part of the default search set.

**ENTITY: ENTITY-1C** `OptimizationProfile`
- **SYNOPSIS:** Named configured search set for one optimization run.
- **FIELD:** `name`
  - **SYNOPSIS:** Stable profile key such as `quick`, `balanced`, or `deep`.
  - **BECAUSE:** Operators need concise reusable names for common search strategies.
- **FIELD:** `entries`
  - **SYNOPSIS:** Ordered list of model references plus the durations selected for each model.
  - **BECAUSE:** The useful search shape is not one raw full matrix; it is one curated list of combinations.
- **FIELD:** `include_baseline_effective`
  - **SYNOPSIS:** Whether the baseline-effective setting is injected in addition to the listed entries.
  - **BECAUSE:** The optimizer should preserve current behavior as a candidate unless explicitly disabled for a special experiment.

**ENTITY: ENTITY-1** `OptimizationExercise`
- **SYNOPSIS:** One runner-owned optimization campaign for one source prompt file.
- **FIELD:** `source_prompt_file`
  - **SYNOPSIS:** The original prompt-runner file being optimized.
  - **BECAUSE:** The exercise needs one authoritative workflow definition.
- **FIELD:** `exercise_root`
  - **SYNOPSIS:** Root directory that contains the baseline reference, synthesized prompt file, optimization run, optimized output file, and report artifacts.
  - **BECAUSE:** The optimize flow should keep its own derived state separate from ordinary runs.
- **FIELD:** `baseline_run_dir`
  - **SYNOPSIS:** Successful baseline run used as the accepted reference for the exercise.
  - **BECAUSE:** The optimization result needs one concrete before-state and benchmark run.
- **FIELD:** `candidate_settings`
  - **SYNOPSIS:** De-duplicated ordered list of model and effort combinations considered by the optimization run.
  - **BECAUSE:** The synthesizer and later report need one stable search-space definition.
- **FIELD:** `optimization_prompt_file`
  - **SYNOPSIS:** Synthesized prompt-runner file that turns optimizable prompts into selection forks.
  - **BECAUSE:** The optimize mode still executes through normal prompt-runner syntax rather than through a second execution engine.
- **FIELD:** `optimization_run_dir`
  - **SYNOPSIS:** Run directory for executing the synthesized optimization prompt file.
  - **BECAUSE:** The optimization workflow is a real prompt-runner run and needs its own worktree and `.run-files` state.
- **FIELD:** `optimized_prompt_file`
  - **SYNOPSIS:** Final derived prompt file with the selected settings materialized as normal prompt headings.
  - **BECAUSE:** The end product of optimization is a reusable prompt file, not only a forensic run directory.

**ENTITY: ENTITY-2** `OptimizationCandidate`
- **SYNOPSIS:** One model-setting option evaluated for an optimizable prompt.
- **FIELD:** `variant_name`
  - **SYNOPSIS:** Stable selection-fork variant key such as `baseline`, `cand-01`, or `cand-02`.
  - **BECAUSE:** The selection machinery needs one deterministic identifier per candidate.
- **FIELD:** `model`
  - **SYNOPSIS:** Effective model name for the candidate.
  - **BECAUSE:** Model choice is one of the requested optimization dimensions.
- **FIELD:** `effort`
  - **SYNOPSIS:** Effective effort value for the candidate, or the inherited default when the candidate leaves effort unset.
  - **BECAUSE:** Thinking duration is the other requested optimization dimension.
- **FIELD:** `origin`
  - **SYNOPSIS:** Whether the candidate came from the CLI search list or from the baseline-effective setting.
  - **BECAUSE:** Reports should distinguish explicitly requested experiments from the preserved current behavior.
- **FIELD:** `profile_source`
  - **SYNOPSIS:** Name of the config profile that contributed the candidate, if any.
  - **BECAUSE:** The final report should show which configured search set produced the winning option.

**ENTITY: ENTITY-3** `PromptCandidateMetrics`
- **SYNOPSIS:** Deterministic metrics captured for one candidate's execution of one prompt.
- **FIELD:** `final_verdict`
  - **SYNOPSIS:** Final pass, revise, or escalate state after the candidate's generator and judge loop.
  - **BECAUSE:** Convergence quality is the primary optimization criterion.
- **FIELD:** `iterations_used`
  - **SYNOPSIS:** Number of generator and judge iterations consumed by the candidate for the prompt.
  - **BECAUSE:** A setting that passes in fewer loops converges more efficiently than one that needs more repair cycles.
- **FIELD:** `wall_time_seconds`
  - **SYNOPSIS:** Prompt-local elapsed wall time from candidate prompt start through final verdict.
  - **BECAUSE:** The user wants shortest time taken as one of the ranking dimensions.
- **FIELD:** `input_tokens`
  - **SYNOPSIS:** Sum of recorded input tokens across all generator and judge calls for the prompt.
  - **BECAUSE:** Prompt-local token use must be comparable across candidates.
- **FIELD:** `output_tokens`
  - **SYNOPSIS:** Sum of recorded output tokens across all generator and judge calls for the prompt.
  - **BECAUSE:** Total prompt cost depends on both prompt and response volume.
- **FIELD:** `total_tokens`
  - **SYNOPSIS:** Sum of all token categories used for prompt-level ranking.
  - **BECAUSE:** The user asked for the lowest tokens consumed, not only the lowest input volume.
- **FIELD:** `summary_excerpt`
  - **SYNOPSIS:** Compact text summary of what the candidate run reported for the prompt.
  - **BECAUSE:** The selector still needs a human-readable description alongside the numeric scorecard.

**ENTITY: ENTITY-4** `PromptOptimizationDecision`
- **SYNOPSIS:** Persisted outcome of model selection for one original prompt.
- **FIELD:** `prompt_index`
  - **SYNOPSIS:** Original prompt index in the source file.
  - **BECAUSE:** The optimized file must map the winner back onto one exact prompt heading.
- **FIELD:** `selected_candidate`
  - **SYNOPSIS:** Winning candidate variant key.
  - **BECAUSE:** The collapse step needs one exact source of truth for the chosen setting.
- **FIELD:** `selected_model`
  - **SYNOPSIS:** Effective model to materialize on the optimized prompt heading.
  - **BECAUSE:** The final output file must contain explicit chosen settings.
- **FIELD:** `selected_effort`
  - **SYNOPSIS:** Effective effort to materialize on the optimized prompt heading.
  - **BECAUSE:** The final output file must freeze the chosen thinking duration as well as the model.
- **FIELD:** `selector_rationale`
  - **SYNOPSIS:** Human-readable explanation for why the winner was chosen.
  - **BECAUSE:** Operators need more than a raw variant key when reviewing the optimization result.
- **FIELD:** `scorecard_path`
  - **SYNOPSIS:** Path to the deterministic scorecard for all candidates on this prompt.
  - **BECAUSE:** The rationale should remain anchored to concrete metrics rather than to free-form selector memory.

**PROCESS: PROCESS-1** `Obtain the baseline run`
- **SYNOPSIS:** The optimize command first resolves a trusted baseline by validating a caller-supplied run directory or by launching a fresh normal run of the original prompt file.
- **READS:** source prompt file digest and effective run configuration
  - **BECAUSE:** The optimizer must verify that the baseline really belongs to the file and backend being optimized.
- **WRITES:** `baseline-reference.json`
  - **BECAUSE:** The exercise root should record exactly which baseline was used, even when the baseline run itself lives elsewhere.
- **WRITES:** `baseline-summary.md`
  - **BECAUSE:** The exercise needs one compact human-readable record of the accepted reference run.

**PROCESS: PROCESS-1A** `Resolve optimization config and candidate set`
- **SYNOPSIS:** Before baseline validation or synthesis, the optimize command resolves the effective optimization catalog from `prompt-runner.toml`, picks one profile, expands its model-duration entries, applies CLI overrides, validates each combination, and de-duplicates the final candidate list.
- **READS:** `[optimize]`, `[optimize.durations]`, `[optimize.duration_aliases]`, `[optimize.models]`, and `[optimize.profiles]` tables
  - **BECAUSE:** The optimizer needs one deterministic source of truth for model and duration policy.
- **CONTAINS:** `Prefer configured profile over raw CLI list`
  - **SYNOPSIS:** When no explicit `--candidate` flags are provided, the optimizer uses the configured profile or the configured default profile.
  - **BECAUSE:** Curated profiles should be the normal operator path.
- **CONTAINS:** `Apply CLI candidates as targeted overrides`
  - **SYNOPSIS:** Explicit CLI candidates append to or replace the configured profile according to a documented precedence rule.
  - **BECAUSE:** Operators still need a quick one-off experiment path without editing config.
- **CONTAINS:** `Expand durations per model`
  - **SYNOPSIS:** Profile entries refer to one model plus a list of duration names, and the optimizer expands them into concrete candidates only after validating them against that model's allowed durations.
  - **BECAUSE:** Durations should be declared once and checked against model-specific policy before execution.
- **CONTAINS:** `De-duplicate by effective model and effort`
  - **SYNOPSIS:** Candidates that resolve to the same effective model and effort pair collapse to one canonical entry.
  - **BECAUSE:** Profiles, aliases, and baseline injection should not create duplicate variant branches.

**PROCESS: PROCESS-2** `Synthesize the optimization prompt file`
- **SYNOPSIS:** Prompt-runner deterministically transforms the original parsed prompt file into a new prompt-runner file that uses one `[VARIANTS] [SELECT]` fork for each optimizable prompt and copies non-optimizable prompts unchanged.
- **READS:** parsed `PromptPair` items, file-level `### Module`, and the ordered candidate setting list
  - **BECAUSE:** The synthesizer must preserve the original workflow semantics while inserting model-setting variants.
- **CONTAINS:** one generated `## Prompt N: <title> [VARIANTS] [SELECT]` heading per optimizable prompt
  - **BECAUSE:** Existing selection-fork execution is the runner mechanism that already compares variants and promotes one winner before continuing.
- **CONTAINS:** one `### Variant <candidate>` block per candidate setting
  - **BECAUSE:** Each candidate needs its own isolated execution branch with its own model and effort settings.
- **CONTAINS:** the original prompt pair's metadata, generation prompt, validation prompt, deterministic validation block, and retry prompt inside every candidate variant
  - **BECAUSE:** The optimizer is changing model settings, not rewriting the task itself.
- **CONTAINS:** one generated selector prompt and selector retry prompt per optimization fork
  - **BECAUSE:** The selection step must be authored by the runner so every prompt uses the same ranking policy.
- **WRITES:** `optimization.prompt.md`
  - **BECAUSE:** The derived workflow should remain inspectable and rerunnable as a normal prompt-runner file.

**PROCESS: PROCESS-3** `Build a deterministic candidate scorecard`
- **SYNOPSIS:** After each candidate variant finishes, prompt-runner aggregates prompt-local verdict, iteration, wall-time, and token data into a deterministic scorecard before running the selector.
- **READS:** backend call telemetry, prompt-local iteration history, and child run summaries
  - **BECAUSE:** Candidate ranking must come from actual execution data rather than from selector inference.
- **WRITES:** one `candidate-scorecard.json` per optimization fork
  - **BECAUSE:** The optimization result needs one machine-readable record of the metrics that drove selection.
- **WRITES:** one selector dossier markdown file per optimization fork
  - **BECAUSE:** The selector still needs a human-readable comparison bundle that pairs metrics with candidate summaries.
- **CONTAINS:** convergence tier, iterations used, wall time, input tokens, output tokens, total tokens, and changed-file summary for each candidate
  - **BECAUSE:** The selection policy depends on both acceptability and efficiency, and the comparison data should be normalized across candidates.

**PROCESS: PROCESS-4** `Execute the synthesized optimization workflow`
- **SYNOPSIS:** The optimize mode launches a normal prompt-runner run against the synthesized optimization file and reuses the current selection-fork behavior to isolate candidate runs, select a winner, promote it, and continue to the next prompt.
- **USES:** existing selection-fork execution in `run_pipeline`
  - **BECAUSE:** Prompt-runner already has the control flow needed to run variants, pick one winner, and continue the parent workflow.
- **USES:** existing child-run isolation under `.selection/variants/<variant>/workspace/`
  - **BECAUSE:** Candidate settings must be compared from the same prompt-local starting state without leaking partial results into the parent worktree.
- **WRITES:** prompt-local optimization decisions under the optimization run's `.run-files` tree
  - **BECAUSE:** The collapse step needs durable per-prompt winner records after the run completes.

**PROCESS: PROCESS-5** `Emit the optimized prompt file and exercise report`
- **SYNOPSIS:** After the optimization run completes successfully, prompt-runner collapses each optimization fork back into one normal prompt heading with the selected model and effort directives and writes a report comparing the baseline run and the optimized run.
- **READS:** optimization-run selected-variant records, candidate scorecards, and the original parsed prompt file
  - **BECAUSE:** The collapse step must preserve the original prompt content while inserting the chosen settings.
- **WRITES:** `optimized.prompt.md`
  - **BECAUSE:** The derived prompt file is the main durable product of the optimization exercise.
- **WRITES:** `report.md`
  - **BECAUSE:** Operators need one concise before-and-after summary that shows which settings won and what the optimization changed in time and token terms.
- **CONTAINS:** overall baseline versus optimized run wall time and token totals plus per-prompt selected settings
  - **BECAUSE:** The user asked for model choices to be judged by convergence, time, and token use, and the final report should expose that outcome directly.

**RULE: RULE-1** `Only judge-bearing non-interactive prompts are transformed`
- **SYNOPSIS:** The synthesizer SHALL convert only non-interactive prompts with a non-empty validation prompt into optimization forks, and it SHALL copy validator-less prompts unchanged.
  - **BECAUSE:** The feature is defined around generator and judge convergence, and prompts without a judge do not provide the acceptability signal needed for fair ranking.

**RULE: RULE-2** `The first version rejects existing forks and interactive prompts`
- **SYNOPSIS:** The initial optimize mode SHALL fail fast when the source file already contains `[VARIANTS]`, `[SELECT]`, or `[interactive]` prompts.
  - **BECAUSE:** Nesting model-setting synthesis inside existing forks or interactive turns would multiply execution shapes and make prompt-local candidate comparison much harder to reason about.

**RULE: RULE-2A** `The first version supports one conservative canonical duration set`
- **SYNOPSIS:** The initial optimize config SHALL recognize `low`, `medium`, `high`, and `xhigh` as canonical duration names and SHALL accept `max` only as an alias for `xhigh`.
  - **BECAUSE:** That maps cleanly onto the current prompt-runner and Codex integration without introducing extra model-family-specific values such as `minimal` or `none` into the first implementation.

**RULE: RULE-2B** `Default profiles stay small and model-aware`
- **SYNOPSIS:** The shipped config SHOULD provide `quick`, `balanced`, and `deep` profiles, with `balanced` as the default, and those profiles SHOULD enumerate only model-duration combinations that are sensible for the specific model rather than all allowed durations.
  - **BECAUSE:** A compact curated search set is much more practical than a large full matrix and better matches the user's request to pick durations that make sense according to the model.

**RULE: RULE-2C** `Recommended default profiles`
- **SYNOPSIS:** The initial shipped profiles SHOULD encode one small recommended search set for `quick`, `balanced`, and `deep`.
  - **BECAUSE:** Those defaults cover a useful spread of cost, latency, and coding strength without making the search explosion the default behavior.
- **CONTAINS:** `quick`
  - **SYNOPSIS:** `gpt-5.4-mini` at `low` and `medium`, plus `gpt-5.3-codex` at `medium`.
  - **BECAUSE:** The quickest profile should stay very small and cost-sensitive.
- **CONTAINS:** `balanced`
  - **SYNOPSIS:** `gpt-5.4-mini` at `low` and `medium`, plus `gpt-5.3-codex` at `medium`, plus `gpt-5.4` and `gpt-5.5` at `medium`.
  - **BECAUSE:** The default profile should sample the stronger frontier options without growing too large.
- **CONTAINS:** `deep`
  - **SYNOPSIS:** `gpt-5.4-mini` at `low` and `medium`, plus `gpt-5.3-codex` at `medium` and `high`, plus `gpt-5.4` and `gpt-5.5` at `medium` and `high`.
  - **BECAUSE:** The deeper profile should widen the reasoning search only for the stronger coding models.

**RULE: RULE-3** `The baseline-effective setting is always in the candidate set`
- **SYNOPSIS:** Every optimizable prompt SHALL include one implicit candidate that reproduces the effective baseline model and effort for that prompt, de-duplicated against the explicit CLI candidates.
  - **BECAUSE:** Optimization must be able to keep the current setting when the proposed alternatives are slower, more expensive, or fail to converge.

**RULE: RULE-3A** `Recommended durations are preferred over allowed durations`
- **SYNOPSIS:** When a configured profile references a model without naming explicit durations, the optimizer SHALL expand that model using its `recommended_durations` list, not its full `allowed_durations` list.
  - **BECAUSE:** Model definitions should be able to express a broad valid surface while still steering the default search toward the smaller subset that usually makes sense.

**RULE: RULE-4** `One optimization exercise uses one backend`
- **SYNOPSIS:** The baseline run and every candidate in one optimization exercise SHALL use the same backend.
  - **BECAUSE:** Model names, effort semantics, and token telemetry are backend-specific, so a mixed-backend score would not be comparable.

**RULE: RULE-4A** `The initial shipped model catalog is conservative`
  - **SYNOPSIS:** The initial default config SHOULD include `gpt-5.4-mini`, `gpt-5.3-codex`, `gpt-5.4`, and `gpt-5.5`, and SHOULD NOT include `gpt-5.4-nano` in the default profiles.
  - **BECAUSE:** The feature is optimizing generator and judge convergence for coding workflows, and the smallest low-cost model is better left as an opt-in experiment rather than part of the default search set.

**RULE: RULE-5** `Optimization metrics are runner-recorded, not selector-invented`
- **SYNOPSIS:** Wall time and token counts used for ranking SHALL come from runner-owned execution telemetry and scorecards, not from selector estimates in natural language.
  - **BECAUSE:** The selector should compare real execution cost rather than hallucinated or rounded numbers.

**RULE: RULE-6** `A winner must have actually passed`
- **SYNOPSIS:** The selector may choose only a candidate whose prompt-local final verdict is `pass`; if no candidate passes, the optimization fork SHALL escalate and halt the exercise.
  - **BECAUSE:** The optimize mode should never materialize a prompt setting that failed to converge acceptably.

**RULE: RULE-7** `The source prompt file is never rewritten in place`
- **SYNOPSIS:** The optimize command SHALL treat the original prompt file as immutable input and SHALL write the synthesized optimization file and optimized output file under the exercise root.
  - **BECAUSE:** The source file is both the benchmark input and the audit reference for the optimization result.

**FILE: FILE-1** `Optimization exercise layout`
- **SYNOPSIS:** One optimize command SHALL write its derived artifacts under a dedicated exercise root separate from ordinary run directories.
- **PRODUCES:** `.prompt-runner/optimizations/<timestamp>-<source-stem>/`
- **CONTAINS:** `source.prompt.md`
  - **BECAUSE:** The exercise should preserve the exact source file it optimized.
- **CONTAINS:** `baseline-reference.json`
  - **BECAUSE:** The exercise must record which baseline run it trusted.
- **CONTAINS:** `baseline-summary.md`
  - **BECAUSE:** A quick accepted-run summary is useful even when the real baseline run directory lives elsewhere.
- **CONTAINS:** `candidates.json`
  - **BECAUSE:** The search-space definition should be inspectable without re-parsing CLI history.
- **CONTAINS:** `optimization.prompt.md`
  - **BECAUSE:** The synthesized workflow itself is part of the exercise evidence.
- **CONTAINS:** `optimization-run/`
  - **BECAUSE:** The synthesized file executes as a real prompt-runner run with its own worktree and `.run-files` state.
- **CONTAINS:** `optimized.prompt.md`
  - **BECAUSE:** The durable output of the exercise is a normal prompt-runner file with explicit chosen settings.
- **CONTAINS:** `report.md`
  - **BECAUSE:** The exercise should finish with one concise artifact that explains the selected settings and their measured outcome.

**FILE: FILE-2** `Optimization config schema`
- **SYNOPSIS:** `prompt-runner.toml` SHALL carry one repo-local optimization policy section that defines durations, models, aliases, and named profiles.
- **PRODUCES:** `[optimize]`
- **CONTAINS:** `backend`
  - **BECAUSE:** Optimization policy is backend-specific.
- **CONTAINS:** `default_profile`
  - **BECAUSE:** The optimizer needs one stable search set for the no-extra-flags case.
- **CONTAINS:** `include_baseline_effective`
  - **BECAUSE:** Baseline inclusion should be configurable but normally on.
- **PRODUCES:** `[optimize.durations.<name>]`
- **CONTAINS:** `effort`
  - **BECAUSE:** Duration names must resolve to concrete prompt-runner effort values.
- **CONTAINS:** `rank`
  - **BECAUSE:** Config should define one deterministic ordering from cheaper to more expensive durations.
- **CONTAINS:** `experimental`
  - **BECAUSE:** Some durations should stay out of conservative profiles.
- **PRODUCES:** `[optimize.duration_aliases]`
  - **BECAUSE:** Existing local aliases such as `max` should remain accepted.
- **PRODUCES:** `[optimize.models.<name>]`
- **CONTAINS:** `model`
  - **BECAUSE:** Configured model entries need one concrete backend model id.
- **CONTAINS:** `allowed_durations`
  - **BECAUSE:** Not every duration is valid or sensible for every model.
- **CONTAINS:** `recommended_durations`
  - **BECAUSE:** Default profiles should prefer a smaller curated subset.
- **PRODUCES:** `[optimize.profiles.<name>]`
- **CONTAINS:** `entries`
  - **BECAUSE:** Profiles need one concise way to name model-duration search groups.

**MODIFICATION: MOD-1** `CLI entrypoint adds optimize mode`
- **SYNOPSIS:** `tools/prompt-runner/src/prompt_runner/__main__.py` SHALL add an `optimize` subcommand that parses profile selection, candidate overrides, baseline reuse flags, and exercise-root options and then invokes the optimization orchestrator.
- **DEPENDS-ON:** `REQ-1`
  - **BECAUSE:** The feature boundary is a new CLI mode, not a hidden branch inside `run`.

**MODIFICATION: MOD-2** `Add an optimization orchestrator module`
- **SYNOPSIS:** Prompt-runner SHALL add a new module such as `tools/prompt-runner/src/prompt_runner/optimizer.py` that owns config resolution, baseline resolution, prompt synthesis, candidate de-duplication, output collapse, and report writing.
- **DEPENDS-ON:** `PROCESS-1`
  - **BECAUSE:** The optimize flow is a runner-owned orchestration feature whose logic is distinct from parsing and from one normal run.
- **DEPENDS-ON:** `PROCESS-1A`
  - **BECAUSE:** Config-driven search expansion belongs in the optimization controller.
- **DEPENDS-ON:** `PROCESS-2`
  - **BECAUSE:** Deterministic prompt-file synthesis belongs with the optimization controller, not with the generic parser.
- **DEPENDS-ON:** `PROCESS-5`
  - **BECAUSE:** The final output file and report are exercise-level artifacts rather than prompt-local runner artifacts.

**MODIFICATION: MOD-2A** `Extend prompt-runner config parsing`
- **SYNOPSIS:** `tools/prompt-runner/src/prompt_runner/config.py` SHALL extend the current config loader to parse and validate the `[optimize]` schema in addition to `[run]`.
- **DEPENDS-ON:** `FILE-2`
  - **BECAUSE:** The optimizer needs one typed config surface instead of ad hoc TOML reads scattered across the codebase.

**MODIFICATION: MOD-3** `Runner persists prompt-local optimization telemetry`
- **SYNOPSIS:** `tools/prompt-runner/src/prompt_runner/runner.py` SHALL persist prompt-local timing, iteration, and token metrics for normal prompts and selection variants and SHALL extend the selector dossier builder to consume the resulting scorecards.
- **DEPENDS-ON:** `PROCESS-3`
  - **BECAUSE:** The optimization selector needs prompt-local metrics that the current runner does not yet store in a reusable structured form.

**MODIFICATION: MOD-4** `Backend adapters expose usage telemetry`
- **SYNOPSIS:** `tools/prompt-runner/src/prompt_runner/codex_client.py` and `tools/prompt-runner/src/prompt_runner/claude_client.py` SHALL extend their response model so the runner can read prompt-local token and duration telemetry from backend-native events when that data is available.
- **DEPENDS-ON:** `RULE-5`
  - **BECAUSE:** Prompt-local token ranking cannot be deterministic until the backend adapters surface the underlying usage data to the runner.

**PROCESS: PROCESS-6** `Verification scope`
- **SYNOPSIS:** The implementation should not ship without CLI, synthesis, telemetry, selector, and collapse coverage for the optimize mode.
- **CONTAINS:** `Config parsing accepts the optimize duration, model, alias, and profile tables and rejects malformed values`
  - **BECAUSE:** The configuration schema becomes part of the public contract.
- **CONTAINS:** `Profiles expand to the intended model-duration set and reject durations outside each model's allowed set`
  - **BECAUSE:** Model-aware duration validation is one of the main design goals of the config layer.
- **CONTAINS:** `CLI accepts candidate lists, baseline reuse flags, and exercise-root flags`
  - **BECAUSE:** The search space and baseline reuse are the public entry contract for the feature.
- **CONTAINS:** `CLI profile selection uses the configured default profile when no explicit candidates are provided`
  - **BECAUSE:** The design expects curated profiles to be the common path.
- **CONTAINS:** `Baseline reuse rejects digest or backend mismatches and accepts a completed matching run`
  - **BECAUSE:** Baseline trust is central to the feature and must be enforced deterministically.
- **CONTAINS:** `Synthesizer converts eligible prompts into selection forks and copies validator-less prompts unchanged`
  - **BECAUSE:** The generated optimization file is the core intermediate artifact of the design.
- **CONTAINS:** `Baseline-effective candidate is injected once and de-duplicated against explicit CLI candidates`
  - **BECAUSE:** Preserving current behavior as a selectable option is a hard safety rule.
- **CONTAINS:** `Prompt-local scorecards record verdict, iterations, wall time, and tokens for each candidate`
  - **BECAUSE:** Candidate ranking depends on those exact metrics.
- **CONTAINS:** `Selector may choose only a passing candidate and halts when all candidates fail`
  - **BECAUSE:** The optimize mode must not emit a broken setting.
- **CONTAINS:** `Optimized output file collapses each winning fork back into one normal prompt heading with explicit [MODEL] and [EFFORT] directives`
  - **BECAUSE:** The final deliverable is a standard prompt-runner file, not a permanently selectionized one.
- **CONTAINS:** `Exercise report shows baseline versus optimized totals plus per-prompt winners`
  - **BECAUSE:** The user wants the chosen model settings to be justified by convergence, time, and token evidence.
