from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    tool_root = Path(__file__).resolve().parents[1]
    script_path = tool_root / "scripts" / "run-timeline.py"
    spec = importlib.util.spec_from_file_location("run_timeline", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_detect_log_backend_codex():
    module = _load_module()
    path = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    assert module.detect_log_backend(path) == "codex"


def test_parse_codex_log_extracts_usage_and_activity():
    module = _load_module()
    path = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    detail = module.parse_log(path)
    assert detail.backend == "codex"
    assert detail.input_tokens == 78640
    assert detail.cache_read_tokens == 75520
    assert detail.output_tokens == 716
    assert detail.subagent_count == 1
    assert len(detail.turns) >= 2
    assert detail.num_turns == len(detail.turns)
    tool_names = [tc.name for turn in detail.turns for tc in turn.tool_calls]
    assert any(turn.text_chars > 0 for turn in detail.turns)
    assert "Bash" in tool_names
    assert "spawn_agent" in tool_names
    assert "wait" in tool_names
    assert "FileChange" in tool_names


def test_render_codex_log_structured_shows_usage():
    module = _load_module()
    path = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    detail = module.parse_log(path)
    html = module._render_log_structured(path, "popup-1", prompt_text="do the thing", detail=detail, step_duration_seconds=15)
    assert "THREAD" in html
    assert "Turn 1" in html
    assert "T+0000s" in html
    assert "CMD" in html
    assert "AGT" in html
    assert "DONE" in html
    assert "cached=75,520" in html


def test_render_codex_log_structured_treats_prompt_as_part_of_turn_one(tmp_path):
    module = _load_module()
    log_path = tmp_path / "codex.stdout.log"
    log_path.write_text(
        "\n".join(
            [
                '{"type":"thread.started","thread_id":"abc"}',
                '{"type":"turn.started"}',
                '{"type":"item.completed","item":{"id":"m1","type":"agent_message","text":"first"}}',
                '{"type":"item.completed","item":{"id":"c1","type":"command_execution","command":"pwd","aggregated_output":"/tmp\\n","exit_code":0,"status":"completed"}}',
                '{"type":"item.completed","item":{"id":"m2","type":"agent_message","text":"second"}}',
                '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":0,"output_tokens":4}}',
            ]
        ) + "\n",
        encoding="utf-8",
    )
    detail = module.parse_log(log_path)
    html = module._render_log_structured(log_path, "popup-2", prompt_text="do the thing", detail=detail, step_duration_seconds=5)
    assert "── Turn 1 — T+0000s ──" in html
    assert "PROMPT" in html
    assert "── Turn 2" in html


def test_render_detail_for_codex_uses_fresh_input_and_backend_label():
    module = _load_module()
    path = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    detail = module.parse_log(path)
    html = module._render_detail(detail, step_id="step-1", popups=[])
    assert "CODEX" in html
    assert "fresh-input: 3,120" in html


def test_parse_log_estimates_codex_cost_from_pricing_table():
    module = _load_module()
    path = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    detail = module.parse_log(path)
    detail.model = "gpt-5.4-mini"
    detail = module._finalize_detail(detail)
    assert detail.cost_estimated is True
    assert detail.cost_usd > 0


def test_parse_log_uses_metadata_sidecar_for_model(tmp_path):
    module = _load_module()
    log_path = tmp_path / "selector.stdout.log"
    log_path.write_text(
        '\n'.join(
            [
                '{"type":"thread.started","thread_id":"abc"}',
                '{"type":"item.completed","item":{"id":"m1","type":"agent_message","text":"selector_model: \\"gpt-5.4-mini\\""}}',
                '{"type":"turn.completed","usage":{"input_tokens":1000,"cached_input_tokens":500,"output_tokens":200}}',
            ]
        ) + "\n",
        encoding="utf-8",
    )
    log_path.with_suffix(".meta.json").write_text(
        json.dumps({"model": "gpt-5.4-mini", "role": "skill-selector"}),
        encoding="utf-8",
    )

    detail = module.parse_log(log_path)

    assert detail.model == "gpt-5.4-mini"
    assert detail.cost_estimated is True
    assert detail.cost_usd > 0


def test_render_log_structured_falls_back_for_plaintext(tmp_path):
    module = _load_module()
    log_path = tmp_path / "selector.stdout.log"
    log_path.write_text('phase_id: "PH-000"\nselector_model: "gpt-5"\n', encoding="utf-8")
    html = module._render_log_structured(log_path, "popup-plain")
    assert "phase_id" in html
    assert "selector_model" in html
    assert "log-unknown" not in html


def test_parse_prompt_runner_run_backfills_prompt_from_manifest_source(tmp_path):
    module = _load_module()
    run_dir = tmp_path / "run"
    prompt_dir = run_dir / "logs" / "prompt-01-generator-only"
    prompt_dir.mkdir(parents=True)

    fixture_log = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    stdout_log = prompt_dir / "iter-01-generator.stdout.log"
    stderr_log = prompt_dir / "iter-01-generator.stderr.log"
    stdout_log.write_text(fixture_log.read_text(encoding="utf-8"), encoding="utf-8")
    stderr_log.write_text("", encoding="utf-8")

    source_file = tmp_path / "source.md"
    source_file.write_text(
        """## Prompt 1: Generator only

```
Write docs/output.txt with RESULT: success.
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps({"source_file": str(source_file)}),
        encoding="utf-8",
    )

    shared_steps, fork_sections = module.parse_prompt_runner_run(run_dir)
    assert not fork_sections
    assert len(shared_steps) == 1
    assert "RESULT: success" in shared_steps[0].detail.prompt_text


def test_parse_prompt_runner_run_uses_manifest_start_for_sequential_step_timing(tmp_path):
    module = _load_module()
    run_dir = tmp_path / "run"
    prompt1 = run_dir / "logs" / "prompt-01-first"
    prompt2 = run_dir / "logs" / "prompt-02-second"
    prompt1.mkdir(parents=True)
    prompt2.mkdir(parents=True)

    fixture_log = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    gen1 = prompt1 / "iter-01-generator.stdout.log"
    err1 = prompt1 / "iter-01-generator.stderr.log"
    gen2 = prompt2 / "iter-01-generator.stdout.log"
    err2 = prompt2 / "iter-01-generator.stderr.log"
    gen1.write_text(fixture_log.read_text(encoding="utf-8"), encoding="utf-8")
    err1.write_text("", encoding="utf-8")
    gen2.write_text(fixture_log.read_text(encoding="utf-8"), encoding="utf-8")
    err2.write_text("", encoding="utf-8")

    source_file = tmp_path / "source.md"
    source_file.write_text(
        """## Prompt 1: First

```
Write docs/one.txt.
```

```
VERDICT: pass
```

## Prompt 2: Second

```
Write docs/two.txt.
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "source_file": str(source_file),
                "started_at": "2026-04-12T02:10:11Z",
            }
        ),
        encoding="utf-8",
    )

    first_end = 1775959989
    second_end = 1775960248
    gen1.touch()
    err1.touch()
    gen2.touch()
    err2.touch()
    import os
    os.utime(gen1, (first_end, first_end))
    os.utime(err1, (first_end, first_end))
    os.utime(gen2, (second_end, second_end))
    os.utime(err2, (second_end, second_end))

    shared_steps, _ = module.parse_prompt_runner_run(run_dir)

    assert len(shared_steps) == 2
    assert shared_steps[0].started.isoformat() == "2026-04-12T02:10:11+00:00"
    assert shared_steps[0].ended.isoformat() == "2026-04-12T02:13:09+00:00"
    assert shared_steps[1].started == shared_steps[0].ended
    assert shared_steps[1].ended.isoformat() == "2026-04-12T02:17:28+00:00"


def _write_codex_run(run_dir: Path, source_file: Path, step_name: str, prompt_text: str, output_text: str):
    prompt_dir = run_dir / "logs" / step_name
    prompt_dir.mkdir(parents=True)
    log = prompt_dir / "iter-01-generator.stdout.log"
    stderr = prompt_dir / "iter-01-generator.stderr.log"
    log.write_text(
        "\n".join(
            [
                '{"type":"thread.started","thread_id":"abc"}',
                '{"type":"turn.started"}',
                f'{{"type":"item.completed","item":{{"id":"item_0","type":"agent_message","text":{json.dumps(output_text)} }}}}',
                '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":20}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    stderr.write_text("", encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"source_file": str(source_file)}),
        encoding="utf-8",
    )


def test_parse_comparison_manifest_collapses_shared_prefix(tmp_path):
    module = _load_module()
    source_file_a = tmp_path / "source-a.md"
    source_file_b = tmp_path / "source-b.md"
    source_file_a.write_text(
        """## Prompt 1: Setup

```
Shared setup prompt.
```

```
VERDICT: pass
```

## Prompt 2: Variant work

```
Variant-specific prompt.
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    source_file_b.write_text(
        """## Prompt 1: Setup

```
Shared setup prompt.
```

```
VERDICT: pass
```

## Prompt 2: Variant work

```
Different variant-specific prompt.
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_codex_run(run_a, source_file_a, "prompt-01-setup", "Shared setup prompt.", "setup ok")
    _write_codex_run(run_a, source_file_a, "prompt-02-variant-work", "Variant-specific prompt.", "run a result")
    _write_codex_run(run_b, source_file_b, "prompt-01-setup", "Shared setup prompt.", "setup ok")
    _write_codex_run(run_b, source_file_b, "prompt-02-variant-work", "Different variant-specific prompt.", "run b result")

    manifest = tmp_path / "compare.json"
    manifest.write_text(
        json.dumps(
            {
                "title": "My Compare",
                "mode": "comparison",
                "runs": [
                    {"label": "A", "path": str(run_a)},
                    {"label": "B", "path": str(run_b)},
                ],
            }
        ),
        encoding="utf-8",
    )

    shared_steps, fork_sections, title = module.parse_comparison_manifest(manifest)
    assert title == "My Compare"
    assert len(shared_steps) == 1
    assert shared_steps[0].name == "prompt-01-setup / iter 01 generator"
    assert len(fork_sections) == 1
    assert sorted(fork_sections[0].variants) == ["variant-a", "variant-b"]
    assert all(len(steps) == 1 for steps in fork_sections[0].variants.values())


def test_parse_comparison_manifest_diagnostic_keeps_all_steps(tmp_path):
    module = _load_module()
    source_file = tmp_path / "source.md"
    source_file.write_text(
        """## Prompt 1: Setup

```
Shared setup prompt.
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_codex_run(run_a, source_file, "prompt-01-setup", "Shared setup prompt.", "setup ok")
    _write_codex_run(run_b, source_file, "prompt-01-setup", "Shared setup prompt.", "setup ok")

    manifest = tmp_path / "compare.json"
    manifest.write_text(
        json.dumps(
            {
                "title": "Diagnostic",
                "mode": "diagnostic",
                "runs": [
                    {"label": "A", "path": str(run_a)},
                    {"label": "B", "path": str(run_b)},
                ],
            }
        ),
        encoding="utf-8",
    )

    shared_steps, fork_sections, title = module.parse_comparison_manifest(manifest)
    assert title == "Diagnostic"
    assert shared_steps == []
    assert len(fork_sections) == 1
    assert all(len(steps) == 1 for steps in fork_sections[0].variants.values())


def test_load_report_document_uses_comparison_adapter(tmp_path):
    module = _load_module()
    source_file = tmp_path / "source.md"
    source_file.write_text(
        """## Prompt 1: Setup

```
Shared setup prompt.
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    run_a = tmp_path / "run-a"
    _write_codex_run(run_a, source_file, "prompt-01-setup", "Shared setup prompt.", "setup ok")
    manifest = tmp_path / "compare.json"
    manifest.write_text(
        json.dumps(
            {
                "title": "Adapter Check",
                "mode": "comparison",
                "runs": [{"label": "A", "path": str(run_a)}],
            }
        ),
        encoding="utf-8",
    )
    doc = module.load_report_document(manifest)
    assert doc.run_title == "Adapter Check"
    assert len(doc.fork_sections) == 1


def test_render_html_includes_elapsed_start_and_links_columns(tmp_path):
    module = _load_module()
    started = module._parse_iso_datetime("2026-04-12T02:10:11Z")
    ended = module._parse_iso_datetime("2026-04-12T02:13:09Z")
    assert started is not None
    assert ended is not None
    step = module.Step(
        name="prompt-01-build / iter 01 generator",
        started=started,
        ended=ended,
        size_bytes=1024,
        detail=module.CallDetail(
            backend="codex",
            output_tokens=20,
            prompt_text="Write docs/out.txt",
            output_text="done",
        ),
        log_path=tmp_path / "iter-01-generator.stdout.log",
    )
    step.log_path.write_text('{"type":"thread.started","thread_id":"abc"}\n', encoding="utf-8")
    doc = module.ReportDocument(
        run_title="Demo",
        workspace=tmp_path,
        shared_steps=[step],
    )

    html = module.render_html(doc)

    assert "<th>T+</th>" in html
    assert "<th>Start</th>" in html
    assert "<th>Links</th>" in html
    assert "0000s" in html
    assert module._fmt_clock(started) in html
    assert "prompt</a>" in html
    assert "output</a>" in html
    assert "log</a>" in html


def test_backfill_prompts_from_file_sets_model_and_estimates_cost(tmp_path):
    module = _load_module()
    prompt_file = tmp_path / "prompt-file.md"
    prompt_file.write_text(
        """## Prompt 1: Demo Step [MODEL:gpt-5.4-mini]

```
Write docs/out.txt
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    detail = module.CallDetail(
        backend="codex",
        input_tokens=1000,
        cache_read_tokens=500,
        output_tokens=200,
    )
    step = module.Step(
        name="prompt-01-demo-step / iter 01 generator",
        started=module._parse_iso_datetime("2026-04-12T02:10:11Z"),
        ended=module._parse_iso_datetime("2026-04-12T02:10:12Z"),
        detail=detail,
    )
    tl = module.PhaseTimeline(phase_id="PH-000", phase_number=0, steps=[step])

    module._backfill_prompts_from_file(tl, prompt_file)

    assert step.detail.prompt_text == "Write docs/out.txt"
    assert step.detail.model == "gpt-5.4-mini"
    assert step.detail.cost_estimated is True
    assert step.detail.cost_usd > 0


def test_parse_comparison_manifest_reports_missing_run_path(tmp_path):
    module = _load_module()
    manifest = tmp_path / "compare.json"
    manifest.write_text(
        json.dumps(
            {
                "title": "Missing",
                "mode": "comparison",
                "runs": [{"label": "A", "path": str(tmp_path / "nope")}],
            }
        ),
        encoding="utf-8",
    )
    try:
        module.parse_comparison_manifest(manifest)
    except ValueError as exc:
        assert "run path not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")
