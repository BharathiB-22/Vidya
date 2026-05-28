import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class SyllabusStatus(str, enum.Enum):
    DRAFT          = "DRAFT"
    AI_GENERATING  = "AI_GENERATING"
    PENDING_REVIEW = "PENDING_REVIEW"   # faculty submitted; awaiting Dean
    DEAN_APPROVED  = "DEAN_APPROVED"    # Dean approved
    DEAN_LOCKED    = "DEAN_LOCKED"      # frozen for semester


class BloomLevel(str, enum.Enum):
    REMEMBER   = "REMEMBER"
    UNDERSTAND = "UNDERSTAND"
    APPLY      = "APPLY"
    ANALYSE    = "ANALYSE"
    EVALUATE   = "EVALUATE"
    CREATE     = "CREATE"


class MappingStrength(str, enum.Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


class RefType(str, enum.Enum):
    TEXTBOOK  = "TEXTBOOK"
    REFERENCE = "REFERENCE"
    JOURNAL   = "JOURNAL"
    ONLINE    = "ONLINE"


class RefSource(str, enum.Enum):
    CROSSREF    = "CROSSREF"
    OPENLIBRARY = "OPENLIBRARY"
    MANUAL      = "MANUAL"


class Syllabus(Base):
    __tablename__ = "syllabi"
    __table_args__ = (
        Index("ix_syllabi_course",          "course_id"),
        Index("ix_syllabi_course_version",  "course_id", "version"),
        Index("ix_syllabi_status",          "status"),
        Index("ix_syllabi_created_by",      "created_by_user_id"),
        Index("ix_syllabi_parent_version",  "parent_version_id"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id           = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    version             = Column(Integer, nullable=False, default=1)
    parent_version_id   = Column(UUID(as_uuid=True), ForeignKey("syllabi.id"), nullable=True)
    status              = Column(
        Enum(SyllabusStatus, native_enum=False),
        nullable=False,
        default=SyllabusStatus.DRAFT,
    )
    custom_instructions = Column(Text, nullable=True)
    change_note         = Column(Text, nullable=True)
    ai_model            = Column(String, nullable=True)
    prompt_hash         = Column(String, nullable=True)
    created_by_user_id  = Column(UUID(as_uuid=True), nullable=False)
    approved_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    approved_at         = Column(DateTime(timezone=True), nullable=True)
    locked_by_user_id   = Column(UUID(as_uuid=True), nullable=True)
    locked_at           = Column(DateTime(timezone=True), nullable=True)
    created_at          = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at          = Column(DateTime(timezone=True), nullable=True)

    parent_version = relationship(
        "Syllabus",
        remote_side=[id],
        foreign_keys=[parent_version_id],
    )
    outcomes    = relationship("CourseOutcome",    back_populates="syllabus", cascade="all, delete-orphan")
    units       = relationship("SyllabusUnit",     back_populates="syllabus", cascade="all, delete-orphan")
    references  = relationship("SyllabusReference", back_populates="syllabus", cascade="all, delete-orphan")


class CourseOutcome(Base):
    __tablename__ = "course_outcomes"
    __table_args__ = (
        UniqueConstraint("syllabus_id", "code"),
        Index("ix_course_outcomes_syllabus", "syllabus_id"),
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_id   = Column(UUID(as_uuid=True), ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False)
    code          = Column(String, nullable=False)
    description   = Column(Text, nullable=False)
    bloom_level   = Column(
        Enum(BloomLevel, native_enum=False),
        nullable=False,
    )
    display_order = Column(Integer, nullable=False, default=0)
    created_at    = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at    = Column(DateTime(timezone=True), nullable=True)

    syllabus = relationship("Syllabus", back_populates="outcomes")
    mappings = relationship("COPOMapping", back_populates="outcome", cascade="all, delete-orphan")


class COPOMapping(Base):
    __tablename__ = "co_po_mappings"
    __table_args__ = (
        UniqueConstraint("co_id", "po_id"),
        Index("ix_co_po_mappings_co",  "co_id"),
        Index("ix_co_po_mappings_po",  "po_id"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    co_id            = Column(UUID(as_uuid=True), ForeignKey("course_outcomes.id", ondelete="CASCADE"), nullable=False)
    po_id            = Column(UUID(as_uuid=True), ForeignKey("program_outcomes.id", ondelete="CASCADE"), nullable=False)
    mapping_strength = Column(
        Enum(MappingStrength, native_enum=False),
        nullable=False,
        default=MappingStrength.MEDIUM,
    )
    justification    = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    outcome = relationship("CourseOutcome", back_populates="mappings")


class SyllabusUnit(Base):
    __tablename__ = "syllabus_units"
    __table_args__ = (
        UniqueConstraint("syllabus_id", "unit_number"),
        Index("ix_syllabus_units_syllabus", "syllabus_id"),
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_id   = Column(UUID(as_uuid=True), ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False)
    unit_number   = Column(Integer, nullable=False)
    title         = Column(String, nullable=False)
    topics        = Column(JSONB, nullable=False, server_default="[]")
    total_hours   = Column(Integer, nullable=False)
    pedagogy      = Column(String, nullable=True)
    bloom_summary = Column(JSONB, nullable=True)
    created_at    = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at    = Column(DateTime(timezone=True), nullable=True)

    syllabus = relationship("Syllabus", back_populates="units")


class SyllabusReference(Base):
    __tablename__ = "syllabus_references"
    __table_args__ = (
        Index("ix_syllabus_references_syllabus", "syllabus_id"),
        Index("ix_syllabus_references_source",   "source"),
    )

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_id  = Column(UUID(as_uuid=True), ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False)
    title        = Column(Text, nullable=False)
    authors      = Column(JSONB, nullable=False, server_default="[]")
    year         = Column(Integer, nullable=True)
    ref_type     = Column(
        Enum(RefType, native_enum=False),
        nullable=False,
        default=RefType.TEXTBOOK,
    )
    source       = Column(
        Enum(RefSource, native_enum=False),
        nullable=False,
        default=RefSource.MANUAL,
    )
    doi          = Column(String, nullable=True)
    isbn         = Column(String, nullable=True)
    url          = Column(Text, nullable=True)
    publisher    = Column(String, nullable=True)
    is_confirmed = Column(Boolean, nullable=False, default=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at   = Column(DateTime(timezone=True), nullable=True)

    syllabus = relationship("Syllabus", back_populates="references")
