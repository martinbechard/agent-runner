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


_HEADING_RE = re.compile(
    r"^##\s+Prompt\b"       # required prefix
    r"(?:\s+\d+)?"          # optional heading number (consumed and ignored)
    r"(?:\s*[:\-—]\s*)?"    # optional separator punctuation
    r"(.*?)\s*$"            # title (captured)
)
_FENCE_RE = re.compile(r"^```[A-Za-z0-9_+\-]*\s*$")
_UNTITLED = "(untitled)"
_BOUNDARY_HEADING = "heading"
_BOUNDARY_EOF = "eof"


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
                _raise_for_incomplete_state(state, current, line_number, _BOUNDARY_HEADING)
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
        if state is _State.SEEK_HEADING:
            pairs.append(current.to_pair())
        else:
            _raise_for_incomplete_state(
                state, current, next_boundary_line=len(lines),
                boundary_kind=_BOUNDARY_EOF,
            )
            # If we reach here, state was SEEK_EXTRA_CHECK (valid terminal).
            pairs.append(current.to_pair())

    return pairs


def _raise_for_incomplete_state(
    state: _State,
    current: _Accumulator,
    next_boundary_line: int,
    boundary_kind: str,
) -> None:
    """Raise the appropriate error when the parser hits a boundary while still
    accumulating a prompt. boundary_kind is _BOUNDARY_HEADING or _BOUNDARY_EOF.

    If state is SEEK_EXTRA_CHECK (both blocks captured), this function returns
    normally — the caller should then finalise the current pair.
    """
    if state is _State.SEEK_FIRST_FENCE:
        raise ParseError(
            "E-NO-BLOCKS",
            _format_no_blocks(current, next_boundary_line=next_boundary_line,
                              boundary_kind=boundary_kind),
        )
    if state is _State.SEEK_SECOND_FENCE:
        raise ParseError(
            "E-MISSING-VALIDATION",
            _format_missing_validation(current, next_boundary_line=next_boundary_line,
                                       boundary_kind=boundary_kind),
        )
    if state is _State.IN_FIRST_FENCE:
        raise ParseError(
            "E-UNCLOSED-GENERATION",
            _format_unclosed(current, role="generation",
                             next_boundary_line=next_boundary_line,
                             boundary_kind=boundary_kind),
        )
    if state is _State.IN_SECOND_FENCE:
        raise ParseError(
            "E-UNCLOSED-VALIDATION",
            _format_unclosed(current, role="validation",
                             next_boundary_line=next_boundary_line,
                             boundary_kind=boundary_kind),
        )
    assert state is _State.SEEK_EXTRA_CHECK, f"Unhandled state in _raise_for_incomplete_state: {state}"


def _format_no_blocks(
    current: _Accumulator, next_boundary_line: int, boundary_kind: str
) -> str:
    boundary_text = (
        f"The next prompt heading was found at line {next_boundary_line}"
        if boundary_kind == _BOUNDARY_HEADING
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
        if boundary_kind == _BOUNDARY_HEADING
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
    assert role in ("generation", "validation"), f"Unknown role: {role}"
    opened_line = (
        current.generation_line if role == "generation" else current.validation_line
    )
    boundary_text = (
        f"the next prompt heading (found at line {next_boundary_line})"
        if boundary_kind == _BOUNDARY_HEADING
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
