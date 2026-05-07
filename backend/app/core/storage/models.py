import enum
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class StorageEntityType(str, enum.Enum):
    SUBMISSION = "submission"
    RESEARCH_DOC = "research_doc"
    COURSE_KIT = "course_kit"
    VIVA_RECORDING = "viva_recording"


class StorageAsset(Base):
    __tablename__ = "storage_assets"
    __table_args__ = (
        Index("ix_storage_assets_entity", "entity_type", "entity_id"),
        Index("ix_storage_assets_uploaded_by_created", "uploaded_by_user_id", "created_at"),
        Index("ix_storage_assets_created", "created_at"),
    )

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uploaded_by_user_id  = Column(UUID(as_uuid=True), nullable=False)
    entity_type          = Column(String, nullable=False)
    entity_id            = Column(UUID(as_uuid=True), nullable=False)
    object_key           = Column(Text, nullable=False, unique=True)
    original_filename    = Column(String, nullable=False)
    size_bytes           = Column(Integer, nullable=False)
    content_type         = Column(String, nullable=False)
    created_at           = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    expires_at           = Column(DateTime(timezone=True), nullable=True)
    deleted_at           = Column(DateTime(timezone=True), nullable=True)
