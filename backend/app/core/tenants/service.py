import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
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

logger = logging.getLogger("vidya.tenants")

_WELCOME_SUBJECT = "Welcome to Vidya — Your institution is live"
_WELCOME_BODY = (
    "Your Vidya institution account has been provisioned and is ready to use.\n\n"
    "Log in at your institution's Vidya URL with the admin credentials that were "
    "set during provisioning.\n\n"
    "If you did not request this account, please contact support immediately."
)


class TenantError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _dispatch_welcome_email(contact_email: str) -> None:
    """Fire-and-forget welcome email via Celery. Never raises."""
    try:
        from app.workers.tasks.send_email import send_email
        send_email.apply_async(
            kwargs={
                "recipient_email": contact_email,
                "subject": _WELCOME_SUBJECT,
                "body_text": _WELCOME_BODY,
            }
        )
    except Exception:
        logger.exception("welcome_email_dispatch_failed recipient=%s", contact_email)


class TenantService:

    @staticmethod
    async def create_tenant(
        body: CreateTenantRequest,
        db: AsyncSession,
        actor_user_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
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
        contact_email = str(body.contact_email) if body.contact_email else str(body.admin_email)

        # Commit PROVISIONING record before running migrations so the row is
        # visible even if provisioning fails (enables retry / investigation).
        tenant = await TenantRepository.create_tenant(
            name=body.name,
            slug=slug,
            schema_name=schema_name,
            db=db,
            contact_email=contact_email,
            logo_url=body.logo_url,
            primary_color=body.primary_color,
            secondary_color=body.secondary_color,
        )
        await db.commit()

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

            tenant = await TenantRepository.update_tenant(
                tenant_id,
                {"status": TenantStatus.ACTIVE, "is_active": True},
                db,
            )
            await db.commit()
            await AuditService.log(
                AuditEventType.TENANT_PROVISIONED,
                actor_user_id=actor_user_id,
                actor_role="SUPER_ADMIN",
                tenant_id=tenant.id,
                schema_name=tenant.schema_name,
                target_entity="Tenant",
                target_id=str(tenant.id),
                metadata={"name": tenant.name, "slug": tenant.slug},
                ip_address=ip_address,
                user_agent=user_agent,
            )

            _dispatch_welcome_email(contact_email)

        except TenantError:
            raise

        except Exception as exc:
            await db.rollback()
            await TenantRepository.update_tenant(
                tenant_id,
                {"status": TenantStatus.FAILED},
                db,
            )
            await db.commit()
            raise TenantError(
                "PROVISIONING_FAILED",
                f"Tenant record created but schema provisioning failed: {exc}",
                500,
            ) from exc

        return TenantResponse.model_validate(tenant)

    @staticmethod
    async def retry_provisioning(
        tenant_id: UUID,
        db: AsyncSession,
        actor_user_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TenantResponse:
        tenant = await TenantRepository.get_tenant_by_id(tenant_id, db)
        if tenant is None:
            raise TenantError("NOT_FOUND", "Tenant not found", 404)
        if tenant.status != TenantStatus.FAILED:
            raise TenantError(
                "INVALID_STATE",
                f"Retry is only allowed for tenants in FAILED state; current state: {tenant.status}",
                409,
            )

        schema_name = tenant.schema_name
        contact_email = tenant.contact_email

        await TenantRepository.update_tenant(
            tenant_id,
            {"status": TenantStatus.PROVISIONING},
            db,
        )
        await db.commit()

        try:
            await run_tenant_migrations(schema_name)

            tenant = await TenantRepository.update_tenant(
                tenant_id,
                {"status": TenantStatus.ACTIVE, "is_active": True},
                db,
            )
            await db.commit()
            await AuditService.log(
                AuditEventType.TENANT_PROVISIONED,
                actor_user_id=actor_user_id,
                actor_role="SUPER_ADMIN",
                tenant_id=tenant.id,
                schema_name=tenant.schema_name,
                target_entity="Tenant",
                target_id=str(tenant.id),
                metadata={"name": tenant.name, "slug": tenant.slug, "retry": True},
                ip_address=ip_address,
                user_agent=user_agent,
            )

            if contact_email:
                _dispatch_welcome_email(contact_email)

        except TenantError:
            raise

        except Exception as exc:
            await db.rollback()
            await TenantRepository.update_tenant(
                tenant_id,
                {"status": TenantStatus.FAILED},
                db,
            )
            await db.commit()
            raise TenantError(
                "PROVISIONING_FAILED",
                f"Retry provisioning failed: {exc}",
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
        actor_user_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TenantResponse:
        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise TenantError("NO_FIELDS", "No fields to update", 422)

        tenant = await TenantRepository.update_tenant(tenant_id, updates, db)
        await db.commit()

        if tenant is None:
            raise TenantError("NOT_FOUND", "Tenant not found", 404)

        event = (
            AuditEventType.TENANT_DEACTIVATED
            if updates.get("is_active") is False
            else AuditEventType.TENANT_UPDATED
        )
        await AuditService.log(
            event,
            actor_user_id=actor_user_id,
            actor_role="SUPER_ADMIN",
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            target_entity="Tenant",
            target_id=str(tenant_id),
            metadata={"changes": updates},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return TenantResponse.model_validate(tenant)
