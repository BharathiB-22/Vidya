from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth.dependencies import require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.task_queue.models import TaskJobStatus
from app.core.task_queue.schemas import TaskJobListResponse, TaskJobResponse
from app.core.task_queue.service import TaskQueueError, TaskQueueService

router = APIRouter(tags=["task-queue"])


def _task_queue_error(e: TaskQueueError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


@router.get("", response_model=TaskJobListResponse)
async def list_jobs(
    status:     TaskJobStatus | None = Query(None, description="Filter by job status"),
    task_type:  str | None           = Query(None, description="Filter by task type"),
    queue_name: str | None           = Query(None, description="Filter by queue name"),
    page:       int                  = Query(1,   ge=1,           description="Page number (1-based)"),
    page_size:  int                  = Query(50,  ge=1,  le=200,  description="Items per page"),
    current_user: CurrentUser        = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession                 = Depends(get_db),
) -> TaskJobListResponse:
    return await TaskQueueService.query(
        current_role=current_user.role,
        current_tenant_id=current_user.tenant_id,
        status=status,
        task_type=task_type,
        queue_name=queue_name,
        page=page,
        page_size=page_size,
        db=db,
    )


@router.get("/{job_id}", response_model=TaskJobResponse)
async def get_job(
    job_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession          = Depends(get_db),
) -> TaskJobResponse:
    try:
        return await TaskQueueService.get(
            job_id,
            tenant_id=current_user.tenant_id,
            db=db,
        )
    except TaskQueueError as e:
        raise _task_queue_error(e)


@router.post("/{job_id}/cancel", response_model=TaskJobResponse)
async def cancel_job(
    job_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession          = Depends(get_db),
) -> TaskJobResponse:
    try:
        return await TaskQueueService.cancel(
            job_id,
            tenant_id=current_user.tenant_id,
            db=db,
        )
    except TaskQueueError as e:
        raise _task_queue_error(e)
