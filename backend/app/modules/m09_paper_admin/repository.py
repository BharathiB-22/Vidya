"""
M09 Paper Administration & Scanning — Repository layer.

All queries use the tenant search_path set on the session.
No cross-tenant queries.

TaskJobPublicRepository operates on public.task_jobs and requires a session
from async_session_public() — same pattern as M06/M07/M08.

Identity rule: no method here returns student_user_id — the service layer
masks it before returning responses to callers.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m09_paper_admin.models import (
    EvaluationRound,
    ExamScoreLedger,
    ScannedScript,
    ScriptEvaluation,
    ScriptStatus,
)


# ---------------------------------------------------------------------------
# ScriptRepository
# ---------------------------------------------------------------------------

class ScriptRepository:

    @staticmethod
    async def create(
        *,
        exam_paper_id: UUID,
        masked_id: str,
        student_user_id: UUID | None,
        student_roll_ref: str | None,
        upload_url: str | None,
        page_count: int | None,
        db: AsyncSession,
    ) -> ScannedScript:
        script = ScannedScript(
            exam_paper_id=exam_paper_id,
            masked_id=masked_id,
            student_user_id=student_user_id,
            student_roll_ref=student_roll_ref,
            upload_url=upload_url,
            page_count=page_count,
            status=ScriptStatus.PENDING.value,
        )
        db.add(script)
        await db.flush()
        return script

    @staticmethod
    async def get_by_id(script_id: UUID, *, db: AsyncSession) -> ScannedScript | None:
        result = await db.execute(
            select(ScannedScript).where(ScannedScript.id == script_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_masked_id(masked_id: str, *, db: AsyncSession) -> ScannedScript | None:
        result = await db.execute(
            select(ScannedScript).where(ScannedScript.masked_id == masked_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_exam_paper(
        exam_paper_id: UUID,
        *,
        status: str | None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ) -> list[ScannedScript]:
        q = select(ScannedScript).where(ScannedScript.exam_paper_id == exam_paper_id)
        if status:
            q = q.where(ScannedScript.status == status)
        q = q.order_by(ScannedScript.created_at.asc()).offset(offset).limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def list_for_evaluator(
        evaluator_id: UUID,
        *,
        status: str | None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ) -> list[ScannedScript]:
        q = select(ScannedScript).where(ScannedScript.evaluator_id == evaluator_id)
        if status:
            q = q.where(ScannedScript.status == status)
        q = q.order_by(ScannedScript.created_at.asc()).offset(offset).limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def list_board_pending(
        *,
        offset: int,
        limit: int,
        db: AsyncSession,
    ) -> list[ScannedScript]:
        """Scripts awaiting Board finalisation (status = MARKS_SUBMITTED)."""
        q = (
            select(ScannedScript)
            .where(ScannedScript.status == ScriptStatus.MARKS_SUBMITTED.value)
            .order_by(ScannedScript.submitted_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def list_all(
        *,
        status: str | None,
        exam_paper_id: UUID | None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ) -> list[ScannedScript]:
        q = select(ScannedScript)
        if status:
            q = q.where(ScannedScript.status == status)
        if exam_paper_id:
            q = q.where(ScannedScript.exam_paper_id == exam_paper_id)
        q = q.order_by(ScannedScript.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def set_eval_job(
        script_id: UUID,
        *,
        job_id: UUID,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                eval_job_id=job_id,
                status=ScriptStatus.PROCESSING.value,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_scored(
        script_id: UUID,
        *,
        objective_auto_score: float,
        db: AsyncSession,
    ) -> None:
        """Called by Celery score task on success. Maximum status = SCORED."""
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                status=ScriptStatus.SCORED.value,
                objective_auto_score=objective_auto_score,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_failed(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        """Called by Celery score task on unrecoverable failure."""
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                status=ScriptStatus.FAILED.value,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_review_required(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        """Transition to REVIEW_REQUIRED for partial failures requiring admin attention."""
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                status=ScriptStatus.REVIEW_REQUIRED.value,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def assign_evaluator(
        script_id: UUID,
        *,
        evaluator_id: UUID,
        second_evaluator_id: UUID | None,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                evaluator_id=evaluator_id,
                second_evaluator_id=second_evaluator_id,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_marks_submitted(
        script_id: UUID,
        *,
        submitted_by: UUID,
        db: AsyncSession,
    ) -> None:
        """Gate 1: written ONLY by submit_marks service method."""
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                status=ScriptStatus.MARKS_SUBMITTED.value,
                submitted_by=submitted_by,
                submitted_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_finalised(
        script_id: UUID,
        *,
        finalised_by: UUID,
        db: AsyncSession,
    ) -> None:
        """Gate 2: written ONLY by board_finalise service method."""
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                status=ScriptStatus.BOARD_FINALISED.value,
                finalised_by=finalised_by,
                finalised_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )


# ---------------------------------------------------------------------------
# ScriptEvaluationRepository
# ---------------------------------------------------------------------------

class ScriptEvaluationRepository:

    @staticmethod
    async def bulk_create_ai_suggestions(
        suggestions: list[dict],
        *,
        script_id: UUID,
        db: AsyncSession,
    ) -> list[ScriptEvaluation]:
        """
        Called by Celery score task.
        Creates one ScriptEvaluation row per question with AI-suggested marks.
        evaluator_marks is left NULL — never written by Celery.
        """
        objs = []
        for s in suggestions:
            obj = ScriptEvaluation(
                script_id=script_id,
                question_id=s["question_id"],
                question_type=s["question_type"],
                max_marks=s["max_marks"],
                evaluation_round=EvaluationRound.PRIMARY.value,
                ai_suggested_marks=s.get("ai_suggested_marks"),
                ai_justification=s.get("ai_justification"),
                ai_model=s.get("ai_model"),
                prompt_hash=s.get("prompt_hash"),
                # evaluator_marks intentionally left NULL
            )
            db.add(obj)
            objs.append(obj)
        await db.flush()
        return objs

    @staticmethod
    async def list_by_script(
        script_id: UUID,
        *,
        evaluation_round: str | None = None,
        db: AsyncSession,
    ) -> list[ScriptEvaluation]:
        q = (
            select(ScriptEvaluation)
            .where(ScriptEvaluation.script_id == script_id)
        )
        if evaluation_round:
            q = q.where(ScriptEvaluation.evaluation_round == evaluation_round)
        q = q.order_by(ScriptEvaluation.created_at)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(eval_id: UUID, *, db: AsyncSession) -> ScriptEvaluation | None:
        result = await db.execute(
            select(ScriptEvaluation).where(ScriptEvaluation.id == eval_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_evaluator_marks(
        eval_id: UUID,
        *,
        evaluator_marks: float,
        evaluator_note: str | None,
        db: AsyncSession,
    ) -> None:
        """Written ONLY by evaluator endpoints — never by Celery."""
        await db.execute(
            sa_update(ScriptEvaluation)
            .where(ScriptEvaluation.id == eval_id)
            .values(
                evaluator_marks=evaluator_marks,
                evaluator_note=evaluator_note,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def bulk_update_evaluator_marks(
        updates: dict[UUID, dict],
        *,
        script_id: UUID,
        db: AsyncSession,
    ) -> None:
        """
        Bulk update evaluator marks by question_id.
        updates: {question_id → {evaluator_marks, evaluator_note}}
        Written ONLY by evaluator endpoints.
        """
        for question_id, data in updates.items():
            await db.execute(
                sa_update(ScriptEvaluation)
                .where(
                    ScriptEvaluation.script_id == script_id,
                    ScriptEvaluation.question_id == question_id,
                    ScriptEvaluation.evaluation_round == EvaluationRound.PRIMARY.value,
                )
                .values(
                    evaluator_marks=data["evaluator_marks"],
                    evaluator_note=data.get("evaluator_note"),
                    updated_at=datetime.now(timezone.utc),
                )
            )

    @staticmethod
    async def set_final_marks(
        script_id: UUID,
        *,
        evaluation_round: str,
        db: AsyncSession,
    ) -> None:
        """
        Copies evaluator_marks → final_marks for all rows of a given round.
        Called by board_finalise service method ONLY.
        """
        await db.execute(
            sa_update(ScriptEvaluation)
            .where(
                ScriptEvaluation.script_id == script_id,
                ScriptEvaluation.evaluation_round == evaluation_round,
            )
            .values(
                final_marks=ScriptEvaluation.evaluator_marks,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def sum_evaluator_marks(
        script_id: UUID,
        *,
        evaluation_round: str,
        db: AsyncSession,
    ) -> float:
        """Returns the sum of evaluator_marks (NULL treated as 0)."""
        result = await db.execute(
            select(func.coalesce(func.sum(ScriptEvaluation.evaluator_marks), 0))
            .where(
                ScriptEvaluation.script_id == script_id,
                ScriptEvaluation.evaluation_round == evaluation_round,
            )
        )
        return float(result.scalar() or 0.0)

    @staticmethod
    async def sum_max_marks(
        script_id: UUID,
        *,
        evaluation_round: str,
        db: AsyncSession,
    ) -> float:
        """Returns the sum of max_marks for all questions in this round."""
        result = await db.execute(
            select(func.coalesce(func.sum(ScriptEvaluation.max_marks), 0))
            .where(
                ScriptEvaluation.script_id == script_id,
                ScriptEvaluation.evaluation_round == evaluation_round,
            )
        )
        return float(result.scalar() or 0.0)


# ---------------------------------------------------------------------------
# ExamScoreLedgerRepository — append-only
# ---------------------------------------------------------------------------

class ExamScoreLedgerRepository:

    @staticmethod
    async def create(
        *,
        script_id: UUID,
        exam_paper_id: UUID,
        student_user_id: UUID | None,
        student_roll_ref: str | None,
        total_marks: float,
        max_marks: float,
        finalised_by: UUID,
        finalisation_note: str | None,
        db: AsyncSession,
    ) -> ExamScoreLedger:
        """
        Append-only write. Called by board_finalise service ONLY.
        No UPDATE or DELETE on exam_score_ledger ever.
        """
        entry = ExamScoreLedger(
            script_id=script_id,
            exam_paper_id=exam_paper_id,
            student_user_id=student_user_id,
            student_roll_ref=student_roll_ref,
            total_marks=total_marks,
            max_marks=max_marks,
            finalised_by=finalised_by,
            finalisation_note=finalisation_note,
        )
        db.add(entry)
        await db.flush()
        return entry

    @staticmethod
    async def get_by_script(script_id: UUID, *, db: AsyncSession) -> ExamScoreLedger | None:
        result = await db.execute(
            select(ExamScoreLedger).where(ExamScoreLedger.script_id == script_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_exam_paper(
        exam_paper_id: UUID,
        *,
        offset: int,
        limit: int,
        db: AsyncSession,
    ) -> list[ExamScoreLedger]:
        q = (
            select(ExamScoreLedger)
            .where(ExamScoreLedger.exam_paper_id == exam_paper_id)
            .order_by(ExamScoreLedger.finalised_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(q)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# TaskJobPublicRepository — identical pattern to M06/M07/M08
# ---------------------------------------------------------------------------

class TaskJobPublicRepository:
    """
    Operates on public.task_jobs. Caller must pass a session from
    async_session_public() (not the tenant session).
    """

    @staticmethod
    async def create(
        *,
        task_name: str,
        tenant_id: UUID,
        db: AsyncSession,
    ):
        from sqlalchemy import text as sa_text
        result = await db.execute(
            sa_text(
                "INSERT INTO public.task_jobs (id, task_name, tenant_id, status, created_at) "
                "VALUES (:id, :task_name, :tenant_id, 'PENDING', now()) RETURNING *"
            ),
            {
                "id":        str(uuid.uuid4()),
                "task_name": task_name,
                "tenant_id": str(tenant_id),
            },
        )
        row = result.mappings().one()

        class _Job:
            pass

        job = _Job()
        job.id = UUID(row["id"]) if isinstance(row["id"], str) else row["id"]
        return job
