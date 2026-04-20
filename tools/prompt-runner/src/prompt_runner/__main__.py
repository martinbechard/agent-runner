"""prompt-runner CLI entry point."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from prompt_runner.client_factory import (
    ClaudeBinaryNotFound,
    CodexBinaryNotFound,
    make_client,
)
from prompt_runner.config import load_config
from prompt_runner.parser import ForkPoint, ParseError, PromptPair, parse_file
from prompt_runner.runner import PipelineResult, RUN_FILES_DIRNAME, RunConfig, run_pipeline


BANNER_RULE = "═" * 70


def _format_pair_summary(pair: PromptPair, full: bool) -> str:
    gen_lines = pair.generation_prompt.splitlines()
    val_lines = pair.validation_prompt.splitlines()
    header = (
        f"═══ Prompt {pair.index}: {pair.title} ═══\n"
        f"  heading line: {pair.heading_line}\n"
        f"  generation prompt: {len(gen_lines)} lines, "
        f"{len(pair.generation_prompt)} chars\n"
        f"  validation prompt: {len(val_lines)} lines, "
        f"{len(pair.validation_prompt)} chars"
    )
    if full:
        return (
            f"{header}\n"
            f"  ─── generation ───\n"
            f"{_indent(pair.generation_prompt)}\n"
            f"  ─── validation ───\n"
            f"{_indent(pair.validation_prompt)}"
        )
    preview_gen = "\n".join(gen_lines[:3])
    preview_val = "\n".join(val_lines[:3])
    return (
        f"{header}\n"
        f"  ─── generation (first 3 lines) ───\n"
        f"{_indent(preview_gen)}\n"
        f"  ─── validation (first 3 lines) ───\n"
        f"{_indent(preview_val)}"
    )


def _format_fork_summary(fork: ForkPoint) -> str:
    lines = [
        f"═══ Prompt {fork.index}: {fork.title} [VARIANTS] ═══",
        f"  heading line: {fork.heading_line}",
        f"  variants: {len(fork.variants)}",
    ]
    for variant in fork.variants:
        lines.append(
            f"  - {variant.variant_name}: {variant.variant_title} "
            f"({len(variant.pairs)} pair{'s' if len(variant.pairs) != 1 else ''})"
        )
    return "\n".join(lines)


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _cmd_parse(args: argparse.Namespace) -> int:
    try:
        pairs = parse_file(Path(args.file))
    except ParseError as err:
        sys.stderr.write(f"{err.error_id}\n\n{err.message}\n")
        return 2
    for pair in pairs:
        if isinstance(pair, ForkPoint):
            sys.stdout.write(_format_fork_summary(pair) + "\n\n")
        else:
            sys.stdout.write(_format_pair_summary(pair, full=args.full) + "\n\n")
    return 0


def _runs_root(project_dir: Path | None) -> Path:
    base = project_dir.resolve() if project_dir is not None else Path.cwd().resolve()
    return base / ".prompt-runner" / "runs"


def _default_run_dir(source: Path, project_dir: Path | None = None) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return _runs_root(project_dir) / f"{ts}-{source.stem}"


def _find_latest_run_dir(source: Path, project_dir: Path | None = None) -> Path | None:
    """Find the most recent run directory matching *source*'s stem.

    Run directories are named ``<timestamp>-<stem>`` under
    ``.prompt-runner/runs/`` inside the working project.
    Timestamps sort lexicographically, so the last match is the most
    recent.  Returns None if no match is found.
    """
    runs_dir = _runs_root(project_dir)
    if not runs_dir.exists():
        return None
    candidates = sorted(runs_dir.glob(f"*-{source.stem}"))
    if not candidates:
        return None
    return candidates[-1]


def _cmd_run(args: argparse.Namespace) -> int:
    source = Path(args.file)
    sys.stdout.write(
        f"prompt-runner starting: {source}\n"
    )
    sys.stdout.flush()
    try:
        pairs = parse_file(source)
    except ParseError as err:
        _print_error_banner(err.error_id, err.message)
        return 2
    try:
        file_config = load_config(source)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as err:
        _print_error_banner("R-CONFIG-INVALID", str(err))
        return 2

    backend = args.backend or file_config.run.backend or "claude"
    model = args.model or file_config.run.model

    generator_prelude: str | None = None
    judge_prelude: str | None = None
    if args.generator_prelude:
        gp_path = Path(args.generator_prelude)
        if not gp_path.exists():
            _print_error_banner(
                "R-PRELUDE-NOT-FOUND",
                f"--generator-prelude file not found: {gp_path}",
            )
            return 2
        generator_prelude = gp_path.read_text(encoding="utf-8")
    if args.judge_prelude:
        jp_path = Path(args.judge_prelude)
        if not jp_path.exists():
            _print_error_banner(
                "R-PRELUDE-NOT-FOUND",
                f"--judge-prelude file not found: {jp_path}",
            )
            return 2
        judge_prelude = jp_path.read_text(encoding="utf-8")

    placeholder_values: dict[str, str] = {}
    for item in args.var:
        if "=" not in item:
            _print_error_banner(
                "R-INVALID-VAR",
                f"invalid --var (expected NAME=VALUE): {item}",
            )
            return 2
        name, value = item.split("=", 1)
        placeholder_values[name] = value

    path_mappings: dict[str, str] = {}
    for item in args.path_map:
        if "=" not in item:
            _print_error_banner(
                "R-INVALID-PATH-MAP",
                f"invalid --path-map (expected PREFIX=ROOT): {item}",
            )
            return 2
        prefix, root = item.split("=", 1)
        if not prefix:
            _print_error_banner(
                "R-INVALID-PATH-MAP",
                f"invalid --path-map prefix: {item}",
            )
            return 2
        path_mappings[prefix] = root

    selected_prompt = args.only if args.only is not None else args.judge_only

    if args.variant is not None and args.only is None:
        _print_error_banner(
            "R-INVALID-FLAGS",
            "--variant requires --only <fork-prompt-number>.",
        )
        return 2
    if args.variant is not None and args.judge_only is not None:
        _print_error_banner(
            "R-INVALID-FLAGS",
            "--variant cannot be combined with --judge-only.",
        )
        return 2
    if args.variant is not None:
        selected_item = next((item for item in pairs if item.index == args.only), None)
        if selected_item is None:
            _print_error_banner(
                "R-INVALID-FLAGS",
                f"--only {args.only} does not match any prompt in {source.name}.",
            )
            return 2
        if not isinstance(selected_item, ForkPoint):
            _print_error_banner(
                "R-INVALID-FLAGS",
                f"--variant requires --only to target a [VARIANTS] prompt, but prompt "
                f"{args.only} is not a fork prompt.",
            )
            return 2
        variant_names = {variant.variant_name for variant in selected_item.variants}
        if args.variant not in variant_names:
            _print_error_banner(
                "R-INVALID-FLAGS",
                f"prompt {args.only} has no variant named '{args.variant}'. "
                f"Available: {', '.join(sorted(variant_names))}",
            )
            return 2

    config = RunConfig(
        backend=backend,
        max_iterations=args.max_iterations,
        model=model,
        debug=args.debug,
        only=selected_prompt,
        judge_only=args.judge_only,
        dry_run=args.dry_run,
        verbose=args.verbose,
        generator_prelude=generator_prelude,
        judge_prelude=judge_prelude,
        include_project_organiser=not args.no_project_organiser,
        dangerously_skip_permissions=args.dangerously_skip_permissions,
        variant_sequential=args.variant_sequential,
        fork_from_session=getattr(args, "fork_from_session", None),
        placeholder_values=placeholder_values,
        path_mappings=path_mappings,
        variant=args.variant,
    )

    try:
        client = make_client(backend, dry_run=args.dry_run, verbose=args.verbose)
    except (ClaudeBinaryNotFound, CodexBinaryNotFound) as err:
        _print_error_banner("R-NO-BACKEND", str(err))
        return 3

    project_dir = Path(args.project_dir).resolve() if args.project_dir else None

    if args.judge_only is not None and args.only is not None and args.judge_only != args.only:
        _print_error_banner(
            "R-INVALID-FLAGS",
            "--judge-only and --only must target the same prompt number when both are set.",
        )
        return 2

    if args.resume is not None or args.judge_only is not None:
        if args.resume == "auto":
            resume_path = _find_latest_run_dir(source, project_dir)
            if resume_path is None:
                _print_error_banner(
                    "R-RESUME-NOT-FOUND",
                    f"No existing run directory found for {source.name} "
                    f"under {_runs_root(project_dir)}. Run without --resume first.",
                )
                return 2
        elif args.resume is not None:
            resume_path = Path(args.resume)
        elif args.run_dir:
            resume_path = Path(args.run_dir)
        else:
            resume_path = _find_latest_run_dir(source, project_dir)
            if resume_path is None:
                _print_error_banner(
                    "R-RESUME-NOT-FOUND",
                    f"No existing run directory found for {source.name} "
                    f"under {_runs_root(project_dir)}. Run without --judge-only first.",
                )
                return 2
        if not resume_path.exists() or not resume_path.is_dir():
            _print_error_banner(
                "R-RESUME-NOT-FOUND",
                f"--resume path does not exist or is not a directory: {resume_path}",
            )
            return 2
        run_dir = resume_path
        do_resume = True
    else:
        run_dir = (
            Path(args.run_dir)
            if args.run_dir else
            _default_run_dir(source, project_dir)
        )
        do_resume = False

    result = run_pipeline(
        pairs=pairs,
        run_dir=run_dir,
        config=config,
        claude_client=client,
        source_file=source,
        source_project_dir=project_dir,
        resume=do_resume,
    )

    if result.halted_early:
        _print_error_banner("HALT", result.halt_reason or "pipeline halted")
        # Exit code: 1 for escalation-style halts, 3 for runtime-style halts.
        reason = result.halt_reason or ""
        if reason.startswith("R-"):
            return 3
        return 1

    _print_success_banner(run_dir)
    return 0


def _print_error_banner(error_id: str, message: str) -> None:
    sys.stderr.write(f"\n{BANNER_RULE}\nERROR: {error_id}\n{BANNER_RULE}\n")
    sys.stderr.write(f"{message}\n{BANNER_RULE}\n")
    sys.stderr.flush()


def _print_success_banner(run_dir: Path) -> None:
    run_files_dir = run_dir / RUN_FILES_DIRNAME
    summary_path = run_files_dir / "summary.txt"
    if not summary_path.exists():
        module_summaries = sorted(run_files_dir.glob("*/summary.txt"))
        if len(module_summaries) == 1:
            summary_path = module_summaries[0]
    summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
    sys.stdout.write(f"\n{BANNER_RULE}\nPrompt Runner — Run complete\n{BANNER_RULE}\n")
    sys.stdout.write(f"{summary}\n{BANNER_RULE}\n")
    sys.stdout.flush()


def _build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="prompt-runner",
        description="Run prompt/validator pairs from a markdown file through a supported coding-agent CLI.",
    )
    sub = root.add_subparsers(dest="command", required=True)

    parse_cmd = sub.add_parser("parse", help="Parse the file and print prompt pairs.")
    parse_cmd.add_argument("file", help="Path to the input markdown file.")
    parse_cmd.add_argument(
        "--full",
        action="store_true",
        help="Dump complete generator and validator bodies verbatim.",
    )
    parse_cmd.set_defaults(func=_cmd_parse)

    run_cmd = sub.add_parser("run", help="Execute the full pipeline.")
    run_cmd.add_argument("file", help="Path to the input markdown file.")
    run_cmd.add_argument(
        "--backend",
        choices=("claude", "codex"),
        default=None,
        help=(
            "Agent backend to use for generation/judging. Overrides [run].backend "
            "from prompt-runner.toml; defaults to claude if neither is set."
        ),
    )
    run_cmd.add_argument(
        "--run-dir",
        default=None,
        help=(
            "Run directory (default: <project>/.prompt-runner/runs/"
            "<timestamp>-<stem>/)."
        ),
    )
    run_cmd.add_argument(
        "--no-project-organiser",
        action="store_true",
        help=(
            "Do not append the project-organiser file-placement instruction "
            "to generator prompts. Use this when prompt paths are already "
            "fully controlled by the prompt or caller."
        ),
    )
    run_cmd.add_argument(
        "--project-dir",
        default=None,
        help=(
            "Source project tree used to initialise a new run worktree. "
            "Defaults to cwd. When omitted, prompt-runner treats --run-dir "
            "itself as the editable project tree."
        ),
    )
    run_cmd.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help=(
            "Extra placeholder binding. May be repeated. Built-in values such "
            "as run_dir and project_dir are always supplied by prompt-runner."
        ),
    )
    run_cmd.add_argument(
        "--path-map",
        action="append",
        default=[],
        metavar="PREFIX=ROOT",
        help=(
            "Prefix-based prompt path mapping. May be repeated. Example: "
            "--path-map skills/=/abs/path/to/skills/ so {{INCLUDE:skills/x.md}} "
            "resolves under that root."
        ),
    )
    run_cmd.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Max revision iterations per prompt (default: 3).",
    )
    run_cmd.add_argument(
        "--model",
        default=None,
        help="Passed through as --model to the selected backend CLI.",
    )
    run_cmd.add_argument(
        "--only",
        type=int,
        default=None,
        help="Run only prompt number N (debug).",
    )
    run_cmd.add_argument(
        "--variant",
        default=None,
        help=(
            "Run only the named variant inside the selected fork prompt. "
            "Use with --only N, where N is the fork prompt number."
        ),
    )
    run_cmd.add_argument(
        "--judge-only",
        type=int,
        default=None,
        help=(
            "Rerun only the judge for prompt number N using that prompt's existing "
            "saved artifact/files in the run directory."
        ),
    )
    run_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and show the planned sequence without calling the backend CLI.",
    )
    run_cmd.add_argument(
        "--verbose",
        action="store_true",
        help="Stream backend stdout/stderr live to the terminal during execution.",
    )
    run_cmd.add_argument(
        "--debug",
        nargs="?",
        const=3,
        default=0,
        type=int,
        metavar="N",
        help=(
            "Enable depth-limited prompt-runner function tracing in "
            ".run-files/process.log. Default depth is 3 when the flag is "
            "present without a value."
        ),
    )
    run_cmd.add_argument(
        "--generator-prelude",
        default=None,
        help=(
            "Path to a text file whose contents are prepended to every "
            "generator message in this run. Used by "
            "methodology-runner to inject phase-specific skill loading "
            "instructions; opaque text from prompt-runner's perspective."
        ),
    )
    run_cmd.add_argument(
        "--judge-prelude",
        default=None,
        help=(
            "Path to a text file whose contents are prepended to every "
            "judge message in this run. Symmetric to "
            "--generator-prelude."
        ),
    )
    run_cmd.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        help=(
            "Use the backend's lowest-friction interactive mode when "
            "available. For Claude this passes "
            "--dangerously-skip-permissions; for Codex it enables "
            "--full-auto. Only affects [interactive] prompts; ignored "
            "for non-interactive."
        ),
    )
    run_cmd.add_argument(
        "--resume",
        nargs="?",
        const="auto",
        default=None,
        help=(
            "Resume an existing run. Without a path, auto-finds the most "
            "recent run directory matching the input file under "
            "<project>/.prompt-runner/runs/. "
            "With a path, uses that directory. Prompts that already "
            "completed with 'pass' are skipped; execution continues from "
            "the first incomplete prompt."
        ),
    )
    run_cmd.add_argument(
        "--variant-sequential",
        action="store_true",
        default=False,
        help=(
            "Run fork-point variants one at a time instead of in parallel. "
            "Parallel (default) is faster; sequential uses less API quota "
            "simultaneously."
        ),
    )
    run_cmd.add_argument(
        "--fork-from-session",
        default=None,
        help=(
            "Fork from an existing backend session. The first generator call "
            "uses backend-specific session inheritance when supported. "
            "Used internally by the variant fork mechanism."
        ),
    )
    run_cmd.set_defaults(func=_cmd_run)

    return root


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
