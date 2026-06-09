"""Student Lifecycle Router — H64.3.

GET  /students/{student_id}/lifecycle   — current status + history  (ADMIN, DEAN)
POST /students/{student_id}/lifecycle   — transition to new status  (ADMIN, DEAN)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.lifecycle_schemas import (
    LifecycleStatusOut,
    LifecycleTransitionIn,
    LifecycleTransitionOut,
    LifecycleHistoryEntry,
)
from app.modules.m11_sis.lifecycle_service import LifecycleServiceError, StudentLifecycleService

lifecycle_router = APIRouter(tags=["SIS Student Lifecycle"])

_MGMT = (TenantRole.ADMIN, TenantRole.DEAN)


def _err(e: LifecycleServiceError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"error": e.code, "message": e.message})


@lifecycle_router.get("/students/{student_id}/lifecycle", response_model=LifecycleStatusOut)
async def get_student_lifecycle(
    student_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MGMT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> LifecycleStatusOut:
    try:
        data = await StudentLifecycleService.get_status(student_id, db)
    except LifecycleServiceError as e:
        raise _err(e)
    return LifecycleStatusOut(
        student_id=data["student_id"],
        current_status=data["current_status"],
        allowed_next=data["allowed_next"],
        history=[LifecycleHistoryEntry.model_validate(h) for h in data["history"]],
    )


@lifecycle_router.post("/students/{student_id}/lifecycle", response_model=LifecycleTransitionOut)
async def transition_student_lifecycle(
    student_id: UUID,
    body: LifecycleTransitionIn,
    current_user: CurrentUser = Depends(require_roles(*_MGMT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> LifecycleTransitionOut:
    try:
        from app.modules.m11_sis.lifecycle_service import StudentLifecycleService as Svc
        # Capture previous before transition
        status_data = await Svc.get_status(student_id, db)
        previous = status_data["current_status"]

        profile = await Svc.transition(
            student_id,
            body.new_status,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            reason=body.reason,
            db=db,
        )
    except LifecycleServiceError as e:
        raise _err(e)
    return LifecycleTransitionOut(
        student_id=student_id,
        previous_status=previous,
        new_status=profile.lifecycle_status,
        is_active=profile.is_active,
        message=f"Status changed from '{previous}' to '{profile.lifecycle_status}'.",
    )
