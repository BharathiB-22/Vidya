"""
Elective Registration — offerings (faculty/seats per semester) and student
choices. `Course.is_elective` (m01_program_advisor) only tags a course as an
elective *slot type* during curriculum design; these tables are the actual
student-choice workflow, which did not exist anywhere before this phase.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ElectiveOfferingStatus(str, enum.Enum):
    OPEN   = "OPEN"
    CLOSED = "CLOSED"


class ElectiveRegistrationStatus(str, enum.Enum):
    REGISTERED = "REGISTERED"
    DROPPED    = "DROPPED"
    WAITLISTED = "WAITLISTED"


class ElectiveOffering(Base):
    __tablename__ = "elective_offerings"
    __table_args__ = (
        Index("ix_elective_offerings_semester", "semester_id"),
        Index("ix_elective_offerings_course",   "course_id"),
        Index("ix_elective_offerings_status",   "status"),
    )

    id                       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id                = Column(UUID(as_uuid=True), ForeignKey("courses.id",        ondelete="CASCADE"), nullable=False)
    semester_id              = Column(UUID(as_uuid=True), ForeignKey("acad_semesters.id", ondelete="CASCADE"), nullable=False)
    faculty_user_id          = Column(UUID(as_uuid=True), nullable=True)
    max_seats                = Column(Integer, nullable=False)
    registration_opens_at    = Column(DateTime(timezone=True), nullable=True)
    registration_closes_at   = Column(DateTime(timezone=True), nullable=True)
    status                   = Column(String(10), nullable=False, default=ElectiveOfferingStatus.OPEN.value)
    created_by_user_id       = Column(UUID(as_uuid=True), nullable=False)
    created_at               = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at               = Column(DateTime(timezone=True), nullable=True)


class ElectiveRegistration(Base):
    __tablename__ = "elective_registrations"
    __table_args__ = (
        Index("ix_elective_registrations_offering", "offering_id"),
        Index("ix_elective_registrations_student",  "student_user_id"),
        UniqueConstraint("offering_id", "student_user_id", name="uq_elective_registrations_offering_student"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    offering_id      = Column(UUID(as_uuid=True), ForeignKey("elective_offerings.id", ondelete="CASCADE"), nullable=False)
    student_user_id  = Column(UUID(as_uuid=True), nullable=False)
    registered_at    = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    status           = Column(String(10), nullable=False, default=ElectiveRegistrationStatus.REGISTERED.value)
    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at       = Column(DateTime(timezone=True), nullable=True)
