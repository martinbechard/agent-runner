# AC-001 — Prompt Runner Implementation Acceptance Criteria

Runnable checks that the `prompt-runner` implementation matches the current heading-based design.

## 1. Parsing

- `AC-01`: The parser returns `PromptPair` objects with title, positional index, prompt bodies, and subsection line numbers.
  Verification: `tests/cli/prompt_runner/test_parser.py::test_parses_minimal_two_prompt_file`

- `AC-02`: Prompt headings accept the documented `## Prompt ...` variants and ignore authored numbering.
  Verification: heading tests in `tests/cli/prompt_runner/test_parser.py`

- `AC-03`: Prompt metadata subsections are parsed before generation.
  Verification: `tests/cli/prompt_runner/test_parser.py::test_required_checks_and_deterministic_sections_are_parsed`

- `AC-04`: Validator-less prompts are accepted.
  Verification: interactive and validator-less coverage in `tests/cli/prompt_runner/test_parser.py` and `tests/cli/prompt_runner/test_smoke_interactive.py`

## 2. Variants

- `AC-05`: A `[VARIANTS]` prompt parses into a `ForkPoint` with named variants.
  Verification: `tests/cli/prompt_runner/test_parser_variants.py::test_simple_fork_with_two_variants`

- `AC-06`: Variant prompts support multiple prompt pairs and per-variant model or effort overrides.
  Verification: `tests/cli/prompt_runner/test_parser_variants.py`

- `AC-07`: Synthetic prompt files emitted for variant subprocesses use the same heading-only format.
  Verification: `tests/cli/prompt_runner/test_runner_variants.py::test_serialize_pairs_to_md` and `::test_serialize_pair_without_validator`

## 3. Error handling

- `AC-08`: Missing generation sections raise `E-NO-GENERATION`.
  Verification: `tests/cli/prompt_runner/test_parser.py::test_error_no_generation`

- `AC-09`: Misordered sections raise `E-BAD-SECTION-ORDER`.
  Verification: `tests/cli/prompt_runner/test_parser.py::test_error_validation_before_generation` and `::test_error_late_required_files`

- `AC-10`: Duplicate sections raise `E-DUPLICATE-SECTION`.
  Verification: `tests/cli/prompt_runner/test_parser.py::test_error_duplicate_section`

- `AC-11`: Unknown reserved-level subsections raise `E-UNKNOWN-SUBSECTION`.
  Verification: `tests/cli/prompt_runner/test_parser.py::test_error_unknown_subsection`

- `AC-12`: Variant prompts with no `### Variant ...` subsections raise `E-NO-VARIANTS`.
  Verification: `tests/cli/prompt_runner/test_parser_variants.py::test_variants_with_no_subsections_raises`

## 4. CLI and README

- `AC-13`: The `parse` subcommand reports parsed prompts and parser errors against the heading-only format.
  Verification: parser CLI coverage in `tests/cli/prompt_runner/test_runner.py`

- `AC-14`: Runner-owned temporary state is written under `run_dir/.run-files`, while project-visible artifacts remain in the run worktree root.
  Verification: `tests/cli/prompt_runner/test_runner.py` and `tests/cli/prompt_runner/test_runner_variants.py`

- `AC-15`: The README example remains parseable and the README lists all parser error IDs.
  Verification: `tests/cli/prompt_runner/test_readme.py`

## 5. End-to-end

- `AC-16`: Mixed normal, validator-less, and interactive prompts run successfully and resume correctly.
  Verification: `tests/cli/prompt_runner/test_smoke_interactive.py`

- `AC-17`: The prompt-runner test suite passes.
  Verification: `pytest tests/cli/prompt_runner`
