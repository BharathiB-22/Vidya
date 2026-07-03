import asyncio
import logging
import sys
from datetime import datetime, timezone
from uuid import UUID

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m01")

# ---------------------------------------------------------------------------
# Module-level async engine — lazy, cached, one per worker process.
# Mirrors the _get_sync_engine() pattern in base_task.py.
# ---------------------------------------------------------------------------

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        from app.config import settings
        # NullPool: no connection caching between asyncio.run() calls.
        # Prevents "Future attached to a different loop" on Windows --pool=solo.
        _async_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    return _async_engine


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.generate_program_structure",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def generate_program_structure(
    *,
    job_id: str,
    program_id: str,
    tenant_id: str,
    schema_name: str,
    prompt_hint: str | None = None,
    ai_instructions: str | None = None,
    request_id: str | None = None,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_generation(
            program_id=UUID(program_id),
            schema_name=schema_name,
            prompt_hint=prompt_hint,
            ai_instructions=ai_instructions,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_generation(
    program_id: UUID,
    schema_name: str,
    prompt_hint: str | None,
    ai_instructions: str | None = None,
) -> dict:
    from sqlalchemy import text, update as sql_update
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.m01_program_advisor.ai_provider import (
        ProgramGenerationContext,
        get_structure_provider,
    )
    from app.modules.m01_program_advisor.compliance import (
        CourseNode,
        detect_prerequisite_cycles,
    )
    from app.modules.m01_program_advisor.models import Course as CourseModel, ProgramStatus
    from app.modules.m01_program_advisor.repository import (
        CoursePrerequisiteRepository,
        CourseRepository,
        ProgramOutcomeRepository,
        ProgramRepository,
    )
    from app.modules.m01_program_advisor.schemas import CourseCreate, ProgramOutcomeCreate

    engine = _get_async_engine()

    async with AsyncSession(engine, expire_on_commit=False) as session:

        # Tenant isolation — all repository queries are schema-less;
        # search_path resolves them to the correct tenant schema.
        await session.execute(text(f"SET search_path TO {schema_name}, public"))

        # ------------------------------------------------------------------
        # Load program
        # ------------------------------------------------------------------
        program = await ProgramRepository.get_by_id(program_id, db=session)
        if program is None:
            raise ValueError(f"Program {program_id} not found in schema {schema_name!r}.")

        # ------------------------------------------------------------------
        # Load existing outcomes — codes are preserved; only new codes added
        # ------------------------------------------------------------------
        existing_outcomes = await ProgramOutcomeRepository.list_by_program(
            program_id, db=session
        )
        existing_codes = {o.code for o in existing_outcomes}

        # ------------------------------------------------------------------
        # Build generation context and call Gemini
        # ------------------------------------------------------------------
        ctx = ProgramGenerationContext(
            degree_type=program.degree_type,
            department=program.department,
            duration_years=program.duration_years,
            total_credits=program.total_credits,
            prompt_hint=prompt_hint,
            ai_instructions=ai_instructions or program.ai_instructions,
            existing_outcome_codes=list(existing_codes),
        )

        provider = get_structure_provider()
        result = await provider.generate_structure(ctx)

        # ------------------------------------------------------------------
        # Cycle detection on AI output — fail fast before any DB write
        # ------------------------------------------------------------------
        temp_ids = {c["code"]: UUID(int=i) for i, c in enumerate(result.courses)}
        ai_nodes = [
            CourseNode(
                id=temp_ids[c["code"]],
                code=c["code"],
                credits=c["credits"],
                semester=c["semester"],
                is_elective=c["is_elective"],
                prerequisite_course_ids=[
                    temp_ids[pc]
                    for pc in c.get("prerequisite_codes", [])
                    if pc in temp_ids
                ],
            )
            for c in result.courses
        ]
        cycle_violations = detect_prerequisite_cycles(ai_nodes)
        if cycle_violations:
            msgs = "; ".join(v.message for v in cycle_violations)
            raise ValueError(f"AI output contains circular prerequisites: {msgs}")

        # ------------------------------------------------------------------
        # Idempotency: delete stale AI-generated courses before re-inserting.
        # Human-authored courses (is_ai_generated=False) are never touched.
        # ------------------------------------------------------------------
        deleted = await CourseRepository.delete_ai_generated(program_id, db=session)
        if deleted:
            logger.info(
                "m01.generate: cleared %d stale ai courses (program=%s)",
                deleted, program_id,
            )

        # ------------------------------------------------------------------
        # Bulk create new AI courses, then flag them as AI-generated.
        # Flagging is done via a targeted UPDATE on the new IDs only —
        # mark_all_ai_generated would incorrectly stamp human-authored courses.
        # ------------------------------------------------------------------
        course_creates = [
            CourseCreate(
                code=c["code"],
                title=c["title"],
                credits=c["credits"],
                semester=c["semester"],
                course_type=c.get("course_type"),
                is_elective=c["is_elective"],
                hours_lecture=c["hours_lecture"],
                hours_tutorial=c["hours_tutorial"],
                hours_practical=c["hours_practical"],
                description=c.get("description"),
            )
            for c in result.courses
        ]
        new_courses = await CourseRepository.bulk_create(program_id, course_creates, db=session)

        if new_courses:
            new_ids = [c.id for c in new_courses]
            await session.execute(
                sql_update(CourseModel)
                .where(CourseModel.id.in_(new_ids))
                .values(is_ai_generated=True)
            )

        logger.info(
            "m01.generate: created %d ai courses (program=%s)",
            len(new_courses), program_id,
        )

        # ------------------------------------------------------------------
        # Build full code→id map (human + AI) for prerequisite resolution
        # ------------------------------------------------------------------
        all_courses = await CourseRepository.list_by_program(program_id, db=session)
        code_to_id = {c.code: c.id for c in all_courses}

        # ------------------------------------------------------------------
        # Wire prerequisites
        # ------------------------------------------------------------------
        prereq_count = 0
        for ai_dict, db_course in zip(result.courses, new_courses):
            prereq_ids = [
                code_to_id[pc]
                for pc in ai_dict.get("prerequisite_codes", [])
                if pc in code_to_id and code_to_id[pc] != db_course.id
            ]
            if prereq_ids:
                await CoursePrerequisiteRepository.bulk_create(
                    db_course.id, prereq_ids, db=session
                )
                prereq_count += len(prereq_ids)

        # ------------------------------------------------------------------
        # Add new AI outcomes — skip codes already present (human-edited)
        # ------------------------------------------------------------------
        new_outcome_creates = [
            ProgramOutcomeCreate(
                code=o["code"],
                description=o["description"],
                bloom_level=o.get("bloom_level"),
                display_order=o.get("display_order", 0),
            )
            for o in result.outcomes
            if o["code"] not in existing_codes
        ]
        new_outcomes = []
        if new_outcome_creates:
            new_outcomes = await ProgramOutcomeRepository.bulk_create(
                program_id, new_outcome_creates, db=session
            )
        logger.info(
            "m01.generate: added %d new outcomes (program=%s)",
            len(new_outcomes), program_id,
        )

        # ------------------------------------------------------------------
        # Update program — record AI metadata and advance status
        # ------------------------------------------------------------------
        await ProgramRepository.update(
            program_id,
            {
                "ai_model":   result.model_used,
                "prompt_hash": result.prompt_hash,
                "status":     ProgramStatus.PENDING_APPROVAL,
                "updated_at": datetime.now(timezone.utc),
            },
            db=session,
        )

        await session.commit()

    return {
        "program_id":          str(program_id),
        "courses_created":     len(new_courses),
        "outcomes_added":      len(new_outcomes),
        "prerequisites_wired": prereq_count,
        "model_used":          result.model_used,
        "provider":            result.provider_name,
    }
