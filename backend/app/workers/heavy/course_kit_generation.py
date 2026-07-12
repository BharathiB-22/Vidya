"""
Celery heavy-queue task: generate a course kit for one syllabus unit via AI provider.

Flow
----
  1. Load course kit (CourseKitRepository).
  2. Guard: PUBLISHED/ARCHIVED kits are immutable — reject immediately.
  3. Load syllabus — must be FACULTY_APPROVED or ADMIN_LOCKED.
  4. Set status → AI_GENERATING (idempotent if already AI_GENERATING on retry).
  5. Load course (M01) for course_code + course_title.
  6. Load approved COs (M02) for CO mapping context.
  7. Load syllabus unit (M02) for unit_title + topic list.
  8. Build KitGenerationContext and call get_kit_provider().generate_kit().
  9. Idempotent cleanup: delete any pre-existing slides, assignments.
 10. Bulk create slides, assignments from AI result.
 11. Update kit: ai_model, prompt_hash, teaching_plan, lesson_plans, resources, status → DRAFT.
 12. Commit, then audit COURSE_KIT_GENERATION_COMPLETED.

On failure: reset kit to DRAFT, audit COURSE_KIT_GENERATION_FAILED, re-raise.
"""
import asyncio
import logging
import sys
from datetime import datetime, timezone
from uuid import UUID

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m03.course_kit_generation")

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        from app.config import settings
        # NullPool: no connection caching between asyncio.run() calls.
        # On Windows --pool=solo each task runs in a fresh event loop; pooled
        # asyncpg connections attached to the previous (closed) loop raise
        # "Future attached to a different loop". NullPool prevents this.
        _async_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    return _async_engine


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.generate_course_kit",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def generate_course_kit(
    *,
    job_id: str,
    kit_id: str,
    tenant_id: str,
    schema_name: str,
    request_id: str | None = None,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_generation(
            kit_id=UUID(kit_id),
            tenant_id=UUID(tenant_id),
            schema_name=schema_name,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_generation(
    kit_id: UUID,
    tenant_id: UUID,
    schema_name: str,
) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import settings
    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m01_program_advisor.repository import CourseRepository
    from app.modules.m02_syllabus.models import SyllabusStatus
    from app.modules.m02_syllabus.repository import (
        CourseOutcomeRepository,
        SyllabusRepository,
        SyllabusUnitRepository,
    )
    from app.modules.m03_course_kit.ai_provider import (
        COContext,
        KitGenerationContext,
        get_kit_provider,
    )
    from app.modules.m03_course_kit.models import CourseKitStatus
    from app.modules.m03_course_kit.repository import (
        AssignmentRepository,
        CourseKitRepository,
        SlideRepository,
    )

    engine = _get_async_engine()

    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await session.execute(text(f"SET search_path TO {schema_name}, public"))

            # ------------------------------------------------------------------
            # 1. Load course kit
            # ------------------------------------------------------------------
            kit = await CourseKitRepository.get_by_id(kit_id, db=session)
            if kit is None:
                raise ValueError(
                    f"CourseKit {kit_id} not found in schema {schema_name!r}."
                )

            # ------------------------------------------------------------------
            # 2. Guard: PUBLISHED / ARCHIVED are immutable
            # ------------------------------------------------------------------
            if kit.status in (CourseKitStatus.PUBLISHED, CourseKitStatus.ARCHIVED):
                raise ValueError(
                    f"CourseKit {kit_id} is {kit.status.value}; "
                    "AI generation is not permitted on PUBLISHED or ARCHIVED kits."
                )

            # ------------------------------------------------------------------
            # 3. Load syllabus — must be at an approved state
            # ------------------------------------------------------------------
            syllabus = await SyllabusRepository.get_by_id(kit.syllabus_id, db=session)
            if syllabus is None:
                raise ValueError(
                    f"Syllabus {kit.syllabus_id} not found for kit {kit_id}."
                )
            if syllabus.status not in (
                SyllabusStatus.APPROVED,
                SyllabusStatus.LOCKED,
            ):
                raise ValueError(
                    f"Syllabus {kit.syllabus_id} is {syllabus.status.value}; "
                    "course kit generation requires a Dean-approved or locked syllabus."
                )

            # ------------------------------------------------------------------
            # 4. Advance to AI_GENERATING (idempotent: already set on retry)
            # ------------------------------------------------------------------
            if kit.status != CourseKitStatus.AI_GENERATING:
                await CourseKitRepository.update_status(
                    kit_id, CourseKitStatus.AI_GENERATING, db=session
                )
                await session.flush()

            # ------------------------------------------------------------------
            # 5. Load course (M01)
            # ------------------------------------------------------------------
            course = await CourseRepository.get_by_id(syllabus.course_id, db=session)
            if course is None:
                raise ValueError(
                    f"Course {syllabus.course_id} not found "
                    f"for syllabus {kit.syllabus_id}."
                )

            # ------------------------------------------------------------------
            # 6. Load approved COs (M02)
            # ------------------------------------------------------------------
            cos = await CourseOutcomeRepository.list_by_syllabus(
                kit.syllabus_id, db=session
            )
            co_contexts = [
                COContext(
                    code=co.code,
                    description=co.description,
                    bloom_level=co.bloom_level.value if hasattr(co.bloom_level, "value") else str(co.bloom_level),
                )
                for co in cos
            ]

            # ------------------------------------------------------------------
            # 7. Load syllabus unit for this kit's unit_number (M02)
            # ------------------------------------------------------------------
            unit = await SyllabusUnitRepository.get_by_number(
                kit.syllabus_id, kit.unit_number, db=session
            )
            if unit is None:
                raise ValueError(
                    f"SyllabusUnit {kit.unit_number} not found "
                    f"in syllabus {kit.syllabus_id}."
                )

            # topics JSONB is a list of dicts like {"title": "...", "hours_estimate": ...}
            unit_topics = [
                t["title"] if isinstance(t, dict) else str(t)
                for t in (unit.topics or [])
            ]

            # ------------------------------------------------------------------
            # 8. Build generation context and call AI provider
            # ------------------------------------------------------------------
            ctx = KitGenerationContext(
                kit_id=str(kit_id),
                unit_number=kit.unit_number,
                unit_title=unit.title,
                unit_topics=unit_topics,
                course_code=course.code,
                course_title=course.title,
                complexity_level=(
                    kit.complexity_level.value
                    if hasattr(kit.complexity_level, "value")
                    else str(kit.complexity_level)
                ),
                tone=kit.tone,
                custom_instructions=kit.custom_instructions,
                cos=co_contexts,
                min_slides=settings.M03_MIN_SLIDES_PER_UNIT,
            )

            provider = get_kit_provider()
            result = await provider.generate_kit(ctx)

            # ------------------------------------------------------------------
            # 9. Idempotent cleanup: remove any existing content rows
            #    (safe on retry — CASCADE deletes ensure no orphans).
            # ------------------------------------------------------------------
            del_slides      = await SlideRepository.delete_all(kit_id, db=session)
            del_assignments = await AssignmentRepository.delete_all(kit_id, db=session)
            if del_slides or del_assignments:
                logger.info(
                    "m03.generate: cleared %d slides, %d assignments (kit=%s)",
                    del_slides, del_assignments, kit_id,
                )

            # ------------------------------------------------------------------
            # 10. Bulk create slides
            # ------------------------------------------------------------------
            slides_data = [
                {
                    "slide_number":  s.slide_number,
                    "title":         s.title,
                    "content":       s.content,
                    "speaker_notes": s.speaker_notes,
                    "bloom_level":   s.bloom_level,
                    "co_reference":  s.co_reference,
                }
                for s in result.slides
            ]
            new_slides = await SlideRepository.bulk_create(kit_id, slides_data, db=session)
            logger.info(
                "m03.generate: created %d slides (kit=%s)", len(new_slides), kit_id
            )

            # ------------------------------------------------------------------
            # 12. Bulk create assignments
            # ------------------------------------------------------------------
            assignments_data = [
                {
                    "assignment_number":     a.assignment_number,
                    "title":                 a.title,
                    "assignment_type":       a.assignment_type,
                    "question_text":         a.question_text,
                    "complexity_level":      a.complexity_level,
                    "current_events_toggle": a.current_events_toggle,
                    "model_answer":          a.model_answer,
                    "rubric":                a.rubric,
                    "bloom_level":           a.bloom_level,
                    "co_reference":          a.co_reference,
                }
                for a in result.assignments
            ]
            new_assignments = await AssignmentRepository.bulk_create(
                kit_id, assignments_data, db=session
            )
            logger.info(
                "m03.generate: created %d assignments (kit=%s)",
                len(new_assignments), kit_id,
            )

            # ------------------------------------------------------------------
            # 13. Update kit: AI metadata + JSONB plan fields + status → DRAFT
            # ------------------------------------------------------------------
            await CourseKitRepository.update(
                kit_id,
                {
                    "ai_model":     result.model_used,
                    "prompt_hash":  result.prompt_hash,
                    "teaching_plan": result.teaching_plan,
                    "lesson_plans":  result.lesson_plans,
                    "resources":     result.resources,
                    "status":        CourseKitStatus.DRAFT,
                    "updated_at":    datetime.now(timezone.utc),
                },
                db=session,
            )

            await session.commit()

        # ------------------------------------------------------------------
        # 14. Audit: COURSE_KIT_GENERATION_COMPLETED  (outside session)
        # ------------------------------------------------------------------
        await AuditService.log(
            AuditEventType.COURSE_KIT_GENERATION_COMPLETED,
            actor_role="SYSTEM",
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="CourseKit",
            target_id=str(kit_id),
            metadata={
                "slides_created":      len(new_slides),
                "assignments_created": len(new_assignments),
                "model_used":          result.model_used,
                "prompt_hash":         result.prompt_hash[:16],
                "unit_number":         ctx.unit_number,
            },
        )

        logger.info(
            "m03.generate: complete (kit=%s slides=%d assignments=%d)",
            kit_id, len(new_slides), len(new_assignments),
        )

        return {
            "kit_id":              str(kit_id),
            "slides_created":      len(new_slides),
            "assignments_created": len(new_assignments),
            "model_used":          result.model_used,
            "provider":            result.provider_name,
        }

    except Exception as exc:
        # Best-effort: reset kit to DRAFT so faculty can retry.
        try:
            async with AsyncSession(engine, expire_on_commit=False) as reset_session:
                await reset_session.execute(
                    text(f"SET search_path TO {schema_name}, public")
                )
                await CourseKitRepository.reset_to_draft(kit_id, db=reset_session)
                await reset_session.commit()
        except Exception:
            logger.exception(
                "m03.generate: failed to reset kit %s to DRAFT after error", kit_id
            )

        try:
            await AuditService.log(
                AuditEventType.COURSE_KIT_GENERATION_FAILED,
                actor_role="SYSTEM",
                tenant_id=tenant_id,
                schema_name=schema_name,
                target_entity="CourseKit",
                target_id=str(kit_id),
                metadata={"error": str(exc)[:500]},
            )
        except Exception:
            logger.exception(
                "m03.generate: failed to log COURSE_KIT_GENERATION_FAILED audit"
            )

        raise
