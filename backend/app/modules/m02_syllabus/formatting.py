"""Official university syllabus formatting — the Course Information header.

An official syllabus opens with a course header:

    Course Code    : MCA201
    Course Name    : Machine Learning
    Credits        : 4
    L-T-P          : 3-1-2
    Contact Hours  : 90
    Category       : Core

Every one of those six values is DERIVED from the `courses` row. None is stored
on the syllabus, and none is typed in by anyone.

That is a deliberate choice. A stored copy of the credits or the category would
be a second source of truth, and the moment the Board adjusts a course's credits
during review the printed syllabus would quietly disagree with the curriculum it
belongs to. Deriving them means the syllabus document cannot drift from the
course: there is nothing to keep in sync.

It is also why the Dean's course form gains no new fields in Phase A — Category
and Contact Hours are read out of columns that already exist.
"""
from __future__ import annotations

from typing import Protocol

from app.modules.m02_syllabus.models import RefType

# A standard semester. Contact hours are the total taught hours across it, which
# is what a university syllabus prints — not the weekly load.
WEEKS_PER_SEMESTER = 15


class _CourseLike(Protocol):
    """The parts of `Course` this module reads. A Protocol rather than the ORM
    class so these helpers stay unit-testable without a database."""
    is_elective: bool
    course_type: str | None
    hours_lecture: int | None
    hours_tutorial: int | None
    hours_practical: int | None


# ---------------------------------------------------------------------------
# Category — Core | Elective | Lab | Project
# ---------------------------------------------------------------------------

CATEGORY_CORE     = "Core"
CATEGORY_ELECTIVE = "Elective"
CATEGORY_LAB      = "Lab"
CATEGORY_PROJECT  = "Project"


# The types that print as "Project" in the header. MINI_PROJECT and MAJOR_PROJECT
# are both here: the split (V2.3, migration 0086ten) gave them different
# DOCUMENTS, not different header categories — a syllabus header says Project for
# either, and the four-word vocabulary below is deliberate.
#
# Naming them explicitly rather than falling through to Core matters: before the
# split this list said "PROJECT", so after it every project and dissertation in
# the catalogue printed its category as Core.
_PROJECT_CATEGORY_TYPES = frozenset({
    "MINI_PROJECT", "MAJOR_PROJECT", "INTERNSHIP", "SEMINAR",
})


def derive_category(course: _CourseLike) -> str:
    """The course's category, from fields the Dean already fills in.

    Elective wins over course_type: a student choosing between three elective
    subjects is making an elective choice, whatever the subject happens to be.
    INTERNSHIP and SEMINAR fold into Project — they are the same kind of thing
    for a syllabus header, and the vocabulary is deliberately four words wide.
    """
    if course.is_elective:
        return CATEGORY_ELECTIVE
    course_type = (course.course_type or "").upper()
    if course_type == "LAB":
        return CATEGORY_LAB
    if course_type in _PROJECT_CATEGORY_TYPES:
        return CATEGORY_PROJECT
    return CATEGORY_CORE


# ---------------------------------------------------------------------------
# L-T-P and Contact Hours
# ---------------------------------------------------------------------------

def derive_ltp(course: _CourseLike) -> tuple[int, int, int]:
    """(Lecture, Tutorial, Practical) hours per week. Missing reads as zero."""
    return (
        course.hours_lecture   or 0,
        course.hours_tutorial  or 0,
        course.hours_practical or 0,
    )


def format_ltp(course: _CourseLike) -> str:
    """'3-1-2' — the canonical L-T-P string."""
    lecture, tutorial, practical = derive_ltp(course)
    return f"{lecture}-{tutorial}-{practical}"


def derive_contact_hours(course: _CourseLike) -> int:
    """Total taught hours for the semester: (L + T + P) x 15 weeks.

    Returns 0 when a course carries no L-T-P at all, rather than inventing a
    figure — an empty header is honest; a fabricated 45 is not.
    """
    lecture, tutorial, practical = derive_ltp(course)
    return (lecture + tutorial + practical) * WEEKS_PER_SEMESTER


def resolve_teaching_hours(course: _CourseLike, stated: int | None) -> int:
    """The taught hours this syllabus is written to: the Board's figure if it stated
    one, the L-T-P derivation otherwise.

    The derivation is a SUGGESTION about the term — (L + T + P) x 15 — and a Board that
    has looked at it and typed 45 knows something about this semester that the
    multiplication does not. Its figure wins, and no arithmetic here second-guesses it.
    """
    return stated if stated and stated > 0 else derive_contact_hours(course)


def resolve_hours_per_week(course: _CourseLike, stated: int | None) -> int:
    """Hours a week, as the header prints it — 'No. of Hours / Week: 04'.

    The Board's figure if it stated one, the course's weekly L-T-P load otherwise,
    which is exactly what hours-a-week means when nobody has overruled it.
    """
    if stated and stated > 0:
        return stated
    lecture, tutorial, practical = derive_ltp(course)
    return lecture + tutorial + practical


def derive_teaching_weeks(teaching_hours: int, hours_per_week: int) -> int:
    """How many weeks the subject runs — 52 hours at 4 a week is 13.

    NOT stored, and that is the point: it is the arithmetic between the two figures the
    Board states, and a third column holding it is a column that can disagree with them.
    Computed here, for the one consumer that wants it — the generator, which paces a
    unit differently over 10 weeks than over 15. Falls back to the standard semester
    when the figures cannot produce one.
    """
    if teaching_hours > 0 and hours_per_week > 0:
        return max(1, round(teaching_hours / hours_per_week))
    return WEEKS_PER_SEMESTER


def has_practical(course: _CourseLike) -> bool:
    """Whether the syllabus should carry a Practical Components section."""
    return (course.hours_practical or 0) > 0 or derive_category(course) == CATEGORY_LAB


# ---------------------------------------------------------------------------
# Unit hours — the Board's, and nobody else's
#
# There is deliberately NO function here that computes them.
#
# An earlier version had one: when the Board generated forty syllabi in a batch and
# stated no hours, the system divided each course's contact hours evenly across its
# units. The arithmetic was right and the decision was not ours to make. How a subject's
# taught hours are apportioned across its units is an academic judgement — it says which
# material matters and how long it is worth — and a system that makes it quietly has
# taken curriculum design away from the Board while appearing to help.
#
# So nothing derives them. If the Board has not allocated the hours, generation STOPS
# and asks for them (m02.service.dispatch_ai_generation). A syllabus that cannot be
# generated until a human has decided how it is taught is the correct behaviour, not a
# gap to be filled.
#
# The one number the system may suggest is the DEFAULT IN THE FORM the Board is filling
# in — a suggestion a human looks at and accepts is not a decision a system made.
# ---------------------------------------------------------------------------


def course_information(
    course,
    *,
    regulation_year: int | None = None,
    teaching_hours: int | None = None,
    hours_per_week: int | None = None,
) -> dict:
    """The full Course Information header, ready to render.

    Takes the ORM `Course` (needs `code`, `title`, `credits`, `semester` and
    `course_type` on top of the Protocol above) and returns the header a real
    regulation prints — the course, what kind of course it is, when it is taught, and
    under which regulation.

    Still DERIVED, every field of it. The Board does not retype the course code into
    the syllabus: the curriculum already says what this course is, and a syllabus that
    kept its own copy would disagree with it the moment the Dean corrected a credit.

    The two the Board may overrule are the taught hours and the hours a week — the pair
    a real syllabus prints at the top of the page ("Total Teaching Hours: 52  /  No. of
    Hours per Week: 04"). Pass the syllabus's figures and the header says what the
    subject is actually taught for; omit them and it falls back to the L-T-P, which is
    what every syllabus printed before the Board could state its own.
    """
    return {
        "course_code":     course.code,
        "course_name":     course.title,
        "credits":         course.credits,
        "ltp":             format_ltp(course),
        "contact_hours":   resolve_teaching_hours(course, teaching_hours),
        "hours_per_week":  resolve_hours_per_week(course, hours_per_week),
        "category":        derive_category(course),
        "course_type":     (course.course_type or "THEORY"),
        "semester":        course.semester,
        # The regulation the curriculum belongs to — "Regulation 2026". It lives on
        # the programme, because a regulation is a property of the curriculum, not of
        # one subject inside it.
        "regulation_year": regulation_year,
    }


# ---------------------------------------------------------------------------
# Bibliography — three printed sections, five stored types
# ---------------------------------------------------------------------------

SECTION_TEXT_BOOKS        = "Text Books"
SECTION_REFERENCE_BOOKS   = "Reference Books"
SECTION_SUGGESTED_READING = "Suggested Reading"
SECTION_WEB_RESOURCES     = "Web Resources"

BIBLIOGRAPHY_SECTIONS: dict[str, str] = {
    RefType.TEXTBOOK.value:          SECTION_TEXT_BOOKS,
    RefType.REFERENCE.value:         SECTION_REFERENCE_BOOKS,
    RefType.JOURNAL.value:           SECTION_REFERENCE_BOOKS,
    RefType.SUGGESTED_READING.value: SECTION_SUGGESTED_READING,
    RefType.WEB_RESOURCE.value:      SECTION_WEB_RESOURCES,
    RefType.ONLINE.value:            SECTION_WEB_RESOURCES,
}

# Print order. A section with no references is omitted entirely rather than
# printed empty.
SECTION_ORDER = (
    SECTION_TEXT_BOOKS,
    SECTION_REFERENCE_BOOKS,
    SECTION_SUGGESTED_READING,
    SECTION_WEB_RESOURCES,
)


# ---------------------------------------------------------------------------
# Unit numbering — a regulation prints Unit I, not Unit 1
# ---------------------------------------------------------------------------

_ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


def roman(unit_number: int) -> str:
    """1 -> 'I'. Falls back to the digit beyond X, which no syllabus reaches."""
    if 1 <= unit_number <= len(_ROMAN):
        return _ROMAN[unit_number - 1]
    return str(unit_number)


def unit_heading(unit) -> str:
    """The heading exactly as it prints in the regulation:

        UNIT I - INTRODUCTION TO COMPUTER SYSTEMS                    (12 Hours)
    """
    hours = f"{unit.total_hours} Hours" if unit.total_hours else ""
    title = (unit.title or "").upper()
    return f"UNIT {roman(unit.unit_number)} - {title}".rstrip(" -") + (f"  ({hours})" if hours else "")


def unit_topic_lines(unit) -> list[str]:
    """The unit's printed lines — 12-20 of them in a real regulation.

    THIS is the unit. The list of academic topics under the heading is what an
    AICTE / Anna University / VTU syllabus prints, and it is what a lecturer reads
    to know what to teach.

    Falls back to splitting the prose block for syllabi that predate the topic list
    (or for a Board that pasted a paragraph in) — they must still print as a
    document rather than as nothing.
    """
    titles = [
        str(t.get("title", "")).strip()
        for t in (unit.topics or [])
        if isinstance(t, dict) and str(t.get("title", "")).strip()
    ]
    if titles:
        return titles

    prose = (unit.content or "").strip().rstrip(".")
    return [part.strip() for part in prose.split(",") if part.strip()] if prose else []


def unit_body(unit) -> str:
    """The unit as one prose line, for regulations that print paragraphs rather
    than bullets — and for anywhere a single string is more useful than a list."""
    if unit.content and unit.content.strip():
        return unit.content.strip()

    lines = unit_topic_lines(unit)
    return ", ".join(lines) + "." if lines else ""


def section_for(ref_type: str | RefType) -> str:
    value = ref_type.value if isinstance(ref_type, RefType) else str(ref_type)
    return BIBLIOGRAPHY_SECTIONS.get(value.upper(), SECTION_SUGGESTED_READING)


def group_references(references: list) -> dict[str, list]:
    """Group references into the three printed sections, in print order,
    omitting sections that have none."""
    grouped: dict[str, list] = {name: [] for name in SECTION_ORDER}
    for ref in references:
        grouped[section_for(ref.ref_type)].append(ref)
    return {name: refs for name, refs in grouped.items() if refs}
