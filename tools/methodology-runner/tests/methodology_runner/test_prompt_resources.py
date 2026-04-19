"""Ensure bundled runtime prompt resources stay in sync with docs/prompt copies."""
from __future__ import annotations

from pathlib import Path


DOCS_PROMPTS = (
    "PR-023-ph001-feature-specification.md",
    "PR-024-ph002-architecture.md",
    "PR-025-ph000-requirements-inventory.md",
    "PR-026-ph003-solution-design.md",
    "PR-027-ph004-interface-contracts.md",
    "PR-028-ph005-intelligent-simulations.md",
    "PR-029-ph006-incremental-implementation.md",
    "PR-030-ph007-verification-sweep.md",
)


def test_bundled_prompt_resources_match_docs_prompts() -> None:
    tool_root = Path(__file__).resolve().parents[2]
    docs_dir = tool_root / "docs" / "prompts"
    bundled_dir = tool_root / "src" / "methodology_runner" / "prompts"

    for name in DOCS_PROMPTS:
        docs_text = (docs_dir / name).read_text(encoding="utf-8")
        bundled_text = (bundled_dir / name).read_text(encoding="utf-8")
        assert bundled_text == docs_text, name
