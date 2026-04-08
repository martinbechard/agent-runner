"""Pipeline orchestration for prompt-runner.

See docs/design/components/CD-001-prompt-runner.md sections 9 and 11.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from prompt_runner.claude_client import (
    ClaudeCall,
    ClaudeClient,
    ClaudeInvocationError,
    ClaudeResponse,
)
from prompt_runner.parser import PromptPair
from prompt_runner.verdict import Verdict, VerdictParseError, parse_verdict


MAX_ITERATIONS_DEFAULT = 3
VERDICT_INSTRUCTION = (
    "End your response with a single line of the exact form: "
    "VERDICT: pass, VERDICT: revise, or VERDICT: escalate. "
    "Do not write anything after that line."
)
ANTI_ANCHORING_CLAUSE = (
    "Below is the revised artifact. Re-evaluate every checklist item against "
    "this current version. Items you previously failed may now pass, and items "
    "you previously passed may now fail if the revision broke them. Do not "
    "defer to your prior verdict."
)
REVISION_GENERATOR_PREAMBLE = (
    "The judge evaluated your previous artifact and returned the feedback "
    "below. Produce a revised artifact that addresses every fail or partial "
    "item. Do not drop content that already passed. Your response must be the "
    "complete revised artifact, with no commentary before or after it."
)
_HORIZONTAL_RULE = "\n\n---\n\n"


@dataclass(frozen=True)
class RunConfig:
    max_iterations: int = MAX_ITERATIONS_DEFAULT
    model: str | None = None
    only: int | None = None
    dry_run: bool = False


@dataclass(frozen=True)
class IterationResult:
    iteration: int
    generator_output: str
    judge_output: str
    verdict: Verdict


@dataclass(frozen=True)
class PromptResult:
    pair: PromptPair
    iterations: list[IterationResult]
    final_verdict: Verdict
    final_artifact: str


@dataclass(frozen=True)
class PipelineResult:
    prompt_results: list[PromptResult]
    halted_early: bool
    halt_reason: str | None


def build_initial_generator_message(
    pair: PromptPair, prior_artifacts: list[tuple[str, str]]
) -> str:
    if not prior_artifacts:
        return pair.generation_prompt
    prior_blocks = "\n\n".join(
        f"## {title}\n\n{body}" for title, body in prior_artifacts
    )
    return (
        f"# Prior approved artifacts\n\n{prior_blocks}"
        f"{_HORIZONTAL_RULE}"
        f"# Your task\n\n{pair.generation_prompt}"
    )


def build_initial_judge_message(pair: PromptPair, artifact: str) -> str:
    return (
        f"{pair.validation_prompt}"
        f"{_HORIZONTAL_RULE}"
        f"# Artifact to evaluate\n\n{artifact}"
        f"{_HORIZONTAL_RULE}"
        f"{VERDICT_INSTRUCTION}"
    )


def build_revision_generator_message(judge_output: str) -> str:
    return f"{REVISION_GENERATOR_PREAMBLE}\n\n# Judge feedback\n\n{judge_output}"


def build_revision_judge_message(new_artifact: str) -> str:
    return (
        f"{ANTI_ANCHORING_CLAUSE}\n\n"
        f"# Revised artifact\n\n{new_artifact}"
        f"{_HORIZONTAL_RULE}"
        f"{VERDICT_INSTRUCTION}"
    )


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    lowered = title.lower()
    slug = _SLUG_STRIP.sub("-", lowered).strip("-")
    return slug or "untitled"


def _prompt_dir_name(pair: PromptPair) -> str:
    return f"prompt-{pair.index:02d}-{_slugify(pair.title)}"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_call(
    *,
    prompt: str,
    session_id: str,
    new_session: bool,
    model: str | None,
    logs_dir: Path,
    iteration: int,
    role: str,
    pair: PromptPair,
) -> ClaudeCall:
    return ClaudeCall(
        prompt=prompt,
        session_id=session_id,
        new_session=new_session,
        model=model,
        stdout_log_path=logs_dir / f"iter-{iteration:02d}-{role}.stdout.log",
        stderr_log_path=logs_dir / f"iter-{iteration:02d}-{role}.stderr.log",
        stream_header=(
            f"── prompt {pair.index} '{pair.title}' / iter {iteration} / {role} ──"
        ),
    )


def run_prompt(
    pair: PromptPair,
    prior_artifacts: list[tuple[str, str]],
    run_dir: Path,
    config: RunConfig,
    claude_client: ClaudeClient,
    run_id: str,
) -> PromptResult:
    gen_session = f"gen-prompt-{pair.index}-{run_id}"
    jud_session = f"jud-prompt-{pair.index}-{run_id}"
    prompt_slug = _prompt_dir_name(pair)
    prompt_dir = run_dir / prompt_slug
    logs_dir = run_dir / "logs" / prompt_slug
    prompt_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    iterations: list[IterationResult] = []

    for iteration_number in range(1, config.max_iterations + 1):
        is_first = iteration_number == 1

        gen_msg = (
            build_initial_generator_message(pair, prior_artifacts)
            if is_first
            else build_revision_generator_message(iterations[-1].judge_output)
        )
        gen_call = _make_call(
            prompt=gen_msg,
            session_id=gen_session,
            new_session=is_first,
            model=config.model,
            logs_dir=logs_dir,
            iteration=iteration_number,
            role="generator",
            pair=pair,
        )
        gen_response = _call_or_persist_partial(
            claude_client, gen_call, prompt_dir / f"iter-{iteration_number:02d}-generator.md"
        )

        jud_msg = (
            build_initial_judge_message(pair, gen_response.stdout)
            if is_first
            else build_revision_judge_message(gen_response.stdout)
        )
        jud_call = _make_call(
            prompt=jud_msg,
            session_id=jud_session,
            new_session=is_first,
            model=config.model,
            logs_dir=logs_dir,
            iteration=iteration_number,
            role="judge",
            pair=pair,
        )
        jud_response = _call_or_persist_partial(
            claude_client, jud_call, prompt_dir / f"iter-{iteration_number:02d}-judge.md"
        )

        verdict = parse_verdict(jud_response.stdout)
        iterations.append(
            IterationResult(
                iteration=iteration_number,
                generator_output=gen_response.stdout,
                judge_output=jud_response.stdout,
                verdict=verdict,
            )
        )
        if verdict != Verdict.REVISE:
            break

    final = iterations[-1]
    final_verdict = final.verdict
    if final_verdict == Verdict.REVISE:
        final_verdict = Verdict.ESCALATE

    _write(prompt_dir / "final-artifact.md", final.generator_output)
    _write(prompt_dir / "final-verdict.txt", final_verdict.value + "\n")

    return PromptResult(
        pair=pair,
        iterations=iterations,
        final_verdict=final_verdict,
        final_artifact=final.generator_output,
    )


def _call_or_persist_partial(
    client: ClaudeClient, call: ClaudeCall, md_path: Path
) -> ClaudeResponse:
    """Invoke the client. On ClaudeInvocationError, write any partial stdout to
    md_path before re-raising so the runner's halt semantics are preserved."""
    try:
        response = client.call(call)
    except ClaudeInvocationError as err:
        _write(md_path, err.response.stdout)
        raise
    _write(md_path, response.stdout)
    return response


def run_pipeline(
    pairs: list[PromptPair],
    run_dir: Path,
    config: RunConfig,
    claude_client: ClaudeClient,
    source_file: Path,
) -> PipelineResult:
    run_id = run_dir.name
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(run_dir, source_file, config, run_id, started_at=_now_iso())

    prior_artifacts: list[tuple[str, str]] = []
    prompt_results: list[PromptResult] = []

    for pair in pairs:
        if config.only is not None and pair.index != config.only:
            continue
        try:
            result = run_prompt(
                pair, prior_artifacts, run_dir, config, claude_client, run_id
            )
        except VerdictParseError as err:
            halt_reason = (
                f"R-NO-VERDICT: prompt {pair.index} \"{pair.title}\" "
                f"returned a judge response with no VERDICT line. {err}"
            )
            _finalise(run_dir, source_file, config, run_id, prompt_results,
                      halted_early=True, halt_reason=halt_reason)
            return PipelineResult(prompt_results, halted_early=True, halt_reason=halt_reason)
        except ClaudeInvocationError as err:
            halt_reason = (
                f"R-CLAUDE-FAILED: prompt {pair.index} \"{pair.title}\" "
                f"{err.call.stream_header} exited with status "
                f"{err.response.returncode}."
            )
            _finalise(run_dir, source_file, config, run_id, prompt_results,
                      halted_early=True, halt_reason=halt_reason)
            return PipelineResult(prompt_results, halted_early=True, halt_reason=halt_reason)

        prompt_results.append(result)
        if result.final_verdict == Verdict.PASS:
            prior_artifacts.append((pair.title, result.final_artifact))
        else:
            halt_reason = f"prompt {pair.index} escalated"
            _finalise(run_dir, source_file, config, run_id, prompt_results,
                      halted_early=True, halt_reason=halt_reason)
            return PipelineResult(prompt_results, halted_early=True, halt_reason=halt_reason)

    _finalise(run_dir, source_file, config, run_id, prompt_results,
              halted_early=False, halt_reason=None)
    return PipelineResult(prompt_results, halted_early=False, halt_reason=None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_manifest(
    run_dir: Path, source_file: Path, config: RunConfig, run_id: str, started_at: str
) -> None:
    manifest = {
        "source_file": str(source_file.resolve()),
        "run_id": run_id,
        "config": {
            "max_iterations": config.max_iterations,
            "model": config.model,
            "only": config.only,
            "dry_run": config.dry_run,
        },
        "started_at": started_at,
        "finished_at": None,
    }
    _write(run_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n")


def _finalise(
    run_dir: Path,
    source_file: Path,
    config: RunConfig,
    run_id: str,
    prompt_results: list[PromptResult],
    halted_early: bool,
    halt_reason: str | None,
) -> None:
    # Rewrite manifest.json with finished_at and halt_reason.
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["finished_at"] = _now_iso()
    manifest["halt_reason"] = halt_reason
    _write(manifest_path, json.dumps(manifest, indent=2) + "\n")

    _write(run_dir / "summary.txt", _format_summary(
        source_file, run_dir, prompt_results, halted_early, halt_reason
    ))


def _format_summary(
    source_file: Path,
    run_dir: Path,
    prompt_results: list[PromptResult],
    halted_early: bool,
    halt_reason: str | None,
) -> str:
    status = "halted" if halted_early else "completed"
    lines = [
        "Prompt Runner — Run Summary",
        f"Source: {source_file}",
        f"Run:    {run_dir}",
        f"Status: {status}",
        "",
        "Prompts:",
    ]
    for result in prompt_results:
        slug = _prompt_dir_name(result.pair)
        iter_count = len(result.iterations)
        lines.append(
            f"  {result.pair.index:02d}  {slug:<40s}  {result.final_verdict.value:<9s}  {iter_count} iter"
        )
    total_calls = sum(len(r.iterations) * 2 for r in prompt_results)
    lines.append("")
    lines.append(f"Total claude calls: {total_calls}")
    if halt_reason:
        lines.append(f"Halt reason: {halt_reason}")
    lines.append("")
    return "\n".join(lines)
