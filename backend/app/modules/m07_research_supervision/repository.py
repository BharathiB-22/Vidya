"""
M07 Research Supervision — Repository layer.

All methods are static and accept an AsyncSession that already has the
correct search_path set (tenant schema).  No method reads or writes the
public schema except TaskJobPublicRepository.

Human-gate invariant enforced here:
  - set_problem_status accepts only AI-writable statuses;
    guide decision endpoint calls set_guide_decision directly.
  - set_document_status accepts only AI-writable statuses;
    guide review endpoint calls set_guide_review directly.
  - set_viva_status accepts only task-writable statuses;
    guide ratify endpoint calls set_guide_ratification directly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.m07_research_supervision.models import (
    DocumentStatus,
    ProblemStatus,
    ResearchDocument,
    ResearchProblem,
    VivaSession,
    VivaStatus,
)


# ---------------------------------------------------------------------------
# ProblemRepository
# ---------------------------------------------------------------------------

class ProblemRepository:

    @staticmethod
    async def create(
        *,
        guide_user_id: UUID,
        student_user_id: UUID | None,
        title: str,
        abstract: str | None,
        research_questions: list[dict],
        source: str,
        db: AsyncSession,
    ) -> ResearchProblem:
        obj = ResearchProblem(
            guide_user_id=guide_user_id,
            student_user_id=student_user_id,
            title=title,
            abstract=abstract,
            research_questions=research_questions,
            source=source,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get_by_id(
        problem_id: UUID,
        *,
        db: AsyncSession,
    ) -> ResearchProblem | None:
        result = await db.execute(
            select(ResearchProblem).where(ResearchProblem.id == problem_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_guide(
        guide_user_id: UUID,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[ResearchProblem], int]:
        q = select(ResearchProblem).where(ResearchProblem.guide_user_id == guide_user_id)
        if status:
            q = q.where(ResearchProblem.status == status)
        total_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(total_q)).scalar_one()
        items = (
            await db.execute(q.order_by(ResearchProblem.created_at.desc()).offset(offset).limit(limit))
        ).scalars().all()
        return list(items), total

    @staticmethod
    async def list_by_student(
        student_user_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[ResearchProblem], int]:
        q = select(ResearchProblem).where(ResearchProblem.student_user_id == student_user_id)
        total_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(total_q)).scalar_one()
        items = (
            await db.execute(q.order_by(ResearchProblem.created_at.desc()).offset(offset).limit(limit))
        ).scalars().all()
        return list(items), total

    @staticmethod
    async def set_eval_scores(
        problem_id: UUID,
        *,
        novelty_score: float,
        feasibility_score: float,
        clarity_score: float,
        ai_recommendation: str,
        ai_reasoning: str,
        ai_model: str,
        prompt_hash: str,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(ResearchProblem)
            .where(ResearchProblem.id == problem_id)
            .values(
                novelty_score=novelty_score,
                feasibility_score=feasibility_score,
                clarity_score=clarity_score,
                ai_recommendation=ai_recommendation,
                ai_reasoning=ai_reasoning,
                ai_model=ai_model,
                prompt_hash=prompt_hash,
                status=ProblemStatus.PENDING_REVIEW,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_eval_job(
        problem_id: UUID,
        *,
        job_id: UUID,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(ResearchProblem)
            .where(ResearchProblem.id == problem_id)
            .values(eval_job_id=job_id, updated_at=datetime.now(timezone.utc))
        )

    @staticmethod
    async def set_guide_decision(
        problem_id: UUID,
        *,
        guide_decision: str,
        guide_note: str | None,
        new_status: str,
        db: AsyncSession,
    ) -> ResearchProblem | None:
        """Human gate: called only by guide decision endpoint."""
        await db.execute(
            update(ResearchProblem)
            .where(ResearchProblem.id == problem_id)
            .values(
                guide_decision=guide_decision,
                guide_note=guide_note,
                status=new_status,
                decided_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        return await ProblemRepository.get_by_id(problem_id, db=db)

    @staticmethod
    async def assign_student(
        problem_id: UUID,
        *,
        student_user_id: UUID,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(ResearchProblem)
            .where(ResearchProblem.id == problem_id)
            .values(student_user_id=student_user_id, updated_at=datetime.now(timezone.utc))
        )

    @staticmethod
    async def update_fields(
        problem_id: UUID,
        *,
        fields: dict,
        db: AsyncSession,
    ) -> ResearchProblem | None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await db.execute(
            update(ResearchProblem)
            .where(ResearchProblem.id == problem_id)
            .values(**fields)
        )
        return await ProblemRepository.get_by_id(problem_id, db=db)


# ---------------------------------------------------------------------------
# DocumentRepository
# ---------------------------------------------------------------------------

class DocumentRepository:

    @staticmethod
    async def create(
        *,
        research_problem_id: UUID,
        student_user_id: UUID,
        file_url: str | None,
        file_name: str | None,
        version: int,
        db: AsyncSession,
    ) -> ResearchDocument:
        obj = ResearchDocument(
            research_problem_id=research_problem_id,
            student_user_id=student_user_id,
            file_url=file_url,
            file_name=file_name,
            version=version,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get_by_id(
        doc_id: UUID,
        *,
        db: AsyncSession,
    ) -> ResearchDocument | None:
        result = await db.execute(
            select(ResearchDocument).where(ResearchDocument.id == doc_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_for_problem(
        research_problem_id: UUID,
        *,
        db: AsyncSession,
    ) -> ResearchDocument | None:
        result = await db.execute(
            select(ResearchDocument)
            .where(ResearchDocument.research_problem_id == research_problem_id)
            .order_by(ResearchDocument.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_problem(
        research_problem_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[ResearchDocument]:
        result = await db.execute(
            select(ResearchDocument)
            .where(ResearchDocument.research_problem_id == research_problem_id)
            .order_by(ResearchDocument.version.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_by_guide(
        guide_user_id: UUID,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[ResearchDocument], int]:
        """List documents where the research_problem belongs to this guide."""
        q = (
            select(ResearchDocument)
            .join(ResearchProblem, ResearchDocument.research_problem_id == ResearchProblem.id)
            .where(ResearchProblem.guide_user_id == guide_user_id)
        )
        if status:
            q = q.where(ResearchDocument.status == status)
        total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        items = (
            await db.execute(q.order_by(ResearchDocument.submitted_at.desc()).offset(offset).limit(limit))
        ).scalars().all()
        return list(items), total

    @staticmethod
    async def set_status(
        doc_id: UUID,
        status: str,
        *,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(ResearchDocument)
            .where(ResearchDocument.id == doc_id)
            .values(status=status)
        )

    @staticmethod
    async def set_eval_result(
        doc_id: UUID,
        *,
        plagiarism_score: float,
        ai_content_score: float,
        format_score: float,
        clarity_score: float,
        evaluation_report: dict,
        ai_model: str,
        prompt_hash: str,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(ResearchDocument)
            .where(ResearchDocument.id == doc_id)
            .values(
                plagiarism_score=plagiarism_score,
                ai_content_score=ai_content_score,
                format_score=format_score,
                clarity_score=clarity_score,
                evaluation_report=evaluation_report,
                ai_model=ai_model,
                prompt_hash=prompt_hash,
                status=DocumentStatus.EVALUATED,
            )
        )

    @staticmethod
    async def set_eval_job(
        doc_id: UUID,
        *,
        job_id: UUID,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(ResearchDocument)
            .where(ResearchDocument.id == doc_id)
            .values(eval_job_id=job_id, status=DocumentStatus.EVALUATING)
        )

    @staticmethod
    async def set_guide_review(
        doc_id: UUID,
        *,
        guide_comment: str | None,
        new_status: str,
        db: AsyncSession,
    ) -> ResearchDocument | None:
        """Human gate: called only by guide review endpoint."""
        await db.execute(
            update(ResearchDocument)
            .where(ResearchDocument.id == doc_id)
            .values(
                guide_comment=guide_comment,
                new_status=new_status,
                guide_reviewed_at=datetime.now(timezone.utc),
                status=new_status,
            )
        )
        return await DocumentRepository.get_by_id(doc_id, db=db)

    @staticmethod
    async def next_version_for_problem(
        research_problem_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        result = await db.execute(
            select(func.max(ResearchDocument.version))
            .where(ResearchDocument.research_problem_id == research_problem_id)
        )
        max_v = result.scalar_one_or_none()
        return (max_v or 0) + 1


# ---------------------------------------------------------------------------
# VivaRepository
# ---------------------------------------------------------------------------

class VivaRepository:

    @staticmethod
    async def create(
        *,
        research_problem_id: UUID,
        document_id: UUID,
        student_user_id: UUID,
        guide_user_id: UUID,
        session_token: str,
        ai_questions: list[dict],
        scheduled_at: datetime | None,
        expires_at: datetime | None,
        db: AsyncSession,
    ) -> VivaSession:
        obj = VivaSession(
            research_problem_id=research_problem_id,
            document_id=document_id,
            student_user_id=student_user_id,
            guide_user_id=guide_user_id,
            session_token=session_token,
            ai_questions=ai_questions,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get_by_id(
        viva_id: UUID,
        *,
        db: AsyncSession,
    ) -> VivaSession | None:
        result = await db.execute(
            select(VivaSession).where(VivaSession.id == viva_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_token(
        token: str,
        *,
        db: AsyncSession,
    ) -> VivaSession | None:
        result = await db.execute(
            select(VivaSession).where(VivaSession.session_token == token)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_guide(
        guide_user_id: UUID,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[VivaSession], int]:
        q = select(VivaSession).where(VivaSession.guide_user_id == guide_user_id)
        if status:
            q = q.where(VivaSession.status == status)
        total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        items = (
            await db.execute(q.order_by(VivaSession.scheduled_at.desc()).offset(offset).limit(limit))
        ).scalars().all()
        return list(items), total

    @staticmethod
    async def list_by_student(
        student_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[VivaSession]:
        result = await db.execute(
            select(VivaSession)
            .where(VivaSession.student_user_id == student_user_id)
            .order_by(VivaSession.scheduled_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def record_consent(
        viva_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(VivaSession)
            .where(VivaSession.id == viva_id)
            .values(consent_recorded=True, status=VivaStatus.IN_PROGRESS)
        )

    @staticmethod
    async def append_response(
        viva_id: UUID,
        *,
        question_id: str,
        response_text: str,
        start_ms: int | None,
        end_ms: int | None,
        db: AsyncSession,
    ) -> None:
        """Append one student response to the ai_responses JSONB array."""
        from sqlalchemy import text as sa_text
        new_response = {
            "question_id":   question_id,
            "response_text": response_text,
            "start_ms":      start_ms,
            "end_ms":        end_ms,
        }
        import json
        await db.execute(
            sa_text(
                "UPDATE viva_sessions "
                "SET ai_responses = ai_responses || :resp::jsonb "
                "WHERE id = :vid"
            ),
            {"resp": json.dumps([new_response]), "vid": str(viva_id)},
        )

    @staticmethod
    async def set_recording(
        viva_id: UUID,
        *,
        video_url: str,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(VivaSession)
            .where(VivaSession.id == viva_id)
            .values(
                video_url=video_url,
                status=VivaStatus.COMPLETED,
                completed_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def set_eval_job(
        viva_id: UUID,
        *,
        job_id: UUID,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(VivaSession)
            .where(VivaSession.id == viva_id)
            .values(eval_job_id=job_id, status=VivaStatus.ASR_PROCESSING)
        )

    @staticmethod
    async def set_ai_evaluation(
        viva_id: UUID,
        *,
        transcript: str,
        ai_evaluation: list[dict],
        overall_ai_score: float,
        ai_model: str,
        db: AsyncSession,
    ) -> None:
        """Written ONLY by Celery process_viva_session task."""
        await db.execute(
            update(VivaSession)
            .where(VivaSession.id == viva_id)
            .values(
                transcript=transcript,
                ai_evaluation=ai_evaluation,
                overall_ai_score=overall_ai_score,
                ai_model=ai_model,
                status=VivaStatus.EVALUATED,
            )
        )

    @staticmethod
    async def set_guide_ratification(
        viva_id: UUID,
        *,
        guide_evaluation: list[dict],
        overall_guide_score: float,
        db: AsyncSession,
    ) -> VivaSession | None:
        """Human gate: called only by guide ratify endpoint."""
        await db.execute(
            update(VivaSession)
            .where(VivaSession.id == viva_id)
            .values(
                guide_evaluation=guide_evaluation,
                overall_guide_score=overall_guide_score,
                status=VivaStatus.GUIDE_RATIFIED,
                ratified_at=datetime.now(timezone.utc),
            )
        )
        return await VivaRepository.get_by_id(viva_id, db=db)


# ---------------------------------------------------------------------------
# TaskJobPublicRepository — same public schema pattern as M06
# ---------------------------------------------------------------------------

from app.modules.m06_labs_evaluator.repository import (
    TaskJobPublicRepository,  # noqa: F401  re-exported for use in service.py
)
