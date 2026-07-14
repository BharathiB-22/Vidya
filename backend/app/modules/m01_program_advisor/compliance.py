from __future__ import annotations

import dataclasses
from uuid import UUID


# ---------------------------------------------------------------------------
# Input types  (pure Python — no ORM or DB dependency)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ProgramNode:
    degree_type:    str
    duration_years: int
    total_credits:  int
    outcome_count:  int


# The course types this module reasons about, as plain strings.
#
# These MIRROR m01.models.CourseType and are deliberately not imported from it:
# this module is pure logic over dataclasses (see the header) and stays free of
# SQLAlchemy so it can be unit-tested without the ORM or a database. The mirror
# is pinned against the real enum by a test, so the two cannot drift.
#
# There is no "PROJECT". It was split into MINI_PROJECT and MAJOR_PROJECT in
# V2.3 (migration 0086ten) because they are different documents; every rule below
# that used to compare against "PROJECT" now has to name both, and a rule that
# means *specifically* a mini project — UGC-LAYOUT-002 — finally can.
TYPE_THEORY        = "THEORY"
TYPE_LAB           = "LAB"
TYPE_INTERNSHIP    = "INTERNSHIP"
TYPE_MINI_PROJECT  = "MINI_PROJECT"
TYPE_MAJOR_PROJECT = "MAJOR_PROJECT"
TYPE_SEMINAR       = "SEMINAR"

PROJECT_TYPES: frozenset[str] = frozenset({TYPE_MINI_PROJECT, TYPE_MAJOR_PROJECT})
PROJECT_OR_INTERNSHIP_TYPES: frozenset[str] = PROJECT_TYPES | {TYPE_INTERNSHIP}


@dataclasses.dataclass
class CourseNode:
    id:                      UUID
    code:                    str
    credits:                 int
    semester:                int
    is_elective:             bool
    prerequisite_course_ids: list[UUID]
    # THEORY|LAB|INTERNSHIP|MINI_PROJECT|MAJOR_PROJECT|SEMINAR
    course_type:             str | None = None
    # Set when this course is one interchangeable OPTION inside an elective
    # slot. Options are real courses (own code, syllabus, faculty, seats) but
    # they are not curriculum entries in their own right — the slot is.
    elective_basket_id:      UUID | None = None

    def is_project(self) -> bool:
        """A project of either size — mini or major."""
        return self.course_type in PROJECT_TYPES

    def is_project_or_internship(self) -> bool:
        """The courses that are DONE rather than taught, and whose credit band is
        therefore wide (2 for an early mini project, 20 for a dissertation)."""
        return self.course_type in PROJECT_OR_INTERNSHIP_TYPES


@dataclasses.dataclass
class ElectiveSlotNode:
    """ONE elective slot in the curriculum, e.g. "Elective 1" worth 3 credits
    in Semester 3. A student takes exactly one of its options, so the slot
    counts once, at its own credit weight, no matter how many options exist."""
    id:       UUID
    name:     str
    credits:  int
    semester: int


def _curriculum_units(
    courses: list[CourseNode],
    slots: list[ElectiveSlotNode],
) -> list[CourseNode]:
    """The list every credit- and shape-based rule must reason over: real
    curriculum entries, with each elective slot standing in for the whole
    basket of options behind it.

    Semester 3 holding OS(4) + CN(4) + Elective 1(3) over {AI, DM, DL} yields
    three units totalling 11 credits — not five units totalling 17.

    An option whose slot was not supplied still counts individually, so a
    caller that passes no slots keeps the pre-slot behaviour rather than
    silently dropping credits."""
    known_slot_ids = {s.id for s in slots}
    units = [
        c for c in courses
        if c.elective_basket_id is None or c.elective_basket_id not in known_slot_ids
    ]
    units.extend(
        CourseNode(
            id=slot.id,
            code=slot.name,
            credits=slot.credits,
            semester=slot.semester,
            is_elective=True,
            prerequisite_course_ids=[],
            course_type=None,
        )
        for slot in slots
    )
    return units


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ComplianceViolation:
    rule_id:  str
    rule_ref: str
    message:  str
    severity: str   # "ERROR" | "WARNING" | "INFO"


@dataclasses.dataclass
class ComplianceResult:
    passed:     bool
    violations: list[ComplianceViolation]


# ---------------------------------------------------------------------------
# Thresholds per degree category
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class _Thresholds:
    min_total_credits: int
    max_total_credits: int
    min_sem_credits:   int
    max_sem_credits:   int
    min_po_count:      int
    min_course_credits: int
    max_course_credits: int


_UG4 = _Thresholds(   # 4-year UG: B.Tech, BE, BCA, B.Arch, B.Pharm
    min_total_credits=160, max_total_credits=200,
    min_sem_credits=14,    max_sem_credits=30,
    min_po_count=3,
    min_course_credits=1,  max_course_credits=6,
)

_UG3 = _Thresholds(   # 3-year UG: BSc, BBA, BA, B.Com, BHM, BDes
    min_total_credits=120, max_total_credits=160,
    min_sem_credits=14,    max_sem_credits=30,
    min_po_count=3,
    min_course_credits=1,  max_course_credits=6,
)

_PG2 = _Thresholds(   # 2-year PG: M.Tech, ME, MBA, MSc, MCA, MA, M.Com, M.Pharm
    min_total_credits=60,  max_total_credits=120,
    min_sem_credits=12,    max_sem_credits=30,
    min_po_count=3,
    min_course_credits=1,  max_course_credits=6,
)

_DEFAULT = _Thresholds(
    min_total_credits=60,  max_total_credits=200,
    min_sem_credits=12,    max_sem_credits=30,
    min_po_count=3,
    min_course_credits=1,  max_course_credits=6,
)

_UG4_KEYS = {"btech", "be", "barch", "bca", "bpharm"}
_UG3_KEYS = {"bsc", "bba", "ba", "bcom", "bhm", "bdes"}
_PG2_KEYS = {"mtech", "me", "mba", "msc", "mca", "ma", "mcom", "mpharm", "mdes"}

_MAX_SEM_SPREAD = 15   # WARNING if max − min semester load exceeds this


def _get_thresholds(degree_type: str) -> _Thresholds:
    key = degree_type.lower().replace(".", "").replace(" ", "").replace("-", "")
    if key in _UG4_KEYS:
        return _UG4
    if key in _UG3_KEYS:
        return _UG3
    if key in _PG2_KEYS:
        return _PG2
    return _DEFAULT


def classify_degree_level(degree_type: str) -> str:
    """Return 'PG' or 'UG' for a program's degree_type string.

    Shared by downstream modules (M03 course kits, M05 learning packages, …)
    so degree level propagates consistently instead of each module guessing
    or hardcoding a UG default.
    """
    key = degree_type.lower().replace(".", "").replace(" ", "").replace("-", "")
    if key in _PG2_KEYS:
        return "PG"
    return "UG"


# ---------------------------------------------------------------------------
# Rule functions (private)
# ---------------------------------------------------------------------------

def _check_total_credits_min(
    program: ProgramNode,
    t: _Thresholds,
) -> list[ComplianceViolation]:
    if program.total_credits < t.min_total_credits:
        return [ComplianceViolation(
            rule_id="UGC-CRED-001",
            rule_ref="UGC LOCF 2020 §3.1",
            message=(
                f"Total credits {program.total_credits} is below the minimum "
                f"{t.min_total_credits} required for {program.degree_type} programs."
            ),
            severity="ERROR",
        )]
    return []


def _check_total_credits_max(
    program: ProgramNode,
    t: _Thresholds,
) -> list[ComplianceViolation]:
    if program.total_credits > t.max_total_credits:
        return [ComplianceViolation(
            rule_id="UGC-CRED-002",
            rule_ref="UGC LOCF 2020 §3.1",
            message=(
                f"Total credits {program.total_credits} exceeds the recommended maximum "
                f"{t.max_total_credits} for {program.degree_type} programs."
            ),
            severity="WARNING",
        )]
    return []


def _check_semester_credits_min(
    units: list[CourseNode],
    t: _Thresholds,
) -> list[ComplianceViolation]:
    sem_credits: dict[int, int] = {}
    for course in units:
        sem_credits[course.semester] = sem_credits.get(course.semester, 0) + course.credits

    violations = []
    for sem, total in sorted(sem_credits.items()):
        if total < t.min_sem_credits:
            violations.append(ComplianceViolation(
                rule_id="UGC-SEM-001",
                rule_ref="UGC LOCF 2020 §4.1",
                message=(
                    f"Semester {sem} has {total} credit(s), below the minimum "
                    f"{t.min_sem_credits} credits per semester."
                ),
                severity="ERROR",
            ))
    return violations


def _check_semester_credits_max(
    units: list[CourseNode],
    t: _Thresholds,
) -> list[ComplianceViolation]:
    """Phase 4.2 policy: a program is validated against its TOTAL configured
    credits, not a hard per-semester cap. A semester carrying more than the
    typical per-semester load is therefore NOT a blocking error — it is a
    non-blocking, advisory recommendation to rebalance. Total-credit ceilings
    are still enforced by _check_total_credits_max."""
    sem_credits: dict[int, int] = {}
    for course in units:
        sem_credits[course.semester] = sem_credits.get(course.semester, 0) + course.credits

    if not sem_credits:
        return []

    lightest_sem = min(sem_credits, key=lambda s: sem_credits[s])

    violations = []
    for sem, total in sorted(sem_credits.items()):
        if total > t.max_sem_credits:
            suggestion = (
                f" Consider moving one elective to Semester {lightest_sem} "
                f"({sem_credits[lightest_sem]} credits) to balance the workload."
                if lightest_sem != sem else ""
            )
            violations.append(ComplianceViolation(
                rule_id="UGC-SEM-002",
                rule_ref="UGC LOCF 2020 §4.1 (advisory)",
                message=(
                    f"Semester {sem} has a heavier workload ({total} credits, "
                    f"above the typical {t.max_sem_credits} per semester)."
                    f"{suggestion}"
                ),
                severity="WARNING",
            ))
    return violations


def _check_semester_balance(
    units: list[CourseNode],
    t: _Thresholds,
) -> list[ComplianceViolation]:
    sem_credits: dict[int, int] = {}
    for course in units:
        sem_credits[course.semester] = sem_credits.get(course.semester, 0) + course.credits

    if len(sem_credits) < 2:
        return []

    loads = list(sem_credits.values())
    spread = max(loads) - min(loads)
    if spread > _MAX_SEM_SPREAD:
        return [ComplianceViolation(
            rule_id="UGC-SEM-003",
            rule_ref="UGC LOCF 2020 §4.2",
            message=(
                f"Semester credit spread is {spread} "
                f"(heaviest: {max(loads)}, lightest: {min(loads)} credits), "
                f"exceeding the recommended balance threshold of {_MAX_SEM_SPREAD}."
            ),
            severity="WARNING",
        )]
    return []


def _check_slot_option_credits(
    courses: list[CourseNode],
    slots: list[ElectiveSlotNode],
) -> list[ComplianceViolation]:
    """Options inside one slot are interchangeable, so they must all be worth
    the slot's credits. If Elective 1 is a 3-credit slot but DM301 carries 4,
    a student who picks DM301 earns 4 credits while the curriculum counted 3 —
    attendance and internal marks run against the course the student actually
    chose, so the mismatch reaches transcripts."""
    by_id = {s.id: s for s in slots}
    violations = []
    for course in courses:
        slot = by_id.get(course.elective_basket_id) if course.elective_basket_id else None
        if slot is not None and course.credits != slot.credits:
            violations.append(ComplianceViolation(
                rule_id="UGC-ELEC-002",
                rule_ref="Internal — Curriculum Integrity",
                message=(
                    f"Elective option {course.code!r} is {course.credits} credit(s) but its "
                    f"slot {slot.name!r} is worth {slot.credits}. Every option in a slot must "
                    f"carry the slot's credits — a student takes exactly one of them."
                ),
                severity="WARNING",
            ))
    return violations


# A mini project is routinely worth 2 credits, while a final-year dissertation
# runs to 20. Both are projects, so the band has to span the whole range rather
# than assume the dissertation.
_PROJECT_INTERNSHIP_MIN_CREDITS = 2
_PROJECT_INTERNSHIP_MAX_CREDITS = 20


def _check_course_credit_range(
    courses: list[CourseNode],
    t: _Thresholds,
) -> list[ComplianceViolation]:
    violations = []
    for course in courses:
        if course.is_project_or_internship():
            if not (_PROJECT_INTERNSHIP_MIN_CREDITS <= course.credits <= _PROJECT_INTERNSHIP_MAX_CREDITS):
                violations.append(ComplianceViolation(
                    rule_id="UGC-COURSE-002",
                    rule_ref="UGC LOCF 2020 §3.2 (project/internship flexibility)",
                    message=(
                        f"Course {course.code!r} ({course.course_type}) has {course.credits} credit(s); "
                        f"project/internship range is "
                        f"[{_PROJECT_INTERNSHIP_MIN_CREDITS}, {_PROJECT_INTERNSHIP_MAX_CREDITS}]."
                    ),
                    severity="WARNING",
                ))
        else:
            if not (t.min_course_credits <= course.credits <= t.max_course_credits):
                violations.append(ComplianceViolation(
                    rule_id="UGC-COURSE-001",
                    rule_ref="UGC LOCF 2020 §3.2",
                    message=(
                        f"Course {course.code!r} has {course.credits} credit(s); "
                        f"accepted range is [{t.min_course_credits}, {t.max_course_credits}]."
                    ),
                    severity="ERROR",
                ))
    return violations


def _check_lab_presence(
    program: ProgramNode,
    units: list[CourseNode],
) -> list[ComplianceViolation]:
    final_semester = program.duration_years * 2
    sem_types: dict[int, set[str]] = {}
    for course in units:
        sem_types.setdefault(course.semester, set()).add(course.course_type or "")

    violations = []
    for sem, types in sorted(sem_types.items()):
        if sem == final_semester:
            continue
        if "LAB" not in types:
            violations.append(ComplianceViolation(
                rule_id="UGC-LAB-001",
                rule_ref="Internal — Curriculum Realism",
                message=(
                    f"Semester {sem} has no LAB course; university curricula typically "
                    "pair theory courses with a corresponding laboratory course in each "
                    "non-final semester."
                ),
                severity="WARNING",
            ))
    return violations


def _check_final_semester_composition(
    program: ProgramNode,
    units: list[CourseNode],
) -> list[ComplianceViolation]:
    final_semester = program.duration_years * 2
    final_courses = [c for c in units if c.semester == final_semester]
    if not final_courses:
        return []

    non_conforming = [c for c in final_courses if not c.is_project_or_internship()]
    if non_conforming:
        codes = ", ".join(c.code for c in non_conforming)
        return [ComplianceViolation(
            rule_id="UGC-FINALSEM-001",
            rule_ref="Internal — Curriculum Realism",
            message=(
                f"Final semester ({final_semester}) contains non-project/internship "
                f"course(s): {codes}. The final semester is expected to contain only "
                "project (mini or major) and internship courses."
            ),
            severity="WARNING",
        )]
    return []


def _check_layout_zones(
    program: ProgramNode,
    units: list[CourseNode],
) -> list[ComplianceViolation]:
    """Finalized curriculum layout: every semester before the last two is
    core-only (no project/internship/elective slot); the second-to-last semester
    holds the mini project + elective slot(s); the final semester is
    checked separately by _check_final_semester_composition. A soft realism
    warning, same severity tier as the rest of this module's shape checks."""
    total_semesters = program.duration_years * 2
    if total_semesters < 3:
        return []  # too short to have a distinct core-only zone

    mini_project_semester = total_semesters - 1
    violations: list[ComplianceViolation] = []

    core_zone_courses = [c for c in units if c.semester < mini_project_semester]
    misplaced = [
        c for c in core_zone_courses
        if c.is_elective or c.is_project_or_internship()
    ]
    if misplaced:
        codes = ", ".join(c.code for c in misplaced)
        violations.append(ComplianceViolation(
            rule_id="UGC-LAYOUT-001",
            rule_ref="Internal — Curriculum Realism",
            message=(
                f"Semesters 1-{mini_project_semester - 1} are expected to contain only core "
                f"(non-elective, non-project, non-internship) courses; found: {codes}."
            ),
            severity="WARNING",
        ))

    mini_semester_courses = [c for c in units if c.semester == mini_project_semester]
    if mini_semester_courses:
        # Specifically a MINI project. Under the old single "PROJECT" value this
        # rule could not tell one from a dissertation, so a major project sitting
        # in the second-to-last semester silently satisfied it.
        has_mini_project = any(
            c.course_type == TYPE_MINI_PROJECT for c in mini_semester_courses
        )
        has_elective = any(c.is_elective for c in mini_semester_courses)
        if not has_mini_project:
            violations.append(ComplianceViolation(
                rule_id="UGC-LAYOUT-002",
                rule_ref="Internal — Curriculum Realism",
                message=f"Semester {mini_project_semester} is missing its Mini Project course.",
                severity="WARNING",
            ))
        if not has_elective:
            violations.append(ComplianceViolation(
                rule_id="UGC-LAYOUT-003",
                rule_ref="Internal — Curriculum Realism",
                message=f"Semester {mini_project_semester} is missing its elective slot.",
                severity="WARNING",
            ))

    return violations


def _check_program_outcomes(
    program: ProgramNode,
    t: _Thresholds,
) -> list[ComplianceViolation]:
    if program.outcome_count < t.min_po_count:
        return [ComplianceViolation(
            rule_id="UGC-PO-001",
            rule_ref="NBA Criteria 3 §3.1",
            message=(
                f"Program has {program.outcome_count} outcome(s); "
                f"minimum {t.min_po_count} Programme Outcomes required for accreditation."
            ),
            severity="ERROR",
        )]
    return []


def _check_duplicate_codes(
    courses: list[CourseNode],
) -> list[ComplianceViolation]:
    seen: dict[str, int] = {}
    for course in courses:
        seen[course.code] = seen.get(course.code, 0) + 1

    violations = []
    for code, count in sorted(seen.items()):
        if count > 1:
            violations.append(ComplianceViolation(
                rule_id="UGC-CODE-001",
                rule_ref="Internal — Program Integrity",
                message=(
                    f"Course code {code!r} appears {count} times; "
                    "codes must be unique within a program."
                ),
                severity="ERROR",
            ))
    return violations


# ---------------------------------------------------------------------------
# DAG cycle detection (public — also called independently by STEP-07 Celery task)
# ---------------------------------------------------------------------------

def detect_prerequisite_cycles(
    courses: list[CourseNode],
) -> list[ComplianceViolation]:
    # DFS with WHITE/GRAY/BLACK colouring. A GRAY node reached during traversal
    # is a back edge, meaning a cycle exists in the prerequisite graph.
    code_map: dict[UUID, str] = {c.id: c.code for c in courses}
    course_ids: set[UUID] = set(code_map)
    adj: dict[UUID, list[UUID]] = {c.id: c.prerequisite_course_ids for c in courses}

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[UUID, int] = {cid: WHITE for cid in course_ids}
    reported: set[frozenset] = set()
    violations: list[ComplianceViolation] = []

    def _dfs(node: UUID, path: list[UUID]) -> None:
        color[node] = GRAY
        for prereq in adj.get(node, []):
            if prereq not in course_ids:
                continue   # cross-program reference — not our responsibility to validate
            if color[prereq] == GRAY:
                cycle_start = path.index(prereq)
                cycle_nodes = path[cycle_start:]
                key = frozenset(cycle_nodes)
                if key not in reported:
                    reported.add(key)
                    display = [code_map[n] for n in cycle_nodes] + [code_map[prereq]]
                    violations.append(ComplianceViolation(
                        rule_id="UGC-DAG-001",
                        rule_ref="UGC LOCF 2020 §4.3",
                        message="Circular prerequisite chain: " + " → ".join(display),
                        severity="ERROR",
                    ))
            elif color[prereq] == WHITE:
                _dfs(prereq, path + [prereq])
        color[node] = BLACK

    for cid in course_ids:
        if color[cid] == WHITE:
            _dfs(cid, [cid])

    return violations


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_compliance_check(
    program: ProgramNode,
    courses: list[CourseNode],
    slots: list[ElectiveSlotNode] | None = None,
) -> ComplianceResult:
    """`courses` is every course in the program, including each option inside
    every elective slot. `slots` are the curriculum's elective slots.

    Rules split into two families. Credit and shape rules run over the
    *curriculum units* — cores plus one entry per slot — so a slot contributes
    its own credits once rather than once per option. Integrity rules (unique
    codes, per-course credit range, prerequisite cycles) run over every real
    course, options included, because each option is a real course a student
    can enrol in.

    Omitting `slots` reproduces the pre-slot behaviour for callers that have no
    basket information."""
    t = _get_thresholds(program.degree_type)
    slots = slots or []
    units = _curriculum_units(courses, slots)
    violations: list[ComplianceViolation] = []

    # Curriculum-shape rules — one slot is one course.
    violations.extend(_check_total_credits_min(program, t))
    violations.extend(_check_total_credits_max(program, t))
    violations.extend(_check_semester_credits_min(units, t))
    violations.extend(_check_semester_credits_max(units, t))
    violations.extend(_check_semester_balance(units, t))
    violations.extend(_check_lab_presence(program, units))
    violations.extend(_check_final_semester_composition(program, units))
    violations.extend(_check_layout_zones(program, units))
    violations.extend(_check_program_outcomes(program, t))

    # Integrity rules — every option is a real course.
    violations.extend(_check_course_credit_range(courses, t))
    violations.extend(_check_slot_option_credits(courses, slots))
    violations.extend(_check_duplicate_codes(courses))
    violations.extend(detect_prerequisite_cycles(courses))

    passed = all(v.severity != "ERROR" for v in violations)
    return ComplianceResult(passed=passed, violations=violations)
