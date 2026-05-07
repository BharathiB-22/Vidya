from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class GenerateUploadUrlRequest(BaseModel):
    entity_type: str = Field(..., description="submission|research_doc|course_kit|viva_recording")
    entity_id: UUID = Field(..., description="UUID of entity (submission, research doc, etc.)")
    original_filename: str = Field(..., description="Original filename for audit trail")
    content_type: str = Field(..., description="MIME type (must be whitelisted)")
    size_bytes: int = Field(..., ge=1, description="File size in bytes")


class GenerateUploadUrlResponse(BaseModel):
    object_key: str = Field(..., description="Server-generated S3 object key")
    presigned_url: str = Field(..., description="Presigned PUT URL (valid for 15 min)")
    expires_in_seconds: int = Field(..., description="URL expiry in seconds")


class CreateAssetRequest(BaseModel):
    object_key: str = Field(..., description="From GenerateUploadUrlResponse")
    entity_type: str
    entity_id: UUID
    original_filename: str
    content_type: str
    size_bytes: int


class StorageAssetResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    uploaded_by_user_id: UUID
    entity_type: str
    entity_id: UUID
    object_key: str
    original_filename: str
    size_bytes: int
    content_type: str
    created_at: datetime
    expires_at: Optional[datetime]
    deleted_at: Optional[datetime]


class DownloadUrlResponse(BaseModel):
    presigned_url: str = Field(..., description="Presigned GET URL (valid for 1 hour)")
    expires_in_seconds: int


class StorageAssetListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[StorageAssetResponse]
