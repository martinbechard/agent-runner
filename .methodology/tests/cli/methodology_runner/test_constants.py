"""Tests for methodology_runner.constants."""
from methodology_runner import constants


def test_max_skills_per_phase_is_positive_int():
    assert isinstance(constants.MAX_SKILLS_PER_PHASE, int)
    assert constants.MAX_SKILLS_PER_PHASE > 0


def test_artifact_full_content_threshold_is_positive_int():
    assert isinstance(constants.ARTIFACT_FULL_CONTENT_THRESHOLD, int)
    assert constants.ARTIFACT_FULL_CONTENT_THRESHOLD > 0


def test_max_catalog_size_warning_is_positive_int():
    assert isinstance(constants.MAX_CATALOG_SIZE_WARNING, int)
    assert constants.MAX_CATALOG_SIZE_WARNING > 0


def test_skill_loading_mode_is_one_of_two_values():
    assert constants.SKILL_LOADING_MODE in ("skill-tool", "inline")


def test_max_cross_ref_retries_is_non_negative():
    assert isinstance(constants.MAX_CROSS_REF_RETRIES, int)
    assert constants.MAX_CROSS_REF_RETRIES >= 0
