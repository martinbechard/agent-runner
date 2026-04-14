"""CLI-level tests for prompt-runner config-file defaults."""
from pathlib import Path


def _prompt_file(path: Path) -> Path:
    path.write_text(
        "# Header\n\n## Prompt 1: X\n\n```\ngen\n```\n\n```\nval\n```\n",
        encoding="utf-8",
    )
    return path


def test_cmd_run_uses_backend_from_config(tmp_path: Path, monkeypatch):
    from prompt_runner import __main__ as m

    (tmp_path / "prompt-runner.toml").write_text(
        "[run]\nbackend = \"codex\"\n",
        encoding="utf-8",
    )
    pfile = _prompt_file(tmp_path / "pr.md")

    captured: dict = {}

    def fake_make_client(backend, *, dry_run=False):
        captured["backend"] = backend

        class DummyClient:
            pass

        return DummyClient()

    def fake_run_pipeline(**kwargs):
        captured["config"] = kwargs["config"]
        from prompt_runner.runner import PipelineResult
        return PipelineResult(prompt_results=[], halted_early=False, halt_reason=None)

    monkeypatch.setattr(m, "make_client", fake_make_client)
    monkeypatch.setattr(m, "run_pipeline", fake_run_pipeline)

    rc = m.main([
        "run", str(pfile),
        "--dry-run",
        "--output-dir", str(tmp_path / "out"),
    ])
    assert rc == 0
    assert captured["backend"] == "codex"
    assert captured["config"].backend == "codex"


def test_cli_backend_overrides_config(tmp_path: Path, monkeypatch):
    from prompt_runner import __main__ as m

    (tmp_path / "prompt-runner.toml").write_text(
        "[run]\nbackend = \"codex\"\n",
        encoding="utf-8",
    )
    pfile = _prompt_file(tmp_path / "pr.md")

    captured: dict = {}

    def fake_make_client(backend, *, dry_run=False):
        captured["backend"] = backend

        class DummyClient:
            pass

        return DummyClient()

    def fake_run_pipeline(**kwargs):
        captured["config"] = kwargs["config"]
        from prompt_runner.runner import PipelineResult
        return PipelineResult(prompt_results=[], halted_early=False, halt_reason=None)

    monkeypatch.setattr(m, "make_client", fake_make_client)
    monkeypatch.setattr(m, "run_pipeline", fake_run_pipeline)

    rc = m.main([
        "run", str(pfile),
        "--backend", "claude",
        "--dry-run",
        "--output-dir", str(tmp_path / "out"),
    ])
    assert rc == 0
    assert captured["backend"] == "claude"
    assert captured["config"].backend == "claude"


def test_invalid_config_reports_error(tmp_path: Path, capsys):
    from prompt_runner import __main__ as m

    (tmp_path / "prompt-runner.toml").write_text(
        "[run\nbackend = \"codex\"\n",
        encoding="utf-8",
    )
    pfile = _prompt_file(tmp_path / "pr.md")

    rc = m.main(["run", str(pfile), "--dry-run"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "R-CONFIG-INVALID" in captured.err


def test_default_run_dir_uses_project_prompt_runner_runs(tmp_path: Path, monkeypatch):
    from prompt_runner import __main__ as m

    pfile = _prompt_file(tmp_path / "pr.md")
    captured: dict = {}

    def fake_make_client(backend, *, dry_run=False):
        class DummyClient:
            pass
        return DummyClient()

    def fake_run_pipeline(**kwargs):
        captured["run_dir"] = kwargs["run_dir"]
        captured["workspace_dir"] = kwargs["workspace_dir"]
        from prompt_runner.runner import PipelineResult
        return PipelineResult(prompt_results=[], halted_early=False, halt_reason=None)

    monkeypatch.setattr(m, "make_client", fake_make_client)
    monkeypatch.setattr(m, "run_pipeline", fake_run_pipeline)

    rc = m.main([
        "run", str(pfile),
        "--dry-run",
        "--project-dir", str(tmp_path),
    ])

    assert rc == 0
    assert captured["workspace_dir"] == tmp_path.resolve()
    assert captured["run_dir"].parent == (tmp_path / ".prompt-runner" / "runs").resolve()


def test_cli_var_flags_populate_placeholder_values(tmp_path: Path, monkeypatch):
    from prompt_runner import __main__ as m

    pfile = _prompt_file(tmp_path / "pr.md")
    captured: dict = {}

    def fake_make_client(backend, *, dry_run=False):
        class DummyClient:
            pass
        return DummyClient()

    def fake_run_pipeline(**kwargs):
        captured["config"] = kwargs["config"]
        from prompt_runner.runner import PipelineResult
        return PipelineResult(prompt_results=[], halted_early=False, halt_reason=None)

    monkeypatch.setattr(m, "make_client", fake_make_client)
    monkeypatch.setattr(m, "run_pipeline", fake_run_pipeline)

    rc = m.main([
        "run", str(pfile),
        "--dry-run",
        "--var", "workflow_prompt=/tmp/workflow.md",
        "--var", "raw_request=/tmp/request.md",
    ])

    assert rc == 0
    assert captured["config"].placeholder_values == {
        "workflow_prompt": "/tmp/workflow.md",
        "raw_request": "/tmp/request.md",
    }
