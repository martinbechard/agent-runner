"""Tests for methodology_runner.cli.

Covers argument parsing, all four subcommands (run, status, resume, reset),
exit code mapping, error handling for missing files/workspaces, pre-flight
dependency checks, the reset downstream-cascade logic, and helper functions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from methodology_runner.cli import (
    EXIT_ESCALATION,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
    _any_escalated,
    _auto_workspace,
    _build_parser,
    _downstream_phase_ids,
    _format_duration,
    _load_state,
    _print_phase_table,
    _print_pipeline_result,
    _reset_phase_selection,
    _slugify,
    cmd_reset,
    cmd_resume,
    cmd_run,
    cmd_status,
    main,
)
from methodology_runner.models import (
    CrossRefResult,
    METHODOLOGY_LIFECYCLE_PHASE_ID,
    PhaseResult,
    PhaseState,
    PhaseStatus,
    ProjectState,
)
from prompt_runner.client_factory import check_backend_cli


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_project_state(
    workspace: Path,
    *,
    phase_statuses: dict[str, PhaseStatus] | None = None,
    model: str | None = None,
) -> ProjectState:
    """Build a minimal ProjectState and save it to the workspace."""
    from methodology_runner.phases import PHASES

    statuses = phase_statuses or {}

    phase_states = [
        PhaseState(
            phase_id=p.phase_id,
            status=statuses.get(p.phase_id, PhaseStatus.PENDING),
            started_at=None,
            completed_at=None,
            prompt_file=None,
            cross_ref_result_path=None,
            cross_ref_retries=0,
            git_commit=None,
        )
        for p in PHASES
    ]

    state = ProjectState(
        workspace_dir=workspace,
        requirements_path=workspace / "docs" / "requirements" / "raw-requirements.md",
        phase_results={},
        started_at="2026-04-08T12:00:00Z",
        git_initialized=True,
        model=model,
        phases=phase_states,
    )

    state_dir = workspace / ".methodology-runner"
    state_dir.mkdir(parents=True, exist_ok=True)
    state.save(state_dir / "state.json")
    return state


def _make_phase_result(
    phase_id: str,
    status: PhaseStatus = PhaseStatus.COMPLETED,
    wall_time: float = 10.0,
) -> PhaseResult:
    """Build a minimal PhaseResult for testing."""
    return PhaseResult(
        phase_id=phase_id,
        status=status,
        prompt_runner_file="prompt-file.md",
        iteration_count=1,
        wall_time_seconds=wall_time,
        prompt_runner_exit_code=0,
        prompt_runner_success=True,
    )


# ---------------------------------------------------------------------------
# Tests: _slugify
# ---------------------------------------------------------------------------

class TestSlugify:

    def test_simple_name(self) -> None:
        assert _slugify("simple") == "simple"

    def test_spaces_replaced(self) -> None:
        assert _slugify("My Requirements Doc") == "my-requirements-doc"

    def test_special_chars_stripped(self) -> None:
        assert _slugify("project_v2.0_FINAL") == "project-v2-0-final"

    def test_leading_trailing_stripped(self) -> None:
        assert _slugify("---hello---") == "hello"

    def test_empty_string(self) -> None:
        assert _slugify("") == ""

    def test_mixed_case(self) -> None:
        assert _slugify("CamelCaseProject") == "camelcaseproject"


# ---------------------------------------------------------------------------
# Tests: _auto_workspace
# ---------------------------------------------------------------------------

class TestAutoWorkspace:

    def test_generates_runs_prefix(self) -> None:
        ws = _auto_workspace(Path("requirements.md"))
        assert str(ws).startswith("runs/")

    def test_contains_slugified_stem(self) -> None:
        ws = _auto_workspace(Path("My Cool Project.md"))
        assert ws.name.endswith("-my-cool-project")

    def test_contains_timestamp(self) -> None:
        ws = _auto_workspace(Path("test.md"))
        # Name format: YYYY-MM-DDTHH-MM-SS-slug
        name = ws.name
        # Should start with a date-like pattern
        assert len(name) > 19  # timestamp alone is 19 chars


# ---------------------------------------------------------------------------
# Tests: _format_duration
# ---------------------------------------------------------------------------

class TestFormatDuration:

    def test_seconds_only(self) -> None:
        assert _format_duration(5.3) == "5.3s"

    def test_minutes_and_seconds(self) -> None:
        assert _format_duration(65.5) == "1m 5.5s"

    def test_multiple_minutes(self) -> None:
        assert _format_duration(125.0) == "2m 5.0s"

    def test_zero(self) -> None:
        assert _format_duration(0.0) == "0.0s"

    def test_exactly_sixty(self) -> None:
        assert _format_duration(60.0) == "1m 0.0s"


# ---------------------------------------------------------------------------
# Tests: _any_escalated
# ---------------------------------------------------------------------------

class TestAnyEscalated:

    def test_empty_list(self) -> None:
        assert _any_escalated([]) is False

    def test_empty_dict(self) -> None:
        assert _any_escalated({}) is False

    def test_list_with_escalated(self) -> None:
        results = [
            _make_phase_result("PH-000", PhaseStatus.COMPLETED),
            _make_phase_result("PH-001", PhaseStatus.ESCALATED),
        ]
        assert _any_escalated(results) is True

    def test_list_without_escalated(self) -> None:
        results = [
            _make_phase_result("PH-000", PhaseStatus.COMPLETED),
            _make_phase_result("PH-001", PhaseStatus.FAILED),
        ]
        assert _any_escalated(results) is False

    def test_dict_with_escalated(self) -> None:
        results = {
            "PH-000": _make_phase_result("PH-000", PhaseStatus.COMPLETED),
            "PH-001": _make_phase_result("PH-001", PhaseStatus.ESCALATED),
        }
        assert _any_escalated(results) is True

    def test_dict_without_escalated(self) -> None:
        results = {
            "PH-000": _make_phase_result("PH-000", PhaseStatus.COMPLETED),
        }
        assert _any_escalated(results) is False


# ---------------------------------------------------------------------------
# Tests: _load_state
# ---------------------------------------------------------------------------

class TestLoadState:

    def test_returns_none_when_no_state(self, tmp_path: Path) -> None:
        assert _load_state(tmp_path) is None

    def test_loads_existing_state(self, tmp_path: Path) -> None:
        saved = _make_project_state(tmp_path)
        loaded = _load_state(tmp_path)
        assert loaded is not None
        assert loaded.workspace_dir == saved.workspace_dir
        assert loaded.started_at == saved.started_at

    def test_backfills_lifecycle_state_for_legacy_state_json(
        self,
        tmp_path: Path,
    ) -> None:
        state_path = tmp_path / ".methodology-runner" / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "workspace_dir": str(tmp_path),
                    "requirements_path": str(
                        tmp_path / "docs" / "requirements" / "raw-requirements.md"
                    ),
                    "phase_results": {},
                    "started_at": "2026-04-08T12:00:00Z",
                    "git_initialized": True,
                    "finished_at": "2026-04-08T13:00:00Z",
                    "current_phase": None,
                    "phases": [
                        {
                            "phase_id": "PH-000-requirements-inventory",
                            "status": "completed",
                            "started_at": "2026-04-08T12:00:00Z",
                            "completed_at": "2026-04-08T12:05:00Z",
                            "prompt_file": None,
                            "cross_ref_result_path": None,
                            "cross_ref_retries": 0,
                            "git_commit": None,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        loaded = _load_state(tmp_path)

        assert loaded is not None
        assert loaded.change_id == tmp_path.name
        assert len(loaded.lifecycle_phases) == 7
        assert loaded.current_lifecycle_phase_id == "LC-002-change-record-preservation"
        methodology = next(
            phase
            for phase in loaded.lifecycle_phases
            if phase.phase_id == METHODOLOGY_LIFECYCLE_PHASE_ID
        )
        assert methodology.status == PhaseStatus.COMPLETED


# ---------------------------------------------------------------------------
# Tests: backend CLI checks
# ---------------------------------------------------------------------------

class TestPreflightChecks:

    def test_claude_cli_found(self) -> None:
        with patch("prompt_runner.client_factory.shutil.which", return_value="/usr/bin/claude"):
            assert check_backend_cli("claude") is None

    def test_claude_cli_missing(self) -> None:
        with patch("prompt_runner.client_factory.shutil.which", return_value=None):
            result = check_backend_cli("claude")
            assert result is not None
            assert "claude" in result.lower()

    def test_codex_cli_found(self) -> None:
        with patch("prompt_runner.client_factory.shutil.which", return_value="/usr/bin/codex"):
            assert check_backend_cli("codex") is None

    def test_codex_cli_missing(self) -> None:
        with patch("prompt_runner.client_factory.shutil.which", return_value=None):
            result = check_backend_cli("codex")
            assert result is not None
            assert "codex" in result.lower()

# ---------------------------------------------------------------------------
# Tests: _downstream_phase_ids
# ---------------------------------------------------------------------------

class TestDownstreamPhaseIds:

    def test_root_phase_cascades_to_all(self) -> None:
        ids = _downstream_phase_ids("PH-000-requirements-inventory")
        assert len(ids) == 8
        assert ids[0] == "PH-000-requirements-inventory"

    def test_terminal_phase_cascades_to_self(self) -> None:
        ids = _downstream_phase_ids("PH-007-verification-sweep")
        assert ids == ["PH-007-verification-sweep"]

    def test_mid_phase_cascades_downstream(self) -> None:
        ids = _downstream_phase_ids("PH-004-interface-contracts")
        assert "PH-004-interface-contracts" in ids
        assert "PH-006-incremental-implementation" in ids
        assert "PH-007-verification-sweep" in ids
        # Phase 0, 1, 2, 3 should NOT be included
        assert "PH-000-requirements-inventory" not in ids
        assert "PH-001-feature-specification" not in ids
        assert "PH-002-architecture" not in ids
        assert "PH-003-solution-design" not in ids

    def test_phase_4_cascades_to_5_and_6(self) -> None:
        ids = _downstream_phase_ids("PH-005-intelligent-simulations")
        assert "PH-005-intelligent-simulations" in ids
        assert "PH-006-incremental-implementation" in ids
        assert "PH-007-verification-sweep" in ids
        assert len(ids) == 3


# ---------------------------------------------------------------------------
# Tests: _build_parser
# ---------------------------------------------------------------------------

class TestBuildParser:

    def test_has_four_subcommands(self) -> None:
        parser = _build_parser()
        # Verify all four commands parse without error
        for cmd_argv in (
            ["run", "req.md"],
            ["status", "/tmp/ws"],
            ["resume", "/tmp/ws"],
            ["reset", "/tmp/ws", "--phase", "PH-000-requirements-inventory"],
        ):
            args = parser.parse_args(cmd_argv)
            assert args.command in ("run", "status", "resume", "reset")

    def test_run_defaults(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["run", "req.md"])
        assert args.requirements_file == "req.md"
        assert args.workspace is None
        assert args.application_repo is None
        assert args.change_id is None
        assert args.branch_name is None
        assert args.backend is None
        assert args.model is None
        assert args.max_iterations is None
        assert args.debug == 0
        assert args.phases is None
        assert args.escalation_policy is None
        assert args.max_cross_ref_retries == 2

    def test_run_all_options(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([
            "run", "req.md",
            "--workspace", "/tmp/ws",
            "--application-repo", "/tmp/app",
            "--change-id", "change-002",
            "--branch-name", "change-002-add-datetime",
            "--model", "opus",
            "--max-iterations", "5",
            "--debug", "4",
            "--phases",
            "PH-000-requirements-inventory,PH-001-feature-specification",
            "--escalation-policy", "flag-and-continue",
            "--max-cross-ref-retries", "3",
        ])
        assert args.workspace == "/tmp/ws"
        assert args.application_repo == "/tmp/app"
        assert args.change_id == "change-002"
        assert args.branch_name == "change-002-add-datetime"
        assert args.model == "opus"
        assert args.max_iterations == 5
        assert args.debug == 4
        assert (
            args.phases
            == "PH-000-requirements-inventory,PH-001-feature-specification"
        )
        assert args.escalation_policy == "flag-and-continue"
        assert args.max_cross_ref_retries == 3

    def test_resume_inherits_run_options(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([
            "resume", "/tmp/ws",
            "--model", "sonnet",
            "--debug",
            "--escalation-policy", "human-review",
        ])
        assert args.workspace_dir == "/tmp/ws"
        assert args.model == "sonnet"
        assert args.debug == 3
        assert args.escalation_policy == "human-review"

    def test_reset_requires_phase(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["reset", "/tmp/ws"])

    def test_reset_with_phase(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([
            "reset", "/tmp/ws", "--phase", "PH-004-interface-contracts",
        ])
        assert args.workspace_dir == "/tmp/ws"
        assert args.phase == "PH-004-interface-contracts"

    def test_run_with_reset_flag(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([
            "run",
            "req.md",
            "--phases",
            "PH-004-interface-contracts",
            "--reset",
        ])
        assert args.reset is True

    def test_resume_with_reset_flag(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([
            "resume",
            "/tmp/ws",
            "--phases",
            "PH-004-interface-contracts",
            "--reset",
        ])
        assert args.reset is True

    def test_escalation_policy_choices(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["run", "req.md", "--escalation-policy", "invalid"])


# ---------------------------------------------------------------------------
# Tests: cmd_run
# ---------------------------------------------------------------------------

class TestCmdRun:

    def test_missing_requirements_file(self, tmp_path: Path) -> None:
        parser = _build_parser()
        args = parser.parse_args(["run", str(tmp_path / "nonexistent.md")])
        rc = cmd_run(args)
        assert rc == EXIT_USAGE_ERROR

    def test_missing_backend_cli(self, tmp_path: Path) -> None:
        req = tmp_path / "req.md"
        req.write_text("# Requirements\n")
        parser = _build_parser()
        args = parser.parse_args(["run", str(req), "--backend", "codex"])
        with patch("prompt_runner.client_factory.shutil.which", return_value=None):
            rc = cmd_run(args)
        assert rc == EXIT_USAGE_ERROR

    def test_run_uses_backend_from_prompt_runner_config(self, tmp_path: Path) -> None:
        req = tmp_path / "req.md"
        req.write_text("# Requirements\n")
        (tmp_path / "prompt-runner.toml").write_text(
            "[run]\nbackend = \"codex\"\n",
            encoding="utf-8",
        )
        parser = _build_parser()
        args = parser.parse_args(["run", str(req), "--workspace", str(tmp_path / "ws")])

        from methodology_runner.orchestrator import PipelineConfig, PipelineResult

        captured_config: list[PipelineConfig] = []
        mock_result = PipelineResult(
            workspace_dir=tmp_path / "ws",
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=1.0,
        )

        def capturing_run(config: PipelineConfig) -> PipelineResult:
            captured_config.append(config)
            return mock_result

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = capturing_run
            try:
                cmd_run(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert captured_config[0].backend == "codex"

    def test_run_prepares_application_worktree_when_repo_requested(self, tmp_path: Path) -> None:
        req = tmp_path / "change-002-add-datetime.md"
        req.write_text("# Requirements\n", encoding="utf-8")
        parser = _build_parser()
        args = parser.parse_args([
            "run",
            str(req),
            "--application-repo",
            str(tmp_path / "app"),
            "--change-id",
            "change-002",
            "--branch-name",
            "change-002-add-datetime",
        ])

        from methodology_runner.orchestrator import PipelineConfig, PipelineResult

        prepared_workspace = tmp_path / "app-worktrees" / "change-002-add-datetime"
        captured_config: list[PipelineConfig] = []
        mock_result = PipelineResult(
            workspace_dir=prepared_workspace,
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=1.0,
        )

        def capturing_run(config: PipelineConfig) -> PipelineResult:
            captured_config.append(config)
            return mock_result

        with (
            patch("methodology_runner.cli.check_backend_cli", return_value=None),
            patch(
                "methodology_runner.cli._prepare_application_worktree",
                return_value=(prepared_workspace, "change-002-add-datetime"),
            ) as mock_prepare,
        ):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = capturing_run
            try:
                rc = cmd_run(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert rc == EXIT_SUCCESS
        mock_prepare.assert_called_once()
        assert captured_config[0].workspace_dir == prepared_workspace

    def test_successful_run(self, tmp_path: Path) -> None:
        req = tmp_path / "req.md"
        req.write_text("# Requirements\n")
        parser = _build_parser()
        args = parser.parse_args([
            "run", str(req), "--workspace", str(tmp_path / "ws"),
        ])

        from methodology_runner.orchestrator import PipelineResult
        mock_result = PipelineResult(
            workspace_dir=tmp_path / "ws",
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=42.0,
        )

        with (
            patch("methodology_runner.cli.check_backend_cli", return_value=None),
            patch("methodology_runner.cli.cmd_run.__module__", "methodology_runner.cli"),
            patch("methodology_runner.orchestrator.run_pipeline", return_value=mock_result),
        ):
            # Patch the late import inside cmd_run
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = lambda config: mock_result
            try:
                rc = cmd_run(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert rc == EXIT_SUCCESS

    def test_halted_run_returns_escalation(self, tmp_path: Path) -> None:
        req = tmp_path / "req.md"
        req.write_text("# Requirements\n")
        parser = _build_parser()
        args = parser.parse_args([
            "run", str(req), "--workspace", str(tmp_path / "ws"),
        ])

        from methodology_runner.orchestrator import PipelineResult
        mock_result = PipelineResult(
            workspace_dir=tmp_path / "ws",
            phase_results=[],
            halted_early=True,
            halt_reason="Phase PH-001 failed",
            end_to_end_result=None,
            wall_time_seconds=5.0,
        )

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = lambda config: mock_result
            try:
                rc = cmd_run(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert rc == EXIT_ESCALATION

    def test_escalated_phase_returns_escalation(self, tmp_path: Path) -> None:
        req = tmp_path / "req.md"
        req.write_text("# Requirements\n")
        parser = _build_parser()
        args = parser.parse_args([
            "run", str(req), "--workspace", str(tmp_path / "ws"),
        ])

        from methodology_runner.orchestrator import PipelineResult
        mock_result = PipelineResult(
            workspace_dir=tmp_path / "ws",
            phase_results=[
                _make_phase_result("PH-000", PhaseStatus.ESCALATED),
            ],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=5.0,
        )

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = lambda config: mock_result
            try:
                rc = cmd_run(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert rc == EXIT_ESCALATION

    def test_escalation_policy_parsed(self, tmp_path: Path) -> None:
        req = tmp_path / "req.md"
        req.write_text("# Requirements\n")
        parser = _build_parser()
        args = parser.parse_args([
            "run", str(req),
            "--workspace", str(tmp_path / "ws"),
            "--escalation-policy", "flag-and-continue",
        ])

        from methodology_runner.models import EscalationPolicy
        from methodology_runner.orchestrator import PipelineConfig, PipelineResult

        captured_config: list[PipelineConfig] = []
        mock_result = PipelineResult(
            workspace_dir=tmp_path / "ws",
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=1.0,
        )

        def capturing_run(config: PipelineConfig) -> PipelineResult:
            captured_config.append(config)
            return mock_result

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = capturing_run
            try:
                cmd_run(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert len(captured_config) == 1
        assert captured_config[0].escalation_policy == EscalationPolicy.FLAG_AND_CONTINUE

    def test_debug_parsed(self, tmp_path: Path) -> None:
        req = tmp_path / "req.md"
        req.write_text("# Requirements\n")
        parser = _build_parser()
        args = parser.parse_args([
            "run", str(req),
            "--workspace", str(tmp_path / "ws"),
            "--debug", "5",
        ])

        from methodology_runner.orchestrator import PipelineConfig, PipelineResult

        captured_config: list[PipelineConfig] = []
        mock_result = PipelineResult(
            workspace_dir=tmp_path / "ws",
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=1.0,
        )

        def capturing_run(config: PipelineConfig) -> PipelineResult:
            captured_config.append(config)
            return mock_result

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = capturing_run
            try:
                cmd_run(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert captured_config[0].debug == 5

    def test_phases_parsed(self, tmp_path: Path) -> None:
        req = tmp_path / "req.md"
        req.write_text("# Requirements\n")
        parser = _build_parser()
        args = parser.parse_args([
            "run", str(req),
            "--workspace", str(tmp_path / "ws"),
            "--phases",
            "PH-001-feature-specification,PH-000-requirements-inventory",
        ])

        from methodology_runner.orchestrator import PipelineConfig, PipelineResult

        captured_config: list[PipelineConfig] = []
        mock_result = PipelineResult(
            workspace_dir=tmp_path / "ws",
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=1.0,
        )

        def capturing_run(config: PipelineConfig) -> PipelineResult:
            captured_config.append(config)
            return mock_result

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = capturing_run
            try:
                cmd_run(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert captured_config[0].phases_to_run == [
            "PH-000-requirements-inventory",
            "PH-001-feature-specification",
        ]

    def test_run_banner_shows_selected_phases(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        req = tmp_path / "req.md"
        req.write_text("# Requirements\n")
        parser = _build_parser()
        args = parser.parse_args([
            "run", str(req),
            "--workspace", str(tmp_path / "ws"),
            "--phases",
            "PH-001-feature-specification,PH-000-requirements-inventory",
        ])

        from methodology_runner.orchestrator import PipelineResult
        mock_result = PipelineResult(
            workspace_dir=tmp_path / "ws",
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=1.0,
        )

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = lambda config: mock_result
            try:
                rc = cmd_run(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert rc == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert (
            "Phases:       PH-000-requirements-inventory, "
            "PH-001-feature-specification"
        ) in captured.out

    def test_reset_requires_exactly_one_phase(self, tmp_path: Path) -> None:
        req = tmp_path / "req.md"
        req.write_text("# Requirements\n")
        parser = _build_parser()
        args = parser.parse_args([
            "run", str(req), "--workspace", str(tmp_path / "ws"), "--reset",
        ])
        rc = cmd_run(args)
        assert rc == EXIT_USAGE_ERROR

    def test_reset_cleans_selected_phase_and_downstream_before_run(
        self, tmp_path: Path,
    ) -> None:
        req = tmp_path / "req.md"
        req.write_text("# Requirements\n")
        workspace = tmp_path / "ws"
        workspace.mkdir()
        state = _make_project_state(
            workspace,
            phase_statuses={
                "PH-000-requirements-inventory": PhaseStatus.COMPLETED,
                "PH-004-interface-contracts": PhaseStatus.COMPLETED,
                "PH-007-verification-sweep": PhaseStatus.COMPLETED,
            },
        )
        state.phase_results["PH-000-requirements-inventory"] = _make_phase_result(
            "PH-000-requirements-inventory"
        )
        state.phase_results["PH-004-interface-contracts"] = _make_phase_result(
            "PH-004-interface-contracts"
        )
        state.phase_results["PH-007-verification-sweep"] = _make_phase_result(
            "PH-007-verification-sweep"
        )
        state.save(workspace / ".methodology-runner" / "state.json")

        artifact_4 = workspace / "docs" / "design" / "interface-contracts.yaml"
        artifact_4.parent.mkdir(parents=True, exist_ok=True)
        artifact_4.write_text("old\n", encoding="utf-8")
        artifact_7 = workspace / "docs" / "verification" / "verification-report.yaml"
        artifact_7.parent.mkdir(parents=True, exist_ok=True)
        artifact_7.write_text("old\n", encoding="utf-8")
        run_dir_4 = workspace / ".methodology-runner" / "runs" / "phase-4"
        run_dir_4.mkdir(parents=True, exist_ok=True)
        (run_dir_4 / "marker.txt").write_text("x\n", encoding="utf-8")

        parser = _build_parser()
        args = parser.parse_args([
            "run",
            str(req),
            "--workspace",
            str(workspace),
            "--phases",
            "PH-004-interface-contracts",
            "--reset",
        ])

        from methodology_runner.orchestrator import PipelineResult
        mock_result = PipelineResult(
            workspace_dir=workspace,
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=1.0,
        )

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = lambda config: mock_result
            try:
                rc = cmd_run(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert rc == EXIT_SUCCESS
        reloaded = ProjectState.load(workspace / ".methodology-runner" / "state.json")
        phase0 = next(ps for ps in reloaded.phases if ps.phase_id == "PH-000-requirements-inventory")
        phase4 = next(ps for ps in reloaded.phases if ps.phase_id == "PH-004-interface-contracts")
        phase7 = next(ps for ps in reloaded.phases if ps.phase_id == "PH-007-verification-sweep")
        assert phase0.status == PhaseStatus.COMPLETED
        assert phase4.status == PhaseStatus.PENDING
        assert phase7.status == PhaseStatus.PENDING
        assert not artifact_4.exists()
        assert not artifact_7.exists()
        assert not run_dir_4.exists()


# ---------------------------------------------------------------------------
# Tests: cmd_status
# ---------------------------------------------------------------------------

class TestCmdStatus:

    def test_missing_workspace(self, tmp_path: Path) -> None:
        parser = _build_parser()
        args = parser.parse_args(["status", str(tmp_path / "nonexistent")])
        rc = cmd_status(args)
        assert rc == EXIT_USAGE_ERROR

    def test_missing_state_file(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        parser = _build_parser()
        args = parser.parse_args(["status", str(workspace)])
        rc = cmd_status(args)
        assert rc == EXIT_USAGE_ERROR

    def test_shows_pending_phases(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        _make_project_state(workspace)
        parser = _build_parser()
        args = parser.parse_args(["status", str(workspace)])
        rc = cmd_status(args)
        assert rc == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "pending" in captured.out
        assert "Project Status" in captured.out

    def test_shows_completed_results(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        state = _make_project_state(
            workspace,
            phase_statuses={"PH-000-requirements-inventory": PhaseStatus.COMPLETED},
        )
        state.phase_results["PH-000-requirements-inventory"] = _make_phase_result(
            "PH-000-requirements-inventory",
            PhaseStatus.COMPLETED,
            wall_time=15.5,
        )
        state_dir = workspace / ".methodology-runner"
        state.save(state_dir / "state.json")

        parser = _build_parser()
        args = parser.parse_args(["status", str(workspace)])
        rc = cmd_status(args)
        assert rc == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "Completed phase results" in captured.out
        assert "PH-000-requirements-inventory" in captured.out

    def test_escalated_returns_escalation_code(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        state = _make_project_state(workspace)
        state.phase_results["PH-000"] = _make_phase_result(
            "PH-000", PhaseStatus.ESCALATED,
        )
        state_dir = workspace / ".methodology-runner"
        state.save(state_dir / "state.json")

        parser = _build_parser()
        args = parser.parse_args(["status", str(workspace)])
        rc = cmd_status(args)
        assert rc == EXIT_ESCALATION

    def test_shows_model(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        _make_project_state(workspace, model="claude-opus-4-6")
        parser = _build_parser()
        args = parser.parse_args(["status", str(workspace)])
        cmd_status(args)
        captured = capsys.readouterr()
        assert "claude-opus-4-6" in captured.out

    def test_shows_lifecycle_boundary_when_methodology_is_complete(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        state = _make_project_state(workspace)
        state.finished_at = "2026-04-08T13:00:00Z"
        state.current_lifecycle_phase_id = "LC-002-change-record-preservation"
        methodology = next(
            phase
            for phase in state.lifecycle_phases
            if phase.phase_id == METHODOLOGY_LIFECYCLE_PHASE_ID
        )
        methodology.status = PhaseStatus.COMPLETED
        methodology.completed_at = "2026-04-08T13:00:00Z"
        state.save(workspace / ".methodology-runner" / "state.json")

        parser = _build_parser()
        args = parser.parse_args(["status", str(workspace)])
        rc = cmd_status(args)

        assert rc == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "Current lifecycle phase: LC-002-change-record-preservation" in captured.out
        assert "Methodology completed at: 2026-04-08T13:00:00Z" in captured.out
        assert "Lifecycle finished at: 2026-04-08T13:00:00Z" in captured.out
        assert "Nested methodology phases are currently inactive" in captured.out


# ---------------------------------------------------------------------------
# Tests: cmd_resume
# ---------------------------------------------------------------------------

class TestCmdResume:

    def test_missing_workspace(self, tmp_path: Path) -> None:
        parser = _build_parser()
        args = parser.parse_args(["resume", str(tmp_path / "nonexistent")])
        rc = cmd_resume(args)
        assert rc == EXIT_USAGE_ERROR

    def test_missing_state_file(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        parser = _build_parser()
        args = parser.parse_args(["resume", str(workspace)])
        rc = cmd_resume(args)
        assert rc == EXIT_USAGE_ERROR

    def test_missing_backend_cli(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        _make_project_state(workspace)
        parser = _build_parser()
        args = parser.parse_args(["resume", str(workspace), "--backend", "codex"])
        with patch("prompt_runner.client_factory.shutil.which", return_value=None):
            rc = cmd_resume(args)
        assert rc == EXIT_USAGE_ERROR

    def test_uses_saved_model(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        _make_project_state(workspace, model="saved-model")
        parser = _build_parser()
        args = parser.parse_args(["resume", str(workspace)])

        from methodology_runner.orchestrator import PipelineConfig, PipelineResult

        captured_config: list[PipelineConfig] = []
        mock_result = PipelineResult(
            workspace_dir=workspace,
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=1.0,
        )

        def capturing_run(config: PipelineConfig) -> PipelineResult:
            captured_config.append(config)
            return mock_result

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = capturing_run
            try:
                cmd_resume(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert captured_config[0].model == "saved-model"

    def test_resume_debug_parsed(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        _make_project_state(workspace, model="saved-model")
        parser = _build_parser()
        args = parser.parse_args([
            "resume", str(workspace),
            "--debug", "4",
        ])

        from methodology_runner.orchestrator import PipelineConfig, PipelineResult

        captured_config: list[PipelineConfig] = []
        mock_result = PipelineResult(
            workspace_dir=workspace,
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=1.0,
        )

        def capturing_run(config: PipelineConfig) -> PipelineResult:
            captured_config.append(config)
            return mock_result

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = capturing_run
            try:
                cmd_resume(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert captured_config[0].debug == 4
        assert captured_config[0].resume is True

    def test_resume_allows_automated_lifecycle_completion_after_methodology_boundary(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        state = _make_project_state(workspace, model="saved-model")
        state.current_lifecycle_phase_id = "LC-002-change-record-preservation"
        methodology = next(
            phase
            for phase in state.lifecycle_phases
            if phase.phase_id == METHODOLOGY_LIFECYCLE_PHASE_ID
        )
        methodology.status = PhaseStatus.COMPLETED
        state.save(workspace / ".methodology-runner" / "state.json")
        parser = _build_parser()
        args = parser.parse_args(["resume", str(workspace)])

        from methodology_runner.orchestrator import PipelineConfig, PipelineResult

        captured_config: list[PipelineConfig] = []
        mock_result = PipelineResult(
            workspace_dir=workspace,
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=1.0,
        )

        def capturing_run(config: PipelineConfig) -> PipelineResult:
            captured_config.append(config)
            return mock_result

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = capturing_run
            try:
                rc = cmd_resume(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert rc == EXIT_SUCCESS
        assert captured_config
        assert captured_config[0].resume is True

    def test_resume_banner_shows_selected_phases(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        _make_project_state(workspace, model="saved-model")
        parser = _build_parser()
        args = parser.parse_args([
            "resume",
            str(workspace),
            "--phases",
            "PH-001-feature-specification,PH-000-requirements-inventory",
        ])

        from methodology_runner.orchestrator import PipelineResult
        mock_result = PipelineResult(
            workspace_dir=workspace,
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=1.0,
        )

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = lambda config: mock_result
            try:
                rc = cmd_resume(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert rc == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert (
            "Phases:       PH-000-requirements-inventory, "
            "PH-001-feature-specification"
        ) in captured.out

    def test_model_override(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        _make_project_state(workspace, model="saved-model")
        parser = _build_parser()
        args = parser.parse_args(["resume", str(workspace), "--model", "override-model"])

        from methodology_runner.orchestrator import PipelineConfig, PipelineResult

        captured_config: list[PipelineConfig] = []
        mock_result = PipelineResult(
            workspace_dir=workspace,
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=1.0,
        )

        def capturing_run(config: PipelineConfig) -> PipelineResult:
            captured_config.append(config)
            return mock_result

        with patch("methodology_runner.cli.check_backend_cli", return_value=None):
            import methodology_runner.orchestrator as orch_mod
            original_run = orch_mod.run_pipeline
            orch_mod.run_pipeline = capturing_run
            try:
                cmd_resume(args)
            finally:
                orch_mod.run_pipeline = original_run

        assert captured_config[0].model == "override-model"

    def test_reset_requires_exactly_one_phase(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        _make_project_state(workspace)
        parser = _build_parser()
        args = parser.parse_args([
            "resume",
            str(workspace),
            "--reset",
            "--phases",
            "PH-000-requirements-inventory,PH-001-feature-specification",
        ])
        rc = cmd_resume(args)
        assert rc == EXIT_USAGE_ERROR


# ---------------------------------------------------------------------------
# Tests: cmd_reset
# ---------------------------------------------------------------------------

class TestCmdReset:

    def test_missing_workspace(self, tmp_path: Path) -> None:
        parser = _build_parser()
        args = parser.parse_args([
            "reset", str(tmp_path / "nonexistent"),
            "--phase", "PH-000-requirements-inventory",
        ])
        rc = cmd_reset(args)
        assert rc == EXIT_USAGE_ERROR

    def test_missing_state_file(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        parser = _build_parser()
        args = parser.parse_args([
            "reset", str(workspace),
            "--phase", "PH-000-requirements-inventory",
        ])
        rc = cmd_reset(args)
        assert rc == EXIT_USAGE_ERROR

    def test_unknown_phase_id(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        _make_project_state(workspace)
        parser = _build_parser()
        args = parser.parse_args([
            "reset", str(workspace), "--phase", "PH-999-bogus",
        ])
        rc = cmd_reset(args)
        assert rc == EXIT_USAGE_ERROR

    def test_resets_single_terminal_phase(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        state = _make_project_state(
            workspace,
            phase_statuses={
                "PH-007-verification-sweep": PhaseStatus.COMPLETED,
            },
        )
        state.phase_results["PH-007-verification-sweep"] = _make_phase_result(
            "PH-007-verification-sweep",
        )
        state_dir = workspace / ".methodology-runner"
        state.save(state_dir / "state.json")

        parser = _build_parser()
        args = parser.parse_args([
            "reset", str(workspace), "--phase", "PH-007-verification-sweep",
        ])
        rc = cmd_reset(args)
        assert rc == EXIT_SUCCESS

        reloaded = ProjectState.load(state_dir / "state.json")
        phase7 = next(ps for ps in reloaded.phases if ps.phase_id == "PH-007-verification-sweep")
        assert phase7.status == PhaseStatus.PENDING
        assert "PH-007-verification-sweep" not in reloaded.phase_results

    def test_cascades_downstream(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        from methodology_runner.phases import PHASES
        all_completed = {p.phase_id: PhaseStatus.COMPLETED for p in PHASES}
        state = _make_project_state(workspace, phase_statuses=all_completed)
        for p in PHASES:
            state.phase_results[p.phase_id] = _make_phase_result(p.phase_id)
        state_dir = workspace / ".methodology-runner"
        state.save(state_dir / "state.json")

        parser = _build_parser()
        args = parser.parse_args([
            "reset", str(workspace),
            "--phase", "PH-004-interface-contracts",
        ])
        rc = cmd_reset(args)
        assert rc == EXIT_SUCCESS

        reloaded = ProjectState.load(state_dir / "state.json")

        # Phases 0, 1, 2, 3 should remain COMPLETED
        for ps in reloaded.phases:
            if ps.phase_id in (
                "PH-000-requirements-inventory",
                "PH-001-feature-specification",
                "PH-002-architecture",
                "PH-003-solution-design",
            ):
                assert ps.status == PhaseStatus.COMPLETED, f"{ps.phase_id} should stay COMPLETED"

        # Phases 4, 5, 6, 7 should be reset to PENDING
        for ps in reloaded.phases:
            if ps.phase_id in (
                "PH-004-interface-contracts",
                "PH-005-intelligent-simulations",
                "PH-006-incremental-implementation",
                "PH-007-verification-sweep",
            ):
                assert ps.status == PhaseStatus.PENDING, f"{ps.phase_id} should be PENDING"
                assert ps.cross_ref_retries == 0

        # Phase results should be removed for reset phases
        assert "PH-004-interface-contracts" not in reloaded.phase_results
        assert "PH-007-verification-sweep" not in reloaded.phase_results
        # Upstream results should remain
        assert "PH-000-requirements-inventory" in reloaded.phase_results

    def test_clears_finished_at(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        state = _make_project_state(workspace)
        state.finished_at = "2026-04-08T13:00:00Z"
        state_dir = workspace / ".methodology-runner"
        state.save(state_dir / "state.json")

        parser = _build_parser()
        args = parser.parse_args([
            "reset", str(workspace),
            "--phase", "PH-000-requirements-inventory",
        ])
        cmd_reset(args)

        reloaded = ProjectState.load(state_dir / "state.json")
        assert reloaded.finished_at is None

    def test_prints_reset_summary(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        _make_project_state(workspace)
        parser = _build_parser()
        args = parser.parse_args([
            "reset", str(workspace),
            "--phase", "PH-004-interface-contracts",
        ])
        cmd_reset(args)
        captured = capsys.readouterr()
        assert "Phase Reset" in captured.out
        assert "PH-004-interface-contracts" in captured.out
        assert "PH-006-incremental-implementation" in captured.out

    def test_reset_cleanup_removes_partial_change_record_root(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        state = _make_project_state(workspace)
        state.change_id = "change-002-add-datetime"
        state_dir = workspace / ".methodology-runner"
        state.save(state_dir / "state.json")

        change_root = workspace / "docs" / "changes" / state.change_id / "execution"
        change_root.mkdir(parents=True, exist_ok=True)
        (change_root / "implementation-workflow.md").write_text("stale\n", encoding="utf-8")

        ids_to_reset = _reset_phase_selection(
            workspace,
            "PH-006-incremental-implementation",
            cleanup_files=True,
        )

        assert ids_to_reset == [
            "PH-006-incremental-implementation",
            "PH-007-verification-sweep",
        ]
        assert not (workspace / "docs" / "changes" / state.change_id).exists()


# ---------------------------------------------------------------------------
# Tests: main entry point
# ---------------------------------------------------------------------------

class TestMain:

    def test_missing_command_raises_system_exit(self) -> None:
        # argparse calls sys.exit(2) when required subcommand is missing.
        # Our main() does not catch SystemExit, so it propagates.
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 2

    def test_keyboard_interrupt(self, tmp_path: Path) -> None:
        def raise_interrupt(_args: object) -> int:
            raise KeyboardInterrupt

        # Patch _build_parser so parse_args returns a namespace with our func
        ns = argparse.Namespace(command="status", func=raise_interrupt)
        with patch("methodology_runner.cli._build_parser") as mock_bp:
            mock_bp.return_value.parse_args.return_value = ns
            rc = main(["status", str(tmp_path)])
        assert rc == EXIT_ESCALATION

    def test_generic_exception(self, tmp_path: Path) -> None:
        def raise_error(_args: object) -> int:
            raise RuntimeError("something broke")

        ns = argparse.Namespace(command="status", func=raise_error)
        with patch("methodology_runner.cli._build_parser") as mock_bp:
            mock_bp.return_value.parse_args.return_value = ns
            rc = main(["status", str(tmp_path)])
        assert rc == EXIT_ESCALATION


# ---------------------------------------------------------------------------
# Tests: _print_pipeline_result / _print_phase_table
# ---------------------------------------------------------------------------

class TestPrintPipelineResult:

    def test_prints_summary(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        from methodology_runner.orchestrator import PipelineResult
        result = PipelineResult(
            workspace_dir=tmp_path,
            phase_results=[
                _make_phase_result("PH-000-req", PhaseStatus.COMPLETED, 12.5),
            ],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=None,
            wall_time_seconds=42.3,
        )
        _print_pipeline_result(result)
        captured = capsys.readouterr()
        assert "Pipeline Summary" in captured.out
        assert "42.3s" in captured.out
        assert "PH-000-req" in captured.out

    def test_prints_halt_reason(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        from methodology_runner.orchestrator import PipelineResult
        result = PipelineResult(
            workspace_dir=tmp_path,
            phase_results=[],
            halted_early=True,
            halt_reason="Phase 1 failed",
            end_to_end_result=None,
            wall_time_seconds=5.0,
        )
        _print_pipeline_result(result)
        captured = capsys.readouterr()
        assert "Phase 1 failed" in captured.out

    def test_prints_end_to_end_result(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        from methodology_runner.orchestrator import PipelineResult
        xref = CrossRefResult(
            passed=False,
            issues=["Missing traceability link"],
            traceability_gaps=["REQ-001"],
            orphaned_elements=[],
            coverage_summary={"traceability": 0.5},
        )
        result = PipelineResult(
            workspace_dir=tmp_path,
            phase_results=[],
            halted_early=False,
            halt_reason=None,
            end_to_end_result=xref,
            wall_time_seconds=1.0,
        )
        _print_pipeline_result(result)
        captured = capsys.readouterr()
        assert "End-to-end verification: FAIL" in captured.out
        assert "Missing traceability link" in captured.out

    def test_ignores_non_pipeline_result(self, capsys: pytest.CaptureFixture[str]) -> None:
        _print_pipeline_result("not a PipelineResult")
        captured = capsys.readouterr()
        assert captured.out == ""


# ---------------------------------------------------------------------------
# Tests: exit code contract (CD-002 Section 10.6)
# ---------------------------------------------------------------------------

class TestExitCodeContract:
    """Verify exit code constants match CD-002 spec:
    0 = success, 1 = escalation/halt, 2 = usage error."""

    def test_success_is_zero(self) -> None:
        assert EXIT_SUCCESS == 0

    def test_escalation_is_one(self) -> None:
        assert EXIT_ESCALATION == 1

    def test_usage_error_is_two(self) -> None:
        assert EXIT_USAGE_ERROR == 2
