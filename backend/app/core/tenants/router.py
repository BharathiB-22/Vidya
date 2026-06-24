from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import require_super_admin
from app.core.auth.schemas import CurrentUser
from app.database import get_db
from app.config import settings as app_settings
from app.core.tenants.schemas import (
    CreateTenantRequest,
    DeleteTenantRequest,
    PermanentDeleteTenantRequest,
    PlatformSettingsResponse,
    PlatformStatsResponse,
    TenantMigrationResult,
    TenantMigrationStatus,
    TenantResponse,
    TenantUpdateRequest,
)
from app.core.tenants.repository import TenantRepository
from app.core.tenants.service import TenantError, TenantService

router = APIRouter(tags=["tenants"])


def _tenant_error(e: TenantError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


@router.post("", response_model=TenantResponse, status_code=201)
async def create_tenant(
    request: Request,
    body: CreateTenantRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.create_tenant(
            body,
            db,
            actor_user_id=current_user.user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except TenantError as e:
        raise _tenant_error(e)


@router.get("", response_model=list[TenantResponse])
async def list_tenants(
    include_inactive: bool = True,
    _: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> list[TenantResponse]:
    return await TenantService.list_tenants(db, include_inactive=include_inactive)


@router.get("/platform-stats", response_model=PlatformStatsResponse)
async def get_platform_stats(
    _: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformStatsResponse:
    return await TenantService.get_platform_stats(db)


@router.get("/platform-settings", response_model=PlatformSettingsResponse)
async def get_platform_settings(
    _: CurrentUser = Depends(require_super_admin),
) -> PlatformSettingsResponse:
    is_minio = (
        "minio" in app_settings.S3_ENDPOINT.lower()
        or "localhost" in app_settings.S3_ENDPOINT
        or "127.0.0.1" in app_settings.S3_ENDPOINT
    )
    return PlatformSettingsResponse(
        platform_name="VIDYA AI",
        company_name="SherpaVector",
        support_email=app_settings.SMTP_FROM,
        environment=app_settings.ENVIRONMENT,
        build_version="H44",
        ai_provider=app_settings.AI_PROVIDER,
        gemini_configured=bool(app_settings.GEMINI_API_KEY),
        gemini_model=app_settings.GEMINI_MODEL,
        gemini_enabled=app_settings.AI_GEMINI_ENABLED,
        groq_configured=bool(app_settings.GROQ_API_KEY),
        groq_model=app_settings.GROQ_MODEL,
        groq_enabled=app_settings.AI_GROQ_ENABLED,
        deepseek_configured=bool(app_settings.DEEPSEEK_API_KEY),
        deepseek_model=app_settings.DEEPSEEK_MODEL,
        deepseek_enabled=app_settings.AI_DEEPSEEK_ENABLED,
        storage_provider="MinIO" if is_minio else "AWS S3",
        s3_endpoint=app_settings.S3_ENDPOINT,
        s3_bucket=app_settings.S3_BUCKET,
        s3_region=app_settings.S3_REGION,
        s3_use_ssl=app_settings.S3_USE_SSL,
        max_upload_mb=app_settings.MAX_UPLOAD_SIZE_MB,
        smtp_host=app_settings.SMTP_HOST,
        smtp_from=app_settings.SMTP_FROM,
        email_enabled=app_settings.EMAIL_NOTIFICATIONS_ENABLED,
        jwt_enabled=True,
        rbac_enabled=True,
        tenant_isolation=True,
        audit_logging_enabled=True,
        soft_delete_enabled=True,
        access_token_expire_minutes=app_settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        refresh_token_expire_days=app_settings.REFRESH_TOKEN_EXPIRE_DAYS,
    )


@router.get("/migrations", response_model=list[TenantMigrationStatus])
async def list_tenant_migration_status(
    _: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> list[TenantMigrationStatus]:
    """Return schema migration status for every non-deleted tenant."""
    from app.core.tenants.migration_runner import get_all_migration_status
    rows = await get_all_migration_status(db)
    return [TenantMigrationStatus(**r) for r in rows]


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    _: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.get_tenant(tenant_id, db)
    except TenantError as e:
        raise _tenant_error(e)


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    request: Request,
    tenant_id: UUID,
    body: TenantUpdateRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.update_tenant(
            tenant_id,
            body,
            db,
            actor_user_id=current_user.user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except TenantError as e:
        raise _tenant_error(e)


@router.delete("/{tenant_id}", response_model=TenantResponse)
async def delete_tenant(
    request: Request,
    tenant_id: UUID,
    body: DeleteTenantRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.delete_tenant(
            tenant_id,
            body.confirm_slug,
            db,
            actor_user_id=current_user.user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except TenantError as e:
        raise _tenant_error(e)


@router.post("/{tenant_id}/retry", response_model=TenantResponse)
async def retry_tenant_provisioning(
    request: Request,
    tenant_id: UUID,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.retry_provisioning(
            tenant_id,
            db,
            actor_user_id=current_user.user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except TenantError as e:
        raise _tenant_error(e)


@router.post("/{tenant_id}/restore", response_model=TenantResponse)
async def restore_tenant(
    request: Request,
    tenant_id: UUID,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.restore_tenant(
            tenant_id,
            db,
            actor_user_id=current_user.user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except TenantError as e:
        raise _tenant_error(e)


# ---------------------------------------------------------------------------
# Tenant migration retry
# ---------------------------------------------------------------------------

@router.post("/{tenant_id}/migrations/retry", response_model=TenantMigrationResult)
async def retry_tenant_migration(
    tenant_id: UUID,
    _: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantMigrationResult:
    """Immediately run pending migrations for a single tenant schema."""
    from app.core.tenants.migration_runner import migrate_tenant
    tenant = await TenantRepository.get_tenant_by_id(tenant_id, db)
    if not tenant:
        raise HTTPException(404, detail={"error": "NOT_FOUND", "message": "Tenant not found"})
    result = await migrate_tenant(tenant.schema_name, tenant_id=tenant_id)
    return TenantMigrationResult(**result)


@router.delete("/{tenant_id}/permanent", response_model=TenantResponse)
async def permanently_delete_tenant(
    request: Request,
    tenant_id: UUID,
    body: PermanentDeleteTenantRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.permanently_delete_tenant(
            tenant_id,
            body.confirm_slug,
            db,
            actor_user_id=current_user.user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except TenantError as e:
        raise _tenant_error(e)
