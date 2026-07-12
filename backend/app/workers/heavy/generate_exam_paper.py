"""
Celery heavy-queue task: generate exam paper questions (M08).

Flow:
  1. Load ExamPaper from DB.
  2. Set status → GENERATING (explicit at task start; handles retries).
  3. Fetch syllabus units, course info, and course outcomes from M01/M02.
  4. Call question_generator.generate_questions() — Gemini/Groq/mock.
     Passes: section_config, course_outcomes, exam_workflow.
  5. Bulk-write ExamQuestion rows (now stores section_label, co_ids, choice_group).
  6. Compute CO coverage report and unit coverage report.
  7. Compute Bloom's compliance report (with co_coverage_ok + unit_coverage_ok flags).
  8. Write BloomsComplianceReport row.
  9. Update ExamPaper: actual_dist, ai_model, prompt_hash,
     co_coverage_report, unit_coverage_report, status → GENERATED.
 10. Commit. Audit EXAM_PAPER_GENERATION_COMPLETED.

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

            # 2. Set GENERATING at task start (explicit; handles retry scenarios)
            await ExamPaperRepository.set_status(
                paper_uuid, ExamPaperStatus.GENERATING.value, db=session
            )
            await session.commit()

            # 3. Fetch syllabus units, course info, and course outcomes from M01/M02
            units = await _fetch_syllabus_units(
                course_id=paper.course_id,
                units_included=list(paper.units_included or []),
                session=session,
            )
            course_info = await _fetch_course_info(
                course_id=paper.course_id,
                session=session,
            )
            course_outcomes = await _fetch_course_outcomes(
                course_id=paper.course_id,
                session=session,
            )

            # 4. Generate questions — passes section_config, COs, workflow
            bloom_targets   = dict(paper.requested_dist or {})
            question_format = dict(paper.question_format or {})
            section_config  = list(paper.section_config) if paper.section_config else None
            exam_workflow   = paper.exam_workflow or "BOARD_EXAM"

            questions_raw, ai_model, prompt_hash = await generate_questions(
                units=units,
                bloom_targets=bloom_targets,
                question_format=question_format,
                total_marks=paper.total_marks,
                special_instructions=paper.special_instructions,
                course_title=course_info.get("title", ""),
                course_code=course_info.get("code", ""),
                exam_type=paper.exam_type or "END_SEM",
                section_config=section_config,
                course_outcomes=course_outcomes,
                exam_workflow=exam_workflow,
            )

            if not questions_raw:
                raise ValueError("Question generator returned no questions.")

            # 5. Bulk-write ExamQuestion rows (section_label, co_ids, choice_group now stored)
            saved = await ExamQuestionRepository.bulk_create(
                questions_raw, exam_paper_id=paper_uuid, db=session
            )
            await session.commit()
            logger.info(
                "Saved %d questions for paper %s; sample set_memberships=%r",
                len(saved),
                paper_id,
                [q.get("set_membership") for q in questions_raw[:3]],
            )

            # 6. Compute CO and unit coverage reports
            co_coverage_report, co_coverage_ok = _compute_co_coverage(
                questions_raw, course_outcomes
            )
            unit_coverage_report, unit_coverage_ok = _compute_unit_coverage(
                questions_raw, list(paper.units_included or [])
            )
            logger.info(
                "Coverage: co_ok=%s unit_ok=%s co_items=%d unit_items=%d",
                co_coverage_ok, unit_coverage_ok,
                len(co_coverage_report), len(unit_coverage_report),
            )

            # 7. Compute Bloom's compliance
            actual_dist = compute_actual_distribution(questions_raw)
            report = check_compliance(
                requested=bloom_targets,
                actual=actual_dist,
                tolerance=float(settings.M08_BLOOM_COMPLIANCE_TOLERANCE),
            )

            # 8. Write BloomsComplianceReport (with coverage advisory flags)
            await BloomsRepository.upsert(
                paper_uuid,
                requested_dist=bloom_targets,
                actual_dist=actual_dist,
                compliance_ok=report.compliance_ok,
                violations=report.to_violations_list(),
                co_coverage_ok=co_coverage_ok,
                unit_coverage_ok=unit_coverage_ok,
                db=session,
            )

            # 9. Update ExamPaper → GENERATED with coverage reports
            await ExamPaperRepository.set_generation_result(
                paper_uuid,
                ai_model=ai_model,
                prompt_hash=prompt_hash,
                actual_dist=actual_dist,
                co_coverage_report=co_coverage_report,
                unit_coverage_report=unit_coverage_report,
                db=session,
            )
            await session.commit()

            # 10. Audit
            await AuditService.log(
                AuditEventType.EXAM_PAPER_GENERATION_COMPLETED,
                actor_user_id=None,
                actor_role="SYSTEM",
                tenant_id=None,
                schema_name=schema_name,
                target_entity="exam_paper",
                target_id=paper_id,
                metadata={
                    "question_count":   len(questions_raw),
                    "compliance_ok":    report.compliance_ok,
                    "violation_count":  len(report.violations),
                    "ai_model":         ai_model,
                    "co_coverage_ok":   co_coverage_ok,
                    "unit_coverage_ok": unit_coverage_ok,
                    "section_count":    len(section_config) if section_config else 0,
                },
            )

            logger.info(
                "Generation complete: paper=%s questions=%d compliance=%s co_ok=%s unit_ok=%s",
                paper_id, len(questions_raw), report.compliance_ok,
                co_coverage_ok, unit_coverage_ok,
            )

            return {
                "paper_id":         paper_id,
                "question_count":   len(questions_raw),
                "compliance_ok":    report.compliance_ok,
                "co_coverage_ok":   co_coverage_ok,
                "unit_coverage_ok": unit_coverage_ok,
                "ai_model":         ai_model,
            }

        except Exception as exc:
            failure_reason = f"{type(exc).__name__}: {exc}"
            logger.error(
                "Exam generation failed for paper %s: %s",
                paper_id, failure_reason, exc_info=True,
            )

            try:
                await session.rollback()
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

        # Get latest LOCKED or APPROVED (official) syllabus for this course
        result = await session.execute(
            select(Syllabus)
            .where(Syllabus.course_id == course_id)
            .where(Syllabus.status.in_(["LOCKED", "APPROVED"]))
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


async def _fetch_course_info(*, course_id, session) -> dict:
    """Fetch course title and code from M01 for richer question generation context."""
    try:
        from sqlalchemy import select
        from app.modules.m01_program_advisor.models import Course
        result = await session.execute(select(Course).where(Course.id == course_id))
        course = result.scalar_one_or_none()
        if course:
            return {"title": course.title or "", "code": course.code or ""}
    except Exception as exc:
        logger.warning("Failed to fetch course info for %s: %s", course_id, exc)
    return {"title": "", "code": ""}


async def _fetch_course_outcomes(*, course_id, session) -> list[dict]:
    """
    Fetch COs from the latest approved syllabus for this course.
    Returns list of {id, co_code, description} dicts for use in generation prompt.
    Falls back to empty list gracefully (CO context becomes optional).
    """
    try:
        from sqlalchemy import select
        from app.modules.m02_syllabus.models import CourseOutcome, Syllabus

        syl_result = await session.execute(
            select(Syllabus)
            .where(Syllabus.course_id == course_id)
            .where(Syllabus.status.in_(["LOCKED", "APPROVED"]))
            .order_by(Syllabus.version.desc())
            .limit(1)
        )
        syllabus = syl_result.scalar_one_or_none()
        if syllabus is None:
            logger.debug("No approved syllabus for course %s — skipping CO context.", course_id)
            return []

        co_result = await session.execute(
            select(CourseOutcome)
            .where(CourseOutcome.syllabus_id == syllabus.id)
            .order_by(CourseOutcome.display_order)
        )
        return [
            {
                "id":          str(co.id),
                "co_code":     co.code or "",
                "description": co.description or "",
            }
            for co in co_result.scalars().all()
        ]
    except Exception as exc:
        logger.warning("Failed to fetch COs for course %s: %s", course_id, exc)
        return []


def _compute_co_coverage(
    questions: list[dict],
    course_outcomes: list[dict],
) -> tuple[list[dict], bool]:
    """
    Compute per-CO coverage from generated questions.

    Returns:
        (co_coverage_report, co_coverage_ok)
        co_coverage_report: [{co_id, co_code, covered: bool, question_count: int}]
        co_coverage_ok: True when every CO has at least one question (advisory flag).
    """
    if not course_outcomes:
        return [], True  # No COs defined — trivially satisfied

    report: list[dict] = []
    all_covered = True
    for co in course_outcomes:
        co_id   = str(co.get("id") or "")
        co_code = co.get("co_code") or ""
        count   = sum(
            1 for q in questions
            if co_id and co_id in (q.get("co_ids") or [])
        )
        covered = count > 0
        if not covered:
            all_covered = False
        report.append({
            "co_id":          co_id,
            "co_code":        co_code,
            "covered":        covered,
            "question_count": count,
        })
    return report, all_covered


def _compute_unit_coverage(
    questions: list[dict],
    units_included: list[int],
) -> tuple[list[dict], bool]:
    """
    Compute per-unit coverage from generated questions.

    Returns:
        (unit_coverage_report, unit_coverage_ok)
        unit_coverage_report: [{unit_no: int, covered: bool, question_count: int}]
        unit_coverage_ok: True when every requested unit has at least one question.
    """
    if not units_included:
        return [], True

    report: list[dict] = []
    all_covered = True
    for unit_no in sorted(set(int(u) for u in units_included)):
        count   = sum(
            1 for q in questions
            if int(q.get("unit_number") or 0) == unit_no
        )
        covered = count > 0
        if not covered:
            all_covered = False
        report.append({
            "unit_no":        unit_no,
            "covered":        covered,
            "question_count": count,
        })
    return report, all_covered
