"""Config-file support for prompt-runner."""
from __future__ import annotations

from dataclasses import dataclass
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
class PromptRunnerConfig:
    path: Path | None
    run: RunDefaults


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
        return PromptRunnerConfig(path=None, run=RunDefaults())

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    run_table = data.get("run", {})
    if not isinstance(run_table, dict):
        raise ValueError(
            f"Invalid prompt-runner config at {config_path}: [run] must be a table."
        )

    backend = run_table.get("backend")
    model = run_table.get("model")
    if backend is not None and not isinstance(backend, str):
        raise ValueError(
            f"Invalid prompt-runner config at {config_path}: run.backend must be a string."
        )
    if model is not None and not isinstance(model, str):
        raise ValueError(
            f"Invalid prompt-runner config at {config_path}: run.model must be a string."
        )

    return PromptRunnerConfig(
        path=config_path,
        run=RunDefaults(backend=backend, model=model),
    )


def resolve_default_backend(source_file: Path, explicit: str | None) -> str:
    """Resolve backend from CLI override, config file, then hard default."""
    if explicit is not None:
        return explicit
    return load_config(source_file).run.backend or "claude"
