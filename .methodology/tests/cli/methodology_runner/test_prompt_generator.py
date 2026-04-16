"""Tests for methodology_runner.prompt_generator.

Covers the meta-prompt template, input context assembly, structural
validation, and the full generate_prompt_file flow using FakeClaudeClient.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from prompt_runner.claude_client import ClaudeResponse, FakeClaudeClient

from methodology_runner.models import (
    CrossRefCheckResult,
    CrossRefIssue,
    CrossReferenceResult,
    InputRole,
    InputSourceTemplate,
    PhaseConfig,
    PhaseState,
    PhaseStatus,
)
from methodology_runner.prompt_generator import (
    CODE_BLOCKS_PER_PROMPT,
    MAX_GENERATION_ATTEMPTS,
    MAX_INPUT_FILE_CHARS,
    META_PROMPT_TEMPLATE,
    PROMPT_RUNNER_FILES_DIR,
    PromptGenerationContext,
    PromptGenerationError,
    _assemble_input_context,
    _format_bullet_list,
    _format_cross_ref_feedback,
    _format_expected_files_block,
    _format_input_artifacts_block,
    _format_prior_phases_block,
    _read_and_truncate,
    _validate_prompt_runner_file,
    assemble_meta_prompt,
    generate_prompt_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _minimal_phase(
    workspace: Path,
    *,
    phase_id: str = "PH-000-test",
    inputs: list[InputSourceTemplate] | None = None,
) -> PhaseConfig:
    """Build a minimal PhaseConfig for testing."""
    if inputs is None:
        inputs = [
            InputSourceTemplate(
                ref_template="{workspace}/docs/requirements/raw-requirements.md",
                role=InputRole.PRIMARY,
                format="markdown",
                description="Raw requirements document",
            ),
        ]
    return PhaseConfig(
        phase_id=phase_id,
        phase_name="Test Phase",
        phase_number=0,
        abbreviation="TP",
        predecessors=[],
        input_source_templates=inputs,
        output_artifact_path="docs/test/output.yaml",
        output_format="yaml",
        expected_output_files=["docs/test/output.yaml"],
        extraction_focus="Test extraction focus",
        generation_instructions="Test generation instructions",
        judge_guidance="Test judge guidance",
        artifact_format="yaml",
        artifact_schema_description="items:\n  - id: T-NNN",
        checklist_examples_good=["Good example one", "Good example two"],
        checklist_examples_bad=["Bad example"],
    )


def _phase_001_phase(workspace: Path) -> PhaseConfig:
    return PhaseConfig(
        phase_id="PH-001-feature-specification",
        phase_name="Feature Specification",
        phase_number=1,
        abbreviation="FS",
        predecessors=["PH-000-requirements-inventory"],
        input_source_templates=[
            InputSourceTemplate(
                ref_template="{workspace}/docs/requirements/requirements-inventory.yaml",
                role=InputRole.PRIMARY,
                format="yaml",
                description="Requirements inventory produced by Phase 0",
            ),
            InputSourceTemplate(
                ref_template="{workspace}/docs/requirements/raw-requirements.md",
                role=InputRole.VALIDATION_REFERENCE,
                format="markdown",
                description="Raw requirements for validating traceability",
            ),
        ],
        output_artifact_path="docs/features/feature-specification.yaml",
        output_format="yaml",
        expected_output_files=["docs/features/feature-specification.yaml"],
        extraction_focus="Keep structural and RI-coverage checks deterministic where possible.",
        generation_instructions="Read the requirements inventory and produce a feature specification YAML file.",
        judge_guidance="Check RI coverage, unsupported scope, and vague acceptance criteria.",
        artifact_format="yaml",
        artifact_schema_description="features:\n  - id: FT-NNN",
        checklist_examples_good=["Every RI item is covered."],
        checklist_examples_bad=["Features cover the requirements."],
    )


def _create_workspace_with_input(tmp_path: Path) -> tuple[Path, PhaseConfig]:
    """Create a workspace with a raw requirements file and return
    (workspace, phase_config)."""
    workspace = tmp_path / "project"
    workspace.mkdir()
    req_dir = workspace / "docs" / "requirements"
    req_dir.mkdir(parents=True)
    (req_dir / "raw-requirements.md").write_text(
        "# Requirements\n\nThe system shall do X.\n",
        encoding="utf-8",
    )
    phase = _minimal_phase(workspace)
    return workspace, phase


def _valid_prompt_runner_content() -> str:
    """Return a minimal valid prompt-runner .md file."""
    return (
        "## Prompt 1: Extract Data\n\n"
        "```\nRead the input and extract.\n```\n\n"
        "```\nVerify extraction.\nVERDICT: pass\n```\n\n"
        "## Prompt 2: Structure Output\n\n"
        "```\nOrganise the extracted data.\n```\n\n"
        "```\nVerify structure.\nVERDICT: pass\n```\n"
    )


# ---------------------------------------------------------------------------
# Tests: _read_and_truncate
# ---------------------------------------------------------------------------

class TestReadAndTruncate:

    def test_reads_small_file(self, tmp_path: Path) -> None:
        f = tmp_path / "small.txt"
        f.write_text("hello world", encoding="utf-8")
        content, truncated = _read_and_truncate(f)
        assert content == "hello world"
        assert truncated is False

    def test_truncates_large_file(self, tmp_path: Path) -> None:
        f = tmp_path / "large.txt"
        text = "x" * (MAX_INPUT_FILE_CHARS + 100)
        f.write_text(text, encoding="utf-8")
        content, truncated = _read_and_truncate(f)
        assert len(content) == MAX_INPUT_FILE_CHARS
        assert truncated is True

    def test_exact_limit_not_truncated(self, tmp_path: Path) -> None:
        f = tmp_path / "exact.txt"
        text = "a" * MAX_INPUT_FILE_CHARS
        f.write_text(text, encoding="utf-8")
        content, truncated = _read_and_truncate(f)
        assert len(content) == MAX_INPUT_FILE_CHARS
        assert truncated is False


# ---------------------------------------------------------------------------
# Tests: _assemble_input_context
# ---------------------------------------------------------------------------

class TestAssembleInputContext:

    def test_assembles_single_input(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        result = _assemble_input_context(phase, workspace)
        assert "# Input:" in result
        assert "role: primary" in result
        assert "The system shall do X." in result

    def test_raises_on_missing_input(self, tmp_path: Path) -> None:
        workspace = tmp_path / "empty"
        workspace.mkdir()
        phase = _minimal_phase(workspace)
        with pytest.raises(PromptGenerationError, match="Input files missing"):
            _assemble_input_context(phase, workspace)

    def test_truncation_note_on_large_input(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        req_dir = workspace / "docs" / "requirements"
        req_dir.mkdir(parents=True)
        (req_dir / "raw-requirements.md").write_text(
            "x" * (MAX_INPUT_FILE_CHARS + 500),
            encoding="utf-8",
        )
        phase = _minimal_phase(workspace)
        result = _assemble_input_context(phase, workspace)
        assert "truncated at" in result
        assert "Generators should Read" in result

    def test_no_inputs_returns_placeholder(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        phase = _minimal_phase(workspace, inputs=[])
        result = _assemble_input_context(phase, workspace)
        assert result == "(no input files)"

    def test_multiple_inputs_separated(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        req_dir = workspace / "docs" / "requirements"
        req_dir.mkdir(parents=True)
        (req_dir / "raw-requirements.md").write_text("req", encoding="utf-8")
        feat_dir = workspace / "docs" / "features"
        feat_dir.mkdir(parents=True)
        (feat_dir / "feature-specification.yaml").write_text(
            "features: []", encoding="utf-8",
        )
        inputs = [
            InputSourceTemplate(
                ref_template="{workspace}/docs/requirements/raw-requirements.md",
                role=InputRole.PRIMARY,
                format="markdown",
                description="Raw requirements",
            ),
            InputSourceTemplate(
                ref_template="{workspace}/docs/features/feature-specification.yaml",
                role=InputRole.VALIDATION_REFERENCE,
                format="yaml",
                description="Feature spec",
            ),
        ]
        phase = _minimal_phase(workspace, inputs=inputs)
        result = _assemble_input_context(phase, workspace)
        assert result.count("# Input:") == 2
        assert "---" in result

    def test_file_reference_mode_lists_paths_without_embedding_content(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        result = _assemble_input_context(phase, workspace, mode="file-reference")
        assert "# Input:" in result
        assert "Read this file directly from the workspace" in result
        assert "The system shall do X." not in result


# ---------------------------------------------------------------------------
# Tests: _validate_prompt_runner_file
# ---------------------------------------------------------------------------

class TestValidatePromptRunnerFile:

    def test_valid_file_returns_empty(self) -> None:
        content = _valid_prompt_runner_content()
        assert _validate_prompt_runner_file(content) == []

    def test_no_headings(self) -> None:
        issues = _validate_prompt_runner_file("Just some text, no prompts.")
        assert len(issues) == 1
        assert "## Prompt N:" in issues[0]

    def test_missing_code_blocks(self) -> None:
        content = "## Prompt 1: Only Heading\n\nNo code blocks here.\n"
        issues = _validate_prompt_runner_file(content)
        assert len(issues) == 1
        assert "fence markers" in issues[0]

    def test_only_one_code_block(self) -> None:
        content = (
            "## Prompt 1: Partial\n\n"
            "```\nGenerate something.\n```\n\n"
            "Missing the validation block.\n"
        )
        issues = _validate_prompt_runner_file(content)
        assert len(issues) == 1
        assert "expected 4" in issues[0]

    def test_too_many_code_blocks(self) -> None:
        content = (
            "## Prompt 1: Extra Fences\n\n"
            "```\nGenerate.\n```\n\n"
            "```\nValidate.\n```\n\n"
            "```\nExtra block.\n```\n"
        )
        issues = _validate_prompt_runner_file(content)
        assert len(issues) == 1
        assert "nested fences" in issues[0]

    def test_multiple_valid_sections(self) -> None:
        content = _valid_prompt_runner_content()
        assert _validate_prompt_runner_file(content) == []

    def test_first_section_valid_second_invalid(self) -> None:
        content = (
            "## Prompt 1: Good\n\n"
            "```\nGen.\n```\n\n"
            "```\nVal.\n```\n\n"
            "## Prompt 2: Bad\n\n"
            "Only one block:\n"
            "```\nGen.\n```\n"
        )
        issues = _validate_prompt_runner_file(content)
        assert len(issues) == 1
        assert "Prompt 2" in issues[0]

    def test_single_prompt_valid(self) -> None:
        content = (
            "## Prompt 1: Solo\n\n"
            "```\nDo the thing.\n```\n\n"
            "```\nCheck the thing.\nVERDICT: pass\n```\n"
        )
        assert _validate_prompt_runner_file(content) == []

    def test_language_tagged_fences_count(self) -> None:
        content = (
            "## Prompt 1: Tagged\n\n"
            "```yaml\nGenerate YAML.\n```\n\n"
            "```text\nValidate YAML.\n```\n"
        )
        assert _validate_prompt_runner_file(content) == []


# ---------------------------------------------------------------------------
# Tests: formatting helpers
# ---------------------------------------------------------------------------

class TestFormatHelpers:

    def test_bullet_list_with_items(self) -> None:
        result = _format_bullet_list(["alpha", "beta"])
        assert result == "- alpha\n- beta"

    def test_bullet_list_empty(self) -> None:
        assert _format_bullet_list([]) == "(none)"

    def test_expected_files_block(self) -> None:
        result = _format_expected_files_block(["a.yaml", "b.yaml"])
        assert "  - a.yaml" in result
        assert "  - b.yaml" in result

    def test_input_artifacts_block_no_inputs(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        phase = _minimal_phase(workspace, inputs=[])
        result = _format_input_artifacts_block(phase, workspace)
        assert "no input artifacts" in result

    def test_prior_phases_block_empty(self) -> None:
        result = _format_prior_phases_block([])
        assert "No prior phases" in result

    def test_prior_phases_block_with_completed(self) -> None:
        state = PhaseState(
            phase_id="PH-000-requirements-inventory",
            status=PhaseStatus.COMPLETED,
            started_at="2026-04-08T10:00:00Z",
            completed_at="2026-04-08T10:15:00Z",
            prompt_file="runs/phase-0/prompt-file.md",
            cross_ref_result_path=None,
            cross_ref_retries=0,
            git_commit="abc1234",
        )
        result = _format_prior_phases_block([state])
        assert "PH-000-requirements-inventory" in result
        assert "Requirements Inventory" in result
        assert "completed" in result

    def test_cross_ref_feedback_none(self) -> None:
        assert _format_cross_ref_feedback(None) == ""

    def test_cross_ref_feedback_with_issues(self) -> None:
        issue = CrossRefIssue(
            category="traceability",
            description="RI-003 has no feature mapping",
            affected_elements=["RI-003"],
            severity="blocking",
        )
        check_pass = CrossRefCheckResult(status="pass", issues=[])
        check_fail = CrossRefCheckResult(status="fail", issues=[issue])
        feedback = CrossReferenceResult(
            verdict="fail",
            traceability=check_fail,
            coverage=check_pass,
            consistency=check_pass,
            integration=check_pass,
        )
        result = _format_cross_ref_feedback(feedback)
        assert "CROSS-REFERENCE FEEDBACK" in result
        assert "RI-003" in result
        assert "blocking" in result


# ---------------------------------------------------------------------------
# Tests: assemble_meta_prompt
# ---------------------------------------------------------------------------

class TestAssembleMetaPrompt:

    def test_contains_all_template_sections(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        prompt = assemble_meta_prompt(context)
        assert "## ROLE AND TASK" in prompt
        assert "## PHASE CONFIGURATION" in prompt
        assert "## INPUT CONTEXT" in prompt
        assert "## PRIOR PHASE CONTEXT" in prompt
        assert "## PROMPT-RUNNER FORMAT CONSTRAINTS" in prompt
        assert "## DECOMPOSITION GUIDANCE" in prompt
        assert "## WORKSPACE CONVENTIONS" in prompt

    def test_phase_config_fields_present(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        prompt = assemble_meta_prompt(context)
        assert phase.phase_id in prompt
        assert phase.phase_name in prompt
        assert phase.output_artifact_path in prompt
        assert phase.extraction_focus in prompt
        assert phase.generation_instructions in prompt
        assert phase.judge_guidance in prompt

    def test_can_include_deterministic_validation_helper(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        req_dir = workspace / "docs" / "requirements"
        req_dir.mkdir(parents=True)
        (req_dir / "requirements-inventory.yaml").write_text("items: []\n", encoding="utf-8")
        (req_dir / "raw-requirements.md").write_text("# Raw\n", encoding="utf-8")
        phase = _phase_001_phase(workspace)
        helper = tmp_path / "phase-1-deterministic-validation.py"
        helper.write_text("# helper\n", encoding="utf-8")
        prompt = assemble_meta_prompt(
            PromptGenerationContext(phase_config=phase, workspace_dir=workspace),
            deterministic_validation_helper_path=helper,
        )
        assert "deterministic-validation" in prompt
        assert str(helper) in prompt
        assert "The available typed block names are:" in prompt
        assert "```deterministic-validation" not in prompt
        assert "Do not show this block as a fenced example inside a prompt body" in prompt

    def test_input_context_embedded(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        prompt = assemble_meta_prompt(context)
        assert "The system shall do X." in prompt

    def test_input_context_file_reference_mode(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
            input_context_mode="file-reference",
        )
        prompt = assemble_meta_prompt(context)
        assert "Do not rely on inlined file contents" in prompt
        assert "Read this file directly from the workspace" in prompt
        assert "The system shall do X." not in prompt

    def test_cross_ref_feedback_included(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        check_pass = CrossRefCheckResult(status="pass", issues=[])
        issue = CrossRefIssue(
            category="coverage",
            description="Missing coverage for RI-005",
            affected_elements=["RI-005"],
            severity="blocking",
        )
        check_fail = CrossRefCheckResult(status="fail", issues=[issue])
        feedback = CrossReferenceResult(
            verdict="fail",
            traceability=check_pass,
            coverage=check_fail,
            consistency=check_pass,
            integration=check_pass,
        )
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
            cross_ref_feedback=feedback,
        )
        prompt = assemble_meta_prompt(context)
        assert "CROSS-REFERENCE FEEDBACK" in prompt
        assert "RI-005" in prompt

    def test_no_cross_ref_feedback_when_none(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        prompt = assemble_meta_prompt(context)
        assert "CROSS-REFERENCE FEEDBACK" not in prompt

    def test_checklist_examples_present(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        prompt = assemble_meta_prompt(context)
        assert "Good example one" in prompt
        assert "Bad example" in prompt


# ---------------------------------------------------------------------------
# Tests: generate_prompt_file
# ---------------------------------------------------------------------------

class TestGeneratePromptFile:

    def test_writes_valid_output(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        valid_content = _valid_prompt_runner_content()
        client = FakeClaudeClient(
            scripted=[ClaudeResponse(stdout=valid_content, stderr="", returncode=0)],
        )
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        result_path = generate_prompt_file(context, client)
        assert result_path.exists()
        written = result_path.read_text(encoding="utf-8")
        assert "## Prompt 1:" in written
        assert "## Prompt 2:" in written

    def test_codex_file_reference_mode_uses_deterministic_ph000_template(self, tmp_path: Path) -> None:
        workspace, _phase = _create_workspace_with_input(tmp_path)
        from methodology_runner.phases import get_phase

        class UnusedClient:
            def call(self, call: object) -> object:
                raise AssertionError("deterministic template should bypass backend")

        context = PromptGenerationContext(
            phase_config=get_phase("PH-000-requirements-inventory"),
            workspace_dir=workspace,
            input_context_mode="file-reference",
        )
        result_path = generate_prompt_file(context, UnusedClient())  # type: ignore[arg-type]
        written = result_path.read_text(encoding="utf-8")
        assert "## Prompt 1: Produce Requirements Inventory [MODEL:gpt-5.4]" in written
        assert "```required-files" in written
        assert "docs/requirements/raw-requirements.md" in written
        assert "Use the selected generator skills loaded in the prelude as the primary source" in written
        assert "Use the selected judge skills loaded in the prelude as the primary source" in written
        assert "## Prompt 2:" not in written
        assert "## Prompt 3:" not in written

    def test_output_path_default_location(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        client = FakeClaudeClient(
            scripted=[
                ClaudeResponse(
                    stdout=_valid_prompt_runner_content(),
                    stderr="",
                    returncode=0,
                ),
            ],
        )
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        result_path = generate_prompt_file(context, client)
        expected = workspace / PROMPT_RUNNER_FILES_DIR / f"{phase.phase_id}.md"
        assert result_path == expected

    def test_custom_output_path(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        custom_path = tmp_path / "custom" / "output.md"
        client = FakeClaudeClient(
            scripted=[
                ClaudeResponse(
                    stdout=_valid_prompt_runner_content(),
                    stderr="",
                    returncode=0,
                ),
            ],
        )
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        result_path = generate_prompt_file(
            context, client, output_path=custom_path,
        )
        assert result_path == custom_path
        assert custom_path.exists()

    def test_phase_001_stages_deterministic_validation_helper(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        req_dir = workspace / "docs" / "requirements"
        req_dir.mkdir(parents=True)
        (req_dir / "requirements-inventory.yaml").write_text("items: []\n", encoding="utf-8")
        (req_dir / "raw-requirements.md").write_text("# Raw\n", encoding="utf-8")
        phase = _phase_001_phase(workspace)
        output_path = workspace / ".methodology-runner" / "runs" / "phase-1" / "prompt-file.md"
        client = FakeClaudeClient(
            scripted=[
                ClaudeResponse(
                    stdout=_valid_prompt_runner_content(),
                    stderr="",
                    returncode=0,
                ),
            ],
        )
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        result_path = generate_prompt_file(context, client, output_path=output_path)
        assert result_path == output_path
        helper_path = output_path.parent / "phase-1-deterministic-validation.py"
        assert helper_path.exists()

    def test_retries_on_invalid_output(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        bad_content = "Here is the file:\n\nNo actual prompt sections."
        good_content = _valid_prompt_runner_content()
        client = FakeClaudeClient(
            scripted=[
                ClaudeResponse(stdout=bad_content, stderr="", returncode=0),
                ClaudeResponse(stdout=good_content, stderr="", returncode=0),
            ],
        )
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        result_path = generate_prompt_file(context, client)
        assert result_path.exists()
        assert len(client.received) == MAX_GENERATION_ATTEMPTS

    def test_retry_prompt_includes_feedback(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        bad_content = "No prompts here."
        good_content = _valid_prompt_runner_content()
        client = FakeClaudeClient(
            scripted=[
                ClaudeResponse(stdout=bad_content, stderr="", returncode=0),
                ClaudeResponse(stdout=good_content, stderr="", returncode=0),
            ],
        )
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        generate_prompt_file(context, client)
        retry_prompt = client.received[1].prompt
        assert "RETRY FEEDBACK" in retry_prompt
        assert "## Prompt N:" in retry_prompt

    def test_saves_exact_attempt_prompt_before_backend_call(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        client = FakeClaudeClient(
            scripted=[
                ClaudeResponse(
                    stdout=_valid_prompt_runner_content(),
                    stderr="",
                    returncode=0,
                ),
            ],
        )
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )

        generate_prompt_file(context, client)

        saved_prompt = (
            workspace
            / PROMPT_RUNNER_FILES_DIR
            / "logs"
            / phase.phase_id
            / "attempt-1-input-prompt.md"
        )
        assert saved_prompt.exists()
        assert saved_prompt.read_text(encoding="utf-8") == client.received[0].prompt

    def test_raises_after_all_attempts_exhausted(
        self, tmp_path: Path,
    ) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        bad_content = "Not valid at all."
        client = FakeClaudeClient(
            scripted=[
                ClaudeResponse(stdout=bad_content, stderr="", returncode=0),
                ClaudeResponse(stdout=bad_content, stderr="", returncode=0),
            ],
        )
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        with pytest.raises(PromptGenerationError, match="Failed to produce"):
            generate_prompt_file(context, client)

    def test_raises_on_claude_invocation_error(
        self, tmp_path: Path,
    ) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)

        class FailingClient:
            def call(self, call: object) -> object:
                raise RuntimeError("Claude crashed")

        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        with pytest.raises(PromptGenerationError, match="backend invocation failed"):
            generate_prompt_file(context, FailingClient())  # type: ignore[arg-type]

    def test_raises_on_empty_response(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        client = FakeClaudeClient(
            scripted=[
                ClaudeResponse(stdout="", stderr="", returncode=0),
                ClaudeResponse(stdout="   ", stderr="", returncode=0),
            ],
        )
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        with pytest.raises(PromptGenerationError, match="Failed to produce"):
            generate_prompt_file(context, client)

    def test_model_passed_to_claude_call(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        client = FakeClaudeClient(
            scripted=[
                ClaudeResponse(
                    stdout=_valid_prompt_runner_content(),
                    stderr="",
                    returncode=0,
                ),
            ],
        )
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        generate_prompt_file(context, client, model="claude-sonnet-4-6")
        assert client.received[0].model == "claude-sonnet-4-6"

    def test_log_dir_created(self, tmp_path: Path) -> None:
        workspace, phase = _create_workspace_with_input(tmp_path)
        client = FakeClaudeClient(
            scripted=[
                ClaudeResponse(
                    stdout=_valid_prompt_runner_content(),
                    stderr="",
                    returncode=0,
                ),
            ],
        )
        context = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        generate_prompt_file(context, client)
        log_dir = (
            workspace / PROMPT_RUNNER_FILES_DIR / "logs" / phase.phase_id
        )
        assert log_dir.is_dir()


# ---------------------------------------------------------------------------
# Tests: PromptGenerationError
# ---------------------------------------------------------------------------

class TestPromptGenerationError:

    def test_attributes(self) -> None:
        err = PromptGenerationError("PH-001-test", "something broke")
        assert err.phase_id == "PH-001-test"
        assert err.reason == "something broke"
        assert "PH-001-test" in str(err)
        assert "something broke" in str(err)


# ---------------------------------------------------------------------------
# Tests: PromptGenerationContext
# ---------------------------------------------------------------------------

class TestPromptGenerationContext:

    def test_frozen(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        phase = _minimal_phase(workspace, inputs=[])
        ctx = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        with pytest.raises(AttributeError):
            ctx.cross_ref_feedback = None  # type: ignore[misc]

    def test_defaults(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        phase = _minimal_phase(workspace, inputs=[])
        ctx = PromptGenerationContext(
            phase_config=phase,
            workspace_dir=workspace,
        )
        assert ctx.completed_phases == []
        assert ctx.cross_ref_feedback is None


# ---------------------------------------------------------------------------
# Tests: META_PROMPT_TEMPLATE
# ---------------------------------------------------------------------------

class TestMetaPromptTemplate:

    def test_has_all_placeholders(self) -> None:
        expected_placeholders = {
            "phase_id",
            "phase_name",
            "generation_instructions",
            "input_artifacts_block",
            "output_artifact_path",
            "output_format",
            "expected_output_files_block",
            "deterministic_validation_block",
            "extraction_focus",
            "artifact_schema_description",
            "judge_guidance",
            "checklist_good_block",
            "checklist_bad_block",
            "input_context_intro",
            "input_context",
            "prior_phases_block",
            "cross_ref_feedback_block",
        }
        import string
        formatter = string.Formatter()
        found = {
            field_name
            for _, field_name, _, _ in formatter.parse(META_PROMPT_TEMPLATE)
            if field_name is not None
        }
        assert found == expected_placeholders

    def test_format_constraints_section_present(self) -> None:
        assert "PROMPT-RUNNER FORMAT CONSTRAINTS" in META_PROMPT_TEMPLATE

    def test_decomposition_guidance_present(self) -> None:
        assert "DECOMPOSITION GUIDANCE" in META_PROMPT_TEMPLATE

    def test_workspace_conventions_present(self) -> None:
        assert "WORKSPACE CONVENTIONS" in META_PROMPT_TEMPLATE

    def test_example_structure_removed(self) -> None:
        assert "Example structure:" not in META_PROMPT_TEMPLATE
        assert "## Prompt 1: Extract Requirements Checklist" not in META_PROMPT_TEMPLATE

    def test_verdict_instruction_present(self) -> None:
        assert "VERDICT: pass" in META_PROMPT_TEMPLATE


# ---------------------------------------------------------------------------
# Tests: skill manifest in meta-prompt
# ---------------------------------------------------------------------------

def _setup_phase_0_workspace(tmp_path: Path) -> Path:
    """Create a workspace with the raw-requirements.md file required by PH-000."""
    req_dir = tmp_path / "docs" / "requirements"
    req_dir.mkdir(parents=True)
    (req_dir / "raw-requirements.md").write_text(
        "# Requirements\n\nThe system shall do X.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_meta_prompt_includes_skill_manifest_section_when_provided(tmp_path):
    from methodology_runner.models import (
        PhaseSkillManifest, SkillChoice, SkillSource,
    )
    from methodology_runner.phases import get_phase
    from methodology_runner.prompt_generator import (
        PromptGenerationContext, assemble_meta_prompt,
    )
    workspace = _setup_phase_0_workspace(tmp_path)
    manifest = PhaseSkillManifest(
        phase_id="PH-000-requirements-inventory",
        selector_run_at="2026-04-09T10:00:00+00:00",
        selector_model="test",
        generator_skills=[
            SkillChoice(
                id="ph000-requirements-extraction",
                source=SkillSource.BASELINE,
                rationale="Baseline",
            ),
        ],
        judge_skills=[],
        overall_rationale="Test",
    )
    ctx = PromptGenerationContext(
        phase_config=get_phase("PH-000-requirements-inventory"),
        workspace_dir=workspace,
        phase_skill_manifest=manifest,
    )
    prompt = assemble_meta_prompt(ctx)
    assert "ph000-requirements-extraction" in prompt
    assert "generator_skills" in prompt.lower() or "generator skill" in prompt.lower()


def test_meta_prompt_without_skill_manifest_omits_section(tmp_path):
    from methodology_runner.phases import get_phase
    from methodology_runner.prompt_generator import (
        PromptGenerationContext, assemble_meta_prompt,
    )
    workspace = _setup_phase_0_workspace(tmp_path)
    ctx = PromptGenerationContext(
        phase_config=get_phase("PH-000-requirements-inventory"),
        workspace_dir=workspace,
    )
    prompt = assemble_meta_prompt(ctx)
    # Should not raise; should not contain a skill manifest header
    assert "SKILL MANIFEST" not in prompt
