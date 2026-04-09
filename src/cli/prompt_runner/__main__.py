"""prompt-runner CLI entry point."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from prompt_runner.claude_client import (
    ClaudeBinaryNotFound,
    DryRunClaudeClient,
    RealClaudeClient,
)
from prompt_runner.parser import ParseError, PromptPair, parse_file
from prompt_runner.runner import PipelineResult, RunConfig, run_pipeline


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


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _cmd_parse(args: argparse.Namespace) -> int:
    try:
        pairs = parse_file(Path(args.file))
    except ParseError as err:
        sys.stderr.write(f"{err.error_id}\n\n{err.message}\n")
        return 2
    for pair in pairs:
        sys.stdout.write(_format_pair_summary(pair, full=args.full) + "\n\n")
    return 0


def _default_run_dir(source: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return Path("runs") / f"{ts}-{source.stem}"


def _cmd_run(args: argparse.Namespace) -> int:
    source = Path(args.file)
    try:
        pairs = parse_file(source)
    except ParseError as err:
        _print_error_banner(err.error_id, err.message)
        return 2

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

    config = RunConfig(
        max_iterations=args.max_iterations,
        model=args.model,
        only=args.only,
        dry_run=args.dry_run,
        generator_prelude=generator_prelude,
        judge_prelude=judge_prelude,
    )

    try:
        client = DryRunClaudeClient() if args.dry_run else RealClaudeClient()
    except ClaudeBinaryNotFound as err:
        _print_error_banner("R-NO-CLAUDE", str(err))
        return 3

    if args.resume:
        resume_path = Path(args.resume)
        if not resume_path.exists() or not resume_path.is_dir():
            _print_error_banner(
                "R-RESUME-NOT-FOUND",
                f"--resume path does not exist or is not a directory: {resume_path}",
            )
            return 2
        run_dir = resume_path
        do_resume = True
    else:
        run_dir = Path(args.output_dir) if args.output_dir else _default_run_dir(source)
        do_resume = False

    result = run_pipeline(
        pairs=pairs,
        run_dir=run_dir,
        config=config,
        claude_client=client,
        source_file=source,
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
    summary_path = run_dir / "summary.txt"
    summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
    sys.stdout.write(f"\n{BANNER_RULE}\nPrompt Runner — Run complete\n{BANNER_RULE}\n")
    sys.stdout.write(f"{summary}\n{BANNER_RULE}\n")
    sys.stdout.flush()


def _build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="prompt-runner",
        description="Run prompt/validator pairs from a markdown file through the Claude CLI.",
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
        "--output-dir",
        default=None,
        help="Run directory (default: ./runs/<timestamp>-<stem>/).",
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
        help="Passed through as --model to claude -p.",
    )
    run_cmd.add_argument(
        "--only",
        type=int,
        default=None,
        help="Run only prompt number N (debug).",
    )
    run_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and show the planned sequence without calling claude.",
    )
    run_cmd.add_argument(
        "--generator-prelude",
        default=None,
        help=(
            "Path to a text file whose contents are prepended to every "
            "generator Claude message in this run.  Used by "
            "methodology-runner to inject phase-specific skill loading "
            "instructions; opaque text from prompt-runner's perspective."
        ),
    )
    run_cmd.add_argument(
        "--judge-prelude",
        default=None,
        help=(
            "Path to a text file whose contents are prepended to every "
            "judge Claude message in this run.  Symmetric to "
            "--generator-prelude."
        ),
    )
    run_cmd.add_argument(
        "--resume",
        default=None,
        help=(
            "Resume an existing run by pointing at its run directory. Prompts "
            "that have already completed with 'pass' (per their final-verdict.txt) "
            "are skipped; execution continues from the first incomplete prompt. "
            "When --resume is set, --output-dir is ignored (the resumed run dir "
            "is used as the output dir)."
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
