from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Student — the elective slots to choose from, and the choice itself.
# ---------------------------------------------------------------------------

class ElectiveOptionOut(BaseModel):
    """One interchangeable choice inside a slot — a real course with its own
    code, credits and faculty."""
    course_id: UUID
    code: str
    title: str
    credits: int
    course_type: str | None = None
    description: str | None = None
    faculty_user_id: UUID | None = None
    faculty_name: str | None = None
    # Demand, not capacity: Phase 5 has no seat cap.
    registered_count: int


class ElectiveSlotOut(BaseModel):
    basket_id: UUID
    name: str
    description: str | None
    credits: int
    semester: int
    semester_id: UUID
    # DRAFT | PUBLISHED | OPEN | CLOSED — see ElectiveSlotStatus.
    status: str
    # True only while the slot is OPEN. A PUBLISHED slot is visible but not yet
    # registerable; a CLOSED one is frozen.
    can_register: bool = False
    options: list[ElectiveOptionOut]
    # The option this student already picked for this slot, if any.
    chosen_course_id: UUID | None = None


class DeanElectiveSlotOut(BaseModel):
    """A slot as the Dean sees it for one running term, each choice carrying the
    faculty assigned for that term."""
    basket_id: UUID
    name: str
    description: str | None
    credits: int
    semester: int
    semester_id: UUID
    status: str
    options: list[ElectiveOptionOut]


class AssignChoiceFacultyBody(BaseModel):
    course_id: UUID
    faculty_user_id: UUID


class ElectiveRegisterBody(BaseModel):
    course_id: UUID  # the ONE option, from within the slot, the student picks


class ElectiveRegistrationOut(BaseModel):
    id: UUID
    basket_id: UUID
    basket_name: str
    course_id: UUID
    course_code: str
    course_title: str
    credits: int
    semester_id: UUID
    semester_label: str | None
    status: str
    registered_at: datetime
    is_current: bool  # True if this registration is for the student's current term


# ---------------------------------------------------------------------------
# Faculty — the combined elective class (one course, all sections).
# ---------------------------------------------------------------------------

class ElectiveRosterStudentOut(BaseModel):
    student_id: UUID
    student_name: str
    usn: str | None = None
    student_email: str | None = None
    section_name: str | None = None
    registered_at: datetime


class FacultyElectiveRosterOut(BaseModel):
    course_id: UUID
    course_code: str
    course_title: str
    basket_id: UUID
    semester_id: UUID
    semester_label: str | None
    basket_name: str
    total_students: int
    # How many sections this combined class draws from (MCA-A + MCA-B -> 2).
    section_count: int
    students: list[ElectiveRosterStudentOut]
