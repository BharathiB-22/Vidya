"""
Elective Registration — offerings (seats per semester, keyed by BASKET, not
a single course) and student choices. An elective is never a single course:
`ElectiveBasket` (m01_program_advisor) groups several elective-tagged
courses (e.g. "Artificial Intelligence Electives" containing AI/DL/ML/...).
Opening an offering makes the whole basket available for a semester; each
student registers for ONE course from within that open basket
(`ElectiveRegistration.course_id`). Faculty is not tracked on the offering —
each course inside the basket already has its own faculty via Course
Assignment (subject_assignments).
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ElectiveOfferingStatus(str, enum.Enum):
    # New workflow: Faculty proposes -> Dean approves/rejects -> Admin publishes.
    PROPOSED      = "PROPOSED"
    DEAN_APPROVED = "DEAN_APPROVED"
    REJECTED      = "REJECTED"
    # Existing values, unchanged meaning: OPEN = published/registerable, CLOSED = registration closed.
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
        Index("ix_elective_offerings_basket",    "basket_id"),
        Index("ix_elective_offerings_status",   "status"),
    )

    id                       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    basket_id                = Column(UUID(as_uuid=True), ForeignKey("elective_baskets.id", ondelete="CASCADE"), nullable=False)
    semester_id              = Column(UUID(as_uuid=True), ForeignKey("acad_semesters.id", ondelete="CASCADE"), nullable=False)
    # Per-course cap, applied identically to every course inside the basket
    # (e.g. max_seats=30 means each of AI/DL/ML/... independently fills to 30).
    max_seats                = Column(Integer, nullable=False)
    registration_opens_at    = Column(DateTime(timezone=True), nullable=True)
    registration_closes_at   = Column(DateTime(timezone=True), nullable=True)
    status                   = Column(String(20), nullable=False, default=ElectiveOfferingStatus.OPEN.value)
    created_by_user_id       = Column(UUID(as_uuid=True), nullable=False)
    # Workflow provenance — all nullable; only populated when the offering goes
    # through the propose -> approve -> publish path (direct-create leaves these null).
    proposed_by_user_id      = Column(UUID(as_uuid=True), nullable=True)
    approved_by_user_id      = Column(UUID(as_uuid=True), nullable=True)
    approved_at              = Column(DateTime(timezone=True), nullable=True)
    published_by_user_id     = Column(UUID(as_uuid=True), nullable=True)
    published_at             = Column(DateTime(timezone=True), nullable=True)
    rejection_reason         = Column(Text, nullable=True)
    created_at               = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at               = Column(DateTime(timezone=True), nullable=True)


class ElectiveRegistration(Base):
    __tablename__ = "elective_registrations"
    __table_args__ = (
        Index("ix_elective_registrations_offering", "offering_id"),
        Index("ix_elective_registrations_student",  "student_user_id"),
        Index("ix_elective_registrations_course",   "course_id"),
        UniqueConstraint("offering_id", "student_user_id", name="uq_elective_registrations_offering_student"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    offering_id      = Column(UUID(as_uuid=True), ForeignKey("elective_offerings.id", ondelete="CASCADE"), nullable=False)
    # The ONE course the student picked from within the basket this offering opened.
    course_id        = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    student_user_id  = Column(UUID(as_uuid=True), nullable=False)
    registered_at    = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    status           = Column(String(10), nullable=False, default=ElectiveRegistrationStatus.REGISTERED.value)
    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at       = Column(DateTime(timezone=True), nullable=True)
