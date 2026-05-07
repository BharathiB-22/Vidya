from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from app.core.task_queue.models import TaskJobStatus


class TaskJobCreate(BaseModel):
    task_type:  str
    queue_name: str = "celery"
    tenant_id:  Optional[UUID] = None
    payload:    Optional[dict[str, Any]] = None


class TaskJobResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:           UUID
    tenant_id:    Optional[UUID]
    task_type:    str
    queue_name:   str
    status:       TaskJobStatus
    payload:      Optional[dict[str, Any]]
    result:       Optional[dict[str, Any]]
    error:        Optional[str]
    created_at:   datetime
    started_at:   Optional[datetime]
    completed_at: Optional[datetime]


class TaskJobListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    items:     list[TaskJobResponse]
