from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole

_ALL_TENANT_ROLES = (
    TenantRole.STUDENT,
    TenantRole.FACULTY,
    TenantRole.ADMIN,
    TenantRole.DEAN,
    TenantRole.BOARD,
    TenantRole.GUIDE,
)
from app.core.auth.schemas import CurrentUser
from app.core.notifications.schemas import (
    MarkReadResponse,
    NotificationListResponse,
)
from app.core.notifications.service import NotificationError, NotificationService

router = APIRouter(tags=["notifications"])


def _notification_error(e: NotificationError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    is_read:  bool | None = Query(None, description="Filter by read status"),
    page:     int         = Query(1,   ge=1,          description="Page number (1-based)"),
    page_size: int        = Query(50,  ge=1, le=200,  description="Items per page"),
    current_user: CurrentUser  = Depends(require_roles(*_ALL_TENANT_ROLES)),
    db: AsyncSession           = Depends(get_tenant_db_dep),
) -> NotificationListResponse:
    return await NotificationService.query(
        current_user_id=current_user.user_id,
        is_read=is_read,
        page=page,
        page_size=page_size,
        db=db,
    )


@router.patch("/{notification_id}/read", response_model=MarkReadResponse)
async def mark_notification_read(
    notification_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_ALL_TENANT_ROLES)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> MarkReadResponse:
    try:
        return await NotificationService.mark_read(
            notification_id,
            current_user_id=current_user.user_id,
            db=db,
        )
    except NotificationError as e:
        raise _notification_error(e)


@router.post("/read-all", response_model=dict)
async def mark_all_notifications_read(
    current_user: CurrentUser = Depends(require_roles(*_ALL_TENANT_ROLES)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> dict:
    return await NotificationService.mark_all_read(
        current_user_id=current_user.user_id,
        db=db,
    )
