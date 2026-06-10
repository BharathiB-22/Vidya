"""
M09 Paper Administration & Scanning — Service layer.

Architecture contract:
  - All business logic lives here; router is pure HTTP glue.
  - ScriptServiceError carries code, message, status_code for HTTP translation.
  - Celery dispatch via TaskJobPublicRepository (public schema session).
  - Human gates enforced here AND in the repository:
      Gate 1a: submit_marks() for primary on double-eval → WAITING_SECOND_EVALUATOR
      Gate 1b: submit_marks() for secondary on double-eval → SECONDARY_EVALUATED → MARKS_SUBMITTED
      Gate 1:  submit_marks() on single-eval → MARKS_SUBMITTED
      Gate 2:  board_finalise() → only way status reaches BOARD_FINALISED
  - exam_score_ledger is written ONLY inside board_finalise().
  - evaluator_marks are written ONLY by update_evaluator_marks() and submit_marks().
  - board_adjusted_marks written ONLY by set_board_adjusted_marks().
  - student_user_id / student_roll_ref are masked (set to None in-memory) on every
    return path until status == BOARD_FINALISED.  Identity is never persisted as
    None — only the service layer strips it before handing objects to the router.
  - double_evaluation_enabled is denormalized from exam_papers at ingest time;
    never changed after that point.
"""
from __future__ import annotations

import logging
import secrets
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m09_paper_admin.models import (
    BoardApprovalStatus,
    BoardSessionStatus,
    EvaluationRound,
    ExamBoardCourseApproval,
    ExamBoardSession,
    ExamScoreLedger,
    ModerationStatus,
    RevaluationRequest,
    RevaluationStatus,
    ScannedScript,
    ScriptEvaluation,
    ScriptModerationReview,
    ScriptStatus,
)
from app.modules.m09_paper_admin.repository import (
    BoardCourseApprovalRepository,
    BoardSessionRepository,
    ExamScoreLedgerRepository,
    ModerationRepository,
    RevaluationEvaluationRepository,
    RevaluationRepository,
    ScriptEvaluationRepository,
    ScriptRepository,
    TaskJobPublicRepository,
)
from app.modules.m09_paper_admin.schemas import (
    BoardAdjustRequest,
    BoardComparisonResponse,
    BulkMarkUpdate,
    PaperPipelineStats,
    QualityOverrideRequest,
    ScriptAssignEvaluatorRequest,
    ScriptEvaluationResponse,
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


def _get_evaluation_round(script: ScannedScript, evaluator_user_id: UUID) -> str:
    """
    Determine which evaluation round an evaluator is working on.
    Returns SECONDARY when:
      - double_evaluation_enabled is True
      - script status is WAITING_SECOND_EVALUATOR
      - the caller is the assigned second evaluator
    Returns PRIMARY in all other cases.
    """
    if (
        script.double_evaluation_enabled
        and script.status == ScriptStatus.WAITING_SECOND_EVALUATOR.value
        and evaluator_user_id == script.second_evaluator_id
    ):
        return EvaluationRound.SECONDARY.value
    return EvaluationRound.PRIMARY.value


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

        # Denormalize double_evaluation_enabled from exam_papers at ingest time.
        # Raw SQL avoids an ORM dependency on M08 models.
        from sqlalchemy import text as sa_text
        paper_row = await db.execute(
            sa_text(
                "SELECT double_evaluation_enabled FROM exam_papers WHERE id = CAST(:pid AS uuid)"
            ),
            {"pid": str(payload.exam_paper_id)},
        )
        paper_rec = paper_row.fetchone()
        double_eval = bool(paper_rec[0]) if paper_rec else False

        script = await ScriptRepository.create(
            exam_paper_id=payload.exam_paper_id,
            masked_id=masked_id,
            student_user_id=payload.student_user_id,
            student_roll_ref=payload.student_roll_ref,
            upload_url=upload_url,
            page_count=page_count,
            double_evaluation_enabled=double_eval,
            db=db,
        )
        await db.commit()
        await db.refresh(script)

        # Create task job record in public schema then dispatch
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as pub_db:
            job_id = await TaskJobPublicRepository.create(
                tenant_id=tenant_id,
                task_type="score_scanned_script",
                queue_name="heavy",
                payload={
                    "script_id":   str(script.id),
                    "schema_name": schema_name,
                },
                db=pub_db,
            )
            await pub_db.commit()

        # Set eval_job_id + status → PROCESSING on the script
        await ScriptRepository.set_eval_job(script.id, job_id=job_id, db=db)
        await db.commit()

        # Route to quality pipeline when a file was uploaded; otherwise score directly.
        if upload_url:
            from app.workers.heavy.detect_scan_quality import detect_scan_quality
            detect_scan_quality.apply_async(
                kwargs={
                    "job_id":      str(job_id),
                    "script_id":   str(script.id),
                    "schema_name": schema_name,
                }
            )
        else:
            from app.workers.heavy.score_scanned_script import score_scanned_script
            score_scanned_script.apply_async(
                kwargs={
                    "job_id":      str(job_id),
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
                "job_id":        str(job_id),
            },
        )

        _mask_identity(script)
        return script, job_id

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
            ScriptStatus.WAITING_SECOND_EVALUATOR.value,
        )
        if script.status not in updatable:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Marks can only be updated when status is SCORED, REVIEW_REQUIRED, "
                f"or WAITING_SECOND_EVALUATOR (current: {script.status!r}).",
            )

        evaluation_round = _get_evaluation_round(script, evaluator_user_id)

        updates: dict[UUID, dict] = {
            UUID(qid): {
                "evaluator_marks": m.evaluator_marks,
                "evaluator_note":  m.evaluator_note,
            }
            for qid, m in payload.marks.items()
        }
        await ScriptEvaluationRepository.bulk_update_evaluator_marks(
            updates, script_id=script_id, evaluation_round=evaluation_round, db=db
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
            script_id, evaluation_round=evaluation_round, db=db
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

        Single-evaluation papers:
          SCORED | REVIEW_REQUIRED → MARKS_SUBMITTED

        Double-evaluation papers (double_evaluation_enabled=True):
          Primary evaluator: SCORED | REVIEW_REQUIRED → WAITING_SECOND_EVALUATOR
            Also initialises SECONDARY evaluation rows (AI suggestions copied from PRIMARY).
            Primary evaluator_marks are NOT visible to the secondary evaluator.
          Secondary evaluator: WAITING_SECOND_EVALUATOR → SECONDARY_EVALUATED → MARKS_SUBMITTED
            M09.2 will insert moderation routing between SECONDARY_EVALUATED and MARKS_SUBMITTED.

        Only the assigned evaluator (primary or secondary) may submit.
        All evaluations for the relevant round must have evaluator_marks set.
        """
        script = await _require_script(script_id, db=db)

        # --- evaluator identity check ---
        allowed_evaluators = {script.evaluator_id, script.second_evaluator_id} - {None}
        if evaluator_user_id not in allowed_evaluators:
            raise ScriptServiceError(
                "FORBIDDEN",
                "Only the assigned evaluator can submit marks for this script.",
                403,
            )

        # --- determine which round this caller belongs to ---
        is_primary   = (evaluator_user_id == script.evaluator_id)
        is_secondary = (evaluator_user_id == script.second_evaluator_id)

        if script.double_evaluation_enabled:
            # --- DOUBLE-EVALUATION BRANCH ---
            if is_primary and not is_secondary:
                # Primary evaluator submitting on a double-eval paper
                submittable = (ScriptStatus.SCORED.value, ScriptStatus.REVIEW_REQUIRED.value)
                if script.status not in submittable:
                    raise ScriptServiceError(
                        "INVALID_STATUS",
                        f"Primary evaluation requires status SCORED or REVIEW_REQUIRED "
                        f"(current: {script.status!r}).",
                    )
                eval_round = EvaluationRound.PRIMARY.value
            elif is_secondary:
                # Secondary evaluator submitting on a double-eval paper
                if script.status != ScriptStatus.WAITING_SECOND_EVALUATOR.value:
                    raise ScriptServiceError(
                        "INVALID_STATUS",
                        f"Secondary evaluation requires status WAITING_SECOND_EVALUATOR "
                        f"(current: {script.status!r}).",
                    )
                eval_round = EvaluationRound.SECONDARY.value
            else:
                raise ScriptServiceError("FORBIDDEN", "Evaluator assignment mismatch.", 403)
        else:
            # --- SINGLE-EVALUATION BRANCH ---
            submittable = (ScriptStatus.SCORED.value, ScriptStatus.REVIEW_REQUIRED.value)
            if script.status not in submittable:
                raise ScriptServiceError(
                    "INVALID_STATUS",
                    f"Marks can only be submitted when status is SCORED or REVIEW_REQUIRED "
                    f"(current: {script.status!r}).",
                )
            eval_round = EvaluationRound.PRIMARY.value

        # --- apply payload marks to the correct round ---
        if payload.marks:
            updates: dict[UUID, dict] = {
                UUID(qid): {
                    "evaluator_marks": m.evaluator_marks,
                    "evaluator_note":  m.evaluator_note,
                }
                for qid, m in payload.marks.items()
            }
            await ScriptEvaluationRepository.bulk_update_evaluator_marks(
                updates, script_id=script_id, evaluation_round=eval_round, db=db
            )

        # --- completeness check for the relevant round ---
        evals = await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=eval_round, db=db
        )
        if not evals:
            raise ScriptServiceError(
                "NO_EVALUATIONS",
                "No evaluation rows found for this round. "
                + ("Run the scoring task first." if eval_round == EvaluationRound.PRIMARY.value
                   else "Secondary evaluation rows were not initialised — contact Admin."),
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

        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService

        # --- advance status based on eval path ---
        if script.double_evaluation_enabled and is_primary and not is_secondary:
            # Primary submits on double-eval: → WAITING_SECOND_EVALUATOR
            # Also create SECONDARY rows so secondary evaluator has questions to work with
            await ScriptRepository.set_waiting_second_evaluator(
                script_id, submitted_by=evaluator_user_id, db=db
            )
            primary_evals = evals
            await ScriptEvaluationRepository.bulk_create_secondary_evaluations(
                primary_evals, script_id=script_id, db=db
            )
            await db.commit()
            await db.refresh(script)

            await AuditService.log(
                AuditEventType.SCRIPT_MARKS_SUBMITTED,
                actor_user_id=evaluator_user_id,
                actor_role="EVALUATOR",
                tenant_id=tenant_id,
                schema_name=None,
                target_entity="scanned_script",
                target_id=str(script_id),
                metadata={
                    "question_count": len(evals),
                    "evaluation_round": "PRIMARY",
                    "new_status": ScriptStatus.WAITING_SECOND_EVALUATOR.value,
                },
            )

        elif script.double_evaluation_enabled and is_secondary:
            # Secondary submits: → SECONDARY_EVALUATED → MARKS_SUBMITTED
            await ScriptRepository.set_secondary_evaluated(
                script_id, submitted_by=evaluator_user_id, db=db
            )
            await db.commit()

            await AuditService.log(
                AuditEventType.SCRIPT_MARKS_SUBMITTED,
                actor_user_id=evaluator_user_id,
                actor_role="EVALUATOR",
                tenant_id=tenant_id,
                schema_name=None,
                target_entity="scanned_script",
                target_id=str(script_id),
                metadata={
                    "question_count": len(evals),
                    "evaluation_round": "SECONDARY",
                    "new_status": ScriptStatus.SECONDARY_EVALUATED.value,
                },
            )

            # M09.2: variance check — auto-flag for moderation if threshold exceeded
            primary_total = await ScriptEvaluationRepository.sum_evaluator_marks(
                script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
            )
            secondary_total = await ScriptEvaluationRepository.sum_evaluator_marks(
                script_id, evaluation_round=EvaluationRound.SECONDARY.value, db=db
            )
            max_marks_total = await ScriptEvaluationRepository.sum_max_marks(
                script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
            )
            threshold_pct = await ModerationRepository.get_threshold(
                script.exam_paper_id, db=db
            )
            variance_pct = (
                abs(primary_total - secondary_total) / max_marks_total * 100
                if max_marks_total > 0 else 0.0
            )

            if variance_pct > threshold_pct:
                # High variance → MODERATION_PENDING
                await ModerationRepository.create(
                    script_id=script_id,
                    exam_paper_id=script.exam_paper_id,
                    primary_total=primary_total,
                    secondary_total=secondary_total,
                    variance_pct=round(variance_pct, 2),
                    variance_threshold=threshold_pct,
                    flag_reason="AUTO_VARIANCE",
                    flagged_by=None,
                    db=db,
                )
                await ScriptRepository.set_moderation_pending(script_id, db=db)
                await db.commit()
                await db.refresh(script)

                await AuditService.log(
                    AuditEventType.SCRIPT_MODERATION_FLAGGED,
                    actor_user_id=evaluator_user_id,
                    actor_role="EVALUATOR",
                    tenant_id=tenant_id,
                    schema_name=None,
                    target_entity="scanned_script",
                    target_id=str(script_id),
                    metadata={
                        "flag_reason":    "AUTO_VARIANCE",
                        "variance_pct":   round(variance_pct, 2),
                        "threshold_pct":  threshold_pct,
                        "primary_total":  primary_total,
                        "secondary_total": secondary_total,
                    },
                )
            else:
                # Low variance → MARKS_SUBMITTED (existing path)
                await ScriptRepository.set_marks_submitted(
                    script_id, submitted_by=evaluator_user_id, db=db
                )
                await db.commit()
                await db.refresh(script)

                await AuditService.log(
                    AuditEventType.SCRIPT_MARKS_SUBMITTED,
                    actor_user_id=evaluator_user_id,
                    actor_role="EVALUATOR",
                    tenant_id=tenant_id,
                    schema_name=None,
                    target_entity="scanned_script",
                    target_id=str(script_id),
                    metadata={
                        "question_count":  len(evals),
                        "evaluation_round": "SECONDARY",
                        "new_status":       ScriptStatus.MARKS_SUBMITTED.value,
                        "variance_pct":     round(variance_pct, 2),
                    },
                )

        else:
            # Single-eval path — existing behaviour
            await ScriptRepository.set_marks_submitted(
                script_id, submitted_by=evaluator_user_id, db=db
            )
            await db.commit()
            await db.refresh(script)

            await AuditService.log(
                AuditEventType.SCRIPT_MARKS_SUBMITTED,
                actor_user_id=evaluator_user_id,
                actor_role="EVALUATOR",
                tenant_id=tenant_id,
                schema_name=None,
                target_entity="scanned_script",
                target_id=str(script_id),
                metadata={
                    "question_count": len(evals),
                    "evaluation_round": "PRIMARY",
                },
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

        acceptable = (
            ScriptStatus.MARKS_SUBMITTED.value,
            ScriptStatus.MODERATION_COMPLETE.value,
        )
        if script.status not in acceptable:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Board finalisation requires status MARKS_SUBMITTED or MODERATION_COMPLETE "
                f"(current: {script.status!r}).",
            )

        # M09.2: use MODERATION round when moderator marks exist; else PRIMARY
        moderation_evals = await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.MODERATION.value, db=db
        )
        authoritative_round = (
            EvaluationRound.MODERATION.value
            if moderation_evals
            else EvaluationRound.PRIMARY.value
        )

        # Step 1: copy COALESCE(board_adjusted_marks, evaluator_marks) → final_marks
        await ScriptEvaluationRepository.set_final_marks(
            script_id, evaluation_round=authoritative_round, db=db
        )

        # Step 2: compute official total using final_marks (respects board adjustments)
        total_marks = await ScriptEvaluationRepository.sum_final_marks(
            script_id, evaluation_round=authoritative_round, db=db
        )
        max_marks = await ScriptEvaluationRepository.sum_max_marks(
            script_id, evaluation_round=authoritative_round, db=db
        )

        # For double-evaluation papers: snapshot pre-adjustment totals per evaluator
        primary_total:   float | None = None
        secondary_total: float | None = None
        if script.double_evaluation_enabled:
            primary_total = await ScriptEvaluationRepository.sum_evaluator_marks(
                script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
            )
            secondary_total = await ScriptEvaluationRepository.sum_evaluator_marks(
                script_id, evaluation_round=EvaluationRound.SECONDARY.value, db=db
            )

        # Step 3: write exam_score_ledger — append-only, never updated
        ledger = await ExamScoreLedgerRepository.create(
            script_id=script_id,
            exam_paper_id=script.exam_paper_id,
            student_user_id=script.student_user_id,
            student_roll_ref=script.student_roll_ref,
            total_marks=total_marks,
            max_marks=max_marks,
            primary_total=primary_total,
            secondary_total=secondary_total,
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

        Secondary evaluator independence: when the caller is the second_evaluator
        and status is WAITING_SECOND_EVALUATOR, SECONDARY round rows are returned
        (ai_suggested_marks visible; primary evaluator_marks are NOT included).
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

        eval_round = _get_evaluation_round(script, requesting_user_id)
        evals = await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=eval_round, db=db
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
        evaluator_marks.  Allowed when status is SCORED, REVIEW_REQUIRED, or
        WAITING_SECOND_EVALUATOR (secondary evaluator accepting on their round).

        Human-gate invariant: final_marks is NEVER written here.
        question_ids=None  → accept all questions.
        question_ids=[...] → accept only those specific questions.
        Questions where ai_suggested_marks is None are silently skipped.
        """
        script = await _require_script(script_id, db=db)

        updatable = (
            ScriptStatus.SCORED.value,
            ScriptStatus.REVIEW_REQUIRED.value,
            ScriptStatus.WAITING_SECOND_EVALUATOR.value,
        )
        if script.status not in updatable:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Suggestions can only be accepted when status is SCORED, "
                f"REVIEW_REQUIRED, or WAITING_SECOND_EVALUATOR (current: {script.status!r}).",
            )

        eval_round = _get_evaluation_round(script, evaluator_user_id)
        evals = await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=eval_round, db=db
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
                updates, script_id=script_id, evaluation_round=eval_round, db=db
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
                "accept_all":     question_ids is None,
                "evaluation_round": eval_round,
            },
        )

        return await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=eval_round, db=db
        )

    # -----------------------------------------------------------------------
    # Board adjusted marks — per-question Board correction (M09.1)
    # -----------------------------------------------------------------------

    @staticmethod
    async def set_board_adjusted_marks(
        script_id: UUID,
        payload: BoardAdjustRequest,
        *,
        board_user_id: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> list[ScriptEvaluation]:
        """
        Board sets adjusted marks per question.  For double-evaluation papers this
        is required before board_finalise(); for single-evaluator papers it is
        optional (Board may adjust any question before finalising).

        Only valid when status == MARKS_SUBMITTED.
        Does NOT advance the status — board_finalise() is still required.
        """
        script = await _require_script(script_id, db=db)

        if script.status != ScriptStatus.MARKS_SUBMITTED.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Board adjustments require status MARKS_SUBMITTED "
                f"(current: {script.status!r}).",
            )

        # M09.4: reject adjustments when results are board-approved or declared (lock)
        locked = await BoardSessionRepository.get_approved_session(
            script.exam_paper_id, db=db
        )
        if locked:
            raise ScriptServiceError(
                "RESULTS_LOCKED",
                "Results for this paper are locked after Board approval. "
                "Use the Revaluation Workflow to make post-approval changes.",
                409,
            )

        updates: dict[UUID, dict] = {
            UUID(qid): {
                "board_adjusted_marks": entry.board_adjusted_marks,
                "board_adjustment_note": entry.board_adjustment_note,
            }
            for qid, entry in payload.adjustments.items()
        }
        await ScriptEvaluationRepository.bulk_update_board_adjusted_marks(
            updates, script_id=script_id, db=db
        )
        await db.commit()

        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        await AuditService.log(
            AuditEventType.SCRIPT_MARKS_UPDATED,
            actor_user_id=board_user_id,
            actor_role="BOARD",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="scanned_script",
            target_id=str(script_id),
            metadata={
                "question_count": len(updates),
                "action":         "board_adjust",
            },
        )

        return await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )

    # -----------------------------------------------------------------------
    # Board comparison view (M09.1)
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_board_comparison(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> "BoardComparisonResponse":
        """
        Board Gate 2 comparison view.

        Returns PRIMARY + SECONDARY evaluation rows side-by-side.
        For single-evaluator papers secondary_evaluations is empty and secondary_total is 0.
        Requires status == MARKS_SUBMITTED.
        Identity is masked (student_user_id / student_roll_ref not exposed here).
        """
        from app.modules.m09_paper_admin.schemas import ScriptEvaluationResponse as EvalResp

        script = await _require_script(script_id, db=db)

        if script.status != ScriptStatus.MARKS_SUBMITTED.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Board comparison view requires status MARKS_SUBMITTED "
                f"(current: {script.status!r}).",
            )

        primary_evals = await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )
        secondary_evals: list[ScriptEvaluation] = []
        if script.double_evaluation_enabled:
            secondary_evals = await ScriptEvaluationRepository.list_by_script(
                script_id, evaluation_round=EvaluationRound.SECONDARY.value, db=db
            )

        primary_total = sum(
            float(e.evaluator_marks) for e in primary_evals if e.evaluator_marks is not None
        )
        secondary_total = sum(
            float(e.evaluator_marks) for e in secondary_evals if e.evaluator_marks is not None
        )
        max_marks_total = sum(float(e.max_marks) for e in primary_evals)

        board_adjustments_set = bool(primary_evals) and all(
            e.board_adjusted_marks is not None for e in primary_evals
        )

        _mask_identity(script)
        ocr_text       = getattr(script, "ocr_text", None)
        page_image_keys = getattr(script, "page_image_keys", None)

        return BoardComparisonResponse(
            script_id=script.id,
            masked_id=script.masked_id,
            exam_paper_id=script.exam_paper_id,
            status=script.status,
            double_evaluation_enabled=script.double_evaluation_enabled,
            ocr_text=ocr_text,
            page_image_keys=page_image_keys,
            primary_evaluations=[EvalResp.model_validate(e) for e in primary_evals],
            secondary_evaluations=[EvalResp.model_validate(e) for e in secondary_evals],
            primary_total=primary_total,
            secondary_total=secondary_total,
            max_marks_total=max_marks_total,
            board_adjustments_set=board_adjustments_set,
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

    @staticmethod
    async def override_quality_failed(
        script_id: UUID,
        payload: QualityOverrideRequest,
        *,
        admin_user_id: UUID,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> ScannedScript:
        """
        STEP-12 human gate: Admin overrides a QUALITY_FAILED script.

        Allowed only when status == QUALITY_FAILED.
        Advances status → OCR_PROCESSING and dispatches ocr_scanned_script.
        Override reason is mandatory and captured in the audit log.
        This is NOT an automatic action — a named Admin must explicitly trigger it.
        """
        script = await _require_script(script_id, db=db)
        if script.status != ScriptStatus.QUALITY_FAILED.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Quality override requires status QUALITY_FAILED, got {script.status}.",
                400,
            )

        await ScriptRepository.set_quality_overridden(script_id, db=db)
        await db.commit()

        from app.workers.heavy.ocr_scanned_script import ocr_scanned_script
        ocr_scanned_script.apply_async(
            kwargs={
                "job_id":      str(script.eval_job_id or script_id),
                "script_id":   str(script_id),
                "schema_name": schema_name,
            },
            queue="celery-heavy",
        )

        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        await AuditService.log(
            AuditEventType.SCRIPT_QUALITY_OVERRIDDEN,
            actor_user_id=admin_user_id,
            actor_role="ADMIN",
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="scanned_script",
            target_id=str(script_id),
            output_summary=f"quality_override: {payload.reason[:200]}",
            confidence_score=None,
            model=None,
            prompt_hash=None,
        )

        await db.refresh(script)
        return script

    @staticmethod
    async def get_script_file_url(
        script_id: UUID,
        *,
        caller_user_id: UUID,
        caller_role: str,
        db: AsyncSession,
        expires_in: int = 300,
    ) -> str:
        """
        Return a presigned GET URL for the script's uploaded PDF/image.

        Authorization:
          - ADMIN and BOARD roles can access any script's file.
          - FACULTY/EVALUATOR callers must be the assigned evaluator or second evaluator.
        Raises ScriptServiceError NO_FILE (404) when upload_url is absent.
        Raises ScriptServiceError FORBIDDEN (403) for non-assigned faculty.
        """
        script = await _require_script(script_id, db=db)

        if not script.upload_url:
            raise ScriptServiceError(
                "NO_FILE",
                "This script has no uploaded file (digital-only exam path).",
                404,
            )

        if caller_role not in ("ADMIN", "BOARD"):
            if (
                script.evaluator_id != caller_user_id
                and script.second_evaluator_id != caller_user_id
            ):
                raise ScriptServiceError(
                    "FORBIDDEN",
                    "You are not the assigned evaluator for this script.",
                    403,
                )

        from app.core.storage.repository import StorageRepository
        return await StorageRepository.generate_presigned_get_url(
            script.upload_url,
            expires_in_seconds=expires_in,
        )

    @staticmethod
    async def export_ledger_csv(
        exam_paper_id: UUID,
        *,
        db: AsyncSession,
    ) -> str:
        """
        Return all Board-finalised score entries for a paper as a CSV string.
        Fetches up to 10 000 rows — no pagination (export context).
        student_user_id is intentionally excluded; student_roll_ref is included
        (it is already captured in the ledger row at finalisation time and is not
        subject to masking rules post-finalisation).
        """
        items, _ = await ScriptService.list_ledger_for_paper(
            exam_paper_id, offset=0, limit=10_000, db=db
        )
        header = "#,masked_script_id,student_roll_ref,total_marks,max_marks,pct,finalised_at"
        rows = [header]
        for i, entry in enumerate(items, 1):
            pct = (
                round(entry.total_marks / entry.max_marks * 100, 1)
                if entry.max_marks > 0 else ""
            )
            roll = entry.student_roll_ref or ""
            rows.append(
                f"{i},{str(entry.script_id)[:8]},{roll},"
                f"{entry.total_marks},{entry.max_marks},{pct},"
                f"{entry.finalised_at.isoformat()}"
            )
        return "\n".join(rows)

    @staticmethod
    async def get_paper_stats(
        exam_paper_id: UUID,
        *,
        db: AsyncSession,
    ) -> PaperPipelineStats:
        """
        Aggregate pipeline-status counts for all scripts in an exam paper.
        Read-only. No identity data returned.
        """
        counts = await ScriptRepository.count_by_status_for_paper(exam_paper_id, db=db)
        total   = sum(counts.values())
        board   = counts.get(ScriptStatus.BOARD_FINALISED.value, 0)
        return PaperPipelineStats(
            paper_id=exam_paper_id,
            total=total,
            pending=counts.get(ScriptStatus.PENDING.value, 0),
            quality_checking=counts.get(ScriptStatus.QUALITY_CHECKING.value, 0),
            quality_failed=counts.get(ScriptStatus.QUALITY_FAILED.value, 0),
            ocr_processing=counts.get(ScriptStatus.OCR_PROCESSING.value, 0),
            processing=counts.get(ScriptStatus.PROCESSING.value, 0),
            scored=counts.get(ScriptStatus.SCORED.value, 0),
            failed=counts.get(ScriptStatus.FAILED.value, 0),
            review_required=counts.get(ScriptStatus.REVIEW_REQUIRED.value, 0),
            waiting_second_evaluator=counts.get(ScriptStatus.WAITING_SECOND_EVALUATOR.value, 0),
            secondary_evaluated=counts.get(ScriptStatus.SECONDARY_EVALUATED.value, 0),
            marks_submitted=counts.get(ScriptStatus.MARKS_SUBMITTED.value, 0),
            moderation_pending=counts.get(ScriptStatus.MODERATION_PENDING.value, 0),
            moderation_complete=counts.get(ScriptStatus.MODERATION_COMPLETE.value, 0),
            board_finalised=board,
            completion_pct=round(board / total * 100, 1) if total > 0 else 0.0,
        )


# ---------------------------------------------------------------------------
# ModerationService — M09.2
# ---------------------------------------------------------------------------

class ModerationService:

    # -----------------------------------------------------------------------
    # Get variance — pre-moderation comparison view
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_variance(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> "ScriptVarianceResponse":
        """
        Return primary vs secondary evaluator totals and variance % for a script.
        Available for any double-evaluation script from SECONDARY_EVALUATED onward.
        For single-evaluator scripts, secondary_total is 0 and variance_pct is 0.
        Identity is always masked.
        """
        from app.modules.m09_paper_admin.schemas import ScriptVarianceResponse

        script = await _require_script(script_id, db=db)

        primary_total = await ScriptEvaluationRepository.sum_evaluator_marks(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )
        secondary_total = (
            await ScriptEvaluationRepository.sum_evaluator_marks(
                script_id, evaluation_round=EvaluationRound.SECONDARY.value, db=db
            )
            if script.double_evaluation_enabled else 0.0
        )
        max_marks_total = await ScriptEvaluationRepository.sum_max_marks(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )
        threshold_pct = await ModerationRepository.get_threshold(
            script.exam_paper_id, db=db
        )
        variance_pct = (
            abs(primary_total - secondary_total) / max_marks_total * 100
            if max_marks_total > 0 else 0.0
        )

        review = await ModerationRepository.get_by_script(script_id, db=db)

        return ScriptVarianceResponse(
            script_id=script.id,
            masked_id=script.masked_id,
            exam_paper_id=script.exam_paper_id,
            status=script.status,
            double_evaluation_enabled=script.double_evaluation_enabled,
            primary_total=primary_total,
            secondary_total=secondary_total,
            max_marks_total=max_marks_total,
            variance_pct=round(variance_pct, 2),
            threshold_pct=threshold_pct,
            exceeds_threshold=(variance_pct > threshold_pct),
            moderation_review_id=review.id if review else None,
            moderation_status=review.status if review else None,
        )

    # -----------------------------------------------------------------------
    # Manual flag — Dean/Admin flags MARKS_SUBMITTED script
    # -----------------------------------------------------------------------

    @staticmethod
    async def flag_for_moderation(
        script_id: UUID,
        *,
        reason: str,
        flagged_by: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> "ScriptModerationReview":
        """
        Dean/Admin manually flags a script for moderation.
        Only valid when status == MARKS_SUBMITTED.
        Creates a moderation review row and advances to MODERATION_PENDING.
        """
        from app.modules.m09_paper_admin.schemas import ModerationReviewResponse
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService

        script = await _require_script(script_id, db=db)

        if script.status != ScriptStatus.MARKS_SUBMITTED.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Manual moderation flag requires status MARKS_SUBMITTED "
                f"(current: {script.status!r}).",
            )

        existing = await ModerationRepository.get_by_script(script_id, db=db)
        if existing and existing.status == ModerationStatus.PENDING:
            raise ScriptServiceError(
                "ALREADY_FLAGGED",
                "This script already has a pending moderation review.",
                409,
            )

        primary_total = await ScriptEvaluationRepository.sum_evaluator_marks(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )
        secondary_total = (
            await ScriptEvaluationRepository.sum_evaluator_marks(
                script_id, evaluation_round=EvaluationRound.SECONDARY.value, db=db
            )
            if script.double_evaluation_enabled else 0.0
        )
        max_marks_total = await ScriptEvaluationRepository.sum_max_marks(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )
        threshold_pct = await ModerationRepository.get_threshold(
            script.exam_paper_id, db=db
        )
        variance_pct = (
            abs(primary_total - secondary_total) / max_marks_total * 100
            if max_marks_total > 0 else 0.0
        )

        review = await ModerationRepository.create(
            script_id=script_id,
            exam_paper_id=script.exam_paper_id,
            primary_total=primary_total,
            secondary_total=secondary_total,
            variance_pct=round(variance_pct, 2),
            variance_threshold=threshold_pct,
            flag_reason=reason,
            flagged_by=flagged_by,
            db=db,
        )
        await ScriptRepository.set_moderation_pending(script_id, db=db)
        await db.commit()
        await db.refresh(review)

        await AuditService.log(
            AuditEventType.SCRIPT_MODERATION_FLAGGED,
            actor_user_id=flagged_by,
            actor_role="DEAN",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="scanned_script",
            target_id=str(script_id),
            metadata={
                "flag_reason":     reason,
                "variance_pct":    round(variance_pct, 2),
                "threshold_pct":   threshold_pct,
                "review_id":       str(review.id),
            },
        )
        return review

    # -----------------------------------------------------------------------
    # Submit moderation — moderator enters per-question marks
    # -----------------------------------------------------------------------

    @staticmethod
    async def submit_moderation(
        script_id: UUID,
        payload: "ModerationSubmitRequest",
        *,
        moderator_id: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> tuple[ScriptModerationReview, list[ScriptEvaluation]]:
        """
        Moderator submits per-question marks for a MODERATION_PENDING script.

        Sequence:
          1. Validate status == MODERATION_PENDING and a moderation review exists.
          2. Verify all PRIMARY round questions are covered in the payload.
          3. Create MODERATION round ScriptEvaluation rows.
          4. Mark moderation review COMPLETE.
          5. Advance script status → MODERATION_COMPLETE.
          6. Log audit event.

        Human-gate invariant:
          - Original PRIMARY / SECONDARY evaluator_marks are never modified.
          - MODERATION round rows carry the moderator's authoritative marks.
          - board_finalise will use MODERATION round for final_marks.
        """
        from app.modules.m09_paper_admin.schemas import ModerationSubmitRequest
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService

        script = await _require_script(script_id, db=db)

        if script.status != ScriptStatus.MODERATION_PENDING.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Moderation submit requires status MODERATION_PENDING "
                f"(current: {script.status!r}).",
            )

        review = await ModerationRepository.get_by_script(script_id, db=db)
        if review is None or review.status != ModerationStatus.PENDING:
            raise ScriptServiceError(
                "NO_REVIEW",
                "No pending moderation review found for this script.",
                404,
            )

        primary_evals = await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )
        if not primary_evals:
            raise ScriptServiceError(
                "NO_EVALUATIONS",
                "No PRIMARY evaluation rows found for this script.",
                422,
            )

        primary_question_ids = {e.question_id for e in primary_evals}
        submitted_ids = {UUID(qid) for qid in payload.marks}
        missing = primary_question_ids - submitted_ids
        if missing:
            raise ScriptServiceError(
                "INCOMPLETE_MARKS",
                f"Moderation marks missing for {len(missing)} question(s). "
                "All questions from the PRIMARY round must be covered.",
                422,
            )

        marks_by_uuid: dict[UUID, dict] = {
            UUID(qid): {
                "evaluator_marks": m.evaluator_marks,
                "evaluator_note":  m.evaluator_note,
            }
            for qid, m in payload.marks.items()
        }

        moderation_evals = await ScriptEvaluationRepository.bulk_create_moderation_evaluations(
            marks_by_uuid,
            primary_evals=primary_evals,
            script_id=script_id,
            db=db,
        )

        await ModerationRepository.complete(
            review,
            moderator_id=moderator_id,
            moderation_notes=payload.moderation_notes,
            db=db,
        )
        await ScriptRepository.set_moderation_complete(script_id, db=db)
        await db.commit()
        await db.refresh(review)

        await AuditService.log(
            AuditEventType.SCRIPT_MODERATION_SUBMITTED,
            actor_user_id=moderator_id,
            actor_role="DEAN",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="scanned_script",
            target_id=str(script_id),
            metadata={
                "review_id":        str(review.id),
                "question_count":   len(moderation_evals),
                "moderation_notes": payload.moderation_notes[:200],
            },
        )
        return review, moderation_evals

    # -----------------------------------------------------------------------
    # Moderation history — full audit trail for a script
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_moderation_history(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> "ModerationHistoryResponse":
        """
        Return the moderation review record plus all three evaluation rounds.
        Available for MODERATION_PENDING, MODERATION_COMPLETE, and BOARD_FINALISED scripts.
        Identity is always masked.
        """
        from app.modules.m09_paper_admin.schemas import (
            ModerationHistoryResponse,
            ModerationReviewResponse,
            ScriptEvaluationResponse,
        )

        await _require_script(script_id, db=db)

        review = await ModerationRepository.get_by_script(script_id, db=db)
        primary_evals = await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )
        secondary_evals = await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.SECONDARY.value, db=db
        )
        moderation_evals = await ScriptEvaluationRepository.list_by_script(
            script_id, evaluation_round=EvaluationRound.MODERATION.value, db=db
        )

        return ModerationHistoryResponse(
            review=(
                ModerationReviewResponse.model_validate(review) if review else None
            ),
            moderation_evals=[ScriptEvaluationResponse.model_validate(e) for e in moderation_evals],
            primary_evals=[ScriptEvaluationResponse.model_validate(e) for e in primary_evals],
            secondary_evals=[ScriptEvaluationResponse.model_validate(e) for e in secondary_evals],
        )

    # -----------------------------------------------------------------------
    # Moderation queue — MODERATION_PENDING scripts for an exam paper
    # -----------------------------------------------------------------------

    @staticmethod
    async def list_moderation_queue(
        exam_paper_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[ScriptModerationReview], int]:
        """List all PENDING moderation reviews for an exam paper, sorted by variance_pct desc."""
        items = await ModerationRepository.list_pending_for_paper(
            exam_paper_id, offset=offset, limit=limit, db=db
        )
        total = await ModerationRepository.count_pending_for_paper(
            exam_paper_id, db=db
        )
        return items, total

    # -----------------------------------------------------------------------
    # Auto-flag all high-variance scripts for a paper
    # -----------------------------------------------------------------------

    @staticmethod
    async def auto_flag_paper(
        exam_paper_id: UUID,
        *,
        flagged_by: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> dict:
        """
        Scan all MARKS_SUBMITTED double-evaluation scripts for a paper and
        auto-flag those exceeding the paper's discrepancy_threshold_pct.
        Returns counts: {checked, flagged, already_pending, skipped}.
        """
        from sqlalchemy import select
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService

        threshold_pct = await ModerationRepository.get_threshold(exam_paper_id, db=db)

        q = (
            select(ScannedScript)
            .where(
                ScannedScript.exam_paper_id == exam_paper_id,
                ScannedScript.status == ScriptStatus.MARKS_SUBMITTED.value,
                ScannedScript.double_evaluation_enabled.is_(True),
            )
        )
        result = await db.execute(q)
        scripts = list(result.scalars().all())

        checked = flagged = already_pending = skipped = 0
        for script in scripts:
            checked += 1
            existing = await ModerationRepository.get_by_script(script.id, db=db)
            if existing and existing.status == ModerationStatus.PENDING:
                already_pending += 1
                continue

            primary_total = await ScriptEvaluationRepository.sum_evaluator_marks(
                script.id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
            )
            secondary_total = await ScriptEvaluationRepository.sum_evaluator_marks(
                script.id, evaluation_round=EvaluationRound.SECONDARY.value, db=db
            )
            max_marks_total = await ScriptEvaluationRepository.sum_max_marks(
                script.id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
            )
            variance_pct = (
                abs(primary_total - secondary_total) / max_marks_total * 100
                if max_marks_total > 0 else 0.0
            )

            if variance_pct > threshold_pct:
                await ModerationRepository.create(
                    script_id=script.id,
                    exam_paper_id=exam_paper_id,
                    primary_total=primary_total,
                    secondary_total=secondary_total,
                    variance_pct=round(variance_pct, 2),
                    variance_threshold=threshold_pct,
                    flag_reason="AUTO_VARIANCE",
                    flagged_by=flagged_by,
                    db=db,
                )
                await ScriptRepository.set_moderation_pending(script.id, db=db)
                flagged += 1
            else:
                skipped += 1

        if flagged > 0:
            await db.commit()

        await AuditService.log(
            AuditEventType.SCRIPT_MODERATION_FLAGGED,
            actor_user_id=flagged_by,
            actor_role="DEAN",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="exam_paper",
            target_id=str(exam_paper_id),
            metadata={
                "action":          "auto_flag_paper",
                "checked":         checked,
                "flagged":         flagged,
                "already_pending": already_pending,
                "skipped":         skipped,
                "threshold_pct":   threshold_pct,
            },
        )
        return {
            "checked":         checked,
            "flagged":         flagged,
            "already_pending": already_pending,
            "skipped":         skipped,
        }


# ---------------------------------------------------------------------------
# BoardApprovalService — M09.4 Examination Board Results Approval
# ---------------------------------------------------------------------------

class BoardApprovalService:
    """
    Examination Board results approval workflow.

    Human-gate invariants:
      convene()  → only Dean/Admin; paper must have all scripts BOARD_FINALISED.
      approve()  → status OPEN only; no further mark changes after this point.
      reject()   → status OPEN only; scripts released for re-evaluation.
      declare()  → status APPROVED only; Admin only.
    """

    # -----------------------------------------------------------------------
    # Convene session
    # -----------------------------------------------------------------------

    @staticmethod
    async def convene(
        exam_paper_id: UUID,
        session_title: str,
        pass_mark_pct: float,
        *,
        convened_by: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> ExamBoardSession:
        """
        Create a new board session for a paper's results.

        Preconditions:
          - At least one BOARD_FINALISED script must exist for the paper.
          - No OPEN session may already exist (prevents double-convening).
        Computes aggregate statistics (mean, pass rate) from the ledger at convene time.
        """
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        import math

        # Guard: no existing OPEN session
        existing_open = await BoardSessionRepository.get_open_session(exam_paper_id, db=db)
        if existing_open:
            raise ScriptServiceError(
                "SESSION_ALREADY_OPEN",
                "An open board session already exists for this paper. "
                "Close or decide the existing session before creating a new one.",
                409,
            )

        # Guard: at least one BOARD_FINALISED script
        count_q = select(func.count(ScannedScript.id)).where(
            ScannedScript.exam_paper_id == exam_paper_id,
            ScannedScript.status == ScriptStatus.BOARD_FINALISED.value,
        )
        count_result = await db.execute(count_q)
        finalised_count = count_result.scalar_one() or 0
        if finalised_count == 0:
            raise ScriptServiceError(
                "NO_FINALISED_SCRIPTS",
                "Cannot convene a board session: no BOARD_FINALISED scripts found for this paper.",
                422,
            )

        # Compute statistics from the exam_score_ledger
        from sqlalchemy import func as sa_func
        ledger_q = select(ExamScoreLedger).where(
            ExamScoreLedger.exam_paper_id == exam_paper_id
        )
        ledger_result = await db.execute(ledger_q)
        ledger_entries = list(ledger_result.scalars().all())

        total_scripts  = len(ledger_entries)
        mean_marks:    float | None = None
        max_marks_val: float | None = None
        pass_count     = 0
        fail_count     = 0
        pass_rate_pct: float | None = None

        if ledger_entries:
            scores     = [float(e.total_marks) for e in ledger_entries]
            max_marks_val = float(ledger_entries[0].max_marks) if ledger_entries else None
            mean_marks = sum(scores) / len(scores)
            pass_threshold = (pass_mark_pct / 100.0) * (max_marks_val or 0.0)
            pass_count = sum(1 for s in scores if s >= pass_threshold)
            fail_count = total_scripts - pass_count
            pass_rate_pct = round(pass_count / total_scripts * 100, 2) if total_scripts > 0 else 0.0

        # Create session
        session = await BoardSessionRepository.create(
            exam_paper_id=exam_paper_id,
            session_title=session_title,
            convened_by=convened_by,
            db=db,
        )

        # Create stats snapshot
        await BoardCourseApprovalRepository.create(
            session_id=session.id,
            exam_paper_id=exam_paper_id,
            mean_marks=round(mean_marks, 2) if mean_marks is not None else None,
            max_marks=max_marks_val,
            pass_count=pass_count,
            fail_count=fail_count,
            total_scripts=total_scripts,
            pass_rate_pct=pass_rate_pct,
            db=db,
        )

        await db.commit()
        await db.refresh(session)

        await AuditService.log(
            AuditEventType.BOARD_SESSION_CONVENED,
            actor_user_id=convened_by,
            actor_role="DEAN",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="exam_paper",
            target_id=str(exam_paper_id),
            metadata={
                "session_id":      str(session.id),
                "session_title":   session_title,
                "finalised_count": finalised_count,
                "total_ledger":    total_scripts,
                "pass_rate_pct":   pass_rate_pct,
            },
        )
        return session

    # -----------------------------------------------------------------------
    # Approve
    # -----------------------------------------------------------------------

    @staticmethod
    async def approve(
        session_id: UUID,
        board_remarks: str | None,
        *,
        decided_by: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> ExamBoardSession:
        """
        Board approves results. Locks the paper — no further mark adjustments.
        Only valid when session status == OPEN.
        """
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService

        session = await _require_board_session(session_id, db=db)

        if session.status != BoardSessionStatus.OPEN.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Board approve requires session status OPEN (current: {session.status!r}).",
            )

        await BoardSessionRepository.approve(
            session, decided_by=decided_by, board_remarks=board_remarks, db=db
        )
        # Update stats snapshot approval status
        approval = await BoardCourseApprovalRepository.get_by_session(session_id, db=db)
        if approval:
            await BoardCourseApprovalRepository.set_approval_status(
                approval, BoardApprovalStatus.APPROVED, db=db
            )

        await db.commit()
        await db.refresh(session)

        await AuditService.log(
            AuditEventType.BOARD_SESSION_APPROVED,
            actor_user_id=decided_by,
            actor_role="DEAN",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="exam_board_session",
            target_id=str(session_id),
            metadata={
                "exam_paper_id": str(session.exam_paper_id),
                "board_remarks": board_remarks,
            },
        )
        return session

    # -----------------------------------------------------------------------
    # Reject
    # -----------------------------------------------------------------------

    @staticmethod
    async def reject(
        session_id: UUID,
        board_remarks: str,
        *,
        decided_by: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> ExamBoardSession:
        """Board rejects results. Session status → REJECTED; scripts released for correction."""
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService

        session = await _require_board_session(session_id, db=db)

        if session.status != BoardSessionStatus.OPEN.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Board reject requires session status OPEN (current: {session.status!r}).",
            )

        await BoardSessionRepository.reject(
            session, decided_by=decided_by, board_remarks=board_remarks, db=db
        )
        approval = await BoardCourseApprovalRepository.get_by_session(session_id, db=db)
        if approval:
            await BoardCourseApprovalRepository.set_approval_status(
                approval, BoardApprovalStatus.REJECTED, db=db
            )

        await db.commit()
        await db.refresh(session)

        await AuditService.log(
            AuditEventType.BOARD_SESSION_REJECTED,
            actor_user_id=decided_by,
            actor_role="DEAN",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="exam_board_session",
            target_id=str(session_id),
            metadata={
                "exam_paper_id": str(session.exam_paper_id),
                "board_remarks": board_remarks,
            },
        )
        return session

    # -----------------------------------------------------------------------
    # Declare
    # -----------------------------------------------------------------------

    @staticmethod
    async def declare(
        session_id: UUID,
        *,
        declared_by: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> ExamBoardSession:
        """
        Admin publishes results. Only valid when session status == APPROVED.
        After this, results are visible to students.
        """
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService

        session = await _require_board_session(session_id, db=db)

        if session.status != BoardSessionStatus.APPROVED.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Results declaration requires session status APPROVED "
                f"(current: {session.status!r}).",
            )

        await BoardSessionRepository.declare(session, declared_by=declared_by, db=db)
        await db.commit()
        await db.refresh(session)

        await AuditService.log(
            AuditEventType.RESULTS_DECLARED,
            actor_user_id=declared_by,
            actor_role="ADMIN",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="exam_board_session",
            target_id=str(session_id),
            metadata={
                "exam_paper_id": str(session.exam_paper_id),
                "session_title": session.session_title,
            },
        )
        return session

    # -----------------------------------------------------------------------
    # Read operations
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_session(session_id: UUID, *, db: AsyncSession) -> ExamBoardSession:
        """Return a board session by ID."""
        session = await _require_board_session(session_id, db=db)
        return session

    @staticmethod
    async def list_sessions(
        exam_paper_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[ExamBoardSession], int]:
        items = await BoardSessionRepository.list_for_paper(
            exam_paper_id, offset=offset, limit=limit, db=db
        )
        total = await BoardSessionRepository.count_for_paper(exam_paper_id, db=db)
        return items, total

    @staticmethod
    async def get_statistics(
        session_id: UUID,
        *,
        db: AsyncSession,
    ) -> ExamBoardCourseApproval | None:
        """Return the aggregate statistics snapshot for a session."""
        return await BoardCourseApprovalRepository.get_by_session(session_id, db=db)

    @staticmethod
    async def get_board_status(
        exam_paper_id: UUID,
        *,
        db: AsyncSession,
    ) -> dict:
        """Current board gate status for a paper."""
        # Count scripts by status
        counts_q = (
            select(ScannedScript.status, func.count(ScannedScript.id))
            .where(ScannedScript.exam_paper_id == exam_paper_id)
            .group_by(ScannedScript.status)
        )
        counts_result = await db.execute(counts_q)
        counts = {row[0]: row[1] for row in counts_result.all()}

        total         = sum(counts.values())
        finalised     = counts.get(ScriptStatus.BOARD_FINALISED.value, 0)
        mod_pending   = counts.get(ScriptStatus.MODERATION_PENDING.value, 0)
        mod_complete  = counts.get(ScriptStatus.MODERATION_COMPLETE.value, 0)
        all_finalised = (total > 0) and (finalised == total)

        # Most recent session
        sessions = await BoardSessionRepository.list_for_paper(
            exam_paper_id, offset=0, limit=1, db=db
        )
        latest = sessions[0] if sessions else None

        return {
            "exam_paper_id":      str(exam_paper_id),
            "total_scripts":      total,
            "finalised_scripts":  finalised,
            "moderation_pending": mod_pending,
            "moderation_complete": mod_complete,
            "all_finalised":      all_finalised,
            "ready_for_board":    all_finalised and (not latest or latest.status == BoardSessionStatus.REJECTED.value),
            "latest_session_id":  str(latest.id) if latest else None,
            "latest_session_status": latest.status if latest else None,
        }


async def _require_board_session(session_id: UUID, *, db: AsyncSession) -> ExamBoardSession:
    """Load a board session or raise 404."""
    session = await BoardSessionRepository.get_by_id(session_id, db=db)
    if session is None:
        raise ScriptServiceError("NOT_FOUND", f"Board session {session_id!r} not found.", 404)
    return session


async def _require_revaluation(request_id: UUID, *, db: AsyncSession) -> RevaluationRequest:
    """Load a revaluation request or raise 404."""
    req = await RevaluationRepository.get_by_id(request_id, db=db)
    if req is None:
        raise ScriptServiceError("NOT_FOUND", f"Revaluation request {request_id!r} not found.", 404)
    return req


# ---------------------------------------------------------------------------
# RevaluationService — M09.3 Post-publication revaluation workflow
# ---------------------------------------------------------------------------

class RevaluationService:
    """
    Revaluation workflow.

    This is the ONLY legitimate post-publication mark change path.

    Human-gate invariants:
      - Only DECLARED scripts may have revaluation requests.
      - assigned_evaluator_id must differ from original + second evaluator.
      - awarded_total = max(original_total, revaluation_total) — never less.
      - Board ratification required before updating exam_score_ledger.
      - All changes append to ledger via a new ledger row (original preserved).
    """

    # -----------------------------------------------------------------------
    # Submit (Student)
    # -----------------------------------------------------------------------

    @staticmethod
    async def submit_request(
        script_id: UUID,
        reason: str,
        payment_reference: str | None,
        *,
        student_user_id: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> RevaluationRequest:
        """
        Student submits a revaluation request.

        Preconditions:
          - Script must be BOARD_FINALISED.
          - A DECLARED board session must exist for the paper.
          - No active revaluation request may already exist for this script.
        """
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        from datetime import datetime, timezone, timedelta

        script = await _require_script(script_id, db=db)

        if script.status != ScriptStatus.BOARD_FINALISED.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Revaluation requests require script status BOARD_FINALISED "
                f"(current: {script.status!r}).",
            )

        # Check declared board session exists for this paper
        declared_session = await BoardSessionRepository.get_by_id_and_status(
            script.exam_paper_id, BoardSessionStatus.DECLARED.value, db=db
        ) if hasattr(BoardSessionRepository, "get_by_id_and_status") else None
        # Simplified: check for any DECLARED session
        sessions = await BoardSessionRepository.list_for_paper(
            script.exam_paper_id, offset=0, limit=1, db=db
        )
        declared = any(s.status == BoardSessionStatus.DECLARED.value for s in sessions)
        if not declared:
            raise ScriptServiceError(
                "RESULTS_NOT_DECLARED",
                "Revaluation requests can only be submitted after results are declared.",
                422,
            )

        # Guard: no active revaluation request
        active_count = await RevaluationRepository.count_open_for_script(script_id, db=db)
        if active_count > 0:
            raise ScriptServiceError(
                "ACTIVE_REQUEST_EXISTS",
                "An active revaluation request already exists for this script.",
                409,
            )

        # Get original total from ledger
        ledger_entry = await ExamScoreLedgerRepository.get_by_script(script_id, db=db)
        if ledger_entry is None:
            raise ScriptServiceError(
                "NO_LEDGER_ENTRY",
                "No finalised score found for this script.",
                422,
            )

        # Default revaluation window: 10 days from now
        window_closes_at = datetime.now(timezone.utc) + timedelta(days=10)

        req = await RevaluationRepository.create(
            script_id=script_id,
            exam_paper_id=script.exam_paper_id,
            student_user_id=student_user_id,
            student_roll_ref=script.student_roll_ref,
            original_total=float(ledger_entry.total_marks),
            max_marks=float(ledger_entry.max_marks),
            reason=reason,
            payment_reference=payment_reference,
            window_closes_at=window_closes_at,
            db=db,
        )
        await db.commit()
        await db.refresh(req)

        await AuditService.log(
            AuditEventType.REVALUATION_REQUESTED,
            actor_user_id=student_user_id,
            actor_role="STUDENT",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="scanned_script",
            target_id=str(script_id),
            metadata={
                "request_id":        str(req.id),
                "original_total":    float(ledger_entry.total_marks),
                "reason_summary":    reason[:200],
                "payment_reference": payment_reference,
            },
        )
        return req

    # -----------------------------------------------------------------------
    # Accept (Admin)
    # -----------------------------------------------------------------------

    @staticmethod
    async def accept_request(
        request_id: UUID,
        assigned_evaluator_id: UUID,
        admin_notes: str | None,
        *,
        admin_user_id: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> RevaluationRequest:
        """
        Admin accepts the request and assigns a senior evaluator.
        Evaluator must not be the original or second evaluator.
        """
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService

        req = await _require_revaluation(request_id, db=db)
        if req.status != RevaluationStatus.SUBMITTED.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Accept requires status SUBMITTED (current: {req.status!r}).",
            )

        # Guard: evaluator must differ from originals
        script = await _require_script(req.script_id, db=db)
        if assigned_evaluator_id in {script.evaluator_id, script.second_evaluator_id}:
            raise ScriptServiceError(
                "EVALUATOR_CONFLICT",
                "The assigned revaluation evaluator must differ from the original evaluator(s).",
                422,
            )

        await RevaluationRepository.accept(
            req,
            assigned_evaluator_id=assigned_evaluator_id,
            admin_notes=admin_notes,
            db=db,
        )
        await db.commit()
        await db.refresh(req)

        await AuditService.log(
            AuditEventType.REVALUATION_ACCEPTED,
            actor_user_id=admin_user_id,
            actor_role="ADMIN",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="revaluation_request",
            target_id=str(request_id),
            metadata={
                "assigned_evaluator_id": str(assigned_evaluator_id),
                "admin_notes": admin_notes,
            },
        )
        return req

    # -----------------------------------------------------------------------
    # Reject at intake (Admin)
    # -----------------------------------------------------------------------

    @staticmethod
    async def reject_request(
        request_id: UUID,
        admin_notes: str,
        *,
        admin_user_id: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> RevaluationRequest:
        """Admin rejects the request at intake."""
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService

        req = await _require_revaluation(request_id, db=db)
        if req.status != RevaluationStatus.SUBMITTED.value:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Reject requires status SUBMITTED (current: {req.status!r}).",
            )

        await RevaluationRepository.reject_intake(
            req, admin_notes=admin_notes, decided_by=admin_user_id, db=db
        )
        await db.commit()
        await db.refresh(req)

        await AuditService.log(
            AuditEventType.REVALUATION_REJECTED,
            actor_user_id=admin_user_id,
            actor_role="ADMIN",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="revaluation_request",
            target_id=str(request_id),
            metadata={"admin_notes": admin_notes},
        )
        return req

    # -----------------------------------------------------------------------
    # Submit marks (Faculty revaluator)
    # -----------------------------------------------------------------------

    @staticmethod
    async def submit_revaluation_marks(
        request_id: UUID,
        marks: dict,  # {question_id str → RevaluationMarkEntry}
        submission_note: str | None,
        *,
        evaluator_user_id: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> RevaluationRequest:
        """
        Assigned evaluator submits per-question revaluation marks.
        Status transitions: ACCEPTED or IN_PROGRESS → EVALUATED.
        Computes revaluation_total as sum of revaluation_marks.
        """
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        from app.modules.m09_paper_admin.schemas import RevaluationMarkEntry

        req = await _require_revaluation(request_id, db=db)
        valid = {RevaluationStatus.ACCEPTED.value, RevaluationStatus.IN_PROGRESS.value}
        if req.status not in valid:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Submit marks requires status ACCEPTED or IN_PROGRESS (current: {req.status!r}).",
            )

        if req.assigned_evaluator_id != evaluator_user_id:
            raise ScriptServiceError(
                "UNAUTHORIZED_EVALUATOR",
                "Only the assigned evaluator may submit revaluation marks.",
                403,
            )

        # Get PRIMARY evaluations to copy original_marks
        primary_evals = await ScriptEvaluationRepository.list_by_script(
            req.script_id, evaluation_round=EvaluationRound.PRIMARY.value, db=db
        )
        original_by_qid = {e.question_id: float(e.evaluator_marks or 0) for e in primary_evals}

        rows = []
        revaluation_total = 0.0
        for qid_str, entry in marks.items():
            from uuid import UUID as _UUID
            q_id = _UUID(qid_str)
            rows.append({
                "question_id":       q_id,
                "question_type":     next((e.question_type for e in primary_evals if e.question_id == q_id), None),
                "max_marks":         next((float(e.max_marks) for e in primary_evals if e.question_id == q_id), None),
                "original_marks":    original_by_qid.get(q_id),
                "revaluation_marks": entry.revaluation_marks if hasattr(entry, "revaluation_marks") else entry["revaluation_marks"],
                "evaluator_note":    entry.evaluator_note if hasattr(entry, "evaluator_note") else entry.get("evaluator_note"),
            })
            revaluation_total += rows[-1]["revaluation_marks"]

        await RevaluationEvaluationRepository.bulk_create(
            request_id=request_id, marks=rows, db=db
        )
        await RevaluationRepository.submit_marks(
            req, revaluation_total=revaluation_total, db=db
        )
        await db.commit()
        await db.refresh(req)

        await AuditService.log(
            AuditEventType.REVALUATION_MARKS_SUBMITTED,
            actor_user_id=evaluator_user_id,
            actor_role="FACULTY",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="revaluation_request",
            target_id=str(request_id),
            metadata={
                "revaluation_total": revaluation_total,
                "question_count":    len(rows),
                "submission_note":   submission_note,
            },
        )
        return req

    # -----------------------------------------------------------------------
    # Board ratify
    # -----------------------------------------------------------------------

    @staticmethod
    async def board_ratify(
        request_id: UUID,
        board_remarks: str | None,
        *,
        decided_by: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> RevaluationRequest:
        """
        Board ratifies the revaluation outcome.
        awarded_total = max(original_total, revaluation_total).
        Updates exam_score_ledger with awarded_total.
        """
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService

        req = await _require_revaluation(request_id, db=db)
        valid = {RevaluationStatus.EVALUATED.value, RevaluationStatus.BOARD_REVIEW.value}
        if req.status not in valid:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Board ratify requires status EVALUATED or BOARD_REVIEW (current: {req.status!r}).",
            )

        # Compute awarded_total = max(original, revaluation)
        await RevaluationRepository.board_ratify(
            req,
            decided_by=decided_by,
            board_remarks=board_remarks,
            db=db,
        )

        await db.commit()
        await db.refresh(req)

        await AuditService.log(
            AuditEventType.REVALUATION_BOARD_RATIFIED,
            actor_user_id=decided_by,
            actor_role="BOARD",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="revaluation_request",
            target_id=str(request_id),
            metadata={
                "original_total":    float(req.original_total),
                "revaluation_total": float(req.revaluation_total or 0),
                "awarded_total":     float(req.awarded_total or 0),
                "board_remarks":     board_remarks,
            },
        )
        return req

    # -----------------------------------------------------------------------
    # Board reject
    # -----------------------------------------------------------------------

    @staticmethod
    async def board_reject(
        request_id: UUID,
        board_remarks: str,
        *,
        decided_by: UUID,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> RevaluationRequest:
        """Board rejects the revaluation outcome — original marks stand."""
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService

        req = await _require_revaluation(request_id, db=db)
        valid = {RevaluationStatus.EVALUATED.value, RevaluationStatus.BOARD_REVIEW.value}
        if req.status not in valid:
            raise ScriptServiceError(
                "INVALID_STATUS",
                f"Board reject requires status EVALUATED or BOARD_REVIEW (current: {req.status!r}).",
            )

        await RevaluationRepository.board_reject(
            req, decided_by=decided_by, board_remarks=board_remarks, db=db
        )
        await db.commit()
        await db.refresh(req)

        await AuditService.log(
            AuditEventType.REVALUATION_BOARD_REJECTED,
            actor_user_id=decided_by,
            actor_role="BOARD",
            tenant_id=tenant_id,
            schema_name=None,
            target_entity="revaluation_request",
            target_id=str(request_id),
            metadata={
                "original_total": float(req.original_total),
                "board_remarks":  board_remarks,
            },
        )
        return req

    # -----------------------------------------------------------------------
    # Read operations
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_request(
        request_id: UUID,
        *,
        requester_user_id: UUID,
        requester_role: str,
        db: AsyncSession,
    ) -> RevaluationRequest:
        """
        Fetch a revaluation request.
        Students may only fetch their own requests.
        """
        req = await _require_revaluation(request_id, db=db)
        if requester_role == "STUDENT" and req.student_user_id != requester_user_id:
            raise ScriptServiceError(
                "FORBIDDEN",
                "Students may only view their own revaluation requests.",
                403,
            )
        return req

    @staticmethod
    async def list_requests_for_paper(
        exam_paper_id: UUID,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[RevaluationRequest]:
        return await RevaluationRepository.list_for_paper(
            exam_paper_id, status=status, offset=offset, limit=limit, db=db
        )

    @staticmethod
    async def list_my_requests(
        student_user_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[RevaluationRequest]:
        return await RevaluationRepository.list_for_student(
            student_user_id, offset=offset, limit=limit, db=db
        )

    @staticmethod
    async def get_request_detail(
        request_id: UUID,
        *,
        requester_user_id: UUID,
        requester_role: str,
        db: AsyncSession,
    ):
        """Fetch request + evaluations."""
        from app.modules.m09_paper_admin.schemas import (
            RevaluationDetailResponse,
            RevaluationEvaluationResponse,
            RevaluationRequestResponse,
        )
        req = await RevaluationService.get_request(
            request_id,
            requester_user_id=requester_user_id,
            requester_role=requester_role,
            db=db,
        )
        evals = await RevaluationEvaluationRepository.list_for_request(request_id, db=db)
        return RevaluationDetailResponse(
            request=RevaluationRequestResponse.model_validate(req),
            evaluations=[RevaluationEvaluationResponse.model_validate(e) for e in evals],
        )
