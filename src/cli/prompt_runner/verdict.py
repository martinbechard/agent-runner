"""Verdict enum and judge-output parser for prompt-runner."""
from __future__ import annotations

import re
from enum import Enum


class Verdict(Enum):
    PASS = "pass"
    REVISE = "revise"
    ESCALATE = "escalate"


class VerdictParseError(Exception):
    """Raised when a judge response contains no recognisable VERDICT line."""


_VERDICT_LINE = re.compile(
    r"^VERDICT:\s*(pass|revise|escalate)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def parse_verdict(judge_output: str) -> Verdict:
    """Extract a Verdict from free-text judge output.

    Rules:
    - Last match wins (the judge may reference the instruction mid-response).
    - Match is case-insensitive.
    - Zero matches raises VerdictParseError with the first 500 chars for debugging.
    """
    matches = _VERDICT_LINE.findall(judge_output)
    if not matches:
        snippet = judge_output[:500]
        raise VerdictParseError(
            f"no VERDICT line found in judge output. First 500 chars: {snippet!r}"
        )
    return Verdict(matches[-1].lower())
