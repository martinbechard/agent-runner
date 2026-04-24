"""Config-file support for prompt-runner."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:  # pragma: no cover - exercised on Python 3.11+ in normal runtime
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


_CONFIG_NAMES: tuple[str, ...] = ("prompt-runner.toml", ".prompt-runner.toml")


@dataclass(frozen=True)
class RunDefaults:
    backend: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class OptimizeDuration:
    effort: str
    rank: int = 0
    experimental: bool = False


@dataclass(frozen=True)
class OptimizeModel:
    model: str
    allowed_durations: tuple[str, ...]
    recommended_durations: tuple[str, ...]


@dataclass(frozen=True)
class OptimizeProfileEntry:
    model: str
    durations: tuple[str, ...] = ()


@dataclass(frozen=True)
class OptimizeProfile:
    entries: tuple[OptimizeProfileEntry, ...]
    include_baseline_effective: bool | None = None


@dataclass(frozen=True)
class OptimizeDefaults:
    backend: str = "codex"
    default_profile: str = "balanced"
    include_baseline_effective: bool = True
    durations: dict[str, OptimizeDuration] = field(default_factory=dict)
    duration_aliases: dict[str, str] = field(default_factory=dict)
    models: dict[str, OptimizeModel] = field(default_factory=dict)
    profiles: dict[str, OptimizeProfile] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptRunnerConfig:
    path: Path | None
    run: RunDefaults
    optimize: OptimizeDefaults


def default_optimize_defaults() -> OptimizeDefaults:
    return OptimizeDefaults(
        backend="codex",
        default_profile="balanced",
        include_baseline_effective=True,
        durations={
            "low": OptimizeDuration(effort="low", rank=10),
            "medium": OptimizeDuration(effort="medium", rank=20),
            "high": OptimizeDuration(effort="high", rank=30),
            "xhigh": OptimizeDuration(effort="xhigh", rank=40, experimental=True),
        },
        duration_aliases={"max": "xhigh"},
        models={
            "gpt_5_4_mini": OptimizeModel(
                model="gpt-5.4-mini",
                allowed_durations=("low", "medium", "high", "xhigh"),
                recommended_durations=("low", "medium"),
            ),
            "gpt_5_3_codex": OptimizeModel(
                model="gpt-5.3-codex",
                allowed_durations=("low", "medium", "high", "xhigh"),
                recommended_durations=("medium", "high"),
            ),
            "gpt_5_4": OptimizeModel(
                model="gpt-5.4",
                allowed_durations=("low", "medium", "high", "xhigh"),
                recommended_durations=("medium", "high"),
            ),
            "gpt_5_5": OptimizeModel(
                model="gpt-5.5",
                allowed_durations=("low", "medium", "high", "xhigh"),
                recommended_durations=("medium", "high"),
            ),
        },
        profiles={
            "quick": OptimizeProfile(
                entries=(
                    OptimizeProfileEntry("gpt_5_4_mini", ("low", "medium")),
                    OptimizeProfileEntry("gpt_5_3_codex", ("medium",)),
                ),
            ),
            "balanced": OptimizeProfile(
                entries=(
                    OptimizeProfileEntry("gpt_5_4_mini", ("low", "medium")),
                    OptimizeProfileEntry("gpt_5_3_codex", ("medium",)),
                    OptimizeProfileEntry("gpt_5_4", ("medium",)),
                    OptimizeProfileEntry("gpt_5_5", ("medium",)),
                ),
            ),
            "deep": OptimizeProfile(
                entries=(
                    OptimizeProfileEntry("gpt_5_4_mini", ("low", "medium")),
                    OptimizeProfileEntry("gpt_5_3_codex", ("medium", "high")),
                    OptimizeProfileEntry("gpt_5_4", ("medium", "high")),
                    OptimizeProfileEntry("gpt_5_5", ("medium", "high")),
                ),
            ),
        },
    )


def _error(config_path: Path, message: str) -> ValueError:
    return ValueError(f"Invalid prompt-runner config at {config_path}: {message}")


def _normalize_duration_name(value: str) -> str:
    return value.strip().lower()


def _normalize_duration_ref(value: str, aliases: dict[str, str]) -> str:
    normalized = _normalize_duration_name(value)
    return aliases.get(normalized, normalized)


def _parse_run_defaults(config_path: Path, data: dict) -> RunDefaults:
    run_table = data.get("run", {})
    if not isinstance(run_table, dict):
        raise _error(config_path, "[run] must be a table.")

    backend = run_table.get("backend")
    model = run_table.get("model")
    if backend is not None and not isinstance(backend, str):
        raise _error(config_path, "run.backend must be a string.")
    if model is not None and not isinstance(model, str):
        raise _error(config_path, "run.model must be a string.")
    return RunDefaults(backend=backend, model=model)


def _parse_duration_table(
    config_path: Path,
    durations_table: dict[str, object],
    defaults: dict[str, OptimizeDuration],
) -> dict[str, OptimizeDuration]:
    merged = dict(defaults)
    for name, raw in durations_table.items():
        if not isinstance(raw, dict):
            raise _error(
                config_path,
                f"optimize.durations.{name} must be a table.",
            )
        normalized_name = _normalize_duration_name(name)
        existing = merged.get(normalized_name)
        effort = raw.get("effort", existing.effort if existing is not None else None)
        rank = raw.get("rank", existing.rank if existing is not None else 0)
        experimental = raw.get(
            "experimental",
            existing.experimental if existing is not None else False,
        )
        if not isinstance(effort, str):
            raise _error(
                config_path,
                f"optimize.durations.{name}.effort must be a string.",
            )
        if not isinstance(rank, int):
            raise _error(
                config_path,
                f"optimize.durations.{name}.rank must be an integer.",
            )
        if not isinstance(experimental, bool):
            raise _error(
                config_path,
                f"optimize.durations.{name}.experimental must be a boolean.",
            )
        merged[normalized_name] = OptimizeDuration(
            effort=effort,
            rank=rank,
            experimental=experimental,
        )
    return merged


def _parse_duration_aliases(
    config_path: Path,
    aliases_table: dict[str, object],
    defaults: dict[str, str],
) -> dict[str, str]:
    merged = dict(defaults)
    for alias, raw_target in aliases_table.items():
        if not isinstance(raw_target, str):
            raise _error(
                config_path,
                f"optimize.duration_aliases.{alias} must be a string.",
            )
        merged[_normalize_duration_name(alias)] = _normalize_duration_name(raw_target)
    return merged


def _parse_duration_list(
    config_path: Path,
    field_name: str,
    values: object,
    aliases: dict[str, str],
) -> tuple[str, ...]:
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise _error(config_path, f"{field_name} must be an array of strings.")
    return tuple(_normalize_duration_ref(item, aliases) for item in values)


def _parse_models_table(
    config_path: Path,
    models_table: dict[str, object],
    defaults: dict[str, OptimizeModel],
    aliases: dict[str, str],
) -> dict[str, OptimizeModel]:
    merged = dict(defaults)
    for name, raw in models_table.items():
        if not isinstance(raw, dict):
            raise _error(config_path, f"optimize.models.{name} must be a table.")
        existing = merged.get(name)
        model = raw.get("model", existing.model if existing is not None else None)
        if not isinstance(model, str):
            raise _error(config_path, f"optimize.models.{name}.model must be a string.")
        allowed_raw = raw.get(
            "allowed_durations",
            list(existing.allowed_durations) if existing is not None else None,
        )
        allowed = _parse_duration_list(
            config_path,
            f"optimize.models.{name}.allowed_durations",
            allowed_raw,
            aliases,
        )
        recommended_raw = raw.get(
            "recommended_durations",
            list(existing.recommended_durations)
            if existing is not None
            else list(allowed),
        )
        recommended = _parse_duration_list(
            config_path,
            f"optimize.models.{name}.recommended_durations",
            recommended_raw,
            aliases,
        )
        merged[name] = OptimizeModel(
            model=model,
            allowed_durations=allowed,
            recommended_durations=recommended,
        )
    return merged


def _parse_profile_entries(
    config_path: Path,
    profile_name: str,
    entries_raw: object,
    aliases: dict[str, str],
) -> tuple[OptimizeProfileEntry, ...]:
    if not isinstance(entries_raw, list):
        raise _error(
            config_path,
            f"optimize.profiles.{profile_name}.entries must be an array.",
        )
    entries: list[OptimizeProfileEntry] = []
    for index, raw in enumerate(entries_raw, start=1):
        if not isinstance(raw, dict):
            raise _error(
                config_path,
                f"optimize.profiles.{profile_name}.entries[{index}] must be a table.",
            )
        model = raw.get("model")
        if not isinstance(model, str):
            raise _error(
                config_path,
                f"optimize.profiles.{profile_name}.entries[{index}].model must be a string.",
            )
        durations_raw = raw.get("durations", [])
        durations = _parse_duration_list(
            config_path,
            f"optimize.profiles.{profile_name}.entries[{index}].durations",
            durations_raw,
            aliases,
        )
        entries.append(OptimizeProfileEntry(model=model, durations=durations))
    return tuple(entries)


def _parse_profiles_table(
    config_path: Path,
    profiles_table: dict[str, object],
    defaults: dict[str, OptimizeProfile],
    aliases: dict[str, str],
) -> dict[str, OptimizeProfile]:
    merged = dict(defaults)
    for name, raw in profiles_table.items():
        if not isinstance(raw, dict):
            raise _error(config_path, f"optimize.profiles.{name} must be a table.")
        existing = merged.get(name)
        if "entries" in raw:
            entries = _parse_profile_entries(
                config_path,
                name,
                raw["entries"],
                aliases,
            )
        elif existing is not None:
            entries = existing.entries
        else:
            raise _error(
                config_path,
                f"optimize.profiles.{name}.entries must be provided.",
            )
        include_baseline_effective = raw.get(
            "include_baseline_effective",
            existing.include_baseline_effective if existing is not None else None,
        )
        if include_baseline_effective is not None and not isinstance(
            include_baseline_effective,
            bool,
        ):
            raise _error(
                config_path,
                f"optimize.profiles.{name}.include_baseline_effective must be a boolean.",
            )
        merged[name] = OptimizeProfile(
            entries=entries,
            include_baseline_effective=include_baseline_effective,
        )
    return merged


def _validate_optimize_defaults(
    config_path: Path,
    optimize: OptimizeDefaults,
) -> OptimizeDefaults:
    for alias, target in optimize.duration_aliases.items():
        if target not in optimize.durations:
            raise _error(
                config_path,
                f"optimize.duration_aliases.{alias} points to unknown duration '{target}'.",
            )
    for name, model in optimize.models.items():
        if not model.allowed_durations:
            raise _error(
                config_path,
                f"optimize.models.{name}.allowed_durations must not be empty.",
            )
        if not model.recommended_durations:
            raise _error(
                config_path,
                f"optimize.models.{name}.recommended_durations must not be empty.",
            )
        for duration in (*model.allowed_durations, *model.recommended_durations):
            if duration not in optimize.durations:
                raise _error(
                    config_path,
                    f"optimize.models.{name} references unknown duration '{duration}'.",
                )
        if not set(model.recommended_durations).issubset(set(model.allowed_durations)):
            raise _error(
                config_path,
                f"optimize.models.{name}.recommended_durations must be a subset of allowed_durations.",
            )
    if optimize.default_profile not in optimize.profiles:
        raise _error(
            config_path,
            f"optimize.default_profile references unknown profile '{optimize.default_profile}'.",
        )
    for profile_name, profile in optimize.profiles.items():
        if not profile.entries:
            raise _error(
                config_path,
                f"optimize.profiles.{profile_name}.entries must not be empty.",
            )
        for entry in profile.entries:
            if entry.model not in optimize.models:
                raise _error(
                    config_path,
                    f"optimize.profiles.{profile_name} references unknown model '{entry.model}'.",
                )
            model = optimize.models[entry.model]
            for duration in entry.durations:
                if duration not in model.allowed_durations:
                    raise _error(
                        config_path,
                        f"optimize.profiles.{profile_name} uses unsupported duration "
                        f"'{duration}' for model '{entry.model}'.",
                    )
    return optimize


def _parse_optimize_defaults(config_path: Path, data: dict) -> OptimizeDefaults:
    base = default_optimize_defaults()
    optimize_table = data.get("optimize", {})
    if not isinstance(optimize_table, dict):
        raise _error(config_path, "[optimize] must be a table.")

    backend = optimize_table.get("backend", base.backend)
    default_profile = optimize_table.get("default_profile", base.default_profile)
    include_baseline_effective = optimize_table.get(
        "include_baseline_effective",
        base.include_baseline_effective,
    )
    if not isinstance(backend, str):
        raise _error(config_path, "optimize.backend must be a string.")
    if not isinstance(default_profile, str):
        raise _error(config_path, "optimize.default_profile must be a string.")
    if not isinstance(include_baseline_effective, bool):
        raise _error(config_path, "optimize.include_baseline_effective must be a boolean.")

    raw_durations = optimize_table.get("durations", {})
    if not isinstance(raw_durations, dict):
        raise _error(config_path, "optimize.durations must be a table.")
    durations = _parse_duration_table(config_path, raw_durations, base.durations)

    raw_aliases = optimize_table.get("duration_aliases", {})
    if not isinstance(raw_aliases, dict):
        raise _error(config_path, "optimize.duration_aliases must be a table.")
    duration_aliases = _parse_duration_aliases(
        config_path,
        raw_aliases,
        base.duration_aliases,
    )

    raw_models = optimize_table.get("models", {})
    if not isinstance(raw_models, dict):
        raise _error(config_path, "optimize.models must be a table.")
    models = _parse_models_table(
        config_path,
        raw_models,
        base.models,
        duration_aliases,
    )

    raw_profiles = optimize_table.get("profiles", {})
    if not isinstance(raw_profiles, dict):
        raise _error(config_path, "optimize.profiles must be a table.")
    profiles = _parse_profiles_table(
        config_path,
        raw_profiles,
        base.profiles,
        duration_aliases,
    )

    return _validate_optimize_defaults(
        config_path,
        OptimizeDefaults(
            backend=backend,
            default_profile=default_profile,
            include_baseline_effective=include_baseline_effective,
            durations=durations,
            duration_aliases=duration_aliases,
            models=models,
            profiles=profiles,
        ),
    )


def find_config(start_dir: Path) -> Path | None:
    """Return the nearest prompt-runner config file from start_dir upward."""
    for base in (start_dir, *start_dir.parents):
        for name in _CONFIG_NAMES:
            candidate = base / name
            if candidate.is_file():
                return candidate
    return None


def load_config(source_file: Path) -> PromptRunnerConfig:
    """Load prompt-runner defaults relative to the source file location."""
    config_path = find_config(source_file.resolve().parent)
    if config_path is None:
        return PromptRunnerConfig(
            path=None,
            run=RunDefaults(),
            optimize=default_optimize_defaults(),
        )

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return PromptRunnerConfig(
        path=config_path,
        run=_parse_run_defaults(config_path, data),
        optimize=_parse_optimize_defaults(config_path, data),
    )


def resolve_default_backend(source_file: Path, explicit: str | None) -> str:
    """Resolve backend from CLI override, config file, then hard default."""
    if explicit is not None:
        return explicit
    return load_config(source_file).run.backend or "claude"
