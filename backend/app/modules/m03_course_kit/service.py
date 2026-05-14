"""
M03 CourseKitService — state machine, dispatch, compliance, fork, CRUD.

STEP-06 scope: generation dispatch only.
STEP-07 scope: full state machine, compliance, fork, and CRUD methods.

Architecture contract
---------------------
  - All business logic lives here; routers are pure HTTP glue.
  - KitServiceError carries a machine-readable `code`, human `message`,
    and HTTP `status_code` so routers can raise HTTPException without logic.
  - Generation dispatch: creates a task_jobs row, sets status → AI_GENERATING
    atomically before dispatching so re-dispatch is blocked until the task
    finishes or fails.
  - AI advises, humans decide: no grade, penalty, or rejection logic here.
  - Every consequential action requires a human ratification step (publish,
    fork, archive all require explicit faculty/admin action; AI generation
    only produces a DRAFT — never directly PUBLISHED).
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m03_course_kit.models import CourseKitStatus
from app.modules.m03_course_kit.repository import (
    CourseKitRepository,
    TaskJobPublicRepository,
)

logger = logging.getLogger("vidya.service.m03")


# ---------------------------------------------------------------------------
# Exported error class
# ---------------------------------------------------------------------------

class KitServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Generation dispatch (STEP-06)
# ---------------------------------------------------------------------------

class CourseKitService:

    @staticmethod
    async def dispatch_kit_generation(
        kit_id: UUID,
        tenant_id: UUID,
        schema_name: str,
        *,
        db: AsyncSession,
    ) -> str:
        """
        Queue the AI course-kit generation Celery task.  Returns the job_id (str).

        Only valid from DRAFT status.  Sets status to AI_GENERATING atomically
        before dispatching so concurrent re-dispatch requests are rejected until
        the task completes or fails (at which point reset_to_draft is called).
        """
        kit = await CourseKitRepository.get_by_id(kit_id, db=db)
        if kit is None:
            raise KitServiceError("NOT_FOUND", "Course kit not found.", 404)

        if kit.status != CourseKitStatus.DRAFT:
            raise KitServiceError(
                "INVALID_STATE",
                f"Course kit is {kit.status.value}; "
                "AI generation can only be triggered from DRAFT status.",
                409,
            )

        # Create task_jobs row (public schema — tenant_id scoped)
        job_id = await TaskJobPublicRepository.create(
            tenant_id=tenant_id,
            task_type="course_kit_generation",
            queue_name="heavy",
            payload={"kit_id": str(kit_id), "schema_name": schema_name},
            db=db,
        )

        # Atomically advance to AI_GENERATING so duplicate dispatches are blocked.
        await CourseKitRepository.update_status(
            kit_id, CourseKitStatus.AI_GENERATING, db=db
        )
        await db.commit()

        # Deferred import avoids circular dependency at module load time.
        from app.workers.heavy.course_kit_generation import generate_course_kit  # noqa: PLC0415

        generate_course_kit.delay(
            job_id=str(job_id),
            kit_id=str(kit_id),
            tenant_id=str(tenant_id),
            schema_name=schema_name,
        )
        logger.info(
            "m03.service: AI generation queued (kit=%s job=%s unit=%s)",
            kit_id, job_id, kit.unit_number,
        )
        return str(job_id)

    # =========================================================================
    # STEP-07 will add: create_kit, update_kit, delete_kit, publish, archive,
    # fork, compliance_check, and all CRUD helpers.
    # =========================================================================
