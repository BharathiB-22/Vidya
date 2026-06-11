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
    BoardApprovalStatus,
    BoardSessionStatus,
    DigitalAttemptStatus,
    DigitalExamAttempt,
    DigitalExamResponse,
    DigitalExamSession,
    DigitalExamSessionStatus,
    EvaluationRound,
    ExamBoardCourseApproval,
    ExamBoardSession,
    ExamScoreLedger,
    ModerationStatus,
    RevaluationEvaluation,
    RevaluationRequest,
    RevaluationStatus,
    ScannedScript,
    ScriptEvaluation,
    ScriptModerationReview,
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
        double_evaluation_enabled: bool = False,
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
            double_evaluation_enabled=double_evaluation_enabled,
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
    async def set_ocr_processing(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        """Mark OCR extraction in progress (ocr_status field; script stays OCR_PROCESSING)."""
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                ocr_status="PROCESSING",
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_ocr_result(
        script_id: UUID,
        *,
        ocr_text: str | None,
        ocr_status_value: str,
        had_ocr: bool,
        db: AsyncSession,
    ) -> None:
        """
        Save OCR output and advance script status.
        had_ocr=True  → status = PROCESSING (score_scanned_script task takes over).
        had_ocr=False → status = REVIEW_REQUIRED (admin reviews; evaluator enters marks manually).
        Called ONLY by ocr_scanned_script Celery task.
        """
        new_status = (
            ScriptStatus.PROCESSING.value
            if had_ocr
            else ScriptStatus.REVIEW_REQUIRED.value
        )
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                ocr_text=ocr_text,
                ocr_status=ocr_status_value,
                status=new_status,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_quality_checking(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        """Called by detect_scan_quality Celery task at task start."""
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                status=ScriptStatus.QUALITY_CHECKING.value,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_quality_result(
        script_id: UUID,
        *,
        quality_score: float,
        flags: list[dict],
        passed: bool,
        db: AsyncSession,
    ) -> None:
        """
        Save scan quality results and advance status.
        passed=True  → OCR_PROCESSING (STEP-03 task takes over).
        passed=False → QUALITY_FAILED (admin must re-upload or override).
        Called ONLY by detect_scan_quality Celery task.
        """
        new_status = (
            ScriptStatus.OCR_PROCESSING.value
            if passed
            else ScriptStatus.QUALITY_FAILED.value
        )
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                ocr_quality_score=quality_score,
                scan_quality_flags=flags,
                status=new_status,
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
    async def set_waiting_second_evaluator(
        script_id: UUID,
        *,
        submitted_by: UUID,
        db: AsyncSession,
    ) -> None:
        """
        Double-eval Gate 1a: primary evaluator submitted.
        Written ONLY by submit_marks service method on double-eval papers.
        """
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                status=ScriptStatus.WAITING_SECOND_EVALUATOR.value,
                submitted_by=submitted_by,
                submitted_at=datetime.now(timezone.utc),
                primary_submitted_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_secondary_evaluated(
        script_id: UUID,
        *,
        submitted_by: UUID,
        db: AsyncSession,
    ) -> None:
        """
        Double-eval Gate 1b: secondary evaluator submitted.
        Written ONLY by submit_marks service method on double-eval papers.
        M09.2 will insert moderation routing between this and MARKS_SUBMITTED.
        """
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                status=ScriptStatus.SECONDARY_EVALUATED.value,
                secondary_submitted_at=datetime.now(timezone.utc),
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
        """Gate 1 final: written ONLY by submit_marks service method."""
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

    @staticmethod
    async def set_moderation_pending(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        """M09.2: flag script for moderation; written ONLY by ModerationService."""
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                status=ScriptStatus.MODERATION_PENDING.value,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_moderation_complete(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        """M09.2: moderator submitted marks; written ONLY by ModerationService."""
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                status=ScriptStatus.MODERATION_COMPLETE.value,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_quality_overridden(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        """
        Admin override: advance a QUALITY_FAILED script to OCR_PROCESSING.
        Called ONLY by override_quality_failed service method.
        Override reason is captured in the audit log, not in this table.
        """
        await db.execute(
            sa_update(ScannedScript)
            .where(ScannedScript.id == script_id)
            .values(
                status=ScriptStatus.OCR_PROCESSING.value,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def count_by_status_for_paper(
        exam_paper_id: UUID,
        *,
        db: AsyncSession,
    ) -> dict[str, int]:
        """
        Returns a mapping of status → count for all scripts in an exam paper.
        Missing statuses are absent from the dict (caller should default to 0).
        Single GROUP BY query — no N+1.
        """
        result = await db.execute(
            select(ScannedScript.status, func.count(ScannedScript.id))
            .where(ScannedScript.exam_paper_id == exam_paper_id)
            .group_by(ScannedScript.status)
        )
        return {row[0]: row[1] for row in result.all()}


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
                # Enrichment fields (STEP-04) — NULL when not available
                keyword_hits=s.get("keyword_hits"),
                rubric_mapping=s.get("rubric_mapping"),
                ai_confidence=s.get("ai_confidence"),
                page_range=s.get("page_range"),
                # evaluator_marks intentionally left NULL — never written by Celery
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
        evaluation_round: str = EvaluationRound.PRIMARY.value,
        db: AsyncSession,
    ) -> None:
        """
        Bulk update evaluator marks by question_id for a given round.
        updates: {question_id → {evaluator_marks, evaluator_note}}
        evaluation_round defaults to PRIMARY; pass SECONDARY for double-eval.
        Written ONLY by evaluator endpoints — never by Celery.
        """
        for question_id, data in updates.items():
            await db.execute(
                sa_update(ScriptEvaluation)
                .where(
                    ScriptEvaluation.script_id == script_id,
                    ScriptEvaluation.question_id == question_id,
                    ScriptEvaluation.evaluation_round == evaluation_round,
                )
                .values(
                    evaluator_marks=data["evaluator_marks"],
                    evaluator_note=data.get("evaluator_note"),
                    updated_at=datetime.now(timezone.utc),
                )
            )

    @staticmethod
    async def bulk_create_secondary_evaluations(
        primary_evals: list[ScriptEvaluation],
        *,
        script_id: UUID,
        db: AsyncSession,
    ) -> list[ScriptEvaluation]:
        """
        Create SECONDARY round evaluation rows by copying AI suggestions from PRIMARY.
        Called ONLY when primary evaluator submits on a double-eval paper.
        evaluator_marks is left NULL — the secondary evaluator fills it independently.
        Primary evaluator_marks are NOT copied, preserving evaluation independence.
        """
        objs = []
        for primary in primary_evals:
            obj = ScriptEvaluation(
                script_id=script_id,
                question_id=primary.question_id,
                question_type=primary.question_type,
                max_marks=primary.max_marks,
                evaluation_round=EvaluationRound.SECONDARY.value,
                ai_suggested_marks=primary.ai_suggested_marks,
                ai_justification=primary.ai_justification,
                ai_model=primary.ai_model,
                prompt_hash=primary.prompt_hash,
                keyword_hits=primary.keyword_hits,
                rubric_mapping=primary.rubric_mapping,
                ai_confidence=primary.ai_confidence,
                page_range=primary.page_range,
            )
            db.add(obj)
            objs.append(obj)
        await db.flush()
        return objs

    @staticmethod
    async def bulk_update_board_adjusted_marks(
        updates: dict[UUID, dict],
        *,
        script_id: UUID,
        db: AsyncSession,
    ) -> None:
        """
        Board sets adjusted marks on PRIMARY evaluation rows.
        updates: {question_id → {board_adjusted_marks, board_adjustment_note}}
        Written ONLY by board_adjust service method — never by Celery.
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
                    board_adjusted_marks=data["board_adjusted_marks"],
                    board_adjustment_note=data.get("board_adjustment_note"),
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
        Copies COALESCE(board_adjusted_marks, evaluator_marks) → final_marks.
        For single-eval papers: board_adjusted_marks is NULL → uses evaluator_marks.
        For double-eval papers: board_adjusted_marks is required before finalise →
        final_marks = board_adjusted_marks (Board's explicit decision).
        Called by board_finalise service method ONLY.
        """
        from sqlalchemy import func as sa_func
        await db.execute(
            sa_update(ScriptEvaluation)
            .where(
                ScriptEvaluation.script_id == script_id,
                ScriptEvaluation.evaluation_round == evaluation_round,
            )
            .values(
                final_marks=sa_func.coalesce(
                    ScriptEvaluation.board_adjusted_marks,
                    ScriptEvaluation.evaluator_marks,
                ),
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def sum_final_marks(
        script_id: UUID,
        *,
        evaluation_round: str,
        db: AsyncSession,
    ) -> float:
        """Returns the sum of final_marks (NULL treated as 0). Call after set_final_marks."""
        result = await db.execute(
            select(func.coalesce(func.sum(ScriptEvaluation.final_marks), 0))
            .where(
                ScriptEvaluation.script_id == script_id,
                ScriptEvaluation.evaluation_round == evaluation_round,
            )
        )
        return float(result.scalar() or 0.0)

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

    @staticmethod
    async def bulk_create_moderation_evaluations(
        marks: dict[UUID, dict],
        *,
        primary_evals: list[ScriptEvaluation],
        script_id: UUID,
        db: AsyncSession,
    ) -> list[ScriptEvaluation]:
        """
        M09.2: create MODERATION round evaluation rows from moderator's per-question marks.
        marks: {question_id → {evaluator_marks, evaluator_note}}
        Primary eval rows supply question_type / max_marks for the MODERATION rows.
        evaluator_marks is the moderator's authoritative mark — never None after this.
        """
        primary_map = {e.question_id: e for e in primary_evals}
        objs = []
        for question_id, data in marks.items():
            primary = primary_map.get(question_id)
            if primary is None:
                continue
            obj = ScriptEvaluation(
                script_id=script_id,
                question_id=question_id,
                question_type=primary.question_type,
                max_marks=primary.max_marks,
                evaluation_round=EvaluationRound.MODERATION.value,
                evaluator_marks=data["evaluator_marks"],
                evaluator_note=data.get("evaluator_note"),
                # Copy AI suggestion metadata for traceability
                ai_suggested_marks=primary.ai_suggested_marks,
                ai_model=primary.ai_model,
                prompt_hash=primary.prompt_hash,
            )
            db.add(obj)
            objs.append(obj)
        await db.flush()
        return objs


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
        primary_total: float | None,
        secondary_total: float | None,
        finalised_by: UUID,
        finalisation_note: str | None,
        db: AsyncSession,
    ) -> ExamScoreLedger:
        """
        Append-only write. Called by board_finalise service ONLY.
        No UPDATE or DELETE on exam_score_ledger ever.
        primary_total / secondary_total are None for single-evaluator papers.
        """
        entry = ExamScoreLedger(
            script_id=script_id,
            exam_paper_id=exam_paper_id,
            student_user_id=student_user_id,
            student_roll_ref=student_roll_ref,
            total_marks=total_marks,
            max_marks=max_marks,
            primary_total=primary_total,
            secondary_total=secondary_total,
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
        tenant_id: UUID,
        task_type: str,
        queue_name: str,
        payload: dict,
        *,
        db: AsyncSession,
    ) -> UUID:  # noqa: E501 (continued below)
        import json as _json
        from sqlalchemy import text as sa_text
        job_id = uuid.uuid4()
        stmt = sa_text(
            "INSERT INTO public.task_jobs "
            "(id, tenant_id, task_type, queue_name, status, payload) "
            "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), :task_type, :queue_name, 'PENDING', CAST(:payload AS jsonb))"
        )
        await db.execute(stmt, {
            "id":         str(job_id),
            "tenant_id":  str(tenant_id),
            "task_type":  task_type,
            "queue_name": queue_name,
            "payload":    _json.dumps(payload),
        })
        await db.flush()
        return job_id


# ---------------------------------------------------------------------------
# ModerationRepository — M09.2
# ---------------------------------------------------------------------------

class ModerationRepository:

    @staticmethod
    async def create(
        *,
        script_id: UUID,
        exam_paper_id: UUID,
        primary_total: float,
        secondary_total: float,
        variance_pct: float,
        variance_threshold: float,
        flag_reason: str,
        flagged_by: UUID | None,
        db: AsyncSession,
    ) -> ScriptModerationReview:
        """Create a new moderation review row. Called ONLY by ModerationService."""
        review = ScriptModerationReview(
            script_id=script_id,
            exam_paper_id=exam_paper_id,
            primary_total=primary_total,
            secondary_total=secondary_total,
            variance_pct=variance_pct,
            variance_threshold=variance_threshold,
            flag_reason=flag_reason,
            flagged_by=flagged_by,
            status=ModerationStatus.PENDING,
        )
        db.add(review)
        await db.flush()
        return review

    @staticmethod
    async def get_by_script(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> ScriptModerationReview | None:
        result = await db.execute(
            select(ScriptModerationReview)
            .where(ScriptModerationReview.script_id == script_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def complete(
        review: ScriptModerationReview,
        *,
        moderator_id: UUID,
        moderation_notes: str,
        db: AsyncSession,
    ) -> None:
        """Mark moderation review complete. Called ONLY by ModerationService.submit_moderation."""
        now = datetime.now(timezone.utc)
        await db.execute(
            sa_update(ScriptModerationReview)
            .where(ScriptModerationReview.id == review.id)
            .values(
                status=ModerationStatus.COMPLETE,
                moderator_id=moderator_id,
                moderation_notes=moderation_notes,
                completed_at=now,
            )
        )

    @staticmethod
    async def list_pending_for_paper(
        exam_paper_id: UUID,
        *,
        offset: int,
        limit: int,
        db: AsyncSession,
    ) -> list[ScriptModerationReview]:
        """All PENDING moderation reviews for an exam paper (moderation queue)."""
        q = (
            select(ScriptModerationReview)
            .where(
                ScriptModerationReview.exam_paper_id == exam_paper_id,
                ScriptModerationReview.status == ModerationStatus.PENDING,
            )
            .order_by(ScriptModerationReview.variance_pct.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def count_pending_for_paper(
        exam_paper_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        result = await db.execute(
            select(func.count(ScriptModerationReview.id))
            .where(
                ScriptModerationReview.exam_paper_id == exam_paper_id,
                ScriptModerationReview.status == ModerationStatus.PENDING,
            )
        )
        return int(result.scalar() or 0)

    @staticmethod
    async def get_threshold(
        exam_paper_id: UUID,
        *,
        db: AsyncSession,
        default_threshold: float = 20.0,
    ) -> float:
        """
        Read discrepancy_threshold_pct from exam_papers.
        Falls back to default_threshold when the paper has no explicit setting.
        Uses raw SQL to avoid a cross-module ORM dependency.
        """
        from sqlalchemy import text as sa_text
        result = await db.execute(
            sa_text(
                "SELECT discrepancy_threshold_pct FROM exam_papers "
                "WHERE id = CAST(:pid AS uuid)"
            ),
            {"pid": str(exam_paper_id)},
        )
        row = result.fetchone()
        if row is None or row[0] is None:
            return default_threshold
        return float(row[0])


# ---------------------------------------------------------------------------
# BoardSessionRepository — M09.4 Examination Board Approval
# ---------------------------------------------------------------------------

class BoardSessionRepository:
    """
    Examination Board session CRUD.
    One session covers one exam paper's result approval lifecycle.
    """

    @staticmethod
    async def create(
        exam_paper_id: UUID,
        session_title: str,
        convened_by: UUID,
        *,
        db: AsyncSession,
    ) -> ExamBoardSession:
        session = ExamBoardSession(
            exam_paper_id=exam_paper_id,
            session_title=session_title,
            convened_by=convened_by,
            status=BoardSessionStatus.OPEN.value,
        )
        db.add(session)
        await db.flush()
        return session

    @staticmethod
    async def get_by_id(session_id: UUID, *, db: AsyncSession) -> ExamBoardSession | None:
        result = await db.execute(
            select(ExamBoardSession).where(ExamBoardSession.id == session_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_paper(
        exam_paper_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[ExamBoardSession]:
        result = await db.execute(
            select(ExamBoardSession)
            .where(ExamBoardSession.exam_paper_id == exam_paper_id)
            .order_by(ExamBoardSession.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def count_for_paper(exam_paper_id: UUID, *, db: AsyncSession) -> int:
        result = await db.execute(
            select(func.count(ExamBoardSession.id))
            .where(ExamBoardSession.exam_paper_id == exam_paper_id)
        )
        return result.scalar_one() or 0

    @staticmethod
    async def get_open_session(exam_paper_id: UUID, *, db: AsyncSession) -> ExamBoardSession | None:
        """Return the most recent OPEN session for a paper, or None."""
        result = await db.execute(
            select(ExamBoardSession)
            .where(
                ExamBoardSession.exam_paper_id == exam_paper_id,
                ExamBoardSession.status == BoardSessionStatus.OPEN.value,
            )
            .order_by(ExamBoardSession.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_approved_session(exam_paper_id: UUID, *, db: AsyncSession) -> ExamBoardSession | None:
        """Return the APPROVED or DECLARED session for a paper (for lock checks)."""
        result = await db.execute(
            select(ExamBoardSession)
            .where(
                ExamBoardSession.exam_paper_id == exam_paper_id,
                ExamBoardSession.status.in_([
                    BoardSessionStatus.APPROVED.value,
                    BoardSessionStatus.DECLARED.value,
                ]),
            )
            .order_by(ExamBoardSession.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def approve(
        session: ExamBoardSession,
        decided_by: UUID,
        board_remarks: str | None,
        *,
        db: AsyncSession,
    ) -> None:
        from datetime import datetime, timezone
        session.status = BoardSessionStatus.APPROVED.value
        session.decided_by = decided_by
        session.decided_at = datetime.now(timezone.utc)
        session.board_remarks = board_remarks
        await db.flush()

    @staticmethod
    async def reject(
        session: ExamBoardSession,
        decided_by: UUID,
        board_remarks: str,
        *,
        db: AsyncSession,
    ) -> None:
        from datetime import datetime, timezone
        session.status = BoardSessionStatus.REJECTED.value
        session.decided_by = decided_by
        session.decided_at = datetime.now(timezone.utc)
        session.board_remarks = board_remarks
        await db.flush()

    @staticmethod
    async def declare(
        session: ExamBoardSession,
        declared_by: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        from datetime import datetime, timezone
        session.status = BoardSessionStatus.DECLARED.value
        session.declared_by = declared_by
        session.declared_at = datetime.now(timezone.utc)
        await db.flush()


class BoardCourseApprovalRepository:
    """Aggregate stats snapshot for one exam paper within a board session."""

    @staticmethod
    async def create(
        session_id: UUID,
        exam_paper_id: UUID,
        *,
        mean_marks: float | None,
        max_marks: float | None,
        pass_count: int | None,
        fail_count: int | None,
        total_scripts: int | None,
        pass_rate_pct: float | None,
        db: AsyncSession,
    ) -> ExamBoardCourseApproval:
        approval = ExamBoardCourseApproval(
            session_id=session_id,
            exam_paper_id=exam_paper_id,
            mean_marks=mean_marks,
            max_marks=max_marks,
            pass_count=pass_count,
            fail_count=fail_count,
            total_scripts=total_scripts,
            pass_rate_pct=pass_rate_pct,
            approval_status=BoardApprovalStatus.PENDING.value,
        )
        db.add(approval)
        await db.flush()
        return approval

    @staticmethod
    async def get_by_session(session_id: UUID, *, db: AsyncSession) -> ExamBoardCourseApproval | None:
        result = await db.execute(
            select(ExamBoardCourseApproval)
            .where(ExamBoardCourseApproval.session_id == session_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def set_approval_status(
        approval: ExamBoardCourseApproval,
        status: BoardApprovalStatus,
        *,
        db: AsyncSession,
    ) -> None:
        approval.approval_status = status.value
        await db.flush()


# ---------------------------------------------------------------------------
# RevaluationRepository — M09.3 Revaluation Workflow
# ---------------------------------------------------------------------------

class RevaluationRepository:
    """
    Revaluation request CRUD.
    Every modification is a direct column update; no row is ever deleted.
    """

    @staticmethod
    async def create(
        script_id: UUID,
        exam_paper_id: UUID,
        student_user_id: UUID,
        student_roll_ref: str | None,
        original_total: float,
        max_marks: float,
        reason: str,
        payment_reference: str | None,
        window_closes_at,
        *,
        db: AsyncSession,
    ) -> RevaluationRequest:
        req = RevaluationRequest(
            script_id=script_id,
            exam_paper_id=exam_paper_id,
            student_user_id=student_user_id,
            student_roll_ref=student_roll_ref,
            original_total=original_total,
            max_marks=max_marks,
            reason=reason,
            payment_reference=payment_reference,
            status=RevaluationStatus.SUBMITTED.value,
            window_closes_at=window_closes_at,
        )
        db.add(req)
        await db.flush()
        return req

    @staticmethod
    async def get_by_id(request_id: UUID, *, db: AsyncSession) -> RevaluationRequest | None:
        result = await db.execute(
            select(RevaluationRequest).where(RevaluationRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_paper(
        exam_paper_id: UUID,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[RevaluationRequest]:
        q = select(RevaluationRequest).where(
            RevaluationRequest.exam_paper_id == exam_paper_id
        )
        if status:
            q = q.where(RevaluationRequest.status == status)
        q = q.order_by(RevaluationRequest.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def list_for_student(
        student_user_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[RevaluationRequest]:
        q = (
            select(RevaluationRequest)
            .where(RevaluationRequest.student_user_id == student_user_id)
            .order_by(RevaluationRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def count_open_for_script(script_id: UUID, *, db: AsyncSession) -> int:
        """Count active (non-rejected, non-closed) requests for a script."""
        active = {
            RevaluationStatus.SUBMITTED.value,
            RevaluationStatus.ACCEPTED.value,
            RevaluationStatus.IN_PROGRESS.value,
            RevaluationStatus.EVALUATED.value,
            RevaluationStatus.BOARD_REVIEW.value,
        }
        result = await db.execute(
            select(func.count(RevaluationRequest.id)).where(
                RevaluationRequest.script_id == script_id,
                RevaluationRequest.status.in_(active),
            )
        )
        return result.scalar_one() or 0

    @staticmethod
    async def accept(
        req: RevaluationRequest,
        assigned_evaluator_id: UUID,
        admin_notes: str | None,
        *,
        db: AsyncSession,
    ) -> None:
        req.status = RevaluationStatus.ACCEPTED.value
        req.assigned_evaluator_id = assigned_evaluator_id
        req.admin_notes = admin_notes
        await db.flush()

    @staticmethod
    async def reject_intake(
        req: RevaluationRequest,
        admin_notes: str,
        decided_by: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        from datetime import datetime, timezone
        req.status = RevaluationStatus.REJECTED.value
        req.admin_notes = admin_notes
        req.decided_by = decided_by
        req.decided_at = datetime.now(timezone.utc)
        await db.flush()

    @staticmethod
    async def set_in_progress(req: RevaluationRequest, *, db: AsyncSession) -> None:
        req.status = RevaluationStatus.IN_PROGRESS.value
        await db.flush()

    @staticmethod
    async def submit_marks(
        req: RevaluationRequest,
        revaluation_total: float,
        *,
        db: AsyncSession,
    ) -> None:
        req.status = RevaluationStatus.EVALUATED.value
        req.revaluation_total = revaluation_total
        await db.flush()

    @staticmethod
    async def forward_to_board(req: RevaluationRequest, *, db: AsyncSession) -> None:
        req.status = RevaluationStatus.BOARD_REVIEW.value
        await db.flush()

    @staticmethod
    async def board_ratify(
        req: RevaluationRequest,
        decided_by: UUID,
        board_remarks: str | None,
        *,
        db: AsyncSession,
    ) -> None:
        from datetime import datetime, timezone
        awarded = max(float(req.original_total), float(req.revaluation_total or 0))
        req.status = RevaluationStatus.APPROVED.value
        req.awarded_total = awarded
        req.decided_by = decided_by
        req.decided_at = datetime.now(timezone.utc)
        req.board_remarks = board_remarks
        await db.flush()

    @staticmethod
    async def board_reject(
        req: RevaluationRequest,
        decided_by: UUID,
        board_remarks: str,
        *,
        db: AsyncSession,
    ) -> None:
        from datetime import datetime, timezone
        req.status = RevaluationStatus.REJECTED_BY_BOARD.value
        req.decided_by = decided_by
        req.decided_at = datetime.now(timezone.utc)
        req.board_remarks = board_remarks
        await db.flush()

    @staticmethod
    async def close(req: RevaluationRequest, *, db: AsyncSession) -> None:
        req.status = RevaluationStatus.CLOSED.value
        await db.flush()


class RevaluationEvaluationRepository:
    """Per-question marks for a revaluation request."""

    @staticmethod
    async def bulk_create(
        request_id: UUID,
        marks: list[dict],  # [{question_id, question_type, max_marks, original_marks, revaluation_marks, note}]
        *,
        db: AsyncSession,
    ) -> list[RevaluationEvaluation]:
        rows = []
        for m in marks:
            row = RevaluationEvaluation(
                request_id=request_id,
                question_id=m["question_id"],
                question_type=m.get("question_type"),
                max_marks=m.get("max_marks"),
                original_marks=m.get("original_marks"),
                revaluation_marks=m["revaluation_marks"],
                evaluator_note=m.get("evaluator_note"),
            )
            db.add(row)
            rows.append(row)
        await db.flush()
        return rows

    @staticmethod
    async def list_for_request(
        request_id: UUID, *, db: AsyncSession
    ) -> list[RevaluationEvaluation]:
        result = await db.execute(
            select(RevaluationEvaluation)
            .where(RevaluationEvaluation.request_id == request_id)
            .order_by(RevaluationEvaluation.created_at)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# DigitalExamSessionRepository — M09.5
# ---------------------------------------------------------------------------

class DigitalSessionRepository:

    @staticmethod
    async def create(
        *,
        exam_paper_id: UUID,
        created_by: UUID,
        title: str,
        max_duration_mins: int,
        window_start,
        window_end,
        instructions: str | None,
        db: AsyncSession,
    ) -> DigitalExamSession:
        session = DigitalExamSession(
            exam_paper_id=exam_paper_id,
            created_by=created_by,
            title=title,
            max_duration_mins=max_duration_mins,
            window_start=window_start,
            window_end=window_end,
            instructions=instructions,
        )
        db.add(session)
        await db.flush()
        return session

    @staticmethod
    async def get(session_id: UUID, *, db: AsyncSession) -> DigitalExamSession | None:
        result = await db.execute(
            select(DigitalExamSession).where(DigitalExamSession.id == session_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        *,
        exam_paper_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[DigitalExamSession], int]:
        q = select(DigitalExamSession)
        if exam_paper_id:
            q = q.where(DigitalExamSession.exam_paper_id == exam_paper_id)
        total_result = await db.execute(
            select(func.count()).select_from(q.subquery())
        )
        total = total_result.scalar_one()
        result = await db.execute(
            q.order_by(DigitalExamSession.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def activate(session: DigitalExamSession, *, db: AsyncSession) -> DigitalExamSession:
        session.status = DigitalExamSessionStatus.ACTIVE
        session.activated_at = datetime.now(timezone.utc)
        await db.flush()
        return session

    @staticmethod
    async def close(session: DigitalExamSession, *, db: AsyncSession) -> DigitalExamSession:
        session.status = DigitalExamSessionStatus.CLOSED
        session.closed_at = datetime.now(timezone.utc)
        await db.flush()
        return session

    @staticmethod
    async def count_attempts(session_id: UUID, *, db: AsyncSession) -> tuple[int, int]:
        """Returns (total_attempts, scored_count)."""
        total_r = await db.execute(
            select(func.count()).where(DigitalExamAttempt.session_id == session_id)
        )
        scored_r = await db.execute(
            select(func.count()).where(
                DigitalExamAttempt.session_id == session_id,
                DigitalExamAttempt.status == DigitalAttemptStatus.SCORED,
            )
        )
        return total_r.scalar_one(), scored_r.scalar_one()


# ---------------------------------------------------------------------------
# DigitalAttemptRepository — M09.5
# ---------------------------------------------------------------------------

class DigitalAttemptRepository:

    @staticmethod
    async def get_for_student(
        session_id: UUID, student_user_id: UUID, *, db: AsyncSession
    ) -> DigitalExamAttempt | None:
        result = await db.execute(
            select(DigitalExamAttempt).where(
                DigitalExamAttempt.session_id == session_id,
                DigitalExamAttempt.student_user_id == student_user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get(attempt_id: UUID, *, db: AsyncSession) -> DigitalExamAttempt | None:
        result = await db.execute(
            select(DigitalExamAttempt).where(DigitalExamAttempt.id == attempt_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        *,
        session_id: UUID,
        student_user_id: UUID,
        expires_at,
        db: AsyncSession,
    ) -> DigitalExamAttempt:
        attempt = DigitalExamAttempt(
            session_id=session_id,
            student_user_id=student_user_id,
            expires_at=expires_at,
            status=DigitalAttemptStatus.IN_PROGRESS,
        )
        db.add(attempt)
        await db.flush()
        return attempt

    @staticmethod
    async def mark_submitted(
        attempt: DigitalExamAttempt, *, db: AsyncSession
    ) -> DigitalExamAttempt:
        attempt.status = DigitalAttemptStatus.SUBMITTED
        attempt.submitted_at = datetime.now(timezone.utc)
        await db.flush()
        return attempt

    @staticmethod
    async def mark_scored(
        attempt: DigitalExamAttempt,
        auto_score: float,
        mcq_max_score: float,
        *,
        db: AsyncSession,
    ) -> DigitalExamAttempt:
        attempt.status = DigitalAttemptStatus.SCORED
        attempt.auto_score = auto_score
        attempt.mcq_max_score = mcq_max_score
        attempt.auto_scored_at = datetime.now(timezone.utc)
        await db.flush()
        return attempt

    @staticmethod
    async def mark_fully_evaluated(
        attempt: DigitalExamAttempt, *, db: AsyncSession
    ) -> DigitalExamAttempt:
        """Set status → FULLY_EVALUATED after faculty submits all subjective scores."""
        attempt.status = DigitalAttemptStatus.FULLY_EVALUATED
        await db.flush()
        return attempt

    @staticmethod
    async def list_for_session(
        session_id: UUID, *, db: AsyncSession
    ) -> list[DigitalExamAttempt]:
        result = await db.execute(
            select(DigitalExamAttempt)
            .where(DigitalExamAttempt.session_id == session_id)
            .order_by(DigitalExamAttempt.started_at)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# DigitalResponseRepository — M09.5
# ---------------------------------------------------------------------------

class DigitalResponseRepository:

    @staticmethod
    async def upsert(
        *,
        attempt_id: UUID,
        question_id: UUID,
        question_type: str | None,
        selected_option: str | None,
        response_text: str | None,
        db: AsyncSession,
    ) -> DigitalExamResponse:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(DigitalExamResponse).where(
                DigitalExamResponse.attempt_id == attempt_id,
                DigitalExamResponse.question_id == question_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.selected_option = selected_option
            existing.response_text = response_text
            existing.answered_at = now
            existing.updated_at = now
            await db.flush()
            return existing
        response = DigitalExamResponse(
            attempt_id=attempt_id,
            question_id=question_id,
            question_type=question_type,
            selected_option=selected_option,
            response_text=response_text,
            answered_at=now,
        )
        db.add(response)
        await db.flush()
        return response

    @staticmethod
    async def list_for_attempt(
        attempt_id: UUID, *, db: AsyncSession
    ) -> list[DigitalExamResponse]:
        result = await db.execute(
            select(DigitalExamResponse)
            .where(DigitalExamResponse.attempt_id == attempt_id)
            .order_by(DigitalExamResponse.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_subjective_for_attempt(
        attempt_id: UUID, *, db: AsyncSession
    ) -> list[DigitalExamResponse]:
        """Return only non-MCQ responses for an attempt, ordered by creation."""
        result = await db.execute(
            select(DigitalExamResponse)
            .where(
                DigitalExamResponse.attempt_id == attempt_id,
                DigitalExamResponse.question_type != "MCQ",
            )
            .order_by(DigitalExamResponse.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_attempt_and_question(
        attempt_id: UUID, question_id: UUID, *, db: AsyncSession
    ) -> DigitalExamResponse | None:
        result = await db.execute(
            select(DigitalExamResponse).where(
                DigitalExamResponse.attempt_id == attempt_id,
                DigitalExamResponse.question_id == question_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def score_subjective(
        response: DigitalExamResponse,
        *,
        score: float,
        note: str | None,
        scored_by: UUID,
        db: AsyncSession,
    ) -> DigitalExamResponse:
        """Write faculty score for one subjective response. Human-gate only — never called by Celery."""
        response.faculty_score    = score
        response.faculty_note     = note
        response.faculty_scored_by = scored_by
        response.faculty_scored_at = datetime.now(timezone.utc)
        await db.flush()
        return response

    @staticmethod
    async def count_unscored_subjective(
        attempt_id: UUID, *, db: AsyncSession
    ) -> int:
        """Count subjective responses that still have faculty_score IS NULL."""
        result = await db.execute(
            select(func.count()).where(
                DigitalExamResponse.attempt_id == attempt_id,
                DigitalExamResponse.question_type != "MCQ",
                DigitalExamResponse.faculty_score.is_(None),
            )
        )
        return result.scalar_one()

    @staticmethod
    async def sum_faculty_scores(
        attempt_id: UUID, *, db: AsyncSession
    ) -> float:
        """Sum of all faculty_scores for subjective responses in an attempt."""
        result = await db.execute(
            select(func.coalesce(func.sum(DigitalExamResponse.faculty_score), 0)).where(
                DigitalExamResponse.attempt_id == attempt_id,
                DigitalExamResponse.question_type != "MCQ",
            )
        )
        return float(result.scalar() or 0.0)

    @staticmethod
    async def list_scored_for_session_with_pending_subjective(
        session_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[DigitalExamAttempt], int]:
        """
        Return SCORED attempts that have at least one unscored subjective response.
        Used to build the faculty review queue.
        """
        from sqlalchemy import exists as sa_exists

        pending_subq = (
            select(DigitalExamResponse.id)
            .where(
                DigitalExamResponse.attempt_id == DigitalExamAttempt.id,
                DigitalExamResponse.question_type != "MCQ",
                DigitalExamResponse.faculty_score.is_(None),
            )
            .correlate(DigitalExamAttempt)
        )
        base_q = select(DigitalExamAttempt).where(
            DigitalExamAttempt.session_id == session_id,
            DigitalExamAttempt.status == DigitalAttemptStatus.SCORED,
            sa_exists(pending_subq),
        )
        count_result = await db.execute(
            select(func.count()).select_from(base_q.subquery())
        )
        total = count_result.scalar_one()
        result = await db.execute(
            base_q.order_by(DigitalExamAttempt.submitted_at).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def score_mcq(
        response: DigitalExamResponse,
        correct_option: str | None,
        marks: float,
        *,
        db: AsyncSession,
    ) -> DigitalExamResponse:
        is_correct = (
            response.selected_option is not None
            and correct_option is not None
            and response.selected_option.upper() == correct_option.upper()
        )
        response.is_auto_scored = True
        response.is_correct = is_correct
        response.auto_score = float(marks) if is_correct else 0.0
        await db.flush()
        return response
