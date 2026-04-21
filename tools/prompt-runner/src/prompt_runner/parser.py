"""Markdown parser for prompt-runner input files.

The prompt-runner format is heading-based:

- ``### Module`` may appear once before the first prompt heading and applies
  to the whole file.
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
    "E-BAD-PATH-ENTRY",
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
    retry_prompt: str
    heading_line: int
    generation_line: int
    validation_line: int
    retry_line: int
    required_files: tuple[str, ...] = ()
    include_files: tuple[str, ...] = ()
    checks_files: tuple[str, ...] = ()
    deterministic_validation: tuple[str, ...] = ()
    retry_mode: str = "replace"
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
    selector_prompt: str = ""
    selector_retry_prompt: str = ""
    selection_include_files: tuple[str, ...] = ()


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
    retry_line: int = 0
    required_files: list[str] = field(default_factory=list)
    include_files: list[str] = field(default_factory=list)
    checks_files: list[str] = field(default_factory=list)
    deterministic_validation: list[str] = field(default_factory=list)
    retry_mode: str = "replace"
    module_slug: str | None = None
    generation_lines: list[str] = field(default_factory=list)
    validation_lines: list[str] = field(default_factory=list)
    retry_lines: list[str] = field(default_factory=list)
    interactive: bool = False
    model_override: str | None = None
    effort_override: str | None = None

    def to_pair(self) -> PromptPair:
        return PromptPair(
            index=self.index,
            title=self.title or _UNTITLED,
            generation_prompt="\n".join(self.generation_lines),
            validation_prompt="\n".join(self.validation_lines),
            retry_prompt="\n".join(self.retry_lines),
            heading_line=self.heading_line,
            generation_line=self.generation_line,
            validation_line=self.validation_line,
            retry_line=self.retry_line,
            required_files=tuple(self.required_files),
            include_files=tuple(self.include_files),
            checks_files=tuple(self.checks_files),
            deterministic_validation=tuple(self.deterministic_validation),
            retry_mode=self.retry_mode,
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
_SELECT_RE = re.compile(r"\s*\[select\]\s*$", re.IGNORECASE)
_MODEL_RE = re.compile(r"\[MODEL:([^\]]+)\]", re.IGNORECASE)
_EFFORT_RE = re.compile(r"\[EFFORT:([^\]]+)\]", re.IGNORECASE)
_VARIANT_HEADING_RE = re.compile(r"^###\s+Variant\s+(\S+?)\s*:\s*(.+?)\s*$")
_LEVEL3_RE = re.compile(r"^###\s+(.+?)\s*$")
_LEVEL4_RE = re.compile(r"^####\s+(.+?)\s*$")
_UNTITLED = "(untitled)"

_GENERATION = "generation"
_VALIDATION = "validation"
_REQUIRED = "required"
_INCLUDE = "include"
_CHECKS = "checks"
_DETERMINISTIC = "deterministic"
_RETRY = "retry"
_MODULE = "module"
_SELECTION_INCLUDE = "selection_include"
_SELECTOR_PROMPT = "selector_prompt"
_SELECTOR_RETRY = "selector_retry"
_RETRY_MODE_RE = re.compile(
    r"^retry prompt(?:\s*\[(replace|append|prepend)\])?$",
    re.IGNORECASE,
)
_MARKDOWN_LIST_RE = re.compile(r"^(?:[-+*]|\d+\.)\s+")


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
    file_module_slug = _parse_file_module_slug(lines)
    cursor = 0

    while cursor < line_count:
        heading_match = _HEADING_RE.match(lines[cursor])
        if heading_match is None:
            cursor += 1
            continue

        raw_title = heading_match.group(1).strip()
        line_number = cursor + 1

        stripped_title = raw_title
        interactive = False
        variants_enabled = False
        selection_enabled = False
        while True:
            if _INTERACTIVE_RE.search(stripped_title) is not None:
                interactive = True
                stripped_title = _INTERACTIVE_RE.sub("", stripped_title).rstrip()
                continue
            if _SELECT_RE.search(stripped_title) is not None:
                selection_enabled = True
                stripped_title = _SELECT_RE.sub("", stripped_title).rstrip()
                continue
            if _VARIANTS_RE.search(stripped_title) is not None:
                variants_enabled = True
                stripped_title = _VARIANTS_RE.sub("", stripped_title).rstrip()
                continue
            break

        if interactive and variants_enabled:
            raise ParseError(
                "E-BAD-SECTION-ORDER",
                f"Prompt heading at line {line_number}: "
                f"[interactive] and [VARIANTS] cannot appear on the same heading.",
            )
        if selection_enabled and not variants_enabled:
            raise ParseError(
                "E-BAD-SECTION-ORDER",
                f"Prompt heading at line {line_number}: "
                f"[SELECT] requires [VARIANTS] on the same heading.",
            )

        next_prompt = _find_next_prompt_heading(lines, cursor + 1)

        if variants_enabled:
            title, _, _ = _extract_directives(stripped_title)
            items.append(_parse_variants_prompt(
                lines=lines,
                start=cursor + 1,
                end=next_prompt,
                index=len(items) + 1,
                title=title or _UNTITLED,
                heading_line=line_number,
                selection_enabled=selection_enabled,
            ))
        else:
            title, model_override, effort_override = _extract_directives(stripped_title)
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

    return _apply_file_module_scope(items, file_module_slug)


def _parse_file_module_slug(lines: list[str]) -> str | None:
    """Parse an optional file-level module slug from the preamble.

    A `### Module` block that appears before the first prompt heading is treated
    as file-level metadata and applies to the whole prompt file.
    """
    first_prompt = _find_next_prompt_heading(lines, 0)
    cursor = 0
    seen_module = False
    while cursor < first_prompt:
        match = _LEVEL3_RE.match(lines[cursor])
        if match is None:
            cursor += 1
            continue
        raw_heading = " ".join(match.group(1).strip().lower().split())
        if raw_heading != "module":
            raise ParseError(
                "E-UNKNOWN-SUBSECTION",
                f'File preamble line {cursor + 1}: only "### Module" is allowed before the first prompt heading.',
            )
        if seen_module:
            raise ParseError(
                "E-DUPLICATE-SECTION",
                f'File preamble line {cursor + 1}: "### Module" may appear at most once before the first prompt heading.',
            )
        body_lines, cursor = _collect_section_body(
            lines=lines,
            start=cursor + 1,
            end=first_prompt,
            boundary_predicate=lambda idx: _LEVEL3_RE.match(lines[idx]) is not None,
        )
        seen_module = True
        values = [line.strip() for line in body_lines if line.strip()]
        if values:
            return values[0]
    return None


def _apply_file_module_scope(
    items: list[PromptPair | ForkPoint],
    file_module_slug: str | None,
) -> list[PromptPair | ForkPoint]:
    """Apply one file-level module slug consistently across the whole parsed file."""
    module_slug = file_module_slug
    if module_slug is None:
        first_pair = _first_prompt_pair(items)
        if first_pair is None:
            return items
        module_slug = first_pair.title

    scoped_items: list[PromptPair | ForkPoint] = []
    for item in items:
        if isinstance(item, PromptPair):
            scoped_items.append(PromptPair(
                index=item.index,
                title=item.title,
                generation_prompt=item.generation_prompt,
                validation_prompt=item.validation_prompt,
                heading_line=item.heading_line,
                generation_line=item.generation_line,
                validation_line=item.validation_line,
                retry_prompt=item.retry_prompt,
                retry_line=item.retry_line,
                required_files=item.required_files,
                include_files=item.include_files,
                checks_files=item.checks_files,
                deterministic_validation=item.deterministic_validation,
                retry_mode=item.retry_mode,
                module_slug=module_slug,
                interactive=item.interactive,
                model_override=item.model_override,
                effort_override=item.effort_override,
            ))
            continue

        scoped_variants: list[VariantPrompt] = []
        for variant in item.variants:
            scoped_pairs = [
                PromptPair(
                    index=pair.index,
                    title=pair.title,
                    generation_prompt=pair.generation_prompt,
                    validation_prompt=pair.validation_prompt,
                    heading_line=pair.heading_line,
                    generation_line=pair.generation_line,
                    validation_line=pair.validation_line,
                    retry_prompt=pair.retry_prompt,
                    retry_line=pair.retry_line,
                    required_files=pair.required_files,
                    include_files=pair.include_files,
                    checks_files=pair.checks_files,
                    deterministic_validation=pair.deterministic_validation,
                    retry_mode=pair.retry_mode,
                    module_slug=module_slug,
                    interactive=pair.interactive,
                    model_override=pair.model_override,
                    effort_override=pair.effort_override,
                )
                for pair in variant.pairs
            ]
            scoped_variants.append(VariantPrompt(
                variant_name=variant.variant_name,
                variant_title=variant.variant_title,
                pairs=scoped_pairs,
            ))
        scoped_items.append(ForkPoint(
            index=item.index,
            title=item.title,
            heading_line=item.heading_line,
            variants=scoped_variants,
            selector_prompt=item.selector_prompt,
            selector_retry_prompt=item.selector_retry_prompt,
            selection_include_files=item.selection_include_files,
        ))

    return scoped_items


def _first_prompt_pair(items: list[PromptPair | ForkPoint]) -> PromptPair | None:
    for item in items:
        if isinstance(item, PromptPair):
            return item
        for variant in item.variants:
            if variant.pairs:
                return variant.pairs[0]
    return None


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

        section, retry_mode = _normalize_prompt_subsection(level3_match.group(1))
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

        if section == _RETRY and pair.validation_line == 0:
            raise ParseError(
                "E-BAD-SECTION-ORDER",
                _format_bad_order(
                    index=index,
                    title=title,
                    heading_line=heading_line,
                    subsection_line=cursor + 1,
                    found_name="Retry Prompt",
                    required_name="Validation Prompt",
                    expected_level="###",
                ),
            )

        if section in {_REQUIRED, _INCLUDE, _CHECKS, _DETERMINISTIC} and pair.generation_line != 0:
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
        _assign_section(
            pair,
            section,
            body_lines,
            heading_line=section_heading_line,
            retry_mode=retry_mode,
        )

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
    selection_enabled: bool = False,
) -> ForkPoint:
    variants: list[VariantPrompt] = []
    cursor = start

    while cursor < end:
        variant_match = _VARIANT_HEADING_RE.match(lines[cursor])
        if variant_match is None:
            if _LEVEL3_RE.match(lines[cursor]) is not None:
                break
            cursor += 1
            continue

        variant_name = variant_match.group(1)
        raw_variant_title = variant_match.group(2)
        variant_title, variant_model, variant_effort = _extract_directives(raw_variant_title)
        next_variant = _find_next_variant_boundary(lines, cursor + 1, end)
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

    selector_prompt = ""
    selector_retry_prompt = ""
    selection_include_files: tuple[str, ...] = ()
    if selection_enabled:
        (
            selection_include_files,
            selector_prompt,
            selector_retry_prompt,
        ) = _parse_selection_sections(
            lines=lines,
            start=cursor,
            end=end,
            index=index,
            title=title,
            heading_line=heading_line,
        )

    if not variants:
        raise ParseError(
            "E-NO-VARIANTS",
            f'Prompt {index} "{title}" (line {heading_line}): '
            f"[VARIANTS] requires at least one \"### Variant X: <title>\" subsection.",
        )
    if selection_enabled and not selector_prompt:
        raise ParseError(
            "E-NO-GENERATION",
            f'Prompt {index} "{title}" (line {heading_line}): '
            f"[SELECT] requires a \"### Selector Prompt\" subsection.",
        )

    return ForkPoint(
        index=index,
        title=title,
        heading_line=heading_line,
        variants=variants,
        selector_prompt=selector_prompt,
        selector_retry_prompt=selector_retry_prompt,
        selection_include_files=selection_include_files,
    )


def _parse_selection_sections(
    lines: list[str],
    start: int,
    end: int,
    index: int,
    title: str,
    heading_line: int,
) -> tuple[tuple[str, ...], str, str]:
    cursor = start
    seen_sections: set[str] = set()
    selection_include_files: tuple[str, ...] = ()
    selector_prompt = ""
    selector_retry_prompt = ""

    while cursor < end:
        level3_match = _LEVEL3_RE.match(lines[cursor])
        if level3_match is None:
            cursor += 1
            continue

        section = _normalize_selection_subsection(level3_match.group(1))
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
                    section_name=_display_selection_name(section),
                    expected_level="###",
                ),
            )

        body_lines, cursor = _collect_section_body(
            lines=lines,
            start=cursor + 1,
            end=end,
            boundary_predicate=lambda idx: _LEVEL3_RE.match(lines[idx]) is not None,
        )
        seen_sections.add(section)
        body_text = "\n".join(body_lines)
        if section == _SELECTION_INCLUDE:
            entries: list[str] = []
            for offset, raw_line in enumerate(body_lines, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                if _MARKDOWN_LIST_RE.match(stripped):
                    raise ParseError(
                        "E-BAD-PATH-ENTRY",
                        (
                            f'Prompt {index} "{title}" line {heading_line + offset}: '
                            "Selection Include Files entries must be bare paths, "
                            f"not markdown list items: {stripped}"
                        ),
                    )
                if stripped.startswith("`") and stripped.endswith("`") and len(stripped) >= 2:
                    raise ParseError(
                        "E-BAD-PATH-ENTRY",
                        (
                            f'Prompt {index} "{title}" line {heading_line + offset}: '
                            "Selection Include Files entries must be bare paths, "
                            f"not code-formatted values: {stripped}"
                        ),
                    )
                entries.append(stripped)
            selection_include_files = tuple(entries)
        elif section == _SELECTOR_PROMPT:
            selector_prompt = body_text
        elif section == _SELECTOR_RETRY:
            selector_retry_prompt = body_text

    return selection_include_files, selector_prompt, selector_retry_prompt


def _normalize_selection_subsection(raw_heading: str) -> str | None:
    normalized = " ".join(raw_heading.strip().lower().split())
    if normalized == "selection include files":
        return _SELECTION_INCLUDE
    if normalized == "selector prompt":
        return _SELECTOR_PROMPT
    if normalized == "selector retry prompt":
        return _SELECTOR_RETRY
    return None


def _display_selection_name(section: str) -> str:
    if section == _SELECTION_INCLUDE:
        return "Selection Include Files"
    if section == _SELECTOR_PROMPT:
        return "Selector Prompt"
    if section == _SELECTOR_RETRY:
        return "Selector Retry Prompt"
    return section


def _find_next_variant_boundary(lines: list[str], start: int, end: int) -> int:
    for idx in range(start, end):
        if _VARIANT_HEADING_RE.match(lines[idx]) is not None:
            return idx
        if _LEVEL3_RE.match(lines[idx]) is not None:
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
            section, retry_mode = _normalize_prompt_subsection(level4_match.group(1))
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

            if section == _RETRY and current.validation_line == 0:
                raise ParseError(
                    "E-BAD-SECTION-ORDER",
                    _format_bad_order(
                        index=0,
                        title=variant_title,
                        heading_line=heading_line,
                        subsection_line=cursor + 1,
                        found_name="Retry Prompt",
                        required_name="Validation Prompt",
                        expected_level="####",
                    ),
                )

            if section in {_REQUIRED, _INCLUDE, _CHECKS, _DETERMINISTIC} and current.generation_line != 0:
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
            _assign_section(
                current,
                section,
                body_lines,
                heading_line=section_heading_line,
                retry_mode=retry_mode,
            )
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
    retry_mode: str | None = None,
) -> None:
    if section == _GENERATION:
        pair.generation_line = heading_line
        pair.generation_lines = body_lines
        return
    if section == _VALIDATION:
        pair.validation_line = heading_line
        pair.validation_lines = body_lines
        return
    if section == _RETRY:
        pair.retry_line = heading_line
        pair.retry_lines = body_lines
        pair.retry_mode = retry_mode or "replace"
        return
    if section == _REQUIRED:
        pair.required_files = _parse_path_section_entries(
            pair=pair,
            section=section,
            body_lines=body_lines,
            heading_line=heading_line,
        )
        return
    if section == _INCLUDE:
        pair.include_files = _parse_path_section_entries(
            pair=pair,
            section=section,
            body_lines=body_lines,
            heading_line=heading_line,
        )
        return
    if section == _CHECKS:
        pair.checks_files = _parse_path_section_entries(
            pair=pair,
            section=section,
            body_lines=body_lines,
            heading_line=heading_line,
        )
        return
    if section == _DETERMINISTIC:
        pair.deterministic_validation = [line.strip() for line in body_lines if line.strip()]
        return
    raise AssertionError(f"Unhandled section {section}")


def _parse_path_section_entries(
    pair: _Accumulator,
    section: str,
    body_lines: list[str],
    heading_line: int,
) -> list[str]:
    entries: list[str] = []
    section_name = _display_name(section)
    for offset, raw_line in enumerate(body_lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if _MARKDOWN_LIST_RE.match(stripped):
            raise ParseError(
                "E-BAD-PATH-ENTRY",
                (
                    f'Prompt {pair.index} "{pair.title}" line {heading_line + offset}: '
                    f'{section_name} entries must be bare paths, not markdown list items: '
                    f"{stripped}"
                ),
            )
        if stripped.startswith("`") and stripped.endswith("`") and len(stripped) >= 2:
            raise ParseError(
                "E-BAD-PATH-ENTRY",
                (
                    f'Prompt {pair.index} "{pair.title}" line {heading_line + offset}: '
                    f'{section_name} entries must be bare paths, not code-formatted values: '
                    f"{stripped}"
                ),
            )
        entries.append(stripped)
    return entries


def _normalize_prompt_subsection(raw_heading: str) -> tuple[str | None, str | None]:
    normalized = " ".join(raw_heading.strip().lower().split())
    if normalized == "generation prompt":
        return _GENERATION, None
    if normalized == "validation prompt":
        return _VALIDATION, None
    retry_match = _RETRY_MODE_RE.match(raw_heading.strip())
    if retry_match is not None:
        return _RETRY, (retry_match.group(1) or "replace").lower()
    if normalized == "required files":
        return _REQUIRED, None
    if normalized == "include files":
        return _INCLUDE, None
    if normalized == "checks files":
        return _CHECKS, None
    if normalized == "deterministic validation":
        return _DETERMINISTIC, None
    return None, None


def _display_name(section: str) -> str:
    mapping = {
        _GENERATION: "Generation Prompt",
        _VALIDATION: "Validation Prompt",
        _RETRY: "Retry Prompt",
        _REQUIRED: "Required Files",
        _INCLUDE: "Include Files",
        _CHECKS: "Checks Files",
        _DETERMINISTIC: "Deterministic Validation",
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
        f'"{expected_level} Module", "{expected_level} Required Files", "{expected_level} Include Files", "{expected_level} Checks Files", '
        f'"{expected_level} Deterministic Validation", "{expected_level} Generation Prompt", '
        f'"{expected_level} Validation Prompt", and "{expected_level} Retry Prompt [REPLACE|APPEND|PREPEND]".'
    )
