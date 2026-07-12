"""
Elective Registration — the student's choice of ONE course from one curriculum
elective slot.

There is no `ElectiveOffering`. The slot IS the offering: `ElectiveBasket`
(m01_program_advisor) is "Elective 1, 3 credits, Semester 3" on a PUBLISHED
program, and the Dean hangs the interchangeable option courses (AI301, ML304,
DL302, ...) off it there. If a student's current semester number matches the
slot's semester, the slot is registerable — nothing is opened or closed, and
the Dean never re-declares an elective in a second screen.

Phase 5 has no capacity model: no seat cap, no registration window, no
waitlist. Any number of students may choose the same option, and every student
who chose it forms ONE combined class across sections (MCA-A + MCA-B together)
— which is exactly what falls out of keying attendance and marks off
`course_id` rather than off a section.

Faculty is not a column here. The Dean assigns elective faculty through
Academic Ownership like any other subject, writing a PRIMARY Course Assignment
(subject_assignments) — the same source attendance and internal marks already
read. Electives need no special plumbing.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, String, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ElectiveRegistrationStatus(str, enum.Enum):
    REGISTERED = "REGISTERED"
    DROPPED    = "DROPPED"


class ElectiveRegistration(Base):
    """One student's pick of one option course from one slot, in one term.

    `basket_id` says which curriculum slot is being satisfied, `course_id`
    which option was chosen, and `semester_id` which running term it counts
    for. The unique constraint on (basket_id, student_user_id) is what enforces
    "choose exactly one" — a student cannot hold two options from the same slot.
    """
    __tablename__ = "elective_registrations"
    __table_args__ = (
        Index("ix_elective_registrations_basket",   "basket_id"),
        Index("ix_elective_registrations_semester", "semester_id"),
        Index("ix_elective_registrations_student",  "student_user_id"),
        Index("ix_elective_registrations_course",   "course_id"),
        UniqueConstraint("basket_id", "student_user_id", name="uq_elective_registrations_basket_student"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    basket_id        = Column(UUID(as_uuid=True), ForeignKey("elective_baskets.id", ondelete="CASCADE"), nullable=False)
    # The ONE option course the student picked from within the slot.
    course_id        = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    # The running term this registration counts for, resolved from the
    # student's active enrollment at registration time.
    semester_id      = Column(UUID(as_uuid=True), ForeignKey("acad_semesters.id", ondelete="CASCADE"), nullable=False)
    student_user_id  = Column(UUID(as_uuid=True), nullable=False)
    registered_at    = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    status           = Column(String(10), nullable=False, default=ElectiveRegistrationStatus.REGISTERED.value)
    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at       = Column(DateTime(timezone=True), nullable=True)
