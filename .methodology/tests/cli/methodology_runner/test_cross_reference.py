"""Tests for methodology_runner.cross_reference.

Covers JSON extraction, result parsing, prompt assembly, the two public
verification functions using FakeClaudeClient, per-phase template
completeness, and error handling paths.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_runner.claude_client import ClaudeResponse, FakeClaudeClient

from methodology_runner.models import (
    CrossRefResult,
    InputRole,
    InputSourceTemplate,
    PhaseConfig,
)
from methodology_runner.phases import PHASES, PHASE_MAP
from methodology_runner.cross_reference import (
    CROSS_REF_LOG_DIR,
    CROSS_REF_SYSTEM_PROMPT,
    END_TO_END_PROMPT_TEMPLATE,
    PHASE_CROSS_REF_CHECKS,
    CrossReferenceError,
    _BARE_JSON_RE,
    _CATEGORY_NAMES,
    _CROSS_REF_PROMPT_TEMPLATE,
    _JSON_FENCE_RE,
    _build_coverage_summary,
    _build_full_prompt,
    _call_backend_for_verification,
    _collect_issues,
    _extract_json_block,
    _format_prior_phases_block,
    _parse_check_result,
    _parse_cross_ref_result,
    assemble_cross_ref_prompt,
    assemble_end_to_end_prompt,
    verify_end_to_end,
    verify_phase_cross_references,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _passing_json() -> str:
    """Return a JSON string representing a fully-passing verification."""
    return json.dumps({
        "verdict": "pass",
        "checks": {
            "traceability": {"status": "pass", "issues": []},
            "coverage": {"status": "pass", "issues": []},
            "consistency": {"status": "pass", "issues": []},
            "integration": {"status": "pass", "issues": []},
        },
    })


def _failing_json(
    *,
    category: str = "traceability",
    description: str = "RI-001 not found in inventory",
    elements: list[str] | None = None,
    severity: str = "blocking",
) -> str:
    """Return JSON with one blocking issue in the named category."""
    issue = {
        "category": category,
        "description": description,
        "affected_elements": elements or ["RI-001"],
        "severity": severity,
    }
    checks: dict = {}
    for cat in _CATEGORY_NAMES:
        if cat == category:
            checks[cat] = {"status": "fail", "issues": [issue]}
        else:
            checks[cat] = {"status": "pass", "issues": []}
    return json.dumps({"verdict": "fail", "checks": checks})


def _passing_json_with_percentages(
    pcts: dict[str, float] | None = None,
) -> str:
    """Return passing JSON that includes coverage_percentages."""
    if pcts is None:
        pcts = {
            "traceability": 100.0,
            "coverage": 87.5,
            "consistency": 100.0,
            "integration": 95.0,
        }
    return json.dumps({
        "verdict": "pass",
        "checks": {
            "traceability": {"status": "pass", "issues": []},
            "coverage": {"status": "pass", "issues": []},
            "consistency": {"status": "pass", "issues": []},
            "integration": {"status": "pass", "issues": []},
        },
        "coverage_percentages": pcts,
    })


def _wrap_in_fence(body: str) -> str:
    """Wrap *body* in a ```json fence."""
    return f"Some reasoning here.\n\n```json\n{body}\n```\n"


def _wrap_bare(body: str) -> str:
    """Return *body* preceded by reasoning prose."""
    return f"I checked all cross-references.\n\n{body}\n"


def test_call_backend_for_verification_uses_selected_backend(
    tmp_path: Path, monkeypatch,
):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    client = FakeClaudeClient(scripted=[
        ClaudeResponse(stdout=_wrap_in_fence(_passing_json()), stderr="", returncode=0),
    ])
    captured: list[str] = []

    def _fake_make_client(backend: str):
        captured.append(backend)
        return client

    monkeypatch.setattr("prompt_runner.client_factory.make_client", _fake_make_client)

    result = _call_backend_for_verification(
        prompt="Verify",
        phase_id="PH-000",
        workspace=workspace,
        backend="codex",
        model=None,
        claude_client=None,
    )

    assert result.passed is True
    assert captured == ["codex"]


def _minimal_phase(
    *,
    phase_id: str = "PH-000-requirements-inventory",
    phase_number: int = 0,
) -> PhaseConfig:
    """Build a minimal PhaseConfig for testing."""
    return PhaseConfig(
        phase_id=phase_id,
        phase_name="Test Phase",
        phase_number=phase_number,
        abbreviation="TP",
        predecessors=[],
        input_source_templates=[
            InputSourceTemplate(
                ref_template="{workspace}/docs/requirements/raw-requirements.md",
                role=InputRole.PRIMARY,
                format="markdown",
                description="Raw requirements document",
            ),
        ],
        output_artifact_path="docs/test/output.yaml",
        output_format="yaml",
        expected_output_files=["docs/test/output.yaml"],
        extraction_focus="Test extraction focus",
        generation_instructions="Test generation instructions",
        judge_guidance="Test judge guidance",
        artifact_format="yaml",
        artifact_schema_description="items:\n  - id: T-NNN",
        checklist_examples_good=["Good example"],
        checklist_examples_bad=["Bad example"],
    )


# ---------------------------------------------------------------------------
# Tests: _extract_json_block
# ---------------------------------------------------------------------------

class TestExtractJsonBlock:

    def test_extracts_fenced_json(self) -> None:
        text = _wrap_in_fence('{"verdict": "pass"}')
        result = _extract_json_block(text)
        assert result is not None
        assert '"verdict"' in result

    def test_extracts_fenced_without_json_lang(self) -> None:
        text = "reasoning\n\n```\n{\"verdict\": \"pass\"}\n```\n"
        result = _extract_json_block(text)
        assert result is not None
        assert '"verdict"' in result

    def test_extracts_bare_json(self) -> None:
        text = _wrap_bare('{"verdict": "pass", "checks": {}}')
        result = _extract_json_block(text)
        assert result is not None
        assert '"verdict"' in result

    def test_returns_none_for_no_json(self) -> None:
        result = _extract_json_block("No JSON here at all.")
        assert result is None

    def test_prefers_fenced_over_bare(self) -> None:
        text = (
            'mention {"verdict": "fail"} in prose\n\n'
            '```json\n{"verdict": "pass"}\n```\n'
        )
        result = _extract_json_block(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["verdict"] == "pass"


# ---------------------------------------------------------------------------
# Tests: _parse_check_result
# ---------------------------------------------------------------------------

class TestParseCheckResult:

    def test_parses_passing_check(self) -> None:
        raw = {"status": "pass", "issues": []}
        result = _parse_check_result(raw)
        assert result.status == "pass"
        assert result.issues == []

    def test_parses_failing_check_with_issues(self) -> None:
        raw = {
            "status": "fail",
            "issues": [{
                "category": "coverage",
                "description": "Missing coverage for RI-003",
                "affected_elements": ["RI-003"],
                "severity": "blocking",
            }],
        }
        result = _parse_check_result(raw)
        assert result.status == "fail"
        assert len(result.issues) == 1
        assert result.issues[0].category == "coverage"
        assert result.issues[0].affected_elements == ["RI-003"]

    def test_defaults_for_missing_fields(self) -> None:
        result = _parse_check_result({})
        assert result.status == "fail"
        assert result.issues == []

    def test_issue_severity_defaults_to_warning(self) -> None:
        raw = {
            "status": "fail",
            "issues": [{"description": "minor thing"}],
        }
        result = _parse_check_result(raw)
        assert result.issues[0].severity == "warning"


# ---------------------------------------------------------------------------
# Tests: _parse_cross_ref_result
# ---------------------------------------------------------------------------

class TestParseCrossRefResult:

    def test_parses_passing_result_from_fence(self) -> None:
        text = _wrap_in_fence(_passing_json())
        result = _parse_cross_ref_result(text)
        assert result.passed is True
        assert result.issues == []
        assert result.traceability_gaps == []
        assert result.orphaned_elements == []

    def test_parses_failing_result(self) -> None:
        text = _wrap_in_fence(_failing_json(
            category="traceability",
            description="RI-001 has no verbatim match",
            elements=["RI-001"],
        ))
        result = _parse_cross_ref_result(text)
        assert result.passed is False
        assert len(result.issues) == 1
        assert "RI-001" in result.issues[0]
        assert "RI-001" in result.traceability_gaps

    def test_parses_bare_json(self) -> None:
        text = _wrap_bare(_passing_json())
        result = _parse_cross_ref_result(text)
        assert result.passed is True

    def test_raises_on_no_json(self) -> None:
        with pytest.raises(CrossReferenceError, match="No JSON block"):
            _parse_cross_ref_result("No JSON here.")

    def test_raises_on_invalid_json(self) -> None:
        text = "```json\n{not valid json}\n```\n"
        with pytest.raises(CrossReferenceError, match="Invalid JSON"):
            _parse_cross_ref_result(text)

    def test_raises_on_non_object(self) -> None:
        text = '```json\n[1, 2, 3]\n```\n'
        with pytest.raises(CrossReferenceError, match="Expected a JSON object"):
            _parse_cross_ref_result(text)

    def test_raises_on_missing_checks(self) -> None:
        text = '```json\n{"verdict": "pass"}\n```\n'
        with pytest.raises(CrossReferenceError, match="Missing or invalid"):
            _parse_cross_ref_result(text)

    def test_integration_issues_become_orphaned_elements(self) -> None:
        text = _wrap_in_fence(_failing_json(
            category="integration",
            description="CMP-099 is orphaned",
            elements=["CMP-099"],
        ))
        result = _parse_cross_ref_result(text)
        assert "CMP-099" in result.orphaned_elements

    def test_multiple_issues_across_categories(self) -> None:
        checks = {}
        for cat in _CATEGORY_NAMES:
            checks[cat] = {
                "status": "fail",
                "issues": [{
                    "category": cat,
                    "description": f"{cat} issue",
                    "affected_elements": [f"EL-{cat[:3].upper()}"],
                    "severity": "blocking",
                }],
            }
        text = _wrap_in_fence(json.dumps({
            "verdict": "fail",
            "checks": checks,
        }))
        result = _parse_cross_ref_result(text)
        assert result.passed is False
        assert len(result.issues) == 4

    def test_coverage_summary_binary_fallback_for_passing(self) -> None:
        text = _wrap_in_fence(_passing_json())
        result = _parse_cross_ref_result(text)
        assert result.coverage_summary == {
            "traceability": 1.0,
            "coverage": 1.0,
            "consistency": 1.0,
            "integration": 1.0,
        }

    def test_coverage_summary_binary_fallback_for_failing(self) -> None:
        text = _wrap_in_fence(_failing_json(category="coverage"))
        result = _parse_cross_ref_result(text)
        assert result.coverage_summary["coverage"] == 0.0
        assert result.coverage_summary["traceability"] == 1.0

    def test_checks_key_is_list_raises(self) -> None:
        text = '```json\n{"verdict": "fail", "checks": [1,2]}\n```\n'
        with pytest.raises(CrossReferenceError, match="Missing or invalid"):
            _parse_cross_ref_result(text)

    def test_coverage_percentages_parsed(self) -> None:
        text = _wrap_in_fence(_passing_json_with_percentages({
            "traceability": 100.0,
            "coverage": 87.5,
            "consistency": 100.0,
            "integration": 95.0,
        }))
        result = _parse_cross_ref_result(text)
        assert result.coverage_summary["traceability"] == 1.0
        assert result.coverage_summary["coverage"] == pytest.approx(0.875)
        assert result.coverage_summary["consistency"] == 1.0
        assert result.coverage_summary["integration"] == pytest.approx(0.95)

    def test_missing_percentages_falls_back_to_binary(self) -> None:
        text = _wrap_in_fence(_passing_json())
        result = _parse_cross_ref_result(text)
        assert result.coverage_summary == {
            "traceability": 1.0,
            "coverage": 1.0,
            "consistency": 1.0,
            "integration": 1.0,
        }

    def test_partial_percentages_mixed_with_fallback(self) -> None:
        data = json.loads(_passing_json())
        data["coverage_percentages"] = {"coverage": 75.0}
        text = _wrap_in_fence(json.dumps(data))
        result = _parse_cross_ref_result(text)
        assert result.coverage_summary["coverage"] == pytest.approx(0.75)
        assert result.coverage_summary["traceability"] == 1.0

    def test_invalid_percentage_falls_back_to_binary(self) -> None:
        data = json.loads(_passing_json())
        data["coverage_percentages"] = {"traceability": "not-a-number"}
        text = _wrap_in_fence(json.dumps(data))
        result = _parse_cross_ref_result(text)
        assert result.coverage_summary["traceability"] == 1.0

    def test_percentage_clamped_to_zero_one(self) -> None:
        data = json.loads(_passing_json())
        data["coverage_percentages"] = {"coverage": 150.0}
        text = _wrap_in_fence(json.dumps(data))
        result = _parse_cross_ref_result(text)
        assert result.coverage_summary["coverage"] == 1.0


# ---------------------------------------------------------------------------
# Tests: _build_full_prompt
# ---------------------------------------------------------------------------

class TestBuildFullPrompt:

    def test_prepends_system_prompt(self) -> None:
        user = "Check phase 0 output."
        full = _build_full_prompt(user)
        assert full.startswith(CROSS_REF_SYSTEM_PROMPT)
        assert "Check phase 0 output." in full

    def test_contains_separator(self) -> None:
        full = _build_full_prompt("user prompt")
        assert "\n\n---\n\n" in full

    def test_system_prompt_has_json_schema(self) -> None:
        full = _build_full_prompt("anything")
        assert '"verdict"' in full
        assert '"coverage_percentages"' in full


# ---------------------------------------------------------------------------
# Tests: _collect_issues
# ---------------------------------------------------------------------------

class TestCollectIssues:

    def test_empty_result(self) -> None:
        from methodology_runner.models import CrossReferenceResult
        result = CrossReferenceResult(
            verdict="pass",
            traceability=_parse_check_result({"status": "pass", "issues": []}),
            coverage=_parse_check_result({"status": "pass", "issues": []}),
            consistency=_parse_check_result({"status": "pass", "issues": []}),
            integration=_parse_check_result({"status": "pass", "issues": []}),
        )
        issues, gaps, orphans = _collect_issues(result)
        assert issues == []
        assert gaps == []
        assert orphans == []

    def test_traceability_issues_routed_to_gaps(self) -> None:
        from methodology_runner.models import CrossReferenceResult
        result = CrossReferenceResult(
            verdict="fail",
            traceability=_parse_check_result({
                "status": "fail",
                "issues": [{
                    "category": "traceability",
                    "description": "RI-001 missing",
                    "affected_elements": ["RI-001"],
                    "severity": "blocking",
                }],
            }),
            coverage=_parse_check_result({"status": "pass", "issues": []}),
            consistency=_parse_check_result({"status": "pass", "issues": []}),
            integration=_parse_check_result({"status": "pass", "issues": []}),
        )
        issues, gaps, orphans = _collect_issues(result)
        assert len(issues) == 1
        assert "RI-001" in gaps
        assert orphans == []

    def test_integration_issues_routed_to_orphans(self) -> None:
        from methodology_runner.models import CrossReferenceResult
        result = CrossReferenceResult(
            verdict="fail",
            traceability=_parse_check_result({"status": "pass", "issues": []}),
            coverage=_parse_check_result({"status": "pass", "issues": []}),
            consistency=_parse_check_result({"status": "pass", "issues": []}),
            integration=_parse_check_result({
                "status": "fail",
                "issues": [{
                    "category": "integration",
                    "description": "CMP-099 orphaned",
                    "affected_elements": ["CMP-099"],
                    "severity": "blocking",
                }],
            }),
        )
        issues, gaps, orphans = _collect_issues(result)
        assert len(issues) == 1
        assert gaps == []
        assert "CMP-099" in orphans


# ---------------------------------------------------------------------------
# Tests: _build_coverage_summary
# ---------------------------------------------------------------------------

class TestBuildCoverageSummary:

    def test_with_percentages(self) -> None:
        from methodology_runner.models import CrossReferenceResult
        result = CrossReferenceResult(
            verdict="pass",
            traceability=_parse_check_result({"status": "pass", "issues": []}),
            coverage=_parse_check_result({"status": "pass", "issues": []}),
            consistency=_parse_check_result({"status": "pass", "issues": []}),
            integration=_parse_check_result({"status": "pass", "issues": []}),
        )
        pcts = {
            "traceability": 95.0,
            "coverage": 80.0,
            "consistency": 100.0,
            "integration": 90.0,
        }
        summary = _build_coverage_summary(result, pcts)
        assert summary["traceability"] == pytest.approx(0.95)
        assert summary["coverage"] == pytest.approx(0.80)
        assert summary["consistency"] == 1.0
        assert summary["integration"] == pytest.approx(0.90)

    def test_without_percentages_uses_binary(self) -> None:
        from methodology_runner.models import CrossReferenceResult
        result = CrossReferenceResult(
            verdict="fail",
            traceability=_parse_check_result({"status": "pass", "issues": []}),
            coverage=_parse_check_result({"status": "fail", "issues": []}),
            consistency=_parse_check_result({"status": "pass", "issues": []}),
            integration=_parse_check_result({"status": "fail", "issues": []}),
        )
        summary = _build_coverage_summary(result, {})
        assert summary == {
            "traceability": 1.0,
            "coverage": 0.0,
            "consistency": 1.0,
            "integration": 0.0,
        }

    def test_clamps_over_100(self) -> None:
        from methodology_runner.models import CrossReferenceResult
        result = CrossReferenceResult(
            verdict="pass",
            traceability=_parse_check_result({"status": "pass", "issues": []}),
            coverage=_parse_check_result({"status": "pass", "issues": []}),
            consistency=_parse_check_result({"status": "pass", "issues": []}),
            integration=_parse_check_result({"status": "pass", "issues": []}),
        )
        summary = _build_coverage_summary(result, {"traceability": 200.0})
        assert summary["traceability"] == 1.0

    def test_invalid_value_falls_back(self) -> None:
        from methodology_runner.models import CrossReferenceResult
        result = CrossReferenceResult(
            verdict="pass",
            traceability=_parse_check_result({"status": "pass", "issues": []}),
            coverage=_parse_check_result({"status": "pass", "issues": []}),
            consistency=_parse_check_result({"status": "pass", "issues": []}),
            integration=_parse_check_result({"status": "pass", "issues": []}),
        )
        summary = _build_coverage_summary(result, {"coverage": "bad"})
        assert summary["coverage"] == 1.0


# ---------------------------------------------------------------------------
# Tests: _format_prior_phases_block
# ---------------------------------------------------------------------------

class TestFormatPriorPhasesBlock:

    def test_no_completed_phases(self) -> None:
        result = _format_prior_phases_block([])
        assert "none" in result.lower()

    def test_single_completed_phase(self) -> None:
        result = _format_prior_phases_block(
            ["PH-000-requirements-inventory"],
        )
        assert "Phase 0" in result
        assert "Requirements Inventory" in result
        assert "requirements-inventory.yaml" in result

    def test_multiple_completed_phases(self) -> None:
        result = _format_prior_phases_block([
            "PH-000-requirements-inventory",
            "PH-001-feature-specification",
        ])
        assert "Phase 0" in result
        assert "Phase 1" in result

    def test_unknown_phase_id_skipped(self) -> None:
        result = _format_prior_phases_block(["PH-999-nonexistent"])
        assert result == "  (none)"


# ---------------------------------------------------------------------------
# Tests: assemble_cross_ref_prompt
# ---------------------------------------------------------------------------

class TestAssembleCrossRefPrompt:

    def test_assembles_phase_0_prompt(self) -> None:
        phase = PHASE_MAP["PH-000-requirements-inventory"]
        prompt = assemble_cross_ref_prompt(phase, [])
        assert "Phase 0" in prompt
        assert "Requirements Inventory" in prompt
        assert "requirements-inventory.yaml" in prompt
        assert "Traceability" in prompt
        assert "Coverage" in prompt
        assert "Consistency" in prompt
        assert "Integration" in prompt

    def test_assembles_phase_1_with_prior(self) -> None:
        phase = PHASE_MAP["PH-001-feature-specification"]
        prompt = assemble_cross_ref_prompt(
            phase,
            ["PH-000-requirements-inventory"],
        )
        assert "Phase 1" in prompt
        assert "Feature Specification" in prompt
        assert "Phase 0" in prompt

    def test_all_phases_have_templates(self) -> None:
        for phase in PHASES:
            prompt = assemble_cross_ref_prompt(phase, [])
            assert "Traceability" in prompt
            assert "Coverage" in prompt

    def test_unknown_phase_raises(self) -> None:
        phase = _minimal_phase(phase_id="PH-999-nonexistent")
        with pytest.raises(CrossReferenceError, match="No cross-reference"):
            assemble_cross_ref_prompt(phase, [])


# ---------------------------------------------------------------------------
# Tests: assemble_end_to_end_prompt
# ---------------------------------------------------------------------------

class TestAssembleEndToEndPrompt:

    def test_contains_all_phase_outputs(self) -> None:
        prompt = assemble_end_to_end_prompt()
        assert "requirements-inventory.yaml" in prompt
        assert "feature-specification.yaml" in prompt
        assert "solution-design.yaml" in prompt
        assert "interface-contracts.yaml" in prompt
        assert "simulation-definitions.yaml" in prompt
        assert "implementation-plan.yaml" in prompt
        assert "verification-report.yaml" in prompt

    def test_contains_traceability_instructions(self) -> None:
        prompt = assemble_end_to_end_prompt()
        assert "RI-*" in prompt
        assert "FT-*" in prompt
        assert "CMP-*" in prompt
        assert "CTR-*" in prompt
        assert "SIM-*" in prompt
        assert "E2E-*" in prompt


# ---------------------------------------------------------------------------
# Tests: PHASE_CROSS_REF_CHECKS completeness
# ---------------------------------------------------------------------------

class TestPhaseCrossRefChecks:

    def test_all_phases_have_check_templates(self) -> None:
        for phase in PHASES:
            assert phase.phase_id in PHASE_CROSS_REF_CHECKS, (
                f"Missing cross-ref check template for {phase.phase_id}"
            )

    def test_no_extra_templates(self) -> None:
        valid_ids = {phase.phase_id for phase in PHASES}
        for key in PHASE_CROSS_REF_CHECKS:
            assert key in valid_ids, f"Unexpected template key: {key}"

    def test_each_template_has_four_sections(self) -> None:
        for phase_id, template in PHASE_CROSS_REF_CHECKS.items():
            assert "### 1. Traceability" in template, (
                f"{phase_id} missing Traceability section"
            )
            assert "### 2. Coverage" in template, (
                f"{phase_id} missing Coverage section"
            )
            assert "### 3. Consistency" in template, (
                f"{phase_id} missing Consistency section"
            )
            assert "### 4. Integration" in template, (
                f"{phase_id} missing Integration section"
            )

    def test_templates_contain_output_path_placeholder(self) -> None:
        for phase_id, template in PHASE_CROSS_REF_CHECKS.items():
            assert "{output_path}" in template, (
                f"{phase_id} template missing {{output_path}} placeholder"
            )

    def test_phase_0_references_raw_requirements(self) -> None:
        t = PHASE_CROSS_REF_CHECKS["PH-000-requirements-inventory"]
        assert "raw-requirements.md" in t

    def test_phase_1_references_phase_0(self) -> None:
        t = PHASE_CROSS_REF_CHECKS["PH-001-feature-specification"]
        assert "requirements-inventory.yaml" in t

    def test_phase_2_references_phase_1(self) -> None:
        t = PHASE_CROSS_REF_CHECKS["PH-002-architecture"]
        assert "feature-specification.yaml" in t

    def test_phase_3_references_phase_2(self) -> None:
        t = PHASE_CROSS_REF_CHECKS["PH-003-solution-design"]
        assert "stack-manifest.yaml" in t

    def test_phase_4_references_phase_3(self) -> None:
        t = PHASE_CROSS_REF_CHECKS["PH-004-interface-contracts"]
        assert "solution-design.yaml" in t

    def test_phase_5_references_phase_4(self) -> None:
        t = PHASE_CROSS_REF_CHECKS["PH-005-intelligent-simulations"]
        assert "interface-contracts.yaml" in t

    def test_phase_6_references_phases_1_through_5(self) -> None:
        t = PHASE_CROSS_REF_CHECKS["PH-006-incremental-implementation"]
        assert "feature-specification.yaml" in t
        assert "solution-design.yaml" in t
        assert "interface-contracts.yaml" in t
        assert "simulation-definitions.yaml" in t

    def test_phase_7_references_phases_0_1_3_6(self) -> None:
        t = PHASE_CROSS_REF_CHECKS["PH-007-verification-sweep"]
        assert "requirements-inventory.yaml" in t
        assert "feature-specification.yaml" in t
        assert "solution-design.yaml" in t
        assert "implementation-plan.yaml" in t


# ---------------------------------------------------------------------------
# Tests: verify_phase_cross_references (with FakeClaudeClient)
# ---------------------------------------------------------------------------

class TestVerifyPhaseCrossReferences:

    def test_passing_verification(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        phase = PHASE_MAP["PH-000-requirements-inventory"]
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout=_wrap_in_fence(_passing_json()),
                stderr="",
                returncode=0,
            ),
        ])
        result = verify_phase_cross_references(
            phase=phase,
            workspace=workspace,
            completed_phases=[],
            claude_client=client,
        )
        assert result.passed is True
        assert result.issues == []
        assert len(client.received) == 1

    def test_failing_verification(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        phase = PHASE_MAP["PH-001-feature-specification"]
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout=_wrap_in_fence(_failing_json(
                    category="coverage",
                    description="RI-005 not covered",
                    elements=["RI-005"],
                )),
                stderr="",
                returncode=0,
            ),
        ])
        result = verify_phase_cross_references(
            phase=phase,
            workspace=workspace,
            completed_phases=["PH-000-requirements-inventory"],
            claude_client=client,
        )
        assert result.passed is False
        assert len(result.issues) == 1
        assert "RI-005" in result.issues[0]

    def test_creates_log_directory(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        phase = PHASE_MAP["PH-000-requirements-inventory"]
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout=_wrap_in_fence(_passing_json()),
                stderr="",
                returncode=0,
            ),
        ])
        verify_phase_cross_references(
            phase=phase,
            workspace=workspace,
            completed_phases=[],
            claude_client=client,
        )
        log_dir = workspace / CROSS_REF_LOG_DIR / phase.phase_id
        assert log_dir.exists()

    def test_prompt_contains_phase_info(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        phase = PHASE_MAP["PH-003-solution-design"]
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout=_wrap_in_fence(_passing_json()),
                stderr="",
                returncode=0,
            ),
        ])
        verify_phase_cross_references(
            phase=phase,
            workspace=workspace,
            completed_phases=[
                "PH-000-requirements-inventory",
                "PH-001-feature-specification",
            ],
            claude_client=client,
        )
        call = client.received[0]
        assert "Phase 2" in call.prompt
        assert "Solution Design" in call.prompt
        assert "solution-design.yaml" in call.prompt

    def test_raises_on_empty_response(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        phase = PHASE_MAP["PH-000-requirements-inventory"]
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(stdout="", stderr="", returncode=0),
        ])
        with pytest.raises(CrossReferenceError, match="empty response"):
            verify_phase_cross_references(
                phase=phase,
                workspace=workspace,
                completed_phases=[],
                claude_client=client,
            )

    def test_raises_on_unparseable_response(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        phase = PHASE_MAP["PH-000-requirements-inventory"]
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout="Just some reasoning, no JSON.",
                stderr="",
                returncode=0,
            ),
        ])
        with pytest.raises(CrossReferenceError, match="No JSON block"):
            verify_phase_cross_references(
                phase=phase,
                workspace=workspace,
                completed_phases=[],
                claude_client=client,
            )

    def test_raises_on_claude_invocation_failure(
        self, tmp_path: Path,
    ) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        phase = PHASE_MAP["PH-000-requirements-inventory"]
        client = FakeClaudeClient(scripted=[])
        with pytest.raises(CrossReferenceError, match="invocation failed"):
            verify_phase_cross_references(
                phase=phase,
                workspace=workspace,
                completed_phases=[],
                claude_client=client,
            )

    def test_model_passed_to_claude_call(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        phase = PHASE_MAP["PH-000-requirements-inventory"]
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout=_wrap_in_fence(_passing_json()),
                stderr="",
                returncode=0,
            ),
        ])
        verify_phase_cross_references(
            phase=phase,
            workspace=workspace,
            completed_phases=[],
            model="claude-sonnet-4-6",
            claude_client=client,
        )
        assert client.received[0].model == "claude-sonnet-4-6"

    def test_worktree_dir_set_on_call(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        phase = PHASE_MAP["PH-000-requirements-inventory"]
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout=_wrap_in_fence(_passing_json()),
                stderr="",
                returncode=0,
            ),
        ])
        verify_phase_cross_references(
            phase=phase,
            workspace=workspace,
            completed_phases=[],
            claude_client=client,
        )
        assert client.received[0].worktree_dir == workspace

    def test_system_prompt_sent_to_claude(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        phase = PHASE_MAP["PH-000-requirements-inventory"]
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout=_wrap_in_fence(_passing_json()),
                stderr="",
                returncode=0,
            ),
        ])
        verify_phase_cross_references(
            phase=phase,
            workspace=workspace,
            completed_phases=[],
            claude_client=client,
        )
        sent_prompt = client.received[0].prompt
        assert "cross-reference verification agent" in sent_prompt
        assert '"verdict"' in sent_prompt
        assert '"coverage_percentages"' in sent_prompt


# ---------------------------------------------------------------------------
# Tests: verify_end_to_end (with FakeClaudeClient)
# ---------------------------------------------------------------------------

class TestVerifyEndToEnd:

    def test_passing_end_to_end(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout=_wrap_in_fence(_passing_json()),
                stderr="",
                returncode=0,
            ),
        ])
        result = verify_end_to_end(
            workspace=workspace,
            claude_client=client,
        )
        assert result.passed is True

    def test_failing_end_to_end(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout=_wrap_in_fence(_failing_json(
                    category="traceability",
                    description="RI-012 chain broken at Phase 3",
                    elements=["RI-012", "FT-004"],
                )),
                stderr="",
                returncode=0,
            ),
        ])
        result = verify_end_to_end(
            workspace=workspace,
            claude_client=client,
        )
        assert result.passed is False
        assert "RI-012" in result.traceability_gaps

    def test_prompt_mentions_all_phases(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout=_wrap_in_fence(_passing_json()),
                stderr="",
                returncode=0,
            ),
        ])
        verify_end_to_end(workspace=workspace, claude_client=client)
        prompt = client.received[0].prompt
        assert "Phase 0" in prompt
        assert "Phase 6" in prompt
        assert "requirements-inventory.yaml" in prompt
        assert "verification-report.yaml" in prompt

    def test_creates_end_to_end_log_dir(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout=_wrap_in_fence(_passing_json()),
                stderr="",
                returncode=0,
            ),
        ])
        verify_end_to_end(workspace=workspace, claude_client=client)
        log_dir = workspace / CROSS_REF_LOG_DIR / "end-to-end"
        assert log_dir.exists()

    def test_raises_on_empty_response(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(stdout="   ", stderr="", returncode=0),
        ])
        with pytest.raises(CrossReferenceError, match="empty response"):
            verify_end_to_end(workspace=workspace, claude_client=client)

    def test_system_prompt_sent_to_claude(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        client = FakeClaudeClient(scripted=[
            ClaudeResponse(
                stdout=_wrap_in_fence(_passing_json()),
                stderr="",
                returncode=0,
            ),
        ])
        verify_end_to_end(workspace=workspace, claude_client=client)
        sent_prompt = client.received[0].prompt
        assert "cross-reference verification agent" in sent_prompt
        assert '"coverage_percentages"' in sent_prompt


# ---------------------------------------------------------------------------
# Tests: constants and system prompt
# ---------------------------------------------------------------------------

class TestConstants:

    def test_system_prompt_not_empty(self) -> None:
        assert len(CROSS_REF_SYSTEM_PROMPT) > 100

    def test_system_prompt_mentions_json(self) -> None:
        assert "JSON" in CROSS_REF_SYSTEM_PROMPT

    def test_system_prompt_includes_coverage_percentages_schema(self) -> None:
        assert "coverage_percentages" in CROSS_REF_SYSTEM_PROMPT

    def test_system_prompt_mentions_four_categories(self) -> None:
        for cat in _CATEGORY_NAMES:
            assert cat in CROSS_REF_SYSTEM_PROMPT

    def test_end_to_end_template_mentions_seven_phases(self) -> None:
        assert "Phase 0" in END_TO_END_PROMPT_TEMPLATE
        assert "Phase 1" in END_TO_END_PROMPT_TEMPLATE
        assert "Phase 2" in END_TO_END_PROMPT_TEMPLATE
        assert "Phase 3" in END_TO_END_PROMPT_TEMPLATE
        assert "Phase 4" in END_TO_END_PROMPT_TEMPLATE
        assert "Phase 5" in END_TO_END_PROMPT_TEMPLATE
        assert "Phase 6" in END_TO_END_PROMPT_TEMPLATE

    def test_category_names_tuple(self) -> None:
        assert _CATEGORY_NAMES == (
            "traceability", "coverage", "consistency", "integration",
        )


# ---------------------------------------------------------------------------
# Tests: CrossReferenceError
# ---------------------------------------------------------------------------

class TestCrossReferenceError:

    def test_stores_phase_id_and_reason(self) -> None:
        err = CrossReferenceError("PH-001-test", "something broke")
        assert err.phase_id == "PH-001-test"
        assert err.reason == "something broke"
        assert "PH-001-test" in str(err)
        assert "something broke" in str(err)

    def test_is_exception(self) -> None:
        assert issubclass(CrossReferenceError, Exception)


# ---------------------------------------------------------------------------
# Tests: round-trip serialisation of parsed results
# ---------------------------------------------------------------------------

class TestResultSerialisation:

    def test_parsed_result_round_trips(self) -> None:
        text = _wrap_in_fence(_failing_json(
            category="consistency",
            description="CTR-002 references non-existent INT-099",
            elements=["CTR-002", "INT-099"],
        ))
        result = _parse_cross_ref_result(text)
        d = result.to_dict()
        restored = CrossRefResult.from_dict(d)
        assert restored.passed == result.passed
        assert restored.issues == result.issues
        assert restored.traceability_gaps == result.traceability_gaps
        assert restored.orphaned_elements == result.orphaned_elements
        assert restored.coverage_summary == result.coverage_summary

    def test_passing_result_round_trips(self) -> None:
        text = _wrap_in_fence(_passing_json())
        result = _parse_cross_ref_result(text)
        d = result.to_dict()
        restored = CrossRefResult.from_dict(d)
        assert restored.passed is True
        assert restored.issues == []
