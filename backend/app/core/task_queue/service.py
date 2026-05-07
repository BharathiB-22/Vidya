import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.task_queue.models import TaskJobStatus
from app.core.task_queue.repository import TaskJobRepository
from app.core.task_queue.schemas import TaskJobCreate, TaskJobListResponse, TaskJobResponse

logger = logging.getLogger("vidya.task_queue")


class TaskQueueError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class TaskQueueService:

    @staticmethod
    async def submit(
        create_data: TaskJobCreate,
        *,
        task_fn: Any,
        extra_kwargs: dict | None = None,
        db: AsyncSession,
    ) -> TaskJobResponse:
        """Create a PENDING task_jobs row then dispatch to Celery.

        The commit happens before apply_async so the worker's before_start
        hook can UPDATE the row the moment it dequeues the task.  If
        apply_async raises after the commit the row remains PENDING and
        is visible for inspection or retry — no rollback is attempted.
        """
        job = await TaskJobRepository.create(create_data, db=db)
        await db.commit()

        kwargs = {"job_id": str(job.id), **(extra_kwargs or {})}
        try:
            task_fn.apply_async(kwargs=kwargs)
        except Exception:
            logger.exception(
                "task_dispatch_failed job_id=%s task_type=%s",
                job.id,
                job.task_type,
            )

        return TaskJobResponse.model_validate(job)

    @staticmethod
    async def get(
        job_id: UUID,
        *,
        tenant_id: UUID | None = None,
        db: AsyncSession,
    ) -> TaskJobResponse:
        """Fetch a single job.

        Pass tenant_id for tenant-scoped calls; omit for SUPER_ADMIN.
        Raises TaskQueueError(404) if the row does not exist or belongs
        to a different tenant.
        """
        job = await TaskJobRepository.get_by_id(job_id, tenant_id=tenant_id, db=db)
        if job is None:
            raise TaskQueueError("NOT_FOUND", "Task job not found", 404)
        return TaskJobResponse.model_validate(job)

    @staticmethod
    async def query(
        *,
        current_role: str,
        current_tenant_id: UUID | None,
        status: TaskJobStatus | None = None,
        task_type: str | None = None,
        queue_name: str | None = None,
        page: int = 1,
        page_size: int = 50,
        db: AsyncSession,
    ) -> TaskJobListResponse:
        """Return a paginated list of task jobs scoped by caller role.

        SUPER_ADMIN sees all jobs and may pass no tenant filter.
        ADMIN is always restricted to their own tenant; any tenant filter
        from the request is ignored — scope comes from the JWT only.
        """
        if current_role == "SUPER_ADMIN":
            effective_tenant_id = None
        else:
            effective_tenant_id = current_tenant_id

        offset = (page - 1) * page_size

        total = await TaskJobRepository.count(
            tenant_id=effective_tenant_id,
            status=status,
            task_type=task_type,
            queue_name=queue_name,
            db=db,
        )
        rows = await TaskJobRepository.list(
            tenant_id=effective_tenant_id,
            status=status,
            task_type=task_type,
            queue_name=queue_name,
            offset=offset,
            limit=page_size,
            db=db,
        )
        items = [TaskJobResponse.model_validate(r) for r in rows]
        return TaskJobListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=items,
        )

    @staticmethod
    async def cancel(
        job_id: UUID,
        *,
        tenant_id: UUID | None = None,
        db: AsyncSession,
    ) -> TaskJobResponse:
        """Set a PENDING or RUNNING job to CANCELLED (DB-only, best-effort).

        The Celery broker is not contacted — a task already dequeued by a
        worker may still run to completion and overwrite this status.
        Pass tenant_id for tenant-scoped calls; omit for SUPER_ADMIN.
        Raises TaskQueueError(409) if the job is terminal or not found.
        """
        job = await TaskJobRepository.cancel(job_id, tenant_id=tenant_id, db=db)
        if job is None:
            raise TaskQueueError(
                "NOT_CANCELLABLE",
                "Job is already in a terminal state or does not exist",
                409,
            )
        await db.commit()
        return TaskJobResponse.model_validate(job)
