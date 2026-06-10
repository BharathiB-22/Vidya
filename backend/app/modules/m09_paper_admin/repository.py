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
    ModerationStatus,
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
