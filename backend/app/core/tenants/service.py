from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.models import TenantStatus
from app.core.auth.security import hash_password
from app.core.tenants.provisioner import (
    derive_schema_name,
    generate_slug,
    run_tenant_migrations,
    seed_admin_user,
)
from app.core.tenants.repository import TenantRepository
from app.core.tenants.schemas import CreateTenantRequest, TenantResponse, TenantUpdateRequest


class TenantError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class TenantService:

    @staticmethod
    async def create_tenant(
        body: CreateTenantRequest,
        db: AsyncSession,
    ) -> TenantResponse:
        slug = generate_slug(body.name)

        existing = await TenantRepository.get_tenant_by_slug(slug, db)
        if existing is not None:
            raise TenantError(
                "SLUG_CONFLICT",
                f"A tenant with slug '{slug}' already exists. "
                "Try a more specific institution name.",
                409,
            )

        schema_name = derive_schema_name(slug)

        # Commit PROVISIONING record before running migrations so the row is
        # visible even if provisioning fails (enables retry / investigation).
        async with db.begin():
            tenant = await TenantRepository.create_tenant(
                name=body.name,
                slug=slug,
                schema_name=schema_name,
                db=db,
            )

        tenant_id = tenant.id

        try:
            await run_tenant_migrations(schema_name)

            # bcrypt is synchronous and intentionally slow; acceptable here
            # because tenant provisioning is a rare, non-hot-path operation.
            pw_hash = hash_password(body.admin_password)
            await seed_admin_user(
                schema_name=schema_name,
                email=body.admin_email,
                password_hash=pw_hash,
                full_name=body.admin_full_name,
            )

            async with db.begin():
                tenant = await TenantRepository.update_tenant(
                    tenant_id,
                    {"status": TenantStatus.ACTIVE, "is_active": True},
                    db,
                )

        except TenantError:
            raise

        except Exception as exc:
            async with db.begin():
                await TenantRepository.update_tenant(
                    tenant_id,
                    {"status": TenantStatus.FAILED},
                    db,
                )
            raise TenantError(
                "PROVISIONING_FAILED",
                f"Tenant record created but schema provisioning failed: {exc}",
                500,
            ) from exc

        return TenantResponse.model_validate(tenant)

    @staticmethod
    async def list_tenants(
        db: AsyncSession,
        include_inactive: bool = True,
    ) -> list[TenantResponse]:
        tenants = await TenantRepository.list_tenants(db, include_inactive=include_inactive)
        return [TenantResponse.model_validate(t) for t in tenants]

    @staticmethod
    async def get_tenant(tenant_id: UUID, db: AsyncSession) -> TenantResponse:
        tenant = await TenantRepository.get_tenant_by_id(tenant_id, db)
        if tenant is None:
            raise TenantError("NOT_FOUND", "Tenant not found", 404)
        return TenantResponse.model_validate(tenant)

    @staticmethod
    async def update_tenant(
        tenant_id: UUID,
        body: TenantUpdateRequest,
        db: AsyncSession,
    ) -> TenantResponse:
        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise TenantError("NO_FIELDS", "No fields to update", 422)

        async with db.begin():
            tenant = await TenantRepository.update_tenant(tenant_id, updates, db)

        if tenant is None:
            raise TenantError("NOT_FOUND", "Tenant not found", 404)

        return TenantResponse.model_validate(tenant)
