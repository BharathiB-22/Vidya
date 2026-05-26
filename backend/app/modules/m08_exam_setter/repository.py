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
from typing import Optional
from uuid import UUID

logger = logging.getLogger("vidya.repo.m08")

from sqlalchemy import select, update as sa_update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m08_exam_setter.models import (
    BloomsComplianceReport,
    ExamPaper,
    ExamPaperStatus,
    ExamQuestion,
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
        total_marks: int,
        duration_mins: int,
        units_included: list,
        question_format: dict,
        requested_dist: dict,
        special_instructions: str | None,
        db: AsyncSession,
    ) -> ExamPaper:
        paper = ExamPaper(
            course_id=course_id,
            created_by=created_by,
            title=title,
            exam_type=exam_type,
            total_marks=total_marks,
            duration_mins=duration_mins,
            units_included=units_included,
            question_format=question_format,
            requested_dist=requested_dist,
            special_instructions=special_instructions,
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
        """Papers awaiting Board review."""
        q = (
            select(ExamPaper)
            .where(ExamPaper.status == ExamPaperStatus.SUBMITTED.value)
            .order_by(ExamPaper.submitted_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def list_all(
        *,
        status: str | None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ) -> list[ExamPaper]:
        """Admin / Dean: all papers for the tenant."""
        q = select(ExamPaper)
        if status:
            q = q.where(ExamPaper.status == status)
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
    async def set_generation_result(
        paper_id: UUID,
        *,
        ai_model: str,
        prompt_hash: str,
        actual_dist: dict,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(ExamPaper)
            .where(ExamPaper.id == paper_id)
            .values(
                ai_model=ai_model,
                prompt_hash=prompt_hash,
                actual_dist=actual_dist,
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
        for q in questions:
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
                ai_generated=True,
                is_edited=False,
            )
            db.add(obj)
            objs.append(obj)
        await db.flush()
        return objs

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
            .order_by(ExamQuestion.created_at)
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
            )
            db.add(report)
        else:
            report.requested_dist = requested_dist
            report.actual_dist    = actual_dist
            report.compliance_ok  = compliance_ok
            report.violations     = violations
            report.generated_at   = datetime.now(timezone.utc)
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
