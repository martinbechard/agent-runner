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
    "E-UNCLOSED-REQUIRED-FILES",
    "E-UNCLOSED-CHECKS-FILES",
    "E-UNCLOSED-DETERMINISTIC-VALIDATION",
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
    validation_prompt: str  # empty string when prompt is validator-less
    heading_line: int
    generation_line: int
    validation_line: int   # 0 when there is no validator
    required_files: tuple[str, ...] = ()
    checks_files: tuple[str, ...] = ()
    deterministic_validation: tuple[str, ...] = ()
    interactive: bool = False
    model_override: str | None = None   # e.g. "claude-sonnet-4-6"
    effort_override: str | None = None  # e.g. "low", "medium", "high", "max"


@dataclass(frozen=True)
class VariantPrompt:
    """One variant within a [VARIANTS] fork point."""

    variant_name: str       # "A", "B", etc.
    variant_title: str      # "Long task list", "Two-pass checklist"
    pairs: list[PromptPair] # the prompt pair(s) for this variant


@dataclass(frozen=True)
class ForkPoint:
    """A prompt heading marked [VARIANTS] that forks execution."""

    index: int              # prompt number where the fork occurs
    title: str              # e.g., "Audit coverage"
    heading_line: int
    variants: list[VariantPrompt]


class ParseError(Exception):
    """Raised when the input file does not match the structural contract."""

    def __init__(self, error_id: str, message: str) -> None:
        super().__init__(message)
        self.error_id = error_id
        self.message = message


class _State(Enum):
    SEEK_HEADING = "seek_heading"
    SEEK_FIRST_FENCE = "seek_first_fence"
    IN_REQUIRED_FENCE = "in_required_fence"
    IN_CHECKS_FENCE = "in_checks_fence"
    IN_DETERMINISTIC_VALIDATION_FENCE = "in_deterministic_validation_fence"
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
_INTERACTIVE_RE = re.compile(r"\s*\[interactive\]\s*$", re.IGNORECASE)
_VARIANTS_RE = re.compile(r"\s*\[variants\]\s*$", re.IGNORECASE)
_MODEL_RE = re.compile(r"\[MODEL:([^\]]+)\]", re.IGNORECASE)
_EFFORT_RE = re.compile(r"\[EFFORT:([^\]]+)\]", re.IGNORECASE)
_VARIANT_HEADING_RE = re.compile(
    r"^###\s+Variant\s+(\S+?)\s*:\s*(.+?)\s*$"
)
_FENCE_RE = re.compile(r"^```[A-Za-z0-9_+\-]*\s*$")
_UNTITLED = "(untitled)"
_REQUIRED_FILES_FENCE_RE = re.compile(r"^```required-files\s*$", re.IGNORECASE)
_CHECKS_FILES_FENCE_RE = re.compile(r"^```checks-files\s*$", re.IGNORECASE)
_DETERMINISTIC_VALIDATION_FENCE_RE = re.compile(
    r"^```deterministic-validation\s*$",
    re.IGNORECASE,
)


def _extract_directives(raw_title: str) -> tuple[str, str | None, str | None]:
    """Strip [MODEL:xxx] and [EFFORT:xxx] from raw_title.

    Returns (cleaned_title, model_value, effort_value). Each directive is
    removed from the title and its value captured; missing directives yield
    None. Whitespace is normalised after removal.
    """
    model_value: str | None = None
    effort_value: str | None = None

    model_match = _MODEL_RE.search(raw_title)
    if model_match is not None:
        model_value = model_match.group(1)
        raw_title = raw_title[:model_match.start()] + raw_title[model_match.end():]

    effort_match = _EFFORT_RE.search(raw_title)
    if effort_match is not None:
        effort_value = effort_match.group(1)
        raw_title = raw_title[:effort_match.start()] + raw_title[effort_match.end():]

    # Collapse any double spaces left behind and strip edges.
    cleaned = " ".join(raw_title.split())
    return cleaned, model_value, effort_value
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
    required_files: list[str] = field(default_factory=list)
    checks_files: list[str] = field(default_factory=list)
    deterministic_validation: list[str] = field(default_factory=list)
    generation_lines: list[str] = field(default_factory=list)
    validation_lines: list[str] = field(default_factory=list)
    interactive: bool = False
    model_override: str | None = None
    effort_override: str | None = None

    def to_pair(self) -> PromptPair:
        return PromptPair(
            index=self.index,
            title=self.title or _UNTITLED,
            generation_prompt="\n".join(self.generation_lines),
            validation_prompt="\n".join(self.validation_lines),
            heading_line=self.heading_line,
            generation_line=self.generation_line,
            validation_line=self.validation_line,
            required_files=tuple(self.required_files),
            checks_files=tuple(self.checks_files),
            deterministic_validation=tuple(self.deterministic_validation),
            interactive=self.interactive,
            model_override=self.model_override,
            effort_override=self.effort_override,
        )


def parse_file(path: Path) -> list[PromptPair | ForkPoint]:
    """Parse a markdown file into a list of PromptPair and ForkPoint objects.

    Raises ParseError (carrying an error_id from ERROR_IDS) if the file does
    not match the structural contract defined in CD-001 §3.
    """
    text = Path(path).read_text(encoding="utf-8")
    return parse_text(text)


def parse_text(text: str) -> list[PromptPair | ForkPoint]:
    lines = text.splitlines()
    items: list[PromptPair | ForkPoint] = []
    state = _State.SEEK_HEADING
    current: _Accumulator | None = None
    # When processing a [VARIANTS] heading, these hold the in-progress data.
    variants_title: str = ""
    variants_heading_line: int = 0
    variants_index: int = 0
    collected_variants: list[VariantPrompt] = []
    # Current variant being built (name, title, accumulated pairs, directives).
    current_variant_name: str = ""
    current_variant_title: str = ""
    current_variant_pairs: list[PromptPair] = []
    current_variant_model: str | None = None
    current_variant_effort: str | None = None
    in_variants_section: bool = False

    def _flush_current_variant() -> None:
        """Finalize the in-progress variant and append to collected_variants."""
        if current_variant_name:
            collected_variants.append(VariantPrompt(
                variant_name=current_variant_name,
                variant_title=current_variant_title,
                pairs=list(current_variant_pairs),
            ))

    def _flush_variants_fork(next_boundary_line: int, boundary_kind: str) -> None:
        """Close out the current [VARIANTS] section and emit a ForkPoint."""
        nonlocal in_variants_section
        _flush_current_variant()
        if not collected_variants:
            raise ParseError(
                "E-NO-BLOCKS",
                f'Prompt {variants_index} "{variants_title}" (line {variants_heading_line}): '
                f"[VARIANTS] heading has no ### Variant subsections. "
                f"Add at least one \"### Variant X: <title>\" subsection with a code block.",
            )
        items.append(ForkPoint(
            index=variants_index,
            title=variants_title,
            heading_line=variants_heading_line,
            variants=list(collected_variants),
        ))
        in_variants_section = False

    for line_index, line in enumerate(lines):
        line_number = line_index + 1

        # Check for a top-level ## Prompt heading.
        heading_match = _HEADING_RE.match(line)
        if heading_match is not None:
            if in_variants_section:
                # Close out the variants fork before starting the next prompt.
                _flush_variants_fork(line_number, _BOUNDARY_HEADING)
            elif current is not None:
                _raise_for_incomplete_state(state, current, line_number, _BOUNDARY_HEADING)
                items.append(current.to_pair())
                current = None

            raw_title = heading_match.group(1).strip()

            # Detect [interactive] and [VARIANTS] markers (mutually exclusive).
            interactive_match = _INTERACTIVE_RE.search(raw_title)
            variants_match = _VARIANTS_RE.search(raw_title)

            if interactive_match is not None and variants_match is not None:
                raise ParseError(
                    "E-NO-BLOCKS",
                    f'Prompt heading at line {line_number}: '
                    f"[interactive] and [VARIANTS] cannot appear on the same heading.",
                )

            if variants_match is not None:
                # Strip the [VARIANTS] marker from the title.
                title_without_variants = raw_title[:variants_match.start()].rstrip()
                # Check for [interactive] in the remainder (it won't be caught by
                # the earlier check when [interactive] precedes [VARIANTS]).
                interactive_m2 = _INTERACTIVE_RE.search(title_without_variants)
                if interactive_m2 is not None:
                    raise ParseError(
                        "E-NO-BLOCKS",
                        f'Prompt heading at line {line_number}: '
                        f"[interactive] and [VARIANTS] cannot appear on the same heading.",
                    )

                # Set up state for collecting variants.
                nonlocal_index = len(items) + 1
                variants_title = title_without_variants or _UNTITLED
                variants_heading_line = line_number
                variants_index = nonlocal_index
                collected_variants.clear()
                current_variant_name = ""
                current_variant_title = ""
                current_variant_pairs.clear()
                current_variant_model = None
                current_variant_effort = None
                in_variants_section = True
                state = _State.SEEK_HEADING  # repurpose: we'll handle sub-headings below
                continue

            if interactive_match is not None:
                title_without_interactive = raw_title[:interactive_match.start()].rstrip()
                title, model_override, effort_override = _extract_directives(title_without_interactive)
                interactive = True
            else:
                title, model_override, effort_override = _extract_directives(raw_title)
                interactive = False

            current = _Accumulator(
                index=len(items) + 1,
                title=title,
                heading_line=line_number,
                interactive=interactive,
                model_override=model_override,
                effort_override=effort_override,
            )
            state = _State.SEEK_FIRST_FENCE
            continue

        # Inside a [VARIANTS] section, look for ### Variant sub-headings.
        if in_variants_section:
            variant_heading_match = _VARIANT_HEADING_RE.match(line)
            if variant_heading_match is not None:
                # If the previous variant ended with a single-fence (validator-less)
                # pair, finalize it before flushing the variant.
                if current is not None and state is _State.SEEK_SECOND_FENCE and current_variant_name:
                    current_variant_pairs.append(current.to_pair())
                # Finalize the previous variant (if any).
                _flush_current_variant()
                current_variant_name = variant_heading_match.group(1)
                raw_variant_title = variant_heading_match.group(2)
                # Extract [MODEL:xxx] and [EFFORT:xxx] from the variant heading.
                current_variant_title, current_variant_model, current_variant_effort = (
                    _extract_directives(raw_variant_title)
                )
                current_variant_pairs.clear()
                # Reset accumulator for collecting pairs within this variant.
                current = _Accumulator(
                    index=0,  # variants don't carry individual indices
                    title=current_variant_title,
                    heading_line=line_number,
                    model_override=current_variant_model,
                    effort_override=current_variant_effort,
                )
                state = _State.SEEK_FIRST_FENCE
                continue

            # If we haven't entered any variant sub-heading yet, skip non-fence lines.
            if not current_variant_name:
                continue

            # Otherwise, we are accumulating code blocks within the current variant.
            assert current is not None
            fence_match = _FENCE_RE.match(line)

            if state is _State.SEEK_FIRST_FENCE:
                # Check for standalone [MODEL:xxx] / [EFFORT:xxx] directives
                # between pairs. These update the model/effort for subsequent
                # pairs within this variant.
                mid_model = _MODEL_RE.search(line)
                mid_effort = _EFFORT_RE.search(line)
                if mid_model or mid_effort:
                    if mid_model:
                        current_variant_model = mid_model.group(1)
                        current.model_override = current_variant_model
                    if mid_effort:
                        current_variant_effort = mid_effort.group(1)
                        current.effort_override = current_variant_effort
                    continue
                if fence_match is not None:
                    if _REQUIRED_FILES_FENCE_RE.match(line):
                        state = _State.IN_REQUIRED_FENCE
                    elif _CHECKS_FILES_FENCE_RE.match(line):
                        state = _State.IN_CHECKS_FENCE
                    elif _DETERMINISTIC_VALIDATION_FENCE_RE.match(line):
                        state = _State.IN_DETERMINISTIC_VALIDATION_FENCE
                    else:
                        current.generation_line = line_number
                        state = _State.IN_FIRST_FENCE
                    continue

            if state is _State.IN_REQUIRED_FENCE:
                if fence_match is not None:
                    state = _State.SEEK_FIRST_FENCE
                else:
                    stripped = line.strip()
                    if stripped:
                        current.required_files.append(stripped)
                continue

            if state is _State.IN_CHECKS_FENCE:
                if fence_match is not None:
                    state = _State.SEEK_FIRST_FENCE
                else:
                    stripped = line.strip()
                    if stripped:
                        current.checks_files.append(stripped)
                continue

            if state is _State.IN_DETERMINISTIC_VALIDATION_FENCE:
                if fence_match is not None:
                    state = _State.SEEK_FIRST_FENCE
                else:
                    stripped = line.strip()
                    if stripped:
                        current.deterministic_validation.append(stripped)
                continue

            if state is _State.IN_FIRST_FENCE:
                if fence_match is not None:
                    state = _State.SEEK_SECOND_FENCE
                else:
                    current.generation_lines.append(line)
                continue

            if state is _State.SEEK_SECOND_FENCE:
                # Check for standalone directives between fences. When a
                # directive appears here, it means the current pair is
                # validator-less (single fence) and the directive applies
                # to the NEXT pair.
                mid_model = _MODEL_RE.search(line)
                mid_effort = _EFFORT_RE.search(line)
                if mid_model or mid_effort:
                    # Finalize current pair as validator-less.
                    current_variant_pairs.append(current.to_pair())
                    # Update variant-level defaults for subsequent pairs.
                    if mid_model:
                        current_variant_model = mid_model.group(1)
                    if mid_effort:
                        current_variant_effort = mid_effort.group(1)
                    # Start a fresh accumulator with the new directives.
                    current = _Accumulator(
                        index=0,
                        title=current_variant_title,
                        heading_line=line_number,
                        model_override=current_variant_model,
                        effort_override=current_variant_effort,
                    )
                    state = _State.SEEK_FIRST_FENCE
                    continue
                if fence_match is not None:
                    current.validation_line = line_number
                    state = _State.IN_SECOND_FENCE
                continue

            if state is _State.IN_SECOND_FENCE:
                if fence_match is not None:
                    # Completed a pair; save it and prepare for a possible next pair.
                    current_variant_pairs.append(current.to_pair())
                    current = _Accumulator(
                        index=0,
                        title=current_variant_title,
                        heading_line=line_number,
                        model_override=current_variant_model,
                        effort_override=current_variant_effort,
                    )
                    state = _State.SEEK_FIRST_FENCE
                else:
                    current.validation_lines.append(line)
                continue

            continue

        if state is _State.SEEK_HEADING:
            continue

        assert current is not None
        fence_match = _FENCE_RE.match(line)

        if state is _State.SEEK_FIRST_FENCE:
            if fence_match is not None:
                if _REQUIRED_FILES_FENCE_RE.match(line):
                    state = _State.IN_REQUIRED_FENCE
                elif _CHECKS_FILES_FENCE_RE.match(line):
                    state = _State.IN_CHECKS_FENCE
                elif _DETERMINISTIC_VALIDATION_FENCE_RE.match(line):
                    state = _State.IN_DETERMINISTIC_VALIDATION_FENCE
                else:
                    current.generation_line = line_number
                    state = _State.IN_FIRST_FENCE
            continue

        if state is _State.IN_REQUIRED_FENCE:
            if fence_match is not None:
                state = _State.SEEK_FIRST_FENCE
            else:
                stripped = line.strip()
                if stripped:
                    current.required_files.append(stripped)
            continue

        if state is _State.IN_CHECKS_FENCE:
            if fence_match is not None:
                state = _State.SEEK_FIRST_FENCE
            else:
                stripped = line.strip()
                if stripped:
                    current.checks_files.append(stripped)
            continue

        if state is _State.IN_DETERMINISTIC_VALIDATION_FENCE:
            if fence_match is not None:
                state = _State.SEEK_FIRST_FENCE
            else:
                stripped = line.strip()
                if stripped:
                    current.deterministic_validation.append(stripped)
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
    if in_variants_section:
        # Flush any in-progress variant pair accumulator as a validator-less pair.
        if current is not None and current_variant_name:
            if state is _State.SEEK_SECOND_FENCE:
                # validator-less single-fence: finalize the pair
                current_variant_pairs.append(current.to_pair())
            elif state is _State.SEEK_FIRST_FENCE:
                pass  # no pairs accumulated in this variant yet (already handled by flush)
        _flush_variants_fork(len(lines), _BOUNDARY_EOF)
    elif current is not None:
        if state is _State.SEEK_HEADING:
            items.append(current.to_pair())
        else:
            _raise_for_incomplete_state(
                state, current, next_boundary_line=len(lines),
                boundary_kind=_BOUNDARY_EOF,
            )
            # If we reach here, state was SEEK_EXTRA_CHECK (valid terminal) or
            # SEEK_SECOND_FENCE (validator-less single-fence prompt). In both
            # cases validation_line is already correct (set or 0 by default).
            items.append(current.to_pair())

    return items


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
    if state is _State.IN_REQUIRED_FENCE:
        raise ParseError(
            "E-UNCLOSED-REQUIRED-FILES",
            _format_unclosed_required_files(
                current,
                next_boundary_line=next_boundary_line,
                boundary_kind=boundary_kind,
            ),
        )
    if state is _State.IN_CHECKS_FENCE:
        raise ParseError(
            "E-UNCLOSED-CHECKS-FILES",
            _format_unclosed_checks_files(
                current,
                next_boundary_line=next_boundary_line,
                boundary_kind=boundary_kind,
            ),
        )
    if state is _State.IN_DETERMINISTIC_VALIDATION_FENCE:
        raise ParseError(
            "E-UNCLOSED-DETERMINISTIC-VALIDATION",
            _format_unclosed_deterministic_validation(
                current,
                next_boundary_line=next_boundary_line,
                boundary_kind=boundary_kind,
            ),
        )
    if state is _State.SEEK_SECOND_FENCE:
        # Validator-less single-fence prompt: accepted as valid. Return normally
        # so the caller can finalise the pair with validation_prompt="".
        return
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
    assert state is _State.SEEK_EXTRA_CHECK, (
        f"Unhandled state in _raise_for_incomplete_state: {state}"
    )


def _format_unclosed_required_files(
    current: _Accumulator, next_boundary_line: int, boundary_kind: str
) -> str:
    boundary_text = (
        f"the next prompt heading (found at line {next_boundary_line})"
        if boundary_kind == _BOUNDARY_HEADING
        else "the end of the file"
    )
    return (
        f'Prompt {current.index} "{current.title}" (line {current.heading_line}): '
        f"the required-files block was opened but never closed.\n\n"
        f"Close it with a line containing exactly ``` before {boundary_text}."
    )


def _format_unclosed_checks_files(
    current: _Accumulator, next_boundary_line: int, boundary_kind: str
) -> str:
    boundary_text = (
        f"the next prompt heading (found at line {next_boundary_line})"
        if boundary_kind == _BOUNDARY_HEADING
        else "the end of the file"
    )
    return (
        f'Prompt {current.index} "{current.title}" (line {current.heading_line}): '
        f"the checks-files block was opened but never closed.\n\n"
        f"Close it with a line containing exactly ``` before {boundary_text}."
    )


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


def _format_unclosed_deterministic_validation(
    current: _Accumulator, next_boundary_line: int, boundary_kind: str
) -> str:
    boundary_text = (
        f"the next prompt heading (found at line {next_boundary_line})"
        if boundary_kind == _BOUNDARY_HEADING
        else "the end of the file"
    )
    return (
        f'Prompt {current.index} "{current.title}" (line {current.heading_line}): '
        f"the deterministic-validation block was opened but never closed.\n\n"
        f"Close it with a line containing exactly ``` before {boundary_text}."
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
