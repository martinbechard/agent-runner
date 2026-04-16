"""Tests for the new PH-002 Architecture phase and renumbering."""
from methodology_runner.phases import (
    PHASES,
    PHASE_MAP,
    get_phase,
)


EXPECTED_ORDER = [
    ("PH-000-requirements-inventory", 0),
    ("PH-001-feature-specification", 1),
    ("PH-002-architecture", 2),
    ("PH-003-solution-design", 3),
    ("PH-004-interface-contracts", 4),
    ("PH-005-intelligent-simulations", 5),
    ("PH-006-incremental-implementation", 6),
    ("PH-007-verification-sweep", 7),
]


def test_eight_phases_in_order():
    ids = [p.phase_id for p in PHASES]
    assert ids == [pid for pid, _ in EXPECTED_ORDER]


def test_phase_numbers_match_order():
    for phase, (expected_id, expected_num) in zip(PHASES, EXPECTED_ORDER):
        assert phase.phase_id == expected_id
        assert phase.phase_number == expected_num


def test_architecture_phase_outputs_stack_manifest():
    arch = get_phase("PH-002-architecture")
    assert "stack-manifest" in arch.output_artifact_path
    assert arch.output_format == "yaml"
    assert arch.predecessors == ["PH-001-feature-specification"]


def test_solution_design_predecessor_is_architecture():
    sd = get_phase("PH-003-solution-design")
    assert "PH-002-architecture" in sd.predecessors


def test_incremental_implementation_predecessors_include_simulations():
    impl = get_phase("PH-006-incremental-implementation")
    assert "PH-005-intelligent-simulations" in impl.predecessors
    assert "PH-004-interface-contracts" in impl.predecessors


def test_verification_sweep_is_final_phase():
    ids = [p.phase_id for p in PHASES]
    assert ids[-1] == "PH-007-verification-sweep"


def test_phase_map_round_trip():
    for phase in PHASES:
        assert PHASE_MAP[phase.phase_id] is phase
