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
