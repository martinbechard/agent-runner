# Prompt-Runner Variant Testing & Audit Improvement

**Status:** Working spec — evolving during the design session
**Date:** 2026-04-10
**Related:**
- `.prompt-runner/src/cli/prompt_runner/runner.py`
- `.prompt-runner/src/cli/prompt_runner/parser.py`

---

## 1. Problem

The methodology-runner's audit/verification prompts (e.g.,
`prompt-02-coverage-hardening-and-compound-splitting`) use a single long
task list that the generator walks through sequentially. This produces
high turn counts (16 turns), heavy TodoWrite overhead (27% of time),
and is hard to evaluate because the prompt structure mixes extraction
and judgment in one pass.

We want to A/B test an alternative: a two-checklist approach where:

- **Checklist A (extraction):** identifies items without inference —
  raw mechanical finding (e.g., "section 3 has no RI-* items")
- **Checklist B (judgment):** applied on checklist A's output to decide
  severity and meaning (e.g., "the omission in section 3 is blocking
  because it contains a shall-statement")

To compare this against the existing approach, we need **native variant
testing in prompt-runner** — the ability to fork execution at a specific
prompt, run two (or more) variants in parallel, and produce separate
result workspaces for comparison.

## 2. Variant testing in prompt-runner

### 2.1 User-facing model

A prompt-runner input file can contain VARIANT sections that define
alternative prompts to test at a fork point:

```markdown
## Prompt 1: Extract requirements

```
generation prompt for step 1
```

```
validation prompt for step 1
```

## Prompt 2: Audit coverage [VARIANTS]

### Variant A: Long task list (current approach)

```
the current long-form audit prompt
```

```
validation for variant A
```

### Variant B: Two-pass checklist

```
checklist-based extraction prompt
```

```
validation for variant B
```

## Prompt 3: Final verification

```
generation prompt that runs after whichever variant was chosen
```

```
validation for step 3
```
```

### 2.2 Execution semantics

When prompt-runner encounters a `[VARIANTS]` prompt:

1. The workspace is at the state left by prompt 1 (all prior prompts
   have run and passed).
2. For each variant (A, B, ...):
   a. Copy the current workspace to a variant-specific directory
      (e.g., `<run-dir>/variant-a/workspace/`)
   b. Spawn a new prompt-runner process (or thread) that:
      - Starts with the variant's prompt as the current prompt
      - Continues with all subsequent prompts (prompt 3, etc.)
      - Writes results to the variant's own run directory
3. The parent waits for all variants to complete.
4. Results are available as separate workspace directories for manual
   comparison or automated diff.

### 2.3 Process model

Subprocess is cleaner than threading:

- Each variant runs as a separate `prompt-runner run` invocation with
  `--workspace` pointing at the copied workspace and `--only` or
  `--start-from` pointing at the variant's prompt number
- The parent orchestrates: copy workspace, spawn N subprocesses, wait
  for all, report
- No shared state, no locking, no GIL concerns
- Each variant's Claude calls are independent sessions

### 2.4 Parser changes

The `[VARIANTS]` marker on a `## Prompt N:` heading signals a fork
point. The subsections (`### Variant A:`, `### Variant B:`) each
contain their own code-fenced prompt pair(s).

Parser produces a new structure:

```python
@dataclass(frozen=True)
class VariantPrompt:
    variant_name: str        # "A", "B", etc.
    variant_title: str       # "Long task list", "Two-pass checklist"
    pairs: list[PromptPair]  # the prompt pair(s) for this variant

@dataclass(frozen=True)
class ForkPoint:
    index: int               # prompt number where the fork occurs
    title: str               # e.g., "Audit coverage"
    variants: list[VariantPrompt]
```

A prompt file is then a sequence of `PromptPair | ForkPoint` items.

### 2.5 Runner changes

`run_pipeline` needs to handle `ForkPoint` items:

1. When a `ForkPoint` is encountered:
   - Snapshot the current workspace
   - For each variant:
     - Copy the snapshot to a variant workspace
     - Build a synthetic prompt list: variant's pairs + all subsequent
       prompts from the original file
     - Spawn `prompt-runner run <synthetic-file> --workspace <variant-ws>`
       as a subprocess
   - Wait for all subprocesses
   - Collect results from each variant's run directory

2. The parent process does NOT continue past the fork point. It only
   reports which variants completed and where their results are.

### 2.6 Output structure

```
runs/<timestamp>-<stem>/
  prompt-01-extract-requirements/       # normal prompt result
  fork-02-audit-coverage/
    variant-a/
      workspace/                        # copied workspace
      run/                              # prompt-runner run output
        prompt-02a-long-task-list/
        prompt-03-final-verification/
    variant-b/
      workspace/
      run/
        prompt-02b-two-pass-checklist/
        prompt-03-final-verification/
  summary.txt                           # comparison summary
```

### 2.7 Resume semantics

`--resume` skips completed prompts up to the fork point. If the fork
point is reached:

- If ALL variants have completed results, skip the fork entirely
- If SOME variants completed, re-run only the incomplete ones
- The variant's own run directory has its own `final-verdict.txt` files
  so the sub-invocation's `--resume` works within each variant

### 2.8 Comparison report

After all variants complete, the parent generates a comparison summary:

- Wall time per variant
- Cost per variant (from result events)
- Output diff (structural comparison of the final workspace artifacts)
- Which variant's judge passed/failed and at which prompt

This could integrate with the timeline report
(`tools/report/scripts/run-timeline.py`)
to produce a side-by-side view.

## 3. Applying variants to the audit improvement

### 3.1 The hypothesis

The current audit prompt (`prompt-02-coverage-hardening-and-compound-splitting`)
is a single long task list producing 16 turns and 27% TodoWrite overhead.

The alternative hypothesis: splitting into two focused checklists
(extraction then judgment) will:

- Reduce turn count (each checklist is a single focused pass)
- Eliminate TodoWrite overhead (checklists are the artifact, not tasks)
- Produce more structured, comparable output
- Be easier for the judge to evaluate

### 3.2 Variant A: Current approach (control)

The existing prompt-02 from the prompt-file.md — a long task list that
walks the source document, checks coverage, splits compounds, verifies
categories, etc.

### 3.3 Variant B: Two-pass checklist

**Pass 1 — Extraction checklist:**

Read the source document section by section. For each section, produce
a checklist entry with:

- section_id: which section of the source
- source_text: exact text from the section
- inventory_items: list of RI-* IDs that trace to this section
- finding: one of "covered", "partial", "missing"
- evidence: the verbatim_quotes from the matching RI-* items

No inference, no judgment. Pure mechanical cross-referencing.

**Pass 2 — Judgment checklist:**

Read the extraction checklist. For each entry with finding != "covered":

- severity: blocking | warning | info
- reason: why this finding matters (compound not split, section omitted,
  category wrong, nuance lost)
- recommendation: specific fix (split RI-003 into two items, add
  RI-018 for the constraint in section 4.2)

This pass is where judgment happens, cleanly separated from extraction.

### 3.4 Success criteria

Variant B wins if:

- Fewer turns than Variant A
- Lower cost (fewer output tokens)
- Equal or better coverage detection (finds the same issues)
- Structured output that's easier for the judge to verify
- Lower TodoWrite overhead (ideally zero)

### 3.5 Timeline report integration

After running both variants, use `tools/report/scripts/run-timeline.py` on each
variant's workspace to produce side-by-side timing breakdowns. The
comparison should make the cost/quality tradeoff visible.

## 4. Open questions

- Should variants share a single Claude session (via --resume) or start
  fresh? Fresh is simpler and avoids session-state contamination between
  variants.
- Should the fork mechanism support more than 2 variants? Yes — design
  for N variants but the audit improvement only uses 2.
- Should variants run in parallel or sequential? Parallel is faster but
  uses more subscription quota simultaneously. Make it configurable:
  `--variant-parallel` (default) vs `--variant-sequential`.
- How does the interactive `[interactive]` marker interact with
  `[VARIANTS]`? Probably not supported — variants are for automated
  A/B testing, not interactive sessions. Flag an error if both markers
  are present on the same prompt.
- The two-pass checklist approach requires prompt-02 to become TWO
  prompts (extraction + judgment). Does each variant support multiple
  prompts, or just one? Multiple — each variant's subsection can
  contain more than one code-fenced pair, and they execute sequentially
  within the variant.

## 5. Implementation order

1. **Parser:** recognize `[VARIANTS]` marker, parse `### Variant X:`
   subsections with their own code-fenced pairs.
2. **Runner:** implement fork-point handling — workspace copy, subprocess
   spawn, wait, collect results.
3. **CLI:** add `--variant-parallel` / `--variant-sequential` flags.
4. **Comparison report:** generate a summary comparing variant results.
5. **Author the variant prompt file:** write the actual A/B test for
   the audit improvement using the new mechanism.
6. **Run the test:** execute, compare results, pick the winner.
7. **Timeline integration:** side-by-side timing report for variants.

## 6. Notes from the session

- The problem was identified via the timeline report showing 27%
  TodoWrite overhead in the generator call for prompt-02.
- The two-checklist approach is inspired by the traceability-discipline
  skill's separation of extraction (Quote Test) from judgment
  (severity assessment).
- The variant mechanism is general-purpose — it can be used for any
  prompt engineering A/B test, not just audit improvement. It's the
  natural next step after the "test all variants with claude -p"
  approach used in skill authoring, scaled up to full pipeline testing.
