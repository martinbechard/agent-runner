"""Integration smoke test for the extended prompt-runner.

Exercises parser (heading-only sections, interactive marker), runner (interactive
spawn, validator-less skip-judge), and --resume (skip completed, identify
incomplete) in one end-to-end flow.
"""
from pathlib import Path
import re

import pytest

from prompt_runner.claude_client import ClaudeResponse, FakeClaudeClient
from prompt_runner.parser import parse_text
from prompt_runner.runner import RUN_FILES_DIRNAME, RunConfig, run_pipeline


def _worktree(tmp_path: Path) -> Path:
    w = tmp_path / "worktree"
    w.mkdir(exist_ok=True)
    return w


def _run_files(run_dir: Path) -> Path:
    return run_dir / RUN_FILES_DIRNAME


def _module_dir(run_dir: Path, title: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "untitled"
    return _run_files(run_dir) / slug


def _prompt_slug(index: int, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "untitled"
    return f"prompt-{index:02d}-{slug}"


INPUT = """# Smoke test

## Prompt 1: Normal headed prompt

### Generation Prompt

generate artifact one

### Validation Prompt

validate artifact one

## Prompt 2: Validator-less mode

### Generation Prompt

generate artifact two, no validator

## Prompt 3: Interactive mode [interactive]

### Generation Prompt

interactive mission text

## Prompt 4: Back to normal

### Generation Prompt

generate artifact four

### Validation Prompt

validate artifact four
"""


def test_end_to_end_mixed_modes_then_resume(tmp_path: Path, monkeypatch):
    # --- arrange -----------------------------------------------------------
    src = tmp_path / "smoke.md"
    src.write_text(INPUT, encoding="utf-8")
    pairs = parse_text(INPUT)
    assert len(pairs) == 4
    assert pairs[0].interactive is False and pairs[0].validation_prompt
    assert pairs[1].interactive is False and pairs[1].validation_prompt == ""
    assert pairs[2].interactive is True and pairs[2].validation_prompt == ""
    assert pairs[3].interactive is False and pairs[3].validation_prompt

    run_dir = tmp_path / "run"
    worktree = _worktree(tmp_path)

    # Stub subprocess.Popen so the interactive prompt doesn't actually
    # spawn claude. Record the invocation for later assertions.
    import subprocess
    import prompt_runner.runner as _runner
    interactive_calls: list[list] = []

    class _FakeInteractiveProc:
        def __init__(self, argv, **kwargs):
            self.argv = argv
            self.kwargs = kwargs
            self.pid = 42424

        def wait(self):
            interactive_calls.append(self.argv)
            # Simulate the user creating a file during the interactive session
            (worktree / "authored-during-interactive.md").write_text(
                "body", encoding="utf-8",
            )
            return 0

    def fake_subprocess_popen(argv, **kwargs):
        return _FakeInteractiveProc(argv, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", fake_subprocess_popen)
    monkeypatch.setattr(_runner, "_git_is_worktree", lambda *_args, **_kwargs: False)

    # Scripted claude responses for the non-interactive prompts:
    # - Prompt 1: generator + judge = 2 calls
    # - Prompt 2: generator only (validator skipped) = 1 call
    # - Prompt 3: no claude client calls (interactive spawns its own subprocess)
    # - Prompt 4: generator + judge = 2 calls
    # Total via claude_client: 5 calls
    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="artifact 1", stderr="", returncode=0),
        ClaudeResponse(stdout="Looks good.\n\nVERDICT: pass", stderr="", returncode=0),
        ClaudeResponse(stdout="artifact 2", stderr="", returncode=0),
        ClaudeResponse(stdout="artifact 4", stderr="", returncode=0),
        ClaudeResponse(stdout="Looks good.\n\nVERDICT: pass", stderr="", returncode=0),
    ])

    # --- act: first pass (full run) ----------------------------------------
    result = run_pipeline(
        pairs=pairs, run_dir=run_dir, config=RunConfig(max_iterations=3, backend="claude"),
        claude_client=client, source_file=src, worktree_dir=worktree,
    )

    # --- assert first pass -------------------------------------------------
    assert not result.halted_early
    assert len(result.prompt_results) == 4
    for pr in result.prompt_results:
        assert pr.final_verdict.value == "pass"

    # Claude client received 5 calls (1 gen + 1 judge + 1 gen-only + 0 + 1 gen + 1 judge)
    assert len(client.received) == 5

    # subprocess.run was called once for the interactive prompt
    assert len(interactive_calls) == 1
    assert interactive_calls[0][0] == "claude"
    assert "interactive mission text" in interactive_calls[0][-1]

    # The whole file is one module, so all prompt verdict files live together.
    module_dir = _module_dir(run_dir, "Normal headed prompt")
    titles = {
        1: "Normal headed prompt",
        2: "Validator-less mode",
        3: "Interactive mode",
        4: "Back to normal",
    }
    for i in range(1, 5):
        prompt_slug = _prompt_slug(i, titles[i])
        verdict = (module_dir / f"{prompt_slug}.final-verdict.txt").read_text("utf-8").strip()
        assert verdict == "pass", f"prompt {i} verdict is {verdict!r}"

    # --- act: second pass (fresh --resume, everything should skip) ---------
    client2 = FakeClaudeClient(scripted=[])  # no responses should be consumed
    interactive_calls.clear()

    result2 = run_pipeline(
        pairs=pairs, run_dir=run_dir, config=RunConfig(max_iterations=3, backend="claude"),
        claude_client=client2, source_file=src, worktree_dir=worktree,
        resume=True,
    )
    assert not result2.halted_early
    assert len(client2.received) == 0, "resume should have skipped all prompts"
    assert len(interactive_calls) == 0, "resume should not respawn interactive prompts"

    # --- act: third pass (simulate crash right before prompt 4) ------------
    # Delete prompt 4's verdict file to mark it incomplete
    prompt_4_dir = module_dir
    prompt_4_slug = _prompt_slug(4, "Back to normal")
    (prompt_4_dir / f"{prompt_4_slug}.final-verdict.txt").unlink()

    client3 = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="artifact 4 re-run", stderr="", returncode=0),
        ClaudeResponse(stdout="Looks good.\n\nVERDICT: pass", stderr="", returncode=0),
    ])
    interactive_calls.clear()

    result3 = run_pipeline(
        pairs=pairs, run_dir=run_dir, config=RunConfig(max_iterations=3, backend="claude"),
        claude_client=client3, source_file=src, worktree_dir=worktree,
        resume=True,
    )
    assert not result3.halted_early
    assert len(client3.received) == 2, "only prompt 4 should have re-run"
    assert len(interactive_calls) == 0, "prompt 3 (interactive) should stay skipped"
    # Prompt 4's re-run produced the new artifact
    verdict = (prompt_4_dir / f"{prompt_4_slug}.final-verdict.txt").read_text("utf-8").strip()
    assert verdict == "pass"
    assert not (prompt_4_dir / f"{prompt_4_slug}.final-artifact.md").exists()


def test_interactive_codex_uses_local_state_overrides(tmp_path: Path, monkeypatch):
    src = tmp_path / "smoke.md"
    src.write_text(
        "# Smoke\n\n## Prompt 1: Interactive [interactive]\n\n### Generation Prompt\n\ninteractive mission\n",
        encoding="utf-8",
    )
    pairs = parse_text(src.read_text(encoding="utf-8"))
    run_dir = tmp_path / "run"
    worktree = _worktree(tmp_path)

    import subprocess
    import prompt_runner.runner as _runner
    captured: dict = {}

    class _FakeInteractiveProc:
        def __init__(self, argv, **kwargs):
            captured["argv"] = argv
            captured["cwd"] = kwargs.get("cwd")
            self.pid = 43434

        def wait(self):
            return 0

    def fake_subprocess_popen(argv, **kwargs):
        return _FakeInteractiveProc(argv, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", fake_subprocess_popen)
    monkeypatch.setattr(_runner, "_git_is_worktree", lambda *_args, **_kwargs: False)

    result = run_pipeline(
        pairs=pairs,
        run_dir=run_dir,
        config=RunConfig(backend="codex", dangerously_skip_permissions=True),
        claude_client=FakeClaudeClient(scripted=[]),
        source_file=src,
        worktree_dir=worktree,
    )

    assert not result.halted_early
    assert captured["argv"][0] == "codex"
    assert f'projects."{worktree}".trust_level="trusted"' in captured["argv"]
    assert 'approval_policy="never"' in captured["argv"]
    assert 'history.persistence="none"' in captured["argv"]
    assert 'sandbox_mode="danger-full-access"' in captured["argv"]
    assert captured["cwd"] == worktree
