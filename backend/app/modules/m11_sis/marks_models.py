"""
SIS Internal Marks — H57 SQLAlchemy models.

Tables:
  sis_marks_components  — one row per assessment component per course+section
  sis_marks_entries     — one row per student per component

Component lifecycle:
  DRAFT      → faculty creating/editing; not visible to students
  PUBLISHED  → marks visible to students; edits require reason; definition immutable
  LOCKED     → finalized by Dean/Admin; no edits; audit gate for hall-ticket eligibility

Entry semantics:
  marks_obtained = NULL  → not yet entered
  marks_obtained = 0..N  → entered (0 is valid — student scored zero)
  marks_obtained > max_marks → rejected at service layer (422)
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index,
    Numeric, SmallInteger, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class ComponentType(str, enum.Enum):
    CIE         = "CIE"
    ASSIGNMENT  = "ASSIGNMENT"
    QUIZ        = "QUIZ"
    LAB         = "LAB"
    OTHER       = "OTHER"


class ComponentStatus(str, enum.Enum):
    DRAFT      = "DRAFT"
    PUBLISHED  = "PUBLISHED"
    LOCKED     = "LOCKED"


class SisMarksComponent(Base):
    __tablename__ = "sis_marks_components"
    __table_args__ = (
        UniqueConstraint(
            "course_id", "section_id", "name",
            name="uq_marks_components_course_section_name",
        ),
        Index("ix_marks_components_course_section", "course_id",   "section_id"),
        Index("ix_marks_components_section_status", "section_id",  "status"),
        Index("ix_marks_components_semester",       "semester_id"),
        Index("ix_marks_components_status",         "status"),
        Index("ix_marks_components_faculty",        "created_by"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Context (semester_id denormalised for fast filtering without JOIN chain)
    course_id        = Column(UUID(as_uuid=True), ForeignKey("courses.id",        ondelete="CASCADE"), nullable=False)
    section_id       = Column(UUID(as_uuid=True), ForeignKey("acad_sections.id",  ondelete="CASCADE"), nullable=False)
    semester_id      = Column(UUID(as_uuid=True), ForeignKey("acad_semesters.id", ondelete="CASCADE"), nullable=False)
    created_by       = Column(UUID(as_uuid=True), nullable=False)   # faculty_user_id; plain UUID — codebase pattern

    # Component definition
    component_type   = Column(String(20),           nullable=False)
    name             = Column(String(100),           nullable=False)
    max_marks        = Column(Numeric(6, 2),         nullable=False)
    weightage        = Column(Numeric(5, 2),         nullable=True)   # optional; for future weighted totals
    due_date         = Column(Date,                  nullable=True)
    display_order    = Column(SmallInteger,          nullable=True)

    # Lifecycle
    status           = Column(String(12), nullable=False, server_default=text("'DRAFT'"))
    published_at     = Column(DateTime(timezone=True), nullable=True)
    locked_at        = Column(DateTime(timezone=True), nullable=True)
    locked_by        = Column(UUID(as_uuid=True),      nullable=True)

    # Reopen (LOCKED → PUBLISHED)
    reopened_by      = Column(UUID(as_uuid=True),       nullable=True)
    reopened_at      = Column(DateTime(timezone=True),  nullable=True)
    reopen_reason    = Column(Text,                     nullable=True)

    is_active        = Column(Boolean, nullable=False, default=True)
    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at       = Column(DateTime(timezone=True), nullable=True)

    entries = relationship(
        "SisMarksEntry",
        back_populates="component",
        cascade="all, delete-orphan",
    )


class SisMarksEntry(Base):
    __tablename__ = "sis_marks_entries"
    __table_args__ = (
        UniqueConstraint("component_id", "student_id", name="uq_marks_entries_component_student"),
        Index("ix_marks_entries_component", "component_id"),
        Index("ix_marks_entries_student",   "student_id"),
    )

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    component_id   = Column(UUID(as_uuid=True), ForeignKey("sis_marks_components.id", ondelete="CASCADE"), nullable=False)
    student_id     = Column(UUID(as_uuid=True), nullable=False)   # plain UUID — codebase pattern

    marks_obtained = Column(Numeric(6, 2), nullable=True)   # NULL = not yet entered
    remarks        = Column(Text,          nullable=True)

    # First save
    marked_by      = Column(UUID(as_uuid=True),         nullable=True)
    marked_at      = Column(DateTime(timezone=True),    nullable=True)

    # Subsequent edits (mandatory reason when component.status = PUBLISHED)
    edited_by      = Column(UUID(as_uuid=True),         nullable=True)
    edited_at      = Column(DateTime(timezone=True),    nullable=True)
    edit_reason    = Column(Text,                       nullable=True)

    created_at     = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at     = Column(DateTime(timezone=True), nullable=True)

    component = relationship("SisMarksComponent", back_populates="entries")
