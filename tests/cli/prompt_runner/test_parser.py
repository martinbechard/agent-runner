import re
from pathlib import Path

import pytest

from prompt_runner.parser import PromptPair, ParseError, parse_file, parse_text

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
