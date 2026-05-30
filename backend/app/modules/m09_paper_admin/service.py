"""
M09 Paper Administration & Scanning — Service layer.

Architecture contract:
  - All business logic lives here; router is pure HTTP glue.
  - ScriptServiceError carries code, message, status_code for HTTP translation.
  - Celery dispatch via TaskJobPublicRepository (public schema session).
  - Two human gates enforced here AND in the repository:
      Gate 1: submit_marks()   → only way status reaches MARKS_SUBMITTED
      Gate 2: board_finalise() → only way status reaches BOARD_FINALISED
  - exam_score_ledger is written ONLY inside board_finalise().
  - evaluator_marks are written ONLY by update_evaluator_marks() and submit_marks().
  - student_user_id / student_roll_ref are masked (set to None in-memory) on every
    return path until status == BOARD_FINALISED.  Identity is never persisted as
    None — only the service layer strips it before handing objects to the router.
"""
from __future__ import annotations

import logging
import secrets
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m09_paper_admin.models import (
    EvaluationRound,
    ExamScoreLedger,
    ScannedScript,
    ScriptEvaluation,
    ScriptStatus,
)
from app.modules.m09_paper_admin.repository import (
    ExamScoreLedgerRepository,
    ScriptEvaluationRepository,
    ScriptRepository,
    TaskJobPublicRepository,
)
from app.modules.m09_paper_admin.schemas import (
    BulkMarkUpdate,
    ScriptAssignEvaluatorRequest,
    ScriptFinaliseRequest,
    ScriptIngestRequest,
    ScriptSubmitMarksRequest,
)

logger = logging.getLogger("vidya.service.m09")


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class ScriptServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _gen_masked_id() -> str:
    """Opaque 11-char token shown to evaluators in place of student identity."""
    return "S" + secrets.token_hex(5).upper()


def _mask_identity(script: ScannedScript) -> ScannedScript:
    """
    Erase student identity fields in-memory (never persisted).
    Called on every code path that returns a script to the router,
    unless status == BOARD_FINALISED (identity intentionally revealed at Gate 2).
    """
    if script.status != ScriptStatus.BOARD_FINALISED.value:
        script.student_user_id  = None
        script.student_roll_ref = None
    return script


async def _require_script(script_id: UUID, *, db: AsyncSession) -> ScannedScript:
    script = await ScriptRepository.get_by_id(script_id, db=db)
    if script is None:
        raise ScriptServiceError("NOT_FOUND", "Scanned script not found.", 404)
    return script


async def _count_scripts(
    *,
    status: str | None,
    exam_paper_id: UUID | None,
    db: AsyncSession,
) -> int:
    q = select(func.count(ScannedScript.id))
    if status:
        q = q.where(ScannedScript.status == status)
    if exam_paper_id:
        q = q.where(ScannedScript.exam_paper_id == exam_paper_id)
    result = await db.execute(q)
    return int(result.scalar() or 0)


async def _count_scripts_for_evaluator(
    evaluator_id: UUID,
    *,
    status: str | None,
    db: AsyncSession,
) -> int:
    q = (
        select(func.count(ScannedScript.id))
        .where(ScannedScript.evaluator_id == evaluator_id)
    )
    if status:
        q = q.where(ScannedScript.status == status)
    result = await db.execute(q)
    return int(result.scalar() or 0)


# ---------------------------------------------------------------------------
# ScriptService
# ---------------------------------------------------------------------------

class ScriptService:

    # -----------------------------------------------------------------------
    # Ingest — create script + dispatch scoring task
    # -----------------------------------------------------------------------

    @staticmethod
    async def ingest_script(
        payload: ScriptIngestRequest,
        *,
        upload_url: str | None,
        page_count: int | None,
        ingested_by: UUID,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> tuple[ScannedScript, UUID]:
        """
        Register a scanned answer script and dispatch the scoring Celery task.
        Returns (script, job_id).  student_user_id is masked on the returned object.
        """
        masked_id = _gen_masked_id()

        script = await ScriptRepository.create(
            exam_paper_id=payload.exam_paper_id,
            masked_id=masked_id,
            student_user_id=payload.student_user_id,
            student_roll_ref=payload.student_roll_ref,
            upload_url=upload_url,
            page_count=page_count,
            db=db,
        )
        await db.commit()
        await db.refresh(script)

        # Create task job record in public schema then dispatch
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as pub_db:
            job = await TaskJobPublicRepository.create(
                task_name="app.workers.heavy.score_scanned_script",
                tenant_id=tenant_id,
                db=pub_db,
            )
            await pub_db.commit()

        # Set eval_job_id + status → PROCESSING on the script
        await ScriptRepository.set_eval_job(script.id, job_id=job.id, db=db)
        await db.commit()

        # Route to quality pipeline when a file was uploaded; otherwise score directly.
        if upload_url:
            from app.workers.heavy.detect_scan_quality import detect_scan_quality
            detect_scan_quality.apply_async(
                kwargs={
                    "job_id":      str(job.id),
                    "script_id":   str(script.id),
                    "schema_name": schema_name,
                }
            )
        else:
            from app.workers.heavy.score_scanned_script import score_scanned_script
            score_scanned_script.apply_async(
                kwargs={
                    "job_id":      str(job.id),
                    "script_id":   str(script.id),
                    "schema_name": schema_name,
                }
            )

        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        await AuditService.log(
            AuditEventType.SCRIPT_SCORING_QUEUED,
            actor_user_id=ingested_by,
            actor_role="ADMIN",
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="scanned_script",
            target_id=str(script.id),
            metadata={
                "masked_id":     masked_id,
                "exam_paper_id": str(payload.exam_paper_id),
                "job_id":        str(job.id),
            },
        )

        _mask_identity(script)
        return script, job.id

    # -----------------------------------------------------------------------
    # Assign evaluator
    # -----------------------------------------------------------------------

    @staticmethod
    async def assign_evaluator(
        script_id: UUID,
        payload: ScriptAssignEvaluatorRequest,
        *,
        assigned_by: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> ScannedScript:
        """Assign (or re-assign) an evaluator. Forbidden after Board finalisation."""
        script = await _require_script(script_id, db=db)

        if script.status == ScriptStatus.BOARD_FINALISED.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                "Cannot reassign evaluator for a Board-finalised script.",
            )

        await ScriptRepository.assign_evaluator(
            script_id,
            evaluator_id=payload.evaluator_id,
            second_evaluator_id=payload.second_evaluator_id,
            db=db,
        )
        await db.commit()
        await db.refresh(script)

        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        await AuditService.log(
            AuditEventType.SCRIPT_EVALUATOR_ASSIGNED,
            actor_user_id=assigned_by,
            actor_role="ADMIN",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="scanned_script",
            target_id=str(script_id),
            metadata={
                "evaluator_id":        str(payload.evaluator_id),
                "second_evaluator_id": (
                    str(payload.second_evaluator_id)
                    if payload.second_evaluator_id else None
                ),
            },
        )

        return _mask_identity(script)

    # -----------------------------------------------------------------------
    # Update evaluator marks (intermediate save — not a gate)
    # -----------------------------------------------------------------------

    @staticmethod
    async def update_evaluator_marks(
        script_id: UUID,
        payload: BulkMarkUpdate,
        *,
        evaluator_user_id: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> list[ScriptEvaluation]:
        """
        Evaluator saves marks for one or more questions without triggering Gate 1.
        Allowed only when status is SCORED or REVIEW_REQUIRED.
        evaluator_marks is the only field written here — final_marks is never touched.
        """
        script = await _require_script(script_id, db=db)

        updatable = (
            ScriptStatus.SCORED.value,
            ScriptStatus.REVIEW_REQUIRED.value,
        )
        if script.status not in updatable:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Marks can only be updated when status is SCORED or REVIEW_REQUIRED "
                f"(current: {script.status!r}).",
            )

        updates: dict[UUID, dict] = {
            UUID(qid): {
                "evaluator_marks": m.evaluator_marks,
                "evaluator_note":  m.evaluator_note,
            }
            for qid, m in payload.marks.items()
        }
        await ScriptEvaluationRepository.bulk_update_evaluator_marks(
            updates, script_id=script_id, db=db
        )
        await db.commit()

        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        await AuditService.log(
            AuditEventType.SCRIPT_MARKS_UPDATED,
            actor_user_id=evaluator_user_id,
            actor_role="EVALUATOR",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="scanned_script",
            target_id=str(script_id),
            metadata={"question_count": len(updates)},
        )

        return await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )

    # -----------------------------------------------------------------------
    # Gate 1 — Evaluator submits marks
    # -----------------------------------------------------------------------

    @staticmethod
    async def submit_marks(
        script_id: UUID,
        payload: ScriptSubmitMarksRequest,
        *,
        evaluator_user_id: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> ScannedScript:
        """
        HUMAN GATE 1: Evaluator finalises and submits all marks.
        Status transitions SCORED | REVIEW_REQUIRED → MARKS_SUBMITTED.
        Requires ALL evaluations to have evaluator_marks set (no nulls).
        Only the assigned evaluator (primary or secondary) may submit.
        """
        script = await _require_script(script_id, db=db)

        # Evaluator identity check
        allowed_evaluators = {script.evaluator_id, script.second_evaluator_id} - {None}
        if evaluator_user_id not in allowed_evaluators:
            raise ScriptServiceError(
                "FORBIDDEN",
                "Only the assigned evaluator can submit marks for this script.",
                403,
            )

        submittable = (
            ScriptStatus.SCORED.value,
            ScriptStatus.REVIEW_REQUIRED.value,
        )
        if script.status not in submittable:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Marks can only be submitted when status is SCORED or REVIEW_REQUIRED "
                f"(current: {script.status!r}).",
            )

        # Apply payload marks first
        if payload.marks:
            updates: dict[UUID, dict] = {
                UUID(qid): {
                    "evaluator_marks": m.evaluator_marks,
                    "evaluator_note":  m.evaluator_note,
                }
                for qid, m in payload.marks.items()
            }
            await ScriptEvaluationRepository.bulk_update_evaluator_marks(
                updates, script_id=script_id, db=db
            )

        # Verify all evaluations now have marks — Gate 1 completeness check
        evals = await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )
        if not evals:
            raise ScriptServiceError(
                "NO_EVALUATIONS",
                "No evaluation rows found. Run the scoring task first.",
            )
        missing = [e for e in evals if e.evaluator_marks is None]
        if missing:
            ids_preview = ", ".join(str(e.question_id) for e in missing[:5])
            raise ScriptServiceError(
                "INCOMPLETE_MARKS",
                f"Evaluator marks missing for {len(missing)} question(s): "
                + ids_preview
                + ("..." if len(missing) > 5 else "."),
            )

        await ScriptRepository.set_marks_submitted(
            script_id, submitted_by=evaluator_user_id, db=db
        )
        await db.commit()
        await db.refresh(script)

        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        await AuditService.log(
            AuditEventType.SCRIPT_MARKS_SUBMITTED,
            actor_user_id=evaluator_user_id,
            actor_role="EVALUATOR",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="scanned_script",
            target_id=str(script_id),
            metadata={"question_count": len(evals)},
        )

        return _mask_identity(script)

    # -----------------------------------------------------------------------
    # Gate 2 — Board finalises marks
    # -----------------------------------------------------------------------

    @staticmethod
    async def board_finalise(
        script_id: UUID,
        payload: ScriptFinaliseRequest,
        *,
        board_user_id: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> tuple[ScannedScript, ExamScoreLedger]:
        """
        HUMAN GATE 2: Board finalises marks and writes the score ledger.

        Sequence (all in one transaction):
          1. Copy evaluator_marks → final_marks for all PRIMARY evaluations.
          2. Sum total_marks and max_marks.
          3. Append row to exam_score_ledger (never updated or deleted).
          4. Advance script status → BOARD_FINALISED; set finalised_by / finalised_at.

        Identity is revealed after this gate: student_user_id is present on the
        returned script and in the ledger row.  Callers must be authorised BOARD members.
        """
        script = await _require_script(script_id, db=db)

        if script.status != ScriptStatus.MARKS_SUBMITTED.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Board finalisation requires status MARKS_SUBMITTED "
                f"(current: {script.status!r}).",
            )

        # Step 1: copy evaluator_marks → final_marks
        await ScriptEvaluationRepository.set_final_marks(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )

        # Step 2: compute totals
        total_marks = await ScriptEvaluationRepository.sum_evaluator_marks(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )
        max_marks = await ScriptEvaluationRepository.sum_max_marks(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )

        # Step 3: write exam_score_ledger — append-only, never updated
        ledger = await ExamScoreLedgerRepository.create(
            script_id=script_id,
            exam_paper_id=script.exam_paper_id,
            student_user_id=script.student_user_id,
            student_roll_ref=script.student_roll_ref,
            total_marks=total_marks,
            max_marks=max_marks,
            finalised_by=board_user_id,
            finalisation_note=payload.finalisation_note,
            db=db,
        )

        # Step 4: advance script status
        await ScriptRepository.set_finalised(
            script_id, finalised_by=board_user_id, db=db
        )
        await db.commit()
        await db.refresh(script)

        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        await AuditService.log(
            AuditEventType.SCRIPT_BOARD_FINALISED,
            actor_user_id=board_user_id,
            actor_role="BOARD",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="scanned_script",
            target_id=str(script_id),
            metadata={
                "total_marks": total_marks,
                "max_marks":   max_marks,
                "ledger_id":   str(ledger.id),
            },
        )
        await AuditService.log(
            AuditEventType.EXAM_SCORE_RECORDED,
            actor_user_id=board_user_id,
            actor_role="BOARD",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="exam_score_ledger",
            target_id=str(ledger.id),
            metadata={
                "script_id":   str(script_id),
                "total_marks": total_marks,
                "max_marks":   max_marks,
            },
        )

        # Identity is now revealed: status == BOARD_FINALISED so _mask_identity is a no-op
        return script, ledger

    # -----------------------------------------------------------------------
    # Read — scripts
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_script(
        script_id: UUID,
        *,
        include_identity: bool = False,
        db: AsyncSession,
    ) -> ScannedScript:
        """
        Fetch a single script.
        include_identity=True only reveals student fields when status == BOARD_FINALISED;
        identity is always masked for non-finalised scripts regardless of the flag.
        """
        script = await _require_script(script_id, db=db)
        if not include_identity or script.status != ScriptStatus.BOARD_FINALISED.value:
            _mask_identity(script)
        return script

    @staticmethod
    async def list_scripts(
        *,
        exam_paper_id: UUID | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[ScannedScript], int]:
        items = await ScriptRepository.list_all(
            status=status, exam_paper_id=exam_paper_id,
            offset=offset, limit=limit, db=db,
        )
        total = await _count_scripts(
            status=status, exam_paper_id=exam_paper_id, db=db
        )
        for s in items:
            _mask_identity(s)
        return items, total

    @staticmethod
    async def list_for_paper(
        exam_paper_id: UUID,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[ScannedScript], int]:
        items = await ScriptRepository.list_for_exam_paper(
            exam_paper_id, status=status, offset=offset, limit=limit, db=db,
        )
        total = await _count_scripts(
            status=status, exam_paper_id=exam_paper_id, db=db
        )
        for s in items:
            _mask_identity(s)
        return items, total

    @staticmethod
    async def list_for_evaluator(
        evaluator_id: UUID,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[ScannedScript], int]:
        items = await ScriptRepository.list_for_evaluator(
            evaluator_id, status=status, offset=offset, limit=limit, db=db,
        )
        total = await _count_scripts_for_evaluator(evaluator_id, status=status, db=db)
        for s in items:
            _mask_identity(s)
        return items, total

    @staticmethod
    async def list_board_pending(
        *,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[ScannedScript], int]:
        """Scripts awaiting Board finalisation (status = MARKS_SUBMITTED)."""
        items = await ScriptRepository.list_board_pending(offset=offset, limit=limit, db=db)
        count_result = await db.execute(
            select(func.count(ScannedScript.id))
            .where(ScannedScript.status == ScriptStatus.MARKS_SUBMITTED.value)
        )
        total = int(count_result.scalar() or 0)
        for s in items:
            _mask_identity(s)
        return items, total

    # -----------------------------------------------------------------------
    # Read — evaluations
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_evaluations(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[ScriptEvaluation]:
        """Return AI suggestions + evaluator marks for a script (PRIMARY round)."""
        await _require_script(script_id, db=db)
        return await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )

    # -----------------------------------------------------------------------
    # Evaluator review panel (STEP-05)
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_evaluator_review(
        script_id: UUID,
        *,
        requesting_user_id: UUID,
        user_role: str,
        db: AsyncSession,
    ) -> tuple[ScannedScript, list[ScriptEvaluation]]:
        """
        Return script (with OCR text preserved) + enriched evaluations for the
        evaluator review panel.  Identity is masked; OCR text is included.

        FACULTY callers are restricted to scripts they are assigned to.
        ADMIN / BOARD / DEAN bypass this check (oversight role).
        """
        script = await _require_script(script_id, db=db)

        if user_role not in ("ADMIN", "BOARD", "DEAN"):
            allowed = {script.evaluator_id, script.second_evaluator_id} - {None}
            if requesting_user_id not in allowed:
                raise ScriptServiceError(
                    "FORBIDDEN",
                    "Only the assigned evaluator may access the review panel.",
                    403,
                )

        evals = await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )
        _mask_identity(script)
        return script, evals

    # -----------------------------------------------------------------------
    # Accept AI suggestions (STEP-05)
    # -----------------------------------------------------------------------

    @staticmethod
    async def accept_suggestions(
        script_id: UUID,
        question_ids: list[UUID] | None,
        *,
        evaluator_note: str | None,
        evaluator_user_id: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> list[ScriptEvaluation]:
        """
        Evaluator accepts AI-suggested marks — copies ai_suggested_marks →
        evaluator_marks.  Allowed only when status is SCORED or REVIEW_REQUIRED.

        Human-gate invariant: final_marks is NEVER written here.
        question_ids=None  → accept all questions.
        question_ids=[...] → accept only those specific questions.
        Questions where ai_suggested_marks is None are silently skipped
        (evaluator must enter those manually).
        """
        script = await _require_script(script_id, db=db)

        updatable = (ScriptStatus.SCORED.value, ScriptStatus.REVIEW_REQUIRED.value)
        if script.status not in updatable:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Suggestions can only be accepted when status is SCORED or "
                f"REVIEW_REQUIRED (current: {script.status!r}).",
            )

        evals = await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )

        if question_ids is not None:
            qid_set = set(question_ids)
            target_evals = [e for e in evals if e.question_id in qid_set]
        else:
            target_evals = evals

        updates: dict[UUID, dict] = {
            e.question_id: {
                "evaluator_marks": float(e.ai_suggested_marks),
                "evaluator_note":  evaluator_note,
            }
            for e in target_evals
            if e.ai_suggested_marks is not None
        }

        if updates:
            await ScriptEvaluationRepository.bulk_update_evaluator_marks(
                updates, script_id=script_id, db=db
            )
            await db.commit()

        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        await AuditService.log(
            AuditEventType.SCRIPT_MARKS_UPDATED,
            actor_user_id=evaluator_user_id,
            actor_role="EVALUATOR",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="scanned_script",
            target_id=str(script_id),
            metadata={
                "accepted_count": len(updates),
                "accept_all": question_ids is None,
            },
        )

        return await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )

    # -----------------------------------------------------------------------
    # Read — score ledger
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_ledger_entry(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> ExamScoreLedger:
        """Fetch the Board-finalised score record. Blocked until BOARD_FINALISED."""
        script = await _require_script(script_id, db=db)
        if script.status != ScriptStatus.BOARD_FINALISED.value:
            raise ScriptServiceError(
                "NOT_FINALISED",
                "Score ledger entry is only accessible after Board finalisation.",
                403,
            )
        entry = await ExamScoreLedgerRepository.get_by_script(script_id, db=db)
        if entry is None:
            raise ScriptServiceError("NOT_FOUND", "Score ledger entry not found.", 404)
        return entry

    @staticmethod
    async def list_ledger_for_paper(
        exam_paper_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[ExamScoreLedger], int]:
        items = await ExamScoreLedgerRepository.list_for_exam_paper(
            exam_paper_id, offset=offset, limit=limit, db=db
        )
        count_result = await db.execute(
            select(func.count(ExamScoreLedger.id))
            .where(ExamScoreLedger.exam_paper_id == exam_paper_id)
        )
        total = int(count_result.scalar() or 0)
        return items, total
