"""
SIS Foundation — M11 School model.

Phase 1 implements School only (sis_schools table).
Future M11 phases add SIS-oriented APIs over the existing acad_* tables;
no new tables or renames are needed below this tier.

Full planned SIS hierarchy:
  sis_schools          ← this module (Phase 1)
    → acad_departments   (school_id FK added in migration 0028, m_academics)
      → acad_programs    (department_id FK, m_academics)
        → acad_batches   (program_id FK, m_academics)
          → acad_semesters (batch_id FK, m_academics)
            → acad_sections (semester_id FK, m_academics)
              → acad_enrollments (section_id FK, m_academics)
                → student_id (UUID → future sis_students)

ORM traversal available from Phase 1:
  school.departments[n].programs[n].batches[n].semesters[n]
         .sections[n].enrollments[n].student_id
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# H64.1: Import batch tracking
# ---------------------------------------------------------------------------

class SisImportBatch(Base):
    __tablename__ = "sis_import_batches"
    __table_args__ = (
        UniqueConstraint("batch_ref", name="uq_sis_import_batches_batch_ref"),
        Index("ix_sis_import_batches_imported_by",    "imported_by"),
        Index("ix_sis_import_batches_imported_at",    "imported_at"),
        Index("ix_sis_import_batches_is_rolled_back", "is_rolled_back"),
    )

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_ref      = Column(String(30),  nullable=False)
    imported_by    = Column(UUID(as_uuid=True), nullable=False)
    imported_at    = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    record_type    = Column(String(20),  nullable=False)   # STUDENT | FACULTY
    total_records  = Column(Integer(),   nullable=False, default=0)
    success_count  = Column(Integer(),   nullable=False, default=0)
    failed_count   = Column(Integer(),   nullable=False, default=0)
    is_rolled_back = Column(Boolean(),   nullable=False, default=False)
    rolled_back_by = Column(UUID(as_uuid=True), nullable=True)
    rolled_back_at = Column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Phase 1: SIS School
# ---------------------------------------------------------------------------

class SisSchool(Base):
    __tablename__ = "sis_schools"
    __table_args__ = (
        UniqueConstraint("code", name="uq_sis_schools_code"),
        UniqueConstraint("name", name="uq_sis_schools_name"),
        Index("ix_sis_schools_is_active", "is_active"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code        = Column(String(10), nullable=False)
    name        = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active   = Column(Boolean, nullable=False, default=True)
    created_at  = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at  = Column(DateTime(timezone=True), nullable=True)

    # Phase 1: root of the SIS traversal chain (string ref avoids circular import)
    departments = relationship("AcadDepartment", back_populates="school", lazy="select")


# ---------------------------------------------------------------------------
# H50: Student profile — extended identity record for STUDENT users
# ---------------------------------------------------------------------------

class SisStudentProfile(Base):
    __tablename__ = "sis_student_profiles"
    __table_args__ = (
        UniqueConstraint("usn", name="uq_sis_student_profiles_usn"),
        Index("ix_sis_student_profiles_usn", "usn"),
        Index("ix_sis_student_profiles_admission_year", "admission_year"),
        Index("ix_sis_student_profiles_import_batch_id", "import_batch_id"),
    )

    user_id                 = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    usn                     = Column(String(30), nullable=True)
    admission_year          = Column(Integer, nullable=True)
    date_of_birth           = Column(Date, nullable=True)
    phone                   = Column(String(20), nullable=True)
    address_line1           = Column(String(200), nullable=True)
    address_city            = Column(String(100), nullable=True)
    address_state           = Column(String(100), nullable=True)
    emergency_contact_name  = Column(String(100), nullable=True)
    emergency_contact_phone = Column(String(20), nullable=True)
    photo_url               = Column(String(500), nullable=True)
    notes                   = Column(Text, nullable=True)
    is_active               = Column(Boolean, nullable=False, default=True)
    lifecycle_status        = Column(String(20), nullable=False, default="ACTIVE")
    import_batch_id         = Column(UUID(as_uuid=True), ForeignKey("sis_import_batches.id", ondelete="SET NULL"), nullable=True)
    created_at              = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at              = Column(DateTime(timezone=True), nullable=True)

    lifecycle_history       = relationship("SisStudentLifecycleHistory", back_populates="student", lazy="select")


# ---------------------------------------------------------------------------
# H50: Faculty profile — extended identity record for FACULTY users
# ---------------------------------------------------------------------------

class SisFacultyProfile(Base):
    __tablename__ = "sis_faculty_profiles"
    __table_args__ = (
        UniqueConstraint("employee_id", name="uq_sis_faculty_profiles_employee_id"),
        Index("ix_sis_faculty_profiles_employee_id", "employee_id"),
        Index("ix_sis_faculty_profiles_primary_department_id", "primary_department_id"),
        Index("ix_sis_faculty_profiles_import_batch_id", "import_batch_id"),
    )

    user_id               = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    employee_id           = Column(String(30), nullable=False)
    designation           = Column(String(100), nullable=True)
    qualifications        = Column(Text, nullable=True)
    bio                   = Column(Text, nullable=True)
    office_location       = Column(String(200), nullable=True)
    phone                 = Column(String(20), nullable=True)
    joining_date          = Column(Date, nullable=True)
    specialization        = Column(String(200), nullable=True)
    primary_department_id = Column(UUID(as_uuid=True), ForeignKey("acad_departments.id", ondelete="SET NULL"), nullable=True)
    photo_url             = Column(String(500), nullable=True)
    is_active             = Column(Boolean, nullable=False, default=True)
    lifecycle_status      = Column(String(20), nullable=False, default="ACTIVE")
    import_batch_id       = Column(UUID(as_uuid=True), ForeignKey("sis_import_batches.id", ondelete="SET NULL"), nullable=True)
    created_at            = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at            = Column(DateTime(timezone=True), nullable=True)

    lifecycle_history     = relationship("SisFacultyLifecycleHistory", back_populates="faculty", lazy="select")


# ---------------------------------------------------------------------------
# H64.3: Student lifecycle history — append-only audit trail
# ---------------------------------------------------------------------------

class SisStudentLifecycleHistory(Base):
    __tablename__ = "sis_student_lifecycle_history"
    __table_args__ = (
        Index("ix_sis_slh_student_id", "student_id"),
        Index("ix_sis_slh_changed_at",  "changed_at"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id  = Column(UUID(as_uuid=True), ForeignKey("sis_student_profiles.user_id", ondelete="CASCADE"), nullable=False)
    from_status = Column(String(20), nullable=True)    # NULL for the initial creation entry
    to_status   = Column(String(20), nullable=False)
    reason      = Column(Text, nullable=True)
    changed_by  = Column(UUID(as_uuid=True), nullable=False)
    changed_at  = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    student = relationship("SisStudentProfile", back_populates="lifecycle_history")


# ---------------------------------------------------------------------------
# H64.4: Faculty lifecycle history — append-only audit trail
# ---------------------------------------------------------------------------

class SisFacultyLifecycleHistory(Base):
    __tablename__ = "sis_faculty_lifecycle_history"
    __table_args__ = (
        Index("ix_sis_flh_faculty_id", "faculty_id"),
        Index("ix_sis_flh_changed_at",  "changed_at"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    faculty_id  = Column(UUID(as_uuid=True), ForeignKey("sis_faculty_profiles.user_id", ondelete="CASCADE"), nullable=False)
    from_status = Column(String(20), nullable=True)
    to_status   = Column(String(20), nullable=False)
    reason      = Column(Text, nullable=True)
    changed_by  = Column(UUID(as_uuid=True), nullable=False)
    changed_at  = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    faculty = relationship("SisFacultyProfile", back_populates="lifecycle_history")
