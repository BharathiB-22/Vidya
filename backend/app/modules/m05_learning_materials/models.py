"""
M05 Learning Material Packager — SQLAlchemy models.

Tables (all tenant-schema, not public):
  learning_packages    — one per (syllabus_id, unit_number); versioned when syllabus bumps
  package_items        — one row per curated or faculty-added material
  package_qa_sessions  — one Q&A conversation per student per package
  package_qa_messages  — individual turns within a Q&A session

Tenant isolation: all tables live in the tenant schema (no schema= kwarg).
Qdrant isolation: tenant_schema + package_id are carried in every Qdrant payload (R1).

content_hash on package_items: SHA-256(normalize(url) + title + text_checksum)
  - deduplication on ingest
  - syllabus-bump diffing (skip unchanged items)
  - see R2 in TASK-013 plan

metadata JSONB reserved keys (Phase 2, do not implement now):
  difficulty_level, estimated_study_time, learning_style_tags
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float,
    ForeignKey, Index, Integer, String, Text, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PackageStatus(str, enum.Enum):
    PENDING  = "PENDING"    # created, curation not yet dispatched
    CURATING = "CURATING"   # Celery task running
    READY    = "READY"      # curation complete and RAG indexed
    OUTDATED = "OUTDATED"   # superseded by a newer syllabus version


class MaterialSourceType(str, enum.Enum):
    YOUTUBE      = "YOUTUBE"
    ARXIV        = "ARXIV"
    NPTEL        = "NPTEL"
    MIT_OCW      = "MIT_OCW"
    FACULTY_NOTE = "FACULTY_NOTE"   # faculty-uploaded text or PDF


class QARole(str, enum.Enum):
    USER      = "USER"
    ASSISTANT = "ASSISTANT"


# ---------------------------------------------------------------------------
# LearningPackage
# ---------------------------------------------------------------------------

class LearningPackage(Base):
    __tablename__ = "learning_packages"
    __table_args__ = (
        Index("ix_learning_packages_syllabus",      "syllabus_id"),
        Index("ix_learning_packages_syllabus_unit", "syllabus_id", "unit_number"),
        Index("ix_learning_packages_status",        "status"),
        Index("ix_learning_packages_created_by",    "created_by_user_id"),
    )

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # FK to M02 syllabi — reads syllabus unit context for embedding
    syllabus_id        = Column(
        UUID(as_uuid=True),
        ForeignKey("syllabi.id", ondelete="CASCADE"),
        nullable=False,
    )
    unit_number        = Column(Integer, nullable=False)
    # mirrors the syllabus.version at the time of curation; increments on re-curation
    version            = Column(Integer, nullable=False, default=1)
    status             = Column(
        Enum(PackageStatus, native_enum=False),
        nullable=False,
        default=PackageStatus.PENDING,
    )
    top_n              = Column(Integer, nullable=False, default=10)
    item_count         = Column(Integer, nullable=False, default=0)  # denormalized counter
    qdrant_indexed     = Column(Boolean, nullable=False, default=False)
    ai_model           = Column(String, nullable=True)
    prompt_hash        = Column(String, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    curated_at         = Column(DateTime(timezone=True), nullable=True)
    created_at         = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at         = Column(DateTime(timezone=True), nullable=True)

    items       = relationship(
        "PackageItem",
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="PackageItem.display_order",
    )
    qa_sessions = relationship(
        "PackageQASession",
        back_populates="package",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# PackageItem
# ---------------------------------------------------------------------------

class PackageItem(Base):
    __tablename__ = "package_items"
    __table_args__ = (
        Index("ix_package_items_package",      "package_id"),
        Index("ix_package_items_source_type",  "source_type"),
        # Dedup index (R2): fast lookup before ingest to skip already-indexed items
        Index("ix_package_items_content_hash", "package_id", "content_hash"),
        Index("ix_package_items_recommended",  "package_id", "faculty_recommended"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id          = Column(
        UUID(as_uuid=True),
        ForeignKey("learning_packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type         = Column(
        Enum(MaterialSourceType, native_enum=False),
        nullable=False,
    )
    title               = Column(String, nullable=False)
    url                 = Column(String, nullable=True)    # null for some faculty notes
    # SHA-256 of normalize(url) + title + extracted_text_checksum (R2)
    content_hash        = Column(String, nullable=True)
    # Current keys: thumbnail_url, authors, duration_seconds, arxiv_id,
    #               publish_date, abstract_snippet
    # Reserved (Phase 2): difficulty_level, estimated_study_time, learning_style_tags
    metadata_           = Column("metadata", JSONB, nullable=False, server_default="{}")
    relevance_score     = Column(Float, nullable=True)     # cosine sim vs unit embedding
    faculty_recommended = Column(Boolean, nullable=False, default=False)
    # null = AI-curated; set when faculty manually adds the item
    added_by_user_id    = Column(UUID(as_uuid=True), nullable=True)
    display_order       = Column(Integer, nullable=False, default=0)
    qdrant_indexed      = Column(Boolean, nullable=False, default=False)
    created_at          = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at          = Column(DateTime(timezone=True), nullable=True)

    package = relationship("LearningPackage", back_populates="items")


# ---------------------------------------------------------------------------
# PackageQASession
# ---------------------------------------------------------------------------

class PackageQASession(Base):
    __tablename__ = "package_qa_sessions"
    __table_args__ = (
        Index("ix_package_qa_sessions_package", "package_id"),
        # List all sessions for a student across a package
        Index("ix_package_qa_sessions_student", "package_id", "student_user_id"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id      = Column(
        UUID(as_uuid=True),
        ForeignKey("learning_packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_user_id = Column(UUID(as_uuid=True), nullable=False)
    created_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at      = Column(DateTime(timezone=True), nullable=True)

    package  = relationship("LearningPackage", back_populates="qa_sessions")
    messages = relationship(
        "PackageQAMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PackageQAMessage.created_at",
    )


# ---------------------------------------------------------------------------
# PackageQAMessage
# ---------------------------------------------------------------------------

class PackageQAMessage(Base):
    __tablename__ = "package_qa_messages"
    __table_args__ = (
        Index("ix_package_qa_messages_session",    "session_id"),
        Index("ix_package_qa_messages_session_ts", "session_id", "created_at"),
    )

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("package_qa_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role       = Column(Enum(QARole, native_enum=False), nullable=False)
    content    = Column(Text, nullable=False)
    # [{item_id, title, url, snippet, relevance_score}]
    sources    = Column(JSONB, nullable=False, server_default="[]")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    session = relationship("PackageQASession", back_populates="messages")
