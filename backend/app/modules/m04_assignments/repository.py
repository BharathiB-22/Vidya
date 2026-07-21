"""
M04 Assignments — Repository layer.

Conventions (mirrors M06):
  - All methods are @staticmethod with keyword-only `db: AsyncSession`.
  - Write methods use db.flush() so callers control commit boundaries.
  - No cross-tenant queries; search_path set at connection time.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m04_assignments.models import (
    AIEvalStatus,
    Assignment,
    AssignmentEvaluation,
    AssignmentStatus,
    AssignmentSubmission,
    SubmissionStatus,
)

# How coursework identifies itself to the M09.6 assignment engine, whose target is
# polymorphic (scanned_script, revaluation_request, …). One student submission is
# one unit of evaluation work.
COURSEWORK_TARGET_ENTITY = "assignment_submission"


class AssignmentRepository:

    @staticmethod
    async def create(
        *,
        created_by_user_id: UUID,
        title: str,
        assignment_type: str,
        max_marks: float,
        syllabus_id: UUID | None = None,
        description: str | None = None,
        instructions: str | None = None,
        weightage_percent: float | None = None,
        due_date: datetime | None = None,
        allow_late: bool = True,
        late_penalty_percent: float | None = None,
        max_attempts: int = 1,
        allowed_file_types: list[str] | None = None,
        evaluator_user_ids: list[UUID] | None = None,
        questions: list[dict] | None = None,
        question_paper_url: str | None = None,
        db: AsyncSession,
    ) -> Assignment:
        obj = Assignment(
            created_by_user_id=created_by_user_id,
            title=title,
            assignment_type=assignment_type,
            max_marks=max_marks,
            syllabus_id=syllabus_id,
            description=description,
            instructions=instructions,
            weightage_percent=weightage_percent,
            due_date=due_date,
            allow_late=allow_late,
            late_penalty_percent=late_penalty_percent,
            max_attempts=max_attempts,
            allowed_file_types=allowed_file_types or [],
            # JSONB holds no UUID type of its own — store the canonical string form.
            evaluator_user_ids=[str(e) for e in (evaluator_user_ids or [])],
            questions=questions or [],
            question_paper_url=question_paper_url,
            status=AssignmentStatus.DRAFT,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get_by_id(assignment_id: UUID, *, db: AsyncSession) -> Assignment | None:
        result = await db.execute(select(Assignment).where(Assignment.id == assignment_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_assignments(
        *,
        db: AsyncSession,
        syllabus_id: UUID | None = None,
        syllabus_ids: list[UUID] | None = None,
        status: AssignmentStatus | None = None,
        statuses: list[AssignmentStatus] | None = None,
        created_by_user_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Assignment], int]:
        # An EMPTY syllabus_ids list means "scoped to an empty enrolment" — the
        # caller (a student with no enrolled courses) must see NOTHING, never the
        # whole institution. Only `None` means "not scoped".
        if syllabus_ids is not None and not syllabus_ids:
            return [], 0
        filters: list[Any] = []
        if syllabus_id:
            filters.append(Assignment.syllabus_id == syllabus_id)
        if syllabus_ids:
            filters.append(Assignment.syllabus_id.in_(syllabus_ids))
        if status:
            filters.append(Assignment.status == status)
        if statuses:
            filters.append(Assignment.status.in_(statuses))
        if created_by_user_id:
            filters.append(Assignment.created_by_user_id == created_by_user_id)

        count_q = select(func.count()).select_from(Assignment)
        list_q = select(Assignment).order_by(Assignment.created_at.desc())
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        list_q = list_q.offset(offset).limit(limit)

        total = (await db.execute(count_q)).scalar_one()
        items = (await db.execute(list_q)).scalars().all()
        return list(items), total

    @staticmethod
    async def delete(assignment_id: UUID, *, db: AsyncSession) -> None:
        """Hard-delete an assignment row.

        assignment_submissions are removed by their ON DELETE CASCADE FK. Deletion
        is only ever reached for a DRAFT (enforced in the service), which by
        construction has no submissions, no evaluator allocations (created on
        submit) and no notifications (created on publish/submit) — so the row
        delete + cascade is the complete, safe cleanup. There is no rubric table
        in M04 (questions live inline as JSONB on the row)."""
        from sqlalchemy import delete as sa_delete
        await db.execute(sa_delete(Assignment).where(Assignment.id == assignment_id))

    @staticmethod
    async def update(assignment_id: UUID, fields: dict, *, db: AsyncSession) -> Assignment | None:
        obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if obj is None:
            return None
        for k, v in fields.items():
            setattr(obj, k, v)
        obj.updated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def publish(assignment_id: UUID, *, db: AsyncSession) -> Assignment | None:
        obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if obj is None:
            return None
        obj.status = AssignmentStatus.PUBLISHED
        obj.published_at = datetime.utcnow()
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def close(assignment_id: UUID, *, db: AsyncSession) -> Assignment | None:
        obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if obj is None:
            return None
        obj.status = AssignmentStatus.CLOSED
        obj.closed_at = datetime.utcnow()
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def set_status(
        assignment_id: UUID, status: AssignmentStatus, *, db: AsyncSession
    ) -> Assignment | None:
        """Generic status transition (release / archive / restore). The service
        validates which transitions are legal; this only writes the new status."""
        obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if obj is None:
            return None
        obj.status = status
        obj.updated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def active_allocation_id_for_submission(
        submission_id: UUID, *, db: AsyncSession
    ) -> UUID | None:
        """The M09.6 allocation ROW id currently active for this submission, so a
        grade can close it. None when nothing is allocated."""
        from sqlalchemy import select as _select
        from app.modules.m09_paper_admin.assignment_models import (
            ACTIVE_STATUSES,
            EvaluationAssignment,
        )
        from app.modules.m04_assignments.repository import COURSEWORK_TARGET_ENTITY
        row = (
            await db.execute(
                _select(EvaluationAssignment.id).where(
                    EvaluationAssignment.target_entity == COURSEWORK_TARGET_ENTITY,
                    EvaluationAssignment.target_id == submission_id,
                    EvaluationAssignment.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalar_one_or_none()
        return row

    @staticmethod
    async def active_evaluator_for_submission(
        submission_id: UUID, *, db: AsyncSession
    ) -> UUID | None:
        """Who the M09.6 assignment engine currently has evaluating this submission.

        Evaluator allocation is not duplicated into m04 — that engine is the one
        ledger for evaluation work, so this reads it. Returns None when nothing is
        allocated yet. Reassignment leaves the superseded row in a non-active
        status, so at most one row can match.
        """
        from app.modules.m09_paper_admin.assignment_models import (
            ACTIVE_STATUSES,
            EvaluationAssignment,
        )
        result = await db.execute(
            select(EvaluationAssignment.evaluator_id).where(
                EvaluationAssignment.target_entity == COURSEWORK_TARGET_ENTITY,
                EvaluationAssignment.target_id == submission_id,
                EvaluationAssignment.status.in_(ACTIVE_STATUSES),
            )
        )
        return result.scalars().first()

    @staticmethod
    async def evaluator_for_student(
        assignment_id: UUID, student_user_id: UUID, *, db: AsyncSession
    ) -> UUID | None:
        """Who is already evaluating this student's work on this assignment.

        A re-attempt is a new submission and so a new unit of work, but it is the
        same student's answer to the same question — it belongs with whoever read
        the first one, not with whoever the rota happens to point at now. Reads the
        M09.6 ledger; m04 keeps no copy.
        """
        from app.modules.m09_paper_admin.assignment_models import EvaluationAssignment

        result = await db.execute(
            select(EvaluationAssignment.evaluator_id)
            .join(
                AssignmentSubmission,
                AssignmentSubmission.id == EvaluationAssignment.target_id,
            )
            .where(
                EvaluationAssignment.target_entity == COURSEWORK_TARGET_ENTITY,
                AssignmentSubmission.assignment_id == assignment_id,
                AssignmentSubmission.student_user_id == student_user_id,
            )
            .order_by(EvaluationAssignment.assigned_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    async def submit_for_evaluation(
        assignment_id: UUID, *, actor_user_id: UUID, db: AsyncSession
    ) -> Assignment | None:
        obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if obj is None:
            return None
        obj.status = AssignmentStatus.SUBMITTED
        obj.submitted_at = datetime.utcnow()
        obj.submitted_by_user_id = actor_user_id
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def finalize(
        assignment_id: UUID, *, actor_user_id: UUID, db: AsyncSession
    ) -> Assignment | None:
        obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if obj is None:
            return None
        obj.status = AssignmentStatus.FINALIZED
        obj.finalized_at = datetime.utcnow()
        obj.finalized_by_user_id = actor_user_id
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def enrolled_section_ids_for_syllabus(
        syllabus_id: UUID, *, db: AsyncSession
    ) -> list[UUID]:
        """Resolve section_ids whose students are enrolled in this syllabus's course.

        Join: syllabi -> course_id -> subject_assignments (active) -> section_id.
        """
        rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT sa.section_id "
                    "FROM syllabi s "
                    "JOIN subject_assignments sa ON sa.course_id = s.course_id "
                    "WHERE s.id = :sid AND sa.is_active = true AND sa.section_id IS NOT NULL"
                ),
                {"sid": str(syllabus_id)},
            )
        ).fetchall()
        return [r[0] for r in rows]

    @staticmethod
    async def teaching_courses_for_faculty(
        faculty_user_id: UUID, *, db: AsyncSession
    ) -> list[dict]:
        """The faculty's own teaching courses with the latest approved syllabus
        resolved for each.

        subject_assignments(active) -> courses, and per course the newest
        LOCKED/APPROVED syllabus (the same rule the exam module and the units
        guard use). syllabus_id is NULL when the course has no approved syllabus
        yet — the caller blocks creation for those with a clear message. Scoped to
        the faculty's own load, so the picker never lists institution-wide courses.
        """
        rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT "
                    "  c.id AS course_id, c.code AS course_code, c.title AS course_title, "
                    "  c.semester AS semester, sa.section_id AS section_id, "
                    "  sec.name AS section_name, "
                    "  (SELECT s.id FROM syllabi s "
                    "     WHERE s.course_id = c.id AND s.status IN ('LOCKED','APPROVED') "
                    "     ORDER BY s.version DESC LIMIT 1) AS syllabus_id "
                    "FROM subject_assignments sa "
                    "JOIN courses c ON c.id = sa.course_id "
                    "LEFT JOIN acad_sections sec ON sec.id = sa.section_id "
                    "WHERE sa.faculty_user_id = :fid AND sa.is_active = true "
                    "ORDER BY c.code, sec.name"
                ),
                {"fid": str(faculty_user_id)},
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def enrolled_syllabus_ids_for_student(
        student_user_id: UUID, *, db: AsyncSession
    ) -> list[UUID]:
        """The syllabi (courses) a student is actively enrolled in.

        The inverse of enrolled_section_ids_for_syllabus:
        acad_enrollments (active) -> section_id -> subject_assignments (active)
        -> course_id -> syllabi. A student sees coursework ONLY for these.
        """
        rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT syl.id "
                    "FROM acad_enrollments ae "
                    "JOIN subject_assignments sa "
                    "  ON sa.section_id = ae.section_id AND sa.is_active = true "
                    "JOIN syllabi syl ON syl.course_id = sa.course_id "
                    "WHERE ae.student_id = :uid AND ae.is_active = true"
                ),
                {"uid": str(student_user_id)},
            )
        ).fetchall()
        return [r[0] for r in rows]

    @staticmethod
    async def evaluation_roster(
        assignment_id: UUID, syllabus_id: UUID | None, *, db: AsyncSession
    ) -> list[dict]:
        """Every actively-enrolled student for the assignment's course, LEFT
        JOINed to their latest submission attempt. A student who has NOT submitted
        still appears (submission_* columns NULL) — that is what lets the
        Evaluation Center show "pending submission" and keep the whole class in
        view. Section set is derived once via a subquery so multiple active
        subject_assignments on the same course/section don't multiply students.
        """
        if syllabus_id is None:
            return []
        rows = (
            await db.execute(
                text(
                    """
                    SELECT ae.student_id       AS student_user_id,
                           u.full_name         AS student_name,
                           sub.id              AS submission_id,
                           sub.status          AS submission_status,
                           sub.is_late         AS is_late,
                           sub.submitted_at    AS submitted_at,
                           sub.marks_obtained  AS marks_obtained,
                           sub.graded_at       AS graded_at,
                           aiev.status         AS ai_status
                    FROM acad_enrollments ae
                    JOIN users u ON u.id = ae.student_id
                    LEFT JOIN LATERAL (
                        SELECT s.id, s.status, s.is_late, s.submitted_at,
                               s.marks_obtained, s.graded_at
                        FROM assignment_submissions s
                        WHERE s.assignment_id = :aid
                          AND s.student_user_id = ae.student_id
                        ORDER BY s.attempt_number DESC
                        LIMIT 1
                    ) sub ON true
                    -- Advisory AI state for that attempt, if the worker has run.
                    LEFT JOIN assignment_evaluations aiev ON aiev.submission_id = sub.id
                    WHERE ae.is_active = true
                      AND ae.section_id IN (
                          SELECT sa.section_id
                          FROM syllabi syl
                          JOIN subject_assignments sa
                            ON sa.course_id = syl.course_id AND sa.is_active = true
                          WHERE syl.id = :sid
                      )
                    ORDER BY u.full_name NULLS LAST
                    """
                ),
                {"aid": str(assignment_id), "sid": str(syllabus_id)},
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def enrolled_student_count_for_syllabus(
        syllabus_id: UUID, *, db: AsyncSession
    ) -> int:
        row = (
            await db.execute(
                text(
                    "SELECT COUNT(DISTINCT ae.student_id) "
                    "FROM syllabi s "
                    "JOIN subject_assignments sa ON sa.course_id = s.course_id "
                    "JOIN acad_enrollments ae ON ae.section_id = sa.section_id AND ae.is_active = true "
                    "WHERE s.id = :sid AND sa.is_active = true"
                ),
                {"sid": str(syllabus_id)},
            )
        ).one_or_none()
        return int(row[0]) if row else 0


class SubmissionRepository:

    @staticmethod
    async def create(
        *,
        assignment_id: UUID,
        student_user_id: UUID,
        attempt_number: int,
        content_text: str | None,
        content_url: str | None,
        is_late: bool,
        db: AsyncSession,
    ) -> AssignmentSubmission:
        obj = AssignmentSubmission(
            assignment_id=assignment_id,
            student_user_id=student_user_id,
            attempt_number=attempt_number,
            content_text=content_text,
            content_url=content_url,
            is_late=is_late,
            status=SubmissionStatus.SUBMITTED,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get_by_id(submission_id: UUID, *, db: AsyncSession) -> AssignmentSubmission | None:
        result = await db.execute(
            select(AssignmentSubmission).where(AssignmentSubmission.id == submission_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def count_student_attempts(
        assignment_id: UUID, student_user_id: UUID, *, db: AsyncSession
    ) -> int:
        result = await db.execute(
            select(func.count()).select_from(AssignmentSubmission).where(
                AssignmentSubmission.assignment_id == assignment_id,
                AssignmentSubmission.student_user_id == student_user_id,
            )
        )
        return result.scalar_one()

    @staticmethod
    async def count_distinct_students(
        assignment_id: UUID, *, db: AsyncSession
    ) -> int:
        """How many students have submitted anything at all.

        This is a student's position in the evaluator rota. It counts STUDENTS,
        not submissions, so a re-attempt cannot shift the rota by one — and a
        re-attempt does not consult it anyway (see `evaluator_for_student`).
        """
        result = await db.execute(
            select(func.count(func.distinct(AssignmentSubmission.student_user_id)))
            .where(AssignmentSubmission.assignment_id == assignment_id)
        )
        return result.scalar_one()

    @staticmethod
    async def list_for_assignment(
        assignment_id: UUID, *, db: AsyncSession, offset: int = 0, limit: int = 100
    ) -> tuple[list[AssignmentSubmission], int]:
        count_q = select(func.count()).select_from(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment_id
        )
        list_q = (
            select(AssignmentSubmission)
            .where(AssignmentSubmission.assignment_id == assignment_id)
            .order_by(AssignmentSubmission.submitted_at.desc())
            .offset(offset)
            .limit(limit)
        )
        total = (await db.execute(count_q)).scalar_one()
        items = (await db.execute(list_q)).scalars().all()
        return list(items), total

    @staticmethod
    async def list_allocated_to(
        assignment_id: UUID,
        evaluator_id: UUID,
        *,
        db: AsyncSession,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[AssignmentSubmission], int]:
        """This assignment's submissions that are allocated to one evaluator.

        Scopes an evaluator to the work actually handed to them. Reads the M09.6
        ledger rather than any copy of it.
        """
        from app.modules.m09_paper_admin.assignment_models import (
            ACTIVE_STATUSES,
            EvaluationAssignment,
        )

        allocated = select(EvaluationAssignment.target_id).where(
            EvaluationAssignment.target_entity == COURSEWORK_TARGET_ENTITY,
            EvaluationAssignment.evaluator_id == evaluator_id,
            EvaluationAssignment.status.in_(ACTIVE_STATUSES),
        )
        where = (
            AssignmentSubmission.assignment_id == assignment_id,
            AssignmentSubmission.id.in_(allocated),
        )
        count_q = select(func.count()).select_from(AssignmentSubmission).where(*where)
        list_q = (
            select(AssignmentSubmission)
            .where(*where)
            .order_by(AssignmentSubmission.submitted_at.desc())
            .offset(offset)
            .limit(limit)
        )
        total = (await db.execute(count_q)).scalar_one()
        items = (await db.execute(list_q)).scalars().all()
        return list(items), total

    @staticmethod
    async def list_for_student(
        student_user_id: UUID,
        *,
        db: AsyncSession,
        syllabus_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AssignmentSubmission], int]:
        q = select(AssignmentSubmission).where(
            AssignmentSubmission.student_user_id == student_user_id
        )
        count_q = select(func.count()).select_from(AssignmentSubmission).where(
            AssignmentSubmission.student_user_id == student_user_id
        )
        if syllabus_id:
            q = q.join(Assignment, Assignment.id == AssignmentSubmission.assignment_id).where(
                Assignment.syllabus_id == syllabus_id
            )
            count_q = count_q.join(
                Assignment, Assignment.id == AssignmentSubmission.assignment_id
            ).where(Assignment.syllabus_id == syllabus_id)
        q = q.order_by(AssignmentSubmission.submitted_at.desc()).offset(offset).limit(limit)

        total = (await db.execute(count_q)).scalar_one()
        items = (await db.execute(q)).scalars().all()
        return list(items), total

    @staticmethod
    async def grade(
        submission_id: UUID,
        *,
        marks_obtained: float,
        feedback: str | None,
        graded_by_user_id: UUID,
        is_evaluator_recommendation: bool = False,
        db: AsyncSession,
    ) -> AssignmentSubmission | None:
        """Record a grade on a submission.

        `marks_obtained` / `feedback` are the AUTHORITATIVE final grade and are
        written every time. When an EVALUATOR saves, the same values are ALSO
        copied into the evaluator_* columns — their recommendation, preserved
        permanently. The faculty owner's review never writes those columns, so
        adjusting a mark can no longer destroy what the evaluator recommended.
        """
        obj = await SubmissionRepository.get_by_id(submission_id, db=db)
        if obj is None:
            return None
        if is_evaluator_recommendation:
            obj.evaluator_marks_obtained = marks_obtained
            obj.evaluator_feedback = feedback
        obj.marks_obtained = marks_obtained
        obj.feedback = feedback
        obj.graded_by_user_id = graded_by_user_id
        obj.graded_at = datetime.utcnow()
        obj.status = SubmissionStatus.GRADED
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def mark_returned(submission_id: UUID, *, db: AsyncSession) -> AssignmentSubmission | None:
        obj = await SubmissionRepository.get_by_id(submission_id, db=db)
        if obj is None:
            return None
        obj.status = SubmissionStatus.RETURNED
        obj.returned_at = datetime.utcnow()
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def count_ungraded(assignment_id: UUID, *, db: AsyncSession) -> int:
        """Submissions still carrying no mark. Guards mark finalization."""
        result = await db.execute(
            select(func.count())
            .select_from(AssignmentSubmission)
            .where(
                AssignmentSubmission.assignment_id == assignment_id,
                AssignmentSubmission.marks_obtained.is_(None),
            )
        )
        return int(result.scalar() or 0)

    @staticmethod
    async def statistics(assignment_id: UUID, *, db: AsyncSession) -> dict:
        rows = (
            await db.execute(
                select(AssignmentSubmission).where(
                    AssignmentSubmission.assignment_id == assignment_id
                )
            )
        ).scalars().all()
        submitted = len(rows)
        graded = [r for r in rows if r.marks_obtained is not None]
        late = sum(1 for r in rows if r.is_late)
        avg = (
            sum(float(r.marks_obtained) for r in graded) / len(graded)
            if graded
            else None
        )
        ai = await SubmissionRepository.ai_progress(assignment_id, db=db)
        return {
            "submitted_count": submitted,
            "graded_count": len(graded),
            "late_count": late,
            "average_marks": round(avg, 2) if avg is not None else None,
            **ai,
        }

    @staticmethod
    async def ai_progress(assignment_id: UUID, *, db: AsyncSession) -> dict:
        """AI-evaluation and evaluator-allocation counts for one assignment.

        Derived on read from assignment_evaluations and the M09.6 ledger — the
        owning faculty needs to see how far the pipeline has got, and a stored
        counter on `assignments` would be a second source of truth that drifts
        the moment a worker retries or the department reallocates.
        """
        rows = (
            await db.execute(
                select(AssignmentEvaluation.status, func.count())
                .join(
                    AssignmentSubmission,
                    AssignmentSubmission.id == AssignmentEvaluation.submission_id,
                )
                .where(AssignmentSubmission.assignment_id == assignment_id)
                .group_by(AssignmentEvaluation.status)
            )
        ).all()
        by_status = {str(getattr(s, "value", s)): n for s, n in rows}
        in_progress = (
            by_status.get(AIEvalStatus.PENDING.value, 0)
            + by_status.get(AIEvalStatus.EXTRACTING.value, 0)
            + by_status.get(AIEvalStatus.EVALUATING.value, 0)
        )

        from app.modules.m09_paper_admin.assignment_models import (
            ACTIVE_STATUSES,
            EvaluationAssignment,
        )
        evaluator_assigned = (
            await db.execute(
                select(func.count(func.distinct(EvaluationAssignment.target_id)))
                .select_from(EvaluationAssignment)
                .join(
                    AssignmentSubmission,
                    AssignmentSubmission.id == EvaluationAssignment.target_id,
                )
                .where(
                    EvaluationAssignment.target_entity == COURSEWORK_TARGET_ENTITY,
                    EvaluationAssignment.status.in_(ACTIVE_STATUSES),
                    AssignmentSubmission.assignment_id == assignment_id,
                )
            )
        ).scalar() or 0

        return {
            "ai_completed_count":       by_status.get(AIEvalStatus.COMPLETED.value, 0),
            "ai_failed_count":          by_status.get(AIEvalStatus.FAILED.value, 0),
            "ai_pending_count":         in_progress,
            "evaluator_assigned_count": int(evaluator_assigned),
        }

    @staticmethod
    async def progress_for_assignments(
        assignment_ids: list[UUID], *, db: AsyncSession
    ) -> dict[UUID, dict]:
        """Per-assignment progress for a LIST of assignments, in three grouped
        queries rather than one pair per row — the faculty dashboard renders this
        for every assignment it shows, so an N+1 here is the whole page.

        Every count is derived from the existing tables; nothing is stored.
        """
        if not assignment_ids:
            return {}

        base = {
            "submitted_count": 0, "graded_count": 0, "late_count": 0,
            "ai_completed_count": 0, "ai_failed_count": 0, "ai_pending_count": 0,
            "evaluator_assigned_count": 0,
        }
        out: dict[UUID, dict] = {aid: dict(base) for aid in assignment_ids}

        # 1. Submission counts.
        sub_rows = (
            await db.execute(
                select(
                    AssignmentSubmission.assignment_id,
                    func.count(),
                    func.count(AssignmentSubmission.marks_obtained),
                    func.count().filter(AssignmentSubmission.is_late.is_(True)),
                )
                .where(AssignmentSubmission.assignment_id.in_(assignment_ids))
                .group_by(AssignmentSubmission.assignment_id)
            )
        ).all()
        for aid, total, graded, late in sub_rows:
            out[aid].update(
                submitted_count=total, graded_count=graded, late_count=late
            )

        # 2. AI evaluation states.
        ai_rows = (
            await db.execute(
                select(
                    AssignmentSubmission.assignment_id,
                    AssignmentEvaluation.status,
                    func.count(),
                )
                .join(
                    AssignmentSubmission,
                    AssignmentSubmission.id == AssignmentEvaluation.submission_id,
                )
                .where(AssignmentSubmission.assignment_id.in_(assignment_ids))
                .group_by(AssignmentSubmission.assignment_id, AssignmentEvaluation.status)
            )
        ).all()
        _in_progress = {
            AIEvalStatus.PENDING.value,
            AIEvalStatus.EXTRACTING.value,
            AIEvalStatus.EVALUATING.value,
        }
        for aid, status, n in ai_rows:
            key = str(getattr(status, "value", status))
            if key == AIEvalStatus.COMPLETED.value:
                out[aid]["ai_completed_count"] += n
            elif key == AIEvalStatus.FAILED.value:
                out[aid]["ai_failed_count"] += n
            elif key in _in_progress:
                out[aid]["ai_pending_count"] += n

        # 3. Evaluator allocations, read from the M09.6 ledger (never copied here).
        from app.modules.m09_paper_admin.assignment_models import (
            ACTIVE_STATUSES,
            EvaluationAssignment,
        )
        alloc_rows = (
            await db.execute(
                select(
                    AssignmentSubmission.assignment_id,
                    func.count(func.distinct(EvaluationAssignment.target_id)),
                )
                .select_from(EvaluationAssignment)
                .join(
                    AssignmentSubmission,
                    AssignmentSubmission.id == EvaluationAssignment.target_id,
                )
                .where(
                    EvaluationAssignment.target_entity == COURSEWORK_TARGET_ENTITY,
                    EvaluationAssignment.status.in_(ACTIVE_STATUSES),
                    AssignmentSubmission.assignment_id.in_(assignment_ids),
                )
                .group_by(AssignmentSubmission.assignment_id)
            )
        ).all()
        for aid, n in alloc_rows:
            out[aid]["evaluator_assigned_count"] = int(n)

        return out


class AiEvaluationRepository:
    """CRUD for the advisory AI evaluation of a submission. One row per
    submission (unique). Never touches assignment_submissions."""

    @staticmethod
    async def get_by_submission(
        submission_id: UUID, *, db: AsyncSession
    ) -> AssignmentEvaluation | None:
        return (
            await db.execute(
                select(AssignmentEvaluation).where(
                    AssignmentEvaluation.submission_id == submission_id
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def status_by_submissions(
        submission_ids: list[UUID], *, db: AsyncSession
    ) -> dict[UUID, str]:
        """{submission_id: ai_status} for a page of submissions, in one query.

        Only the status — the heavy JSONB columns stay behind the per-submission
        detail endpoint. A submission with no row is simply absent from the map.
        """
        if not submission_ids:
            return {}
        rows = (
            await db.execute(
                select(
                    AssignmentEvaluation.submission_id, AssignmentEvaluation.status
                ).where(AssignmentEvaluation.submission_id.in_(submission_ids))
            )
        ).all()
        return {sid: str(getattr(st, "value", st)) for sid, st in rows}

    @staticmethod
    async def upsert_pending(
        submission_id: UUID, *, db: AsyncSession
    ) -> AssignmentEvaluation:
        """Create the row (or reset an existing one) to PENDING for a (re)run.
        Bumps retry_count and clears the previous error so a retry starts clean."""
        row = await AiEvaluationRepository.get_by_submission(submission_id, db=db)
        if row is None:
            row = AssignmentEvaluation(
                submission_id=submission_id, status=AIEvalStatus.PENDING
            )
            db.add(row)
        else:
            row.status = AIEvalStatus.PENDING
            row.error_log = None
            row.retry_count = (row.retry_count or 0) + 1
        await db.flush()
        return row

    @staticmethod
    async def set_status(
        submission_id: UUID, status: AIEvalStatus, *, db: AsyncSession,
        error_log: str | None = None,
    ) -> None:
        row = await AiEvaluationRepository.get_by_submission(submission_id, db=db)
        if row is None:
            return
        row.status = status
        if error_log is not None:
            row.error_log = error_log[:4000]
        await db.flush()

    @staticmethod
    async def save_extraction(
        submission_id: UUID, *, text_value: str, word_count: int,
        file_type: str | None, db: AsyncSession,
    ) -> None:
        row = await AiEvaluationRepository.get_by_submission(submission_id, db=db)
        if row is None:
            return
        row.extracted_text = text_value
        row.word_count = word_count
        row.file_type = file_type
        await db.flush()

    @staticmethod
    async def save_results(
        submission_id: UUID, *, results: dict, similarity_score: float | None,
        similarity_matches: list | None, processing_ms: int, db: AsyncSession,
    ) -> None:
        row = await AiEvaluationRepository.get_by_submission(submission_id, db=db)
        if row is None:
            return
        row.suggested_marks = results.get("suggested_marks")
        row.overall_suggested_marks = results.get("overall_suggested_marks")
        row.percentage = results.get("percentage")
        row.confidence_level = results.get("confidence_level")
        row.feedback = results.get("feedback")
        row.rubric_scores = results.get("rubric_scores")
        row.bloom_analysis = results.get("bloom_analysis")
        row.co_analysis = results.get("co_analysis")
        row.similarity_score = similarity_score
        row.similarity_matches = similarity_matches
        row.ai_model = results.get("ai_model")
        row.provider_used = results.get("provider_used")
        row.fallback_chain = results.get("fallback_chain")
        row.prompt_hash = results.get("prompt_hash")
        row.processing_ms = processing_ms
        row.status = AIEvalStatus.COMPLETED
        await db.flush()

    @staticmethod
    async def cohort_texts(
        assignment_id: UUID, exclude_submission_id: UUID, *, db: AsyncSession
    ) -> list[tuple[UUID, str]]:
        """(submission_id, extracted_text) for OTHER submissions of the same
        assignment that already have extracted text — the internal-similarity
        cohort. External sources are never consulted."""
        rows = (
            await db.execute(
                select(
                    AssignmentEvaluation.submission_id,
                    AssignmentEvaluation.extracted_text,
                )
                .join(
                    AssignmentSubmission,
                    AssignmentSubmission.id == AssignmentEvaluation.submission_id,
                )
                .where(
                    AssignmentSubmission.assignment_id == assignment_id,
                    AssignmentEvaluation.submission_id != exclude_submission_id,
                    AssignmentEvaluation.extracted_text.isnot(None),
                )
            )
        ).all()
        return [(r[0], r[1]) for r in rows if r[1]]
