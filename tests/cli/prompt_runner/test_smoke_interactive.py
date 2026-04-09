"""Integration smoke test for the extended prompt-runner.

Exercises parser (single-fence, interactive marker), runner (interactive
spawn, validator-less skip-judge), and --resume (skip completed, identify
incomplete) in one end-to-end flow.
"""
from pathlib import Path

import pytest

from prompt_runner.claude_client import ClaudeResponse, FakeClaudeClient
from prompt_runner.parser import parse_text
from prompt_runner.runner import RunConfig, run_pipeline


def _workspace(tmp_path: Path) -> Path:
    w = tmp_path / "workspace"
    w.mkdir(exist_ok=True)
    return w


INPUT = """# Smoke test

## Prompt 1: Normal two-fence

```
generate artifact one
```

```
validate artifact one
```

## Prompt 2: Validator-less mode

```
generate artifact two, no validator
```

## Prompt 3: Interactive mode [interactive]

```
interactive mission text
```

## Prompt 4: Back to normal

```
generate artifact four
```

```
validate artifact four
```
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
    workspace = _workspace(tmp_path)

    # Stub subprocess.run so the interactive prompt doesn't actually
    # spawn claude. Record the invocation for later assertions.
    import subprocess
    interactive_calls: list[list] = []

    def fake_subprocess_run(argv, **kwargs):
        interactive_calls.append(argv)
        # Simulate the user creating a file during the interactive session
        (workspace / "authored-during-interactive.md").write_text(
            "body", encoding="utf-8",
        )
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

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
        pairs=pairs, run_dir=run_dir, config=RunConfig(max_iterations=3),
        claude_client=client, source_file=src, workspace_dir=workspace,
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

    # Each prompt dir has a final-verdict.txt == pass
    for i in range(1, 5):
        # Slug matches what _prompt_dir_name produces
        slug_candidates = list(run_dir.glob(f"prompt-0{i}-*"))
        assert len(slug_candidates) == 1, f"prompt {i} dir missing"
        verdict = (slug_candidates[0] / "final-verdict.txt").read_text("utf-8").strip()
        assert verdict == "pass", f"prompt {i} verdict is {verdict!r}"

    # --- act: second pass (fresh --resume, everything should skip) ---------
    client2 = FakeClaudeClient(scripted=[])  # no responses should be consumed
    interactive_calls.clear()

    result2 = run_pipeline(
        pairs=pairs, run_dir=run_dir, config=RunConfig(max_iterations=3),
        claude_client=client2, source_file=src, workspace_dir=workspace,
        resume=True,
    )
    assert not result2.halted_early
    assert len(client2.received) == 0, "resume should have skipped all prompts"
    assert len(interactive_calls) == 0, "resume should not respawn interactive prompts"

    # --- act: third pass (simulate crash right before prompt 4) ------------
    # Delete prompt 4's verdict file to mark it incomplete
    prompt_4_dirs = list(run_dir.glob("prompt-04-*"))
    assert len(prompt_4_dirs) == 1
    (prompt_4_dirs[0] / "final-verdict.txt").unlink()

    client3 = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout="artifact 4 re-run", stderr="", returncode=0),
        ClaudeResponse(stdout="Looks good.\n\nVERDICT: pass", stderr="", returncode=0),
    ])
    interactive_calls.clear()

    result3 = run_pipeline(
        pairs=pairs, run_dir=run_dir, config=RunConfig(max_iterations=3),
        claude_client=client3, source_file=src, workspace_dir=workspace,
        resume=True,
    )
    assert not result3.halted_early
    assert len(client3.received) == 2, "only prompt 4 should have re-run"
    assert len(interactive_calls) == 0, "prompt 3 (interactive) should stay skipped"
    # Prompt 4's re-run produced the new artifact
    verdict = (prompt_4_dirs[0] / "final-verdict.txt").read_text("utf-8").strip()
    assert verdict == "pass"
    artifact = (prompt_4_dirs[0] / "final-artifact.md").read_text("utf-8")
    assert "artifact 4 re-run" in artifact
