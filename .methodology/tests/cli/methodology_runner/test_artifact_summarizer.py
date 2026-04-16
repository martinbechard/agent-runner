"""Tests for artifact summarization with caching."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from methodology_runner.artifact_summarizer import (
    ArtifactSummaryProvider,
    SummarizerResult,
)
from methodology_runner.constants import ARTIFACT_FULL_CONTENT_THRESHOLD


@dataclass
class _StubClient:
    responses: list[str]
    received: list[str] = field(default_factory=list)
    _idx: int = 0

    def call(self, call: Any):  # matches ClaudeClient protocol minimally
        self.received.append(call.prompt)
        text = self.responses[self._idx]
        self._idx += 1
        from prompt_runner.claude_client import ClaudeResponse
        return ClaudeResponse(stdout=text, stderr="", returncode=0)


def _small_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("small artifact body", encoding="utf-8")


def _large_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * (ARTIFACT_FULL_CONTENT_THRESHOLD + 10), encoding="utf-8")


def test_small_artifact_returned_in_full_no_claude_call(tmp_path: Path):
    art = tmp_path / "small.md"
    _small_file(art)
    client = _StubClient(responses=[])
    provider = ArtifactSummaryProvider(
        cache_dir=tmp_path / ".cache",
        claude_client=client,
    )
    result = provider.get(art)
    assert result.full_content == "small artifact body"
    assert result.summary is None
    assert client.received == []


def test_large_artifact_triggers_summary_call(tmp_path: Path):
    art = tmp_path / "big.md"
    _large_file(art)
    client = _StubClient(responses=["A concise summary of the file."])
    provider = ArtifactSummaryProvider(
        cache_dir=tmp_path / ".cache",
        claude_client=client,
    )
    result = provider.get(art)
    assert result.full_content is None
    assert result.summary == "A concise summary of the file."
    assert len(client.received) == 1


def test_cached_summary_returned_without_second_call(tmp_path: Path):
    art = tmp_path / "big.md"
    _large_file(art)
    client = _StubClient(responses=["first summary"])
    provider = ArtifactSummaryProvider(
        cache_dir=tmp_path / ".cache",
        claude_client=client,
    )
    provider.get(art)
    # Second provider reading same cache dir: no new client calls.
    client2 = _StubClient(responses=[])
    provider2 = ArtifactSummaryProvider(
        cache_dir=tmp_path / ".cache",
        claude_client=client2,
    )
    result = provider2.get(art)
    assert result.summary == "first summary"
    assert client2.received == []


def test_cache_invalidates_when_artifact_changes(tmp_path: Path):
    art = tmp_path / "big.md"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text("x" * (ARTIFACT_FULL_CONTENT_THRESHOLD + 10), encoding="utf-8")
    client = _StubClient(responses=["old", "new"])
    provider = ArtifactSummaryProvider(
        cache_dir=tmp_path / ".cache",
        claude_client=client,
    )
    first = provider.get(art)
    assert first.summary == "old"

    # Rewrite the file with different content but same size
    art.write_text("y" * (ARTIFACT_FULL_CONTENT_THRESHOLD + 10), encoding="utf-8")
    second = provider.get(art)
    assert second.summary == "new"
    assert len(client.received) == 2


def test_get_returns_error_when_file_missing(tmp_path: Path):
    provider = ArtifactSummaryProvider(
        cache_dir=tmp_path / ".cache",
        claude_client=_StubClient(responses=[]),
    )
    try:
        provider.get(tmp_path / "missing.md")
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")
