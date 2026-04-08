# CD-001 — Prompt Runner

*Component design for a Python CLI tool that runs prompt/validator pairs from a markdown file through the Claude CLI, with a revision loop.*

## 1. Purpose

The *prompt-runner* is a small Python command-line tool that executes a sequence of prompt pairs defined in a markdown file. For each pair it runs the generation prompt through Claude, runs the validation prompt in a separate Claude session, and iterates on failures up to a configurable maximum.

The runner is **content-agnostic**: it has no hardcoded knowledge of any specific prompt set. Given any markdown file that matches the structural contract in Section 3, it will run that file. The file that motivated this tool (*ai-development-methodology-prompts_1.md*, containing six bootstrap prompts for an AI-driven development methodology) is one possible input, not a requirement.

## 2. Scope

### In scope

- Parsing a markdown file into an ordered list of prompt pairs.
- Printing parsed pairs (the *parse* subcommand) for manual verification.
- Running each pair through Claude via one-shot subprocess invocations of the *claude* CLI.
- A revision loop per pair that resumes the generator and judge sessions independently, up to a max iteration count.
- Halting the pipeline on an *escalate* verdict or on unrecoverable errors.
- Injecting prior approved artifacts as explicit text context into subsequent generator prompts.
- Writing all iteration outputs, final artifacts, and an end-of-run summary to a run directory.

### Out of scope

- Oscillation detection across iterations.
- Multi-policy escalation (halt / flag-and-continue / human-review / restructure). Only *halt* is implemented.
- Checkpoint/resume of a killed run. If the runner is interrupted, the user re-runs it.
- A dashboard, a database, or any storage backend other than the local filesystem.
- Any of the downstream software-development-pipeline machinery that the motivating file happens to describe (Phase Processing Unit, simulations, traceability graph, etc.). Those are artifacts produced **by** running this runner, not features **of** it.

## 3. Input contract

The runner accepts any markdown file whose body contains zero or more prompt sections of the following shape:

```
## Prompt [optional number] [optional title]

<any number of lines of arbitrary content — headings, prose, etc.>

```
<multi-line generation prompt body>
```

<optional lines of arbitrary content>

```
<multi-line validation prompt body>
```
```

(The nested triple-backtick lines above are the actual fenced code blocks that delimit the two prompt bodies; the outermost block is just this document quoting the format.)

Invariants the parser enforces:

1. Each prompt section is introduced by a level-2 heading whose first word is *Prompt* — the Python regex is *^##\s+Prompt\b[\s:\-—0-9]*(.*?)\s*$* (case-sensitive on the word *Prompt*). The trailing capture group is the title. All of the following are valid:
   - *## Prompt 1: Phase Processing Unit* — title is *Phase Processing Unit*
   - *## Prompt: Phase Processing Unit* — title is *Phase Processing Unit*
   - *## Prompt Phase Processing Unit* — title is *Phase Processing Unit*
   - *## Prompt 3 — Agent Roles* — title is *Agent Roles*
   - *## Prompt* — title is empty; the parser assigns *(untitled)* as the display title.
   The leading run of whitespace, colons, dashes, em-dashes, and digits after *Prompt* is discarded; whatever remains is the title. If the heading contains a number (*Prompt 3*), that number is ignored and the prompt's position in the file is used instead — see *index* below.
2. Between a prompt heading and the next prompt heading (or end-of-file), there must be **exactly two** fenced code blocks. Fences may be bare triple-backticks or may carry a language tag (e.g. *text*, *markdown*); the language tag is ignored.
3. Within a section, the **first** fenced block is the generation prompt and the **second** is the validation prompt. Ordering determines role — no label matching is performed on any subsection headers (*### 1.1 Generation Prompt*, *### N.2 Validation Prompt*, etc. are treated as plain text between fences and ignored).

Indexing: the parser assigns each *PromptPair* a 1-based *index* equal to its **position** in the file (first = 1, second = 2, ...). Any number that appears in the heading itself is discarded — the runner does not trust file-authored numbering because (a) it is optional, (b) it can have gaps, and (c) it can disagree with the author's intended order.

Non-invariants (deliberately not enforced, so different files work):

- Subsection headers may use any wording, or may be absent entirely.
- Heading numbers (if present at all) may be missing, non-sequential, or out of order. They are ignored for indexing.
- Prose, notes, and non-fenced content may appear anywhere between heading and first fence, between fences, and after the second fence.

Known limitation (v1):

- Fenced code blocks are delimited by exactly three backticks. A prompt body must not itself contain a triple-backtick block, because the parser would interpret the inner backticks as the end of the outer fence. If a prompt author needs to show a code example inside a prompt, they should either indent it four spaces or describe it in prose. Relaxing this to support 4+ backtick outer fences is a straightforward future extension (track the opening fence's backtick count, only close on a matching or longer run) but is not in v1.

## 4. Module layout

Source code lives under *src/cli/prompt_runner/*. Tests mirror under *tests/cli/prompt_runner/*.

```
src/cli/prompt_runner/
  __init__.py
  __main__.py          # python -m prompt_runner entry point
  parser.py            # markdown → list[PromptPair]
  claude_client.py     # subprocess wrapper around `claude -p`
  verdict.py           # Verdict enum + parse_verdict()
  runner.py            # pipeline orchestration (prompt loop + revision loop)

tests/cli/prompt_runner/
  __init__.py
  test_parser.py
  test_verdict.py
  test_runner.py
  fixtures/
    sample-prompts.md           # 2-prompt file for happy-path parser tests
    missing-validator.md        # one fence → parser error
    three-fences.md             # three fences → parser error
    unclosed-fence.md           # opening fence not closed → parser error
    tagged-fences.md            # ```text and ```markdown openings
    no-subsection-headers.md    # bare fences, no ### subheadings
    arbitrary-subsections.md    # ### Anything Goes subheadings
```

## 5. CLI shape

Two subcommands, sharing the parser.

```
python -m prompt_runner parse <file> [--full]

    Parse the file and pretty-print each prompt pair (index, title, body line/char
    counts, first few lines of each fenced block). With --full, dump the complete
    generator and validator bodies verbatim.

    This subcommand makes no Claude calls. It is the step-1 verification tool
    and also the sanity check for any new file before running it.

python -m prompt_runner run <file> [options]

    Execute the full pipeline.

    --output-dir DIR        Root of the run directory. Default:
                            ./runs/<ISO-timestamp>-<source-stem>/
    --max-iterations N      Max revision iterations per prompt. Default 3.
    --model MODEL           Passed through as --model to claude -p. Default:
                            omitted (inherits claude CLI default).
    --only N                Run only prompt number N (for debugging). Prior
                            prompts are still parsed but their output context
                            is not injected.
    --dry-run               Parse the file and print the planned sequence of
                            Claude invocations without actually calling claude.
```

Exit codes:

- *0* — pipeline ran to completion, every prompt reached a *pass* verdict.
- *1* — at least one prompt escalated (max iterations exhausted or judge returned *escalate*).
- *2* — parse error in the input file.
- *3* — runtime error (claude binary missing, subprocess failure, unparseable verdict).

## 6. Parser (*parser.py*)

### 6.1 Data model

```python
@dataclass(frozen=True)
class PromptPair:
    index: int              # 1-based position in the file; NOT read from the heading
    title: str              # title extracted from the heading, or "(untitled)" if empty
    generation_prompt: str  # body of the first fenced code block, fences stripped
    validation_prompt: str  # body of the second fenced code block, fences stripped
    heading_line: int       # 1-based line number where the "## Prompt ..." heading appears
    generation_line: int    # 1-based line number of the opening fence of the generation block, or 0 if not yet seen
    validation_line: int    # 1-based line number of the opening fence of the validation block, or 0 if not yet seen
```

The line-number fields exist so that every error message can point at the exact line in the user's file. *heading_line* is always populated; *generation_line* and *validation_line* are populated as those blocks are encountered (and used in error messages for partially-parsed sections).

### 6.2 Algorithm

A line-by-line state machine over the file content. States:

- *SEEK_HEADING* — looking for the next *## Prompt* heading.
- *SEEK_FIRST_FENCE* — heading captured; looking for the opening of the generation prompt's code block.
- *IN_FIRST_FENCE* — accumulating the generation prompt body until the closing fence.
- *SEEK_SECOND_FENCE* — generation prompt captured; looking for the opening of the validation prompt's code block.
- *IN_SECOND_FENCE* — accumulating the validation prompt body until the closing fence.
- *SEEK_EXTRA_CHECK* — both code blocks captured; scanning until the next heading or end of file, erroring if another code block opens.

Transitions (and the error IDs they raise, defined in section 6.3):

- Any state, on a *## Prompt …* heading line:
  - From *SEEK_HEADING* or *SEEK_EXTRA_CHECK*: finalise the previous pair (if any), start a new one.
  - From *SEEK_FIRST_FENCE*: raise *E-NO-BLOCKS*.
  - From *SEEK_SECOND_FENCE*: raise *E-MISSING-VALIDATION*.
  - From *IN_FIRST_FENCE*: raise *E-UNCLOSED-GENERATION*.
  - From *IN_SECOND_FENCE*: raise *E-UNCLOSED-VALIDATION*.
- *SEEK_FIRST_FENCE* on an opening-fence line → *IN_FIRST_FENCE* (record *generation_line*).
- *IN_FIRST_FENCE* on a closing-fence line → *SEEK_SECOND_FENCE*.
- *SEEK_SECOND_FENCE* on an opening-fence line → *IN_SECOND_FENCE* (record *validation_line*).
- *IN_SECOND_FENCE* on a closing-fence line → *SEEK_EXTRA_CHECK*.
- *SEEK_EXTRA_CHECK* on an opening-fence line → raise *E-EXTRA-BLOCK*.

Fence detection regex: *^```[A-Za-z0-9_+-]*\s*$* — a line that is nothing but three backticks optionally followed by a language tag. An opening and closing fence look identical, so we disambiguate by state.

At end of file:
- *SEEK_HEADING* or *SEEK_EXTRA_CHECK* → OK, emit final pair if one is in progress.
- *SEEK_FIRST_FENCE* → raise *E-NO-BLOCKS*.
- *SEEK_SECOND_FENCE* → raise *E-MISSING-VALIDATION*.
- *IN_FIRST_FENCE* → raise *E-UNCLOSED-GENERATION*.
- *IN_SECOND_FENCE* → raise *E-UNCLOSED-VALIDATION*.

### 6.3 Error catalogue

Every *ParseError* carries an ID and a user-facing message. The messages are designed to be read by someone who wrote the input file and now needs to fix it — including AIs that were told to generate a prompt file. They always include: the prompt's position in the file, its title, the relevant line number, and a concrete repair instruction.

**E-NO-BLOCKS** — a prompt heading was found but neither the generation prompt nor the validation prompt followed before the next heading (or end of file).

```
Prompt 3 "Agent Roles" (line 258): no generation prompt or validation prompt
was found in this section.

Each prompt section must contain two fenced code blocks, in order:
  1. the generation prompt (delimited by a line of exactly ``` at the start
     and another line of exactly ``` at the end)
  2. the validation prompt (same delimiters)

The next prompt heading was found at line 312 before either block appeared.
Add both blocks between line 258 and line 312.
```

**E-MISSING-VALIDATION** — the generation prompt was successfully read, but no validation prompt followed before the next heading (or end of file).

```
Prompt 3 "Agent Roles" (line 258): the generation prompt was found (starting at
line 262), but the validation prompt is missing.

Each prompt section must contain two fenced code blocks. After the closing ```
of the generation prompt, add a second fenced code block containing the
validation prompt.

The next prompt heading was found at line 312 before the validation block
appeared. Add the validation block between line 287 (end of the generation
block) and line 312.
```

(If the error is raised at end of file instead of at the next heading, the final sentence becomes *"The file ended before the validation block appeared. Add it before the end of the file."*)

**E-UNCLOSED-GENERATION** — a generation-prompt code block was opened but never closed before the next heading or end of file.

```
Prompt 3 "Agent Roles" (line 258): the generation prompt's code block was
opened at line 262 but never closed.

A code block is closed by a line containing exactly ``` (three backticks
with nothing else on the line). Add that line somewhere between line 262
and the next prompt heading (found at line 312), or before the end of the
file.

Common cause: the body of the generation prompt itself contains a line of
triple backticks, which the parser interprets as the end of the code block.
If you need to show a code example inside the prompt, indent it four spaces
instead of wrapping it in triple backticks.
```

**E-UNCLOSED-VALIDATION** — same as above, but for the validation prompt's code block.

```
Prompt 3 "Agent Roles" (line 258): the validation prompt's code block was
opened at line 289 but never closed.

A code block is closed by a line containing exactly ``` (three backticks
with nothing else on the line). Add that line somewhere between line 289
and the next prompt heading (found at line 312), or before the end of the
file.

Common cause: the body of the validation prompt itself contains a line of
triple backticks, which the parser interprets as the end of the code block.
If you need to show a code example inside the prompt, indent it four spaces
instead of wrapping it in triple backticks.
```

**E-EXTRA-BLOCK** — a third (or later) fenced code block was found inside a prompt section, after both the generation and validation blocks had already been read.

```
Prompt 3 "Agent Roles" (line 258): an unexpected third code block was found,
opening at line 305.

Each prompt section must contain exactly two fenced code blocks: the
generation prompt (found at line 262) and the validation prompt (found at
line 289). Any additional fenced code block before the next prompt heading
is an error.

Likely causes:
  - You included an example as a fenced code block inside the validation
    prompt. Indent the example four spaces instead, or describe it in prose.
  - You intended to start a new prompt but used "##" with a different word
    instead of "## Prompt".

Fix: either remove the extra code block at line 305, or start a new prompt
section with a "## Prompt ..." heading before it.
```

### 6.4 Parser test list

- *test_parses_minimal_two_prompt_file* — fixture *sample-prompts.md*, asserts two *PromptPair* objects with expected positional indices (1, 2), titles, and body contents.
- *test_preserves_body_verbatim* — generator body contains *## Fake Prompt 99:* and *### fake subheading*; parser does not misinterpret them because they are inside a fenced code block.
- *test_strips_fences_from_body* — returned *generation_prompt* and *validation_prompt* do not begin or end with a backtick-fence line.
- *test_accepts_language_tagged_fences* — fixture *tagged-fences.md* with *```text* and *```markdown* openings parses identically.
- *test_accepts_no_subsection_headers* — fixture *no-subsection-headers.md* with two fences directly under the heading parses correctly.
- *test_accepts_arbitrary_subsection_headers* — fixture *arbitrary-subsections.md* with *### Anything Goes* headings parses correctly.
- *test_accepts_numbered_heading* — heading *## Prompt 1: Phase Processing Unit* yields title *Phase Processing Unit*, index 1.
- *test_accepts_unnumbered_heading_with_colon* — heading *## Prompt: Phase Processing Unit* yields title *Phase Processing Unit*.
- *test_accepts_unnumbered_heading_without_colon* — heading *## Prompt Phase Processing Unit* yields title *Phase Processing Unit*.
- *test_accepts_em_dash_separator* — heading *## Prompt 3 — Agent Roles* yields title *Agent Roles*.
- *test_empty_title_becomes_untitled* — heading *## Prompt* alone yields title *(untitled)*.
- *test_positional_index_ignores_heading_number* — file has headings *## Prompt 5: A* then *## Prompt 10: B*; parser returns indices 1 and 2.
- *test_error_no_blocks* — fixture with a prompt heading followed directly by the next heading (no code blocks in between) raises *ParseError* with ID *E-NO-BLOCKS*, containing the prompt's title, heading line, and next-heading line.
- *test_error_missing_validation* — fixture *missing-validator.md* raises *ParseError* with ID *E-MISSING-VALIDATION*, containing the prompt's title, heading line, generation-block line, and next-heading-or-EOF line.
- *test_error_unclosed_generation* — fixture with an unclosed generator block raises *E-UNCLOSED-GENERATION*, message mentions the generation-block opening line.
- *test_error_unclosed_validation* — fixture with an unclosed validator block raises *E-UNCLOSED-VALIDATION*, message mentions the validation-block opening line.
- *test_error_extra_block* — fixture *three-fences.md* raises *E-EXTRA-BLOCK*, message mentions all three block line numbers.
- *test_error_messages_mention_title_and_lines* — every *ParseError* message contains the prompt title (or *(untitled)*), the heading line number, and at least one specific repair instruction.

## 7. Claude client (*claude_client.py*)

A wrapper around *subprocess.Popen* for invoking the Claude CLI, with live output streaming, per-invocation log capture, and concurrent stderr reading.

```python
@dataclass(frozen=True)
class ClaudeCall:
    prompt: str
    session_id: str
    new_session: bool       # if True, pass --session-id; if False, pass --resume
    model: str | None
    stdout_log_path: Path   # where to write raw stdout (teed while streaming)
    stderr_log_path: Path   # where to write raw stderr
    stream_header: str      # a short label printed to the terminal before streaming begins
                            # e.g. "── prompt 3 'Agent Roles' / iter 2 / judge ──"

@dataclass(frozen=True)
class ClaudeResponse:
    stdout: str             # full captured stdout (what the runner uses as the "response")
    stderr: str             # full captured stderr
    returncode: int

class ClaudeInvocationError(Exception):
    call: ClaudeCall
    response: ClaudeResponse  # partial response, may contain useful stdout/stderr even on failure

class ClaudeClient(Protocol):
    def call(self, call: ClaudeCall) -> ClaudeResponse: ...
```

The return type changed from *str* to *ClaudeResponse* so callers can see stderr and exit code explicitly. The runner uses *response.stdout* as the model's reply.

### 7.1 Real implementation

Constructs an argv list of the form:

```
claude -p --output-format text
        [--model <model>]
        (--session-id <id> | --resume <id>)
```

The prompt body is written to the child process's **stdin**, not placed on argv. Decisions:

- Stdin-only prompt delivery. Prompt bodies can be thousands of characters long and may contain shell-special characters; stdin avoids all quoting issues and argv length limits.
- *--output-format text* is selected so the stdout stream is just the model's response token-by-token, with no wrapping JSON to decode on the fly.
- A *binary-not-found* check at startup (in *runner.run_pipeline*) gives a clear error before any prompt is parsed, rather than a cryptic failure mid-run.

**Streaming, log capture, and concurrent stderr reading:**

The real client uses *subprocess.Popen* rather than *subprocess.run* so that it can forward stdout to the terminal in real time while the model is still generating. The structure is:

```
1. Popen(argv, stdin=PIPE, stdout=PIPE, stderr=PIPE,
         text=True, bufsize=1, encoding="utf-8")
2. Print call.stream_header (a dim/indented label) to the terminal.
3. Write call.prompt to proc.stdin, then proc.stdin.close().
4. Start a background thread that reads proc.stderr in a loop, appending
   every chunk to an in-memory buffer AND to call.stderr_log_path.
   (Stderr from claude -p is usually empty; we read it concurrently
   purely to prevent the pipe buffer from filling and deadlocking
   the child when stdout is large.)
5. In the main thread, iterate over proc.stdout line by line. For each
   line:
     - write it to sys.stdout (indented under the stream_header) and
       flush, so the user sees it live
     - append it to an in-memory stdout buffer
     - append it to call.stdout_log_path
6. When stdout is exhausted, call proc.wait() to collect the exit code.
7. Join the stderr thread to collect the final stderr buffer.
8. Construct and return a ClaudeResponse(stdout, stderr, returncode).
   If returncode != 0, raise ClaudeInvocationError(call, response)
   carrying the partial response — this lets the runner persist what
   little was captured before bubbling the error up.
```

The stdout log file is opened in append mode before each line is written, so the file reflects the live state of the stream even if the process is killed. Similarly for stderr.

### 7.2 Fake implementation (for tests)

*FakeClaudeClient* stores a scripted list of *ClaudeResponse* objects and returns them in order, recording each *ClaudeCall* it receives for assertions. It does **not** write to *stdout_log_path* or *stderr_log_path* — log writing is tested separately as part of the real-client tests. This is the test double used in all *test_runner.py* cases.

### 7.3 Dry-run implementation

*DryRunClaudeClient* records the call and returns a synthetic *ClaudeResponse* with a placeholder stdout string describing what would have happened and empty stderr, exit code 0. It makes no subprocess call and writes no log files. The *--dry-run* flag wires this into the runner.

### 7.4 Claude client test list

- *test_real_client_streams_stdout_to_terminal* — monkeypatch *Popen* to return a fake process that emits three lines slowly on stdout; assert that sys.stdout receives each line before the next arrives (use a captured-stdout fixture that timestamps writes).
- *test_real_client_writes_stdout_log* — after a successful call, assert that *stdout_log_path* contains the complete stdout.
- *test_real_client_writes_stderr_log* — fake process emits two lines on stderr; after call, *stderr_log_path* contains both.
- *test_real_client_concurrent_reading_no_deadlock* — fake process that emits >64KB on both stdout and stderr; call completes without hanging.
- *test_real_client_nonzero_exit_raises_with_partial_response* — fake process exits 1 after emitting some stdout; *ClaudeInvocationError* is raised and its *response* field contains the partial stdout and stderr.
- *test_real_client_binary_missing* — monkeypatch *Popen* to raise *FileNotFoundError*; the client converts this into a distinct exception class (*ClaudeBinaryNotFound*) that *runner.run_pipeline* catches at startup for *R-NO-CLAUDE*.
- *test_fake_client_scripted_responses* — sanity check that *FakeClaudeClient* returns its scripted list in order and records call arguments correctly.
- *test_dry_run_client_makes_no_subprocess_call* — ensure *Popen* is never called when *DryRunClaudeClient* is used.

## 8. Verdict parser (*verdict.py*)

```python
class Verdict(Enum):
    PASS = "pass"
    REVISE = "revise"
    ESCALATE = "escalate"

class VerdictParseError(Exception): ...

def parse_verdict(judge_output: str) -> Verdict: ...
```

Implementation:

- Regex: *^VERDICT:\s*(pass|revise|escalate)\s*$*, compiled with *re.IGNORECASE | re.MULTILINE*.
- *findall* returns all matches; the **last** match wins. Rationale: a judge may reference the instruction mid-response (e.g. "if I were to say VERDICT: pass here..."), and we told it to put the real verdict on the final line, so taking the last match is the robust choice.
- If there are zero matches, raise *VerdictParseError* with the first 500 characters of the judge output for debugging.

### Verdict test list

- *test_parses_pass*, *test_parses_revise*, *test_parses_escalate*.
- *test_case_insensitive_keyword* — *VERDICT: Pass* returns *Verdict.PASS*.
- *test_case_insensitive_label* — *Verdict: revise* returns *Verdict.REVISE*.
- *test_takes_last_match* — an output containing *VERDICT: revise* in the middle and *VERDICT: pass* at the end returns PASS.
- *test_raises_on_missing* — plain text with no *VERDICT* line raises *VerdictParseError*.
- *test_raises_on_unknown_value* — *VERDICT: maybe* raises (no regex match).
- *test_allows_trailing_whitespace* — *VERDICT: pass   * matches.

## 9. Runner engine (*runner.py*)

### 9.1 Data model

```python
@dataclass(frozen=True)
class RunConfig:
    max_iterations: int = 3
    model: str | None = None
    only: int | None = None
    dry_run: bool = False

@dataclass(frozen=True)
class IterationResult:
    iteration: int
    generator_output: str
    judge_output: str
    verdict: Verdict

@dataclass(frozen=True)
class PromptResult:
    pair: PromptPair
    iterations: list[IterationResult]
    final_verdict: Verdict        # verdict of the last iteration
    final_artifact: str           # generator_output of the last iteration

@dataclass(frozen=True)
class PipelineResult:
    prompt_results: list[PromptResult]
    halted_early: bool
    halt_reason: str | None
```

### 9.2 Top-level flow — *run_pipeline*

```
function run_pipeline(pairs, run_dir, config, claude_client):
    create run_dir
    write manifest.json (source file, config, start time)
    prior_artifacts = []                       # list of (title, body) tuples
    prompt_results = []

    for pair in pairs:
        if config.only is not None and pair.index != config.only:
            continue

        result = run_prompt(pair, prior_artifacts, run_dir, config, claude_client)
        prompt_results.append(result)

        if result.final_verdict == Verdict.PASS:
            prior_artifacts.append((pair.title, result.final_artifact))
        else:
            # final_verdict is ESCALATE (either direct or max-iterations)
            halt_reason = f"prompt {pair.index} escalated"
            write_summary(run_dir, prompt_results,
                          halted_early=True, halt_reason=halt_reason)
            return PipelineResult(prompt_results,
                                  halted_early=True, halt_reason=halt_reason)

    write_summary(run_dir, prompt_results, halted_early=False, halt_reason=None)
    return PipelineResult(prompt_results, halted_early=False, halt_reason=None)
```

### 9.3 Per-prompt flow — *run_prompt*

```
function run_prompt(pair, prior_artifacts, run_dir, config, claude_client):
    run_id       = stem of run_dir (ISO timestamp + source stem)
    gen_session  = f"gen-prompt-{pair.index}-{run_id}"
    jud_session  = f"jud-prompt-{pair.index}-{run_id}"
    prompt_slug  = f"prompt-{pair.index:02d}-{slugify(pair.title)}"
    prompt_dir   = run_dir / prompt_slug
    logs_dir     = run_dir / "logs" / prompt_slug
    create prompt_dir and logs_dir

    # Print a banner to the terminal so the user knows which prompt is running.
    stream_banner(f"═══ Prompt {pair.index}: {pair.title} ═══")

    iterations = []

    for iteration_number in 1, 2, ..., config.max_iterations:
        is_first = (iteration_number == 1)

        # ---- Generator call ----
        gen_msg = (build_initial_generator_message(pair, prior_artifacts)
                   if is_first
                   else build_revision_generator_message(iterations[-1].judge_output))

        gen_call = ClaudeCall(
            prompt=gen_msg,
            session_id=gen_session,
            new_session=is_first,       # True → --session-id, False → --resume
            model=config.model,
            stdout_log_path=logs_dir / f"iter-{iteration_number:02d}-generator.stdout.log",
            stderr_log_path=logs_dir / f"iter-{iteration_number:02d}-generator.stderr.log",
            stream_header=f"── iter {iteration_number} / generator ──",
        )
        gen_response = claude_client.call(gen_call)
        # gen_response.stdout is the model's reply; write it to the clean .md file too.
        write(prompt_dir / f"iter-{iteration_number:02d}-generator.md", gen_response.stdout)

        # ---- Judge call ----
        jud_msg = (build_initial_judge_message(pair, gen_response.stdout)
                   if is_first
                   else build_revision_judge_message(gen_response.stdout))

        jud_call = ClaudeCall(
            prompt=jud_msg,
            session_id=jud_session,
            new_session=is_first,
            model=config.model,
            stdout_log_path=logs_dir / f"iter-{iteration_number:02d}-judge.stdout.log",
            stderr_log_path=logs_dir / f"iter-{iteration_number:02d}-judge.stderr.log",
            stream_header=f"── iter {iteration_number} / judge ──",
        )
        jud_response = claude_client.call(jud_call)
        write(prompt_dir / f"iter-{iteration_number:02d}-judge.md", jud_response.stdout)

        verdict = parse_verdict(jud_response.stdout)
        iterations.append(IterationResult(
            iteration_number, gen_response.stdout, jud_response.stdout, verdict))

        if verdict != Verdict.REVISE:
            break   # pass or escalate — exit the loop

    final = iterations[-1]
    # If we exited the loop still on REVISE, we hit the max iteration count → escalate.
    final_verdict = final.verdict
    if final_verdict == Verdict.REVISE:
        final_verdict = Verdict.ESCALATE

    write(prompt_dir / "final-artifact.md",  final.generator_output)
    write(prompt_dir / "final-verdict.txt",  final_verdict.value)

    return PromptResult(pair, iterations, final_verdict, final.generator_output)
```

The for-loop form is equivalent to the earlier while-loop but removes the duplication between the first iteration (fresh sessions) and the revision iterations (resumed sessions) — the *is_first* flag controls the branch instead.

### 9.4 Prompt builders

All four functions return plain strings.

**build_initial_generator_message**(pair, prior_artifacts)

- If *prior_artifacts* is empty: return *pair.generation_prompt* verbatim.
- Otherwise: prepend a *# Prior approved artifacts* block with each prior (title, body) as a subsection, then a horizontal rule, then a *# Your task* heading, then *pair.generation_prompt*.

**build_initial_judge_message**(pair, artifact)

Concatenation of:
1. *pair.validation_prompt* verbatim.
2. Horizontal rule.
3. *# Artifact to evaluate* heading and the artifact body.
4. Horizontal rule.
5. A fixed instruction block:

   > End your response with a single line of the exact form: *VERDICT: pass*, *VERDICT: revise*, or *VERDICT: escalate*. Do not write anything after that line.

**build_revision_generator_message**(judge_output)

A fixed preamble followed by the judge output. Preamble:

> The judge evaluated your previous artifact and returned the feedback below. Produce a revised artifact that addresses every fail or partial item. Do not drop content that already passed. Your response must be the complete revised artifact, with no commentary before or after it.

The revised generator prompt does **not** re-inject the previous artifact, because the generator's resumed session already contains it.

**build_revision_judge_message**(new_artifact)

A fixed preamble (the anti-anchoring clause) followed by the new artifact. Preamble:

> Below is the revised artifact. Re-evaluate every checklist item against this current version. Items you previously failed may now pass, and items you previously passed may now fail if the revision broke them. Do not defer to your prior verdict.

Followed by the artifact, followed by the same *VERDICT:* instruction as the initial judge message.

### 9.5 Runner test list

All tests use *FakeClaudeClient* with scripted responses and assert on the recorded call log.

- *test_single_prompt_passes_first_try* — one *PromptPair*, judge returns *VERDICT: pass* on iteration 1. Expects exactly one generator call and one judge call, both with *new_session=True*. Final verdict *PASS*.
- *test_single_prompt_passes_on_second_iteration* — judge returns *revise* then *pass*. Expects two generator calls (second with *new_session=False*), two judge calls (second with *new_session=False*). Final verdict *PASS*. Final artifact equals the second generator output.
- *test_escalation_on_max_iterations* — judge always returns *revise* with *max_iterations=3*. Expects exactly three generator calls and three judge calls. Final verdict *ESCALATE*.
- *test_direct_escalation* — judge returns *VERDICT: escalate* on iteration 1. Expects one generator call and one judge call. Final verdict *ESCALATE*. Pipeline halts.
- *test_prior_artifacts_injected_into_next_prompt* — two *PromptPair* objects; prompt 1 passes with artifact *"ARTIFACT-ONE"*. Assert that the generator call for prompt 2 has a *prompt* field containing the string *"ARTIFACT-ONE"*.
- *test_escalation_halts_pipeline* — three *PromptPair* objects; prompt 2 escalates. Expects that prompt 3 is never called; pipeline result has *halted_early=True*.
- *test_dry_run_makes_no_real_calls* — *RunConfig(dry_run=True)*; wires in *DryRunClaudeClient*; asserts no subprocess was ever invoked.
- *test_unparseable_verdict_raises* — judge returns output with no *VERDICT:* line; runner raises *VerdictParseError* which halts the pipeline with a *halt_reason* mentioning the prompt index and that line was missing.
- *test_only_flag_runs_single_prompt* — three pairs, *only=2*; expects only prompt 2's pair is executed, and its generator message does **not** contain any prior artifact injection (because *only* bypasses the forward context).
- *test_session_id_naming* — asserts the session IDs used for prompt N are *gen-prompt-N-<run-id>* and *jud-prompt-N-<run-id>* and that generator and judge session IDs are never identical.
- *test_resume_flag_set_on_iterations_after_first* — iteration 1 calls use *new_session=True*, iteration 2+ use *new_session=False*.
- *test_log_paths_passed_to_every_call* — asserts that every *ClaudeCall* the runner constructs has a *stdout_log_path* and *stderr_log_path* rooted under *<run_dir>/logs/<prompt-slug>/*, with filenames that include the iteration number and role.
- *test_logs_dir_created_before_first_call* — asserts *<run_dir>/logs/<prompt-slug>/* exists on disk before the first *ClaudeCall* is dispatched for that prompt (so the real client can open the log files for append without an ENOENT).
- *test_stream_header_contains_prompt_title_and_role* — asserts each *ClaudeCall*'s *stream_header* mentions the prompt number, the iteration number, and either *generator* or *judge*.
- *test_halt_on_claude_failure_writes_partial_md* — *FakeClaudeClient* raises *ClaudeInvocationError* on iteration 2's judge call with a partial *ClaudeResponse* whose stdout contains *"PARTIAL-JUDGE-OUTPUT"*; assert that *iter-02-judge.md* was written with that content even though the error halted the pipeline.

## 10. Storage layout

Run directory:

```
runs/2026-04-08T14-30-12-ai-development-methodology-prompts_1/
  manifest.json
  summary.txt
  prompt-01-phase-processing-unit/
    iter-01-generator.md          # clean model response (= captured stdout of gen call)
    iter-01-judge.md              # clean model response (= captured stdout of judge call)
    iter-02-generator.md          # only exists if iteration 1 said revise
    iter-02-judge.md
    final-artifact.md
    final-verdict.txt
  prompt-02-phase-definitions/
    ...
  logs/
    prompt-01-phase-processing-unit/
      iter-01-generator.stdout.log    # raw subprocess stdout (typically == iter-01-generator.md)
      iter-01-generator.stderr.log    # raw subprocess stderr (empty on success, populated on warnings/errors)
      iter-01-judge.stdout.log
      iter-01-judge.stderr.log
      iter-02-generator.stdout.log
      iter-02-generator.stderr.log
      iter-02-judge.stdout.log
      iter-02-judge.stderr.log
    prompt-02-phase-definitions/
      ...
```

Two-layer structure: the prompt-NN/ directories at the top level hold the **clean content** the user will actually want to look at (the model's parsed response per iteration, the final artifact, the verdict). The *logs/* subtree holds the **raw subprocess captures** — stdout and stderr for every claude invocation, indexed by the same prompt-NN/iter-NN keys. On success, stdout.log is usually identical to the corresponding .md file; the value of the separate log is for investigating failures, where stderr may hold the only useful information. The *.stderr.log* files are created even when empty, so their absence indicates a run that never got that far.

*manifest.json* schema:

```json
{
  "source_file": "/abs/path/to/input.md",
  "run_id": "2026-04-08T14-30-12-input",
  "config": {
    "max_iterations": 3,
    "model": null,
    "only": null,
    "dry_run": false
  },
  "started_at": "2026-04-08T14:30:12Z",
  "finished_at": null
}
```

*finished_at* is rewritten on pipeline exit.

*summary.txt* schema (plain text, human-readable):

```
Prompt Runner — Run Summary
Source: /abs/path/to/input.md
Run:    runs/2026-04-08T14-30-12-input
Status: completed | halted

Prompts:
  01  phase-processing-unit         pass      1 iter
  02  phase-definitions             pass      2 iter
  03  agent-role-specifications     escalate  3 iter  (max iterations exhausted)
  04  ...                           skipped
  ...

Total claude calls: 12
Wall time: 00:04:32
```

## 11. Error handling & halt conditions

### 11.1 Summary table

| Condition | Behaviour | Exit code |
|---|---|---|
| Parse error in input file (any *E-…* from section 6.3) | Print the full error message to stderr (including prompt position, title, line numbers, and repair instructions). No run directory created. | 2 |
| *claude* binary not found on PATH | Print a friendly error to stderr at startup (see 11.2). No run directory created. | 3 |
| *claude -p* exits non-zero mid-run | Stop the pipeline. Write *summary.txt* with a *halt_reason* naming the prompt, iteration, role (generator/judge), and stderr excerpt (see 11.2). | 3 |
| Judge output has no parseable *VERDICT* line | Stop the pipeline. Write *summary.txt* with a *halt_reason* naming the prompt, iteration, and pointing at the offending *iter-NN-judge.md* (see 11.2). | 3 |
| Prompt reaches *max_iterations* still on *revise* | Treat as *escalate*. Halt pipeline. | 1 |
| Judge returns *VERDICT: escalate* directly | Halt pipeline. | 1 |
| Pipeline completes with all prompts *pass* | Write *summary.txt*. | 0 |

Halts always write a *summary.txt* reflecting whatever progress was made before the halt, and rewrite *manifest.json*'s *finished_at* field.

### 11.2 Runtime error messages

Parse errors use the catalogue in section 6.3. Runtime errors follow the same principle — name the prompt, give a line or file pointer, give a repair instruction — but the "line number" points into a saved run file rather than into the source markdown.

**R-NO-CLAUDE** — the *claude* binary cannot be found on PATH at startup.

```
prompt-runner: cannot find the 'claude' command on PATH.

This tool invokes the Claude CLI as a subprocess to run each prompt. Install
the Claude CLI and make sure 'claude' is on your PATH, then try again.

See: https://code.claude.com/docs/en/quickstart
```

**R-CLAUDE-FAILED** — a *claude -p* invocation exited non-zero.

```
Prompt 3 "Agent Roles", iteration 2, generator call: the 'claude' command
exited with status 1.

Command:
  claude -p --output-format text --resume gen-prompt-3-<run-id>

Last 20 lines of stderr (from logs/prompt-03-agent-roles/iter-02-generator.stderr.log):
  <last 20 lines of the stderr log, indented>

Partial output saved to:
  runs/2026-04-08T14-30-12-input/prompt-03-agent-roles/iter-02-generator.md

Full logs saved to:
  runs/2026-04-08T14-30-12-input/logs/prompt-03-agent-roles/

To retry, re-run prompt-runner. To investigate, look at the .stdout.log and
.stderr.log files in the logs directory above.
```

The *role* in the first line is *generator call* or *judge call*. The *iteration* number is whichever iteration was in flight when the error occurred. The "last 20 lines of stderr" is read from *stderr_log_path*, not from an in-memory buffer, so that the user sees exactly what was persisted.

**R-NO-VERDICT** — a judge response was received but contains no recognisable *VERDICT:* line.

```
Prompt 3 "Agent Roles", iteration 2: the judge's response did not contain a
VERDICT line.

The runner appends an instruction to every judge prompt asking it to end
its response with a line of the exact form:
  VERDICT: pass
  VERDICT: revise
  VERDICT: escalate

The judge's actual response has been saved to:
  runs/2026-04-08T14-30-12-input/prompt-03-agent-roles/iter-02-judge.md

Full stdout/stderr logs:
  runs/2026-04-08T14-30-12-input/logs/prompt-03-agent-roles/iter-02-judge.stdout.log
  runs/2026-04-08T14-30-12-input/logs/prompt-03-agent-roles/iter-02-judge.stderr.log

Last 20 lines of the response, for quick diagnosis:
  <last 20 lines of iter-02-judge.md, indented>

The pipeline is halting. Re-run prompt-runner to retry; if the same judge
produces an ungrammatical verdict on every iteration, review the validation
prompt itself and make sure its instructions don't conflict with the VERDICT
requirement.
```

Every runtime error message follows the same shape: *what went wrong* (one line), *where to find the evidence on disk* (path, including both the clean .md file and the raw .log file), *how to fix or retry* (instruction). This is the contract for any future error type added to the runner.

### 11.3 Halt semantics

When the runner halts (any row above with an exit code other than 0), it must always:

1. Write the current iteration's generator and judge outputs to disk before the error is raised — partial files are fine, missing files are not. Raw subprocess logs (*.stdout.log*, *.stderr.log*) are already streaming-written by the real claude client, so they reflect whatever the subprocess produced up to the point of failure. The runner wraps each *claude_client.call()* in a try/except that writes the clean *.md* file using whatever *response.stdout* was captured in the *ClaudeInvocationError* before bubbling the error up.
2. Rewrite *manifest.json* with *finished_at* set to the halt timestamp and a new *halt_reason* field containing the error ID (*E-…* or *R-…*) and the error message.
3. Write *summary.txt* listing every prompt's status up to the halt. Prompts that never ran are listed as *skipped*.
4. Print the error prominently to stderr **after all streamed output has finished**, so the user sees it as the last thing on the terminal rather than buried above the most recent streamed model response. The format is:

   ```
   ══════════════════════════════════════════════════════════════════════
   ERROR: <error ID>
   ══════════════════════════════════════════════════════════════════════
   <the full error message from section 6.3 or 11.2, verbatim>
   ══════════════════════════════════════════════════════════════════════
   ```

   The horizontal rules exist specifically to visually detach the error block from streamed model content that may be directly above it.
5. Exit with the exit code from the table in 11.1.

### 11.4 Successful-completion output

On a clean pipeline completion (exit code 0), the runner prints a short success block to stdout, mirroring the error block's visual framing so successful runs are equally scannable:

```
══════════════════════════════════════════════════════════════════════
Prompt Runner — Run complete
══════════════════════════════════════════════════════════════════════
<contents of summary.txt>
══════════════════════════════════════════════════════════════════════
```

## 12. Implementation order

Suggested build sequence (each step ends with tests green before the next begins):

1. *verdict.py* + *test_verdict.py* — smallest independent unit.
2. *parser.py* + *test_parser.py* — the other pure-logic unit; also the step-1 deliverable target. Implement the full error catalogue from section 6.3 up front — friendly errors are a feature, not polish.
3. *__main__.py parse* subcommand — wires the parser to stdout. End of step-1 deliverable.
4. The input-format companion README (section 13) — written before the runner subcommand so that the first person to point a new file at the runner has something to read.
5. *claude_client.py* protocol + *FakeClaudeClient* + *DryRunClaudeClient* — test doubles only; no real subprocess yet. This lets runner tests proceed while the real streaming client is still being designed.
6. *runner.py* + *test_runner.py* — the bulk of the logic, test-driven against *FakeClaudeClient*.
7. *claude_client.py* real streaming implementation — *Popen*, concurrent stderr reader, tee-to-log, stream-to-terminal. Tested with a monkeypatched *Popen* for determinism, then smoke-tested once against a live *claude* binary.
8. *__main__.py run* subcommand, including the halt banner (11.3) and completion banner (11.4) — end of step-2 deliverable.

## 13. Input format companion README

### 13.1 Why

The prompt runner is content-agnostic: it will run any file that matches the structural contract in section 3. That means the tool's usefulness depends on someone — often an AI agent being told *"write me a prompt file for the prompt runner"* — being able to author a valid file without reading this design document.

The README is the document that AI (and human) file authors read. Its audience is explicitly *"I need to produce a markdown file that the prompt runner will accept."* It is **not** a tool manual for end users running the CLI; that role is played by *--help* and by example commands at the bottom of the README.

### 13.2 Location & filename

To be confirmed by the *project-organiser* sub-agent at write time. Leading candidates:

- *src/cli/prompt_runner/README.md* — co-located with the Python package. Works well if the user also wants it shown by *pip show* / *python -m prompt_runner --help*.
- *docs/guides/prompt-runner-input-format.md* — a project-level guide if a new taxonomy category is introduced.

The file itself does not change based on location.

### 13.3 Contents

The README must cover, in roughly this order:

1. **What the runner does**, in one paragraph. Include the sentence "it runs any markdown file that matches the format described below" to set the reader's expectation that this is a format spec, not a tool manual.
2. **The required file structure**, by example. Show a minimal valid file with two prompts, annotated with arrows pointing at the heading, the two fenced code blocks, and the gap between prompts. The example must be copy-pasteable and must parse without error.
3. **The heading format**, with all accepted variants listed (the five bullet points from section 3 of this design). Make it clear that heading numbers are ignored.
4. **The two code blocks**, with the role of each (first = generation prompt, second = validation prompt) and a plain-English statement that ordering determines the role.
5. **What NOT to do**, with concrete examples:
   - *Do not* include a third fenced code block — if the prompt body needs a code example, indent it four spaces.
   - *Do not* nest triple-backtick blocks inside a prompt body (v1 limitation).
   - *Do not* include your own verdict-format instruction in the validation prompt — the runner appends a *VERDICT: pass|revise|escalate* instruction automatically, and a conflicting instruction confuses the judge.
   - *Do not* rely on the heading number being preserved — the runner indexes by file order, so if you want prompts in a specific order, put them in the file in that order.
6. **What the runner does with prior outputs**: each passing prompt's output is injected as context into every subsequent generator call. Authors writing prompt 3 can assume that prompts 1 and 2's approved artifacts are available above their own prompt in the generator's view. Be explicit that this is the *only* cross-prompt communication channel.
7. **What the runner does around the validation prompt**: it appends a fixed instruction that the judge must end with *VERDICT: pass*, *VERDICT: revise*, or *VERDICT: escalate*. Authors must not undo or contradict this in their validation prompt body.
8. **How the revision loop behaves**: if a validation returns *revise*, the generator gets the feedback and produces a new version, up to *--max-iterations* (default 3). Authors of validation prompts should write feedback that the generator can act on — specific, line-pointed, actionable — because that feedback is all the generator has to work with on the next iteration.
9. **A short error-guide section** listing the five parser error IDs from section 6.3 (*E-NO-BLOCKS*, *E-MISSING-VALIDATION*, *E-UNCLOSED-GENERATION*, *E-UNCLOSED-VALIDATION*, *E-EXTRA-BLOCK*) with one-line explanations. This is for file authors debugging their own files — the actual error messages printed by the tool already include full repair instructions, so the README just needs to tell people what the IDs mean.
10. **How to run the tool once your file is ready**: a short example of *python -m prompt_runner parse your-file.md* to verify the structure, followed by *python -m prompt_runner run your-file.md* to execute it.
11. **A known-limitations note** for v1: triple-backtick blocks cannot be nested; all prompts run sequentially with no parallelism; only *halt* escalation policy; no resume-from-crash.

### 13.4 Constraints on the README itself

- It must be short enough to fit in a single screen when expanded — target 200-400 lines of markdown. A long README that no AI will read in full defeats the purpose.
- The worked example in section (2) above must be a real file in *tests/cli/prompt_runner/fixtures/readme-example.md*, and a parser test (*test_readme_example_parses*) must assert it parses successfully. If we ever change the input contract, this test forces the README to stay in sync.
- The "error guide" section (9) must list exactly the error IDs defined in section 6.3 of this design. A test (*test_error_ids_match_readme*) greps the README for each ID from the code's error catalogue and fails if any are missing.

### 13.5 Out of scope for the README

- Tool installation and Python environment setup — belongs in the project's top-level README, not this one.
- Details of the revision-loop internals, session ID naming, or storage layout — file authors don't need to know those.
- Every option of the *run* subcommand — that's what *--help* is for. The README shows only *parse* and the simplest *run*.

## 14. Acceptance criteria

This section serves two purposes: enumerate every user requirement that drove the design, and provide a traceable check that the spec captures each one. A separate document, *docs/testing/AC-001-prompt-runner.md*, contains the implementation acceptance criteria — runnable checks that verify the eventual code matches this design. **The two layers are intentionally separate**: design ACs live here because they verify the spec; implementation ACs live in *AC-001* because they verify the code. You cannot meaningfully run implementation ACs until the design ACs in this section all pass.

### 14.1 Requirements enumerated

Extracted from the brainstorming conversation that produced this design. If any of these are missing or have drifted from the user's intent, the design is not yet ready for implementation.

| REQ | Description | Source |
|---|---|---|
| REQ-1 | Parse a markdown file containing prompts. | Initial request |
| REQ-2 | Each prompt has a matching validation prompt. | Initial request |
| REQ-3 | Run each prompt through the Claude Code CLI. | Initial request |
| REQ-4 | Run the validation prompt for each generated output. | Initial request |
| REQ-5 | If validation returns feedback, loop back and feed the feedback to the agent that produced the original. | Initial request |
| REQ-6 | Step-1 deliverable: a dummy script that parses the file and prints prompts with their validation prompts. | Initial request |
| REQ-7 | Step-2 deliverable: run the prompts as one-shot CLI calls (not interactive, not long-running sessions). | Initial request |
| REQ-8 | Generator and judge sessions must be independent — no shared context to avoid contamination. | Session-handling clarification |
| REQ-9 | Both the generator and the judge benefit from continuity within their own history across revision iterations. | Session-handling clarification |
| REQ-10 | Prior prompts' generator and judge sessions are discarded — fresh session per new prompt. | Hybrid-approach summary, approved |
| REQ-11 | Scope must be explicit — no hidden second pass, no silent MVP scoping. | "I'm not sure what you mean by MVP" |
| REQ-12 | Do not build the elaborate orchestration described inside the prompts — just run them and verify them. | "we just need to run the prompts and verify them" |
| REQ-13 | The runner must be content-agnostic — work on any markdown file with the same structure, not just the motivating file. | "Don't code the script to match the specific prompts in the file" |
| REQ-14 | The parser must accept files written to the structural contract but with flexibility in non-structural details. | "are you sure keeping the regexes strict will allow you to use a different file of prompts?" |
| REQ-15 | Error messages must be friendly and include: prompt name, line number, and whether it's the generation or validation prompt that is missing or wrong. | "the error handling is not very friendly..." |
| REQ-16 | Error messages must not rely on jargon like *fence* that end users will not recognise. | "end users won't be helped by fences" |
| REQ-17 | A companion README must exist so AIs and humans know how to create prompt files for the runner. | "We're going to need a README so AIs will know how to create the prompts" |
| REQ-18 | The tool name is *prompt-runner*, not *methodology-runner*. | "this is a prompt runner not a methodology runner" |
| REQ-19 | The heading regex must not require a number after *## Prompt*. | "the regex doesn't have to match a number after the ## Prompt" |
| REQ-20 | Capture stdout and stderr of each claude invocation and save them in a logs folder. | "we should capture the stdout and stderr for each invocation and save them in a logs folder" |
| REQ-21 | Display the last error prominently when the tool halts. | "Also display the last error" |
| REQ-22 | Stream the output as execution happens, don't buffer until completion. | "Stream the output as execution happens" |
| REQ-23 | The companion README's "how to install" content is about *prompt-runner* itself, not about tools used by Claude Code. | "Not sure what you mean by tool-installation..." |
| REQ-24 | Acceptance criteria for the design document itself must exist and trace back to the requirements. | "go back to all the requirements and identify acceptance criteria for the design document itself" |

### 14.2 Design acceptance criteria

Each DAC below is verifiable by reading this document — a section lookup, a grep, or a test-case-listed check. If even one DAC fails, the design is not ready and coding should not begin.

| DAC | REQ | Check | Verify against |
|---|---|---|---|
| **DAC-1** | REQ-1, REQ-2 | A *PromptPair* data structure is defined with both *generation_prompt* and *validation_prompt* string fields. | §6.1 data model |
| **DAC-2** | REQ-1, REQ-14 | An input-file contract is defined in structural terms (heading pattern, fenced-block count, ordering) with no content-specific assumptions. | §3 input contract |
| **DAC-3** | REQ-3 | Invoking the *claude* CLI as a subprocess via *claude -p* with the prompt body on stdin is specified. | §7.1 real implementation |
| **DAC-4** | REQ-4 | The per-prompt flow invokes the Claude client once for the generation prompt and once for the validation prompt per iteration. | §9.3 — the for-loop body has two *claude_client.call()* sites, one per role |
| **DAC-5** | REQ-5 | A revision loop is defined that, on a *REVISE* verdict, invokes the generator with the judge's feedback, up to *max_iterations*. | §9.3 loop + §9.4 *build_revision_generator_message* |
| **DAC-6** | REQ-6 | A *parse* subcommand is defined that reads the file and prints prompt pairs to stdout, making zero Claude calls. | §5 CLI shape + §12 implementation order step 3 |
| **DAC-7** | REQ-7 | Claude client calls are synchronous, one-shot *Popen* invocations that end before the next call starts — no persistent Claude process. | §7.1 real implementation |
| **DAC-8** | REQ-8 | For every prompt, the runner allocates two distinct session IDs (*gen_session*, *jud_session*) and never passes the same ID to both roles. | §9.3 + *test_session_id_naming* in §9.5 |
| **DAC-9** | REQ-9 | Within a revision loop, the generator's session is resumed across iterations (iter-1 with *--session-id*, iter-2+ with *--resume*), and so is the judge's. | §9.3 *is_first* branch + *test_resume_flag_set_on_iterations_after_first* in §9.5 |
| **DAC-10** | REQ-10 | Session IDs incorporate the prompt's positional index, so prompt N's sessions are distinct from prompt N-1's. | §9.3 — session IDs are *gen-prompt-{pair.index}-{run_id}* and *jud-prompt-{pair.index}-{run_id}* |
| **DAC-11** | REQ-11 | An explicit Out-of-scope list exists that prevents silent scope creep. | §2 In-scope / Out-of-scope |
| **DAC-12** | REQ-12 | The Out-of-scope list explicitly excludes the orchestration machinery described inside the motivating file. | §2 Out of scope, final bullet |
| **DAC-13** | REQ-13 | Content-agnosticism is stated as a first-class property, and no load-bearing content-specific tokens appear in the design. Verify by grepping this document for *phase processing unit*, *methodology*, *traceability*, *simulation* — each appears only in §1's motivating-file note or §2's out-of-scope list, never as a design assumption. | §1 purpose + §2 + grep |
| **DAC-14** | REQ-14 | The parser design specifies non-invariants explicitly: subsection headers may use any wording or be absent, and role is determined by fenced-block ordering not by label matching. | §3 non-invariants + §6.2 algorithm (no label match in the state transitions) |
| **DAC-15** | REQ-15 | Every error catalogue entry includes: the prompt's positional index, the prompt's title, the heading line number, and a concrete repair instruction. Where the error involves a specific role, the message explicitly says *generation prompt* or *validation prompt*. | §6.3 (each error template contains all four fields; E-MISSING-VALIDATION and E-UNCLOSED-\* name the role) |
| **DAC-16** | REQ-16 | Every user-facing error message template uses *fenced code block* or *triple backticks*, never the bare word *fence*. Verified by running *grep -n "\bfence\b"* on this document and confirming no matches fall inside any error template (matches inside design prose, state machine docs, and test names are acceptable). | §6.3, §11.2, plus grep — verified passing as of this writing |
| **DAC-17** | REQ-17 | A companion README is specified, including its audience (AI and human file authors), its required contents (11 numbered items), and the self-tests that keep it in sync with the design. | §13 entire section |
| **DAC-18** | REQ-18 | The design doc is titled *Prompt Runner*, the filename is *CD-001-prompt-runner.md*, the package path is *src/cli/prompt_runner/*, and the CLI entry point is *python -m prompt_runner*. No references to *methodology-runner* or *methodology_runner* anywhere. Verified by *grep -Ei "methodology[-_ ]?[Rr]unner\|Methodology Runner"* on this document returning zero matches. | §1 title, §4 module layout, §5 CLI, plus grep — verified passing as of this writing |
| **DAC-19** | REQ-19 | The heading regex listed in Section 3 accepts five documented forms, including unnumbered variants. Test cases for each form are listed in the parser test list. | §3 invariant 1 + §6.4 test cases *test_accepts_numbered_heading*, *test_accepts_unnumbered_heading_with_colon*, *test_accepts_unnumbered_heading_without_colon*, *test_accepts_em_dash_separator*, *test_empty_title_becomes_untitled* |
| **DAC-20** | REQ-20 | The storage layout has a *logs/* subtree under each run directory, containing *.stdout.log* and *.stderr.log* per invocation. The *ClaudeCall* data structure carries *stdout_log_path* and *stderr_log_path* fields. The real client writes to both log files while streaming. | §10 storage layout + §7.1 *ClaudeCall* + §7.1 streaming description steps 4–5 |
| **DAC-21** | REQ-21 | When the pipeline halts, the runner prints a framed error block to stderr *after all streamed output has finished*, so the error is the last thing on the terminal. A matching success banner exists for exit-0 runs. | §11.3 step 4 + §11.4 |
| **DAC-22** | REQ-22 | The real Claude client uses *subprocess.Popen* with line-buffered stdout and iterates line-by-line, writing each line to the terminal as it arrives. A concurrent stderr reader thread prevents pipe-buffer deadlock. | §7.1 "Streaming, log capture, and concurrent stderr reading" section + *test_real_client_streams_stdout_to_terminal* in §7.4 |
| **DAC-23** | REQ-23 | The README's audience is explicitly *AI and human file authors*, not end users running the CLI. Tool-installation instructions are listed as out-of-scope for this README because they belong in the project's top-level README. | §13.1 audience + §13.5 out of scope |
| **DAC-24** | REQ-24 | This section (§14) enumerates every requirement and provides a traceability check for each one, and points at a companion document (*AC-001*) for implementation-level acceptance criteria. | §14 — this section itself |

### 14.3 Implementation acceptance criteria

Runnable verification of the finished code lives in `docs/testing/AC-001-prompt-runner.md`. That document contains 37 implementation ACs grouped by module (parser, runner, session handling, streaming/logs, README consistency, cross-cutting correctness). Each AC traces back to one or more REQs in §14.1 and to the design section it derives from. Implementation ACs may only be meaningfully evaluated after the design ACs in §14.2 all pass — design-level consistency is a prerequisite for implementation-level verification.

### 14.4 Sign-off gate

Before the writing-plans skill is invoked to produce an implementation plan from this spec, all 24 design ACs in §14.2 must be verified passing. Two (DAC-16 and DAC-18) are grep-backed and have been verified passing. The remaining 22 are section-lookup checks that the user is expected to review.
