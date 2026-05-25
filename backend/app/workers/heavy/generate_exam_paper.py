"""
Celery heavy-queue task: generate exam paper questions (M08).

Flow:
  1. Load ExamPaper from DB.
  2. Set status → GENERATING.
  3. Fetch linked Syllabus units from M02 tables (SET search_path).
  4. Call question_generator.generate_questions() — Gemini/Groq/mock.
  5. Bulk-write ExamQuestion rows.
  6. Compute Bloom's compliance report.
  7. Write BloomsComplianceReport row.
  8. Update ExamPaper: actual_dist, ai_model, prompt_hash, status → GENERATED.
  9. Commit. Audit EXAM_PAPER_GENERATION_COMPLETED.

On failure:
  - Set status back to DRAFT (so faculty can retry).
  - Audit EXAM_PAPER_GENERATION_FAILED.
  - Re-raise so Celery marks task FAILED.
"""
import asyncio
import logging
import sys

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m08.generate_exam_paper")

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import settings
        _async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return _async_engine


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.generate_exam_paper",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def generate_exam_paper(
    *,
    job_id:      str,
    paper_id:    str,
    schema_name: str,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_generation(
            paper_id=paper_id,
            schema_name=schema_name,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_generation(*, paper_id: str, schema_name: str) -> dict:
    from uuid import UUID
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import settings
    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m08_exam_setter.blooms_analyser import (
        compute_actual_distribution,
        check_compliance,
    )
    from app.modules.m08_exam_setter.models import ExamPaperStatus
    from app.modules.m08_exam_setter.question_generator import generate_questions
    from app.modules.m08_exam_setter.repository import (
        BloomsRepository,
        ExamPaperRepository,
        ExamQuestionRepository,
    )

    engine = _get_async_engine()
    paper_uuid = UUID(paper_id)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text(f"SET search_path TO {schema_name}, public"))

        try:
            # 1. Load paper
            paper = await ExamPaperRepository.get_by_id(paper_uuid, db=session)
            if paper is None:
                raise ValueError(f"ExamPaper {paper_id} not found in schema {schema_name!r}.")

            # 2. Fetch syllabus units from M02
            units = await _fetch_syllabus_units(
                course_id=paper.course_id,
                units_included=list(paper.units_included or []),
                session=session,
            )

            # 3. Generate questions
            bloom_targets = dict(paper.requested_dist or {})
            question_format = dict(paper.question_format or {})

            questions_raw, ai_model, prompt_hash = await generate_questions(
                units=units,
                bloom_targets=bloom_targets,
                question_format=question_format,
                total_marks=paper.total_marks,
                special_instructions=paper.special_instructions,
            )

            if not questions_raw:
                raise ValueError("Question generator returned no questions.")

            # 4. Bulk-write ExamQuestion rows
            await ExamQuestionRepository.bulk_create(
                questions_raw, exam_paper_id=paper_uuid, db=session
            )
            await session.commit()

            # 5. Compute Bloom's compliance
            actual_dist = compute_actual_distribution(questions_raw)
            report = check_compliance(
                requested=bloom_targets,
                actual=actual_dist,
                tolerance=float(settings.M08_BLOOM_COMPLIANCE_TOLERANCE),
            )

            # 6. Write BloomsComplianceReport
            await BloomsRepository.upsert(
                paper_uuid,
                requested_dist=bloom_targets,
                actual_dist=actual_dist,
                compliance_ok=report.compliance_ok,
                violations=report.to_violations_list(),
                db=session,
            )

            # 7. Update ExamPaper → GENERATED
            await ExamPaperRepository.set_generation_result(
                paper_uuid,
                ai_model=ai_model,
                prompt_hash=prompt_hash,
                actual_dist=actual_dist,
                db=session,
            )
            await session.commit()

            # 8. Audit
            await AuditService.log(
                AuditEventType.EXAM_PAPER_GENERATION_COMPLETED,
                actor_user_id=None,
                actor_role="SYSTEM",
                tenant_id=None,
                schema_name=schema_name,
                target_entity="exam_paper",
                target_id=paper_id,
                metadata={
                    "question_count":  len(questions_raw),
                    "compliance_ok":   report.compliance_ok,
                    "violation_count": len(report.violations),
                    "ai_model":        ai_model,
                },
            )

            logger.info(
                "Generation complete: paper=%s questions=%d compliance=%s",
                paper_id, len(questions_raw), report.compliance_ok,
            )

            return {
                "paper_id":       paper_id,
                "question_count": len(questions_raw),
                "compliance_ok":  report.compliance_ok,
                "ai_model":       ai_model,
            }

        except Exception as exc:
            failure_reason = f"{type(exc).__name__}: {exc}"
            logger.error(
                "Exam generation failed for paper %s: %s",
                paper_id, failure_reason, exc_info=True,
            )

            # Roll back partial writes (e.g. partially inserted questions)
            # then mark the paper FAILED so the UI shows a clear error state.
            try:
                await session.rollback()
                # SET search_path is session-level in Postgres, survives rollback.
                await ExamPaperRepository.set_failed(
                    paper_uuid,
                    reason=failure_reason,
                    db=session,
                )
                await session.commit()
            except Exception as mark_exc:
                logger.error(
                    "Could not mark paper %s as FAILED: %s", paper_id, mark_exc
                )

            try:
                await AuditService.log(
                    AuditEventType.EXAM_PAPER_GENERATION_FAILED,
                    actor_user_id=None,
                    actor_role="SYSTEM",
                    tenant_id=None,
                    schema_name=schema_name,
                    target_entity="exam_paper",
                    target_id=paper_id,
                    metadata={"error": failure_reason},
                )
            except Exception:
                pass

            raise


async def _fetch_syllabus_units(
    *,
    course_id,
    units_included: list[int],
    session,
) -> list[dict]:
    """
    Fetch syllabus units from M02 tables (same tenant schema, already set in search_path).
    Returns a list of unit dicts compatible with question_generator.
    Falls back to stub units if no syllabus found (graceful degradation in dev/test).
    """
    try:
        from sqlalchemy import select, text as sa_text
        from app.modules.m02_syllabus.models import Syllabus

        # Get latest ADMIN_LOCKED or FACULTY_APPROVED syllabus for this course
        result = await session.execute(
            select(Syllabus)
            .where(Syllabus.course_id == course_id)
            .where(Syllabus.status.in_(["ADMIN_LOCKED", "FACULTY_APPROVED"]))
            .order_by(Syllabus.version.desc())
            .limit(1)
        )
        syllabus = result.scalar_one_or_none()

        if syllabus is None:
            logger.warning(
                "No approved syllabus found for course %s — using stub units.", course_id
            )
            return _stub_units(units_included)

        raw_units: list[dict] = syllabus.units or []

        # Filter to requested units; fall back to all if filter produces empty
        if units_included:
            filtered = [
                u for u in raw_units
                if int(u.get("unit_no") or u.get("unit_number") or 0) in units_included
            ]
            return filtered if filtered else raw_units

        return raw_units

    except Exception as exc:
        logger.warning("Failed to fetch syllabus units: %s — using stub units.", exc)
        return _stub_units(units_included)


def _stub_units(units_included: list[int]) -> list[dict]:
    """Fallback stub units for dev/test when no syllabus exists."""
    if not units_included:
        units_included = [1, 2]
    return [
        {
            "unit_no": n,
            "title":   f"Unit {n}",
            "topics":  ["Topic A", "Topic B"],
            "hours":   6,
        }
        for n in units_included
    ]
