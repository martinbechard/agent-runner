from pathlib import Path

import pytest

from prompt_runner.parser import ERROR_IDS, ParseError, parse_file, parse_text

FIXTURES = Path(__file__).parent / "fixtures"


def _wrap(heading: str, body: str | None = None) -> str:
    body = body or (
        "### Generation Prompt\n\n"
        "gen\n\n"
        "### Validation Prompt\n\n"
        "val\n"
    )
    return f"{heading}\n\n{body}"


def test_parses_minimal_two_prompt_file():
    pairs = parse_file(FIXTURES / "sample-prompts.md")
    assert len(pairs) == 2
    assert pairs[0].index == 1
    assert pairs[0].title == "First Thing"
    assert pairs[0].generation_prompt == "Generate the first thing.\nIt has multiple lines."
    assert pairs[0].validation_prompt == "Validate the first thing."
    assert pairs[0].heading_line == 3
    assert pairs[0].generation_line == 7
    assert pairs[0].validation_line == 12

    assert pairs[1].index == 2
    assert pairs[1].title == "Second Thing"
    assert pairs[1].generation_prompt == "Generate the second thing."
    assert pairs[1].validation_prompt == "Validate the second thing.\nIt has multiple lines too."


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
        _wrap("## Prompt 5: A") + "\n\n" +
        _wrap("## Prompt 10: B")
    )
    pairs = parse_text(text)
    assert len(pairs) == 2
    assert pairs[0].index == 1
    assert pairs[1].index == 2


def test_required_checks_and_deterministic_sections_are_parsed():
    text = """## Prompt 1: Needs inputs

### Required Files

docs/request.md
relative/extra.txt

### Checks Files

docs/summary.txt
relative/maybe.txt

### Deterministic Validation

scripts/validate_feature_spec.py
--strict

### Generation Prompt

generate

### Validation Prompt

validate
"""
    pairs = parse_text(text)
    assert pairs[0].required_files == ("docs/request.md", "relative/extra.txt")
    assert pairs[0].checks_files == ("docs/summary.txt", "relative/maybe.txt")
    assert pairs[0].deterministic_validation == (
        "scripts/validate_feature_spec.py",
        "--strict",
    )


def test_include_files_section_is_parsed():
    text = """## Prompt 1: Needs includes

### Required Files

docs/request.md

### Include Files

docs/request.md
docs/context.md

### Generation Prompt

generate
"""
    pairs = parse_text(text)
    assert pairs[0].required_files == ("docs/request.md",)
    assert pairs[0].include_files == ("docs/request.md", "docs/context.md")


def test_module_section_is_parsed():
    text = """### Module

requirements-inventory

## Prompt 1: Needs module

### Generation Prompt

generate
"""
    pairs = parse_text(text)
    assert pairs[0].module_slug == "requirements-inventory"


def test_file_level_module_applies_to_all_prompts():
    text = """### Module

requirements-inventory

## Prompt 1: First

### Generation Prompt

gen 1

## Prompt 2: Second

### Generation Prompt

gen 2
"""
    pairs = parse_text(text)
    assert pairs[0].module_slug == "requirements-inventory"
    assert pairs[1].module_slug == "requirements-inventory"


def test_module_inside_prompt_is_rejected():
    text = """## Prompt 1: First

### Module

requirements-inventory

### Generation Prompt

gen 1
"""
    with pytest.raises(ParseError) as exc_info:
        parse_text(text)
    err = exc_info.value
    assert err.error_id == "E-UNKNOWN-SUBSECTION"


def test_missing_file_level_module_falls_back_to_first_prompt_title():
    text = """## Prompt 1: First prompt title

### Generation Prompt

gen 1

## Prompt 2: Second prompt title

### Generation Prompt

gen 2
"""
    pairs = parse_text(text)
    assert pairs[0].module_slug == "First prompt title"
    assert pairs[1].module_slug == "First prompt title"


def test_heading_without_interactive_marker_defaults_to_false():
    pairs = parse_text(_wrap("## Prompt 1: Plain title"))
    assert pairs[0].interactive is False


def test_heading_with_interactive_marker_strips_and_sets_flag():
    text = """## Prompt 1: Author tdd skill [interactive]

### Generation Prompt

mission body
"""
    pairs = parse_text(text)
    assert pairs[0].title == "Author tdd skill"
    assert pairs[0].interactive is True
    assert pairs[0].generation_prompt == "mission body"
    assert pairs[0].validation_prompt == ""
    assert pairs[0].validation_line == 0


def test_interactive_marker_is_case_insensitive():
    for marker in ("[interactive]", "[Interactive]", "[INTERACTIVE]"):
        text = f"""## Prompt 1: Title {marker}

### Generation Prompt

gen
"""
        pairs = parse_text(text)
        assert pairs[0].interactive is True
        assert pairs[0].title == "Title"


def test_brackets_earlier_with_interactive_at_end():
    text = """## Prompt 1: Deal with [brackets] in title [interactive]

### Generation Prompt

gen
"""
    pairs = parse_text(text)
    assert pairs[0].title == "Deal with [brackets] in title"
    assert pairs[0].interactive is True


def test_empty_file_returns_empty_list():
    assert parse_text("") == []


def test_file_with_no_prompt_headings_returns_empty_list():
    assert parse_text("# Introduction\n\nSome prose.\n") == []


def test_error_no_generation():
    with pytest.raises(ParseError) as exc_info:
        parse_file(FIXTURES / "no-blocks.md")
    err = exc_info.value
    assert err.error_id == "E-NO-GENERATION"
    assert '"Empty Section"' in err.message
    assert "Generation Prompt" in err.message


def test_error_validation_before_generation():
    text = """## Prompt 1: Bad order

### Validation Prompt

val
"""
    with pytest.raises(ParseError) as exc_info:
        parse_text(text)
    err = exc_info.value
    assert err.error_id == "E-BAD-SECTION-ORDER"
    assert "Validation Prompt" in err.message
    assert "Generation Prompt" in err.message


def test_error_duplicate_section():
    text = """## Prompt 1: Duplicate

### Generation Prompt

gen 1

### Generation Prompt

gen 2
"""
    with pytest.raises(ParseError) as exc_info:
        parse_text(text)
    err = exc_info.value
    assert err.error_id == "E-DUPLICATE-SECTION"
    assert "Generation Prompt" in err.message


def test_error_unknown_subsection():
    text = """## Prompt 1: Unknown

### Notes

hello
"""
    with pytest.raises(ParseError) as exc_info:
        parse_text(text)
    err = exc_info.value
    assert err.error_id == "E-UNKNOWN-SUBSECTION"
    assert "Notes" in err.message


def test_error_late_required_files():
    text = """## Prompt 1: Late metadata

### Generation Prompt

gen

### Required Files

docs/request.md
"""
    with pytest.raises(ParseError) as exc_info:
        parse_text(text)
    err = exc_info.value
    assert err.error_id == "E-BAD-SECTION-ORDER"
    assert "Required Files" in err.message


def test_model_override_on_prompt_heading():
    text = _wrap("## Prompt 1: Test [MODEL:claude-sonnet-4-6]")
    items = parse_text(text)
    assert items[0].model_override == "claude-sonnet-4-6"
    assert items[0].title == "Test"


def test_effort_override_on_prompt_heading():
    text = _wrap("## Prompt 1: Test [EFFORT:low]")
    items = parse_text(text)
    assert items[0].effort_override == "low"
    assert items[0].title == "Test"


def test_both_model_and_effort():
    text = _wrap("## Prompt 1: Test [MODEL:claude-haiku-4-5-20251001] [EFFORT:medium]")
    items = parse_text(text)
    assert items[0].model_override == "claude-haiku-4-5-20251001"
    assert items[0].effort_override == "medium"
    assert items[0].title == "Test"


def test_error_ids_are_stable():
    assert ERROR_IDS == (
        "E-NO-GENERATION",
        "E-BAD-SECTION-ORDER",
        "E-DUPLICATE-SECTION",
        "E-UNKNOWN-SUBSECTION",
        "E-NO-VARIANTS",
    )
