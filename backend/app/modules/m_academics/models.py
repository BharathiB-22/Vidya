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
    ForeignKey, Index, Integer, PrimaryKeyConstraint, SmallInteger, String, Text,
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
        Index("ix_acad_departments_school_id", "school_id"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id   = Column(UUID(as_uuid=True), ForeignKey("sis_schools.id"), nullable=True)
    name        = Column(String, nullable=False)
    code        = Column(String(10), nullable=False)
    description = Column(Text, nullable=True)
    is_active   = Column(Boolean, nullable=False, default=True)
    created_at  = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at  = Column(DateTime(timezone=True), nullable=True)

    # M11 SIS: back-reference to SisSchool (string ref avoids circular import)
    school   = relationship("SisSchool", back_populates="departments")
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

    semester    = relationship("AcadSemester", back_populates="sections")
    enrollments = relationship("AcadEnrollment", back_populates="section")


class AcadEnrollment(Base):
    __tablename__ = "acad_enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", name="uq_acad_enrollments_student_id"),
        Index("ix_acad_enrollments_section_id", "section_id"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id  = Column(UUID(as_uuid=True), nullable=False)
    section_id  = Column(UUID(as_uuid=True), ForeignKey("acad_sections.id"), nullable=False)
    enrolled_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    is_active   = Column(Boolean, nullable=False, default=True)

    section = relationship("AcadSection", back_populates="enrollments")


# ---------------------------------------------------------------------------
# H-31: Faculty Subject Assignment
# ---------------------------------------------------------------------------

class CourseRoleInCourse(str, enum.Enum):
    PRIMARY    = "PRIMARY"
    CO_FACULTY = "CO_FACULTY"
    GUEST      = "GUEST"


class SubjectAssignment(Base):
    """Records which faculty member owns a course in a given semester.

    Constraint enforced at service layer: at most one active PRIMARY per
    (course_id, semester_id) pair. History is never deleted — revocation
    sets is_active=False and stamps revoked_at / revoked_by_user_id.
    """
    __tablename__ = "subject_assignments"
    __table_args__ = (
        Index("ix_subject_assignments_course_sem",  "course_id",       "semester_id"),
        Index("ix_subject_assignments_faculty",      "faculty_user_id", "is_active"),
        Index("ix_subject_assignments_active",       "is_active"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id           = Column(UUID(as_uuid=True), ForeignKey("courses.id",        ondelete="CASCADE"), nullable=False)
    faculty_user_id     = Column(UUID(as_uuid=True), nullable=False)
    semester_id         = Column(UUID(as_uuid=True), ForeignKey("acad_semesters.id", ondelete="CASCADE"), nullable=False)
    assigned_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    assigned_at         = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    is_active           = Column(Boolean, nullable=False, default=True)
    role_in_course      = Column(Enum(CourseRoleInCourse, name="courseroleincoarse", native_enum=False), nullable=False)
    revoked_at          = Column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id  = Column(UUID(as_uuid=True), nullable=True)


# ---------------------------------------------------------------------------
# ERP Onboarding (Phase 1): USN sequence allocation
# ---------------------------------------------------------------------------

class UsnSequenceCounter(Base):
    """Per-(school, admission year, program) monotonic USN sequence counter.

    `next_seq` is the next sequence number to hand out (starts at 1).  Blocks are
    reserved atomically in `UsnAllocator` via
        INSERT ... ON CONFLICT DO UPDATE SET next_seq = next_seq + n RETURNING
    The ON CONFLICT row lock serialises concurrent allocations, so every issued
    USN sequence is contiguous, gap-free, and never double-assigned.  The counter
    resets per triple: SCA/2026/MCA is independent of SCA/2026/BCA and SCA/2027/MCA.

    admission_year is stored full (e.g. 2026); the USN string renders the 2-digit
    suffix.  Import-layer year validation keeps years within one century so that
    rendering stays unambiguous.
    """
    __tablename__ = "usn_sequence_counters"
    __table_args__ = (
        PrimaryKeyConstraint(
            "school_code", "admission_year", "program_code",
            name="pk_usn_sequence_counters",
        ),
    )

    school_code    = Column(String(10), nullable=False)
    admission_year = Column(Integer,    nullable=False)
    program_code   = Column(String(10), nullable=False)
    next_seq       = Column(Integer,    nullable=False, server_default=text("1"))
    created_at     = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at     = Column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# ERP Onboarding (Phase 1 / Step 3): Faculty ↔ Program mapping
# ---------------------------------------------------------------------------

class FacultyProgramAssignment(Base):
    """Many-to-many faculty ↔ program membership (program teaching scope).

    Distinct from `SisFacultyProfile.primary_department_id` (the faculty's home
    department).  Soft-revoke only — rows are never deleted; revocation stamps
    `is_active=False`, `revoked_by`, `revoked_at`.  A partial-unique index
    enforces at most one ACTIVE assignment per (faculty, program), while still
    allowing historical revoked rows and re-assignment after revocation.
    """
    __tablename__ = "faculty_program_assignments"
    __table_args__ = (
        Index(
            "uq_fpa_active_faculty_program",
            "faculty_user_id", "program_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        Index("ix_fpa_program",        "program_id"),
        Index("ix_fpa_faculty_active", "faculty_user_id", "is_active"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    faculty_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id",          ondelete="CASCADE"), nullable=False)
    program_id      = Column(UUID(as_uuid=True), ForeignKey("acad_programs.id",   ondelete="CASCADE"), nullable=False)
    is_active       = Column(Boolean, nullable=False, default=True)
    assigned_by     = Column(UUID(as_uuid=True), nullable=False)
    assigned_at     = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    revoked_by      = Column(UUID(as_uuid=True), nullable=True)
    revoked_at      = Column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# ERP Onboarding (Phase 1.5): Faculty responsibility grants + FAC code counter
# ---------------------------------------------------------------------------

class FacultyRoleGrant(Base):
    """Responsibilities a single FACULTY account holds simultaneously.

    role_code ∈ {GUIDE, EVALUATOR, BOARD, DEAN} (validated at the service layer).
    The faculty's base login role stays `users.role = FACULTY`; responsibilities
    are grants, never separate accounts.  Soft-revoke only — rows are never
    deleted; revocation stamps `is_active=False`, `revoked_by`, `revoked_at`.
    A partial-unique index enforces at most one ACTIVE grant per
    (faculty_user_id, role_code), while permitting historical revoked rows and
    re-granting (reactivation in place) after revocation.

    Mirrors the FacultyProgramAssignment soft-revoke/audit pattern exactly.
    """
    __tablename__ = "faculty_role_grants"
    __table_args__ = (
        Index(
            "uq_frg_active_faculty_role",
            "faculty_user_id", "role_code",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        Index("ix_frg_role",           "role_code", "is_active"),
        Index("ix_frg_faculty_active", "faculty_user_id", "is_active"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    faculty_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_code       = Column(String(20), nullable=False)
    is_active       = Column(Boolean, nullable=False, default=True)
    granted_by      = Column(UUID(as_uuid=True), nullable=False)
    granted_at      = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    revoked_by      = Column(UUID(as_uuid=True), nullable=True)
    revoked_at      = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at      = Column(DateTime(timezone=True), nullable=True)


class FacultyCodeCounter(Base):
    """Per-prefix monotonic counter for faculty-code allocation (e.g. FAC0001).

    `next_value` is the next sequence number to hand out (starts at 1).  Blocks
    are reserved atomically via INSERT ... ON CONFLICT DO UPDATE ... RETURNING,
    mirroring UsnSequenceCounter, so issued codes are contiguous, gap-free, and
    never double-assigned under concurrency.  Default prefix is `FAC`
    (tenant-global); a per-school prefix (e.g. `SCAFAC`) is also supported.
    """
    __tablename__ = "faculty_code_counters"

    prefix     = Column(String(15), primary_key=True)
    next_value = Column(Integer, nullable=False, server_default=text("1"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True)
