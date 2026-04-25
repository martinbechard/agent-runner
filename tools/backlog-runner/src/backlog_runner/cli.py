"""Command-line interface for backlog-runner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backlog_runner.status import render_status
from backlog_runner.supervisor import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    SupervisorConfig,
    SupervisorLockError,
    request_stop,
    run_loop,
    run_once,
)


EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_USAGE_ERROR = 2
DEFAULT_TARGET_BRANCH = "main"


def cmd_once(args: argparse.Namespace) -> int:
    """Run one bounded backlog-runner cycle."""
    try:
        result = run_once(_config_from_args(args))
    except SupervisorLockError as exc:
        _print_error(str(exc))
        return EXIT_FAILURE
    _print_run_result(result)
    return EXIT_FAILURE if result.failed else EXIT_SUCCESS


def cmd_run(args: argparse.Namespace) -> int:
    """Run the continuous supervisor loop."""
    config = _config_from_args(args)
    if args.once:
        return cmd_once(args)
    try:
        run_loop(config)
    except SupervisorLockError as exc:
        _print_error(str(exc))
        return EXIT_FAILURE
    return EXIT_SUCCESS


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume by running one reconciliation cycle."""
    return cmd_once(args)


def cmd_status(args: argparse.Namespace) -> int:
    """Print backlog-runner status."""
    sys.stdout.write(render_status(Path(args.backlog_root)))
    return EXIT_SUCCESS


def cmd_stop(args: argparse.Namespace) -> int:
    """Request graceful supervisor stop."""
    stop_file = request_stop(Path(args.backlog_root))
    sys.stdout.write(f"Stop requested: {stop_file}\n")
    return EXIT_SUCCESS


def _config_from_args(args: argparse.Namespace) -> SupervisorConfig:
    application_repo = Path(args.application_repo).resolve()
    return SupervisorConfig(
        backlog_root=Path(args.backlog_root).resolve(),
        application_repo=application_repo,
        target_branch=args.target_branch,
        base_branch=args.base_branch,
        backend=args.backend,
        model=args.model,
        max_workers=args.max_workers,
        poll_interval_seconds=args.poll_interval,
        methodology_runner_command=args.methodology_runner_command,
        max_iterations=args.max_iterations,
        dry_run=args.dry_run,
    )


def _print_run_result(result) -> None:
    sys.stdout.write(
        "backlog-runner: "
        f"dispatched={result.dispatched} "
        f"merged={result.merged} "
        f"failed={result.failed} "
        f"invalid={len(result.invalid_files)}\n"
    )


def _print_error(message: str) -> None:
    sys.stderr.write(f"Error: {message}\n")


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--backlog-root",
        default=".",
        help="Directory containing backlog folders and .backlog-runner state.",
    )
    parser.add_argument(
        "--application-repo",
        required=True,
        help="Application repository target worktree.",
    )
    parser.add_argument(
        "--target-branch",
        default=DEFAULT_TARGET_BRANCH,
        help="Target branch that receives completed feature branches.",
    )
    parser.add_argument(
        "--base-branch",
        default=None,
        help="Base branch passed to methodology-runner for new feature branches.",
    )
    parser.add_argument(
        "--backend",
        choices=["claude", "codex"],
        default=None,
        help="Agent backend passed to methodology-runner.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model passed to methodology-runner.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="Maximum methodology-runner workers to run at once.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Seconds between continuous supervisor cycles.",
    )
    parser.add_argument(
        "--methodology-runner-command",
        default="methodology-runner",
        help="Command used to invoke methodology-runner.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum prompt-runner iterations passed to methodology-runner.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Claim and plan work without launching workers or merging.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backlog-runner",
        description="Run backlog items through methodology-runner.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run the continuous supervisor loop.")
    _add_run_options(run_cmd)
    run_cmd.add_argument(
        "--once",
        action="store_true",
        help="Run one bounded cycle instead of the continuous loop.",
    )
    run_cmd.set_defaults(func=cmd_run)

    once_cmd = sub.add_parser("once", help="Run one bounded supervisor cycle.")
    _add_run_options(once_cmd)
    once_cmd.set_defaults(func=cmd_once)

    resume_cmd = sub.add_parser("resume", help="Reconcile and resume work.")
    _add_run_options(resume_cmd)
    resume_cmd.set_defaults(func=cmd_resume)

    status_cmd = sub.add_parser("status", help="Show backlog-runner status.")
    status_cmd.add_argument("--backlog-root", default=".")
    status_cmd.set_defaults(func=cmd_status)

    stop_cmd = sub.add_parser("stop", help="Request graceful stop.")
    stop_cmd.add_argument("--backlog-root", default=".")
    stop_cmd.set_defaults(func=cmd_stop)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
