import json
from pathlib import Path

from prompt_runner.claude_client import FakeClaudeClient
from prompt_runner.config import PromptRunnerConfig, RunDefaults, default_optimize_defaults
from prompt_runner.optimizer import (
    OptimizeResult,
    OptimizationError,
    build_prompt_candidates,
    optimize_prompt_file,
    resolve_requested_candidates,
    synthesize_optimization_items,
)
from prompt_runner.parser import ForkPoint, PromptPair
from prompt_runner.runner import ForkResult, RunConfig, VariantResult


def _pair(
    index: int,
    title: str,
    *,
    validation_prompt: str = "judge",
) -> PromptPair:
    return PromptPair(
        index=index,
        title=title,
        generation_prompt="generate",
        validation_prompt=validation_prompt,
        retry_prompt="",
        heading_line=1,
        generation_line=2,
        validation_line=5,
        retry_line=0,
    )


def test_resolve_requested_candidates_defaults_to_balanced_profile():
    optimize = default_optimize_defaults()

    candidates, profile_name, profile = resolve_requested_candidates(
        optimize,
        profile_name=None,
        candidate_specs=[],
    )

    assert profile_name == "balanced"
    assert profile is not None
    assert [(candidate.model, candidate.effort) for candidate in candidates] == [
        ("gpt-5.4-mini", "low"),
        ("gpt-5.4-mini", "medium"),
        ("gpt-5.3-codex", "medium"),
        ("gpt-5.4", "medium"),
        ("gpt-5.5", "medium"),
    ]


def test_build_prompt_candidates_deduplicates_baseline_effective():
    optimize = default_optimize_defaults()
    pair = _pair(1, "Alpha")
    requested_candidates = [
        candidate
        for candidate in resolve_requested_candidates(
            optimize,
            profile_name=None,
            candidate_specs=["gpt_5_3_codex:medium"],
        )[0]
    ]

    prompt_candidates = build_prompt_candidates(
        pair,
        requested_candidates=requested_candidates,
        include_baseline_effective=True,
        run_config=RunConfig(model="gpt-5.3-codex"),
        optimize=optimize,
    )

    assert [candidate.variant_name for candidate in prompt_candidates] == ["cand-01"]
    assert prompt_candidates[0].model == "gpt-5.3-codex"
    assert prompt_candidates[0].effort == "medium"


def test_synthesize_optimization_items_wraps_only_judged_prompts():
    optimize = default_optimize_defaults()
    source_items = [
        _pair(1, "Alpha"),
        _pair(2, "Beta", validation_prompt=""),
    ]
    requested_candidates = resolve_requested_candidates(
        optimize,
        profile_name="quick",
        candidate_specs=[],
    )[0]

    synthesized, prompt_candidates = synthesize_optimization_items(
        source_items,
        requested_candidates=requested_candidates,
        active_profile=optimize.profiles["quick"],
        run_config=RunConfig(model="gpt-5.3-codex"),
        optimize=optimize,
    )

    assert isinstance(synthesized[0], ForkPoint)
    assert synthesized[0].selector_prompt
    assert synthesized[1] == source_items[1]
    assert 1 in prompt_candidates
    assert 2 not in prompt_candidates


def test_synthesize_optimization_items_rejects_existing_forks():
    optimize = default_optimize_defaults()
    source_items = [
        ForkPoint(index=1, title="Fork", heading_line=1, variants=[]),
    ]

    try:
        synthesize_optimization_items(
            source_items,
            requested_candidates=[],
            active_profile=None,
            run_config=RunConfig(model="gpt-5.3-codex"),
            optimize=optimize,
        )
    except OptimizationError as err:
        assert "[VARIANTS]" in str(err)
    else:
        raise AssertionError("expected OptimizationError")


def test_optimize_prompt_file_writes_optimized_prompt_and_report(tmp_path: Path, monkeypatch):
    source_file = tmp_path / "source.prompt.md"
    source_file.write_text(
        "## Prompt 1: Alpha\n\n### Generation Prompt\n\ngenerate\n\n### Validation Prompt\n\njudge\n",
        encoding="utf-8",
    )
    source_items = [_pair(1, "Alpha")]
    exercise_root = tmp_path / "exercise"

    config = PromptRunnerConfig(
        path=None,
        run=RunDefaults(backend="codex", model="gpt-5.3-codex"),
        optimize=default_optimize_defaults(),
    )
    run_config = RunConfig(backend="codex", model="gpt-5.3-codex")

    def _write_manifest(run_dir: Path, source: Path) -> None:
        run_files = run_dir / ".run-files"
        run_files.mkdir(parents=True, exist_ok=True)
        (run_files / "manifest.json").write_text(
            json.dumps(
                {
                    "source_file": str(source.resolve()),
                    "source_file_sha256": __import__("hashlib").sha256(source.read_bytes()).hexdigest(),
                    "run_id": run_dir.name,
                    "config": {
                        "backend": "codex",
                        "model": "gpt-5.3-codex",
                        "default_effort": "medium",
                    },
                    "started_at": "2026-04-23T00:00:00Z",
                    "finished_at": "2026-04-23T00:00:01Z",
                    "halt_reason": None,
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    def fake_run_pipeline(*, pairs, run_dir, config, claude_client, source_file, source_project_dir, **kwargs):
        _write_manifest(run_dir, source_file)
        module_dir = run_dir / ".run-files" / "alpha"
        module_dir.mkdir(parents=True, exist_ok=True)
        (module_dir / "summary.txt").write_text("summary\n", encoding="utf-8")
        if source_file.name == "source.prompt.md":
            (module_dir / "prompt-01.metrics.json").write_text(
                json.dumps(
                    {
                        "prompt_index": 1,
                        "prompt_title": "Alpha",
                        "final_verdict": "pass",
                        "iterations_used": 2,
                        "wall_time_seconds": 5.0,
                        "input_tokens": 20,
                        "cached_input_tokens": 0,
                        "output_tokens": 10,
                        "total_tokens": 30,
                        "model": "gpt-5.3-codex",
                        "effort": "medium",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            from prompt_runner.runner import PipelineResult

            return PipelineResult(prompt_results=[], halted_early=False, halt_reason=None)

        synthetic_fork = next(item for item in pairs if isinstance(item, ForkPoint))
        selector_dir = (
            run_dir
            / ".run-files"
            / "alpha"
            / "prompt-01.selection"
            / "selector"
        )
        selector_dir.mkdir(parents=True, exist_ok=True)
        (selector_dir / "candidate-scorecard.json").write_text("{}\n", encoding="utf-8")
        from prompt_runner.runner import PipelineResult

        return PipelineResult(
            prompt_results=[],
            halted_early=False,
            halt_reason=None,
            fork_results=[
                ForkResult(
                    fork_index=1,
                    fork_title="Alpha",
                    variant_results=[
                        VariantResult(
                            variant_name="baseline",
                            variant_title="gpt-5.3-codex / medium",
                            exit_code=0,
                            run_dir=run_dir,
                            worktree_dir=run_dir,
                            summary="baseline summary",
                            final_verdict="pass",
                            metrics={
                                "iterations_used": 2,
                                "wall_time_seconds": 5.0,
                                "input_tokens": 20,
                                "cached_input_tokens": 0,
                                "output_tokens": 10,
                                "total_tokens": 30,
                            },
                        ),
                        VariantResult(
                            variant_name="cand-01",
                            variant_title="gpt-5.4 / medium",
                            exit_code=0,
                            run_dir=run_dir,
                            worktree_dir=run_dir,
                            summary="candidate summary",
                            final_verdict="pass",
                            metrics={
                                "iterations_used": 1,
                                "wall_time_seconds": 3.0,
                                "input_tokens": 12,
                                "cached_input_tokens": 0,
                                "output_tokens": 6,
                                "total_tokens": 18,
                            },
                        ),
                    ],
                    selected_variant="cand-01",
                    selector_rationale="fewer iterations and lower total tokens",
                )
            ],
        )

    monkeypatch.setattr("prompt_runner.optimizer.run_pipeline", fake_run_pipeline)

    result = optimize_prompt_file(
        source_file=source_file,
        items=source_items,
        file_config=config,
        run_config=run_config,
        claude_client=FakeClaudeClient(scripted=[]),
        profile_name=None,
        candidate_specs=["gpt_5_4:medium"],
        baseline_run_dir=None,
        exercise_root=exercise_root,
        source_project_dir=tmp_path,
    )

    optimized_text = result.optimized_prompt_file.read_text(encoding="utf-8")
    report_text = result.report_path.read_text(encoding="utf-8")
    assert "[MODEL:gpt-5.4]" in optimized_text
    assert "[EFFORT:medium]" in optimized_text
    assert "Optimized" in report_text
    assert "gpt-5.4 / medium" in report_text
