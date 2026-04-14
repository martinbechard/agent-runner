"""Tests for [VARIANTS] fork point parsing."""
from prompt_runner.parser import (
    ForkPoint,
    PromptPair,
    VariantPrompt,
    ParseError,
    parse_text,
)
import pytest


def test_simple_fork_with_two_variants():
    text = """## Prompt 1: Setup

```
gen 1
```

```
val 1
```

## Prompt 2: Audit [VARIANTS]

### Variant A: Long list

```
gen 2a
```

```
val 2a
```

### Variant B: Checklist

```
gen 2b
```

```
val 2b
```

## Prompt 3: Final

```
gen 3
```

```
val 3
```
"""
    items = parse_text(text)
    assert len(items) == 3
    assert isinstance(items[0], PromptPair)
    assert items[0].title == "Setup"
    assert items[0].index == 1

    assert isinstance(items[1], ForkPoint)
    assert items[1].title == "Audit"
    assert items[1].index == 2
    assert len(items[1].variants) == 2
    assert items[1].variants[0].variant_name == "A"
    assert items[1].variants[0].variant_title == "Long list"
    assert len(items[1].variants[0].pairs) == 1
    assert items[1].variants[0].pairs[0].generation_prompt == "gen 2a"
    assert items[1].variants[0].pairs[0].validation_prompt == "val 2a"
    assert items[1].variants[1].variant_name == "B"
    assert items[1].variants[1].variant_title == "Checklist"

    assert isinstance(items[2], PromptPair)
    assert items[2].title == "Final"
    assert items[2].index == 3


def test_variant_with_single_fence_no_validator():
    text = """## Prompt 1: Test [VARIANTS]

### Variant A: With validator

```
gen
```

```
val
```

### Variant B: Without validator

```
gen only
```
"""
    items = parse_text(text)
    assert isinstance(items[0], ForkPoint)
    assert items[0].variants[1].pairs[0].validation_prompt == ""


def test_variant_with_multiple_pairs():
    text = """## Prompt 1: Multi [VARIANTS]

### Variant A: Two-pass

```
pass 1 gen
```

```
pass 1 val
```

```
pass 2 gen
```

```
pass 2 val
```

### Variant B: Single-pass

```
single gen
```

```
single val
```
"""
    items = parse_text(text)
    assert isinstance(items[0], ForkPoint)
    assert len(items[0].variants[0].pairs) == 2
    assert items[0].variants[0].pairs[0].generation_prompt == "pass 1 gen"
    assert items[0].variants[0].pairs[1].generation_prompt == "pass 2 gen"
    assert len(items[0].variants[1].pairs) == 1


def test_variants_and_interactive_on_same_heading_raises():
    text = """## Prompt 1: Bad [interactive] [VARIANTS]

### Variant A: X

```
gen
```
"""
    with pytest.raises(ParseError) as exc_info:
        parse_text(text)
    assert "interactive" in str(exc_info.value).lower()
    assert "variants" in str(exc_info.value).lower()


def test_variants_with_no_subsections_raises():
    text = """## Prompt 1: Empty [VARIANTS]

No variant subsections here.

## Prompt 2: Next

```
gen
```

```
val
```
"""
    with pytest.raises(ParseError) as exc_info:
        parse_text(text)
    assert "variant" in str(exc_info.value).lower()


def test_variant_name_extraction():
    text = """## Prompt 1: Test [VARIANTS]

### Variant Alpha: First approach

```
gen
```

### Variant Beta-2: Second approach

```
gen
```
"""
    items = parse_text(text)
    assert items[0].variants[0].variant_name == "Alpha"
    assert items[0].variants[0].variant_title == "First approach"
    assert items[0].variants[1].variant_name == "Beta-2"
    assert items[0].variants[1].variant_title == "Second approach"


def test_file_with_no_variants_unchanged():
    """Existing files without [VARIANTS] parse identically."""
    text = """## Prompt 1: Normal

```
gen
```

```
val
```

## Prompt 2: Also normal

```
gen 2
```

```
val 2
```
"""
    items = parse_text(text)
    assert len(items) == 2
    assert all(isinstance(i, PromptPair) for i in items)


def test_model_override_on_prompt_heading():
    text = """## Prompt 1: Test [MODEL:claude-sonnet-4-6]

```
gen
```

```
val
```
"""
    items = parse_text(text)
    assert items[0].model_override == "claude-sonnet-4-6"
    assert items[0].title == "Test"


def test_effort_override_on_prompt_heading():
    text = """## Prompt 1: Test [EFFORT:low]

```
gen
```

```
val
```
"""
    items = parse_text(text)
    assert items[0].effort_override == "low"
    assert items[0].title == "Test"


def test_both_model_and_effort():
    text = """## Prompt 1: Test [MODEL:claude-haiku-4-5-20251001] [EFFORT:medium]

```
gen
```

```
val
```
"""
    items = parse_text(text)
    assert items[0].model_override == "claude-haiku-4-5-20251001"
    assert items[0].effort_override == "medium"
    assert items[0].title == "Test"


def test_model_on_variant_heading():
    text = """## Prompt 1: Audit [VARIANTS]

### Variant A: Default

```
gen
```

### Variant B: Sonnet [MODEL:claude-sonnet-4-6]

```
gen
```
"""
    items = parse_text(text)
    fork = items[0]
    assert fork.variants[0].pairs[0].model_override is None
    assert fork.variants[1].pairs[0].model_override == "claude-sonnet-4-6"


def test_effort_on_variant_heading():
    text = """## Prompt 1: Audit [VARIANTS]

### Variant A: Default

```
gen
```

### Variant B: Low effort [EFFORT:low]

```
gen
```
"""
    items = parse_text(text)
    fork = items[0]
    assert fork.variants[0].pairs[0].effort_override is None
    assert fork.variants[1].pairs[0].effort_override == "low"


def test_model_and_effort_not_in_title():
    text = """## Prompt 1: My [MODEL:x] test [EFFORT:low] here

```
gen
```

```
val
```
"""
    items = parse_text(text)
    assert items[0].model_override == "x"
    assert items[0].effort_override == "low"
    assert items[0].title == "My test here"


def test_no_directives_unchanged():
    text = """## Prompt 1: Plain title

```
gen
```

```
val
```
"""
    items = parse_text(text)
    assert items[0].model_override is None
    assert items[0].effort_override is None


def test_mid_variant_model_switch():
    """[MODEL:xxx] between fences overrides model for subsequent pairs."""
    text = """## Prompt 1: Pipeline [VARIANTS]

### Variant Optimized: Split pipeline [MODEL:claude-haiku-4-5-20251001]

```
extraction prompt
```

[MODEL:claude-opus-4-6]

```
judgment prompt
```

```
judgment validator
```
"""
    items = parse_text(text)
    fork = items[0]
    assert isinstance(fork, ForkPoint)
    pairs = fork.variants[0].pairs
    assert len(pairs) == 2
    # First pair: inherits Haiku from heading (no validator)
    assert pairs[0].model_override == "claude-haiku-4-5-20251001"
    assert pairs[0].generation_prompt == "extraction prompt"
    assert pairs[0].validation_prompt == ""
    # Second pair: switched to Opus via mid-variant directive
    assert pairs[1].model_override == "claude-opus-4-6"
    assert pairs[1].generation_prompt == "judgment prompt"
    assert pairs[1].validation_prompt == "judgment validator"


def test_mid_variant_effort_switch():
    """[EFFORT:xxx] between fences overrides effort for subsequent pairs."""
    text = """## Prompt 1: Test [VARIANTS]

### Variant A: Multi-effort [EFFORT:low]

```
pass 1
```

```
val 1
```

[EFFORT:high]

```
pass 2
```

```
val 2
```
"""
    items = parse_text(text)
    pairs = items[0].variants[0].pairs
    assert len(pairs) == 2
    assert pairs[0].effort_override == "low"
    assert pairs[1].effort_override == "high"


def test_mid_variant_both_model_and_effort():
    """Both [MODEL:xxx] and [EFFORT:xxx] on same standalone line."""
    text = """## Prompt 1: Test [VARIANTS]

### Variant A: Split [MODEL:claude-haiku-4-5-20251001]

```
extraction
```

[MODEL:claude-opus-4-6] [EFFORT:high]

```
judgment
```

```
validator
```
"""
    items = parse_text(text)
    pairs = items[0].variants[0].pairs
    assert pairs[0].model_override == "claude-haiku-4-5-20251001"
    assert pairs[0].effort_override is None
    assert pairs[1].model_override == "claude-opus-4-6"
    assert pairs[1].effort_override == "high"


def test_mid_variant_directive_does_not_affect_other_variants():
    """Mid-variant directives only affect the variant they appear in."""
    text = """## Prompt 1: Test [VARIANTS]

### Variant A: Haiku then Opus [MODEL:claude-haiku-4-5-20251001]

```
extraction
```

[MODEL:claude-opus-4-6]

```
judgment
```

```
validator
```

### Variant B: Default model

```
single gen
```

```
single val
```
"""
    items = parse_text(text)
    fork = items[0]
    # Variant A: two pairs, different models
    assert fork.variants[0].pairs[0].model_override == "claude-haiku-4-5-20251001"
    assert fork.variants[0].pairs[1].model_override == "claude-opus-4-6"
    # Variant B: no model override
    assert fork.variants[1].pairs[0].model_override is None
