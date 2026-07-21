"""
M08 Exam Setter — Repository layer.

All queries use the tenant search_path set on the session.
No cross-tenant queries. No raw SQL strings beyond SET search_path (done by caller).

TaskJobPublicRepository operates on the public schema (public.task_jobs)
and requires a session from AsyncSessionLocal() (not the tenant session).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

logger = logging.getLogger("vidya.repo.m08")

from sqlalchemy import select, update as sa_update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m08_exam_setter.models import (
    BloomsComplianceReport,
    ExamPaper,
    ExamPaperStatus,
    ExamQuestion,
    ExamWorkflow,
    InternalMarkStatus,
    InternalMarksSummary,
    QuestionBankEntry,
)


# ---------------------------------------------------------------------------
# ExamPaperRepository
# ---------------------------------------------------------------------------

class ExamPaperRepository:

    @staticmethod
    async def create(
        *,
        course_id: UUID,
        created_by: UUID,
        title: str,
        exam_type: str,
        exam_workflow: str = ExamWorkflow.BOARD_EXAM.value,
        total_marks: int,
        duration_mins: int,
        units_included: list,
        question_format: dict,
        requested_dist: dict,
        section_config: list | None = None,
        blueprint: list | None = None,
        template_type: str | None = None,
        template_definition: dict | None = None,
        special_instructions: str | None,
        creation_mode: str = "AI",
        db: AsyncSession,
    ) -> ExamPaper:
        paper = ExamPaper(
            course_id=course_id,
            created_by=created_by,
            title=title,
            exam_type=exam_type,
            exam_workflow=exam_workflow,
            total_marks=total_marks,
            duration_mins=duration_mins,
            units_included=units_included,
            question_format=question_format,
            requested_dist=requested_dist,
            section_config=section_config,
            blueprint=blueprint,
            template_type=template_type,
            template_definition=template_definition,
            special_instructions=special_instructions,
            creation_mode=creation_mode,
            status=ExamPaperStatus.DRAFT.value,
        )
        db.add(paper)
        await db.flush()
        return paper

    @staticmethod
    async def get_by_id(paper_id: UUID, *, db: AsyncSession) -> ExamPaper | None:
        result = await db.execute(
            select(ExamPaper).where(ExamPaper.id == paper_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_faculty(
        created_by: UUID,
        *,
        status: str | None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ) -> list[ExamPaper]:
        q = select(ExamPaper).where(ExamPaper.created_by == created_by)
        if status:
            q = q.where(ExamPaper.status == status)
        q = q.order_by(ExamPaper.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def list_board_pending(
        *,
        offset: int,
        limit: int,
        db: AsyncSession,
    ) -> list[ExamPaper]:
        """SEMESTER (BOARD_EXAM) papers awaiting Board review. Internal papers go
        to the Dean queue instead."""
        q = (
            select(ExamPaper)
            .where(ExamPaper.status == ExamPaperStatus.SUBMITTED.value)
            .where(ExamPaper.exam_workflow == ExamWorkflow.BOARD_EXAM.value)
            .order_by(ExamPaper.submitted_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def list_dean_pending(
        *,
        course_ids: list[UUID] | None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ) -> list[ExamPaper]:
        """INTERNAL papers awaiting Dean review. When course_ids is not None the
        result is restricted to that set (department scoping); None = unrestricted
        (ADMIN)."""
        q = (
            select(ExamPaper)
            .where(ExamPaper.status == ExamPaperStatus.SUBMITTED.value)
            .where(ExamPaper.exam_workflow == ExamWorkflow.INTERNAL.value)
        )
        if course_ids is not None:
            if not course_ids:
                return []
            q = q.where(ExamPaper.course_id.in_(course_ids))
        q = q.order_by(ExamPaper.submitted_at.asc()).offset(offset).limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def list_all(
        *,
        status: str | None,
        workflow: str | None = None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ) -> list[ExamPaper]:
        """Admin / Dean: all papers for the tenant. When ``workflow`` is given the
        result is restricted to that workflow — the Board passes BOARD_EXAM so it
        never sees INTERNAL papers (workflow isolation)."""
        q = select(ExamPaper)
        if status:
            q = q.where(ExamPaper.status == status)
        if workflow:
            q = q.where(ExamPaper.exam_workflow == workflow)
        q = q.order_by(ExamPaper.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def set_status(
        paper_id: UUID,
        status: str,
        *,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(ExamPaper)
            .where(ExamPaper.id == paper_id)
            .values(status=status, updated_at=datetime.now(timezone.utc))
        )

    @staticmethod
    async def set_failed(
        paper_id: UUID,
        *,
        reason: str,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(ExamPaper)
            .where(ExamPaper.id == paper_id)
            .values(
                status=ExamPaperStatus.FAILED.value,
                failure_reason=reason,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def delete(paper_id: UUID, *, db: AsyncSession) -> None:
        """Delete the paper row. A Core DELETE lets Postgres apply the ON DELETE
        CASCADE on exam_questions and blooms_compliance_reports directly, rather
        than SQLAlchemy trying to manage those relationships in Python."""
        from sqlalchemy import delete as sa_delete
        await db.execute(
            sa_delete(ExamPaper).where(ExamPaper.id == paper_id)
        )

    @staticmethod
    async def set_generation_result(
        paper_id: UUID,
        *,
        ai_model: str,
        prompt_hash: str,
        actual_dist: dict,
        co_coverage_report: list | None = None,
        unit_coverage_report: list | None = None,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(ExamPaper)
            .where(ExamPaper.id == paper_id)
            .values(
                ai_model=ai_model,
                prompt_hash=prompt_hash,
                actual_dist=actual_dist,
                co_coverage_report=co_coverage_report,
                unit_coverage_report=unit_coverage_report,
                status=ExamPaperStatus.GENERATED.value,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_generation_job(
        paper_id: UUID,
        *,
        job_id: UUID,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(ExamPaper)
            .where(ExamPaper.id == paper_id)
            .values(
                generation_job_id=job_id,
                status=ExamPaperStatus.GENERATING.value,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_submitted(paper_id: UUID, *, db: AsyncSession) -> None:
        await db.execute(
            sa_update(ExamPaper)
            .where(ExamPaper.id == paper_id)
            .values(
                status=ExamPaperStatus.SUBMITTED.value,
                submitted_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_board_decision(
        paper_id: UUID,
        *,
        approved: bool,
        approved_by: UUID,
        board_comment: str | None,
        db: AsyncSession,
    ) -> None:
        new_status = (
            ExamPaperStatus.BOARD_APPROVED.value
            if approved
            else ExamPaperStatus.BOARD_RETURNED.value
        )
        values: dict = {
            "status":        new_status,
            "approved_by":   approved_by,
            "board_comment": board_comment,
            "updated_at":    datetime.now(timezone.utc),
        }
        if approved:
            values["approved_at"] = datetime.now(timezone.utc)
        await db.execute(sa_update(ExamPaper).where(ExamPaper.id == paper_id).values(**values))

    @staticmethod
    async def set_sealed(
        paper_id: UUID,
        *,
        release_at: datetime,
        encrypted_blob_key: str,
        encryption_key_ref: str,
        release_job_id: UUID,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(ExamPaper)
            .where(ExamPaper.id == paper_id)
            .values(
                status=ExamPaperStatus.SEALED.value,
                sealed_at=datetime.now(timezone.utc),
                release_at=release_at,
                encrypted_blob_key=encrypted_blob_key,
                encryption_key_ref=encryption_key_ref,
                release_job_id=release_job_id,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_released(paper_id: UUID, *, db: AsyncSession) -> None:
        await db.execute(
            sa_update(ExamPaper)
            .where(ExamPaper.id == paper_id)
            .values(
                status=ExamPaperStatus.RELEASED.value,
                released_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_faculty_approved(
        paper_id: UUID,
        *,
        approved_by: UUID,
        board_comment: str | None,
        db: AsyncSession,
    ) -> None:
        """INTERNAL workflow: faculty self-approval sets BOARD_APPROVED, skipping Board review."""
        await db.execute(
            sa_update(ExamPaper)
            .where(ExamPaper.id == paper_id)
            .values(
                status=ExamPaperStatus.BOARD_APPROVED.value,
                approved_by=approved_by,
                approved_at=datetime.now(timezone.utc),
                board_comment=board_comment,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_scrutinizer(
        paper_id: UUID,
        *,
        scrutinizer_id: UUID,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(ExamPaper)
            .where(ExamPaper.id == paper_id)
            .values(
                scrutinizer_id=scrutinizer_id,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_scrutinized(
        paper_id: UUID,
        *,
        comment: str | None,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(ExamPaper)
            .where(ExamPaper.id == paper_id)
            .values(
                scrutinized_at=datetime.now(timezone.utc),
                scrutinizer_comment=comment,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_section_config(
        paper_id: UUID,
        *,
        section_config: list,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(ExamPaper)
            .where(ExamPaper.id == paper_id)
            .values(
                section_config=section_config,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def list_by_workflow(
        workflow: str,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[ExamPaper]:
        q = select(ExamPaper).where(ExamPaper.exam_workflow == workflow)
        if status:
            q = q.where(ExamPaper.status == status)
        q = q.order_by(ExamPaper.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# ExamQuestionRepository
# ---------------------------------------------------------------------------

class ExamQuestionRepository:

    @staticmethod
    async def bulk_create(
        questions: list[dict],
        *,
        exam_paper_id: UUID,
        db: AsyncSession,
    ) -> list[ExamQuestion]:
        objs = []
        for idx, q in enumerate(questions):
            obj = ExamQuestion(
                exam_paper_id=exam_paper_id,
                unit_number=q["unit_number"],
                co_code=q.get("co_code"),
                bloom_level=(q["bloom_level"] or "REMEMBER").upper().strip(),
                question_type=(q["question_type"] or "SHORT_ANSWER").upper().replace(" ", "_").strip(),
                question_text=q["question_text"],
                options=q.get("options"),
                correct_option=q.get("correct_option"),
                marks=q["marks"],
                model_answer=q.get("model_answer"),
                marking_scheme=q.get("marking_scheme"),
                set_membership=q.get("set_membership", ["A", "B"]),
                section_label=q.get("section_label"),
                choice_group=q.get("choice_group"),
                co_ids=q.get("co_ids") or [],
                ai_generated=True,
                is_edited=False,
                display_order=idx,
                template_block_id=q.get("template_block_id"),
                template_subpart_index=q.get("template_subpart_index"),
                unit_numbers=q.get("unit_numbers"),
                difficulty=q.get("difficulty"),
            )
            db.add(obj)
            objs.append(obj)
        await db.flush()
        return objs

    @staticmethod
    async def add_one(
        exam_paper_id: UUID,
        *,
        data: dict,
        display_order: int,
        db: AsyncSession,
    ) -> ExamQuestion:
        """Add a single hand-written question (manual builder)."""
        obj = ExamQuestion(
            exam_paper_id=exam_paper_id,
            unit_number=data.get("unit_number", 1),
            co_code=data.get("co_code"),
            bloom_level=(data.get("bloom_level") or "REMEMBER").upper().strip(),
            question_type=(data.get("question_type") or "SHORT_ANSWER").upper().replace(" ", "_").strip(),
            question_text=data["question_text"],
            options=data.get("options"),
            correct_option=data.get("correct_option"),
            marks=data["marks"],
            model_answer=data.get("model_answer"),
            marking_scheme=data.get("marking_scheme"),
            set_membership=data.get("set_membership") or ["A", "B"],
            section_label=data.get("section_label"),
            co_ids=data.get("co_ids") or [],
            ai_generated=False,
            is_edited=False,
            display_order=display_order,
            template_block_id=data.get("template_block_id"),
            template_subpart_index=data.get("template_subpart_index"),
            unit_numbers=data.get("unit_numbers"),
            difficulty=data.get("difficulty"),
        )
        db.add(obj)
        await db.flush()
        return obj

    @staticmethod
    async def copy_question(
        source: ExamQuestion,
        *,
        display_order: int,
        db: AsyncSession,
    ) -> ExamQuestion:
        """Duplicate an existing question (all content columns) into the same
        paper. The copy is treated as a manual artifact (ai_generated=False)."""
        obj = ExamQuestion(
            exam_paper_id=source.exam_paper_id,
            unit_number=source.unit_number,
            co_code=source.co_code,
            bloom_level=source.bloom_level,
            question_type=source.question_type,
            question_text=source.question_text,
            options=source.options,
            correct_option=source.correct_option,
            marks=source.marks,
            model_answer=source.model_answer,
            marking_scheme=source.marking_scheme,
            set_membership=source.set_membership or ["A", "B"],
            section_label=source.section_label,
            choice_group=source.choice_group,
            co_ids=source.co_ids or [],
            ai_generated=False,
            is_edited=False,
            display_order=display_order,
            # The copy belongs to the same template block as its source, so it
            # prints alongside it instead of ending up unplaceable.
            template_block_id=source.template_block_id,
            template_subpart_index=source.template_subpart_index,
            unit_numbers=source.unit_numbers,
            difficulty=source.difficulty,
        )
        db.add(obj)
        await db.flush()
        return obj

    @staticmethod
    async def max_display_order(exam_paper_id: UUID, *, db: AsyncSession) -> int:
        from sqlalchemy import func
        result = await db.execute(
            select(func.max(ExamQuestion.display_order)).where(
                ExamQuestion.exam_paper_id == exam_paper_id
            )
        )
        return int(result.scalar() or -1)

    @staticmethod
    async def set_display_orders(order_map: dict[UUID, int], *, db: AsyncSession) -> None:
        for qid, order in order_map.items():
            await db.execute(
                sa_update(ExamQuestion).where(ExamQuestion.id == qid).values(display_order=order)
            )

    @staticmethod
    async def list_by_paper(
        exam_paper_id: UUID,
        *,
        set_label: str | None = None,
        db: AsyncSession,
    ) -> list[ExamQuestion]:
        q = (
            select(ExamQuestion)
            .where(ExamQuestion.exam_paper_id == exam_paper_id)
            .order_by(ExamQuestion.display_order, ExamQuestion.created_at)
        )
        result = await db.execute(q)
        rows = list(result.scalars().all())
        logger.debug(
            "list_by_paper paper=%s total_rows=%d set_label=%r",
            exam_paper_id, len(rows), set_label,
        )
        if set_label:
            filtered = [r for r in rows if set_label in (r.set_membership or [])]
            logger.debug(
                "list_by_paper after set_label=%r filter: %d/%d rows pass; "
                "sample memberships=%r",
                set_label, len(filtered), len(rows),
                [r.set_membership for r in rows[:3]],
            )
            return filtered
        return rows

    @staticmethod
    async def get_by_id(
        question_id: UUID,
        *,
        db: AsyncSession,
    ) -> ExamQuestion | None:
        result = await db.execute(
            select(ExamQuestion).where(ExamQuestion.id == question_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_question(
        question_id: UUID,
        *,
        updates: dict,
        db: AsyncSession,
    ) -> None:
        if "bloom_level" in updates and updates["bloom_level"]:
            updates["bloom_level"] = updates["bloom_level"].upper().strip()
        if "question_type" in updates and updates["question_type"]:
            updates["question_type"] = updates["question_type"].upper().replace(" ", "_").strip()
        updates["is_edited"] = True
        updates["updated_at"] = datetime.now(timezone.utc)
        await db.execute(
            sa_update(ExamQuestion)
            .where(ExamQuestion.id == question_id)
            .values(**updates)
        )

    @staticmethod
    async def delete(question_id: UUID, *, db: AsyncSession) -> None:
        from sqlalchemy import delete as sa_delete
        await db.execute(
            sa_delete(ExamQuestion).where(ExamQuestion.id == question_id)
        )


# ---------------------------------------------------------------------------
# BloomsRepository
# ---------------------------------------------------------------------------

class BloomsRepository:

    @staticmethod
    async def upsert(
        exam_paper_id: UUID,
        *,
        requested_dist: dict,
        actual_dist: dict,
        compliance_ok: bool,
        violations: list,
        co_coverage_ok: bool = False,
        unit_coverage_ok: bool = False,
        db: AsyncSession,
    ) -> BloomsComplianceReport:
        existing = await db.execute(
            select(BloomsComplianceReport).where(
                BloomsComplianceReport.exam_paper_id == exam_paper_id
            )
        )
        report = existing.scalar_one_or_none()
        if report is None:
            report = BloomsComplianceReport(
                exam_paper_id=exam_paper_id,
                requested_dist=requested_dist,
                actual_dist=actual_dist,
                compliance_ok=compliance_ok,
                violations=violations,
                co_coverage_ok=co_coverage_ok,
                unit_coverage_ok=unit_coverage_ok,
            )
            db.add(report)
        else:
            report.requested_dist  = requested_dist
            report.actual_dist     = actual_dist
            report.compliance_ok   = compliance_ok
            report.violations      = violations
            report.co_coverage_ok  = co_coverage_ok
            report.unit_coverage_ok = unit_coverage_ok
            report.generated_at    = datetime.now(timezone.utc)
        await db.flush()
        return report

    @staticmethod
    async def get_by_paper(
        exam_paper_id: UUID,
        *,
        db: AsyncSession,
    ) -> BloomsComplianceReport | None:
        result = await db.execute(
            select(BloomsComplianceReport).where(
                BloomsComplianceReport.exam_paper_id == exam_paper_id
            )
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# TaskJobPublicRepository — mirrors M07 pattern exactly
# ---------------------------------------------------------------------------

class TaskJobPublicRepository:
    """
    Operates on public.task_jobs. Caller must pass a session scoped to the
    public schema (AsyncSessionLocal(), not the tenant session).
    Returns the new job UUID.
    """

    @staticmethod
    async def create(
        *,
        task_type: str,
        queue_name: str,
        tenant_id: UUID,
        payload: dict | None = None,
        db: AsyncSession,
    ) -> UUID:
        import json as _json
        from sqlalchemy import text as sa_text
        job_id = uuid.uuid4()
        await db.execute(
            sa_text(
                "INSERT INTO public.task_jobs "
                "(id, tenant_id, task_type, queue_name, status, payload) "
                "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), "
                ":task_type, :queue_name, 'PENDING', CAST(:payload AS jsonb))"
            ),
            {
                "id":         str(job_id),
                "tenant_id":  str(tenant_id),
                "task_type":  task_type,
                "queue_name": queue_name,
                "payload":    _json.dumps(payload or {}),
            },
        )
        return job_id


# ---------------------------------------------------------------------------
# InternalMarksRepository  (H-35 Addition 2)
# ---------------------------------------------------------------------------

class InternalMarksRepository:

    @staticmethod
    async def create(
        *,
        student_id: UUID,
        course_id: UUID,
        semester: int,
        academic_year: str,
        internal1_marks=None,
        internal2_marks=None,
        assignment_marks=None,
        attendance_marks=None,
        max_internal: int = 40,
        db: AsyncSession,
    ) -> InternalMarksSummary:
        ims = InternalMarksSummary(
            student_id=student_id,
            course_id=course_id,
            semester=semester,
            academic_year=academic_year,
            internal1_marks=internal1_marks,
            internal2_marks=internal2_marks,
            assignment_marks=assignment_marks,
            attendance_marks=attendance_marks,
            max_internal=max_internal,
            status=InternalMarkStatus.PENDING.value,
        )
        db.add(ims)
        await db.flush()
        return ims

    @staticmethod
    async def get_by_id(
        ims_id: UUID,
        *,
        db: AsyncSession,
    ) -> InternalMarksSummary | None:
        result = await db.execute(
            select(InternalMarksSummary).where(InternalMarksSummary.id == ims_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_student_course(
        student_id: UUID,
        course_id: UUID,
        semester: int,
        academic_year: str,
        *,
        db: AsyncSession,
    ) -> InternalMarksSummary | None:
        result = await db.execute(
            select(InternalMarksSummary).where(
                InternalMarksSummary.student_id == student_id,
                InternalMarksSummary.course_id == course_id,
                InternalMarksSummary.semester == semester,
                InternalMarksSummary.academic_year == academic_year,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_marks(
        ims_id: UUID,
        *,
        updates: dict,
        db: AsyncSession,
    ) -> None:
        updates = {**updates, "updated_at": datetime.now(timezone.utc)}
        await db.execute(
            sa_update(InternalMarksSummary)
            .where(InternalMarksSummary.id == ims_id)
            .values(**updates)
        )

    @staticmethod
    async def set_submitted(
        ims_id: UUID,
        *,
        submitted_by: UUID,
        total_internal: float,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(InternalMarksSummary)
            .where(InternalMarksSummary.id == ims_id)
            .values(
                status=InternalMarkStatus.FACULTY_SUBMITTED.value,
                submitted_by=submitted_by,
                submitted_at=datetime.now(timezone.utc),
                total_internal=total_internal,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_locked(
        ims_id: UUID,
        *,
        locked_by: UUID,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(InternalMarksSummary)
            .where(InternalMarksSummary.id == ims_id)
            .values(
                status=InternalMarkStatus.DEAN_LOCKED.value,
                locked_by=locked_by,
                locked_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def list_by_course(
        course_id: UUID,
        *,
        semester: int | None = None,
        academic_year: str | None = None,
        offset: int = 0,
        limit: int = 100,
        db: AsyncSession,
    ) -> list[InternalMarksSummary]:
        q = select(InternalMarksSummary).where(
            InternalMarksSummary.course_id == course_id
        )
        if semester is not None:
            q = q.where(InternalMarksSummary.semester == semester)
        if academic_year:
            q = q.where(InternalMarksSummary.academic_year == academic_year)
        q = q.order_by(InternalMarksSummary.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_course(
        course_id: UUID,
        *,
        semester: int | None = None,
        academic_year: str | None = None,
        db: AsyncSession,
    ) -> int:
        q = select(func.count(InternalMarksSummary.id)).where(
            InternalMarksSummary.course_id == course_id
        )
        if semester is not None:
            q = q.where(InternalMarksSummary.semester == semester)
        if academic_year:
            q = q.where(InternalMarksSummary.academic_year == academic_year)
        result = await db.execute(q)
        return result.scalar_one()


# ---------------------------------------------------------------------------
# QuestionBankRepository  (H-35 Addition 1)
# ---------------------------------------------------------------------------

class QuestionBankRepository:

    @staticmethod
    async def promote_from_paper(
        *,
        paper_id: UUID,
        course_id: UUID,
        questions: list[ExamQuestion],
        is_approved: bool,
        db: AsyncSession,
    ) -> list[QuestionBankEntry]:
        entries = []
        for q in questions:
            entry = QuestionBankEntry(
                course_id=course_id,
                source_paper_id=paper_id,
                unit_number=q.unit_number,
                co_ids=getattr(q, "co_ids", None) or [],
                bloom_level=q.bloom_level,
                question_type=q.question_type,
                question_text=q.question_text,
                options=q.options,
                correct_option=q.correct_option,
                marks=q.marks,
                model_answer=q.model_answer,
                marking_scheme=q.marking_scheme,
                section_label=getattr(q, "section_label", None),
                is_approved=is_approved,
                ai_generated=q.ai_generated,
            )
            db.add(entry)
            entries.append(entry)
        if entries:
            await db.flush()
        return entries

    @staticmethod
    async def list_by_course(
        course_id: UUID,
        *,
        bloom_level: str | None = None,
        question_type: str | None = None,
        unit_number: int | None = None,
        approved_only: bool = True,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[QuestionBankEntry]:
        q = select(QuestionBankEntry).where(QuestionBankEntry.course_id == course_id)
        if approved_only:
            q = q.where(QuestionBankEntry.is_approved.is_(True))
        if bloom_level:
            q = q.where(QuestionBankEntry.bloom_level == bloom_level.upper())
        if question_type:
            q = q.where(QuestionBankEntry.question_type == question_type.upper())
        if unit_number is not None:
            q = q.where(QuestionBankEntry.unit_number == unit_number)
        q = q.order_by(QuestionBankEntry.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_course(
        course_id: UUID,
        *,
        approved_only: bool = True,
        db: AsyncSession,
    ) -> int:
        q = select(func.count(QuestionBankEntry.id)).where(
            QuestionBankEntry.course_id == course_id
        )
        if approved_only:
            q = q.where(QuestionBankEntry.is_approved.is_(True))
        result = await db.execute(q)
        return result.scalar_one()
