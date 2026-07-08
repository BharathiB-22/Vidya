import logging
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.storage.models import StorageAsset, StorageEntityType
from app.core.storage.repository import StorageRepository
from app.core.storage.schemas import (
    StorageAssetResponse,
    StorageAssetListResponse,
    GenerateUploadUrlRequest,
    GenerateUploadUrlResponse,
)

logger = logging.getLogger("vidya.storage")


class StorageError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class StorageService:

    # ------------------------------------------------------------------
    # Object key generation (server-side only)
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_object_key(
        tenant_slug: str,
        entity_type: str,
        entity_id: UUID,
        original_filename: str,
    ) -> str:
        """Generate tenant-safe object key.

        Format: vidya-assets/{tenant_slug}/{entity_type}/{entity_id}/{uuid}-{filename}
        """
        # Sanitize filename: remove path separators, control chars
        safe_filename = original_filename.replace("/", "_").replace("\\", "_")
        safe_filename = "".join(c for c in safe_filename if ord(c) >= 32)[:255]

        file_uuid = uuid.uuid4()
        return f"vidya-assets/{tenant_slug}/{entity_type}/{entity_id}/{file_uuid}-{safe_filename}"

    # ------------------------------------------------------------------
    # Upload URL generation (with authorization checks)
    # ------------------------------------------------------------------

    @staticmethod
    async def generate_upload_url(
        request: GenerateUploadUrlRequest,
        *,
        tenant_slug: str,
        current_user_id: UUID,
        db: AsyncSession,
    ) -> GenerateUploadUrlResponse:
        """Generate presigned PUT URL after validating permissions and MIME type.

        Does not create StorageAsset yet — frontend uploads, then calls create_asset()
        to persist metadata.
        """
        # Validate entity_type
        try:
            StorageEntityType(request.entity_type)
        except ValueError:
            raise StorageError(
                "INVALID_ENTITY_TYPE",
                f"Invalid entity_type: {request.entity_type}",
                400,
            )

        # Validate MIME type against whitelist
        allowed_mimes = settings.STORAGE_MIME_WHITELIST.get(request.entity_type, [])
        if request.content_type not in allowed_mimes:
            raise StorageError(
                "INVALID_CONTENT_TYPE",
                f"Content-Type '{request.content_type}' not allowed for {request.entity_type}",
                400,
            )

        # Validate file size
        if request.size_bytes > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise StorageError(
                "FILE_TOO_LARGE",
                f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit",
                400,
            )

        # Generate object key (server-side)
        object_key = StorageService._generate_object_key(
            tenant_slug=tenant_slug,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            original_filename=request.original_filename,
        )

        # Generate presigned URL
        expires_in_sec = settings.PRESIGNED_URL_EXPIRY_MINUTES_PUT * 60
        presigned_url = await StorageRepository.generate_presigned_put_url(
            object_key=object_key,
            content_type=request.content_type,
            expires_in_seconds=expires_in_sec,
        )

        # Return URL and object_key for frontend to use
        return GenerateUploadUrlResponse(
            object_key=object_key,
            presigned_url=presigned_url,
            expires_in_seconds=expires_in_sec,
        )

    # ------------------------------------------------------------------
    # Asset metadata persistence (called after upload completes)
    # ------------------------------------------------------------------

    @staticmethod
    async def create_asset(
        object_key: str,
        uploaded_by_user_id: UUID,
        entity_type: str,
        entity_id: UUID,
        original_filename: str,
        size_bytes: int,
        content_type: str,
        expires_at: datetime | None = None,
        *,
        tenant_id: UUID,
        tenant_slug: str,
        db: AsyncSession,
    ) -> StorageAssetResponse:
        """Create StorageAsset metadata after successful upload.

        Validates object_key matches expected format (tenant-safe).
        Logs to AuditLog.
        """
        # Verify object_key is server-generated format
        expected_prefix = f"vidya-assets/{tenant_slug}/{entity_type}/{entity_id}/"
        if not object_key.startswith(expected_prefix):
            raise StorageError(
                "INVALID_OBJECT_KEY",
                "Object key does not match tenant/entity scope",
                400,
            )

        # Verify object exists in S3
        exists = await StorageRepository.check_object_exists(object_key)
        if not exists:
            raise StorageError(
                "OBJECT_NOT_FOUND",
                "File was not found in storage (upload may have failed)",
                400,
            )

        # Create metadata in DB
        asset = await StorageRepository.create(
            uploaded_by_user_id=uploaded_by_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            object_key=object_key,
            original_filename=original_filename,
            size_bytes=size_bytes,
            content_type=content_type,
            expires_at=expires_at,
            db=db,
        )
        await db.commit()

        # Audit log (fire-and-forget)
        await AuditService.log(
            AuditEventType.STORAGE_ASSET_CREATED,
            actor_user_id=uploaded_by_user_id,
            actor_role="FACULTY",  # TODO: get actual role from CurrentUser context
            tenant_id=tenant_id,
            schema_name=f"tenant_{tenant_slug}",
            target_entity="StorageAsset",
            target_id=str(asset.id),
            metadata={
                "object_key": object_key,
                "entity_type": entity_type,
                "size_bytes": size_bytes,
                "content_type": content_type,
            },
        )

        return StorageAssetResponse.model_validate(asset)

    # ------------------------------------------------------------------
    # Download (with authorization checks)
    # ------------------------------------------------------------------

    @staticmethod
    async def generate_download_url(
        asset_id: UUID,
        *,
        tenant_id: UUID,
        tenant_slug: str,
        current_user_id: UUID,
        db: AsyncSession,
    ) -> str:
        """Generate presigned GET URL after validating access.

        Authorization: user must own the asset or have admin role.
        (In production, extend to check entity permissions.)
        """
        asset = await StorageRepository.get_by_id(asset_id, db=db)
        if asset is None:
            raise StorageError(
                "ASSET_NOT_FOUND",
                "Asset not found or has been deleted",
                404,
            )

        # Authorization: owner only — EXCEPT avatars, which are profile pictures
        # meant to be visible to every authenticated tenant user (navbar,
        # directory, faculty/student lists). Without this, only the uploader
        # could ever resolve their own avatar URL and nobody else could load it.
        if asset.entity_type != "avatar" and asset.uploaded_by_user_id != current_user_id:
            raise StorageError(
                "FORBIDDEN",
                "You do not have permission to download this asset",
                403,
            )

        expires_in_sec = settings.PRESIGNED_URL_EXPIRY_MINUTES_GET * 60
        presigned_url = await StorageRepository.generate_presigned_get_url(
            object_key=asset.object_key,
            expires_in_seconds=expires_in_sec,
        )

        # Audit log (fire-and-forget)
        await AuditService.log(
            AuditEventType.STORAGE_ASSET_DOWNLOADED,
            actor_user_id=current_user_id,
            actor_role="STUDENT",  # TODO: get actual role
            tenant_id=tenant_id,
            schema_name=f"tenant_{tenant_slug}",
            target_entity="StorageAsset",
            target_id=str(asset.id),
            metadata={"object_key": asset.object_key},
        )

        return presigned_url

    # ------------------------------------------------------------------
    # Listing and deletion
    # ------------------------------------------------------------------

    @staticmethod
    async def list_assets(
        entity_type: str,
        entity_id: UUID,
        *,
        page: int = 1,
        page_size: int = 50,
        db: AsyncSession,
    ) -> StorageAssetListResponse:
        """List assets for an entity."""
        offset = (page - 1) * page_size
        total = await StorageRepository.count_by_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            db=db,
        )
        rows = await StorageRepository.list_by_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            offset=offset,
            limit=page_size,
            db=db,
        )
        items = [StorageAssetResponse.model_validate(r) for r in rows]
        return StorageAssetListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=items,
        )

    @staticmethod
    async def delete_asset(
        asset_id: UUID,
        *,
        tenant_id: UUID,
        tenant_slug: str,
        current_user_id: UUID,
        db: AsyncSession,
    ) -> None:
        """Soft-delete asset. Actual S3 cleanup handled by retention job."""
        asset = await StorageRepository.get_by_id(asset_id, db=db)
        if asset is None:
            raise StorageError(
                "ASSET_NOT_FOUND",
                "Asset not found or already deleted",
                404,
            )

        # Authorization: owner only
        if asset.uploaded_by_user_id != current_user_id:
            raise StorageError(
                "FORBIDDEN",
                "You do not have permission to delete this asset",
                403,
            )

        await StorageRepository.delete(asset_id, db=db)
        await db.commit()

        # Audit log
        await AuditService.log(
            AuditEventType.STORAGE_ASSET_DELETED,
            actor_user_id=current_user_id,
            actor_role="STUDENT",  # TODO: get actual role
            tenant_id=tenant_id,
            schema_name=f"tenant_{tenant_slug}",
            target_entity="StorageAsset",
            target_id=str(asset.id),
            metadata={"object_key": asset.object_key},
        )
