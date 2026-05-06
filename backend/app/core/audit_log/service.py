import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.core.audit_log.models import AuditEventType
from app.core.audit_log.repository import AuditLogRepository
from app.core.audit_log.schemas import AuditLogEntry, AuditLogListResponse

logger = logging.getLogger("vidya.audit")


class AuditService:

    @staticmethod
    async def log(
        event_type: AuditEventType,
        *,
        actor_user_id: UUID | None = None,
        actor_role: str | None = None,
        tenant_id: UUID | None = None,
        schema_name: str | None = None,
        target_entity: str | None = None,
        target_id: str | None = None,
        metadata: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        # Opens its own session — fully independent of any business transaction.
        # Swallows all exceptions per OQ-01: a DB outage must not block the
        # caller's business operation.  Failures are emitted to the audit logger
        # so they appear in structured logs without disrupting the response.
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await AuditLogRepository.create(
                        event_type.value,
                        actor_user_id=actor_user_id,
                        actor_role=actor_role,
                        tenant_id=tenant_id,
                        schema_name=schema_name,
                        target_entity=target_entity,
                        target_id=target_id,
                        metadata=metadata,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        db=session,
                    )
        except Exception:
            logger.error(
                "audit_write_failed event_type=%s actor=%s tenant=%s",
                event_type.value,
                actor_user_id,
                tenant_id,
                exc_info=True,
            )

    @staticmethod
    async def query(
        *,
        current_role: str,
        current_tenant_id: UUID | None,
        filter_tenant_id: UUID | None = None,
        event_type: AuditEventType | None = None,
        actor_user_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
        db: AsyncSession,
    ) -> AuditLogListResponse:
        is_super_admin = current_role == "SUPER_ADMIN"

        if is_super_admin:
            # SUPER_ADMIN sees everything; may optionally narrow by tenant_id.
            restrict = False
            effective_tenant_id = filter_tenant_id
        else:
            # ADMIN is always restricted to their own tenant.
            # filter_tenant_id from the request is intentionally ignored here —
            # scope comes exclusively from the JWT, never from the caller.
            restrict = True
            effective_tenant_id = current_tenant_id

        offset = (page - 1) * page_size
        event_type_str = event_type.value if event_type is not None else None

        total = await AuditLogRepository.count(
            tenant_id=effective_tenant_id,
            restrict_to_tenant=restrict,
            event_type=event_type_str,
            actor_user_id=actor_user_id,
            date_from=date_from,
            date_to=date_to,
            db=db,
        )
        rows = await AuditLogRepository.list(
            tenant_id=effective_tenant_id,
            restrict_to_tenant=restrict,
            event_type=event_type_str,
            actor_user_id=actor_user_id,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=page_size,
            db=db,
        )
        items = [AuditLogEntry.model_validate(r) for r in rows]
        return AuditLogListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=items,
        )
