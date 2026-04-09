"""Size-threshold-gated summarization of prior phase artifacts.

The Skill-Selector receives every prior phase artifact as input.
Small artifacts (under ``ARTIFACT_FULL_CONTENT_THRESHOLD`` bytes) are
passed in full.  Larger artifacts are replaced by a short
AI-generated summary, computed once and cached on disk so later
selector invocations reuse it.

Cache layout::

    <workspace>/.methodology-runner/artifact-summaries/
        <sha256-of-path>-<sha256-of-content>.txt

The cache key includes both the absolute path and a content hash,
so a file that is rewritten with new content gets re-summarized
but a file that is merely touched does not.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import ARTIFACT_FULL_CONTENT_THRESHOLD

if TYPE_CHECKING:
    from prompt_runner.claude_client import ClaudeClient, ClaudeCall


@dataclass(frozen=True)
class SummarizerResult:
    """Outcome of a single ``provider.get(path)`` call.

    Exactly one of ``full_content`` or ``summary`` is non-None.
    """

    path: Path
    size_bytes: int
    full_content: str | None
    summary: str | None


SUMMARY_PROMPT_TEMPLATE = """\
You are summarizing a prior-phase artifact from an AI-driven development
methodology pipeline.  A downstream Skill-Selector agent will read your
summary to decide which specialized knowledge skills the next phase
needs.

Produce a concise 1-2 paragraph summary focused on:

- What kind of artifact this is and which phase produced it.
- The key technical decisions, components, frameworks, or types declared.
- Any implications for what skills the next phase will need.

Do NOT reproduce the full content.  Do NOT list every element.  Keep
the summary under 500 words.

---

# Source artifact

Path: {path}
Size: {size_bytes} bytes

---

# Content

{content}
"""


class ArtifactSummaryProvider:
    """Returns either full content (small files) or a cached summary (large).

    Parameters
    ----------
    cache_dir:
        Directory where summaries are persisted.  Created on demand.
    claude_client:
        Injected Claude client used for summarization calls.
    model:
        Optional model override forwarded to claude.
    threshold:
        Size (in bytes) above which summaries are produced.  Defaults
        to :data:`ARTIFACT_FULL_CONTENT_THRESHOLD`.
    """

    def __init__(
        self,
        *,
        cache_dir: Path,
        claude_client: "ClaudeClient",
        model: str | None = None,
        threshold: int = ARTIFACT_FULL_CONTENT_THRESHOLD,
    ) -> None:
        self._cache_dir = cache_dir
        self._claude_client = claude_client
        self._model = model
        self._threshold = threshold

    def get(self, path: Path) -> SummarizerResult:
        """Return the full content or a cached summary for *path*.

        Raises :class:`FileNotFoundError` if the artifact does not
        exist.
        """
        if not path.exists():
            raise FileNotFoundError(f"artifact not found: {path}")

        content = path.read_text(encoding="utf-8")
        size = len(content.encode("utf-8"))

        if size <= self._threshold:
            return SummarizerResult(
                path=path,
                size_bytes=size,
                full_content=content,
                summary=None,
            )

        cache_path = self._cache_path_for(path, content)
        if cache_path.exists():
            cached = cache_path.read_text(encoding="utf-8")
            return SummarizerResult(
                path=path,
                size_bytes=size,
                full_content=None,
                summary=cached,
            )

        summary = self._call_claude_for_summary(path, content, size)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(summary, encoding="utf-8")
        return SummarizerResult(
            path=path,
            size_bytes=size,
            full_content=None,
            summary=summary,
        )

    def _cache_path_for(self, path: Path, content: str) -> Path:
        path_hash = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return self._cache_dir / f"{path_hash}-{content_hash}.txt"

    def _call_claude_for_summary(
        self, path: Path, content: str, size_bytes: int,
    ) -> str:
        from prompt_runner.claude_client import ClaudeCall

        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            path=path,
            size_bytes=size_bytes,
            content=content,
        )
        logs_dir = self._cache_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stem = f"summarize-{uuid.uuid4().hex[:8]}"
        call = ClaudeCall(
            prompt=prompt,
            session_id=str(uuid.uuid4()),
            new_session=True,
            model=self._model,
            stdout_log_path=logs_dir / f"{stem}.stdout.log",
            stderr_log_path=logs_dir / f"{stem}.stderr.log",
            stream_header=f"-- artifact summary / {path.name} --",
            workspace_dir=path.parent,
        )
        response = self._claude_client.call(call)
        return response.stdout.strip()
