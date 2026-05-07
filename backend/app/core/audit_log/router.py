from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth.dependencies import require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.audit_log.models import AuditEventType
from app.core.audit_log.schemas import AuditLogListResponse
from app.core.audit_log.service import AuditService

router = APIRouter(tags=["audit-log"])


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    event_type:    AuditEventType | None = Query(None, description="Filter by event type"),
    actor_user_id: UUID | None           = Query(None, description="Filter by actor user ID"),
    tenant_id:     UUID | None           = Query(None, description="Filter by tenant (SUPER_ADMIN only; ignored for ADMIN)"),
    date_from:     datetime | None       = Query(None, description="Inclusive start of date range (ISO 8601)"),
    date_to:       datetime | None       = Query(None, description="Inclusive end of date range (ISO 8601)"),
    page:          int                   = Query(1,   ge=1,            description="Page number (1-based)"),
    page_size:     int                   = Query(50,  ge=1,   le=200,  description="Items per page"),
    current_user:  CurrentUser           = Depends(require_roles(TenantRole.ADMIN)),
    db:            AsyncSession          = Depends(get_db),
) -> AuditLogListResponse:
    return await AuditService.query(
        current_role=current_user.role,
        current_tenant_id=current_user.tenant_id,
        filter_tenant_id=tenant_id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
        db=db,
    )
