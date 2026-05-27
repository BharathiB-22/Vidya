"""
Academic Structure — SQLAlchemy models.

Tables (all tenant-schema, no schema= kwarg):
  acad_departments  — CS, ECE, MBA, etc.
  acad_programs     — B.Tech CSE, M.Tech AI, etc. (FK → dept)
  acad_batches      — 2023-2027 cohort of a program (FK → program)
  acad_semesters    — Sem 1..N within a batch (FK → batch)
  acad_sections     — Section A, B, C within a semester (FK → semester)

Tenant isolation: search_path injected by _inject_search_path event at BEGIN.
Naming prefix `acad_` avoids collision with m01's `programs` table.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum,
    ForeignKey, Index, SmallInteger, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class DegreeType(str, enum.Enum):
    UG          = "UG"
    PG          = "PG"
    PHD         = "PHD"
    DIPLOMA     = "DIPLOMA"
    CERTIFICATE = "CERTIFICATE"


class AcadDepartment(Base):
    __tablename__ = "acad_departments"
    __table_args__ = (
        UniqueConstraint("name", name="uq_acad_departments_name"),
        UniqueConstraint("code", name="uq_acad_departments_code"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name        = Column(String, nullable=False)
    code        = Column(String(10), nullable=False)
    description = Column(Text, nullable=True)
    is_active   = Column(Boolean, nullable=False, default=True)
    created_at  = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at  = Column(DateTime(timezone=True), nullable=True)

    programs = relationship("AcadProgram", back_populates="department")


class AcadProgram(Base):
    __tablename__ = "acad_programs"
    __table_args__ = (
        UniqueConstraint("code", name="uq_acad_programs_code"),
        Index("ix_acad_programs_department_id", "department_id"),
    )

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_id  = Column(UUID(as_uuid=True), ForeignKey("acad_departments.id"), nullable=False)
    name           = Column(String, nullable=False)
    code           = Column(String(10), nullable=False)
    degree_type    = Column(Enum(DegreeType, native_enum=False), nullable=False)
    duration_years = Column(SmallInteger, nullable=False)
    is_active      = Column(Boolean, nullable=False, default=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at     = Column(DateTime(timezone=True), nullable=True)

    department = relationship("AcadDepartment", back_populates="programs")
    batches    = relationship("AcadBatch", back_populates="program")


class AcadBatch(Base):
    __tablename__ = "acad_batches"
    __table_args__ = (
        UniqueConstraint("program_id", "start_year", name="uq_acad_batches_program_start_year"),
        Index("ix_acad_batches_program_id", "program_id"),
    )

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("acad_programs.id"), nullable=False)
    name       = Column(String, nullable=False)
    start_year = Column(SmallInteger, nullable=False)
    end_year   = Column(SmallInteger, nullable=False)
    is_active  = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True)

    program   = relationship("AcadProgram", back_populates="batches")
    semesters = relationship("AcadSemester", back_populates="batch")


class AcadSemester(Base):
    __tablename__ = "acad_semesters"
    __table_args__ = (
        UniqueConstraint("batch_id", "number", name="uq_acad_semesters_batch_number"),
        Index("ix_acad_semesters_batch_id", "batch_id"),
    )

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id   = Column(UUID(as_uuid=True), ForeignKey("acad_batches.id"), nullable=False)
    number     = Column(SmallInteger, nullable=False)
    label      = Column(String, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date   = Column(Date, nullable=True)
    is_active  = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    batch    = relationship("AcadBatch", back_populates="semesters")
    sections = relationship("AcadSection", back_populates="semester")


class AcadSection(Base):
    __tablename__ = "acad_sections"
    __table_args__ = (
        UniqueConstraint("semester_id", "name", name="uq_acad_sections_semester_name"),
        Index("ix_acad_sections_semester_id", "semester_id"),
    )

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semester_id  = Column(UUID(as_uuid=True), ForeignKey("acad_semesters.id"), nullable=False)
    name         = Column(String, nullable=False)
    max_strength = Column(SmallInteger, nullable=True)
    is_active    = Column(Boolean, nullable=False, default=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    semester = relationship("AcadSemester", back_populates="sections")
