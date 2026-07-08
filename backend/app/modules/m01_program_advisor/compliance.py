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


@dataclasses.dataclass
class CourseNode:
    id:                      UUID
    code:                    str
    credits:                 int
    semester:                int
    is_elective:             bool
    prerequisite_course_ids: list[UUID]
    course_type:             str | None = None   # THEORY|LAB|PROJECT|INTERNSHIP|SEMINAR

    def is_project_or_internship(self) -> bool:
        return self.course_type in ("PROJECT", "INTERNSHIP")


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
    min_elective_ratio: float
    min_po_count:      int
    min_course_credits: int
    max_course_credits: int


_UG4 = _Thresholds(   # 4-year UG: B.Tech, BE, BCA, B.Arch, B.Pharm
    min_total_credits=160, max_total_credits=200,
    min_sem_credits=14,    max_sem_credits=30,
    min_elective_ratio=0.20,
    min_po_count=3,
    min_course_credits=1,  max_course_credits=6,
)

_UG3 = _Thresholds(   # 3-year UG: BSc, BBA, BA, B.Com, BHM, BDes
    min_total_credits=120, max_total_credits=160,
    min_sem_credits=14,    max_sem_credits=30,
    min_elective_ratio=0.20,
    min_po_count=3,
    min_course_credits=1,  max_course_credits=6,
)

_PG2 = _Thresholds(   # 2-year PG: M.Tech, ME, MBA, MSc, MCA, MA, M.Com, M.Pharm
    min_total_credits=60,  max_total_credits=120,
    min_sem_credits=12,    max_sem_credits=30,
    min_elective_ratio=0.15,
    min_po_count=3,
    min_course_credits=1,  max_course_credits=6,
)

_DEFAULT = _Thresholds(
    min_total_credits=60,  max_total_credits=200,
    min_sem_credits=12,    max_sem_credits=30,
    min_elective_ratio=0.15,
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
    courses: list[CourseNode],
    t: _Thresholds,
) -> list[ComplianceViolation]:
    sem_credits: dict[int, int] = {}
    for course in courses:
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
    courses: list[CourseNode],
    t: _Thresholds,
) -> list[ComplianceViolation]:
    """Phase 4.2 policy: a program is validated against its TOTAL configured
    credits, not a hard per-semester cap. A semester carrying more than the
    typical per-semester load is therefore NOT a blocking error — it is a
    non-blocking, advisory recommendation to rebalance. Total-credit ceilings
    are still enforced by _check_total_credits_max."""
    sem_credits: dict[int, int] = {}
    for course in courses:
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
    courses: list[CourseNode],
    t: _Thresholds,
) -> list[ComplianceViolation]:
    sem_credits: dict[int, int] = {}
    for course in courses:
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


def _check_elective_ratio(
    courses: list[CourseNode],
    t: _Thresholds,
) -> list[ComplianceViolation]:
    if not courses:
        return []
    elective_count = sum(1 for c in courses if c.is_elective)
    ratio = elective_count / len(courses)
    if ratio < t.min_elective_ratio:
        return [ComplianceViolation(
            rule_id="UGC-ELEC-001",
            rule_ref="UGC LOCF 2020 §5.3",
            message=(
                f"Electives are {round(ratio * 100, 1)}% of total "
                f"({elective_count}/{len(courses)}), below the recommended "
                f"{round(t.min_elective_ratio * 100)}% minimum. Elective selection "
                "is not yet implemented in this phase — current elective courses "
                "are placeholders, so this is informational only and not a defect "
                "in the generated structure."
            ),
            severity="INFO",
        )]
    return []


_PROJECT_INTERNSHIP_MAX_CREDITS = 20


def _check_course_credit_range(
    courses: list[CourseNode],
    t: _Thresholds,
) -> list[ComplianceViolation]:
    violations = []
    for course in courses:
        if course.is_project_or_internship():
            # Projects and internships may span 6–20 credits per UGC flexibility norms.
            if not (6 <= course.credits <= _PROJECT_INTERNSHIP_MAX_CREDITS):
                violations.append(ComplianceViolation(
                    rule_id="UGC-COURSE-002",
                    rule_ref="UGC LOCF 2020 §3.2 (project/internship flexibility)",
                    message=(
                        f"Course {course.code!r} ({course.course_type}) has {course.credits} credit(s); "
                        f"project/internship range is [6, {_PROJECT_INTERNSHIP_MAX_CREDITS}]."
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
    courses: list[CourseNode],
) -> list[ComplianceViolation]:
    final_semester = program.duration_years * 2
    sem_types: dict[int, set[str]] = {}
    for course in courses:
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
    courses: list[CourseNode],
) -> list[ComplianceViolation]:
    final_semester = program.duration_years * 2
    final_courses = [c for c in courses if c.semester == final_semester]
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
                "PROJECT and INTERNSHIP courses."
            ),
            severity="WARNING",
        )]
    return []


def _check_layout_zones(
    program: ProgramNode,
    courses: list[CourseNode],
) -> list[ComplianceViolation]:
    """Finalized curriculum layout: every semester before the last two is
    core-only (no project/internship/elective); the second-to-last semester
    holds the mini project + elective basket(s); the final semester is
    checked separately by _check_final_semester_composition. A soft realism
    warning, same severity tier as the rest of this module's shape checks."""
    total_semesters = program.duration_years * 2
    if total_semesters < 3:
        return []  # too short to have a distinct core-only zone

    mini_project_semester = total_semesters - 1
    violations: list[ComplianceViolation] = []

    core_zone_courses = [c for c in courses if c.semester < mini_project_semester]
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

    mini_semester_courses = [c for c in courses if c.semester == mini_project_semester]
    if mini_semester_courses:
        has_mini_project = any(c.course_type == "PROJECT" for c in mini_semester_courses)
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
                message=f"Semester {mini_project_semester} is missing its elective basket course(s).",
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
) -> ComplianceResult:
    t = _get_thresholds(program.degree_type)
    violations: list[ComplianceViolation] = []

    violations.extend(_check_total_credits_min(program, t))
    violations.extend(_check_total_credits_max(program, t))
    violations.extend(_check_semester_credits_min(courses, t))
    violations.extend(_check_semester_credits_max(courses, t))
    violations.extend(_check_semester_balance(courses, t))
    violations.extend(_check_elective_ratio(courses, t))
    violations.extend(_check_course_credit_range(courses, t))
    violations.extend(_check_lab_presence(program, courses))
    violations.extend(_check_final_semester_composition(program, courses))
    violations.extend(_check_layout_zones(program, courses))
    violations.extend(_check_program_outcomes(program, t))
    violations.extend(_check_duplicate_codes(courses))
    violations.extend(detect_prerequisite_cycles(courses))

    passed = all(v.severity != "ERROR" for v in violations)
    return ComplianceResult(passed=passed, violations=violations)
