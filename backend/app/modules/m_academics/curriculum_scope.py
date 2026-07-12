"""What counts as a real curriculum course.

Academic Ownership answers one question: which subjects does this institution
actually teach, and who teaches them. A `courses` row is not evidence of that.
Two kinds of row exist in the table long before anyone teaches them:

  1. **Courses of a programme that is not PUBLISHED yet.** A DRAFT, AI_GENERATING,
     GENERATION_FAILED, PENDING_APPROVAL or even APPROVED programme is still a
     proposal — publishing is the act that commits it. Counting its courses gave
     the Dean a dashboard full of subjects that could never be staffed, which is
     why "Courses: 22, Vacant: 22" appeared for a programme with no published
     curriculum at all.

  2. **Choices inside a DRAFT elective paper.** When a Dean adds Artificial
     Intelligence and Machine Learning to Elective 1, real `courses` rows are
     created immediately — a choice needs a code, credits and a syllabus. But
     until the paper is published those subjects do not exist institutionally.

The invariant is therefore:

    a course counts in Academic Ownership  <=>  its programme is PUBLISHED
                                            AND it is not a choice inside a
                                                draft elective paper

Publishing is the single event that flips a course into existence: the dashboard,
the vacancy count, teaching coverage, the department summary, faculty workload and
the assignable-course list all read this one predicate, so none of them can
disagree about what the curriculum contains.

`published_course_sql` deliberately correlates on `courses.program_id` via an
EXISTS rather than requiring a `programs` alias in scope. Half the ownership
queries reach courses through `subject_assignments` and have no `programs` join
to hang a status filter on; making the predicate self-contained is what lets the
same rule apply to every one of them.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Publishing is what commits a curriculum. APPROVED is not enough: an approved
# programme is still editable and may yet change.
_PUBLISHED_PROGRAM = "PUBLISHED"

# A paper in this state has not been published; its choices are not curriculum.
_DRAFT_PAPER = "DRAFT"


def published_course_sql(course: str = "c") -> str:
    """SQL predicate selecting courses that are live, published curriculum.

    `course` is the alias already in scope for `courses`. Returns a bare boolean
    expression, so callers append it with `AND`. Needs no other table in scope.

    The elective half is written as "not attached to a draft paper" rather than
    "attached to a published paper", so an ordinary course
    (`elective_basket_id IS NULL`) passes without needing a paper at all.
    """
    return (
        f"EXISTS ("
        f"  SELECT 1 FROM programs p_cs"
        f"  WHERE p_cs.id = {course}.program_id AND p_cs.status = '{_PUBLISHED_PROGRAM}'"
        f") AND NOT EXISTS ("
        f"  SELECT 1 FROM elective_baskets eb_cs"
        f"  WHERE eb_cs.id = {course}.elective_basket_id AND eb_cs.status = '{_DRAFT_PAPER}'"
        f")"
    )


async def is_published_curriculum_course(course_id: UUID, db: AsyncSession) -> bool:
    """Whether one course is live curriculum — the row-level form of
    `published_course_sql`, for guarding writes such as faculty assignment."""
    row = (await db.execute(
        text(f"SELECT 1 FROM courses c WHERE c.id = :cid AND {published_course_sql()}"),
        {"cid": str(course_id)},
    )).first()
    return row is not None


async def draft_paper_name_for_course(course_id: UUID, db: AsyncSession) -> str | None:
    """The name of the DRAFT elective paper this course belongs to, if any.

    Used only to explain a refusal — "Elective 1 has not been published yet"
    reads a great deal better than "course not found"."""
    return (await db.execute(
        text(
            "SELECT eb.name FROM courses c "
            "JOIN elective_baskets eb ON eb.id = c.elective_basket_id "
            "WHERE c.id = :cid AND eb.status = 'DRAFT'"
        ),
        {"cid": str(course_id)},
    )).scalar_one_or_none()
