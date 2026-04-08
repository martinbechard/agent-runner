"""Pipeline orchestration for prompt-runner.

See docs/design/components/CD-001-prompt-runner.md sections 9 and 11.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from prompt_runner.claude_client import (
    ClaudeCall,
    ClaudeClient,
    ClaudeInvocationError,
    ClaudeResponse,
)
from prompt_runner.parser import PromptPair
from prompt_runner.verdict import Verdict, VerdictParseError, parse_verdict


MAX_ITERATIONS_DEFAULT = 3
VERDICT_INSTRUCTION = (
    "End your response with a single line of the exact form: "
    "VERDICT: pass, VERDICT: revise, or VERDICT: escalate. "
    "Do not write anything after that line."
)
ANTI_ANCHORING_CLAUSE = (
    "Below is the revised artifact. Re-evaluate every checklist item against "
    "this current version. Items you previously failed may now pass, and items "
    "you previously passed may now fail if the revision broke them. Do not "
    "defer to your prior verdict."
)
REVISION_GENERATOR_PREAMBLE = (
    "The judge evaluated your previous artifact and returned the feedback "
    "below. Produce a revised artifact that addresses every fail or partial "
    "item. Do not drop content that already passed. Your response must be the "
    "complete revised artifact, with no commentary before or after it."
)
_HORIZONTAL_RULE = "\n\n---\n\n"


@dataclass(frozen=True)
class RunConfig:
    max_iterations: int = MAX_ITERATIONS_DEFAULT
    model: str | None = None
    only: int | None = None
    dry_run: bool = False


@dataclass(frozen=True)
class IterationResult:
    iteration: int
    generator_output: str
    judge_output: str
    verdict: Verdict


@dataclass(frozen=True)
class PromptResult:
    pair: PromptPair
    iterations: list[IterationResult]
    final_verdict: Verdict
    final_artifact: str


@dataclass(frozen=True)
class PipelineResult:
    prompt_results: list[PromptResult]
    halted_early: bool
    halt_reason: str | None


def build_initial_generator_message(
    pair: PromptPair, prior_artifacts: list[tuple[str, str]]
) -> str:
    if not prior_artifacts:
        return pair.generation_prompt
    prior_blocks = "\n\n".join(
        f"## {title}\n\n{body}" for title, body in prior_artifacts
    )
    return (
        f"# Prior approved artifacts\n\n{prior_blocks}"
        f"{_HORIZONTAL_RULE}"
        f"# Your task\n\n{pair.generation_prompt}"
    )


def build_initial_judge_message(pair: PromptPair, artifact: str) -> str:
    return (
        f"{pair.validation_prompt}"
        f"{_HORIZONTAL_RULE}"
        f"# Artifact to evaluate\n\n{artifact}"
        f"{_HORIZONTAL_RULE}"
        f"{VERDICT_INSTRUCTION}"
    )


def build_revision_generator_message(judge_output: str) -> str:
    return f"{REVISION_GENERATOR_PREAMBLE}\n\n# Judge feedback\n\n{judge_output}"


def build_revision_judge_message(new_artifact: str) -> str:
    return (
        f"{ANTI_ANCHORING_CLAUSE}\n\n"
        f"# Revised artifact\n\n{new_artifact}"
        f"{_HORIZONTAL_RULE}"
        f"{VERDICT_INSTRUCTION}"
    )


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    lowered = title.lower()
    slug = _SLUG_STRIP.sub("-", lowered).strip("-")
    return slug or "untitled"


def _prompt_dir_name(pair: PromptPair) -> str:
    return f"prompt-{pair.index:02d}-{_slugify(pair.title)}"
