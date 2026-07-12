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
import sys
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
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
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
        normalize_course_type,
    )
    from app.modules.m02_syllabus.schemas import parse_document
    from app.modules.m02_syllabus.formatting import (
        derive_category,
        derive_contact_hours,
        format_ltp,
        has_practical,
    )
    from app.modules.m02_syllabus.models import MappingStrength, SyllabusStatus
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
            if syllabus.status in (SyllabusStatus.APPROVED, SyllabusStatus.LOCKED):
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
            # The Course Information header of the official syllabus, derived from
            # the course rather than stored (see m02/formatting.py). The AI writes
            # TO this header: units are paced against the contact hours, and a
            # course with no practical hours gets no Practical Components.
            # The course's TYPE decides WHICH document gets written — a theory
            # syllabus, a lab manual, internship guidelines, a project handbook.
            # Generating five units of lectures for an internship is not a cosmetic
            # error; it is a regulation promising teaching that will never happen.
            course_type = normalize_course_type(course.course_type)

            ctx = SyllabusGenerationContext(
                course_id=str(syllabus.course_id),
                course_code=course.code,
                course_title=course.title,
                course_credits=course.credits,
                program_outcomes=po_contexts,
                custom_instructions=syllabus.custom_instructions,
                ltp=format_ltp(course),
                contact_hours=derive_contact_hours(course),
                category=derive_category(course),
                has_practical=has_practical(course),
                course_type=course_type,
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
                strengths = ai_co.get("po_mapping_strengths", {})
                for po_code in ai_co.get("suggested_po_codes", []):
                    po_id = po_code_to_id.get(po_code)
                    if po_id is not None:
                        try:
                            strength = MappingStrength(strengths.get(po_code, "MEDIUM"))
                        except ValueError:
                            strength = MappingStrength.MEDIUM
                        mapping_items.append({
                            "co_id": db_co.id,
                            "po_id": po_id,
                            "mapping_strength": strength,
                        })

            if mapping_items:
                await COPOMappingRepository.bulk_create(mapping_items, db=session)
                logger.info(
                    "m02.generate: created %d CO-PO mappings (syllabus=%s)",
                    len(mapping_items), syllabus_id,
                )

            # ------------------------------------------------------------------
            # Bulk create Units — THEORY only.
            #
            # result.units is empty for every other type, and that is the point: a
            # laboratory has experiments, an internship has weekly activities, and
            # neither has a Unit III. Their content lives in `document` instead.
            # ------------------------------------------------------------------
            new_units = await SyllabusUnitRepository.bulk_create(
                syllabus_id,
                result.units,
                db=session,
            ) if result.units else []

            if new_units:
                logger.info(
                    "m02.generate: created %d units (syllabus=%s)",
                    len(new_units), syllabus_id,
                )

            # ------------------------------------------------------------------
            # Update syllabus: the document, official-format prose, AI metadata,
            # back to DRAFT.
            #
            # DRAFT, never APPROVED: AI advises, humans decide. A generated
            # document lands in the Board's queue for review and sign-off — it is
            # never self-approving, and the curriculum's approve gate will not
            # pass until a Board member has looked at it.
            # ------------------------------------------------------------------
            await SyllabusRepository.update(
                syllabus_id,
                {
                    # doc_type is stamped from the course at GENERATION time and is
                    # not read back through to courses.course_type afterwards — see
                    # m02.models.Syllabus.doc_type.
                    "doc_type":             result.doc_type,
                    # Re-validated against its own schema on the way in. The provider
                    # already shaped it, but the DB column is a free-form JSONB and
                    # this is the last place a malformed body can be stopped before
                    # it becomes an approved university document.
                    "document":             parse_document(result.doc_type, result.document),
                    "objectives":           result.objectives,
                    "practical_components": result.practical_components,
                    "internal_assessment":  result.internal_assessment,
                    "ai_model":    result.model_used,
                    "prompt_hash": result.prompt_hash,
                    "status":      SyllabusStatus.DRAFT,
                    "updated_at":  datetime.now(timezone.utc),
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
                "doc_type":         result.doc_type,
                "cos_created":      len(new_cos),
                "mappings_created": len(mapping_items),
                "units_created":    len(new_units),
                "document_sections": sorted(result.document.keys()),
                "model_used":       result.model_used,
                "prompt_hash":      result.prompt_hash[:16],
            },
        )

        logger.info(
            "m02.generate: complete (syllabus=%s type=%s cos=%d units=%d doc_sections=%d)",
            syllabus_id, result.doc_type, len(new_cos), len(new_units),
            len(result.document),
        )

        return {
            "syllabus_id":      str(syllabus_id),
            "doc_type":         result.doc_type,
            "cos_created":      len(new_cos),
            "mappings_created": len(mapping_items),
            "units_created":    len(new_units),
            "model_used":       result.model_used,
            "provider":         result.provider_name,
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
    replace_types: list[str] | None = None,
) -> None:
    """`replace_types` scopes which references enrichment is allowed to replace.

    A BOOKS regeneration passes ["TEXTBOOK"] so the Reference Books and Web
    Resources survive it; a full generation passes None and replaces the lot.
    """
    try:
        from app.workers.heavy.reference_enrichment import enrich_references  # noqa: PLC0415

        enrich_references.delay(
            job_id=None,        # fire-and-forget; no task_jobs row needed
            syllabus_id=syllabus_id,
            tenant_id=tenant_id,
            schema_name=schema_name,
            reference_queries=reference_queries,
            replace_types=replace_types,
        )
        logger.info(
            "m02.generate: reference_enrichment dispatched (syllabus=%s queries=%d scope=%s)",
            syllabus_id, len(reference_queries), replace_types or "ALL",
        )
    except Exception:
        # Reference enrichment failure must never fail the parent task.
        logger.exception(
            "m02.generate: failed to dispatch reference_enrichment (syllabus=%s)",
            syllabus_id,
        )


# ---------------------------------------------------------------------------
# Section regeneration — rewrite ONE part of an existing syllabus
#
# The Board should never have to regenerate a whole syllabus because one unit came
# out weak. Five units, five COs, a reference list and two prose sections is a lot
# of work to throw away — and by the time anyone notices the flaw, much of the rest
# will have been hand-edited.
#
# So this task rewrites exactly the slice it is asked for, and touches nothing else.
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.regenerate_syllabus_section",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def regenerate_syllabus_section(
    *,
    job_id: str,
    syllabus_id: str,
    tenant_id: str,
    schema_name: str,
    section: str,
    unit_id: str | None = None,
    guidance: str | None = None,
    request_id: str | None = None,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_section_regeneration(
            syllabus_id=UUID(syllabus_id),
            tenant_id=UUID(tenant_id),
            schema_name=schema_name,
            section=section,
            unit_id=UUID(unit_id) if unit_id else None,
            guidance=guidance,
        )
    )


async def _run_section_regeneration(
    syllabus_id: UUID,
    tenant_id: UUID,
    schema_name: str,
    section: str,
    unit_id: UUID | None,
    guidance: str | None,
) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m01_program_advisor.repository import (
        CourseRepository,
        ProgramOutcomeRepository,
    )
    from app.modules.m02_syllabus.ai_provider import (
        SECTION_BOOKS,
        SECTION_DOCUMENT,
        SECTION_OBJECTIVES,
        SECTION_OUTCOMES,
        SECTION_PRACTICALS,
        SECTION_REFERENCES,
        SECTION_UNIT,
        POContext,
        SyllabusGenerationContext,
        get_syllabus_provider,
        normalize_course_type,
    )
    from app.modules.m02_syllabus.formatting import (
        derive_category,
        derive_contact_hours,
        format_ltp,
        has_practical,
    )
    from app.modules.m02_syllabus.models import MappingStrength, SyllabusStatus
    from app.modules.m02_syllabus.repository import (
        COPOMappingRepository,
        CourseOutcomeRepository,
        SyllabusRepository,
        SyllabusUnitRepository,
    )
    from app.modules.m02_syllabus.schemas import parse_document

    engine = _get_async_engine()

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text(f"SET search_path TO {schema_name}, public"))

        syllabus = await SyllabusRepository.get_detail(syllabus_id, db=session)
        if syllabus is None:
            raise ValueError(f"Syllabus {syllabus_id} not found in {schema_name!r}.")
        if syllabus.status == SyllabusStatus.LOCKED:
            raise ValueError(
                f"Syllabus {syllabus_id} is LOCKED — its curriculum is approved, and "
                "nothing inside an approved curriculum may be regenerated."
            )

        course = await CourseRepository.get_by_id(syllabus.course_id, db=session)
        if course is None:
            raise ValueError(f"Course {syllabus.course_id} not found.")

        pos = await ProgramOutcomeRepository.list_by_program(course.program_id, db=session)
        ctx = SyllabusGenerationContext(
            course_id=str(syllabus.course_id),
            course_code=course.code,
            course_title=course.title,
            course_credits=course.credits,
            program_outcomes=[
                POContext(id=str(p.id), code=p.code, description=p.description) for p in pos
            ],
            custom_instructions=syllabus.custom_instructions,
            ltp=format_ltp(course),
            contact_hours=derive_contact_hours(course),
            category=derive_category(course),
            has_practical=has_practical(course),
            # Regenerate the document this course ACTUALLY has. The syllabus row's
            # own doc_type, not the course's current type: if a Dean reclassified
            # the course after the Board approved a lab manual, this row is still a
            # lab manual, and regenerating one of its sections must not quietly turn
            # it into a theory syllabus.
            course_type=normalize_course_type(syllabus.doc_type or course.course_type),
        )

        call_kwargs: dict = {"guidance": guidance}
        if section == SECTION_UNIT:
            target = next((u for u in syllabus.units if u.id == unit_id), None)
            if target is None:
                raise ValueError(f"Unit {unit_id} does not belong to syllabus {syllabus_id}.")
            call_kwargs.update(
                unit_number=target.unit_number,
                unit_title=target.title,
                # Tell the model what the OTHER units already teach, so the rewrite
                # fills its own place instead of drifting into theirs. A unit
                # regenerated in isolation is how you end up with two of them
                # teaching cache memory.
                sibling_units=[
                    f"Unit {u.unit_number}: {u.title}"
                    for u in sorted(syllabus.units, key=lambda x: x.unit_number)
                    if u.id != unit_id
                ],
            )

        provider = get_syllabus_provider()
        result = await provider.generate_section(ctx, section, **call_kwargs)

        changed: dict = {}

        if section == SECTION_UNIT:
            await SyllabusUnitRepository.update(
                unit_id,
                {
                    "title":       result.unit["title"],
                    "content":     result.unit.get("content"),
                    "topics":      result.unit.get("topics", []),
                    "total_hours": result.unit["total_hours"],
                    "pedagogy":    result.unit.get("pedagogy"),
                    "updated_at":  datetime.now(timezone.utc),
                },
                db=session,
            )
            changed = {"unit_id": str(unit_id), "topics": len(result.unit.get("topics", []))}

        elif section == SECTION_OBJECTIVES:
            await SyllabusRepository.update(
                syllabus_id,
                {"objectives": result.objectives, "updated_at": datetime.now(timezone.utc)},
                db=session,
            )
            changed = {"objectives": len(result.objectives or [])}

        elif section == SECTION_OUTCOMES:
            # COs are replaced wholesale. The CO-PO matrix hangs off them, and half a
            # matrix mapped against outcomes that no longer exist is incoherent.
            await CourseOutcomeRepository.delete_all(syllabus_id, db=session)
            new_cos = await CourseOutcomeRepository.bulk_create(
                syllabus_id, result.outcomes, db=session,
            )
            po_by_code = {p.code: p.id for p in pos}
            mappings = []
            for ai_co, db_co in zip(result.outcomes, new_cos):
                strengths = ai_co.get("po_mapping_strengths", {})
                for code in ai_co.get("suggested_po_codes", []):
                    po_id = po_by_code.get(code)
                    if po_id is None:
                        continue
                    try:
                        strength = MappingStrength(strengths.get(code, "MEDIUM"))
                    except ValueError:
                        strength = MappingStrength.MEDIUM
                    mappings.append(
                        {"co_id": db_co.id, "po_id": po_id, "mapping_strength": strength}
                    )
            if mappings:
                await COPOMappingRepository.bulk_create(mappings, db=session)
            changed = {"outcomes": len(new_cos), "mappings": len(mappings)}

        elif section in (SECTION_REFERENCES, SECTION_BOOKS):
            # The AI only ever produces SEARCH QUERIES — it never invents
            # bibliographic detail. Real metadata is fetched from CrossRef and
            # OpenLibrary, so these sections are regenerated by re-running
            # enrichment rather than by writing reference rows here.
            changed = {"reference_queries": len(result.reference_queries or [])}

        elif section == SECTION_PRACTICALS:
            await SyllabusRepository.update(
                syllabus_id,
                {
                    "practical_components": result.practical_components or [],
                    "updated_at": datetime.now(timezone.utc),
                },
                db=session,
            )
            changed = {"practical_components": len(result.practical_components or [])}

        elif section == SECTION_DOCUMENT:
            # The non-theory equivalent of regenerating every unit at once: the whole
            # type-specific body is rewritten. Objectives and outcomes come back with
            # it, because the model wrote the document as a coherent whole and a
            # rubric that no longer matches its own outcomes is worse than either.
            doc_type = normalize_course_type(syllabus.doc_type or course.course_type)

            updates: dict = {
                "document":   parse_document(doc_type, result.document or {}),
                "objectives": result.objectives or [],
                "updated_at": datetime.now(timezone.utc),
            }

            # A THEORY document IS its units, so regenerating it replaces them.
            if result.units:
                await SyllabusUnitRepository.delete_all(syllabus_id, db=session)
                await SyllabusUnitRepository.bulk_create(syllabus_id, result.units, db=session)

            await SyllabusRepository.update(syllabus_id, updates, db=session)

            # COs are replaced wholesale for the same reason as SECTION_OUTCOMES: the
            # CO-PO matrix hangs off them, and half a matrix mapped against outcomes
            # that no longer exist is incoherent.
            await CourseOutcomeRepository.delete_all(syllabus_id, db=session)
            new_cos = await CourseOutcomeRepository.bulk_create(
                syllabus_id, result.outcomes or [], db=session,
            )
            po_by_code = {p.code: p.id for p in pos}
            mappings = []
            for ai_co, db_co in zip(result.outcomes or [], new_cos):
                strengths = ai_co.get("po_mapping_strengths", {})
                for code in ai_co.get("suggested_po_codes", []):
                    po_id = po_by_code.get(code)
                    if po_id is None:
                        continue
                    try:
                        strength = MappingStrength(strengths.get(code, "MEDIUM"))
                    except ValueError:
                        strength = MappingStrength.MEDIUM
                    mappings.append(
                        {"co_id": db_co.id, "po_id": po_id, "mapping_strength": strength}
                    )
            if mappings:
                await COPOMappingRepository.bulk_create(mappings, db=session)

            changed = {
                "doc_type":          doc_type,
                "document_sections": sorted((result.document or {}).keys()),
                "units":             len(result.units or []),
                "outcomes":          len(new_cos),
            }

        # Regenerating any part of an APPROVED syllabus withdraws that approval. The
        # sign-off meant "I have read exactly this", and this is no longer that.
        if syllabus.status == SyllabusStatus.APPROVED:
            await SyllabusRepository.revert_to_draft(syllabus_id, db=session)
            changed["approval_withdrawn"] = True

        await session.commit()

    if section in (SECTION_REFERENCES, SECTION_BOOKS, SECTION_DOCUMENT) and result.reference_queries:
        # BOOKS replaces the Text Books ONLY. REFERENCES replaces the other three
        # printed sections. Getting this scope wrong is how a Board that asked to
        # rewrite its textbook list silently loses its web resources.
        replace_types = (
            ["TEXTBOOK"] if section == SECTION_BOOKS
            else ["REFERENCE", "JOURNAL", "SUGGESTED_READING", "WEB_RESOURCE", "ONLINE"]
            if section == SECTION_REFERENCES
            else None       # DOCUMENT rewrote everything; replace the whole bibliography
        )
        _dispatch_reference_enrichment(
            syllabus_id=str(syllabus_id),
            tenant_id=str(tenant_id),
            schema_name=schema_name,
            reference_queries=result.reference_queries,
            replace_types=replace_types,
        )

    await AuditService.log(
        AuditEventType.SYLLABUS_SECTION_REGENERATED,
        actor_role="SYSTEM",
        tenant_id=tenant_id,
        schema_name=schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus_id),
        metadata={
            "section":     section,
            "model_used":  result.model_used,
            "prompt_hash": result.prompt_hash[:16],
            **changed,
        },
    )

    logger.info("m02.regenerate: section=%s syllabus=%s %s", section, syllabus_id, changed)
    return {"syllabus_id": str(syllabus_id), "section": section, **changed}
