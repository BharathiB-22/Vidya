"""
Pure-function compliance check tests for M02.
No DB access — all inputs are built in-memory.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.modules.m02_syllabus.models import BloomLevel, MappingStrength
from app.modules.m02_syllabus.service import _run_compliance_check


# ---------------------------------------------------------------------------
# Minimal fake ORM object factories (no DB required)
# ---------------------------------------------------------------------------

def _co(bloom_level: BloomLevel = BloomLevel.APPLY):
    return SimpleNamespace(id=uuid.uuid4(), bloom_level=bloom_level)


def _unit(number: int = 1, topics: int = 12):
    """A unit as compliance now sees it.

    It carries its NUMBER and its TOPICS because compliance is now also the
    completeness gate: a theory syllabus is written and saved one unit at a time, so a
    unit may exist and still be half-written, and approval has to be able to tell.
    Twelve topics is a real unit; the floor is MIN_TOPICS_PER_UNIT.
    """
    return SimpleNamespace(
        id=uuid.uuid4(),
        unit_number=number,
        topics=[{"title": f"Topic {i}"} for i in range(topics)],
    )


def _mapping(co_id: uuid.UUID):
    return SimpleNamespace(co_id=co_id)


def _cos(n: int, levels: list[BloomLevel] | None = None) -> list:
    if levels is None:
        levels = [
            BloomLevel.REMEMBER, BloomLevel.APPLY,
            BloomLevel.EVALUATE, BloomLevel.CREATE,
        ]
    cos = []
    for i in range(n):
        cos.append(_co(levels[i % len(levels)]))
    return cos


def _units(n: int) -> list:
    return [_unit(number=i + 1) for i in range(n)]


# ===========================================================================
# Passing cases
# ===========================================================================

def test_compliance_passes_with_minimum_data():
    cos   = _cos(4)
    units = _units(4)
    mappings = [_mapping(co.id) for co in cos]
    result = _run_compliance_check(cos, units, mappings)
    assert result.passed is True
    assert all(v.severity != "ERROR" for v in result.violations)


def test_compliance_passes_with_no_violations():
    cos   = _cos(6)
    units = _units(5)
    mappings = [_mapping(co.id) for co in cos]
    result = _run_compliance_check(cos, units, mappings)
    assert result.passed is True
    assert result.violations == []


def test_compliance_passes_with_only_warnings():
    # 4+ COs, 4+ units, but 0% CO-PO coverage → WARNING only
    cos   = _cos(4)
    units = _units(4)
    result = _run_compliance_check(cos, units, mappings=[])
    assert result.passed is True
    codes = {v.code for v in result.violations}
    assert "COPO_COVERAGE_LOW" in codes
    assert "CO_MIN_NOT_MET" not in codes
    assert "GENERATION_INCOMPLETE" not in codes


# ===========================================================================
# Error cases (blocking)
# ===========================================================================

def test_compliance_fails_too_few_cos():
    cos   = _cos(3)
    units = _units(4)
    result = _run_compliance_check(cos, units, mappings=[])
    assert result.passed is False
    codes = {v.code for v in result.violations}
    assert "CO_MIN_NOT_MET" in codes
    error_violations = [v for v in result.violations if v.severity == "ERROR"]
    assert any(v.code == "CO_MIN_NOT_MET" for v in error_violations)


def test_compliance_fails_zero_cos():
    result = _run_compliance_check([], _units(4), mappings=[])
    assert result.passed is False
    assert any(v.code == "CO_MIN_NOT_MET" for v in result.violations)


def test_compliance_fails_too_few_units():
    cos   = _cos(4)
    units = _units(3)
    result = _run_compliance_check(cos, units, mappings=[])
    assert result.passed is False
    codes = {v.code for v in result.violations}
    assert "GENERATION_INCOMPLETE" in codes


def test_compliance_fails_both_co_and_unit_min():
    result = _run_compliance_check(_cos(2), _units(2), mappings=[])
    assert result.passed is False
    codes = {v.code for v in result.violations}
    assert "CO_MIN_NOT_MET" in codes
    assert "GENERATION_INCOMPLETE" in codes


# ===========================================================================
# Warning cases (non-blocking)
# ===========================================================================

def test_compliance_warns_low_copo_coverage():
    # 4 COs, only 1 mapped (25% < 50% threshold)
    cos      = _cos(4)
    units    = _units(4)
    mappings = [_mapping(cos[0].id)]
    result   = _run_compliance_check(cos, units, mappings)
    assert result.passed is True
    codes = {v.code for v in result.violations}
    assert "COPO_COVERAGE_LOW" in codes
    warn = next(v for v in result.violations if v.code == "COPO_COVERAGE_LOW")
    assert warn.severity == "WARNING"


def test_compliance_no_copo_warning_at_50_percent_coverage():
    # 4 COs, exactly 2 mapped (50% == threshold) → no warning
    cos      = _cos(4)
    units    = _units(4)
    mappings = [_mapping(cos[0].id), _mapping(cos[1].id)]
    result   = _run_compliance_check(cos, units, mappings)
    codes = {v.code for v in result.violations}
    assert "COPO_COVERAGE_LOW" not in codes


def test_compliance_warns_low_bloom_diversity():
    # All 4 COs at the same Bloom level
    cos      = [_co(BloomLevel.APPLY) for _ in range(4)]
    units    = _units(4)
    mappings = [_mapping(co.id) for co in cos]
    result   = _run_compliance_check(cos, units, mappings)
    assert result.passed is True
    codes = {v.code for v in result.violations}
    assert "BLOOM_DIVERSITY_LOW" in codes
    warn = next(v for v in result.violations if v.code == "BLOOM_DIVERSITY_LOW")
    assert warn.severity == "WARNING"


def test_compliance_no_bloom_warning_with_diverse_levels():
    cos      = _cos(4)  # uses REMEMBER, APPLY, EVALUATE, CREATE
    units    = _units(4)
    mappings = [_mapping(co.id) for co in cos]
    result   = _run_compliance_check(cos, units, mappings)
    codes = {v.code for v in result.violations}
    assert "BLOOM_DIVERSITY_LOW" not in codes


def test_compliance_violation_objects_have_required_fields():
    result = _run_compliance_check(_cos(1), _units(1), mappings=[])
    assert result.passed is False
    for v in result.violations:
        assert hasattr(v, "code")
        assert hasattr(v, "message")
        assert hasattr(v, "severity")
        assert v.severity in ("ERROR", "WARNING")


def test_compliance_empty_syllabus_fails_both_mins():
    result = _run_compliance_check([], [], mappings=[])
    assert result.passed is False
    codes = {v.code for v in result.violations}
    assert "CO_MIN_NOT_MET" in codes
    assert "GENERATION_INCOMPLETE" in codes
