from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth.dependencies import require_super_admin
from app.core.auth.schemas import CurrentUser
from app.core.audit_log.models import AuditEventType
from app.core.audit_log.repository import AuditLogRepository
from app.core.audit_log.schemas import AuditLogEntry, AuditLogListResponse, PlatformAuditStats

router = APIRouter(tags=["platform-audit"])


@router.get("/stats", response_model=PlatformAuditStats)
async def get_platform_audit_stats(
    _: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformAuditStats:
    counts = await AuditLogRepository.count_by_category(db)
    recent_rows = await AuditLogRepository.list(restrict_to_tenant=False, limit=20, db=db)
    return PlatformAuditStats(
        total_events=counts["total"],
        tenant_events=counts["tenant_events"],
        login_events=counts["login_events"],
        ai_events=counts["ai_events"],
        security_events=counts["security_events"],
        recent=[AuditLogEntry.model_validate(r) for r in recent_rows],
    )


@router.get("", response_model=AuditLogListResponse)
async def list_platform_audit_logs(
    tenant_id:  UUID | None           = Query(None, description="Filter by tenant UUID"),
    event_type: AuditEventType | None = Query(None, description="Filter by exact event type"),
    date_from:  datetime | None       = Query(None, description="Inclusive start (ISO 8601)"),
    date_to:    datetime | None       = Query(None, description="Inclusive end (ISO 8601)"),
    page:       int                   = Query(1,  ge=1),
    page_size:  int                   = Query(50, ge=1, le=200),
    _: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    event_type_str = event_type.value if event_type is not None else None
    offset = (page - 1) * page_size

    total = await AuditLogRepository.count(
        tenant_id=tenant_id,
        restrict_to_tenant=False,
        event_type=event_type_str,
        date_from=date_from,
        date_to=date_to,
        db=db,
    )
    rows = await AuditLogRepository.list(
        tenant_id=tenant_id,
        restrict_to_tenant=False,
        event_type=event_type_str,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=page_size,
        db=db,
    )
    items = [AuditLogEntry.model_validate(r) for r in rows]
    return AuditLogListResponse(total=total, page=page, page_size=page_size, items=items)
