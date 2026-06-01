from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditLog

_LOGIN_PREFIXES  = ('AUTH_LOGIN_', 'PLATFORM_LOGIN_')
_TENANT_PREFIX   = 'TENANT_'
_AI_SUBSTRINGS   = ('_GENERATION_', 'AI_EVALUATED', 'AI_GENERATED', 'AI_REVIEW',
                    'BELL_CURVE_ANALYSIS', 'LAB_EVAL_COMPLETED', 'LAB_EVAL_FAILED',
                    'SCRIPT_SCORING_')
_SECURITY_TYPES  = {
    'AUTH_TOKEN_REUSE_DETECTED', 'PLATFORM_TOKEN_REUSE_DETECTED',
    'AUTH_LOGIN_FAILURE', 'PLATFORM_LOGIN_FAILURE',
    'AUTH_PASSWORD_RESET_OTP_FAILED', 'PLATFORM_PASSWORD_RESET_OTP_FAILED',
}


class AuditLogRepository:

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filters(
        *,
        tenant_id: UUID | None,
        restrict_to_tenant: bool,
        event_type: str | None,
        actor_user_id: UUID | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list:
        clauses = []

        if tenant_id is not None:
            clauses.append(AuditLog.tenant_id == tenant_id)
        elif restrict_to_tenant:
            # ADMIN path reached without a tenant_id — return nothing rather
            # than accidentally exposing data from other tenants.
            clauses.append(false())

        if event_type is not None:
            clauses.append(AuditLog.event_type == event_type)
        if actor_user_id is not None:
            clauses.append(AuditLog.actor_user_id == actor_user_id)
        if date_from is not None:
            clauses.append(AuditLog.created_at >= date_from)
        if date_to is not None:
            clauses.append(AuditLog.created_at <= date_to)

        return clauses

    # ------------------------------------------------------------------
    # Write (append-only — no update or delete methods exist)
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        event_type: str,
        *,
        actor_user_id: UUID | None,
        actor_role: str | None,
        tenant_id: UUID | None,
        schema_name: str | None,
        target_entity: str | None,
        target_id: str | None,
        metadata: dict | None,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> AuditLog:
        entry = AuditLog(
            event_type=event_type,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity=target_entity,
            target_id=target_id,
            metadata_=metadata,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(entry)
        await db.flush()
        await db.refresh(entry)
        return entry

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def list(
        *,
        tenant_id: UUID | None = None,
        restrict_to_tenant: bool = False,
        event_type: str | None = None,
        actor_user_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[AuditLog]:
        clauses = AuditLogRepository._build_filters(
            tenant_id=tenant_id,
            restrict_to_tenant=restrict_to_tenant,
            event_type=event_type,
            actor_user_id=actor_user_id,
            date_from=date_from,
            date_to=date_to,
        )
        stmt = select(AuditLog)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_category(db: AsyncSession) -> dict[str, int]:
        """Single GROUP BY query; returns category counts for the KPI dashboard."""
        stmt = (
            select(AuditLog.event_type, func.count(AuditLog.id))
            .group_by(AuditLog.event_type)
        )
        result = await db.execute(stmt)
        counts: dict[str, int] = {row[0]: row[1] for row in result.all()}

        total    = sum(counts.values())
        login    = sum(v for k, v in counts.items() if k.startswith(_LOGIN_PREFIXES))
        tenant   = sum(v for k, v in counts.items() if k.startswith(_TENANT_PREFIX))
        ai       = sum(v for k, v in counts.items() if any(s in k for s in _AI_SUBSTRINGS))
        security = sum(v for k, v in counts.items() if k in _SECURITY_TYPES)

        return {
            'total':           total,
            'login_events':    login,
            'tenant_events':   tenant,
            'ai_events':       ai,
            'security_events': security,
        }

    @staticmethod
    async def count(
        *,
        tenant_id: UUID | None = None,
        restrict_to_tenant: bool = False,
        event_type: str | None = None,
        actor_user_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        db: AsyncSession,
    ) -> int:
        clauses = AuditLogRepository._build_filters(
            tenant_id=tenant_id,
            restrict_to_tenant=restrict_to_tenant,
            event_type=event_type,
            actor_user_id=actor_user_id,
            date_from=date_from,
            date_to=date_to,
        )
        stmt = select(func.count(AuditLog.id))
        if clauses:
            stmt = stmt.where(and_(*clauses))
        result = await db.execute(stmt)
        return result.scalar_one()
