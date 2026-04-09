"""Pipeline orchestration for prompt-runner.

See docs/design/components/CD-001-prompt-runner.md sections 9 and 11.
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
PROJECT_ORGANISER_INSTRUCTION = (
    "If this task involves producing files on disk: before writing any new "
    "file, invoke the `project-organiser` sub-agent via the Agent tool "
    "(subagent_type=project-organiser) with the file's content or a "
    "description of its content. Use the `path` it returns as the exact "
    "file path for your Write tool call. Do not guess paths from the "
    "project layout. If this task is purely text output (no files), ignore "
    "this instruction."
)
_HORIZONTAL_RULE = "\n\n---\n\n"

# Stable namespace for deterministic session-ID UUID generation.
# The Claude CLI requires --session-id to be a valid UUID, so we map our
# logical session labels (gen-prompt-N-<run-id>) through uuid5 to get a
# deterministic UUID — deterministic so that iteration 2's --resume uses
# the same UUID as iteration 1's --session-id.
_SESSION_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-0000000000a1")


def _session_id(logical_label: str) -> str:
    """Derive a deterministic UUID session ID from a logical label.

    The UUID is stable across iterations of the same prompt/role, which is
    required so that --resume picks up the session that --session-id created.
    The logical label is preserved only for the ClaudeCall.stream_header,
    which is human-readable and independent of the wire-format session ID.
    """
    return str(uuid.uuid5(_SESSION_NAMESPACE, logical_label))


# Number of stderr lines to include in R-CLAUDE-FAILED halt reasons.
STDERR_TAIL_LINES = 20


def _tail_lines(text: str, n: int) -> str:
    """Return the last n lines of text, indented by two spaces, or a placeholder."""
    if not text:
        return "  (empty)"
    lines = text.splitlines()
    tail = lines[-n:] if len(lines) > n else lines
    return "\n".join(f"  {line}" for line in tail)


def _format_wall_time(started_at: datetime, finished_at: datetime) -> str:
    """Format elapsed wall time as HH:MM:SS."""
    elapsed: timedelta = finished_at - started_at
    total_seconds = int(elapsed.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


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
    created_files: list[Path] = field(default_factory=list)
    """Relative paths of files added or modified by this prompt's generator,
    relative to the workspace directory. Empty for text-only prompts. Passed
    to subsequent prompts' generator messages as part of the file manifest so
    they know what the prior prompt produced on disk."""


@dataclass(frozen=True)
class PipelineResult:
    prompt_results: list[PromptResult]
    halted_early: bool
    halt_reason: str | None


@dataclass(frozen=True)
class PriorArtifact:
    """One prior-prompt result, injected as context into subsequent prompts."""

    title: str
    text_body: str
    files: list[Path]
    """Relative paths (relative to workspace_dir) of files created by the
    prior prompt. The current prompt's generator can Read them directly
    since it shares the same workspace."""


def _format_file_manifest(files: list[Path]) -> str:
    if not files:
        return "(no files created)"
    return "\n".join(f"- {f}" for f in files)


def build_initial_generator_message(
    pair: PromptPair, prior_artifacts: list[PriorArtifact]
) -> str:
    sections: list[str] = []

    if prior_artifacts:
        prior_blocks: list[str] = []
        for p in prior_artifacts:
            prior_blocks.append(
                f"## {p.title}\n\n"
                f"### Text response\n\n{p.text_body}\n\n"
                f"### Files created (relative to current working directory)\n\n"
                f"{_format_file_manifest(p.files)}"
            )
        sections.append("# Prior approved artifacts\n\n" + "\n\n".join(prior_blocks))
        sections.append(
            "The files listed above exist on disk in the current working "
            "directory (your cwd is the project root). You can Read them "
            "with the Read tool if you need to import from them, reference "
            "their contents, or extend them."
        )

    sections.append(f"# Your task\n\n{pair.generation_prompt}")
    sections.append(PROJECT_ORGANISER_INSTRUCTION)

    return _HORIZONTAL_RULE.join(sections)


def build_initial_judge_message(pair: PromptPair, artifact: str) -> str:
    return (
        f"{pair.validation_prompt}"
        f"{_HORIZONTAL_RULE}"
        f"# Artifact to evaluate (generator's text response)\n\n{artifact}"
        f"{_HORIZONTAL_RULE}"
        f"The generator may also have created files on disk. Your current "
        f"working directory is the project root. You can Read any file, run "
        f"Bash commands (python -m py_compile, mypy, pytest, etc.), and Glob "
        f"for files the generator may have produced. Use tool-based "
        f"verification in addition to reading the text response."
        f"{_HORIZONTAL_RULE}"
        f"{VERDICT_INSTRUCTION}"
    )


def build_revision_generator_message(judge_output: str) -> str:
    return (
        f"{REVISION_GENERATOR_PREAMBLE}\n\n"
        f"# Judge feedback\n\n{judge_output}"
        f"{_HORIZONTAL_RULE}"
        f"{PROJECT_ORGANISER_INSTRUCTION}"
    )


def build_revision_judge_message(new_artifact: str) -> str:
    return (
        f"{ANTI_ANCHORING_CLAUSE}\n\n"
        f"# Revised artifact (generator's text response)\n\n{new_artifact}"
        f"{_HORIZONTAL_RULE}"
        f"The generator may have created or modified files on disk. Re-check "
        f"them via Read / Bash / Glob as needed, alongside re-reading the "
        f"text response."
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


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# Directory names that are always skipped when snapshotting or diffing the
# workspace. These are either the tool's own outputs (runs), dependency caches
# (.venv, node_modules), Python bytecode caches (__pycache__, .pytest_cache),
# version-control state (.git), or build artifacts.
_SNAPSHOT_SKIP_DIR_NAMES: frozenset[str] = frozenset({
    ".git",
    "runs",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
})


def _is_snapshot_excluded(rel_path: Path) -> bool:
    """Return True if this relative path should be excluded from snapshot/diff."""
    for part in rel_path.parts:
        if part in _SNAPSHOT_SKIP_DIR_NAMES:
            return True
        if part.endswith(".egg-info"):
            return True
        if part == ".DS_Store":
            return True
    return False


def _iter_workspace_files(workspace_dir: Path):
    """Yield (relative_path, mtime_ns) for every non-excluded file in the workspace."""
    for src in workspace_dir.rglob("*"):
        if src.is_symlink() or not src.is_file():
            continue
        rel = src.relative_to(workspace_dir)
        if _is_snapshot_excluded(rel):
            continue
        try:
            yield rel, src.stat().st_mtime_ns
        except FileNotFoundError:
            # File vanished between glob and stat — skip.
            continue


def _snapshot_workspace(workspace_dir: Path, dest_dir: Path) -> None:
    """Copy every non-excluded file from workspace_dir into dest_dir.

    Used before each prompt so an escalated prompt can be rolled back by
    restoring from the snapshot. The dest_dir must not already exist (or if
    it does, it will be overlaid — caller is responsible for cleanup).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    for rel, _ in _iter_workspace_files(workspace_dir):
        src = workspace_dir / rel
        dest = dest_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def _diff_workspace_since_snapshot(
    workspace_dir: Path, snapshot_dir: Path
) -> list[Path]:
    """Return the list of relative paths that exist in workspace but differ
    from (or are missing from) the snapshot. These are the files the prompt
    created or modified."""
    snapshot_mtimes: dict[Path, int] = {}
    if snapshot_dir.exists():
        for rel, mtime in _iter_workspace_files(snapshot_dir):
            snapshot_mtimes[rel] = mtime
    changed: list[Path] = []
    for rel, mtime in _iter_workspace_files(workspace_dir):
        prev = snapshot_mtimes.get(rel)
        if prev is None or prev != mtime:
            changed.append(rel)
    return sorted(changed)


def _restore_workspace_from_snapshot(
    workspace_dir: Path, snapshot_dir: Path
) -> None:
    """Restore workspace_dir to match snapshot_dir exactly (within exclusions).

    1. Remove any file in workspace that is not in the snapshot (files the
       failed prompt added).
    2. Copy every file from snapshot back into workspace (overwrites files
       the failed prompt modified; recreates files the failed prompt may have
       deleted).
    """
    if not snapshot_dir.exists():
        return

    snapshot_rels: set[Path] = set()
    for rel, _ in _iter_workspace_files(snapshot_dir):
        snapshot_rels.add(rel)

    # Pass 1: remove files present in workspace but absent from snapshot.
    for rel, _ in list(_iter_workspace_files(workspace_dir)):
        if rel not in snapshot_rels:
            try:
                (workspace_dir / rel).unlink()
            except FileNotFoundError:
                pass

    # Pass 2: copy everything from snapshot back.
    for rel in snapshot_rels:
        src = snapshot_dir / rel
        dest = workspace_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def _make_call(
    *,
    prompt: str,
    session_id: str,
    new_session: bool,
    model: str | None,
    logs_dir: Path,
    iteration: int,
    role: str,
    pair: PromptPair,
    workspace_dir: Path,
) -> ClaudeCall:
    return ClaudeCall(
        prompt=prompt,
        session_id=session_id,
        new_session=new_session,
        model=model,
        stdout_log_path=logs_dir / f"iter-{iteration:02d}-{role}.stdout.log",
        stderr_log_path=logs_dir / f"iter-{iteration:02d}-{role}.stderr.log",
        stream_header=(
            f"── prompt {pair.index} '{pair.title}' / iter {iteration} / {role} ──"
        ),
        workspace_dir=workspace_dir,
    )


def run_prompt(
    pair: PromptPair,
    prior_artifacts: list[PriorArtifact],
    run_dir: Path,
    config: RunConfig,
    claude_client: ClaudeClient,
    run_id: str,
    workspace_dir: Path,
) -> PromptResult:
    if config.max_iterations < 1:
        raise ValueError(
            f"max_iterations must be >= 1, got {config.max_iterations}"
        )
    gen_session = _session_id(f"gen-prompt-{pair.index}-{run_id}")
    jud_session = _session_id(f"jud-prompt-{pair.index}-{run_id}")
    prompt_slug = _prompt_dir_name(pair)
    prompt_dir = run_dir / prompt_slug
    logs_dir = run_dir / "logs" / prompt_slug
    snapshot_dir = run_dir / "snapshots" / f"{prompt_slug}-pre"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot the workspace before the prompt runs so we can roll back to
    # this state if the prompt escalates. Also lets us diff at the end to
    # find out which files the prompt's generator created.
    _snapshot_workspace(workspace_dir, snapshot_dir)

    iterations: list[IterationResult] = []

    for iteration_number in range(1, config.max_iterations + 1):
        is_first = iteration_number == 1

        gen_msg = (
            build_initial_generator_message(pair, prior_artifacts)
            if is_first
            else build_revision_generator_message(iterations[-1].judge_output)
        )
        gen_call = _make_call(
            prompt=gen_msg,
            session_id=gen_session,
            new_session=is_first,
            model=config.model,
            logs_dir=logs_dir,
            iteration=iteration_number,
            role="generator",
            pair=pair,
            workspace_dir=workspace_dir,
        )
        gen_response = _call_or_persist_partial(
            claude_client, gen_call, prompt_dir / f"iter-{iteration_number:02d}-generator.md"
        )

        jud_msg = (
            build_initial_judge_message(pair, gen_response.stdout)
            if is_first
            else build_revision_judge_message(gen_response.stdout)
        )
        jud_call = _make_call(
            prompt=jud_msg,
            session_id=jud_session,
            new_session=is_first,
            model=config.model,
            logs_dir=logs_dir,
            iteration=iteration_number,
            role="judge",
            pair=pair,
            workspace_dir=workspace_dir,
        )
        jud_response = _call_or_persist_partial(
            claude_client, jud_call, prompt_dir / f"iter-{iteration_number:02d}-judge.md"
        )

        verdict = parse_verdict(jud_response.stdout)
        iterations.append(
            IterationResult(
                iteration=iteration_number,
                generator_output=gen_response.stdout,
                judge_output=jud_response.stdout,
                verdict=verdict,
            )
        )
        if verdict != Verdict.REVISE:
            break

    final = iterations[-1]
    final_verdict = final.verdict
    if final_verdict == Verdict.REVISE:
        final_verdict = Verdict.ESCALATE

    if final_verdict == Verdict.PASS:
        # Compute the list of files this prompt created so they can be
        # injected into subsequent prompts' prior-artifact context, and
        # preserve the workspace state (do not restore).
        created_files = _diff_workspace_since_snapshot(workspace_dir, snapshot_dir)
    else:
        # Escalation — roll back the workspace so a half-done prompt does
        # not pollute later prompts or leave garbage in the tree.
        _restore_workspace_from_snapshot(workspace_dir, snapshot_dir)
        created_files = []

    _write(prompt_dir / "final-artifact.md", final.generator_output)
    _write(prompt_dir / "final-verdict.txt", final_verdict.value + "\n")
    _write(
        prompt_dir / "files-created.txt",
        "\n".join(str(p) for p in created_files) + ("\n" if created_files else ""),
    )

    return PromptResult(
        pair=pair,
        iterations=iterations,
        final_verdict=final_verdict,
        final_artifact=final.generator_output,
        created_files=created_files,
    )


def _call_or_persist_partial(
    client: ClaudeClient, call: ClaudeCall, md_path: Path
) -> ClaudeResponse:
    """Invoke the client. On ClaudeInvocationError, write any partial stdout to
    md_path before re-raising so the runner's halt semantics are preserved."""
    try:
        response = client.call(call)
    except ClaudeInvocationError as err:
        _write(md_path, err.response.stdout)
        raise
    _write(md_path, response.stdout)
    return response


def run_pipeline(
    pairs: list[PromptPair],
    run_dir: Path,
    config: RunConfig,
    claude_client: ClaudeClient,
    source_file: Path,
    workspace_dir: Path | None = None,
) -> PipelineResult:
    run_id = run_dir.name
    run_dir.mkdir(parents=True, exist_ok=True)
    if workspace_dir is None:
        workspace_dir = Path.cwd().resolve()
    else:
        workspace_dir = Path(workspace_dir).resolve()
    started_at = datetime.now(timezone.utc)
    _write_manifest(run_dir, source_file, config, run_id,
                    started_at=_format_iso(started_at))

    prior_artifacts: list[PriorArtifact] = []
    prompt_results: list[PromptResult] = []

    for pair in pairs:
        if config.only is not None and pair.index != config.only:
            continue
        try:
            result = run_prompt(
                pair, prior_artifacts, run_dir, config, claude_client,
                run_id, workspace_dir,
            )
        except VerdictParseError as err:
            halt_reason = (
                f"R-NO-VERDICT: prompt {pair.index} \"{pair.title}\" "
                f"returned a judge response with no VERDICT line. {err}"
            )
            _finalise(run_dir, source_file, config, run_id, pairs, prompt_results,
                      started_at=started_at, halted_early=True,
                      halt_reason=halt_reason)
            return PipelineResult(prompt_results, halted_early=True, halt_reason=halt_reason)
        except ClaudeInvocationError as err:
            halt_reason = _format_claude_failed_halt_reason(pair, err, run_dir)
            _finalise(run_dir, source_file, config, run_id, pairs, prompt_results,
                      started_at=started_at, halted_early=True,
                      halt_reason=halt_reason)
            return PipelineResult(prompt_results, halted_early=True, halt_reason=halt_reason)

        prompt_results.append(result)
        if result.final_verdict == Verdict.PASS:
            prior_artifacts.append(
                PriorArtifact(
                    title=pair.title,
                    text_body=result.final_artifact,
                    files=list(result.created_files),
                )
            )
        else:
            halt_reason = f"prompt {pair.index} escalated"
            _finalise(run_dir, source_file, config, run_id, pairs, prompt_results,
                      started_at=started_at, halted_early=True,
                      halt_reason=halt_reason)
            return PipelineResult(prompt_results, halted_early=True, halt_reason=halt_reason)

    _finalise(run_dir, source_file, config, run_id, pairs, prompt_results,
              started_at=started_at, halted_early=False, halt_reason=None)
    return PipelineResult(prompt_results, halted_early=False, halt_reason=None)


def _format_claude_failed_halt_reason(
    pair: PromptPair, err: ClaudeInvocationError, run_dir: Path,
) -> str:
    """Build a multi-line R-CLAUDE-FAILED halt reason per CD-001 §11.2."""
    partial_md_path = err.call.stdout_log_path.parent.parent.parent / (
        _prompt_dir_name(pair) + "/" + err.call.stdout_log_path.stem.removesuffix(".stdout") + ".md"
    )
    logs_dir = err.call.stdout_log_path.parent
    stderr_tail = _tail_lines(err.response.stderr, STDERR_TAIL_LINES)
    return (
        f"R-CLAUDE-FAILED: prompt {pair.index} \"{pair.title}\" "
        f"{err.call.stream_header} exited with status "
        f"{err.response.returncode}.\n"
        f"\n"
        f"Last {STDERR_TAIL_LINES} lines of stderr "
        f"(from {err.call.stderr_log_path}):\n"
        f"{stderr_tail}\n"
        f"\n"
        f"Partial output saved to: {partial_md_path}\n"
        f"Full logs saved to: {logs_dir}/\n"
        f"\n"
        f"To retry, re-run prompt-runner. To investigate, look at the "
        f".stdout.log and .stderr.log files in the logs directory above."
    )


def _now_iso() -> str:
    return _format_iso(datetime.now(timezone.utc))


def _format_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_manifest(
    run_dir: Path, source_file: Path, config: RunConfig, run_id: str, started_at: str
) -> None:
    manifest = {
        "source_file": str(source_file.resolve()),
        "run_id": run_id,
        "config": {
            "max_iterations": config.max_iterations,
            "model": config.model,
            "only": config.only,
            "dry_run": config.dry_run,
        },
        "started_at": started_at,
        "finished_at": None,
    }
    _write(run_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n")


def _finalise(
    run_dir: Path,
    source_file: Path,
    config: RunConfig,
    run_id: str,
    pairs: list[PromptPair],
    prompt_results: list[PromptResult],
    started_at: datetime,
    halted_early: bool,
    halt_reason: str | None,
) -> None:
    finished_at = datetime.now(timezone.utc)
    wall_time = _format_wall_time(started_at, finished_at)

    # Rewrite manifest.json with finished_at and halt_reason.
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["finished_at"] = _format_iso(finished_at)
    manifest["halt_reason"] = halt_reason
    manifest["wall_time"] = wall_time
    _write(manifest_path, json.dumps(manifest, indent=2) + "\n")

    _write(run_dir / "summary.txt", _format_summary(
        source_file, run_dir, pairs, prompt_results,
        halted_early, halt_reason, wall_time,
    ))


def _format_summary(
    source_file: Path,
    run_dir: Path,
    pairs: list[PromptPair],
    prompt_results: list[PromptResult],
    halted_early: bool,
    halt_reason: str | None,
    wall_time: str,
) -> str:
    status = "halted" if halted_early else "completed"
    lines = [
        "Prompt Runner — Run Summary",
        f"Source: {source_file}",
        f"Run:    {run_dir}",
        f"Status: {status}",
        "",
        "Prompts:",
    ]
    # Index prompt_results by pair.index for fast lookup.
    results_by_index = {r.pair.index: r for r in prompt_results}
    for pair in pairs:
        slug = _prompt_dir_name(pair)
        result = results_by_index.get(pair.index)
        if result is None:
            lines.append(
                f"  {pair.index:02d}  {slug:<40s}  skipped"
            )
        else:
            iter_count = len(result.iterations)
            lines.append(
                f"  {pair.index:02d}  {slug:<40s}  {result.final_verdict.value:<9s}  {iter_count} iter"
            )
    total_calls = sum(len(r.iterations) * 2 for r in prompt_results)
    lines.append("")
    lines.append(f"Total claude calls: {total_calls}")
    lines.append(f"Wall time: {wall_time}")
    if halt_reason:
        lines.append(f"Halt reason: {halt_reason}")
    lines.append("")
    return "\n".join(lines)
