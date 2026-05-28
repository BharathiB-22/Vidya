"""
Celery heavy-queue task: generate a syllabus draft for a course via Gemini AI.

Flow
----
  1. Load syllabus + course + program outcomes (tenant schema).
  2. Guard: FACULTY_APPROVED / ADMIN_LOCKED are immutable — reject immediately.
  3. Set status → AI_GENERATING (idempotent on retry if already AI_GENERATING).
  4. Call GeminiSyllabusProvider.generate_syllabus().
  5. Idempotent cleanup: delete existing COs (CASCADE removes CO-PO mappings) + units.
  6. Bulk-create new COs, CO-PO mappings (AI-suggested PO codes resolved to IDs).
  7. Bulk-create new units.
  8. Update syllabus: ai_model, prompt_hash, status → DRAFT.
  9. Commit, then dispatch reference_enrichment task.
 10. Audit: SYLLABUS_GENERATION_COMPLETED.

On failure: reset syllabus to DRAFT, audit SYLLABUS_GENERATION_FAILED, re-raise.
"""
import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m02.syllabus_generation")

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        from app.config import settings
        # NullPool: no connection caching between asyncio.run() calls.
        # Each task creates a fresh event loop; pooled asyncpg connections
        # attached to the previous (now-closed) loop would cause
        # "Future attached to a different loop" — NullPool prevents that.
        _async_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    return _async_engine


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.generate_syllabus",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def generate_syllabus(
    *,
    job_id: str,
    syllabus_id: str,
    tenant_id: str,
    schema_name: str,
    request_id: str | None = None,
    **kwargs,
) -> dict:
    return asyncio.run(
        _run_generation(
            syllabus_id=UUID(syllabus_id),
            tenant_id=UUID(tenant_id),
            schema_name=schema_name,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_generation(
    syllabus_id: UUID,
    tenant_id: UUID,
    schema_name: str,
) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m01_program_advisor.models import ProgramOutcome
    from app.modules.m01_program_advisor.repository import (
        CourseRepository,
        ProgramOutcomeRepository,
    )
    from app.modules.m02_syllabus.ai_provider import (
        POContext,
        SyllabusGenerationContext,
        get_syllabus_provider,
    )
    from app.modules.m02_syllabus.models import SyllabusStatus
    from app.modules.m02_syllabus.repository import (
        COPOMappingRepository,
        CourseOutcomeRepository,
        SyllabusRepository,
        SyllabusUnitRepository,
    )

    engine = _get_async_engine()

    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await session.execute(text(f"SET search_path TO {schema_name}, public"))

            # ------------------------------------------------------------------
            # Load syllabus
            # ------------------------------------------------------------------
            syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=session)
            if syllabus is None:
                raise ValueError(
                    f"Syllabus {syllabus_id} not found in schema {schema_name!r}."
                )

            # Guard: immutable states must never be regenerated
            if syllabus.status in (SyllabusStatus.PENDING_REVIEW, SyllabusStatus.DEAN_APPROVED, SyllabusStatus.DEAN_LOCKED):
                raise ValueError(
                    f"Syllabus {syllabus_id} is {syllabus.status.value}; "
                    "AI generation is not permitted on immutable syllabi."
                )

            # ------------------------------------------------------------------
            # Advance to AI_GENERATING (idempotent: already AI_GENERATING on retry)
            # ------------------------------------------------------------------
            if syllabus.status != SyllabusStatus.AI_GENERATING:
                await SyllabusRepository.update_status(
                    syllabus_id, SyllabusStatus.AI_GENERATING, db=session
                )
                await session.flush()

            # ------------------------------------------------------------------
            # Load course (M01 table — same tenant schema)
            # ------------------------------------------------------------------
            course = await CourseRepository.get_by_id(syllabus.course_id, db=session)
            if course is None:
                raise ValueError(
                    f"Course {syllabus.course_id} not found for syllabus {syllabus_id}."
                )

            # ------------------------------------------------------------------
            # Load program outcomes for CO-PO mapping suggestions
            # ------------------------------------------------------------------
            pos = await ProgramOutcomeRepository.list_by_program(course.program_id, db=session)
            po_contexts = [
                POContext(id=str(po.id), code=po.code, description=po.description)
                for po in pos
            ]
            po_code_to_id: dict[str, UUID] = {po.code: po.id for po in pos}

            # ------------------------------------------------------------------
            # Build generation context and call Gemini
            # ------------------------------------------------------------------
            ctx = SyllabusGenerationContext(
                course_id=str(syllabus.course_id),
                course_code=course.code,
                course_title=course.title,
                course_credits=course.credits,
                program_outcomes=po_contexts,
                custom_instructions=syllabus.custom_instructions,
            )

            provider = get_syllabus_provider()
            result = await provider.generate_syllabus(ctx)

            # ------------------------------------------------------------------
            # Idempotent cleanup: remove all existing COs (CASCADE deletes
            # co_po_mappings) and units before re-creating from AI output.
            # Confirmed references are preserved; only unconfirmed ones are
            # cleared during reference_enrichment.
            # ------------------------------------------------------------------
            deleted_cos   = await CourseOutcomeRepository.delete_all(syllabus_id, db=session)
            deleted_units = await SyllabusUnitRepository.delete_all(syllabus_id, db=session)
            if deleted_cos or deleted_units:
                logger.info(
                    "m02.generate: cleared %d COs, %d units (syllabus=%s)",
                    deleted_cos, deleted_units, syllabus_id,
                )

            # ------------------------------------------------------------------
            # Bulk create Course Outcomes
            # ------------------------------------------------------------------
            new_cos = await CourseOutcomeRepository.bulk_create(
                syllabus_id,
                result.outcomes,
                db=session,
            )
            logger.info(
                "m02.generate: created %d COs (syllabus=%s)",
                len(new_cos), syllabus_id,
            )

            # ------------------------------------------------------------------
            # Create CO-PO mappings for AI-suggested codes that exist in the DB.
            # Unknown PO codes are silently skipped (validated at CO creation;
            # service layer filters them; faculty edits mappings post-approval).
            # ------------------------------------------------------------------
            mapping_items = []
            co_code_to_id = {co.code: co.id for co in new_cos}
            for ai_co, db_co in zip(result.outcomes, new_cos):
                for po_code in ai_co.get("suggested_po_codes", []):
                    po_id = po_code_to_id.get(po_code)
                    if po_id is not None:
                        mapping_items.append({
                            "co_id": db_co.id,
                            "po_id": po_id,
                        })

            if mapping_items:
                await COPOMappingRepository.bulk_create(mapping_items, db=session)
                logger.info(
                    "m02.generate: created %d CO-PO mappings (syllabus=%s)",
                    len(mapping_items), syllabus_id,
                )

            # ------------------------------------------------------------------
            # Bulk create Units
            # ------------------------------------------------------------------
            new_units = await SyllabusUnitRepository.bulk_create(
                syllabus_id,
                result.units,
                db=session,
            )
            logger.info(
                "m02.generate: created %d units (syllabus=%s)",
                len(new_units), syllabus_id,
            )

            # ------------------------------------------------------------------
            # Update syllabus: record AI metadata, set status back to DRAFT
            # ------------------------------------------------------------------
            await SyllabusRepository.update(
                syllabus_id,
                {
                    "ai_model":   result.model_used,
                    "prompt_hash": result.prompt_hash,
                    "status":     SyllabusStatus.DRAFT,
                    "updated_at": datetime.now(timezone.utc),
                },
                db=session,
            )

            await session.commit()

        # ------------------------------------------------------------------
        # Dispatch reference enrichment (fire-and-forget after DB commit)
        # ------------------------------------------------------------------
        _dispatch_reference_enrichment(
            syllabus_id=str(syllabus_id),
            tenant_id=str(tenant_id),
            schema_name=schema_name,
            reference_queries=result.reference_queries,
        )

        # ------------------------------------------------------------------
        # Audit: SYLLABUS_GENERATION_COMPLETED
        # ------------------------------------------------------------------
        await AuditService.log(
            AuditEventType.SYLLABUS_GENERATION_COMPLETED,
            actor_role="SYSTEM",
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="Syllabus",
            target_id=str(syllabus_id),
            metadata={
                "cos_created":      len(new_cos),
                "mappings_created": len(mapping_items),
                "units_created":    len(new_units),
                "model_used":       result.model_used,
                "prompt_hash":      result.prompt_hash[:16],
            },
        )

        logger.info(
            "m02.generate: complete (syllabus=%s cos=%d units=%d)",
            syllabus_id, len(new_cos), len(new_units),
        )

        return {
            "syllabus_id":      str(syllabus_id),
            "cos_created":      len(new_cos),
            "mappings_created": len(mapping_items),
            "units_created":    len(new_units),
            "model_used":       result.model_used,
        }

    except Exception as exc:
        # Reset syllabus to DRAFT so faculty can retry.
        # Best-effort: swallow any nested DB failures.
        try:
            async with AsyncSession(engine, expire_on_commit=False) as reset_session:
                await reset_session.execute(
                    text(f"SET search_path TO {schema_name}, public")
                )
                await SyllabusRepository.update_status(
                    syllabus_id, SyllabusStatus.DRAFT, db=reset_session
                )
                await reset_session.commit()
        except Exception:
            logger.exception(
                "m02.generate: failed to reset syllabus %s to DRAFT after error",
                syllabus_id,
            )

        try:
            await AuditService.log(
                AuditEventType.SYLLABUS_GENERATION_FAILED,
                actor_role="SYSTEM",
                tenant_id=tenant_id,
                schema_name=schema_name,
                target_entity="Syllabus",
                target_id=str(syllabus_id),
                metadata={"error": str(exc)[:500]},
            )
        except Exception:
            logger.exception("m02.generate: failed to log SYLLABUS_GENERATION_FAILED audit")

        raise


# ---------------------------------------------------------------------------
# Helper: dispatch reference_enrichment (deferred import to avoid circulars)
# ---------------------------------------------------------------------------

def _dispatch_reference_enrichment(
    syllabus_id: str,
    tenant_id: str,
    schema_name: str,
    reference_queries: list[dict],
) -> None:
    try:
        from app.workers.heavy.reference_enrichment import enrich_references  # noqa: PLC0415

        enrich_references.delay(
            job_id=None,        # fire-and-forget; no task_jobs row needed
            syllabus_id=syllabus_id,
            tenant_id=tenant_id,
            schema_name=schema_name,
            reference_queries=reference_queries,
        )
        logger.info(
            "m02.generate: reference_enrichment dispatched (syllabus=%s queries=%d)",
            syllabus_id, len(reference_queries),
        )
    except Exception:
        # Reference enrichment failure must never fail the parent task.
        logger.exception(
            "m02.generate: failed to dispatch reference_enrichment (syllabus=%s)",
            syllabus_id,
        )
