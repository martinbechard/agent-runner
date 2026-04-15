"""Markdown parser for prompt-runner input files.

The prompt-runner format is heading-based:

- ``## Prompt ...`` starts a prompt section.
- Normal prompt subsections use ``###`` headings.
- Variant containers use ``### Variant ...`` headings.
- Prompt subsections inside a variant use ``####`` headings.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


ERROR_IDS = (
    "E-NO-GENERATION",
    "E-BAD-SECTION-ORDER",
    "E-DUPLICATE-SECTION",
    "E-UNKNOWN-SUBSECTION",
    "E-NO-VARIANTS",
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
    required_files: tuple[str, ...] = ()
    checks_files: tuple[str, ...] = ()
    deterministic_validation: tuple[str, ...] = ()
    module_slug: str | None = None
    interactive: bool = False
    model_override: str | None = None
    effort_override: str | None = None


@dataclass(frozen=True)
class VariantPrompt:
    """One variant within a [VARIANTS] fork point."""

    variant_name: str
    variant_title: str
    pairs: list[PromptPair]


@dataclass(frozen=True)
class ForkPoint:
    """A prompt heading marked [VARIANTS] that forks execution."""

    index: int
    title: str
    heading_line: int
    variants: list[VariantPrompt]


class ParseError(Exception):
    """Raised when the input file does not match the structural contract."""

    def __init__(self, error_id: str, message: str) -> None:
        super().__init__(message)
        self.error_id = error_id
        self.message = message


@dataclass
class _Accumulator:
    index: int
    title: str
    heading_line: int
    generation_line: int = 0
    validation_line: int = 0
    required_files: list[str] = field(default_factory=list)
    checks_files: list[str] = field(default_factory=list)
    deterministic_validation: list[str] = field(default_factory=list)
    module_slug: str | None = None
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
            module_slug=self.module_slug,
            interactive=self.interactive,
            model_override=self.model_override,
            effort_override=self.effort_override,
        )


_HEADING_RE = re.compile(
    r"^##\s+Prompt\b"
    r"(?:\s+\d+)?"
    r"(?:\s*[:\-—]\s*)?"
    r"(.*?)\s*$"
)
_INTERACTIVE_RE = re.compile(r"\s*\[interactive\]\s*$", re.IGNORECASE)
_VARIANTS_RE = re.compile(r"\s*\[variants\]\s*$", re.IGNORECASE)
_MODEL_RE = re.compile(r"\[MODEL:([^\]]+)\]", re.IGNORECASE)
_EFFORT_RE = re.compile(r"\[EFFORT:([^\]]+)\]", re.IGNORECASE)
_VARIANT_HEADING_RE = re.compile(r"^###\s+Variant\s+(\S+?)\s*:\s*(.+?)\s*$")
_LEVEL3_RE = re.compile(r"^###\s+(.+?)\s*$")
_LEVEL4_RE = re.compile(r"^####\s+(.+?)\s*$")
_UNTITLED = "(untitled)"

_GENERATION = "generation"
_VALIDATION = "validation"
_REQUIRED = "required"
_CHECKS = "checks"
_DETERMINISTIC = "deterministic"
_MODULE = "module"


def _extract_directives(raw_title: str) -> tuple[str, str | None, str | None]:
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

    cleaned = " ".join(raw_title.split())
    return cleaned, model_value, effort_value


def parse_file(path: Path) -> list[PromptPair | ForkPoint]:
    text = Path(path).read_text(encoding="utf-8")
    return parse_text(text)


def parse_text(text: str) -> list[PromptPair | ForkPoint]:
    lines = text.splitlines()
    items: list[PromptPair | ForkPoint] = []
    line_count = len(lines)
    cursor = 0

    while cursor < line_count:
        heading_match = _HEADING_RE.match(lines[cursor])
        if heading_match is None:
            cursor += 1
            continue

        raw_title = heading_match.group(1).strip()
        interactive_match = _INTERACTIVE_RE.search(raw_title)
        variants_match = _VARIANTS_RE.search(raw_title)
        line_number = cursor + 1

        if interactive_match is not None and variants_match is not None:
            raise ParseError(
                "E-BAD-SECTION-ORDER",
                f"Prompt heading at line {line_number}: "
                f"[interactive] and [VARIANTS] cannot appear on the same heading.",
            )

        next_prompt = _find_next_prompt_heading(lines, cursor + 1)

        if variants_match is not None:
            title_without_variants = raw_title[:variants_match.start()].rstrip()
            interactive_m2 = _INTERACTIVE_RE.search(title_without_variants)
            if interactive_m2 is not None:
                raise ParseError(
                    "E-BAD-SECTION-ORDER",
                    f"Prompt heading at line {line_number}: "
                    f"[interactive] and [VARIANTS] cannot appear on the same heading.",
                )
            title, _, _ = _extract_directives(title_without_variants)
            items.append(_parse_variants_prompt(
                lines=lines,
                start=cursor + 1,
                end=next_prompt,
                index=len(items) + 1,
                title=title or _UNTITLED,
                heading_line=line_number,
            ))
        else:
            if interactive_match is not None:
                title_without_interactive = raw_title[:interactive_match.start()].rstrip()
                title, model_override, effort_override = _extract_directives(title_without_interactive)
                interactive = True
            else:
                title, model_override, effort_override = _extract_directives(raw_title)
                interactive = False
            items.append(_parse_normal_prompt(
                lines=lines,
                start=cursor + 1,
                end=next_prompt,
                index=len(items) + 1,
                title=title or _UNTITLED,
                heading_line=line_number,
                interactive=interactive,
                model_override=model_override,
                effort_override=effort_override,
            ))

        cursor = next_prompt

    return items


def _find_next_prompt_heading(lines: list[str], start: int) -> int:
    for idx in range(start, len(lines)):
        if _HEADING_RE.match(lines[idx]) is not None:
            return idx
    return len(lines)


def _parse_normal_prompt(
    lines: list[str],
    start: int,
    end: int,
    index: int,
    title: str,
    heading_line: int,
    interactive: bool,
    model_override: str | None,
    effort_override: str | None,
) -> PromptPair:
    pair = _Accumulator(
        index=index,
        title=title,
        heading_line=heading_line,
        interactive=interactive,
        model_override=model_override,
        effort_override=effort_override,
    )
    seen_sections: set[str] = set()
    cursor = start

    while cursor < end:
        level3_match = _LEVEL3_RE.match(lines[cursor])
        if level3_match is None:
            cursor += 1
            continue

        section = _normalize_prompt_subsection(level3_match.group(1))
        if section is None:
            raise ParseError(
                "E-UNKNOWN-SUBSECTION",
                _format_unknown_subsection(
                    index=index,
                    title=title,
                    heading_line=heading_line,
                    subsection_line=cursor + 1,
                    raw_heading=level3_match.group(1),
                    expected_level="###",
                ),
            )

        if section in seen_sections:
            raise ParseError(
                "E-DUPLICATE-SECTION",
                _format_duplicate_section(
                    index=index,
                    title=title,
                    heading_line=heading_line,
                    subsection_line=cursor + 1,
                    section_name=_display_name(section),
                    expected_level="###",
                ),
            )

        if section == _VALIDATION and pair.generation_line == 0:
            raise ParseError(
                "E-BAD-SECTION-ORDER",
                _format_bad_order(
                    index=index,
                    title=title,
                    heading_line=heading_line,
                    subsection_line=cursor + 1,
                    found_name="Validation Prompt",
                    required_name="Generation Prompt",
                    expected_level="###",
                ),
            )

        if section in {_REQUIRED, _CHECKS, _DETERMINISTIC, _MODULE} and pair.generation_line != 0:
            raise ParseError(
                "E-BAD-SECTION-ORDER",
                _format_bad_order(
                    index=index,
                    title=title,
                    heading_line=heading_line,
                    subsection_line=cursor + 1,
                    found_name=_display_name(section),
                    required_name="Generation Prompt",
                    expected_level="###",
                    before_generation_only=True,
                ),
            )

        section_heading_line = cursor + 1
        body_lines, cursor = _collect_section_body(
            lines=lines,
            start=cursor + 1,
            end=end,
            boundary_predicate=lambda idx: _LEVEL3_RE.match(lines[idx]) is not None,
        )

        seen_sections.add(section)
        _assign_section(pair, section, body_lines, heading_line=section_heading_line)

    if pair.generation_line == 0:
        raise ParseError(
            "E-NO-GENERATION",
            _format_no_generation(index, title, heading_line, "###"),
        )

    return pair.to_pair()


def _parse_variants_prompt(
    lines: list[str],
    start: int,
    end: int,
    index: int,
    title: str,
    heading_line: int,
) -> ForkPoint:
    variants: list[VariantPrompt] = []
    cursor = start

    while cursor < end:
        variant_match = _VARIANT_HEADING_RE.match(lines[cursor])
        if variant_match is None:
            cursor += 1
            continue

        variant_name = variant_match.group(1)
        raw_variant_title = variant_match.group(2)
        variant_title, variant_model, variant_effort = _extract_directives(raw_variant_title)
        next_variant = _find_next_variant_heading(lines, cursor + 1, end)
        pairs = _parse_variant_pairs(
            lines=lines,
            start=cursor + 1,
            end=next_variant,
            variant_title=variant_title,
            heading_line=cursor + 1,
            model_override=variant_model,
            effort_override=variant_effort,
        )
        variants.append(VariantPrompt(
            variant_name=variant_name,
            variant_title=variant_title,
            pairs=pairs,
        ))
        cursor = next_variant

    if not variants:
        raise ParseError(
            "E-NO-VARIANTS",
            f'Prompt {index} "{title}" (line {heading_line}): '
            f"[VARIANTS] requires at least one \"### Variant X: <title>\" subsection.",
        )

    return ForkPoint(
        index=index,
        title=title,
        heading_line=heading_line,
        variants=variants,
    )


def _find_next_variant_heading(lines: list[str], start: int, end: int) -> int:
    for idx in range(start, end):
        if _VARIANT_HEADING_RE.match(lines[idx]) is not None:
            return idx
    return end


def _parse_variant_pairs(
    lines: list[str],
    start: int,
    end: int,
    variant_title: str,
    heading_line: int,
    model_override: str | None,
    effort_override: str | None,
) -> list[PromptPair]:
    cursor = start
    pairs: list[PromptPair] = []
    current = _Accumulator(
        index=0,
        title=variant_title,
        heading_line=heading_line,
        model_override=model_override,
        effort_override=effort_override,
    )
    seen_sections: set[str] = set()
    current_model = model_override
    current_effort = effort_override

    def flush_current() -> None:
        nonlocal current, seen_sections
        if current.generation_line == 0:
            return
        pairs.append(current.to_pair())
        current = _Accumulator(
            index=0,
            title=variant_title,
            heading_line=heading_line,
            model_override=current_model,
            effort_override=current_effort,
        )
        seen_sections = set()

    while cursor < end:
        variant_heading = _VARIANT_HEADING_RE.match(lines[cursor])
        if variant_heading is not None:
            break

        level4_match = _LEVEL4_RE.match(lines[cursor])
        if level4_match is not None:
            section = _normalize_prompt_subsection(level4_match.group(1))
            if section is None:
                raise ParseError(
                    "E-UNKNOWN-SUBSECTION",
                    _format_unknown_subsection(
                        index=0,
                        title=variant_title,
                        heading_line=heading_line,
                        subsection_line=cursor + 1,
                        raw_heading=level4_match.group(1),
                        expected_level="####",
                    ),
                )

            if section == _GENERATION and current.generation_line != 0:
                flush_current()

            if section in seen_sections:
                raise ParseError(
                    "E-DUPLICATE-SECTION",
                    _format_duplicate_section(
                        index=0,
                        title=variant_title,
                        heading_line=heading_line,
                        subsection_line=cursor + 1,
                        section_name=_display_name(section),
                        expected_level="####",
                    ),
                )

            if section == _VALIDATION and current.generation_line == 0:
                raise ParseError(
                    "E-BAD-SECTION-ORDER",
                    _format_bad_order(
                        index=0,
                        title=variant_title,
                        heading_line=heading_line,
                        subsection_line=cursor + 1,
                        found_name="Validation Prompt",
                        required_name="Generation Prompt",
                        expected_level="####",
                    ),
                )

            if section in {_REQUIRED, _CHECKS, _DETERMINISTIC, _MODULE} and current.generation_line != 0:
                raise ParseError(
                    "E-BAD-SECTION-ORDER",
                    _format_bad_order(
                        index=0,
                        title=variant_title,
                        heading_line=heading_line,
                        subsection_line=cursor + 1,
                        found_name=_display_name(section),
                        required_name="Generation Prompt",
                        expected_level="####",
                        before_generation_only=True,
                    ),
                )

            section_heading_line = cursor + 1
            body_lines, cursor = _collect_section_body(
                lines=lines,
                start=cursor + 1,
                end=end,
                boundary_predicate=lambda idx: (
                    _LEVEL4_RE.match(lines[idx]) is not None
                    or _VARIANT_HEADING_RE.match(lines[idx]) is not None
                    or _MODEL_RE.search(lines[idx]) is not None
                    or _EFFORT_RE.search(lines[idx]) is not None
                ),
            )
            seen_sections.add(section)
            _assign_section(current, section, body_lines, heading_line=section_heading_line)
            continue

        if current.generation_line == 0:
            pass

        mid_model = _MODEL_RE.search(lines[cursor])
        mid_effort = _EFFORT_RE.search(lines[cursor])
        if mid_model or mid_effort:
            if current.generation_line != 0:
                flush_current()
            if mid_model:
                current_model = mid_model.group(1)
            if mid_effort:
                current_effort = mid_effort.group(1)
            current.model_override = current_model
            current.effort_override = current_effort
            cursor += 1
            continue
        cursor += 1

    flush_current()

    if not pairs:
        raise ParseError(
            "E-NO-GENERATION",
            _format_no_generation(0, variant_title, heading_line, "####"),
        )

    return pairs


def _collect_section_body(
    lines: list[str],
    start: int,
    end: int,
    boundary_predicate,
) -> tuple[list[str], int]:
    cursor = start
    body: list[str] = []
    while cursor < end and not boundary_predicate(cursor):
        body.append(lines[cursor])
        cursor += 1
    return _trim_blank_edges(body), cursor


def _trim_blank_edges(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and lines[start].strip() == "":
        start += 1
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    return lines[start:end]


def _assign_section(
    pair: _Accumulator,
    section: str,
    body_lines: list[str],
    heading_line: int,
) -> None:
    if section == _GENERATION:
        pair.generation_line = heading_line
        pair.generation_lines = body_lines
        return
    if section == _VALIDATION:
        pair.validation_line = heading_line
        pair.validation_lines = body_lines
        return
    if section == _REQUIRED:
        pair.required_files = [line.strip() for line in body_lines if line.strip()]
        return
    if section == _CHECKS:
        pair.checks_files = [line.strip() for line in body_lines if line.strip()]
        return
    if section == _DETERMINISTIC:
        pair.deterministic_validation = [line.strip() for line in body_lines if line.strip()]
        return
    if section == _MODULE:
        values = [line.strip() for line in body_lines if line.strip()]
        pair.module_slug = values[0] if values else None
        return
    raise AssertionError(f"Unhandled section {section}")


def _normalize_prompt_subsection(raw_heading: str) -> str | None:
    normalized = " ".join(raw_heading.strip().lower().split())
    if normalized == "generation prompt":
        return _GENERATION
    if normalized == "validation prompt":
        return _VALIDATION
    if normalized == "required files":
        return _REQUIRED
    if normalized == "checks files":
        return _CHECKS
    if normalized == "deterministic validation":
        return _DETERMINISTIC
    if normalized == "module":
        return _MODULE
    return None


def _display_name(section: str) -> str:
    mapping = {
        _GENERATION: "Generation Prompt",
        _VALIDATION: "Validation Prompt",
        _REQUIRED: "Required Files",
        _CHECKS: "Checks Files",
        _DETERMINISTIC: "Deterministic Validation",
        _MODULE: "Module",
    }
    return mapping[section]


def _format_no_generation(index: int, title: str, heading_line: int, expected_level: str) -> str:
    prompt_label = f'Prompt "{title}"' if index == 0 else f'Prompt {index} "{title}"'
    return (
        f"{prompt_label} (line {heading_line}): no generation prompt section was found.\n\n"
        f'Add a "{expected_level} Generation Prompt" subsection inside this section.'
    )


def _format_duplicate_section(
    index: int,
    title: str,
    heading_line: int,
    subsection_line: int,
    section_name: str,
    expected_level: str,
) -> str:
    prompt_label = f'Prompt "{title}"' if index == 0 else f'Prompt {index} "{title}"'
    return (
        f"{prompt_label} (line {heading_line}): "
        f"{section_name} appears more than once; the duplicate starts at line {subsection_line}.\n\n"
        f'Keep at most one "{expected_level} {section_name}" subsection per prompt pair.'
    )


def _format_bad_order(
    index: int,
    title: str,
    heading_line: int,
    subsection_line: int,
    found_name: str,
    required_name: str,
    expected_level: str,
    before_generation_only: bool = False,
) -> str:
    prompt_label = f'Prompt "{title}"' if index == 0 else f'Prompt {index} "{title}"'
    if before_generation_only:
        repair = (
            f'"{expected_level} {found_name}" must appear before '
            f'"{expected_level} {required_name}".'
        )
    else:
        repair = (
            f'"{expected_level} {found_name}" cannot appear before '
            f'"{expected_level} {required_name}".'
        )
    return (
        f"{prompt_label} (line {heading_line}): "
        f"{found_name} starts at line {subsection_line} in the wrong order.\n\n"
        f"{repair}"
    )


def _format_unknown_subsection(
    index: int,
    title: str,
    heading_line: int,
    subsection_line: int,
    raw_heading: str,
    expected_level: str,
) -> str:
    prompt_label = f'Prompt "{title}"' if index == 0 else f'Prompt {index} "{title}"'
    return (
        f"{prompt_label} (line {heading_line}): "
        f'unrecognized subsection "{raw_heading}" at line {subsection_line}.\n\n'
        f"Allowed prompt subsections at this level are: "
        f'"{expected_level} Module", "{expected_level} Required Files", "{expected_level} Checks Files", '
        f'"{expected_level} Deterministic Validation", "{expected_level} Generation Prompt", '
        f'and "{expected_level} Validation Prompt".'
    )
