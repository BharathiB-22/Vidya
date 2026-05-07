from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.task_queue.models import TaskJob, TaskJobStatus
from app.core.task_queue.schemas import TaskJobCreate

# Only these statuses may be cancelled by the orchestration layer.
# Execution-lifecycle transitions (RUNNING, SUCCESS, FAILED) are owned
# exclusively by VidyaTask hooks in app.workers.base_task.
_CANCELLABLE = (TaskJobStatus.PENDING, TaskJobStatus.RUNNING)


class TaskJobRepository:

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filters(
        *,
        tenant_id:  UUID | None,
        status:     TaskJobStatus | None,
        task_type:  str | None,
        queue_name: str | None,
    ) -> list:
        clauses = []
        if tenant_id is not None:
            clauses.append(TaskJob.tenant_id == tenant_id)
        if status is not None:
            clauses.append(TaskJob.status == status)
        if task_type is not None:
            clauses.append(TaskJob.task_type == task_type)
        if queue_name is not None:
            clauses.append(TaskJob.queue_name == queue_name)
        return clauses

    # ------------------------------------------------------------------
    # Write (orchestration actions only — no lifecycle transitions here)
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        create_data: TaskJobCreate,
        *,
        db: AsyncSession,
    ) -> TaskJob:
        job = TaskJob(
            tenant_id=create_data.tenant_id,
            task_type=create_data.task_type,
            queue_name=create_data.queue_name,
            status=TaskJobStatus.PENDING,
            payload=create_data.payload,
        )
        db.add(job)
        await db.flush()
        await db.refresh(job)
        return job

    @staticmethod
    async def cancel(
        job_id: UUID,
        *,
        tenant_id: UUID | None = None,
        db: AsyncSession,
    ) -> TaskJob | None:
        """Set status=CANCELLED for a PENDING or RUNNING job.

        Pass tenant_id for tenant-scoped calls (prevents cross-tenant
        cancellation).  Omit only for Super Admin platform-level calls.

        Returns the updated row.  Returns None if the job is terminal
        (SUCCESS / FAILED / CANCELLED), does not exist, or belongs to a
        different tenant — the service layer should raise HTTP 409 on None.
        """
        clauses = [
            TaskJob.id == job_id,
            TaskJob.status.in_(_CANCELLABLE),
        ]
        if tenant_id is not None:
            clauses.append(TaskJob.tenant_id == tenant_id)

        stmt = (
            update(TaskJob)
            .where(and_(*clauses))
            .values(status=TaskJobStatus.CANCELLED, completed_at=func.now())
            .returning(TaskJob)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        job_id: UUID,
        *,
        tenant_id: UUID | None = None,
        db: AsyncSession,
    ) -> TaskJob | None:
        """Fetch a single job by PK.

        Pass tenant_id to enforce tenant isolation — omit only for Super
        Admin lookups that may span tenants.
        """
        clauses = [TaskJob.id == job_id]
        if tenant_id is not None:
            clauses.append(TaskJob.tenant_id == tenant_id)
        result = await db.execute(
            select(TaskJob).where(and_(*clauses))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list(
        *,
        tenant_id:  UUID | None = None,
        status:     TaskJobStatus | None = None,
        task_type:  str | None = None,
        queue_name: str | None = None,
        offset:     int = 0,
        limit:      int = 50,
        db: AsyncSession,
    ) -> list[TaskJob]:
        clauses = TaskJobRepository._build_filters(
            tenant_id=tenant_id,
            status=status,
            task_type=task_type,
            queue_name=queue_name,
        )
        stmt = select(TaskJob)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        stmt = (
            stmt
            .order_by(TaskJob.created_at.desc(), TaskJob.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count(
        *,
        tenant_id:  UUID | None = None,
        status:     TaskJobStatus | None = None,
        task_type:  str | None = None,
        queue_name: str | None = None,
        db: AsyncSession,
    ) -> int:
        clauses = TaskJobRepository._build_filters(
            tenant_id=tenant_id,
            status=status,
            task_type=task_type,
            queue_name=queue_name,
        )
        stmt = select(func.count(TaskJob.id))
        if clauses:
            stmt = stmt.where(and_(*clauses))
        result = await db.execute(stmt)
        return result.scalar_one()
