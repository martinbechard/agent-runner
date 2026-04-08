"""Verdict enum and judge-output parser for prompt-runner."""
from __future__ import annotations

import re
from enum import Enum


class Verdict(Enum):
    PASS = "pass"
    REVISE = "revise"
    ESCALATE = "escalate"


SNIPPET_LENGTH = 500


class VerdictParseError(ValueError):
    """Raised when a judge response contains no recognisable VERDICT line
    or when the verdict keyword is not one of the Verdict enum values.
    """


_VERDICT_LINE = re.compile(
    r"^VERDICT:\s*(pass|revise|escalate)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def parse_verdict(judge_output: str) -> Verdict:
    """Extract a Verdict from free-text judge output.

    Rules:
    - Last match wins (the judge may reference the instruction mid-response).
    - Match is case-insensitive.
    - Zero matches raises VerdictParseError with the first SNIPPET_LENGTH chars for debugging.
    - A matched keyword that is not a Verdict member also raises VerdictParseError
      (this only triggers if the regex is ever widened).
    """
    matches = _VERDICT_LINE.findall(judge_output)
    if not matches:
        snippet = judge_output[:SNIPPET_LENGTH]
        raise VerdictParseError(
            f"no VERDICT line found in judge output. "
            f"First {SNIPPET_LENGTH} chars: {snippet!r}"
        )
    keyword = matches[-1].lower()
    try:
        return Verdict(keyword)
    except ValueError:
        raise VerdictParseError(
            f"unrecognised verdict keyword: {keyword!r}"
        ) from None
