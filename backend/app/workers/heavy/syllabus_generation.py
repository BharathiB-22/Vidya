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

from app.database import tenant_schema_scope
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
        from app.database import bind_tenant_search_path
        # NullPool: no connection caching between asyncio.run() calls.
        # Each task creates a fresh event loop; pooled asyncpg connections
        # attached to the previous (now-closed) loop would cause
        # "Future attached to a different loop" — NullPool prevents that.
        _async_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        # And because of NullPool, a commit does not return this task's connection to
        # a pool — it closes it. Everything after the first commit therefore runs on a
        # connection that never saw a session-level `SET search_path`, which is why
        # this job died writing a table that exists. The search_path is re-applied at
        # the start of every transaction instead (app/database.py), which is the one
        # place a commit cannot undo it.
        bind_tenant_search_path(_async_engine)
    return _async_engine


# ---------------------------------------------------------------------------
# The Board's hours
# ---------------------------------------------------------------------------

def _apply_board_hours(units: list[dict], plan: list[int]) -> list[dict]:
    """Stamp the Board's hours onto the generated units.

    The model was TOLD these hours and asked to pace each unit to fit them, so it
    normally returns them unchanged — this is what makes sure of it. The units'
    hours add up to the course's taught hours, and a model that quietly returned 12
    where the Board said 10 would leave a printed regulation that does not add up.

    An empty plan means the Board did not state the hours, and the model's own pacing
    stands. A plan that no longer matches the number of units is ignored rather than
    stretched: it belongs to a syllabus of a different shape, and half-applying it
    would leave the last unit with hours nobody chose.
    """
    if not plan or len(plan) != len(units):
        return units

    by_number = sorted(units, key=lambda u: u["unit_number"])
    for unit, hours in zip(by_number, plan):
        unit["total_hours"] = hours
    return units


def _hours_for(unit: dict, plan: list[int]) -> list[int]:
    """The Board's hours for ONE unit, as a one-element plan.

    Units are now saved one at a time, so the whole-syllabus plan has to be sliced to
    the unit being saved. A unit whose number falls outside the plan (the Board changed
    the unit count after setting the hours) gets no plan and keeps the hours the model
    paced it to — the alternative is to give it somebody else's.
    """
    number = unit.get("unit_number") or 0
    return [plan[number - 1]] if 1 <= number <= len(plan) else []


async def _publish_progress(
    job_id: UUID,
    phase: str,
    message: str,
    *,
    total_units: int,
    engine,
) -> None:
    """Tell the Board what is happening, now, in their own words.

    In its OWN session, deliberately. The generation holds a long transaction — it is
    saving units as it writes them — and progress written inside that transaction would
    be invisible until the whole thing committed, which is precisely when nobody needs
    it any more. So this connects, writes, commits and leaves.

    Best-effort by design: a syllabus that generated perfectly must not fail because a
    progress line could not be written. A missed message costs a moment of silence; a
    raised exception here would cost the syllabus.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.m02_syllabus.repository import TaskJobPublicRepository

    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await TaskJobPublicRepository.set_progress(
                job_id,
                {"phase": phase, "message": message, "total_units": total_units},
                db=session,
            )
            await session.commit()
    except Exception:
        logger.warning(
            "m02.generate: could not publish progress '%s' (job=%s)", message, job_id,
            exc_info=True,
        )


async def _audit(engine, event_type, **fields) -> None:
    """An audit record, on a session of THIS worker's own — and always a fresh one.

    Two reasons, and the second is the one that cost us an afternoon of misleading logs.

    1. `AuditService.log` otherwise opens `AsyncSessionLocal`, which is bound to the
       API's engine. Its pooled asyncpg connections belong to whichever event loop
       created them, and a Celery task gets a brand-new loop every time (`asyncio.run`).
       Reaching for one from the next task finds a connection attached to a closed loop:
       "cannot perform operation: another operation is in progress".

    2. The audit record for a FAILURE must never be written through the transaction that
       failed. That session is poisoned — the next statement on it raises about
       connection state, not about the syllabus — and the real error, the one naming the
       unit that could not be generated, gets buried under a database error that is
       merely its echo. So this opens its own session, and the caller keeps its exception.

    Best-effort, like the progress channel: a missing audit line must never be the reason
    a Board is told a syllabus failed. `AuditService.log` swallows its own errors; this
    swallows the rest.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.service import AuditService

    try:
        async with AsyncSession(engine, expire_on_commit=False) as audit_session:
            await AuditService.log(event_type, db=audit_session, **fields)
    except Exception:
        logger.warning(
            "m02.generate: could not write audit record %s", event_type, exc_info=True,
        )


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
    # Which tenant every transaction in this task belongs to. Held for the whole run
    # and dropped at the end of it: a worker process is long-lived and serves every
    # tenant in turn, and a schema left set is a schema the next task inherits.
    with tenant_schema_scope(schema_name):
        return asyncio.run(
            _run_generation(
                # The job's own id, so the run can say what it is doing while it does
                # it. The Board watches a syllabus being written; it must not watch a
                # spinner.
                job_id=UUID(job_id),
                syllabus_id=UUID(syllabus_id),
                tenant_id=UUID(tenant_id),
                schema_name=schema_name,
            )
        )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_generation(
    job_id: UUID,
    syllabus_id: UUID,
    tenant_id: UUID,
    schema_name: str,
) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m01_program_advisor.models import CourseType, ProgramOutcome
    from app.modules.m01_program_advisor.repository import (
        CourseRepository,
        ProgramOutcomeRepository,
    )
    from app.modules.m02_syllabus.ai_provider import (
        PHASE_READING,
        PHASE_READY,
        PHASE_SAVING,
        POContext,
        SyllabusGenerationContext,
        generate_theory_syllabus,
        get_syllabus_provider,
        normalize_course_type,
        resolve_unit_count,
    )
    from app.modules.m02_syllabus.schemas import parse_document
    from app.modules.m02_syllabus.formatting import (
        derive_category,
        format_ltp,
        has_practical,
        resolve_teaching_hours,
        resolve_hours_per_week,
        derive_teaching_weeks,
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

            # The hours each unit is taught for — the BOARD'S, and nobody else's.
            #
            # Not the model's, and not the system's either. Nothing here computes them:
            # a theory syllabus whose hours the Board has not allocated does not reach
            # this worker at all (the service refuses to dispatch it), because how a
            # subject's taught hours are apportioned across its units is an academic
            # judgement and not a gap for software to fill.
            board_hours = list(syllabus.unit_hours or [])

            if course_type == CourseType.THEORY.value and not board_hours:
                raise ValueError(
                    f"Syllabus {syllabus_id} has no unit hours. The Board must allocate "
                    "them before its syllabus can be written — the system does not "
                    "invent academic structure."
                )

            # The header's two figures. Stated by the Board; the L-T-P is the fallback
            # for syllabi written before it could state them.
            _hours    = resolve_teaching_hours(course, syllabus.teaching_hours)
            _per_week = resolve_hours_per_week(course, syllabus.hours_per_week)

            ctx = SyllabusGenerationContext(
                course_id=str(syllabus.course_id),
                course_code=course.code,
                course_title=course.title,
                course_credits=course.credits,
                program_outcomes=po_contexts,
                custom_instructions=syllabus.custom_instructions,
                ltp=format_ltp(course),
                # What the subject is taught for, and at how many hours a week — the
                # header's own two figures, stated by the Board. Nothing here assumes
                # 60: a Board that typed 52 is telling the generator something true
                # that no multiplication of the L-T-P could have known. The weeks are
                # the arithmetic between them (52 at 4 a week is 13), and exist only to
                # pace the units.
                contact_hours=_hours,
                hours_per_week=_per_week,
                teaching_weeks=derive_teaching_weeks(_hours, _per_week),
                category=derive_category(course),
                has_practical=has_practical(course),
                course_type=course_type,
                # Four units or five, and the hours of each. Not the generator's to
                # pick — EVER.
                #
                # The Board states the hours when it generates one syllabus. When it
                # generates forty in a batch it states nothing, because forty hour
                # forms is not a workflow — and the old fallback there was to let the
                # model distribute them, which is how a 24-hour Unit III happens. So
                # the SYSTEM derives them from the contact hours the curriculum already
                # records, and the model is told the answer in every path.
                unit_count=resolve_unit_count(syllabus.unit_count),
                unit_hours_plan=board_hours,
            )

            provider = get_syllabus_provider()

            # ------------------------------------------------------------------
            # Clear what this run is replacing, BEFORE it starts.
            #
            # Units and COs go now rather than at the end, because the units of a
            # theory syllabus are now saved AS THEY ARE WRITTEN (below), and a Unit III
            # from the previous run sitting in the table while this run writes its own
            # Unit III is a uniqueness violation that would kill the job at its most
            # expensive moment. Confirmed references survive: they were fetched from
            # CrossRef and somebody vouched for them.
            # ------------------------------------------------------------------
            deleted_cos   = await CourseOutcomeRepository.delete_all(syllabus_id, db=session)
            deleted_units = await SyllabusUnitRepository.delete_all(syllabus_id, db=session)
            if deleted_cos or deleted_units:
                logger.info(
                    "m02.generate: cleared %d COs, %d units (syllabus=%s)",
                    deleted_cos, deleted_units, syllabus_id,
                )
            await session.commit()

            # ------------------------------------------------------------------
            # THEORY: written one unit at a time, and SAVED one unit at a time.
            #
            # Outline first (so the units cannot overlap), then each unit written,
            # validated, regenerated if it falls short — and committed the moment it
            # passes. A run that dies at Unit V leaves four good units on disk and the
            # Board regenerates the one that failed, instead of paying for all five
            # again. The syllabus stays AI_GENERATING throughout, which is already a
            # state nobody can edit or approve, and only becomes a DRAFT when the run
            # completes. An incomplete syllabus is therefore visible and repairable,
            # but never approvable — the approve gate tests completeness (see
            # m02.service compliance), rather than trusting that a row exists.
            #
            # Every other type keeps the single call it has always had: a lab manual, an
            # internship's guidelines and a project handbook have no units to write one
            # at a time. Course-type intelligence is untouched.
            # ------------------------------------------------------------------
            async def save_unit(unit: dict) -> None:
                """One validated unit, on disk, in its own transaction.

                The unit's HOURS are the Board's, taken from the plan by unit number.
                Not the model's — the response normaliser will happily invent six hours
                for a unit whose hours the model omitted, and a fabricated teaching hour
                that reached a locked regulation would be a number nobody chose
                governing a timetable somebody has to run.
                """
                hours = _hours_for(unit, board_hours)
                if not hours:
                    raise ValueError(
                        f"Unit {unit.get('unit_number')} has no hours in the Board's "
                        f"plan {board_hours}. The system does not choose teaching hours."
                    )

                stamped = _apply_board_hours([unit], hours)
                await SyllabusUnitRepository.bulk_create(syllabus_id, stamped, db=session)
                await session.commit()
                logger.info(
                    "m02.generate: saved unit %s (%d topics, syllabus=%s)",
                    unit.get("unit_number"), len(unit.get("topics", [])), syllabus_id,
                )

            async def say(phase: str, message: str) -> None:
                await _publish_progress(
                    job_id, phase, message,
                    total_units=resolve_unit_count(syllabus.unit_count),
                    engine=engine,
                )

            await say(PHASE_READING, "Reading curriculum…")

            if course_type == CourseType.THEORY.value:
                result = await generate_theory_syllabus(
                    provider, ctx, on_progress=say, on_unit=save_unit,
                )
            else:
                result = await provider.generate_syllabus(ctx)

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
            # Units — already on disk.
            #
            # A theory syllabus saved each unit as it passed validation (`save_unit`
            # above), which is what lets a run that dies at Unit V keep the four units
            # before it. There is nothing left to write here, and writing it again
            # would violate the (syllabus_id, unit_number) uniqueness constraint.
            #
            # Every other type has no units at all — a laboratory has experiments, an
            # internship has weekly activities, and neither has a Unit III. Their
            # content lives in `document`.
            # ------------------------------------------------------------------
            unit_count = len(result.units)

            # ------------------------------------------------------------------
            # Update syllabus: the document, official-format prose, AI metadata,
            # back to DRAFT.
            #
            # DRAFT, never APPROVED: AI advises, humans decide. A generated
            # document lands in the Board's queue for review and sign-off — it is
            # never self-approving, and the curriculum's approve gate will not
            # pass until a Board member has looked at it.
            # ------------------------------------------------------------------
            await _publish_progress(
                job_id, PHASE_SAVING, "Preparing draft…",
                total_units=resolve_unit_count(syllabus.unit_count), engine=engine,
            )

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

        await _publish_progress(
            job_id, PHASE_READY, "AI draft ready for Board review.",
            total_units=unit_count, engine=engine,
        )

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
        await _audit(
            engine,
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
                "units_created":    unit_count,
                "document_sections": sorted(result.document.keys()),
                "model_used":       result.model_used,
                "prompt_hash":      result.prompt_hash[:16],
            },
        )

        logger.info(
            "m02.generate: complete (syllabus=%s type=%s cos=%d units=%d doc_sections=%d)",
            syllabus_id, result.doc_type, len(new_cos), unit_count,
            len(result.document),
        )

        return {
            "syllabus_id":      str(syllabus_id),
            "doc_type":         result.doc_type,
            "cos_created":      len(new_cos),
            "mappings_created": len(mapping_items),
            "units_created":    unit_count,
            "model_used":       result.model_used,
            "provider":         result.provider_name,
        }

    except Exception as exc:
        # The run died. Whatever it had already written and validated STAYS — the units
        # that passed are real work, they cost real AI calls, and they are exactly what
        # lets the Board repair this with one click instead of paying for the whole
        # syllabus again.
        #
        # The syllabus goes back to DRAFT, which is what makes those units visible and
        # editable. It cannot be APPROVED in that state: approval tests completeness,
        # not existence (m02.service._run_compliance_check), so a syllabus missing
        # Unit V — or holding a Unit V with three topics in it — is refused at the gate.
        # The Board sees "AI generation incomplete" against the unit that failed, and
        # regenerates that unit alone.
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

        # What the Board is told, and it must not be a dead end. The AI stopped; the
        # syllabus did not. Everything that was written is on disk, the document is back
        # in DRAFT, every section is open, and the Board can finish it by hand or ask
        # for the missing part again. Compliance names what is still pending.
        await _publish_progress(
            job_id,
            "FAILED",
            "AI generation did not finish. What it wrote is saved — complete the "
            "remaining sections yourself, or regenerate them.",
            total_units=0,
            engine=engine,
        )

        # On a FRESH session, never the one that just failed — see `_audit`. The audit
        # record reports the error; it must not become one, and it must not replace the
        # exception the Board actually needs to see.
        await _audit(
            engine,
            AuditEventType.SYLLABUS_GENERATION_FAILED,
            actor_role="SYSTEM",
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="Syllabus",
            target_id=str(syllabus_id),
            metadata={"error": str(exc)[:500]},
        )

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
    with tenant_schema_scope(schema_name):
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
    from app.modules.m01_program_advisor.models import CourseType
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
        SectionGenerationResult,
        SyllabusGenerationContext,
        generate_theory_syllabus,
        get_syllabus_provider,
        normalize_course_type,
        resolve_unit_count,
    )
    from app.modules.m02_syllabus.formatting import (
        derive_category,
        format_ltp,
        has_practical,
        resolve_teaching_hours,
        resolve_hours_per_week,
        derive_teaching_weeks,
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
            # The same hours the syllabus was WRITTEN to, not a fresh derivation: a
            # rewritten unit has to fit the course the rest of the units belong to.
            contact_hours=resolve_teaching_hours(course, syllabus.teaching_hours),
            hours_per_week=resolve_hours_per_week(course, syllabus.hours_per_week),
            teaching_weeks=derive_teaching_weeks(
                resolve_teaching_hours(course, syllabus.teaching_hours),
                resolve_hours_per_week(course, syllabus.hours_per_week),
            ),
            category=derive_category(course),
            has_practical=has_practical(course),
            # Regenerate the document this course ACTUALLY has. The syllabus row's
            # own doc_type, not the course's current type: if a Dean reclassified
            # the course after the Board approved a lab manual, this row is still a
            # lab manual, and regenerating one of its sections must not quietly turn
            # it into a theory syllabus.
            course_type=normalize_course_type(syllabus.doc_type or course.course_type),
            # A regenerated syllabus must come back the same SHAPE as the one it
            # replaces — the Board decided how many units this course is taught in and
            # for how long each, and a rewrite does not reopen either decision.
            unit_count=resolve_unit_count(syllabus.unit_count),
            unit_hours_plan=list(syllabus.unit_hours or []),
        )

        call_kwargs: dict = {"guidance": guidance}
        target = None
        if section == SECTION_UNIT:
            target = next((u for u in syllabus.units if u.id == unit_id), None)
            if target is None:
                raise ValueError(f"Unit {unit_id} does not belong to syllabus {syllabus_id}.")
            # The unit's hours are the Board's allocation, not the model's — they are
            # part of a total that has to keep adding up. Tell the model what it is
            # writing to, so the topics are paced to hours it cannot change.
            ctx.unit_hours = target.total_hours
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

        # "Regenerate the entire syllabus" on a THEORY course is a fresh generation of
        # the whole document, so it goes through the same unit-at-a-time workflow a
        # first generation does — outline, then each unit written and validated on its
        # own. Doing it in one call here would make this the one door through which a
        # thin Unit IV could still reach the Board.
        #
        # Every other type's DOCUMENT — a lab manual, an internship's guidelines — is
        # regenerated in a single call, exactly as it is generated.
        if section == SECTION_DOCUMENT and ctx.course_type == CourseType.THEORY.value:
            full = await generate_theory_syllabus(provider, ctx)
            result = SectionGenerationResult(
                section=SECTION_DOCUMENT,
                units=full.units,
                objectives=full.objectives,
                outcomes=full.outcomes,
                reference_queries=full.reference_queries,
                practical_components=full.practical_components,
                document={},
                model_used=full.model_used,
                provider_name=full.provider_name,
                prompt_hash=full.prompt_hash,
            )
        else:
            result = await provider.generate_section(ctx, section, **call_kwargs)

        changed: dict = {}

        if section == SECTION_UNIT:
            # The Board's hours survive the rewrite. The units together total the
            # course's taught hours; letting a rewritten unit come back with hours of
            # its own choosing would break that total silently, and the Board would
            # find out by reading a printed regulation that no longer adds up.
            await SyllabusUnitRepository.update(
                unit_id,
                {
                    "title":       result.unit["title"],
                    "content":     result.unit.get("content"),
                    "topics":      result.unit.get("topics", []),
                    "total_hours": target.total_hours or result.unit["total_hours"],
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

            # A THEORY document IS its units, so regenerating it replaces them — and
            # the Board's hours survive the rewrite exactly as they survive a
            # single-unit one.
            if result.units:
                units_to_save = _apply_board_hours(result.units, list(syllabus.unit_hours or []))
                await SyllabusUnitRepository.delete_all(syllabus_id, db=session)
                await SyllabusUnitRepository.bulk_create(syllabus_id, units_to_save, db=session)

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

    await _audit(
        engine,
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
