import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class CourseKitStatus(str, enum.Enum):
    DRAFT         = "DRAFT"
    AI_GENERATING = "AI_GENERATING"
    PUBLISHED     = "PUBLISHED"
    ARCHIVED      = "ARCHIVED"


class ComplexityLevel(str, enum.Enum):
    UG = "UG"
    PG = "PG"


class AssignmentType(str, enum.Enum):
    CLASSWORK  = "CLASSWORK"
    HOMEWORK   = "HOMEWORK"
    CASE_STUDY = "CASE_STUDY"


class BloomLevel(str, enum.Enum):
    REMEMBER   = "REMEMBER"
    UNDERSTAND = "UNDERSTAND"
    APPLY      = "APPLY"
    ANALYSE    = "ANALYSE"
    EVALUATE   = "EVALUATE"
    CREATE     = "CREATE"


class CourseKit(Base):
    __tablename__ = "course_kits"
    __table_args__ = (
        Index("ix_course_kits_syllabus",       "syllabus_id"),
        Index("ix_course_kits_syllabus_unit",  "syllabus_id", "unit_number"),
        Index("ix_course_kits_status",         "status"),
        Index("ix_course_kits_created_by",     "created_by_user_id"),
        Index("ix_course_kits_parent_version", "parent_version_id"),
    )

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_id          = Column(UUID(as_uuid=True), ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False)
    unit_number          = Column(Integer, nullable=False)
    version              = Column(Integer, nullable=False, default=1)
    parent_version_id    = Column(UUID(as_uuid=True), ForeignKey("course_kits.id"), nullable=True)
    status               = Column(
        Enum(CourseKitStatus, native_enum=False),
        nullable=False,
        default=CourseKitStatus.DRAFT,
    )
    complexity_level     = Column(
        Enum(ComplexityLevel, native_enum=False),
        nullable=False,
        default=ComplexityLevel.UG,
    )
    tone                 = Column(String, nullable=True)
    custom_instructions  = Column(Text, nullable=True)
    teaching_plan        = Column(JSONB, nullable=False, server_default="[]")
    lesson_plans         = Column(JSONB, nullable=False, server_default="[]")
    resources            = Column(JSONB, nullable=False, server_default="[]")
    ai_model             = Column(String, nullable=True)
    prompt_hash          = Column(String, nullable=True)
    created_by_user_id   = Column(UUID(as_uuid=True), nullable=False)
    published_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    published_at         = Column(DateTime(timezone=True), nullable=True)
    created_at           = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at           = Column(DateTime(timezone=True), nullable=True)

    parent_version = relationship(
        "CourseKit",
        remote_side=[id],
        foreign_keys=[parent_version_id],
    )
    slides      = relationship("KitSlide",      back_populates="kit", cascade="all, delete-orphan")
    assignments = relationship("KitAssignment", back_populates="kit", cascade="all, delete-orphan")


class KitSlide(Base):
    __tablename__ = "kit_slides"
    __table_args__ = (
        UniqueConstraint("kit_id", "slide_number"),
        Index("ix_kit_slides_kit", "kit_id"),
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kit_id        = Column(UUID(as_uuid=True), ForeignKey("course_kits.id", ondelete="CASCADE"), nullable=False)
    slide_number  = Column(Integer, nullable=False)
    title         = Column(String, nullable=False)
    content       = Column(JSONB, nullable=False, server_default="{}")
    speaker_notes = Column(Text, nullable=True)
    bloom_level   = Column(Enum(BloomLevel, native_enum=False), nullable=True)
    co_reference  = Column(String, nullable=True)
    created_at    = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at    = Column(DateTime(timezone=True), nullable=True)

    kit = relationship("CourseKit", back_populates="slides")


class KitAssignment(Base):
    __tablename__ = "kit_assignments"
    __table_args__ = (
        UniqueConstraint("kit_id", "assignment_number"),
        Index("ix_kit_assignments_kit", "kit_id"),
    )

    id                    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kit_id                = Column(UUID(as_uuid=True), ForeignKey("course_kits.id", ondelete="CASCADE"), nullable=False)
    assignment_number     = Column(Integer, nullable=False)
    title                 = Column(String, nullable=False)
    assignment_type       = Column(
        Enum(AssignmentType, native_enum=False),
        nullable=False,
        default=AssignmentType.CLASSWORK,
    )
    question_text         = Column(Text, nullable=False)
    complexity_level      = Column(
        Enum(ComplexityLevel, native_enum=False),
        nullable=False,
        default=ComplexityLevel.UG,
    )
    current_events_toggle = Column(Boolean, nullable=False, default=False)
    model_answer          = Column(Text, nullable=True)
    rubric                = Column(JSONB, nullable=False, server_default="[]")
    bloom_level           = Column(Enum(BloomLevel, native_enum=False), nullable=True)
    co_reference          = Column(String, nullable=True)
    created_at            = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at            = Column(DateTime(timezone=True), nullable=True)

    kit = relationship("CourseKit", back_populates="assignments")
