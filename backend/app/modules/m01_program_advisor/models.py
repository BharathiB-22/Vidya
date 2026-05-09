import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class ProgramStatus(str, enum.Enum):
    DRAFT             = "DRAFT"
    AI_GENERATING     = "AI_GENERATING"
    PENDING_APPROVAL  = "PENDING_APPROVAL"
    APPROVED          = "APPROVED"


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (
        Index("ix_programs_status",         "status"),
        Index("ix_programs_created_by",     "created_by_user_id"),
        Index("ix_programs_parent_version", "parent_version_id"),
        Index("ix_programs_created_at",     "created_at"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version             = Column(Integer, nullable=False, default=1)
    parent_version_id   = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=True)
    title               = Column(String, nullable=False)
    degree_type         = Column(String, nullable=False)
    department          = Column(String, nullable=False)
    duration_years      = Column(Integer, nullable=False)
    total_credits       = Column(Integer, nullable=False)
    status              = Column(
        Enum(ProgramStatus, native_enum=False),
        nullable=False,
        default=ProgramStatus.DRAFT,
    )
    ai_model            = Column(String, nullable=True)
    prompt_hash         = Column(String, nullable=True)
    approved_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    approved_at         = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id  = Column(UUID(as_uuid=True), nullable=False)
    created_at          = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at          = Column(DateTime(timezone=True), nullable=True)

    parent_version = relationship(
        "Program",
        remote_side=[id],
        foreign_keys=[parent_version_id],
    )
    outcomes = relationship("ProgramOutcome", back_populates="program", cascade="all, delete-orphan")
    courses  = relationship("Course",         back_populates="program", cascade="all, delete-orphan")


class ProgramOutcome(Base):
    __tablename__ = "program_outcomes"
    __table_args__ = (
        UniqueConstraint("program_id", "code"),
        Index("ix_program_outcomes_program", "program_id"),
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id    = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    code          = Column(String, nullable=False)
    description   = Column(Text, nullable=False)
    bloom_level   = Column(String, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    created_at    = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    program = relationship("Program", back_populates="outcomes")


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("program_id", "code"),
        Index("ix_courses_program",          "program_id"),
        Index("ix_courses_program_semester", "program_id", "semester"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id      = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    code            = Column(String, nullable=False)
    title           = Column(String, nullable=False)
    credits         = Column(Integer, nullable=False)
    semester        = Column(Integer, nullable=False)
    is_elective     = Column(Boolean, nullable=False, default=False)
    is_ai_generated = Column(Boolean, nullable=False, default=False)
    hours_lecture   = Column(Integer, nullable=True)
    hours_tutorial  = Column(Integer, nullable=True)
    hours_practical = Column(Integer, nullable=True)
    description     = Column(Text, nullable=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at      = Column(DateTime(timezone=True), nullable=True)

    program       = relationship("Program", back_populates="courses")
    prerequisites = relationship(
        "CoursePrerequisite",
        foreign_keys="CoursePrerequisite.course_id",
        back_populates="course",
        cascade="all, delete-orphan",
    )


class CoursePrerequisite(Base):
    __tablename__ = "course_prerequisites"
    __table_args__ = (
        UniqueConstraint("course_id", "prerequisite_course_id"),
        Index("ix_course_prereqs_course",  "course_id"),
        Index("ix_course_prereqs_prereq",  "prerequisite_course_id"),
    )

    id                     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id              = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    prerequisite_course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)

    course              = relationship("Course", foreign_keys=[course_id],              back_populates="prerequisites")
    prerequisite_course = relationship("Course", foreign_keys=[prerequisite_course_id])
