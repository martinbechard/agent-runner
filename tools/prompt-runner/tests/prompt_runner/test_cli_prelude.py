"""CLI-level tests for the --generator-prelude and --judge-prelude flags."""
from pathlib import Path

import pytest

from prompt_runner.__main__ import _build_parser


def test_run_parser_accepts_generator_prelude_flag():
    parser = _build_parser()
    args = parser.parse_args([
        "run", "file.md",
        "--generator-prelude", "/tmp/gp.txt",
        "--judge-prelude", "/tmp/jp.txt",
    ])
    assert args.generator_prelude == "/tmp/gp.txt"
    assert args.judge_prelude == "/tmp/jp.txt"


def test_run_parser_prelude_flags_default_to_none():
    parser = _build_parser()
    args = parser.parse_args(["run", "file.md"])
    assert args.generator_prelude is None
    assert args.judge_prelude is None


def test_cmd_run_reads_prelude_files(tmp_path: Path, monkeypatch):
    gp = tmp_path / "gp.txt"
    jp = tmp_path / "jp.txt"
    gp.write_text("GEN-PRELUDE-BODY", encoding="utf-8")
    jp.write_text("JUD-PRELUDE-BODY", encoding="utf-8")

    captured: dict = {}

    def fake_run_pipeline(**kwargs):
        captured.update(kwargs)
        from prompt_runner.runner import PipelineResult
        return PipelineResult(prompt_results=[], halted_early=False, halt_reason=None)

    from prompt_runner import __main__ as m
    monkeypatch.setattr(m, "run_pipeline", fake_run_pipeline)

    # Minimal valid prompt file
    pfile = tmp_path / "pr.md"
    pfile.write_text(
        "# Header\n\n## Prompt 1: X\n\n### Generation Prompt\n\ngen\n\n### Validation Prompt\n\nval\n",
        encoding="utf-8",
    )

    rc = m.main([
        "run", str(pfile),
        "--generator-prelude", str(gp),
        "--judge-prelude", str(jp),
        "--dry-run",
        "--run-dir", str(tmp_path / "out"),
    ])
    assert rc == 0
    cfg = captured["config"]
    assert cfg.generator_prelude == "GEN-PRELUDE-BODY"
    assert cfg.judge_prelude == "JUD-PRELUDE-BODY"


def test_cmd_run_missing_prelude_file_errors(tmp_path: Path, capsys):
    from prompt_runner import __main__ as m
    pfile = tmp_path / "pr.md"
    pfile.write_text(
        "# H\n\n## Prompt 1: X\n\n### Generation Prompt\n\ngen\n\n### Validation Prompt\n\nval\n",
        encoding="utf-8",
    )
    rc = m.main([
        "run", str(pfile),
        "--generator-prelude", str(tmp_path / "nope.txt"),
        "--dry-run",
    ])
    assert rc != 0
    captured = capsys.readouterr()
    assert "prelude" in captured.err.lower() or "not found" in captured.err.lower()
