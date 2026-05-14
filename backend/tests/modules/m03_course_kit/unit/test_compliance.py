"""
Unit tests for _build_compliance — pure function, no DB, no fixtures.

Every test is synchronous; asyncio_mode=auto does not affect sync tests.
"""
from __future__ import annotations

from app.modules.m03_course_kit.service import _build_compliance


def test_passes_when_all_minimums_met_with_plan():
    result = _build_compliance(
        slide_count=8, quizlet_count=2,
        teaching_plan=[{"week": 1}],
        min_slides=8, min_quizlets=2,
    )
    assert result.passed is True
    assert result.violations == []


def test_passes_when_exactly_at_minimums_no_plan_warning():
    result = _build_compliance(
        slide_count=8, quizlet_count=2,
        teaching_plan=[],
        min_slides=8, min_quizlets=2,
    )
    assert result.passed is True  # WARNING does not block
    assert any(v.code == "NO_TEACHING_PLAN" for v in result.violations)


def test_slide_min_not_met_is_error_blocks_publish():
    result = _build_compliance(
        slide_count=5, quizlet_count=2,
        teaching_plan=[{"week": 1}],
        min_slides=8, min_quizlets=2,
    )
    assert result.passed is False
    codes = {v.code for v in result.violations}
    assert "SLIDE_MIN_NOT_MET" in codes
    errors = [v for v in result.violations if v.severity == "ERROR"]
    assert len(errors) >= 1


def test_quizlet_min_not_met_is_error_blocks_publish():
    result = _build_compliance(
        slide_count=8, quizlet_count=0,
        teaching_plan=[{"week": 1}],
        min_slides=8, min_quizlets=2,
    )
    assert result.passed is False
    codes = {v.code for v in result.violations}
    assert "QUIZLET_MIN_NOT_MET" in codes
    errors = [v for v in result.violations if v.severity == "ERROR"]
    assert len(errors) >= 1


def test_no_teaching_plan_is_warning_does_not_block():
    result = _build_compliance(
        slide_count=8, quizlet_count=2,
        teaching_plan=[],
        min_slides=8, min_quizlets=2,
    )
    assert result.passed is True
    warnings = [v for v in result.violations if v.severity == "WARNING"]
    assert any(v.code == "NO_TEACHING_PLAN" for v in warnings)
    errors = [v for v in result.violations if v.severity == "ERROR"]
    assert len(errors) == 0


def test_slide_and_quizlet_min_not_met_both_errors():
    result = _build_compliance(
        slide_count=2, quizlet_count=0,
        teaching_plan=[{"week": 1}],
        min_slides=8, min_quizlets=2,
    )
    assert result.passed is False
    codes = {v.code for v in result.violations}
    assert "SLIDE_MIN_NOT_MET" in codes
    assert "QUIZLET_MIN_NOT_MET" in codes
    errors = [v for v in result.violations if v.severity == "ERROR"]
    assert len(errors) == 2


def test_all_three_violations_accumulate():
    result = _build_compliance(
        slide_count=0, quizlet_count=0,
        teaching_plan=[],
        min_slides=8, min_quizlets=2,
    )
    assert result.passed is False
    codes = {v.code for v in result.violations}
    assert "SLIDE_MIN_NOT_MET" in codes
    assert "QUIZLET_MIN_NOT_MET" in codes
    assert "NO_TEACHING_PLAN" in codes
    assert len(result.violations) == 3


def test_custom_min_values_respected_exact_match():
    result = _build_compliance(
        slide_count=3, quizlet_count=1,
        teaching_plan=[],
        min_slides=3, min_quizlets=1,
    )
    assert result.passed is True
    assert not any(v.severity == "ERROR" for v in result.violations)


def test_exceeding_minimums_no_violations():
    result = _build_compliance(
        slide_count=20, quizlet_count=10,
        teaching_plan=[{"week": 1}, {"week": 2}],
        min_slides=8, min_quizlets=2,
    )
    assert result.passed is True
    assert result.violations == []


def test_one_above_minimum_passes():
    result = _build_compliance(
        slide_count=9, quizlet_count=3,
        teaching_plan=[{"week": 1}],
        min_slides=8, min_quizlets=2,
    )
    assert result.passed is True
    assert result.violations == []
