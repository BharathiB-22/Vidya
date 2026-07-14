"""
Pure-Python compliance engine tests.
No DB, no async — all rules and DAG cycle detection exercised directly.
"""
from __future__ import annotations

import uuid

import pytest

from app.modules.m01_program_advisor.compliance import (
    CourseNode,
    ElectiveSlotNode,
    ProgramNode,
    _check_course_credit_range,
    _curriculum_units,
    _get_thresholds,
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
    """4 courses × 4 credits per semester; 1 standalone elective per 4.
    Satisfies: UGC-COURSE-001 (4 ∈ [1,6]), UGC-SEM-001 (16 ≥ 14),
    UGC-SEM-002 (16 ≤ 30).
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
# Elective slots — one basket is ONE curriculum course, at the slot's credits
# ---------------------------------------------------------------------------

def _slot(name: str = "Elective 1", credits: int = 3, semester: int = 1) -> ElectiveSlotNode:
    return ElectiveSlotNode(id=uuid.uuid4(), name=name, credits=credits, semester=semester)


def _option(code: str, slot: ElectiveSlotNode, credits: int | None = None) -> CourseNode:
    return CourseNode(
        id=uuid.uuid4(),
        code=code,
        credits=slot.credits if credits is None else credits,
        semester=slot.semester,
        is_elective=True,
        prerequisite_course_ids=[],
        elective_basket_id=slot.id,
    )


def test_slot_counts_once_not_once_per_option():
    """Semester 3 = OS(4) + CN(4) + Elective 1(3 cr over AI/DM/DL/Cloud/BA).
    The semester is worth 11 credits, not 4+4+15=23."""
    slot = _slot(semester=3)
    courses = [
        _course("OS301", credits=4, semester=3),
        _course("CN301", credits=4, semester=3),
        *(_option(code, slot) for code in ("AI301", "DM301", "DL301", "CLD301", "BA301")),
    ]
    units = _curriculum_units(courses, [slot])

    assert sum(u.credits for u in units) == 11
    assert len(units) == 3
    # Five options collapse into exactly one curriculum entry, named for the slot.
    assert sorted(u.code for u in units) == ["CN301", "Elective 1", "OS301"]


def test_three_independent_papers_in_one_semester_count_nine_credits():
    """Semester 3 holds Elective 1, Elective 2 and Elective 3 — three separate
    curriculum courses. The student takes all three, choosing one alternative
    inside each, so they contribute 3 + 3 + 3 = 9 credits, not 3."""
    e1 = _slot(name="Elective 1", credits=3, semester=3)
    e2 = _slot(name="Elective 2", credits=3, semester=3)
    e3 = _slot(name="Elective 3", credits=3, semester=3)
    courses = [
        _option("AI301", e1), _option("ML301", e1),
        _option("DM301", e2), _option("DS301", e2), _option("BI301", e2),
        _option("BM301", e3), _option("SMM301", e3),
    ]
    units = _curriculum_units(courses, [e1, e2, e3])

    assert len(units) == 3, "three papers are three curriculum courses"
    assert sum(u.credits for u in units) == 9
    assert sorted(u.code for u in units) == ["Elective 1", "Elective 2", "Elective 3"]


def test_semester_credits_include_every_paper():
    """A semester's load is its cores plus EACH elective paper, not one of them."""
    e1 = _slot(name="Elective 1", credits=3, semester=3)
    e2 = _slot(name="Elective 2", credits=3, semester=3)
    e3 = _slot(name="Elective 3", credits=3, semester=3)
    courses = [
        _course("OS301", credits=4, semester=3),
        _course("CN301", credits=4, semester=3),
        _option("AI301", e1), _option("ML301", e1),
        _option("DM301", e2), _option("DS301", e2),
        _option("BM301", e3), _option("SMM301", e3),
    ]
    units = _curriculum_units(courses, [e1, e2, e3])
    assert sum(u.credits for u in units) == 4 + 4 + 3 + 3 + 3 == 17


def test_slot_credits_are_the_slots_own_not_derived_from_options():
    """The slot's weight is a curriculum fact, so it holds even when the
    options disagree with it or when there are no options at all yet."""
    empty = _slot(name="Elective 1", credits=3)
    assert [u.credits for u in _curriculum_units([], [empty])] == [3]

    # A 4-credit option does not drag the 3-credit slot up.
    slot = _slot(name="Elective 2", credits=3)
    units = _curriculum_units([_option("DM301", slot, credits=4)], [slot])
    assert [u.credits for u in units] == [3]


def test_many_options_do_not_overload_a_semester():
    """The old model counted each option, so a basket of 5 blew past the
    30-credit advisory ceiling. One slot must never trigger UGC-SEM-002."""
    program = _btech_program()
    slot = _slot(semester=1, credits=3)
    courses = [
        _course("CS101", credits=4, semester=1),
        _course("CS102", credits=4, semester=1),
        _course("CS103", credits=4, semester=1),
        *(_option(f"EL1{i:02d}", slot) for i in range(8)),   # 8 × 3 = 24 raw credits
    ]
    result = run_compliance_check(program, courses, [slot])
    assert [v for v in result.violations if v.rule_id == "UGC-SEM-002"] == []


def test_option_credits_must_match_slot_credits():
    # 3 cores × 4 cr + a 3 cr slot = 15, clearing the 14-credit semester minimum
    # so the only thing under test here is the option/slot mismatch.
    slot = _slot(credits=3)
    courses = [
        _course("CS101", credits=4), _course("CS102", credits=4), _course("CS103", credits=4),
        _option("AI301", slot), _option("DM301", slot, credits=4),
    ]
    result = run_compliance_check(_btech_program(), courses, [slot])

    elec002 = [v for v in result.violations if v.rule_id == "UGC-ELEC-002"]
    assert len(elec002) == 1
    assert "DM301" in elec002[0].message
    assert elec002[0].severity == "WARNING"
    assert result.passed is True   # advisory, never blocks approval


def test_option_codes_are_still_checked_for_uniqueness():
    """Options are real courses, so integrity rules still see them even though
    the credit rules do not."""
    slot = _slot()
    courses = [_option("AI301", slot), _option("AI301", slot)]
    result = run_compliance_check(_btech_program(), courses, [slot])

    assert "UGC-CODE-001" in [v.rule_id for v in result.violations]
    assert result.passed is False


def test_removed_elective_ratio_rule_never_fires():
    """UGC-ELEC-001 ("Electives are only XX% … placeholders … not implemented")
    was invalid once slots existed. It must not come back."""
    program = _btech_program()
    courses = [
        CourseNode(id=uuid.uuid4(), code=f"CS{i:03d}", credits=4,
                   semester=(1 if i <= 4 else 2), is_elective=False,
                   prerequisite_course_ids=[])
        for i in range(1, 9)
    ]
    result = run_compliance_check(program, courses)
    assert "UGC-ELEC-001" not in [v.rule_id for v in result.violations]
    assert result.passed is True


def test_no_slots_preserves_pre_slot_behaviour():
    """Backward compatibility: a caller that supplies no slots still gets every
    course counted individually, rather than options silently vanishing."""
    orphan_basket_id = uuid.uuid4()
    courses = [
        _course("OS301", credits=4, semester=3),
        CourseNode(id=uuid.uuid4(), code="AI301", credits=3, semester=3,
                   is_elective=True, prerequisite_course_ids=[],
                   elective_basket_id=orphan_basket_id),
    ]
    units = _curriculum_units(courses, [])
    assert sum(u.credits for u in units) == 7
    assert len(units) == 2


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


# ---------------------------------------------------------------------------
# Project / internship credit range — [2, 20], not [6, 20]
# ---------------------------------------------------------------------------

def _typed_course(code: str, credits: int, course_type: str) -> CourseNode:
    return CourseNode(
        id=uuid.uuid4(),
        code=code,
        credits=credits,
        semester=3,
        is_elective=False,
        prerequisite_course_ids=[],
        course_type=course_type,
    )


def _credit_range_violations(course: CourseNode) -> list:
    return _check_course_credit_range([course], _get_thresholds("MCA"))


def test_two_credit_mini_project_is_valid():
    # A Semester 3 mini-project is routinely 2 credits. Flagging it was the bug.
    assert _credit_range_violations(_typed_course("MCA309", 2, "MINI_PROJECT")) == []


def test_two_credit_internship_is_valid():
    assert _credit_range_violations(_typed_course("MCA310", 2, "INTERNSHIP")) == []


def test_twenty_credit_dissertation_is_valid():
    assert _credit_range_violations(_typed_course("MCA401", 20, "MAJOR_PROJECT")) == []


@pytest.mark.parametrize("course_type", ["MINI_PROJECT", "MAJOR_PROJECT"])
def test_one_credit_project_is_still_flagged(course_type):
    # The floor moved to 2, it did not disappear. Both project sizes share the band.
    v = _credit_range_violations(_typed_course("MCA311", 1, course_type))
    assert len(v) == 1 and v[0].rule_id == "UGC-COURSE-002"
    assert "[2, 20]" in v[0].message


@pytest.mark.parametrize("course_type", ["MINI_PROJECT", "MAJOR_PROJECT"])
def test_twentyone_credit_project_is_still_flagged(course_type):
    v = _credit_range_violations(_typed_course("MCA402", 21, course_type))
    assert len(v) == 1 and v[0].rule_id == "UGC-COURSE-002"


def test_legacy_project_type_is_not_a_project_anymore():
    """The old single "PROJECT" value no longer exists in the enum, and nothing
    writes it (migration 0086ten split the stored rows; normalize_course_type
    resolves the AI's bare "PROJECT" before it can be persisted).

    If one ever reappeared it would be treated as an ordinary taught course and
    held to the narrow [1, 6] band — a loud, visible failure rather than a
    dissertation quietly passing every shape rule.
    """
    v = _credit_range_violations(_typed_course("MCA403", 20, "PROJECT"))
    assert len(v) == 1 and v[0].rule_id == "UGC-COURSE-001"


def test_theory_course_keeps_the_narrow_band():
    # A 20-credit THEORY course must still be an error, not a project's warning.
    v = _credit_range_violations(_typed_course("MCA303", 20, "THEORY"))
    assert len(v) == 1 and v[0].rule_id == "UGC-COURSE-001"
    assert v[0].severity == "ERROR"
