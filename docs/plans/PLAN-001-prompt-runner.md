# Prompt Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Build a Python CLI tool that parses a markdown file of prompt/validator pairs, runs each through the Claude CLI with a revision loop, captures streaming output and per-invocation logs, and halts on escalation.

**Architecture:** Single Python package under *src/cli/prompt_runner/*. Pure-logic modules (parser, verdict) are tested first; a Claude-client protocol with fake/dry-run/real implementations decouples the runner from subprocess details. The real client uses *subprocess.Popen* with a concurrent stderr reader thread to stream stdout line-by-line to the terminal while tee-writing to per-invocation log files.

**Tech Stack:** Python 3.12, standard library only for runtime code (*subprocess*, *pathlib*, *re*, *dataclasses*, *threading*, *argparse*, *enum*, *json*). *pytest* as the only dev dependency. Packaging via *setuptools* declared in *pyproject.toml*.

**Parent artifacts:**
- Design: *docs/design/components/CD-001-prompt-runner.md*
- Design ACs: §14 of the design doc
- Implementation ACs: *docs/testing/AC-001-prompt-runner.md*

**Coding rules the engineer must respect:**
- Files under *tests/cli/prompt_runner/* mirror files under *src/cli/prompt_runner/*.
- Python modules use *snake_case.py*.
- Never use *Any* where a specific type exists.
- Never use *--no-lint* or skip hooks in commits.
- Markdown files (including this plan's generated README) must not use inline single backticks — only triple-backtick fenced blocks. Italicise paths and identifiers in prose.
- No emojis in generated files.
- Every code change is followed by running the tests. No "I'll run them at the end" batching.

---

## File structure (locked in before task decomposition)

Files to create:

```
pyproject.toml                                     # new — Python packaging
src/cli/prompt_runner/__init__.py                  # new — package marker
src/cli/prompt_runner/__main__.py                  # new — CLI entry point (parse + run subcommands)
src/cli/prompt_runner/verdict.py                   # new — Verdict enum + parse_verdict()
src/cli/prompt_runner/parser.py                    # new — PromptPair dataclass + parse_file() + error catalogue
src/cli/prompt_runner/claude_client.py             # new — ClaudeCall/ClaudeResponse + Protocol + Real/Fake/DryRun implementations
src/cli/prompt_runner/runner.py                    # new — RunConfig + PromptResult + PipelineResult + run_pipeline + run_prompt + prompt builders
src/cli/prompt_runner/README.md                    # new — input-format guide for AI/human file authors

tests/cli/prompt_runner/__init__.py                # new — test package marker
tests/cli/prompt_runner/test_verdict.py            # new
tests/cli/prompt_runner/test_parser.py             # new
tests/cli/prompt_runner/test_claude_client.py      # new
tests/cli/prompt_runner/test_runner.py             # new
tests/cli/prompt_runner/test_readme.py             # new — meta-tests that keep the README in sync with the code
tests/cli/prompt_runner/fixtures/sample-prompts.md             # new — 2-prompt happy path
tests/cli/prompt_runner/fixtures/missing-validator.md          # new — E-MISSING-VALIDATION
tests/cli/prompt_runner/fixtures/no-blocks.md                  # new — E-NO-BLOCKS
tests/cli/prompt_runner/fixtures/unclosed-generation.md        # new — E-UNCLOSED-GENERATION
tests/cli/prompt_runner/fixtures/unclosed-validation.md        # new — E-UNCLOSED-VALIDATION
tests/cli/prompt_runner/fixtures/three-fences.md               # new — E-EXTRA-BLOCK
tests/cli/prompt_runner/fixtures/tagged-fences.md              # new — language-tagged fences
tests/cli/prompt_runner/fixtures/no-subsection-headers.md      # new — bare fences
tests/cli/prompt_runner/fixtures/arbitrary-subsections.md      # new — arbitrary ### headings
```

Files to modify: none — agent-runner is greenfield, no existing Python code.

---

## Task 0: Bootstrap Python package

**Files:**
- Create: *pyproject.toml*
- Create: *src/cli/prompt_runner/__init__.py*
- Create: *tests/cli/prompt_runner/__init__.py*

- [ ] **Step 0.1: Create *pyproject.toml* at the project root**

File: *pyproject.toml*

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "prompt-runner"
version = "0.1.0"
description = "Run prompt/validator pairs from a markdown file through the Claude CLI with a revision loop"
requires-python = ">=3.12"

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
prompt-runner = "prompt_runner.__main__:main"

[tool.setuptools.packages.find]
where = ["src/cli"]
include = ["prompt_runner*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 0.2: Create the package marker files**

File: *src/cli/prompt_runner/__init__.py* — empty file.

File: *tests/cli/prompt_runner/__init__.py* — empty file.

Shell:
```bash
mkdir -p src/cli/prompt_runner tests/cli/prompt_runner
touch src/cli/prompt_runner/__init__.py
touch tests/cli/prompt_runner/__init__.py
# Delete the .gitkeep placeholder that was in src/cli/
rm -f src/cli/.gitkeep
```

- [ ] **Step 0.3: Editable install**

Shell:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: the last line of pip output includes *Successfully installed prompt-runner-0.1.0 ...* and *pytest-8....*.

- [ ] **Step 0.4: Verify pytest discovers zero tests successfully**

Shell:
```bash
pytest
```

Expected: *no tests ran in X.XXs* with exit code 5 (pytest's "no tests collected" exit code, not a failure). This confirms pytest is installed and discovers the *tests/* directory.

- [ ] **Step 0.5: Verify the package imports**

Shell:
```bash
python -c "import prompt_runner; print('ok')"
```

Expected: *ok*.

- [ ] **Step 0.6: Commit**

```bash
git add pyproject.toml src/cli/prompt_runner/__init__.py tests/cli/prompt_runner/__init__.py
git rm src/cli/.gitkeep
git commit -m "chore: bootstrap prompt-runner Python package"
```

---

## Task 1: verdict.py — Verdict enum and parse_verdict()

**Files:**
- Create: *src/cli/prompt_runner/verdict.py*
- Create: *tests/cli/prompt_runner/test_verdict.py*

Design reference: §8 (Verdict parser) and §8 test list in *CD-001-prompt-runner.md*.

- [ ] **Step 1.1: Write the failing happy-path tests**

File: *tests/cli/prompt_runner/test_verdict.py*

```python
from prompt_runner.verdict import Verdict, VerdictParseError, parse_verdict
import pytest


def test_parses_pass():
    assert parse_verdict("reasoning text\n\nVERDICT: pass") == Verdict.PASS


def test_parses_revise():
    assert parse_verdict("reasoning\n\nVERDICT: revise") == Verdict.REVISE


def test_parses_escalate():
    assert parse_verdict("reasoning\n\nVERDICT: escalate") == Verdict.ESCALATE
```

- [ ] **Step 1.2: Run tests and verify they fail**

Shell:
```bash
pytest tests/cli/prompt_runner/test_verdict.py -v
```

Expected: three tests ERROR with *ModuleNotFoundError: No module named 'prompt_runner.verdict'*.

- [ ] **Step 1.3: Write the minimal implementation**

File: *src/cli/prompt_runner/verdict.py*

```python
"""Verdict enum and judge-output parser for prompt-runner."""
from __future__ import annotations

import re
from enum import Enum


class Verdict(Enum):
    PASS = "pass"
    REVISE = "revise"
    ESCALATE = "escalate"


class VerdictParseError(Exception):
    """Raised when a judge response contains no recognisable VERDICT line."""


_VERDICT_LINE = re.compile(
    r"^VERDICT:\s*(pass|revise|escalate)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def parse_verdict(judge_output: str) -> Verdict:
    """Extract a Verdict from free-text judge output.

    Rules:
    - Last match wins (the judge may reference the instruction mid-response).
    - Match is case-insensitive.
    - Zero matches raises VerdictParseError with the first 500 chars for debugging.
    """
    matches = _VERDICT_LINE.findall(judge_output)
    if not matches:
        snippet = judge_output[:500]
        raise VerdictParseError(
            f"no VERDICT line found in judge output. First 500 chars: {snippet!r}"
        )
    return Verdict(matches[-1].lower())
```

- [ ] **Step 1.4: Run tests and verify the three happy-path cases pass**

Shell:
```bash
pytest tests/cli/prompt_runner/test_verdict.py -v
```

Expected: three tests PASS.

- [ ] **Step 1.5: Add remaining tests (case-insensitivity, last-match-wins, errors, whitespace)**

Append to *tests/cli/prompt_runner/test_verdict.py*:

```python
def test_case_insensitive_keyword():
    assert parse_verdict("VERDICT: Pass") == Verdict.PASS


def test_case_insensitive_label():
    assert parse_verdict("Verdict: revise") == Verdict.REVISE


def test_takes_last_match():
    text = (
        "early on I thought maybe VERDICT: revise\n"
        "but after more thought\n"
        "VERDICT: pass"
    )
    assert parse_verdict(text) == Verdict.PASS


def test_raises_on_missing():
    with pytest.raises(VerdictParseError) as exc_info:
        parse_verdict("this has no verdict at all")
    assert "no VERDICT line" in str(exc_info.value)


def test_raises_on_unknown_value():
    with pytest.raises(VerdictParseError):
        parse_verdict("VERDICT: maybe")


def test_allows_trailing_whitespace():
    assert parse_verdict("VERDICT: pass   ") == Verdict.PASS
```

- [ ] **Step 1.6: Run all tests and verify they pass**

Shell:
```bash
pytest tests/cli/prompt_runner/test_verdict.py -v
```

Expected: nine tests PASS.

- [ ] **Step 1.7: Commit**

```bash
git add src/cli/prompt_runner/verdict.py tests/cli/prompt_runner/test_verdict.py
git commit -m "feat(prompt-runner): add Verdict enum and parse_verdict()"
```

---

## Task 2: parser.py — PromptPair dataclass and markdown parser

**Files:**
- Create: *src/cli/prompt_runner/parser.py*
- Create: *tests/cli/prompt_runner/test_parser.py*
- Create: 9 fixture files under *tests/cli/prompt_runner/fixtures/*

Design reference: §3 (input contract), §6.1 (data model), §6.2 (state machine algorithm), §6.3 (error catalogue), §6.4 (test list) in *CD-001-prompt-runner.md*.

### Subtask 2a: Fixtures and happy-path parsing

- [ ] **Step 2a.1: Create the happy-path fixture**

File: *tests/cli/prompt_runner/fixtures/sample-prompts.md*

````markdown
# Example prompt file

## Prompt 1: First Thing

### 1.1 Generation Prompt

```
Generate the first thing.
It has multiple lines.
```

### 1.2 Validation Prompt

```
Validate the first thing.
```

## Prompt 2: Second Thing

### 2.1 Generation Prompt

```
Generate the second thing.
```

### 2.2 Validation Prompt

```
Validate the second thing.
It has multiple lines too.
```
````

- [ ] **Step 2a.2: Write the failing happy-path test**

File: *tests/cli/prompt_runner/test_parser.py*

```python
from pathlib import Path

import pytest

from prompt_runner.parser import PromptPair, ParseError, parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_minimal_two_prompt_file():
    pairs = parse_file(FIXTURES / "sample-prompts.md")
    assert len(pairs) == 2

    assert pairs[0].index == 1
    assert pairs[0].title == "First Thing"
    assert pairs[0].generation_prompt == "Generate the first thing.\nIt has multiple lines."
    assert pairs[0].validation_prompt == "Validate the first thing."
    assert pairs[0].heading_line == 3

    assert pairs[1].index == 2
    assert pairs[1].title == "Second Thing"
    assert pairs[1].generation_prompt == "Generate the second thing."
    assert pairs[1].validation_prompt == "Validate the second thing.\nIt has multiple lines too."
```

- [ ] **Step 2a.3: Run test and verify it fails**

Shell:
```bash
pytest tests/cli/prompt_runner/test_parser.py::test_parses_minimal_two_prompt_file -v
```

Expected: ERROR with *ModuleNotFoundError: No module named 'prompt_runner.parser'*.

- [ ] **Step 2a.4: Write the minimal parser implementation**

File: *src/cli/prompt_runner/parser.py*

```python
"""Markdown parser for prompt-runner input files.

See docs/design/components/CD-001-prompt-runner.md sections 3, 6.1, 6.2, 6.3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# Error IDs from CD-001 §6.3. Kept as module-level constants so tests and the
# README can reference them.
ERROR_IDS = (
    "E-NO-BLOCKS",
    "E-MISSING-VALIDATION",
    "E-UNCLOSED-GENERATION",
    "E-UNCLOSED-VALIDATION",
    "E-EXTRA-BLOCK",
)


@dataclass(frozen=True)
class PromptPair:
    """A single (generation, validation) pair extracted from an input file."""

    index: int
    title: str
    generation_prompt: str
    validation_prompt: str
    heading_line: int
    generation_line: int
    validation_line: int


class ParseError(Exception):
    """Raised when the input file does not match the structural contract."""

    def __init__(self, error_id: str, message: str) -> None:
        super().__init__(message)
        self.error_id = error_id
        self.message = message


class _State(Enum):
    SEEK_HEADING = "seek_heading"
    SEEK_FIRST_FENCE = "seek_first_fence"
    IN_FIRST_FENCE = "in_first_fence"
    SEEK_SECOND_FENCE = "seek_second_fence"
    IN_SECOND_FENCE = "in_second_fence"
    SEEK_EXTRA_CHECK = "seek_extra_check"


_HEADING_RE = re.compile(r"^##\s+Prompt\b[\s:\-—0-9]*(.*?)\s*$")
_FENCE_RE = re.compile(r"^```[A-Za-z0-9_+\-]*\s*$")
_UNTITLED = "(untitled)"


@dataclass
class _Accumulator:
    """Mutable per-prompt buffer used while the state machine walks the file."""

    index: int
    title: str
    heading_line: int
    generation_line: int = 0
    validation_line: int = 0
    generation_lines: list[str] = field(default_factory=list)
    validation_lines: list[str] = field(default_factory=list)

    def to_pair(self) -> PromptPair:
        return PromptPair(
            index=self.index,
            title=self.title or _UNTITLED,
            generation_prompt="\n".join(self.generation_lines),
            validation_prompt="\n".join(self.validation_lines),
            heading_line=self.heading_line,
            generation_line=self.generation_line,
            validation_line=self.validation_line,
        )


def parse_file(path: Path) -> list[PromptPair]:
    """Parse a markdown file into a list of PromptPair objects.

    Raises ParseError (carrying an error_id from ERROR_IDS) if the file does
    not match the structural contract defined in CD-001 §3.
    """
    text = Path(path).read_text(encoding="utf-8")
    return parse_text(text)


def parse_text(text: str) -> list[PromptPair]:
    lines = text.splitlines()
    pairs: list[PromptPair] = []
    state = _State.SEEK_HEADING
    current: _Accumulator | None = None

    for line_index, line in enumerate(lines):
        line_number = line_index + 1

        heading_match = _HEADING_RE.match(line)
        if heading_match is not None:
            if current is not None:
                _raise_for_mid_prompt_heading(state, current, line_number)
                pairs.append(current.to_pair())
            title = heading_match.group(1).strip()
            current = _Accumulator(
                index=len(pairs) + 1,
                title=title,
                heading_line=line_number,
            )
            state = _State.SEEK_FIRST_FENCE
            continue

        if state is _State.SEEK_HEADING:
            continue

        assert current is not None
        fence_match = _FENCE_RE.match(line)

        if state is _State.SEEK_FIRST_FENCE:
            if fence_match is not None:
                current.generation_line = line_number
                state = _State.IN_FIRST_FENCE
            continue

        if state is _State.IN_FIRST_FENCE:
            if fence_match is not None:
                state = _State.SEEK_SECOND_FENCE
            else:
                current.generation_lines.append(line)
            continue

        if state is _State.SEEK_SECOND_FENCE:
            if fence_match is not None:
                current.validation_line = line_number
                state = _State.IN_SECOND_FENCE
            continue

        if state is _State.IN_SECOND_FENCE:
            if fence_match is not None:
                state = _State.SEEK_EXTRA_CHECK
            else:
                current.validation_lines.append(line)
            continue

        if state is _State.SEEK_EXTRA_CHECK:
            if fence_match is not None:
                raise ParseError(
                    "E-EXTRA-BLOCK",
                    _format_extra_block(current, extra_line=line_number),
                )
            continue

    # End of file handling.
    if current is not None:
        if state in (_State.SEEK_HEADING, _State.SEEK_EXTRA_CHECK):
            pairs.append(current.to_pair())
        else:
            _raise_for_eof(state, current, eof_line=len(lines))

    return pairs


def _raise_for_mid_prompt_heading(
    state: _State, current: _Accumulator, next_heading_line: int
) -> None:
    """Raise the appropriate error when a new heading arrives mid-prompt."""
    if state is _State.SEEK_FIRST_FENCE:
        raise ParseError(
            "E-NO-BLOCKS",
            _format_no_blocks(current, next_boundary_line=next_heading_line,
                              boundary_kind="heading"),
        )
    if state is _State.SEEK_SECOND_FENCE:
        raise ParseError(
            "E-MISSING-VALIDATION",
            _format_missing_validation(current, next_boundary_line=next_heading_line,
                                       boundary_kind="heading"),
        )
    if state is _State.IN_FIRST_FENCE:
        raise ParseError(
            "E-UNCLOSED-GENERATION",
            _format_unclosed(current, role="generation",
                             next_boundary_line=next_heading_line,
                             boundary_kind="heading"),
        )
    if state is _State.IN_SECOND_FENCE:
        raise ParseError(
            "E-UNCLOSED-VALIDATION",
            _format_unclosed(current, role="validation",
                             next_boundary_line=next_heading_line,
                             boundary_kind="heading"),
        )


def _raise_for_eof(state: _State, current: _Accumulator, eof_line: int) -> None:
    if state is _State.SEEK_FIRST_FENCE:
        raise ParseError(
            "E-NO-BLOCKS",
            _format_no_blocks(current, next_boundary_line=eof_line, boundary_kind="eof"),
        )
    if state is _State.SEEK_SECOND_FENCE:
        raise ParseError(
            "E-MISSING-VALIDATION",
            _format_missing_validation(current, next_boundary_line=eof_line,
                                       boundary_kind="eof"),
        )
    if state is _State.IN_FIRST_FENCE:
        raise ParseError(
            "E-UNCLOSED-GENERATION",
            _format_unclosed(current, role="generation",
                             next_boundary_line=eof_line, boundary_kind="eof"),
        )
    if state is _State.IN_SECOND_FENCE:
        raise ParseError(
            "E-UNCLOSED-VALIDATION",
            _format_unclosed(current, role="validation",
                             next_boundary_line=eof_line, boundary_kind="eof"),
        )


def _format_no_blocks(
    current: _Accumulator, next_boundary_line: int, boundary_kind: str
) -> str:
    boundary_text = (
        f"The next prompt heading was found at line {next_boundary_line}"
        if boundary_kind == "heading"
        else "The file ended"
    )
    return (
        f'Prompt {current.index} "{current.title}" (line {current.heading_line}): '
        f"no generation prompt or validation prompt was found in this section.\n\n"
        f"Each prompt section must contain two fenced code blocks, in order:\n"
        f"  1. the generation prompt (delimited by a line of exactly ``` at the start\n"
        f"     and another line of exactly ``` at the end)\n"
        f"  2. the validation prompt (same delimiters)\n\n"
        f"{boundary_text} before either block appeared. "
        f"Add both blocks between line {current.heading_line} and line {next_boundary_line}."
    )


def _format_missing_validation(
    current: _Accumulator, next_boundary_line: int, boundary_kind: str
) -> str:
    boundary_text = (
        f"The next prompt heading was found at line {next_boundary_line}"
        if boundary_kind == "heading"
        else "The file ended"
    )
    return (
        f'Prompt {current.index} "{current.title}" (line {current.heading_line}): '
        f"the generation prompt was found (starting at line {current.generation_line}), "
        f"but the validation prompt is missing.\n\n"
        f"Each prompt section must contain two fenced code blocks. After the closing "
        f"triple-backtick line of the generation prompt, add a second fenced code "
        f"block containing the validation prompt.\n\n"
        f"{boundary_text} before the validation block appeared. "
        f"Add the validation block before line {next_boundary_line}."
    )


def _format_unclosed(
    current: _Accumulator, role: str, next_boundary_line: int, boundary_kind: str
) -> str:
    opened_line = (
        current.generation_line if role == "generation" else current.validation_line
    )
    boundary_text = (
        f"the next prompt heading (found at line {next_boundary_line})"
        if boundary_kind == "heading"
        else "the end of the file"
    )
    return (
        f'Prompt {current.index} "{current.title}" (line {current.heading_line}): '
        f"the {role} prompt's code block was opened at line {opened_line} but never "
        f"closed.\n\n"
        f"A code block is closed by a line containing exactly ``` (three backticks "
        f"with nothing else on the line). Add that line somewhere between line "
        f"{opened_line} and {boundary_text}.\n\n"
        f"Common cause: the body of the {role} prompt itself contains a line of "
        f"triple backticks, which the parser interprets as the end of the code "
        f"block. If you need to show a code example inside the prompt, indent it "
        f"four spaces instead of wrapping it in triple backticks."
    )


def _format_extra_block(current: _Accumulator, extra_line: int) -> str:
    return (
        f'Prompt {current.index} "{current.title}" (line {current.heading_line}): '
        f"an unexpected third code block was found, opening at line {extra_line}.\n\n"
        f"Each prompt section must contain exactly two fenced code blocks: the "
        f"generation prompt (found at line {current.generation_line}) and the "
        f"validation prompt (found at line {current.validation_line}). Any "
        f"additional fenced code block before the next prompt heading is an error.\n\n"
        f"Likely causes:\n"
        f"  - You included an example as a fenced code block inside the validation\n"
        f"    prompt. Indent the example four spaces instead, or describe it in prose.\n"
        f"  - You intended to start a new prompt but used \"##\" with a different word\n"
        f"    instead of \"## Prompt\".\n\n"
        f"Fix: either remove the extra code block at line {extra_line}, or start a "
        f"new prompt section with a \"## Prompt ...\" heading before it."
    )
```

- [ ] **Step 2a.5: Run the happy-path test and verify it passes**

Shell:
```bash
pytest tests/cli/prompt_runner/test_parser.py::test_parses_minimal_two_prompt_file -v
```

Expected: PASS.

- [ ] **Step 2a.6: Commit**

```bash
git add src/cli/prompt_runner/parser.py tests/cli/prompt_runner/test_parser.py tests/cli/prompt_runner/fixtures/sample-prompts.md
git commit -m "feat(prompt-runner): add parser with happy-path parsing"
```

### Subtask 2b: Heading variants

- [ ] **Step 2b.1: Add heading-variant tests**

Append to *tests/cli/prompt_runner/test_parser.py*:

```python
from prompt_runner.parser import parse_text


_TWO_EMPTY_BLOCKS = "```\ngen\n```\n\n```\nval\n```\n"


def _wrap(heading: str) -> str:
    return f"{heading}\n\n{_TWO_EMPTY_BLOCKS}"


def test_accepts_numbered_heading():
    pairs = parse_text(_wrap("## Prompt 1: Phase Processing Unit"))
    assert pairs[0].title == "Phase Processing Unit"
    assert pairs[0].index == 1


def test_accepts_unnumbered_heading_with_colon():
    pairs = parse_text(_wrap("## Prompt: Phase Processing Unit"))
    assert pairs[0].title == "Phase Processing Unit"


def test_accepts_unnumbered_heading_without_colon():
    pairs = parse_text(_wrap("## Prompt Phase Processing Unit"))
    assert pairs[0].title == "Phase Processing Unit"


def test_accepts_em_dash_separator():
    pairs = parse_text(_wrap("## Prompt 3 — Agent Roles"))
    assert pairs[0].title == "Agent Roles"


def test_empty_title_becomes_untitled():
    pairs = parse_text(_wrap("## Prompt"))
    assert pairs[0].title == "(untitled)"


def test_positional_index_ignores_heading_number():
    text = (
        "## Prompt 5: A\n\n" + _TWO_EMPTY_BLOCKS + "\n"
        "## Prompt 10: B\n\n" + _TWO_EMPTY_BLOCKS
    )
    pairs = parse_text(text)
    assert len(pairs) == 2
    assert pairs[0].index == 1
    assert pairs[0].title == "A"
    assert pairs[1].index == 2
    assert pairs[1].title == "B"
```

- [ ] **Step 2b.2: Run the new tests and verify they pass**

Shell:
```bash
pytest tests/cli/prompt_runner/test_parser.py -v
```

Expected: all heading tests PASS (the existing regex already handles these cases).

- [ ] **Step 2b.3: Commit**

```bash
git add tests/cli/prompt_runner/test_parser.py
git commit -m "test(prompt-runner): verify parser accepts all heading variants"
```

### Subtask 2c: Fence variants and body preservation

- [ ] **Step 2c.1: Create the fence-variant fixtures**

File: *tests/cli/prompt_runner/fixtures/tagged-fences.md*

````markdown
## Prompt 1: Tagged

```text
Generator body with text language tag.
```

```markdown
Validator body with markdown language tag.
```
````

File: *tests/cli/prompt_runner/fixtures/no-subsection-headers.md*

````markdown
## Prompt 1: Bare

```
Generator, no subheading.
```

```
Validator, no subheading.
```
````

File: *tests/cli/prompt_runner/fixtures/arbitrary-subsections.md*

````markdown
## Prompt 1: Custom

### Anything Goes

```
Generator body.
```

### Whatever I Want

```
Validator body.
```
````

- [ ] **Step 2c.2: Add fence-variant tests**

Append to *tests/cli/prompt_runner/test_parser.py*:

```python
def test_accepts_language_tagged_fences():
    pairs = parse_file(FIXTURES / "tagged-fences.md")
    assert len(pairs) == 1
    assert pairs[0].generation_prompt == "Generator body with text language tag."
    assert pairs[0].validation_prompt == "Validator body with markdown language tag."


def test_accepts_no_subsection_headers():
    pairs = parse_file(FIXTURES / "no-subsection-headers.md")
    assert len(pairs) == 1
    assert pairs[0].generation_prompt == "Generator, no subheading."
    assert pairs[0].validation_prompt == "Validator, no subheading."


def test_accepts_arbitrary_subsection_headers():
    pairs = parse_file(FIXTURES / "arbitrary-subsections.md")
    assert len(pairs) == 1
    assert pairs[0].generation_prompt == "Generator body."
    assert pairs[0].validation_prompt == "Validator body."


def test_preserves_body_verbatim():
    text = (
        "## Prompt 1: Tricky\n\n"
        "```\n"
        "## Fake Prompt 99: Not real\n"
        "### Fake subheading\n"
        "just body text\n"
        "```\n\n"
        "```\n"
        "validator\n"
        "```\n"
    )
    pairs = parse_text(text)
    assert len(pairs) == 1
    assert "Fake Prompt 99" in pairs[0].generation_prompt
    assert "Fake subheading" in pairs[0].generation_prompt


def test_strips_fences_from_body():
    pairs = parse_file(FIXTURES / "sample-prompts.md")
    for pair in pairs:
        assert not pair.generation_prompt.startswith("```")
        assert not pair.generation_prompt.endswith("```")
        assert not pair.validation_prompt.startswith("```")
        assert not pair.validation_prompt.endswith("```")
```

- [ ] **Step 2c.3: Run and verify the new tests pass**

Shell:
```bash
pytest tests/cli/prompt_runner/test_parser.py -v
```

Expected: all tests PASS.

- [ ] **Step 2c.4: Commit**

```bash
git add tests/cli/prompt_runner/fixtures/tagged-fences.md tests/cli/prompt_runner/fixtures/no-subsection-headers.md tests/cli/prompt_runner/fixtures/arbitrary-subsections.md tests/cli/prompt_runner/test_parser.py
git commit -m "test(prompt-runner): verify parser accepts fence variants and preserves body verbatim"
```

### Subtask 2d: Error catalogue fixtures and tests

- [ ] **Step 2d.1: Create the five error fixtures**

File: *tests/cli/prompt_runner/fixtures/no-blocks.md*

````markdown
## Prompt 1: Empty Section

Some prose but no code blocks at all.

## Prompt 2: Second

```
gen
```

```
val
```
````

File: *tests/cli/prompt_runner/fixtures/missing-validator.md*

````markdown
## Prompt 1: Incomplete

```
Only a generation prompt, no validation.
```

## Prompt 2: Second

```
gen
```

```
val
```
````

File: *tests/cli/prompt_runner/fixtures/unclosed-generation.md*

````markdown
## Prompt 1: Unclosed Generator

```
Generation prompt that is never closed

## Prompt 2: Second

```
gen
```

```
val
```
````

File: *tests/cli/prompt_runner/fixtures/unclosed-validation.md*

````markdown
## Prompt 1: Unclosed Validator

```
Generator body.
```

```
Validator body that is never closed

## Prompt 2: Second

```
gen
```

```
val
```
````

File: *tests/cli/prompt_runner/fixtures/three-fences.md*

````markdown
## Prompt 1: Too Many Blocks

```
Generator body.
```

```
Validator body.
```

```
Unexpected third block.
```

## Prompt 2: Second

```
gen
```

```
val
```
````

- [ ] **Step 2d.2: Add the error-catalogue tests**

Append to *tests/cli/prompt_runner/test_parser.py*:

```python
def test_error_no_blocks():
    with pytest.raises(ParseError) as exc_info:
        parse_file(FIXTURES / "no-blocks.md")
    err = exc_info.value
    assert err.error_id == "E-NO-BLOCKS"
    assert '"Empty Section"' in err.message
    assert "line 1" in err.message  # heading line
    assert "Add" in err.message  # repair verb


def test_error_missing_validation():
    with pytest.raises(ParseError) as exc_info:
        parse_file(FIXTURES / "missing-validator.md")
    err = exc_info.value
    assert err.error_id == "E-MISSING-VALIDATION"
    assert '"Incomplete"' in err.message
    assert "generation prompt" in err.message
    assert "validation prompt" in err.message
    assert "Add" in err.message


def test_error_unclosed_generation():
    with pytest.raises(ParseError) as exc_info:
        parse_file(FIXTURES / "unclosed-generation.md")
    err = exc_info.value
    assert err.error_id == "E-UNCLOSED-GENERATION"
    assert '"Unclosed Generator"' in err.message
    assert "generation prompt" in err.message
    assert "Add" in err.message


def test_error_unclosed_validation():
    with pytest.raises(ParseError) as exc_info:
        parse_file(FIXTURES / "unclosed-validation.md")
    err = exc_info.value
    assert err.error_id == "E-UNCLOSED-VALIDATION"
    assert '"Unclosed Validator"' in err.message
    assert "validation prompt" in err.message


def test_error_extra_block():
    with pytest.raises(ParseError) as exc_info:
        parse_file(FIXTURES / "three-fences.md")
    err = exc_info.value
    assert err.error_id == "E-EXTRA-BLOCK"
    assert '"Too Many Blocks"' in err.message
    assert "third code block" in err.message


def test_no_bare_fence_jargon_in_error_messages():
    """Every ParseError message must avoid the bare word 'fence'."""
    fixtures_and_ids = [
        ("no-blocks.md", "E-NO-BLOCKS"),
        ("missing-validator.md", "E-MISSING-VALIDATION"),
        ("unclosed-generation.md", "E-UNCLOSED-GENERATION"),
        ("unclosed-validation.md", "E-UNCLOSED-VALIDATION"),
        ("three-fences.md", "E-EXTRA-BLOCK"),
    ]
    bare_fence = re.compile(r"\bfence\b", re.IGNORECASE)
    for filename, _ in fixtures_and_ids:
        with pytest.raises(ParseError) as exc_info:
            parse_file(FIXTURES / filename)
        assert bare_fence.search(exc_info.value.message) is None, (
            f"{filename}: error message uses bare word 'fence': "
            f"{exc_info.value.message}"
        )


def test_error_ids_are_stable():
    from prompt_runner.parser import ERROR_IDS
    assert ERROR_IDS == (
        "E-NO-BLOCKS",
        "E-MISSING-VALIDATION",
        "E-UNCLOSED-GENERATION",
        "E-UNCLOSED-VALIDATION",
        "E-EXTRA-BLOCK",
    )
```

Also add *import re* at the top of *test_parser.py* if it is not already there.

- [ ] **Step 2d.3: Run and verify all error tests pass**

Shell:
```bash
pytest tests/cli/prompt_runner/test_parser.py -v
```

Expected: all tests PASS.

- [ ] **Step 2d.4: Commit**

```bash
git add tests/cli/prompt_runner/fixtures/no-blocks.md tests/cli/prompt_runner/fixtures/missing-validator.md tests/cli/prompt_runner/fixtures/unclosed-generation.md tests/cli/prompt_runner/fixtures/unclosed-validation.md tests/cli/prompt_runner/fixtures/three-fences.md tests/cli/prompt_runner/test_parser.py
git commit -m "test(prompt-runner): verify parser error catalogue"
```

---

## Task 3: parse subcommand — step-1 deliverable

**Files:**
- Create: *src/cli/prompt_runner/__main__.py*

Design reference: §5 (CLI shape) and §12 step 3 in *CD-001-prompt-runner.md*.

- [ ] **Step 3.1: Write the __main__ module with the parse subcommand**

File: *src/cli/prompt_runner/__main__.py*

```python
"""prompt-runner CLI entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from prompt_runner.parser import ParseError, PromptPair, parse_file


def _format_pair_summary(pair: PromptPair, full: bool) -> str:
    gen_lines = pair.generation_prompt.splitlines()
    val_lines = pair.validation_prompt.splitlines()
    header = (
        f"═══ Prompt {pair.index}: {pair.title} ═══\n"
        f"  heading line: {pair.heading_line}\n"
        f"  generation prompt: {len(gen_lines)} lines, "
        f"{len(pair.generation_prompt)} chars\n"
        f"  validation prompt: {len(val_lines)} lines, "
        f"{len(pair.validation_prompt)} chars"
    )
    if full:
        return (
            f"{header}\n"
            f"  ─── generation ───\n"
            f"{_indent(pair.generation_prompt)}\n"
            f"  ─── validation ───\n"
            f"{_indent(pair.validation_prompt)}"
        )
    preview_gen = "\n".join(gen_lines[:3])
    preview_val = "\n".join(val_lines[:3])
    return (
        f"{header}\n"
        f"  ─── generation (first 3 lines) ───\n"
        f"{_indent(preview_gen)}\n"
        f"  ─── validation (first 3 lines) ───\n"
        f"{_indent(preview_val)}"
    )


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _cmd_parse(args: argparse.Namespace) -> int:
    try:
        pairs = parse_file(Path(args.file))
    except ParseError as err:
        sys.stderr.write(f"{err.error_id}\n\n{err.message}\n")
        return 2
    for pair in pairs:
        sys.stdout.write(_format_pair_summary(pair, full=args.full) + "\n\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="prompt-runner",
        description="Run prompt/validator pairs from a markdown file through the Claude CLI.",
    )
    sub = root.add_subparsers(dest="command", required=True)

    parse_cmd = sub.add_parser("parse", help="Parse the file and print prompt pairs.")
    parse_cmd.add_argument("file", help="Path to the input markdown file.")
    parse_cmd.add_argument(
        "--full",
        action="store_true",
        help="Dump complete generator and validator bodies verbatim.",
    )
    parse_cmd.set_defaults(func=_cmd_parse)

    return root


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3.2: Verify the parse subcommand runs against the happy-path fixture**

Shell:
```bash
prompt-runner parse tests/cli/prompt_runner/fixtures/sample-prompts.md
```

Expected: stdout shows two "═══ Prompt N: ..." blocks with heading line, body line/char counts, and the first 3 lines of each body. Exit code 0.

- [ ] **Step 3.3: Verify the parse subcommand runs against the motivating file**

Shell:
```bash
prompt-runner parse /Users/martinbechard/Downloads/ai-development-methodology-prompts_1.md
```

Expected: stdout shows six "═══ Prompt N: ..." blocks with indices 1 through 6, titles matching the motivating file's prompts. Exit code 0.

- [ ] **Step 3.4: Verify a parse error is reported on a broken file**

Shell:
```bash
prompt-runner parse tests/cli/prompt_runner/fixtures/missing-validator.md
echo "Exit: $?"
```

Expected: stderr shows *E-MISSING-VALIDATION* followed by the friendly message with prompt title, line numbers, and repair instruction. Exit code 2.

- [ ] **Step 3.5: Commit**

```bash
git add src/cli/prompt_runner/__main__.py
git commit -m "feat(prompt-runner): add parse subcommand (step-1 deliverable)"
```

---

## Task 4: Companion README for input-file authors

**Files:**
- Create: *src/cli/prompt_runner/README.md*
- Create: *tests/cli/prompt_runner/fixtures/readme-example.md*
- Create: *tests/cli/prompt_runner/test_readme.py*

Design reference: §13 in *CD-001-prompt-runner.md*.

- [ ] **Step 4.1: Create the worked-example fixture**

File: *tests/cli/prompt_runner/fixtures/readme-example.md*

````markdown
## Prompt 1: Greeting

### Generation Prompt

```
Write a short friendly greeting for a new user.
Keep it under 20 words.
```

### Validation Prompt

```
Evaluate the greeting:
- Is it friendly?
- Is it under 20 words?

End with: VERDICT: pass, VERDICT: revise, or VERDICT: escalate.
```

## Prompt 2: Sign-off

### Generation Prompt

```
Write a short friendly sign-off for an email.
```

### Validation Prompt

```
Evaluate the sign-off:
- Is it friendly?
- Is it one line?
```
````

- [ ] **Step 4.2: Write the companion README**

File: *src/cli/prompt_runner/README.md*

````markdown
# prompt-runner — input file format

*How to write a markdown file that the prompt-runner tool will accept. This guide is for people (and AIs) producing input files, not for people running the CLI.*

## What this tool does

prompt-runner is a small Python CLI that takes a markdown file of prompt/validator pairs, runs each prompt through Claude, runs the matching validator in a separate session, and iterates on revision feedback. It runs any markdown file that matches the format described below — it has no knowledge of any specific prompt content.

## Required file structure

Your file must contain one or more prompt sections of this shape:

```markdown
## Prompt 1: Your Title Here

Whatever prose or sub-headings you like (or none at all).

   (code block 1: the generation prompt)

More optional prose.

   (code block 2: the validation prompt)
```

(In the real file the two code blocks would each be wrapped in triple-backtick lines, not the parenthetical placeholders shown above.)

See *tests/cli/prompt_runner/fixtures/readme-example.md* for a minimal, parseable example.

## The heading rule

Every prompt section starts with a level-2 heading whose first word is *Prompt*. All of the following are accepted:

- *## Prompt 1: First Thing*
- *## Prompt: First Thing*
- *## Prompt First Thing*
- *## Prompt 3 — Agent Roles*
- *## Prompt* (the prompt will be listed as "(untitled)")

Any number in the heading is ignored — the runner assigns each prompt a 1-based index based on its position in the file. If you want prompts to run in a specific order, put them in the file in that order.

## The two code blocks

Between a prompt heading and the next prompt heading (or end of file), the parser expects **exactly two fenced code blocks**, in this order:

1. The **generation prompt** — the body of the first code block.
2. The **validation prompt** — the body of the second code block.

The order determines the role. The parser does not look at sub-headings like *### 1.1 Generation Prompt* — you can use those for readability, or not use them at all. You can put any prose, sub-headings, or notes between the two code blocks; only the code blocks are extracted.

Each code block is delimited by a line of exactly three backticks. You may add a language tag to the opening line (for example, *text* or *markdown*) — it is ignored.

## What NOT to do

- **Do not** include a third code block inside a prompt section. If your prompt body needs a code example, indent the example four spaces instead of wrapping it in triple backticks.
- **Do not** nest triple-backtick blocks inside a prompt body. v1 does not support this — the parser would see the inner backticks as the end of the outer block. Workaround: indent the inner example four spaces.
- **Do not** put your own VERDICT-format instruction in the validation prompt. The runner automatically appends an instruction telling the judge to end its response with *VERDICT: pass*, *VERDICT: revise*, or *VERDICT: escalate*. If your validation prompt prescribes a different verdict format, the two instructions will conflict.
- **Do not** rely on the number you write in the heading being preserved. The runner uses the prompt's position in the file.

## What the runner does with your prompts

- The first prompt's generator is invoked with the generation prompt body as-is.
- Each subsequent prompt's generator is invoked with every prior approved artifact prepended as context, followed by the generation prompt body.
- Each prompt's judge is invoked in a **separate Claude session** with the validation prompt body, followed by the artifact the generator just produced, followed by the VERDICT instruction.
- If the judge returns *VERDICT: revise*, the generator is resumed with the judge's feedback and produces a revised artifact. The judge is then resumed to re-evaluate. Up to *--max-iterations* (default 3).
- If the judge returns *VERDICT: escalate* or the iteration cap is reached, the pipeline halts and the remaining prompts are skipped.

Generator and judge **never** share a Claude session — they are always separate processes with separate session IDs.

## Writing good validation prompts

Your validation prompt is what the judge sees on every iteration. When the generator needs to revise, the only feedback it gets is whatever the judge wrote. Good validation prompts:

- List specific, checkable criteria (not "be thorough" or "use good judgement").
- Ask the judge to point at specific parts of the artifact that fail (line numbers, section names).
- Explain what a "revise" feedback should contain — the generator will act on it verbatim.

## Parser error IDs

If the parser rejects your file, it prints one of these error IDs and a friendly repair instruction:

- **E-NO-BLOCKS** — a prompt heading was found but no code blocks followed before the next heading or end of file.
- **E-MISSING-VALIDATION** — the generation prompt was found but no validation prompt followed.
- **E-UNCLOSED-GENERATION** — the generation prompt's code block was opened but never closed.
- **E-UNCLOSED-VALIDATION** — the validation prompt's code block was opened but never closed.
- **E-EXTRA-BLOCK** — more than two code blocks were found inside a single prompt section.

## Running the tool

Once your file is ready:

```bash
prompt-runner parse your-file.md
```

verifies that the parser accepts it. Then:

```bash
prompt-runner run your-file.md
```

executes the full pipeline. See *prompt-runner run --help* for options.

## Known limitations (v1)

- Code blocks inside prompt bodies must not use triple backticks — indent them instead.
- All prompts run sequentially; no parallelism.
- On failure, the only escalation policy is *halt* — the runner does not automatically re-route to a prior phase.
- Interrupted runs cannot be resumed; re-run the tool from the beginning.
````

- [ ] **Step 4.3: Write the README meta-tests**

File: *tests/cli/prompt_runner/test_readme.py*

```python
"""Meta-tests that keep the README in sync with the code."""
from __future__ import annotations

from pathlib import Path

from prompt_runner.parser import ERROR_IDS, parse_file

README_PATH = Path(__file__).parent.parent.parent / "src" / "cli" / "prompt_runner" / "README.md"
FIXTURES = Path(__file__).parent / "fixtures"


def test_readme_exists():
    assert README_PATH.exists(), f"README not found at {README_PATH}"


def test_readme_example_parses():
    pairs = parse_file(FIXTURES / "readme-example.md")
    assert len(pairs) == 2
    assert pairs[0].title == "Greeting"
    assert pairs[1].title == "Sign-off"


def test_error_ids_match_readme():
    text = README_PATH.read_text(encoding="utf-8")
    for error_id in ERROR_IDS:
        assert error_id in text, f"README is missing error ID {error_id}"


def test_readme_is_short_enough():
    text = README_PATH.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    assert line_count <= 400, f"README has {line_count} lines, cap is 400"
```

- [ ] **Step 4.4: Run the README tests and verify they pass**

Shell:
```bash
pytest tests/cli/prompt_runner/test_readme.py -v
```

Expected: four tests PASS.

- [ ] **Step 4.5: Commit**

```bash
git add src/cli/prompt_runner/README.md tests/cli/prompt_runner/fixtures/readme-example.md tests/cli/prompt_runner/test_readme.py
git commit -m "docs(prompt-runner): add input-format README and meta-tests"
```

---

## Task 5: ClaudeClient protocol and test doubles

**Files:**
- Create: *src/cli/prompt_runner/claude_client.py*
- Create: *tests/cli/prompt_runner/test_claude_client.py*

Design reference: §7 (Claude client) in *CD-001-prompt-runner.md*. The real streaming implementation is deferred to Task 7; this task builds only the protocol, dataclasses, and fake/dry-run doubles that the runner tests in Task 6 will depend on.

- [ ] **Step 5.1: Write the claude_client module (doubles only, no real implementation yet)**

File: *src/cli/prompt_runner/claude_client.py*

```python
"""Claude CLI subprocess wrapper with streaming output and per-invocation logs.

This module defines the ClaudeClient protocol plus three implementations:
- FakeClaudeClient: scripted responses for unit tests.
- DryRunClaudeClient: records calls and returns a placeholder response.
- RealClaudeClient: Popen-backed streaming client (added in Task 7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ClaudeCall:
    prompt: str
    session_id: str
    new_session: bool
    model: str | None
    stdout_log_path: Path
    stderr_log_path: Path
    stream_header: str


@dataclass(frozen=True)
class ClaudeResponse:
    stdout: str
    stderr: str
    returncode: int


class ClaudeBinaryNotFound(Exception):
    """Raised by the real client at startup when `claude` is not on PATH."""


class ClaudeInvocationError(Exception):
    """Raised when a claude invocation exits non-zero.

    Carries a partial ClaudeResponse so the runner can persist whatever output
    was captured before the failure.
    """

    def __init__(self, call: ClaudeCall, response: ClaudeResponse) -> None:
        super().__init__(
            f"claude -p exited with status {response.returncode} "
            f"for {call.stream_header}"
        )
        self.call = call
        self.response = response


class ClaudeClient(Protocol):
    def call(self, call: ClaudeCall) -> ClaudeResponse: ...


@dataclass
class FakeClaudeClient:
    """Scripted test double.

    Pass a list of ClaudeResponse (or ClaudeInvocationError) in the order they
    should be returned. The client records every ClaudeCall it receives.
    """

    scripted: list[ClaudeResponse | ClaudeInvocationError]
    received: list[ClaudeCall] = field(default_factory=list)
    _index: int = 0

    def call(self, call: ClaudeCall) -> ClaudeResponse:
        self.received.append(call)
        if self._index >= len(self.scripted):
            raise AssertionError(
                f"FakeClaudeClient ran out of scripted responses "
                f"(received {len(self.received)}, scripted {len(self.scripted)})"
            )
        item = self.scripted[self._index]
        self._index += 1
        if isinstance(item, ClaudeInvocationError):
            raise item
        return item


@dataclass
class DryRunClaudeClient:
    """Returns a placeholder response without invoking claude.

    Used when --dry-run is passed on the CLI. Writes no log files.
    """

    received: list[ClaudeCall] = field(default_factory=list)

    def call(self, call: ClaudeCall) -> ClaudeResponse:
        self.received.append(call)
        placeholder = (
            f"[dry-run] would have called claude with "
            f"session={call.session_id}, resume={not call.new_session}, "
            f"model={call.model}, prompt_len={len(call.prompt)}"
        )
        return ClaudeResponse(stdout=placeholder, stderr="", returncode=0)
```

- [ ] **Step 5.2: Write tests for the doubles**

File: *tests/cli/prompt_runner/test_claude_client.py*

```python
from pathlib import Path

import pytest

from prompt_runner.claude_client import (
    ClaudeCall,
    ClaudeInvocationError,
    ClaudeResponse,
    DryRunClaudeClient,
    FakeClaudeClient,
)


def _make_call(prefix: str = "test") -> ClaudeCall:
    return ClaudeCall(
        prompt="a prompt body",
        session_id=f"{prefix}-session",
        new_session=True,
        model=None,
        stdout_log_path=Path(f"/tmp/{prefix}.stdout.log"),
        stderr_log_path=Path(f"/tmp/{prefix}.stderr.log"),
        stream_header=f"── {prefix} ──",
    )


def test_fake_client_returns_scripted_responses_in_order():
    client = FakeClaudeClient(
        scripted=[
            ClaudeResponse(stdout="first", stderr="", returncode=0),
            ClaudeResponse(stdout="second", stderr="", returncode=0),
        ]
    )
    call_a = _make_call("a")
    call_b = _make_call("b")
    assert client.call(call_a).stdout == "first"
    assert client.call(call_b).stdout == "second"
    assert client.received == [call_a, call_b]


def test_fake_client_raises_when_scripted_list_exhausted():
    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="only", stderr="", returncode=0)
    ])
    client.call(_make_call())
    with pytest.raises(AssertionError, match="ran out of scripted responses"):
        client.call(_make_call())


def test_fake_client_raises_scripted_invocation_error():
    partial = ClaudeResponse(stdout="partial", stderr="boom", returncode=1)
    err = ClaudeInvocationError(_make_call("err"), partial)
    client = FakeClaudeClient(scripted=[err])
    with pytest.raises(ClaudeInvocationError) as exc_info:
        client.call(_make_call("err"))
    assert exc_info.value.response.stdout == "partial"


def test_dry_run_client_returns_placeholder_and_records_call():
    client = DryRunClaudeClient()
    call = _make_call("dry")
    response = client.call(call)
    assert response.returncode == 0
    assert "dry-run" in response.stdout
    assert "dry-session" in response.stdout
    assert client.received == [call]
```

- [ ] **Step 5.3: Run the claude_client tests and verify they pass**

Shell:
```bash
pytest tests/cli/prompt_runner/test_claude_client.py -v
```

Expected: four tests PASS.

- [ ] **Step 5.4: Commit**

```bash
git add src/cli/prompt_runner/claude_client.py tests/cli/prompt_runner/test_claude_client.py
git commit -m "feat(prompt-runner): add ClaudeClient protocol with fake and dry-run doubles"
```

---

## Task 6: runner.py — pipeline orchestration

**Files:**
- Create: *src/cli/prompt_runner/runner.py*
- Create: *tests/cli/prompt_runner/test_runner.py*

Design reference: §9 (runner engine) and §9.4 (prompt builders), §9.5 (test list) in *CD-001-prompt-runner.md*.

### Subtask 6a: Data model and prompt builders

- [ ] **Step 6a.1: Write the runner module skeleton with data model and prompt builders**

File: *src/cli/prompt_runner/runner.py*

```python
"""Pipeline orchestration for prompt-runner.

See docs/design/components/CD-001-prompt-runner.md sections 9 and 11.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from prompt_runner.claude_client import (
    ClaudeCall,
    ClaudeClient,
    ClaudeInvocationError,
    ClaudeResponse,
)
from prompt_runner.parser import PromptPair
from prompt_runner.verdict import Verdict, VerdictParseError, parse_verdict


MAX_ITERATIONS_DEFAULT = 3
VERDICT_INSTRUCTION = (
    "End your response with a single line of the exact form: "
    "VERDICT: pass, VERDICT: revise, or VERDICT: escalate. "
    "Do not write anything after that line."
)
ANTI_ANCHORING_CLAUSE = (
    "Below is the revised artifact. Re-evaluate every checklist item against "
    "this current version. Items you previously failed may now pass, and items "
    "you previously passed may now fail if the revision broke them. Do not "
    "defer to your prior verdict."
)
REVISION_GENERATOR_PREAMBLE = (
    "The judge evaluated your previous artifact and returned the feedback "
    "below. Produce a revised artifact that addresses every fail or partial "
    "item. Do not drop content that already passed. Your response must be the "
    "complete revised artifact, with no commentary before or after it."
)
_HORIZONTAL_RULE = "\n\n---\n\n"


@dataclass(frozen=True)
class RunConfig:
    max_iterations: int = MAX_ITERATIONS_DEFAULT
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
    final_verdict: Verdict
    final_artifact: str


@dataclass(frozen=True)
class PipelineResult:
    prompt_results: list[PromptResult]
    halted_early: bool
    halt_reason: str | None


def build_initial_generator_message(
    pair: PromptPair, prior_artifacts: list[tuple[str, str]]
) -> str:
    if not prior_artifacts:
        return pair.generation_prompt
    prior_blocks = "\n\n".join(
        f"## {title}\n\n{body}" for title, body in prior_artifacts
    )
    return (
        f"# Prior approved artifacts\n\n{prior_blocks}"
        f"{_HORIZONTAL_RULE}"
        f"# Your task\n\n{pair.generation_prompt}"
    )


def build_initial_judge_message(pair: PromptPair, artifact: str) -> str:
    return (
        f"{pair.validation_prompt}"
        f"{_HORIZONTAL_RULE}"
        f"# Artifact to evaluate\n\n{artifact}"
        f"{_HORIZONTAL_RULE}"
        f"{VERDICT_INSTRUCTION}"
    )


def build_revision_generator_message(judge_output: str) -> str:
    return f"{REVISION_GENERATOR_PREAMBLE}\n\n# Judge feedback\n\n{judge_output}"


def build_revision_judge_message(new_artifact: str) -> str:
    return (
        f"{ANTI_ANCHORING_CLAUSE}\n\n"
        f"# Revised artifact\n\n{new_artifact}"
        f"{_HORIZONTAL_RULE}"
        f"{VERDICT_INSTRUCTION}"
    )


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    lowered = title.lower()
    slug = _SLUG_STRIP.sub("-", lowered).strip("-")
    return slug or "untitled"


def _prompt_dir_name(pair: PromptPair) -> str:
    return f"prompt-{pair.index:02d}-{_slugify(pair.title)}"
```

- [ ] **Step 6a.2: Write tests for the prompt builders**

File: *tests/cli/prompt_runner/test_runner.py*

```python
from pathlib import Path

import pytest

from prompt_runner.parser import PromptPair
from prompt_runner.runner import (
    VERDICT_INSTRUCTION,
    ANTI_ANCHORING_CLAUSE,
    REVISION_GENERATOR_PREAMBLE,
    build_initial_generator_message,
    build_initial_judge_message,
    build_revision_generator_message,
    build_revision_judge_message,
)


def _pair(index: int, title: str, gen: str = "GEN", val: str = "VAL") -> PromptPair:
    return PromptPair(
        index=index,
        title=title,
        generation_prompt=gen,
        validation_prompt=val,
        heading_line=1,
        generation_line=2,
        validation_line=5,
    )


def test_initial_generator_message_with_no_priors_is_verbatim():
    p = _pair(1, "First", gen="the body")
    assert build_initial_generator_message(p, []) == "the body"


def test_initial_generator_message_injects_priors():
    p = _pair(2, "Second", gen="the task body")
    msg = build_initial_generator_message(
        p,
        [("First", "ARTIFACT-ONE"), ("A", "ARTIFACT-A")],
    )
    assert "ARTIFACT-ONE" in msg
    assert "ARTIFACT-A" in msg
    assert "# Prior approved artifacts" in msg
    assert "# Your task" in msg
    assert "the task body" in msg


def test_initial_judge_message_includes_verdict_instruction():
    p = _pair(1, "First", val="please evaluate")
    msg = build_initial_judge_message(p, "ARTIFACT")
    assert "please evaluate" in msg
    assert "ARTIFACT" in msg
    assert VERDICT_INSTRUCTION in msg


def test_revision_generator_message_contains_preamble_and_feedback():
    msg = build_revision_generator_message("some feedback")
    assert REVISION_GENERATOR_PREAMBLE in msg
    assert "some feedback" in msg


def test_revision_judge_message_contains_anti_anchoring_and_artifact():
    msg = build_revision_judge_message("NEW-ARTIFACT")
    assert ANTI_ANCHORING_CLAUSE in msg
    assert "NEW-ARTIFACT" in msg
    assert VERDICT_INSTRUCTION in msg
```

- [ ] **Step 6a.3: Run the builder tests and verify they pass**

Shell:
```bash
pytest tests/cli/prompt_runner/test_runner.py -v
```

Expected: five tests PASS.

- [ ] **Step 6a.4: Commit**

```bash
git add src/cli/prompt_runner/runner.py tests/cli/prompt_runner/test_runner.py
git commit -m "feat(prompt-runner): add runner data model and prompt builders"
```

### Subtask 6b: run_prompt and run_pipeline

- [ ] **Step 6b.1: Append the run_prompt and run_pipeline functions to runner.py**

Append to *src/cli/prompt_runner/runner.py*:

```python
def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_call(
    *,
    prompt: str,
    session_id: str,
    new_session: bool,
    model: str | None,
    logs_dir: Path,
    iteration: int,
    role: str,
    pair: PromptPair,
) -> ClaudeCall:
    return ClaudeCall(
        prompt=prompt,
        session_id=session_id,
        new_session=new_session,
        model=model,
        stdout_log_path=logs_dir / f"iter-{iteration:02d}-{role}.stdout.log",
        stderr_log_path=logs_dir / f"iter-{iteration:02d}-{role}.stderr.log",
        stream_header=(
            f"── prompt {pair.index} '{pair.title}' / iter {iteration} / {role} ──"
        ),
    )


def run_prompt(
    pair: PromptPair,
    prior_artifacts: list[tuple[str, str]],
    run_dir: Path,
    config: RunConfig,
    claude_client: ClaudeClient,
    run_id: str,
) -> PromptResult:
    gen_session = f"gen-prompt-{pair.index}-{run_id}"
    jud_session = f"jud-prompt-{pair.index}-{run_id}"
    prompt_slug = _prompt_dir_name(pair)
    prompt_dir = run_dir / prompt_slug
    logs_dir = run_dir / "logs" / prompt_slug
    prompt_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    iterations: list[IterationResult] = []

    for iteration_number in range(1, config.max_iterations + 1):
        is_first = iteration_number == 1

        gen_msg = (
            build_initial_generator_message(pair, prior_artifacts)
            if is_first
            else build_revision_generator_message(iterations[-1].judge_output)
        )
        gen_call = _make_call(
            prompt=gen_msg,
            session_id=gen_session,
            new_session=is_first,
            model=config.model,
            logs_dir=logs_dir,
            iteration=iteration_number,
            role="generator",
            pair=pair,
        )
        gen_response = _call_or_persist_partial(
            claude_client, gen_call, prompt_dir / f"iter-{iteration_number:02d}-generator.md"
        )

        jud_msg = (
            build_initial_judge_message(pair, gen_response.stdout)
            if is_first
            else build_revision_judge_message(gen_response.stdout)
        )
        jud_call = _make_call(
            prompt=jud_msg,
            session_id=jud_session,
            new_session=is_first,
            model=config.model,
            logs_dir=logs_dir,
            iteration=iteration_number,
            role="judge",
            pair=pair,
        )
        jud_response = _call_or_persist_partial(
            claude_client, jud_call, prompt_dir / f"iter-{iteration_number:02d}-judge.md"
        )

        verdict = parse_verdict(jud_response.stdout)
        iterations.append(
            IterationResult(
                iteration=iteration_number,
                generator_output=gen_response.stdout,
                judge_output=jud_response.stdout,
                verdict=verdict,
            )
        )
        if verdict != Verdict.REVISE:
            break

    final = iterations[-1]
    final_verdict = final.verdict
    if final_verdict == Verdict.REVISE:
        final_verdict = Verdict.ESCALATE

    _write(prompt_dir / "final-artifact.md", final.generator_output)
    _write(prompt_dir / "final-verdict.txt", final_verdict.value + "\n")

    return PromptResult(
        pair=pair,
        iterations=iterations,
        final_verdict=final_verdict,
        final_artifact=final.generator_output,
    )


def _call_or_persist_partial(
    client: ClaudeClient, call: ClaudeCall, md_path: Path
) -> ClaudeResponse:
    """Invoke the client. On ClaudeInvocationError, write any partial stdout to
    md_path before re-raising so the runner's halt semantics are preserved."""
    try:
        response = client.call(call)
    except ClaudeInvocationError as err:
        _write(md_path, err.response.stdout)
        raise
    _write(md_path, response.stdout)
    return response


def run_pipeline(
    pairs: list[PromptPair],
    run_dir: Path,
    config: RunConfig,
    claude_client: ClaudeClient,
    source_file: Path,
) -> PipelineResult:
    run_id = run_dir.name
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(run_dir, source_file, config, run_id, started_at=_now_iso())

    prior_artifacts: list[tuple[str, str]] = []
    prompt_results: list[PromptResult] = []

    for pair in pairs:
        if config.only is not None and pair.index != config.only:
            continue
        try:
            result = run_prompt(
                pair, prior_artifacts, run_dir, config, claude_client, run_id
            )
        except VerdictParseError as err:
            halt_reason = (
                f"R-NO-VERDICT: prompt {pair.index} \"{pair.title}\" "
                f"returned a judge response with no VERDICT line. {err}"
            )
            _finalise(run_dir, source_file, config, run_id, prompt_results,
                      halted_early=True, halt_reason=halt_reason)
            return PipelineResult(prompt_results, halted_early=True, halt_reason=halt_reason)
        except ClaudeInvocationError as err:
            halt_reason = (
                f"R-CLAUDE-FAILED: prompt {pair.index} \"{pair.title}\" "
                f"{err.call.stream_header} exited with status "
                f"{err.response.returncode}."
            )
            _finalise(run_dir, source_file, config, run_id, prompt_results,
                      halted_early=True, halt_reason=halt_reason)
            return PipelineResult(prompt_results, halted_early=True, halt_reason=halt_reason)

        prompt_results.append(result)
        if result.final_verdict == Verdict.PASS:
            prior_artifacts.append((pair.title, result.final_artifact))
        else:
            halt_reason = f"prompt {pair.index} escalated"
            _finalise(run_dir, source_file, config, run_id, prompt_results,
                      halted_early=True, halt_reason=halt_reason)
            return PipelineResult(prompt_results, halted_early=True, halt_reason=halt_reason)

    _finalise(run_dir, source_file, config, run_id, prompt_results,
              halted_early=False, halt_reason=None)
    return PipelineResult(prompt_results, halted_early=False, halt_reason=None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_manifest(
    run_dir: Path, source_file: Path, config: RunConfig, run_id: str, started_at: str
) -> None:
    manifest = {
        "source_file": str(source_file.resolve()),
        "run_id": run_id,
        "config": {
            "max_iterations": config.max_iterations,
            "model": config.model,
            "only": config.only,
            "dry_run": config.dry_run,
        },
        "started_at": started_at,
        "finished_at": None,
    }
    _write(run_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n")


def _finalise(
    run_dir: Path,
    source_file: Path,
    config: RunConfig,
    run_id: str,
    prompt_results: list[PromptResult],
    halted_early: bool,
    halt_reason: str | None,
) -> None:
    # Rewrite manifest.json with finished_at and halt_reason.
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["finished_at"] = _now_iso()
    manifest["halt_reason"] = halt_reason
    _write(manifest_path, json.dumps(manifest, indent=2) + "\n")

    _write(run_dir / "summary.txt", _format_summary(
        source_file, run_dir, prompt_results, halted_early, halt_reason
    ))


def _format_summary(
    source_file: Path,
    run_dir: Path,
    prompt_results: list[PromptResult],
    halted_early: bool,
    halt_reason: str | None,
) -> str:
    status = "halted" if halted_early else "completed"
    lines = [
        "Prompt Runner — Run Summary",
        f"Source: {source_file}",
        f"Run:    {run_dir}",
        f"Status: {status}",
        "",
        "Prompts:",
    ]
    for result in prompt_results:
        slug = _prompt_dir_name(result.pair)
        iter_count = len(result.iterations)
        lines.append(
            f"  {result.pair.index:02d}  {slug:<40s}  {result.final_verdict.value:<9s}  {iter_count} iter"
        )
    total_calls = sum(len(r.iterations) * 2 for r in prompt_results)
    lines.append("")
    lines.append(f"Total claude calls: {total_calls}")
    if halt_reason:
        lines.append(f"Halt reason: {halt_reason}")
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 6b.2: Write runner integration tests**

Append to *tests/cli/prompt_runner/test_runner.py*:

```python
from prompt_runner.claude_client import (
    ClaudeInvocationError,
    ClaudeResponse,
    FakeClaudeClient,
)
from prompt_runner.runner import (
    PipelineResult,
    PromptResult,
    RunConfig,
    run_pipeline,
    run_prompt,
)
from prompt_runner.verdict import Verdict


def _pass_response(text: str = "ARTIFACT") -> ClaudeResponse:
    return ClaudeResponse(stdout=text, stderr="", returncode=0)


def _judge_pass() -> ClaudeResponse:
    return ClaudeResponse(stdout="All good.\n\nVERDICT: pass", stderr="", returncode=0)


def _judge_revise(note: str = "Fix this.") -> ClaudeResponse:
    return ClaudeResponse(
        stdout=f"{note}\n\nVERDICT: revise", stderr="", returncode=0
    )


def _judge_escalate() -> ClaudeResponse:
    return ClaudeResponse(
        stdout="Cannot continue.\n\nVERDICT: escalate", stderr="", returncode=0
    )


def test_single_prompt_passes_first_try(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response("gen-output"), _judge_pass()])
    result = run_prompt(
        pair=pair,
        prior_artifacts=[],
        run_dir=tmp_path / "run",
        config=RunConfig(),
        claude_client=client,
        run_id="testrun",
    )
    assert result.final_verdict == Verdict.PASS
    assert len(result.iterations) == 1
    assert len(client.received) == 2  # one generator, one judge
    assert client.received[0].new_session is True
    assert client.received[1].new_session is True
    assert client.received[0].session_id != client.received[1].session_id


def test_single_prompt_passes_on_second_iteration(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[
        _pass_response("gen-1"),
        _judge_revise("needs work"),
        _pass_response("gen-2-revised"),
        _judge_pass(),
    ])
    result = run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=client, run_id="testrun",
    )
    assert result.final_verdict == Verdict.PASS
    assert len(result.iterations) == 2
    assert result.final_artifact == "gen-2-revised"
    assert len(client.received) == 4
    # Iteration 1 uses new sessions; iteration 2 resumes.
    assert client.received[0].new_session is True
    assert client.received[1].new_session is True
    assert client.received[2].new_session is False
    assert client.received[3].new_session is False
    # Generator's revision call contains the judge's feedback.
    assert "needs work" in client.received[2].prompt


def test_escalation_on_max_iterations(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[
        _pass_response("g1"), _judge_revise("r1"),
        _pass_response("g2"), _judge_revise("r2"),
        _pass_response("g3"), _judge_revise("r3"),
    ])
    result = run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(max_iterations=3), claude_client=client,
        run_id="testrun",
    )
    assert result.final_verdict == Verdict.ESCALATE
    assert len(result.iterations) == 3
    assert len(client.received) == 6


def test_direct_escalation(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response("g1"), _judge_escalate()])
    result = run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=client, run_id="testrun",
    )
    assert result.final_verdict == Verdict.ESCALATE
    assert len(result.iterations) == 1
    assert len(client.received) == 2


def test_prior_artifacts_injected_into_next_prompt(tmp_path: Path):
    p1 = _pair(1, "First")
    p2 = _pair(2, "Second")
    client = FakeClaudeClient(scripted=[
        _pass_response("ARTIFACT-ONE"), _judge_pass(),
        _pass_response("ARTIFACT-TWO"), _judge_pass(),
    ])
    result = run_pipeline(
        pairs=[p1, p2],
        run_dir=tmp_path / "run",
        config=RunConfig(),
        claude_client=client,
        source_file=tmp_path / "source.md",
    )
    assert not result.halted_early
    # prompt 2's generator call (index 2 in received) should contain ARTIFACT-ONE.
    assert "ARTIFACT-ONE" in client.received[2].prompt
    # prompt 1's generator call should not mention "Prior approved artifacts".
    assert "Prior approved artifacts" not in client.received[0].prompt


def test_escalation_halts_pipeline(tmp_path: Path):
    p1 = _pair(1, "First")
    p2 = _pair(2, "Second")
    p3 = _pair(3, "Third")
    client = FakeClaudeClient(scripted=[
        _pass_response("a1"), _judge_pass(),    # p1 passes
        _pass_response("a2"), _judge_escalate(),  # p2 escalates
        # p3 must not run
    ])
    result = run_pipeline(
        pairs=[p1, p2, p3], run_dir=tmp_path / "run", config=RunConfig(),
        claude_client=client, source_file=tmp_path / "source.md",
    )
    assert result.halted_early
    assert len(result.prompt_results) == 2
    assert len(client.received) == 4


def test_only_flag_runs_single_prompt(tmp_path: Path):
    p1 = _pair(1, "First")
    p2 = _pair(2, "Second")
    p3 = _pair(3, "Third")
    client = FakeClaudeClient(scripted=[_pass_response("a2"), _judge_pass()])
    result = run_pipeline(
        pairs=[p1, p2, p3], run_dir=tmp_path / "run",
        config=RunConfig(only=2), claude_client=client,
        source_file=tmp_path / "source.md",
    )
    assert not result.halted_early
    assert len(client.received) == 2
    # Prompt 2's generator call should NOT contain any prior-artifact injection.
    assert "Prior approved artifacts" not in client.received[0].prompt


def test_session_id_naming(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=client, run_id="myrun",
    )
    gen_call, jud_call = client.received
    assert gen_call.session_id.startswith("gen-prompt-1-")
    assert jud_call.session_id.startswith("jud-prompt-1-")
    assert gen_call.session_id != jud_call.session_id


def test_resume_flag_set_on_iterations_after_first(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[
        _pass_response(), _judge_revise(),
        _pass_response(), _judge_pass(),
    ])
    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=client, run_id="myrun",
    )
    # Iter 1: both calls new_session=True. Iter 2: both calls new_session=False.
    assert [c.new_session for c in client.received] == [True, True, False, False]


def test_log_paths_passed_to_every_call(tmp_path: Path):
    pair = _pair(1, "Alpha")
    client = FakeClaudeClient(scripted=[_pass_response(), _judge_pass()])
    run_dir = tmp_path / "run"
    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=run_dir,
        config=RunConfig(), claude_client=client, run_id="myrun",
    )
    for call in client.received:
        assert call.stdout_log_path.parent.parent == run_dir / "logs"
        assert call.stdout_log_path.name.startswith("iter-01-")
        assert call.stdout_log_path.name.endswith(".stdout.log")


def test_logs_dir_created_before_first_call(tmp_path: Path):
    pair = _pair(1, "Alpha")
    captured = []

    class AssertingClient:
        def call(self, call):
            # Capture the existence of the parent dir at the moment of the call.
            captured.append(call.stdout_log_path.parent.exists())
            return _pass_response() if "generator" in call.stream_header else _judge_pass()

    run_prompt(
        pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
        config=RunConfig(), claude_client=AssertingClient(), run_id="myrun",
    )
    assert all(captured), "logs directory was not created before a claude call"


def test_halt_on_claude_failure_writes_partial_md(tmp_path: Path):
    pair = _pair(1, "Alpha")
    gen_ok = _pass_response("g1")
    judge_partial = ClaudeResponse(stdout="PARTIAL-JUDGE-OUTPUT", stderr="oops", returncode=1)
    # Second call (judge) raises.
    err = ClaudeInvocationError(
        ClaudeCall_stub := None,  # placeholder, replaced below
        judge_partial,
    )
    # Need a real ClaudeCall for the error's .call field; use any.
    # The fake client raises this exception on the second call.
    dummy_call = ClaudeCall(
        prompt="", session_id="x", new_session=True, model=None,
        stdout_log_path=Path("/tmp/x"), stderr_log_path=Path("/tmp/x"),
        stream_header="── test ──",
    )
    err = ClaudeInvocationError(dummy_call, judge_partial)
    client = FakeClaudeClient(scripted=[gen_ok, err])
    with pytest.raises(ClaudeInvocationError):
        run_prompt(
            pair=pair, prior_artifacts=[], run_dir=tmp_path / "run",
            config=RunConfig(), claude_client=client, run_id="myrun",
        )
    judge_md = tmp_path / "run" / "prompt-01-alpha" / "iter-01-judge.md"
    assert judge_md.exists()
    assert judge_md.read_text() == "PARTIAL-JUDGE-OUTPUT"


def test_unparseable_verdict_halts_pipeline(tmp_path: Path):
    pair = _pair(1, "Alpha")
    bad_judge = ClaudeResponse(stdout="no verdict here at all", stderr="", returncode=0)
    client = FakeClaudeClient(scripted=[_pass_response(), bad_judge])
    result = run_pipeline(
        pairs=[pair], run_dir=tmp_path / "run", config=RunConfig(),
        claude_client=client, source_file=tmp_path / "source.md",
    )
    assert result.halted_early
    assert result.halt_reason is not None
    assert "R-NO-VERDICT" in result.halt_reason


def test_dry_run_makes_no_real_calls(tmp_path: Path):
    from prompt_runner.claude_client import DryRunClaudeClient
    pair = _pair(1, "Alpha")
    client = DryRunClaudeClient()
    # DryRunClaudeClient returns stdout that has no VERDICT line, so we expect
    # the pipeline to halt at the first judge call with R-NO-VERDICT — that is
    # the correct dry-run behaviour because dry-run is about skipping the
    # subprocess, not about bypassing verdict parsing. The test asserts that no
    # subprocess-style activity happened (the DryRunClient recorded the call
    # but didn't spawn anything).
    result = run_pipeline(
        pairs=[pair], run_dir=tmp_path / "run",
        config=RunConfig(dry_run=True), claude_client=client,
        source_file=tmp_path / "source.md",
    )
    # At least the first generator call was recorded.
    assert len(client.received) >= 1
    assert result.halted_early  # because DryRun responses have no VERDICT line
```

- [ ] **Step 6b.3: Run all runner tests and verify they pass**

Shell:
```bash
pytest tests/cli/prompt_runner/test_runner.py -v
```

Expected: all tests PASS. If any fail, investigate — the most common issues are path separators in session IDs, slug generation edge cases, and partial-write ordering on ClaudeInvocationError.

- [ ] **Step 6b.4: Commit**

```bash
git add src/cli/prompt_runner/runner.py tests/cli/prompt_runner/test_runner.py
git commit -m "feat(prompt-runner): add run_prompt and run_pipeline with revision loop"
```

---

## Task 7: Real streaming Claude client

**Files:**
- Modify: *src/cli/prompt_runner/claude_client.py*
- Modify: *tests/cli/prompt_runner/test_claude_client.py*

Design reference: §7.1 (Real implementation, streaming and log capture), §7.4 in *CD-001-prompt-runner.md*.

- [ ] **Step 7.1: Append the real client implementation to claude_client.py**

Append to *src/cli/prompt_runner/claude_client.py*:

```python
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass as _dataclass


def _ensure_claude_on_path() -> None:
    """Raise ClaudeBinaryNotFound if the claude CLI is not on PATH."""
    if shutil.which("claude") is None:
        raise ClaudeBinaryNotFound(
            "cannot find the 'claude' command on PATH. "
            "Install the Claude CLI and make sure 'claude' is on your PATH."
        )


@_dataclass
class RealClaudeClient:
    """Popen-backed streaming client.

    On each call():
      1. Builds an argv for `claude -p --output-format text ...`.
      2. Spawns the subprocess with pipes for stdin/stdout/stderr.
      3. Writes the prompt to stdin and closes it.
      4. Starts a background thread that reads stderr to an in-memory buffer
         AND the stderr_log_path (prevents pipe-buffer deadlock).
      5. Iterates stdout line-by-line on the main thread, writing each line to
         sys.stdout (indented), to an in-memory buffer, and to stdout_log_path.
      6. Waits for the subprocess, joins the stderr thread, and returns the
         ClaudeResponse.
      7. If returncode != 0, raises ClaudeInvocationError carrying the partial
         response.
    """

    def __post_init__(self) -> None:
        _ensure_claude_on_path()

    def call(self, call: ClaudeCall) -> ClaudeResponse:
        argv = self._build_argv(call)
        sys.stdout.write(call.stream_header + "\n")
        sys.stdout.flush()

        # Truncate log files at the start of the call; we append during streaming.
        call.stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
        call.stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
        call.stdout_log_path.write_text("", encoding="utf-8")
        call.stderr_log_path.write_text("", encoding="utf-8")

        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding="utf-8",
        )
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None

        proc.stdin.write(call.prompt)
        proc.stdin.close()

        stderr_buffer: list[str] = []

        def drain_stderr() -> None:
            assert proc.stderr is not None
            with open(call.stderr_log_path, "a", encoding="utf-8") as log:
                for chunk in proc.stderr:
                    stderr_buffer.append(chunk)
                    log.write(chunk)
                    log.flush()

        stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
        stderr_thread.start()

        stdout_buffer: list[str] = []
        with open(call.stdout_log_path, "a", encoding="utf-8") as log:
            for line in proc.stdout:
                indented = "    " + line if not line.startswith("    ") else line
                sys.stdout.write(indented)
                sys.stdout.flush()
                stdout_buffer.append(line)
                log.write(line)
                log.flush()

        returncode = proc.wait()
        stderr_thread.join()

        response = ClaudeResponse(
            stdout="".join(stdout_buffer),
            stderr="".join(stderr_buffer),
            returncode=returncode,
        )
        if returncode != 0:
            raise ClaudeInvocationError(call, response)
        return response

    @staticmethod
    def _build_argv(call: ClaudeCall) -> list[str]:
        argv = ["claude", "-p", "--output-format", "text"]
        if call.model is not None:
            argv += ["--model", call.model]
        if call.new_session:
            argv += ["--session-id", call.session_id]
        else:
            argv += ["--resume", call.session_id]
        return argv
```

- [ ] **Step 7.2: Write tests for the real client using a monkeypatched Popen**

Append to *tests/cli/prompt_runner/test_claude_client.py*:

```python
from unittest.mock import MagicMock

from prompt_runner.claude_client import (
    ClaudeBinaryNotFound,
    ClaudeInvocationError,
    RealClaudeClient,
)


class _FakeProcess:
    def __init__(self, stdout_lines: list[str], stderr_lines: list[str], returncode: int = 0):
        self._stdout_lines = iter(stdout_lines)
        self._stderr_lines = iter(stderr_lines)
        self._returncode = returncode
        self.stdin = MagicMock()
        self.stdout = self
        self.stderr = _FakeStream(stderr_lines)

    def __iter__(self):
        return self._stdout_lines

    def wait(self):
        return self._returncode


class _FakeStream:
    def __init__(self, lines: list[str]):
        self._lines = iter(lines)

    def __iter__(self):
        return self._lines


@pytest.fixture
def log_paths(tmp_path):
    return tmp_path / "out.log", tmp_path / "err.log"


def _call(stdout_log: Path, stderr_log: Path) -> ClaudeCall:
    return ClaudeCall(
        prompt="test prompt",
        session_id="s",
        new_session=True,
        model=None,
        stdout_log_path=stdout_log,
        stderr_log_path=stderr_log,
        stream_header="── test ──",
    )


def test_real_client_raises_when_claude_not_on_path(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(ClaudeBinaryNotFound):
        RealClaudeClient()


def test_real_client_writes_stdout_log(monkeypatch, log_paths):
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")

    def fake_popen(*args, **kwargs):
        return _FakeProcess(stdout_lines=["hello\n", "world\n"], stderr_lines=[])

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealClaudeClient()
    response = client.call(_call(stdout_log, stderr_log))
    assert response.returncode == 0
    assert response.stdout == "hello\nworld\n"
    assert stdout_log.read_text() == "hello\nworld\n"
    assert stderr_log.read_text() == ""


def test_real_client_writes_stderr_log(monkeypatch, log_paths):
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *a, **k: _FakeProcess(stdout_lines=[], stderr_lines=["warning\n"]),
    )
    client = RealClaudeClient()
    response = client.call(_call(stdout_log, stderr_log))
    assert response.stderr == "warning\n"
    assert stderr_log.read_text() == "warning\n"


def test_real_client_nonzero_exit_raises_with_partial(monkeypatch, log_paths):
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *a, **k: _FakeProcess(
            stdout_lines=["partial\n"], stderr_lines=["boom\n"], returncode=1
        ),
    )
    client = RealClaudeClient()
    with pytest.raises(ClaudeInvocationError) as exc_info:
        client.call(_call(stdout_log, stderr_log))
    assert exc_info.value.response.stdout == "partial\n"
    assert exc_info.value.response.stderr == "boom\n"
    assert exc_info.value.response.returncode == 1


def test_real_client_argv_uses_session_id_on_first_call(monkeypatch, log_paths):
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    captured: dict = {}

    def fake_popen(argv, *a, **k):
        captured["argv"] = argv
        return _FakeProcess(stdout_lines=["x\n"], stderr_lines=[])

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealClaudeClient()
    client.call(_call(stdout_log, stderr_log))
    assert "--session-id" in captured["argv"]
    assert "--resume" not in captured["argv"]


def test_real_client_argv_uses_resume_on_subsequent_call(monkeypatch, log_paths):
    stdout_log, stderr_log = log_paths
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    captured: dict = {}

    def fake_popen(argv, *a, **k):
        captured["argv"] = argv
        return _FakeProcess(stdout_lines=["x\n"], stderr_lines=[])

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    client = RealClaudeClient()
    call = ClaudeCall(
        prompt="p", session_id="s", new_session=False, model=None,
        stdout_log_path=stdout_log, stderr_log_path=stderr_log,
        stream_header="── test ──",
    )
    client.call(call)
    assert "--resume" in captured["argv"]
    assert "--session-id" not in captured["argv"]
```

- [ ] **Step 7.3: Run the real-client tests and verify they pass**

Shell:
```bash
pytest tests/cli/prompt_runner/test_claude_client.py -v
```

Expected: all tests PASS.

- [ ] **Step 7.4: Commit**

```bash
git add src/cli/prompt_runner/claude_client.py tests/cli/prompt_runner/test_claude_client.py
git commit -m "feat(prompt-runner): add streaming RealClaudeClient with log capture"
```

---

## Task 8: run subcommand, halt banner, and success banner

**Files:**
- Modify: *src/cli/prompt_runner/__main__.py*

Design reference: §5 (CLI shape), §11.3 (halt semantics), §11.4 (success banner) in *CD-001-prompt-runner.md*.

- [ ] **Step 8.1: Add the run subcommand to __main__.py**

Replace the contents of *src/cli/prompt_runner/__main__.py* with:

```python
"""prompt-runner CLI entry point."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from prompt_runner.claude_client import (
    ClaudeBinaryNotFound,
    DryRunClaudeClient,
    RealClaudeClient,
)
from prompt_runner.parser import ParseError, PromptPair, parse_file
from prompt_runner.runner import PipelineResult, RunConfig, run_pipeline


BANNER_RULE = "═" * 70


def _format_pair_summary(pair: PromptPair, full: bool) -> str:
    gen_lines = pair.generation_prompt.splitlines()
    val_lines = pair.validation_prompt.splitlines()
    header = (
        f"═══ Prompt {pair.index}: {pair.title} ═══\n"
        f"  heading line: {pair.heading_line}\n"
        f"  generation prompt: {len(gen_lines)} lines, "
        f"{len(pair.generation_prompt)} chars\n"
        f"  validation prompt: {len(val_lines)} lines, "
        f"{len(pair.validation_prompt)} chars"
    )
    if full:
        return (
            f"{header}\n"
            f"  ─── generation ───\n"
            f"{_indent(pair.generation_prompt)}\n"
            f"  ─── validation ───\n"
            f"{_indent(pair.validation_prompt)}"
        )
    preview_gen = "\n".join(gen_lines[:3])
    preview_val = "\n".join(val_lines[:3])
    return (
        f"{header}\n"
        f"  ─── generation (first 3 lines) ───\n"
        f"{_indent(preview_gen)}\n"
        f"  ─── validation (first 3 lines) ───\n"
        f"{_indent(preview_val)}"
    )


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _cmd_parse(args: argparse.Namespace) -> int:
    try:
        pairs = parse_file(Path(args.file))
    except ParseError as err:
        sys.stderr.write(f"{err.error_id}\n\n{err.message}\n")
        return 2
    for pair in pairs:
        sys.stdout.write(_format_pair_summary(pair, full=args.full) + "\n\n")
    return 0


def _default_run_dir(source: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return Path("runs") / f"{ts}-{source.stem}"


def _cmd_run(args: argparse.Namespace) -> int:
    source = Path(args.file)
    try:
        pairs = parse_file(source)
    except ParseError as err:
        _print_error_banner(err.error_id, err.message)
        return 2

    config = RunConfig(
        max_iterations=args.max_iterations,
        model=args.model,
        only=args.only,
        dry_run=args.dry_run,
    )

    try:
        client = DryRunClaudeClient() if args.dry_run else RealClaudeClient()
    except ClaudeBinaryNotFound as err:
        _print_error_banner("R-NO-CLAUDE", str(err))
        return 3

    run_dir = Path(args.output_dir) if args.output_dir else _default_run_dir(source)

    result = run_pipeline(
        pairs=pairs,
        run_dir=run_dir,
        config=config,
        claude_client=client,
        source_file=source,
    )

    if result.halted_early:
        _print_error_banner("HALT", result.halt_reason or "pipeline halted")
        # Exit code: 1 for escalation-style halts, 3 for runtime-style halts.
        reason = result.halt_reason or ""
        if reason.startswith("R-"):
            return 3
        return 1

    _print_success_banner(run_dir)
    return 0


def _print_error_banner(error_id: str, message: str) -> None:
    sys.stderr.write(f"\n{BANNER_RULE}\nERROR: {error_id}\n{BANNER_RULE}\n")
    sys.stderr.write(f"{message}\n{BANNER_RULE}\n")
    sys.stderr.flush()


def _print_success_banner(run_dir: Path) -> None:
    summary_path = run_dir / "summary.txt"
    summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
    sys.stdout.write(f"\n{BANNER_RULE}\nPrompt Runner — Run complete\n{BANNER_RULE}\n")
    sys.stdout.write(f"{summary}\n{BANNER_RULE}\n")
    sys.stdout.flush()


def _build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="prompt-runner",
        description="Run prompt/validator pairs from a markdown file through the Claude CLI.",
    )
    sub = root.add_subparsers(dest="command", required=True)

    parse_cmd = sub.add_parser("parse", help="Parse the file and print prompt pairs.")
    parse_cmd.add_argument("file", help="Path to the input markdown file.")
    parse_cmd.add_argument("--full", action="store_true",
                           help="Dump complete generator and validator bodies verbatim.")
    parse_cmd.set_defaults(func=_cmd_parse)

    run_cmd = sub.add_parser("run", help="Execute the full pipeline.")
    run_cmd.add_argument("file", help="Path to the input markdown file.")
    run_cmd.add_argument("--output-dir", default=None,
                         help="Run directory (default: ./runs/<timestamp>-<stem>/).")
    run_cmd.add_argument("--max-iterations", type=int, default=3,
                         help="Max revision iterations per prompt (default: 3).")
    run_cmd.add_argument("--model", default=None,
                         help="Passed through as --model to claude -p.")
    run_cmd.add_argument("--only", type=int, default=None,
                         help="Run only prompt number N (debug).")
    run_cmd.add_argument("--dry-run", action="store_true",
                         help="Parse and show the planned sequence without calling claude.")
    run_cmd.set_defaults(func=_cmd_run)

    return root


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 8.2: Add CLI integration tests**

Append to *tests/cli/prompt_runner/test_runner.py*:

```python
from prompt_runner.__main__ import main


def test_cli_parse_subcommand_prints_all_prompts(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures" / "sample-prompts.md"
    exit_code = main(["parse", str(fixture)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Prompt 1: First Thing" in out
    assert "Prompt 2: Second Thing" in out


def test_cli_parse_subcommand_reports_parse_error(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures" / "missing-validator.md"
    exit_code = main(["parse", str(fixture)])
    err = capsys.readouterr().err
    assert exit_code == 2
    assert "E-MISSING-VALIDATION" in err
```

- [ ] **Step 8.3: Run all tests and verify they pass**

Shell:
```bash
pytest -v
```

Expected: every test in the suite PASSES.

- [ ] **Step 8.4: Dry-run smoke test against the motivating file**

Shell:
```bash
prompt-runner run /Users/martinbechard/Downloads/ai-development-methodology-prompts_1.md --dry-run --output-dir /tmp/pr-dry-run
```

Expected: the command completes (or halts on R-NO-VERDICT because DryRunClaudeClient returns a placeholder that has no VERDICT line). A *runs/*, *manifest.json*, and *summary.txt* appear in */tmp/pr-dry-run*. Whatever exit code the runner returns, the absence of stack traces confirms the control flow is wired.

- [ ] **Step 8.5: Commit**

```bash
git add src/cli/prompt_runner/__main__.py tests/cli/prompt_runner/test_runner.py
git commit -m "feat(prompt-runner): add run subcommand with halt and success banners"
```

---

## Task 9: Live smoke test against a real Claude binary

**Files:** none (manual verification).

Design reference: AC-24 in *docs/testing/AC-001-prompt-runner.md*.

- [ ] **Step 9.1: Verify the claude binary is available**

Shell:
```bash
which claude
claude --version
```

Expected: a path and a version string. If not, the smoke test must be deferred — document the gap in a PR comment or a follow-up.

- [ ] **Step 9.2: Run the tool against the README example fixture**

Shell:
```bash
prompt-runner run tests/cli/prompt_runner/fixtures/readme-example.md --output-dir /tmp/pr-smoke
```

Expected:
- A stream of text appears on the terminal as each prompt's generator and judge produce output. Text must appear progressively, not all at once after a long silence.
- After each prompt, the tool either advances (verdict: pass) or loops (verdict: revise) up to 3 iterations.
- The run either completes (exit code 0 with a success banner) or halts with a framed error banner.
- *ls /tmp/pr-smoke/* shows a *manifest.json*, *summary.txt*, per-prompt directories, and a *logs/* subtree.

- [ ] **Step 9.3: Verify logs were captured**

Shell:
```bash
find /tmp/pr-smoke/logs -type f -name "*.log"
```

Expected: at least four files (2 calls per prompt × 2 prompts × stdout+stderr). Each *stdout.log* should be non-empty.

- [ ] **Step 9.4: Run the implementation AC suite end-to-end**

Shell:
```bash
pytest -v
```

Expected: all tests PASS, indicating every AC from *docs/testing/AC-001-prompt-runner.md* that is automated (everything except AC-24, which is this manual smoke test) is green.

- [ ] **Step 9.5: Commit the README.md at the project root if anything was updated during smoke-testing**

If any fixtures or error messages were tweaked during the smoke test, commit them:

```bash
git status
# review changes
git add -p
git commit -m "fix(prompt-runner): <specific fix from smoke test>"
```

Otherwise, no commit is needed for Task 9.

---

## Self-review

After writing this plan, check against the spec with fresh eyes.

**Spec coverage:**
- §3 input contract → Task 2 fixtures and tests cover all five heading forms, all three fence variants, and all five error cases.
- §6 parser → Task 2 implements the state machine, error catalogue, and all listed tests.
- §7 claude client → Tasks 5 (protocol + doubles) and 7 (real streaming implementation).
- §9 runner engine → Task 6 (data model, prompt builders, run_prompt, run_pipeline, 15+ tests).
- §10 storage layout → Task 6 (*_write_manifest*, *_finalise*, *_format_summary*) + Task 7 (real client writes log files).
- §11 error handling → Task 6 (halt semantics in run_pipeline) + Task 8 (halt/success banners in *__main__*).
- §12 implementation order → This plan follows §12's order exactly, with the README moved to Task 4 per the spec.
- §13 README → Task 4.
- §14 design ACs → this plan's existence is DAC-24; every other DAC has already been verified in the spec review.
- AC-001 implementation ACs → every AC traces to at least one step in this plan:
  - AC-01..06 → Task 2 (parser)
  - AC-07..10 → Task 2 (error catalogue)
  - AC-11..15 → Task 6 (runner + revision loop)
  - AC-16..20 → Task 6 (session handling)
  - AC-21..28 → Tasks 6, 7, 8 (streaming, logs, error display)
  - AC-29..32 → Task 4 (README)
  - AC-33..37 → Task 9 smoke test + cross-cutting runs

**Placeholder scan:** every step shows exact code, exact commands, and expected output. No "TBD", no "implement later", no "similar to Task N" without repeating the content.

**Type consistency:** *PromptPair*, *ClaudeCall*, *ClaudeResponse*, *ClaudeInvocationError*, *Verdict*, *RunConfig*, *PromptResult*, *PipelineResult*, and *IterationResult* are defined in the same files throughout; method and attribute names match across tasks.

**Known gaps / manual steps:**
- AC-24 (streaming appears incrementally on the terminal) is a manual smoke test (Task 9.2) — automating it has disproportionate complexity.
- The plan assumes the agent has *python3* >= 3.12 installed and a working C compiler for any wheels pytest might transitively need. If not, Task 0 pip install will fail — fix by installing Python 3.12 before proceeding.
- Task 0 uses a venv at *.venv/*. If the project adds a different Python environment manager later, update Task 0 accordingly.
