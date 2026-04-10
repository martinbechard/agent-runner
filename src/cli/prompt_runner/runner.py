"""Pipeline orchestration for prompt-runner.

See docs/design/components/CD-001-prompt-runner.md sections 9 and 11.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
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
from prompt_runner.parser import ForkPoint, PromptPair, VariantPrompt
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
    generator_prelude: str | None = None
    """Optional text prepended to every generator Claude message in this
    run.  Used by methodology-runner to inject phase-specific skill
    loading instructions.  prompt-runner treats this as opaque text —
    it does not parse, interpret, or modify it."""
    judge_prelude: str | None = None
    """Optional text prepended to every judge Claude message in this
    run.  Symmetric to generator_prelude."""
    dangerously_skip_permissions: bool = False
    """When True, pass --dangerously-skip-permissions to claude in
    interactive mode so the user is not prompted for every tool call."""
    fork_from_session: str | None = None
    """When set, the first generator call in this run uses
    --resume <session-id> --fork-session to inherit conversation
    context from a prior session. Used by variant forks so each
    variant starts with the same context as the pre-fork prompts."""
    variant_sequential: bool = False
    """When True, run fork-point variants one at a time instead of in
    parallel. Parallel (default) is faster; sequential uses less quota."""


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
    last_session_id: str = ""
    """Session ID from the last generator claude call. Used by the fork
    mechanism to inherit conversation context via --fork-session."""


@dataclass(frozen=True)
class VariantResult:
    """Outcome of one variant subprocess within a fork point."""

    variant_name: str
    variant_title: str
    exit_code: int
    run_dir: Path
    workspace_dir: Path
    summary: str  # content of summary.txt, or empty if not found


@dataclass(frozen=True)
class ForkResult:
    """Aggregated results for all variants at one fork point."""

    fork_index: int
    fork_title: str
    variant_results: list[VariantResult]


@dataclass(frozen=True)
class PipelineResult:
    prompt_results: list[PromptResult]
    halted_early: bool
    halt_reason: str | None
    fork_results: list[ForkResult] = field(default_factory=list)


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
    pair: PromptPair,
    prior_artifacts: list[PriorArtifact],
    generator_prelude: str | None = None,
) -> str:
    sections: list[str] = []

    if generator_prelude:
        sections.append(generator_prelude)

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


def _format_generator_files_section(files: list[Path]) -> str:
    """Format a list of files produced by the generator for a judge message.

    If files is empty (text-only task), returns a short note saying so;
    the judge can still look around with tools but should not expect any
    specific files.
    """
    if not files:
        return (
            "# Files produced by the generator during this iteration\n\n"
            "(no files created or modified — this appears to be a text-only "
            "task)"
        )
    listing = "\n".join(f"- {f}" for f in files)
    return (
        "# Files produced by the generator during this prompt (relative to cwd)\n\n"
        f"{listing}\n\n"
        "These are the exact files the generator added or modified since "
        "this prompt started. Your cwd is the project root — Read any of "
        "them directly, run Bash (python -m py_compile, mypy, pytest, etc.) "
        "to verify them, and consult them alongside the text response."
    )


def build_initial_judge_message(
    pair: PromptPair,
    artifact: str,
    generator_files: list[Path] | None = None,
    judge_prelude: str | None = None,
) -> str:
    files_section = _format_generator_files_section(generator_files or [])
    prelude_block = f"{judge_prelude}{_HORIZONTAL_RULE}" if judge_prelude else ""
    return (
        f"{prelude_block}"
        f"{pair.validation_prompt}"
        f"{_HORIZONTAL_RULE}"
        f"# Artifact to evaluate (generator's text response)\n\n{artifact}"
        f"{_HORIZONTAL_RULE}"
        f"{files_section}"
        f"{_HORIZONTAL_RULE}"
        f"{VERDICT_INSTRUCTION}"
    )


def build_revision_generator_message(
    judge_output: str,
    generator_prelude: str | None = None,
) -> str:
    prelude_block = f"{generator_prelude}{_HORIZONTAL_RULE}" if generator_prelude else ""
    return (
        f"{prelude_block}"
        f"{REVISION_GENERATOR_PREAMBLE}\n\n"
        f"# Judge feedback\n\n{judge_output}"
        f"{_HORIZONTAL_RULE}"
        f"{PROJECT_ORGANISER_INSTRUCTION}"
    )


def build_revision_judge_message(
    new_artifact: str,
    generator_files: list[Path] | None = None,
    judge_prelude: str | None = None,
) -> str:
    files_section = _format_generator_files_section(generator_files or [])
    prelude_block = f"{judge_prelude}{_HORIZONTAL_RULE}" if judge_prelude else ""
    return (
        f"{prelude_block}"
        f"{ANTI_ANCHORING_CLAUSE}\n\n"
        f"# Revised artifact (generator's text response)\n\n{new_artifact}"
        f"{_HORIZONTAL_RULE}"
        f"{files_section}"
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
    fork_session: bool = False,
    fork_from_session_id: str = "",
) -> ClaudeCall:
    return ClaudeCall(
        prompt=prompt,
        session_id=session_id,
        new_session=new_session,
        model=model,
        stdout_log_path=logs_dir / f"iter-{iteration:02d}-{role}.stdout.log",
        stderr_log_path=logs_dir / f"iter-{iteration:02d}-{role}.stderr.log",
        fork_session=fork_session,
        fork_from_session_id=fork_from_session_id,
        stream_header=(
            f"── prompt {pair.index} '{pair.title}' / iter {iteration} / {role} ──"
        ),
        workspace_dir=workspace_dir,
    )


def _run_interactive_prompt(
    pair: PromptPair,
    prior_artifacts: list[PriorArtifact],
    run_dir: Path,
    config: RunConfig,
    workspace_dir: Path,
) -> PromptResult:
    """Spawn claude interactively with pair.generation_prompt as the mission.

    Inherits stdin/stdout/stderr so the user sees a real TTY session and
    can drive claude directly. Waits for the subprocess to exit (human
    types /exit or Ctrl-C). Marks the prompt pass regardless of exit
    code — the human is the validator in interactive mode.
    """
    import subprocess

    from prompt_runner.verdict import Verdict

    prompt_slug = _prompt_dir_name(pair)
    prompt_dir = run_dir / prompt_slug
    prompt_dir.mkdir(parents=True, exist_ok=True)

    snapshot_dir = run_dir / "snapshots" / f"{prompt_slug}-pre"
    _snapshot_workspace(workspace_dir, snapshot_dir)

    # Build the mission text: prior-artifact context + the pair's
    # generation prompt. We use the same message builder as the
    # non-interactive path so the user sees consistent context across
    # the two modes.
    mission = build_initial_generator_message(
        pair, prior_artifacts, generator_prelude=config.generator_prelude,
    )

    # Spawn claude interactively. stdin/stdout/stderr inherit from this
    # process so the user sees a real TTY session. Wait for exit.
    argv = ["claude"]
    # Interactive mode always skips permissions — the human is present
    # and driving the session, so tool-use prompts are just friction.
    argv.append("--dangerously-skip-permissions")
    if config.model:
        argv.extend(["--model", config.model])
    argv.append(mission)

    print(
        f"\n{'=' * 70}\n"
        f"-- prompt {pair.index} '{pair.title}' / INTERACTIVE --\n"
        f"{'=' * 70}\n"
        f"Spawning claude interactively. When done, type /exit or Ctrl-C\n"
        f"to return control to prompt-runner.\n"
        f"{'=' * 70}\n",
        flush=True,
    )

    result = subprocess.run(argv)  # no capture — inherit stdio
    exit_code = result.returncode

    # Capture files the session created
    created_files = _diff_workspace_since_snapshot(workspace_dir, snapshot_dir)

    # Write artifact stubs so downstream resume logic can see the pair completed.
    # There is no generator text to capture (stdio was inherited), so the
    # artifact file records the fact that this was an interactive session.
    artifact_stub = (
        f"[interactive prompt -- stdio inherited, no captured output]\n"
        f"Mission: {pair.title}\n"
        f"Exit code: {exit_code}\n"
    )
    _write(prompt_dir / "final-artifact.md", artifact_stub)
    _write(prompt_dir / "final-verdict.txt", Verdict.PASS.value + "\n")
    _write(
        prompt_dir / "files-created.txt",
        "\n".join(str(p) for p in created_files) + ("\n" if created_files else ""),
    )

    return PromptResult(
        pair=pair,
        iterations=[],  # no iterations in interactive mode
        final_verdict=Verdict.PASS,
        final_artifact=artifact_stub,
        created_files=created_files,
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
    if pair.interactive:
        return _run_interactive_prompt(
            pair, prior_artifacts, run_dir, config, workspace_dir,
        )
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
    gen_response: ClaudeResponse | None = None

    for iteration_number in range(1, config.max_iterations + 1):
        is_first = iteration_number == 1

        gen_msg = (
            build_initial_generator_message(
                pair, prior_artifacts,
                generator_prelude=config.generator_prelude,
            )
            if is_first
            else build_revision_generator_message(
                iterations[-1].judge_output,
                generator_prelude=config.generator_prelude,
            )
        )
        # When forking from a prior session, the FIRST generator call
        # uses --resume <prior-session> --fork-session to inherit context.
        # Subsequent iterations resume from the forked session normally.
        use_fork = is_first and config.fork_from_session is not None
        # For forks: gen_session is the NEW session ID for this fork;
        # fork_from_session is the SOURCE to inherit context from.
        # Use a random UUID for forks to avoid collisions with prior runs.
        if use_fork:
            import uuid as _uuid
            fork_new_session = str(_uuid.uuid4())
        else:
            fork_new_session = gen_session
        gen_call = _make_call(
            prompt=gen_msg,
            session_id=fork_new_session,
            new_session=is_first and not use_fork,
            model=config.model,
            logs_dir=logs_dir,
            iteration=iteration_number,
            role="generator",
            pair=pair,
            workspace_dir=workspace_dir,
            fork_session=use_fork,
            fork_from_session_id=config.fork_from_session if use_fork else "",
        )
        gen_response = _call_or_persist_partial(
            claude_client, gen_call, prompt_dir / f"iter-{iteration_number:02d}-generator.md"
        )

        # Diff the workspace against the pre-prompt snapshot to find which
        # files the generator has touched so far. Pass this list to the
        # judge so it knows exactly which files to inspect, rather than
        # having to discover them via Glob.
        files_so_far = _diff_workspace_since_snapshot(workspace_dir, snapshot_dir)

        if not pair.validation_prompt:
            # Validator-less prompt: accept the generator's output without a
            # judge call. Mark the iteration as pass so the loop exits.
            iterations.append(
                IterationResult(
                    iteration=iteration_number,
                    generator_output=gen_response.stdout,
                    judge_output="",  # no judge call
                    verdict=Verdict.PASS,
                )
            )
            break

        jud_msg = (
            build_initial_judge_message(
                pair, gen_response.stdout, files_so_far,
                judge_prelude=config.judge_prelude,
            )
            if is_first
            else build_revision_judge_message(
                gen_response.stdout, files_so_far,
                judge_prelude=config.judge_prelude,
            )
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

    # Capture the session ID from the last generator response for fork support.
    last_sid = ""
    if gen_response is not None:
        last_sid = getattr(gen_response, "session_id", "")

    return PromptResult(
        pair=pair,
        iterations=iterations,
        final_verdict=final_verdict,
        final_artifact=final.generator_output,
        created_files=created_files,
        last_session_id=last_sid,
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


def _load_prior_artifact_from_disk(
    pair: PromptPair, run_dir: Path,
) -> PriorArtifact:
    """Reconstruct a PriorArtifact for a completed prompt from its on-disk
    final-artifact and files-created files. Used by --resume to rebuild the
    prior-artifact context for prompts that were already completed in a
    previous run."""
    prompt_dir = run_dir / _prompt_dir_name(pair)
    text_body = (prompt_dir / "final-artifact.md").read_text(encoding="utf-8")
    files_txt = (prompt_dir / "files-created.txt").read_text(encoding="utf-8")
    files = [
        Path(line) for line in files_txt.splitlines() if line.strip()
    ]
    return PriorArtifact(
        title=pair.title,
        text_body=text_body,
        files=files,
    )


def _serialize_pairs_to_md(pairs: list[PromptPair]) -> str:
    """Convert a list of PromptPair objects back to prompt-runner markdown format.

    Each pair becomes a '## Prompt N: <title>' section with two fenced code
    blocks.  Validator-less pairs (empty validation_prompt) get only one block.
    """
    sections: list[str] = []
    for pair in pairs:
        lines: list[str] = [f"## Prompt {pair.index}: {pair.title}", ""]
        lines.append("```")
        lines.append(pair.generation_prompt)
        lines.append("```")
        if pair.validation_prompt:
            lines.append("")
            lines.append("```")
            lines.append(pair.validation_prompt)
            lines.append("```")
        sections.append("\n".join(lines))
    return "\n\n".join(sections) + "\n"


def _copy_workspace_for_variant(src_workspace: Path, dest_workspace: Path) -> None:
    """Copy a workspace directory to a new location, excluding build/cache dirs.

    dest_workspace must not already exist.
    """
    def _ignore(dir_path: str, names: list[str]) -> list[str]:
        skipped: list[str] = []
        for name in names:
            rel = Path(dir_path) / name
            if name in _SNAPSHOT_SKIP_DIR_NAMES or name.endswith(".egg-info") or name == ".DS_Store":
                skipped.append(name)
        return skipped

    shutil.copytree(src_workspace, dest_workspace, ignore=_ignore, symlinks=False)


def _run_fork_point(
    fork: ForkPoint,
    fork_index_in_run: int,
    items_after: list[PromptPair | ForkPoint],
    run_dir: Path,
    workspace_dir: Path,
    config: RunConfig,
    source_file: Path,
    fork_from_session: str = "",
) -> ForkResult:
    """Execute all variants of a fork point and return their aggregated results.

    For each variant:
    1. Copy the current workspace into a per-variant directory.
    2. Build a synthetic prompt file (variant pairs + items_after).
    3. Spawn a prompt-runner subprocess.
    4. Collect results.
    """
    fork_slug = f"fork-{fork.index:02d}-{_slugify(fork.title)}"
    fork_dir = run_dir / fork_slug
    fork_dir.mkdir(parents=True, exist_ok=True)

    procs: list[tuple[VariantPrompt, Path, Path, subprocess.Popen[bytes]]] = []

    for variant in fork.variants:
        variant_slug = f"variant-{_slugify(variant.variant_name)}"
        variant_dir = fork_dir / variant_slug
        variant_workspace = variant_dir / "workspace"
        # Use a unique run-dir name per variant so _session_id() generates
        # distinct UUIDs (it hashes the run_dir.name as the run_id).
        variant_run_dir = variant_dir / f"run-{variant_slug}"

        variant_dir.mkdir(parents=True, exist_ok=True)
        variant_run_dir.mkdir(parents=True, exist_ok=True)

        # Copy the workspace into the variant directory.
        _copy_workspace_for_variant(workspace_dir, variant_workspace)

        # Build a synthetic prompt list: variant pairs + all subsequent items.
        # Only PromptPair items from items_after are serialised (ForkPoints
        # in the tail are not yet supported for recursive nesting; they will
        # be ignored in serialisation for now).
        tail_pairs: list[PromptPair] = [
            item for item in items_after if isinstance(item, PromptPair)
        ]
        synthetic_pairs = list(variant.pairs) + tail_pairs
        synthetic_md = _serialize_pairs_to_md(synthetic_pairs)

        temp_md_path = variant_dir / "synthetic-prompt.md"
        temp_md_path.write_text(synthetic_md, encoding="utf-8")

        # When forking sessions, use the ORIGINAL workspace as project-dir
        # so claude finds the session (sessions are stored per-project-path).
        # Variants share the original workspace — must run sequentially.
        effective_project_dir = (
            workspace_dir if fork_from_session else variant_workspace
        )
        cmd: list[str] = [
            sys.executable, "-m", "prompt_runner",
            "run", str(temp_md_path),
            "--project-dir", str(effective_project_dir),
            "--output-dir", str(variant_run_dir),
        ]
        if config.model:
            cmd.extend(["--model", config.model])
        if config.generator_prelude:
            prelude_path = variant_dir / "generator-prelude.txt"
            prelude_path.write_text(config.generator_prelude, encoding="utf-8")
            cmd.extend(["--generator-prelude", str(prelude_path)])
        if config.judge_prelude:
            prelude_path = variant_dir / "judge-prelude.txt"
            prelude_path.write_text(config.judge_prelude, encoding="utf-8")
            cmd.extend(["--judge-prelude", str(prelude_path)])
        if fork_from_session:
            cmd.extend(["--fork-from-session", fork_from_session])

        print(
            f"[fork {fork.index}] spawning variant '{variant.variant_name}' "
            f"({variant.variant_title}) → {variant_run_dir}",
            flush=True,
        )

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        procs.append((variant, variant_run_dir, variant_workspace, proc))

        if config.variant_sequential:
            proc.wait()

    # Wait for all subprocesses.
    variant_results: list[VariantResult] = []
    for variant, variant_run_dir, variant_workspace, proc in procs:
        proc.wait()
        exit_code = proc.returncode
        summary_path = variant_run_dir / "summary.txt"
        summary = (
            summary_path.read_text(encoding="utf-8")
            if summary_path.exists()
            else ""
        )
        variant_results.append(VariantResult(
            variant_name=variant.variant_name,
            variant_title=variant.variant_title,
            exit_code=exit_code,
            run_dir=variant_run_dir,
            workspace_dir=variant_workspace,
            summary=summary,
        ))

    # Write a comparison report.
    comparison_lines: list[str] = [
        f"Fork {fork.index}: {fork.title}",
        f"Slug: {fork_slug}",
        f"Variants: {len(variant_results)}",
        "",
    ]

    # Side-by-side table header.
    col_name = 12
    col_code = 9
    col_status = 11
    col_summary = 48
    header = (
        f"{'Variant':<{col_name}} {'Exit Code':>{col_code}} {'Status':<{col_status}} Summary"
    )
    separator = "-" * (col_name + col_code + col_status + col_summary + 3)
    comparison_lines.append(header)
    comparison_lines.append(separator)

    for vr in variant_results:
        status = "completed" if vr.exit_code == 0 else "failed"
        # First 3 non-empty lines of summary.txt as a one-liner excerpt.
        summary_lines = [ln for ln in vr.summary.splitlines() if ln.strip()][:3]
        excerpt = " | ".join(summary_lines)
        if len(excerpt) > col_summary:
            excerpt = excerpt[: col_summary - 3] + "..."
        name_col = f"{vr.variant_name} ({vr.variant_title})"
        if len(name_col) > col_name:
            name_col = name_col[: col_name - 1] + "…"
        comparison_lines.append(
            f"{name_col:<{col_name}} {vr.exit_code:>{col_code}} {status:<{col_status}} {excerpt}"
        )

    comparison_lines.append("")
    comparison_lines.append("Per-variant details:")

    for vr in variant_results:
        status = "completed" if vr.exit_code == 0 else "failed"
        comparison_lines.append(f"")
        comparison_lines.append(f"  Variant {vr.variant_name}: {vr.variant_title}")
        comparison_lines.append(f"    exit code : {vr.exit_code} ({status})")
        comparison_lines.append(f"    run dir   : {vr.run_dir}")
        comparison_lines.append(f"    workspace : {vr.workspace_dir}")

        # Summary excerpt (first 3 lines).
        summary_lines = [ln for ln in vr.summary.splitlines() if ln.strip()][:3]
        if summary_lines:
            comparison_lines.append("    summary   :")
            for ln in summary_lines:
                comparison_lines.append(f"      {ln}")

        # Files created in the variant workspace.
        if vr.workspace_dir.exists():
            ws_files = sorted(
                str(p.relative_to(vr.workspace_dir))
                for p in vr.workspace_dir.rglob("*")
                if p.is_file()
            )
            if ws_files:
                comparison_lines.append(f"    workspace files ({len(ws_files)}):")
                for f in ws_files:
                    comparison_lines.append(f"      {f}")

    comparison_lines.append("")

    _write(fork_dir / "comparison.txt", "\n".join(comparison_lines) + "\n")

    return ForkResult(
        fork_index=fork.index,
        fork_title=fork.title,
        variant_results=variant_results,
    )


def run_pipeline(
    pairs: list[PromptPair | ForkPoint],
    run_dir: Path,
    config: RunConfig,
    claude_client: ClaudeClient,
    source_file: Path,
    workspace_dir: Path | None = None,
    resume: bool = False,
) -> PipelineResult:
    run_id = run_dir.name
    run_dir.mkdir(parents=True, exist_ok=True)
    if workspace_dir is None:
        workspace_dir = Path.cwd().resolve()
    else:
        workspace_dir = Path(workspace_dir).resolve()
    started_at = datetime.now(timezone.utc)
    if not resume:
        _write_manifest(run_dir, source_file, config, run_id,
                        started_at=_format_iso(started_at))

    prior_artifacts: list[PriorArtifact] = []
    prompt_results: list[PromptResult] = []
    fork_results: list[ForkResult] = []
    last_session_id: str = ""  # for fork context inheritance

    # When resuming, track whether we have hit the first incomplete prompt.
    # All prompts before it that have a 'pass' verdict are skipped; once we
    # encounter an incomplete prompt we switch to normal forward execution.
    still_skipping = resume

    for item_index, item in enumerate(pairs):
        # --- ForkPoint handling ---
        if isinstance(item, ForkPoint):
            fork = item
            items_after = pairs[item_index + 1:]
            print(
                f"[fork] prompt {fork.index} '{fork.title}' — "
                f"spawning {len(fork.variants)} variant(s)",
                flush=True,
            )
            fork_result = _run_fork_point(
                fork=fork,
                fork_index_in_run=item_index,
                items_after=items_after,
                run_dir=run_dir,
                workspace_dir=workspace_dir,
                config=config,
                source_file=source_file,
                fork_from_session=last_session_id,
            )
            fork_results.append(fork_result)
            # Parent does not continue past the fork point.
            _finalise(run_dir, source_file, config, run_id, pairs, prompt_results,
                      started_at=started_at, halted_early=False, halt_reason=None,
                      fork_results=fork_results)
            return PipelineResult(
                prompt_results, halted_early=False, halt_reason=None,
                fork_results=fork_results,
            )

        # --- Normal PromptPair handling ---
        pair: PromptPair = item  # type: ignore[assignment]

        if config.only is not None and pair.index != config.only:
            continue

        if still_skipping:
            prompt_dir = run_dir / _prompt_dir_name(pair)
            verdict_path = prompt_dir / "final-verdict.txt"
            if verdict_path.exists() and verdict_path.read_text(encoding="utf-8").splitlines()[0] == "pass":
                # This prompt already completed with pass — skip it.
                prior_artifact = _load_prior_artifact_from_disk(pair, run_dir)
                text_body = (prompt_dir / "final-artifact.md").read_text(encoding="utf-8")
                files_txt = (prompt_dir / "files-created.txt").read_text(encoding="utf-8")
                created_files = [
                    Path(line) for line in files_txt.splitlines() if line.strip()
                ]
                synthetic_result = PromptResult(
                    pair=pair,
                    iterations=[],
                    final_verdict=Verdict.PASS,
                    final_artifact=text_body,
                    created_files=created_files,
                )
                prompt_results.append(synthetic_result)
                prior_artifacts.append(prior_artifact)
                print(
                    f"[resume] skipping prompt {pair.index} '{pair.title}' — already pass",
                    flush=True,
                )
                continue
            else:
                # First incomplete prompt — stop skipping from here on.
                still_skipping = False

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
        if result.last_session_id:
            last_session_id = result.last_session_id
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
    pairs: list[PromptPair | ForkPoint],
    prompt_results: list[PromptResult],
    started_at: datetime,
    halted_early: bool,
    halt_reason: str | None,
    fork_results: list[ForkResult] | None = None,
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
        fork_results=fork_results or [],
    ))


def _format_summary(
    source_file: Path,
    run_dir: Path,
    pairs: list[PromptPair | ForkPoint],
    prompt_results: list[PromptResult],
    halted_early: bool,
    halt_reason: str | None,
    wall_time: str,
    fork_results: list[ForkResult] | None = None,
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
    for item in pairs:
        if isinstance(item, ForkPoint):
            fork = item
            lines.append(
                f"  {fork.index:02d}  fork-{fork.index:02d}-{_slugify(fork.title):<34s}  [fork]"
            )
            if fork_results:
                for fr in fork_results:
                    if fr.fork_index == fork.index:
                        for vr in fr.variant_results:
                            vstatus = "ok" if vr.exit_code == 0 else f"exit {vr.exit_code}"
                            lines.append(
                                f"        variant-{vr.variant_name}  {vr.variant_title}  {vstatus}"
                            )
        else:
            pair: PromptPair = item  # type: ignore[assignment]
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
    if fork_results:
        lines.append(f"Forks executed: {len(fork_results)}")
    if halt_reason:
        lines.append(f"Halt reason: {halt_reason}")
    lines.append("")
    return "\n".join(lines)
