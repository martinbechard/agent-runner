"""Optimization orchestration for prompt-runner."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from prompt_runner.claude_client import ClaudeClient
from prompt_runner.config import (
    OptimizeDefaults,
    OptimizeModel,
    OptimizeProfile,
    PromptRunnerConfig,
)
from prompt_runner.parser import ForkPoint, PromptPair, VariantPrompt
from prompt_runner.runner import (
    RUN_FILES_DIRNAME,
    ForkResult,
    PipelineResult,
    RunConfig,
    _load_run_prompt_metrics,
    _selection_dir,
    _serialize_pairs_to_md,
    run_pipeline,
)


class OptimizationError(Exception):
    """Raised when the optimize workflow cannot proceed safely."""


@dataclass(frozen=True)
class ResolvedCandidate:
    model: str
    effort: str
    duration_name: str
    origin: str
    profile_source: str | None = None
    model_key: str | None = None


@dataclass(frozen=True)
class PromptCandidate:
    variant_name: str
    variant_title: str
    model: str
    effort: str
    duration_name: str
    origin: str
    profile_source: str | None = None
    model_key: str | None = None


@dataclass(frozen=True)
class PromptOptimizationDecision:
    prompt_index: int
    prompt_title: str
    selected_variant: str
    selected_model: str
    selected_effort: str
    selector_rationale: str
    scorecard_path: Path
    metrics: dict[str, object]


@dataclass(frozen=True)
class OptimizeResult:
    exercise_root: Path
    baseline_run_dir: Path
    optimization_run_dir: Path
    optimization_prompt_file: Path
    optimized_prompt_file: Path
    report_path: Path
    decisions: list[PromptOptimizationDecision]


def _optimizations_root(project_dir: Path | None) -> Path:
    base = project_dir.resolve() if project_dir is not None else Path.cwd().resolve()
    return base / ".prompt-runner" / "optimizations"


def default_exercise_dir(source: Path, project_dir: Path | None = None) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return _optimizations_root(project_dir) / f"{ts}-{source.stem}"


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_duration_name(value: str, optimize: OptimizeDefaults) -> str:
    normalized = value.strip().lower()
    return optimize.duration_aliases.get(normalized, normalized)


def _duration_to_effort(duration_name: str, optimize: OptimizeDefaults) -> str:
    normalized = _normalize_duration_name(duration_name, optimize)
    duration = optimize.durations.get(normalized)
    if duration is None:
        raise OptimizationError(f"unknown optimization duration '{duration_name}'")
    return duration.effort


def _resolve_model_ref(model_ref: str, optimize: OptimizeDefaults) -> tuple[str, OptimizeModel]:
    if model_ref in optimize.models:
        return model_ref, optimize.models[model_ref]
    for key, model in optimize.models.items():
        if model.model == model_ref:
            return key, model
    raise OptimizationError(
        f"unknown optimization model '{model_ref}'. Add it to [optimize.models] first."
    )


def _candidate_identity(model: str, effort: str) -> tuple[str, str]:
    return model, effort.strip().lower()


def _resolve_cli_candidates(
    optimize: OptimizeDefaults,
    candidate_specs: list[str],
) -> list[ResolvedCandidate]:
    resolved: list[ResolvedCandidate] = []
    for spec in candidate_specs:
        model_ref, separator, duration_ref = spec.partition(":")
        model_key, model = _resolve_model_ref(model_ref.strip(), optimize)
        if separator:
            duration_name = _normalize_duration_name(duration_ref, optimize)
            durations = (duration_name,)
        else:
            durations = model.recommended_durations
        for duration_name in durations:
            if duration_name not in model.allowed_durations:
                raise OptimizationError(
                    f"duration '{duration_name}' is not allowed for model '{model_ref}'."
                )
            resolved.append(
                ResolvedCandidate(
                    model=model.model,
                    effort=_duration_to_effort(duration_name, optimize),
                    duration_name=duration_name,
                    origin="cli",
                    profile_source=None,
                    model_key=model_key,
                )
            )
    return resolved


def _resolve_profile_candidates(
    optimize: OptimizeDefaults,
    profile_name: str,
) -> list[ResolvedCandidate]:
    profile = optimize.profiles.get(profile_name)
    if profile is None:
        raise OptimizationError(f"unknown optimization profile '{profile_name}'.")
    resolved: list[ResolvedCandidate] = []
    for entry in profile.entries:
        model = optimize.models[entry.model]
        durations = entry.durations or model.recommended_durations
        for duration_name in durations:
            if duration_name not in model.allowed_durations:
                raise OptimizationError(
                    f"profile '{profile_name}' uses unsupported duration "
                    f"'{duration_name}' for model '{entry.model}'."
                )
            resolved.append(
                ResolvedCandidate(
                    model=model.model,
                    effort=_duration_to_effort(duration_name, optimize),
                    duration_name=duration_name,
                    origin="profile",
                    profile_source=profile_name,
                    model_key=entry.model,
                )
            )
    return resolved


def resolve_requested_candidates(
    optimize: OptimizeDefaults,
    *,
    profile_name: str | None,
    candidate_specs: list[str],
) -> tuple[list[ResolvedCandidate], str | None, OptimizeProfile | None]:
    active_profile_name: str | None
    profile: OptimizeProfile | None = None
    if profile_name is not None:
        active_profile_name = profile_name
    elif candidate_specs:
        active_profile_name = None
    else:
        active_profile_name = optimize.default_profile

    candidates: list[ResolvedCandidate] = []
    if active_profile_name is not None:
        profile = optimize.profiles.get(active_profile_name)
        if profile is None:
            raise OptimizationError(f"unknown optimization profile '{active_profile_name}'.")
        candidates.extend(_resolve_profile_candidates(optimize, active_profile_name))
    candidates.extend(_resolve_cli_candidates(optimize, candidate_specs))

    deduped: list[ResolvedCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        identity = _candidate_identity(candidate.model, candidate.effort)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(candidate)
    return deduped, active_profile_name, profile


def _effective_prompt_candidate(
    pair: PromptPair,
    run_config: RunConfig,
    optimize: OptimizeDefaults,
) -> ResolvedCandidate:
    effective_model = pair.model_override or run_config.model
    if not effective_model:
        raise OptimizationError(
            f"prompt {pair.index} '{pair.title}' has no effective model. "
            "Set [MODEL:...] on the prompt or pass --model / configure [run].model."
        )
    effective_effort = pair.effort_override or run_config.default_effort
    if not effective_effort:
        raise OptimizationError(
            f"prompt {pair.index} '{pair.title}' has no effective effort."
        )
    duration_name = _normalize_duration_name(effective_effort, optimize)
    if duration_name not in optimize.durations:
        raise OptimizationError(
            f"prompt {pair.index} '{pair.title}' uses unsupported effort "
            f"'{effective_effort}' for optimization."
        )
    return ResolvedCandidate(
        model=effective_model,
        effort=_duration_to_effort(duration_name, optimize),
        duration_name=duration_name,
        origin="baseline",
    )


def build_prompt_candidates(
    pair: PromptPair,
    *,
    requested_candidates: list[ResolvedCandidate],
    include_baseline_effective: bool,
    run_config: RunConfig,
    optimize: OptimizeDefaults,
) -> list[PromptCandidate]:
    candidates: list[ResolvedCandidate] = list(requested_candidates)
    baseline_candidate = _effective_prompt_candidate(pair, run_config, optimize)
    if include_baseline_effective:
        identity = _candidate_identity(baseline_candidate.model, baseline_candidate.effort)
        if not any(
            _candidate_identity(candidate.model, candidate.effort) == identity
            for candidate in candidates
        ):
            candidates.insert(0, baseline_candidate)

    prompt_candidates: list[PromptCandidate] = []
    candidate_counter = 0
    for candidate in candidates:
        if candidate.origin == "baseline":
            variant_name = "baseline"
        else:
            candidate_counter += 1
            variant_name = f"cand-{candidate_counter:02d}"
        prompt_candidates.append(
            PromptCandidate(
                variant_name=variant_name,
                variant_title=f"{candidate.model} / {candidate.duration_name}",
                model=candidate.model,
                effort=candidate.effort,
                duration_name=candidate.duration_name,
                origin=candidate.origin,
                profile_source=candidate.profile_source,
                model_key=candidate.model_key,
            )
        )
    return prompt_candidates


def _copy_pair_with_overrides(pair: PromptPair, *, model: str, effort: str) -> PromptPair:
    return PromptPair(
        index=pair.index,
        title=pair.title,
        generation_prompt=pair.generation_prompt,
        validation_prompt=pair.validation_prompt,
        retry_prompt=pair.retry_prompt,
        heading_line=pair.heading_line,
        generation_line=pair.generation_line,
        validation_line=pair.validation_line,
        retry_line=pair.retry_line,
        required_files=pair.required_files,
        include_files=pair.include_files,
        checks_files=pair.checks_files,
        deterministic_validation=pair.deterministic_validation,
        retry_mode=pair.retry_mode,
        module_slug=pair.module_slug,
        interactive=pair.interactive,
        model_override=model,
        effort_override=effort,
    )


def _selector_prompt(pair: PromptPair) -> str:
    return (
        f"You are selecting the best model setting for prompt {pair.index}: {pair.title}.\n\n"
        "Choose exactly one candidate whose `Final verdict` is `pass`.\n"
        "Ranking rules:\n"
        "1. A passing candidate always beats a revise or escalate candidate.\n"
        "2. Among passing candidates, prefer fewer `Iterations used`.\n"
        "3. If iterations tie, prefer lower `Wall time`.\n"
        "4. If wall time ties, prefer lower `Total tokens`.\n"
        "5. Use the summary and changed files only as tie-break context, not as a substitute for the scorecard.\n\n"
        "If no candidate passed, emit `VERDICT: escalate` and explain that no candidate converged acceptably."
    )


def _selector_retry_prompt() -> str:
    return (
        "Produce a valid selector decision using the required output schema. "
        "Do not select a non-passing candidate."
    )


def _validate_source_items(items: list[PromptPair | ForkPoint]) -> list[PromptPair]:
    normalized: list[PromptPair] = []
    for item in items:
        if isinstance(item, ForkPoint):
            raise OptimizationError(
                "optimize does not yet support source files that already contain [VARIANTS] or [SELECT]."
            )
        if item.interactive:
            raise OptimizationError(
                "optimize does not yet support [interactive] prompts."
            )
        normalized.append(item)
    return normalized


def synthesize_optimization_items(
    items: list[PromptPair | ForkPoint],
    *,
    requested_candidates: list[ResolvedCandidate],
    active_profile: OptimizeProfile | None,
    run_config: RunConfig,
    optimize: OptimizeDefaults,
) -> tuple[list[PromptPair | ForkPoint], dict[int, list[PromptCandidate]]]:
    source_pairs = _validate_source_items(items)
    include_baseline_effective = (
        active_profile.include_baseline_effective
        if active_profile is not None and active_profile.include_baseline_effective is not None
        else optimize.include_baseline_effective
    )
    synthesized: list[PromptPair | ForkPoint] = []
    prompt_candidates: dict[int, list[PromptCandidate]] = {}
    for pair in source_pairs:
        if not pair.validation_prompt.strip():
            synthesized.append(pair)
            continue
        candidates = build_prompt_candidates(
            pair,
            requested_candidates=requested_candidates,
            include_baseline_effective=include_baseline_effective,
            run_config=run_config,
            optimize=optimize,
        )
        prompt_candidates[pair.index] = candidates
        synthesized.append(
            ForkPoint(
                index=pair.index,
                title=pair.title,
                heading_line=pair.heading_line,
                variants=[
                    VariantPrompt(
                        variant_name=candidate.variant_name,
                        variant_title=candidate.variant_title,
                        pairs=[
                            _copy_pair_with_overrides(
                                pair,
                                model=candidate.model,
                                effort=candidate.effort,
                            )
                        ],
                    )
                    for candidate in candidates
                ],
                selector_prompt=_selector_prompt(pair),
                selector_retry_prompt=_selector_retry_prompt(),
            )
        )
    return synthesized, prompt_candidates


def _append_pair_sections(lines: list[str], pair: PromptPair, *, heading_prefix: str) -> None:
    if pair.required_files:
        lines.extend([f"{heading_prefix} Required Files", ""])
        lines.extend(pair.required_files)
        lines.append("")
    if pair.include_files:
        lines.extend([f"{heading_prefix} Include Files", ""])
        lines.extend(pair.include_files)
        lines.append("")
    if pair.checks_files:
        lines.extend([f"{heading_prefix} Checks Files", ""])
        lines.extend(pair.checks_files)
        lines.append("")
    if pair.deterministic_validation:
        lines.extend([f"{heading_prefix} Deterministic Validation", ""])
        lines.extend(pair.deterministic_validation)
        lines.append("")
    lines.extend([f"{heading_prefix} Generation Prompt", "", pair.generation_prompt])
    if pair.validation_prompt:
        lines.extend(["", f"{heading_prefix} Validation Prompt", "", pair.validation_prompt])
    if pair.retry_prompt:
        retry_heading = f"{heading_prefix} Retry Prompt"
        if pair.retry_mode != "replace":
            retry_heading += f" [{pair.retry_mode.upper()}]"
        lines.extend(["", retry_heading, "", pair.retry_prompt])


def serialize_items_to_md(items: list[PromptPair | ForkPoint]) -> str:
    sections: list[str] = []
    representative_pair: PromptPair | None = None
    for item in items:
        if isinstance(item, PromptPair):
            representative_pair = item
            break
        if item.variants and item.variants[0].pairs:
            representative_pair = item.variants[0].pairs[0]
            break
    module_slug = representative_pair.module_slug if representative_pair else None
    if module_slug:
        sections.extend(["### Module", "", module_slug, ""])

    for item in items:
        if isinstance(item, PromptPair):
            lines = [f"## Prompt {item.index}: {item.title}"]
            if item.model_override:
                lines[0] += f" [MODEL:{item.model_override}]"
            if item.effort_override:
                lines[0] += f" [EFFORT:{item.effort_override}]"
            lines.append("")
            _append_pair_sections(lines, item, heading_prefix="###")
            sections.append("\n".join(lines))
            continue

        lines = [f"## Prompt {item.index}: {item.title} [VARIANTS] [SELECT]", ""]
        for variant in item.variants:
            lines.extend([f"### Variant {variant.variant_name}: {variant.variant_title}", ""])
            for pair in variant.pairs:
                _append_pair_sections(lines, pair, heading_prefix="####")
                lines.append("")
        lines.extend(["### Selection Prompt", "", item.selector_prompt])
        if item.selector_retry_prompt:
            lines.extend(["", "### Selection Retry Prompt", "", item.selector_retry_prompt])
        sections.append("\n".join(lines).rstrip())
    return "\n\n".join(sections).rstrip() + "\n"


def _read_summary_text(run_dir: Path) -> str:
    run_files_dir = run_dir / RUN_FILES_DIRNAME
    root_summary = run_files_dir / "summary.txt"
    if root_summary.exists():
        return root_summary.read_text(encoding="utf-8")
    module_summaries = sorted(run_files_dir.glob("*/summary.txt"))
    if module_summaries:
        return module_summaries[0].read_text(encoding="utf-8")
    return ""


def _read_manifest(run_dir: Path) -> dict[str, object]:
    manifest_path = run_dir / RUN_FILES_DIRNAME / "manifest.json"
    if not manifest_path.exists():
        raise OptimizationError(f"baseline run is missing manifest.json: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OptimizationError(f"baseline manifest is invalid JSON: {manifest_path}") from exc
    if not isinstance(payload, dict):
        raise OptimizationError(f"baseline manifest is malformed: {manifest_path}")
    return payload


def _metrics_by_prompt_index(run_dir: Path) -> dict[int, dict[str, object]]:
    metrics: dict[int, dict[str, object]] = {}
    for payload in _load_run_prompt_metrics(run_dir):
        try:
            prompt_index = int(payload.get("prompt_index", 0))
        except (TypeError, ValueError):
            continue
        metrics[prompt_index] = payload
    return metrics


def _validate_baseline_run_dir(
    run_dir: Path,
    *,
    source_file: Path,
    run_config: RunConfig,
    expected_prompt_count: int,
) -> dict[str, object]:
    manifest = _read_manifest(run_dir)
    if manifest.get("source_file_sha256") != _file_sha256(source_file):
        raise OptimizationError(
            f"baseline run {run_dir} was produced from a different source prompt file."
        )
    config = manifest.get("config", {})
    if not isinstance(config, dict):
        raise OptimizationError(f"baseline manifest has invalid config payload: {run_dir}")
    manifest_backend = config.get("backend")
    if manifest_backend != run_config.backend:
        raise OptimizationError(
            f"baseline run backend mismatch: expected {run_config.backend}, found {manifest_backend!r}."
        )
    if manifest.get("halt_reason"):
        raise OptimizationError(
            f"baseline run did not complete successfully: {manifest.get('halt_reason')}"
        )
    if not manifest.get("finished_at"):
        raise OptimizationError(f"baseline run is incomplete: {run_dir}")
    metrics = _metrics_by_prompt_index(run_dir)
    if len(metrics) < expected_prompt_count:
        raise OptimizationError(
            f"baseline run is missing prompt metrics. Expected {expected_prompt_count}, found {len(metrics)}."
        )
    return manifest


def _copy_baseline_reference(
    exercise_root: Path,
    *,
    baseline_run_dir: Path,
    manifest: dict[str, object],
    reused: bool,
) -> None:
    baseline_reference = {
        "baseline_run_dir": str(baseline_run_dir.resolve()),
        "reused": reused,
        "manifest": manifest,
    }
    (exercise_root / "baseline-reference.json").write_text(
        json.dumps(baseline_reference, indent=2) + "\n",
        encoding="utf-8",
    )
    (exercise_root / "baseline-summary.md").write_text(
        _read_summary_text(baseline_run_dir),
        encoding="utf-8",
    )


def _selected_variant_result(fork_result: ForkResult) -> dict[str, object]:
    if fork_result.selected_variant is None:
        raise OptimizationError(
            f"optimization fork {fork_result.fork_index} did not select a passing variant."
        )
    selected = next(
        (result for result in fork_result.variant_results if result.variant_name == fork_result.selected_variant),
        None,
    )
    if selected is None:
        raise OptimizationError(
            f"selected variant '{fork_result.selected_variant}' is missing from fork {fork_result.fork_index}."
        )
    if selected.metrics is None:
        raise OptimizationError(
            f"selected variant '{fork_result.selected_variant}' is missing prompt metrics."
        )
    return {
        "variant_name": selected.variant_name,
        "variant_title": selected.variant_title,
        "metrics": selected.metrics,
    }


def _optimized_pair(
    pair: PromptPair,
    decision: PromptOptimizationDecision | None,
) -> PromptPair:
    if decision is None:
        return pair
    return _copy_pair_with_overrides(
        pair,
        model=decision.selected_model,
        effort=decision.selected_effort,
    )


def _sum_metric_fields(metrics: list[dict[str, object]]) -> dict[str, float | int]:
    return {
        "wall_time_seconds": sum(float(item.get("wall_time_seconds", 0.0) or 0.0) for item in metrics),
        "input_tokens": sum(int(item.get("input_tokens", 0) or 0) for item in metrics),
        "cached_input_tokens": sum(int(item.get("cached_input_tokens", 0) or 0) for item in metrics),
        "output_tokens": sum(int(item.get("output_tokens", 0) or 0) for item in metrics),
        "total_tokens": sum(int(item.get("total_tokens", 0) or 0) for item in metrics),
    }


def _format_totals(label: str, totals: dict[str, float | int]) -> list[str]:
    return [
        f"## {label}",
        f"- Wall time: {float(totals['wall_time_seconds']):.3f}s",
        f"- Input tokens: {int(totals['input_tokens'])}",
        f"- Cached input tokens: {int(totals['cached_input_tokens'])}",
        f"- Output tokens: {int(totals['output_tokens'])}",
        f"- Total tokens: {int(totals['total_tokens'])}",
        "",
    ]


def _write_report(
    report_path: Path,
    *,
    source_pairs: list[PromptPair],
    baseline_metrics_by_prompt: dict[int, dict[str, object]],
    optimization_metrics_by_prompt: dict[int, dict[str, object]],
    decisions: list[PromptOptimizationDecision],
) -> None:
    decision_by_index = {decision.prompt_index: decision for decision in decisions}
    baseline_metrics = [baseline_metrics_by_prompt[pair.index] for pair in source_pairs]
    optimized_metrics: list[dict[str, object]] = []
    lines = [
        "# Prompt Runner Model Optimization Report",
        "",
        "Optimized totals are projected from the selected candidate metrics for optimizable prompts and the top-level optimization run metrics for unchanged prompts.",
        "",
    ]
    for pair in source_pairs:
        decision = decision_by_index.get(pair.index)
        if decision is not None:
            optimized_metrics.append(decision.metrics)
        else:
            metric = optimization_metrics_by_prompt.get(pair.index, baseline_metrics_by_prompt[pair.index])
            optimized_metrics.append(metric)

    lines.extend(_format_totals("Baseline", _sum_metric_fields(baseline_metrics)))
    lines.extend(_format_totals("Optimized", _sum_metric_fields(optimized_metrics)))

    lines.extend(["## Per-prompt winners", ""])
    for pair in source_pairs:
        decision = decision_by_index.get(pair.index)
        if decision is None:
            lines.append(f"- Prompt {pair.index}: {pair.title} -> unchanged")
            continue
        lines.append(
            f"- Prompt {pair.index}: {pair.title} -> {decision.selected_model} / {decision.selected_effort} "
            f"(iterations={decision.metrics.get('iterations_used', 0)}, "
            f"wall_time={float(decision.metrics.get('wall_time_seconds', 0.0) or 0.0):.3f}s, "
            f"total_tokens={int(decision.metrics.get('total_tokens', 0) or 0)})"
        )
        if decision.selector_rationale:
            lines.append(f"  rationale: {decision.selector_rationale}")
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def optimize_prompt_file(
    *,
    source_file: Path,
    items: list[PromptPair | ForkPoint],
    file_config: PromptRunnerConfig,
    run_config: RunConfig,
    claude_client: ClaudeClient,
    profile_name: str | None,
    candidate_specs: list[str],
    baseline_run_dir: Path | None,
    exercise_root: Path,
    source_project_dir: Path | None,
) -> OptimizeResult:
    if run_config.backend != "codex":
        raise OptimizationError("optimize currently supports only the codex backend.")

    source_pairs = _validate_source_items(items)
    if not any(pair.validation_prompt.strip() for pair in source_pairs):
        raise OptimizationError("optimize requires at least one prompt with a validation prompt.")

    exercise_root = exercise_root.resolve()
    exercise_root.mkdir(parents=True, exist_ok=True)
    (exercise_root / "source.prompt.md").write_text(
        source_file.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    requested_candidates, active_profile_name, active_profile = resolve_requested_candidates(
        file_config.optimize,
        profile_name=profile_name,
        candidate_specs=candidate_specs,
    )
    synthesized_items, prompt_candidates = synthesize_optimization_items(
        source_pairs,
        requested_candidates=requested_candidates,
        active_profile=active_profile,
        run_config=run_config,
        optimize=file_config.optimize,
    )
    (exercise_root / "candidates.json").write_text(
        json.dumps(
            {
                "profile": active_profile_name,
                "requested_candidates": [
                    {
                        "model": candidate.model,
                        "effort": candidate.effort,
                        "duration_name": candidate.duration_name,
                        "origin": candidate.origin,
                        "profile_source": candidate.profile_source,
                    }
                    for candidate in requested_candidates
                ],
                "prompt_candidates": [
                    {
                        "prompt_index": pair.index,
                        "prompt_title": pair.title,
                        "candidates": [
                            {
                                "variant_name": candidate.variant_name,
                                "variant_title": candidate.variant_title,
                                "model": candidate.model,
                                "effort": candidate.effort,
                                "duration_name": candidate.duration_name,
                                "origin": candidate.origin,
                                "profile_source": candidate.profile_source,
                            }
                            for candidate in prompt_candidates.get(pair.index, [])
                        ],
                    }
                    for pair in source_pairs
                    if pair.validation_prompt.strip()
                ],
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    if baseline_run_dir is None:
        baseline_run_dir = exercise_root / "baseline-run"
        baseline_result = run_pipeline(
            pairs=source_pairs,
            run_dir=baseline_run_dir,
            config=run_config,
            claude_client=claude_client,
            source_file=source_file,
            source_project_dir=source_project_dir,
        )
        if baseline_result.halted_early:
            raise OptimizationError(
                f"baseline run halted early: {baseline_result.halt_reason or 'unknown halt'}"
            )
        baseline_manifest = _validate_baseline_run_dir(
            baseline_run_dir,
            source_file=source_file,
            run_config=run_config,
            expected_prompt_count=len(source_pairs),
        )
        reused_baseline = False
    else:
        baseline_run_dir = baseline_run_dir.resolve()
        baseline_manifest = _validate_baseline_run_dir(
            baseline_run_dir,
            source_file=source_file,
            run_config=run_config,
            expected_prompt_count=len(source_pairs),
        )
        reused_baseline = True
    _copy_baseline_reference(
        exercise_root,
        baseline_run_dir=baseline_run_dir,
        manifest=baseline_manifest,
        reused=reused_baseline,
    )

    baseline_metrics_by_prompt = _metrics_by_prompt_index(baseline_run_dir)

    optimization_prompt_file = exercise_root / "optimization.prompt.md"
    optimization_prompt_file.write_text(
        serialize_items_to_md(synthesized_items),
        encoding="utf-8",
    )

    optimization_run_dir = exercise_root / "optimization-run"
    optimization_result = run_pipeline(
        pairs=synthesized_items,
        run_dir=optimization_run_dir,
        config=run_config,
        claude_client=claude_client,
        source_file=optimization_prompt_file,
        source_project_dir=source_project_dir,
    )
    if optimization_result.halted_early:
        raise OptimizationError(
            f"optimization run halted early: {optimization_result.halt_reason or 'unknown halt'}"
        )

    fork_items = {
        item.index: item
        for item in synthesized_items
        if isinstance(item, ForkPoint)
    }
    fork_results = {result.fork_index: result for result in optimization_result.fork_results}
    decisions: list[PromptOptimizationDecision] = []
    for pair in source_pairs:
        if not pair.validation_prompt.strip():
            continue
        fork_result = fork_results.get(pair.index)
        if fork_result is None:
            raise OptimizationError(f"optimization run produced no fork result for prompt {pair.index}.")
        selected_payload = _selected_variant_result(fork_result)
        selected_variant = str(selected_payload["variant_name"])
        candidate = next(
            (
                candidate
                for candidate in prompt_candidates[pair.index]
                if candidate.variant_name == selected_variant
            ),
            None,
        )
        if candidate is None:
            raise OptimizationError(
                f"selected variant '{selected_variant}' is unknown for prompt {pair.index}."
            )
        fork = fork_items[pair.index]
        scorecard_path = _selection_dir(optimization_run_dir, fork) / "selector" / "candidate-scorecard.json"
        decisions.append(
            PromptOptimizationDecision(
                prompt_index=pair.index,
                prompt_title=pair.title,
                selected_variant=selected_variant,
                selected_model=candidate.model,
                selected_effort=candidate.effort,
                selector_rationale=fork_result.selector_rationale,
                scorecard_path=scorecard_path,
                metrics=dict(selected_payload["metrics"]),
            )
        )

    decision_by_index = {decision.prompt_index: decision for decision in decisions}
    optimized_pairs = [_optimized_pair(pair, decision_by_index.get(pair.index)) for pair in source_pairs]
    optimized_prompt_file = exercise_root / "optimized.prompt.md"
    optimized_prompt_file.write_text(
        _serialize_pairs_to_md(optimized_pairs),
        encoding="utf-8",
    )

    report_path = exercise_root / "report.md"
    _write_report(
        report_path,
        source_pairs=source_pairs,
        baseline_metrics_by_prompt=baseline_metrics_by_prompt,
        optimization_metrics_by_prompt=_metrics_by_prompt_index(optimization_run_dir),
        decisions=decisions,
    )

    return OptimizeResult(
        exercise_root=exercise_root,
        baseline_run_dir=baseline_run_dir,
        optimization_run_dir=optimization_run_dir,
        optimization_prompt_file=optimization_prompt_file,
        optimized_prompt_file=optimized_prompt_file,
        report_path=report_path,
        decisions=decisions,
    )
