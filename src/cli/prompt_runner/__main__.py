"""prompt-runner CLI entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from prompt_runner.parser import ParseError, PromptPair, parse_file


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

    return root


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
