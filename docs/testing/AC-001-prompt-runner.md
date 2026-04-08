# AC-001 — Prompt Runner Implementation Acceptance Criteria

*Runnable verification that the Prompt Runner implementation matches the design at `docs/design/components/CD-001-prompt-runner.md`.*

## 1. Purpose and scope

This document enumerates the acceptance criteria for the **implementation** of the Prompt Runner. Each criterion is a boolean check with an explicit verification method — a test name, a shell command, or a manual smoke test.

These criteria sit one layer below the design acceptance criteria. The separation is:

- **Design ACs** (Section 14 of the parent design doc) verify that the design-as-written captures every user requirement. Checkable by reading the spec.
- **Implementation ACs** (this document) verify that the built code matches the design. Checkable by running the code.

An implementation AC may only be evaluated after the corresponding design AC has passed — you cannot verify that the code matches the design if the design itself is incomplete or contradictory.

## 2. Parent design

Design spec: `docs/design/components/CD-001-prompt-runner.md`

Every AC in this document traces back to:

- A **REQ-NN** identifier (a user requirement extracted from the brainstorming conversation — enumerated in Section 14.1 of the design doc), and
- One or more **design sections** that specify the behaviour being verified.

If a requirement changes, update the corresponding AC(s) here and the design section(s) they point at, in lockstep.

## 3. Traceability legend

Each AC row uses the following fields:

- **AC-NN** — unique identifier, sequential.
- **Traces to** — the REQ and the design sections the AC derives from.
- **Check** — one sentence stating what must be true.
- **Verification** — the exact test function, command, or manual procedure that decides pass/fail.

## 4. Parsing and the parse subcommand

### Maps to the step-1 deliverable (REQ-6: dummy script that parses the file and prints prompts with their validation prompts).

| AC | Traces to | Check | Verification |
|---|---|---|---|
| **AC-01** | REQ-1, REQ-2 → §3, §6.1 | The parser returns a list of *PromptPair* objects, each carrying an *index*, *title*, *generation_prompt*, *validation_prompt*, and three line-number fields (*heading_line*, *generation_line*, *validation_line*). | *test_parses_minimal_two_prompt_file* in *tests/cli/prompt_runner/test_parser.py* — asserts the returned list has the expected length, and each pair has every field populated with the expected value. |
| **AC-02** | REQ-6 → §5, §12 step 3 | The *parse* subcommand runs against *ai-development-methodology-prompts_1.md* and prints six prompt pairs with their positional indices (1..6), titles, heading line numbers, and first few lines of each body. Exit code 0. No Claude calls are made. | Command: *python -m prompt_runner parse /Users/martinbechard/Downloads/ai-development-methodology-prompts_1.md*. Expected stdout contains "Prompt 1" through "Prompt 6". Expected exit code 0. No network or subprocess activity. |
| **AC-03** | REQ-13 → §1, §2 | The runner has no hardcoded content-specific references. | Shell: *grep -Eri "phase processing unit\|methodology\|traceability graph\|simulation framework" src/cli/prompt_runner/* returns no matches. |
| **AC-04** | REQ-14 → §3, §6.2 | The parser accepts files with flexible subsection labels and non-standard fence language tags. | *test_accepts_arbitrary_subsection_headers*, *test_accepts_no_subsection_headers*, and *test_accepts_language_tagged_fences* in *test_parser.py*. |
| **AC-05** | REQ-19 → §3 invariant 1, §6.4 | The heading regex accepts all five documented forms: *## Prompt 1: Title*, *## Prompt: Title*, *## Prompt Title*, *## Prompt 3 — Title*, *## Prompt*. | Five dedicated test cases in *test_parser.py*: *test_accepts_numbered_heading*, *test_accepts_unnumbered_heading_with_colon*, *test_accepts_unnumbered_heading_without_colon*, *test_accepts_em_dash_separator*, *test_empty_title_becomes_untitled*. All pass. |
| **AC-06** | REQ-19 → §3 indexing paragraph | The parser uses positional indexing and ignores any number present in the heading. | *test_positional_index_ignores_heading_number* — fixture with *## Prompt 5: A* then *## Prompt 10: B* yields pairs with index 1 and 2. |

## 5. Error handling (parser errors)

### Maps to REQ-15 (friendly error messages) and REQ-16 (no jargon).

| AC | Traces to | Check | Verification |
|---|---|---|---|
| **AC-07** | REQ-15 → §6.3 | Every parser error identifies the prompt by positional index and title, cites the heading line number, cites any block line numbers that were known at the point of failure, and ends with a concrete repair instruction. | Five dedicated tests in *test_parser.py*: *test_error_no_blocks*, *test_error_missing_validation*, *test_error_unclosed_generation*, *test_error_unclosed_validation*, *test_error_extra_block*. Each asserts the error message contains the prompt's title, the heading line number, at least one other line number, and the word *"Add"* or *"remove"* (the repair verb). |
| **AC-08** | REQ-15 → §6.3 | Every *ParseError* carries a stable error ID (one of *E-NO-BLOCKS*, *E-MISSING-VALIDATION*, *E-UNCLOSED-GENERATION*, *E-UNCLOSED-VALIDATION*, *E-EXTRA-BLOCK*). | *test_error_ids_are_stable* — asserts each *ParseError* exposes a *.error_id* attribute with one of the five documented values. |
| **AC-09** | REQ-15 → §6.3 E-MISSING-VALIDATION, E-UNCLOSED-GENERATION, E-UNCLOSED-VALIDATION | Error messages that concern a specific role say *"generation prompt"* or *"validation prompt"*, so the user knows which of the two to fix. | *test_error_messages_name_the_role* — for E-MISSING-VALIDATION, E-UNCLOSED-GENERATION, and E-UNCLOSED-VALIDATION fixtures, the error message contains the exact string *"generation prompt"* or *"validation prompt"* as appropriate. |
| **AC-10** | REQ-16 → §6.3 | No user-facing error message uses the bare word *fence* without qualification (*fenced code block*, *triple backticks*, etc. are acceptable). | *test_no_bare_fence_jargon* — for every fixture that triggers a parser error, the error message is searched with a regex *\bfence\b* and must match zero times. |

## 6. Runner engine and revision loop

### Maps to REQ-3, REQ-4, REQ-5, REQ-7 (run prompts, run validations, loop on feedback, one-shot CLI calls).

| AC | Traces to | Check | Verification |
|---|---|---|---|
| **AC-11** | REQ-3, REQ-4 → §9.3 | For each iteration of each prompt, the runner makes exactly one generator call and exactly one judge call, in that order, through the *ClaudeClient* interface. | *test_single_prompt_passes_first_try* — *FakeClaudeClient* records exactly two calls per prompt iteration (generator then judge). |
| **AC-12** | REQ-5 → §9.3, §9.4 | When the judge returns *VERDICT: revise*, the runner invokes the generator again with a message built from the judge's output, then invokes the judge again with the new artifact. | *test_single_prompt_passes_on_second_iteration* — judge returns revise then pass; runner records two generator calls and two judge calls; the second generator call's *prompt* field contains the first judge's output substring. |
| **AC-13** | REQ-5 → §9.1, §9.3 | The revision loop honours *RunConfig.max_iterations* (default 3). When the cap is reached with the verdict still *revise*, the final verdict becomes *escalate*. | *test_escalation_on_max_iterations* — judge always returns revise with *max_iterations=3*; runner records exactly 3 iterations and the final verdict is *ESCALATE*. |
| **AC-14** | REQ-5 → §11.1 | When a judge returns *VERDICT: escalate* directly, the pipeline halts immediately. | *test_direct_escalation* — judge returns *VERDICT: escalate* on iteration 1; runner records exactly one generator call and one judge call. |
| **AC-15** | REQ-7 → §7.1 | Every Claude invocation is a distinct *subprocess.Popen* that ends before the next call starts. No long-running subprocess persists across calls. | *test_each_call_is_a_distinct_subprocess* — monkeypatched *Popen* records each instantiation; after a 3-iteration run, the number of Popen instances equals the number of ClaudeCalls, and each instance's *wait()* returned before the next was created. |

## 7. Session handling

### Maps to REQ-8 (no contamination), REQ-9 (continuity across iterations within a role), REQ-10 (fresh sessions across prompts).

| AC | Traces to | Check | Verification |
|---|---|---|---|
| **AC-16** | REQ-8 → §9.3 | For every call recorded by the fake client, the generator's session ID is never equal to the judge's session ID. | *test_session_id_naming* — asserts for every recorded (gen, jud) pair, *gen.session_id != jud.session_id*. |
| **AC-17** | REQ-9 → §9.3, §7.1 | Iteration 1's Claude calls have *new_session=True* (triggering *--session-id*); all subsequent iterations' calls have *new_session=False* (triggering *--resume*). | *test_resume_flag_set_on_iterations_after_first* — asserts that for every prompt, iter-1's calls use *new_session=True* and iter-2+ use *new_session=False*, for both generator and judge. |
| **AC-18** | REQ-10 → §9.3 | Session IDs incorporate the prompt's positional index, so prompt N's sessions are distinct from prompt N-1's. | *test_session_id_naming* also asserts that *gen-prompt-1-...* and *gen-prompt-2-...* are distinct, and that session IDs match the pattern *(gen\|jud)-prompt-\d+-.\**. |
| **AC-19** | REQ-4 (prior outputs as context) → §9.4 *build_initial_generator_message* | The generator call for prompt N (N > 1) includes the approved artifact text of every prior prompt in its *prompt* field. | *test_prior_artifacts_injected_into_next_prompt* — a 2-prompt run where prompt 1 passes with artifact text *"ARTIFACT-ONE"*; assert that the generator call for prompt 2 has a *prompt* field containing *"ARTIFACT-ONE"*. |
| **AC-20** | REQ-4 → §5 *--only* flag, §9.2 | The *--only N* flag runs only prompt N and does not inject prior artifacts (because prior prompts were skipped). | *test_only_flag_runs_single_prompt* — three-pair file run with *only=2*; assert only prompt 2's calls are recorded; assert prompt 2's generator call does **not** contain any prior-artifact injection block. |

## 8. Streaming, logs, and error display

### Maps to REQ-20 (logs folder), REQ-21 (display last error), REQ-22 (stream output).

| AC | Traces to | Check | Verification |
|---|---|---|---|
| **AC-21** | REQ-20 → §7.1, §10 | Every *ClaudeCall* the runner constructs has a *stdout_log_path* and *stderr_log_path* rooted under *<run_dir>/logs/<prompt-slug>/*, and those paths include the iteration number and the role (*generator* or *judge*). | *test_log_paths_passed_to_every_call* — inspect the recorded calls from a fake-client run, assert every *stdout_log_path* matches *<run_dir>/logs/prompt-\d+-.\*/iter-\d+-(generator\|judge).stdout.log*. |
| **AC-22** | REQ-20 → §9.3 | The *logs/<prompt-slug>/* directory exists on disk before the first *claude_client.call()* is dispatched for that prompt, so the real client can open log files for append without ENOENT. | *test_logs_dir_created_before_first_call* — runner run with a fake client that asserts *os.path.isdir(call.stdout_log_path.parent)* at the moment of each call; the assertion must pass for every call. |
| **AC-23** | REQ-20 → §7.1 real implementation | After a successful real-client call, *stdout_log_path* contains the complete captured stdout, and *stderr_log_path* exists even if empty. | *test_real_client_writes_stdout_log*, *test_real_client_writes_stderr_log* in *tests/cli/prompt_runner/test_claude_client.py* — monkeypatched *Popen* emits scripted stdout/stderr; after the call returns, both log files are read from disk and compared byte-for-byte to the scripted content. |
| **AC-24** | REQ-22 → §7.1 real implementation, §7.4 | With a live *claude* binary, the model's response appears on the terminal as it is generated, not after the full response is assembled. | Manual smoke test: run *python -m prompt_runner run tests/cli/prompt_runner/fixtures/readme-example.md* against a live *claude* binary. Observe that model output appears incrementally on the terminal. No automated test — automating a timing-based streaming assertion has disproportionate complexity. |
| **AC-25** | REQ-22 → §7.1 implementation steps 4 (stderr thread) | A large (>64KB) model response does not deadlock the subprocess, proving concurrent stderr reading is working. | *test_real_client_concurrent_reading_no_deadlock* — monkeypatched *Popen* whose stdout and stderr each emit >64KB; the test must complete within a short wall-clock timeout (5 seconds). |
| **AC-26** | REQ-21 → §11.3 step 4 | On any halting exit (exit codes 1, 2, or 3), the runner prints a framed error block to stderr *after* any streamed output, consisting of three horizontal rule lines and the error ID and message between them. | *test_halt_prints_framed_error_block* — captured stderr after a forced-escalate run contains the three rule lines and the error ID. *test_error_block_is_last_stderr_output* asserts nothing is written to stderr after the closing rule line. |
| **AC-27** | REQ-21 → §11.4 | On a clean exit (exit code 0), the runner prints a framed success block to stdout containing the contents of *summary.txt*. | *test_success_prints_framed_block* — captured stdout after a run where every prompt passes contains three rule lines and the summary contents. |
| **AC-28** | REQ-20, REQ-21 → §11.3 item 1 | When a claude invocation fails mid-stream, whatever was captured on stdout before the failure is written to the corresponding *iter-NN-<role>.md* file before the error propagates. | *test_halt_on_claude_failure_writes_partial_md* — *FakeClaudeClient* raises *ClaudeInvocationError* with a partial *ClaudeResponse* whose stdout is *"PARTIAL-JUDGE-OUTPUT"*; assert that *iter-02-judge.md* exists on disk and contains that string after the pipeline halts. |

## 9. README companion

### Maps to REQ-17 (README for AIs to create prompts).

| AC | Traces to | Check | Verification |
|---|---|---|---|
| **AC-29** | REQ-17 → §13 | A companion README exists at the location assigned by *project-organiser* at write time. It covers the 11 content items listed in §13.3. | Manual review against the 11 numbered items in §13.3. A checklist test (*test_readme_has_required_sections*) greps the README for distinctive strings from each required item and fails if any are missing. |
| **AC-30** | REQ-17 → §13.4 | The README contains a worked example file that the parser can parse without error. | *test_readme_example_parses* — extracts the worked-example block from the README, writes it to a temp file, calls *parser.parse_file()*, asserts it returns the expected number of *PromptPair* objects. |
| **AC-31** | REQ-17 → §13.4 | The README lists every parser error ID from §6.3. | *test_error_ids_match_readme* — for each of the five *E-\** IDs from the parser's error catalogue, assert the README contains the literal ID. |
| **AC-32** | REQ-17 → §13.4 | The README is under 400 lines of markdown. | Shell: *wc -l <readme-path>* returns ≤ 400. |

## 10. Cross-cutting correctness

| AC | Traces to | Check | Verification |
|---|---|---|---|
| **AC-33** | REQ-18 → §1 title, §4 | The tool name is *prompt-runner*. No references to *methodology-runner* or *methodology_runner* exist in source code or documentation. | Shell: *grep -Eri "methodology[-_]runner\|Methodology Runner" src/ tests/ docs/* returns zero matches. |
| **AC-34** | REQ-11, REQ-12 → §2 Out of scope | The implementation does not include oscillation detection, multi-policy escalation, checkpoint/resume, dashboards, dependency-graph analysis, or any simulation framework. | Code review against the Out-of-scope list in §2. If any of these features are implemented, the review flags them as out-of-scope creep. |
| **AC-35** | All REQs → §6.4, §7.4, §8, §9.5 | All unit tests pass. | Shell: *pytest tests/cli/prompt_runner/* exits 0. |
| **AC-36** | Project CLAUDE.md conventions | No file produced by the runner into *<run_dir>/* contains inline backticks (except inside triple-backtick fenced blocks) or emojis. | *test_run_dir_output_has_no_inline_backticks_or_emojis* — after a run, walks *run_dir*, reads each *.md* and *.txt* file, asserts no match on *(?<!\`)\`(?!\`\`)* and no match on the emoji Unicode range *[\x{1F300}-\x{1F9FF}]*. |
| **AC-37** | REQ-7 → §5 exit codes | The tool exits with the documented exit codes: 0 (all pass), 1 (at least one escalate), 2 (parse error), 3 (runtime error). | Four tests: *test_exit_code_0_all_pass*, *test_exit_code_1_on_escalate*, *test_exit_code_2_on_parse_error*, *test_exit_code_3_on_claude_failure*. |

## 11. How to use this document

When implementing the Prompt Runner:

1. Implement one module at a time, in the order listed in *§12 Implementation order* of the design doc.
2. After each module is implemented, run the AC checks that trace to that module's design section.
3. Do not claim a module is done until every AC traced to it passes.
4. Before opening a pull request or declaring the whole tool done, run every AC in this document in sequence. The tool is only done when AC-01 through AC-37 all pass.

If an AC cannot be verified (e.g. a live *claude* binary is not available), document the gap explicitly rather than skipping the AC silently.
