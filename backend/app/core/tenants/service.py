import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
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
from app.core.tenants.schemas import (
    AIServiceInfo,
    AuditEventSummary,
    CreateTenantRequest,
    JobCounts,
    PlatformStatsResponse,
    ServiceHealthItem,
    TenantCounts,
    TenantResponse,
    TenantUpdateRequest,
)

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
    async def delete_tenant(
        tenant_id: UUID,
        confirm_slug: str,
        db: AsyncSession,
        actor_user_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TenantResponse:
        tenant = await TenantRepository.get_tenant_by_id(tenant_id, db)
        if tenant is None:
            raise TenantError("NOT_FOUND", "Tenant not found", 404)
        if tenant.slug != confirm_slug:
            raise TenantError(
                "SLUG_MISMATCH",
                "Confirmation slug does not match the tenant slug. "
                "Type the exact slug to confirm deletion.",
                409,
            )

        tenant = await TenantRepository.delete_tenant(tenant_id, db)
        await db.commit()

        await AuditService.log(
            AuditEventType.TENANT_DELETED,
            actor_user_id=actor_user_id,
            actor_role="SUPER_ADMIN",
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            target_entity="Tenant",
            target_id=str(tenant_id),
            metadata={"name": tenant.name, "slug": tenant.slug},
            ip_address=ip_address,
            user_agent=user_agent,
        )

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
        raw = body.model_dump(exclude_none=True)
        if not raw:
            raise TenantError("NO_FIELDS", "No fields to update", 422)

        updates: dict = {}

        # Metadata fields pass through directly
        for field in ("name", "contact_email", "logo_url", "primary_color", "secondary_color"):
            if field in raw:
                updates[field] = raw[field]

        # Status transition atomically drives is_active
        if "status" in raw:
            requested = raw["status"]
            updates["status"] = requested
            updates["is_active"] = requested == TenantStatus.ACTIVE
        elif "is_active" in raw:
            # Legacy deactivate path: keep status consistent
            updates["is_active"] = raw["is_active"]
            if not raw["is_active"]:
                updates["status"] = TenantStatus.INACTIVE

        tenant = await TenantRepository.update_tenant(tenant_id, updates, db)
        await db.commit()

        if tenant is None:
            raise TenantError("NOT_FOUND", "Tenant not found", 404)

        requested_status = raw.get("status")
        if requested_status == TenantStatus.ARCHIVED:
            event = AuditEventType.TENANT_ARCHIVED
        elif requested_status == TenantStatus.ACTIVE:
            event = AuditEventType.TENANT_REACTIVATED
        elif updates.get("is_active") is False:
            event = AuditEventType.TENANT_DEACTIVATED
        else:
            event = AuditEventType.TENANT_UPDATED

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

    @staticmethod
    async def get_platform_stats(db: AsyncSession) -> PlatformStatsResponse:
        from app.config import settings
        from app.core.monitoring.health import HealthService

        _LABELS = {
            "db":     "PostgreSQL",
            "redis":  "Redis",
            "s3":     "MinIO / S3",
            "qdrant": "Qdrant Vector DB",
        }

        # 1. Parallel health checks
        health_results, all_healthy = await HealthService.check_all()
        health = [
            ServiceHealthItem(
                service=r.service,
                label=_LABELS.get(r.service, r.service),
                status=r.status,
                latency_ms=round(r.latency_ms, 1),
                error_msg=r.error_msg,
            )
            for r in health_results
        ]

        # 2. Tenant counts (single query)
        trow = await db.execute(
            text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'ACTIVE')       AS active,
                    COUNT(*) FILTER (WHERE status = 'INACTIVE')     AS inactive,
                    COUNT(*) FILTER (WHERE status = 'ARCHIVED')     AS archived,
                    COUNT(*) FILTER (WHERE status = 'PROVISIONING') AS provisioning,
                    COUNT(*) FILTER (WHERE status = 'FAILED')       AS failed
                FROM public.tenants
                WHERE status != 'DELETED'
            """)
        )
        tc = trow.one()
        tenants = TenantCounts(
            total=tc.total or 0,
            active=tc.active or 0,
            inactive=tc.inactive or 0,
            archived=tc.archived or 0,
            provisioning=tc.provisioning or 0,
            failed=tc.failed or 0,
        )

        # 3. Job counts (single query)
        jrow = await db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'PENDING')  AS pending,
                    COUNT(*) FILTER (WHERE status = 'RUNNING')  AS running,
                    COUNT(*) FILTER (WHERE status = 'SUCCESS')  AS completed,
                    COUNT(*) FILTER (WHERE status = 'FAILED')   AS failed,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') AS total_24h
                FROM public.task_jobs
            """)
        )
        jc = jrow.one()
        jobs = JobCounts(
            pending=jc.pending or 0,
            running=jc.running or 0,
            completed=jc.completed or 0,
            failed=jc.failed or 0,
            total_24h=jc.total_24h or 0,
        )

        # 4. AI services
        active_provider = getattr(settings, "AI_PROVIDER", "groq")
        ai_services = [
            AIServiceInfo(
                name="Gemini",
                configured=bool(getattr(settings, "GEMINI_API_KEY", "")),
                model=getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash"),
                active=(active_provider == "gemini"),
            ),
            AIServiceInfo(
                name="Groq",
                configured=bool(getattr(settings, "GROQ_API_KEY", "")),
                model=getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"),
                active=(active_provider == "groq"),
            ),
        ]

        # 5. Recent platform-level audit events
        erows = await db.execute(
            text("""
                SELECT event_type, created_at, schema_name, metadata
                FROM public.audit_logs
                WHERE event_type LIKE 'TENANT_%'
                   OR event_type LIKE 'PLATFORM_LOGIN%'
                ORDER BY created_at DESC
                LIMIT 15
            """)
        )
        recent_events = [
            AuditEventSummary(
                event_type=r.event_type,
                created_at=r.created_at,
                schema_name=r.schema_name,
                metadata_=r.metadata,
            )
            for r in erows.fetchall()
        ]

        return PlatformStatsResponse(
            health=health,
            all_healthy=all_healthy,
            tenants=tenants,
            jobs=jobs,
            ai_services=ai_services,
            recent_events=recent_events,
            generated_at=datetime.now(timezone.utc),
        )
