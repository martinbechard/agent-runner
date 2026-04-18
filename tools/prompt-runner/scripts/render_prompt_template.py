#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def render_template(text: str, variables: dict[str, str]) -> str:
    rendered = text
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a prompt template by replacing {{name}} placeholders.",
    )
    parser.add_argument("source", help="Template file to read.")
    parser.add_argument("dest", help="Rendered file to write.")
    parser.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Placeholder binding. May be repeated.",
    )
    args = parser.parse_args(argv)

    bindings: dict[str, str] = {}
    for item in args.var:
        if "=" not in item:
            raise SystemExit(f"invalid --var (expected NAME=VALUE): {item}")
        name, value = item.split("=", 1)
        bindings[name] = value

    source = Path(args.source)
    dest = Path(args.dest)
    text = source.read_text(encoding="utf-8")
    rendered = render_template(text, bindings)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
