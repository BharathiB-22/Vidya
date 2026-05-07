from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser, TenantInfo
from app.core.storage.schemas import (
    CreateAssetRequest,
    DownloadUrlResponse,
    GenerateUploadUrlRequest,
    GenerateUploadUrlResponse,
    StorageAssetListResponse,
)
from app.core.storage.service import StorageError, StorageService

router = APIRouter(tags=["storage"])

_ALL_TENANT_ROLES = (
    TenantRole.STUDENT,
    TenantRole.FACULTY,
    TenantRole.ADMIN,
    TenantRole.DEAN,
    TenantRole.BOARD,
    TenantRole.GUIDE,
)


def _storage_error(e: StorageError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


@router.post("/upload-url", response_model=GenerateUploadUrlResponse)
async def generate_upload_url(
    request: GenerateUploadUrlRequest,
    current_user: CurrentUser = Depends(require_roles(*_ALL_TENANT_ROLES)),
    tenant_info: TenantInfo = Depends(),  # Injected by resolve_tenant
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GenerateUploadUrlResponse:
    """Generate presigned PUT URL for file upload.

    Frontend receives URL and object_key, uploads file directly to MinIO/S3.
    """
    try:
        return await StorageService.generate_upload_url(
            request,
            tenant_slug=tenant_info.slug,
            current_user_id=current_user.user_id,
            db=db,
        )
    except StorageError as e:
        raise _storage_error(e)


@router.post("/assets", response_model=StorageAssetListResponse)
async def create_asset_metadata(
    request: CreateAssetRequest,
    current_user: CurrentUser = Depends(require_roles(*_ALL_TENANT_ROLES)),
    tenant_info: TenantInfo = Depends(),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> StorageAssetListResponse:
    """Persist asset metadata after successful upload.

    Frontend calls this after file is uploaded to S3 via presigned URL.
    Returns asset record.
    """
    try:
        asset = await StorageService.create_asset(
            object_key=request.object_key,
            uploaded_by_user_id=current_user.user_id,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            original_filename=request.original_filename,
            size_bytes=request.size_bytes,
            content_type=request.content_type,
            tenant_id=tenant_info.id,
            tenant_slug=tenant_info.slug,
            db=db,
        )
        return StorageAssetListResponse(
            total=1,
            page=1,
            page_size=1,
            items=[asset],
        )
    except StorageError as e:
        raise _storage_error(e)


@router.get("/{asset_id}/download-url", response_model=DownloadUrlResponse)
async def get_download_url(
    asset_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_ALL_TENANT_ROLES)),
    tenant_info: TenantInfo = Depends(),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> DownloadUrlResponse:
    """Get presigned GET URL for download (after authorization check).

    Does not expose raw object keys — URL is generated server-side.
    """
    try:
        presigned_url = await StorageService.generate_download_url(
            asset_id,
            tenant_id=tenant_info.id,
            tenant_slug=tenant_info.slug,
            current_user_id=current_user.user_id,
            db=db,
        )
        from app.config import settings

        expires_in_sec = settings.PRESIGNED_URL_EXPIRY_MINUTES_GET * 60
        return DownloadUrlResponse(
            presigned_url=presigned_url,
            expires_in_seconds=expires_in_sec,
        )
    except StorageError as e:
        raise _storage_error(e)


@router.get("", response_model=StorageAssetListResponse)
async def list_assets(
    entity_type: str = Query(..., description="submission|research_doc|course_kit|viva_recording"),
    entity_id: UUID = Query(..., description="UUID of entity"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    current_user: CurrentUser = Depends(require_roles(*_ALL_TENANT_ROLES)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> StorageAssetListResponse:
    """List assets for an entity (non-deleted only)."""
    try:
        return await StorageService.list_assets(
            entity_type=entity_type,
            entity_id=entity_id,
            page=page,
            page_size=page_size,
            db=db,
        )
    except StorageError as e:
        raise _storage_error(e)


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_ALL_TENANT_ROLES)),
    tenant_info: TenantInfo = Depends(),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    """Soft-delete asset (actual S3 cleanup via retention job)."""
    try:
        await StorageService.delete_asset(
            asset_id,
            tenant_id=tenant_info.id,
            tenant_slug=tenant_info.slug,
            current_user_id=current_user.user_id,
            db=db,
        )
        return {"status": "deleted"}
    except StorageError as e:
        raise _storage_error(e)
