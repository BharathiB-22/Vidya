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
        db: AsyncSession | None = None,
    ) -> None:
        # Opens its own session — fully independent of any business transaction.
        # Swallows all exceptions per OQ-01: a DB outage must not block the
        # caller's business operation.  Failures are emitted to the audit logger
        # so they appear in structured logs without disrupting the response.
        #
        # `db` — A SESSION THE CALLER OPENED, for callers that cannot use ours.
        #
        # A Celery worker is one. `AsyncSessionLocal` is bound to the API's engine,
        # whose pooled asyncpg connections belong to the event loop that created them —
        # and a worker gets a NEW loop per task (`asyncio.run`). Writing an audit row
        # through it from inside a task therefore reaches for a connection attached to a
        # loop that has since closed, and asyncpg says so: "cannot perform operation:
        # another operation is in progress", or "Event loop is closed". That failure
        # then landed on top of whatever the worker was already reporting, and buried it.
        #
        # So a worker hands us a session of its own, on its own engine — and it must be
        # a FRESH one, never the session whose transaction just failed. A session that
        # has raised is not usable again until it is rolled back or discarded; trying to
        # write the audit record for a failure through the very transaction that failed
        # is how the original error gets replaced by a confusing one about connection
        # state. The audit trail must report the failure, not become it.
        try:
            if db is not None:
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
                    db=db,
                )
                await db.commit()
                return

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
