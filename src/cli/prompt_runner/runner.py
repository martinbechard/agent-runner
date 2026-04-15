"""Pipeline orchestration for prompt-runner.

See docs/design/components/CD-001-prompt-runner.md sections 9 and 11.
"""
from __future__ import annotations

import json
import os
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
from prompt_runner.process_tracking import (
    mark_process_completed,
    write_spawn_metadata,
)
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
    "file, determine its path with the repository's file-placement helper. "
    "Prefer the dedicated `project_organiser` custom agent / "
    "`project-organiser` sub-agent when the runtime supports it, because that "
    "keeps taxonomy context isolated. If the dedicated agent is unavailable, "
    "use the `project-organiser-use` skill or consult "
    "`docs/project-taxonomy.md` directly. Use the resulting path as the exact "
    "file path for your Write tool call. Do not guess paths from the project "
    "layout and do not rely on an external Claude CLI wrapper. If this task "
    "is purely text output (no files), ignore this instruction."
)
_HORIZONTAL_RULE = "\n\n---\n\n"
RUN_FILES_DIRNAME = ".run-files"

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


def _emit_progress(message: str) -> None:
    """Write a terse live progress line to stdout."""
    sys.stdout.write(f"{message}\n")
    sys.stdout.flush()


def _progress_prefix(started_at: datetime) -> str:
    """Return a fixed-width elapsed-seconds prefix from a run-relative start."""
    elapsed = datetime.now(timezone.utc) - started_at
    seconds = max(0, int(elapsed.total_seconds()))
    return f"T+{seconds:04d}s"


@dataclass(frozen=True)
class RunConfig:
    backend: str = "codex"
    """Agent backend to use for prompt execution."""
    max_iterations: int = MAX_ITERATIONS_DEFAULT
    model: str | None = None
    only: int | None = None
    judge_only: int | None = None
    dry_run: bool = False
    generator_prelude: str | None = None
    """Optional text prepended to every generator Claude message in this
    run.  Used by methodology-runner to inject phase-specific skill
    loading instructions.  prompt-runner treats this as opaque text —
    it does not parse, interpret, or modify it."""
    judge_prelude: str | None = None
    """Optional text prepended to every judge Claude message in this
    run.  Symmetric to generator_prelude."""
    include_project_organiser: bool = True
    """When True, append the project-organiser sub-agent instruction to
    generator prompts that create files."""
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
    verbose: bool = False
    """When True, mirror backend stdout/stderr live to the terminal."""
    placeholder_values: dict[str, str] = field(default_factory=dict)
    """Caller-supplied placeholder bindings applied in addition to
    built-in values such as run_dir and project_dir."""


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
    relative to the worktree directory. Empty for text-only prompts. Passed
    to subsequent prompts' generator messages as part of the file manifest so
    they know what the prior prompt produced on disk."""
    last_session_id: str = ""
    """Session ID from the last generator claude call. Used by the fork
    mechanism to inherit conversation context via --fork-session."""


@dataclass(frozen=True)
class DeterministicValidationResult:
    command: list[str]
    script_path: Path
    returncode: int
    stdout: str
    stderr: str
    stdout_log_path: Path
    stderr_log_path: Path
    process_metadata_path: Path


class DeterministicValidationError(Exception):
    """Raised when deterministic validation cannot complete successfully."""


@dataclass(frozen=True)
class VariantResult:
    """Outcome of one variant subprocess within a fork point."""

    variant_name: str
    variant_title: str
    exit_code: int
    run_dir: Path
    worktree_dir: Path
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
    """Relative paths (relative to worktree_dir) of files created by the
    prior prompt. The current prompt's generator can Read them directly
    since it shares the same worktree."""


def _format_file_manifest(files: list[Path]) -> str:
    if not files:
        return "(no files created)"
    return "\n".join(f"- {f}" for f in files)


def build_initial_generator_message(
    pair: PromptPair,
    prior_artifacts: list[PriorArtifact],
    generator_prelude: str | None = None,
    include_project_organiser: bool = True,
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
    if include_project_organiser:
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


def _format_deterministic_validation_section(
    result: DeterministicValidationResult | None,
) -> str:
    if result is None:
        return (
            "# Deterministic validation\n\n"
            "(no deterministic validation configured for this prompt)"
        )
    stdout = result.stdout.strip() or "(empty)"
    stderr = result.stderr.strip() or "(empty)"
    status = (
        "checks passed"
        if result.returncode == 0
        else "checks failed"
        if result.returncode == 1
        else "script error"
    )
    command_listing = "\n".join(f"- {part}" for part in result.command)
    return (
        "# Deterministic validation\n\n"
        f"Script: `{result.script_path}`\n"
        f"Return code: `{result.returncode}` ({status})\n"
        f"Stdout log: `{result.stdout_log_path}`\n"
        f"Stderr log: `{result.stderr_log_path}`\n"
        f"Process metadata: `{result.process_metadata_path}`\n\n"
        "Command argv:\n"
        f"{command_listing}\n\n"
        "Stdout:\n\n"
        f"{stdout}\n\n"
        "Stderr:\n\n"
        f"{stderr}"
    )


def build_initial_judge_message(
    pair: PromptPair,
    artifact: str,
    generator_files: list[Path] | None = None,
    deterministic_validation: DeterministicValidationResult | None = None,
    judge_prelude: str | None = None,
) -> str:
    files_section = _format_generator_files_section(generator_files or [])
    deterministic_section = _format_deterministic_validation_section(
        deterministic_validation,
    )
    prelude_block = f"{judge_prelude}{_HORIZONTAL_RULE}" if judge_prelude else ""
    return (
        f"{prelude_block}"
        f"{pair.validation_prompt}"
        f"{_HORIZONTAL_RULE}"
        f"# Artifact to evaluate (generator's text response)\n\n{artifact}"
        f"{_HORIZONTAL_RULE}"
        f"{files_section}"
        f"{_HORIZONTAL_RULE}"
        f"{deterministic_section}"
        f"{_HORIZONTAL_RULE}"
        f"{VERDICT_INSTRUCTION}"
    )


def build_revision_generator_message(
    judge_output: str,
    generator_prelude: str | None = None,
    original_task: str | None = None,
    previous_artifact: str | None = None,
    include_project_organiser: bool = True,
) -> str:
    prelude_block = f"{generator_prelude}{_HORIZONTAL_RULE}" if generator_prelude else ""
    task_block = (
        f"# Original task\n\n{original_task}{_HORIZONTAL_RULE}"
        if original_task else ""
    )
    previous_artifact_block = (
        f"# Previous artifact (generator's last text response)\n\n"
        f"{previous_artifact}{_HORIZONTAL_RULE}"
        if previous_artifact else ""
    )
    msg = (
        f"{prelude_block}"
        f"{task_block}"
        f"{previous_artifact_block}"
        f"{REVISION_GENERATOR_PREAMBLE}\n\n"
        f"# Judge feedback\n\n{judge_output}"
    )
    if include_project_organiser:
        msg += f"{_HORIZONTAL_RULE}{PROJECT_ORGANISER_INSTRUCTION}"
    return msg


def build_revision_judge_message(
    new_artifact: str,
    generator_files: list[Path] | None = None,
    deterministic_validation: DeterministicValidationResult | None = None,
    judge_prelude: str | None = None,
    validation_prompt: str | None = None,
) -> str:
    files_section = _format_generator_files_section(generator_files or [])
    deterministic_section = _format_deterministic_validation_section(
        deterministic_validation,
    )
    prelude_block = f"{judge_prelude}{_HORIZONTAL_RULE}" if judge_prelude else ""
    validation_block = (
        f"{validation_prompt}{_HORIZONTAL_RULE}"
        if validation_prompt else ""
    )
    return (
        f"{prelude_block}"
        f"{validation_block}"
        f"{ANTI_ANCHORING_CLAUSE}\n\n"
        f"# Revised artifact (generator's text response)\n\n{new_artifact}"
        f"{_HORIZONTAL_RULE}"
        f"{files_section}"
        f"{_HORIZONTAL_RULE}"
        f"{deterministic_section}"
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


def _module_slug(pair: PromptPair) -> str:
    return pair.module_slug or _slugify(pair.title)


def _module_dir(run_dir: Path, pair: PromptPair) -> Path:
    return _run_files_dir(run_dir) / _module_slug(pair)


def _module_log_path(run_dir: Path, pair: PromptPair) -> Path:
    return _module_dir(run_dir, pair) / "module.log"


def _prompt_file_stem(pair: PromptPair) -> str:
    return f"prompt-{pair.index:02d}"


def _prompt_artifact_dir(run_dir: Path, pair: PromptPair) -> Path:
    return _module_dir(run_dir, pair)


def _prompt_history_dir(run_dir: Path, pair: PromptPair) -> Path:
    return _module_dir(run_dir, pair) / "history" / _prompt_file_stem(pair)


def _iteration_history_path(
    run_dir: Path,
    pair: PromptPair,
    iteration_number: int,
    *,
    validation: bool = False,
) -> Path:
    suffix = "-validation" if validation else ""
    return (
        _prompt_history_dir(run_dir, pair)
        / f"iter-{iteration_number:02d}{suffix}.md"
    )


def _append_log(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(content)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_files_dir(run_dir: Path) -> Path:
    return run_dir / RUN_FILES_DIRNAME


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        text=True,
        capture_output=True,
    )


def _git_is_worktree(path: Path) -> bool:
    try:
        proc = _git(["rev-parse", "--is-inside-work-tree"], cwd=path, check=False)
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _git_worktree_root(path: Path) -> Path | None:
    if not _git_is_worktree(path):
        return None
    proc = _git(["rev-parse", "--show-toplevel"], cwd=path)
    return Path(proc.stdout.strip()).resolve()


def _git_status_paths(
    worktree_dir: Path,
    extra_excluded_roots: tuple[Path, ...] = (),
) -> list[Path]:
    proc = _git(
        ["status", "--porcelain=v1", "--untracked-files=all", "-z"],
        cwd=worktree_dir,
    )
    raw_entries = [entry for entry in proc.stdout.split("\0") if entry]
    changed: list[Path] = []
    i = 0
    while i < len(raw_entries):
        entry = raw_entries[i]
        if len(entry) < 4:
            i += 1
            continue
        code = entry[:2]
        path_text = entry[3:]
        if code.startswith("R") or code.startswith("C"):
            i += 1
            if i >= len(raw_entries):
                break
            path_text = raw_entries[i]
        rel = Path(path_text)
        if _is_snapshot_excluded(rel, extra_excluded_roots):
            i += 1
            continue
        full = worktree_dir / rel
        if full.exists():
            changed.append(rel)
        i += 1
    return sorted(dict.fromkeys(changed))


def _git_has_changes(
    worktree_dir: Path,
    extra_excluded_roots: tuple[Path, ...] = (),
) -> bool:
    return bool(_git_status_paths(worktree_dir, extra_excluded_roots))


def _git_commit_prompt_changes(worktree_dir: Path, pair: PromptPair) -> None:
    _git(["add", "-A"], cwd=worktree_dir)
    proc = _git(["diff", "--cached", "--quiet"], cwd=worktree_dir, check=False)
    if proc.returncode == 0:
        return
    _git(
        [
            "-c", "user.name=prompt-runner",
            "-c", "user.email=prompt-runner@local",
            "commit",
            "--no-gpg-sign",
            "-m",
            f"prompt-runner: prompt {pair.index} {pair.title}",
        ],
        cwd=worktree_dir,
    )


def _git_restore_prompt_baseline(worktree_dir: Path) -> None:
    _git(["reset", "--hard", "HEAD"], cwd=worktree_dir)
    _git(["clean", "-fd"], cwd=worktree_dir)


def _using_git_change_tracking(worktree_dir: Path, run_dir: Path) -> bool:
    root = _git_worktree_root(worktree_dir)
    if root is None:
        return False
    git_entry = run_dir / ".git"
    return (
        git_entry.is_file()
        and root == worktree_dir.resolve() == run_dir.resolve()
    )


def _git_commit_current_state(worktree_dir: Path, message: str) -> None:
    _git(["add", "-A"], cwd=worktree_dir)
    proc = _git(["diff", "--cached", "--quiet"], cwd=worktree_dir, check=False)
    if proc.returncode == 0:
        return
    _git(
        [
            "-c", "user.name=prompt-runner",
            "-c", "user.email=prompt-runner@local",
            "commit",
            "--no-gpg-sign",
            "-m",
            message,
        ],
        cwd=worktree_dir,
    )


# Directory names that are always skipped when snapshotting or diffing the
# worktree. These are either the tool's own outputs (runs), dependency caches
# (.venv, node_modules), Python bytecode caches (__pycache__, .pytest_cache),
# version-control state (.git), or build artifacts.
_SNAPSHOT_SKIP_DIR_NAMES: frozenset[str] = frozenset({
    ".git",
    "runs",
    "tmp",
    ".methodology-runner",
    ".prompt-runner",
    ".run-files",
    "prompt-runner-files",
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


def _is_snapshot_excluded(
    rel_path: Path,
    extra_excluded_roots: tuple[Path, ...] = (),
) -> bool:
    """Return True if this relative path should be excluded from snapshot/diff."""
    for root in extra_excluded_roots:
        try:
            rel_path.relative_to(root)
            return True
        except ValueError:
            pass
    for part in rel_path.parts:
        if part in _SNAPSHOT_SKIP_DIR_NAMES:
            return True
        if part.endswith(".egg-info"):
            return True
        if part == ".DS_Store":
            return True
    return False


def _iter_worktree_files(
    worktree_dir: Path,
    extra_excluded_roots: tuple[Path, ...] = (),
):
    """Yield (relative_path, mtime_ns) for every non-excluded file in the worktree."""
    def _onerror(_: OSError) -> None:
        return

    for root, dirnames, filenames in os.walk(worktree_dir, topdown=True, onerror=_onerror):
        root_path = Path(root)
        try:
            rel_root = root_path.relative_to(worktree_dir)
        except ValueError:
            continue

        kept_dirs: list[str] = []
        for dirname in dirnames:
            rel_dir = rel_root / dirname if rel_root != Path(".") else Path(dirname)
            if _is_snapshot_excluded(rel_dir, extra_excluded_roots):
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in filenames:
            rel = rel_root / filename if rel_root != Path(".") else Path(filename)
            if _is_snapshot_excluded(rel, extra_excluded_roots):
                continue
            src = root_path / filename
            try:
                if src.is_symlink() or not src.is_file():
                    continue
                yield rel, src.stat().st_mtime_ns
            except (FileNotFoundError, OSError):
                continue


def _snapshot_worktree(
    worktree_dir: Path,
    dest_dir: Path,
    extra_excluded_roots: tuple[Path, ...] = (),
) -> None:
    """Copy every non-excluded file from worktree_dir into dest_dir.

    Used before each prompt so an escalated prompt can be rolled back by
    restoring from the snapshot. The dest_dir must not already exist (or if
    it does, it will be overlaid — caller is responsible for cleanup).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    for rel, _ in _iter_worktree_files(worktree_dir, extra_excluded_roots):
        src = worktree_dir / rel
        dest = dest_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def _diff_worktree_since_snapshot(
    worktree_dir: Path,
    snapshot_dir: Path,
    extra_excluded_roots: tuple[Path, ...] = (),
) -> list[Path]:
    """Return the list of relative paths that exist in worktree but differ
    from (or are missing from) the snapshot. These are the files the prompt
    created or modified."""
    snapshot_mtimes: dict[Path, int] = {}
    if snapshot_dir.exists():
        for rel, mtime in _iter_worktree_files(snapshot_dir, extra_excluded_roots):
            snapshot_mtimes[rel] = mtime
    changed: list[Path] = []
    for rel, mtime in _iter_worktree_files(worktree_dir, extra_excluded_roots):
        prev = snapshot_mtimes.get(rel)
        if prev is None or prev != mtime:
            changed.append(rel)
    return sorted(changed)


def _restore_worktree_from_snapshot(
    worktree_dir: Path,
    snapshot_dir: Path,
    extra_excluded_roots: tuple[Path, ...] = (),
) -> None:
    """Restore worktree_dir to match snapshot_dir exactly (within exclusions).

    1. Remove any file in worktree that is not in the snapshot (files the
       failed prompt added).
    2. Copy every file from snapshot back into worktree (overwrites files
       the failed prompt modified; recreates files the failed prompt may have
       deleted).
    """
    if not snapshot_dir.exists():
        return

    snapshot_rels: set[Path] = set()
    for rel, _ in _iter_worktree_files(snapshot_dir, extra_excluded_roots):
        snapshot_rels.add(rel)

    # Pass 1: remove files present in worktree but absent from snapshot.
    for rel, _ in list(_iter_worktree_files(worktree_dir, extra_excluded_roots)):
        if rel not in snapshot_rels:
            try:
                (worktree_dir / rel).unlink()
            except FileNotFoundError:
                pass

    # Pass 2: copy everything from snapshot back.
    for rel in snapshot_rels:
        src = snapshot_dir / rel
        dest = worktree_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def _excluded_run_roots(worktree_dir: Path, run_dir: Path) -> tuple[Path, ...]:
    if worktree_dir.resolve() == run_dir.resolve():
        return (Path(RUN_FILES_DIRNAME),)
    try:
        return (run_dir.resolve().relative_to(worktree_dir.resolve()),)
    except ValueError:
        return (Path(RUN_FILES_DIRNAME),)


def _ensure_run_files_gitignored(run_dir: Path) -> None:
    entry = f"{RUN_FILES_DIRNAME}/"
    if _git_is_worktree(run_dir):
        proc = _git(["rev-parse", "--git-path", "info/exclude"], cwd=run_dir)
        exclude_path = Path(proc.stdout.strip())
        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        existing = (
            exclude_path.read_text(encoding="utf-8").splitlines()
            if exclude_path.exists() else []
        )
        if entry in existing:
            return
        content = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
        suffix = "" if content.endswith("\n") or content == "" else "\n"
        _write(exclude_path, content + suffix + entry + "\n")
        return

    gitignore_path = run_dir / ".gitignore"
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8").splitlines()
        if entry in existing:
            return
        content = gitignore_path.read_text(encoding="utf-8")
        suffix = "" if content.endswith("\n") or content == "" else "\n"
        _write(gitignore_path, content + suffix + entry + "\n")
        return
    _write(gitignore_path, entry + "\n")


def _initial_copy_excluded_roots(
    project_dir: Path,
    run_dir: Path,
) -> tuple[Path, ...]:
    excluded: list[Path] = [Path(RUN_FILES_DIRNAME)]
    try:
        excluded.append(run_dir.resolve().relative_to(project_dir.resolve()))
    except ValueError:
        pass
    return tuple(excluded)


def _initialise_run_worktree(project_dir: Path, run_dir: Path) -> None:
    project_dir = project_dir.resolve()
    run_dir = run_dir.resolve()
    if project_dir == run_dir:
        _ensure_run_files_gitignored(run_dir)
        return

    existing_files = [p for p in run_dir.iterdir()] if run_dir.exists() else []
    if existing_files:
        _ensure_run_files_gitignored(run_dir)
        return

    git_root = _git_worktree_root(project_dir) if _git_is_worktree(project_dir) else None

    # Only use a linked git worktree when project_dir is itself the repository
    # root. If project_dir is a fixture subdirectory inside a larger repo, a
    # linked worktree would pull the whole repo into the run dir, including
    # unrelated baggage like old runs and docs. In that case, copy only the
    # requested subtree instead.
    if git_root is not None and git_root.resolve() == project_dir:
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        _git(["worktree", "prune"], cwd=project_dir, check=False)
        _git(["worktree", "add", "--detach", str(run_dir), "HEAD"], cwd=project_dir)
        excluded = _initial_copy_excluded_roots(project_dir, run_dir)
        _restore_worktree_from_snapshot(run_dir, project_dir, excluded)
        _git_commit_current_state(run_dir, "prompt-runner: baseline")
    else:
        run_dir.mkdir(parents=True, exist_ok=True)
        excluded = _initial_copy_excluded_roots(project_dir, run_dir)
        _snapshot_worktree(project_dir, run_dir, excluded)
    _ensure_run_files_gitignored(run_dir)


def _materialize_generator_artifact(
    *,
    backend: str,
    worktree_dir: Path,
    created_files: list[Path],
    generator_stdout: str,
) -> str:
    """Prefer on-disk artifact text for single-file Codex generations.

    Codex may end a file-writing turn with a short status message such as
    ``PASS`` or other commentary, even when it successfully wrote the real
    artifact to disk. For prompts that create exactly one text file, the file
    contents are the most faithful artifact to hand to the judge and to persist
    as the final artifact for later prompts.
    """
    if backend != "codex" or len(created_files) != 1:
        return generator_stdout
    target = worktree_dir / created_files[0]
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return generator_stdout


def _make_call(
    *,
    prompt: str,
    session_id: str,
    new_session: bool,
    model: str | None,
    effort: str | None = None,
    module_log_path: Path,
    iteration: int,
    role: str,
    pair: PromptPair,
    worktree_dir: Path,
    fork_session: bool = False,
    fork_from_session_id: str = "",
) -> ClaudeCall:
    return ClaudeCall(
        prompt=prompt,
        session_id=session_id,
        new_session=new_session,
        model=model,
        effort=effort,
        stdout_log_path=module_log_path,
        stderr_log_path=module_log_path,
        fork_session=fork_session,
        fork_from_session_id=fork_from_session_id,
        stream_header=(
            f"── prompt {pair.index} '{pair.title}' / iter {iteration} / {role} ──"
        ),
        worktree_dir=worktree_dir,
    )


def _run_interactive_prompt(
    pair: PromptPair,
    prior_artifacts: list[PriorArtifact],
    run_dir: Path,
    config: RunConfig,
    worktree_dir: Path,
) -> PromptResult:
    """Spawn the selected backend interactively with pair.generation_prompt.

    Inherits stdin/stdout/stderr so the user sees a real TTY session and
    can drive the agent directly. Waits for the subprocess to exit (human
    types /exit or Ctrl-C). Marks the prompt pass regardless of exit
    code — the human is the validator in interactive mode.
    """
    import subprocess

    from prompt_runner.verdict import Verdict

    prompt_slug = _prompt_dir_name(pair)
    run_files_dir = _run_files_dir(run_dir)
    prompt_dir = _prompt_artifact_dir(run_dir, pair)
    module_log_path = _module_log_path(run_dir, pair)
    prompt_dir.mkdir(parents=True, exist_ok=True)

    excluded_roots = _excluded_run_roots(worktree_dir, run_dir)
    snapshot_dir = prompt_dir / "snapshot-pre"
    use_git_tracking = _using_git_change_tracking(worktree_dir, run_dir)
    if not use_git_tracking:
        _snapshot_worktree(worktree_dir, snapshot_dir, excluded_roots)

    # Build the mission text: prior-artifact context + the pair's
    # generation prompt. We use the same message builder as the
    # non-interactive path so the user sees consistent context across
    # the two modes.
    mission = build_initial_generator_message(
        pair, prior_artifacts, generator_prelude=config.generator_prelude,
    )

    # Spawn the selected backend interactively. stdin/stdout/stderr inherit from this
    # process so the user sees a real TTY session. Wait for exit.
    if config.backend == "codex":
        state_root = run_files_dir / "backend-state" / "codex"
        log_dir = state_root / "log"
        sqlite_home = state_root / "sqlite"
        log_dir.mkdir(parents=True, exist_ok=True)
        sqlite_home.mkdir(parents=True, exist_ok=True)
        argv = ["codex"]
        argv.extend([
            "-c", f'projects."{worktree_dir}".trust_level="trusted"',
            "-c", 'approval_policy="never"',
            "-c", 'history.persistence="none"',
            "-c", 'sandbox_mode="danger-full-access"',
            "-c", f'log_dir="{log_dir}"',
            "-c", f'sqlite_home="{sqlite_home}"',
        ])
    else:
        argv = ["claude"]
        if config.dangerously_skip_permissions:
            argv.append("--dangerously-skip-permissions")
    if config.model:
        argv.extend(["--model", config.model])
    argv.append(mission)

    print(
        f"\n{'=' * 70}\n"
        f"-- prompt {pair.index} '{pair.title}' / INTERACTIVE --\n"
        f"{'=' * 70}\n"
        f"Spawning {config.backend} interactively. When done, type /exit or Ctrl-C\n"
        f"to return control to prompt-runner.\n"
        f"{'=' * 70}\n",
        flush=True,
    )

    process_meta_path = prompt_dir / f"{prompt_slug}.interactive-process.json"
    proc = subprocess.Popen(argv, cwd=worktree_dir)
    write_spawn_metadata(
        process_meta_path,
        kind="interactive-backend-call",
        pid=proc.pid,
        argv=argv,
        cwd=worktree_dir,
    )
    exit_code = proc.wait()
    mark_process_completed(process_meta_path, returncode=exit_code)

    # Capture files the session created
    created_files = (
        _git_status_paths(worktree_dir, excluded_roots)
        if use_git_tracking else
        _diff_worktree_since_snapshot(worktree_dir, snapshot_dir, excluded_roots)
    )
    if use_git_tracking and _git_has_changes(worktree_dir, excluded_roots):
        _git_commit_prompt_changes(worktree_dir, pair)

    # Write artifact stubs so downstream resume logic can see the pair completed.
    # There is no generator text to capture (stdio was inherited), so the
    # artifact file records the fact that this was an interactive session.
    artifact_stub = (
        f"[interactive prompt -- stdio inherited, no captured output]\n"
        f"Mission: {pair.title}\n"
        f"Exit code: {exit_code}\n"
    )
    _append_log(
        module_log_path,
        f"\n=== interactive prompt {pair.index}: {pair.title} ===\n"
        f"exit_code={exit_code}\n",
    )
    _write(prompt_dir / f"{prompt_slug}.final-artifact.md", artifact_stub)
    _write(prompt_dir / f"{prompt_slug}.final-verdict.txt", Verdict.PASS.value + "\n")
    _write(
        prompt_dir / f"{prompt_slug}.files-created.txt",
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
    worktree_dir: Path,
    pipeline_started_at: datetime | None = None,
) -> PromptResult:
    if pair.interactive:
        return _run_interactive_prompt(
            pair, prior_artifacts, run_dir, config, worktree_dir,
        )
    if config.judge_only == pair.index:
        return _run_judge_only_prompt(
            pair=pair,
            run_dir=run_dir,
            config=config,
            claude_client=claude_client,
            run_id=run_id,
            worktree_dir=worktree_dir,
            pipeline_started_at=pipeline_started_at,
        )
    if config.max_iterations < 1:
        raise ValueError(
            f"max_iterations must be >= 1, got {config.max_iterations}"
        )
    gen_session = _session_id(f"gen-prompt-{pair.index}-{run_id}")
    jud_session = _session_id(f"jud-prompt-{pair.index}-{run_id}")
    prompt_slug = _prompt_dir_name(pair)
    prompt_dir = _prompt_artifact_dir(run_dir, pair)
    module_log_path = _module_log_path(run_dir, pair)
    prompt_dir.mkdir(parents=True, exist_ok=True)
    excluded_roots = _excluded_run_roots(worktree_dir, run_dir)
    snapshot_dir = prompt_dir / "snapshot-pre"
    use_git_tracking = _using_git_change_tracking(worktree_dir, run_dir)

    # Snapshot the worktree before the prompt runs so we can roll back to
    # this state if the prompt escalates. Also lets us diff at the end to
    # find out which files the prompt's generator created.
    if not use_git_tracking:
        _snapshot_worktree(worktree_dir, snapshot_dir, excluded_roots)

    iterations: list[IterationResult] = []
    gen_response: ClaudeResponse | None = None
    stateless_revisions = config.backend == "codex"
    progress_started_at = pipeline_started_at or datetime.now(timezone.utc)

    _emit_progress(
        f"{_progress_prefix(progress_started_at)} "
        f"prompt {pair.index}/{pair.title} start"
    )

    for iteration_number in range(1, config.max_iterations + 1):
        is_first = iteration_number == 1

        gen_msg = (
            build_initial_generator_message(
                pair, prior_artifacts,
                generator_prelude=config.generator_prelude,
                include_project_organiser=config.include_project_organiser,
            )
            if is_first
            else build_revision_generator_message(
                iterations[-1].judge_output,
                generator_prelude=config.generator_prelude,
                original_task=pair.generation_prompt if stateless_revisions else None,
                previous_artifact=(
                    iterations[-1].generator_output if stateless_revisions else None
                ),
                include_project_organiser=config.include_project_organiser,
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
        _emit_progress(
            f"{_progress_prefix(progress_started_at)} "
            f"prompt {pair.index} iter {iteration_number} generator start"
        )
        _append_log(
            module_log_path,
            f"\n=== generator prompt {pair.index} iter {iteration_number} start ===\n",
        )
        gen_call = _make_call(
            prompt=gen_msg,
            session_id=fork_new_session,
            new_session=(is_first and not use_fork) or stateless_revisions,
            model=pair.model_override or config.model,
            effort=pair.effort_override,
            module_log_path=module_log_path,
            iteration=iteration_number,
            role="generator",
            pair=pair,
            worktree_dir=worktree_dir,
            fork_session=use_fork,
            fork_from_session_id=config.fork_from_session if use_fork else "",
        )
        gen_response = _call_or_persist_partial(
            claude_client,
            gen_call,
            _iteration_history_path(run_dir, pair, iteration_number),
        )
        _emit_progress(
            f"{_progress_prefix(progress_started_at)} "
            f"prompt {pair.index} iter {iteration_number} generator done"
        )
        _append_log(
            module_log_path,
            f"\n=== generator prompt {pair.index} iter {iteration_number} end ===\n",
        )

        # Diff the worktree against the pre-prompt snapshot to find which
        # files the generator has touched so far. Pass this list to the
        # judge so it knows exactly which files to inspect, rather than
        # having to discover them via Glob.
        files_so_far = (
            _git_status_paths(worktree_dir, excluded_roots)
            if use_git_tracking else
            _diff_worktree_since_snapshot(worktree_dir, snapshot_dir, excluded_roots)
        )
        artifact_text = _materialize_generator_artifact(
            backend=config.backend,
            worktree_dir=worktree_dir,
            created_files=files_so_far,
            generator_stdout=gen_response.stdout,
        )
        deterministic_validation = _run_deterministic_validation(
            pair=pair,
            prompt_dir=prompt_dir,
            module_log_path=module_log_path,
            worktree_dir=worktree_dir,
            iteration_number=iteration_number,
        )
        if (
            deterministic_validation is not None
            and deterministic_validation.returncode not in (0, 1)
        ):
            raise DeterministicValidationError(
                "R-DETERMINISTIC-VALIDATION-FAILED: "
                f"prompt {pair.index} \"{pair.title}\" deterministic "
                f"validation returned {deterministic_validation.returncode}. "
                f"See {deterministic_validation.stdout_log_path} and "
                f"{deterministic_validation.stderr_log_path}."
            )

        if not pair.validation_prompt:
            # Validator-less prompt: accept the generator's output without a
            # judge call. Mark the iteration as pass so the loop exits.
            iterations.append(
                IterationResult(
                    iteration=iteration_number,
                    generator_output=artifact_text,
                    judge_output="",  # no judge call
                    verdict=Verdict.PASS,
                )
            )
            _emit_progress(
                f"{_progress_prefix(progress_started_at)} "
                f"prompt {pair.index} iter {iteration_number} verdict pass"
            )
            break

        _emit_progress(
            f"{_progress_prefix(progress_started_at)} "
            f"prompt {pair.index} iter {iteration_number} judge start"
        )
        _append_log(
            module_log_path,
            f"\n=== validation prompt {pair.index} iter {iteration_number} start ===\n",
        )
        jud_msg = (
            build_initial_judge_message(
                pair, artifact_text, files_so_far,
                deterministic_validation=deterministic_validation,
                judge_prelude=config.judge_prelude,
            )
            if is_first
            else build_revision_judge_message(
                artifact_text, files_so_far,
                deterministic_validation=deterministic_validation,
                judge_prelude=config.judge_prelude,
                validation_prompt=(
                    pair.validation_prompt if stateless_revisions else None
                ),
            )
        )
        jud_call = _make_call(
            prompt=jud_msg,
            session_id=jud_session,
            new_session=is_first or stateless_revisions,
            model=pair.model_override or config.model,
            effort=pair.effort_override,
            module_log_path=module_log_path,
            iteration=iteration_number,
            role="judge",
            pair=pair,
            worktree_dir=worktree_dir,
        )
        jud_response = _call_or_persist_partial(
            claude_client,
            jud_call,
            _iteration_history_path(
                run_dir, pair, iteration_number, validation=True,
            ),
        )
        _emit_progress(
            f"{_progress_prefix(progress_started_at)} "
            f"prompt {pair.index} iter {iteration_number} judge done"
        )
        _append_log(
            module_log_path,
            f"\n=== validation prompt {pair.index} iter {iteration_number} end ===\n",
        )

        verdict = parse_verdict(jud_response.stdout)
        iterations.append(
                IterationResult(
                    iteration=iteration_number,
                    generator_output=artifact_text,
                    judge_output=jud_response.stdout,
                    verdict=verdict,
                )
        )
        _emit_progress(
            f"{_progress_prefix(progress_started_at)} "
            f"prompt {pair.index} iter {iteration_number} verdict {verdict.value}"
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
        # preserve the worktree state (do not restore).
        created_files = (
            _git_status_paths(worktree_dir, excluded_roots)
            if use_git_tracking else
            _diff_worktree_since_snapshot(worktree_dir, snapshot_dir, excluded_roots)
        )
        if use_git_tracking and _git_has_changes(worktree_dir, excluded_roots):
            _git_commit_prompt_changes(worktree_dir, pair)
    else:
        # Escalation — roll back the worktree so a half-done prompt does
        # not pollute later prompts or leave garbage in the tree.
        if use_git_tracking:
            _git_restore_prompt_baseline(worktree_dir)
        else:
            _restore_worktree_from_snapshot(
                worktree_dir, snapshot_dir, excluded_roots,
            )
        created_files = []

    _write(prompt_dir / f"{prompt_slug}.final-artifact.md", final.generator_output)
    _write(prompt_dir / f"{prompt_slug}.final-verdict.txt", final_verdict.value + "\n")
    _write(
        prompt_dir / f"{prompt_slug}.files-created.txt",
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


def _next_judge_only_iteration_number(run_dir: Path, pair: PromptPair) -> int:
    history_dir = _prompt_artifact_dir(run_dir, pair) / "history" / f"prompt-{pair.index:02d}"
    if not history_dir.exists():
        return 1
    numbers: list[int] = []
    for path in history_dir.glob("iter-*-validation.md"):
        match = re.match(r"iter-(\d+)-validation\.md$", path.name)
        if match:
            numbers.append(int(match.group(1)))
    if not numbers:
        return 1
    return max(numbers) + 1


def _load_saved_prompt_state(
    pair: PromptPair,
    run_dir: Path,
) -> tuple[str, list[Path]]:
    prompt_slug = _prompt_dir_name(pair)
    prompt_dir = _prompt_artifact_dir(run_dir, pair)
    artifact_path = prompt_dir / f"{prompt_slug}.final-artifact.md"
    files_path = prompt_dir / f"{prompt_slug}.files-created.txt"
    if not artifact_path.exists() or not files_path.exists():
        raise FileNotFoundError(
            f"prompt {pair.index} judge-only requires existing saved prompt state: "
            f"{artifact_path} and {files_path}"
        )
    artifact_text = artifact_path.read_text(encoding="utf-8")
    files = [Path(line) for line in files_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return artifact_text, files


def _run_judge_only_prompt(
    *,
    pair: PromptPair,
    run_dir: Path,
    config: RunConfig,
    claude_client: ClaudeClient,
    run_id: str,
    worktree_dir: Path,
    pipeline_started_at: datetime | None = None,
) -> PromptResult:
    if not pair.validation_prompt:
        raise ValueError(
            f"judge-only requires a validation prompt, but prompt {pair.index} has none"
        )
    jud_session = _session_id(f"jud-prompt-{pair.index}-{run_id}")
    prompt_slug = _prompt_dir_name(pair)
    prompt_dir = _prompt_artifact_dir(run_dir, pair)
    module_log_path = _module_log_path(run_dir, pair)
    prompt_dir.mkdir(parents=True, exist_ok=True)
    artifact_text, created_files = _load_saved_prompt_state(pair, run_dir)
    iteration_number = _next_judge_only_iteration_number(run_dir, pair)
    progress_started_at = pipeline_started_at or datetime.now(timezone.utc)

    _emit_progress(
        f"{_progress_prefix(progress_started_at)} "
        f"prompt {pair.index}/{pair.title} judge-only start"
    )

    deterministic_validation = _run_deterministic_validation(
        pair=pair,
        prompt_dir=prompt_dir,
        module_log_path=module_log_path,
        worktree_dir=worktree_dir,
        iteration_number=iteration_number,
    )
    if (
        deterministic_validation is not None
        and deterministic_validation.returncode not in (0, 1)
    ):
        raise DeterministicValidationError(
            "R-DETERMINISTIC-VALIDATION-FAILED: "
            f"prompt {pair.index} \"{pair.title}\" deterministic "
            f"validation returned {deterministic_validation.returncode}. "
            f"See {deterministic_validation.stdout_log_path} and "
            f"{deterministic_validation.stderr_log_path}."
        )

    _emit_progress(
        f"{_progress_prefix(progress_started_at)} "
        f"prompt {pair.index} iter {iteration_number} judge start"
    )
    _append_log(
        module_log_path,
        f"\n=== validation prompt {pair.index} iter {iteration_number} judge-only start ===\n",
    )
    jud_msg = build_initial_judge_message(
        pair,
        artifact_text,
        created_files,
        deterministic_validation=deterministic_validation,
        judge_prelude=config.judge_prelude,
    )
    jud_call = _make_call(
        prompt=jud_msg,
        session_id=jud_session,
        new_session=True,
        model=pair.model_override or config.model,
        effort=pair.effort_override,
        module_log_path=module_log_path,
        iteration=iteration_number,
        role="judge",
        pair=pair,
        worktree_dir=worktree_dir,
    )
    jud_response = _call_or_persist_partial(
        claude_client,
        jud_call,
        _iteration_history_path(run_dir, pair, iteration_number, validation=True),
    )
    _emit_progress(
        f"{_progress_prefix(progress_started_at)} "
        f"prompt {pair.index} iter {iteration_number} judge done"
    )
    _append_log(
        module_log_path,
        f"\n=== validation prompt {pair.index} iter {iteration_number} judge-only end ===\n",
    )
    verdict = parse_verdict(jud_response.stdout)
    _emit_progress(
        f"{_progress_prefix(progress_started_at)} "
        f"prompt {pair.index} iter {iteration_number} verdict {verdict.value}"
    )
    _write(prompt_dir / f"{prompt_slug}.final-artifact.md", artifact_text)
    _write(prompt_dir / f"{prompt_slug}.final-verdict.txt", verdict.value + "\n")
    _write(
        prompt_dir / f"{prompt_slug}.files-created.txt",
        "\n".join(str(p) for p in created_files) + ("\n" if created_files else ""),
    )
    return PromptResult(
        pair=pair,
        iterations=[
            IterationResult(
                iteration=iteration_number,
                generator_output=artifact_text,
                judge_output=jud_response.stdout,
                verdict=verdict,
            )
        ],
        final_verdict=verdict,
        final_artifact=artifact_text,
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


def _load_prior_artifact_from_disk(
    pair: PromptPair, run_dir: Path,
) -> PriorArtifact:
    """Reconstruct a PriorArtifact for a completed prompt from its on-disk
    final-artifact and files-created files. Used by --resume to rebuild the
    prior-artifact context for prompts that were already completed in a
    previous run."""
    prompt_slug = _prompt_dir_name(pair)
    prompt_dir = _prompt_artifact_dir(run_dir, pair)
    text_body = (prompt_dir / f"{prompt_slug}.final-artifact.md").read_text(encoding="utf-8")
    files_txt = (prompt_dir / f"{prompt_slug}.files-created.txt").read_text(encoding="utf-8")
    files = [
        Path(line) for line in files_txt.splitlines() if line.strip()
    ]
    return PriorArtifact(
        title=pair.title,
        text_body=text_body,
        files=files,
    )


def _resolve_required_file(path_text: str, worktree_dir: Path) -> Path:
    candidate = Path(path_text)
    if candidate.is_absolute():
        worktree_prefix = str(worktree_dir.resolve())
        raw = str(candidate)
        if raw.startswith(worktree_prefix + os.sep):
            tail = raw[len(worktree_prefix):]
            tail_path = Path(tail)
            # Repair only the specific duplicated-prefix case:
            #   <worktree>/<absolute-path>
            # when the stripped absolute tail is itself a real path. Do not
            # rewrite ordinary absolute paths that legitimately live under the
            # worktree, such as <worktree>/docs/request.md>.
            if tail_path.is_absolute() and tail_path.exists():
                return tail_path
        return candidate
    return (worktree_dir / candidate).resolve()


def _resolve_deterministic_validation_script(
    pair: PromptPair,
    worktree_dir: Path,
) -> Path | None:
    if not pair.deterministic_validation:
        return None
    return _resolve_required_file(pair.deterministic_validation[0], worktree_dir)


def _missing_required_files(pair: PromptPair, worktree_dir: Path) -> list[Path]:
    missing: list[Path] = []
    for raw_path in pair.required_files:
        resolved = _resolve_required_file(raw_path, worktree_dir)
        if not resolved.exists():
            missing.append(resolved)
    return missing


_PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")


def _placeholder_context(
    run_dir: Path,
    worktree_dir: Path,
    config: RunConfig,
) -> dict[str, str]:
    context = dict(config.placeholder_values)
    context["run_dir"] = str(run_dir.resolve())
    context["project_dir"] = str(worktree_dir.resolve())
    return context


def _render_placeholders(text: str, context: dict[str, str]) -> str:
    rendered = text
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _render_prompt_pair(pair: PromptPair, context: dict[str, str]) -> PromptPair:
    return PromptPair(
        index=pair.index,
        title=_render_placeholders(pair.title, context),
        generation_prompt=_render_placeholders(pair.generation_prompt, context),
        validation_prompt=_render_placeholders(pair.validation_prompt, context),
        heading_line=pair.heading_line,
        generation_line=pair.generation_line,
        validation_line=pair.validation_line,
        required_files=tuple(
            _render_placeholders(path, context) for path in pair.required_files
        ),
        checks_files=tuple(
            _render_placeholders(path, context) for path in pair.checks_files
        ),
        deterministic_validation=tuple(
            _render_placeholders(value, context)
            for value in pair.deterministic_validation
        ),
        module_slug=(
            _render_placeholders(pair.module_slug, context)
            if pair.module_slug is not None
            else None
        ),
        interactive=pair.interactive,
        model_override=pair.model_override,
        effort_override=pair.effort_override,
    )


def _pair_unresolved_placeholders(pair: PromptPair) -> list[str]:
    names: set[str] = set()
    text_fields = [
        pair.title,
        pair.generation_prompt,
        pair.validation_prompt,
        *pair.required_files,
        *pair.checks_files,
        *pair.deterministic_validation,
    ]
    for text in text_fields:
        names.update(_PLACEHOLDER_RE.findall(text))
    return sorted(names)


def _optional_file_checks(pair: PromptPair, worktree_dir: Path) -> list[dict[str, str | bool]]:
    checks: list[dict[str, str | bool]] = []
    for raw_path in pair.checks_files:
        resolved = _resolve_required_file(raw_path, worktree_dir)
        checks.append(
            {
                "path": raw_path,
                "resolved_path": str(resolved),
                "exists": resolved.exists(),
            }
        )
    return checks


def _write_optional_file_checks_trace(
    run_dir: Path,
    pair: PromptPair,
    worktree_dir: Path,
) -> None:
    if not pair.checks_files:
        return
    checks = _optional_file_checks(pair, worktree_dir)
    _append_log(
        _module_log_path(run_dir, pair),
        "\n=== checks files ===\n"
        f"{json.dumps(checks, indent=2)}\n"
        "=== checks files end ===\n",
    )


def _run_deterministic_validation(
    *,
    pair: PromptPair,
    prompt_dir: Path,
    module_log_path: Path,
    worktree_dir: Path,
    iteration_number: int,
) -> DeterministicValidationResult | None:
    if not pair.deterministic_validation:
        return None
    script_path = _resolve_deterministic_validation_script(pair, worktree_dir)
    assert script_path is not None
    argv = [
        sys.executable,
        str(script_path),
        *pair.deterministic_validation[1:],
    ]
    stdout_log_path = module_log_path
    stderr_log_path = module_log_path
    process_metadata_path = (
        prompt_dir / f"prompt-{pair.index:02d}.iter-{iteration_number:02d}-deterministic-validation.proc.json"
    )
    env = os.environ.copy()
    env.update(
        {
            "PROMPT_RUNNER_WORKTREE_DIR": str(worktree_dir.resolve()),
            "PROMPT_RUNNER_PROMPT_DIR": str(prompt_dir.resolve()),
            "PROMPT_RUNNER_PROMPT_INDEX": str(pair.index),
            "PROMPT_RUNNER_PROMPT_TITLE": pair.title,
            "PROMPT_RUNNER_ITERATION": str(iteration_number),
        }
    )
    proc = subprocess.Popen(
        argv,
        cwd=worktree_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    write_spawn_metadata(
        process_metadata_path,
        kind="deterministic-validation",
        pid=proc.pid,
        argv=argv,
        cwd=worktree_dir,
    )
    _append_log(
        module_log_path,
        f"\n=== deterministic validation prompt {pair.index} iter {iteration_number} start ===\n"
        f"command: {' '.join(argv)}\n",
    )
    stdout, stderr = proc.communicate()
    mark_process_completed(process_metadata_path, returncode=proc.returncode)
    _append_log(
        module_log_path,
        f"exit_code: {proc.returncode}\n"
        f"stdout:\n{stdout if stdout.endswith(chr(10)) or not stdout else stdout + chr(10)}"
        f"stderr:\n{stderr if stderr.endswith(chr(10)) or not stderr else stderr + chr(10)}"
        f"=== deterministic validation prompt {pair.index} iter {iteration_number} end ===\n",
    )
    return DeterministicValidationResult(
        command=argv,
        script_path=script_path,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
        process_metadata_path=process_metadata_path,
    )


def _serialize_pairs_to_md(pairs: list[PromptPair]) -> str:
    """Convert PromptPair objects back to heading-based prompt-runner markdown."""
    sections: list[str] = []
    for pair in pairs:
        heading = f"## Prompt {pair.index}: {pair.title}"
        if pair.model_override:
            heading += f" [MODEL:{pair.model_override}]"
        if pair.effort_override:
            heading += f" [EFFORT:{pair.effort_override}]"
        lines: list[str] = [heading, ""]
        if pair.module_slug:
            lines.append("### Module")
            lines.append("")
            lines.append(pair.module_slug)
            lines.append("")
        if pair.required_files:
            lines.append("### Required Files")
            lines.append("")
            lines.extend(pair.required_files)
            lines.append("")
        if pair.checks_files:
            lines.append("### Checks Files")
            lines.append("")
            lines.extend(pair.checks_files)
            lines.append("")
        if pair.deterministic_validation:
            lines.append("### Deterministic Validation")
            lines.append("")
            lines.extend(pair.deterministic_validation)
            lines.append("")
        lines.append("### Generation Prompt")
        lines.append("")
        lines.append(pair.generation_prompt)
        if pair.validation_prompt:
            lines.append("")
            lines.append("### Validation Prompt")
            lines.append("")
            lines.append(pair.validation_prompt)
        sections.append("\n".join(lines))
    return "\n\n".join(sections) + "\n"


def _copy_worktree_for_variant(src_workspace: Path, dest_workspace: Path) -> None:
    """Copy a worktree directory to a new location, excluding build/cache dirs.

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
    worktree_dir: Path,
    config: RunConfig,
    source_file: Path,
    fork_from_session: str = "",
) -> ForkResult:
    """Execute all variants of a fork point and return their aggregated results.

    For each variant:
    1. Copy the current worktree into a per-variant directory.
    2. Build a synthetic prompt file (variant pairs + items_after).
    3. Spawn a prompt-runner subprocess.
    4. Collect results.
    """
    fork_slug = f"fork-{fork.index:02d}-{_slugify(fork.title)}"
    run_files_dir = _run_files_dir(run_dir)
    fork_dir = run_files_dir / fork_slug
    fork_dir.mkdir(parents=True, exist_ok=True)

    procs: list[tuple[VariantPrompt, Path, subprocess.Popen[bytes]]] = []

    for variant in fork.variants:
        variant_slug = f"variant-{_slugify(variant.variant_name)}"
        variant_run_dir = fork_dir / variant_slug

        # Copy the worktree into the variant directory.
        _copy_worktree_for_variant(worktree_dir, variant_run_dir)
        _ensure_run_files_gitignored(variant_run_dir)

        # Build a synthetic prompt list: variant pairs + all subsequent items.
        # Only PromptPair items from items_after are serialised (ForkPoints
        # in the tail are not yet supported for recursive nesting; they will
        # be ignored in serialisation for now).
        tail_pairs: list[PromptPair] = [
            item for item in items_after if isinstance(item, PromptPair)
        ]
        synthetic_pairs = list(variant.pairs) + tail_pairs
        synthetic_md = _serialize_pairs_to_md(synthetic_pairs)

        temp_md_path = _run_files_dir(variant_run_dir) / "synthetic-prompt.md"
        _write(temp_md_path, synthetic_md)
        cmd: list[str] = [
            sys.executable, "-m", "prompt_runner",
            "run", str(temp_md_path),
            "--run-dir", str(variant_run_dir),
            "--backend", config.backend,
        ]
        for key, value in config.placeholder_values.items():
            cmd.extend(["--var", f"{key}={value}"])
        if config.model:
            cmd.extend(["--model", config.model])
        if config.generator_prelude:
            prelude_path = _run_files_dir(variant_run_dir) / "generator-prelude.txt"
            _write(prelude_path, config.generator_prelude)
            cmd.extend(["--generator-prelude", str(prelude_path)])
        if config.judge_prelude:
            prelude_path = _run_files_dir(variant_run_dir) / "judge-prelude.txt"
            _write(prelude_path, config.judge_prelude)
            cmd.extend(["--judge-prelude", str(prelude_path)])
        if fork_from_session:
            cmd.extend(["--fork-from-session", fork_from_session])

        print(
            f"[fork {fork.index}] spawning variant '{variant.variant_name}' "
            f"({variant.variant_title}) → {variant_run_dir}",
            flush=True,
        )

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        write_spawn_metadata(
            _run_files_dir(variant_run_dir) / "child-process.json",
            kind="variant-run",
            pid=proc.pid,
            argv=[str(part) for part in cmd],
            cwd=variant_run_dir,
        )
        procs.append((variant, variant_run_dir, proc))

        if config.variant_sequential:
            proc.wait()

    # Wait for all subprocesses.
    variant_results: list[VariantResult] = []
    for variant, variant_run_dir, proc in procs:
        proc.wait()
        exit_code = proc.returncode
        mark_process_completed(
            _run_files_dir(variant_run_dir) / "child-process.json",
            returncode=exit_code,
        )
        summary_path = _run_files_dir(variant_run_dir) / "summary.txt"
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
            worktree_dir=variant_run_dir,
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
        comparison_lines.append(f"    worktree : {vr.worktree_dir}")

        # Summary excerpt (first 3 lines).
        summary_lines = [ln for ln in vr.summary.splitlines() if ln.strip()][:3]
        if summary_lines:
            comparison_lines.append("    summary   :")
            for ln in summary_lines:
                comparison_lines.append(f"      {ln}")

        # Files created in the variant worktree.
        if vr.worktree_dir.exists():
            ws_files = sorted(
                str(p.relative_to(vr.worktree_dir))
                for p in vr.worktree_dir.rglob("*")
                if p.is_file()
            )
            if ws_files:
                comparison_lines.append(f"    worktree files ({len(ws_files)}):")
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
    source_project_dir: Path | None = None,
    worktree_dir: Path | None = None,
    resume: bool = False,
) -> PipelineResult:
    run_dir = run_dir.resolve()
    run_id = run_dir.name
    run_dir.mkdir(parents=True, exist_ok=True)
    if source_project_dir is None and worktree_dir is not None:
        source_project_dir = worktree_dir
    if source_project_dir is None:
        source_project_dir = run_dir
    else:
        source_project_dir = Path(source_project_dir).resolve()
    worktree_dir = run_dir
    if not resume:
        _initialise_run_worktree(source_project_dir, run_dir)
    started_at = datetime.now(timezone.utc)
    if not resume:
        _write_manifest(run_dir, source_file, config, run_id,
                        started_at=_format_iso(started_at))
    _emit_progress(
        f"{_progress_prefix(started_at)} "
        f"run start {run_id} backend={config.backend}"
    )

    prior_artifacts: list[PriorArtifact] = []
    prompt_results: list[PromptResult] = []
    fork_results: list[ForkResult] = []
    last_session_id: str = ""  # for fork context inheritance
    placeholder_context = _placeholder_context(run_dir, worktree_dir, config)

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
                worktree_dir=worktree_dir,
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
        rendered_pair = _render_prompt_pair(pair, placeholder_context)

        if config.only is not None and rendered_pair.index != config.only:
            continue

        unresolved_placeholders = _pair_unresolved_placeholders(rendered_pair)
        if unresolved_placeholders:
            halt_reason = (
                f'R-UNRESOLVED-PLACEHOLDERS: prompt {rendered_pair.index} '
                f'"{rendered_pair.title}" has unresolved placeholders: '
                + ", ".join(unresolved_placeholders)
            )
            _emit_progress(
                f"{_progress_prefix(started_at)} "
                f"run halt R-UNRESOLVED-PLACEHOLDERS prompt {rendered_pair.index}"
            )
            _finalise(
                run_dir,
                source_file,
                config,
                run_id,
                pairs,
                prompt_results,
                started_at=started_at,
                halted_early=True,
                halt_reason=halt_reason,
            )
            return PipelineResult(
                prompt_results,
                halted_early=True,
                halt_reason=halt_reason,
            )

        if still_skipping:
            if config.judge_only == rendered_pair.index:
                still_skipping = False
            else:
                prompt_slug = _prompt_dir_name(rendered_pair)
                prompt_dir = _prompt_artifact_dir(run_dir, rendered_pair)
                verdict_path = prompt_dir / f"{prompt_slug}.final-verdict.txt"
                if verdict_path.exists() and verdict_path.read_text(encoding="utf-8").splitlines()[0] == "pass":
                    # This prompt already completed with pass — skip it.
                    prior_artifact = _load_prior_artifact_from_disk(rendered_pair, run_dir)
                    text_body = (prompt_dir / f"{prompt_slug}.final-artifact.md").read_text(encoding="utf-8")
                    files_txt = (prompt_dir / f"{prompt_slug}.files-created.txt").read_text(encoding="utf-8")
                    created_files = [
                        Path(line) for line in files_txt.splitlines() if line.strip()
                    ]
                    synthetic_result = PromptResult(
                        pair=rendered_pair,
                        iterations=[],
                        final_verdict=Verdict.PASS,
                        final_artifact=text_body,
                        created_files=created_files,
                    )
                    prompt_results.append(synthetic_result)
                    prior_artifacts.append(prior_artifact)
                    print(
                        f"[resume] skipping prompt {rendered_pair.index} '{rendered_pair.title}' — already pass",
                        flush=True,
                    )
                    _emit_progress(
                        f"{_progress_prefix(started_at)} "
                        f"prompt {rendered_pair.index} resume-skip pass"
                    )
                    continue
                else:
                    # First incomplete prompt — stop skipping from here on.
                    still_skipping = False

        prompt_dir = _prompt_artifact_dir(run_dir, rendered_pair)
        prompt_dir.mkdir(parents=True, exist_ok=True)
        _write_optional_file_checks_trace(run_dir, rendered_pair, worktree_dir)

        missing_required = _missing_required_files(rendered_pair, worktree_dir)
        if missing_required:
            missing_lines = "\n".join(f"- {path}" for path in missing_required)
            halt_reason = (
                f"R-MISSING-REQUIRED-FILES: prompt {rendered_pair.index} \"{rendered_pair.title}\" "
                f"is missing required files:\n{missing_lines}"
            )
            _emit_progress(
                f"{_progress_prefix(started_at)} "
                f"run halt R-MISSING-REQUIRED-FILES prompt {rendered_pair.index}"
            )
            _finalise(
                run_dir,
                source_file,
                config,
                run_id,
                pairs,
                prompt_results,
                started_at=started_at,
                halted_early=True,
                halt_reason=halt_reason,
            )
            return PipelineResult(
                prompt_results,
                halted_early=True,
                halt_reason=halt_reason,
            )
        deterministic_script = _resolve_deterministic_validation_script(
            rendered_pair,
            worktree_dir,
        )
        if deterministic_script is not None and not deterministic_script.exists():
            halt_reason = (
                f"R-MISSING-DETERMINISTIC-VALIDATION: prompt {rendered_pair.index} "
                f"\"{rendered_pair.title}\" is missing deterministic validation "
                f"script:\n- {deterministic_script}"
            )
            _emit_progress(
                f"{_progress_prefix(started_at)} "
                f"run halt R-MISSING-DETERMINISTIC-VALIDATION prompt "
                f"{rendered_pair.index}"
            )
            _finalise(
                run_dir,
                source_file,
                config,
                run_id,
                pairs,
                prompt_results,
                started_at=started_at,
                halted_early=True,
                halt_reason=halt_reason,
            )
            return PipelineResult(
                prompt_results,
                halted_early=True,
                halt_reason=halt_reason,
            )

        try:
            result = run_prompt(
                rendered_pair, prior_artifacts, run_dir, config, claude_client,
                run_id, worktree_dir, started_at,
            )
        except VerdictParseError as err:
            halt_reason = (
                f"R-NO-VERDICT: prompt {rendered_pair.index} \"{rendered_pair.title}\" "
                f"returned a judge response with no VERDICT line. {err}"
            )
            _emit_progress(
                f"{_progress_prefix(started_at)} "
                f"run halt {halt_reason}"
            )
            _finalise(run_dir, source_file, config, run_id, pairs, prompt_results,
                      started_at=started_at, halted_early=True,
                      halt_reason=halt_reason)
            return PipelineResult(prompt_results, halted_early=True, halt_reason=halt_reason)
        except ClaudeInvocationError as err:
            halt_reason = _format_claude_failed_halt_reason(rendered_pair, err, run_dir)
            _emit_progress(
                f"{_progress_prefix(started_at)} "
                f"run halt R-CLAUDE-FAILED prompt {rendered_pair.index}"
            )
            _finalise(run_dir, source_file, config, run_id, pairs, prompt_results,
                      started_at=started_at, halted_early=True,
                      halt_reason=halt_reason)
            return PipelineResult(prompt_results, halted_early=True, halt_reason=halt_reason)
        except DeterministicValidationError as err:
            halt_reason = str(err)
            _emit_progress(
                f"{_progress_prefix(started_at)} "
                f"run halt R-DETERMINISTIC-VALIDATION-FAILED prompt "
                f"{rendered_pair.index}"
            )
            _finalise(
                run_dir,
                source_file,
                config,
                run_id,
                pairs,
                prompt_results,
                started_at=started_at,
                halted_early=True,
                halt_reason=halt_reason,
            )
            return PipelineResult(
                prompt_results,
                halted_early=True,
                halt_reason=halt_reason,
            )

        prompt_results.append(result)
        if result.last_session_id:
            last_session_id = result.last_session_id
        if result.final_verdict == Verdict.PASS:
            prior_artifacts.append(
                PriorArtifact(
                    title=rendered_pair.title,
                    text_body=result.final_artifact,
                    files=list(result.created_files),
                )
            )
        else:
            halt_reason = f"prompt {rendered_pair.index} escalated"
            _emit_progress(
                f"{_progress_prefix(started_at)} "
                f"run halt {halt_reason}"
            )
            _finalise(run_dir, source_file, config, run_id, pairs, prompt_results,
                      started_at=started_at, halted_early=True,
                      halt_reason=halt_reason)
            return PipelineResult(prompt_results, halted_early=True, halt_reason=halt_reason)

    _emit_progress(
        f"{_progress_prefix(started_at)} "
        f"run complete {run_id}"
    )
    _finalise(run_dir, source_file, config, run_id, pairs, prompt_results,
              started_at=started_at, halted_early=False, halt_reason=None)
    return PipelineResult(prompt_results, halted_early=False, halt_reason=None)


def _format_claude_failed_halt_reason(
    pair: PromptPair, err: ClaudeInvocationError, run_dir: Path,
) -> str:
    """Build a multi-line R-CLAUDE-FAILED halt reason per CD-001 §11.2."""
    partial_md_path = _iteration_history_path(run_dir, pair, 1)
    module_log_path = _module_log_path(run_dir, pair)
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
        f"Full log saved to: {module_log_path}\n"
        f"\n"
        f"To retry, re-run prompt-runner. To investigate, look at the "
        f"module log above."
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
            "judge_only": config.judge_only,
            "dry_run": config.dry_run,
        },
        "started_at": started_at,
        "finished_at": None,
    }
    _write(_run_files_dir(run_dir) / "manifest.json", json.dumps(manifest, indent=2) + "\n")


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
    manifest_path = _run_files_dir(run_dir) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["finished_at"] = _format_iso(finished_at)
    manifest["halt_reason"] = halt_reason
    manifest["wall_time"] = wall_time
    _write(manifest_path, json.dumps(manifest, indent=2) + "\n")

    _write(_run_files_dir(run_dir) / "summary.txt", _format_summary(
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
    lines.append(f"Total backend calls: {total_calls}")
    lines.append(f"Wall time: {wall_time}")
    if fork_results:
        lines.append(f"Forks executed: {len(fork_results)}")
    if halt_reason:
        lines.append(f"Halt reason: {halt_reason}")
    lines.append("")
    return "\n".join(lines)
