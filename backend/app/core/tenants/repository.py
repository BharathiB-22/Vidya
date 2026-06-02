from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.models import Tenant, TenantStatus


class TenantRepository:

    @staticmethod
    async def create_tenant(
        name: str,
        slug: str,
        schema_name: str,
        db: AsyncSession,
        contact_email: str | None = None,
        logo_url: str | None = None,
        primary_color: str | None = None,
        secondary_color: str | None = None,
    ) -> Tenant:
        tenant = Tenant(
            name=name,
            slug=slug,
            schema_name=schema_name,
            status=TenantStatus.PROVISIONING,
            is_active=False,
            contact_email=contact_email,
            logo_url=logo_url,
            primary_color=primary_color,
            secondary_color=secondary_color,
        )
        db.add(tenant)
        await db.flush()
        await db.refresh(tenant)
        return tenant

    @staticmethod
    async def get_tenant_by_id(tenant_id: UUID, db: AsyncSession) -> Tenant | None:
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_tenant_by_slug(slug: str, db: AsyncSession) -> Tenant | None:
        stmt = select(Tenant).where(Tenant.slug == slug)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_tenants(
        db: AsyncSession,
        include_inactive: bool = True,
    ) -> list[Tenant]:
        # PERMANENTLY_DELETED tenants are always hidden — they are compliance
        # tombstones and must never surface in any listing or login flow.
        stmt = select(Tenant).where(Tenant.status != TenantStatus.PERMANENTLY_DELETED)
        if not include_inactive:
            stmt = stmt.where(Tenant.is_active.is_(True))
        stmt = stmt.order_by(Tenant.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_tenant(
        tenant_id: UUID,
        updates: dict,
        db: AsyncSession,
    ) -> Tenant | None:
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await db.execute(stmt)
        tenant = result.scalar_one_or_none()
        if tenant is None:
            return None
        for key, value in updates.items():
            setattr(tenant, key, value)
        await db.flush()
        await db.refresh(tenant)
        return tenant

    @staticmethod
    async def delete_tenant(
        tenant_id: UUID,
        deleted_by_user_id: UUID | None,
        db: AsyncSession,
    ) -> Tenant | None:
        return await TenantRepository.update_tenant(
            tenant_id,
            {
                "status": TenantStatus.DELETED,
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc),
                "deleted_by_user_id": deleted_by_user_id,
            },
            db,
        )

    @staticmethod
    async def restore_tenant(tenant_id: UUID, db: AsyncSession) -> Tenant | None:
        return await TenantRepository.update_tenant(
            tenant_id,
            {
                "status": TenantStatus.INACTIVE,
                "is_active": False,
                "deleted_at": None,
                "deleted_by_user_id": None,
            },
            db,
        )

    @staticmethod
    async def permanently_delete_tenant(tenant_id: UUID, db: AsyncSession) -> Tenant | None:
        # Compliance-safe: update status to PERMANENTLY_DELETED rather than issuing
        # a SQL DELETE, which would cascade an UPDATE onto audit_logs (blocked by
        # the append-only trigger on that table).
        return await TenantRepository.update_tenant(
            tenant_id,
            {"status": TenantStatus.PERMANENTLY_DELETED, "is_active": False},
            db,
        )
