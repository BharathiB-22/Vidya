"""
M07 Research Supervision — Service layer.

Architecture contract:
  - All business logic here; router is pure HTTP glue.
  - ResearchServiceError carries code, message, status_code for HTTP translation.
  - Celery task dispatch via TaskJobPublicRepository.
  - Human gates enforced here AND in the repository:
      ProblemService.guide_decide() → only way status reaches ACCEPTED/REJECTED
      DocumentService.guide_review() → only way status reaches APPROVED
      VivaService.ratify() → only way status reaches GUIDE_RATIFIED
  - AI results NEVER advance any status past EVALUATED without human action.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m07_research_supervision.models import (
    DocumentStatus,
    ProblemStatus,
    VivaStatus,
)
from app.modules.m07_research_supervision.repository import (
    DocumentRepository,
    ProblemRepository,
    TaskJobPublicRepository,
    VivaRepository,
)
from app.modules.m07_research_supervision.schemas import (
    DocumentSubmit,
    GuideDecisionRequest,
    GuideDocumentReviewRequest,
    ProblemCreate,
    VivaRatifyRequest,
    VivaScheduleRequest,
)

logger = logging.getLogger("vidya.service.m07")


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class ResearchServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# ProblemService
# ---------------------------------------------------------------------------

class ProblemService:

    @staticmethod
    async def create_student_proposal(
        payload: ProblemCreate,
        *,
        student_user_id: UUID,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ):
        """Create a student-proposed research problem and queue evaluation."""
        # Validate guide: must exist in tenant, role=GUIDE, is_active
        from sqlalchemy import select
        from app.core.auth.models import User, TenantRole
        row = await db.execute(select(User).where(User.id == payload.guide_user_id))
        guide = row.scalar_one_or_none()
        if guide is None or guide.role != TenantRole.GUIDE or not guide.is_active:
            raise ResearchServiceError(
                "INVALID_GUIDE",
                "Guide not found or is not an active GUIDE in this institution. "
                "Please verify the UUID from Admin → Users.",
                400,
            )

        # Prevent duplicate active proposals to the same guide
        duplicate = await ProblemRepository.find_active_by_student(
            student_user_id=student_user_id,
            guide_user_id=payload.guide_user_id,
            db=db,
        )
        if duplicate is not None:
            raise ResearchServiceError(
                "DUPLICATE_PROPOSAL",
                "You already have an active research proposal with this guide. "
                "Please wait for their decision before submitting another.",
                409,
            )

        problem = await ProblemRepository.create(
            guide_user_id=payload.guide_user_id,
            student_user_id=student_user_id,
            title=payload.title,
            abstract=payload.abstract,
            research_questions=[q.model_dump() for q in payload.research_questions],
            source="STUDENT_PROPOSED",
            db=db,
        )
        await db.commit()
        await db.refresh(problem)

        # Dispatch Celery evaluation task
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as pub_db:
            job_id = await TaskJobPublicRepository.create(
                tenant_id=tenant_id,
                task_type="evaluate_research_proposal",
                queue_name="heavy",
                payload={"problem_id": str(problem.id), "schema_name": schema_name},
                db=pub_db,
            )
            await pub_db.commit()

        await ProblemRepository.set_eval_job(problem.id, job_id=job_id, db=db)
        await db.commit()

        from app.workers.heavy.evaluate_research_proposal import evaluate_research_proposal
        evaluate_research_proposal.apply_async(
            kwargs={
                "job_id":      str(job_id),
                "problem_id":  str(problem.id),
                "schema_name": schema_name,
            },
            queue="celery-heavy",
        )
        return problem, job_id

    @staticmethod
    async def get(problem_id: UUID, *, db: AsyncSession):
        obj = await ProblemRepository.get_by_id(problem_id, db=db)
        if obj is None:
            raise ResearchServiceError("NOT_FOUND", "Research problem not found.", 404)
        return obj

    @staticmethod
    async def list_for_guide(
        guide_user_id: UUID,
        *,
        status: str | None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ):
        return await ProblemRepository.list_by_guide(
            guide_user_id, status=status, offset=offset, limit=limit, db=db
        )

    @staticmethod
    async def list_for_student(
        student_user_id: UUID,
        *,
        offset: int,
        limit: int,
        db: AsyncSession,
    ):
        return await ProblemRepository.list_by_student(
            student_user_id, offset=offset, limit=limit, db=db
        )

    @staticmethod
    async def guide_decide(
        problem_id: UUID,
        payload: GuideDecisionRequest,
        *,
        guide_user_id: UUID,
        db: AsyncSession,
    ):
        """HUMAN GATE 1: Guide makes explicit decision on a research problem."""
        problem = await ProblemRepository.get_by_id(problem_id, db=db)
        if problem is None:
            raise ResearchServiceError("NOT_FOUND", "Research problem not found.", 404)

        if problem.guide_user_id != guide_user_id:
            raise ResearchServiceError("FORBIDDEN", "Only the assigned guide can decide.", 403)

        if problem.status not in (
            ProblemStatus.PENDING_REVIEW.value,
            ProblemStatus.REVISION_REQUESTED.value,
        ):
            raise ResearchServiceError(
                "INVALID_STATUS",
                f"Cannot decide on problem with status {problem.status!r}.",
            )

        decision_to_status = {
            "ACCEPT": ProblemStatus.ACCEPTED.value,
            "REVISE": ProblemStatus.REVISION_REQUESTED.value,
            "REJECT": ProblemStatus.REJECTED.value,
        }
        new_status = decision_to_status[payload.decision]

        updated = await ProblemRepository.set_guide_decision(
            problem_id,
            guide_decision=payload.decision,
            guide_note=payload.guide_note,
            new_status=new_status,
            db=db,
        )
        await db.commit()
        return updated

    @staticmethod
    async def create_ai_generated(
        guide_user_id: UUID,
        research_area: str,
        num_problems: int,
    ) -> list[dict]:
        """Generate AI research problems for a guide (returns raw dict list, not stored)."""
        from app.modules.m07_research_supervision.problem_generator import generate_problems
        result = await generate_problems(research_area, num_problems=num_problems)
        return result

    @staticmethod
    async def store_ai_generated_problem(
        guide_user_id: UUID,
        title: str,
        abstract: str,
        research_questions: list[str],
        *,
        db: AsyncSession,
    ):
        """Guide selects one AI-generated problem to offer to students."""
        problem = await ProblemRepository.create(
            guide_user_id=guide_user_id,
            student_user_id=None,
            title=title,
            abstract=abstract,
            research_questions=[{"question": q} for q in research_questions],
            source="AI_GENERATED",
            db=db,
        )
        # AI-generated problems start as DRAFT (no student yet; no eval needed)
        await db.execute(
            __import__("sqlalchemy", fromlist=["update"]).update(
                __import__("app.modules.m07_research_supervision.models", fromlist=["ResearchProblem"]).ResearchProblem
            )
            .where(
                __import__("app.modules.m07_research_supervision.models", fromlist=["ResearchProblem"]).ResearchProblem.id == problem.id
            )
            .values(status=ProblemStatus.DRAFT.value)
        )
        await db.commit()
        await db.refresh(problem)
        return problem


# ---------------------------------------------------------------------------
# DocumentService
# ---------------------------------------------------------------------------

class DocumentService:

    @staticmethod
    async def submit(
        payload: DocumentSubmit,
        *,
        student_user_id: UUID,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ):
        """Student submits a research document and queues evaluation."""
        # Verify the research problem exists and student is assigned to it
        problem = await ProblemRepository.get_by_id(payload.research_problem_id, db=db)
        if problem is None:
            raise ResearchServiceError("NOT_FOUND", "Research problem not found.", 404)
        if problem.student_user_id != student_user_id:
            raise ResearchServiceError(
                "FORBIDDEN", "You are not assigned to this research problem.", 403
            )
        if problem.status != ProblemStatus.ACCEPTED.value:
            raise ResearchServiceError(
                "INVALID_STATUS",
                f"Cannot submit document for a problem with status {problem.status!r}. "
                "The problem must be ACCEPTED first.",
            )

        # Compute next version number
        version = await DocumentRepository.next_version_for_problem(
            payload.research_problem_id, db=db
        )
        doc = await DocumentRepository.create(
            research_problem_id=payload.research_problem_id,
            student_user_id=student_user_id,
            file_url=payload.file_url,
            file_name=payload.file_name,
            version=version,
            db=db,
        )
        await db.commit()
        await db.refresh(doc)

        # Only dispatch evaluation immediately when the file is already uploaded
        # (one-step flow). For the two-step flow (file_url=None), dispatch
        # happens in update_file_url() after the PATCH confirms the upload.
        job_id = None
        if payload.file_url:
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as pub_db:
                job_id = await TaskJobPublicRepository.create(
                    tenant_id=tenant_id,
                    task_type="evaluate_research_document",
                    queue_name="heavy",
                    payload={"document_id": str(doc.id), "schema_name": schema_name},
                    db=pub_db,
                )
                await pub_db.commit()

            await DocumentRepository.set_eval_job(doc.id, job_id=job_id, db=db)
            await db.commit()

            from app.workers.heavy.evaluate_research_document import evaluate_research_document
            evaluate_research_document.apply_async(
                kwargs={
                    "job_id":      str(job_id),
                    "document_id": str(doc.id),
                    "schema_name": schema_name,
                },
                queue="celery-heavy",
            )

        return doc, job_id

    @staticmethod
    async def get(doc_id: UUID, *, db: AsyncSession):
        obj = await DocumentRepository.get_by_id(doc_id, db=db)
        if obj is None:
            raise ResearchServiceError("NOT_FOUND", "Research document not found.", 404)
        return obj

    @staticmethod
    async def list_for_guide(
        guide_user_id: UUID,
        *,
        status: str | None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ):
        return await DocumentRepository.list_by_guide(
            guide_user_id, status=status, offset=offset, limit=limit, db=db
        )

    @staticmethod
    async def list_for_problem(research_problem_id: UUID, *, db: AsyncSession):
        return await DocumentRepository.list_for_problem(research_problem_id, db=db)

    @staticmethod
    async def guide_review(
        doc_id: UUID,
        payload: GuideDocumentReviewRequest,
        *,
        guide_user_id: UUID,
        db: AsyncSession,
    ):
        """HUMAN GATE 2: Guide approves or requests revision on a document."""
        doc = await DocumentRepository.get_by_id(doc_id, db=db)
        if doc is None:
            raise ResearchServiceError("NOT_FOUND", "Research document not found.", 404)

        # Verify guide owns the parent problem
        problem = await ProblemRepository.get_by_id(doc.research_problem_id, db=db)
        if problem is None or problem.guide_user_id != guide_user_id:
            raise ResearchServiceError("FORBIDDEN", "Only the assigned guide can review.", 403)

        if doc.status not in (
            DocumentStatus.EVALUATED.value,
            DocumentStatus.GUIDE_REVIEWED.value,
        ):
            raise ResearchServiceError(
                "INVALID_STATUS",
                f"Cannot review document with status {doc.status!r}. Must be EVALUATED first.",
            )

        new_status = (
            DocumentStatus.APPROVED.value
            if payload.decision == "APPROVE"
            else DocumentStatus.REVISION_REQUESTED.value
        )

        updated = await DocumentRepository.set_guide_review(
            doc_id,
            guide_comment=payload.guide_comment,
            new_status=new_status,
            db=db,
        )
        await db.commit()
        return updated

    @staticmethod
    async def update_file_url(
        doc_id: UUID,
        *,
        file_url: str,
        file_name: str | None,
        student_user_id: UUID,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ):
        """Update file URL after presigned upload completes (two-step upload flow).

        Sets the confirmed S3 key on the document record, then queues
        evaluate_research_document so the AI pipeline sees the real file.
        """
        doc = await DocumentRepository.get_by_id(doc_id, db=db)
        if doc is None:
            raise ResearchServiceError("NOT_FOUND", "Document not found.", 404)
        if doc.student_user_id != student_user_id:
            raise ResearchServiceError("FORBIDDEN", "Access denied.", 403)

        from sqlalchemy import update as sa_update
        from app.modules.m07_research_supervision.models import ResearchDocument
        await db.execute(
            sa_update(ResearchDocument)
            .where(ResearchDocument.id == doc_id)
            .values(file_url=file_url, file_name=file_name)
        )
        await db.commit()

        # Dispatch evaluation now that the file is confirmed uploaded
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as pub_db:
            job_id = await TaskJobPublicRepository.create(
                tenant_id=tenant_id,
                task_type="evaluate_research_document",
                queue_name="heavy",
                payload={"document_id": str(doc_id), "schema_name": schema_name},
                db=pub_db,
            )
            await pub_db.commit()

        await DocumentRepository.set_eval_job(doc_id, job_id=job_id, db=db)
        await db.commit()

        from app.workers.heavy.evaluate_research_document import evaluate_research_document
        evaluate_research_document.apply_async(
            kwargs={
                "job_id":      str(job_id),
                "document_id": str(doc_id),
                "schema_name": schema_name,
            },
            queue="celery-heavy",
        )

        return await DocumentRepository.get_by_id(doc_id, db=db)


# ---------------------------------------------------------------------------
# VivaService
# ---------------------------------------------------------------------------

class VivaService:

    @staticmethod
    async def schedule(
        payload: VivaScheduleRequest,
        *,
        guide_user_id: UUID,
        db: AsyncSession,
    ):
        """Guide schedules a viva session and pre-generates questions."""
        # Validate problem
        problem = await ProblemRepository.get_by_id(payload.research_problem_id, db=db)
        if problem is None:
            raise ResearchServiceError("NOT_FOUND", "Research problem not found.", 404)
        if problem.guide_user_id != guide_user_id:
            raise ResearchServiceError("FORBIDDEN", "Only the assigned guide can schedule.", 403)
        if problem.status != ProblemStatus.ACCEPTED.value:
            raise ResearchServiceError(
                "INVALID_STATUS", "Research problem must be ACCEPTED before scheduling viva.", 400
            )

        # Validate document
        doc = await DocumentRepository.get_by_id(payload.document_id, db=db)
        if doc is None:
            raise ResearchServiceError("NOT_FOUND", "Research document not found.", 404)
        if doc.status != DocumentStatus.APPROVED.value:
            raise ResearchServiceError(
                "INVALID_STATUS", "Document must be APPROVED before scheduling viva.", 400
            )

        # Generate questions from document content (use mock text if no file extracted yet)
        doc_text = f"Research: {problem.title}\n{problem.abstract or ''}"
        from app.modules.m07_research_supervision.viva_engine import generate_base_questions
        questions = await generate_base_questions(doc_text, num_questions=6)

        # Session token + expiry
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=payload.session_ttl_hours)

        # Use caller-supplied student_user_id if provided; fall back to the
        # document record, which is the authoritative source after validation.
        effective_student_id = payload.student_user_id or doc.student_user_id

        viva = await VivaRepository.create(
            research_problem_id=payload.research_problem_id,
            document_id=payload.document_id,
            student_user_id=effective_student_id,
            guide_user_id=guide_user_id,
            session_token=token,
            ai_questions=[
                {
                    "id":           q.id,
                    "text":         q.text,
                    "source":       q.source,
                    "based_on_qid": q.based_on_qid,
                    "order":        q.order,
                }
                for q in questions
            ],
            scheduled_at=payload.scheduled_at or now,
            expires_at=expires_at,
            db=db,
        )
        await db.commit()
        await db.refresh(viva)
        return viva

    @staticmethod
    async def get(viva_id: UUID, *, db: AsyncSession):
        obj = await VivaRepository.get_by_id(viva_id, db=db)
        if obj is None:
            raise ResearchServiceError("NOT_FOUND", "Viva session not found.", 404)
        return obj

    @staticmethod
    async def get_by_token(token: str, *, db: AsyncSession):
        obj = await VivaRepository.get_by_token(token, db=db)
        if obj is None:
            raise ResearchServiceError("NOT_FOUND", "Session not found or expired.", 404)
        now = datetime.now(timezone.utc)
        if obj.expires_at and obj.expires_at < now:
            raise ResearchServiceError("SESSION_EXPIRED", "Viva session has expired.", 410)
        return obj

    @staticmethod
    async def record_consent(viva_id: UUID, *, db: AsyncSession):
        await VivaRepository.record_consent(viva_id, db=db)
        await db.commit()

    @staticmethod
    async def submit_response(
        viva_id: UUID,
        *,
        question_id: str,
        response_text: str,
        start_ms: int | None,
        end_ms: int | None,
        db: AsyncSession,
    ):
        """Student submits one response during the viva session."""
        viva = await VivaRepository.get_by_id(viva_id, db=db)
        if viva is None:
            raise ResearchServiceError("NOT_FOUND", "Viva session not found.", 404)
        if viva.status not in (VivaStatus.SCHEDULED.value, VivaStatus.IN_PROGRESS.value):
            raise ResearchServiceError(
                "INVALID_STATUS",
                f"Session not active (status={viva.status!r}).",
            )

        # Generate follow-up question if this is a base question response
        questions: list[dict] = list(viva.ai_questions or [])
        base_q = next((q for q in questions if q["id"] == question_id and q["source"] == "base"), None)
        new_followup = None
        if base_q:
            from app.modules.m07_research_supervision.viva_engine import generate_followup
            try:
                fq = await generate_followup(
                    base_question=base_q["text"],
                    student_response=response_text,
                    base_question_id=question_id,
                    order=len(questions) + 1,
                )
                new_followup = {
                    "id":           fq.id,
                    "text":         fq.text,
                    "source":       fq.source,
                    "based_on_qid": fq.based_on_qid,
                    "order":        fq.order,
                }
                # Append follow-up to session questions
                from sqlalchemy import update as sa_update
                from app.modules.m07_research_supervision.models import VivaSession
                import json as _json
                questions.append(new_followup)
                await db.execute(
                    sa_update(VivaSession)
                    .where(VivaSession.id == viva_id)
                    .values(ai_questions=questions)
                )
            except Exception as exc:
                logger.warning("Follow-up generation failed: %s", exc)

        await VivaRepository.append_response(
            viva_id,
            question_id=question_id,
            response_text=response_text,
            start_ms=start_ms,
            end_ms=end_ms,
            db=db,
        )
        await db.commit()
        return new_followup

    @staticmethod
    async def complete(
        viva_id: UUID,
        *,
        video_url: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ):
        """Mark session complete and queue ASR + evaluation."""
        viva = await VivaRepository.get_by_id(viva_id, db=db)
        if viva is None:
            raise ResearchServiceError("NOT_FOUND", "Viva session not found.", 404)
        if not viva.consent_recorded:
            raise ResearchServiceError(
                "CONSENT_REQUIRED", "Student consent must be recorded before completing session."
            )

        await VivaRepository.set_recording(viva_id, video_url=video_url, db=db)
        await db.commit()

        # Dispatch Celery processing task
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as pub_db:
            job_id = await TaskJobPublicRepository.create(
                tenant_id=tenant_id,
                task_type="process_viva_session",
                queue_name="heavy",
                payload={"viva_id": str(viva_id), "schema_name": schema_name},
                db=pub_db,
            )
            await pub_db.commit()

        await VivaRepository.set_eval_job(viva_id, job_id=job_id, db=db)
        await db.commit()

        from app.workers.heavy.process_viva_session import process_viva_session
        process_viva_session.apply_async(
            kwargs={
                "job_id":      str(job_id),
                "viva_id":     str(viva_id),
                "schema_name": schema_name,
            },
            queue="celery-heavy",
        )
        return await VivaRepository.get_by_id(viva_id, db=db), job_id

    @staticmethod
    async def ratify(
        viva_id: UUID,
        payload: VivaRatifyRequest,
        *,
        guide_user_id: UUID,
        db: AsyncSession,
    ):
        """HUMAN GATE 3: Guide ratifies or amends AI viva evaluation."""
        viva = await VivaRepository.get_by_id(viva_id, db=db)
        if viva is None:
            raise ResearchServiceError("NOT_FOUND", "Viva session not found.", 404)
        if viva.guide_user_id != guide_user_id:
            raise ResearchServiceError("FORBIDDEN", "Only the assigned guide can ratify.", 403)
        if viva.status != VivaStatus.EVALUATED.value:
            raise ResearchServiceError(
                "INVALID_STATUS",
                f"Viva must be EVALUATED before ratification (current={viva.status!r}).",
            )

        # Build guide_evaluation: start from AI evaluation, apply overrides
        ai_eval: list[dict] = list(viva.ai_evaluation or [])
        overrides = {o.question_id: o for o in payload.question_overrides}

        guide_eval: list[dict] = []
        total_score = 0.0
        count = 0
        for item in ai_eval:
            qid = item.get("question_id", "")
            override = overrides.get(qid)
            g_entry: dict = {
                "question_id":    qid,
                "score_override": None,
                "comment":        None,
            }
            if override:
                g_entry["score_override"] = override.score_override
                g_entry["comment"]        = override.comment
            guide_eval.append(g_entry)

            # Compute effective score: use override if set, else AI average
            if override and override.score_override is not None:
                effective = override.score_override
            else:
                effective = (
                    float(item.get("coherence", 0))
                    + float(item.get("accuracy", 0))
                    + float(item.get("depth", 0))
                ) / 3.0
            total_score += effective
            count += 1

        overall_guide = round(total_score / count, 2) if count else 0.0

        updated = await VivaRepository.set_guide_ratification(
            viva_id,
            guide_evaluation=guide_eval,
            overall_guide_score=overall_guide,
            db=db,
        )
        await db.commit()
        return updated

    @staticmethod
    async def list_for_guide(
        guide_user_id: UUID,
        *,
        status: str | None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ):
        return await VivaRepository.list_by_guide(
            guide_user_id, status=status, offset=offset, limit=limit, db=db
        )

    @staticmethod
    async def list_for_student(student_user_id: UUID, *, db: AsyncSession):
        return await VivaRepository.list_by_student(student_user_id, db=db)
