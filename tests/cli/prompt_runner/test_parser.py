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


def test_single_fence_fixture_now_accepted():
    """The missing-validator fixture has a single-fence prompt section which is
    now accepted as a validator-less pair instead of raising E-MISSING-VALIDATION."""
    pairs = parse_file(FIXTURES / "missing-validator.md")
    assert len(pairs) == 2
    assert pairs[0].title == "Incomplete"
    assert pairs[0].validation_prompt == ""
    assert pairs[0].validation_line == 0
    assert pairs[1].title == "Second"
    assert pairs[1].validation_prompt == "Validator body."


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
    assert "Add" in err.message


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
        ("unclosed-generation.md", "E-UNCLOSED-GENERATION"),
        ("unclosed-validation.md", "E-UNCLOSED-VALIDATION"),
        ("three-fences.md", "E-EXTRA-BLOCK"),
    ]
    bare_fence = re.compile(r"\bfence\b", re.IGNORECASE)
    for filename, expected_id in fixtures_and_ids:
        with pytest.raises(ParseError) as exc_info:
            parse_file(FIXTURES / filename)
        assert exc_info.value.error_id == expected_id, (
            f"{filename}: expected error_id {expected_id}, got {exc_info.value.error_id}"
        )
        assert bare_fence.search(exc_info.value.message) is None, (
            f"{filename}: error message uses bare word 'fence': "
            f"{exc_info.value.message}"
        )


def test_error_ids_are_stable():
    from prompt_runner.parser import ERROR_IDS
    assert ERROR_IDS == (
        "E-NO-BLOCKS",
        "E-MISSING-VALIDATION",
        "E-UNCLOSED-REQUIRED-FILES",
        "E-UNCLOSED-CHECKS-FILES",
        "E-UNCLOSED-DETERMINISTIC-VALIDATION",
        "E-UNCLOSED-GENERATION",
        "E-UNCLOSED-VALIDATION",
        "E-EXTRA-BLOCK",
    )


def test_required_files_block_is_parsed_before_generation():
    text = """## Prompt 1: Needs inputs

```required-files
docs/request.md
relative/extra.txt
```

```
generate
```

```
validate
```
"""
    pairs = parse_text(text)
    assert len(pairs) == 1
    assert pairs[0].required_files == ("docs/request.md", "relative/extra.txt")
    assert pairs[0].generation_prompt == "generate"
    assert pairs[0].validation_prompt == "validate"


def test_error_unclosed_required_files():
    text = """## Prompt 1: Needs inputs

```required-files
docs/request.md
"""
    with pytest.raises(ParseError) as exc_info:
        parse_text(text)
    err = exc_info.value
    assert err.error_id == "E-UNCLOSED-REQUIRED-FILES"
    assert "required-files block" in err.message


def test_checks_files_block_is_parsed_before_generation():
    text = """## Prompt 1: Optional inputs

```checks-files
docs/summary.txt
relative/maybe.txt
```

```
generate
```

```
validate
```
"""
    pairs = parse_text(text)
    assert len(pairs) == 1
    assert pairs[0].checks_files == ("docs/summary.txt", "relative/maybe.txt")


def test_deterministic_validation_block_is_parsed_before_generation():
    text = """## Prompt 1: Optional deterministic validation

```deterministic-validation
scripts/validate_feature_spec.py
--strict
```

```
generate
```

```
validate
```
"""
    pairs = parse_text(text)
    assert len(pairs) == 1
    assert pairs[0].deterministic_validation == (
        "scripts/validate_feature_spec.py",
        "--strict",
    )
    assert pairs[0].generation_prompt == "generate"
    assert pairs[0].validation_prompt == "validate"


def test_error_unclosed_checks_files():
    text = """## Prompt 1: Optional inputs

```checks-files
docs/summary.txt
"""
    with pytest.raises(ParseError) as exc_info:
        parse_text(text)
    err = exc_info.value
    assert err.error_id == "E-UNCLOSED-CHECKS-FILES"
    assert "checks-files block" in err.message


def test_error_unclosed_deterministic_validation():
    text = """## Prompt 1: Needs deterministic validation

```deterministic-validation
scripts/validate_feature_spec.py
"""
    with pytest.raises(ParseError) as exc_info:
        parse_text(text)
    err = exc_info.value
    assert err.error_id == "E-UNCLOSED-DETERMINISTIC-VALIDATION"
    assert "deterministic-validation block" in err.message


def test_title_starting_with_digit_is_preserved():
    """Regression test: the heading regex must not eat leading digits from the title."""
    pairs = parse_text(_wrap("## Prompt: 3D rendering"))
    assert pairs[0].title == "3D rendering"


def test_empty_file_returns_empty_list():
    assert parse_text("") == []


def test_file_with_no_prompt_headings_returns_empty_list():
    assert parse_text("# Introduction\n\nSome prose.\n") == []


# ---------------------------------------------------------------------------
# Interactive marker and optional validator (skill-authoring harness)
# ---------------------------------------------------------------------------

def test_heading_without_interactive_marker_defaults_to_false():
    text = """## Prompt 1: Plain title

```
gen
```

```
val
```
"""
    pairs = parse_text(text)
    assert len(pairs) == 1
    assert pairs[0].title == "Plain title"
    assert pairs[0].interactive is False


def test_heading_with_interactive_marker_strips_and_sets_flag():
    text = """## Prompt 1: Author tdd skill [interactive]

```
mission body
```
"""
    pairs = parse_text(text)
    assert len(pairs) == 1
    assert pairs[0].title == "Author tdd skill"
    assert pairs[0].interactive is True
    assert pairs[0].generation_prompt == "mission body"
    assert pairs[0].validation_prompt == ""


def test_interactive_marker_is_case_insensitive():
    for marker in ("[interactive]", "[Interactive]", "[INTERACTIVE]"):
        text = f"""## Prompt 1: Title {marker}

```
gen
```
"""
        pairs = parse_text(text)
        assert pairs[0].interactive is True, f"failed for {marker}"
        assert pairs[0].title == "Title"


def test_brackets_earlier_in_title_are_not_interactive_marker():
    text = """## Prompt 1: Deal with [brackets] in title

```
gen
```

```
val
```
"""
    pairs = parse_text(text)
    assert pairs[0].title == "Deal with [brackets] in title"
    assert pairs[0].interactive is False


def test_brackets_earlier_with_interactive_at_end():
    text = """## Prompt 1: Deal with [brackets] in title [interactive]

```
gen
```
"""
    pairs = parse_text(text)
    assert pairs[0].title == "Deal with [brackets] in title"
    assert pairs[0].interactive is True


def test_single_fence_prompt_is_accepted_as_validator_less():
    text = """## Prompt 1: Mission only

```
this is the mission, no validator follows
```
"""
    pairs = parse_text(text)
    assert len(pairs) == 1
    assert pairs[0].generation_prompt == "this is the mission, no validator follows"
    assert pairs[0].validation_prompt == ""
    assert pairs[0].validation_line == 0


def test_single_fence_prompt_followed_by_another_heading():
    text = """## Prompt 1: First mission

```
mission one
```

## Prompt 2: Second mission

```
mission two
```
"""
    pairs = parse_text(text)
    assert len(pairs) == 2
    assert pairs[0].generation_prompt == "mission one"
    assert pairs[0].validation_prompt == ""
    assert pairs[1].generation_prompt == "mission two"
    assert pairs[1].validation_prompt == ""


def test_mixed_single_fence_and_double_fence_in_same_file():
    text = """## Prompt 1: With validator

```
gen
```

```
val
```

## Prompt 2: Without validator [interactive]

```
mission
```
"""
    pairs = parse_text(text)
    assert len(pairs) == 2
    assert pairs[0].validation_prompt == "val"
    assert pairs[0].interactive is False
    assert pairs[1].validation_prompt == ""
    assert pairs[1].interactive is True


def test_unclosed_generation_block_still_raises():
    text = """## Prompt 1: Broken

```
unclosed generation
"""
    try:
        parse_text(text)
    except ParseError as exc:
        assert exc.error_id == "E-UNCLOSED-GENERATION"
        return
    raise AssertionError("expected E-UNCLOSED-GENERATION")


def test_no_blocks_at_all_still_raises():
    text = """## Prompt 1: Empty

No code blocks here, just prose.
"""
    try:
        parse_text(text)
    except ParseError as exc:
        assert exc.error_id == "E-NO-BLOCKS"
        return
    raise AssertionError("expected E-NO-BLOCKS")
