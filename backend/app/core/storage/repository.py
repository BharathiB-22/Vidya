import asyncio
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.storage.models import StorageAsset, StorageEntityType


class StorageRepository:

    # Validates object_key format: vidya-assets/tenant_slug/entity_type/entity_id/uuid-filename
    # Entity type is validated against StorageEntityType enum in the service layer;
    # the regex only enforces structural safety (no traversal, no free-form segments).
    _KEY_PATTERN = re.compile(
        r"^vidya-assets/[a-z0-9_-]+/"
        r"[a-z0-9_]+"
        r"/[a-f0-9\-]{36}/[a-f0-9\-]{36}-[^/]+$"
    )

    @staticmethod
    def _validate_object_key(object_key: str) -> bool:
        """Reject keys that don't match expected format."""
        return bool(StorageRepository._KEY_PATTERN.match(object_key))

    @staticmethod
    def _get_s3_client():
        """Create S3 client (sync). Call via asyncio.to_thread()."""
        return boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            use_ssl=settings.S3_USE_SSL,
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        uploaded_by_user_id: UUID,
        entity_type: str,
        entity_id: UUID,
        object_key: str,
        original_filename: str,
        size_bytes: int,
        content_type: str,
        expires_at: datetime | None = None,
        *,
        db: AsyncSession,
    ) -> StorageAsset:
        """Create StorageAsset metadata. object_key must be server-generated."""
        if not StorageRepository._validate_object_key(object_key):
            raise ValueError(f"Invalid object_key format: {object_key}")

        asset = StorageAsset(
            uploaded_by_user_id=uploaded_by_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            object_key=object_key,
            original_filename=original_filename,
            size_bytes=size_bytes,
            content_type=content_type,
            expires_at=expires_at,
        )
        db.add(asset)
        await db.flush()
        await db.refresh(asset)
        return asset

    @staticmethod
    async def delete(
        asset_id: UUID,
        *,
        db: AsyncSession,
    ) -> StorageAsset | None:
        """Soft-delete: set deleted_at to now()."""
        stmt = select(StorageAsset).where(
            and_(
                StorageAsset.id == asset_id,
                StorageAsset.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        asset = result.scalar_one_or_none()
        if asset is None:
            return None
        asset.deleted_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(asset)
        return asset

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        asset_id: UUID,
        *,
        db: AsyncSession,
    ) -> StorageAsset | None:
        """Get asset by ID (non-deleted only)."""
        stmt = select(StorageAsset).where(
            and_(
                StorageAsset.id == asset_id,
                StorageAsset.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_object_key(
        object_key: str,
        *,
        db: AsyncSession,
    ) -> StorageAsset | None:
        """Internal lookup by object_key (non-deleted only)."""
        stmt = select(StorageAsset).where(
            and_(
                StorageAsset.object_key == object_key,
                StorageAsset.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_entity(
        entity_type: str,
        entity_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[StorageAsset]:
        """List all assets for an entity (non-deleted only)."""
        stmt = (
            select(StorageAsset)
            .where(
                and_(
                    StorageAsset.entity_type == entity_type,
                    StorageAsset.entity_id == entity_id,
                    StorageAsset.deleted_at.is_(None),
                )
            )
            .order_by(StorageAsset.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def count_by_entity(
        entity_type: str,
        entity_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        """Count assets for an entity (non-deleted only)."""
        from sqlalchemy import func

        stmt = select(func.count(StorageAsset.id)).where(
            and_(
                StorageAsset.entity_type == entity_type,
                StorageAsset.entity_id == entity_id,
                StorageAsset.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one()

    # ------------------------------------------------------------------
    # S3 Operations (presigned URLs, etc.)
    # ------------------------------------------------------------------

    @staticmethod
    async def generate_presigned_put_url(
        object_key: str,
        content_type: str,
        expires_in_seconds: int,
    ) -> str:
        """Generate presigned PUT URL for upload. object_key must be pre-validated."""
        if not StorageRepository._validate_object_key(object_key):
            raise ValueError(f"Invalid object_key format: {object_key}")

        loop = asyncio.get_event_loop()

        def _gen_put():
            client = StorageRepository._get_s3_client()
            url = client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.S3_BUCKET,
                    "Key": object_key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in_seconds,
            )
            return url

        return await loop.run_in_executor(None, _gen_put)

    @staticmethod
    async def generate_presigned_get_url(
        object_key: str,
        expires_in_seconds: int,
    ) -> str:
        """Generate presigned GET URL for download. object_key must be pre-validated."""
        if not StorageRepository._validate_object_key(object_key):
            raise ValueError(f"Invalid object_key format: {object_key}")

        loop = asyncio.get_event_loop()

        def _gen_get():
            client = StorageRepository._get_s3_client()
            url = client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.S3_BUCKET,
                    "Key": object_key,
                },
                ExpiresIn=expires_in_seconds,
            )
            return url

        return await loop.run_in_executor(None, _gen_get)

    @staticmethod
    async def delete_object(object_key: str) -> None:
        """Delete object from S3. Called by retention Celery job."""
        if not StorageRepository._validate_object_key(object_key):
            raise ValueError(f"Invalid object_key format: {object_key}")

        loop = asyncio.get_event_loop()

        def _delete():
            client = StorageRepository._get_s3_client()
            try:
                client.delete_object(Bucket=settings.S3_BUCKET, Key=object_key)
            except ClientError as e:
                if e.response["Error"]["Code"] != "NoSuchKey":
                    raise

        return await loop.run_in_executor(None, _delete)

    @staticmethod
    async def check_object_exists(object_key: str) -> bool:
        """Check if object exists in S3."""
        if not StorageRepository._validate_object_key(object_key):
            return False

        loop = asyncio.get_event_loop()

        def _check():
            client = StorageRepository._get_s3_client()
            try:
                client.head_object(Bucket=settings.S3_BUCKET, Key=object_key)
                return True
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    return False
                raise

        return await loop.run_in_executor(None, _check)
