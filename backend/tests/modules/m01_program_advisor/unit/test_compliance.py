"""
Pure-Python compliance engine tests.
No DB, no async — all rules and DAG cycle detection exercised directly.
"""
from __future__ import annotations

import uuid

from app.modules.m01_program_advisor.compliance import (
    CourseNode,
    ProgramNode,
    detect_prerequisite_cycles,
    run_compliance_check,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _btech_program(total_credits: int = 160, outcome_count: int = 12) -> ProgramNode:
    return ProgramNode(
        degree_type="BTech",
        duration_years=4,
        total_credits=total_credits,
        outcome_count=outcome_count,
    )


def _course(
    code: str,
    credits: int = 4,
    semester: int = 1,
    is_elective: bool = False,
) -> CourseNode:
    return CourseNode(
        id=uuid.uuid4(),
        code=code,
        credits=credits,
        semester=semester,
        is_elective=is_elective,
        prerequisite_course_ids=[],
    )


def _spread_courses(n_sems: int = 8, code_offset: int = 0) -> list[CourseNode]:
    """4 courses × 4 credits per semester; 1 elective per 4 (25 %).
    Satisfies: UGC-COURSE-001 (4 ∈ [1,6]), UGC-SEM-001 (16 ≥ 14),
    UGC-SEM-002 (16 ≤ 30), UGC-ELEC-001 (25 % ≥ 20 % for BTech).
    code_offset prevents duplicate codes when combined with extra courses."""
    result = []
    for sem in range(1, n_sems + 1):
        for j in range(4):
            idx = (sem - 1) * 4 + j + 1 + code_offset
            result.append(CourseNode(
                id=uuid.uuid4(),
                code=f"CS{idx:03d}",
                credits=4,
                semester=sem,
                is_elective=(j == 3),
                prerequisite_course_ids=[],
            ))
    return result


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_happy_path_btech():
    program = _btech_program(total_credits=160, outcome_count=12)
    courses = _spread_courses(8)
    result = run_compliance_check(program, courses)
    assert result.passed is True
    assert [v for v in result.violations if v.severity == "ERROR"] == []


# ---------------------------------------------------------------------------
# Total credits rules
# ---------------------------------------------------------------------------

def test_total_credits_below_min():
    program = _btech_program(total_credits=150)
    result = run_compliance_check(program, _spread_courses(8))
    rule_ids = [v.rule_id for v in result.violations]
    assert "UGC-CRED-001" in rule_ids
    assert result.passed is False


def test_total_credits_above_max_is_warning_only():
    # Program declares 210 credits (> 200 max) → UGC-CRED-002 WARNING.
    # Courses themselves are all valid so no ERROR fires.
    program = _btech_program(total_credits=210)
    courses = _spread_courses(8)
    result = run_compliance_check(program, courses)
    rule_ids = [v.rule_id for v in result.violations]
    assert "UGC-CRED-002" in rule_ids
    severities = [v.severity for v in result.violations if v.rule_id == "UGC-CRED-002"]
    assert severities == ["WARNING"]
    assert result.passed is True


# ---------------------------------------------------------------------------
# Semester credit rules
# ---------------------------------------------------------------------------

def test_sem_credits_below_min():
    # Semester 1 has only 2 × 4 = 8 credits, below the BTech minimum of 14.
    # Semesters 2-8 use shifted spread courses (compliant, 16 each).
    program = _btech_program()
    bad_sem = [_course("CS901", credits=4, semester=1),
               _course("CS902", credits=4, semester=1)]
    good_sems = _spread_courses(n_sems=7, code_offset=0)
    for c in good_sems:
        c.semester += 1  # push to semesters 2-8
    courses = bad_sem + good_sems
    result = run_compliance_check(program, courses)
    rule_ids = [v.rule_id for v in result.violations]
    assert "UGC-SEM-001" in rule_ids
    assert result.passed is False


def test_sem_credits_above_max():
    # Semester 1 has 8 × 4 = 32 credits, above the typical per-semester load of 30.
    # Phase 4.2 policy: a program is validated against its TOTAL configured
    # credits, not a hard per-semester cap. An above-typical semester is an
    # advisory WARNING (a rebalancing recommendation) and must NOT block approval.
    program = _btech_program()
    heavy_sem = [
        CourseNode(id=uuid.uuid4(), code=f"CS9{j:02d}", credits=4,
                   semester=1, is_elective=(j == 0), prerequisite_course_ids=[])
        for j in range(8)  # 8 × 4 = 32 > 30
    ]
    good_sems = _spread_courses(n_sems=7, code_offset=0)
    for c in good_sems:
        c.semester += 1
    courses = heavy_sem + good_sems
    result = run_compliance_check(program, courses)
    sem002 = [v for v in result.violations if v.rule_id == "UGC-SEM-002"]
    assert sem002, "expected an advisory UGC-SEM-002 recommendation"
    assert all(v.severity == "WARNING" for v in sem002)
    # A heavy semester alone no longer fails the program.
    assert result.passed is True


def test_sem_balance_warning_only():
    # Semester 1: 6 × 5 = 30 credits (at maximum — no SEM-002 error).
    # Semester 2: 2 × 4 + 1 × 6 = 14 credits (at minimum — no SEM-001 error).
    # Spread = 30 - 14 = 16 > 15 → UGC-SEM-003 WARNING only.
    program = _btech_program()
    sem1 = [
        CourseNode(id=uuid.uuid4(), code=f"S1C{j}", credits=5,
                   semester=1, is_elective=(j < 2), prerequisite_course_ids=[])
        for j in range(6)
    ]
    sem2 = [
        CourseNode(id=uuid.uuid4(), code="S2C0", credits=4, semester=2, is_elective=True, prerequisite_course_ids=[]),
        CourseNode(id=uuid.uuid4(), code="S2C1", credits=4, semester=2, is_elective=False, prerequisite_course_ids=[]),
        CourseNode(id=uuid.uuid4(), code="S2C2", credits=6, semester=2, is_elective=False, prerequisite_course_ids=[]),
    ]
    rest = _spread_courses(n_sems=6, code_offset=0)
    for c in rest:
        c.semester += 2  # push to semesters 3-8
    courses = sem1 + sem2 + rest
    result = run_compliance_check(program, courses)
    rule_ids = [v.rule_id for v in result.violations]
    assert "UGC-SEM-003" in rule_ids
    severities = [v.severity for v in result.violations if v.rule_id == "UGC-SEM-003"]
    assert severities == ["WARNING"]
    assert result.passed is True


# ---------------------------------------------------------------------------
# Elective ratio
# ---------------------------------------------------------------------------

def test_elective_ratio_informational_only():
    # 8 courses across 2 semesters, none elective → 0 % < 20 % minimum.
    # Semester credits: 4 × 4 = 16 per sem (valid). Each course 4 ∈ [1,6].
    # Elective selection isn't implemented yet, so this is advisory (INFO), not a WARNING.
    program = _btech_program()
    courses = [
        CourseNode(id=uuid.uuid4(), code=f"CS{i:03d}", credits=4,
                   semester=(1 if i <= 4 else 2), is_elective=False,
                   prerequisite_course_ids=[])
        for i in range(1, 9)
    ]
    result = run_compliance_check(program, courses)
    rule_ids = [v.rule_id for v in result.violations]
    assert "UGC-ELEC-001" in rule_ids
    severities = [v.severity for v in result.violations if v.rule_id == "UGC-ELEC-001"]
    assert severities == ["INFO"]
    assert result.passed is True


# ---------------------------------------------------------------------------
# Course credit range
# ---------------------------------------------------------------------------

def test_course_credit_out_of_range_zero():
    program = _btech_program()
    bad = _course("CS000", credits=0)
    courses = [bad, *_spread_courses(8, code_offset=1)]
    result = run_compliance_check(program, courses)
    rule_ids = [v.rule_id for v in result.violations]
    assert "UGC-COURSE-001" in rule_ids
    assert result.passed is False


def test_course_credit_out_of_range_too_high():
    program = _btech_program()
    bad = _course("CS999", credits=8)
    courses = [bad, *_spread_courses(8, code_offset=1)]
    result = run_compliance_check(program, courses)
    rule_ids = [v.rule_id for v in result.violations]
    assert "UGC-COURSE-001" in rule_ids
    assert result.passed is False


# ---------------------------------------------------------------------------
# Program outcomes
# ---------------------------------------------------------------------------

def test_program_outcomes_below_min():
    program = _btech_program(outcome_count=2)
    result = run_compliance_check(program, _spread_courses())
    rule_ids = [v.rule_id for v in result.violations]
    assert "UGC-PO-001" in rule_ids
    assert result.passed is False


# ---------------------------------------------------------------------------
# Duplicate codes
# ---------------------------------------------------------------------------

def test_duplicate_course_codes():
    program = _btech_program()
    # Two explicit courses with the same code, then padded valid courses.
    dup_sem1 = _course("CSDUP", credits=4, semester=1)
    dup_sem2 = _course("CSDUP", credits=4, semester=2)
    rest = _spread_courses(8, code_offset=100)  # codes CS{101..} — no overlap
    courses = [dup_sem1, dup_sem2, *rest]
    result = run_compliance_check(program, courses)
    rule_ids = [v.rule_id for v in result.violations]
    assert "UGC-CODE-001" in rule_ids
    assert result.passed is False


# ---------------------------------------------------------------------------
# DAG cycle detection
# ---------------------------------------------------------------------------

def test_dag_no_cycle():
    a = _course("A", semester=1)
    b = CourseNode(id=uuid.uuid4(), code="B", credits=4, semester=2,
                   is_elective=False, prerequisite_course_ids=[a.id])
    c = CourseNode(id=uuid.uuid4(), code="C", credits=4, semester=3,
                   is_elective=False, prerequisite_course_ids=[b.id])
    violations = detect_prerequisite_cycles([a, b, c])
    assert violations == []


def test_dag_simple_cycle():
    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    a = CourseNode(id=a_id, code="A", credits=4, semester=1,
                   is_elective=False, prerequisite_course_ids=[b_id])
    b = CourseNode(id=b_id, code="B", credits=4, semester=2,
                   is_elective=False, prerequisite_course_ids=[a_id])
    violations = detect_prerequisite_cycles([a, b])
    assert any(v.rule_id == "UGC-DAG-001" for v in violations)


def test_dag_three_node_cycle():
    a_id, b_id, c_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    a = CourseNode(id=a_id, code="A", credits=4, semester=1,
                   is_elective=False, prerequisite_course_ids=[c_id])
    b = CourseNode(id=b_id, code="B", credits=4, semester=2,
                   is_elective=False, prerequisite_course_ids=[a_id])
    c = CourseNode(id=c_id, code="C", credits=4, semester=3,
                   is_elective=False, prerequisite_course_ids=[b_id])
    violations = detect_prerequisite_cycles([a, b, c])
    assert any(v.rule_id == "UGC-DAG-001" for v in violations)


# ---------------------------------------------------------------------------
# passed flag semantics
# ---------------------------------------------------------------------------

def test_passed_false_on_any_error():
    # UGC-PO-001 (ERROR) fires; result must be passed=False.
    program = _btech_program(outcome_count=2)
    result = run_compliance_check(program, _spread_courses(8))
    assert result.passed is False
    assert any(v.severity == "ERROR" for v in result.violations)


# ---------------------------------------------------------------------------
# Threshold routing
# ---------------------------------------------------------------------------

def test_pg_mba_thresholds():
    # MBA maps to PG2: min_total_credits=60. Declaring 60 must not trigger
    # UGC-CRED-001.
    program = ProgramNode(degree_type="MBA", duration_years=2,
                          total_credits=60, outcome_count=6)
    courses = _spread_courses(4)
    result = run_compliance_check(program, courses)
    cred_errors = [v for v in result.violations if v.rule_id == "UGC-CRED-001"]
    assert cred_errors == [], "60 credits should satisfy MBA PG2 minimum of 60"
