"""
Celery heavy-queue task: AI-evaluate a coursework submission (M04). ADVISORY.

Flow:
  1. Load submission + assignment (+ course context, course outcomes).
  2. status -> EXTRACTING; get submission text (reuse m06 text_extractor for
     files; inline text is used as-is). Extraction failure -> status FAILED.
  3. status -> EVALUATING; run the coursework AI evaluator (reuses the same
     google-genai client m06 uses).
  4. Internal similarity across THIS assignment's other submissions
     (reuse m06 compute_plagiarism). No external sources — plagiarism_status
     stays PLACEHOLDER.
  5. Persist results -> status COMPLETED. Audit COURSEWORK_AI_EVAL_COMPLETED.

Reliability guarantees:
  * The student submission is committed BEFORE this task runs — nothing here can
    lose it.
  * Any failure sets status=FAILED + error_log and returns; manual grading and
    finalization are never blocked.
  * Re-runnable: the API exposes a retry that re-enqueues this task.
"""
import asyncio
import logging
import sys
import time
from uuid import UUID

from app.database import tenant_schema_scope
from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m04.evaluate_coursework_submission")


def _make_async_engine():
    """Fresh NullPool async engine per task — see evaluate_lab_submission for the
    event-loop rationale (asyncpg pools are bound to the loop that made them)."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.config import settings
    from app.database import bind_tenant_search_path
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    # And because of NullPool, a commit does not return this task's connection to a
    # pool — it CLOSES it. A session-level `SET search_path` therefore survives only
    # until the first commit; everything after it ran on a fresh connection with
    # search_path = public, which is why this job died on `assignment_evaluations`
    # — a table that plainly exists in the tenant schema. The schema is instead
    # re-applied at the start of every transaction (app/database.py), the one place
    # a commit cannot undo it.
    bind_tenant_search_path(engine)
    return engine


@celery_app.task(
    bind=True,
    base=VidyaTask,
    name="app.workers.heavy.evaluate_coursework_submission",
    max_retries=2,
)
def evaluate_coursework_submission(
    self,
    *,
    submission_id: str,
    assignment_id: str,
    schema_name: str,
    **kwargs,
) -> dict:
    """Only TRANSIENT failures (all providers down) bubble out of _run — those get
    Celery retries with backoff. Permanent failures (bad file, malformed JSON, no
    provider configured) are recorded as FAILED inside _run and never retried."""
    from app.modules.m04_assignments.ai_providers import TransientAIError

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Which tenant every transaction in this task belongs to. Held for the whole run
    # and dropped at the end of it: a worker process is long-lived and serves every
    # tenant in turn, and a schema left set is a schema the next task inherits.
    with tenant_schema_scope(schema_name):
        try:
            return asyncio.run(_run(
                submission_id=UUID(submission_id),
                assignment_id=UUID(assignment_id),
                schema_name=schema_name,
            ))
        except TransientAIError as exc:
            from celery.exceptions import MaxRetriesExceededError
            try:
                # Exponential backoff: 30s, 60s, … capped at 5 min.
                raise self.retry(exc=exc, countdown=min(300, 30 * (2 ** self.request.retries)))
            except MaxRetriesExceededError:
                asyncio.run(_mark_failed(
                    UUID(submission_id), schema_name,
                    f"AI providers unavailable after {self.request.retries} retries: {exc!s:.300}",
                ))
                return {"status": "FAILED", "reason": "transient-exhausted"}


async def _extract(object_key: str) -> tuple[str, str | None]:
    """Reuse m06's extractor, off the event loop (it uses blocking boto3)."""
    from app.modules.m06_labs_evaluator.text_extractor import extract_text
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, extract_text, object_key)


def _ext_of(object_key: str) -> str:
    name = object_key.rsplit("/", 1)[-1]
    return ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""


async def _run(submission_id: UUID, assignment_id: UUID, schema_name: str) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m04_assignments.models import AIEvalStatus
    from app.modules.m04_assignments.repository import (
        AiEvaluationRepository,
        AssignmentRepository,
    )
    from app.modules.m04_assignments.ai_evaluator import evaluate
    from app.modules.m04_assignments.ai_providers import TransientAIError
    from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism

    started = time.monotonic()
    engine = _make_async_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            # No `SET search_path` here: the engine injects SET LOCAL at every BEGIN,
            # so the schema survives the commits below.

            # The API creates the PENDING row on submit (and on retry). Be
            # defensive: create it WITHOUT bumping retry_count if it's missing.
            if await AiEvaluationRepository.get_by_submission(submission_id, db=session) is None:
                from app.modules.m04_assignments.models import AssignmentEvaluation, AIEvalStatus as _S
                session.add(AssignmentEvaluation(submission_id=submission_id, status=_S.PENDING))
                await session.commit()

            sub = await _load_submission(session, submission_id)
            if sub is None:
                logger.warning("coursework AI: submission %s not found in %s", submission_id, schema_name)
                return {"status": "MISSING"}

            assignment = await AssignmentRepository.get_by_id(assignment_id, db=session)
            if assignment is None:
                await _fail(session, submission_id, "Assignment not found.")
                return {"status": "FAILED"}

            # --- 1. Extraction ---------------------------------------------------
            await AiEvaluationRepository.set_status(submission_id, AIEvalStatus.EXTRACTING, db=session)
            await session.commit()

            if sub.content_url:
                body, err = await _extract(sub.content_url)
                file_type = _ext_of(sub.content_url).lstrip(".") or None
                if err:
                    await _fail(session, submission_id, f"Extraction failed: {err}")
                    await _audit_failed(AuditService, AuditEventType, schema_name, submission_id, err)
                    return {"status": "FAILED", "reason": err}
            elif sub.content_text:
                body, file_type = sub.content_text, "text"
            else:
                await _fail(session, submission_id, "Submission has no file or text content.")
                return {"status": "FAILED"}

            word_count = len(body.split())
            await AiEvaluationRepository.save_extraction(
                submission_id, text_value=body, word_count=word_count,
                file_type=file_type, db=session,
            )
            await AiEvaluationRepository.set_status(submission_id, AIEvalStatus.EVALUATING, db=session)
            await session.commit()

            # --- 2. Context ------------------------------------------------------
            ctx = await _build_context(session, assignment, body, schema_name)

            # Optional: question-paper text enriches the prompt (best-effort).
            if assignment.question_paper_url:
                try:
                    qp, qperr = await _extract(assignment.question_paper_url)
                    if not qperr:
                        ctx.question_paper_text = qp
                except Exception:
                    logger.info("coursework AI: question paper extract skipped for %s", assignment_id)

            # --- 3. LLM evaluation ----------------------------------------------
            results = await evaluate(ctx)

            # --- 4. Internal similarity -----------------------------------------
            similarity_score, matches = None, None
            try:
                cohort = await AiEvaluationRepository.cohort_texts(assignment_id, submission_id, db=session)
                if cohort:
                    pr = compute_plagiarism(body, cohort, threshold=0.85)
                    similarity_score = pr.max_similarity
                    matches = pr.matches
            except Exception:
                logger.exception("coursework AI: similarity step failed for %s (non-fatal)", submission_id)

            # --- 5. Persist ------------------------------------------------------
            processing_ms = int((time.monotonic() - started) * 1000)
            await AiEvaluationRepository.save_results(
                submission_id, results=results,
                similarity_score=similarity_score, similarity_matches=matches,
                processing_ms=processing_ms, db=session,
            )
            await session.commit()

            await _audit_ok(AuditService, AuditEventType, schema_name, submission_id, results)
            logger.info("coursework AI completed for %s in %dms", submission_id, processing_ms)
            return {"status": "COMPLETED", "processing_ms": processing_ms}

    except TransientAIError:
        # Every provider failed transiently — DO NOT record FAILED here. Let it
        # propagate so the task wrapper can Celery-retry; status stays EVALUATING.
        raise
    except Exception as exc:  # noqa: BLE001 — permanent errors must not crash the queue
        logger.exception("coursework AI failed for %s", submission_id)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as s2:
                await _fail(s2, submission_id, f"{type(exc).__name__}: {exc!s:.300}")
        except Exception:
            logger.exception("coursework AI: could not record FAILED for %s", submission_id)
        return {"status": "FAILED"}
    finally:
        await engine.dispose()


async def _load_submission(session, submission_id: UUID):
    from sqlalchemy import select
    from app.modules.m04_assignments.models import AssignmentSubmission
    return (
        await session.execute(
            select(AssignmentSubmission).where(AssignmentSubmission.id == submission_id)
        )
    ).scalar_one_or_none()


async def _build_context(session, assignment, submission_text: str, schema_name: str):
    from sqlalchemy import text as _text
    from app.modules.m04_assignments.ai_evaluator import EvalContext

    course_title = course_code = department = program = None
    semester = None
    outcomes: list[dict] = []

    # Institution name from the public tenants registry (best-effort; the schema
    # name is the reliable fallback the AI can still use).
    institution = None
    try:
        inst = (
            await session.execute(
                _text("SELECT name FROM public.tenants WHERE schema_name = :s"),
                {"s": schema_name},
            )
        ).scalar_one_or_none()
        institution = inst
    except Exception:
        logger.info("coursework AI: institution name lookup skipped for %s", schema_name)

    if assignment.syllabus_id is not None:
        # course -> program gives Department + Program; never hardcoded.
        row = (
            await session.execute(
                _text(
                    "SELECT c.title, c.code, c.semester, p.title, p.department "
                    "FROM syllabi s JOIN courses c ON c.id = s.course_id "
                    "LEFT JOIN programs p ON p.id = c.program_id "
                    "WHERE s.id = :sid"
                ),
                {"sid": str(assignment.syllabus_id)},
            )
        ).one_or_none()
        if row:
            course_title, course_code, semester, program, department = (
                row[0], row[1], row[2], row[3], row[4]
            )

        co_rows = (
            await session.execute(
                _text(
                    "SELECT code, description, bloom_level FROM course_outcomes "
                    "WHERE syllabus_id = :sid ORDER BY display_order"
                ),
                {"sid": str(assignment.syllabus_id)},
            )
        ).all()
        outcomes = [
            {"co_code": r[0], "description": r[1], "bloom_level": r[2]} for r in co_rows
        ]

    return EvalContext(
        assignment_title=assignment.title,
        max_marks=float(assignment.max_marks),
        questions=assignment.questions or [],
        instructions=assignment.instructions,
        institution=institution,
        department=department,
        program=program,
        course_title=course_title,
        course_code=course_code,
        semester=semester,
        course_outcomes=outcomes,
        submission_text=submission_text,
    )


async def _mark_failed(submission_id: UUID, schema_name: str, message: str) -> None:
    """Record status=FAILED in a fresh session (used when Celery retries are
    exhausted). Best-effort — never raises. Runs inside the caller's
    tenant_schema_scope, so the engine scopes its transaction for us."""
    from sqlalchemy.ext.asyncio import AsyncSession
    engine = _make_async_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            await _fail(s, submission_id, message)
    except Exception:
        logger.exception("coursework AI: _mark_failed could not record for %s", submission_id)
    finally:
        await engine.dispose()


async def _fail(session, submission_id: UUID, message: str) -> None:
    from app.modules.m04_assignments.models import AIEvalStatus
    from app.modules.m04_assignments.repository import AiEvaluationRepository
    await AiEvaluationRepository.set_status(
        submission_id, AIEvalStatus.FAILED, db=session, error_log=message,
    )
    await session.commit()


async def _audit_ok(AuditService, AuditEventType, schema_name, submission_id, results):
    try:
        await AuditService.log(
            AuditEventType.COURSEWORK_AI_EVAL_COMPLETED,
            actor_user_id=None, actor_role="SYSTEM",
            tenant_id=None, schema_name=schema_name,
            target_entity="assignment_submission", target_id=str(submission_id),
            metadata={
                "model": results.get("ai_model"),
                "prompt_hash": results.get("prompt_hash"),
                "confidence": results.get("confidence_level"),
                "overall_suggested_marks": float(results.get("overall_suggested_marks") or 0),
            },
        )
    except Exception:
        logger.info("coursework AI: audit(completed) skipped for %s", submission_id)


async def _audit_failed(AuditService, AuditEventType, schema_name, submission_id, err):
    try:
        await AuditService.log(
            AuditEventType.COURSEWORK_AI_EVAL_FAILED,
            actor_user_id=None, actor_role="SYSTEM",
            tenant_id=None, schema_name=schema_name,
            target_entity="assignment_submission", target_id=str(submission_id),
            metadata={"error": str(err)[:300]},
        )
    except Exception:
        logger.info("coursework AI: audit(failed) skipped for %s", submission_id)
