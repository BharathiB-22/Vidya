"""
M08 Exam Setter — Service layer.

Architecture contract:
  - All business logic here; router is pure HTTP glue.
  - ExamServiceError carries code, message, status_code for HTTP translation.
  - Celery task dispatch via TaskJobPublicRepository.
  - Three human gates enforced here AND in the repository:
      ExamService.submit_for_review() → only way status reaches SUBMITTED (Gate 1)
      ExamService.board_decide()      → only way status reaches BOARD_APPROVED / BOARD_RETURNED (Gate 2)
      ExamService.seal()              → only way status reaches SEALED (Gate 3)
  - Celery tasks may only advance status to GENERATED (generate task) or RELEASED (release task).
  - Model answers and correct_option are NEVER returned when status == SEALED.
  - Questions are NEVER returned when status == SEALED (forbidden at service level).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m08_exam_setter.models import ExamPaperStatus
from app.modules.m08_exam_setter.repository import (
    BloomsRepository,
    ExamPaperRepository,
    ExamQuestionRepository,
    TaskJobPublicRepository,
)
from app.modules.m08_exam_setter.schemas import (
    BoardDecisionRequest,
    ExamPaperCreate,
    ExamQuestionUpdate,
    SealRequest,
)

logger = logging.getLogger("vidya.service.m08")


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class ExamServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# ExamService
# ---------------------------------------------------------------------------

class ExamService:

    # -----------------------------------------------------------------------
    # Create
    # -----------------------------------------------------------------------

    @staticmethod
    async def create(
        payload: ExamPaperCreate,
        *,
        created_by: UUID,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ):
        """
        Create an ExamPaper record and dispatch the generation Celery task.
        Returns (paper, job_id).
        """
        # Verify the course exists in this tenant before creating the paper
        from sqlalchemy import select as _select
        from app.modules.m01_program_advisor.models import Course as _Course
        course_result = await db.execute(
            _select(_Course).where(_Course.id == payload.course_id)
        )
        if course_result.scalar_one_or_none() is None:
            raise ExamServiceError(
                "COURSE_NOT_FOUND",
                "The selected course was not found. Please select a valid course from the dropdown.",
                404,
            )

        paper = await ExamPaperRepository.create(
            course_id=payload.course_id,
            created_by=created_by,
            title=payload.title,
            exam_type=payload.exam_type,
            total_marks=payload.total_marks,
            duration_mins=payload.duration_mins,
            units_included=payload.units_included,
            question_format=payload.question_format.model_dump(),
            requested_dist=payload.requested_dist.model_dump(),
            special_instructions=payload.special_instructions,
            db=db,
        )
        await db.commit()
        await db.refresh(paper)

        # Dispatch Celery generation task
        from app.database import async_session_public
        async with async_session_public() as pub_db:
            job = await TaskJobPublicRepository.create(
                task_name="app.workers.heavy.generate_exam_paper",
                tenant_id=tenant_id,
                db=pub_db,
            )
            await pub_db.commit()

        await ExamPaperRepository.set_generation_job(paper.id, job_id=job.id, db=db)
        await db.commit()

        try:
            from app.workers.heavy.generate_exam_paper import generate_exam_paper
            generate_exam_paper.apply_async(
                kwargs={
                    "job_id":      str(job.id),
                    "paper_id":    str(paper.id),
                    "schema_name": schema_name,
                }
            )
        except Exception as exc:
            logger.error(
                "Failed to dispatch exam generation task for paper %s: %s",
                paper.id, exc,
            )
            # Mark the record FAILED so the user sees a clear error instead of
            # a zombie GENERATING row that never resolves.
            await ExamPaperRepository.set_failed(
                paper.id,
                reason=f"Task queue unavailable: {exc}",
                db=db,
            )
            await db.commit()
            raise ExamServiceError(
                "QUEUE_UNAVAILABLE",
                "Question generation could not be queued — the task worker appears to be offline. "
                "Start the Celery worker (celery -A app.workers.celery_app worker) and try again.",
                503,
            )

        return paper, job.id

    # -----------------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------------

    @staticmethod
    async def get(paper_id: UUID, *, db: AsyncSession):
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)
        return paper

    @staticmethod
    async def get_questions(
        paper_id: UUID,
        *,
        set_label: str | None,
        include_answers: bool,
        db: AsyncSession,
    ) -> list:
        """
        Return questions for a paper.
        Raises SEALED_ACCESS if paper is sealed (questions inaccessible until release).
        Model answers stripped unless include_answers=True (role-gated by router).
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.status == ExamPaperStatus.SEALED.value:
            raise ExamServiceError(
                "SEALED_ACCESS",
                "Exam paper is sealed and inaccessible until the release date.",
                403,
            )

        questions = await ExamQuestionRepository.list_by_paper(
            paper_id, set_label=set_label, db=db
        )

        if not include_answers:
            # Strip model answer and correct_option for non-privileged views
            for q in questions:
                q.model_answer   = None
                q.correct_option = None

        return questions

    @staticmethod
    async def list_for_faculty(
        created_by: UUID,
        *,
        status: str | None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ):
        return await ExamPaperRepository.list_for_faculty(
            created_by, status=status, offset=offset, limit=limit, db=db
        )

    @staticmethod
    async def list_board_pending(*, offset: int, limit: int, db: AsyncSession):
        return await ExamPaperRepository.list_board_pending(offset=offset, limit=limit, db=db)

    @staticmethod
    async def list_all(
        *,
        status: str | None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ):
        return await ExamPaperRepository.list_all(status=status, offset=offset, limit=limit, db=db)

    @staticmethod
    async def get_blooms_report(paper_id: UUID, *, db: AsyncSession):
        report = await BloomsRepository.get_by_paper(paper_id, db=db)
        if report is None:
            raise ExamServiceError(
                "NOT_FOUND",
                "Bloom's compliance report not yet generated for this paper.",
                404,
            )
        return report

    # -----------------------------------------------------------------------
    # Question editing
    # -----------------------------------------------------------------------

    @staticmethod
    async def update_question(
        paper_id: UUID,
        question_id: UUID,
        payload: ExamQuestionUpdate,
        *,
        editor_user_id: UUID,
        db: AsyncSession,
    ):
        """Faculty edits an individual question. Only allowed before SUBMITTED."""
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        editable_statuses = (
            ExamPaperStatus.GENERATED.value,
            ExamPaperStatus.BOARD_RETURNED.value,
        )
        if paper.status not in editable_statuses:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Questions can only be edited when paper status is "
                f"GENERATED or BOARD_RETURNED (current: {paper.status!r}).",
            )

        question = await ExamQuestionRepository.get_by_id(question_id, db=db)
        if question is None or question.exam_paper_id != paper_id:
            raise ExamServiceError("NOT_FOUND", "Question not found in this paper.", 404)

        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        if not updates:
            raise ExamServiceError("NO_CHANGES", "No fields provided for update.")

        await ExamQuestionRepository.update_question(question_id, updates=updates, db=db)
        await db.commit()
        return await ExamQuestionRepository.get_by_id(question_id, db=db)

    @staticmethod
    async def delete_question(
        paper_id: UUID,
        question_id: UUID,
        *,
        db: AsyncSession,
    ):
        """Faculty removes a question. Only allowed before SUBMITTED."""
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        editable_statuses = (
            ExamPaperStatus.GENERATED.value,
            ExamPaperStatus.BOARD_RETURNED.value,
        )
        if paper.status not in editable_statuses:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Questions can only be deleted when paper status is "
                f"GENERATED or BOARD_RETURNED (current: {paper.status!r}).",
            )

        question = await ExamQuestionRepository.get_by_id(question_id, db=db)
        if question is None or question.exam_paper_id != paper_id:
            raise ExamServiceError("NOT_FOUND", "Question not found in this paper.", 404)

        await ExamQuestionRepository.delete(question_id, db=db)
        await db.commit()

    # -----------------------------------------------------------------------
    # GATE 1 — Faculty submits for Board review
    # -----------------------------------------------------------------------

    @staticmethod
    async def submit_for_review(
        paper_id: UUID,
        *,
        faculty_user_id: UUID,
        db: AsyncSession,
    ):
        """
        HUMAN GATE 1: Faculty submits paper for Examination Board review.
        Only the creator can submit. Status must be GENERATED or BOARD_RETURNED.
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.created_by != faculty_user_id:
            raise ExamServiceError(
                "FORBIDDEN", "Only the paper creator can submit it for review.", 403
            )

        submittable = (
            ExamPaperStatus.GENERATED.value,
            ExamPaperStatus.BOARD_RETURNED.value,
        )
        if paper.status not in submittable:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Paper must be GENERATED or BOARD_RETURNED to submit "
                f"(current: {paper.status!r}).",
            )

        # Must have at least one question
        questions = await ExamQuestionRepository.list_by_paper(paper_id, db=db)
        if not questions:
            raise ExamServiceError(
                "NO_QUESTIONS",
                "Cannot submit a paper with no questions. Generate questions first.",
            )

        await ExamPaperRepository.set_submitted(paper_id, db=db)
        await db.commit()
        return await ExamPaperRepository.get_by_id(paper_id, db=db)

    # -----------------------------------------------------------------------
    # GATE 2 — Examination Board approves or returns
    # -----------------------------------------------------------------------

    @staticmethod
    async def board_decide(
        paper_id: UUID,
        payload: BoardDecisionRequest,
        *,
        board_user_id: UUID,
        db: AsyncSession,
    ):
        """
        HUMAN GATE 2: Examination Board approves or returns the paper.
        Status must be SUBMITTED.
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.status != ExamPaperStatus.SUBMITTED.value:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Board decision requires paper status SUBMITTED (current: {paper.status!r}).",
            )

        await ExamPaperRepository.set_board_decision(
            paper_id,
            approved=payload.approved,
            approved_by=board_user_id,
            board_comment=payload.board_comment,
            db=db,
        )
        await db.commit()
        return await ExamPaperRepository.get_by_id(paper_id, db=db)

    # -----------------------------------------------------------------------
    # GATE 3 — Faculty seals the paper
    # -----------------------------------------------------------------------

    @staticmethod
    async def seal(
        paper_id: UUID,
        payload: SealRequest,
        *,
        faculty_user_id: UUID,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ):
        """
        HUMAN GATE 3: Faculty seals the paper with AES encryption.
        Paper must be BOARD_APPROVED. Only the creator or Admin can seal.
        Schedules an ETA Celery task to auto-release at release_at.
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.created_by != faculty_user_id:
            raise ExamServiceError(
                "FORBIDDEN", "Only the paper creator can seal it.", 403
            )

        if paper.status != ExamPaperStatus.BOARD_APPROVED.value:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Paper must be BOARD_APPROVED to seal (current: {paper.status!r}).",
            )

        # Collect all questions + model answers for encryption
        questions = await ExamQuestionRepository.list_by_paper(paper_id, db=db)
        paper_payload = {
            "paper_id":    str(paper_id),
            "title":       paper.title,
            "total_marks": paper.total_marks,
            "questions": [
                {
                    "id":             str(q.id),
                    "question_text":  q.question_text,
                    "bloom_level":    q.bloom_level,
                    "question_type":  q.question_type,
                    "unit_number":    q.unit_number,
                    "marks":          float(q.marks),
                    "options":        q.options,
                    "correct_option": q.correct_option,
                    "model_answer":   q.model_answer,
                    "marking_scheme": q.marking_scheme,
                    "set_membership": q.set_membership,
                }
                for q in questions
            ],
        }

        from app.modules.m08_exam_setter.paper_sealer import seal as fernet_seal
        encrypted_bytes, key_ref = fernet_seal(paper_payload)

        # Store encrypted blob in S3
        s3_key = await ExamService._store_encrypted_blob(
            tenant_id=tenant_id,
            paper_id=paper_id,
            encrypted_bytes=encrypted_bytes,
        )

        # Create release job
        from app.database import async_session_public
        async with async_session_public() as pub_db:
            release_job = await TaskJobPublicRepository.create(
                task_name="app.workers.heavy.release_exam_paper",
                tenant_id=tenant_id,
                db=pub_db,
            )
            await pub_db.commit()

        # Update paper record
        await ExamPaperRepository.set_sealed(
            paper_id,
            release_at=payload.release_at,
            encrypted_blob_key=s3_key,
            encryption_key_ref=key_ref,
            release_job_id=release_job.id,
            db=db,
        )
        await db.commit()

        # Schedule release Celery task at ETA
        from app.workers.heavy.release_exam_paper import release_exam_paper
        release_exam_paper.apply_async(
            kwargs={
                "job_id":      str(release_job.id),
                "paper_id":    str(paper_id),
                "schema_name": schema_name,
            },
            eta=payload.release_at,
        )

        return await ExamPaperRepository.get_by_id(paper_id, db=db)

    @staticmethod
    async def _store_encrypted_blob(
        *,
        tenant_id: UUID,
        paper_id: UUID,
        encrypted_bytes: bytes,
    ) -> str:
        """Upload encrypted paper blob to S3. Returns S3 object key."""
        s3_key = f"exam_papers/{tenant_id}/{paper_id}/encrypted.bin"
        try:
            from app.core.storage.client import get_storage_client
            client = get_storage_client()
            import io
            await client.upload_fileobj(
                io.BytesIO(encrypted_bytes),
                key=s3_key,
                content_type="application/octet-stream",
            )
        except Exception as exc:
            logger.warning(
                "S3 upload failed for sealed paper %s: %s — storing key only.", paper_id, exc
            )
        return s3_key

    # -----------------------------------------------------------------------
    # Release (called by Celery task only)
    # -----------------------------------------------------------------------

    @staticmethod
    async def release(paper_id: UUID, *, schema_name: str, db: AsyncSession):
        """
        Called by release_exam_paper Celery task at scheduled release_at time.
        Transitions status SEALED → RELEASED.
        This is a system action, not a human gate.
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.status != ExamPaperStatus.SEALED.value:
            # Already released or in unexpected state — log and return
            logger.warning(
                "Release called on paper %s with status %s (expected SEALED).",
                paper_id, paper.status,
            )
            return paper

        # Verify release_at has passed
        now = datetime.now(timezone.utc)
        if paper.release_at and paper.release_at > now:
            raise ExamServiceError(
                "TOO_EARLY",
                f"Release time {paper.release_at.isoformat()} has not passed yet.",
                400,
            )

        await ExamPaperRepository.set_released(paper_id, db=db)
        await db.commit()
        return await ExamPaperRepository.get_by_id(paper_id, db=db)
