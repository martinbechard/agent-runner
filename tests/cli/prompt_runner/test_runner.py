from pathlib import Path

import pytest

from prompt_runner.parser import PromptPair
from prompt_runner.runner import (
    VERDICT_INSTRUCTION,
    ANTI_ANCHORING_CLAUSE,
    REVISION_GENERATOR_PREAMBLE,
    build_initial_generator_message,
    build_initial_judge_message,
    build_revision_generator_message,
    build_revision_judge_message,
)


def _pair(index: int, title: str, gen: str = "GEN", val: str = "VAL") -> PromptPair:
    return PromptPair(
        index=index,
        title=title,
        generation_prompt=gen,
        validation_prompt=val,
        heading_line=1,
        generation_line=2,
        validation_line=5,
    )


def test_initial_generator_message_with_no_priors_is_verbatim():
    p = _pair(1, "First", gen="the body")
    assert build_initial_generator_message(p, []) == "the body"


def test_initial_generator_message_injects_priors():
    p = _pair(2, "Second", gen="the task body")
    msg = build_initial_generator_message(
        p,
        [("First", "ARTIFACT-ONE"), ("A", "ARTIFACT-A")],
    )
    assert "ARTIFACT-ONE" in msg
    assert "ARTIFACT-A" in msg
    assert "# Prior approved artifacts" in msg
    assert "# Your task" in msg
    assert "the task body" in msg


def test_initial_judge_message_includes_verdict_instruction():
    p = _pair(1, "First", val="please evaluate")
    msg = build_initial_judge_message(p, "ARTIFACT")
    assert "please evaluate" in msg
    assert "ARTIFACT" in msg
    assert VERDICT_INSTRUCTION in msg


def test_revision_generator_message_contains_preamble_and_feedback():
    msg = build_revision_generator_message("some feedback")
    assert REVISION_GENERATOR_PREAMBLE in msg
    assert "some feedback" in msg


def test_revision_judge_message_contains_anti_anchoring_and_artifact():
    msg = build_revision_judge_message("NEW-ARTIFACT")
    assert ANTI_ANCHORING_CLAUSE in msg
    assert "NEW-ARTIFACT" in msg
    assert VERDICT_INSTRUCTION in msg
