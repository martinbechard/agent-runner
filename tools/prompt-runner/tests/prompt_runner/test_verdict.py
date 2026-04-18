from prompt_runner.verdict import Verdict, VerdictParseError, parse_verdict
import pytest


def test_parses_pass():
    assert parse_verdict("reasoning text\n\nVERDICT: pass") == Verdict.PASS


def test_parses_revise():
    assert parse_verdict("reasoning\n\nVERDICT: revise") == Verdict.REVISE


def test_parses_escalate():
    assert parse_verdict("reasoning\n\nVERDICT: escalate") == Verdict.ESCALATE


def test_case_insensitive_keyword():
    assert parse_verdict("VERDICT: Pass") == Verdict.PASS


def test_case_insensitive_label():
    assert parse_verdict("Verdict: revise") == Verdict.REVISE


def test_takes_last_match():
    text = (
        "early on I thought maybe VERDICT: revise\n"
        "but after more thought\n"
        "VERDICT: pass"
    )
    assert parse_verdict(text) == Verdict.PASS


def test_raises_on_missing():
    with pytest.raises(VerdictParseError) as exc_info:
        parse_verdict("this has no verdict at all")
    assert "no VERDICT line" in str(exc_info.value)


def test_raises_on_unknown_value():
    with pytest.raises(VerdictParseError):
        parse_verdict("VERDICT: maybe")


def test_allows_trailing_whitespace():
    assert parse_verdict("VERDICT: pass   ") == Verdict.PASS


def test_bare_keyword_without_verdict_prefix_does_not_match():
    """A bare word 'pass' without the VERDICT: prefix must NOT match."""
    with pytest.raises(VerdictParseError):
        parse_verdict("just the word pass alone")


def test_verdict_line_followed_by_more_content():
    """A VERDICT line in the middle of the response (not the last line) still parses."""
    text = (
        "preamble\n"
        "VERDICT: pass\n"
        "trailing thank-you note that should be ignored"
    )
    assert parse_verdict(text) == Verdict.PASS
