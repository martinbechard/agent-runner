"""Tests for [VARIANTS] fork point parsing."""

import pytest

from prompt_runner.parser import ForkPoint, ParseError, PromptPair, parse_text


def test_simple_fork_with_two_variants():
    text = """## Prompt 1: Setup

### Generation Prompt

gen 1

### Validation Prompt

val 1

## Prompt 2: Audit [VARIANTS]

### Variant A: Long list

#### Generation Prompt

gen 2a

#### Validation Prompt

val 2a

### Variant B: Checklist

#### Generation Prompt

gen 2b

#### Validation Prompt

val 2b

## Prompt 3: Final

### Generation Prompt

gen 3

### Validation Prompt

val 3
"""
    items = parse_text(text)
    assert len(items) == 3
    assert isinstance(items[0], PromptPair)
    assert isinstance(items[1], ForkPoint)
    assert isinstance(items[2], PromptPair)
    assert items[1].title == "Audit"
    assert items[1].variants[0].variant_name == "A"
    assert items[1].variants[1].variant_title == "Checklist"
    assert items[1].variants[0].pairs[0].generation_prompt == "gen 2a"


def test_variant_with_single_generation_section_no_validator():
    text = """## Prompt 1: Test [VARIANTS]

### Variant A: With validator

#### Generation Prompt

gen

#### Validation Prompt

val

### Variant B: Without validator

#### Generation Prompt

gen only
"""
    items = parse_text(text)
    assert isinstance(items[0], ForkPoint)
    assert items[0].variants[1].pairs[0].validation_prompt == ""


def test_variant_with_multiple_pairs():
    text = """## Prompt 1: Multi [VARIANTS]

### Variant A: Two-pass

#### Generation Prompt

pass 1 gen

#### Validation Prompt

pass 1 val

#### Generation Prompt

pass 2 gen

#### Validation Prompt

pass 2 val

### Variant B: Single-pass

#### Generation Prompt

single gen

#### Validation Prompt

single val
"""
    items = parse_text(text)
    fork = items[0]
    assert isinstance(fork, ForkPoint)
    assert len(fork.variants[0].pairs) == 2
    assert fork.variants[0].pairs[1].generation_prompt == "pass 2 gen"


def test_variants_and_interactive_on_same_heading_raises():
    text = """## Prompt 1: Bad [interactive] [VARIANTS]

### Variant A: X

#### Generation Prompt

gen
"""
    with pytest.raises(ParseError) as exc_info:
        parse_text(text)
    assert exc_info.value.error_id == "E-BAD-SECTION-ORDER"


def test_variants_with_no_subsections_raises():
    text = """## Prompt 1: Empty [VARIANTS]

No variant subsections here.
"""
    with pytest.raises(ParseError) as exc_info:
        parse_text(text)
    assert exc_info.value.error_id == "E-NO-VARIANTS"


def test_variant_name_extraction():
    text = """## Prompt 1: Test [VARIANTS]

### Variant Alpha: First approach

#### Generation Prompt

gen

### Variant Beta-2: Second approach

#### Generation Prompt

gen
"""
    items = parse_text(text)
    assert items[0].variants[0].variant_name == "Alpha"
    assert items[0].variants[1].variant_name == "Beta-2"


def test_model_and_effort_on_variant_heading():
    text = """## Prompt 1: Audit [VARIANTS]

### Variant A: Sonnet [MODEL:claude-sonnet-4-6] [EFFORT:low]

#### Generation Prompt

gen
"""
    items = parse_text(text)
    pair = items[0].variants[0].pairs[0]
    assert pair.model_override == "claude-sonnet-4-6"
    assert pair.effort_override == "low"


def test_mid_variant_model_switch():
    text = """## Prompt 1: Pipeline [VARIANTS]

### Variant Optimized: Split pipeline [MODEL:claude-haiku-4-5-20251001]

#### Generation Prompt

extraction prompt

[MODEL:claude-opus-4-6]

#### Generation Prompt

judgment prompt

#### Validation Prompt

judgment validator
"""
    items = parse_text(text)
    pairs = items[0].variants[0].pairs
    assert len(pairs) == 2
    assert pairs[0].model_override == "claude-haiku-4-5-20251001"
    assert pairs[0].validation_prompt == ""
    assert pairs[1].model_override == "claude-opus-4-6"


def test_mid_variant_directive_does_not_affect_other_variants():
    text = """## Prompt 1: Test [VARIANTS]

### Variant A: Haiku then Opus [MODEL:claude-haiku-4-5-20251001]

#### Generation Prompt

extraction

[MODEL:claude-opus-4-6]

#### Generation Prompt

judgment

#### Validation Prompt

validator

### Variant B: Default model

#### Generation Prompt

single gen

#### Validation Prompt

single val
"""
    items = parse_text(text)
    fork = items[0]
    assert fork.variants[0].pairs[0].model_override == "claude-haiku-4-5-20251001"
    assert fork.variants[0].pairs[1].model_override == "claude-opus-4-6"
    assert fork.variants[1].pairs[0].model_override is None
