"""Meta-tests that keep the README in sync with the code."""
from __future__ import annotations

from pathlib import Path

from prompt_runner.parser import ERROR_IDS, parse_file

README_PATH = Path(__file__).parent.parent.parent.parent / "src" / "cli" / "prompt_runner" / "README.md"
FIXTURES = Path(__file__).parent / "fixtures"


def test_readme_exists():
    assert README_PATH.exists(), f"README not found at {README_PATH}"


def test_readme_example_parses():
    pairs = parse_file(FIXTURES / "readme-example.md")
    assert len(pairs) == 2
    assert pairs[0].title == "Greeting"
    assert pairs[1].title == "Sign-off"


def test_error_ids_match_readme():
    text = README_PATH.read_text(encoding="utf-8")
    for error_id in ERROR_IDS:
        assert error_id in text, f"README is missing error ID {error_id}"


def test_readme_is_short_enough():
    text = README_PATH.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    assert line_count <= 400, f"README has {line_count} lines, cap is 400"
