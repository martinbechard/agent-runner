"""Tests for PH-005 component simulation validation."""
from __future__ import annotations

from pathlib import Path

from methodology_runner.phase_5_validation import build_report


def _write(path: Path, content: str) -> Path:
    """Write a temporary test fixture file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_common_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create architecture, contract, and feature inputs shared by tests."""
    architecture = _write(
        tmp_path / "docs" / "architecture" / "architecture-design.yaml",
        """components:
  - id: "CMP-001"
    name: "Checkout service"
    role: "runtime"
    technology: "Python"
    runtime: "Python 3"
    frameworks: []
    persistence: "none"
    expected_expertise: ["Python application design"]
    features_served: ["FT-001"]
    simulation_target: false
    simulation_boundary: "none"
  - id: "CMP-002"
    name: "Clock provider"
    role: "runtime"
    technology: "Python"
    runtime: "Python 3"
    frameworks: []
    persistence: "none"
    expected_expertise: ["Python time provider interfaces"]
    features_served: ["FT-001"]
    simulation_target: true
    simulation_boundary: "dependency-injection"
integration_points:
  - id: "IP-001"
    between: ["CMP-001", "CMP-002"]
    protocol: "dependency-injection"
    contract_source: "FT-001"
rationale: "The checkout service consumes time through a provider boundary."
""",
    )
    contracts = _write(
        tmp_path / "docs" / "design" / "interface-contracts.yaml",
        """contracts:
  - id: "CTR-001"
    name: "Clock provider contract"
    interaction_ref: "IP-001"
    source_component: "CMP-001"
    target_component: "CMP-002"
    operations:
      - name: "current_time"
        description: "Return the current local date and time."
        request_schema:
          fields:
            - name: "timezone"
              type: "string"
              required: false
              constraints: "Optional local timezone label."
        response_schema:
          fields:
            - name: "value"
              type: "string"
              required: true
              constraints: "Date-and-time-bearing value."
        error_types:
          - name: "clock_unavailable"
            condition: "The provider cannot return a value."
            http_status: 503
    behavioral_specs:
      - precondition: "A consumer has a clock provider."
        postcondition: "The provider returns a date-and-time-bearing value."
        invariant: "The provider hides clock internals."
""",
    )
    feature_spec = _write(
        tmp_path / "docs" / "features" / "feature-specification.yaml",
        """features:
  - id: "FT-001"
    name: "Checkout timestamps"
    description: "Checkout can ask for the current time."
    source_inventory_refs: ["RI-001"]
    acceptance_criteria:
      - id: "AC-001"
        description: "A date-and-time value is available."
    dependencies: []
""",
    )
    return architecture, contracts, feature_spec


def test_phase_5_validation_accepts_compile_checked_component_simulation(tmp_path: Path) -> None:
    architecture, contracts, feature_spec = _write_common_inputs(tmp_path)
    _write(
        tmp_path / "simulations" / "interfaces" / "clock_provider.py",
        '''"""Language interface for clock provider simulations."""
from typing import Protocol


class ClockProvider(Protocol):
    """Provides the local date and time to consumers."""

    def current_time(self) -> str:
        """Return a date-and-time-bearing value."""
        ...
''',
    )
    _write(
        tmp_path / "simulations" / "fakes" / "fake_clock_provider.py",
        '''"""Compile-checked fake implementation of the clock provider."""
from simulations.interfaces.clock_provider import ClockProvider


class FakeClockProvider:
    """In-memory simulation that returns a configured date-time value."""

    def __init__(self, value: str = "2026-04-24 09:15:01") -> None:
        self._value = value

    def current_time(self) -> str:
        """Return the configured date-time value."""
        return self._value


def build_fake_clock_provider() -> ClockProvider:
    """Build the fake as the declared interface type."""
    return FakeClockProvider()
''',
    )
    simulations = _write(
        tmp_path / "docs" / "simulations" / "simulation-definitions.yaml",
        """simulations:
  - id: "SIM-001"
    component_ref: "CMP-002"
    simulated_component: "Clock provider"
    purpose: "Lets checkout integration slices run without a real clock provider."
    interface:
      language: "python"
      kind: "Protocol"
      path: "simulations/interfaces/clock_provider.py"
      symbol: "ClockProvider"
      contract_refs: ["CTR-001"]
    implementation:
      path: "simulations/fakes/fake_clock_provider.py"
      symbol: "FakeClockProvider"
      implements: "ClockProvider"
      behavior: "Returns a configurable in-memory local date-time value."
    usage:
      mode: "fake"
      instructions: "Import build_fake_clock_provider and inject the returned ClockProvider into checkout integration slices."
      integration_reference: "simulations.fakes.fake_clock_provider.build_fake_clock_provider"
      configuration:
        value: "Override the constructor value to control the returned date-time."
      startup: []
      retirement: "Replace FakeClockProvider with the real CMP-002 implementation while keeping the ClockProvider interface."
      documentation:
        location: "inline_comments"
        path: "simulations/fakes/fake_clock_provider.py"
    artifacts:
      - path: "simulations/interfaces/clock_provider.py"
        role: "interface"
        description: "Protocol consumed by checkout code and implemented by the fake."
        phase_6_usage: "Use this as the dependency-injection boundary for tests and real implementation."
      - path: "simulations/fakes/fake_clock_provider.py"
        role: "implementation"
        description: "Configurable fake clock provider with inline usage docstrings."
        phase_6_usage: "Inject this fake until CMP-002 is replaced by the real provider."
    integration_scenarios:
      - id: "SCN-001"
        name: "consumer reads current time"
        exposed_functionality: "current_time returns a date-time-bearing string"
        inputs: {}
        outputs:
          value: "2026-04-24 09:15:01"
        state_model: "configurable"
        error_modes: []
    compile_commands:
      - >-
        python3 -m py_compile simulations/interfaces/clock_provider.py
        simulations/fakes/fake_clock_provider.py &&
        python3 -c 'from simulations.fakes.fake_clock_provider import
        build_fake_clock_provider; assert build_fake_clock_provider().current_time()'
    validation_rules:
      - rule: "The fake must compile and expose the ClockProvider current_time behavior."
        severity: "blocking"
""",
    )

    report = build_report(architecture, contracts, feature_spec, simulations)

    assert report["overall_status"] == "pass"
    assert report["failed_checks"] == []


def test_phase_5_validation_rejects_legacy_contract_scenario_shape(tmp_path: Path) -> None:
    architecture, contracts, feature_spec = _write_common_inputs(tmp_path)
    simulations = _write(
        tmp_path / "docs" / "simulations" / "simulation-definitions.yaml",
        """simulations:
  - id: "SIM-001"
    contract_ref: "CTR-001"
    description: "Legacy scenario-only simulation."
    scenario_bank:
      - name: "happy path"
        type: "happy_path"
        input: {}
        expected_output: {}
        assertions:
          - field: "ok"
            operator: "equals"
            value: true
    llm_adjuster:
      temperature: 0.0
      system_prompt_addendum: ""
      forbidden_patterns: []
    validation_rules:
      - rule: "legacy"
        severity: "blocking"
""",
    )

    report = build_report(architecture, contracts, feature_spec, simulations)

    assert report["overall_status"] == "fail"
    assert "legacy_contract_scenario_shape" in report["failed_checks"]
    assert "simulation_required_fields" in report["failed_checks"]
    assert "component_target_coverage" in report["failed_checks"]


def test_phase_5_validation_rejects_missing_usage_artifact_contract(tmp_path: Path) -> None:
    architecture, contracts, feature_spec = _write_common_inputs(tmp_path)
    _write(
        tmp_path / "simulations" / "interfaces" / "clock_provider.py",
        '''"""Clock provider interface."""
from typing import Protocol


class ClockProvider(Protocol):
    """Provides current time."""

    def current_time(self) -> str:
        """Return current time."""
        ...
''',
    )
    _write(
        tmp_path / "simulations" / "fakes" / "fake_clock_provider.py",
        '''"""Fake clock provider."""
from simulations.interfaces.clock_provider import ClockProvider


class FakeClockProvider:
    """Fake clock implementation."""

    def current_time(self) -> str:
        """Return a fixed value."""
        return "2026-04-24 09:15:01"


def build_fake_clock_provider() -> ClockProvider:
    """Build the fake as the interface type."""
    return FakeClockProvider()
''',
    )
    simulations = _write(
        tmp_path / "docs" / "simulations" / "simulation-definitions.yaml",
        """simulations:
  - id: "SIM-001"
    component_ref: "CMP-002"
    simulated_component: "Clock provider"
    purpose: "Lets checkout integration slices run without a real clock provider."
    interface:
      language: "python"
      kind: "Protocol"
      path: "simulations/interfaces/clock_provider.py"
      symbol: "ClockProvider"
      contract_refs: ["CTR-001"]
    implementation:
      path: "simulations/fakes/fake_clock_provider.py"
      symbol: "FakeClockProvider"
      implements: "ClockProvider"
      behavior: "Returns a fixed local date-time value."
    integration_scenarios:
      - id: "SCN-001"
        name: "consumer reads current time"
        exposed_functionality: "current_time returns a date-time-bearing string"
        inputs: {}
        outputs:
          value: "2026-04-24 09:15:01"
        state_model: "none"
        error_modes: []
    compile_commands:
      - "python3 -m py_compile simulations/interfaces/clock_provider.py simulations/fakes/fake_clock_provider.py"
    validation_rules:
      - rule: "The fake must compile."
        severity: "blocking"
""",
    )

    report = build_report(architecture, contracts, feature_spec, simulations)

    assert report["overall_status"] == "fail"
    assert "simulation_required_fields" in report["failed_checks"]
    assert "simulation_usage_documentation" in report["failed_checks"]
    assert "simulation_artifact_list" in report["failed_checks"]
